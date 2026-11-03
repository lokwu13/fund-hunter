# -*- coding: utf-8 -*-
"""任务102回归（任务108现行契约）：六宽基动态证据、估值参考与失败锁门。"""
import importlib.util
import inspect
import json
import tempfile
from pathlib import Path

import pandas as pd
import update_data as ud

ROOT = Path(__file__).resolve().parent
AS_OF = '20261030'
CODES = [x[0] for x in ud.OBSERVATION_INDICES]
NAMES = dict(ud.OBSERVATION_INDICES)
ud.API_DELAY = 0
checks = {}


def check(name, condition, evidence=None):
    checks[name] = {'pass': bool(condition), 'evidence': evidence}


def weekly(code, value=50.0, fresh=True):
    passed = bool(fresh and value <= 20)
    return {'indexCode': code, 'indexName': NAMES[code], 'weeklyRsi': 50.0, 'weeklyRsi6': 50.0,
            'previousWeeklyRsi6': 18.0, 'previousWeeklyRsiDate': '20261016',
            'weeklyRsiDate': '20261023', 'dailyDate': AS_OF if fresh else '20261029',
            'weeklyFresh': True, 'dynamicWeeklyRsi6': value, 'dynamicWeeklyRsiDate': AS_OF if fresh else None,
            'dynamicWeeklyFresh': fresh, 'inOversoldZone': passed, 'rsiPass': passed,
            'rsiReason': '受控动态RSI6边界'}


def valuation(code, pe=50.0, pb=50.0):
    return {'indexCode': code, 'indexName': NAMES[code], 'peTtm': 10.0, 'pb': 1.0,
            'pePct10y': pe, 'pbPct10y': pb, 'valuationDate': AS_OF,
            'observations': 600, 'fresh': True, 'sufficientHistory': True,
            'valuationLow': pe <= 20 and pb <= 20, 'reason': '受控估值参考'}


def decide(values=None, fresh=True, valuations=None):
    values = values or {}
    ws = [weekly(c, values.get(c, 50.0), fresh) for c in CODES]
    vs = [valuation(c, *(valuations or {}).get(c, (50.0, 50.0))) for c in CODES]
    return ud._broad_observation_decision(ws, vs, AS_OF)


check('任一动态RSI6不超20可开', decide({CODES[0]: 18})['active'])
check('动态RSI6等于20边界可开', decide({CODES[0]: 20})['active'])
check('动态RSI6大于20不开', not decide({CODES[0]: 20.01})['active'])
check('动态行情不新鲜不开', not decide({CODES[0]: 18}, fresh=False)['active'])
check('PE/PB高估值不否决动态门', decide({CODES[0]: 18}, valuations={CODES[0]: (99, 99)})['active'])
check('低估值本身不开门', not decide(valuations={c: (1, 1) for c in CODES})['active'])
for code in CODES:
    obs = decide({code: 20})
    check(f'同名指数独立配对:{code}', obs['qualifiedIndices'] == [NAMES[code]]
          and obs['qualifiedCount'] == 1, obs['qualifiedIndices'])


class EmptyPro:
    def index_dailybasic(self, **kwargs):
        return pd.DataFrame()


def valuation_gate_with_rows(rows):
    old_path = ud.BROAD_VALUATION_PATH
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'valuation.json'
            path.write_text(json.dumps({'rows': {c: rows for c in CODES}}), encoding='utf-8')
            ud.BROAD_VALUATION_PATH = str(path)
            return ud._broad_valuation_gate(EmptyPro(), AS_OF)
    finally:
        ud.BROAD_VALUATION_PATH = old_path


fresh_rows = [[d.strftime('%Y%m%d'), 10.0, 1.0] for d in pd.date_range(end='2026-10-30', periods=600)]
stale_rows = [[d.strftime('%Y%m%d'), 10.0, 1.0] for d in pd.date_range(end='2026-10-01', periods=600)]
check('宽基估值陈旧只锁估值参考状态', all(not x['fresh'] and not x['valuationLow']
      for x in valuation_gate_with_rows(stale_rows)))
check('宽基估值历史不足500日只锁估值参考状态', all(not x['sufficientHistory'] and not x['valuationLow']
      for x in valuation_gate_with_rows(fresh_rows[-499:])))

