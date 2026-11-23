# -*- coding: utf-8 -*-
"""概念真实样本修复线上只读核验：自动push run、HTTP/bundle、生产SHA。"""
import base64
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
REPO = 'lokwu13/fund-hunter'
BASE = 'https://lokwu13.github.io/fund-hunter/'
push = json.loads((ROOT / 'zz_push_concept_sample.json').read_text(encoding='utf-8'))
COMMIT = push['commit']
cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
api = requests.Session()
api.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-concept-sample-verification'})
web = requests.Session()
web.headers.update({'User-Agent': 'fund-hunter-concept-sample-http-readonly'})

def req(path):
    response = api.get('https://api.github.com' + path, timeout=60)
    if not response.ok:
        raise RuntimeError(f'{path}: {response.status_code} {response.text[:500]}')
    return response.json()

def content(path, ref):
    obj = req(f'/repos/{REPO}/contents/{path}?ref={ref}')
    if obj.get('content'):
        return base64.b64decode(obj['content'])
    return base64.b64decode(req(f'/repos/{REPO}/git/blobs/{obj["sha"]}')['content'])

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def target_run():
    runs = req(f'/repos/{REPO}/actions/runs?event=push&per_page=100').get('workflow_runs') or []
    candidates = [x for x in runs if x.get('head_sha') == COMMIT]
    candidates.sort(key=lambda x: (x.get('created_at') or '', x['id']), reverse=True)
    return candidates[0] if candidates else None

run = None
deadline = time.time() + 230
while time.time() < deadline:
    run = target_run()
    if run and run.get('status') == 'completed':
        break
    time.sleep(10)
assert run, '目标commit自动push run尚未出现'
run_info = {'id': run['id'], 'name': run.get('name'), 'event': run['event'], 'status': run['status'],
            'conclusion': run.get('conclusion'), 'headSha': run['head_sha'], 'url': run.get('html_url'),
            'createdAt': run.get('created_at'), 'updatedAt': run.get('updated_at')}
assert run.get('status') == 'completed' and run.get('conclusion') == 'success', run_info
main = req(f'/repos/{REPO}/git/ref/heads/main')['object']['sha']
commit = req(f'/repos/{REPO}/git/commits/{COMMIT}')
assert commit['parents'][0]['sha'] == push['parent']

page = js_name = css_name = None
js_raw = css_raw = None
http_resources = {}
page_deadline = time.time() + 100
while time.time() < page_deadline:
    buster = f'{run["id"]}-{time.time_ns()}'
    response = web.get(BASE, params={'v': buster}, timeout=60)
    response.raise_for_status()
    page = response.text
    http_resources['page'] = {'url': response.url, 'status': response.status_code,
                              'bytes': len(response.content), 'sha256': sha(response.content)}
    jm = re.search(r'src="(/fund-hunter/assets/index-[^"]+\.js)"', page)
    cm = re.search(r'href="(/fund-hunter/assets/index-[^"]+\.css)"', page)
    if jm and cm:
        js_name, css_name = jm.group(1), cm.group(1)
        jr = web.get('https://lokwu13.github.io' + js_name, params={'v': buster}, timeout=90)
        cr = web.get('https://lokwu13.github.io' + css_name, params={'v': buster}, timeout=90)
        jr.raise_for_status()
        cr.raise_for_status()
        js_raw, css_raw = jr.content, cr.content
        http_resources['js'] = {'url': jr.url, 'status': jr.status_code, 'bytes': len(js_raw), 'sha256': sha(js_raw)}
        http_resources['css'] = {'url': cr.url, 'status': cr.status_code, 'bytes': len(css_raw), 'sha256': sha(css_raw)}
        if all(x in js_raw.decode('utf-8') for x in ('amountSource', '样本不足', '真实成交额')):
            break
    time.sleep(10)
assert page and js_raw and css_raw
js_text = js_raw.decode('utf-8')
online_data = {}
online_response = web.get(BASE + 'fund_data.json', params={'v': time.time_ns()}, timeout=90)
online_response.raise_for_status()
online_raw = online_response.content
http_resources['fund_data'] = {'url': online_response.url, 'status': online_response.status_code,
                               'bytes': len(online_raw), 'sha256': sha(online_raw)}
