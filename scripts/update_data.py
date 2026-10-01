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
import statistics
import requests
import tushare as ts
import re
import urllib.request
import urllib.parse

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
    '600031.SH': {'name': '三一重工', 'industry': '工程机械', 'group': 'watch', 'watchPrice': 0},
}

# 用户 ETF 账户（行情走 fund_daily，与 nationalETF 的 daily 不同）
MY_ETFS = {
    '159883.SZ': {'name': '永赢中证全指医疗器械ETF',   'ticker': '159883'},
    '159892.SZ': {'name': '华夏恒生生物科技ETF(QDII)', 'ticker': '159892'},
    '159265.SZ': {'name': '鹏华国证港股通消费主题ETF', 'ticker': '159265'},
    '518880.SH': {'name': '华安易富黄金ETF',           'ticker': '518880'},
    '562510.SH': {'name': '华夏中证旅游主题ETF',       'ticker': '562510'},
    '159731.SZ': {'name': '华夏中证石化产业ETF',         'ticker': '159731'},
    '512070.SH': {'name': '易方达沪深300非银行金融ETF',  'ticker': '512070'},
}

# 备选 ETF 池（2026-08-28 用户指令新增；09-03 石化/非银转正后仅剩银行）：纯展示，不进任何信号/预警计算
MY_ETFS_ALT = {
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
                    'auto': info.get('auto'),   # 第三步自动收录标记（2026-09-30，非自动收录为 None）
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


# fetch_hot_fund_navs 已删除（2026-10-01 死字段清理：hotFundNavs 前端无消费，省 fund_nav 调用/日）
# 宽基 ETF 份额监控池（核心宽基申赎动向名单，16 只）
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
SECTOR_BACKFILL_DAYS = 250      # 首次运行回补交易日数（250=一年窗口，支撑历史位置分层；每日 2 次调用，落盘可断点续传）
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
    lw = [i for i in items if i['status'] == '低位关注']
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
    if lw:
        parts.append(f"{len(lw)}个板块低位关注（{'、'.join(i['sector'] for i in lw[:3])}）：历史低位+持续流入")
    return '今日' + '；'.join(parts) + '。'


SCAN_POSITION_NOTE = ('位置口径：行业等权收益合成指数近似（非真实板块指数）；'
                      '⭐低位=距60日高点回撤≥3%且近20日涨幅≤10%（回测10日胜率约59%）；'
                      '高位=距60日高点<3%或近20日涨幅>10%（回测10日胜率仅17~29%）；'
                      '历史位置=250日（或可得最长）窗口一年分位，🟢历史低位=分位≤30%或距250日高点回撤≥20%；'
                      '双头风险/高位流入·谨慎需一年分位≥70%才生效（历史低位的短窗新高不再误判）；'
                      '低位关注=历史低位+连续净流入≥2天（涨幅温和未触发启动/吸筹）；'
                      '缩量=近5日均额/前5日均额<0.8，低位缩量吸筹加分')


def build_sector_scan(hist, trade_date, today_map):
    """板块资金扫描榜（精简版）：只保留触发信号的板块，每个板块附 2 只吸筹个股。

    信号规则（2026-09-08 历史位置分层版，数据来自行业资金历史沉淀）：
    - 短窗位置分层（等权收益合成指数近似，非真实板块指数）：
      高位 = 距60日高点 <3% 或 近20日涨幅 >10%；
      低位 = 距60日高点回撤 ≥3% 且 近20日涨幅 ≤10%；半路 = 历史不足等兜底。
    - 长窗历史位置（一年窗口）：histPct=250日（或可得最长）价格分位，
      distHigh250=距250日高点回撤；历史低位=分位≤30 或 回撤≥20%，历史高位=分位≥70。
    - 高潮风险：连续净流入 ≥3 天 且 近5日涨幅 ≥8%（任何位置都发，最高优先）
    - 双头风险：距60日高点<3% + 连续净流入 ≥2 天 + 流入减速（当日 < 近3日均值）
      **且历史高位（一年分位≥70）**——历史低位的"接近短窗前高"不再误判双头
    - 启动确认：连续净流入 ≥2 天 且 当日涨幅 ≥1.5%（仅当 短窗高位且历史高位 时降「高位流入·谨慎」；
      短窗高但长窗不高 → 正常发启动确认，tier=mid）
    - 吸筹中：连续净流入 ≥3 天 且 当日涨幅 <1%（同上高位谨慎门槛；低位/历史低位+量比<0.8 标记"缩量"）
    - 低位关注：历史低位 + 连续净流入 ≥2 天（涨幅温和未触发启动/吸筹的兜底信号，tier=core）
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

        # ── 长周期历史位置（2026-09-08 新增）：一年窗口分位 + 距250日高点回撤 ──
        # 短窗（60日）分层无法识别"长期低位反弹"（如机场/旅游服务：长周期低位、
        # 短期贴近60日新高被误判双头）。历史高位（hist_high）作为双头/高位谨慎的一票否决前提。
        win250 = pxs[-250:]
        hist_pct = _pct_rank100(win250, px)
        dist_high250 = (px / max(win250) - 1) * 100
        hist_low = hist_pct is not None and (hist_pct <= 30 or dist_high250 <= -20)
        hist_high = hist_pct is not None and hist_pct >= 70

        # 量比：近5日均额 / 前5日均额
        amt5 = sum(r[3] for r in rows[-5:]) / 5
        amt_prev5 = sum(r[3] for r in rows[-10:-5]) / 5 if len(rows) >= 10 else 0
        vol_ratio = round(amt5 / amt_prev5, 2) if amt_prev5 > 0 else None

        # ── 信号判定（高潮风险 > 双头风险（需历史高位）> 启动/吸筹（高位谨慎需历史高位）> 低位关注）──
        slowing = consec >= 2 and rows[-1][1] < sum(r[1] for r in rows[-3:]) / 3
        low_vol = (tier == 'low' or hist_low) and vol_ratio is not None and vol_ratio < 0.8
        if consec >= 3 and pct5 >= 8:
            status, out_tier = '高潮风险', 'risk'
        elif dist_high > -3 and slowing and hist_high:
            status, out_tier = '双头风险', 'risk'
        elif consec >= 2 and ret1 >= 1.5:
            if tier == 'high' and hist_high:
                status, out_tier = '高位流入·谨慎', 'high'
            else:
                # 短窗偏高但一年分位未达高位 → 正常发启动确认（不降级）
                status, out_tier = '启动确认', ('core' if (tier == 'low' or hist_low) else 'mid')
        elif consec >= 3 and ret1 < 1:
            if tier == 'high' and hist_high:
                status, out_tier = '高位流入·谨慎', 'high'
            else:
                status, out_tier = '吸筹中', ('core' if (tier == 'low' or hist_low) else 'mid')
        elif hist_low and consec >= 2:
            status, out_tier = '低位关注', 'core'
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
            'histPct': hist_pct,
            'distHigh250': round(dist_high250, 1),
            'histLow': hist_low,
            'histHigh': hist_high,
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
    """板块龙头统一口径（bottomWatch 卡片与 dualAxes 趋势轴共用，禁止各算各的）：
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


def _ensure_mf_cache(pro, trade_date):
    """主力资金流缓存（全市场，10 天滚动）：短线轴龙头排名 + 排雷资金雷共用。
    每晚 1 次全市场 moneyflow 调用（当日已缓存则 0 调用）。net_mf_amount 万元→亿。"""
    mf_cache = _load_json_cache(MINE_MF_CACHE_PATH, {})
    if trade_date not in mf_cache:
        try:
            time.sleep(API_DELAY)
            mf = pro.moneyflow(trade_date=trade_date)
            if mf is not None and len(mf):
                mf_cache[trade_date] = {r['ts_code']: round(float(r['net_mf_amount']) / 1e4, 2)
                                        for _, r in mf.iterrows()}
        except Exception as e:
            print(f"  Warning: moneyflow cache update failed: {e}")
        days_sorted = sorted(mf_cache)[-10:]
        mf_cache = {d: mf_cache[d] for d in days_sorted}
        _save_json_cache(MINE_MF_CACHE_PATH, mf_cache)
    return mf_cache


def _short_leaders(sector, today_map, mf_cache, max_n=3):
    """短线龙头：板块成员按近 5 日主力净流入（全市场缓存，0 额外调用）排名取前 N；
    缓存覆盖不足 2 只时回退今日主力净流入前 N（today_map 既有顺序）。"""
    members = today_map.get(sector) or []
    days = sorted(mf_cache)[-5:]
    scored = []
    for s in members[:12]:
        nets = [mf_cache[d][s['code']] for d in days if s['code'] in mf_cache.get(d, {})]
        if len(nets) >= 3:
            scored.append((sum(nets), s))
    if len(scored) < 2:
        return [{'name': s['name'], 'code': s['code'], 'pctChg': s['pct'],
                 'strength': '今日主力净流入居前（资金口径）'} for s in members[:max_n]]
    scored.sort(key=lambda x: -x[0])
    return [{'name': s['name'], 'code': s['code'], 'pctChg': s['pct'],
             'strength': f'近5日主力净流入{net:+.1f}亿'} for net, s in scored[:max_n]]


# ══════════ 宽基 ETF：趋势评估 + 宽基 VCP（2026-09-01 用户拍板新增） ══════════

BROAD_IDX_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    'cache', 'broad_idx_cache.json')
# 9 大宽基 → 代表 ETF（名称 2026-09-01 经 fund_basic 核实；展示顺序=用户指定顺序）
BROAD_ETF_MAP = [
    ('000300.SH', '沪深300',   '510300.SH', '华泰柏瑞沪深300ETF'),
    ('000016.SH', '上证50',    '510050.SH', '华夏上证50ETF'),
    ('000905.SH', '中证500',   '510500.SH', '南方中证500ETF'),
    ('000852.SH', '中证1000',  '512100.SH', '南方中证1000ETF'),
    ('000688.SH', '科创50',    '588000.SH', '华夏科创50ETF'),
    ('399006.SZ', '创业板指',  '159915.SZ', '易方达创业板ETF'),
    ('000510.SH', '中证A500',  '512050.SH', '华夏中证A500ETF'),
    ('000001.SH', '上证综指',  '510210.SH', '富国上证综指ETF'),
    ('399001.SZ', '深证成指',  '159903.SZ', '南方深证成份ETF'),
]


def _broad_idx_bars(pro, trade_date):
    """9 大宽基指数日线 OHLCV 缓存（[date, close, high, low, vol]，≤300 条滚动）。
    每晚 1 次 index_daily 批量调用（按 trade_date 全量快照过滤 9 只）；
    首次/缺历史时逐只回补（≤9 次，一次性）。"""
    cache = _load_json_cache(BROAD_IDX_CACHE_PATH, {})
    try:
        time.sleep(API_DELAY)
        snap = pro.index_daily(trade_date=trade_date)
        if snap is not None and len(snap):
            for _, r in snap.iterrows():
                tc = r['ts_code']
                if tc not in [c for c, _, _, _ in BROAD_ETF_MAP]:
                    continue
                rows = cache.setdefault(tc, [])
                if not rows or rows[-1][0] != trade_date:
                    rows.append([trade_date, round(float(r['close']), 3),
                                 round(float(r['high']), 3), round(float(r['low']), 3),
                                 round(float(r['vol']), 1)])
    except Exception as e:
        print(f"  Warning: broad idx daily batch failed: {e}")
    for tc, _, _, _ in BROAD_ETF_MAP:
        rows = cache.get(tc, [])
        if len(rows) < 120:
            try:
                time.sleep(API_DELAY)
                start = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=600)).strftime('%Y%m%d')
                df = pro.index_daily(ts_code=tc, start_date=start, end_date=trade_date)
                if df is not None and len(df):
                    have = {r[0] for r in rows}
                    for _, r in df.sort_values('trade_date').iterrows():
                        if r['trade_date'] not in have:
                            rows.append([r['trade_date'], round(float(r['close']), 3),
                                         round(float(r['high']), 3), round(float(r['low']), 3),
                                         round(float(r['vol']), 1)])
                    rows.sort(key=lambda x: x[0])
                    cache[tc] = rows
            except Exception as e:
                print(f"  Warning: broad idx backfill failed for {tc}: {e}")
        cache[tc] = cache.get(tc, [])[-300:]
    _save_json_cache(BROAD_IDX_CACHE_PATH, cache)
    return cache


BROAD_ETF_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    'cache', 'broad_etf_cache.json')
# 2026-09-26 用户拍板：50/300/500 置顶（只做不高估的 500/300/50 标的，直接买宽基 ETF）
BROAD_TOP3 = ['000016.SH', '000300.SH', '000905.SH']


def _broad_etf_bars(pro, trade_date):
    """9 只宽基代表 ETF 日线 OHLCV 缓存（fund_daily，[date, close, high, low, vol]，≤300 条滚动）。
    每晚 fund_daily(trade_date) 批量 1 次过滤 9 只；首次/缺历史逐只回补（≤9 次，一次性）。
    2026-09-26 月底大改版②：宽基买点直接对 ETF 行情算（枢轴价=ETF 价格，可直接下单口径）。"""
    cache = _load_json_cache(BROAD_ETF_CACHE_PATH, {})
    codes = [ec for _, _, ec, _ in BROAD_ETF_MAP]
    try:
        time.sleep(API_DELAY)
        snap = pro.fund_daily(trade_date=trade_date)
        if snap is not None and len(snap):
            for _, r in snap.iterrows():
                tc = r['ts_code']
                if tc not in codes:
                    continue
                rows = cache.setdefault(tc, [])
                if not rows or rows[-1][0] != trade_date:
                    rows.append([trade_date, round(float(r['close']), 4),
                                 round(float(r['high']), 4), round(float(r['low']), 4),
                                 round(float(r['vol']), 1)])
    except Exception as e:
        print(f"  Warning: broad etf daily batch failed: {e}")
    for tc in codes:
        rows = cache.get(tc, [])
        if len(rows) < 120:
            try:
                time.sleep(API_DELAY)
                start = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=600)).strftime('%Y%m%d')
                df = pro.fund_daily(ts_code=tc, start_date=start, end_date=trade_date)
                if df is not None and len(df):
                    have = {r[0] for r in rows}
                    for _, r in df.sort_values('trade_date').iterrows():
                        if r['trade_date'] not in have:
                            rows.append([r['trade_date'], round(float(r['close']), 4),
                                         round(float(r['high']), 4), round(float(r['low']), 4),
                                         round(float(r['vol']), 1)])
                    rows.sort(key=lambda x: x[0])
                    cache[tc] = rows
            except Exception as e:
                print(f"  Warning: broad etf backfill failed for {tc}: {e}")
        cache[tc] = cache.get(tc, [])[-300:]
    _save_json_cache(BROAD_ETF_CACHE_PATH, cache)
    return cache


def _etf_form_state(ebars, tier):
    """宽基 ETF 形态五档（2026-09-26 用户口径）：
    高位发散 / 突破确认（收盘>枢轴且量≥50日均量×1.4）/ 临近枢轴（距枢轴≤3%）/
    构筑基底（平台成型，距枢轴 3~8%）/ 低波蓄势（未成型但近20日振幅≤8%且缩量）。
    返回 dict（state/pivot/distPct/volConfirm/invalidation/pattern/days）。"""
    if len(ebars) < 60:
        return {'state': '无形态', 'pattern': None}
    bars = [[r[0], r[2], r[3], r[1], r[4]] for r in ebars]  # (date, high, low, close, vol)
    close = ebars[-1][1]
    vol50 = sum(r[4] for r in ebars[-50:]) / 50
    last_vol = ebars[-1][4]
    v = _vcp_platform(bars)
    if tier == '高位':
        st = {'state': '高位发散', 'pattern': None}
    elif v and v['formed']:
        n = v['days']
        plat_lo = min(b[2] for b in bars[-n:])
        dist = v['distPct']
        if dist < -5:
            state = '高位发散'
        elif dist < 0:
            state = '突破确认' if last_vol >= vol50 * BREAKOUT_VOL_X else '突破待确认（未放量）'
        elif dist <= 3:
            state = '临近枢轴'
        else:
            state = '构筑基底'
        st = {'state': state, 'pattern': v['type'], 'days': v['days'],
              'pivot': v['pivot'], 'distPct': dist,
              'amplitude': v['amplitude'], 'volRatio': v.get('volRatio'),
              'volConfirm': round(vol50 * BREAKOUT_VOL_X, 0),
              'invalidation': round(plat_lo, 4)}
    else:
        recent = ebars[-20:]
        amp20 = (max(r[2] for r in recent) - min(r[3] for r in recent)) / min(r[3] for r in recent) * 100
        vol10 = sum(r[4] for r in ebars[-10:]) / 10
        if amp20 <= 8 and vol10 < vol50:
            st = {'state': '低波蓄势', 'pattern': None,
                  'amp20': round(amp20, 1), 'volRatio': round(vol10 / vol50, 2) if vol50 else None}
        else:
            st = {'state': '无形态', 'pattern': None}
    st['etfClose'] = close
    return st


def build_broad_watch(pro, trade_date, data):
    """宽基 ETF 趋势评估（趋势轴宽基组）+ 宽基 VCP 三档监测（第3步宽基分区+速览提示）。

    - 趋势位置层（与板块扫描同口径，用指数收盘）：高位=距60日高点>-3% 或 近20日涨幅>10%；
      低位=距60日高点≤-5% 且 近20日涨幅≤5%；其余=半路。
      低位且份额资金未流出=✅趋势候选；半路=观察；高位=仅展示标灰。
    - 份额资金：etfShareRadar 13 只雷达内 ETF 直接引用 5 日份额变化；雷达外标注"无份额监测"。
    - 波动率：引用 indexVol 的 HV20 近一年分位。
    - 宽基 VCP：复用 _vcp_platform（杯柄型/底部平台型同口径），状态三档——
      未突破·观察（成型但距枢轴≥5%，盯突破）、临近买点（距枢轴<5%）、已突破（收盘站上枢轴）。
    每晚新增调用：index_daily 批量 1 次（与 nt_upgrade 既有调用不同维度，独立缓存）。
    """
    d = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    cache = _broad_idx_bars(pro, trade_date)
    etf_cache = _broad_etf_bars(pro, trade_date)   # 2026-09-26 改版②：买点直接对 ETF 行情算
    radar = {i['code']: i for i in (data.get('etfShareRadar') or {}).get('items', [])}
    vol_map = {i['code']: i for i in (data.get('indexVol') or {}).get('items', [])}
    trend_items, vcp_items = [], []
    # 展示顺序：上证50/沪深300/中证500 置顶，其余宽基排后（2026-09-26 用户拍板）
    ordered = sorted(BROAD_ETF_MAP,
                     key=lambda m: (BROAD_TOP3.index(m[0]) if m[0] in BROAD_TOP3 else 99))
    for ic, iname, ec, ename in ordered:
        rows = cache.get(ic, [])
        if len(rows) < 25:
            continue
        closes = [r[1] for r in rows]
        close = closes[-1]
        dist_high = round((close / max(closes[-60:]) - 1) * 100, 1)
        ret20 = round((close / closes[-21] - 1) * 100, 1) if len(closes) >= 21 else None
        if dist_high > -3 or (ret20 is not None and ret20 > 10):
            tier = '高位'
        elif dist_high <= -5 and (ret20 is None or ret20 <= 5):
            tier = '低位'
        else:
            tier = '半路'
        ri = radar.get(ec)
        if ri:
            share5, share20 = ri.get('chg5Pct'), ri.get('chg20Pct')
            share_txt = f"份额5日{share5:+.1f}%" if share5 is not None else '份额无变化数据'
            flow_out = share5 is not None and share5 < 0
        else:
            share5 = share20 = None
            share_txt = '无份额监测'
            flow_out = False
        hv = (vol_map.get(ic) or {}).get('hvPct1y')
        if tier == '高位':
            status = '高位·仅展示'
        elif tier == '低位':
            status = '低位观察（份额流出）' if flow_out else '✅趋势候选'
        else:
            status = '观察'
        trend_items.append({'indexCode': ic, 'indexName': iname, 'etfCode': ec, 'etfName': ename,
                            'close': close, 'distHigh60': dist_high, 'ret20': ret20,
                            'tier': tier, 'share5Pct': share5, 'share20Pct': share20,
                            'shareNote': share_txt, 'hvPct1y': hv, 'status': status})
        # ── 形态阶段 + ETF 买点（2026-09-26 改版②：枢轴/失效位直接对 ETF 日线算）──
        eb = etf_cache.get(ec, [])
        st = _etf_form_state(eb, tier)
        vcp_items.append({'indexCode': ic, 'indexName': iname, 'etfCode': ec, 'etfName': ename,
                          'pattern': st.get('pattern'), 'days': st.get('days'),
                          'pivot': st.get('pivot'), 'distPct': st.get('distPct'),
                          'amplitude': st.get('amplitude'), 'volRatio': st.get('volRatio'),
                          'state': st['state'], 'etfClose': st.get('etfClose'),
                          'volConfirm': st.get('volConfirm'), 'invalidation': st.get('invalidation'),
                          'breakoutConfirm': (f"收盘>{st['pivot']} 且成交量≥50日均量×1.4"
                                              f"（≈{st['volConfirm']:.0f}手）"
                                              if st.get('pivot') and st.get('volConfirm') else None),
                          'top3': ic in BROAD_TOP3})
    data['broadTrend'] = {
        'trade_date': d, 'items': trend_items,
        'note': ('位置层口径同板块扫描（高位=距60日高点>-3%或近20日>10%；低位=距高点≤-5%且20日≤5%）；'
                 '低位且份额未流出=✅趋势候选；份额=etfShareRadar 5日份额变化，雷达外标"无份额监测"；'
                 '波动=HV20近一年分位（indexVol）')}
    data['broadVcp'] = {
        'trade_date': d, 'items': vcp_items,
        'note': ('宽基形态五档（2026-09-26 改版，上证50/沪深300/中证500置顶）：高位发散/突破确认（收盘>枢轴且量≥50日均量×1.4）/'
                 '临近枢轴（距枢轴≤3%）/构筑基底（平台成型距枢轴3~8%）/低波蓄势（近20日振幅≤8%且缩量）；'
                 '枢轴价/失效位直接对跟踪 ETF 日线计算（fund_daily），为可直接下单口径；'
                 '突破确认与失效位为形态参数，非操作建议')}
    # broadVcpDigest 字段已删除（2026-10-01 死字段清理：前端无任何渲染消费）
    print(f"  broadWatch: 趋势 {len(trend_items)} 只"
          f"（✅{sum(1 for i in trend_items if i['status'] == '✅趋势候选')}），"
          f"形态五档 "
          + '、'.join(f"{i['indexName']}:{i['state']}" for i in vcp_items[:4]))


def build_long_window(data):
    """做多窗口判定（2026-09-26 月底大改版③，层级服从门控大级别）。

    规则（优先级 水温>宽基）：
    - closed：水温🔴冷，或 上证50/沪深300/中证500 全部处于 高位发散/破位；
    - open：水温🟢暖 且三只中至少一只处于 临近枢轴/突破确认；
    - half：其余情形。
    债券相互关系（2026-09-27 用户拍板纳入）：10Y 收益率近 1 月变动 ≥+10bp
    =资金趋紧，窗口降一档（open→half、half→closed）；≤-10bp=趋松仅作加分备注，
    不主动升档（升档仍需水温+宽基自身满足）。
    window=closed 时板块能投名单/个股 VCP 榜照常计算但前端标灰降级（信号仅观察）；
    half 时正常展示+顶部"半窗"提示；open 时全量高亮。
    """
    temp = ((data.get('bondData') or {}).get('marginTrading') or {}).get('temp') or ''
    verdict = ((data.get('bondData') or {}).get('marginTrading') or {}).get('verdict') or ''
    items = (data.get('broadVcp') or {}).get('items') or []
    top = {i['indexCode']: i for i in items if i.get('indexCode') in BROAD_TOP3}
    states = {c: (top.get(c) or {}).get('state', '无数据') for c in BROAD_TOP3}
    names = {'000016.SH': '上证50', '000300.SH': '沪深300', '000905.SH': '中证500'}
    near = any(s in ('临近枢轴', '突破确认') for s in states.values())
    all_high = bool(states) and all(s in ('高位发散', '破位', '无数据') for s in states.values())
    if '冷' in temp or all_high:
        w = 'closed'
    elif '暖' in temp and near:
        w = 'open'
    else:
        w = 'half'
    # 债券相互关系：收益率快速上行=资金紧，降一档；快速下行=资金松，仅备注
    y10_1m = (((data.get('bondData') or {}).get('stats') or {}).get('1m_change') or {}).get('y10')
    bond_note = ''
    if y10_1m is not None and y10_1m >= 10:
        if w == 'open':
            w = 'half'
        elif w == 'half':
            w = 'closed'
        bond_note = f'10Y收益率近1月{y10_1m:+.0f}bp快速上行=资金趋紧，窗口降一档'
    elif y10_1m is not None and y10_1m <= -10:
        bond_note = f'10Y收益率近1月{y10_1m:+.0f}bp下行=资金面偏松（加分备注，不主动升档）'
    reason_parts = [f"水温{temp or '—'}（{verdict or '—'}）",
                    '宽基形态：' + '，'.join(f"{names[c]}{states[c]}" for c in BROAD_TOP3)]
    if bond_note:
        reason_parts.append(bond_note)
    if w == 'closed':
        reason_parts.append('大级别无做多窗口，下级信号降级为观察')
    elif w == 'open':
        reason_parts.append('水温偏暖且宽基临近/突破，做多窗口打开')
    else:
        reason_parts.append('半窗：谨慎关注，仓位与信号强度自行降档')
    data['longWindow'] = {
        'window': w, 'temp': temp, 'verdict': verdict,
        'broadStates': {names[c]: states[c] for c in BROAD_TOP3},
        'nearPivot': bool(near), 'allHigh': bool(all_high),
        'bondY10_1m': y10_1m, 'bondNote': bond_note,
        'reason': '；'.join(reason_parts),
        'note': ('层级服从（2026-09-26 用户拍板）：水温>宽基>板块>个股；'
                 'closed=水温🔴冷或50/300/500全部高位发散/破位；open=水温🟢暖且至少一只临近枢轴/突破确认；其余half；'
                 '债券规则（2026-09-27）：10Y收益率近1月≥+10bp=资金紧、窗口降一档，≤-10bp=偏松仅备注不升档；'
                 'closed 时板块/个股信号照常计算但标灰降级"窗口未开，信号仅观察"，half 挂半窗提示，open 全量高亮'),
    }
    print(f"  longWindow: {w}（水温{temp or '—'}；"
          f"{'，'.join(names[c] + states[c] for c in BROAD_TOP3)}"
          f"{('；' + bond_note) if bond_note else ''}）")


# ══════════ 板块形态判定（2026-09-27 第2-3步共振双轨改版，用户正式指令）══════════
SECTOR_VOL_SHRINK_MAX = 0.7   # 量能萎缩极致（自定阈值并注明）：近10日均成交额/近60日均成交额 ≤ 0.7


