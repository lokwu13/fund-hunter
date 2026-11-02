# -*- coding: utf-8 -*-
"""任务108：当周动态RSI6与自身历史估值；FakePro+临时缓存，零真实API/生产数据写入。"""
import copy
import hashlib
import json
import tempfile
from pathlib import Path

import pandas as pd
import update_data as ud
from rsi6_oversold import weekly_rsi6_evidence
from sector_valuation_history import (group_valuation_snapshot, history_valuation_position,
                                      month_end_sample_dates, MIN_HISTORY_SAMPLES)

ROOT = Path(__file__).resolve().parent
AS_OF = '20261030'
EXPECTED_CODES = ['000016.SH', '000300.SH', '000510.SH', '000905.SH', '000688.SH', '399673.SZ']
ud.API_DELAY = 0
checks = {}
DATA_FILES = ['public/fund_data.json', 'src/data/fund_data.json']
data_sha_before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in DATA_FILES}


def check(name, condition, evidence=None):
    checks[name] = {'pass': bool(condition), 'evidence': evidence}


def weekly_rows(final_gain=0.30, unfinished_gain=0.0, include_current=True):
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


zone_rows = weekly_rows(final_gain=-0.05)
cross_rows = weekly_rows(final_gain=0.30)
zone = ud._weekly_rsi6_evidence(zone_rows, AS_OF)
check('当周动态RSI6进入20以下即通过且日期新鲜', zone['rsiPass'] and zone['inOversoldZone']
      and zone['dynamicWeeklyFresh'] and zone['dynamicWeeklyRsi6'] <= 20
      and zone['dynamicWeeklyRsiDate'] == AS_OF and zone['dailyDate'] == AS_OF
      and '周内会变化' in zone['rsiReason'], zone)

boundary_rows = weekly_rows()
boundary = weekly_rsi6_evidence(boundary_rows, AS_OF, lambda values, period: [20.0] * len(values))
check('RSI6等于20边界通过', boundary['dynamicWeeklyRsi6'] == 20 and boundary['rsiPass']
      and boundary['inOversoldZone'], boundary)

cross = ud._weekly_rsi6_evidence(cross_rows, AS_OF)
check('完成周上穿但当周动态大于20不开', cross['weeklyCross20'] and cross['weeklyRsi6'] > 20
      and cross['dynamicWeeklyRsi6'] > 20 and not cross['rsiPass'] and not cross['inOversoldZone']
      and cross['dynamicWatch'], cross)
stale = ud._weekly_rsi6_evidence(weekly_rows(final_gain=-0.05, include_current=False), AS_OF)
check('陈旧当周动态行情不开', not stale['dynamicWeeklyFresh'] and not stale['rsiPass'], stale)
empty = ud._weekly_rsi6_evidence([], AS_OF)
check('空行情不开且披露原因', not empty['rsiPass'] and empty['dynamicWeeklyRsi6'] is None
      and bool(empty['rsiReason']), empty)

check('六宽基完整且399300与000300不重复', [c for c, _ in ud.OBSERVATION_INDICES] == EXPECTED_CODES
      and '399300' not in str(ud.OBSERVATION_INDICES)
      and [c for c, _ in ud.OBSERVATION_INDICES].count('000300.SH') == 1, ud.OBSERVATION_INDICES)


def observation_for(active_code=None, valuations=None):
    cache = {code: (zone_rows if code == active_code else cross_rows) for code in EXPECTED_CODES}
    weekly = ud._broad_weekly_rsi(AS_OF, cache)
    return ud._broad_observation_decision(weekly, valuations or [], AS_OF)


for code in EXPECTED_CODES:
    obs = observation_for(code)
    ext = ud._extreme_rebound_decision(obs, AS_OF, trading_days=[AS_OF])
    check(f'六宽基任一单独触发:{code}', obs['active'] and obs['requiredCount'] == 1
          and obs['qualifiedIndices'] == [dict(ud.OBSERVATION_INDICES)[code]] and ext['active']
          and ext['triggerDetails'][0]['indexCode'] == code
          and ext['triggerDetails'][0]['dynamicWeeklyRsi6'] <= 20
          and ext['maxDays'] is None and ext['remainingDays'] == 1, ext)

high_valuation = [{'indexCode': c, 'indexName': n, 'pePct10y': 99, 'pbPct10y': 99,
                   'valuationLow': False} for c, n in ud.OBSERVATION_INDICES]
