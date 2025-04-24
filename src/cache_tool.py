#!/usr/bin/env python
"""
命令行工具用于管理金融数据缓存和持久存储
"""
import argparse
import logging
import sys
from datetime import datetime, timedelta
from colorama import Fore, Style, init

from data.cache import init_cache
from data.database import init_db
from data.cache_manager import get_cache_manager
from tools.api import refresh_data, check_and_fill_data

# 初始化colorama
init(autoreset=True)

# 设置日志
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def initialize_db():
    """初始化数据库和Redis连接"""
    try:
        init_db()
        init_cache()
        print(f"{Fore.GREEN}数据库和缓存系统已初始化{Style.RESET_ALL}")
        return True
    except Exception as e:
        print(f"{Fore.RED}初始化失败: {e}{Style.RESET_ALL}")
        return False

def refresh_ticker(args):
    """刷新指定股票的数据"""
    if not args.ticker:
        print(f"{Fore.RED}错误: 必须指定股票代码{Style.RESET_ALL}")
        return False
        
    # 解析日期
    end_date = args.end_date or datetime.now().strftime("%Y-%m-%d")
    
    if not args.start_date:
        # 默认为过去3个月
        start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=90)).strftime("%Y-%m-%d")
    else:
        start_date = args.start_date
    
    try:
        cache_manager = get_cache_manager()
        print(f"{Fore.CYAN}正在刷新 {args.ticker} 的数据...{Style.RESET_ALL}")
        
        if args.type:
            # 刷新特定类型的数据
            data_type = args.type
            data_params = {
                "ticker": args.ticker,
                "start_date": start_date,
                "end_date": end_date
            }
            
            if data_type == "prices":
                result = refresh_data(data_type, **data_params)
            elif data_type == "financial_metrics":
                result = refresh_data(data_type, ticker=args.ticker, end_date=end_date, period=args.period, limit=args.limit)
            elif data_type == "insider_trades":
                result = refresh_data(data_type, ticker=args.ticker, end_date=end_date, start_date=start_date, limit=args.limit)
            elif data_type == "company_news":
                result = refresh_data(data_type, ticker=args.ticker, end_date=end_date, start_date=start_date, limit=args.limit)
            else:
                print(f"{Fore.RED}错误: 不支持的数据类型 {data_type}{Style.RESET_ALL}")
                return False
                
            if result:
                print(f"{Fore.GREEN}成功刷新 {args.ticker} 的 {data_type} 数据{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}刷新 {args.ticker} 的 {data_type} 数据失败{Style.RESET_ALL}")
            
            return result
        else:
            # 刷新所有类型的数据
            results = cache_manager.refresh_ticker_data(args.ticker, start_date=start_date, end_date=end_date)
            success_count = sum(1 for status in results.values() if status)
            
            if success_count == len(results):
                print(f"{Fore.GREEN}成功刷新所有 {args.ticker} 的数据{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}部分刷新成功: {success_count}/{len(results)} 数据类型{Style.RESET_ALL}")
                
                # 显示详细状态
                for data_type, status in results.items():
                    status_color = Fore.GREEN if status else Fore.RED
                    print(f"  {status_color}{data_type}: {'成功' if status else '失败'}{Style.RESET_ALL}")
            
            return success_count > 0
    
    except Exception as e:
        print(f"{Fore.RED}刷新数据时出错: {e}{Style.RESET_ALL}")
        return False

def check_data(args):
    """检查股票数据的完整性"""
    if not args.ticker:
        print(f"{Fore.RED}错误: 必须指定股票代码{Style.RESET_ALL}")
        return False
        
    # 解析日期
    end_date = args.end_date or datetime.now().strftime("%Y-%m-%d")
    
    if not args.start_date:
        # 默认为过去3个月
        start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=90)).strftime("%Y-%m-%d")
    else:
        start_date = args.start_date
    
    try:
        cache_manager = get_cache_manager()
        print(f"{Fore.CYAN}正在检查 {args.ticker} 的数据统计...{Style.RESET_ALL}")
        
        # 获取数据统计
        stats = cache_manager.get_data_stats(args.ticker)
        
        # 显示统计信息
        for data_type, data_stats in stats.items():
            count = data_stats.get('count', 0)
            if count > 0:
                if data_type == 'prices':
                    earliest = data_stats.get('earliest_date', 'N/A')
                    latest = data_stats.get('latest_date', 'N/A')
                    print(f"  {Fore.GREEN}{data_type}: {count} 条记录 ({earliest} 至 {latest}){Style.RESET_ALL}")
                    
                    # 检查指定日期范围内的价格数据是否完整
                    if args.fill:
                        print(f"{Fore.CYAN}检查并填充 {args.ticker} 在 {start_date} 至 {end_date} 期间的缺失价格数据...{Style.RESET_ALL}")
                        _, missing_dates = cache_manager.fill_missing_price_data(args.ticker, start_date, end_date)
                        
                        if missing_dates:
                            print(f"{Fore.YELLOW}已填充 {len(missing_dates)} 个缺失的交易日数据{Style.RESET_ALL}")
                            for date in sorted(missing_dates)[:5]:  # 只显示前5个
                                print(f"    - {date}")
                            if len(missing_dates) > 5:
                                print(f"    - ... 以及其他 {len(missing_dates) - 5} 个日期")
                        else:
                            print(f"{Fore.GREEN}数据完整，无需填充{Style.RESET_ALL}")
                    
                elif data_type == 'financial_metrics':
                    earliest = data_stats.get('earliest_period', 'N/A')
                    latest = data_stats.get('latest_period', 'N/A')
                    print(f"  {Fore.GREEN}{data_type}: {count} 条记录 ({earliest} 至 {latest}){Style.RESET_ALL}")
                elif data_type in ('insider_trades', 'company_news'):
                    earliest = data_stats.get('earliest_date', 'N/A')
                    latest = data_stats.get('latest_date', 'N/A')
                    print(f"  {Fore.GREEN}{data_type}: {count} 条记录 ({earliest} 至 {latest}){Style.RESET_ALL}")
                else:
                    print(f"  {Fore.GREEN}{data_type}: {count} 条记录{Style.RESET_ALL}")
            else:
                print(f"  {Fore.YELLOW}{data_type}: 无数据{Style.RESET_ALL}")
        
        return True
        
    except Exception as e:
        print(f"{Fore.RED}检查数据时出错: {e}{Style.RESET_ALL}")
        return False

