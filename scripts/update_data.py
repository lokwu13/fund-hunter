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
API_DELAY = float(os.environ.get('API_DELAY', '1.5'))  # seconds（本地调试可用环境变量调低）
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
    '600521.SH': {'name': '华海药业', 'industry': '化学制药', 'group': 'watch', 'watchPrice': 0},
    '000708.SZ': {'name': '中信特钢', 'industry': '特种钢',   'group': 'watch', 'watchPrice': 0},
}

# 用户 ETF 账户（行情走 fund_daily，与 nationalETF 的 daily 不同）
MY_ETFS = {
    '159883.SZ': {'name': '永赢中证全指医疗器械ETF',   'ticker': '159883'},
    '159892.SZ': {'name': '华夏恒生生物科技ETF(QDII)', 'ticker': '159892'},
    '159265.SZ': {'name': '鹏华国证港股通消费主题ETF', 'ticker': '159265'},
    '159736.SZ': {'name': '天弘中证食品饮料ETF',       'ticker': '159736'},
    '518880.SH': {'name': '华安易富黄金ETF',           'ticker': '518880'},
    '562510.SH': {'name': '华夏中证旅游主题ETF',       'ticker': '562510'},
}

# 备选 ETF 池（2026-08-28 用户指令新增）：纯展示，不进任何信号/预警计算
MY_ETFS_ALT = {
    '159731.SZ': {'name': '华夏中证石化产业ETF',         'ticker': '159731'},
    '512070.SH': {'name': '易方达沪深300非银行金融ETF',  'ticker': '512070'},
    '512800.SH': {'name': '华宝中证银行ETF',             'ticker': '512800'},
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


def fetch_my_etfs(pro, trade_date, etfs=None):
    """Fetch user's own ETF account quotes via fund_daily.

    注意：fund_daily 不支持逗号分隔的批量 ts_code（实测批量返回空），
    因此逐只查询。etfs 默认 MY_ETFS，备选池传 MY_ETFS_ALT（纯展示用）。
    """
    etf_data = []
    for tc, info in (etfs or MY_ETFS).items():
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
BOTTOM_TIERS = (30, 60)         # 双档监测窗口（30日=较新积聚，60日=长期扎实吸筹）
BOTTOM_POS_RATIO = 0.5          # 窗口内净流入天数过半
BOTTOM_PRICE_POS = 0.4          # 价格底部分位上限（沿用原判据：等权累计收益指数长期分位）
BOTTOM_SCALE_PCT = 0.005        # 窗口累计净流入 ≥ 窗口累计成交额的 0.5%（"有一定规模"下限）
BOTTOM_TIER_MIN_ROWS = {30: 25, 60: 50}  # 行业历史不足则该档不判定（不为用不满窗口的板块造假数）
BOTTOM_LEADER_SECTORS = 4       # 只为评分前 4 的板块抓龙头，控制每晚 API 增量


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
    """扫描榜自动总评（items 已只含信号板块，2026-08-22 起含位置分层）。"""
    absorb = [i for i in items if i['status'] == '吸筹中']
    start = [i for i in items if i['status'] == '启动确认']
    risk = [i for i in items if i['status'] == '高潮风险']
    dt = [i for i in items if i['status'] == '双头风险']
    hi = [i for i in items if i['status'] == '高位流入·谨慎']
    parts = []
    if absorb:
        core = [i for i in absorb if i.get('tier') == 'core']
        txt = (f"{len(absorb)}个板块出现吸筹信号："
               + '、'.join(f"{i['sector']}连续{i['consecutiveDays']}日净流入" for i in absorb[:3]))
        if core:
            txt += f"（其中⭐低位 {len(core)} 个）"
        parts.append(txt)
    if start:
        core = [i for i in start if i.get('tier') == 'core']
        txt = f"{len(start)}个板块启动确认（{'、'.join(i['sector'] for i in start[:3])}）"
        if core:
            txt += f"，其中⭐低位 {len(core)} 个"
        parts.append(txt)
    if risk:
        parts.append(f"{len(risk)}个板块存在高潮风险（{'、'.join(i['sector'] for i in risk[:3])}），谨慎追高")
    if dt:
        parts.append(f"{len(dt)}个板块双头风险（{'、'.join(i['sector'] for i in dt[:3])}）：接近前高且流入减速")
    if hi:
        parts.append(f"{len(hi)}个板块高位流入（{'、'.join(i['sector'] for i in hi[:3])}），位置偏高谨慎")
    return '今日' + '；'.join(parts) + '。'


SCAN_POSITION_NOTE = ('位置口径：行业等权收益合成指数近似（非真实板块指数）；'
                      '⭐低位=距60日高点回撤≥3%且近20日涨幅≤10%（回测10日胜率约59%）；'
                      '高位=距60日高点<3%或近20日涨幅>10%（回测10日胜率仅17~29%，信号降级为"高位流入·谨慎"）；'
                      '双头风险=接近前高+连续净流入+流入减速；缩量=近5日均额/前5日均额<0.8，低位缩量吸筹加分')


def build_sector_scan(hist, trade_date, today_map):
    """板块资金扫描榜（精简版）：只保留触发信号的板块，每个板块附 2 只吸筹个股。

    信号规则（2026-08-22 位置分层版，数据来自行业资金历史沉淀）：
    - 位置分层（等权收益合成指数近似，非真实板块指数）：
      高位 = 距60日高点 <3% 或 近20日涨幅 >10%；
      低位 = 距60日高点回撤 ≥3% 且 近20日涨幅 ≤10%；半路 = 历史不足等兜底。
    - 高潮风险：连续净流入 ≥3 天 且 近5日涨幅 ≥8%（任何位置都发，最高优先）
    - 双头风险：高位（距高点<3%）+ 连续净流入 ≥2 天 + 流入减速（当日 < 近3日均值）
    - 启动确认：连续净流入 ≥2 天 且 当日涨幅 ≥1.5%（仅低位/半路发）
    - 吸筹中：连续净流入 ≥3 天 且 当日涨幅 <1%（仅低位/半路发；低位+量比<0.8 标记"缩量"）
    - 高位触发吸筹/启动条件的，改标「高位流入·谨慎」沉底展示
    回测依据（81交易日×110行业）：低位信号10日胜率~59%/中位+1.4~1.9%，
    高位信号胜率17~29%/中位-3.4~-3.8%；高潮风险高位触发 8/8 后续下跌。
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

        # ── 位置分层：等权收益合成指数（与 2026-08-22 回测同口径）──
        px = 1.0
        pxs = []
        for _, _n, r, _a in rows:
            px *= (1 + r / 100.0)
            pxs.append(px)
        win60 = pxs[-60:]
        dist_high = (px / max(win60) - 1) * 100
        ret20 = (px / pxs[-21] - 1) * 100 if len(pxs) >= 21 else None
        if ret20 is None:
            tier = 'mid'  # 历史不足 20 日，兜底半路层
        elif dist_high > -3 or ret20 > 10:
            tier = 'high'
        else:
            tier = 'low'

        # 量比：近5日均额 / 前5日均额
        amt5 = sum(r[3] for r in rows[-5:]) / 5
        amt_prev5 = sum(r[3] for r in rows[-10:-5]) / 5 if len(rows) >= 10 else 0
        vol_ratio = round(amt5 / amt_prev5, 2) if amt_prev5 > 0 else None

        # ── 信号判定（高潮风险 > 双头风险 > 启动/吸筹，高位降级）──
        slowing = consec >= 2 and rows[-1][1] < sum(r[1] for r in rows[-3:]) / 3
        low_vol = tier == 'low' and vol_ratio is not None and vol_ratio < 0.8
        if consec >= 3 and pct5 >= 8:
            status, out_tier = '高潮风险', 'risk'
        elif dist_high > -3 and slowing:
            status, out_tier = '双头风险', 'risk'
        elif consec >= 2 and ret1 >= 1.5:
            if tier == 'high':
                status, out_tier = '高位流入·谨慎', 'high'
            else:
                status, out_tier = '启动确认', ('core' if tier == 'low' else 'mid')
        elif consec >= 3 and ret1 < 1:
            if tier == 'high':
                status, out_tier = '高位流入·谨慎', 'high'
            else:
                status, out_tier = '吸筹中', ('core' if tier == 'low' else 'mid')
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
            'tier': out_tier,
            'distHigh': round(dist_high, 1),
            'ret20': round(ret20, 1) if ret20 is not None else None,
            'volRatio': vol_ratio,
            'lowVol': low_vol,
            'stocks': stocks,
        })
    d = f"{latest[:4]}-{latest[4:6]}-{latest[6:]}"
    if not items:
        return {'trade_date': d, 'summary': '今日无板块触发吸筹/启动/高潮信号，资金以观望为主。', 'items': [],
                'note': SCAN_POSITION_NOTE}
    rank_score = _scan_rank_scores(items, len(items))
    tier_adj = {'core': 30, 'mid': 0, 'high': -50, 'risk': 0}
    for it in items:
        it['score'] = round(it['consecutiveDays'] * 20 + rank_score[id(it)]
                            - (20 if it['pct5d'] > 8 else 0)
                            + tier_adj.get(it['tier'], 0)
                            + (10 if it.get('lowVol') else 0), 1)
    items.sort(key=lambda x: -x['score'])
    return {'trade_date': d, 'summary': _scan_summary(items), 'items': items,
            'note': SCAN_POSITION_NOTE}


def _find_bottom_leaders(pro, trade_date, sector, today_map, max_check=5):
    """率先脱离底部的龙头：今日行业主力净流入前 max_check 只，逐只拉近 60 日行情，
    筛选收盘价站上 20 日线 且 逼近/站上 60 日线（≥95%）且 距 60 日高点 <15%（率先走强）。
    2026-08-29 放宽：原要求严格站上 60 日线，底部启动初期的龙头常仍在 60 日线下方，
    导致板块龙头恒为空（08-28 水力发电/石油加工实证）。"""
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
            if close > ma20 and close >= ma60 * 0.95 and dist <= 15:
                ma_txt = '站上20/60日线' if close > ma60 else '站上20日线·逼近60日线'
                leaders.append({'name': s['name'], 'code': s['code'], 'pctChg': s['pct'],
                                'strength': f"{ma_txt}，距60日高点{dist:.0f}%"})
        except Exception as e:
            print(f"  Warning: bottom leader check failed for {s['code']}: {e}")
    leaders.sort(key=lambda x: -x['pctChg'])
    return leaders[:3]


def _pick_sector_leaders(pro, trade_date, sector, today_map, max_n=3):
    """板块龙头统一口径（bottomWatch 卡片与 leaderStep 第2步共用，禁止各算各的）：
    优先"率先脱离底部"趋势判定；无命中时扶正兜底——今日板块内主力净流入前 N（today_map）。
    返回 (leaders, via)，via: 'trend'=率先脱离底部 / 'inflow'=主力净流入口径。"""
    leaders = _find_bottom_leaders(pro, trade_date, sector, today_map)
    if leaders:
        return leaders[:max_n], 'trend'
    fallback = [{'name': s['name'], 'code': s['code'], 'pctChg': s['pct'],
                 'strength': '今日主力净流入居前（资金口径）'}
                for s in (today_map.get(sector) or [])[:max_n]]
    return fallback, 'inflow'


def build_bottom_watch(hist, pro, trade_date, today_map):
    """底部资金积聚监测（30日/60日双档）：长窗口 + 缓慢持续流入 + 价格底部 + 龙头先行。

    每档独立判定（同一口径，仅窗口长度不同）：
    - 窗口累计净流入 >0 且 ≥ 窗口累计成交额的 0.5%（有一定规模）
    - 净流入天数占比 ≥50%（缓慢持续）
    - 价格底部分位 <0.4（等权累计收益指数处于长期低位，未大幅上涨）
    - 近 5 日仍净流入（积聚仍在进行）
    60日档命中且30日档也命中 = 🔥双档共振（最扎实，排最前）。
    score = 持续性×40% + 累计流入排名分×40% + 底部深度×20%（双档 +30 优先分）。
    行业历史不足该档最低天数时该档不判定；全量历史不足 BOTTOM_MIN_DAYS 时输出 note"数据积累中"。
    """
    industries = set()
    for day in hist['days'].values():
        industries.update(day.get('sectors', {}).keys())
    n_days = len(hist['days'])
    latest = max(hist['days']) if hist['days'] else trade_date
    d = f"{latest[:4]}-{latest[4:6]}-{latest[6:]}"
    result = {'trade_date': d, 'days': n_days, 'windows': list(BOTTOM_TIERS),
              'thresholds': {'posRatio': int(BOTTOM_POS_RATIO * 100),
                             'pricePos': int(BOTTOM_PRICE_POS * 100),
                             'scalePct': BOTTOM_SCALE_PCT * 100,
                             'inflow5d': '仍为正'},
              'counts': {'both': 0, 'd30': 0, 'd60': 0}, 'items': []}
    if n_days < BOTTOM_MIN_DAYS:
        result['note'] = f'数据积累中（已积累 {n_days} 个交易日，满 {BOTTOM_MIN_DAYS} 天后开始判定）'
        return result
    if n_days < BOTTOM_TIER_MIN_ROWS[60]:
        result['note'] = f'60日档数据积累中（已积累 {n_days} 个交易日，随每日增量补足），当前仅判定30日档'
    items = []
    for ind in sorted(industries):
        rows = _history_series(hist, ind)
        if len(rows) < BOTTOM_TIER_MIN_ROWS[30]:
            continue
        inflow5 = sum(r[1] for r in rows[-5:])
        # 价格位置：等权累计收益指数在全部已积累历史（最多 250 日）区间中的分位
        idx = 1.0
        curve = []
        for r in rows:
            idx *= (1 + r[2] / 100.0)
            curve.append(idx)
        lo, hi = min(curve), max(curve)
        price_pos = (curve[-1] - lo) / (hi - lo) if hi > lo else 0.5
        hit = {}
        stat = {}
        for w in BOTTOM_TIERS:
            if len(rows) < BOTTOM_TIER_MIN_ROWS[w]:
                hit[w] = False
                continue
            win = rows[-w:]
            nets = [r[1] for r in win]
            inflow = sum(nets)
            amt = sum(r[3] for r in win)
            pos_ratio = sum(1 for x in nets if x > 0) / len(nets)
            stat[w] = (round(inflow, 2), round(pos_ratio * 100, 1))
            hit[w] = (inflow > 0 and inflow >= amt * BOTTOM_SCALE_PCT
                      and pos_ratio >= BOTTOM_POS_RATIO
                      and price_pos < BOTTOM_PRICE_POS and inflow5 > 0)
        if not (hit.get(30) or hit.get(60)):
            continue
        in30, pr30 = stat.get(30, (0.0, 0.0))
        in60, pr60 = stat.get(60, (0.0, 0.0))
        items.append({'sector': ind, 'hit30': bool(hit.get(30)), 'hit60': bool(hit.get(60)),
                      'both': bool(hit.get(30) and hit.get(60)),
                      'inflow30d': in30, 'inflow60d': in60,
                      'positiveRatio30': pr30, 'positiveRatio60': pr60,
                      'inflow5d': round(inflow5, 2),
                      'pricePosition': round(price_pos, 3)})
    if not items:
        return result
    m = len(items)
    # 排名分按主档口径：命中60日档用60日累计，否则用30日累计
    key_inflow = lambda x: x['inflow60d'] if x['hit60'] else x['inflow30d']
    key_ratio = lambda x: x['positiveRatio60'] if x['hit60'] else x['positiveRatio30']
    by_inflow = sorted(items, key=key_inflow, reverse=True)
    rank = {id(it): (m - 1 - i) / (m - 1) if m > 1 else 0.5 for i, it in enumerate(by_inflow)}
    for it in items:
        it['score'] = round(key_ratio(it) / 100 * 40 + rank[id(it)] * 40
                            + (1 - it['pricePosition']) * 20
                            + (30 if it['both'] else 0), 1)
    items.sort(key=lambda x: (-x['both'], -x['score']))
    items = items[:8]
    counts = {'both': sum(1 for i in items if i['both']),
              'd30': sum(1 for i in items if i['hit30'] and not i['hit60']),
              'd60': sum(1 for i in items if i['hit60'] and not i['hit30'])}
    result['counts'] = counts
    for it in items[:BOTTOM_LEADER_SECTORS]:
        it['leaders'], it['leaderVia'] = _pick_sector_leaders(pro, trade_date, it['sector'], today_map)
    parts = []
    both = [i['sector'] for i in items if i['both']]
    only30 = [i['sector'] for i in items if i['hit30'] and not i['hit60']]
    only60 = [i['sector'] for i in items if i['hit60'] and not i['hit30']]
    if both:
        parts.append(f"🔥双档共振（30日+60日持续积聚）：{'、'.join(both[:4])}")
    if only30:
        parts.append(f"30日档（较新积聚）：{'、'.join(only30[:4])}")
    if only60:
        parts.append(f"60日档（长期吸筹）：{'、'.join(only60[:4])}")
    result['items'] = items
    result['summary'] = (f"{len(items)} 个板块出现底部资金积聚信号——"
                         + '；'.join(parts)
                         + "。长周期资金缓慢流入且价格处于长期低位，关注率先走强的龙头。")
    return result


# ══════════ 总览漏斗：第2步·选龙头 + 第4步·排雷（2026-08-29 用户拍板新增） ══════════

MINE_MF_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'cache', 'mine_moneyflow_cache.json')
MINE_FINA_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    'cache', 'mine_fundamental_cache.json')
MINE_FINA_PERIOD = '20260630'      # 基本面雷使用的最新报告期（中报）
MINE_KEYWORDS = ['处罚', '立案', '问询', '警示', '诉讼', '仲裁', '退市', '违规',
                 '减持', '冻结', '下修', '预亏', '商誉减值', '担保逾期']
_CONCEPT_EXCLUDE = ('昨日', '涨停', '连板', '新高', '新低', '破净', '含一字', 'ST', '退市', 'B股')


def build_leader_step(pro, trade_date, data, today_map):
    """第2步·选龙头（总览漏斗卡数据）。

    - 板块部分严格以第1步输出为输入（2026-08-29 断链修复，禁止另算一套积聚命中）：
      ① actionableSectors 能投名单（subSector 二级口径优先，如 通信/电信运营→电信运营）
      ② bottomWatch 入围命中板块，取并集；同时在两者中出现的板块标注"能投名单·X档"。
      龙头统一走 _pick_sector_leaders（bottomWatch 已算好的直接复用，保证两处一致）。
    - 概念板块：东财 dc_index（单日全板块快照，含领涨股）取"大的活跃概念"——
      剔除纯技术性板块（昨日涨停/历史新高等），要求总市值 ≥300 亿且上涨家数 ≥5，
      按当日涨幅取前 3；成分龙头用 dc_member × 今日全市场涨幅（复用 today_map，0 额外行情调用）。
    概念指数历史短，不套用积聚判定——属"题材活跃轴"，与能投名单独立（口径见 note）。
    每晚新增调用：dc_index 1 次 + dc_member ≤3 次 + 能投独有板块龙头日线 ≤5×2 次。
    """
    out = {'trade_date': f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}",
           'sectors': [], 'concepts': [],
           'note': ('板块龙头=率先脱离底部（站上20日线·逼近/站上60日线·距60日高点<15%），'
                    '无率先龙头时用今日主力净流入居前（资金口径）；'
                    '概念板块=题材活跃轴（与能投名单独立，需自行甄别）：东财概念指数当日口径'
                    '（涨幅+总市值≥300亿+上涨家数≥5，剔除打板/新高类技术板块），仅供人工二筛参考')}
    flat = {s['code']: s for lst in today_map.values() for s in lst}
    bw_items = (data.get('bottomWatch') or {}).get('items', [])
    bw_by_sector = {b['sector']: b for b in bw_items}

    def _norm_leaders(leaders):
        return [{'name': l['name'], 'code': l['code'], 'pctChg': l.get('pctChg', 0),
                 **({'strength': l['strength']} if l.get('strength') else {})}
                for l in (leaders or [])[:3]]

    # ① 能投名单板块（第1步输出，排最前）
    seen = set()
    for it in (data.get('actionableSectors') or {}).get('items', []):
        sub = it.get('subSector') or it.get('sector')
        if sub in seen:
            continue
        bw = bw_by_sector.get(sub)
        if bw and bw.get('leaders'):
            leaders = _norm_leaders(bw['leaders'])
            via = bw.get('leaderVia', 'trend')
            tier = '双档共振' if bw.get('both') else ('60日档' if bw.get('hit60') else '30日档')
            src = f'能投名单·{tier}'
        else:
            leaders, via = _pick_sector_leaders(pro, trade_date, sub, today_map)
            src = '能投名单'
        if leaders:
            out['sectors'].append({'sector': sub, 'source': src, 'fromActionable': True,
                                   'leaderVia': via, 'leaders': leaders})
            seen.add(sub)
    # ② bottomWatch 其余入围板块（能投名单之外的积聚命中）
    for b in bw_items:
        if b['sector'] in seen:
            continue
        if b.get('leaders'):
            leaders, via = _norm_leaders(b['leaders']), b.get('leaderVia', 'trend')
        else:
            leaders, via = _pick_sector_leaders(pro, trade_date, b['sector'], today_map)
        if leaders:
            out['sectors'].append({'sector': b['sector'],
                                   'source': '双档共振' if b.get('both') else ('60日档' if b.get('hit60') else '30日档'),
                                   'fromActionable': False, 'leaderVia': via, 'leaders': leaders})
            seen.add(b['sector'])
    out['sectors'] = out['sectors'][:6]
    # ② 题材活跃轴：大的活跃概念板块（东财概念指数，与能投名单独立）
    try:
        time.sleep(API_DELAY)
        dc = pro.dc_index(trade_date=trade_date)
        if dc is not None and len(dc):
            df = dc[~dc['name'].str.contains('|'.join(_CONCEPT_EXCLUDE))].copy()
            df = df[(df['total_mv'] >= 3_000_000) & (df['up_num'] >= 5)]  # total_mv 单位万元
            df = df.sort_values('pct_change', ascending=False).head(3)
            for _, r in df.iterrows():
                leaders = []
                try:
                    time.sleep(API_DELAY)
                    mb = pro.dc_member(ts_code=r['ts_code'], trade_date=trade_date)
                    for _, m in mb.iterrows():
                        s = flat.get(m['con_code'])
                        if s:
                            leaders.append({'name': s['name'], 'code': m['con_code'], 'pctChg': s['pct']})
                    leaders.sort(key=lambda x: -x['pctChg'])
                except Exception as e:
                    print(f"  Warning: dc_member failed for {r['name']}: {e}")
                if not leaders:
                    leaders = [{'name': r['leading'], 'code': str(r.get('leading_code', '')),
                                'pctChg': round(float(r['leading_pct']), 2)}]
                out['concepts'].append({'name': r['name'],
                                        'pctChange': round(float(r['pct_change']), 2),
                                        'totalMvY': round(float(r['total_mv']) / 1e4, 0),
                                        'upNum': int(r['up_num']),
                                        'leaders': leaders[:3]})
    except Exception as e:
        print(f"  Warning: leader step concepts failed: {e}")
    data['leaderStep'] = out
    print(f"  leaderStep: 板块 {len(out['sectors'])} 个, 概念 {len(out['concepts'])} 个"
          + (f"（{'、'.join(c['name'] for c in out['concepts'])}）" if out['concepts'] else ''))


def _cninfo_anns_for(tc, trade_date, days=7, session=None):
    """单只个股巨潮公告（排雷消息面用，非自选股兜底）。"""
    import requests
    s = session or requests.Session()
    s.headers.update({'User-Agent': UA_BROWSER,
                      'Referer': 'http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice',
                      'X-Requested-With': 'XMLHttpRequest'})
    code = tc.split('.')[0]
    column = 'sse' if tc.endswith('.SH') else 'szse'
    start = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=days)).strftime('%Y-%m-%d')
    end = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    time.sleep(API_DELAY)
    r = s.post('http://www.cninfo.com.cn/new/information/topSearch/query',
               data={'keyWord': code, 'maxNum': 10}, timeout=15)
    org_id = ''
    for it in r.json():
        if it.get('code') == code:
            org_id = it.get('orgId', '')
            break
    time.sleep(API_DELAY)
    r2 = s.post('http://www.cninfo.com.cn/new/hisAnnouncement/query', data={
        'pageNum': 1, 'pageSize': 10, 'column': column, 'tabName': 'fulltext',
        'plate': '', 'stock': f"{code},{org_id}" if org_id else code, 'searchkey': '',
        'secid': '', 'category': '', 'trade': '', 'seDate': f'{start}~{end}',
        'sortName': '', 'sortType': '', 'isHLtitle': 'true'}, timeout=15)
    out = []
    for a in (r2.json().get('announcements') or []):
        title = str(a.get('announcementTitle', '')).replace('<em>', '').replace('</em>', '').strip()
        ts_ms = a.get('announcementTime', 0)
        d = (datetime.utcfromtimestamp(ts_ms / 1000) + timedelta(hours=8)).strftime('%Y-%m-%d') if ts_ms else ''
        if title and d:
            out.append({'title': title, 'date': d})
    return out


def build_mine_watch(pro, trade_date, data):
    """第4步·排雷：入围标的重大缺陷扫描（总览红色卡，无雷也要明示）。

    范围：能投/入围板块龙头 + 概念龙头 + VCP 精扫名单 + 自选持仓观察（去重）。
    三类雷（命中才上榜，不凑数）：
    - 资金面：融资红灯（marginWatch 既有口径直接引用）；近 5 日主力净流出 ≥3 亿
      （moneyflow 每日 1 次全市场调用，缓存 10 天增量累加）；
    - 消息面：近 7 天公告命中 处罚/立案/问询/诉讼/减持/退市 等关键词
      （自选股复用 holdingsNews，0 调用；非自选 ≤5 只走巨潮，≤10 次）；
    - 基本面：最新中报归母净利同比 ≤-30% 或亏损；商誉/归母净资产 >40%
      （fina_indicator + balancesheet，周更缓存，每晚 0 增量）。
    """
    # ── 扫描名单（去重）──
    uni = {}
    for tc, info in STOCKS.items():
        uni[tc] = {'name': info['name'], 'src': '自选'}
    for it in (data.get('vcpStocks') or {}).get('items', []):
        uni.setdefault(it['code'], {'name': it['name'], 'src': 'VCP'})
    for it in (data.get('bottomWatch') or {}).get('items', []):
        for l in (it.get('leaders') or []):
            if l.get('code'):
                uni.setdefault(l['code'], {'name': l['name'], 'src': '板块龙头'})
    for grp in ('sectors', 'concepts'):
        for sec in (data.get('leaderStep') or {}).get(grp, []):
            for l in sec.get('leaders', []):
                if l.get('code'):
                    uni.setdefault(l['code'], {'name': l['name'], 'src': '第2步龙头'})

    mines = {}  # code -> {'types': set, 'details': []}
    def _hit(code, typ, detail, date=''):
        m = mines.setdefault(code, {'types': set(), 'details': []})
        m['types'].add(typ)
        m['details'].append({'type': typ, 'detail': detail, 'date': date})

    # ── ① 资金面：融资红灯（marginWatch 既有口径）+ 主力5日净流出≥3亿（缓存）──
    mw_map = {m.get('code'): m for m in (data.get('marginWatch') or {}).get('items', [])}
    mf_cache = _load_json_cache(MINE_MF_CACHE_PATH, {})
    if trade_date not in mf_cache:
        try:
            time.sleep(API_DELAY)
            mf = pro.moneyflow(trade_date=trade_date)
            if mf is not None and len(mf):
                mf_cache[trade_date] = {r['ts_code']: round(float(r['net_mf_amount']) / 1e4, 2)
                                        for _, r in mf.iterrows() if r['ts_code'] in uni}
        except Exception as e:
            print(f"  Warning: mineWatch moneyflow failed: {e}")
        days_sorted = sorted(mf_cache)[-10:]
        mf_cache = {d: mf_cache[d] for d in days_sorted}
        _save_json_cache(MINE_MF_CACHE_PATH, mf_cache)
    for code, meta in uni.items():
        m = mw_map.get(code)
        if m and (m.get('level') == 'alert' or m.get('triggered')):
            _hit(code, '资金', f"融资红灯：3日融资余额增量占流通市值{m.get('incPct', '?')}%", m.get('trade_date', ''))
        nets = [mf_cache[d][code] for d in sorted(mf_cache)[-5:] if code in mf_cache[d]]
        if len(nets) >= 3:
            net5 = sum(nets)
            if net5 <= -3:
                _hit(code, '资金', f"近5日主力净流出{abs(net5):.1f}亿", trade_date)

    # ── ② 消息面：公告关键词（自选复用 holdingsNews；非自选 ≤5 只巨潮兜底）──
    hn = {}
    for e in (data.get('holdingsNews') or []):
        hn[e.get('code') or ''] = e.get('items') or []
    extra = [c for c in uni if c not in hn][:5]
    extra_anns = {}
    if extra:
        try:
            import requests
            sess = requests.Session()
            for tc in extra:
                try:
                    extra_anns[tc] = _cninfo_anns_for(tc, trade_date, 7, sess)
                except Exception as e:
                    print(f"  Warning: mineWatch cninfo failed for {tc}: {e}")
        except ImportError:
            print("  Warning: requests not installed; mineWatch 消息面仅覆盖自选股")
    cutoff = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=7)).strftime('%Y-%m-%d')
    for code in uni:
        anns = list(hn.get(code) or []) + list(extra_anns.get(code) or [])
        for a in anns:
            title = a.get('title', '')
            if a.get('date', '') >= cutoff and any(k in title for k in MINE_KEYWORDS):
                _hit(code, '消息', f"公告：{title[:38]}", a.get('date', ''))
                break  # 每只股票消息面最多列一条最重

    # ── ③ 基本面：中报净利/商誉（周更缓存）──
    fina_cache = _load_json_cache(MINE_FINA_CACHE_PATH, {})
    today_str = datetime.now().strftime('%Y-%m-%d')
    need = [c for c in uni
            if fina_cache.get(c, {}).get('period') != MINE_FINA_PERIOD
            or (datetime.now() - datetime.strptime(fina_cache[c].get('at', '2000-01-01'), '%Y-%m-%d')).days > 7]
    for tc in need[:40]:  # 周更刷新，单次运行硬上限
        rec = {'period': MINE_FINA_PERIOD, 'at': today_str}
        try:
            time.sleep(API_DELAY)
            fi = pro.fina_indicator(ts_code=tc, period=MINE_FINA_PERIOD,
                                    fields='ts_code,end_date,netprofit_yoy')
            if fi is not None and len(fi):
                v = fi.iloc[0]['netprofit_yoy']
                rec['yoy'] = round(float(v), 1) if pd.notna(v) else None
            time.sleep(API_DELAY)
            inc = pro.income(ts_code=tc, period=MINE_FINA_PERIOD,
                             fields='ts_code,end_date,n_income_attr_p')
            if inc is not None and len(inc):
                ni = inc.iloc[0]['n_income_attr_p']
                rec['nIncome'] = round(float(ni) / 1e8, 2) if pd.notna(ni) else None
            time.sleep(API_DELAY)
            bs = pro.balancesheet(ts_code=tc, period=MINE_FINA_PERIOD,
                                  fields='ts_code,goodwill,total_hldr_eqy_exc_min_int')
            if bs is not None and len(bs):
                gw, eq = bs.iloc[0]['goodwill'], bs.iloc[0]['total_hldr_eqy_exc_min_int']
                if pd.notna(gw) and pd.notna(eq) and float(eq) > 0:
                    rec['gwRatio'] = round(float(gw) / float(eq) * 100, 1)
        except Exception as e:
            print(f"  Warning: mineWatch fina failed for {tc}: {e}")
        fina_cache[tc] = rec
    if need:
        _save_json_cache(MINE_FINA_CACHE_PATH, fina_cache)
    for code in uni:
        r = fina_cache.get(code) or {}
        if r.get('period') != MINE_FINA_PERIOD:
            continue
        if r.get('nIncome') is not None and r['nIncome'] < 0:
            _hit(code, '基本面', f"中报亏损（归母净利{r['nIncome']}亿）", MINE_FINA_PERIOD)
        elif r.get('yoy') is not None and r['yoy'] <= -30:
            _hit(code, '基本面', f"中报归母净利同比{r['yoy']}%", MINE_FINA_PERIOD)
        if r.get('gwRatio') is not None and r['gwRatio'] > 40:
            _hit(code, '基本面', f"商誉/归母净资产{r['gwRatio']}%", MINE_FINA_PERIOD)

    items = []
    for code, m in mines.items():
        items.append({'code': code, 'name': uni[code]['name'], 'src': uni[code]['src'],
                      'types': sorted(m['types']), 'details': m['details']})
    items.sort(key=lambda x: (-len(x['types']), x['code']))
    data['mineWatch'] = {
        'trade_date': f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}",
        'checked': len(uni),
        'items': items,
        'thresholds': ('资金=融资红灯(marginWatch既有口径)或近5日主力净流出≥3亿；'
                       '消息=近7天公告命中处罚/立案/问询/诉讼/减持/退市等关键词；'
                       '基本面=中报归母净利同比≤-30%或亏损、商誉/净资产>40%（周更缓存）'),
    }
    # 联动第2步：有雷的板块/概念龙头在 leaderStep 里就地打 ⛔ 标记
    mined = {m['code']: m['types'] for m in items}
    ls = data.get('leaderStep')
    if ls and mined:
        for grp in list(ls.get('sectors', [])) + list(ls.get('concepts', [])):
            for l in grp.get('leaders', []):
                if l.get('code') in mined:
                    l['mine'] = mined[l['code']]
    print(f"  mineWatch: 扫描 {len(uni)} 只, 上榜 {len(items)} 只"
          + (f"（{'、'.join(i['name'] for i in items[:6])}）" if items else '，今日无雷'))


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
        update_bottom_freshness(bottom, hist)
        data['bottomWatch'] = bottom
        if bottom.get('note') and not bottom['items']:
            print(f"  bottomWatch: {bottom['note']}")
        else:
            c = bottom.get('counts', {})
            print(f"  bottomWatch: {len(bottom['items'])} triggered sectors "
                  f"(🔥双档{c.get('both', 0)} / 30日档{c.get('d30', 0)} / 60日档{c.get('d60', 0)})")
            if bottom.get('note'):
                print(f"  note: {bottom['note']}")
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
    """强势一级行业子板块分级展示：达标精选 + 观察池。

    达标（金标准，不放松）：母板块 ECI前10 且 30日累计净流入>0 且 30日流入天数占比≥50%；
    子板块四维简版打分（0-15×4 折算百分制）：资金集中度/趋势同步(20日上涨天数占比)/
    一致性动量/活跃度；选得分前 3 且 30日净流入>0（宁缺毋滥，可少于 3 个甚至为 0）；
    每个入选子板块带今日主力净流入前 2 的龙头。
    观察池：ECI前10 中未达标但接近的——(30日净流入>0 且 流入天数占比≥40%) 或 ECI前5 之一；
    每行带差距说明，灰蓝样式区别于达标。
    """
    days = sorted(hist['days'])
    if len(days) < 40:
        return None
    latest = days[-1]
    # 一级 30 日聚合（母板块资金条件）
    l1_30 = {}
    for d in days[-30:]:
        for ind, s in hist['days'][d].get('sectors', {}).items():
            l1 = SECTOR_TO_L1.get(ind)
            if not l1:
                continue
            a = l1_30.setdefault(l1, {'net': 0.0, 'pos': 0, 'n': 0})
            a['net'] += s.get('net', 0.0)
            a['pos'] += 1 if s.get('net', 0.0) > 0 else 0
            a['n'] += 1
    top10 = sorted((eci_data or {}).get('sectors', []), key=lambda x: -x.get('eci', 0))[:10]
    top5_names = {s['sector'] for s in top10[:5]}
    items = []
    watchlist = []
    for sec in top10:
        parent = sec['sector']
        a = l1_30.get(parent)
        net30 = a['net'] if a else 0.0
        pos_ratio = (a['pos'] / a['n']) if a and a['n'] else 0.0
        if not (a and a['n'] > 0 and net30 > 0 and pos_ratio >= 0.5):
            # 观察池：未完全达标但接近（金标准不放松，仅分级展示）
            if (net30 > 0 and pos_ratio >= 0.4) or (parent in top5_names):
                if net30 <= 0:
                    gap = f'30日净流出{abs(net30):.1f}亿，待资金回正'
                elif pos_ratio < 0.4:
                    gap = f'流入占比{pos_ratio * 100:.1f}%，不足40%'
                else:
                    gap = f'流入占比{pos_ratio * 100:.1f}%，未过半'
                watchlist.append({'parent': parent, 'eci': sec['eci'],
                                  'inflow30d': round(net30, 2),
                                  'posRatio': round(pos_ratio * 100, 1),
                                  'gap': gap})
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
            net30 = sum(r[1] for r in rows[-30:])
            pos30 = sum(1 for r in rows[-30:] if r[1] > 0) / len(rows[-30:])
            amt20 = sum(r[3] for r in rows[-20:])
            stat_list.append({
                'name': ind, 'net30': net30, 'pos30': pos30,
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
        picked = [s for s in sorted(stat_list, key=lambda x: -x['eci']) if s['net30'] > 0][:3]
        if not picked:
            continue
        subs = [{
            'name': s['name'], 'eci': s['eci'], 'inflow20d': s['inflow20d'],
            'positiveRatio': round(s['pos30'] * 100, 1),
            'leaders': [{'name': t['name'], 'code': t['code'], 'pctChg': t['pct']}
                        for t in (today_map.get(s['name']) or [])[:2]],
        } for s in picked]
        items.append({'parent': parent, 'parentEci': sec['eci'], 'subs': subs})
    return {
        'trade_date': f"{latest[:4]}-{latest[4:6]}-{latest[6:]}",
        'items': items,
        'watchlist': watchlist,
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
            # 5日变化标记：同一口径把历史窗口前移 5 个交易日重算一次做对比（无需额外存储）
            days_all = sorted(hist['days'])
            if len(days_all) >= 45:
                cutoff = days_all[-6]
                hist5 = {'days': {d: v for d, v in hist['days'].items() if d <= cutoff}}
                prev = _rebuild_eci_from_history(hist5, data.get('eciData'))
                if prev:
                    prev_map = {s['sector']: s['eci'] for s in prev['sectors']}
                    for s in eci['sectors']:
                        p = prev_map.get(s['sector'])
                        if p is not None:
                            s['change5d'] = round(s['eci'] - p, 1)
            data['eciData'] = eci
            # 月度变化标记：同一口径把历史窗口前移 21 个交易日重算一次做对比
            # （sector_history 即 ECI 历史沉淀，无需另建缓存；不足 62 天时前端暂用 change5d 并标注）
            if len(days_all) >= 62:
                cutoff = days_all[-22]
                hist21 = {'days': {d: v for d, v in hist['days'].items() if d <= cutoff}}
                prev = _rebuild_eci_from_history(hist21, data.get('eciData'))
                if prev:
                    prev_map = {s['sector']: s['eci'] for s in prev['sectors']}
                    for s in eci['sectors']:
                        p = prev_map.get(s['sector'])
                        if p is not None:
                            s['change1m'] = round(s['eci'] - p, 1)
            top = sorted(eci['sectors'], key=lambda x: -x['eci'])[:3]
            print(f"  eciData rebuilt from history: {eci['totalIndustries']} sectors, "
                  f"top3: {[(s['sector'], s['eci']) for s in top]}")
        subs = build_eci_subsectors(hist, data.get('eciData'), today_map)
        if subs is not None:
            data['eciSubsectors'] = subs
            n = sum(len(i['subs']) for i in subs['items'])
            print(f"  eciSubsectors: {len(subs['items'])} parents, {n} subs picked, "
                  f"watchlist: {[w['parent'] for w in subs.get('watchlist', [])]}")
    except Exception as e:
        print(f"  Warning: fetch_eci_daily failed: {e}")


MARGIN_HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', 'margin_history.json')
MARGIN_HISTORY_MAX_DAYS = 60    # 每只股票保留最近交易日数
MARGIN_BACKFILL_CAL_DAYS = 90   # 首次回补日历日（覆盖约 60 个交易日）
MARGIN_TRIGGER_PCT = 3.0        # 红灯阈值：3日融资余额增量 ÷ 流通市值 ≥3%
MARGIN_WATCH_DAYS = 5           # 黄灯：连续增持交易日数
MARGIN_WATCH_PCT = 0.5          # 黄灯：5日累计增量 ÷ 流通市值 ≥0.5%


def _load_margin_history():
    try:
        with open(MARGIN_HISTORY_PATH, encoding='utf-8') as f:
            h = json.load(f)
        return h if isinstance(h.get('stocks'), dict) else {'stocks': {}}
    except Exception:
        return {'stocks': {}}


def _save_margin_history(hist):
    os.makedirs(os.path.dirname(MARGIN_HISTORY_PATH), exist_ok=True)
    for entry in hist['stocks'].values():
        days = entry.get('days', {})
        keep = sorted(days)[-MARGIN_HISTORY_MAX_DAYS:]
        entry['days'] = {d: days[d] for d in keep}
    with open(MARGIN_HISTORY_PATH, 'w', encoding='utf-8') as f:
        json.dump(hist, f, ensure_ascii=False)


def _update_margin_stock(pro, code, hist, trade_date):
    """增量更新单只股票的 rzye(亿)/circ_mv(亿) 日线缓存，返回 sorted 日期列表。

    rzye：margin_detail 融资余额（元）→ 亿；circ_mv：daily_basic 流通市值（万元）→ 亿。
    """
    entry = hist['stocks'].setdefault(code, {'days': {}})
    days = entry['days']
    if days:
        start = (datetime.strptime(max(days), '%Y%m%d') - timedelta(days=10)).strftime('%Y%m%d')
    else:
        start = (datetime.strptime(trade_date, '%Y%m%d')
                 - timedelta(days=MARGIN_BACKFILL_CAL_DAYS)).strftime('%Y%m%d')
    time.sleep(API_DELAY)
    md = pro.margin_detail(ts_code=code, start_date=start, end_date=trade_date,
                           fields='ts_code,trade_date,rzye')
    time.sleep(API_DELAY)
    db = pro.daily_basic(ts_code=code, start_date=start, end_date=trade_date,
                         fields='ts_code,trade_date,circ_mv')
    mv_map = {}
    if db is not None and len(db) > 0:
        for _, r in db.iterrows():
            if pd.notna(r['circ_mv']):
                mv_map[str(r['trade_date'])] = float(r['circ_mv']) / 1e4  # 万元→亿
    if md is not None and len(md) > 0:
        for _, r in md.iterrows():
            if pd.isna(r['rzye']):
                continue
            d = str(r['trade_date'])
            cur = days.setdefault(d, {})
            cur['rzye'] = round(float(r['rzye']) / 1e8, 4)  # 元→亿
    for d, mv in mv_map.items():
        if d in days:
            days[d]['circ_mv'] = round(mv, 2)
    if not days:
        raise ValueError(f'no margin data for {code}')
    return sorted(days)


def fetch_margin_watch(pro, trade_date, data):
    """融资余额突变预警：红灯=3 日融资余额增量 ÷ 流通市值 ≥3%；黄灯=连续 5 日增持且 5 日累计增量占流通市值 ≥0.5%。

    口径：inc3d/inc5d = rzye最新 − rzye前3/前5个交易日（亿元）；incPct = 增量 / circ_mv × 100。
    Tushare 融资融券口径，T+1 披露。单只失败保留旧条目。
    level: "alert"(红) / "watch"(黄) / None，红灯优先级高于黄灯。
    """
    try:
        hist = _load_margin_history()
        old_items = {it['code']: it for it in (data.get('marginWatch') or {}).get('items', [])}
        items = []
        latest_dates = []
        for code, info in STOCKS.items():
            try:
                dates = _update_margin_stock(pro, code, hist, trade_date)
                if len(dates) < 6:
                    raise ValueError(f'only {len(dates)} days cached')
                days = hist['stocks'][code]['days']
                d1, d0 = dates[-1], dates[-4]
                latest_dates.append(d1)
                circ = days[d1].get('circ_mv') or next(
                    (days[d]['circ_mv'] for d in reversed(dates) if days[d].get('circ_mv')), None)
                if not circ:
                    raise ValueError('no circ_mv')
                inc3d = round(days[d1]['rzye'] - days[d0]['rzye'], 2)
                inc_pct = round(inc3d / circ * 100, 2)
                # 黄灯：连续 N 个交易日增持（每天 rzye 较前一日增加）
                consec = 0
                for i in range(len(dates) - 1, 0, -1):
                    if days[dates[i]]['rzye'] > days[dates[i - 1]]['rzye']:
                        consec += 1
                    else:
                        break
                inc5d = round(days[d1]['rzye'] - days[dates[-6]]['rzye'], 2)
                inc5d_pct = round(inc5d / circ * 100, 2)
                red = inc_pct >= MARGIN_TRIGGER_PCT
                yellow = consec >= MARGIN_WATCH_DAYS and inc5d_pct >= MARGIN_WATCH_PCT
                level = 'alert' if red else ('watch' if yellow else None)
                items.append({
                    'code': code, 'name': info['name'], 'group': info['group'],
                    'rzye': round(days[d1]['rzye'], 2), 'inc3d': inc3d, 'incPct': inc_pct,
                    'inc5d': inc5d, 'inc5dPct': inc5d_pct,
                    'consecutiveUpDays': consec,
                    'triggered': red, 'level': level,
                })
            except Exception as e:
                print(f"  Warning: margin watch {code} failed: {e}")
                if code in old_items:
                    items.append(old_items[code])
        _save_margin_history(hist)
        items.sort(key=lambda x: -x.get('incPct', 0))
        td = max(latest_dates) if latest_dates else trade_date
        data['marginWatch'] = {
            'trade_date': f"{td[:4]}-{td[4:6]}-{td[6:]}",
            'threshold': MARGIN_TRIGGER_PCT,
            'items': items,
        }
        trig = [(i['name'], i['level']) for i in items if i.get('level')]
        print(f"  marginWatch: {len(items)} stocks as of {td}, signals: {trig or '无'}")
    except Exception as e:
        print(f"  Warning: fetch_margin_watch failed: {e}")


def fetch_north_south(pro, trade_date):
    """北向成交额 + 南向净买入（真实历史累计口径）。

    口径说明（2026-08 实测）：
    - moneyflow_hsgt 的 north_money 自 2024-08 官方停披净买入后实为【北向成交总额】（百万），
      hgt+sgt 与之吻合；因此北向只展示成交额，不再冒充"净买入"。
    - ggt_daily 的 buy_amount-sell_amount 为南向真实净买入（亿，港元），该口径官方仍披露。
    week/month 均为近 5/20 个交易日真实累计，不做倍数估算。
    """
    north, south = {}, {}
    start = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=45)).strftime('%Y%m%d')
    try:
        time.sleep(API_DELAY)
        df_hsgt = pro.moneyflow_hsgt(start_date=start, end_date=trade_date)
        if df_hsgt is not None and len(df_hsgt) > 0:
            df_hsgt = df_hsgt.sort_values('trade_date')
            vals = [float(v) / 100 for v in df_hsgt['north_money']]  # 百万→亿
            d_last = str(df_hsgt['trade_date'].iloc[-1])
            north = {
                'today': round(vals[-1], 1),
                'week': round(sum(vals[-5:]), 1),
                'month': round(sum(vals[-20:]), 1),
                'updateTime': f'{d_last[:4]}-{d_last[4:6]}-{d_last[6:]}',
                'note': '北向成交总额（亿元）；官方2024-08起停披净买入，仅披露成交额',
            }
    except Exception as e:
        print(f"  Warning: Failed to fetch northbound: {e}")

    try:
        time.sleep(API_DELAY)
        df_ggt = pro.ggt_daily(start_date=start, end_date=trade_date)
        if df_ggt is not None and len(df_ggt) > 0:
            df_ggt = df_ggt.sort_values('trade_date')
            nets = [float(r['buy_amount']) - float(r['sell_amount']) for _, r in df_ggt.iterrows()]
            d_last = str(df_ggt['trade_date'].iloc[-1])
            south = {
                'today': round(nets[-1], 2),
                'week': round(sum(nets[-5:]), 2),
                'month': round(sum(nets[-20:]), 2),
                'updateTime': f'{d_last[:4]}-{d_last[4:6]}-{d_last[6:]}',
            }
    except Exception as e:
        print(f"  Warning: Failed to fetch southbound: {e}")
    return north, south


def fetch_margin_summary(pro, trade_date, data):
    """全市场两融余额自动日更（Tushare margin，沪深北三所合计）。

    T+1 口径：交易日当晚披露前一交易日数据，updateTime 如实标注数据日期。
    daily 滚动保留最近 40 个交易日；totalBalance/finBalance/secBalance/trend/comment 自动重算。
    """
    try:
        start = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=120)).strftime('%Y%m%d')
        time.sleep(API_DELAY)
        df = pro.margin(start_date=start, end_date=trade_date)
        if df is None or not len(df):
            raise ValueError('margin empty')
        agg = df.groupby('trade_date')[['rzye', 'rqye', 'rzrqye']].sum().sort_index()
        days = list(agg.index[-40:])
        if len(days) < 2:
            raise ValueError('margin history too short')
        daily = [{
            'date': f'{td[4:6]}-{td[6:]}',
            'total': round(float(agg.loc[td, 'rzrqye']) / 1e8),
            'fin': round(float(agg.loc[td, 'rzye']) / 1e8, 2),
            'sec': round(float(agg.loc[td, 'rqye']) / 1e8, 2),
        } for td in days]
        latest, prev = daily[-1], daily[-2]
        td_last = days[-1]
        update_time = f'{td_last[:4]}-{td_last[4:6]}-{td_last[6:]}'
        chg = latest['total'] - prev['total']
        # 连续升/降天数
        streak, direction = 0, 0
        for i in range(len(daily) - 1, 0, -1):
            diff = daily[i]['total'] - daily[i - 1]['total']
            if diff == 0:
                break
            sign = 1 if diff > 0 else -1
            if direction == 0:
                direction = sign
            if sign != direction:
                break
            streak += 1
        d5 = latest['total'] - daily[-6]['total'] if len(daily) >= 6 else chg
        trend = '上升' if d5 > 0 else ('下降' if d5 < 0 else '持平')
        md = f"{int(td_last[4:6])}月{int(td_last[6:])}日"
        c = f"截至{md}两融余额{latest['total']:.0f}亿，较前日{'增加' if chg >= 0 else '减少'}约{abs(chg):.0f}亿"
        if streak >= 2:
            c += f"，连续{streak}日{'上升' if direction > 0 else '下降'}"
        c += f"。融资余额{latest['fin']:.0f}亿，融券余额{latest['sec']:.0f}亿。"
        if d5 > 0:
            c += "杠杆资金持续回流，市场风险偏好回升。"
        elif d5 < 0:
            c += "杠杆资金持续离场，市场风险偏好下降。"
        else:
            c += "杠杆资金总体观望，市场风险偏好平稳。"

        # ── 水温 + 做多结论（A. 结论先行，依据随后）──
        bd = data.get('bondData') or {}
        lt = bd.get('liquidityTools') or {}
        dr007 = float(lt.get('dr007') or 0)
        policy = float(lt.get('policyRate') or 0)
        net = float(lt.get('monthlyNet') or 0)
        y10_1m = ((bd.get('stats') or {}).get('1m_change') or {}).get('y10')  # bp
        loose = bool((dr007 and policy and dr007 <= policy - 0.05)
                     or net > 0 or (y10_1m is not None and y10_1m < 0))
        tight = bool((dr007 and policy and dr007 >= policy + 0.05 and net < 0)
                     or (y10_1m is not None and y10_1m > 20))
        if streak >= 5 and direction > 0 and loose and not tight:
            temp, verdict = '🟢暖', '支持'
        elif (streak >= 5 and direction < 0) or tight:
            temp, verdict = '🔴冷', '不支持'
        else:
            temp, verdict = '🟡平', '中性（谨慎）'
        basis = []
        if streak >= 2:
            basis.append(f"两融连续{streak}日{'上升' if direction > 0 else '下降'}")
        basis.append(f"较前日{'增加' if chg >= 0 else '减少'}约{abs(chg):.0f}亿")
        if dr007 and policy:
            basis.append(f"DR007 {dr007:.2f}%{'低于' if dr007 < policy else '高于'}政策利率{policy:.2f}%")
        if net:
            basis.append(f"本月公开市场净{'投放' if net > 0 else '回笼'}{abs(net):.0f}亿")
        if y10_1m is not None:
            basis.append(f"10Y收益率近1月{y10_1m:+.0f}bp")
        conclusion = {
            '支持': '支持股票市场做多',
            '不支持': '不支持股票市场做多',
            '中性（谨慎）': '中性，股票市场做多需谨慎',
        }[verdict]
        c += (f"水温{temp}（{'；'.join(basis)}）。"
              f"结论：当前杠杆资金环境{conclusion}。")
        mt = data.setdefault('bondData', {}).setdefault('marginTrading', {})
        mt.update({
            'updateTime': update_time,
            'totalBalance': float(latest['total']),
            'finBalance': latest['fin'],
            'secBalance': latest['sec'],
            'trend': trend,
            'temp': temp,
            'verdict': verdict,
            'daily': daily,
            'comment': c,
        })
        ds = data.setdefault('dataSources', {}).setdefault('marginTrading', {})
        ds.update({'source': 'Tushare margin（沪深北交易所两融汇总）', 'freq': '日更',
                   'lastUpdate': update_time, 'note': 'T+1口径：交易日当晚更新前一交易日数据'})
        print(f"  marginTrading: {update_time} 余额{latest['total']:.0f}亿 近5日{d5:+.0f}亿")
    except Exception as e:
        print(f"  Warning: fetch_margin_summary failed: {e}")


def fetch_southbound_concentration(pro, trade_date, data):
    """南向持股集中度 TOP10（Tushare hk_hold 批量，交易日盘后更新）。"""
    try:
        d = trade_date
        df = None
        for _ in range(5):
            time.sleep(API_DELAY)
            df = pro.hk_hold(trade_date=d)
            if df is not None and len(df):
                break
            d = (datetime.strptime(d, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
        if df is None or not len(df):
            raise ValueError('hk_hold empty')
        top = df.sort_values('ratio', ascending=False).head(10)
        items = [{
            'name': r['name'], 'code': r['ts_code'],
            'ratio': f"{float(r['ratio']):.2f}%",
            'vol': int(r['vol']), 'concept': '—', 'sector': '—',
        } for _, r in top.iterrows()]
        data['southbound_concentration_top10'] = items
        ds = data.setdefault('dataSources', {}).setdefault('southbound_concentration_top10', {})
        ds.update({'source': 'Tushare hk_hold（港交所CCASS港股通持股）', 'freq': '日更',
                   'lastUpdate': f'{d[:4]}-{d[4:6]}-{d[6:]}',
                   'note': '港股通持股占港股总股本比例，交易日盘后更新；名称为港交所登记繁体原名'})
        print(f"  southbound_concentration_top10: as of {d}, top {items[0]['name']} {items[0]['ratio']}")
    except Exception as e:
        print(f"  Warning: fetch_southbound_concentration failed: {e}")


def fetch_leverage_concentration(pro, trade_date, data):
    """杠杆资金控盘集中度 TOP10（margin_detail 融资余额 / daily_basic 流通市值，T+1）。"""
    try:
        d = trade_date
        md = None
        for _ in range(5):
            time.sleep(API_DELAY)
            md = pro.margin_detail(trade_date=d)
            if md is not None and len(md):
                break
            d = (datetime.strptime(d, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
        if md is None or not len(md):
            raise ValueError('margin_detail empty')
        time.sleep(API_DELAY)
        db = pro.daily_basic(trade_date=d, fields='ts_code,circ_mv')
        if db is None or not len(db):
            raise ValueError('daily_basic empty')
        mv = dict(zip(db['ts_code'], db['circ_mv'].astype(float)))  # 万元
        # 个股名称：data['stocks'] 仅覆盖自选观察名单（list），改用 stock_basic 全市场映射
        time.sleep(API_DELAY)
        sb = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
        names = dict(zip(sb['ts_code'], sb['name'])) if sb is not None and len(sb) else {}
        rows = []
        for _, r in md.iterrows():
            cap = mv.get(r['ts_code'])
            if not cap or cap <= 0:
                continue
            ratio = float(r['rzye']) / 1e4 / cap * 100  # 元→万元 / 万元
            rows.append({'code': r['ts_code'], 'name': names.get(r['ts_code'], r['ts_code'].split('.')[0]),
                         'ratio': f"{ratio:.2f}%", 'concept': '—'})
        rows.sort(key=lambda x: -float(x['ratio'].rstrip('%')))
        items = [{'rank': i + 1, **row} for i, row in enumerate(rows[:10])]
        data['leverage_concentration_top10'] = items
        ds = data.setdefault('dataSources', {}).setdefault('leverage_concentration_top10', {})
        ds.update({'source': 'Tushare margin_detail + daily_basic', 'freq': '日更',
                   'lastUpdate': f'{d[:4]}-{d[4:6]}-{d[6:]}',
                   'note': '融资余额占流通市值比，T+1口径每日更新'})
        print(f"  leverage_concentration_top10: as of {d}, top {items[0]['name']} {items[0]['ratio']}")
    except Exception as e:
        print(f"  Warning: fetch_leverage_concentration failed: {e}")


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


def build_sector_flows(data):
    """三档净流入（任务：sectorPeriod 扩展）：近5/10/20日主力净流入 + 资金节奏标签。

    全部用 sector_history 缓存计算（Tushare 二级行业口径，与板块资金表的 data.sectors 同名），
    不新增接口。
    """
    try:
        hist = _load_sector_history()
        days = sorted(hist['days'])
        if len(days) < 20:
            print(f"  sectorFlows: history only {len(days)} days, keep old")
            return
        agg = {}
        for d in days[-20:]:
            for ind, s in hist['days'][d]['sectors'].items():
                agg.setdefault(ind, []).append(s.get('net', 0.0))
        rows = []
        for ind, nets in agg.items():
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
            rows.append({'name': ind, 'net5': round(n5, 1), 'net10': round(n10, 1),
                         'net20': round(n20, 1), 'tag': tag})
        rows.sort(key=lambda x: -x['net5'])
        d1 = days[-1]
        data['sectorFlows'] = {
            'trade_date': f'{d1[:4]}-{d1[4:6]}-{d1[6:]}',
            'items': rows,
            'note': 'Tushare 二级行业主力净流入；节奏=近5日日均 vs 前5日日均（加速流入/减速流入/拐点/持续流出）',
        }
        print(f"  sectorFlows: {len(rows)} industries as of {d1}, "
              f"top: {[(r['name'], r['net5'], r['tag']) for r in rows[:3]]}")
    except Exception as e:
        print(f"  Warning: build_sector_flows failed: {e}")


def _vcp_append_rows(old_rows, new_rows, max_len=300):
    """把新抓的日线行并入口径一致的缓存行（按日期去重追加，裁尾）。"""
    seen = {r[0] for r in old_rows}
    out = list(old_rows) + [r for r in new_rows if r[0] not in seen]
    out.sort()
    return out[-max_len:]


def fetch_vcp_watch(pro, trade_date, data):
    """VCP 板块-龙头共振监测（并入版，每晚增量控制成本）。

    增量方案：龙头个股日线用 daily(trade_date) 全市场批量 1 次本地过滤追加；
    指数日线增量 31 SW + 15 概念 ≈46 次；daily_basic 批量 1 次；
    成分股名单/流通市值/龙头名单 每周五刷新。全部读写给 vcp_preview 同一缓存。
    失败时保留旧 vcpWatch，不中断主流程。
    """
    try:
        import vcp_preview as vcp
        c = vcp.load_cache()
        cold = not c.get('sw_list')
        if cold:
            # 冷启动（仅首次）：全量首抓，与样张脚本同路径
            print('  vcpWatch cold start: full bootstrap (~250 calls)')
            vcp.ensure_basics(pro, c)
            vcp.ensure_sw_list(pro, c)
            vcp.ensure_stock_basic(pro, c)
            vcp.ensure_circ_mv(pro, c)
            vcp.ensure_sw_members(pro, c)
            vcp.ensure_concepts(pro, c)
            vcp.ensure_leaders(c)
            vcp.ensure_index_daily(pro, c)
            vcp.ensure_stock_daily(pro, c)
        else:
            # 盘中/早间数据可能尚未发布：逐日回探到首个有数据的交易日，只重算不追加
            eff = None
            df_probe = None
            for k in range(0, 8):
                d = (datetime.strptime(trade_date, '%Y%m%d')
                     - timedelta(days=k)).strftime('%Y%m%d')
                df_probe = vcp.api(pro, 'daily_basic', trade_date=d,
                                   fields='ts_code,trade_date,circ_mv')
                if df_probe is not None and len(df_probe) > 0:
                    eff = d
                    break
            if not eff:
                raise RuntimeError('vcpWatch: no daily_basic data in last 8 days')
            if eff != trade_date:
                print(f'  vcpWatch: {trade_date} 数据未发布，回退有效日期 {eff}')
            c['trade_date'] = eff
            start = (datetime.strptime(eff, '%Y%m%d')
                     - timedelta(days=10)).strftime('%Y%m%d')
            # ── 每周五：成分/市值/龙头名单刷新 ──
            if datetime.strptime(eff, '%Y%m%d').weekday() == 4:
                print('  vcpWatch Friday refresh: members + circ_mv + leaders')
                vcp.ensure_stock_basic(pro, c)
                c.pop('circ_mv', None)
                vcp.ensure_circ_mv(pro, c)
                for s in c['sw_list']:
                    df = vcp.api(pro, 'index_member', index_code=s['code'])
                    c['sw_members'][s['code']] = [
                        r['con_code'] for _, r in df.iterrows()
                        if str(r.get('out_date')) in ('None', 'nan', 'NaT', '')]
                for con in c.get('concepts', []):
                    df = vcp.api(pro, 'ths_member', ts_code=con['code'])
                    c['ths_members'][con['code']] = [r['con_code'] for _, r in df.iterrows()]
                c.pop('leaders', None)
                vcp.ensure_leaders(c)
                vcp.save_cache(c)
            else:
                # 平日：daily_basic 批量更新市值快照（不重排龙头）；df_probe 为 None 说明当日数据未发布，跳过
                df = df_probe
                if df is not None and len(df) > 0:
                    for _, r in df.iterrows():
                        if r['circ_mv'] == r['circ_mv']:
                            c['circ_mv'][r['ts_code']] = float(r['circ_mv']) / 1e4
            # ── 龙头个股日线：单日全市场批量 1 次，本地过滤追加 ──
            df = None if eff != trade_date else vcp.api(pro, 'daily', trade_date=eff)
            if df is not None and len(df) > 0:
                want = set(c['stock_daily'])
                appended = 0
                for _, r in df.iterrows():
                    code = r['ts_code']
                    if code not in want:
                        continue
                    row = [str(r['trade_date']), float(r['close']), float(r['high']),
                           float(r['low']), float(r['vol'])]
                    c['stock_daily'][code] = _vcp_append_rows(c['stock_daily'][code], [row])
                    appended += 1
                print(f'  vcpWatch stock_daily appended: {appended}/{len(want)}')
            # ── 指数日线增量（31 SW + 15 概念）──
            for s in c['sw_list']:
                code = s['code']
                df = vcp.api(pro, 'index_daily', ts_code=code,
                             start_date=start, end_date=eff)
                if df is not None and len(df) > 0:
                    rows = [[str(r['trade_date']), float(r['close']), float(r.get('amount') or 0)]
                            for _, r in df.iterrows()]
                    c['index_daily'][code] = _vcp_append_rows(
                        c['index_daily'].get(code, []), rows, max_len=290)
            for con in c.get('concepts', []):
                code = con['code']
                try:
                    df = vcp.api(pro, 'ths_daily', ts_code=code,
                                 start_date=start, end_date=eff)
                    if df is not None and len(df) > 0:
                        rows = [[str(r['trade_date']), float(r['close']),
                                 float(r['amount']) if 'amount' in df.columns
                                 and r.get('amount') == r.get('amount') else 0]
                                for _, r in df.iterrows()]
                        c['index_daily'][code] = _vcp_append_rows(
                            c['index_daily'].get(code, []), rows, max_len=290)
                except Exception as e:
                    print(f'  vcpWatch ths_daily {con["name"]} failed: {str(e)[:60]}')
            # 周五新入名单的龙头补一年历史
            need = sorted({x for v in c['leaders'].values() for x in v}
                          - set(c['stock_daily']))
            back_start = (datetime.strptime(eff, '%Y%m%d')
                          - timedelta(days=vcp.BACK_CAL_DAYS)).strftime('%Y%m%d')
            for code in need:
                try:
                    df = vcp.api(pro, 'daily', ts_code=code, start_date=back_start, end_date=eff)
                    rows = [[str(r['trade_date']), float(r['close']), float(r['high']),
                             float(r['low']), float(r['vol'])] for _, r in df.iterrows()]
                    rows.sort()
                    c['stock_daily'][code] = rows
                except Exception as e:
                    print(f'  vcpWatch leader backfill {code} failed: {str(e)[:60]}')
            if need:
                print(f'  vcpWatch new leaders backfilled: {len(need)}')
        vcp.save_cache(c)

        res = vcp.compute_results(c)
        green = [r for r in res if r['signal'] == '🟢']
        yellow = [r for r in res if r['signal'] == '🟡']
        white = [r for r in res if r['signal'] == '⚪'][:5]
        computed = {r['code'] for r in res}
        concept_short = [x['name'] for x in c.get('concepts', [])
                         if x['code'] not in computed
                         and len(c['index_daily'].get(x['code'], [])) < 100]
        td = c['trade_date']
        data['vcpWatch'] = {
            'trade_date': f'{td[:4]}-{td[4:6]}-{td[6:]}',
            'stats': {'total': len(res), 'green': len(green), 'yellow': len(yellow)},
            'items': green + yellow + white,
            'conceptShort': concept_short,
            'note': '20日滚动波动率年分位<25% 且 ≥3/5 龙头同时窄幅(振幅比<0.75)+缩量(量比<0.7) = 🟢强共振；'
                    '2只 = 🟡观察；⚪为分位最低前5名对照。概念指数无成交额时收缩比显示—',
        }
        print(f"  vcpWatch: {len(res)} sectors, 🟢{len(green)} 🟡{len(yellow)}, "
              f"展示 {len(green) + len(yellow) + len(white)} 行")
    except Exception as e:
        print(f"  Warning: fetch_vcp_watch failed (keep old vcpWatch): {e}")


# ══════════════════════════════════════════════════════════════════
# A. 个股级 VCP 精扫（中证A500∪上证50∪沪深300 成分池，日线+周线双级别）
# B. bottomWatch 积聚新鲜度（首触日+连续命中天数持久化）
# C. 资金+预期双确认（bottomWatch × ECI 前10 展示层联动）
# ══════════════════════════════════════════════════════════════════

VCP_MEMBERS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'cache', 'index_members.json')
VCP_FRESHNESS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'cache', 'bottomwatch_first_seen.json')
VCP_POOL_INDICES = ['000016.SH', '000905.SH', '000300.SH', '000852.SH']  # 上证50∪中证500∪沪深300∪中证1000（2026-08-19 用户口径，去掉中证A500）
VCP_MIN_MV = 2_500_000                    # 全池总市值下限 250 亿（daily_basic total_mv，万元）
VCP_DAILY_WIN, VCP_DAILY_K = 60, 2      # 日线级：近60交易日窗口，摆动高点±2日确认
VCP_WEEK_WIN, VCP_WEEK_K = 40, 1        # 周线级：近40周窗口，摆动高点±1周确认
VCP_MIN_CONTRACTIONS = 2                # 最少收缩次数（递减即达标）
VCP_DECAY_TOL = 1.25                    # 收缩递减容差（后次 ≤ 前次×1.25 且末次<首次）
VCP_SHOW_DIST = 8.0                     # 只展示距枢轴 <8%（容忍 3% 以内已突破）
VCP_SECTOR_LEADERS = 3                  # 每个命中板块取池内龙头数


def _load_json_cache(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _save_json_cache(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def ensure_index_members(pro, trade_date):
    """上证50∪中证500∪沪深300∪中证1000 成分股池：index_weight 取最新月度权重，每周五刷新。

    刷新时一并取 daily_basic 总市值快照（1 次调用），供全池 ≥250 亿市值过滤。
    """
    c = _load_json_cache(VCP_MEMBERS_PATH, {})
    friday = datetime.strptime(trade_date, '%Y%m%d').weekday() == 4
    if (c.get('members') and c.get('mv') and not friday
            and sorted(c['members'].keys()) == sorted(VCP_POOL_INDICES)):
        return c
    members = {}
    # 注意：index_weight 按月发布、trade_date 为月末日，查询区间必须覆盖月末日，
    # 否则返回空（2026-08-18 实测：~0727 无行，~0731 有行）。取 70 日宽窗内最新快照。
    wide_start = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=70)).strftime('%Y%m%d')
    for idx in VCP_POOL_INDICES:
        try:
            time.sleep(API_DELAY)
            df = pro.index_weight(index_code=idx, start_date=wide_start, end_date=trade_date)
            if df is not None and len(df):
                snap = df['trade_date'].max()
                cur = df[df['trade_date'] == snap]
                members[idx] = sorted(set(cur['con_code'].tolist()))
                print(f'  index members {idx}: {len(members[idx])} (snapshot {snap})')
        except Exception as e:
            print(f'  Warning: index_weight {idx} failed: {str(e)[:60]}')
    mv = {}
    mv_date = None
    if members:
        # 总市值快照：从 trade_date 往前最多找 5 个自然日（应对非交易日周五刷新）
        for back in range(0, 6):
            td = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=back)).strftime('%Y%m%d')
            try:
                time.sleep(API_DELAY)
                df = pro.daily_basic(trade_date=td, fields='ts_code,total_mv')
                if df is not None and len(df):
                    all_codes = set()
                    for v in members.values():
                        all_codes.update(v)
                    sub = df[df['ts_code'].isin(all_codes)]
                    mv = {r['ts_code']: float(r['total_mv']) for _, r in sub.iterrows()
                          if r['total_mv'] == r['total_mv']}
                    mv_date = td
                    print(f'  pool market-cap snapshot: {len(mv)}/{len(all_codes)} codes ({td})')
                    break
            except Exception as e:
                print(f'  Warning: daily_basic {td} failed: {str(e)[:60]}')
                break
    if members:
        c = {'updated': trade_date, 'members': members, 'mv': mv, 'mvDate': mv_date}
        _save_json_cache(VCP_MEMBERS_PATH, c)
    return c


def _vcp_swing_highs(bars, k):
    """bars: 升序 [(date, high, low, close, vol)]；返回摆动高点下标（前后 k 根内最高）。"""
    idx = []
    for i in range(k, len(bars) - k):
        h = bars[i][1]
        if h >= max(b[1] for b in bars[i - k:i + k + 1]):
            idx.append(i)
    return idx


def _vcp_level(bars, win, k):
    """单级别 VCP 判定：收缩序列递减 + 量能递减 + 右侧缩量 + 枢轴/距买点。

    返回 dict 或 None（历史不足/摆动点不足）。
    """
    bars = bars[-win:]
    if len(bars) < 12:
        return None
    sh = _vcp_swing_highs(bars, k)
    if len(sh) < VCP_MIN_CONTRACTIONS + 1:
        return None
    sh = sh[-(VCP_MIN_CONTRACTIONS + 3):]   # 最多取最近 5 个摆动高点 → 4 段收缩
    depths, seg_vols = [], []
    for a, b in zip(sh, sh[1:]):
        hi = bars[a][1]
        lo = min(x[2] for x in bars[a:b + 1])
        if hi <= 0:
            return None
        depths.append((hi - lo) / hi * 100)
        seg_vols.append(sum(x[4] for x in bars[a:b + 1]) / (b - a + 1))
    if len(depths) < VCP_MIN_CONTRACTIONS:
        return None
    dec = (all(depths[i + 1] <= depths[i] * VCP_DECAY_TOL for i in range(len(depths) - 1))
           and depths[-1] < depths[0])
    vol_ratio = seg_vols[-1] / seg_vols[0] if seg_vols[0] > 0 else 1.0
    vol_trend = '递减' if vol_ratio <= 0.9 else ('放大' if vol_ratio >= 1.15 else '持平')
    avg_all = sum(x[4] for x in bars) / len(bars)
    right = sum(x[4] for x in bars[-3:]) / 3
    right_shrink = right < avg_all if avg_all > 0 else False
    pivot = bars[sh[-1]][1]
    close = bars[-1][3]
    dist = (pivot / close - 1) * 100 if close > 0 else 999
    formed = dec and vol_trend == '递减'
    return {'contractions': [round(x, 1) for x in depths],
            'count': len(depths), 'decreasing': bool(dec),
            'volTrend': vol_trend, 'rightShrink': bool(right_shrink),
            'pivot': round(pivot, 2), 'distPct': round(dist, 1),
            'formed': bool(formed)}


def _vcp_platform(bars, min_days=10, max_days=50, max_amp=0.14, min_rise=0.10):
    """平台判定（2026-08-19 用户口径重命名两类，缺一不入选）。

    共同要件：平台期 10~50 个交易日窄幅横盘（振幅≤14%）、缩量（平台日均量<前 20 日拉升段）、
    规律收缩（平台三等分段振幅递减，容差 1.25 且末段<首段）。
    分类：
    - 杯柄型：底部已抬升（平台起点收盘相对前 60 日最低 ≥10%）且平台最低价未跌回前低
      → 底部起来后做平台，平台上沿=柄/枢轴（用户认定的高胜率形态）；
    - 底部平台型：抬升不足 10%，平台就在底部区域做规律窄幅缩量波动
      （平台最低价不破前低×0.98），上沿突破即底部确认。
    取满足条件的最长平台（从 50 日往下试）。
    """
    if len(bars) < min_days + 70:
        return None
    close = bars[-1][3]
    if close <= 0:
        return None
    best = None
    for n in range(max_days, min_days - 1, -1):
        plat = bars[-n:]
        hi = max(b[1] for b in plat)
        lo = min(b[2] for b in plat)
        if lo <= 0:
            continue
        amp = (hi - lo) / lo
        if amp > max_amp:
            continue
        prior = bars[-(n + 60):-n]
        if not prior:
            continue
        prior_low = min(b[2] for b in prior)
        if prior_low <= 0:
            continue
        rise = plat[0][3] / prior_low - 1       # 平台起点相对前低的抬升幅度
        if rise >= min_rise and lo > prior_low:
            kind = '杯柄型'                      # 底部抬升后做平台（柄）
        elif lo >= prior_low * 0.98:            # 底部区域内窄幅平台（未破位）
            kind = '底部平台型'
        else:
            continue
        # 缩量
        rally = bars[-(n + 20):-n]              # 拉升段
        plat_vol = sum(b[4] for b in plat) / n
        rally_vol = sum(b[4] for b in rally) / len(rally) if rally else 0
        vol_quiet = rally_vol > 0 and plat_vol <= rally_vol
        if not vol_quiet:
            continue
        # 规律收缩：三等分段振幅递减（容差：后段≤前段×1.25 且末段<首段）
        seg = n // 3
        seg_amps = []
        for i in range(3):
            part = plat[i * seg:(i + 1) * seg] if i < 2 else plat[i * seg:]
            seg_amps.append((max(b[1] for b in part) - min(b[2] for b in part))
                            / min(b[2] for b in part))
        reg_shrink = (seg_amps[2] < seg_amps[0]
                      and all(seg_amps[i + 1] <= seg_amps[i] * 1.25 for i in range(2)))
        if not reg_shrink:
            continue
        pivot = hi
        dist = (pivot / close - 1) * 100
        best = {'type': kind, 'days': n, 'amplitude': round(amp * 100, 1),
                'riseFromLow': round(rise * 100, 1),
                'volRatio': round(plat_vol / rally_vol, 2) if rally_vol > 0 else None,
                'segAmps': [round(a * 100, 1) for a in seg_amps],
                'pivot': round(pivot, 2), 'distPct': round(dist, 1), 'formed': True}
        break   # 已取最长平台
    return best


def _resample_weekly(rows):
    """日线 rows [date, close, high, low, vol] → 周线 bars [(week, high, low, close, vol)]。"""
    weeks = {}
    order = []
    for r in rows:
        d = datetime.strptime(r[0], '%Y%m%d')
        key = f'{d.isocalendar()[0]}W{d.isocalendar()[1]:02d}'
        if key not in weeks:
            weeks[key] = [key, r[2], r[3], r[1], r[4]]  # high, low, close(首), vol
            order.append(key)
        w = weeks[key]
        w[1] = max(w[1], r[2])
        w[2] = min(w[2], r[3])
        w[3] = r[1]          # close 取周内最后一日
        w[4] += r[4]
    return [weeks[k] for k in order]


def fetch_vcp_stocks(pro, trade_date, data, today_map):
    """个股级 VCP 精扫：A500∪SZ50∪HS300 成分池 ∩（持仓观察股 ∪ 积聚板块龙头 ∪ vcpWatch信号板块龙头）。

    个股日线历史复用 vcp_cache.stock_daily（300 交易日，含周线重采样所需长度）；
    缺历史的票一次性回补 420 日历日后并入缓存，次日起随 vcpWatch 批量日更零成本。
    成分池 index_weight 仅周五刷新（4 次调用）+ daily_basic 市值快照（1 次）。失败保留旧 vcpStocks。
    """
    try:
        import vcp_preview as vcp
        c = vcp.load_cache()
        stock_daily = c.get('stock_daily') or {}
        info = c.get('stock_info') or {}
        mc = ensure_index_members(pro, trade_date)
        pool_raw = set()
        for v in (mc.get('members') or {}).values():
            pool_raw.update(v)
        if not pool_raw:
            raise ValueError('index members pool empty')
        # 全池总市值 ≥250 亿过滤（daily_basic total_mv，万元；快照随周五成分刷新更新）
        mv = mc.get('mv') or {}
        if mv:
            pool = {c2 for c2 in pool_raw if mv.get(c2, 0) >= VCP_MIN_MV}
            print(f'  vcpStocks pool: {len(pool_raw)} raw → {len(pool)} after ≥250亿 mv filter '
                  f'(mv snapshot {mc.get("mvDate")})')
        else:
            pool = pool_raw
            print(f'  vcpStocks pool: {len(pool)} (no mv snapshot, filter skipped)')

        # ── 精扫对象 ──
        targets = {}   # code → {'sector': ..., 'star': bool}
        for code, s in STOCKS.items():           # 用户 14 只持仓/观察股（星标，点名纳入，不受池限制）
            targets[code] = {'sector': s['industry'], 'star': True, 'inPool': code in pool}
        bw = data.get('bottomWatch') or {}
        for it in bw.get('items', []):
            sector = it['sector']
            cand = [s for s in (today_map.get(sector) or []) if s['code'] in pool]
            for s in cand[:VCP_SECTOR_LEADERS]:
                targets.setdefault(s['code'], {'sector': sector, 'star': False, 'inPool': True})
        vw = data.get('vcpWatch') or {}
        for r in vw.get('items', []):
            if r.get('signal') == '⚪':
                continue
            for l in r.get('leaders', []):
                if l['code'] in pool:
                    targets.setdefault(l['code'], {'sector': r['name'], 'star': False, 'inPool': True})
        print(f'  vcpStocks targets: {len(targets)} (pool {len(pool)})')

        # ── 历史补缺（一次性，并入 vcp 缓存随日更维护）──
        eff = None
        for rows in stock_daily.values():
            if rows:
                eff = rows[-1][0]
                break
        eff = eff or trade_date
        stale_cut = (datetime.strptime(eff, '%Y%m%d') - timedelta(days=7)).strftime('%Y%m%d')
        need = [code for code in targets
                if not stock_daily.get(code) or stock_daily[code][-1][0] < stale_cut]
        if need:
            back_start = (datetime.strptime(eff, '%Y%m%d')
                          - timedelta(days=vcp.BACK_CAL_DAYS)).strftime('%Y%m%d')
            for code in need:
                try:
                    time.sleep(API_DELAY)
                    df = pro.daily(ts_code=code, start_date=back_start, end_date=eff)
                    if df is None or not len(df):
                        continue
                    rows = [[str(r['trade_date']), float(r['close']), float(r['high']),
                             float(r['low']), float(r['vol'])] for _, r in df.iterrows()]
                    rows.sort()
                    c.setdefault('stock_daily', {})[code] = rows[-300:]
                    stock_daily = c['stock_daily']
                except Exception as e:
                    print(f'  Warning: vcpStocks backfill {code} failed: {str(e)[:60]}')
            vcp.save_cache(c)
            print(f'  vcpStocks backfilled: {len(need)}')

        # ── 综合建议维度：水温 × 板块合适度（关注优先级，不含操作指令）──
        temp = ((data.get('bondData') or {}).get('marginTrading') or {}).get('temp') or ''
        if '冷' in temp:
            water_txt = '水温偏冷·只观察'
        elif '平' in temp:
            water_txt = '水温中性·谨慎关注'
        elif '暖' in temp:
            water_txt = '水温偏暖·正常关注'
        else:
            water_txt = ''
        good_sectors = set()
        for a in (data.get('actionableSectors') or {}).get('items', []):
            good_sectors.add(a['sector'])
            if a.get('subSector'):
                good_sectors.add(a['subSector'])
        for b in (bw.get('items') or []):          # 积聚档（含双确认）
            good_sectors.add(b['sector'])
        bad_sectors = set()
        for f in (data.get('sectorFlows') or {}).get('items', []):
            if f.get('tag') in ('拐点·转流出', '持续流出'):
                bad_sectors.add(f['name'])
        for s in (data.get('sectorScan') or {}).get('items', []):
            if s.get('status') == '高潮风险':
                bad_sectors.add(s['sector'])

        # ── 平台两类判定（杯柄型/底部平台型）；收缩型降级：不再单独展示 ──
        items = []
        for code, meta in targets.items():
            rows = stock_daily.get(code) or []
            if len(rows) < 60:
                continue
            bars = [(r[0], r[2], r[3], r[1], r[4]) for r in rows]  # (date, high, low, close, vol)
            pf = _vcp_platform(bars)
            d_lv = _vcp_level(bars, VCP_DAILY_WIN, VCP_DAILY_K)
            w_lv = _vcp_level(_resample_weekly(rows), VCP_WEEK_WIN, VCP_WEEK_K)
            p_ok = bool(pf and pf['formed'])
            d_ok = bool(d_lv and d_lv['formed'])
            w_ok = bool(w_lv and w_lv['formed'])
            if not p_ok:
                continue   # 收缩型降级（用户：纯大幅波动收缩胜率不高），仅作 tag 辅助信息
            main_lv, pattern = pf, pf['type']
            if not (-5 <= main_lv['distPct'] <= VCP_SHOW_DIST):
                continue   # 只展示成型或临近成型（距枢轴 <8%）
            sec = meta['sector']
            if sec in bad_sectors:
                fit_txt = '板块不配合⚠️'
            elif sec in good_sectors:
                fit_txt = '板块配合✅'
            else:
                fit_txt = '板块中性'
            advice = (f"{pattern}·距枢轴{main_lv['distPct']}%｜{water_txt}｜{fit_txt}"
                      if water_txt else f"{pattern}·距枢轴{main_lv['distPct']}%｜{fit_txt}")
            close = rows[-1][1]
            tag = ('日线✅+周线✅' if d_ok and w_ok else
                   ('日线✅' if d_ok else ('周线✅' if w_ok else '—')))
            items.append({'code': code,
                          'name': info.get(code, {}).get('name', code),
                          'sector': sec, 'star': meta['star'],
                          'close': round(close, 2), 'tag': tag,
                          'pattern': pattern, 'platform': pf,
                          'distMain': main_lv['distPct'],
                          'sectorFit': fit_txt, 'advice': advice,
                          'daily': d_lv, 'weekly': w_lv})
        items.sort(key=lambda x: (0 if x['pattern'] == '杯柄型' else 1, x['distMain']))
        eff_d = f'{eff[:4]}-{eff[4:6]}-{eff[6:]}'
        data['vcpStocks'] = {
            'trade_date': eff_d, 'poolSize': len(pool), 'poolRaw': len(pool_raw),
            'mvDate': mc.get('mvDate'), 'scanned': len(targets),
            'items': items[:15],
            'note': '池=上证50∪中证500∪沪深300∪中证1000成分（周五刷新）∩总市值≥250亿（daily_basic口径，随成分周更）；精扫=持仓观察股(★点名纳入,不受池限)+积聚板块池内龙头+VCP信号板块龙头；'
                    '形态两类：杯柄型=底部抬升≥10%后做柄（平台上沿=枢轴）；底部平台型=底部区域规律窄幅缩量平台；共同要件=10~50日窄幅(振幅≤14%)+缩量+分段振幅规律收缩；'
                    '收缩型已降级不单独展示；只展示距枢轴<8%的成型/临近成型个股，杯柄型优先；建议=水温×板块合适度，仅供关注优先级参考',
        }
        print(f"  vcpStocks: scanned {len(targets)}, formed {len(items)} "
              f"({[i['name'] + ':' + i['pattern'] for i in items[:5]]})")
    except Exception as e:
        print(f"  Warning: fetch_vcp_stocks failed (keep old vcpStocks): {e}")


def update_bottom_freshness(bottom, hist):
    """B. 积聚新鲜度：bottomWatch 命中板块的首触日+连续命中交易日数（轻量持久化）。

    scripts/cache/bottomwatch_first_seen.json 纳入 workflow 回写；未命中板块记录保留但 streak 归零。
    """
    try:
        days = sorted(hist['days'])
        if not days:
            return
        today, prev = days[-1], (days[-2] if len(days) > 1 else days[-1])
        rec = _load_json_cache(VCP_FRESHNESS_PATH, {})
        hit_sectors = [it['sector'] for it in bottom.get('items', [])]
        for s, r in rec.items():
            if s not in hit_sectors:
                r['streak'] = 0
        for s in hit_sectors:
            r = rec.setdefault(s, {'first': today, 'streak': 0, 'last': ''})
            if r.get('last') == prev or r.get('last') == today:
                r['streak'] = int(r.get('streak', 0)) + (0 if r['last'] == today else 1)
            else:
                r['streak'] = 1
                r['first'] = today
            r['last'] = today
        _save_json_cache(VCP_FRESHNESS_PATH, rec)
        fmt = lambda dd: f'{dd[4:6]}-{dd[6:]}'
        fresh = []
        for it in bottom.get('items', []):
            r = rec.get(it['sector'])
            if not r:
                continue
            it['firstSeen'] = fmt(r['first'])
            it['streakDays'] = r['streak']
            fresh.append({'sector': it['sector'], 'firstSeen': fmt(r['first']),
                          'streakDays': r['streak'],
                          'stage': ('新进入积聚' if r['streak'] <= 5 else
                                    ('积聚已久' if r['streak'] > 15 else '积聚跟踪中'))})
        bottom['freshness'] = fresh
        if fresh:
            print('  bottomWatch freshness: '
                  + '、'.join(f"{f['sector']}{f['streakDays']}天({f['stage']})" for f in fresh))
    except Exception as e:
        print(f"  Warning: bottom freshness failed: {e}")


def apply_dual_confirm(data):
    """C. 资金+预期双确认：bottomWatch 任一档命中 且 ECI 总分前10 → 双向打标 + 短评一句。"""
    try:
        bw = data.get('bottomWatch') or {}
        eci = data.get('eciData') or {}
        hit_l1 = set()
        for it in bw.get('items', []):
            l1 = SECTOR_TO_L1.get(it['sector'])
            if l1:
                hit_l1.add(l1)
        if not hit_l1 or not eci.get('sectors'):
            return
        top10 = sorted(eci['sectors'], key=lambda s: -s.get('eci', 0))[:10]
        top10_names = {s['sector'] for s in top10}
        dual = sorted(hit_l1 & top10_names)
        for s in eci['sectors']:
            if s['sector'] in hit_l1:
                s['fundAccum'] = True
        for it in bw.get('items', []):
            if SECTOR_TO_L1.get(it['sector']) in top10_names:
                it['dualConfirm'] = True
        if dual:
            note = '双确认：' + '、'.join(f'{n}（资金积聚+预期一致前10）' for n in dual) + '。'
            bw['dualConfirmNote'] = note
            bw['summary'] = (bw.get('summary') or '') + note
            print(f'  双确认: {"、".join(dual)}')
    except Exception as e:
        print(f'  Warning: dual confirm failed: {e}')


def build_eci_quadrant(data):
    """行业景气四象限数据块（参照券商产业景气四象限图，用最贴近的 ECI 口径日更）。

    X=31 行业 ECI 总分当前值；Y=ECI 较上月变化（同口径：sector_history 窗口前移 21 交易日重算，
    历史不足时暂用 change5d 并标注 yMode='5d'）；中线=31 行业当前中位数（与原图一致，非 0 轴）。
    """
    try:
        eci = data.get('eciData') or {}
        secs = eci.get('sectors') or []
        if not secs:
            return
        y_mode = 'monthly' if any(s.get('change1m') is not None for s in secs) else '5d'
        items = []
        for s in secs:
            chg = (s.get('change1m') if y_mode == 'monthly' else s.get('change5d'))
            items.append({'sector': s['sector'], 'eci': float(s['eci']),
                          'chg': float(chg if chg is not None else 0.0)})
        xs = sorted(i['eci'] for i in items)
        ys = sorted(i['chg'] for i in items)
        xm, ym = xs[len(xs) // 2], ys[len(ys) // 2]
        for i in items:
            hi, up = i['eci'] >= xm, i['chg'] >= ym
            i['quadrant'] = ('景气高位·持续改善' if hi and up else
                             '景气高位·边际走弱' if hi else
                             '景气低位·边际修复' if up else '景气低位·仍在筑底')
        data['eciQuadrant'] = {
            'trade_date': eci.get('period') or '',
            'yMode': y_mode,
            'xMedian': xm, 'yMedian': ym,
            'items': items,
            'note': '以 ECI 预期一致性指数近似行业景气度（日更），较券商产业景气指数（月更）更及时；'
                    'X/Y 中线=31 行业当前中位数',
        }
        print(f"  eciQuadrant: {len(items)} sectors, yMode={y_mode}, median=({xm}, {ym})")
    except Exception as e:
        print(f'  Warning: build_eci_quadrant failed: {e}')


def build_actionable_sectors(data):
    """D. 能投板块短名单（同一块数据三处展示，不重复计算）。

    入选：双确认（bottomWatch任一档∩ECI前10）最优先；其次🔥双档共振、60日档、30日档；
    否决：资金节奏"拐点·转流出/持续流出" 或 扫描榜"高潮风险"。无入选则如实空名单。
    """
    try:
        bw = data.get('bottomWatch') or {}
        eci = data.get('eciData') or {}
        flows = {r['name']: r for r in (data.get('sectorFlows') or {}).get('items', [])}
        scan_veto = {i['sector'] for i in (data.get('sectorScan') or {}).get('items', [])
                     if i.get('status') == '高潮风险'}
        eci_sorted = sorted(eci.get('sectors', []), key=lambda s: -s.get('eci', 0))
        top10 = [s['sector'] for s in eci_sorted[:10]]
        fresh_map = {f['sector']: f for f in bw.get('freshness', [])}
        out, vetoed = [], []
        for it in bw.get('items', []):
            l1 = SECTOR_TO_L1.get(it['sector'])
            if not l1:
                continue
            reasons = []
            if it.get('dualConfirm'):
                rank = top10.index(l1) + 1 if l1 in top10 else None
                reasons.append(f"双确认（资金积聚+ECI预期前10{('第' + str(rank) + '名') if rank else ''}）")
            if it.get('both'):
                reasons.append('🔥30日+60日双档共振')
            elif it.get('hit60'):
                reasons.append('60日档长期吸筹')
            elif it.get('hit30'):
                reasons.append('30日档较新积聚')
            f = fresh_map.get(it['sector'])
            if f:
                reasons.append(f"积聚{f['streakDays']}天（{f['stage']}）")
            fr = flows.get(it['sector'])
            if fr:
                reasons.append(f"资金节奏：{fr['tag']}（近5日{fr['net5']:+.1f}亿）")
            veto = None
            if fr and fr['tag'] in ('拐点·转流出', '持续流出'):
                veto = f"资金节奏{fr['tag']}"
            if it['sector'] in scan_veto:
                veto = '扫描榜高潮风险'
            entry = {'sector': l1, 'subSector': it['sector'], 'reasons': reasons,
                     'priority': 1 if it.get('dualConfirm') else (2 if it.get('both') else 3),
                     'pricePosition': it.get('pricePosition'),
                     'firstSeen': it.get('firstSeen'), 'streakDays': it.get('streakDays')}
            (vetoed if veto else out).append({**entry, **({'veto': veto} if veto else {})})
        out.sort(key=lambda x: (x['priority'], x.get('pricePosition') or 9))
        td = bw.get('trade_date', '')
        data['actionableSectors'] = {
            'trade_date': td,
            'items': out[:8],
            'vetoed': [{'sector': v['sector'], 'subSector': v['subSector'], 'veto': v['veto']}
                       for v in vetoed[:5]],
            'note': '入选=双确认/双档共振/60日档/30日档；否决=资金节奏拐点·转流出或持续流出、扫描榜高潮风险；'
                    '仅基于底部积聚命中板块，无命中则空名单',
        }
        print(f"  actionableSectors: {len(out)} 入选, {len(vetoed)} 否决"
              f"({[o['sector'] for o in out[:5]]})")
    except Exception as e:
        print(f"  Warning: actionableSectors failed: {e}")


def load_existing_data():
    """Load existing fund_data.json to preserve manually maintained fields."""
    try:
        with open(OUTPUT_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════
# 国家队栏目升级：ETF份额雷达 / 板块资金轮动(份额口径) / 汇金持仓估算 / 宽基波动率
# ══════════════════════════════════════════════════════════════
import re as _re

ETF_SHARE_CACHE = 'scripts/cache/etf_share_history.json'
NT_RATIO_CONFIG = 'scripts/config/national_team_ratio.json'

# ETF 份额雷达监控池（19 只；名称已用 fund_basic 核对）
# group: broad=宽基组（汇金系），soe=央企主题组（国新/诚通）；series 用于轮动表分节与合计行
ETF_RADAR_WATCH = {
    '510300.SH': {'name': '华泰柏瑞300ETF', 'group': 'broad', 'series': '沪深300系列'},
    '510310.SH': {'name': '易方达300ETF',   'group': 'broad', 'series': '沪深300系列'},
    '510330.SH': {'name': '华夏300ETF',     'group': 'broad', 'series': '沪深300系列'},
    '159919.SZ': {'name': '嘉实300ETF',     'group': 'broad', 'series': '沪深300系列'},
    '510050.SH': {'name': '华夏50ETF',      'group': 'broad', 'series': '上证50'},
    '510500.SH': {'name': '南方500ETF',     'group': 'broad', 'series': '中证500系列'},
    '512500.SH': {'name': '华夏500ETF',     'group': 'broad', 'series': '中证500系列'},
    '512100.SH': {'name': '南方1000ETF',    'group': 'broad', 'series': '中证1000系列'},
    '159845.SZ': {'name': '华夏1000ETF',    'group': 'broad', 'series': '中证1000系列'},
    '588000.SH': {'name': '华夏科创50ETF',  'group': 'broad', 'series': '科创50系列'},
    '588080.SH': {'name': '易方达科创50ETF', 'group': 'broad', 'series': '科创50系列'},
    '510180.SH': {'name': '华安180ETF',     'group': 'broad', 'series': '上证180'},
    '159915.SZ': {'name': '易方达创业板ETF', 'group': 'broad', 'series': '创业板'},
    '560170.SH': {'name': '央企科技ETF',      'group': 'soe', 'series': '国新系'},
    '520660.SH': {'name': '港股通央企红利ETF(南方)', 'group': 'soe', 'series': '国新系'},
    '520990.SH': {'name': '港股通央企红利ETF(景顺)', 'group': 'soe', 'series': '国新系'},
    '159335.SZ': {'name': '央企科创ETF',      'group': 'soe', 'series': '诚通系'},
    '159336.SZ': {'name': '央企红利ETF',      'group': 'soe', 'series': '诚通系'},
    '560810.SH': {'name': '央企ESG ETF',      'group': 'soe', 'series': '诚通系'},
}

# 国家队短评（B）：系列 → 利多/利空影响的指数/主题
SERIES_IMPACT = {
    '沪深300系列': '沪深300/大盘蓝筹',
    '上证50': '上证50/超大盘蓝筹',
    '中证500系列': '中证500/中盘股',
    '中证1000系列': '中证1000/小盘股',
    '科创50系列': '科创50/硬科技',
    '上证180': '上证180/大盘价值',
    '创业板': '创业板/成长股',
    '国新系': '央企科技/央企红利主题',
    '诚通系': '央企科创/央企红利主题',
}

# 宽基波动率（ETF VIX）标的指数
VOL_INDICES = {
    '000300.SH': '沪深300',
    '000905.SH': '中证500',
    '000852.SH': '中证1000',
    '000016.SH': '上证50',
    '399006.SZ': '创业板指',
    '000688.SH': '科创50',
    '000510.SH': '中证A500',
    '000001.SH': '上证综指',
    '399001.SZ': '深证成指',
}

# 板块资金轮动分类（名称关键词，按优先级从上到下匹配）
ETF_CATEGORY_RULES = [
    ('货币',   r'货币|添益|日利|快线|保证金|理财金'),
    ('债券',   r'债|国开|利率|信用'),
    ('商品',   r'黄金|白银|豆粕|原油|能源化工|饲料'),
    ('港股海外', r'恒生|港股|H股|中概|纳斯达克|标普|日经|德国|法国|亚太|全球|美国|沙特|QDII|海外|国际原油'),
    ('红利',   r'红利|股息|低波|现金流'),
    ('宽基',   r'沪深300|中证500|中证1000|中证2000|上证50|科创50|科创创业|创业板|A500|中证800|上证180|深证100|中证100|MSCI|综指|深证成|双创'),
    ('科技',   r'半导体|芯片|科技|科创|人工智能|智能|通信|计算机|电子|5G|软件|云|大数据|信创|机器人|军工|互联网|游戏|传媒|VR|信息安全'),
    ('医药',   r'医药|医疗|生物|创新药|中药|疫苗|健康'),
    ('消费',   r'消费|食品|饮料|酒|家电|农业|养殖|旅游|畜牧'),
    ('金融地产', r'银行|证券|保险|金融|地产|券商|非银'),
    ('新能源', r'新能源|光伏|锂电|电池|储能|风电|碳中和|充电'),
]


def _etf_classify(name):
    for cat, pat in ETF_CATEGORY_RULES:
        if _re.search(pat, name or ''):
            return cat
    return '其他'


def _etf_cache_load():
    try:
        with open(ETF_SHARE_CACHE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _etf_cache_save(c):
    try:
        os.makedirs(os.path.dirname(ETF_SHARE_CACHE), exist_ok=True)
        with open(ETF_SHARE_CACHE, 'w', encoding='utf-8') as f:
            json.dump(c, f, ensure_ascii=False)
    except Exception as e:
        print(f"  Warning: etf share cache save failed: {e}")


def _hv(closes, win):
    """年化历史波动率(%)：对最近 win 个日收益率取标准差 ×√252。"""
    if len(closes) < win + 1:
        return None
    rets = [closes[i] / closes[i - 1] - 1 for i in range(len(closes) - win, len(closes))]
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return round((var ** 0.5) * (252 ** 0.5) * 100, 1)


def _pct_rank100(values, v):
    """v 在 values 中的百分位(0-100)。注意与 ECI 用的 _pct_rank(0-1) 区分，勿同名覆盖。"""
    vals = [x for x in values if x is not None]
    if not vals or v is None:
        return None
    return round(sum(1 for x in vals if x <= v) / len(vals) * 100, 1)


def fetch_nt_upgrade(pro, trade_date, data):
    """国家队升级主流程：份额雷达 + 板块轮动 + 汇金估算 + 宽基波动率 + 自动短评。

    每晚增量调用（≤10 次）：fund_share 批量 1 + fund_daily 批量 1 +
    index_daily 按 trade_date 1 + index_dailybasic 6 + （名称表每周五 1）。
    首次运行本地回补历史：radar 13×2 + 指数 6×2 ≈ 38 次。
    全模块 try/except，单块失败不影响主流程。
    """
    cache = _etf_cache_load()
    cache.setdefault('watch', {})      # {code: {date: [share亿份, close]}}  ~400 天
    cache.setdefault('snapshots', {})  # {date: {code: share亿份}} 全市场，保留 12 天
    cache.setdefault('names', {})      # {code: name}
    cache.setdefault('idx', {})        # {idx_code: {date: close}}
    cache.setdefault('idxBasic', {})   # {idx_code: {date: pe_ttm}}

    # ── 有效日期回探（数据未发布时退到前一交易日）──
    eff = None
    df_share_all = None
    d = trade_date
    for _ in range(5):
        try:
            time.sleep(API_DELAY)
            df_share_all = pro.fund_share(trade_date=d)
            if df_share_all is not None and len(df_share_all) > 0:
                eff = d
                break
        except Exception as e:
            print(f"  Warning: fund_share batch {d} failed: {e}")
        d = (datetime.strptime(d, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
    if eff is None or df_share_all is None:
        print("  Warning: fund_share unavailable, skip national team upgrade")
        return
    if eff != trade_date:
        print(f"  fund_share {trade_date} 未发布，回退有效日期 {eff}")

    # 全市场 ETF 份额（亿份）
    shares_now = {}
    for _, r in df_share_all.iterrows():
        try:
            shares_now[r['ts_code']] = float(r['fd_share']) / 10000.0
        except Exception:
            continue
    cache['snapshots'][eff] = {k: round(v, 4) for k, v in shares_now.items()}
    cache['snapshots'] = dict(sorted(cache['snapshots'].items())[-12:])

    # ── fund_daily 批量：收盘价 ──
    close_now = {}
    try:
        time.sleep(API_DELAY)
        df_fd = pro.fund_daily(trade_date=eff)
        if df_fd is not None and len(df_fd) > 0:
            close_now = dict(zip(df_fd['ts_code'], df_fd['close'].astype(float)))
    except Exception as e:
        print(f"  Warning: fund_daily batch failed: {e}")

    # ── 雷达池历史维护（首次回补 400 天，之后每日 1 行）──
    backfill_start = (datetime.strptime(eff, '%Y%m%d') - timedelta(days=600)).strftime('%Y%m%d')
    for tc in ETF_RADAR_WATCH:
        try:
            hist = cache['watch'].setdefault(tc, {})
            if eff in hist:
                continue
            if not hist:
                # 首次回补：份额 + 收盘价各 1 次
                time.sleep(API_DELAY)
                dfs = pro.fund_share(ts_code=tc, start_date=backfill_start, end_date=eff)
                time.sleep(API_DELAY)
                dfd = pro.fund_daily(ts_code=tc, start_date=backfill_start, end_date=eff)
                closes = dict(zip(dfd['trade_date'], dfd['close'].astype(float))) if dfd is not None and len(dfd) else {}
                if dfs is not None and len(dfs):
                    for _, r in dfs.iterrows():
                        hist[r['trade_date']] = [round(float(r['fd_share']) / 10000.0, 4),
                                                 round(float(closes.get(r['trade_date'], 0)), 4)]
            else:
                if tc in shares_now:
                    hist[eff] = [round(shares_now[tc], 4), round(float(close_now.get(tc, 0)), 4)]
            cache['watch'][tc] = dict(sorted(hist.items())[-400:])
        except Exception as e:
            print(f"  Warning: radar history {tc} failed: {e}")

    # ── 输出日期 od：雷达池覆盖≥80%的最新日期（防 fund_share 部分发布导致数据残缺）──
    _cnt = {}
    for tc in ETF_RADAR_WATCH:
        for d0 in cache['watch'].get(tc, {}):
            _cnt[d0] = _cnt.get(d0, 0) + 1
    _need = max(1, int(len(ETF_RADAR_WATCH) * 0.8))
    _covered = [d0 for d0, n in _cnt.items() if n >= _need]
    od = max(_covered) if _covered else eff
    if od != eff:
        print(f"  雷达池 {eff} 覆盖不足（部分发布），输出日期回退 {od}")

    # ── 快照回补（首次运行补最近 8 个交易日，供板块轮动 1日/5日对比）──
    try:
        if len(cache['snapshots']) < 6:
            cal = sorted(cache['watch'].get('510300.SH', {}).keys())
            todo = [d0 for d0 in cal[-9:] if d0 not in cache['snapshots'] and d0 <= od]
            for d0 in todo:
                time.sleep(API_DELAY)
                dfs = pro.fund_share(trade_date=d0)
                if dfs is not None and len(dfs):
                    cache['snapshots'][d0] = {
                        r['ts_code']: round(float(r['fd_share']) / 10000.0, 4)
                        for _, r in dfs.iterrows()
                    }
            cache['snapshots'] = dict(sorted(cache['snapshots'].items())[-12:])
            print(f"  snapshots backfilled: {len(cache['snapshots'])} days")
    except Exception as e:
        print(f"  Warning: snapshot backfill failed: {e}")

    # ── ETF 名称表（分类用；每周五或缺失时刷新，1 次调用）──
    try:
        wd = datetime.strptime(eff, '%Y%m%d').weekday()
        need = (not cache['names']) or cache.get('namesUpdated', '') < cache.get('lastFriday', '') \
            or len([c for c in shares_now if c not in cache['names']]) > 200
        if wd == 4:
            cache['lastFriday'] = eff
        if wd == 4 or not cache['names'] or need:
            time.sleep(API_DELAY)
            fb = pro.fund_basic(market='E', status='L', fields='ts_code,name')
            if fb is not None and len(fb):
                cache['names'] = dict(zip(fb['ts_code'], fb['name']))
                cache['namesUpdated'] = eff
    except Exception as e:
        print(f"  Warning: fund_basic names refresh failed: {e}")

    # ── 指数日线（HV）：先按 trade_date 全量 1 次，缺失逐只回补 ──
    for ic in VOL_INDICES:
        try:
            cache['idx'].setdefault(ic, {})
        except Exception:
            pass
    try:
        time.sleep(API_DELAY)
        di = pro.index_daily(trade_date=eff)
        if di is not None and len(di):
            for ic in VOL_INDICES:
                row = di[di['ts_code'] == ic]
                if len(row):
                    cache['idx'][ic][eff] = round(float(row.iloc[0]['close']), 4)
    except Exception as e:
        print(f"  Warning: index_daily batch failed: {e}")
    for ic in VOL_INDICES:
        try:
            hist = cache['idx'][ic]
            if len(hist) < 80:
                start = (datetime.strptime(eff, '%Y%m%d') - timedelta(days=600)).strftime('%Y%m%d')
            elif eff not in hist:
                start = (datetime.strptime(max(hist), '%Y%m%d') + timedelta(days=1)).strftime('%Y%m%d')
            else:
                start = None
            if start:
                time.sleep(API_DELAY)
                d1 = pro.index_daily(ts_code=ic, start_date=start, end_date=eff)
                if d1 is not None and len(d1):
                    for _, r in d1.iterrows():
                        hist[r['trade_date']] = round(float(r['close']), 4)
            cache['idx'][ic] = dict(sorted(hist.items())[-320:])
        except Exception as e:
            print(f"  Warning: index daily {ic} failed: {e}")

    # ── 指数估值（PE TTM）：逐只增量，首次回补约 2.5 年 ──
    for ic in VOL_INDICES:
        try:
            hist = cache['idxBasic'].setdefault(ic, {})
            if eff in hist:
                continue
            start = (datetime.strptime(eff, '%Y%m%d') - timedelta(days=920)).strftime('%Y%m%d') if not hist \
                else (datetime.strptime(max(hist), '%Y%m%d') + timedelta(days=1)).strftime('%Y%m%d')
            time.sleep(API_DELAY)
            db = pro.index_dailybasic(ts_code=ic, start_date=start, end_date=eff, fields='ts_code,trade_date,pe_ttm')
            if db is not None and len(db):
                for _, r in db.iterrows():
                    if pd.notna(r['pe_ttm']):
                        hist[r['trade_date']] = round(float(r['pe_ttm']), 2)
            cache['idxBasic'][ic] = dict(sorted(hist.items())[-620:])
        except Exception as e:
            print(f"  Warning: index_dailybasic {ic} failed: {e}")

    _etf_cache_save(cache)

    # ════════ 1. ETF 份额雷达（19 只：宽基组 + 央企主题组） ════════
    try:
        items = []
        for tc, meta in ETF_RADAR_WATCH.items():
            hist = cache['watch'].get(tc, {})
            days = [d0 for d0 in sorted(hist.keys()) if d0 <= od]
            if len(days) < 2:
                continue
            share = hist[days[-1]][0]
            close = hist[days[-1]][1] or close_now.get(tc, 0)

            def _chg(n):
                if len(days) > n and hist[days[-1 - n]][0] > 0:
                    prev = hist[days[-1 - n]][0]
                    return round(share - prev, 2), round((share - prev) / prev * 100, 2)
                return None, None

            c1, p1 = _chg(1)
            c5, p5 = _chg(5)
            c20, p20 = _chg(20)
            amt1 = round(c1 * close, 2) if c1 is not None and close else None
            # 信号口径：单日份额|>3%|且金额|>1亿|，或金额|>20亿| = 强信号；|>2%|且|>5亿| = 关注
            # （金额下限防止小规模ETF因份额基数小而出Percentage大、金额微不足道的伪强信号）
            if p1 is not None and amt1 is not None and ((abs(p1) > 3 and abs(amt1) > 1) or abs(amt1) > 20):
                signal = '强信号'
            elif p1 is not None and amt1 is not None and abs(p1) > 2 and abs(amt1) > 5:
                signal = '关注'
            else:
                signal = None
            # 连续 3 日同向份额变化 = 趋势性增/减仓
            trend3 = None
            if len(days) >= 4:
                diffs = []
                ok = True
                for k in (1, 2, 3):
                    a, b = hist[days[-k]][0], hist[days[-1 - k]][0]
                    if b <= 0:
                        ok = False
                        break
                    diffs.append(a - b)
                if ok and all(x > 0 for x in diffs):
                    trend3 = '趋势性增持'
                elif ok and all(x < 0 for x in diffs):
                    trend3 = '趋势性减持'
            items.append({
                'code': tc, 'name': meta['name'], 'group': meta['group'], 'series': meta['series'],
                'share': round(share, 2), 'close': round(close, 3),
                'chg1': c1, 'chg1Pct': p1, 'amt1': amt1,
                'chg5': c5, 'chg5Pct': p5, 'chg20': c20, 'chg20Pct': p20,
                'signal': signal, 'trend3': trend3, 'alert': signal is not None,
            })
        data['etfShareRadar'] = {
            'trade_date': f"{od[:4]}-{od[4:6]}-{od[6:]}",
            'items': items,
            'alertCount': sum(1 for i in items if i['alert']),
            'note': '份额变化×当日收盘价折算金额；单日|>2%|且|>5亿|=关注，|>3%|且|>1亿|或|>20亿|=强信号',
        }
        print(f"  etfShareRadar: {len(items)} ETFs, alerts {data['etfShareRadar']['alertCount']}")
    except Exception as e:
        print(f"  Warning: etfShareRadar failed: {e}")

    # ════════ 1b. 国家队持仓轮动表（宽基组按系列分节 + 央企主题组） ════════
    try:
        radar_items = (data.get('etfShareRadar') or {}).get('items') or []
        if radar_items:
            # 央企组真实占比/持有人（config 中带 owner 的条目）
            nt_ratio_cfg = {}
            try:
                with open(NT_RATIO_CONFIG, encoding='utf-8') as f:
                    nt_ratio_cfg = json.load(f)
            except Exception:
                pass

            def _rot_row(it):
                row = {
                    'code': it['code'], 'name': it['name'],
                    'share': it['share'], 'chg1': it['chg1'], 'chg1Pct': it['chg1Pct'],
                    'amt1': it['amt1'], 'chg5Pct': it['chg5Pct'],
                    'signal': it['signal'], 'trend3': it['trend3'],
                }
                cfg = nt_ratio_cfg.get(it['code']) or {}
                if cfg.get('owner'):
                    row['owner'] = cfg['owner']
                    row['ratio'] = cfg.get('ratio')
                return row

            groups = []
            for gkey, gname in (('broad', '宽基组（汇金系）'), ('soe', '央企主题组（国新/诚通）')):
                gitems = [i for i in radar_items if i.get('group') == gkey]
                series_list = []
                seen = []
                for i in gitems:
                    if i['series'] not in seen:
                        seen.append(i['series'])
                for sname in seen:
                    sitems = [i for i in gitems if i['series'] == sname]
                    rows = [_rot_row(i) for i in sitems]
                    total = None
                    if len(rows) > 1:
                        def _s(key):
                            vals = [r[key] for r in rows if r.get(key) is not None]
                            return round(sum(vals), 2) if vals else None
                        # 系列合计：份额/变化额/金额直接加总；百分比按份额加权
                        def _wp(key):
                            num = sum(r[key] * r['share'] for r in rows
                                      if r.get(key) is not None and r.get('share'))
                            den = sum(r['share'] for r in rows
                                      if r.get(key) is not None and r.get('share'))
                            return round(num / den, 2) if den > 0 else None
                        total = {'share': _s('share'), 'chg1': _s('chg1'), 'chg1Pct': _wp('chg1Pct'),
                                 'amt1': _s('amt1'), 'chg5Pct': _wp('chg5Pct')}
                    series_list.append({'name': sname, 'items': rows, 'total': total})
                groups.append({'key': gkey, 'name': gname, 'series': series_list})

            # 共振判定：宽基组有信号且单日份额变化同向的 ≥3 只
            sig_broad = [i for i in radar_items
                         if i.get('group') == 'broad' and i.get('signal') and i.get('chg1')]
            ups = [i['name'] for i in sig_broad if i['chg1'] > 0]
            downs = [i['name'] for i in sig_broad if i['chg1'] < 0]
            if len(ups) >= 3:
                resonance = {'hit': True, 'count': len(ups), 'direction': '增持', 'names': ups}
            elif len(downs) >= 3:
                resonance = {'hit': True, 'count': len(downs), 'direction': '减持', 'names': downs}
            else:
                resonance = {'hit': False, 'count': max(len(ups), len(downs)), 'direction': None, 'names': []}
            data['ntRotation'] = {
                'trade_date': f"{od[:4]}-{od[4:6]}-{od[6:]}",
                'groups': groups,
                'resonance': resonance,
                'note': '信号口径：单日份额|>2%|且金额|>5亿|=关注，|>3%|且|>1亿|或|>20亿|=强信号；≥3只核心宽基同向异动=共振·疑似国家队；连续3日同向=趋势性增/减仓',
            }
            print(f"  ntRotation: {len(groups)} groups, resonance={resonance['hit']}")
    except Exception as e:
        print(f"  Warning: ntRotation failed: {e}")

    # ════════ 2. 板块资金轮动（份额口径） ════════
    try:
        snap_days = [d0 for d0 in sorted(cache['snapshots'].keys()) if d0 <= od]
        cur_day = snap_days[-1] if snap_days else None
        prev1 = snap_days[-2] if len(snap_days) >= 2 else None
        prev5 = snap_days[-6] if len(snap_days) >= 6 else None
        shares_cur = cache['snapshots'].get(cur_day, {}) if cur_day else {}
        cats = {}
        for tc, s1 in shares_cur.items():
            cat = _etf_classify(cache['names'].get(tc, ''))
            close = float(close_now.get(tc, 0) or 0)
            if close <= 0:
                continue
            slot = cats.setdefault(cat, {'todayNet': 0.0, 'net5d': 0.0, 'count': 0})
            slot['count'] += 1
            if prev1 and tc in cache['snapshots'][prev1]:
                slot['todayNet'] += (s1 - cache['snapshots'][prev1][tc]) * close
            if prev5 and tc in cache['snapshots'][prev5]:
                slot['net5d'] += (s1 - cache['snapshots'][prev5][tc]) * close
        money = cats.pop('货币', None)  # 货币ETF份额巨大且属现金管理，不计入轮动
        items = [{'cat': c, 'todayNet': round(v['todayNet'], 1),
                  'net5d': round(v['net5d'], 1), 'count': v['count']}
                 for c, v in cats.items()]
        items.sort(key=lambda x: -x['net5d'])
        inflow3 = [i['cat'] for i in items if i['net5d'] > 0][:3]
        outflow3 = [i['cat'] for i in reversed(items) if i['net5d'] < 0][:3]
        data['etfRotation'] = {
            'trade_date': f"{od[:4]}-{od[4:6]}-{od[6:]}",
            'items': items,
            'inflowTop3': inflow3,
            'outflowTop3': outflow3,
            'totalToday': round(sum(i['todayNet'] for i in items), 1),
            'total5d': round(sum(i['net5d'] for i in items), 1),
            'moneyToday': round(money['todayNet'], 1) if money else None,
            'note': '份额变化×当日收盘价估算（不含货币ETF），5日净额按分类汇总；新发/退市ETF会造成少量误差',
        }
        print(f"  etfRotation: {len(items)} categories, inflow {inflow3}, outflow {outflow3}")
    except Exception as e:
        print(f"  Warning: etfRotation failed: {e}")

    # ════════ 3. 国家队持仓估算（已下线，清除存量字段；占比配置保留供轮动v2复用） ════════
    data.pop('nationalTeamEst', None)

    # ════════ 4. 宽基波动率（ETF VIX） ════════
    try:
        vol_items = []
        for ic, iname in VOL_INDICES.items():
            hist = cache['idx'].get(ic, {})
            days = sorted(hist.keys())
            closes = [hist[d] for d in days]
            hv20 = _hv(closes, 20)
            hv60 = _hv(closes, 60)
            hv20_prev = _hv(closes[:-5], 20) if len(closes) > 25 else None
            # HV20 近一年分位
            hv20_series = [_hv(closes[:i + 1], 20) for i in range(20, len(closes))]
            hv20_1y = hv20_series[-250:] if len(hv20_series) > 250 else hv20_series
            hv_pct = _pct_rank100(hv20_1y, hv20)
            # PE TTM + 近2年分位
            bh = cache['idxBasic'].get(ic, {})
            bdays = sorted(bh.keys())
            pe = bh[bdays[-1]] if bdays else None
            pe_pct = _pct_rank100([bh[d] for d in bdays], pe)
            if hv20 is not None and hv60 is not None:
                if hv20 > hv60 * 1.2:
                    status = '升温'
                elif hv20 < hv60 * 0.85:
                    status = '降温'
                else:
                    status = '平稳'
            else:
                status = '数据不足'
            low = bool(hv_pct is not None and hv_pct < 25)
            vol_items.append({
                'code': ic, 'name': iname, 'hv20': hv20, 'hv60': hv60,
                'hv20Chg5': round(hv20 - hv20_prev, 1) if hv20 is not None and hv20_prev is not None else None,
                'hvPct1y': hv_pct, 'peTtm': pe, 'pePct2y': pe_pct,
                'status': status, 'low': low,
            })
        data['indexVol'] = {
            'trade_date': f"{eff[:4]}-{eff[4:6]}-{eff[6:]}",
            'items': vol_items,
            'note': 'HV20/HV60为年化历史波动率；HV20>HV60×1.2升温，<HV60×0.85降温；低位=HV20近一年分位<25%',
        }
        # 每日评语速览·宽基低波提示：HV20 近一年分位 <25% 的宽基全部列出；无命中则清除残留字段
        low_hits = [v for v in vol_items if v.get('low')]
        if low_hits:
            names = '、'.join(v['name'] for v in low_hits)
            pcts = '/'.join(f"{v['hvPct1y']:.0f}%" for v in low_hits)
            data['lowVolDigest'] = (f"宽基低波：{names} 20日波动率处一年低位"
                                    f"（分位 {pcts}），形态发育友好。")
        else:
            data.pop('lowVolDigest', None)
        print(f"  indexVol: {len(vol_items)} indices, low={len(low_hits)}, "
              + ', '.join(f"{v['name']}{v['status']}" for v in vol_items[:3]))
    except Exception as e:
        print(f"  Warning: indexVol failed: {e}")

    # ════════ 5. 自动短评 ════════
    try:
        data['nationalTeamComment'] = _build_nt_comment(data)
        print(f"  nationalTeamComment: {data['nationalTeamComment'][:60]}...")
    except Exception as e:
        print(f"  Warning: nationalTeamComment failed: {e}")


def _build_nt_comment(data):
    """规则生成 3-5 句平实短评。"""
    sents = []
    rot = data.get('etfRotation') or {}
    radar = data.get('etfShareRadar') or {}
    vol = data.get('indexVol') or {}

    # 1) 全市场 ETF 份额净增减
    if rot:
        t = rot.get('totalToday', 0)
        if abs(t) < 1:
            sents.append("全市场ETF（不含货币）昨日份额基本持平（净额不足1亿元）。")
        else:
            direction = '净申购' if t >= 0 else '净赎回'
            sents.append(f"全市场ETF（不含货币）昨日{direction}约{abs(t):.0f}亿元（份额变化×收盘价口径）。")

    # 2) 异动
    alerts = [i for i in radar.get('items', []) if i.get('alert')]
    if alerts:
        a = alerts[0]
        act = '进场' if (a.get('chg1') or 0) > 0 else '出场'
        sent = f"{a['name']}单日份额{a['chg1']:+.2f}亿份（约{a['amt1']:+.1f}亿元），疑似大资金{act}"
        ntr_res = (data.get('ntRotation') or {}).get('resonance') or {}
        if not ntr_res.get('hit'):
            sent += "；单边异动、未见跨公司共振，更可能是汇金自身调仓而非托市信号"
        sents.append(sent + "。")
    elif radar:
        sents.append("19只重点监控ETF份额未见明显异动，无大资金进出信号。")

    # 3) 板块轮动主线
    if rot.get('inflowTop3') or rot.get('outflowTop3'):
        inflow = '、'.join(rot.get('inflowTop3') or []) or '无'
        outflow = '、'.join(rot.get('outflowTop3') or []) or '无'
        sents.append(f"近5日份额口径资金主要流入{inflow}类，流出{outflow}类。")

    # 4) 国家队轮动：系列异动 + 共振 + 央企主题组动作
    ntr = data.get('ntRotation') or {}
    if ntr:
        res = ntr.get('resonance') or {}
        if res.get('hit'):
            sents.append(f"{res['count']}只核心宽基ETF（{'、'.join(res.get('names', [])[:4])}等）"
                         f"同日同向{res['direction']}，呈共振形态，疑似国家队统一动作/托市信号。")
        else:
            # 找异动最集中的系列
            hot = []
            for g in ntr.get('groups', []):
                if g.get('key') != 'broad':
                    continue
                for s in g.get('series', []):
                    n = sum(1 for r in s.get('items', []) if r.get('signal'))
                    if n:
                        hot.append((n, s['name']))
            if hot:
                hot.sort(reverse=True)
                sents.append(f"宽基组中{hot[0][1]}异动最集中（{hot[0][0]}只触发信号），但未达共振标准。")
            else:
                sents.append("宽基组各系列份额平稳，未见国家队典型操作痕迹。")
        # ── 利多/利空点名：按系列合计份额金额映射到宽基指数/主题（B）──
        flow_sents = []
        calm_series = []
        for g in ntr.get('groups', []):
            for s in g.get('series', []):
                t = s.get('total') or {}
                amt = t.get('amt1')
                target = SERIES_IMPACT.get(s['name'])
                if not target:
                    continue
                if amt is not None and abs(amt) >= 5:
                    d_ = '净流入' if amt > 0 else '净流出'
                    impact = '利多' if amt > 0 else '利空'
                    flow_sents.append((abs(amt), f"{s['name']}合计{d_}{abs(amt):.1f}亿 → 短期{impact}{target}"))
                elif amt is not None and abs(amt) < 1 and not any(
                        r.get('signal') for r in s.get('items', [])):
                    calm_series.append(f"{target}（份额稳定 → 中性，不受汇金调仓影响）")
        flow_sents.sort(reverse=True)
        for _, txt in flow_sents[:3]:
            sents.append(txt + "。")
        if not flow_sents and calm_series:
            sents.append(f"{calm_series[0]}。")
        soe_sig = []
        soe_trend = []
        for g in ntr.get('groups', []):
            if g.get('key') != 'soe':
                continue
            for s in g.get('series', []):
                for r in s.get('items', []):
                    if r.get('signal'):
                        soe_sig.append(f"{r['name']}（{r['signal']}）")
                    elif r.get('trend3'):
                        impact = '利多' if '增持' in r['trend3'] else '利空'
                        theme = SERIES_IMPACT.get(s['name'], '央企主题')
                        soe_trend.append(f"{r['name']}{r['trend3']} → {impact}{theme}")
        if soe_sig:
            sents.append(f"央企主题组当日有动作：{'、'.join(soe_sig[:3])}；国新/诚通多为发行人关联方，单边异动多为自身调仓。")
        elif soe_trend:
            sents.append(f"央企主题组未见单日异动，但{'、'.join(soe_trend[:2])}。")
        else:
            sents.append("央企主题组（国新/诚通系）当日未见明显动作。")

    # 5) 波动率状态
    vitems = vol.get('items') or []
    if vitems:
        hs = next((v for v in vitems if v['code'] == '000300.SH'), vitems[0])
        txt = f"沪深300波动率HV20为{hs['hv20']}%"
        if hs.get('hvPct1y') is not None:
            txt += f"（近一年{hs['hvPct1y']:.0f}%分位）"
        warming = [v['name'] for v in vitems if v['status'] == '升温']
        lows = [v['name'] for v in vitems if v.get('low')]
        if warming:
            txt += f"，{'、'.join(warming)}波动升温"
        elif lows:
            txt += f"，{'、'.join(lows)}波动处低位"
        else:
            txt += "，主要宽基波动平稳"
        sents.append(txt + "。")
    return ''.join(sents)


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
    print("\n[1/17] Fetching indices (batch)...")
    indices = fetch_indices_batch(pro, trade_date)
    if indices:
        data['indices'] = indices
        for k, v in indices.items():
            print(f"  {v['name']}: {v['value']} ({v['change']:+.2f}%)")

    # ── 2. Stocks (batch) ──
    print("\n[2/17] Fetching stocks (batch)...")
    stocks = fetch_stocks_batch(pro, trade_date)
    if stocks:
        data['stocks'] = stocks
        print(f"  Updated {len(stocks)} stocks")
        for s in stocks[:3]:
            print(f"    {s['name']}: {s['close']} ({s['pctChg']:+.2f}%)")

    # ── 3. ETFs (batch) ──
    print("\n[3/17] Fetching ETFs (batch)...")
    etfs = fetch_etfs_batch(pro, trade_date)
    if etfs:
        data['nationalETF'] = etfs
        print(f"  Updated {len(etfs)} ETFs")
        for e in etfs[:3]:
            print(f"    {e['name']}: {e['close']} ({e['changePct']:+.2f}%)")

    # ── 4. My ETF account (fund_daily, batch) ──
    print("\n[4/17] Fetching my ETF account (fund_daily, batch)...")
    my_etfs = fetch_my_etfs(pro, trade_date)
    if my_etfs:
        data['myETF'] = my_etfs
        print(f"  Updated {len(my_etfs)} my ETFs")
        for e in my_etfs[:3]:
            print(f"    {e['name']}: {e['close']} ({e['changePct']:+.2f}%)")

    # ── 4b. 备选 ETF 池（纯展示，不进信号/预警）──
    alt_etfs = fetch_my_etfs(pro, trade_date, MY_ETFS_ALT)
    if alt_etfs:
        data['myETFAlt'] = alt_etfs
        print(f"  Updated {len(alt_etfs)} alt ETFs（备选池）")

    # ── 5. Announcements + holdingsNews (全量覆盖旧手工数据) ──
    print("\n[5/17] Fetching announcements & building holdingsNews...")
    anns_map = fetch_announcements(pro, trade_date)
    data['holdingsNews'] = build_holdings_news(anns_map, trade_date)
    total_anns = sum(len(e['items']) for e in data['holdingsNews'])
    print(f"  Built {len(data['holdingsNews'])} holdingsNews entries, {total_anns} announcements")

    # ── 6. Mainforce flow ──
    print("\n[6/17] Fetching mainforce flow...")
    inflow, outflow = fetch_mainforce_flow(pro, trade_date)
    if inflow:
        data['mainforce_inflow_top10'] = inflow
        print(f"  Inflow #1: {inflow[0]['name']} {inflow[0]['amount']}")
    if outflow:
        data['mainforce_outflow_top10'] = outflow
        print(f"  Outflow #1: {outflow[0]['name']} {outflow[0]['amount']}")

    # ── 7. Hot fund NAVs (fund_nav, 取到才覆盖) ──
    print("\n[7/17] Fetching hot fund NAVs...")
    hot_navs = fetch_hot_fund_navs(pro, trade_date, data.get('hotFundNavs', []))
    if hot_navs:
        data['hotFundNavs'] = hot_navs
        dates = {h.get('date', '') for h in hot_navs}
        print(f"  Updated {len(hot_navs)} fund NAVs, dates: {sorted(dates)}")

    # ── 8. National ETF watch (宽基ETF份额监控) ──
    print("\n[8/17] Fetching national ETF watch (fund_share)...")
    etf_watch = fetch_national_etf_watch(pro, trade_date, data.get('nationalETFWatch'))
    if etf_watch:
        data['nationalETFWatch'] = etf_watch
        t = etf_watch['total']
        print(f"  {len(etf_watch['items'])} ETFs as of {etf_watch['trade_date']}, "
              f"total netFlow {t['netFlow']:+.2f}亿, 5d {t['netFlow5d']:+.2f}亿")

    # ── 9. Bond yields + liquidity commentary (东方财富) ──
    print("\n[9/17] Fetching bond yields & liquidity commentary (eastmoney)...")
    fetch_bond_yields(trade_date, data)

    # ── 10. North/South bound ──
    print("\n[10/17] Fetching north/south bound...")
    north, south = fetch_north_south(pro, trade_date)
    if north:
        data['northbound'] = north
        print(f"  Northbound: {north['today']}亿")
    if south:
        data['southbound'] = south
        print(f"  Southbound: {south['today']}亿")

    # ── 10b. 两融汇总 / 南向持股集中度 / 杠杆控盘集中度（Tushare 日更）──
    fetch_margin_summary(pro, trade_date, data)
    fetch_southbound_concentration(pro, trade_date, data)
    fetch_leverage_concentration(pro, trade_date, data)

    # ── 11. Sector index commentary (细分指数每日点评) ──
    print("\n[11/17] Fetching sector index commentary...")
    # 涨跌停信号卡已废弃：不再生成 keySignals，并删除存量字段
    data.pop('keySignals', None)
    commentary = fetch_sector_commentary(pro, trade_date)
    if commentary:
        data['sectorCommentary'] = commentary
        print(f"  Built {len(commentary)} sector commentaries")
        for c in commentary[:3]:
            print(f"    {c['name']}: {c['pctChg']:+.2f}% - {c['comment']}")

    # ── 12. Sector watch: 扫描榜(仅信号) + 底部资金积聚 (Tushare 历史沉淀) ──
    print("\n[12/17] Building sector watch (scan + bottom accumulation)...")
    watch_ctx = fetch_sector_watch(pro, trade_date, data)
    data.pop('conceptHot', None)  # 主题概念领涨栏目已下线，清除存量字段

    # ── 13. ECI 六维分每日真算 + 强势一级行业子板块精选 ──
    print("\n[13/17] Rebuilding ECI from sector history + picking subsectors...")
    fetch_eci_daily(pro, trade_date, data, watch_ctx)
    apply_dual_confirm(data)   # C. 资金积聚×ECI前10 双确认（纯展示层联动）

    # ── 14. 融资余额突变预警（持仓+观察股） ──
    print("\n[14/17] Building margin watch (融资融券)...")
    fetch_margin_watch(pro, trade_date, data)

    # ── 15. 三档净流入（近5/10/20日 + 资金节奏，sector_history 缓存计算） ──
    print("\n[15/17] Building sector flows (3-tier net inflow)...")
    build_sector_flows(data)
    build_actionable_sectors(data)   # D. 能投板块短名单（bottomWatch×ECI×资金节奏×扫描榜）
    build_eci_quadrant(data)         # 行业景气四象限（X=ECI 当前值，Y=较上月同口径变化）

    # ── 16. VCP 板块-龙头共振监测（增量维护 vcp_cache） ──
    print("\n[16/17] Building VCP watch (板块-龙头共振)...")
    fetch_vcp_watch(pro, trade_date, data)

    # ── 16b. 个股级 VCP 精扫（A500∪SZ50∪HS300 池，日线+周线双级别）──
    print("\n[16b/17] Building stock-level VCP scan (vcpStocks)...")
    _today_map = watch_ctx[3] if watch_ctx else {}
    fetch_vcp_stocks(pro, trade_date, data, _today_map)

    # ── 16c. 总览漏斗：第2步选龙头（含概念板块）+ 第4步排雷 ──
    print("\n[16c/17] Building leader step (sectors+concepts) + mine watch...")
    try:
        build_leader_step(pro, trade_date, data, _today_map)
    except Exception as e:
        print(f"  Warning: leaderStep failed: {e}")
    try:
        build_mine_watch(pro, trade_date, data)
    except Exception as e:
        print(f"  Warning: mineWatch failed: {e}")

    # ── 17. 国家队升级：份额雷达 + 板块轮动 + 汇金估算 + 宽基波动率 + 短评 ──
    print("\n[17/17] Building national team upgrade (share radar / rotation / est / vol)...")
    fetch_nt_upgrade(pro, trade_date, data)

    # ── Metadata ──
    # updateTime 以数据实际最新日期为准（盘中/早间运行时各板块数据仍是前一交易日）
    actual_date = (data.get('sectorFlows') or {}).get('trade_date') or \
        f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    data['updateTime'] = f"{actual_date} 收盘 (Tushare自动)"

    # 本周资金监测标签：最新数据日所在交易周的周一~周五（动态计算，修复静态残留）
    _dt = datetime.strptime(actual_date, '%Y-%m-%d')
    _mon = _dt - timedelta(days=_dt.weekday())
    _fri = _mon + timedelta(days=4)
    data['week'] = f"{_mon:%Y.%m.%d} - {_fri:%m.%d}"

    # sectorPeriod（近4周主力累计）：最新数据日往前 20 个交易日的窗口（同为静态残留修复）
    try:
        _cal_start = (_dt - timedelta(days=45)).strftime('%Y%m%d')
        _cal = pro.trade_cal(exchange='SSE', start_date=_cal_start,
                             end_date=actual_date.replace('-', ''), is_open='1')
        _open_days = sorted(_cal['cal_date'].tolist())[-20:]
        if len(_open_days) >= 2:
            _p0 = f"{_open_days[0][:4]}.{_open_days[0][4:6]}.{_open_days[0][6:]}"
            _p1 = f"{_open_days[-1][:4]}.{_open_days[-1][4:6]}.{_open_days[-1][6:]}"
            data['sectorPeriod'] = f"{_p0}~{_p1} (近4周主力累计)"
    except Exception as e:
        print(f"  Warning: sectorPeriod compute failed, keep existing: {e}")

    # 大盘状态：最新数据日=今天 → 正常交易；否则明示数据截至日期（周末/节假日）
    if actual_date == datetime.now().strftime('%Y-%m-%d'):
        data['marketStatus'] = '正常交易'
    else:
        data['marketStatus'] = f"数据至 {actual_date[5:7]}月{actual_date[8:10]}日 收盘"

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
