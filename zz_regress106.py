# -*- coding: utf-8 -*-
"""RSI6单口径开窗与真实指数超跌榜回归；任务103 VCP函数逐字保护。"""
import importlib.util
import inspect
import json
import tempfile
from pathlib import Path

import pandas as pd
import update_data as ud

ROOT = Path(__file__).resolve().parent
AS_OF = '20261030'
EXPECTED_CODES = ['000016.SH', '000300.SH', '000510.SH', '000905.SH', '000688.SH', '399673.SZ']
ud.API_DELAY = 0
checks = {}


def check(name, condition, evidence=None):
    checks[name] = {'pass': bool(condition), 'evidence': evidence}


def weekly_rows(final_gain=0.30, unfinished_gain=0.0, include_current=True):
    """真实收 weekday 形状的受控周线序列；长跌后末周反弹，RSI值由生产Wilder函数计算。"""
    days = pd.date_range(end='2026-10-23', periods=30, freq='W-FRI').strftime('%Y%m%d').tolist()
    closes = [100.0]
    for _ in range(28):
        closes.append(closes[-1] * 0.96)
    closes.append(closes[-1] * (1 + final_gain))
    rows = [[d, round(c, 6), round(c, 6), round(c, 6), 1000.0] for d, c in zip(days, closes)]
    if include_current:
        closes.append(closes[-1] * (1 + unfinished_gain))
        rows.append([AS_OF, round(closes[-1], 6), round(closes[-1], 6), round(closes[-1], 6), 1000.0])
    return rows


cross_rows = weekly_rows()
cross = ud._weekly_rsi6_evidence(cross_rows, AS_OF)
check('RSI6从20下方向上收复20触发', cross['weeklyFresh'] and cross['previousWeeklyRsi6'] <= 20
      and cross['weeklyRsi6'] > 20 and cross['rsiPass'], cross)

no_cross_rows = weekly_rows(final_gain=-0.05)
no_cross = ud._weekly_rsi6_evidence(no_cross_rows, AS_OF)
completed_closes = [r[1] for r in no_cross_rows[:-1]]
# 用周收盘直接验证RSI14可单独低于20，但绝不触发新门。
week_closes = []
for row in no_cross_rows[:-1]:
    week_closes.append(row[1])
rsi14 = ud._rsi_series(week_closes, 14)[-1]
check('仅RSI14低于20不触发', rsi14 < 20 and not no_cross['rsiPass'], {'rsi14': rsi14, 'evidence': no_cross})
check('未上穿20不触发', no_cross['weeklyRsi6'] <= 20 and not no_cross['rsiPass'], no_cross)

unfinished = ud._weekly_rsi6_evidence(weekly_rows(final_gain=-0.05, unfinished_gain=0.50), AS_OF)
check('未完结周只动态观察不触发', not unfinished['rsiPass'] and unfinished['weeklyRsi6'] <= 20
      and unfinished['dynamicWeeklyRsi6'] > 20 and unfinished['dynamicWatch'], unfinished)
stale = ud._weekly_rsi6_evidence(weekly_rows(include_current=False), AS_OF)
check('陈旧行情不触发', not stale['weeklyFresh'] and not stale['rsiPass'], stale)
empty = ud._weekly_rsi6_evidence([], AS_OF)
check('空数据不触发且原因透明', not empty['rsiPass'] and empty['weeklyRsi6'] is None
      and bool(empty['rsiReason']), empty)

check('六宽基清单含A500且沪深300不重复', [c for c, _ in ud.OBSERVATION_INDICES] == EXPECTED_CODES
      and '399300' not in str(ud.OBSERVATION_INDICES)
      and [c for c, _ in ud.OBSERVATION_INDICES].count('000300.SH') == 1, ud.OBSERVATION_INDICES)


def observation_for(active_code):
    cache = {code: (cross_rows if code == active_code else no_cross_rows) for code in EXPECTED_CODES}
    weekly = ud._broad_weekly_rsi(AS_OF, cache)
    return ud._broad_observation_decision(weekly, [], AS_OF)


for code in EXPECTED_CODES:
    obs = observation_for(code)
    ext = ud._extreme_rebound_decision(obs, AS_OF, trading_days=[AS_OF])
    check(f'任一宽基可单独强制开窗:{code}', obs['active'] and obs['requiredCount'] == 1
          and obs['qualifiedIndices'] == [dict(ud.OBSERVATION_INDICES)[code]] and ext['active']
          and ext['triggerDetails'][0]['indexCode'] == code
          and ext['triggerDetails'][0]['previousWeeklyRsi6'] <= 20
          and ext['triggerDetails'][0]['weeklyRsi6'] > 20, ext)


