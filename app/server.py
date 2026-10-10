"""Local single-learner editor. PHP executes only in separate containers."""
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
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-src http://localhost:8081 http://localhost:8082 http://localhost:8083 http://localhost:8084; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get('Host') in {'localhost:8080', '127.0.0.1:8080'}

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {'error': 'localhost:8080 から開いてください'})
        path = urlsplit(self.path).path
        if path == '/api/lessons':
            return self.reply(200, CATALOG)
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
        if not self.valid_host() or self.headers.get('Origin') not in {'http://localhost:8080', 'http://127.0.0.1:8080'}:
            return self.reply(403, {'error': '編集画面から操作してください'})
        if self.headers.get('Content-Type') != 'application/json':
            return self.reply(415, {'error': 'JSONが必要です'})
        parts = urlsplit(self.path).path.strip('/').split('/')
        if len(parts) != 3 or parts[0] != 'api' or parts[1] not in IDS or parts[2] not in {'code', 'reset'}:
            return self.reply(404, {'error': '見つかりません'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 0 or size > 65536:
                return self.reply(413, {'error': 'コードは64KBまでです'})
            self.connection.settimeout(5)
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError()
            lab, action = parts[1:]
            code = (LESSONS / lab / 'index.php').read_text() if action == 'reset' else body['code']
            if not isinstance(code, str) or not code.strip():
                raise ValueError()
        except (ValueError, KeyError, TimeoutError):
            return self.reply(400, {'error': '空でないコードを指定してください'})
        with LOCK:
            target = STATE / lab / 'index.php'
            temp = target.with_suffix('.tmp')
            temp.write_text(code)
            temp.replace(target)
        self.reply(200, {'code': code})


class Attacker(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get('Host') not in {'localhost:8084', '127.0.0.1:8084'}:
            self.send_error(403)
            return
        body = (ROOT / 'static' / 'attacker.html').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)


def main():
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
