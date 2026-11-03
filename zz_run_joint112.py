# -*- coding: utf-8 -*-
"""任务112历史联合回归：分批真实执行、逐项落日志并合并机器结果。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime

ROOT = Path(__file__).resolve().parent
ALL_TASKS = [92, 95, 96, 99, 101, 102, 104, 105, 106, 107, 108, 109, 110]
OUT = ROOT / 'zz_joint_regress112.json'


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tasks', type=int, nargs='+', default=ALL_TASKS)
    parser.add_argument('--timeout', type=int, default=240)
    args = parser.parse_args()
    unknown = sorted(set(args.tasks) - set(ALL_TASKS))
    if unknown:
        raise SystemExit(f'未知任务: {unknown}')
    previous = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    by_task = {x['task']: x for x in previous.get('results', [])}
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONPATH'] = str(ROOT / 'scripts')
    for task in args.tasks:
        script = ROOT / f'zz_regress{task}.py'
        log = ROOT / f'zz_regress{task}_task112.log'
        command = [sys.executable, str(script)]
        started = time.monotonic()
        record = {
            'task': task,
            'command': subprocess.list2cmdline(command),
            'cwd': str(ROOT),
            'environment': {'PYTHONIOENCODING': 'utf-8', 'PYTHONPATH': str(ROOT / 'scripts')},
            'log': log.name,
            'startedAt': now(),
            'timeoutSeconds': args.timeout,
        }
        try:
            with log.open('w', encoding='utf-8') as handle:
                completed = subprocess.run(command, cwd=ROOT, env=env, stdout=handle,
                                           stderr=subprocess.STDOUT, timeout=args.timeout, check=False)
            record['returncode'] = completed.returncode
            record['passed'] = completed.returncode == 0
        except subprocess.TimeoutExpired:
            record['returncode'] = None
            record['passed'] = False
            record['error'] = f'超过{args.timeout}秒'
        except Exception as exc:
            record['returncode'] = None
            record['passed'] = False
            record['error'] = f'{type(exc).__name__}: {exc}'
        record['durationSeconds'] = round(time.monotonic() - started, 3)
        record['finishedAt'] = now()
        record['logBytes'] = log.stat().st_size if log.exists() else 0
        by_task[task] = record
        results = [by_task[t] for t in ALL_TASKS if t in by_task]
        complete = all(t in by_task for t in ALL_TASKS)
        result = {
            'task': 112,
            'complete': complete,
            'allPassed': bool(complete and all(by_task[t]['passed'] for t in ALL_TASKS)),
            'passed': sum(bool(by_task[t]['passed']) for t in ALL_TASKS if t in by_task),
            'executed': len(results),
            'total': len(ALL_TASKS),
            'manualDispatch': False,
            'productionDataRegenerated': False,
            'results': results,
        }
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(record, ensure_ascii=False), flush=True)
    return 0 if all(by_task[t]['passed'] for t in args.tasks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
