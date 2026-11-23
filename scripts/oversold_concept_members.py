# -*- coding: utf-8 -*-
"""RSI6历史估值专用同花顺概念成分：真实代码核验、A股过滤与可审计公开分页兜底。"""
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup


OVERSOLD_CONCEPT_SOURCES = {
    '新能源车': {'indexName': '新能源汽车', 'code': '885431.TI', 'queryCode': '300008'},
    '卫星互联网': {'indexName': '卫星导航', 'code': '885574.TI', 'queryCode': '300722'},
    '智能驾驶': {'indexName': '无人驾驶', 'code': '885736.TI', 'queryCode': '301286'},
    '光伏': {'indexName': '光伏概念', 'code': '885531.TI', 'queryCode': '301079'},
    '数据中心': {'indexName': '数据中心(AIDC)', 'code': '885887.TI', 'queryCode': '308642'},
    '充电桩': {'indexName': '充电桩', 'code': '885461.TI', 'queryCode': '300786'},
    '消费电子': {'indexName': '消费电子概念', 'code': '885800.TI', 'queryCode': '308384'},
    '人形机器人': {'indexName': '人形机器人', 'code': '886069.TI', 'queryCode': '309119'},
    '商业航天': {'indexName': '商业航天', 'code': '886078.TI', 'queryCode': '309130'},
    '固态电池': {'indexName': '固态电池', 'code': '886032.TI', 'queryCode': '308294'},
    '创新药': {'indexName': '创新药', 'code': '886015.TI', 'queryCode': '308014'},
}
PUBLIC_MEMBER_SOURCE = '同花顺公开概念页全分页（真实A股）'
TUSHARE_MEMBER_SOURCE = 'Tushare ths_member（真实A股，公开页核验指数）'
PUBLIC_BASE_URL = 'https://q.10jqka.com.cn/gn/detail/code'
MIN_CONCEPT_MEMBERS = 5


def is_real_a_share_code(code):
    code = str(code or '').upper()
    if code.endswith('.SH'):
        return code.startswith(('600', '601', '603', '605', '688', '689'))
    if code.endswith('.SZ'):
        return code.startswith(('000', '001', '002', '003', '300', '301', '302'))
    if code.endswith('.BJ'):
        return code.startswith(('43', '83', '87', '88', '92'))
    return False


def a_share_code(bare):
    bare = str(bare or '').strip()
    if not re.fullmatch(r'\d{6}', bare):
        return None
    suffix = 'SH' if bare.startswith('6') else 'BJ' if bare.startswith(('43', '83', '87', '88', '92')) else 'SZ'
    code = f'{bare}.{suffix}'
    return code if is_real_a_share_code(code) else None


def _public_text(response):
    # requests对GBK页面可能误判ISO-8859-1；直接按网页声明的中文编码解码。
    return response.content.decode('gb18030', 'replace')


def parse_public_concept_page(text, source):
    """返回经h3身份核验的指数、A股代码与页数；海外证券与无效行不进入样本。"""
    soup = BeautifulSoup(text, 'html.parser')
    heading = soup.select_one('.board-hq h3')
    heading_text = heading.get_text(' ', strip=True) if heading else ''
    match = re.search(r'(\d{6})(?!.*\d{6})', heading_text)
    actual_code = f'{match.group(1)}.TI' if match else None
    if actual_code != source['code']:
        raise ValueError(f"公开页指数身份不符：期望{source['indexName']} {source['code']}，实际{heading_text or '缺失'}")
    index_name = heading_text[:match.start()].strip() if match else ''
    if index_name != source['indexName']:
        raise ValueError(f"公开页指数名称不符：期望{source['indexName']}，实际{index_name or '缺失'}")
    members, rejected = set(), set()
    for row in soup.select('table tbody tr'):
        cells = [cell.get_text(' ', strip=True) for cell in row.select('td')]
        if len(cells) < 3 or not re.fullmatch(r'\d+', cells[0]) or not re.fullmatch(r'\d{6}', cells[1]):
            continue
        code = a_share_code(cells[1])
        (members if code else rejected).add(code or cells[1])
    pages = [int(a.get('page')) for a in soup.select('#m-page a[page]')
             if str(a.get('page') or '').isdigit()]
    return {'indexName': index_name, 'code': actual_code, 'members': members,
            'rejectedNonA': sorted(rejected), 'pageCount': max(pages, default=1)}


def _get_public_page(session, query_code, page):
    url = f'{PUBLIC_BASE_URL}/{query_code}/' + (f'page/{page}/' if page > 1 else '')
    response = session.get(url, timeout=30)
    response.raise_for_status()
    if '/account/login' in response.url or not response.content.strip().lower().startswith(b'<!doctype html'):
        raise RuntimeError(f'公开分页需登录或返回非概念页，拒绝使用不完整成员：page={page}')
    return response


def _fetch_identity_page(session, source, attempts=2):
    """空白/反爬异常页只作有限重试；指数代码或名称真实不符时立即失败，不改映射。"""
    last_error = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(0.6)
        try:
            response = _get_public_page(session, source['queryCode'], 1)
            return parse_public_concept_page(_public_text(response), source)
        except ValueError as exc:
            last_error = exc
            if '实际缺失' not in str(exc):
                raise
    raise last_error


