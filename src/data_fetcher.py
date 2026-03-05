"""
Stock data fetcher — yfinance wrapper with retry logic.
"""

import time
import logging
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_stock_data(symbol: str, period: str = '6mo', max_retries: int = 3) -> dict | None:
    """
    Fetch stock data from yfinance.

    Returns dict with keys: symbol, name, sector, industry, market_cap,
    currency, current_price, change_pct, pe_ratio, fifty_two_week_high,
    fifty_two_week_low, history (DataFrame), exchange.
    Returns None if the symbol is invalid or all retries fail.
    """
    for attempt in range(1, max_retries + 1):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Validate that we got real data
            name = info.get('shortName') or info.get('longName')
            if not name:
                logger.warning(f'No data found for {symbol} — skipping')
                return None

            hist = ticker.history(period=period)
            if hist.empty:
                logger.warning(f'No price history for {symbol} — skipping')
                return None

            # Current price: use regularMarketPrice, fall back to last close
            current_price = (
                info.get('regularMarketPrice')
                or info.get('currentPrice')
                or float(hist['Close'].iloc[-1])
            )

            # Day change %
            prev_close = info.get('regularMarketPreviousClose') or info.get('previousClose')
            if prev_close and prev_close > 0:
                change_pct = round((current_price - prev_close) / prev_close * 100, 2)
            else:
                change_pct = 0.0

            return {
                'symbol': symbol.upper(),
                'name': name,
                'sector': info.get('sector', 'N/A'),
                'industry': info.get('industry', 'N/A'),
                'market_cap': info.get('marketCap', 0),
                'currency': info.get('currency', 'USD'),
                'exchange': info.get('exchange', ''),
                'current_price': current_price,
                'change_pct': change_pct,
                'pe_ratio': info.get('trailingPE') or info.get('forwardPE') or 0,
                'fifty_two_week_high': info.get('fiftyTwoWeekHigh', 0),
                'fifty_two_week_low': info.get('fiftyTwoWeekLow', 0),
                'history': hist,
            }

        except Exception as e:
            wait = 2 ** attempt
            logger.warning(f'Attempt {attempt}/{max_retries} failed for {symbol}: {e}')
            if attempt < max_retries:
                logger.info(f'Retrying in {wait}s...')
                time.sleep(wait)

    logger.error(f'All {max_retries} attempts failed for {symbol}')
    return None
