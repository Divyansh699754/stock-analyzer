"""
Backtest report generator — Plotly charts + stats.
"""

import csv
import math
import logging
from pathlib import Path
from datetime import datetime

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from backtest.state import BacktestState

logger = logging.getLogger(__name__)

REPORT_DIR = Path(__file__).parent.parent / 'reports' / 'backtest'


def generate_report(state: BacktestState, benchmarks: dict = None):
    """Generate full backtest report with graphs and stats."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    stats = compute_stats(state, benchmarks)
    _print_stats_table(stats)

    # Generate charts
    fig = _create_charts(state, benchmarks, stats)
    html_path = REPORT_DIR / f'backtest_{timestamp}.html'
    fig.write_html(str(html_path), include_plotlyjs=True)
    logger.info(f'Report saved: {html_path}')

    # Save trade log as CSV
    csv_path = REPORT_DIR / f'trades_{timestamp}.csv'
    _save_trade_csv(state.trades, csv_path)
    logger.info(f'Trade log saved: {csv_path}')

    # Save static images
    try:
        png_path = REPORT_DIR / f'backtest_{timestamp}.png'
        fig.write_image(str(png_path), width=1200, height=900)
        logger.info(f'Chart image saved: {png_path}')
    except Exception:
        logger.debug('PNG export requires kaleido package — skipped')

    return str(html_path)


def compute_stats(state: BacktestState, benchmarks: dict = None) -> dict:
    """Compute summary statistics."""
    daily = state.daily_values
    trades = state.trades

    if not daily:
        return {}

    # Portfolio returns (USD)
    usd_values = [d.get('total_usd', 0) for d in daily]
    start_usd = usd_values[0] if usd_values[0] > 0 else 1
    end_usd = usd_values[-1]
    total_return_usd = (end_usd - start_usd) / start_usd * 100

    # Annualized return
    days = len(daily)
    years = days / 252  # trading days per year
    if years > 0 and end_usd > 0 and start_usd > 0:
        ann_return_usd = ((end_usd / start_usd) ** (1 / years) - 1) * 100
    else:
        ann_return_usd = 0

    # Max drawdown
    max_dd = _max_drawdown(usd_values)

    # Win/loss
    sells = [t for t in trades if t.get('action') == 'SELL']
    wins = [t for t in sells if t.get('pnl_pct', 0) > 0]
    losses = [t for t in sells if t.get('pnl_pct', 0) <= 0]
    win_rate = len(wins) / len(sells) * 100 if sells else 0
    avg_win = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t['pnl_pct'] for t in losses) / len(losses) if losses else 0

    # Sharpe ratio (simplified — daily returns, annualized)
    if len(usd_values) > 1:
        returns = [(usd_values[i] - usd_values[i-1]) / usd_values[i-1]
                   for i in range(1, len(usd_values)) if usd_values[i-1] > 0]
        if returns:
            import numpy as np
            mean_r = np.mean(returns)
            std_r = np.std(returns)
            sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0
        else:
            sharpe = 0
    else:
        sharpe = 0

    stats = {
        'bot': {
            'total_return': round(total_return_usd, 1),
            'annualized_return': round(ann_return_usd, 1),
            'max_drawdown': round(max_dd, 1),
            'win_rate': round(win_rate, 0),
            'avg_win': round(avg_win, 1),
            'avg_loss': round(avg_loss, 1),
            'total_trades': len(trades),
            'sharpe_ratio': round(sharpe, 2),
        }
    }

    # Benchmark stats
    if benchmarks:
        dates = [d['date'] for d in daily]
        for name, hist in benchmarks.items():
            bench_values = []
            for date in dates:
                mask = hist.index.strftime('%Y-%m-%d') <= date
                if mask.any():
                    bench_values.append(float(hist.loc[mask, 'Close'].iloc[-1]))
            if bench_values:
                start_b = bench_values[0]
                end_b = bench_values[-1]
                ret = (end_b - start_b) / start_b * 100 if start_b > 0 else 0
                dd = _max_drawdown(bench_values)
                stats[name] = {
                    'total_return': round(ret, 1),
                    'max_drawdown': round(dd, 1),
                }

    return stats


def _max_drawdown(values: list) -> float:
    """Calculate maximum drawdown percentage."""
    if not values:
        return 0
    peak = values[0]
    max_dd = 0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            max_dd = max(max_dd, dd)
    return max_dd


def _create_charts(state: BacktestState, benchmarks: dict,
                   stats: dict) -> go.Figure:
    """Create multi-panel Plotly figure."""
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=(
            'Portfolio Value Over Time',
            'Drawdown',
            'Trade P&L Distribution',
        ),
        vertical_spacing=0.08,
        row_heights=[0.45, 0.25, 0.30],
    )

    dates = [d['date'] for d in state.daily_values]

    # Chart 1: Portfolio value
    usd_values = [d.get('total_usd', 0) for d in state.daily_values]
    fig.add_trace(
        go.Scatter(x=dates, y=usd_values, name='Bot (USD)',
                  line=dict(color='green', width=2)),
        row=1, col=1,
    )

    # Add benchmarks
    colors = {'S&P 500': 'blue', 'NIFTY 50': 'orange'}
    if benchmarks:
        for name, hist in benchmarks.items():
            bench_vals = []
            for date in dates:
                mask = hist.index.strftime('%Y-%m-%d') <= date
                if mask.any():
                    bench_vals.append(float(hist.loc[mask, 'Close'].iloc[-1]))
                else:
                    bench_vals.append(None)

            if bench_vals and bench_vals[0] and bench_vals[0] > 0:
                # Normalize to same starting value
                start = bench_vals[0]
                normalized = [
                    (v / start * usd_values[0]) if v else None
                    for v in bench_vals
                ]
                fig.add_trace(
                    go.Scatter(x=dates, y=normalized, name=name,
                              line=dict(color=colors.get(name, 'gray'), width=1.5)),
                    row=1, col=1,
                )

    # Chart 2: Drawdown
    peak = usd_values[0] if usd_values else 1
    drawdowns = []
    for v in usd_values:
        if v > peak:
            peak = v
        dd = -(peak - v) / peak * 100 if peak > 0 else 0
        drawdowns.append(dd)

    fig.add_trace(
        go.Scatter(x=dates, y=drawdowns, name='Drawdown',
                  fill='tozeroy', line=dict(color='red', width=1)),
        row=2, col=1,
    )

    # Chart 3: Trade P&L histogram
    sells = [t for t in state.trades if t.get('action') == 'SELL']
    pnls = [t.get('pnl_pct', 0) for t in sells]

    if pnls:
        fig.add_trace(
            go.Histogram(x=pnls, name='Trade P&L %',
                        marker_color=['green' if p > 0 else 'red' for p in sorted(pnls)],
                        nbinsx=30),
            row=3, col=1,
        )

    fig.update_layout(
        title=f'Backtest Report — {state.start_date} to {state.end_date}',
        height=900,
        showlegend=True,
        template='plotly_white',
    )

    fig.update_xaxes(title_text='Date', row=3, col=1)
    fig.update_yaxes(title_text='Value ($)', row=1, col=1)
    fig.update_yaxes(title_text='Drawdown %', row=2, col=1)
    fig.update_yaxes(title_text='Count', row=3, col=1)

    return fig


def _print_stats_table(stats: dict):
    """Print stats comparison table to console."""
    if not stats:
        return

    bot = stats.get('bot', {})
    print(f'\n{"="*60}')
    print(f'  BACKTEST RESULTS')
    print(f'{"="*60}')

    headers = ['Metric', 'Bot']
    bench_names = [k for k in stats if k != 'bot']
    headers.extend(bench_names)

    rows = [
        ('Total Return', f'{bot.get("total_return", 0):+.1f}%'),
        ('Annualized Return', f'{bot.get("annualized_return", 0):+.1f}%'),
        ('Max Drawdown', f'-{bot.get("max_drawdown", 0):.1f}%'),
        ('Win Rate', f'{bot.get("win_rate", 0):.0f}%'),
        ('Avg Win', f'+{bot.get("avg_win", 0):.1f}%'),
        ('Avg Loss', f'{bot.get("avg_loss", 0):.1f}%'),
        ('Total Trades', f'{bot.get("total_trades", 0)}'),
        ('Sharpe Ratio', f'{bot.get("sharpe_ratio", 0):.2f}'),
    ]

    # Print
    col_width = 18
    header_line = ''.join(h.ljust(col_width) for h in headers)
    print(header_line)
    print('-' * len(header_line))

    for label, bot_val in rows:
        line = label.ljust(col_width) + bot_val.ljust(col_width)
        for name in bench_names:
            bench = stats[name]
            if label == 'Total Return':
                line += f'{bench.get("total_return", 0):+.1f}%'.ljust(col_width)
            elif label == 'Max Drawdown':
                line += f'-{bench.get("max_drawdown", 0):.1f}%'.ljust(col_width)
            else:
                line += '—'.ljust(col_width)
        print(line)

    print(f'{"="*60}\n')


def _save_trade_csv(trades: list, filepath: Path):
    """Save trade log as CSV."""
    if not trades:
        return

    fields = ['date', 'symbol', 'action', 'price', 'quantity', 'pnl', 'pnl_pct', 'reason']
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(trades)
