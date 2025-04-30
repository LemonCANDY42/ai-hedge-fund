"""
新闻分析Agent - 负责解析新闻内容，提取相关股票代码并分析对应的金融情感。
"""

from typing import List, Dict, Optional, Any, Set
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from utils.llm import call_llm
from utils.progress import progress
from data.models import CompanyNews
import re
from llm.models import ModelProvider
from tools.api import get_company_facts_tickers
from tools.ticker_lookup import lookup_ticker, validate_ticker

# 情感强度定义 - 从最负面到最正面
SENTIMENT_SCALE = [
    "strong negative",     # 强烈负面
    "moderately negative", # 中度负面
    "mildly negative",     # 轻度负面
    "neutral",             # 中性
    "mildly positive",     # 轻度正面
    "moderately positive", # 中度正面
    "strong positive"      # 强烈正面
]

# 情感权重映射，用于计算情感得分
SENTIMENT_WEIGHTS = {
    "strong negative": -3.0,
    "moderately negative": -2.0,
    "mildly negative": -1.0,
    "neutral": 0.0,
    "mildly positive": 1.0,
    "moderately positive": 2.0,
    "strong positive": 3.0
}

class TickerSentiment(BaseModel):
    """股票代码的情感分析结果"""
    sentiment: str = Field(..., description="情感分析结果，可选值：strong negative/moderately negative/mildly negative/neutral/mildly positive/moderately positive/strong positive")
    relevance: float = Field(..., description="相关性得分，0.0到1.0")
    reasoning: str = Field(..., description="分析原因")

class NewsAnalysisResult(BaseModel):
    """新闻分析的结果"""
    related_tickers: List[str] = Field(..., description="从新闻内容中提取的相关股票代码列表")
    ticker_sentiments: Dict[str, TickerSentiment] = Field(..., description="每个股票代码的情感分析结果")

