import datetime
import os
import pandas as pd
import requests

from data.cache import get_cache, init_cache
from data.models import (
    CompanyNews,
    CompanyNewsResponse,
    FinancialMetrics,
    FinancialMetricsResponse,
    Price,
    PriceResponse,
    LineItem,
    LineItemResponse,
    InsiderTrade,
    InsiderTradeResponse,
    CompanyFactsResponse,
)

# 初始化缓存系统
init_cache()

# 全局缓存实例
_cache = get_cache()


def get_prices(ticker: str, start_date: str, end_date: str) -> list[Price]:
    """从缓存或API获取价格数据"""
    # 首先检查缓存
    if cached_data := _cache.get_prices(ticker, start_date=start_date, end_date=end_date):
        # 转换为Price对象
        return [Price(**price) for price in cached_data]

    # 如果不在缓存中，从API获取
    headers = {}
    if api_key := os.environ.get("FINANCIAL_DATASETS_API_KEY"):
        headers["X-API-KEY"] = api_key

    url = f"https://api.financialdatasets.ai/prices/?ticker={ticker}&interval=day&interval_multiplier=1&start_date={start_date}&end_date={end_date}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Error fetching data: {ticker} - {response.status_code} - {response.text}")

    # 使用Pydantic模型解析响应
    price_response = PriceResponse(**response.json())
    prices = price_response.prices

    if not prices:
        return []

    # 缓存结果
    _cache.set_prices(ticker, [p.model_dump() for p in prices])
    return prices


def get_financial_metrics(
    ticker: str,
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
) -> list[FinancialMetrics]:
    """从缓存或API获取财务指标"""
    # 首先检查缓存
    if cached_data := _cache.get_financial_metrics(ticker, end_date=end_date, period=period, limit=limit):
        # 转换为FinancialMetrics对象
        return [FinancialMetrics(**metric) for metric in cached_data]

    # 如果不在缓存中，从API获取
    headers = {}
    if api_key := os.environ.get("FINANCIAL_DATASETS_API_KEY"):
        headers["X-API-KEY"] = api_key

    url = f"https://api.financialdatasets.ai/financial-metrics/?ticker={ticker}&report_period_lte={end_date}&limit={limit}&period={period}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Error fetching data: {ticker} - {response.status_code} - {response.text}")

    # 使用Pydantic模型解析响应
    metrics_response = FinancialMetricsResponse(**response.json())
    financial_metrics = metrics_response.financial_metrics

    if not financial_metrics:
        return []

    # 缓存结果
    _cache.set_financial_metrics(ticker, [m.model_dump() for m in financial_metrics])
    return financial_metrics


def search_line_items(
    ticker: str,
    line_items: list[str],
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
) -> list[LineItem]:
    """从缓存或API获取财务报表行项目"""
    # 构建缓存查询参数
    # 注意：由于line_items是可变的，这里我们不使用缓存，直接从API获取
    
    headers = {}
    if api_key := os.environ.get("FINANCIAL_DATASETS_API_KEY"):
        headers["X-API-KEY"] = api_key

    url = "https://api.financialdatasets.ai/financials/search/line-items"

    body = {
        "tickers": [ticker],
        "line_items": line_items,
        "end_date": end_date,
        "period": period,
        "limit": limit,
    }
    response = requests.post(url, headers=headers, json=body)
    if response.status_code != 200:
        raise Exception(f"Error fetching data: {ticker} - {response.status_code} - {response.text}")
    data = response.json()
    response_model = LineItemResponse(**data)
    search_results = response_model.search_results
    if not search_results:
        return []

    # 缓存结果
    _cache.set_line_items(ticker, [item.model_dump() for item in search_results])
    return search_results[:limit]


def get_insider_trades(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
) -> list[InsiderTrade]:
    """从缓存或API获取内部交易数据"""
    # 首先检查缓存
    if cached_data := _cache.get_insider_trades(ticker, start_date=start_date, end_date=end_date):
        # 转换为InsiderTrade对象
        return [InsiderTrade(**trade) for trade in cached_data]

    # 如果不在缓存中，从API获取
    headers = {}
    if api_key := os.environ.get("FINANCIAL_DATASETS_API_KEY"):
        headers["X-API-KEY"] = api_key

    all_trades = []
    current_end_date = end_date
    
    while True:
        url = f"https://api.financialdatasets.ai/insider-trades/?ticker={ticker}&filing_date_lte={current_end_date}"
        if start_date:
            url += f"&filing_date_gte={start_date}"
        url += f"&limit={limit}"
        
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Error fetching data: {ticker} - {response.status_code} - {response.text}")
        
        data = response.json()
        response_model = InsiderTradeResponse(**data)
        insider_trades = response_model.insider_trades
        
        if not insider_trades:
            break
            
        all_trades.extend(insider_trades)
        
        # 只有在有start_date且获取了整页数据时继续分页
        if not start_date or len(insider_trades) < limit:
            break
            
        # 更新end_date为当前批次中最旧的filing_date，用于下一次迭代
        current_end_date = min(trade.filing_date for trade in insider_trades).split('T')[0]
        
        # 如果已经达到或超过start_date，可以停止
        if current_end_date <= start_date:
            break

    if not all_trades:
        return []

    # 缓存结果
    _cache.set_insider_trades(ticker, [trade.model_dump() for trade in all_trades])
    return all_trades


