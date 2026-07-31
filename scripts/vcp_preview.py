# -*- coding: utf-8 -*-
"""VCP 板块-龙头共振监测 —— 本地验收样张生成器（不入库部署）。

用法：python scripts/vcp_preview.py   （可重复运行，缓存断点续抓）
产出：scripts/cache/vcp_cache.json（数据缓存）+ 工作区 vcp-preview.html（自包含样张）

口径：
- 龙头：申万行业指数成分中流通市值前 5（剔除 ST、上市不足 60 交易日）
- 20日滚动波动率 = 日收益 std × √244（年化%）；年分位 = 近244交易日该序列中 ≤当前值 的占比
- 振幅收窄比 = 近10日均(high/low-1) ÷ 近60日均值；<0.75 窄幅
- 量能收缩比 = 近5日均量 ÷ 近60日均量；<0.7 缩量
- 板块：SW 行业指数日线的 20日波动率年分位 + 成交额收缩比（近5日均额÷近60日均额）
- 🟢强共振：板块分位<25% 且 5 龙头中 ≥3 只同时窄幅+缩量；=2 只 → 🟡观察；其余 ⚪
- 概念板块：fund_data.json conceptSectors 15 个，走同花顺 ths_index/ths_member/ths_daily
"""
import importlib.util
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta

import tushare as ts

TOKEN = os.environ.get('TUSHARE_TOKEN', '')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 仓库根
CACHE_PATH = os.path.join(BASE, 'scripts', 'cache', 'vcp_cache.json')
FUND_DATA_PATH = os.path.join(BASE, 'public', 'fund_data.json')
HTML_OUT = os.environ.get('VCP_HTML_OUT',
                          r'C:\Users\Administrator\Documents\kimi\workspace\vcp-preview.html')
API_DELAY = float(os.environ.get('API_DELAY', '1.5'))
BACK_CAL_DAYS = 420       # 日线回溯日历日（覆盖 244 个滚动20日波动率点）
MIN_LIST_CAL_DAYS = 90    # 上市不足约 60 交易日剔除
VOL_WIN, VOL_YEAR = 20, 244
AMP_NARROW = 0.75
VOL_SHRINK = 0.7
SECTOR_LOW_PCT = 25.0


def load_cache():
    try:
        with open(CACHE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(c):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    tmp = CACHE_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(c, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)


def api(pro, fn, **kw):
    time.sleep(API_DELAY)
    return getattr(pro, fn)(**kw)


def rolling_vol_pct(closes):
    """closes: 升序收盘价 → (当前年化波动率%, 年分位%)，数据不足返回 (None, None)"""
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1] > 0]
    if len(rets) < VOL_WIN + 60:
        return None, None
    series = []
    for i in range(VOL_WIN, len(rets) + 1):
        w = rets[i - VOL_WIN:i]
        m = sum(w) / len(w)
        var = sum((x - m) ** 2 for x in w) / (len(w) - 1)
        series.append(math.sqrt(var) * math.sqrt(VOL_YEAR) * 100)
    series = series[-VOL_YEAR:]
    cur = series[-1]
    pct = sum(1 for v in series if v <= cur) / len(series) * 100
    return round(cur, 1), round(pct, 1)


def stock_metrics(rows):
    """rows: 升序 [date, close, high, low, vol] → 指标 dict"""
    closes = [r[1] for r in rows]
    vol, pct = rolling_vol_pct(closes)
    amps = [r[2] / r[3] - 1 for r in rows if r[3] > 0]
    vols = [r[4] for r in rows]
    if len(amps) < 60 or len(vols) < 60 or vol is None:
        return None
    amp_ratio = (sum(amps[-10:]) / 10) / (sum(amps[-60:]) / 60) if sum(amps[-60:]) > 0 else None
    vol_ratio = (sum(vols[-5:]) / 5) / (sum(vols[-60:]) / 60) if sum(vols[-60:]) > 0 else None
    if amp_ratio is None or vol_ratio is None:
        return None
    return {
        'vol20': vol, 'volPct': pct,
        'ampRatio': round(amp_ratio, 2), 'volRatio': round(vol_ratio, 2),
        'narrow': amp_ratio < AMP_NARROW, 'shrink': vol_ratio < VOL_SHRINK,
    }


