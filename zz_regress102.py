# -*- coding: utf-8 -*-
"""任务102：五宽基周RSI×低估值AND观察窗；真实输入、逐日历史与既有函数保护。"""
import copy
import importlib.util
import inspect
import json
import re
import tempfile
import time
from pathlib import Path

import pandas as pd
import update_data as ud

ROOT = Path(__file__).resolve().parent
AS_OF = '20261030'
CODES = [x[0] for x in ud.OBSERVATION_INDICES]
NAMES = dict(ud.OBSERVATION_INDICES)
REAL = json.loads((ROOT / 'zz_audit102_real_inputs.json').read_text(encoding='utf-8'))
ud.API_DELAY = 0
checks = {}


def check(name, condition, evidence=None):
    checks[name] = {'pass': bool(condition), 'evidence': evidence}


def weekly(code, rsi=50.0, passed=False, fresh=True):
    return {'indexCode': code, 'indexName': NAMES[code], 'weeklyRsi': rsi,
            'weeklyRsiDate': '20261023', 'dailyDate': AS_OF,
            'weeklyFresh': fresh, 'rsiPass': passed, 'rsiReason': '受控边界'}


def valuation(code, pe=50.0, pb=50.0, low=False, fresh=True, sufficient=True):
    return {'indexCode': code, 'indexName': NAMES[code], 'peTtm': 10.0, 'pb': 1.0,
            'pePct10y': pe, 'pbPct10y': pb, 'valuationDate': AS_OF,
            'observations': 600 if sufficient else 499, 'fresh': fresh,
            'sufficientHistory': sufficient, 'valuationLow': low, 'reason': '受控边界'}


def decide(rsi_pass=(), low=(), rsi_values=None, valuation_values=None):
    rsi_values = rsi_values or {}
    valuation_values = valuation_values or {}
    ws = []
    for c in CODES:
        value = rsi_values.get(c, 19.0 if c in rsi_pass else 50.0)
        ws.append(weekly(c, value, value < 20))
    vs = []
    for c in CODES:
        pe, pb = valuation_values.get(c, (10.0, 10.0) if c in low else (50.0, 50.0))
        vs.append(valuation(c, pe, pb, pe <= 20 and pb <= 20))
    return ud._broad_observation_decision(ws, vs, AS_OF)


# AND边界：两个完全满足才开；RSI=20不满足；估值>20、单指标低均不满足。
check('两个同名宽基完全AND满足才开', decide(CODES[:2], CODES[:2])['active'])
check('单只完全满足不能开', not decide(CODES[:1], CODES[:1])['active'])
check('RSI等于20严格不开', not decide(CODES[:2], CODES[:2], {c: 20.0 for c in CODES[:2]})['active'])
check('RSI高于20不开', not decide(CODES[:2], CODES[:2], {c: 20.01 for c in CODES[:2]})['active'])
check('PE高于20分位不开', not decide(CODES[:2], CODES[:2], valuation_values={c: (20.1, 10.0) for c in CODES[:2]})['active'])
check('PB高于20分位不开', not decide(CODES[:2], CODES[:2], valuation_values={c: (10.0, 20.1) for c in CODES[:2]})['active'])
check('只有PE低而PB不低不开', not decide(CODES[:2], (), valuation_values={c: (10.0, 50.0) for c in CODES[:2]})['active'])
check('只有PB低而PE不低不开', not decide(CODES[:2], (), valuation_values={c: (50.0, 10.0) for c in CODES[:2]})['active'])

# 五宽基逐一证明不会把甲的RSI与乙的估值拼接；每只单独特征均实名归属。
pairing = {}
for i, code in enumerate(CODES):
    crossed = decide([code], [CODES[(i + 1) % len(CODES)]])
    single = decide([code], [code])
    pairing[code] = {'crossedQualified': crossed['qualifiedCount'], 'singleQualified': single['qualifiedIndices']}
    check(f'同名配对:{code}', crossed['qualifiedCount'] == 0 and single['qualifiedIndices'] == [NAMES[code]], pairing[code])

