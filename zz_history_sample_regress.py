# -*- coding: utf-8 -*-
"""历史估值当前快照修复专项：全为受控fixture，不请求真实API、不写生产数据。"""
import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import update_data as ud
import oversold_concept_members as members
from sector_valuation_history import group_valuation_snapshot, history_valuation_position

ud.API_DELAY = 0
checks = {}
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
data_sha = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in DATA}


def check(name, condition, evidence=None):
    checks[name] = {'pass': bool(condition), 'evidence': evidence}


EXPECTED = {
    '新能源车': ('新能源汽车', '885431.TI', '300008'), '卫星互联网': ('卫星导航', '885574.TI', '300722'),
    '智能驾驶': ('无人驾驶', '885736.TI', '301286'), '光伏': ('光伏概念', '885531.TI', '301079'),
    '数据中心': ('数据中心(AIDC)', '885887.TI', '308642'), '充电桩': ('充电桩', '885461.TI', '300786'),
    '消费电子': ('消费电子概念', '885800.TI', '308384'), '人形机器人': ('人形机器人', '886069.TI', '309119'),
    '商业航天': ('商业航天', '886078.TI', '309130'), '固态电池': ('固态电池', '886032.TI', '308294'),
    '创新药': ('创新药', '886015.TI', '308014'),
}
check('11组独立真实映射不复用拥挤度近似别名', set(members.OVERSOLD_CONCEPT_SOURCES) == set(EXPECTED)
      and all((v['indexName'], v['code'], v['queryCode']) == EXPECTED[k]
              for k, v in members.OVERSOLD_CONCEPT_SOURCES.items()), members.OVERSOLD_CONCEPT_SOURCES)
check('海外代码ETF与B股均被拒绝', members.is_real_a_share_code('600000.SH')
      and members.is_real_a_share_code('300750.SZ') and members.is_real_a_share_code('920001.BJ')
      and not any(members.is_real_a_share_code(x) for x in ('TSLA', '9926.HK', '865166.TI', '510300.SH', '900901.SH')))


def page_html(page, count=2, last=2):
    codes = [f'600{page * 100 + i:03d}' for i in range(count)]
    rows = ''.join(f'<tr><td>{i + 1}</td><td>{codes[i]}</td><td>股票{i}</td></tr>' for i in range(count))
    rows += '<tr><td>99</td><td>TSLA</td><td>海外</td></tr><tr><td>100</td><td>900901</td><td>B股</td></tr>'
    return (f'<!DOCTYPE html><div class="board-hq"><h3>卫星导航<span>885574</span></h3></div>'
            f'<table><tbody>{rows}</tbody></table><div id="m-page"><a page="1">1</a><a page="{last}">尾页</a></div>')


class FakeResponse:
    def __init__(self, text, url='https://q.10jqka.com.cn/gn/detail/code/300722/'):
        self.content = text.encode('gb18030')
        self.url = url

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.headers = {}
        self.calls = []
        self.closed = False

    def get(self, url, timeout):
        self.calls.append(url)
        page = int(url.rstrip('/').split('/page/')[-1]) if '/page/' in url else 1
        return FakeResponse(self.pages[page], url)

    def close(self):
        self.closed = True


source = dict(members.OVERSOLD_CONCEPT_SOURCES['卫星互联网'], name='卫星互联网')
session = FakeSession({1: page_html(1, 3, 2), 2: page_html(2, 4, 2)})
parsed = members.fetch_public_concept_members(source, '20261123', session=session, delay=0)
check('公开分页解析h3身份代码与完整A股成员', parsed['memberCount'] == 7 and parsed['pageCount'] == 2
      and len(session.calls) == 2 and parsed['asOf'] == '20261123'
      and all(members.is_real_a_share_code(c) for c in parsed['members'])
      and 'TSLA' not in parsed['members'] and '900901' in parsed['rejectedNonA'], parsed)
try:
    bad = dict(source, code='865166.TI')
    members.parse_public_concept_page(page_html(1), bad)
    identity_rejected = False
except ValueError as exc:
    identity_rejected = '身份不符' in str(exc)
