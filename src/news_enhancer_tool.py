#!/usr/bin/env python3
"""
命令行工具用于增强新闻数据
这个工具可以使用LLM对公司新闻数据进行增强，添加摘要、实体识别和分类。
"""

import argparse
import datetime
import sys
import os
from typing import List, Optional

from colorama import Fore, Style, init
import questionary

from data.cache import init_cache, get_cache
from tools.news_enhancer import enhance_ticker_news, enhance_multiple_tickers
from tools.api import get_company_news
from llm.models import (
    AVAILABLE_MODELS, OLLAMA_MODELS, get_lmstudio_models, ModelProvider, 
    LLM_ORDER, OLLAMA_LLM_ORDER, get_model_info
)
from utils.ollama import (
    is_ollama_installed, is_ollama_server_running, get_locally_available_models,
    download_model, ensure_ollama_and_model
)
from utils.lmstudio import is_lmstudio_server_running, ensure_lmstudio_server

# 初始化colorama
init(autoreset=True)

# 初始化缓存系统
init_cache()


def initialize_db():
    """确保数据库和缓存系统已初始化"""
    try:
        init_cache()
    except Exception as e:
        print(f"初始化数据库和缓存系统时出错: {e}")
        sys.exit(1)


def select_model():
    """
    选择LLM模型
    
    Returns:
        Tuple[str, str]: 模型名称和提供商
    """
    # 选择模型提供商
    provider_choice = questionary.select(
        "选择模型提供商:",
        choices=[
            questionary.Choice("Ollama（本地运行）", "ollama"),
            questionary.Choice("LM Studio（本地运行）", "lmstudio"),
            questionary.Choice("云服务提供商（OpenAI/Anthropic等）", "cloud")
        ],
        style=questionary.Style([
            ("selected", "fg:green bold"),
            ("pointer", "fg:green bold"),
            ("highlighted", "fg:green"),
            ("answer", "fg:green bold"),
        ])
    ).ask()
    
    if not provider_choice:
        print("\n\n中断接收。退出...")
        sys.exit(0)
    
    if provider_choice == "ollama":
        # 确保Ollama已安装且运行
        if not is_ollama_installed():
            print(f"{Fore.RED}Ollama 未安装在您的系统上。{Style.RESET_ALL}")
            sys.exit(1)
        
        # 确保Ollama服务正在运行
        if not is_ollama_server_running():
            print(f"{Fore.RED}Ollama 服务未运行。请先启动Ollama服务。{Style.RESET_ALL}")
            sys.exit(1)
        
        # 获取本地可用模型
        local_models = get_locally_available_models()
        
        # 如果没有本地模型，提示下载
        if not local_models:
            print(f"{Fore.YELLOW}未发现本地Ollama模型。请先下载模型。{Style.RESET_ALL}")
            
            # 提供默认模型列表供下载
            model_choice = questionary.select(
                "选择要下载的模型:",
                choices=[model.display_name for model in OLLAMA_MODELS],
                style=questionary.Style([
                    ("selected", "fg:green bold"),
                    ("pointer", "fg:green bold"),
                    ("highlighted", "fg:green"),
                    ("answer", "fg:green bold"),
                ])
            ).ask()
            
            if not model_choice:
                print("\n\n中断接收。退出...")
                sys.exit(0)
            
            # 获取模型名称
            model_name = next((model.model_name for model in OLLAMA_MODELS if model.display_name == model_choice), None)
            
            if not model_name:
                print(f"{Fore.RED}无法找到所选模型的配置。退出...{Style.RESET_ALL}")
                sys.exit(1)
            
            # 下载模型
            print(f"{Fore.CYAN}正在下载模型 {model_name}...{Style.RESET_ALL}")
            if not download_model(model_name):
                print(f"{Fore.RED}下载模型失败。请手动下载或选择其他模型。{Style.RESET_ALL}")
                sys.exit(1)
                
            print(f"{Fore.GREEN}模型下载成功。{Style.RESET_ALL}")
            
            # 更新本地模型列表
            local_models = get_locally_available_models()
        
        # 从本地模型中选择
        model_choice = questionary.select(
            "选择Ollama模型:",
            choices=local_models,
            style=questionary.Style([
                ("selected", "fg:green bold"),
                ("pointer", "fg:green bold"),
                ("highlighted", "fg:green"),
                ("answer", "fg:green bold"),
            ])
        ).ask()
        
        if not model_choice:
            print("\n\n中断接收。退出...")
            sys.exit(0)
            
        return model_choice, ModelProvider.OLLAMA.value
    
    elif provider_choice == "lmstudio":
        # 确保LM Studio服务正在运行
        if not ensure_lmstudio_server():
            print(f"{Fore.RED}无法继续，因为LM Studio服务未运行。{Style.RESET_ALL}")
            sys.exit(1)
        
        # 获取LM Studio模型
        lmstudio_models = get_lmstudio_models()
        if not lmstudio_models:
            print(f"{Fore.RED}LM Studio中没有可用模型。请先在LM Studio中添加模型。{Style.RESET_ALL}")
            sys.exit(1)
            
        lmstudio_choices = [
            questionary.Choice(model.display_name, value=model.model_name) 
            for model in lmstudio_models
        ]
        
        # 从LM Studio模型中选择
        model_choice = questionary.select(
            "选择LM Studio模型:",
            choices=lmstudio_choices,
            style=questionary.Style([
                ("selected", "fg:green bold"),
                ("pointer", "fg:green bold"),
                ("highlighted", "fg:green"),
                ("answer", "fg:green bold"),
            ])
        ).ask()
        
        if not model_choice:
            print("\n\n中断接收。退出...")
            sys.exit(0)
            
        return model_choice, ModelProvider.LMSTUDIO.value
    
    else:  # cloud
        # 从云服务提供商模型中选择
        model_choice = questionary.select(
            "选择LLM模型:",
            choices=[questionary.Choice(display, value=value) for display, value, _ in LLM_ORDER],
            style=questionary.Style([
                ("selected", "fg:green bold"),
                ("pointer", "fg:green bold"),
                ("highlighted", "fg:green"),
                ("answer", "fg:green bold"),
            ])
        ).ask()

        if not model_choice:
            print("\n\n中断接收。退出...")
            sys.exit(0)
        else:
            # 获取模型信息
            model_info = get_model_info(model_choice)
            if model_info:
                model_provider = model_info.provider.value
                print(f"\n已选择 {Fore.CYAN}{model_provider}{Style.RESET_ALL} 模型: {Fore.GREEN + Style.BRIGHT}{model_choice}{Style.RESET_ALL}\n")
                
                # 检查环境变量
                env_var_name = f"{model_provider.upper()}_API_KEY"
                if model_provider == ModelProvider.GEMINI:
                    env_var_name = "GOOGLE_API_KEY"
                
                if not os.environ.get(env_var_name):
                    print(f"{Fore.RED}错误：未找到 {env_var_name} 环境变量。请在 .env 文件中设置 API 密钥。{Style.RESET_ALL}")
                    sys.exit(1)
                
                return model_choice, model_provider
            else:
                print(f"{Fore.RED}无法找到所选模型的配置。退出...{Style.RESET_ALL}")
                sys.exit(1)


