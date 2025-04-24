#!/usr/bin/env python
import os
import argparse
import logging
from typing import List

# 设置日志
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_database():
    """初始化数据库和Redis连接"""
    from data.database import init_db
    from data.cache import init_cache
    
    # 初始化数据库
    init_db()
    logger.info("数据库表已创建")
    
    # 初始化缓存
    init_cache()
    logger.info("缓存系统已初始化")
    
    return True

def migrate_memory_cache(tickers: List[str]):
    """将内存缓存迁移到持久化存储"""
    import json
    from pathlib import Path
    from data.cache import get_cache
    
    cache = get_cache()
    
    # 如果指定了tickers，则只迁移这些股票的数据
    if not tickers:
        logger.info("未指定股票代码，将尝试迁移所有缓存数据")
    else:
        logger.info(f"将迁移以下股票的数据: {', '.join(tickers)}")
    
    # 检查是否有保存的缓存文件
    cache_dir = Path("./cache")
    if not cache_dir.exists():
        logger.info("未找到缓存目录，跳过迁移")
        return
    
    migrated_count = 0
    
    # 处理价格数据
    for cache_file in cache_dir.glob("prices_*.json"):
        try:
            ticker = cache_file.stem.split("_")[1]
            if tickers and ticker not in tickers:
                continue
            
            with open(cache_file, "r") as f:
                data = json.load(f)
                
            if data:
                cache.set_prices(ticker, data, force_update=True)
                logger.info(f"已迁移 {ticker} 的价格数据: {len(data)} 条记录")
                migrated_count += 1
        except Exception as e:
            logger.error(f"迁移价格数据时出错 ({cache_file.name}): {e}")
    
    # 处理财务指标数据
    for cache_file in cache_dir.glob("metrics_*.json"):
        try:
            ticker = cache_file.stem.split("_")[1]
            if tickers and ticker not in tickers:
                continue
            
            with open(cache_file, "r") as f:
                data = json.load(f)
                
            if data:
                cache.set_financial_metrics(ticker, data, force_update=True)
                logger.info(f"已迁移 {ticker} 的财务指标数据: {len(data)} 条记录")
                migrated_count += 1
        except Exception as e:
            logger.error(f"迁移财务指标数据时出错 ({cache_file.name}): {e}")
    
    # 处理内部交易数据
    for cache_file in cache_dir.glob("insider_trades_*.json"):
        try:
            ticker = cache_file.stem.split("_")[2]
            if tickers and ticker not in tickers:
                continue
            
            with open(cache_file, "r") as f:
                data = json.load(f)
                
            if data:
                cache.set_insider_trades(ticker, data, force_update=True)
                logger.info(f"已迁移 {ticker} 的内部交易数据: {len(data)} 条记录")
                migrated_count += 1
        except Exception as e:
            logger.error(f"迁移内部交易数据时出错 ({cache_file.name}): {e}")
    
    # 处理公司新闻数据
    for cache_file in cache_dir.glob("news_*.json"):
        try:
            ticker = cache_file.stem.split("_")[1]
            if tickers and ticker not in tickers:
                continue
            
            with open(cache_file, "r") as f:
                data = json.load(f)
                
            if data:
                cache.set_company_news(ticker, data, force_update=True)
                logger.info(f"已迁移 {ticker} 的公司新闻数据: {len(data)} 条记录")
                migrated_count += 1
        except Exception as e:
            logger.error(f"迁移公司新闻数据时出错 ({cache_file.name}): {e}")
    
    if migrated_count > 0:
        logger.info(f"已成功迁移 {migrated_count} 个缓存文件")
    else:
        logger.info("没有找到可迁移的缓存文件")

def main():
    """主函数，解析命令行参数并执行相应操作"""
    parser = argparse.ArgumentParser(description="数据库初始化和缓存迁移工具")
    parser.add_argument("--init", action="store_true", help="初始化数据库")
    parser.add_argument("--migrate", action="store_true", help="迁移内存缓存到持久化存储")
    parser.add_argument("--tickers", nargs="+", help="指定要处理的股票代码（用于迁移）")
    
    args = parser.parse_args()
    
    if args.init:
        setup_database()
    
    if args.migrate:
        migrate_memory_cache(args.tickers)
    
    if not args.init and not args.migrate:
        parser.print_help()

if __name__ == "__main__":
    main() 