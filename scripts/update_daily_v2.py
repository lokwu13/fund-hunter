#!/usr/bin/env python3
"""
资金猎人 - 每日自动更新脚本 v2
执行时间: 每天16:40 (A股收盘后)
数据源: Tushare Pro
更新范围: 只更新日频数据（指数/个股/资金/主力/keySignals），不动季频/周频
"""

import json
import os
import sys
from datetime import datetime

# === 安装依赖 ===
try:
    import tushare as ts
    import pandas as pd
except ImportError:
    os.system(f"{sys.executable} -m pip install tushare pandas -q")
    import tushare as ts
    import pandas as pd

# === 配置 ===
TUSHARE_TOKEN = '28c8451ed0b7ce55dbc6d73e2933019727dd55a44c4df8b3fde2a2ae'
DATA_URL = "https://tuud54yjtew3e.ok.kimi.link/fund_data.json"
DATA_FILE = os.path.expanduser('~/kimi-projects/fund-hunter/data/fund_data.json')
BACKUP_DIR = os.path.expanduser('~/kimi-projects/fund-hunter/data/backup/')

pro = ts.pro_api(TUSHARE_TOKEN)

# ============================================================
# 全局名称映射（只查一次，避免重复API调用）
# ============================================================
print("[准备] 加载股票名称映射...")

# A股
_df_a = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name,industry')
A_NAME_MAP = dict(zip(_df_a['ts_code'], _df_a['name']))
A_INDUSTRY_MAP = dict(zip(_df_a['ts_code'], _df_a['industry']))

# 港股
_df_hk = pro.hk_basic()
HK_NAME_MAP = dict(zip(_df_hk['ts_code'], _df_hk['name']))

print(f"  A股: {len(A_NAME_MAP)} 只, 港股: {len(HK_NAME_MAP)} 只")


def get_name(code):
    """获取股票名称（A股或港股）"""
    if code.endswith(('.SZ', '.SH')):
        return A_NAME_MAP.get(code, code)
    elif code.endswith('.HK'):
        return HK_NAME_MAP.get(code, code)
    return code


def get_industry(code):
    """获取行业（A股返回行业，港股返回'港股'）"""
    if code.endswith(('.SZ', '.SH')):
        return A_INDUSTRY_MAP.get(code, '')
    elif code.endswith('.HK'):
        return '港股'
    return ''


def format_amount(amount_yuan):
    """金额格式化（元→亿/万）"""
    if amount_yuan >= 100000000:
        return f"+{amount_yuan/100000000:.1f}亿"
    elif amount_yuan >= 10000:
        return f"+{amount_yuan/10000:.0f}万"
    else:
        return f"+{amount_yuan:.0f}元"


def format_amount_negative(amount_yuan):
    """金额格式化（负值）"""
    if abs(amount_yuan) >= 100000000:
        return f"{amount_yuan/100000000:.1f}亿"
    elif abs(amount_yuan) >= 10000:
        return f"{amount_yuan:.0f}万"
    else:
        return f"{amount_yuan:.1f}万"


