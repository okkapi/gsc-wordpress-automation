#!/usr/bin/env python3
"""古い記事を自動リライト・公開更新するスクリプト

使い方:
    python3 refresh_article.py --id 67           # 指定IDをリライト
    python3 refresh_article.py --oldest 1        # 最終更新が最も古い1件をリライト
    python3 refresh_article.py --oldest 3        # 古い順に3件
"""
import os
import re
import sys
import argparse
import requests
import xmlrpc.client
import anthropic
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from datetime import datetime

# 設定・ログの置き場は APP_HOME で差し替え可能。既定はこのスクリプトの階層。
APP_HOME = os.environ.get("APP_HOME", os.path.dirname(os.path.abspath(__file__)))

ENV_PATH = os.path.join(APP_HOME, ".env")
load_dotenv(ENV_PATH, override=True)

WP_URL = os.getenv("WP_URL")
WP_USER = os.getenv("WP_USER")
WP_PASSWORD = os.getenv("WP_PASSWORD")
AUTH = HTTPBasicAuth(WP_USER, WP_PASSWORD)
LOG_PATH = os.path.join(APP_HOME, "refresh.log")


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_post(pid):
    r = requests.get(f"{WP_URL}/wp-json/wp/v2/posts/{pid}", params={"context": "edit"}, auth=AUTH)
    r.raise_for_status()
    return r.json()


def list_oldest(n):
    r = requests.get(f"{WP_URL}/wp-json/wp/v2/posts",
                     params={"per_page": 100, "_fields": "id,title,modified", "orderby": "modified", "order": "asc"},
                     auth=AUTH)
    return r.json()[:n]


# ---- 本文クリーンアップ ----
AD_MARKERS = [
    "4B3HQJ+FJ21TE+1JUK+HVNAP", "4B3HQK+HV0XE+2PEO+O4P5D",
    "4B3JAF+EXMG1E+5GDG+NVP2P", "4B3JAF+EXMG1E+5GDG+NWJXT",
    "4B3JAF+FUDAB6+5V86+61Z81", "4B3K2N+77L0J6+50+552T41",
    "4B3K2N+7MGUNM+ONS+TV3PD", "4B3K2N+98TBXU+80W+NTJWX",
]


def strip_extras(html):
    """広告・関連リンク・開示文言・比較表を除去して本文だけを返す"""
    # 開示文言
    html = re.sub(r'<p[^>]*>※本記事にはアフィリエイト広告を利用しています。</p>\s*', '', html)
    # 広告 div
    html = re.sub(r'<div[^>]*>\s*<a href="https://px\.a8\.net[^"]*"[^>]*>.*?</div>', '', html, flags=re.DOTALL)
    # 関連リンクブロック
    html = re.sub(r'<!--RELATED_POSTS-->.*?</div>', '', html, count=1, flags=re.DOTALL)
    # 比較表（h2マーカーから次のh2まで）
    html = re.sub(r'<h2>📊 ひと目でわかる比較表</h2>.*?(?=<h2|\Z)', '', html, count=1, flags=re.DOTALL)
    # 余分な改行
    html = re.sub(r'\n{3,}', '\n\n', html)
    return html.strip()


