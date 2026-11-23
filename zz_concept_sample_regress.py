# -*- coding: utf-8 -*-
"""行业/概念拥挤度真实样本链专项回归。"""
import copy
import importlib.util
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

vcp = load('vcp_concept_sample_test', ROOT / 'scripts' / 'vcp_preview.py')
u = load('update_concept_sample_test', ROOT / 'scripts' / 'update_data.py')
results = []

def check(name, condition, evidence):
    results.append({'name': name, 'pass': bool(condition), 'evidence': evidence})
    if not condition:
        raise AssertionError(f'{name}: {evidence}')

DAYS = [(datetime(2026, 8, 1) + timedelta(days=i)).strftime('%Y%m%d') for i in range(80)]
EFF = DAYS[-1]
CONCEPT_DAYS = DAYS[-25:]

def iso(d):
    return f'{d[:4]}-{d[4:6]}-{d[6:]}'

def history():
    names = ['银行', '保险', '纺织机械', '机场', '出版业', '行业六', '行业七']
    return {'days': {day: {'sectors': {name: {'net': 0.0, 'ret': 0.1 + j * .01,
        'amt': float(i + 1 + j)} for j, name in enumerate(names)}} for i, day in enumerate(DAYS)}}

def make_cache(specs, missing=None, amount_missing=None, future=False):
    missing, amount_missing = missing or {}, amount_missing or set()
    cache = {'concept_heat_universe': [], 'concept_heat_display_map': [], 'concept_heat_daily': {},
             'concept_heat_source': {'provider': 'test-real-schema', 'schema': ['date', 'close', 'volume', 'amount']}}
    for j, (name, rate) in enumerate(specs):
        code = f'C{j:02d}'
        close = 100.0
        rows = []
        for i, day in enumerate(CONCEPT_DAYS):
            if day in missing.get(name, set()):
                continue
            if i:
                close *= 1 + rate
            amount = None if name in amount_missing else 1000.0 + i * 10 + j
            rows.append([day, close, 2000.0 + i, amount])
        if future:
            rows.append(['20270101', close * 2, 9999.0, 999999.0])
        target = {'name': name, 'code': code, 'indexName': name}
        cache['concept_heat_universe'].append(target)
        cache['concept_heat_display_map'].append(target)
        cache['concept_heat_daily'][code] = rows
    return cache

def run(cache):
    u._load_sector_history = history
    u._load_json_cache = lambda *_args: copy.deepcopy(cache)
    data = {'sectorFlows': {'trade_date': iso(EFF)}, 'sectorRotation': {'trade_date': iso(EFF), 'stats': []}}
    u.build_sector_crowding(data)
    return data['sectorCrowding']

def by_name(block, name):
    return next(x for x in block['items'] if x['name'] == name)

def concept_items(block):
    return [x for x in block['items'] if x['type'] == '概念']

real_cache = json.loads((ROOT / 'zz_concept_sample_remote_vcp_cache.json').read_text(encoding='utf-8'))
universe, displays = vcp.concept_heat_targets(real_cache)
check('展示15与独立40样本宇宙职责分离', len(universe) == 40 and len(displays) == 15,
      {'universe': len(universe), 'displays': len(displays)})
alias = {x['name']: x for x in displays}
check('代码及同义映射可审计且无强行替代', alias['AI算力']['code'] == '885957.TI'
      and alias['人形机器人']['code'] == '875261.TI' and alias['数据中心']['code'] == '885887.TI'
      and alias['商业航天']['code'] == '865195.TI' and alias['固态电池']['code'] == '865182.TI', alias)

class FakeResponse:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return (b'cb({"data":"20261120,1,2,0.5,10.5,12345,678900.000,,,,0;'
                b'20261121,1,2,0.5,11.5,999,0,,,,0;'
                b'20261122,1,2,0.5,12.5,999,NaN,,,,0;'
                b'20261123,1,2,0.5,inf,999,1000,,,,0;bad"})')
old_urlopen = vcp.urllib.request.urlopen
vcp.urllib.request.urlopen = lambda *_args, **_kwargs: FakeResponse()
parsed = vcp._ths_public_year_rows('885957.TI', 2026)
vcp.urllib.request.urlopen = old_urlopen
check('成交量成交额分列且零NaNinf不伪造', len(parsed) == 2
      and parsed[0] == ['20261120', 10.5, 12345.0, 678900.0]
      and parsed[1] == ['20261121', 11.5, 999.0, None], parsed)
merged = vcp.merge_concept_heat_rows(parsed, [['20261120', 10.6, None, None]])
check('增量缺字段保留原真实成交量成交额', merged[0] == ['20261120', 10.6, 12345.0, 678900.0], merged)