# ============================================================
# 升级自检机制
# ============================================================
class DataValidator:
    """数据完整性验证器"""
    
    REQUIRED_FIELDS = [
        'updateTime', 'week', 'marketStatus', 'indices', 'sectors', 'stocks',
        'northbound', 'southbound', 'keySignals', 'foreignSummary',
        'combined_sell_top10', 'leverage_concentration_top10', 'medicalSectorFunds',
        'southbound_concentration_top10', 'foreign_concentration_top10',
        'top10_foreign', 'foreignInstitution_top10', 'divergence_top10',
        'dataSources', 'top5_national', 'top10_publicfund', 'publicFund_outflow_top10',
        'concentration_top10', 'mainforce_inflow_top10', 'mainforce_outflow_top10',
        'privateFund_inflow', 'privateFund_outflow', 'sectorPeriod',
        'conceptSectors', 'bondData'
    ]
    
    ARRAY_FIELDS = {
        'sectors': 18, 'conceptSectors': 15, 'stocks': 19, 'keySignals': 4,
        'top10_publicfund': 10, 'mainforce_inflow_top10': 10, 'mainforce_outflow_top10': 10,
        'concentration_top10': 10, 'privateFund_inflow': 5, 'privateFund_outflow': 5,
        'combined_sell_top10': 10, 'leverage_concentration_top10': 10,
        'southbound_concentration_top10': 10, 'foreign_concentration_top10': 10,
        'top10_foreign': 10, 'divergence_top10': 10,
        'top5_national': 5, 'publicFund_outflow_top10': 10,
        'mainforce_inflow_top10': 10, 'mainforce_outflow_top10': 10,
    }
    
    @staticmethod
    def validate(data):
        errors = []
        
        # 1. 字段完整性
        for field in DataValidator.REQUIRED_FIELDS:
            if field not in data:
                errors.append(f"❌ 缺失字段: {field}")
        
        # 2. 数组非空且数量正确
        for field, expected_len in DataValidator.ARRAY_FIELDS.items():
            arr = data.get(field)
            if not isinstance(arr, list):
                errors.append(f"❌ {field} 不是数组")
            elif len(arr) == 0:
                errors.append(f"❌ {field} 为空数组")
            elif len(arr) != expected_len:
                errors.append(f"⚠️ {field} 数量异常: {len(arr)} (期望{expected_len})")
        
        # 3. concept 不能全是 "-"
        for field in ['mainforce_inflow_top10', 'mainforce_outflow_top10', 'top10_publicfund', 
                      'concentration_top10', 'top10_foreign']:
            arr = data.get(field, [])
            all_dash = all(item.get('concept') == '-' for item in arr)
            if all_dash:
                errors.append(f"❌ {field} concept 全部为 '-'")
            elif any(item.get('concept') == '-' for item in arr):
                errors.append(f"⚠️ {field} 部分 concept 为 '-'")
        
        # 4. 金额异常检查
        for field in ['mainforce_inflow_top10', 'mainforce_outflow_top10']:
            arr = data.get(field, [])
            for item in arr:
                amt = item.get('amount', '')
                if amt in ['-0万', '0.0亿', '0万', '+0万']:
                    errors.append(f"❌ {field} {item.get('name')}: 金额异常 '{amt}'")
        
        # 5. 港股混入检查（A股列表中不应有.HK）
        for field in ['top10_publicfund', 'concentration_top10']:
            arr = data.get(field, [])
            hk_items = [item for item in arr if item.get('code', '').endswith('.HK')]
            if hk_items:
                names = [i['name'] for i in hk_items]
                errors.append(f"⚠️ {field} 包含港股(预期A+H都有则正常): {names}")
        
        # 6. 指数合理性
        sh = data.get('indices', {}).get('shIndex', {})
        if sh.get('value', 0) < 1000 or sh.get('value', 0) > 10000:
            errors.append(f"❌ 上证指数异常: {sh.get('value')}")
        
        return errors


