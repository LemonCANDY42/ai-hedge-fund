"""
缓存管理模块 - 提供高级缓存管理功能
"""
import logging
import datetime
from typing import List, Dict, Any, Optional, Tuple

from data.cache import get_cache
from tools.api import refresh_data, check_and_fill_data

# 设置日志
logger = logging.getLogger(__name__)

class CacheManager:
    """缓存管理器 - 提供高级缓存管理功能"""
    
    def __init__(self):
        """初始化缓存管理器"""
        self.cache = get_cache()
    
    def refresh_ticker_data(self, ticker: str, start_date: str = None, end_date: str = None) -> Dict[str, bool]:
        """刷新指定股票的所有数据
        
        Args:
            ticker: 股票代码
            start_date: 开始日期，默认为None（7天前）
            end_date: 结束日期，默认为None（当天）
            
        Returns:
            Dict[str, bool]: 各类数据刷新结果
        """
        # 设置默认日期范围
        if end_date is None:
            end_date = datetime.datetime.now().strftime("%Y-%m-%d")
            
        if start_date is None:
            start_date = (datetime.datetime.strptime(end_date, "%Y-%m-%d") - 
                          datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        
        results = {}
        
        # 刷新价格数据
        results['prices'] = refresh_data('prices', ticker, 
                                       start_date=start_date, 
                                       end_date=end_date)
        
        # 刷新财务指标
        results['financial_metrics'] = refresh_data('financial_metrics', ticker, 
                                                  end_date=end_date, 
                                                  period='ttm', 
                                                  limit=10)
        
        # 刷新内部交易
        results['insider_trades'] = refresh_data('insider_trades', ticker, 
                                               end_date=end_date, 
                                               start_date=start_date, 
                                               limit=100)
        
        # 刷新公司新闻
        results['company_news'] = refresh_data('company_news', ticker, 
                                             end_date=end_date, 
                                             start_date=start_date, 
                                             limit=50)
        
        return results
    
    def fill_missing_price_data(self, ticker: str, start_date: str, end_date: str) -> Tuple[List[Dict], List[str]]:
        """查找并填充缺失的价格数据
        
        Args:
            ticker: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            Tuple[List[Dict], List[str]]: (合并后的完整数据, 填充的日期列表)
        """
        # 从缓存获取现有数据
        existing_data = self.cache.get_prices(ticker, start_date=start_date, end_date=end_date)
        
        if not existing_data:
            # 如果没有数据，获取整个范围
            prices = check_and_fill_data('prices', ticker, start_date=start_date, end_date=end_date)
            return prices, []
            
        # 检查日期连续性
        existing_dates = {item['time'].split('T')[0] for item in existing_data}
        
        # 生成所有应该存在的日期（工作日）
        all_dates = []
        current_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.datetime.strptime(end_date, "%Y-%m-%d")
        while current_date <= end:
            # 只包括工作日（简化处理，不考虑节假日）
            if current_date.weekday() < 5:  # 0-4 为周一至周五
                all_dates.append(current_date.strftime("%Y-%m-%d"))
            current_date += datetime.timedelta(days=1)
            
        # 找出缺失的日期
        missing_dates = [d for d in all_dates if d not in existing_dates]
        
        if not missing_dates:
            # 没有缺失日期
            return existing_data, []
            
        # 填充缺失数据
        complete_data = check_and_fill_data('prices', ticker, start_date=start_date, end_date=end_date)
        
        return complete_data, missing_dates
    
    def get_data_stats(self, ticker: str) -> Dict[str, Dict[str, Any]]:
        """获取指定股票的缓存数据统计信息
        
        Args:
            ticker: 股票代码
            
        Returns:
            Dict[str, Dict[str, Any]]: 各类数据的统计信息
        """
        stats = {}
        
        # 获取价格数据统计
        prices = self.cache.get_prices(ticker)
        if prices:
            dates = [p['time'].split('T')[0] for p in prices]
            stats['prices'] = {
                'count': len(prices),
                'earliest_date': min(dates),
                'latest_date': max(dates)
            }
        else:
            stats['prices'] = {'count': 0}
            
        # 获取财务指标统计
        metrics = self.cache.get_financial_metrics(ticker)
        if metrics:
            periods = [m['report_period'] for m in metrics]
            stats['financial_metrics'] = {
                'count': len(metrics),
                'earliest_period': min(periods),
                'latest_period': max(periods)
            }
        else:
            stats['financial_metrics'] = {'count': 0}
            
        # 获取内部交易统计
        trades = self.cache.get_insider_trades(ticker)
        if trades:
            filing_dates = [t['filing_date'].split('T')[0] for t in trades]
            stats['insider_trades'] = {
                'count': len(trades),
                'earliest_date': min(filing_dates),
                'latest_date': max(filing_dates)
            }
        else:
            stats['insider_trades'] = {'count': 0}
            
        # 获取公司新闻统计
        news = self.cache.get_company_news(ticker)
        if news:
            dates = [n['date'] for n in news]
            stats['company_news'] = {
                'count': len(news),
                'earliest_date': min(dates),
                'latest_date': max(dates)
            }
        else:
            stats['company_news'] = {'count': 0}
            
        return stats
    
    def clear_ticker_cache(self, ticker: str) -> bool:
        """清除指定股票的所有Redis缓存（不删除数据库数据）
        
        Args:
            ticker: 股票代码
            
        Returns:
            bool: 操作是否成功
        """
        try:
            redis = self.cache.redis
            
            # 清除该股票的所有缓存
            for pattern in [
                f"prices:ticker:{ticker}*", 
                f"metrics:ticker:{ticker}*", 
                f"line_items:ticker:{ticker}*",
                f"insider_trades:ticker:{ticker}*", 
                f"company_news:ticker:{ticker}*"
            ]:
                for key in redis.scan_iter(pattern):
                    redis.delete(key)
                    
            return True
            
        except Exception as e:
            logger.error(f"清除缓存时出错 ({ticker}): {e}")
            return False


# 创建全局缓存管理器实例
_cache_manager = CacheManager()

def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器实例"""
    return _cache_manager 