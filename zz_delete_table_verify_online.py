# -*- coding: utf-8 -*-
"""目标 commit 自动 push 部署与线上只读核验；不 dispatch、不改生产 JSON。"""
import hashlib
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
REPO = 'lokwu13/fund-hunter'
BASE = 'https://lokwu13.github.io/fund-hunter/'
push = json.loads((ROOT / 'zz_delete_table_push.json').read_text(encoding='utf-8'))
preflight = json.loads((ROOT / 'zz_delete_table_live_preflight.json').read_text(encoding='utf-8'))
build = json.loads((ROOT / 'zz_delete_table_build.json').read_text(encoding='utf-8'))
commit = push['commit']

cred = subprocess.run(
    ['git', 'credential', 'fill'],
    input='protocol=https\nhost=github.com\n\n',
    text=True, capture_output=True, check=True,
).stdout
fields = dict(line.split('=', 1) for line in cred.splitlines() if '=' in line)
api = requests.Session()
api.headers.update({
    'Authorization': f"Bearer {fields['password']}",
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'fund-hunter-delete-table-verify',
})
web = requests.Session()
web.headers.update({
    'User-Agent': 'fund-hunter-delete-table-readonly',
    'Cache-Control': 'no-cache',
})


def req(path):
    response = api.get('https://api.github.com' + path, timeout=60)
    response.raise_for_status()
    return response.json()


def target_run():
    runs = req(f'/repos/{REPO}/actions/runs?event=push&branch=main&per_page=100').get('workflow_runs') or []
    return next((run for run in runs if run.get('head_sha') == commit), None)


run = None
deadline = time.monotonic() + 600
while time.monotonic() < deadline:
    run = target_run()
    if run and run.get('status') == 'completed':
        break
    time.sleep(12)
assert run and run.get('status') == 'completed', f'目标 commit 自动 push run 未完成：{run}'
assert run.get('conclusion') == 'success', f'目标 run 失败：{run.get("id")} {run.get("html_url")}'

html_response = web.get(BASE, params={'v': commit}, timeout=90)
html_response.raise_for_status()
bundle_urls = []
for src in re.findall(r'<script[^>]+src=["\']([^"\']+\.js)["\']', html_response.text):
    bundle_urls.append(src if src.startswith('http') else requests.compat.urljoin(BASE, src))
assert bundle_urls, '线上 HTML 无 JS bundle'

expected_js = {
    Path(asset['path']).name: asset['sha256']
    for asset in build['assets'] if asset['path'].endswith('.js')
}
online_js_names = {url.rsplit('/', 1)[-1] for url in bundle_urls}
bundle_results = []
bundle_text = ''
for url in bundle_urls:
    response = web.get(url, params={'v': commit}, timeout=90)
    sha256 = hashlib.sha256(response.content).hexdigest()
    bundle_results.append({
        'url': response.url,
        'status': response.status_code,
        'bytes': len(response.content),
        'sha256': sha256,
    })
    response.raise_for_status()
    bundle_text += response.text

removed = {text: text in bundle_text for text in build['removedBundleMarkersPresent']}
retained = {text: text in bundle_text for text in build['retainedBundleMarkers']}
production = web.get(BASE + 'fund_data.json', params={'v': commit}, timeout=90)
production.raise_for_status()
production_sha = hashlib.sha256(production.content).hexdigest()
production_doc = production.json()
shared_data_fields = all(
    isinstance(production_doc.get(key), dict) and 'week' in production_doc[key]
    for key in ('northbound', 'southbound')
)
expected_sha = preflight['onlineFundDataSha256']
not_found_url = BASE + f'assets/__delete_table_404_{commit[:12]}__.js'
not_found = web.get(not_found_url, timeout=60)
checks = {
    'targetCommitPushRunSuccess': run.get('head_sha') == commit and run.get('event') == 'push'
                                  and run.get('status') == 'completed' and run.get('conclusion') == 'success',
    'http200': html_response.status_code == 200 and production.status_code == 200
               and all(item['status'] == 200 for item in bundle_results),
    'http404': not_found.status_code == 404,
    'currentHtmlUsesLocalBuildBundle': online_js_names == set(expected_js)
                                       and all(item['sha256'] == expected_js[item['url'].rsplit('/', 1)[-1].split('?')[0]]
                                               for item in bundle_results),
    'targetTitlesAbsentInCurrentBundle': not any(removed.values()),
    'retainedMarkersInCurrentBundle': all(retained.values()),
    'productionDataShaUnchanged': production_sha == expected_sha
                                  == push['remoteFundDataAfter']['public/fund_data.json']['sha256'],
    'sharedProductionFieldsRetained': shared_data_fields,
    'noNightlyOrProductionWrite': not push['nightlyExecuted'] and not push['productionDataRegenerated']
                                  and not push['workflowModified'] and not push['scheduleModified'],
}
result = {
    'task': 'delete-table',
    'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
    'commit': commit,
    'run': {
        'id': run['id'], 'name': run.get('name'), 'event': run.get('event'),
        'headSha': run.get('head_sha'), 'status': run.get('status'),
        'conclusion': run.get('conclusion'), 'url': run.get('html_url'),
        'runAttempt': run.get('run_attempt'),
    },
    'http': {
        'page': html_response.status_code,
        'fundData': production.status_code,
        'bundles': bundle_results,
        'expected404': not_found.status_code,
        'expected404Url': not_found_url,
    },
    'currentHtmlBundleNames': sorted(online_js_names),
    'expectedLocalBundleNames': sorted(expected_js),
    'removedBundleMarkersPresent': removed,
    'retainedBundleMarkers': retained,
    'localBuildAssets': build['assets'],
    'productionFundDataSha256': production_sha,
    'expectedProductionFundDataSha256': expected_sha,
    'sharedProductionFieldsRetained': shared_data_fields,
    'checks': checks,
    'allPassed': all(checks.values()),
    'manualDispatch': False,
    'productionDataRegenerated': False,
    'workflowModified': False,
    'browserConsoleVerified': False,
    'browserLimitation': '仅做 HTTP、当前 HTML 实际引用 bundle 与生产 JSON 只读核验；未执行浏览器渲染、Console 或交互巡检。',
}
(ROOT / 'zz_delete_table_online_verification.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
if not result['allPassed']:
    raise SystemExit(1)
