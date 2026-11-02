# -*- coding: utf-8 -*-
"""行业/概念自身历史估值：纯计算、可独立复算，不使用全A横截面分位。"""
import statistics


MIN_METRIC_COUNT = 5
MIN_METRIC_COVERAGE = 0.60
MIN_HISTORY_SAMPLES = 24


def group_valuation_snapshot(members, records):
    """正PE/正PB分别取中位数；亏损PE披露但不进PE中位数。"""
    members = sorted(set(members or []))
    rows = [records[code] for code in members if code in (records or {})]
    pe = [r.get('peTtm') for r in rows if r.get('peTtm') is not None and r.get('peTtm') > 0]
    pb = [r.get('pb') for r in rows if r.get('pb') is not None and r.get('pb') > 0]
    common = [r for r in rows if r.get('peTtm') is not None and r.get('peTtm') > 0
              and r.get('pb') is not None and r.get('pb') > 0]
    return {
        'memberCount': len(members), 'snapshotCount': len(rows),
        'missingSnapshotCount': len(members) - len(rows),
        'peCount': len(pe), 'pbCount': len(pb), 'commonCount': len(common),
        'peCoverage': round(len(pe) / len(members), 4) if members else 0.0,
        'pbCoverage': round(len(pb) / len(members), 4) if members else 0.0,
        'commonCoverage': round(len(common) / len(members), 4) if members else 0.0,
        'lossPeCount': sum(r.get('peTtm') is not None and r.get('peTtm') <= 0 for r in rows),
        'peTtmMedian': round(float(statistics.median(pe)), 4) if pe else None,
        'pbMedian': round(float(statistics.median(pb)), 4) if pb else None,
    }


def _valid_metric(snapshot, prefix):
    median = snapshot.get('peTtmMedian' if prefix == 'pe' else 'pbMedian')
    count = snapshot.get(f'{prefix}Count') or 0
    coverage = snapshot.get(f'{prefix}Coverage') or 0
    return (median is not None and median > 0 and count >= MIN_METRIC_COUNT
            and coverage >= MIN_METRIC_COVERAGE)


def history_valuation_position(current, history_rows, min_samples=MIN_HISTORY_SAMPLES):
    """当前有效日中位数相对自身历史有效月末中位数的<=占比，当前点计入。

    PE/PB历史样本分别筛选各自覆盖率；不足时该指标分位为None，绝不回退横截面。
    双有效取平均，单有效保留单指标，均无效则综合分位None。
    """
    result = dict(current)
    result.update({'peHistoryPct': None, 'pbHistoryPct': None, 'compositeHistoryPct': None,
                   'peHistorySamples': 0, 'pbHistorySamples': 0,
                   'valuationRankBasis': 'missing', 'rankEligible': False,
                   'historyStatus': 'snapshot_missing', 'historyReason': '当前有效日快照缺失'})
    current_date = str(current.get('tradeDate') or '')
    history = [row for row in history_rows or [] if str(row.get('tradeDate') or '') != current_date]
    for prefix, median_key, pct_key, sample_key in (
            ('pe', 'peTtmMedian', 'peHistoryPct', 'peHistorySamples'),
            ('pb', 'pbMedian', 'pbHistoryPct', 'pbHistorySamples')):
        if not _valid_metric(current, prefix):
            continue
        values = [row[median_key] for row in history
                  if _valid_metric(row, prefix) and row.get(median_key) is not None]
        values.append(current[median_key])
        result[sample_key] = len(values)
        if len(values) >= min_samples:
            result[pct_key] = round(sum(v <= current[median_key] for v in values) / len(values) * 100, 1)
    valid = [x for x in (result['peHistoryPct'], result['pbHistoryPct']) if x is not None]
    if valid:
        result['compositeHistoryPct'] = round(sum(valid) / len(valid), 1)
        result['valuationRankBasis'] = 'dual' if len(valid) == 2 else 'single'
        result['rankEligible'] = True
        result['historyStatus'] = 'ok'
        result['historyReason'] = ('PE/PB自身历史分位均值' if len(valid) == 2 else '仅一个指标历史样本足够，按单一指标排序')
    else:
        pe_ready, pb_ready = _valid_metric(current, 'pe'), _valid_metric(current, 'pb')
        if pe_ready or pb_ready:
            result['historyStatus'] = 'insufficient'
            result['historyReason'] = f'历史样本不足：至少需{min_samples}个有效月末/当前样本，不用横截面分位充数'
        elif (current.get('snapshotCount') or 0) == 0:
            result['historyStatus'] = 'snapshot_missing'
            result['historyReason'] = '当前有效日快照缺失，当前中位数与历史分位均不参与排序'
        else:
            result['historyStatus'] = 'coverage_insufficient'
            result['historyReason'] = '当前PE/PB有效数量或覆盖率不足，不参与估值排序'
    return result


def month_end_sample_dates(cal_dates, trade_date, years=10):
    """真实交易日历中每月最后交易日，仅取本批月份之前的完整月份，最多十年。"""
    import pandas as pd
    td = pd.Timestamp(str(trade_date).replace('-', ''))
    start = td - pd.DateOffset(years=years)
    previous_month_end = td.replace(day=1) - pd.Timedelta(days=1)
    dates = sorted({str(x).replace('-', '') for x in cal_dates or []
                    if start.strftime('%Y%m%d') <= str(x).replace('-', '') <= previous_month_end.strftime('%Y%m%d')})
    by_month = {}
    for date in dates:
        by_month[date[:6]] = date
    return [by_month[m] for m in sorted(by_month)]
