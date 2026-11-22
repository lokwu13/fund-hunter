# -*- coding: utf-8 -*-
"""任务115：独立低量窄幅VCP入口、严格边界、PIT证据、历史与统一展示。"""
import ast
import copy
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import update_data as ud
import pattern_history as ph

PRODUCTION = ('public/fund_data.json', 'src/data/fund_data.json')
production_before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in PRODUCTION}
checks = []


def check(name, condition, evidence=None):
    checks.append({'name': name, 'passed': bool(condition), 'evidence': evidence})


def business_dates(count, end=dt.date(2026, 10, 30)):
    dates = []
    day = end
    while len(dates) < count:
        if day.weekday() < 5:
            dates.append(day)
        day -= dt.timedelta(days=1)
    return list(reversed(dates))


def make_bars(count=240, constant_volume=False):
    dates = business_dates(count)
    closes = [50.0] * (count - 90) + [100.0] * 89 + [100.05]
    bars = []
    for i, (day, close) in enumerate(zip(dates, closes)):
        volume = 1000.0 if constant_volume else 100000.0 - i * 50.0
        bars.append((day.strftime('%Y%m%d'), round(close + 0.1, 4),
                     round(close - 0.1, 4), close, volume))
    # 未突破基线：末日最高恰好接近参考高但未破；收盘仍严格高于MA50。
    bars[-1] = (bars[-1][0], 100.1, 99.95, 100.05, bars[-1][4])
    return bars


def view(candidate):
    if not candidate:
        return None
    structure = candidate.get('vcpStructure') or {}
    return {
        'formed': candidate.get('formed'), 'structureFormed': candidate.get('structureFormed'),
        'displayEligible': candidate.get('displayEligible'),
        'entryId': candidate.get('vcpEntryId'), 'structurePath': candidate.get('structurePath'),
        'startDate': structure.get('startDate'), 'endDate': structure.get('endDate'),
        'tradingDays': structure.get('tradingDays'), 'amplitudePct': structure.get('amplitudePct'),
        'belowVol20Days': structure.get('belowVol20Days'),
        'belowVol20RatioPct': structure.get('belowVol20RatioPct'),
        'vol20ValidDays': structure.get('vol20ValidDays'),
        'vol20InsufficientDays': structure.get('vol20InsufficientDays'),
        'dailyTrend': candidate.get('dailyTrend'), 'gestation': candidate.get('vcpGestation'),
        'rejectReasons': candidate.get('rejectReasons'),
    }


base = make_bars()
qualified = ud._vcp_low_vol_tight_window(base, 31)
check('31日独立入口五门全部通过且证据完整', qualified['formed'] and qualified['structureFormed']
      and qualified['displayEligible'] and qualified['vcpEntryId'] == 'low_vol_tight'
      and qualified['structurePath'] == 'low_vol_tight'
      and qualified['vcpStructure']['tradingDays'] == 31
      and qualified['vcpStructure']['belowVol20RatioPct'] == 100.0
      and qualified['vcpStructure']['amplitudePct'] < 8
      and qualified['dailyTrend']['pass'] and qualified['vcpGestation']['pass'], view(qualified))
short = ud._vcp_low_vol_tight_window(base, 30)
check('30日不通过且明确至少31日', not short['formed'] and not short['structureFormed']
      and short['vcpStructure']['tradingDays'] == 30
      and any('至少31日' in x and '30日不通过' in x for x in short['vcpStructure']['rejectReasons']), view(short))

exact8_bars = copy.deepcopy(base)
slightly_below_bars = copy.deepcopy(base)
for i in range(len(base) - 31, len(base)):
    exact8_bars[i] = (exact8_bars[i][0], 108.0, 100.0, exact8_bars[i][3], exact8_bars[i][4])
    slightly_below_bars[i] = (slightly_below_bars[i][0], 107.99, 100.0,
                              slightly_below_bars[i][3], slightly_below_bars[i][4])
exact8 = ud._vcp_low_vol_tight_window(exact8_bars, 31)
below8 = ud._vcp_low_vol_tight_window(slightly_below_bars, 31)
check('振幅8.00%恰好不通过且沿用high-low除以low', not exact8['structureFormed']
      and exact8['vcpStructure']['amplitudePct'] == 8.0
      and exact8['vcpStructure']['intervalHigh'] == 108.0
      and exact8['vcpStructure']['intervalLow'] == 100.0
      and exact8['vcpStructure']['amplitudeBasis'] == '(interval_max_high-interval_min_low)/interval_min_low*100',
      view(exact8))
check('振幅7.99%略低于8%通过结构振幅门', below8['formed']
      and below8['vcpStructure']['amplitudePct'] == 7.99, view(below8))