def index_metrics(rows):
    """rows: 升序 [date, close, amount] → (vol20, volPct, amtRatio)；无成交额(概念指数)则 amtRatio=None"""
    closes = [r[1] for r in rows]
    amts = [r[2] for r in rows]
    vol, pct = rolling_vol_pct(closes)
    if vol is None:
        return None
    if len(amts) >= 60 and sum(amts[-60:]) > 0:
        amt_ratio = round((sum(amts[-5:]) / 5) / (sum(amts[-60:]) / 60), 2)
    else:
        amt_ratio = None
    return {'vol20': vol, 'volPct': pct, 'amtRatio': amt_ratio}


# ── 数据抓取（全部带缓存续传） ─────────────────────────────────

def ensure_basics(pro, c):
    if c.get('trade_date'):
        return
    today = datetime.now().strftime('%Y%m%d')
    cal = api(pro, 'trade_cal', exchange='SSE', is_open='1',
              start_date=(datetime.now() - timedelta(days=10)).strftime('%Y%m%d'), end_date=today)
    opens = sorted(str(x) for x in cal['cal_date'])
    # 最新交易日盘中/更新前数据可能未发布：逐日回探到首个有 daily_basic 数据的日期
    td = None
    for d in reversed(opens):
        df = api(pro, 'daily_basic', trade_date=d, fields='ts_code,trade_date,circ_mv')
        if df is not None and len(df) > 0:
            td = d
            break
        print('daily_basic empty for', d, ', fallback')
    if not td:
        raise RuntimeError('no trading data available in last 10 days')
    c['trade_date'] = td
    print('trade_date =', c['trade_date'])
    save_cache(c)


def ensure_sw_list(pro, c):
    if c.get('sw_list'):
        return
    df = api(pro, 'index_classify', level='L1', src='SW2021')
    c['sw_list'] = [{'code': r['index_code'], 'name': r['industry_name']} for _, r in df.iterrows()]
    print('SW L1:', len(c['sw_list']))
    save_cache(c)


def ensure_stock_basic(pro, c):
    if c.get('stock_info'):
        return
    df = api(pro, 'stock_basic', exchange='', list_status='L', fields='ts_code,name,list_date')
    c['stock_info'] = {r['ts_code']: {'name': r['name'], 'list_date': str(r['list_date'])}
                       for _, r in df.iterrows()}
    print('stock_basic:', len(c['stock_info']))
    save_cache(c)


def ensure_circ_mv(pro, c):
    if c.get('circ_mv'):
        return
    df = api(pro, 'daily_basic', trade_date=c['trade_date'], fields='ts_code,trade_date,circ_mv')
    c['circ_mv'] = {r['ts_code']: float(r['circ_mv']) / 1e4   # 万元→亿
                    for _, r in df.iterrows() if r['circ_mv'] == r['circ_mv']}
    print('circ_mv:', len(c['circ_mv']))
    save_cache(c)


def ensure_sw_members(pro, c):
    c.setdefault('sw_members', {})
    for s in c['sw_list']:
        if s['code'] in c['sw_members']:
            continue
        df = api(pro, 'index_member', index_code=s['code'])
        cur = [r['con_code'] for _, r in df.iterrows()
               if str(r.get('out_date')) in ('None', 'nan', 'NaT', '')]
        c['sw_members'][s['code']] = cur
        print('members', s['code'], s['name'], len(cur))
        save_cache(c)


CONCEPT_ALIAS = {           # fund_data 概念名 → 同花顺指数名（无完全同名时的近似映射）
    'AI算力': '东数西算(算力)',
    '智能驾驶': '无人驾驶',
    '卫星互联网': '卫星概念',
    '光伏': '光伏概念',
}


def ensure_concepts(pro, c):
    """fund_data.json 的 15 个概念 → ths 代码/成分；接口失败则记录原因跳过"""
    if c.get('concepts_done'):
        return
    c.setdefault('concepts', [])
    c.setdefault('ths_members', {})
    try:
        fd = json.load(open(FUND_DATA_PATH, encoding='utf-8'))
        names = [x['name'] for x in fd.get('conceptSectors', [])]
        c['concept_names'] = names
        if not c.get('ths_index'):
            df = api(pro, 'ths_index')
            c['ths_index'] = {r['name']: r['ts_code'] for _, r in df.iterrows()}
            save_cache(c)
        for n in names:
            code = c['ths_index'].get(n)
            if not code and n in CONCEPT_ALIAS:
                code = c['ths_index'].get(CONCEPT_ALIAS[n])
                if code:
                    print('concept alias:', n, '→', CONCEPT_ALIAS[n], code)
            if not code:
                print('concept no match:', n)
                continue
            if code not in c['ths_members']:
                df = api(pro, 'ths_member', ts_code=code)
                c['ths_members'][code] = [r['con_code'] for _, r in df.iterrows()]
                print('ths_member', n, code, len(c['ths_members'][code]))
                save_cache(c)
            c['concepts'].append({'name': n, 'code': code})
        c['concepts_done'] = True
        save_cache(c)
    except Exception as e:
        c['concepts_error'] = str(e)[:200]
        c['concepts_done'] = True
        save_cache(c)
        print('concepts skipped:', e)


