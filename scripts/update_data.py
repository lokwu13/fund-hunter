#!/usr/bin/env python3
"""
Fund Hunter - Daily Data Updater (Batch Mode)
Uses Tushare Pro API to fetch market data and generate fund_data.json
Triggered by GitHub Actions daily at 19:00 CST (after market close)

Batch requests reduce API calls to avoid IP limits.
"""

import os
import sys
import json
import time
import requests
import tushare as ts

# Delay between API calls to avoid IP rate limits
API_DELAY = 1.5  # seconds
import pandas as pd
from datetime import datetime, timedelta

# ── Configuration ──
TUSHARE_TOKEN = os.environ.get('TUSHARE_TOKEN', '')
OUTPUT_PATH = os.environ.get('OUTPUT_PATH', 'public/fund_data.json')

# Index codes: ts_code → internal key
INDICES = {
    '000001.SH': {'key': 'shIndex', 'name': '上证指数'},
    '399001.SZ': {'key': 'szIndex', 'name': '深证成指'},
    '000300.SH': {'key': 'hs300', 'name': '沪深300'},
    '399006.SZ': {'key': 'cyIndex', 'name': '创业板指'},
}

# Stocks: 用户自己的持仓(hold) + 观察股(watch)，其它股票不再跟踪
# watchPrice 字段保留以兼容旧数据/引用（前端当前未使用，统一填 0）
STOCKS = {
    # ── 持股（个股账户）──
    '600276.SH': {'name': '恒瑞医药', 'industry': '化学制药', 'group': 'hold', 'watchPrice': 0},
    '688016.SH': {'name': '心脉医疗', 'industry': '医疗保健', 'group': 'hold', 'watchPrice': 0},
    '688029.SH': {'name': '南微医学', 'industry': '医疗保健', 'group': 'hold', 'watchPrice': 0},
    '600009.SH': {'name': '上海机场', 'industry': '机场',     'group': 'hold', 'watchPrice': 0},
    # ── 观察股 ──
    '600309.SH': {'name': '万华化学', 'industry': '化工原料', 'group': 'watch', 'watchPrice': 0},
    '600406.SH': {'name': '国电南瑞', 'industry': '电气设备', 'group': 'watch', 'watchPrice': 0},
    '002216.SZ': {'name': '三全食品', 'industry': '食品',     'group': 'watch', 'watchPrice': 0},
    '000895.SZ': {'name': '双汇发展', 'industry': '食品',     'group': 'watch', 'watchPrice': 0},
    '600298.SH': {'name': '安琪酵母', 'industry': '食品',     'group': 'watch', 'watchPrice': 0},
    '002568.SZ': {'name': '百润股份', 'industry': '红黄酒',   'group': 'watch', 'watchPrice': 0},
    '601888.SH': {'name': '中国中免', 'industry': '旅游服务', 'group': 'watch', 'watchPrice': 0},
    '603259.SH': {'name': '药明康德', 'industry': '化学制药', 'group': 'watch', 'watchPrice': 0},
    '300760.SZ': {'name': '迈瑞医疗', 'industry': '医疗保健', 'group': 'watch', 'watchPrice': 0},
    '688271.SH': {'name': '联影医疗', 'industry': '医疗保健', 'group': 'watch', 'watchPrice': 0},
}

# 用户 ETF 账户（行情走 fund_daily，与 nationalETF 的 daily 不同）
MY_ETFS = {
    '159883.SZ': {'name': '永赢中证全指医疗器械ETF',   'ticker': '159883'},
    '159892.SZ': {'name': '华夏恒生生物科技ETF(QDII)', 'ticker': '159892'},
    '159265.SZ': {'name': '鹏华国证港股通消费主题ETF', 'ticker': '159265'},
    '159736.SZ': {'name': '天弘中证食品饮料ETF',       'ticker': '159736'},
    '512800.SH': {'name': '华宝中证银行ETF',           'ticker': '512800'},
}

# ETFs
ETFS = {
    '510300.SH': {'name': '华泰柏瑞沪深300ETF', 'ticker': '510300'},
    '510310.SH': {'name': '易方达沪深300ETF', 'ticker': '510310'},
    '510330.SH': {'name': '华夏沪深300ETF', 'ticker': '510330'},
    '159919.SZ': {'name': '嘉实沪深300ETF', 'ticker': '159919'},
    '510050.SH': {'name': '华夏上证50ETF', 'ticker': '510050'},
    '510500.SH': {'name': '南方中证500ETF', 'ticker': '510500'},
    '512100.SH': {'name': '华夏中证1000ETF', 'ticker': '512100'},
}


def get_trade_date(pro):
    """Get the most recent trade date."""
    today = datetime.now()
    # Try today first, then go backwards
    for i in range(7):
        date_str = (today - timedelta(days=i)).strftime('%Y%m%d')
        try:
            df = pro.trade_cal(exchange='SSE', start_date=date_str, end_date=date_str)
            if len(df) > 0 and df.iloc[0]['is_open'] == 1:
                return date_str
        except:
            pass
    return '20260721'


def fetch_indices_batch(pro, trade_date):
    """Fetch all indices; batch first, fall back to per-code (batch may return empty)."""
    time.sleep(API_DELAY)
    indices_data = {}
    ts_codes = ','.join(INDICES.keys())
    rows = []
    try:
        df = pro.index_daily(ts_code=ts_codes, start_date=trade_date, end_date=trade_date)
        rows = list(df.iterrows())
    except Exception as e:
        print(f"  Warning: Failed to fetch indices (batch): {e}")
    if not rows:
        for tc in INDICES:
            try:
                time.sleep(API_DELAY)
                df = pro.index_daily(ts_code=tc, start_date=trade_date, end_date=trade_date)
                if len(df) > 0:
                    rows.append((0, df.iloc[0]))
            except Exception as e:
                print(f"  Warning: Failed to fetch index {tc}: {e}")
    for _, row in rows:
        tc = row['ts_code']
        if tc in INDICES:
            info = INDICES[tc]
            indices_data[info['key']] = {
                'name': info['name'],
                'value': round(float(row['close']), 2),
                'change': round(float(row['pct_chg']), 2),
            }
    return indices_data


def fetch_stocks_batch(pro, trade_date):
    """Fetch all stocks in one batch request."""
    time.sleep(API_DELAY)
    stocks_data = []
    ts_codes = ','.join(STOCKS.keys())
    try:
        df = pro.daily(ts_code=ts_codes, start_date=trade_date, end_date=trade_date)
        for _, row in df.iterrows():
            tc = row['ts_code']
            if tc in STOCKS:
                info = STOCKS[tc]
                stocks_data.append({
                    'code': tc,
                    'name': info['name'],
                    'industry': info['industry'],
                    'group': info['group'],
                    'close': round(float(row['close']), 2),
                    'pctChg': round(float(row['pct_chg']), 2),
                    'vol': round(float(row['vol']) / 10000, 2),
                    'watchPrice': info['watchPrice'],
                })
    except Exception as e:
        print(f"  Warning: Failed to fetch stocks: {e}")
    return stocks_data


def fetch_etfs_batch(pro, trade_date):
    """Fetch all national-team ETFs; batch first, fall back to per-code."""
    time.sleep(API_DELAY)
    etf_data = []
    ts_codes = ','.join(ETFS.keys())
    rows = []
    try:
        df = pro.daily(ts_code=ts_codes, start_date=trade_date, end_date=trade_date)
        rows = list(df.iterrows())
    except Exception as e:
        print(f"  Warning: Failed to fetch ETFs (batch): {e}")
    if not rows:
        for tc in ETFS:
            try:
                time.sleep(API_DELAY)
                df = pro.daily(ts_code=tc, start_date=trade_date, end_date=trade_date)
                if len(df) > 0:
                    rows.append((0, df.iloc[0]))
            except Exception as e:
                print(f"  Warning: Failed to fetch ETF {tc}: {e}")
    for _, row in rows:
        tc = row['ts_code']
        if tc in ETFS:
            info = ETFS[tc]
            etf_data.append({
                'ticker': info['ticker'],
                'name': info['name'],
                'market': 'sh' if '.SH' in tc else 'sz',
                'q1Note': '',
                'close': round(float(row['close']), 3),
                'changePct': round(float(row['pct_chg']), 2),
                'preClose': round(float(row['pre_close']), 3),
            })
    return etf_data


def fetch_my_etfs(pro, trade_date):
    """Fetch user's own ETF account quotes via fund_daily.

    注意：fund_daily 不支持逗号分隔的批量 ts_code（实测批量返回空），
    因此逐只查询。
    """
    etf_data = []
    for tc, info in MY_ETFS.items():
        try:
            time.sleep(API_DELAY)
            df = pro.fund_daily(ts_code=tc, start_date=trade_date, end_date=trade_date)
            if len(df) == 0:
                continue
            row = df.iloc[0]
            etf_data.append({
                'ticker': info['ticker'],
                'name': info['name'],
                'close': round(float(row['close']), 3),
                'changePct': round(float(row['pct_chg']), 2),
                'preClose': round(float(row['pre_close']), 3),
            })
        except Exception as e:
            print(f"  Warning: Failed to fetch my ETF {tc}: {e}")
    return etf_data


# ── 公告抓取：雪球为主，巨潮兜底 ──
# 雪球接口参考 https://stock.xueqiu.com/v5/stock/f10/cn/announcement.json
# （需先 GET https://xueqiu.com/hq 拿 xq_a_token cookie，否则 401/400）。
# 注意：本机实测（2026-07）该公告路径返回 404（token 有效，其它 f10 接口正常），
# 疑似雪球已下线/迁移该接口；代码仍保留雪球为首选，若接口恢复即自动生效。
# 雪球失败时自动降级到巨潮资讯 hisAnnouncement/query（POST，需先 topSearch 取 orgId）。
# 两者都失败则该股票 items 置空，绝不让脚本崩溃。
# 另外注意：GitHub Actions 为美国机房 IP，雪球/巨潮都可能拒绝海外 IP，
# 失败时同样优雅降级为空 items。

