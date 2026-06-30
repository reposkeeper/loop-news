---
name: ln-synthesize
description: Loop News 汇总分析步骤。加载前一天语料 + 相关历史,套用八个方法论透镜挖掘新闻间深层关联,产出分级结论(事实/推断/预测,带证据回链),写入 data/analysis/DATE.json。每天早上跑一次。当用户说"汇总"、"分析新闻"、"synthesize"、"ln-synthesize"、"出今天的结论"时使用。
---

# ln-synthesize · 汇总分析步骤

把零散新闻连成关系网,得出"看单条得不出、连起来才浮现"的有价值结论。**每天早上跑一次,汇总前一天。**

> **北极星(见 [GOALS.md](../../../GOALS.md)):最大化「非显然洞察」。** 优先且尽量多产跨时间/跨域、可证伪、言之有据的深层判断;但每条必须回链证据+分级,**无据不出(防 over-reach)**。

## 运行参数
- `date`:被汇总的日期,默认**昨天**(Asia/Shanghai)。

## 步骤
1. 读方法论 `prompts/synthesize.method.md`,**严格按其八透镜与产出要求执行**。
2. **加载输入**:
   - 当日新增:`data/corpus/<date>.json`(昨天采集的全部条目)。
   - 相关历史:用 `data/entities/index.json` 按实体/话题,从更早的 `data/corpus/*.json` 检索出相关旧条目(跨时间关联的素材)。
3. **逐透镜分析**:对素材依次套用 8 个透镜(时间线追踪、二阶效应、共识缺口、跨域模式、跟着钱走、矛盾检测、沉默信号、主体网络)。适用才产出。
4. **筛选呈现**:按 `config/loop.yaml` 的 `output.*` 上限,挑出要进网页的共识条目、深度条目、关联、结论。
   - **关联与结论的 `evidence` 可跨日期**:既能引用今天的条目 id,也能引用历史条目 id(编译时会自动链到那一天)。
5. **维护跨日期线索 `data/threads.json`**:这是"话题/实体线索时间线"的数据源。
   - 对识别出的**跨多天**主题/主体(如"AI 监管"、"OpenAI"),把今天的相关条目**接到已有线索的 `timeline`** 上;没有就新建一条 thread。
   - 每条 thread 必须真正**跨日期**(timeline 含 ≥2 个不同日期),否则不要建(单日的放当天 `connections` 即可)。
   - 更新 `summary_zh` / `status_zh` 反映最新进展。线索条目的 `item_id` 必须能在某天 corpus 里找到(可回溯)。
6. **写盘**:`data/analysis/<date>.json`(schema 见下)+ `data/threads.json`;更新 `state/metrics.json`(结论数、各透镜命中数、线索数,以及**北极星指标 `non_obvious / edge / cross_date / falsifiable`**,定义见 [GOALS.md](../../../GOALS.md))。

## 分析产物 schema(`data/analysis/<date>.json`)—— 被 web/compile.py 消费
```json
{
  "date": "2026-06-29",
  "generated_at": "2026-06-30T07:05:00+08:00",
  "summary_zh": "当日总览,2-4 句:今天最值得记住的是什么。",
  "consensus": [
    { "title_zh": "...", "summary_zh": "...", "sources": ["Reuters","AP"],
      "consensus_count": 5, "url": "https://...", "topics": ["..."], "id": "...",
      "charts": [{ "type":"bar|line|pie", "title":"", "unit":"%", "source":"", "note":"据报道生成,仅供参考", "data":[{"label":"","value":0}] }] }
  ],
  "deep": [
    { "title_zh": "...", "summary_zh": "...", "source": "@sama", "lang": "en",
      "original_quote": "原文原话...", "url": "https://...",
      "insight_zh": "为什么值得注意", "id": "..." }
  ],
  "connections": [
    { "lens": "时间线追踪", "title_zh": "...", "narrative_zh": "把几条连成一件事的叙事",
      "evidence": ["id1","id2"] }
  ],
  "conclusions": [
    { "text_zh": "结论正文", "grade": "事实 | 推断 | 预测",
      "confidence": 0.7, "evidence": ["id1","id2"] }
  ],
  "methodology_note_zh": "本期主要用了哪些透镜、为何"
}
```

## 跨日期线索 schema(`data/threads.json`)—— 被 web/compile.py 渲染成"线索时间线"
```json
{
  "generated_at": "2026-06-30T07:30:00+08:00",
  "threads": [
    {
      "id": "thread-ai-regulation",
      "title_zh": "线索标题",
      "key_entities": ["AI 监管", "..."],
      "summary_zh": "这条线索在讲什么、进展到哪",
      "status_zh": "进行中 · 简短状态",
      "timeline": [
        { "date": "2026-06-04", "item_id": "co0604-...", "title_zh": "...", "note_zh": "这步是什么" },
        { "date": "2026-06-30", "item_id": "co-...",     "title_zh": "...", "note_zh": "这步是什么" }
      ]
    }
  ]
}
```

## 纪律(来自 synthesize.method.md)
- 事实/推断/预测严格分级;**无证据不出结论**;不确定就降置信度或不写。
- 所有 `evidence` 必须能在 corpus 里按 id 追回原始新闻。
- 优先输出非显然的、跨时间/跨域的判断。
