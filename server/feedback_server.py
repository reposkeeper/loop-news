#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Loop News 反馈服务器(零第三方依赖,Python 标准库)。

端点(CORS 全开,任何设备/页面可调用):
  GET  /health    健康检查
  GET  /tags      返回常用反馈词 config/feedback_tags.json(弹窗 chips 用)
  POST /feedback  追加一条反馈到 data/feedback.jsonl
  GET  /feedback  列出全部反馈(供 ln-evolve / 自查)

用法:
  python3 server/feedback_server.py [port]      # 默认 8099
本地够用;要让手机/他人用,需把它部署到带 HTTPS 的公网(见 RUNBOOK 的"反馈服务"一节),
并把 config/loop.yaml 的 feedback.api_url 改成该公网地址。
"""
import json, os, sys, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEEDBACK = os.path.join(ROOT, "data", "feedback.jsonl")
TAGS = os.path.join(ROOT, "config", "feedback_tags.json")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
ALLOWED_ACTIONS = {"up", "down", "adopt", "ask"}
OWNER_TOKEN = os.environ.get("OWNER_TOKEN", "")  # 设置后,ask(全局提问)需带该 token


def _cors(h):
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        _cors(self)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        _cors(self)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            return self._json(200, {"ok": True})
        if path == "/tags":
            tags = json.load(open(TAGS, encoding="utf-8")) if os.path.exists(TAGS) else {}
            return self._json(200, tags)
        if path == "/feedback":
            items = []
            if os.path.exists(FEEDBACK):
                for line in open(FEEDBACK, encoding="utf-8"):
                    line = line.strip()
                    if line:
                        items.append(json.loads(line))
            return self._json(200, {"count": len(items), "items": items})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/feedback":
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception as exc:
            return self._json(400, {"error": f"bad json: {exc}"})
        action = data.get("action", "")
        if action not in ALLOWED_ACTIONS:
            return self._json(400, {"error": f"action must be one of {sorted(ALLOWED_ACTIONS)}"})
        if action == "ask" and OWNER_TOKEN and data.get("token") != OWNER_TOKEN:
            return self._json(403, {"error": "global feedback requires owner token"})
        rec = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "action": action,
            "item_id": str(data.get("item_id", ""))[:120],
            "date": str(data.get("date", ""))[:20],
            "title": str(data.get("title", ""))[:300],
            "tags": [str(t)[:40] for t in (data.get("tags") or [])][:8],
            "text": (str(data.get("text", "")) or "").strip()[:2000],
        }
        os.makedirs(os.path.dirname(FEEDBACK), exist_ok=True)
        with open(FEEDBACK, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return self._json(200, {"ok": True, "saved": rec})

    def log_message(self, *args):
        pass  # 静默


if __name__ == "__main__":
    print(f"[feedback] 监听 http://0.0.0.0:{PORT}")
    print(f"[feedback] /health /tags /feedback ;反馈写入 {FEEDBACK}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