check('指数身份不符不静默改映射', identity_rejected)

login_session = FakeSession({1: page_html(1, 3, 1)})
login_session.pages[1] = '<script>login</script>'
login_response = FakeResponse('<script>login</script>', 'https://q.10jqka.com.cn/account/login/')
login_session.get = lambda url, timeout: login_response
try:
    members.fetch_public_concept_members(source, '20261123', session=login_session, delay=0)
    login_rejected = False
except RuntimeError as exc:
    login_rejected = '不完整成员' in str(exc)
check('公开页跳登录拒绝使用不完整成分', login_rejected)


class MemberPro:
    def __init__(self, mode):
        self.mode = mode
        self.calls = []

    def ths_member(self, **kwargs):
        self.calls.append(kwargs)
        if self.mode == 'error':
            raise RuntimeError('受控成员失败')
        if self.mode == 'empty':
            return pd.DataFrame()
        return pd.DataFrame([{'con_code': code} for code in
                             ['600000.SH', '000001.SZ', '300750.SZ', '688001.SH', '920001.BJ', 'TSLA', '9926.HK']])


original_sources = members.OVERSOLD_CONCEPT_SOURCES
original_session = members.requests.Session
original_fetch = members.fetch_public_concept_members
members.OVERSOLD_CONCEPT_SOURCES = {'卫星互联网': copy.deepcopy(original_sources['卫星互联网'])}
members.requests.Session = lambda: FakeSession({1: page_html(1, 3, 2), 2: page_html(2, 4, 2)})
try:
    pro = MemberPro('ok')
    cache = {'concepts': [{'name': '卫星互联网'}], 'ths_members': {'OLD': ['TSLA']}, 'unrelated': 42}
    records, errors = members.ensure_oversold_concept_members(pro, '20261120', cache)
    check('Tushare优先且海外成员剔除', not errors and records['卫星互联网']['memberCount'] == 5
          and len(pro.calls) == 1 and records['卫星互联网']['source'] == members.TUSHARE_MEMBER_SOURCE
          and all(members.is_real_a_share_code(c) for c in records['卫星互联网']['members']), records)
    calls = []
    def save(updated):
        calls.append(copy.deepcopy(updated))
    fallback_records = {}
    for mode in ('empty', 'error'):
        def fake_fetch(raw, as_of, session=None, delay=0, _mode=mode):
            return {'name': '卫星互联网', 'indexName': '卫星导航', 'code': '885574.TI', 'queryCode': '300722',
                    'members': ['600000.SH', '000001.SZ', '300750.SZ', '688001.SH', '920001.BJ'],
                    'memberCount': 5, 'source': members.PUBLIC_MEMBER_SOURCE, 'asOf': as_of,
                    'fallbackReason': raw.get('fallbackReason')}
        members.fetch_public_concept_members = fake_fetch
        records, errors = members.ensure_oversold_concept_members(MemberPro(mode), '20261120', cache, save)
        fallback_records[mode] = records
        check(f'Tushare {mode}使用真实公开兜底并保留其它缓存', not errors and records['卫星互联网']['memberCount'] == 5
              and records['卫星互联网']['source'] == members.PUBLIC_MEMBER_SOURCE
              and cache['concepts'] == [{'name': '卫星互联网'}] and cache['ths_members'] == {'OLD': ['TSLA']}
              and calls[-1]['unrelated'] == 42, records)
    stale_cache = {'oversoldConceptMembers': {'卫星互联网': dict(records['卫星互联网'], asOf='20261119')}}
    before = len(calls)
    members.fetch_public_concept_members = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('不应绕过'))
    records, errors = members.ensure_oversold_concept_members(MemberPro('ok'), '20261120', stale_cache, save)
    fresh_records, fresh_errors = members.ensure_oversold_concept_members(MemberPro('error'), '20261120', {
        'oversoldConceptMembers': records}, save)
    check('成员缓存asOf隔离当日可复用且陈旧不冒充', len(calls) > before and not fresh_errors
          and fresh_records['卫星互联网']['members'] == records['卫星互联网']['members'], fresh_records)
