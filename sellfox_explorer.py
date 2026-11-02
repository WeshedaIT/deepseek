#!/usr/bin/env python3
"""
sellfox_explorer.py — 赛狐开放平台 API Explorer 本地版。

职责:
  GET  /             直接返回构建好的 index.html（与静态页完全同一份文件）
  GET  /api/tree     返回 data/api_tree.json（唯一数据源）
  GET  /api/health   健康检查
  POST /api/proxy    带签名转发到 openapi.sellfox.com，绕过浏览器 CORS

零第三方依赖，仅用标准库。

用法:
    python3 sellfox_explorer.py                  # http://127.0.0.1:8765
    python3 sellfox_explorer.py --port 9000
    python3 sellfox_explorer.py --open           # 启动后尝试打开浏览器
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent
INDEX_FILE = ROOT / "index.html"
DATA_FILE = ROOT / "data" / "api_tree.json"

UPSTREAM = "https://openapi.sellfox.com"
TIMEOUT = 40


class Tree:
    """data/api_tree.json 的只读封装 —— 应用里唯一知道接口清单的对象。"""

    def __init__(self, path: pathlib.Path):
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.tree = raw["tree"]
        self.source = raw.get("source", "")
        self.endpoints = {}
        self.api_count = 0
        self._index(self.tree)
        self.stats = {
            "apis": self.api_count,
            "modules": len(self.tree),
        }

    def _index(self, nodes):
        for node in nodes:
            if node.get("type") == "apiDetail":
                self.api_count += 1
                # 文档中同一路径可能出现于多个分组，首次出现者作为代表
                self.endpoints.setdefault(node["path"], node)
            self._index(node.get("children") or [])

    def has_path(self, path: str) -> bool:
        return path in self.endpoints


def md5_sign(params: dict, app_secret: str) -> str:
    """赛狐签名: 参数按名 ASCII 升序拼 key=value&...，末尾追加 &key=secret，取 MD5。"""
    filtered = {k: v for k, v in params.items() if k != "sign" and v is not None}
    joined = "&".join(f"{k}={filtered[k]}" for k in sorted(filtered))
    return hashlib.md5(f"{joined}&key={app_secret}".encode("utf-8")).hexdigest()


def build_public_params(access_token: str, client_id: str, app_secret: str) -> dict:
    params = {
        "access_token": access_token,
        "client_id": client_id,
        "timestamp": int(time.time() * 1000),
        "nonce": random.randint(100000, 999999999),
    }
    params["sign"] = md5_sign(params, app_secret)
    return params


class Handler(BaseHTTPRequestHandler):
    server_version = "SellFoxExplorer/1.0"
    tree: Any = None  # 由 main() 注入：Tree 实例

    def log_message(self, format, *args):  # noqa: A002 - 沿用基类签名
        print(f"[{self.log_date_time_string()}] {format % args}")

    # ---------- helpers ----------

    def _send(self, status: int, body: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    # ---------- routes ----------

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path in ("/", "/index.html"):
            if not INDEX_FILE.exists():
                self._json(500, {
                    "error": "index.html 不存在",
                    "hint": "先运行 python3 build.py 从 data/api_tree.json 生成",
                })
                return
            self._send(200, INDEX_FILE.read_bytes(), "text/html; charset=utf-8")
            return

        if path == "/api/health":
            self._json(200, {
                "status": "ok",
                "upstream": UPSTREAM,
                "apis": self.tree.stats["apis"],
                "modules": self.tree.stats["modules"],
                "source": self.tree.source,
            })
            return

        if path == "/api/tree":
            self._json(200, {"source": self.tree.source, "stats": self.tree.stats,
                             "tree": self.tree.tree})
            return

        self._json(404, {"error": "not found", "path": path})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/proxy":
            self._handle_proxy()
        else:
            self._json(404, {"error": "not found", "path": path})

    def _handle_proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 4 * 1024 * 1024:
            self._json(400, {"error": "请求体为空或过大"})
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._json(400, {"error": f"请求体不是合法 JSON: {exc}"})
            return

        api_path = payload.get("path") or ""
        body = payload.get("body") or {}
        access_token = payload.get("access_token") or ""
        client_id = payload.get("client_id") or ""
        app_secret = payload.get("app_secret") or ""

        if not api_path.startswith("/"):
            self._json(400, {"error": "path 必须以 / 开头"})
            return
        if not access_token or not client_id:
            self._json(400, {"error": "缺少 access_token 或 client_id"})
            return
        if not self.tree.has_path(api_path):
            self._json(404, {
                "error": f"接口不在当前 API 树中: {api_path}",
                "hint": "运行 python3 build.py 可从最新数据重建",
            })
            return

        params = build_public_params(access_token, client_id, app_secret)
        final_body = dict(body)
        final_body.update(params)

        url = UPSTREAM + api_path
        data = json.dumps(final_body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            status = exc.code
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self._json(502, {"error": f"上游请求失败: {exc}", "upstream": url})
            return

        elapsed = int((time.time() - started) * 1000)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None

        self._json(200, {
            "status": status,
            "elapsed_ms": elapsed,
            "upstream": url,
            "request": {k: v for k, v in final_body.items() if k != "access_token"},
            "response": parsed if parsed is not None else raw,
        })


def main() -> int:
    parser = argparse.ArgumentParser(description="SellFox API Explorer 本地服务")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--open", action="store_true", help="启动后打开浏览器")
    args = parser.parse_args()

    if not DATA_FILE.exists():
        print(f"缺少数据源 {DATA_FILE}")
        return 1

    Handler.tree = Tree(DATA_FILE)

    if not INDEX_FILE.exists():
        print("index.html 不存在，尝试构建…")
        import subprocess, sys
        subprocess.run([sys.executable, str(ROOT / "build.py")], check=False)

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"SellFox API Explorer 已启动: {url}")
    print(f"  接口 {Handler.tree.stats['apis']} 个 / 模块 {Handler.tree.stats['modules']} 个")
    print(f"  上游 {UPSTREAM}")
    print("  Ctrl+C 停止")

    if args.open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