# 缺估值、缺周RSI均不计满足。
ws = [weekly(c, 19.0, True) for c in CODES[:2]]
vs = [valuation(CODES[0], 10, 10, True)]
missing_val = ud._broad_observation_decision(ws, vs, AS_OF)
check('缺估值锁门', not missing_val['active'] and missing_val['qualifiedCount'] == 1, missing_val['reason'])
missing_rsi = ud._broad_observation_decision([ws[0]], [valuation(c, 10, 10, True) for c in CODES[:2]], AS_OF)
check('缺周RSI锁门', not missing_rsi['active'] and missing_rsi['qualifiedCount'] == 1, missing_rsi['reason'])


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
short_rows = fresh_rows[-499:]
stale = valuation_gate_with_rows(stale_rows)
insufficient = valuation_gate_with_rows(short_rows)
check('估值陈旧即使分位低也锁门', all(not x['fresh'] and not x['valuationLow'] for x in stale), stale[0])
check('估值历史不足500日锁门', all(not x['sufficientHistory'] and not x['valuationLow'] for x in insufficient), insufficient[0])

# 当前周单日崩跌可令日RSI<20，但最近完成周RSI=100，观察门只能采用后者。
days = pd.bdate_range('2025-01-03', '2026-10-30').strftime('%Y%m%d').tolist()
closes = [100.0] * len(days)
closes[-1] = 1.0
controlled_daily = [[d, closes[i], closes[i], closes[i], 1000.0] for i, d in enumerate(days)]
daily_rsi = ud._rsi_series(closes, 14)[-1]
controlled_weekly = ud._broad_weekly_rsi(AS_OF, {CODES[0]: controlled_daily})[0]
check('单日RSI与周RSI冲突只用完成周', daily_rsi < 20 and controlled_weekly['weeklyRsi'] == 100
      and not controlled_weekly['rsiPass'], {'dailyRsi': daily_rsi, 'weekly': controlled_weekly})
stale_weekly = ud._broad_weekly_rsi(AS_OF, {CODES[0]: controlled_daily[:-1]})[0]
check('行情非本批有效日周RSI锁门', not stale_weekly['weeklyFresh'] and not stale_weekly['rsiPass'], stale_weekly)

# 真实当前输入：直接复用生产周RSI/估值函数，估值缓存只写临时目录。
daily_map = {c: REAL['indices'][c]['daily'] for c in CODES}
real_weekly = ud._broad_weekly_rsi(AS_OF, daily_map)
real_valuation = None
old_path = ud.BROAD_VALUATION_PATH
try:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'valuation.json'
        path.write_text(json.dumps({'rows': {c: REAL['indices'][c]['valuation'] for c in CODES}}), encoding='utf-8')
        ud.BROAD_VALUATION_PATH = str(path)
        real_valuation = ud._broad_valuation_gate(EmptyPro(), AS_OF)
finally:
    ud.BROAD_VALUATION_PATH = old_path
real_decision = ud._broad_observation_decision(real_weekly, real_valuation, AS_OF)
expected = {
    '000016.SH': (35.62, 11.0857, 67.8, 1.2462, 54.4),
    '000300.SH': (25.74, 12.9122, 53.5, 1.3427, 23.1),
    '000905.SH': (33.36, 26.7601, 57.1, 1.9436, 52.5),
    '000688.SH': (37.71, 90.461, 63.6, 5.5488, 55.5),
    '399673.SZ': (28.59, 22.0067, 1.8, 3.9664, 10.8),
}
actual_compact = {x['indexCode']: (x['weeklyRsi'], x['peTtm'], x['pePct10y'], x['pb'], x['pbPct10y'])
                  for x in real_decision['items']}
check('真实五宽基数值与审计一致', actual_compact == expected, actual_compact)
check('真实当前仅创业板50估值低且五只周RSI均未超卖',
      [x['indexCode'] for x in real_decision['items'] if x['valuationLow']] == ['399673.SZ']
      and not any(x['rsiPass'] for x in real_decision['items']))
