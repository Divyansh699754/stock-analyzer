# Stock Analyzer — AI-Powered Daily Analysis (US + India)

Daily stock analysis tool that fetches market data, calculates technical indicators, searches news, sends everything to Google Gemini AI, and delivers Buy/Hold/Sell signals via Telegram.

## Features

- **Multi-market**: US stocks (AAPL, TSLA) + Indian stocks (RELIANCE.NS, TCS.NS)
- **Technical indicators**: MA, MACD, RSI, BIAS, Bollinger Bands, Volume Ratio
- **AI analysis**: Google Gemini (free tier) with OpenAI-compatible fallback
- **News integration**: Tavily (primary) + SerpAPI (fallback)
- **Notifications**: Telegram dashboard + Email
- **Backtesting**: Rules-only mode (instant) + LLM mode (multi-day via GitHub Actions)
- **Automated**: GitHub Actions for daily runs — zero manual work

## Quick Start

### 1. Install dependencies

```bash
cd stock-analyzer
pip install -r requirements.txt
```

### 2. Set up API keys

```bash
cp .env.example .env
# Edit .env with your API keys
```

**Required**: At least `GEMINI_API_KEY` (free from https://aistudio.google.com)

**Optional**: `TAVILY_API_KEYS`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

### 3. Run analysis

```bash
# Analyze specific stocks (no notifications)
python main.py --stocks AAPL,RELIANCE.NS --no-notify

# Full analysis with default watchlist
python main.py

# JSON output
python main.py --stocks AAPL --output json

# Market overview only
python main.py --market-review
```

## CLI Options

| Flag | Description |
|------|-------------|
| `--stocks AAPL,TCS.NS` | Override stock list |
| `--no-notify` | Skip Telegram/Email notifications |
| `--market-review` | Only show market index overview |
| `--schedule` | Enter scheduled mode (daily at SCHEDULE_TIME) |
| `--output json` | Print raw JSON to stdout |
| `--verbose` | Debug logging |
| `--dry-run` | Run analysis, skip notifications |

## Backtesting

### Rules-Only (instant, free)

```bash
python -m backtest.engine \
  --mode rules-only \
  --symbols AAPL,RELIANCE.NS \
  --start 2020-01-01 \
  --end 2025-12-31 \
  --cash-usd 10000 \
  --cash-inr 1000000
```

### LLM Mode (uses Gemini API)

```bash
python -m backtest.engine \
  --mode llm \
  --symbols AAPL \
  --start 2020-01-01 \
  --end 2025-12-31 \
  --max-api-calls 100
```

For multi-day backtests, use GitHub Actions (see `.github/workflows/backtest.yml`).

## GitHub Actions

### Daily Analysis
Runs automatically Mon-Fri after market close. Set secrets in repo settings:
- `GEMINI_API_KEY`
- `STOCK_LIST`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TAVILY_API_KEYS` (optional)

### Backtest
Trigger manually from Actions tab. Resumes automatically via cron for LLM mode.

## Environment Variables

See `.env.example` for the full list.

## Project Structure

```
stock-analyzer/
├── main.py                  # CLI entry point
├── config.py                # Environment config + market detection
├── src/
│   ├── data_fetcher.py      # yfinance wrapper
│   ├── technical_analysis.py # Indicators (MA, MACD, RSI, etc.)
│   ├── ai_analyzer.py       # Prompt builder + LLM caller + parser
│   ├── stock_pipeline.py    # Per-stock orchestration
│   ├── news_search.py       # Tavily/SerpAPI
│   ├── notification.py      # Telegram + Email
│   ├── market_review.py     # Index overview
│   ├── storage.py           # JSON/Markdown reports
│   └── scheduler.py         # APScheduler
├── backtest/
│   ├── engine.py            # Rules-only + LLM modes
│   ├── portfolio.py         # Simulated portfolio
│   ├── state.py             # Save/resume state
│   └── report_generator.py  # Plotly charts + stats
├── templates/
│   └── analysis_prompt.txt  # LLM prompt template
└── .github/workflows/
    ├── daily_analysis.yml
    └── backtest.yml
```

## Disclaimer

Not financial advice. Not SEC/SEBI registered. Educational purposes only.
