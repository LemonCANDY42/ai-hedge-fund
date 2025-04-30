"""
提供从公司名称或实体查找股票代码的工具
"""

import os
import json
import time
import requests
from typing import List, Dict, Any, Optional, Union
from bs4 import BeautifulSoup
import re
from data.cache import get_cache
from tools.api import get_company_facts_tickers

# 全局缓存实例
_cache = get_cache()

# TODO： 缓存结果改为使用Redis缓存+sqlite持久化存储，并加长缓存过期时间
# TODO： 持久化存储也检查时间，并设置过期时间，查到过期后，更新对应条目
# TODO： 增加对Bloomberg API的查询
# TODO： 增加对Yahoo Finance API的查询
# TODO： 增加对Google Finance API的查询



def fetch_ticker_from_api(company_name: str) -> List[Dict[str, Any]]:
    """
    通过Financial Datasets API查询公司股票代码
    
    Args:
        company_name: 公司名称
        
    Returns:
        公司信息列表，每个包含名称、股票代码等信息
    """
    # 首先检查缓存
    cache_key = f"company_lookup:{company_name}"
    cached_result = _cache.redis.get(cache_key) if _cache.redis else None
    
    if cached_result:
        return json.loads(cached_result)
    
    # 设置API请求头
    headers = {}
    if api_key := os.environ.get("FINANCIAL_DATASETS_API_KEY"):
        headers["X-API-KEY"] = api_key
    else:
        # 如果没有API密钥，则不能使用API查询，返回空列表
        return []
    
    try:
        # 使用搜索端点搜索公司
        url = f"https://api.financialdatasets.ai/search?query={company_name}&type=company"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"搜索公司时出错: {response.status_code} - {response.text}")
            return []
        
        search_results = response.json().get("results", [])
        company_results = []
        
        # 处理搜索结果，获取每个公司的详细信息
        for result in search_results[:5]:  # 仅处理前5个结果以避免过多API调用
            ticker = result.get("ticker")
            if not ticker:
                continue
                
            # 获取公司详细信息
            facts_url = f"https://api.financialdatasets.ai/company/facts?ticker={ticker}"
            facts_response = requests.get(facts_url, headers=headers, timeout=10)
            
            if facts_response.status_code == 200:
                company_facts = facts_response.json().get("company_facts", {})
                if company_facts:
                    company_results.append({
                        "ticker": ticker,
                        "name": company_facts.get("name", ""),
                        "exchange": company_facts.get("exchange", ""),
                        "industry": company_facts.get("industry", ""),
                        "sector": company_facts.get("sector", ""),
                        "is_active": company_facts.get("is_active", True),
                        "match_source": "api"
                    })
        
        # 缓存结果（24小时有效期）
        if _cache.redis and company_results:
            _cache.redis.setex(cache_key, 24*60*60, json.dumps(company_results))
            
        return company_results
        
    except Exception as e:
        print(f"通过API查询公司股票代码时出错: {e}")
        return []


def fetch_ticker_from_fmp(company_name: str) -> List[Dict[str, Any]]:
    """
    通过Financial Modeling Prep API查询公司股票代码
    
    Args:
        company_name: 公司名称
        
    Returns:
        公司信息列表，每个包含名称、股票代码等信息
    """
    # 首先检查缓存
    cache_key = f"fmp_company_lookup:{company_name}"
    cached_result = _cache.redis.get(cache_key) if _cache.redis else None
    
    if cached_result:
        return json.loads(cached_result)
    
    # 如果没有设置API密钥，则无法使用此API
    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        return []
    
    results = []
    
    try:
        # 使用Financial Modeling Prep的Name Search API
        url = f"https://financialmodelingprep.com/api/v3/search?query={company_name}&limit=10&apikey={api_key}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            print(f"FMP搜索公司时出错: {response.status_code} - {response.text}")
            return []
        
        search_results = response.json()
        
        # 处理搜索结果
        for result in search_results:
            ticker = result.get("symbol")
            name = result.get("name")
            exchange = result.get("exchangeShortName", "")
            
            if ticker and name:
                results.append({
                    "ticker": ticker,
                    "name": name,
                    "exchange": exchange,
                    "match_source": "financial_modeling_prep"
                })
        
        # 缓存结果（24小时有效期）
        if _cache.redis and results:
            _cache.redis.setex(cache_key, 24*60*60, json.dumps(results))
        
        return results
        
    except Exception as e:
        print(f"通过FMP查询公司股票代码时出错: {e}")
        return []


