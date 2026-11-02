# -*- coding: utf-8 -*-
"""任务87离线回归：突破后位置瑕疵、全量漏斗、极端修复临时窗、高股息独立池。"""
import copy
import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('update_data87', ROOT / 'scripts' / 'update_data.py')
u = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(u)
u.API_DELAY = 0
results = []


def check(name, condition, evidence):
    results.append({'name': name, 'pass': bool(condition), 'evidence': evidence})
    if not condition:
        raise AssertionError(f'{name}: {evidence}')


# 中国广核：锚点结构保留，当前位置单独追加瑕疵。
cgn = {'breakout': True, 'formed': True, 'defects': [], 'qualified': True}
u._apply_post_breakout_position_defect(cgn, 88.4, -6.7)
check('中国广核突破后临近前高转瑕疵', cgn['qualified'] is False and cgn['defects'] == [
    '临近前高（距250日高点6.7%·一年分位88.4%）'], cgn)
check('位置风险不改写锚点结构', cgn['formed'] and cgn['positionRisk']['structureIntact'], cgn['positionRisk'])
ordinary = {'breakout': False, 'formed': True, 'defects': []}
u._apply_post_breakout_position_defect(ordinary, 88.4, -6.7)
check('普通未突破形态不追加突破后瑕疵', not ordinary['defects'], ordinary)


def osc(n=0, buy=None, sell=None, top=False, date='2026-10-19'):
    names = ['上证50', '沪深300', '中证500', '中证1000', '科创50', '创业板指']
    return {
        'trade_date': date, 'extremeEvidence': [], 'buyWindows': buy or [],
        'reboundWatch': [], 'sellAlerts': sell or [],
        'items': ([{'indexName': '上证50', 'state': '顶部风险'}] if top else
                  [{'indexName': '沪深300', 'state': '完整抄底窗口'}] if buy else []),
    }


def observation(zone=False, dynamic=False):
    dynamic_rsi = 18.0 if zone else 25.0 if dynamic else 30.0
    item = {'indexCode': '000300.SH', 'indexName': '沪深300', 'qualified': zone,
            'previousWeeklyRsi6': 18.0, 'weeklyRsi6': 25.0,
            'previousWeeklyRsiDate': '20261016', 'weeklyRsiDate': '20261023',
            'dailyDate': '20261019', 'weeklyFresh': True, 'rsiPass': zone,
            'dynamicWeeklyRsi6': dynamic_rsi, 'dynamicWeeklyRsiDate': '20261019',
            'dynamicWeeklyFresh': True, 'inOversoldZone': zone, 'dynamicWatch': dynamic and not zone}
    return {'active': zone, 'requiredCount': 1, 'qualifiedCount': int(zone),
            'qualifiedIndices': ['沪深300'] if zone else [], 'items': [item], 'reason': '受控RSI6边界'}


days = ['20261019', '20261020', '20261021', '20261022', '20261023', '20261026']
check('动态值不在20以下区域不开临时窗', not u._extreme_rebound_decision(observation(), '20261019')['active'],
      u._extreme_rebound_decision(observation(), '20261019'))
pending = u._extreme_rebound_decision(observation(dynamic=True), '20261019')
check('动态值大于20不待确认也不开窗', not pending['pendingConfirmation'] and not pending['active'], pending)
opened = u._extreme_rebound_decision(observation(zone=True), '20261019', trading_days=days)
check('单指数当周动态RSI6不超20即开', opened['active'] and opened['remainingDays'] == 1
      and opened['maxDays'] is None, opened)
sell = u._extreme_rebound_decision(observation(zone=True), '20261019')
check('强硬减仓不否决RSI6临时窗', sell['active'] and not sell['blockedBy'], sell)
top = u._extreme_rebound_decision(observation(zone=True), '20261019')
check('顶部风险不否决RSI6临时窗', top['active'] and not top['blockedBy'], top)
prev = {**opened, 'windowType': 'extreme_rebound', 'temporary': True}
continued = u._extreme_rebound_decision(observation(zone=True), '20261020', prev, days)
check('仍在20以下区域只按当日状态active', continued['active'] and continued['remainingDays'] == 1
      and continued['maxDays'] is None, continued)
