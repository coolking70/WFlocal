#!/usr/bin/env python3
"""Serve WFTest with caching disabled, and open a chosen page.

Caching is the enemy here: a browser that mixes a fresh bundle with a stale
.orderedmap (or a stale wfmod/runtime.js) produces failures that look like code
bugs. Everything is sent no-store.
"""
import argparse
import http.server
import json
import socketserver
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import apply_edit  # noqa: E402

BUILD = "0.3.3"
DEFAULT_PAGE = "game-index.html?wfmode=challenge&wfdev=fullskill"

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8081)
ap.add_argument("--no-open", action="store_true")
ap.add_argument("--page", default=DEFAULT_PAGE,
                help=f"page to open, relative to the server root (default: {DEFAULT_PAGE})")
args = ap.parse_args()

root = (Path(__file__).resolve().parent / "WFTest").resolve()


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "application/javascript", ".json": "application/json",
        ".orderedmap": "application/octet-stream",
        ".woff": "font/woff", ".ttf": "font/ttf",
    }

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(root), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("X-WF-Mod-Build", BUILD)
        super().end_headers()

    # The Hub edits data through this, because a browser cannot write files and
    # should not learn how - tools/apply_edit.py keeps Python the only writer.
    # The server binds to 127.0.0.1, so this is reachable from this machine only.
    # A GET on the edit endpoint answers "editing is available here". A server
    # started before this feature existed answers 404 for it and 501 to the POST,
    # and the browser has no other way to tell - which is exactly the confusion
    # this caused: the page looked fine because the old server still served files.
    def do_GET(self):
        if self.path.split("?")[0] == "/wfmod/api/edit":
            self.reply(200, {"ready": True, "build": BUILD})
            return
        super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] != "/wfmod/api/edit":
            self.send_error(404, "no such endpoint")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            request = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError) as error:
            self.reply(400, {"error": f"bad request body: {error}"})
            return
        try:
            output = apply_edit.apply(
                request.get("program"), request.get("command"),
                request.get("param"), request.get("value"), request.get("index"))
        except apply_edit.EditError as error:
            self.reply(400, {"error": str(error)})
            return
        print(f"[WFMod] edit {request.get('command')}.{request.get('param')} "
              f"= {request.get('value')}")
        self.reply(200, {"ok": True, "output": output})

    def reply(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *a):
        pass    # the access log buries the lines that matter


class Server(socketserver.TCPServer):
    allow_reuse_address = True      # do not fail on a socket still in TIME_WAIT


separator = "&" if "?" in args.page else "?"
url = f"http://127.0.0.1:{args.port}/{args.page}{separator}wfbuild={BUILD}"

try:
    httpd = Server(("127.0.0.1", args.port), Handler)
except OSError as error:
    if error.errno in (48, 98):     # EADDRINUSE on macOS / Linux
        sys.exit(
            f"\n端口 {args.port} 已被占用——多半是上一个服务还在跑。\n"
            f"  查看： lsof -ti tcp:{args.port}\n"
            f"  结束： lsof -ti tcp:{args.port} | xargs kill\n"
            f"  或改端口： python3 ./run_server_nocache.py --port {args.port + 1}\n"
            f"如果那个服务就是你要的，直接打开：{url}\n")
    raise

print(f"[WFMod] v{BUILD} no-cache server: {url}")
if not args.no_open:
    webbrowser.open(url)
with httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[WFMod] server stopped")
