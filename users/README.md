# users/ — ③ Agent 自进化环境(千人千面,每人一份)

> SP2 相位 2a 的地基:**一切皆文件,Agent = 读文件 → 想 → 写文件;千人千面 = 每人一份可进化的环境文件夹,而不是每人一段代码。**
> 权威设计见 [`specs/2026-07-01-personalization-evolution-design.md`](../specs/2026-07-01-personalization-evolution-design.md) §5–§7。这里是**离线/本地(git 侧)**部分,**不经灰度**。

## 目录约定:base ⊕ 稀疏 overlay

```
users/
├── _base/                 # base = owner 底座的可分叉表达(fork 源)= 全体新用户的默认起点
│   ├── agent.md      (a)  # 个人策展 agent 的人设/镜头/可改哪些文件/克制↔创新边界
│   ├── spec.md       (b1) # 个人筛/排/强调/折叠规范(对 synthesize 的个人补充)
│   ├── rubric.md     (b2) # 个人 8 维评价口径(承 prompts/scoring.md;真实分用户不可见)
│   ├── goals.md      (c1) # 个人北极星(承 GOALS.md:对这个人而言什么是非显然洞察)
│   ├── loop.md       (c2) # 个人进化循环六要素:目标/信号/执行器/驱动/护栏/节律
│   └── profile.json       # 空基线画像(= 新用户 ≡ owner 页)
└── <user_id>/             # 一个用户的 overlay(稀疏,只存相对 base 有分叉的文件)
    ├── (agent.md/spec.md/rubric.md/goals.md/profile.json …只在分叉时才出现)
    ├── changelog.md       # 个人进化留痕(每轮改了什么/为什么/如何回滚),base 无、overlay 独有
    └── scores.jsonl       # 个人 8 维分时间序列,base 无、overlay 独有
```

## 有效环境 = base 文件级 merge overlay
- **有效环境 = `_base/` 的文件,被 `<user_id>/` 里同名文件逐个覆盖**(文件级 merge,不是行级 diff——足够简单)。
- **新用户 overlay ≈ 空** → 有效环境 ≡ `_base` ≡ owner 底座 → 页面 ≡ 现状 AI 向。开始反馈后,进化循环**只写发生分叉的那个文件**(通常就是 `profile.json` + `agent.md` 里一句「你的镜头」+ `rubric.md` 几个权重微调)。
- 稀疏 overlay 一次性解决四件事:①存储极小(每用户几 KB);②**base 升级自动下渗**(owner 改了某 base 文件,所有没覆盖它的用户自动受益);③**「重置我」= 删 overlay**;④回滚 = 恢复 overlay 上一版本。

## 怎么物化 / 写回:`scripts/env-sync.sh`
把「散落在 base+overlay 的文件」物化成 runner 眼里一个普通文件夹,跑完稀疏写回:

```
scripts/env-sync.sh pull  <user_id>          # _base ⊕ <user_id> → runtime/users/<id>/(文件级 merge)
scripts/env-sync.sh push  <user_id>          # runtime 里相对 base 有分叉的文件 → 稀疏写回 users/<id>/
scripts/env-sync.sh diff  <user_id>          # 列出该用户相对 base 分叉了哪些文件
scripts/env-sync.sh reset <user_id> [file]   # 删 overlay(整体或某文件)→ 回到 base
```

- `runtime/`(物化工作目录)**不入库**(见 `.gitignore`),是一次性可重建的副本。
- **本目录 = 本地 git 版**:overlay 存 git 的 `users/<id>/`。生产版把 overlay 存 R2、`profile.json` 热副本进 KV、分数进 D1,由**无状态 runner** 拉取/写回(§6/§7);逻辑相同,只换存储。这些**云侧同步**在 `env-sync.sh` 的 `push` 里留了 TODO 注释,由 runner 在有 wrangler 凭据时做。

## 两条更新通道(都只写 `profile.json`,热路径只读它)
- **通道 A(热·确定性·Workers·每次反馈)**:👍👎✓关注屏蔽停留 → 规则微调 `profile.json` 权重 → 写 KV+R2。无 LLM、即时、稳。**属 ① 代码层**(`worker/feedback-worker.js`),不在本目录。
- **通道 B(冷·LLM·runner·每日/活跃时)**:读【有效环境 prose + 累积反馈 + 当前 profile】→ 小 LLM 精修画像叙事/权重 → 确定性并进 `profile.json` + 写 `changelog.md`。见 [`.claude/skills/ln-evolve-lite/SKILL.md`](../.claude/skills/ln-evolve-lite/SKILL.md)。

## 隔离不变量(硬红线)
**谁的反馈都只改自己 overlay**:个人进化不改他人 overlay、不改 ② 共享语料、不改 owner 全局 base(`prompts/*.md`/`config/*.yaml`/`GOALS.md`/`prompts/scoring.md`);全局 `ln-evolve` 也不改任何已分叉 overlay。个人进化**只消化该用户自己的反馈**。真实评分框架用户不可见(§8.5),用户端只见翻译版。
