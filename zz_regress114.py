# -*- coding: utf-8 -*-
"""任务114：VCP孕育期新高门、横盘优选、通用突破生命周期与再次入选历史。"""
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
import zz_scan101

VCP = 'VCP收缩型'
DATA_PATH = ROOT / 'zz_audit100_current_rows_full.json'
DATA_SHA256 = 'f77eb8dcfcd11c0d582ea44eec9b25b67b859fd9c1de383c4dde6cbb4fa25d45'
DATA = json.loads(DATA_PATH.read_text(encoding='utf-8'))
assert hashlib.sha256(DATA_PATH.read_bytes()).hexdigest() == DATA_SHA256
PRODUCTION = ('public/fund_data.json', 'src/data/fund_data.json')
production_before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in PRODUCTION}
checks = []


def check(name, condition, evidence=None):
    checks.append({'name': name, 'passed': bool(condition), 'evidence': evidence})


def bars_of(rows):
    return [(r[0], r[2], r[3], r[1], r[4]) for r in rows]


def rows_asof(code, date):
    rows = [r for r in DATA['rows'][code] if r[0] <= date]
    assert rows and rows[-1][0] == date
    return rows


def candidate_view(candidate):
    if not candidate:
        return None
    keys = ('formed', 'structureFormed', 'eligible', 'displayEligible', 'dailyTrendPass',
            'gestationPass', 'vcpGestation', 'startDate', 'endDate', 'pivot', 'structurePath')
    return {k: candidate[k] for k in keys if k in candidate}


# 中国神华：提前新高拒绝；接近但未破参考高允许。
shenhua_reject_rows = rows_asof('601088.SH', '20251104')
shenhua_reject = ud._vcp_fixed_base(bars_of(shenhua_reject_rows))
reject_gate = shenhua_reject['vcpGestation']
check('中国神华20251104孕育期提前新高拒绝正式VCP', shenhua_reject['structureFormed']
      and not shenhua_reject['formed'] and not shenhua_reject['displayEligible']
      and not shenhua_reject['gestationPass'] and reject_gate['referenceHigh'] == 43.60
      and reject_gate['prematureNewHighs'][0]['date'] == '20251030'
      and reject_gate['prematureNewHighs'][0]['high'] == 43.81, candidate_view(shenhua_reject))
pattern, diag = zz_scan101.scan(ud, shenhua_reject_rows, 0)
check('中国神华20251104结构证据保留但不入选VCP', pattern != VCP
      and diag['fixedBase']['structureFormed'] and not diag['fixedBase']['formed'], pattern)
shenhua_near = ud._vcp_fixed_base(bars_of(rows_asof('601088.SH', '20251202')))
near_gate = shenhua_near['vcpGestation']
check('中国神华20251202接近新高但未破可入', shenhua_near['formed'] and shenhua_near['gestationPass']
      and near_gate['referenceHigh'] == 43.99 and not near_gate['prematureNewHighs']
      and near_gate['nearHighAllowed'] and near_gate['startDate'] == '20251111', candidate_view(shenhua_near))

# 合成边界：内部提前新高、最后正常突破、最后非突破、新高参考和横盘优选。
def synthetic_bars():
    return [(f'd{i:03d}', 100.0, 99.0, 100.0, 1000.0) for i in range(30)]

base = synthetic_bars()
base[20] = ('d020', 105.0, 99.0, 100.0, 1000.0)
internal = list(base)
internal[22] = ('d022', 105.01, 99.0, 100.0, 1000.0)
internal_gate = ud._vcp_gestation_new_high_gate(internal, 'd020', 104.0, 'd025', 105.0)
check('合成内部提前新高硬拒绝', not internal_gate['pass'] and internal_gate['status'] == 'premature_new_high'
      and internal_gate['prematureNewHighs'][0]['date'] == 'd022', internal_gate)
final = list(base)
final[25] = ('d025', 106.0, 99.0, 104.01, 1000.0)
final_gate = ud._vcp_gestation_new_high_gate(final, 'd020', 104.0, 'd025', 105.0)
check('最后一天实际收盘高于枢轴的正常突破豁免', final_gate['pass'] and final_gate['finalBreakout']
      and final_gate['finalBreakout']['date'] == 'd025' and not final_gate['prematureNewHighs'], final_gate)
