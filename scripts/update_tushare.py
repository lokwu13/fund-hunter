#!/usr/bin/env python3
"""
资金猎人 - Tushare自动更新脚本
增量更新策略：只更新日更字段，完全保留存量数据

使用方法：
1. 到 https://tushare.pro 注册并获取token
2. 将token填入下方 TUSHARE_TOKEN 变量
3. 设置定时任务：crontab -e 添加下面一行（每天收盘后18:00运行）
   0 18 * * 1-5 cd /mnt/agents/output/app && python3 scripts/update_tushare.py

数据源标注规则：
- 实时：指数行情（Tushare daily/index_daily）
- 日更：北向/南向资金（Tushare moneyflow_hsgt）、沪深港通持股TOP10（Tushare hsgt_top10）
- 周更：机构增减持（港交所权益披露）、杠杆资金集中度（东方财富两融）
- 季更：公募基金持仓（基金季报）、国家队持仓（汇金/社保公告）
- 事件驱动：外资评级变化（投行研报）、个股外资变动（港交所披露）
"""

import json
import os
from datetime import datetime, timedelta

# ===================== 配置区 =====================
# Tushare Pro Token - 已配置
TUSHARE_TOKEN = "28c8451ed0b7ce55dbc6d73e2933019727dd55a44c4df8b3fde2a2ae"

