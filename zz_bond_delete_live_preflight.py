# -*- coding: utf-8 -*-
"""债券栏目删减实时main只读预检；保存任务116后端与BondsPanel基线。"""
import base64
import hashlib
import json
import subprocess
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
REPO = 'lokwu13/fund-hunter'
cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
s = requests.Session()
s.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                  'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-bond-delete-preflight'})


def req(path):
    response = s.get('https://api.github.com' + path, timeout=60)
    response.raise_for_status()
    return response.json()


def content(path, ref):
    obj = req(f'/repos/{REPO}/contents/{path}?ref={ref}')
    if obj.get('content'):
        return base64.b64decode(obj['content']), obj['sha']
    return base64.b64decode(req(f'/repos/{REPO}/git/blobs/{obj["sha"]}')['content']), obj['sha']


head = req(f'/repos/{REPO}/git/ref/heads/main')['object']['sha']
commit = req(f'/repos/{REPO}/git/commits/{head}')
remote_panel, panel_blob = content('src/sections/BondsPanel.tsx', head)
local_panel = (ROOT / 'src/sections/BondsPanel.tsx').read_bytes()
remote_backend, backend_blob = content('scripts/update_data.py', head)
(ROOT / 'zz_bond_delete_BondsPanel_baseline.tsx').write_bytes(remote_panel)
(ROOT / 'zz_bond_delete_update_data_baseline.py').write_bytes(remote_backend)
print('HEAD_FOR_AUDIT', head, commit['message'], flush=True)
line_ending_only = remote_panel.decode('utf-8').replace('\r\n', '\n') == local_panel.decode('utf-8').replace('\r\n', '\n')
assert remote_panel == local_panel or line_ending_only, '本地BondsPanel.tsx与实时main存在实质差异，先审计差异'
assert remote_backend == (ROOT / 'scripts/update_data.py').read_bytes(), '后端与实时main不一致，先审计差异'
data = {}
for path in ('public/fund_data.json', 'src/data/fund_data.json'):
    raw, blob = content(path, head)
    data[path] = {'remoteBytes': len(raw), 'remoteSha256': hashlib.sha256(raw).hexdigest(), 'remoteBlob': blob,
                  'localBytes': (ROOT / path).stat().st_size,
                  'localSha256': hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
result = {
    'task': 'bond-delete', 'head': head, 'headTree': commit['tree']['sha'], 'headMessage': commit['message'],
    'remoteBondsPanelSha256': hashlib.sha256(remote_panel).hexdigest(), 'remoteBondsPanelBlob': panel_blob,
    'remoteBackendSha256': hashlib.sha256(remote_backend).hexdigest(), 'remoteBackendBlob': backend_blob,
    'bondsPanelBaselineMatched': True, 'bondsPanelLineEndingOnlyDifference': line_ending_only and remote_panel != local_panel,
    'backendBaselineMatched': True, 'fundData': data,
    'targetTitles': ['债券市场要闻', '中美国债收益率对比'],
    'manualDispatch': False, 'workflowModified': False, 'scheduleModified': False,
}
(ROOT / 'zz_bond_delete_live_preflight.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
