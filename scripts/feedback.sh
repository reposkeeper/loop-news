#!/usr/bin/env bash
# 列出待消化的人类反馈,供 ln-evolve 读取。
#
# 账号体系上线后(SP1-Core),反馈存 Cloudflare D1(worker/schema.sql 的 feedback 表,按 user_id 隔离),
# 不再是全局 data/feedback.jsonl / 匿名 curl <api>/feedback。
# 只有 owner 角色的反馈驱动全局 prompts/config 进化;普通用户反馈是个人数据,不进本脚本(SP2 千人千面 才消费)。
# owner 本机已 wrangler login,直接查 D1 即可,无需走带 session cookie 的 HTTP 接口。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "===== owner 反馈(D1 feedback,role=owner)====="
npx wrangler d1 execute loop-news-db --remote --command \
  "SELECT action,item_id,date,title,tags,text,ts FROM feedback f JOIN users u ON u.id=f.user_id WHERE u.role='owner' ORDER BY f.ts"

echo
echo "===== 本地反馈 feedback.md(自然语言随手记,若存在)====="
if [ -f feedback.md ]; then cat feedback.md; else echo "(无 feedback.md)"; fi
