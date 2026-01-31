"""박스권 전략 (기존 filter_box_*)"""
import logging
from typing import List, Union

import pandas as pd

from data.dto.account_dto import StockResponseDTO
from data.models import Subscription
from services.strategies.base import BaseStrategy
from services.trading_helpers import (
    allocate_volume_to_levels,
    apply_bollinger_bands,
    bb_proximity_ok,
    calculate_atr,
    calculate_adtv,
    calculate_position_volume,
    fetch_price_dataframe,
    generate_dca_entry_levels,
    higher_timeframe_ok,
    has_min_rows,
    is_same_anchor_date,
    meets_liquidity_threshold,
    normalize_dataframe_for_country,
    obv_sma_rising,
    prepare_buy_context,
    add_prev_close_allocation,
)
from services.data_handler import get_country_by_symbol


class RangeBoundStrategy(BaseStrategy):
    """박스권 전략 (횡보 구간 매매)"""

    def filter_for_buy(self, country: str = "KOR") -> dict[str, dict[float, int]]:
        """박스권 매수 대상 필터링"""
        anchor_date, risk_amount_value, risk_k, adtv_limit_ratio, stocks, usd_krw = prepare_buy_context(country, "box")
        buy_levels: dict[str, dict[float, int]] = {}

        for symbol in stocks:
            try:
                df = fetch_price_dataframe(symbol)
                if df is None or df.empty:
                    continue
                df = normalize_dataframe_for_country(df, country)

                if not is_same_anchor_date(df, anchor_date):
                    continue
                if not has_min_rows(df, 120):
                    continue

                adtv = calculate_adtv(df)
                if not meets_liquidity_threshold(adtv, country, usd_krw):
                    continue

                df = apply_bollinger_bands(df)

                bb_upper = df["BB_Upper"].iloc[-1]
                bb_lower = df["BB_Lower"].iloc[-1]
                bb_mavg = df["BB_Mavg"].iloc[-1]
                if pd.isna(bb_upper) or pd.isna(bb_lower) or pd.isna(bb_mavg) or bb_mavg <= 0:
                    continue
                width_ratio = float((bb_upper - bb_lower) / bb_mavg)
                if not (0.07 <= width_ratio <= 0.18):
                    continue

                sma20 = df["close"].rolling(window=20).mean()
                if len(sma20) < 11 or pd.isna(sma20.iloc[-1]) or pd.isna(sma20.iloc[-11]):
                    continue
                slope_ratio = abs(float(sma20.iloc[-1]) / float(sma20.iloc[-11]) - 1.0)
                if slope_ratio > 0.05:
                    continue

                if not higher_timeframe_ok(df):
                    continue
                if not obv_sma_rising(df, steps=3):
                    continue

                if not bb_proximity_ok(df, tol=0.15, use_low=True, lookback=3):
                    continue

                atr = calculate_atr(df)
                if atr is None:
                    continue

                close_price = float(df.iloc[-1]["close"])
                volume = calculate_position_volume(
                    atr=atr,
                    adtv=adtv,
                    close_price=close_price,
                    risk_amount_value=risk_amount_value,
                    risk_k=risk_k,
                    adtv_limit_ratio=adtv_limit_ratio,
                )
                if volume <= 0:
                    continue

                price_levels = generate_dca_entry_levels(df, atr)
                if not price_levels:
                    continue

                levels = allocate_volume_to_levels(price_levels, total_volume=volume)
                if not levels:
                    continue

                buy_levels[symbol] = add_prev_close_allocation(levels, df, volume)
            except Exception as e:
                logging.error(f"RangeBoundStrategy.filter_for_buy 처리 중 에러: {symbol} -> {e}")
        return buy_levels

    def filter_for_sell(
            self,
            stocks_held: Union[List[StockResponseDTO], StockResponseDTO, None]
    ) -> dict[str, dict[float, int]]:
        """박스권 매도 대상 필터링"""
        sell_levels: dict[str, dict[float, int]] = {}
        if not stocks_held:
            return sell_levels

        holdings = stocks_held if isinstance(stocks_held, list) else [stocks_held]
        box_query = (
            Subscription
            .select(Subscription.symbol)
            .where(Subscription.category == "box")
        )
        box_symbols = {sub.symbol for sub in box_query}

        for stock in holdings:
            try:
                symbol = stock.pdno
            except Exception:
                continue

            if symbol not in box_symbols:
                continue

            country = get_country_by_symbol(symbol)
            if not country:
                continue

            try:
                hldg_qty = int(float(getattr(stock, "hldg_qty", 0) or 0))
            except (TypeError, ValueError):
                hldg_qty = 0

            if hldg_qty <= 0:
                continue

            try:
                df = fetch_price_dataframe(symbol)
                if df is None or df.empty:
                    continue
                df = normalize_dataframe_for_country(df, country)

                if not has_min_rows(df, 120):
                    continue

                df = apply_bollinger_bands(df)
                if df is None or "BB_Upper" not in df.columns:
                    continue

                close_price = float(df.iloc[-1]["close"])
                bb_upper = float(df["BB_Upper"].iloc[-1])
                bb_lower = float(df["BB_Lower"].iloc[-1])
                bb_mavg = float(df["BB_Mavg"].iloc[-1])

                if pd.isna(bb_upper) or pd.isna(bb_lower) or pd.isna(bb_mavg):
                    continue

                atr = calculate_atr(df)
                if atr is None:
                    continue

                # 볼린저 밴드 상단 근접 시 매도
                dist_to_upper = (bb_upper - close_price) / atr if atr > 0 else 999
                if dist_to_upper <= 0.3:
                    sell_vol = max(1, int(hldg_qty * 0.5))
                    sell_price = round(bb_upper * 0.99, 2) if country == "USA" else int(bb_upper * 0.99)
                    sell_levels.setdefault(symbol, {})[sell_price] = sell_vol
                    continue

                # 박스권 이탈 시 (하단 돌파)
                if close_price < bb_lower:
                    sell_vol = max(1, int(hldg_qty * 0.7))
                    sell_price = round(close_price * 0.995, 2) if country == "USA" else int(close_price * 0.995)
                    sell_levels.setdefault(symbol, {})[sell_price] = sell_vol

            except Exception as e:
                logging.error(f"RangeBoundStrategy.filter_for_sell 처리 중 에러: {symbol} -> {e}")
                continue

        return sell_levels
