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

## 关注议程(持续追踪 —— 来自网页「+ 关注」)
用户在网页「+ 关注」过的新闻,经反馈服务聚合成**追踪话题/实体**。**每轮采集先拉取**:线上 `curl "<feedback.api_url>/follows"`(取 `topics`/`entities` 聚合),把它们并入本轮搜索议程,**主动搜这些话题的最新进展**(共识与深度都查),而不是等它们偶然出现。
- 某关注话题**连续多轮无新内容** → 在 `state/metrics.json` 标 `stale`、降优先;**确实长期无更新才停**(对应用户「除非确实没有更新的内容」)。
- 这让系统对用户在意的线索保持跟进,正是北极星「跨时间洞察」的素材来源。
- 对 `config/domains.yaml` 里 `status=tracking/dossier` 的领域,按其 `playbook`(angles/kol/adjacent)跑**领域专属搜索**(原声 / 历年数据 / 周边产业),为 `ln-dossier` 攒料。
- **用户请求的新闻类型**:`curl "<feedback.api_url>/requests"`(任意用户用网页「➕ 想看的话题」提交的 `text`/`tags`)→ **并入本轮搜索议程、优先采相关内容**;首次响应后在 `state/metrics.json` 记已响应,避免每轮重复全量采(持续追踪转入关注/领域机制)。

## 🎙️ 播客采集(知名主持 × 知名 AI 人物)
读 `config/podcasts.yaml`(节目 RSS/主页 + `key_guests`)。**每轮找这些节目的最新几集**(优先 RSS,WebFetch 抓 feed;或 WebSearch「<节目/主持> <AI 人物> podcast」),命中 `key_guests`(一线 AI 决策者/研究者)的**整集深访**即收入:
- 抓:`show` / `host` / `guest`(+ `guest_title`)/ 标题 / `url` / 发布日;写**中文** `summary_zh` + **3–5 个** `key_points_zh` + 一句**代表原话** `quote`(英文保真,不臆造/不断章)。
- 归一化为 corpus 条目(`category: "podcast"` + 上述字段);`ln-synthesize` 择近期/重磅者放进当日 `analysis.podcasts`(网页「🎙️ 播客」区)。
- 只收整集深访,不收剪辑/资讯口播;拿不到内容不硬凑。

## 更多 AI(反馈:AI 内容太少)+ 即刻
- **AI 权重上调**:`config/sources.yaml` 已加 AI 专项 query/RSS 与请求话题(企业 AI/harness、机器人具身融资、AI 安全/前沿模型);本轮**优先保证 AI 类产出量**。
- **`config/people.yaml` 的 `priority: low`**(ylecun/DrJimFan/paulkrugman/RayDalio):**少抓或跳过**(metrics 显示多口水/格言/无实质),配额让给高信号 AI 声音与新嘉宾。
- **即刻 Jike**(`sources.cn_platforms`):WebSearch 限定 `okjike.com` 找公开 AI 热帖/圈子方向,顺到一手链接再 WebFetch;抓不到只作信号,不臆造。

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
  "published": "2026-06-30",
  "first_seen": "2026-06-30",
  "insight_zh": "深度类:一句话说清为何值得注意;共识类可为空"
}
```
- **`published`(事件发生日,YYYY-MM-DD,必填)**:据实取报道/官方稿的事件日期,不是采集日、不是文章 SEO 日期。**及时性分(第 6 分)据此算**——不标 = 无法主张及时、拉低分数。
- **`first_seen`(首次采到日)**:本条首次进 corpus 的日期(通常=今天)。用于识别"漏采后补"。

## 及时性(第 6 分,强惩罚)—— 新闻必须实时,漏采要罚
制度见 [prompts/scoring.md](../../../prompts/scoring.md)。采集时:
- **优先当日/昨日一手快讯**:`lateness = 采集日 − published`,超过 `fresh_days`(4 天)即判 `stale`;**一天里多条 stale → 及时性分用 0.78ⁿ 强惩罚,几条就大跌**。别用一周前的综述/回顾页充数。
- **来源要实时**:优先 `source_quality.json` 里 `recency: realtime/fast` 的源(快讯/官方稿/当日报道);`slow`(回顾/分析)源采到的旧闻会计入 stale。
- **堵漏采**:重大事件当天没采到、次日才补 = 漏采后补(`lateness` 大),同样扣分。**晚班也认真采**、下轮开头补齐上轮漏的当日大新闻,别把"当时没采"拖成"过期补"。
- 深度/播客类时效性弱,但也标 `published`;及时性分只对 `consensus/deep` 算。

## 纪律
- 输出中文;深度类原文保真,**不臆造引文/链接**。
- 不把同一事件刷成多条;低于 `thresholds.importance_min` 丢弃。
- **每条必标 `published`(据实)**;旧闻/漏采后补会被及时性分惩罚,别为凑数塞过期新闻。
- 失败的来源记进 metrics(供 ln-evolve 优化),不要静默跳过。
