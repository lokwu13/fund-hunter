# -*- coding: utf-8 -*-
"""任务101：等待期失效、另锚续检、杯柄展示回退、UI与真实云铝；38/739/609审计。"""
import copy
import hashlib
import importlib.util
import inspect
import json
from collections import Counter
from pathlib import Path

import update_data as ud
import zz_regress96 as r96
import zz_scan99
import zz_scan101

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('update_data_task101_remote_baseline',
                                              ROOT / 'zz_update_data_task101_remote_baseline.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
library = json.loads(r96.SAMPLE_PATH.read_text(encoding='utf-8'))
case_map, cache, real95, rows600795 = r96.load_inputs()
current = json.loads((ROOT / 'zz_audit100_current_rows_full.json').read_text(encoding='utf-8'))
checks = {}


def check(name, condition, evidence=None):
    checks[name] = {'pass': bool(condition), 'evidence': evidence}


def rows_for(sample):
    if sample.get('sourceCase'):
        rows, mv = case_map[sample['sourceCase']]
    elif sample.get('source') == 'current_cache':
        rows, mv = cache.get(sample['code']), 0
    elif sample.get('source') == 'real95':
        rows, mv = real95.get(sample['code']), 0
    else:
        rows, mv = rows600795, 0
    return [r for r in (rows or []) if r[0] <= sample['asOf']], mv


def cup_view(cup):
    if not cup:
        return None
    out = r96.compact_cup(cup)
    for key in ('backgroundMode', 'handleQuality', 'handleFuzzy', 'positionRisk'):
        if key in cup:
            out[key] = cup[key]
    return out


def sample_audit(module, scanner):
    rows_out = []
    for sample in library['samples']:
        rows, mv = rows_for(sample)
        pattern, diag = scanner(module, rows, mv)
        valid = r96.expected_pass(sample, pattern) if len(rows) >= 70 else None
        rows_out.append({'id': sample['id'], 'code': sample['code'], 'name': sample['name'],
                         'sampleClass': sample['sampleClass'], 'asOf': sample['asOf'],
                         'rows': len(rows), 'currentCategory': pattern, 'valid': valid,
                         'regularCup': cup_view(diag.get('regularCup')),
                         'recentCup': cup_view(diag.get('recentCup')),
                         'platform': diag.get('platform'),
                         'mainVcpAttribute': ((diag.get('main') or {}).get('vcpAttribute')),
                         'fallbackUsed': diag.get('fallbackUsed'),
                         'signalDisplayable': diag.get('signalDisplayable'),
                         'rejectReasons': diag.get('rejectReasons') or []})
    stats = {}
    for group in ('杯柄严格样本', '形态有效但可不同标签', '明确反例'):
        subset = [r for r in rows_out if r['sampleClass'] == group]
        stats[group] = {'total': len(subset), 'valid': sum(r['valid'] is True for r in subset),
                        'invalid': sum(r['valid'] is False for r in subset),
                        'unverified': sum(r['valid'] is None for r in subset)}
    return {'stats': stats, 'rows': rows_out,
            'negativeViolations': [r['id'] for r in rows_out
                                   if r['sampleClass'] == '明确反例' and r['valid'] is False]}


# 真实600323：首日及内部破位均不得收回后复活；旧基线用于证明测试有区分度。
rows600323 = current['rows']['600323.SH']
bars600323 = r96.bars_of(rows600323)
old600323 = old._cup_early_breakout(bars600323)
new600323 = ud._cup_early_breakout(bars600323)
check('600323旧基线有信号新门硬剔除', old600323 and old600323['anchorDate'] == '20260827'
      and old600323['signalDate'] == '20261026' and new600323 is None,
      {'old': cup_view(old600323), 'new': new600323})


def controlled_bars(breach_date=None):
    bars = []
    for i in range(200):
        date = f'd{i:03d}'
        high, low, close, volume = 10.0, 9.0, 9.8, 100.0
        if date == 'd000':
            high, low, close = 11.0, 10.8, 11.0
        if date == breach_date:
            high, low, close = 10.0, 8.8, 8.9
        if date in ('d192', 'd196'):
            high, low, close, volume = 10.2, 9.9, 10.0, 150.0
        if date == 'd196':
            close = 10.2
        if date == 'd199':
            high, low, close, volume = 10.2, 9.9, 10.0, 1000.0
        bars.append((date, high, low, close, volume))
    return bars


def controlled_strict(anchor_dates):
    def strict(bars, *args, **kwargs):
        if bars[-1][0] in anchor_dates:
            return {'formed': True, 'displayEligible': True, 'days': 10, 'pivot': 10.0, 'distPct': 0.0,
                    'brkNeedVol': 1000.0, 'rimDate': 'd170'}
        return None
    return strict


for label, date in (('首日', 'd191'), ('内部', 'd195')):
    fixture = controlled_bars(date)
    old_strict, new_strict = old._cup_handle_strict, ud._cup_handle_strict
    try:
        old._cup_handle_strict = controlled_strict({'d190'})
        ud._cup_handle_strict = controlled_strict({'d190'})
        before = old._cup_early_breakout(fixture)
        after = ud._cup_early_breakout(fixture)
    finally:
        old._cup_handle_strict, ud._cup_handle_strict = old_strict, new_strict
    check(f'{label}收盘破位后收回不得复活', before and before['signalDate'] == 'd199' and after is None,
          {'breachDate': date, 'oldSignal': (before or {}).get('signalDate'), 'new': after})

# 失效锚点后必须继续检查其他锚点；完全受控的结构避免真实行情夹具失去区分度。
real_strict = ud._cup_handle_strict
try:
    ud._cup_handle_strict = controlled_strict({'d190', 'd195'})
    later = ud._cup_early_breakout(controlled_bars('d191'))
finally:
    ud._cup_handle_strict = real_strict
check('失效锚点后另锚续检', later and later['anchorDate'] == 'd195'
      and later['signalDate'] == 'd199', cup_view(later))

# C10首次信号与N12时效。
before_report = sample_audit(old, zz_scan99.scan)
after_report = sample_audit(ud, zz_scan101.scan)
before_by_id = {r['id']: r for r in before_report['rows']}
after_by_id = {r['id']: r for r in after_report['rows']}
sample_changes = [{'id': r['id'], 'before': before_by_id[r['id']]['currentCategory'],
                   'after': r['currentCategory'], 'beforeValid': before_by_id[r['id']]['valid'],
                   'afterValid': r['valid'], 'fallbackUsed': r['fallbackUsed']}
                  for r in after_report['rows']
                  if before_by_id[r['id']]['currentCategory'] != r['currentCategory']
                  or before_by_id[r['id']]['valid'] != r['valid']]
regressed = [r['id'] for r in after_report['rows']
             if before_by_id[r['id']]['valid'] is True and r['valid'] is not True]
check('38样本无既有有效样本回退', not regressed, regressed)
check('38样本明确反例违规集合不变', after_report['negativeViolations'] == before_report['negativeViolations'],
      {'before': before_report['negativeViolations'], 'after': after_report['negativeViolations']})
c10 = after_by_id['C10']['recentCup']
n12 = after_by_id['N12']['recentCup']
check('C10首次信号不变', c10 and c10['signalDate'] == '20260902' and c10['breakoutAge'] == 0
      and after_by_id['C10']['signalDisplayable'] and after_by_id['C10']['currentCategory'] == '杯柄型', c10)
check('N12旧信号仍不可展示且不得保留杯柄', n12 and n12['signalDate'] == '20260902'
      and n12['breakoutAge'] == 32 and not after_by_id['N12']['signalDisplayable']
      and after_by_id['N12']['currentCategory'] != '杯柄型',
      {'cup': n12, 'category': after_by_id['N12']['currentCategory'],
       'fallback': after_by_id['N12']['fallbackUsed']})

# 云铝真实案例：旧杯柄年龄/当前失效后回退底部整理，属性完整保留。
# 后续任务已更新共享扫描器，旧基线自身也可直接落底部；核心契约是当前回退及属性不丢失，
# 不再把“旧基线必须为None”误当业务门。
cloud_rows = current['rows']['000807.SZ']
cloud_before, cloud_diag_before = zz_scan99.scan(old, cloud_rows, current['mv']['000807.SZ'] / 1e4)
cloud_after, cloud_diag = zz_scan101.scan(ud, cloud_rows, current['mv']['000807.SZ'] / 1e4)
cloud_attr = (cloud_diag.get('main') or {}).get('vcpAttribute') or {}
check('云铝真实旧杯柄回退平台属性', cloud_after == '底部整理'
      and cloud_diag.get('fallbackUsed') and cloud_attr.get('formed')
      and cloud_attr.get('style') == 'platform_vcp'
      and not cloud_diag.get('signalDisplayable'),
      {'before': cloud_before, 'after': cloud_after, 'attribute': cloud_attr,
       'recent': cup_view(cloud_diag.get('recentCup')), 'reasons': cloud_diag['rejectReasons']})
check('云铝属性单日门与量能门未放宽', cloud_attr['narrowIntegrity']['pass']
      and cloud_attr['platformToRallyVol'] <= ud.PLATFORM_VCP_STAGE_VOL_MAX
      and cloud_attr['volumeMA']['pass'], cloud_attr)

# 普通非突破杯柄距离失败也回退；构造只替换杯柄返回值，平台仍由真实云铝行情计算。
original_recent = ud._cup_early_breakout
original_strict = ud._cup_handle_strict
try:
    ud._cup_early_breakout = lambda bars: None
    ud._cup_handle_strict = lambda *args, **kwargs: {
        'type': '杯柄型', 'formed': True, 'breakout': False, 'days': 12, 'totalDays': 50,
        'pivot': 26.80, 'distPct': 9.4, 'invalidation': 24.0, 'volConfirm': 1,
        'defects': [], 'structureFuzzy': False}
    ordinary_after, ordinary_diag = zz_scan101.scan(ud, cloud_rows, current['mv']['000807.SZ'] / 1e4)
finally:
    ud._cup_early_breakout = original_recent
    ud._cup_handle_strict = original_strict
check('普通杯柄距离展示失败回退', ordinary_after == '底部整理' and ordinary_diag.get('fallbackUsed')
      and ((ordinary_diag.get('main') or {}).get('vcpAttribute') or {}).get('formed'),
      {'pattern': ordinary_after, 'fallback': ordinary_diag.get('fallbackUsed')})

# 任务103仅有意修改VCP三函数；趋势模板和价格务实收缩辅助函数保持逐字一致。
for function_name in ('_trend_template', '_platform_contraction_practical_ok'):
    check(f'禁止范围函数未改:{function_name}',
          inspect.getsource(getattr(old, function_name)) == inspect.getsource(getattr(ud, function_name)),
          'source identical')

# 739历史固定池 before/after，全量保存差异供人工审计。
pool_rows = []
for code in sorted(cache):
    rows = cache[code]
    before, _ = zz_scan99.scan(old, rows, 0)
    after, diag = zz_scan101.scan(ud, rows, 0)
    pool_rows.append({'code': code, 'before': before, 'after': after,
                      'fallbackUsed': diag.get('fallbackUsed'),
                      'attributeFormed': bool(((diag.get('main') or {}).get('vcpAttribute') or {}).get('formed')),
                      'recent': cup_view(diag.get('recentCup'))})
pool_changes = [r for r in pool_rows if r['before'] != r['after']]
check('固定池数量739', len(pool_rows) == 739, len(pool_rows))

# 当前609真实池 before/after；输出所有标签变化，不只线上展示截断后的名单。
current_rows = []
for code in sorted(current['rows']):
    rows = current['rows'][code]
    mv = current['mv'].get(code, 0) / 1e4
    before, _ = zz_scan99.scan(old, rows, mv)
    after, diag = zz_scan101.scan(ud, rows, mv)
    current_rows.append({'code': code, 'name': current['stockInfo'].get(code, {}).get('name', code),
                         'before': before, 'after': after, 'fallbackUsed': diag.get('fallbackUsed'),
                         'attributeFormed': bool(((diag.get('main') or {}).get('vcpAttribute') or {}).get('formed')),
                         'vcpPath': ((diag.get('main') or {}).get('structurePath') if after == 'VCP收缩型' else None),
                         'recent': cup_view(diag.get('recentCup'))})
current_changes = [r for r in current_rows if r['before'] != r['after']]
current_cups = [{'code': r['code'], 'name': r['name']} for r in current_rows if r['after'] == '杯柄型']
current_vcps = [{'code': r['code'], 'name': r['name'], 'path': r['vcpPath']}
                for r in current_rows if r['after'] == 'VCP收缩型']
current_attrs = [{'code': r['code'], 'name': r['name'], 'pattern': r['after']}
                 for r in current_rows if r['attributeFormed']]
check('当前600323与601963剔除', next(r for r in current_rows if r['code'] == '600323.SH')['after'] is None
      and next(r for r in current_rows if r['code'] == '601963.SH')['after'] is None,
      [r for r in current_changes if r['code'] in ('600323.SH', '601963.SH')])
check('当前云铝恢复底部整理属性', next(r for r in current_rows if r['code'] == '000807.SZ')['after'] == '底部整理'
      and next(r for r in current_rows if r['code'] == '000807.SZ')['attributeFormed'],
      next(r for r in current_rows if r['code'] == '000807.SZ'))
check('任务103当前固定区间VCP均有结构路径', {r['code'] for r in current_vcps} == {
      '000100.SZ', '600015.SH', '600019.SH', '600031.SH', '600066.SH'}
      and all(r['path'] == 'fixed_base' for r in current_vcps),
      {'vcps': current_vcps, 'counts': dict(Counter(r['after'] for r in current_rows))})
check('当前杯柄与属性名单目标', {r['code'] for r in current_cups} == {'600938.SH', '600803.SH', '601018.SH'}
      and {r['code'] for r in current_attrs} == {'000807.SZ'},
      {'cups': current_cups, 'attributes': current_attrs})

# UI静态契约；实际bundle在nightly后另行核验。
types = (ROOT / 'src/hooks/useFundData.ts').read_text(encoding='utf-8')
panel = (ROOT / 'src/sections/ECIPanel.tsx').read_text(encoding='utf-8')
check('UI可选类型与徽章tooltip', all(x in types for x in ('vcpAttribute?:', 'patternNote?: string | null'))
      and '平台型VCP属性（非正式VCP）' in panel
      and 'it.vcpAttribute?.formed' in panel and 'it.patternNote || it.vcpAttribute.note' in panel,
      'optional fields + formed badge + note tooltip')

out = {'task': 101, 'pitOnly': True, 'notMarketWinRate': True,
       'baselineProductionSha256': hashlib.sha256((ROOT / 'zz_update_data_task101_remote_baseline.py').read_bytes()).hexdigest(),
       'productionSha256': hashlib.sha256((ROOT / 'scripts/update_data.py').read_bytes()).hexdigest(),
       'sampleExpectationsChanged': False, 'boundaryChecks': checks,
       'sampleStatsBefore': before_report['stats'], 'sampleStatsAfter': after_report['stats'],
       'sampleChanges': sample_changes, 'sampleRowsAfter': after_report['rows'],
       'fixedPool': {'poolSize': len(pool_rows), 'asOf': max(rows[-1][0] for rows in cache.values()),
                     'beforeCounts': dict(Counter(r['before'] for r in pool_rows)),
                     'afterCounts': dict(Counter(r['after'] for r in pool_rows)),
                     'changedCount': len(pool_changes), 'changes': pool_changes},
       'currentPool': {'poolSize': len(current_rows), 'asOf': current['asOf'],
                       'beforeCounts': dict(Counter(r['before'] for r in current_rows)),
                       'afterCounts': dict(Counter(r['after'] for r in current_rows)),
                       'changedCount': len(current_changes), 'changes': current_changes,
                       'cups': current_cups, 'platformVcpAttributes': current_attrs}}
path = ROOT / 'zz_regress101.json'
path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {'output': path.name, 'checksPassed': sum(x['pass'] for x in checks.values()),
           'checksTotal': len(checks), 'failed': [k for k, v in checks.items() if not v['pass']],
           'sampleChanges': sample_changes, 'fixedPoolChanges': pool_changes,
           'currentPoolChanges': current_changes, 'currentCups': current_cups,
           'currentAttributes': current_attrs}
(ROOT / 'zz_regress101_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if summary['failed']:
    raise AssertionError(f"任务101检查失败: {summary['failed']}")
