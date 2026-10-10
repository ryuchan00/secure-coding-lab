"""Shared classroom entrance. Routing tokens are never sent to PHP runtimes."""
import hashlib
import hmac
import json
import os
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

SEATS = json.loads(Path('/config/seats.json').read_text())
ORIGIN = os.environ['EDITOR_ORIGIN']
HOST = ORIGIN.split('://', 1)[1]
ATTEMPTS = defaultdict(deque)
LOCK = threading.Lock()
FORM = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>セキュアコーディング研修</title><style>body{font:17px/1.8 system-ui;color:#213a38;background:#f4f6f3;max-width:520px;margin:12vh auto;padding:24px}main{padding:28px;background:white;border-radius:12px}input,button{font:inherit;padding:12px;box-sizing:border-box;width:100%;margin-top:12px}button{background:#216958;color:white;border:0;border-radius:6px}label{display:block}p{font-size:15px}</style><main><h1>セキュアコーディング研修</h1><p>講師から受け取った自分の受講コードを入力してください。編集したコードや練習データは、自分の学習環境に保存されます。</p><form method="post" action="/login"><label>受講コード<input type="password" name="code" autocomplete="off" required maxlength="100"></label><button>研修を始める</button></form>{message}</main></html>'''


class Portal(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Do not record learner codes or routing credentials.

    def reply(self, status, body, cookie=None, redirect=False):
        data = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        if redirect:
            self.send_header('Location', '/')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get('Host') != HOST:
            return self.reply(403, '研修の入口URLから開いてください')
        if self.path == '/logout':
            body = FORM.split('<form')[0] + '<form method="post" action="/logout"><button>受講を終了する</button></form><p>保存済みのコードは残ります。再開するときは同じ受講コードを使ってください。</p></main></html>'
            return self.reply(200, body)
        if self.path != '/':
            return self.reply(401, '受講コードで研修の入口から入ってください')
        self.reply(200, FORM.replace('{message}', ''))

    def do_POST(self):
        if self.headers.get('Host') != HOST or self.headers.get('Origin') != ORIGIN:
            return self.reply(403, '研修の入口から操作してください')
        if self.path == '/logout':
            return self.reply(303, '', 'lab_workspace=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict', True)
        if self.path != '/login':
            return self.reply(404, 'ページが見つかりません')
        with LOCK:
            now = time.monotonic()
            for ip in list(ATTEMPTS):
                while ATTEMPTS[ip] and ATTEMPTS[ip][0] < now - 60:
                    ATTEMPTS[ip].popleft()
                if not ATTEMPTS[ip]:
                    del ATTEMPTS[ip]
            # Header is overwritten by our gateway; never trust a direct client header.
            ip = self.headers.get('X-Real-IP', self.client_address[0])
            if len(ATTEMPTS[ip]) >= 60:
                return self.reply(429, FORM.replace('{message}', '<p>しばらく待ってから、もう一度入力してください。</p>'))
            ATTEMPTS[ip].append(now)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 0 or size > 1024:
                raise ValueError()
            self.connection.settimeout(5)
            fields = parse_qs(self.rfile.read(size).decode())
            digest = hashlib.sha256(fields.get('code', [''])[0].strip().encode()).hexdigest()
        except (ValueError, UnicodeError, TimeoutError):
            return self.reply(400, '受講コードを確認してください')
        seat = next((x for x in SEATS if hmac.compare_digest(x['code_hash'], digest)), None)
        if seat is None:
            return self.reply(401, FORM.replace('{message}', '<p>受講コードを確認してください。</p>'))
        self.reply(303, '', f"lab_workspace={seat['token']}; Path=/; HttpOnly; SameSite=Strict", True)


ThreadingHTTPServer(('0.0.0.0', 8080), Portal).serve_forever()
