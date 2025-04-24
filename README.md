# AI Hedge Fund

This is a proof of concept for an AI-powered hedge fund.  The goal of this project is to explore the use of AI to make trading decisions.  This project is for **educational** purposes only and is not intended for real trading or investment.

This system employs several agents working together:

1. Ben Graham Agent - The godfather of value investing, only buys hidden gems with a margin of safety
2. Bill Ackman Agent - An activist investors, takes bold positions and pushes for change
3. Cathie Wood Agent - The queen of growth investing, believes in the power of innovation and disruption
4. Charlie Munger Agent - Warren Buffett's partner, only buys wonderful businesses at fair prices
5. Michael Burry Agent - The Big Short contrarian who hunts for deep value
6. Peter Lynch Agent - Practical investor who seeks "ten-baggers" in everyday businesses
7. Phil Fisher Agent - Meticulous growth investor who uses deep "scuttlebutt" research 
8. Stanley Druckenmiller Agent - Macro legend who hunts for asymmetric opportunities with growth potential
9. Warren Buffett Agent - The oracle of Omaha, seeks wonderful companies at a fair price
10. Valuation Agent - Calculates the intrinsic value of a stock and generates trading signals
11. Sentiment Agent - Analyzes market sentiment and generates trading signals
12. Fundamentals Agent - Analyzes fundamental data and generates trading signals
13. Technicals Agent - Analyzes technical indicators and generates trading signals
14. Risk Manager - Calculates risk metrics and sets position limits
15. Portfolio Manager - Makes final trading decisions and generates orders
    

<img width="1042" alt="Screenshot 2025-03-22 at 6 19 07 PM" src="https://github.com/user-attachments/assets/cbae3dcf-b571-490d-b0ad-3f0f035ac0d4" />

**Note**: the system simulates trading decisions, it does not actually trade.

**TODO:**

1. Add local persistent caching of historical financial data.
2. By obtaining historical information before a certain moment, combining the characteristics of different experts, using reinforcement learning to generate expected transaction summary, and changing it to a predictive thinking process, using frameworks such as LLaMA-Factory/unsloth to fine-tune the various agents represented by llm (priority for MoE).