high_obs = observation_for('000300.SH', high_valuation)
check('高估值不否决且沪深300只触发一次', high_obs['active'] and high_obs['qualifiedCount'] == 1
      and high_obs['qualifiedIndices'] == ['沪深300'], high_obs)


def long_data(obs, sell=False, top=False, previous=None):
    return {
        'bondData': {'marginTrading': {'temp': '🔴冷', 'verdict': '冷温边界'},
                     'stats': {'1m_change': {'y10': 25}}},
        'broadVcp': {'items': []}, 'sectorFlows': {'trade_date': '2026-10-30'},
        'broadObservation': obs,
        'broadOsc': {'trade_date': '2026-10-30',
                     'items': ([{'indexName': '上证50', 'state': '顶部风险'}] if top else []),
                     'sellAlerts': ['上证50'] if sell else [], 'buyWindows': [],
                     'reboundWatch': [], 'extremeEvidence': []},
        'longWindow': previous or {},
    }


active_obs = observation_for('000510.SH')
for label, kwargs in (('旧估值数量门', {}), ('强硬减仓', {'sell': True}), ('顶部风险', {'top': True})):
    data = long_data(active_obs, **kwargs)
    ud.build_long_window(data)
    lw = data['longWindow']
    check(f'{label}不得阻止动态RSI6强制open', lw['window'] == 'open' and lw['standardWindow'] == 'closed'
          and lw['windowType'] == 'extreme_rebound' and lw['extremeRebound']['active']
          and not lw['extremeRebound']['blockedBy'], lw)

none_obs = observation_for()
previous_active = {'window': 'open', 'windowType': 'extreme_rebound', 'startedDate': '2026-10-29',
                   'remainingDays': 4, 'extremeRebound': {'active': True, 'startedDate': '2026-10-29'}}
closed = long_data(none_obs, previous=previous_active)
ud.build_long_window(closed)
check('全部离开20以下区域立即回standard且旧active不续命', closed['longWindow']['window'] == 'closed'
      and closed['longWindow']['standardWindow'] == 'closed'
      and closed['longWindow']['windowType'] == 'standard'
      and not closed['longWindow']['extremeRebound']['active']
      and closed['longWindow']['remainingDays'] == 0
      and closed['longWindow']['extremeRebound']['maxDays'] is None, closed['longWindow'])
check('普通standardWindow字段与任务103 VCP输入保留', closed['longWindow']['standardWindow'] == 'closed'
      and 'broadStates' in closed['longWindow'] and closed['broadVcp'] == {'items': []}, closed['longWindow'])


# 真实中位数、独立PE/PB历史分位与24样本边界。
def snapshot(date, pe=10.0, pb=2.0, members=None):
    members = members or [f'600{i:03d}.SH' for i in range(10)]
    records = {}
    for i, code in enumerate(members):
        if i < 8:
            records[code] = {'peTtm': pe, 'pb': pb}
        elif i == 8:
            records[code] = {'peTtm': -3.0, 'pb': pb}
    return dict(group_valuation_snapshot(members, records), tradeDate=date)


current = snapshot(AS_OF)
check('正PE/PB分别取中位数且亏损PE披露不进中位数', current['peTtmMedian'] == 10
      and current['pbMedian'] == 2 and current['lossPeCount'] == 1
      and current['peCount'] == 8 and current['pbCount'] == 9
      and current['peCoverage'] == 0.8 and current['pbCoverage'] == 0.9, current)
history = [snapshot(f'2024{i:02d}28', pe=5 if i <= 11 else 15, pb=1 if i <= 5 else 3)
           for i in range(1, 24)]
position = history_valuation_position(current, history)
check('24样本含当前点且PE/PB独立分位复算', position['peHistorySamples'] == 24
      and position['pbHistorySamples'] == 24 and position['peHistoryPct'] == 50
      and position['pbHistoryPct'] == 25 and position['compositeHistoryPct'] == 37.5
      and position['valuationRankBasis'] == 'dual' and position['rankEligible'], position)
check('23样本边界不制造分位', not history_valuation_position(current, history[:-1])['rankEligible']
      and history_valuation_position(current, history[:-1])['historyStatus'] == 'insufficient'
      and history_valuation_position(current, history[:-1])['peHistorySamples'] == 23,
      history_valuation_position(current, history[:-1]))