not_final = list(final)
not_final[25] = ('d025', 106.0, 99.0, 104.0, 1000.0)
not_final_gate = ud._vcp_gestation_new_high_gate(not_final, 'd020', 104.0, 'd025', 105.0)
check('最后一天收盘未严格高于枢轴不得豁免', not not_final_gate['pass']
      and not_final_gate['prematureNewHighs'][0]['close'] == 104.0, not_final_gate)
near = list(base)
near[23] = ('d023', 105.0, 99.0, 104.9, 1000.0)
near_gate = ud._vcp_gestation_new_high_gate(near, 'd020', 104.0, 'd025', 105.0)
check('恰好接近参考高但未破不拒绝', near_gate['pass'] and near_gate['referenceHigh'] == 105.0
      and near_gate['referenceSamples'] == 20, near_gate)
short_gate = ud._vcp_gestation_new_high_gate(base, 'd005', 104.0, 'd010', 105.0)
check('新高参考样本不足明确拒绝并披露', not short_gate['pass'] and short_gate['status'] == 'insufficient_samples'
      and short_gate['referenceSamples'] == 5 and any('不足20' in x for x in short_gate['rejectReasons']), short_gate)

flat = list(base)
flat[20] = ('d020', 110.0, 99.0, 100.0, 1000.0)
flat[25] = ('d025', 110.0, 99.0, 102.0, 1000.0)
drifty = list(flat)
drifty[25] = ('d025', 110.0, 99.0, 110.0, 1000.0)
flat_gate = ud._vcp_gestation_new_high_gate(flat, 'd020', 150.0, 'd025', 110.0)
drift_gate = ud._vcp_gestation_new_high_gate(drifty, 'd020', 150.0, 'd025', 110.0)
check('横盘与非完全横盘仅差优选标签不改变资格', flat_gate['pass'] and drift_gate['pass']
      and flat_gate['sidewaysPreferred'] and not drift_gate['sidewaysPreferred']
      and flat_gate['sidewaysScore'] > drift_gate['sidewaysScore']
      and drift_gate['sidewaysLabel'].startswith('非完全横盘但可入')
      and drift_gate['sidewaysPreferenceOnly'], {'flat': flat_gate, 'drifty': drift_gate})

# 任务113等号、样本和严格多头门不变。
def bars_from_closes(closes):
    return [(f'd{i:03d}', c * 1.001, c * 0.999, c, 100.0) for i, c in enumerate(closes)]

equal_close = bars_from_closes([100.0] * 150 + [120.0] * 50)
trend_equal = ud._vcp_daily_trend_gate(equal_close)
trend_short = ud._vcp_daily_trend_gate(equal_close[:199])
trend_pass = ud._vcp_daily_trend_gate(bars_from_closes([100.0] * 150 + [130.0] * 49 + [131.0]))
check('任务113等号和至少200根硬门不变', not trend_equal['pass'] and not trend_short['pass']
      and trend_equal['close'] == trend_equal['ma50'] and trend_short['samples'] == 199)
check('任务113严格多头门不变', trend_pass['pass'] and trend_pass['closeAboveMA50'] and trend_pass['bullish'])

# strict/daily真实正例。
strict_rows = rows_asof('000776.SZ', '20250403')
strict_bars = bars_of(strict_rows)
strict = ud._vcp_level_strict(strict_bars, ud.VCP_DAILY_WIN, ud.VCP_DAILY_K,
                              max_dd=0.15, max_contraction=8.0, practical=True)
check('strict与daily路径均含通过的孕育证据', strict and strict['formed'] and strict['structureFormed']
      and strict['vcpGestation']['pass'] and strict['gestationPass']
      and strict['vcpGestation']['startDate'] == '20250217', candidate_view(strict))
check('fixed路径含孕育证据', shenhua_near.get('vcpGestation') and shenhua_near['gestationPass'])