def fetch_ticker_from_web(company_name: str) -> List[Dict[str, Any]]:
    """
    通过网络搜索查询公司股票代码
    
    Args:
        company_name: 公司名称
        
    Returns:
        公司信息列表，每个包含名称、股票代码等信息
    """
    # 首先检查缓存
    cache_key = f"web_company_lookup:{company_name}"
    cached_result = _cache.redis.get(cache_key) if _cache.redis else None
    
    if cached_result:
        return json.loads(cached_result)
    
    results = []
    
    try:
        # 尝试从Yahoo Finance搜索
        search_url = f"https://finance.yahoo.com/lookup?s={company_name}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        response = requests.get(search_url, headers=headers, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找搜索结果表格
            table = soup.find('table', {'class': 'W(100%)'})
            if table:
                rows = table.find_all('tr')[1:]  # 跳过表头行
                
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        ticker = cells[0].text.strip()
                        name = cells[1].text.strip()
                        
                        # 添加到结果中
                        results.append({
                            "ticker": ticker,
                            "name": name,
                            "exchange": cells[2].text.strip() if len(cells) > 2 else "",
                            "match_source": "yahoo_finance"
                        })
        
        # 如果Yahoo Finance没有结果，尝试从Market Watch搜索
        if not results:
            mw_search_url = f"https://www.marketwatch.com/tools/quotes/lookup.asp?siteID=mktw&Lookup={company_name}&Country=us&Type=All"
            mw_response = requests.get(mw_search_url, headers=headers, timeout=15)
            
            if mw_response.status_code == 200:
                soup = BeautifulSoup(mw_response.text, 'html.parser')
                
                # 查找MarketWatch的搜索结果表格
                table = soup.find('table', {'class': 'results'})
                if table:
                    rows = table.find_all('tr')[1:]  # 跳过表头行
                    
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            ticker = cells[0].text.strip()
                            name = cells[1].text.strip()
                            
                            # 添加到结果中
                            results.append({
                                "ticker": ticker,
                                "name": name,
                                "exchange": cells[2].text.strip() if len(cells) > 2 else "",
                                "match_source": "market_watch"
                            })
        
        # 缓存结果（24小时有效期）
        if _cache.redis and results:
            _cache.redis.setex(cache_key, 24*60*60, json.dumps(results))
            
        return results
        
    except Exception as e:
        print(f"通过Web查询公司股票代码时出错: {e}")
        return []


def lookup_ticker(company_name: str) -> List[Dict[str, Any]]:
    """
    根据公司名称查找股票代码
    
    Args:
        company_name: 公司名称
        
    Returns:
        公司信息列表，每个包含名称、股票代码等信息
    """
    if not company_name or len(company_name) < 2:
        return []
        
    # 尝试使用所有数据源查询，按优先级排序
    api_results = fetch_ticker_from_api(company_name)
    
    # 如果第一个数据源没有结果，尝试第二个数据源
    if not api_results:
        fmp_results = fetch_ticker_from_fmp(company_name)
        if fmp_results:
            return fmp_results
    else:
        return api_results
        
    # 如果前两个数据源都没有结果，尝试网络搜索
    web_results = fetch_ticker_from_web(company_name)
    return web_results