check('真实当前观察窗不触发', not real_decision['active'] and real_decision['qualifiedCount'] == 0, real_decision['reason'])
check('科创50真实历史1520其余2429', {x['indexCode']: x['observations'] for x in real_decision['items']} == {
    '000016.SH': 2429, '000300.SH': 2429, '000905.SH': 2429, '000688.SH': 1520, '399673.SZ': 2429})


class RealDailyMock:
    def __init__(self):
        self.range_calls = []

    def index_daily(self, **kwargs):
        if 'trade_date' in kwargs:
            return pd.DataFrame()
        code = kwargs['ts_code']
        self.range_calls.append(code)
        rows = [r for r in daily_map[code] if kwargs['start_date'] <= r[0] <= kwargs['end_date']]
        return pd.DataFrame(rows, columns=['trade_date', 'close', 'high', 'low', 'vol'])


old_idx_path = ud.BROAD_IDX_CACHE_PATH
try:
    with tempfile.TemporaryDirectory() as tmp:
        ud.BROAD_IDX_CACHE_PATH = str(Path(tmp) / 'broad.json')
        daily_pro = RealDailyMock()
        backfilled = ud._broad_idx_bars(daily_pro, AS_OF, codes=CODES)
finally:
    ud.BROAD_IDX_CACHE_PATH = old_idx_path
check('观察窗五宽基独立真实日线回补链路', daily_pro.range_calls == CODES
      and set(backfilled) == set(CODES) and '399006.SZ' not in backfilled
      and all(backfilled[c][-1][0] == AS_OF for c in CODES), daily_pro.range_calls)


def long_data(observation, sell=None, top=False):
    return {
        'bondData': {'marginTrading': {'temp': '🔴冷', 'verdict': '冷温边界'}, 'stats': {'1m_change': {'y10': 25}}},
        'broadVcp': {'items': []}, 'sectorFlows': {'trade_date': '2026-10-30'},
        'broadObservation': observation,
        'broadOsc': {'trade_date': '2026-10-30', 'items': ([{'indexName': '上证50', 'state': '顶部风险'}] if top else []),
                     'sellAlerts': sell or [], 'buyWindows': [], 'reboundWatch': [], 'extremeEvidence': []},
    }


active_observation = decide(CODES[:2], CODES[:2])
opened = long_data(active_observation)
ud.build_long_window(opened)
check('冷普通水温债券降级后观察窗仍open', opened['longWindow']['window'] == 'open'
      and opened['longWindow']['standardWindow'] == 'closed'
      and opened['longWindow']['windowType'] == 'oversold_valuation_watch'
      and not opened['longWindow']['temporary'], {k: opened['longWindow'][k] for k in
      ('window', 'standardWindow', 'windowType', 'temporary')})
check('观察窗明确非趋势反转或买点', '不是趋势反转或买点' in opened['longWindow']['reason'])
ud.build_funnel(opened)
step0 = next(s for s in opened['funnel']['steps'] if s['n'] == 0)
step1 = next(s for s in opened['funnel']['steps'] if s['n'] == 1)
check('漏斗第0至1步贯通不灰化', opened['funnel']['window'] == 'open' and step0['lamp'] == '🟢'
      and step0['title'] == '极端超卖/低估值观察窗' and '不是趋势反转或买点' in step0['conclusion']
      and step1['rows'] is not None, {'step0': step0, 'step1Count': len(step1['rows'])})
for label, kwargs in (('强硬减仓', {'sell': ['上证50']}), ('顶部风险', {'top': True})):
    vetoed = long_data(active_observation, **kwargs)
    ud.build_long_window(vetoed)
    check(f'{label}否决观察窗', vetoed['longWindow']['window'] == 'closed'
          and vetoed['longWindow']['windowType'] == 'standard'
          and not vetoed['longWindow']['oversoldValuationWatch']['effectiveActive']
          and vetoed['longWindow']['oversoldValuationWatch']['blockedBy'],
          vetoed['longWindow']['oversoldValuationWatch']['blockedBy'])