# 周线结构：周键映射回原始交易日，不拿YYYYWww查日线。
def dated_swing_bars():
    dates = []
    day = dt.date(2026, 10, 30)
    while len(dates) < 200:
        if day.weekday() < 5:
            dates.append(day)
        day -= dt.timedelta(days=1)
    dates = list(reversed(dates))
    closes = [50.0] * 150 + [130.0] * 49 + [131.0]
    return [(dates[i].strftime('%Y%m%d'), c * 1.001, c * 0.999, c, 1000.0)
            for i, c in enumerate(closes)]


daily_for_week = dated_swing_bars()
week_keys = []
for bar in daily_for_week:
    day = dt.datetime.strptime(bar[0], '%Y%m%d').date()
    key = f'{day.isocalendar().year}W{day.isocalendar().week:02d}'
    if key not in week_keys:
        week_keys.append(key)
anchors = [4, 10, 16, 22, 28, 34]
depths = [8, 7, 6, 5, 4]
vols = [1000, 900, 800, 700, 600]
weekly_bars = []
for i, key in enumerate(week_keys):
    high, low, vol = 90.0, 98.0, 600.0
    for k, (a, b) in enumerate(zip(anchors, anchors[1:])):
        if a < i < b:
            low, vol = 100.0 - depths[k], float(vols[k])
            break
    if i in anchors:
        high, low = 100.0, 98.0
    if i > anchors[-1]:
        low, vol = 98.0, float(vols[-1])
    close = (high + low) / 2
    if i == len(week_keys) - 1:
        high, low, close = 100.0, 98.0, 100.0
    weekly_bars.append((key, high, low, close, vol))
quality_pass = {'pass': True, 'rejectReasons': [], 'reason': None}
volume_pass = {'pass': True, 'reason': None, 'ma5': 600.0, 'ma10': 600.0,
               'ma20': 650.0, 'maBase': 700.0, 'ma10ToBase': 0.857,
               'sequenceOk': True, 'baseWindow': 50}
with patch.object(ud, '_vcp_right_side_quality', return_value=quality_pass), \
     patch.object(ud, '_vcp_recent_volume_quality', return_value=quality_pass), \
     patch.object(ud, '_vcp_volume_ma_evidence', return_value=volume_pass):
    weekly = ud._vcp_level_strict(weekly_bars, 40, 1, max_dd=0.15, max_contraction=8.0,
                                  practical=True, trend_bars=daily_for_week)
check('周线结构含孕育证据且周键映射原始日线', weekly and weekly.get('vcpGestation')
      and 'W' in weekly['structureStartDate'] and 'W' not in weekly['startDate']
      and len(weekly['startDate']) == 8 and weekly['endDate'] == '20261030'
      and weekly['dailyTrend']['samples'] == 200, candidate_view(weekly))

# 平台型VCP属性沿用真实A04结构，必须附孕育证据。
import zz_regress96 as r96
library = json.loads(r96.SAMPLE_PATH.read_text(encoding='utf-8'))
case_map, _, _, _ = r96.load_inputs()
a04 = next(x for x in library['samples'] if x['id'] == 'A04')
a04_rows, _ = case_map[a04['sourceCase']]
_, a04_diag = r96.scan(ud, a04_rows, 0)
platform_attr = ud._platform_vcp_attribute(bars_of(a04_rows), a04_diag['platform'], 100.0, 0.0)
check('平台型VCP属性含孕育证据且高位不硬拒', platform_attr and platform_attr.get('vcpGestation')
      and platform_attr['vcpGestation']['nearHighAllowed']
      and not any('一年分位' in x or '一年高点' in x for x in platform_attr['rejectReasons']),
      candidate_view(platform_attr))

# 中国核电首批种子：通用定义得到20261015，10个交易日边界准确。
nuclear_rows = rows_asof('601985.SH', '20261030')
nuclear_origin_rows = rows_asof('601985.SH', '20261013')
nuclear_origin_bars = bars_of(nuclear_origin_rows)
nuclear_fixed = ud._vcp_fixed_base(nuclear_origin_bars)
nuclear_gate = nuclear_fixed['vcpGestation']
nuclear_platform = ud._vcp_platform(
    nuclear_origin_bars, max_amp=0.105, tail_vol_max=ud.PATTERN_TAIL_VOL_MAX,
    rise_max=0.20, trend60_min=-0.10,
    dist_gate=(ud.VCP_SHOW_DIST_LO, ud.VCP_SHOW_DIST_PLAT), practical=True,
    dist_high250=(nuclear_origin_rows[-1][1] / max(r[1] for r in nuclear_origin_rows[-250:]) - 1) * 100)
