"""Utility helpers for the trading service."""

import datetime
import math
from typing import Iterable, Optional, Set, Tuple, Union

import FinanceDataReader
import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator

from config import setting_env
from data.models import Blacklist, Stock, Subscription
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


def prepare_buy_context(country: str, category: str) -> tuple[str, float, float, float, Set[str], float]:
    usd_krw = float(FinanceDataReader.DataReader("USD/KRW").iloc[-1]["Adj Close"])

    risk_pct = float(getattr(setting_env, "RISK_PCT", 0.0051))
    risk_k = float(getattr(setting_env, "RISK_ATR_MULT", 12.0))
    adtv_limit_ratio = float(getattr(setting_env, "ADTV_LIMIT_RATIO", 0.015))
    default_equity_usd = float(getattr(setting_env, "EQUITY_USD", 100_000.0))

    anchor_date = datetime.datetime.now()
    if country == "USA":
        anchor_date -= datetime.timedelta(days=1)
    anchor_date_str = anchor_date.strftime("%Y-%m-%d")

    equity_base = default_equity_usd *( 1 if country == "USA" else usd_krw )
    risk_amount_value = equity_base * risk_pct

    blacklist_symbols = Blacklist.select(Blacklist.symbol)
    sub_symbols = Subscription.select(Subscription.symbol).where(Subscription.category == category)
    stocks_query = (
        Stock.select(Stock.symbol)
        .where(
            (Stock.country == country)
            & (Stock.symbol.in_(sub_symbols))
            & ~(Stock.symbol.in_(blacklist_symbols))
        )
    )
    stocks = {row.symbol for row in stocks_query}

    return anchor_date_str, risk_amount_value, risk_k, adtv_limit_ratio, stocks, usd_krw


def normalize_dataframe_for_country(df: pd.DataFrame, country: str) -> pd.DataFrame:
    if country == "USA":
        for column in ("open", "high", "close", "low"):
            df[column] = df[column].astype(float)
    return df


def is_same_anchor_date(df: pd.DataFrame, anchor_date: str) -> bool:
    try:
        return str(df.iloc[-1]["date"]) == anchor_date
    except (KeyError, IndexError):
        return False


def has_min_rows(df: pd.DataFrame, min_length: int) -> bool:
    return len(df) >= min_length


def calculate_adtv(df: pd.DataFrame) -> Optional[float]:
    try:
        rolling_volume = df["volume"].rolling(window=50).mean().iloc[-1]
        if pd.isna(rolling_volume):
            return None
        return float(df.iloc[-1]["close"]) * float(rolling_volume)
    except (KeyError, IndexError):
        return None


def meets_liquidity_threshold(adtv: Optional[float], country: str, usd_krw: float) -> bool:
    if adtv is None or adtv <= 0:
        return False
    threshold = 10_000_000 * usd_krw if country == "KOR" else 20_000_000
    return adtv >= threshold


def calculate_atr(df: pd.DataFrame) -> Optional[float]:
    atr_values: list[float] = []
    try:
        for window in (5, 10, 20):
            atr_series = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=window).average_true_range()
            atr_value = float(atr_series.iloc[-1])
            if pd.isna(atr_value) or atr_value <= 0:
                return None
            atr_values.append(atr_value)
    except (KeyError, IndexError):
        return None
    return max(atr_values) if atr_values else None


def apply_bollinger_bands(df: pd.DataFrame, window: int = 20, window_dev: float = 2) -> pd.DataFrame:
    if "close" not in df.columns:
        return df
    indicator = BollingerBands(close=df["close"], window=window, window_dev=window_dev)
    df["BB_Mavg"] = indicator.bollinger_mavg()
    df["BB_Upper"] = indicator.bollinger_hband()
    df["BB_Lower"] = indicator.bollinger_lband()
    return df


