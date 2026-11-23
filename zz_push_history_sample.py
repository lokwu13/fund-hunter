# -*- coding: utf-8 -*-
"""历史估值快照修复：实时main基树/父提交Git Data API发布，force=False。"""
import base64
import concurrent.futures
import hashlib
import json
import subprocess
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
REPO = 'lokwu13/fund-hunter'
FILES = [
    'scripts/update_data.py', 'scripts/oversold_concept_members.py',
    'src/hooks/useFundData.ts', 'src/sections/SectorHeatmap.tsx',
    'zz_regress116.py', 'zz_regress116_summary.json',
    'zz_regress108_summary.json', 'zz_concept_sample_regress.json', 'zz_joint_regress116.json',
    'zz_history_sample_live_preflight.py', 'zz_history_sample_live_preflight.json',
    'zz_history_sample_online_module.json', 'zz_history_sample_real_identity.json',
    'zz_history_sample_regress.py', 'zz_history_sample_regress.json',
    'zz_history_sample_real_coverage.py', 'zz_history_sample_real_coverage.json',
    'zz_history_sample_build.py', 'zz_history_sample_build.json', 'zz_history_sample_build.log',
    'zz_history_sample_machine_verification.py', 'zz_history_sample_machine_verification.json',
    'zz_push_history_sample.py', 'zz_verify_history_sample_online.py',
]
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
FORBIDDEN = ['scripts/cache/vcp_cache.json', 'zz_history_sample_remote_vcp_cache.json',
             'zz_history_sample_real_members.json', 'zz_history_sample_issue.png', 'dist']
assert len(FILES) == len(set(FILES)) and not set(FILES) & set(DATA + FORBIDDEN)
assert not any(name.startswith(('.github/', 'dist/')) or 'cache/' in name or name.endswith('.png') for name in FILES)
assert all((ROOT / name).is_file() for name in FILES)
machine = json.loads((ROOT / 'zz_history_sample_machine_verification.json').read_text(encoding='utf-8'))
assert machine['allPassed'] and machine['codeReleaseReady'] and not machine['realDataRecoveryComplete']
assert machine['nextNormalNightlyRequired'] and not machine['manualDispatch'] and not machine['workflowModified']
regress = json.loads((ROOT / 'zz_history_sample_regress.json').read_text(encoding='utf-8'))
assert regress['passed'] == regress['total'] == 19 and not regress['failed']
real = json.loads((ROOT / 'zz_history_sample_real_coverage.json').read_text(encoding='utf-8'))
assert len(real['items']) == 11 and not real['allElevenRecovered'] and not real['coverageEvaluationComplete']
preflight = json.loads((ROOT / 'zz_history_sample_live_preflight.json').read_text(encoding='utf-8'))
assert all(x['matched'] for x in preflight['baselines'].values()) and preflight['onlineEqualsRemoteMain']

cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
s = requests.Session()
s.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                  'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-history-sample-push'})

def req(method, path, **kwargs):
    response = s.request(method, 'https://api.github.com' + path, timeout=60, **kwargs)
    if not response.ok:
        raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:500]}')
    return response.json()

def item(path, ref):
    return req('GET', f'/repos/{REPO}/contents/{path}?ref={ref}')

def content(path, ref):
    obj = item(path, ref)
    if obj.get('content'):
        return base64.b64decode(obj['content'])
    return base64.b64decode(req('GET', f'/repos/{REPO}/git/blobs/{obj["sha"]}')['content'])

def data_state(ref=None):
    result = {}
    for path in DATA:
        if ref:
            raw = content(path, ref)
            result[path] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        else:
            raw = (ROOT / path).read_bytes()
            result[path] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    return result

before_local = data_state()
assert all(before_local[p]['sha256'] == machine['productionFundDataSha256'][p] for p in DATA)
head = req('GET', f'/repos/{REPO}/git/ref/heads/main')['object']['sha']
head_commit = req('GET', f'/repos/{REPO}/git/commits/{head}')
if head != preflight['head'] or head_commit['tree']['sha'] != preflight['headTree']:
    raise RuntimeError(f'实时main已从预检基线变化：{head}；停止发布并重新审计')
if content('scripts/update_data.py', head) != (ROOT / 'zz_history_sample_update_data_baseline.py').read_bytes():
    raise RuntimeError('实时main后端不再逐字节等于预检基线，停止发布')
before_remote = data_state(head)
assert all(before_remote[p]['sha256'] == preflight['fundData'][p]['remoteSha256'] for p in DATA)
print('REAL_HEAD', head, head_commit['message'], flush=True)

def upload(name):
    raw = (ROOT / name).read_bytes()
    blob = req('POST', f'/repos/{REPO}/git/blobs', json={
        'content': base64.b64encode(raw).decode('ascii'), 'encoding': 'base64'})
    return {'path': name, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']}

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    tree_items = list(pool.map(upload, FILES))
tree = req('POST', f'/repos/{REPO}/git/trees', json={'base_tree': head_commit['tree']['sha'], 'tree': tree_items})
commit = req('POST', f'/repos/{REPO}/git/commits', json={
    'message': '修复超跌估值真实A股成分与历史补样', 'tree': tree['sha'], 'parents': [head]})
updated = req('PATCH', f'/repos/{REPO}/git/refs/heads/main', json={'sha': commit['sha'], 'force': False})
print('PUSHED', commit['sha'], flush=True)
after_remote = data_state(commit['sha'])
after_local = data_state()
assert before_local == after_local and before_remote == after_remote
for name in FILES:
    assert content(name, commit['sha']) == (ROOT / name).read_bytes(), name
comparison = req('GET', f'/repos/{REPO}/compare/{head}...{commit["sha"]}')
changed = {x['filename'] for x in comparison.get('files') or []}
assert changed <= set(FILES) and not changed & set(DATA + FORBIDDEN)
assert not any(x.startswith(('.github/', 'dist/')) or x.endswith('.png') for x in changed)
assert req('GET', f'/repos/{REPO}/git/ref/heads/main')['object']['sha'] == commit['sha']
result = {
    'task': 'history-sample', 'realHead': head, 'realHeadTree': head_commit['tree']['sha'],
    'realHeadMessage': head_commit['message'], 'commit': commit['sha'], 'tree': tree['sha'],
    'parent': head, 'ref': updated['object']['sha'], 'files': FILES, 'changedFiles': sorted(changed),
    'force': False, 'manualDispatch': False, 'nightlyExecuted': False,
    'workflowModified': False, 'scheduleModified': False,
    'localFundDataBefore': before_local, 'localFundDataAfter': after_local,
    'remoteFundDataBefore': before_remote, 'remoteFundDataAfter': after_remote,
    'remoteFilesContentVerified': True, 'fundDataUnchanged': True,
    'productionDataRegenerated': False, 'screenshotsIncluded': False,
    'realDataRecoveryComplete': False, 'nextNormalNightlyRequired': True,
}
(ROOT / 'zz_push_history_sample.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('VERIFIED', commit['sha'], flush=True)