# ---- Claude呼び出し ----
def refresh_with_claude(title, body, client):
    today = datetime.now().strftime("%Y年%m月")
    prompt = f"""以下のブログ記事をリライトして、最新化・拡充してください。

【記事タイトル】{title}
【現在の日付】{today}

【リライトの方針】
- 既存の構成・流れを尊重しつつ、本文を最新（2026年）の情報に更新する
- 古い年号（2024、2025等）や古いツール名は最新に置き換える
- 「やってみた体験」「具体的な数値」「実例」を追加する
- 新しいh2セクションを1〜2個追加する（読者ニーズに合うもの）
- 文字数は5000〜7000文字を目標
- 一人称は必ず「私」で統一する（僕・俺・自分・わたし は使わない）
- 「：」コロンは見出し（h2/h3）でのみ使い、本文中では使わない。本文中の代替は「⬇️」「✅」「❌」「→」「（）」「・・・」
- 仮名の知人・友人体験談（Aさん・Bさん等）は使わない（冗長化を防ぐ）。実例は「私自身の経験」or「公開データ」で表現
- 親しみやすい口調（「〜よね」「〜ですよね」「あるんですよね」）
- 「〜である」「〜と言える」など教科書調は避ける
- HTML構造（h2・h3・p・ul・li・strong）を維持
- コードブロック記号（```）は絶対に使わない
- 前置き・説明・記号は不要。リライト後の本文HTMLのみを出力

【元の記事本文】
{body}
"""
    full = ""
    messages = [{"role": "user", "content": prompt}]
    for _ in range(3):
        resp = client.messages.create(model="claude-haiku-4-5", max_tokens=8192, messages=messages)
        chunk = resp.content[0].text
        full += chunk
        if resp.stop_reason != "max_tokens":
            break
        # 末尾の閉じ済みブロックまで切って続きを依頼
        candidates = [full.rfind(t) + len(t) for t in ['</p>', '</ul>', '</ol>', '</h2>', '</h3>'] if full.rfind(t) != -1]
        if candidates:
            full = full[:max(candidates)].rstrip()
        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": full},
            {"role": "user", "content": "続きをそのまま自然に出力してください。重複させず、最後まで完結させてください。HTMLのみ、コードブロック記号は使わない。"},
        ]
    text = re.sub(r'^```[\w]*\n?', '', full.strip())
    text = re.sub(r'\n?```$', '', text.strip())
    text = text.strip()
    # コロン除去（HTMLタグ・Q1：等のラベルは保護）
    placeholders = []
    def _mask(m):
        placeholders.append(m.group(0))
        return f"\x00{len(placeholders)-1}\x00"
    # h2/h3全体（見出し内）と他のHTMLタグをマスク
    masked = re.sub(r'<h[23]>.*?</h[23]>', _mask, text, flags=re.DOTALL)
    masked = re.sub(r'<[^>]+>', _mask, masked)
    keep_holders = []
    keep_re = re.compile(
        r'((?:Q\d+|A\d+|例\d+|Step\d+|ステップ\d+|ポイント\d+|手順\d+|失敗例\d+|事例\d+|ケース\d+'
        r'|まとめ|結論|終わりに|最後に|はじめに|前提|注意点|補足|余談|本題|解決策|結果)'
        r')([:：])'
    )
    def _keep(m):
        keep_holders.append(m.group(1) + '：')
        return f"\x01{len(keep_holders)-1}\x01"
    masked = keep_re.sub(_keep, masked)
    masked = masked.replace('：', '。')
    masked = re.sub(r'(?<!\d):(?!\d)', '。', masked)
    masked = re.sub(r'。+', '。', masked)
    masked = re.sub(r'\x01(\d+)\x01', lambda m: keep_holders[int(m.group(1))], masked)
    text = re.sub(r'\x00(\d+)\x00', lambda m: placeholders[int(m.group(1))], masked)
    return text


# ---- 広告・関連・開示文言を再構築 ----
NOTICE = '<p style="background:#fff5e6;border-left:4px solid #ff9800;padding:10px 14px;margin-bottom:24px;font-size:0.9em;color:#333;">※本記事にはアフィリエイト広告を利用しています。</p>'