def extract_stock_symbols(news_item: CompanyNews, article_content: str, 
                          model_name: str = None, model_provider: str = None) -> List[str]:
    """
    从新闻内容和实体信息中提取相关股票代码，使用LLM分析实体来确定相关公司
    
    Args:
        news_item: 新闻项，包含标题、实体信息等
        article_content: 文章内容
        model_name: 用于LLM分析的模型名称
        model_provider: 用于LLM分析的模型提供商
        
    Returns:
        相关股票代码列表
    """
    # 确保原始ticker被包含
    default_tickers = [news_item.ticker] if news_item.ticker else []
    
    # 如果没有足够的信息进行分析，直接返回原始ticker
    if not news_item.entities and not article_content and not model_name:
        return default_tickers
    
    # 准备用于获取有效股票代码的函数
    def validate_tickers(potential_tickers):
        """验证股票代码，返回有效的代码"""
        if not potential_tickers:
            return default_tickers
            
        # 获取有效的股票代码列表
        valid_tickers = set(get_company_facts_tickers())
        
        # 过滤出有效的股票代码
        verified_tickers = list(set(potential_tickers).intersection(valid_tickers))
        
        # 如果原始ticker是有效的，且不在结果中，添加它
        if news_item.ticker and news_item.ticker not in verified_tickers and news_item.ticker in valid_tickers:
            verified_tickers.append(news_item.ticker)
        
        # 如果没有找到有效的股票代码，则使用原始的ticker
        if not verified_tickers:
            return default_tickers
            
        return verified_tickers
    
    # 首先尝试从实体信息中提取股票代码
    if news_item.entities:
        try:
            # 找出实体中的公司名称并使用ticker_lookup直接查询股票代码
            company_entities = []
            if "公司" in news_item.entities:
                company_entities.extend(news_item.entities["公司"])
            if "企业" in news_item.entities:
                company_entities.extend(news_item.entities["企业"])
            if "组织" in news_item.entities:
                company_entities.extend(news_item.entities["组织"])
            if "Company" in news_item.entities:
                company_entities.extend(news_item.entities["Company"])
            if "Organization" in news_item.entities:
                company_entities.extend(news_item.entities["Organization"])
            
            # 直接使用ticker_lookup查询已识别的公司实体
            potential_tickers = []
            for company in company_entities:
                ticker_results = lookup_ticker(company)
                for result in ticker_results:
                    ticker = result.get("ticker")
                    if ticker and validate_ticker(ticker):
                        potential_tickers.append(ticker.upper())
            
            # 如果有效使用ticker_lookup找到的股票代码，验证并返回
            if potential_tickers:
                # 确保原始ticker也被包含
                if news_item.ticker:
                    potential_tickers.append(news_item.ticker)
                return validate_tickers(potential_tickers)
            
            # 若直接查询没有结果，使用LLM分析实体信息，查找相关公司
            entity_prompt = ChatPromptTemplate.from_template("""
            你是一个金融数据专家，需要根据提供的实体信息，识别相关的公司及其股票代码。
            
            实体信息: {entities}
            
            主要相关股票代码: {ticker}
            
            任务:
            1. 分析提供的实体信息，识别所有可能的公司名称
            2. 对于每个公司，确定其可能的股票代码(例如 AAPL, MSFT, GOOGL等)
            3. 评估每个公司与主要股票代码的关系(例如竞争对手、供应商、合作伙伴等)
            
            请以JSON格式返回结果:
            {{
                "related_companies": [
                    {{
                        "name": "公司名称",
                        "ticker": "推测的股票代码",
                        "relationship": "与主要股票的关系"
                    }}
                ]
            }}
            
            注意:
            - 集中关注公司实体
            - 股票代码通常是1-5个大写字母
            - 如果无法确定某个公司的股票代码，请使用空字符串
            - 确保输出的是有效的JSON格式
            """)
            
            # 准备实体数据格式化
            entities_str = str(news_item.entities)
            
            # 创建实体分析请求
            prompt = entity_prompt.format(
                entities=entities_str,
                ticker=news_item.ticker or ""
            )
            
            # 定义响应模型
            class CompanyInfo(BaseModel):
                name: str = Field(..., description="公司名称")
                ticker: str = Field(..., description="推测的股票代码")
                relationship: str = Field(..., description="与主要股票的关系")
            
            class EntityAnalysisResult(BaseModel):
                related_companies: List[CompanyInfo] = Field(..., description="相关公司列表")
            
            # 调用LLM分析实体
            if model_name and model_provider:
                entity_result = call_llm(
                    prompt=prompt,
                    model_name=model_name,
                    model_provider=model_provider,
                    pydantic_model=EntityAnalysisResult,
                    agent_name="news_analyzer"
                )
                
                # 提取可能的股票代码和公司名称
                potential_tickers = []
                company_names = []
                if entity_result and entity_result.related_companies:
                    for company in entity_result.related_companies:
                        # 如果LLM提供了股票代码，直接使用
                        if company.ticker and len(company.ticker) <= 5:
                            potential_tickers.append(company.ticker.upper())
                        
                        # 同时收集公司名称，用于后续查询
                        if company.name and len(company.name) > 1:
                            company_names.append(company.name)
                
                # 对LLM未能提供股票代码但提供了名称的公司进行查询
                for company_name in company_names:
                    if company_name:
                        ticker_results = lookup_ticker(company_name)
                        for result in ticker_results:
                            ticker = result.get("ticker")
                            if ticker and validate_ticker(ticker) and ticker.upper() not in potential_tickers:
                                potential_tickers.append(ticker.upper())
                
                # 确保原始ticker也被包含
                if news_item.ticker:
                    potential_tickers.append(news_item.ticker)
                    
                # 验证并返回有效的股票代码
                return validate_tickers(potential_tickers)
                
        except Exception as e:
            print(f"分析实体信息提取股票代码时出错: {e}")
            # 如果实体分析失败，继续使用内容分析
    
    # 如果没有提供模型信息或实体分析失败，尝试使用文章内容进行分析
    if model_name and model_provider and article_content:
        try:
            # 构建提示模板
            llm_prompt = ChatPromptTemplate.from_template("""
            你是一个金融数据分析专家。请分析以下新闻内容，识别所有相关的公司和实体，然后确定它们可能的股票代码。
            
            新闻标题: {title}
            新闻日期: {date}
            主要相关股票: {ticker}
            新闻内容: 
            {content}
            
            分析要求:
            1. 仔细识别新闻中直接提到的所有公司名称
            2. 分析新闻中间接提到的相关公司（如供应商、竞争对手、合作伙伴等）
            3. 确定这些公司可能的股票代码（通常是大写字母缩写，如AAPL、MSFT等）
            
            请以JSON格式返回结果，结构如下:
            {{
                "identified_companies": [
                    {{
                        "name": "公司名称",
                        "possible_ticker": "可能的股票代码",
                        "relationship": "与主要公司的关系（如竞争对手、供应商等）"
                    }}
                ]
            }}
            
            注意:
            - 只包含与新闻内容相关的公司
            - 不要猜测股票代码，如果不确定就保留为空字符串
            - 务必包含新闻中明确提到的公司
            """)
            
            # 构建提示
            prompt = llm_prompt.format(
                title=news_item.title,
                date=news_item.date,
                ticker=news_item.ticker or "",
                content=article_content
            )
            
            # 定义响应模型
            class CompanyIdentification(BaseModel):
                name: str = Field(..., description="公司名称")
                possible_ticker: str = Field(..., description="可能的股票代码")
                relationship: str = Field(..., description="与主要公司的关系")
                
            class CompanyAnalysisResult(BaseModel):
                identified_companies: List[CompanyIdentification] = Field(..., description="识别的公司列表")
            
            # 调用LLM进行分析
            llm_result = call_llm(
                prompt=prompt,
                model_name=model_name,
                model_provider=model_provider,
                pydantic_model=CompanyAnalysisResult,
                agent_name="news_analyzer"
            )
            
            # 收集可能的股票代码和公司名称
            potential_tickers = []
            company_names = []
            
            # 如果LLM返回了结果，处理识别的公司
            if llm_result and llm_result.identified_companies:
                for company in llm_result.identified_companies:
                    # 如果LLM提供了股票代码，直接使用
                    if company.possible_ticker and len(company.possible_ticker) <= 5:
                        potential_tickers.append(company.possible_ticker.upper())
                    
                    # 同时收集公司名称，用于后续查询
                    if company.name and len(company.name) > 1:
                        company_names.append(company.name)
            
            # 对LLM未能提供股票代码但提供了名称的公司进行查询
            for company_name in company_names:
                if company_name:
                    ticker_results = lookup_ticker(company_name)
                    for result in ticker_results:
                        ticker = result.get("ticker")
                        if ticker and validate_ticker(ticker) and ticker.upper() not in potential_tickers:
                            potential_tickers.append(ticker.upper())
            
            # 确保原始ticker也被包含
            if news_item.ticker:
                potential_tickers.append(news_item.ticker)
                
            # 验证并返回有效的股票代码
            return validate_tickers(potential_tickers)
                
        except Exception as e:
            # 如果LLM分析失败，记录错误并返回默认值
            print(f"LLM分析提取股票代码时出错: {e}")
    
    # 如果以上方法都失败，返回默认ticker
    return default_tickers

