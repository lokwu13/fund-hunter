# -*- coding: utf-8 -*-
"""任务94：行业/概念拥挤度、轮动榜迁移、陈旧缺失门控回归。"""
import copy
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('update_data94', ROOT / 'scripts' / 'update_data.py')
u = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(u)
results = []
DAYS = [(datetime(2025, 10, 16) + timedelta(days=i)).strftime('%Y%m%d') for i in range(250)]
EFF = DAYS[-1]


def check(name, condition, evidence):
    results.append({'name': name, 'pass': bool(condition), 'evidence': evidence})
    if not condition:
        raise AssertionError(f'{name}: {evidence}')


def iso(d):
    return f'{d[:4]}-{d[4:6]}-{d[6:]}'


def make_history(specs):
    days = {}
    for i, day in enumerate(DAYS):
        sectors = {}
        for name, cfg in specs.items():
            ret = cfg.get('ret', 0.0)
            amt = cfg.get('amt', 1.0)
            sectors[name] = {
                'net': 0.0,
                'ret': ret[i] if isinstance(ret, list) else ret,
                'amt': amt[i] if isinstance(amt, list) else amt,
            }
        days[day] = {'sectors': sectors}
    return {'days': days}


def run_crowding(hist, cache=None, stats=None, effective=EFF):
    u._load_sector_history = lambda: hist
    u._load_json_cache = lambda *_args: copy.deepcopy(cache or {})
    data = {
        'sectorFlows': {'trade_date': iso(effective)},
        'sectorRotation': {'trade_date': iso(effective), 'stats': stats or []},
    }
    u.build_sector_crowding(data)
    return data['sectorCrowding']


def by_name(block, name):
    return next(x for x in block['items'] if x['name'] == name)


# 分档边界全部固定，轮动过热必须高于低温规则。
level_cases = [
    ('轮动4次一票过热', (0, 10, 4, 0), '过热'),
    ('连续3天一票过热', (0, 10, 0, 3), '过热'),
    ('双高阈值含边界', (15, 80, 0, 0), '过热'),
    ('热榜3次为偏高', (0, 50, 3, 0), '偏高'),
    ('偏热双阈值含边界', (8, 60, 0, 0), '偏高'),
    ('低温三条件含边界', (0, 20, 0, 0), '低'),
    ('普通对象为正常', (7.9, 59.9, 0, 0), '正常'),
]
for name, args, expected in level_cases:
    actual = u._crowding_level(*args)[0]
    check(name, actual == expected, {'args': args, 'actual': actual, 'expected': expected})
check('成交缺失不补0也不伪造低温或双高',
      u._crowding_level(-20, None, 0, 0)[0] == '正常'
      and u._crowding_level(30, None, 0, 0)[0] == '正常', 'amountPct=None')

# 行业20日复利、250日成交分位及低温集成。
amounts_low = [2.0] * 200 + [1.0] * 50
hist = make_history({
    '银行': {'ret': 1.0, 'amt': list(range(1, 251))},
    '低温行业': {'ret': 0.0, 'amt': amounts_low},
})
block = run_crowding(hist, stats=[{'sector': '银行', 'hits10': 4, 'streak': 1}])
bank = by_name(block, '银行')
expected_ret20 = round(((1.01 ** 20) - 1) * 100, 1)
check('行业20日涨幅按20个真实日收益复利', bank['ret20'] == expected_ret20,
      {'actual': bank['ret20'], 'expected': expected_ret20})
check('行业最新成交额取250日分位', bank['amountPct'] == 100.0, bank)
check('既有轮动过热与拥挤度一致', bank['level'] == '过热' and bank['reason'] == '轮动过热', bank)
low = by_name(block, '低温行业')
check('低温行业分位可复算且判低', low['amountPct'] == 20.0 and low['level'] == '低', low)

# 24个当前概念逐日前10 + 1个陈旧概念 + 1个过热行业：样本充足时仍计算热榜。
concept_cache = {'concept_heat_universe': [], 'concept_heat_display_map': [], 'concept_heat_daily': {}}
concept_days = DAYS[-25:]
for j in range(24):
    name = 'AI算力' if j == 23 else f'概念{j:02d}'
    code = f'C{j:02d}'
    rate = j / 1000.0
    rows = []
    close = 100.0
    for i, day in enumerate(concept_days):
        if i:
            close *= 1 + rate
        rows.append([day, close, 999.0, None])  # 成交量不得冒充第四列真实成交额。
    target = {'name': name, 'code': code, 'indexName': name}
    concept_cache['concept_heat_universe'].append(target)
    concept_cache['concept_heat_display_map'].append(target)
    concept_cache['concept_heat_daily'][code] = rows
