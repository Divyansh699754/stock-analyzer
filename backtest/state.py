"""
Backtest state — save/load progress for resumable backtests.
"""

import json
from pathlib import Path
from backtest.portfolio import Portfolio


class BacktestState:
    """Manages backtest progress, portfolio, and history for save/resume."""

    def __init__(self, portfolio: Portfolio, symbols: list,
                 start_date: str, end_date: str):
        self.portfolio = portfolio
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.status = 'pending'  # pending, running, complete
        self.current_day_index = 0
        self.total_days = 0
        self.current_sim_date = start_date
        self.daily_values: list[dict] = []
        self.trades: list[dict] = []
        self.api_calls_used = 0

    @property
    def progress_pct(self) -> float:
        if self.total_days == 0:
            return 0.0
        return round(self.current_day_index / self.total_days * 100, 1)

    def is_complete(self) -> bool:
        return self.status == 'complete'

    def record_day(self, date: str, values: dict):
        """Record portfolio value for a simulated day."""
        self.daily_values.append({'date': date, **values})
        self.current_sim_date = date
        self.current_day_index += 1

    def save(self, filepath: str):
        """Save state to JSON file."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            'status': self.status,
            'symbols': self.symbols,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'current_day_index': self.current_day_index,
            'total_days': self.total_days,
            'current_sim_date': self.current_sim_date,
            'api_calls_used': self.api_calls_used,
            'portfolio': self.portfolio.to_dict(),
            'daily_values': self.daily_values,
            'trades': self.trades + self.portfolio.trades,
        }

        path.write_text(json.dumps(data, indent=2), encoding='utf-8')

    @classmethod
    def load(cls, filepath: str) -> 'BacktestState':
        """Load state from JSON file."""
        data = json.loads(Path(filepath).read_text(encoding='utf-8'))

        portfolio = Portfolio.from_dict(data['portfolio'])
        # Restore trades that were on the portfolio
        portfolio.trades = []

        state = cls(
            portfolio=portfolio,
            symbols=data['symbols'],
            start_date=data['start_date'],
            end_date=data['end_date'],
        )
        state.status = data['status']
        state.current_day_index = data['current_day_index']
        state.total_days = data['total_days']
        state.current_sim_date = data['current_sim_date']
        state.daily_values = data.get('daily_values', [])
        state.trades = data.get('trades', [])
        state.api_calls_used = data.get('api_calls_used', 0)

        return state
