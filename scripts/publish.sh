#!/usr/bin/env bash
# Loop News 源码备份:提交全部改动并推到 GitHub(仅源码/历史)。
# 托管在 Cloudflare(站点 Pages + 反馈 Worker),发布/上线用 scripts/deploy-cloudflare.sh,不依赖 GitHub Pages。
set -euo pipefail
cd "$(dirname "$0")/.."

MSG="${1:-publish: $(date +%F)}"

git add -A
if git diff --cached --quiet; then
  echo "[publish] 无改动,跳过提交。"
else
  git commit -m "$MSG"
fi

# 拉取远端避免冲突(首次推送前远端可能没有 main,忽略失败)
git pull --rebase origin main 2>/dev/null || true
git push origin main

echo "[publish] 已推送到 GitHub(源码备份)。托管/上线请用 bash scripts/deploy-cloudflare.sh。"