UA_BROWSER = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')


def _xq_symbol(ts_code):
    """600276.SH → SH600276"""
    num, exch = ts_code.split('.')
    return f"{exch}{num}"


def fetch_anns_xueqiu(trade_date):
    """雪球公告（首选）。返回 {ts_code: [item, ...]}；整体失败返回 None。"""
    try:
        import requests
        session = requests.Session()
        session.headers.update({'User-Agent': UA_BROWSER, 'Referer': 'https://xueqiu.com/'})
        # 先拿 xq_a_token cookie
        session.get('https://xueqiu.com/hq', timeout=15)
        result = {}
        probe_ok = False
        for tc in STOCKS:
            try:
                time.sleep(API_DELAY)
                url = (f"https://stock.xueqiu.com/v5/stock/f10/cn/announcement.json"
                       f"?symbol={_xq_symbol(tc)}&page=1&size=10")
                r = session.get(url, timeout=15)
                if r.status_code != 200:
                    if not probe_ok:
                        print(f"  Warning: Xueqiu announcement API returned {r.status_code}; will fall back to cninfo.")
                        return None
                    continue
                probe_ok = True
                data = r.json()
                lst = (data.get('data') or {}).get('list') or []
                items = []
                for a in lst:
                    title = str(a.get('title', '')).strip()
                    decl = str(a.get('decl_date') or a.get('pub_date') or a.get('date') or '')[:10]
                    link = str(a.get('url') or a.get('pdf_url') or '')
                    if not title or not decl:
                        continue
                    item = {'type': '公告', 'date': decl, 'title': title, 'content': title}
                    if link:
                        item['url'] = link
                    items.append(item)
                result[tc] = items
            except Exception as e:
                print(f"  Warning: Xueqiu announcements failed for {tc}: {e}")
        return result if probe_ok else None
    except Exception as e:
        print(f"  Warning: Xueqiu session init failed: {e}")
        return None


def fetch_anns_cninfo(pro, trade_date):
    """巨潮资讯公告（兜底）。返回 {ts_code: [item, ...]}，单只失败即为空列表。"""
    try:
        import requests
    except Exception:
        print("  Warning: requests not installed; cninfo fallback unavailable.")
        return {}
    session = requests.Session()
    session.headers.update({
        'User-Agent': UA_BROWSER,
        'Referer': 'http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice',
        'X-Requested-With': 'XMLHttpRequest',
    })
    start = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=7)).strftime('%Y-%m-%d')
    end = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    result = {}
    for tc, info in STOCKS.items():
        items = []
        code = tc.split('.')[0]
        column = 'sse' if tc.endswith('.SH') else 'szse'
        try:
            # 1) topSearch 取 orgId（hisAnnouncement 的 stock 参数需要 code,orgId 格式）
            time.sleep(API_DELAY)
            r = session.post('http://www.cninfo.com.cn/new/information/topSearch/query',
                             data={'keyWord': code, 'maxNum': 10}, timeout=15)
            org_id = ''
            for it in r.json():
                if it.get('code') == code:
                    org_id = it.get('orgId', '')
                    break
            # 2) 查询公告
            time.sleep(API_DELAY)
            stock_param = f"{code},{org_id}" if org_id else code
            r2 = session.post('http://www.cninfo.com.cn/new/hisAnnouncement/query', data={
                'pageNum': 1, 'pageSize': 10, 'column': column, 'tabName': 'fulltext',
                'plate': '', 'stock': stock_param, 'searchkey': '', 'secid': '',
                'category': '', 'trade': '', 'seDate': f'{start}~{end}',
                'sortName': '', 'sortType': '', 'isHLtitle': 'true',
            }, timeout=15)
            anns = (r2.json().get('announcements') or [])
            seen = set()
            for a in anns:
                title = str(a.get('announcementTitle', '')).replace('<em>', '').replace('</em>', '').strip()
                ts_ms = a.get('announcementTime', 0)
                # 巨潮时间戳为北京时间零点；GitHub Actions 容器是 UTC，
                # 直接 fromtimestamp 会早一天，故显式按 UTC+8 转换
                date_fmt = (datetime.utcfromtimestamp(ts_ms / 1000) + timedelta(hours=8)).strftime('%Y-%m-%d') if ts_ms else ''
                if not title or not date_fmt:
                    continue
                key = (date_fmt, title)
                if key in seen:  # 同一公告多个 PDF 版本，去重
                    continue
                seen.add(key)
                adj = str(a.get('adjunctUrl', ''))
                item = {'type': '公告', 'date': date_fmt, 'title': title, 'content': title}
                if adj:
                    item['url'] = f"http://static.cninfo.com.cn/{adj}"
                items.append(item)
        except Exception as e:
            print(f"  Warning: cninfo announcements failed for {tc}: {e}")
        result[tc] = items
    return result


def fetch_announcements(pro, trade_date):
    """近 3 个交易日公告：雪球为主，巨潮兜底，都失败则空（脚本不崩）。"""
    anns = fetch_anns_xueqiu(trade_date)
    if anns is not None:
        print("  Announcements source: Xueqiu")
        return anns
    anns = fetch_anns_cninfo(pro, trade_date)
    print("  Announcements source: cninfo (fallback)")
    return anns


def build_holdings_news(anns_map, trade_date):
    """为 14 只股票各生成一个 holdingsNews 条目（每次运行全量覆盖，不保留旧手工数据）。

    行业信息不进 items，由前端在条目头部直接展示 industry 字段。
    公告为空则 items 为空数组。anns_map: {ts_code: [item, ...]}
    """
    entries = []
    cutoff = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=5)).strftime('%Y-%m-%d')
    for tc, info in STOCKS.items():
        items = [it for it in (anns_map.get(tc) or []) if it.get('date', '') >= cutoff]
        items.sort(key=lambda x: x['date'], reverse=True)
        entries.append({
            'stockCode': tc,
            'stockName': info['name'],
            'group': info['group'],
            'industry': info['industry'],
            'items': items,
        })
    return entries


def fetch_mainforce_flow(pro, trade_date):
    """Fetch mainforce inflow/outflow top10."""
    time.sleep(API_DELAY)
    inflow, outflow = [], []
    try:
        df_mf = pro.moneyflow(trade_date=trade_date)
        if len(df_mf) == 0:
            return inflow, outflow

        # Get stock names in batch
        all_codes = df_mf['ts_code'].tolist()
        # Tushare stock_basic doesn't support batch ts_code query well,
        # so we load all stock basics once
        df_basic = pro.stock_basic(exchange='', list_status='L')
        name_map = dict(zip(df_basic['ts_code'], df_basic['name']))
        ind_map = dict(zip(df_basic['ts_code'], df_basic['industry']))

        df_mf['name'] = df_mf['ts_code'].map(name_map)
        df_mf['industry'] = df_mf['ts_code'].map(ind_map)

        # Inflow top10
        df_in = df_mf[df_mf['net_mf_amount'] > 0].nlargest(10, 'net_mf_amount')
        for _, row in df_in.iterrows():
            name = row['name'] if pd.notna(row['name']) else row['ts_code']
            concept = row['industry'] if pd.notna(row['industry']) else '-'
            inflow.append({
                'name': name,
                'code': row['ts_code'],
                'concept': concept,
                'sector': concept if concept else '其他',
                'amount': f"+{round(float(row['net_mf_amount']) / 10000, 2)}亿",
            })

        # Outflow top10
        df_out = df_mf[df_mf['net_mf_amount'] < 0].nsmallest(10, 'net_mf_amount')
        for _, row in df_out.iterrows():
            name = row['name'] if pd.notna(row['name']) else row['ts_code']
            concept = row['industry'] if pd.notna(row['industry']) else '-'
            outflow.append({
                'name': name,
                'code': row['ts_code'],
                'concept': concept,
                'sector': concept if concept else '其他',
                'amount': f"{round(float(row['net_mf_amount']) / 10000, 2)}亿",
            })
    except Exception as e:
        print(f"  Warning: Failed to fetch mainforce flow: {e}")
    return inflow, outflow


def fetch_hot_fund_navs(pro, trade_date, existing):
    """用 pro.fund_nav 逐只更新 hotFundNavs 的最新净值。

    接口已实测有权限。每只取近 10 日净值，用最新一条更新
    nav/accumNav/date；change 为最新单位净值相对前一净值日的绝对变动（小数）。
    取不到数据的基金保留旧值（取到才覆盖）。
    """
    if not existing:
        return existing
    start = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=10)).strftime('%Y%m%d')
    updated = []
    for item in existing:
        code = item.get('code', '')
        if not code:
            updated.append(item)
            continue
        try:
            time.sleep(API_DELAY)
            df = pro.fund_nav(ts_code=code, start_date=start, end_date=trade_date)
            if df is None or len(df) == 0:
                updated.append(item)
                continue
            df = df.sort_values('nav_date').reset_index(drop=True)
            last = df.iloc[-1]
            new_item = dict(item)
            if pd.notna(last.get('unit_nav')):
                new_item['nav'] = round(float(last['unit_nav']), 4)
            if pd.notna(last.get('accum_nav')):
                new_item['accumNav'] = round(float(last['accum_nav']), 4)
            new_item['date'] = str(last['nav_date'])
            if len(df) >= 2:
                prev = df.iloc[-2]
                if pd.notna(last.get('unit_nav')) and pd.notna(prev.get('unit_nav')):
                    new_item['change'] = round(float(last['unit_nav']) - float(prev['unit_nav']), 3)
            updated.append(new_item)
        except Exception as e:
            print(f"  Warning: Failed to fetch fund nav {code}: {e}")
            updated.append(item)
    return updated


