# 设计:SP2 · 三层分离(代码 / 数据 / Agent 自进化环境)

> 日期:2026-07-01 · 修订:2026-07-02(v2 三层重构)· 状态:已定,进入执行 · 作者:reposkeeper + Claude
> **建在 [SP1 · 账号地基](2026-07-01-user-isolation-auth-design.md) 之上**(账号 / 隔离 / 活动日志已就位)。
>
> v2 把系统重新切成**三层正交部件**:①代码(确定性引擎)②数据(话题为键的新闻)③Agent 自进化环境(千人千面,每人一套文件)。
> 核心范式:**一切皆文件,Agent = 读文件 → 思考 → 写文件**;千人千面 = 每人一份可进化的环境文件夹,而**不是**每人一段代码。

---

## 0. v2 相对 v1 改了什么(为什么重构)

| | v1(旧) | v2(本文) |
|---|---|---|
| 组织方式 | 按功能罗列(画像/重排/评分/话题…混在一起) | 切成**代码 / 数据 / Agent 环境**三层,各自独立演化 |
| 千人千面的本质 | 隐含"per-user 逻辑" | **每人一个环境文件夹**(`agent.md`+规范+评价+目标/驱动),差异是**数据不是代码** |
| Agent 跑在哪 | 未定义 | **无状态 runner**:近期本地 Claude Code,远期同一套 skill 提升为定时云端;热路径永在 Workers |
| 环境怎么拿 | 未定义 | `env-sync`:base(git)⊕ overlay(R2)物化成工作目录,跑完写回 |
| 复杂度 | 偏重 | **确定性引擎 + 边缘极简 + 稀疏 overlay + 无状态**,四条把系统压简 |

保留不变:隔离不变量、话题为键共享、6→8 分与张力矩阵、**§8 评分框架=系统核心用户不可见(硬约束)**、相位 2c→2a→2b。

---

## 1. 核心范式:一切皆文件

现有全局系统**本身就是一个 Agent 自进化环境**:`CLAUDE.md`/`AGENTS.md`(agent 说明)+ `GOALS.md`(北极星)+ `prompts/scoring.md`(评价)+ `prompts/*.md`(规范)+ `prompts/CHANGELOG.md`(进化留痕),`ln-evolve` 读反馈+指标→**改这些文件**→ git 可回滚。

**SP2 = 把这套"环境"从全局一份,变成每人一份**——以 owner 的那份为 base,每个用户在其上叠一层薄薄的 overlay,用自己的反馈进化出自己的形态。

这带来一个统一世界观,消灭所有"per-user 特判代码":
- Agent 对每个用户做的事永远是同一个动作:**把这个用户的环境文件读进来 → 想 → 把改动写回去**。
- 用户之间的差异**只存在于文件内容**(overlay),**不在代码里**。新增一个用户 = 给他一个(初始为空的)文件夹,**不写一行新代码**。

---

## 2. 三层分解总览

```
┌────────────────────────────────────────────────────────────────────────┐
│  ① 代码 CODE — 确定性引擎(全局共享,git 版本化,跑在 Cloudflare)        │
│  认证/会话 · 反馈/关注/活动 API · 个人重排(读 profile,无 LLM)         │
│  · owner 仪表盘 & 用户管理 · 灰度发布 · score.py · compile.py            │
│  特征:无 LLM、确定性、永在线、可单测。 用户之间"一份代码"。            │
└───────────────┬────────────────────────────────────────┬───────────────┘
                │ 读                                       │ 读
┌───────────────▼──────────────────┐   ┌──────────────────▼───────────────┐
│ ② 数据 DATA — 话题为键的新闻       │   │ ③ AGENT 环境 — 千人千面(每人一份)│
│ 采集/汇总按【规范话题】去重共享     │   │ users/<id>/ 环境文件夹:            │
│ D1 索引 · R2 载荷 · KV 热缓存      │   │  agent.md(a)+ 规范/评价(b)        │
│ 成本 O(话题数) 非 O(用户数)        │   │  + 目标/驱动(c)+ profile.json     │
│ 所有用户共享同一份语料             │◄──┤ base(owner)⊕ overlay(用户)        │
└────────────────────────────────────┘   │ 由无状态 runner 用 env-sync 物化跑 │
     "看什么内容"(共享池)              │ "怎么看/怎么进化"(个人镜头)       │
                                          └────────────────────────────────────┘
```