# 真实历史逐日扫描：估值取各日当时十年历史，周RSI只取当时最近完成周。
def historical_valuation(code, date):
    rows = [r for r in REAL['indices'][code]['valuation'] if r[0] <= date]
    if not rows:
        return valuation(code, low=False)
    latest = rows[-1]
    cutoff = (pd.Timestamp(latest[0]) - pd.DateOffset(years=10)).strftime('%Y%m%d')
    history = [r for r in rows if cutoff <= r[0] <= latest[0]]
    pe_pct = sum(r[1] <= latest[1] for r in history) / len(history) * 100
    pb_pct = sum(r[2] <= latest[2] for r in history) / len(history) * 100
    age = (pd.Timestamp(date) - pd.Timestamp(latest[0])).days
    fresh = 0 <= age <= ud.OBSERVATION_VALUATION_MAX_AGE_DAYS
    sufficient = len(history) >= ud.OBSERVATION_VALUATION_MIN_OBS
    low = fresh and sufficient and pe_pct <= 20 and pb_pct <= 20
    return {'indexCode': code, 'indexName': NAMES[code], 'peTtm': latest[1], 'pb': latest[2],
            'pePct10y': pe_pct, 'pbPct10y': pb_pct, 'valuationDate': latest[0],
            'observations': len(history), 'fresh': fresh, 'sufficientHistory': sufficient,
            'valuationLow': low}


def scan_history(extra_daily=None, start='20250101'):
    combined = {c: list(daily_map[c]) + list((extra_daily or {}).get(c) or []) for c in CODES}
    combined = {c: sorted({r[0]: r for r in rows}.values(), key=lambda r: r[0]) for c, rows in combined.items()}
    dates = sorted({r[0] for rows in combined.values() for r in rows if start <= r[0] <= AS_OF})
    positives = []
    scanned = 0
    for date in dates:
        ws = ud._broad_weekly_rsi(date, {c: [r for r in combined[c] if r[0] <= date] for c in CODES})
        vs = [historical_valuation(c, date) for c in CODES]
        decision = ud._broad_observation_decision(ws, vs, date)
        scanned += 1
        if decision['active']:
            positives.append({'tradeDate': date, 'qualifiedIndices': decision['qualifiedIndices'],
                              'items': [{'indexCode': x['indexCode'], 'weeklyRsiDate': x['weeklyRsiDate'],
                                         'weeklyRsi': x['weeklyRsi'], 'pePct10y': round(x['pePct10y'], 2),
                                         'pbPct10y': round(x['pbPct10y'], 2)}
                                        for x in decision['items'] if x['qualified']]})
    return {'start': start, 'end': AS_OF, 'scannedDays': scanned, 'positiveCount': len(positives),
            'firstPositive': positives[0] if positives else None, 'positivesSample': positives[:20]}


scan2025 = scan_history()
check('2025以来真实历史扫描无伪造正例', scan2025['scannedDays'] > 300,
      {k: v for k, v in scan2025.items() if k != 'positivesSample'})
if scan2025['positiveCount'] == 0:
    supplement_path = ROOT / 'zz_audit102_pre2025_daily.json'
    if supplement_path.exists():
        supplement = json.loads(supplement_path.read_text(encoding='utf-8'))
    else:
        import tushare as ts
        source = (ROOT / 'scripts/update_daily_v2.py').read_text(encoding='utf-8')
        token = re.search(r"TUSHARE_TOKEN\s*=\s*['\"]([^'\"]+)", source).group(1)
        pro = ts.pro_api(token)
        supplement = {'start': '20180101', 'end': '20241231', 'daily': {}}
        for code in CODES:
            time.sleep(0.35)
            frame = pro.index_daily(ts_code=code, start_date='20180101', end_date='20241231',
                                    fields='ts_code,trade_date,close,high,low,vol')
            if frame is None or frame.empty:
                raise RuntimeError(f'{code}: earlier index_daily empty')
            supplement['daily'][code] = [[str(r.trade_date), float(r.close), float(r.high), float(r.low), float(r.vol)]
                                         for r in frame.sort_values('trade_date').itertuples()]
        supplement_path.write_text(json.dumps(supplement, ensure_ascii=False) + '\n', encoding='utf-8')
    earlier_scan = scan_history(supplement['daily'], '20190101')