# 宽基 ETF 份额监控池（跟踪国家队/汇金宽基申赎动向的经典名单，16 只）
NATIONAL_ETF_WATCH = {
    '159919.SZ': '嘉实300ETF',
    '510300.SH': '华泰柏瑞300ETF',
    '510310.SH': '易方达300ETF',
    '510330.SH': '华夏300ETF',
    '510050.SH': '华夏上证50ETF',
    '588000.SH': '华夏科创50ETF',
    '588080.SH': '易方达科创50ETF',
    '510500.SH': '南方中证500ETF',
    '512100.SH': '南方中证1000ETF',
    '159915.SZ': '易方达创业板ETF',
    '159949.SZ': '华安创业板50ETF',
    '563360.SH': '华泰柏瑞A500ETF',
    '159352.SZ': '南方A500ETF',
    '159338.SZ': '国泰A500ETF',
    '512050.SH': '华夏A500ETF',
    '159361.SZ': '易方达A500ETF',
}


def fetch_national_etf_watch(pro, trade_date, existing):
    """宽基 ETF 份额监控：最新份额 / 前一日对比 / 5日对比 / VWAP 估算净流入。

    - 份额：pro.fund_share（已实测有权限），fd_share 单位为万份，统一换算亿份
    - 成交均价：pro.fund_daily 的 VWAP = amount(千元)*10 / vol(手)（元）
    - 当日净流入 = 当日份额变动(亿份) × 当日成交均价(元)，单位亿元
    - 5日净流入 = 近 5 个交易日每日净流入之和
    单只取不到数据时：优先保留旧数据条目，否则跳过，不报错。
    """
    start = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=20)).strftime('%Y%m%d')
    existing_map = {e.get('code'): e for e in (existing or {}).get('items', [])}
    items = []
    latest_dates = []
    for tc, name in NATIONAL_ETF_WATCH.items():
        try:
            time.sleep(API_DELAY)
            df_share = pro.fund_share(ts_code=tc, start_date=start, end_date=trade_date)
            time.sleep(API_DELAY)
            df_daily = pro.fund_daily(ts_code=tc, start_date=start, end_date=trade_date)
            if df_share is None or len(df_share) < 2:
                raise ValueError('fund_share empty')
            shares = dict(zip(df_share['trade_date'], df_share['fd_share'] / 10000.0))  # 亿份
            vwap = {}
            if df_daily is not None and len(df_daily) > 0:
                for _, r in df_daily.iterrows():
                    if float(r['vol']) > 0:
                        vwap[r['trade_date']] = float(r['amount']) * 10.0 / float(r['vol'])
            days = sorted(shares.keys())
            latest = days[-1]
            latest_dates.append(latest)
            # 每日份额变动 × 当日 VWAP = 当日净流入（亿元）
            daily_flow = {}
            daily_chg = {}
            for i in range(1, len(days)):
                d0, d1 = days[i - 1], days[i]
                chg = shares[d1] - shares[d0]
                daily_chg[d1] = chg
                daily_flow[d1] = chg * vwap.get(d1, 0.0)
            prev = days[-2]
            last5 = days[-5:]  # 近 5 个交易日
            share_chg = daily_chg.get(latest, 0.0)
            net_flow = daily_flow.get(latest, 0.0)
            share_chg_5d = sum(daily_chg.get(d, 0.0) for d in last5)
            net_flow_5d = sum(daily_flow.get(d, 0.0) for d in last5)
            items.append({
                'name': name,
                'code': tc,
                'share': round(shares[latest], 2),
                'prevShare': round(shares[prev], 2),
                'shareChg': round(share_chg, 2),
                'avgPrice': round(vwap.get(latest, 0.0), 3),
                'netFlow': round(net_flow, 2),
                'shareChg5d': round(share_chg_5d, 2),
                'netFlow5d': round(net_flow_5d, 2),
            })
        except Exception as e:
            print(f"  Warning: ETF watch failed for {tc}: {e}")
            if tc in existing_map:
                items.append(existing_map[tc])  # 保留旧数据
    if not items:
        return None
    total = {
        'shareChg': round(sum(i['shareChg'] for i in items), 2),
        'netFlow': round(sum(i['netFlow'] for i in items), 2),
        'shareChg5d': round(sum(i['shareChg5d'] for i in items), 2),
        'netFlow5d': round(sum(i['netFlow5d'] for i in items), 2),
    }
    d = max(latest_dates) if latest_dates else trade_date
    return {
        'trade_date': f"{d[:4]}-{d[4:6]}-{d[6:]}",
        'items': items,
        'total': total,
    }


# 东方财富 中债国债收益率接口（已实测可用，主流口径，免费）
BOND_YIELD_URL = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
BOND_YIELD_MAP = {  # 内部字段 → 东财列名
    'y2': 'EMM00588704',   # 2年
    'y5': 'EMM00166462',   # 5年
    'y10': 'EMM00166466',  # 10年
    'y30': 'EMM00166469',  # 30年
}


def _sub_months(dt, months):
    """日期减 N 个自然月（月末日钳位）。"""
    m = dt.month - months
    y = dt.year
    while m <= 0:
        m += 12
        y -= 1
    days_in_month = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return datetime(y, m, min(dt.day, days_in_month[m - 1]))


def _nearest_row(rows, target_dt):
    """rows 已按 date 升序，取 date <= target 的最近一行。"""
    best = None
    for r in rows:
        if datetime.strptime(r['date'], '%Y-%m-%d') <= target_dt:
            best = r
        else:
            break
    return best


