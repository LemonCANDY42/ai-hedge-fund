"""
使用LLM增强新闻数据，添加摘要、实体和分类信息。
"""

import os
import time
import requests
from typing import List, Dict, Any, Optional
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from data.cache import get_cache
from data.models import CompanyNews
from data.db_models import News
from tools.api import get_company_news, refresh_data
from llm.models import get_model_info, ModelProvider
from utils.llm import call_llm
from utils.progress import progress
from bs4 import BeautifulSoup
import re

# 全局缓存实例
_cache = get_cache()


class EnhancedNewsItem(BaseModel):
    """增强后的新闻项"""
    ticker: str = Field(..., description="股票代码")
    title: str = Field(..., description="标题")
    summary: str = Field(..., description="文章内容的摘要，包含关键信息")
    categories: List[str] = Field(..., description="新闻分类，例如：['财报', '管理层变动', '产品发布']")
    entities: Dict[str, List[str]] = Field(..., description="提到的实体，按类型分组，例如：{'人物': ['CEO名'], '公司': ['竞争对手'], '地点': ['国家/地区']}")


def get_article_content(url: str) -> str:
    """
    从URL获取文章内容
    
    Args:
        url: 新闻文章URL
        
    Returns:
        str: 提取的文章内容
    """
    if not url or url == "#":
        return ""
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # 使用BeautifulSoup解析HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 移除脚本、样式和导航元素
        for script in soup(["script", "style", "nav", "header", "footer", "aside"]):
            script.extract()
        
        # 获取正文段落
        paragraphs = soup.find_all('p')
        
        # 提取和清理文本
        text = ' '.join([p.get_text().strip() for p in paragraphs])
        
        # 清理额外的空白字符
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 如果内容太长，截取前1500个字符
        if len(text) > 1500:
            text = text[:1500] + "..."
            
        return text
    except Exception as e:
        print(f"获取文章内容时出错: {url} - {e}")
        return ""


def enhance_news_with_llm(
    news_items: List[CompanyNews],
    model_name: str,
    model_provider: str,
    limit: int = None,
    batch_size: int = 1
) -> List[Dict[str, Any]]:
    """
    使用LLM增强新闻数据
    
    Args:
        news_items: 需要增强的新闻项列表
        model_name: 模型名称
        model_provider: 模型提供商
        limit: 处理的新闻项数量上限，如果为None则处理所有项
        batch_size: 批处理大小，每次调用LLM处理的新闻项数量
        
    Returns:
        增强后的新闻项列表
    """
    if not news_items:
        return []
    
    # 限制处理的数量
    if limit and limit < len(news_items):
        news_items = news_items[:limit]
    
    # 记录总数和当前进度
    total_count = len(news_items)
    processed_count = 0
    enhanced_items = []
    
    # 创建提示模板
    prompt_template = ChatPromptTemplate.from_template("""
    你是一个新闻分析专家，需要完成对以下新闻的分析和信息提取。请根据新闻标题和内容，提供以下信息：
    
    1. 文章内容的详细摘要（基于提供的内容）
    2. 新闻分类（财报、管理层变动、产品发布等）
    3. 相关实体提取（人物、公司、地点等）
    
    请不要分析情感倾向，只关注事实内容。
    
    新闻信息:
    股票代码: {ticker}
    标题: {title}
    来源: {source}
    日期: {date}
    内容摘录: {content}
    
    请以JSON格式回答，包含以下字段:
    - ticker: 股票代码
    - title: 标题
    - summary: 内容摘要
    - categories: 新闻分类的字符串列表
    - entities: 包含不同类型实体的对象，key为实体类型，value为该类型的实体列表
    """)
    
    # 批处理新闻项
    for i in range(0, len(news_items), batch_size):
        batch = news_items[i:i+batch_size]
        
        for news_item in batch:
            try:
                # 获取文章内容
                progress.update_status("news_enhancer", news_item.ticker, f"获取新闻内容 ({processed_count+1}/{total_count})")
                article_content = get_article_content(news_item.url or "")
                
                # 构建提示
                prompt = prompt_template.format(
                    ticker=news_item.ticker,
                    title=news_item.title,
                    source=news_item.source or "未知来源",
                    date=news_item.date,
                    content=article_content or f"无法获取内容。标题：{news_item.title}"
                )
                
                # 调用LLM
                progress.update_status("news_enhancer", news_item.ticker, f"增强新闻 ({processed_count+1}/{total_count})")
                
                # 执行LLM调用，如果失败则使用一个基本增强
                result = call_llm(
                    prompt=prompt,
                    model_name=model_name,
                    model_provider=model_provider,
                    pydantic_model=EnhancedNewsItem,
                    agent_name="news_enhancer"
                )
                
                # 更新缓存条目，保留原有的sentiment值
                enhanced_item = {
                    "ticker": news_item.ticker,
                    "title": news_item.title,
                    "author": news_item.author or "",
                    "source": news_item.source or "",
                    "date": news_item.date,
                    "url": news_item.url or "",
                    "sentiment": news_item.sentiment,  # 保留原有的情感值
                    "summary": result.summary,
                    "categories": result.categories,
                    "entities": result.entities
                }
                
                enhanced_items.append(enhanced_item)
                processed_count += 1
                
                # 添加间隔避免对API限速
                if batch_size > 1 and i + batch_size < len(news_items):
                    time.sleep(0.5)
                
            except Exception as e:
                print(f"增强新闻时出错: {news_item.title} - {e}")
                # 添加一个基本增强以避免跳过
                enhanced_items.append({
                    "ticker": news_item.ticker,
                    "title": news_item.title,
                    "author": news_item.author or "",
                    "source": news_item.source or "",
                    "date": news_item.date,
                    "url": news_item.url or "",
                    "sentiment": news_item.sentiment,  # 保留原有的情感值
                    "summary": f"摘要: {news_item.title}",
                    "categories": ["未分类"],
                    "entities": {"公司": [news_item.ticker]}
                })
                processed_count += 1
    
    progress.update_status("news_enhancer", news_items[0].ticker if news_items else "", "完成")
    return enhanced_items