三层的一句话职责:
- **代码 = 引擎**(怎么跑,所有人一样,永在线、确定性)。
- **数据 = 素材**(有什么新闻,话题为键、全员共享)。
- **Agent 环境 = 镜头**(这个人怎么看这些素材、怎么根据反馈进化,每人一份、可回滚)。

**隔离不变量(贯穿三层):谁的反馈都只改自己 ③ 里的 overlay,不改他人 ③、不改 ② 共享语料、不改 owner 全局 base。**

---

## 3. ① 代码层(确定性引擎)

**原则:代码里没有 LLM,也没有 per-user 分支。** 用户差异全在 ③ 的文件里;代码只是"拿 profile.json 给共享语料排个序"这种确定性动作。

跑在何处 = 沿用现状:**Cloudflare Pages(站点)+ Workers(API)+ Cron Triggers(定时/入队)**。

| 模块 | 位置 | 说明 |
|---|---|---|
| 认证 / 会话 | `worker/lib/{auth,session,otp}.js` + `functions/_middleware.js` | SP1 已有,不动 |
| 反馈/关注/已读/请求/活动 | `worker/feedback-worker.js` + `worker/lib/*` | SP1 已有;**新增:handler 里顺带确定性更新 profile(§5.3 热通道)** |
| 个人重排 | 新增 `worker/lib/rank.js` + `GET /me/feed` | 读 profile.json(KV 热缓存)对共享语料打分排序,**纯确定性、无 LLM** |
| 翻译版进化面 | `GET /me/evolution` | 服务端把真实分**翻译**成不透明等级+叙事(§8.5 硬约束) |
| owner 仪表盘 / 用户管理 | `web/compile.py` 模板 + `worker/lib/admin.js` | 8 维系统分 + 每用户真实进化(owner only) |
| 系统评分 | `scripts/score.py` | 确定性 6→8 分(相位 2c) |
| 编译 / 发布 / 灰度 | `web/compile.py` · `scripts/deploy-cloudflare.sh` · `scripts/deploy-gray.sh` | 沿用;compile.py 属人工大版本 |

热路径(用户每次翻页)= 只碰代码 ① + 数据 ② + profile.json,**永不触发 LLM、永不读 ③ 的 prose 文件**。这是稳定性的第一块基石:面向用户的路径完全确定、可单测、Agent 挂了也照常出页。

---

## 4. ② 数据层(话题为键的新闻)· 存储设计方案

**采集按话题去重共享(后端效率),看见由本人订阅+画像决定(前端隔离)。** 成本 = O(规范话题数),不是 O(用户数)。

### 4.1 话题注册表(共享单一真源)
- `config/topics.yaml`(owner 可编种子)+ `data/topics/registry.json`(运行态:规范名、别名、活跃订阅数、来源/检索角度、上次采集、状态)。
- **归一/合并**:用户新话题先规范化(「A股/股市/炒股」→ `finance.equities`),轻量映射为主、必要时一次 LLM 归类。
- **护栏**:①新话题软上限(每周期新增 ≤N,超出排队)或 owner 审核;②长期零订阅→休眠停采;③owner 可并/删/降权。⇒ 成本受控。

### 4.2 存储分层(D1 / KV / R2)——各司其职