def get_company_news(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
) -> list[CompanyNews]:
    """从缓存或API获取公司新闻"""
    # 首先检查缓存
    if cached_data := _cache.get_company_news(ticker, start_date=start_date, end_date=end_date):
        # 转换为CompanyNews对象
        return [CompanyNews(**news) for news in cached_data]

    # 如果不在缓存中，从API获取
    headers = {}
    if api_key := os.environ.get("FINANCIAL_DATASETS_API_KEY"):
        headers["X-API-KEY"] = api_key

    all_news = []
    current_end_date = end_date
    
    while True:
        url = f"https://api.financialdatasets.ai/news/?ticker={ticker}&end_date={current_end_date}"
        if start_date:
            url += f"&start_date={start_date}"
        url += f"&limit={limit}"
        
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Error fetching data: {ticker} - {response.status_code} - {response.text}")
        
        data = response.json()
        response_model = CompanyNewsResponse(**data)
        company_news = response_model.news
        
        if not company_news:
            break
            
        all_news.extend(company_news)
        
        # 只有在有start_date且获取了整页数据时继续分页
        if not start_date or len(company_news) < limit:
            break
            
        # 更新end_date为当前批次中最旧的日期，用于下一次迭代
        current_end_date = min(news.date for news in company_news).split('T')[0]
        
        # 如果已经达到或超过start_date，可以停止
        if current_end_date <= start_date:
            break

    if not all_news:
        return []

    # 缓存结果
    _cache.set_company_news(ticker, [news.model_dump() for news in all_news])
    return all_news


