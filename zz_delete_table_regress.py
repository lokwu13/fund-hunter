# -*- coding: utf-8 -*-
"""外资摘要双卡精准删除：逐字差异、相邻模块、共享字段与生产数据保护。"""
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PANEL = 'src/sections/ForeignCapitalPanel.tsx'
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
TARGET_TITLES = [
    '北向成交 (本周)', '南下资金 (本周)',
    '北向成交（本周）', '南下资金（本周）',
]

current = (ROOT / PANEL).read_text(encoding='utf-8')
baseline = (ROOT / 'zz_delete_table_ForeignCapitalPanel_baseline.tsx').read_text(encoding='utf-8')
preflight = json.loads((ROOT / 'zz_delete_table_live_preflight.json').read_text(encoding='utf-8'))
types = (ROOT / 'src/hooks/useFundData.ts').read_text(encoding='utf-8')
app = (ROOT / 'src/App.tsx').read_bytes()
backend = (ROOT / 'scripts/update_data.py').read_bytes()
active_frontend = '\n'.join(
    p.read_text(encoding='utf-8')
    for pattern in ('*.ts', '*.tsx')
    for p in (ROOT / 'src').rglob(pattern)
)
checks = []


def check(name, passed, evidence=None):
    checks.append({'name': name, 'passed': bool(passed), 'evidence': evidence})


expected = baseline.replace(
    "import { Globe, ArrowUpRight, ArrowDownRight, ChevronRight, Activity, TrendingUp, TrendingDown, AlertTriangle, FileText } from 'lucide-react';",
    "import { Globe, ChevronRight, Activity, TrendingUp, TrendingDown, AlertTriangle, FileText } from 'lucide-react';",
    1,
).replace(
    '  const { data } = useFundData();\n  const nb = data.northbound;\n  const sb = data.southbound;\n',
    '  const { data } = useFundData();\n',
    1,
)
start = expected.index('      {/* Northbound & Southbound Summary */}')
end = expected.index('      {/* ====== CCASS 外资托管持股月末快照', start)
expected = expected[:start] + expected[end:]
check('仅删除目标双卡组及其专属导入和局部变量，其他面板逐字保持', current == expected, {
    'baselineChars': len(baseline), 'currentChars': len(current),
    'removedChars': len(baseline) - len(current),
})
for title in TARGET_TITLES:
    check(f'活动前端不再含目标标题：{title}', title not in active_frontend)
check('目标双卡容器与注释整体移除', 'Northbound & Southbound Summary' not in current
      and '官方2024-08起停披净买入，现为成交总额口径' not in current)
check('目标卡专属局部变量和金额渲染移除', all(x not in current for x in (
    'const nb = data.northbound;', 'const sb = data.southbound;', '{nb.week}', '{sb.week}')))
check('目标卡专属图标导入清理且无残留引用', 'ArrowUpRight' not in current and 'ArrowDownRight' not in current)
check('CCASS 外资托管持股模块及锚点保留', all(x in current for x in (
    'id="ccass-foreign"', '外资托管持股动向（CCASS 月末快照）', 'cf.items.map')))
check('外资机构增减仓模块及锚点保留', all(x in current for x in (
    'id="di-foreign"', '外资机构增减仓（权益披露）', 'di.items.map')))
check('公告列与申报书外链保留', all(x in current for x in (
    '<th className="text-right font-medium">公告</th>', 'href={it.url}', '>申报书</a>')))
check('南下资金独立持股集中度表保留', all(x in current for x in (
    '南下资金（国内资金）持股集中度TOP10', 'data.southbound_concentration_top10?.map')))
check('北向资金独立净流入 TOP10 保留', all(x in current for x in (
    '北向资金近三个月净流入最多TOP10', 'data.top10_foreign?.map')))
check('内外资分歧图和独立详细表保留', all(x in current for x in (
    '内外资分歧 — 个股双向流向对比', '内外资分歧最大十大标的', 'data.divergence_top10?.map')))
check('外资机构买卖及详细表保留', all(x in current for x in (
    '外资机构买入TOP10（A+H股）', '外资机构卖出TOP10（A+H股）', '外资机构买入TOP10详细（A+H股全市场）')))
check('共享 northbound/southbound 前端类型保留', all(x in types for x in (
    'northbound: { today: number; week: number;', 'southbound: { today: number; week: number;')))
local_json = {path: json.loads((ROOT / path).read_text(encoding='utf-8')) for path in DATA}
check('两份本地生产 JSON 的共享 northbound/southbound 字段均保留', all(
    isinstance(doc.get('northbound'), dict) and isinstance(doc.get('southbound'), dict)
    and 'week' in doc['northbound'] and 'week' in doc['southbound']
    for doc in local_json.values()))
check('WeeklySummary 关于保留共享 northbound/southbound 数据的既有约定未破坏',
      'nationalETFWatch/northbound/southbound' in (ROOT / 'src/sections/WeeklySummary.tsx').read_text(encoding='utf-8'))
check('App 与实时 main 预检基线逐字节一致',
      hashlib.sha256(app).hexdigest() == preflight['protectedFrontend']['src/App.tsx']['localSha256'])
check('共享数据 Hook 与实时 main 预检基线逐字节一致',
      hashlib.sha256((ROOT / 'src/hooks/useFundData.ts').read_bytes()).hexdigest()
      == preflight['protectedFrontend']['src/hooks/useFundData.ts']['localSha256'])
check('后端取数脚本与实时 main 基线逐字节一致',
      backend == (ROOT / 'zz_delete_table_update_data_baseline.py').read_bytes(),
      {'sha256': hashlib.sha256(backend).hexdigest()})
data_state = {
    path: {'bytes': (ROOT / path).stat().st_size,
           'sha256': hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
    for path in DATA
}
check('本地生产 JSON 与预检逐字节一致', all(
    data_state[path]['sha256'] == preflight['fundData'][path]['localSha256'] for path in DATA), data_state)
check('实时 main 与线上生产 JSON 预检一致', preflight['onlineEqualsRemoteMain']
      and preflight['fundData']['public/fund_data.json']['remoteSha256'] == preflight['onlineFundDataSha256'])
check('目标双卡没有独立锚点，未误删 CCASS/DI 锚点',
      'id="northbound' not in baseline and 'id="southbound' not in baseline
      and 'id="ccass-foreign"' in current and 'id="di-foreign"' in current)

passed = sum(item['passed'] for item in checks)
report = {
    'task': 'delete-table',
    'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
    'allPassed': passed == len(checks),
    'checksPassed': passed,
    'checksTotal': len(checks),
    'failed': [item['name'] for item in checks if not item['passed']],
    'checks': checks,
    'panelSha256': hashlib.sha256((ROOT / PANEL).read_bytes()).hexdigest(),
    'productionFundDataSha256': {path: state['sha256'] for path, state in data_state.items()},
    'manualDispatch': False,
    'productionDataRegenerated': False,
    'developmentServerStarted': False,
}
(ROOT / 'zz_delete_table_regress.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {key: report[key] for key in (
    'task', 'allPassed', 'checksPassed', 'checksTotal', 'failed',
    'productionFundDataSha256', 'manualDispatch', 'productionDataRegenerated')}
(ROOT / 'zz_delete_table_regress_summary.json').write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if not report['allPassed']:
    print(json.dumps([item for item in checks if not item['passed']], ensure_ascii=False, indent=2))
raise SystemExit(0 if report['allPassed'] else 1)
