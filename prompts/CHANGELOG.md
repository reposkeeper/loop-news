# 进化改动日志(CHANGELOG)

> `ln-evolve` 每轮自评后,把对 `prompts/*.md`、`config/*.yaml` 的改动记在这里。
> 格式:日期 · 改了什么 · 为什么 · 如何回滚。最新在最上。

---

## 2026-07-01 · 账号体系(SP1-Core)
- **改了什么**:
  1. **访问门从 token 分享升级为邮箱验证码会话**:`POST /auth/request-code` 给白名单邮箱(D1 `users` 表)发 6 位码(Resend,10 分钟有效,KV 哈希存储,≤5 次尝试);`POST /auth/verify` 校验通过后签发 30 天会话(KV `session:<token>`),写 httpOnly cookie `lns`;`functions/_middleware.js` 改查会话放行,未登录返回两步登录页,内容不下发(旧的 `scripts/share-token.sh` + `SHARE_TOKENS` + `?token=` 已废弃)。
  2. **反馈/收藏/关注/已读/请求按 `user_id` 隔离**:`worker/feedback-worker.js` 的 per-user 端点(`/feedback` `/favorite(s)` `/follow(s)` `/read(s)` `/request(s)` `/activity`)从会话身份(`identify`)推导用户,写读 D1(`worker/schema.sql`),各账户数据互不影响;`/follows`、`/requests` 仍为 owner-only。
  3. **活动日志**:登录/退出/浏览/打开/反馈/收藏/关注/已读/请求/分享 全部记入 D1 `activity` 表,按 `user_id` 可查。
  4. **ln-evolve 限定 owner 反馈**:`.claude/skills/ln-evolve/SKILL.md` 的"读人类反馈"步骤改为只消化 `role=owner` 的反馈(`bash scripts/feedback.sh` 直接 `wrangler d1 execute` 查 `feedback JOIN users WHERE role='owner'`)驱动全局 `prompts/*.md`/`config/*.yaml` 进化;普通账号反馈是个人数据,驱动各自视图,不进全局进化(留给 SP2 千人千面)。
  5. 新增 `scripts/setup-auth.sh`(一次性 owner 引导:apply D1 schema + 播种 `OWNER_EMAIL`);`scripts/deploy-cloudflare.sh` 部署前加一步应用 D1 schema(幂等);`CLOUDFLARE.md`/`RUNBOOK.md`/`AGENTS.md`/`CLAUDE.md` 同步身份模型与反馈语义。
- **为什么**:旧的 token 分享门下所有人共享同一份反馈,一个人的口味会改动全站看到的新闻;升级为邮箱账号后每人反馈独立沉淀,同时把"谁的反馈驱动系统进化"收窄为 owner 一人,避免访客反馈误伤全局提示词/配置。这是 SP1(账号地基)的收尾任务,SP2(千人千面/个人进化)将建在这份地基之上。
- **如何回滚**:`git revert` 对应提交;数据库/KV 层面的资源创建(`wrangler d1 create`/`kv namespace create`)与 secret 需人工在 Cloudflare 控制台单独处理,代码回滚不会删除已创建的云资源。

---

## 2026-07-01 · 发布(反馈台账页 + 分享图预览/复制 + 更高清)
- **改了什么**:
  1. **📋 反馈台账**(系统区新页):实时拉 `/requests`+`/feedback` 显示大家的反馈,并对照 `data/feedback_ledger.json` 标注每条在**哪一轮进化被覆盖**;下方列出每轮进化覆盖了什么(ln-evolve 每轮维护台账)。
  2. **分享图改为预览 + 下载/复制**:生成后先在弹窗展示,下面两个按钮(下载 / 复制图片到剪贴板),不再直接下载。
  3. **分享图更高清**:输出分辨率 1200 → 2000px(HTML 里所有 px 统一缩放,图表用占位符避免误改),治糊。
- **为什么**:让反馈透明可追溯(哪条被哪轮消化);分享前先看效果、支持复制;更高分辨率更清晰。
- **如何回滚**:`git revert` 对应提交。

---

## 2026-07-01 · 加固(分享图 R2 缓存 + 每日预热 + 重试;免费版即可,无需付费)
- **依据**:站长反馈分享图 Worker 偶发失败。实测:单张/分散请求基本能出图,但**密集连发时 503**(免费版 Worker CPU 边界被突发渲染顶爆);站长并要求每天新闻生成后自动预渲染所有卡片。
- **改了什么**:
  1. **`worker/share-worker.js` R2 缓存**:按**卡片 id** 缓存 PNG——命中直接秒发(不再跑 Satori/resvg、不抓字体),每张只渲染一次;字体抓取加 **3 次重试**;`force` 可刷新;`wrangler.share.toml` 加 `BUCKET`(复用 `loop-news` 桶)。
  2. **前端重试**:点分享失败**自动重试 3 次**(退避),兜住冷启动/部署瞬间/字体抖动。
  3. **`scripts/warm-share.py`**:每天新闻生成后把所有卡片(共识/深度/播客)按 id 预渲染进缓存;**幂等自收敛**(已缓存走 HIT 跳过、失败的下一轮重渲染,卡间隔降温避免突发顶爆);接进 `ln-daily` 步骤 7 与 CLAUDE.md 每日循环。
