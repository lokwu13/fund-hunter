# -*- coding: utf-8 -*-
"""任务114：可持久化、可PIT重放的形态孕育→突破→10日退出→再次入选历史。

只保存事件与证据，不保存生产fund_data；运行期嵌套在既有vcp_cache.patternEpisodeHistory，
首批验证记录由pattern_episode_seed.json提供。不得按股票代码写特殊分支。
"""
import copy
import json
import os

PATTERN_BREAKOUT_MAX_TRADING_DAYS = 10
PENDING_MAX_AGE_TRADING_DAYS = 60
SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pattern_episode_seed.json')


def empty_history():
    return {
        'version': 1,
        'coverage': {
            'kind': 'runtime_plus_verified_seed', 'fullMarketComplete': False,
            'note': '每日正式入选孕育记录+首批可重放验证种子；不是全市场全历史归档，未覆盖区间不伪造历史。',
        },
        'stocks': {},
    }


def load_seed():
    try:
        with open(SEED_PATH, encoding='utf-8') as handle:
            return json.load(handle)
    except FileNotFoundError:
        return empty_history()


def _pending_key(record):
    return record.get('patternType'), record.get('gestationStart'), record.get('pivot')


def _merge_stock(seed_stock, runtime_stock):
    """同一股票的种子与运行缓存做事件级合并，避免旧运行缓存遮蔽较新的只读种子。"""
    result = copy.deepcopy(seed_stock or {})
    pending = {_pending_key(x): copy.deepcopy(x) for x in result.get('pending') or []}
    for record in (runtime_stock or {}).get('pending') or []:
        key = _pending_key(record)
        old = pending.get(key)
        if old is None or record.get('gestationEnd', '') >= old.get('gestationEnd', ''):
            pending[key] = copy.deepcopy(record)
    episodes = {x.get('episodeId'): copy.deepcopy(x) for x in result.get('episodes') or []}
    for record in (runtime_stock or {}).get('episodes') or []:
        episodes[record.get('episodeId')] = copy.deepcopy(record)
    result['pending'] = sorted(pending.values(), key=lambda x: (x['gestationEnd'], x['gestationStart']))
    result['episodes'] = sorted(episodes.values(), key=lambda x: (x['breakoutDate'], x['episodeId']))
    return result


def load_history(cache_container=None):
    """种子为只读基线，运行缓存按事件合并；调用方把返回对象写回vcp_cache独立键。"""
    runtime = (cache_container or {}).get('patternEpisodeHistory') or {}
    base = copy.deepcopy(load_seed() or empty_history())
    base.setdefault('stocks', {})
    for code, stock in (runtime.get('stocks') or {}).items():
        base['stocks'][code] = _merge_stock(base['stocks'].get(code), stock)
    if runtime.get('coverage'):
        base['runtimeCoverage'] = copy.deepcopy(runtime['coverage'])
    return base


def _stock(history, code):
    return history.setdefault('stocks', {}).setdefault(code, {'pending': [], 'episodes': []})


def register_gestation(history, code, name, candidate, as_of, origin_formal=True):
    """登记当时已经合格的形态锚点；字段全部来自该日PIT证据，不读取未来。"""
    required = ('patternType', 'startDate', 'endDate', 'pivot', 'referenceHigh')
    if any(candidate.get(k) in (None, '') for k in required):
        return False
    start, end = str(candidate['startDate']), str(candidate['endDate'])
    if not (len(start) == len(end) == len(as_of) == 8 and start <= end <= as_of):
        return False
    pivot, reference = float(candidate['pivot']), float(candidate['referenceHigh'])
    if pivot <= 0 or reference <= 0:
        return False
    stock = _stock(history, code)
    # 已突破的同一形态/起点/枢轴不得在下一天被重复包装成“首次突破”。
    if any(x.get('patternType') == candidate['patternType']
           and x.get('gestationStart') == start and x.get('pivot') == round(pivot, 4)
           for x in stock.setdefault('episodes', [])):
        return False
    record = {
        'code': code, 'name': name, 'patternType': candidate['patternType'],
        'structurePath': candidate.get('structurePath'), 'gestationStart': start, 'gestationEnd': end,
        'vcpEntryId': candidate.get('vcpEntryId'), 'vcpEntryLabel': candidate.get('vcpEntryLabel'),
        'vcpStructure': copy.deepcopy(candidate.get('vcpStructure')),
        'pivot': round(pivot, 4), 'breakoutPoint': round(pivot, 4),
        'referenceHigh': round(reference, 4), 'referenceDate': candidate.get('referenceDate'),
        'referenceBasis': candidate.get('referenceBasis') or 'prior_250d_highest_close_plus_anchor_high',
        'referenceSamples': candidate.get('referenceSamples'),
        'anchorHigh': candidate.get('anchorHigh'), 'invalidation': candidate.get('invalidation'),
        'sidewaysLabel': candidate.get('sidewaysLabel'), 'sidewaysScore': candidate.get('sidewaysScore'),
        'originFormalAdmission': bool(origin_formal),
        'originQualificationNote': candidate.get('originQualificationNote') or (
            '正式入选时登记' if origin_formal else '仅价格结构回放，不冒充当时正式入选'),
        'dailyTrend': copy.deepcopy(candidate.get('dailyTrend')),
        'vcpGestation': copy.deepcopy(candidate.get('vcpGestation')),
        'originPatternEvidence': copy.deepcopy(candidate.get('patternEvidence')),
    }
    key = _pending_key(record)
    for i, old in enumerate(stock['pending']):
        if _pending_key(old) == key:
            # 同一孕育起点/枢轴只推进可见终点，不保留相互矛盾的重复锚点。
            if end >= old.get('gestationEnd', ''):
                stock['pending'][i] = record
            break
    else:
        stock['pending'].append(record)
    stock['pending'] = sorted(stock['pending'], key=lambda x: (x['gestationEnd'], x['gestationStart']))[-40:]
    return True


