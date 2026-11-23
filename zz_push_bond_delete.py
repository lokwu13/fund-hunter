# -*- coding: utf-8 -*-
"""债券栏目删减Git Data API发布：实时main基树/父提交，force=False，不触生产数据/workflow。"""
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
    'src/sections/BondsPanel.tsx',
    'zz_bond_delete_BondsPanel_baseline.tsx', 'zz_bond_delete_update_data_baseline.py',
    'zz_regress_bond_delete.py', 'zz_regress_bond_delete_summary.json', 'zz_regress_bond_delete_report.json',
    'zz_build_bond_delete.py', 'zz_build_bond_delete.json', 'zz_build_bond_delete.log',
    'zz_bond_delete_report.md', 'zz_bond_delete_machine_verification.py', 'zz_bond_delete_machine_verification.json',
    'zz_bond_delete_live_preflight.py', 'zz_bond_delete_live_preflight.json',
    'zz_push_bond_delete.py', 'zz_verify_bond_delete_online.py',
]
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
assert len(FILES) == len(set(FILES)) and not set(FILES) & set(DATA)
assert not any(name.startswith('.github/') or name.startswith('dist/') for name in FILES)
assert not any('__pycache__' in name or 'cache/' in name or name.endswith('.png') for name in FILES)
assert all((ROOT / name).is_file() for name in FILES)
regression = json.loads((ROOT / 'zz_regress_bond_delete_summary.json').read_text(encoding='utf-8'))
assert regression['allPassed'] and regression['checksPassed'] == regression['checksTotal'] == 19
assert not regression['failed'] and not regression['productionDataRegenerated']
build = json.loads((ROOT / 'zz_build_bond_delete.json').read_text(encoding='utf-8'))
assert build['success'] and build['returncode'] == 0 and build['matchesRegressionDataSha']
assert build['fundDataUnchanged'] and not build['developmentServerStarted']
assert all(build['retainedBundleMarkers'].values()) and not any(build['removedBundleMarkersPresent'].values())
machine = json.loads((ROOT / 'zz_bond_delete_machine_verification.json').read_text(encoding='utf-8'))
assert machine['allPassed'] and machine['releaseReady']
assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == sha
           for p, sha in machine['sourceSha256'].items())
preflight = json.loads((ROOT / 'zz_bond_delete_live_preflight.json').read_text(encoding='utf-8'))
assert preflight['bondsPanelBaselineMatched'] and preflight['backendBaselineMatched']
assert not preflight['manualDispatch'] and not preflight['workflowModified'] and not preflight['scheduleModified']

cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
s = requests.Session()
s.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                  'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-bond-delete-push'})


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
assert all(x['sha256'] == regression['productionFundDataSha256'][p] for p, x in before_local.items())
head = req('GET', '/repos/%s/git/ref/heads/main' % REPO)['object']['sha']
head_commit = req('GET', f'/repos/{REPO}/git/commits/{head}')
if head != preflight['head'] or head_commit['tree']['sha'] != preflight['headTree']:
    raise RuntimeError(f'实时main已从预检基线变化：{head}；停止发布并重新审计')
if content('src/sections/BondsPanel.tsx', head) != (ROOT / 'zz_bond_delete_BondsPanel_baseline.tsx').read_bytes():
    raise RuntimeError('实时main BondsPanel不再逐字节等于预检基线，停止发布')
if content('scripts/update_data.py', head) != (ROOT / 'zz_bond_delete_update_data_baseline.py').read_bytes():
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
    'message': '债券栏目删除市场要闻与中美国债对比',
    'tree': tree['sha'], 'parents': [head]})
updated = req('PATCH', f'/repos/{REPO}/git/refs/heads/main', json={'sha': commit['sha'], 'force': False})
print('PUSHED', commit['sha'], flush=True)
after_remote = remote_data(commit['sha'])
after_local = local_data()
assert before_local == after_local and before_remote == after_remote
for name in FILES:
    assert content(name, commit['sha']) == (ROOT / name).read_bytes(), name
comparison = req('GET', f'/repos/{REPO}/compare/{head}...{commit["sha"]}')
changed = {x['filename'] for x in comparison.get('files') or []}
assert changed <= set(FILES) and not changed & set(DATA)
assert not any(x.startswith('.github/') or x.startswith('dist/') or x.endswith('.png') for x in changed)
assert req('GET', '/repos/%s/git/ref/heads/main' % REPO)['object']['sha'] == commit['sha']
result = {
    'task': 'bond-delete', 'realHead': head, 'realHeadMessage': head_commit['message'],
    'realHeadTree': head_commit['tree']['sha'], 'commit': commit['sha'], 'tree': tree['sha'],
    'ref': updated['object']['sha'], 'parent': head, 'files': FILES, 'changedFiles': sorted(changed),
    'force': False, 'manualDispatch': False, 'nightlyExecuted': False,
    'workflowModified': False, 'scheduleModified': False,
    'localFundDataBefore': before_local, 'localFundDataAfter': after_local,
    'remoteFundDataBefore': before_remote, 'remoteFundDataAfter': after_remote,
    'remoteFilesContentVerified': True, 'fundDataUnchanged': True,
    'productionDataRegenerated': False, 'screenshotsIncluded': False,
}
(ROOT / 'zz_push_bond_delete.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('VERIFIED', commit['sha'], flush=True)