check('中国核电20261013仅结构成立不伪称正式VCP', nuclear_fixed['structureFormed']
      and not nuclear_fixed['formed'] and not nuclear_fixed['dailyTrendPass']
      and nuclear_fixed['dailyTrend']['ma50'] < nuclear_fixed['dailyTrend']['ma150']
      and nuclear_platform['type'] == '底部平台型', candidate_view(nuclear_fixed))
check('中国核电孕育枢轴9.21参考高9.51', nuclear_fixed['startDate'] == '20260828'
      and nuclear_fixed['endDate'] == '20261013' and nuclear_fixed['pivot'] == 9.21
      and nuclear_gate['referenceHigh'] == 9.51 and nuclear_gate['referenceDate'] == '20251029')


def nuclear_candidate():
    return {
        'patternType': '底部平台型', 'structurePath': 'fixed_base_plus_platform_structure_replay',
        'startDate': nuclear_fixed['startDate'], 'endDate': nuclear_fixed['endDate'],
        'pivot': nuclear_fixed['pivot'], 'referenceHigh': nuclear_gate['referenceHigh'],
        'referenceDate': nuclear_gate['referenceDate'], 'referenceBasis': nuclear_gate['referenceBasis'],
        'referenceSamples': nuclear_gate['referenceSamples'], 'anchorHigh': nuclear_gate['anchorHigh'],
        'invalidation': nuclear_fixed['invalidation'], 'sidewaysLabel': nuclear_gate['sidewaysLabel'],
        'sidewaysScore': nuclear_gate['sidewaysScore'], 'dailyTrend': nuclear_fixed['dailyTrend'],
        'vcpGestation': nuclear_gate,
        'originQualificationNote': '底部平台型结构突破回放；仅价格结构回放，不冒充当时正式入选。',
    }


def fresh_nuclear_history():
    history = ph.empty_history()
    assert ph.register_gestation(history, '601985.SH', '中国核电', nuclear_candidate(),
                                 '20261013', origin_formal=False)
    return history


nuclear_bars = bars_of(nuclear_rows)
fresh_14 = fresh_nuclear_history()
active_14 = ph.advance_stock(fresh_14, '601985.SH', '中国核电',
                             [b for b in nuclear_bars if b[0] <= '20261014'])
fresh_15 = fresh_nuclear_history()
active_15 = ph.advance_stock(fresh_15, '601985.SH', '中国核电',
                             [b for b in nuclear_bars if b[0] <= '20261015'])
check('中国核电20261014尚未突破20261015才突破', active_14 is None and active_15
      and active_15['breakoutDate'] == '20261015' and active_15['breakoutHigh'] == 9.52
      and active_15['breakoutClose'] == 9.41 and active_15['pivot'] == 9.21
      and active_15['referenceHigh'] == 9.51, active_15)
fresh_28 = fresh_nuclear_history()
active_28 = ph.advance_stock(fresh_28, '601985.SH', '中国核电',
                             [b for b in nuclear_bars if b[0] <= '20261028'])
life_28 = ph.trading_day_lifecycle([b[0] for b in nuclear_bars if b[0] <= '20261028'], '20261015')
fresh_29 = fresh_nuclear_history()
active_29 = ph.advance_stock(fresh_29, '601985.SH', '中国核电',
                             [b for b in nuclear_bars if b[0] <= '20261029'])
life_29 = ph.trading_day_lifecycle([b[0] for b in nuclear_bars if b[0] <= '20261029'], '20261015')
check('中国核电20261028年龄9仍active', active_28 and life_28['active'] and life_28['breakoutAge'] == 9
      and life_28['remainingDays'] == 1 and ph.active_candidate(
          active_28, [b for b in nuclear_bars if b[0] <= '20261028'])['breakoutRemainingDays'] == 1)
