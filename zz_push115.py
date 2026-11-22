# -*- coding: utf-8 -*-
"""任务115 Git Data API发布：实时main基树/父提交，force=False，不触生产数据/workflow。"""
import base64
import concurrent.futures
import hashlib
import json
import subprocess
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
REPO = 'lokwu13/fund-hunter'
JOINT_TASKS = [95, 96, 98, 99, 101, 102, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115]
FILES = [
    'scripts/update_data.py', 'scripts/pattern_history.py',
    'src/sections/patternEvidence.ts', 'src/sections/PatternHistoryLabel.tsx',
    'src/hooks/useFundData.ts', 'src/sections/WeeklySummary.tsx', 'src/sections/ECIPanel.tsx',
    'zz_scan101.py', 'zz_update_data_task115_baseline.py',
    'zz_regress115.py', 'zz_regress115_summary.json', 'zz_regress115_report.json',
    'zz_regress113_summary.json', 'zz_regress114_summary.json',
    'zz_run_joint115.py', 'zz_joint_regress115.json',
    'zz_build115.py', 'zz_build115.json', 'zz_build115.log',
    'zz_task115_report.md', 'zz_task115_machine_verification.py', 'zz_task115_machine_verification.json',
    'zz_task115_live_preflight.py', 'zz_task115_live_preflight.json',
    'zz_push115.py', 'zz_verify115_online.py',
] + [f'zz_regress{task}_task115.log' for task in JOINT_TASKS]
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
assert len(FILES) == len(set(FILES)) and not set(FILES) & set(DATA)
assert not any(name.startswith('.github/') or name.startswith('dist/') for name in FILES)
assert not any('__pycache__' in name or 'cache/' in name for name in FILES)
assert all((ROOT / name).is_file() for name in FILES)

r113 = json.loads((ROOT / 'zz_regress113_summary.json').read_text(encoding='utf-8'))
r114 = json.loads((ROOT / 'zz_regress114_summary.json').read_text(encoding='utf-8'))
r115 = json.loads((ROOT / 'zz_regress115_summary.json').read_text(encoding='utf-8'))
assert r113['allPassed'] and not r113['failed'] and r113['checksPassed'] == r113['checksTotal'] == 309
assert r114['allPassed'] and not r114['failed'] and r114['checksPassed'] == r114['checksTotal'] == 34
assert r115['allPassed'] and not r115['failed'] and r115['checksPassed'] == r115['checksTotal'] == 23
assert r115['entryId'] == 'low_vol_tight' and not r115['oldFunctionsChanged']
assert r113['productionFundDataSha256'] == r114['productionFundDataSha256'] == r115['productionFundDataSha256']
assert r114['pitOnly'] and r115['pitOnly']
assert not r114['productionDataRegenerated'] and not r115['productionDataRegenerated']
joint = json.loads((ROOT / 'zz_joint_regress115.json').read_text(encoding='utf-8'))
assert joint['complete'] and joint['allPassed'] and joint['passed'] == joint['total'] == 18
assert [x['task'] for x in joint['results']] == JOINT_TASKS
assert all(x['returncode'] == 0 and x['passed'] for x in joint['results'])
assert all((ROOT / x['log']).is_file() and (ROOT / x['log']).stat().st_size == x['logBytes']
           for x in joint['results'])
build = json.loads((ROOT / 'zz_build115.json').read_text(encoding='utf-8'))
assert build['success'] and build['returncode'] == 0 and build['matchesTask115RegressionDataSha']
assert build['fundDataUnchanged'] and not build['developmentServerStarted']
machine = json.loads((ROOT / 'zz_task115_machine_verification.json').read_text(encoding='utf-8'))
assert machine['allPassed'] and machine['releaseReady'] and machine['build']['success']
assert machine['jointRegression']['passed'] == machine['jointRegression']['total'] == 18
assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == sha
           for p, sha in machine['sourceSha256'].items())
preflight = json.loads((ROOT / 'zz_task115_live_preflight.json').read_text(encoding='utf-8'))
assert preflight['task114SourceBaselineMatched'] and not preflight['manualDispatch']
assert not preflight['workflowModified'] and not preflight['scheduleModified']

cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
s = requests.Session()
s.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                  'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-task115-push'})


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
assert all(x['sha256'] == r115['productionFundDataSha256'][p] for p, x in before_local.items()), before_local
head = req('GET', '/repos/%s/git/ref/heads/main' % REPO)['object']['sha']
head_commit = req('GET', f'/repos/{REPO}/git/commits/{head}')
remote_source = content('scripts/update_data.py', head).decode('utf-8')
if head_commit['message'].startswith('任务115') or 'VCP_LOW_VOL_TIGHT_ENTRY_ID' in remote_source:
    raise RuntimeError(f'实时main {head} 已含任务115，停止重复发布')
if head != preflight['head'] or head_commit['tree']['sha'] != preflight['headTree']:
    raise RuntimeError(f'实时main已从预检基线变化：{head}；请重新预检和审计')
if remote_source.encode('utf-8') != (ROOT / 'zz_update_data_task115_baseline.py').read_bytes():
    raise RuntimeError('实时main后端源码不再逐字节等于任务114基线，停止发布')
before_remote = remote_data(head)
assert all(before_remote[p]['sha256'] == preflight['fundData'][p]['remoteSha256'] for p in DATA)
print('REAL_HEAD', head, flush=True)
print('REAL_HEAD_MESSAGE', head_commit['message'], flush=True)
print('DATA_BEFORE', json.dumps({'local': before_local, 'remote': before_remote}, ensure_ascii=False), flush=True)


def upload(name):
    raw = (ROOT / name).read_bytes()
    blob = req('POST', f'/repos/{REPO}/git/blobs', json={
        'content': base64.b64encode(raw).decode('ascii'), 'encoding': 'base64'})
    return {'path': name, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']}


with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    tree_items = list(pool.map(upload, FILES))
print('BLOBS_READY', len(tree_items), flush=True)
tree = req('POST', f'/repos/{REPO}/git/trees', json={'base_tree': head_commit['tree']['sha'], 'tree': tree_items})
commit = req('POST', f'/repos/{REPO}/git/commits', json={
    'message': '任务115：低量窄幅独立VCP入口',
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
assert not any(x.startswith('.github/') or x.startswith('dist/') for x in changed)
live_main = req('GET', '/repos/%s/git/ref/heads/main' % REPO)['object']['sha']
assert live_main == commit['sha']
result = {
    'task': 115, 'realHead': head, 'realHeadMessage': head_commit['message'],
    'realHeadTree': head_commit['tree']['sha'], 'commit': commit['sha'], 'tree': tree['sha'],
    'ref': updated['object']['sha'], 'parent': head, 'files': FILES, 'changedFiles': sorted(changed),
    'force': False, 'manualDispatch': False, 'nightlyExecuted': False,
    'workflowModified': False, 'scheduleModified': False,
    'localFundDataBefore': before_local, 'localFundDataAfter': after_local,
    'remoteFundDataBefore': before_remote, 'remoteFundDataAfter': after_remote,
    'remoteFilesContentVerified': True, 'fundDataUnchanged': True,
    'productionDataRegenerated': False, 'productionListRefreshed': False,
}
(ROOT / 'zz_push115.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('VERIFIED', commit['sha'], flush=True)
