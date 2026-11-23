# -*- coding: utf-8 -*-
"""任务116：逐指数严格RSI6<20、成分隔离正股息率Top10；FakePro+临时缓存，零生产写入。"""
import ast
import copy
import hashlib
import importlib.util
import inspect
import json
import tempfile
from pathlib import Path

import pandas as pd
import update_data as ud

ROOT = Path(__file__).resolve().parent
AS_OF = '20261030'
CODES = [c for c, _ in ud.OBSERVATION_INDICES]
NAMES = dict(ud.OBSERVATION_INDICES)
DATA_FILES = ['public/fund_data.json', 'src/data/fund_data.json']
ud.API_DELAY = 0
checks = {}
data_sha_before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in DATA_FILES}


def check(name, condition, evidence=None):
    checks[name] = {'pass': bool(condition), 'evidence': evidence}


def observation(rsis, fresh=True, as_of=AS_OF):
    return {'tradeDate': AS_OF, 'items': [
        {'indexCode': code, 'indexName': NAMES[code],
         'dynamicWeeklyRsi6': rsis.get(code), 'dynamicWeeklyRsiDate': as_of,
         'dynamicWeeklyFresh': fresh, 'rsiPass': rsis.get(code) is not None and rsis[code] <= 20,
         'qualified': rsis.get(code) is not None and rsis[code] <= 20}
        for code in CODES]}


def fixture():
    members, names, records = {}, {}, {}
    snapshots = {}
    for i, index in enumerate(CODES):
        rows = []
        for j in range(15):
            code = f'{i + 1}{j:05d}.SZ'
            rows.append(code)
            names[code] = f'{NAMES[index]}成分{j}'
            dv = 30.0 - j if j < 12 else float('inf') if j == 12 else 0.0 if j == 13 else -2.0
            records[code] = {'tradeDate': AS_OF, 'dvTtm': dv}
        members[index] = rows
        snapshots[index] = '20261023'
    records['999999.SZ'] = {'tradeDate': AS_OF, 'dvTtm': 999.0}
    names['999999.SZ'] = '非本指数高息股'
    cache = {'updated': AS_OF, 'members': members, 'names': names,
             'memberSnapshots': snapshots, 'source': '受控index_weight'}
    return cache, records


CACHE, RECORDS = fixture()
check('六宽基完整且含中证500', CODES == ['000016.SH', '000300.SH', '000510.SH', '000905.SH', '000688.SH', '399673.SZ']
      and ud.DIVIDEND_POOL_INDICES == CODES and ud.INDEX_DIVIDEND_TOP_N == 10, CODES)

# 每个指数逐一单独触发：其它五榜即使有高息记录也必须为空。
for active in CODES:
    rsis = {code: 19.99 if code == active else 12.0 for code in CODES}
    # 其它指数更低也不能替active之外的指数开门；先构造单触发。
    rsis = {code: 19.99 if code == active else 25.0 for code in CODES}
    boards = ud._index_dividend_boards(observation(rsis), CACHE, RECORDS, AS_OF)
    opened = [x for x in boards if x['open']]
    target = next(x for x in boards if x['indexCode'] == active)
    check(f'逐指数独立触发且成分隔离:{active}', len(opened) == 1 and opened[0]['indexCode'] == active
          and target['count'] == 10 and len(target['items']) == 10
          and all(x['code'] in CACHE['members'][active] for x in target['items'])
          and all(x['count'] == 0 and x['items'] == [] and x['status'] == 'not_requested'
                  for x in boards if x['indexCode'] != active)
          and all(x['code'] != '999999.SZ' for x in target['items']), opened[0])

boundary = ud._index_dividend_boards(observation({c: 20.0 for c in CODES}), CACHE, RECORDS, AS_OF)
check('RSI6等于20整六榜均不触发', all(not x['open'] and not x['visible'] and x['count'] == 0 and not x['items']
                                      and x['rsi20Excluded'] for x in boundary), boundary)
window_at_20 = ud._broad_observation_decision(observation({c: 20.0 for c in CODES})['items'], [], AS_OF)
check('0步窗口原20整可触发未被误改', window_at_20['active'] and window_at_20['qualifiedCount'] == 6,
      window_at_20['qualifiedCount'])

for label, obs in (
        ('行情不新鲜', observation({c: 18.0 for c in CODES}, fresh=False)),
        ('RSI日期陈旧', observation({c: 18.0 for c in CODES}, as_of='20261029')),
        ('RSI缺失', observation({c: None for c in CODES}))):
    boards = ud._index_dividend_boards(obs, CACHE, RECORDS, AS_OF)
    check(f'{label}不得伪装新触发', all(not x['open'] and not x['items'] for x in boards), boards)

