# -*- coding: utf-8 -*-
"""真实远端缓存覆盖审计：不合成缺失成员或估值，不用fixture冒充真实恢复。"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
from oversold_concept_members import OVERSOLD_CONCEPT_SOURCES, is_real_a_share_code

cache_path = ROOT / 'zz_history_sample_remote_vcp_cache.json'
cache_raw = cache_path.read_bytes()
cache = json.loads(cache_raw.decode('utf-8'))
module = json.loads((ROOT / 'zz_history_sample_online_module.json').read_text(encoding='utf-8'))
preflight = json.loads((ROOT / 'zz_history_sample_live_preflight.json').read_text(encoding='utf-8'))
identity = json.loads((ROOT / 'zz_history_sample_real_identity.json').read_text(encoding='utf-8'))
identity_errors = {x['name']: x.get('error') for x in identity['items'] if x.get('error')}
rows = (cache.get('sectorValuationHistory') or {}).get('rows') or {}
report = []
for concept in cache.get('concepts') or []:
    name = concept.get('name')
    if name not in OVERSOLD_CONCEPT_SOURCES:
        continue
    old_code = concept.get('code')
    old_members = (cache.get('ths_members') or {}).get(old_code) or []
    current = next(x for x in module.get('concepts') or [] if x.get('name') == name)
    source = OVERSOLD_CONCEPT_SOURCES[name]
    report.append({
        'name': name, 'oldCode': old_code, 'oldMemberCount': len(old_members),
        'oldRealAShareCount': sum(is_real_a_share_code(x) for x in old_members),
        'oldNonAShareExamples': [x for x in old_members if not is_real_a_share_code(x)][:8],
        'newIndexName': source['indexName'], 'newCode': source['code'], 'queryCode': source['queryCode'],
        'newFullMemberCount': None, 'newSnapshotCount': None, 'newPeCount': None, 'newPbCount': None,
        'newPeCoverage': None, 'newPbCoverage': None, 'newPeHistorySamples': None,
        'newPbHistorySamples': None, 'newPeHistoryPct': None, 'newPbHistoryPct': None,
        'newLeaders': [], 'oldSnapshotCount': current.get('snapshotCount'),
        'oldHistoryKeys': sum(f'concept:{old_code}' in values for values in rows.values()),
        'oldHistoryNonZeroSnapshots': sum((values.get(f'concept:{old_code}') or {}).get('snapshotCount', 0) > 0
                                         for values in rows.values()),
        'newMembershipSource': None, 'newMembershipAsOf': None,
        'identityRetrievalError20261123': identity_errors.get(name),
        'status': 'pending_real_members_and_valuation_history',
    })
assert len(report) == 11
assert all(x['oldSnapshotCount'] == 0 and x['oldHistoryKeys'] == 120
           and x['oldHistoryNonZeroSnapshots'] == 0 and x['oldRealAShareCount'] == 0 for x in report)
result = {
    'task': 'history-sample', 'effective': '20261120',
    'sourceCacheSha256': hashlib.sha256(cache_raw).hexdigest(),
    'sourceCacheTradeDate': cache.get('trade_date'),
    'sourceProductionFundDataSha256': preflight['onlineFundDataSha256'],
    'sourceModule': {'snapshotDate': module.get('snapshotDate'), 'valuationStatus': module.get('valuationStatus'),
                     'counts': module.get('counts')},
    'items': report,
    'realCurrentValuationVerified': False,
    'realHistoryCoverageVerified': False,
    'fullMembershipVerified': False,
    'allElevenRecovered': False,
    'coverageEvaluationComplete': False,
    'blockers': [
        '本地无TUSHARE_TOKEN，未调用或声称调用Tushare。',
        'Wind analytics指定20261120全A横截面请求返回没找到数据，未获得个股估值。',
        'Gildata指定20261120全A查询只返回市场聚合统计，未返回逐股PE_TTM/PB/总市值。',
        '同花顺公开页实际抓取第6页及随后请求跳/account/login；前5页不冒充完整成员。',
        '旧海外组120个历史键snapshotCount全为0，不复制到新A股代码。',
    ],
    'thresholdsPreserved': {'minMetricCount': 5, 'minMetricCoverage': .6, 'minHistorySamplesIncludingCurrent': 24},
    'nextNormalNightlyRequired': True,
    'productionDataRegenerated': False,
    'manualDispatch': False,
    'note': '本报告是未完成的真实覆盖审计。只有真实成员、有效日估值和历史横截面齐全后才能把null改为实测值并判定恢复。',
}
(ROOT / 'zz_history_sample_real_coverage.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'groups': len(report), 'allElevenRecovered': result['allElevenRecovered'],
                  'realCurrentValuationVerified': result['realCurrentValuationVerified'],
                  'realHistoryCoverageVerified': result['realHistoryCoverageVerified'],
                  'blockers': result['blockers']}, ensure_ascii=False, indent=2))
