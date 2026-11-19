# -*- coding: utf-8 -*-
"""任务113：所有VCP路径统一识别日日线趋势硬门，取消VCP一年/历史高位排除。"""
import copy
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import update_data as ud
import zz_scan101

VCP = 'VCP收缩型'
DATA_PATH = ROOT / 'zz_audit100_current_rows_full.json'
DATA_SHA256 = 'f77eb8dcfcd11c0d582ea44eec9b25b67b859fd9c1de383c4dde6cbb4fa25d45'
DATA = json.loads(DATA_PATH.read_text(encoding='utf-8'))
BEFORE = json.loads((ROOT / 'zz_task113_before103.json').read_text(encoding='utf-8'))
assert hashlib.sha256(DATA_PATH.read_bytes()).hexdigest() == DATA_SHA256
assert BEFORE['summary']['task'] == 103
CASES = [
    {'code': '002371.SZ', 'name': '北方华创', 'asOf': '20250520', 'label': 'VCP负例'},
    {'code': '000776.SZ', 'name': '广发证券', 'asOf': '20250403', 'label': 'VCP结构正例'},
    {'code': '600118.SH', 'name': '中国卫星', 'asOf': '20250402', 'label': '底部平台/整理，非VCP'},
    {'code': '002027.SZ', 'name': '分众传媒', 'asOf': '20250402', 'label': '负例'},
    {'code': '600030.SH', 'name': '中信证券', 'asOf': '20250328', 'label': '负例'},
    {'code': '600919.SH', 'name': '江苏银行', 'asOf': '20250228', 'label': '负例'},
    {'code': '000651.SZ', 'name': '格力电器', 'asOf': '20240902', 'label': '负例'},
    {'code': '603392.SH', 'name': '万泰生物', 'asOf': '20240715', 'label': 'VCP结构正例'},
    {'code': '002252.SZ', 'name': '上海莱士', 'asOf': '20231016', 'label': '负例'},
    {'code': '601328.SH', 'name': '交通银行', 'asOf': '20230904', 'label': '当时负例'},
]
WINDOWS = [
    {'code': '000776.SZ', 'name': '广发证券', 'start': '20250403', 'end': '20250403', 'kind': 'vcp'},
    {'code': '603392.SH', 'name': '万泰生物', 'start': '20240715', 'end': '20240715', 'kind': 'vcp'},
    {'code': '002027.SZ', 'name': '分众传媒', 'start': '20250707', 'end': '20250801', 'kind': 'vcp'},
    {'code': '600030.SH', 'name': '中信证券', 'start': '20240722', 'end': '20240923', 'kind': 'vcp'},
    {'code': '601328.SH', 'name': '交通银行', 'start': '20230905', 'end': '20231229', 'kind': 'vcp'},
    {'code': '600118.SH', 'name': '中国卫星', 'start': '20250402', 'end': '20250822', 'kind': 'platform'},
]
checks = []


def check(name, condition, evidence=None):
    checks.append({'name': name, 'passed': bool(condition), 'evidence': evidence})


def bars_from_closes(closes):
    return [(f'd{i:03d}', c * 1.001, c * 0.999, c, 100.0) for i, c in enumerate(closes)]


# 精确数值边界：等号均拒绝，严格大于才通过。
equal_close = bars_from_closes([100.0] * 150 + [120.0] * 50)
g_equal_close = ud._vcp_daily_trend_gate(equal_close)
g_above_close = ud._vcp_daily_trend_gate(equal_close[:-1] + [('d199', 120.12, 119.88, 120.01, 100.0)])
check('收盘恰好等于MA50拒绝', not g_equal_close['pass'] and not g_equal_close['closeAboveMA50']
      and g_equal_close['close'] == g_equal_close['ma50'] == 120.0, g_equal_close)
check('收盘严格高于MA50通过该子条件', g_above_close['pass'] and g_above_close['closeAboveMA50'], g_above_close)
equal_ma = bars_from_closes([100.0] * 50 + [120.02] * 100 + [120.0] * 49 + [121.0])
g_equal_ma = ud._vcp_daily_trend_gate(equal_ma)
g_bullish = ud._vcp_daily_trend_gate(bars_from_closes([100.0] * 150 + [130.0] * 49 + [131.0]))
check('MA50恰好等于MA150拒绝', not g_equal_ma['pass'] and not g_equal_ma['bullish']
      and g_equal_ma['ma50'] == g_equal_ma['ma150'] == 120.02
      and g_equal_ma['ma150'] > g_equal_ma['ma200'], g_equal_ma)
