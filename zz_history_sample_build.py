# -*- coding: utf-8 -*-
"""历史估值当前快照修复：生产构建与产物标记，不启动开发服务器。"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime

ROOT = Path(__file__).resolve().parent
DATA = ['public/fund_data.json', 'src/data/fund_data.json']

def state():
    return {p: {'bytes': (ROOT / p).stat().st_size,
                'sha256': hashlib.sha256((ROOT / p).read_bytes()).hexdigest()} for p in DATA}

before = state()
started = time.monotonic()
completed = subprocess.run('npm run build', cwd=ROOT, shell=True, text=True, encoding='utf-8',
                           errors='replace', capture_output=True, check=False)
log = completed.stdout + completed.stderr
(ROOT / 'zz_history_sample_build.log').write_text(log, encoding='utf-8')
after = state()
assets = []
for pattern in ('dist/assets/*.js', 'dist/assets/*.css'):
    for path in sorted(ROOT.glob(pattern)):
        assets.append({'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
                       'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
js = '\n'.join(p.read_text(encoding='utf-8') for p in (ROOT / 'dist/assets').glob('*.js'))
markers = {text: text in js for text in (
    'RSI6≤20窗 · 行业 / 大概念自身历史估值低→高与双龙头', '成分：', 'asOf', '当前快照',
    '当前PE_TTM中位数', '总市值', '历史样本')}
modules = re.search(r'(\d+) modules transformed', log)
result = {'task': 'history-sample', 'command': 'npm run build',
          'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
          'durationSeconds': round(time.monotonic() - started, 3), 'returncode': completed.returncode,
          'modulesTransformed': int(modules.group(1)) if modules else None,
          'success': completed.returncode == 0 and bool(assets) and before == after and all(markers.values()),
          'warning': 'Some chunks are larger than 500 kB after minification' if 'Some chunks are larger than 500 kB' in log else None,
          'assets': assets, 'bundleMarkers': markers, 'fundDataBefore': before, 'fundDataAfter': after,
          'fundDataUnchanged': before == after, 'developmentServerStarted': False,
          'productionDataRegenerated': False, 'manualDispatch': False}
(ROOT / 'zz_history_sample_build.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['success'] else 1)
