"""
Configuration module — loads .env, detects markets, validates keys.
"""

import os
from pathlib import Path
from dotenv import load_dotenv


# Load .env from project root
_env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=_env_path)


def detect_market(symbol: str) -> dict:
    """Detect market type from stock symbol format."""
    s = symbol.strip().upper()
    if s.endswith('.NS'):
        return {'market': 'india_nse', 'currency': '₹', 'exchange': 'NSE'}
    elif s.endswith('.BO'):
        return {'market': 'india_bse', 'currency': '₹', 'exchange': 'BSE'}
    elif s.startswith('^'):
        return {'market': 'index', 'currency': '', 'exchange': 'Index'}
    else:
        return {'market': 'us', 'currency': '$', 'exchange': 'US'}


def format_inr(amount: float) -> str:
    """Format a number in Indian comma style: 1,00,000."""
    if amount < 0:
        return '-' + format_inr(-amount)
    s = f'{amount:.2f}'
    integer_part, decimal_part = s.split('.')
    # Indian system: last 3 digits, then groups of 2
    if len(integer_part) <= 3:
        return f'{integer_part}.{decimal_part}'
    last3 = integer_part[-3:]
    rest = integer_part[:-3]
    # Insert commas every 2 digits from the right in 'rest'
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return ','.join(groups) + ',' + last3 + '.' + decimal_part


def format_currency(amount: float, symbol: str) -> str:
    """Format amount with correct currency symbol and style."""
    market = detect_market(symbol)
    if market['currency'] == '₹':
        return f'₹{format_inr(amount)}'
    elif market['currency'] == '$':
        return f'${amount:,.2f}'
    else:
        return f'{amount:,.2f}'


def format_market_cap(value: float, symbol: str) -> str:
    """Format market cap in human-readable form (B/T/Cr/L Cr)."""
    market = detect_market(symbol)
    if market['currency'] == '₹':
        # Indian: use Crore (1 Cr = 10M) and Lakh Crore (1 L Cr = 1T)
        cr = value / 1e7
        if cr >= 1e5:
            return f'₹{cr / 1e5:.2f} L Cr'
        elif cr >= 1:
            return f'₹{cr:,.0f} Cr'
        else:
            return f'₹{format_inr(value)}'
    else:
        if value >= 1e12:
            return f'${value / 1e12:.2f}T'
        elif value >= 1e9:
            return f'${value / 1e9:.2f}B'
        elif value >= 1e6:
            return f'${value / 1e6:.2f}M'
        else:
            return f'${value:,.0f}'


class Config:
    """Singleton configuration loaded from environment variables."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        # AI keys
        self.gemini_api_key = os.getenv('GEMINI_API_KEY', '')
        self.openai_api_key = os.getenv('OPENAI_API_KEY', '')
        self.openai_base_url = os.getenv('OPENAI_BASE_URL', '')
        self.openai_model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')

        # Stock list
        raw = os.getenv('STOCK_LIST', 'AAPL')
        self.stock_list = [s.strip() for s in raw.split(',') if s.strip()]

        # News
        self.tavily_api_keys = _parse_keys('TAVILY_API_KEYS')
        self.serpapi_api_keys = _parse_keys('SERPAPI_API_KEYS')

        # Telegram
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')

        # Email
        self.email_sender = os.getenv('EMAIL_SENDER', '')
        self.email_password = os.getenv('EMAIL_PASSWORD', '')
        self.email_receivers = [
            e.strip() for e in os.getenv('EMAIL_RECEIVERS', '').split(',') if e.strip()
        ]

        # Behavior
        self.analysis_delay = int(os.getenv('ANALYSIS_DELAY', '10'))
        self.news_max_age_days = int(os.getenv('NEWS_MAX_AGE_DAYS', '3'))
        self.bias_threshold = float(os.getenv('BIAS_THRESHOLD', '5.0'))
        self.schedule_time = os.getenv('SCHEDULE_TIME', '18:00')

    def validate(self):
        """Raise if minimum required config is missing."""
        errors = []
        if not self.gemini_api_key and not self.openai_api_key:
            errors.append('At least one AI key required (GEMINI_API_KEY or OPENAI_API_KEY)')
        if not self.stock_list:
            errors.append('STOCK_LIST is empty')
        if errors:
            raise ValueError('Config validation failed:\n' + '\n'.join(f'  - {e}' for e in errors))

    @classmethod
    def reload(cls):
        """Force reload configuration (useful for testing)."""
        cls._instance = None
        load_dotenv(dotenv_path=_env_path, override=True)
        return cls()


def _parse_keys(env_var: str) -> list:
    """Parse comma-separated API keys from env var."""
    raw = os.getenv(env_var, '')
    return [k.strip() for k in raw.split(',') if k.strip()]