def generate_dca_entry_levels(df: pd.DataFrame, atr: float, max_levels: Optional[int] = None) -> Optional[list[float]]:
    """Return descending ladder prices for staged DCA buys using ATR/volatility aware spacing."""

    if atr <= 0:
        return None

    try:
        close_price = float(df.iloc[-1]["close"])
    except (KeyError, IndexError, ValueError, TypeError):
        return None

    if pd.isna(close_price) or close_price <= 0:
        return None

    bb_lower_today = np.nan
    if "BB_Lower" in df.columns:
        bb_lower_today = float(df.iloc[-1]["BB_Lower"])

    if pd.isna(bb_lower_today) or bb_lower_today <= 0:
        try:
            bb_lower_today = float(df["low"].rolling(window=20, min_periods=5).quantile(0.1).iloc[-2])
        except (KeyError, IndexError, ValueError):
            bb_lower_today = np.nan

    swing_floor = np.nan
    try:
        swing_floor = float(df["low"].rolling(window=30, min_periods=5).min().iloc[-2])
    except (KeyError, IndexError, ValueError):
        pass

    if pd.isna(swing_floor) or swing_floor <= 0:
        try:
            swing_floor = float(df["low"].rolling(window=10, min_periods=3).min().iloc[-2])
        except (KeyError, IndexError, ValueError):
            swing_floor = np.nan

    floor_price = 0.0
    if not pd.isna(swing_floor) and swing_floor > 0:
        floor_price = max(floor_price, swing_floor * 0.95)
    if not pd.isna(bb_lower_today) and bb_lower_today > 0:
        floor_price = max(floor_price, bb_lower_today * 0.98)

    min_gap = max(close_price * 0.005, atr * 0.25)
    available_span = max(close_price - floor_price, min_gap)
    theoretical_cap = max(1, int(available_span / min_gap))

    volatility_ratio = atr / close_price
    desired_levels = 2
    if volatility_ratio >= 0.03:
        desired_levels = 5
    elif volatility_ratio >= 0.02:
        desired_levels = 4
    elif volatility_ratio >= 0.012:
        desired_levels = 3

    target_levels = min(theoretical_cap, desired_levels)
    if max_levels is not None and max_levels > 0:
        target_levels = min(target_levels, max_levels)
    target_levels = max(1, target_levels)

    multipliers = np.linspace(0.4, 2.2, num=max(target_levels * 3, 4))
    candidate_pool: list[float] = [close_price - float(mult) * atr for mult in multipliers]
    for extra in (bb_lower_today, swing_floor, floor_price):
        if extra and not pd.isna(extra) and extra > 0:
            candidate_pool.append(float(extra))

    candidate_pool = sorted({val for val in candidate_pool if val > 0}, reverse=True)

    levels: list[float] = []
    prev_level = close_price
    for raw_candidate in candidate_pool:
        candidate = max(raw_candidate, floor_price)
        candidate = min(candidate, prev_level - min_gap)

        if candidate <= 0:
            continue
        if levels and candidate >= levels[-1] - 1e-8:
            continue

        levels.append(float(candidate))
        prev_level = candidate

        if len(levels) >= target_levels:
            break

    if floor_price > 0 and len(levels) < target_levels:
        candidate = max(floor_price, min(prev_level - min_gap, floor_price))
        if candidate > 0 and (not levels or candidate < levels[-1] - min_gap * 0.25):
            levels.append(float(candidate))

    return levels[:target_levels] or None


def build_weight_profile(level_count: int, profile: str = "uniform") -> list[float]:
    """Return weight coefficients tailored to the requested DCA profile."""

    if level_count <= 0:
        return []

    profile_key = profile.lower()
    if profile_key == "front_loaded":
        return [float(level_count - idx) for idx in range(level_count)]
    if profile_key == "bottom_loaded":
        return [float(idx + 1) for idx in range(level_count)]
    if profile_key == "middle_loaded":
        midpoint = (level_count - 1) / 2
        return [float(level_count - abs(idx - midpoint)) for idx in range(level_count)]
    return [1.0] * level_count


