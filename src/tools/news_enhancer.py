"""
使用LLM增强新闻数据，添加摘要、实体和分类信息。
"""

import os
import time
import requests
from typing import List, Dict, Any, Optional
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from src.data.cache import get_cache
from src.data.models import CompanyNews
from src.data.db_models import News
from src.tools.api import get_company_news, refresh_data
from src.llm.models import get_model_info, ModelProvider
from src.utils.llm import call_llm
from src.utils.progress import progress
from bs4 import BeautifulSoup
import re
from src.agents.news_analyzer import batch_analyze_news

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
    batch_size: int = 1,
    sentiment_model_name: Optional[str] = None,
    sentiment_model_provider: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    使用LLM增强新闻数据
    
    Args:
        news_items: 需要增强的新闻项列表
        model_name: 模型名称
        model_provider: 模型提供商
        limit: 处理的新闻项数量上限，如果为None则处理所有项
        batch_size: 批处理大小，每次调用LLM处理的新闻项数量
        sentiment_model_name: 情感分析专用模型名称（可选）
        sentiment_model_provider: 情感分析专用模型提供商（可选）
        
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
    article_contents = []
    
    # 获取所有文章内容
    for news_item in news_items:
        progress.update_status("news_enhancer", news_item.ticker, f"获取新闻内容 ({processed_count+1}/{total_count})")
        article_content = get_article_content(news_item.url or "")
        article_contents.append(article_content)
        processed_count += 1
    
    # 重置进度计数
    processed_count = 0
    
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
    
    # 批处理新闻项，完成基本增强（摘要、分类和实体识别）
    for i in range(0, len(news_items), batch_size):
        batch = news_items[i:i+batch_size]
        batch_contents = article_contents[i:i+batch_size]
        
        for news_item, article_content in zip(batch, batch_contents):
            try:
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
                    "entities": result.entities,
                    # 初始化相关股票和情感字段，将在后续步骤中填充
                    "related_tickers": [],
                    "ticker_sentiments": {},
                    "enhancement_status": "success"  # 标记成功状态
                }
                
                enhanced_items.append(enhanced_item)
                processed_count += 1
                
                # 添加间隔避免对API限速
                if batch_size > 1 and i + batch_size < len(news_items):
                    time.sleep(0.5)
                
            except Exception as e:
                print(f"增强新闻时出错: {news_item.title} - {e}")
                # 添加原始条目而不是基本增强，保持原有状态以便下次补全
                enhanced_item = {
                    "ticker": news_item.ticker,
                    "title": news_item.title,
                    "author": news_item.author or "",
                    "source": news_item.source or "",
                    "date": news_item.date,
                    "url": news_item.url or "",
                    "sentiment": news_item.sentiment,  # 保留原有的情感值
                    # 不设置summary、categories、entities字段，保持原始状态
                    # 保持相关股票和情感字段的原有状态，而不是初始化
                    "enhancement_status": "error"  # 标记错误状态
                }
                
                enhanced_items.append(enhanced_item)
                processed_count += 1
    
    # 立即将实体信息保存到数据库
    # 这样我们可以先保存实体信息，然后再进行情感分析
    temp_enhance_items = enhanced_items.copy()
    progress.update_status("news_enhancer", news_items[0].ticker if news_items else "", "保存实体信息到数据库")
    update_news_with_enhancements(temp_enhance_items, force_update=False)
    
    # 现在进行相关股票识别和情感分析
    progress.update_status("news_enhancer", news_items[0].ticker if news_items else "", "分析相关股票和情感")
    
    # 将临时字典转换为CompanyNews对象列表，用于情感分析
    analysis_items = []
    for i, item in enumerate(enhanced_items):
        # 只对成功增强的新闻进行情感分析
        if item.get("enhancement_status") == "success" and "entities" in item:
            analysis_item = CompanyNews(
                ticker=item["ticker"],
                title=item["title"],
                author=item["author"],
                source=item["source"],
                date=item["date"],
                url=item["url"],
                sentiment=item["sentiment"],
                summary=item["summary"],
                categories=item["categories"],
                entities=item["entities"]  # 传递已提取的实体信息给情感分析
            )
            analysis_items.append(analysis_item)
        else:
            # 跳过失败的条目
            enhanced_items[i]["skip_sentiment_analysis"] = True
    
    # 只有当有成功增强的条目时才进行情感分析
    if analysis_items:
        # 调用news_analyzer进行批量分析
        analyzed_results = batch_analyze_news(
            analysis_items,
            [article_contents[i] for i, item in enumerate(enhanced_items) if "skip_sentiment_analysis" not in item],
            model_name,
            model_provider,
            sentiment_model_name,
            sentiment_model_provider
        )
        
        # 更新相关股票和情感信息
        analyzed_index = 0
        for i, item in enumerate(enhanced_items):
            if "skip_sentiment_analysis" not in item:
                if analyzed_index < len(analyzed_results):
                    enhanced_items[i]["related_tickers"] = analyzed_results[analyzed_index]["related_tickers"]
                    enhanced_items[i]["ticker_sentiments"] = analyzed_results[analyzed_index]["ticker_sentiments"]
                    analyzed_index += 1
    
    # 移除临时标记字段
    for item in enhanced_items:
        if "enhancement_status" in item:
            del item["enhancement_status"]
        if "skip_sentiment_analysis" in item:
            del item["skip_sentiment_analysis"]
    
    progress.update_status("news_enhancer", news_items[0].ticker if news_items else "", "完成")
    return enhanced_items


