# -*- coding: utf-8 -*-
"""债券栏目两张完整卡片精准删除：静态差异、共享逻辑与生产数据保护。"""
import ast
import hashlib
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
PANEL = ROOT / 'src/sections/BondsPanel.tsx'
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
current = PANEL.read_text(encoding='utf-8')
baseline = (ROOT / 'zz_bond_delete_BondsPanel_baseline.tsx').read_text(encoding='utf-8')
backend = (ROOT / 'scripts/update_data.py').read_bytes()
backend_baseline = (ROOT / 'zz_bond_delete_update_data_baseline.py').read_bytes()
types = (ROOT / 'src/hooks/useFundData.ts').read_text(encoding='utf-8')
preflight = json.loads((ROOT / 'zz_bond_delete_live_preflight.json').read_text(encoding='utf-8'))
checks = []


def check(name, passed, evidence=None):
    checks.append({'name': name, 'passed': bool(passed), 'evidence': evidence})


start = baseline.index('      {/* ====== 8. 中美国债对比 ====== */')
end = baseline.index('      <BondToStockImpact', start)
expected = (baseline[:start] + '      {/* 债券 → A+H股市影响分析；保留共享us数据与综合评语。 */}\n'
            + baseline[end:])
check('仅目标连续区段发生变化，其他BondsPanel逐字保持', current == expected,
      {'baselineChars': len(baseline), 'currentChars': len(current), 'removedChars': len(baseline) - len(current)})
for title in ('债券市场要闻', '中美国债收益率对比'):
    check(f'活动债券源码标题已删除：{title}', title not in current)
check('完整逐日新闻列表渲染已删除', 'news.map((item, idx)' not in current)
check('中美横向双图条件渲染已删除', '{us && us.latest && (' not in current)
check('中美双图专属横向layout已删除', 'layout="vertical"' not in current)
check('中美双图底部资产吸引力文案已删除',
      '美元资产吸引力更高' not in current and '人民币资产吸引力更高' not in current)
check('共享us数据仍传递股市影响组件',
      'const us = bd.us || null;' in current and '<BondToStockImpact latest={latest} us={us}' in current)
check('共享news仍保留两处既有小幅动态', current.count('news.filter(') == 3
      and '今日债市要闻 · 东方财富' in current and '近期债市动态' in current)
check('短期流动性工具及资金面点评保留',
      '央行短期流动性工具' in current and 'bd.liquidityTools.comment' in current)
check('20日滚动波动率保留', '滚动波动率（20日标准差）' in current and 'volatilityData' in current)
check('累计偏离与期限变动模块保留', all(x in current for x in (
    '收益率累计偏离（近半年）', '累计偏离放大（近1月）', '各期限收益率变动（最新 vs 历史）', '月度涨跌幅')))
check('融资融券与bond-margin锚点保留', '全市场融资融券' in current and 'id="bond-margin"' in current)
check('债市综合评语和中美利差共享逻辑保留', all(x in current for x in (
    '债市信号 → A+H股市一个月影响推演', 'const usCnSpread', 'A股一个月展望', '港股一个月展望',
    '中美利差(25%)', '中美利差(45%)')))
check('共享BondData类型us/news/liquidityTools均保留', all(x in types for x in (
    'us?: {', 'news?: Array<', 'liquidityTools?: {', 'marginTrading?: {')))
def backend_without_concept_changes(raw):
    tree = ast.parse(raw.decode('utf-8'))
    allowed = {'build_sector_crowding', 'fetch_vcp_watch'}
    return [ast.dump(node) for node in tree.body
            if not (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in allowed)]

check('债券基线后仅本次两个概念函数演进', backend_without_concept_changes(backend) == backend_without_concept_changes(backend_baseline),
      {'sha256': hashlib.sha256(backend).hexdigest(),
       'allowedFunctions': ['build_sector_crowding', 'fetch_vcp_watch']})
data_state = {p: {'bytes': (ROOT / p).stat().st_size,
                  'sha256': hashlib.sha256((ROOT / p).read_bytes()).hexdigest()} for p in DATA}
check('本地生产数据与预检逐字节一致', all(
    data_state[p]['sha256'] == preflight['fundData'][p]['localSha256'] for p in DATA), data_state)
check('预检实时main与后端基线有效', preflight['bondsPanelBaselineMatched'] and preflight['backendBaselineMatched'],
      {'head': preflight['head'], 'headTree': preflight['headTree']})
check('截图目标仅两张完整卡片，未扩大删除总览或共享模块', current == expected)

passed = sum(x['passed'] for x in checks)
report = {'task': 'bond-delete', 'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
          'allPassed': passed == len(checks), 'checksPassed': passed, 'checksTotal': len(checks),
          'failed': [x['name'] for x in checks if not x['passed']], 'checks': checks,
          'panelSha256': hashlib.sha256(PANEL.read_bytes()).hexdigest(),
          'productionFundDataSha256': {p: x['sha256'] for p, x in data_state.items()},
          'manualDispatch': False, 'productionDataRegenerated': False, 'developmentServerStarted': False}
(ROOT / 'zz_regress_bond_delete_report.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {k: report[k] for k in ('task', 'allPassed', 'checksPassed', 'checksTotal', 'failed',
                                  'productionFundDataSha256', 'manualDispatch', 'productionDataRegenerated')}
(ROOT / 'zz_regress_bond_delete_summary.json').write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if not report['allPassed']:
    print(json.dumps([x for x in checks if not x['passed']], ensure_ascii=False, indent=2))
raise SystemExit(0 if report['allPassed'] else 1)
