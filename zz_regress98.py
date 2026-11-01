# -*- coding: utf-8 -*-
"""任务98：务实VCP、平台型VCP属性、量能均线与反例边界回归。"""
import copy
import difflib
import hashlib
import inspect
import json
from pathlib import Path
import update_data as u
import zz_regress96 as r96

ROOT = Path(__file__).resolve().parent
results = []


def check(name, condition, evidence):
    results.append({'name': name, 'pass': bool(condition), 'evidence': evidence})
    if not condition:
        raise AssertionError(f'{name}: {evidence}')


def synthetic_bars(depths, seg_vols):
    """5个摆动段；峰距10日，所有峰高100，单日收缩均≤8%由输入控制。"""
    anchors = [4, 14, 24, 34, 44, 54]
    bars = []
    for i in range(60):
        high = 90.0 + i * 0.01  # 非平台高点，避免等高点都被识别为摆动峰
        low = 94.0
        vol = 500.0
        for j, (a, b) in enumerate(zip(anchors, anchors[1:])):
            if a < i < b:
                low = 100.0 - depths[j]
                vol = seg_vols[j]
                break
        if i in anchors:
            high = 100.0
            low = 98.0
        if i > anchors[-1]:
            low = 98.0
            vol = seg_vols[-1]
        close = (high + low) / 2
        bars.append((f'd{i:02d}', high, low, close, float(vol)))
    return bars


def practical(depths, vols=(1000, 900, 800, 700, 600), enabled=True, **kwargs):
    options = {'max_dd': 0.15, 'max_contraction': 8.0,
               'dist_high250': -12.0, 'hist_pct': 45.0, 'practical': enabled}
    options.update(kwargs)
    return u._vcp_level_strict(synthetic_bars(depths, vols), 60, 2, **options)


one_reversal = practical([8, 7, 7.8, 6, 5])
check('任务103务实反复仅保留证据且不独立成型', one_reversal and not one_reversal['formed']
      and not one_reversal['decreasing'] and one_reversal['practicalDecreasing']
      and one_reversal['priceMode'] == 'practical'
      and one_reversal['structurePath'] == 'swing_evidence_only', one_reversal)
strict_blocked = practical([8, 7, 7.8, 6, 5], enabled=False)
check('同一宽松价格序列不会被旧严格路径误收', strict_blocked and not strict_blocked['formed'], strict_blocked)
two_reversals = practical([8, 6, 6.9, 5, 5.8])
check('两次温和扩张仍拒绝', two_reversals and not two_reversals['formed']
      and not two_reversals['practicalDecreasing'], two_reversals)
wide_reversal = practical([8, 6, 7.8, 5, 4])
check('单次扩张超过25%即宽幅发散拒绝', wide_reversal and not wide_reversal['formed']
      and not wide_reversal['practicalDecreasing'], wide_reversal)
check('单次收缩超过8%仍硬拒绝', practical([8.1, 7, 6, 5, 4]) is None, 'max_contraction=8')
check('临近一年新高仍硬拒绝', practical([8, 7, 7.8, 6, 5], dist_high250=-7.99) is None,
      'dist_high250=-7.99')
check('一年极高位仍硬拒绝', practical([8, 7, 7.8, 6, 5], hist_pct=85.01) is None, 'hist_pct=85.01')
ma_failure = practical([8, 7, 7.8, 6, 5], vols=(500, 100, 120, 600, 450))
check('首尾量缩但均量序列上行仍不得走务实路径', ma_failure and not ma_failure['formed']
      and ma_failure['volFirst'] > ma_failure['volLast'] and not ma_failure['volumeMA']['pass'], ma_failure)