[![Twitter Follow](https://img.shields.io/twitter/follow/virattt?style=social)](https://twitter.com/virattt)

## Disclaimer

This project is for **educational and research purposes only**.

- Not intended for real trading or investment
- No warranties or guarantees provided
- Past performance does not indicate future results
- Creator assumes no liability for financial losses
- Consult a financial advisor for investment decisions

By using this software, you agree to use it solely for learning purposes.

## Table of Contents
- [Setup](#setup)
- [Usage](#usage)
  - [Running the Hedge Fund](#running-the-hedge-fund)
  - [Running the Backtester](#running-the-backtester)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [Feature Requests](#feature-requests)
- [License](#license)

## Setup

Clone the repository:
```bash
git clone https://github.com/virattt/ai-hedge-fund.git
cd ai-hedge-fund
```

1. Install Poetry (if not already installed):
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

2. Install dependencies:
```bash
poetry install
```

3. Set up your environment variables:
```bash
# Create .env file for your API keys
cp .env.example .env
```

4. Set your API keys:
```bash
# For running LLMs hosted by openai (gpt-4o, gpt-4o-mini, etc.)
# Get your OpenAI API key from https://platform.openai.com/
OPENAI_API_KEY=your-openai-api-key

# For running LLMs hosted by groq (deepseek, llama3, etc.)
# Get your Groq API key from https://groq.com/
GROQ_API_KEY=your-groq-api-key

# For getting financial data to power the hedge fund
# Get your Financial Datasets API key from https://financialdatasets.ai/
FINANCIAL_DATASETS_API_KEY=your-financial-datasets-api-key
```

**Important**: You must set `OPENAI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, or `DEEPSEEK_API_KEY` for the hedge fund to work.  If you want to use LLMs from all providers, you will need to set all API keys.

Financial data for AAPL, GOOGL, MSFT, NVDA, and TSLA is free and does not require an API key.

For any other ticker, you will need to set the `FINANCIAL_DATASETS_API_KEY` in the .env file.

### Local LLM Setup (Optional)

To use local LLMs, you can set up either Ollama or LM Studio:

#### Ollama
1. Download and install [Ollama](https://ollama.com/) for your platform
2. Start the Ollama server
3. Use the `--ollama` flag when running the hedge fund

#### LM Studio
1. Download and install [LM Studio](https://lmstudio.ai/) for your platform
2. Launch LM Studio and load your desired model
3. Enable the "OpenAI Compatible Server" in Settings > Local Inference Server
4. Use the `--lmstudio` flag when running the hedge fund

## Usage

### Running the Hedge Fund
```bash
poetry run python src/main.py --ticker AAPL,MSFT,NVDA
```

**Example Output:**
<img width="992" alt="Screenshot 2025-01-06 at 5 50 17 PM" src="https://github.com/user-attachments/assets/e8ca04bf-9989-4a7d-a8b4-34e04666663b" />

You can also specify a `--ollama` flag to run the AI hedge fund using local LLMs.

```bash
poetry run python src/main.py --ticker AAPL,MSFT,NVDA --ollama
```

You can also specify a `--lmstudio` flag to run the AI hedge fund using LM Studio for local LLM inference.

```bash
poetry run python src/main.py --ticker AAPL,MSFT,NVDA --lmstudio
```

You can also specify a `--show-reasoning` flag to print the reasoning of each agent to the console.

```bash
poetry run python src/main.py --ticker AAPL,MSFT,NVDA --show-reasoning
```
You can optionally specify the start and end dates to make decisions for a specific time period.

```bash
poetry run python src/main.py --ticker AAPL,MSFT,NVDA --start-date 2024-01-01 --end-date 2024-03-01 
```

### Running the Backtester

```bash
poetry run python src/backtester.py --ticker AAPL,MSFT,NVDA
```

**Example Output:**
<img width="941" alt="Screenshot 2025-01-06 at 5 47 52 PM" src="https://github.com/user-attachments/assets/00e794ea-8628-44e6-9a84-8f8a31ad3b47" />


You can optionally specify the start and end dates to backtest over a specific time period.

```bash
poetry run python src/backtester.py --ticker AAPL,MSFT,NVDA --start-date 2024-01-01 --end-date 2024-03-01
```

You can also specify a `--ollama` flag to run the backtester using local LLMs.
```bash
poetry run python src/backtester.py --ticker AAPL,MSFT,NVDA --ollama
```

You can also specify a `--lmstudio` flag to run the backtester using LM Studio for local LLM inference.
```bash
poetry run python src/backtester.py --ticker AAPL,MSFT,NVDA --lmstudio
```


## Project Structure 
```
ai-hedge-fund/
├── src/
│   ├── agents/                   # Agent definitions and workflow
│   │   ├── bill_ackman.py        # Bill Ackman agent
│   │   ├── fundamentals.py       # Fundamental analysis agent
│   │   ├── portfolio_manager.py  # Portfolio management agent
│   │   ├── risk_manager.py       # Risk management agent
│   │   ├── sentiment.py          # Sentiment analysis agent
│   │   ├── technicals.py         # Technical analysis agent
│   │   ├── valuation.py          # Valuation analysis agent
│   │   ├── ...                   # Other agents
│   │   ├── warren_buffett.py     # Warren Buffett agent
│   │   ├── ...                   # Other agents
│   │	├── data/    
│   │   │	├── cache.py              # Cache system
│   │   └── ...                   # Other cache-related files
│   ├── tools/                    # Agent tools
│   │   ├── api.py                # API tools
│   │   └── ...                   # Other tools
│   ├── backtester.py             # Backtesting tools
│   ├── main.py                   # Main entry point
│   ├── ollama_utils.py           # Utilities for using Ollama
│   ├── lmstudio_utils.py         # Utilities for using LM Studio
├── pyproject.toml
├── ...
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

**Important**: Please keep your pull requests small and focused.  This will make it easier to review and merge.

## Feature Requests

If you have a feature request, please open an [issue](https://github.com/virattt/ai-hedge-fund/issues) and make sure it is tagged with `enhancement`.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

# AI Hedge Fund - Local Persistent Caching System

This repository contains a flexible caching system for financial data, designed to minimize external API calls while providing efficient data access patterns.

## Features

- **Multi-level Caching**: Support for Redis, SQLite/PostgreSQL, and in-memory caching
- **Graceful Degradation**: Automatically falls back to less persistent cache levels if a level is unavailable
- **Configurable Cache Modes**: Choose between full persistence, Redis-only, memory-only, or no caching
- **Thread-safe Access**: Safe for concurrent data retrieval and updates

## Cache Architecture

The system implements a hierarchical caching model:

1. **Redis Cache (Fast)**: Primary cache for frequently accessed data
2. **SQL Database (Persistent)**: Long-term storage and data persistence
3. **Memory Cache (Fallback)**: Used when Redis is unavailable
4. **No Cache**: Direct API usage when all cache levels are disabled

## Configuration

The caching system can be configured via environment variables:

| Variable | Description | Default | Options |
|----------|-------------|---------|---------|
| `CACHE_MODE` | Cache operation mode | `full` | `full`, `redis`, `memory`, `none` |
| `DATABASE_URL` | Database connection string | `sqlite:///./data.db` | Any SQLAlchemy URL |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` | Any Redis URL |
| `REDIS_EXPIRATION` | Redis cache TTL (seconds) | `604800` (7 days) | Any integer |
| `AUTO_INITIALIZE` | Auto-initialize on import | `true` | `true`, `false` |

## Cache Modes

- **Full Mode** (`full`): Uses both Redis and Database for maximum performance and persistence
- **Redis Mode** (`redis`): Uses only Redis, no database persistence
- **Memory Mode** (`memory`): Uses only in-memory cache, no persistence
- **No Cache** (`none`): Disables all caching, data is fetched directly from API

## Usage Example

```python
from data.cache import get_cache

# Get the cache instance
cache = get_cache()

# Retrieve price data (tries cache first, then database if cache misses)
prices = cache.get_prices("AAPL", start_date="2023-01-01", end_date="2023-01-31")

# Store new data (updates both cache and database)
new_prices = [
    {
        "ticker": "AAPL",
        "time": "2023-02-01T00:00:00",
        "open": 150.0,
        "close": 155.0,
        "high": 156.0,
        "low": 149.0,
        "volume": 1000000
    }
]
cache.set_prices("AAPL", new_prices)
```

## Support for Different Data Types

The caching system supports various financial data types:

- **Price Data**: Historical OHLCV data
- **Financial Metrics**: Key financial ratios and metrics
- **Financial Line Items**: Detailed financial statement entries
- **Insider Trades**: Company insider transaction data
- **Company News**: News articles related to companies

## Error Handling and Monitoring

The system includes comprehensive logging to track cache hits, misses, and errors. If a cache level fails, the system automatically degrades to the next available level.

## Performance Considerations

- **Redis**: Optimal for high-throughput scenarios with moderate memory requirements
- **Database**: Best for long-term storage and complex queries
- **Memory**: Fastest but volatile, use for temporary caching
