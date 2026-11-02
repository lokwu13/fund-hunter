# -*- coding: utf-8 -*-
"""当周动态 Wilder RSI6 与真实行业/概念指数的纯计算函数。

不访问API、不读写生产数据；所有证据均可由输入行情复算。
"""
from datetime import datetime, timedelta
import statistics

import pandas as pd


def _normalized_closes(rows, trade_date):
    td = str(trade_date).replace('-', '')
    by_date = {}
    for row in rows or []:
        try:
            date = str(row[0]).replace('-', '')
            close = float(row[1])
            if len(date) == 8 and date <= td and close > 0:
                by_date[date] = close
        except (IndexError, TypeError, ValueError):
            continue
    return [[date, by_date[date]] for date in sorted(by_date)]


def _week_series(rows, trade_date):
    """按ISO周取最后真实收盘；输入可为五字段OHLCV或三字段[date,close,vol]。"""
    weeks = {}
    for date, close in _normalized_closes(rows, trade_date):
        week = pd.to_datetime(date, format='%Y%m%d').strftime('%G%V')
        weeks[week] = [week, date, close]
    return [weeks[key] for key in sorted(weeks)]


def weekly_rsi6_evidence(rows, trade_date, rsi_func):
    """当周动态Wilder RSI6<=20即通过；完成周上穿只保留为历史证据，不再开窗。"""
    td = str(trade_date).replace('-', '')
    timestamp = pd.to_datetime(td, format='%Y%m%d')
    current_week = timestamp.strftime('%G%V')
    expected_week = (timestamp - pd.Timedelta(days=7)).strftime('%G%V')
    normalized = _normalized_closes(rows, td)
    weekly = _week_series(rows, td)
    completed = [bar for bar in weekly if bar[0] != current_week]
    closes = [bar[2] for bar in completed]
    rsi = rsi_func(closes, 6) if closes else []
    current = rsi[-1] if rsi else None
    previous = rsi[-2] if len(rsi) >= 2 else None
    rsi_date = completed[-1][1] if completed and current is not None else None
    previous_date = completed[-2][1] if len(completed) >= 2 and previous is not None else None
    daily_date = normalized[-1][0] if normalized else None
    actual_week = pd.to_datetime(rsi_date, format='%Y%m%d').strftime('%G%V') if rsi_date else None
    fresh = bool(daily_date == td and actual_week == expected_week)
    crossed = bool(fresh and previous is not None and current is not None
                   and previous <= 20 and current > 20)

    live_rsi = rsi_func([bar[2] for bar in weekly], 6) if weekly else []
    dynamic = live_rsi[-1] if live_rsi else None
    dynamic_date = weekly[-1][1] if weekly and weekly[-1][0] == current_week and dynamic is not None else None
    dynamic_fresh = bool(daily_date == td and dynamic_date == td)
    in_zone = bool(dynamic_fresh and dynamic is not None and dynamic <= 20)
    dynamic_watch = bool(dynamic_fresh and dynamic is not None and dynamic > 20)
    if not normalized:
        reason = '真实指数行情为空'
    elif dynamic is None:
        reason = '周线不足，无法计算当周动态Wilder RSI6'
    elif not dynamic_fresh:
        reason = f'当周动态RSI6行情不新鲜：日线{daily_date or "无"}，要求本批有效日{td}'
    elif in_zone:
        reason = f'当周动态RSI6进入20以下区域：{dynamic_date} RSI6={dynamic:.2f}≤20；周内会变化'
    else:
        reason = f'当周动态RSI6={dynamic:.2f}>20，不在20以下区域，不开窗'
    if crossed:
        reason += f'；完成周上穿仅作历史证据：{previous_date} {previous:.2f}≤20 → {rsi_date} {current:.2f}>20'
    return {
        'dailyDate': daily_date,
        'weeklyRsiDate': rsi_date, 'previousWeeklyRsiDate': previous_date,
        'weeklyRsi': round(current, 2) if current is not None else None,
        'previousWeeklyRsi': round(previous, 2) if previous is not None else None,
        'weeklyRsi6': round(current, 2) if current is not None else None,
        'previousWeeklyRsi6': round(previous, 2) if previous is not None else None,
        'dynamicWeeklyRsi6': round(dynamic, 2) if dynamic is not None else None,
        'dynamicWeeklyRsiDate': dynamic_date,
        'weeklyFresh': fresh, 'dynamicWeeklyFresh': dynamic_fresh,
        'rsiPass': in_zone, 'inOversoldZone': in_zone, 'weeklyCross20': crossed,
        'dynamicWatch': dynamic_watch, 'completedWeekCount': len(completed),
        'rsiReason': reason,
    }