# ============================================================
# 主程序
# ============================================================
def main():
    print("=" * 60)
    print("资金猎人 - 每日自动更新 v2")
    print("=" * 60)
    
    today = datetime.now().strftime('%Y%m%d')
    today_display = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    # === 1. 下载现有数据 ===
    print("\n[1/8] 下载现有数据...")
    import urllib.request
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    urllib.request.urlretrieve(DATA_URL, DATA_FILE)
    
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"  当前数据: {data.get('updateTime', 'N/A')}")
    
    # === 2. 备份 ===
    print("\n[2/8] 备份数据...")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup = os.path.join(BACKUP_DIR, f"fund_data_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    with open(backup, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"  备份: {backup}")
    
    # === 3. 更新指数 ===
    print("\n[3/8] 更新指数...")
    for key, ts_code in [('shIndex','000001.SH'),('szIndex','399001.SZ'),
                          ('hs300','000300.SH'),('cyIndex','399006.SZ')]:
        try:
            df = pro.index_daily(ts_code=ts_code, start_date=today, end_date=today)
            if not df.empty:
                data['indices'][key]['value'] = round(float(df.iloc[0]['close']), 2)
                data['indices'][key]['change'] = round(float(df.iloc[0]['pct_chg']), 2)
                print(f"  ✅ {data['indices'][key]['name']}: {data['indices'][key]['value']}")
        except Exception as e:
            print(f"  ⏳ {key}: {e}")
    
    # 恒生
    try:
        df = pro.hk_daily(ts_code='HSI.HK', start_date=today, end_date=today)
        if not df.empty:
            data['indices']['hsi']['value'] = round(float(df.iloc[0]['close']), 2)
            data['indices']['hsi']['change'] = round(float(df.iloc[0]['pct_chg']), 2)
            print(f"  ✅ 恒生: {data['indices']['hsi']['value']}")
    except Exception as e:
        print(f"  ⏳ 恒生: {e}")
    
    # === 4. 更新个股 ===
    print("\n[4/8] 更新个股...")
    updated = 0
    for stock in data['stocks']:
        code = stock['code']
        try:
            df = pro.daily(ts_code=code, start_date=today, end_date=today) if not code.endswith('.HK') else pro.hk_daily(ts_code=code, start_date=today, end_date=today)
            if not df.empty:
                stock['close'] = round(float(df.iloc[0]['close']), 2)
                stock['pctChg'] = round(float(df.iloc[0]['pct_chg']), 2)
                updated += 1
        except:
            pass
    print(f"  更新 {updated}/{len(data['stocks'])} 只")
    
    # === 5. 更新北向/南向 ===
    print("\n[5/8] 更新北向/南向资金...")
    try:
        df = pro.moneyflow_hsgt(start_date=today, end_date=today)
        if not df.empty:
            data['northbound']['today'] = round(float(df.iloc[0]['north_money'])/10000, 2)
            data['southbound']['today'] = round(float(df.iloc[0]['south_money'])/10000, 2)
            print(f"  ✅ 北向:{data['northbound']['today']}亿 南向:{data['southbound']['today']}亿")
        else:
            print(f"  ⏳ 当日数据未同步")
    except Exception as e:
        print(f"  ⏳ {e}")
    
    # === 6. 更新主力资金 ===
    print("\n[6/8] 更新主力资金日频...")
    try:
        df_mf = pro.moneyflow(trade_date=today)
        df_mf['net_mf_amount'] = df_mf['net_mf_amount'].astype(float)
        
        # 流入TOP10
        inflow = []
        for _, row in df_mf.nlargest(10, 'net_mf_amount').iterrows():
            code = row['ts_code']
            amt = row['net_mf_amount']
            industry = get_industry(code)
            inflow.append({
                'name': get_name(code), 'code': code,
                'concept': industry or '-', 'sector': industry or '-',
                'amount': format_amount(amt)
            })
        
        # 流出TOP10
        outflow = []
        for _, row in df_mf.nsmallest(10, 'net_mf_amount').iterrows():
            code = row['ts_code']
            amt = row['net_mf_amount']
            industry = get_industry(code)
            amt_str = format_amount_negative(amt)
            if amt_str in ['-0万', '0.0亿']:
                amt_str = f"{amt:.1f}万"
            outflow.append({
                'name': get_name(code), 'code': code,
                'concept': industry or '-', 'sector': industry or '-',
                'amount': amt_str
            })
        
        data['mainforce_inflow_top10'] = inflow
        data['mainforce_outflow_top10'] = outflow
        print(f"  ✅ 流入:{inflow[0]['name']} {inflow[0]['amount']}")
        print(f"  ✅ 流出:{outflow[0]['name']} {outflow[0]['amount']}")
    except Exception as e:
        print(f"  ⏳ {e}")
    
    # === 7. 更新keySignals ===
    print("\n[7/8] 更新关键信号...")
    sh = data['indices']['shIndex']
    cy = data['indices']['cyIndex']
    signals = []
    
    if sh['change'] > 0.5: signals.append({'type':'info','text':f"上证指数今日收涨{sh['change']}%，大盘强势。"})
    elif sh['change'] < -0.5: signals.append({'type':'warning','text':f"上证指数今日收跌{abs(sh['change'])}%，大盘承压。"})
    else: signals.append({'type':'info','text':f"上证指数今日波动{sh['change']}%，大盘震荡。"})
    
    if cy['change'] > 1: signals.append({'type':'caution','text':f"创业板指今日大涨{cy['change']}%，科技股活跃。"})
    elif cy['change'] < -1: signals.append({'type':'caution','text':f"创业板指今日大跌{abs(cy['change'])}%，科技股回调。"})
    else: signals.append({'type':'info','text':f"创业板指今日波动{cy['change']}%，科技股分化。"})
    
    for stock in data['stocks']:
        if stock.get('name') in ['心脉医疗','恒瑞医药','南微医学','上海机场']:
            pct = stock.get('pctChg',0)
            if abs(pct) > 2:
                signals.append({'type':'caution','text':f"{stock['name']}今日{'大涨' if pct>0 else '大跌'}{abs(pct)}%，收盘价{stock['close']}元。"})
                break
    
    nb = data['northbound'].get('today',0)
    if nb > 50: signals.append({'type':'info','text':f"北向资金今日净流入{nb}亿，外资积极做多。"})
    elif nb < -20: signals.append({'type':'warning','text':f"北向资金今日净流出{abs(nb)}亿，外资流出明显。"})
    
    while len(signals) < 4: signals.append({'type':'info','text':'市场正常交易，建议关注持仓个股基本面变化。'})
    data['keySignals'] = signals[:4]
    print(f"  ✅ {len(signals)} 条信号")
    
    # === 8. 自检 ===
    print("\n[8/8] 数据完整性检查...")
    errors = DataValidator.validate(data)
    if errors:
        for e in errors:
            print(f"  {e}")
        print("\n⚠️ 检查发现异常，请检查日志")
    else:
        print("  ✅ 全部通过")
    
    # 更新元数据
    data['updateTime'] = f"{today_display}（Tushare实时）"
    data['week'] = f"{datetime.now().strftime('%Y.%m.%d - ')}{(datetime.now() + __import__('datetime').timedelta(days=4-datetime.now().weekday())).strftime('%m.%d')}" if datetime.now().weekday() < 5 else data.get('week', '')
    data['marketStatus'] = '正常交易'
    
    # 保存
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n[完成] 数据已保存")
    print(f"[时间] {today_display}")


if __name__ == '__main__':
    main()