concept_cache['concept_heat_display_map'].append({'name': '陈旧概念', 'code': 'OLD', 'indexName': '陈旧概念'})
concept_cache['concept_heat_daily']['OLD'] = [[d, 100.0, 0.0, None] for d in concept_days[:-1]]
combined = run_crowding(hist, concept_cache,
                        stats=[{'sector': '银行', 'hits10': 4, 'streak': 1}])
check('行业概念各取前5且候选不足不伪造', len(combined['items']) == 7
      and sum(x['type'] == '行业' for x in combined['items']) == 2
      and sum(x['type'] == '概念' for x in combined['items']) == 5, combined['items'])
small_targets = concept_cache['concept_heat_universe'][:2]
small_cache = {
    'concept_heat_universe': small_targets,
    'concept_heat_display_map': small_targets,
    'concept_heat_daily': {x['code']: concept_cache['concept_heat_daily'][x['code']] for x in small_targets},
}
small = run_crowding(hist, small_cache, stats=[{'sector': '银行', 'hits10': 4, 'streak': 1}])
check('行业与真实概念进入同一候选表', {x['type'] for x in small['items']} == {'行业', '概念'}, small['items'])
ai = by_name(combined, 'AI算力')
ai_rows = concept_cache['concept_heat_daily']['C23']
expected_ai_ret20 = round((ai_rows[-1][1] / ai_rows[-21][1] - 1) * 100, 1)
check('概念20日涨幅按首尾21个收盘点复利', ai['ret20'] == expected_ai_ret20,
      {'actual': ai['ret20'], 'expected': expected_ai_ret20})
check('样本充足时概念同池每日前10并计算热度与连续天数',
      ai['heatReady'] is True and ai['heatReason'] is None
      and ai['hits10'] == 10 and ai['streak'] == 15 and ai['level'] == '过热', ai)
check('概念第三列不冒充成交额且缺失不补0',
      all(x['amountPct'] is None for x in combined['items'] if x['type'] == '概念'), combined['items'])
check('热榜后两名不伪造上榜次数', by_name(combined, '概念00')['hits10'] == 0
      if any(x['name'] == '概念00' for x in combined['items']) else True, combined['items'])
check('陈旧概念剔除并写入说明', all(x['name'] != '陈旧概念' for x in combined['items'])
      and '概念1个' in combined['note'] and '陈旧概念' in combined['note'], combined['note'])

# 行业有效日落后本批，整批清空而不是沿用旧榜。
stale = run_crowding(hist, effective=(datetime.strptime(EFF, '%Y%m%d') + timedelta(days=1)).strftime('%Y%m%d'))
check('行业陈旧时 stale 且不入榜', stale['stale'] is True and stale['items'] == []
      and '剔除陈旧行业2个' in stale['note'], stale)

# 真实任务93线上数据 + 任务92真实250日缓存交叉验证；本机概念缓存旧，必须剔除。
real_history = json.loads((ROOT / 'zz_sector_history_online92.json').read_text(encoding='utf-8'))
real_cache = json.loads((ROOT / 'scripts' / 'cache' / 'vcp_cache.json').read_text(encoding='utf-8'))
real_data = json.loads((ROOT / 'zz_fd_online93.json').read_text(encoding='utf-8'))
u._load_sector_history = lambda: real_history
u._load_json_cache = lambda *_args: real_cache
u.build_sector_crowding(real_data)
real = real_data['sectorCrowding']
real_bank = by_name(real, '银行')
real_rows = u._history_series(real_history, '银行')
level_value = 1.0
for row in real_rows[-20:]:
    level_value *= 1 + row[2] / 100.0
expected_bank = (round((level_value - 1) * 100, 1),
                 u._pct_rank100([r[3] for r in real_rows[-250:]], real_rows[-1][3]))
check('真实有效日与行业5加概念0正确', real['trade_date'] == '2026-10-27'
      and real['stale'] is False and len(real['items']) == 5
      and [x['type'] for x in real['items']] == ['行业'] * 5, real)
check('真实银行20日涨幅与250日成交分位可复算',
      (real_bank['ret20'], real_bank['amountPct']) == expected_bank,
      {'actual': (real_bank['ret20'], real_bank['amountPct']), 'expected': expected_bank})
