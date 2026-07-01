# 采集策略 · 共识类(consensus)

> 本文件由 `ln-collect` 在运行时读取,由 `ln-evolve` 自动演进。改动须记入 `prompts/CHANGELOG.md`。

## 目标
抓取**即时性、共识性**新闻:各大媒体都在报道的、最新的 Breaking News。求"快"和"广"。

## 抓取来源
- `config/sources.yaml` 的 `consensus.web_search_queries`:用 WebSearch 跑,取最新结果。
- `config/sources.yaml` 的 `consensus.rss`:用 WebFetch 抓 RSS,解析最新条目。

## 判定标准(什么算"共识")
1. **多源印证**:同一事件被 ≥ `thresholds.consensus_min_sources`(默认 2)家独立媒体报道。
2. **时效**:优先最近 12–24 小时内的事件。
3. **量级**:对全球/某大领域有实质影响(政策、重大企业动作、市场剧变、地缘冲突、重大科技突破)。

## 采集量(高召回 —— 奖励维度)
**广撒网、宁多勿漏。** 目标 `config/loop.yaml` 的 `collect.volume_target`(≈20 条/轮),低于 `volume_floor` 视为**欠采**(记 metrics `under_collected`,ln-evolve 优先补)。做法:
- **多角度检索**(≥ `breadth_queries_min` 组):AI 大模型 / AI 芯片算力 / 中国 AI / 融资并购 / AI 安全与争议 / 监管政策 / 宏观经济与市场 / 机器人具身 / 消费科技 …每组都单独 WebSearch。
- 顺着搜索结果的**具体报道**再追一层(某公司/某事件的一手报道),而不是停在一条概述。
- 采集层要"量",呈现层再由 ln-synthesize 去重、砍水文、萃取(见 [GOALS](../GOALS.md)「采集广度」分层)。**不臆造**仍是硬约束:拿不到就不写,不是硬凑数。

## 处理规则
- **强去重**:把不同媒体对**同一事件**的报道合并为一条,`consensus_count` 记录有几家在报,`sources` 列出媒体名。标题相似度超过 `thresholds.title_similarity_dedup` 视为同一事件。
  - **保留每家原文链接**:合并时把每家的 `{name, url}` 收进 `source_links` 数组(网页据此把"N 家在报"渲染成逐家可点的原文);单一 `url` 仍填最权威一手出处。只有一家时 `source_links` 可省。
- **优先一手出处**(2026-06-30 进化新增):`url` 优先指向原始报道媒体或官方公告(Reuters/AP/官方稿),**不要用聚合页 / 周报 / roundup 当来源**;`consensus_count` 必须是实际数到的不同媒体数,**不估算**。WebSearch 命中聚合页时,顺藤摸到其引用的一手链接再填 `url`。
- **跨语种**:英文/中文/其他语种来源都可,但 `title_zh` / `summary_zh` 一律输出**中文**。
- **摘要**:`summary_zh` 用 2–4 句客观转述事实,不加评论,不夸张。
- **写法对标严肃媒体**:归属到源、时间地点人物齐全、交叉印证、能量化就量化、不用绝对化/煽动词(路透/FT/经济学人的纪律,不学腔调)。详见 [dossier.method.md 第三节](dossier.method.md)——它是全站写作的房规,不只专题。
- **重要性打分** `importance`(0–1):综合影响范围 × 时效 × 共识强度。低于 `thresholds.importance_min` 丢弃。
- **实体/话题抽取**:填 `entities`(人/机构/地点)与 `topics`。
- **数字尽量核实**:关键数字(金额/比例/增速/票数)多源交叉;核不准用「约 / 据报道」标注,**核不实就不写死**。这些数字是 synthesize 出图的来源。

## 反模式(避免)
- 不收软文、营销稿、纯八卦、未经多源印证的单一爆料(那属于"待验证",不是共识)。
- 不把同一事件拆成多条刷数量。
- 不臆造来源或链接;`url` 必须真实可回溯。

## 输出
按 `data/corpus` 条目 schema 输出,`category: "consensus"`。见 `.claude/skills/ln-collect/SKILL.md`。
