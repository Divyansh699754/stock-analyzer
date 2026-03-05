"""
Backtest engine — rules-only and LLM modes.

Usage:
    python -m backtest.engine --mode rules-only --symbols AAPL,RELIANCE.NS \
        --start 2020-01-01 --end 2025-12-31 --cash-usd 10000 --cash-inr 1000000

    python -m backtest.engine --mode llm --symbols AAPL,RELIANCE.NS \
        --start 2016-01-01 --end 2025-12-31 --state-file backtest/state/progress.json \
        --max-api-calls 1400
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd
import yfinance as yf

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest.portfolio import Portfolio
from backtest.state import BacktestState
from src.technical_analysis import calculate_indicators

logger = logging.getLogger(__name__)


def load_historical_data(symbols: list, start: str, end: str) -> dict:
    """Download full historical data for all symbols at once."""
    data = {}
    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start, end=end)
            if not hist.empty:
                data[symbol] = hist
                logger.info(f'Loaded {len(hist)} days for {symbol}')
            else:
                logger.warning(f'No data for {symbol}')
        except Exception as e:
            logger.warning(f'Failed to load {symbol}: {e}')
    return data


def load_benchmark_data(start: str, end: str) -> dict:
    """Load benchmark index data (S&P 500, NIFTY 50)."""
    benchmarks = {}
    for symbol, name in [('^GSPC', 'S&P 500'), ('^NSEI', 'NIFTY 50')]:
        try:
            hist = yf.Ticker(symbol).history(start=start, end=end)
            if not hist.empty:
                benchmarks[name] = hist
        except Exception as e:
            logger.warning(f'Failed to load benchmark {name}: {e}')
    return benchmarks


def run_rules_only(state: BacktestState, all_data: dict,
                   bias_threshold: float = 7.0, stop_loss_pct: float = 5.0,
                   trailing_pct: float = 15.0):
    """
    Run rules-only backtest with trailing stops.

    Buy when ALL true:
    - MA5 just crossed above MA10 (within last 3 days)
    - MA5 > MA10 > MA20 (bullish alignment)
    - RSI between 30 and 70
    - BIAS < threshold

    Sell when ANY true:
    - Trailing stop hit (price drops trailing_pct% from peak)
    - Initial stop-loss hit
    - NO fixed target — let winners ride

    No MA death cross sell — rely on trailing stop to exit.
    """
    # Build trading calendar (union of all dates)
    all_dates = set()
    for df in all_data.values():
        all_dates.update(df.index.strftime('%Y-%m-%d').tolist())
    all_dates = sorted(all_dates)

    # Filter to date range
    all_dates = [d for d in all_dates if state.start_date <= d <= state.end_date]
    state.total_days = len(all_dates)

    # Skip to resume point
    start_idx = state.current_day_index

    state.status = 'running'
    logger.info(f'Rules-only backtest: {len(all_dates)} trading days, '
                f'resuming from day {start_idx}')

    for i in range(start_idx, len(all_dates)):
        date = all_dates[i]

        # Get current prices for all held and watchlist stocks
        current_prices = {}
        for symbol, df in all_data.items():
            mask = df.index.strftime('%Y-%m-%d') <= date
            if mask.any():
                current_prices[symbol] = float(df.loc[mask, 'Close'].iloc[-1])

        # 1. Update trailing stops and check if any triggered
        state.portfolio.update_trailing_stops(current_prices, date)

        # 2. Evaluate each symbol for entry
        for symbol in state.symbols:
            if symbol not in all_data:
                continue

            df = all_data[symbol]
            mask = df.index.strftime('%Y-%m-%d') <= date
            visible = df.loc[mask]

            if len(visible) < 60:  # need enough data for MA60
                continue

            try:
                indicators = calculate_indicators(visible)
            except Exception:
                continue

            price = current_prices.get(symbol)
            if price is None:
                continue

            # Skip if already holding
            if symbol in state.portfolio.holdings:
                continue

            # Check buy conditions
            if _should_buy_rules(indicators, visible, bias_threshold):
                state.portfolio.buy(symbol, price, date,
                                   stop_loss_pct=stop_loss_pct,
                                   trailing_pct=trailing_pct)

        # Record daily value
        values = state.portfolio.get_total_value(current_prices)
        state.record_day(date, values)

    state.status = 'complete'
    state.trades = state.portfolio.trades.copy()
    logger.info(f'Backtest complete. {len(state.trades)} trades executed.')


def _should_buy_rules(indicators: dict, visible_df: pd.DataFrame,
                      bias_threshold: float) -> bool:
    """Check if rules-based buy conditions are met."""
    # Bullish alignment
    if not ('Bullish' in indicators.get('trend_status', '')):
        return False

    # MACD confirmation — require MACD above signal line
    macd_status = indicators.get('macd_status', 'Bearish')
    if macd_status not in ('Bullish', 'Golden Cross'):
        return False

    # BIAS check
    if abs(indicators.get('bias_ma5', 99)) >= bias_threshold:
        return False

    # RSI in safe range
    rsi = indicators.get('rsi_14', 50)
    if rsi < 30 or rsi > 70:
        return False

    # MA5 cross above MA10 (recent crossover within last 5 days)
    close = visible_df['Close']
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    if len(ma5) >= 2 and len(ma10) >= 2:
        found_cross = False
        for j in range(min(5, len(ma5) - 1)):
            idx = -(j + 1)
            prev_idx = idx - 1
            if prev_idx < -len(ma5):
                break
            prev_diff = float(ma5.iloc[prev_idx]) - float(ma10.iloc[prev_idx])
            curr_diff = float(ma5.iloc[idx]) - float(ma10.iloc[idx])
            if prev_diff <= 0 and curr_diff > 0:
                found_cross = True
                break
        if not found_cross:
            return False

    return True


def run_llm_mode(state: BacktestState, all_data: dict,
                 max_api_calls: int = 1400):
    """
    Run LLM-powered backtest. Calls Gemini for each day/stock.
    Saves state after every day for crash-safe resume.
    """
    from config import Config
    from src.ai_analyzer import build_prompt, call_llm, parse_analysis

    config = Config()

    # Build trading calendar
    all_dates = set()
    for df in all_data.values():
        all_dates.update(df.index.strftime('%Y-%m-%d').tolist())
    all_dates = sorted(d for d in all_dates
                       if state.start_date <= d <= state.end_date)
    state.total_days = len(all_dates)

    start_idx = state.current_day_index
    api_calls = 0

    state.status = 'running'
    logger.info(f'LLM backtest: {len(all_dates)} days, '
                f'max {max_api_calls} API calls, resuming from day {start_idx}')

    for i in range(start_idx, len(all_dates)):
        if api_calls >= max_api_calls:
            logger.info(f'API call limit reached ({api_calls}/{max_api_calls})')
            break

        date = all_dates[i]

        # Current prices
        current_prices = {}
        for symbol, df in all_data.items():
            mask = df.index.strftime('%Y-%m-%d') <= date
            if mask.any():
                current_prices[symbol] = float(df.loc[mask, 'Close'].iloc[-1])

        # Update trailing stops
        state.portfolio.update_trailing_stops(current_prices, date)

        # Analyze each symbol via LLM
        for symbol in state.symbols:
            if symbol not in all_data or api_calls >= max_api_calls:
                continue

            df = all_data[symbol]
            mask = df.index.strftime('%Y-%m-%d') <= date
            visible = df.loc[mask]

            if len(visible) < 30:
                continue

            try:
                indicators = calculate_indicators(visible)
                price = current_prices.get(symbol)
                if price is None:
                    continue

                stock_data = {
                    'symbol': symbol,
                    'name': symbol,
                    'sector': 'N/A',
                    'industry': 'N/A',
                    'market_cap': 0,
                    'current_price': price,
                    'change_pct': 0,
                    'pe_ratio': 'N/A',
                    'fifty_two_week_high': float(visible['Close'].max()),
                    'fifty_two_week_low': float(visible['Close'].min()),
                }

                prompt = build_prompt(stock_data, indicators, [],
                                     config.bias_threshold)
                response = call_llm(prompt, config)
                api_calls += 1
                state.api_calls_used += 1

                analysis = parse_analysis(response)

                if analysis['signal'] == 'Buy' and symbol not in state.portfolio.holdings:
                    state.portfolio.buy(symbol, price, date,
                                       stop_loss_pct=7.0, trailing_pct=12.0)
                elif analysis['signal'] == 'Sell' and symbol in state.portfolio.holdings:
                    state.portfolio.sell(symbol, price, date,
                                       reason=f'LLM signal: {analysis["core_conclusion"]}')

            except Exception as e:
                logger.warning(f'LLM analysis failed for {symbol} on {date}: {e}')

        # Record daily value
        values = state.portfolio.get_total_value(current_prices)
        state.record_day(date, values)

    # Check if complete
    if state.current_day_index >= state.total_days:
        state.status = 'complete'
        logger.info('LLM backtest complete!')
    else:
        logger.info(f'LLM backtest paused at {state.progress_pct}% '
                    f'({state.current_day_index}/{state.total_days} days)')

    state.trades = state.portfolio.trades.copy()


def main():
    parser = argparse.ArgumentParser(description='Backtest Engine')
    parser.add_argument('--mode', choices=['rules-only', 'llm'], default='rules-only')
    parser.add_argument('--symbols', type=str, required=True, help='Comma-separated symbols')
    parser.add_argument('--start', type=str, default='2020-01-01', help='Start date')
    parser.add_argument('--end', type=str, default='2025-12-31', help='End date')
    parser.add_argument('--cash-usd', type=float, default=10000)
    parser.add_argument('--cash-inr', type=float, default=1000000)
    parser.add_argument('--state-file', type=str, default='backtest/state/progress.json')
    parser.add_argument('--max-api-calls', type=int, default=1400)
    parser.add_argument('--bias-threshold', type=float, default=7.0)
    parser.add_argument('--stop-loss-pct', type=float, default=5.0)
    parser.add_argument('--trailing-pct', type=float, default=15.0)

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                       format='%(asctime)s [%(levelname)s] %(message)s')

    symbols = [s.strip() for s in args.symbols.split(',')]

    # Try to resume from state file
    state_path = Path(args.state_file)
    if state_path.exists():
        logger.info(f'Resuming from {state_path}')
        state = BacktestState.load(str(state_path))
        if state.is_complete():
            logger.info('Backtest already complete. Generating report...')
            _generate_report(state, args)
            return
    else:
        portfolio = Portfolio(cash_usd=args.cash_usd, cash_inr=args.cash_inr)
        state = BacktestState(portfolio, symbols, args.start, args.end)

    # Load data
    logger.info('Loading historical data...')
    all_data = load_historical_data(symbols, args.start, args.end)

    if not all_data:
        logger.error('No data loaded. Exiting.')
        return

    # Run backtest
    if args.mode == 'rules-only':
        run_rules_only(state, all_data,
                      bias_threshold=args.bias_threshold,
                      stop_loss_pct=args.stop_loss_pct,
                      trailing_pct=args.trailing_pct)
    else:
        run_llm_mode(state, all_data, max_api_calls=args.max_api_calls)

    # Save state
    state.save(str(state_path))
    logger.info(f'State saved to {state_path}')

    # Generate report if complete
    if state.is_complete():
        _generate_report(state, args)


def _generate_report(state: BacktestState, args):
    """Generate the backtest report."""
    try:
        from backtest.report_generator import generate_report
        benchmarks = load_benchmark_data(args.start, args.end)
        generate_report(state, benchmarks)
    except ImportError:
        logger.info('Report generator not yet available. Printing summary...')
        _print_summary(state)


def _print_summary(state: BacktestState):
    """Print a basic summary of backtest results."""
    if not state.daily_values:
        return

    first = state.daily_values[0]
    last = state.daily_values[-1]

    print(f'\n{"="*50}')
    print(f'  BACKTEST SUMMARY')
    print(f'{"="*50}')
    print(f'  Period: {state.start_date} to {state.end_date}')
    print(f'  Days processed: {state.current_day_index}')
    print(f'  Total trades: {len(state.trades)}')
    print(f'\n  USD Pool:')
    print(f'    Start: ${first.get("total_usd", 0):,.2f}')
    print(f'    End:   ${last.get("total_usd", 0):,.2f}')
    usd_return = 0
    if first.get('total_usd', 0) > 0:
        usd_return = (last.get('total_usd', 0) - first['total_usd']) / first['total_usd'] * 100
    print(f'    Return: {usd_return:+.1f}%')

    if first.get('total_inr', 0) > 0:
        print(f'\n  INR Pool:')
        print(f'    Start: ₹{first["total_inr"]:,.0f}')
        print(f'    End:   ₹{last.get("total_inr", 0):,.0f}')
        inr_return = (last.get('total_inr', 0) - first['total_inr']) / first['total_inr'] * 100
        print(f'    Return: {inr_return:+.1f}%')

    # Win/loss stats
    wins = [t for t in state.trades if t.get('action') == 'SELL' and t.get('pnl_pct', 0) > 0]
    losses = [t for t in state.trades if t.get('action') == 'SELL' and t.get('pnl_pct', 0) <= 0]
    total_sells = len(wins) + len(losses)

    if total_sells > 0:
        print(f'\n  Win Rate: {len(wins)}/{total_sells} ({len(wins)/total_sells*100:.0f}%)')
        if wins:
            avg_win = sum(t['pnl_pct'] for t in wins) / len(wins)
            print(f'  Avg Win: +{avg_win:.1f}%')
        if losses:
            avg_loss = sum(t['pnl_pct'] for t in losses) / len(losses)
            print(f'  Avg Loss: {avg_loss:.1f}%')

    print(f'{"="*50}\n')


if __name__ == '__main__':
    main()
