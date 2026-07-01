# RUNBOOK — Loop News(agent 中立操作手册)

本手册让**任何 agent**(Claude Code / Codex / 其他)都能驱动 Loop News,**不依赖某家专有工具或 skill 机制**。
- Claude Code 用户:`.claude/skills/ln-*` 只是这些步骤的薄封装,等价。
- Codex 等用户:直接照本手册执行(另见 [AGENTS.md](AGENTS.md))。

> **进化北极星(目标函数)见 [GOALS.md](GOALS.md):最大化「非显然洞察」——跨时间/跨域、可证伪、言之有据的深层判断。`ln-synthesize` 朝它产出、`ln-evolve` 朝它收敛;硬约束=不臆造、回链证据、宁缺毋滥。**

## 变更落地契约(所有 agent 必守)
任何由**进化(ln-evolve)或功能改动**带来的变化,**必须落进二者之一,不允许只存在于对话/记忆**:
- **代码**:`web/compile.py`、`scripts/*`、`worker/*`、`functions/*`、`server/*`、`config/*`、`data/*`。
- **skill / 提示词 / 文档**:`.claude/skills/*`、`prompts/*`、`RUNBOOK.md`/`AGENTS.md`/`CLAUDE.md`/`GOALS.md`。

每次进化/改动后**自动检查**:`bash scripts/check.sh`(**git pre-commit 已强制,不通过则拦住提交**;`ln-evolve`/`ln-daily` 末尾也会跑)。它验证:编译自洽、JSON/skill/文件引用自洽、**进化已记 `prompts/CHANGELOG.md` 留痕**、改动已纳入提交。
> 新克隆启用钩子:`git config core.hooksPath .githooks`。

## 能力前提(用通用名词,按你的运行时自行映射)
- **网页搜索**:找共识/Breaking 新闻 + 名人发言。
- **网页抓取**:抓 RSS / 文章全文 / HackerNews Algolia API / 媒体页。
- **X/Twitter 访问**:已装 **X MCP**(`bash scripts/setup-mcp.sh` 构建到 `vendor/x-mcp`;`.mcp.json` 已配,凭证放不入库的 `.env`)。读工具:`search_tweets` / `get_timeline` / `get_user` / `get_tweet`。未配凭证时退化为"网页搜索还原引用"。Codex 等用各自的 MCP 配置指向同一 server(见 AGENTS.md)。
- **X 官方文档**:已配远程 MCP `x-docs`(`https://docs.x.com/mcp`,只读、免凭证)。**开发或调用 X API 前优先用它查最新官方文档**,避免凭旧知识读错接口。
- **shell**:`python3`(仅标准库,无需第三方)、`git`、`gh`(发布)。
- **反馈服务**:生产走 Cloudflare(`worker/feedback-worker.js` + D1 `loop-news-db` + KV `SESSIONS`)——反馈/收藏/关注/已读/请求按登录账号的 `user_id` 隔离,全站行为记 `activity`。本地零依赖备选 `server/feedback_server.py`(`data/feedback.jsonl`,账号体系之前的旧路径)。
- 时区:Asia/Shanghai。

## 每日循环
- **早班 07:00**:collect(am) → synthesize(汇总**昨天**) → compile → 〔人工确认〕→ publish → evolve
- **晚班 19:00**:仅 collect(pm)

## 步骤(= 对应 skill)
### 1. 采集 collect(= ln-collect)
读 `config/*.yaml` + `prompts/collect.consensus.md` + `prompts/collect.deep.md`,严格按其规则:
- 共识:网页搜索 + 媒体 RSS;强去重合并同事件、记 `consensus_count`、**优先一手出处**。
- 深度:Substack/博客 RSS 全文;名人原声(X 访问,缺则搜索还原引用);HN Algolia;Reddit 仅作搜索信号。**必留 `original_quote`**。
- 输出:归一化为〔语料条目 schema〕→ 去重追加 `data/corpus/<date>.json`;更新 `data/entities/index.json`、`state/seen.json`、`state/metrics.json`;原始批次存 `data/raw/<date>-<batch>.json`。

### 2. 汇总 synthesize(= ln-synthesize)
读 `prompts/synthesize.method.md`。加载昨天 corpus + 按实体/话题检索历史 → 套八透镜 → `connections` + 分级 `conclusions`(事实/推断/预测 + **证据回链,evidence 可跨日期**)。**维护跨日期 `data/threads.json`**;对含**可核实数字**的条目产出 `charts`(line/bar/pie,compile 渲染成内联 SVG,放新闻后;只对核实过的数字、标来源+"仅供参考",禁编造)。输出 `data/analysis/<date>.json`。

### 3. 编译 compile(= ln-compile)
`python3 web/compile.py` → 把全部 analysis + threads 编译成**单页** `docs/index.html`(确定性、无 LLM)。

### 4. 发布 publish(= ln-publish)
`bash scripts/publish.sh "<msg>"` → commit + push,GitHub Pages 上线。**默认早班把这步留人工确认**(发布是公开操作)。
> 若托管在 **Cloudflare**:改用 `bash scripts/deploy-cloudflare.sh`(Pages 发站 + Worker API + R2 + D1 schema),详见 [CLOUDFLARE.md](CLOUDFLARE.md)。
> **访问门 = 邮箱账号登录**(非整站私有,也不再是 token 分享):`functions/_middleware.js` 校验会话(cookie `lns` → KV `SESSIONS` 查 session),未登录返回两步登录页(邮箱 → 6 位验证码,Resend 发信),内容不下发。白名单 = D1 `users` 表;owner 引导见 `scripts/setup-auth.sh`。每个账号的反馈/收藏/关注/已读/请求按 `user_id` 隔离存 D1;全站行为记 `activity`。

### 5. 进化 evolve(= ln-evolve)
先读**人类反馈**(`bash scripts/feedback.sh`:从 D1 `feedback` 表拉取〔`up 赞 / down 踩 / adopt 采用` + 常用词 + 文字〕+ `feedback.md`)——**只消化 `role=owner` 的反馈用于全局进化**(普通账号的反馈是个人数据,驱动各自视图,不改全局 `prompts/*.md`/`config/*.yaml`,属 SP2 千人千面尚未构建的部分);若存在站长全局提问 `ask`,最高优先(本轮必须落实),采用次之。再读 `state/metrics.json`(含北极星指标 non_obvious/edge/cross_date/falsifiable)+ 抽样产物;小步改 `prompts/*.md` / `config/*.yaml` / `config/feedback_tags.json`;记 `prompts/CHANGELOG.md`。**早班顺序:本步在 synthesize 之前跑,进化修复完成后才生成当天总结。**

## 数据 schema(agent 间的契约 —— 权威定义)
- 语料条目:见 `.claude/skills/ln-collect/SKILL.md`
- 分析产物 + 跨日期线索:见 `.claude/skills/ln-synthesize/SKILL.md`
> 改 schema 属**人工大版本**,不归自动进化。

## 纪律(所有 agent 通用)
不臆造(新闻/引文/链接真实可回溯)· 中文呈现 + 深度留原文 · 结论分级 + 回链 · 失败来源记 metrics · 改动可 git 回滚。

## 确定性 vs 需要 LLM
- **确定性**(任何运行时结果一致):`web/compile.py`、`scripts/*.sh`。
- **需要 LLM 判断**:collect / synthesize / evolve —— 其 prompt 全部**外置在 `prompts/`**,便于跨 agent 复用、版本化,并被自进化安全修改。