def controlled_flags(bars, low_count):
    flags = []
    start = len(bars) - 40
    for i, bar in enumerate(bars):
        below = i >= start and i - start < low_count
        flags.append({'date': bar[0], 'volume': bar[4], 'samples': 20, 'sufficient': True,
                      'ma20': bar[4] + (1.0 if below else -1.0), 'belowVol20': below})
    return flags


with patch.object(ud, '_vcp_pit_vol20_flags', return_value=controlled_flags(base, 36)):
    ratio90 = ud._vcp_low_vol_tight_window(base, 40)
with patch.object(ud, '_vcp_pit_vol20_flags', return_value=controlled_flags(base, 37)):
    ratio925 = ud._vcp_low_vol_tight_window(base, 40)
check('低于VOL20恰好90%不通过', not ratio90['structureFormed']
      and ratio90['vcpStructure']['belowVol20Days'] == 36
      and ratio90['vcpStructure']['belowVol20RatioPct'] == 90.0
      and any('恰好90%不通过' in x for x in ratio90['vcpStructure']['rejectReasons']), view(ratio90))
check('低于VOL20占比92.5%略高即通过量能门', ratio925['formed']
      and ratio925['vcpStructure']['belowVol20Days'] == 37
      and ratio925['vcpStructure']['belowVol20RatioPct'] == 92.5, view(ratio925))

insufficient = ud._vcp_low_vol_tight_window(make_bars(31), 31)
check('VOL20不足20根不得计作缩量且留在区间分母', not insufficient['structureFormed']
      and insufficient['vcpStructure']['vol20ValidDays'] == 12
      and insufficient['vcpStructure']['vol20InsufficientDays'] == 19
      and insufficient['vcpStructure']['belowVol20Days'] == 12
      and insufficient['vcpStructure']['belowVol20RatioPct'] < 90
      and insufficient['vcpStructure']['insufficientNotCountedAsBelow'], view(insufficient))
vol_flags = ud._vcp_pit_vol20_flags(make_bars(25))
equal_vol_flags = ud._vcp_pit_vol20_flags(make_bars(25, constant_volume=True))
check('VOL20含当日PIT计算且等于均线不算低于', not vol_flags[18]['sufficient']
      and vol_flags[19]['sufficient'] and vol_flags[19]['belowVol20']
      and vol_flags[19]['ma20'] > vol_flags[19]['volume']
      and not equal_vol_flags[19]['belowVol20']
      and equal_vol_flags[19]['ma20'] == equal_vol_flags[19]['volume'],
      {'declining': vol_flags[18:20], 'equal': equal_vol_flags[19]})


def flat_bars(count):
    dates = business_dates(count)
    return [(d.strftime('%Y%m%d'), 100.1, 99.9, 100.0, 100000.0 - i * 50.0)
            for i, d in enumerate(dates)]


trend_equal = ud._vcp_low_vol_tight_window(flat_bars(200), 31)
trend_short = ud._vcp_low_vol_tight_window(flat_bars(199), 31)
check('均线等于不通过新入口正式资格', trend_equal['structureFormed'] and not trend_equal['formed']
      and not trend_equal['dailyTrendPass'] and trend_equal['dailyTrend']['close']
      == trend_equal['dailyTrend']['ma50'] == trend_equal['dailyTrend']['ma150']
      == trend_equal['dailyTrend']['ma200'], view(trend_equal))
check('任务113样本不足门在新入口不可绕过', trend_short['structureFormed'] and not trend_short['formed']
      and trend_short['dailyTrend']['samples'] == 199
      and trend_short['dailyTrend']['bullishStatus'] == 'insufficient_samples', view(trend_short))

premature_bars = copy.deepcopy(base)
i = len(base) - 30
premature_bars[i] = (premature_bars[i][0], 105.0, 99.9, 100.0, premature_bars[i][4])
premature = ud._vcp_low_vol_tight_window(premature_bars, 31)
check('孕育期提前新高拒绝但保留结构证据', premature['structureFormed'] and not premature['formed']
      and premature['vcpGestation']['status'] == 'premature_new_high'
      and premature['vcpGestation']['prematureNewHighs'][0]['date'] == base[i][0], view(premature))
final_bars = copy.deepcopy(base)
final_bars[-1] = (final_bars[-1][0], 101.2, 99.95, 101.0, final_bars[-1][4])
final = ud._vcp_low_vol_tight_window(final_bars, 31)
check('最后正常突破不被误杀且枢轴不取突破日自身高点', final['formed']
      and final['pivot'] == 100.1 and final['vcpGestation']['finalBreakout']
      and final['vcpGestation']['finalBreakout']['close'] == 101.0
      and not final['vcpGestation']['prematureNewHighs'], view(final))

