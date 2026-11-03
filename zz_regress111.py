# -*- coding: utf-8 -*-
"""任务111：平台/周线底部新证据门。真实九股走完整生产链；失败也先写完整机器报告。"""
import copy
import hashlib
import json
import math
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
FORMAL = {'平台整理', '长平台整理', '底部整理'}
DATA_FILES = ['public/fund_data.json', 'src/data/fund_data.json']
sha_before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in DATA_FILES}
checks = []
fatal_errors = []
real_cases = []
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


def platform_bars(n, long=False, uptrend=True, wide=False, shrink=True, prior_end=None):
    maximum = ud.LP_MAX_DAYS if long else ud.PLATFORM_MAX_DAYS
    prior_n = maximum + 60 - n
    ds = dates_business(prior_n + n)
    # 平台前收低于平台，使任何更长窗都因振幅超限而不能吞并目标下边界。
    end = prior_end if prior_end is not None else (85.0 if long else 90.0)
    start = 80.0 if uptrend else end * 1.25
    rows = []
    for i in range(prior_n):
        close = start + (end - start) * i / max(1, prior_n - 1)
        rows.append([ds[i], close * 1.002, close * 0.998, close, 100.0])
    for i in range(n):
        close = 100.0 + (0.2 if i % 2 else -0.2)
        spread = 0.07 if wide else 0.01
        rows.append([ds[prior_n + i], close * (1 + spread), close * (1 - spread), close,
                     50.0 if shrink else 100.0])
    return [tuple(r) for r in rows]


def weekly_bars(mode='flat'):
    # 每周五一根合成K线，周线重采样仍走生产函数；前10周为历史高位。
    periods = 36 if mode == 'multi' else 140
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
                close = 88.0 + 12.0 * j / last
                if j in (5, 15):
                    close = 82.0
            elif mode == 'near_high':
                close = 100.0 if j < 129 else 195.0
            else:
                close = 100.0
        low = close * 0.99
        if mode == 'flat' and i == 40:
            low = 85.0
        if mode == 'multi' and i - 10 in (5, 15):
            low = 80.0
        rows.append((d, close * 1.01, low, close, 100.0))
    # 生产入口还要求至少132根输入K线；多重底短样本复制周内记录但不新增周。
    return [b for b in rows for _ in range(4)] if mode == 'multi' else rows


def valuation_history(samples=40, boundary=False, dual=True):
    rows = {}
    for i in range(samples):
        if i == samples - 1:
            pe = 12.0
        elif boundary and i < 11:
            pe = 10.0 + i * 0.1
        else:
            pe = 20.0 + i
        date = AS_OF if i == samples - 1 else f'2020{(i // 28) + 1:02d}{(i % 28) + 1:02d}'
        rows[date] = {'peTtm': pe, 'pb': (pe / 10) if dual else None}
    # 单指标样例只有PE具备足够样本，PB不得参与均值。
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


