#!/usr/bin/env bash
# 生成 / 登记一个访问令牌,并同步到 Cloudflare Pages(供 functions/_middleware.js 校验)。
# 用法:  bash scripts/share-token.sh <名字> [--owner]
#   <名字>   给谁用(便于日后吊销识别)
#   --owner  标记为站长令牌(解锁全局反馈按钮;并把该 token 同步给反馈 Worker 校验)
# 吊销:编辑 config/share_tokens.json 删掉该条,再重跑本脚本(任意名字)同步即可。
set -euo pipefail
cd "$(dirname "$0")/.."

NAME="${1:?用法: bash scripts/share-token.sh <名字> [--owner]}"
OWNER="false"; [ "${2:-}" = "--owner" ] && OWNER="true"
FILE="config/share_tokens.json"
[ -f "$FILE" ] || echo '{}' > "$FILE"

TOKEN="lnk_$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"

python3 - "$FILE" "$TOKEN" "$NAME" "$OWNER" <<'PY'
import json, sys
f, tok, name, owner = sys.argv[1:5]
d = json.load(open(f, encoding="utf-8"))
d[tok] = {"name": name, "owner": owner == "true"}
json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY

echo "✅ 已登记:$NAME  (owner=$OWNER)"
echo "🔗 分享链接: https://news.xdzq.org/?token=$TOKEN"
echo

# 同步全部有效令牌到 Pages 环境变量(中间件读它校验)
VALUE=$(python3 -c "import json;d=json.load(open('$FILE'));print(json.dumps({k:v for k,v in d.items() if not k.startswith('_')},ensure_ascii=False))")
echo "→ 同步 SHARE_TOKENS 到 Pages(门校验)…"
printf '%s' "$VALUE" | npx --yes wrangler pages secret put SHARE_TOKENS --project-name loop-news
echo "→ 同步 SHARE_TOKENS 到反馈 Worker(收藏/关注校验)…"
printf '%s' "$VALUE" | npx --yes wrangler secret put SHARE_TOKENS

# 站长令牌额外同步给反馈 Worker(校验"全局提问"只接受 owner)
if [ "$OWNER" = "true" ]; then
  echo "→ 同步 OWNER_TOKEN 到反馈 Worker…"
  printf '%s' "$TOKEN" | npx --yes wrangler secret put OWNER_TOKEN
fi
echo "完成。"
