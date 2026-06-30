#!/usr/bin/env bash
# 安装/更新 X(Twitter)MCP server(Infatoshi/x-mcp)到 vendor/x-mcp。
# 第三方开源 MCP;凭证不在此处,见 .env(不入库)。任何 agent 首次用前跑一次。
set -euo pipefail
cd "$(dirname "$0")/.."

DIR="vendor/x-mcp"
REPO="https://github.com/Infatoshi/x-mcp.git"

if [ -d "$DIR/.git" ]; then
  echo "[setup-mcp] 更新已有 $DIR"
  git -C "$DIR" pull --ff-only
else
  echo "[setup-mcp] 克隆 $REPO → $DIR"
  git clone --depth 1 "$REPO" "$DIR"
fi

echo "[setup-mcp] 安装依赖并构建…"
( cd "$DIR" && npm install && npm run build )

# 把项目根 .env(凭证)同步到 server 的 dotenv 路径(vendor 不入库)。server 用 vendor/x-mcp/.env 读凭证。
if [ -f .env ]; then cp .env "$DIR/.env" && echo "[setup-mcp] 已同步 .env → $DIR/.env"; else echo "[setup-mcp] 提醒:还没有根 .env,先 cp .env.example .env 并填值"; fi

if [ -f "$DIR/dist/index.js" ]; then
  echo "[setup-mcp] ✅ 完成,产物:$DIR/dist/index.js"
else
  echo "[setup-mcp] ⚠️ 未找到 dist/index.js,请检查该仓库的 build 输出路径,并据此调整 .mcp.json"
fi
echo "[setup-mcp] 下一步:cp .env.example .env;填 3 个真实 key(X_API_KEY / X_API_SECRET / X_BEARER_TOKEN),"
echo "[setup-mcp]            X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET 只读可留占位(server 启动要求非空,读取不用)。"
