# -*- coding: utf-8 -*-
"""任务107：RSI6极端窗全A股息率TTM Top20；临时缓存+FakePro，零真实API/生产数据写入。"""
import copy
import hashlib
import importlib.util
import inspect
import json
import tempfile
from pathlib import Path

import pandas as pd
import update_data as ud

ROOT = Path(__file__).resolve().parent
AS_OF = '20261030'
ud.API_DELAY = 0
checks = {}
DATA_FILES = ['public/fund_data.json', 'src/data/fund_data.json']
data_sha_before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in DATA_FILES}


def check(name, condition, evidence=None):
    checks[name] = {'pass': bool(condition), 'evidence': evidence}


def row(code, dv, name=None, date=AS_OF, pe=10.0, pb=1.0, mv=1000000.0):
    return {'ts_code': code, 'trade_date': date, 'close': 10.0,
            'total_mv': mv, 'dv_ttm': dv, 'pe_ttm': pe, 'pb': pb}


valid_rows = [
    row('600000.SH', 12.0, pe=-15.0, mv=1.0),                 # 亏损PE、小市值，仍第一
    row('600001.SH', 11.8),                                   # *ST且明确排雷命中，剔除
    row('000001.SZ', 11.8),                                   # 三只并列，代码升序
    row('000002.SZ', 11.8),
    row('300001.SZ', 11.7, mv=0.01),                          # ST已覆盖未命中，保留
    row('920001.BJ', 11.6),                                   # 北交所真实A股
    row('600002.SH', 11.5, mv=None),                          # 缺市值不删除
]
valid_rows += [row(f'600{100 + i}.SH', 10.9 - i * 0.1) for i in range(16)]  # 合计23只有效
invalid_rows = [
    row('000300.SH', 999), row('510300.SH', 998),            # 指数/ETF不得混入
    row('900901.SH', 997), row('200001.SZ', 996),            # B股不得混入
    row('600200.SH', None), row('600201.SH', float('nan')),
    row('600202.SH', 0), row('600203.SH', -3),
]
ROWS = valid_rows + invalid_rows

stock_info = {r['ts_code']: {'name': f'股票{r["ts_code"][:6]}'} for r in valid_rows}
stock_info['600001.SH']['name'] = '*ST高息'
stock_info['000001.SZ']['name'] = '并列平安'
stock_info['300001.SZ']['name'] = 'ST未命中'
stock_industry = {r['ts_code']: '测试行业' for r in valid_rows}
stock_industry['600000.SH'] = '银行'
stock_industry.pop('000001.SZ')
stock_industry.pop('300001.SZ')
CACHE = {
    'stock_info': stock_info,
    'stock_industry': stock_industry,
    'sw_list': [{'code': 'I1', 'name': '保险'}],
    'sw_members': {'I1': ['000001.SZ']},
}