check('中国核电20261029年龄10退出', active_29 is None and life_29['expired']
      and life_29['breakoutAge'] == 10 and life_29['exitDate'] == '20261029'
      and ph.active_candidate(active_15, [b for b in nuclear_bars if b[0] <= '20261029']) is None, life_29)
full_replay = fresh_nuclear_history()
ph.advance_stock(full_replay, '601985.SH', '中国核电', nuclear_bars)
check('同PIT前缀与全量未来数据重放首个突破一致', full_replay['stocks']['601985.SH']['episodes'][0]
      == fresh_15['stocks']['601985.SH']['episodes'][0]
      and full_replay['stocks']['601985.SH']['episodes'][0]['breakoutDate'] == '20261015')

seed = ph.load_history({})
seed_episode = seed['stocks']['601985.SH']['episodes'][0]
check('持久化种子字段完整且明确非正式入选', seed_episode['episodeId'] == active_15['episodeId']
      and seed_episode['originFormalAdmission'] is False
      and '不冒充当时正式入选' in seed_episode['originQualificationNote']
      and seed['coverage']['fullMarketComplete'] is False
      and seed['coverage']['sourceSha256'] == DATA_SHA256, seed_episode)
merged = ph.load_history({'patternEpisodeHistory': fresh_15})
check('种子与运行缓存合并不重复事件', len(merged['stocks']['601985.SH']['episodes']) == 1)

# 同锚点登记只推进终点；已生成episode后不得重复包装首次突破。
update_anchor = fresh_nuclear_history()
updated_candidate = dict(nuclear_candidate(), endDate='20261014')
assert ph.register_gestation(update_anchor, '601985.SH', '中国核电', updated_candidate, '20261014', False)
check('同锚点pending只推进可见终点', len(update_anchor['stocks']['601985.SH']['pending']) == 1
      and update_anchor['stocks']['601985.SH']['pending'][0]['gestationEnd'] == '20261014')
check('已突破同锚点不得重复登记', not ph.register_gestation(
    fresh_15, '601985.SH', '中国核电', nuclear_candidate(), '20261015', False))

# 当前episode不冒充历史；再次入选才返回此前不同episode完整小字标签。
current_item = {'code': '601985.SH', 'patternEpisode': active_15,
                'buyPoint': {'breakoutDate': '20261015'}}
ph.attach_history([current_item], seed, '20261015')
check('当前首次突破不显示成历史', current_item['patternHistory'] == [])
again_item = {'code': '601985.SH', 'patternEpisode': None, 'buyPoint': {}}
ph.attach_history([again_item], seed, '20261030')
check('再次入选返回完整历史标签和覆盖边界', len(again_item['patternHistory']) == 1
      and all(again_item['patternHistory'][0].get(k) not in (None, '') for k in (
          'gestationStart', 'gestationEnd', 'patternType', 'breakoutDate', 'breakoutPoint',
          'pivot', 'referenceHigh', 'originQualificationNote'))
      and again_item['patternHistoryCoverage']['fullMarketComplete'] is False, again_item)

# 漏斗三轨共用同一对象字段，不另造名单。
funnel_item = {
    'code': '601985.SH', 'name': '中国核电', 'sector': '电力', 'pattern': '底部平台型',
    'inPool': True, 'star': False, 'entryTier': 'qualified', 'defects': [],
    'buyPoint': {'pivot': 9.21, 'distanceToPivotPct': -2.2, 'breakoutRemainingDays': 1},
    'patternEpisode': None, 'patternHistory': again_item['patternHistory'],
    'patternHistoryCoverage': again_item['patternHistoryCoverage'],
    'vcpGestation': nuclear_gate, 'gestationPass': True,
}
funnel_data = {'longWindow': {'window': 'half'}, 'vcpStocks': {'items': [funnel_item]}}
ud.build_funnel(funnel_data)
funnel_row = next(s for s in funnel_data['funnel']['steps'] if s['key'] == 'vcp')['rows'][0]
check('漏斗传递事件历史孕育与退出字段', funnel_row['track'] == 'reserve'
      and funnel_row['patternHistory'] == again_item['patternHistory']
      and funnel_row['patternHistoryCoverage'] == again_item['patternHistoryCoverage']
      and funnel_row['vcpGestation'] == nuclear_gate and funnel_row['gestationPass'] is True
      and funnel_row['breakoutRemainingDays'] == 1
      and all(k in funnel_row for k in ('patternEpisode', 'breakoutDate', 'breakoutExitDate')), funnel_row)

