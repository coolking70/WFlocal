#!/usr/bin/env python3
"""Serve WFTest with caching disabled, and open a chosen page.

Caching is the enemy here: a browser that mixes a fresh bundle with a stale
.orderedmap (or a stale wfmod/runtime.js) produces failures that look like code
bugs. Everything is sent no-store.
"""
import argparse
import http.server
import socketserver
import sys
import webbrowser
from pathlib import Path

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
