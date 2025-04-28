"""
缓存系统测试脚本 - 用于测试不同的缓存模式
"""
import sys
import os
from datetime import datetime, timedelta
from colorama import Fore, Style, init

# 初始化colorama
init(autoreset=True)

# 导入所需模块
from data.database import (
    init_db, set_cache_mode, get_cache_mode, 
    is_db_enabled, is_redis_enabled
)
from data.cache import init_cache, get_cache
from data.cache_manager import get_cache_manager
from tools.api import get_prices, refresh_data

def test_cache_modes():
    """测试不同的缓存模式"""
    print(f"{Fore.CYAN}=== 缓存模式测试 ==={Style.RESET_ALL}")
    
    # 测试SQLite模式
    print(f"\n{Fore.YELLOW}测试 SQLite 缓存模式:{Style.RESET_ALL}")
    set_cache_mode('sqlite')
    init_db()
    init_cache()
    
    cache_mode = get_cache_mode()
    print(f"当前缓存模式: {Fore.GREEN}{cache_mode}{Style.RESET_ALL}")
    print(f"SQLite 数据库已启用: {Fore.GREEN if is_db_enabled() else Fore.RED}{is_db_enabled()}{Style.RESET_ALL}")
    print(f"Redis 已启用: {Fore.GREEN if is_redis_enabled() else Fore.RED}{is_redis_enabled()}{Style.RESET_ALL}")
    
    # 测试数据获取和保存
    ticker = "AAPL"
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    print(f"\n{Fore.YELLOW}测试数据获取和保存 ({ticker}, {start_date} 至 {end_date}):{Style.RESET_ALL}")
    
    # 使用API刷新数据（会自动保存到缓存）
    print(f"刷新价格数据...")
    refresh_success = refresh_data('prices', ticker, start_date=start_date, end_date=end_date)
    print(f"刷新结果: {Fore.GREEN if refresh_success else Fore.RED}{refresh_success}{Style.RESET_ALL}")
    
    # 使用API刷新新闻数据
    print(f"刷新新闻数据...")
    refresh_success = refresh_data('company_news', ticker, start_date=start_date, end_date=end_date)
    print(f"刷新结果: {Fore.GREEN if refresh_success else Fore.RED}{refresh_success}{Style.RESET_ALL}") 
    
    # 从缓存读取数据
    print(f"从缓存读取价格数据...")
    cache = get_cache()
    cached_prices = cache.get_prices(ticker, start_date=start_date, end_date=end_date)
    print(f"缓存中的价格数据条数: {Fore.GREEN}{len(cached_prices)}{Style.RESET_ALL}")
    
    if cached_prices:
        print(f"首条记录: {cached_prices[0]['time']} - 收盘价: {cached_prices[0]['close']}")
        print(f"末条记录: {cached_prices[-1]['time']} - 收盘价: {cached_prices[-1]['close']}")
    
    # 测试缓存管理器
    print(f"\n{Fore.YELLOW}测试缓存管理器:{Style.RESET_ALL}")
    cache_manager = get_cache_manager()
    stats = cache_manager.get_data_stats(ticker)
    
    print(f"缓存统计信息:")
    for data_type, data_stats in stats.items():
        count = data_stats.get('count', 0)
        print(f"  {data_type}: {Fore.GREEN if count > 0 else Fore.RED}{count} 条记录{Style.RESET_ALL}")
        if count > 0 and 'earliest_date' in data_stats:
            print(f"    日期范围: {data_stats['earliest_date']} 至 {data_stats['latest_date']}")

def main():
    print(f"{Fore.CYAN}开始测试缓存系统...{Style.RESET_ALL}")
    
    try:
        test_cache_modes()
        print(f"\n{Fore.GREEN}测试完成！{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}测试过程中发生错误: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 