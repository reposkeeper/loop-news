# 进化改动日志(CHANGELOG)

> `ln-evolve` 每轮自评后,把对 `prompts/*.md`、`config/*.yaml` 的改动记在这里。
> 格式:日期 · 改了什么 · 为什么 · 如何回滚。最新在最上。

---

## 2026-06-30 · 进化 #1(首期真实运行后自评)
- **依据**:`state/metrics.json` 的 `2026-06-30-am` 一轮 —— `x_mcp: unavailable`、`reddit: blocked`、`nitter: dead`;且抽查首期产物发现共识类 `url` 多指向聚合/周报页(buildfastwithai、medium 综述)而非一手出处。
- **改了什么**:
  1. `prompts/collect.consensus.md`:新增「优先一手出处」规则——`url` 优先原始媒体/官方稿,禁用聚合页当来源,`consensus_count` 必须实数不估算。
  2. `config/sources.yaml`:标注 Reddit 被拦(仅作 WebSearch 信号)、HN 改用 Algolia API、新增 `x.via: mcp`(fallback websearch)。
- **为什么**:提升共识类来源可信度与可回溯性;把实测的来源可用性固化进配置,指导下一轮采集。
- **如何回滚**:`git revert` 本次提交,或删除上述两处新增段落即可恢复到「进化 #0/初始化」基线。

---

## 2026-06-30 · 工程初始化
- **改了什么**:创建初始提示词(collect.consensus / collect.deep / synthesize.method)与来源配置。
- **为什么**:Loop Engineering 工程起步,建立可被后续自动演进的基线。
- **如何回滚**:本条为初始版本,无需回滚;后续改动以本版本为基线对比。