def fetch_public_concept_members(source, as_of, session=None, delay=0.15):
    """完整逐页请求，任何一页失败均不返回不完整成分；as_of由调用方如实给出。"""
    owns_session = session is None
    session = session or requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36',
                            'Referer': 'https://q.10jqka.com.cn/'})
    try:
        first = _fetch_identity_page(session, source)
        members = set(first['members'])
        rejected = set(first['rejectedNonA'])
        fetched_pages = {1}
        for page in range(2, first['pageCount'] + 1):
            if delay:
                time.sleep(delay)
            parsed = parse_public_concept_page(_public_text(_get_public_page(session, source['queryCode'], page)), source)
            members.update(parsed['members'])
            rejected.update(parsed['rejectedNonA'])
            fetched_pages.add(page)
        if fetched_pages != set(range(1, first['pageCount'] + 1)):
            raise ValueError('公开分页不完整')
        members = sorted(members)
        if len(members) < MIN_CONCEPT_MEMBERS:
            raise ValueError(f'真实A股成分不足{MIN_CONCEPT_MEMBERS}只：{len(members)}')
        return {'name': source['name'], 'indexName': first['indexName'], 'code': source['code'],
                'queryCode': source['queryCode'], 'members': members, 'memberCount': len(members),
                'source': PUBLIC_MEMBER_SOURCE, 'asOf': str(as_of),
                'retrievedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
                'pageCount': first['pageCount'], 'rejectedNonA': sorted(rejected - set(members)),
                'fallbackReason': source.get('fallbackReason')}
    finally:
        if owns_session:
            session.close()


def _cached_member_record(cache, source, as_of):
    record = ((cache.get('oversoldConceptMembers') or {}).get(source['name']) or {})
    members = sorted({str(code).upper() for code in record.get('members') or [] if is_real_a_share_code(code)})
    if (record.get('code') == source['code'] and record.get('indexName') == source['indexName']
            and str(record.get('asOf') or '') == str(as_of) and len(members) >= MIN_CONCEPT_MEMBERS
            and len(members) == record.get('memberCount') and record.get('source')):
        return dict(record, members=members)
    return None


def _tushare_members(pro, source):
    if pro is None or not callable(getattr(pro, 'ths_member', None)):
        raise RuntimeError('ths_member不可用')
    frame = pro.ths_member(ts_code=source['code'])
    if frame is None or not len(frame):
        raise RuntimeError('ths_member为空')
    members = set()
    for _, row in frame.iterrows():
        raw = row.get('con_code') or row.get('ts_code') or row.get('code')
        code = str(raw or '').upper()
        if is_real_a_share_code(code):
            members.add(code)
    if len(members) < MIN_CONCEPT_MEMBERS:
        raise RuntimeError(f'ths_member真实A股不足{MIN_CONCEPT_MEMBERS}只：{len(members)}')
    return sorted(members)


def ensure_oversold_concept_members(pro, as_of, cache, save_cache=None, request_delay=0.15, names=None):
    """返回独立成员缓存；绝不回退旧海外865/875代码或修改其它概念/龙头缓存。"""
    result = dict(cache.get('oversoldConceptMembers') or {})
    errors = {}
    requested = set(names) if names is not None else None
    for name, raw_source in OVERSOLD_CONCEPT_SOURCES.items():
        if requested is not None and name not in requested:
            continue
        source = dict(raw_source, name=name)
        cached = _cached_member_record(cache, source, as_of)
        if cached:
            result[name] = cached
            continue
        try:
            try:
                members = _tushare_members(pro, source)
                # 完整Tushare成员不被公开页登录限制阻断；但身份异常单独留痕，真实错配仍拒绝。
                identity_error = None
                identity_session = requests.Session()
                identity_session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36',
                                                 'Referer': 'https://q.10jqka.com.cn/'})
                try:
                    identity = _fetch_identity_page(identity_session, source)
                except RuntimeError as exc:
                    identity_error = str(exc)[:240]
                finally:
                    identity_session.close()
                record = {'name': name, 'indexName': source['indexName'], 'code': source['code'],
                          'queryCode': source['queryCode'], 'members': members, 'memberCount': len(members),
                          'source': TUSHARE_MEMBER_SOURCE, 'asOf': str(as_of),
                          'retrievedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
                          'identityStatus': 'unavailable' if identity_error else 'verified',
                          'identityError': identity_error}
            except Exception as exc:
                record = fetch_public_concept_members(dict(source, fallbackReason=str(exc)[:240]), as_of,
                                                      delay=request_delay)
            result[name] = record
            errors.pop(name, None)
        except Exception as exc:
            errors[name] = {**raw_source, 'asOf': str(as_of), 'error': str(exc)[:300]}
        if save_cache:
            # 每组独立增量落盘，公开分页中途失败不会写入半成品。
            next_cache = dict(cache)
            next_cache['oversoldConceptMembers'] = result
            next_cache['oversoldConceptMemberErrors'] = errors
            save_cache(next_cache)
    return result, errors