# 新入口不得暗中调用传统摆动、近期量或右侧质量门。
with patch.object(ud, '_vcp_swing_highs', side_effect=AssertionError('不得调用摆动')), \
     patch.object(ud, '_vcp_recent_volume_quality', side_effect=AssertionError('不得调用近期量门')), \
     patch.object(ud, '_vcp_right_side_quality', side_effect=AssertionError('不得调用右侧质量门')):
    independent = ud._vcp_low_vol_tight_window(base, 31)
check('新入口不要求三次收缩规律摆动或额外质量门', independent['formed']
      and independent['vcpStructure']['traditionalContractionsRequired'] is False
      and independent['vcpStructure']['regularSwingRequired'] is False, view(independent))

# 同一历史前缀附加极端未来数据，历史PIT flags与候选逐字节一致。
future = []
day = dt.datetime.strptime(base[-1][0], '%Y%m%d').date()
while len(future) < 11:
    day += dt.timedelta(days=1)
    if day.weekday() < 5:
        idx = len(future)
        future.append((day.strftime('%Y%m%d'), 500.0 + idx, 0.1, 400.0 + idx, 99999999.0 + idx))
full = base + future
prefix_candidate = ud._vcp_low_vol_tight_window(base, 31)
replayed_prefix = ud._vcp_low_vol_tight_window(full[:len(base)], 31)
check('PIT无未来函数且附加未来数据不改历史候选', prefix_candidate == replayed_prefix
      and ud._vcp_pit_vol20_flags(base) == ud._vcp_pit_vol20_flags(full)[:len(base)]
      and prefix_candidate['vcpStructure']['pitOnly'], view(replayed_prefix))

# 正式登记→首个突破→age 9/10→历史标签；字段全链透传。
history = ph.empty_history()
formal = ph.candidate_from_formal('VCP收缩型', qualified)
assert formal, json.dumps(view(qualified), ensure_ascii=False, indent=2)
registered = ph.register_gestation(history, 'TEST115.SH', '任务115样本', formal,
                                   qualified['endDate'], origin_formal=True)
breakout_day = future[0]
breakout_bar = (breakout_day[0], 100.2, 99.9, 100.15, breakout_day[4])
life_bars = [breakout_bar] + [(x[0], 100.1, 99.9, 100.0, 1000.0) for x in future[1:]]
active0 = ph.advance_stock(history, 'TEST115.SH', '任务115样本', base + life_bars[:1])
active0_candidate = ph.active_candidate(active0, base + life_bars[:1])
check('新入口历史事件登记及首个突破字段完整', registered and active0
      and active0['breakoutDate'] == breakout_bar[0]
      and active0['vcpEntryId'] == 'low_vol_tight'
      and active0['vcpStructure']['tradingDays'] == 31
      and active0_candidate['vcpStructure'] == active0['vcpStructure']
      and active0_candidate['breakoutRemainingDays'] == 10, active0)
active9 = ph.advance_stock(history, 'TEST115.SH', '任务115样本', base + life_bars[:10])
expired10 = ph.advance_stock(history, 'TEST115.SH', '任务115样本', base + life_bars[:11])
lifecycle10 = ph.trading_day_lifecycle([b[0] for b in base + life_bars[:11]], breakout_bar[0])
check('突破后age9保留且第10个交易日退出', active9 and expired10 is None
      and lifecycle10['breakoutAge'] == 10 and lifecycle10['exitDate'] == life_bars[10][0]
      and ph.active_candidate(active0, base + life_bars[:11]) is None, lifecycle10)
current_item = {'code': 'TEST115.SH', 'patternEpisode': active0,
                'buyPoint': {'breakoutDate': breakout_bar[0]}}
ph.attach_history([current_item], history, breakout_bar[0])
again_item = {'code': 'TEST115.SH', 'patternEpisode': None, 'buyPoint': {}}
ph.attach_history([again_item], history, life_bars[10][0])
check('首次不冒充历史且再次入选显示入口及完整历史证据', current_item['patternHistory'] == []
      and len(again_item['patternHistory']) == 1
      and again_item['patternHistory'][0]['vcpEntryLabel'] == '低量窄幅独立VCP'
      and again_item['patternHistory'][0]['vcpStructure']['belowVol20RatioPct'] == 100.0
      and again_item['patternHistoryCoverage']['fullMarketComplete'] is False, again_item)