def _pick_leaders(c, member_codes):
    info = c['stock_info']
    mv = c['circ_mv']
    limit = (datetime.strptime(c['trade_date'], '%Y%m%d')
             - timedelta(days=MIN_LIST_CAL_DAYS)).strftime('%Y%m%d')
    cands = []
    for code in member_codes:
        si = info.get(code)
        if not si or 'ST' in si['name'].upper():
            continue
        if si['list_date'] > limit:
            continue
        v = mv.get(code)
        if v:
            cands.append((code, v))
    cands.sort(key=lambda x: -x[1])
    return [code for code, _ in cands[:5]]


def ensure_leaders(c):
    if c.get('leaders'):
        return
    if not c.get('circ_mv'):
        raise RuntimeError('circ_mv empty, refuse to pick leaders')  # 防空数据固化进缓存
    leaders = {}
    for s in c['sw_list']:
        leaders[s['code']] = _pick_leaders(c, c['sw_members'].get(s['code'], []))
    for con in c.get('concepts', []):
        leaders[con['code']] = _pick_leaders(c, c['ths_members'].get(con['code'], []))
    c['leaders'] = leaders
    print('leaders picked:', sum(len(v) for v in leaders.values()))
    save_cache(c)


def ensure_index_daily(pro, c):
    """行业指数走 index_daily；概念指数走 ths_daily（无成交额，板块量比记 None）"""
    c.setdefault('index_daily', {})
    start = (datetime.strptime(c['trade_date'], '%Y%m%d')
             - timedelta(days=BACK_CAL_DAYS)).strftime('%Y%m%d')
    targets = [s['code'] for s in c['sw_list']]
    for code in targets:
        if code in c['index_daily']:
            continue
        df = api(pro, 'index_daily', ts_code=code, start_date=start, end_date=c['trade_date'])
        rows = [[str(r['trade_date']), float(r['close']), float(r.get('amount') or 0)]
                for _, r in df.iterrows()]
        rows.sort()
        c['index_daily'][code] = rows
        print('index_daily', code, len(rows))
        save_cache(c)
    for con in c.get('concepts', []):
        code = con['code']
        if code in c['index_daily']:
            continue
        try:
            df = api(pro, 'ths_daily', ts_code=code, start_date=start, end_date=c['trade_date'])
            rows = [[str(r['trade_date']), float(r['close']),
                     float(r['amount']) if 'amount' in df.columns and r.get('amount') == r.get('amount') else 0]
                    for _, r in df.iterrows()]
            rows.sort()
            c['index_daily'][code] = rows
            print('ths_daily', con['name'], code, len(rows), 'amount' if rows and rows[-1][2] else 'no-amount')
        except Exception as e:
            print('ths_daily FAILED', con['name'], str(e)[:80])
        save_cache(c)


def ensure_stock_daily(pro, c):
    c.setdefault('stock_daily', {})
    start = (datetime.strptime(c['trade_date'], '%Y%m%d')
             - timedelta(days=BACK_CAL_DAYS)).strftime('%Y%m%d')
    need = sorted({code for v in c['leaders'].values() for code in v}
                  - set(c['stock_daily']))
    print('stock_daily to fetch:', len(need))
    for i, code in enumerate(need):
        try:
            df = api(pro, 'daily', ts_code=code, start_date=start, end_date=c['trade_date'])
            rows = [[str(r['trade_date']), float(r['close']), float(r['high']),
                     float(r['low']), float(r['vol'])] for _, r in df.iterrows()]
            rows.sort()
            c['stock_daily'][code] = rows
        except Exception as e:
            print('daily FAILED', code, str(e)[:80])
        if (i + 1) % 10 == 0 or i == len(need) - 1:
            print(f'  stock_daily {i + 1}/{len(need)}')
            save_cache(c)
    save_cache(c)


# ── 计算与渲染 ─────────────────────────────────────────────────