| 层 | 存什么(数据) | 为什么放这 |
|---|---|---|
| **D1**(关系型,可 JOIN/查询) | **索引与关系**:`corpus_item`(id,date,batch,topic,source,url,title_zh,kind,dedup_key,r2_key)、`topics` 注册表、`user_topics` 订阅、`feedback`/`activity`(SP1)、`user_scores` | 需要"给我话题 X,Y 在 D 日的条目"这种**带条件查询/联表**的能力 |
| **R2**(对象存储,便宜、装大块) | **载荷与文件**:`corpus/<date>/<topic>.json`(条目全文/原声/证据)、`analysis/<date>.json`、原始抓取、分享图(已有)、**③ 的环境文件与 profile 快照/历史** | "文件"的天然归宿;大 JSON、原文、图片不该塞 D1 |
| **KV**(边缘,毫秒读,最终一致) | **热缓存**:会话(SP1)、**每用户 profile.json 热副本**(重排每请求读一次)、话题注册表快照 | 边缘"读一小块极快";重排热路径靠它免打 D1/R2 |

**读写流向:** 写入=索引进 D1、载荷进 R2;重排热读=profile 从 KV、候选条目从 D1 索引(必要时载荷走 R2/CDN)。**贵的(采集/汇总产物)共享一份;便宜的(排序)才 per-request。**

### 4.3 迁移的克制(先简单,后扩展)
- **现状不动**:共享语料现以 JSON 存 git(`data/corpus`、`data/analysis`)并编译进静态页,**继续如此**——最简单、天然版本化可回滚。
- **只在必要时上云**:当话题/条目数把"一张巨型静态页"撑爆时,才把**载荷搬 R2 + 索引进 D1**,页面改按话题/日期走 API 取,而非一次性下发全量。**相位 2b 才做,2a 不需要。**

### 4.4 `/me/feed` 热路径(相位分明)
1. 取用户订阅话题(KV profile.topics)。
2. **常见情形(订阅⊆base 话题)**:静态页已含全部 base 条目 → `/me/feed` 只回**顺序 + 隐藏集 + 不透明「为你」标签**,JS 据此重排/折叠 DOM。**= SP1 静态页 + 一次极小重排调用,零额外载荷。**
3. **进阶情形(有额外话题)**:D1 按话题查候选 id → R2/CDN 取载荷 → 排序回传。属 2b。

---

## 5. ③ Agent 自进化环境(千人千面,每人一份)

### 5.1 环境 = 每人一个文件夹(对应用户要求的 a/b/c)

```
users/<user_id>/            # 一个用户的完整"自进化环境"(overlay,稀疏)
├── agent.md          (a)  # 这个用户的 agent 说明/人设/镜头:它替谁策展、克制/创新的边界、可改哪些文件
├── spec.md           (b1) # 规范:为这个用户怎么筛/排/强调/折叠(对 prompts/synthesize 的个人化补充)
├── rubric.md         (b2) # 评价:个人 8 维评分口径(对 prompts/scoring.md 的个人 base;§8)
├── goals.md          (c1) # 目标:这个用户的北极星(对 GOALS.md 个人化——"对他而言什么是非显然洞察")
├── loop.md           (c2) # 驱动手段:个人进化循环(信号→执行器→压力→护栏→节律,§5.4)
├── profile.json           # 编译产物:结构化权重(话题/实体/来源/语气/muted),热路径唯一消费物
├── changelog.md           # 个人进化留痕(每轮改了什么、为什么),可回看可回滚
└── scores.jsonl           # 个人 8 维分数时间序列
```

对齐用户三点要求:**(a)=`agent.md`;(b)规范+评价=`spec.md`+`rubric.md`;(c)目标+驱动=`goals.md`+`loop.md`。**

### 5.2 base ⊕ overlay(稀疏叠加)——简单性的核心

- **base = owner 的那份环境**(`CLAUDE.md`/`GOALS.md`/`prompts/scoring.md`/`prompts/*.md`),即现有 git 仓库,**= 全体新用户的默认起点**。
- **overlay = `users/<id>/` 里那几个文件**,且**稀疏**:新用户 overlay ≈ 空 → 有效环境 ≡ owner base → 页面 ≡ 现状 AI 向。开始反馈后,进化循环**只写发生分叉的那个文件**(通常就是 `profile.json` + 一句 `agent.md` 里的"你的镜头" + `rubric.md` 里几个权重微调)。
- **有效环境 = base 的文件,被 overlay 里同名文件逐个覆盖**(文件级 merge,不是行级 diff,足够简单)。