def long_data(obs, sell=False, top=False):
    return {
        'bondData': {'marginTrading': {'temp': '🔴冷', 'verdict': '冷温边界'},
                     'stats': {'1m_change': {'y10': 25}}},
        'broadVcp': {'items': []}, 'sectorFlows': {'trade_date': '2026-10-30'},
        'broadObservation': obs,
        'broadOsc': {'trade_date': '2026-10-30',
                     'items': ([{'indexName': '上证50', 'state': '顶部风险'}] if top else []),
                     'sellAlerts': ['上证50'] if sell else [], 'buyWindows': [],
                     'reboundWatch': [], 'extremeEvidence': []},
    }


active_obs = observation_for('000510.SH')
for label, kwargs in (('旧估值数量门', {}), ('强硬减仓', {'sell': True}), ('顶部风险', {'top': True})):
    data = long_data(active_obs, **kwargs)
    ud.build_long_window(data)
    lw = data['longWindow']
    check(f'{label}不得阻止RSI6强制open', lw['window'] == 'open' and lw['standardWindow'] == 'closed'
          and lw['windowType'] == 'extreme_rebound' and lw['extremeRebound']['active']
          and not lw['extremeRebound']['blockedBy'], lw)

# 一只触发时即使估值全高/全部缺失也不影响；未触发时估值全低也不开门。
high_valuation = [{'indexCode': c, 'indexName': n, 'pePct10y': 99, 'pbPct10y': 99,
                   'valuationLow': False} for c, n in ud.OBSERVATION_INDICES]
one_cross = ud._broad_observation_decision(ud._broad_weekly_rsi(AS_OF, {c: (cross_rows if c == '000300.SH' else no_cross_rows) for c in EXPECTED_CODES}), high_valuation, AS_OF)
check('单只RSI6触发不要双指数或估值AND', one_cross['active'] and one_cross['qualifiedCount'] == 1, one_cross)
none_cross = ud._broad_observation_decision(ud._broad_weekly_rsi(AS_OF, {c: no_cross_rows for c in EXPECTED_CODES}), [], AS_OF)
check('未上穿且无双指数估值替代门', not none_cross['active'] and none_cross['qualifiedCount'] == 0, none_cross)

# A500真实缓存可直接复算；最后孤立点前有缺口，因此以最后密集交易日为as-of，绝不伪称该孤立点新鲜。
real_cache = json.loads((ROOT / 'scripts/cache/broad_idx_cache.json').read_text(encoding='utf-8'))
a500_rows = real_cache.get('000510.SH') or []
a500_date = a500_rows[-2][0]
a500_evidence = ud._weekly_rsi6_evidence(a500_rows, a500_date)
check('A500连续真实行情及RSI6可复算', len(a500_rows) >= 250 and a500_evidence['weeklyFresh']
      and a500_evidence['weeklyRsi6'] is not None and a500_evidence['previousWeeklyRsi6'] is not None,
      {'rows': len(a500_rows), 'start': a500_rows[0][0], 'asOf': a500_date,
       'cacheEnd': a500_rows[-1][0], 'evidence': a500_evidence})

# 行业/概念真实指数超跌排序、概念归属、双龙头和估值失败降级。
def direction_rows(final_gain):
    return [[r[0], r[1], r[4]] for r in weekly_rows(final_gain=final_gain)]