def fetch_bond_yields(trade_date, data):
    """国债收益率 + 资金面点评自动更新（东方财富 datacenter 接口）。

    - bondData.daily：新日期按 date 去重 append（历史手工值不覆盖），y*_chg 统一重算
    - bondData.stats：latest（spread=y30-y2）、1m_change（单位 bp）、近一年 range 全部重算
    - bondData.curveCompare：latest / 1M / 3M / 6M / 1Y，按 <=目标日 最近邻取值
    - bondData.news：头部追加当日条目（当日已存在则跳过，cap 30 条）
    - bondData.liquidityTools：updateTime 刷新 + comment 模板自动生成
    TODO: DR001/DR007 暂无可靠免费接口（中国货币网质押式回购历史接口未找到，
          ShiborHis 可用但口径不同），dr001/dr007/monthlyNet 暂保留手工值。
    """
    try:
        resp = requests.get(BOND_YIELD_URL, params={
            'reportName': 'RPTA_WEB_TREASURYYIELD',
            'columns': 'ALL',
            'pageSize': 30,
            'pageNumber': 1,
            'sortColumns': 'SOLAR_DATE',
            'sortTypes': -1,
            'source': 'WEB',
            'client': 'WEB',
        }, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        rows_raw = (resp.json().get('result') or {}).get('data') or []
        new_rows = {}
        for r in rows_raw:
            vals = {k: r.get(col) for k, col in BOND_YIELD_MAP.items()}
            if any(v is None for v in vals.values()):
                continue
            d = str(r.get('SOLAR_DATE', ''))[:10]
            if len(d) != 10:
                continue
            new_rows[d] = {'date': d, **{k: round(float(v), 4) for k, v in vals.items()}}
        if not new_rows:
            raise ValueError('eastmoney treasury yield empty')

        bd = data.setdefault('bondData', {})
        daily_map = {r['date']: dict(r) for r in bd.get('daily', [])}
        added = 0
        for d, row in new_rows.items():
            if d not in daily_map:  # 历史手工值不覆盖
                daily_map[d] = row
                added += 1
        daily = [daily_map[d] for d in sorted(daily_map)]
        if not daily:
            raise ValueError('bond daily empty')
        # 统一重算 chg（当日 - 前一交易日，百分点，round 4）
        for i, r in enumerate(daily):
            for k in BOND_YIELD_MAP:
                r[f'{k}_chg'] = 0 if i == 0 else round(r[k] - daily[i - 1][k], 4)
        bd['daily'] = daily

        latest = daily[-1]
        latest_dt = datetime.strptime(latest['date'], '%Y-%m-%d')

        # stats：latest / 1m_change(bp) / 近一年 range
        r1m = _nearest_row(daily, _sub_months(latest_dt, 1)) or daily[0]
        bd['stats'] = {
            'latest': {'date': latest['date'],
                       **{k: latest[k] for k in BOND_YIELD_MAP},
                       'spread': round(latest['y30'] - latest['y2'], 3)},
            '1m_change': {k: round((latest[k] - r1m[k]) * 100, 1) for k in BOND_YIELD_MAP},
            'range': {k: {'min': round(min(r[k] for r in daily
                                         if datetime.strptime(r['date'], '%Y-%m-%d')
                                         >= latest_dt - timedelta(days=365)), 3),
                          'max': round(max(r[k] for r in daily
                                         if datetime.strptime(r['date'], '%Y-%m-%d')
                                         >= latest_dt - timedelta(days=365)), 3)}
                      for k in BOND_YIELD_MAP},
        }

        # curveCompare（<=目标日 最近邻）
        cc = {'latest': {'date': latest['date'], **{k: latest[k] for k in BOND_YIELD_MAP}}}
        for label, months in [('1M_ago', 1), ('3M_ago', 3), ('6M_ago', 6), ('1Y_ago', 12)]:
            rr = _nearest_row(daily, _sub_months(latest_dt, months)) or daily[0]
            cc[label] = {'date': rr['date'], **{k: rr[k] for k in BOND_YIELD_MAP}}
        bd['curveCompare'] = cc

        # news：当日条目 prepend（已存在则跳过）
        news = bd.setdefault('news', [])
        if not any(n.get('date') == latest['date'] for n in news):
            c = latest['y10_chg']
            if c < 0:
                title = f"10年期国债收益率续降至{latest['y10']:.3f}%，债市持续走牛"
            elif c > 0:
                title = f"10年期国债收益率回升至{latest['y10']:.3f}%，债市出现调整"
            else:
                title = f"10年期国债收益率持平于{latest['y10']:.3f}%，债市横盘整理"
            news.insert(0, {'date': latest['date'], 'title': title, 'source': '中债登'})
            bd['news'] = news[:30]

        # liquidityTools：updateTime 刷新 + comment 模板自动生成
        lt = bd.get('liquidityTools')
        if lt:
            lt['updateTime'] = latest['date']
            try:
                dr007 = float(lt.get('dr007', 0))
                policy = float(lt.get('policyRate', 1.40))
                if dr007 <= policy - 0.05:
                    s1 = f"DR007（{dr007:.2f}%）低于7天逆回购政策利率（{policy:.2f}%），资金面偏松"
                elif dr007 >= policy + 0.05:
                    s1 = f"DR007（{dr007:.2f}%）高于7天逆回购政策利率（{policy:.2f}%），资金面边际收敛"
                else:
                    s1 = f"DR007（{dr007:.2f}%）贴近7天逆回购政策利率（{policy:.2f}%），资金面整体均衡"
                net = float(lt.get('monthlyNet', 0))
                if net > 0:
                    s2 = f"本月公开市场净投放{net:.0f}亿元，央行持续呵护流动性。"
                elif net < 0:
                    s2 = f"本月公开市场净回笼{abs(net):.0f}亿元，流动性投放力度偏中性。"
                else:
                    s2 = "本月公开市场投放与到期基本持平，流动性维持平稳。"
                lt['comment'] = s1 + '；' + s2
            except Exception as e:
                print(f"  Warning: liquidity comment build failed: {e}")

        print(f"  daily 末行 {latest['date']}: 2Y {latest['y2']}, 5Y {latest['y5']}, "
              f"10Y {latest['y10']}, 30Y {latest['y30']} (新增 {added} 行)")
        return True
    except Exception as e:
        print(f"  Warning: fetch_bond_yields failed: {e}")
        return False


# ── 行业资金历史沉淀 + 板块资金扫描榜 + 底部资金积聚监测（Tushare）──
# 设计目标：监测"长时间大资金缓慢流入、在底部形成积聚、且有龙头率先脱离底部"的板块。
# 历史数据每天增量积累在 scripts/cache/sector_history.json（不部署，随 workflow 提交回写延续）。
SECTOR_HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', 'sector_history.json')
SECTOR_HISTORY_MAX_DAYS = 250   # 历史最长保留交易日数
SECTOR_BACKFILL_DAYS = 60       # 首次运行回补交易日数（每天 2 次调用，约 3 分钟）
BOTTOM_WINDOW = 60              # 底部积聚监测窗口（交易日）
BOTTOM_MIN_DAYS = 40            # 历史不足该天数时降级为"数据积累中"


def _load_sector_history():
    try:
        with open(SECTOR_HISTORY_PATH, encoding='utf-8') as f:
            h = json.load(f)
        return h if isinstance(h.get('days'), dict) else {'days': {}}
    except Exception:
        return {'days': {}}


def _save_sector_history(hist):
    os.makedirs(os.path.dirname(SECTOR_HISTORY_PATH), exist_ok=True)
    days = hist['days']
    keep = sorted(days)[-SECTOR_HISTORY_MAX_DAYS:]
    hist['days'] = {d: days[d] for d in keep}
    with open(SECTOR_HISTORY_PATH, 'w', encoding='utf-8') as f:
        json.dump(hist, f, ensure_ascii=False)


def _aggregate_industry_day(pro, date, ind_map):
    """单日全市场 moneyflow + daily 按 industry 聚合 → {行业: {net(亿), ret(%), amt(亿)}}（ret 等权）。"""
    time.sleep(API_DELAY)
    mf = pro.moneyflow(trade_date=date)
    time.sleep(API_DELAY)
    dl = pro.daily(trade_date=date)
    if mf is None or len(mf) == 0:
        raise ValueError(f'moneyflow empty for {date}')
    mf = mf.copy()
    mf['industry'] = mf['ts_code'].map(ind_map)
    g = mf.dropna(subset=['industry']).groupby('industry')['net_mf_amount'].sum() / 1e4  # 万元→亿
    sectors = {ind: {'net': round(float(v), 2), 'ret': 0.0, 'amt': 0.0} for ind, v in g.items()}
    if dl is not None and len(dl) > 0:
        dl = dl.copy()
        dl['industry'] = dl['ts_code'].map(ind_map)
        valid = dl.dropna(subset=['industry'])
        rg = valid.groupby('industry')['pct_chg'].mean()  # 等权涨跌幅
        ag = valid.groupby('industry')['amount'].sum() / 1e5  # 成交额 千元→亿
        for ind in set(rg.index) | set(ag.index):
            sectors.setdefault(ind, {'net': 0.0, 'ret': 0.0, 'amt': 0.0})
            if ind in rg.index:
                sectors[ind]['ret'] = round(float(rg[ind]), 2)
            if ind in ag.index:
                sectors[ind]['amt'] = round(float(ag[ind]), 2)
    return sectors


def update_sector_history(pro, trade_date):
    """增量维护行业资金历史。首次/缺历史时回补最近 SECTOR_BACKFILL_DAYS 个交易日；
    每日落盘一次，中断后下次可续传。返回 (hist, ind_map, name_map)。"""
    basic = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name,industry')
    ind_map = dict(zip(basic['ts_code'], basic['industry']))
    name_map = dict(zip(basic['ts_code'], basic['name']))
    hist = _load_sector_history()
    start = (datetime.strptime(trade_date, '%Y%m%d')
             - timedelta(days=int(SECTOR_BACKFILL_DAYS * 1.6))).strftime('%Y%m%d')
    cal = pro.trade_cal(exchange='SSE', start_date=start, end_date=trade_date, is_open='1')
    # trade_cal 返回顺序不保证升序，必须显式排序（已实测踩坑）
    dates = sorted(cal['cal_date'].tolist())[-SECTOR_BACKFILL_DAYS:]
    if trade_date not in dates:
        dates.append(trade_date)
    # 缺日期 或 存量日期缺 amt 字段（老缓存）都需要重抓
    def _day_ok(day):
        secs = day.get('sectors', {})
        return bool(secs) and all('amt' in s for s in secs.values())
    todo = [d for d in dates if d not in hist['days'] or not _day_ok(hist['days'][d])]
    if todo:
        print(f"  sector history backfill: {len(todo)} days to fetch ({todo[0]}~{todo[-1]})")
    for d in todo:
        try:
            hist['days'][d] = {'sectors': _aggregate_industry_day(pro, d, ind_map)}
            _save_sector_history(hist)  # 每日落盘，中断可续
        except Exception as e:
            print(f"  Warning: industry aggregate failed for {d}: {e}")
    _save_sector_history(hist)
    print(f"  sector history: {len(hist['days'])} days accumulated")
    return hist, ind_map, name_map


def _today_industry_stocks(pro, trade_date, ind_map, name_map):
    """当日全市场 moneyflow+daily → {行业: [{name, code, net(亿), pct}]}（按净流入降序）。"""
    try:
        time.sleep(API_DELAY)
        mf = pro.moneyflow(trade_date=trade_date)
        time.sleep(API_DELAY)
        dl = pro.daily(trade_date=trade_date)
        if mf is None or len(mf) == 0:
            raise ValueError('moneyflow empty')
        pct_map = {}
        if dl is not None and len(dl) > 0:
            pct_map = dict(zip(dl['ts_code'], dl['pct_chg']))
        mf = mf.copy()
        mf['industry'] = mf['ts_code'].map(ind_map)
        mf = mf.dropna(subset=['industry']).sort_values('net_mf_amount', ascending=False)
        out = {}
        for _, r in mf.iterrows():
            out.setdefault(r['industry'], []).append({
                'name': name_map.get(r['ts_code'], r['ts_code']),
                'code': r['ts_code'],
                'net': round(float(r['net_mf_amount']) / 1e4, 2),
                'pct': round(float(pct_map.get(r['ts_code'], 0.0)), 2),
            })
        return out
    except Exception as e:
        print(f"  Warning: today industry stocks failed: {e}")
        return {}


def _history_series(hist, industry):
    """行业的逐日 (date, net, ret, amt) 序列，按日期升序。"""
    rows = []
    for d in sorted(hist['days']):
        s = hist['days'][d].get('sectors', {}).get(industry)
        if s is not None:
            rows.append((d, s.get('net', 0.0), s.get('ret', 0.0), s.get('amt', 0.0)))
    return rows


def _scan_rank_scores(items, n):
    """5日净流入排名分（0~40，越高越好）。"""
    if n <= 1:
        return {id(it): 20.0 for it in items}
    by_net5 = sorted(items, key=lambda x: x['netInflow5d'], reverse=True)
    return {id(it): round((n - 1 - i) / (n - 1) * 40, 1) for i, it in enumerate(by_net5)}


def _scan_summary(items):
    """扫描榜自动总评（items 已只含信号板块）。"""
    absorb = [i for i in items if i['status'] == '吸筹中']
    start = [i for i in items if i['status'] == '启动确认']
    risk = [i for i in items if i['status'] == '高潮风险']
    parts = []
    if absorb:
        parts.append(f"{len(absorb)}个板块出现吸筹信号："
                     + '、'.join(f"{i['sector']}连续{i['consecutiveDays']}日净流入" for i in absorb[:3]))
    if start:
        parts.append(f"{len(start)}个板块启动确认（{'、'.join(i['sector'] for i in start[:3])}）")
    if risk:
        parts.append(f"{len(risk)}个板块存在高潮风险（{'、'.join(i['sector'] for i in risk[:3])}），谨慎追高")
    return '今日' + '；'.join(parts) + '。'


def build_sector_scan(hist, trade_date, today_map):
    """板块资金扫描榜（精简版）：只保留触发信号的板块，每个板块附 2 只吸筹个股。

    信号规则（数据来自行业资金历史沉淀）：
    - 吸筹中：连续净流入 ≥3 天 且 当日涨幅 <1%（资金进、价未动）
    - 启动确认：连续净流入 ≥2 天 且 当日涨幅 ≥1.5%
    - 高潮风险：连续净流入 ≥3 天 且 近5日涨幅 ≥8%（风险提示优先判定）
    """
    industries = set()
    for day in hist['days'].values():
        industries.update(day.get('sectors', {}).keys())
    items = []
    latest = trade_date
    for ind in sorted(industries):
        rows = _history_series(hist, ind)
        if len(rows) < 3:
            continue
        latest = rows[-1][0]
        consec = 0
        for _, net, _r, _a in reversed(rows):
            if net > 0:
                consec += 1
            else:
                break
        ret1 = rows[-1][2]
        acc = 1.0
        for r in rows[-5:]:
            acc *= (1 + r[2] / 100.0)
        pct5 = (acc - 1) * 100
        if consec >= 3 and pct5 >= 8:
            status = '高潮风险'
        elif consec >= 2 and ret1 >= 1.5:
            status = '启动确认'
        elif consec >= 3 and ret1 < 1:
            status = '吸筹中'
        else:
            continue  # 无信号不展示
        stocks = [{'name': s['name'], 'code': s['code'], 'netInflow': s['net'], 'pctChg': s['pct']}
                  for s in (today_map.get(ind) or [])[:2]]
        items.append({
            'sector': ind,
            'netInflow1d': round(rows[-1][1], 2),
            'netInflow5d': round(sum(r[1] for r in rows[-5:]), 2),
            'consecutiveDays': consec,
            'sectorPctChg': round(ret1, 2),
            'pct5d': round(pct5, 2),
            'status': status,
            'stocks': stocks,
        })
    d = f"{latest[:4]}-{latest[4:6]}-{latest[6:]}"
    if not items:
        return {'trade_date': d, 'summary': '今日无板块触发吸筹/启动/高潮信号，资金以观望为主。', 'items': []}
    rank_score = _scan_rank_scores(items, len(items))
    for it in items:
        it['score'] = round(it['consecutiveDays'] * 20 + rank_score[id(it)]
                            - (20 if it['pct5d'] > 8 else 0), 1)
    items.sort(key=lambda x: -x['score'])
    return {'trade_date': d, 'summary': _scan_summary(items), 'items': items}


def _find_bottom_leaders(pro, trade_date, sector, today_map, max_check=5):
    """率先脱离底部的龙头：今日行业主力净流入前 max_check 只，逐只拉近 60 日行情，
    筛选收盘价站上 20/60 日均线 且 距 60 日高点 <15%（率先走强）。"""
    leaders = []
    start60 = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=100)).strftime('%Y%m%d')
    for s in (today_map.get(sector) or [])[:max_check]:
        try:
            time.sleep(API_DELAY)
            df = pro.daily(ts_code=s['code'], start_date=start60, end_date=trade_date)
            if df is None or len(df) < 25:
                continue
            df = df.sort_values('trade_date')
            closes = df['close'].tolist()
            close = closes[-1]
            ma20 = sum(closes[-20:]) / 20
            ma60 = sum(closes[-60:]) / min(60, len(closes))
            high60 = df['high'].max()
            dist = (high60 / close - 1) * 100 if close else 999
            if close > ma20 and close > ma60 and dist <= 15:
                leaders.append({'name': s['name'], 'code': s['code'], 'pctChg': s['pct'],
                                'strength': f"站上20/60日线，距60日高点{dist:.0f}%"})
        except Exception as e:
            print(f"  Warning: bottom leader check failed for {s['code']}: {e}")
    leaders.sort(key=lambda x: -x['pctChg'])
    return leaders[:3]


