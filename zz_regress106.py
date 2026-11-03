# -*- coding: utf-8 -*-
"""任务106回归（任务108现行契约）：动态RSI6开窗与任务103函数保护。"""
import importlib.util
import inspect
import json
from pathlib import Path

import pandas as pd
import update_data as ud

ROOT = Path(__file__).resolve().parent
AS_OF = '20261030'
EXPECTED_CODES = ['000016.SH', '000300.SH', '000510.SH', '000905.SH', '000688.SH', '399673.SZ']
checks = {}


def check(name, condition, evidence=None):
    checks[name] = {'pass': bool(condition), 'evidence': evidence}


def rows(final_gain, current_gain=0.0):
    dates = pd.date_range(end='2026-10-23', periods=30, freq='W-FRI').strftime('%Y%m%d').tolist()
    closes = [100.0]
    for _ in range(28):
        closes.append(closes[-1] * 0.96)
    closes.append(closes[-1] * (1 + final_gain))
    result = [[d, c, c, c, 1000.0] for d, c in zip(dates, closes)]
    closes.append(closes[-1] * (1 + current_gain))
    return result + [[AS_OF, closes[-1], closes[-1], closes[-1], 1000.0]]


zone_rows, cross_rows = rows(-0.05), rows(0.30)
zone = ud._weekly_rsi6_evidence(zone_rows, AS_OF)
cross = ud._weekly_rsi6_evidence(cross_rows, AS_OF)
check('当周动态值不超20直接通过', zone['rsiPass'] and zone['dynamicWeeklyFresh']
      and zone['dynamicWeeklyRsiDate'] == AS_OF and zone['inOversoldZone'], zone)
check('完成周上穿不再替代动态区域条件', cross['weeklyCross20'] and not cross['rsiPass']
      and cross['dynamicWeeklyRsi6'] > 20, cross)
check('六宽基含A500且沪深300唯一', [c for c, _ in ud.OBSERVATION_INDICES] == EXPECTED_CODES
      and '399300' not in str(ud.OBSERVATION_INDICES), ud.OBSERVATION_INDICES)


def observation(active=None):
    weekly = ud._broad_weekly_rsi(AS_OF, {c: zone_rows if c == active else cross_rows for c in EXPECTED_CODES})
    return ud._broad_observation_decision(weekly, [], AS_OF)


for code in EXPECTED_CODES:
    obs = observation(code)
    ext = ud._extreme_rebound_decision(obs, AS_OF)
    check(f'任一指数单独开窗:{code}', obs['qualifiedCount'] == 1 and ext['active']
          and ext['triggerDetails'][0]['dynamicWeeklyRsi6'] <= 20, ext)

opened = observation('000300.SH')
data = {'bondData': {'marginTrading': {'temp': '🔴冷'}, 'stats': {'1m_change': {'y10': 30}}},
        'broadVcp': {'items': []}, 'sectorFlows': {'trade_date': '2026-10-30'},
        'broadObservation': opened,
        'broadOsc': {'trade_date': '2026-10-30', 'sellAlerts': ['上证50'],
                     'buyWindows': [], 'reboundWatch': [], 'items': []}}
ud.build_long_window(data)
check('旧风险债券估值门不否决且保留普通窗', data['longWindow']['window'] == 'open'
      and data['longWindow']['standardWindow'] == 'closed'
      and data['longWindow']['windowType'] == 'extreme_rebound', data['longWindow'])
closed = dict(data, broadObservation=observation(), longWindow=data['longWindow'])
ud.build_long_window(closed)
check('离开区域旧active不延续', closed['longWindow']['windowType'] == 'standard'
      and closed['longWindow']['window'] == 'closed'
      and closed['longWindow']['extremeRebound']['maxDays'] is None, closed['longWindow'])

spec = importlib.util.spec_from_file_location('update_data_task106_baseline_current',
                                              ROOT / 'zz_update_data_task106_rsi6_baseline.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
# 任务110允许杯柄追加统一资格过滤，旧基线逐字门不再适用于这两个函数；
# 核心几何仍由任务105约束，资格边界由任务110约束。
for name in ('_vcp_level_strict', '_vcp_fixed_base', '_vcp_right_side_quality'):
    check(f'任务103函数逐字未改:{name}', inspect.getsource(getattr(old, name)) == inspect.getsource(getattr(ud, name)))

production = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
ui = ''.join((ROOT / p).read_text(encoding='utf-8') for p in (
    'src/sections/WeeklySummary.tsx', 'src/sections/funnelConclusions.ts',
    'src/sections/SectorHeatmap.tsx', 'src/sections/ECIPanel.tsx'))
check('动态开窗全链路新文案', '当周动态RSI6进入20以下区域' in production + ui
      and 'dynamicWeeklyRsiDate' in ui and '周内会变化' in ui)
check('旧实时口径已清理', not any(x in ui for x in ('完成周RSI6收复20', '周RSI6收复20',
                                                   '周RSI6升序', '最长5日')))
check('独立RSI14高股息模块未误删', '_dividend_group_catalyst' in production
      and '近4个完成周曾周RSI14<20' in production)

out = {'task': 106, 'updatedForTask': 108, 'asOf': AS_OF, 'checks': checks}
(ROOT / 'zz_regress106.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {'checksPassed': sum(x['pass'] for x in checks.values()), 'checksTotal': len(checks),
           'failed': [k for k, v in checks.items() if not v['pass']]}
(ROOT / 'zz_regress106_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if summary['failed']:
    raise AssertionError(summary['failed'])