def _sector_pattern(hist, name):
    """板块等权合成指数的形态检测（与个股同族口径，复用 sector_history 沉淀，零新增 API）。

    价格=行业等权日收益复利净值（sector_history 无日内高低价，high/low 以收盘近似——
    形态为收盘口径近似，阈值沿用个股 Minervini 精修）；量能=行业成交额合计（amt 字段）。
    形态族：VCP收缩（≥3次严格递减收缩+末次收缩均量<首次）/ 杯柄（个股同口径）/
    底部（一年价格分位≤30%）；外加要件：量能萎缩极致（10日/60日均额 ≤0.7）。
    qualified = 任一形态命中 且 缩量极致。历史不足 80 日返回 None。
    """
    rows = _history_series(hist, name)
    if len(rows) < 80:
        return None
    level, closes, amts = 1.0, [], []
    for _, _, ret, amt in rows:
        level *= (1 + ret / 100.0)
        closes.append(level)
        amts.append(amt)
    vol10 = sum(amts[-10:]) / 10
    vol60 = sum(amts[-60:]) / 60
    vol_ratio = vol10 / vol60 if vol60 > 0 else 1.0
    shrink = vol_ratio <= SECTOR_VOL_SHRINK_MAX
    pct1y = _pct_rank100(closes[-250:], closes[-1])
    bottom = pct1y is not None and pct1y <= 30
    bars = [(rows[i][0], closes[i], closes[i], closes[i], amts[i]) for i in range(len(rows))]
    vcp = _vcp_level_strict(bars, VCP_DAILY_WIN, VCP_DAILY_K)
    cup = _cup_handle_strict(bars)
    patterns = []
    if vcp and vcp['formed']:
        patterns.append('VCP收缩')
    if cup and cup['formed']:
        patterns.append('杯柄')
    if bottom:
        patterns.append('底部')
    ev = []
    if vcp and vcp['formed']:
        ev.append(f"VCP {vcp['count']}次收缩{vcp['contractions']}·距枢轴{vcp['distPct']}%")
    if cup and cup['formed']:
        ev.append(f"杯柄·杯深{cup['cupDepth']}%·柄{cup['days']}日")
    if bottom:
        ev.append(f"一年分位{pct1y}%")
    ev.append(f"量能比10/60={vol_ratio:.2f}{'≤0.7✓' if shrink else '>0.7✗'}")
    return {'patterns': patterns,
            'pattern': '+'.join(patterns) if patterns else None,
            'volRatio': round(vol_ratio, 2), 'shrinkExtreme': bool(shrink),
            'pct1y': pct1y, 'qualified': bool(patterns and shrink),
            'evidence': '；'.join(ev)}


# ══════════ 板块聪明钱超额榜（2026-09-27 大改版收官，用户批准并入第2步）══════════
# 名单=三十六节样表策展 45 只主动基金（A 类），家电无合适标的空档保留；覆盖 12 个一级板块。
SMART_NAV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'cache', 'smart_money_nav.json')
SMART_META_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'cache', 'smart_money_meta.json')
SMART_MONEY_NAV_BACKFILL = '20251201'   # 首次回补起点（须覆盖 YTD 基期=上年末）
SMART_MONEY_FUNDS = {
    '医药生物': [
        ('003095.OF', '中欧医疗健康混合-A', 134.1),
        ('001717.OF', '工银瑞信前沿医疗股票-A', 73.5),
        ('004851.OF', '广发医疗保健股票-A', 35.6),
        ('006113.OF', '汇添富创新医药主题混合-A', 92.3),
        ('005176.OF', '富国精准医疗灵活配置混合-A', 28.2),
    ],
    '食品饮料': [
        ('013289.OF', '工银瑞信食品饮料行业混合-A', 0.4),
        ('110022.OF', '易方达消费行业股票', 102.6),
        ('000083.OF', '汇添富消费行业混合', 63.1),
        ('519915.OF', '富国消费主题混合-A', 22.8),
        ('001044.OF', '嘉实新消费股票-A', 11.1),
    ],
    '电子': [
        ('012650.OF', '博时半导体主题混合-A', 9.1),
        ('013339.OF', '创金合信芯片产业股票-A', 1.9),
        ('016500.OF', '华夏半导体龙头混合-A', 4.7),
        ('014319.OF', '德邦半导体产业混合-A', 6.7),
        ('017746.OF', '建信电子行业股票-A', 3.8),
    ],
    '电力设备': [
        ('012445.OF', '华富新能源股票-A', 8.8),
        ('013103.OF', '博时新能源主题混合-A', 1.2),
        ('012354.OF', '南方新能源产业趋势混合-A', 4.2),
        ('013395.OF', '华夏新能源车龙头混合-A', 2.7),
        ('014141.OF', '大成新能源混合-A', 0.2),
    ],
    '国防军工': [
        ('014686.OF', '招商核心装备混合-A', 0.3),
        ('001475.OF', '易方达国防军工混合-A', 64.1),
        ('004698.OF', '博时军工主题股票-A', 14.8),
        ('005609.OF', '富国军工主题混合-A', 21.7),
    ],
    '有色金属': [
        ('021642.OF', '富国资源精选混合-A', 5.0),
        ('023036.OF', '中欧资源精选混合-A', 9.0),
        ('023834.OF', '广发资源智选股票-A', 2.5),
        ('024895.OF', '泰康资源精选股票-A', 1.0),
    ],
    '机械设备': [
        ('016847.OF', '中欧高端装备股票-A', 1.9),
        ('014606.OF', '招商高端装备混合-A', 0.7),
        ('018611.OF', '鹏华高端装备一年持有期混合-A', 0.8),
        ('020057.OF', '银河高端装备混合-A', 0.1),
    ],
    '非银金融': [
        ('012244.OF', '广发金融地产精选股票-A', 0.2),
        ('013490.OF', '同泰金融精选股票-A', 0.3),
        ('000251.OF', '工银瑞信金融地产行业混合-A', 9.2),
    ],
    '银行': [
        ('015887.OF', '国投瑞银行业睿选混合-A', 0.6),
        ('001054.OF', '工银瑞信新金融股票-A', 10.5),
        ('004871.OF', '中银金融地产混合-A', 0.4),
    ],
    '家用电器': [],   # 空档如实保留：全市场无合适主动家电基金（样表结论）
    '农林牧渔': [
        ('016725.OF', '农银汇理品质农业股票-A', 0.1),
        ('021830.OF', '国寿安保农业产业股票-A', 0.1),
        ('022521.OF', '中欧农业产业混合-A', 0.7),
        ('005106.OF', '银华农业产业股票-A', 4.4),
    ],
    '社会服务': [
        ('013132.OF', '创金合信文娱媒体股票-A', 2.0),
        ('001628.OF', '招商体育文化休闲股票-A', 1.6),
        ('001714.OF', '工银瑞信文体产业股票-A', 23.3),
    ],
}
# L1 → 东财行业板块候选名（push2 clist m:90+t:2 动态解析；无干净对应板的板块不列，直接走合成降级）
SMART_MONEY_EM_BOARD = {
    '食品饮料': ['食品饮料'], '银行': ['银行'], '有色金属': ['有色金属'],
    '家用电器': ['家电行业', '家用电器'], '农林牧渔': ['农牧饲渔', '农林牧渔'],
}


def _series_ret(series, sessions=None, ytd_base=None):
    """升序 [(date, val)] 序列的区间收益 %。sessions=向前N个交易点；ytd_base=上年末基期日。"""
    rows = [(d, v) for d, v in series if v]
    if len(rows) < 2:
        return None
    ev = rows[-1][1]
    if ytd_base:
        base = [r for r in rows if r[0] <= ytd_base]
        if not base:
            return None
        bv = base[-1][1]
    else:
        if len(rows) <= sessions:
            return None
        bv = rows[-1 - sessions][1]
    if bv <= 0:
        return None
    return round((ev / bv - 1) * 100, 2)


def fetch_sector_smart_money(pro, trade_date, data):
    """板块聪明钱超额榜：12 板块 × 45 只主动基金，超额=复权净值区间收益 − 板块基准。

    调用量：每晚 fund_nav 增量 45 次；周五加 fund_basic 分页(≤5)+fund_share×45（周更）。
    基准：东财行业板块指数日K优先（SMART_MONEY_EM_BOARD 候选名动态解析），
    封禁/无对应板降级 sector_history L1 成交额加权合成，逐板块注明 benchSrc。
    判定（YTD 超额）：中位>0 且 跑赢占比≥60% → ✅有效；中位<0 且 ≤40% → ❌无效；其余中性。
    窗口：近1月=21 交易点 / 近3月=63 / YTD=上年末基期。T+1 净值口径。
    """
    try:
        nav_cache = _load_json_cache(SMART_NAV_PATH, {})
        meta = _load_json_cache(SMART_META_PATH, {})
        all_funds = [(tc, nm, sec) for sec, fs in SMART_MONEY_FUNDS.items() for tc, nm, _ in fs]

        # ── 1. 元数据周更（周五或缓存缺失：fund_basic 分页 ≤5 次 + fund_share 逐只 45 次）──
        friday = datetime.strptime(trade_date, '%Y%m%d').weekday() == 4
        if friday or not meta.get('funds'):
            fm = meta.setdefault('funds', {})
            try:
                frames = []
                for off in range(0, 25000, 5000):
                    time.sleep(API_DELAY)
                    fb = pro.fund_basic(market='O', status='L', limit=5000, offset=off)
                    if fb is None or not len(fb):
                        break
                    frames.append(fb)
                if frames:
                    fbx = pd.concat(frames).drop_duplicates('ts_code').set_index('ts_code')
                    for tc, _, _ in all_funds:
                        if tc in fbx.index:
                            r = fbx.loc[tc]
                            fm.setdefault(tc, {})['name'] = str(r.get('name') or '')
                            mgmt = r.get('management')
                            if pd.notna(mgmt):
                                fm[tc]['mgmt'] = str(mgmt)
                    print(f'  smartMoney fund_basic: {len(fbx)} funds scanned')
            except Exception as e:
                print(f'  Warning: smartMoney fund_basic failed: {e}')
            share_start = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=40)).strftime('%Y%m%d')
            for tc, _, _ in all_funds:
                try:
                    time.sleep(API_DELAY)
                    sh = pro.fund_share(ts_code=tc, start_date=share_start, end_date=trade_date)
                    if sh is not None and len(sh):
                        last = sh.sort_values('trade_date').iloc[-1]
                        fm.setdefault(tc, {})['share'] = round(float(last['fd_share']) / 1e4, 2)  # 万份→亿份
                        fm[tc]['shareDate'] = str(last['trade_date'])
                except Exception as e:
                    print(f'  Warning: smartMoney fund_share {tc} failed: {str(e)[:50]}')
            meta['updated'] = trade_date
            _save_json_cache(SMART_META_PATH, meta)
            print(f'  smartMoney meta refreshed (Friday): {len(meta.get("funds") or {})} funds')

        # ── 2. 净值增量（每晚 45 次 fund_nav；首次全量回补自 20251201）──
        fetched = 0
        for tc, _, _ in all_funds:
            rows = nav_cache.get(tc) or []
            start = SMART_MONEY_NAV_BACKFILL if not rows else \
                (datetime.strptime(rows[-1][0], '%Y%m%d') + timedelta(days=1)).strftime('%Y%m%d')
            if start > trade_date:
                continue
            try:
                time.sleep(API_DELAY)
                df = pro.fund_nav(ts_code=tc, start_date=start, end_date=trade_date)
                if df is None or not len(df):
                    continue
                fetched += 1
                for _, r in df.iterrows():
                    if pd.notna(r.get('adj_nav')):
                        rows.append([str(r['nav_date']), round(float(r['adj_nav']), 4)])
                dd = {r[0]: r[1] for r in rows}
                nav_cache[tc] = [list(x) for x in sorted(dd.items())[-220:]]
            except Exception as e:
                print(f'  Warning: smartMoney nav {tc} failed: {str(e)[:50]}')
        _save_json_cache(SMART_NAV_PATH, nav_cache)
        print(f'  smartMoney nav updated: {fetched} funds fetched, cache {len(nav_cache)}')

        # ── 3. 板块基准（东财优先，降级 L1 成交额加权合成）──
        hist = _load_sector_history()
        l1s = _l1_series(hist)
        boards, board_broken = None, False
        bench = {}
        for l1 in SMART_MONEY_FUNDS:
            series, src = None, None
            if not board_broken:
                for cand in SMART_MONEY_EM_BOARD.get(l1, []):
                    try:
                        if boards is None:
                            boards = _em_board_list()
                        bk = boards.get(cand)
                        if not bk:
                            continue
                        pct = _em_kline_pct(f'90.{bk}')
                        if pct:
                            level, out = 1.0, []
                            for d in sorted(pct):
                                level *= 1 + pct[d] / 100.0
                                out.append((d, level))
                            series, src = out, f'东财板块指数·{cand}'
                            break
                    except Exception:
                        board_broken = True   # IP 封禁/网络问题：本晚全部降级合成
                        break
            if series is None:
                level, out = 1.0, []
                for d, _, ret, _a in (l1s.get(l1) or []):
                    level *= 1 + ret / 100.0
                    out.append((d, level))
                series, src = out, '等权合成·sector_history'
            bench[l1] = {'series': series, 'src': src}

        # ── 4. 收益 / 超额 / 板块级判定 ──
        ytd_base = f'{int(trade_date[:4]) - 1}1231'
        meta_funds = meta.get('funds') or {}
        sectors_out, latest_nav = [], '00000000'
        for l1, funds in SMART_MONEY_FUNDS.items():
            bs, bsrc = bench[l1]['series'], bench[l1]['src']
            b1, b3, bytd = _series_ret(bs, 21), _series_ret(bs, 63), _series_ret(bs, ytd_base=ytd_base)
            fund_rows = []
            for tc, nm, scale0 in funds:
                rows = nav_cache.get(tc) or []
                if rows:
                    latest_nav = max(latest_nav, rows[-1][0])
                r1, r3, rytd = _series_ret(rows, 21), _series_ret(rows, 63), _series_ret(rows, ytd_base=ytd_base)
                mfr = meta_funds.get(tc) or {}
                share = mfr.get('share')
                fund_rows.append({
                    'ts_code': tc, 'name': mfr.get('name') or nm,
                    'scale': round(share * rows[-1][1], 1) if share and rows else scale0,
                    'navDate': rows[-1][0] if rows else None,
                    'r1m': r1, 'r3m': r3, 'rytd': rytd,
                    'ex1m': round(r1 - b1, 2) if r1 is not None and b1 is not None else None,
                    'ex3m': round(r3 - b3, 2) if r3 is not None and b3 is not None else None,
                    'exytd': round(rytd - bytd, 2) if rytd is not None and bytd is not None else None,
                })
            exs = [f['exytd'] for f in fund_rows if f['exytd'] is not None]
            if not fund_rows:
                verdict, med, win_pct = '无样本', None, None
            elif not exs:
                verdict, med, win_pct = '数据积累中', None, None
            else:
                med = round(statistics.median(exs), 2)
                win_pct = round(sum(1 for v in exs if v > 0) / len(exs) * 100)
                verdict = ('✅有效' if med > 0 and win_pct >= 60
                           else '❌无效' if med < 0 and win_pct <= 40 else '中性')
            ex1s = [f['ex1m'] for f in fund_rows if f['ex1m'] is not None]
            ex3s = [f['ex3m'] for f in fund_rows if f['ex3m'] is not None]
            sectors_out.append({
                'sector': l1, 'nFunds': len(fund_rows), 'benchSrc': bsrc,
                'ex1mMed': round(statistics.median(ex1s), 2) if ex1s else None,
                'ex3mMed': round(statistics.median(ex3s), 2) if ex3s else None,
                'exytdMed': med, 'winYtdPct': win_pct, 'verdict': verdict,
                'funds': fund_rows,
            })
        data['sectorSmartMoney'] = {
            'trade_date': f'{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}',
            'nav_date': f'{latest_nav[:4]}-{latest_nav[4:6]}-{latest_nav[6:]}' if latest_nav > '00000000' else None,
            'ytdBase': ytd_base,
            'sectors': sectors_out,
            'note': ('聪明钱超额榜（2026-09-27 样表产品化）：45 只主动基金 × 12 板块（名单为策展样本，'
                     '家电无合适标的空档保留）；超额=复权净值区间收益−板块基准'
                     '（近1月=21交易点/近3月=63/YTD=上年末基期），T+1 净值口径（判定滞后一天）；'
                     '判定：YTD超额中位>0 且 跑赢占比≥60% → ✅有效；中位<0 且 ≤40% → ❌无效；其余中性；'
                     '基准东财板块指数优先、封禁降级等权合成，逐板块见 benchSrc。'),
        }
        print('  smartMoney: ' + '；'.join(
            f"{s['sector']}{s['verdict']}(YTD中位{s['exytdMed']}%/赢{s['winYtdPct']}%·{s['benchSrc'][:4]})"
            for s in sectors_out if s['nFunds'] > 0))
    except Exception as e:
        print(f"  Warning: fetch_sector_smart_money failed (keep old): {e}")


# ── 板块每日涨幅轮动榜（2026-09-29 用户正式指令）──
# 阈值口径（2026-09-29 用户批准下调，可调）：近10日上榜≥4次 或 当前连续上榜≥3天 = 🔥过热（惩罚）；
# 上榜3次/10日 = 🟠中段（中性）；其余（首次/隔日上榜）= 🟢启动。
ROTATION_DAYS = 15            # 轮动榜网格列数（近15个交易日）
ROTATION_TOPN = 10            # 每日涨幅前10
ROTATION_STAT_WINDOW = 10     # 上榜次数统计窗口
ROTATION_OVERHEAT_HITS = 4    # ≥4次/10日 = 过热（2026-09-29 用户批准自 5 下调，房产服务类高频上榜纳入惩罚）
ROTATION_OVERHEAT_STREAK = 3  # 连续≥3天 = 过热
ROTATION_MID_HITS = 3         # 3次/10日 = 中段

# 东财行业板块涨幅榜快照缓存（第二口径，2026-09-29 用户批准双轨）：
# 东财只有当日快照无历史回补——每晚积累一列，随 workflow 提交回写延续。
EM_BOARD_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', 'em_board_snapshot.json')
_EM_BOARD_HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'}


