# -*- coding: utf-8 -*-
"""任务104回归（任务108现行契约）：自身历史估值、真实龙头排雷与失败降级。"""
import copy
import importlib.util
import inspect
import json
import tempfile
from pathlib import Path

import pandas as pd
import update_data as ud
from sector_valuation_history import group_valuation_snapshot

ROOT = Path(__file__).resolve().parent
AS_OF = '20261030'
ud.API_DELAY = 0
checks = {}


def check(name, condition, evidence=None):
    checks[name] = {'pass': bool(condition), 'evidence': evidence}


SPECS = [{'type': 'industry', 'code': 'I1', 'name': '历史可排行业'},
         {'type': 'industry', 'code': 'I2', 'name': '历史不足行业'},
         {'type': 'concept', 'code': 'C1', 'name': '真实大概念'}]
members, stock_info, circ_mv = {}, {}, {}
for gi, spec in enumerate(SPECS):
    members[spec['code']] = [f'600{gi}{i:02d}.SH' for i in range(10)]
    for i, code in enumerate(members[spec['code']]):
        stock_info[code] = {'name': f'{spec["name"]}{i}'}
        circ_mv[code] = float(10000 - i)
CACHE = {
    'sw_list': [{'code': 'I1', 'name': '历史可排行业'}, {'code': 'I2', 'name': '历史不足行业'}],
    'sw_members': {'I1': members['I1'], 'I2': members['I2']},
    'concepts': [{'code': 'C1', 'name': '真实大概念'}],
    'ths_members': {'C1': members['C1']}, 'ths_index': {'真实大概念': 'C1'},
    'stock_info': stock_info, 'circ_mv': circ_mv,
}


