---
name: ln-dossier
description: Loop News 领域专题。按 config/domains.yaml 的领域剧本,生成/更新一个产业级深度专题——该领域 KOL/KOC 在讲什么 + 历年数据变化 + 脉络 + 未来展望 + 周边产业 + 综合洞察,写入 data/dossiers/<id>.json,页面长出「📂 专题」。当用户说"生成专题"、"出个领域报告"、"ln-dossier"、"专题 <领域>"时使用;也由 ln-evolve 判断某领域成熟时调用。
---

# ln-dossier · 领域专题(产业纵深)

把一个**领域**做成持续追踪、越来越深的产业级深度报告。这是北极星「非显然洞察」的**领域纵深版**——单条新闻看不出、把一个领域的原声+历年数据+周边产业连起来才浮现。

## 参数
- `domain`:领域 id(如 `ai-regulation`)。无则在 `config/domains.yaml` 里挑 status=tracking/dossier 且素材最足的。

## 步骤
1. 读 `config/domains.yaml` 该领域的 **playbook**(`kol/koc`、`series`、`adjacent`、`angles`、`outlook_questions`)——这是该领域**独特的搜索方式**(由 ln-evolve 进化出)。
2. 按 playbook 搜集/更新素材(X MCP / web 搜索 / 抓取):
   - **KOL/KOC 原声**:`playbook.kol/koc` 最近在说什么(**留 `original_quote` 原文**)。
   - **历年数据**:`playbook.series` 的序列——**先查 ≥5 年、写入/更新 `data/series/<id>.json` 沉淀**(只补新点)。
   - **脉络**:该领域关键事件时间线(可复用 `data/threads.json` / corpus)。
   - **周边产业**:`playbook.adjacent` 的发展与对本领域的外溢。
3. 综合:按 `angles` 与 `outlook_questions` 产出 **未来展望**(分级预测 + 证据)与 **综合洞察**(事实/推断/预测)。**不臆造、回链证据**(corpus id 或 series id)。
4. 写盘:`data/dossiers/<domain>.json`(schema 见下);把该领域 `status` 置为 `dossier`;记 `prompts/CHANGELOG.md`。

## schema(`data/dossiers/<id>.json`,被 web/compile.py 渲染成「📂 专题」)
```json
{
  "id":"", "name":"", "updated":"YYYY-MM-DD", "summary_zh":"领域综述(可含 ==高亮==)",
  "kol_voices":[{"source":"@x","date":"","lang":"en","url":"","original_quote":"原文","summary_zh":""}],
  "data":[{"type":"line","title":"","series":"<id>","recent":6,"note":""}],
  "timeline":[{"date":"","note_zh":""}],
  "outlook":[{"text_zh":"","grade":"预测","confidence":0.4,"evidence":["id"]}],
  "adjacent":[{"name":"","note_zh":"","evidence":["id"]}],
  "conclusions":[{"text_zh":"","grade":"事实|推断|预测","confidence":0.8,"evidence":["id"]}],
  "methodology_note_zh":"本专题独特的搜索方式(随关注与新料进化)"
}
```

## 纪律
- 遵守 [GOALS.md](../../../GOALS.md) 北极星与**不臆造**硬约束;数字出图**先查史沉淀**(见 synthesize.method.md「图表」);深度类**保留原文**。
- 专题是**持续追踪**:已有就增量更新(补新原声/新数据点/新脉络),不推倒重来。
