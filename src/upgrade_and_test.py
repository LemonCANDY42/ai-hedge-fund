#!/usr/bin/env python3
"""
执行数据库迁移并测试新闻增强功能
"""

import sys
import os
import logging
from datetime import datetime, timedelta

# 设置日志
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """主函数：执行数据库迁移并测试新闻增强功能"""
    try:
        
        # 执行数据库迁移
        logger.info("升级数据库结构...")
        from data.migrations import upgrade_news_author_field
        upgrade_result = upgrade_news_author_field()
        
        if upgrade_result:
            logger.info("数据库结构升级成功")
        else:
            logger.info("数据库结构已是最新或无需升级")
        
        # 初始化数据库和缓存
        logger.info("初始化数据库和缓存...")
        from data.cache import init_cache
        init_cache()
        
        # 获取一个测试股票
        ticker = "AAPL"
        
        # 设置日期范围为最近30天
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        # 获取新闻数据（不增强）
        logger.info(f"获取 {ticker} 的新闻数据...")
        from tools.api import get_company_news
        news_items = get_company_news(ticker, end_date, start_date)
        
        logger.info(f"找到 {len(news_items)} 条新闻")
        
        if not news_items:
            logger.warning("没有找到新闻数据。请先刷新数据。")
            return
        
        # 显示几条新闻样本
        logger.info("新闻样本:")
        for i, news in enumerate(news_items[:3]):
            logger.info(f"  {i+1}. {news.title}")
            logger.info(f"     日期: {news.date}")
            logger.info(f"     来源: {news.source}")
            logger.info(f"     作者: {news.author}")
            logger.info(f"     URL: {news.url}")
            logger.info(f"     sentiment: {news.sentiment}")
            logger.info(f"     summary: {news.summary}")
            if news.categories:
                logger.info(f"     分类: {news.categories}")
            if news.entities:
                logger.info(f"     实体: {news.entities}")
            logger.info("")
        
        # 询问是否进行增强测试
        response = input("是否进行新闻增强测试? (y/n): ")
        if response.lower() != 'y':
            logger.info("退出测试")
            return
        
        # 选择默认使用Ollama的本地模型或者询问用户
        use_ollama = False
        if os.environ.get("OLLAMA_AVAILABLE") == "true":
            from utils.ollama import is_ollama_server_running, get_locally_available_models
            if is_ollama_server_running():
                models = get_locally_available_models()
                if models:
                    use_ollama = True
                    model_name = models[0]  # 使用第一个可用模型
                    logger.info(f"使用Ollama模型: {model_name}")
        
        if not use_ollama:
            model_name = "gemma3:12b"  # 默认模型
            logger.info(f"使用默认模型: {model_name}")
        
        # 测试新闻增强
        logger.info("测试新闻增强功能...")
        
        # 只测试前2条有URL的新闻
        news_with_url = [news for news in news_items if news.url]
        if not news_with_url:
            logger.warning("没有找到带URL的新闻，无法测试内容抓取功能")
            # 使用前两条无URL的新闻
            test_items = news_items[:min(2, len(news_items))]
        else:
            test_items = news_with_url[:min(2, len(news_with_url))]
        
        logger.info(f"选择了 {len(test_items)} 条新闻进行测试")
        
        from tools.news_enhancer import enhance_news_with_llm, update_news_with_enhancements, get_article_content
        from llm.models import ModelProvider
        
        # 先测试内容抓取
        for i, news in enumerate(test_items):
            if news.url:
                logger.info(f"测试抓取第 {i+1} 条新闻内容: {news.url}")
                content = get_article_content(news.url)
                logger.info(f"抓取结果: {len(content)} 字符")
                logger.info(f"内容预览: {content[:200]}..." if content else "无法获取内容")
        
        # 执行增强
        enhanced_items = enhance_news_with_llm(
            test_items,
            model_name, 
            ModelProvider.OLLAMA.value
        )
        
        if enhanced_items:
            logger.info(f"成功增强 {len(enhanced_items)} 条新闻")
            logger.info("增强示例:")
            for i, enhanced in enumerate(enhanced_items):
                logger.info(f"  {i+1}. {enhanced['title']}")
                logger.info(f"     原始sentiment: {test_items[i].sentiment}")
                logger.info(f"     保留的sentiment: {enhanced['sentiment']}")
                logger.info(f"     summary: {enhanced['summary'][:200]}..." if enhanced['summary'] else "无摘要")
                if enhanced['categories']:
                    logger.info(f"     分类: {enhanced['categories']}")
                if enhanced['entities']:
                    logger.info(f"     实体示例: ")
                    for entity_type, entities in list(enhanced['entities'].items())[:3]:
                        if entities:
                            logger.info(f"       {entity_type}: {', '.join(entities[:5])}")
                logger.info("")
            
            # 测试更新到数据库
            logger.info("测试更新到数据库...")
            update_result = update_news_with_enhancements(enhanced_items, force_update=True)
            
            if update_result:
                logger.info("更新到数据库成功")
            else:
                logger.error("更新到数据库失败")
        else:
            logger.error("新闻增强失败")
        
        logger.info("测试完成")
        
    except Exception as e:
        logger.error(f"测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    main() 