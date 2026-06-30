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

## 处理规则
- **强去重**:把不同媒体对**同一事件**的报道合并为一条,`consensus_count` 记录有几家在报,`sources` 列出媒体名。标题相似度超过 `thresholds.title_similarity_dedup` 视为同一事件。
- **优先一手出处**(2026-06-30 进化新增):`url` 优先指向原始报道媒体或官方公告(Reuters/AP/官方稿),**不要用聚合页 / 周报 / roundup 当来源**;`consensus_count` 必须是实际数到的不同媒体数,**不估算**。WebSearch 命中聚合页时,顺藤摸到其引用的一手链接再填 `url`。
- **跨语种**:英文/中文/其他语种来源都可,但 `title_zh` / `summary_zh` 一律输出**中文**。
- **摘要**:`summary_zh` 用 2–4 句客观转述事实,不加评论,不夸张。
- **重要性打分** `importance`(0–1):综合影响范围 × 时效 × 共识强度。低于 `thresholds.importance_min` 丢弃。
- **实体/话题抽取**:填 `entities`(人/机构/地点)与 `topics`。

## 反模式(避免)
- 不收软文、营销稿、纯八卦、未经多源印证的单一爆料(那属于"待验证",不是共识)。
- 不把同一事件拆成多条刷数量。
- 不臆造来源或链接;`url` 必须真实可回溯。

## 输出
按 `data/corpus` 条目 schema 输出,`category: "consensus"`。见 `.claude/skills/ln-collect/SKILL.md`。
