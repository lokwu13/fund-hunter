# -*- coding: utf-8 -*-
"""任务103十例人工标签：VCP/平台规则优化不可弱化回归；只做PIT形态识别，不做收益回测。"""
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))

import update_data as ud
import zz_scan101

DATA_PATH = ROOT / 'zz_audit100_current_rows_full.json'
DATA_SHA256 = 'f77eb8dcfcd11c0d582ea44eec9b25b67b859fd9c1de383c4dde6cbb4fa25d45'
DATA = json.loads(DATA_PATH.read_text(encoding='utf-8'))
assert hashlib.sha256(DATA_PATH.read_bytes()).hexdigest() == DATA_SHA256

# 用户人工标签原文的结构化映射；不得按后续收益、突破成败或股票/日期特判修改。
CASES = [
    {'code': '002371.SZ', 'name': '北方华创', 'asOf': '20250520', 'label': 'VCP负例'},
    {'code': '000776.SZ', 'name': '广发证券', 'asOf': '20250403', 'label': 'VCP正例'},
    {'code': '600118.SH', 'name': '中国卫星', 'asOf': '20250402', 'label': '底部平台/整理，非VCP'},
    {'code': '002027.SZ', 'name': '分众传媒', 'asOf': '20250402', 'label': '负例'},
    {'code': '600030.SH', 'name': '中信证券', 'asOf': '20250328', 'label': '负例'},
    {'code': '600919.SH', 'name': '江苏银行', 'asOf': '20250228', 'label': '负例'},
    {'code': '000651.SZ', 'name': '格力电器', 'asOf': '20240902', 'label': '负例'},
    {'code': '603392.SH', 'name': '万泰生物', 'asOf': '20240715', 'label': 'VCP正例；不看后续趋势'},
    {'code': '002252.SZ', 'name': '上海莱士', 'asOf': '20231016', 'label': '负例'},
    {'code': '601328.SH', 'name': '交通银行', 'asOf': '20230904', 'label': '当时负例'},
]
WINDOWS = [
    {'code': '000776.SZ', 'name': '广发证券', 'start': '20250403', 'end': '20250403', 'kind': 'vcp'},
    {'code': '603392.SH', 'name': '万泰生物', 'start': '20240715', 'end': '20240715', 'kind': 'vcp'},
    {'code': '002027.SZ', 'name': '分众传媒', 'start': '20250707', 'end': '20250801', 'kind': 'vcp'},
    {'code': '600030.SH', 'name': '中信证券', 'start': '20240722', 'end': '20240923', 'kind': 'vcp'},
    {'code': '601328.SH', 'name': '交通银行', 'start': '20230905', 'end': '20231229', 'kind': 'vcp'},
    {'code': '600118.SH', 'name': '中国卫星', 'start': '20250402', 'end': '20250822', 'kind': 'platform'},
]
VCP = 'VCP收缩型'
PLATFORMS = {'底部整理', '平台整理', '底部平台型', '长平台整理'}
checks = {}


def check(name, condition, evidence=None):
    checks[name] = {'pass': bool(condition), 'evidence': evidence}


def candidate_view(main):
    if not main:
        return None
    keys = ('formed', 'structurePath', 'priceMode', 'days', 'amplitude', 'segAmps',
            'contractions', 'distPct', 'pivot', 'volFirst', 'volLast', 'volRatio',
            'rightSideQuality', 'recentVolumeQuality', 'volumeMA', 'rejectReasons', 'reasons')
    return {k: main[k] for k in keys if k in main}


def scan_asof(code, date):
    # 唯一历史入口：先截断再扫描，绝不把完整历史传给形态函数。
    rows = [r for r in DATA['rows'][code] if r[0] <= date]
    assert rows and rows[-1][0] == date, (code, date, rows[-1][0] if rows else None)
    pattern, diag = zz_scan101.scan(ud, rows, 0)
    return {
        'code': code, 'asOf': date, 'rowsUsed': len(rows), 'lastInputDate': rows[-1][0],
        'pattern': pattern, 'formed': pattern == VCP,
        'type': pattern, 'reasons': diag.get('rejectReasons') or [],
        'daily': candidate_view(diag.get('vcpDaily')),
        'weekly': candidate_view(diag.get('vcpWeekly')),
        'fixedBase': candidate_view(diag.get('fixedBase')),
        'main': candidate_view(diag.get('main')),
        'platform': candidate_view(diag.get('platform')),
        'trendPass': (diag.get('trendTemplate') or {}).get('pass'),
        'pitProof': {'requestedAsOf': date, 'lastInputDate': rows[-1][0],
                     'futureRowsExcluded': sum(r[0] > date for r in DATA['rows'][code])},
    }


