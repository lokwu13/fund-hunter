# -*- coding: utf-8 -*-
"""任务107排雷顺延增量：Git Data API非强制发布，实时main基树/父提交，不改生产数据。"""
import base64
import hashlib
import json
import subprocess
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
REPO = 'lokwu13/fund-hunter'
FILES = [
    'scripts/update_data.py',
    'src/hooks/useFundData.ts',
    'src/sections/funnelConclusions.ts',
    'src/sections/SectorHeatmap.tsx',
    'zz_regress107.py',
    'TASK107_MINEFILTER_INCREMENT_REPORT.md',
    'zz_task107_minefilter_verification.json',
    'zz_push107_minefilter.py',
]
DATA_FILES = ['public/fund_data.json', 'src/data/fund_data.json']
assert not set(FILES) & set(DATA_FILES)
assert not any(name.startswith('.github/workflows/') for name in FILES)
for name in ('zz_regress107_summary.json',):
    result = json.loads((ROOT / name).read_text(encoding='utf-8'))
    assert result['checksPassed'] == result['checksTotal'] == 29 and not result['failed'], result

cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
s = requests.Session()
s.headers.update({'Authorization': f"Bearer {fields['password']}",
                  'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
                  'User-Agent': 'fund-hunter-task107-minefilter-push'})


def req(method, path, **kwargs):
    response = s.request(method, f'https://api.github.com{path}', timeout=60, **kwargs)
    if not response.ok:
        raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:500]}')
    return response.json()


def remote_item(path, ref):
    return req('GET', f'/repos/{REPO}/contents/{path}?ref={ref}')


def remote_content(path, ref):
    item = remote_item(path, ref)
    if item.get('content'):
        return base64.b64decode(item['content'])
    blob = req('GET', f"/repos/{REPO}/git/blobs/{item['sha']}")
    return base64.b64decode(blob['content'])


def local_data():
    result = {}
    for path in DATA_FILES:
        raw = (ROOT / path).read_bytes()
        result[path] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    return result


def remote_data(ref):
    result = {}
    for path in DATA_FILES:
        item = remote_item(path, ref)
        raw = remote_content(path, ref)
        result[path] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                        'blobSha': item['sha']}
    return result


before_local = local_data()
head = req('GET', f'/repos/{REPO}/git/ref/heads/main')['object']['sha']
head_commit = req('GET', f'/repos/{REPO}/git/commits/{head}')
before_remote = remote_data(head)
print('REAL_HEAD', head, flush=True)
print('DATA_BEFORE', json.dumps({'local': before_local, 'remote': before_remote}, ensure_ascii=False), flush=True)
# 若实时main已经包含同一增量，停止而不是重复发布。
remote_script = remote_content('scripts/update_data.py', head).decode('utf-8')
if 'remainingCandidateCount' in remote_script and '明确命中排雷剔除并顺延补足' in remote_script:
    raise RuntimeError(f'实时main {head} 已含任务107排雷顺延增量；停止重复发布，请先复核')

tree_items = []
for name in FILES:
    content = (ROOT / name).read_bytes()
    blob = req('POST', f'/repos/{REPO}/git/blobs', json={
        'content': base64.b64encode(content).decode('ascii'), 'encoding': 'base64'})
    tree_items.append({'path': name, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
tree = req('POST', f'/repos/{REPO}/git/trees', json={
    'base_tree': head_commit['tree']['sha'], 'tree': tree_items})
commit = req('POST', f'/repos/{REPO}/git/commits', json={
    'message': '任务107：明确排雷命中剔除并顺延补足Top20',
    'tree': tree['sha'], 'parents': [head]})
updated = req('PATCH', f'/repos/{REPO}/git/refs/heads/main', json={
    'sha': commit['sha'], 'force': False})

after_remote = remote_data(commit['sha'])
after_local = local_data()
assert before_local == after_local
assert before_remote == after_remote
for name in FILES:
    assert remote_content(name, commit['sha']) == (ROOT / name).read_bytes(), name
comparison = req('GET', f'/repos/{REPO}/compare/{head}...{commit["sha"]}')
changed = {item['filename'] for item in comparison.get('files') or []}
assert changed <= set(FILES), changed
assert not changed & set(DATA_FILES)

result = {
    'task': 107, 'increment': 'mine-exclusion-and-backfill', 'realHead': head,
    'commit': commit['sha'], 'tree': tree['sha'], 'ref': updated['object']['sha'],
    'files': FILES, 'changedFiles': sorted(changed), 'force': False,
    'manualDispatch': False, 'workflowModified': False,
    'localFundDataBefore': before_local, 'localFundDataAfter': after_local,
    'remoteFundDataBefore': before_remote, 'remoteFundDataAfter': after_remote,
    'remoteFilesContentVerified': True,
}
(ROOT / 'zz_push107_minefilter.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('PUSHED', commit['sha'], flush=True)
