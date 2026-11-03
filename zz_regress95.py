# -*- coding: utf-8 -*-
"""任务95：真实误判拒绝、右侧双门边界、指定正样本as-of与信号新鲜度回归。"""
import importlib.util
import json
from pathlib import Path

import zz_regress22 as reg
import zz_regress23_83 as r23
import zz_regress96 as r96

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


u = load('update_data95', ROOT / 'scripts' / 'update_data.py')
old = load('update_data95_before', ROOT / 'zz_update_data_before95.py')
results = []


def check(name, condition, evidence):
    results.append({'name': name, 'pass': bool(condition), 'evidence': evidence})
    if not condition:
        raise AssertionError(f'{name}: {evidence}')


def bars_of(rows):
    return [(r[0], r[2], r[3], r[1], r[4]) for r in rows]


def asof(rows, date):
    return [r for r in rows if r[0] <= date]


def scan(module, rows, mv=None):
    # 96b生产展示门由96 harness复刻；旧95基线仍走旧扫描器，避免把新fuzzy误报成回退。
    if module is u:
        return r96.scan(module, rows, mv)
    reg.ud = module
    return reg.scan(rows, mv, allow_cup_defect=True)


def brief(cup):
    if not cup:
        return None
    return {k: cup.get(k) for k in ('days', 'totalDays', 'rimDate', 'rimHigh', 'cupStart', 'cupEnd',
            'handleStart', 'handleEnd', 'handlePosition', 'pivot', 'pivotRecovery',
            'rightSideHigh', 'rightSideOvershootPct', 'signalDate', 'signalType',
            'breakoutAge', 'currentDist', 'currentValid', 'initialStop')}


def gate_from_old_candidate(anchor, cup):
    """从改门前真实候选还原杯底→柄前右侧；只用于解释新门拒绝原因。"""
    n = cup['days']
    window = anchor[-(n + 120):-n]
    low_i = min(range(len(window)), key=lambda i: window[i][2])
    right = window[low_i + 1:]
    return u._cup_right_side_gate(cup['rimHigh'], cup['pivot'], right)


# 数值边界直接走生产共用函数：92%含边界，低于92%拒绝；5%含边界，超过5%拒绝。
right_ok = [('20260101', 100.0, 90.0, 99.0, 1.0)]
g92 = u._cup_right_side_gate(100.0, 92.0, right_ok)
g9199 = u._cup_right_side_gate(100.0, 91.99, right_ok)
g5 = u._cup_right_side_gate(100.0, 100.0, [('20260101', 105.0, 90.0, 99.0, 1.0)])
g501 = u._cup_right_side_gate(100.0, 100.0, [('20260101', 105.01, 90.0, 99.0, 1.0)])
check('枢轴收复92%边界通过', g92['pass'] and g92['pivotRecovery'] == 92.0, g92)
check('枢轴收复91.99%透明拒绝', not g9199['pass'] and '枢轴收复' in g9199['rejectReasons'][0], g9199)
check('柄前右侧超沿5%边界通过', g5['pass'] and g5['rightSideOvershootPct'] == 5.0, g5)
check('柄前右侧超沿5.01%透明拒绝', not g501['pass'] and '柄前右侧' in g501['rejectReasons'][0], g501)
check('右侧无效段不得通过', not u._cup_right_side_gate(100, 100, [])['pass'], 'empty right side')