def update_em_board_snapshot(trade_date):
    """东财行业板块当日涨幅榜快照（push2 clist，m:90+t:2 行业板块，按涨跌幅降序前30）入缓存。

    本地 IP 封禁是已知问题：失败返回 None 优雅跳过（不影响主流程），Actions 可通就走 Actions 积累。
    首日只有 1 列，如实展示。
    """
    try:
        r = requests.get('https://push2.eastmoney.com/api/qt/clist/get', params={
            'pn': 1, 'pz': 30, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2,
            'fid': 'f3', 'fs': 'm:90 t:2', 'fields': 'f12,f14,f3',
        }, headers=_EM_BOARD_HEADERS, timeout=15)
        diff = ((r.json().get('data') or {}).get('diff')) or []
        rows = [{'code': x.get('f12'), 'name': x.get('f14'),
                 'ret': round(float(x['f3']), 2)} for x in diff
                if x.get('f14') and x.get('f3') not in (None, '-')]
        if not rows:
            print('  Warning: EM board snapshot empty (skip)')
            return None
        cache = _load_json_cache(EM_BOARD_CACHE_PATH, {})
        days = cache.setdefault('days', {})
        days[trade_date] = rows
        for d in sorted(days)[:-40]:   # 滚动保留最近 40 个快照日
            del days[d]
        with open(EM_BOARD_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
        print(f'  emBoard: {trade_date} 快照 {len(rows)} 板块入缓存（榜首 {rows[0]["name"]} {rows[0]["ret"]:+.2f}%），累计 {len(days)} 天')
        return len(rows)
    except Exception as e:
        print(f'  Warning: EM board snapshot failed (skip, 东财IP封禁则待Actions积累): {str(e)[:60]}')
        return None


def build_sector_rotation(data):
    """每日涨幅轮动榜：近15交易日×每日涨幅前10 网格 + 轮动热度判定（过热因子供漏斗第2步降权）。

    数据全部来自 sector_history 沉淀（110 个 L2 板块等权日收益），零新增 API 调用。
    过热口径：轮动上涨已久的板块后面容易滞涨回落，要惩罚（用户原话）——
    近10日上榜≥4次（2026-09-29 用户批准自5下调）或 当前连续上榜≥3天 判 🔥过热；
    积聚期板块通常不在涨幅榜上，天然规避过热。
    东财双轨（2026-09-29 用户批准）：em 子块给东财行业板块口径网格（当日快照积累，无历史回补）；
    过热因子仅按 Tushare 口径计算（缓存深、口径稳），东财口径只做展示对照。
    """
    try:
        hist = _load_sector_history()
        days_map = (hist or {}).get('days') or {}
        all_days = sorted(days_map)
        if len(all_days) < ROTATION_DAYS:
            print('  rotation: 历史不足15日，跳过')
            return
        last15 = all_days[-ROTATION_DAYS:]
        topsets = {}   # date -> [(sector, ret)] 涨幅前10
        grid = []
        for d in last15:
            secs = (days_map[d].get('sectors') or {})
            ranked = sorted(((n, v.get('ret')) for n, v in secs.items() if v.get('ret') is not None),
                            key=lambda x: -x[1])[:ROTATION_TOPN]
            topsets[d] = ranked
            grid.append({'date': f'{d[4:6]}-{d[6:]}',
                         'rows': [{'rank': i + 1, 'sector': n, 'ret': round(r, 2)}
                                  for i, (n, r) in enumerate(ranked)]})
        last10 = set(last15[-ROTATION_STAT_WINDOW:])
        hit_days = {}
        for d in last15:
            for n, _r in topsets[d]:
                hit_days.setdefault(n, []).append(d)

        def _on_board(d, name):
            return any(nn == name for nn, _ in topsets[d])

        stats = []
        for n, ds in hit_days.items():
            hits10 = sum(1 for d in ds if d in last10)
            streak = 0
            for d in reversed(last15):
                if _on_board(d, n):
                    streak += 1
                else:
                    break
            since = 0
            for d in reversed(last15):
                if _on_board(d, n):
                    break
                since += 1
            rows = _history_series(hist, n)
            cum10 = None
            if len(rows) >= 10:
                lvl = 1.0
                for r in [x[2] for x in rows[-10:]]:
                    lvl *= (1 + r / 100.0)
                cum10 = round((lvl - 1) * 100, 2)
            overheat = hits10 >= ROTATION_OVERHEAT_HITS or streak >= ROTATION_OVERHEAT_STREAK
            phase = '过热' if overheat else ('中段' if hits10 >= ROTATION_MID_HITS else '启动')
            stats.append({'sector': n, 'hits10': hits10, 'streak': streak, 'sinceLast': since,
                          'cum10': cum10, 'phase': phase, 'overheat': overheat,
                          'label': ('🔥轮动过热·追高风险' if overheat
                                    else '🟠中段' if phase == '中段' else '🟢启动')})
        stats.sort(key=lambda s: (-s['hits10'], -s['streak'], s['sector']))
        # 轮动解读：当前连续霸榜板块 + 过热警示
        hot = [s for s in stats if s['streak'] >= 2]
        hot.sort(key=lambda s: (-s['streak'], -s['hits10']))
        ovh = [s for s in stats if s['overheat']]
        parts = []
        if hot:
            parts.append('当前连续上榜：' + '、'.join(f"{s['sector']}（连{s['streak']}天）" for s in hot[:4]))
        if ovh:
            parts.append('🔥过热警示：' + '、'.join(f"{s['sector']}（10日上榜{s['hits10']}次/连{s['streak']}天）"
                                                  for s in ovh[:6]) + '——轮动上涨已久，谨防滞涨回落')
        summary = '；'.join(parts) if parts else '近15日无连续上榜板块，轮动分散'
        latest_d = last15[-1]
        # ── 东财第二口径网格（当日快照积累，无历史回补；首日可能只有 1-2 列，如实展示）──
        em_cache = _load_json_cache(EM_BOARD_CACHE_PATH, {})
        em_days_map = (em_cache or {}).get('days') or {}
        em_keys = sorted(em_days_map)[-ROTATION_DAYS:]
        if em_keys:
            em_grid = [{'date': f'{d[4:6]}-{d[6:]}',
                        'rows': [{'rank': i + 1, 'sector': x['name'], 'ret': x['ret']}
                                 for i, x in enumerate(em_days_map[d][:ROTATION_TOPN])]}
                       for d in em_keys]
            em_block = {'available': True, 'snapshotDays': len(em_days_map),
                        'days': [g['date'] for g in em_grid], 'grid': em_grid,
                        'note': ('东财行业板块口径（push2 当日快照前10，约496个行业板块）；'
                                 '东财无历史回补，自 2026-09-29 起每晚积累一列，列数随天数增长；'
                                 '与 Tushare L2 等权口径成分/加权不同，仅作对照，过热判定仍以 Tushare 口径为准。')}
        else:
            em_block = {'available': False, 'snapshotDays': 0, 'days': [], 'grid': [],
                        'note': ('东财口径待补：东财行业板块榜只有当日快照、无历史回补，'
                                 '自 2026-09-29 起每晚积累（本地 IP 封禁时由 Actions  runner 抓取）；当前快照 0 天。')}
        data['sectorRotation'] = {
            'trade_date': f'{latest_d[:4]}-{latest_d[4:6]}-{latest_d[6:]}',
            'days': [g['date'] for g in grid],
            'grid': grid,
            'stats': stats,
            'summary': summary,
            'em': em_block,
            'note': ('每日涨幅轮动榜（2026-09-29 用户指令）：sector_history 沉淀等权日收益，近15交易日×每日涨幅前10；'
                     f'热度口径（2026-09-29 用户批准下调，可调）：近10日上榜≥{ROTATION_OVERHEAT_HITS}次 或 连续≥{ROTATION_OVERHEAT_STREAK}天=🔥过热、'
                     f'{ROTATION_MID_HITS}次=🟠中段、其余=🟢启动；过热板块在漏斗第2步一票降权（排序沉底+警示，不否决）。'),
        }
        print(f"  rotation: 15日网格 ✓ 上榜板块{len(stats)}个，过热{len(ovh)}个"
              + (('（' + '、'.join(s['sector'] for s in ovh[:5]) + '）') if ovh else ''))
    except Exception as e:
        print(f"  Warning: build_sector_rotation failed (keep old): {e}")


# ── 第三步入选历史 + 自动收录观察股（2026-09-30 用户正式指令）──
# "如果个股曾经入选第三步相对长一段时间，记录出来作为备选观察形态。入选超过5个交易日就放入我的观察股，后续都这样处理。"
# 每日记录第3步（共振轨+优中选优轨）入选名单入 step3_history.json（随 workflow 提交回写延续）；
# 累计入选≥STEP3_AUTO_WATCH_DAYS 个交易日的个股自动并入 STOCKS（cache 驱动、group=watch、打 auto 标记）；
# 一旦收录常驻（用户自行决定剔除），掉出第三步后前端灰态提示。09-30 一次性回填自 git 历史（第三步 09-27 才有）。
STEP3_HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', 'step3_history.json')
STEP3_AUTO_WATCH_DAYS = 5     # 累计入选≥5个交易日 → 自动收录观察股（可调）
STEP3_HISTORY_KEEP = 120      # 日名单滚动保留天数


def _step3_day_counts(hist):
    """step3_history days 映射 → {code: 累计入选交易日数}。"""
    cnt = {}
    for _d, codes in (hist.get('days') or {}).items():
        for c in codes:
            cnt[c] = cnt.get(c, 0) + 1
    return cnt


def apply_step3_auto_watch():
    """累计入选≥5日的个股自动并入 STOCKS 观察股（动态 cache 驱动，STOCKS dict 单点配置不变）。

    在 main 取数前调用，使新收录股当晚即获得行情/公告/排雷/RS 等全部下游处理。
    已在 STOCKS 的（用户手动持仓/观察）不改 group、不打标。返回新收录名单。"""
    hist = _load_json_cache(STEP3_HISTORY_PATH, {})
    cnt = _step3_day_counts(hist)
    meta = hist.get('stocks') or {}
    added = []
    for c, n in cnt.items():
        if n >= STEP3_AUTO_WATCH_DAYS and c not in STOCKS:
            m = meta.get(c) or {}
            first = str(m.get('first') or '')
            STOCKS[c] = {'name': m.get('name') or c, 'industry': m.get('sector') or '',
                         'group': 'watch', 'watchPrice': 0,
                         'auto': {'source': 'step3', 'days': n,
                                  'since': f'{first[4:6]}-{first[6:]}' if len(first) == 8 else first}}
            added.append((c, STOCKS[c]['name'], n))
    if added:
        print('  step3AutoWatch 新收录: ' + '、'.join(f'{n}({c}·{d}日)' for c, n, d in added))
    return added


def update_step3_history(data):
    """每日记录第3步入选名单（以 funnel 数据日期为键），并回写累计天数到第3步行（前端展示用）。"""
    try:
        funnel = data.get('funnel') or {}
        steps = funnel.get('steps') or []
        s3 = next((s for s in steps if s.get('key') == 'vcp'), None)
        if s3 is None:
            return
        td = str(funnel.get('trade_date') or '').replace('-', '')
        rows = s3.get('rows') or []
        hist = _load_json_cache(STEP3_HISTORY_PATH, {})
        days = hist.setdefault('days', {})
        meta = hist.setdefault('stocks', {})
        if td and rows:
            days[td] = sorted({r['code'] for r in rows if r.get('code')})
        for dd in sorted(days)[:-STEP3_HISTORY_KEEP]:
            del days[dd]
        # 元数据与累计统计
        for r in rows:
            c = r.get('code')
            if not c:
                continue
            m = meta.setdefault(c, {'name': r.get('name'), 'sector': r.get('sector')})
            m['name'] = m.get('name') or r.get('name')
            m['sector'] = m.get('sector') or r.get('sector')
        cnt = _step3_day_counts(hist)
        for c, m in meta.items():
            m['days'] = cnt.get(c, 0)
            hits = [d for d, codes in days.items() if c in codes]
            if hits:
                m['first'], m['last'] = hits[0], hits[-1]
        hist['note'] = ('第三步入选历史（2026-09-30 用户指令）：每日记录共振轨+优中选优轨入选名单；'
                        f'累计≥{STEP3_AUTO_WATCH_DAYS}交易日自动收录观察股（常驻，掉出仅灰态提示）；'
                        '09-30 一次性回填自 git 历史（第三步 2026-09-27 大改版才有，此前无记录）。')
        _save_json_cache(STEP3_HISTORY_PATH, hist)
        # 回写 rows：累计入选天数（selDays）+ 是否已达收录线
        for r in rows:
            n = cnt.get(r.get('code'), 0)
            r['selDays'] = n
            r['selQualified'] = n >= STEP3_AUTO_WATCH_DAYS
        if td and rows:
            print(f"  step3History: {td} 记录 {len(days[td])} 只（"
                  + '、'.join(f"{r['name']}{cnt.get(r['code'], 0)}日" for r in rows) + '）')
    except Exception as e:
        print(f"  Warning: update_step3_history failed (keep old): {e}")


def build_funnel(data):
    """总览五步漏斗结论汇总（2026-09-27 用户正式指令：0窗口→1宽基→2板块→3个股→4排雷）。

    纯汇总层：只读既有块（longWindow/broadTrend/broadVcp/bottomWatch/sectorScan/
    sectorFlows/vcpStocks/mineWatch/dualAxes/actionableSectors）+ 本地缓存
    （宽基指数日线、sector_history），零新增 API 调用。
    板块生命周期（2026-09-27 用户拍板规则）：
      积聚期=bottomWatch 命中；启动期=sectorScan 启动确认；高潮期=scan 高潮/双头风险；
      退潮期=近5日净流出 且 一年价格分位≥70%；主升期=近20日涨>10% 且 近5日净流入；
      其余=半路。优先级：积聚>启动>高潮>退潮>主升>半路。
    第2步入选=（积聚期∪启动期）且 板块形态达标（VCP/底部/杯柄任一+缩量极致，2026-09-27 升级）。
    """
    hist = _load_sector_history()
    flows = {i['name']: i for i in (data.get('sectorFlows') or {}).get('items') or []}
    bw_map = {i['sector']: i for i in (data.get('bottomWatch') or {}).get('items') or []}
    scan_map = {i['sector']: i for i in (data.get('sectorScan') or {}).get('items') or []}
    mine_codes = {m['code'] for m in (data.get('mineWatch') or {}).get('items') or []}

    def _sector_stats(name):
        """sector_history 逐日序列 → (ret20%, 一年价格分位%)（复利近似）。"""
        rows = _history_series(hist, name)
        if len(rows) < 30:
            return None, None
        rets = [r[2] for r in rows]
        level, levels = 1.0, []
        for r in rets[-250:]:
            level *= (1 + r / 100.0)
            levels.append(level)
        ret20 = round((levels[-1] / levels[-21] - 1) * 100, 1) if len(levels) >= 21 else None
        pct1y = _pct_rank100(levels, levels[-1])
        return ret20, pct1y

    def _lifecycle(name):
        if name in bw_map:
            return '积聚期'
        st = (scan_map.get(name) or {}).get('status') or ''
        if '启动' in st:
            return '启动期'
        if '高潮' in st or '双头' in st:
            return '高潮期'
        fl = flows.get(name) or {}
        ret20, pct1y = _sector_stats(name)
        if (fl.get('net5') or 0) < 0 and pct1y is not None and pct1y >= 70:
            return '退潮期'
        if ret20 is not None and ret20 > 10 and (fl.get('net5') or 0) > 0:
            return '主升期'
        return '半路'

    # ── 第0步 做多窗口 ──
    lw = data.get('longWindow') or {}
    w = lw.get('window') or 'half'
    lamp0 = {'open': '🟢', 'half': '🟡', 'closed': '🔴'}[w]
    concl0 = {'open': '窗口打开：水温偏暖+宽基临近买点，可以做多',
              'half': '半窗：只看不动，仓位与信号降档',
              'closed': '窗口关闭：今天到此为止'}[w]
    guide0 = ('本步回答：今天能不能做多？' + concl0 +
              ('。下级全部标灰"窗口未开"，无需往下翻' if w == 'closed'
               else '。可以继续看第1步，但只观察不动手' if w == 'half'
               else '。继续第1步定风格'))

    # ── 第1步 宽基定风格（四态标签 + ETF 买点）──
    idx_cache = _load_json_cache(BROAD_IDX_CACHE_PATH, {})
    bt_map = {i['indexCode']: i for i in (data.get('broadTrend') or {}).get('items') or []}
    bv_map = {i['indexCode']: i for i in (data.get('broadVcp') or {}).get('items') or []}
    step1_rows = []
    focus = []
    for ic, iname, ec, ename in BROAD_ETF_MAP:
        if ic in ('000001.SH', '399001.SZ'):
            continue  # 上证/深证综指仅展示于趋势层，不进风格判定（用户口径：50/300/500/1000/A500/创业板/科创50）
        rows = idx_cache.get(ic) or []
        closes = [r[1] for r in rows]
        label4, pct1y, ma_align = '无数据', None, ''
        if len(closes) >= 200:
            close = closes[-1]
            pct1y = _pct_rank100(closes[-250:], close)
            ma50 = sum(closes[-50:]) / 50
            ma150 = sum(closes[-150:]) / 150
            ma200 = sum(closes[-200:]) / 200
            bull = ma50 > ma150 > ma200
            bt = bt_map.get(ic) or {}
            low_vol = (bt.get('hvPct1y') is not None and bt['hvPct1y'] <= 20)
            if pct1y is not None and pct1y <= 30:
                label4 = '阶段底部'
            elif bull:
                label4 = '多头排列'
            elif low_vol:
                label4 = '窄幅波动'
            elif pct1y is not None and pct1y >= 80:
                label4 = '高位'
            else:
                label4 = '半路'
            ma_align = f"50/150/200={'多头' if bull else '非多头'}"
        bv = bv_map.get(ic) or {}
        row = {'indexCode': ic, 'indexName': iname, 'etfCode': ec, 'etfName': ename,
               'etfClose': bv.get('etfClose'), 'label4': label4, 'pct1y': pct1y,
               'maAlign': ma_align, 'state': bv.get('state') or '无数据',
               'pivot': bv.get('pivot'), 'distPct': bv.get('distPct'),
               'invalidation': bv.get('invalidation'),
               'volConfirm': bv.get('volConfirm')}
        step1_rows.append(row)
        if row['state'] in ('临近枢轴', '突破确认', '突破待确认'):
            focus.append(f"{iname}（{row['state']}，盯 {ec.split('.')[0]} 突破 {row['pivot']}）")
        elif row['state'] in ('构筑基底', '低波蓄势') and row['distPct'] is not None and row['distPct'] <= 8:
            focus.append(f"{iname}（{row['state']}，距枢轴{row['distPct']}%）")
        elif label4 == '阶段底部':
            focus.append(f"{iname}（一年分位{pct1y}%，阶段底部）")
    lamp1 = ('🟢' if any(r['state'] in ('临近枢轴', '突破确认') for r in step1_rows)
             else '🔴' if step1_rows and all(r['label4'] == '高位' for r in step1_rows) else '🟡')
    concl1 = ('当前可关注：' + '；'.join(focus[:3])) if focus else '七只宽基均无可关注形态，空仓等待'
    guide1 = '本步回答：买哪类宽基/什么风格？' + concl1 + '。选好风格后进第2步圈板块'

    # ── 第2步 圈板块（生命周期分级 + 板块形态双达标，2026-09-27 用户正式指令升级）──
    # 入选 = 资金持续流入（积聚期∪启动期，现有口径）且 板块自身形态达标
    #       （VCP收缩/底部/杯柄 任一命中 + 量能萎缩极致10/60≤0.7）。两条都要。
    all_sectors = sorted(set(list(flows.keys()) + list(bw_map.keys()) + list(scan_map.keys())))
    lc_map = {n: _lifecycle(n) for n in all_sectors}
    sp_map = {}
    for n in all_sectors:
        sp = _sector_pattern(hist, n)
        if sp:
            sp_map[n] = sp
    # ── 聪明钱超额并入第2步（2026-09-27 用户批准）：L1 判定 → L2 解析（代理注明）──
    sm_l1 = {s['sector']: s for s in (data.get('sectorSmartMoney') or {}).get('sectors') or []}
    smart_l2 = {}
    for _l2, _l1 in SECTOR_TO_L1.items():
        _s = sm_l1.get(_l1)
        if _s and _s.get('verdict') not in (None, '无样本', '数据积累中'):
            smart_l2[_l2] = {'verdict': _s['verdict'], 'exytdMed': _s.get('exytdMed'), 'l1': _l1}
    # ── 轮动过热因子并入第2步（2026-09-29 用户正式指令）：🔥过热一票降权（排序沉底+警示，不否决）──
    rot_map = {s['sector']: s for s in (data.get('sectorRotation') or {}).get('stats') or []}
    step2_rows = []
    dropped2 = []   # 积聚/启动但形态未达标（如实展示哪条卡掉）
    for n in all_sectors:
        lc = lc_map[n]
        if lc not in ('积聚期', '启动期'):
            continue
        sp = sp_map.get(n)
        if not (sp and sp['qualified']):
            why = ('历史不足80日' if sp is None
                   else '板块形态未命中（VCP/底部/杯柄均无）' if not sp['patterns']
                   else f"量能萎缩未达极致（10/60={sp['volRatio']}>0.7）")
            dropped2.append({'sector': n, 'lifecycle': lc, 'why': why,
                             'pattern': (sp or {}).get('pattern'),
                             'volRatio': (sp or {}).get('volRatio')})
            continue
        bw, sc = bw_map.get(n), scan_map.get(n)
        leaders = []
        if bw and bw.get('leaders'):
            leaders = [{'name': l['name'], 'code': l.get('code'), 'pctChg': l.get('pctChg'),
                        'mine': bool(l.get('code') and l['code'] in mine_codes)} for l in bw['leaders'][:2]]
        elif sc and sc.get('stocks'):
            leaders = [{'name': s['name'], 'code': s.get('code'), 'pctChg': s.get('pctChg'),
                        'mine': bool(s.get('code') and s['code'] in mine_codes)}
                       for s in sorted(sc['stocks'], key=lambda x: -(x.get('netInflow') or 0))[:2]]
        reason = ''
        if bw:
            reason = (f"底部积聚：30日流入{bw.get('inflow30d')}亿/60日{bw.get('inflow60d')}亿，"
                      f"价格低位（分位{round((bw.get('pricePosition') or 0) * 100)}%）")
        elif sc:
            reason = f"{sc.get('status')}：连续净流入{sc.get('consecutiveDays')}天，近5日{sc.get('netInflow5d')}亿"
        step2_rows.append({'sector': n, 'lifecycle': lc, 'reason': reason, 'leaders': leaders,
                           'dual': bool(bw and bw.get('both')),
                           'pattern': sp['pattern'], 'volRatio': sp['volRatio'],
                           'patternEvidence': sp['evidence'],
                           'rotation': ({'phase': rot_map[n]['phase'], 'hits10': rot_map[n]['hits10'],
                                         'streak': rot_map[n]['streak'], 'overheat': rot_map[n]['overheat'],
                                         'label': rot_map[n]['label']} if n in rot_map else None),
                           'smart': dict(smart_l2[n], proxy=(n != smart_l2[n]['l1'])) if n in smart_l2 else None})
    # 轮动过热一票降权：排序沉底（其余保持原名序），不否决（2026-09-29 用户口径）
    step2_rows.sort(key=lambda r: (1 if (r.get('rotation') or {}).get('overheat') else 0, r['sector']))
    collapsed = {}
    for n, lc in lc_map.items():
        if lc not in ('积聚期', '启动期'):
            collapsed[lc] = collapsed.get(lc, 0) + 1
    # 生命周期全量映射（2026-09-27 工具/板块栏目联动用）：L2 全量 + 归并 L1（取成员最高优先级）
    _lc_prio = ['积聚期', '启动期', '主升期', '高潮期', '退潮期', '半路']
    lc_l1 = {}
    for _l2, _lc in lc_map.items():
        _l1 = SECTOR_TO_L1.get(_l2)
        if not _l1:
            continue
        if _l1 not in lc_l1 or _lc_prio.index(_lc) < _lc_prio.index(lc_l1[_l1]):
            lc_l1[_l1] = _lc
    lamp2 = '🟢' if step2_rows else ('🟡' if collapsed.get('主升期') or dropped2 else '🔴')
    sm_bad = [r['sector'] for r in step2_rows if (r.get('smart') or {}).get('verdict') == '❌无效']
    concl2 = (f"入选{len(step2_rows)}个：" + '、'.join(f"{r['sector']}（{r['lifecycle']}·{r['pattern']}）" for r in step2_rows)) \
        if step2_rows else (
            f"今日无入选：{len(dropped2)}个资金流入板块被形态条件卡掉（"
            + '、'.join(f"{d['sector']}·{d['why']}" for d in dropped2[:3])
            + ('…' if len(dropped2) > 3 else '') + '）' if dropped2 else '今日无入选（无积聚期/启动期板块）')
    if sm_bad:
        concl2 += '；⚠主动资金未验证：' + '、'.join(sm_bad)
    rot_hot2 = [r['sector'] for r in step2_rows if (r.get('rotation') or {}).get('overheat')]
    if rot_hot2:
        concl2 += ('；🔥轮动过热（已沉底降权，追高风险）：'
                   + '、'.join(f"{r['sector']}（10日上榜{r['rotation']['hits10']}次/连{r['rotation']['streak']}天）"
                               for r in step2_rows if (r.get('rotation') or {}).get('overheat')))
    guide2 = '本步回答：主线板块是哪几个？' + concl2 + '。' + ('带着板块去第3步看个股形态（共振轨优先）' if step2_rows else '第3步共振轨为空，只能看⭐优中选优轨')

    # ── 第3步 个股形态（双轨制，2026-09-27 用户正式指令；两轨都不沾不进榜）──
    # 🔗共振轨（置顶）：个股属于第2步入选板块（形态+资金双达标）；
    # ⭐优中选优轨：板块不同步但 ①个股在池内（上证50∪中证500∪沪深300∪科创50∪创业板50∪中证1000）
    #   ②形态达标（Minervini 口径 VCP收缩型/杯柄型，Stage 2 过趋势模板；底部整理不算达标）
    #   ③聪明钱持续流入（自定口径：近10个缓存交易日主力净流入为正天数≥6，
    #     数据=MINE_MF 全市场 moneyflow 10日滚动缓存，零新增调用）。三条缺一不入。
    sel_sectors = {r['sector'] for r in step2_rows}
    mf_cache = _load_json_cache(MINE_MF_CACHE_PATH, {})
    mf_days = sorted(mf_cache)[-10:]

    def _smart_money_days(code):
        return sum(1 for d in mf_days if (mf_cache[d].get(code) or 0) > 0)

    step3_rows = []
    step3_excluded = 0
    for it in (data.get('vcpStocks') or {}).get('items') or []:
        bp = it.get('buyPoint') or {}
        reson = bool(it.get('sector') and it['sector'] in sel_sectors)
        sm_days = _smart_money_days(it['code'])
        cherry = (bool(it.get('inPool'))
                  and it.get('pattern') in ('VCP收缩型', '杯柄型')
                  and sm_days >= 6)
        if reson:
            track = 'reson'
        elif cherry:
            track = 'cherry'
        else:
            step3_excluded += 1
            continue
        step3_rows.append({'code': it['code'], 'name': it['name'], 'pattern': it.get('pattern'),
                           'stage': it.get('stage'), 'sector': it.get('sector'),
                           'pivot': bp.get('pivot'), 'distPct': bp.get('distanceToPivotPct') if bp.get('distanceToPivotPct') is not None else it.get('distMain'),
                           'invalidation': bp.get('invalidation'),
                           'track': track, 'smartMoneyPosDays': sm_days,
                           'inPool': bool(it.get('inPool')),
                           'reson': reson,
                           'mine': it['code'] in mine_codes, 'star': bool(it.get('star'))})
    step3_rows.sort(key=lambda r: (0 if r['track'] == 'reson' else 1,
                                   r['distPct'] if r['distPct'] is not None else 99))
    n_reson = sum(1 for r in step3_rows if r['track'] == 'reson')
    n_cherry = len(step3_rows) - n_reson
    lamp3 = ('🟢' if any(r['distPct'] is not None and r['distPct'] <= 3 for r in step3_rows)
             else '🟡' if step3_rows else '🔴')
    concl3 = (f"🔗共振{n_reson}只 + ⭐精选{n_cherry}只：" + '、'.join(
              f"{'🔗' if r['track'] == 'reson' else '⭐'}{r['name']}（{r['pattern']}·距枢轴{r['distPct']}%）"
              for r in step3_rows[:4]) + ('…' if len(step3_rows) > 4 else '')) \
        if step3_rows else '今日双轨皆空（无共振也无精选）'
    guide3 = '本步回答：具体买哪只、什么价？' + concl3 + '。' + ('🔗=第2步入选板块共振（赢面优先）；⭐=池内形态达标+聪明钱流入的优中选优；最后过第4步排雷' if step3_rows else '可翻第4步确认持仓无雷')

    # ── 第4步 排雷（范围=第2步龙头∪第3步入围∪持仓观察股）──
    scope = {l['code'] for r in step2_rows for l in r['leaders'] if l.get('code')} \
        | {r['code'] for r in step3_rows} | set(STOCKS.keys())
    mw_items = [m for m in (data.get('mineWatch') or {}).get('items') or [] if m.get('code') in scope]
    lamp4 = '🔴' if mw_items else '🟢'
    concl4 = (f"⛔{len(mw_items)}只有雷：" + '、'.join(m['name'] for m in mw_items[:5])
              + ('…' if len(mw_items) > 5 else '')) if mw_items else '✅ 入围标的今日无雷'
    guide4 = '本步回答：入围的有没有雷？' + concl4 + ('。有雷标的一票否决，不碰' if mw_items else '。可以放心按前面步骤执行')

    # ── 当日路径总结 ──
    w_txt = {'open': '窗口开', 'half': '窗口半开', 'closed': '窗口关'}[w]
    broad_txt = '、'.join(f"{r['indexName']}{r['state']}" for r in step1_rows[:3] if r['state'] != '无数据') or '无形态'
    path = (f"{w_txt} → 宽基：{broad_txt} → 板块：{len(step2_rows)}个入选 → "
            f"个股：{len(step3_rows)}只成型 → 排雷：{len(mw_items)}只")

    data['funnel'] = {
        'trade_date': (data.get('sectorFlows') or {}).get('trade_date') or '',
        'path': path, 'window': w,
        'lifecycleAll': lc_map, 'lifecycleL1': lc_l1,
        'sectorPattern': sp_map,
        'smartMoney': {'byL2': smart_l2,
                       'byL1': {k: {'verdict': v['verdict'], 'exytdMed': v.get('exytdMed'),
                                    'winYtdPct': v.get('winYtdPct'), 'benchSrc': v.get('benchSrc')}
                                for k, v in sm_l1.items()}},
        'steps': [
            {'n': 0, 'key': 'window', 'title': '做多窗口', 'lamp': lamp0,
             'conclusion': concl0, 'guide': guide0, 'reason': lw.get('reason')},
            {'n': 1, 'key': 'broad', 'title': '宽基定风格', 'lamp': lamp1,
             'conclusion': concl1, 'guide': guide1, 'rows': step1_rows},
            {'n': 2, 'key': 'sector', 'title': '圈板块', 'lamp': lamp2,
             'conclusion': concl2, 'guide': guide2, 'rows': step2_rows,
             'collapsed': collapsed, 'dropped': dropped2},
            {'n': 3, 'key': 'vcp', 'title': '个股形态', 'lamp': lamp3,
             'conclusion': concl3, 'guide': guide3, 'rows': step3_rows,
             'excluded': step3_excluded},
            {'n': 4, 'key': 'mine', 'title': '排雷', 'lamp': lamp4,
             'conclusion': concl4, 'guide': guide4, 'rows': mw_items},
        ],
        'note': ('五步漏斗（2026-09-27 第二波修订，用户正式指令）：0窗口（水温×债券相互关系）→1宽基四态'
                 '（阶段底部=一年分位≤30%/窄幅波动=低波/多头排列=50>150>200日线/高位）→2板块生命周期'
                 '（积聚=bottomWatch命中，启动=scan启动确认，主升=20日涨>10%且流入，高潮=高潮风险，'
                 '退潮=流出+一年分位≥70%）；第2步入选=积聚∪启动 且 板块自身形态达标'
                 '（VCP收缩/底部/杯柄任一+量能萎缩极致10日/60日均额≤0.7，收盘口径近似，两条都要；'
                 '被卡掉的积聚/启动板块在 dropped 字段如实列出）。'
                 '→3个股形态双轨：🔗共振轨=属于第2步入选板块（置顶，赢面优先）；'
                 '⭐优中选优轨=板块不同步但 池内（上证50∪中证500∪沪深300∪科创50∪创业板50∪中证1000，2026-10-01恢复中证1000）'
                 '∩形态达标（VCP收缩型/杯柄型，Stage2过趋势模板）∩聪明钱持续流入（近10缓存日主力净流入为正≥6天），'
                 '三条缺一不入；两轨都不沾不进第3步榜。'
                 '→4排雷（范围=第2步龙头∪第3步入围∪持仓观察股）。'
                 '状态灯🟢可看/🟡谨慎/🔴停；窗口🔴时下级全部降级为观察。'),
    }
    print(f"  funnel: {path}")
    print(f"  funnel 生命周期分布: "
          f"{ {lc: sum(1 for v in lc_map.values() if v == lc) for lc in ['积聚期','启动期','主升期','高潮期','退潮期','半路'] if lc in lc_map.values()} }")
    print(f"  funnel 板块形态: 达标{sum(1 for s in sp_map.values() if s['qualified'])}个/"
          f"{len(sp_map)}个有数据；第2步入选{len(step2_rows)}，形态卡掉{len(dropped2)}"
          f"（{[d['sector'] for d in dropped2]}）；第3步 共振{n_reson}/精选{n_cherry}/剔除{step3_excluded}")


def build_dual_axes(pro, trade_date, data, today_map):
    """总览并联双轴（2026-08-29 用户拍板：趋势轴∥短线轴，替代原串联第1/2步）。

    - 趋势轴（周线/日线级，中线布局，下游接 VCP 形态确认）：板块 = ① actionableSectors
      能投名单（subSector 二级口径优先）∪ ② bottomWatch 入围积聚 ∪ ③ sectorScan ⭐核心层
      "吸筹中"板块（source=吸筹观察，排最后；双头/高潮/高位天然排除）；同时在能投与积聚中
      出现的标注"能投名单·X档"。龙头统一走 _pick_sector_leaders（bottomWatch 已算好的
      直接复用，两处一致）。
    - 短线轴（60分钟/日线级）：题材活跃概念（东财 dc_index 当日口径）+ 短线强势板块
      （sectorScan「启动确认」信号：连续净流入≥2天+当日涨幅≥1.5%，仅低位/半路层——
      高潮风险/双头风险/高位流入一律排除，短线不追双头）。龙头=近5日主力净流入口径
      （全市场缓存，0 额外行情调用）。
    60分钟线实测：stk_mins 有权限但限频 1 次/分钟，全扫描需 10+ 分钟且挤占每晚预算，
    成本不可控未启用，短线口径用日线近似（note 注明）。
    每晚新增调用：dc_index 1 + dc_member ≤3 + moneyflow 1（缓存）+ 能投独有板块日线 ≤5×2。
    """
    d = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    flat = {s['code']: s for lst in today_map.values() for s in lst}
    mf_cache = _ensure_mf_cache(pro, trade_date)
    bw_items = (data.get('bottomWatch') or {}).get('items', [])
    bw_by_sector = {b['sector']: b for b in bw_items}

    def _norm_leaders(leaders):
        return [{'name': l['name'], 'code': l['code'], 'pctChg': l.get('pctChg', 0),
                 **({'strength': l['strength']} if l.get('strength') else {})}
                for l in (leaders or [])[:3]]

    # ── 趋势轴：能投名单板块（排最前）──
    trend_sectors = []
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
            trend_sectors.append({'sector': sub, 'source': src, 'fromActionable': True,
                                  'leaderVia': via, 'leaders': leaders})
            seen.add(sub)
    # bottomWatch 其余入围板块（能投名单之外的积聚命中）
    for b in bw_items:
        if b['sector'] in seen:
            continue
        if b.get('leaders'):
            leaders, via = _norm_leaders(b['leaders']), b.get('leaderVia', 'trend')
        else:
            leaders, via = _pick_sector_leaders(pro, trade_date, b['sector'], today_map)
        if leaders:
            trend_sectors.append({'sector': b['sector'],
                                  'source': '双档共振' if b.get('both') else ('60日档' if b.get('hit60') else '30日档'),
                                  'fromActionable': False, 'leaderVia': via, 'leaders': leaders})
            seen.add(b['sector'])
    # sectorScan ⭐核心层"吸筹中"板块（2026-08-29 断层修复：吸筹层不再是孤儿；
    # 双头/高潮/高位风险天然排除——只收 status=吸筹中 且 tier=core）
    for it in (data.get('sectorScan') or {}).get('items', []):
        if it.get('status') != '吸筹中' or it.get('tier') != 'core':
            continue
        if it['sector'] in seen:
            continue
        leaders, via = _pick_sector_leaders(pro, trade_date, it['sector'], today_map)
        if leaders:
            trend_sectors.append({'sector': it['sector'], 'source': '吸筹观察',
                                  'fromActionable': False, 'leaderVia': via, 'leaders': leaders})
            seen.add(it['sector'])
    trend_sectors = trend_sectors[:8]

    # ── 短线轴 A：短线强势板块（启动确认信号，排除高潮/双头/高位）──
    trend_names = {s['sector'] for s in trend_sectors}
    short_sectors = []
    for it in (data.get('sectorScan') or {}).get('items', []):
        if it.get('status') != '启动确认':
            continue  # 高潮风险/双头风险/高位流入·谨慎/吸筹中 一律不进短线轴
        leaders = _short_leaders(it['sector'], today_map, mf_cache)
        if not leaders:
            continue
        short_sectors.append({'sector': it['sector'], 'status': it['status'],
                              'pct5d': it.get('pct5d'), 'netInflow5d': it.get('netInflow5d'),
                              'consecDays': it.get('consecutiveDays'),
                              'trendOverlap': it['sector'] in trend_names,
                              'leaders': leaders})
    short_sectors = short_sectors[:4]

    # ── 短线轴 B：题材活跃概念（东财概念指数当日口径，与能投名单独立）──
    concepts = []
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
                concepts.append({'name': r['name'],
                                 'pctChange': round(float(r['pct_change']), 2),
                                 'totalMvY': round(float(r['total_mv']) / 1e4, 0),
                                 'upNum': int(r['up_num']),
                                 'leaders': leaders[:3]})
    except Exception as e:
        print(f"  Warning: dual axes concepts failed: {e}")

    data['dualAxes'] = {
        'trade_date': d,
        'trend': {'sectors': trend_sectors,
                  'broadEtfs': (data.get('broadTrend') or {}).get('items', []),
                  'note': ('趋势机会：周线/日线级别，服务中线布局，配合第3步形态确认等买点；'
                           '板块=能投名单∪底部积聚命中∪吸筹⭐观察（扫描榜核心层吸筹中，'
                           '双头/高潮/高位已排除），龙头=率先脱离底部（站上20日线·逼近/站上60日线·'
                           '距60日高点<15%），无率先龙头时用今日主力净流入居前（与底部监测卡同口径）')},
        'short': {'sectors': short_sectors, 'concepts': concepts,
                  'note': ('短线机会：60分钟/日线级别，实际口径为日线近似（60分钟线限频1次/分钟未启用）；'
                           '短线强势板块=启动确认信号（连续净流入≥2天+当日涨幅≥1.5%，低位/半路层，'
                           '已排除高潮/双头/高位）；题材活跃概念=东财概念指数当日口径'
                           '（涨幅+总市值≥300亿+上涨家数≥5，剔除打板/新高类），需自行甄别；'
                           '龙头=近5日主力净流入口径')},
    }
    data.pop('leaderStep', None)
    print(f"  dualAxes: 趋势轴板块 {len(trend_sectors)} 个, "
          f"短线轴强势板块 {len(short_sectors)} 个"
          + (f"（{'、'.join(s['sector'] for s in short_sectors)}）" if short_sectors else '')
          + f", 概念 {len(concepts)} 个"
          + (f"（{'、'.join(c['name'] for c in concepts)}）" if concepts else ''))


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

    范围：能投/入围板块龙头 + 概念龙头 + 形态精扫名单 + 自选持仓观察（去重）。
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
    axes = data.get('dualAxes') or {}
    for sec in (axes.get('trend') or {}).get('sectors', []):
        for l in sec.get('leaders', []):
            if l.get('code'):
                uni.setdefault(l['code'], {'name': l['name'], 'src': '趋势轴龙头'})
    for grp in ('sectors', 'concepts'):
        for sec in (axes.get('short') or {}).get(grp, []):
            for l in sec.get('leaders', []):
                if l.get('code'):
                    uni.setdefault(l['code'], {'name': l['name'], 'src': '短线轴龙头'})

    mines = {}  # code -> {'types': set, 'details': []}
    def _hit(code, typ, detail, date=''):
        m = mines.setdefault(code, {'types': set(), 'details': []})
        m['types'].add(typ)
        m['details'].append({'type': typ, 'detail': detail, 'date': date})

    # ── ① 资金面：融资红灯（marginWatch 既有口径）+ 主力5日净流出≥3亿（全市场缓存）──
    mw_map = {m.get('code'): m for m in (data.get('marginWatch') or {}).get('items', [])}
    mf_cache = _ensure_mf_cache(pro, trade_date)
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
    # 联动双轴：有雷的板块/概念龙头在 dualAxes 里就地打 ⛔ 标记
    mined = {m['code']: m['types'] for m in items}
    axes = data.get('dualAxes')
    if axes and mined:
        groups = list((axes.get('trend') or {}).get('sectors', [])) \
            + list((axes.get('short') or {}).get('sectors', [])) \
            + list((axes.get('short') or {}).get('concepts', []))
        for grp in groups:
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


# ── 两融数据事故修正（2026-09-28 用户确认）──
# tushare margin 接口 2026-09-24 起口径异常：全市场两融余额 09-23 26,550 亿 → 09-24 13,505 亿
# 断崖腰斩（疑只含单交易所）。以下按交易所口径/Gildata 核实值写死修正，守卫规则兜底未来异常。
MARGIN_TRUTH_OVERRIDE = {
    '20260924': {'total': 26373.03, 'fin': 26078.71, 'sec': 294.32,
                 'src': '交易所口径/Gildata核实（tushare margin 接口异常值13,505亿已剔除）'},
}
MARGIN_GUARD_MAX_CHG = 0.15   # 异常守卫：单日总余额变化 |Δ|>15% 即判数据源异常，丢弃该点沿用前值
MARGIN_DIVERGENCE_PCT = 2.0   # 双源比对（2026-09-29 用户指令）：|东财−Tushare|/Tushare >2% 打分歧标记
# TODO(备选源)：东财 datacenter 两融汇总接口（datacenter-web.eastmoney.com，RPTA_WEB_RZRQ_GGMX
# 或沪深汇总报表）作为 tushare 异常时的自动降级；本地 IP 封禁未实测，目前仅做守卫剔除（2026-09-28）。
# 2026-09-29 更新：RPTA_RZRQ_LSHJ（市场合计历史）本地实测可用，已落地为每日比对源（见下）。

_EM_DC_HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}