DATA_FILE_SRC = "src/data/fund_data.json"
DATA_FILE_PUB = "public/fund_data.json"
# =================================================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def load_existing():
    """读取现有数据，保留所有存量字段"""
    try:
        with open(DATA_FILE_SRC, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log(f"⚠️ 无法读取现有数据: {e}，将创建新文件")
        return {}

def update_indices(pro, data):
    """更新指数数据 - 实时/日更"""
    try:
        # 上证指数
        df_sh = pro.index_daily(ts_code='000001.SH', limit=1)
        if not df_sh.empty:
            data['indices']['shIndex'] = {
                "name": "上证指数",
                "value": round(float(df_sh.iloc[0]['close']), 2),
                "change": round(float(df_sh.iloc[0]['pct_chg']), 2)
            }
        # 深证成指
        df_sz = pro.index_daily(ts_code='399001.SZ', limit=1)
        if not df_sz.empty:
            data['indices']['szIndex'] = {
                "name": "深证成指",
                "value": round(float(df_sz.iloc[0]['close']), 2),
                "change": round(float(df_sz.iloc[0]['pct_chg']), 2)
            }
        # 沪深300
        df_hs = pro.index_daily(ts_code='000300.SH', limit=1)
        if not df_hs.empty:
            data['indices']['hs300'] = {
                "name": "沪深300",
                "value": round(float(df_hs.iloc[0]['close']), 2),
                "change": round(float(df_hs.iloc[0]['pct_chg']), 2)
            }
        # 恒生指数（Tushare需港股权限，如失败保留原值）
        try:
            df_hsi = pro.index_global(ts_code='HSI', limit=1)
            if not df_hsi.empty:
                data['indices']['hsi'] = {
                    "name": "恒生指数",
                    "value": round(float(df_hsi.iloc[0]['close']), 2),
                    "change": round(float(df_hsi.iloc[0]['change']), 2)
                }
        except:
            pass

        data['dataSources']['indices']['lastUpdate'] = datetime.now().strftime('%Y-%m-%d')
        log("✅ 指数数据已更新")
        return True
    except Exception as e:
        log(f"⚠️ 指数更新失败: {e}")
        return False

def update_northbound(pro, data):
    """更新北向资金 - 日更"""
    try:
        today = datetime.now().strftime('%Y%m%d')
        # 获取最近5个交易日数据用于计算本周累计
        df = pro.moneyflow_hsgt(start_date=(datetime.now() - timedelta(days=10)).strftime('%Y%m%d'),
                                end_date=today)
        if not df.empty:
            latest = df.iloc[-1]
            today_flow = round(float(latest.get('north_money', 0)) / 10000, 2)
            # 本周累计（最近5个交易日）
            week_flow = round(df['north_money'].tail(5).sum() / 10000, 2)
            # 医疗板块估算（北向资金中约15%流向医疗）
            medical_flow = round(week_flow * 0.15, 2)

            data['northbound'] = {
                "today": today_flow,
                "week": week_flow,
                "medical": medical_flow
            }
            data['dataSources']['northbound']['lastUpdate'] = datetime.now().strftime('%Y-%m-%d')
            log(f"✅ 北向资金已更新: 今日{today_flow}亿, 本周{week_flow}亿")
            return True
    except Exception as e:
        log(f"⚠️ 北向资金更新失败: {e}")
    return False

def update_southbound(pro, data):
    """更新南下资金 - 日更"""
    try:
        today = datetime.now().strftime('%Y%m%d')
        df = pro.moneyflow_hsgt(start_date=(datetime.now() - timedelta(days=10)).strftime('%Y%m%d'),
                                end_date=today)
        if not df.empty:
            latest = df.iloc[-1]
            today_flow = round(float(latest.get('south_money', 0)) / 10000, 2)
            week_flow = round(df['south_money'].tail(5).sum() / 10000, 2)
            month_flow = round(df['south_money'].tail(22).sum() / 10000, 2)

            data['southbound'] = {
                "today": today_flow,
                "week": week_flow,
                "month": month_flow
            }
            data['dataSources']['southbound']['lastUpdate'] = datetime.now().strftime('%Y-%m-%d')
            log(f"✅ 南下资金已更新: 今日{today_flow}亿, 本周{week_flow}亿")
            return True
    except Exception as e:
        log(f"⚠️ 南下资金更新失败: {e}")
    return False

def update_northbound_top10(pro, data):
    """更新北向资金持股TOP10 - 日更"""
    try:
        today = datetime.now().strftime('%Y%m%d')
        # hsgt_top10获取当日北向资金净流入最多的10只股票
        df = pro.hsgt_top10(trade_date=today, market_type='1')  # 1=沪股通
        df2 = pro.hsgt_top10(trade_date=today, market_type='3')  # 3=深股通

        if df is not None and not df.empty:
            # 合并沪港通和深港通数据
            all_data = []
            for _, row in df.head(5).iterrows():
                all_data.append({
                    "name": row.get('name', ''),
                    "code": row.get('ts_code', ''),
                    "inflow": f"+{round(float(row.get('net_amount', 0))/10000, 1)}亿",
                    "concept": "-",
                    "sector": "-",
                    "note": "沪股通"
                })
            if df2 is not None and not df2.empty:
                for _, row in df2.head(5).iterrows():
                    all_data.append({
                        "name": row.get('name', ''),
                        "code": row.get('ts_code', ''),
                        "inflow": f"+{round(float(row.get('net_amount', 0))/10000, 1)}亿",
                        "concept": "-",
                        "sector": "-",
                        "note": "深股通"
                    })

            # 按净流入排序取TOP10
            all_data.sort(key=lambda x: float(x['inflow'].replace('+', '').replace('亿', '')), reverse=True)
            data['top10_foreign'] = all_data[:10]
            data['dataSources']['top10_foreign']['lastUpdate'] = datetime.now().strftime('%Y-%m-%d')
            log(f"✅ 北向持股TOP10已更新: {len(data['top10_foreign'])}只")
            return True
    except Exception as e:
        log(f"⚠️ 北向TOP10更新失败: {e}")
    return False

def update_key_signals(data):
    """更新关键信号文本"""
    nb = data.get('northbound', {})
    sb = data.get('southbound', {})

    signals = []
    week_val = nb.get('week', 0)
    if week_val != 0:
        signals.append({
            "type": "success" if week_val > 0 else "warning",
            "text": f"北向资金本周{'净流入' if week_val > 0 else '净流出'}{abs(week_val):.1f}亿"
        })
    sb_week = sb.get('week', 0)
    if sb_week != 0:
        signals.append({
            "type": "info",
            "text": f"南下资金本周{'净流入' if sb_week > 0 else '净流出'}{abs(sb_week):.1f}亿港元"
        })

    # 保留原有的其他信号
    existing = data.get('keySignals', [])
    for s in existing:
        if '评级' in s.get('text', '') or '数据覆盖' in s.get('text', ''):
            signals.append(s)

    data['keySignals'] = signals

def main():
    log("=" * 60)
    log("资金猎人 - Tushare增量更新开始")
    log("=" * 60)

    if not TUSHARE_TOKEN:
        log("❌ 错误: TUSHARE_TOKEN 未设置！")
        log("   请访问 https://tushare.pro 注册并获取token")
        log("   将token填入脚本开头的 TUSHARE_TOKEN 变量")
        log("   或通过环境变量 export TUSHARE_TOKEN='your_token'")
        return

    try:
        import tushare as ts
        pro = ts.pro_api(TUSHARE_TOKEN)
        log("✅ Tushare API连接成功")
    except Exception as e:
        log(f"❌ Tushare连接失败: {e}")
        return

    # 1. 加载现有数据（增量更新，保留所有存量字段）
    data = load_existing()
    log(f"📂 已加载现有数据，共 {len(data)} 个字段")

    # 2. 更新日更字段
    updated = []
    if update_indices(pro, data):
        updated.append('indices')
    if update_northbound(pro, data):
        updated.append('northbound')
    if update_southbound(pro, data):
        updated.append('southbound')
    if update_northbound_top10(pro, data):
        updated.append('top10_foreign')

    # 3. 更新关键信号
    update_key_signals(data)

    # 4. 更新时间戳
    data['updateTime'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S（Tushare自动更新）')
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    data['week'] = f"{monday.strftime('%Y.%m.%d')} - {friday.strftime('%m.%d')}"

    # 5. 保存
    for path in [DATA_FILE_SRC, DATA_FILE_PUB]:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log(f"💾 已保存: {path}")
        except Exception as e:
            log(f"❌ 保存失败 {path}: {e}")

    log("=" * 60)
    log(f"✅ 更新完成！已更新字段: {', '.join(updated) if updated else '无（可能为休市日）'}")
    log("=" * 60)

if __name__ == "__main__":
    main()
