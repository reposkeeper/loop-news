---
name: ln-evolve-lite
description: Loop News 个人自进化(通道 B,千人千面)。对某个活跃用户,读他自己的反馈 + 当前画像 + 有效环境,规则为主(可选一次小 LLM 精修)地微调他的个人环境 overlay(agent/spec/rubric/goals 侧重 + profile.json 权重),写个人 changelog,env push 回 users/<id>/。与全局分离:只消化该用户自己的反馈,绝不改全局 prompts/config/owner base,也不碰别的用户。每日一次或用户活跃时,由无状态 runner 跑。当用户说"个人进化"、"evolve-lite"、"给某用户跑进化"、"per-user evolve"时使用。
---

# ln-evolve-lite · 个人自进化(通道 B)

让**每个用户**的镜头越跑越懂他:对某个活跃 `user_id`,读他自己的反馈,规则为主地微调**他自己**的环境 overlay,产出确定性的 `profile.json` 增量。**这是「千人千面」的冷通道**——面向用户永远是确定性的通道 A + 排序;本 skill 只在后台跑,产物落成 `profile.json` 再被热路径消费。

> 权威设计见 [`specs/2026-07-01-personalization-evolution-design.md`](../../../specs/2026-07-01-personalization-evolution-design.md) §5.3(两条更新通道)、§5.4(loop 六要素)、§6(无状态 runner)、§8.4–8.5(个人 8 维 + 真实分用户不可见)。个人环境目录约定见 [`users/README.md`](../../../users/README.md)。
>
> **与全局 [`ln-evolve`](../ln-evolve/SKILL.md) 的分工(硬红线)**:全局 evolve 消化 `role=owner` 反馈、改**全局** `prompts/*.md` / `config/*.yaml` / `GOALS.md` / `prompts/scoring.md`;本 skill 消化**某个普通用户自己**的反馈、只改**他自己**的 `users/<id>/` overlay。**个人 evolve 绝不改全局 base,全局 evolve 也不改已分叉 overlay。**

## 触发
- **节律**:每日一次(早班链路里,对当日活跃用户逐个跑),或该用户活跃时增量。批量、规则为主、单价极低。
- **对象**:一个活跃 `user_id`(有新反馈或近期有互动)。runner 无状态:所有状态在 git(overlay)/ R2 / D1 / KV,runner 自己不存任何东西(§6)。

## 输入(全是「这个人自己的」)
1. **他自己的反馈**:D1 `feedback` 表(schema 见 [`worker/schema.sql`](../../../worker/schema.sql)),**按 `WHERE user_id=<id>` 取**(动作:`up 赞 / down 踩 / adopt 采用` + `tags` 常用词 + 自定义 `text`;另有 `follows`(关注)/ `reads`(已读)可选)。
   - **复用 [`scripts/feedback.sh`](../../../scripts/feedback.sh) 的思路**(内部 `npx wrangler d1 execute loop-news-db --remote`),但把 `WHERE role='owner'` 换成 `WHERE f.user_id=<id>`。feedback.sh 本身只查 owner(供全局 evolve);个人 evolve 查单个用户。
   - 通道 A 已把每次反馈即时折进 `profile.json`(确定性、在 [`worker/feedback-worker.js`](../../../worker/feedback-worker.js) 里);本 skill(通道 B)做的是**规则算不出的冷增量**。
2. **当前画像**:该用户的 `profile.json`(形状:`{topics:{t:w}, entities:{e:w}, sources:{s:w}, tones:{深度,共识,数据,原声}, muted:[], version, updated_at}`;空 = base = 新用户 ≡ owner 页)。
3. **有效环境 prose**:`bash scripts/env-sync.sh pull <id>` 物化到 `runtime/users/<id>/`(base ⊕ overlay 文件级 merge),读其中 `agent.md` / `spec.md` / `rubric.md` / `goals.md` / `loop.md` 当上下文。

