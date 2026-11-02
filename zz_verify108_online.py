# -*- coding: utf-8 -*-
"""任务108发布后只读核验：自动push run、Pages实际bundle、远端/线上数据SHA；不dispatch。"""
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
push = json.loads((ROOT / 'zz_push108.json').read_text(encoding='utf-8'))
expected = json.loads((ROOT / 'zz_task108_verification.json').read_text(encoding='utf-8'))
COMMIT = push['commit']
cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
api = requests.Session()
api.headers.update({'Authorization': f"Bearer {fields['password']}",
                    'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
                    'User-Agent': 'fund-hunter-task108-readonly-verify'})
web = requests.Session()
web.headers['User-Agent'] = 'fund-hunter-task108-readonly-verify'


def req(path, **kwargs):
    response = api.get(f'https://api.github.com{path}', timeout=60, **kwargs)
    if not response.ok:
        raise RuntimeError(f'GET {path}: {response.status_code} {response.text[:500]}')
    return response.json()


def remote_content(path, ref):
    item = req(f'/repos/{REPO}/contents/{path}?ref={ref}')
    if item.get('content'):
        return base64.b64decode(item['content'])
    blob = req(f"/repos/{REPO}/git/blobs/{item['sha']}")
    return base64.b64decode(blob['content'])


# 只轮询push事件；绝不调用dispatch端点。
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
if not run:
    raise RuntimeError(f'未找到commit {COMMIT} 的自动push run')
if run.get('status') != 'completed' or run.get('conclusion') != 'success':
    raise RuntimeError(f'push run未成功: id={run.get("id")} status={run.get("status")} conclusion={run.get("conclusion")}')

# 读取实时main和目标commit，记录而不改写。
main = req(f'/repos/{REPO}/git/ref/heads/main')['object']['sha']
commit_obj = req(f'/repos/{REPO}/git/commits/{COMMIT}')
assert commit_obj['parents'][0]['sha'] == push['parent']

# Pages HTML必须重新读取，实际bundle名称不得沿用旧任务。
page = None
js_name = css_name = None
js_raw = css_raw = None
page_deadline = time.time() + 75
while time.time() < page_deadline:
    buster = f'{run["id"]}-{time.time_ns()}'
    response = web.get(BASE, params={'v': buster}, timeout=60)
    response.raise_for_status()
    page = response.text
    js_match = re.search(r'src="(/fund-hunter/assets/index-[^"]+\.js)"', page)
    css_match = re.search(r'href="(/fund-hunter/assets/index-[^"]+\.css)"', page)
    if js_match and css_match:
        js_name, css_name = js_match.group(1), css_match.group(1)
        js_raw = web.get('https://lokwu13.github.io' + js_name, params={'v': buster}, timeout=90).content
        css_raw = web.get('https://lokwu13.github.io' + css_name, params={'v': buster}, timeout=90).content
        if hashlib.sha256(js_raw).hexdigest() == expected['build']['js']['sha256']:
            break
    time.sleep(10)
assert page and js_name and css_name and js_raw and css_raw

online_data = {}
for path in ('public/fund_data.json', 'src/data/fund_data.json'):
    remote_raw = remote_content(path, COMMIT)
    online_url = BASE + 'fund_data.json'
    online_raw = web.get(online_url, params={'v': f'{run["id"]}-{time.time_ns()}'}, timeout=90).content
    online_data[path] = {
        'remoteCommitBytes': len(remote_raw), 'remoteCommitSha256': hashlib.sha256(remote_raw).hexdigest(),
        'onlineBytes': len(online_raw), 'onlineSha256': hashlib.sha256(online_raw).hexdigest(),
        'onlineEqualsRemoteCommit': online_raw == remote_raw,
        'remoteBeforeAfterUnchanged': push['remoteFundDataBefore'][path] == push['remoteFundDataAfter'][path],
        'localUnchanged': push['localFundDataBefore'][path] == push['localFundDataAfter'][path],
    }

js_text = js_raw.decode('utf-8')
checks = {
    'automaticPushRunSuccess': run.get('event') == 'push' and run.get('head_sha') == COMMIT
                              and run.get('conclusion') == 'success',
    'realParentAndNonForce': commit_obj['parents'][0]['sha'] == push['parent'] and push['force'] is False,
    'actualJsMatchesLocalBuild': hashlib.sha256(js_raw).hexdigest() == expected['build']['js']['sha256'],
    'actualCssMatchesLocalBuild': hashlib.sha256(css_raw).hexdigest() == expected['build']['css']['sha256'],
    'dynamicRsi6BundlePublished': all(x in js_text for x in ('当周动态RSI6进入20以下区域',
                                      'dynamicWeeklyRsiDate', '周内会变化')),
    'historicalValuationBundlePublished': all(x in js_text for x in ('peHistoryPct', 'pbHistoryPct',
                                      'compositeHistoryPct', '非PIT', '生存者偏差')),
    'oldLiveTextAbsent': not any(x in js_text for x in ('完成周RSI6收复20', '周RSI6收复20',
                                      '周RSI6升序', '最长5日')),
    'task107Top20Retained': all(x in js_text for x in ('rsi6-dividend-top20',
                                      '明确命中排雷剔除并顺延补足', '未覆盖仅标未核验')),
    'remoteAndLocalFundDataUnchanged': all(x['remoteBeforeAfterUnchanged'] and x['localUnchanged']
                                      for x in online_data.values()),
    'onlineFundDataByteEqualsRemoteCommit': all(x['onlineEqualsRemoteCommit'] for x in online_data.values()),
}
result = {
    'task': 108, 'commit': COMMIT, 'parent': push['parent'], 'mainAtVerification': main,
    'run': {'id': run['id'], 'event': run['event'], 'status': run['status'],
            'conclusion': run['conclusion'], 'headSha': run['head_sha'],
            'url': run.get('html_url'), 'createdAt': run.get('created_at'), 'updatedAt': run.get('updated_at')},
    'pages': {'url': BASE, 'js': {'path': js_name, 'bytes': len(js_raw),
              'sha256': hashlib.sha256(js_raw).hexdigest()},
              'css': {'path': css_name, 'bytes': len(css_raw),
              'sha256': hashlib.sha256(css_raw).hexdigest()}},
    'fundData': online_data,
    'historicalCache': {'file': 'scripts/cache/vcp_cache.json', 'key': 'sectorValuationHistory',
                        'independentNestedKey': True, 'preservesOtherFieldsTested': True,
                        'workflowModified': False},
    'manualDispatch': False, 'productionDataRegeneratedByThisRelease': False,
    'productionDataNote': '线上fund_data保持发布前快照；新动态信号与历史估值清单等待既有计划任务。',
    'checks': checks, 'allPassed': all(checks.values()),
}
(ROOT / 'zz_task108_online_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
if not result['allPassed']:
    raise SystemExit(1)