seg_failure = practical([8, 7, 7.8, 6, 5], vols=(100, 200, 300, 400, 500))
check('阶段量能未萎缩不能仅靠均线或价格入围', seg_failure and not seg_failure['formed'], seg_failure)
strict_positive = practical([8, 7, 6, 5, 4], enabled=False)
check('严格价格证据保留但旧合成夹具被新增质量门拒绝', strict_positive and not strict_positive['formed']
      and strict_positive['priceMode'] == 'strict' and strict_positive['decreasing']
      and (not strict_positive['rightSideQuality']['pass'] or strict_positive['distPct'] > u.VCP_READY_DIST_MAX),
      strict_positive)
vol_ma = one_reversal['volumeMA']
check('多窗口均量校准独立量化', vol_ma['pass'] and vol_ma['sequenceOk']
      and vol_ma['ma10ToBase'] <= u.VCP_VOL_MA_RATIO_MAX
      and vol_ma['baseWindow'] == 50, vol_ma)

library = json.loads(r96.SAMPLE_PATH.read_text(encoding='utf-8'))
case_map, cache, real95, rows600795 = r96.load_inputs()
sample = next(x for x in library['samples'] if x['id'] == 'A04')
rows, mv = case_map[sample['sourceCase']]
pattern, diag = r96.scan(u, rows, mv)
pf = diag['platform']
attr = pf.get('vcpAttribute')
check('A04单标签保持平台整理且明确具有VCP属性', pattern == '平台整理' and attr and attr['formed']
      and not diag['trendTemplate']['pass'], {'pattern': pattern, 'attribute': attr})
check('A04实际平台区间与窄幅收缩证据', pf['days'] == 16 and rows[-16][0] == '20260326'
      and rows[-1][0] == '20260417' and pf['amplitude'] == 4.9
      and pf['segAmps'] == [4.4, 3.9, 2.5], {'first': rows[-16][0], 'last': rows[-1][0], 'platform': pf})
check('A04低位且非临近新高', attr['histPct'] == 44.8 and attr['distHigh250'] == -12.61,
      {'histPct': attr['histPct'], 'distHigh250': attr['distHigh250']})
check('A04阶段缩量与量能均线证据', attr['platformToRallyVol'] == 0.58
      and attr['volumeMA']['ma10ToBase'] == 0.709 and attr['volumeMA']['sequenceOk']
      and attr['volumeMA']['ma10'] == 4190718.4 and attr['volumeMA']['ma20'] == 4541352.6
      and attr['volumeMA']['maBase'] == 5911990.1, attr['volumeMA'])
check('A04下跌中继稳定例外透明且未取消', attr['trend60Pct'] == -12.61
      and attr['platformDriftPct'] == 2.03 and '若60日跌幅超10%' in attr['note'], attr['note'])
check('A04证据note明确平台型VCP而非伪造双标签', '平台型VCP属性' in attr['note']
      and '单标签仍为平台整理' in attr['note'], attr['note'])

high_attr = u._platform_vcp_attribute(r96.bars_of(rows), pf, 60.01, -12.61)
near_high_attr = u._platform_vcp_attribute(r96.bars_of(rows), pf, 44.8, -7.99)
check('平台VCP属性高位与临近新高边界', not high_attr['formed'] and not near_high_attr['formed'],
      {'high': high_attr['rejectReasons'], 'nearHigh': near_high_attr['rejectReasons']})
bad_stage = copy.deepcopy(pf)
bad_stage['volRatio'] = 0.76
stage_attr = u._platform_vcp_attribute(r96.bars_of(rows), bad_stage, 44.8, -12.61)
check('平台VCP阶段量超过75%拒绝', not stage_attr['formed'], stage_attr['rejectReasons'])
constant_bars = [(d, h, l, c, 100.0) for d, h, l, c, _ in r96.bars_of(rows)]
ma_attr = u._platform_vcp_attribute(constant_bars, pf, 44.8, -12.61)
check('任务103不再以机械均量排列拒绝平台属性', ma_attr['formed'] and ma_attr['volumeMA']['pass']
      and ma_attr['volumeMA']['ma10ToBase'] == 1.0 and ma_attr['recentVolumeQuality']['pass'],
      {'rejectReasons': ma_attr['rejectReasons'], 'volumeMA': ma_attr['volumeMA']})
