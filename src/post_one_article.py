#!/usr/bin/env python3
"""1記事分のAI関連テーマを生成してpost_one_article.pyを実行する"""
import subprocess
import sys
import os
import anthropic
from dotenv import load_dotenv
from datetime import datetime

# 開発機（macOS）と本番サーバ（VPS）でディレクトリ構成が異なるため、
# 候補パスを順に評価して最初に存在したものを採用する。
# 環境ごとに設定ファイルを分けるのではなく、コード1箇所で吸収する方針。
def _first_existing(*paths):
    for p in paths:
        p = os.path.expanduser(p)
        if os.path.exists(p):
            return p
    return None

# APP_HOME が指定されていればそれを最優先。なければ既知の候補を順に探す。
_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = (os.environ.get("APP_HOME")
             or _first_existing("~/ai_blog", "~/app")
             or _HERE)

ENV_PATH = _first_existing(
    os.path.join(_DATA_DIR, ".env"),
    "~/.env_ai",
) or os.path.join(_DATA_DIR, ".env")
load_dotenv(ENV_PATH, override=True)

GENERATE_SCRIPT = os.environ.get("GENERATE_SCRIPT") or _first_existing(
    "~/.claude/skills/wp-blog-writer/scripts/generate_and_post.py",
    "~/ai_blog/generate_and_post.py",
) or os.path.expanduser("~/ai_blog/generate_and_post.py")

LOG_PATH = os.path.join(_DATA_DIR, "daily_articles.log")