def update_news_with_enhancements(
    enhanced_items: List[Dict[str, Any]],
    force_update: bool = False
) -> bool:
    """
    将增强的新闻数据更新到数据库和缓存
    
    特别说明：默认情况下，此函数只会填补原来为空的数据（summary、categories、entities），
    如果某一类别已有数据，则不会覆盖。只有在force_update=True时才会覆盖所有字段。
    
    Args:
        enhanced_items: 增强后的新闻项列表
        force_update: 是否强制更新，即使记录已存在
        
    Returns:
        bool: 操作是否成功
    """
    if not enhanced_items:
        return False
    
    # 获取缓存实例
    cache = get_cache()
    
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
        # 先获取现有的新闻数据
        existing_news = cache.get_company_news(ticker)
        existing_news_map = {}
        
        # 构建现有数据的映射，基于标题和URL
        for news in existing_news:
            key = (news.get('title', ''), news.get('url', ''))
            existing_news_map[key] = news
        
        # 处理每个增强项
        for item in items:
            title = item.get('title', '')
            url = item.get('url', '')
            key = (title, url)
            
            # 检查该新闻是否已存在
            if key in existing_news_map:
                existing = existing_news_map[key]
                
                # 如果当前条目处于错误状态，跳过更新
                if item.get("enhancement_status") == "error":
                    # 保持现有状态，不更新
                    existing_news_map[key] = existing
                    continue
                
                # 只填补原来为空的数据或强制更新所有字段
                if force_update or not existing.get('summary'):
                    existing['summary'] = item.get('summary', '')
                
                if force_update or not existing.get('categories'):
                    existing['categories'] = item.get('categories', [])
                
                if force_update or not existing.get('entities'):
                    existing['entities'] = item.get('entities', {})
                
                # 只有在进行完整更新时才更新情感信息和相关股票
                if 'related_tickers' in item and (force_update or not existing.get('related_tickers')):
                    existing['related_tickers'] = item['related_tickers']
                
                if 'ticker_sentiments' in item and (force_update or not existing.get('ticker_sentiments')):
                    existing['ticker_sentiments'] = item['ticker_sentiments']
                
                # 更新回处理列表中
                existing_news_map[key] = existing
            else:
                # 如果新闻不存在，且不在错误状态，则直接添加
                if item.get("enhancement_status") != "error":
                    existing_news_map[key] = item
        
        # 将更新后的数据转换回列表
        updated_items = list(existing_news_map.values())
        
        # 更新到缓存和数据库
        if not cache.set_company_news(ticker, updated_items, force_update=force_update):
            success = False
    
    return success


def enhance_ticker_news(
    ticker: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    model_name: str = "gemma3:12b",  # 默认为本地Ollama模型
    model_provider: str = ModelProvider.OLLAMA.value,
    sentiment_model_name: Optional[str] = None,
    sentiment_model_provider: Optional[str] = None,
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
        sentiment_model_name: 情感分析专用模型名称（可选）
        sentiment_model_provider: 情感分析专用模型提供商（可选）
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
                batch_size,
                sentiment_model_name,
                sentiment_model_provider
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
    sentiment_model_name: Optional[str] = None,
    sentiment_model_provider: Optional[str] = None,
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
        sentiment_model_name: 情感分析专用模型名称（可选）
        sentiment_model_provider: 情感分析专用模型提供商（可选）
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
            sentiment_model_name,
            sentiment_model_provider,
            limit_per_ticker, 
            force_update,
            batch_size,
            no_content
        )
        results[ticker] = result
        print(f"增强 {ticker} 的新闻数据{'成功' if result else '失败'}")
    
    return results 