#!/usr/bin/env bash
# env-sync.sh — ③ Agent 自进化环境的物化工具(SP2 相位 2a · 本地 git 版)
# 依据:specs/2026-07-01-personalization-evolution-design.md §5(base⊕稀疏overlay)、§7(pull/push/diff/reset)。
#
# 一切皆文件:每个用户一套环境 = users/_base/*(fork 源)⊕ users/<id>/*(稀疏 overlay,只存不同的)。
# 有效环境 = base 的文件,被 overlay 里同名文件逐个覆盖(文件级 merge,不是行级 diff)。
# 本工具把「散落在 git 里的 base+overlay」物化成 runner 眼里一个普通文件夹 runtime/users/<id>/,
# 跑完把「相对 base 有分叉」的文件稀疏写回 users/<id>/。
#
# 【本地 git 版】:overlay 存 git 的 users/<id>/。生产版 overlay 存 R2、由无状态 runner 拉取(§6),
# 逻辑相同、只把存储从 git 换成 R2。env-sync 只管 git 侧文件物化;云侧同步见 push 的 TODO。
set -euo pipefail
cd "$(dirname "$0")/.."

BASE_DIR="users/_base"

cmd="${1:-}"; uid="${2:-}"; file="${3:-}"

usage() {
  cat <<'EOF'
env-sync.sh — ③ Agent 环境物化(本地 git 版;base ⊕ 稀疏 overlay)
用法:
  scripts/env-sync.sh pull  <user_id>          # base ⊕ overlay → runtime/users/<id>/(文件级 merge)
  scripts/env-sync.sh push  <user_id>          # runtime 里相对 base 有分叉的文件 → 稀疏写回 users/<id>/
  scripts/env-sync.sh diff  <user_id>          # 列出该用户相对 base 分叉了哪些文件(= overlay 内容)
  scripts/env-sync.sh reset <user_id> [file]   # 删 overlay(整体或某文件)→ 回到 base
说明:base = users/_base/(fork 源);overlay = users/<id>/(稀疏,只存不同的);runtime/ 不入库。
      profile.json 也走同一套(base 的 profile = 空基线)。
EOF
}

require_uid() {
  if [ -z "$uid" ]; then echo "✗ 缺 <user_id>"; usage; exit 2; fi
  case "$uid" in
    _*|.*|*/*) echo "✗ 非法 user_id: '$uid'(不得以 _/. 开头或含 /)"; exit 2;;
  esac
  [ -d "$BASE_DIR" ] || { echo "✗ 缺 base 目录 $BASE_DIR"; exit 1; }
}

cmd_pull() {
  require_uid
  local overlay="users/$uid" rt="runtime/users/$uid"
  rm -rf "$rt"; mkdir -p "$rt"
  # 1) base 全量物化
  for f in "$BASE_DIR"/*; do
    [ -f "$f" ] || continue
    cp "$f" "$rt/"
  done
  # 2) overlay 覆盖同名(文件级 merge)
  if [ -d "$overlay" ]; then
    for f in "$overlay"/*; do
      [ -f "$f" ] || continue
      cp "$f" "$rt/"
    done
  fi
  echo "✓ env pull: base ⊕ overlay 物化 → $rt/"
  ls -1 "$rt" | sed 's/^/    /'
}

cmd_push() {
  require_uid
  local overlay="users/$uid" rt="runtime/users/$uid"
  [ -d "$rt" ] || { echo "✗ 无 runtime:$rt(先 env pull)"; exit 1; }
  mkdir -p "$overlay"
  local wrote=0 cleared=0
  for f in "$rt"/*; do
    [ -f "$f" ] || continue
    local name base_f; name="$(basename "$f")"; base_f="$BASE_DIR/$name"
    if [ -f "$base_f" ] && cmp -s "$f" "$base_f"; then
      # 与 base 相同 → 不该留 overlay(保持稀疏);清掉旧 overlay
      if [ -f "$overlay/$name" ]; then rm -f "$overlay/$name"; echo "    = $name(回到 base,清除 overlay)"; cleared=$((cleared+1)); fi
    else
      cp "$f" "$overlay/$name"; echo "    ≠ $name(分叉,写回 overlay)"; wrote=$((wrote+1))
    fi
  done
  rmdir "$overlay" 2>/dev/null || true   # overlay 空了(纯 base 用户)→ 不留空壳
  echo "✓ env push: 写回 $wrote 个分叉文件、清除 $cleared 个已回归文件 → $overlay/"
  # TODO(runner,需 wrangler 凭据 —— env-sync 本地版不做,由无状态 runner 在有云凭据时执行):
  #   1) prose/overlay → R2  env/users/$uid/*(R2 versioning 留痕、可回滚)
  #   2) profile.json  → 结构化镜像进 D1(user_profile,§9 可选表)+ 刷新 KV 热副本(重排热路径每请求读一次)
  #   3) scores.jsonl  → D1 user_scores(owner 侧趋势查询)
  # 以上属 ① 代码层/② 云存储的职责;env-sync(本地 git 版)只负责 git 侧 users/<id>/ 文件。
}

cmd_diff() {
  require_uid
  local overlay="users/$uid"
  echo "# $uid 相对 base($BASE_DIR)的分叉(= overlay 内容):"
  if [ ! -d "$overlay" ] || [ -z "$(ls -A "$overlay" 2>/dev/null)" ]; then
    echo "    (空 overlay → 有效环境 ≡ base ≡ owner 底座;此用户 = 新用户)"
  else
    for f in "$overlay"/*; do
      [ -f "$f" ] || continue
      local name base_f; name="$(basename "$f")"; base_f="$BASE_DIR/$name"
      if [ ! -f "$base_f" ]; then echo "    ＋ $name(base 无此文件,overlay 独有,如 changelog.md / scores.jsonl)"
      elif cmp -s "$f" "$base_f"; then echo "    = $name(与 base 相同;可 env reset $uid $name 清除)"
      else echo "    ≠ $name(相对 base 分叉)"; fi
    done
  fi
  echo "# 继承 base(未被 overlay 覆盖):"
  for f in "$BASE_DIR"/*; do
    [ -f "$f" ] || continue
    local name; name="$(basename "$f")"
    [ -f "$overlay/$name" ] 2>/dev/null || echo "    · $name"
  done
}

cmd_reset() {
  require_uid
  local overlay="users/$uid"
  if [ -n "$file" ]; then
    if [ -f "$overlay/$file" ]; then rm -f "$overlay/$file"; echo "✓ env reset: 删 overlay $overlay/$file → 该文件回到 base"
    else echo "· 无 overlay 文件 $overlay/$file(本就继承 base,无需 reset)"; fi
    rmdir "$overlay" 2>/dev/null || true
  else
    if [ -d "$overlay" ]; then rm -rf "$overlay"; echo "✓ env reset: 删整个 overlay $overlay/ → 完全回到 base(= 新用户)"
    else echo "· 无 overlay:$overlay(本就 ≡ base)"; fi
  fi
  echo "  提示:runtime/ 是物化副本;重新 scripts/env-sync.sh pull $uid 即刷新。"
}

case "$cmd" in
  pull)  cmd_pull;;
  push)  cmd_push;;
  diff)  cmd_diff;;
  reset) cmd_reset;;
  ""|-h|--help|help) usage;;
  *) echo "✗ 未知子命令: '$cmd'"; usage; exit 2;;
esac