single_current = dict(current, pbMedian=None, pbCount=0, pbCoverage=0.0)
single = history_valuation_position(single_current, history)
check('单指标有效可排并明确标记', single['valuationRankBasis'] == 'single'
      and single['rankEligible'] and single['compositeHistoryPct'] == single['peHistoryPct']
      and single['pbHistoryPct'] is None and '单一指标' in single['historyReason'], single)
missing = history_valuation_position(group_valuation_snapshot(current and [f'600{i:03d}.SH' for i in range(10)], {}), history)
check('当前快照缺失与覆盖不足区分', missing['historyStatus'] == 'snapshot_missing'
      and not missing['rankEligible'] and missing['compositeHistoryPct'] is None, missing)
coverage = history_valuation_position(dict(current, peCount=4, peCoverage=0.4,
                                          pbCount=4, pbCoverage=0.4), history)
check('有效数量或覆盖率不足不排', coverage['historyStatus'] == 'coverage_insufficient'
      and not coverage['rankEligible'], coverage)
sorted_groups = sorted([dict(position, code='DUAL'), dict(single, code='SINGLE'),
                        dict(missing, code='MISSING', compositeHistoryPct=None)],
                       key=lambda g: (g['compositeHistoryPct'] is None,
                                      g['compositeHistoryPct'] if g['compositeHistoryPct'] is not None else 999,
                                      g['code']))
check('双单缺失统一低高排序且缺失置后', [g['code'] for g in sorted_groups] == ['DUAL', 'SINGLE', 'MISSING'],
      [(g['code'], g['compositeHistoryPct']) for g in sorted_groups])

cal_dates = pd.bdate_range('2026-01-05', '2026-03-31').strftime('%Y%m%d').tolist()
month_ends = month_end_sample_dates(cal_dates, '20260415')
check('月末只取真实最后交易日且不含当前未完结月', month_ends == ['20260130', '20260227', '20260331'], month_ends)


class HistoryPro:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on
        self.cal_calls = []
        self.daily_calls = []

    def trade_cal(self, **kwargs):
        self.cal_calls.append(kwargs)
        return pd.DataFrame({'cal_date': cal_dates})

    def daily_basic(self, **kwargs):
        date = kwargs['trade_date']
        self.daily_calls.append(kwargs)
        if date == self.fail_on:
            raise RuntimeError('受控历史采样失败')
        return pd.DataFrame([{'ts_code': f'600{i:03d}.SH', 'trade_date': date,
                              'pe_ttm': 10 + i, 'pb': 1 + i / 10} for i in range(10)])


history_spec = [{'type': 'industry', 'code': 'I1', 'name': '历史行业',
                 'members': {f'600{i:03d}.SH' for i in range(10)}}]
with tempfile.TemporaryDirectory() as tmp:
    old_path = ud.SECTOR_VALUATION_HISTORY_PATH
    ud.SECTOR_VALUATION_HISTORY_PATH = str(Path(tmp) / 'history.json')
    Path(ud.SECTOR_VALUATION_HISTORY_PATH).write_text(json.dumps({
        'stock_info': {'KEEP.SH': {'name': '原缓存保留'}}, 'unrelated': {'value': 87}
    }, ensure_ascii=False), encoding='utf-8')
    try:
        pro = HistoryPro()
        first = ud._update_sector_valuation_history(pro, '20260415', history_spec)
        check('首轮一次日历且每缺失月一次请求', len(pro.cal_calls) == 1
              and [x['trade_date'] for x in pro.daily_calls] == month_ends
              and sorted(first['rows']) == month_ends and first['lastAddedMonthEnds'] == 3,
              {'cal': pro.cal_calls, 'daily': pro.daily_calls})
        second_pro = HistoryPro()
        second = ud._update_sector_valuation_history(second_pro, '20260415', history_spec)
        check('第二轮增量零重复历史请求且保留缓存', len(second_pro.cal_calls) == 1
              and second_pro.daily_calls == [] and second['lastRequestedMonthEnds'] == 0
              and sorted(second['rows']) == month_ends, second)
        container = json.loads(Path(ud.SECTOR_VALUATION_HISTORY_PATH).read_text(encoding='utf-8'))
        check('嵌套历史缓存保留vcp_cache其它字段', container['stock_info'] == {'KEEP.SH': {'name': '原缓存保留'}}
              and container['unrelated'] == {'value': 87}
              and container[ud.SECTOR_VALUATION_HISTORY_CACHE_KEY]['rows'] == second['rows'], container)
    finally:
        ud.SECTOR_VALUATION_HISTORY_PATH = old_path

