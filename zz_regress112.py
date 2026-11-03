# -*- coding: utf-8 -*-
"""任务112：统一15~120日平台及12~104周/估值40%底部门；离线边界与九股完整生产链。"""
import copy
import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import update_data as ud

AS_OF = '20261030'
CORE_POSITIVE = {'600000.SH', '000895.SZ', '601818.SH', '601916.SH'}
NEGATIVE = {'600795.SH', '601233.SH', '601872.SH', '600926.SH', '002648.SZ'}
ALL_CODES = ['600000.SH', '000895.SZ', '601818.SH', '601916.SH', '600795.SH',
             '601233.SH', '601872.SH', '600926.SH', '002648.SZ']
NAMES = {'600000.SH': '浦发银行', '000895.SZ': '双汇发展', '601818.SH': '光大银行',
         '601916.SH': '浙商银行', '600795.SH': '国电电力', '601233.SH': '桐昆股份',
         '601872.SH': '招商轮船', '600926.SH': '杭州银行', '002648.SZ': '卫星化学'}
FORMAL = {'平台整理', '底部整理'}
DATA_FILES = ['public/fund_data.json', 'src/data/fund_data.json']
sha_before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in DATA_FILES}
checks, fatal_errors, real_cases = [], [], []
production_snapshot = {}


def check(name, condition, evidence=None):
    checks.append({'name': name, 'passed': bool(condition), 'evidence': evidence})


def dates_business(n, end=AS_OF):
    out, d = [], datetime.strptime(end, '%Y%m%d')
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.strftime('%Y%m%d'))
        d -= timedelta(days=1)
    return list(reversed(out))


def platform_bars(n, amplitude=0.10, uptrend=True, shrink=True, prior_end=85.0):
    """目标窗精确振幅；前置末端85使任何更长窗振幅>15%，不会被吞并。"""
    prior_n = ud.PLATFORM_MAX_DAYS + 60 - n
    ds = dates_business(prior_n + n)
    start = 70.0 if uptrend else 105.0
    rows = []
    for i in range(prior_n):
        close = start + (prior_end - start) * i / max(1, prior_n - 1)
        rows.append((ds[i], close * 1.002, close * 0.998, close, 100.0))
    low, high, close = 100.0, 100.0 * (1 + amplitude), 100.0 * (1 + amplitude / 2)
    for i in range(n):
        rows.append((ds[prior_n + i], high, low, close, 50.0 if shrink else 100.0))
    return rows


def weekly_bars(mode='flat'):
    # 前10周历史高位；12周夹具在窗口早期留低，避免最近4周创新低门误伤。
    periods = {'multi': 22, 'higher': 22, 'twelve': 22, 'eleven': 21}.get(mode, 140)
    ds = dates_business(periods * 5, AS_OF)[4::5]
    last = periods - 11
    rows = []
    for i, d in enumerate(ds):
        if i < 10:
            close = 200.0
        else:
            j = i - 10
            if mode == 'down':
                close = 100.0 - 40.0 * j / 129
            elif mode == 'multi':
                close = 100.0 + 10.0 * j / last
                if j in (2, 7):
                    close = 82.0
            elif mode == 'higher':
                close = 88.0 + 12.0 * j / last
            elif mode == 'near_high':
                close = 100.0 if j < 129 else 195.0
            else:
                close = 100.0
        low = close * 0.99
        if mode == 'flat' and i == 40:
            low = 85.0
        if mode in ('twelve', 'eleven') and i == 10:
            low = 85.0
        if mode == 'higher' and i - 10 in (2, 7):
            low = {2: 80.0, 7: 90.0}[i - 10]
        if mode == 'multi' and i - 10 in (2, 7):
            low = 80.0
        rows.append((d, close * 1.01, low, close, 100.0))
    return [b for b in rows for _ in range(4)] if mode in ('multi', 'higher', 'twelve', 'eleven') else rows


