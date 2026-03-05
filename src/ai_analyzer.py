"""
AI Analyzer — builds prompts, calls LLMs, parses responses.
"""

import re
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).parent.parent / 'templates' / 'analysis_prompt.txt'
_TEMPLATE_CACHE = None


def _load_template() -> str:
    """Load and cache the prompt template."""
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is None:
        _TEMPLATE_CACHE = _TEMPLATE_PATH.read_text(encoding='utf-8')
    return _TEMPLATE_CACHE


def build_prompt(stock_data: dict, indicators: dict, news: list,
                 bias_threshold: float = 5.0) -> str:
    """Build the complete LLM prompt from stock data, indicators, and news."""
    from config import format_market_cap, detect_market

    market_info = detect_market(stock_data['symbol'])

    # Format news
    if news:
        news_lines = []
        for i, item in enumerate(news[:5], 1):
            news_lines.append(f"{i}. {item.get('title', 'N/A')}")
            if item.get('snippet'):
                news_lines.append(f"   {item['snippet'][:200]}")
            if item.get('date'):
                news_lines.append(f"   Date: {item['date']}")
        formatted_news = '\n'.join(news_lines)
    else:
        formatted_news = 'No recent news available.'

    template = _load_template()

    return template.format(
        name=stock_data.get('name', 'Unknown'),
        symbol=stock_data['symbol'],
        market=market_info['exchange'],
        currency=market_info['currency'],
        sector=stock_data.get('sector', 'N/A'),
        industry=stock_data.get('industry', 'N/A'),
        current_price=stock_data.get('current_price', 0),
        change_pct=stock_data.get('change_pct', 0),
        fifty_two_week_low=stock_data.get('fifty_two_week_low', 0),
        fifty_two_week_high=stock_data.get('fifty_two_week_high', 0),
        pe_ratio=stock_data.get('pe_ratio', 'N/A'),
        market_cap_formatted=format_market_cap(
            stock_data.get('market_cap', 0), stock_data['symbol']
        ),
        ma5=indicators.get('ma5', 0),
        ma10=indicators.get('ma10', 0),
        ma20=indicators.get('ma20', 0),
        ma60=indicators.get('ma60', 0),
        trend_status=indicators.get('trend_status', 'N/A'),
        bias_ma5=indicators.get('bias_ma5', 0),
        macd_status=indicators.get('macd_status', 'N/A'),
        macd_histogram=indicators.get('macd_histogram', 0),
        rsi_14=indicators.get('rsi_14', 50),
        volume_ratio=indicators.get('volume_ratio', 0),
        bollinger_upper=indicators.get('bollinger_upper', 0),
        bollinger_lower=indicators.get('bollinger_lower', 0),
        formatted_news=formatted_news,
        bias_threshold=bias_threshold,
    )


def call_gemini(prompt: str, api_key: str, max_retries: int = 3) -> str:
    """Call Google Gemini API."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    for attempt in range(1, max_retries + 1):
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            err_str = str(e).lower()
            if '429' in err_str or 'rate' in err_str or 'quota' in err_str:
                wait = min(2 ** attempt * 5, 60)
                logger.warning(f'Gemini rate limited, waiting {wait}s (attempt {attempt})')
                time.sleep(wait)
            else:
                logger.error(f'Gemini error: {e}')
                if attempt == max_retries:
                    raise
                time.sleep(2 ** attempt)

    raise RuntimeError('Gemini: all retries exhausted')


def call_openai_compatible(prompt: str, api_key: str, base_url: str,
                           model: str = 'gpt-4o-mini', max_retries: int = 3) -> str:
    """Call any OpenAI-compatible API (DeepSeek, Qwen, etc.)."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url or None)

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.7,
                max_tokens=2000,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f'OpenAI-compatible error (attempt {attempt}): {e}')
            if attempt < max_retries:
                time.sleep(2 ** attempt)

    raise RuntimeError('OpenAI-compatible: all retries exhausted')


def call_llm(prompt: str, config) -> str:
    """Try primary LLM (Gemini), fall back to OpenAI-compatible."""
    errors = []

    if config.gemini_api_key:
        try:
            return call_gemini(prompt, config.gemini_api_key)
        except Exception as e:
            errors.append(f'Gemini: {e}')
            logger.warning(f'Gemini failed, trying fallback: {e}')

    if config.openai_api_key:
        try:
            return call_openai_compatible(
                prompt, config.openai_api_key,
                config.openai_base_url, config.openai_model
            )
        except Exception as e:
            errors.append(f'OpenAI: {e}')

    raise RuntimeError(f'All LLM providers failed: {"; ".join(errors)}')


def parse_analysis(response: str) -> dict:
    """Extract structured data from LLM text response."""
    result = {
        'signal': 'Hold',
        'signal_emoji': '🟡',
        'score': 50,
        'core_conclusion': '',
        'time_sensitivity': '',
        'entry_price': None,
        'stop_loss': None,
        'target_price': None,
        'checklist': [],
        'risk_factors': [],
        'news_impact': '',
        'raw': response,
    }

    # Signal
    if '🟢' in response or re.search(r'Signal:\s*.*Buy', response, re.IGNORECASE):
        result['signal'] = 'Buy'
        result['signal_emoji'] = '🟢'
    elif '🔴' in response or re.search(r'Signal:\s*.*Sell', response, re.IGNORECASE):
        result['signal'] = 'Sell'
        result['signal_emoji'] = '🔴'
    else:
        result['signal'] = 'Hold'
        result['signal_emoji'] = '🟡'

    # Score
    m = re.search(r'Score:\s*(\d+)', response)
    if m:
        result['score'] = int(m.group(1))

    # Core Conclusion
    m = re.search(r'Core Conclusion:\s*(.+?)(?:\n|$)', response)
    if m:
        result['core_conclusion'] = m.group(1).strip()

    # Time Sensitivity
    m = re.search(r'Time Sensitivity:\s*(.+?)(?:\n|$)', response)
    if m:
        result['time_sensitivity'] = m.group(1).strip()

    # Prices — match currency symbols and numbers
    m = re.search(r'Entry Price:\s*[₹$]?\s*([\d,]+\.?\d*)', response)
    if m:
        result['entry_price'] = _parse_price(m.group(1))

    m = re.search(r'Stop Loss:\s*[₹$]?\s*([\d,]+\.?\d*)', response)
    if m:
        result['stop_loss'] = _parse_price(m.group(1))

    m = re.search(r'Target Price:\s*[₹$]?\s*([\d,]+\.?\d*)', response)
    if m:
        result['target_price'] = _parse_price(m.group(1))

    # Checklist items
    checklist_pattern = re.findall(r'[-•]\s*\[(✅|⚠️|❌)\]\s*(.+?)(?:\n|$)', response)
    result['checklist'] = [
        {'status': status, 'item': item.strip()}
        for status, item in checklist_pattern
    ]

    # Risk Factors
    risk_section = re.search(r'Risk Factors:\s*\n((?:[-•]\s*.+\n?)+)', response)
    if risk_section:
        risks = re.findall(r'[-•]\s*(.+)', risk_section.group(1))
        result['risk_factors'] = [r.strip() for r in risks]

    # News Impact
    m = re.search(r'News Impact:\s*(.+?)(?:\n\n|$)', response, re.DOTALL)
    if m:
        result['news_impact'] = m.group(1).strip()

    return result


def _parse_price(s: str) -> float:
    """Parse a price string, removing commas."""
    return float(s.replace(',', ''))