class FakePro:
    def __init__(self, stale=False, fail=False):
        self.stale, self.fail, self.calls = stale, fail, []

    def daily_basic(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError('受控估值API失败')
        rows = []
        for spec in SPECS:
            for i, code in enumerate(members[spec['code']]):
                rows.append({'ts_code': code, 'trade_date': '20261029' if self.stale else AS_OF,
                             'close': 10.0, 'total_mv': float((i + 1) * 1000000),
                             'pe_ttm': None if i == 9 else -3.0 if i == 8 else 5.0 + i,
                             'pb': 0.5 + i / 10})
        return pd.DataFrame(rows)


def data():
    return {'sectorFlows': {'trade_date': '2026-10-30'},
            'longWindow': {'window': 'open', 'windowType': 'extreme_rebound',
                           'extremeRebound': {'active': True}},
            'mineWatch': {'checkedCodes': [members['I1'][8]], 'items': [
                {'code': members['I1'][8], 'types': ['基本面'],
                 'details': [{'type': '基本面', 'detail': '受控风险', 'date': AS_OF}]}]}}


def history_snapshot(date, spec, pe, pb):
    records = {}
    for i, code in enumerate(members[spec['code']]):
        if i < 8:
            records[code] = {'peTtm': pe, 'pb': pb}
        elif i == 8:
            records[code] = {'peTtm': -3.0, 'pb': pb}
    return dict(group_valuation_snapshot(members[spec['code']], records), tradeDate=date)


def history_cache():
    dates = pd.date_range(end='2026-09-30', periods=23, freq='ME').strftime('%Y%m%d').tolist()
    rows = {}
    for i, date in enumerate(dates):
        rows[date] = {'industry:I1': history_snapshot(date, SPECS[0], 20, 2)}
        if i >= 13:
            rows[date]['industry:I2'] = history_snapshot(date, SPECS[1], 20, 2)
    return {'rows': rows, 'membershipBasis': 'current_constituents_non_pit',
            'survivorshipBias': True, 'fetchError': None}


with tempfile.TemporaryDirectory() as tmp:
    old_group, old_history = ud.DIVIDEND_GROUP_CACHE_PATH, ud.SECTOR_VALUATION_HISTORY_PATH
    old_update = ud._update_sector_valuation_history
    ud.DIVIDEND_GROUP_CACHE_PATH = str(Path(tmp) / 'groups.json')
    ud.SECTOR_VALUATION_HISTORY_PATH = str(Path(tmp) / 'history.json')
    Path(ud.DIVIDEND_GROUP_CACHE_PATH).write_text(json.dumps(CACHE, ensure_ascii=False), encoding='utf-8')
    try:
        normal = data()
        normal['longWindow'] = {'window': 'open', 'windowType': 'standard', 'extremeRebound': {'active': False}}
        normal['oversoldValueDirections'] = {'visible': True, 'industries': [{'name': '旧名单'}]}
        pro = FakePro()
        ud.build_oversold_value_directions(pro, AS_OF, normal)
        check('普通窗清空旧名单且零估值请求', not normal['oversoldValueDirections']['visible']
              and normal['oversoldValueDirections']['industries'] == [] and pro.calls == [])

        ud._update_sector_valuation_history = lambda pro, date, specs: history_cache()
        active, before = data(), copy.deepcopy(data()['longWindow'])
        pro = FakePro()
        ud.build_oversold_value_directions(pro, AS_OF, active)
        block = active['oversoldValueDirections']
        check('RSI6窗一次当前快照请求且不反向改门', block['visible'] and len(pro.calls) == 1
              and pro.calls[0]['trade_date'] == AS_OF and active['longWindow'] == before, pro.calls)
        check('行业大概念全量保留不按估值过滤', block['counts']['directionCount'] == 3
              and len(block['industries']) == 2 and len(block['concepts']) == 1, block['counts'])
        first = block['industries'][0]
        check('自身历史分位低高排序且历史不足置后', first['name'] == '历史可排行业'
              and first['rankEligible'] and first['compositeHistoryPct'] == 4.2
              and block['industries'][1]['historyStatus'] == 'insufficient'
              and block['concepts'][0]['historyStatus'] == 'insufficient', block['industries'])
        check('亏损和缺失PE不进中位数且披露', first['peTtmMedian'] == 8.5
              and first['pbMedian'] == 0.95 and first['lossPeCount'] == 1
              and first['peCount'] == 8 and first['snapshotCount'] == 10
              and first['missingSnapshotCount'] == 0, first)
        check('真实总市值前2与排雷命中保留', [x['code'] for x in first['leaders']] == [members['I1'][9], members['I1'][8]]
              and first['leaders'][0]['peTtm'] is None
              and first['leaders'][1]['peTtm'] == -3 and first['leaders'][1]['mineTypes'] == ['基本面'], first['leaders'])
        check('不使用全A横截面分位', first['peCrossPct'] is None and first['pbCrossPct'] is None
              and first['peHistoryPct'] == 4.2 and first['pbHistoryPct'] == 4.2, first)
        check('现行成分非PIT与生存者偏差明示', block['historySampling']['membershipBasis'] == 'current_constituents_non_pit'
              and block['historySampling']['pit'] is False and block['historySampling']['survivorshipBias'] is True
              and '非PIT' in block['note'] and '生存者偏差' in block['note'], block['historySampling'])
        summary = ud._oversold_value_directions_summary(active)
        check('摘要为历史估值低高而非RSI排序', '自身历史分位低→高' in summary
              and '非横截面' in summary and '非操作买卖建议' in summary, summary)

        ud._update_sector_valuation_history = old_update
        stale = data()
        ud.build_oversold_value_directions(FakePro(stale=True), AS_OF, stale)
        stale_block = stale['oversoldValueDirections']
        check('陈旧快照保留方向但当前中位数分位缺失', stale_block['valuationStatus'] == 'stale'
              and stale_block['counts']['rankedGroupCount'] == 0
              and all(g['historyStatus'] == 'snapshot_missing' and g['peTtmMedian'] is None
                      for g in stale_block['industries'] + stale_block['concepts']), stale_block)
        check('失败或陈旧以circ_mv取龙头并披露非总市值', all('circ_mv' in g['leaderSortMethod']
              for g in stale_block['industries'] + stale_block['concepts'])
              and all(x['totalMv'] is None for g in stale_block['industries'] for x in g['leaders']),
              stale_block['industries'][0]['leaderSortMethod'])
        failed = data()
        ud.build_oversold_value_directions(FakePro(fail=True), AS_OF, failed)
        check('估值API失败不影响开窗也不保留旧分位', failed['longWindow'] == before
              and failed['oversoldValueDirections']['valuationStatus'] == 'missing'
              and failed['oversoldValueDirections']['counts']['rankedGroupCount'] == 0
              and '受控估值API失败' in failed['oversoldValueDirections']['valuationError'], failed['oversoldValueDirections'])
    finally:
        ud.DIVIDEND_GROUP_CACHE_PATH, ud.SECTOR_VALUATION_HISTORY_PATH = old_group, old_history
        ud._update_sector_valuation_history = old_update

spec = importlib.util.spec_from_file_location('update_data_task104_baseline_current',
                                              ROOT / 'zz_update_data_task104_remote_baseline.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
for name in ('_broad_valuation_gate', '_dividend_group_catalyst', 'build_broad_osc',
             '_cup_handle_strict', '_cup_early_breakout', '_trend_template'):
    check(f'既有函数逐字未改:{name}', inspect.getsource(getattr(old, name)) == inspect.getsource(getattr(ud, name)))

ui = ''.join((ROOT / p).read_text(encoding='utf-8') for p in (
    'src/sections/WeeklySummary.tsx', 'src/sections/funnelConclusions.ts',
    'src/sections/SectorHeatmap.tsx', 'src/hooks/useFundData.ts'))
check('前端历史估值类型和展示全链路', all(x in ui for x in ('peHistoryPct', 'pbHistoryPct',
      'compositeHistoryPct', 'historySampling.cachedMonthEnds', 'mineCovered')))
check('任务107完整榜单不被估值模块覆盖', 'rsi6-dividend-top20' in ui
      and '明确命中排雷剔除并顺延补足' in ui)

out = {'task': 104, 'updatedForTask': 108, 'asOf': AS_OF, 'checks': checks,
       'testIsolation': 'TemporaryDirectory + FakePro；未调用真实API或写正式缓存'}
(ROOT / 'zz_regress104.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {'checksPassed': sum(x['pass'] for x in checks.values()), 'checksTotal': len(checks),
           'failed': [k for k, v in checks.items() if not v['pass']]}
(ROOT / 'zz_regress104_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if summary['failed']:
    raise AssertionError(summary['failed'])
