"""Google Suggest（オートコンプリート）から検索ニーズの強いキーワードを取得する。
post_one_article.py から import して、Claudeのテーマ生成に「実検索キーワード」をヒントとして渡す。
"""
import requests
import urllib.parse
import random


# AI関連のシード語（拡張可能）
SEED_KEYWORDS = [
    "ChatGPT", "Claude", "Gemini", "Copilot", "Perplexity",
    "AI ツール", "AI 副業", "AI 業務効率化", "AI 自動化",
    "プロンプト", "生成AI", "AI 画像生成", "AI ライティング",
    "AI 議事録", "AI 文字起こし", "AI コーディング", "AI 動画",
    "ChatGPT 使い方", "Claude 使い方",
]


def fetch_suggestions(seed: str, lang: str = "ja", timeout: int = 8) -> list:
    """Google Suggestからサジェストキーワードを取得する。
    失敗時は空リストを返す（実装はベストエフォート）。
    """
    url = (
        "https://www.google.com/complete/search"
        f"?client=firefox&hl={lang}&q={urllib.parse.quote(seed)}"
    )
    try:
        r = requests.get(
            url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"},
        )
        if not r.ok:
            return []
        data = r.json()
        return data[1] if len(data) >= 2 and isinstance(data[1], list) else []
    except Exception:
        return []


def collect_trending_keywords(seeds: list = None, max_per_seed: int = 8) -> list:
    """複数のシード語からサジェストを集めて、重複を除いたキーワードリストを返す"""
    seeds = seeds if seeds is not None else SEED_KEYWORDS
    all_kw = []
    for seed in seeds:
        suggestions = fetch_suggestions(seed)
        for kw in suggestions[:max_per_seed]:
            kw = kw.strip()
            if kw and kw not in all_kw and 4 <= len(kw) <= 50:
                all_kw.append(kw)
    return all_kw


def pick_random_keywords(n: int = 5) -> list:
    """サジェストプールからランダムにn個ピック。失敗時は空リスト"""
    pool = collect_trending_keywords()
    if not pool:
        return []
    random.shuffle(pool)
    return pool[:n]


if __name__ == "__main__":
    # 動作確認用：サジェスト取得とランダム抽出を表示
    print("=== シード別サジェスト ===")
    for seed in SEED_KEYWORDS[:5]:
        sugs = fetch_suggestions(seed)
        print(f"  {seed}: {sugs[:5]}")
    print()
    print("=== ランダム5個ピック ===")
    for kw in pick_random_keywords(5):
        print(f"  - {kw}")
