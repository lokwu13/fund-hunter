# -*- coding: utf-8 -*-
"""任务1124：实时 main 基树/父提交 Git Data API 白名单发布，force=False。"""
import base64
import concurrent.futures
import hashlib
import json
import subprocess
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
REPO = 'lokwu13/fund-hunter'
PANEL = 'src/sections/ForeignCapitalPanel.tsx'
BACKEND = 'scripts/update_data.py'
FILES = [
    PANEL,
    'zz_delete_table_1124_ForeignCapitalPanel_baseline.tsx',
    'zz_delete_table_1124_update_data_baseline.py',
    'zz_delete_table_1124_live_preflight.py', 'zz_delete_table_1124_live_preflight.json',
    'zz_delete_table_1124_regress.py', 'zz_delete_table_1124_regress.json',
    'zz_delete_table_1124_regress_summary.json',
    'zz_delete_table_1124_build.py', 'zz_delete_table_1124_build.json', 'zz_delete_table_1124_build.log',
    'zz_delete_table_1124_edge_verify.py', 'zz_delete_table_1124_edge_verification.json',
    'zz_delete_table_1124_machine_verification.py', 'zz_delete_table_1124_machine_verification.json',
    'zz_delete_table_1124_push.py', 'zz_delete_table_1124_verify_online.py',
]
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
assert len(FILES) == len(set(FILES)) and not set(FILES) & set(DATA)
assert not any(name.startswith(('.github/', 'dist/')) or '__pycache__' in name
               or 'cache/' in name or name.endswith('.png') for name in FILES)
assert all((ROOT / name).is_file() for name in FILES)
regression = json.loads((ROOT / 'zz_delete_table_1124_regress_summary.json').read_text(encoding='utf-8'))
assert regression['allPassed'] and regression['checksPassed'] == regression['checksTotal'] == 30
assert not regression['failed'] and not regression['productionDataRegenerated']
build = json.loads((ROOT / 'zz_delete_table_1124_build.json').read_text(encoding='utf-8'))
assert build['success'] and build['returncode'] == 0 and build['matchesRegressionDataSha']
assert build['fundDataUnchanged'] and not build['developmentServerStarted']
assert all(build['retainedBundleMarkers'].values()) and not any(build['removedBundleMarkersPresent'].values())
edge = json.loads((ROOT / 'zz_delete_table_1124_edge_verification.json').read_text(encoding='utf-8'))
assert edge['allPassed'] and edge['temporaryStaticServerStopped'] and edge['edgeProcessStopped']
machine = json.loads((ROOT / 'zz_delete_table_1124_machine_verification.json').read_text(encoding='utf-8'))
assert machine['allPassed'] and machine['releaseReady']
assert all(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha
           for path, sha in machine['sourceSha256'].items())
preflight = json.loads((ROOT / 'zz_delete_table_1124_live_preflight.json').read_text(encoding='utf-8'))
assert preflight['panelBaselineMatched'] and preflight['backendBaselineMatched']
assert preflight['onlineEqualsRemoteMain'] and not preflight['manualDispatch']
assert not preflight['workflowModified'] and not preflight['scheduleModified']

cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
api = requests.Session()
api.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-delete-table-1124-push'})


def req(method, path, **kwargs):
    response = api.request(method, 'https://api.github.com' + path, timeout=60, **kwargs)
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
    return {path: {'bytes': (ROOT / path).stat().st_size,
                   'sha256': hashlib.sha256((ROOT / path).read_bytes()).hexdigest()} for path in DATA}


def remote_data(ref):
    result = {}
    for path in DATA:
        obj = item(path, ref)
        raw = content(path, ref)
        result[path] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'blobSha': obj['sha']}
    return result


before_local = local_data()
assert all(state['sha256'] == regression['productionFundDataSha256'][path]
           for path, state in before_local.items())
head = req('GET', f'/repos/{REPO}/git/ref/heads/main')['object']['sha']
head_commit = req('GET', f'/repos/{REPO}/git/commits/{head}')
if head != preflight['head'] or head_commit['tree']['sha'] != preflight['headTree']:
    raise RuntimeError(f'实时 main 已从预检基线变化：{head}；停止发布并重新审计')
if content(PANEL, head) != (ROOT / 'zz_delete_table_1124_ForeignCapitalPanel_baseline.tsx').read_bytes():
    raise RuntimeError('实时 main 外资面板不再逐字节等于预检基线，停止发布')
if content(BACKEND, head) != (ROOT / 'zz_delete_table_1124_update_data_baseline.py').read_bytes():
    raise RuntimeError('实时 main 后端不再逐字节等于预检基线，停止发布')
for path, state in preflight['protectedFrontend'].items():
    if hashlib.sha256(content(path, head)).hexdigest() != state['remoteSha256']:
        raise RuntimeError(f'实时 main 受保护前端文件已变化：{path}；停止发布')
before_remote = remote_data(head)
assert all(before_remote[path]['sha256'] == preflight['fundData'][path]['remoteSha256'] for path in DATA)
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
    'message': '删除外资栏内外资分歧十大标的表格', 'tree': tree['sha'], 'parents': [head]})
updated = req('PATCH', f'/repos/{REPO}/git/refs/heads/main', json={'sha': commit['sha'], 'force': False})
print('PUSHED', commit['sha'], flush=True)
after_remote = remote_data(commit['sha'])
after_local = local_data()
assert before_local == after_local and before_remote == after_remote
for name in FILES:
    assert content(name, commit['sha']) == (ROOT / name).read_bytes(), name
comparison = req('GET', f'/repos/{REPO}/compare/{head}...{commit["sha"]}')
changed = {entry['filename'] for entry in comparison.get('files') or []}
assert changed == set(FILES) and not changed & set(DATA)
assert not any(name.startswith(('.github/', 'dist/')) or 'cache/' in name or name.endswith('.png') for name in changed)
assert req('GET', f'/repos/{REPO}/git/ref/heads/main')['object']['sha'] == commit['sha']
result = {
    'task': 'delete-table-1124', 'realHead': head, 'realHeadMessage': head_commit['message'],
    'realHeadTree': head_commit['tree']['sha'], 'commit': commit['sha'], 'tree': tree['sha'],
    'ref': updated['object']['sha'], 'parent': head, 'files': FILES, 'changedFiles': sorted(changed),
    'force': False, 'manualDispatch': False, 'nightlyExecuted': False,
    'workflowModified': False, 'scheduleModified': False,
    'localFundDataBefore': before_local, 'localFundDataAfter': after_local,
    'remoteFundDataBefore': before_remote, 'remoteFundDataAfter': after_remote,
    'remoteFilesContentVerified': True, 'fundDataUnchanged': True,
    'productionDataRegenerated': False, 'screenshotsIncluded': False,
}
(ROOT / 'zz_delete_table_1124_push.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('VERIFIED', commit['sha'], flush=True)
