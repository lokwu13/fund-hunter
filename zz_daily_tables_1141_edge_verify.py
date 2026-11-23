# -*- coding: utf-8 -*-
"""任务1141：真实 Edge 渲染两榜、切换外资页签与局部截图；临时服务/进程全部关闭。"""
import base64
import functools
import http.server
import json
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
import websocket

ROOT = Path(__file__).resolve().parent
EDGE = Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
PROFILE = ROOT / 'zz_daily_tables_1141_edge_profile'
SCREENSHOT = ROOT / 'zz_daily_tables_1141_edge_tables.png'
REPORT = ROOT / 'zz_daily_tables_1141_edge_verification.json'
assert EDGE.is_file()
shutil.rmtree(PROFILE, ignore_errors=True)
PROFILE.mkdir()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/fund-hunter/'):
            self.path = self.path[len('/fund-hunter'):]
        return super().do_GET()

    def log_message(self, fmt, *args):
        pass


server = http.server.ThreadingHTTPServer(
    ('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT / 'dist')))
server_thread = threading.Thread(target=server.serve_forever, daemon=True)
server_thread.start()
url = f'http://127.0.0.1:{server.server_port}/fund-hunter/'
edge = None
ws = None
next_id = 0


def evaluate(expression):
    global next_id
    next_id += 1
    command_id = next_id
    ws.send(json.dumps({'id': command_id, 'method': 'Runtime.evaluate',
                        'params': {'expression': expression, 'returnByValue': True, 'awaitPromise': True}}))
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        message = json.loads(ws.recv())
        if message.get('id') == command_id:
            if 'error' in message:
                raise RuntimeError(message['error'])
            return (message.get('result') or {}).get('result', {}).get('value')
    raise TimeoutError('CDP Runtime.evaluate 超时')


def wait_for(expression, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if evaluate(expression):
            return True
        time.sleep(0.25)
    return False


try:
    edge = subprocess.Popen([
        str(EDGE), '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
        '--remote-debugging-port=0', '--remote-allow-origins=*', f'--user-data-dir={PROFILE}', url,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_file = PROFILE / 'DevToolsActivePort'
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline and not port_file.is_file():
        if edge.poll() is not None:
            raise RuntimeError(f'Edge 提前退出：{edge.returncode}')
        time.sleep(0.2)
    assert port_file.is_file(), 'Edge 未写 DevToolsActivePort'
    debug_port = int(port_file.read_text().splitlines()[0])
    page = None
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        pages = requests.get(f'http://127.0.0.1:{debug_port}/json/list', timeout=2).json()
        page = next((item for item in pages if item.get('type') == 'page'
                     and item.get('url', '').startswith(url)), None)
        if page:
            break
        time.sleep(0.25)
    assert page, '未找到 Edge 页面目标'
    ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=20, origin='http://127.0.0.1')
    next_id += 1
    metrics_id = next_id
    ws.send(json.dumps({'id': metrics_id, 'method': 'Emulation.setDeviceMetricsOverride',
                        'params': {'width': 1600, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False}}))
    while True:
        message = json.loads(ws.recv())
        if message.get('id') == metrics_id:
            assert 'result' in message, message
            break
    assert wait_for("document.readyState === 'complete' && !!document.querySelector('button')"), '页面未完成加载'
    clicked = evaluate("""(() => {
      const button = Array.from(document.querySelectorAll('button'))
        .find(item => item.textContent.trim() === '外资');
      if (!button) return false;
      button.focus();
      for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
        const EventClass = type.startsWith('pointer') ? PointerEvent : MouseEvent;
        button.dispatchEvent(new EventClass(type, {
          bubbles: true, cancelable: true, view: window, button: 0, buttons: type.includes('down') ? 1 : 0
        }));
      }
      return true;
    })()""")
    assert clicked, '未找到外资页签按钮'
    assert wait_for("document.body.innerText.includes('南下资金（国内资金）持股集中度TOP10')"), '外资页签内容未渲染'
    selected = evaluate("""Array.from(document.querySelectorAll('button'))
      .filter(item => item.getAttribute('aria-selected') === 'true').map(item => item.textContent.trim())""")
    body_flags = evaluate("""(() => {
      const text = document.body.innerText;
      return {
        southbound: text.includes('南下资金（国内资金）持股集中度TOP10'),
        foreignConcentration: text.includes('外资（非国内资金）持股集中度TOP10'),
        southSource: text.includes('Tushare hk_hold（港交所CCASS港股通持股）'),
        southFrequency: text.includes('日更'),
        southAsOf: text.includes('截至 2026-10-23'),
        foreignSource: text.includes('港交所CCASS'),
        foreignManualFrequency: text.includes('手工季更'),
        foreignAsOf: text.includes('截至 2026-07-04'),
        newForeignSubtitle: text.includes('国际中介/外资托管行持股占港股总股本比例'),
        tips: text.includes('如何理解内外资分歧'),
        northbound: text.includes('北向资金近三个月净流入最多TOP10'),
        ccass: document.querySelectorAll('#ccass-foreign').length,
        di: document.querySelectorAll('#di-foreign').length,
        disclosureLinks: document.querySelectorAll('#di-foreign a[href]').length,
        viewportWidth: document.documentElement.clientWidth,
        removedTop10: text.includes('内外资分歧最大十大标的'),
        previousChart: text.includes('个股双向流向对比')
      };
    })()""")
    shot_clip = evaluate("""(() => {
      const node = Array.from(document.querySelectorAll('*'))
        .find(item => item.textContent.trim() === '南下资金（国内资金）持股集中度TOP10');
      if (!node) return null;
      const rect = node.getBoundingClientRect();
      return {
        x: 0, y: Math.max(0, rect.top + window.scrollY - 120),
        width: document.documentElement.clientWidth, height: 760, scale: 1
      };
    })()""")
    assert shot_clip, '未找到两榜截图位置'
    time.sleep(0.5)
    next_id += 1
    shot_id = next_id
    ws.send(json.dumps({'id': shot_id, 'method': 'Page.captureScreenshot',
                        'params': {'format': 'png', 'captureBeyondViewport': True, 'clip': shot_clip}}))
    while True:
        message = json.loads(ws.recv())
        if message.get('id') == shot_id:
            assert 'result' in message, message
            SCREENSHOT.write_bytes(base64.b64decode(message['result']['data']))
            break
    checks = {
        'realEdgeRendered': True,
        'foreignTabClicked': '外资' in (selected or []),
        'bothTablesRendered': body_flags['southbound'] and body_flags['foreignConcentration'],
        'southSourceFrequencyAsOfRendered': body_flags['southSource'] and body_flags['southFrequency'] and body_flags['southAsOf'],
        'foreignCurrentManualFrequencyHonest': body_flags['foreignSource'] and body_flags['foreignManualFrequency'] and body_flags['foreignAsOf'],
        'newForeignSubtitleRendered': body_flags['newForeignSubtitle'],
        'independentTipsRetained': body_flags['tips'],
        'northboundRetained': body_flags['northbound'],
        'ccassAnchorRetained': body_flags['ccass'] == 1,
        'diAnchorRetained': body_flags['di'] == 1,
        'disclosureLinksRetained': body_flags['disclosureLinks'] == 80,
        'previousRemovalsNotRestored': not body_flags['removedTop10'] and not body_flags['previousChart'],
        'desktopViewportApplied': 1580 <= body_flags['viewportWidth'] <= 1600,
        'screenshotCaptured': SCREENSHOT.is_file() and SCREENSHOT.stat().st_size > 0,
    }
    result = {
        'task': 'daily-tables-1141', 'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
        'browser': 'Microsoft Edge headless (CDP)',
        'automationFramework': 'websocket-client / Chrome DevTools Protocol; no Playwright/Selenium/Puppeteer',
        'localUrl': url, 'selectedTabs': selected, 'bodyFlags': body_flags,
        'checks': checks, 'allPassed': all(checks.values()), 'screenshot': SCREENSHOT.name,
        'browserConsoleVerified': False,
        'limitation': '真实 Edge 渲染、外资页签切换和两榜局部截图；使用本地旧生产JSON确认界面如实显示现有as-of/手工季更，未把新频率提前冒充到旧数据。未采集完整浏览器 Console，未做全站交互巡检。',
        'temporaryStaticServerStopped': False, 'edgeProcessStopped': False,
    }
finally:
    if ws is not None:
        try:
            ws.close()
        except Exception:
            pass
    if edge is not None:
        if edge.poll() is None:
            edge.terminate()
            try:
                edge.wait(timeout=10)
            except subprocess.TimeoutExpired:
                edge.kill()
                edge.wait(timeout=5)
    server.shutdown()
    server.server_close()
    server_thread.join(timeout=5)
    shutil.rmtree(PROFILE, ignore_errors=True)

result['temporaryStaticServerStopped'] = not server_thread.is_alive()
result['edgeProcessStopped'] = edge is not None and edge.poll() is not None
result['allPassed'] = result['allPassed'] and result['temporaryStaticServerStopped'] and result['edgeProcessStopped']
REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['allPassed'] else 1)
