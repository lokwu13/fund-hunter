# -*- coding: utf-8 -*-
"""任务1102：双向流向卡精准删除、移动静态规则、交互锚点与生产数据保护。"""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PANEL = 'src/sections/ForeignCapitalPanel.tsx'
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
current = (ROOT / PANEL).read_text(encoding='utf-8')
baseline = (ROOT / 'zz_delete_table_1102_ForeignCapitalPanel_baseline.tsx').read_text(encoding='utf-8')
preflight = json.loads((ROOT / 'zz_delete_table_1102_live_preflight.json').read_text(encoding='utf-8'))
types = (ROOT / 'src/hooks/useFundData.ts').read_text(encoding='utf-8')
active_frontend = '\n'.join(
    p.read_text(encoding='utf-8')
    for pattern in ('*.ts', '*.tsx') for p in (ROOT / 'src').rglob(pattern)
)
checks = []


def check(name, passed, evidence=None):
    checks.append({'name': name, 'passed': bool(passed), 'evidence': evidence})


expected = baseline.replace(
    "import { Globe, ChevronRight, Activity, TrendingUp, TrendingDown, AlertTriangle, FileText } from 'lucide-react';",
    "import { Globe, ChevronRight, Activity, TrendingUp, TrendingDown, FileText } from 'lucide-react';",
    1,
)
data_start = expected.index('// 分歧数据 - 南向流入 vs 外资流出')
data_end = expected.index('export default function ForeignCapitalPanel()', data_start)
expected = expected[:data_start] + expected[data_end:]
flow_start = expected.index('  // 计算最大比例用于条形图')
flow_end = expected.index('  // ── CCASS 外资托管持股月末快照', flow_start)
expected = expected[:flow_start] + expected[flow_end:]
card_start = expected.index('      {/* ====== 内外资分歧个股双向对比图 ====== */}')
card_end = expected.index('      {/* ====== 分歧TOP10详细表格 ====== */}', card_start)
expected = expected[:card_start] + expected[card_end:]
check('仅删除目标卡片、divergenceData、maxFlow 与 AlertTriangle，其他面板逐字保持',
      current == expected, {'baselineChars': len(baseline), 'currentChars': len(current),
                            'removedChars': len(baseline) - len(current)})
for marker in preflight['targetMarkers']:
    check(f'活动前端目标标记已删除：{marker}', marker not in active_frontend)
check('目标专属静态个股数组与比例计算全部移除', all(x not in active_frontend for x in (
    'const divergenceData = [', 'const maxFlow = Math.max(', 'divergenceData.map',
    'southPct', 'foreignPct', 'divergenceTotal')))
check('目标专属双向条样式与图标无残留', all(x not in current for x in (
    'AlertTriangle', 'bg-red-400 rounded-l-md', 'bg-emerald-400 rounded-r-md',
    '内外资分歧个股双向对比图')))
check('独立内外资分歧 TOP10 表格保留', all(x in current for x in (
    '内外资分歧最大十大标的', 'data.divergence_top10?.map', '分歧TOP10详细表格')))
check('独立如何理解内外资分歧说明卡保留', '如何理解内外资分歧' in current)
check('CCASS 外资托管模块及锚点保留', all(x in current for x in (
    'id="ccass-foreign"', '外资托管持股动向（CCASS 月末快照）', 'cf.items.map')))
check('外资机构增减仓模块及锚点保留', all(x in current for x in (
    'id="di-foreign"', '外资机构增减仓（权益披露）', 'di.items.map')))
check('公告列及申报书外链保留', all(x in current for x in (
    '<th className="text-right font-medium">公告</th>', 'href={it.url}',
    'target="_blank" rel="noreferrer"', '>申报书</a>')))
check('南下资金独立持股集中度表保留', all(x in current for x in (
    '南下资金（国内资金）持股集中度TOP10', 'data.southbound_concentration_top10?.map')))
check('北向资金独立净流入 TOP10 保留', all(x in current for x in (
    '北向资金近三个月净流入最多TOP10', 'data.top10_foreign?.map')))
check('外资机构买卖及详细表保留', all(x in current for x in (
    '外资机构买入TOP10（A+H股）', '外资机构卖出TOP10（A+H股）',
    '外资机构买入TOP10详细（A+H股全市场）')))
check('此前删除的北向/南下本周摘要卡未恢复', all(x not in active_frontend for x in (
    '北向成交 (本周)', '南下资金 (本周)', '北向成交（本周）', '南下资金（本周）')))