case_rows = []
for case in CASES:
    result = scan_asof(case['code'], case['asOf'])
    result.update({'name': case['name'], 'humanLabel': case['label']})
    if case['code'] in ('000776.SZ', '603392.SH'):
        result['pass'] = result['pattern'] == VCP
    elif case['code'] == '600118.SH':
        result['pass'] = result['pattern'] in PLATFORMS and result['pattern'] != VCP
    else:
        result['pass'] = result['pattern'] != VCP
    case_rows.append(result)
    check(f"指定日人工标签:{case['name']}:{case['asOf']}", result['pass'],
          {'label': case['label'], 'pattern': result['pattern'], 'reasons': result['reasons']})
    check(f"指定日仅用当时数据:{case['name']}:{case['asOf']}",
          result['lastInputDate'] == case['asOf'] and result['rowsUsed'] > 0,
          result['pitProof'])

window_rows = []
for spec in WINDOWS:
    records = []
    for row in DATA['rows'][spec['code']]:
        date = row[0]
        if spec['start'] <= date <= spec['end']:
            records.append(scan_asof(spec['code'], date))
    positives = [r for r in records if r['pattern'] == VCP]
    platforms = [r for r in records if r['pattern'] in PLATFORMS]
    if spec['kind'] == 'vcp':
        passed = bool(positives) and all(r['lastInputDate'] == r['asOf'] for r in positives)
        first = positives[0] if positives else None
        # 最佳日仅按当时结构证据：紧致度优先，其次量缩和枢轴距离；绝不使用后续收益。
        def score(r):
            main = r.get('main') or {}
            amp = main.get('amplitude')
            contractions = main.get('contractions') or []
            tightness = amp if amp is not None else (sum(contractions) / len(contractions) if contractions else 999)
            vol_ratio = main.get('volRatio')
            if vol_ratio is None and main.get('volFirst') and main.get('volLast') is not None:
                vol_ratio = main['volLast'] / main['volFirst']
            return (tightness, vol_ratio if vol_ratio is not None else 999, abs(main.get('distPct', 999)), r['asOf'])
        best = min(positives, key=score) if positives else None
        evidence = {'positiveCount': len(positives), 'first': first, 'best': best}
    else:
        passed = bool(platforms) and not positives and records[0]['pattern'] in PLATFORMS
        first = platforms[0] if platforms else None
        best = None
        evidence = {'platformCount': len(platforms), 'vcpViolationCount': len(positives),
                    'first': first, 'firstDatePattern': records[0]['pattern'] if records else None}
    result = {**spec, 'pass': passed, 'scannedDays': len(records), **evidence, 'records': records}
    window_rows.append(result)
    check(f"人工窗口:{spec['name']}:{spec['start']}~{spec['end']}", passed,
          {k: v for k, v in evidence.items() if k not in ('first', 'best')} |
          {'firstDate': (first or {}).get('asOf'), 'bestDate': (best or {}).get('asOf')})

# 广发必须保留总体段量缩与近期量质量，不再依赖MA10≤MA20≤MA50；万泰用突破前基底量证据。
gf = next(r for r in case_rows if r['code'] == '000776.SZ')
gf_main = gf.get('main') or {}
check('广发正例为严格摆动证据且不靠机械均量排列',
      gf_main.get('priceMode') == 'strict' and gf_main.get('volFirst', 0) > gf_main.get('volLast', 999)
      and not ((gf_main.get('volumeMA') or {}).get('sequenceOk', True)), gf_main)
wt = next(r for r in case_rows if r['code'] == '603392.SH')
wt_main = wt.get('main') or {}
check('万泰突破日不抹掉既有基底结构', wt_main.get('distPct', 99) < 0
      and ((wt_main.get('recentVolumeQuality') or {}).get('basisExcludesBreakout') is True), wt_main)

# 通用边界：不依赖任何股票或日期分支。
volume_bars = [(f'v{i:02d}', 11.0, 9.0, 10.0, float(v))
               for i, v in enumerate([50] * 10 + [100] * 40 + [120] * 10)]
volume_evidence = ud._vcp_volume_ma_evidence(volume_bars, 60)
check('均量排列不机械下行但非异常放量可通过', volume_evidence['pass']
      and not volume_evidence['sequenceOk'] and volume_evidence['ma10ToBase'] <= 1.20, volume_evidence)

def controlled_price_bars(closes):
    return [(f'p{i:02d}', c * 1.001, c * 0.999, c, 100.0) for i, c in enumerate(closes)]