- **为什么**:把"每次点分享都现渲染"改成"每卡只渲一次、之后全命中",在**免费版**下把偶发 503 基本消除——**不必升级 $5/月 Workers Paid**(除非日后要更高分辨率/更大分享量)。
- **如何回滚**:`git revert`;去掉 R2 绑定即回到纯即时渲染。

---

## 2026-07-01 · 重采(纯当日鲜闻:及时性 7.7 → 90.5)
- **依据**:站长指令「重采一份」——旧 7-01 期含 ~2–4 周前旧闻,及时性分仅 7.7。用新规则(实时源、只采当日/昨日、据实标 published)重采。
- **改了什么**:
  1. **整期重采**:替换 7-01 语料为 **15 条 6/29–6/30 鲜闻**(仅推理并购 1 条 6/24),全部真实一手 URL。含美团 LongCat-2.0(1.6 万亿参数、国产芯片全程预训练)、GitHub Copilot 计量计费冲击、台湾突袭 Super Micro、GPT-5.6 政府门控、Anthropic 解禁 + Claude Science、最高法地理围栏案、Meta『戛纳』测试丑闻、AP 全球 AI 诈骗调查等。
  2. **重出分析**:4 条当日关联 + 2 条**跨日期**关联(接 6-30 的 Anthropic 蒸馏指控/高通收 Tenstorrent)+ 6 条分级结论;深度原声 Import AI 463(ARGUS 万卡框架)、GeopolitechS(LongCat 冲击出口管制);更新「美中 AI 角力」线索到芯片/训练层。
  3. **源台账评选**:新增 Bloomberg/VentureBeat 固化为 core,The Next Web/SiliconANGLE/GeopolitechS 入 trial。
  4. **分数**:及时 **7.7→90.5**、关联 **66.7→100**、综合 **71.4→84.6**;数量降到 71.9(守住『只上干净鲜闻、不注水』)。
- **为什么**:验证新及时性强惩罚的正向面——按规则采,分数自然回正;且不牺牲真实性与一手溯源。
- **如何回滚**:`git revert`;语料/分析/线索可分别回退。

---

## 2026-07-01 · 进化(第 6 分:新闻及时性 · 强惩罚 + 漏采后补也罚)
- **依据**:用户要求——不能总把几天前、甚至上周的新闻塞进来,**新闻要实时、来源要实时**;及时性用**强惩罚**,一天里有几条超期分数就大跌;且**"漏采后补"**(当时没采、现在才补)也要罚。
- **改了什么**:
  1. **第 6 分 `timeliness`**(`scripts/score.py`):`lateness = 采集日 − 事件日(published)`;**内容陈旧 + 漏采后补**双重判罚;`fresh_days=4`,超期条数用 **`0.78^(n-1)` 强惩罚**(多条即大跌);未标 `published` 拉低覆盖率。composite 改**六者均值**。
  2. **语料加 `published`(事件日,必填)+ `first_seen`(首采日)**;`ln-collect` 要求据实标注、优先当日一手、堵漏采;`source_quality.json` 源加 **`recency: realtime/fast/slow`**,优先实时源。
  3. **仪表盘加第 6 卡「及时性」**;`prompts/scoring.md` / `GOALS.md` / `ln-evolve`(及时性低=优先修:补实时源、剔旧闻、堵漏采)全部接入。
  4. **今日据实**:7-01 补全事件日、**砍掉 3 条 4 月旧闻**;及时性据实算得 **7.7**(8 条为 2–4 周前旧闻/漏采后补)——强惩罚如实触发,标为本轮最低分待修。
- **为什么**:把"新闻必须实时、漏采要罚"变成硬性、可量化的强惩罚,逼采集只上当日一手、不吃回锅旧闻。
- **如何回滚**:`git revert`;score.py / `published` 字段可分别回退。

---

