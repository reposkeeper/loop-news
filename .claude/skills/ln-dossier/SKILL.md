---
name: ln-dossier
description: Loop News 领域专题。把一个产业级议题做成一篇真正的深度报道(不是新闻聚合)——一手资料 + 多年数据 + 多方在录原声 + 分级分析,写成结构化文章存入 data/dossiers/<id>.json,页面长出「📂 专题」。严肃新闻体、反自媒体危言耸听;方法论见 prompts/dossier.method.md(由 ln-evolve 持续打磨)。当用户说"生成专题"、"出个领域深度报道"、"ln-dossier"、"专题 <领域>"时使用;也由 ln-evolve 判断某领域成熟时调用。
---

# ln-dossier · 领域专题(深度报道)

把一个**领域议题**做成**一篇真正的深度报道**:综合一手资料、多年数据、各方在录原声与独立分析,给出有据、分级、可证伪的判断。**不是新闻聚合**;严肃新闻体、反危言耸听。这是北极星「非显然洞察」的领域纵深版。

> **动笔前必读 [prompts/dossier.method.md](../../../prompts/dossier.method.md)——文章结构、研究深度、严肃媒体写法、反煽动硬约束、自评口径都在那。本 skill 保持稳定,方法/风格由那份文件持续进化(ln-evolve 编辑)。**

## 参数
- `domain`:领域 id(如 `ai-regulation`)。无则在 `config/domains.yaml` 里挑 `status=tracking/dossier` 且素材最足的。

## 步骤
1. **读方法与剧本**:先读 `prompts/dossier.method.md`;再读 `config/domains.yaml` 该领域 **playbook**(`kol/koc`、`series`、`adjacent`、`angles`、`outlook_questions`、`primary_sources`、`opposing_voices`)——该领域独特的深挖方式(由 ln-evolve 进化)。
2. **深挖备料(动笔前把料备足,见 method 第五节)**:
   - **一手文件**:法案/官方公告/财报/申报/数据集——WebFetch 直接读,记一手 `url`。
   - **多年数据**:`playbook.series` 的每条序列**查 ≥5 年、写入/更新 `data/series/<id>.json` 沉淀**(只补新点),供图表。
   - **多元在录原声(≥3,立场不同,含 ≥1 反对/质疑方)**:主推方 / 反对·批评方 / 独立专家 / 官方。X MCP(低成本,留 `original_quote` 原文)+ 严肃媒体在录引述。
   - **交叉印证**:关键事实 ≥2 个独立来源;冲突就如实呈现张力。
   - **脉络 + 周边**:复用 `data/threads.json`/corpus 补时间线;`playbook.adjacent` 的外溢。
3. **写成文章(见 method 第四节的 `sections` 骨架)**:核心判断 lede → 背景脉络 → 数据透视(讲清数字说明/没说明什么)→ 各方立场(多方 steelman)→ 深度分析(分级结论 + 证据回链)→ 反方与不确定 → 后续看点 → 方法与来源。**每个事实回链来源;事实/推断/预测分档;不煽动、能量化就量化。**
4. **自评**:按 method 第七节给 `quality_self_eval` 打分(depth/sourcing/balance/data_grounded/non_obvious/anti_sensational),低分写 `notes`;同时把本轮情况记进 `state/metrics.json`(供 ln-evolve 进化 dossier.method.md 与 playbook)。
5. **写盘**:`data/dossiers/<domain>.json`(schema 见下);该领域 `status` 置 `dossier`;推进 `updated`(触发红点);记 `prompts/CHANGELOG.md`。**已有专题就增量更新**(补新数据点/新声音/新一手文件),不推倒重来。

## schema(`data/dossiers/<id>.json`,被 web/compile.py 渲染成文章式「📂 专题」)
```json
{
  "id": "ai-regulation",
  "name": "AI 监管",
  "title_zh": "报道标题(具体、不标题党)",
  "dek_zh": "一句话核心判断(副标题)",
  "updated": "YYYY-MM-DD",
  "status": "dossier",
  "lede_zh": "核心判断段落(1–2 段,此刻发生什么+为何重要+主线,带来源)",
  "sections": [
    { "heading_zh": "背景与脉络", "kind": "context", "body_zh": "把时间线织入分析(可含 ≤2 处 ==高亮==)", "evidence": ["corpus-id"] },
    { "heading_zh": "数据透视", "kind": "data", "body_zh": "数字显示了什么/没显示什么/口径与局限",
      "charts": [{ "type": "line", "title": "", "series": "<series-id>", "recent": 6, "unit": "", "source": "", "note": "" }], "evidence": [] },
    { "heading_zh": "各方立场", "kind": "voices", "body_zh": "导语",
      "voices": [{ "who": "", "role": "主推|反对|独立专家|官方", "stance_zh": "该方最强表述", "quote": "原话(深度保真)", "lang": "en", "source": "", "url": "" }], "evidence": [] },
    { "heading_zh": "深度分析", "kind": "analysis", "body_zh": "主线:把事实/数据/立场连成判断", "evidence": [] }
  ],
  "conclusions": [{ "grade": "事实|推断|预测", "text_zh": "", "confidence": 0.8, "evidence": ["id"] }],
  "counterpoints_zh": ["最强反方论证 / 还不知道什么 / 什么会推翻当前判断"],
  "watch_zh": ["具体、可证伪的后续路标(到某日或某指标到某值回看)"],
  "sources": [{ "name": "", "url": "", "kind": "primary|media|data|expert" }],
  "methodology_note_zh": "如何研究、数据出处、局限",
  "quality_self_eval": { "depth": 0.0, "sourcing": 0.0, "balance": 0.0, "data_grounded": 0.0, "non_obvious": 0.0, "anti_sensational": 0.0, "notes": "" }
}
```
> 兼容:旧字段(`summary_zh/kol_voices/data/timeline/outlook/adjacent`)仍可被渲染,但新专题一律用上面的文章式结构。

## 纪律
- 遵守 [GOALS.md](../../../GOALS.md) 北极星 + **不臆造 / 分级 / 不煽动 / 给反方 / 一手优先**(method 第二节硬约束)。
- 数字出图**先查史沉淀**(≥5 年,见 dossier.method + synthesize.method「图表」);深度类**保留原文**。
- 专题是**持续追踪**:增量更新,`updated` 每动一次都要有新增有据内容。