稀疏 overlay 一次性解决四件事:
1. **存储极小**(每用户几 KB)。
2. **base 升级自动下渗**——owner 进化了某 prompt,所有没覆盖该文件的用户自动受益(不必逐户同步)。
3. **"重置我" = 删 overlay**。
4. **回滚 = 恢复 overlay 上一版本**(R2 版本化)。

### 5.3 两条更新通道(热=确定性,冷=LLM)——都只写 `profile.json`,热路径只读它

`profile.json` 是**唯一被 ① 代码热路径消费的编译产物**;prose 文件(agent/spec/rubric/goals/loop)是**人/LLM 可编辑的源**,**热路径永不读**。

```
通道 A｜热 · 确定性 · Workers · 每次反馈:   👍👎✓关注屏蔽停留 → EWMA 规则微调 profile 权重 → 写 KV+R2
        ── 这一条就足以让"页面随反馈变"。无 LLM、即时、稳。
通道 B｜冷 · LLM · runner · 周期(每日/活跃时):
        读【有效环境 prose + 累积反馈 + 当前 profile】→ 小 LLM 精修:
          · 重写 agent.md/spec.md 里"你的镜头"叙事、发现细微偏好
          · 微调 rubric.md 权重、goals.md 侧重
          · 产出规则算不出的 profile 增量(如"此人其实偏爱逆共识")
        → 确定性地把增量并进 profile.json + 写 changelog + 记 scores.jsonl
        ── 远低于全量管线;规则为主、LLM 为辅。
```

⇒ **面向用户永远是确定性的 A + 排序;LLM 只在后台的 B,且产物落成确定性的 profile.json 再被消费。** 这是稳定性第二块基石。

### 5.4 loop.md = "loop engineering 的目标与驱动手段"(用户要求的 c)

每个用户的 `loop.md` 把个人进化循环写死成五要素:

| 要素 | 内容 |
|---|---|
| **目标 goal** | 见 `goals.md`:对此用户最大化"非显然洞察";硬约束=不臆造、宁缺毋滥(承自全局 GOALS) |
| **信号 signal** | 此人的反馈(👍/👎/✓/关注/屏蔽/停留)+ 个人 8 维分 |
| **执行器 actuator** | 只能改:`agent.md`/`spec.md`/`rubric.md`/`goals.md` 侧重 + `profile.json` 权重/muted。**不能改代码/schema/②共享语料/owner base** |
| **压力 driver** | 每轮把个人 8 分里**最低的**提上去;**张力矩阵**防作弊(§8.3):过度 mute→个人克制↓(反回音室);兴趣过窄→个人创新↓(反过滤气泡) |
| **护栏 guard** | 隔离不变量;小步可回滚 + 个人 changelog;个人 evolve 不碰全局,全局 evolve 不碰已分叉 overlay |
| **节律 cadence** | 每日一次(或活跃时增量),批量 |

**驱动手段的本质**:个人 8 维分 = 奖励函数,"提最低分 + 张力矩阵" = 让循环自动收敛到"既懂这个人、又不把他关进过滤气泡"。这正是 loop engineering。

---

## 6. Agent 运行在哪里(Q1)· 无状态 runner

**决定:热路径永在 Workers;LLM 进化在一个无状态 `runner`,近期本地、远期云端,同一套 skill 零改动搬家。**

```
┌ 永在线(确定性) ─────────────┐     ┌ 周期(LLM 进化) ─────────────────────┐
│ Cloudflare Workers            │     │ agent runner(无状态,可搬家)        │
│  · /me/feed 重排(读 profile) │     │  近期:owner 本地 Claude Code(ln-daily│
│  · 通道 A 反馈→profile        │     │        循环活跃用户,复用现有 skill)  │
│  · /me/evolution 翻译版        │     │  远期:同一 skill 提升为**定时云端**   │
│  Cron Trigger 只**入队**       │────►│        (Claude Code 定时云 agent /     │
│  "evolve user X"(不跑 LLM)   │queue│         cron 容器跑 headless)          │
└───────────────────────────────┘     │  动作:env-sync 拉环境→跑通道B→写回    │
                                        └────────────────────────────────────────┘
```

