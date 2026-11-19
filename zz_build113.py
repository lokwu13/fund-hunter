# -*- coding: utf-8 -*-
"""任务113生产构建证据；只构建，不启动开发服务器、不生成生产数据。"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime

ROOT = Path(__file__).resolve().parent
DATA = ['public/fund_data.json', 'src/data/fund_data.json']


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def data_state():
    return {name: {'path': name, 'bytes': (ROOT / name).stat().st_size,
                   'sha256': hashlib.sha256((ROOT / name).read_bytes()).hexdigest()} for name in DATA}


before = data_state()
started_at = now()
started = time.monotonic()
completed = subprocess.run('npm run build', cwd=ROOT, shell=True, text=True,
                           encoding='utf-8', errors='replace', capture_output=True, check=False)
log = completed.stdout + completed.stderr
(ROOT / 'zz_build113.log').write_text(log, encoding='utf-8')
after = data_state()
assets = []
for pattern in ('dist/assets/*.js', 'dist/assets/*.css'):
    for path in sorted(ROOT.glob(pattern)):
        raw = path.read_bytes()
        assets.append({'path': path.relative_to(ROOT).as_posix(), 'bytes': len(raw),
                       'sha256': hashlib.sha256(raw).hexdigest()})
regression = json.loads((ROOT / 'zz_regress113_summary.json').read_text(encoding='utf-8'))
expected = regression['productionFundDataSha256']
match = all(after[name]['sha256'] == expected[name] for name in DATA)
modules = re.search(r'(\d+) modules transformed', log)
warning = 'Some chunks are larger than 500 kB after minification' if (
    'Some chunks are larger than 500 kB after minification' in log) else None
result = {
    'task': 113,
    'command': 'npm run build',
    'startedAt': started_at,
    'durationSeconds': round(time.monotonic() - started, 3),
    'success': bool(completed.returncode == 0 and assets and before == after and match),
    'returncode': completed.returncode,
    'modulesTransformed': int(modules.group(1)) if modules else None,
    'warning': warning,
    'log': 'zz_build113.log',
    'assets': assets,
    'localFundDataBefore': before,
    'localFundDataAfter': after,
    'localFundData': after,
    'fundDataUnchanged': before == after,
    'matchesTask113RegressionDataSha': match,
    'manualDispatch': False,
    'productionDataRegenerated': False,
    'developmentServerStarted': False,
}
(ROOT / 'zz_build113.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['success'] else 1)
