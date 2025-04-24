import json
import logging
import pickle
from datetime import datetime
from functools import wraps
from typing import Any, Dict, List, Optional, Type, TypeVar, Callable, Union

from sqlalchemy.orm import Session
from sqlalchemy.sql import or_, and_

from data.database import (
    get_db, get_redis, generate_cache_key, REDIS_EXPIRATION,
    is_db_enabled, is_redis_enabled, get_cache_mode
)
import data.db_models as db_models

# 设置日志记录器
logger = logging.getLogger(__name__)

# 定义一个类型变量用于泛型函数
T = TypeVar('T')

# 内存缓存，当Redis不可用时使用
_memory_cache = {
    "prices": {},              # ticker -> list[dict]
    "financial_metrics": {},   # ticker -> list[dict]
    "line_items": {},          # ticker -> list[dict]
    "insider_trades": {},      # ticker -> list[dict]
    "company_news": {},        # ticker -> list[dict]
}

def with_db_session(func: Callable):
    """装饰器：提供数据库会话给函数"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not is_db_enabled():
            # 如果数据库已禁用，使用 None 作为 db 参数
            return func(*args, db=None, **kwargs)
            
        db_gen = get_db()
        db = next(db_gen)
        try:
            result = func(*args, db=db, **kwargs)
            return result
        finally:
            try:
                next(db_gen, None)
            except StopIteration:
                pass
    return wrapper

class PersistentCache:
    """持久化缓存系统 - 支持多种缓存模式
    
    该类提供了一个灵活的缓存系统:
    1. Redis + 数据库（完整持久化）
    2. 仅Redis（无持久存储）
    3. 内存缓存（回退模式）
    4. 无缓存（直接从API获取）
    """
    
    def __init__(self):
        """初始化缓存系统"""
        self.redis = get_redis()
        self.cache_mode = get_cache_mode()
        logger.info(f"缓存系统初始化，模式：{self.cache_mode}")
            
    def _redis_get(self, key: str) -> Optional[Any]:
        """从Redis获取数据
        
        Args:
            key: Redis键
            
        Returns:
            Optional[Any]: 反序列化后的数据，如果不存在则返回None
        """
        if not self.redis:
            return None
            
        try:
            data = self.redis.get(key)
            if data:
                return pickle.loads(data)
        except Exception as e:
            logger.warning(f"Redis读取错误: {e}")
        return None

    def _redis_set(self, key: str, value: Any, expire: int = REDIS_EXPIRATION) -> bool:
        """存储数据到Redis
        
        Args:
            key: Redis键
            value: 要存储的数据
            expire: 过期时间（秒）
            
        Returns:
            bool: 是否成功
        """
        if not self.redis:
            return False
            
        try:
            serialized = pickle.dumps(value)
            return bool(self.redis.set(key, serialized, ex=expire))
        except Exception as e:
            logger.warning(f"Redis写入错误: {e}")
            return False
    
    def _memory_get(self, cache_type: str, ticker: str, **filters) -> Optional[List[Dict]]:
        """从内存缓存获取数据
        
        Args:
            cache_type: 缓存类型 (prices, financial_metrics, etc.)
            ticker: 股票代码
            **filters: 其他过滤条件
            
        Returns:
            Optional[List[Dict]]: 缓存的数据，如果不存在则返回None
        """
        if ticker not in _memory_cache.get(cache_type, {}):
            return None
            
        data = _memory_cache[cache_type][ticker]
        
        # 应用过滤条件（简单实现，可能需要扩展）
        if "start_date" in filters and data:
            field = "time" if cache_type == "prices" else "date" if cache_type == "company_news" else "filing_date"
            if field in data[0]:
                start_date = filters["start_date"]
                data = [item for item in data if item.get(field, "").split("T")[0] >= start_date]
                
        if "end_date" in filters and data:
            field = "time" if cache_type == "prices" else "date" if cache_type == "company_news" else "filing_date" if cache_type == "insider_trades" else "report_period"
            if field in data[0]:
                end_date = filters["end_date"]
                data = [item for item in data if item.get(field, "").split("T")[0] <= end_date]
                
        if "limit" in filters and data:
            data = data[:filters["limit"]]
            
        return data if data else None
        
    def _memory_set(self, cache_type: str, ticker: str, data: List[Dict], key_field: str) -> bool:
        """存储数据到内存缓存
        
        Args:
            cache_type: 缓存类型
            ticker: 股票代码
            data: 要存储的数据
            key_field: 用于检测重复的字段
            
        Returns:
            bool: 是否成功
        """
        try:
            if cache_type not in _memory_cache:
                _memory_cache[cache_type] = {}
                
            if ticker not in _memory_cache[cache_type]:
                _memory_cache[cache_type][ticker] = []
                
            # 合并数据，避免重复
            _memory_cache[cache_type][ticker] = self._merge_data(
                _memory_cache[cache_type][ticker], 
                data, 
                key_field
            )
            return True
        except Exception as e:
            logger.warning(f"内存缓存写入错误: {e}")
            return False

    def _merge_data(self, existing: list[dict] | None, new_data: list[dict], key_field: str) -> list[dict]:
        """合并现有数据和新数据，避免基于关键字段的重复
        
        Args:
            existing: 现有数据列表
            new_data: 新数据列表
            key_field: 用于检测重复的字段
            
        Returns:
            list[dict]: 合并后的数据
        """
        if not existing:
            return new_data

        # 创建现有键的集合，用于O(1)查找
        existing_keys = {item[key_field] for item in existing}

        # 只添加尚不存在的项
        merged = existing.copy()
        merged.extend([item for item in new_data if item[key_field] not in existing_keys])
        return merged

    @with_db_session
    def get_prices(self, ticker: str, start_date: Optional[str] = None, end_date: Optional[str] = None, db: Session = None) -> List[Dict[str, Any]]:
        """获取价格数据，优先从缓存获取
        
        Args:
            ticker: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            db: 数据库会话
            
        Returns:
            List[Dict[str, Any]]: 价格数据列表
        """
        cache_key = None
        
        # 尝试从Redis缓存获取
        if self.redis:
            cache_key = generate_cache_key("prices", ticker=ticker, start_date=start_date, end_date=end_date)
            cached_data = self._redis_get(cache_key)
            if cached_data:
                return cached_data
        
        # 如果不在Redis中，尝试从内存缓存获取
        if self.cache_mode == "memory" and not is_db_enabled():
            memory_data = self._memory_get("prices", ticker, start_date=start_date, end_date=end_date)
            if memory_data:
                # 如果Redis可用，将内存数据写入Redis
                if self.redis and cache_key:
                    self._redis_set(cache_key, memory_data)
                return memory_data
                
        # 如果不在缓存中且数据库已启用，从数据库获取
        if db:
            query = db.query(db_models.Price).filter(db_models.Price.ticker == ticker)
            if start_date:
                query = query.filter(db_models.Price.time >= start_date)
            if end_date:
                query = query.filter(db_models.Price.time <= end_date)
            
            # 按时间排序
            db_results = query.order_by(db_models.Price.time).all()
            
            # 转换为字典列表
            results = []
            for item in db_results:
                result = {
                    'ticker': item.ticker,
                    'time': item.time,
                    'open': item.open,
                    'close': item.close,
                    'high': item.high,
                    'low': item.low,
                    'volume': item.volume
                }
                results.append(result)
            
            # 如果结果非空
            if results:
                # 存入Redis缓存（如果可用）
                if self.redis and cache_key:
                    self._redis_set(cache_key, results)
                    
                # 存入内存缓存（如果启用）
                if self.cache_mode == "memory":
                    self._memory_set("prices", ticker, results, "time")
                    
                return results
                
        # 如果不在数据库中且内存缓存已启用，返回一个空列表
        return []

    @with_db_session
    def set_prices(self, ticker: str, data: List[Dict[str, Any]], force_update: bool = False, db: Session = None) -> bool:
        """设置价格数据，同时更新缓存和数据库
        
        Args:
            ticker: 股票代码
            data: 价格数据列表
            force_update: 是否强制更新现有记录
            db: 数据库会话
            
        Returns:
            bool: 操作是否成功
        """
        if not data:
            return False
        
        # 更新内存缓存（如果启用）
        if self.cache_mode == "memory":
            self._memory_set("prices", ticker, data, "time")
            
        # 更新Redis缓存（如果可用）
        if self.redis:
            # 清除相关的Redis缓存
            pattern = f"prices:ticker:{ticker}*"
            try:
                for key in self.redis.scan_iter(pattern):
                    self.redis.delete(key)
            except Exception as e:
                logger.warning(f"清除Redis缓存时出错: {e}")
                
        # 如果数据库未启用，返回True（因为内存/Redis缓存已更新）
        if not db:
            return True
            
        try:
            # 遍历数据项并保存到数据库
            for item in data:
                time_val = item['time']
                
                # 查找现有记录
                existing = db.query(db_models.Price).filter(
                    db_models.Price.ticker == ticker,
                    db_models.Price.time == time_val
                ).first()
                
                if existing and not force_update:
                    # 记录已存在且不强制更新
                    continue
                    
                if existing:
                    # 更新现有记录
                    existing.open = item.get('open')
                    existing.close = item.get('close')
                    existing.high = item.get('high')
                    existing.low = item.get('low')
                    existing.volume = item.get('volume')
                    existing.updated_at = datetime.utcnow()
                else:
                    # 创建新记录
                    new_record = db_models.Price(
                        ticker=ticker,
                        time=time_val,
                        open=item.get('open'),
                        close=item.get('close'),
                        high=item.get('high'),
                        low=item.get('low'),
                        volume=item.get('volume')
                    )
                    db.add(new_record)
            
            # 提交事务
            db.commit()
            return True
            
        except Exception as e:
            if db:
                db.rollback()
            logger.error(f"保存价格数据时出错: {e}")
            return False
    
    @with_db_session
    def get_financial_metrics(self, ticker: str, end_date: Optional[str] = None, period: str = 'ttm', limit: int = 10, db: Session = None) -> List[Dict[str, Any]]:
        """获取财务指标数据，优先从缓存获取
        
        Args:
            ticker: 股票代码
            end_date: 结束日期
            period: 报告期间 (ttm, quarterly, etc.)
            limit: 最大返回记录数
            db: 数据库会话
            
        Returns:
            List[Dict[str, Any]]: 财务指标数据列表
        """
        cache_key = None
        
        # 尝试从Redis缓存获取
        if self.redis:
            cache_key = generate_cache_key("metrics", ticker=ticker, end_date=end_date, period=period, limit=limit)
            cached_data = self._redis_get(cache_key)
            if cached_data:
                return cached_data
        
        # 尝试从内存缓存获取
        if self.cache_mode == "memory" and not is_db_enabled():
            memory_data = self._memory_get("financial_metrics", ticker, end_date=end_date, limit=limit)
            if memory_data:
                # 过滤period
                memory_data = [item for item in memory_data if item.get("period") == period]
                if memory_data:
                    # 如果Redis可用，将内存数据写入Redis  
                    if self.redis and cache_key:
                        self._redis_set(cache_key, memory_data)
                    return memory_data
                
        # 从数据库获取
        if db:
            query = db.query(db_models.FinancialMetric).filter(
                db_models.FinancialMetric.ticker == ticker,
                db_models.FinancialMetric.period == period
            )
            
            if end_date:
                query = query.filter(db_models.FinancialMetric.report_period <= end_date)
                
            # 按报告期排序，最新的排在前面
            db_results = query.order_by(db_models.FinancialMetric.report_period.desc()).limit(limit).all()
            
            # 转换为字典列表
            results = []
            for item in db_results:
                # 将SQLAlchemy模型转换为字典
                item_dict = {c.name: getattr(item, c.name) for c in item.__table__.columns 
                            if not c.name.startswith('_') and c.name not in ('id', 'created_at', 'updated_at')}
                results.append(item_dict)
                
            # 存入Redis缓存
            if results and self.redis and cache_key:
                self._redis_set(cache_key, results)
                
            # 存入内存缓存
            if results and self.cache_mode == "memory":
                self._memory_set("financial_metrics", ticker, results, "report_period")
                
            return results
            
        return []

    @with_db_session
    def set_financial_metrics(self, ticker: str, data: List[Dict[str, Any]], force_update: bool = False, db: Session = None) -> bool:
        """设置财务指标数据，同时更新缓存和数据库
        
        Args:
            ticker: 股票代码
            data: 财务指标数据列表
            force_update: 是否强制更新现有记录
            db: 数据库会话
            
        Returns:
            bool: 操作是否成功
        """
        if not data:
            return False
            
        try:
            # 遍历数据项并保存到数据库
            for item in data:
                report_period = item['report_period']
                period = item.get('period', 'ttm')
                
                # 查找现有记录
                existing = db.query(db_models.FinancialMetric).filter(
                    db_models.FinancialMetric.ticker == ticker,
                    db_models.FinancialMetric.report_period == report_period,
                    db_models.FinancialMetric.period == period
                ).first()
                
                if existing and not force_update:
                    # 记录已存在且不强制更新
                    continue
                    
                if existing:
                    # 更新现有记录所有字段
                    for key, value in item.items():
                        if hasattr(existing, key):
                            setattr(existing, key, value)
                    existing.updated_at = datetime.utcnow()
                else:
                    # 创建新记录
                    # 从item中过滤出与模型相匹配的字段
                    filtered_item = {k: v for k, v in item.items() if hasattr(db_models.FinancialMetric, k)}
                    new_record = db_models.FinancialMetric(**filtered_item)
                    db.add(new_record)
            
            # 提交事务
            db.commit()
            
            # 清除相关的Redis缓存
            pattern = f"metrics:ticker:{ticker}*"
            for key in self.redis.scan_iter(pattern):
                self.redis.delete(key)
                
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"保存财务指标数据时出错: {e}")
            return False
    
    @with_db_session
    def get_line_items(self, ticker: str, end_date: Optional[str] = None, period: str = 'ttm', db: Session = None) -> List[Dict[str, Any]]:
        """获取财务报表行项目，优先从缓存获取
        
        Args:
            ticker: 股票代码
            end_date: 结束日期
            period: 报告期间
            db: 数据库会话
            
        Returns:
            List[Dict[str, Any]]: 行项目数据列表
        """
        # 尝试从Redis缓存获取
        cache_key = generate_cache_key("line_items", ticker=ticker, end_date=end_date, period=period)
        cached_data = self._redis_get(cache_key)
        if cached_data:
            return cached_data
            
        # 从数据库获取
        query = db.query(db_models.LineItem).filter(
            db_models.LineItem.ticker == ticker,
            db_models.LineItem.period == period
        )
        
        if end_date:
            query = query.filter(db_models.LineItem.report_period <= end_date)
            
        # 按报告期排序
        db_results = query.order_by(db_models.LineItem.report_period.desc()).all()
        
        # 转换为字典列表
        results = []
        for item in db_results:
            # 基本字段
            item_dict = {
                'ticker': item.ticker,
                'report_period': item.report_period,
                'period': item.period,
                'currency': item.currency
            }
            # 添加JSON数据字段
            if item.data:
                item_dict.update(item.data)
            results.append(item_dict)
            
        # 存入Redis缓存
        if results:
            self._redis_set(cache_key, results)
            
        return results
            
    @with_db_session
    def set_line_items(self, ticker: str, data: List[Dict[str, Any]], force_update: bool = False, db: Session = None) -> bool:
        """设置财务报表行项目，同时更新缓存和数据库
        
        Args:
            ticker: 股票代码
            data: 行项目数据列表
            force_update: 是否强制更新现有记录
            db: 数据库会话
            
        Returns:
            bool: 操作是否成功
        """
        if not data:
            return False
            
        try:
            # 遍历数据项并保存到数据库
            for item in data:
                report_period = item['report_period']
                period = item.get('period', 'ttm')
                
                # 查找现有记录
                existing = db.query(db_models.LineItem).filter(
                    db_models.LineItem.ticker == ticker,
                    db_models.LineItem.report_period == report_period,
                    db_models.LineItem.period == period
                ).first()
                
                # 提取基本字段和JSON数据
                base_fields = {
                    'ticker': ticker,
                    'report_period': report_period,
                    'period': period,
                    'currency': item.get('currency')
                }
                
                # 其余字段作为JSON数据
                json_data = {k: v for k, v in item.items() 
                           if k not in ('ticker', 'report_period', 'period', 'currency')}
                
                if existing and not force_update:
                    # 记录已存在且不强制更新
                    continue
                    
                if existing:
                    # 更新现有记录
                    existing.currency = base_fields['currency']
                    existing.data = json_data
                    existing.updated_at = datetime.utcnow()
                else:
                    # 创建新记录
                    new_record = db_models.LineItem(
                        ticker=base_fields['ticker'],
                        report_period=base_fields['report_period'],
                        period=base_fields['period'],
                        currency=base_fields['currency'],
                        data=json_data
                    )
                    db.add(new_record)
            
            # 提交事务
            db.commit()
            
            # 清除相关的Redis缓存
            pattern = f"line_items:ticker:{ticker}*"
            for key in self.redis.scan_iter(pattern):
                self.redis.delete(key)
                
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"保存行项目数据时出错: {e}")
            return False

    @with_db_session
    def get_insider_trades(self, ticker: str, start_date: Optional[str] = None, end_date: Optional[str] = None, db: Session = None) -> List[Dict[str, Any]]:
        """获取内部交易数据，优先从缓存获取
        
        Args:
            ticker: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            db: 数据库会话
            
        Returns:
            List[Dict[str, Any]]: 内部交易数据列表
        """
        # 尝试从Redis缓存获取
        cache_key = generate_cache_key("insider_trades", ticker=ticker, start_date=start_date, end_date=end_date)
        cached_data = self._redis_get(cache_key)
        if cached_data:
            return cached_data
            
        # 从数据库获取
        query = db.query(db_models.InsiderTrade).filter(db_models.InsiderTrade.ticker == ticker)
        
        # 构建日期过滤条件
        date_conditions = []
        if start_date:
            # 检查交易日期或申报日期
            cond1 = db_models.InsiderTrade.transaction_date >= start_date
            cond2 = db_models.InsiderTrade.filing_date >= start_date
            date_conditions.append(or_(cond1, cond2))
            
        if end_date:
            # 检查交易日期或申报日期
            cond1 = db_models.InsiderTrade.transaction_date <= end_date
            cond2 = db_models.InsiderTrade.filing_date <= end_date
            date_conditions.append(or_(cond1, cond2))
            
        if date_conditions:
            query = query.filter(and_(*date_conditions))
            
        # 按申报日期排序，最新的排在前面
        db_results = query.order_by(db_models.InsiderTrade.filing_date.desc()).all()
        
        # 转换为字典列表
        results = []
        for item in db_results:
            # 将SQLAlchemy模型转换为字典
            item_dict = {c.name: getattr(item, c.name) for c in item.__table__.columns 
                        if not c.name.startswith('_') and c.name not in ('id', 'created_at', 'updated_at')}
            results.append(item_dict)
            
        # 存入Redis缓存
        if results:
            self._redis_set(cache_key, results)
            
        return results
    
    @with_db_session
    def set_insider_trades(self, ticker: str, data: List[Dict[str, Any]], force_update: bool = False, db: Session = None) -> bool:
        """设置内部交易数据，同时更新缓存和数据库
        
        Args:
            ticker: 股票代码
            data: 内部交易数据列表
            force_update: 是否强制更新现有记录
            db: 数据库会话
            
        Returns:
            bool: 操作是否成功
        """
        if not data:
            return False
            
        try:
            # 遍历数据项并保存到数据库
            for item in data:
                filing_date = item['filing_date']
                name = item.get('name')
                transaction_date = item.get('transaction_date')
                
                # 查找现有记录 - 基于filing_date, name和transaction_date
                query = db.query(db_models.InsiderTrade).filter(
                    db_models.InsiderTrade.ticker == ticker,
                    db_models.InsiderTrade.filing_date == filing_date
                )
                
                if name:
                    query = query.filter(db_models.InsiderTrade.name == name)
                    
                if transaction_date:
                    query = query.filter(db_models.InsiderTrade.transaction_date == transaction_date)
                    
                existing = query.first()
                
                if existing and not force_update:
                    # 记录已存在且不强制更新
                    continue
                    
                # 为数据库记录准备数据
                item_data = item.copy()
                item_data['ticker'] = ticker  # 确保ticker正确
                
                if existing:
                    # 更新现有记录
                    for key, value in item_data.items():
                        if hasattr(existing, key):
                            setattr(existing, key, value)
                    existing.updated_at = datetime.utcnow()
                else:
                    # 创建新记录
                    filtered_data = {k: v for k, v in item_data.items() if hasattr(db_models.InsiderTrade, k)}
                    new_record = db_models.InsiderTrade(**filtered_data)
                    db.add(new_record)
            
            # 提交事务
            db.commit()
            
            # 清除相关的Redis缓存
            pattern = f"insider_trades:ticker:{ticker}*"
            for key in self.redis.scan_iter(pattern):
                self.redis.delete(key)
                
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"保存内部交易数据时出错: {e}")
            return False
    
    @with_db_session
    def get_company_news(self, ticker: str, start_date: Optional[str] = None, end_date: Optional[str] = None, db: Session = None) -> List[Dict[str, Any]]:
        """获取公司新闻，优先从缓存获取
        
        Args:
            ticker: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            db: 数据库会话
            
        Returns:
            List[Dict[str, Any]]: 公司新闻列表
        """
        # 尝试从Redis缓存获取
        cache_key = generate_cache_key("company_news", ticker=ticker, start_date=start_date, end_date=end_date)
        cached_data = self._redis_get(cache_key)
        if cached_data:
            return cached_data
            
        # 从数据库获取
        query = db.query(db_models.CompanyNews).filter(db_models.CompanyNews.ticker == ticker)
        
        if start_date:
            query = query.filter(db_models.CompanyNews.date >= start_date)
            
        if end_date:
            query = query.filter(db_models.CompanyNews.date <= end_date)
            
        # 按日期排序，最新的排在前面
        db_results = query.order_by(db_models.CompanyNews.date.desc()).all()
        
        # 转换为字典列表
        results = []
        for item in db_results:
            # 将SQLAlchemy模型转换为字典
            item_dict = {c.name: getattr(item, c.name) for c in item.__table__.columns 
                        if not c.name.startswith('_') and c.name not in ('id', 'created_at', 'updated_at')}
            results.append(item_dict)
            
        # 存入Redis缓存
        if results:
            self._redis_set(cache_key, results)
            
        return results
    
    @with_db_session
    def set_company_news(self, ticker: str, data: List[Dict[str, Any]], force_update: bool = False, db: Session = None) -> bool:
        """设置公司新闻，同时更新缓存和数据库
        
        Args:
            ticker: 股票代码
            data: 公司新闻列表
            force_update: 是否强制更新现有记录
            db: 数据库会话
            
        Returns:
            bool: 操作是否成功
        """
        if not data:
            return False
            
        try:
            # 遍历数据项并保存到数据库
            for item in data:
                date = item['date']
                title = item['title']
                url = item.get('url')
                
                # 构建查询
                query = db.query(db_models.CompanyNews).filter(
                    db_models.CompanyNews.ticker == ticker,
                    db_models.CompanyNews.date == date
                )
                
                # 如果有URL，用URL作为唯一标识
                if url:
                    query = query.filter(db_models.CompanyNews.url == url)
                else:
                    # 否则使用标题作为标识
                    query = query.filter(db_models.CompanyNews.title == title)
                
                existing = query.first()
                
                if existing and not force_update:
                    # 记录已存在且不强制更新
                    continue
                    
                # 为数据库记录准备数据
                item_data = item.copy()
                item_data['ticker'] = ticker  # 确保ticker正确
                
                if existing:
                    # 更新现有记录
                    for key, value in item_data.items():
                        if hasattr(existing, key):
                            setattr(existing, key, value)
                    existing.updated_at = datetime.utcnow()
                else:
                    # 创建新记录
                    filtered_data = {k: v for k, v in item_data.items() if hasattr(db_models.CompanyNews, k)}
                    new_record = db_models.CompanyNews(**filtered_data)
                    db.add(new_record)
            
            # 提交事务
            db.commit()
            
            # 清除相关的Redis缓存
            pattern = f"company_news:ticker:{ticker}*"
            for key in self.redis.scan_iter(pattern):
                self.redis.delete(key)
                
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"保存公司新闻时出错: {e}")
            return False
            
    def refresh_cache(self, data_type: str, ticker: str, **kwargs) -> bool:
        """强制刷新指定类型数据的缓存
        
        此方法会从数据库获取最新数据并更新Redis缓存
        
        Args:
            data_type: 数据类型 ('prices', 'financial_metrics', 等)
            ticker: 股票代码
            **kwargs: 其他查询参数
            
        Returns:
            bool: 刷新是否成功
        """
        try:
            if data_type == 'prices':
                data = self.get_prices(ticker, force_db=True, **kwargs)
            elif data_type == 'financial_metrics':
                data = self.get_financial_metrics(ticker, force_db=True, **kwargs)
            elif data_type == 'line_items':
                data = self.get_line_items(ticker, force_db=True, **kwargs)
            elif data_type == 'insider_trades':
                data = self.get_insider_trades(ticker, force_db=True, **kwargs)
            elif data_type == 'company_news':
                data = self.get_company_news(ticker, force_db=True, **kwargs)
            else:
                logger.warning(f"未知的数据类型: {data_type}")
                return False
                
            # 生成缓存键
            cache_key = generate_cache_key(data_type, ticker=ticker, **kwargs)
            
            # 更新Redis缓存
            return self._redis_set(cache_key, data)
            
        except Exception as e:
            logger.error(f"刷新缓存时出错 ({data_type}, {ticker}): {e}")
            return False

# 全局缓存实例
_cache = PersistentCache()

def get_cache() -> PersistentCache:
    """获取全局缓存实例"""
    return _cache

def init_cache():
    """初始化缓存，确保数据库和Redis连接正常"""
    from data.database import init_db
    
    # 如果AUTO_INITIALIZE为false，尝试初始化数据库
    # 否则数据库已在导入时自动初始化
    init_db()
    
    # 重新获取全局缓存实例（因为数据库状态可能已更改）
    return get_cache()