BASE_CACHE = {
    'sw_list': [{'code': 'I1', 'name': '行业一'}, {'code': 'I2', 'name': '行业二'},
                {'code': 'I3', 'name': '空数据行业'}],
    'sw_members': {'I1': ['A001.SZ', 'A002.SZ', 'A003.SZ'],
                   'I2': ['B001.SZ', 'B002.SZ', 'B003.SZ'], 'I3': ['N001.SZ']},
    'concepts': [{'code': 'C1', 'name': '真实大概念'}],
    'ths_members': {'C1': ['C001.SZ', 'C002.SZ', 'C003.SZ']},
    'ths_index': {'真实大概念': 'C1'},
    'index_daily': {'I1': direction_rows(0.05), 'I2': direction_rows(0.15),
                    'C1': direction_rows(0.25), 'I3': []},
    'stock_info': {**{f'A{i:03d}.SZ': {'name': f'行业A{i}'} for i in range(1, 4)},
                   **{f'B{i:03d}.SZ': {'name': f'行业B{i}'} for i in range(1, 4)},
                   **{f'C{i:03d}.SZ': {'name': f'概念C{i}'} for i in range(1, 4)},
                   'N001.SZ': {'name': '空数据N'}, 'OUTSIDE.SZ': {'name': '关系不标'}},
    'circ_mv': {'A001.SZ': 100, 'A002.SZ': 300, 'A003.SZ': 200,
                'B001.SZ': 100, 'B002.SZ': 300, 'B003.SZ': 200,
                'C001.SZ': 100, 'C002.SZ': 300, 'C003.SZ': 200},
}


def snapshot_row(code, mv, date=AS_OF):
    return {'ts_code': code, 'trade_date': date, 'close': 10.0,
            'total_mv': mv, 'pe_ttm': 100.0, 'pb': 10.0}