# ── 合成通用边界：不用真实标签反推阈值。 ──
try:
    p15 = ud._platform_price_pattern(platform_bars(15))
    check('普通平台15日下边界通过', p15 and p15['days'] == 15, evidence_view(p15))
    check('普通平台14日不冒充15日', ud._platform_price_pattern(
        platform_bars(14, prior_end=90.0)) is None)
    check('普通平台宽幅拒绝', ud._platform_price_pattern(platform_bars(15, wide=True)) is None)
    check('普通平台下跌趋势拒绝', ud._platform_price_pattern(platform_bars(15, uptrend=False)) is None)
    check('普通平台总体未缩量拒绝', ud._platform_price_pattern(platform_bars(15, shrink=False)) is None)
    p45 = ud._platform_price_pattern(platform_bars(45, long=True), long=True)
    check('长平台45日下边界通过', p45 and p45['days'] == 45, evidence_view(p45))
    check('长平台宽于12%拒绝', ud._platform_price_pattern(
        platform_bars(45, long=True, wide=True), long=True) is None)

    days = [b[0] for b in platform_bars(15)[-15:]]
    pos = ud._apply_platform_eligibility(p15, platform_bars(15), {d: 1.0 for d in days})
    neg = ud._apply_platform_eligibility(p15, platform_bars(15), {d: -1.0 for d in days})
    missing_flows = {d: 1.0 for d in days[:-1]}
    missing = ud._apply_platform_eligibility(p15, platform_bars(15), missing_flows)
    zero = ud._apply_platform_eligibility(p15, platform_bars(15), {d: 0.0 for d in days})
    check('平台区间资金正且100%覆盖通过', pos['displayEligible'] and pos['moneyflowCoveragePct'] == 100, evidence_view(pos))
    check('平台区间资金为负拒绝', not neg['displayEligible'] and neg['moneyflowCoveragePct'] == 100, evidence_view(neg))
    check('平台缺一日资金拒绝', not missing['displayEligible'] and missing['moneyflowCoveragePct'] < 100, evidence_view(missing))
    check('平台累计资金恰好0拒绝', not zero['displayEligible'], evidence_view(zero))

    flat_bars = weekly_bars('flat')
    flat = ud._bottom_weekly_price_pattern(flat_bars)
    check('26~104周长期走平结构可识别', flat and flat['weeklyStructure'] == 'weekly_flat', evidence_view(flat))
    check('周线下跌中继拒绝', ud._bottom_weekly_price_pattern(weekly_bars('down')) is None)
    multi = ud._bottom_weekly_price_pattern(weekly_bars('multi'))
    check('多重底结构可识别', multi and multi['weeklyStructure'] == 'multi_bottom', evidence_view(multi))
    check('距历史高不足10%拒绝', ud._bottom_weekly_price_pattern(weekly_bars('near_high')) is None)
    recent_low = list(flat_bars)
    d, h, _, c, v = recent_low[-1]
    recent_low[-1] = (d, h, 70.0, c, v)
    check('近期仍创新低拒绝', ud._bottom_weekly_price_pattern(recent_low) is None)

    exact = ud._stock_valuation_evidence(valuation_history(boundary=True), AS_OF)
    check('估值分位恰好30%通过', exact['valuationPass'] and exact['valuationScorePct'] == 30.0, exact)
    above_history = valuation_history(boundary=True)
    above_history['20200128']['peTtm'] = 10.0  # 13/40=32.5%，明确验证不放宽30%边界。
    above_history['20200128']['pb'] = 1.0
    above = ud._stock_valuation_evidence(above_history, AS_OF)
    check('估值分位高于30%拒绝', not above['valuationPass'], above)
    insufficient = ud._stock_valuation_evidence(valuation_history(samples=23), AS_OF)
    check('估值历史不足24样本拒绝', not insufficient['valuationPass'] and insufficient['valuationBasis'] == 'insufficient', insufficient)
    single = ud._stock_valuation_evidence(valuation_history(dual=False), AS_OF)
    check('单指标有效可判并明确标注', single['valuationBasis'] == 'single' and single['valuationPass'], single)
    dual = ud._stock_valuation_evidence(valuation_history(dual=True), AS_OF)
    check('双指标有效取均值', dual['valuationBasis'] == 'dual' and dual['valuationPass'], dual)

    bottom_days = [b[0] for b in flat_bars[-flat['days']:]] if flat else []
    bottom_missing_flow = ud._apply_bottom_eligibility(
        flat, flat_bars, {d: 1.0 for d in bottom_days[:-1]}, valuation_history())
    check('底部缺资金不得正式通过', not bottom_missing_flow['displayEligible'], evidence_view(bottom_missing_flow))
    bottom_missing_val = ud._apply_bottom_eligibility(
        flat, flat_bars, {d: 1.0 for d in bottom_days}, {})
    check('底部缺估值不得正式通过', not bottom_missing_val['displayEligible'], evidence_view(bottom_missing_val))

    base = platform_bars(15)
    past = ud._platform_price_pattern(base)
    future = base + [(f'202611{i:02d}', 300.0, 290.0, 295.0, 999.0) for i in range(1, 4)]
    still_past = ud._platform_price_pattern(future[:-3])
    check('平台识别不读取未来数据', past == still_past)
    hist = valuation_history()
    no_future = ud._stock_valuation_evidence(hist, AS_OF)
    with_future_rows = copy.deepcopy(hist)
    with_future_rows['20261231'] = {'peTtm': 0.01, 'pb': 0.01}
    with_future = ud._stock_valuation_evidence(with_future_rows, AS_OF)
    check('估值识别排除识别日后样本', no_future == with_future)
except Exception as exc:
    fatal_errors.append(f'合成边界: {type(exc).__name__}: {exc}')
    check('合成边界执行无异常', False, str(exc))