finally:
    members.OVERSOLD_CONCEPT_SOURCES = original_sources
    members.requests.Session = original_session
    members.fetch_public_concept_members = original_fetch


class HistoryPro:
    def __init__(self):
        self.calls = []
        self.dates = pd.bdate_range('2026-01-05', '2026-03-31').strftime('%Y%m%d').tolist()

    def trade_cal(self, **kwargs):
        return pd.DataFrame({'cal_date': self.dates})

    def daily_basic(self, **kwargs):
        date = kwargs['trade_date']
        self.calls.append(date)
        return pd.DataFrame([{'ts_code': f'60000{i}.SH', 'trade_date': date,
                              'pe_ttm': 10 + i, 'pb': 1 + i / 10} for i in range(6)])


history_spec = {'type': 'concept', 'code': '886069.TI', 'name': '人形机器人',
                'members': {f'60000{i}.SH' for i in range(6)}}
history_spec['membershipFingerprint'] = ud._spec_membership_fingerprint(history_spec)
with tempfile.TemporaryDirectory() as tmp:
    old_path = ud.SECTOR_VALUATION_HISTORY_PATH
    ud.SECTOR_VALUATION_HISTORY_PATH = str(Path(tmp) / 'cache.json')
    dates = ['20260130', '20260227', '20260331']
    old_row = {'tradeDate': '20260130', 'memberCount': 5, 'snapshotCount': 0, 'peCount': 0,
               'peCoverage': 0, 'peTtmMedian': 999}
    Path(ud.SECTOR_VALUATION_HISTORY_PATH).write_text(json.dumps({'sectorValuationHistory': {'rows': {
        d: {'concept:865166.TI': dict(old_row, tradeDate=d), 'industry:KEEP': {'tradeDate': d, 'keep': True}}
        for d in dates}}}), encoding='utf-8')
    try:
        pro = HistoryPro()
        result = ud._update_sector_valuation_history(pro, '20260415', [history_spec])
        check('全局日期已有但新组键缺失仍逐月补抓', pro.calls == dates and result['lastRequestedMonthEnds'] == 3
              and result['lastAddedMonthEnds'] == 3 and result['lastAddedGroupKeys'] == 3, result)
        check('新键用真实新成员计算不复制旧海外零记录且保留其它键', all(
            result['rows'][d]['concept:886069.TI']['snapshotCount'] == 6
            and result['rows'][d]['concept:886069.TI']['peTtmMedian'] != 999
            and result['rows'][d]['concept:865166.TI']['snapshotCount'] == 0
            and result['rows'][d]['industry:KEEP'] == {'tradeDate': d, 'keep': True} for d in dates))
        second = HistoryPro()
        ud._update_sector_valuation_history(second, '20260415', [history_spec])
        changed = dict(history_spec, members=set(history_spec['members']) | {'601888.SH'})
        changed['membershipFingerprint'] = ud._spec_membership_fingerprint(changed)
        third = HistoryPro()
        ud._update_sector_valuation_history(third, '20260415', [changed])
        check('同组键成分指纹一致不重复变化才重采', second.calls == [] and third.calls == dates,
              {'unchangedCalls': second.calls, 'changedCalls': third.calls})
    finally:
        ud.SECTOR_VALUATION_HISTORY_PATH = old_path


codes10 = [f'6000{i:02d}.SH' for i in range(10)]
records6 = {c: {'peTtm': 10, 'pb': 1} for c in codes10[:6]}
six = group_valuation_snapshot(codes10, records6)
check('60覆盖率边界不降低', six['peCount'] == 6 and six['peCoverage'] == .6
      and history_valuation_position(dict(six, tradeDate='20261120'), [])['historyStatus'] == 'insufficient')