def log(message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n")
    print(message)


TOPIC_PATTERNS = [
    "比較記事（例：『ChatGPT Plus と Claude Pro を1ヶ月使って比較』『Notion AI vs Obsidian AI』のようにツールを2つ並べる）",
    "やってみた体験談（例：『ChatGPTで議事録自動化を1ヶ月試した結果』のように具体的な期間や数値を含む）",
    "業種・職種特化（例：『中小企業の経理がChatGPTで月20時間削減した方法』『個人塾講師のClaude活用術』のように対象を絞る）",
    "ロングテール課題解決型（例：『ChatGPT 議事録 文字起こし 制限 対処法』のように3〜4語の具体的な悩みベース）",
    "おすすめN選（例：『ChatGPTプラグイン おすすめ7選 2026年版』のように購入・選択意図に応える）",
    "始め方ガイド（例：『主婦がClaudeで在宅副業を始める7ステップ』のようにペルソナ＋手順）",
]


def _load_gsc_candidates() -> list:
    """GSC実データから抽出した記事ネタ候補を読み込む。確率1/3で使用"""
    path = os.path.join(_DATA_DIR, "topic_candidates.txt")
    if not os.path.exists(path):
        return []
    candidates = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            kw = line.split("\t")[0].strip()
            if kw:
                candidates.append(kw)
    return candidates


PILLAR_INFO = {
    "909": ("AIライティング副業の始め方", "https://ai-torisetu.com/ai-writing-sidehustle-guide/"),
    "931": ("ChatGPT業務効率化完全ガイド", "https://ai-torisetu.com/chatgpt-business-efficiency-guide/"),
}


def _load_cluster_topics() -> list:
    """柱記事に紐づくクラスターキーワードを読み込む。確率30%で使用。
    返り値: [(pillar_id, keyword), ...]
    """
    path = os.path.join(_DATA_DIR, "cluster_topics.txt")
    if not os.path.exists(path):
        return []
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" not in line:
                continue
            pid, kw = line.split("|", 1)
            items.append((pid.strip(), kw.strip()))
    return items


def suggest_topic(client: anthropic.Anthropic) -> str:
    import random
    from google_suggest import pick_random_keywords

    now = datetime.now().strftime("%Y年%m月%d日 %H時")
    pattern = random.choice(TOPIC_PATTERNS)

    # Googleサジェストから実検索キーワードを5個取得（失敗時は空でフォールバック）
    trending = pick_random_keywords(n=5)

    # GSC実データから「自サイトに必要なキーワード」を取得
    gsc_kws = _load_gsc_candidates()
    gsc_pick = random.choice(gsc_kws) if gsc_kws and random.random() < 0.4 else None

    # トピッククラスター：30%確率で柱記事に紐づく深掘りテーマを選ぶ
    cluster_topics = _load_cluster_topics()
    cluster_pick = random.choice(cluster_topics) if cluster_topics and random.random() < 0.3 else None

    hints = []
    if cluster_pick:
        pid, kw = cluster_pick
        pillar_title, pillar_url = PILLAR_INFO.get(pid, ("柱記事", ""))
        hints.append(f"\n【最優先：このキーワードで「柱記事」の派生記事を書く（クラスター戦略）】\n- キーワード: {kw}\n- 柱記事: 「{pillar_title}」 ({pillar_url})\n- 本文中に柱記事への内部リンクを必ず1箇所自然に含めること。アンカーテキストは柱記事のタイトル全文か関連語にする。")
    elif gsc_pick:
        hints.append(f"\n【最優先：このキーワードを盛り込んだテーマにすること（自サイトで表示はあるけど記事が無い検索ニーズ）】\n- {gsc_pick}")
    if trending:
        hints.append("\n【参考：いま実際にGoogleで検索されているキーワード】\n" + "\n".join(f"- {kw}" for kw in trending))
    trending_hint = "\n".join(hints)

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"""今（{now}）のAI関連ブログ記事のテーマを1つ考えてください。

【記事タイプ】
{pattern}
{trending_hint}

【必須条件】
- 上記タイプに沿った具体的なテーマにする
- 上記の参考キーワードがあれば、検索ニーズと合致するものを優先的に取り入れる（必須ではない）
- タイトルにロングテールキーワード（3語以上の具体的な検索語）を含める
- 抽象的な「〇〇の活用法」「〇〇とは」「〇〇完全ガイド」は禁止
- 購入・行動意図のあるキーワード（おすすめ／比較／始め方／料金／体験談／月◯円）を1つ以上入れる
- 対象読者（業種・職種・状況）を1つ絞る
- 日本語で35〜60文字

テーマのみを1行で出力してください。前置き・説明・記号は不要。"""
        }]
    )
    return response.content[0].text.strip()


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log("エラー：ANTHROPIC_API_KEYが設定されていません")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    log("テーマを生成中...")
    topic = suggest_topic(client)
    log(f"テーマ決定：{topic}")

    result = subprocess.run(
        [sys.executable, GENERATE_SCRIPT, "--theme", topic],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        log(line)
    if result.returncode != 0:
        log(f"エラー：{result.stderr[:300]}")
        sys.exit(1)

    # 公開された記事URLを抽出してインデックス申請（IndexNow）
    # 記事IDを抽出してWP APIで公開URLを取得（wp-adminの編集URLは無視）
    try:
        import re, requests
        from requests.auth import HTTPBasicAuth
        pid_m = re.search(r"記事ID[:：]\s*(\d+)", result.stdout)
        ng_m = re.search(r"下書きに振り分け", result.stdout)
        if pid_m and not ng_m:
            pid = pid_m.group(1)
            wp_url = os.getenv("WP_URL").rstrip("/")
            auth = HTTPBasicAuth(os.getenv("WP_USER"), os.getenv("WP_PASSWORD"))
            r = requests.get(f"{wp_url}/wp-json/wp/v2/posts/{pid}",
                params={"_fields": "link,status"}, auth=auth, timeout=15).json()
            if r.get("status") == "publish" and r.get("link"):
                from index_request import notify_new_post
                notify_new_post(r["link"])
                log(f"インデックス申請: {r['link']}")
            else:
                log(f"インデックス申請スキップ（下書きor非公開）: ID:{pid}")
        elif ng_m:
            log("インデックス申請スキップ（自己チェックNGで下書き化）")
    except Exception as e:
        log(f"インデックス申請スキップ: {e}")


if __name__ == "__main__":
    main()