expired = u._extreme_rebound_decision(observation(), '20261026', prev, days)
check('离开20以下区域立即关闭且无到期续命', not expired['expired'] and not expired['active']
      and expired['remainingDays'] == 0, expired)

# 冷水温原层级为closed；当周动态RSI6≤20可独立旁路，大于20不能误开。
def long_data(obs, osc_block=None):
    return {'bondData': {'marginTrading': {'temp': '🔴冷', 'verdict': '测试'},
                         'stats': {'1m_change': {'y10': 0}}},
            'broadVcp': {'items': []}, 'broadOsc': osc_block or osc(),
            'broadObservation': obs, 'sectorFlows': {'trade_date': '2026-10-19'}}

ld = long_data(observation(dynamic=True))
u.build_long_window(ld)
check('冷水温+动态值大于20仍关窗', ld['longWindow']['window'] == 'closed'
      and ld['longWindow']['windowType'] == 'standard', ld['longWindow']['extremeRebound'])
ld2 = long_data(observation(zone=True))
u.build_long_window(ld2)
check('RSI6临时窗独立open且保留standardWindow', ld2['longWindow']['window'] == 'open'
      and ld2['longWindow']['standardWindow'] == 'closed'
      and ld2['longWindow']['windowType'] == 'extreme_rebound'
      and ld2['longWindow']['temporary'], {k: ld2['longWindow'][k] for k in
      ('window', 'standardWindow', 'windowType', 'startedDate', 'remainingDays')})

# 真实10-26快照：全量漏斗和中国广核缺陷字段。
fd = json.loads((ROOT / 'zz_fd_1026.json').read_text(encoding='utf-8'))
for it in fd['vcpStocks']['items']:
    if it['code'] == '003816.SZ':
        u._apply_post_breakout_position_defect(it['cupHandle'], it['histPct'], it['distHigh250'])
        it['defects'] = list(it['cupHandle']['defects'])
        it['entryTier'] = 'fuzzy'
u.build_funnel(fd)
step3 = next(s for s in fd['funnel']['steps'] if s['key'] == 'vcp')
check('第3步总数等于vcpStocks.items', len(step3['rows']) == len(fd['vcpStocks']['items']) == 34,
      {'step3': len(step3['rows']), 'vcp': len(fd['vcpStocks']['items']),
       'tracks': {t: sum(r['track'] == t for r in step3['rows']) for t in ('reson', 'cherry', 'reserve')}})
check('第3步不再excluded', step3['excluded'] == 0, step3['excluded'])
row_cgn = next(r for r in step3['rows'] if r['code'] == '003816.SZ')
check('中国广核瑕疵在总览可见', row_cgn['entryTier'] == 'fuzzy' and '临近前高' in row_cgn['defects'][0], row_cgn)
check('路径使用全量形态数', '个股：34只成型' in fd['funnel']['path'], fd['funnel']['path'])

# 实际broad_idx_cache：历史证据可计算；无确认时不得误开。
fd2 = json.loads((ROOT / 'zz_fd_1026.json').read_text(encoding='utf-8'))
u.build_broad_osc(fd2)
u.build_long_window(fd2)
if not fd2['broadOsc']['triggerIndices']:
    check('10-26无核心完整确认不误开临时窗', fd2['longWindow']['windowType'] != 'extreme_rebound',
          {'evidence': len(fd2['broadOsc']['extremeEvidence']), 'triggers': fd2['broadOsc']['triggerIndices'],
           'window': fd2['longWindow']['window'], 'reason': fd2['longWindow']['extremeRebound']['reason']})
else:
    check('10-26临时窗严格服从证据数量与风险否决',
          (not fd2['longWindow']['extremeRebound']['active'])
          == (not fd2['longWindow']['extremeRebound']['qualified']), fd2['longWindow']['extremeRebound'])