def analyze_news(
    news_item: CompanyNews,
    article_content: str,
    model_name: str,
    model_provider: str
) -> NewsAnalysisResult:
    """
    分析新闻，提取相关股票代码并进行情感分析
    
    Args:
        news_item: 新闻项
        article_content: 文章内容
        model_name: 模型名称
        model_provider: 模型提供商
        
    Returns:
        分析结果
    """
    # 提取相关股票代码（使用相同的模型）
    # 优先使用实体信息中提取的股票代码
    potential_tickers = extract_stock_symbols(news_item, article_content, model_name, model_provider)
    
    # 如果没有找到任何潜在股票代码，直接返回只包含原始ticker的结果
    if not potential_tickers:
        return NewsAnalysisResult(
            related_tickers=[news_item.ticker],
            ticker_sentiments={
                news_item.ticker: TickerSentiment(
                    sentiment="neutral",
                    relevance=1.0,
                    reasoning="这是新闻原始关联的股票，但未找到明确的情感导向。"
                )
            }
        )
    
    # 创建提示模板
    prompt_template = ChatPromptTemplate.from_template("""
    你是一个专业的金融新闻分析师，需要分析以下新闻对各股票可能产生的影响和情感倾向。
    
    请遵循以下分析步骤：
    1. 仔细阅读新闻内容
    2. 识别新闻中提到的股票及其相关股票（如供应商、竞争对手等）
    3. 分析新闻对每只股票的情感影响
    4. 评估每只股票与新闻的相关程度（0.0到1.0的分数）
    
    股票列表，供参考：{potential_tickers}
    
    新闻信息:
    标题: {title}
    日期: {date}
    股票代码: {ticker}
    内容: {content}
    
    请对每只相关股票进行分析，使用以下情感等级:
    - strong negative (强烈负面): 可能导致股价大幅下跌
    - moderately negative (中度负面): 可能导致股价下跌
    - mildly negative (轻度负面): 可能导致股价小幅下跌
    - neutral (中性): 对股价影响不明确或无影响
    - mildly positive (轻度正面): 可能导致股价小幅上涨
    - moderately positive (中度正面): 可能导致股价上涨
    - strong positive (强烈正面): 可能导致股价大幅上涨
    
    请以JSON格式返回分析结果，包含以下字段:
    - related_tickers: 相关股票代码列表（必须是字符串数组）
    - ticker_sentiments: 每只股票的情感分析（必须是对象/字典），其中键是股票代码，值是包含sentiment、relevance、reasoning三个属性的对象
    
    示例格式:
    {{
      "related_tickers": ["AAPL", "MSFT"],
      "ticker_sentiments": {{
        "AAPL": {{
          "sentiment": "mildly positive",
          "relevance": 0.8,
          "reasoning": "分析理由"
        }},
        "MSFT": {{
          "sentiment": "neutral",
          "relevance": 0.5,
          "reasoning": "分析理由"
        }}
      }}
    }}
    
    注意：
    - 如果新闻提到多个股票，请分析每个相关股票的具体影响
    - 即使新闻主要关联的是一个股票代码，但如果内容显示对其他股票有重大影响，请准确分析这种关系
    - 相关性分数应基于新闻与该股票的直接相关程度，1.0表示完全相关，0.0表示完全不相关
    - 如果股票与新闻完全无关，请将相关程度设为0.0，这样的股票将被过滤掉
    - 只有在确定新闻与某股票真正相关时才包含该股票
    - 确保格式正确，related_tickers必须是数组，ticker_sentiments必须是对象/字典
    """)
    
    # 构建提示
    prompt = prompt_template.format(
        potential_tickers=potential_tickers,
        title=news_item.title,
        date=news_item.date,
        ticker=news_item.ticker,
        content=article_content or news_item.title
    )
    
    try:
        # 调用LLM进行分析
        result = call_llm(
            prompt=prompt,
            model_name=model_name,
            model_provider=model_provider,
            pydantic_model=NewsAnalysisResult,
            agent_name="news_analyzer"
        )
        
        # 过滤掉相关程度为0.0的股票
        filtered_tickers = []
        filtered_sentiments = {}
        
        for ticker, sentiment in result.ticker_sentiments.items():
            if sentiment.relevance > 0.0:
                filtered_tickers.append(ticker)
                filtered_sentiments[ticker] = sentiment
        
        # 如果过滤后没有相关股票，保留原始ticker
        if not filtered_tickers and news_item.ticker:
            filtered_tickers = [news_item.ticker]
            filtered_sentiments[news_item.ticker] = TickerSentiment(
                sentiment="neutral",
                relevance=1.0,
                reasoning="过滤掉所有相关程度为0的股票后，保留原始股票作为默认"
            )
        
        # 创建过滤后的结果
        filtered_result = NewsAnalysisResult(
            related_tickers=filtered_tickers,
            ticker_sentiments=filtered_sentiments
        )
        
        return filtered_result
    except Exception as e:
        print(f"分析新闻出错，使用基本分析结果: {e}")
        # 发生错误时返回基本结果
        return NewsAnalysisResult(
            related_tickers=potential_tickers,
            ticker_sentiments={
                news_item.ticker: TickerSentiment(
                    sentiment="neutral",
                    relevance=1.0,
                    reasoning="调用LLM时出现格式错误，使用默认中性情感。"
                )
            }
        )