names = ['AI算力'] + [f'概念{i:02d}' for i in range(1, 22)]
specs = [(name, .030 - i * .001) for i, name in enumerate(names)]
full = run(make_cache(specs))
ai = by_name(full, 'AI算力')
check('22真实样本连续10日可算热榜及真实成交分位', full['conceptCoverage']['heatReady'] is True
      and all(full['conceptCoverage']['dailySamples'][d] == 22 for d in full['conceptCoverage']['last10'])
      and ai['hits10'] == 10 and ai['streak'] == 15 and ai['amountPct'] is not None
      and ai['amountSource'] == '同花顺公开指数日线.amount（元）', ai)

latest_five = set(names[:5])
shrunk = run(make_cache(specs, {name: {EFF} for name in names if name not in latest_five}))
check('最新日仅5样本则热榜留空且样本门不降低', shrunk['conceptCoverage']['dailySamples'][EFF] == 5
      and not shrunk['conceptCoverage']['heatReady']
      and all(x['hits10'] is None and x['streak'] is None for x in concept_items(shrunk)), shrunk['conceptCoverage'])
partial_day = CONCEPT_DAYS[-5]
partial = run(make_cache(specs, {name: {partial_day} for name in names if name not in latest_five}))
check('近10日任一日不足20则整个热榜留空', not partial['conceptCoverage']['heatReady']
      and partial['conceptCoverage']['dailySamples'][partial_day] == 5
      and all(x['heatReason'] == '近10日有1个样本不足日，完整热榜窗口不可用' for x in concept_items(partial)),
      partial['conceptCoverage']['heatReason'])

missing_cache = make_cache(specs, amount_missing={'AI算力'})
missing_cache['concept_heat_display_map'] = missing_cache['concept_heat_display_map'][:5]
missing_amount = run(missing_cache)
check('真实成交额缺失显示空而非0或成交量分位', by_name(missing_amount, 'AI算力')['amountPct'] is None
      and by_name(missing_amount, 'AI算力')['heatReady'] is True, by_name(missing_amount, 'AI算力'))
stale = run(make_cache(specs, {'AI算力': {EFF}}))
check('展示概念最新日陈旧剔除但不补0', all(x['name'] != 'AI算力' for x in concept_items(stale))
      and 'AI算力' in stale['note'], stale['note'])
future = run(make_cache(specs, future=True))
check('未来行情不参与收益成交和热榜', future['conceptCoverage']['asOf'] == iso(EFF)
      and max(future['conceptCoverage']['dailySamples']) == EFF
      and by_name(future, 'AI算力')['ret20'] == ai['ret20']
      and by_name(future, 'AI算力')['amountPct'] == ai['amountPct'], future['conceptCoverage']['dailySamples'])
short_cache = make_cache(specs)
short_cache['concept_heat_daily']['C21'] = short_cache['concept_heat_daily']['C21'][-10:]
short = run(short_cache)
check('历史不足单独披露且不进入有效收益样本', short['conceptCoverage']['shortHistory'] == [
      {'name': '概念21', 'code': 'C21', 'days': 10}]
      and short['conceptCoverage']['dailySamples'][EFF] == 21, short['conceptCoverage']['shortHistory'])
legacy = {'concepts': [{'name': 'AI算力', 'code': 'OLD'}], 'index_daily': {'OLD': [[EFF, 100, 999999]]},
          'concept_heat_universe': [{'name': 'AI算力', 'code': 'OLD', 'indexName': 'AI算力'}],
          'concept_heat_display_map': [{'name': 'AI算力', 'code': 'OLD', 'indexName': 'AI算力'}]}
legacy_result = run(legacy)
check('旧amountvol混写列绝不再作为真实样本', legacy_result['conceptCoverage']['dailySamples'] == {}
      and legacy_result['conceptCoverage']['heatReady'] is False and not concept_items(legacy_result),
      legacy_result['conceptCoverage'])

heat = (ROOT / 'src' / 'sections' / 'SectorHeatmap.tsx').read_text(encoding='utf-8')
hook = (ROOT / 'src' / 'hooks' / 'useFundData.ts').read_text(encoding='utf-8')
check('UI真实覆盖时显示数值真实不足仍显示样本不足', "`${item.hits10}次 · 连${item.streak}天`" in heat
      and "'样本不足'" in heat and 'item.amountSource' in heat and 'conceptCoverage?:' in hook,
      'amount/heat nullable UI contract')
report = {'passed': sum(x['pass'] for x in results), 'total': len(results), 'results': results}
(ROOT / 'zz_concept_sample_regress.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'passed': report['passed'], 'total': report['total']}, ensure_ascii=False))