def build_bottom_watch(hist, pro, trade_date, today_map):
    """底部资金积聚监测：长窗口 + 缓慢持续流入 + 价格底部 + 龙头先行。

    触发条件：60 日累计净流入 >0 且 净流入天数占比 ≥55%（缓慢持续）
              且 价格底部分位 <0.4（等权累计收益指数处于长期低位）
              且 近 5 日仍净流入。
    score = 持续性×40% + 累计流入排名分×40% + 底部深度×20%。
    历史不足 BOTTOM_MIN_DAYS 天时不判定，输出 note"数据积累中"。
    """
    industries = set()
    for day in hist['days'].values():
        industries.update(day.get('sectors', {}).keys())
    n_days = len(hist['days'])
    latest = max(hist['days']) if hist['days'] else trade_date
    d = f"{latest[:4]}-{latest[4:6]}-{latest[6:]}"
    result = {'trade_date': d, 'window': BOTTOM_WINDOW, 'days': n_days, 'items': []}
    if n_days < BOTTOM_MIN_DAYS:
        result['note'] = f'数据积累中（已积累 {n_days} 个交易日，满 {BOTTOM_MIN_DAYS} 天后开始判定）'
        return result
    items = []
    for ind in sorted(industries):
        rows = _history_series(hist, ind)
        if len(rows) < BOTTOM_MIN_DAYS:
            continue
        win = rows[-BOTTOM_WINDOW:]
        nets = [r[1] for r in win]
        inflow60 = sum(nets)
        pos_ratio = sum(1 for x in nets if x > 0) / len(nets)
        inflow5 = sum(nets[-5:])
        # 价格位置：等权累计收益指数在全部已积累历史（最多 250 日）区间中的分位
        idx = 1.0
        curve = []
        for r in rows:
            idx *= (1 + r[2] / 100.0)
            curve.append(idx)
        lo, hi = min(curve), max(curve)
        price_pos = (curve[-1] - lo) / (hi - lo) if hi > lo else 0.5
        if inflow60 > 0 and pos_ratio >= 0.55 and price_pos < 0.4 and inflow5 > 0:
            items.append({'sector': ind, 'inflow60d': round(inflow60, 2),
                          'inflow5d': round(inflow5, 2),
                          'positiveRatio': round(pos_ratio * 100, 1),
                          'pricePosition': round(price_pos, 3)})
    if not items:
        return result
    m = len(items)
    by_inflow = sorted(items, key=lambda x: x['inflow60d'], reverse=True)
    rank = {id(it): (m - 1 - i) / (m - 1) if m > 1 else 0.5 for i, it in enumerate(by_inflow)}
    for it in items:
        it['score'] = round(it['positiveRatio'] / 100 * 40 + rank[id(it)] * 40
                            + (1 - it['pricePosition']) * 20, 1)
    items.sort(key=lambda x: -x['score'])
    for it in items:
        it['leaders'] = _find_bottom_leaders(pro, trade_date, it['sector'], today_map)
    names = '、'.join(i['sector'] for i in items[:4])
    result['items'] = items
    result['summary'] = (f"{len(items)} 个板块出现底部资金积聚信号：{names}——"
                         f"长周期资金缓慢流入且价格处于长期低位，关注率先走强的龙头。")
    return result


def fetch_sector_watch(pro, trade_date, data):
    """板块资金观察台：行业资金历史沉淀 → 扫描榜（仅信号板块）+ 底部资金积聚监测。

    数据源全部为 Tushare（moneyflow + daily + stock_basic），每天增量积累历史。
    任一环节失败保留旧数据，不崩脚本。成功返回 (hist, ind_map, name_map, today_map) 供后续步骤复用。
    """
    try:
        hist, ind_map, name_map = update_sector_history(pro, trade_date)
        if len(hist['days']) < 3:
            raise ValueError('sector history empty')
        today_map = _today_industry_stocks(pro, trade_date, ind_map, name_map)
        scan = build_sector_scan(hist, trade_date, today_map)
        data['sectorScan'] = scan
        n_stocks = sum(len(i.get('stocks', [])) for i in scan['items'])
        print(f"  sectorScan: {len(scan['items'])} signal sectors ({n_stocks} stocks attached)")
        print(f"  summary: {scan['summary']}")
        bottom = build_bottom_watch(hist, pro, trade_date, today_map)
        data['bottomWatch'] = bottom
        if bottom.get('note'):
            print(f"  bottomWatch: {bottom['note']}")
        else:
            print(f"  bottomWatch: {len(bottom['items'])} triggered sectors")
            if bottom.get('summary'):
                print(f"  {bottom['summary']}")
        return hist, ind_map, name_map, today_map
    except Exception as e:
        print(f"  Warning: fetch_sector_watch failed: {e}")
        return None