def compute_results(c):
    info = c['stock_info']
    sectors = ([{'code': s['code'], 'name': s['name'], 'kind': '行业'} for s in c['sw_list']]
               + [{'code': x['code'], 'name': x['name'], 'kind': '概念'} for x in c.get('concepts', [])])
    out = []
    for s in sectors:
        im = index_metrics(c['index_daily'].get(s['code'], []))
        if not im:
            continue
        leaders = []
        for code in c['leaders'].get(s['code'], []):
            m = stock_metrics(c['stock_daily'].get(code, []))
            if not m:
                continue
            leaders.append({'code': code, 'name': info.get(code, {}).get('name', code),
                            'mv': round(c['circ_mv'].get(code, 0), 0), **m})
        n_hit = sum(1 for l in leaders if l['narrow'] and l['shrink'])
        if im['volPct'] < SECTOR_LOW_PCT and n_hit >= 3:
            sig = '🟢'
        elif im['volPct'] < SECTOR_LOW_PCT and n_hit == 2:
            sig = '🟡'
        else:
            sig = '⚪'
        out.append({'code': s['code'], 'name': s['name'], 'kind': s['kind'],
                    'vol20': im['vol20'], 'volPct': im['volPct'],
                    'amtRatio': im['amtRatio'], 'nHit': n_hit, 'nLeaders': len(leaders),
                    'signal': sig, 'leaders': leaders})
    out.sort(key=lambda x: x['volPct'])
    return out


def load_l1_flows():
    """三档净流入：sector_history.json + update_data 的 SECTOR_TO_L1（不新增接口）"""
    spec = importlib.util.spec_from_file_location(
        'upd', os.path.join(BASE, 'scripts', 'update_data.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    hist = json.load(open(os.path.join(BASE, 'scripts', 'cache', 'sector_history.json'),
                          encoding='utf-8'))
    days = sorted(hist['days'])[-20:]
    agg = {}
    for d in days:
        for ind, s in hist['days'][d]['sectors'].items():
            l1 = m.SECTOR_TO_L1.get(ind)
            if not l1:
                continue
            agg.setdefault(l1, []).append(s.get('net', 0.0))
    rows = []
    for l1, nets in agg.items():
        n5, n10, n20 = sum(nets[-5:]), sum(nets[-10:]), sum(nets[-20:])
        p5, p10 = n5 / 5, (n10 - n5) / 5
        if n5 < 0 and n10 < 0 and n20 < 0:
            tag = '持续流出'
        elif n5 > 0 and n10 <= 0:
            tag = '拐点·转流入'
        elif n5 < 0 and n10 >= 0:
            tag = '拐点·转流出'
        elif n5 > 0 and p5 > p10 * 1.2:
            tag = '加速流入'
        elif n5 > 0:
            tag = '减速流入'
        else:
            tag = '反复'
        rows.append({'name': l1, 'net5': round(n5, 1), 'net10': round(n10, 1),
                     'net20': round(n20, 1), 'tag': tag})
    rows.sort(key=lambda x: -x['net5'])
    return rows, days[-1]


def fmt_pct_cell(v, good_low=True):
    cls = 'good' if (v < 25 if good_low else v > 75) else ('mid' if (v < 50 if good_low else v > 50) else '')
    return f'<td class="num {cls}">{v:.1f}%</td>'


