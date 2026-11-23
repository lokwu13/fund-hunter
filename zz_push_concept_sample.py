# -*- coding: utf-8 -*-
"""概念真实样本修复Git Data API发布：实时main基树/父提交，force=False。"""
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
    'scripts/update_data.py', 'scripts/vcp_preview.py',
    'src/hooks/useFundData.ts', 'src/sections/SectorHeatmap.tsx',
    'zz_concept_sample_live_preflight.py', 'zz_concept_sample_live_preflight.json',
    'zz_concept_sample_online_module.json',
    'zz_concept_sample_real_coverage.py', 'zz_concept_sample_real_coverage.json',
    'zz_concept_sample_regress.py', 'zz_concept_sample_regress.json',
    'zz_concept_sample_machine_verification.py', 'zz_concept_sample_machine_verification.json',
    'zz_regress94.py', 'zz_regress94.json', 'zz_regress94b.py', 'zz_regress94b.json',
    'zz_regress_bond_delete.py', 'zz_regress_bond_delete_report.json', 'zz_regress_bond_delete_summary.json',
    'zz_push_concept_sample.py', 'zz_verify_concept_sample_online.py',
]
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
FORBIDDEN = ['scripts/cache/vcp_cache.json', 'zz_concept_sample_real_cache.json',
             'zz_concept_sample_remote_vcp_cache.json', 'zz_concept_sample_issue.png']
assert len(FILES) == len(set(FILES)) and not set(FILES) & set(DATA + FORBIDDEN)
assert not any(name.startswith(('.github/', 'dist/')) or 'cache/' in name or name.endswith('.png') for name in FILES)
assert all((ROOT / name).is_file() for name in FILES)
machine = json.loads((ROOT / 'zz_concept_sample_machine_verification.json').read_text(encoding='utf-8'))
assert machine['allPassed'] and machine['checksPassed'] == machine['checksTotal'] == 14
assert not machine['manualDispatch'] and not machine['workflowModified'] and not machine['scheduleModified']
regress = json.loads((ROOT / 'zz_concept_sample_regress.json').read_text(encoding='utf-8'))
assert regress['passed'] == regress['total'] == 13
real = json.loads((ROOT / 'zz_concept_sample_real_coverage.json').read_text(encoding='utf-8'))
assert real['coverage']['heatReady'] and all(real['coverage']['dailySamples'][d] >= 20 for d in real['coverage']['last10'])
for path, total in [('zz_regress94.json', 32), ('zz_regress94b.json', 18)]:
    obj = json.loads((ROOT / path).read_text(encoding='utf-8'))
    assert obj['passed'] == obj['total'] == total
bond = json.loads((ROOT / 'zz_regress_bond_delete_summary.json').read_text(encoding='utf-8'))
assert bond['allPassed'] and bond['checksPassed'] == bond['checksTotal'] == 19
preflight = json.loads((ROOT / 'zz_concept_sample_live_preflight.json').read_text(encoding='utf-8'))
assert preflight['backendBaselineMatched'] and preflight['onlineEqualsRemoteMain']
assert not preflight['manualDispatch'] and not preflight['workflowModified'] and not preflight['scheduleModified']

cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
s = requests.Session()
s.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                  'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-concept-sample-push'})

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

def local_data():
    return {p: {'bytes': (ROOT / p).stat().st_size,
                'sha256': hashlib.sha256((ROOT / p).read_bytes()).hexdigest()} for p in DATA}

def remote_data(ref):
    result = {}
    for path in DATA:
        obj = item(path, ref)
        raw = content(path, ref)
        result[path] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'blobSha': obj['sha']}
    return result

before_local = local_data()
assert all(x['sha256'] == machine['production'][p]['sha256'] for p, x in before_local.items())
head = req('GET', f'/repos/{REPO}/git/ref/heads/main')['object']['sha']
head_commit = req('GET', f'/repos/{REPO}/git/commits/{head}')
if head != preflight['head'] or head_commit['tree']['sha'] != preflight['headTree']:
    raise RuntimeError(f'实时main已从预检基线变化：{head}；停止发布并重新审计')
if content('scripts/update_data.py', head) != (ROOT / 'zz_concept_sample_update_data_baseline.py').read_bytes():
    raise RuntimeError('实时main后端不再逐字节等于预检基线，停止发布')
before_remote = remote_data(head)
assert all(before_remote[p]['sha256'] == preflight['fundData'][p]['remoteSha256'] for p in DATA)
print('REAL_HEAD', head, head_commit['message'], flush=True)
print('DATA_BEFORE', json.dumps({'local': before_local, 'remote': before_remote}, ensure_ascii=False), flush=True)

def upload(name):
    raw = (ROOT / name).read_bytes()
    blob = req('POST', f'/repos/{REPO}/git/blobs', json={
        'content': base64.b64encode(raw).decode('ascii'), 'encoding': 'base64'})
    return {'path': name, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']}

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    tree_items = list(pool.map(upload, FILES))
tree = req('POST', f'/repos/{REPO}/git/trees', json={'base_tree': head_commit['tree']['sha'], 'tree': tree_items})
commit = req('POST', f'/repos/{REPO}/git/commits', json={
    'message': '修复概念拥挤度真实样本与成交额数据链', 'tree': tree['sha'], 'parents': [head]})
updated = req('PATCH', f'/repos/{REPO}/git/refs/heads/main', json={'sha': commit['sha'], 'force': False})
print('PUSHED', commit['sha'], flush=True)
after_remote = remote_data(commit['sha'])
after_local = local_data()
assert before_local == after_local and before_remote == after_remote
for name in FILES:
    assert content(name, commit['sha']) == (ROOT / name).read_bytes(), name
comparison = req('GET', f'/repos/{REPO}/compare/{head}...{commit["sha"]}')
changed = {x['filename'] for x in comparison.get('files') or []}
assert changed <= set(FILES) and not changed & set(DATA + FORBIDDEN)
assert not any(x.startswith(('.github/', 'dist/')) or x.endswith('.png') for x in changed)
assert req('GET', f'/repos/{REPO}/git/ref/heads/main')['object']['sha'] == commit['sha']
result = {
    'task': 'concept-sample', 'realHead': head, 'realHeadMessage': head_commit['message'],
    'realHeadTree': head_commit['tree']['sha'], 'commit': commit['sha'], 'tree': tree['sha'],
    'ref': updated['object']['sha'], 'parent': head, 'files': FILES, 'changedFiles': sorted(changed),
    'force': False, 'manualDispatch': False, 'nightlyExecuted': False,
    'workflowModified': False, 'scheduleModified': False,
    'localFundDataBefore': before_local, 'localFundDataAfter': after_local,
    'remoteFundDataBefore': before_remote, 'remoteFundDataAfter': after_remote,
    'remoteFilesContentVerified': True, 'fundDataUnchanged': True,
    'productionDataRegenerated': False, 'screenshotsIncluded': False,
}
(ROOT / 'zz_push_concept_sample.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('VERIFIED', commit['sha'], flush=True)
