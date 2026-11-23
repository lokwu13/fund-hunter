# -*- coding: utf-8 -*-
"""任务1141：实时 main 基树/父提交 Git Data API 白名单发布，force=False。"""
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
WORKFLOW = '.github/workflows/daily-update.yml'
CACHE = 'scripts/cache/ccass_history.json'
FILES = [
    PANEL, BACKEND,
    'zz_daily_tables_1141_ForeignCapitalPanel_baseline.tsx',
    'zz_daily_tables_1141_update_data_baseline.py',
    'zz_daily_tables_1141_daily_update_baseline.yml',
    'zz_daily_tables_1141_live_preflight.py', 'zz_daily_tables_1141_live_preflight.json',
    'zz_daily_tables_1141_backend_tests.py', 'zz_daily_tables_1141_backend_tests.json',
    'zz_daily_tables_1141_real_source_verify.py', 'zz_daily_tables_1141_real_source_verify.json',
    'zz_daily_tables_1141_regress.py', 'zz_daily_tables_1141_regress.json', 'zz_daily_tables_1141_regress_summary.json',
    'zz_daily_tables_1141_build.py', 'zz_daily_tables_1141_build.json', 'zz_daily_tables_1141_build.log',
    'zz_daily_tables_1141_edge_verify.py', 'zz_daily_tables_1141_edge_verification.json',
    'zz_daily_tables_1141_machine_verification.py', 'zz_daily_tables_1141_machine_verification.json',
    'zz_daily_tables_1141_push.py', 'zz_daily_tables_1141_verify_online.py',
]
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
assert len(FILES) == len(set(FILES)) and not set(FILES) & set(DATA)
assert WORKFLOW not in FILES and CACHE not in FILES
assert not any(name.startswith(('.github/', 'dist/')) or '__pycache__' in name
               or 'cache/' in name or name.endswith('.png') for name in FILES)
assert all((ROOT / name).is_file() for name in FILES)
regression = json.loads((ROOT / 'zz_daily_tables_1141_regress_summary.json').read_text(encoding='utf-8'))
assert regression['allPassed'] and regression['checksPassed'] == regression['checksTotal'] == 44
assert not regression['failed'] and not regression['productionDataRegenerated']
backend_tests = json.loads((ROOT / 'zz_daily_tables_1141_backend_tests.json').read_text(encoding='utf-8'))
assert backend_tests['allPassed'] and backend_tests['checksPassed'] == backend_tests['checksTotal'] == 35
real = json.loads((ROOT / 'zz_daily_tables_1141_real_source_verify.json').read_text(encoding='utf-8'))
assert real['allPassed'] and real['productionDataUnchanged'] and not real['fullNightlyDispatched']
build = json.loads((ROOT / 'zz_daily_tables_1141_build.json').read_text(encoding='utf-8'))
assert build['success'] and build['returncode'] == 0 and build['matchesRegressionDataSha']
assert build['fundDataUnchanged'] and not build['developmentServerStarted']
assert all(build['retainedBundleMarkers'].values()) and not any(build['removedBundleMarkersPresent'].values())
edge = json.loads((ROOT / 'zz_daily_tables_1141_edge_verification.json').read_text(encoding='utf-8'))
assert edge['allPassed'] and edge['temporaryStaticServerStopped'] and edge['edgeProcessStopped']
machine = json.loads((ROOT / 'zz_daily_tables_1141_machine_verification.json').read_text(encoding='utf-8'))
assert machine['allPassed'] and machine['releaseReady']
assert all(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha
           for path, sha in machine['sourceSha256'].items())
preflight = json.loads((ROOT / 'zz_daily_tables_1141_live_preflight.json').read_text(encoding='utf-8'))
assert preflight['onlineEqualsRemoteMain'] and not preflight['manualDispatch']
assert not preflight['workflowModified'] and not preflight['scheduleModified']
assert (ROOT / WORKFLOW).read_bytes() == (ROOT / 'zz_daily_tables_1141_daily_update_baseline.yml').read_bytes()

cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
api = requests.Session()
api.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-daily-tables-1141-push'})


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
for path, state in preflight['protectedFiles'].items():
    if hashlib.sha256(content(path, head)).hexdigest() != state['remoteSha256']:
        raise RuntimeError(f'实时 main 受保护文件已变化：{path}；停止发布')
before_remote = remote_data(head)
assert all(before_remote[path]['sha256'] == preflight['fundData'][path]['remoteSha256'] for path in DATA)
cache_before = hashlib.sha256(content(CACHE, head)).hexdigest()
assert cache_before == preflight['ccassCache']['remoteSha256']
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
    'message': '两榜接入交易日nightly并展示真实数据日期', 'tree': tree['sha'], 'parents': [head]})
updated = req('PATCH', f'/repos/{REPO}/git/refs/heads/main', json={'sha': commit['sha'], 'force': False})
print('PUSHED', commit['sha'], flush=True)
after_remote = remote_data(commit['sha'])
after_local = local_data()
assert before_local == after_local and before_remote == after_remote
assert hashlib.sha256(content(CACHE, commit['sha'])).hexdigest() == cache_before
for name in FILES:
    assert content(name, commit['sha']) == (ROOT / name).read_bytes(), name
comparison = req('GET', f'/repos/{REPO}/compare/{head}...{commit["sha"]}')
changed = {entry['filename'] for entry in comparison.get('files') or []}
assert changed == set(FILES) and not changed & set(DATA) and WORKFLOW not in changed and CACHE not in changed
assert not any(name.startswith(('.github/', 'dist/')) or 'cache/' in name or name.endswith('.png') for name in changed)
assert req('GET', f'/repos/{REPO}/git/ref/heads/main')['object']['sha'] == commit['sha']
result = {
    'task': 'daily-tables-1141', 'realHead': head, 'realHeadMessage': head_commit['message'],
    'realHeadTree': head_commit['tree']['sha'], 'commit': commit['sha'], 'tree': tree['sha'],
    'ref': updated['object']['sha'], 'parent': head, 'files': FILES, 'changedFiles': sorted(changed),
    'force': False, 'manualDispatch': False, 'nightlyExecuted': False,
    'workflowModified': False, 'scheduleModified': False,
    'localFundDataBefore': before_local, 'localFundDataAfter': after_local,
    'remoteFundDataBefore': before_remote, 'remoteFundDataAfter': after_remote,
    'ccassCacheSha256BeforeAfter': cache_before,
    'remoteFilesContentVerified': True, 'fundDataUnchanged': True, 'ccassCacheUnchanged': True,
    'productionDataRegenerated': False, 'productionDataIncluded': False, 'screenshotsIncluded': False,
}
(ROOT / 'zz_daily_tables_1141_push.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('VERIFIED', commit['sha'], flush=True)
