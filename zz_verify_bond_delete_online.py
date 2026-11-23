# -*- coding: utf-8 -*-
"""债券栏目删减线上核验：目标commit自动push run、HTTP/bundle、活动代码与历史数据分离。"""
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
push = json.loads((ROOT / 'zz_push_bond_delete.json').read_text(encoding='utf-8'))
COMMIT = push['commit']
cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
api = requests.Session()
api.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-bond-delete-verification'})
web = requests.Session()
web.headers.update({'User-Agent': 'fund-hunter-bond-delete-http-verification'})
artifact_repair = {'attempted': False, 'runId': None, 'deletedArtifactIds': [],
                   'rerunJobId': None, 'note': '未发生或无需处理；绝不触碰其他run。'}


def req(path, method='GET', **kwargs):
    response = api.request(method, 'https://api.github.com' + path, timeout=60, **kwargs)
    if not response.ok:
        raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:500]}')
    return response.json() if response.content else {}


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


def repair_own_duplicate_pages_artifacts(run):
    jobs = req(f'/repos/{REPO}/actions/runs/{run["id"]}/jobs?per_page=100').get('jobs') or []
    failed = [x for x in jobs if x.get('conclusion') not in (None, 'success', 'skipped', 'neutral')]
    artifacts = req(f'/repos/{REPO}/actions/runs/{run["id"]}/artifacts?per_page=100').get('artifacts') or []
    pages = [x for x in artifacts if x.get('name') == 'github-pages' and not x.get('expired')]
    if len(pages) < 2 or not failed:
        return False
    artifact_repair.update({'attempted': True, 'runId': run['id'],
                            'note': '仅清理本目标run重复github-pages artifacts，并重跑一个失败job一次。'})
    pages.sort(key=lambda x: (x.get('created_at') or '', x['id']))
    for artifact in pages[1:]:
        req(f'/repos/{REPO}/actions/artifacts/{artifact["id"]}', method='DELETE')
        artifact_repair['deletedArtifactIds'].append(artifact['id'])
    job = sorted(failed, key=lambda x: x['id'])[0]
    req(f'/repos/{REPO}/actions/jobs/{job["id"]}/rerun', method='POST')
    artifact_repair['rerunJobId'] = job['id']
    return True


run = None
deadline = time.time() + 300
while time.time() < deadline:
    run = target_run()
    if run and run.get('status') == 'completed':
        if run.get('conclusion') == 'success':
            break
        if not artifact_repair['attempted'] and repair_own_duplicate_pages_artifacts(run):
            run = None
            deadline = time.time() + 300
            time.sleep(10)
            continue
        break
    time.sleep(10)
assert run, '目标commit自动push run尚未出现'
result_run = {'id': run['id'], 'name': run.get('name'), 'event': run['event'],
              'status': run['status'], 'conclusion': run.get('conclusion'),
              'headSha': run['head_sha'], 'url': run.get('html_url'),
              'createdAt': run.get('created_at'), 'updatedAt': run.get('updated_at')}
assert run.get('status') == 'completed' and run.get('conclusion') == 'success', result_run
main = req(f'/repos/{REPO}/git/ref/heads/main')['object']['sha']
commit = req(f'/repos/{REPO}/git/commits/{COMMIT}')
assert commit['parents'][0]['sha'] == push['parent']

retained = ('债市信号 → A+H股市一个月影响推演', '央行短期流动性工具', '滚动波动率（20日标准差）',
            '今日债市要闻 · 东方财富', '近期债市动态', 'bond-margin', '中美利差(45%)')
removed = ('债券市场要闻', '中美国债收益率对比', '美元资产吸引力更高', '人民币资产吸引力更高')
page = js_name = css_name = None
js_raw = css_raw = None
http_resources = {}
page_deadline = time.time() + 180
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
        js_response = web.get('https://lokwu13.github.io' + js_name, params={'v': buster}, timeout=90)
        css_response = web.get('https://lokwu13.github.io' + css_name, params={'v': buster}, timeout=90)
        js_response.raise_for_status()
        css_response.raise_for_status()
        js_raw, css_raw = js_response.content, css_response.content
        http_resources['js'] = {'url': js_response.url, 'status': js_response.status_code,
                                'bytes': len(js_raw), 'sha256': sha(js_raw)}
        http_resources['css'] = {'url': css_response.url, 'status': css_response.status_code,
                                 'bytes': len(css_raw), 'sha256': sha(css_raw)}
        text = js_raw.decode('utf-8')
        if all(x in text for x in retained) and all(x not in text for x in removed[:2]):
            break
    time.sleep(10)
