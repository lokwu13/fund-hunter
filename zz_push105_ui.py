# -*- coding: utf-8 -*-
"""任务103前端证据补充：实时父提交保护，force=false，不dispatch，不改fund_data。"""
import base64
import hashlib
import json
import subprocess
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
REPO = 'lokwu13/fund-hunter'
EXPECTED_PARENT = json.loads((ROOT / 'zz_push105.json').read_text(encoding='utf-8'))['commit']
FILES = ['src/hooks/useFundData.ts', 'src/sections/ECIPanel.tsx',
         '任务103-VCP规则优化对照.md', 'zz_push105_ui.py']
DATA_FILES = ['public/fund_data.json', 'src/data/fund_data.json']
assert not set(FILES) & set(DATA_FILES)

cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
s = requests.Session()
s.headers.update({'Authorization': f"Bearer {fields['password']}",
                  'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
                  'User-Agent': 'fund-hunter-task103-ui-push'})


def req(method, path, **kwargs):
    response = s.request(method, f'https://api.github.com{path}', timeout=60, **kwargs)
    if not response.ok:
        raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:500]}')
    return response.json()


def remote_content(path, ref):
    item = req('GET', f'/repos/{REPO}/contents/{path}?ref={ref}')
    if item.get('content'):
        return base64.b64decode(item['content'])
    blob = req('GET', f"/repos/{REPO}/git/blobs/{item['sha']}")
    return base64.b64decode(blob['content'])


def local_data_hashes():
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in DATA_FILES}


before_local = local_data_hashes()
head = req('GET', f'/repos/{REPO}/git/ref/heads/main')['object']['sha']
if head != EXPECTED_PARENT:
    raise RuntimeError(f'实时main偏离任务103规则提交，停止前端补充：{head}')
head_commit = req('GET', f'/repos/{REPO}/git/commits/{head}')
remote_before = {path: req('GET', f'/repos/{REPO}/contents/{path}?ref={head}')['sha']
                 for path in DATA_FILES}
tree_items = []
for name in FILES:
    blob = req('POST', f'/repos/{REPO}/git/blobs', json={
        'content': base64.b64encode((ROOT / name).read_bytes()).decode('ascii'),
        'encoding': 'base64'})
    tree_items.append({'path': name, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
tree = req('POST', f'/repos/{REPO}/git/trees', json={
    'base_tree': head_commit['tree']['sha'], 'tree': tree_items})
commit = req('POST', f'/repos/{REPO}/git/commits', json={
    'message': '任务103：补充固定区间VCP前端证据',
    'tree': tree['sha'], 'parents': [head]})
updated = req('PATCH', f'/repos/{REPO}/git/refs/heads/main', json={
    'sha': commit['sha'], 'force': False})
remote_after = {path: req('GET', f'/repos/{REPO}/contents/{path}?ref={commit["sha"]}')['sha']
                for path in DATA_FILES}
after_local = local_data_hashes()
assert before_local == after_local
assert remote_before == remote_after
for name in FILES:
    assert remote_content(name, commit['sha']) == (ROOT / name).read_bytes(), name
result = {'task': 103, 'parent': head, 'commit': commit['sha'], 'tree': tree['sha'],
          'ref': updated['object']['sha'], 'files': FILES, 'force': False,
          'manualDispatch': False, 'workflowModified': False,
          'localFundDataSha256Before': before_local, 'localFundDataSha256After': after_local,
          'remoteFundDataBlobBefore': remote_before, 'remoteFundDataBlobAfter': remote_after,
          'remoteFilesContentVerified': True}
(ROOT / 'zz_push105_ui.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('PUSHED', commit['sha'], flush=True)
