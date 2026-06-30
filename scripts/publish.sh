#!/usr/bin/env bash
# Loop News 发布:提交 docs/ 与数据,推到 GitHub,Pages 自动上线。
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

URL=$(grep -E '^\s*url:' config/loop.yaml | head -1 | sed -E 's/.*url:\s*"?([^"]*)"?.*/\1/')
echo "[publish] 已推送。站点:${URL:-https://reposkeeper.github.io/loop-news/}"
