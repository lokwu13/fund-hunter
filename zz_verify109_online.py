# -*- coding: utf-8 -*-
"""任务109只读线上核验；不dispatch，不写生产数据。"""
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
push = json.loads((ROOT / 'zz_push109.json').read_text(encoding='utf-8'))
COMMIT = push['commit']
cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
api = requests.Session()
api.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-task109-readonly'})
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
deadline = time.time() + 180
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
        if 'prefers-reduced-motion: reduce' in text and 'getClientRects' in text:
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
checks = {
    'automaticPushRunSuccess': run.get('event') == 'push' and run.get('head_sha') == COMMIT and run.get('conclusion') == 'success',
    'realParentAndNonForce': commit['parents'][0]['sha'] == push['parent'] and push['force'] is False,
    'renderedAnchorWaitPublished': 'getClientRects' in js_text and 'requestAnimationFrame' in js_text,
    'reducedMotionPublished': 'prefers-reduced-motion: reduce' in js_text,
    'bothStableTargetsPublished': all(x in js_text for x in ('oversold-value-directions', 'rsi6-dividend-top20')),
    'buttonLabelsPublished': all(x in js_text for x in ('查看行业/大概念自身历史估值、双龙头与数据限制', '查看全A股息率TTM Top20完整原榜')),
    'keyboardAriaControlsPublished': 'aria-controls' in js_text,
    'remoteAndLocalFundDataUnchanged': all(x['remoteBeforeAfterUnchanged'] and x['localUnchanged'] for x in online_data.values()),
    'onlineFundDataByteEqualsRemoteCommit': all(x['onlineEqualsRemoteCommit'] for x in online_data.values()),
}
local_js = next((ROOT / 'dist/assets').glob('index-CjcnNGdo-v25.js'))
result = {
    'task': 109, 'commit': COMMIT, 'parent': push['parent'], 'mainAtVerification': main,
    'run': {'id': run['id'], 'event': run['event'], 'status': run['status'], 'conclusion': run['conclusion'],
            'headSha': run['head_sha'], 'url': run.get('html_url'), 'createdAt': run.get('created_at'), 'updatedAt': run.get('updated_at')},
    'pages': {'url': BASE,
              'js': {'path': js_name, 'bytes': len(js_raw), 'sha256': hashlib.sha256(js_raw).hexdigest()},
              'css': {'path': css_name, 'bytes': len(css_raw), 'sha256': hashlib.sha256(css_raw).hexdigest()}},
    'localWindowsJs': {'path': 'dist/assets/index-CjcnNGdo-v25.js', 'bytes': local_js.stat().st_size,
                       'sha256': hashlib.sha256(local_js.read_bytes()).hexdigest()},
    'crossPlatformJsHashNote': 'code-path包含平台路径分隔符，Windows与Linux CI的JS哈希不同；以目标commit成功run及线上功能标记核验。',
    'fundData': online_data, 'manualDispatch': False, 'workflowModified': False,
    'productionDataRegeneratedByThisRelease': False,
    'checks': checks, 'allPassed': all(checks.values()),
}
(ROOT / 'zz_task109_online_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['allPassed'] else 1)
