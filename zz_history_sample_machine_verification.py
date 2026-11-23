# -*- coding: utf-8 -*-
"""发布前机器核验：代码发布准备与真实数据恢复完成度分开判定。"""
import hashlib
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
regress = json.loads((ROOT / 'zz_history_sample_regress.json').read_text(encoding='utf-8'))
real = json.loads((ROOT / 'zz_history_sample_real_coverage.json').read_text(encoding='utf-8'))
joint = json.loads((ROOT / 'zz_joint_regress116.json').read_text(encoding='utf-8'))
build = json.loads((ROOT / 'zz_history_sample_build.json').read_text(encoding='utf-8'))
r116 = json.loads((ROOT / 'zz_regress116_summary.json').read_text(encoding='utf-8'))
r108 = json.loads((ROOT / 'zz_regress108_summary.json').read_text(encoding='utf-8'))
concept = json.loads((ROOT / 'zz_concept_sample_regress.json').read_text(encoding='utf-8'))
preflight = json.loads((ROOT / 'zz_history_sample_live_preflight.json').read_text(encoding='utf-8'))
source = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
member_source = (ROOT / 'scripts/oversold_concept_members.py').read_text(encoding='utf-8')
data_state = {p: {'bytes': (ROOT / p).stat().st_size,
                  'sha256': hashlib.sha256((ROOT / p).read_bytes()).hexdigest()} for p in DATA}
checks = {
    'newRegression19Passed': regress['passed'] == regress['total'] == 19 and not regress['failed'],
    'old108Regression40Passed': r108['checksPassed'] == r108['checksTotal'] == 40 and not r108['failed'],
    'latest116Regression34Passed': r116['allPassed'] and r116['checksPassed'] == r116['checksTotal'] == 34
                                   and r116['oldFunctionsChanged'] == ['build_oversold_value_directions'],
    'conceptRegression13Passed': concept['passed'] == concept['total'] == 13,
    'joint18Passed': joint['complete'] and joint['allPassed'] and joint['passed'] == joint['executed'] == joint['total'] == 18
                     and all(x['returncode'] == 0 and x['passed'] for x in joint['results']),
    'jointLogsPresent': all((ROOT / x['log']).is_file() and (ROOT / x['log']).stat().st_size == x['logBytes']
                            for x in joint['results']),
    'buildPassed': build['success'] and build['returncode'] == 0 and all(build['bundleMarkers'].values()),
    'productionDataUntouched': build['fundDataUnchanged'] and build['fundDataAfter'] == data_state
                               and all(data_state[p]['sha256'] == preflight['fundData'][p]['localSha256'] for p in DATA),
    'sourceCacheUntouched': hashlib.sha256((ROOT / 'scripts/cache/vcp_cache.json').read_bytes()).hexdigest()
                            == preflight['remoteCache']['localSha256'],
    'thresholdsPreserved': regress['thresholds'] == {'minMetricCount': 5, 'minMetricCoverage': .6,
                                                     'minHistorySamplesIncludingCurrent': 24}
                           and all(x in source for x in ('OVERSOLD_VALUE_MIN_COMMON = MIN_METRIC_COUNT',
                                                         'OVERSOLD_VALUE_MIN_COVERAGE = MIN_METRIC_COVERAGE',
                                                         'SECTOR_VALUATION_MIN_SAMPLES = MIN_HISTORY_SAMPLES')),
    'membershipAndHistoryFixPresent': all(x in source for x in (
        'ensure_oversold_concept_members', '_history_spec_needs_refresh', 'membershipFingerprint',
        'lastAddedGroupKeys', 'snapshotMissingGroupCount', 'oversoldConceptMembers')) and all(x in member_source for x in (
        '885431.TI', '885574.TI', '885736.TI', '885531.TI', '885887.TI', '885461.TI',
        '885800.TI', '886069.TI', '886078.TI', '886032.TI', '886015.TI',
        '公开分页需登录或返回非概念页', '不完整成员')),
    'realCoverageHonestlyIncomplete': len(real['items']) == 11 and not real['allElevenRecovered']
                                      and not real['realCurrentValuationVerified'] and not real['realHistoryCoverageVerified']
                                      and not real['fullMembershipVerified'] and not real['coverageEvaluationComplete']
                                      and all(x['newFullMemberCount'] is None and x['newSnapshotCount'] is None
                                              and x['newPeHistorySamples'] is None and x['newLeaders'] == []
                                              for x in real['items']),
    'oldZeroHistoryNotReused': all(x['oldHistoryKeys'] == 120 and x['oldHistoryNonZeroSnapshots'] == 0
                                   and x['oldRealAShareCount'] == 0 for x in real['items']),
    'noNightlyOrScheduleActions': not real['manualDispatch'] and not real['productionDataRegenerated']
                                  and not build['manualDispatch'] and not build['productionDataRegenerated']
                                  and not build['developmentServerStarted']
                                  and not preflight['workflowModified'] and not preflight['scheduleModified'],
}
result = {
    'task': 'history-sample', 'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
    'checks': checks, 'allPassed': all(checks.values()), 'codeReleaseReady': all(checks.values()),
    'realDataRecoveryComplete': False, 'nextNormalNightlyRequired': True,
    'realCoverageStatus': 'pending_real_members_current_snapshot_and_history',
    'productionFundDataSha256': {p: x['sha256'] for p, x in data_state.items()},
    'jointRegression': {'passed': joint['passed'], 'total': joint['total']},
    'build': {'success': build['success'], 'assets': build['assets'], 'warning': build['warning']},
    'manualDispatch': False, 'productionDataRegenerated': False, 'workflowModified': False,
    'scheduleModified': False, 'developmentServerStarted': False,
    'note': 'allPassed仅表示代码发布门禁通过，不表示11组真实历史估值已经恢复；线上旧名单须下一次正常nightly重算。',
}
(ROOT / 'zz_history_sample_machine_verification.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['allPassed'] else 1)