class FakePro:
    def __init__(self, rows=None, fail=False):
        self.rows = list(rows or [])
        self.fail = fail
        self.calls = []

    def daily_basic(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError('受控全A快照失败')
        return pd.DataFrame(self.rows)


def extreme_data():
    return {
        'sectorFlows': {'trade_date': '2026-10-30'},
        'longWindow': {'window': 'open', 'windowType': 'extreme_rebound',
                       'extremeRebound': {'active': True}},
        'mineWatch': {
            'checkedCodes': ['600000.SH', '600001.SH', '300001.SZ', '600100.SH'],
            'items': [
                {'code': '600001.SH', 'types': ['基本面'],
                 'details': [{'type': '基本面', 'detail': '中报亏损', 'date': '20260630'}]},
                {'code': '600100.SH', 'types': ['交易风险'],
                 'details': [{'type': '交易风险', 'detail': '受控异常交易', 'date': '20261029'}]},
            ],
        },
        # 原RSI14独立高股息模块必须原样保留，不被新子模块覆盖。
        'dividendWatch': {'visible': True, 'count': 1, 'catalystGroupCount': 1,
                          'items': [{'code': 'LEGACY.SH'}], 'groups': [{'name': '原催化组'}]},
    }


with tempfile.TemporaryDirectory() as tmp:
    cache_path = Path(tmp) / 'vcp_cache.json'
    cache_path.write_text(json.dumps(CACHE, ensure_ascii=False), encoding='utf-8')
    old_path = ud.DIVIDEND_GROUP_CACHE_PATH
    ud.DIVIDEND_GROUP_CACHE_PATH = str(cache_path)
    try:
        inactive_specs = [
            ('普通open', {'window': 'open', 'windowType': 'standard', 'extremeRebound': {'active': False}}),
            ('普通half', {'window': 'half', 'windowType': 'standard', 'extremeRebound': {'active': False}}),
            ('普通closed', {'window': 'closed', 'windowType': 'standard', 'extremeRebound': {'active': False}}),
            ('观察窗', {'window': 'open', 'windowType': 'oversold_valuation_watch', 'extremeRebound': {'active': False}}),
        ]
        for label, lw in inactive_specs:
            data = extreme_data()
            data['longWindow'] = lw
            data['broadObservation'] = {'active': True}
            data['dividendWatch']['rsi6Top20'] = {'visible': True, 'count': 20, 'items': [{'code': 'OLD'}]}
            pro = FakePro(ROWS)
            ud.build_rsi6_dividend_top20(pro, AS_OF, data)
            block = data['dividendWatch']['rsi6Top20']
            check(f'{label}清空旧Top20且零请求', not block['visible'] and block['status'] == 'not_requested'
                  and block['count'] == 0 and block['items'] == [] and pro.calls == [], block)

        active = extreme_data()
        before_window = copy.deepcopy(active['longWindow'])
        pro = FakePro(ROWS)
        ud.build_rsi6_dividend_top20(pro, AS_OF, active)
        block = active['dividendWatch']['rsi6Top20']
        items = block['items']
        check('RSI6窗展示且不反向开门', block['visible'] and active['longWindow'] == before_window
              and active['dividendWatch']['visible'] and active['dividendWatch']['count'] == 1
              and active['dividendWatch']['items'] == [{'code': 'LEGACY.SH'}], active['longWindow'])
        check('同一有效日只请求一次全A daily_basic并含股息估值字段', len(pro.calls) == 1
              and pro.calls[0]['trade_date'] == AS_OF
              and pro.calls[0]['fields'] == 'ts_code,trade_date,close,total_mv,dv_ttm,pe_ttm,pb', pro.calls)
        check('全A范围含北交所和VCP池外且严格Top20', block['status'] == 'ok' and block['count'] == 20
              and block['eligibleCount'] == 23 and len(items) == 20
              and any(x['code'] == '920001.BJ' for x in items)
              and any(x['code'] == '300001.SZ' for x in items)
              and all(x['code'] not in ('000300.SH', '510300.SH', '900901.SH', '200001.SZ') for x in items),
              {'count': block['count'], 'eligible': block['eligibleCount'], 'codes': [x['code'] for x in items]})
        expected_original = sorted(valid_rows, key=lambda r: (-r['dv_ttm'], r['ts_code']))
        original_ranks = {r['ts_code']: i for i, r in enumerate(expected_original, 1)}
        expected_codes = [r['ts_code'] for r in expected_original if r['ts_code'] not in ('600001.SH', '600100.SH')][:20]
        check('原始股息率降序并列代码升序且最终名次重排', [x['code'] for x in items[:3]] == ['600000.SH', '000001.SZ', '000002.SZ']
              and [x['code'] for x in items] == expected_codes
              and [x['rank'] for x in items] == list(range(1, 21))
              and all(x['originalRank'] == original_ranks[x['code']] for x in items), items[:4])
        check('缺失NaN零负股息不参与且不补0', block['eligibleCount'] == 23
              and all(x['code'] not in ('600200.SH', '600201.SH', '600202.SH', '600203.SH') for x in items)
              and all(x['dvTtm'] > 0 for x in items), block['reasons'])
        check('亏损PE小市值和缺市值均不影响原榜', items[0]['code'] == '600000.SH'
              and items[0]['peTtm'] == -15 and items[0]['totalMvYi'] == 0.0
              and any(x['code'] == '600002.SH' and x['totalMv'] is None for x in items), items[0])
        st_item = next(x for x in items if x['code'] == '300001.SZ')
        check('ST未命中保留并标记且命中ST剔除', st_item['isST'] and st_item['name'] == 'ST未命中'
              and st_item['mineStatus'] == 'clear' and '不代表无风险' in st_item['mineNote']
              and all(x['code'] != '600001.SH' for x in items), st_item)
        check('中文名和行业归属含申万回退及未标注', items[0]['name'] == '股票600000' and items[0]['industry'] == '银行'
              and next(x for x in items if x['code'] == '000001.SZ')['industry'] == '保险'
              and st_item['industry'] == '行业未标注', items[:4])
        check('已覆盖未命中与未覆盖未核验严格区分', items[0]['mineStatus'] == 'clear'
              and '不代表无风险' in items[0]['mineNote']
              and next(x for x in items if x['code'] == '600101.SH')['mineStatus'] == 'unchecked'
              and next(x for x in items if x['code'] == '600101.SH')['mineNote'] == '既有排雷未覆盖，未核验'
              and all(x['mineStatus'] != 'hit' for x in items), items[:4])
        check('原Top20多只明确命中剔除且第21名及以后顺延补足', block['excludedCount'] == 2
              and block['remainingCandidateCount'] == 21 and len(block['excludedItems']) == 2
              and [x['code'] for x in block['excludedItems']] == ['600001.SH', '600100.SH']
              and [x['originalRank'] for x in block['excludedItems']] == [4, 8]
              and [(x['code'], x['originalRank']) for x in items[-2:]] == [('600113.SH', 21), ('600114.SH', 22)]
              and all(x['code'] not in ('600001.SH', '600100.SH') for x in items), block['excludedItems'])
        check('剔除摘要完整含原始名次代码股息率和原因', all(
              all(key in x for key in ('originalRank', 'code', 'name', 'dvTtm', 'mineTypes', 'mineDetails', 'reason'))
              for x in block['excludedItems'])
              and '中报亏损' in block['excludedItems'][0]['reason']
              and '受控异常交易' in block['excludedItems'][1]['reason']
              and any('剔除代码/原因' in reason and '600100.SH' in reason for reason in block['reasons']), block['reasons'])
        check('快照日期TTM口径和一次性分红风险明示', block['snapshotDate'] == AS_OF
              and all(x['tradeDate'] == AS_OF for x in items)
              and 'dv_ttm' in block['source'] and '一次性/特别分红' in block['note']
              and '高股息不等于安全或买点' in block['note'], block['note'])

        fewer = extreme_data()
        ud.build_rsi6_dividend_top20(FakePro(valid_rows[2:5]), AS_OF, fewer)
        fewer_block = fewer['dividendWatch']['rsi6Top20']
        check('不足20如实显示实际数量不凑数', fewer_block['visible'] and fewer_block['status'] == 'ok'
              and fewer_block['count'] == 3 and len(fewer_block['items']) == 3
              and '实际展示3只' in fewer_block['reasons'][0]
              and any('候选不足或数据限制' in reason for reason in fewer_block['reasons']), fewer_block)

        missing_mine = extreme_data()
        missing_mine.pop('mineWatch')
        ud.build_rsi6_dividend_top20(FakePro(ROWS), AS_OF, missing_mine)
        missing_block = missing_mine['dividendWatch']['rsi6Top20']
        check('排雷整体缺失不剔除且全部未核验', missing_block['mineCoverageStatus'] == 'missing'
              and missing_block['excludedCount'] == 0 and missing_block['excludedItems'] == []
              and missing_block['remainingCandidateCount'] == 23 and missing_block['count'] == 20
              and all(x['mineStatus'] == 'unchecked' and not x['mineCovered'] for x in missing_block['items'])
              and all('未核验' in x['mineNote'] for x in missing_block['items'])
              and all(x['mineStatus'] != 'clear' for x in missing_block['items']), missing_block['reasons'])
        check('排雷整体缺失不把未知写成无风险且保留ST', any(x['code'] == '600001.SH' and x['isST'] for x in missing_block['items'])
              and any('未把未知当成未命中或无风险' in reason for reason in missing_block['reasons'])
              and '未剔除且全部标未核验' in ud._rsi6_dividend_top20_summary(missing_mine), missing_block['note'])

        stale = extreme_data()
        stale['dividendWatch']['rsi6Top20'] = {'visible': True, 'count': 20, 'items': [{'code': 'OLD'}]}
        ud.build_rsi6_dividend_top20(FakePro([dict(r, trade_date='20261029') for r in ROWS]), AS_OF, stale)
        stale_block = stale['dividendWatch']['rsi6Top20']
        check('陈旧快照锁榜清旧且不伪装当前', stale_block['visible'] and stale_block['status'] == 'stale'
              and stale_block['rankingLocked'] and stale_block['count'] == 0 and stale_block['items'] == []
              and stale_block['snapshotDate'] == '20261029' and stale_block['tradeDate'] == AS_OF
              and '不把旧日期伪装成当前' in stale_block['reasons'][0], stale_block)

        failed = extreme_data()
        failed['dividendWatch']['rsi6Top20'] = {'visible': True, 'count': 20, 'items': [{'code': 'OLD'}]}
        ud.build_rsi6_dividend_top20(FakePro(ROWS, fail=True), AS_OF, failed)
        failed_block = failed['dividendWatch']['rsi6Top20']
        check('API失败锁榜清旧且不影响RSI6门', failed_block['visible'] and failed_block['status'] == 'missing'
              and failed_block['rankingLocked'] and failed_block['items'] == []
              and '受控全A快照失败' in failed_block['snapshotError'] and failed['longWindow'] == before_window, failed_block)

        empty = extreme_data()
        ud.build_rsi6_dividend_top20(FakePro([]), AS_OF, empty)
        empty_block = empty['dividendWatch']['rsi6Top20']
        check('空快照锁榜且不保留旧项', empty_block['visible'] and empty_block['status'] == 'missing'
              and empty_block['count'] == 0 and empty_block['items'] == [] and '为空' in empty_block['reasons'][0], empty_block)

        summary = ud._rsi6_dividend_top20_summary(active)
        check('总览第0步摘要含日期Top20与非买点提示', '全A股息率TTM Top20' in summary and AS_OF in summary
              and '高股息≠安全/买点' in summary, summary)
        ud.build_funnel(active)
        step0 = next(s for s in active['funnel']['steps'] if s['n'] == 0)
        check('后端漏斗第0步贯通Top20摘要', summary in step0['conclusion'], step0['conclusion'])
    finally:
        ud.DIVIDEND_GROUP_CACHE_PATH = old_path

# 原RSI14高股息函数逐字保护；任务106/103由对应完整回归另行强制执行。
spec = importlib.util.spec_from_file_location('update_data_task106_baseline_for107',
                                              ROOT / 'zz_update_data_task106_rsi6_baseline.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
for name in ('_dividend_group_catalyst', 'build_dividend_watch'):
    check(f'独立RSI14高股息函数未改:{name}',
          inspect.getsource(getattr(old, name)) == inspect.getsource(getattr(ud, name)), 'source identical')

production = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
types = (ROOT / 'src/hooks/useFundData.ts').read_text(encoding='utf-8')
weekly_ui = (ROOT / 'src/sections/WeeklySummary.tsx').read_text(encoding='utf-8')
funnel_ui = (ROOT / 'src/sections/funnelConclusions.ts').read_text(encoding='utf-8')
heatmap_ui = (ROOT / 'src/sections/SectorHeatmap.tsx').read_text(encoding='utf-8')
check('前端类型总览入口和唯一完整榜契约', 'rsi6Top20?: Rsi6DividendTop20' in types
      and 'originalRank: number' in types and 'excludedItems: Rsi6DividendExcludedItem[]' in types
      and 'mineCoverageStatus' in types and 'remainingCandidateCount' in types
      and 'dividendTop20Text' in weekly_ui and 'rsi6-dividend-top20' in weekly_ui
      and 'dividendTop20Text' in funnel_ui and 'top.items.map' in heatmap_ui
      and 'top.items.filter' not in heatmap_ui)
check('前端原始名次剔除顺延和风险文案契约', '快照{top.snapshotDate' in heatmap_ui
      and '股息率TTM' in heatmap_ui and '原#{r.originalRank}' in heatmap_ui
      and 'top.excludedItems.map' in heatmap_ui and '明确命中排雷剔除并顺延补足' in heatmap_ui
      and '未覆盖仅标未核验' in heatmap_ui and '已覆盖未命中不代表无风险' in heatmap_ui
      and '排雷只标记不删除' not in production + heatmap_ui
      and '排雷命中不删除' not in production + heatmap_ui
      and '既有排雷状态（只标记）' not in heatmap_ui and '一次性/特别分红' in production)

data_sha_after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in DATA_FILES}
check('两份生产fund_data字节未变', data_sha_before == data_sha_after, data_sha_after)

out = {'task': 107, 'asOf': AS_OF, 'checks': checks, 'dataSha256': data_sha_after}
(ROOT / 'zz_regress107.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {'checksPassed': sum(x['pass'] for x in checks.values()), 'checksTotal': len(checks),
           'failed': [k for k, v in checks.items() if not v['pass']], 'dataSha256': data_sha_after}
(ROOT / 'zz_regress107_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if summary['failed']:
    raise AssertionError(f'任务107检查失败: {summary["failed"]}')
