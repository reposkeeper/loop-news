#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分享图预热器 —— 每天新闻生成后,把当日所有卡片(共识/深度/播客)按 id 逐张 force 渲染进 R2 缓存。
之后用户点「分享」几乎都是缓存命中(秒发、不吃 Worker CPU、不受字体抖动影响)。
用法:python3 scripts/warm-share.py [YYYY-MM-DD]   # 默认最新有分析的日期
由 ln-daily / ln-synthesize 在编译+部署后调用。缓存键=卡片 id(与前端分享一致),force 每次刷新为最新内容。
"""
import json, os, sys, re, subprocess, glob, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def share_api():
    try:
        y = open(os.path.join(ROOT, "config/loop.yaml"), encoding="utf-8").read()
        m = re.search(r'share_api_url:\s*"([^"]+)"', y)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "https://share.xdzq.org/share"


def cards_for(a, date):
    out = []
    for it in (a.get("consensus", []) or []) + (a.get("deep", []) or []) + (a.get("podcasts", []) or []):
        if not it.get("id"):
            continue
        deep = bool(it.get("original_quote"))
        src = it.get("source") or " · ".join(it.get("sources", []) or [])
        cc = it.get("consensus_count") or len(it.get("sources") or [])
        badge = f"{cc} 家在报" if (cc and not deep) else ""
        out.append({"id": it["id"], "title": it.get("title_zh", ""), "summary": it.get("summary_zh", ""),
                    "source": src, "date": date, "kind": "deep" if deep else "consensus",
                    "badge": badge, "quote": it.get("original_quote", "") or ""})
    return out


def _post_once(api, body):
    r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code} %{time_total} %{header_json}",
                        "-X", "POST", api, "-H", "Content-Type: application/json", "-d", body, "--max-time", "70"],
                       capture_output=True, text=True)
    parts = (r.stdout or "").split(" ", 2)
    code = parts[0] if parts else "000"
    t = parts[1] if len(parts) > 1 else "?"
    xc = "WARM"
    if len(parts) > 2:
        m = re.search(r'"x-cache":\s*\["?([A-Z]+)', parts[2])
        if m:
            xc = m.group(1)
    return code, t, xc


def post(api, card, tries=5):
    # 渲染偶发 503(免费版 CPU 边界,尤其突发并发时)——耐心重试 + 每次拉长冷却即可;
    # 成功一次后即永久缓存命中,故无需付费升级。
    body = json.dumps(card, ensure_ascii=False)
    code = t = xc = None
    for i in range(tries):
        code, t, xc = _post_once(api, body)
        if code == "200":
            return code, t, xc
        time.sleep(3 * (i + 1))  # 3s,6s,9s,12s —— 给 isolate 降温,避开突发超限
    return code, t, xc


def warm(date, force=False, passes=3):
    ap = os.path.join(ROOT, f"data/analysis/{date}.json")
    if not os.path.exists(ap):
        print(f"[warm-share] 无 {date} 分析,跳过")
        return 0
    a = json.load(open(ap, encoding="utf-8"))
    api = share_api()
    cards = cards_for(a, date)
    print(f"[warm-share] {date} → {api}  共 {len(cards)} 张卡片{'(force 刷新)' if force else '(幂等:只渲染未缓存的)'}")
    total_hit = 0
    remaining = cards
    # 自动收敛:突发渲染偶发 503,下一轮已成功的走 HIT(廉价)、只重渲染失败的,直到全部缓存
    for p in range(passes):
        failed = []
        for i, c in enumerate(remaining):
            payload = {**c, "force": True} if (force and p == 0) else c
            code, t, xc = post(api, payload)
            if code == "200":
                total_hit += (xc == "HIT")
                print(f"  ✓ {c['kind']:9} [{xc}] {t}s  {c['title'][:32]}")
            else:
                failed.append(c)
                print(f"  ✗ {code}      {c['title'][:32]}")
            if i < len(remaining) - 1 and xc != "HIT":
                time.sleep(2)   # 卡间隔,避免密集渲染顶爆免费版 CPU
        if not failed:
            print(f"[warm-share] {date}: 全部 {len(cards)} 张已缓存 ✅(第 {p + 1} 轮收敛)")
            return 0
        remaining = failed
        if p < passes - 1:
            print(f"  ↻ 第 {p + 2} 轮补渲染 {len(failed)} 张(降温 6s)…")
            time.sleep(6)
    print(f"[warm-share] {date}: 仍有 {len(remaining)} 张未缓存(可稍后再跑一次补齐):"
          + " / ".join(c["title"][:16] for c in remaining))
    return len(remaining)


def main():
    args = [x for x in sys.argv[1:]]
    force = "--force" in args
    args = [x for x in args if x != "--force"]
    date = args[0] if args else None
    if not date:
        ds = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(ROOT, "data/analysis/*.json")))
        date = ds[-1] if ds else None
    if not date:
        sys.exit("no analysis date")
    sys.exit(1 if warm(date, force) else 0)


if __name__ == "__main__":
    main()
