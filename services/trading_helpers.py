"""Utility helpers for the trading service."""

import math
from typing import Iterable, Tuple

import pandas as pd
import numpy as np
from ta.volatility import BollingerBands, AverageTrueRange
from services.data_handler import get_country_by_symbol, get_history_table
from utils.operations import price_refine


def fetch_price_dataframe(symbol: str, days: int = 365) -> pd.DataFrame:
    """Return recent price history for ``symbol``.

    Parameters
    ----------
    symbol: str
        Stock symbol.
    days: int
        Number of days to look back.
    """
    table = get_history_table(get_country_by_symbol(symbol))
    return pd.DataFrame(
        list(
            table.select()
            .where(
                (table.date.between(
                    pd.Timestamp.now() - pd.Timedelta(days=days),
                    pd.Timestamp.now(),
                ))
                & (table.symbol == symbol)
            )
            .order_by(table.date)
            .dicts()
        )
    )


def calc_adjusted_volumes(volume: int, base_price: float, country: str) -> Iterable[tuple[int, float]]:
    """Return tuples of ``(volume, price)`` adjusted for sell queue operations."""
    if country == "KOR":
        return [
            (volume - int(volume * 0.5), math.ceil(price_refine(base_price * 1.080))),
            (int(volume * 0.5), math.ceil(price_refine(base_price * 1.155))),
        ]

    if country == "USA":
        return [
            (volume - int(volume * 0.5), round(base_price * 1.080, 2)),
            (int(volume * 0.5), round(base_price * 1.155, 2)),
        ]
    return []


def compute_resistance_prices(df: pd.DataFrame) -> Tuple[float, float, float]:
    """Compute three resistance prices using recent price action.

    Returns a tuple of:
      - pivot_high: recent pivot high (3-bar local maximum with fallbacks)
      - bb_upper: Bollinger Upper band (20, 2) with quantile fallback
      - atr_up: pivot_high + 0.5 * ATR(max of 5/10/20)

    This function performs safe fallbacks for NaNs and insufficient data.
    """
    if df is None or len(df) < 20:
        raise ValueError("Insufficient data to compute resistance prices")

    # Ensure numeric
    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ATR (max of 5/10/20)
    df['ATR5'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=5).average_true_range()
    df['ATR10'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=10).average_true_range()
    df['ATR20'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=20).average_true_range()
    atr_vals = [df.iloc[-1]['ATR5'], df.iloc[-1]['ATR10'], df.iloc[-1]['ATR20']]
    atr = max([v for v in atr_vals if not pd.isna(v)] or [np.nan])

    # Pivot high (3-bar)
    df['pivot_high_flag'] = (df['high'] > df['high'].shift(1)) & (df['high'] > df['high'].shift(-1))
    pivots_window = df.tail(30)
    pivots = pivots_window[pivots_window['pivot_high_flag']]
    if len(pivots) > 0:
        pivot_high_val = float(pivots.iloc[-1]['high'])
    else:
        # fallback to rolling maxima
        pivot_high_val = float(df['high'].rolling(window=5).max().iloc[-2])
        if pd.isna(pivot_high_val) or pivot_high_val <= 0:
            pivot_high_val = float(df['high'].rolling(window=10).max().iloc[-2])

    # Bollinger Upper with fallback
    boll = BollingerBands(close=df['close'], window=20, window_dev=2)
    bb_upper_today = float(boll.bollinger_hband().iloc[-1])
    if pd.isna(bb_upper_today) or bb_upper_today <= 0:
        bb_upper_today = float(df['high'].rolling(window=20).quantile(0.9).iloc[-2])

    # ATR-up projection
    atr = 0.0 if (pd.isna(atr) or atr <= 0) else float(atr)
    atr_up = float(pivot_high_val) + 0.5 * atr

    price_r1 = max(0.0, float(pivot_high_val))
    price_r2 = max(0.0, float(bb_upper_today))
    price_r3 = max(0.0, float(atr_up))
    return price_r1, price_r2, price_r3