def direction_rsi6_metrics(rows, trade_date, rsi_func):
    evidence = weekly_rsi6_evidence(rows, trade_date, rsi_func)
    normalized = _normalized_closes(rows, trade_date)
    closes = [row[1] for row in normalized]
    daily = rsi_func(closes, 6) if closes else []
    daily_rsi = daily[-1] if daily else None

    def drawdown(n):
        if len(closes) < n:
            return None
        return round((closes[-1] / max(closes[-n:]) - 1) * 100, 2)

    return {**evidence,
            'dailyRsi6': round(daily_rsi, 2) if daily_rsi is not None else None,
            'drawdown20Pct': drawdown(20), 'drawdown60Pct': drawdown(60),
            'dailyRows': len(normalized)}


def _number(value):
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_direction_groups(specs, index_daily, trade_date, rsi_func, records=None,
                           stock_info=None, circ_mv=None, mine_watch=None,
                           market_pe=None, market_pb=None):
    """RSI6决定入榜与排序；估值只作参考，daily_basic缺失时以circ_mv披露降级。"""
    records = records or {}
    stock_info = stock_info or {}
    circ_mv = circ_mv or {}
    mine_watch = mine_watch or {}
    mine_map = {x.get('code'): x for x in mine_watch.get('items') or []}
    checked_codes = set(mine_watch.get('checkedCodes') or []) | set(mine_map)
    market_pe = sorted(x for x in (market_pe or []) if x is not None and x > 0)
    market_pb = sorted(x for x in (market_pb or []) if x is not None and x > 0)
    groups, insufficient = [], []
    for spec in specs:
        metrics = direction_rsi6_metrics((index_daily or {}).get(spec['code']) or [], trade_date, rsi_func)
        members = sorted(spec.get('members') or [])
        coverage = {'type': spec['type'], 'code': spec['code'], 'name': spec['name'],
                    'memberCount': len(members)}
        if not metrics['weeklyFresh'] or metrics['weeklyRsi6'] is None or metrics['previousWeeklyRsi6'] is None:
            insufficient.append({**coverage, 'dailyRows': metrics['dailyRows'],
                                 'weeklyRsiDate': metrics['weeklyRsiDate'],
                                 'reason': metrics['rsiReason']})
            continue
        rows = [records[code] for code in members if code in records]
        pe_values = [r['peTtm'] for r in rows if r.get('peTtm') is not None and r['peTtm'] > 0]
        pb_values = [r['pb'] for r in rows if r.get('pb') is not None and r['pb'] > 0]
        common = [r for r in rows if r.get('peTtm') is not None and r['peTtm'] > 0
                  and r.get('pb') is not None and r['pb'] > 0]
        pe_median = float(statistics.median(pe_values)) if pe_values else None
        pb_median = float(statistics.median(pb_values)) if pb_values else None
        pe_pct = (sum(v <= pe_median for v in market_pe) / len(market_pe) * 100
                  if pe_median is not None and market_pe else None)
        pb_pct = (sum(v <= pb_median for v in market_pb) / len(market_pb) * 100
                  if pb_median is not None and market_pb else None)

        if records:
            leader_rows = sorted((r for r in rows if r.get('totalMv') is not None),
                                 key=lambda r: (-r['totalMv'], r['code']))[:2]
            leader_sort = 'daily_basic.total_mv总市值降序，代码升序打破并列'
        else:
            fallback = []
            for code in members:
                value = _number(circ_mv.get(code))
                if value is not None:
                    fallback.append({'code': code, 'tradeDate': None, 'close': None,
                                     'totalMv': None, 'peTtm': None, 'pb': None, 'circMv': value})
            leader_rows = sorted(fallback, key=lambda r: (-r['circMv'], r['code']))[:2]
            leader_sort = 'daily_basic缺失；vcp_cache.circ_mv既有流通市值降序，代码升序打破并列（非总市值）'

        leaders = []
        for row in leader_rows:
            code = row['code']
            name = str((stock_info.get(code) or {}).get('name') or code)
            mine = mine_map.get(code)
            covered = code in checked_codes
            mine_types = list((mine or {}).get('types') or [])
            mine_details = list((mine or {}).get('details') or [])
            mine_note = (('既有排雷命中：' + '、'.join(mine_types)) if mine else
                         '既有排雷已覆盖，未命中既有规则（不代表无风险）' if covered else '既有排雷未覆盖')
            pe = _number(row.get('peTtm'))
            pb = _number(row.get('pb'))
            total_mv = _number(row.get('totalMv'))
            cached_circ = _number(circ_mv.get(code))
            leaders.append({
                'code': code, 'name': name, 'close': _number(row.get('close')),
                'peTtm': round(pe, 4) if pe is not None else None,
                'pb': round(pb, 4) if pb is not None else None,
                'peStatus': '估值快照缺失' if pe is None else
                            '亏损/非正PE，未计入组内PE中位数' if pe <= 0 else '有效PE',
                'pbStatus': '估值快照缺失' if pb is None else '有效PB',
                'totalMv': round(total_mv, 2) if total_mv is not None else None,
                'totalMvYi': round(total_mv / 10000, 2) if total_mv is not None else None,
                'circMv': round(cached_circ, 4) if cached_circ is not None else None,
                'isST': 'ST' in name.upper(), 'tradeDate': row.get('tradeDate'),
                'mineCovered': covered, 'mineTypes': mine_types, 'mineDetails': mine_details,
                'mineNote': mine_note,
            })
        leader_note = ('可用市值成员不足2只，仅展示实际可用的'
                       f'{len(leaders)}只；不以无市值股票补足' if len(leaders) < 2 else leader_sort)
        common_coverage = len(common) / len(members) if members else 0.0
        groups.append({
            **coverage, **metrics,
            'snapshotCount': len(rows), 'missingSnapshotCount': len(members) - len(rows),
            'peCount': len(pe_values), 'pbCount': len(pb_values), 'commonCount': len(common),
            'commonCoverage': round(common_coverage, 4),
            'lossPeCount': sum(r.get('peTtm') is not None and r['peTtm'] <= 0 for r in rows),
            'peTtmMedian': round(pe_median, 4) if pe_median is not None else None,
            'pbMedian': round(pb_median, 4) if pb_median is not None else None,
            'peCrossPct': round(pe_pct, 1) if pe_pct is not None else None,
            'pbCrossPct': round(pb_pct, 1) if pb_pct is not None else None,
            'oversoldPriority': bool(metrics['weeklyRsi6'] <= 20 or metrics['weeklyCross20']),
            'leaders': leaders, 'leaderNote': leader_note, 'leaderSortMethod': leader_sort,
            'valuationReferenceOnly': True,
            'reason': (f"周RSI6 {metrics['previousWeeklyRsi6']:.2f}→{metrics['weeklyRsi6']:.2f}，"
                       f"日RSI6={metrics['dailyRsi6'] if metrics['dailyRsi6'] is not None else '缺失'}；"
                       '按周RSI6升序，估值不参与入围'),
        })
    groups.sort(key=lambda g: (g['weeklyRsi6'],
                               g['dailyRsi6'] if g['dailyRsi6'] is not None else 999,
                               g['type'], g['code']))
    return {
        'industries': [g for g in groups if g['type'] == 'industry'],
        'concepts': [g for g in groups if g['type'] == 'concept'],
        'insufficientGroups': insufficient,
        'evaluatedGroupCount': len(specs),
        'rsiInsufficientGroupCount': len(insufficient),
        'insufficientCoverageGroupCount': sum(g['commonCount'] < 5 or g['commonCoverage'] < 0.60 for g in groups),
        'highValuationGroupCount': sum((g['peCrossPct'] is not None and g['peCrossPct'] > 20)
                                       or (g['pbCrossPct'] is not None and g['pbCrossPct'] > 20)
                                       for g in groups),
    }
