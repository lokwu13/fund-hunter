# -*- coding: utf-8 -*-
"""任务115发布前实时main/生产数据只读预检。"""
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
                  'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-task115-preflight'})

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
remote_source, source_blob = content('scripts/update_data.py', head)
baseline = (ROOT / 'zz_update_data_task115_baseline.py').read_bytes()
assert remote_source == baseline, '实时main的任务114源码基线已变化，停止自动发布'
data = {}
for path in ('public/fund_data.json', 'src/data/fund_data.json'):
    raw, blob = content(path, head)
    data[path] = {'remoteBytes': len(raw), 'remoteSha256': hashlib.sha256(raw).hexdigest(), 'remoteBlob': blob,
                  'localBytes': (ROOT / path).stat().st_size,
                  'localSha256': hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
result = {'task': 115, 'head': head, 'headTree': commit['tree']['sha'], 'headMessage': commit['message'],
          'remoteTask114SourceSha256': hashlib.sha256(remote_source).hexdigest(), 'remoteSourceBlob': source_blob,
          'task114SourceBaselineMatched': True, 'fundData': data,
          'manualDispatch': False, 'workflowModified': False, 'scheduleModified': False}
(ROOT / 'zz_task115_live_preflight.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
