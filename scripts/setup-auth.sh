#!/usr/bin/env bash
# 一次性:账号体系 owner 引导。apply D1 schema(远端)+ 播种 owner 用户。
# 前置(人工,只需一次,见 CLOUDFLARE.md「账号体系」):
#   1) npx wrangler d1 create loop-news-db  → 把 database_id 填进 wrangler.toml [[d1_databases]]
#   2) npx wrangler kv namespace create SESSIONS → 把 id 填进 wrangler.toml [[kv_namespaces]]
#   3) npx wrangler secret put RESEND_API_KEY
#   4) Cloudflare 控制台把 KV 命名空间 SESSIONS 绑定到 Pages 项目(functions/_middleware.js 要用)
# 本脚本只做:apply schema + 播种 owner。需先 npx wrangler login。
set -euo pipefail
cd "$(dirname "$0")/.."

: "${OWNER_EMAIL:?请先 export OWNER_EMAIL=你的邮箱}"

echo "[setup-auth] 1/2 apply D1 schema(远端,幂等)"
npx wrangler d1 execute loop-news-db --remote --file worker/schema.sql

echo "[setup-auth] 2/2 播种 owner: $OWNER_EMAIL"
npx wrangler d1 execute loop-news-db --remote --command \
  "INSERT OR IGNORE INTO users (email,name,role,status,created_at) VALUES ('$OWNER_EMAIL','站长','owner','active','$(date -u +%Y-%m-%dT%H:%M:%SZ)')"

echo "[setup-auth] 完成。别忘了(若尚未做):"
echo "  - npx wrangler d1 create loop-news-db 与 npx wrangler kv namespace create SESSIONS 的真实 id 已填进 wrangler.toml(须先于本脚本完成,否则上面两步会失败)"
echo "  - npx wrangler secret put RESEND_API_KEY(发验证码邮件)"
echo "  - Cloudflare 控制台把 KV 命名空间 SESSIONS 绑定到 Pages 项目(网站门禁 functions/_middleware.js 依赖它)"
