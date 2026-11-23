# -*- coding: utf-8 -*-
"""任务1141：更新链路、数据契约、相邻模块、锚点及生产数据静态回归。"""
import ast
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PANEL = 'src/sections/ForeignCapitalPanel.tsx'
BACKEND = 'scripts/update_data.py'
DATA = ['public/fund_data.json', 'src/data/fund_data.json']
panel = (ROOT / PANEL).read_text(encoding='utf-8')
panel_base = (ROOT / 'zz_daily_tables_1141_ForeignCapitalPanel_baseline.tsx').read_text(encoding='utf-8')
backend = (ROOT / BACKEND).read_text(encoding='utf-8')
backend_base = (ROOT / 'zz_daily_tables_1141_update_data_baseline.py').read_text(encoding='utf-8')
workflow = (ROOT / '.github/workflows/daily-update.yml').read_bytes()
workflow_base = (ROOT / 'zz_daily_tables_1141_daily_update_baseline.yml').read_bytes()
preflight = json.loads((ROOT / 'zz_daily_tables_1141_live_preflight.json').read_text(encoding='utf-8'))
backend_tests = json.loads((ROOT / 'zz_daily_tables_1141_backend_tests.json').read_text(encoding='utf-8'))
real = json.loads((ROOT / 'zz_daily_tables_1141_real_source_verify.json').read_text(encoding='utf-8'))
active_frontend = '\n'.join(p.read_text(encoding='utf-8') for pattern in ('*.ts', '*.tsx')
                            for p in (ROOT / 'src').rglob(pattern))
checks = []


def check(name, passed, evidence=None):
    checks.append({'name': name, 'passed': bool(passed), 'evidence': evidence})


check('后端契约35项全过', backend_tests['allPassed'] and backend_tests['checksPassed'] == backend_tests['checksTotal'] == 35)
check('真实源干跑通过', real['allPassed'] and real['isolatedCache'] and not real['fullNightlyDispatched'])
check('真实hk_hold日期已归一到交易日', real['hkHold']['actualAvailableDate'] == '20261120'
      and real['hkHold']['weekendDuplicate']['sameTencentRatio'])
check('真实CCASS日期与hk_hold一致', real['ccass']['actualAvailableDate'] == '2026-11-20')
check('真实CCASS比例公式及分母有效', real['ccass']['formula'] == 'foreign / totalIssued * 100'
      and real['ccass']['issuedShares'] > 0 and real['ccass']['calculatedRatio'] == '56.42%')
check('真实断源last-good验证通过', real['failureFallback']['rowsUnchanged']
      and real['failureFallback']['asOfUnchanged'] == '2026-11-20')
check('生产数据未由测试重新生成', real['productionDataUnchanged'] and not real['productionDataRegenerated'])

check('南向更新器复用hk_hold', 'def _fetch_hk_hold_latest' in backend and 'pro.hk_hold(trade_date=d)' in backend)
check('交易日历排除周末', 'def _recent_open_dates' in backend and "exchange='SSE'" in backend
      and "cal['is_open'].astype(int) == 1" in backend and 'day.weekday() < 5' in backend)
check('周末源标签不会直接作为as-of', "dates.str.fullmatch(r'\\d{8}') & dates.isin(open_days)" in backend)
check('南向成功返回真实日期', 'return d\n    except Exception as e:' in backend
      and 'southbound_concentration_date = fetch_southbound_concentration(pro, trade_date, data)' in backend)
check('右榜已接入同一nightly调用链',
      'fetch_foreign_concentration(pro, trade_date, data, preferred_date=southbound_concentration_date)' in backend)
check('右榜复用现有SDW链路', '_ccass_get_form()' in backend and '_ccass_query(code5, dd, form)' in backend)
check('SDW解析真实已发行股本', 'Total number of Issued Shares/Warrants/Units' in backend
      and "'totalIssued': int(issued.group(1).replace(',', '')) if issued else None" in backend)
check('右榜比例非静态硬编码', "float(cur['foreign']) / int(cur['totalIssued']) * 100" in backend
      and '42.56%' not in backend and '36.45%' not in backend)
check('完整20只才允许发布', 'def complete(iso):' in backend
      and 'all(valid(code5, snap.get(code5)) for code5, _ in CCASS_STOCKS)' in backend)
check('右榜明确20只池非全市场', '现有20只港股蓝筹跟踪池，非全市场排名' in backend)
check('右榜机构字段不再伪造具体股东', "'institution': '主流外资托管行合计'" in backend)
check('每日缓存与月末缓存分离', "cache.setdefault('concentrationSnapshots', {})" in backend
      and "cache.setdefault('snapshots', {})" in backend)
check('月末CCASS函数逐字未改', backend[backend.index('def fetch_ccass_foreign'):backend.index('def fetch_foreign_concentration')]
      == backend_base[backend_base.index('def fetch_ccass_foreign'):backend_base.index('# ── DI 权益披露')])
