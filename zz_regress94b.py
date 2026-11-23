# -*- coding: utf-8 -*-
"""任务94b：概念热榜样本充足门、空值门控、纯价格分档与5+5结构回归。"""
import copy
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('update_data94b', ROOT / 'scripts' / 'update_data.py')
u = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(u)
results = []
DAYS = [(datetime(2026, 8, 1) + timedelta(days=i)).strftime('%Y%m%d') for i in range(80)]
EFF = DAYS[-1]
CONCEPT_DAYS = DAYS[-25:]


def check(name, condition, evidence):
    results.append({'name': name, 'pass': bool(condition), 'evidence': evidence})
    if not condition:
        raise AssertionError(f'{name}: {evidence}')


def iso(d):
    return f'{d[:4]}-{d[4:6]}-{d[6:]}'


def make_history():
    names = ['银行', '保险', '纺织机械', '机场', '出版业', '行业六', '行业七']
    days = {}
    for i, day in enumerate(DAYS):
        days[day] = {'sectors': {
            name: {'net': 0.0, 'ret': 0.1 + j * 0.01, 'amt': float(i + 1 + j)}
            for j, name in enumerate(names)
        }}
    return {'days': days}


def make_cache(specs, missing=None):
    """specs=[(名称, 日收益率)]；missing 按名称给出不出现在日线中的日期。"""
    missing = missing or {}
    # 新独立缓存契约；成交额置空以继续验证原“无成交不补0”断言。
    cache = {'concept_heat_universe': [], 'concept_heat_display_map': [], 'concept_heat_daily': {}}
    for j, (name, rate) in enumerate(specs):
        code = f'C{j:02d}'
        close = 100.0
        rows = []
        for i, day in enumerate(CONCEPT_DAYS):
            if day in missing.get(name, set()):
                continue
            if i:
                close *= 1 + rate
            rows.append([day, close, 999.0, None])
        target = {'name': name, 'code': code, 'indexName': name}
        cache['concept_heat_universe'].append(target)
        cache['concept_heat_display_map'].append(target)
        cache['concept_heat_daily'][code] = rows
    return cache


def run(cache, stats=None):
    u._load_sector_history = lambda: make_history()
    u._load_json_cache = lambda *_args: copy.deepcopy(cache)
    data = {
        'sectorFlows': {'trade_date': iso(EFF)},
        'sectorRotation': {'trade_date': iso(EFF), 'stats': stats or []},
    }
    u.build_sector_crowding(data)
    return data['sectorCrowding']


def by_name(block, name):
    return next(x for x in block['items'] if x['name'] == name)


def concepts(block):
    return [x for x in block['items'] if x['type'] == '概念']


check('样本门固定为每日Top10的两倍', u.CONCEPT_HEAT_MIN_SAMPLES == 20
      and u.SECTOR_CROWDING_GROUP_TOPN == 5,
      {'minSamples': u.CONCEPT_HEAT_MIN_SAMPLES, 'groupTopN': u.SECTOR_CROWDING_GROUP_TOPN})

# ①⑤⑥：仅5个概念时，旧逻辑会全部10/15并过热；新逻辑必须全部空热榜。
small_specs = [
    ('跨境电商', -0.004),
    ('低空经济', -0.006),
    ('AI算力', -0.007),
    ('半导体设备', -0.020),
    ('高涨幅概念', 0.010),
]
small = run(make_cache(small_specs), stats=[{'sector': '银行', 'hits10': 4, 'streak': 1}])
small_concepts = concepts(small)
check('行业5行在前概念5行在后', len(small['items']) == 10
      and [x['type'] for x in small['items']] == ['行业'] * 5 + ['概念'] * 5,
      [(x['type'], x['name']) for x in small['items']])
check('仅5概念不再全员虚热且热榜字段全部留空', len(small_concepts) == 5
      and all(x['heatReady'] is False and x['hits10'] is None and x['streak'] is None
              and x['amountPct'] is None and x['level'] != '过热' for x in small_concepts),
      small_concepts)
check('样本不足说明包含最新5低于20', all(x['heatReason'] == '最新日可用概念5个，低于20个有效样本门'
      for x in small_concepts) and '最新日可用概念5个，低于20个有效样本门' in small['note'], small['note'])
check('负涨幅纯价格保守分档且20日原值可复算',
      all(by_name(small, name)['level'] == '正常' for name in ('跨境电商', '低空经济', 'AI算力', '半导体设备'))
      and by_name(small, '跨境电商')['ret20'] == round(((1 - 0.004) ** 20 - 1) * 100, 1)
      and by_name(small, '半导体设备')['ret20'] == round(((1 - 0.020) ** 20 - 1) * 100, 1),
      small_concepts)