check('真实银行保险轮动过热一致且机场为偏高',
      real_bank['hits10'] == 4 and real_bank['level'] == '过热'
      and by_name(real, '保险')['level'] == '过热'
      and by_name(real, '机场')['level'] == '偏高', real['items'][:4])
check('真实陈旧概念全部剔除不冒充当前', all(x['type'] == '行业' for x in real['items'])
      and '剔除陈旧行业0个、概念15个' in real['note'], real['note'])

# 前端：总览/工具无轮动榜，板块页仅一处；拥挤度严格六列且在正上方。
app = (ROOT / 'src' / 'App.tsx').read_text(encoding='utf-8')
heat = (ROOT / 'src' / 'sections' / 'SectorHeatmap.tsx').read_text(encoding='utf-8')
eci = (ROOT / 'src' / 'sections' / 'ECIPanel.tsx').read_text(encoding='utf-8')
old_heat = (ROOT / 'zz_SectorHeatmap_before94.tsx').read_text(encoding='utf-8')
old_eci = (ROOT / 'zz_ECIPanel_before94.tsx').read_text(encoding='utf-8')
check('总览与工具不挂载轮动榜且板块页仅一处',
      app.count('<SectorHeatmap') == 2 and '<SectorHeatmap />' in app and '<SectorHeatmap detailed />' in app
      and 'sector-rotation' not in eci and 'rotTab' not in eci
      and heat.count('id="sector-rotation"') == 1 and '{detailed && data.sectorRotation' in heat, 'mounts')
check('拥挤度简表位于轮动榜正上方', heat.count('id="sector-crowding"') == 1
      and heat.index('id="sector-crowding"') < heat.index('id="sector-rotation"')
      and '{detailed && data.sectorCrowding' in heat, 'ordering')
crowding_ui = heat[heat.index('id="sector-crowding"'):heat.index('id="sector-rotation"')]
headers = ['名称', '类型', '20日涨幅', '成交热度', '10日热榜', '拥挤度']
positions = [crowding_ui.find(f'>{h}<') for h in headers]
check('拥挤度严格六列且顺序正确', all(p >= 0 for p in positions) and positions == sorted(positions), positions)
check('缺失成交热度显示横线且不补0', "item.amountPct == null ? '—'" in crowding_ui
      and 'item.amountPct || 0' not in crowding_ui and '不补0' in crowding_ui, 'missing UI')
check('热榜无效时前端显示样本不足并给出原因', "'样本不足'" in crowding_ui
      and 'item.heatReason' in crowding_ui and 'item.hits10 == null' in crowding_ui
      and 'item.streak == null' in crowding_ui, 'heat null UI')

# 原轮动 UI 除 detailed 守卫外逐字保留；短期资金统一表逐字不动。
def rotation_block(text, detailed=False):
    marker = '{detailed && data.sectorRotation' if detailed else '{data.sectorRotation'
    start = text.index(marker)
    end = text.index('      })()}', start) + len('      })()}')
    block = text[start:end]
    return block.replace('{detailed && data.sectorRotation', '{data.sectorRotation', 1)


def short_flow_block(text):
    start = text.index('{/* 总览与板块页共用')
    end = text.index('      </Card>', start) + len('      </Card>')
    return text[start:end]


check('轮动双口径tab网格summary徽章原样迁移', rotation_block(old_eci) == rotation_block(heat, True), 'rotation byte block')
check('任务93短期资金统一表代码未改', short_flow_block(old_heat) == short_flow_block(heat), 'short flow byte block')
hook = (ROOT / 'src' / 'hooks' / 'useFundData.ts').read_text(encoding='utf-8')
check('拥挤度类型包含可空热榜与风险分档', 'sectorCrowding?:' in hook
      and 'ret20: number | null;' in hook and 'amountPct: number | null;' in hook
      and 'hits10: number | null;' in hook and 'streak: number | null;' in hook
      and 'heatReady: boolean;' in hook and 'heatReason?: string | null;' in hook
      and "'过热' | '偏高' | '正常' | '低'" in hook, 'FundData interface')

report = {
    'passed': sum(x['pass'] for x in results), 'total': len(results), 'results': results,
    'realSample': {
        'tradeDate': real['trade_date'],
        'items': real['items'],
        'note': real['note'],
    },
}
(ROOT / 'zz_regress94.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'passed': report['passed'], 'total': report['total'],
                  'realSample': report['realSample']['items'][:4]}, ensure_ascii=False))