for path in ('public/fund_data.json', 'src/data/fund_data.json'):
    remote_raw = content(path, COMMIT)
    online_data[path] = {'remoteCommitBytes': len(remote_raw), 'remoteCommitSha256': sha(remote_raw),
                         'onlineBytes': len(online_raw), 'onlineSha256': sha(online_raw),
                         'onlineEqualsRemoteCommit': online_raw == remote_raw,
                         'remoteBeforeAfterUnchanged': push['remoteFundDataBefore'][path] == push['remoteFundDataAfter'][path],
                         'localUnchanged': push['localFundDataBefore'][path] == push['localFundDataAfter'][path]}
production = json.loads(online_raw.decode('utf-8'))
old_module = production.get('sectorCrowding') or {}
remote_sources = {path: content(path, COMMIT) for path in (
    'scripts/update_data.py', 'scripts/vcp_preview.py', 'src/hooks/useFundData.ts', 'src/sections/SectorHeatmap.tsx')}
browser_executables = {name: shutil.which(name) for name in ('chrome', 'chrome.exe', 'msedge', 'msedge.exe', 'chromium', 'chromium.exe')}
known_browser_paths = [r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                       r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
                       r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                       r'C:\Program Files\Microsoft\Edge\Application\msedge.exe']
browser_paths_found = [p for p in known_browser_paths if Path(p).is_file()]
browser_modules = {name: importlib.util.find_spec(name) is not None for name in ('playwright', 'selenium', 'puppeteer')}
checks = {
    'automaticPushRunSuccess': run.get('event') == 'push' and run.get('head_sha') == COMMIT and run.get('conclusion') == 'success',
    'realParentAndNonForce': commit['parents'][0]['sha'] == push['parent'] and push['force'] is False,
    'remoteSourcesMatchLocal': all(raw == (ROOT / path).read_bytes() for path, raw in remote_sources.items()),
    'newBackendRealSampleChainPublished': all(x in remote_sources['scripts/update_data.py'].decode('utf-8') for x in (
        'concept_heat_daily', 'concept_heat_universe', 'conceptCoverage', 'ensure_concept_heat_daily')),
    'newFetcherFourFieldsPublished': all(x in remote_sources['scripts/vcp_preview.py'].decode('utf-8') for x in (
        "CONCEPT_HEAT_SCHEMA = ['date', 'close', 'volume', 'amount']", '_ths_public_year_rows', 'CONCEPT_HEAT_UNIVERSE_NAMES')),
    'bundleMarkersPublished': all(x in js_text for x in ('amountSource', '样本不足', '真实成交额')),
    'remoteAndLocalFundDataUnchanged': all(x['remoteBeforeAfterUnchanged'] and x['localUnchanged'] for x in online_data.values()),
    'onlineFundDataByteEqualsRemoteCommit': all(x['onlineEqualsRemoteCommit'] for x in online_data.values()),
    'httpResourcesNo404': all(x['status'] == 200 for x in http_resources.values()),
    'productionWaitsNormalNightlyRecompute': old_module.get('trade_date') == '2026-11-20'
        and any(x.get('type') == '概念' and x.get('heatReady') is False for x in old_module.get('items') or []),
}
result = {
    'task': 'concept-sample', 'commit': COMMIT, 'parent': push['parent'], 'mainAtVerification': main,
    'run': run_info, 'pages': {'url': BASE, 'js': {'path': js_name, 'bytes': len(js_raw), 'sha256': sha(js_raw)},
                                'css': {'path': css_name, 'bytes': len(css_raw), 'sha256': sha(css_raw)}},
    'httpResources': http_resources, 'bundleMarkers': {x: x in js_text for x in ('amountSource', '样本不足', '真实成交额')},
    'fundData': online_data, 'currentOnlineSectorCrowding': old_module,
    'currentOnlineDataNote': '生产JSON未重写；当前名单仍是2026-11-20旧结果，需下一次正常数据更新生成新缓存并重算。',
    'manualDispatch': False, 'nightlyExecuted': False, 'workflowModified': False, 'scheduleModified': False,
    'productionDataRegeneratedByThisRelease': False,
    'browser': {'consoleVerified': False, 'executables': browser_executables, 'knownPathsFound': browser_paths_found,
                'automationModules': browser_modules,
                'note': '未执行真实浏览器console核验；仅完成只读HTTP/bundle及活动源码核验。'},
    'checks': checks, 'allPassed': all(checks.values()),
}
(ROOT / 'zz_concept_sample_online_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['allPassed'] else 1)