check('无热榜且成交缺失时涨幅15仅偏高', by_name(small, '高涨幅概念')['level'] == '偏高'
      and u._crowding_level(15, None, None, None)[0] == '偏高'
      and u._crowding_level(14.9, None, None, None)[0] == '正常'
      and u._crowding_level(-20, None, None, None)[0] == '正常',
      {'hotPrice': by_name(small, '高涨幅概念'), 'negative': u._crowding_level(-20, None, None, None)})
check('概念空热榜按纯价格及涨幅排序不伪造对象', [x['name'] for x in small_concepts]
      == ['高涨幅概念', '跨境电商', '低空经济', 'AI算力', '半导体设备'], small_concepts)
bank = by_name(small, '银行')
check('行业热度与过热逻辑保持原样', bank['heatReady'] is True and bank['heatReason'] is None
      and bank['hits10'] == 4 and bank['streak'] == 1 and bank['level'] == '过热', bank)

# ②：历史22个充足样本、最新仅5个，不能把此前连续上榜继承到最新窗口。
full_names = ['AI算力'] + [f'概念{i:02d}' for i in range(1, 22)]
full_specs = [(name, 0.030 - i * 0.001) for i, name in enumerate(full_names)]
latest_five = set(full_names[:5])
drop_latest = {name: {EFF} for name in full_names if name not in latest_five}
shrunk = run(make_cache(full_specs, drop_latest))
shrunk_concepts = concepts(shrunk)
check('历史充足最新降至5仍全部空热榜', len(shrunk_concepts) == 5
      and all(x['heatReady'] is False and x['hits10'] is None and x['streak'] is None
              and x['level'] != '过热' for x in shrunk_concepts), shrunk_concepts)
check('最新样本不足不继承AI此前连续天数', by_name(shrunk, 'AI算力')['streak'] is None
      and by_name(shrunk, 'AI算力')['hits10'] is None
      and '最新日可用概念5个' in shrunk['note'], by_name(shrunk, 'AI算力'))

# ③：22个概念全历史充足，正常每日Top10、10日命中与15日连续过热仍须工作。
full = run(make_cache(full_specs))
full_ai = by_name(full, 'AI算力')
check('22概念全历史充足可正常计算热榜', full_ai['heatReady'] is True
      and full_ai['heatReason'] is None and full_ai['hits10'] == 10
      and full_ai['streak'] == 15 and full_ai['level'] == '过热', full_ai)
check('充足样本说明不误导', '最新日可用概念22个；近10日样本不足日0个' in full['note'], full['note'])

# ④：最新22个充足，但近10日中一天只有5个，完整窗口仍不可用。
partial_day = CONCEPT_DAYS[-5]
partial_missing = {name: {partial_day} for name in full_names if name not in latest_five}
partial = run(make_cache(full_specs, partial_missing))
partial_concepts = concepts(partial)
check('近10日一个样本不足日即清空完整热度', len(partial_concepts) == 5
      and all(x['heatReady'] is False and x['hits10'] is None and x['streak'] is None
              for x in partial_concepts), partial_concepts)
check('部分不足原因不误报最新日', all(x['heatReason'] == '近10日有1个样本不足日，完整热榜窗口不可用'
      for x in partial_concepts) and '最新日可用概念22个；近10日样本不足日1个' in partial['note'], partial['note'])

# ⑦：前端严格六列，空热榜只显示“样本不足”，轮动与短期资金区域未被94b触碰。
heat = (ROOT / 'src' / 'sections' / 'SectorHeatmap.tsx').read_text(encoding='utf-8')
crowding_ui = heat[heat.index('id="sector-crowding"'):heat.index('id="sector-rotation"')]
check('拥挤度前端仍严格六列', crowding_ui.count('<TableHead className=') == 6,
      crowding_ui.count('<TableHead className='))
check('空热榜显示样本不足且title带后端原因', "'样本不足'" in crowding_ui
      and 'item.heatReason' in crowding_ui and '!item.heatReady' in crowding_ui
      and 'item.hits10 == null' in crowding_ui and 'item.streak == null' in crowding_ui,
      'null-gated heat cell')
check('后续迭代后轮动和短期资金区域仍完整挂载',
      heat.count('id="sector-rotation"') == 1 and '短期资金' in heat
      and heat.index('id="sector-crowding"') < heat.index('id="sector-rotation"'),
      'current structural guards; superseded byte baseline not used')
hook = (ROOT / 'src' / 'hooks' / 'useFundData.ts').read_text(encoding='utf-8')
check('前端类型允许空热榜并要求就绪标志', 'hits10: number | null;' in hook
      and 'streak: number | null;' in hook and 'heatReady: boolean;' in hook
      and 'heatReason?: string | null;' in hook, 'FundData sectorCrowding contract')

report = {
    'passed': sum(x['pass'] for x in results),
    'total': len(results),
    'results': results,
    'smallSample': {'items': small['items'], 'note': small['note']},
}
(ROOT / 'zz_regress94b.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'passed': report['passed'], 'total': report['total'],
                  'smallConcepts': small_concepts}, ensure_ascii=False))
