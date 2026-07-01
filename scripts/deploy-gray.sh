#!/usr/bin/env bash
# 部署【灰度(canary)】:与生产同一后端(KV/D1/R2、cookie、用户、会话全共享)、另一套代码,挂 gray-*.xdzq.org。
# 被灰度的客户用真实账号/数据在候选新代码上体验。首次前置见 GRAY.md(建 gray Pages 项目、绑共享 KV、custom domains、gray worker secret)。
set -euo pipefail
cd "$(dirname "$0")/.."

GRAY_PAGES="${CF_GRAY_PAGES:-loop-news-gray}"
FEEDBACK_API="${GRAY_FEEDBACK_API:-https://gray-feedback.xdzq.org}"
SHARE_API="${GRAY_SHARE_API:-https://gray-share.xdzq.org/share}"

echo "[gray] 1/4 构建灰度站(前端 API 指向 gray-*)→ build/gray/(不动 docs/)"
LN_DOCS_DIR=build/gray LN_FEEDBACK_API="$FEEDBACK_API" LN_SHARE_API="$SHARE_API" python3 web/compile.py

echo "[gray] 2/4 部署 Pages(灰度站)→ 项目 $GRAY_PAGES(functions/ 中间件随之部署)"
npx wrangler pages deploy build/gray --project-name="$GRAY_PAGES"

echo "[gray] 3/4 部署灰度反馈 Worker(--env gray;共享 prod KV/D1/R2,CORS=gray-news)"
npx wrangler deploy --env gray

echo "[gray] 4/4 部署灰度分享 Worker(--env gray)"
[ -d node_modules/workers-og ] || npm install
npx wrangler deploy -c wrangler.share.toml --env gray

echo "[gray] 完成。灰度站 https://gray-news.xdzq.org —— 与生产【共享登录/数据】,跑候选代码。"
echo "[gray] 首次务必(见 GRAY.md):控制台把【共享】KV(SESSIONS)绑到 $GRAY_PAGES、设其 env SITE_API=$FEEDBACK_API;"
echo "[gray]        并 npx wrangler secret put RESEND_API_KEY --env gray(灰度发真验证码)。"
