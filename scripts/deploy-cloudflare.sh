#!/usr/bin/env bash
# 一键部署到 Cloudflare:静态站 → Pages;反馈 API → Worker;常用词 → R2。
# 前置(只需一次):见 CLOUDFLARE.md(wrangler login、创建 R2 桶、创建 Pages 项目、接自定义域)。
set -euo pipefail
cd "$(dirname "$0")/.."

PAGES_PROJECT="${CF_PAGES_PROJECT:-loop-news}"
R2_BUCKET="${CF_R2_BUCKET:-loop-news}"

echo "[deploy] 1/5 编译静态站 → docs/"
python3 web/compile.py

echo "[deploy] 2/5 部署 Pages(静态站)"
npx wrangler pages deploy docs --project-name="$PAGES_PROJECT"

echo "[deploy] 3/5 同步常用词到 R2(弹窗 chips 数据源)"
npx wrangler r2 object put "$R2_BUCKET/config/feedback_tags.json" --file config/feedback_tags.json --content-type application/json --remote

echo "[deploy] 4/5 部署 Worker(反馈 API)"
npx wrangler deploy

echo "[deploy] 5/5 部署 Worker(分享出图;依赖 workers-og,缺则先 npm install)"
[ -d node_modules/workers-og ] || npm install
npx wrangler deploy -c wrangler.share.toml

echo "[deploy] 完成。别忘了把 config/loop.yaml 的 feedback.api_url / share_api_url 设为 Worker 的公网地址。"
