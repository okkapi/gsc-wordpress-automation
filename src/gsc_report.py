"""GSC（Google Search Console）から検索パフォーマンスを取得して週次レポートを生成する。

初回実行時：ブラウザが開いてOAuth認証 → GSC_HOME/gsc_token.json に保存
2回目以降：保存済みトークンで自動実行（認証不要）

使い方:
  python3 gsc_report.py                  # 直近28日のTopクエリ
  python3 gsc_report.py --weekly         # 先週/先々週の比較レポート
  python3 gsc_report.py --rewrite-target # リライト推奨記事を抽出
"""
import os
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

# 対象サイトと認証ファイルの場所は環境変数で差し替えられる。
# 未設定なら、このスクリプトが置かれたディレクトリを基準にする。
BASE_DIR = Path(os.environ.get("GSC_HOME", Path(__file__).resolve().parent))
SITE_URL = os.environ.get("GSC_SITE_URL", "https://ai-torisetu.com/")
CLIENT_SECRETS = str(BASE_DIR / "oauth_client.json")
TOKEN_PATH = str(BASE_DIR / "gsc_token.json")


def get_service():
    """OAuth認証してSearch Console APIサービスを返す"""
    creds = None
    if Path(TOKEN_PATH).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        print(f"✓ トークン保存: {TOKEN_PATH}")
    return build("searchconsole", "v1", credentials=creds)


def query(service, start: str, end: str, dimensions=None, row_limit=100):
    body = {
        "startDate": start,
        "endDate": end,
        "dimensions": dimensions or ["query"],
        "rowLimit": row_limit,
    }
    return service.searchanalytics().query(siteUrl=SITE_URL, body=body).execute().get("rows", [])


def report_top_queries(service, days=28, top=20):
    end = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=3 + days)).strftime("%Y-%m-%d")
    rows = query(service, start, end, ["query"], row_limit=top)
    print(f"\n=== 検索クエリ Top{top}（{start} 〜 {end}） ===")
    print(f"{'順':>3} {'クリック':>5} {'表示':>6} {'CTR':>5} {'順位':>5} クエリ")
    for i, r in enumerate(rows, 1):
        kw = r["keys"][0]
        clicks = r.get("clicks", 0)
        impr = r.get("impressions", 0)
        ctr = r.get("ctr", 0) * 100
        pos = r.get("position", 0)
        print(f"{i:>3} {clicks:>5.0f} {impr:>6.0f} {ctr:>4.1f}% {pos:>5.1f} {kw}")


def report_weekly_diff(service):
    """先週と先々週を比較。順位上昇/下降を表示"""
    today = datetime.now()
    last_end = (today - timedelta(days=3)).strftime("%Y-%m-%d")
    last_start = (today - timedelta(days=10)).strftime("%Y-%m-%d")
    prev_end = (today - timedelta(days=10)).strftime("%Y-%m-%d")
    prev_start = (today - timedelta(days=17)).strftime("%Y-%m-%d")

    last = {r["keys"][0]: r for r in query(service, last_start, last_end, ["query"], 200)}
    prev = {r["keys"][0]: r for r in query(service, prev_start, prev_end, ["query"], 200)}

    diffs = []
    for kw, r in last.items():
        cur_pos = r.get("position", 0)
        prev_pos = prev[kw].get("position", 0) if kw in prev else None
        if prev_pos and r.get("impressions", 0) >= 5:
            diffs.append((kw, prev_pos, cur_pos, r.get("clicks", 0), r.get("impressions", 0)))

    print(f"\n=== 順位変動（先週 vs 先々週・表示5回以上） ===")
    print(f"\n[ 上昇TOP10 ]")
    print(f"{'順位差':>7} {'前→今':>11} {'クリック':>5} {'表示':>5} クエリ")
    for kw, p, c, cl, im in sorted(diffs, key=lambda x: x[1] - x[2], reverse=True)[:10]:
        print(f"  +{p-c:>5.1f} {p:>4.1f}→{c:>4.1f} {cl:>5.0f} {im:>5.0f} {kw}")
    print(f"\n[ 下降TOP10 ]")
    for kw, p, c, cl, im in sorted(diffs, key=lambda x: x[1] - x[2])[:10]:
        diff = p - c
        print(f"  {diff:>+6.1f} {p:>4.1f}→{c:>4.1f} {cl:>5.0f} {im:>5.0f} {kw}")


def report_rewrite_targets(service):
    """リライト推奨記事を抽出：表示は多いがクリック少ない or 11〜20位の惜しい記事"""
    end = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=31)).strftime("%Y-%m-%d")
    rows = query(service, start, end, ["page", "query"], row_limit=500)

    pages = {}
    for r in rows:
        page = r["keys"][0]
        kw = r["keys"][1]
        impr = r.get("impressions", 0)
        clicks = r.get("clicks", 0)
        pos = r.get("position", 0)
        pages.setdefault(page, []).append((kw, impr, clicks, pos))

    print(f"\n=== リライト推奨記事（直近28日） ===\n")
    candidates = []
    for page, kws in pages.items():
        # 各ページの代表値（最大imprのKW）
        kws.sort(key=lambda x: x[1], reverse=True)
        top_kw, top_impr, top_clicks, top_pos = kws[0]
        ctr = (top_clicks / top_impr * 100) if top_impr else 0
        # 惜しい記事の条件
        is_almost = 11 <= top_pos <= 25 and top_impr >= 50
        is_low_ctr = top_pos <= 10 and ctr < 3 and top_impr >= 100
        if is_almost or is_low_ctr:
            reason = "10位圏外で惜しい" if is_almost else "上位だがCTR低"
            candidates.append((page, top_kw, top_impr, top_clicks, top_pos, ctr, reason))

    candidates.sort(key=lambda x: x[2], reverse=True)
    print(f"{'表示':>5} {'クリック':>5} {'順位':>5} {'CTR':>5} 主KW｜記事URL（理由）")
    for page, kw, im, cl, pos, ctr, reason in candidates[:15]:
        short = page.replace("https://ai-torisetu.com/", "/")[:50]
        print(f"{im:>5.0f} {cl:>5.0f} {pos:>5.1f} {ctr:>4.1f}% [{kw}] {short} ({reason})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weekly", action="store_true", help="先週/先々週の比較")
    parser.add_argument("--rewrite-target", action="store_true", help="リライト推奨記事")
    parser.add_argument("--top", type=int, default=20, help="Topクエリ表示数")
    parser.add_argument("--days", type=int, default=28, help="集計日数")
    args = parser.parse_args()

    service = get_service()

    if args.weekly:
        report_weekly_diff(service)
    elif args.rewrite_target:
        report_rewrite_targets(service)
    else:
        report_top_queries(service, days=args.days, top=args.top)


if __name__ == "__main__":
    main()
