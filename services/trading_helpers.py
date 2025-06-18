"""Utility helpers for the trading service."""

import math
from typing import Iterable

import pandas as pd
from services.data_handler import get_country_by_symbol, get_history_table


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
            (volume - int(volume * 0.5), math.ceil(base_price * 1.080)),
            (int(volume * 0.5), math.ceil(base_price * 1.155)),
        ]

    if country == "USA":
        return [
            (volume - int(volume * 0.5), round(base_price * 1.080, 2)),
            (int(volume * 0.5), round(base_price * 1.155, 2)),
        ]
    return []