# ── 九股真实数据：长历史与当前缓存合并，完整调用生产fetch_vcp_stocks。 ──
def merged_cache(codes):
    current = json.loads((ROOT / 'scripts/cache/vcp_cache.json').read_text(encoding='utf-8'))
    long_path = ROOT.parent / 'vcp_cache_1027.json'
    long_cache = json.loads(long_path.read_text(encoding='utf-8'))
    daily = {}
    for code in codes:
        merged = {r[0]: r for r in long_cache['stock_daily'].get(code, [])}
        merged.update({r[0]: r for r in current['stock_daily'].get(code, [])})
        daily[code] = [merged[d] for d in sorted(merged)][-1200:]
    current['stock_daily'] = daily
    current['stock_info'] = dict(current.get('stock_info') or {})
    for code in codes:
        current['stock_info'][code] = {'name': NAMES[code]}
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
    for p in patches:
        p.start()
    extra = extra_patches or []
    for p in extra:
        p.start()
    try:
        ud.fetch_vcp_stocks(NoApi(), AS_OF, data, {})
    finally:
        for p in reversed(extra + patches):
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
        ls = ud._platform_price_pattern(bars, long=True)
        bs = ud._bottom_weekly_price_pattern(bars)
        plat = ud._apply_platform_eligibility(ps, bars, flows)
        lp = ud._apply_platform_eligibility(ls, bars, flows)
        bottom = ud._apply_bottom_eligibility(bs, bars, flows, vals)
        real_cases.append({'code': code, 'name': NAMES[code], 'asOf': rows[-1][0],
                           'dailyBars': len(rows), 'dailyStart': rows[0][0], 'dailyEnd': rows[-1][0],
                           'platform': evidence_view(plat), 'longPlatform': evidence_view(lp),
                           'bottom': evidence_view(bottom)})
    production_snapshot = run_production(ALL_CODES)
    production_snapshot['items'] = [{k: v for k, v in it.items() if k not in ('daily', 'weekly')}
                                    for it in production_snapshot.get('items', [])]
    labels = {}
    for code in ALL_CODES:
        items = [it for it in production_snapshot.get('items', []) if it['code'] == code]
        drops = [d for d in production_snapshot.get('droppedByPatternEvidence', []) if d['code'] == code]
        watch = [w for w in production_snapshot.get('bottomShapeWatch', []) if w['code'] == code]
        labels[code] = {'patterns': [it['pattern'] for it in items], 'drops': drops,
                        'bottomShapeWatch': watch}
        case = next(x for x in real_cases if x['code'] == code)
        case['production'] = labels[code]
        if code in CORE_POSITIVE:
            # 用户原话的价格结构正例与正式资格分开断言；不得用资金/估值反否形态。
            bottom = case.get('bottom') or {}
            case['shapePassed'] = bool(bottom.get('bottomShape') and bottom.get('shapeRecognized')
                                       and bottom.get('weeklyStructure'))
            case['qualificationPassed'] = bool(bottom.get('eligible'))
            expected_eligible = bool(bottom.get('moneyflowPass') and bottom.get('valuationPass'))
            formal_bottom = any(it['pattern'] == '底部整理' for it in items)
            observation_ok = bool(len(watch) == 1 and watch[0]['bottomShape']
                                  and watch[0]['formalAdmission'] == expected_eligible)
            case['releaseCasePassed'] = bool(case['shapePassed'] and observation_ok
                                             and bottom.get('eligible') == expected_eligible
                                             and formal_bottom == expected_eligible)
            check(f'核心正例通用周线价格结构:{NAMES[code]}', case['shapePassed'], bottom)
            check(f'资格硬门独立且观察不计正式入选:{NAMES[code]}', case['releaseCasePassed'], {
                'expectedEligible': expected_eligible, 'actualEligible': bottom.get('eligible'),
                'formalBottom': formal_bottom, 'observation': watch})
        else:
            case['releaseCasePassed'] = not any(it['pattern'] in FORMAL for it in items)
            check(f'反例完整生产不误收:{NAMES[code]}', case['releaseCasePassed'], case['production'])

    hz = next(x for x in real_cases if x['code'] == '600926.SH')
    structure_ok = bool((hz['platform'] or {}).get('displayEligible')
                        or (hz['longPlatform'] or {}).get('displayEligible'))
    high_drop = any('高位门' in reason for d in hz['production']['drops'] for reason in d['reasons'])
    check('杭州银行辅助结构通过但完整一年高位门排除', structure_ok and high_drop
          and not any(p in FORMAL for p in hz['production']['patterns']),
          {'structureOk': structure_ok, 'production': hz['production']})

    # 分类不抢占：杭州银行平台结构即使通过，严格摆动VCP+趋势模板仍优先。
    fake_vcp = {'formed': True, 'distPct': 0.0, 'pivot': 100.0, 'invalidation': 90.0,
                'volConfirm': 100.0, 'count': 3, 'contractions': [8, 6, 4],
                'contractionsOk': [True, True, True], 'decreasing': True}
    fake_tt = {'pass': True, 'evidence': []}
    priority = run_production(['600926.SH'], [
        patch.object(ud, '_vcp_level_strict', side_effect=[dict(fake_vcp), None]),
        patch.object(ud, '_trend_template', return_value=fake_tt)])
    check('VCP分类优先且不被平台证据抢占', any(it['pattern'] == 'VCP收缩型'
          for it in priority.get('items', [])), [it['pattern'] for it in priority.get('items', [])])
