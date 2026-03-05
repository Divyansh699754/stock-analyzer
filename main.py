"""
Stock Analyzer — Entry point.

Usage:
    python main.py                              # Full analysis, all stocks
    python main.py --stocks AAPL,RELIANCE.NS    # Override watchlist
    python main.py --market-review              # Only market overview
    python main.py --no-notify                  # Run analysis, skip notifications
    python main.py --schedule                   # Enter scheduled mode
    python main.py --output json                # Print raw JSON to stdout
"""

import sys
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import Config


def setup_logging(verbose: bool = False):
    """Configure logging to console and file."""
    level = logging.DEBUG if verbose else logging.INFO
    log_dir = Path(__file__).parent / 'logs'
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f'{datetime.now().strftime("%Y-%m-%d")}.log'

    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding='utf-8'),
    ]

    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S',
        handlers=handlers,
    )


def run_analysis(args, config: Config):
    """Run the main analysis pipeline."""
    from src.stock_pipeline import analyze_watchlist

    # Determine stock list
    if args.stocks:
        symbols = [s.strip() for s in args.stocks.split(',') if s.strip()]
    else:
        symbols = config.stock_list

    logging.info(f'Analyzing {len(symbols)} stocks: {", ".join(symbols)}')

    # News function (None in Phase 1, will be wired in Phase 2)
    news_fn = None
    try:
        from src.news_search import search_news
        if config.tavily_api_keys or config.serpapi_api_keys:
            news_fn = lambda name, market: search_news(name, market, config)
    except ImportError:
        pass

    # Run analysis
    results = analyze_watchlist(symbols, config, news_fn=news_fn)

    if not results:
        logging.warning('No stocks were successfully analyzed')
        return []

    # Market review
    market_review = None
    if not args.no_notify or args.market_review:
        try:
            from src.market_review import get_market_review
            market_review = get_market_review()
        except ImportError:
            pass

    # Output
    if args.output == 'json':
        # JSON output (strip non-serializable data)
        output = []
        for r in results:
            entry = {
                'symbol': r['symbol'],
                'name': r['name'],
                'market': r['market'],
                'indicators': r['indicators'],
                'analysis': {k: v for k, v in r['analysis'].items() if k != 'raw'},
            }
            output.append(entry)
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        _print_dashboard(results, market_review)

    # Save reports
    try:
        from src.storage import save_daily_report
        save_daily_report(results, market_review)
    except ImportError:
        pass

    # Send notifications
    if not args.no_notify:
        try:
            from src.notification import notify_all, format_dashboard
            if config.telegram_bot_token or config.email_sender:
                dashboard = format_dashboard(results, market_review)
                notify_all(dashboard, config)
                logging.info('Notifications sent')
        except ImportError:
            logging.debug('Notification module not yet available')

    return results


def _print_dashboard(results: list, market_review: str = None):
    """Print a formatted dashboard to the console."""
    today = datetime.now().strftime('%b %d, %Y')
    buy = sum(1 for r in results if r['analysis']['signal'] == 'Buy')
    hold = sum(1 for r in results if r['analysis']['signal'] == 'Hold')
    sell = sum(1 for r in results if r['analysis']['signal'] == 'Sell')

    print(f'\n{"="*60}')
    print(f'  {today} — Decision Dashboard')
    print(f'  {len(results)} stocks | Buy: {buy} | Hold: {hold} | Sell: {sell}')
    print(f'{"="*60}')

    if market_review:
        print(f'\n{market_review}')

    for r in results:
        a = r['analysis']
        currency = r['market']['currency']
        price = r['indicators']['current_price']

        print(f'\n{a["signal_emoji"]} {r["symbol"]} ({r["name"]}) — {currency}{price}')
        if a['core_conclusion']:
            print(f'  {a["core_conclusion"]}')

        if a['entry_price'] and a['signal'] == 'Buy':
            print(f'  Entry: {currency}{a["entry_price"]} | '
                  f'Stop: {currency}{a["stop_loss"]} | '
                  f'Target: {currency}{a["target_price"]}')

        if a['checklist']:
            items = ' '.join(f'{c["status"]}' for c in a['checklist'])
            print(f'  {items}')

    print(f'\n{"="*60}')
    print('  Not financial advice. Not SEC/SEBI registered. Educational only.')
    print(f'{"="*60}\n')


def run_market_review_only():
    """Run and print only the market review."""
    try:
        from src.market_review import get_market_review
        review = get_market_review()
        print(review)
    except ImportError:
        print('Market review module not yet available.')


def run_scheduler(config: Config):
    """Enter scheduled mode — runs daily at configured time."""
    try:
        from src.scheduler import start_scheduler
        start_scheduler(config, lambda: run_analysis(
            argparse.Namespace(stocks=None, no_notify=False,
                             market_review=False, output='text'),
            config
        ))
    except ImportError:
        print('Scheduler module not yet available.')


def main():
    parser = argparse.ArgumentParser(description='Stock Analyzer — AI-powered daily analysis')
    parser.add_argument('--stocks', type=str, help='Comma-separated stock symbols (overrides STOCK_LIST)')
    parser.add_argument('--no-notify', action='store_true', help='Skip sending notifications')
    parser.add_argument('--market-review', action='store_true', help='Only show market overview')
    parser.add_argument('--schedule', action='store_true', help='Enter scheduled mode (runs daily)')
    parser.add_argument('--output', choices=['text', 'json'], default='text', help='Output format')
    parser.add_argument('--verbose', action='store_true', help='Enable debug logging')
    parser.add_argument('--dry-run', action='store_true', help='Run analysis but skip notifications')

    args = parser.parse_args()

    if args.dry_run:
        args.no_notify = True

    setup_logging(args.verbose)

    config = Config()
    config.validate()

    if args.market_review:
        run_market_review_only()
    elif args.schedule:
        run_scheduler(config)
    else:
        run_analysis(args, config)


if __name__ == '__main__':
    main()