check('共享 northbound/southbound 前端类型保留', all(x in types for x in (
    'northbound: { today: number; week: number;', 'southbound: { today: number; week: number;')))
local_json = {path: json.loads((ROOT / path).read_text(encoding='utf-8')) for path in DATA}
check('本地生产 JSON 的共享 northbound/southbound 字段均保留', all(
    isinstance(doc.get('northbound'), dict) and isinstance(doc.get('southbound'), dict)
    and 'week' in doc['northbound'] and 'week' in doc['southbound']
    for doc in local_json.values()))
check('App 与实时 main 预检基线逐字节一致',
      hashlib.sha256((ROOT / 'src/App.tsx').read_bytes()).hexdigest()
      == preflight['protectedFrontend']['src/App.tsx']['localSha256'])
check('共享数据 Hook 与实时 main 预检基线逐字节一致',
      hashlib.sha256((ROOT / 'src/hooks/useFundData.ts').read_bytes()).hexdigest()
      == preflight['protectedFrontend']['src/hooks/useFundData.ts']['localSha256'])
check('后端取数脚本与实时 main 基线逐字节一致',
      (ROOT / 'scripts/update_data.py').read_bytes()
      == (ROOT / 'zz_delete_table_1102_update_data_baseline.py').read_bytes())
data_state = {path: {'bytes': (ROOT / path).stat().st_size,
                     'sha256': hashlib.sha256((ROOT / path).read_bytes()).hexdigest()} for path in DATA}
check('本地生产 JSON 与预检逐字节一致', all(
    data_state[path]['sha256'] == preflight['fundData'][path]['localSha256'] for path in DATA), data_state)
check('实时 main 与线上生产 JSON 预检一致', preflight['onlineEqualsRemoteMain']
      and preflight['fundData']['public/fund_data.json']['remoteSha256'] == preflight['onlineFundDataSha256'])

index_html = (ROOT / 'index.html').read_text(encoding='utf-8')
check('移动静态规则：桌面看板 viewport 保留且本任务未改入口 HTML', '<meta name="viewport"' in index_html
      and current == expected, {'existingZoomPolicyUnchanged': 'user-scalable=no' in index_html})
fixed_widths = re.findall(r'(?<![-\w])w-\[(\d+)px\]|(?<!min-)(?<!max-)width:\s*(\d+)px', current)
oversized = [int(a or b) for a, b in fixed_widths if int(a or b) > 375]
check('移动静态规则：当前面板无大于375px的固定元素宽度', not oversized, {'oversized': oversized})
check('移动静态规则：既有宽表最小宽度均由横向滚动容器承接',
      current.count('min-w-[560px]') == 1 and current.count('min-w-[640px]') == 1
      and current.count('overflow-x-auto') >= 2)
ids = re.findall(r'id=["\']([A-Za-z0-9_-]+)["\']', active_frontend)
hrefs = re.findall(r'href=["\']#([^"\']*)["\']', active_frontend)
check('交互锚点：无空占位 href，所有静态页内锚点均有目标',
      all(target and target in ids for target in hrefs), {'hrefs': hrefs})
check('交互锚点：CCASS/DI 目标全局唯一且未受删除影响',
      ids.count('ccass-foreign') == 1 and ids.count('di-foreign') == 1)
check('目标卡原本无独立锚点，本次未删除其他锚点',
      'id="divergence' not in baseline and 'id="ccass-foreign"' in current
      and 'id="di-foreign"' in current)

passed = sum(item['passed'] for item in checks)
report = {
    'task': 'delete-table-1102',
    'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
    'allPassed': passed == len(checks), 'checksPassed': passed, 'checksTotal': len(checks),
    'failed': [item['name'] for item in checks if not item['passed']], 'checks': checks,
    'panelSha256': hashlib.sha256((ROOT / PANEL).read_bytes()).hexdigest(),
    'productionFundDataSha256': {path: state['sha256'] for path, state in data_state.items()},
    'manualDispatch': False, 'productionDataRegenerated': False,
    'developmentServerStarted': False, 'browserConsoleVerified': False,
}
(ROOT / 'zz_delete_table_1102_regress.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {key: report[key] for key in (
    'task', 'allPassed', 'checksPassed', 'checksTotal', 'failed',
    'productionFundDataSha256', 'manualDispatch', 'productionDataRegenerated')}
(ROOT / 'zz_delete_table_1102_regress_summary.json').write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if not report['allPassed']:
    print(json.dumps([item for item in checks if not item['passed']], ensure_ascii=False, indent=2))
raise SystemExit(0 if report['allPassed'] else 1)
