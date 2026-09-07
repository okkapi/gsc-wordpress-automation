#!/bin/bash
# 毎週月曜朝に GSC レポートを生成してファイル保存する。
# crontab から実行される想定:
#   0 8 * * 1 /path/to/src/gsc_weekly_report.sh
#
# cron は対話シェルと作業ディレクトリ・環境変数が異なるため、
# スクリプト自身の位置と python の絶対パスを明示している。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export GSC_HOME="${GSC_HOME:-$SCRIPT_DIR}"
PYTHON="${PYTHON:-/usr/bin/python3}"

cd "$GSC_HOME"

DATE=$(date +%Y-%m-%d)
LOG_DIR="$GSC_HOME/gsc_reports"
mkdir -p "$LOG_DIR"

{
    echo "=========================================="
    echo " GSC週次レポート $(date +'%Y-%m-%d %H:%M')"
    echo "=========================================="
    "$PYTHON" "$SCRIPT_DIR/gsc_report.py" --top 30
    echo ""
    "$PYTHON" "$SCRIPT_DIR/gsc_report.py" --weekly
    echo ""
    "$PYTHON" "$SCRIPT_DIR/gsc_report.py" --rewrite-target
    echo ""
    echo "=== 記事ネタ候補（GSC実データ抽出） ==="
    "$PYTHON" "$SCRIPT_DIR/gsc_topic_extract.py"
} > "$LOG_DIR/${DATE}.txt" 2>&1

# 完了通知（macOS のみ。他環境では静かにスキップ）
if command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"GSC週次レポートを生成しました: $LOG_DIR/${DATE}.txt\" with title \"GSC Weekly Report\""
fi