# 原杯柄/平台/底部高位门源码仍在；VCP旧快照必须同时具有日线与孕育新证据。
source = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
check('杯柄历史高位门与平台底部一年高位门保留', source.count('_apply_cup_history_eligibility(') == 4
      and 'def _cup_history_position_gate' in source and 'if ext_high:' in source
      and 'for evidence in (plat, bottom):' in source
      and "if pattern != 'VCP收缩型':\n                        _apply_post_breakout_position_defect" in source)
check('杯柄5日门未被VCP底部10日门替换', 'CUP_SIGNAL_MAX_AGE = 5' in source
      and 'PATTERN_BREAKOUT_MAX_TRADING_DAYS = 10' in (ROOT / 'scripts/pattern_history.py').read_text(encoding='utf-8')
      and "if main_lv.get('patternEpisode'):" in source and 'elif main_lv.get(\'breakout\'):' in source)
ui = ''.join((ROOT / p).read_text(encoding='utf-8') for p in (
    'src/sections/patternEvidence.ts', 'src/sections/PatternHistoryLabel.tsx',
    'src/sections/ECIPanel.tsx', 'src/sections/WeeklySummary.tsx', 'src/hooks/useFundData.ts'))
check('前端旧VCP缺孕育证据不得展示', 'item.vcpGestation?.pass === true && item.gestationPass === true' in ui)
check('总览工具共用历史组件且包含全部指定字段', ui.count("import PatternHistoryLabel from './PatternHistoryLabel'") == 2
      and '<PatternHistoryLabel records={it.patternHistory}' in ui
      and '<PatternHistoryLabel records={r.patternHistory}' in ui
      and all(x in ui for x in ('历史入选记录', '孕育', '形态类型', '突破日', '突破点/枢轴价',
                                '参考高', '覆盖边界', '非当时正式入选')))
check('公开文案保留旧趋势文本并追加新高横盘规则', '日线收盘>MA50且MA50>MA150>MA200；VCP不限制接近新高' in ui
      and '孕育期内不得先于最终突破创出新高' in ui and '横盘仅为优选' in ui
      and '满10个交易日后退出' in source and 'droppedByVcpGestation' in source)

production_after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in PRODUCTION}
check('生产两份fund_data测试前后SHA不变', production_before == production_after,
      {'before': production_before, 'after': production_after})
failed = [c['name'] for c in checks if not c['passed']]
summary = {
    'task': 114, 'allPassed': not failed, 'checksPassed': len(checks) - len(failed),
    'checksTotal': len(checks), 'failed': failed, 'dataSha256': DATA_SHA256,
    'productionFundDataSha256': production_after, 'pitOnly': True,
    'manualDispatch': False, 'productionDataRegenerated': False,
    'seed': 'scripts/pattern_episode_seed.json',
    'seedSha256': hashlib.sha256((ROOT / 'scripts/pattern_episode_seed.json').read_bytes()).hexdigest(),
}
report = {'summary': summary, 'checks': checks,
          'productionSha256': hashlib.sha256((ROOT / 'scripts/update_data.py').read_bytes()).hexdigest(),
          'historySha256': hashlib.sha256((ROOT / 'scripts/pattern_history.py').read_bytes()).hexdigest(),
          'realCases': {'shenhuaReject': candidate_view(shenhua_reject),
                        'shenhuaNear': candidate_view(shenhua_near),
                        'nuclearOrigin': candidate_view(nuclear_fixed),
                        'nuclearEpisode': seed_episode}}
(ROOT / 'zz_regress114_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(ROOT / 'zz_regress114_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if failed:
    print('失败检查:', json.dumps(failed, ensure_ascii=False, indent=2))
raise SystemExit(1 if failed else 0)