check('断源仅标记已日更数据不冒充手工旧值', "if ds.get('freq') == CONCENTRATION_FREQ and ds.get('lastUpdate'):" in backend)
check('频率文案区分检查与新观测', '每交易日 nightly 检查并刷新最新可得港股通快照' in backend
      and '源数据可能延迟，断源沿用最近可得日期' in backend)

check('左榜展示真实source/freq', 'southboundConcentrationMeta.source' in panel
      and 'southboundConcentrationMeta.freq' in panel)
check('左榜展示真实as-of', "截至 {southboundConcentrationMeta?.lastUpdate ?? '—'}" in panel)
check('右榜展示真实source/freq', 'foreignConcentrationMeta.source' in panel
      and 'foreignConcentrationMeta.freq' in panel)
check('右榜展示真实as-of', "截至 {foreignConcentrationMeta?.lastUpdate ?? '—'}" in panel)
check('两榜展示真实note', 'southboundConcentrationMeta?.note' in panel and 'foreignConcentrationMeta?.note' in panel)
check('两榜标题及表格保留', all(x in panel for x in (
    '南下资金（国内资金）持股集中度TOP10', 'data.southbound_concentration_top10?.map',
    '外资（非国内资金）持股集中度TOP10', 'data.foreign_concentration_top10?.map')))
check('CCASS/DI锚点与模块保留', all(x in panel for x in (
    'id="ccass-foreign"', '外资托管持股动向（CCASS 月末快照）', 'id="di-foreign"', '外资机构增减仓（权益披露）')))
check('独立说明卡保留未扩大修改', '如何理解内外资分歧' in panel and 'Activity, TrendingUp' in panel)
check('前两轮删除内容未恢复', all(x not in active_frontend for x in (
    '内外资分歧最大十大标的', '个股双向流向对比', '南向资金净买入 vs 国际中介净卖出 · 2025年6月')))
check('北向和机构买卖模块保留', all(x in panel for x in (
    '北向资金近三个月净流入最多TOP10', '外资机构买入TOP10详细（A+H股全市场）')))
types_text = (ROOT / 'src/hooks/useFundData.ts').read_text(encoding='utf-8')
check('共享两榜与dataSources类型契约保留', all(x in types_text for x in (
    'southbound_concentration_top10?: Array<', 'foreign_concentration_top10?: Array<',
    'dataSources?: Record<string, {')))

check('workflow逐字节未改', workflow == workflow_base)
check('schedule未改且仍调用现有更新器', b"37 11 * * 1-5" in workflow and b'python scripts/update_data.py' in workflow)
check('未新增Kimi调度或dispatch', 'manualDispatch' not in backend and 'workflow_dispatch' not in backend)
check('实时main预检已记录', preflight['head'] and preflight['headTree'] and not preflight['manualDispatch'])
for path, state in preflight['fundData'].items():
    sha = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    check('生产JSON未改:' + path, sha == state['localSha256'], sha)

ids = re.findall(r'id=["\']([A-Za-z0-9_-]+)["\']', active_frontend)
hrefs = re.findall(r'href=["\']#([^"\']*)["\']', active_frontend)
check('静态页内锚点均有目标', all(target and target in ids for target in hrefs), hrefs)
check('CCASS/DI锚点全局唯一', ids.count('ccass-foreign') == 1 and ids.count('di-foreign') == 1)
fixed_widths = re.findall(r'(?<![-\w])w-\[(\d+)px\]|(?<!min-)(?<!max-)width:\s*(\d+)px', panel)
oversized = [int(a or b) for a, b in fixed_widths if int(a or b) > 375]
check('桌面看板无新增超宽固定元素', not oversized, oversized)
check('既有宽表仍由横向滚动容器承接', panel.count('min-w-[560px]') == 1
      and panel.count('min-w-[640px]') == 1 and panel.count('overflow-x-auto') >= 2)
check('入口viewport保留', '<meta name="viewport"' in (ROOT / 'index.html').read_text(encoding='utf-8'))

passed = sum(item['passed'] for item in checks)
production = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in DATA}
result = {
    'task': 'daily-tables-1141', 'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
    'allPassed': passed == len(checks), 'checksPassed': passed, 'checksTotal': len(checks),
    'failed': [item['name'] for item in checks if not item['passed']], 'checks': checks,
    'productionFundDataSha256': production, 'manualDispatch': False, 'productionDataRegenerated': False,
    'workflowModified': False, 'scheduleModified': False,
}
(ROOT / 'zz_daily_tables_1141_regress.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {key: result[key] for key in ('task', 'allPassed', 'checksPassed', 'checksTotal', 'failed',
                                        'productionFundDataSha256', 'manualDispatch', 'productionDataRegenerated')}
(ROOT / 'zz_daily_tables_1141_regress_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['allPassed'] else 1)
