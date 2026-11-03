# -*- coding: utf-8 -*-
"""任务111只读线上核验；不dispatch，不写生产数据。"""
import base64
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
REPO = 'lokwu13/fund-hunter'
BASE = 'https://lokwu13.github.io/fund-hunter/'
push = json.loads((ROOT / 'zz_push111.json').read_text(encoding='utf-8'))
COMMIT = push['commit']
cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
api = requests.Session()
api.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-task111-readonly'})
web = requests.Session()

def req(path):
    response = api.get('https://api.github.com' + path, timeout=60)
    if not response.ok:
        raise RuntimeError(f'{response.status_code} {path}: {response.text[:400]}')
    return response.json()

def content(path, ref):
    obj = req(f'/repos/{REPO}/contents/{path}?ref={ref}')
    if obj.get('content'):
        return base64.b64decode(obj['content'])
    return base64.b64decode(req(f'/repos/{REPO}/git/blobs/{obj["sha"]}')['content'])

run = None
deadline = time.time() + 240
while time.time() < deadline:
    runs = req(f'/repos/{REPO}/actions/runs?event=push&per_page=100').get('workflow_runs') or []
    candidates = [x for x in runs if x.get('head_sha') == COMMIT]
    if candidates:
        run = candidates[0]
        if run.get('status') == 'completed':
            break
    time.sleep(10)
assert run and run.get('status') == 'completed' and run.get('conclusion') == 'success', run
main = req(f'/repos/{REPO}/git/ref/heads/main')['object']['sha']
commit = req(f'/repos/{REPO}/git/commits/{COMMIT}')
assert commit['parents'][0]['sha'] == push['parent']

page = js_name = css_name = None
js_raw = css_raw = None
page_deadline = time.time() + 120
markers = ('底部价格结构观察', 'bottomShapeWatch', 'qualificationLabel', 'formalAdmission')
while time.time() < page_deadline:
    buster = f'{run["id"]}-{time.time_ns()}'
    response = web.get(BASE, params={'v': buster}, timeout=60)
    response.raise_for_status()
    page = response.text
    jm = re.search(r'src="(/fund-hunter/assets/index-[^"]+\.js)"', page)
    cm = re.search(r'href="(/fund-hunter/assets/index-[^"]+\.css)"', page)
    if jm and cm:
        js_name, css_name = jm.group(1), cm.group(1)
        js_raw = web.get('https://lokwu13.github.io' + js_name, params={'v': buster}, timeout=90).content
        css_raw = web.get('https://lokwu13.github.io' + css_name, params={'v': buster}, timeout=90).content
        text = js_raw.decode('utf-8')
        if all(x in text for x in markers):
            break
    time.sleep(10)
assert page and js_raw and css_raw
js_text = js_raw.decode('utf-8')
online_data = {}
for path in ('public/fund_data.json', 'src/data/fund_data.json'):
    remote_raw = content(path, COMMIT)
    online_raw = web.get(BASE + 'fund_data.json', params={'v': time.time_ns()}, timeout=90).content
    online_data[path] = {
        'remoteCommitBytes': len(remote_raw), 'remoteCommitSha256': hashlib.sha256(remote_raw).hexdigest(),
        'onlineBytes': len(online_raw), 'onlineSha256': hashlib.sha256(online_raw).hexdigest(),
        'onlineEqualsRemoteCommit': online_raw == remote_raw,
        'remoteBeforeAfterUnchanged': push['remoteFundDataBefore'][path] == push['remoteFundDataAfter'][path],
        'localUnchanged': push['localFundDataBefore'][path] == push['localFundDataAfter'][path],
    }
production = content('scripts/update_data.py', COMMIT).decode('utf-8')
checks = {
    'automaticPushRunSuccess': run.get('event') == 'push' and run.get('head_sha') == COMMIT and run.get('conclusion') == 'success',
    'realParentAndNonForce': commit['parents'][0]['sha'] == push['parent'] and push['force'] is False,
    'layeredObservationPublished': all(x in js_text for x in markers),
    'qualificationReasonsPublished': '不等于正式底部入选' in js_text and '底部形态观察·资格排除' in production,
    'layeredGateInTargetCommit': all(x in production for x in (
        "'bottomShapeWatch': bottom_shape_watch[:100]", "'bottomShapeWatchCount': len(bottom_shape_watch)",
        "'formalAdmission': eligible", "'qualificationStatus': status")),
    'remoteAndLocalFundDataUnchanged': all(x['remoteBeforeAfterUnchanged'] and x['localUnchanged'] for x in online_data.values()),
    'onlineFundDataByteEqualsRemoteCommit': all(x['onlineEqualsRemoteCommit'] for x in online_data.values()),
}
local_js = ROOT / 'dist/assets/index-DfCZCAaT-v25.js'
result = {
    'task': 111, 'commit': COMMIT, 'parent': push['parent'], 'mainAtVerification': main,
    'run': {'id': run['id'], 'event': run['event'], 'status': run['status'], 'conclusion': run['conclusion'],
            'headSha': run['head_sha'], 'url': run.get('html_url'), 'createdAt': run.get('created_at'), 'updatedAt': run.get('updated_at')},
    'pages': {'url': BASE,
              'js': {'path': js_name, 'bytes': len(js_raw), 'sha256': hashlib.sha256(js_raw).hexdigest()},
              'css': {'path': css_name, 'bytes': len(css_raw), 'sha256': hashlib.sha256(css_raw).hexdigest()}},
    'localWindowsJs': {'path': 'dist/assets/index-DfCZCAaT-v25.js', 'bytes': local_js.stat().st_size,
                       'sha256': hashlib.sha256(local_js.read_bytes()).hexdigest()},
    'crossPlatformJsHashNote': 'code-path包含平台路径分隔符，Windows与Linux CI的JS哈希可能不同；以目标commit成功run及线上功能标记核验。',
    'fundData': online_data, 'manualDispatch': False, 'workflowModified': False,
    'productionDataRegeneratedByThisRelease': False,
    'productionListRefreshVerified': False,
    'productionListRefreshNote': '本次不重算生产数据；既有线上名单需等待nightly按新门刷新。',
    'checks': checks, 'allPassed': all(checks.values()),
}
(ROOT / 'zz_task111_online_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['allPassed'] else 1)
