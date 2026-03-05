"""
Stock pipeline — per-stock orchestration: fetch → indicators → news → LLM → parse.
"""

import time
import logging

from config import Config, detect_market
from src.data_fetcher import fetch_stock_data
from src.technical_analysis import calculate_indicators
from src.ai_analyzer import build_prompt, call_llm, parse_analysis

logger = logging.getLogger(__name__)


def analyze_stock(symbol: str, config: Config, news_fn=None) -> dict | None:
    """
    Run the full analysis pipeline for a single stock.

    Args:
        symbol: Stock symbol (e.g. 'AAPL', 'RELIANCE.NS')
        config: Config instance
        news_fn: Optional callable(stock_name, market_info) -> list of news dicts.
                 If None, news is skipped.

    Returns dict with analysis results, or None on failure.
    """
    logger.info(f'Analyzing {symbol}...')

    # 1. Fetch data
    stock_data = fetch_stock_data(symbol)
    if stock_data is None:
        logger.error(f'Failed to fetch data for {symbol}')
        return None

    # 2. Calculate indicators
    try:
        indicators = calculate_indicators(stock_data['history'])
    except Exception as e:
        logger.error(f'Indicator calculation failed for {symbol}: {e}')
        return None

    # 3. Search news (optional)
    news = []
    if news_fn:
        try:
            market_info = detect_market(symbol)
            news = news_fn(stock_data['name'], market_info) or []
        except Exception as e:
            logger.warning(f'News search failed for {symbol}: {e}')

    # 4. Build prompt and call LLM
    try:
        prompt = build_prompt(stock_data, indicators, news, config.bias_threshold)
        llm_response = call_llm(prompt, config)
    except Exception as e:
        logger.error(f'LLM call failed for {symbol}: {e}')
        return None

    # 5. Parse response
    analysis = parse_analysis(llm_response)

    return {
        'symbol': symbol,
        'name': stock_data['name'],
        'market': detect_market(symbol),
        'data': {k: v for k, v in stock_data.items() if k != 'history'},
        'indicators': indicators,
        'news': news,
        'analysis': analysis,
    }


def analyze_watchlist(symbols: list, config: Config, news_fn=None) -> list:
    """
    Analyze all stocks in the watchlist with a delay between each.

    Returns list of analysis result dicts (skips failures).
    """
    results = []
    total = len(symbols)

    for i, symbol in enumerate(symbols, 1):
        logger.info(f'[{i}/{total}] Processing {symbol}')
        result = analyze_stock(symbol, config, news_fn=news_fn)
        if result:
            results.append(result)
        else:
            logger.warning(f'Skipped {symbol} due to errors')

        # Delay between stocks (skip after the last one)
        if i < total and config.analysis_delay > 0:
            logger.debug(f'Waiting {config.analysis_delay}s before next stock...')
            time.sleep(config.analysis_delay)

    # Sort: Buy first, then Hold, then Sell
    signal_order = {'Buy': 0, 'Hold': 1, 'Sell': 2}
    results.sort(key=lambda r: signal_order.get(r['analysis']['signal'], 1))

    return results