- **Workers 永不跑 LLM**——只服务确定性热路径 + 用 Cron Trigger 把"该给用户 X 跑进化了"塞进队列。边界干净。
- **runner 无状态**:全部状态在 git(base)+ R2(overlay/载荷)+ D1(索引/分数)+ KV(热缓存)。runner 自己不存任何东西 → **可随时重启、可从笔记本搬到云容器,零代码改动**(只把 env-sync 指向同一批存储)。这直接回答 Q1+Q3:稳定=无状态+可搬家。
- **搬家路径**:今天 `ln-daily` 在本地循环少量用户;人数涨了,把**完全相同**的 skill/loop 挂到定时云 agent(或 cron 容器跑 Claude Code headless / Agent SDK)。因为环境是"存储里的文件",搬家不重写逻辑。
- **降级即安全**:runner 宕机 → 热路径照常出页(服务最后一版 profile.json),只是进化暂停。无单点拖垮用户。

---

## 7. 如何获取环境文件(Q2)· env-sync

一个小工具/skill `env-sync`,把"文件散落在 git+R2"物化成 runner 眼里一个普通文件夹:

```
env pull <user_id>              # base(git checkout)⊕ overlay(R2 objects) → runtime/users/<id>/
                                #   → runner 看到的就是一叠正常 markdown + profile.json
env push <user_id>              # 把改动写回:
                                #   prose/overlay → R2(新版本,R2 versioning 留痕)
                                #   profile.json  → R2 + 刷新 KV 热副本
                                #   changelog     → append;scores → D1 user_scores
env diff <user_id>              # 看这个用户相对 base 分叉了哪些文件(= overlay 内容)
env reset <user_id> [file]      # 删 overlay(整体或某文件)→ 回到 owner base
```

- **base"怎么拿"** = 它就是 git 仓库,现状即如此。
- **owner 侧可见**:`GET /admin/users/:id/env` 只读查看某用户有效环境 + 真实分(用户管理里)。
- **用户不可见(硬约束 §8.5)**:用户端**没有**任何返回 rubric/权重/真实分的接口;`/me/*` 只回本人设置(订阅/屏蔽)与翻译版进化面。
- **实现克制**:overlay 就是 R2 里 `env/users/<id>/<file>` 几个对象;pull=批量 GET,push=批量 PUT。无需数据库建模 prose(D1 只存 profile 的结构化镜像用于查询,可选)。

---

## 8. 评分:6→8 系统分 + 张力 + 统一框架 + 可见性硬约束

评分口径 = ③ 里的**评价文件**(全局 base=`prompts/scoring.md`+`scripts/score.py`;个人=`rubric.md`)。承自 v1,措辞收紧。

### 8.1 现有 6 分(`scripts/score.py`,确定性,已上线)
`correlation / volume / analysis / breadth / source_quality / timeliness`,`composite=6 者均值`,agent 每轮提最低分。**几乎全在奖励"更多/更高"**(盲区见下)。

### 8.2 新增 2 分(补正交盲区,形成克制↔创新张力)· 相位 2c

**7 · 克制 restraint** — 盲区:GOALS 称 over-reach 为"北极星最大风险"却无分惩罚;关联/分析分反奖励大胆。组件(从 `analysis`+`corpus` 确定性算):
- `overreach_rate`:大胆结论(grade∈推断/预测)中 `len(evidence)<2` 或"预测无置信度标注"占比;`grounded = 1 − overreach_rate`(权重最高)。
- `grade_discipline`:预测占比落健康带(≤0.4);推断不冒充事实。
- `evidence_depth`:大胆结论平均证据数 → `clamp(avg/2)`。
- `snr`:呈现条目中被 conclusions/connections 证据**真正引用**的占比(无水文尾巴)。
- `restraint = 100·(0.40·grounded + 0.20·grade_discipline + 0.20·evidence_depth + 0.20·snr)`
- **反作弊**:堆 non_obvious 刷关联 → overreach↑ → restraint↓,composite 不赚。