def trading_day_lifecycle(dates, breakout_date, max_days=PATTERN_BREAKOUT_MAX_TRADING_DAYS):
    """突破日age=0；其后第10个交易日age=10退出，与既有10日信号年龄语义一致。"""
    dates = sorted(set(dates or []))
    if breakout_date not in dates:
        return {'known': False, 'active': False, 'expired': False, 'breakoutAge': None,
                'remainingDays': None, 'exitDate': None, 'maxTradingDays': max_days}
    after = [d for d in dates if d > breakout_date]
    age = len(after)
    expired = age >= max_days
    exit_date = after[max_days - 1] if expired else None
    return {'known': True, 'active': not expired, 'expired': expired, 'breakoutAge': age,
            'remainingDays': max(0, max_days - age), 'exitDate': exit_date, 'maxTradingDays': max_days}


def _episode_from_pending(pending, bar):
    return {
        'episodeId': '|'.join((pending['code'], pending['gestationStart'], pending['gestationEnd'], bar[0])),
        'code': pending['code'], 'name': pending['name'], 'patternType': pending['patternType'],
        'structurePath': pending.get('structurePath'),
        'gestationStart': pending['gestationStart'], 'gestationEnd': pending['gestationEnd'],
        'vcpEntryId': pending.get('vcpEntryId'), 'vcpEntryLabel': pending.get('vcpEntryLabel'),
        'vcpStructure': copy.deepcopy(pending.get('vcpStructure')),
        'pivot': pending['pivot'], 'breakoutPoint': pending['pivot'],
        'referenceHigh': pending['referenceHigh'], 'referenceDate': pending.get('referenceDate'),
        'referenceBasis': pending.get('referenceBasis'), 'referenceSamples': pending.get('referenceSamples'),
        'breakoutDate': bar[0], 'breakoutHigh': round(float(bar[1]), 4),
        'breakoutClose': round(float(bar[3]), 4), 'breakoutVolume': round(float(bar[4]), 4),
        'breakoutDefinition': '孕育结束后首个盘中最高价>参考高点且收盘价>枢轴的交易日',
        'exitAfterTradingDays': PATTERN_BREAKOUT_MAX_TRADING_DAYS,
        'originFormalAdmission': pending.get('originFormalAdmission'),
        'originQualificationNote': pending.get('originQualificationNote'),
        'invalidation': pending.get('invalidation'), 'sidewaysLabel': pending.get('sidewaysLabel'),
        'sidewaysScore': pending.get('sidewaysScore'), 'dailyTrend': copy.deepcopy(pending.get('dailyTrend')),
        'vcpGestation': copy.deepcopy(pending.get('vcpGestation')),
        'originPatternEvidence': copy.deepcopy(pending.get('originPatternEvidence')),
    }


def advance_stock(history, code, name, bars):
    """逐日推进通用事件；相同PIT前缀重放得到相同首个突破，不用后续结果倒选锚点。"""
    stock = _stock(history, code)
    bars = list(bars or [])
    if not bars:
        return None
    dates = [b[0] for b in bars]
    pending = []
    for candidate in stock.get('pending') or []:
        after = [b for b in bars if b[0] > candidate['gestationEnd']]
        breakout = next((b for b in after
                         if b[1] > candidate['referenceHigh'] + 1e-9 and b[3] > candidate['pivot']), None)
        if breakout:
            episode = _episode_from_pending(candidate, breakout)
            if all(x.get('episodeId') != episode['episodeId'] for x in stock.setdefault('episodes', [])):
                stock['episodes'].append(episode)
            continue
        if len(after) < PENDING_MAX_AGE_TRADING_DAYS:
            pending.append(candidate)
    stock['pending'] = pending
    stock['episodes'] = sorted(stock.get('episodes') or [], key=lambda x: (x['breakoutDate'], x['episodeId']))
    active = None
    for episode in stock['episodes']:
        lifecycle = trading_day_lifecycle(dates, episode['breakoutDate'])
        if lifecycle['known'] and lifecycle['active']:
            active = episode
    return copy.deepcopy(active)