class MockPro:
    def __init__(self):
        self.daily_calls = 0
        self.daily_dates = []

    def index_weight(self, index_code, start_date, end_date):
        code = '600000.SH' if index_code == '000510.SH' else '000001.SZ'
        return pd.DataFrame([{'trade_date': '20260930', 'con_code': code}])

    def stock_basic(self, exchange, list_status, fields):
        return pd.DataFrame([{'ts_code': '600000.SH', 'name': 'A500样本'},
                             {'ts_code': '000001.SZ', 'name': '低息样本'}])

    def daily_basic(self, trade_date, fields):
        self.daily_calls += 1
        self.daily_dates.append(trade_date)
        return pd.DataFrame([
            {'ts_code': '600000.SH', 'trade_date': trade_date, 'close': 10.0, 'total_mv': 3000000, 'dv_ttm': 5.2},
            {'ts_code': '000001.SZ', 'trade_date': trade_date, 'close': 20.0, 'total_mv': 3000000, 'dv_ttm': 3.9},
            {'ts_code': '999999.SH', 'trade_date': trade_date, 'close': 1.0, 'total_mv': 9000000, 'dv_ttm': 9.9},
        ])


# 任务91：无催化组清空旧名单且零daily_basic；有效催化才走任务87原池逻辑。
u.DIVIDEND_GROUP_CACHE_PATH = str(ROOT / 'zz_dividend_group_mock_cache87.json')
u._save_json_cache(u.DIVIDEND_GROUP_CACHE_PATH, {})
hidden_mock = MockPro()
hidden_data = {'sectorFlows': {'trade_date': '2026-10-26'},
               'dividendWatch': {'visible': True, 'count': 73, 'items': [{'code': 'old'}]}}
u.build_dividend_watch(hidden_mock, '20261027', hidden_data)
check('高股息无催化组强制隐藏且零daily_basic', hidden_mock.daily_calls == 0
      and hidden_data['dividendWatch']['visible'] is False
      and hidden_data['dividendWatch']['count'] == 0
      and hidden_data['dividendWatch']['items'] == [], hidden_data['dividendWatch'])
u._save_json_cache(u.DIVIDEND_GROUP_CACHE_PATH, {
    'sw_list': [{'code': 'SW', 'name': '测试行业'}],
    'sw_members': {'SW': ['600000.SH', '000001.SZ', '999999.SH']},
    'index_daily': {'SW': [['20261026', 1, 1]]}, 'concepts': [], 'ths_members': {}, 'ths_index': {}})
u._dividend_group_catalyst = lambda group, rows, trade_date: {
    'type': group['type'], 'code': group['code'], 'name': group['name'],
    'catalyzed': True, 'catalystDate': '20261026', 'signalAge': 0,
    'dailyDate': '20261026', 'reason': '测试有效催化'}
mock = MockPro()
u.DIVIDEND_MEMBERS_PATH = str(ROOT / 'zz_dividend_mock_cache87.json')
div_data = {'sectorFlows': {'trade_date': '2026-10-26'}}
u.build_dividend_watch(mock, '20261027', div_data)
check('有效催化后高股息池含A500且dvTtm非空', div_data['dividendWatch']['count'] == 1
      and div_data['dividendWatch']['items'][0]['indexMembership'] == ['中证A500']
      and div_data['dividendWatch']['items'][0]['dvTtm'] == 5.2, div_data['dividendWatch'])
check('有效催化每日一次daily_basic且池外不混入', mock.daily_calls == 1
      and all(x['code'] != '999999.SH' for x in div_data['dividendWatch']['items']), mock.daily_calls)
check('盘前使用本批最新有效快照日期', mock.daily_dates == ['20261026']
      and div_data['dividendWatch']['trade_date'] == '20261026', mock.daily_dates)

report = {'passed': sum(x['pass'] for x in results), 'total': len(results), 'results': results}
(ROOT / 'zz_regress87.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'passed': report['passed'], 'total': report['total']}, ensure_ascii=False))