def _em_margin_totals():
    """东财 datacenter 两融市场合计（RPTA_RZRQ_LSHJ）→ {YYYYMMDD: {total,fin,sec}}（元→亿）。

    每日比对源（2026-09-29）：仅取最近 5 行供最新交易日比对；任何失败返回 None（优雅跳过，
    不影响主流程）。实测 2026-09-29：09-24 RZRQYE=26,373.03 亿，与交易所口径/Gildata 一致。
    """
    try:
        r = requests.get('https://datacenter-web.eastmoney.com/api/data/v1/get', params={
            'reportName': 'RPTA_RZRQ_LSHJ', 'columns': 'DIM_DATE,RZYE,RQYE,RZRQYE',
            'sortColumns': 'DIM_DATE', 'sortTypes': '-1',
            'pageSize': 5, 'pageNumber': 1, 'source': 'WEB', 'client': 'WEB',
        }, headers=_EM_DC_HEADERS, timeout=15)
        rows = ((r.json().get('result') or {}).get('data')) or []
        out = {}
        for x in rows:
            d = str(x['DIM_DATE'])[:10].replace('-', '')
            if x.get('RZRQYE'):
                out[d] = {'total': round(float(x['RZRQYE']) / 1e8, 2),
                          'fin': round(float(x['RZYE']) / 1e8, 2) if x.get('RZYE') else None,
                          'sec': round(float(x['RQYE']) / 1e8, 2) if x.get('RQYE') else None}
        return out or None
    except Exception as e:
        print(f'  Warning: EM margin compare unavailable (skip): {str(e)[:60]}')
        return None