boards = ud._index_dividend_boards(observation({CODES[0]: 19.0}), CACHE, RECORDS, AS_OF)
first = boards[0]
check('股息率原始值严格降序前10且代码破并列', first['count'] == 10
      and [x['dvTtm'] for x in first['items']] == sorted([x['dvTtm'] for x in first['items']], reverse=True)
      and [x['code'] for x in first['items']] == CACHE['members'][CODES[0]][:10]
      and [x['rank'] for x in first['items']] == list(range(1, 11)), first['items'])
check('缺失无穷零零负股息率均不混入且覆盖如实', first['coverage']['memberCount'] == 15
      and first['coverage']['validDividendCount'] == 12 and first['coverage']['missingDividendCount'] == 1
      and first['coverage']['nonPositiveDividendCount'] == 2 and first['coverage']['snapshotMatchedCount'] == 14
      and first['coverage']['dividendCoveragePct'] == 80.0
      and all(x['dvTtm'] > 0 for x in first['items'])
      and all(x['code'] not in CACHE['members'][CODES[0]][12:] for x in first['items']), first['coverage'])
check('成分与股息来源asOf和缺失处理完整', first['asOf'] == AS_OF and first['snapshotDate'] == AS_OF
      and first['coverage']['membershipAsOf'] == '20261023'
      and 'index_weight' in first['coverage']['membershipSource']
      and 'daily_basic.dv_ttm' in first['coverage']['dividendSource']
      and '不补0' in first['coverage']['missingPolicy'] and '不虚构' in first['coverage']['missingPolicy'], first)

small_cache = copy.deepcopy(CACHE)
small_cache['members'][CODES[0]] = CACHE['members'][CODES[0]][:3]
small = ud._index_dividend_boards(observation({CODES[0]: 19.0}), small_cache, RECORDS, AS_OF)[0]
check('不足10只显示实际数量不凑数', small['count'] == 3 and len(small['items']) == 3
      and any('实际3只，不凑数' in x for x in small['reasons']), small)

raw_cache = {'updated': AS_OF, 'members': {CODES[0]: ['000002.SZ', '000001.SZ']},
             'names': {'000001.SZ': 'A', '000002.SZ': 'B'}, 'memberSnapshots': {}}
raw_records = {'000001.SZ': {'tradeDate': AS_OF, 'dvTtm': 8.00003},
               '000002.SZ': {'tradeDate': AS_OF, 'dvTtm': 8.00004}}
raw_board = ud._index_dividend_boards(observation({CODES[0]: 19.0}), raw_cache, raw_records, AS_OF)[0]
check('排序使用原始dv而非显示四舍五入值', [x['code'] for x in raw_board['items']] == ['000002.SZ', '000001.SZ']
      and raw_board['items'][0]['dvTtm'] == raw_board['items'][1]['dvTtm'] == 8.0, raw_board['items'])

locked = ud._index_dividend_boards(observation({CODES[0]: 19.0, CODES[1]: 18.0}), CACHE, RECORDS,
                                   AS_OF, 'stale', '旧日期20261029')
check('快照陈旧只锁触发榜且清旧不影响未触发榜', all(x['status'] == 'stale' and x['rankingLocked']
      and not x['items'] for x in locked[:2]) and all(x['status'] == 'not_requested' for x in locked[2:]), locked[:2])


class FakePro:
    def __init__(self, rows, member_fail=False, daily_fail=False):
        self.rows, self.member_fail, self.daily_fail = rows, member_fail, daily_fail
        self.index_calls, self.daily_calls, self.basic_calls = [], [], []

    def index_weight(self, **kwargs):
        self.index_calls.append(kwargs)
        if self.member_fail:
            raise RuntimeError('受控成分失败')
        index = kwargs['index_code']
        return pd.DataFrame([{'trade_date': '20261023', 'con_code': code} for code in CACHE['members'][index]])

    def stock_basic(self, **kwargs):
        self.basic_calls.append(kwargs)
        return pd.DataFrame([{'ts_code': code, 'name': name} for code, name in CACHE['names'].items()])

    def daily_basic(self, **kwargs):
        self.daily_calls.append(kwargs)
        if self.daily_fail:
            raise RuntimeError('受控股息快照失败')
        return pd.DataFrame(self.rows)


def live_rows(date=AS_OF):
    return [{'ts_code': code, 'trade_date': date, 'dv_ttm': record['dvTtm']}
            for code, record in RECORDS.items()]