def valuation_history(samples=40, dual=True):
    rows = {}
    for i in range(samples):
        pe = 12.0 if i == samples - 1 else 20.0 + i
        date = AS_OF if i == samples - 1 else f'2020{(i // 28) + 1:02d}{(i % 28) + 1:02d}'
        rows[date] = {'peTtm': pe, 'pb': pe / 10 if dual else None}
    return rows


def valuation_boundary(rank):
    """10000个有效样本，当前样本排名rank，百分位精确为rank/100。"""
    rows, end = {}, datetime.strptime(AS_OF, '%Y%m%d')
    for i in range(9999):
        pe = 50.0 + i / 100000 if i < rank - 1 else 200.0 + i
        d = (end - timedelta(days=9999 - i)).strftime('%Y%m%d')
        rows[d] = {'peTtm': pe, 'pb': pe / 10}
    rows[AS_OF] = {'peTtm': 100.0, 'pb': 10.0}
    return rows


def evidence_view(e):
    if not e:
        return None
    keys = ('type', 'days', 'weeks', 'amplitude', 'drift', 'trendSlopePct', 'ma20',
            'ma20Previous', 'ma60', 'volRatio', 'weeklyStructure', 'weeklyStructureLabel',
            'moneyflowStart', 'moneyflowEnd', 'moneyflowDays', 'moneyflowCoveredDays',
            'moneyflowCoveragePct', 'intervalNetInflow', 'moneyflowPass', 'moneyflowReason',
            'valuationBasis', 'valuationScorePct', 'valuationPass', 'valuationReason',
            'valuationMetrics', 'distanceToAvailableHighPct', 'bottomShape', 'bottomPattern',
            'shapeRecognized', 'eligible', 'displayEligible', 'formalAdmission',
            'qualificationStatus', 'qualificationLabel', 'patternReasons')
    return {k: e.get(k) for k in keys if k in e}


