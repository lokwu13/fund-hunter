#!/usr/bin/env python3
"""Daily profit/loss breadth of publicly disclosed fund NAVs.

The Eastmoney ranking response contains one comma-separated record per public fund
share code. Only a complete, internally reconciled single-page response can replace
last-good. A/C shares remain separate observations and missing growth is never zero.
"""
from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import requests

CACHE_PATH = Path(__file__).resolve().parent / 'cache' / 'fund_profit_breadth.json'
SOURCE_URL = 'https://fund.eastmoney.com/data/fundranking.html'
RANK_URL = 'https://fund.eastmoney.com/data/rankhandler.aspx'
SOURCE_NAME = '天天基金公开净值排行'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')


def _iso_date(value):
    text = str(value).strip()
    for fmt in ('%Y%m%d', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    raise ValueError(f'invalid trade date: {value!r}')


def _now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def _load(path):
    try:
        doc = json.loads(Path(path).read_text(encoding='utf-8'))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def _pct(numerator, denominator):
    if not denominator:
        return 0.0
    value = Decimal(numerator) * 100 / Decimal(denominator)
    return float(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _metadata(text, key):
    match = re.search(rf'\b{re.escape(key)}\s*:\s*(\d+)', text)
    if not match:
        raise ValueError(f'missing response metadata: {key}')
    return int(match.group(1))


def _fetch(trade_date):
    end = datetime.strptime(trade_date, '%Y-%m-%d')
    try:
        start = end.replace(year=end.year - 1)
    except ValueError:  # February 29
        start = end.replace(year=end.year - 1, day=28)
    response = requests.get(RANK_URL, params={
        'op': 'ph', 'dt': 'kf', 'ft': 'all', 'rs': '', 'gs': '0',
        'sc': '1nzf', 'st': 'desc', 'sd': start.strftime('%Y-%m-%d'),
        'ed': end.strftime('%Y-%m-%d'), 'qdii': '', 'tabSubtype': ',,,,,',
        'pi': '1', 'pn': '50000', 'dx': '1',
    }, headers={'User-Agent': UA, 'Referer': SOURCE_URL}, timeout=60)
    response.raise_for_status()
    response.encoding = 'utf-8'
    return response.text


def parse_rank_response(response_text, trade_date):
    """Validate and aggregate a rank response without inventing missing NAV growth."""
    max_date = _iso_date(trade_date)
    if not isinstance(response_text, str) or 'rankData' not in response_text:
        raise ValueError('not a fund rank response')
    match = re.search(r'\bdatas\s*:\s*(\[.*?\])\s*,\s*allRecords\s*:', response_text, re.S)
    if not match:
        raise ValueError('fund rank datas not found')
    try:
        raw_rows = json.loads(match.group(1))
    except ValueError as exc:
        raise ValueError('invalid fund rank datas') from exc
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError('empty fund rank response')

    declared = _metadata(response_text, 'allRecords')
    all_num = _metadata(response_text, 'allNum')
    page_index = _metadata(response_text, 'pageIndex')
    page_num = _metadata(response_text, 'pageNum')
    all_pages = _metadata(response_text, 'allPages')
    if len(raw_rows) != declared or declared != all_num:
        raise ValueError('fund rank row count does not reconcile')
    if page_index != 1 or all_pages != 1 or page_num < declared:
        raise ValueError('fund rank response is not a complete single page')

    counts = Counter()
    dates = Counter()
    codes = set()
    for index, raw in enumerate(raw_rows):
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f'empty fund rank row: {index}')
        try:
            row = next(csv.reader([raw], strict=True))
        except (csv.Error, StopIteration) as exc:
            raise ValueError(f'invalid fund rank row: {index}') from exc
        if len(row) < 7:
            raise ValueError(f'short fund rank row: {index}')
        code = row[0].strip()
        if not re.fullmatch(r'\d{6}', code) or code in codes:
            raise ValueError(f'invalid or duplicate fund code: {code!r}')
        codes.add(code)

        disclosed = row[3].strip()
        if disclosed:
            try:
                disclosed = _iso_date(disclosed)
            except ValueError as exc:
                raise ValueError(f'invalid disclosure date for {code}') from exc
        growth = row[6].strip()
        if not growth:
            counts['missing'] += 1
            continue
        if not disclosed or disclosed > max_date:
            raise ValueError(f'missing or future disclosure date for {code}')
        try:
            value = Decimal(growth)
        except InvalidOperation as exc:
            raise ValueError(f'invalid daily growth for {code}') from exc
        if not value.is_finite():
            raise ValueError(f'non-finite daily growth for {code}')
        counts['profit' if value > 0 else 'loss' if value < 0 else 'flat'] += 1
        dates[disclosed] += 1

    total = len(raw_rows)
    valid = counts['profit'] + counts['loss'] + counts['flat']
    if not valid or valid + counts['missing'] != total:
        raise ValueError('no valid daily growth or classification mismatch')
    primary_date, primary_count = min(dates.items(), key=lambda item: (-item[1], item[0]))
    return {
        'version': 1,
        'unit': '公开基金代码/份额（A/C分开计数）',
        'total': total,
        'validCount': valid,
        'validPct': _pct(valid, total),
        'counts': {
            key: {'count': counts[key], 'pct': _pct(counts[key], total)}
            for key in ('profit', 'loss', 'flat', 'missing')
        },
        'asOf': max(dates),
        'primaryDate': primary_date,
        'primaryDateValidCount': primary_count,
        'primaryDateValidPct': _pct(primary_count, valid),
        'earliestDisclosureDate': min(dates),
        'disclosureDateCount': len(dates),
        'status': 'ok',
        'source': SOURCE_NAME,
        'sourceUrl': SOURCE_URL,
        'checkedAt': _now(),
        'error': None,
        'note': ('天天基金公开净值覆盖，不是完整法定基金名录；家数按公开基金代码/份额计，A/C分开。'
                 '盈利仅指该披露日增长率>0，不代表持有至今收益；未披露不补0。'),
    }


def update_fund_profit_breadth(trade_date, data, cache_path=CACHE_PATH, *, response_text=None):
    """Update data in place; retain last-good on failure and reject date regression."""
    max_date = _iso_date(trade_date)
    cached = _load(cache_path)
    try:
        current = parse_rank_response(
            _fetch(max_date) if response_text is None else response_text, max_date)
        if current['total'] < 1000:
            raise ValueError('fund coverage unexpectedly small')
        if cached:
            if cached.get('status') != 'ok' or not cached.get('asOf'):
                raise ValueError('invalid fund breadth last-good cache')
            if _iso_date(cached['asOf']) > max_date:
                raise ValueError('cached fund breadth is after requested date')
            if current['asOf'] < cached['asOf']:
                raise ValueError('fund breadth is older than cached last-good')
        _save(cache_path, current)
        result = current
    except Exception as exc:
        if not cached or cached.get('status') != 'ok' or not cached.get('asOf'):
            raise
        if _iso_date(cached['asOf']) > max_date:
            raise ValueError('cached fund breadth is after requested date') from exc
        result = dict(cached)
        result['status'] = 'stale'
        result['checkedAt'] = _now()
        result['error'] = str(exc)[:300]
    data['fundProfitBreadth'] = result
    return result
