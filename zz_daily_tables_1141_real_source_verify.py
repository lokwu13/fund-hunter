# -*- coding: utf-8 -*-
"""任务1141：真实 hk_hold + 单股 SDW 干跑；隔离缓存，不改生产数据、不 dispatch。"""
import copy
import hashlib
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import mock

import tushare as ts

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import update_data as u
import update_tushare as existing_tushare_config

DATA = ['public/fund_data.json', 'src/data/fund_data.json']
before = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in DATA}

# 仅使用项目已有的 Tushare 配置，不输出凭据。
ts.set_token(existing_tushare_config.TUSHARE_TOKEN)
pro = ts.pro_api()
with mock.patch.object(u, 'API_DELAY', 0.2):
    hk_date, hk_df = u._fetch_hk_hold_latest(pro, '20261123')
    weekend_df = pro.hk_hold(trade_date='20261121')
calendar = pro.trade_cal(exchange='SSE', start_date='20261120', end_date='20261123')
expected_iso = f'{hk_date[:4]}-{hk_date[4:6]}-{hk_date[6:]}'
south_top = hk_df.dropna(subset=['ratio']).sort_values('ratio', ascending=False).iloc[0]
tencent_day = hk_df.loc[hk_df['ts_code'] == '00700.HK'].iloc[0]
tencent_weekend = weekend_df.loc[weekend_df['ts_code'] == '00700.HK'].iloc[0]
hk_report = {
    'requestedDate': '20261123', 'actualAvailableDate': hk_date,
    'rows': int(len(hk_df)), 'sourceTradeDates': sorted(hk_df['trade_date'].astype(str).unique().tolist()),
    'top': {'code': south_top['ts_code'], 'name': south_top['name'], 'ratio': float(south_top['ratio'])},
    'calendar': calendar.to_dict('records'),
    'weekendDuplicate': {'date': '20261121', 'rows': int(len(weekend_df)),
                         'sameTencentRatio': float(tencent_day['ratio']) == float(tencent_weekend['ratio']),
                         'normalizedAsOf': hk_date},
}
assert hk_date == '20261120' and len(hk_df) > 0
assert hk_report['weekendDuplicate']['sameTencentRatio']

# 新右榜更新器真实干跑：只查腾讯一只，缓存位于临时目录。
with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
    isolated_cache = str(Path(tmp) / 'ccass_history.json')
    data = {'dataSources': {}}
    with mock.patch.object(u, 'CCASS_STOCKS', [('00700', '腾讯控股')]), \
         mock.patch.object(u, 'CCASS_CACHE_PATH', isolated_cache), \
         mock.patch.object(u, 'CCASS_REQ_GAP', 4.0):
        ccass_date = u.fetch_foreign_concentration(pro, '20261123', data, preferred_date=hk_date)
    assert ccass_date == expected_iso
    assert len(data['foreign_concentration_top10']) == 1
    ccass_row = data['foreign_concentration_top10'][0]
    ccass_meta = data['dataSources']['foreign_concentration_top10']
    assert ccass_row['code'] == '00700.HK' and ccass_row['ratio'].endswith('%')
    assert ccass_meta['lastUpdate'] == expected_iso and ccass_meta['freq'] == u.CONCENTRATION_FREQ
    cached = json.loads(Path(isolated_cache).read_text(encoding='utf-8'))
    raw = cached['concentrationSnapshots'][expected_iso]['00700']
    assert raw['totalIssued'] > 0 and raw['foreign'] >= 0
    expected_ratio = f"{raw['foreign'] / raw['totalIssued'] * 100:.2f}%"
    assert ccass_row['ratio'] == expected_ratio

    # 同一更新器断源：不得清空或改写最近完整观测。
    last_good_rows = copy.deepcopy(data['foreign_concentration_top10'])
    with mock.patch.object(u, 'CCASS_STOCKS', [('00700', '腾讯控股')]), \
         mock.patch.object(u, 'CCASS_CACHE_PATH', str(Path(tmp) / 'unavailable.json')), \
         mock.patch.object(u, '_ccass_get_form', return_value=None):
        failed = u.fetch_foreign_concentration(pro, '20261123', data, preferred_date='20261124')
    assert failed is None
    assert data['foreign_concentration_top10'] == last_good_rows
    assert data['dataSources']['foreign_concentration_top10']['lastUpdate'] == expected_iso
    assert f'沿用 {expected_iso}' in data['dataSources']['foreign_concentration_top10']['note']

ccass_report = {
    'dryRunUniverse': ['00700 腾讯控股'], 'actualAvailableDate': ccass_date,
    'foreignShares': raw['foreign'], 'issuedShares': raw['totalIssued'],
    'participants': raw['nPart'], 'calculatedRatio': ccass_row['ratio'],
    'formula': 'foreign / totalIssued * 100', 'institutionLabel': ccass_row['institution'],
    'source': ccass_meta['source'], 'frequency': ccass_meta['freq'],
    'monthlyNamespaceUsed': False, 'dailyNamespace': 'concentrationSnapshots',
}
fallback_report = {
    'simulatedFailure': 'SDW form unavailable', 'rowsUnchanged': True,
    'asOfUnchanged': expected_iso, 'notice': data['dataSources']['foreign_concentration_top10']['note'],
}
after = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in DATA}
assert before == after
result = {
    'task': 'daily-tables-1141-real-source', 'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
    'hkHold': hk_report, 'ccass': ccass_report, 'failureFallback': fallback_report,
    'productionFundDataSha256Before': before, 'productionFundDataSha256After': after,
    'productionDataUnchanged': True, 'productionDataRegenerated': False,
    'isolatedCache': True, 'fullNightlyDispatched': False, 'allPassed': True,
    'frequencyConclusion': {
        'southbound': '每个交易日 nightly 检查 hk_hold 最新可用记录；源按交易日披露，可能延迟，不是保证每日当天值。',
        'foreign': '每个交易日 nightly 检查20只蓝筹池的完整 CCASS/SDW 快照；非全市场，托管行口径，断源保留 last-good。',
    },
}
(ROOT / 'zz_daily_tables_1141_real_source_verify.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
