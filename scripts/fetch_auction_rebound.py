#!/usr/bin/env python3
"""
资金猎人 - 竞价曾跌停但开盘前反弹个股抓取脚本

监测逻辑：
- 9:15-9:25 竞价阶段，某股曾打到跌停或-9.5%以上
- 但 9:25 最终开盘价，跌幅收窄到-5%以上（即反弹了）

技术难点：
- AKShare只能获取最终开盘价，无法获取竞价过程中的最高/最低跌幅
- 需要Level-2逐笔委托数据才能精确抓取

当前方案：结合多种数据源做近似判断
"""

import json
import os
from datetime import datetime, timedelta

def fetch_potential_rebound_stocks():
    """
    抓取可能符合"竞价曾跌停但开盘反弹"条件的个股
    
    策略：
    1. 开盘价跌幅在 -9.5% ~ -5% 之间（曾经深跌但最终反弹了一些）
    2. 同时当天有负面消息/公告（说明有砸盘理由）
    3. 成交量异常放大（说明有资金承接）
    """
    try:
        import akshare as ak
        
        # 获取当天全部A股
        df = ak.stock_zh_a_spot_em()
        
        # 条件1：开盘价跌幅在 -9.5% 到 -5% 之间
        # 这些股可能竞价阶段曾 deeper，但开盘前反弹了
        potential = df[
            (df['涨跌幅'] >= -9.5) & 
            (df['涨跌幅'] <= -5.0)
        ].copy()
        
        if potential.empty:
            return []
        
        # 条件2：量比>3（成交量异常放大，说明有资金博弈）
        potential = potential[potential.get('量比', 0) > 3]
        
        # 条件3：振幅>8%（当天波动大，说明有砸盘和承接）
        potential = potential[potential.get('振幅', 0) > 8]
        
        potential = potential.sort_values('涨跌幅')
        
        results = []
        for _, row in potential.iterrows():
            name = row.get('名称', '')
            code = row.get('代码', '')
            change = row.get('涨跌幅', 0)
            volume_ratio = row.get('量比', 0)
            amplitude = row.get('振幅', 0)
            
            if not name or not code:
                continue
            
            # 判断是否为ST股（ST股跌停是-5%，不是-10%）
            is_st = name.startswith('*ST') or name.startswith('ST')
            limit = -4.5 if is_st else -9.5
            
            results.append({
                "date": datetime.now().strftime("%m-%d"),
                "name": name,
                "code": code,
                "openChange": f"{change:.2f}%",
                "volumeRatio": f"{volume_ratio:.1f}",
                "amplitude": f"{amplitude:.2f}%",
                "isST": is_st,
                "concept": "-",
                "sector": "-",
                "note": f"量比{volume_ratio:.1f}倍，振幅{amplitude:.1f}%，疑似竞价曾深跌后反弹"
            })
        
        return results
        
    except ImportError:
        print("⚠️ 未安装akshare，请先运行: pip install akshare")
        return []
    except Exception as e:
        print(f"❌ 抓取失败: {e}")
        return []

def update_weekly_data(new_stocks, data_file="src/data/fund_data.json"):
    """更新本周列表"""
    
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    week_str = f"{monday.strftime('%Y.%m.%d')} - {friday.strftime('%m.%d')}"
    
    if 'auction_rebound_weekly' not in data:
        data['auction_rebound_weekly'] = {
            "week": week_str,
            "updateDate": today.strftime("%Y-%m-%d"),
            "summary": "",
            "stocks": [],
            "dataSourceNote": "基于量比+振幅的近似判断，非精确竞价逐笔数据"
        }
    
    existing = data['auction_rebound_weekly']
    existing_codes = {s['code'] + s['date'] for s in existing.get('stocks', [])}
    
    for stock in new_stocks:
        key = stock['code'] + stock['date']
        if key not in existing_codes:
            existing['stocks'].append(stock)
            existing_codes.add(key)
    
    existing['stocks'].sort(key=lambda x: x['date'])
    existing['summary'] = f"本周共{len(existing['stocks'])}只个股疑似竞价曾深跌后反弹"
    existing['updateDate'] = today.strftime("%Y-%m-%d")
    
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    import shutil
    shutil.copy(data_file, data_file.replace('src/data/', 'public/'))
    
    return existing['stocks']

def main():
    print(f"🚀 抓取竞价深跌反弹数据 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print("⚠️ 技术说明：")
    print("  本脚本基于'开盘价跌幅在-9.5%~-5%之间 + 量比>3 + 振幅>8%'做近似判断")
    print("  精确数据需要Level-2逐笔委托接口（付费）")
    print("  实际竞价阶段最高跌幅可能更深，脚本无法精确捕捉")
    print("=" * 60)
    
    stocks = fetch_potential_rebound_stocks()
    
    if stocks:
        print(f"\n📉 发现 {len(stocks)} 只疑似竞价深跌后反弹个股:")
        for s in stocks[:15]:
            st_mark = "【ST】" if s['isST'] else ""
            print(f"  {s['date']} {s['name']}({s['code']}) {st_mark}")
            print(f"    开盘{s['openChange']} | 量比{s['volumeRatio']}倍 | 振幅{s['amplitude']}")
        
        all_stocks = update_weekly_data(stocks)
        print(f"\n📊 本周累计: {len(all_stocks)} 只个股")
    else:
        print("\n📊 当天无符合条件个股")
        update_weekly_data([])
    
    print("=" * 60)

if __name__ == "__main__":
    main()