def update_news_with_enhancements(
    enhanced_items: List[Dict[str, Any]],
    force_update: bool = False
) -> bool:
    """
    将增强的新闻数据更新到数据库和缓存
    
    Args:
        enhanced_items: 增强后的新闻项列表
        force_update: 是否强制更新，即使记录已存在
        
    Returns:
        bool: 操作是否成功
    """
    if not enhanced_items:
        return False
    
    # 按股票代码分组
    ticker_groups = {}
    for item in enhanced_items:
        ticker = item['ticker']
        if ticker not in ticker_groups:
            ticker_groups[ticker] = []
        ticker_groups[ticker].append(item)
    
    # 逐个股票更新缓存
    success = True
    for ticker, items in ticker_groups.items():
        if not _cache.set_company_news(ticker, items, force_update=force_update):
            success = False
    
    return success


def enhance_ticker_news(
    ticker: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    model_name: str = "gemma3:12b",  # 默认为本地Ollama模型
    model_provider: str = ModelProvider.OLLAMA.value,
    limit: Optional[int] = None,
    force_update: bool = False,
    batch_size: int = 1,
    no_content: bool = False
) -> bool:
    """
    增强特定股票的新闻数据
    
    Args:
        ticker: 股票代码
        start_date: 开始日期
        end_date: 结束日期
        model_name: 模型名称
        model_provider: 模型提供商
        limit: 处理的新闻项数量上限
        force_update: 是否强制更新，即使记录已存在
        batch_size: 批处理大小
        no_content: 是否禁用URL内容获取功能
        
    Returns:
        bool: 操作是否成功
    """
    try:
        # 获取新闻数据
        news_items = get_company_news(ticker, end_date, start_date)
        
        if not news_items:
            print(f"没有找到 {ticker} 在指定时间范围内的新闻")
            return False
        
        # 如果禁用内容获取，修改get_article_content功能
        if no_content:
            # 临时替换get_article_content函数
            global get_article_content
            original_func = get_article_content
            get_article_content = lambda url: ""
        
        try:
            # 增强新闻数据
            enhanced_items = enhance_news_with_llm(
                news_items, 
                model_name, 
                model_provider, 
                limit, 
                batch_size
            )
            
            # 更新缓存和数据库
            return update_news_with_enhancements(enhanced_items, force_update)
        finally:
            # 如果禁用了内容获取，恢复原始函数
            if no_content:
                get_article_content = original_func
        
    except Exception as e:
        print(f"增强 {ticker} 新闻时出错: {e}")
        return False


def enhance_multiple_tickers(
    tickers: List[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    model_name: str = "gemma3:12b",
    model_provider: str = ModelProvider.OLLAMA.value,
    limit_per_ticker: Optional[int] = None,
    force_update: bool = False,
    batch_size: int = 1,
    no_content: bool = False
) -> Dict[str, bool]:
    """
    增强多个股票的新闻数据
    
    Args:
        tickers: 股票代码列表
        start_date: 开始日期
        end_date: 结束日期
        model_name: 模型名称
        model_provider: 模型提供商
        limit_per_ticker: 每个股票处理的新闻项数量上限
        force_update: 是否强制更新，即使记录已存在
        batch_size: 批处理大小
        no_content: 是否禁用URL内容获取功能
        
    Returns:
        Dict[str, bool]: 每个股票的操作结果
    """
    results = {}
    
    for ticker in tickers:
        print(f"开始增强 {ticker} 的新闻数据...")
        result = enhance_ticker_news(
            ticker, 
            start_date, 
            end_date, 
            model_name, 
            model_provider, 
            limit_per_ticker, 
            force_update,
            batch_size,
            no_content
        )
        results[ticker] = result
        print(f"增强 {ticker} 的新闻数据{'成功' if result else '失败'}")
    
    return results 