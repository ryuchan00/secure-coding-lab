"""One editor per learner; execution takes place in a separate container."""
import html
import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).parent
LESSONS = Path(os.getenv('LESSONS_DIR', '/lessons'))
STATE = Path(os.getenv('STATE_DIR', '/state'))
CATALOG = json.loads((LESSONS / 'catalog.json').read_text())
IDS = {lesson['id'] for lesson in CATALOG}
LOCK = threading.Lock()
EDITOR_ORIGIN = os.getenv('EDITOR_ORIGIN', 'http://localhost:8080')
RUNTIME_ORIGIN = os.getenv('RUNTIME_ORIGIN', '')
ATTACKER_ORIGIN = os.getenv('ATTACKER_ORIGIN', 'http://localhost:8084')
EDITOR_HOST = urlsplit(EDITOR_ORIGIN).netloc
ATTACKER_HOST = urlsplit(ATTACKER_ORIGIN).netloc
FRAME_ORIGINS = [RUNTIME_ORIGIN] if RUNTIME_ORIGIN else [f'http://localhost:{x["port"]}' for x in CATALOG]
FRAME_ORIGINS.append(ATTACKER_ORIGIN)


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body, kind='application/json; charset=utf-8'):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-src " + ' '.join(FRAME_ORIGINS) + "; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get('Host') == EDITOR_HOST

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {'error': '研修の入口URLから開いてください'})
        path = urlsplit(self.path).path
        if path == '/api/lessons':
            return self.reply(200, CATALOG)
        if path == '/api/workspace':
            return self.reply(200, {'name': os.getenv('WORKSPACE_NAME', '個人の学習環境'), 'classroom': bool(RUNTIME_ORIGIN), 'runtimeOrigin': RUNTIME_ORIGIN, 'attackerOrigin': ATTACKER_ORIGIN})
        if path == '/api/progress':
            with LOCK:
                target = STATE / 'meta' / 'progress.json'
                result = json.loads(target.read_text()) if target.exists() else {'completed': []}
            return self.reply(200, result)
        parts = path.strip('/').split('/')
        if len(parts) == 3 and parts[0] == 'api' and parts[1] in IDS:
            lab, action = parts[1:]
            if action in {'code', 'solution'}:
                target = STATE / lab / 'index.php' if action == 'code' else LESSONS / lab / 'solution.php'
                with LOCK:
                    code = target.read_text()
                return self.reply(200, {'code': code})
        static = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
        if path in static:
            name, kind = static[path]
            return self.reply(200, (ROOT / 'static' / name).read_bytes(), kind + '; charset=utf-8')
        if path.startswith('/vendor/codemirror/'):
            base = ROOT / 'static' / 'vendor' / 'codemirror'
            target = (ROOT / 'static' / path.lstrip('/')).resolve()
            if target.is_relative_to(base) and target.is_file():
                kind = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
                return self.reply(200, target.read_bytes(), kind + '; charset=utf-8')
        self.reply(404, {'error': '見つかりません'})

    def do_POST(self):
        if not self.valid_host() or self.headers.get('Origin') != EDITOR_ORIGIN:
            return self.reply(403, {'error': '編集画面から操作してください'})
        if self.headers.get('Content-Type') != 'application/json':
            return self.reply(415, {'error': 'JSONが必要です'})
        path = urlsplit(self.path).path
        parts = path.strip('/').split('/')
        progress = path == '/api/progress'
        if not progress and (len(parts) != 3 or parts[0] != 'api' or parts[1] not in IDS or parts[2] not in {'code', 'reset'}):
            return self.reply(404, {'error': '見つかりません'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 0 or size > 65536:
                return self.reply(413, {'error': 'コードは64KBまでです'})
            self.connection.settimeout(5)
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError()
            if progress:
                completed = body['completed']
                if not isinstance(completed, list) or any(not isinstance(x, str) or x not in IDS for x in completed):
                    raise ValueError()
                result = {'completed': list(dict.fromkeys(completed))}
                with LOCK:
                    (STATE / 'meta' / 'progress.json').write_text(json.dumps(result))
                return self.reply(200, result)
            lab, action = parts[1:]
            code = (LESSONS / lab / 'index.php').read_text() if action == 'reset' else body['code']
            if not isinstance(code, str) or not code.strip():
                raise ValueError()
        except (ValueError, KeyError, TimeoutError):
            return self.reply(400, {'error': '入力内容を確認してください'})
        with LOCK:
            target = STATE / lab / 'index.php'
            temp = target.with_suffix('.tmp')
            temp.write_text(code)
            temp.replace(target)
        self.reply(200, {'code': code})


class Attacker(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get('Host') != ATTACKER_HOST:
            self.send_error(403)
            return
        account = RUNTIME_ORIGIN + '/csrf/' if RUNTIME_ORIGIN else 'http://localhost:8083/'
        body = (ROOT / 'static' / 'attacker.html').read_text().replace('http://localhost:8083/', html.escape(account, quote=True)).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / 'meta').mkdir(parents=True, exist_ok=True)
    for lab in IDS:
        target = STATE / lab / 'index.php'
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes((LESSONS / lab / 'index.php').read_bytes())
    attack = ThreadingHTTPServer(('0.0.0.0', 8084), Attacker)
    threading.Thread(target=attack.serve_forever, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()


if __name__ == '__main__':
    main()