# 单日崩跌必须进入包含未完结周的动态周RSI，不再被最近完成周100掩盖。
days = pd.bdate_range('2025-01-03', '2026-10-30').strftime('%Y%m%d').tolist()
closes = [100.0] * len(days)
closes[-1] = 1.0
controlled = [[d, closes[i], closes[i], closes[i], 1000.0] for i, d in enumerate(days)]
evidence = ud._broad_weekly_rsi(AS_OF, {CODES[0]: controlled})[0]
check('动态周纳入最新未完结周单日崩跌', evidence['weeklyRsi6'] == 100
      and evidence['dynamicWeeklyRsi6'] < 20 and evidence['rsiPass']
      and evidence['dynamicWeeklyRsiDate'] == AS_OF, evidence)

# 本地真实缓存与既有审计输入逐指数复算，不访问网络；使用最后密集交易日避开末尾孤立点。
local = json.loads((ROOT / 'scripts/cache/broad_idx_cache.json').read_text(encoding='utf-8'))
audit = json.loads((ROOT / 'zz_audit102_real_inputs.json').read_text(encoding='utf-8'))
real = {}
for code in CODES:
    rows = local.get(code) or (audit['indices'].get(code) or {}).get('daily') or []
    date = rows[-2][0]
    item = ud._weekly_rsi6_evidence(rows, date)
    real[code] = item
    check(f'真实缓存动态证据可复算:{code}', item['dynamicWeeklyFresh']
          and item['dynamicWeeklyRsi6'] is not None
          and item['rsiPass'] == (item['dynamicWeeklyRsi6'] <= 20)
          and item['dailyDate'] == date, item)


def long_data(obs):
    return {'bondData': {'marginTrading': {'temp': '🔴冷'}, 'stats': {'1m_change': {'y10': 25}}},
            'broadVcp': {'items': []}, 'sectorFlows': {'trade_date': '2026-10-30'},
            'broadObservation': obs,
            'broadOsc': {'trade_date': '2026-10-30', 'items': [], 'sellAlerts': [],
                         'buyWindows': [], 'reboundWatch': [], 'extremeEvidence': []}}


opened = long_data(decide({CODES[0]: 20}))
ud.build_long_window(opened)
check('冷普通窗被动态RSI6独立覆盖且保留standard', opened['longWindow']['window'] == 'open'
      and opened['longWindow']['standardWindow'] == 'closed'
      and opened['longWindow']['windowType'] == 'extreme_rebound', opened['longWindow'])
closed = long_data(decide())
closed['longWindow'] = opened['longWindow']
ud.build_long_window(closed)
check('全部大于20直接回普通窗且无续命', closed['longWindow']['window'] == 'closed'
      and closed['longWindow']['windowType'] == 'standard'
      and closed['longWindow']['extremeRebound']['remainingDays'] == 0, closed['longWindow'])

spec = importlib.util.spec_from_file_location('update_data_task102_baseline_current',
                                              ROOT / 'zz_update_data_task102_remote_baseline.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
# 任务110已授权更新杯柄统一资格门，不能再用更早基线禁止该后续变更；
# 杯柄核心几何由任务105、资格边界由任务110独立回归。
for name in ('_dividend_group_catalyst', '_osc_weekly_ma', '_weekly_ma150_200_display_gate',
             '_platform_contraction_practical_ok', '_trend_template', 'build_broad_osc'):
    check(f'既有函数逐字未改:{name}', inspect.getsource(getattr(old, name)) == inspect.getsource(getattr(ud, name)))

production = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
ui = ''.join((ROOT / p).read_text(encoding='utf-8') for p in (
    'src/sections/WeeklySummary.tsx', 'src/sections/funnelConclusions.ts',
    'src/sections/ECIPanel.tsx', 'src/hooks/useFundData.ts'))
check('前端动态字段日期与周内变化贯通', 'dynamicWeeklyRsiDate' in ui and 'dynamicWeeklyFresh' in ui
      and '当周动态RSI6进入20以下区域' in ui and '周内会变化' in ui)
check('数据失败清旧active且动态锁门', "'active': False, 'label': '当周动态RSI6进入20以下区域'" in production
      and 'broadObservation failed (locked)' in production)
check('旧完成周收复与5日文案清理', not any(x in ui for x in ('完成周RSI6收复20', '周RSI6收复20', '最长5日')))

out = {'task': 102, 'updatedForTask': 108, 'asOf': AS_OF, 'checks': checks,
       'realCacheEvidence': real}
(ROOT / 'zz_regress102.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {'checksPassed': sum(x['pass'] for x in checks.values()), 'checksTotal': len(checks),
           'failed': [k for k, v in checks.items() if not v['pass']]}
(ROOT / 'zz_regress102_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if summary['failed']:
    raise AssertionError(summary['failed'])
