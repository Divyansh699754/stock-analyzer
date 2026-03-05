"""
Backtest portfolio — fake portfolio with separate USD/INR pools.
"""

from dataclasses import dataclass, field


@dataclass
class Holding:
    symbol: str
    quantity: int
    avg_cost: float
    stop_loss: float = 0.0
    target: float = 0.0
    entry_date: str = ''


class Portfolio:
    """Simulated portfolio with separate USD and INR cash pools."""

    def __init__(self, cash_usd: float = 10000, cash_inr: float = 1000000,
                 max_position_pct: float = 0.20):
        self.cash_usd = cash_usd
        self.cash_inr = cash_inr
        self.initial_usd = cash_usd
        self.initial_inr = cash_inr
        self.max_position_pct = max_position_pct
        self.holdings: dict[str, Holding] = {}
        self.trades: list[dict] = []

    def _is_indian(self, symbol: str) -> bool:
        s = symbol.upper()
        return s.endswith('.NS') or s.endswith('.BO')

    def _get_cash(self, symbol: str) -> float:
        return self.cash_inr if self._is_indian(symbol) else self.cash_usd

    def _set_cash(self, symbol: str, amount: float):
        if self._is_indian(symbol):
            self.cash_inr = amount
        else:
            self.cash_usd = amount

    def _get_total_pool(self, symbol: str, current_prices: dict) -> float:
        """Total value of the relevant currency pool (cash + holdings)."""
        cash = self._get_cash(symbol)
        is_indian = self._is_indian(symbol)
        holdings_value = sum(
            h.quantity * current_prices.get(h.symbol, h.avg_cost)
            for h in self.holdings.values()
            if self._is_indian(h.symbol) == is_indian
        )
        return cash + holdings_value

    def buy(self, symbol: str, price: float, date: str,
            stop_loss: float = 0, target: float = 0) -> bool:
        """
        Buy a stock. Position sized to max_position_pct of pool.
        Returns True if trade executed.
        """
        if symbol in self.holdings:
            return False  # already holding

        cash = self._get_cash(symbol)
        max_amount = cash * self.max_position_pct
        quantity = int(max_amount / price)

        if quantity <= 0:
            return False

        cost = quantity * price
        self._set_cash(symbol, cash - cost)
        self.holdings[symbol] = Holding(
            symbol=symbol,
            quantity=quantity,
            avg_cost=price,
            stop_loss=stop_loss,
            target=target,
            entry_date=date,
        )

        self.trades.append({
            'date': date,
            'symbol': symbol,
            'action': 'BUY',
            'price': round(price, 2),
            'quantity': quantity,
            'reason': f'Entry at {price:.2f}',
        })
        return True

    def sell(self, symbol: str, price: float, date: str, reason: str = '') -> dict | None:
        """Sell a held position. Returns trade record or None."""
        if symbol not in self.holdings:
            return None

        h = self.holdings.pop(symbol)
        proceeds = h.quantity * price
        self._set_cash(symbol, self._get_cash(symbol) + proceeds)

        cost = h.quantity * h.avg_cost
        pnl = proceeds - cost
        pnl_pct = round((price - h.avg_cost) / h.avg_cost * 100, 2)

        trade = {
            'date': date,
            'symbol': symbol,
            'action': 'SELL',
            'price': round(price, 2),
            'quantity': h.quantity,
            'pnl': round(pnl, 2),
            'pnl_pct': pnl_pct,
            'reason': reason,
        }
        self.trades.append(trade)
        return trade

    def check_stops(self, current_prices: dict, date: str) -> list:
        """Check stop-loss and take-profit for all holdings. Returns list of triggered trades."""
        triggered = []
        symbols = list(self.holdings.keys())

        for symbol in symbols:
            h = self.holdings[symbol]
            price = current_prices.get(symbol)
            if price is None:
                continue

            if h.stop_loss > 0 and price <= h.stop_loss:
                trade = self.sell(symbol, price, date, reason='Stop-loss triggered')
                if trade:
                    triggered.append(trade)
            elif h.target > 0 and price >= h.target:
                trade = self.sell(symbol, price, date, reason='Target reached')
                if trade:
                    triggered.append(trade)

        return triggered

    def get_total_value(self, current_prices: dict) -> dict:
        """Calculate total portfolio value."""
        holdings_usd = sum(
            h.quantity * current_prices.get(h.symbol, h.avg_cost)
            for h in self.holdings.values()
            if not self._is_indian(h.symbol)
        )
        holdings_inr = sum(
            h.quantity * current_prices.get(h.symbol, h.avg_cost)
            for h in self.holdings.values()
            if self._is_indian(h.symbol)
        )

        return {
            'cash_usd': round(self.cash_usd, 2),
            'cash_inr': round(self.cash_inr, 2),
            'holdings_usd': round(holdings_usd, 2),
            'holdings_inr': round(holdings_inr, 2),
            'total_usd': round(self.cash_usd + holdings_usd, 2),
            'total_inr': round(self.cash_inr + holdings_inr, 2),
        }

    def to_dict(self) -> dict:
        """Serialize portfolio for state saving."""
        return {
            'cash_usd': self.cash_usd,
            'cash_inr': self.cash_inr,
            'initial_usd': self.initial_usd,
            'initial_inr': self.initial_inr,
            'max_position_pct': self.max_position_pct,
            'holdings': {
                s: {
                    'quantity': h.quantity,
                    'avg_cost': h.avg_cost,
                    'stop_loss': h.stop_loss,
                    'target': h.target,
                    'entry_date': h.entry_date,
                }
                for s, h in self.holdings.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Portfolio':
        """Deserialize portfolio from state."""
        p = cls(
            cash_usd=data['cash_usd'],
            cash_inr=data['cash_inr'],
            max_position_pct=data.get('max_position_pct', 0.20),
        )
        p.initial_usd = data.get('initial_usd', data['cash_usd'])
        p.initial_inr = data.get('initial_inr', data['cash_inr'])
        for s, h in data.get('holdings', {}).items():
            p.holdings[s] = Holding(
                symbol=s,
                quantity=h['quantity'],
                avg_cost=h['avg_cost'],
                stop_loss=h.get('stop_loss', 0),
                target=h.get('target', 0),
                entry_date=h.get('entry_date', ''),
            )
        return p