unstable_bars = r96.bars_of(rows)
last = unstable_bars[-1]
unstable_bars[-1] = (last[0], last[1], last[2], unstable_bars[-16][3] * 0.95, last[4])
unstable_attr = u._platform_vcp_attribute(unstable_bars, pf, 44.8, -12.61)
check('明显下跌且平台漂移超过3%不得附VCP属性', not unstable_attr['formed']
      and any('明显下跌' in x for x in unstable_attr['rejectReasons']), unstable_attr)

negative = {}
for sid in ('N01', 'N02', 'N03'):
    s = next(x for x in library['samples'] if x['id'] == sid)
    rr = cache[s['code']]
    rr = [x for x in rr if x[0] <= s['asOf']]
    p, d = r96.scan(u, rr, 0)
    negative[sid] = {'pattern': p, 'rejectReasons': d.get('rejectReasons')}
check('N02与N03不得回归为VCP', all(negative[s]['pattern'] != 'VCP收缩型' for s in ('N02', 'N03')), negative)
check('南微仍先被任务97周MA空头门硬删', negative['N01']['pattern'] is None
      and negative['N01']['rejectReasons'] == ['周MA150<MA200空头排列'], negative['N01'])

source = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
check('生产note量化任务103 VCP与平台属性', all(x in source for x in (
    '任务103十例人工标签校准', '务实反复序列只留证据', '不强制MA10≤MA20≤MA50',
    '平台日均量≤前20日拉升段75%', '不伪造双标签')), 'task103 note')
check('生产分类保留VCP优先且固定区间不抢占杯柄', "raw, main_lv = 'VCP收缩型', swing_lv" in source
      and '固定区间VCP不抢占已经成立的杯柄' in source
      and source.index('if d_c3 or w_c3:') < source.index('pattern, main_lv = non_cup_fallback()'),
      'classification priority preserved')
check('生产输出包含属性、固定区间与证据note', "'vcpAttribute': main_lv.get('vcpAttribute')" in source
      and "'fixedBase': fixed_lv if main_lv is fixed_lv else None" in source
      and "'patternNote':" in source, 'item evidence')
old_source = (ROOT / 'zz_update_data_before98.py').read_text(encoding='utf-8').splitlines()
added = [x for x in difflib.ndiff(old_source, source.splitlines()) if x.startswith('+ ')]
check('未加入002648平台单日破位规则', not [x for x in added if '002648' in x or '单日-5%' in x or '单日−5%' in x],
      [x for x in added if '002648' in x])

# 以下为任务98历史审计快照，不冒充任务103当前全池结果；当前回退由zz_regress101/105另行实算。
audit = json.loads((ROOT / 'zz_audit98.json').read_text(encoding='utf-8'))
check('任务98历史固定池审计证据保持可读', audit['fixedPool']['newVcpCount'] == 0
      and audit['fixedPool']['lostVcpCount'] == 0 and not audit['fixedPool']['changes'], audit['fixedPool'])
check('任务98历史平台VCP属性仅4个且标签不变', audit['fixedPool']['platformVcpAttributeCount'] == 4
      and all(x['before'] == x['after'] for x in audit['fixedPool']['platformVcpAttributes']),
      [(x['code'], x['before'], x['after']) for x in audit['fixedPool']['platformVcpAttributes']])
check('任务98历史38样本审计证据保持可读', not audit['sampleChanges'], audit['sampleChanges'])

report = {'task': 98, 'passed': sum(x['pass'] for x in results), 'total': len(results),
          'results': results, 'notMarketWinRate': True, 'sampleExpectationsChanged': False}
(ROOT / 'zz_regress98.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'task': 98, 'passed': report['passed'], 'total': report['total']}, ensure_ascii=False))
