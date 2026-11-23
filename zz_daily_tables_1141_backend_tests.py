# -*- coding: utf-8 -*-
"""任务1141：两榜更新器隔离单元/数据契约测试；不触网、不写生产数据。"""
import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import update_data as u

checks = []


def check(name, condition, detail=None):
    checks.append({'name': name, 'passed': bool(condition), 'detail': detail})
    if not condition:
        raise AssertionError(f'{name}: {detail}')


class FakePro:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def hk_hold(self, trade_date):
        self.calls.append(trade_date)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def trade_cal(self, exchange, start_date, end_date):
        return pd.DataFrame([
            {'cal_date': '20261119', 'is_open': 1}, {'cal_date': '20261120', 'is_open': 1},
            {'cal_date': '20261121', 'is_open': 0}, {'cal_date': '20261122', 'is_open': 0},
            {'cal_date': '20261123', 'is_open': 1},
        ])


def frame(date='20261120'):
    return pd.DataFrame([
        {'ts_code': '00001.HK', 'name': '甲', 'vol': 100, 'ratio': 1.25, 'trade_date': date},
        {'ts_code': '00700.HK', 'name': '乙', 'vol': 200, 'ratio': 8.75, 'trade_date': date},
        {'ts_code': '03690.HK', 'name': '丙', 'vol': 300, 'ratio': 5.00, 'trade_date': date},
    ])


# 南向：真实源日期、排序、假期回退；周末重复标签必须归一到交易日。
data = {}
pro = FakePro([pd.DataFrame(), frame('20261121')])
with mock.patch.object(u, 'API_DELAY', 0):
    result = u.fetch_southbound_concentration(pro, '20261123', data)
check('southSourceAsOf', result == '20261120', result)
check('southSorted', [x['code'] for x in data['southbound_concentration_top10']] == ['00700.HK', '03690.HK', '00001.HK'])
meta = data['dataSources']['southbound_concentration_top10']
check('southMetadata', meta['lastUpdate'] == '2026-11-20' and meta['freq'] == u.CONCENTRATION_FREQ
      and '发布滞后' in meta['note'] and '周末/假期' in meta['note'])
check('southBacktrackBounded', pro.calls == ['20261123', '20261120'], pro.calls)
check('weekendDuplicateNotRebranded', meta['lastUpdate'] == '2026-11-20')

# 南向断源：last-good 行和日期不变，明确标记本次失败。
old_rows = copy.deepcopy(data['southbound_concentration_top10'])
with mock.patch.object(u, 'API_DELAY', 0):
    failed = u.fetch_southbound_concentration(FakePro([RuntimeError('offline')]), '20261123', data)
check('southFailureReturnsNone', failed is None)
check('southLastGoodRows', data['southbound_concentration_top10'] == old_rows)
check('southLastGoodDate', data['dataSources']['southbound_concentration_top10']['lastUpdate'] == '2026-11-20')
check('southLastGoodNotice', '沿用 2026-11-20' in data['dataSources']['southbound_concentration_top10']['note'])

# SDW HTML：外资合计和已发行股本均来自真实页面结构。
html = '''<tr><td class="col-participant-id">A
<td class="col-participant-name"><div class="mobile-list-body">HSBC</div></td>
<td class="col-shareholding "><div class="mobile-list-body">5,130,452,128</div></td></tr>
<tr><td class="col-participant-id">B
<td class="col-participant-name"><div class="mobile-list-body">CHINA SECURITIES DEPOSITORY</div></td>
<td class="col-shareholding "><div class="mobile-list-body">1,095,008,914</div></td></tr>
<div class="summary-header">Total number of Issued Shares/Warrants/Units
(last updated figure)</div><div class="summary-value">9,092,644,829</div>'''
with mock.patch.object(u, '_sdw_http', return_value=html):
    parsed = u._ccass_query('00700', '2026/11/20', ('vs', 'vg'))
check('ccassForeignParsed', parsed['foreign'] == 5130452128 and parsed['south'] == 1095008914)
check('ccassIssuedSharesParsed', parsed['totalIssued'] == 9092644829)

