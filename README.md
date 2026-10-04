# GSC × WordPress 運用自動化

自社メディア（WordPress / 月間数百記事規模の運用）のために構築した、
**Google Search Console のデータ収集を定期実行し、記事改善の判断材料を自動で出力する**システムと、
その周辺で使う WordPress 操作ツール群です。

外部から受注した案件ではなく、自分の運用課題を解決するために独力で設計・実装・運用したものです。

---

## 1. 稼働中のシステム — GSC週次レポート自動生成

このリポジトリで**実際に定期実行され、運用が継続している**のはこの1本です。

毎週月曜 8:00 に launchd から起動し、Search Console API から4種類の分析を実行して
1つのテキストレポートに束ね、ファイル保存と OS 通知まで行います。

```mermaid
flowchart LR
    CRON["launchd<br/>毎週月曜 8:00<br/>スリープ時は起動後に補完"] --> SH["gsc_weekly_report.sh"]
    SH --> A["gsc_report.py --top 30<br/>上位クエリ"]
    SH --> B["gsc_report.py --weekly<br/>前週比較"]
    SH --> C["gsc_report.py --rewrite-target<br/>リライト対象抽出"]
    SH --> D["gsc_topic_extract.py<br/>新規記事の候補抽出"]
    A & B & C & D --> OUT["gsc_reports/YYYY-MM-DD.txt"]
    OUT --> NOTIF["macOS 通知"]

    GSC[("Search Console API")] -.OAuth 2.0.-> A
    GSC -.-> B
    GSC -.-> C
    GSC -.-> D
```

### 稼働実績

| 項目 | 内容 |
|---|---|
| 稼働期間 | 2026年5月13日 〜 継続中 |
| レポート出力回数 | 14回（うち無人実行 3回、手動実行 11回） |
| 障害と対応 ① | OAuth リフレッシュトークンの失効を2回検知し、再認証して復旧（2026/6/8・2026/7/10） |
| 障害と対応 ② | **2026/8/17 〜 10/4 の7週間、停止していた。** 原因は後述。launchd へ移行して解決（2026/10/4） |

### 技術的なポイント

- **OAuth 2.0 のトークン管理を自前で実装**
  初回はブラウザで認証フローを通し、以降は `gsc_token.json` に保存したリフレッシュトークンで無人更新。
  `creds.expired and creds.refresh_token` を判定して自動リフレッシュし、失効時のみ再認証フローに落とす。
  無人実行の自動化では、この「認証が切れたときにどう振る舞うか」が実運用上いちばん壊れやすい箇所です。

- **分析ロジックを「次の行動」に変換している**
  単なるデータのダンプではなく、判断に使える形で切り出しています。
  - `--rewrite-target` : 検索順位 30〜100位 = あと一押しで1ページ目に届く記事
  - `gsc_topic_extract.py` : 表示はあるがクリック0のクエリ = 需要はあるのに対応記事がない領域

- **無人実行前提の設計**
  シェルスクリプト側で `cd` と絶対パスの python を明示し、標準出力・標準エラーをまとめてファイルへリダイレクト。
  対話シェルとは環境変数や作業ディレクトリが異なる問題を回避しています。

### 運用して分かったこと — cron から launchd へ移行した経緯

**2026/8/17 から 10/4 までの7週間、このシステムは止まっていました。** 7回分の月曜が丸ごと欠測しています。

原因は macOS における cron の仕様でした。

| | cron | launchd |
|---|---|---|
| 指定時刻にスリープしていたら | **実行時刻を破棄する（後で取り返さない）** | 次回起動時に1回だけ補完実行する |
| 失敗したとき | 出力が捨てられ、痕跡が残らない | `StandardErrorPath` に必ず残る |

このマシンは `pmset` の `sleep` が 1 分に設定されており、月曜 8:00 はほぼ確実にスリープ中でした。
そのうえ cron は何も記録を残さないため、**止まっていること自体に気づけない**状態になっていました。
実際、5月以降に出力された14本のレポートのうち、cron による無人実行は3回だけで、
残りは「最近動いていないな」と気づいたときの手動実行でした。

