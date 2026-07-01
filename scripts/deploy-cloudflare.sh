#!/usr/bin/env bash
# 一键部署到 Cloudflare:静态站 → Pages;反馈 API → Worker;常用词 → R2。
# 前置(只需一次):见 CLOUDFLARE.md(wrangler login、创建 R2 桶、创建 Pages 项目、接自定义域)。
set -euo pipefail
cd "$(dirname "$0")/.."

PAGES_PROJECT="${CF_PAGES_PROJECT:-loop-news}"
R2_BUCKET="${CF_R2_BUCKET:-loop-news}"

echo "[deploy] 1/6 编译静态站 → docs/"
python3 web/compile.py

echo "[deploy] 2/6 部署 Pages(静态站)"
npx wrangler pages deploy docs --project-name="$PAGES_PROJECT"

echo "[deploy] 3/6 同步常用词到 R2(弹窗 chips 数据源)"
npx wrangler r2 object put "$R2_BUCKET/config/feedback_tags.json" --file config/feedback_tags.json --content-type application/json --remote

echo "[deploy] 4/6 应用 D1 schema(幂等;账号体系:用户/活动/反馈/收藏/关注/已读/请求)"
npx wrangler d1 execute loop-news-db --remote --file worker/schema.sql

echo "[deploy] 5/6 部署 Worker(反馈 API + 账号体系 /auth /me)"
npx wrangler deploy

echo "[deploy] 6/6 部署 Worker(分享出图;依赖 workers-og,缺则先 npm install)"
[ -d node_modules/workers-og ] || npm install
npx wrangler deploy -c wrangler.share.toml

echo "[deploy] 完成。别忘了把 config/loop.yaml 的 feedback.api_url / share_api_url 设为 Worker 的公网地址;首次上线还需跑一次 scripts/setup-auth.sh(见 CLOUDFLARE.md「账号体系」)。"
