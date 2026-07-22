#!/usr/bin/env python3
"""
资金猎人 - 每周竞价跌停/接近跌停个股抓取脚本
每周五收盘后运行，抓取本周一到周五竞价阶段跌幅≥9.5%的个股

数据来源：东方财富 AKShare
"""

import json
import os
from datetime import datetime, timedelta

def fetch_today_auction_limit_down():
    """
    抓取当天（运行日）竞价跌停或跌幅超9.5%的个股
    需要安装：pip install akshare
    """
    try:
        import akshare as ak
        
        # 获取当天全部A股实时行情（含开盘价、涨跌幅）
        df = ak.stock_zh_a_spot_em()
        
        # 筛选条件：
        # 1. 涨跌幅 <= -9.5%（跌停或接近跌停）
        # 2. 排除ST/ST*/*ST（如果需要保留则删除这行）
        limit_down = df[df['涨跌幅'] <= -9.5].copy()
        
        if limit_down.empty:
            return []
        
        # 按跌幅排序
        limit_down = limit_down.sort_values('涨跌幅')
        
        results = []
        for _, row in limit_down.iterrows():
            name = row.get('名称', '')
            code = row.get('代码', '')
            change = row.get('涨跌幅', 0)
            
            # 跳过无效数据
            if not name or not code:
                continue
                
            results.append({
                "date": datetime.now().strftime("%m-%d"),
                "name": name,
                "code": code,
                "auctionChange": f"{change:.2f}%",
                "openChange": f"{change:.2f}%",  # 实时行情近似
                "concept": "-",  # 需要另外补充
                "sector": "-",   # 需要另外补充
                "reason": "-"    # 需要人工标注
            })
        
        return results
        
    except ImportError:
        print("⚠️ 未安装akshare，请先运行: pip install akshare")
        return []
    except Exception as e:
        print(f"❌ 抓取失败: {e}")
        return []

def update_weekly_data(new_stocks, data_file="src/data/fund_data.json"):
    """将新抓取的数据追加到本周列表中"""
    
    # 读取现有数据
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 获取当前周的日期范围（周一到周五）
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    week_str = f"{monday.strftime('%Y.%m.%d')} - {friday.strftime('%m.%d')}"
    
    # 如果已有本周数据，追加新个股（去重）
    if 'auction_limit_down_weekly' not in data:
        data['auction_limit_down_weekly'] = {
            "week": week_str,
            "updateDate": today.strftime("%Y-%m-%d"),
            "summary": "",
            "stocks": []
        }
    
    existing = data['auction_limit_down_weekly']
    existing_codes = {s['code'] + s['date'] for s in existing.get('stocks', [])}
    
    for stock in new_stocks:
        key = stock['code'] + stock['date']
        if key not in existing_codes:
            existing['stocks'].append(stock)
            existing_codes.add(key)
    
    # 按日期排序
    existing['stocks'].sort(key=lambda x: x['date'])
    existing['summary'] = f"本周共{len(existing['stocks'])}只个股出现竞价跌停或跌幅超9.5%"
    existing['updateDate'] = today.strftime("%Y-%m-%d")
    
    # 写回文件
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 同步到public
    import shutil
    shutil.copy(data_file, data_file.replace('src/data/', 'public/'))
    
    print(f"✅ 已更新: 本周共{len(existing['stocks'])}只个股")
    return existing['stocks']

def main():
    print(f"🚀 抓取竞价跌停数据 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    stocks = fetch_today_auction_limit_down()
    
    if stocks:
        print(f"📉 当天发现 {len(stocks)} 只竞价跌停/接近跌停个股:")
        for s in stocks[:10]:  # 最多显示10只
            print(f"  {s['date']} {s['name']}({s['code']}) {s['auctionChange']}")
        
        # 更新到数据文件
        all_stocks = update_weekly_data(stocks)
        print(f"\n📊 本周累计: {len(all_stocks)} 只个股")
    else:
        print("📊 当天无竞价跌停/接近跌停个股")
        # 仍然更新summary
        update_weekly_data([])
    
    print("=" * 50)

if __name__ == "__main__":
    main()
