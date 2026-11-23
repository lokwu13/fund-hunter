# -*- coding: utf-8 -*-
"""任务1102生产构建；不启动服务器、不生成或改写生产数据。"""
import hashlib
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
RETAINED = [
    '内外资分歧最大十大标的', '如何理解内外资分歧',
    '外资托管持股动向（CCASS 月末快照）', 'ccass-foreign',
    '外资机构增减仓（权益披露）', 'di-foreign', '公告', '申报书',
    '南下资金（国内资金）持股集中度TOP10', '北向资金近三个月净流入最多TOP10',
    '外资机构买入TOP10详细（A+H股全市场）',
]
REMOVED = [
    '内外资分歧 — 个股双向流向对比', '个股双向流向对比',
    '同一标的上：南向资金买入 vs 国际中介卖出 · 单位：亿港元',
    '左右两端长度代表金额大小 · 中间竖线为分界 · 两侧同时存在=激烈分歧',
]


def data_state():
    return {name: {'path': name, 'bytes': (ROOT / name).stat().st_size,
                   'sha256': hashlib.sha256((ROOT / name).read_bytes()).hexdigest()} for name in DATA}


before = data_state()
started = time.monotonic()
completed = subprocess.run(
    'npm run build', cwd=ROOT, shell=True, text=True,
    encoding='utf-8', errors='replace', capture_output=True, check=False)
log = completed.stdout + completed.stderr
(ROOT / 'zz_delete_table_1102_build.log').write_text(log, encoding='utf-8')
after = data_state()
assets = []
for pattern in ('dist/assets/*.js', 'dist/assets/*.css'):
    for path in sorted(ROOT.glob(pattern)):
        raw = path.read_bytes()
        assets.append({'path': path.relative_to(ROOT).as_posix(), 'bytes': len(raw),
                       'sha256': hashlib.sha256(raw).hexdigest()})
regression = json.loads((ROOT / 'zz_delete_table_1102_regress_summary.json').read_text(encoding='utf-8'))
expected = regression['productionFundDataSha256']
data_match = all(after[name]['sha256'] == expected[name] for name in DATA)
modules = re.search(r'(\d+) modules transformed', log)
warning = 'Some chunks are larger than 500 kB after minification' if (
    'Some chunks are larger than 500 kB after minification' in log) else None
js_text = '\n'.join(path.read_text(encoding='utf-8') for path in (ROOT / 'dist/assets').glob('*.js'))
retained = {text: text in js_text for text in RETAINED}
removed = {text: text in js_text for text in REMOVED}
viewport = '<meta name="viewport"' in (ROOT / 'dist/index.html').read_text(encoding='utf-8')
result = {
    'task': 'delete-table-1102', 'command': 'npm run build',
    'startedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
    'durationSeconds': round(time.monotonic() - started, 3),
    'success': bool(completed.returncode == 0 and assets and before == after and data_match
                    and all(retained.values()) and not any(removed.values()) and viewport),
    'returncode': completed.returncode,
    'modulesTransformed': int(modules.group(1)) if modules else None,
    'warning': warning, 'log': 'zz_delete_table_1102_build.log', 'assets': assets,
    'retainedBundleMarkers': retained, 'removedBundleMarkersPresent': removed,
    'viewportMetaPresent': viewport,
    'localFundDataBefore': before, 'localFundDataAfter': after,
    'fundDataUnchanged': before == after, 'matchesRegressionDataSha': data_match,
    'manualDispatch': False, 'productionDataRegenerated': False, 'developmentServerStarted': False,
    'browserConsoleVerified': False,
}
(ROOT / 'zz_delete_table_1102_build.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['success'] else 1)
