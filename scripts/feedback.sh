#!/usr/bin/env bash
# 列出待消化的人类反馈,供 ln-evolve 读取。
# 来源:① data/feedback.jsonl(反馈服务器写入的弹窗反馈:赞/踩/采用 + 常用词 + 文字)
#       ② 本地 feedback.md(自然语言随手记)
set -euo pipefail
cd "$(dirname "$0")/.."

echo "===== 弹窗反馈 data/feedback.jsonl ====="
if [ -f data/feedback.jsonl ]; then
  python3 - <<'PY'
import json, collections
rows = [json.loads(l) for l in open("data/feedback.jsonl", encoding="utf-8") if l.strip()]
print(f"共 {len(rows)} 条 | 分布: {dict(collections.Counter(r.get('action') for r in rows))}")
tagc = collections.Counter(t for r in rows for t in r.get("tags", []))
if tagc:
    print("高频常用词:", tagc.most_common(10))
itemc = collections.Counter(r.get("item_id") for r in rows if r.get("action") == "adopt")
if itemc:
    print("被『采用』最多的条目:", itemc.most_common(5))
print("--- 明细(最近 30 条)---")
for r in rows[-30:]:
    print(f"[{r.get('action')}] {r.get('item_id','')} | {r.get('date','')} | tags={r.get('tags',[])} | {r.get('text','')}")
PY
else
  echo "(暂无;反馈服务器尚未收到提交,或本地未拉取)"
fi

echo
echo "===== 本地反馈 feedback.md ====="
if [ -f feedback.md ]; then cat feedback.md; else echo "(无 feedback.md)"; fi