def active_candidate(active, bars):
    """把未到期事件转换为现有精扫/漏斗共用的主候选；到期后不返回。"""
    if not active or not bars:
        return None
    lifecycle = trading_day_lifecycle([b[0] for b in bars], active['breakoutDate'])
    if not lifecycle['active']:
        return None
    close = bars[-1][3]
    pivot = active['pivot']
    pattern = active['patternType']
    return {
        'type': pattern, 'formed': True, 'structureFormed': True, 'eligible': True, 'displayEligible': True,
        'pivot': pivot, 'distPct': round((pivot / close - 1) * 100, 1) if close > 0 else 999,
        'invalidation': active.get('invalidation'), 'startDate': active['gestationStart'],
        'endDate': active['gestationEnd'], 'breakout': True, 'breakoutDate': active['breakoutDate'],
        'signalDate': active['breakoutDate'], 'signalType': 'pattern_new_high',
        'signalLabel': f"{pattern}参考高点突破·10个交易日后退出",
        'breakoutAge': lifecycle['breakoutAge'], 'breakoutRemainingDays': lifecycle['remainingDays'],
        'breakoutExitDate': lifecycle['exitDate'], 'currentDist': round((close / pivot - 1) * 100, 1),
        'currentValid': True, 'patternEpisode': copy.deepcopy(active),
        'vcpEntryId': active.get('vcpEntryId'), 'vcpEntryLabel': active.get('vcpEntryLabel'),
        'vcpStructure': copy.deepcopy(active.get('vcpStructure')),
        'dailyTrend': copy.deepcopy(active.get('dailyTrend')),
        'dailyTrendPass': bool((active.get('dailyTrend') or {}).get('pass')) if pattern == 'VCP收缩型' else None,
        'vcpGestation': copy.deepcopy(active.get('vcpGestation')),
        'gestationPass': bool((active.get('vcpGestation') or {}).get('pass')) if pattern == 'VCP收缩型' else None,
        'structurePath': active.get('structurePath') or 'persisted_episode',
        **({'patternEvidence': copy.deepcopy(active['originPatternEvidence'])}
           if active.get('originPatternEvidence') else {}),
    }


def attach_history(items, history, as_of):
    """只有之前不同episode才显示“历史入选记录”；当前首次突破不冒充再次入选。"""
    coverage = copy.deepcopy(history.get('coverage') or empty_history()['coverage'])
    for item in items or []:
        stock = (history.get('stocks') or {}).get(item.get('code')) or {}
        episode = item.get('patternEpisode') or {}
        current_id = episode.get('episodeId')
        current_breakout = episode.get('breakoutDate') or (item.get('buyPoint') or {}).get('breakoutDate')
        records = [copy.deepcopy(x) for x in stock.get('episodes') or []
                   if x.get('breakoutDate', '') < as_of
                   and x.get('episodeId') != current_id and x.get('breakoutDate') != current_breakout]
        item['patternHistory'] = records[-10:]
        item['patternHistoryCoverage'] = coverage
    return items


def candidate_from_formal(pattern, main, daily_trend=None):
    """把update_data正式主候选转换为通用登记结构；不改变原形态高位门。"""
    if not main:
        return None
    gestation = main.get('vcpGestation') or main.get('historyGestation') or {}
    start = main.get('startDate') or main.get('bottomStart')
    end = main.get('endDate') or main.get('bottomEnd')
    if not start or not end or not gestation or gestation.get('pass') is not True:
        return None
    return {
        'patternType': pattern, 'structurePath': main.get('structurePath'),
        'startDate': start, 'endDate': end,
        'vcpEntryId': main.get('vcpEntryId'), 'vcpEntryLabel': main.get('vcpEntryLabel'),
        'vcpStructure': copy.deepcopy(main.get('vcpStructure')),
        'pivot': main.get('pivot'), 'referenceHigh': gestation.get('referenceHigh'),
        'referenceDate': gestation.get('referenceDate'), 'referenceBasis': gestation.get('referenceBasis'),
        'referenceSamples': gestation.get('referenceSamples'), 'anchorHigh': gestation.get('anchorHigh'),
        'invalidation': main.get('invalidation'), 'sidewaysLabel': gestation.get('sidewaysLabel'),
        'sidewaysScore': gestation.get('sidewaysScore'), 'dailyTrend': daily_trend or main.get('dailyTrend'),
        'vcpGestation': gestation,
        'patternEvidence': copy.deepcopy(main) if pattern == '底部整理' else None,
    }