slide = ud._vcp_right_side_quality(controlled_price_bars([100 - i * 10 / 29 for i in range(30)]))
violent = ud._vcp_right_side_quality(controlled_price_bars(
    [100.0] * 19 + [100, 106, 100, 106, 100, 106, 100, 106, 100, 106, 100]))
check('右侧持续下滑通用边界拒绝', not slide['pass'] and slide['persistentDownslide'], slide)
check('右侧剧烈起伏通用边界拒绝', not violent['pass'] and violent['violent'], violent)
bf = next(r for r in case_rows if r['code'] == '002371.SZ')
check('务实摆动序列不独立成型', (bf.get('daily') or {}).get('priceMode') == 'practical'
      and not (bf.get('daily') or {}).get('formed'), bf.get('daily'))
fz_positive = next(r for r in window_rows if r['code'] == '002027.SZ')['first']
check('固定区间中继允许接近一年新高', fz_positive['pattern'] == VCP
      and (fz_positive.get('main') or {}).get('structurePath') == 'fixed_base'
      and fz_positive['trendPass'] is False, fz_positive.get('main'))
platform_bars = [(f'b{i:02d}', 10.05, 9.95, 10.0, 100.0 if i < 40 else 110.0) for i in range(90)]
rhythmic = ud._bottom_platform_rhythmic(platform_bars, dist_gate=(-5, 12))
check('底部平台允许量能律动及温和放大', rhythmic and rhythmic['formed']
      and rhythmic['volumePolicy'] == 'rhythmic_mild_expansion' and rhythmic['volRatio'] == 1.1, rhythmic)

# 固定区间允许近一年新高；务实摆动不能独立formed；量能律动平台可温和放大。
source_path = ROOT / 'scripts' / 'update_data.py'
source = source_path.read_text(encoding='utf-8')
tree = ast.parse(source)
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name in ('_vcp_level_strict', '_vcp_fixed_base', '_vcp_right_side_quality'):
        segment = ast.get_source_segment(source, node) or ''
        check(f'形态函数无代码日期特判:{node.name}',
              not re.search(r'002371|000776|600118|002027|600030|600919|000651|603392|002252|601328|20250520|20250403|20230904', segment),
              'no security/date literals')
check('十例规则不读取后续收益', all(term not in source for term in ('futureReturn', 'forwardReturn', 'postBreakoutWinRate')), 'no forward-return selector')

# 杯柄两个核心函数不得被本次VCP/平台修改触碰。
import importlib.util
import inspect
baseline_path = ROOT / 'zz_update_data_task104_remote_baseline.py'
spec = importlib.util.spec_from_file_location('update_data_task105_baseline', baseline_path)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
# 任务110只允许在几何formed之后追加统一资格过滤；核心几何与信号定义仍逐字保持。
for name, helpers in (
        ('_cup_handle_strict', ('_cup_weekly_trend', '_cup_right_side_gate', '_cup_shape_gate',
                               '_cup_handle_quality', '_cup_body_background', '_cup_structure_segments')),
        ('_cup_early_breakout', ('_cup_signal_kind', '_cup_signal_displayable', '_cup_body_evidence'))):
    check(f'杯柄核心几何未改:{name}',
          all(inspect.getsource(getattr(old, helper)) == inspect.getsource(getattr(ud, helper))
              for helper in helpers), {'helpers': list(helpers), 'task110': 'eligible/display post-filter only'})

failed_cases = [r['code'] for r in case_rows if not r['pass']]
failed_windows = [r['code'] for r in window_rows if not r['pass']]
summary = {
    'task': 103, 'dataSha256': DATA_SHA256, 'pitOnly': True, 'notMarketWinRate': True,
    'checksPassed': sum(x['pass'] for x in checks.values()), 'checksTotal': len(checks),
    'failed': [k for k, v in checks.items() if not v['pass']],
    'casePassed': sum(r['pass'] for r in case_rows), 'caseTotal': len(case_rows),
    'failedCases': failed_cases, 'failedWindows': failed_windows,
    'casePatterns': {r['code']: r['pattern'] for r in case_rows},
    'windowFirstBest': {r['code']: {'first': (r.get('first') or {}).get('asOf'),
                                    'best': (r.get('best') or {}).get('asOf'),
                                    'pass': r['pass']} for r in window_rows},
}
report = {'summary': summary, 'humanLabelsImmutable': True, 'cases': case_rows,
          'windows': window_rows, 'checks': checks,
          'productionSha256': hashlib.sha256(source_path.read_bytes()).hexdigest()}
(ROOT / '任务103-十案例回归报告.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(ROOT / 'zz_regress105_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if summary['failed']:
    raise AssertionError(f"任务103十例回归失败: {summary['failed']}")
