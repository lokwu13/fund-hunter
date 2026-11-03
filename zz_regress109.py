# -*- coding: utf-8 -*-
"""任务109：两个总览入口的源码/DOM契约与真实滚动函数可执行回归。"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
weekly = (ROOT / 'src/sections/WeeklySummary.tsx').read_text(encoding='utf-8')
app = (ROOT / 'src/App.tsx').read_text(encoding='utf-8')
sector = (ROOT / 'src/sections/SectorHeatmap.tsx').read_text(encoding='utf-8')
nav = (ROOT / 'src/navigation.ts').read_text(encoding='utf-8')
checks = []

def check(name, condition):
    checks.append({'name': name, 'passed': bool(condition)})

links = {
    'oversold-value-directions': '查看行业/大概念自身历史估值、双龙头与数据限制',
    'rsi6-dividend-top20': '查看全A股息率TTM Top20完整原榜',
}
for anchor, text in links.items():
    check(f'{anchor}:目标tab为sectors', f"onNavigate?.('sectors', '{anchor}')" in weekly)
    check(f'{anchor}:不再误跳tools', f"onNavigate?.('tools', '{anchor}')" not in weekly)
    check(f'{anchor}:原生键盘按钮', re.search(r'<button type="button" aria-controls="' + re.escape(anchor) + r'"', weekly) is not None)
    check(f'{anchor}:目标id全局唯一', len(re.findall(r'id=["\']' + re.escape(anchor) + r'["\']', ''.join(
        p.read_text(encoding='utf-8') for p in (ROOT / 'src').rglob('*.tsx')))) == 1)
    check(f'{anchor}:目标有滚动边距', re.search(r'<Card id="' + re.escape(anchor) + r'"[^>]*scroll-mt-20', sector) is not None)
    check(f'{anchor}:按钮文案保留', text in weekly)

check('板块详细组件实际承接目标', '<TabsContent value="sectors"' in app and '<SectorHeatmap detailed />' in app)
check('估值卡与按钮使用同一显示条件', 'detailed && extremeReboundActive(data) && data.oversoldValueDirections?.visible' in sector
      and '{data.oversoldValueDirections?.visible && (' in weekly)
check('Top20卡与按钮使用同一显示条件', 'detailed && extremeReboundActive(data) && data.dividendWatch?.rsi6Top20?.visible' in sector
      and '{data.dividendWatch?.rsi6Top20?.visible && (' in weekly)
check('切换tab后使用渲染感知滚动', 'setActiveTab(tab);' in app and 'if (anchor) scrollToRenderedAnchor(anchor);' in app)
check('相关工具返回链路共用可靠滚动', app.count('if (anchor) scrollToRenderedAnchor(anchor);') == 2)
check('无固定150ms竞态', 'setTimeout' not in app)
check('等待DOM且验证可见', 'document.getElementById(anchor)' in nav and 'target.getClientRects().length > 0' in nav)
check('支持prefers-reduced-motion', "window.matchMedia('(prefers-reduced-motion: reduce)').matches" in nav
      and "reducedMotion ? 'auto' : 'smooth'" in nav)

try:
    node = Path(r'C:\Users\Administrator\AppData\Roaming\kimi-desktop\daimon-share\daimon\command-process-owner\bin\node.cmd')
    run = subprocess.run(['cmd', '/c', str(node), 'zz_navigation109.test.cjs'], cwd=ROOT, text=True,
                         encoding='utf-8', capture_output=True, timeout=60)
    dom_output = (run.stdout + run.stderr).strip()
    check('可执行DOM延迟挂载/可见/滚动测试', run.returncode == 0 and '6/6 passed' in dom_output)
except Exception as exc:
    dom_output = str(exc)
    check('可执行DOM延迟挂载/可见/滚动测试', False)

result = {
    'task': 109,
    'checksPassed': sum(c['passed'] for c in checks),
    'checksTotal': len(checks),
    'failed': [c['name'] for c in checks if not c['passed']],
    'checks': checks,
    'domTestOutput': dom_output,
}
(ROOT / 'zz_regress109_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(1 if result['failed'] else 0)