try:
    for n in (15, 120):
        p = ud._platform_price_pattern(platform_bars(n))
        check(f'统一平台{n}日通过且只用一个标签', bool(p and p['days'] == n and p['type'] == '平台整理'), evidence_view(p))
    check('统一平台14日拒绝', ud._platform_price_pattern(platform_bars(14)) is None)
    for amplitude, expected in ((0.1499, True), (0.15, True), (0.1501, False)):
        p = ud._platform_price_pattern(platform_bars(15, amplitude=amplitude))
        check(f'统一平台振幅{amplitude * 100:.2f}%边界', bool(p) == expected
              and (not p or p['amplitude'] == round(amplitude * 100, 2)), evidence_view(p))
    check('统一平台前置下跌趋势拒绝', ud._platform_price_pattern(platform_bars(15, uptrend=False)) is None)
    check('统一平台总体未缩量拒绝', ud._platform_price_pattern(platform_bars(15, shrink=False)) is None)

    p15 = ud._platform_price_pattern(platform_bars(15))
    bars15 = platform_bars(15)
    days = [b[0] for b in bars15[-15:]]
    pos = ud._apply_platform_eligibility(p15, bars15, {d: 1.0 for d in days})
    neg = ud._apply_platform_eligibility(p15, bars15, {d: -1.0 for d in days})
    zero = ud._apply_platform_eligibility(p15, bars15, {d: 0.0 for d in days})
    missing = ud._apply_platform_eligibility(p15, bars15, {d: 1.0 for d in days[:-1]})
    check('平台资金正值且100%覆盖通过', pos['displayEligible'] and pos['moneyflowCoveragePct'] == 100, evidence_view(pos))
    check('平台资金负值拒绝', not neg['displayEligible'], evidence_view(neg))
    check('平台资金零值拒绝', not zero['displayEligible'], evidence_view(zero))
    check('平台资金缺一天拒绝', not missing['displayEligible'] and missing['moneyflowCoveragePct'] < 100, evidence_view(missing))

    flat_bars = weekly_bars('flat')
    flat = ud._bottom_weekly_price_pattern(flat_bars)
    check('12~104周长期走平可识别', bool(flat and flat['weeklyStructure'] == 'weekly_flat'), evidence_view(flat))
    twelve = ud._bottom_weekly_price_pattern(weekly_bars('twelve'))
    check('底部12周下边界通过', bool(twelve and twelve['weeks'] == 12), evidence_view(twelve))
    check('底部11周拒绝', ud._bottom_weekly_price_pattern(weekly_bars('eleven')) is None)
    multi = ud._bottom_weekly_price_pattern(weekly_bars('multi'))
    check('多重底可识别', bool(multi and multi['weeklyStructure'] == 'multi_bottom'), evidence_view(multi))
    higher = ud._bottom_weekly_price_pattern(weekly_bars('higher'))
    check('抬升低点可识别', bool(higher and higher['weeklyStructure'] == 'higher_lows'), evidence_view(higher))
    check('周线下跌中继拒绝', ud._bottom_weekly_price_pattern(weekly_bars('down')) is None)
    check('距历史高不足10%拒绝', ud._bottom_weekly_price_pattern(weekly_bars('near_high')) is None)
    recent_low = list(flat_bars)
    d, h, _, c, v = recent_low[-1]
    recent_low[-1] = (d, h, 70.0, c, v)
    check('最近四周仍创新低拒绝', ud._bottom_weekly_price_pattern(recent_low) is None)

    for rank, expected in ((3999, True), (4000, True), (4001, False)):
        value = ud._stock_valuation_evidence(valuation_boundary(rank), AS_OF)
        check(f'估值{rank / 100:.2f}%双指标边界', value['valuationBasis'] == 'dual'
              and value['valuationScorePct'] == rank / 100 and value['valuationPass'] == expected, value)
    single = ud._stock_valuation_evidence(valuation_history(dual=False), AS_OF)
    dual = ud._stock_valuation_evidence(valuation_history(dual=True), AS_OF)
    insufficient = ud._stock_valuation_evidence(valuation_history(samples=23), AS_OF)
    check('单指标有效可判并明确标注', single['valuationBasis'] == 'single' and single['valuationPass'], single)
    check('双指标有效取均值', dual['valuationBasis'] == 'dual' and dual['valuationPass'], dual)
    check('估值不足24样本拒绝', not insufficient['valuationPass'] and insufficient['valuationBasis'] == 'insufficient', insufficient)

    bottom_days = [b[0] for b in flat_bars[-flat['days']:]] if flat else []
    eligible = ud._apply_bottom_eligibility(flat, flat_bars, {d: 1.0 for d in bottom_days}, valuation_history())
    excluded = ud._apply_bottom_eligibility(flat, flat_bars, {d: -1.0 for d in bottom_days}, valuation_history())
    pending_flow = ud._apply_bottom_eligibility(flat, flat_bars, {d: 1.0 for d in bottom_days[:-1]}, valuation_history())
    pending_val = ud._apply_bottom_eligibility(flat, flat_bars, {d: 1.0 for d in bottom_days}, {})
    check('底部eligible分层', eligible['qualificationStatus'] == 'eligible' and eligible['formalAdmission'], evidence_view(eligible))
    check('底部excluded分层', excluded['qualificationStatus'] == 'excluded' and not excluded['formalAdmission'], evidence_view(excluded))
    check('底部缺资金pending且观察保留', pending_flow['qualificationStatus'] == 'pending' and pending_flow['bottomShape'], evidence_view(pending_flow))
    check('底部缺估值pending且观察保留', pending_val['qualificationStatus'] == 'pending' and pending_val['bottomShape'], evidence_view(pending_val))

    base = platform_bars(15)
    past = ud._platform_price_pattern(base)
    still_past = ud._platform_price_pattern(base + [('20261101', 300.0, 290.0, 295.0, 999.0)][:-1])
    check('平台识别不读取未来数据', past == still_past)
    hist = valuation_history()
    no_future = ud._stock_valuation_evidence(hist, AS_OF)
    with_future_rows = copy.deepcopy(hist)
    with_future_rows['20261231'] = {'peTtm': 0.01, 'pb': 0.01}
    check('估值排除识别日后样本', no_future == ud._stock_valuation_evidence(with_future_rows, AS_OF))
except Exception as exc:
    fatal_errors.append(f'合成边界: {type(exc).__name__}: {exc}')
    check('合成边界执行无异常', False, str(exc))