def allocate_volume_to_levels(
        price_levels: Iterable[float],
        total_volume: int,
        weights: Optional[Union[Iterable[float], str]] = None,
) -> dict[float, int]:
    if total_volume <= 0:
        return {}

    normalized_levels: list[float] = []
    for price in price_levels:
        try:
            price_val = float(price)
        except (TypeError, ValueError):
            continue
        if pd.isna(price_val) or price_val <= 0:
            continue
        if normalized_levels and abs(normalized_levels[-1] - price_val) < 1e-8:
            continue
        normalized_levels.append(price_val)

    if not normalized_levels:
        return {}

    level_count = len(normalized_levels)
    if isinstance(weights, str):
        weights_list = build_weight_profile(level_count, weights)
    elif weights is None:
        weights_list = [1.0] * level_count
    else:
        weights_list = []
        for weight in weights:
            try:
                weight_val = float(weight)
            except (TypeError, ValueError):
                weight_val = 0.0
            weights_list.append(max(0.0, weight_val))
        if len(weights_list) < level_count:
            weights_list.extend([1.0] * (level_count - len(weights_list)))
        elif len(weights_list) > level_count:
            weights_list = weights_list[:level_count]
        if sum(weights_list) <= 0:
            weights_list = [1.0] * level_count

    weight_sum = sum(weights_list)
    allocations: dict[float, int] = {}
    assigned = 0

    for idx, (price, weight) in enumerate(zip(normalized_levels, weights_list)):
        if idx == level_count - 1:
            qty = total_volume - assigned
        else:
            qty = int(max(0, math.floor(total_volume * (weight / weight_sum))))
            assigned += qty

        if qty <= 0:
            continue

        allocations[price] = allocations.get(price, 0) + qty

    return allocations


def add_prev_close_allocation(levels: dict[float, int], df: pd.DataFrame, base_volume: int) -> dict[float, int]:
    if base_volume <= 0 or len(df) < 2:
        return levels

    prev_close = df.iloc[-2]["close"]
    if pd.isna(prev_close):
        return levels

    prev_close_value = float(prev_close)
    if prev_close_value <= 0:
        return levels

    extra_volume = math.ceil(base_volume * 0.1)
    if extra_volume <= 0:
        return levels

    levels[prev_close_value] = levels.get(prev_close_value, 0) + extra_volume
    return levels


def calculate_position_volume(
        atr: Optional[float],
        adtv: Optional[float],
        close_price: float,
        risk_amount_value: float,
        risk_k: float,
        adtv_limit_ratio: float,
) -> int:
    if atr is None or atr <= 0:
        return 0
    if adtv is None or adtv <= 0 or close_price <= 0:
        return 0
    base_shares = int(risk_amount_value / (atr * risk_k))
    if base_shares <= 0:
        return 0
    shares_adtv_cap = int((adtv * adtv_limit_ratio) / close_price)
    return max(0, min(base_shares, shares_adtv_cap))