**8 · 创新 innovation** — 盲区:6 分奖励"同类做更多",`source_quality` 还奖励吃 core(吃老本)。组件(对比历史窗口 `state/scores.json`/`data/entities`/前 K 日 corpus):
- `new_productive`:今日**产出内容**里近窗口未见的话题/实体数。
- `exploration`:`1 − from_core_share`(取健康带,**与第 5 分反向**,逼别只吃 core)。
- `lens_diversity`:用到的透镜种类,冷门透镜(二阶效应/跨域/跟着钱走/共识缺口)加成。
- `cross_domain_novel`:近窗口未配过的跨域配对数。
- `learning_velocity`:上轮最低分本轮是否被 evolve 提上来(读 `delta_vs_prev`)。
- `innovation = 100·(0.25·new_productive + 0.20·exploration + 0.20·lens_diversity + 0.20·cross_domain_novel + 0.15·learning_velocity)`
- **反停滞**:只吃 core、重复昨天 → exploration/new_productive↓ → innovation↓。

### 8.3 张力矩阵(分数间关系 = 约束)
| 抄近路 | 涨 | 跌(净不赚) |
|---|---|---|
| 臆造/过度引申堆关联 | 关联↑ 分析↑ | 克制↓ |
| 只吃 core、重复昨天 | 源固化↑ | 创新↓ |
| 灌水凑量 | 数量↑ 广度↑ | 克制↓(信噪比) |
| 乱试制造噪音 | 创新↑ | 克制↓ |
| 只求稳不试新 | 克制↑ | 创新↓ |

`composite = 8 者均值`,提最低分 → 收敛到"既克制又创新"。**score.py 输出 8 分 + composite;`state/scores.json` 加两分(向后兼容:旧 entry 缺则视 None,`delta` 对 None 不算)。**

### 8.4 统一框架:全局 vs 个人(同一套 8 维)
- **全局尺度**(score.py over `data/analysis/<date>`,owner)= **系统迭代能力**,owner 仪表盘。
- **个人尺度**(同 8 维,over 用户那片:其订阅话题条目 + 其反馈 + 其画像变更)= **个人进化分数**;`composite=分数`,进化能力=成熟度等级。
- **个人克制=反过拟合/反回音室**(muted 过猛即扣);**个人创新=反过滤气泡**(始终留 serendipity)→ 天然过滤气泡护栏。
- **明确不含系统分**(个人进化能力不含系统迭代)。

### 8.5 可见性:评分框架=系统核心,用户只见"翻译版"(**硬约束**)
- **真实评分系统**(8 维/克制创新/composite/rank 权重公式)= 核心资产,**任何用户不可见**:不下发客户端、无 API 返回真实分、页面无维度名/雷达/数字。
- **用户只见翻译版进化面**:不透明等级+进度+会变的叙事(+可选里程碑),服务端从真实分翻译。目的仅:让用户"感到在进化、越来越懂我"。
- **owner 例外**:owner 在用户管理看每用户**真实**个人进化(8 维+趋势+能力);全局 8 分在 owner 仪表盘。真实评分只在 owner 侧。

---

## 9. 数据模型(D1 新增,建在 SP1 之上)

