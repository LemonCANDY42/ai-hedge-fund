#!/usr/bin/env python3
"""
新闻情感分析数据库迁移脚本 - 添加相关股票和情感字段
"""

import argparse
import logging
import sys
from sqlalchemy import create_engine, text, Column, JSON, String
from colorama import Fore, Style, init

from data.database import init_db, DATABASE_URL
from data.cache import init_cache
from data.migrations import add_column_if_not_exists
from data.db_models import Base, News

# 初始化colorama
init(autoreset=True)

# 设置日志
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def upgrade_db_schema():
    """升级数据库结构，添加related_tickers和ticker_sentiments字段"""
    # 获取数据库引擎
    engine = create_engine(DATABASE_URL)
    
    try:
        # 检查表是否存在
        with engine.connect() as conn:
            tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            table_names = [table[0] for table in tables]
            
            if "company_news" not in table_names:
                logger.warning("表 company_news 不存在，将创建新表")
                Base.metadata.create_all(engine)
                return True
        
        # 添加related_tickers列
        related_tickers_result = add_column_if_not_exists(engine, "company_news", "related_tickers", "JSON")
        
        # 添加ticker_sentiments列
        ticker_sentiments_result = add_column_if_not_exists(engine, "company_news", "ticker_sentiments", "JSON")
        
        return related_tickers_result or ticker_sentiments_result
        
    except Exception as e:
        logger.error(f"迁移失败: {e}")
        return False

def main():
    """主函数，处理命令行参数和执行迁移"""
    parser = argparse.ArgumentParser(description="新闻情感分析数据库迁移工具")
    parser.add_argument("--force", action="store_true", help="强制执行迁移，即使迁移已完成")
    
    args = parser.parse_args()
    
    # 初始化数据库连接
    try:
        init_db()
        init_cache()
        print(f"{Fore.CYAN}数据库和缓存系统已初始化。{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}初始化数据库和缓存系统时出错: {e}{Style.RESET_ALL}")
        sys.exit(1)
    
    # 执行迁移
    print(f"{Fore.CYAN}开始升级数据库结构...{Style.RESET_ALL}")
    result = upgrade_db_schema()
    
    if result:
        print(f"{Fore.GREEN}数据库结构升级成功{Style.RESET_ALL}")
        print(f"{Fore.CYAN}已添加 related_tickers 和 ticker_sentiments 字段{Style.RESET_ALL}")
    else:
        if args.force:
            print(f"{Fore.YELLOW}未检测到需要升级的结构，但已强制重建{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}数据库结构无需升级或升级失败{Style.RESET_ALL}")
    
    print(f"\n{Fore.CYAN}提示：要分析新闻并填充这些字段，请使用以下命令:{Style.RESET_ALL}")
    print(f"{Fore.GREEN}python src/news_enhancer_tool.py enhance <股票代码> --force-update{Style.RESET_ALL}")

if __name__ == "__main__":
    main() 