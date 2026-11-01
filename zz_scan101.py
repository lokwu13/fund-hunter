# -*- coding: utf-8 -*-
"""任务101生产忠实扫描：任务99分类链+等待期失效门+杯柄展示失败回退。"""
import zz_regress96 as r96


def scan(ud, rows, mv_yi=None):
    bars = r96.bars_of(rows)
    if len(bars) < 70:
        return None, {'rejectReasons': ['历史不足70交易日']}
    weekly_ma = ud._cup_weekly_trend(bars)
    weekly_gate = ud._weekly_ma150_200_display_gate(weekly_ma)
    if weekly_gate['state'] == 'bearish':
        return None, {'rejectReasons': [weekly_gate['reason']],
                      'weeklyMA': weekly_ma, 'weeklyMAGate': weekly_gate}
    closes250 = [r[1] for r in rows[-250:]]
    hist_pct = ud._pct_rank100(closes250, rows[-1][1])
    dist_high250 = (rows[-1][1] / max(closes250) - 1) * 100
    tt = ud._trend_template(rows)
    pf = ud._vcp_platform(bars, max_amp=0.105, tail_vol_max=ud.PATTERN_TAIL_VOL_MAX,
                          rise_max=0.20, trend60_min=-0.10, dist_gate=(-5.0, 12.0), practical=True,
                          dist_high250=dist_high250)
    fl = ud._flag_pattern(bars)
    d_lv = ud._vcp_level_strict(bars, ud.VCP_DAILY_WIN, ud.VCP_DAILY_K, max_dd=0.15,
                                max_contraction=8.0, dist_high250=dist_high250, hist_pct=hist_pct,
                                practical=True)
    w_lv = ud._vcp_level_strict(ud._resample_weekly(rows), ud.VCP_WEEK_WIN, ud.VCP_WEEK_K,
                                max_dd=0.15, max_contraction=8.0,
                                dist_high250=dist_high250, hist_pct=hist_pct, practical=True)
    fixed_lv = ud._vcp_fixed_base(bars)
    platform_vcp = ud._platform_vcp_attribute(bars, pf, hist_pct, dist_high250)
    if platform_vcp and platform_vcp['formed']:
        pf = dict(pf)
        pf['vcpAttribute'] = platform_vcp
    d_c3 = bool(d_lv and d_lv['formed'])
    w_c3 = bool(w_lv and w_lv['formed'])
    f_c3 = bool(fixed_lv and fixed_lv['formed'])
    ch = ud._cup_handle_strict(bars, True, dist_high250=dist_high250,
                               hist_pct=hist_pct, allow_weekly_defect=True)
    recent = ud._cup_early_breakout(bars) if not (d_c3 or w_c3) else None
    lp = ud._long_platform(bars, circ_mv=mv_yi, hist_pct=hist_pct, dist_high250=dist_high250)

    def non_cup_fallback(after_cup=False):
        if (after_cup and lp and lp['formed'] and -5.0 <= lp['distPct'] <= 12.0):
            return '长平台整理', lp
        ext_high = ((hist_pct is not None and hist_pct > 85)
                    or (dist_high250 > -7 and hist_pct is not None and hist_pct > 60))
        if ext_high:
            return None, None
        if fl and fl['formed'] and -5.0 <= fl['distPct'] <= ud.VCP_SHOW_DIST:
            return '旗形整理', fl
        if pf and pf['formed']:
            internal_bottom = pf.get('type') == '底部平台型' and dist_high250 <= -15
            if (hist_pct is not None and hist_pct <= 40) or dist_high250 <= -20 or internal_bottom:
                pattern = '底部整理'
            elif hist_pct is not None and hist_pct <= 60:
                pattern = '平台整理'
            else:
                return None, None
            plat = bars[-pf['days']:]
            vol50 = sum(b[4] for b in bars[-50:]) / min(50, len(bars))
            main = dict(pf)
            main['invalidation'] = round(min(b[2] for b in plat), 2)
            main['volConfirm'] = round(vol50 * ud.BREAKOUT_VOL_X, 1)
            return pattern, main
        return None, None

    raw, main_lv, pattern = None, None, None
    reasons = []
    if d_c3 or w_c3:
        swing_lv = d_lv if d_c3 else w_lv
        if tt['pass']:
            raw, main_lv = 'VCP收缩型', swing_lv
        else:
            reasons.append('VCP结构候选被Stage 2趋势模板拦截')
    if raw is None and recent:
        raw, main_lv = '杯柄型', recent
        ch = recent
    elif raw is None and ch and ch['formed'] and not (dist_high250 > -7 and hist_pct is not None and hist_pct > 60):
        raw, main_lv = '杯柄型', ch
    elif raw is None and ch and ch.get('formed'):
        reasons.append('普通杯柄被贴新高中高位位置门拦截')
    elif raw is None and f_c3:
        raw, main_lv = 'VCP收缩型', fixed_lv
    elif raw is None and lp and lp['formed']:
        raw, main_lv = '长平台整理', lp
    if raw is None:
        pattern, main_lv = non_cup_fallback()
        if not main_lv:
            ext_high = ((hist_pct is not None and hist_pct > 85)
                        or (dist_high250 > -7 and hist_pct is not None and hist_pct > 60))
            reasons.append('平台/旗形被一年极高位或贴新高中高位门拦截' if ext_high
                           else '各候选未同时满足完整结构与展示门')
    else:
        pattern = raw
    display_ok = False
    fallback_used = False
    if main_lv:
        for attempt in range(2):
            ud._apply_post_breakout_position_defect(main_lv, hist_pct, dist_high250)
            if main_lv.get('breakout'):
                display_ok = ud._cup_signal_displayable(main_lv)
                if not display_ok:
                    reasons.append(f"首次信号年龄{main_lv.get('breakoutAge')}或失效位/距离不满足当前展示门")
            else:
                lim = 12.0 if pattern in ('底部整理', '平台整理', '长平台整理') else (
                    (12.0 if main_lv.get('structureFuzzy') else ud.CUP_SHOW_DIST)
                    if pattern == '杯柄型' else 8.0)
                display_ok = -5.0 <= main_lv['distPct'] <= lim
                if not display_ok:
                    reasons.append(f"{pattern}距枢轴{main_lv.get('distPct')}%超展示窗-5~{lim}%")
            if display_ok:
                break
            if attempt == 0 and pattern == '杯柄型':
                pattern, main_lv = non_cup_fallback(after_cup=True)
                if main_lv:
                    fallback_used = True
                    continue
            break
    if not display_ok:
        pattern = None
    diag = {'pct': round(hist_pct, 1) if hist_pct is not None else None,
            'distHigh250': round(dist_high250, 2), 'trendTemplate': tt,
            'vcpDaily': d_lv, 'vcpWeekly': w_lv, 'fixedBase': fixed_lv, 'platform': pf, 'flag': fl,
            'longPlatform': lp, 'regularCup': ch, 'recentCup': recent,
            'main': main_lv if pattern else None,
            'signalDisplayable': ud._cup_signal_displayable(recent) if recent else None,
            'fallbackUsed': fallback_used, 'rejectReasons': reasons}
    return pattern, diag
