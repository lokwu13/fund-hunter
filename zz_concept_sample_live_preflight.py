# -*- coding: utf-8 -*-
"""概念样本问题实时main、线上生产模块与真实vcp缓存只读预检。"""
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
                  'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-concept-sample-preflight'})
web = requests.Session()
web.headers.update({'User-Agent': 'fund-hunter-concept-sample-readonly'})


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
remote_backend, backend_blob = content('scripts/update_data.py', head)
local_backend = (ROOT / 'scripts/update_data.py').read_bytes()
assert remote_backend == local_backend, '本地后端与实时main存在差异，先审计'
(ROOT / 'zz_concept_sample_update_data_baseline.py').write_bytes(remote_backend)
remote_data, data_blob = content('public/fund_data.json', head)
online_response = web.get(BASE + 'fund_data.json', params={'v': head}, timeout=90)
online_response.raise_for_status()
online_raw = online_response.content
assert online_raw == remote_data, '线上生产JSON与实时main不一致，先审计部署状态'
production = json.loads(remote_data.decode('utf-8'))
module = production.get('sectorCrowding') or {}
(ROOT / 'zz_concept_sample_online_module.json').write_text(
    json.dumps(module, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
cache_raw, cache_blob = content('scripts/cache/vcp_cache.json', head)
cache = json.loads(cache_raw.decode('utf-8'))
(ROOT / 'zz_concept_sample_remote_vcp_cache.json').write_bytes(cache_raw)
local_cache_raw = (ROOT / 'scripts/cache/vcp_cache.json').read_bytes()
data = {}
for path in ('public/fund_data.json', 'src/data/fund_data.json'):
    raw, blob = content(path, head)
    data[path] = {'remoteBytes': len(raw), 'remoteSha256': hashlib.sha256(raw).hexdigest(), 'remoteBlob': blob,
                  'localBytes': (ROOT / path).stat().st_size,
                  'localSha256': hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
result = {
    'task': 'concept-sample', 'head': head, 'headTree': commit['tree']['sha'], 'headMessage': commit['message'],
    'remoteBackendSha256': hashlib.sha256(remote_backend).hexdigest(), 'remoteBackendBlob': backend_blob,
    'backendBaselineMatched': True,
    'onlineFundDataSha256': hashlib.sha256(online_raw).hexdigest(), 'onlineEqualsRemoteMain': True,
    'onlineSectorCrowding': module,
    'remoteCache': {'bytes': len(cache_raw), 'sha256': hashlib.sha256(cache_raw).hexdigest(),
                    'tradeDate': cache.get('trade_date'), 'conceptCount': len(cache.get('concepts') or []),
                    'thsIndexCount': len(cache.get('ths_index') or {}),
                    'indexDailyCount': len(cache.get('index_daily') or {}),
                    'localBytes': len(local_cache_raw), 'localSha256': hashlib.sha256(local_cache_raw).hexdigest(),
                    'localTradeDate': json.loads(local_cache_raw.decode('utf-8')).get('trade_date')},
    'fundData': data, 'manualDispatch': False, 'workflowModified': False, 'scheduleModified': False,
}
(ROOT / 'zz_concept_sample_live_preflight.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k != 'onlineSectorCrowding'}, ensure_ascii=False, indent=2))
print('ONLINE_SECTOR_CROWDING', json.dumps(module, ensure_ascii=False))