def fetch_margin_summary(pro, trade_date, data):
    """全市场两融余额自动日更（Tushare margin，沪深北三所合计）。

    T+1 口径：交易日当晚披露前一交易日数据，updateTime 如实标注数据日期。
    daily 滚动保留最近 40 个交易日；totalBalance/finBalance/secBalance/trend/comment 自动重算。
    异常守卫（2026-09-28）：单日总余额 |Δ|>15% 判数据源异常，丢弃该点沿用最后正常值，
    块内标 suspect:true + suspectNote；连续异常保持哨兵直到恢复。MARGIN_TRUTH_OVERRIDE
    内核实值优先于接口原始值（修正记录于 corrections）。
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
        # ── ① 核实值修正（写死，来源注明）──
        corrections = []
        for i, td in enumerate(days):
            ov = MARGIN_TRUTH_OVERRIDE.get(td)
            if ov and abs(daily[i]['total'] - ov['total']) > 1:
                corrections.append({'date': daily[i]['date'], 'from': daily[i]['total'],
                                    'to': ov['total'], 'src': ov['src']})
                daily[i] = {'date': daily[i]['date'], 'total': ov['total'],
                            'fin': ov['fin'], 'sec': ov['sec'], 'corrected': True}
        # ── ② 异常守卫：|Δ|>15% 丢弃该点、沿用前值、标 suspect ──
        suspect_dates = []
        for i in range(1, len(daily)):
            prev_t = daily[i - 1]['total']
            if prev_t > 0 and abs(daily[i]['total'] - prev_t) / prev_t > MARGIN_GUARD_MAX_CHG:
                suspect_dates.append(daily[i]['date'])
                daily[i] = {'date': daily[i]['date'], 'total': prev_t,
                            'fin': daily[i - 1]['fin'], 'sec': daily[i - 1]['sec'],
                            'suspect': True}
        suspect = bool(suspect_dates and suspect_dates[-1] == daily[-1]['date'])
        suspect_note = (f"数据源异常守卫：{('、'.join(suspect_dates))} Tushare 两融值单日偏离前日>15%，"
                        f"已丢弃并沿用最后正常值；接口恢复后自动消除。") if suspect_dates else None
        # ── ③ 东财双源比对（2026-09-29 用户指令：Tushare 为主、东财 RPTA_RZRQ_LSHJ 每日比对）──
        # 偏差>2% 打 divergence 标记（块内注记两边数值与来源）；>15% 按守卫逻辑沿用前值+suspect；
        # 东财不可用（IP封禁/接口异常）优雅跳过并注明，绝不影响主流程。
        em = _em_margin_totals()
        compare = None
        if em:
            em_d = sorted(em)[-1]
            em_v = em[em_d]
            cur_t = daily[-1]['total']
            diff_pct = abs(em_v['total'] - cur_t) / cur_t * 100 if cur_t else 999.0
            compare = {'emDate': f'{em_d[:4]}-{em_d[4:6]}-{em_d[6:]}',
                       'emTotal': em_v['total'], 'tushareTotal': cur_t,
                       'diffPct': round(diff_pct, 2),
                       'divergence': bool(diff_pct > MARGIN_DIVERGENCE_PCT),
                       'source': 'Tushare margin（主） vs 东财datacenter RPTA_RZRQ_LSHJ（比对）'}
            if diff_pct > 15:
                # 双源严重分歧=数据源异常，按守卫逻辑沿用前日值 + suspect 哨兵
                daily[-1] = {'date': daily[-1]['date'], 'total': daily[-2]['total'],
                             'fin': daily[-2]['fin'], 'sec': daily[-2]['sec'], 'suspect': True}
                suspect = True
                suspect_note = ((suspect_note or '')
                                + f"双源严重分歧：Tushare {cur_t:.0f}亿 vs 东财 {em_v['total']:.0f}亿"
                                  f"（{compare['emDate']}，偏差{diff_pct:.1f}%>15%），已沿用前值并标 suspect。")
                compare['action'] = '沿用前值+suspect'
            elif diff_pct > MARGIN_DIVERGENCE_PCT:
                suspect_note = ((suspect_note or '')
                                + f"双源分歧：Tushare {cur_t:.0f}亿 vs 东财 {em_v['total']:.0f}亿"
                                  f"（{compare['emDate']}，偏差{diff_pct:.1f}%>2%），数值保留待观察。")
        else:
            compare = {'skipped': True,
                       'note': '东财比对源不可用（IP封禁/接口异常），本日仅 Tushare 单源'}
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
        # 噪声带（2026-09-28 起注明）：5日变动 ±50亿内（≈余额0.2%）视为持平，避免微噪误判趋势
        trend = '上升' if d5 > 50 else ('下降' if d5 < -50 else '持平')
        md = f"{int(td_last[4:6])}月{int(td_last[6:])}日"
        c = f"截至{md}两融余额{latest['total']:.0f}亿，较前日{'增加' if chg >= 0 else '减少'}约{abs(chg):.0f}亿"
        if streak >= 2:
            c += f"，连续{streak}日{'上升' if direction > 0 else '下降'}"
        c += f"。融资余额{latest['fin']:.0f}亿，融券余额{latest['sec']:.0f}亿。"
        if trend == '上升':
            c += "杠杆资金持续回流，市场风险偏好回升。"
        elif trend == '下降':
            c += "杠杆资金持续离场，市场风险偏好下降。"
        else:
            c += "杠杆资金总体观望，市场风险偏好平稳。"
        if corrections:
            c += '（' + '；'.join(f"{x['date']}值{x['from']:.0f}亿系接口异常，已按{x['src']}修正为{x['to']:.0f}亿"
                                 for x in corrections) + '）'
        if suspect_note:
            c += f'（{suspect_note}）'

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
            'suspect': suspect,
            'suspectNote': suspect_note,
            'corrections': corrections,
            'compare': compare,
        })
        ds = data.setdefault('dataSources', {}).setdefault('marginTrading', {})
        ds.update({'source': 'Tushare margin（沪深北交易所两融汇总）', 'freq': '日更',
                   'lastUpdate': update_time,
                   'note': 'T+1口径：交易日当晚更新前一交易日数据；异常守卫：单日|Δ|>15%剔除沿用前值（2026-09-28）；双源比对=东财RPTA_RZRQ_LSHJ每日对照，偏差>2%标分歧、>15%沿用前值+suspect（2026-09-29）'})
        cmp_txt = ''
        if compare and not compare.get('skipped'):
            cmp_txt = f" | 比对 Tushare {compare['tushareTotal']:.0f} vs 东财 {compare['emTotal']:.0f}（差{compare['diffPct']}%{' ⚠分歧' if compare['divergence'] else ' ✓一致'}）"
        elif compare:
            cmp_txt = ' | 比对：东财不可用，单源'
        print(f"  marginTrading: {update_time} 余额{latest['total']:.0f}亿 近5日{d5:+.0f}亿{cmp_txt}")
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


# ── CCASS 外资托管持股快照（2026-09-30 用户正式指令：外资栏目加港交所月底月初公布的外资加减仓动向）──
# 数据源考证结论（2026-09-30 本机实测）：
#   HKEX SDW（www3.hkexnews.hk/sdw/search/searchsdw.aspx）可机查——GET 取 __VIEWSTATE 后 POST 表单
#   （无需 __EVENTVALIDATION），返回全部 CCASS 参与者（托管行/券商）持股明细；历史≥12 个月可回补
#   （实测 2025/12/31、2026/03/31、2026/08/31 均通）；需 ~4s 间隔+退避，快速连发会被断连。
#   Tushare 无 CCASS 托管行接口（hk_hold=港股通内资南向，勿混）；akshare 无 CCASS 接口。
# 口径免责：CCASS 托管行持股≠纯外资最终持仓（nominee 混合账户，含该行全部客户），仅作参考口径。
CCASS_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', 'ccass_history.json')
CCASS_SDW_URL = 'https://www3.hkexnews.hk/sdw/search/searchsdw.aspx'
CCASS_REQ_GAP = 4.0           # SDW 请求间隔（实测限流）
# 港股大市值蓝筹 20 只（配置化可改）
CCASS_STOCKS = [
    ('00700', '腾讯控股'), ('03690', '美团-W'), ('00005', '汇丰控股'), ('01299', '友邦保险'),
    ('00941', '中国移动'), ('00388', '香港交易所'), ('09988', '阿里巴巴-W'), ('01398', '工商银行'),
    ('00939', '建设银行'), ('02318', '中国平安'), ('01810', '小米集团-W'), ('01211', '比亚迪股份'),
    ('00857', '中国石油股份'), ('00883', '中国海洋石油'), ('02628', '中国人寿'), ('01088', '中国神华'),
    ('09618', '京东集团-SW'), ('09999', '网易-S'), ('09888', '百度集团-SW'), ('09633', '农夫山泉'),
]
# 外资托管行/券商名称关键词（大写包含匹配，覆盖主流外资行；名单可调）
CCASS_FOREIGN_KEYS = [
    'HONGKONG AND SHANGHAI BANKING', 'HSBC', 'CITIBANK', 'STANDARD CHARTERED',
    'JPMORGAN', 'J.P. MORGAN', 'MORGAN STANLEY', 'MERRILL LYNCH', 'UBS', 'GOLDMAN SACHS',
    'DEUTSCHE BANK', 'BNP PARIBAS', 'CREDIT SUISSE', 'NOMURA', 'BARCLAYS', 'MACQUARIE',
    'STATE STREET', 'INTERACTIVE BROKERS', 'BANK OF NEW YORK', 'CACEIS', 'CLEARSTREAM',
]
CCASS_SOUTHBOND_KEY = 'CHINA SECURITIES DEPOSITORY'   # 中国结算=港股通内资（对照项，不计入外资）


def _sdw_http(data=None, tries=3):
    """SDW GET/POST（gzip 兼容、限流退避）。失败返回 None。
    注意：GET 不得带 Content-Type/Referer，否则被 WAF 重定向到门户首页（2026-09-30 实测）。"""
    import ssl as _ssl
    ctx = _ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = _ssl.CERT_NONE
    for k in range(tries):
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            if data is not None:
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                headers['Referer'] = CCASS_SDW_URL
            req = urllib.request.Request(CCASS_SDW_URL, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=40, context=ctx) as r:
                raw = r.read()
                if r.headers.get('Content-Encoding') == 'gzip':
                    import gzip as _gz, io as _io
                    raw = _gz.GzipFile(fileobj=_io.BytesIO(raw)).read()
                return raw.decode('utf-8', errors='ignore')
        except Exception as e:
            print(f'    sdw retry{k}: {type(e).__name__} {str(e)[:50]}')
            time.sleep(12 * (k + 1))
    return None


def _ccass_query(code5, date_dash, form):
    """查某股某日 CCASS 参与者持股 → (foreign, south, n_participants)；失败/非交易日返回 None。
    form=(vs, vg) 可跨查询复用；返回 None 时调用方应刷新表单重试一次。"""
    import urllib.parse
    payload = {
        '__EVENTTARGET': '', '__EVENTARGUMENT': '', '__VIEWSTATE': form[0], '__VIEWSTATEGENERATOR': form[1],
        'today': datetime.now().strftime('%Y%m%d'), 'sortBy': 'shareholding', 'sortDirection': 'desc',
        'alertMsg': '', 'txtShareholdingDate': date_dash, 'txtStockCode': code5,
        'txtStockName': '', 'txtParticipantID': '', 'txtParticipantName': '',
        'txtShareholdingName': '', 'btnSearch': 'Search',
    }
    h = _sdw_http(data=urllib.parse.urlencode(payload).encode())
    if not h:
        return None
    trs = re.findall(r'<tr>\s*<td class="col-participant-id">([\s\S]*?)</tr>', h)
    rows = []
    for t in trs:
        m = re.search(r'col-participant-name[\s\S]*?mobile-list-body">([^<]*)</div>', t)
        s = re.search(r'col-shareholding [\s\S]*?mobile-list-body">([^<]*)</div>', t)
        if m and s:
            try:
                rows.append((m.group(1).strip(), int(s.group(1).replace(',', ''))))
            except ValueError:
                pass
    if not rows:
        return None   # 非交易日/日期超限/被限流
    foreign = sum(s for n, s in rows if any(k in n.upper() for k in CCASS_FOREIGN_KEYS))
    south = sum(s for n, s in rows if CCASS_SOUTHBOND_KEY in n.upper())
    return {'foreign': foreign, 'south': south, 'nPart': len(rows)}


def _ccass_get_form():
    h = _sdw_http()
    if not h:
        return None
    vs = re.search(r'__VIEWSTATE[^>]*value="([^"]*)"', h)
    vg = re.search(r'__VIEWSTATEGENERATOR[^>]*value="([^"]*)"', h)
    return (vs.group(1), vg.group(1)) if vs and vg else None


def fetch_ccass_foreign(pro, trade_date, data, backfill_dates=None):
    """CCASS 外资托管持股月末快照（月底/月初双触发 + 首次回补）。

    触发：trade_date 为当月最后一个交易日→快照=当日；为当月第一个交易日→快照=上月末（兜底月末失败）。
    backfill_dates（一次性本地回填用）：给定 ['2025-12-31', ...] 直接抓这些日期。
    快照数据入 ccass_history.json 滚动持久（随 workflow 回写）；SDW 不可达→本月快照缺失标注，
    绝不影响 nightly 主流程。展示块 data['ccassForeign']=最新月末 vs 上月末 环比。
    """
    cache = _load_json_cache(CCASS_CACHE_PATH, {})
    snaps = cache.setdefault('snapshots', {})

    def _hk_trade_dates(ym):
        """A股历近似当月起止（港股历差异由 SDW 空结果兜底）。"""
        try:
            cal = pro.trade_cal(exchange='SSE', start_date=f'{ym}01',
                                end_date=f'{ym}31', is_open='1')
            return sorted(cal['cal_date'].tolist())
        except Exception:
            return []

    targets = []
    if backfill_dates:
        targets = [d for d in backfill_dates if len(snaps.get(d) or {}) < len(CCASS_STOCKS)]
    else:
        days_cur = _hk_trade_dates(trade_date[:6])
        if days_cur:
            if trade_date == days_cur[-1]:      # 月末交易日
                targets = [f'{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}']
            elif trade_date == days_cur[0]:     # 月初交易日→补上月末
                prev = (datetime.strptime(trade_date, '%Y%m%d').replace(day=1) - timedelta(days=1))
                pd_days = _hk_trade_dates(prev.strftime('%Y%m'))
                if pd_days:
                    t = pd_days[-1]
                    t_iso = f'{t[:4]}-{t[4:6]}-{t[6:]}'
                    targets = [t_iso] if len(snaps.get(t_iso) or {}) < len(CCASS_STOCKS) else []
        targets = [t for t in targets if len(snaps.get(t) or {}) < len(CCASS_STOCKS)]

    fetched, failed = 0, 0
    if targets:
        form = _ccass_get_form()
        for tgt in targets:
            dd = tgt.replace('-', '/')
            snap = snaps.setdefault(tgt, {})   # 部分完成可续：只补缺的股票
            for code5, name in CCASS_STOCKS:
                if code5 in snap:
                    continue
                time.sleep(CCASS_REQ_GAP)
                r = _ccass_query(code5, dd, form) if form else None
                if r is None and form:   # 可能是 viewstate 过期：刷新表单重试一次
                    form = _ccass_get_form() or form
                    time.sleep(CCASS_REQ_GAP)
                    r = _ccass_query(code5, dd, form)
                if r is None:
                    failed += 1
                    continue
                r['name'] = name
                snap[code5] = r
                fetched += 1
                _save_json_cache(CCASS_CACHE_PATH, cache)   # 逐股落盘（SDW 慢，防超时中断丢失）
            if snap:
                print(f'  ccass: {tgt} 快照 {len(snap)}/{len(CCASS_STOCKS)} 只入缓存')
            else:
                print(f'  ccass: {tgt} 全部失败（SDW 不可达/非交易日），本月快照缺失')
        cache['note'] = ('CCASS 托管持股快照（HKEX SDW 机查，2026-09-30 上线）：每月最后/第一个交易日双触发；'
                         'foreign=外资托管行合计（汇丰/花旗/渣打/摩根大通/摩根士丹利/美林/瑞银/高盛等关键词匹配），'
                         'south=中国结算（港股通内资，对照项）。口径免责：托管行持股≠纯外资最终持仓'
                         '（nominee 混合账户含该行全部客户），仅作参考口径。')
        _save_json_cache(CCASS_CACHE_PATH, cache)

    # ── 展示块：最新月末 vs 上月末 环比（无论本月是否触发都重建）──
    try:
        dates = sorted(snaps)
        if not dates:
            data['ccassForeign'] = {'asOf': None, 'items': [], 'topUp': [], 'topDown': [],
                                    'missing': True,
                                    'note': 'CCASS 快照缓存为空（SDW 不可达待积累）'}
            return
        latest, prev = dates[-1], dates[-2] if len(dates) >= 2 else None
        items = []
        for code5, name in CCASS_STOCKS:
            cur = snaps[latest].get(code5)
            if not cur:
                continue
            pv = (snaps.get(prev) or {}).get(code5) if prev else None
            chg = cur['foreign'] - pv['foreign'] if pv else None
            chg_pct = round(chg / pv['foreign'] * 100, 2) if pv and pv['foreign'] else None
            items.append({'code': code5, 'name': name,
                          'foreign': cur['foreign'], 'south': cur['south'],
                          'chg': chg, 'chgPct': chg_pct,
                          'southChg': (cur['south'] - pv['south']) if pv else None})
        ranked = sorted((i for i in items if i['chg'] is not None), key=lambda x: -x['chg'])
        data['ccassForeign'] = {
            'asOf': latest, 'prevAsOf': prev,
            'items': items,
            'topUp': ranked[:5], 'topDown': ranked[-5:][::-1] if ranked else [],
            'missing': bool(targets and fetched == 0),
            'note': ('外资托管行合计持股（HKEX CCASS/SDW 月末快照）；环比=最新月末 vs 上月末。'
                     '口径免责：托管行持股≠纯外资最终持仓（nominee 混合账户），港股通内资单列对照，仅作参考。'),
        }
        print(f"  ccassForeign: asOf {latest}（vs {prev}），{len(items)} 只"
              + (f"，增持居首 {ranked[0]['name']}" if ranked else ''))
    except Exception as e:
        print(f"  Warning: ccassForeign display failed: {e}")


# ── DI 权益披露：外资大机构增减仓（2026-09-30 用户指令：雪球爬港交所公告→考证后改披露易直连）──
# 数据源考证结论（2026-09-30 本机实测）：
#   雪球港股公告 f10 接口 404、notice/hk/list 403（openresty 封 IP），不可用；
#   披露易 DI 门户 di.hkex.com.hk 可机查：GET NSSrchDate.aspx 取 VIEWSTATE（含 __EVENTVALIDATION）
#   → POST cmdSearchSS（大股东申报）+ 日期下拉 → NSNoticeSSDateList.aspx 分页列表（50 条/页，
#   pg=N GET 翻页），字段含 申报号/事件日/上市公司/申报人/代码/涉及股数/价格/变动后持股/变动后比例；
#   详情页 NSForm2.aspx?fn=<ref> 有股票代码（lblDStockCode）。服务器慢（~9s/次），需 4s 间隔+退避。
#   代码语义（官方 NSStdCode.aspx）：前两位 10=首次≥5%(新进)、11=增持、12=减持、13=权益性质变化
#   （1311/1313=借出、1312/1314=召回借券，非买卖）、14=淡仓增、15=淡仓减、16=借贷池、17=其他
#   （1704=清仓退出）。后缀 (L)=好仓/(S)=淡仓。
# 口径免责：仅持股跨越 5% 整数关口才强制申报（非全量持仓变动），申报滞后≤3 个交易日；
#   13xx 为借券/质押等性质变化并非买卖。Actions 出口 IP 可达性未实测，失败只标缺失不断流。
DI_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', 'di_notices.json')
DI_BASE = 'https://di.hkex.com.hk/di'
DI_REQ_GAP = 4.0            # di.hkex 请求间隔（实测服务器慢+会断连）
DI_WINDOW_DAYS = 7          # nightly 回看窗口（周末/漏跑兜底，按申报号去重）
DI_DISPLAY_DAYS = 30        # 前端展示窗口
DI_MAX_PAGES = 60           # 单次分页上限（防失控）
DI_CACHE_KEEP_DAYS = 90     # 缓存滚动保留天数（展示窗口 30 天，多留余量防膨胀：实测 ~80 条/交易日）

# 外资大机构白名单：(规范名, [匹配式])；英文用 \b 词边界正则，中文用子串。名单可调。
DI_FOREIGN_INSTITUTIONS = [
    ('BlackRock 贝莱德',       [r'\bblackrock\b', '贝莱德']),
    ('Vanguard 先锋领航',      [r'\bvanguard\b', '先锋领航', '先锋集团']),
    ('JPMorgan 摩根大通',      [r'\bjpmorgan\b', r'j\.?\s*p\.?\s*morgan', '摩根大通']),
    ('Morgan Stanley 摩根士丹利', [r'\bmorgan stanley\b', '摩根士丹利', '大摩']),
    ('Norges Bank 挪威央行',   [r'\bnorges bank\b', '挪威央行']),
    ('GIC 新加坡政府投资',     [r'\bgic\b', '新加坡政府投资']),
    ('Temasek 淡马锡',         [r'\btemasek\b', '淡马锡']),
    ('Capital Group 资本集团', [r'\bcapital group\b', '资本集团']),
    ('Fidelity 富达',          [r'\bfmr\b', r'\bfil limited\b', r'\bfidelity\b', '富达']),
    ('State Street 道富',      [r'\bstate street\b', '道富']),
    ('Goldman Sachs 高盛',     [r'\bgoldman sachs\b', '高盛']),
    ('UBS 瑞银',               [r'\bubs\b', '瑞银']),
    ('Citigroup 花旗',         [r'\bcitigroup\b', r'\bcitibank\b', r'\bciticorp\b', '花旗']),
    ('HSBC 汇丰',              [r'\bhsbc\b', r'hongkong and shanghai banking', '汇丰']),
    ('Schroders 施罗德',       [r'\bschroder', '施罗德']),
    ('Allianz 安联',           [r'\ballianz\b', '安联']),
    ('T. Rowe Price 普信',     [r't\.?\s*rowe\s*price', '普信']),
    ('Invesco 景顺',           [r'\binvesco\b', '景顺']),
    ('Amundi 东方汇理',        [r'\bamundi\b', '东方汇理']),
    ('Wellington 威灵顿',      [r'\bwellington\b', '威灵顿']),
    ('Baillie Gifford 柏基',   [r'\bbaillie gifford\b', '柏基']),
    ('Macquarie 麦格理',       [r'\bmacquarie\b', '麦格理']),
    ('Nomura 野村',            [r'\bnomura\b', '野村']),
    ('Daiwa 大和',             [r'\bdaiwa\b', '大和证券']),
    ('Mizuho 瑞穗',            [r'\bmizuho\b', '瑞穗']),
    ('Mitsubishi UFJ 三菱UFJ', [r'\bmitsubishi\b', '三菱']),
    ('Sumitomo Mitsui 三井住友', [r'\bsumitomo\b', '三井住友']),
    ('Northern Trust 北方信托', [r'\bnorthern trust\b', '北方信托']),
    ('Legal & General 励正',   [r'\blegal\s*&\s*general\b', r'\blegal and general\b', '励正']),
    ('Pictet 百达',            [r'\bpictet\b', '百达']),
    ('BNP Paribas 法巴',       [r'\bbnp paribas\b', '法国巴黎银行']),
    ('Deutsche Bank 德银',     [r'\bdeutsche bank\b', '德意志银行']),
    ('Barclays 巴克莱',        [r'\bbarclays\b', '巴克莱']),
    ('Standard Chartered 渣打', [r'\bstandard chartered\b', '渣打']),
    ('Manulife 宏利',          [r'\bmanulife\b', '宏利']),
    ('Prudential 保诚',        [r'\bprudential\b', '保诚']),
    ('abrdn 安本',             [r'\babrdn\b', r'\baberdeen\b', '安本']),
    ('Franklin Templeton 富兰克林', [r'\bfranklin\b', '富兰克林']),
    ('Qatar Investment 卡塔尔', [r'\bqatar\b', '卡塔尔投资']),
    ('ADIA 阿布扎比投资局',    [r'\babu dhabi\b', '阿布扎比']),
]
# 申报代码前两位 → 方向（官方 NSStdCode 语义）
DI_DIRECTION_MAP = {'10': '新进', '11': '增持', '12': '减持', '13': '性质变化',
                    '14': '淡仓增', '15': '淡仓减', '16': '借贷池', '17': '其他'}


def _di_match_institution(holder_name):
    """申报人名匹配外资白名单 → 规范名；不匹配返回 None。"""
    low = holder_name.lower()
    for canon, keys in DI_FOREIGN_INSTITUTIONS:
        for k in keys:
            if k.startswith('\\') or '\\b' in k or '\\s' in k or '.' in k:
                if re.search(k, low):
                    return canon
            elif k.lower() in low:
                return canon
    return None


def _di_direction(code_str):
    """'1201(L)' → (方向, 好仓/淡仓)。"""
    m = re.match(r'(\d{4,5})\s*\(([LS])\)', code_str)
    if not m:
        return '其他', ''
    num, pos = m.group(1), m.group(2)
    if num == '1704':
        return '清仓退出', pos
    return DI_DIRECTION_MAP.get(num[:2], '其他'), pos


# ── 港股英文名→中文简称映射（2026-09-30 用户指令：权益披露卡片标的中文化）──
# Tushare hk_basic 一次性全量拉取（enname+name），规范化英文名做 key 落 hk_names.json 持久缓存
# （随 workflow 回写，>30 天自动刷新，1 次调用）。翻译在展示块构建时进行——缓存里查不到的
# 标的保留英文名并计数，映射表日后补全后 nightly 自动补译（不改 notices 历史缓存）。
HK_NAMES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', 'hk_names.json')
HK_NAMES_REFRESH_DAYS = 30


def _hk_norm_name(s):
    """港股公司英文名规范化（双向同规则，DI 列表名 ↔ hk_basic enname）。"""
    from html import unescape as _unesc
    s = _unesc(s or '').upper()
    s = re.sub(r"(\s*-\s*(?:H SHARES|SW|W2?|SB|B|S|P))\s*$", '', s)   # 类别后缀
    s = re.sub(r"(\s*-\s*(?:H SHARES|SW|W2?|SB|B|S|P))\s*$", '', s)   # 双重后缀（如 "- B - H Shares"）
    s = re.sub(r"['\u2019]", '', s)
    s = re.sub(r'\bCOMPANY\b', 'CO', s)
    s = re.sub(r'\bLIMITED\b', 'LTD', s)
    s = re.sub(r'\bINTERNATIONAL\b', 'INTL', s)
    s = re.sub(r'\bCORPORATION\b', 'CORP', s)
    s = re.sub(r'\bHOLDINGS\b', 'HLDG', s)
    return re.sub(r'[^A-Z0-9]', '', s)


def _hk_names_map(pro):
    """加载/刷新港股名称映射 → {normKey: {code, cn}}；失败返回现有缓存或 {}。"""
    cache = _load_json_cache(HK_NAMES_PATH, {})
    mp = cache.get('map') or {}
    refreshed = cache.get('refreshedAt') or ''
    stale = True
    if refreshed:
        try:
            stale = (datetime.now() - datetime.strptime(refreshed, '%Y-%m-%d')).days > HK_NAMES_REFRESH_DAYS
        except ValueError:
            stale = True
    if (not mp or stale) and pro is not None:
        try:
            time.sleep(API_DELAY)
            df = pro.hk_basic(list_status='L', fields='ts_code,name,enname')
            new_mp = {}
            for _, r in df.iterrows():
                k = _hk_norm_name(r.get('enname'))
                if k and r.get('name'):
                    new_mp[k] = {'code': str(r['ts_code'])[:5], 'cn': r['name']}
            if len(new_mp) > 1000:
                cache = {'map': new_mp, 'refreshedAt': datetime.now().strftime('%Y-%m-%d'),
                         'note': 'Tushare hk_basic 英文名→中文简称映射（key=规范化英文名），权益披露标的中文化用'}
                _save_json_cache(HK_NAMES_PATH, cache)
                print(f'  hk_names: 映射表刷新 {len(new_mp)} 条')
                return new_mp
        except Exception as e:
            print(f'  Warning: hk_basic 刷新失败（用旧缓存）: {e}')
    return mp


def _di_session():
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
    return s


def _di_req(fn, tries=3):
    """di.hkex 请求带退避（服务器慢，偶发断连/超时）。"""
    for k in range(tries):
        try:
            return fn()
        except Exception as e:
            print(f'    di retry{k}: {type(e).__name__} {str(e)[:50]}')
            time.sleep(12 * (k + 1))
    return None


def _di_search_form(s):
    """GET 按日期搜索表单 → (vs, vsg, ev)；失败 None。"""
    r = _di_req(lambda: s.get(f'{DI_BASE}/NSSrchDate.aspx?src=MAIN&lang=EN&g_lang=en',
                              timeout=(20, 60)))
    if r is None or r.status_code != 200:
        return None
    h = r.text
    vs = re.search(r'__VIEWSTATE" value="([^"]*)"', h)
    vg = re.search(r'__VIEWSTATEGENERATOR" value="([^"]*)"', h)
    ev = re.search(r'__EVENTVALIDATION" value="([^"]*)"', h)
    return (vs.group(1), vg.group(1), ev.group(1)) if vs and vg and ev else None


def _di_parse_list(html):
    """解析大股东申报列表页 → [row dict]（不过滤白名单）。"""
    from html import unescape as _unesc
    rows = []
    for tr in re.findall(r'<tr[^>]*>[\s\S]*?</tr>', html):
        cells = re.findall(r'<td[^>]*>([\s\S]*?)</td>', tr)
        if len(cells) < 9:
            continue
        clean = [_unesc(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', c))).replace('\xa0', '').strip()
                 for c in cells]   # 2026-09-30 修复：HTML 实体（&#39;/&amp;）要反转义，否则英文名匹配失败
        ref = clean[0]
        if not re.match(r'^[A-Z]{2}\d{8}[A-Z]\d{5}$', ref):
            continue
        dm = re.match(r'(\d{2})/(\d{2})/(\d{4})', clean[1])
        if not dm:
            continue
        iso = f'{dm.group(3)}-{dm.group(2)}-{dm.group(1)}'
        direction, pos = _di_direction(clean[4])

        def _num(x):
            m2 = re.match(r'([\d,]+)', x)   # '5,515,000(L)' → 5515000；空/&nbsp; → None
            return int(m2.group(1).replace(',', '')) if m2 else None

        pm = re.search(r'([\d.]+)%?', clean[8])
        rows.append({
            'ref': ref, 'date': iso, 'corp': clean[2], 'holder': clean[3],
            'code': clean[4], 'direction': direction, 'pos': pos,
            'shares': _num(clean[5]),
            'price': clean[6] or None,
            'resultShares': _num(clean[7]),
            'resultPct': float(pm.group(1)) if pm else None,
            'url': f'{DI_BASE}/NSForm2.aspx?fn={ref}&lang=EN',
        })
    return rows


def fetch_di_foreign(pro, trade_date, data, backfill_days=None):
    """外资大机构权益披露（大股东申报）增量抓取 + 展示块。

    nightly：搜 [trade_date-7d, trade_date] 窗口，按申报号去重增量入 di_notices.json；
    backfill_days（一次性本地回填）：搜 [trade_date-Nd, trade_date]。
    分页早停：整页申报号全部已在缓存→停止翻页（窗口内旧页重复扫描）。
    展示块 data['diForeign']=近 30 天白名单申报（日期倒序，封顶 80 条）+ 机构活跃度榜。
    """
    notices_cache = _load_json_cache(DI_CACHE_PATH, {})
    notices = notices_cache.setdefault('notices', {})

    end_dt = datetime.strptime(trade_date, '%Y%m%d')
    days = backfill_days if backfill_days else DI_WINDOW_DAYS
    start_dt = end_dt - timedelta(days=days - 1)

    fetched, dup_stop = 0, False
    s = _di_session()
    form = _di_search_form(s)
    if not form:
        print('  di: 搜索表单获取失败（di.hkex 不可达），本期跳过')
    else:
        payload = {
            '__EVENTTARGET': '', '__EVENTARGUMENT': '',
            '__VIEWSTATE': form[0], '__VIEWSTATEGENERATOR': form[1], '__EVENTVALIDATION': form[2],
            'reCaptchaSS': '', 'reCaptchaDir': '', 'reCaptchaAllForm': '',
            'ddlStartDateDD': start_dt.strftime('%d'), 'ddlStartDateMM': start_dt.strftime('%m'),
            'ddlStartDateYYYY': start_dt.strftime('%Y'),
            'ddlEndDateDD': end_dt.strftime('%d'), 'ddlEndDateMM': end_dt.strftime('%m'),
            'ddlEndDateYYYY': end_dt.strftime('%Y'),
            'cmdSearchSS': 'Search Substantial Shareholder Notice',
        }
        time.sleep(DI_REQ_GAP)
        r = _di_req(lambda: s.post(f'{DI_BASE}/NSSrchDate.aspx?src=MAIN&lang=EN&g_lang=en',
                                   data=payload, timeout=(20, 120),
                                   headers={'Referer': f'{DI_BASE}/NSSrchDate.aspx?src=MAIN&lang=EN&g_lang=en'}))
        if r is None or 'NSNoticeSSDateList' not in r.url:
            print('  di: 搜索 POST 失败，本期跳过')
        else:
            list_url = r.url.replace('&', '&')  # 结果页 URL（含 scsd/sced），翻页加 &pg=N
            html = r.text
            # 总记录数 → 计算总页数（非末页也可能 <50 行：部分行结构不符被解析跳过，
            # 不能用 len<50 判末页，2026-09-30 回补时曾因此截断漏数据）
            tm = re.search(r'Total records[^0-9]*(\d+)', re.sub(r'<[^>]+>', ' ', html))
            total_rec = int(tm.group(1)) if tm else 0
            max_pg = min(DI_MAX_PAGES, (total_rec + 49) // 50) if total_rec else DI_MAX_PAGES
            for pg in range(1, max_pg + 1):
                if pg > 1:
                    time.sleep(DI_REQ_GAP)
                    sep = '&' if '?' in list_url else '?'
                    rr = _di_req(lambda pg=pg: s.get(f'{list_url}{sep}pg={pg}', timeout=(20, 90)))
                    if rr is None or rr.status_code != 200:
                        break
                    html = rr.text
                rows = _di_parse_list(html)
                if not rows:
                    break
                new_on_page = 0
                for row in rows:
                    if row['ref'] in notices:
                        continue
                    inst = _di_match_institution(row['holder'])
                    if not inst:
                        continue
                    row['inst'] = inst
                    notices[row['ref']] = row
                    fetched += 1
                    new_on_page += 1
                if all(row['ref'] in notices for row in rows):
                    dup_stop = True   # 整页都是旧数据 → 提前停止
                    break
                if new_on_page:
                    _save_json_cache(DI_CACHE_PATH, notices_cache)   # 逐页落盘（服务器慢，防中断丢失）
            notices_cache['note'] = ('港交所权益披露（披露易 DI，大股东 Form 1/2 申报，2026-09-30 上线）：'
                                     '外资大机构白名单命中才入缓存；direction 由官方申报代码映射'
                                     '（10=新进 11=增持 12=减持 13=性质变化[借券/质押等非买卖] '
                                     '14/15=淡仓增减 1704=清仓）。口径：仅持股跨越 5% 整数关口才强制申报，'
                                     '滞后≤3 个交易日，非全量持仓变动。')
            _save_json_cache(DI_CACHE_PATH, notices_cache)
            print(f'  di: 窗口 {start_dt:%Y-%m-%d}~{end_dt:%Y-%m-%d} 新增 {fetched} 条'
                  + ('（早停去重）' if dup_stop else ''))

    # 滚动裁剪旧缓存
    cutoff = (end_dt - timedelta(days=DI_CACHE_KEEP_DAYS)).strftime('%Y-%m-%d')
    stale = [k for k, v in notices.items() if (v.get('date') or '') < cutoff]
    for k in stale:
        notices.pop(k, None)
    if stale:
        _save_json_cache(DI_CACHE_PATH, notices_cache)

    # ── 展示块：近 30 天白名单申报（无论本期是否抓到都重建）──
    try:
        win_start = (end_dt - timedelta(days=DI_DISPLAY_DAYS - 1)).strftime('%Y-%m-%d')
        win_items = sorted((v for v in notices.values() if (v.get('date') or '') >= win_start),
                           key=lambda x: (x['date'], x['ref']), reverse=True)
        inst_stat = {}
        for it in win_items:   # 统计用窗口全量（不受列表封顶影响）
            st = inst_stat.setdefault(it.get('inst') or it['holder'], {'n': 0, 'up': 0, 'down': 0})
            st['n'] += 1
            if it['direction'] in ('新进', '增持'):
                st['up'] += 1
            elif it['direction'] in ('减持', '清仓退出'):
                st['down'] += 1
        items = win_items[:80]   # 前端列表封顶 80 条
        # ── 标的中文化：英文名→中文简称(代码)（hk_names 映射，展示时翻译自动补译；查不到保留英文）──
        hk_mp = _hk_names_map(pro)
        unmatched = 0
        for it in items:
            hit = hk_mp.get(_hk_norm_name(it.get('corp')))
            if hit:
                it['corpCn'] = hit['cn']
                it['stockCode'] = hit['code']
            else:
                it['corpCn'] = None
                it['stockCode'] = None
                unmatched += 1
            # ── 涉及股数占该机构持仓比例（2026-09-30 用户指令）──
            # DI 列表页无"变动前持股"字段（详情 Form 才有，逐条抓太贵）→ 按方向反推：
            # 增持 before=resultShares-shares；减持 before=resultShares+shares；
            # 新进无分母→标签'新进建仓'；清仓→'清仓退出'；性质变化/淡仓/借贷池非买卖→None。
            # 反推口径：假设涉及股数全部计入好仓变动（11x/12x 成立），近似值。
            sh, rs = it.get('shares'), it.get('resultShares')
            d = it.get('direction')
            it['pctOfHolding'] = None
            it['pctOfTotal'] = None
            it['holdingNote'] = None
            if d == '新进':
                it['holdingNote'] = '新进建仓'
            elif d == '清仓退出':
                it['holdingNote'] = '清仓退出'
            elif d in ('增持', '减持') and sh and rs is not None:
                before = (rs - sh) if d == '增持' else (rs + sh)
                if before > 0:
                    p = round(sh / before * 100, 2)
                    it['pctOfHolding'] = p if d == '增持' else -p
            # 占总股本比例（便宜顺算：总股本=resultShares/resultPct）
            if sh and rs and it.get('resultPct'):
                total_sh = rs / (it['resultPct'] / 100.0)
                if total_sh > 0:
                    it['pctOfTotal'] = round(sh / total_sh * 100, 3)
        top_inst = sorted(({'name': k, **v} for k, v in inst_stat.items()),
                          key=lambda x: -x['n'])[:8]
        data['diForeign'] = {
            'asOf': end_dt.strftime('%Y-%m-%d'),
            'windowDays': DI_DISPLAY_DAYS,
            'items': items,
            'topInst': top_inst,
            'total': len(win_items),
            'unmatched': unmatched,
            'missing': not items,
            'note': ('港交所权益披露（大股东申报）：仅持股跨越 5% 整数关口才强制申报，非全量持仓变动；'
                     '申报滞后≤3 个交易日；「性质变化」多为借券/质押等非买卖操作；'
                     '淡仓(S)=做空方向。机构名单为主流外资白名单，不代表全部外资。'),
        }
        print(f"  diForeign: 近{DI_DISPLAY_DAYS}天 {len(win_items)} 条（展示 {len(items)}）"
              + (f"，最活跃 {top_inst[0]['name']}×{top_inst[0]['n']}" if top_inst else ''))
    except Exception as e:
        print(f"  Warning: diForeign display failed: {e}")


# fetch_leverage_concentration 已删除（2026-10-01 死字段清理：杠杆控盘卡下线，函数只喂该卡）
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
# A. 个股级形态精扫（上证50∪中证500∪沪深300∪科创50∪创业板50∪中证1000 成分池，日线+周线双级别）
# B. bottomWatch 积聚新鲜度（首触日+连续命中天数持久化）
# C. 资金+预期双确认（bottomWatch × ECI 前10 展示层联动）
# ══════════════════════════════════════════════════════════════════

VCP_MEMBERS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'cache', 'index_members.json')
VCP_FRESHNESS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'cache', 'bottomwatch_first_seen.json')
VCP_POOL_INDICES = ['000016.SH', '000905.SH', '000300.SH', '000688.SH', '399673.SZ', '000852.SH']
# 上证50∪中证500∪沪深300∪科创50∪创业板50∪中证1000（2026-10-01 用户口径恢复中证1000，六指数池；
# 2026-09-27 口径曾去掉中证1000、加入科创50/创业板50）。周五刷新调用 5→6 次。
VCP_MIN_MV = 2_500_000                    # 全池总市值下限 250 亿（daily_basic total_mv，万元）
VCP_DAILY_WIN, VCP_DAILY_K = 60, 2      # 日线级：近60交易日窗口，摆动高点±2日确认
VCP_WEEK_WIN, VCP_WEEK_K = 40, 1        # 周线级：近40周窗口，摆动高点±1周确认
VCP_MIN_CONTRACTIONS = 2                # 最少收缩次数（递减即达标）
VCP_DECAY_TOL = 1.25                    # 收缩递减容差（后次 ≤ 前次×1.25 且末次<首次）
VCP_CONTRACT_MIN = 3                    # VCP收缩型正式类别：≥3 次递减收缩（2026-09-08 用户口径，优先级最高）
VCP_SHOW_DIST = 8.0                     # 收缩型/杯柄型只展示距枢轴 <8%（容忍 3% 以内已突破）
VCP_SHOW_DIST_LO = -5.0                 # 距枢轴下限（负值=已突破容忍幅度）
VCP_SHOW_DIST_PLAT = 12.0               # 底部平台型展示距枢轴放宽至 12%（2026-10-01 十二案例校准：
                                        # 底部平台枢轴常偏离 8% 以上，中信特钢 11.4%/思源电气 10.7%）
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
    """上证50∪中证500∪沪深300∪科创50∪创业板50∪中证1000 成分股池：index_weight 取最新月度权重，每周五刷新。

    刷新时一并取 daily_basic 总市值快照（1 次调用），供全池 ≥250 亿市值过滤。
    （2026-10-01 恢复中证1000 六指数池，周五刷新 5→6 次调用；
    缓存键不匹配时立即强制刷新，不必等周五。）
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