with tempfile.TemporaryDirectory() as tmp:
    old_path = ud.SECTOR_VALUATION_HISTORY_PATH
    ud.SECTOR_VALUATION_HISTORY_PATH = str(Path(tmp) / 'history.json')
    try:
        pro = HistoryPro(fail_on='20260227')
        failed = ud._update_sector_valuation_history(pro, '20260415', history_spec)
        check('历史采样失败停止本轮且已成功月份落盘', [x['trade_date'] for x in pro.daily_calls] == month_ends[:2]
              and sorted(failed['rows']) == month_ends[:1] and '停止本轮历史请求' in failed['fetchError']
              and (Path(tmp) / 'history.json').exists(), failed)
    finally:
        ud.SECTOR_VALUATION_HISTORY_PATH = old_path


# 生产板块整合：双指标/单指标/历史不足低高排序，保留真实龙头与排雷。
GROUP_SPECS = [
    {'type': 'industry', 'code': 'I1', 'name': '双指标低估'},
    {'type': 'industry', 'code': 'I2', 'name': '单指标可排'},
    {'type': 'concept', 'code': 'C1', 'name': '历史不足'},
]
members = {}
stock_info = {}
circ_mv = {}
for gi, spec in enumerate(GROUP_SPECS):
    codes = [f'600{gi}{i:02d}.SH' for i in range(10)]
    members[spec['code']] = codes
    for i, code in enumerate(codes):
        stock_info[code] = {'name': f'{spec["name"]}{i}'}
        circ_mv[code] = float(1000 - i)
GROUP_CACHE = {
    'sw_list': [{'code': 'I1', 'name': '双指标低估'}, {'code': 'I2', 'name': '单指标可排'}],
    'sw_members': {'I1': members['I1'], 'I2': members['I2']},
    'concepts': [{'code': 'C1', 'name': '历史不足'}],
    'ths_members': {'C1': members['C1']}, 'ths_index': {'历史不足': 'C1'},
    'stock_info': stock_info, 'circ_mv': circ_mv,
}


def extreme_data():
    return {'sectorFlows': {'trade_date': '2026-10-30'},
            'longWindow': {'window': 'open', 'windowType': 'extreme_rebound',
                           'extremeRebound': {'active': True}},
            'mineWatch': {'checkedCodes': [members['I1'][9]],
                          'items': [{'code': members['I1'][9], 'types': ['基本面'],
                                     'details': [{'type': '基本面', 'detail': '受控风险', 'date': AS_OF}]}]}}


class GroupPro:
    def __init__(self, stale=False):
        self.stale = stale
        self.calls = []

    def daily_basic(self, **kwargs):
        self.calls.append(kwargs)
        rows = []
        date = '20261029' if self.stale else AS_OF
        for gi, spec in enumerate(GROUP_SPECS):
            for i, code in enumerate(members[spec['code']]):
                rows.append({'ts_code': code, 'trade_date': date, 'close': 10.0,
                             'total_mv': float((i + 1) * 1000000), 'pe_ttm': -3.0 if i == 8 else 10.0,
                             'pb': 2.0})
        return pd.DataFrame(rows)


def prepared_history():
    dates = pd.date_range(end='2026-09-30', periods=23, freq='ME').strftime('%Y%m%d').tolist()
    rows = {}
    for date in dates:
        single_history = snapshot(date, pe=5, pb=2, members=members['I2'])
        if len(rows) < 13:
            single_history.update({'pbMedian': None, 'pbCount': 0, 'pbCoverage': 0.0})
        rows[date] = {
            'industry:I1': snapshot(date, pe=20, pb=4, members=members['I1']),
            'industry:I2': single_history,
        }
    return {'rows': rows, 'membershipBasis': 'current_constituents_non_pit',
            'survivorshipBias': True, 'fetchError': None}