対処として `launchd/com.example.gsc-weekly.plist` を追加し、以下を設定しています。

- `StartCalendarInterval` による週次起動（スリープ分は起動後に補完実行）
- `StandardOutPath` / `StandardErrorPath` を明示し、失敗が必ずログに残るようにする
- `EnvironmentVariables` で `PATH` / `LANG` / `GSC_HOME` を明示

定期実行の自動化では、動かすこと自体より
**「止まったときに気づける状態を作っておくこと」のほうが重要**だと考えるようになりました。

---

## 2. WordPress 操作ツール群（手動実行）

定期実行はしておらず、必要なときにコマンドで叩くツールです。

| ファイル | 内容 |
|---|---|
| `wp_post.py` | WordPress REST API での投稿。アプリケーションパスワードによる Basic 認証 |
| `post_one_article.py` | 記事を1本生成して投稿。**Mac / 本番サーバの両方で動くパス解決**を実装 |
| `refresh_article.py` | Claude API による既存記事のリライト。`--id` 指定 / `--oldest N` で古い記事から順に処理 |
| `index_request.py` | Google Indexing API へのインデックス申請 |
| `google_suggest.py` | サジェストからのキーワード収集 |

### 環境差分の吸収

`post_one_article.py` では、開発機（Mac）と本番（VPS）でディレクトリ構成が異なる問題に対し、
候補パスを順に評価して最初に存在したものを採用する `_first_existing()` を実装しています。
環境ごとに設定ファイルを分けるより、コード1箇所で完結させる判断をしました。

---

## 3. 自作 WordPress プラグイン

`plugin/cocoon-seo-rest.php` — **本番サイトで有効化して運用したプラグイン**です。

**解決した課題**: Cocoon テーマの SEO メタフィールド（メタタイトル・ディスクリプション・キーワード）は
カスタムフィールドとして保存されるものの REST API に露出しておらず、外部から自動で書き込めませんでした。

**実装**: `register_post_meta()` で3つのメタキーを `show_in_rest => true` として登録。
`auth_callback` に `current_user_can('edit_posts')` を置き、
REST 経由の読み書きに権限チェックを効かせています。

30行ほどのコードですが、「既存テーマの制約を、テーマを改造せずプラグイン側で解決する」という
WordPress 案件で頻出する形の対応です。

---

## 4. 試行して停止したもの

`daily_articles.py` / `auto_article.py` は、記事テーマの提案から生成・投稿までを
1日3件・自動で回す試みです。2026年4月30日から5月25日まで稼働させましたが、
**生成される記事の品質が公開水準に達しなかったため、効果を測定したうえで停止**しました。
現在は定期実行に登録していません。

コードは経緯を残す目的で同梱しています。実運用中のシステムではありません。

---

## セットアップ

```bash
pip install -r requirements.txt
cp .env.example .env      # 値を埋める
```

Search Console API を使うスクリプトは、Google Cloud で OAuth クライアントを作成し
`oauth_client.json` を配置したうえで初回のみブラウザ認証が必要です。

定期実行の登録（macOS / launchd）:

```bash
# パスを書き換えてから配置する
cp launchd/com.example.gsc-weekly.plist ~/Library/LaunchAgents/
plutil -lint ~/Library/LaunchAgents/com.example.gsc-weekly.plist
launchctl load ~/Library/LaunchAgents/com.example.gsc-weekly.plist
launchctl start com.example.gsc-weekly    # 動作確認用の即時実行
```

Linux サーバ等で cron を使う場合は以下。
（macOS では上記の理由からスリープで取りこぼすため推奨しません）

```
0 8 * * 1 /path/to/src/gsc_weekly_report.sh
```

### 認証情報の扱い

APIキー・パスワードの類は**一切コードに書いていません**。
すべて `.env`（`python-dotenv`）または外部の認証 JSON から読み込み、`.gitignore` で除外しています。

---

## 使用技術

Python 3 / Google Search Console API / Google Indexing API / OAuth 2.0 /
Anthropic Claude API / WordPress REST API / PHP（WordPress プラグイン） / launchd / cron / シェルスクリプト
