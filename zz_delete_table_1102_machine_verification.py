# -*- coding: utf-8 -*-
"""任务1102发布前只读机器核验；不重跑测试、不生成生产数据。"""
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
regression = json.loads((ROOT / 'zz_delete_table_1102_regress_summary.json').read_text(encoding='utf-8'))
adjacent = json.loads((ROOT / 'zz_regress109_summary.json').read_text(encoding='utf-8'))
build = json.loads((ROOT / 'zz_delete_table_1102_build.json').read_text(encoding='utf-8'))
edge = json.loads((ROOT / 'zz_delete_table_1102_edge_verification.json').read_text(encoding='utf-8'))
preflight = json.loads((ROOT / 'zz_delete_table_1102_live_preflight.json').read_text(encoding='utf-8'))
panel = (ROOT / 'src/sections/ForeignCapitalPanel.tsx').read_text(encoding='utf-8')
checks = {
    'targetedRegression29Passed': regression['allPassed']
                                   and regression['checksPassed'] == regression['checksTotal'] == 29
                                   and not regression['failed'],
    'adjacentNavigation22AndDom6Passed': adjacent['checksPassed'] == adjacent['checksTotal'] == 22
                                         and not adjacent['failed']
                                         and '6/6 passed' in adjacent['domTestOutput'],
    'buildPassed': build['success'] and build['returncode'] == 0
                   and build['fundDataUnchanged'] and build['matchesRegressionDataSha']
                   and all(build['retainedBundleMarkers'].values())
                   and not any(build['removedBundleMarkersPresent'].values())
                   and build['viewportMetaPresent'],
    'realEdgeVerificationPassed': edge['allPassed'] and edge['checks']['foreignTabClicked']
                                  and edge['checks']['targetCardAbsent']
                                  and edge['checks']['adjacentDivergenceModulesRetained']
                                  and edge['temporaryStaticServerStopped'] and edge['edgeProcessStopped'],
    'targetMarkersAbsentInActivePanel': all(marker not in panel for marker in preflight['targetMarkers']),
    'sharedAndAdjacentModulesRetained': all(marker in panel for marker in (
        '内外资分歧最大十大标的', '如何理解内外资分歧', 'id="ccass-foreign"', 'id="di-foreign"',
        '外资机构增减仓（权益披露）', '南下资金（国内资金）持股集中度TOP10',
        '北向资金近三个月净流入最多TOP10', 'href={it.url}', '>申报书</a>')),
    'backendUnchanged': (ROOT / 'scripts/update_data.py').read_bytes()
                        == (ROOT / 'zz_delete_table_1102_update_data_baseline.py').read_bytes(),
    'protectedFrontendUnchanged': all(
        hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == state['localSha256']
        for path, state in preflight['protectedFrontend'].items()),
    'localProductionDataUnchanged': build['localFundDataBefore'] == build['localFundDataAfter']
                                    and all(build['localFundDataAfter'][path]['sha256'] == sha
                                            for path, sha in regression['productionFundDataSha256'].items()),
    'remoteAndOnlineProductionBaselineMatched': preflight['onlineEqualsRemoteMain']
                                                and preflight['onlineFundDataSha256']
                                                == preflight['fundData']['public/fund_data.json']['remoteSha256'],
    'noForbiddenActions': not regression['productionDataRegenerated']
                          and not build['productionDataRegenerated']
                          and not build['developmentServerStarted']
                          and not preflight['manualDispatch']
                          and not preflight['workflowModified'] and not preflight['scheduleModified'],
}
result = {
    'task': 'delete-table-1102',
    'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
    'checks': checks, 'allPassed': all(checks.values()), 'releaseReady': all(checks.values()),
    'regression': {'allPassed': regression['allPassed'], 'checksPassed': regression['checksPassed'],
                   'checksTotal': regression['checksTotal']},
    'adjacentRegression': {'checksPassed': adjacent['checksPassed'], 'checksTotal': adjacent['checksTotal'],
                           'domTestOutput': adjacent['domTestOutput']},
    'build': {'success': build['success'], 'returncode': build['returncode'],
              'modulesTransformed': build['modulesTransformed'], 'warning': build['warning'],
              'assets': build['assets']},
    'edge': {'allPassed': edge['allPassed'], 'selectedTabs': edge['selectedTabs'],
             'browserConsoleVerified': edge['browserConsoleVerified'], 'limitation': edge['limitation']},
    'sourceSha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                     for path in ('src/sections/ForeignCapitalPanel.tsx',
                                  'zz_delete_table_1102_regress.py', 'zz_delete_table_1102_build.py',
                                  'zz_delete_table_1102_edge_verify.py')},
    'productionFundDataSha256': regression['productionFundDataSha256'],
    'manualDispatch': False, 'productionDataRegenerated': False,
    'workflowModified': False, 'scheduleModified': False, 'developmentServerStarted': False,
    'testsReexecutedByThisVerification': False,
}
(ROOT / 'zz_delete_table_1102_machine_verification.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['allPassed'] else 1)
