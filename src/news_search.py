"""
News search — Tavily (primary), SerpAPI (fallback).
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Rotating key index for multi-key support
_tavily_key_idx = 0
_serpapi_key_idx = 0


def search_news(stock_name: str, market_info: dict, config) -> list:
    """
    Search for recent news about a stock. Tries Tavily first, falls back to SerpAPI.

    Returns list of dicts with keys: title, snippet, url, date.
    Returns empty list on failure (never crashes).
    """
    query = _build_query(stock_name, market_info)
    max_age_days = config.news_max_age_days

    # Try Tavily
    if config.tavily_api_keys:
        try:
            results = _search_tavily(query, config.tavily_api_keys, max_age_days)
            if results:
                return results
        except Exception as e:
            logger.warning(f'Tavily search failed: {e}')

    # Fallback to SerpAPI
    if config.serpapi_api_keys:
        try:
            results = _search_serpapi(query, config.serpapi_api_keys)
            if results:
                return results
        except Exception as e:
            logger.warning(f'SerpAPI search failed: {e}')

    logger.info(f'No news found for "{stock_name}"')
    return []


def _build_query(stock_name: str, market_info: dict) -> str:
    """Build a search query appropriate for the market."""
    base = f'{stock_name} stock news'
    if market_info.get('market', '').startswith('india'):
        exchange = market_info.get('exchange', 'NSE')
        return f'{stock_name} {exchange} stock news India'
    return base


def _search_tavily(query: str, api_keys: list, max_age_days: int = 3,
                   max_results: int = 5) -> list:
    """Search using Tavily API with key rotation."""
    global _tavily_key_idx
    from tavily import TavilyClient

    key = api_keys[_tavily_key_idx % len(api_keys)]
    _tavily_key_idx += 1

    client = TavilyClient(api_key=key)
    response = client.search(
        query=query,
        search_depth='basic',
        max_results=max_results,
        include_answer=False,
    )

    cutoff = datetime.now() - timedelta(days=max_age_days)
    results = []

    for item in response.get('results', []):
        # Parse date if available
        pub_date = item.get('published_date', '')
        if pub_date:
            try:
                dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                if dt.replace(tzinfo=None) < cutoff:
                    continue
                date_str = dt.strftime('%Y-%m-%d')
            except (ValueError, TypeError):
                date_str = pub_date[:10] if len(pub_date) >= 10 else ''
        else:
            date_str = ''

        results.append({
            'title': item.get('title', ''),
            'snippet': item.get('content', '')[:300],
            'url': item.get('url', ''),
            'date': date_str,
        })

    return results[:max_results]


def _search_serpapi(query: str, api_keys: list, max_results: int = 5) -> list:
    """Search using SerpAPI (Google News)."""
    global _serpapi_key_idx
    import requests

    key = api_keys[_serpapi_key_idx % len(api_keys)]
    _serpapi_key_idx += 1

    params = {
        'q': query,
        'tbm': 'nws',
        'api_key': key,
        'num': max_results,
    }

    resp = requests.get('https://serpapi.com/search', params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get('news_results', [])[:max_results]:
        results.append({
            'title': item.get('title', ''),
            'snippet': item.get('snippet', ''),
            'url': item.get('link', ''),
            'date': item.get('date', ''),
        })

    return results
