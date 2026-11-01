# -*- coding: utf-8 -*-
"""任务103：Git Data API发布；实时main基树/父提交，force=false，不dispatch，不改fund_data。"""
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
    'zz_scan101.py',
    'zz_regress98.py',
    'zz_regress101.py',
    'zz_regress102.py',
    'zz_regress104.py',
    'zz_regress105.py',
    'zz_audit105_samples.py',
    '任务103-VCP规则优化对照.md',
    '任务103-十案例回归报告.md',
    '任务103-十案例回归报告.json',
    'zz_regress105_summary.json',
    'zz_audit105_samples.json',
    'zz_push105.py',
]
DATA_FILES = ['public/fund_data.json', 'src/data/fund_data.json']
assert not set(FILES) & set(DATA_FILES)

cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
s = requests.Session()
s.headers.update({'Authorization': f"Bearer {fields['password']}",
                  'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
                  'User-Agent': 'fund-hunter-task103-push'})


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


before_local_data = local_data_hashes()
head = req('GET', f'/repos/{REPO}/git/ref/heads/main')['object']['sha']
head_commit = req('GET', f'/repos/{REPO}/git/commits/{head}')
# 任务104推送后的实时生产镜像；已人工核对本地差异仅含任务103规则。
if remote_content('scripts/update_data.py', head) != (ROOT / 'zz_update_data_task105_remote_precheck.py').read_bytes():
    raise RuntimeError('实时main的生产规则已偏离任务104发布后镜像，停止推送')
remote_data_before = {path: req('GET', f'/repos/{REPO}/contents/{path}?ref={head}')['sha']
                      for path in DATA_FILES}
print('REAL_HEAD', head, flush=True)

tree_items = []
for name in FILES:
    content = (ROOT / name).read_bytes()
    blob = req('POST', f'/repos/{REPO}/git/blobs', json={
        'content': base64.b64encode(content).decode('ascii'), 'encoding': 'base64'})
    tree_items.append({'path': name, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
tree = req('POST', f'/repos/{REPO}/git/trees', json={
    'base_tree': head_commit['tree']['sha'], 'tree': tree_items})
commit = req('POST', f'/repos/{REPO}/git/commits', json={
    'message': '任务103：按十案例校准VCP与底部平台规则',
    'tree': tree['sha'], 'parents': [head]})
updated = req('PATCH', f'/repos/{REPO}/git/refs/heads/main', json={
    'sha': commit['sha'], 'force': False})

remote_data_after = {path: req('GET', f'/repos/{REPO}/contents/{path}?ref={commit["sha"]}')['sha']
                     for path in DATA_FILES}
after_local_data = local_data_hashes()
assert before_local_data == after_local_data
assert remote_data_before == remote_data_after
for name in FILES:
    assert remote_content(name, commit['sha']) == (ROOT / name).read_bytes(), name

result = {
    'task': 103,
    'realHead': head,
    'remoteBaselineMatched': True,
    'commit': commit['sha'],
    'tree': tree['sha'],
    'ref': updated['object']['sha'],
    'files': FILES,
    'force': False,
    'manualDispatch': False,
    'workflowModified': False,
    'localFundDataSha256Before': before_local_data,
    'localFundDataSha256After': after_local_data,
    'remoteFundDataBlobBefore': remote_data_before,
    'remoteFundDataBlobAfter': remote_data_after,
    'remoteFilesContentVerified': True,
}
(ROOT / 'zz_push105.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('PUSHED', commit['sha'], flush=True)
