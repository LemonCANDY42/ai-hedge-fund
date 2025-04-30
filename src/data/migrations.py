#!/usr/bin/env python3
"""
数据库迁移工具 - 用于执行架构变更
"""

import argparse
import logging
import sys
from sqlalchemy import create_engine, Column, String, text
from sqlalchemy.exc import OperationalError

from data.database import DATABASE_URL
from data.db_models import Base

# 设置日志
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_url():
    """获取数据库URL"""
    return DATABASE_URL

def add_column_if_not_exists(engine, table_name, column_name, column_type):
    """添加列到表中（如果该列不存在）"""
    # 检查列是否存在
    with engine.connect() as conn:
        inspector = conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns = inspector.fetchall()
        column_names = [column[1] for column in columns]
        
        if column_name not in column_names:
            logger.info(f"正在向表 {table_name} 添加列 {column_name}...")
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
            logger.info(f"列 {column_name} 添加成功")
            return True
        else:
            logger.info(f"列 {column_name} 已存在于表 {table_name} 中")
            return False

def upgrade_news_author_field():
    """升级News表，添加author字段"""
    # 获取数据库URL
    db_url = get_db_url()
    
    # 创建数据库引擎
    engine = create_engine(db_url)
    
    try:
        # 检查表是否存在
        with engine.connect() as conn:
            tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            table_names = [table[0] for table in tables]
            
            if "company_news" not in table_names:
                logger.warning("表 company_news 不存在，无需迁移")
                return False
        
        # 添加author列
        result = add_column_if_not_exists(engine, "company_news", "author", "VARCHAR(128)")
        return result
        
    except Exception as e:
        logger.error(f"迁移失败: {e}")
        return False

def add_related_tickers_field():
    """升级News表，添加related_tickers字段"""
    # 获取数据库URL
    db_url = get_db_url()
    
    # 创建数据库引擎
    engine = create_engine(db_url)
    
    try:
        # 检查表是否存在
        with engine.connect() as conn:
            tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            table_names = [table[0] for table in tables]
            
            if "company_news" not in table_names:
                logger.warning("表 company_news 不存在，无需迁移")
                return False
        
        # 添加related_tickers列
        result = add_column_if_not_exists(engine, "company_news", "related_tickers", "JSON")
        return result
        
    except Exception as e:
        logger.error(f"添加related_tickers字段失败: {e}")
        return False

def add_ticker_sentiments_field():
    """升级News表，添加ticker_sentiments字段"""
    # 获取数据库URL
    db_url = get_db_url()
    
    # 创建数据库引擎
    engine = create_engine(db_url)
    
    try:
        # 检查表是否存在
        with engine.connect() as conn:
            tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            table_names = [table[0] for table in tables]
            
            if "company_news" not in table_names:
                logger.warning("表 company_news 不存在，无需迁移")
                return False
        
        # 添加ticker_sentiments列
        result = add_column_if_not_exists(engine, "company_news", "ticker_sentiments", "JSON")
        return result
        
    except Exception as e:
        logger.error(f"添加ticker_sentiments字段失败: {e}")
        return False

def main():
    """主函数，处理命令行参数和执行迁移"""
    parser = argparse.ArgumentParser(description="数据库迁移工具")
    parser.add_argument("--upgrade", action="store_true", help="升级数据库结构")
    
    args = parser.parse_args()
    
    if args.upgrade:
        logger.info("开始升级数据库结构...")
        
        # 升级News表添加author字段
        news_result = upgrade_news_author_field()
        
        # 添加新的相关股票和情感字段
        related_tickers_result = add_related_tickers_field()
        ticker_sentiments_result = add_ticker_sentiments_field()
        
        if news_result or related_tickers_result or ticker_sentiments_result:
            logger.info("数据库结构升级成功")
        else:
            logger.info("数据库结构无需升级或升级失败")
            
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 