AD_BLOCKS = {
    "top_rect": '''<div style="text-align:center;margin:30px 0;">
<a href="https://px.a8.net/svt/ejp?a8mat=4B3K2N+77L0J6+50+552T41" rel="nofollow">
<img border="0" width="300" height="250" alt="" src="https://www20.a8.net/svt/bgt?aid=260506463436&wid=001&eno=01&mid=s00000000018031086000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=4B3K2N+77L0J6+50+552T41" alt="">
</div>''',
    "1st_h2": '''<div style="text-align:center;margin:30px 0;overflow-x:auto;">
<a href="https://px.a8.net/svt/ejp?a8mat=4B3K2N+98TBXU+80W+NTJWX" rel="nofollow">
<img border="0" width="468" height="60" alt="" src="https://www23.a8.net/svt/bgt?aid=260506463559&wid=001&eno=01&mid=s00000001040004001000&mc=1" style="max-width:100%;height:auto;"></a>
<img border="0" width="1" height="1" src="https://www14.a8.net/0.gif?a8mat=4B3K2N+98TBXU+80W+NTJWX" alt="">
</div>''',
    "lead": '''<div style="text-align:center;margin:30px 0;overflow-x:auto;">
<a href="https://px.a8.net/svt/ejp?a8mat=4B3JAF+FUDAB6+5V86+61Z81" rel="nofollow">
<img border="0" width="728" height="90" alt="" src="https://www25.a8.net/svt/bgt?aid=260505447958&wid=001&eno=01&mid=s00000027375001017000&mc=1" style="max-width:100%;height:auto;"></a>
<img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=4B3JAF+FUDAB6+5V86+61Z81" alt="">
</div>''',
    "mid": '''<div style="text-align:center;margin:30px 0;">
<a href="https://px.a8.net/svt/ejp?a8mat=4B3JAF+EXMG1E+5GDG+NWJXT" rel="nofollow">
<img border="0" width="320" height="50" alt="" src="https://www23.a8.net/svt/bgt?aid=260505447903&wid=001&eno=01&mid=s00000025450004015000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www13.a8.net/0.gif?a8mat=4B3JAF+EXMG1E+5GDG+NWJXT" alt="">
</div>''',
    "3q": '''<div style="text-align:center;margin:30px 0;">
<a href="https://px.a8.net/svt/ejp?a8mat=4B3HQK+HV0XE+2PEO+O4P5D" rel="nofollow">
<img border="0" width="320" height="50" alt="" src="https://www27.a8.net/svt/bgt?aid=260503436030&wid=001&eno=01&mid=s00000012624004053000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www13.a8.net/0.gif?a8mat=4B3HQK+HV0XE+2PEO+O4P5D" alt="">
</div>''',
    "before_summary": '''<div style="text-align:center;margin:30px 0;">
<a href="https://px.a8.net/svt/ejp?a8mat=4B3HQJ+FJ21TE+1JUK+HVNAP" rel="nofollow">
<img border="0" width="320" height="50" alt="" src="https://www23.a8.net/svt/bgt?aid=260503435939&wid=001&eno=01&mid=s00000007238003003000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www13.a8.net/0.gif?a8mat=4B3HQJ+FJ21TE+1JUK+HVNAP" alt="">
</div>''',
    "bottom_lead": '''<div style="text-align:center;margin:30px 0;overflow-x:auto;">
<a href="https://px.a8.net/svt/ejp?a8mat=4B3K2N+7MGUNM+ONS+TV3PD" rel="nofollow">
<img border="0" width="728" height="90" alt="" src="https://www23.a8.net/svt/bgt?aid=260506463461&wid=001&eno=01&mid=s00000003196005016000&mc=1" style="max-width:100%;height:auto;"></a>
<img border="0" width="1" height="1" src="https://www11.a8.net/0.gif?a8mat=4B3K2N+7MGUNM+ONS+TV3PD" alt="">
</div>''',
    "end": '''<div style="text-align:center;margin:30px 0;">
<a href="https://px.a8.net/svt/ejp?a8mat=4B3JAF+EXMG1E+5GDG+NVP2P" rel="nofollow">
<img border="0" width="300" height="250" alt="" src="https://www25.a8.net/svt/bgt?aid=260503436030&wid=001&eno=01&mid=s00000025450004011000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www15.a8.net/0.gif?a8mat=4B3JAF+EXMG1E+5GDG+NVP2P" alt="">
</div>''',
}