def render_html(results, flows, flow_date, trade_date, path, concepts_error=None,
                concept_short=None):
    td = f'{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}'
    green = [r for r in results if r['signal'] == '🟢']
    yellow = [r for r in results if r['signal'] == '🟡']
    white = [r for r in results if r['signal'] == '⚪'][:5]   # 分位最低的前5名作对照
    show = green + yellow + white

    def leader_rows(ls):
        trs = []
        for l in ls:
            trs.append(
                f"<tr class='sub'>"
                f"<td>{l['name']}<span class='dim'>{l['code']}</span></td>"
                f"<td class='num'>{l['vol20']:.1f}%</td>"
                f"{fmt_pct_cell(l['volPct'])}"
                f"<td class='num {'good' if l['ampRatio'] < AMP_NARROW else ''}'>{l['ampRatio']:.2f}</td>"
                f"<td class='num {'good' if l['volRatio'] < VOL_SHRINK else ''}'>{l['volRatio']:.2f}</td>"
                f"<td>{'✅窄幅' if l['narrow'] else '<span class=dim>—</span>'}</td>"
                f"<td>{'✅缩量' if l['shrink'] else '<span class=dim>—</span>'}</td>"
                f"</tr>")
        return ''.join(trs)

    main_rows = []
    for r in show:
        reps = [l for l in r['leaders'] if l['narrow'] and l['shrink']] or r['leaders'][:1]
        rep_txt = '、'.join(f"{l['name']}" for l in reps[:2])
        rid = 'row-' + r['code'].replace('.', '')
        amt = f"{r['amtRatio']:.2f}" if r['amtRatio'] else '<span class=dim>无</span>'
        main_rows.append(
            f"<tr class='main' onclick=\"document.getElementById('{rid}').classList.toggle('open')\">"
            f"<td><span class='kind kind-{r['kind']}'>{r['kind']}</span>{r['name']}</td>"
            f"<td class='num'>{r['vol20']:.1f}%</td>"
            f"{fmt_pct_cell(r['volPct'])}"
            f"<td class='num {'good' if r['amtRatio'] and r['amtRatio'] < VOL_SHRINK else ''}'>{amt}</td>"
            f"<td class='num'>{r['nHit']}/{r['nLeaders']}</td>"
            f"<td class='sig'>{r['signal']}</td>"
            f"<td>{rep_txt}</td></tr>"
            f"<tr id='{rid}' class='detail'><td colspan='7'><table class='inner'>"
            f"<thead><tr><th>股票</th><th>20日波动率</th><th>年分位</th><th>振幅比</th><th>量比</th><th>窄幅&lt;0.75</th><th>缩量&lt;0.7</th></tr></thead>"
            f"<tbody>{leader_rows(r['leaders'])}</tbody></table></td></tr>")

    tag_cls = {'加速流入': 'up', '减速流入': 'up2', '拐点·转流入': 'warn', '拐点·转流出': 'warn',
               '持续流出': 'down', '反复': ''}
    flow_rows = ''.join(
        f"<tr><td>{f['name']}</td>"
        f"<td class='num {'up' if f['net5'] > 0 else 'down'}'>{f['net5']:+.1f}</td>"
        f"<td class='num {'up' if f['net10'] > 0 else 'down'}'>{f['net10']:+.1f}</td>"
        f"<td class='num {'up' if f['net20'] > 0 else 'down'}'>{f['net20']:+.1f}</td>"
        f"<td><span class='tag {tag_cls.get(f['tag'], '')}'>{f['tag']}</span></td></tr>"
        for f in flows)

    concept_note = (f"<p class='warn-note'>概念板块未纳入：{concepts_error}</p>" if concepts_error else '')
    if concept_short:
        concept_note += (f"<p class='warn-note'>概念指数历史不足一年（ths_daily 仅约 6 个交易日，无法计算年分位）："
                         f"{'、'.join(concept_short)}</p>")
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VCP 板块-龙头共振监测 · 验收样张</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #0b1220; color: #cbd5e1; font: 13px/1.6 -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; padding: 20px; }}
.wrap {{ max-width: 1080px; margin: 0 auto; }}
.banner {{ background: linear-gradient(90deg, #164e63, #1e293b); border: 1px solid #0e7490; border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; }}
.banner b {{ color: #67e8f9; font-size: 15px; }}
.banner .meta {{ color: #94a3b8; font-size: 11px; margin-top: 2px; }}
.badge-trial {{ background: #f59e0b; color: #0b1220; font-weight: 700; font-size: 10px; border-radius: 4px; padding: 1px 6px; margin-left: 8px; vertical-align: 2px; }}
h2 {{ color: #e2e8f0; font-size: 14px; margin: 18px 0 8px; }}
.card {{ background: #111a2e; border: 1px solid #1e293b; border-radius: 10px; padding: 12px; overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; min-width: 760px; }}
th {{ color: #64748b; font-weight: 500; text-align: left; padding: 6px 8px; border-bottom: 1px solid #1e293b; white-space: nowrap; }}
td {{ padding: 6px 8px; border-bottom: 1px solid #16203a; white-space: nowrap; }}
tr.main {{ cursor: pointer; }}
tr.main:hover {{ background: #16203a; }}
tr.detail {{ display: none; }}
tr.detail.open {{ display: table-row; }}
table.inner {{ min-width: 0; margin: 4px 0 8px; background: #0d1526; border-radius: 6px; }}
table.inner th {{ color: #475569; font-size: 11px; }}
tr.sub td {{ border-bottom: 1px solid #131c33; font-size: 12px; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.good {{ color: #34d399; font-weight: 600; }}
.mid {{ color: #fbbf24; }}
.up {{ color: #f87171; }}
.up2 {{ color: #fb923c; }}
.down {{ color: #34d399; }}
.warn {{ color: #fbbf24; }}
.dim {{ color: #475569; font-size: 10px; margin-left: 4px; }}
.sig {{ font-size: 15px; }}
.kind {{ font-size: 9px; border-radius: 3px; padding: 1px 4px; margin-right: 5px; }}
.kind-行业 {{ background: #164e63; color: #67e8f9; }}
.kind-概念 {{ background: #4c1d95; color: #c4b5fd; }}
.tag {{ font-size: 10px; border-radius: 3px; padding: 1px 6px; background: #1e293b; }}
.tag.up {{ background: #450a0a; color: #f87171; }}
.tag.up2 {{ background: #431407; color: #fb923c; }}
.tag.down {{ background: #022c22; color: #34d399; }}
.tag.warn {{ background: #422006; color: #fbbf24; }}
.note {{ color: #64748b; font-size: 11px; margin-top: 8px; }}
.warn-note {{ color: #fbbf24; font-size: 11px; margin-top: 8px; }}
.legend {{ color: #94a3b8; font-size: 11px; margin: 6px 0 0; }}
</style></head><body><div class="wrap">
<div class="banner"><b>VCP 板块-龙头共振监测</b><span class="badge-trial">验收样张 · 未上线</span>
<div class="meta">数据日期 {td}（Tushare 真实数据） · 31 个申万一级行业 + {len([r for r in results if r['kind'] == '概念'])} 个概念板块 · 每板块流通市值前 5 龙头（剔除 ST/次新）</div></div>

<h2>共振信号（按板块波动率年分位升序，🟢{len(green)} 🟡{len(yellow)}，另列分位最低的 ⚪ 前 5 名对照；点击行展开龙头明细）</h2>
<div class="card"><table>
<thead><tr><th>板块</th><th>板块20日波动率</th><th>波动率年分位</th><th>成交收缩比</th><th>窄幅+缩量龙头</th><th>信号</th><th>代表龙头</th></tr></thead>
<tbody>{''.join(main_rows)}</tbody></table>
<p class="legend">🟢 强共振 = 板块波动率年分位&lt;25% 且 ≥3 只龙头同时窄幅(振幅比&lt;0.75)+缩量(量比&lt;0.7)；🟡 观察 = 同条件 2 只；龙头行内绿色数值 = 达到阈值</p>
{concept_note}</div>

<h2>三档净流入预览（申万一级，近5/10/20日主力净流入，亿元 · 截至 {flow_date[:4]}-{flow_date[4:6]}-{flow_date[6:]}）</h2>
<div class="card"><table>
<thead><tr><th>板块</th><th>近5日</th><th>近10日</th><th>近20日</th><th>资金节奏</th></tr></thead>
<tbody>{flow_rows}</tbody></table>
<p class="note">口径：sector_history 二级行业净流入按申万一级归并求和；节奏=近5日日均 vs 前5日日均比较（加速流入/减速流入/拐点/持续流出）。红=净流入 绿=净流出。</p></div>

<p class="note">生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M')} · scripts/vcp_preview.py · 本文件为本地验收样张，未进入 git 部署流程</p>
</div></body></html>"""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    print('HTML written:', path)


def main():
    if not TOKEN:
        print('ERROR: TUSHARE_TOKEN not set')
        sys.exit(1)
    ts.set_token(TOKEN)
    pro = ts.pro_api()
    c = load_cache()
    ensure_basics(pro, c)
    ensure_sw_list(pro, c)
    ensure_stock_basic(pro, c)
    ensure_circ_mv(pro, c)
    ensure_sw_members(pro, c)
    ensure_concepts(pro, c)
    ensure_leaders(c)
    ensure_index_daily(pro, c)
    ensure_stock_daily(pro, c)

    results = compute_results(c)
    computed_codes = {r['code'] for r in results}
    concept_short = [x['name'] for x in c.get('concepts', [])
                     if x['code'] not in computed_codes and len(c['index_daily'].get(x['code'], [])) < 100]
    flows, flow_date = load_l1_flows()
    render_html(results, flows, flow_date, c['trade_date'], HTML_OUT,
                concepts_error=c.get('concepts_error'), concept_short=concept_short)
    print('\n=== SUMMARY ===')
    for r in results:
        if r['signal'] != '⚪':
            print(r['signal'], r['kind'], r['name'], f"volPct={r['volPct']}", f"hit={r['nHit']}/{r['nLeaders']}",
                  'leaders=', [(l['name'], l['volPct'], l['ampRatio'], l['volRatio']) for l in r['leaders']])


if __name__ == '__main__':
    main()