```sql
CREATE TABLE user_topics (          -- 话题订阅(便于按话题聚合/扩采触发)
  user_id INTEGER, topic TEXT, weight REAL, subscribed_at TEXT, PRIMARY KEY(user_id, topic));
CREATE TABLE user_scores (          -- 个人 8 分时间序列(镜像 R2 的 scores.jsonl,便于 owner 查询/画趋势)
  user_id INTEGER, date TEXT, scores TEXT, composite REAL, capability REAL, computed_at TEXT,
  PRIMARY KEY(user_id, date));
CREATE TABLE topics (               -- 规范话题注册表索引(运行态真源仍是 data/topics/registry.json)
  topic TEXT PRIMARY KEY, canonical TEXT, aliases TEXT, subscribers INTEGER,
  sources TEXT, last_collected TEXT, status TEXT);
CREATE TABLE corpus_item (          -- 语料索引(载荷在 R2);2b 上云时启用,2a 可不建
  id TEXT PRIMARY KEY, date TEXT, batch TEXT, topic TEXT, source TEXT, url TEXT,
  title_zh TEXT, kind TEXT, dedup_key TEXT, r2_key TEXT, created_at TEXT);
```
- **profile / prose 环境不进 D1**:`profile.json` 与 prose 文件是 **R2 对象**(`env/users/<id>/*`),KV 存 profile 热副本。D1 只存需要**联表/趋势查询**的东西(订阅、分数、话题、语料索引)。
- 全局系统 8 分仍走 `state/scores.json`(加两字段,git 版本化)。

---

## 10. API(新增,建在 SP1 认证之上)

| 端点 | 作用 |
|---|---|
| `GET /me/feed?date=` | 服务端算好的个人排序:条目 id 顺序 + 隐藏集 + 不透明「为你」标签(**不含权重/框架**) |
| `GET /me/evolution` | **翻译版**:等级+进度+会变叙事(+里程碑);**绝不含 8 维/克制创新/composite/公式** |
| `POST /me/topics {topic,on}` | 订阅/退订(触发归一+可能扩采) |
| `POST /me/mute {kind,value,on}` | 屏蔽话题/实体/来源 |
| `GET /topics` | 可订阅话题列表(+是否已采) |
| `POST /admin/topics ...` | owner 管注册表(并/删/降权/审核) |
| `GET /admin/users/:id/evolution` | **owner** 看某用户**真实**个人进化(8 维+composite+能力+趋势) |
| `GET /admin/users/:id/env` | **owner** 看某用户有效环境(base⊕overlay 只读) |
| `GET /admin/scores` | **owner** 全局系统 8 分(现有 +2) |

> 客户端**无**任何返回真实分/画像权重/prose 的端点;真实评分与环境仅 `/admin/*`(owner)可得。反馈/关注等 SP1 端点在其 handler 里**顺带走通道 A**更新 profile。

---

## 11. 前端
- **个人页重排**:登录后单页 JS `GET /me/feed` → 按返回顺序/隐藏集重排 DOM、标不透明「为你」(**不取权重/框架**);订阅/屏蔽入口复用 SP1 设置菜单。
- **翻译版进化面**:`GET /me/evolution` → 等级+进度条+一句会变叙事(+里程碑)。**不出现任何真实维度/分数/公式/雷达**。
- **owner 全局仪表盘**:现有「📊 自进化仪表盘」升级显示 8 维(+克制/创新),owner 专属。
- **owner 用户管理**:每用户行可展开真实个人进化(8 维+趋势+能力)。真实评分只在 owner 侧。
- 主题/深色沿用 SP1。

---

## 12. 简单性与稳定性原则(Q3)· 显式清单

系统"简单且稳定"靠这五条硬原则托住,任何改动不得违反:
1. **一种范式**:Agent 只做"读文件→想→写文件";用户差异是**数据(overlay)不是代码**。永不写 per-user 分支。
2. **确定性引擎 + 边缘极简**:面向用户的热路径(重排/服务/通道A)**零 LLM、可单测、可复现**;LLM 只在后台通道B,且产物落成确定性 `profile.json` 再被消费。
3. **稀疏 overlay 而非 fork**:每用户只存分叉的那几个文件;base 升级自动下渗;重置=删 overlay;回滚=恢复上一版。
4. **无状态 runner**:全部状态在 git/R2/D1/KV;runner 可重启、可从本地搬云端零改动。runner 宕机 → 热路径照常降级出页。
5. **复用现有结构**:overlay 文件镜像现仓库(`agent.md`~CLAUDE/AGENTS、`rubric.md`~scoring.md、`goals.md`~GOALS.md);不发明新范式,新增 schema 字段向后兼容。