## 2026-07-01 · 进化(5 分制评分 + 自进化仪表盘 + 信息源固化)
- **改了什么**:
  1. **5 个系统分数**(`scripts/score.py` 确定性算,写 `state/scores.json`):关联度 / 数量 / 分析整合 / 自进化广度 / **信息源固化** + 综合。数量分对欠采**陡峭惩罚**;信息源固化分**强迫每轮评选来源**(不评选则随天数衰减)。制度见 `prompts/scoring.md`。
  2. **信息源固化台账** `data/source_quality.json`:core(固化)/ trial / watch / demoted 分档;ln-evolve 每轮**升优汰劣**(优质源升 core、噪音源降级淘汰)。
  3. **📊 自进化仪表盘**(owner 专属新页 `view-dashboard`):综合分 + 5 分 + Δ + 趋势 + 来源分档 + 成分明细。
  4. **skill 联动**:ln-synthesize 末尾必跑 `score.py`;ln-evolve **优先修最低/下滑分** + 每轮评选来源;GOALS 运行化为 5 分。
  5. **按名字 + 时间问候**:访问门写 `lnname` cookie,页面顶部「下午好,之桥…」;owner 名字设为「之桥」。
- **为什么**:把『防欠采、持续评优质源、每轮都进步』变成显式、可量化、有奖惩的机制,agent 每轮盯着分数往上做。
- **如何回滚**:`git revert`;score.py / scores.json / source_quality.json 可分别回退。

---

## 2026-07-01 · 进化(奖励『多采集』+ 今日补采到 14 条)
- **依据**:用户反馈『采集太少、远低于正常新闻量』,且点名漏采了当天很爆的 Claude Code『中国指纹』事件。
- **改了什么**:
  1. **把『采集量』设为奖励维度**:`loop.yaml` 加 `collect.volume_target=20 / floor=12 / breadth_queries_min=8`;`GOALS.md` 新增「采集广度」分层(采集层高召回、欠采=失职;呈现层仍宁缺毋滥);`collect.consensus/deep` 加『高召回、多角度检索』;`ln-evolve` 把『欠采』列为高优先诊断;`sources.yaml` 再拓 5 组检索角度(芯片/中国 AI/融资/安全争议/产品发布)。
  2. **今日补采**:2026-07-01 从 6 条补到 **14 条**——含 Claude Code 中国指纹(Anthropic 员工已确认将回滚)、Anthropic 指控阿里 1600 万次蒸馏、OpenAI 秘密 IPO、中国开源 Qwen/GLM-5、苹果跑 Nvidia、欧盟 AI 法 8 月全面适用、芯片版图重排;重出分析(11 共识 / 2 深度 / 6 关联 / 7 结论),新增「美中 AI 角力」跨日期线索。
- **为什么**:没料就没洞察;把『广撒网』变成 loop 的显式奖励,避免欠采。
- **如何回滚**:`git revert` 对应提交;配置 / 提示词 / 数据可分别回退。

---

## 2026-07-01 · 进化(消化反馈:更多 AI + 即刻 + 🎙️ 播客环节)
- **依据**:线上 `/requests`(「AI 在企业中的应用 / harness engineering」「机器人 / 具身智能创业融资」)+ `/follows`(AI 安全 / 前沿模型)+ metrics(ylecun/DrJimFan/paulkrugman/RayDalio 多口水/格言/无实质);站长指令「AI 内容太少、加即刻、新增播客」。
- **改了什么**:
  1. **更多 AI**:`sources.yaml` 加 AI 专项 query(企业 AI/harness、机器人具身融资、AI 安全/前沿模型)+ AI RSS(TechCrunch AI / VentureBeat AI / MIT Tech Review);`people.yaml` 新增高信号声音(Mira Murati / Noam Shazeer / Jared Kaplan / Aidan Gomez / Arvind Narayanan),低产者标 `priority: low` 降权(ylecun/DrJimFan/paulkrugman/RayDalio)。
  2. **即刻 Jike**:`sources.cn_platforms` 加即刻(WebSearch 限定 okjike.com 找一手,抓不到只作信号,不臆造)。
  3. **🎙️ 播客环节(新)**:`config/podcasts.yaml`(Dwarkesh / Lex / No Priors / Latent Space … + 重点 AI 嘉宾);ln-collect 加播客采集步、ln-synthesize schema 加 `podcasts`、compile 新增「🎙️ 播客 · AI 人物访谈」区(节目 / 主持×嘉宾 / 要点 / 原话 / 收听);示例接入 3 集真实访谈(Dwarkesh×Amodei、Lex×Hassabis、Lex×Pichai)。
- **为什么**:反馈明确要更多 AI 与高质量中文平台;知名主持 × 知名 AI 人物的整集深访是「非显然洞察」的富矿(北极星)。
- **如何回滚**:`git revert` 对应提交;播客/即刻/AI 源均为配置与提示词,删对应段即回退。

---