# ── ECI 六维分每日自动真算 + 强势一级行业子板块精选 ──
# Tushare 二级行业 → 申万一级行业映射（覆盖 sector_history 中全部 110 个二级行业，
# 商贸零售类因 ECI 31 行业无此一级，归入 None 并打印警告，不参与一级聚合）
SECTOR_TO_L1 = {
    # 医药生物
    '化学制药': '医药生物', '生物制药': '医药生物', '中成药': '医药生物',
    '医疗保健': '医药生物', '医药商业': '医药生物',
    # 电子 / 计算机 / 通信
    '半导体': '电子', '元器件': '电子',
    '软件服务': '计算机', 'IT设备': '计算机',
    '通信设备': '通信', '电信运营': '通信',
    # 电力设备
    '电气设备': '电力设备', '电器仪表': '电力设备',
    # 食品饮料
    '白酒': '食品饮料', '红黄酒': '食品饮料', '啤酒': '食品饮料',
    '食品': '食品饮料', '乳制品': '食品饮料', '软饮料': '食品饮料',
    # 金融
    '银行': '银行',
    '证券': '非银金融', '保险': '非银金融', '多元金融': '非银金融',
    # 汽车 / 机械设备 / 国防军工
    '汽车整车': '汽车', '汽车配件': '汽车', '汽车服务': '汽车', '摩托车': '汽车',
    '专用机械': '机械设备', '工程机械': '机械设备', '机床制造': '机械设备',
    '机械基件': '机械设备', '农用机械': '机械设备', '化工机械': '机械设备',
    '轻工机械': '机械设备', '纺织机械': '机械设备', '运输设备': '机械设备',
    '航空': '国防军工', '船舶': '国防军工',
    # 有色金属 / 钢铁 / 煤炭 / 石油石化 / 基础化工
    '铜': '有色金属', '铝': '有色金属', '铅锌': '有色金属',
    '小金属': '有色金属', '黄金': '有色金属',
    '普钢': '钢铁', '特种钢': '钢铁', '钢加工': '钢铁',
    '煤炭开采': '煤炭', '焦炭加工': '煤炭',
    '石油开采': '石油石化', '石油加工': '石油石化', '石油贸易': '石油石化',
    '化工原料': '基础化工', '化纤': '基础化工', '塑料': '基础化工',
    '染料涂料': '基础化工', '橡胶': '基础化工', '农药化肥': '基础化工',
    # 家用电器 / 轻工制造 / 纺织服装 / 美容护理
    '家用电器': '家用电器',
    '家居用品': '轻工制造', '造纸': '轻工制造',
    '纺织': '纺织服装', '服饰': '纺织服装',
    '日用化工': '美容护理',
    # 房地产 / 建筑装饰 / 建筑材料
    '全国地产': '房地产', '区域地产': '房地产', '房产服务': '房地产', '园区开发': '房地产',
    '建筑工程': '建筑装饰', '装修装饰': '建筑装饰',
    '水泥': '建筑材料', '玻璃': '建筑材料', '陶瓷': '建筑材料',
    '其他建材': '建筑材料', '矿物制品': '建筑材料',
    # 交通运输
    '水运': '交通运输', '港口': '交通运输', '空运': '交通运输', '机场': '交通运输',
    '铁路': '交通运输', '公路': '交通运输', '路桥': '交通运输',
    '仓储物流': '交通运输', '公共交通': '交通运输',
    # 传媒
    '出版业': '传媒', '影视音像': '传媒', '广告包装': '传媒', '互联网': '传媒',
    # 农林牧渔 / 公用事业 / 社会服务 / 环保 / 综合
    '种植业': '农林牧渔', '林业': '农林牧渔', '渔业': '农林牧渔',
    '饲料': '农林牧渔', '农业综合': '农林牧渔',
    '火力发电': '公用事业', '水力发电': '公用事业', '新型电力': '公用事业',
    '供气供热': '公用事业', '水务': '公用事业',
    '旅游景点': '社会服务', '旅游服务': '社会服务', '酒店餐饮': '社会服务', '文教休闲': '社会服务',
    '环境保护': '环保',
    '综合类': '综合',
    # ECI 31 行业无"商贸零售"，以下归入 None（打印警告，不参与一级聚合）
    '商品城': None, '商贸代理': None, '百货': None, '超市连锁': None,
    '批发业': None, '电器连锁': None, '其他商业': None,
}

_ECI_DIM_MAX = 15  # 六维各维度满分（ECI 总分折算百分制）


def _l1_series(hist):
    """二级历史按 SECTOR_TO_L1 归并 → {一级: [(date, net, ret, amt)]}（ret 按成交额加权）。"""
    out = {}
    warned = set()
    for d in sorted(hist['days']):
        acc = {}
        for ind, s in hist['days'][d].get('sectors', {}).items():
            if ind not in SECTOR_TO_L1 and ind not in warned:
                warned.add(ind)
                print(f"  Warning: unknown industry '{ind}' not in SECTOR_TO_L1, skipped")
            l1 = SECTOR_TO_L1.get(ind)
            if not l1:
                continue
            a = acc.setdefault(l1, {'net': 0.0, 'amt': 0.0, 'ret_amt': 0.0, 'ret_eq': 0.0, 'n': 0})
            amt = s.get('amt', 0.0)
            a['net'] += s.get('net', 0.0)
            a['amt'] += amt
            a['ret_amt'] += s.get('ret', 0.0) * amt
            a['ret_eq'] += s.get('ret', 0.0)
            a['n'] += 1
        for l1, a in acc.items():
            ret = a['ret_amt'] / a['amt'] if a['amt'] > 0 else (a['ret_eq'] / a['n'] if a['n'] else 0.0)
            out.setdefault(l1, []).append((d, a['net'], ret, a['amt']))
    return out


def _cv(xs):
    """变异系数 std/mean（量能波动度量）。"""
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    if m <= 0:
        return 0.0
    var = sum((x - m) ** 2 for x in xs) / len(xs)
    return (var ** 0.5) / m


def _pct_rank(values, v):
    """v 在 values 中的分位（0-1，越高越大）。"""
    if not values:
        return 0.5
    return sum(1 for x in values if x <= v) / len(values)


def _pearson(xs, ys):
    n = len(xs)
    if n < 5:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / (vx ** 0.5 * vy ** 0.5)


def _mean_pairwise_corr(member_rets):
    """一级内部各二级行业 20 日日收益的两两 Pearson 相关均值；不足 2 个成员返回 None。"""
    corrs = []
    for i in range(len(member_rets)):
        for j in range(i + 1, len(member_rets)):
            c = _pearson(member_rets[i], member_rets[j])
            if c is not None:
                corrs.append(c)
    return sum(corrs) / len(corrs) if corrs else None


def _sign(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)


def _rebuild_eci_from_history(hist, old):
    """用 sector_history 真实数据按一级行业重算 ECI 31 行六维分（每维 0-15，总分折算百分制）。

    - volConvergence 量能收敛：20日成交额变异系数 vs 60日（CV 下降=收敛），跨行业分位归一
    - fundConcentration 资金集中度：20日累计净流入 / 20日累计成交额，跨行业分位归一
    - trendSync 趋势同步：一级内部各二级 20 日日收益的符号一致率（绝对值映射）
    - consistencyMomentum 一致性动量：近5日方向与近20日一致性 0.6 + 动量强度分位 0.4
    - activity 活跃度：近5日成交额均值在 60 日中的分位（绝对值映射）
    - policy 政策分：固定中性 7.5/15（无法自动化，页面注明）
    currentCorr=一级内二级 20 日日收益两两相关均值；predictedCorr=其 5 日前移窗口的变化外推。
    历史不足 40 天或无二级成员的一级行业：保留旧数据行。
    """
    try:
        l1s = _l1_series(hist)
        old_sectors = {s.get('sector'): s for s in (old or {}).get('sectors', [])}
        # 原始指标
        raw = {}
        for l1, rows in l1s.items():
            if len(rows) < 40:
                continue
            amts60 = [r[3] for r in rows[-60:]]
            amts20 = amts60[-20:]
            nets20 = [r[1] for r in rows[-20:]]
            nets5 = nets20[-5:]
            rets20 = [r[2] for r in rows[-20:]]
            rets5 = rets20[-5:]
            raw[l1] = {
                'conv': _cv(amts60) - _cv(amts20),          # 量能收敛（越大越收敛）
                'fund': (sum(nets20) / sum(amts20)) if sum(amts20) > 0 else 0.0,
                'ret5': sum(rets5),
                'align': (sum(1 for x in rets5 if _sign(x) == _sign(sum(rets20)) and x != 0) / 5),
                'act': _pct_rank(amts60, sum(amts20[-5:]) / 5),
                'dates': (rows[-20][0], rows[-1][0]),
            }
        if len(raw) < 20:
            print(f"  Warning: eci history rebuild skipped, only {len(raw)} L1 sectors")
            return None
        conv_vals = [v['conv'] for v in raw.values()]
        fund_vals = [v['fund'] for v in raw.values()]
        ret5_vals = [abs(v['ret5']) for v in raw.values()]

        # 一级内二级 20 日收益矩阵（trendSync / currentCorr 用）
        def member_ret_matrix(l1, end_offset=0):
            mats = []
            for ind, m1 in SECTOR_TO_L1.items():
                if m1 != l1:
                    continue
                rows = _history_series(hist, ind)
                if len(rows) >= 20 + end_offset:
                    seg = rows[-(20 + end_offset):len(rows) - end_offset or None]
                    mats.append([r[2] for r in seg])
            return mats

        sectors = []
        for l1, v in raw.items():
            vol = round(_pct_rank(conv_vals, v['conv']) * _ECI_DIM_MAX, 1)
            fund = round(_pct_rank(fund_vals, v['fund']) * _ECI_DIM_MAX, 1)
            mats = member_ret_matrix(l1)
            if mats:
                sync_days = []
                for k in range(20):
                    signs = [_sign(m[k]) for m in mats if k < len(m)]
                    signs = [s for s in signs if s != 0]
                    if signs:
                        up = signs.count(1)
                        sync_days.append(max(up, len(signs) - up) / len(signs))
                trend_sync = round((sum(sync_days) / len(sync_days)) * _ECI_DIM_MAX, 1) if sync_days else 7.5
                cur = _mean_pairwise_corr(mats)
            else:
                trend_sync = 7.5
                cur = None
            strength = _pct_rank(ret5_vals, abs(v['ret5']))
            mom = round((0.6 * v['align'] + 0.4 * strength) * _ECI_DIM_MAX, 1)
            act = round(v['act'] * _ECI_DIM_MAX, 1)
            policy = 7.5  # 政策维度：人工中性分（无法自动化）
            eci = round((vol + fund + trend_sync + mom + act + policy) / (_ECI_DIM_MAX * 6) * 100, 1)
            current_corr = round(min(0.95, max(0.05, cur if cur is not None else trend_sync / _ECI_DIM_MAX)), 2)
            prev_corr = _mean_pairwise_corr(member_ret_matrix(l1, end_offset=5))
            if prev_corr is not None and cur is not None:
                predicted = cur + (cur - prev_corr)
            else:
                predicted = current_corr + (mom - _ECI_DIM_MAX / 2) * 0.01
            predicted_corr = round(min(0.95, max(0.05, predicted)), 2)
            trend = '↑上升' if mom >= 9 else ('↓下降' if mom <= 6 else '→震荡')
            if eci >= 65:
                a1 = '板块即将强联动，适合ETF或龙头一揽子买入'
            elif eci >= 50:
                a1 = '关注龙头个股，等待一致性确认'
            else:
                a1 = '必须精选个股，板块参考意义不大'
            a2 = {'↑上升': '一致性在增强，可加仓', '→震荡': '一致性震荡，观望为主',
                  '↓下降': '一致性在减弱，控制仓位'}[trend]
            prev_s = old_sectors.get(l1, {})
            sec = {
                'sector': l1, 'eci': eci,
                'volConvergence': vol, 'fundConcentration': fund, 'trendSync': trend_sync,
                'consistencyMomentum': mom, 'activity': act, 'policy': policy,
                'currentCorr': current_corr, 'predictedCorr': predicted_corr,
                'trend': trend,
                'stocks': prev_s.get('stocks', 0),
                'advice': f'{a1} | {a2}',
                'sampleStocks': prev_s.get('sampleStocks', []),
            }
            if prev_s.get('leaders'):
                sec['leaders'] = prev_s['leaders']  # 手工龙头数据保留
            sectors.append(sec)
        # 无数据/历史不足的一级行业：保留旧数据行，不裁减 31 行展示
        sectors.extend(s for name, s in old_sectors.items() if name not in raw)
        old_order = [s.get('sector') for s in (old or {}).get('sectors', [])]
        sectors.sort(key=lambda s: (old_order.index(s['sector']) if s['sector'] in old_order else 999))

        indicators = dict((old or {}).get('indicators') or {})
        for k in ['volConvergence', 'fundConcentration', 'trendSync',
                  'consistencyMomentum', 'activity', 'policy']:
            if k in indicators:
                indicators[k] = {**indicators[k], 'weight': '15分'}
        d0, d1 = next(iter(raw.values()))['dates']
        def _fmt(dd):
            return dd.replace('-', '.') if '-' in dd else f'{dd[:4]}.{dd[4:6]}.{dd[6:]}'
        p0, p1 = _fmt(d0), _fmt(d1)
        return {
            'updateTime': f"{p1.replace('.', '-')} 收盘（Tushare自动）",
            'period': f'{p0}~{p1} (20个交易日)',
            'totalIndustries': len(sectors),
            'divergentCount': sum(1 for s in sectors if s['eci'] < 50),
            'sectors': sectors,
            'indicators': indicators,
            'note': '评分口径：量能收敛=20日vs60日成交额变异系数变化；资金集中度=20日净流入/成交额；'
                    '趋势同步=二级行业日收益符号一致率；一致性动量=5日方向一致性×动量强度；'
                    '活跃度=5日成交额60日分位（以上均为 Tushare 真实数据，二级行业按申万一级归并）；'
                    '政策维度为人工中性评分（固定7.5/15）；ECI总分=六维加总折算百分制',
        }
    except Exception as e:
        print(f"  Warning: eci history rebuild failed: {e}")
        return None