# 三只真实OHLCV截至20261029：改门前确实命中，新普通/early均不得成为杯柄。
fixture = json.loads((ROOT / 'zz_real95_asof1029.json').read_text(encoding='utf-8'))['rows']
negative_evidence = {}
for code in ('002648.SZ', '600985.SH', '000415.SZ'):
    bars = bars_of(fixture[code])
    before_strict = old._cup_handle_strict(bars, True, allow_weekly_defect=True)
    before_early = old._cup_early_breakout(bars)
    after_strict = u._cup_handle_strict(bars, True, allow_weekly_defect=True)
    after_early = u._cup_early_breakout(bars)
    if code == '000415.SZ':
        check('渤海改门前真实早期信号可复现', before_early
              and before_early.get('signalDate') == '20261029'
              and before_early.get('breakoutAge') == 0, brief(before_early))
        anchor = bars[:next(i for i, b in enumerate(bars) if b[0] == before_early['anchorDate']) + 1]
        anchor_cup = old._cup_handle_strict(anchor, True)
        gate = gate_from_old_candidate(anchor, anchor_cup)
        displayed_recovery = round(before_early['pivot'] / before_early['rimHigh'] * 100, 2)
        check('渤海展示杯沿4.75对应枢轴收复不足92%', before_early['rimHigh'] == 4.75
              and displayed_recovery < u.CUP_PIVOT_RECOVERY_MIN,
              {'bodyEvidenceRimHigh': before_early['rimHigh'], 'pivot': before_early['pivot'],
               'displayedPivotRecovery': displayed_recovery,
               'strictLeftRimHigh': anchor_cup['rimHigh'], 'strictGate': gate})
    else:
        check(f'{code}改门前普通杯柄可复现', before_strict and before_strict.get('formed'), brief(before_strict))
        gate = gate_from_old_candidate(bars, before_strict)
    check(f'{code}新门拒绝原因为右侧先于柄明显超沿', not gate['pass']
          and any('柄前右侧' in reason for reason in gate['rejectReasons']), gate)
    check(f'{code}普通杯柄新链拒绝', after_strict is None, brief(after_strict))
    check(f'{code}early不得绕过同一结构门', after_early is None, brief(after_early))
    negative_evidence[code] = {'beforeStrict': brief(before_strict), 'beforeEarly': brief(before_early),
                               'afterStrict': brief(after_strict), 'afterEarly': brief(after_early),
                               'newGateOnOldCandidate': gate}

# 指定正样本及既有样本：同一数据、同一全链路，新增拒绝必须为空。
case_map = {label: (rows, mv) for label, rows, mv in r23.cases()}
named_labels = [label for label in case_map if any(key in label for key in (
    '601808', '600583', '601857', '600028', '600309', '09987', '惠泰医疗', '平高电气'))]
positive_comparisons = []
for label in named_labels:
    rows, mv = case_map[label]
    before_pattern, before_diag = scan(old, rows, mv)
    after_pattern, after_diag = scan(u, rows, mv)
    positive_comparisons.append({'case': label, 'before': before_pattern, 'after': after_pattern,
                                 'beforeCup': brief(before_diag.get('cup') or before_diag.get('regularCup')),
                                 'afterCup': brief(after_diag.get('cup') or after_diag.get('regularCup')),
                                 'afterReasons': after_diag.get('rejectReasons') or []})
expected_96b = {
    'VCP|600583.SH|2022-08-22': None,
    'CUP|601808.SH|20190507|20190816|近似杯柄': None,
    'CUP|600583.SH|20250901|20260107|杯柄': '长平台整理',
    'CUP|601857.SH|20250120|20250603|双底杯柄': '杯柄型',
    'CUP|600028.SH|20220307|20220526|双底杯柄': None,
}
unexpected_96b = [x for x in positive_comparisons if x['before'] != x['after']
                  and expected_96b.get(x['case']) != x['after']]
check('指定历史案例仅出现96b改进与任务97明确空头剔除', not unexpected_96b, unexpected_96b)
check('三个新增剔除均有周MA空头证据', all(x['afterReasons'] == ['周MA150<MA200空头排列']
      for x in positive_comparisons if x['before'] != x['after'] and x['after'] is None),
      [x for x in positive_comparisons if x['before'] != x['after'] and x['after'] is None])

# 平高：50%柄位边界与92.55%枢轴收复的真实正样本，买点窗逐日对比。
pg_rows, pg_mv = case_map['CUP|平高电气|20260924']
pg_full = json.loads((ROOT / 'zz_600312_qfq.json').read_text(encoding='utf-8'))['rows']
pg_rows_all = [[r['date'], r['close'], r['high'], r['low'], r['vol']] for r in pg_full]
pg_replay = []
for date in ('20260921', '20260922', '20260923', '20260924', '20260928', '20260929', '20260930'):
    rows = asof(pg_rows_all, date)
    bp, bd = scan(old, rows)
    ap, ad = scan(u, rows)
    cup = ad.get('cup') or ad.get('regularCup')
    pg_replay.append({'date': date, 'before': bp, 'after': ap, 'cup': brief(cup),
                      'historyGate': u._cup_history_position_gate(bars_of(rows))})