---

## 13. 成本与扩展
- 采集/汇总:O(规范话题数),护栏封顶;个人重排:确定性 O(条目数)、无 LLM;个人 evolve:规则为主、单价极低,随人数线性但便宜。⇒ **共享贵的(采集/汇总),便宜的才 per-user。**
- 明确接受:全新话题一次性扩采成本(用户已认可)。

---

## 14. 实施相位(每相位独立 plan;派发子任务执行)
- **2c(可独立先行,无账号/数据依赖)· 最小最快见效**:`score.py` 6→8(克制/创新)+ `prompts/scoring.md`/`GOALS.md` + owner 仪表盘 8 维。**先落、先推灰度。**
- **2a(需 SP1)**:③ 环境骨架(`users/<id>/` 文件树 + env-sync)+ 通道A(反馈→profile)+ 服务端 `/me/feed` 重排 + 通道B evolve-lite(runner)+ 个人真实 8 分(owner 侧)+ 用户端翻译版进化面。**跑在现有共享语料上。**
- **2b(需 SP1,最重最后)**:话题注册表 + 话题为键采集/汇总改造 + 新话题扩采 + ②数据上云(R2 载荷 + D1 索引)。

建议顺序:**SP1 → 2c → 2a → 2b**(2c 也可与 SP1 并行)。

---

## 15. 隔离不变量与测试
- 单测(确定性):score.py 7/8 反作弊(堆 non_obvious→克制↓;只吃 core→创新↓)、rank 函数、profile 更新规则(通道A)、话题归一、护栏软上限、overlay 文件级 merge。
- **隔离不变量测试**:A 反馈后 B 的页面/画像/分数不变;个人 evolve 不改全局 base;owner evolve 不改已分叉 overlay;runner 宕机 → 热路径仍出页(降级)。
- 端到端:新用户≡owner base → 反馈后分叉;订新话题→扩采回填可见;个人仪表盘随反馈上行;过滤气泡护栏(创新分兜底 serendipity);env pull→改→push→回滚闭环。

---

## 16. 已决 / 遗留 / 假设
- **已决**:三层分离(代码/数据/Agent 环境);一切皆文件 + base⊕稀疏overlay;热路径确定性 Workers、LLM 仅后台无状态 runner;profile.json=唯一热消费编译产物;6→8 张力约束;**评分框架=核心、用户只见翻译版、真实分仅 owner(§8.5 硬约束)**;存储分层 D1索引/R2载荷/KV热缓存。
- **假设(执行按此,若不符再调)**:runner 近期=owner 本地 Claude Code 循环活跃用户;远期提升为定时云端;个人 evolve 每日一次;话题归一默认映射+必要时轻 LLM;新话题默认软上限自动纳入。
- **遗留(评审待定)**:翻译版进化面的等级/叙事/里程碑措辞与阈值;话题软上限 N 的取值;云端 runner 具体载体(定时云 agent vs cron 容器)——待 2a/2b 落地时定。

---

### 附:上游需求(用户原话,v2 三层框架)
- 三部件:①代码(认证/灰度/仪表盘等服务)②数据(采集的新闻,按主题/领域分,存 DB/KV/R2)③Agent 自进化环境(千人千面,每人一份:`agent.md` + 规范/评价文件 + loop engineering 的目标与驱动手段;由个人反馈 + 系统反馈共同驱动)。
- 三个必答:①Agent 以后跑在哪(§6)②我如何获取环境文件(§7)③如何更简单稳定(§12)。
- 全局底座以现状为基准;新用户默认=owner 底座;开始反馈后按自己形态走→千人千面。每人可见自己的进化分数/能力(不含系统迭代)。基于现有 6 分加 2 分,用分数间关系约束采集/聚合/生长/进化中的克制与创新(补正交盲区)。
