# Loop News · 事实新闻驱动的新闻汇总中心

一个**自循环、可自我进化**的新闻情报系统。它持续从多语种、多平台采集新闻,沉淀成长期语料库,
每天用方法论挖掘**不同时间新闻之间的深层关联**,产出**有价值的结论**,再编译成纯静态网页发布到
GitHub Pages。系统还会自评质量、自动改进自己的采集提示词与分析方法论,**越跑越聪明**。

🌐 站点:https://reposkeeper.github.io/loop-news/

## 两类新闻
- **共识类(consensus)**:各大媒体都在报道的、最新的 Breaking News —— 求"快"和"广"。
- **深度类(deep)**:不在大众视野、但能引发圈层共鸣的原声(AI/经济圈名人第一手发言)—— 求"原汁原味",保留原文。

采集跨语种,**最终一律中文呈现**(深度类同时保留原文引用)。

## 循环(每天)
```
早班 07:00  采集(早) → 汇总前一天 → 编译 → 发布 → 自我进化
晚班 19:00  仅采集(晚)
```

## 五个步骤(均为 .claude/skills 下的 skill)
| Skill | 作用 | 类型 |
|---|---|---|
| `ln-collect`    | 四类来源采集 → 中文化 → 去重入库 `data/corpus` | LLM |
| `ln-synthesize` | 跨时间关联 + 八方法论 → 分级结论 `data/analysis` | LLM |
| `ln-compile`    | `data/analysis` 套模板 → `docs/*.html` | 脚本 |
| `ln-publish`    | 提交并推到 GitHub Pages | 脚本 |
| `ln-evolve`     | 自评 → 改 `prompts/*.md` → 写 CHANGELOG | LLM |

## 目录
```
config/    运行配置、来源清单、追踪名人
prompts/   ★ 会被自动进化编辑的提示词与方法论 + CHANGELOG(进化轨迹)
.claude/skills/  五个步骤
data/      raw 原始批次 / corpus 语料库(长期记忆) / entities 实体索引 / analysis 每日产物
web/       templates 模板 / assets 样式 / compile.py 小编译系统
docs/      ★ GitHub Pages 托管目录(编译输出)
state/     seen 去重索引 / metrics 质量指标
scripts/   publish.sh
```

## 手动跑一轮
```bash
# 采集(在 Claude Code 里):/ln-collect am
# 汇总:               /ln-synthesize 2026-06-29
python3 web/compile.py 2026-06-29     # 编译
bash scripts/publish.sh               # 发布
# 进化:               /ln-evolve
```

## 设计要点
- 提示词/方法论**外置成文件**,进化步骤直接编辑它们 → git history + `prompts/CHANGELOG.md` 即进化轨迹,可回看可回滚。
- 结论强制 `事实 / 推断 / 预测` 分级 + **证据回链**,防臆造。
- 共识类强去重(体现"N 家在报"),深度类弱去重 + 必留原文。
