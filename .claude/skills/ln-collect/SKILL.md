---
name: ln-collect
description: Loop News 采集步骤。从四类来源(主流媒体/RSS、X名人原声、Substack/博客、Reddit/HN)抓取新闻,翻译成中文、摘要、归一化去重后写入语料库 data/corpus。早晚各跑一次。当用户说"采集新闻"、"跑采集"、"collect"、"ln-collect"、"拉今天的新闻"时使用。参数:批次 am|pm(默认按当前时间判断)。
---

# ln-collect · 采集步骤

把多语种、多平台的新闻抓回来,统一成中文语料库条目。**早班(am)/晚班(pm)各跑一次。**

## 运行参数
- `batch`:`am` 或 `pm`(不传则按当前时间:< 12:00 视为 am,否则 pm)。
- `date`:默认今天(`config/loop.yaml` 的时区 Asia/Shanghai)。

## 步骤
1. 读 `config/loop.yaml`、`config/sources.yaml`、`config/people.yaml`。
2. 读策略提示词:`prompts/collect.consensus.md` 与 `prompts/collect.deep.md`,**严格按其规则执行**。
3. **共识类采集**:用 WebSearch 跑 `consensus.web_search_queries`;用 WebFetch 抓 `consensus.rss`。按 collect.consensus.md 强去重、多源合并。
4. **深度类采集**:按 `prompts/collect.deep.md` 的**实测来源梯子**执行,**必留 `original_quote` 原文**:
   - Substack/博客 RSS → ✅ 主力(WebFetch 全文)。
   - 名人原声 → **优先 X MCP,低成本模式**(详见 `prompts/collect.deep.md` 与 `config/loop.yaml` 的 `x_cost`):**仅在 `x_cost.collect_batches`(默认 am)批次**抓;优先 `search_tweets("from:handle", max_results=x_cost.per_person_max_tweets)`(省 $0.010 用户读);**只读不写**;按需缓存 `x_id`。X MCP 未连接(未配 `.env`)时退化为 WebSearch 还原引用。
   - HackerNews → ✅ Algolia API;Reddit → ❌ 被拦,只能用 WebSearch 限域取信号。
   - 任何来源抓取失败都写进本轮 metrics,不静默跳过。
5. **归一化**:每条转成下方 schema 的对象;`id` 用 url 的 sha1(无 url 用 标题+source 的 sha1)。
6. **去重**:读 `state/seen.json`(已见 id/指纹集合);丢弃已存在的;共识类还要按标题相似度合并同事件。
7. **写盘**:
   - 原始批次 → `data/raw/<date>-<batch>.json`(数组)。
   - 合并进当日语料 → `data/corpus/<date>.json`(数组,追加去重后的新条目)。
   - 更新实体索引 `data/entities/index.json`:`{ "实体名": [ {date, id, title_zh}, ... ] }`(供汇总做跨时间检索)。
   - 更新 `state/seen.json`、`state/metrics.json`(本轮:各来源产出条数、去重数、深/共识占比、X 抓取是否成功)。

## 语料库条目 schema(`data/corpus/<date>.json` 数组元素)
```json
{
  "id": "sha1(url)",
  "collected_at": "2026-06-30T07:00:00+08:00",
  "category": "consensus | deep",
  "source_type": "media | x | substack | reddit_hn",
  "source": "Reuters | @sama | Stratechery | r/LocalLLaMA",
  "lang": "en",
  "url": "https://...",
  "title_zh": "中文标题",
  "summary_zh": "中文摘要(2-4句)",
  "original_quote": "深度类必留的原文原话;共识类可为空字符串",
  "entities": ["OpenAI", "Sam Altman"],
  "topics": ["AI 监管", "算力"],
  "importance": 0.62,
  "consensus_count": 4,
  "insight_zh": "深度类:一句话说清为何值得注意;共识类可为空"
}
```

## 纪律
- 输出中文;深度类原文保真,**不臆造引文/链接**。
- 不把同一事件刷成多条;低于 `thresholds.importance_min` 丢弃。
- 失败的来源记进 metrics(供 ln-evolve 优化),不要静默跳过。
