# -*- coding: utf-8 -*-
"""概念真实样本修复发布前机器核验。"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
preflight = json.loads((ROOT / 'zz_concept_sample_live_preflight.json').read_text(encoding='utf-8'))
coverage = json.loads((ROOT / 'zz_concept_sample_real_coverage.json').read_text(encoding='utf-8'))
regress = json.loads((ROOT / 'zz_concept_sample_regress.json').read_text(encoding='utf-8'))
backend = (ROOT / 'scripts/update_data.py').read_text(encoding='utf-8')
vcp = (ROOT / 'scripts/vcp_preview.py').read_text(encoding='utf-8')
ui = (ROOT / 'src/sections/SectorHeatmap.tsx').read_text(encoding='utf-8')
types = (ROOT / 'src/hooks/useFundData.ts').read_text(encoding='utf-8')
checks = {}

def check(name, condition):
    checks[name] = bool(condition)
    if not condition:
        raise AssertionError(name)

check('专项13项全部通过', regress['passed'] == regress['total'] == 13)
check('真实缓存连续10日每日至少20', coverage['coverage']['heatReady'] is True
      and len(coverage['coverage']['last10']) == 10
      and all(coverage['coverage']['dailySamples'][d] >= 20 for d in coverage['coverage']['last10']))
check('真实展示概念成交与热榜非空', len(coverage['conceptItems']) == 5
      and all(x['amountPct'] is not None and x['hits10'] is not None and x['streak'] is not None
              and x['heatReady'] for x in coverage['conceptItems']))
check('20样本门未降低', 'CONCEPT_HEAT_MIN_SAMPLES = 2 * ROTATION_TOPN' in backend)
check('旧混写缓存不再参与拥挤度', "cache.get('index_daily')" not in backend[backend.index('def build_sector_crowding'):backend.index('# ── 第三步入选历史')])
check('独立四字段真实缓存与公开源', "CONCEPT_HEAT_SCHEMA = ['date', 'close', 'volume', 'amount']" in vcp
      and 'd.10jqka.com.cn/v4/line' in vcp and 'concept_heat_daily' in backend)
check('成交额不从成交量兜底', 'amount = float(fields[6])' in vcp and 'volume = float(fields[5])' in vcp
      and 'amount = volume' not in vcp)
check('前端真实值和样本不足双门控', 'item.amountSource' in ui and "'样本不足'" in ui
      and '`${item.hits10}次 · 连${item.streak}天`' in ui and 'conceptCoverage?:' in types)
production = {}
for path, base in preflight['fundData'].items():
    raw = (ROOT / path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    production[path] = {'bytes': len(raw), 'sha256': sha}
    check(path + '本地生产SHA未改', sha == base['localSha256'])
    check(path + '未误写远端生产数据', sha != base['remoteSha256'])
bundles = sorted((ROOT / 'dist/assets').glob('index-*.js'))
check('生产bundle存在', len(bundles) == 1)
bundle = bundles[0].read_text(encoding='utf-8')
check('bundle包含成交来源和可空热榜逻辑', 'amountSource' in bundle and '样本不足' in bundle and '真实成交额' in bundle)
forbidden = ['public/fund_data.json', 'src/data/fund_data.json', 'scripts/cache/vcp_cache.json',
             'zz_concept_sample_real_cache.json', 'zz_concept_sample_remote_vcp_cache.json',
             'zz_concept_sample_issue.png', 'dist', '.github']
report = {
    'task': 'concept-sample', 'allPassed': all(checks.values()), 'checksPassed': sum(checks.values()),
    'checksTotal': len(checks), 'checks': checks, 'headBaseline': preflight['head'],
    'production': production, 'bundle': bundles[0].name,
    'realDailySamples': coverage['coverage']['dailySamples'],
    'publishWhitelist': ['scripts/update_data.py', 'scripts/vcp_preview.py',
                         'src/hooks/useFundData.ts', 'src/sections/SectorHeatmap.tsx'],
    'forbiddenPublishPaths': forbidden, 'manualDispatch': False, 'workflowModified': False,
    'scheduleModified': False, 'productionDataRegenerated': False,
}
(ROOT / 'zz_concept_sample_machine_verification.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
