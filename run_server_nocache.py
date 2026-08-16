#!/usr/bin/env python3
import http.server, socketserver, webbrowser, argparse
from pathlib import Path
ap=argparse.ArgumentParser(); ap.add_argument('--port',type=int,default=8081); ap.add_argument('--no-open',action='store_true'); a=ap.parse_args()
root=(Path(__file__).resolve().parent/'WFTest').resolve()
class H(http.server.SimpleHTTPRequestHandler):
    extensions_map={**http.server.SimpleHTTPRequestHandler.extensions_map,'.js':'application/javascript','.json':'application/json','.orderedmap':'application/octet-stream','.woff':'font/woff','.ttf':'font/ttf'}
    def __init__(self,*x,**kw): super().__init__(*x,directory=str(root),**kw)
    def end_headers(self):
        self.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma','no-cache')
        self.send_header('Expires','0')
        self.send_header('X-WF-Mod-Build','0.2.11')
        super().end_headers()
with socketserver.TCPServer(('127.0.0.1',a.port),H) as httpd:
    url=f'http://127.0.0.1:{a.port}/index.html?wfbuild=0.2.11'
    print('[WFMod] v0.2.11 no-cache server:',url)
    if not a.no_open: webbrowser.open(url)
    httpd.serve_forever()