def merged_cache(codes):
    current = json.loads((ROOT / 'scripts/cache/vcp_cache.json').read_text(encoding='utf-8'))
    long_cache = json.loads((ROOT.parent / 'vcp_cache_1027.json').read_text(encoding='utf-8'))
    daily = {}
    for code in codes:
        merged = {r[0]: r for r in long_cache['stock_daily'].get(code, [])}
        merged.update({r[0]: r for r in current['stock_daily'].get(code, [])})
        daily[code] = [merged[d] for d in sorted(merged)][-1200:]
    current['stock_daily'] = daily
    current['stock_info'] = {code: {'name': NAMES[code]} for code in codes}
    current['stock_industry'] = {code: '测试行业' for code in codes}
    current['stock_industry_date'] = AS_OF
    return current


def run_production(codes, extra_patches=None):
    cache = merged_cache(codes)
    data = {'bottomWatch': {'items': []}, 'vcpWatch': {'items': []},
            'actionableSectors': {'items': []}, 'sectorFlows': {'items': []},
            'sectorScan': {'items': []}, 'bondData': {'marginTrading': {'temp': ''}}}

    class NoApi:
        def daily(self, **kwargs):
            raise RuntimeError('回归不允许回补或联网')

        def stock_basic(self, **kwargs):
            raise RuntimeError('回归不允许回补或联网')

    mc = {'members': {'TEST': list(codes)}, 'mv': {c: 10000000.0 for c in codes}, 'mvDate': AS_OF}
    import vcp_preview as vcp
    patches = [patch.object(vcp, 'load_cache', return_value=copy.deepcopy(cache)),
               patch.object(vcp, 'save_cache', side_effect=lambda _c: None),
               patch.object(ud, 'ensure_index_members', return_value=mc),
               patch.object(ud, '_ensure_mf_cache', return_value={}),
               patch.dict(ud.STOCKS, {}, clear=True)]
    extra = extra_patches or []
    for p in patches + extra:
        p.start()
    try:
        ud.fetch_vcp_stocks(NoApi(), AS_OF, data, {})
    finally:
        for p in reversed(patches + extra):
            p.stop()
    return data['vcpStocks']


