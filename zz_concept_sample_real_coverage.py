# -*- coding: utf-8 -*-
"""概念拥挤度真实THS缓存副本覆盖复算；不写生产JSON与原缓存。"""
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

vcp = load('vcp_concept_sample_real', ROOT / 'scripts' / 'vcp_preview.py')
u = load('update_concept_sample_real', ROOT / 'scripts' / 'update_data.py')
source_path = ROOT / 'zz_concept_sample_remote_vcp_cache.json'
source_raw = source_path.read_bytes()
source = json.loads(source_raw.decode('utf-8'))
cache = {k: copy.deepcopy(source.get(k)) for k in ('ths_index', 'concepts')}
effective = '20261120'
vcp.ensure_concept_heat_daily(cache, effective)
(ROOT / 'zz_concept_sample_real_cache.json').write_text(
    json.dumps(cache, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')

u._load_sector_history = lambda: {}
u._load_json_cache = lambda *_args: copy.deepcopy(cache)
data = {'sectorFlows': {'trade_date': '2026-11-20'}, 'sectorRotation': {'trade_date': '2026-11-20', 'stats': []}}
u.build_sector_crowding(data)
module = data.get('sectorCrowding') or {}
coverage = module.get('conceptCoverage') or {}
assert coverage.get('heatReady') is True, coverage
assert coverage.get('dailySamples', {}).get(effective, 0) >= 20, coverage
assert len(coverage.get('last10') or []) == 10
assert all(v >= 20 for k, v in coverage.get('dailySamples', {}).items() if k in coverage['last10'])
concepts = [x for x in module.get('items') or [] if x['type'] == '概念']
assert concepts and all(x['heatReady'] and x['hits10'] is not None and x['streak'] is not None for x in concepts)
assert any(x['amountPct'] is not None for x in concepts)
assert all(x.get('amountSource') == '同花顺公开指数日线.amount（元）' for x in concepts)
assert all(r[0] <= effective for rows in cache['concept_heat_daily'].values() for r in rows)
assert all(len(r) == 4 for rows in cache['concept_heat_daily'].values() for r in rows)
summary = {
    'sourceCacheSha256': hashlib.sha256(source_raw).hexdigest(),
    'sourceProductionUntouched': True,
    'effective': effective,
    'source': cache['concept_heat_source'],
    'universeCount': len(cache['concept_heat_universe']),
    'displayMap': cache['concept_heat_display_map'],
    'series': [
        {'code': code, 'days': len(rows), 'first': rows[0][0] if rows else None,
         'last': rows[-1][0] if rows else None,
         'amountPositiveDays': sum(1 for r in rows if isinstance(r[3], (int, float)) and r[3] > 0),
         'latestAmount': rows[-1][3] if rows else None}
        for code, rows in sorted(cache['concept_heat_daily'].items())
    ],
    'coverage': coverage,
    'conceptItems': concepts,
    'note': module.get('note'),
}
(ROOT / 'zz_concept_sample_real_coverage.json').write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'universeCount': summary['universeCount'], 'dailySamples': coverage['dailySamples'],
                  'conceptItems': concepts, 'shortHistory': coverage['shortHistory'],
                  'staleUniverse': coverage['staleUniverse']}, ensure_ascii=False, indent=2))
