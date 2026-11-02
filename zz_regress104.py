# -*- coding: utf-8 -*-
"""任务104：极端强制开窗低估值方向；临时缓存+FakePro，零真实API/正式缓存写入。"""
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


def check(name, condition, evidence=None):
    checks[name] = {'pass': bool(condition), 'evidence': evidence}


def row(code, pe, pb, mv, date=AS_OF, close=10.0):
    return {'ts_code': code, 'trade_date': date, 'close': close,
            'total_mv': mv, 'pe_ttm': pe, 'pb': pb}


class FakePro:
    def __init__(self, rows, fail=False):
        self.rows = rows
        self.fail = fail
        self.calls = []

    def daily_basic(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError('受控API失败')
        return pd.DataFrame(self.rows)


def extreme_data():
    return {
        'sectorFlows': {'trade_date': '2026-10-30'},
        'longWindow': {'window': 'open', 'windowType': 'extreme_rebound',
                       'extremeRebound': {'active': True}},
        'mineWatch': {
            'checked': 2, 'checkedCodes': ['A002.SZ', 'C002.SZ'],
            'items': [{'code': 'LOSS.SZ', 'name': '*ST亏损', 'src': '测试',
                       'types': ['基本面'], 'details': [{'type': '基本面', 'detail': '中报亏损', 'date': '20260630'}]}],
        },
    }


def direction_rows(final_gain):
    days = pd.date_range(end='2026-10-23', periods=30, freq='W-FRI').strftime('%Y%m%d').tolist()
    closes = [100.0]
    for _ in range(28):
        closes.append(closes[-1] * 0.96)
    closes.append(closes[-1] * (1 + final_gain))
    rows = [[d, round(c, 6), 1000.0] for d, c in zip(days, closes)]
    return rows + [[AS_OF, round(closes[-1], 6), 1000.0]]


BASE_CACHE = {
    'sw_list': [
        {'code': 'I1', 'name': '低估值行业'},
        {'code': 'I2', 'name': '高估值行业'},
        {'code': 'I3', 'name': '覆盖不足行业'},
    ],
    'sw_members': {
        'I1': ['A001.SZ', 'A002.SZ', 'A003.SZ', 'A004.SZ', 'A005.SZ', 'LOSS.SZ', 'MISS.SZ'],
        'I2': ['H001.SZ', 'H002.SZ', 'H003.SZ', 'H004.SZ', 'H005.SZ'],
        'I3': ['N001.SZ', 'N002.SZ', 'N003.SZ', 'N004.SZ', 'N005.SZ', 'N006.SZ', 'N007.SZ'],
    },
    'concepts': [{'code': 'C1', 'name': '真实大概念'}],
    'ths_members': {'C1': ['C001.SZ', 'C002.SZ', 'C003.SZ', 'C004.SZ', 'C005.SZ']},
    'ths_index': {'真实大概念': 'C1'},
    'index_daily': {'I1': direction_rows(0.05), 'I2': direction_rows(0.10),
                    'I3': direction_rows(0.15), 'C1': direction_rows(0.20)},
    'circ_mv': {'MISS.SZ': 10_000_000, 'LOSS.SZ': 9_000_000,
                'C002.SZ': 8_000_000, 'C003.SZ': 8_000_000},
    'stock_info': {
        **{f'A{i:03d}.SZ': {'name': f'行业{i}'} for i in range(1, 6)},
        **{f'C{i:03d}.SZ': {'name': f'概念{i}'} for i in range(1, 6)},
        **{f'H{i:03d}.SZ': {'name': f'高估{i}'} for i in range(1, 6)},
        'LOSS.SZ': {'name': '*ST亏损'}, 'MISS.SZ': {'name': '缺估值龙头'},
        'OUTSIDE.SZ': {'name': '关系不标股票'},
    },
}

ROWS = [
    row('A001.SZ', 5, 0.5, 1_000_000), row('A002.SZ', 6, 0.6, 5_000_000),
    row('A003.SZ', 7, 0.7, 3_000_000), row('A004.SZ', 8, 0.8, 2_000_000),
    row('A005.SZ', 9, 0.9, 1_500_000), row('LOSS.SZ', -3, 0.4, 9_000_000),
    row('MISS.SZ', None, None, 10_000_000),
    row('C001.SZ', 4, 0.3, 1_000_000), row('C002.SZ', 5, 0.4, 8_000_000),
    row('C003.SZ', 6, 0.5, 8_000_000), row('C004.SZ', 7, 0.6, 2_000_000),
    row('C005.SZ', 8, 0.7, 1_000_000),
    # 关系不标股票：有快照、低估值且市值极大，但不是任何真实成员，绝不能进入。
    row('OUTSIDE.SZ', 1, 0.1, 99_000_000),
    *[row(f'H{i:03d}.SZ', 100 + i, 10 + i, 1_000_000) for i in range(1, 6)],
    *[row(f'N{i:03d}.SZ', 20 + i, 2 + i, 1_000_000) for i in range(1, 5)],
    # 全A横截面其余高估值证券：只参与市场分位，不属于任何行业/概念组。
    *[row(f'X{i:03d}.SZ', 200 + i, 20 + i, 1000) for i in range(1, 31)],
]


with tempfile.TemporaryDirectory() as tmp:
    cache_path = Path(tmp) / 'vcp_cache.json'
    cache_path.write_text(json.dumps(BASE_CACHE, ensure_ascii=False), encoding='utf-8')
    old_path = ud.DIVIDEND_GROUP_CACHE_PATH
    ud.DIVIDEND_GROUP_CACHE_PATH = str(cache_path)
    try:
        # 正常关窗：即使塞入旧active名单，也必须清空且零API。
        normal = extreme_data()
        normal['longWindow'] = {'window': 'closed', 'windowType': 'standard', 'extremeRebound': {'active': False}}
        normal['oversoldValueDirections'] = {'visible': True, 'industries': [{'name': '旧行业'}], 'concepts': [{'name': '旧概念'}]}
        normal_pro = FakePro(ROWS)
        ud.build_oversold_value_directions(normal_pro, AS_OF, normal)
        normal_block = normal['oversoldValueDirections']
        check('正常关窗零请求并清旧active名单', not normal_block['visible'] and not normal_block['industries']
              and not normal_block['concepts'] and normal_block['counts']['directionCount'] == 0
              and normal_pro.calls == [], normal_block)

        # 普通open也不能触发。
        ordinary_open = extreme_data()
        ordinary_open['longWindow']['windowType'] = 'standard'
        ordinary_open['longWindow']['extremeRebound']['active'] = False
        ordinary_pro = FakePro(ROWS)
        ud.build_oversold_value_directions(ordinary_pro, AS_OF, ordinary_open)
        check('普通open不借低估值展示或开门', not ordinary_open['oversoldValueDirections']['visible']
              and ordinary_open['longWindow']['windowType'] == 'standard' and ordinary_pro.calls == [])

        # 任务102观察窗单独触发无效；即便残留extreme active但类型不对也不触发。
        observation = extreme_data()
        observation['longWindow']['windowType'] = 'oversold_valuation_watch'
        observation['broadObservation'] = {'active': True}
        observation_pro = FakePro(ROWS)
        ud.build_oversold_value_directions(observation_pro, AS_OF, observation)
        check('任务102观察窗不能单独触发模块', not observation['oversoldValueDirections']['visible']
              and observation_pro.calls == [] and observation['oversoldValueDirections']['industries'] == [])

        active = extreme_data()
        active_pro = FakePro(ROWS)
        ud.build_oversold_value_directions(active_pro, AS_OF, active)
        block = active['oversoldValueDirections']
        check('极端三条件触发且仅一次全A请求', block['visible'] and len(active_pro.calls) == 1
              and active_pro.calls[0]['trade_date'] == AS_OF
              and active_pro.calls[0]['fields'] == 'ts_code,trade_date,close,total_mv,pe_ttm,pb', active_pro.calls)
        check('行业与真实大概念均由RSI6入围', len(block['industries']) == 3
              and [g['name'] for g in block['concepts']] == ['真实大概念']
              and block['counts']['directionCount'] == 4, block['counts'])
        industry = next(g for g in block['industries'] if g['name'] == '低估值行业')
        concept = block['concepts'][0]
        check('亏损非正PE不进中位数且单独披露', industry['lossPeCount'] == 1 and industry['peTtmMedian'] == 7
              and industry['commonCount'] == 5 and industry['commonCoverage'] == round(5 / 7, 4), industry)
        check('缺失估值不补0且龙头如实披露', [x['code'] for x in industry['leaders']] == ['MISS.SZ', 'LOSS.SZ']
              and industry['leaders'][0]['peTtm'] is None and industry['leaders'][0]['pb'] is None
              and industry['leaders'][0]['peStatus'] == '估值快照缺失'
              and industry['leaders'][1]['peStatus'].startswith('亏损/非正PE')
              and industry['leaders'][1]['isST'], industry['leaders'])
        check('概念真实归属关系不标股票不得进入', all(x['code'] != 'OUTSIDE.SZ' for x in concept['leaders'])
              and concept['memberCount'] == 5 and concept['snapshotCount'] == 5, concept)
        check('总市值前2且同市值代码升序确定排序', [x['code'] for x in concept['leaders']] == ['C002.SZ', 'C003.SZ']
              and all(x['totalMv'] == 8_000_000 for x in concept['leaders']), concept['leaders'])
        check('排雷命中已覆盖未命中与未覆盖严格区分', industry['leaders'][0]['mineNote'] == '既有排雷未覆盖'
              and industry['leaders'][1]['mineTypes'] == ['基本面']
              and concept['leaders'][0]['mineNote'] == '既有排雷已覆盖，未命中既有规则（不代表无风险）'
              and concept['leaders'][1]['mineNote'] == '既有排雷未覆盖',
              [x['mineNote'] for x in industry['leaders'] + concept['leaders']])
        check('高估值与覆盖不足仅统计不过滤RSI6方向', block['counts']['highValuationGroupCount'] == 2
              and block['counts']['insufficientCoverageGroupCount'] == 1
              and block['counts']['rsiInsufficientGroupCount'] == 0
              and all(g['name'] in ('低估值行业', '高估值行业', '覆盖不足行业') for g in block['industries']),
              block['counts'])
        check('口径明示估值仅参考', '不参与方向入围或排序' in block['valuationMethod']
              and '极端超卖≠立即反转' in block['note'] and 'PE/PB不参与入围' in block['note'])
        summary = ud._oversold_value_directions_summary(active)
        check('摘要含各组前2龙头和非反转提示', all(x in summary for x in
              ('低估值行业[周RSI6', '缺估值龙头、*ST亏损', '真实大概念[周RSI6', '概念2、概念3',
               '极端超卖≠立即反转', '非操作买卖建议')), summary)
        ud.build_funnel(active)
        step0 = next(s for s in active['funnel']['steps'] if s['n'] == 0)
        check('后端漏斗第0步贯通同一摘要', summary in step0['conclusion'], step0['conclusion'])
        check('模块未反向修改极端长窗', active['longWindow']['window'] == 'open'
              and active['longWindow']['windowType'] == 'extreme_rebound'
              and active['longWindow']['extremeRebound']['active'] is True)

        stale = extreme_data()
        stale_pro = FakePro([dict(r, trade_date='20261029') for r in ROWS])
        ud.build_oversold_value_directions(stale_pro, AS_OF, stale)
        stale_block = stale['oversoldValueDirections']
        check('陈旧快照标缺失但保留RSI6名单', stale_block['visible'] and stale_block['coverage']['stale']
              and stale_block['snapshotDate'] == '20261029' and len(stale_block['industries']) == 3
              and len(stale_block['concepts']) == 1 and stale_block['valuationStatus'] == 'stale'
              and '不等于本批有效日' in stale_block['reasons'][0], stale_block)

        failed = extreme_data()
        failed_pro = FakePro([], fail=True)
        ud.build_oversold_value_directions(failed_pro, AS_OF, failed)
        check('API失败不清空门控或RSI6名单', failed['oversoldValueDirections']['visible']
              and failed['longWindow']['window'] == 'open'
              and failed['oversoldValueDirections']['counts']['directionCount'] == 4
              and failed['oversoldValueDirections']['valuationStatus'] == 'missing'
              and '失败' in failed['oversoldValueDirections']['reasons'][0])

        # 高估值真实组仍按RSI6入榜；关系不标的低估值股票不得混入。
        high_cache = {
            'sw_list': [{'code': 'I2', 'name': '高估值行业'}],
            'sw_members': {'I2': BASE_CACHE['sw_members']['I2']},
            'concepts': [], 'ths_members': {}, 'ths_index': {}, 'stock_info': BASE_CACHE['stock_info'],
            'index_daily': {'I2': BASE_CACHE['index_daily']['I2']},
        }
        cache_path.write_text(json.dumps(high_cache, ensure_ascii=False), encoding='utf-8')
        high = extreme_data()
        high_rows = [r for r in ROWS if r['ts_code'].startswith('H') or r['ts_code'] == 'OUTSIDE.SZ']
        high_rows += [row(f'L{i:03d}.SZ', i, i / 10, 1000) for i in range(1, 31)]
        ud.build_oversold_value_directions(FakePro(high_rows), AS_OF, high)
        high_block = high['oversoldValueDirections']
        check('高估值不过滤且关系不标股票不补足', high_block['visible']
              and high_block['counts']['directionCount'] == 1 and len(high_block['industries']) == 1
              and not high_block['concepts'] and high_block['counts']['highValuationGroupCount'] == 1
              and all(x['code'] != 'OUTSIDE.SZ' for x in high_block['industries'][0]['leaders']), high_block)
    finally:
        ud.DIVIDEND_GROUP_CACHE_PATH = old_path

# 任务101/102与任务87关键门控函数逐字保护。
spec = importlib.util.spec_from_file_location('update_data_task104_remote_baseline',
                                              ROOT / 'zz_update_data_task104_remote_baseline.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
# 本轮有意替换RSI开窗三函数；估值函数、高股息、broadOsc和VCP/杯柄继续逐字保护。
protected = ('_broad_valuation_gate', '_dividend_group_catalyst', 'build_broad_osc',
             '_cup_handle_strict', '_cup_early_breakout', '_trend_template')
for name in protected:
    check(f'既有函数未改:{name}', inspect.getsource(getattr(old, name)) == inspect.getsource(getattr(ud, name)),
          'source identical')

# 前端三重门与三处展示静态契约。
weekly = (ROOT / 'src/sections/WeeklySummary.tsx').read_text(encoding='utf-8')
heatmap = (ROOT / 'src/sections/SectorHeatmap.tsx').read_text(encoding='utf-8')
funnel_ui = (ROOT / 'src/sections/funnelConclusions.ts').read_text(encoding='utf-8')
types = (ROOT / 'src/hooks/useFundData.ts').read_text(encoding='utf-8')
check('前端极端三条件防止旧名单绕门', "window === 'open'" in funnel_ui
      and "windowType === 'extreme_rebound'" in funnel_ui
      and 'extremeRebound?.active === true' in funnel_ui
      and 'extremeReboundActive(data)' in weekly and 'extremeReboundActive(data)' in heatmap)
check('第0步板块明细及类型全链路', 'oversoldValueDirectionsText(data)' in weekly
      and 'oversoldValueDirectionsText(data)' in funnel_ui
      and 'oversold-value-directions' in heatmap and 'OversoldValueDirections' in types
      and 'mineCovered' in heatmap and 'weeklyRsi6' in heatmap
      and 'rsiInsufficientGroupCount' in heatmap and '超跌程度' in heatmap)

out = {'task': 104, 'asOf': AS_OF, 'checks': checks,
       'testIsolation': 'TemporaryDirectory + FakePro；未调用真实API，未读写正式vcp_cache'}
(ROOT / 'zz_regress104.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {'checksPassed': sum(x['pass'] for x in checks.values()), 'checksTotal': len(checks),
           'failed': [k for k, v in checks.items() if not v['pass']]}
(ROOT / 'zz_regress104_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if summary['failed']:
    raise AssertionError(f"任务104检查失败: {summary['failed']}")
