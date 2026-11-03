# -*- coding: utf-8 -*-
"""任务110：杯柄历史高位统一资格门；PIT、边界、普通/早期/fuzzy与前端证据契约。"""
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import update_data as ud

checks = []
def check(name, condition, evidence=None):
    checks.append({'name': name, 'passed': bool(condition), 'evidence': evidence})

def bars(closes):
    return [(f'2026{i // 10000 % 100:02d}{i // 100 % 100:02d}', c, c, c, 100.0)
            for i, c in enumerate(closes, 1)]

def gate_for_previous(high, close):
    return ud._cup_history_position_gate(bars([80.0] * 20 + [high, close]))

for label, close, expected in [('7.99%排除', 92.01, False), ('恰好8%通过', 92.0, True),
                               ('超过8%通过', 91.99, True)]:
    gate = gate_for_previous(100, close)
    check(label, gate['historyGatePass'] is expected
          and (expected or gate['historyExclusionReason'] == '距历史高点不足8%'), gate)

breakout = gate_for_previous(100, 101)
check('突破创可得历史新高排除', not breakout['historyGatePass']
      and breakout['historyExclusionReason'] == '距历史高点不足8%', breakout)

long_bars = bars([200.0] + [80.0] * 280 + [110.0] * 18 + [92.0])
long_gate = ud._cup_history_position_gate(long_bars)
check('一年高但远低于历史高不误杀', long_gate['historyGatePass']
      and long_gate['historicalHighClose'] == 200 and long_gate['historyStart'] == long_bars[0][0], long_gate)
check('历史高为前一交易日最高收盘而非最高价', long_gate['historicalHighClose'] == 200
      and long_gate['historyEnd'] == long_bars[-2][0])

past = bars([100.0] * 30 + [92.0])
future = past + bars([180.0, 200.0])
past_gate = ud._cup_history_position_gate(past)
future_gate = ud._cup_history_position_gate(future)
check('只用当时历史且未来更高点不影响过去', past_gate['historyGatePass']
      and past_gate['historicalHighClose'] == 100 and future_gate['historicalHighClose'] == 180
      and not future_gate['historyGatePass'])

for mode in ('ordinary', 'fuzzy'):
    candidate = {'formed': True, 'structureFuzzy': mode == 'fuzzy', 'defects': ['近似'] if mode == 'fuzzy' else []}
    excluded = ud._apply_cup_history_eligibility(dict(candidate), bars([100.0] * 30 + [92.01]))
    check(f'{mode}:formed保留但eligible/display均false', excluded['formed']
          and not excluded['eligible'] and not excluded['displayEligible']
          and excluded['historyExclusionReason'] == '距历史高点不足8%')
    check(f'{mode}:排除原因不降级为fuzzy瑕疵', '距历史高点不足8%' not in excluded['defects'])

# 受控早期链：几何strict结果固定，仅验证当前识别日统一资格门，不修改杯柄几何。
fake_cup = {'formed': True, 'displayEligible': True, 'distPct': 0.0, 'pivot': 90.0,
            'days': 10, 'brkNeedVol': 450.0, 'rimDate': '20260101'}
def early_bars(closes):
    result = [(d, h, l, c, 300.0) for d, h, l, c, _ in bars(closes)]
    result[-1] = (*result[-1][:4], 450.0)
    return result
early_base = early_bars([100.0] * 165 + [90.0] * 10 + [91.0])
with patch.object(ud, '_cup_handle_strict', return_value=dict(fake_cup)):
    early_pass = ud._cup_early_breakout(early_base)
    early_excluded = ud._cup_early_breakout(early_bars([100.0] * 165 + [90.0] * 10 + [101.0]))
check('早期突破当前距历史高点>=8%可通过', early_pass and early_pass['displayEligible'], early_pass)
check('早期突破创新高直接排除', early_excluded is None)

vcp_source = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
check('VCP/底部平台不走历史高位资格过滤', vcp_source.count('_apply_cup_history_eligibility(') == 4
      and "raw, main_lv = 'VCP收缩型'" in vcp_source)
check('普通生产入口核验displayEligible', "ch['formed'] and ch.get('displayEligible')" in vcp_source
      and "recent and recent.get('displayEligible')" in vcp_source)
check('指数杯柄与漏斗核验displayEligible', "cup['formed'] and cup.get('displayEligible')" in vcp_source
      and "r['cup'].get('displayEligible')" in vcp_source)

weekly = (ROOT / 'src/sections/WeeklySummary.tsx').read_text(encoding='utf-8')
eci = (ROOT / 'src/sections/ECIPanel.tsx').read_text(encoding='utf-8')
for field in ('historicalHighClose', 'historicalHighDate', 'distanceToHistoricalHighPct',
              'historyScope', 'historyExclusionReason'):
    check(f'前后端证据字段:{field}', field in vcp_source and field in weekly and field in eci)
check('总览tooltip披露历史范围与原因', '历史最高收盘' in weekly and '排除原因=' in weekly)
check('精扫tooltip披露历史范围与原因', '历史最高收盘' in eci and '排除原因=' in eci)

# 真实杯柄样本只校验新证据与PIT，不重写原几何标签。
import zz_regress96 as samples
case_map, cache, real95, rows600795 = samples.load_inputs()
library = json.loads(samples.SAMPLE_PATH.read_text(encoding='utf-8'))
real_evidence = []
for sample in library['samples']:
    if not sample['id'].startswith('C'):
        continue
    if sample.get('sourceCase'):
        rows = case_map[sample['sourceCase']][0]
    elif sample.get('source') == 'current_cache':
        rows = cache.get(sample['code'])
    elif sample.get('source') == 'real95':
        rows = real95.get(sample['code'])
    else:
        rows = rows600795
    rows = [r for r in rows if r[0] <= sample['asOf']]
    bs = samples.bars_of(rows)
    cup = ud._cup_handle_strict(bs, True, allow_weekly_defect=True)
    if cup and cup.get('formed'):
        gate = ud._cup_history_position_gate(bs)
        real_evidence.append({'id': sample['id'], 'asOf': sample['asOf'], 'historyEnd': gate.get('historyEnd'),
                              'eligible': cup['eligible'], 'reason': cup['historyExclusionReason']})
        check(f"真实杯柄样本PIT:{sample['id']}", gate.get('historyEnd') < sample['asOf']
              and cup['displayEligible'] == gate['historyGatePass'])
check('真实杯柄样本至少覆盖一例', len(real_evidence) > 0, real_evidence)

before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
          for p in ('public/fund_data.json', 'src/data/fund_data.json')}
result = {'task': 110, 'checksPassed': sum(c['passed'] for c in checks), 'checksTotal': len(checks),
          'failed': [c['name'] for c in checks if not c['passed']], 'checks': checks,
          'realCupEvidence': real_evidence, 'dataSha256': before}
(ROOT / 'zz_regress110_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'checksPassed': result['checksPassed'], 'checksTotal': result['checksTotal'],
                  'failed': result['failed'], 'realCupEvidence': real_evidence}, ensure_ascii=False, indent=2))
raise SystemExit(1 if result['failed'] else 0)
