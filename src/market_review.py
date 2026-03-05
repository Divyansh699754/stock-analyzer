"""
Market review — daily index overview for US and India markets.
"""

import logging
import yfinance as yf

logger = logging.getLogger(__name__)

US_INDICES = {
    '^GSPC': 'S&P 500',
    '^IXIC': 'NASDAQ',
    '^DJI': 'Dow Jones',
    '^VIX': 'VIX',
}

INDIA_INDICES = {
    '^NSEI': 'NIFTY 50',
    '^BSESN': 'SENSEX',
    '^NSEBANK': 'Bank NIFTY',
}


def get_market_review() -> str:
    """Fetch key market indices and format a summary."""
    lines = []

    # US markets
    us_data = _fetch_indices(US_INDICES)
    for symbol, name in US_INDICES.items():
        if symbol in us_data:
            d = us_data[symbol]
            emoji = '🟢' if d['change_pct'] >= 0 else '🔴'
            lines.append(f'🇺🇸 {name}: {d["price"]:,.0f} ({emoji} {d["change_pct"]:+.2f}%)')

    # India markets
    india_data = _fetch_indices(INDIA_INDICES)
    for symbol, name in INDIA_INDICES.items():
        if symbol in india_data:
            d = india_data[symbol]
            emoji = '🟢' if d['change_pct'] >= 0 else '🔴'
            lines.append(f'🇮🇳 {name}: {d["price"]:,.0f} ({emoji} {d["change_pct"]:+.2f}%)')

    if not lines:
        return 'Market data unavailable.'

    return '\n'.join(lines)


def _fetch_indices(indices: dict) -> dict:
    """Fetch current price and change % for a dict of indices."""
    results = {}

    for symbol in indices:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            price = (
                info.get('regularMarketPrice')
                or info.get('currentPrice', 0)
            )
            prev = info.get('regularMarketPreviousClose') or info.get('previousClose', 0)

            if price and prev and prev > 0:
                change_pct = (price - prev) / prev * 100
            else:
                change_pct = 0.0

            results[symbol] = {
                'price': price or 0,
                'change_pct': round(change_pct, 2),
            }
        except Exception as e:
            logger.warning(f'Failed to fetch {symbol}: {e}')

    return results