## 步骤(规则为主 + 可选一次小 LLM 精修)
1. **物化环境 + 取反馈**:`bash scripts/env-sync.sh pull <id>` → 读 `runtime/users/<id>/` 全部 prose + `profile.json`;按 `user_id` 从 D1 取该用户反馈(见上「输入」)。
2. **规则更新画像(主体,确定性,无 LLM)**:据反馈聚合小步调 `profile.json`——
   - `up`/`adopt`(采用)→ 对应 `topics`/`entities`/`sources` 权重↑;`down` → ↓;明确屏蔽 → 进 `muted`。
   - `tones`(深度/共识/数据/原声)按**被赞条目的 kind** 微调偏好。
   - **小步 EWMA、幅度设上限**(单轮不剧烈翻转),保证可解释、可回滚。
3. **个人 8 分 + 张力矩阵防作弊**(口径承 [`rubric.md`](../../../users/_base/rubric.md) / [`prompts/scoring.md`](../../../prompts/scoring.md),over「这个人那片」):
   - 算此人个人 8 维分,**提最低分**那一维。
   - **张力护栏**:若 **`muted` 过猛 / 只留一种声音 → 个人克制↓(反回音室)** → 本轮抑制继续窄化、给对立面留透气口;若 **兴趣过窄 / 只吃 core → 个人创新↓(反过滤气泡)** → 本轮强制保留 serendipity 名额(共识缺口 / 逆共识 / 跨域惊喜)。⇒ 循环收敛到「既懂他、又不把他关进气泡」。
4. **可选一次小 LLM 精修**(仅当规则算不出时,小改、有据):重写 `agent.md` 里一句「你的镜头」叙事 / 发现细微偏好(如「其实偏爱逆共识」)/ 微调 `rubric.md`、`goals.md` 的侧重。**产物必须能落成确定性的 `profile.json` 增量**再被消费(§5.3)。
5. **确定性并进 + 留痕**:把增量并进 `runtime/users/<id>/profile.json`(bump `version`、更新 `updated_at`);在 `runtime/users/<id>/changelog.md` 顶部追加一条(**日期 · 改了什么 · 为什么(引用具体反馈条目 id/text) · 如何回滚**);append 个人 8 分到 `runtime/users/<id>/scores.jsonl`。
6. **写回 overlay**:`bash scripts/env-sync.sh push <id>` → 把相对 base 有分叉的文件稀疏写回 `users/<id>/`(env-sync 只管 git 侧;`profile.json`→KV/D1、`scores.jsonl`→D1 由 runner 在有 wrangler 凭据时做,见 env-sync push 的 TODO 注释)。
7. **隔离自检**:`bash scripts/env-sync.sh diff <id>` 确认本轮**只** `users/<id>/` 有分叉;**没碰** `prompts/*.md` / `config/*.yaml` / `GOALS.md` / `prompts/scoring.md` / owner 全局 base / 别的用户 / ② 共享语料 / 代码 schema。

## 纪律(隔离 + 规则为主 + 硬约束)
- **隔离不变量(硬红线)**:只改本用户 `users/<id>/` overlay;**只消化该用户自己的反馈**;不外溢成全局改动;不碰他人 overlay。个人 evolve 不碰全局 base,全局 `ln-evolve` 不碰已分叉 overlay。
- **规则为主、LLM 为辅**:主体是确定性规则(权重 EWMA + 张力矩阵 + 提最低分);LLM 至多一次小精修,且**产物落成确定性 `profile.json` 再被热路径消费**。远低于全量管线。
- **降级即安全 / 无状态可搬家**(§6):runner 宕机 → 热路径服务最后一版 `profile.json` 照常出页,只是进化暂停;runner 不自存状态,可从本地 Claude Code 搬到定时云端零代码改动(同一 skill,只把 env-sync 指向同一批存储)。
- **可见性硬约束(§8.5)**:真实 8 维分 / 权重 / 框架**用户不可见**;`rubric.md`/`scores.jsonl` 是内部口径,用户端只见服务端翻译版(不透明等级 + 进度 + 会变叙事)。
- **承 [GOALS.md](../../../GOALS.md) 硬约束**:不臆造、宁缺毋滥;个人偏好不能凌驾「不臆造」;个性化下限 = 不喂回音室/过滤气泡。
- **小步可回滚**:每轮改动小、有据;git revert + 个人 `changelog.md` 可回滚。若本轮该用户反馈稀疏、画像健康,可「无改动」,在 `changelog.md` 记一句「本轮稳定,无改动」。