# 20260921在任务109基线已回退为长平台，并非任务110剔除；本次须证明该日历史门仍通过。
pg_expected_changes = {'20260921': ('杯柄型', '长平台整理')}
pg_actual_changes = {x['date']: (x['before'], x['after']) for x in pg_replay if x['before'] != x['after']}
check('平高买点窗仅保留任务110前既有分类差异', pg_actual_changes == pg_expected_changes, pg_replay)
pg0921 = next(x for x in pg_replay if x['date'] == '20260921')
check('平高0921分类差异非历史高位门造成', pg0921['historyGate']['historyGatePass']
      and pg0921['historyGate']['historyExclusionReason'] is None, pg0921)
pg0924 = next(x for x in pg_replay if x['date'] == '20260924')
check('平高50%柄位及92%以上收复仍识别', pg0924['after'] == '杯柄型'
      and pg0924['cup']['handlePosition'] == 0.5
      and pg0924['cup']['pivotRecovery'] >= 92, pg0924)

# 惠泰：覆盖用户提供的大结构末日及原买点复权时点，不把旧BOLL拒绝写成新门拒绝。
ht_full = json.loads((ROOT / 'zz_688617_qfq.json').read_text(encoding='utf-8'))['rows']
ht_rows_all = [[r['date'], r['close'], r['high'], r['low'], r['vol']] for r in ht_full]
ht_replay = []
for date in ('20260916', '20260918', '20260922', '20260924', '20260930',
             '20261009', '20261012', '20261026'):
    rows = asof(ht_rows_all, date)
    bp, bd = scan(old, rows)
    ap, ad = scan(u, rows)
    ht_replay.append({'date': date, 'before': bp, 'after': ap,
                      'cup': brief(ad.get('cup') or ad.get('regularCup'))})
# 0918/0924是任务109基线已有的模糊杯柄改进，不属于任务110新增变化。
ht_expected_changes = {'20260918': (None, '杯柄型'), '20260924': (None, '杯柄型')}
ht_actual_changes = {x['date']: (x['before'], x['after']) for x in ht_replay if x['before'] != x['after']}
check('惠泰大结构与买点窗仅保留任务110前既有改进', ht_actual_changes == ht_expected_changes, ht_replay)
ht1012 = next(x for x in ht_replay if x['date'] == '20261012')
check('惠泰确认买点仍模糊杯柄且右侧双门通过', ht1012['after'] == '杯柄型'
      and ht1012['cup']['pivotRecovery'] >= 92
      and ht1012['cup']['rightSideOvershootPct'] <= 5, ht1012)

# 中国广核/600795：真实首次信号、右侧新门与age 5/6同时保留。
cache = json.loads((WORK / 'vcp_cache_1027.json').read_text(encoding='utf-8'))['stock_daily']
rows3816 = cache['003816.SZ']
signal_replay = []
for code, rows, dates in (
        ('003816.SZ', rows3816, ('20261008', '20261015', '20261016')),
        ('600795.SH', json.loads((ROOT / 'zz_600795_full_rows92.json').read_text(encoding='utf-8')),
         ('20260902', '20260909', '20260910'))):
    for date in dates:
        bars = bars_of(asof(rows, date))
        sig = u._cup_early_breakout(bars)
        signal_replay.append({'code': code, 'asOf': date, 'signal': brief(sig),
                              'displayable': u._cup_signal_displayable(sig)})
        check(f'{code} {date}真实首次信号及新右侧门保留', sig and sig.get('pivotRecovery') >= 92
              and sig.get('rightSideOvershootPct') <= 5, brief(sig))
    check(f'{code}首次信号age5/6门不回退', u.CUP_SIGNAL_MAX_AGE == 5
          and signal_replay[-2]['displayable'] and not signal_replay[-1]['displayable']
          and signal_replay[-2]['signal']['breakoutAge'] == 5
          and signal_replay[-1]['signal']['breakoutAge'] == 6, signal_replay[-2:])