def batch_analyze_news(
    news_items: List[CompanyNews],
    article_contents: List[str],
    model_name: str,
    model_provider: str,
    sentiment_model_name: Optional[str] = None,
    sentiment_model_provider: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    批量分析新闻
    
    Args:
        news_items: 新闻项列表
        article_contents: 文章内容列表
        model_name: 模型名称
        model_provider: 模型提供商
        sentiment_model_name: 情感分析专用模型名称（可选）
        sentiment_model_provider: 情感分析专用模型提供商（可选）
        
    Returns:
        增强后的新闻项列表
    """
    if not news_items:
        return []
        
    # 如果未指定情感分析专用模型，使用通用模型
    if not sentiment_model_name:
        sentiment_model_name = model_name
        sentiment_model_provider = model_provider
        
    # 记录总数和当前进度
    total_count = len(news_items)
    processed_count = 0
    enhanced_items = []
    
    # 处理每个新闻项
    for i, (news_item, article_content) in enumerate(zip(news_items, article_contents)):
        try:
            # 更新进度
            progress.update_status("news_analyzer", news_item.ticker, f"分析新闻 ({processed_count+1}/{total_count})")
            
            # 分析新闻
            analysis_result = analyze_news(
                news_item,
                article_content,
                sentiment_model_name,
                sentiment_model_provider
            )
            
            # 转换结果格式并过滤相关程度为0的股票
            sentiment_dict = {}
            filtered_tickers = []
            
            # 确保ticker_sentiments是字典类型
            if isinstance(analysis_result.ticker_sentiments, dict):
                for ticker, sentiment_data in analysis_result.ticker_sentiments.items():
                    # 只保留相关程度大于0的股票
                    if sentiment_data.relevance > 0.0:
                        sentiment_dict[ticker] = {
                            "sentiment": sentiment_data.sentiment,
                            "relevance": sentiment_data.relevance,
                            "reasoning": sentiment_data.reasoning
                        }
                        filtered_tickers.append(ticker)
            else:
                # 如果不是字典类型，使用默认值
                sentiment_dict = {
                    news_item.ticker: {
                        "sentiment": "neutral",
                        "relevance": 1.0,
                        "reasoning": "分析结果格式错误，使用默认中性情感"
                    }
                }
                filtered_tickers = [news_item.ticker]
            
            # 如果过滤后没有相关股票，至少保留原始ticker
            if not filtered_tickers and news_item.ticker:
                filtered_tickers = [news_item.ticker]
                sentiment_dict[news_item.ticker] = {
                    "sentiment": "neutral",
                    "relevance": 1.0,
                    "reasoning": "过滤掉所有相关程度为0的股票后，保留原始股票作为默认"
                }
            
            # 创建增强项
            enhanced_item = news_item.model_dump()
            
            # 使用过滤后的股票列表作为related_tickers
            enhanced_item["related_tickers"] = filtered_tickers
            enhanced_item["ticker_sentiments"] = sentiment_dict
            
            enhanced_items.append(enhanced_item)
            processed_count += 1
            
        except Exception as e:
            print(f"分析新闻时出错: {news_item.title} - {e}")
            # 添加一个基本结果以避免跳过
            enhanced_item = news_item.model_dump()
            
            # 尝试提取相关股票代码（即使发生错误，也尝试基本提取）
            try:
                related_tickers = extract_stock_symbols(news_item, article_content)
            except Exception:
                related_tickers = [news_item.ticker]
                
            enhanced_item["related_tickers"] = related_tickers
            enhanced_item["ticker_sentiments"] = {
                news_item.ticker: {
                    "sentiment": "neutral",
                    "relevance": 1.0,
                    "reasoning": "分析过程中发生错误，使用默认中性情感"
                }
            }
            
            enhanced_items.append(enhanced_item)
            processed_count += 1
    
    progress.update_status("news_analyzer", news_items[0].ticker if news_items else "", "完成")
    return enhanced_items 