def _vol_shrink_ok(vols, tail_max=1.2, tail_shrink=0.85, decline_min=0.6):
    """大比例缩量判定（2026-10-01 第三轮③，用户口径）：5 段均量相邻递减对占比≥60%
    或末段均量/全程均量 ≤0.85，二者必居其一（强制缩量，斜率旁路已删除）；
    允许后期温和放量——末段/全程 ≤tail_max(=1.2) 为上限，超出=异常放量拒。
    返回 (ok, tail_ratio)。平台/杯柄/旗形统一套用。"""
    n = len(vols)
    if n < 4:
        return False, 9.0
    avg = sum(vols) / n
    if avg <= 0:
        return False, 9.0
    q = max(1, n // 5)
    parts = [vols[i * q:(i + 1) * q] for i in range(4)] + [vols[4 * q:]]
    sv = [sum(p) / len(p) for p in parts if p]
    tail_ratio = sv[-1] / avg
    if tail_ratio > tail_max:
        return False, round(tail_ratio, 3)
    pairs = sum(1 for i in range(len(sv) - 1) if sv[i + 1] < sv[i])
    decline_ok = len(sv) > 1 and pairs / (len(sv) - 1) >= decline_min
    return bool(decline_ok or tail_ratio <= tail_shrink), round(tail_ratio, 3)


def _vcp_platform(bars, min_days=10, max_days=50, max_amp=0.14, min_rise=0.10, dist_gate=None,
                  tail_vol_max=None, rise_max=None, trend60_min=None):
    """平台判定（2026-08-19 用户口径重命名两类，缺一不入选）。

    共同要件：平台期 10~50 个交易日窄幅横盘（振幅≤14%）、缩量（平台日均量<前 20 日拉升段）、
    规律收缩（平台三等分段振幅递减，容差 1.25 且末段<首段）。
    2026-10-01 收紧（用户反馈粤高速A/联影一眼假，12 案例口径锚定，默认 None=旧行为，
    宽基/杯柄调用不受影响；个股精扫调用处启用）：
    - tail_vol_max：末段量/区间均量失控上限（=1.4；2026-10-01 用户口径②由 0.95 硬门槛改为
      整体缩量判定——5 段递减对≥60% 或日量线性斜率<0 即可，末端单段放量=主力预热不一票否决）；
    - rise_max：杯柄型温和抬升上限（用户⑤「一段温和抬升后的平台整理」抬升段 ≤20%）；
    - trend60_min：近 60 日涨跌下限（排除下跌中继——粤高速A 60 日 -14% 的 12 天停顿非底部基座）。
    分类：
    - 杯柄型：底部已抬升（平台起点收盘相对前 60 日最低 ≥10%）且平台最低价未跌回前低
      → 底部起来后做平台，平台上沿=柄/枢轴（用户认定的高胜率形态）；
    - 底部平台型：抬升不足 10%，平台就在底部区域做规律窄幅缩量波动
      （平台最低价不破前低×0.98），上沿突破即底部确认。
    选择规则：dist_gate=None 时取满足条件的最长平台（从 50 日往下试，旧行为，宽基/杯柄沿用）；
    dist_gate=(lo, hi) 时优先取距枢轴落在窗内的最长成型平台，都不在窗内退回最长成型平台
    （2026-10-01 十二案例校准：中信特钢最长 47 日平台 dist 11.4% 被展示门槛误杀，
    缩短至 40 日则 dist 7.0% 达标）。
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
            if rise_max is not None and rise > rise_max:
                continue                        # 抬升超限：非「温和抬升后平台」
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
        seg_vols = []
        for i in range(3):
            part = plat[i * seg:(i + 1) * seg] if i < 2 else plat[i * seg:]
            seg_amps.append((max(b[1] for b in part) - min(b[2] for b in part))
                            / min(b[2] for b in part))
            seg_vols.append(sum(b[4] for b in part) / len(part))
        reg_shrink = (seg_amps[2] < seg_amps[0]
                      and all(seg_amps[i + 1] <= seg_amps[i] * 1.25 for i in range(2)))
        if not reg_shrink:
            continue
        # 量能判定（2026-10-01 第三轮③，用户口径，仅 tail_vol_max 非 None 时启用）：
        # 大比例缩量强制——5 段递减对≥60% 或末段/区间均量≤0.85 必居其一（斜率旁路已删，
        # 银行/电力/高速靠斜率<0 混进来的漏洞封堵）；末段≤tail_vol_max(=1.2) 为温和放量
        # 上限，超出=异常放量拒。保留 tailRatio 展示。
        tail_ratio = seg_vols[2] / plat_vol if plat_vol > 0 else 9.0
        if tail_vol_max is not None:
            vol_ok, tail_ratio = _vol_shrink_ok([b[4] for b in plat], tail_max=tail_vol_max)
            if not vol_ok:
                continue
        # 排除下跌中继（2026-10-01）：近 60 日跌幅超限的停顿非底部基座
        if trend60_min is not None and len(bars) > 61:
            t60 = close / bars[-61][3] - 1
            if t60 < trend60_min:
                continue
        pivot = hi
        dist = (pivot / close - 1) * 100
        cand = {'type': kind, 'days': n, 'amplitude': round(amp * 100, 1),
                'riseFromLow': round(rise * 100, 1),
                'tailRatio': round(tail_ratio, 2),
                'volRatio': round(plat_vol / rally_vol, 2) if rally_vol > 0 else None,
                'segAmps': [round(a * 100, 1) for a in seg_amps],
                'pivot': round(pivot, 2), 'distPct': round(dist, 1), 'formed': True}
        if dist_gate is None:
            best = cand
            break   # 已取最长平台（旧行为）
        if best is None:
            best = cand   # 最长成型平台兜底
        if dist_gate[0] <= dist <= dist_gate[1]:
            best = cand   # 距枢轴在展示窗内的最长平台，优先采用
            break
    return best


# ══════════ Minervini 精修（2026-09-26 月底大改版①，用户拍板口径） ══════════
MINERVINI_VCP_TOL = 1.10    # 收缩严格递减容差：每次收缩必须小于前一次（允许 ≤前次×1.10），且末次<首次
MINERVINI_MIN_CONTR = 3     # VCP 收缩次数下限
CUP_DEPTH_MIN, CUP_DEPTH_MAX = 12.0, 33.0   # 杯深 %（大盘弱势期放宽至 40）
CUP_DEPTH_MAX_WEAK = 40.0
CUP_MIN_TOTAL_DAYS = 25     # 杯+柄总时长 ≥5 周（25 交易日）
BREAKOUT_VOL_X = 1.4        # 突破确认：成交量 ≥ 50 日均量 ×1.4


def _trend_template(rows):
    """Minervini 趋势模板（Stage 2 资格审查）。rows=[date,close,high,low,vol] 升序。
    52 周≈250 交易日（vcp 缓存 300 日窗口内近似）。返回 {'pass': bool, 'evidence': [...]}。"""
    closes = [r[1] for r in rows]
    if len(closes) < 220:
        return {'pass': False, 'evidence': [{'item': '历史≥220日', 'ok': False, 'val': f'仅{len(closes)}日'}]}

    def ma(n, off=0):
        seg = closes[len(closes) - n - off: len(closes) - off if off else len(closes)]
        return sum(seg) / len(seg) if len(seg) == n else None

    c = closes[-1]
    ma50, ma150, ma200 = ma(50), ma(150), ma(200)
    ma200_1m = ma(200, 20)
    win = closes[-250:]
    lo52, hi52 = min(win), max(win)
    checks = [
        ('现价>150日线', ma150 is not None and c > ma150,
         f'{c:.2f} vs MA150 {ma150:.2f}' if ma150 else '—'),
        ('现价>200日线', ma200 is not None and c > ma200,
         f'{c:.2f} vs MA200 {ma200:.2f}' if ma200 else '—'),
        ('200日线上行≥1个月', ma200 is not None and ma200_1m is not None and ma200 > ma200_1m,
         f'MA200 {ma200_1m:.2f}→{ma200:.2f}' if ma200 and ma200_1m else '—'),
        ('50日线>150日线', ma50 is not None and ma150 is not None and ma50 > ma150,
         f'{ma50:.2f} vs {ma150:.2f}' if ma50 and ma150 else '—'),
        ('150日线>200日线', ma150 is not None and ma200 is not None and ma150 > ma200,
         f'{ma150:.2f} vs {ma200:.2f}' if ma150 and ma200 else '—'),
        ('距52周低点≥+25%', c >= lo52 * 1.25,
         f'低点{lo52:.2f}→现价{c:.2f}（{(c / lo52 - 1) * 100:+.0f}%）'),
        ('距52周高点≤25%', c >= hi52 * 0.75,
         f'高点{hi52:.2f}→现价{c:.2f}（{(c / hi52 - 1) * 100:+.0f}%）'),
    ]
    return {'pass': bool(all(ok for _, ok, _ in checks)),
            'evidence': [{'item': n, 'ok': bool(ok), 'val': v} for n, ok, v in checks]}


def _vcp_level_strict(bars, win, k, max_dd=None, max_contraction=None,
                      dist_high250=None, hist_pct=None):
    """Minervini 严格 VCP（2026-09-26 口径）：
    收缩序列 ≥3 次、每次收缩必须小于前一次（容差10%，逐项标 ok）、
    末次收缩均量 < 首次收缩均量（量能递减强制）；
    枢轴=末次收缩高点；失效位=末次收缩低点；放量确认线=50日均量×1.4。
    2026-10-01 第三轮收紧（用户口径，参数默认 None=旧行为，板块侧 vcpPreview 不受影响；
    仅个股精扫调用处启用）：
    - max_dd：窗口区间总回撤（区间最高高点→最低低点）上限（=0.15）；
    - max_contraction：单次收缩深度上限 %（=8.0）；
    - 高位拒：距一年高点 <8%（dist_high250 > -8）或一年分位 >85 的 VCP 直接拒。
    """
    if dist_high250 is not None and dist_high250 > -8:
        return None
    if hist_pct is not None and hist_pct > 85:
        return None
    bars = bars[-win:]
    if len(bars) < 12:
        return None
    if max_dd is not None:
        w_hi = max(x[1] for x in bars)
        w_lo = min(x[2] for x in bars)
        if w_hi <= 0 or (w_hi - w_lo) / w_hi > max_dd:
            return None
    sh = _vcp_swing_highs(bars, k)
    if len(sh) < MINERVINI_MIN_CONTR + 1:
        return None
    sh = sh[-(MINERVINI_MIN_CONTR + 3):]
    depths, seg_vols, seg_lows = [], [], []
    for a, b in zip(sh, sh[1:]):
        hi = bars[a][1]
        lo = min(x[2] for x in bars[a:b + 1])
        if hi <= 0:
            return None
        depths.append((hi - lo) / hi * 100)
        seg_lows.append(lo)
        seg_vols.append(sum(x[4] for x in bars[a:b + 1]) / (b - a + 1))
    if len(depths) < MINERVINI_MIN_CONTR:
        return None
    if max_contraction is not None and any(d > max_contraction for d in depths):
        return None                     # 单次收缩超限（2026-10-01 第三轮：≤8%）
    marks = [True] + [depths[i] <= depths[i - 1] * MINERVINI_VCP_TOL
                      for i in range(1, len(depths))]
    dec_strict = bool(all(marks) and depths[-1] < depths[0])
    vol_ok = bool(seg_vols[0] > 0 and seg_vols[-1] < seg_vols[0])
    pivot = bars[sh[-1]][1]
    close = bars[-1][3]
    dist = (pivot / close - 1) * 100 if close > 0 else 999
    vol50 = sum(x[4] for x in bars[-50:]) / min(50, len(bars))
    return {'contractions': [round(x, 1) for x in depths],
            'contractionsOk': marks,
            'count': len(depths), 'decreasing': dec_strict,
            'volTrend': '递减' if vol_ok else '未递减',
            'volFirst': round(seg_vols[0], 1), 'volLast': round(seg_vols[-1], 1),
            'pivot': round(pivot, 2), 'distPct': round(dist, 1),
            'invalidation': round(seg_lows[-1], 2),
            'volConfirm': round(vol50 * BREAKOUT_VOL_X, 1),
            'formed': bool(dec_strict and vol_ok)}


def _cup_handle_strict(bars, market_weak=False, dist_high250=None, hist_pct=None):
    """杯柄·底部反转型（2026-10-01 第三轮重写，用户口径——不再套 Stage 2 趋势模板）：
    前置：近半年明显下撤——现价自一年高点回撤 ≥12%（dist_high250 缺省时由 bars 内推）；
    位置门槛：距一年高点 ≥8% 或一年分位 ≤85（高位杯柄一律拒）；
    杯身=柄前 120 日内 1~2 个坑（低点相近或第二坑略高均可），杯深 12~33%（大盘弱势期 40%）；
    杯柄=右侧 10~20 日窄幅横盘（振幅 ≤8%）且低点不破杯身底部（容差 2%）；
    量能：坑底缩量（坑底±5日均量 < 杯身均量）+ 杯柄均量 < 杯身均量 +
    杯柄大比例缩量（③：5段递减对≥60% 或末段/均量≤0.85，末段≤1.2 温和放量上限）；
    杯+柄总时长 ≥25 交易日。枢轴=柄部高点；失效位=柄部低点；放量确认线=50日均量×1.4。
    取满足条件的最长杯柄。"""
    if len(bars) < 40:
        return None
    closes = [b[3] for b in bars]
    close = closes[-1]
    if close <= 0:
        return None
    if dist_high250 is None or hist_pct is None:
        win = closes[-250:]
        if dist_high250 is None:
            dist_high250 = (close / max(win) - 1) * 100
        if hist_pct is None:
            hist_pct = _pct_rank100(win, close)
    if dist_high250 > -12:
        return None                     # 前置：近半年明显下撤（自一年高点回撤≥12%）
    if not (dist_high250 <= -8 or (hist_pct is not None and hist_pct <= 85)):
        return None                     # 位置门槛：距一年高点≥8% 或分位≤85
    depth_max = CUP_DEPTH_MAX_WEAK if market_weak else CUP_DEPTH_MAX
    vol50 = sum(b[4] for b in bars[-50:]) / min(50, len(bars))
    for n in range(20, 9, -1):          # 杯柄 10~20 日（右侧横盘≥2 周），取最长
        handle = bars[-n:]
        h_hi = max(b[1] for b in handle)
        h_lo = min(b[2] for b in handle)
        if h_lo <= 0:
            continue
        amp = (h_hi - h_lo) / h_lo
        if amp > 0.08:
            continue                    # 柄右侧窄幅横盘：振幅 ≤8%
        cup = bars[-(n + 120):-n]
        if len(cup) < 15:
            continue
        hi_pos = max(range(len(cup)), key=lambda i: cup[i][1])
        cup_hi = cup[hi_pos][1]
        body = cup[hi_pos:]             # 杯身=杯沿高点之后
        lo_rel = min(range(len(body)), key=lambda i: body[i][2])
        cup_lo = body[lo_rel][2]
        if cup_hi <= 0:
            continue
        depth = (cup_hi - cup_lo) / cup_hi * 100
        if not (CUP_DEPTH_MIN <= depth <= depth_max):
            continue
        # 坑形态验证（用户口径：杯身=1~2 个低点相近或第二坑略高的坑）：
        # 杯身右半最低 < 左半最低×0.97 = 第二坑明显更深/单边阴跌创新低，非杯身，拒
        # （容差 3%=「相近」的量化；京东方案例第二坑深 8% 据此拒）
        half = len(body) // 2
        if half > 0:
            l1 = min(b[2] for b in body[:half])
            l2 = min(b[2] for b in body[half:])
            if l2 < l1 * 0.97:
                continue
        if h_lo < cup_lo * 0.98:
            continue                    # 柄低点破杯身底部
        total_days = len(body) + n
        if total_days < CUP_MIN_TOTAL_DAYS:
            continue
        cup_vol = sum(b[4] for b in body) / len(body)
        if cup_vol <= 0:
            continue
        h_vol = sum(b[4] for b in handle) / n
        if h_vol >= cup_vol:
            continue                    # 柄均量须低于杯身均量
        bottom = body[max(0, lo_rel - 5): lo_rel + 6]
        b_vol = sum(b[4] for b in bottom) / len(bottom)
        if b_vol >= cup_vol:
            continue                    # 坑底未缩量
        vol_ok, tail_ratio = _vol_shrink_ok([b[4] for b in handle])
        if not vol_ok:
            continue                    # 柄非大比例缩量/异常放量
        dist = (h_hi / close - 1) * 100
        return {'type': '杯柄型', 'days': n, 'totalDays': total_days,
                'cupDepth': round(depth, 1), 'depthOk': True, 'depthMax': depth_max,
                'amplitude': round(amp * 100, 1),
                'tailRatio': round(tail_ratio, 2),
                'volRatio': round(h_vol / cup_vol, 2),
                'bottomVolRatio': round(b_vol / cup_vol, 2),
                'pivot': round(h_hi, 2), 'distPct': round(dist, 1),
                'invalidation': round(h_lo, 2),
                'volConfirm': round(vol50 * BREAKOUT_VOL_X, 1),
                'formed': True}
    return None


# ══════════ 旗形整理简版检测（2026-10-01 用户指令：形态精扫多形态并列） ══════════
FLAG_MIN_DAYS, FLAG_MAX_DAYS = 5, 15     # 旗面 5~15 个交易日
FLAG_POLE_MIN = 0.15                     # 旗杆：旗面前约 12 个交易日收盘区间涨幅 ≥15%
FLAG_MAX_AMP = 0.09                      # 旗面振幅 ≤9%（窄幅下飘/横盘）
FLAG_BAND_LO, FLAG_BAND_HI = 0.85, 1.03  # 现价相对旗杆顶部的下飘/上飘容忍带


def _flag_pattern(bars):
    """旗形整理（简版，2026-10-01 用户口径）：旗杆急涨 ≥15%（旗面前约 12 个交易日收盘区间涨幅），
    随后 5~15 日窄幅下飘/横盘旗面（振幅 ≤9%、现价在旗杆顶部 0.85~1.03 带内）、
    旗面均量 < 旗杆均量（缩量）。枢轴=旗面高点；失效位=旗面低点；放量确认线=50日均量×1.4。
    取满足条件的最长旗面。bars: (date, high, low, close, vol) 升序。"""
    if len(bars) < FLAG_MAX_DAYS + 14:
        return None
    close = bars[-1][3]
    if close <= 0:
        return None
    for n in range(FLAG_MAX_DAYS, FLAG_MIN_DAYS - 1, -1):
        flag = bars[-n:]
        hi = max(b[1] for b in flag)
        lo = min(b[2] for b in flag)
        if lo <= 0:
            continue
        amp = (hi - lo) / lo
        if amp > FLAG_MAX_AMP:
            continue
        pole = bars[-(n + 12):-n]
        if len(pole) < 8:
            continue
        pole_ret = flag[0][3] / pole[0][3] - 1
        if pole_ret < FLAG_POLE_MIN:
            continue
        pole_top = max(b[1] for b in pole)
        if not (pole_top * FLAG_BAND_LO <= close <= pole_top * FLAG_BAND_HI):
            continue
        flag_vol = sum(b[4] for b in flag) / n
        pole_vol = sum(b[4] for b in pole) / len(pole)
        if not (pole_vol > 0 and flag_vol < pole_vol):
            continue
        # 旗面大比例缩量③（2026-10-01 第三轮）：递减对≥60% 或末段/均量≤0.85，末段≤1.2 上限
        vol_ok, flag_tail = _vol_shrink_ok([b[4] for b in flag])
        if not vol_ok:
            continue
        dist = (hi / close - 1) * 100
        vol50 = sum(b[4] for b in bars[-50:]) / min(50, len(bars))
        return {'type': '旗形整理', 'days': n, 'amplitude': round(amp * 100, 1),
                'polePct': round(pole_ret * 100, 1),
                'volRatio': round(flag_vol / pole_vol, 2),
                'tailRatio': round(flag_tail, 2),
                'pivot': round(hi, 2), 'distPct': round(dist, 1),
                'invalidation': round(lo, 2),
                'volConfirm': round(vol50 * BREAKOUT_VOL_X, 1),
                'formed': True}
    return None


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
    """个股级形态精扫（原个股 VCP 精扫，2026-10-01 改名多形态并列：VCP收缩/杯柄/平台整理/旗形整理）：上证50∪中证500∪沪深300∪科创50∪创业板50∪中证1000 成分池 ∩（持仓观察股 ∪ 积聚板块龙头 ∪ vcpWatch信号板块龙头）。

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

        # ── 形态判定（2026-09-26 Minervini 精修口径，月底大改版①）──
        # 趋势模板前置：VCP收缩型/杯柄型强制要求 Stage 2（不过则打回——能落底部整理则降级，
        # 否则剔除并记录 dropped_tt 供对照验证）；底部整理类保留并标注 Stage 1 基底分层。
        # VCP 收缩：严格递减（每次<前次，容差10%，逐项标红）≥3次 + 末次收缩均量<首次（量能递减强制）；
        # 杯柄：杯深12~33%（大盘弱势期放宽40%）+柄在杯体上半部+杯柄总时长≥25交易日；
        # 每只入围股输出买点参数（精确枢轴/突破放量确认条件/失效位/距枢轴%）——形态参数，非操作建议。
        market_weak = ('冷' in temp) or ('平' in temp)   # 大盘弱势期杯深上限放宽至 40%
        # 主力资金确认加分项（2026-10-01 用户口径）：复用 MINE_MF 全市场 moneyflow 10 日滚动缓存
        # （此处先调一次，16c 步第3/4步命中同一缓存，全天仍只 1 次全市场调用）；
        # 近 10 个缓存交易日主力净流入为正天数 ≥6 记为资金确认，advice 标注 + 同形态排序优先。
        try:
            mf_cache = _ensure_mf_cache(pro, trade_date)
        except Exception as e:
            print(f'  Warning: vcpStocks mf cache failed: {e}')
            mf_cache = {}
        mf_days = sorted(mf_cache)[-10:]
        items = []
        dropped_tt = []
        for code, meta in targets.items():
            rows = stock_daily.get(code) or []
            if len(rows) < 60:
                continue
            bars = [(r[0], r[2], r[3], r[1], r[4]) for r in rows]  # (date, high, low, close, vol)
            # 个股一年位置：250 交易日窗口价格分位 + 距250日高点回撤（复用日线缓存，零新增调用）
            closes250 = [r[1] for r in rows[-250:]]
            hist_pct = _pct_rank100(closes250, rows[-1][1])
            dist_high250 = (rows[-1][1] / max(closes250) - 1) * 100
            hist_low = (hist_pct is not None and hist_pct <= 30) or dist_high250 <= -20
            tt = _trend_template(rows)
            pf = _vcp_platform(bars, max_amp=0.105, tail_vol_max=1.2, rise_max=0.20,
                               trend60_min=-0.10,
                               dist_gate=(VCP_SHOW_DIST_LO, VCP_SHOW_DIST_PLAT))
                               # 2026-10-01 第三轮③（用户口径）：量能=大比例缩量强制
                               # （5段递减对≥60%或末段/均量≤0.85，斜率旁路已删）+
                               # 末段≤1.2 温和放量上限（由 1.4 收口），超=异常放量拒
            fl = _flag_pattern(bars)
            # VCP 收缩三收紧（2026-10-01 第三轮，用户口径）：区间总回撤≤15%、单次收缩≤8%、
            # 距一年高点<8% 或分位>85 直接拒（参数默认 None，板块侧 vcpPreview 不受影响）
            d_lv = _vcp_level_strict(bars, VCP_DAILY_WIN, VCP_DAILY_K, max_dd=0.15,
                                     max_contraction=8.0, dist_high250=dist_high250,
                                     hist_pct=hist_pct)
            w_lv = _vcp_level_strict(_resample_weekly(rows), VCP_WEEK_WIN, VCP_WEEK_K,
                                     max_dd=0.15, max_contraction=8.0,
                                     dist_high250=dist_high250, hist_pct=hist_pct)
            d_c3 = bool(d_lv and d_lv['formed'])
            w_c3 = bool(w_lv and w_lv['formed'])
            ch = _cup_handle_strict(bars, market_weak, dist_high250=dist_high250,
                                    hist_pct=hist_pct)
            raw, main_lv = None, None
            if d_c3 or w_c3:
                raw, main_lv = 'VCP收缩型', (d_lv if d_c3 else w_lv)
                if not tt['pass']:
                    dropped_tt.append(f"{info.get(code, {}).get('name', code)}:VCP收缩型")
                    raw, main_lv = None, None        # VCP 收缩保留 Stage 2 趋势模板拦截
            elif ch and ch['formed']:
                raw, main_lv = '杯柄型', ch          # 底部反转型（2026-10-01 第三轮重写）：
                                                     # 不再套 Stage 2，前置回撤≥12%+位置门槛在函数内
            if raw is None:
                # 2026-10-01 第三轮：极高位（分位>85 或距一年高点<8%）平台/旗形同样拒——
                # 与 VCP/杯柄位置门槛同阈值，封堵银行/电力/高速贴新高平台泛滥；
                # 分位 60~85 仍打「高位」标签照常展示（histPct 前端琥珀徽章）
                ext_high = (hist_pct is not None and hist_pct > 85) or dist_high250 > -8
                if ext_high:
                    continue
                if fl and fl['formed'] and VCP_SHOW_DIST_LO <= fl['distPct'] <= VCP_SHOW_DIST:
                    pattern = '旗形整理'           # 急涨后缩量旗面（趋势中继，非 Stage 1 基底，不强制趋势模板）
                    main_lv = fl                  # 距枢轴超窗的旗面不硬贴标签，回落平台判定
                elif pf and pf['formed']:
                    pattern = '底部整理'           # Stage 1 基底分层保留展示
                    plat = bars[-pf['days']:]
                    vol50 = sum(b[4] for b in bars[-50:]) / min(50, len(bars))
                    main_lv = dict(pf)
                    main_lv['invalidation'] = round(min(b[2] for b in plat), 2)
                    main_lv['volConfirm'] = round(vol50 * BREAKOUT_VOL_X, 1)
                else:
                    continue
            else:
                pattern = raw
            dist_limit = VCP_SHOW_DIST_PLAT if pattern == '底部整理' else VCP_SHOW_DIST
            if not (VCP_SHOW_DIST_LO <= main_lv['distPct'] <= dist_limit):
                continue   # 只展示成型或临近成型（收缩/杯柄距枢轴<8%；底部平台放宽至12%，2026-10-01 校准）
            sec = meta['sector']
            if sec in bad_sectors:
                fit_txt = '板块不配合⚠️'
            elif sec in good_sectors:
                fit_txt = '板块配合✅'
            else:
                fit_txt = '板块中性'
            stage = 'Stage 2' if tt['pass'] else 'Stage 1 基底（未过趋势模板）'
            sm_days = sum(1 for d in mf_days if (mf_cache.get(d) or {}).get(code, 0) > 0)
            mf_txt = (f'｜主力10日净流入{sm_days}天✅' if sm_days >= 6
                      else (f'｜主力10日净流入{sm_days}天' if mf_days else ''))
            advice = (f"{pattern}·距枢轴{main_lv['distPct']}%｜{water_txt}｜{fit_txt}{mf_txt}"
                      if water_txt else f"{pattern}·距枢轴{main_lv['distPct']}%｜{fit_txt}{mf_txt}")
            close = rows[-1][1]
            d_ok = bool(d_lv and d_lv['formed'])
            w_ok = bool(w_lv and w_lv['formed'])
            tag = ('日线✅+周线✅' if d_ok and w_ok else
                   ('日线✅' if d_ok else ('周线✅' if w_ok else '—')))
            buy_point = {'pivot': main_lv['pivot'],
                         'distanceToPivotPct': main_lv['distPct'],
                         'invalidation': main_lv.get('invalidation'),
                         'volConfirm': main_lv.get('volConfirm'),
                         'breakoutConfirm': (f"收盘>{main_lv['pivot']} 且成交量≥50日均量×1.4"
                                             + (f"（≈{main_lv['volConfirm']:.0f}手）"
                                                if main_lv.get('volConfirm') else ''))}
            items.append({'code': code,
                          'name': info.get(code, {}).get('name', code),
                          'sector': sec, 'star': meta['star'],
                          'inPool': bool(meta.get('inPool')),
                          'close': round(close, 2), 'tag': tag,
                          'pattern': pattern, 'platform': pf,
                          'cupHandle': ch if pattern == '杯柄型' else None,
                          'flag': fl if pattern == '旗形整理' else None,
                          'trendTemplate': tt, 'stage': stage,
                          'buyPoint': buy_point,
                          'histPct': hist_pct,
                          'distHigh250': round(dist_high250, 1),
                          'distMain': main_lv['distPct'],
                          'mfDays': sm_days,
                          'sectorFit': fit_txt, 'advice': advice,
                          'daily': d_lv, 'weekly': w_lv})
        items.sort(key=lambda x: (0 if x.get('mfDays', 0) >= 6 else 1,   # 资金确认组置顶（2026-10-01 用户口径：保持加分但分两组展示）
                                  {'VCP收缩型': 0, '杯柄型': 1, '底部整理': 2, '超窄幅整理': 2, '底部平台型': 2, '旗形整理': 3}.get(x['pattern'], 4),
                                  x['distMain']))
        eff_d = f'{eff[:4]}-{eff[4:6]}-{eff[6:]}'
        data['vcpStocks'] = {
            'trade_date': eff_d, 'poolSize': len(pool), 'poolRaw': len(pool_raw),
            'mvDate': mc.get('mvDate'), 'scanned': len(targets),
            'items': items[:15],
            'droppedByTrendTemplate': dropped_tt,
            'note': '池=上证50∪中证500∪沪深300∪科创50∪创业板50∪中证1000成分（index_weight周五刷新；2026-10-01用户口径恢复中证1000）∩总市值≥250亿（daily_basic口径，随成分周更）；精扫=持仓观察股(★点名纳入,不受池限)+积聚板块池内龙头+VCP信号板块龙头；'
                    '形态口径（2026-10-01 第三轮定稿，用户口径）：'
                    'VCP收缩型=≥3次严格递减收缩（每次<前次，容差10%）+末次收缩均量<首次+区间总回撤≤15%+单次收缩≤8%+高位拒（距一年高点<8%或分位>85 直接拒）+Stage 2 趋势模板强制拦截；'
                    '杯柄型=底部反转型（不再套 Stage 2）：前置近半年自一年高点回撤≥12%+位置门槛（距一年高点≥8%或分位≤85），杯身=柄前120日内1~2个坑（杯深12~33%，大盘弱势期40%），杯柄=右侧8~20日窄幅横盘（振幅≤8%）且低点不破杯底，量能=坑底缩量+柄均量<杯身均量+柄大比例缩量，杯柄总时长≥25交易日，枢轴=柄部高点；'
                    '底部整理=Stage 1 基底（未过趋势模板）的规律窄幅缩量平台（10~50日，振幅≤10.5%+大比例缩量强制（5段递减≥60%或末段/均量≤0.85，末段≤1.2为温和放量上限，超=异常放量拒）+杯柄抬升≤20%+近60日跌幅≥-10%排下跌中继；分位>60打「高位」标签照常展示），单独分层展示；'
                    '旗形整理=旗杆急涨≥15%（约12个交易日）后5~15日窄幅下飘/横盘旗面（振幅≤9%+旗面均量<旗杆均量+旗面大比例缩量③，现价在旗杆顶0.85~1.03带内，分位>60打「高位」标签），枢轴=旗面高点，不强制趋势模板；'
                    '大比例缩量③=5段均量递减对≥60% 或 末段/区间均量≤0.85（强制，斜率旁路已删），允许后期温和放量（末段≤1.2），超出=异常放量拒；'
                    '买点参数：枢轴价/突破确认（收盘>枢轴且量≥50日均量×1.4）/失效位（末次收缩低点或柄部低点）/距枢轴%——形态参数，非操作建议；'
                    '只展示距枢轴<8%的成型/临近成型个股（底部平台型放宽至12%）；'
                    '主力资金确认=近10个缓存交易日主力净流入≥6天（MINE_MF缓存，0新增调用），advice标注，名单按「资金确认组置顶→形态分组→距枢轴」排序；'
                    '建议=水温×板块合适度×资金确认，仅供关注优先级参考',
        }
        print(f"  vcpStocks: scanned {len(targets)}, formed {len(items)} "
              f"({[i['name'] + ':' + i['pattern'] for i in items[:5]]})"
              + (f", 趋势模板拦截 {len(dropped_tt)}: {dropped_tt[:6]}" if dropped_tt else ''))
    except Exception as e:
        print(f"  Warning: fetch_vcp_stocks failed (keep old vcpStocks): {e}")


# ── 个股半年对抗统计（2026-09-09 用户指令）──
STOCK_RS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'cache', 'stock_rs_cache.json')
STOCK_RS_ANN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'cache', 'stock_rs_ann_cache.json')
STOCK_RS_WINDOW = 120       # 近120个交易日（约半年）
STOCK_RS_BASE_TH = 0.3      # 基准涨/跌判定阈值 %
STOCK_RS_EXCESS_TH = 1.5    # 个股超额阈值 pct
STOCK_RS_GAP_TH = 1.5       # 开盘跳空≥+1.5% 的强对抗日剔除（隔夜消息定价签名，2026-09-09 用户指令）
# tushare 二级行业 → 东财行业板块名（push2 clist m:90+t:2，板块代码运行时动态解析，
# 2026-09-08 实测清单对齐；两个一级近似已在此标注并在前端 note 披露）
STOCK_RS_INDUSTRY_MAP = {
    '化学制药': '化学制药',
    '医疗保健': '医疗器械',    # 心脉/南微/迈瑞/联影均为器械股
    '机场': '航空机场',
    '化工原料': '化学原料',
    '电气设备': '电网设备',
    '食品': '食品饮料',
    '红黄酒': '食品饮料',      # 东财新版行业板块无酒类二级，归入食品饮料一级（近似）
    '旅游服务': '社会服务',    # 东财新版无旅游酒店二级，归入社会服务一级（近似）
    '特种钢': '钢铁',
    '工程机械': '工程机械',  # 东财行业板块清单精确存在（2026-09-13 探针验证）
}
_EM_HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'}