four = dict(six, peCount=4, peCoverage=.4, pbCount=4, pbCoverage=.4)
check('5只数量门与60覆盖任一不足均不可排', history_valuation_position(four, [])['historyStatus'] == 'coverage_insufficient')
codes5 = codes10[:5]
current5 = dict(group_valuation_snapshot(codes5, {c: {'peTtm': 10, 'pb': 1} for c in codes5}), tradeDate='20261120')
history23 = [dict(group_valuation_snapshot(codes5, {c: {'peTtm': 9, 'pb': 1} for c in codes5}), tradeDate=f'2024{i:02d}28')
             for i in range(1, 24)]
check('5只边界及24样本含当前点', history_valuation_position(current5, history23)['rankEligible']
      and history_valuation_position(current5, history23)['peHistorySamples'] == 24
      and not history_valuation_position(current5, history23[:-1])['rankEligible'])
check('非PIT生存者偏差持续明示', ud.OVERSOLD_VALUE_METHOD.find('至少24个') >= 0
      and ud.MIN_METRIC_COUNT == 5 and ud.MIN_METRIC_COVERAGE == .6 and ud.MIN_HISTORY_SAMPLES == 24)


class SnapshotPro:
    def __init__(self, date):
        self.date = date

    def daily_basic(self, **kwargs):
        return pd.DataFrame([{'ts_code': c, 'trade_date': self.date, 'close': 10,
                              'total_mv': (10 - i) * 10000, 'pe_ttm': 10, 'pb': 1}
                             for i, c in enumerate(codes10)])


cache_data = {'sw_list': [{'code': 'I1', 'name': '测试行业'}], 'sw_members': {'I1': codes10},
              'concepts': [], 'stock_info': {c: {'name': f'股票{i}'} for i, c in enumerate(codes10)}, 'circ_mv': {}}
with tempfile.TemporaryDirectory() as tmp:
    old_group, old_history = ud.DIVIDEND_GROUP_CACHE_PATH, ud.SECTOR_VALUATION_HISTORY_PATH
    old_update = ud._update_sector_valuation_history
    ud.DIVIDEND_GROUP_CACHE_PATH = str(Path(tmp) / 'groups.json')
    ud.SECTOR_VALUATION_HISTORY_PATH = str(Path(tmp) / 'empty.json')
    Path(ud.DIVIDEND_GROUP_CACHE_PATH).write_text(json.dumps(cache_data), encoding='utf-8')
    ud._update_sector_valuation_history = lambda *args: {'rows': {}, 'fetchError': None}
    try:
        outcomes = {}
        for label, date in [('current', '20261120'), ('stale', '20261119'), ('future', '20261121'), ('missing', None)]:
            data = {'sectorFlows': {'trade_date': '2026-11-20'},
                    'longWindow': {'window': 'open', 'windowType': 'extreme_rebound', 'extremeRebound': {'active': True}}}
            ud.build_oversold_value_directions(SnapshotPro(date), '20261120', data)
            block = data['oversoldValueDirections']
            group = block['industries'][0]
            outcomes[label] = {'status': block['valuationStatus'], 'rank': group['rankEligible'],
                               'historyStatus': group['historyStatus'], 'snapshotDate': block['snapshotDate']}
        check('当前陈旧未来及日期缺失严格隔离', outcomes['current']['status'] == 'ok'
              and all(outcomes[x]['status'] == 'stale' and not outcomes[x]['rank'] for x in ('stale', 'future', 'missing'))
              and outcomes['current']['snapshotDate'] == '20261120', outcomes)
        data = {'sectorFlows': {'trade_date': '2026-11-20'},
                'longWindow': {'window': 'open', 'windowType': 'extreme_rebound', 'extremeRebound': {'active': True}}}
        ud.build_oversold_value_directions(SnapshotPro('20261120'), '20261120', data)
        group = data['oversoldValueDirections']['industries'][0]
        check('双龙头按真实总市值前2且无市值不凑数', [x['code'] for x in group['leaders']] == codes10[:2]
              and all(x['tradeDate'] == '20261120' for x in group['leaders']), group['leaders'])
    finally:
        ud.DIVIDEND_GROUP_CACHE_PATH, ud.SECTOR_VALUATION_HISTORY_PATH = old_group, old_history
        ud._update_sector_valuation_history = old_update