# 总览漏斗字段与三轨共用行对象。
funnel_item = {
    'code': 'TEST115.SH', 'name': '任务115样本', 'sector': '电力', 'pattern': 'VCP收缩型',
    'inPool': True, 'star': False, 'entryTier': 'qualified', 'defects': [],
    'buyPoint': {'pivot': qualified['pivot'], 'distanceToPivotPct': qualified['distPct']},
    'patternEpisode': None, 'patternHistory': again_item['patternHistory'],
    'patternHistoryCoverage': again_item['patternHistoryCoverage'],
    'vcpEntryId': 'low_vol_tight', 'vcpEntryLabel': '低量窄幅独立VCP',
    'vcpStructure': qualified['vcpStructure'],
    'vcpDailyTrend': qualified['dailyTrend'], 'dailyTrendPass': True,
    'vcpGestation': qualified['vcpGestation'], 'gestationPass': True,
}
funnel_data = {'longWindow': {'window': 'half'}, 'vcpStocks': {'items': [funnel_item]}}
ud.build_funnel(funnel_data)
funnel_row = next(s for s in funnel_data['funnel']['steps'] if s['key'] == 'vcp')['rows'][0]
check('共振精选储备漏斗共用新入口证据字段', funnel_row['track'] == 'reserve'
      and funnel_row['vcpEntryId'] == 'low_vol_tight'
      and funnel_row['vcpStructure'] == qualified['vcpStructure']
      and funnel_row['vcpDailyTrend'] == qualified['dailyTrend']
      and funnel_row['vcpGestation'] == qualified['vcpGestation']
      and funnel_row['patternHistory'] == again_item['patternHistory'], funnel_row)

# 原函数AST逐字不变，防止新入口改写旧形态。
baseline_source = (ROOT / 'zz_update_data_task115_baseline.py').read_text(encoding='utf-8')
current_source = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
baseline_tree = ast.parse(baseline_source)
current_tree = ast.parse(current_source)
baseline_nodes = {n.name: n for n in baseline_tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
current_nodes = {n.name: n for n in current_tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
unchanged_functions = (
    '_vcp_level_strict', '_vcp_fixed_base', '_platform_vcp_attribute', '_vcp_daily_trend_gate',
    '_vcp_gestation_new_high_gate', '_cup_handle_strict', '_cup_weekly_trend',
    '_platform_price_pattern', '_bottom_weekly_price_pattern',
)
changed_old = [name for name in unchanged_functions
               if ast.get_source_segment(baseline_source, baseline_nodes[name])
               != ast.get_source_segment(current_source, current_nodes[name])]
check('strict fixed 周线杯柄平台底部原函数未改', not changed_old, {'changed': changed_old})
check('生产扫描保留旧入口并在其后补入独立入口', all(x in current_source for x in (
    "('fixed_base', fixed_lv), ('platform_attribute', platform_vcp)",
    "('low_vol_tight', low_vol_tight_lv)", 'elif raw is None and f_c3:',
    'elif raw is None and l_c3:', 'low_vol_tight_lv if main_lv is low_vol_tight_lv else None')))

ui = {p: (ROOT / p).read_text(encoding='utf-8') for p in (
    'src/sections/patternEvidence.ts', 'src/sections/PatternHistoryLabel.tsx',
    'src/sections/ECIPanel.tsx', 'src/sections/WeeklySummary.tsx', 'src/hooks/useFundData.ts')}
all_ui = ''.join(ui.values())
check('总览工具共振精选储备统一可见新入口完整证据', all(x in all_ui for x in (
    '低量窄幅独立VCP', 'low_vol_tight', 'vcpLowVolTightText(it.vcpStructure)',
    'vcpLowVolTightText(r.vcpStructure)', 'vcpDailyTrendText(r.vcpDailyTrend)',
    'vcpGestationText(r.vcpGestation)', 'VCP·低量窄幅', 'record.vcpEntryLabel')))
check('前端严格边界文案与缺证据旧快照门完整', all(x in all_ui for x in (
    '8.00%不通过', '恰好90%不通过', '不足20日样本不得当作缩量',
    '无需传统三次收缩或规律摆动', "item.vcpStructure?.pass === true")))
check('生产两份fund_data测试前后SHA不变', production_before == {
    p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in PRODUCTION}, production_before)

failed = [c['name'] for c in checks if not c['passed']]
summary = {
    'task': 115, 'allPassed': not failed, 'checksPassed': len(checks) - len(failed),
    'checksTotal': len(checks), 'failed': failed,
    'productionFundDataSha256': production_before, 'pitOnly': True,
    'manualDispatch': False, 'productionDataRegenerated': False,
    'entryId': 'low_vol_tight', 'oldFunctionsChanged': changed_old,
}
report = {
    'summary': summary, 'checks': checks,
    'productionSha256': hashlib.sha256(current_source.encode('utf-8')).hexdigest(),
    'historySha256': hashlib.sha256((ROOT / 'scripts/pattern_history.py').read_bytes()).hexdigest(),
    'qualifiedExample': view(qualified), 'finalBreakoutExample': view(final),
}
(ROOT / 'zz_regress115_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(ROOT / 'zz_regress115_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if failed:
    print('失败检查:', json.dumps(failed, ensure_ascii=False, indent=2))
raise SystemExit(1 if failed else 0)
