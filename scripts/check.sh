#!/usr/bin/env bash
# Loop News 变更落地自检 —— 规范见 RUNBOOK.md「变更落地契约」。
# 每次进化/功能改动后必跑(git pre-commit 已自动调用)。硬检查失败 → 退出 1(拦住提交)。
# 用途:确保改动确实落进了【代码】或【skill/提示词/文档】,且系统自洽、进化有记录。
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0

echo "▶ 1. 编译自洽(输出到临时目录,不动 docs/)"
TMP=$(mktemp -d)
if LN_DOCS_DIR="$TMP" python3 web/compile.py >/tmp/ln_compile.log 2>&1; then
  if grep -q '{{' "$TMP/index.html" 2>/dev/null; then echo "  ✗ 编译输出残留未替换 token"; fail=1; else echo "  ✓ compile 通过、无残留 token"; fi
else
  echo "  ✗ web/compile.py 失败:$(tail -1 /tmp/ln_compile.log)"; fail=1
fi
rm -rf "$TMP"

echo "▶ 2. 结构自洽(JSON / skill / 引用 / 进化日志)"
python3 - <<'PY' || fail=1
import json, glob, os, re, sys
bad = []
for p in glob.glob("data/**/*.json", recursive=True) + glob.glob("config/*.json") + glob.glob("state/*.json"):
    try: json.load(open(p, encoding="utf-8"))
    except Exception as e: bad.append(f"JSON 损坏 {p}: {e}")
for sk in glob.glob(".claude/skills/*/SKILL.md"):
    t = open(sk, encoding="utf-8").read()
    if "name:" not in t or "description:" not in t: bad.append(f"skill 缺 frontmatter: {sk}")
# 引用完整性:文档/skill 里点名的 prompts/scripts/worker/functions 必须真实存在
refs = set()
for f in glob.glob(".claude/skills/*/SKILL.md") + ["RUNBOOK.md", "AGENTS.md", "CLAUDE.md", "GOALS.md"]:
    if os.path.exists(f):
        refs |= set(re.findall(r'(prompts/[\w.\-]+\.md|scripts/[\w.\-]+\.sh|web/compile\.py|server/[\w.\-]+\.py|worker/[\w.\-]+\.js|functions/[\w.\-]+\.js|GOALS\.md)', open(f, encoding="utf-8").read()))
for r in sorted(refs):
    if not os.path.exists(r): bad.append(f"引用了不存在的文件: {r}")
# 进化必留痕:metrics 里每条 evolve 的日期都要能在 CHANGELOG.md 找到
try:
    m = json.load(open("state/metrics.json", encoding="utf-8"))
    cl = open("prompts/CHANGELOG.md", encoding="utf-8").read()
    for r in (m if isinstance(m, list) else []):
        if r.get("type") == "evolve":
            mt = re.search(r"\d{4}-\d{2}-\d{2}", (r.get("run", "") + " " + r.get("changelog_ref", "")))
            if mt and mt.group(0) not in cl:
                bad.append(f"进化记录 {mt.group(0)} 未写入 prompts/CHANGELOG.md(变更须落地留痕)")
except Exception as e:
    bad.append(f"metrics/CHANGELOG 检查失败: {e}")
for b in bad: print("  ✗ " + b)
if not bad: print("  ✓ JSON / skill frontmatter / 文件引用 / 进化留痕 自洽")
sys.exit(1 if bad else 0)
PY

echo "▶ 3. 落地提醒(改动须进 代码或 skill;别只改了工作区没纳入提交)"
UNSTAGED=$(git diff --name-only -- web server worker functions scripts config prompts .claude GOALS.md RUNBOOK.md AGENTS.md CLAUDE.md 2>/dev/null)
UNTRACKED=$(git ls-files --others --exclude-standard -- web server worker functions scripts config prompts .claude 2>/dev/null)
if [ -n "$UNSTAGED$UNTRACKED" ]; then
  echo "  ⚠ 以下代码/skill 改动未纳入本次提交(规范:进化/功能改动须落地并提交):"
  printf '%s\n%s\n' "$UNSTAGED" "$UNTRACKED" | grep . | sed 's/^/      /'
else
  echo "  ✓ 代码/skill 改动均已纳入提交"
fi

echo
if [ "$fail" = 0 ]; then echo "✅ 变更落地自检通过"; else echo "❌ 自检未通过(见上 ✗)。修复后再提交。"; fi
exit $fail
