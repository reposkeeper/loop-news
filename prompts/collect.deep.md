# 采集策略 · 深度类(deep)

> 本文件由 `ln-collect` 在运行时读取,由 `ln-evolve` 自动演进。改动须记入 `prompts/CHANGELOG.md`。

## 目标
抓取**深层次内容**:不在大众关注范畴、但能引发共鸣与思考的内容。这类思考往往只存在于特定圈子
(AI 领域、经济领域的名人)。**核心诉求:听到原汁原味的话语。**

> **写法对标严肃媒体**:原声要归属清楚、优先在录/一手、正反都要听(不只捧场方);翻译呈现中文但**保留 `original_quote` 原文**,不夸张不断章取义。房规见 [dossier.method.md 第三节](dossier.method.md)。

## 采集量(高召回)
深度类也要**够量**:除名人原声外,主动搜"圈内在吵什么"——AI 争议 / 安全事件 / 一手技术分析(如今日 Claude Code『中国指纹』这类会引爆圈层的),纳入 `collect.volume_target` 的总盘。宁多勿漏,呈现层再萃取(见 [GOALS](../GOALS.md)「采集广度」)。

## 抓取来源(按优先级 + 本环境实测可行性,2026-06)
1. **深度长文 / 独立观点** `deep.substack_rss`:✅ WebFetch 抓 RSS + 全文可用,**深度类主力**。提炼核心论点,保留代表性原句。
2. **名人原声** `config/people.yaml`:**优先用 X MCP**(已装,见 [RUNBOOK](../RUNBOOK.md) / `scripts/setup-mcp.sh`)。
   - **a. X MCP(首选,低成本模式)**:严格按 `config/loop.yaml` 的 `x_cost` 执行(X API 按返回资源计费):
     - **只在 `x_cost.collect_batches`(默认 `am`)批次抓 X**;晚班跳过 X,只用免费来源。
     - **优先 `search_tweets`**:对每位 handle 用 `search_tweets(query="from:<handle>", max_results=x_cost.per_person_max_tweets)` 直接取最近推文 —— 仅按推文计费($0.005/条),**不产生 $0.010 的用户读**;原文填 `original_quote`。
     - 仅当确需时间线特性时才用 `get_user`+`get_timeline`,并把解析到的 `user_id` **回写 `people.yaml` 的 `x_id`** 缓存,避免下次重复 `get_user`。
     - **绝不调用写接口**(post/reply/like/retweet)。同一 UTC 日内同推文重复抓只收一次费,早晚班不必担心重复扣。
     - 前提:`.env` 配好 X 凭证、`x` server 已连接。
   - **b. WebSearch 还原引用(回退)**:X MCP 不可用时,搜「<人名> said / 表态 + 主题」→ WebFetch 文章 → 提取直接引用(注明经文章转引)。
   - **c. 官方渠道**:本人博客 / 公司 newsletter / 采访稿(如 Anthropic、OpenAI 博客),抓原文。
3. **圈层讨论**:
   - **HackerNews** `deep.hackernews`:✅ 用 Algolia API `https://hn.algolia.com/api/v1/search?tags=front_page` 抓,作为科技圈信号。
   - **Reddit** `deep.reddit`:❌ WebFetch 拦截 reddit 全站。退化:WebSearch 限定 `reddit.com` 域找到热帖标题/讨论方向,用于交叉验证(拿不到全文,只作信号)。

## 判定标准(什么算"深度")
- **非共识**:主流媒体还没大规模报道,或主流叙事之外的视角。
- **有洞察**:提供了新框架、反直觉判断、第一手数据或亲历经验。
- **能引发思考**:即使只在小圈子,也具备启发性。

## 处理规则(与共识类的关键差异)
- **弱去重**:独立声音本就稀缺,不同人对同一话题的不同观点**都要保留**,不要合并。
- **必留原文** `original_quote`:保留发言人最具代表性的**原话原文**(原语种),这是"原汁原味"的硬要求。配 `title_zh` / `summary_zh` 中文。
- **标注洞察** `insight_zh`:一句话说清"为什么这条值得注意 / 它挑战了什么共识"。
- **署名** `source`:写清是谁说的(如 `@sama`、`Stratechery`、`r/LocalLLaMA`)。
- **重要性** `importance`:深度类按"洞察密度"而非"传播广度"打分。

## 反模式(避免)
- 不要把原话改写成平庸转述而丢掉锋芒;原文必须保真。
- 不要只收已经全网刷屏的内容(那是共识类的活)。
- 不臆造引文;`original_quote` 必须是真实存在、可回溯的原话。

## 输出
按 `data/corpus` 条目 schema 输出,`category: "deep"`,必填 `original_quote`。见 `.claude/skills/ln-collect/SKILL.md`。