assert page and js_raw and css_raw
js_text = js_raw.decode('utf-8')
online_data = {}
for path in ('public/fund_data.json', 'src/data/fund_data.json'):
    remote_raw = content(path, COMMIT)
    online_response = web.get(BASE + 'fund_data.json', params={'v': time.time_ns()}, timeout=90)
    online_response.raise_for_status()
    online_raw = online_response.content
    http_resources[f'fund_data:{path}'] = {
        'url': online_response.url, 'status': online_response.status_code,
        'bytes': len(online_raw), 'sha256': sha(online_raw)}
    online_data[path] = {
        'remoteCommitBytes': len(remote_raw), 'remoteCommitSha256': sha(remote_raw),
        'onlineBytes': len(online_raw), 'onlineSha256': sha(online_raw),
        'onlineEqualsRemoteCommit': online_raw == remote_raw,
        'remoteBeforeAfterUnchanged': push['remoteFundDataBefore'][path] == push['remoteFundDataAfter'][path],
        'localUnchanged': push['localFundDataBefore'][path] == push['localFundDataAfter'][path],
    }
remote_panel = content('src/sections/BondsPanel.tsx', COMMIT).decode('utf-8')
remote_backend = content('scripts/update_data.py', COMMIT)
remote_data_text = content('public/fund_data.json', COMMIT).decode('utf-8')
removed_attribution = {
    x: {'inBundle': x in js_text, 'inUnchangedRemoteProductionData': x in remote_data_text,
        'inActiveBondsPanel': x in remote_panel}
    for x in removed
}
browser_executables = {name: shutil.which(name) for name in (
    'chrome', 'chrome.exe', 'msedge', 'msedge.exe', 'chromium', 'chromium.exe')}
known_browser_paths = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
]
browser_paths_found = [p for p in known_browser_paths if Path(p).is_file()]
browser_modules = {name: importlib.util.find_spec(name) is not None for name in (
    'playwright', 'selenium', 'puppeteer')}
checks = {
    'automaticPushRunSuccess': run.get('event') == 'push' and run.get('head_sha') == COMMIT
                               and run.get('conclusion') == 'success',
    'realParentAndNonForce': commit['parents'][0]['sha'] == push['parent'] and push['force'] is False,
    'remotePanelMatchesLocal': remote_panel.encode('utf-8') == (ROOT / 'src/sections/BondsPanel.tsx').read_bytes(),
    'targetTitlesAbsentInActiveSource': all(x not in remote_panel for x in ('债券市场要闻', '中美国债收益率对比')),
    'targetCompleteCardsAbsentInActiveSource': 'news.map((item, idx)' not in remote_panel
                                               and '{us && us.latest && (' not in remote_panel
                                               and 'layout="vertical"' not in remote_panel,
    'sharedBondModulesRetainedInActiveSource': all(x in remote_panel for x in (
        'const us = bd.us || null;', 'const news = bd.news || [];', '央行短期流动性工具',
        '滚动波动率（20日标准差）', '债市信号 → A+H股市一个月影响推演', 'const usCnSpread')),
    'backendUnchanged': remote_backend == (ROOT / 'zz_bond_delete_update_data_baseline.py').read_bytes(),
    'retainedBundleMarkersPublished': all(x in js_text for x in retained),
    'removedBundleStringsAbsentOrOnlyPreservedData': all(
        not x['inActiveBondsPanel'] and (not x['inBundle'] or x['inUnchangedRemoteProductionData'])
        for x in removed_attribution.values()),
    'remoteAndLocalFundDataUnchanged': all(x['remoteBeforeAfterUnchanged'] and x['localUnchanged']
                                           for x in online_data.values()),
    'onlineFundDataByteEqualsRemoteCommit': all(x['onlineEqualsRemoteCommit'] for x in online_data.values()),
    'httpResourcesNo404': all(x['status'] == 200 for x in http_resources.values()),
}
result = {
    'task': 'bond-delete', 'commit': COMMIT, 'parent': push['parent'], 'mainAtVerification': main,
    'run': result_run, 'artifactRepair': artifact_repair,
    'pages': {'url': BASE, 'js': {'path': js_name, 'bytes': len(js_raw), 'sha256': sha(js_raw)},
              'css': {'path': css_name, 'bytes': len(css_raw), 'sha256': sha(css_raw)}},
    'httpResources': http_resources, 'retainedBundleMarkers': {x: x in js_text for x in retained},
    'removedBundleMarkersPresent': {x: x in js_text for x in removed},
    'removedStringAttribution': removed_attribution,
    'dataStringNote': '线上bundle旧标题或专属文案若存在，只允许来自发布前后逐字节未变的历史生产JSON；活动BondsPanel不得包含。',
    'fundData': online_data, 'manualDispatch': False, 'nightlyExecuted': False,
    'workflowModified': False, 'scheduleModified': False, 'productionDataRegeneratedByThisRelease': False,
    'browser': {'consoleVerified': False, 'executables': browser_executables,
                'knownPathsFound': browser_paths_found, 'automationModules': browser_modules,
                'note': '未执行真实浏览器console核验；仅完成只读HTTP/bundle及活动源码核验。'},
    'checks': checks, 'allPassed': all(checks.values()),
}
(ROOT / 'zz_bond_delete_online_verification.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['allPassed'] else 1)