class FakePro:
    def __init__(self, fail=False, stale=False):
        self.fail = fail
        self.stale = stale
        self.calls = []

    def daily_basic(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError('受控估值API失败')
        codes = list(BASE_CACHE['stock_info'])
        return pd.DataFrame([snapshot_row(c, (i + 1) * 1000000, '20261029' if self.stale else AS_OF)
                             for i, c in enumerate(codes)])


def extreme_data():
    return {'sectorFlows': {'trade_date': '2026-10-30'},
            'longWindow': {'window': 'open', 'windowType': 'extreme_rebound',
                           'extremeRebound': {'active': True}},
            'mineWatch': {'checkedCodes': [], 'items': []}}


with tempfile.TemporaryDirectory() as tmp:
    cache_path = Path(tmp) / 'groups.json'
    cache_path.write_text(json.dumps(BASE_CACHE, ensure_ascii=False), encoding='utf-8')
    old_path = ud.DIVIDEND_GROUP_CACHE_PATH
    ud.DIVIDEND_GROUP_CACHE_PATH = str(cache_path)
    try:
        failed = extreme_data()
        ud.build_oversold_value_directions(FakePro(fail=True), AS_OF, failed)
        block = failed['oversoldValueDirections']
        check('估值API失败不阻止超跌榜', block['visible'] and block['counts']['directionCount'] == 3
              and len(block['industries']) == 2 and len(block['concepts']) == 1
              and block['valuationStatus'] == 'missing', block)
        ordered = [g['weeklyRsi6'] for g in block['industries'] + block['concepts']]
        check('行业概念按周RSI6升序透明排列', ordered == sorted(ordered)
              and all(g['previousWeeklyRsi6'] is not None and g['dailyRsi6'] is not None
                      and 'drawdown20Pct' in g and 'drawdown60Pct' in g
                      for g in block['industries'] + block['concepts']), ordered)
        check('空数据单独披露不凑数', block['counts']['rsiInsufficientGroupCount'] == 1
              and block['coverage']['insufficientGroups'][0]['name'] == '空数据行业', block['coverage'])
        concept = block['concepts'][0]
        check('概念真实归属且关系不标股票排除', concept['memberCount'] == 3
              and all(x['code'] != 'OUTSIDE.SZ' for x in concept['leaders']), concept)
        check('估值失败用披露circ_mv口径取前2', [x['code'] for x in concept['leaders']] == ['C002.SZ', 'C003.SZ']
              and all(x['totalMv'] is None and x['circMv'] is not None and x['peTtm'] is None
                      for x in concept['leaders'])
              and 'circ_mv' in concept['leaderSortMethod'], concept['leaders'])
        check('超跌摘要含RSI6排序和非反转提示', '周RSI6升序' in ud._oversold_value_directions_summary(failed)
              and '极端超卖≠立即反转' in ud._oversold_value_directions_summary(failed),
              ud._oversold_value_directions_summary(failed))

        valid = extreme_data()
        ud.build_oversold_value_directions(FakePro(), AS_OF, valid)
        valid_concept = valid['oversoldValueDirections']['concepts'][0]
        check('快照可用时保留总市值前2与估值排雷字段', [x['code'] for x in valid_concept['leaders']] == ['C003.SZ', 'C002.SZ']
              and all(x['totalMv'] is not None and x['peTtm'] == 100 and 'mineNote' in x
                      for x in valid_concept['leaders'])
              and valid['oversoldValueDirections']['valuationStatus'] == 'ok', valid_concept['leaders'])
        check('高估值不再作为方向入围门', valid['oversoldValueDirections']['counts']['directionCount'] == 3
              and all(g['peTtmMedian'] == 100 for g in valid['oversoldValueDirections']['industries']),
              valid['oversoldValueDirections']['counts'])

        stale_snap = extreme_data()
        ud.build_oversold_value_directions(FakePro(stale=True), AS_OF, stale_snap)
        check('陈旧估值快照也不清空RSI6超跌榜', stale_snap['oversoldValueDirections']['counts']['directionCount'] == 3
              and stale_snap['oversoldValueDirections']['coverage']['stale']
              and stale_snap['oversoldValueDirections']['valuationStatus'] == 'stale', stale_snap['oversoldValueDirections'])

        empty_cache = dict(BASE_CACHE)
        empty_cache['index_daily'] = {}
        cache_path.write_text(json.dumps(empty_cache, ensure_ascii=False), encoding='utf-8')
        no_data = extreme_data()
        ud.build_oversold_value_directions(FakePro(fail=True), AS_OF, no_data)
        check('方向指数空数据不伪造榜单', no_data['oversoldValueDirections']['counts']['directionCount'] == 0
              and no_data['oversoldValueDirections']['counts']['rsiInsufficientGroupCount'] == 4
              and not no_data['oversoldValueDirections']['industries']
              and not no_data['oversoldValueDirections']['concepts'], no_data['oversoldValueDirections'])
    finally:
        ud.DIVIDEND_GROUP_CACHE_PATH = old_path

# 任务103 VCP与杯柄逐字保护；完整十例/六窗口由zz_regress105.py另行强制执行。
spec = importlib.util.spec_from_file_location('update_data_task106_rsi6_baseline',
                                              ROOT / 'zz_update_data_task106_rsi6_baseline.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
for name in ('_vcp_level_strict', '_vcp_fixed_base', '_vcp_right_side_quality',
             '_cup_handle_strict', '_cup_early_breakout'):
    check(f'任务103函数逐字未改:{name}', inspect.getsource(getattr(old, name)) == inspect.getsource(getattr(ud, name)),
          'source identical')

# 前端/后端只清除极端窗旧口径，保留高股息等独立RSI14模块。
production = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
weekly_ui = (ROOT / 'src/sections/WeeklySummary.tsx').read_text(encoding='utf-8')
funnel_ui = (ROOT / 'src/sections/funnelConclusions.ts').read_text(encoding='utf-8')
heatmap_ui = (ROOT / 'src/sections/SectorHeatmap.tsx').read_text(encoding='utf-8')
types = (ROOT / 'src/hooks/useFundData.ts').read_text(encoding='utf-8')
check('前端RSI6开窗与超跌榜契约', '周RSI6' in weekly_ui and 'previousWeeklyRsi6' in weekly_ui
      and 'weeklyRsi6' in types and '周RSI6升序' in funnel_ui
      and '超跌程度' in heatmap_ui and 'rsiInsufficientGroupCount' in heatmap_ui)
check('清除极端窗旧开门描述', '至少2只才开窗' not in weekly_ui and '观察窗AND门' not in funnel_ui
      and '超低估值方向' not in funnel_ui and '超低估值行业' not in heatmap_ui
      and 'RSI14<20 AND' not in production)
check('独立高股息RSI14模块未误删', '_dividend_group_catalyst' in production
      and '近4个完成周曾周RSI14<20' in production)

out = {'rule': 'weekly_wilder_rsi6_cross20_and_oversold_directions', 'asOf': AS_OF,
       'checks': checks, 'expectedCodes': EXPECTED_CODES,
       'a500': {'rows': len(a500_rows), 'start': a500_rows[0][0], 'end': a500_date,
                'evidence': a500_evidence}}
(ROOT / 'zz_regress106.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {'checksPassed': sum(x['pass'] for x in checks.values()), 'checksTotal': len(checks),
           'failed': [k for k, v in checks.items() if not v['pass']]}
(ROOT / 'zz_regress106_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if summary['failed']:
    raise AssertionError(f'RSI6规则回归失败: {summary["failed"]}')
