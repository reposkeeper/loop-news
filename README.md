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
RUNBOOK.md AGENTS.md  ★ agent 中立操作手册(Claude/Codex 通用)
CLAUDE.md            Claude 视角补充约定
config/    运行配置、来源清单、追踪名人
prompts/   ★ 会被自动进化编辑的提示词与方法论 + CHANGELOG(进化轨迹)
.claude/skills/  五个步骤(薄封装)
data/      raw 原始批次 / corpus 语料库(长期记忆) / entities 实体索引
           analysis 每日产物 / threads.json 跨日期线索
web/       templates 单页模板 / assets 样式 / compile.py 小编译系统
docs/      ★ GitHub Pages 托管目录(唯一 index.html 单页)
state/     seen 去重索引 / metrics 质量指标
scripts/   publish.sh 发布 / feedback.sh 读人类反馈
feedback.md          本地反馈箱(另可在网站点 👍/👎)
```

## 网站(单页)
`docs/index.html` 一个文件搞定:**左侧日期列表 + 🧵 线索时间线入口**,右侧主区,点击在同页内切换(hash 路由,无 iframe)。
线索时间线把同一主题/主体**跨多天串成一条线**;每条新闻/结论旁有 👍/👎,点击预填 GitHub feedback issue。

## 反馈驱动自进化(Human-in-the-loop)
两条反馈通道,`ln-evolve` 每轮先读再改进:① 网站 👍/👎 → GitHub `feedback` issue;② 本地 `feedback.md`。
改完会在 `prompts/CHANGELOG.md` 记录,并回帖关闭对应 issue —— 你能看到反馈真的生效。

## X MCP(名人原声直采)
深度类的 X 原声优先走 **X MCP**(已装,Infatoshi x-mcp)。启用三步:
```bash
bash scripts/setup-mcp.sh        # 构建到 vendor/x-mcp(不入库)
cp .env.example .env             # 填 3 个真实 key(API Key/Secret + Bearer,读取够用),另 2 个留占位
set -a; source .env; set +a      # 让 .mcp.json 的 ${X_*} 占位生效,再启动
```
`.mcp.json` 已配名为 `x` 的 server;读工具 `search_tweets` / `get_timeline` / `get_user`。未配凭证时自动退化为 WebSearch 还原引用。其他 agent(Codex)按 [AGENTS.md](AGENTS.md) 指向同一 server。

## 手动跑一轮
```bash
# 采集(LLM 步骤):/ln-collect am
# 汇总(汇总昨天):/ln-synthesize
python3 web/compile.py        # 编译成单页 docs/index.html
# 本地预览确认后:
bash scripts/publish.sh       # 发布上线
/ln-evolve                    # 读反馈 + 自评,改进 prompts/config
```
> 其他 agent(如 Codex)照 [RUNBOOK.md](RUNBOOK.md) 跑,等价、不依赖 Claude 专有工具。

## 设计要点
- 提示词/方法论**外置成文件**,进化步骤直接编辑它们 → git history + `prompts/CHANGELOG.md` 即进化轨迹,可回看可回滚。
- 结论强制 `事实 / 推断 / 预测` 分级 + **证据回链**,防臆造。
- 共识类强去重(体现"N 家在报"),深度类弱去重 + 必留原文。
