# -*- coding: utf-8 -*-
"""任务115发布前机器核验；只读取既有测试/构建证据，不重跑测试或生产数据。"""
import hashlib
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
JOINT_TASKS = [95, 96, 98, 99, 101, 102, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115]
CORE = [
    'scripts/update_data.py', 'scripts/pattern_history.py', 'scripts/pattern_episode_seed.json',
    'src/hooks/useFundData.ts', 'src/sections/patternEvidence.ts',
    'src/sections/PatternHistoryLabel.tsx', 'src/sections/ECIPanel.tsx', 'src/sections/WeeklySummary.tsx',
    'zz_scan101.py', 'zz_regress115.py', 'zz_run_joint115.py', 'zz_build115.py',
]
r113 = json.loads((ROOT / 'zz_regress113_summary.json').read_text(encoding='utf-8'))
r114 = json.loads((ROOT / 'zz_regress114_summary.json').read_text(encoding='utf-8'))
r115 = json.loads((ROOT / 'zz_regress115_summary.json').read_text(encoding='utf-8'))
joint = json.loads((ROOT / 'zz_joint_regress115.json').read_text(encoding='utf-8'))
build = json.loads((ROOT / 'zz_build115.json').read_text(encoding='utf-8'))
source = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
history = (ROOT / 'scripts/pattern_history.py').read_text(encoding='utf-8')
frontend = ''.join((ROOT / p).read_text(encoding='utf-8') for p in CORE if p.startswith('src/'))
checks = {
    'task113AllPassed': r113['allPassed'] and r113['checksPassed'] == r113['checksTotal'] == 309,
    'task114AllPassed': r114['allPassed'] and r114['checksPassed'] == r114['checksTotal'] == 34,
    'task115AllPassed': r115['allPassed'] and r115['checksPassed'] == r115['checksTotal'] == 23,
    'jointAllPassed': joint['complete'] and joint['allPassed'] and joint['passed'] == joint['total'] == 18,
    'jointExactTasks': [x['task'] for x in joint['results']] == JOINT_TASKS
                       and all(x['returncode'] == 0 and x['passed'] for x in joint['results']),
    'jointLogsPresent': all((ROOT / x['log']).is_file()
                            and (ROOT / x['log']).stat().st_size == x['logBytes'] for x in joint['results']),
    'buildPassed': build['success'] and build['returncode'] == 0
                   and build['matchesTask115RegressionDataSha'] and build['fundDataUnchanged']
                   and all(build['bundleMarkers'].values()) and build['viewportMetaPresent'],
    'productionDataUnchangedAcrossSuites': r113['productionFundDataSha256'] == r114['productionFundDataSha256']
                                           == r115['productionFundDataSha256']
                                           and build['localFundDataBefore'] == build['localFundDataAfter']
                                           and all(build['localFundDataAfter'][p]['sha256']
                                                   == r115['productionFundDataSha256'][p]
                                                   for p in r115['productionFundDataSha256']),
    'independentEntryMarkers': all(x in source for x in (
        "VCP_LOW_VOL_TIGHT_ENTRY_ID = 'low_vol_tight'", 'VCP_LOW_VOL_TIGHT_MIN_DAYS = 31',
        'VCP_LOW_VOL_TIGHT_AMPLITUDE_MAX = 0.08', 'VCP_LOW_VOL_TIGHT_VOL20_MIN_RATIO = 0.90',
        'def _vcp_pit_vol20_flags', 'def _vcp_low_vol_tight_window', 'def _vcp_low_vol_tight_base',
        "('low_vol_tight', low_vol_tight_lv)", 'elif raw is None and l_c3:')),
    'strictBoundaryAndNoExtraStructureGate': all(x in source for x in (
        'amplitude < VCP_LOW_VOL_TIGHT_AMPLITUDE_MAX', 'ratio > VCP_LOW_VOL_TIGHT_VOL20_MIN_RATIO',
        'len(base) > 30', "'traditionalContractionsRequired': False", "'regularSwingRequired': False",
        "'pivotBasis': 'interval_high_before_final_day'", 'bar[4] < ma20')),
    'historyEntryEvidenceLifecycle': all(x in history for x in (
        "'vcpEntryId': candidate.get('vcpEntryId')", "'vcpStructure': copy.deepcopy(candidate.get('vcpStructure'))",
        "'vcpEntryId': active.get('vcpEntryId')", 'PATTERN_BREAKOUT_MAX_TRADING_DAYS = 10')),
    'frontendSharedEvidenceAllTracks': all(x in frontend for x in (
        'vcpLowVolTightText(it.vcpStructure)', 'vcpLowVolTightText(r.vcpStructure)',
        'vcpDailyTrendText(r.vcpDailyTrend)', 'vcpGestationText(r.vcpGestation)',
        'VCP·低量窄幅', 'record.vcpEntryLabel', "item.vcpStructure?.pass === true")),
    'oldFunctionsUnchanged': r115['oldFunctionsChanged'] == [],
    'noProductionOrWorkflowActions': not r115['productionDataRegenerated'] and not joint['productionDataRegenerated']
                                     and not build['productionDataRegenerated'] and not build['developmentServerStarted'],
}
result = {
    'task': 115, 'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
    'checks': checks, 'allPassed': all(checks.values()), 'releaseReady': all(checks.values()),
    'task113': {'allPassed': r113['allPassed'], 'checksPassed': r113['checksPassed'], 'checksTotal': r113['checksTotal']},
    'task114': {'allPassed': r114['allPassed'], 'checksPassed': r114['checksPassed'], 'checksTotal': r114['checksTotal']},
    'task115': {'allPassed': r115['allPassed'], 'checksPassed': r115['checksPassed'], 'checksTotal': r115['checksTotal']},
    'jointRegression': {'complete': joint['complete'], 'allPassed': joint['allPassed'],
                        'passed': joint['passed'], 'total': joint['total']},
    'build': {'success': build['success'], 'returncode': build['returncode'],
              'modulesTransformed': build['modulesTransformed'], 'warning': build['warning'],
              'assets': build['assets']},
    'sourceSha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in CORE},
    'manualDispatch': False, 'productionDataRegenerated': False, 'workflowModified': False,
    'scheduleModified': False, 'developmentServerStarted': False,
    'testsReexecutedByThisVerification': False,
}
(ROOT / 'zz_task115_machine_verification.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'allPassed': result['allPassed'], 'releaseReady': result['releaseReady'],
                  'checks': checks}, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['allPassed'] else 1)