except Exception as exc:
    fatal_errors.append(f'真实九股生产链: {type(exc).__name__}: {exc}')
    check('真实九股生产链执行无异常', False, str(exc))


try:
    source = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
    weekly = (ROOT / 'src/sections/WeeklySummary.tsx').read_text(encoding='utf-8')
    eci = (ROOT / 'src/sections/ECIPanel.tsx').read_text(encoding='utf-8')
    evidence_ui = (ROOT / 'src/sections/patternEvidence.ts').read_text(encoding='utf-8')
    check('生产输出证据剔除清单', "'droppedByPatternEvidence': dropped_pattern_evidence[:100]" in source)
    check('总览复制完整形态证据', "'patternEvidence': it.get('patternEvidence')" in source
          and 'patternEvidenceText(r.patternEvidence)' in weekly)
    check('精扫展示完整形态证据与剔除原因', 'patternEvidenceText(it.patternEvidence)' in eci
          and 'droppedByPatternEvidence' in eci)
    for token in ('trendSlopePct', 'ma20Previous', 'ma60', 'volRatio', 'moneyflowCoveragePct',
                  'intervalNetInflow', 'weeks', 'weeklyStructureLabel', 'valuationBasis',
                  'valuationMetrics', 'samples'):
        check(f'前端证据字段:{token}', token in evidence_ui)
    check('前端缺资金或估值不显示正式底部', 'completeBottomEvidence' in evidence_ui
          and 'formalPatternDisplayable' in evidence_ui
          and 'filter(formalPatternDisplayable)' in eci
          and '.filter(formalPatternDisplayable)' in weekly)
    check('生产说明不再宣称旧底部温和放量', '允许量能律动与温和放大' not in source
          and '长平台整理=45~120日+振幅≤21%' not in source)
    check('生产输出独立底部结构观察', "'bottomShapeWatch': bottom_shape_watch[:100]" in source
          and "'bottomShapeWatchCount': len(bottom_shape_watch)" in source)
    check('总览与精扫展示观察资格标签', '底部价格结构观察' in weekly and '底部价格结构观察' in eci
          and 'qualificationLabel' in weekly and 'qualificationLabel' in eci)
except Exception as exc:
    fatal_errors.append(f'前后端契约: {type(exc).__name__}: {exc}')
    check('前后端契约执行无异常', False, str(exc))

sha_after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in DATA_FILES}
check('两份生产fund_data保持不变', sha_before == sha_after, {'before': sha_before, 'after': sha_after})
core_passed = sum(bool(next((x for x in real_cases if x['code'] == code), {}).get('shapePassed'))
                  for code in CORE_POSITIVE)
core_eligible = sum(bool(next((x for x in real_cases if x['code'] == code), {}).get('qualificationPassed'))
                    for code in CORE_POSITIVE)
all_passed = all(c['passed'] for c in checks) and not fatal_errors and core_passed == len(CORE_POSITIVE)
result = {
    'task': 111, 'asOf': AS_OF, 'allPassed': all_passed,
    'releaseEligible': bool(all_passed and core_passed == len(CORE_POSITIVE)),
    'corePositivePassed': core_passed, 'corePositiveTotal': len(CORE_POSITIVE),
    'coreEligiblePassed': core_eligible, 'coreEligibleTotal': len(CORE_POSITIVE),
    'checksPassed': sum(c['passed'] for c in checks), 'checksTotal': len(checks),
    'failed': [c['name'] for c in checks if not c['passed']], 'fatalErrors': fatal_errors,
    'checks': checks, 'realCases': real_cases, 'production': production_snapshot,
    'dataSha256Before': sha_before, 'dataSha256After': sha_after,
    'note': '4只价格结构样本全部通过；资格失败保留观察，不进入正式入选。allPassed只表示结构、资格一致性、反例与边界回归均通过。'
}
out = ROOT / 'zz_regress111_summary.json'
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: result[k] for k in ('allPassed', 'releaseEligible', 'corePositivePassed',
      'corePositiveTotal', 'coreEligiblePassed', 'coreEligibleTotal', 'checksPassed',
      'checksTotal', 'failed', 'fatalErrors')}, ensure_ascii=False, indent=2))
for case in real_cases:
    b = case.get('bottom') or {}
    print(case['name'], case.get('production'), '底部=', b.get('weeklyStructureLabel'),
          '净流入=', b.get('intervalNetInflow'), '估值=', b.get('valuationScorePct'),
          '原因=', b.get('patternReasons'))
raise SystemExit(0 if all_passed else 1)
