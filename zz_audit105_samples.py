# -*- coding: utf-8 -*-
"""任务103规则优化的38个既有标准样本与当前609池PIT回退审计。"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import update_data as ud
import zz_regress96 as r96
import zz_scan101

library = json.loads(r96.SAMPLE_PATH.read_text(encoding='utf-8'))
case_map, cache, real95, rows600795 = r96.load_inputs()
baseline = json.loads((ROOT / 'zz_regress101.json').read_text(encoding='utf-8'))
baseline_samples = {x['id']: x for x in baseline['sampleRowsAfter']}
rows_out = []
for sample in library['samples']:
    if sample.get('sourceCase'):
        rows, mv = case_map[sample['sourceCase']]
    elif sample.get('source') == 'current_cache':
        rows, mv = cache.get(sample['code']), 0
    elif sample.get('source') == 'real95':
        rows, mv = real95.get(sample['code']), 0
    else:
        rows, mv = rows600795, 0
    rows = [r for r in (rows or []) if r[0] <= sample['asOf']]
    pattern, diag = zz_scan101.scan(ud, rows, mv)
    valid = r96.expected_pass(sample, pattern) if len(rows) >= 70 else None
    before = baseline_samples[sample['id']]
    rows_out.append({'id': sample['id'], 'code': sample['code'], 'name': sample['name'],
                     'sampleClass': sample['sampleClass'], 'asOf': sample['asOf'],
                     'before': before['currentCategory'], 'after': pattern,
                     'beforeValid': before['valid'], 'afterValid': valid,
                     'fixedBase': diag.get('fixedBase'),
                     'platform': diag.get('platform'),
                     'main': diag.get('main') if pattern == 'VCP收缩型' else None,
                     'rejectReasons': diag.get('rejectReasons') or []})
    print('SAMPLE', sample['id'], before['currentCategory'], '=>', pattern,
          'valid', before['valid'], '=>', valid, flush=True)

current = json.loads((ROOT / 'zz_audit100_current_rows_full.json').read_text(encoding='utf-8'))
baseline_current = {x['code']: x for x in baseline['currentPool']['changes']}
# 完整before标签从固定基线统计文件不可逐项还原时，以任务101生产忠实旧模块重算仅发生变化的股票。
current_rows = []
for code in sorted(current['rows']):
    rows = current['rows'][code]
    pattern, diag = zz_scan101.scan(ud, rows, current['mv'].get(code, 0) / 1e4)
    current_rows.append({'code': code, 'name': current['stockInfo'].get(code, {}).get('name', code),
                         'after': pattern, 'fixedBase': diag.get('fixedBase'),
                         'platform': diag.get('platform'),
                         'main': diag.get('main') if pattern == 'VCP收缩型' else None})
    if pattern:
        print('CURRENT', code, current_rows[-1]['name'], pattern, flush=True)

regressed = [x['id'] for x in rows_out if x['beforeValid'] is True and x['afterValid'] is not True]
negative_violations = [x['id'] for x in rows_out
                       if x['sampleClass'] == '明确反例' and x['afterValid'] is False]
summary = {'sampleCount': len(rows_out), 'sampleRegressions': regressed,
           'negativeViolations': negative_violations,
           'sampleChanged': [{'id': x['id'], 'before': x['before'], 'after': x['after'],
                              'beforeValid': x['beforeValid'], 'afterValid': x['afterValid']}
                             for x in rows_out if x['before'] != x['after'] or x['beforeValid'] != x['afterValid']],
           'currentPoolSize': len(current_rows),
           'currentCounts': dict(Counter(x['after'] for x in current_rows)),
           'currentVcp': [{'code': x['code'], 'name': x['name'],
                           'path': (x['main'] or {}).get('structurePath')} for x in current_rows
                          if x['after'] == 'VCP收缩型']}
out = {'task': 103, 'pitOnly': True, 'notMarketWinRate': True,
       'productionSha256': hashlib.sha256((ROOT / 'scripts/update_data.py').read_bytes()).hexdigest(),
       'summary': summary, 'samples': rows_out, 'currentPool': current_rows}
(ROOT / 'zz_audit105_samples.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
