"""
Technical indicator calculations — MA, MACD, RSI, BIAS, Bollinger Bands.
"""

import numpy as np
import pandas as pd


def calculate_indicators(df: pd.DataFrame) -> dict:
    """
    Calculate all technical indicators from an OHLCV DataFrame.

    Expects columns: Open, High, Low, Close, Volume.
    Returns a flat dict with all indicator values.
    """
    close = df['Close']
    volume = df['Volume']

    # --- Moving Averages ---
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    latest_close = float(close.iloc[-1])
    latest_ma5 = _safe_last(ma5)
    latest_ma10 = _safe_last(ma10)
    latest_ma20 = _safe_last(ma20)
    latest_ma60 = _safe_last(ma60)

    # --- BIAS (deviation from MA5) ---
    if latest_ma5 and latest_ma5 != 0:
        bias_ma5 = round((latest_close - latest_ma5) / latest_ma5 * 100, 2)
    else:
        bias_ma5 = 0.0

    # --- Trend Status ---
    trend_status = _determine_trend(latest_ma5, latest_ma10, latest_ma20)

    # --- MACD (12, 26, 9) ---
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    macd_val = _safe_last(macd_line)
    signal_val = _safe_last(signal_line)
    hist_val = _safe_last(histogram)

    # MACD cross status
    if len(macd_line) >= 2 and len(signal_line) >= 2:
        prev_diff = float(macd_line.iloc[-2]) - float(signal_line.iloc[-2])
        curr_diff = float(macd_line.iloc[-1]) - float(signal_line.iloc[-1])
        if prev_diff <= 0 and curr_diff > 0:
            macd_status = 'Golden Cross'
        elif prev_diff >= 0 and curr_diff < 0:
            macd_status = 'Death Cross'
        elif curr_diff > 0:
            macd_status = 'Bullish'
        else:
            macd_status = 'Bearish'
    else:
        macd_status = 'N/A'

    # --- RSI (14) ---
    rsi_14 = _calculate_rsi(close, 14)

    # --- Volume Ratio (current vs 20-day average) ---
    avg_vol_20 = volume.rolling(20).mean()
    latest_vol = float(volume.iloc[-1]) if len(volume) > 0 else 0
    avg_vol = _safe_last(avg_vol_20)
    if avg_vol and avg_vol > 0:
        volume_ratio = round(latest_vol / avg_vol, 2)
    else:
        volume_ratio = 0.0

    # --- Bollinger Bands (20, 2) ---
    bb_mid = ma20
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    return {
        'ma5': _round(latest_ma5),
        'ma10': _round(latest_ma10),
        'ma20': _round(latest_ma20),
        'ma60': _round(latest_ma60),
        'bias_ma5': bias_ma5,
        'trend_status': trend_status,
        'macd_status': macd_status,
        'macd_histogram': _round(hist_val),
        'rsi_14': _round(rsi_14),
        'volume_ratio': volume_ratio,
        'bollinger_upper': _round(_safe_last(bb_upper)),
        'bollinger_lower': _round(_safe_last(bb_lower)),
        'current_price': round(latest_close, 2),
    }


def _calculate_rsi(series: pd.Series, period: int = 14) -> float:
    """Calculate RSI using exponential moving average of gains/losses."""
    if len(series) < period + 1:
        return 50.0  # neutral default

    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    last_gain = float(avg_gain.iloc[-1])
    last_loss = float(avg_loss.iloc[-1])

    if last_loss == 0:
        return 100.0
    rs = last_gain / last_loss
    return round(100 - (100 / (1 + rs)), 1)


def _determine_trend(ma5, ma10, ma20) -> str:
    """Determine trend alignment from moving averages."""
    if ma5 is None or ma10 is None or ma20 is None:
        return 'Insufficient Data'
    if ma5 > ma10 > ma20:
        return 'Bullish Alignment (MA5 > MA10 > MA20)'
    elif ma5 < ma10 < ma20:
        return 'Bearish Alignment (MA5 < MA10 < MA20)'
    else:
        return 'Mixed / Transitioning'


def _safe_last(series: pd.Series):
    """Get last non-NaN value from series, or None."""
    if series is None or series.empty:
        return None
    last = series.iloc[-1]
    if pd.isna(last):
        return None
    return float(last)


def _round(val, decimals=2):
    """Round a value, handling None."""
    if val is None:
        return 0.0
    return round(val, decimals)
