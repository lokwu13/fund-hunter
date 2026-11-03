# -*- coding: utf-8 -*-
"""任务96：38个用户样本的PIT基线/终版审计；不做收益或市场胜率回测。"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import zz_regress23_83 as r23

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent
SAMPLE_PATH = ROOT / 'scripts' / 'pattern_samples.json'


def bars_of(rows):
    return [(r[0], r[2], r[3], r[1], r[4]) for r in rows]


def scan(ud, rows, mv_yi=None):
    """复刻生产分类优先级及全部展示门，返回所有候选供拒绝原因审计。"""
    bars = bars_of(rows)
    if len(bars) < 70:
        return None, {'rejectReasons': ['历史不足70交易日']}
    # 任务97起与生产一致：所有形态共用周MA150/200状态门；旧模块无此函数时保持旧基线。
    if hasattr(ud, '_weekly_ma150_200_display_gate'):
        weekly_ma = ud._cup_weekly_trend(bars)
        weekly_ma_gate = ud._weekly_ma150_200_display_gate(weekly_ma)
        if weekly_ma_gate['state'] == 'bearish':
            return None, {'rejectReasons': [weekly_ma_gate['reason']],
                          'weeklyMA': weekly_ma, 'weeklyMAGate': weekly_ma_gate}
    closes250 = [r[1] for r in rows[-250:]]
    hist_pct = ud._pct_rank100(closes250, rows[-1][1])
    dist_high250 = (rows[-1][1] / max(closes250) - 1) * 100
    tt = ud._trend_template(rows)
    pf = ud._vcp_platform(bars, max_amp=0.105, tail_vol_max=ud.PATTERN_TAIL_VOL_MAX,
                          rise_max=0.20, trend60_min=-0.10, dist_gate=(-5.0, 12.0))
    fl = ud._flag_pattern(bars)
    if hasattr(ud, '_platform_vcp_attribute'):
        d_lv = ud._vcp_level_strict(bars, ud.VCP_DAILY_WIN, ud.VCP_DAILY_K, max_dd=0.15,
                                    max_contraction=8.0, dist_high250=dist_high250, hist_pct=hist_pct,
                                    practical=True)
        w_lv = ud._vcp_level_strict(ud._resample_weekly(rows), ud.VCP_WEEK_WIN, ud.VCP_WEEK_K,
                                    max_dd=0.15, max_contraction=8.0,
                                    dist_high250=dist_high250, hist_pct=hist_pct, practical=True)
        platform_vcp = ud._platform_vcp_attribute(bars, pf, hist_pct, dist_high250)
        if platform_vcp and platform_vcp['formed']:
            pf = dict(pf)
            pf['vcpAttribute'] = platform_vcp
    else:
        d_lv = ud._vcp_level_strict(bars, ud.VCP_DAILY_WIN, ud.VCP_DAILY_K, max_dd=0.15,
                                    max_contraction=8.0, dist_high250=dist_high250, hist_pct=hist_pct)
        w_lv = ud._vcp_level_strict(ud._resample_weekly(rows), ud.VCP_WEEK_WIN, ud.VCP_WEEK_K,
                                    max_dd=0.15, max_contraction=8.0,
                                    dist_high250=dist_high250, hist_pct=hist_pct)
    d_c3 = bool(d_lv and d_lv['formed'])
    w_c3 = bool(w_lv and w_lv['formed'])
    ch = ud._cup_handle_strict(bars, True, dist_high250=dist_high250,
                               hist_pct=hist_pct, allow_weekly_defect=True)
    recent = ud._cup_early_breakout(bars) if not (d_c3 or w_c3) else None
    lp = ud._long_platform(bars, circ_mv=mv_yi, hist_pct=hist_pct, dist_high250=dist_high250)
    raw, main_lv, pattern = None, None, None
    reasons = []
    if d_c3 or w_c3:
        raw, main_lv = 'VCP收缩型', (d_lv if d_c3 else w_lv)
        if not tt['pass']:
            reasons.append('VCP结构候选被Stage 2趋势模板拦截')
            raw, main_lv = None, None
    elif recent and recent.get('displayEligible'):
        raw, main_lv = '杯柄型', recent
        ch = recent
    elif ch and ch['formed'] and ch.get('displayEligible') and not (dist_high250 > -7 and hist_pct is not None and hist_pct > 60):
        raw, main_lv = '杯柄型', ch
    elif ch and ch.get('formed') and not ch.get('displayEligible'):
        reasons.append(ch.get('historyExclusionReason') or '距历史高点不足8%')
    elif ch and ch.get('formed'):
        reasons.append('普通杯柄被贴新高中高位位置门拦截')
    elif lp and lp['formed']:
        raw, main_lv = '长平台整理', lp
    if raw is None:
        ext_high = ((hist_pct is not None and hist_pct > 85)
                    or (dist_high250 > -7 and hist_pct is not None and hist_pct > 60))
        if ext_high:
            reasons.append('平台/旗形被一年极高位或贴新高中高位门拦截')
        elif fl and fl['formed'] and -5.0 <= fl['distPct'] <= ud.VCP_SHOW_DIST:
            pattern, main_lv = '旗形整理', fl
        elif pf and pf['formed']:
            if ((hist_pct is not None and hist_pct <= 40) or dist_high250 <= -20):
                pattern = '底部整理'
            elif hist_pct is not None and hist_pct <= 60:
                pattern = '平台整理'
            else:
                reasons.append('窄幅平台被分位>60门拦截')
            if pattern:
                plat = bars[-pf['days']:]
                vol50 = sum(b[4] for b in bars[-50:]) / min(50, len(bars))
                main_lv = dict(pf)
                main_lv['invalidation'] = round(min(b[2] for b in plat), 2)
                main_lv['volConfirm'] = round(vol50 * ud.BREAKOUT_VOL_X, 1)
        elif fl and fl.get('formed'):
            reasons.append('旗形结构存在但距枢轴超展示窗')
    else:
        pattern = raw
    if main_lv:
        ud._apply_post_breakout_position_defect(main_lv, hist_pct, dist_high250)
        if main_lv.get('breakout'):
            if not ud._cup_signal_displayable(main_lv):
                reasons.append(f"首次信号年龄{main_lv.get('breakoutAge')}或失效位/距离不满足当前展示门")
                pattern = None
        else:
            lim = 12.0 if pattern in ('底部整理', '平台整理', '长平台整理') else (
                (12.0 if main_lv.get('structureFuzzy') else ud.CUP_SHOW_DIST)
                if pattern == '杯柄型' else 8.0)
            if not (-5.0 <= main_lv['distPct'] <= lim):
                reasons.append(f"{pattern}距枢轴{main_lv.get('distPct')}%超展示窗-5~{lim}%")
                pattern = None
    if not pattern and not reasons:
        reasons.append('各候选未同时满足完整结构与展示门')
    diag = {
        'pct': round(hist_pct, 1) if hist_pct is not None else None,
        'distHigh250': round(dist_high250, 2),
        'trendTemplate': tt,
        'vcpDaily': d_lv, 'vcpWeekly': w_lv,
        'platform': pf, 'flag': fl, 'longPlatform': lp,
        'regularCup': ch, 'recentCup': recent,
        'main': main_lv if pattern else None,
        'signalDisplayable': ud._cup_signal_displayable(recent) if recent else None,
        'rejectReasons': reasons,
    }
    return pattern, diag


def expected_pass(sample, pattern):
    mode = sample['labelMode']
    expected = sample.get('expectedCategories') or []
    forbidden = sample.get('forbiddenCategories') or []
    if mode in ('strict', 'valid_form'):
        return pattern in expected
    if mode == 'forbid_only':
        return pattern not in forbidden
    if mode == 'strict_and_forbid':
        return pattern in expected and pattern not in forbidden
    raise ValueError(f"unknown labelMode: {mode}")


def load_inputs():
    case_map = {label: (rows, mv) for label, rows, mv in r23.cases()}
    # 近期缓存有些股票只有300行，不能用来伪装杯柄200周历史不足；与真实长缓存按日期合并。
    long_cache = json.loads((WORK / 'vcp_cache_1027.json').read_text(encoding='utf-8'))['stock_daily']
    current_path = ROOT / 'scripts' / 'cache' / 'vcp_cache.json'
    current = json.loads(current_path.read_text(encoding='utf-8'))['stock_daily']
    cache = {}
    for code in set(long_cache) | set(current):
        merged = {r[0]: r for r in (long_cache.get(code) or []) + (current.get(code) or [])}
        cache[code] = [merged[d] for d in sorted(merged)]
    real95 = json.loads((ROOT / 'zz_real95_asof1029.json').read_text(encoding='utf-8'))['rows']
    rows600795 = json.loads((ROOT / 'zz_600795_full_rows92.json').read_text(encoding='utf-8'))
    return case_map, cache, real95, rows600795


def compact_cup(cup):
    if not cup:
        return None
    keys = ('days', 'totalDays', 'cupDepth', 'amplitude', 'tailRatio', 'volRatio',
            'rimDate', 'rimHigh', 'bottomDate', 'cupLow', 'segmentBasis',
            'bottomZoneDays', 'bottomZonePct', 'bottomZoneLimit', 'handlePosition',
            'pivotRecovery', 'rightSideOvershootPct', 'pivot', 'distPct', 'defects',
            'structureFuzzy', 'qualified', 'anchorDate',
            'cupStart', 'cupEnd', 'handleStart', 'handleEnd', 'signalDate',
            'signalType', 'breakoutAge', 'currentDist', 'currentValid')
    return {k: cup.get(k) for k in keys if k in cup}


def audit(module):
    library = json.loads(SAMPLE_PATH.read_text(encoding='utf-8'))
    case_map, cache, real95, rows600795 = load_inputs()
    rows_out, missing = [], []
    for sample in library['samples']:
        rows, mv = None, None
        if sample.get('sourceCase'):
            rows, mv = case_map[sample['sourceCase']]
        elif sample.get('source') == 'current_cache':
            rows = cache.get(sample['code'])
        elif sample.get('source') == 'real95':
            rows = real95.get(sample['code'])
        elif sample.get('source') == 'rows600795':
            rows = rows600795
        if not sample.get('sourceCase'):
            # 无PIT市值时不得拿后来的daily_basic快照倒填；保守关闭长平台分支并单独披露。
            mv = 0
        if not rows:
            missing.append({'id': sample['id'], 'code': sample['code'], 'reason': '无OHLCV数据'})
            rows_out.append({'id': sample['id'], 'code': sample['code'], 'dataAvailable': False,
                             'valid': None, 'currentCategory': None})
            continue
        pit_rows = [r for r in rows if r[0] <= sample['asOf']]
        if len(pit_rows) < 70:
            missing.append({'id': sample['id'], 'code': sample['code'],
                            'reason': f'PIT历史仅{len(pit_rows)}行'})
        pattern, diag = scan(module, pit_rows, mv)
        data_ok = bool(pit_rows and pit_rows[-1][0] <= sample['asOf'] and len(pit_rows) >= 70)
        result = {
            'id': sample['id'], 'code': sample['code'], 'name': sample['name'],
            'sampleClass': sample['sampleClass'], 'labelMode': sample['labelMode'],
            'asOf': sample['asOf'], 'dateRange': sample['dateRange'],
            'expectedCategories': sample.get('expectedCategories') or [],
            'forbiddenCategories': sample.get('forbiddenCategories') or [],
            'dataAvailable': data_ok, 'rows': len(pit_rows),
            'firstBar': pit_rows[0][0], 'lastBar': pit_rows[-1][0],
            'currentCategory': pattern, 'valid': expected_pass(sample, pattern) if data_ok else None,
            'keyEvidence': {
                'pct': diag.get('pct'), 'distHigh250': diag.get('distHigh250'),
                'trendPass': (diag.get('trendTemplate') or {}).get('pass'),
                'vcpDaily': diag.get('vcpDaily'), 'vcpWeekly': diag.get('vcpWeekly'),
                'platform': diag.get('platform'), 'flag': diag.get('flag'),
                'longPlatform': diag.get('longPlatform'),
                'regularCup': compact_cup(diag.get('regularCup')),
                'recentCup': compact_cup(diag.get('recentCup')),
                'signalDisplayable': diag.get('signalDisplayable'),
            },
            'rejectReasons': diag.get('rejectReasons') or [],
        }
        rows_out.append(result)
        print(sample['id'], sample['code'], sample['asOf'], 'rows', len(pit_rows),
              'last', pit_rows[-1][0], 'pattern', pattern, 'valid', result['valid'], flush=True)
    stats = {}
    for group in ('杯柄严格样本', '形态有效但可不同标签', '明确反例'):
        subset = [r for r in rows_out if r.get('sampleClass') == group]
        stats[group] = {'total': len(subset), 'valid': sum(r['valid'] is True for r in subset),
                        'invalid': sum(r['valid'] is False for r in subset),
                        'unverified': sum(r['valid'] is None for r in subset)}
    confusion = {
        'strictCupMisses': [r['id'] for r in rows_out if r.get('sampleClass') == '杯柄严格样本' and r['valid'] is False],
        'strictCupMislabeledVcp': [r['id'] for r in rows_out if r.get('sampleClass') == '杯柄严格样本' and r.get('currentCategory') == 'VCP收缩型'],
        'validFormMisses': [r['id'] for r in rows_out if r.get('sampleClass') == '形态有效但可不同标签' and r['valid'] is False],
        'validFormAsVcp': [r['id'] for r in rows_out if r.get('sampleClass') == '形态有效但可不同标签' and r.get('currentCategory') == 'VCP收缩型'],
        'negativeViolations': [r['id'] for r in rows_out if r.get('sampleClass') == '明确反例' and r['valid'] is False],
        'categoryCounts': dict(Counter(r.get('currentCategory') for r in rows_out)),
    }
    source = (ROOT / 'scripts' / 'update_data.py').read_bytes()
    return {
        'sampleLibraryVersion': library['version'], 'sampleCount': len(library['samples']),
        'productionSha256': hashlib.sha256(source).hexdigest(),
        'pitOnly': True, 'notMarketWinRate': True,
        'pitMarketCapPolicy': 'sourceCase使用样本自带历史市值；其他样本无PIT市值时长平台保守拒绝，不倒填后续快照',
        'structuralConflicts': [{'id': 'C11', 'handlePositionPct': 38.46,
                                 'reason': '指定12日柄含20260818低点4.89；杯沿5.37/杯底4.59下低于50%硬门，未放宽'}],
        'stats': stats, 'confusion': confusion, 'missingData': missing, 'rows': rows_out,
    }


def boundary_checks(ud):
    """通用门槛边界测试，不使用任何股票或日期分支。"""
    body2 = [('d1', 10.2, 9.70, 9.8, 100), ('d2', 10.1, 9.71, 9.9, 100),
             ('d3', 10.4, 10.2, 10.3, 100)]
    body3 = [('d1', 10.2, 9.70, 9.8, 100), ('d2', 10.1, 9.80, 9.9, 100),
             ('d3', 10.2, 9.90, 10.0, 100), ('d4', 10.4, 10.2, 10.3, 100)]
    shape2 = ud._cup_shape_gate(body2, 9.70)
    shape3 = ud._cup_shape_gate(body3, 9.70)
    tail_at_cap = 1350.0 / 3.65  # [400,300,200,100,x]的末段/全段均量恰好1.35
    tail_ok, tail_ratio = ud._vol_shrink_ok([400, 300, 200, 100, tail_at_cap])
    tail_over, tail_over_ratio = ud._vol_shrink_ok([400, 300, 200, 100, tail_at_cap + 1.0])
    checks = {
        'cupBottomTwoDaysRejected': (not shape2['pass'] and shape2['bottomZoneDays'] == 2
                                     and bool(shape2['rejectReasons'])),
        'cupBottomThreeDaysAccepted': shape3['pass'] and shape3['bottomZoneDays'] == 3,
        'platformTolerance110Accepted': ud._platform_contraction_ok([0.10, 0.11, 0.09]),
        'platformAbove110Rejected': not ud._platform_contraction_ok([0.10, 0.111, 0.09]),
        'platformLastMustContract': not ud._platform_contraction_ok([0.10, 0.09, 0.10]),
        'tailVolume135Accepted': tail_ok and abs(tail_ratio - 1.35) <= 0.001,
        'tailVolumeAbove135Rejected': not tail_over and tail_over_ratio > 1.35,
        'sharedTailVolumeConstant': ud.PATTERN_TAIL_VOL_MAX == 1.35,
    }
    assert all(checks.values()), checks
    return {'passed': sum(checks.values()), 'total': len(checks), 'checks': checks,
            'tailAtCapRatio': tail_ratio, 'tailAboveCapRatio': tail_over_ratio,
            'shape2': shape2, 'shape3': shape3}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    import update_data as ud
    report = audit(ud)
    report['boundaryChecks'] = boundary_checks(ud)
    if args.baseline:
        path = ROOT / 'zz_audit96_baseline.json'
    else:
        path = ROOT / 'zz_regress96.json'
        baseline_path = ROOT / 'zz_audit96_baseline.json'
        if baseline_path.exists():
            baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
            before = {r['id']: r for r in baseline['rows']}
            report['beforeAfter'] = [{
                'id': r['id'], 'before': before[r['id']].get('currentCategory'),
                'after': r.get('currentCategory'), 'beforeValid': before[r['id']].get('valid'),
                'afterValid': r.get('valid')} for r in report['rows']
                if before[r['id']].get('currentCategory') != r.get('currentCategory')
                or before[r['id']].get('valid') != r.get('valid')]
            report['baselineStats'] = baseline['stats']
            report['baselineConfusion'] = baseline['confusion']
            regressed = [r['id'] for r in report['rows']
                         if before[r['id']].get('valid') is True and r.get('valid') is not True]
            # 任务97保留原valid=false证据，只允许两项明确空头政策剔除，其他回退仍失败。
            assert set(regressed) == {'A03', 'A12'}, f'非任务97基线回退: {regressed}'
        by_id = {r['id']: r for r in report['rows']}
        assert all(by_id[s]['rejectReasons'] == ['周MA150<MA200空头排列']
                   for s in ('A03', 'A12', 'C01', 'C04', 'N01'))
        assert not report['missingData'], report['missingData']
        assert report['confusion']['negativeViolations'] == ['N01'], report['confusion']['negativeViolations']
        assert all(r['dataAvailable'] for r in report['rows'])
        assert by_id['N01']['currentCategory'] is None
        assert by_id['N01']['rejectReasons'] == ['周MA150<MA200空头排列'], by_id['N01']
        assert by_id['N05']['currentCategory'] != '底部整理', by_id['N05']
        # 96b允许指定12日柄以38.46%柄位进入fuzzy，但绝不可进入干净qualified。
        c11 = by_id['C11']['keyEvidence']['regularCup']
        assert (by_id['C11']['currentCategory'] == '杯柄型' and c11
                and c11.get('days') == 12 and c11.get('handleStart') == '20260804'
                and c11.get('handleEnd') == '20260819'
                and abs(c11.get('handlePosition') - 0.385) < 0.001
                and c11.get('defects')), by_id['C11']
        c10 = by_id['C10']['keyEvidence']['recentCup']
        assert c10 and c10.get('signalDate') == '20260902', by_id['C10']
        n12_recent = by_id['N12']['keyEvidence']['recentCup']
        assert (by_id['N12']['currentCategory'] is None and n12_recent
                and n12_recent.get('signalDate') == '20260902'
                and n12_recent.get('breakoutAge') > ud.CUP_SIGNAL_MAX_AGE
                and not by_id['N12']['keyEvidence']['signalDisplayable']), by_id['N12']
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': path.name, 'sampleCount': report['sampleCount'],
                      'stats': report['stats'], 'confusion': report['confusion'],
                      'missingData': report['missingData'],
                      'boundaryChecks': report['boundaryChecks']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
