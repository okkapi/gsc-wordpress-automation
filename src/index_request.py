"""新規記事のインデックス申請を自動化する。
- Bing/Yandex: IndexNow API（即時反映、無料）
- Google: sitemap (/wp-sitemap.xml) はGSCに提出済みなので、自然クロール待ち
  ※ Google sitemap pingエンドポイントは2023年に廃止されたため未使用
"""
import requests

INDEXNOW_KEY = "7cf200aa72244273984512c919592e72"
HOST = "ai-torisetu.com"


def ping_indexnow(url: str) -> bool:
    """Bing/YandexにIndexNow経由で即時通知"""
    endpoint = "https://api.indexnow.org/IndexNow"
    payload = {
        "host": HOST,
        "key": INDEXNOW_KEY,
        "keyLocation": f"https://{HOST}/{INDEXNOW_KEY}.txt",
        "urlList": [url],
    }
    try:
        r = requests.post(endpoint, json=payload, timeout=10)
        return r.status_code in (200, 202)
    except Exception as e:
        print(f"  IndexNow error: {e}")
        return False


def notify_new_post(post_url: str) -> None:
    """新規記事公開時に呼ぶ。Bing/Yandexに通知。"""
    if ping_indexnow(post_url):
        print(f"  ✓ IndexNow通知（Bing/Yandex）: {post_url}")
    else:
        print(f"  ⚠ IndexNow失敗")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        notify_new_post(sys.argv[1])
    else:
        print("Usage: python3 index_request.py <article_url>")