try:
    cache9 = merged_cache(ALL_CODES)
    for code in ALL_CODES:
        rows = cache9['stock_daily'][code]
        bars = [(r[0], r[2], r[3], r[1], r[4]) for r in rows]
        flows = (cache9['patternMoneyflow']['rows'].get(code) or {})
        vals = (cache9['stockValuationHistory']['rows'].get(code) or {})
        ps = ud._platform_price_pattern(bars)
        bs = ud._bottom_weekly_price_pattern(bars)
        plat = ud._apply_platform_eligibility(ps, bars, flows)
        bottom = ud._apply_bottom_eligibility(bs, bars, flows, vals)
        real_cases.append({'code': code, 'name': NAMES[code], 'asOf': rows[-1][0],
                           'dailyBars': len(rows), 'dailyStart': rows[0][0], 'dailyEnd': rows[-1][0],
                           'platform': evidence_view(plat), 'bottom': evidence_view(bottom)})
    production_snapshot = run_production(ALL_CODES)
    production_snapshot['items'] = [{k: v for k, v in it.items() if k not in ('daily', 'weekly')}
                                    for it in production_snapshot.get('items', [])]
    all_patterns = [it['pattern'] for it in production_snapshot.get('items', [])]
    check('生产结果无长平台标签', '长平台整理' not in all_patterns, all_patterns)
    check('生产formed只计正式items', production_snapshot.get('formed') == len(production_snapshot.get('items', [])),
          {'formed': production_snapshot.get('formed'), 'items': len(production_snapshot.get('items', [])),
           'bottomShapeWatchCount': production_snapshot.get('bottomShapeWatchCount')})
    check('底部观察不计formed且有独立计数', production_snapshot.get('bottomShapeWatchCount')
          == len(production_snapshot.get('bottomShapeWatch', [])))
    for code in ALL_CODES:
        items = [it for it in production_snapshot.get('items', []) if it['code'] == code]
        drops = [d for d in production_snapshot.get('droppedByPatternEvidence', []) if d['code'] == code]
        watch = [w for w in production_snapshot.get('bottomShapeWatch', []) if w['code'] == code]
        case = next(x for x in real_cases if x['code'] == code)
        case['production'] = {'patterns': [it['pattern'] for it in items], 'drops': drops, 'bottomShapeWatch': watch}
        case['shapePassed'] = bool(case.get('bottom') and case['bottom'].get('bottomShape')
                                   and case['bottom'].get('shapeRecognized') and case['bottom'].get('weeklyStructure'))
        bottom = case.get('bottom') or {}
        case['qualificationPassed'] = bool(bottom.get('eligible'))
        expected_eligible = bool(bottom.get('moneyflowPass') and bottom.get('valuationPass'))
        formal_bottom = any(it['pattern'] == '底部整理' for it in items)
        formal_platform = any(it['pattern'] == '平台整理' for it in items)
        observation_ok = (not case['shapePassed'] or (len(watch) == 1 and watch[0]['bottomShape']
                          and watch[0]['formalAdmission'] == expected_eligible))
        eligibility_ok = (not case['shapePassed'] or bottom.get('eligible') == expected_eligible)
        classification_ok = (not expected_eligible or formal_bottom or formal_platform)
        case['releaseCasePassed'] = bool(observation_ok and eligibility_ok and classification_ok)
        if code in CORE_POSITIVE:
            check(f'核心正例周线结构:{NAMES[code]}', case['shapePassed'], bottom)
        check(f'九股资格/观察/分类一致:{NAMES[code]}', case['releaseCasePassed'], {
            'expectedEligible': expected_eligible, 'actualEligible': bottom.get('eligible'),
            'formalBottom': formal_bottom, 'formalPlatform': formal_platform,
            'observation': watch, 'drops': drops})
        if expected_eligible:
            check(f'观察项formalAdmission为true:{NAMES[code]}', len(watch) == 1 and watch[0]['formalAdmission'] is True, watch)
    zs = next(x for x in real_cases if x['code'] == '601916.SH')
    check('浙商估值40%新门转为底部eligible', bool(zs['bottom'] and zs['bottom']['eligible']
          and zs['bottom']['valuationPass'] and zs['bottom']['moneyflowPass']), zs['bottom'])
    hz = next(x for x in real_cases if x['code'] == '600926.SH')
    structure_ok = bool((hz['platform'] or {}).get('displayEligible') or (hz['bottom'] or {}).get('displayEligible'))
    high_drop = any('高位门' in reason for d in hz['production']['drops'] for reason in d['reasons'])
    check('杭州银行结构即使通过也被高位门排除', structure_ok and high_drop
          and not any(p in FORMAL for p in hz['production']['patterns']),
          {'structureOk': structure_ok, 'production': hz['production']})

    fake_vcp = {'formed': True, 'distPct': 0.0, 'pivot': 100.0, 'invalidation': 90.0,
                'volConfirm': 100.0, 'count': 3, 'contractions': [8, 6, 4],
                'contractionsOk': [True, True, True], 'decreasing': True}
    priority = run_production(['600926.SH'], [
        patch.object(ud, '_vcp_level_strict', side_effect=[dict(fake_vcp), None]),
        patch.object(ud, '_trend_template', return_value={'pass': True, 'evidence': []})])
    check('VCP分类优先且不被统一平台抢占', any(it['pattern'] == 'VCP收缩型'
          for it in priority.get('items', [])), [it['pattern'] for it in priority.get('items', [])])
except Exception as exc:
    fatal_errors.append(f'真实九股生产链: {type(exc).__name__}: {exc}')
    check('真实九股生产链执行无异常', False, str(exc))


