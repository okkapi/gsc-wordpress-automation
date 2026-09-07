import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

WP_URL = os.getenv("WP_URL")
WP_USER = os.getenv("WP_USER")
WP_PASSWORD = os.getenv("WP_PASSWORD")


def post_article(title: str, content: str, status: str = "draft") -> dict:
    endpoint = f"{WP_URL}/wp-json/wp/v2/posts"
    payload = {
        "title": title,
        "content": content,
        "status": status,
    }
    response = requests.post(
        endpoint,
        json=payload,
        auth=HTTPBasicAuth(WP_USER, WP_PASSWORD),
    )
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    result = post_article(
        "【テスト】Claude Codeから自動投稿できました！",
        "<p>これはClaude Codeから自動投稿したテスト記事です。</p>"
    )
    print(f"投稿成功！記事ID：{result['id']}")
