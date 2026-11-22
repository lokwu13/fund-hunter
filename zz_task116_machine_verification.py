# -*- coding: utf-8 -*-
"""任务116发布前机器核验；只读取既有测试/构建证据，不重跑测试或生产数据。"""
import ast
import hashlib
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
JOINT_TASKS = [95, 96, 98, 99, 101, 102, 104, 105, 106, 108, 109, 110, 111, 112, 113, 114, 115, 116]
CORE = [
    'scripts/update_data.py', 'src/hooks/useFundData.ts', 'src/sections/funnelConclusions.ts',
    'src/sections/WeeklySummary.tsx', 'src/sections/SectorHeatmap.tsx',
    'zz_regress116.py', 'zz_run_joint116.py', 'zz_build116.py',
]
regression = json.loads((ROOT / 'zz_regress116_summary.json').read_text(encoding='utf-8'))
joint = json.loads((ROOT / 'zz_joint_regress116.json').read_text(encoding='utf-8'))
build = json.loads((ROOT / 'zz_build116.json').read_text(encoding='utf-8'))
preflight = json.loads((ROOT / 'zz_task116_live_preflight.json').read_text(encoding='utf-8'))
superseded = json.loads((ROOT / 'zz_regress107_task116_superseded.json').read_text(encoding='utf-8'))
source = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
frontend = ''.join((ROOT / p).read_text(encoding='utf-8') for p in CORE if p.startswith('src/'))
tree = ast.parse(source)
main_node = next(x for x in tree.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == 'main')
main_calls = {x.func.id for x in ast.walk(main_node)
              if isinstance(x, ast.Call) and isinstance(x.func, ast.Name)}
checks = {
    'task116AllPassed': regression['allPassed'] and not regression['failed']
                        and regression['checksPassed'] == regression['checksTotal'] == 34,
    'jointAllPassed': joint['complete'] and joint['allPassed']
                      and joint['passed'] == joint['executed'] == joint['total'] == 18,
    'jointExactTasks': [x['task'] for x in joint['results']] == JOINT_TASKS
                       and all(x['returncode'] == 0 and x['passed'] for x in joint['results']),
    'jointLogsPresent': all((ROOT / x['log']).is_file()
                            and (ROOT / x['log']).stat().st_size == x['logBytes'] for x in joint['results']),
    'task107ExplicitlySuperseded': joint['superseded'].get('107') == 'zz_regress107_task116_superseded.json'
                                   and superseded['status'] == 'superseded_by_task_116'
                                   and superseded['replacement'] == 'zz_regress116.py',
    'buildPassed': build['success'] and build['returncode'] == 0
                   and build['matchesTask116RegressionDataSha'] and build['fundDataUnchanged']
                   and all(build['bundleMarkers'].values())
                   and not any(build['legacyBundleMarkersPresent'].values()) and build['viewportMetaPresent'],
    'productionDataUnchangedAcrossSuites': build['localFundDataBefore'] == build['localFundDataAfter']
                                           and all(build['localFundDataAfter'][p]['sha256']
                                                   == regression['productionFundDataSha256'][p]
                                                   for p in regression['productionFundDataSha256'])
                                           and all(preflight['fundData'][p]['localSha256']
                                                   == regression['productionFundDataSha256'][p]
                                                   for p in regression['productionFundDataSha256']),
    'sixIndependentStrictRsiBoards': all(x in source for x in (
        'INDEX_DIVIDEND_TOP_N = 10', 'INDEX_DIVIDEND_RSI_THRESHOLD = 20.0',
        'rsi < INDEX_DIVIDEND_RSI_THRESHOLD', 'def _index_dividend_boards',
        'def build_index_dividend_watch', 'build_index_dividend_watch(pro, trade_date, data)',
        '_weekly_rsi6_evidence', 'dynamicWeeklyFresh', 'indexBoards', 'memberSnapshots',
        'daily_basic(trade_date=effective', 'dv_ttm')),
    'rankingAndSnapshotCoverage': all(x in source for x in (
        'validDividendCount', 'missingDividendCount', 'nonPositiveDividendCount',
        'dividendCoveragePct', 'membershipAsOf', 'snapshot_dates != {effective}',
        'eligible[:INDEX_DIVIDEND_TOP_N]')),
    'oldProductionEntryRemoved': 'build_dividend_watch' not in main_calls
                                 and 'build_index_dividend_watch' in main_calls
                                 and 'def build_dividend_watch' in source,
    'oldFunctionsProtected': regression['oldFunctionsChanged'] == [],
    'frontendSharedIndexBoards': all(x in frontend for x in (
        'indexBoards', 'dividendDefenseText', 'index-dividend-defensive',
        '高股息防御 · 逐指数独立榜', '20整不触发', '其他宽基触发不打开本榜',
        '每榜最多10只', 'membershipAsOf', 'validDividendCount')),
    'legacyFrontendRemoved': all(x not in frontend for x in (
        '全A股息率TTM Top20', 'rsi6Top20', 'rsi6-dividend-top20')),
    'noProductionOrWorkflowActions': not regression['productionDataRegenerated']
                                     and not joint['productionDataRegenerated']
                                     and not build['productionDataRegenerated']
                                     and not build['developmentServerStarted']
                                     and not preflight['workflowModified'] and not preflight['scheduleModified'],
}
result = {
    'task': 116, 'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
    'checks': checks, 'allPassed': all(checks.values()), 'releaseReady': all(checks.values()),
    'task116': {'allPassed': regression['allPassed'], 'checksPassed': regression['checksPassed'],
                'checksTotal': regression['checksTotal'], 'pitOnly': regression['pitOnly'],
                'oldFunctionsChanged': regression['oldFunctionsChanged']},
    'jointRegression': {'complete': joint['complete'], 'allPassed': joint['allPassed'],
                        'passed': joint['passed'], 'executed': joint['executed'], 'total': joint['total'],
                        'superseded': joint['superseded']},
    'build': {'success': build['success'], 'returncode': build['returncode'],
              'modulesTransformed': build['modulesTransformed'], 'warning': build['warning'],
              'assets': build['assets']},
    'sourceSha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in CORE},
    'productionFundDataSha256': regression['productionFundDataSha256'],
    'manualDispatch': False, 'productionDataRegenerated': False, 'workflowModified': False,
    'scheduleModified': False, 'developmentServerStarted': False,
    'testsReexecutedByThisVerification': False,
}
(ROOT / 'zz_task116_machine_verification.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'allPassed': result['allPassed'], 'releaseReady': result['releaseReady'],
                  'checks': checks}, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['allPassed'] else 1)
