# -*- coding: utf-8 -*-
"""任务1141：实时 main、受保护文件、缓存与线上两榜 as-of 预检。"""
import base64
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
REPO = 'lokwu13/fund-hunter'
PREVIOUS = '111e3fe98c5c66e885fa457e79f609b62808a6bd'
FILES = {
    'src/sections/ForeignCapitalPanel.tsx': 'zz_daily_tables_1141_ForeignCapitalPanel_baseline.tsx',
    'scripts/update_data.py': 'zz_daily_tables_1141_update_data_baseline.py',
    '.github/workflows/daily-update.yml': 'zz_daily_tables_1141_daily_update_baseline.yml',
}
DATA = ['public/fund_data.json', 'src/data/fund_data.json']

cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
api = requests.Session()
api.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-daily-tables-1141-preflight'})


def req(path):
    response = api.get('https://api.github.com' + path, timeout=60)
    response.raise_for_status()
    return response.json()


def content(path, ref):
    obj = req(f'/repos/{REPO}/contents/{path}?ref={ref}')
    if obj.get('content'):
        return base64.b64decode(obj['content'])
    blob = req(f'/repos/{REPO}/git/blobs/{obj["sha"]}')
    return base64.b64decode(blob['content'])


head = req(f'/repos/{REPO}/git/ref/heads/main')['object']['sha']
commit = req(f'/repos/{REPO}/git/commits/{head}')
report = {
    'task': 'daily-tables-1141', 'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
    'previousHead': PREVIOUS, 'head': head, 'headTree': commit['tree']['sha'],
    'headMessage': commit['message'], 'changedSincePrevious': head != PREVIOUS,
    'protectedFiles': {}, 'fundData': {}, 'manualDispatch': False,
}
for path, baseline in FILES.items():
    raw = content(path, head)
    local = (ROOT / path).read_bytes()
    (ROOT / baseline).write_bytes(raw)
    report['protectedFiles'][path] = {
        'remoteSha256': hashlib.sha256(raw).hexdigest(),
        'localSha256': hashlib.sha256(local).hexdigest(),
        'matched': raw == local, 'baseline': baseline,
    }
assert all(item['matched'] for item in report['protectedFiles'].values()), '本地受保护文件与实时 main 不一致，停止修改'
for path in DATA:
    raw = content(path, head)
    local = (ROOT / path).read_bytes()
    report['fundData'][path] = {
        'remoteSha256': hashlib.sha256(raw).hexdigest(), 'remoteBytes': len(raw),
        'localSha256': hashlib.sha256(local).hexdigest(), 'localBytes': len(local),
        'matched': raw == local,
    }
remote_doc = json.loads(content('public/fund_data.json', head))
cache_raw = content('scripts/cache/ccass_history.json', head)
cache = json.loads(cache_raw)
online_response = requests.get('https://lokwu13.github.io/fund-hunter/fund_data.json', timeout=90)
online_response.raise_for_status()
online_doc = online_response.json()
report['onlineFundDataSha256'] = hashlib.sha256(online_response.content).hexdigest()
report['onlineEqualsRemoteMain'] = online_response.content == content('public/fund_data.json', head)
report['ccassCache'] = {
    'remoteSha256': hashlib.sha256(cache_raw).hexdigest(),
    'monthlyDates': sorted(cache.get('snapshots') or {}),
    'dailyNamespaces': sorted((cache.get('concentrationSnapshots') or {})),
}
report['remoteAsOf'] = {key: remote_doc.get('dataSources', {}).get(key)
                        for key in ('southbound_concentration_top10', 'foreign_concentration_top10')}
report['onlineAsOf'] = {key: online_doc.get('dataSources', {}).get(key)
                        for key in ('southbound_concentration_top10', 'foreign_concentration_top10')}
report['workflowModified'] = False
report['scheduleModified'] = False
(ROOT / 'zz_daily_tables_1141_live_preflight.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
