# 系统评分制度 · scoring.md

> Loop 的**奖惩仪表盘**。八个分数,每一轮(采集/汇总/进化)都**必须重算并关注**,目标是**让每个分数、以及综合分,随轮次向上涨**。
> 计算是确定性的:`python3 scripts/score.py [YYYY-MM-DD]` → 写入 `state/scores.json`(时间序列 + 与上轮 delta)。**agent 的能力建立在分数之上:每轮先看分数,优先把最低/下滑的那个提上去。**

## 八个分数(各 0–100)
| # | 分数 | 衡量什么 | 主要成分(见 score.py) |
|---|---|---|---|
| 1 | **关联度 correlation** | 新闻之间连得有多深 | 关联条数、跨日期关联、非显然结论(≥2 证据且跨日期/域) |
| 2 | **数量 volume** | 采集量够不够 | 当日 corpus 条数 vs `loop.yaml` 的 `collect.volume_target`(20)/`floor`(12) |
| 3 | **分析整合 analysis** | 分析/结论的质量 | 分级结论数、证据回链率、共识缺口/矛盾(edge)、可证伪(预测) |
| 4 | **自进化广度 breadth** | 系统覆盖面在不在扩 | 检索角度数、话题覆盖、领域专题数、近一轮已消化反馈数 |
| 5 | **信息源固化 source_quality** | 优质源有没有被评选/固化 | 已固化(core)源数量与质量、今日采自 core 源的占比、**是否在持续评选(否则衰减)** |
| 6 | **新闻及时性 timeliness** | 新闻新不新、有没有漏采后补 | `lateness=采集日−事件日`;内容陈旧 + 漏采后补 **双重惩罚**;**一天里多条超期→强惩罚(几条就大跌)** |
| 7 | **克制 restraint** | 有没有管住手——不臆造、证据纪律够不够、信噪比高不高 | `grounded`(=1−overreach_rate,权重最高)、`grade_discipline`(预测占比健康带)、`evidence_depth`(大胆结论平均证据数)、`snr`(呈现条目被真正引用占比) |
| 8 | **创新 innovation** | 前沿有没有在扩、有没有只吃老本停滞 | `new_productive`(近窗口未见话题/实体数)、`exploration`(1−from_core_share,与第 5 分反向)、`lens_diversity`(冷门透镜用量)、`cross_domain_novel`(未配过的跨域配对数)、`learning_velocity`(上轮最低分本轮是否被提上来) |

综合分 `composite` = 八者均值。

## 新闻及时性(第 6 分)· 强惩罚 + 漏采后补也罚
每条新闻带 `published`(事件发生日)与 `first_seen`(首次采到日)。核心量 **`lateness = 采集日 − published`**:
- **两种失败都罚**:① 内容陈旧(事件是几天前甚至上周的);② **漏采后补**——事件几天前发生、当时没采到、现在才补进来(`lateness` 同样大)。都判为"不及时"。
- **强惩罚(用户明确要求)**:`fresh_days=4` 天内算新鲜,超过即 `stale`;分数 = `100 × 覆盖率 × (0.5·新鲜度均值 + 0.5·实时占比) × 0.78^(stale数−1)`——**容忍 1 条超期,之后每多 1 条 ×0.78,几条就大跌**(实测 7-01 有 6 条超期 → 及时性掉到 7.7)。
- **覆盖率**:未标 `published` 无法主张及时 → 拉低分数,逼采集端据实标注事件日。
- **来源要实时**:优先实时性高的源(快讯/官方稿/当日报道);`source_quality.json` 给源标 `recency: realtime|fast|slow`,慢速/回顾类源采到的旧闻计入 `stale`。
- **怎么提分**:采当日/昨日一手快讯,别用一周前综述;每轮都跑(晚班也采),避免"当时没采、次日补"的漏采。

## 信息源固化(第 5 分)· 强迫持续评选来源
台账 `data/source_quality.json` 给每个源打 tier:**core(已固化)/ trial(试用)/ watch(观察,岌岌可危)/ demoted(降级淘汰)** + quality。
- **奖励(升级)**:某源连续多轮**被展示 / 被采用 / 贡献非显然结论、且低噪音** → `ln-evolve` 升它一档(trial→core『固化』),quality 上调。
- **惩罚(降级)**:某源连续多轮**噪音 / 重复 / 无产** → 降档(core→watch→demoted→从 `sources.yaml`/`people.yaml` 移除或标 `priority: low`)。
- **强迫评选**:`last_curation` 距今越久,分数里的 `curation` 成分越低(>7 天几乎清零)——**只要 ln-evolve 某轮不评选来源,这个分就会掉**,以此逼它每轮都动手评选。评选完更新 `last_curation` 为当日。
- 目标 `core_sources`≥12;随成长可上调。

## 克制与创新(第 7、8 分)· 补正交盲区 + 张力矩阵
前 6 分几乎全在奖励"更多/更高"(关联更多、量更大、分析更足、广度更宽、源更固化、更及时),唯独没有分惩罚"大胆过头",也没有分惩罚"吃老本停滞"——这两个盲区恰是 [GOALS](../GOALS.md) 早已点名的最大风险(over-reach)与隐藏风险(同类做更多的高分停滞)。第 7、8 分把它们**变成可计分的护栏**。

