# -*- coding: utf-8 -*-
"""债券栏目删减发布前只读机器核验；不重跑测试、不生成生产数据。"""
import hashlib
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
regression = json.loads((ROOT / 'zz_regress_bond_delete_summary.json').read_text(encoding='utf-8'))
build = json.loads((ROOT / 'zz_build_bond_delete.json').read_text(encoding='utf-8'))
preflight = json.loads((ROOT / 'zz_bond_delete_live_preflight.json').read_text(encoding='utf-8'))
panel = (ROOT / 'src/sections/BondsPanel.tsx').read_text(encoding='utf-8')
backend = (ROOT / 'scripts/update_data.py').read_bytes()
checks = {
    'targetedRegression19Passed': regression['allPassed'] and regression['checksPassed'] == regression['checksTotal'] == 19
                                   and not regression['failed'],
    'buildPassed': build['success'] and build['returncode'] == 0 and build['fundDataUnchanged']
                   and build['matchesRegressionDataSha'] and all(build['retainedBundleMarkers'].values())
                   and not any(build['removedBundleMarkersPresent'].values()) and build['viewportMetaPresent'],
    'targetTitlesAbsentInActivePanel': all(x not in panel for x in preflight['targetTitles']),
    'sharedModulesRetained': all(x in panel for x in (
        'const us = bd.us || null;', 'const news = bd.news || [];', '央行短期流动性工具',
        '滚动波动率（20日标准差）', '债市信号 → A+H股市一个月影响推演', 'const usCnSpread')),
    'backendUnchanged': backend == (ROOT / 'zz_bond_delete_update_data_baseline.py').read_bytes(),
    'localProductionDataUnchanged': build['localFundDataBefore'] == build['localFundDataAfter']
                                    and all(build['localFundDataAfter'][p]['sha256']
                                            == regression['productionFundDataSha256'][p]
                                            for p in regression['productionFundDataSha256']),
    'noForbiddenActions': not regression['productionDataRegenerated'] and not build['productionDataRegenerated']
                          and not build['developmentServerStarted'] and not preflight['manualDispatch']
                          and not preflight['workflowModified'] and not preflight['scheduleModified'],
}
result = {
    'task': 'bond-delete', 'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
    'checks': checks, 'allPassed': all(checks.values()), 'releaseReady': all(checks.values()),
    'regression': {'allPassed': regression['allPassed'], 'checksPassed': regression['checksPassed'],
                   'checksTotal': regression['checksTotal']},
    'build': {'success': build['success'], 'returncode': build['returncode'],
              'modulesTransformed': build['modulesTransformed'], 'warning': build['warning'],
              'assets': build['assets']},
    'sourceSha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in (
        'src/sections/BondsPanel.tsx', 'zz_regress_bond_delete.py', 'zz_build_bond_delete.py')},
    'productionFundDataSha256': regression['productionFundDataSha256'],
    'manualDispatch': False, 'productionDataRegenerated': False, 'workflowModified': False,
    'scheduleModified': False, 'developmentServerStarted': False, 'testsReexecutedByThisVerification': False,
}
(ROOT / 'zz_bond_delete_machine_verification.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['allPassed'] else 1)