check('严格MA50大于MA150大于MA200通过', g_bullish['pass'] and g_bullish['bullish'], g_bullish)
for n in (0, 199):
    short = ud._vcp_daily_trend_gate(bars_from_closes([100.0] * n))
    check(f'日线样本{n}根拒绝且披露原因', not short['pass'] and short['samples'] == n
          and short['bullishStatus'] == 'insufficient_samples'
          and any('不足200' in r for r in short['reasons']), short)

# 幂等包装器同时覆盖正式资格、结构保留和fixed路径。
structure = {'formed': True, 'structurePath': 'fixed_base', 'distPct': 0.0}
passed = ud._apply_vcp_daily_trend_eligibility(structure, bars_from_closes([100.0] * 150 + [130.0] * 49 + [131.0]))
failed = ud._apply_vcp_daily_trend_eligibility(structure, equal_ma)
check('fixed结构通过统一日线门', passed['structureFormed'] and passed['formed']
      and passed['eligible'] and passed['displayEligible'] and passed['dailyTrend']['source'] == 'daily', passed)
check('fixed结构保留但趋势失败不得展示', failed['structureFormed'] and not failed['formed']
      and not failed['eligible'] and not failed['displayEligible'] and failed['rejectReasons'], failed)
check('统一资格包装器幂等', ud._apply_vcp_daily_trend_eligibility(
    passed, bars_from_closes([100.0] * 150 + [130.0] * 49 + [131.0])) == passed)


def swing_structure_bars():
    """真实调用摆动几何；只固定右侧/近期量质量，不伪造收缩结构。"""
    anchors = [4, 14, 24, 34, 44, 54]
    depths = [8, 7, 6, 5, 4]
    vols = [1000, 900, 800, 700, 600]
    out = []
    for i in range(200):
        if i < 140:
            close = 50.0 + i * 0.2
            out.append((f'p{i:03d}', close * 1.001, close * 0.999, close, 1000.0))
            continue
        j = i - 140
        high, low, vol = 90.0 + j * 0.01, 94.0, 500.0
        for k, (a, b) in enumerate(zip(anchors, anchors[1:])):
            if a < j < b:
                low, vol = 100.0 - depths[k], float(vols[k])
                break
        if j in anchors:
            high, low = 100.0, 98.0
        if j > anchors[-1]:
            low, vol = 98.0, float(vols[-1])
        close = (high + low) / 2
        if j == 59:
            high, low, close = 100.0, 98.0, 100.0
        out.append((f's{j:03d}', high, low, close, vol))
    return out


quality_pass = {'pass': True, 'rejectReasons': [], 'reason': None}
volume_pass = {'pass': True, 'reason': None, 'ma5': 600.0, 'ma10': 600.0,
               'ma20': 650.0, 'maBase': 700.0, 'ma10ToBase': 0.857,
               'sequenceOk': True, 'baseWindow': 50}
with patch.object(ud, '_vcp_right_side_quality', return_value=quality_pass), \
     patch.object(ud, '_vcp_recent_volume_quality', return_value=quality_pass), \
     patch.object(ud, '_vcp_volume_ma_evidence', return_value=volume_pass):
    sb = swing_structure_bars()
    high = ud._vcp_level_strict(sb, 60, 2, max_dd=0.15, max_contraction=8.0,
                                dist_high250=0.0, hist_pct=100.0, practical=True)
    low = ud._vcp_level_strict(sb, 60, 2, max_dd=0.15, max_contraction=8.0,
                               dist_high250=-20.0, hist_pct=20.0, practical=True)
    check('strict接近一年高及一年分位100不再排除', high and high['structureFormed']
          and high['formed'] and high['dailyTrendPass'], high)
    check('strict取消高位门前后结构证据一致', high['contractions'] == low['contractions']
          and high['structureFormed'] == low['structureFormed'], {'high': high, 'low': low})
    weekly = ud._vcp_level_strict(sb[-60:], 60, 2, max_dd=0.15, max_contraction=8.0,
                                  dist_high250=0.0, hist_pct=100.0, practical=True, trend_bars=sb)
    check('周线结构统一读取原始200日趋势而非周线MA', weekly and weekly['formed']
          and weekly['dailyTrend'] == high['dailyTrend'] and weekly['dailyTrend']['samples'] == 200, weekly)
    future = sb + [('future1', 1.0, 1.0, 1.0, 1.0), ('future2', 999.0, 999.0, 999.0, 999.0)]
    past_again = ud._vcp_level_strict(future[:-2], 60, 2, max_dd=0.15, max_contraction=8.0,
                                      dist_high250=0.0, hist_pct=100.0, practical=True)
    check('识别日后未来数据不影响strict及趋势证据', past_again == high)