def build_eci_subsectors(hist, eci_data, today_map):
    """强势一级行业（ECI前5 且 60日累计净流入>0 且 流入天数占比≥50%）的二级子板块精选。

    子板块四维简版打分（0-15×4 折算百分制）：资金集中度/趋势同步(20日上涨天数占比)/
    一致性动量/活跃度；选得分前 3 且 60日净流入>0（宁缺毋滥，可少于 3 个甚至为 0）；
    每个入选子板块带今日主力净流入前 2 的龙头。
    """
    days = sorted(hist['days'])
    if len(days) < 40:
        return None
    latest = days[-1]
    # 一级 60 日聚合（母板块资金条件）
    l1_60 = {}
    for d in days[-60:]:
        for ind, s in hist['days'][d].get('sectors', {}).items():
            l1 = SECTOR_TO_L1.get(ind)
            if not l1:
                continue
            a = l1_60.setdefault(l1, {'net': 0.0, 'pos': 0, 'n': 0})
            a['net'] += s.get('net', 0.0)
            a['pos'] += 1 if s.get('net', 0.0) > 0 else 0
            a['n'] += 1
    top5 = sorted((eci_data or {}).get('sectors', []), key=lambda x: -x.get('eci', 0))[:5]
    items = []
    for sec in top5:
        parent = sec['sector']
        a = l1_60.get(parent)
        if not a or a['n'] == 0 or a['net'] <= 0 or a['pos'] / a['n'] < 0.5:
            continue
        subs = []
        stat_list = []
        for ind, l1 in SECTOR_TO_L1.items():
            if l1 != parent:
                continue
            rows = _history_series(hist, ind)
            if len(rows) < 40:
                continue
            nets20 = [r[1] for r in rows[-20:]]
            rets20 = [r[2] for r in rows[-20:]]
            rets5 = rets20[-5:]
            amts60 = [r[3] for r in rows[-60:]]
            net60 = sum(r[1] for r in rows[-60:])
            pos60 = sum(1 for r in rows[-60:] if r[1] > 0) / len(rows[-60:])
            amt20 = sum(r[3] for r in rows[-20:])
            stat_list.append({
                'name': ind, 'net60': net60, 'pos60': pos60,
                'inflow20d': round(sum(nets20), 2),
                'fund': (sum(nets20) / amt20) if amt20 > 0 else 0.0,
                'up_ratio': sum(1 for x in rets20 if x > 0) / 20,
                'align': sum(1 for x in rets5 if _sign(x) == _sign(sum(rets20)) and x != 0) / 5,
                'ret5': abs(sum(rets5)),
                'act': _pct_rank(amts60, sum(amts60[-5:]) / 5) if amts60 else 0.5,
            })
        if not stat_list:
            continue
        fund_vals = [s['fund'] for s in stat_list]
        ret5_vals = [s['ret5'] for s in stat_list]
        for s in stat_list:
            fund = round(_pct_rank(fund_vals, s['fund']) * _ECI_DIM_MAX, 1)
            tsync = round(s['up_ratio'] * _ECI_DIM_MAX, 1)
            mom = round((0.6 * s['align'] + 0.4 * _pct_rank(ret5_vals, s['ret5'])) * _ECI_DIM_MAX, 1)
            act = round(s['act'] * _ECI_DIM_MAX, 1)
            s['eci'] = round((fund + tsync + mom + act) / (_ECI_DIM_MAX * 4) * 100, 1)
        picked = [s for s in sorted(stat_list, key=lambda x: -x['eci']) if s['net60'] > 0][:3]
        if not picked:
            continue
        subs = [{
            'name': s['name'], 'eci': s['eci'], 'inflow20d': s['inflow20d'],
            'positiveRatio': round(s['pos60'] * 100, 1),
            'leaders': [{'name': t['name'], 'code': t['code'], 'pctChg': t['pct']}
                        for t in (today_map.get(s['name']) or [])[:2]],
        } for s in picked]
        items.append({'parent': parent, 'parentEci': sec['eci'], 'subs': subs})
    return {
        'trade_date': f"{latest[:4]}-{latest[4:6]}-{latest[6:]}",
        'items': items,
    }


def fetch_eci_daily(pro, trade_date, data, watch_ctx=None):
    """ECI 每日自动真算（任务1）+ 强势一级行业子板块精选（任务2）。

    数据全部来自 sector_history 沉淀；watch_ctx 为第 12 步返回的 (hist, ind_map, name_map, today_map)，
    缺省时自行从缓存加载历史（today_map 为空则子板块龙头为空，不致命）。
    """
    try:
        if watch_ctx:
            hist, ind_map, name_map, today_map = watch_ctx
        else:
            hist = _load_sector_history()
            today_map = {}
        if len(hist['days']) < 40:
            print(f"  eciDaily: history only {len(hist['days'])} days, keep old eciData")
            return
        eci = _rebuild_eci_from_history(hist, data.get('eciData'))
        if eci:
            data['eciData'] = eci
            top = sorted(eci['sectors'], key=lambda x: -x['eci'])[:3]
            print(f"  eciData rebuilt from history: {eci['totalIndustries']} sectors, "
                  f"top3: {[(s['sector'], s['eci']) for s in top]}")
        subs = build_eci_subsectors(hist, data.get('eciData'), today_map)
        if subs is not None:
            data['eciSubsectors'] = subs
            n = sum(len(i['subs']) for i in subs['items'])
            print(f"  eciSubsectors: {len(subs['items'])} parents, {n} subs picked")
    except Exception as e:
        print(f"  Warning: fetch_eci_daily failed: {e}")


def fetch_north_south(pro, trade_date):
    """Fetch northbound and southbound data."""
    time.sleep(API_DELAY)
    north, south = {}, {}
    try:
        df_hsgt = pro.moneyflow_hsgt(trade_date=trade_date)
        if len(df_hsgt) > 0:
            row = df_hsgt.iloc[0]
            north_money = round(float(row.get('north_money', 0)) / 10000, 2)
            north = {'today': north_money, 'week': north_money * 3, 'month': north_money * 10}
    except Exception as e:
        print(f"  Warning: Failed to fetch northbound: {e}")

    try:
        df_ggt = pro.ggt_daily(trade_date=trade_date)
        if len(df_ggt) > 0:
            row = df_ggt.iloc[0]
            south_money = round((float(row.get('buy_amount', 0)) - float(row.get('sell_amount', 0))) / 10000, 2)
            south = {'today': south_money, 'week': south_money * 3, 'month': south_money * 10}
    except Exception as e:
        print(f"  Warning: Failed to fetch southbound: {e}")
    return north, south


# 中证行业指数系列（细分指数每日点评）
# 实测（2026-07，当前 token）：000929/000930/000931/000936/000937 及其深市镜像
# 399929/399930/399931/399936/399937 在 index_daily 均无数据（需更高积分），
# 因此这 5 个板块按顺序回退到覆盖相同行业的其它指数：
#   材料 → 000987.SH 全指材料；工业 → 399383.SZ 中证1000工业；
#   可选 → 000989.SH 全指可选；电信 → 801770.SI 申万通信；公用 → 801160.SI 申万公用事业
# 若 token 升级积分，原 0009xx 代码会自动优先生效。
SECTOR_INDICES = [
    {'codes': ['000928.SH'], 'name': '中证能源'},
    {'codes': ['000929.SH', '000987.SH'], 'name': '中证材料'},
    {'codes': ['000930.SH', '399383.SZ'], 'name': '中证工业'},
    {'codes': ['000931.SH', '000989.SH'], 'name': '中证可选'},
    {'codes': ['000932.SH'], 'name': '中证消费'},
    {'codes': ['000933.SH'], 'name': '中证医药'},
    {'codes': ['000934.SH'], 'name': '中证金融'},
    {'codes': ['000935.SH'], 'name': '中证信息'},
    {'codes': ['000936.SH', '801770.SI'], 'name': '中证电信'},
    {'codes': ['000937.SH', '801160.SI'], 'name': '中证公用'},
]