try:
    source = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
    weekly = (ROOT / 'src/sections/WeeklySummary.tsx').read_text(encoding='utf-8')
    eci = (ROOT / 'src/sections/ECIPanel.tsx').read_text(encoding='utf-8')
    evidence_ui = (ROOT / 'src/sections/patternEvidence.ts').read_text(encoding='utf-8')
    check('统一平台常量与单一识别链', 'PLATFORM_MIN_DAYS, PLATFORM_MAX_DAYS = 15, 120' in source
          and 'PLATFORM_MAX_AMP = 0.15' in source and 'def _platform_price_pattern(bars):' in source
          and 'long=True' not in source)
    check('底部常量与估值门', 'BOTTOM_MIN_WEEKS, BOTTOM_MAX_WEEKS = 12, 104' in source
          and 'STOCK_VALUATION_MAX_PCT = 40.0' in source)
    check('生产无旧长平台输出字段', "'longPlat'" not in source and 'long_structure' not in source)
    check('生产高位门主分支回退共用证据', 'def non_cup_fallback():' in source
          and 'for evidence in (plat, bottom):' in source and 'if ext_high:' in source)
    check('前端统一平台新口径', '统一平台 · 15~120日 · 振幅≤15%' in eci
          and '26~104周' not in eci and '15~44日' not in eci and '45~120日' not in eci)
    check('前端底部新口径', '最少12周' in weekly and '≤40%' in weekly
          and '最少12周' in evidence_ui and '<= 40' in evidence_ui)
    check('前端缺资金或估值不显示正式底部', 'completeBottomEvidence' in evidence_ui
          and 'formalPatternDisplayable' in evidence_ui and 'filter(formalPatternDisplayable)' in eci)
    check('生产输出独立观察与剔除清单', "'bottomShapeWatch': bottom_shape_watch[:100]" in source
          and "'droppedByPatternEvidence': dropped_pattern_evidence[:100]" in source)
except Exception as exc:
    fatal_errors.append(f'前后端契约: {type(exc).__name__}: {exc}')
    check('前后端契约执行无异常', False, str(exc))

sha_after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in DATA_FILES}
check('两份生产fund_data保持不变', sha_before == sha_after, {'before': sha_before, 'after': sha_after})
core_passed = sum(bool(next((x for x in real_cases if x['code'] == code), {}).get('shapePassed')) for code in CORE_POSITIVE)
core_eligible = sum(bool(next((x for x in real_cases if x['code'] == code), {}).get('qualificationPassed')) for code in CORE_POSITIVE)
all_passed = all(c['passed'] for c in checks) and not fatal_errors and core_passed == len(CORE_POSITIVE)
result = {
    'task': 112, 'asOf': AS_OF, 'allPassed': all_passed,
    'releaseEligible': bool(all_passed and core_passed == len(CORE_POSITIVE)),
    'corePositivePassed': core_passed, 'corePositiveTotal': len(CORE_POSITIVE),
    'coreEligiblePassed': core_eligible, 'coreEligibleTotal': len(CORE_POSITIVE),
    'checksPassed': sum(c['passed'] for c in checks), 'checksTotal': len(checks),
    'failed': [c['name'] for c in checks if not c['passed']], 'fatalErrors': fatal_errors,
    'checks': checks, 'realCases': real_cases, 'production': production_snapshot,
    'dataSha256Before': sha_before, 'dataSha256After': sha_after,
    'note': '离线确定性边界及真实九股缓存完整生产链；不联网、不回补、不写生产fund_data。底部资格通过可由统一平台分类优先承接。'
}
(ROOT / 'zz_regress112_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: result[k] for k in ('allPassed', 'releaseEligible', 'corePositivePassed',
      'corePositiveTotal', 'coreEligiblePassed', 'coreEligibleTotal', 'checksPassed',
      'checksTotal', 'failed', 'fatalErrors')}, ensure_ascii=False, indent=2))
for case in real_cases:
    b, p = case.get('bottom') or {}, case.get('platform') or {}
    print(case['name'], case.get('production'), '平台=', p.get('days'), p.get('amplitude'),
          '底部=', b.get('weeklyStructureLabel'), '净流入=', b.get('intervalNetInflow'),
          '估值=', b.get('valuationScorePct'), '原因=', b.get('patternReasons'))
raise SystemExit(0 if all_passed else 1)