# 平台型VCP位置排除取消；真实A04保留其结构、资金以外原有属性和PIT数据。
import zz_regress96 as r96
library = json.loads(r96.SAMPLE_PATH.read_text(encoding='utf-8'))
case_map, _, _, _ = r96.load_inputs()
a04 = next(x for x in library['samples'] if x['id'] == 'A04')
a04_rows, a04_mv = case_map[a04['sourceCase']]
_, a04_diag = r96.scan(ud, a04_rows, a04_mv)
a04_bars = r96.bars_of(a04_rows)
a04_pf = a04_diag['platform']
high_attr = ud._platform_vcp_attribute(a04_bars, a04_pf, 100.0, 0.0)
normal_attr = ud._platform_vcp_attribute(a04_bars, a04_pf, 44.8, -12.61)
check('平台型VCP属性取消一年分位和近新高排除', high_attr and normal_attr
      and high_attr['formed'] == normal_attr['formed']
      and not any('一年分位' in x or '一年高点' in x for x in high_attr['rejectReasons'])
      and high_attr['dailyTrend']['source'] == 'daily', high_attr)

# 杯柄8%历史高位门不变；平台/底部高位门由111/112真实链回归共同防回退。
def cup_bars(high, close):
    return bars_from_closes([80.0] * 20 + [high, close])
for close, expected in ((92.01, False), (92.0, True), (91.99, True)):
    gate = ud._cup_history_position_gate(cup_bars(100.0, close))
    check(f'杯柄历史高位门close={close}保持', gate['historyGatePass'] is expected, gate)
source = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
check('VCP不再调用突破后位置瑕疵且平台底部高位门保留',
      "if pattern != 'VCP收缩型':\n                        _apply_post_breakout_position_defect" in source
      and 'if ext_high:' in source and 'for evidence in (plat, bottom):' in source)
check('杯柄历史资格函数仍只用于杯柄链', source.count('_apply_cup_history_eligibility(') == 4)


def candidate_view(candidate):
    if not candidate:
        return None
    keys = ('formed', 'structureFormed', 'eligible', 'displayEligible', 'dailyTrendPass',
            'dailyTrend', 'structurePath', 'priceMode', 'days', 'amplitude', 'segAmps',
            'contractions', 'distPct', 'pivot', 'volFirst', 'volLast', 'volRatio', 'rejectReasons')
    return {k: candidate[k] for k in keys if k in candidate}


def scan_asof(code, date):
    rows = [r for r in DATA['rows'][code] if r[0] <= date]
    assert rows and rows[-1][0] == date
    pattern, diag = zz_scan101.scan(ud, rows, 0)
    paths = {'daily': diag.get('vcpDaily'), 'weekly': diag.get('vcpWeekly'), 'fixedBase': diag.get('fixedBase')}
    return {
        'code': code, 'asOf': date, 'rowsUsed': len(rows), 'lastInputDate': rows[-1][0],
        'pattern': pattern, 'formed': pattern == VCP,
        'structurePaths': {k: bool(v and v.get('structureFormed')) for k, v in paths.items()},
        'structureFormed': any(v and v.get('structureFormed') for v in paths.values()),
        'trendPass': bool(next((v for v in paths.values() if v and v.get('structureFormed')), {}).get('dailyTrendPass')),
        'trendEvidence': next((v.get('dailyTrend') for v in paths.values() if v and v.get('structureFormed')), None),
        'reasons': diag.get('rejectReasons') or [],
        'daily': candidate_view(paths['daily']), 'weekly': candidate_view(paths['weekly']),
        'fixedBase': candidate_view(paths['fixedBase']), 'main': candidate_view(diag.get('main')),
        'trendTemplatePass': (diag.get('trendTemplate') or {}).get('pass'),
        'futureRowsExcluded': sum(r[0] > date for r in DATA['rows'][code]),
    }


before_cases = {(x['code'], x['asOf']): x for x in BEFORE['cases']}
case_rows = []
for case in CASES:
    result = scan_asof(case['code'], case['asOf'])
    old = before_cases[(case['code'], case['asOf'])]
    result.update({'name': case['name'], 'humanLabel': case['label'],
                   'beforePattern': old['pattern'], 'changed': old['pattern'] != result['pattern']})
    case_rows.append(result)
    check(f"十例PIT:{case['name']}:{case['asOf']}", result['lastInputDate'] == case['asOf']
          and result['futureRowsExcluded'] >= 0)
    if case['code'] in ('000776.SZ', '603392.SH'):
        check(f"人工结构正例保留:{case['name']}", result['structureFormed'], result['structurePaths'])
    if result['pattern'] == VCP:
        check(f"正式VCP具有新趋势证据:{case['name']}", result['main']['formed']
              and result['main']['dailyTrendPass'] and result['main']['dailyTrend']['pass']
              and result['main']['dailyTrend']['source'] == 'daily', result['main'])