stocks = [('00001', '甲'), ('00700', '腾讯控股')]


def row(code, foreign, issued):
    return {'foreign': foreign, 'south': 0, 'nPart': 10, 'totalIssued': issued, 'name': code}


with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
    cache_path = Path(tmp) / 'ccass.json'
    monthly = {'2026-10-30': {'00700': {'foreign': 1, 'south': 2, 'nPart': 3}}}
    cache_path.write_text(json.dumps({'snapshots': copy.deepcopy(monthly), 'note': 'monthly'}), encoding='utf-8')
    query_calls = []

    def fake_query(code5, date_dash, form):
        query_calls.append((code5, date_dash))
        return row(code5, 50 if code5 == '00001' else 25, 100)

    data = {'foreign_concentration_top10': [
        {'code': '00700.HK', 'name': '旧', 'ratio': '1.00%', 'institution': '旧', 'concept': '互联网', 'sector': '互联网'}
    ], 'dataSources': {}}
    with mock.patch.object(u, 'CCASS_STOCKS', stocks), \
         mock.patch.object(u, 'CCASS_CACHE_PATH', str(cache_path)), \
         mock.patch.object(u, 'CCASS_REQ_GAP', 0), \
         mock.patch.object(u, '_ccass_get_form', return_value=('vs', 'vg')), \
         mock.patch.object(u, '_ccass_query', side_effect=fake_query):
        result = u.fetch_foreign_concentration(None, '20261123', data, preferred_date='20261120')
    check('foreignRealAsOf', result == '2026-11-20')
    check('foreignRatioFormula', data['foreign_concentration_top10'][0]['ratio'] == '50.00%'
          and data['foreign_concentration_top10'][1]['ratio'] == '25.00%')
    check('foreignSorted', [x['code'] for x in data['foreign_concentration_top10']] == ['00001.HK', '00700.HK'])
    check('foreignInstitutionHonest', all(x['institution'] == '主流外资托管行合计'
                                          for x in data['foreign_concentration_top10']))
    check('foreignMetadata', data['dataSources']['foreign_concentration_top10']['freq'] == u.CONCENTRATION_FREQ
          and '非全市场排名' in data['dataSources']['foreign_concentration_top10']['note'])
    check('foreignConceptPreserved', data['foreign_concentration_top10'][1]['concept'] == '互联网')
    cached = json.loads(cache_path.read_text(encoding='utf-8'))
    check('dailyCacheWritten', set(cached['concentrationSnapshots']['2026-11-20']) == {'00001', '00700'})
    check('monthlyCacheUntouched', cached['snapshots'] == monthly and cached['note'] == 'monthly')

    # 完整缓存直接复用，不重复请求。
    with mock.patch.object(u, 'CCASS_STOCKS', stocks), \
         mock.patch.object(u, 'CCASS_CACHE_PATH', str(cache_path)), \
         mock.patch.object(u, '_ccass_get_form', side_effect=AssertionError('should not GET')), \
         mock.patch.object(u, '_ccass_query', side_effect=AssertionError('should not POST')):
        check('completeCacheReused', u.fetch_foreign_concentration(
            None, '20261123', data, preferred_date='20261120') == '2026-11-20')

    # 部分快照：不得覆盖完整 last-good。
    previous_rows = copy.deepcopy(data['foreign_concentration_top10'])
    cache_path.write_text(json.dumps({'snapshots': copy.deepcopy(monthly)}), encoding='utf-8')
    responses = iter([row('00001', 50, 100), None])
    with mock.patch.object(u, 'CCASS_STOCKS', stocks), \
         mock.patch.object(u, 'CCASS_CACHE_PATH', str(cache_path)), \
         mock.patch.object(u, 'CCASS_REQ_GAP', 0), \
         mock.patch.object(u, '_ccass_get_form', return_value=('vs', 'vg')), \
         mock.patch.object(u, '_ccass_query', side_effect=lambda *args: next(responses)):
        result = u.fetch_foreign_concentration(None, '20261123', data, preferred_date='20261121')
    check('partialSnapshotRejected', result is None)
    check('partialKeepsRows', data['foreign_concentration_top10'] == previous_rows)
    check('partialKeepsAsOf', data['dataSources']['foreign_concentration_top10']['lastUpdate'] == '2026-11-20')
    check('partialLastGoodNotice', '沿用 2026-11-20' in data['dataSources']['foreign_concentration_top10']['note'])
    check('partialMonthlyStillUntouched', json.loads(cache_path.read_text(encoding='utf-8'))['snapshots'] == monthly)

    # 连续失败熔断，避免断源时20只逐一长时间重试。
    cache_path.write_text(json.dumps({'snapshots': copy.deepcopy(monthly)}), encoding='utf-8')
    query_count = 0

    def always_none(*args):
        global query_count
        query_count += 1
        return None

    with mock.patch.object(u, 'CCASS_STOCKS', stocks + [('03690', '美团-W')]), \
         mock.patch.object(u, 'CCASS_CACHE_PATH', str(cache_path)), \
         mock.patch.object(u, 'CCASS_REQ_GAP', 0), \
         mock.patch.object(u, '_ccass_get_form', return_value=('vs', 'vg')), \
         mock.patch.object(u, '_ccass_query', side_effect=always_none):
        result = u.fetch_foreign_concentration(None, '20261123', data, preferred_date='20261121')
    check('consecutiveFailureCircuitBreaker', result is None and query_count == 4,
          {'requests': query_count, 'failedStocks': 3, 'firstStockFormRetry': 1})
    check('circuitBreakerKeepsLastGood', data['foreign_concentration_top10'] == previous_rows
          and data['dataSources']['foreign_concentration_top10']['lastUpdate'] == '2026-11-20')

