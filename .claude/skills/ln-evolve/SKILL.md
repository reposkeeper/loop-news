---
name: ln-evolve
description: Loop News 自我进化步骤。读质量指标 state/metrics.json + 抽样产物,找出采集/分析的弱点,自动改进 prompts/*.md 与 config/*.yaml,并把改动记入 prompts/CHANGELOG.md(可回看可回滚)。每天早上跑一次。当用户说"进化"、"自我改进"、"evolve"、"ln-evolve"、"优化提示词"时使用。
---

# ln-evolve · 自我进化步骤

让系统越跑越聪明:每轮自评,改进自己的提示词与配置。**每天早上「在采集之后、汇总之前」第一步跑**——把所有待处理反馈/问题修复掉,**进化完成后才生成当天总结页**。

> **北极星(见 [GOALS.md](../../../GOALS.md)):最大化「非显然洞察」。** 每轮以提升 `non_obvious / edge / cross_date / falsifiable`(质量优先,见 metrics)为首要目标;人类反馈用于**校准"什么算洞察"**(`采用` 是旁证,非靶心);并**主动压制 over-reach**——发现"聪明但无据"的结论模式就收紧证据/分级要求。冲突时:北极星 > 子目标 > 顺手优化。

## 步骤
1. **读人类反馈(Human-in-the-loop,最高优先)**:
   - **弹窗反馈**:`bash scripts/feedback.sh`(读 `data/feedback.jsonl` 或线上 `curl <api>/feedback`:`up 赞 / down 踩 / adopt 采用 / ask 全局提问` + 常用词 `tags` + 自定义 `text`)。
     - **`ask`(站长全局提问)= 最高优先**:当作本轮**必须落实**的指令(它是站长对整站的方向性要求)。
     - **`adopt 采用`**:说明该条被用进自媒体,据此加权对应来源/主题(校准"什么算有洞察")。
   - **本轮必须把待处理反馈清空**(尤其 `ask`),处理不完也要给出最简处置并记 CHANGELOG,不积压到下一天。
   - **本地**:若存在 `feedback.md`,一并读取(自然语言反馈)。
   - 反馈**优先于**机器自评:用户明确说的(某来源是噪音、某类结论没用、想多看某主题)直接据此改。
2. **读指标 + 系统分数**:`state/metrics.json` 最近若干轮(采集条数、去重率、深/共识占比、结论数、**各来源有效产出 vs 噪音**、X 抓取成功率、各透镜命中数、线索数);并读 `state/scores.json` 的四个分数(关联度/数量/分析整合/自进化广度 + 综合)与 delta。**本轮改进优先针对最低 / 较上轮下滑的那个分数**(数量低→补源加角度;关联低→强化跨日期/跨域透镜;分析低→严证据分级;广度低→加领域/角度),改完再跑 `python3 scripts/score.py` 确认回升。评分制度见 [prompts/scoring.md](../../../prompts/scoring.md)。
3. **抽样产物**:看最近几期 `data/analysis/*.json`,评估:结论是否有证据回链?是否够"非显然"?深度类原文是否保真?共识去重是否干净?
4. **诊断弱点**(**先看北极星**),例如:
   - **采集量不足 / 欠采(高优先)**:`collected` < `config/loop.yaml` 的 `collect.volume_floor`,或 metrics 有 `under_collected`,或用户反馈"新闻太少" → **优先修**:在 `config/sources.yaml` 加检索角度 / RSS / 中文平台,broaden `web_search_queries`,把每轮量拉到 `volume_target`(采集层高召回,见 [GOALS](../../../GOALS.md)「采集广度」)。没料就没洞察,欠采是失职。
   - **信息源固化(第 5 分,每轮必评)**:读 `data/source_quality.json` + 各源本轮产出(被展示 / 被采用 / 贡献非显然结论 vs 噪音 / 重复 / 无产)→ **升级**持续优质的源(trial→core『固化』、上调 quality)、**降级/淘汰**噪音源(core→watch→demoted,并在 `sources.yaml`/`people.yaml` 落地移除或标 `priority: low`);**更新 `last_curation` 为当日**——不评选则第 5 分随天数衰减(惩罚),以此强迫每轮都评选来源。评选口径见 [prompts/scoring.md](../../../prompts/scoring.md)。
   - **及时性(第 6 分)偏低**(旧闻多 / 漏采后补 / `stale_gt4d` 高)→ **强惩罚已触发,优先修**:给 `sources.yaml` 补**实时性高的一手快讯源**、给 `source_quality.json` 的源标 `recency: realtime/fast/slow`、把慢速回顾源降权;要求采集端只采当日/昨日、剔除一周前综述;对反复漏采的重大线索,提示晚班也采、下轮开头补当日大新闻——**堵住"当时没采、次日过期补"**。口径见 [prompts/scoring.md](../../../prompts/scoring.md)。
   - **北极星未上行**(`non_obvious`/`edge` 停滞或靠堆量)→ 强化 `prompts/synthesize.method.md` 的非显然/跨域/共识缺口要求;或在 `config` 增"能制造分歧信号"的来源(更多圈内原声以对照主流)。
   - **出现 over-reach**(无据/过度引申的"洞察")→ 收紧 `synthesize.method.md` 的证据回链与分级门槛,宁缺毋滥。
   - **领域自进化(产业纵深)**:从 `/follows`(关注)+ `data/threads.json` + 反复出现的实体识别**成熟领域**;在 `config/domains.yaml` 新建/细化其剧本(KOL/KOC、要追的历年数据 `series`、周边产业、独特搜索角度);某领域够深就**调用 `ln-dossier <id>` 生成/更新专题**(决定是否「在页面长出专题」);长期无料的领域标 `dormant`。**专题质量进化**:读各专题的 `quality_self_eval`(depth/sourcing/balance/data_grounded/non_obvious/anti_sensational),对反复偏低的维度**编辑 `prompts/dossier.method.md`**(加规则 / 换角度 / 调结构)——让专题越来越像严肃深度报道、越来越不像自媒体危言耸听。这是"专题 skill 不断进化"的落点。
   - 某来源连续多轮全是重复/噪音 → 在 `config/sources.yaml` 降权或移除。
   - 深度结论太浅 → 强化 `prompts/synthesize.method.md` 的某个透镜要求。
   - 共识漏报某领域 / 用户想多看某主题 → 在 `config/sources.yaml` 增 query/RSS,或 `config/people.yaml` 增人。
   - X 抓取持续失败 → 调整 `prompts/collect.deep.md` 的退化策略。
   - **进化常用反馈词**:据 `feedback.jsonl` 里 `tags` 的使用频次,增删 `config/feedback_tags.json`(高频保留、补充用户在 `text` 里反复出现的新表述、删僵尸词)。
5. **落地改动**:直接编辑相应 `prompts/*.md` / `config/*.yaml` / `config/feedback_tags.json`。**一次只改少量、有依据的点**,避免大改导致不可控。
6. **记日志**:在 `prompts/CHANGELOG.md` 顶部追加一条:日期 · 改了什么 · 为什么(**引用具体反馈条目 / 指标 / 样本**) · 如何回滚。
7. **闭环留痕**:弹窗反馈无 issue 可关;在 CHANGELOG 标注本轮已消化到 `feedback.jsonl` 的哪个时间点,避免下轮重复计入。**并向 `data/feedback_ledger.json` 追加本轮 cycle**(`date` / `changelog` / `covered:[{type,text,how}]`)——网页「📋 反馈台账」据此显示每条反馈在哪一轮被覆盖。
8. **变更落地自检**:跑 `bash scripts/check.sh` 必须通过——确认本轮所有改动已落进【代码】或【skill/提示词/文档】、且已记 `prompts/CHANGELOG.md`(契约见 [RUNBOOK](../../../RUNBOOK.md)「变更落地契约」)。不通过先修再继续。

## 纪律
- 改动必须**有数据/样本支撑**,不凭感觉。
- 保守迭代:每轮改动可被 git revert + CHANGELOG 回滚。
- 不删历史数据;不动 schema(改 schema 属于人工大版本,不归自动进化)。
- 若本轮指标健康、无明显弱点,可"无改动",在 CHANGELOG 记一句"本轮稳定,无改动"。