# 东财限频对策（2026-09-09 实测）：瞬时高频会被单个边缘节点瞬断 IP，换编号子域即恢复。
# 每次调用在多宿主间轮换 + 失败退避重试；调用间隔 1s。
_EM_KLINE_HOSTS = ['https://push2his.eastmoney.com', 'https://83.push2his.eastmoney.com',
                   'https://91.push2his.eastmoney.com', 'https://39.push2his.eastmoney.com']
_EM_CLIST_HOSTS = ['https://push2.eastmoney.com', 'https://83.push2.eastmoney.com',
                   'https://91.push2.eastmoney.com']


def _em_get_json(hosts, path, params, tries=4):
    """东财 HTTP GET：多宿主轮换 + 退避重试（5/10/15/20s）。"""
    last = None
    for t in range(tries):
        try:
            r = requests.get(hosts[t % len(hosts)] + path, params=params,
                             headers=_EM_HEADERS, timeout=20)
            return r.json() or {}
        except Exception as e:
            last = e
            if t < tries - 1:
                time.sleep(5 * (t + 1))
    raise last


def _em_board_list():
    """东财行业板块清单 {板块名: BK代码}（push2 clist，m:90+t:2=行业板块）。"""
    diff = ((_em_get_json(_EM_CLIST_HOSTS, '/api/qt/clist/get',
                          {'pn': 1, 'pz': 300, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2,
                           'fs': 'm:90+t:2', 'fields': 'f12,f14'}).get('data') or {}).get('diff') or [])
    return {x['f14']: x['f12'] for x in diff}


def _em_kline_pct(secid, lmt=300):
    """东财 push2his 日K → {YYYYMMDD: 涨跌幅%}（secid：指数 1.000001 / 板块 90.BKxxxx）。"""
    out = {}
    for k in (((_em_get_json(_EM_KLINE_HOSTS, '/api/qt/stock/kline/get',
                             {'secid': secid, 'klt': 101, 'fqt': 0, 'lmt': lmt,
                              'end': '20500101', 'iscca': 1,
                              'fields1': 'f1,f2,f3,f7', 'fields2': 'f51,f59'})
                .get('data') or {}).get('klines') or [])):
        p = k.split(',')
        out[p[0].replace('-', '')] = float(p[1])
    return out


def _rs_hit(bucket, base_pct, excess, excl=False):
    """单日判定：强对抗 +1 / 弱对抗 -1 / 不计 0。excl=True 的消息面驱动强对抗日剔除并计数。"""
    strong = base_pct < -STOCK_RS_BASE_TH and excess >= STOCK_RS_EXCESS_TH
    if strong and excl:
        bucket['excluded'] += 1
        bucket['days'].append(0)
    elif strong:
        bucket['win'] += 1
        bucket['days'].append(1)
    elif base_pct > STOCK_RS_BASE_TH and excess <= -STOCK_RS_EXCESS_TH:
        bucket['lose'] += 1
        bucket['days'].append(-1)
    else:
        bucket['days'].append(0)


def _rs_pack(bk):
    d20 = bk['days'][-20:]
    return {'win': bk['win'], 'lose': bk['lose'], 'net': bk['win'] - bk['lose'],
            'win20': sum(1 for x in d20 if x > 0), 'lose20': sum(1 for x in d20 if x < 0),
            'net20': sum(d20), 'excluded': bk['excluded']}


def _cninfo_org_id(session, code):
    """巨潮 topSearch 取 orgId（hisAnnouncement 的 stock 参数需要 code,orgId 格式）。"""
    time.sleep(API_DELAY)
    r = session.post('http://www.cninfo.com.cn/new/information/topSearch/query',
                     data={'keyWord': code, 'maxNum': 10}, timeout=15)
    for it in r.json():
        if it.get('code') == code:
            return it.get('orgId', '')
    return ''


def _rs_ann_backfill(pro, trade_date, need_start):
    """消息面过滤数据维护：公告日期（巨潮，每股列表）+ 开盘价（tushare daily）。

    返回 (ann_map, open_map)：ann_map {ts_code: set(YYYYMMDD)}，open_map {ts_code: {date: open}}。
    断点续传入 stock_rs_ann_cache.json（每股落盘）。成本：公告首跑≈每股 1 topSearch + 1~3 页查询，
    之后每晚每股 1 次（增量窗口=最近公告日-3天起，orgId 缓存）；开盘价首跑每股 1 次，
    之后每晚全市场批量 1 次。合计每晚 ≈17 次（<30 阈值）。
    """
    cache = _load_json_cache(STOCK_RS_ANN_PATH, {})
    orgs = cache.setdefault('orgIds', {})
    anns = cache.setdefault('anns', {})
    opens = cache.setdefault('opens', {})
    session = requests.Session()
    session.headers.update({'User-Agent': UA_BROWSER,
                            'Referer': 'http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice',
                            'X-Requested-With': 'XMLHttpRequest'})
    ann_calls = 0
    q_end = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    for tc in STOCKS:
        code = tc.split('.')[0]
        have = set(anns.get(tc, []))
        if have and max(have) >= (datetime.strptime(trade_date, '%Y%m%d')
                                  - timedelta(days=3)).strftime('%Y%m%d'):
            continue   # 近3天已覆盖（公告会补发/改期，保留 3 天回溯重叠）
        q_start = ((datetime.strptime(max(have), '%Y%m%d') - timedelta(days=3)).strftime('%Y-%m-%d')
                   if have else f"{need_start[:4]}-{need_start[4:6]}-{need_start[6:]}")
        try:
            if not orgs.get(tc):
                orgs[tc] = _cninfo_org_id(session, code)
                ann_calls += 1
            column = 'sse' if tc.endswith('.SH') else 'szse'
            new_dates = set()
            for page in range(1, 9):
                time.sleep(API_DELAY)
                ann_calls += 1
                r = session.post('http://www.cninfo.com.cn/new/hisAnnouncement/query', data={
                    'pageNum': page, 'pageSize': 30, 'column': column, 'tabName': 'fulltext',
                    'plate': '', 'stock': f"{code},{orgs[tc]}" if orgs[tc] else code,
                    'searchkey': '', 'secid': '', 'category': '', 'trade': '',
                    'seDate': f'{q_start}~{q_end}', 'sortName': '', 'sortType': '',
                    'isHLtitle': 'true'}, timeout=15)
                lst = (r.json().get('announcements') or [])
                if not lst:
                    break
                for a in lst:
                    ts_ms = a.get('announcementTime', 0)
                    if ts_ms:
                        new_dates.add((datetime.utcfromtimestamp(ts_ms / 1000)
                                       + timedelta(hours=8)).strftime('%Y%m%d'))
                if len(lst) < 30:
                    break
            anns[tc] = sorted(have | new_dates)
            _save_json_cache(STOCK_RS_ANN_PATH, cache)   # 每股落盘，中断可续
        except Exception as e:
            print(f'  Warning: stockRS anns {tc} failed: {str(e)[:60]}')
    # 开盘价：全部个股都在 7 天新鲜度内 → 每日全市场批量 1 次；否则逐股回补（首跑）
    stale = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=7)).strftime('%Y%m%d')
    open_calls = 0
    all_fresh = all(opens.get(tc) and max(opens[tc]) >= stale for tc in STOCKS)
    if all_fresh:
        try:
            time.sleep(API_DELAY)
            open_calls += 1
            df = pro.daily(trade_date=trade_date, fields='ts_code,trade_date,open')
            if df is not None and len(df):
                for _, r in df.iterrows():
                    tc = str(r['ts_code'])
                    if tc in STOCKS:
                        opens.setdefault(tc, {})[str(r['trade_date'])] = float(r['open'])
        except Exception as e:
            print(f'  Warning: stockRS opens batch failed: {str(e)[:60]}')
    else:
        for tc in STOCKS:
            od = opens.setdefault(tc, {})
            if od and max(od) >= stale:
                continue
            try:
                time.sleep(API_DELAY)
                open_calls += 1
                df = pro.daily(ts_code=tc,
                               start_date=(datetime.strptime(trade_date, '%Y%m%d')
                                           - timedelta(days=200)).strftime('%Y%m%d'),
                               end_date=trade_date, fields='trade_date,open')
                if df is not None and len(df):
                    for _, r in df.iterrows():
                        od[str(r['trade_date'])] = float(r['open'])
            except Exception as e:
                print(f'  Warning: stockRS opens {tc} failed: {str(e)[:60]}')
    # 裁剪：公告日期/开盘价各保留最近 200 个
    for tc in list(anns.keys()):
        if len(anns[tc]) > 200:
            anns[tc] = anns[tc][-200:]
    for tc in list(opens.keys()):
        if len(opens[tc]) > 200:
            for k in sorted(opens[tc].keys())[:-200]:
                opens[tc].pop(k, None)
    _save_json_cache(STOCK_RS_ANN_PATH, cache)
    print(f'  stockRS ann/open cache: anns {sum(len(v) for v in anns.values())} dates, '
          f'cninfo calls {ann_calls}, open calls {open_calls}')
    return {tc: set(v) for tc, v in anns.items()}, opens


def fetch_stock_rs(pro, trade_date, data):
    """个股半年对抗统计：STOCKS 全部个股 vs 上证综指 / 所属东财行业板块。

    判定（日线口径近似"日内对抗"）：
    - 强对抗日：基准跌（pct<-0.3%）且个股超额（个股pct-基准pct）≥+1.5pct → 记+1
    - 弱对抗日：基准涨（pct>+0.3%）且个股超额≤-1.5pct → 记-1
    窗口=近120个交易日（约半年），近20日为子项。
    行情源：个股=vcp_cache 日线缓存（零新增调用）；大盘/板块=东财 push2his
    （首日回补300日≈板块数+2 次 HTTP，之后每晚增量 lmt=10，断点续传入 stock_rs_cache）。
    """
    try:
        import vcp_preview as vcp
        vc = vcp.load_cache()
        stock_daily = vc.get('stock_daily') or {}
        # 缺历史/过期的个股回补（与 fetch_vcp_stocks 同口径；首日预计全部已齐、零回补）
        stale = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=7)).strftime('%Y%m%d')
        for code in STOCKS:
            rows = stock_daily.get(code) or []
            if len(rows) < STOCK_RS_WINDOW + 10 or rows[-1][0] < stale:
                try:
                    time.sleep(API_DELAY)
                    df = pro.daily(ts_code=code,
                                   start_date=(datetime.strptime(trade_date, '%Y%m%d')
                                               - timedelta(days=vcp.BACK_CAL_DAYS)).strftime('%Y%m%d'),
                                   end_date=trade_date)
                    if df is not None and len(df):
                        rows = [[str(r['trade_date']), float(r['close']), float(r['high']),
                                 float(r['low']), float(r['vol'])] for _, r in df.iterrows()]
                        rows.sort()
                        vc.setdefault('stock_daily', {})[code] = rows[-300:]
                        stock_daily = vc['stock_daily']
                except Exception as e:
                    print(f'  Warning: stockRS backfill {code} failed: {str(e)[:60]}')
        vcp.save_cache(vc)

        # 交易日序列：任取一只历史最完整的个股（A股统一历）
        ref = max((r for r in stock_daily.values() if r), key=len)
        all_dates = [r[0] for r in ref]
        need_dates = set(all_dates[-(STOCK_RS_WINDOW + 2):])

        # 消息面过滤数据（2026-09-09 用户指令：强对抗日必须是盘面自身打出来的强度，
        # 公告/隔夜消息推动的强势日剔除；弱对抗侧用户未提，暂不过滤）：
        # ①开盘跳空≥+1.5% ②当日或前一交易日有公告（巨潮口径）
        ann_map, open_map = _rs_ann_backfill(pro, trade_date, min(need_dates))

        cache = _load_json_cache(STOCK_RS_PATH, {})
        idx_days = cache.setdefault('index', {})
        boards = cache.setdefault('boards', {})
        calls = 0

        # 大盘=上证综指（东财 secid=1.000001 优先；东财被限流时回退 tushare index_daily，
        # 2026-09-09 本地实测东财共享出口 IP 会被瞬断，Actions 环境正常）
        # 来源随缓存持久化（cache['indexSrc']），避免"本期未取数"时误标来源
        src_idx = cache.get('indexSrc') or 'eastmoney'
        if not need_dates.issubset(idx_days.keys()):
            try:
                idx_days.update(_em_kline_pct('1.000001',
                                              lmt=300 if len(idx_days) < STOCK_RS_WINDOW else 10))
                calls += 1
                time.sleep(1)   # 东财限频：每次调用间隔 1s（瞬时高频会断 IP）
                cache['indexSrc'] = src_idx = 'eastmoney'
            except Exception as e:
                print(f'  Warning: stockRS EM index failed ({str(e)[:50]}), fallback tushare index_daily')
                time.sleep(API_DELAY)
                di = pro.index_daily(ts_code='000001.SH',
                                     start_date=(datetime.strptime(trade_date, '%Y%m%d')
                                                 - timedelta(days=200)).strftime('%Y%m%d'),
                                     end_date=trade_date)
                for _, r in di.iterrows():
                    idx_days[str(r['trade_date'])] = float(r['pct_chg'])
                cache['indexSrc'] = src_idx = 'tushare'

        # 行业板块：映射 + 日K回补（缓存已有的日期不重抓，断点续传；东财失败逐板块降级合成指数）
        board_names = sorted({STOCK_RS_INDUSTRY_MAP.get(s['industry'])
                              for s in STOCKS.values()} - {None})
        bl = cache.get('boardList') or {}
        try:
            bl_age = (datetime.strptime(trade_date, '%Y%m%d')
                      - datetime.strptime(cache.get('boardListDate', '20000101'), '%Y%m%d')).days
        except Exception:
            bl_age = 99
        if not bl or bl_age > 7:
            try:
                bl = _em_board_list()
                calls += 1
                time.sleep(1)
                cache['boardList'] = bl
                cache['boardListDate'] = trade_date
            except Exception as e:
                print(f'  Warning: stockRS EM board list failed ({str(e)[:50]}), 全部板块走合成指数')
                bl = cache.get('boardList') or {}
        unmapped_boards = []
        em_failed_boards = set()
        for bn in board_names:
            bcode = bl.get(bn)
            if not bcode:
                unmapped_boards.append(bn)
                em_failed_boards.add(bn)
                continue
            b = boards.setdefault(bn, {'code': bcode, 'days': {}})
            b['code'] = bcode
            if not need_dates.issubset(b['days'].keys()):
                try:
                    b['days'].update(_em_kline_pct(f'90.{bcode}',
                                                   lmt=300 if len(b['days']) < STOCK_RS_WINDOW else 10))
                    calls += 1
                    time.sleep(1)
                except Exception as e:
                    print(f'  Warning: stockRS EM kline {bn} failed ({str(e)[:50]}), 该股走合成指数')
                    em_failed_boards.add(bn)
        # 兜底基准：sector_history 等权合成指数（tushare 行业名精确匹配，零调用，本地常驻）
        syn = cache.setdefault('boardsSyn', {})
        hist = _load_sector_history()
        for ind in sorted({s['industry'] for s in STOCKS.values()}):
            sd = syn.setdefault(ind, {})
            for dt, _n, ret, _a in _history_series(hist, ind):
                sd[dt] = ret
            if len(sd) > 260:
                for k in sorted(sd.keys())[:-260]:
                    sd.pop(k, None)
        # 裁剪缓存：指数/板块各保留最近 260 个交易日
        for days in [idx_days] + [b['days'] for b in boards.values()]:
            if len(days) > 260:
                for k in sorted(days.keys())[:-260]:
                    days.pop(k, None)
        _save_json_cache(STOCK_RS_PATH, cache)

        def _sector_days(ind):
            """个股行业基准序列：东财板块优先（覆盖≥80%窗口），否则等权合成指数。返回 (days, 名称, 来源)。"""
            bn = STOCK_RS_INDUSTRY_MAP.get(ind)
            if bn and bn not in em_failed_boards:
                emd = (boards.get(bn) or {}).get('days') or {}
                if emd and len(need_dates & set(emd.keys())) >= len(need_dates) * 0.8:
                    return emd, bn, 'eastmoney'
            sd = syn.get(ind) or {}
            return (sd, f'{ind}(合成)', 'tushare合成') if sd else ({}, None, None)

        # ── 逐股逆行日流水（2026-09-26 月底大改版④：废除"强X/弱Y/剔除"表）──
        # 逆行日（2026-09-26 用户正式指令·三条件交集，缺一不可）：
        #   上证当日跌（pct<0）且 所属板块当日跌（pct<0）且 个股收红或平手（pct≥0）；
        #   废除旧"或"逻辑与"抗跌（跌幅<基准一半）"类别——收绿一律不算；
        #   基准跌幅不设幅度下限（只要下跌即算）。
        # 大涨（≥3%）且放量（≥2倍20日均量）的加粗标⭐；公告日打*号备注、不剔除。
        items = []
        skipped = []
        sec_src_used = set()
        for code, s in STOCKS.items():
            rows = stock_daily.get(code) or []
            closes = {r[0]: r[1] for r in rows}
            vols = {r[0]: r[4] for r in rows}
            seq = [d for d in all_dates if d in closes and d in idx_days][-(STOCK_RS_WINDOW + 1):]
            if len(seq) < 30:
                skipped.append(s['name'])
                continue
            bdays, sec_name, sec_src = _sector_days(s['industry'])
            if sec_src:
                sec_src_used.add(sec_src)
            ann_set = ann_map.get(code) or set()
            rev = []
            for i, (a, b) in enumerate(zip(seq, seq[1:])):
                if closes[a] <= 0:
                    continue
                pct = (closes[b] / closes[a] - 1) * 100
                idx_pct, sec_pct = idx_days.get(b), bdays.get(b)
                # 三条件交集：大盘跌 + 板块跌 + 个股收红/平手
                if idx_pct is None or sec_pct is None:
                    continue
                if not (idx_pct < 0 and sec_pct < 0 and pct >= 0):
                    continue
                hit_base, base_pct = ('板块', sec_pct) if sec_pct <= idx_pct else ('大盘', idx_pct)
                prior = [vols[d2] for d2 in seq[max(0, i + 1 - 20):i + 1] if d2 in vols]
                vol_x = (vols.get(b, 0) / (sum(prior) / len(prior))) if prior and sum(prior) > 0 else None
                big = bool(pct >= 3.0 and vol_x is not None and vol_x >= 2.0)
                rev.append({'date': f'{b[4:6]}/{b[6:]}', 'pct': round(pct, 1),
                            'basePct': round(base_pct, 1), 'base': hit_base,
                            'idxPct': round(idx_pct, 1), 'secPct': round(sec_pct, 1),
                            'volX': round(vol_x, 1) if vol_x is not None else None,
                            'big': big, 'ann': bool(b in ann_set or a in ann_set)})
            items.append({'code': code, 'name': s['name'], 'group': s['group'],
                          'industry': s['industry'], 'sectorName': sec_name,
                          'sectorSrc': sec_src,
                          'reverseCount': len(rev),
                          'reverseDays': rev[::-1],   # 最新在前
                          'daysUsed': len(seq) - 1})
        # 排序（2026-09-26 用户口径）：逆行天数降序
        items.sort(key=lambda x: (-x['reverseCount'], x['code']))
        d = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
        src_txt = f"大盘={'东财' if src_idx == 'eastmoney' else 'tushare'}，板块={'东财行业板块' if sec_src_used == {'eastmoney'} else '含tushare合成指数降级（标注（合成））'}"
        data['stockRS'] = {
            'trade_date': d, 'window': STOCK_RS_WINDOW, 'baseIndex': '上证综指',
            'indexSrc': src_idx,
            'items': items,
            'unmapped': sorted({s['industry'] for s in STOCKS.values()
                                if s['industry'] not in STOCK_RS_INDUSTRY_MAP}),
            'unmappedBoards': unmapped_boards,
            'note': ('逆行日流水（2026-09-26 三条件交集口径，用户正式指令）：'
                     '逆行日=上证当日跌 且 所属板块当日跌 且 个股收红或平手（pct≥0），三者缺一不可；'
                     '收绿一律不算（原"抗跌"类别已废除）；基准跌幅不设幅度下限；'
                     '逐日列出 日期+个股涨幅+大盘/板块跌幅；大涨≥3%且放量≥2倍20日均量加粗标⭐；'
                     '公告日打*号备注（不剔除，消息面强势如实展示由读者自判）；'
                     '基准=上证综指+所属行业板块（东财行业板块优先，限流时降级Tushare等权合成，'
                     '名称带（合成）者；东财行业为近似映射：医疗保健→医疗器械、红黄酒→食品饮料、'
                     '旅游服务→社会服务）；个股涨跌幅=日线收盘环比（未复权，除权日略有误差）；'
                     '窗口=近120个交易日（约半年）；'
                     f'本期数据源：{src_txt}'),
        }
        print(f"  stockRS(逆行流水): {len(items)} stocks × {STOCK_RS_WINDOW}d, EM HTTP calls: {calls}, "
              f"sources: idx={src_idx}, sec={sorted(sec_src_used)}"
              + (f", skipped: {skipped}" if skipped else '')
              + f", top: {[(i['name'], i['reverseCount']) for i in items[:3]]}")
    except Exception as e:
        print(f"  Warning: fetch_stock_rs failed (keep old stockRS): {e}")


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
# 宽基栏目：ETF份额雷达 / 板块资金轮动(份额口径) / 宽基波动率
# ══════════════════════════════════════════════════════════════
import re as _re

ETF_SHARE_CACHE = 'scripts/cache/etf_share_history.json'
# ETF 份额雷达监控池（13 只宽基；名称已用 fund_basic 核对）
# group 统一为 broad；series 用于轮动表分节与合计行
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
}

