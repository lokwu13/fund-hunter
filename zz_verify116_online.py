# -*- coding: utf-8 -*-
"""任务116线上核验：等待目标commit自动push run；只读页面/数据，严格限制产物冲突修复范围。"""
import ast
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
push = json.loads((ROOT / 'zz_push116.json').read_text(encoding='utf-8'))
COMMIT = push['commit']
cred = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                      text=True, capture_output=True, check=True).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
api = requests.Session()
api.headers.update({'Authorization': f"Bearer {fields['password']}", 'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'fund-hunter-task116-verification'})
web = requests.Session()
web.headers.update({'User-Agent': 'fund-hunter-task116-http-verification'})
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
    """唯一允许的写操作：目标run重复github-pages产物清理+一个失败job重跑一次。"""
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
assert run.get('status') == 'completed' and run.get('conclusion') == 'success', {
    'run': result_run, 'artifactRepair': artifact_repair}
main = req(f'/repos/{REPO}/git/ref/heads/main')['object']['sha']
commit = req(f'/repos/{REPO}/git/commits/{COMMIT}')
assert commit['parents'][0]['sha'] == push['parent']

page = js_name = css_name = None
js_raw = css_raw = None
http_resources = {}
markers = ('高股息防御 · 逐指数独立榜', '20整不触发', '其他宽基触发不打开本榜',
           '每榜最多10只', '有效正股息率', 'index-dividend-defensive', 'membershipAsOf',
           '无形态、价格位置、估值历史分位、阶段缩量、均线、市值或资金流门')
legacy_markers = ('全A股息率TTM Top20', 'rsi6Top20', 'rsi6-dividend-top20')
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
        if all(x in js_raw.decode('utf-8') for x in markers):
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
production = content('scripts/update_data.py', COMMIT).decode('utf-8')
types = content('src/hooks/useFundData.ts', COMMIT).decode('utf-8')
funnel = content('src/sections/funnelConclusions.ts', COMMIT).decode('utf-8')
weekly = content('src/sections/WeeklySummary.tsx', COMMIT).decode('utf-8')
sector = content('src/sections/SectorHeatmap.tsx', COMMIT).decode('utf-8')
tree = ast.parse(production)
main_node = next(x for x in tree.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == 'main')
main_calls = {x.func.id for x in ast.walk(main_node)
              if isinstance(x, ast.Call) and isinstance(x.func, ast.Name)}
local_page = (ROOT / 'dist/index.html').read_text(encoding='utf-8')
local_assets = []
for match in re.finditer(r'(?:src|href)="([^"]*assets/index-[^"]+\.(?:js|css))"', local_page):
    relative = match.group(1).lstrip('/')
    if relative.startswith('fund-hunter/'):
        relative = relative[len('fund-hunter/'):]
    path = ROOT / 'dist' / relative
    raw = path.read_bytes()
    local_assets.append({'path': f'dist/{relative}', 'bytes': len(raw), 'sha256': sha(raw)})

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
browser_note = ('未执行真实浏览器console核验；仅完成只读HTTP/bundle核验，不把资源检查冒充浏览器运行检查。')
checks = {
    'automaticPushRunSuccess': run.get('event') == 'push' and run.get('head_sha') == COMMIT
                               and run.get('conclusion') == 'success',
    'realParentAndNonForce': commit['parents'][0]['sha'] == push['parent'] and push['force'] is False,
    'task116BundleMarkersPublished': all(x in js_text for x in markers),
    'legacyBundleMarkersAbsent': all(x not in js_text for x in legacy_markers),
    'sixIndependentStrictRsiBoardsInTargetCommit': all(x in production for x in (
        "('000016.SH', '上证50')", "('000300.SH', '沪深300')", "('000510.SH', '中证A500')",
        "('000905.SH', '中证500')", "('000688.SH', '科创50')", "('399673.SZ', '创业板50')",
        'INDEX_DIVIDEND_TOP_N = 10', 'INDEX_DIVIDEND_RSI_THRESHOLD = 20.0',
        'rsi < INDEX_DIVIDEND_RSI_THRESHOLD', 'def _index_dividend_boards',
        'def build_index_dividend_watch', '_weekly_rsi6_evidence', 'dynamicWeeklyFresh',
        'daily_basic(trade_date=effective', 'memberSnapshots', 'snapshot_dates != {effective}')),
    'onlyNewProductionEntryInTargetCommit': 'build_index_dividend_watch' in main_calls
                                             and 'build_dividend_watch' not in main_calls,
    'frontendSharedEvidenceInTargetCommit': all(x in types + funnel + weekly + sector for x in (
        'indexBoards', 'dividendDefenseText', 'index-dividend-defensive', 'membershipAsOf',
        'validDividendCount', 'missingDividendCount', 'nonPositiveDividendCount', '20整不触发')),
    'remoteAndLocalFundDataUnchanged': all(x['remoteBeforeAfterUnchanged'] and x['localUnchanged']
                                           for x in online_data.values()),
    'onlineFundDataByteEqualsRemoteCommit': all(x['onlineEqualsRemoteCommit'] for x in online_data.values()),
    'httpResourcesNo404': all(x['status'] == 200 for x in http_resources.values()),
}
result = {
    'task': 116, 'commit': COMMIT, 'parent': push['parent'], 'mainAtVerification': main,
    'run': result_run, 'artifactRepair': artifact_repair,
    'pages': {'url': BASE, 'js': {'path': js_name, 'bytes': len(js_raw), 'sha256': sha(js_raw)},
              'css': {'path': css_name, 'bytes': len(css_raw), 'sha256': sha(css_raw)}},
    'httpResources': http_resources, 'bundleMarkers': {x: x in js_text for x in markers},
    'legacyBundleMarkersPresent': {x: x in js_text for x in legacy_markers},
    'localWindowsAssets': local_assets,
    'crossPlatformHashNote': 'Windows与Linux CI构建哈希可能不同；以目标commit自动push run及线上功能标记为准。',
    'fundData': online_data, 'manualDispatch': False, 'nightlyExecuted': False,
    'workflowModified': False, 'scheduleModified': False,
    'productionDataRegeneratedByThisRelease': False,
    'productionListRefreshVerified': False,
    'productionListRefreshNote': '本次只发布代码，不手动执行nightly；线上既有名单未按新规则重算。',
    'browser': {'consoleVerified': False, 'executables': browser_executables,
                'knownPathsFound': browser_paths_found, 'automationModules': browser_modules,
                'note': browser_note},
    'checks': checks, 'allPassed': all(checks.values()),
}
(ROOT / 'zz_task116_online_verification.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['allPassed'] else 1)