with tempfile.TemporaryDirectory() as tmp:
    old_group = ud.DIVIDEND_GROUP_CACHE_PATH
    old_history = ud.SECTOR_VALUATION_HISTORY_PATH
    old_update = ud._update_sector_valuation_history
    ud.DIVIDEND_GROUP_CACHE_PATH = str(Path(tmp) / 'groups.json')
    ud.SECTOR_VALUATION_HISTORY_PATH = str(Path(tmp) / 'empty-history.json')
    Path(ud.DIVIDEND_GROUP_CACHE_PATH).write_text(json.dumps(GROUP_CACHE, ensure_ascii=False), encoding='utf-8')
    try:
        ud._update_sector_valuation_history = lambda pro, date, specs: prepared_history()
        valid = extreme_data()
        pro = GroupPro()
        ud.build_oversold_value_directions(pro, AS_OF, valid)
        block = valid['oversoldValueDirections']
        check('生产分组按双单缺失低高排序', [g['name'] for g in block['industries']] == ['双指标低估', '单指标可排']
              and block['industries'][0]['valuationRankBasis'] == 'dual'
              and block['industries'][1]['valuationRankBasis'] == 'single'
              and block['concepts'][0]['historyStatus'] == 'insufficient'
              and not block['concepts'][0]['rankEligible'] and block['counts']['rankedGroupCount'] == 2,
              {'industries': [(g['name'], g['compositeHistoryPct']) for g in block['industries']],
               'concept': block['concepts'][0]})
        check('历史估值不是全A横截面且保留真实前2龙头排雷', all(g['peCrossPct'] is None and g['pbCrossPct'] is None
              for g in block['industries'] + block['concepts'])
              and [x['code'] for x in block['industries'][0]['leaders']] == [members['I1'][9], members['I1'][8]]
              and block['industries'][0]['leaders'][0]['mineTypes'] == ['基本面']
              and 'current_constituents_non_pit' in block['historySampling']['membershipBasis']
              and block['historySampling']['pit'] is False and block['historySampling']['survivorshipBias'] is True
              and '非PIT' in block['note'] and '生存者偏差' in block['note'], block['industries'][0])
        check('摘要披露自身历史低高非PIT与生存者偏差', '自身历史分位低→高' in ud._oversold_value_directions_summary(valid)
              and '非横截面' in ud._oversold_value_directions_summary(valid)
              and '生存者偏差' in ud._oversold_value_directions_summary(valid),
              ud._oversold_value_directions_summary(valid))

        ud._update_sector_valuation_history = old_update
        stale_data = extreme_data()
        ud.build_oversold_value_directions(GroupPro(stale=True), AS_OF, stale_data)
        stale_block = stale_data['oversoldValueDirections']
        check('当前快照陈旧则中位数分位缺失且不历史引导', stale_block['valuationStatus'] == 'stale'
              and stale_block['coverage']['stale'] and stale_block['counts']['rankedGroupCount'] == 0
              and all(g['historyStatus'] == 'snapshot_missing' and g['peTtmMedian'] is None
                      and g['pbMedian'] is None and g['compositeHistoryPct'] is None
                      for g in stale_block['industries'] + stale_block['concepts'])
              and all('circ_mv' in g['leaderSortMethod'] for g in stale_block['industries']), stale_block)
    finally:
        ud.DIVIDEND_GROUP_CACHE_PATH = old_group
        ud.SECTOR_VALUATION_HISTORY_PATH = old_history
        ud._update_sector_valuation_history = old_update


# 估值API失败不得影响开窗或任务107 Top20。
TOP_CACHE = {
    'sw_list': [{'code': 'I1', 'name': '估值隔离行业'}],
    'sw_members': {'I1': ['600000.SH', '600001.SH']},
    'concepts': [], 'ths_members': {}, 'ths_index': {},
    'stock_info': {'600000.SH': {'name': '高息甲'}, '600001.SH': {'name': '高息乙'}},
    'stock_industry': {'600000.SH': '银行', '600001.SH': '银行'}, 'circ_mv': {},
}


class IsolationPro:
    def __init__(self):
        self.calls = []

    def daily_basic(self, **kwargs):
        self.calls.append(kwargs)
        if 'dv_ttm' in kwargs.get('fields', ''):
            return pd.DataFrame([
                {'ts_code': '600000.SH', 'trade_date': AS_OF, 'close': 10, 'total_mv': 1000000,
                 'dv_ttm': 8, 'pe_ttm': 10, 'pb': 1},
                {'ts_code': '600001.SH', 'trade_date': AS_OF, 'close': 10, 'total_mv': 900000,
                 'dv_ttm': 7, 'pe_ttm': 11, 'pb': 1.1},
            ])
        raise RuntimeError('受控板块估值失败')