# 宽基系列 → 份额异动影响映射（用于短评）
SERIES_IMPACT = {
    '沪深300系列': '沪深300/大盘蓝筹',
    '上证50': '上证50/超大盘蓝筹',
    '中证500系列': '中证500/中盘股',
    '中证1000系列': '中证1000/小盘股',
    '科创50系列': '科创50/硬科技',
    '上证180': '上证180/大盘价值',
    '创业板': '创业板/成长股',
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
    """宽基栏目主流程：份额雷达 + 板块轮动 + 宽基波动率 + 自动短评。

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

    # ════════ 1. ETF 份额雷达（13 只核心宽基） ════════
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

    # ════════ 1b. 宽基份额轮动表（按系列分节） ════════
    try:
        radar_items = (data.get('etfShareRadar') or {}).get('items') or []
        if radar_items:
            def _rot_row(it):
                return {
                    'code': it['code'], 'name': it['name'],
                    'share': it['share'], 'chg1': it['chg1'], 'chg1Pct': it['chg1Pct'],
                    'amt1': it['amt1'], 'chg5Pct': it['chg5Pct'],
                    'signal': it['signal'], 'trend3': it['trend3'],
                }

            groups = []
            for gkey, gname in (('broad', '宽基组'),):
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
                'note': '信号口径：单日份额|>2%|且金额|>5亿|=关注，|>3%|且|>1亿|或|>20亿|=强信号；≥3只核心宽基同向异动=共振·大资金情绪信号；连续3日同向=趋势性增/减仓',
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

    # ════════ 3. 主体持仓估算（已下线，清除存量字段） ════════
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
        # 每日评语速览·宽基低波提示：HV20 近一年分位 <25% 的宽基（lowVolDigest 字段 2026-10-01 已删，前端无消费）
        low_hits = [v for v in vol_items if v.get('low')]
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
    """规则生成 4-6 句宽基市场短评（纯宽基口径：份额异动/位置层/形态/波动，无主体归因）。"""
    sents = []
    rot = data.get('etfRotation') or {}
    radar = data.get('etfShareRadar') or {}
    vol = data.get('indexVol') or {}
    bt = (data.get('broadTrend') or {}).get('items') or []
    bv = (data.get('broadVcp') or {}).get('items') or []

    # 1) 全市场 ETF 份额净增减
    if rot:
        t = rot.get('totalToday', 0)
        if abs(t) < 1:
            sents.append("全市场ETF（不含货币）昨日份额基本持平（净额不足1亿元）。")
        else:
            direction = '净申购' if t >= 0 else '净赎回'
            sents.append(f"全市场ETF（不含货币）昨日{direction}约{abs(t):.0f}亿元（份额变化×收盘价口径）。")

    # 2) 宽基份额异动 / 共振
    alerts = [i for i in radar.get('items', []) if i.get('alert')]
    if alerts:
        a = alerts[0]
        act = '流入' if (a.get('chg1') or 0) > 0 else '流出'
        sent = f"{a['name']}单日份额{a['chg1']:+.2f}亿份（约{a['amt1']:+.1f}亿元），大额资金{act}信号"
        res = (data.get('ntRotation') or {}).get('resonance') or {}
        if res.get('hit'):
            sent += f"，且{res['count']}只核心宽基同日同向{res['direction']}、呈共振，大资金情绪信号明确"
        else:
            sent += "；未见跨公司共振，暂属个别产品资金行为"
        sents.append(sent + "。")
    elif radar:
        sents.append("13只宽基ETF份额未见明显异动，资金面平稳。")

    # 3) 板块轮动主线
    if rot.get('inflowTop3') or rot.get('outflowTop3'):
        inflow = '、'.join(rot.get('inflowTop3') or []) or '无'
        outflow = '、'.join(rot.get('outflowTop3') or []) or '无'
        sents.append(f"近5日份额口径资金主要流入{inflow}类，流出{outflow}类。")

    # 4) 宽基位置层 + VCP 形态
    if bt:
        low = [i['indexName'] for i in bt if i.get('status') == '✅趋势候选']
        low_out = [i['indexName'] for i in bt if i.get('status') == '低位观察（份额流出）']
        high = [i['indexName'] for i in bt if i.get('status') == '高位·仅展示']
        if low:
            sents.append(f"位置层处于低位且份额未流出：{'、'.join(low)}，列为趋势候选。")
        elif low_out:
            sents.append(f"{'、'.join(low_out)}处低位但份额仍在流出，暂只观察。")
        if high:
            sents.append(f"{'、'.join(high)}处高位（距60日高点3%内或近20日涨幅>10%），仅展示不作候选。")
        if not low and not low_out and not high:
            sents.append("主要宽基多处于半路位置，暂无低位趋势候选。")
    if bv:
        brk = [i for i in bv if i.get('state') == '已突破']
        watch = [i for i in bv if i.get('state') in ('临近买点', '未突破·观察')]
        if brk:
            sents.append(f"{'、'.join(i['indexName'] for i in brk)}已收盘站上平台枢轴，形态突破确认。")
        for i in watch[:2]:
            sents.append(f"{i['indexName']}形成{i['pattern']}（{i['days']}日，振幅{i['amplitude']}%），"
                         f"{i['state']}、距枢轴{i['distPct']}%，盯{i['etfCode'].split('.')[0]}突破确认。")

    # 5) 宽基系列份额净额映射
    ntr = data.get('ntRotation') or {}
    flow_sents = []
    for g in ntr.get('groups', []):
        for s in g.get('series', []):
            t = s.get('total') or {}
            amt = t.get('amt1')
            target = SERIES_IMPACT.get(s['name'])
            if not target or amt is None:
                continue
            if abs(amt) >= 5:
                d_ = '净流入' if amt > 0 else '净流出'
                impact = '利多' if amt > 0 else '利空'
                flow_sents.append((abs(amt), f"{s['name']}ETF合计{d_}{abs(amt):.1f}亿 → 短期{impact}{target}"))
    flow_sents.sort(reverse=True)
    for _, txt in flow_sents[:2]:
        sents.append(txt + "。")

    # 6) 波动率状态
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


# ══════════════════════════════════════════════════════════════
# 指增 ETF 跟踪（宽基栏目第六卡，2026-09-04 样表验收后上线）
# ══════════════════════════════════════════════════════════════
ZIZENG_BASIC_CACHE = 'scripts/cache/zizeng_basic_cache.json'
ZIZENG_INDEX_BASIC_CACHE = 'scripts/cache/zizeng_index_basic.json'  # 板块指增跟踪指数代码名录（index_basic 周更）
ZIZENG_MIN_SCALE = 2.0  # 亿；≥5 亿前端打"达标"徽标

# 宽基（规模类）指数关键字：命中即从板块指增口径剔除（2026-09-17 用户口径：只保留行业/主题/策略指增）
ZIZENG_BROAD_KEYWORDS = [
    '上证科创板综合价格', '上证科创板综合', '上证科创板50成份', '上证科创板100',
    'MSCI中国A50互联互通', '创业板综合', '创业板指数',
    '中证A500', '中证A50', '中证1000', '中证2000', '中证800', '中证500', '中证小盘500',
    '沪深300', '上证50', '上证综合', '科创创业50', '中证A100', '巨潮100',
]

# benchmark 关键字 → 指数代码（按关键字长度降序匹配，避免 中证A50 误中 中证A500）
ZIZENG_INDEX_MAP = [
    ('上证科创板综合价格', '000681.SH'), ('上证科创板综合', '000680.SH'),
    ('上证科创板50成份', '000688.SH'), ('上证科创板100', '000698.SH'),
    ('MSCI中国A50互联互通', None),
    ('创业板综合', '399102.SZ'), ('创业板指数', '399006.SZ'),
    ('中证A500', '000510.SH'), ('中证A50', '930050.CSI'),
    ('中证1000', '000852.SH'), ('中证2000', '932000.CSI'),
    ('中证800', '000906.SH'), ('中证500', '000905.SH'),
    ('沪深300', '000300.SH'), ('上证50', '000016.SH'), ('上证综合', '000001.SH'),
]
ZIZENG_INDEX_NAME = {'000300.SH': '沪深300', '000905.SH': '中证500', '000852.SH': '中证1000',
                     '932000.CSI': '中证2000', '000510.SH': '中证A500', '930050.CSI': '中证A50',
                     '000016.SH': '上证50', '399006.SZ': '创业板指', '399102.SZ': '创业板综',
                     '000688.SH': '科创50', '000698.SH': '科创100', '000680.SH': '科创综指',
                     '000681.SH': '科创综合价格', '000001.SH': '上证综指', '000906.SH': '中证800'}


def _zizeng_map_index(benchmark):
    for kw, code in ZIZENG_INDEX_MAP:
        if kw in (benchmark or ''):
            return code
    return None


def _zizeng_is_broad(benchmark):
    """宽基（规模类）判定：benchmark 命中宽基关键字清单。MSCI A50 等 map 值为 None 的也算宽基。"""
    bm = benchmark or ''
    return any(kw in bm for kw in ZIZENG_BROAD_KEYWORDS)


def _zizeng_index_basic(pro, trade_date):
    """指数名录（CSI/SSE/SZSE 三市场 index_basic），周五刷新，缓存复用；失败回退旧缓存。"""
    basic = None
    try:
        with open(ZIZENG_INDEX_BASIC_CACHE, encoding='utf-8') as f:
            basic = json.load(f)
    except Exception:
        basic = None
    if basic is None or datetime.strptime(trade_date, '%Y%m%d').weekday() == 4:
        items = []
        for mk in ['CSI', 'SSE', 'SZSE']:
            try:
                time.sleep(API_DELAY)
                ib = pro.index_basic(market=mk, fields='ts_code,name,category')
                if ib is not None and len(ib):
                    items.extend(ib.to_dict('records'))
            except Exception as e:
                print(f"  Warning: zizeng index_basic {mk} failed: {e}")
        if items:
            basic = {'fetched': trade_date, 'items': items}
            os.makedirs(os.path.dirname(ZIZENG_INDEX_BASIC_CACHE), exist_ok=True)
            with open(ZIZENG_INDEX_BASIC_CACHE, 'w', encoding='utf-8') as f:
                json.dump(basic, f, ensure_ascii=False)
    return (basic or {}).get('items') or []


def _zizeng_match_sector_index(ib_items, benchmark):
    """板块/主题/策略 benchmark → 指数 ts_code。

    benchmark 形如 '中证医药主题指数收益率×95%+活期存款…'：截取'收益率'/'×'前为核心名，
    去掉尾部'指数'后在名录中找 名称相等 / 名称+指数相等 / 互为包含 的最长匹配。
    解析不到返回 None（该只剔除并计数披露）。
    """
    bm = benchmark or ''
    for sep in ['收益率', '×']:
        if sep in bm:
            bm = bm.split(sep)[0]
    core = bm.strip()
    if core.endswith('指数'):
        core = core[:-2]
    if not core or not ib_items:
        return None
    best, best_len = None, 0
    for r in ib_items:
        nm = str(r.get('name') or '').strip()
        if not nm:
            continue
        if nm == core or nm + '指数' == core or core in nm or nm in core:
            if len(nm) > best_len:
                best, best_len = r['ts_code'], len(nm)
    return best


def build_zizeng_etf(pro, trade_date, data):
    """板块指增 ETF 超额收益跟踪（2026-09-17 用户口径改：只保留行业/主题/策略指增，宽基全移出）。

    - 候选：fund_basic 名称含"增强"且 invest_type=增强指数型 的场内 ETF（fund_basic 周五周更，缓存复用）；
      宽基（规模类）指数关键字命中即剔除；板块指增的跟踪指数经 index_basic 名录（周五周更缓存）解析代码；
      规模 = 份额(fund_share) × 收盘(fund_daily) ≥ 2 亿。当前全市场板块指增 ETF 为 0 只（空态展示，
      名单周更，新上市板块指增自动入选）。
    - 超额 = 复权净值(adj_nav)涨幅 − 跟踪指数涨幅，近1月(21个交易日)/YTD 双档；
      YTD 基准 = 上一年最后一个净值日/交易日。
    - 份额变化：复用 fetch_nt_upgrade 的 etf cache snapshots（12 天全市场快照），零新增调用。
    - 折溢价 = 当日收盘 / 最新单位净值 - 1（净值 T+1 披露，输出带 nav_date 供前端注明）。
    每晚调用 ≈25 次：fund_basic 1(仅周五) + index_basic 3(仅周五且有板块候选时) + fund_daily 1
      + index_daily ≈指数种数 + fund_nav ≈入选只数。
    """
    y0 = str(int(trade_date[:4]) - 1)
    nav_start, ytd_base = f'{y0}1210', f'{y0}1231'

    # ── 1. fund_basic 周更（周五刷新 / 缓存缺失时刷新，失败回退旧缓存）──
    basic = None
    try:
        with open(ZIZENG_BASIC_CACHE, encoding='utf-8') as f:
            basic = json.load(f)
    except Exception:
        basic = None
    if basic is None or datetime.strptime(trade_date, '%Y%m%d').weekday() == 4:
        try:
            time.sleep(API_DELAY)
            fb_new = pro.fund_basic(market='E', status='L')
            if fb_new is not None and len(fb_new):
                basic = {'fetched': trade_date, 'items': fb_new.to_dict('records')}
                os.makedirs(os.path.dirname(ZIZENG_BASIC_CACHE), exist_ok=True)
                with open(ZIZENG_BASIC_CACHE, 'w', encoding='utf-8') as f:
                    json.dump(basic, f, ensure_ascii=False)
        except Exception as e:
            print(f"  Warning: zizeng fund_basic failed: {e}")
    if not basic:
        print("  Warning: zizeng basic unavailable, skip")
        return
    fb = pd.DataFrame(basic['items'])
    # 只要场内 ETF：fund_basic(market='E') 含 LOF，名称带 (LOF) 的一律剔除
    # （板块指增 LOF 存在，如 501089 消费红利/161035 医药主题，但非 ETF 且份额不可得，不计入）
    cand = fb[fb['name'].str.contains('增强', na=False)
              & (fb['invest_type'] == '增强指数型')
              & ~fb['name'].str.contains('LOF', na=False)].copy()
    # 2026-09-17 用户口径：剔除宽基（规模类），只保留行业/主题/策略指增
    cand['broad'] = cand['benchmark'].map(_zizeng_is_broad)
    broad_n = int(cand['broad'].sum())
    sector = cand[~cand['broad']].copy()
    # 板块指增跟踪指数代码：index_basic 名录解析（周五周更缓存；无候选时零调用）
    if len(sector):
        ib_items = _zizeng_index_basic(pro, trade_date)
        sector['idx_code'] = sector['benchmark'].map(
            lambda b: _zizeng_match_sector_index(ib_items, b))
    else:
        sector['idx_code'] = pd.Series(dtype=object)

    # ── 2. 份额（复用 etf cache 全市场快照）+ 收盘（同一日期配对）──
    cache = _etf_cache_load()
    snaps = cache.get('snapshots') or {}
    sdates = [d0 for d0 in sorted(snaps) if d0 <= trade_date]
    if not sdates:
        print("  Warning: zizeng no share snapshot, skip")
        return
    sd = sdates[-1]
    share_now = snaps[sd]
    share_5ago = snaps[sdates[-6]] if len(sdates) >= 6 else {}
    close_now = {}
    try:
        time.sleep(API_DELAY)
        df_fd = pro.fund_daily(trade_date=sd)
        if df_fd is not None and len(df_fd):
            close_now = dict(zip(df_fd['ts_code'], df_fd['close'].astype(float)))
    except Exception as e:
        print(f"  Warning: zizeng fund_daily failed: {e}")

    sector['scale'] = sector['ts_code'].map(
        lambda c: round(share_now.get(c, 0) * close_now.get(c, 0), 2))
    unresolved = sector[sector['idx_code'].isna()] if len(sector) else sector
    pool = sector[(sector['scale'] >= ZIZENG_MIN_SCALE) & sector['idx_code'].notna()].copy()
    if not len(pool):
        # 板块指增当前为 0 只（2026-09-17 实测）：空态落盘，绝不保留旧宽基数据
        data['zizengETF'] = {
            'trade_date': f"{sd[:4]}-{sd[4:6]}-{sd[6:]}",
            'nav_date': None,
            'items': [],
            'stats': {'total': 0, 'pass5': 0, 'medianYtd': None, 'posYtd': 0, 'validYtd': 0,
                      'candidates': len(cand), 'broad': broad_n,
                      'sectorPool': len(sector), 'unresolved': len(unresolved)},
            'note': ('口径（2026-09-17 用户指令改）：只跟踪行业/主题/策略指数的增强指数型场内 ETF（板块指增），'
                     '宽基指增（沪深300/中证500/中证1000/中证2000/中证A500/上证50/科创/创业板等规模指数）已全部移出，'
                     '指数增强 LOF 非 ETF 亦不计入；'
                     '规模=份额×收盘，入选门槛≥2亿（≥5亿=达标）；超额=复权净值涨幅−跟踪指数涨幅'
                     '（未含指数股息，全收益口径超额会再低1-3点/年），近1月=21个交易日，YTD基准=上年末；'
                     '净值T+1披露；基金名单每周五刷新，新上市的板块指增 ETF 将自动入选'),
        }
        print(f"  zizengETF: 板块指增 0 只（候选 {len(cand)} 只均为宽基，已移出），空态展示")
        return

    # ── 3. 跟踪指数行情（每只指数 1 次）──
    idx_ret = {}
    for ic in sorted(pool['idx_code'].unique()):
        try:
            time.sleep(API_DELAY)
            df = pro.index_daily(ts_code=ic, start_date=nav_start, end_date=trade_date)
            if df is None or not len(df):
                continue
            df = df.sort_values('trade_date')
            closes = list(df['close'].astype(float))
            base = df[df['trade_date'] <= ytd_base]
            r1m = closes[-1] / closes[-22] - 1 if len(closes) >= 22 else None
            rytd = closes[-1] / float(base.iloc[-1]['close']) - 1 if len(base) else None
            idx_ret[ic] = {'r1m': r1m, 'rytd': rytd}
        except Exception as e:
            print(f"  Warning: zizeng index {ic} failed: {e}")

    # ── 4. 逐只基金复权净值（T+1 披露，记录 nav_date）──
    idx_name_map = {r['ts_code']: str(r.get('name') or '') for r in (ib_items if len(sector) else [])}
    items, nav_dates = [], []
    for _, f in pool.iterrows():
        try:
            time.sleep(API_DELAY)
            nav = pro.fund_nav(ts_code=f['ts_code'], start_date=nav_start, end_date=trade_date)
        except Exception as e:
            print(f"  Warning: zizeng nav {f['ts_code']} failed: {e}")
            continue
        if nav is None or not len(nav):
            continue
        nav = nav.sort_values('nav_date')
        adj = list(nav['adj_nav'].astype(float))
        nav_dates.append(str(nav.iloc[-1]['nav_date']))
        base = nav[nav['nav_date'] <= ytd_base]
        r1m = adj[-1] / adj[-22] - 1 if len(adj) >= 22 else None
        rytd = adj[-1] / float(base.iloc[-1]['adj_nav']) - 1 if len(base) else None
        ir = idx_ret.get(f['idx_code']) or {}
        ex1m = round((r1m - ir['r1m']) * 100, 2) if r1m is not None and ir.get('r1m') is not None else None
        exytd = round((rytd - ir['rytd']) * 100, 2) if rytd is not None and ir.get('rytd') is not None else None
        s_now = share_now.get(f['ts_code'])
        s_5 = share_5ago.get(f['ts_code'])
        share5 = round((s_now / s_5 - 1) * 100, 2) if s_now and s_5 else None
        unit_nav = nav.iloc[-1]['unit_nav']
        cl = close_now.get(f['ts_code'])
        prem = round((cl / float(unit_nav) - 1) * 100, 2) if cl and pd.notna(unit_nav) and float(unit_nav) > 0 else None
        fee = round(float(f['m_fee'] or 0) + float(f['c_fee'] or 0), 2)
        items.append({
            'code': f['ts_code'].split('.')[0], 'tsCode': f['ts_code'], 'name': f['name'],
            'idx': idx_name_map.get(f['idx_code']) or ZIZENG_INDEX_NAME.get(f['idx_code'], f['idx_code']),
            'scale': f['scale'], 'fee': fee, 'share5Pct': share5, 'premiumPct': prem,
            'r1m': round(r1m * 100, 2) if r1m is not None else None,
            'i1m': round(ir['r1m'] * 100, 2) if ir.get('r1m') is not None else None,
            'ex1m': ex1m,
            'rytd': round(rytd * 100, 2) if rytd is not None else None,
            'iytd': round(ir['rytd'] * 100, 2) if ir.get('rytd') is not None else None,
            'exytd': exytd, 'list': f.get('list_date'),
        })
    items.sort(key=lambda r: (r['exytd'] is None, -(r['exytd'] or -999)))
    if not items:
        print("  Warning: zizeng items empty, skip")
        return

    valid = [r['exytd'] for r in items if r['exytd'] is not None]
    med = round(sorted(valid)[len(valid) // 2], 2) if valid else None
    data['zizengETF'] = {
        'trade_date': f"{sd[:4]}-{sd[4:6]}-{sd[6:]}",
        'nav_date': f"{max(nav_dates)[:4]}-{max(nav_dates)[4:6]}-{max(nav_dates)[6:]}" if nav_dates else None,
        'items': items,
        'stats': {'total': len(items), 'pass5': sum(1 for r in items if r['scale'] >= 5),
                  'medianYtd': med, 'posYtd': sum(1 for v in valid if v > 0), 'validYtd': len(valid),
                  'candidates': len(cand), 'broad': broad_n,
                  'sectorPool': len(sector), 'unresolved': len(unresolved)},
        'note': ('口径（2026-09-17 用户指令改）：只跟踪行业/主题/策略指数的增强指数型场内 ETF（板块指增），'
                 f"宽基指增已全部移出（本周剔除 {broad_n} 只，宽基关键字或指数名录判定）；"
                 '超额=复权净值涨幅−跟踪指数涨幅（未含指数股息，全收益口径超额会再低1-3点/年）；'
                 '近1月=21个交易日，YTD基准=上年末；规模=份额×收盘（≥5亿=达标）；'
                 '净值T+1披露，折溢价=当日收盘/最新单位净值−1（存在口径时差，仅供参考）；'
                 '基金名单每周五刷新，新上市的板块指增 ETF 将自动入选'),
    }
    print(f"  zizengETF: {len(items)} 只（≥5亿 {data['zizengETF']['stats']['pass5']}），"
          f"YTD超额中位 {med}%，净值日 {data['zizengETF']['nav_date']}")


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

    # ── 0. 第三步自动收录观察股（2026-09-30 用户指令：累计入选≥5日 cache 驱动并入 STOCKS）──
    apply_step3_auto_watch()

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

    # ── 7. Hot fund NAVs：已停用并删除字段（2026-10-01 死字段清理：hotFundNavs 前端无渲染消费，
    #        fetch_hot_fund_navs 函数体一并删除，省 fund_nav 逐只调用/日）──

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

    # ── 10b. 两融汇总 / 南向持股集中度（Tushare 日更）──
    fetch_margin_summary(pro, trade_date, data)
    fetch_southbound_concentration(pro, trade_date, data)
    # fetch_leverage_concentration 已停用（2026-10-01 用户指令）：杠杆资金控盘集中度TOP10 卡下线，
    # 该函数只喂那张卡，停用省 3 次 Tushare 调用/日（margin_detail+daily_basic+stock_basic）。
    # 函数体保留未删；fund_data.json 存量 leverage_concentration_top10 静态残留无害（前端不再渲染）。

    # ── 10c. CCASS 外资托管持股月末快照（HKEX SDW；月底/月初双触发，SDW 失败只标缺失不断流）──
    try:
        fetch_ccass_foreign(pro, trade_date, data)
    except Exception as e:
        print(f"  Warning: ccassForeign failed (keep old): {e}")

    # ── 10d. 外资机构权益披露增减仓（披露易 DI 大股东申报；每日增量，失败只标缺失不断流）──
    try:
        fetch_di_foreign(pro, trade_date, data)
    except Exception as e:
        print(f"  Warning: diForeign failed (keep old): {e}")

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

    # ── 16b. 个股级形态精扫（六指数池，日线+周线双级别，VCP/杯柄/平台/旗形多形态）──
    print("\n[16b/17] Building stock-level pattern scan (vcpStocks)...")
    _today_map = watch_ctx[3] if watch_ctx else {}
    fetch_vcp_stocks(pro, trade_date, data, _today_map)

    # ── 16b2. 个股半年对抗统计（持仓+观察股 vs 上证综指/所属行业板块）──
    print("\n[16b2/17] Building stock RS battle stats (stockRS)...")
    try:
        fetch_stock_rs(pro, trade_date, data)
    except Exception as e:
        print(f"  Warning: stockRS failed: {e}")

    # ── 16c. 总览并联双轴（趋势轴∥短线轴）+ 宽基趋势/VCP + 第4步排雷 ──
    print("\n[16c/17] Building dual axes (trend/short) + broad watch + mine watch...")
    try:
        build_broad_watch(pro, trade_date, data)
    except Exception as e:
        print(f"  Warning: broadWatch failed: {e}")
    try:
        build_dual_axes(pro, trade_date, data, _today_map)
    except Exception as e:
        print(f"  Warning: dualAxes failed: {e}")
    try:
        build_mine_watch(pro, trade_date, data)
    except Exception as e:
        print(f"  Warning: mineWatch failed: {e}")

    # ── 17. 宽基升级：份额雷达 + 板块轮动 + 宽基波动率 + 短评 ──
    print("\n[17/17] Building national team upgrade (share radar / rotation / est / vol)...")
    fetch_nt_upgrade(pro, trade_date, data)

    # ── 17b. 指增 ETF 跟踪（宽基栏目第六卡；份额复用 nt 快照）──
    try:
        build_zizeng_etf(pro, trade_date, data)
    except Exception as e:
        print(f"  Warning: zizengETF failed: {e}")

    # ── 17c. 做多窗口判定（大级别门控：水温×宽基形态，改版③）──
    try:
        build_long_window(data)
    except Exception as e:
        print(f"  Warning: longWindow failed: {e}")

    # ── 17c2. 板块聪明钱超额榜（45只主动基金×12板块；每晚净值增量45次，周五+份额周更）──
    try:
        fetch_sector_smart_money(pro, trade_date, data)
    except Exception as e:
        print(f"  Warning: sectorSmartMoney failed: {e}")

    # ── 17c3. 板块每日涨幅轮动榜（sector_history 零新增调用；🔥过热因子供漏斗第2步降权）──
    try:
        update_em_board_snapshot(trade_date)   # 东财第二口径当日快照（失败优雅跳过，Actions 积累）
    except Exception as e:
        print(f"  Warning: emBoardSnapshot failed: {e}")
    try:
        build_sector_rotation(data)
    except Exception as e:
        print(f"  Warning: sectorRotation failed: {e}")

    # ── 17d. 总览五步漏斗结论汇总（2026-09-27 改版第二波，纯汇总零新增调用）──
    try:
        build_funnel(data)
    except Exception as e:
        print(f"  Warning: funnel failed: {e}")

    # ── 17e. 第三步入选历史记录（每日名单入 cache + selDays 回写漏斗行；2026-09-30 用户指令）──
    update_step3_history(data)

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
