# -*- coding: utf-8 -*-
"""任务114发布前机器核验；不访问或改写生产数据。"""
import hashlib
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
JOINT_TASKS = [95, 96, 98, 99, 101, 102, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114]
CORE = [
    'scripts/update_data.py', 'scripts/pattern_history.py', 'scripts/pattern_episode_seed.json',
    'src/hooks/useFundData.ts', 'src/sections/patternEvidence.ts',
    'src/sections/PatternHistoryLabel.tsx', 'src/sections/ECIPanel.tsx', 'src/sections/WeeklySummary.tsx',
    'zz_regress114.py', 'zz_generate114_seed.py', 'zz_run_joint114.py', 'zz_build114.py',
]
r113 = json.loads((ROOT / 'zz_regress113_summary.json').read_text(encoding='utf-8'))
r114 = json.loads((ROOT / 'zz_regress114_summary.json').read_text(encoding='utf-8'))
joint = json.loads((ROOT / 'zz_joint_regress114.json').read_text(encoding='utf-8'))
build = json.loads((ROOT / 'zz_build114.json').read_text(encoding='utf-8'))
seed = json.loads((ROOT / 'zz_task114_seed_verification.json').read_text(encoding='utf-8'))
source = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
history = (ROOT / 'scripts/pattern_history.py').read_text(encoding='utf-8')
frontend = ''.join((ROOT / p).read_text(encoding='utf-8') for p in CORE if p.startswith('src/'))
production = json.loads((ROOT / 'scripts/pattern_episode_seed.json').read_text(encoding='utf-8'))
episode = production['stocks']['601985.SH']['episodes'][0]
checks = {
    'task113AllPassed': r113['allPassed'] and r113['checksPassed'] == r113['checksTotal'] == 309,
    'task114AllPassed': r114['allPassed'] and r114['checksPassed'] == r114['checksTotal'] == 34,
    'jointAllPassed': joint['complete'] and joint['allPassed'] and joint['passed'] == joint['total'] == 17,
    'jointExactTasks': [x['task'] for x in joint['results']] == JOINT_TASKS
                       and all(x['returncode'] == 0 and x['passed'] for x in joint['results']),
    'jointLogsPresent': all((ROOT / x['log']).is_file()
                            and (ROOT / x['log']).stat().st_size == x['logBytes'] for x in joint['results']),
    'buildPassed': build['success'] and build['returncode'] == 0
                   and build['matchesTask114RegressionDataSha'] and build['fundDataUnchanged'],
    'productionDataUnchangedAcrossSuites': r113['productionFundDataSha256'] == r114['productionFundDataSha256']
                                           and build['localFundDataBefore'] == build['localFundDataAfter']
                                           and all(build['localFundDataAfter'][p]['sha256']
                                                   == r114['productionFundDataSha256'][p]
                                                   for p in r114['productionFundDataSha256']),
    'gestationRuleMarkers': all(x in source for x in (
        'def _vcp_gestation_new_high_gate', 'VCP_GESTATION_REFERENCE_DAYS = 250',
        'VCP_GESTATION_MIN_REFERENCE_SAMPLES = 20', 'VCP_SIDEWAYS_DRIFT_MAX = 3.0',
        'droppedByVcpGestation', '横盘仅为优选')),
    'historyLifecycleMarkers': all(x in history for x in (
        'PATTERN_BREAKOUT_MAX_TRADING_DAYS = 10', 'def register_gestation', 'def advance_stock',
        'def attach_history', 'def candidate_from_formal')),
    'frontendSharedHistoryAndGate': frontend.count("import PatternHistoryLabel from './PatternHistoryLabel'") == 2
                                    and '历史入选记录' in frontend
                                    and 'item.vcpGestation?.pass === true && item.gestationPass === true' in frontend,
    'nuclearBreakoutAndExpiry': episode['breakoutDate'] == '20261015' and episode['pivot'] == 9.21
                                and episode['referenceHigh'] == 9.51
                                and seed['replay']['20261028']['active']
                                and seed['replay']['20261029']['lifecycle']['exitDate'] == '20261029'
                                and not seed['replay']['20261029']['active'],
    'honestOriginQualification': episode['originFormalAdmission'] is False
                                 and '不冒充当时正式入选' in episode['originQualificationNote'],
    'noProductionOrWorkflowActions': not r114['productionDataRegenerated'] and not joint['productionDataRegenerated']
                                     and not build['productionDataRegenerated'] and not build['developmentServerStarted'],
}
result = {
    'task': 114,
    'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
    'checks': checks, 'allPassed': all(checks.values()), 'releaseReady': all(checks.values()),
    'task113': r113, 'task114': r114,
    'jointRegression': {'complete': joint['complete'], 'allPassed': joint['allPassed'],
                        'passed': joint['passed'], 'total': joint['total']},
    'build': {'success': build['success'], 'returncode': build['returncode'],
              'modulesTransformed': build['modulesTransformed'], 'warning': build['warning']},
    'sourceSha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in CORE},
    'manualDispatch': False, 'productionDataRegenerated': False, 'workflowModified': False,
    'scheduleModified': False, 'developmentServerStarted': False,
}
(ROOT / 'zz_task114_machine_verification.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'allPassed': result['allPassed'], 'releaseReady': result['releaseReady'],
                  'checks': checks}, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['allPassed'] else 1)
