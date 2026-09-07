"""GSC実データから「記事ネタ候補」を自動抽出する。
- 表示はあるけどクリック0のクエリ＝既存記事がまだないニーズ
- 順位30〜100位で表示が多めのクエリ＝記事を書けば上位狙えそうなニッチ
これらを GSC_HOME/topic_candidates.txt に書き出し、post_one_article.py が参照する。
"""
import os
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
OUTPUT = str(BASE_DIR / "topic_candidates.txt")


def get_service():
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
    return build("searchconsole", "v1", credentials=creds)


def extract_candidates() -> list:
    """記事ネタ候補（実検索キーワード）を抽出"""
    service = get_service()
    end = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=33)).strftime("%Y-%m-%d")

    body = {
        "startDate": start,
        "endDate": end,
        "dimensions": ["query"],
        "rowLimit": 500,
    }
    rows = service.searchanalytics().query(siteUrl=SITE_URL, body=body).execute().get("rows", [])

    candidates = []
    for r in rows:
        kw = r["keys"][0].strip()
        clicks = r.get("clicks", 0)
        impr = r.get("impressions", 0)
        pos = r.get("position", 0)

        # ① クリック0だが表示2回以上 ＆ 順位が低め（30位以下）= 新規記事を書く価値あり
        # ② 順位 20〜80位 で表示が多め = 既存記事のリライトより新記事の方が早いケース
        if (clicks == 0 and impr >= 2 and pos >= 20) or (20 <= pos <= 80 and impr >= 3):
            # ノイズ除外
            if len(kw) < 3 or 'hello world' in kw.lower():
                continue
            # 短すぎるクエリ（1単語）も除外
            if len(kw.split()) <= 1 and len(kw) < 6:
                continue
            candidates.append((kw, impr, pos))

    # impressionsで降順
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:30]


def main():
    candidates = extract_candidates()
    with open(OUTPUT, "w", encoding="utf-8") as f:
        for kw, impr, pos in candidates:
            f.write(f"{kw}\timpr:{impr}\tpos:{pos:.1f}\n")
    print(f"✓ {len(candidates)}件の候補を {OUTPUT} に保存")
    print("\n=== Top10 ===")
    for kw, impr, pos in candidates[:10]:
        print(f"  [表示{impr}回・順位{pos:.1f}] {kw}")


if __name__ == "__main__":
    main()
