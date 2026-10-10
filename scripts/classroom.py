#!/usr/bin/env python3
"""Generate an isolated, fixed-size classroom without exposing Docker to the app."""
import argparse
import hashlib
import ipaddress
import json
import os
from itertools import islice
import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description='10〜20人が同じURLから受講するためのDocker設定を作成')
parser.add_argument('--seats', type=int, default=20)
parser.add_argument('--host', default='localhost', help='受講者から見えるサーバーのIPまたはホスト名')
parser.add_argument('--bind', default='127.0.0.1', help='公開するインターフェースのIP。LAN共有時は0.0.0.0')
parser.add_argument('--editor-port', type=int, default=8080)
parser.add_argument('--runtime-port', type=int, default=8081)
parser.add_argument('--attacker-port', type=int, default=8084)
parser.add_argument('--subnet', default='10.240.0.0/22', help='受講者用のDockerネットワーク範囲。社内LANやVPNと重ならない私有IPv4範囲')
parser.add_argument('--output', type=Path, default=ROOT / '.classroom')
args = parser.parse_args()
if not 1 <= args.seats <= 50:
    parser.error('--seats は1〜50を指定してください')
if not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?', args.host):
    parser.error('--host はIPv4またはホスト名を指定してください（URLやパスは不可）')
try:
    ipaddress.IPv4Address(args.bind)
except ValueError:
    parser.error('--bind はIPv4アドレスを指定してください')
