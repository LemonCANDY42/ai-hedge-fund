"""
缓存系统使用示例

本示例展示了如何使用多级缓存系统来高效地存储和检索金融数据。
"""

import os
import sys
import time
from datetime import datetime, timedelta
import random

# 添加父目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 配置环境变量（这里仅用于演示，实际使用时通常在环境中设置）
# os.environ["CACHE_MODE"] = "full"  # 可选: "full", "redis", "memory", "none"
# os.environ["DATABASE_URL"] = "sqlite:///./example_data.db"
# os.environ["REDIS_URL"] = "redis://localhost:6379/0"

from data.cache import get_cache, init_cache
from data.database import get_cache_mode, is_db_enabled, is_redis_enabled

def generate_mock_price_data(ticker, days=30):
    """生成模拟价格数据用于示例"""
    data = []
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # 初始价格
    last_close = random.uniform(100, 500)
    
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() < 5:  # 只在工作日
            # 生成每日价格变动（-2%到+2%）
            change_pct = random.uniform(-0.02, 0.02)
            open_price = last_close
            close_price = open_price * (1 + change_pct)
            high_price = max(open_price, close_price) * (1 + random.uniform(0, 0.01))
            low_price = min(open_price, close_price) * (1 - random.uniform(0, 0.01))
            volume = int(random.uniform(500000, 5000000))
            
            data.append({
                "ticker": ticker,
                "time": current_date.strftime("%Y-%m-%dT%H:%M:%S"),
                "open": open_price,
                "close": close_price,
                "high": high_price,
                "low": low_price,
                "volume": volume
            })
            
            last_close = close_price
        
        current_date += timedelta(days=1)
    
    return data

def demo_cache_operations():
    """演示缓存系统的基本操作"""
    # 初始化缓存系统
    cache = init_cache()
    
    # 打印当前缓存模式
    print(f"当前缓存模式: {get_cache_mode()}")
    print(f"数据库启用状态: {is_db_enabled()}")
    print(f"Redis启用状态: {is_redis_enabled()}")
    print("-" * 50)
    
    # 测试股票列表
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
    
    # 1. 保存模拟数据到缓存系统
    print("生成并保存模拟数据...")
    for ticker in tickers:
        mock_data = generate_mock_price_data(ticker)
        print(f"保存 {ticker} 的 {len(mock_data)} 条价格数据")
        cache.set_prices(ticker, mock_data)
    print("-" * 50)
    
    # 2. 从缓存系统读取数据
    print("从缓存读取数据:")
    start_time = time.time()
    for ticker in tickers:
        data = cache.get_prices(ticker)
        print(f"{ticker}: 获取到 {len(data)} 条价格记录")
    first_read_time = time.time() - start_time
    print(f"首次读取耗时: {first_read_time:.4f} 秒")
    print("-" * 50)
    
    # 3. 再次读取数据以测试缓存效果
    print("再次从缓存读取数据:")
    start_time = time.time()
    for ticker in tickers:
        data = cache.get_prices(ticker)
        print(f"{ticker}: 获取到 {len(data)} 条价格记录")
    second_read_time = time.time() - start_time
    print(f"第二次读取耗时: {second_read_time:.4f} 秒")
    print(f"性能提升: {(first_read_time/second_read_time if second_read_time > 0 else 'N/A')}x")
    print("-" * 50)
    
    # 4. 测试日期范围过滤
    ticker = tickers[0]
    start_date = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")
    print(f"读取 {ticker} 的指定日期范围数据 ({start_date} 到 {end_date}):")
    filtered_data = cache.get_prices(ticker, start_date=start_date, end_date=end_date)
    print(f"获取到 {len(filtered_data)} 条记录")
    print("-" * 50)
    
    # 5. 更新现有数据
    print("更新现有数据:")
    today = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    update_data = [{
        "ticker": ticker,
        "time": today,
        "open": 150.0,
        "close": 155.0,
        "high": 156.0, 
        "low": 149.0,
        "volume": 1000000
    }]
    cache.set_prices(ticker, update_data)
    updated_data = cache.get_prices(ticker, start_date=today.split("T")[0])
    print(f"更新后的数据: {updated_data}")
    
    return cache

def demo_multi_level_cache():
    """演示多级缓存系统的行为"""
    # 在不同缓存模式下运行示例
    cache_modes = ["full", "redis", "memory", "none"]
    
    for mode in cache_modes:
        print(f"\n{'='*20} 测试缓存模式: {mode} {'='*20}")
        os.environ["CACHE_MODE"] = mode
        
        # 清空现有缓存实例
        import data.cache as cache_module
        cache_module._cache = None
        
        # 运行演示
        try:
            demo_cache_operations()
        except Exception as e:
            print(f"在 {mode} 模式下出现错误: {e}")

if __name__ == "__main__":
    # 如果仅使用当前配置模式
    demo_cache_operations()
    
    # 测试所有缓存模式行为
    # demo_multi_level_cache() 