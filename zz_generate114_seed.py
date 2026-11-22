# -*- coding: utf-8 -*-
"""任务114首批种子：从固定SHA真实样本经通用登记/推进函数生成，禁止手写突破结果。"""
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import update_data as ud
import pattern_history as ph

SOURCE = ROOT / 'zz_audit100_current_rows_full.json'
EXPECTED_SHA256 = 'f77eb8dcfcd11c0d582ea44eec9b25b67b859fd9c1de383c4dde6cbb4fa25d45'
CODE = '601985.SH'
NAME = '中国核电'
GESTATION_END = '20261013'
SAMPLE_END = '20261030'

raw = SOURCE.read_bytes()
assert hashlib.sha256(raw).hexdigest() == EXPECTED_SHA256
data = json.loads(raw)
rows = [r for r in data['rows'][CODE] if r[0] <= SAMPLE_END]
origin_rows = [r for r in rows if r[0] <= GESTATION_END]
assert origin_rows[-1][0] == GESTATION_END and rows[-1][0] == SAMPLE_END
bars = [(r[0], r[2], r[3], r[1], r[4]) for r in origin_rows]
fixed = ud._vcp_fixed_base(bars)
platform = ud._vcp_platform(
    bars, max_amp=0.105, tail_vol_max=ud.PATTERN_TAIL_VOL_MAX,
    rise_max=0.20, trend60_min=-0.10,
    dist_gate=(ud.VCP_SHOW_DIST_LO, ud.VCP_SHOW_DIST_PLAT), practical=True,
    dist_high250=(origin_rows[-1][1] / max(r[1] for r in origin_rows[-250:]) - 1) * 100)
assert fixed and fixed.get('structureFormed') and fixed.get('vcpGestation', {}).get('pass')
assert platform and platform.get('formed') and platform.get('type') == '底部平台型'
gestation = fixed['vcpGestation']
assert (fixed['startDate'], fixed['endDate'], fixed['pivot']) == ('20260828', '20261013', 9.21)
assert gestation['referenceHigh'] == 9.51
candidate = {
    'patternType': platform['type'], 'structurePath': 'fixed_base_plus_platform_structure_replay',
    'startDate': fixed['startDate'], 'endDate': fixed['endDate'], 'pivot': fixed['pivot'],
    'referenceHigh': gestation['referenceHigh'], 'referenceDate': gestation['referenceDate'],
    'referenceBasis': gestation['referenceBasis'], 'referenceSamples': gestation['referenceSamples'],
    'anchorHigh': gestation['anchorHigh'], 'invalidation': fixed.get('invalidation'),
    'sidewaysLabel': gestation['sidewaysLabel'], 'sidewaysScore': gestation['sidewaysScore'],
    'dailyTrend': fixed['dailyTrend'], 'vcpGestation': gestation,
    'originQualificationNote': (
        '底部平台型结构突破回放；仅价格结构回放，不冒充当时正式入选。'
        '20261013任务113日线严格多头门未通过，正式底部资金/估值资格也未据此认定。'),
}
history = ph.empty_history()
history['coverage'] = {
    'kind': 'runtime_plus_verified_seed', 'fullMarketComplete': False,
    'note': '首批仅含中国核电已验证底部平台型结构突破事件；不是全市场全历史归档，未覆盖区间不伪造历史。',
    'sourceFile': SOURCE.name, 'sourceSha256': EXPECTED_SHA256,
    'sampleStart': rows[0][0], 'sampleEnd': SAMPLE_END,
    'originFormalAdmission': False,
    'replayMethod': 'register_gestation + advance_stock；同一通用函数适用于全部股票',
}
assert ph.register_gestation(history, CODE, NAME, candidate, GESTATION_END, origin_formal=False)
all_bars = [(r[0], r[2], r[3], r[1], r[4]) for r in rows]
active = ph.advance_stock(history, CODE, NAME, all_bars)
assert active is None  # 到样本截止已到期，但事件必须持久化保留。
episodes = history['stocks'][CODE]['episodes']
assert len(episodes) == 1
episode = episodes[0]
assert (episode['breakoutDate'], episode['pivot'], episode['referenceHigh']) == ('20261015', 9.21, 9.51)
assert (episode['breakoutHigh'], episode['breakoutClose']) == (9.52, 9.41)
assert episode['originFormalAdmission'] is False
assert ph.trading_day_lifecycle([b[0] for b in all_bars], '20261015')['exitDate'] == '20261029'
history['generatedBy'] = 'zz_generate114_seed.py'
out = ROOT / 'scripts/pattern_episode_seed.json'
out.write_text(json.dumps(history, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
# 从磁盘重新加载并按三个PIT日前缀重放，验证种子不是不可重放的静态展示标签。
reloaded = ph.load_history({})
replay = {}
for date in ('20261013', '20261014', '20261015', '20261028', '20261029'):
    prefix = [b for b in all_bars if b[0] <= date]
    current = ph.advance_stock(reloaded, CODE, NAME, prefix)
    replay[date] = {
        'active': bool(current), 'breakoutDate': current and current['breakoutDate'],
        'lifecycle': ph.trading_day_lifecycle([b[0] for b in prefix], '20261015'),
    }
assert replay['20261013']['active'] is False and replay['20261014']['active'] is False
assert replay['20261015']['breakoutDate'] == '20261015'
assert replay['20261028']['lifecycle']['breakoutAge'] == 9
assert replay['20261028']['active'] is True
assert replay['20261029']['lifecycle']['breakoutAge'] == 10
assert replay['20261029']['active'] is False
result = {
    'task': 114, 'seed': 'scripts/pattern_episode_seed.json',
    'seedSha256': hashlib.sha256(out.read_bytes()).hexdigest(),
    'sourceSha256': EXPECTED_SHA256, 'episode': episode, 'replay': replay,
    'generatedByGenericFunctions': True, 'productionDataRegenerated': False,
}
(ROOT / 'zz_task114_seed_verification.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
