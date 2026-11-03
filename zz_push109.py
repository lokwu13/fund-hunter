# -*- coding: utf-8 -*-
"""任务109 Git Data API发布；实时main基树/父提交，force=False，不触生产数据/workflow。"""
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
    'src/App.tsx', 'src/navigation.ts', 'src/sections/WeeklySummary.tsx',
    'zz_navigation109.test.cjs', 'zz_regress109.py', 'zz_regress109_summary.json',
    'TASK109_OVERVIEW_NAVIGATION_FIX.md', 'zz_push109.py', 'zz_verify109_online.py',
]
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
assert not set(FILES) & set(DATA)
for number, total in [('109', 21), ('108', 40), ('107', 29), ('105', 40)]:
    result = json.loads((ROOT / f'zz_regress{number}_summary.json').read_text(encoding='utf-8'))
    assert result['checksPassed'] == result['checksTotal'] == total and not result['failed'], number
r105 = json.loads((ROOT / 'zz_regress105_summary.json').read_text(encoding='utf-8'))
assert r105['casePassed'] == r105['caseTotal'] == 10 and not r105['failedWindows']

cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
s = requests.Session()
s.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                  'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-task109-push'})

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
head = req('GET', f'/repos/{REPO}/git/ref/heads/main')['object']['sha']
head_commit = req('GET', f'/repos/{REPO}/git/commits/{head}')
before_remote = remote_data(head)
print('REAL_HEAD', head, flush=True)
print('DATA_BEFORE', json.dumps({'local': before_local, 'remote': before_remote}, ensure_ascii=False), flush=True)
if 'scrollToRenderedAnchor' in content('src/App.tsx', head).decode('utf-8'):
    raise RuntimeError(f'实时main {head} 已含任务109修复，停止重复发布')

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
    'message': '任务109：修复总览明细入口板块导航与渲染后定位',
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
    'task': 109, 'realHead': head, 'commit': commit['sha'], 'tree': tree['sha'],
    'ref': updated['object']['sha'], 'parent': head, 'files': FILES, 'changedFiles': sorted(changed),
    'force': False, 'manualDispatch': False, 'workflowModified': False,
    'localFundDataBefore': before_local, 'localFundDataAfter': after_local,
    'remoteFundDataBefore': before_remote, 'remoteFundDataAfter': after_remote,
    'remoteFilesContentVerified': True, 'fundDataUnchanged': True,
}
(ROOT / 'zz_push109.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('VERIFIED', commit['sha'], flush=True)
