"""
Notification module — Telegram (primary) + Email (secondary).
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

import requests

from config import format_currency, detect_market, format_inr

logger = logging.getLogger(__name__)


def format_dashboard(results: list, market_review: str = None) -> str:
    """Format analysis results into a Telegram-friendly dashboard."""
    today = datetime.now().strftime('%b %d, %Y')
    buy = sum(1 for r in results if r['analysis']['signal'] == 'Buy')
    hold = sum(1 for r in results if r['analysis']['signal'] == 'Hold')
    sell = sum(1 for r in results if r['analysis']['signal'] == 'Sell')

    lines = [
        f'📊 {today} — Decision Dashboard',
        f'{len(results)} stocks | 🟢 Buy: {buy} | 🟡 Hold: {hold} | 🔴 Sell: {sell}',
        '',
    ]

    if market_review:
        lines.append('━━━ MARKET OVERVIEW ━━━')
        lines.append(market_review)
        lines.append('')

    lines.append('━━━ STOCK ANALYSIS ━━━')

    for r in results:
        a = r['analysis']
        market = r['market']
        currency = market['currency']
        price = r['indicators']['current_price']

        # Format price with correct currency
        if currency == '₹':
            price_str = f'₹{format_inr(price)}'
        else:
            price_str = f'${price:,.2f}'

        lines.append(f'\n{a["signal_emoji"]} {r["symbol"]} ({r["name"]}) — {price_str}')

        if a['core_conclusion']:
            lines.append(f'📌 {a["core_conclusion"]}')

        if a['signal'] == 'Buy' and a.get('entry_price'):
            entry = _fmt(a['entry_price'], currency)
            stop = _fmt(a['stop_loss'], currency)
            target = _fmt(a['target_price'], currency)
            lines.append(f'💰 Buy {entry} | Stop {stop} | Target {target}')
        elif a['signal'] == 'Sell' and a.get('entry_price'):
            entry = _fmt(a['entry_price'], currency)
            lines.append(f'💰 Exit {entry}')

        if a['checklist']:
            checks = ' '.join(c['status'] for c in a['checklist'])
            labels = ['Trend', 'BIAS', 'Volume', 'MACD', 'RSI', 'News']
            items = []
            for i, c in enumerate(a['checklist'][:6]):
                label = labels[i] if i < len(labels) else c['item'][:8]
                items.append(f'{c["status"]} {label}')
            lines.append(' '.join(items))

    lines.append('')
    lines.append('⚠️ Not financial advice. Not SEC/SEBI registered. Educational only.')

    return '\n'.join(lines)


def _fmt(price, currency: str) -> str:
    """Format a price with currency."""
    if price is None:
        return 'N/A'
    if currency == '₹':
        return f'₹{format_inr(price)}'
    return f'${price:,.2f}'


def send_telegram(message: str, bot_token: str, chat_id: str) -> bool:
    """Send a message via Telegram Bot API. Splits long messages."""
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    max_len = 4096

    chunks = _split_message(message, max_len)

    for chunk in chunks:
        payload = {
            'chat_id': chat_id,
            'text': chunk,
            'parse_mode': 'Markdown',
            'disable_web_page_preview': True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code != 200:
                # Retry without Markdown parse mode
                payload['parse_mode'] = ''
                resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f'Telegram send failed: {e}')
            return False

    return True


def _split_message(text: str, max_len: int) -> list:
    """Split a message into chunks at newline boundaries."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ''
    for line in text.split('\n'):
        if len(current) + len(line) + 1 > max_len:
            if current:
                chunks.append(current)
            current = line
        else:
            current = current + '\n' + line if current else line

    if current:
        chunks.append(current)

    return chunks


def send_email(subject: str, body: str, sender: str, password: str,
               receivers: list) -> bool:
    """Send an email via Gmail SMTP."""
    try:
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = ', '.join(receivers)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            server.sendmail(sender, receivers, msg.as_string())

        logger.info(f'Email sent to {len(receivers)} recipients')
        return True
    except Exception as e:
        logger.error(f'Email send failed: {e}')
        return False


def notify_all(message: str, config) -> None:
    """Send notifications to all configured channels."""
    if config.telegram_bot_token and config.telegram_chat_id:
        if send_telegram(message, config.telegram_bot_token, config.telegram_chat_id):
            logger.info('Telegram notification sent')

    if config.email_sender and config.email_password and config.email_receivers:
        today = datetime.now().strftime('%Y-%m-%d')
        send_email(
            subject=f'Stock Analysis — {today}',
            body=message,
            sender=config.email_sender,
            password=config.email_password,
            receivers=config.email_receivers,
        )