## 2026-07-01 · 进化(专题升级为深度报道 + 严肃媒体房规)
- **改了什么**:
  1. 新增 `prompts/dossier.method.md`(深度报道方法论 + 严肃媒体写法 + 反煽动硬约束 + 自评口径);重写 `ln-dossier` skill:深挖一手/多元信源 → 写成结构化文章(核心判断 / 脉络 / 数据 / 各方 / 分析 / 反方 / 看点 / 来源)。
  2. compile 专题改文章式渲染(刊头 + 导语首字下沉 + 各方角色标签 + 分级结论 + 反方 + 看点 + 来源);示例「AI 监管」专题据实重写为深度报道——州法爆发 vs 联邦 99–1 预占失败 vs 州内降温,含 Cruz / Markey 真实原话与 NCSL / 参议院一手来源。
  3. `ln-evolve` 读专题 `quality_self_eval` 持续打磨 dossier.method;`collect.consensus/deep` 与 `domains.yaml` 加"对标严肃媒体 + 一手优先 + 多方在录"房规。
- **为什么**:专题不该是新闻聚合,而应是有数据、图表、(挣来的)观点、分析的深度报道;把"严肃新闻体、反自媒体危言耸听"固化成可进化的房规。
- **如何回滚**:`git revert` 对应提交;方法都在 `dossier.method.md`,回退即恢复旧专题形态。

---

## 2026-07-01 · 发布(系统/新闻分离 + 多家原文 + 自助分享链接)
- **改了什么**:
  1. **「想看的话题」改浮动按钮**叠在「反馈」上(所有访客);**「自进化日志」等系统项**移入侧栏底部「系统」区,与新闻导航(线索/收藏/专题/每日)分开——系统管理不与新闻混。
  2. **多家报道→逐家可点原文**:`source_links` 让"N 家在报"渲染成逐家各自可点的原文链接;并据实修正科罗拉多 AI 法(实为 SB189 大改 + 推迟到 2027-01)。
  3. **自进化日志可分享成现代产品发布卡**:版本徽章 + 标题 + 要点,刻意区别于新闻卡。
  4. **owner 自助生成分享链接**:网页填名字一键生成专属访问链接(便于区分分享给谁),访问门与各接口同时认 R2 里的自助 token。
- **为什么**:把"系统管理"与"新闻消费"在信息架构上分开;让多家印证可逐家溯源;让"分享与放行"从改配置变成网页自助。
- **如何回滚**:`git revert` 对应提交;自助 token 存 R2 `tokens/`,删对象即吊销。

---

## 2026-07-01 · 发布(改版 + 分享出图 + 想看的话题)
- **改了什么**:
  1. **整页重设计 + 移动端适配**:统一条目动作栏(赞/踩/采用 · 收藏/关注/分享 同一行、顶部发丝线分隔),侧栏抽屉、底部抽屉式弹窗、安全区与触控目标下沉;桌面/手机两端实测。
  2. **每条新闻「⤴ 分享」**:服务端按手机卡片样式出图(独立 Worker `loop-news-share` · Satori+resvg / `workers-og`),中文按本卡片文本子集化加载、含图表,点击自动下载 PNG。
  3. **「➕ 想看的话题」**:任意用户提交想持续看到的新闻类型,下一轮 `ln-collect` 并入采集议程。
  4. **「提问」→「反馈」**:全局浮动按钮更名。
- **为什么**:多次迭代后按钮位置/结构不统一,先理顺;并补齐对外分享通路与用户驱动采集,贴近北极星——让有信息优势的内容更易被带走、被持续追踪。
- **如何回滚**:`git revert` 对应提交;分享出图为独立 Worker,可单独下线不影响主站与反馈 API。

---

## 2026-06-30 · 进化 #1(首期真实运行后自评)
- **依据**:`state/metrics.json` 的 `2026-06-30-am` 一轮 —— `x_mcp: unavailable`、`reddit: blocked`、`nitter: dead`;且抽查首期产物发现共识类 `url` 多指向聚合/周报页(buildfastwithai、medium 综述)而非一手出处。
- **改了什么**:
  1. `prompts/collect.consensus.md`:新增「优先一手出处」规则——`url` 优先原始媒体/官方稿,禁用聚合页当来源,`consensus_count` 必须实数不估算。
  2. `config/sources.yaml`:标注 Reddit 被拦(仅作 WebSearch 信号)、HN 改用 Algolia API、新增 `x.via: mcp`(fallback websearch)。
- **为什么**:提升共识类来源可信度与可回溯性;把实测的来源可用性固化进配置,指导下一轮采集。
- **如何回滚**:`git revert` 本次提交,或删除上述两处新增段落即可恢复到「进化 #0/初始化」基线。

---

## 2026-06-30 · 工程初始化
- **改了什么**:创建初始提示词(collect.consensus / collect.deep / synthesize.method)与来源配置。
- **为什么**:Loop Engineering 工程起步,建立可被后续自动演进的基线。
- **如何回滚**:本条为初始版本,无需回滚;后续改动以本版本为基线对比。