else:
    earlier_scan = None
positive_scan = scan2025 if scan2025['positiveCount'] else earlier_scan
check('真实历史找到至少一个AND正例且逐只合规', positive_scan and positive_scan['positiveCount'] > 0
      and all(len(p['qualifiedIndices']) >= 2 and all(x['weeklyRsi'] < 20 and x['pePct10y'] <= 20 and x['pbPct10y'] <= 20
              for x in p['items']) for p in positive_scan['positivesSample']),
      None if not positive_scan else {k: v for k, v in positive_scan.items() if k != 'positivesSample'})

# 任务87/90/101保护范围逐字比较任务102实时基线。
spec = importlib.util.spec_from_file_location('update_data_task102_remote_baseline',
                                              ROOT / 'zz_update_data_task102_remote_baseline.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
# 任务103仅有意修改VCP三函数；其余门控和杯柄继续逐字保护。
protected = ('_extreme_rebound_decision', '_dividend_group_catalyst', '_osc_weekly_ma',
             '_weekly_ma150_200_display_gate', '_cup_handle_strict', '_cup_early_breakout',
             '_platform_contraction_practical_ok', '_trend_template', 'build_broad_osc')
for name in protected:
    check(f'既有函数未改:{name}', inspect.getsource(getattr(old, name)) == inspect.getsource(getattr(ud, name)),
          'source identical')

# 前端静态契约和失败锁门代码路径；实际bundle在nightly后另行核验。
types = (ROOT / 'src/hooks/useFundData.ts').read_text(encoding='utf-8')
weekly_ui = (ROOT / 'src/sections/WeeklySummary.tsx').read_text(encoding='utf-8')
funnel_ui = (ROOT / 'src/sections/funnelConclusions.ts').read_text(encoding='utf-8')
eci_ui = (ROOT / 'src/sections/ECIPanel.tsx').read_text(encoding='utf-8')
production = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
workflow = (ROOT / '.github/workflows/daily-update.yml').read_text(encoding='utf-8')
check('前端类型横幅证据及徽章贯通', "'oversold_valuation_watch'" in types and 'broadObservation?:' in types
      and '极端超卖/低估值观察窗' in weekly_ui and 'weeklyRsiDate' in weekly_ui
      and 'pePct10y' in weekly_ui and 'pbPct10y' in weekly_ui
      and '观察窗AND门' in funnel_ui and '极端超卖/低估值观察窗·非买点' in eci_ui)
check('数据失败清旧active并锁门', "data['broadObservation'] = {" in production
      and "'active': False, 'label': '极端超卖/低估值观察窗'" in production
      and 'broadObservation failed (locked)' in production)
check('估值缓存纳入nightly提交', 'scripts/cache/broad_valuation.json' in workflow)
check('创业板50独立回补不扩大原九宽基且不用399006替代',
      '399673.SZ' in CODES and '399006.SZ' not in CODES
      and '399673.SZ' not in [x[0] for x in ud.BROAD_ETF_MAP]
      and "codes=[c for c, _ in OBSERVATION_INDICES]" in production)

out = {'task': 102, 'asOf': AS_OF, 'checks': checks,
       'current': {'active': real_decision['active'], 'qualifiedCount': real_decision['qualifiedCount'],
                   'reason': real_decision['reason'], 'items': real_decision['items']},
       'history2025': scan2025, 'historyEarlier': earlier_scan}
(ROOT / 'zz_regress102.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {'checksPassed': sum(x['pass'] for x in checks.values()), 'checksTotal': len(checks),
           'failed': [k for k, v in checks.items() if not v['pass']],
           'currentActive': real_decision['active'], 'history2025Positive': scan2025['positiveCount'],
           'earlierPositive': earlier_scan['positiveCount'] if earlier_scan else None,
           'firstPositive': positive_scan.get('firstPositive') if positive_scan else None}
(ROOT / 'zz_regress102_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if summary['failed']:
    raise AssertionError(f"任务102检查失败: {summary['failed']}")