def production_data(rsis=None):
    return {'sectorFlows': {'trade_date': '2026-10-30'},
            'broadObservation': observation(rsis or {CODES[0]: 19.0}),
            'longWindow': {'window': 'closed', 'windowType': 'standard'},
            'dividendWatch': {'visible': True, 'groups': [{'name': '旧概念组'}],
                              'rsi6Top20': {'visible': True, 'items': [{'code': 'OLD'}]},
                              'items': [{'code': 'OLD'}]}}


with tempfile.TemporaryDirectory() as tmp:
    old_path = ud.DIVIDEND_MEMBERS_PATH
    ud.DIVIDEND_MEMBERS_PATH = str(Path(tmp) / 'members.json')
    try:
        data = production_data()
        before_window = copy.deepcopy(data['longWindow'])
        pro = FakePro(live_rows())
        ud.build_index_dividend_watch(pro, AS_OF, data)
        block = data['dividendWatch']
        opened = [x for x in block['indexBoards'] if x['open']]
        check('生产入口只请求一次同批股息快照并读六指数成分', len(pro.daily_calls) == 1
              and pro.daily_calls[0] == {'trade_date': AS_OF, 'fields': 'ts_code,trade_date,dv_ttm'}
              and len(pro.index_calls) == 6 and len(pro.basic_calls) == 1, pro.daily_calls)
        check('生产入口独立开门不依赖0步窗且清旧结构', block['visible'] and block['triggeredCount'] == 1
              and block['count'] == 10 and len(opened) == 1 and opened[0]['count'] == 10
              and data['longWindow'] == before_window and 'groups' not in block and 'rsi6Top20' not in block
              and all(x['code'] != 'OLD' for x in block['items']), block['reasons'])
        check('生产成分快照日期真实落证据', opened[0]['coverage']['membershipAsOf'] == '20261023'
              and all(x['coverage']['membershipAsOf'] == '20261023' for x in block['indexBoards']),
              opened[0]['coverage'])
        summary = ud._index_dividend_summary(data)
        check('总览摘要逐指数含RSI日期实际数量和严格边界', '逐指数高股息防御' in summary
              and '严格RSI6<20' in summary and NAMES[CODES[0]] in summary and AS_OF in summary
              and '实际10只' in summary and 'Top20' not in summary, summary)

        inactive = production_data({c: 20.0 for c in CODES})
        inactive_pro = FakePro(live_rows())
        ud.build_index_dividend_watch(inactive_pro, AS_OF, inactive)
        check('无指数触发时成分和股息均零请求且旧榜清空', not inactive['dividendWatch']['visible']
              and inactive['dividendWatch']['count'] == 0 and inactive['dividendWatch']['items'] == []
              and inactive_pro.index_calls == [] and inactive_pro.daily_calls == [] and inactive_pro.basic_calls == [],
              inactive['dividendWatch']['reasons'])

        stale = production_data({CODES[0]: 19.0, CODES[1]: 18.0})
        ud.build_index_dividend_watch(FakePro(live_rows('20261029')), AS_OF, stale)
        stale_open = [x for x in stale['dividendWatch']['indexBoards'] if x['open']]
        check('生产陈旧快照两触发榜分别锁空', len(stale_open) == 2
              and all(x['status'] == 'stale' and x['count'] == 0 and x['items'] == [] for x in stale_open)
              and all('20261029' in (x['snapshotError'] or '') for x in stale_open), stale_open)

        failed = production_data({CODES[0]: 19.0})
        ud.build_index_dividend_watch(FakePro(live_rows(), daily_fail=True), AS_OF, failed)
        failed_open = next(x for x in failed['dividendWatch']['indexBoards'] if x['open'])
        check('股息API失败锁空而非沿用旧榜', failed_open['status'] == 'missing' and failed_open['rankingLocked']
              and failed_open['items'] == [] and '受控股息快照失败' in failed_open['snapshotError'], failed_open)

        empty = production_data({CODES[0]: 19.0})
        ud.build_index_dividend_watch(FakePro([]), AS_OF, empty)
        empty_open = next(x for x in empty['dividendWatch']['indexBoards'] if x['open'])
        check('空股息快照锁空', empty_open['status'] == 'missing' and empty_open['items'] == []
              and 'daily_basic为空' in empty_open['snapshotError'], empty_open)
    finally:
        ud.DIVIDEND_MEMBERS_PATH = old_path

# 复用既有动态Wilder RSI6算法并验证未来数据不参与当前证据。
dates = pd.date_range(end='2026-10-23', periods=30, freq='W-FRI').strftime('%Y%m%d').tolist()
closes = [100.0]
for _ in range(28):
    closes.append(closes[-1] * 0.96)