with tempfile.TemporaryDirectory() as tmp:
    old_group = ud.DIVIDEND_GROUP_CACHE_PATH
    old_history = ud.SECTOR_VALUATION_HISTORY_PATH
    ud.DIVIDEND_GROUP_CACHE_PATH = str(Path(tmp) / 'top.json')
    ud.SECTOR_VALUATION_HISTORY_PATH = str(Path(tmp) / 'no-history.json')
    Path(ud.DIVIDEND_GROUP_CACHE_PATH).write_text(json.dumps(TOP_CACHE, ensure_ascii=False), encoding='utf-8')
    try:
        data = extreme_data()
        data['mineWatch'] = {'checkedCodes': [], 'items': []}
        before = copy.deepcopy(data['longWindow'])
        pro = IsolationPro()
        ud.build_rsi6_dividend_top20(pro, AS_OF, data)
        ud.build_oversold_value_directions(pro, AS_OF, data)
        check('估值API失败不影响longWindow和任务107Top20', data['longWindow'] == before
              and data['dividendWatch']['rsi6Top20']['status'] == 'ok'
              and data['dividendWatch']['rsi6Top20']['count'] == 2
              and data['oversoldValueDirections']['valuationStatus'] == 'missing'
              and '受控板块估值失败' in data['oversoldValueDirections']['valuationError'],
              {'top20': data['dividendWatch']['rsi6Top20'], 'valuation': data['oversoldValueDirections']['reasons']})
    finally:
        ud.DIVIDEND_GROUP_CACHE_PATH = old_group
        ud.SECTOR_VALUATION_HISTORY_PATH = old_history


production = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
ui = ''.join((ROOT / p).read_text(encoding='utf-8') for p in (
    'src/sections/WeeklySummary.tsx', 'src/sections/funnelConclusions.ts',
    'src/sections/SectorHeatmap.tsx', 'src/sections/ECIPanel.tsx'))
check('总览漏斗板块ECI清除旧实时文案', not any(text in ui for text in (
    '完成周RSI6收复20', '周RSI6收复20', '超跌程度排序', '周RSI6升序', '最长5日', '5日续命',
    '未完结周仅动态观察')), [text for text in ('完成周RSI6收复20', '周RSI6收复20', '最长5日') if text in ui])
check('前端统一动态区域日期周内变化和历史估值字段', '当周动态RSI6进入20以下区域' in ui
      and 'dynamicWeeklyRsiDate' in ui and '周内会变化' in ui
      and 'peHistoryPct' in ui and 'pbHistoryPct' in ui and 'compositeHistoryPct' in ui
      and 'historySampling.cachedMonthEnds' in ui and '非PIT' in ui and '生存者偏差' in ui)
check('任务107完整Top20卡片与排雷顺延保留', 'rsi6-dividend-top20' in ui
      and '明确命中排雷剔除并顺延补足' in ui and '未覆盖仅标未核验' in ui
      and 'build_rsi6_dividend_top20' in production)

# 后端第0步只输出新口径；普通VCP/高股息独立块不被删除。
funnel_data = extreme_data()
funnel_data['broadObservation'] = active_obs
funnel_data['oversoldValueDirections'] = {'visible': False}
funnel_data['dividendWatch'] = {'rsi6Top20': {'visible': False}}
funnel_data['mineWatch'] = {'checkedCodes': [], 'items': []}
ud.build_funnel(funnel_data)
step0 = next(s for s in funnel_data['funnel']['steps'] if s['n'] == 0)
check('后端漏斗第0步动态新口径', '当周动态RSI6进入20以下区域' in step0['conclusion']
      and '周内会变化' in step0['conclusion'] and step0['title'] == '当周动态RSI6≤20临时窗'
      and '完成周RSI6收复20' not in step0['conclusion'], step0)

data_sha_after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in DATA_FILES}
check('两份生产fund_data字节未变', data_sha_before == data_sha_after, data_sha_after)
out = {'task': 108, 'asOf': AS_OF, 'checks': checks, 'expectedCodes': EXPECTED_CODES,
       'testIsolation': 'TemporaryDirectory + FakePro；未调用真实API，未写正式缓存或生产数据',
       'dataSha256': data_sha_after}
(ROOT / 'zz_regress108.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {'checksPassed': sum(x['pass'] for x in checks.values()), 'checksTotal': len(checks),
           'failed': [k for k, v in checks.items() if not v['pass']], 'dataSha256': data_sha_after}
(ROOT / 'zz_regress108_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if summary['failed']:
    raise AssertionError(f'任务108检查失败: {summary["failed"]}')