# 从未成功接入时断源：旧手工数据保持原标识，不冒充日更。
manual = {'foreign_concentration_top10': [{'code': '00700.HK', 'ratio': '36.45%'}],
          'dataSources': {'foreign_concentration_top10': {
              'source': '港交所CCASS', 'freq': '手工季更', 'lastUpdate': '2026-07-04', 'note': '旧手工数据'}}}
manual_before = copy.deepcopy(manual)
with tempfile.TemporaryDirectory(dir=ROOT) as tmp, \
     mock.patch.object(u, 'CCASS_CACHE_PATH', str(Path(tmp) / 'empty.json')), \
     mock.patch.object(u, '_ccass_get_form', return_value=None):
    result = u.fetch_foreign_concentration(None, '20261123', manual, preferred_date='20261120')
check('initialFailureReturnsNone', result is None)
check('initialFailureDoesNotRebrandManualData', manual == manual_before)

# nightly 接入、workflow 与生产数据保护。
source = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
check('nightlySouthCalled', 'southbound_concentration_date = fetch_southbound_concentration(pro, trade_date, data)' in source)
check('nightlyForeignCalled', 'fetch_foreign_concentration(pro, trade_date, data, preferred_date=southbound_concentration_date)' in source)
workflow = (ROOT / '.github/workflows/daily-update.yml').read_bytes()
workflow_baseline = (ROOT / 'zz_daily_tables_1141_daily_update_baseline.yml').read_bytes()
check('workflowByteIdentical', workflow == workflow_baseline)
check('noScheduleChange', b"37 11 * * 1-5" in workflow and b"python scripts/update_data.py" in workflow)
preflight = json.loads((ROOT / 'zz_daily_tables_1141_live_preflight.json').read_text(encoding='utf-8'))
for path, state in preflight['fundData'].items():
    actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    check('productionUnchanged:' + path, actual == state['localSha256'], actual)

result = {
    'task': 'daily-tables-1141-backend-contract', 'checksPassed': sum(x['passed'] for x in checks),
    'checksTotal': len(checks), 'failed': [x for x in checks if not x['passed']],
    'checks': checks, 'networkUsed': False, 'productionDataRegenerated': False,
    'manualDispatch': False, 'allPassed': all(x['passed'] for x in checks),
}
(ROOT / 'zz_daily_tables_1141_backend_tests.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f"backend contract tests: {result['checksPassed']}/{result['checksTotal']} passed")