before_window_records = {}
for window in BEFORE['windows']:
    for record in window['records']:
        before_window_records[(window['code'], record['asOf'])] = record
window_rows = []
for spec in WINDOWS:
    records = []
    for row in DATA['rows'][spec['code']]:
        date = row[0]
        if spec['start'] <= date <= spec['end']:
            result = scan_asof(spec['code'], date)
            old = before_window_records[(spec['code'], date)]
            result.update({'beforePattern': old['pattern'], 'changed': old['pattern'] != result['pattern']})
            records.append(result)
            check(f"六窗口PIT:{spec['code']}:{date}", result['lastInputDate'] == date)
            if result['pattern'] == VCP:
                check(f"六窗口正式VCP趋势证据:{spec['code']}:{date}", result['main']['dailyTrendPass']
                      and result['main']['dailyTrend']['pass'] and result['main']['dailyTrend']['source'] == 'daily')
    changes = [{'asOf': r['asOf'], 'before': r['beforePattern'], 'after': r['pattern'],
                'structurePaths': r['structurePaths'], 'trendPass': r['trendPass'],
                'reasons': r['reasons']} for r in records if r['changed']]
    window_rows.append({**spec, 'scannedDays': len(records), 'beforePositiveCount': sum(
        r['pattern'] == VCP for r in before_window_records.values() if r['code'] == spec['code']
        and spec['start'] <= r['asOf'] <= spec['end']),
        'afterPositiveCount': sum(r['pattern'] == VCP for r in records),
        'changedCount': len(changes), 'changes': changes, 'records': records})
    check(f"六窗口完整重算:{spec['name']}:{spec['start']}~{spec['end']}", bool(records)
          and len(records) == len(window_rows[-1]['records']))

# 前端旧快照缺新证据不得伪装合格VCP，公开文案在精扫与总览共用。
evidence_ui = (ROOT / 'src/sections/patternEvidence.ts').read_text(encoding='utf-8')
weekly_ui = (ROOT / 'src/sections/WeeklySummary.tsx').read_text(encoding='utf-8')
eci_ui = (ROOT / 'src/sections/ECIPanel.tsx').read_text(encoding='utf-8')
check('前端旧VCP缺趋势证据不展示', "item.vcpDailyTrend?.pass === true && item.dailyTrendPass === true" in evidence_ui)
check('前端VCP提示完整且两入口共用', all(x in evidence_ui + weekly_ui + eci_ui for x in (
    'vcpDailyTrendText', 'closeAboveMA50', 'bullishStatus',
    '日线收盘>MA50且MA50>MA150>MA200；VCP不限制接近新高')))
check('VCP不再显示一年高位徽标', '!isContract && (it.histPct ?? 0) > 60' in eci_ui)

production_files = ('public/fund_data.json', 'src/data/fund_data.json')
data_sha = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in production_files}
failed = [c['name'] for c in checks if not c['passed']]
summary = {
    'task': 113, 'allPassed': not failed, 'checksPassed': len(checks) - len(failed),
    'checksTotal': len(checks), 'failed': failed, 'dataSha256': DATA_SHA256,
    'caseChangedCount': sum(r['changed'] for r in case_rows),
    'windowChangedCount': sum(r['changedCount'] for r in window_rows),
    'windowPositiveCounts': {r['code']: {'before': r['beforePositiveCount'], 'after': r['afterPositiveCount'],
                                       'changedDays': r['changedCount']} for r in window_rows},
    'productionFundDataSha256': data_sha, 'pitOnly': True, 'notMarketWinRate': True,
    'manualDispatch': False, 'productionDataRegenerated': False,
}
report = {'summary': summary, 'checks': checks, 'cases': case_rows, 'windows': window_rows,
          'productionSha256': hashlib.sha256((ROOT / 'scripts/update_data.py').read_bytes()).hexdigest(),
          'baselineFile': 'zz_task113_before103.json'}
(ROOT / 'zz_regress113_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(ROOT / 'zz_regress113_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
print('指定日变化:', json.dumps([{k: r[k] for k in ('name', 'asOf', 'beforePattern', 'pattern', 'structurePaths', 'trendPass', 'reasons')}
                               for r in case_rows if r['changed']], ensure_ascii=False, indent=2))
print('窗口变化:', json.dumps([{k: r[k] for k in ('name', 'start', 'end', 'beforePositiveCount', 'afterPositiveCount', 'changedCount', 'changes')}
                             for r in window_rows], ensure_ascii=False, indent=2))
raise SystemExit(1 if failed else 0)