def insert_ads(content):
    """generate_and_post.py と同じ流儀で広告を挿入"""
    def insert_at(html, pos, snippet):
        return html[:pos] + snippet + '\n\n' + html[pos:]

    # 末尾h2直前
    h2 = [m.start() for m in re.finditer(r'<h2', content)]
    if h2:
        content = insert_at(content, h2[-1], AD_BLOCKS["before_summary"])
    # 3/4位置
    h2 = [m.start() for m in re.finditer(r'<h2', content)]
    if len(h2) >= 4:
        content = insert_at(content, h2[(len(h2) * 3) // 4], AD_BLOCKS["3q"])
    elif len(h2) >= 2:
        content = insert_at(content, h2[-2], AD_BLOCKS["3q"])
    # 中央
    h2 = [m.start() for m in re.finditer(r'<h2', content)]
    if len(h2) >= 3:
        content = insert_at(content, h2[len(h2) // 2], AD_BLOCKS["mid"])
    # 3番目のh2 (468x60) - 元仕様だと"上の方"に変えたが互換のため省略
    # 1/4位置 (728x90 lead)
    h2 = [m.start() for m in re.finditer(r'<h2', content)]
    if len(h2) >= 2:
        content = insert_at(content, h2[1], AD_BLOCKS["lead"])
    # 1番目h2直前 (468x60)
    h2 = [m.start() for m in re.finditer(r'<h2', content)]
    if h2:
        content = insert_at(content, h2[0], AD_BLOCKS["1st_h2"])

    return NOTICE + '\n\n' + AD_BLOCKS["top_rect"] + '\n\n' + content + '\n\n' + AD_BLOCKS["bottom_lead"] + '\n\n' + AD_BLOCKS["end"]


def append_related(post_id, category_id, tag_ids):
    params = {"per_page": 6, "exclude": post_id, "_fields": "id,title,link,tags",
              "orderby": "date", "order": "desc"}
    if category_id:
        params["categories"] = category_id
    r = requests.get(f"{WP_URL}/wp-json/wp/v2/posts", params=params, auth=AUTH)
    candidates = r.json() if r.status_code == 200 else []
    if tag_ids:
        candidates.sort(key=lambda p: -len(set(p.get("tags", [])) & set(tag_ids)))
    related = candidates[:3]
    if not related:
        return ""
    lis = "\n".join(f'<li><a href="{p["link"]}">{p["title"]["rendered"]}</a></li>' for p in related)
    return f'''<!--RELATED_POSTS-->
<div style="background:#f7f9fc;border-left:4px solid #4a90e2;padding:16px 20px;margin:30px 0;">
<p style="font-weight:bold;margin:0 0 10px;font-size:1.05em;color:#333;">▼ あわせて読みたい関連記事</p>
<ul style="margin:0;padding-left:20px;">
{lis}
</ul>
</div>'''


def update_seo_xmlrpc(post_id, title, content, client):
    prompt = f"""以下のブログ記事に対してSEO設定を生成してください。

【記事タイトル】{title}
【記事冒頭】{content[:800]}

以下の形式で出力してください：
SEOタイトル: （32文字以内）
メタディスクリプション: （120文字前後）
メタキーワード: （5〜8語をカンマ区切り）
"""
    r = client.messages.create(model="claude-haiku-4-5", max_tokens=400, messages=[{"role": "user", "content": prompt}])
    text = r.content[0].text.strip()
    seo = {"seo_title": "", "meta_description": "", "meta_keywords": ""}
    for raw in text.splitlines():
        line = raw.strip().lstrip('*# ').rstrip('*')
        for label, key in [("SEOタイトル", "seo_title"), ("メタディスクリプション", "meta_description"), ("メタキーワード", "meta_keywords")]:
            if line.startswith(label):
                rest = line[len(label):].lstrip(':：*').strip()
                if rest:
                    seo[key] = rest
                break
    if not seo["seo_title"]:
        return
    wp = xmlrpc.client.ServerProxy(f"{WP_URL}/xmlrpc.php")
    wp.wp.editPost(1, WP_USER, WP_PASSWORD, post_id, {
        "custom_fields": [
            {"key": "the_page_seo_title", "value": seo["seo_title"]},
            {"key": "the_page_meta_description", "value": seo["meta_description"]},
            {"key": "the_page_meta_keywords", "value": seo["meta_keywords"]},
        ]
    })


def refresh_one(pid, client):
    log(f"=== ID:{pid} リライト開始 ===")
    p = get_post(pid)
    title = p["title"]["raw"]
    raw_content = p["content"]["raw"]
    category_id = (p.get("categories") or [None])[0]
    tag_ids = p.get("tags") or []

    log(f"  タイトル: {title[:50]}")
    log(f"  元文字数: {len(raw_content)}")

    body = strip_extras(raw_content)
    log(f"  剥がした後: {len(body)}文字")

    refreshed = refresh_with_claude(title, body, client)
    log(f"  リライト後: {len(refreshed)}文字")

    # ファクトチェック
    try:
        import sys as _sys
        _sys.path.insert(0, "/Users/yu-rinnti-/.claude/skills/wp-blog-writer/scripts")
        _sys.path.insert(0, "/home/c6300302/ai_blog")
        from generate_and_post import fact_check_article
        before = len(refreshed)
        refreshed = fact_check_article(title, refreshed, client)
        log(f"  ファクトチェック完了 ({before}→{len(refreshed)})")
    except Exception as e:
        log(f"  ファクトチェック失敗（スキップ）: {e}")

    # 読みやすさ強化
    import sys
    sys.path.insert(0, "/Users/yu-rinnti-/.claude/skills/wp-blog-writer/scripts")
    sys.path.insert(0, "/home/c6300302/ai_blog")
    try:
        from generate_and_post import _ensure_h2_emoji, _highlight_strong, _add_callout_boxes, generate_summary_box
        refreshed = _ensure_h2_emoji(refreshed)
        refreshed = _highlight_strong(refreshed)
        refreshed = _add_callout_boxes(refreshed)
        try:
            summary = generate_summary_box(title, refreshed, client)
            if summary:
                h2m = re.search(r'<h2', refreshed)
                if h2m:
                    refreshed = refreshed[:h2m.start()] + summary + '\n\n' + refreshed[h2m.start():]
        except Exception as e:
            log(f"  サマリーボックス失敗: {e}")
        log("  読みやすさ強化完了")
    except Exception as e:
        log(f"  読みやすさ強化失敗: {e}")

    with_ads = insert_ads(refreshed)
    related_block = append_related(pid, category_id, tag_ids)
    final_content = with_ads + ("\n\n" + related_block if related_block else "")

    requests.post(f"{WP_URL}/wp-json/wp/v2/posts/{pid}", json={"content": final_content}, auth=AUTH).raise_for_status()
    log(f"  本文更新完了 ({len(final_content)}文字)")

    try:
        update_seo_xmlrpc(pid, title, refreshed, client)
        log("  SEO更新完了")
    except Exception as e:
        log(f"  SEO更新失敗: {e}")

    log(f"=== ID:{pid} リライト完了 ===\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, help="リライト対象の記事ID")
    parser.add_argument("--oldest", type=int, default=0, help="最終更新が古い順にN件リライト")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log("エラー: ANTHROPIC_API_KEY未設定")
        sys.exit(1)
    client = anthropic.Anthropic(api_key=api_key)

    targets = []
    if args.id:
        targets.append(args.id)
    elif args.oldest:
        for p in list_oldest(args.oldest):
            targets.append(p["id"])
    else:
        log("--id か --oldest を指定してください")
        sys.exit(1)

    for pid in targets:
        try:
            refresh_one(pid, client)
        except Exception as e:
            log(f"ID:{pid} リライト失敗: {e}")


if __name__ == "__main__":
    main()