def enhance_news(args):
    """增强新闻数据"""
    # 处理日期
    if args.end_date:
        end_date = args.end_date
    else:
        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
    if args.start_date:
        start_date = args.start_date
    else:
        # 默认为结束日期前90天
        start_date = (datetime.datetime.now() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
    
    print(f"时间范围: {start_date} 到 {end_date}")
    
    # 选择模型
    if not (args.model_name and args.model_provider):
        model_name, model_provider = select_model()
    else:
        model_name = args.model_name
        model_provider = args.model_provider
    
    print(f"使用模型: {model_name} ({model_provider})")
    
    # 处理刷新选项
    force_update = args.force_update
    
    # 处理批处理选项
    batch_size = args.batch_size
    
    # 处理限制选项
    limit = args.limit
    
    # 处理股票代码
    ticker = args.ticker
    if ticker and ticker.lower() != 'all':
        # 增强单个股票的新闻
        print(f"增强 {ticker} 的新闻数据...")
        
        # 获取现有的新闻数据以显示信息
        news_items = get_company_news(ticker, end_date, start_date)
        total_news = len(news_items)
        
        print(f"找到 {total_news} 条 {ticker} 的新闻")
        
        if total_news == 0:
            print("没有找到可增强的新闻。退出。")
            return
            
        if limit and limit < total_news:
            print(f"将只处理 {limit}/{total_news} 条新闻")
            
        # 增强新闻
        result = enhance_ticker_news(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            model_name=model_name,
            model_provider=model_provider,
            limit=limit,
            force_update=force_update,
            batch_size=batch_size
        )
        
        if result:
            print(f"{Fore.GREEN}成功增强 {ticker} 的新闻数据。{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}增强 {ticker} 的新闻数据失败。{Style.RESET_ALL}")
    
    else:
        # 获取要处理的所有股票
        if args.tickers:
            tickers = [t.strip() for t in args.tickers.split(',')]
        else:
            # 从缓存中获取所有唯一的股票代码
            cache = get_cache()
            all_tickers = cache.get_all_tickers()
            
            if not all_tickers:
                print("没有找到任何股票数据。请先获取数据。")
                return
            
            # 选择要处理的股票
            ticker_choice = questionary.checkbox(
                "选择要处理的股票:",
                choices=all_tickers,
                style=questionary.Style([
                    ("selected", "fg:green bold"),
                    ("pointer", "fg:green bold"),
                    ("highlighted", "fg:green"),
                    ("answer", "fg:green bold"),
                ])
            ).ask()
            
            if not ticker_choice:
                print("未选择任何股票。退出。")
                return
                
            tickers = ticker_choice
        
        # 增强多个股票的新闻
        print(f"将处理以下股票的新闻数据: {', '.join(tickers)}")
        
        # 检查每个股票的新闻数量
        ticker_news_counts = {}
        for t in tickers:
            news_items = get_company_news(t, end_date, start_date)
            ticker_news_counts[t] = len(news_items)
            
        # 显示每个股票的新闻数量
        print("\n股票新闻数量:")
        for t, count in ticker_news_counts.items():
            print(f"  {t}: {count} 条新闻")
            
        # 确认是否继续
        if not args.yes and not questionary.confirm("是否继续增强这些新闻数据?").ask():
            print("操作已取消。")
            return
            
        # 增强多个股票的新闻
        results = enhance_multiple_tickers(
            tickers=tickers,
            start_date=start_date,
            end_date=end_date,
            model_name=model_name,
            model_provider=model_provider,
            limit_per_ticker=limit,
            force_update=force_update,
            batch_size=batch_size
        )
        
        # 显示结果
        success_count = sum(1 for r in results.values() if r)
        print(f"\n增强结果: {success_count}/{len(results)} 个股票成功")
        
        for t, result in results.items():
            status = f"{Fore.GREEN}成功{Style.RESET_ALL}" if result else f"{Fore.RED}失败{Style.RESET_ALL}"
            print(f"  {t}: {status}")


def check_news(args):
    """检查新闻数据增强状态"""
    # 处理股票代码
    ticker = args.ticker
    
    # 处理日期
    if args.end_date:
        end_date = args.end_date
    else:
        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
    if args.start_date:
        start_date = args.start_date
    else:
        # 默认为结束日期前90天
        start_date = (datetime.datetime.now() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
    
    print(f"检查 {ticker} 在 {start_date} 到 {end_date} 的新闻数据增强状态")
    
    # 获取新闻数据
    news_items = get_company_news(ticker, end_date, start_date)
    
    if not news_items:
        print(f"未找到 {ticker} 在指定时间范围内的新闻")
        return
    
    # 计算增强状态
    total_count = len(news_items)
    enhanced_count = sum(1 for n in news_items if n.summary and n.categories and n.entities)
    
    # 计算完成百分比
    percentage = (enhanced_count / total_count) * 100 if total_count > 0 else 0
    
    # 显示统计信息
    print(f"\n新闻总数: {total_count}")
    print(f"已增强数量: {enhanced_count} ({percentage:.1f}%)")
    print(f"未增强数量: {total_count - enhanced_count}")
    
    # 显示最近的几条新闻及其增强状态
    if args.show_samples and news_items:
        sample_count = min(5, len(news_items))
        print(f"\n最近 {sample_count} 条新闻的增强状态:")
        
        for i, news in enumerate(news_items[:sample_count]):
            status = f"{Fore.GREEN}已增强{Style.RESET_ALL}" if news.summary and news.categories and news.entities else f"{Fore.RED}未增强{Style.RESET_ALL}"
            print(f"  {i+1}. {news.title[:50]}... ({status})")
            
            if args.verbose and news.summary:
                print(f"     摘要: {news.summary[:100]}...")
                if news.categories:
                    print(f"     分类: {', '.join(news.categories)}")
                if news.entities:
                    for entity_type, entities in news.entities.items():
                        if entities:
                            print(f"     {entity_type}: {', '.join(entities[:5])}")


def main():
    """主函数，解析命令行参数并执行相应操作"""
    parser = argparse.ArgumentParser(description="新闻数据增强工具")
    subparsers = parser.add_subparsers(dest="command", help="要执行的命令")
    
    # enhance命令
    enhance_parser = subparsers.add_parser("enhance", help="增强新闻数据")
    enhance_parser.add_argument("ticker", help="股票代码，或'all'表示所有股票")
    enhance_parser.add_argument("--start-date", help="开始日期 (YYYY-MM-DD)，默认为3个月前")
    enhance_parser.add_argument("--end-date", help="结束日期 (YYYY-MM-DD)，默认为今天")
    enhance_parser.add_argument("--limit", type=int, help="每个股票处理的新闻项数量上限")
    enhance_parser.add_argument("--force-update", action="store_true", help="强制更新现有的增强数据")
    enhance_parser.add_argument("--batch-size", type=int, default=1, help="批处理大小，每次调用LLM处理的新闻项数量")
    enhance_parser.add_argument("--model-name", help="LLM模型名称（如不提供则交互式选择）")
    enhance_parser.add_argument("--model-provider", help="LLM模型提供商（如不提供则交互式选择）")
    enhance_parser.add_argument("--tickers", help="逗号分隔的股票代码列表（当ticker='all'时使用）")
    enhance_parser.add_argument("--yes", "-y", action="store_true", help="自动确认所有提示")
    
    # check命令
    check_parser = subparsers.add_parser("check", help="检查新闻数据增强状态")
    check_parser.add_argument("ticker", help="股票代码")
    check_parser.add_argument("--start-date", help="开始日期 (YYYY-MM-DD)，默认为3个月前")
    check_parser.add_argument("--end-date", help="结束日期 (YYYY-MM-DD)，默认为今天")
    check_parser.add_argument("--show-samples", action="store_true", help="显示样本新闻及其增强状态")
    check_parser.add_argument("--verbose", "-v", action="store_true", help="显示详细信息")
    
    args = parser.parse_args()
    
    # 如果没有指定子命令，显示帮助信息
    if not args.command:
        parser.print_help()
        return
    
    # 确保数据库和缓存系统已初始化
    initialize_db()
    
    # 执行相应的命令
    if args.command == "enhance":
        enhance_news(args)
    elif args.command == "check":
        check_news(args)


if __name__ == "__main__":
    main() 