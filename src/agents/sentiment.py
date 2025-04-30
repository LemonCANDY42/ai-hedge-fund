from langchain_core.messages import HumanMessage
from graph.state import AgentState, show_agent_reasoning
from utils.progress import progress
import pandas as pd
import numpy as np
import json

from tools.api import get_insider_trades, get_company_news

# 情感强度权重映射表
SENTIMENT_WEIGHTS = {
    "strong negative": -3.0,
    "moderately negative": -2.0,
    "mildly negative": -1.0,
    "neutral": 0.0,
    "mildly positive": 1.0,
    "moderately positive": 2.0,
    "strong positive": 3.0
}

def get_sentiment_score(sentiment_level):
    """将情感级别转换为数值分数"""
    return SENTIMENT_WEIGHTS.get(sentiment_level, 0.0)

def get_signal_from_score(score):
    """将分数转换为信号"""
    if score > 0.5:
        return "bullish"
    elif score < -0.5:
        return "bearish"
    else:
        return "neutral"

##### Sentiment Agent #####
def sentiment_agent(state: AgentState):
    """Analyzes market sentiment and generates trading signals for multiple tickers."""
    data = state.get("data", {})
    end_date = data.get("end_date")
    tickers = data.get("tickers")

    # Initialize sentiment analysis for each ticker
    sentiment_analysis = {}
    
    # 创建一个字典，用于跟踪所有情感影响，不仅限于原始tickers
    all_affected_tickers = {}
    
    # 首先，从所有新闻中收集所有相关股票的情感影响
    all_tickers_news_sentiment = {}

    for ticker in tickers:
        progress.update_status("sentiment_agent", ticker, "Fetching insider trades")

        # Get the insider trades
        insider_trades = get_insider_trades(
            ticker=ticker,
            end_date=end_date,
            limit=1000,
        )

        progress.update_status("sentiment_agent", ticker, "Analyzing trading patterns")

        # Get the signals from the insider trades (保持原有的内部交易分析)
        transaction_shares = pd.Series([t.transaction_shares for t in insider_trades]).dropna()
        insider_signals = np.where(transaction_shares < 0, "bearish", "bullish").tolist()
        
        # 将内部交易信号转换为数值分数：bearish=-1.0, bullish=1.0
        insider_scores = [1.0 if signal == "bullish" else -1.0 for signal in insider_signals]

        progress.update_status("sentiment_agent", ticker, "Fetching company news")

        # Get the company news
        company_news = get_company_news(ticker, end_date, limit=100)

        # 分析新闻情感
        progress.update_status("sentiment_agent", ticker, "Analyzing enhanced news sentiment")
        
        # 使用ticker_sentiments分析所有相关股票的情感
        for news in company_news:
            # 检查是否有增强情感分析数据
            if hasattr(news, 'ticker_sentiments') and news.ticker_sentiments:
                ticker_sentiments = news.ticker_sentiments
                
                # 处理所有相关ticker的情感，不仅限于当前ticker
                for related_ticker, sentiment_data in ticker_sentiments.items():
                    # 获取情感级别和相关性
                    sentiment_level = sentiment_data.get('sentiment', 'neutral')
                    relevance = sentiment_data.get('relevance', 0.0)
                    
                    # 计算情感得分（使用情感级别权重 * 相关性）
                    sentiment_score = get_sentiment_score(sentiment_level) * relevance
                    
                    # 将该新闻的情感影响添加到所有受影响股票的列表中
                    if related_ticker not in all_tickers_news_sentiment:
                        all_tickers_news_sentiment[related_ticker] = []
                    
                    all_tickers_news_sentiment[related_ticker].append({
                        "score": sentiment_score,
                        "relevance": relevance,
                        "original_ticker": news.ticker,
                        "news_title": news.title,
                        "sentiment_level": sentiment_level,
                        "reasoning": sentiment_data.get('reasoning', '')
                    })
        
        # 处理内部交易情感（仅适用于当前ticker）
        # 初始化该ticker的内部交易情感
        insider_sentiment = []
        
        for signal, value in zip(insider_signals, insider_scores):
            insider_sentiment.append({
                "score": value,
                "relevance": 1.0,  # 内部交易始终具有完全相关性
                "sentiment_level": "strong positive" if signal == "bullish" else "strong negative"
            })
        
        # 将内部交易数据添加到all_tickers_news_sentiment中
        if ticker not in all_tickers_news_sentiment:
            all_tickers_news_sentiment[ticker] = []
        
        all_tickers_news_sentiment[ticker].extend(insider_sentiment)
        
        # 收集所有受影响的ticker（包括新闻中提到的相关ticker）
        for affected_ticker in all_tickers_news_sentiment:
            if affected_ticker not in all_affected_tickers:
                all_affected_tickers[affected_ticker] = True
    
    # 现在，计算每个受影响ticker的最终情感
    for affected_ticker in all_affected_tickers:
        # 内部交易和新闻权重（如果该ticker有内部交易数据）
        insider_weight = 0.3
        news_weight = 0.7
        
        # 获取该ticker的所有情感数据
        ticker_sentiment_data = all_tickers_news_sentiment.get(affected_ticker, [])
        
        if not ticker_sentiment_data:
            continue  # 跳过没有任何情感数据的ticker
        
        # 分离内部交易和新闻情感
        insider_data = [item for item in ticker_sentiment_data if 'original_ticker' not in item]
        news_data = [item for item in ticker_sentiment_data if 'original_ticker' in item]
        
        # 计算加权情感分数
        total_score = 0.0
        total_weight = 0.0
        
        # 内部交易情感
        if insider_data:
            insider_score = sum(item["score"] for item in insider_data) / len(insider_data)
            total_score += insider_score * insider_weight
            total_weight += insider_weight
        
        # 新闻情感（加权平均，考虑相关性）
        if news_data:
            total_relevance = sum(item["relevance"] for item in news_data)
            if total_relevance > 0:
                weighted_news_score = sum(item["score"] * item["relevance"] for item in news_data) / total_relevance
                total_score += weighted_news_score * news_weight
                total_weight += news_weight
        
        # 计算最终分数和信号
        final_score = total_score / total_weight if total_weight > 0 else 0.0
        signal = get_signal_from_score(final_score)
        
        # 计算置信度（基于情感数据的数量和相关性）
        confidence = min(100, max(0, (
            len(insider_data) * 10 + 
            sum(item["relevance"] * 10 for item in news_data)
        )))
        
        # 生成详细的分析信息
        details = {
            "final_score": final_score,
            "signal": signal,
            "confidence": confidence,
            "insider_data_count": len(insider_data),
            "news_data_count": len(news_data),
            "top_news": sorted(news_data, key=lambda x: x["relevance"], reverse=True)[:3] if news_data else [],
        }
        
        # 生成分析理由
        if insider_data and news_data:
            reasoning = (
                f"综合分析基于{len(insider_data)}条内部交易记录和{len(news_data)}条相关新闻。"
                f"情感加权得分:{final_score:.2f}，信号:{signal}。"
                f"内部交易得分:{insider_score:.2f}，新闻加权得分:{weighted_news_score:.2f}，权重:{insider_weight}/{news_weight}。"
            )
        elif insider_data:
            reasoning = (
                f"分析基于{len(insider_data)}条内部交易记录，无相关新闻。"
                f"情感得分:{final_score:.2f}，信号:{signal}。"
            )
        elif news_data:
            reasoning = (
                f"分析基于{len(news_data)}条相关新闻，无内部交易记录。"
                f"情感加权得分:{final_score:.2f}，信号:{signal}。"
            )
        else:
            reasoning = "无足够数据进行分析，使用中性评估。"
        
        # 添加到分析结果
        sentiment_analysis[affected_ticker] = {
            "signal": signal,
            "confidence": confidence,
            "reasoning": reasoning,
            "details": details
        }
    
    # 确保原始请求的所有ticker都有结果（即使没有找到相关情感数据）
    for ticker in tickers:
        if ticker not in sentiment_analysis:
            sentiment_analysis[ticker] = {
                "signal": "neutral",
                "confidence": 0,
                "reasoning": "未找到相关情感数据，使用中性评估。"
            }
    
    # Create the sentiment message
    message = HumanMessage(
        content=json.dumps(sentiment_analysis),
        name="sentiment_agent",
    )

    # Print the reasoning if the flag is set
    if state["metadata"]["show_reasoning"]:
        show_agent_reasoning(sentiment_analysis, "Sentiment Analysis Agent")

    # Add the signal to the analyst_signals list
    state["data"]["analyst_signals"]["sentiment_agent"] = sentiment_analysis

    return {
        "messages": [message],
        "data": data,
    }