# 生产整合：新代码独立成员缓存替换旧海外代码，双龙头与历史键均使用新成分。
repaired_codes = codes10[:6]
repaired_spec = {'type': 'concept', 'code': '886069.TI', 'name': '人形机器人', 'members': set(repaired_codes)}
fingerprint = ud._spec_membership_fingerprint(repaired_spec)
repaired_cache = {'sw_list': [], 'sw_members': {}, 'concepts': [{'name': '人形机器人', 'code': '865166.TI'}],
                  'ths_members': {'865166.TI': ['TSLA']}, 'stock_info': cache_data['stock_info'], 'circ_mv': {},
                  'oversoldConceptMembers': {'人形机器人': {
                      'name': '人形机器人', 'indexName': '人形机器人', 'code': '886069.TI', 'queryCode': '309119',
                      'members': repaired_codes, 'memberCount': 6, 'source': members.TUSHARE_MEMBER_SOURCE,
                      'asOf': '20261120', 'identityStatus': 'verified'}}}
history_rows = {}
for i in range(1, 24):
    date = f'2024{i:02d}28'
    snap = dict(group_valuation_snapshot(repaired_codes, {c: {'peTtm': 9, 'pb': 1} for c in repaired_codes}),
                tradeDate=date, membershipFingerprint=fingerprint)
    history_rows[date] = {'concept:886069.TI': snap,
                          'concept:865166.TI': {'tradeDate': date, 'memberCount': 5, 'snapshotCount': 0}}
with tempfile.TemporaryDirectory() as tmp:
    old_group, old_history = ud.DIVIDEND_GROUP_CACHE_PATH, ud.SECTOR_VALUATION_HISTORY_PATH
    ud.DIVIDEND_GROUP_CACHE_PATH = str(Path(tmp) / 'groups.json')
    ud.SECTOR_VALUATION_HISTORY_PATH = str(Path(tmp) / 'history.json')
    Path(ud.DIVIDEND_GROUP_CACHE_PATH).write_text(json.dumps(repaired_cache), encoding='utf-8')
    Path(ud.SECTOR_VALUATION_HISTORY_PATH).write_text(json.dumps({'sectorValuationHistory': {
        'rows': history_rows, 'fetchError': None}}), encoding='utf-8')
    try:
        data = {'sectorFlows': {'trade_date': '2026-11-20'},
                'longWindow': {'window': 'open', 'windowType': 'extreme_rebound', 'extremeRebound': {'active': True}}}
        ud.build_oversold_value_directions(SnapshotPro('20261120'), '20261120', data)
        block = data['oversoldValueDirections']
        group = block['concepts'][0]
        check('生产整合新A股代码历史分位双龙头与来源asOf', group['code'] == '886069.TI'
              and group['memberCount'] == 6 and group['snapshotCount'] == 6 and group['rankEligible']
              and group['peHistorySamples'] == 24 and group['pbHistorySamples'] == 24
              and [x['code'] for x in group['leaders']] == repaired_codes[:2]
              and group['membershipAsOf'] == '20261120' and group['membershipSource'] == members.TUSHARE_MEMBER_SOURCE
              and block['counts']['snapshotMissingGroupCount'] == 0, group)
    finally:
        ud.DIVIDEND_GROUP_CACHE_PATH, ud.SECTOR_VALUATION_HISTORY_PATH = old_group, old_history

assert data_sha == {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in DATA}
failed = [name for name, result in checks.items() if not result['pass']]
report = {'task': 'history-sample', 'passed': len(checks) - len(failed), 'total': len(checks),
          'failed': failed, 'checks': checks, 'productionDataUntouched': True,
          'thresholds': {'minMetricCount': 5, 'minMetricCoverage': .6, 'minHistorySamplesIncludingCurrent': 24},
          'note': 'fixture验证不代表真实历史估值已覆盖；真实覆盖单独报告。'}
(ROOT / 'zz_history_sample_regress.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'passed': report['passed'], 'total': report['total'], 'failed': failed}, ensure_ascii=False, indent=2))
if failed:
    raise SystemExit(1)