def higher_timeframe_ok(df_all: pd.DataFrame) -> bool:
    df_res = df_all[["date", "open", "high", "low", "close", "volume"]].copy()
    df_res["date_dt"] = pd.to_datetime(df_res["date"], errors="coerce")
    df_res = df_res.dropna(subset=["date_dt"]).sort_values("date_dt")
    weekly_ok = False
    monthly_ok = False
    if len(df_res) >= 2:
        weekly = df_res.resample("W-FRI", on="date_dt").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        monthly = df_res.resample("ME", on="date_dt").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        if len(weekly) >= 3:
            wk_close_prev = float(weekly["close"].iloc[-2])
            wk_sma20_series = weekly["close"].rolling(20).mean()
            wk_sma20_prev = wk_sma20_series.iloc[-2] if len(wk_sma20_series) >= 2 else np.nan
            if not pd.isna(wk_sma20_prev):
                weekly_ok = bool(wk_close_prev > float(wk_sma20_prev))
            else:
                wk_down1 = bool(weekly["close"].iloc[-2] < weekly["close"].iloc[-3])
                wk_down2 = bool(weekly["close"].iloc[-3] < weekly["close"].iloc[-4]) if len(weekly) >= 4 else False
                weekly_ok = not (wk_down1 and wk_down2)
        if len(monthly) >= 2:
            mo_sma10_series = monthly["close"].rolling(10).mean()
            mo_sma10_prev = mo_sma10_series.iloc[-2] if len(mo_sma10_series) >= 2 else np.nan
            if not pd.isna(mo_sma10_prev):
                mo_close_prev = float(monthly["close"].iloc[-2])
                monthly_ok = bool(mo_close_prev >= float(mo_sma10_prev))
    return bool(weekly_ok or monthly_ok)


def bb_proximity_ok(df_all: pd.DataFrame, tol: float = 0.05, use_low: bool = True, lookback: int = 3) -> bool:
    df_tail = df_all.tail(int(max(1, lookback)))
    lower = df_tail["BB_Lower"]
    upper = df_tail["BB_Upper"]
    denom = upper - lower
    price_series = np.minimum(df_tail["close"], df_tail["low"]) if use_low else df_tail["close"]
    valid = (~pd.isna(lower)) & (~pd.isna(upper)) & (~pd.isna(price_series)) & (denom > 0)
    if not valid.any():
        return False
    pct_b = (price_series - lower) / denom
    return bool((pct_b[valid] <= tol).any())


def obv_sma_rising(df_all: pd.DataFrame, steps: int = 3) -> bool:
    obv_series = OnBalanceVolumeIndicator(close=df_all["close"], volume=df_all["volume"]).on_balance_volume()
    obv_sma = obv_series.rolling(window=10).mean()
    if len(obv_sma) < steps + 1:
        return False
    if pd.isna(obv_sma.iloc[-1]) or pd.isna(obv_sma.iloc[-steps]):
        return False
    return bool(obv_sma.iloc[-1] > obv_sma.iloc[-steps])


def macd_rebound_ok(df: pd.DataFrame) -> bool:
    macd_indicator = MACD(close=df['close'], window_fast=12, window_slow=26, window_sign=9)
    df['MACD'] = macd_indicator.macd()
    df['MACD_Signal'] = macd_indicator.macd_signal()
    if pd.isna(df['MACD'].iloc[-1]) or pd.isna(df['MACD_Signal'].iloc[-1]):
        return False
    macd_curr = float(df['MACD'].iloc[-1])
    macd_prev = float(df['MACD'].iloc[-2])
    sig_curr = float(df['MACD_Signal'].iloc[-1])
    sig_prev = float(df['MACD_Signal'].iloc[-2])
    recent_below_signal = bool((df['MACD'] <= df['MACD_Signal']).tail(6).head(5).any())
    return (macd_curr >= sig_curr) and ((macd_curr - sig_curr) > (macd_prev - sig_prev)) and recent_below_signal


def rsi_in_range(df: pd.DataFrame, window: int, lower: float, upper: float) -> bool:
    rsi_series = RSIIndicator(close=df['close'], window=window).rsi()
    if pd.isna(rsi_series.iloc[-1]):
        return False
    return lower <= float(rsi_series.iloc[-1]) <= upper


def rsi_rebound_below(df: pd.DataFrame, window: int, upper_bound: float) -> bool:
    rsi_series = RSIIndicator(close=df['close'], window=window).rsi()
    if len(rsi_series) < 2:
        return False
    curr = rsi_series.iloc[-1]
    prev = rsi_series.iloc[-2]
    if pd.isna(curr) or pd.isna(prev):
        return False
    curr_val = float(curr)
    prev_val = float(prev)
    return prev_val < curr_val < upper_bound
