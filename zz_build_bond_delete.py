# -*- coding: utf-8 -*-
"""债券栏目删减生产构建；只构建，不启动开发服务器、不生成生产数据。"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime

ROOT = Path(__file__).resolve().parent
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
RETAINED = ['债市信号 → A+H股市一个月影响推演', '央行短期流动性工具', '滚动波动率（20日标准差）',
            '今日债市要闻 · 东方财富', '近期债市动态', 'bond-margin', '中美利差(45%)']
REMOVED = ['债券市场要闻', '中美国债收益率对比', '美元资产吸引力更高', '人民币资产吸引力更高']


def data_state():
    return {name: {'path': name, 'bytes': (ROOT / name).stat().st_size,
                   'sha256': hashlib.sha256((ROOT / name).read_bytes()).hexdigest()} for name in DATA}


before = data_state()
started = time.monotonic()
completed = subprocess.run('npm run build', cwd=ROOT, shell=True, text=True,
                           encoding='utf-8', errors='replace', capture_output=True, check=False)
log = completed.stdout + completed.stderr
(ROOT / 'zz_build_bond_delete.log').write_text(log, encoding='utf-8')
after = data_state()
assets = []
for pattern in ('dist/assets/*.js', 'dist/assets/*.css'):
    for path in sorted(ROOT.glob(pattern)):
        raw = path.read_bytes()
        assets.append({'path': path.relative_to(ROOT).as_posix(), 'bytes': len(raw),
                       'sha256': hashlib.sha256(raw).hexdigest()})
regression = json.loads((ROOT / 'zz_regress_bond_delete_summary.json').read_text(encoding='utf-8'))
expected = regression['productionFundDataSha256']
data_match = all(after[name]['sha256'] == expected[name] for name in DATA)
modules = re.search(r'(\d+) modules transformed', log)
warning = 'Some chunks are larger than 500 kB after minification' if (
    'Some chunks are larger than 500 kB after minification' in log) else None
js_text = '\n'.join(p.read_text(encoding='utf-8') for p in (ROOT / 'dist/assets').glob('*.js'))
retained = {x: x in js_text for x in RETAINED}
removed = {x: x in js_text for x in REMOVED}
viewport = '<meta name="viewport"' in (ROOT / 'dist/index.html').read_text(encoding='utf-8')
result = {
    'task': 'bond-delete', 'command': 'npm run build',
    'startedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
    'durationSeconds': round(time.monotonic() - started, 3),
    'success': bool(completed.returncode == 0 and assets and before == after and data_match
                    and all(retained.values()) and not any(removed.values()) and viewport),
    'returncode': completed.returncode,
    'modulesTransformed': int(modules.group(1)) if modules else None,
    'warning': warning, 'log': 'zz_build_bond_delete.log', 'assets': assets,
    'retainedBundleMarkers': retained, 'removedBundleMarkersPresent': removed, 'viewportMetaPresent': viewport,
    'localFundDataBefore': before, 'localFundDataAfter': after,
    'fundDataUnchanged': before == after, 'matchesRegressionDataSha': data_match,
    'manualDispatch': False, 'productionDataRegenerated': False, 'developmentServerStarted': False,
}
(ROOT / 'zz_build_bond_delete.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['success'] else 1)
