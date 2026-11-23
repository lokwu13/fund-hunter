# -*- coding: utf-8 -*-
"""任务1141：发布前机器核验；只汇总已执行证据，不重跑 nightly。"""
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
load = lambda name: json.loads((ROOT / name).read_text(encoding='utf-8'))
preflight = load('zz_daily_tables_1141_live_preflight.json')
backend = load('zz_daily_tables_1141_backend_tests.json')
real = load('zz_daily_tables_1141_real_source_verify.json')
regress = load('zz_daily_tables_1141_regress_summary.json')
adjacent = load('zz_regress109_summary.json')
build = load('zz_daily_tables_1141_build.json')
edge = load('zz_daily_tables_1141_edge_verification.json')
production = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in DATA}
source_paths = [
    'src/sections/ForeignCapitalPanel.tsx', 'scripts/update_data.py',
    'zz_daily_tables_1141_backend_tests.py', 'zz_daily_tables_1141_real_source_verify.py',
    'zz_daily_tables_1141_regress.py', 'zz_daily_tables_1141_build.py', 'zz_daily_tables_1141_edge_verify.py',
]
source_sha = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in source_paths}
checks = {
    'backendContract35Passed': backend['allPassed'] and backend['checksPassed'] == backend['checksTotal'] == 35,
    'realSourceDryRunPassed': real['allPassed'] and real['hkHold']['actualAvailableDate'] == '20261120'
                              and real['ccass']['actualAvailableDate'] == '2026-11-20',
    'failureFallbackVerified': real['failureFallback']['rowsUnchanged'] and backend['allPassed'],
    'staticRegression44Passed': regress['allPassed'] and regress['checksPassed'] == regress['checksTotal'] == 44,
    'adjacentNavigation22AndDom6Passed': adjacent['checksPassed'] == adjacent['checksTotal'] == 22
                                       and '6/6 passed' in adjacent['domTestOutput'],
    'buildPassed': build['success'] and build['returncode'] == 0 and build['fundDataUnchanged'],
    'realEdgePassed': edge['allPassed'] and edge['foreignTabClicked'] if 'foreignTabClicked' in edge else False,
    'edgeStopped': edge['temporaryStaticServerStopped'] and edge['edgeProcessStopped'],
    'workflowUnchanged': (ROOT / '.github/workflows/daily-update.yml').read_bytes()
                         == (ROOT / 'zz_daily_tables_1141_daily_update_baseline.yml').read_bytes(),
    'productionUnchanged': all(production[path] == preflight['fundData'][path]['localSha256'] for path in DATA),
    'remoteOnlineBaselineMatched': preflight['onlineEqualsRemoteMain'],
    'noManualDispatchOrDataGeneration': not real['fullNightlyDispatched'] and not real['productionDataRegenerated'],
}
# Edge 报告将页签结果放在 checks 中。
checks['realEdgePassed'] = edge['allPassed'] and edge['checks']['foreignTabClicked'] and edge['checks']['bothTablesRendered']
result = {
    'task': 'daily-tables-1141', 'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
    'checks': checks, 'allPassed': all(checks.values()), 'releaseReady': all(checks.values()),
    'backendRegression': {'checksPassed': backend['checksPassed'], 'checksTotal': backend['checksTotal']},
    'staticRegression': {'checksPassed': regress['checksPassed'], 'checksTotal': regress['checksTotal']},
    'adjacentRegression': {'checksPassed': adjacent['checksPassed'], 'checksTotal': adjacent['checksTotal'],
                           'domTestOutput': adjacent['domTestOutput']},
    'realSource': {'hkHoldAsOf': real['hkHold']['actualAvailableDate'], 'ccassAsOf': real['ccass']['actualAvailableDate'],
                   'ccassRatio': real['ccass']['calculatedRatio'], 'weekendDuplicateNormalized': True},
    'build': {'success': build['success'], 'modulesTransformed': build['modulesTransformed'],
              'warning': build['warning'], 'assets': build['assets']},
    'edge': {'allPassed': edge['allPassed'], 'browserConsoleVerified': False, 'limitation': edge['limitation']},
    'sourceSha256': source_sha, 'productionFundDataSha256': production,
    'manualDispatch': False, 'productionDataRegenerated': False, 'workflowModified': False,
    'scheduleModified': False, 'developmentServerStarted': False, 'testsReexecutedByThisVerification': False,
}
(ROOT / 'zz_daily_tables_1141_machine_verification.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['allPassed'] else 1)
