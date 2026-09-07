#!/usr/bin/env python3
"""
毎日3件のAI関連記事を自動生成・公開するスクリプト
crontabから呼び出される想定
"""
import subprocess
import sys
import os
import anthropic
from dotenv import load_dotenv
from datetime import date

APP_HOME = os.environ.get("APP_HOME", os.path.dirname(os.path.abspath(__file__)))

ENV_PATH = os.path.join(APP_HOME, ".env")
load_dotenv(ENV_PATH, override=True)

GENERATE_SCRIPT = os.environ.get(
    "GENERATE_SCRIPT",
    os.path.expanduser("~/.claude/skills/wp-blog-writer/scripts/generate_and_post.py"),
)
LOG_PATH = os.path.join(APP_HOME, "daily_articles.log")


def suggest_topics(client: anthropic.Anthropic) -> list[str]:
    today = date.today().strftime("%Y年%m月%d日")
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": f"""今日（{today}）のAI関連ブログ記事のテーマを3つ考えてください。

【条件】
- 初心者〜中級者向けの読者を想定
- 実用的・トレンド性があるテーマ
- 互いに重複しないテーマ
- 日本語で具体的に（例：「ChatGPTで議事録を自動作成する方法」）

テーマのみを番号付きで3行で出力してください。説明不要。
1.
2.
3. """
        }]
    )
    lines = response.content[0].text.strip().splitlines()
    topics = []
    for line in lines:
        line = line.strip()
        if line and line[0].isdigit():
            topic = line.split(".", 1)[-1].strip()
            if topic:
                topics.append(topic)
    return topics[:3]


def log(message: str) -> None:
    timestamp = date.today().isoformat()
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(message)


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log("エラー：ANTHROPIC_API_KEYが設定されていません")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    log("=== 本日の記事生成開始 ===")
    log("テーマを生成中...")
    topics = suggest_topics(client)

    if len(topics) < 3:
        log(f"テーマ生成に失敗しました（取得数: {len(topics)}）")
        sys.exit(1)

    for i, topic in enumerate(topics, 1):
        log(f"\n--- 記事 {i}/3: {topic} ---")
        result = subprocess.run(
            [sys.executable, GENERATE_SCRIPT, "--theme", topic],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                log(line)
        else:
            log(f"エラー発生：{result.stderr[:200]}")

    log("\n=== 本日の記事生成完了 ===\n")


if __name__ == "__main__":
    main()