# 风格归类：用于总评"市场风格偏成长/偏防御"
_GROWTH_SECTORS = {'中证信息', '中证电信', '中证工业', '中证可选'}
_DEFENSIVE_SECTORS = {'中证医药', '中证消费', '中证公用', '中证能源'}


def fetch_sector_commentary(pro, trade_date):
    """拉取中证行业指数近约 6 个交易日行情，自动生成中文简评。

    index_daily 批量 ts_code 实测返回空，逐只查询。
    每条: {code, name, pctChg, close, comment, tone('up'/'down'/'flat')}
    """
    start = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=12)).strftime('%Y%m%d')
    entries = []
    for sector in SECTOR_INDICES:
        df = None
        used_code = None
        for tc in sector['codes']:
            try:
                time.sleep(API_DELAY)
                d = pro.index_daily(ts_code=tc, start_date=start, end_date=trade_date)
                if len(d) > 0:
                    df = d
                    used_code = tc
                    break
            except Exception as e:
                print(f"  Warning: Failed to fetch sector index {tc}: {e}")
        if df is None:
            print(f"  Warning: No data for {sector['name']} ({'/'.join(sector['codes'])})")
            continue
        try:
            df = df.sort_values('trade_date').reset_index(drop=True)
            last = df.iloc[-1]
            pct = round(float(last['pct_chg']), 2)
            close = round(float(last['close']), 2)
            # 连续同向天数（含当日）
            signs = [1 if v > 0 else (-1 if v < 0 else 0) for v in df['pct_chg'].tolist()]
            streak = 0
            cur = signs[-1]
            for s in reversed(signs):
                if s == cur and cur != 0:
                    streak += 1
                else:
                    break
            entries.append({
                'code': used_code,
                'name': sector['name'],
                'pctChg': pct,
                'close': close,
                '_streak': streak,
                '_sign': cur,
            })
        except Exception as e:
            print(f"  Warning: Failed to parse sector index {used_code}: {e}")

    if not entries:
        return []

    # 排名生成点评
    ranked = sorted(entries, key=lambda e: e['pctChg'], reverse=True)
    top2 = {e['code'] for e in ranked[:2]}
    bottom2 = {e['code'] for e in ranked[-2:]}
    for e in entries:
        pct = e['pctChg']
        if e['code'] in top2 and pct > 0:
            comment = '领涨，资金关注度高'
        elif e['code'] in bottom2 and pct < 0:
            comment = '领跌，注意风险'
        elif abs(pct) < 0.3:
            comment = '窄幅震荡'
        elif pct > 0:
            comment = '跟涨，表现平稳'
        else:
            comment = '回调，观望为主'
        if e['_streak'] >= 3:
            comment += f"，{'连涨' if e['_sign'] > 0 else '连跌'}{e['_streak']}日"
        e['comment'] = comment
        e['tone'] = 'up' if pct > 0.3 else ('down' if pct < -0.3 else 'flat')
        del e['_streak']
        del e['_sign']
    return entries


def load_existing_data():
    """Load existing fund_data.json to preserve manually maintained fields."""
    try:
        with open(OUTPUT_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    print("=" * 60)
    print("Fund Hunter - Daily Data Update (Batch Mode)")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not TUSHARE_TOKEN:
        print("ERROR: TUSHARE_TOKEN not set in environment!")
        sys.exit(1)

    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()

    trade_date = get_trade_date(pro)
    print(f"Trade date: {trade_date}")

    data = load_existing_data()

    # ── 1. Indices (batch) ──
    print("\n[1/13] Fetching indices (batch)...")
    indices = fetch_indices_batch(pro, trade_date)
    if indices:
        data['indices'] = indices
        for k, v in indices.items():
            print(f"  {v['name']}: {v['value']} ({v['change']:+.2f}%)")

    # ── 2. Stocks (batch) ──
    print("\n[2/13] Fetching stocks (batch)...")
    stocks = fetch_stocks_batch(pro, trade_date)
    if stocks:
        data['stocks'] = stocks
        print(f"  Updated {len(stocks)} stocks")
        for s in stocks[:3]:
            print(f"    {s['name']}: {s['close']} ({s['pctChg']:+.2f}%)")

    # ── 3. ETFs (batch) ──
    print("\n[3/13] Fetching ETFs (batch)...")
    etfs = fetch_etfs_batch(pro, trade_date)
    if etfs:
        data['nationalETF'] = etfs
        print(f"  Updated {len(etfs)} ETFs")
        for e in etfs[:3]:
            print(f"    {e['name']}: {e['close']} ({e['changePct']:+.2f}%)")

    # ── 4. My ETF account (fund_daily, batch) ──
    print("\n[4/13] Fetching my ETF account (fund_daily, batch)...")
    my_etfs = fetch_my_etfs(pro, trade_date)
    if my_etfs:
        data['myETF'] = my_etfs
        print(f"  Updated {len(my_etfs)} my ETFs")
        for e in my_etfs[:3]:
            print(f"    {e['name']}: {e['close']} ({e['changePct']:+.2f}%)")

    # ── 5. Announcements + holdingsNews (全量覆盖旧手工数据) ──
    print("\n[5/13] Fetching announcements & building holdingsNews...")
    anns_map = fetch_announcements(pro, trade_date)
    data['holdingsNews'] = build_holdings_news(anns_map, trade_date)
    total_anns = sum(len(e['items']) for e in data['holdingsNews'])
    print(f"  Built {len(data['holdingsNews'])} holdingsNews entries, {total_anns} announcements")

    # ── 6. Mainforce flow ──
    print("\n[6/13] Fetching mainforce flow...")
    inflow, outflow = fetch_mainforce_flow(pro, trade_date)
    if inflow:
        data['mainforce_inflow_top10'] = inflow
        print(f"  Inflow #1: {inflow[0]['name']} {inflow[0]['amount']}")
    if outflow:
        data['mainforce_outflow_top10'] = outflow
        print(f"  Outflow #1: {outflow[0]['name']} {outflow[0]['amount']}")

    # ── 7. Hot fund NAVs (fund_nav, 取到才覆盖) ──
    print("\n[7/13] Fetching hot fund NAVs...")
    hot_navs = fetch_hot_fund_navs(pro, trade_date, data.get('hotFundNavs', []))
    if hot_navs:
        data['hotFundNavs'] = hot_navs
        dates = {h.get('date', '') for h in hot_navs}
        print(f"  Updated {len(hot_navs)} fund NAVs, dates: {sorted(dates)}")

    # ── 8. National ETF watch (宽基ETF份额监控) ──
    print("\n[8/13] Fetching national ETF watch (fund_share)...")
    etf_watch = fetch_national_etf_watch(pro, trade_date, data.get('nationalETFWatch'))
    if etf_watch:
        data['nationalETFWatch'] = etf_watch
        t = etf_watch['total']
        print(f"  {len(etf_watch['items'])} ETFs as of {etf_watch['trade_date']}, "
              f"total netFlow {t['netFlow']:+.2f}亿, 5d {t['netFlow5d']:+.2f}亿")

    # ── 9. Bond yields + liquidity commentary (东方财富) ──
    print("\n[9/13] Fetching bond yields & liquidity commentary (eastmoney)...")
    fetch_bond_yields(trade_date, data)

    # ── 10. North/South bound ──
    print("\n[10/13] Fetching north/south bound...")
    north, south = fetch_north_south(pro, trade_date)
    if north:
        data['northbound'] = north
        print(f"  Northbound: {north['today']}亿")
    if south:
        data['southbound'] = south
        print(f"  Southbound: {south['today']}亿")

    # ── 11. Sector index commentary (细分指数每日点评) ──
    print("\n[11/13] Fetching sector index commentary...")
    # 涨跌停信号卡已废弃：不再生成 keySignals，并删除存量字段
    data.pop('keySignals', None)
    commentary = fetch_sector_commentary(pro, trade_date)
    if commentary:
        data['sectorCommentary'] = commentary
        print(f"  Built {len(commentary)} sector commentaries")
        for c in commentary[:3]:
            print(f"    {c['name']}: {c['pctChg']:+.2f}% - {c['comment']}")

    # ── 12. Sector watch: 扫描榜(仅信号) + 底部资金积聚 (Tushare 历史沉淀) ──
    print("\n[12/13] Building sector watch (scan + bottom accumulation)...")
    watch_ctx = fetch_sector_watch(pro, trade_date, data)
    data.pop('conceptHot', None)  # 主题概念领涨栏目已下线，清除存量字段

    # ── 13. ECI 六维分每日真算 + 强势一级行业子板块精选 ──
    print("\n[13/13] Rebuilding ECI from sector history + picking subsectors...")
    fetch_eci_daily(pro, trade_date, data, watch_ctx)

    # ── Metadata ──
    data['updateTime'] = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]} 收盘 (Tushare自动)"
    data['marketStatus'] = '正常交易'

    # ── Save ──
    print(f"\n[Saving] {OUTPUT_PATH}")
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Also save to src/data/
    src_path = OUTPUT_PATH.replace('public/', 'src/data/')
    if 'public/' in OUTPUT_PATH:
        os.makedirs(os.path.dirname(src_path), exist_ok=True)
        with open(src_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[Saving] {src_path}")

    print("\n" + "=" * 60)
    print("SUCCESS!")
    print("=" * 60)


if __name__ == '__main__':
    main()