try:
    pool = ipaddress.IPv4Network(args.subnet)
    if not any(pool.subnet_of(ipaddress.ip_network(x)) for x in ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']) or pool.prefixlen > 28:
        raise ValueError()
    subnets = list(islice(pool.subnets(new_prefix=28), args.seats + 1))
    if len(subnets) < args.seats + 1:
        raise ValueError()
except ValueError:
    parser.error('--subnet は受講者数+1個の/28に分割できる私有IPv4範囲を指定してください')
ports = [args.editor_port, args.runtime_port, args.attacker_port]
if len(set(ports)) != 3 or any(x < 1024 or x > 65535 for x in ports):
    parser.error('ポートは重複しない1024〜65535の番号にしてください')
out = args.output.resolve()
if out.exists():
    parser.error(f'{out} は既にあります。既存の受講コードを保つため上書きしません')
out.mkdir(mode=0o700, parents=True)
origin = f'http://{args.host}:{args.editor_port}'
runtime_origin = f'http://{args.host}:{args.runtime_port}'
attacker_origin = f'http://{args.host}:{args.attacker_port}'
seats, roster = [], []
services, networks, volumes = {}, {'edge': {'ipam': {'config': [{'subnet': str(subnets[0])}]}}}, {}
restrict = {'read_only': True, 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'], 'pids_limit': 32}
app_build = {'context': str(ROOT), 'dockerfile': 'app/Dockerfile'}
# Bind-mounted private configuration belongs to the user who generated it.
# Editors and PHP still run as UID 1000 with their own named volumes.
config_user = f'{os.getuid()}:{os.getgid()}'
services['portal'] = {
    **restrict, 'image': 'secure-coding-lab-classroom-editor:latest', 'build': app_build, 'user': config_user, 'command': ['python', 'portal.py'],
    'environment': {'EDITOR_ORIGIN': origin}, 'volumes': [f'{out}/seats.json:/config/seats.json:ro'],
    'networks': ['edge'], 'mem_limit': '128m', 'tmpfs': ['/tmp:uid=1000,gid=1000,mode=1777'],
}
for i in range(1, args.seats + 1):
    name = f'learner{i:02}'
    code, token = secrets.token_urlsafe(12), secrets.token_hex(32)
    seats.append({'name': name, 'code_hash': hashlib.sha256(code.encode()).hexdigest(), 'token': token})
    roster.append({'name': name, 'code': code})
    networks[name] = {'internal': True, 'ipam': {'config': [{'subnet': str(subnets[i])}]}}
    volumes[name] = {}
    services[f'{name}-init'] = {
        'image': 'secure-coding-lab-classroom-editor:latest', 'build': app_build, 'user': '0:0',
        'command': ['python', '-c', 'import os; os.chown("/state", 1000, 1000)'],
        'volumes': [f'{name}:/state'], 'network_mode': 'none',
    }
    services[f'{name}-editor'] = {
        **restrict, 'image': 'secure-coding-lab-classroom-editor:latest', 'build': app_build, 'volumes': [f'{name}:/state'], 'networks': [name],
        'environment': {'EDITOR_ORIGIN': origin, 'RUNTIME_ORIGIN': runtime_origin, 'ATTACKER_ORIGIN': attacker_origin, 'WORKSPACE_NAME': f'受講者 {i:02}'},
        'depends_on': {f'{name}-init': {'condition': 'service_completed_successfully'}},
        'tmpfs': ['/tmp:uid=1000,gid=1000,mode=1777'], 'mem_limit': '128m',
        'healthcheck': {'test': ['CMD', 'python', '-c', f'import urllib.request; urllib.request.urlopen(urllib.request.Request("http://localhost:8080/api/lessons", headers={{"Host": "{args.host}:{args.editor_port}"}}))'], 'interval': '3s', 'timeout': '2s', 'retries': 10},
    }
    services[f'{name}-runtime'] = {
        **restrict, 'image': 'secure-coding-lab-classroom-runtime:latest', 'build': str(ROOT / 'runtime'), 'volumes': [f'{name}:/work:ro'],
        'command': ['php', '-S', '0.0.0.0:8080', '-t', '/work', '/opt/router.php'],
        'networks': [name], 'depends_on': {f'{name}-editor': {'condition': 'service_healthy'}},
        'tmpfs': ['/tmp:uid=1000,gid=1000,mode=1777,size=32m'], 'mem_limit': '256m', 'cpus': 0.5,
    }

maps = []
for key, target in [('editor', 'editor:8080'), ('runtime', 'runtime:8080'), ('attacker', 'editor:8084')]:
    default = 'portal:8080' if key == 'editor' else 'denied'
    rows = '\n'.join(f'    "{s["token"]}" {s["name"]}-{target};' for s in seats)
    maps.append(f'map $cookie_lab_workspace ${key} {{\n    default {default};\n{rows}\n}}')
conf = '''pid /tmp/nginx.pid;
worker_processes 1;
error_log /dev/stderr warn;
events { worker_connections 1024; }
http {
    map_hash_bucket_size 128;
    resolver 127.0.0.11 ipv6=off valid=5s;
    access_log off;
    client_body_temp_path /tmp/client;
    proxy_temp_path /tmp/proxy;
    fastcgi_temp_path /tmp/fastcgi;
    uwsgi_temp_path /tmp/uwsgi;
    scgi_temp_path /tmp/scgi;
    proxy_read_timeout 10s;
    client_max_body_size 64k;
'''+ '\n'.join(maps) + f'''
    server {{
        listen {args.editor_port};
        if ($http_host != "{args.host}:{args.editor_port}") {{ return 403; }}
        location ~ ^/(login|logout)$ {{
            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_pass http://portal:8080;
        }}
        location / {{
            proxy_set_header Host $http_host;
            proxy_pass http://$editor;
        }}
    }}
    server {{
        listen {args.runtime_port};
        if ($http_host != "{args.host}:{args.runtime_port}") {{ return 403; }}
        location / {{
            if ($runtime = denied) {{ return 401; }}
            proxy_set_header Host $http_host;
            # Never forward the classroom credential into editable PHP.
            proxy_set_header Cookie "lab_csrf=$cookie_lab_csrf; lab_access=$cookie_lab_access; PHPSESSID=$cookie_PHPSESSID";
            proxy_pass http://$runtime;
        }}
    }}
    server {{
        listen {args.attacker_port};
        if ($http_host != "{args.host}:{args.attacker_port}") {{ return 403; }}
        location / {{
            if ($attacker = denied) {{ return 401; }}
            proxy_set_header Host $http_host;
            proxy_pass http://$attacker;
        }}
    }}
}}
'''
services['gateway'] = {
    **restrict, 'image': 'nginx:1.28-alpine', 'user': config_user, 'entrypoint': ['nginx', '-g', 'daemon off;'],
    'ports': [f'{args.bind}:{p}:{p}' for p in ports],
    'volumes': [f'{out}/nginx.conf:/etc/nginx/nginx.conf:ro'],
    'networks': list(networks), 'depends_on': ['portal'] + [f'{s["name"]}-runtime' for s in seats],
    'mem_limit': '128m', 'tmpfs': ['/tmp:uid=1000,gid=1000,mode=1777,size=16m'],
    'healthcheck': {'test': ['CMD', 'wget', '-q', '-O', '/dev/null', '--header', f'Host: {args.host}:{args.editor_port}', f'http://127.0.0.1:{args.editor_port}/'], 'interval': '3s', 'timeout': '2s', 'retries': 10},
}
for file, data in [('seats.json', json.dumps(seats)), ('roster.json', json.dumps(roster)), ('compose.json', json.dumps({'name': 'secure-coding-classroom', 'services': services, 'networks': networks, 'volumes': volumes}, indent=2)), ('nginx.conf', conf)]:
    target = out / file
    target.write_text(data + '\n')
    target.chmod(0o600)
(out / 'roster.csv').write_text('受講者,受講コード\n' + '\n'.join(f'{x["name"]},{x["code"]}' for x in roster) + '\n')
(out / 'roster.csv').chmod(0o600)
print(f'設定を作成しました: {out}/compose.json')
print(f'講師用の受講コード一覧: {out}/roster.csv （各自の1行だけを配布）')
print(f'共通の入口: {origin}')
print(f'起動: docker compose -f {out}/compose.json up --build -d --wait')
