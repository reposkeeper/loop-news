---
name: ln-compile
description: Loop News 编译步骤。运行 web/compile.py,把当日分析 data/analysis/DATE.json 套 HTML 模板编译成静态网页写入 docs/(DATE.html + 刷新 index/archive)。当用户说"编译"、"生成网页"、"compile"、"ln-compile"、"出页面"时使用。
---

# ln-compile · 编译步骤

把分析产物编译成纯静态网页(GitHub Pages 托管目录 `docs/`)。这是确定性脚本,无 LLM。

## 运行
```bash
python3 web/compile.py <date>      # 编译指定日期,默认昨天
python3 web/compile.py --all       # 重建全部历史页面(模板改版后用)
```

## 它做什么
1. 读 `config/loop.yaml`(站点标题等)+ `data/analysis/<date>.json`。
2. 用 `web/templates/page.html` 外壳 + Python 生成各分区,写出:
   - `docs/<date>.html` —— 当期页(今日要闻/深度原声/关联与结论/方法论说明)。
   - `docs/index.html` —— 指向最新一期。
   - `docs/archive.html` —— 历史归档列表(扫描 `data/analysis/*.json`)。
3. 把 `web/assets/*` 同步到 `docs/assets/`。

## 验证
本地用浏览器或 `browse` skill 打开 `docs/<date>.html`,核对四个分区与中文排版、深度原声"显示原文"折叠可用。

## 出错处理
- 缺 `data/analysis/<date>.json` → 报错并提示先跑 `ln-synthesize`。
- schema 字段缺失 → 脚本应跳过该条并在 stderr 警告,不整体崩溃。
