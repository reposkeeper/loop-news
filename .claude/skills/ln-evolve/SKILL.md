---
name: ln-evolve
description: Loop News 自我进化步骤。读质量指标 state/metrics.json + 抽样产物,找出采集/分析的弱点,自动改进 prompts/*.md 与 config/*.yaml,并把改动记入 prompts/CHANGELOG.md(可回看可回滚)。每天早上跑一次。当用户说"进化"、"自我改进"、"evolve"、"ln-evolve"、"优化提示词"时使用。
---

# ln-evolve · 自我进化步骤

让系统越跑越聪明:每轮循环后自评,改进自己的提示词与配置。**每天早上跑一次(在发布之后)。**

## 步骤
1. **读人类反馈(Human-in-the-loop,最高优先)**:
   - **弹窗反馈**:`bash scripts/feedback.sh`(读 `data/feedback.jsonl`:网页弹窗提交的 `up 赞 / down 踩 / adopt 采用` + 常用词 `tags` + 自定义 `text`)。**「采用(adopt)」信号最重**——说明该条被用进自媒体,应据此加权对应来源/主题/作者。
   - **本地**:若存在 `feedback.md`,一并读取(自然语言反馈)。
   - 反馈**优先于**机器自评:用户明确说的(某来源是噪音、某类结论没用、想多看某主题)直接据此改。
2. **读指标**:`state/metrics.json` 最近若干轮(采集条数、去重率、深/共识占比、结论数、**各来源有效产出 vs 噪音**、X 抓取成功率、各透镜命中数、线索数)。
3. **抽样产物**:看最近几期 `data/analysis/*.json`,评估:结论是否有证据回链?是否够"非显然"?深度类原文是否保真?共识去重是否干净?
4. **诊断弱点**,例如:
   - 某来源连续多轮全是重复/噪音 → 在 `config/sources.yaml` 降权或移除。
   - 深度结论太浅 → 强化 `prompts/synthesize.method.md` 的某个透镜要求。
   - 共识漏报某领域 / 用户想多看某主题 → 在 `config/sources.yaml` 增 query/RSS,或 `config/people.yaml` 增人。
   - X 抓取持续失败 → 调整 `prompts/collect.deep.md` 的退化策略。
   - **进化常用反馈词**:据 `feedback.jsonl` 里 `tags` 的使用频次,增删 `config/feedback_tags.json`(高频保留、补充用户在 `text` 里反复出现的新表述、删僵尸词)。
5. **落地改动**:直接编辑相应 `prompts/*.md` / `config/*.yaml` / `config/feedback_tags.json`。**一次只改少量、有依据的点**,避免大改导致不可控。
6. **记日志**:在 `prompts/CHANGELOG.md` 顶部追加一条:日期 · 改了什么 · 为什么(**引用具体反馈条目 / 指标 / 样本**) · 如何回滚。
7. **闭环留痕**:弹窗反馈无 issue 可关;在 CHANGELOG 标注本轮已消化到 `feedback.jsonl` 的哪个时间点,避免下轮重复计入。

## 纪律
- 改动必须**有数据/样本支撑**,不凭感觉。
- 保守迭代:每轮改动可被 git revert + CHANGELOG 回滚。
- 不删历史数据;不动 schema(改 schema 属于人工大版本,不归自动进化)。
- 若本轮指标健康、无明显弱点,可"无改动",在 CHANGELOG 记一句"本轮稳定,无改动"。