def get_market_cap(
    ticker: str,
    end_date: str,
) -> float | None:
    """获取指定日期的市值"""
    metrics = get_financial_metrics(ticker, end_date, limit=1)
    if metrics and metrics[0].market_cap is not None:
        return metrics[0].market_cap
    
    # 如果财务指标中没有市值，则尝试计算
    prices = get_prices(ticker, start_date=end_date, end_date=end_date)
    if not prices:
        # 尝试获取最近的价格
        prev_date = (datetime.datetime.strptime(end_date, "%Y-%m-%d") - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        prices = get_prices(ticker, start_date=prev_date, end_date=end_date)
        if not prices:
            return None
    
    # 使用最近的价格和财务指标计算市值
    price = prices[-1].close
    
    # 尝试获取加权平均股数
    # 注意：这需要额外的API调用，这里只是一个示例
    weighted_shares = 1000000  # 假设值
    
    return price * weighted_shares


def prices_to_df(prices: list[Price]) -> pd.DataFrame:
    """将价格列表转换为pandas DataFrame"""
    df = pd.DataFrame([
        {
            "date": datetime.datetime.strptime(p.time.split("T")[0], "%Y-%m-%d").date(),
            "open": p.open,
            "high": p.high,
            "low": p.low,
            "close": p.close,
            "volume": p.volume,
        }
        for p in prices
    ])
    df.set_index("date", inplace=True)
    df.sort_index(inplace=True)
    return df


def get_price_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取价格数据并转换为DataFrame"""
    prices = get_prices(ticker, start_date, end_date)
    return prices_to_df(prices)


# 新函数：强制刷新缓存
def refresh_data(data_type: str, ticker: str, **kwargs) -> bool:
    """强制刷新指定类型数据的缓存和持久化存储
    
    Args:
        data_type: 数据类型 ('prices', 'financial_metrics', 'insider_trades', 'company_news', 'line_items')
        ticker: 股票代码
        **kwargs: 其他参数，如start_date, end_date等
        
    Returns:
        bool: 刷新操作是否成功
    """
    try:
        # 从API获取最新数据
        if data_type == 'prices':
            if 'start_date' not in kwargs or 'end_date' not in kwargs:
                raise ValueError("刷新价格数据需要提供start_date和end_date参数")
            data = get_prices(ticker, kwargs['start_date'], kwargs['end_date'])
            # 转换为字典并保存
            return _cache.set_prices(ticker, [p.model_dump() for p in data], force_update=True)
        
        elif data_type == 'financial_metrics':
            if 'end_date' not in kwargs:
                raise ValueError("刷新财务指标数据需要提供end_date参数")
            period = kwargs.get('period', 'ttm')
            limit = kwargs.get('limit', 10)
            data = get_financial_metrics(ticker, kwargs['end_date'], period, limit)
            # 转换为字典并保存
            return _cache.set_financial_metrics(ticker, [m.model_dump() for m in data], force_update=True)
        
        elif data_type == 'line_items':
            if 'end_date' not in kwargs or 'line_items' not in kwargs:
                raise ValueError("刷新行项目数据需要提供end_date和line_items参数")
            period = kwargs.get('period', 'ttm')
            limit = kwargs.get('limit', 10)
            data = search_line_items(ticker, kwargs['line_items'], kwargs['end_date'], period, limit)
            # 转换为字典并保存
            return _cache.set_line_items(ticker, [item.model_dump() for item in data], force_update=True)
        
        elif data_type == 'insider_trades':
            if 'end_date' not in kwargs:
                raise ValueError("刷新内部交易数据需要提供end_date参数")
            start_date = kwargs.get('start_date')
            limit = kwargs.get('limit', 1000)
            data = get_insider_trades(ticker, kwargs['end_date'], start_date, limit)
            # 转换为字典并保存
            return _cache.set_insider_trades(ticker, [trade.model_dump() for trade in data], force_update=True)
        
        elif data_type == 'company_news':
            if 'end_date' not in kwargs:
                raise ValueError("刷新公司新闻需要提供end_date参数")
            start_date = kwargs.get('start_date')
            limit = kwargs.get('limit', 1000)
            data = get_company_news(ticker, kwargs['end_date'], start_date, limit)
            # 转换为字典并保存
            return _cache.set_company_news(ticker, [news.model_dump() for news in data], force_update=True)
        
        else:
            raise ValueError(f"未知的数据类型: {data_type}")
    
    except Exception as e:
        print(f"刷新数据时出错 ({data_type}, {ticker}): {e}")
        return False


# 新函数：检查数据完整性并获取缺失部分
def check_and_fill_data(data_type: str, ticker: str, **kwargs) -> list:
    """检查指定时间范围内的数据完整性，获取并填充缺失数据
    
    Args:
        data_type: 数据类型 ('prices')
        ticker: 股票代码
        **kwargs: 参数，如start_date, end_date等
        
    Returns:
        list: 合并后的完整数据
    """
    if data_type == 'prices':
        if 'start_date' not in kwargs or 'end_date' not in kwargs:
            raise ValueError("需要提供start_date和end_date参数")
        
        start_date = kwargs['start_date']
        end_date = kwargs['end_date']
        
        # 从缓存获取现有数据
        existing_data = _cache.get_prices(ticker, start_date=start_date, end_date=end_date)
        
        if not existing_data:
            # 如果没有现有数据，获取整个范围
            prices = get_prices(ticker, start_date, end_date)
            return [p.model_dump() for p in prices]
        
        # 检查日期连续性
        dates = sorted([item['time'].split('T')[0] for item in existing_data])
        all_dates = []
        
        # 生成所有应该存在的日期
        current_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.datetime.strptime(end_date, "%Y-%m-%d")
        while current_date <= end:
            date_str = current_date.strftime("%Y-%m-%d")
            # 只包括工作日（简化处理，不考虑节假日）
            if current_date.weekday() < 5:  # 0-4 为周一至周五
                all_dates.append(date_str)
            current_date += datetime.timedelta(days=1)
        
        # 找出缺失的日期
        missing_dates = [d for d in all_dates if d not in dates]
        
        if not missing_dates:
            # 没有缺失日期
            return existing_data
        
        # 获取缺失日期的数据
        for date_range in split_date_ranges(missing_dates):
            try:
                new_prices = get_prices(ticker, date_range['start'], date_range['end'])
                if new_prices:
                    _cache.set_prices(ticker, [p.model_dump() for p in new_prices])
            except Exception as e:
                print(f"获取价格数据时出错 ({ticker}, {date_range}): {e}")
        
        # 返回完整的合并数据
        return _cache.get_prices(ticker, start_date=start_date, end_date=end_date)
    
    else:
        raise ValueError(f"数据完整性检查不支持该数据类型: {data_type}")


def split_date_ranges(dates: list[str]) -> list[dict]:
    """将日期列表分割为连续的日期范围
    
    Args:
        dates: 日期字符串列表，格式为 'YYYY-MM-DD'
        
    Returns:
        list[dict]: 日期范围列表，每个范围包含 'start' 和 'end' 键
    """
    if not dates:
        return []
    
    # 将字符串日期转换为datetime对象并排序
    date_objs = sorted([datetime.datetime.strptime(d, "%Y-%m-%d") for d in dates])
    
    ranges = []
    range_start = date_objs[0]
    prev_date = date_objs[0]
    
    for i in range(1, len(date_objs)):
        curr_date = date_objs[i]
        # 如果当前日期与前一日期不连续（间隔大于1天）
        if (curr_date - prev_date).days > 1:
            # 结束当前范围
            ranges.append({
                'start': range_start.strftime("%Y-%m-%d"),
                'end': prev_date.strftime("%Y-%m-%d")
            })
            # 开始新范围
            range_start = curr_date
        
        prev_date = curr_date
    
    # 添加最后一个范围
    ranges.append({
        'start': range_start.strftime("%Y-%m-%d"),
        'end': date_objs[-1].strftime("%Y-%m-%d")
    })
    
    return ranges
