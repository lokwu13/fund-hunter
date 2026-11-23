# -*- coding: utf-8 -*-
"""外资摘要双卡删除：实时 main、活动前端与线上生产 JSON 只读预检。"""
import base64
import hashlib
import json
import subprocess
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
REPO = 'lokwu13/fund-hunter'
BASE = 'https://lokwu13.github.io/fund-hunter/'
PANEL = 'src/sections/ForeignCapitalPanel.tsx'
BACKEND = 'scripts/update_data.py'
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
PROTECTED_FRONTEND = ['src/App.tsx', 'src/hooks/useFundData.ts']

cred = subprocess.run(
    ['git', 'credential', 'fill'],
    input='protocol=https\nhost=github.com\n\n',
    text=True, capture_output=True, check=True,
).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
api = requests.Session()
api.headers.update({
    'Authorization': f"Bearer {fields['password']}",
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'fund-hunter-delete-table-preflight',
})
web = requests.Session()
web.headers.update({'User-Agent': 'fund-hunter-delete-table-readonly'})


def req(path):
    response = api.get('https://api.github.com' + path, timeout=60)
    response.raise_for_status()
    return response.json()


def content(path, ref):
    obj = req(f'/repos/{REPO}/contents/{path}?ref={ref}')
    if obj.get('content'):
        return base64.b64decode(obj['content']), obj['sha']
    blob = req(f'/repos/{REPO}/git/blobs/{obj["sha"]}')
    return base64.b64decode(blob['content']), obj['sha']


head = req(f'/repos/{REPO}/git/ref/heads/main')['object']['sha']
commit = req(f'/repos/{REPO}/git/commits/{head}')
remote_panel, panel_blob = content(PANEL, head)
local_panel = (ROOT / PANEL).read_bytes()
line_ending_only = (
    remote_panel.decode('utf-8').replace('\r\n', '\n')
    == local_panel.decode('utf-8').replace('\r\n', '\n')
)
assert remote_panel == local_panel or line_ending_only, '本地外资面板与实时 main 存在实质差异，先审计'
assert '北向成交 (本周)' in remote_panel.decode('utf-8')
assert '南下资金 (本周)' in remote_panel.decode('utf-8')
(ROOT / 'zz_delete_table_ForeignCapitalPanel_baseline.tsx').write_bytes(remote_panel)

remote_backend, backend_blob = content(BACKEND, head)
assert remote_backend == (ROOT / BACKEND).read_bytes(), '后端与实时 main 不一致，先审计'
(ROOT / 'zz_delete_table_update_data_baseline.py').write_bytes(remote_backend)

protected = {}
for path in PROTECTED_FRONTEND:
    raw, blob = content(path, head)
    local = (ROOT / path).read_bytes()
    assert raw == local, f'{path} 本地与实时 main 不一致，先审计'
    protected[path] = {
        'remoteSha256': hashlib.sha256(raw).hexdigest(),
        'remoteBlob': blob,
        'localSha256': hashlib.sha256(local).hexdigest(),
        'matched': True,
    }

fund_data = {}
remote_public = None
for path in DATA:
    raw, blob = content(path, head)
    local = (ROOT / path).read_bytes()
    fund_data[path] = {
        'remoteBytes': len(raw),
        'remoteSha256': hashlib.sha256(raw).hexdigest(),
        'remoteBlob': blob,
        'localBytes': len(local),
        'localSha256': hashlib.sha256(local).hexdigest(),
    }
    if path == 'public/fund_data.json':
        remote_public = raw

online = web.get(BASE + 'fund_data.json', params={'v': head}, timeout=90)
online.raise_for_status()
assert online.content == remote_public, '线上生产 JSON 与实时 main 不一致，先审计部署状态'

result = {
    'task': 'delete-table',
    'head': head,
    'headTree': commit['tree']['sha'],
    'headMessage': commit['message'],
    'panelBaselineMatched': True,
    'panelLineEndingOnlyDifference': line_ending_only and remote_panel != local_panel,
    'remotePanelSha256': hashlib.sha256(remote_panel).hexdigest(),
    'remotePanelBlob': panel_blob,
    'backendBaselineMatched': True,
    'remoteBackendSha256': hashlib.sha256(remote_backend).hexdigest(),
    'remoteBackendBlob': backend_blob,
    'protectedFrontend': protected,
    'fundData': fund_data,
    'onlineFundDataSha256': hashlib.sha256(online.content).hexdigest(),
    'onlineEqualsRemoteMain': True,
    'targetTitles': ['北向成交 (本周)', '南下资金 (本周)'],
    'manualDispatch': False,
    'workflowModified': False,
    'scheduleModified': False,
}
(ROOT / 'zz_delete_table_live_preflight.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
)
print(json.dumps(result, ensure_ascii=False, indent=2))