# 早期中国石油保留严格结构与首次信号证据；其现行全链路未命中的原因不得伪写成95新增拒绝。
petro = next(x for x in positive_comparisons if '601857' in x['case'])
check('中国石油早期正样本结构仍返回且信号未被96b重置', petro['beforeCup'] and petro['afterCup']
      and petro['beforeCup']['signalDate'] == petro['afterCup']['signalDate'] == '20250528'
      and petro['afterCup']['pivotRecovery'] >= 92, petro)

# 23案例完整对比：96b的每一处标签变化均按真实before/after固定，禁止借此删除反例。
all23 = []
for label, rows, mv in r23.cases():
    bp, bd = scan(old, rows, mv)
    ap, ad = scan(u, rows, mv)
    all23.append({'case': label, 'before': bp, 'after': ap, 'changed': bp != ap,
                  'afterReasons': ad.get('rejectReasons') or []})
changes23 = [x for x in all23 if x['changed']]
expected_changes_96b = {
    'VCP|000625.SZ|2023-09-27': ('杯柄型', '平台整理'),
    'VCP|000708.SZ|2025-06-10': ('底部整理', None),
    'VCP|000725.SZ|2026-04-17': (None, '平台整理'),
    'VCP|002028.SZ|2025-07-11': (None, '长平台整理'),
    'VCP|688012.SH|2023-03-01': ('底部整理', '长平台整理'),
    'VCP|688041.SH|2024-09-24': (None, '长平台整理'),
    'VCP|688047.SH|2024-09-26': (None, '底部整理'),
    'VCP|601000.SH|2026-01-19': ('底部整理', '长平台整理'),
    'VCP|002155.SZ|2026-01-09': ('杯柄型', None),
    'VCP|600583.SH|2022-08-22': ('底部整理', None),
    'CUP|601808.SH|20190507|20190816|近似杯柄': ('底部整理', None),
    'CUP|600583.SH|20250901|20260107|杯柄': (None, '长平台整理'),
    'CUP|601857.SH|20250120|20250603|双底杯柄': (None, '杯柄型'),
    'CUP|600028.SH|20220307|20220526|双底杯柄': ('长平台整理', None),
    'LP|海光段①|688041.SH|20240909': (None, '长平台整理'),
}
actual_changes_96b = {x['case']: (x['before'], x['after']) for x in changes23}
check('23案例仅出现96b及任务97逐项审核变化', actual_changes_96b == expected_changes_96b, changes23)
check('23案例四个新增空头剔除证据完整', all(x['afterReasons'] == ['周MA150<MA200空头排列']
      for x in changes23 if x['case'] in {
          'VCP|000708.SZ|2025-06-10', 'VCP|600583.SH|2022-08-22',
          'CUP|601808.SH|20190507|20190816|近似杯柄',
          'CUP|600028.SH|20220307|20220526|双底杯柄'}), changes23)

note_source = (ROOT / 'scripts' / 'update_data.py').read_text(encoding='utf-8')
check('页面note包含右侧双门及早期干净链', '枢轴收复原杯沿≥92%' in note_source
      and '柄前右侧最高超原杯沿≤5%' in note_source
      and '早期链只走干净全局杯、50~80%柄位' in note_source, 'vcpStocks.note source')
check('early生产锚点仍调用共用strict结构函数', 'ch = _cup_handle_strict(anchor, True, dist_high250=dist_high, hist_pct=hist_pct)'
      in note_source, '_cup_early_breakout shared strict anchor')

report = {
    'passed': sum(x['pass'] for x in results), 'total': len(results), 'results': results,
    'negativeEvidence': negative_evidence,
    'positiveComparisons': positive_comparisons,
    'pinggaoReplay': pg_replay, 'huitaiReplay': ht_replay, 'signalReplay': signal_replay,
    'all23': all23, 'changes23': changes23,
    'handlePositionCalibration': '保留0.50~0.80；平高/中国广核0.50，未采用会误杀正样本的60/65%',
    'freshness': 'CUP_SIGNAL_MAX_AGE=5，age5通过/age6拒绝',
    'data': '三只1026前为真实vcp_cache，20261027~29用Tushare pro.daily补齐；其余为既有真实历史fixtures',
}
(ROOT / 'zz_regress95.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'passed': report['passed'], 'total': report['total'], 'changes23': changes23},
                 ensure_ascii=False, indent=2))