def validate_ticker(ticker: str) -> bool:
    """
    验证股票代码是否有效
    
    Args:
        ticker: 股票代码
        
    Returns:
        bool: 股票代码是否有效
    """
    if not ticker or len(ticker) > 5:
        return False
        
    # 获取有效的股票代码列表
    valid_tickers = set(get_company_facts_tickers())
    
    # 检查股票代码是否在有效列表中
    return ticker.upper() in valid_tickers


def get_company_info(ticker: str) -> Optional[Dict[str, Any]]:
    """
    获取公司信息
    
    Args:
        ticker: 股票代码
        
    Returns:
        公司信息字典
    """
    # 首先检查缓存
    cache_key = f"company_info:{ticker}"
    cached_result = _cache.redis.get(cache_key) if _cache.redis else None
    
    if cached_result:
        return json.loads(cached_result)
    
    # 设置API请求头
    headers = {}
    if api_key := os.environ.get("FINANCIAL_DATASETS_API_KEY"):
        headers["X-API-KEY"] = api_key
    else:
        # 如果没有API密钥，则不能使用API查询
        return None
    
    try:
        # 获取公司详细信息
        facts_url = f"https://api.financialdatasets.ai/company/facts?ticker={ticker}"
        facts_response = requests.get(facts_url, headers=headers, timeout=10)
        
        if facts_response.status_code == 200:
            company_facts = facts_response.json().get("company_facts", {})
            
            if company_facts:
                result = {
                    "ticker": ticker,
                    "name": company_facts.get("name", ""),
                    "exchange": company_facts.get("exchange", ""),
                    "industry": company_facts.get("industry", ""),
                    "sector": company_facts.get("sector", ""),
                    "is_active": company_facts.get("is_active", True),
                    "website_url": company_facts.get("website_url", ""),
                    "location": company_facts.get("location", ""),
                }
                
                # 缓存结果（24小时有效期）
                if _cache.redis:
                    _cache.redis.setex(cache_key, 24*60*60, json.dumps(result))
                    
                return result
        
        return None
        
    except Exception as e:
        print(f"获取公司信息时出错: {ticker} - {e}")
        return None


def get_similar_companies(ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    获取与指定公司类似的公司
    
    Args:
        ticker: 股票代码
        limit: 返回的类似公司数量限制
        
    Returns:
        类似公司信息列表
    """
    company_info = get_company_info(ticker)
    if not company_info:
        return []
        
    # 获取公司的行业和部门
    industry = company_info.get("industry", "")
    sector = company_info.get("sector", "")
    
    if not industry and not sector:
        return []
    
    # 首先检查缓存
    cache_key = f"similar_companies:{ticker}"
    cached_result = _cache.redis.get(cache_key) if _cache.redis else None
    
    if cached_result:
        return json.loads(cached_result)[:limit]
    
    # 设置API请求头
    headers = {}
    if api_key := os.environ.get("FINANCIAL_DATASETS_API_KEY"):
        headers["X-API-KEY"] = api_key
    else:
        # 如果没有API密钥，则不能使用API查询
        return []
    
    try:
        # 使用搜索端点搜索同行业公司
        search_query = industry or sector
        url = f"https://api.financialdatasets.ai/search?query={search_query}&type=company"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return []
        
        search_results = response.json().get("results", [])
        similar_companies = []
        
        # 处理搜索结果，获取每个公司的详细信息
        for result in search_results:
            result_ticker = result.get("ticker")
            if not result_ticker or result_ticker == ticker:
                continue
                
            similar_companies.append({
                "ticker": result_ticker,
                "name": result.get("name", ""),
                "similarity_reason": f"同行业公司 ({industry or sector})"
            })
            
            if len(similar_companies) >= limit:
                break
        
        # 缓存结果（7天有效期）
        if _cache.redis and similar_companies:
            _cache.redis.setex(cache_key, 7*24*60*60, json.dumps(similar_companies))
            
        return similar_companies
        
    except Exception as e:
        print(f"获取类似公司时出错: {ticker} - {e}")
        return [] 