closes.append(closes[-1] * 0.95)
rows = [[d, c, c, c, 1000.0] for d, c in zip(dates, closes)]
rows.append([AS_OF, closes[-1] * 0.95, closes[-1] * 0.95, closes[-1] * 0.95, 1000.0])
pit = ud._weekly_rsi6_evidence(rows, AS_OF)
future = ud._weekly_rsi6_evidence(rows + [['20261102', 1.0, 1.0, 1.0, 1000.0],
                                           ['20270101', 10000.0, 10000.0, 10000.0, 1000.0]], AS_OF)
check('沿用同一Wilder周RSI6函数且asOf新鲜', pit['dynamicWeeklyFresh'] and pit['dynamicWeeklyRsiDate'] == AS_OF
      and pit['dynamicWeeklyRsi6'] < 20 and ud._weekly_rsi6_evidence.__name__ == '_weekly_rsi6_evidence', pit)
check('PIT未来行情不改变当前RSI证据', pit == future, {'current': pit, 'withFuture': future})

production = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
tree = ast.parse(production)
main_fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == 'main')
main_calls = {x.func.id for x in ast.walk(main_fn) if isinstance(x, ast.Call) and isinstance(x.func, ast.Name)}
check('生产main移除旧分组和全A Top20调用只接新榜', 'build_index_dividend_watch' in main_calls
      and 'build_dividend_watch' not in main_calls and 'build_rsi6_dividend_top20' not in main_calls,
      sorted(x for x in main_calls if 'dividend' in x))
check('超跌估值与0步窗口生产调用仍保留', 'build_oversold_value_directions' in main_calls
      and 'build_broad_observation' in main_calls and 'build_long_window' in main_calls,
      sorted(x for x in main_calls if x in ('build_oversold_value_directions', 'build_broad_observation', 'build_long_window')))

spec = importlib.util.spec_from_file_location('update_data_task116_baseline', ROOT / 'zz_update_data_task116_baseline.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
protected = ('_extreme_rebound_decision', '_broad_observation_decision', 'build_long_window',
             'build_oversold_value_directions', '_dividend_group_catalyst', 'build_dividend_watch',
             'build_rsi6_dividend_top20')
changed = [name for name in protected if inspect.getsource(getattr(old, name)) != inspect.getsource(getattr(ud, name))]
# 本任务明确修复build_oversold_value_directions的海外概念成分与历史补键；其余旧函数仍逐字保护。
intentional_changed = {'build_oversold_value_directions'}
check('0步窗口其他超跌低估值和旧函数未误改', set(changed) == intentional_changed,
      {'intentionalChanged': sorted(intentional_changed), 'actualChanged': changed})

ui = ''.join((ROOT / p).read_text(encoding='utf-8') for p in (
    'src/hooks/useFundData.ts', 'src/sections/WeeklySummary.tsx',
    'src/sections/funnelConclusions.ts', 'src/sections/SectorHeatmap.tsx'))
check('前端逐指数统一入口覆盖来源边界和无附加门', all(x in ui for x in (
    'indexBoards', 'index-dividend-defensive', 'dividendDefenseText', '20整不触发',
    'board.coverage.membershipAsOf', 'board.coverage.missingDividendCount',
    'board.coverage.nonPositiveDividendCount', 'board.asOf', 'board.items.map',
    '无形态、价格位置、估值历史分位、阶段缩量、均线、市值或资金流门')), 'UI contract')
check('旧全A混排Top20及行业概念高股息UI彻底移除', not any(x in ui for x in (
    'rsi6Top20', 'dividendTop20Text', 'rsi6-dividend-top20', '全A股息率TTM Top20',
    'catalystGroupCount', 'dividendGroups', 'shrinkEvidence.ratio')), 'legacy removed')

data_sha_after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in DATA_FILES}
check('两份生产fund_data字节未变', data_sha_before == data_sha_after, data_sha_after)
report = {'task': 116, 'asOf': AS_OF, 'checks': checks,
          'testIsolation': 'FakePro + TemporaryDirectory；无真实API、无生产fund_data写入',
          'superseded': {'107': '全A Top20由任务116逐指数Top10明确替代'},
          'productionFundDataSha256': data_sha_after, 'oldFunctionsChanged': changed}
(ROOT / 'zz_regress116_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {'task': 116, 'allPassed': all(x['pass'] for x in checks.values()),
           'checksPassed': sum(x['pass'] for x in checks.values()), 'checksTotal': len(checks),
           'failed': [k for k, v in checks.items() if not v['pass']],
           'productionFundDataSha256': data_sha_after, 'pitOnly': True,
           'manualDispatch': False, 'productionDataRegenerated': False, 'oldFunctionsChanged': changed}
(ROOT / 'zz_regress116_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if summary['failed']:
    raise AssertionError(summary['failed'])
