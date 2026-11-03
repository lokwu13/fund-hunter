# -*- coding: utf-8 -*-
"""任务111 Git Data API发布；实时main基树/父提交，force=False，不触生产数据/workflow。"""
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
    'scripts/update_data.py', 'scripts/cache/vcp_cache.json',
    'src/hooks/useFundData.ts', 'src/sections/patternEvidence.ts',
    'src/sections/WeeklySummary.tsx', 'src/sections/ECIPanel.tsx',
    'zz_regress111.py', 'zz_regress111_summary.json', 'zz_joint_regress111.json',
    'zz_regress101.py', 'zz_regress102.py', 'zz_regress104.py', 'zz_regress106.py',
    'zz_task111_report.md', 'zz_task111_machine_verification.json',
    'zz_push111.py', 'zz_verify111_online.py',
]
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
EXPECTED_LOCAL_DATA_SHA = '3e6be924bdc847d48bbffc8276776ab90ee319a0cb2863ab432531ff800637a1'
assert len(FILES) == len(set(FILES)) and not set(FILES) & set(DATA)
assert not any(name.startswith('.github/') for name in FILES)
r111 = json.loads((ROOT / 'zz_regress111_summary.json').read_text(encoding='utf-8'))
assert r111['allPassed'] and r111['releaseEligible'] and not r111['failed'] and not r111['fatalErrors']
assert r111['checksPassed'] == r111['checksTotal'] == 59
assert r111['corePositivePassed'] == r111['corePositiveTotal'] == 4
assert r111['coreEligiblePassed'] == 0 and r111['coreEligibleTotal'] == 4
joint = json.loads((ROOT / 'zz_joint_regress111.json').read_text(encoding='utf-8'))
assert joint['allPassed'] and joint['passed'] == joint['total'] == 13
machine = json.loads((ROOT / 'zz_task111_machine_verification.json').read_text(encoding='utf-8'))
assert machine['allPassed'] and machine['build']['success']

cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
s = requests.Session()
s.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                  'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-task111-push'})

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
assert all(x['sha256'] == EXPECTED_LOCAL_DATA_SHA for x in before_local.values()), before_local
head = req('GET', '/repos/%s/git/ref/heads/main' % REPO)['object']['sha']
head_commit = req('GET', f'/repos/{REPO}/git/commits/{head}')
before_remote = remote_data(head)
print('REAL_HEAD', head, flush=True)
print('DATA_BEFORE', json.dumps({'local': before_local, 'remote': before_remote}, ensure_ascii=False), flush=True)
if "'bottomShapeWatch': bottom_shape_watch[:100]" in content('scripts/update_data.py', head).decode('utf-8'):
    raise RuntimeError(f'实时main {head} 已含任务111分层修复，停止重复发布')

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
    'message': '任务111：底部价格结构观察与正式入选资格分层',
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
result = {
    'task': 111, 'realHead': head, 'commit': commit['sha'], 'tree': tree['sha'],
    'ref': updated['object']['sha'], 'parent': head, 'files': FILES, 'changedFiles': sorted(changed),
    'force': False, 'manualDispatch': False, 'workflowModified': False,
    'localFundDataBefore': before_local, 'localFundDataAfter': after_local,
    'remoteFundDataBefore': before_remote, 'remoteFundDataAfter': after_remote,
    'remoteFilesContentVerified': True, 'fundDataUnchanged': True,
}
(ROOT / 'zz_push111.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('VERIFIED', commit['sha'], flush=True)
