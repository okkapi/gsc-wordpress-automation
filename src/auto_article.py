import os
import anthropic
from dotenv import load_dotenv
from wp_post import post_article

load_dotenv(override=True)

PROMPT = """
あなたはAIジャンルの人気ブロガーです。
以下の条件でブログ記事を日本語で書いてください。

【テーマ】Claude Codeの使い方・初心者向け解説
【文字数】1,500〜2,000文字
【構成】
1. 導入（読者の悩みに共感）
2. 本文（わかりやすい解説）
3. まとめ（行動を促す）

【注意事項】
- 冗長な表現は削り、テンポよく読める文体にする
- 親しみやすい表現を使う（「〜ですよね」「〜しましょう」など）
- 専門用語は噛み砕いて誰でもわかるように説明する
- HTML形式で出力する（<h2>、<p>、<ul>、<li> タグを使う）
- タイトルは含めず、本文のみ出力する

記事の本文のみを出力してください。前置きや説明は不要です。
"""

TITLE = "Claude Codeって何？初心者でも今日からできる使い方ガイド"


def generate_article() -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": PROMPT}],
    )
    return response.content[0].text


if __name__ == "__main__":
    print("記事を生成中...")
    content = generate_article()
    print(f"生成完了（{len(content)}文字）\n投稿中...")

    result = post_article(TITLE, content)
    print(f"投稿成功！記事ID：{result['id']}")
    print(f"編集URL：{result['link']}")