**7 · 克制 restraint** —— 衡量"有没有管住手、证据纪律够不够、信噪比高不高":
- `grounded = 1 − overreach_rate`(权重最高):大胆结论(grade ∈ 推断/预测)里"证据 <2 条"或"预测没标置信度"的占比,越低越好。
- `grade_discipline`:预测占比是否落在健康带(≤0.4)、推断有没有冒充事实。
- `evidence_depth`:大胆结论的平均证据数,`clamp(avg/2)`。
- `snr`:呈现条目里真正被 conclusions/connections 引用的占比(砍掉挂着没人用的水文尾巴)。
- `restraint = 100·(0.40·grounded + 0.20·grade_discipline + 0.20·evidence_depth + 0.20·snr)`
- **反作弊**:靠堆 non_obvious 刷关联分 → overreach 升 → grounded 降 → 克制分跟着掉,composite 不赚。

**8 · 创新 innovation** —— 衡量"前沿有没有在扩、有没有只吃老本":
- `new_productive`:今日产出内容里,近窗口(对比 `state/scores.json`/`data/entities`/前 K 日 corpus)未出现过的话题/实体数。
- `exploration = 1 − from_core_share`(取健康带,**与第 5 分 source_quality 刻意反向**):逼系统别只吃已固化的 core 源。
- `lens_diversity`:用到的方法论透镜种类,冷门透镜(二阶效应/跨域模式/跟着钱走/共识缺口)加成。
- `cross_domain_novel`:近窗口里没配过的跨域配对数。
- `learning_velocity`:上一轮最低分,这一轮是否被 ln-evolve 提上来了(读 `delta_vs_prev`)。
- `innovation = 100·(0.25·new_productive + 0.20·exploration + 0.20·lens_diversity + 0.20·cross_domain_novel + 0.15·learning_velocity)`
- **反停滞**:只吃 core、重复昨天的话题/配对 → new_productive/exploration 双降 → 创新分掉,composite 不赚。

### 张力矩阵(抄近路 → 某分涨,另一分跌,composite 净不赚)
| 抄近路 | 涨 | 跌(净不赚) |
|---|---|---|
| 臆造/过度引申堆关联 | 关联↑ 分析↑ | 克制↓ |
| 只吃 core、重复昨天 | 源固化↑ | 创新↓ |
| 灌水凑量 | 数量↑ 广度↑ | 克制↓(信噪比) |
| 乱试制造噪音 | 创新↑ | 克制↓ |
| 只求稳不试新 | 克制↑ | 创新↓ |

`composite = 八者均值` + 每轮**提最低分**这条硬规则,让上面每条"抄近路"都不划算:单边讨好某一分会拖垮另一分、进而拖垮综合分,唯一的稳态是**既克制又创新**——既不臆造、也不停滞。

## 奖惩规则(重点)
- **数量分是硬惩罚项**:低于 `volume_floor`(12)按**平方级陡峭下跌**(如 6 条 ≈ 14 分),达 `volume_target`(20)才满分。**采集太少 = 数量分暴跌**,这是"防欠采"的主刹车。
- **只涨不许无理由跌**:某分数较上轮下滑,ln-evolve 本轮**必须优先修它**(补来源/加角度/强化方法论透镜),并在 CHANGELOG 说明。
- **不能靠注水刷分**:数量分看的是 corpus(真实采集,高召回),但**呈现层仍宁缺毋滥、不臆造**(见 [GOALS](../GOALS.md)「采集广度」分层)——刷假条目会被"不臆造"硬约束否决,且拉低分析分。
- **北极星优先**:分数是代理指标;冲突时以 [GOALS](../GOALS.md) 北极星(非显然洞察)为准,分数服务它。

## 每轮怎么用(写进各 skill)
1. **ln-collect** 末尾:采集完先自查数量——远低于 `volume_target` 就地补采(加检索角度),别把欠采留给下游。
2. **ln-synthesize** 末尾:`python3 scripts/score.py <date>` 重算八分,读出最低/下滑项。
3. **ln-evolve**:读 `state/scores.json` 最近若干轮 → **本轮改进优先针对最低/下滑的那个分数**(数量低→补源;关联低→强化跨日期/跨域透镜;分析低→严证据分级;广度低→加领域/角度;源固化低→评选升降级源;**及时性低→采当日一手、剔除旧闻、堵漏采**;**克制低→砍无据结论、补证据、收窄预测占比**;**创新低→别只吃 core、换冷门透镜、找新跨域配对**)。改完再跑一次 score.py 确认回升。
4. 页面「📊 自进化仪表盘」(owner 专属)展示当前八分 + Δ + 趋势(compile 读 `state/scores.json`)。

## 目标线(score.py 里的 TARGETS,可随成长上调)
volume 20/floor 12 · connections 6 · cross_date 3 · non_obvious 4 · conclusions 8 · edge 3 · falsifiable 2 · sources 30 · topics 20 · domains 3 · feedback 6 · angles 8 · core_sources 12 · fresh_days 4 · stale_decay 0.78。
达标即满分;随系统变强,ln-evolve 可上调目标线(记 CHANGELOG),让"向上涨"持续有空间。
