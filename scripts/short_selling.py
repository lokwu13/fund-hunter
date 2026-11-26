#!/usr/bin/env python3
"""Northbound short-selling snapshots for the foreign-capital panel.

Only complete official files enter the cache; failed or intraday responses retain the
last complete observation and its date. Legacy H/SFC parsers and cache namespaces are
retained, but their nightly requests are disabled with the removed Hong Kong card.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

CACHE_PATH = Path(__file__).resolve().parent / 'cache' / 'short_selling_history.json'
NB_PAGE = 'https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Statistics/Short-Selling?sc_lang=en'
NB_FILE = 'https://www.hkex.com.hk/eng/csm/shortsell/data_tab_short_selling_{}e.js'
HK_PAGE = 'https://www.hkex.com.hk/Market-Data/Statistics/Securities-Market/Short-Selling-Turnover-Today?sc_lang=en'
HK_FILE = 'https://www.hkex.com.hk/eng/stat/smstat/ssturnover/ncms/ASHTMAIN.HTM'
SFC_PAGE = ('https://www.sfc.hk/en/Regulatory-functions/Market/Short-position-reporting/'
            'Aggregated-reportable-short-positions-of-specified-shares')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')


def _now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def _iso(date8):
    return f'{date8[:4]}-{date8[4:6]}-{date8[6:]}'


def _load(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _save(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def _get(url, timeout=45):
    response = requests.get(url, headers={
        'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache', 'Pragma': 'no-cache',
        'Referer': NB_PAGE if '/csm/' in url else HK_PAGE,
    }, timeout=timeout)
    response.raise_for_status()
    return response


def parse_northbound(text, date8):
    """Parse both complete afternoon HKEX Stock Connect tables.

    Positive-turnover rows alone are cached; a complete official universe means an
    absent code in a later comparison is a genuine zero, not missing data.
    """
    if not isinstance(date8, str) or not re.fullmatch(r'\d{8}', date8):
        raise ValueError('invalid northbound date')
    chunks = re.split(r'(?="tabName"\s*:)', text)
    tabs = []
    for market, marker in (('SH', 'Short Selling Data of SSE Securities'),
                           ('SZ', 'Short Selling Data of SZSE Securities')):
        chunk = next((part for part in chunks if marker in part), None)
        if not chunk:
            raise ValueError(f'missing {market} table')
        time_match = re.search(r'"time"\s*:\s*[\'\"](\d{2}:\d{2})[\'\"]', chunk)
        day_match = re.search(r'"tradingDay"\s*:\s*(\d+)', chunk)
        if not time_match or time_match.group(1) < '15:00' or not day_match or day_match.group(1) != '1':
            raise ValueError(f'{market} is not a complete afternoon file')
        if 'Value (RMB)' not in chunk or 'Percentage of Short Selling' not in chunk:
            raise ValueError(f'{market} schema changed')
        raw_rows = re.findall(r'\{"tableTitle": false,"td": \[\s*(\[.*?\])\]\}', chunk, re.S)
        records = []
        for raw in raw_rows:
            values = json.loads(raw)
            if len(values) != 8 or not re.fullmatch(r'\d{1,6}', values[1]):
                raise ValueError('northbound row schema changed')
            shares = int(values[4].replace(',', ''))
            value = int(values[5].replace(',', ''))
            if shares < 0 or value < 0:
                raise ValueError('negative northbound turnover')
            if value > 0:
                records.append({'code': values[1].zfill(6) + ('.SH' if market == 'SH' else '.SZ'),
                                'name': values[2], 'shares': shares, 'value': value,
                                'shortPct': values[6], 'cum10Pct': values[7]})
        if len(raw_rows) < 100:
            raise ValueError(f'{market} universe unexpectedly small')
        tabs.append({'market': market, 'universeCount': len(raw_rows), 'records': records})
    records = tabs[0]['records'] + tabs[1]['records']
    return {
        'asOf': _iso(date8), 'session': 'day_close', 'currency': 'RMB',
        'universeCount': sum(tab['universeCount'] for tab in tabs),
        'nonZeroCount': len(records), 'totalValue': sum(row['value'] for row in records),
        'records': records, 'sourceUrl': NB_FILE.format(date8), 'retrievedAt': _now(),
    }


def parse_hkex_mainboard(text, max_date=None):
    """Parse HKEX Main Board day-close text; '%' records are non-HKD and excluded."""
    match = re.search(r'SHORTSELL REPORT\s+TRADING DATE\s*:\s*(\d{2})\s+([A-Z]{3})\s+(\d{4})', text)
    if not match or 'up to day close today' not in text:
        raise ValueError('HKEX day-close report unavailable')
    try:
        as_of = datetime.strptime(' '.join(match.groups()), '%d %b %Y').strftime('%Y-%m-%d')
    except ValueError as exc:
        raise ValueError('invalid HKEX report date') from exc
    if max_date and as_of > max_date:
        raise ValueError('HKEX report date is after requested date')
    body = text.split('Total No. of all Securities recording Short Selling', 1)[0]
    records = []
    non_hkd = 0
    for line in body.splitlines():
        row = re.match(r'^\s*(%?)\s*(\d{1,5})\s+(.+?)\s+([\d,]+)\s+([\d,]+)\s*$', line)
        if not row:
            continue
        non_hkd_mark, code, name, shares_raw, value_raw = row.groups()
        shares, value = int(shares_raw.replace(',', '')), int(value_raw.replace(',', ''))
        if non_hkd_mark:
            non_hkd += 1
            continue
        if value > 0:
            records.append({'code': code.zfill(5) + '.HK', 'name': name.strip(),
                            'shares': shares, 'value': value})
    declared = re.search(r'Total No\. of all Securities recording Short Selling\s*:\s*(\d+)', text)
    total_value = sum(row['value'] for row in records)
    declared_total = re.search(r'\(C\) Short Selling of all Designated Securities[\s\S]*?'
                               r'Short Selling Turnover Total Value \(\$\)\s*:\s*HKD\s*([\d,]+)', text)
    if not declared or len(records) + non_hkd != int(declared.group(1)) or len(records) < 10:
        raise ValueError('HKEX rows do not reconcile with declared count')
    if not declared_total or total_value != int(declared_total.group(1).replace(',', '')):
        raise ValueError('HKD rows do not reconcile with declared turnover')
    return {
        'asOf': as_of, 'session': 'day_close', 'currency': 'HKD',
        'universeCount': int(declared.group(1)), 'nonZeroCount': len(records),
        'nonHkdExcluded': non_hkd, 'totalValue': total_value,
        'records': records, 'sourceUrl': HK_FILE, 'retrievedAt': _now(),
    }


def parse_sfc_page(html):
    soup = BeautifulSoup(html, 'html.parser')
    links = []
    for anchor in soup.select('a[href]'):
        href = anchor.get('href') or ''
        match = re.search(r'Short_Position_Reporting_Aggregated_Data_(\d{8})\.csv', href, re.I)
        if match:
            date8 = match.group(1)
            url = urljoin(SFC_PAGE, href).split('?')[0]
            if date8 not in [item[0] for item in links]:
                links.append((date8, url))
    if len(links) < 2:
        raise ValueError('SFC latest and previous CSV links unavailable')
    return links


def parse_sfc_csv(text, expected_date8):
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    required = {'Date', 'Stock Code', 'Stock Name',
                'Aggregated Reportable Short Positions (Shares)',
                'Aggregated Reportable Short Positions (HK$)'}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError('SFC CSV schema changed')
    records = []
    dates = set()
    universe_count = 0
    for row in reader:
        universe_count += 1
        date8 = datetime.strptime(row['Date'], '%d/%m/%Y').strftime('%Y%m%d')
        dates.add(date8)
        value = int(row['Aggregated Reportable Short Positions (HK$)'])
        shares = int(row['Aggregated Reportable Short Positions (Shares)'])
        if value > 0:
            records.append({'code': str(int(row['Stock Code'])).zfill(5) + '.HK',
                            'name': row['Stock Name'].strip(), 'shares': shares, 'value': value})
    if dates != {expected_date8} or len(records) < 10:
        raise ValueError('SFC CSV date or row count mismatch')
    return {'asOf': _iso(expected_date8), 'frequency': 'weekly', 'currency': 'HKD',
            'universeCount': universe_count,
            'nonZeroCount': len(records), 'totalValue': sum(row['value'] for row in records),
            'records': records, 'sourceUrl': SFC_PAGE, 'retrievedAt': _now()}


def _previous(cache, market, as_of):
    dates = sorted(date for date in cache.get(market, {}) if date < as_of)
    return cache[market][dates[-1]] if dates else None


def _board(current, previous, status, note, source, page_url, error=None):
    previous_records = {row['code']: row for row in (previous or {}).get('records', [])}
    items = []
    for rank, row in enumerate(sorted(current.get('records', []), key=lambda item: item['value'], reverse=True)[:10], 1):
        old = previous_records.get(row['code'])
        old_value = old['value'] if old else (0 if previous else None)
        item = {key: row[key] for key in ('code', 'name', 'shares', 'value')}
        item.update({'rank': rank,
                     'valueChg': row['value'] - old_value if old_value is not None else None,
                     'valueChgPct': ((row['value'] - old_value) / old_value * 100)
                                    if old_value else None,
                     'changeFromZero': old_value == 0})
        items.append(item)
    return {'asOf': current.get('asOf'), 'previousAsOf': (previous or {}).get('asOf'),
            'status': status, 'currency': current.get('currency'), 'items': items,
            'universeCount': current.get('universeCount'), 'nonZeroCount': current.get('nonZeroCount'),
            'nonHkdExcluded': current.get('nonHkdExcluded'), 'totalValue': current.get('totalValue'),
            'source': source, 'sourceUrl': current.get('sourceUrl') or page_url, 'pageUrl': page_url,
            'note': note, 'error': error, 'checkedAt': _now()}


def _latest_cached(cache, market, max_date):
    dates = sorted(date for date in cache.get(market, {}) if date <= max_date)
    return cache[market][dates[-1]] if dates else None


def _empty_board(market, error):
    if market == 'a':
        return _board({}, None, 'unavailable',
                      '北向渠道卖空成交（RMB），非未平仓余额，也不等于全部外资。',
                      'HKEX Stock Connect Northbound Short Selling', NB_PAGE, error)
    return _board({}, None, 'unavailable',
                  '港股主板卖空成交（HKD），非未平仓余额、非纯外资；%标记非港元记录剔除。',
                  'HKEX Main Board Short Selling Turnover', HK_PAGE, error)


def _prune(cache):
    for market, keep in (('a', 62), ('h', 62), ('weekly', 20)):
        entries = cache.setdefault(market, {})
        for date in sorted(entries)[:-keep]:
            del entries[date]


def update_short_selling_monitor(trade_date, data, cache_path=CACHE_PATH, *,
                                 northbound_texts=None, hkex_text=None, sfc_page_text=None,
                                 sfc_csv_texts=None):
    """Nightly Northbound update; legacy H/SFC arguments remain for API compatibility."""
    cache = _load(cache_path)
    for market in ('a', 'h', 'weekly'):
        cache.setdefault(market, {})
    max_date = _iso(trade_date)

    # A: requested/latest complete afternoon file plus previous valid file.
    try:
        snapshots = []
        if northbound_texts is not None:
            for date8 in sorted(northbound_texts, reverse=True):
                snapshots.append(parse_northbound(northbound_texts[date8], date8))
        else:
            start = datetime.strptime(trade_date, '%Y%m%d')
            for offset in range(12):
                day = start - timedelta(days=offset)
                if day.weekday() >= 5:
                    continue
                date8 = day.strftime('%Y%m%d')
                try:
                    time.sleep(0.15)
                    snapshots.append(parse_northbound(_get(NB_FILE.format(date8)).text, date8))
                    if len(snapshots) == 2:
                        break
                except Exception as exc:
                    if offset == 0:
                        print(f'  short-selling A latest unavailable: {exc}')
            if not snapshots:
                raise ValueError('no complete northbound file')
        current = snapshots[0]
        cached_latest = _latest_cached(cache, 'a', max_date)
        if cached_latest and current['asOf'] < cached_latest['asOf']:
            raise ValueError('northbound file is older than cached last-good')
        for snapshot in snapshots:
            cache['a'][snapshot['asOf']] = snapshot
        previous = snapshots[1] if len(snapshots) > 1 else _previous(cache, 'a', current['asOf'])
        a_board = _board(current, previous, 'ok',
                         '北向渠道卖空成交（RMB），非未平仓余额，也不等于全部外资；仅官方完整收盘文件入榜。',
                         'HKEX Stock Connect Northbound Short Selling', NB_PAGE)
    except Exception as exc:
        current = _latest_cached(cache, 'a', max_date)
        a_board = (_board(current, _previous(cache, 'a', current['asOf']), 'stale',
                          '北向渠道卖空成交（RMB），非未平仓余额，也不等于全部外资；本次断源沿用最近完整快照。',
                          'HKEX Stock Connect Northbound Short Selling', NB_PAGE, str(exc)[:240])
                   if current else _empty_board('a', str(exc)[:240]))

    cache['note'] = ('仅北向日成交继续 nightly 更新；H/SFC 历史缓存保留但停止请求；'
                     '仅完整官方文件入缓存，完整官方 universe 支持缺失代码按0计算变化。')
    _prune(cache)
    _save(cache_path, cache)
    data['shortSellingMonitor'] = {'version': 1, 'frequency': '每个既有交易日夜间检查',
                                   'a': a_board}
    return data['shortSellingMonitor']
