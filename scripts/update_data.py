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
    print("\n[1/11] Fetching indices (batch)...")
    indices = fetch_indices_batch(pro, trade_date)
    if indices:
        data['indices'] = indices
        for k, v in indices.items():
            print(f"  {v['name']}: {v['value']} ({v['change']:+.2f}%)")

    # ── 2. Stocks (batch) ──
    print("\n[2/11] Fetching stocks (batch)...")
    stocks = fetch_stocks_batch(pro, trade_date)
    if stocks:
        data['stocks'] = stocks
        print(f"  Updated {len(stocks)} stocks")
        for s in stocks[:3]:
            print(f"    {s['name']}: {s['close']} ({s['pctChg']:+.2f}%)")

    # ── 3. ETFs (batch) ──
    print("\n[3/11] Fetching ETFs (batch)...")
    etfs = fetch_etfs_batch(pro, trade_date)
    if etfs:
        data['nationalETF'] = etfs
        print(f"  Updated {len(etfs)} ETFs")
        for e in etfs[:3]:
            print(f"    {e['name']}: {e['close']} ({e['changePct']:+.2f}%)")

    # ── 4. My ETF account (fund_daily, batch) ──
    print("\n[4/11] Fetching my ETF account (fund_daily, batch)...")
    my_etfs = fetch_my_etfs(pro, trade_date)
    if my_etfs:
        data['myETF'] = my_etfs
        print(f"  Updated {len(my_etfs)} my ETFs")
        for e in my_etfs[:3]:
            print(f"    {e['name']}: {e['close']} ({e['changePct']:+.2f}%)")

    # ── 5. Announcements + holdingsNews (全量覆盖旧手工数据) ──
    print("\n[5/11] Fetching announcements & building holdingsNews...")
    anns_map = fetch_announcements(pro, trade_date)
    data['holdingsNews'] = build_holdings_news(anns_map, trade_date)
    total_anns = sum(len(e['items']) for e in data['holdingsNews'])
    print(f"  Built {len(data['holdingsNews'])} holdingsNews entries, {total_anns} announcements")

    # ── 6. Mainforce flow ──
    print("\n[6/11] Fetching mainforce flow...")
    inflow, outflow = fetch_mainforce_flow(pro, trade_date)
    if inflow:
        data['mainforce_inflow_top10'] = inflow
        print(f"  Inflow #1: {inflow[0]['name']} {inflow[0]['amount']}")
    if outflow:
        data['mainforce_outflow_top10'] = outflow
        print(f"  Outflow #1: {outflow[0]['name']} {outflow[0]['amount']}")

    # ── 7. Hot fund NAVs (fund_nav, 取到才覆盖) ──
    print("\n[7/11] Fetching hot fund NAVs...")
    hot_navs = fetch_hot_fund_navs(pro, trade_date, data.get('hotFundNavs', []))
    if hot_navs:
        data['hotFundNavs'] = hot_navs
        dates = {h.get('date', '') for h in hot_navs}
        print(f"  Updated {len(hot_navs)} fund NAVs, dates: {sorted(dates)}")

    # ── 8. National ETF watch (宽基ETF份额监控) ──
    print("\n[8/11] Fetching national ETF watch (fund_share)...")
    etf_watch = fetch_national_etf_watch(pro, trade_date, data.get('nationalETFWatch'))
    if etf_watch:
        data['nationalETFWatch'] = etf_watch
        t = etf_watch['total']
        print(f"  {len(etf_watch['items'])} ETFs as of {etf_watch['trade_date']}, "
              f"total netFlow {t['netFlow']:+.2f}亿, 5d {t['netFlow5d']:+.2f}亿")

    # ── 9. Bond yields + liquidity commentary (东方财富) ──
    print("\n[9/11] Fetching bond yields & liquidity commentary (eastmoney)...")
    fetch_bond_yields(trade_date, data)

    # ── 10. North/South bound ──
    print("\n[10/11] Fetching north/south bound...")
    north, south = fetch_north_south(pro, trade_date)
    if north:
        data['northbound'] = north
        print(f"  Northbound: {north['today']}亿")
    if south:
        data['southbound'] = south
        print(f"  Southbound: {south['today']}亿")

    # ── 11. Sector index commentary (细分指数每日点评) ──
    print("\n[11/11] Fetching sector index commentary...")
    # 涨跌停信号卡已废弃：不再生成 keySignals，并删除存量字段
    data.pop('keySignals', None)
    commentary = fetch_sector_commentary(pro, trade_date)
    if commentary:
        data['sectorCommentary'] = commentary
        print(f"  Built {len(commentary)} sector commentaries")
        for c in commentary[:3]:
            print(f"    {c['name']}: {c['pctChg']:+.2f}% - {c['comment']}")

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
