# -*- coding: utf-8 -*-
"""历史估值当前快照问题：实时main、线上生产模块和远端缓存只读预检。"""
import base64
import hashlib
import json
import subprocess
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
REPO = 'lokwu13/fund-hunter'
BASE = 'https://lokwu13.github.io/fund-hunter/'
cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
s = requests.Session()
s.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                  'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-history-sample-preflight'})
web = requests.Session()
web.headers.update({'User-Agent': 'fund-hunter-history-sample-readonly'})

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
baselines = {}
for path, target in [('scripts/update_data.py', 'zz_history_sample_update_data_baseline.py'),
                     ('scripts/vcp_preview.py', 'zz_history_sample_vcp_preview_baseline.py')]:
    raw, blob = content(path, head)
    assert raw == (ROOT / path).read_bytes(), f'{path}本地与实时main不同，先审计'
    (ROOT / target).write_bytes(raw)
    baselines[path] = {'sha256': hashlib.sha256(raw).hexdigest(), 'blob': blob, 'matched': True}
remote_data, data_blob = content('public/fund_data.json', head)
online = web.get(BASE + 'fund_data.json', params={'v': head}, timeout=90)
online.raise_for_status()
assert online.content == remote_data, '线上生产JSON与实时main不一致，先审计部署状态'
production = json.loads(remote_data.decode('utf-8'))
module = production.get('oversoldValueDirections') or {}
(ROOT / 'zz_history_sample_online_module.json').write_text(
    json.dumps(module, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
cache_raw, cache_blob = content('scripts/cache/vcp_cache.json', head)
(ROOT / 'zz_history_sample_remote_vcp_cache.json').write_bytes(cache_raw)
cache = json.loads(cache_raw.decode('utf-8'))
local_cache_raw = (ROOT / 'scripts/cache/vcp_cache.json').read_bytes()
data = {}
for path in ('public/fund_data.json', 'src/data/fund_data.json'):
    raw, blob = content(path, head)
    data[path] = {'remoteBytes': len(raw), 'remoteSha256': hashlib.sha256(raw).hexdigest(), 'remoteBlob': blob,
                  'localBytes': (ROOT / path).stat().st_size,
                  'localSha256': hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
concept_coverage = []
history = (cache.get('sectorValuationHistory') or {}).get('rows') or {}
for concept in cache.get('concepts') or []:
    code = concept.get('code')
    members = (cache.get('ths_members') or {}).get(code) or []
    current = next((x for x in module.get('concepts') or [] if x.get('name') == concept.get('name')), {})
    concept_coverage.append({'name': concept.get('name'), 'code': code, 'memberCountCache': len(members),
                             'historyMemberCount': current.get('memberCount'),
                             'snapshotCount': current.get('snapshotCount'), 'peCount': current.get('peCount'),
                             'pbCount': current.get('pbCount'), 'peHistorySamples': current.get('peHistorySamples'),
                             'pbHistorySamples': current.get('pbHistorySamples'),
                             'historyStatus': current.get('historyStatus'),
                             'historyKeys': sum(1 for rows in history.values()
                                                for key in rows if key == f"concept:{code}")})
result = {
    'task': 'history-sample', 'head': head, 'headTree': commit['tree']['sha'], 'headMessage': commit['message'],
    'baselines': baselines, 'onlineFundDataSha256': hashlib.sha256(online.content).hexdigest(),
    'onlineEqualsRemoteMain': True,
    'onlineModuleSummary': {'tradeDate': module.get('tradeDate'), 'snapshotDate': module.get('snapshotDate'),
                            'valuationStatus': module.get('valuationStatus'), 'counts': module.get('counts'),
                            'reasons': module.get('reasons'), 'historySampling': module.get('historySampling')},
    'remoteCache': {'bytes': len(cache_raw), 'sha256': hashlib.sha256(cache_raw).hexdigest(),
                    'tradeDate': cache.get('trade_date'), 'conceptCount': len(cache.get('concepts') or []),
                    'thsIndexCount': len(cache.get('ths_index') or {}),
                    'thsMembersCount': len(cache.get('ths_members') or {}),
                    'historyMonthEnds': len(history),
                    'localBytes': len(local_cache_raw), 'localSha256': hashlib.sha256(local_cache_raw).hexdigest()},
    'conceptCoverage': concept_coverage, 'fundData': data,
    'manualDispatch': False, 'workflowModified': False, 'scheduleModified': False,
}
(ROOT / 'zz_history_sample_live_preflight.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