def clear_cache(args):
    """清除Redis缓存（但保留数据库数据）"""
    if not args.ticker:
        print(f"{Fore.RED}错误: 必须指定股票代码或 'all'{Style.RESET_ALL}")
        return False
    
    try:
        cache_manager = get_cache_manager()
        
        if args.ticker.lower() == 'all':
            # 清除所有缓存
            # 这里我们需要从数据库获取所有股票代码
            print(f"{Fore.YELLOW}警告: 清除所有缓存功能尚未实现{Style.RESET_ALL}")
            return False
        else:
            # 清除指定股票的缓存
            print(f"{Fore.CYAN}正在清除 {args.ticker} 的Redis缓存...{Style.RESET_ALL}")
            result = cache_manager.clear_ticker_cache(args.ticker)
            
            if result:
                print(f"{Fore.GREEN}成功清除 {args.ticker} 的Redis缓存{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}清除 {args.ticker} 的Redis缓存失败{Style.RESET_ALL}")
            
            return result
    
    except Exception as e:
        print(f"{Fore.RED}清除缓存时出错: {e}{Style.RESET_ALL}")
        return False

def main():
    """主函数，解析命令行参数并执行相应操作"""
    parser = argparse.ArgumentParser(description="金融数据缓存管理工具")
    subparsers = parser.add_subparsers(dest="command", help="要执行的命令")
    
    # init命令
    init_parser = subparsers.add_parser("init", help="初始化数据库和缓存系统")
    
    # refresh命令
    refresh_parser = subparsers.add_parser("refresh", help="刷新指定股票的数据")
    refresh_parser.add_argument("ticker", help="股票代码")
    refresh_parser.add_argument("--type", choices=["prices", "financial_metrics", "insider_trades", "company_news"], 
                               help="指定要刷新的数据类型（默认刷新所有类型）")
    refresh_parser.add_argument("--start-date", help="开始日期 (YYYY-MM-DD)，默认为3个月前")
    refresh_parser.add_argument("--end-date", help="结束日期 (YYYY-MM-DD)，默认为今天")
    refresh_parser.add_argument("--period", default="ttm", choices=["ttm", "annual", "quarterly"], 
                               help="财务报告期间（仅适用于financial_metrics）")
    refresh_parser.add_argument("--limit", type=int, default=10, 
                               help="获取的记录数限制（仅适用于financial_metrics/insider_trades/company_news）")
    
    # check命令
    check_parser = subparsers.add_parser("check", help="检查股票数据的统计信息")
    check_parser.add_argument("ticker", help="股票代码")
    check_parser.add_argument("--start-date", help="开始日期 (YYYY-MM-DD)，默认为3个月前")
    check_parser.add_argument("--end-date", help="结束日期 (YYYY-MM-DD)，默认为今天")
    check_parser.add_argument("--fill", action="store_true", help="是否填充缺失的价格数据")
    
    # clear命令
    clear_parser = subparsers.add_parser("clear", help="清除Redis缓存")
    clear_parser.add_argument("ticker", help="股票代码或 'all' 表示所有")
    
    args = parser.parse_args()
    
    # 如果没有指定子命令，显示帮助信息
    if not args.command:
        parser.print_help()
        return
    
    # 确保数据库和缓存系统已初始化
    if args.command != "init":
        initialize_db()
    
    # 执行相应的命令
    if args.command == "init":
        initialize_db()
    elif args.command == "refresh":
        refresh_ticker(args)
    elif args.command == "check":
        check_data(args)
    elif args.command == "clear":
        clear_cache(args)

if __name__ == "__main__":
    main() 