"""배당주 전략 (기존 filter_stable_*)"""
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
    macd_rebound_ok,
    meets_liquidity_threshold,
    normalize_dataframe_for_country,
    obv_sma_rising,
    prepare_buy_context,
    rsi_rebound_below,
    add_prev_close_allocation,
)
from services.data_handler import get_country_by_symbol


class DividendStrategy(BaseStrategy):
    """배당주 전략 (안정적인 배당 수익 추구)"""

    def filter_for_buy(self, country: str = "KOR") -> dict[str, dict[float, int]]:
        """배당주 매수 대상 필터링"""
        anchor_date, risk_amount_value, risk_k, adtv_limit_ratio, stocks, usd_krw = prepare_buy_context(country, "dividend")
        buy_levels: dict[str, dict[float, int]] = {}

        for symbol in stocks:
            try:
                df = fetch_price_dataframe(symbol)
                if df is None or df.empty:
                    continue
                df = normalize_dataframe_for_country(df, country)

                if not is_same_anchor_date(df, anchor_date):
                    continue

                if not has_min_rows(df, 100):
                    continue

                adtv = calculate_adtv(df)
                if not meets_liquidity_threshold(adtv, country, usd_krw):
                    continue

                if not higher_timeframe_ok(df):
                    continue

                df = apply_bollinger_bands(df)
                if not bb_proximity_ok(df, tol=0.10, use_low=True, lookback=3):
                    continue

                if not obv_sma_rising(df, steps=3):
                    continue

                if not (rsi_rebound_below(df, window=7, upper_bound=30) or macd_rebound_ok(df)):
                    continue

                if not (float(df.iloc[-1]['close']) > float(df.iloc[-2]['low'])):
                    continue

                atr = calculate_atr(df)
                if atr is None:
                    continue

                close_price = float(df.iloc[-1]['close'])
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
                logging.error(f"DividendStrategy.filter_for_buy 처리 중 에러: {symbol} -> {e}")
        return buy_levels

    def filter_for_sell(
            self,
            stocks_held: Union[List[StockResponseDTO], StockResponseDTO, None]
    ) -> dict[str, dict[float, int]]:
        """배당주 매도 대상 필터링"""
        sell_levels: dict[str, dict[float, int]] = {}
        if not stocks_held:
            return sell_levels

        holdings = stocks_held if isinstance(stocks_held, list) else [stocks_held]
        growth_query = (
            Subscription
            .select(Subscription.symbol)
            .where(Subscription.category == "growth")
        )
        growth_symbols = {sub.symbol for sub in growth_query}

        for stock in holdings:
            try:
                symbol = stock.pdno
            except Exception:
                continue

            if symbol in growth_symbols:
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

                if not has_min_rows(df, 100):
                    continue

                df = apply_bollinger_bands(df)
                if df is None or "BB_Upper" not in df.columns:
                    continue

                close_price = float(df.iloc[-1]["close"])
                bb_upper = float(df["BB_Upper"].iloc[-1])
                bb_mavg = float(df["BB_Mavg"].iloc[-1])

                if pd.isna(bb_upper) or pd.isna(bb_mavg):
                    continue

                atr = calculate_atr(df)
                if atr is None:
                    continue

                # 볼린저 밴드 상단 근접 시 일부 매도
                dist_to_upper = (bb_upper - close_price) / atr if atr > 0 else 999
                if dist_to_upper <= 0.5:
                    sell_vol = max(1, int(hldg_qty * 0.5))
                    sell_price = round(close_price * 1.005, 2) if country == "USA" else int(close_price * 1.005)
                    sell_levels.setdefault(symbol, {})[sell_price] = sell_vol
                    continue

                # 볼린저 밴드 중간선 위에서 상승 모멘텀 약화 시
                if close_price > bb_mavg:
                    rsi_vals = self._compute_rsi(df, window=7)
                    if rsi_vals is not None and len(rsi_vals) >= 2:
                        if rsi_vals.iloc[-1] < rsi_vals.iloc[-2] and rsi_vals.iloc[-1] > 70:
                            sell_vol = max(1, int(hldg_qty * 0.3))
                            sell_price = round(close_price * 1.003, 2) if country == "USA" else int(close_price * 1.003)
                            sell_levels.setdefault(symbol, {})[sell_price] = sell_vol

            except Exception as e:
                logging.error(f"DividendStrategy.filter_for_sell 처리 중 에러: {symbol} -> {e}")
                continue

        return sell_levels

    @staticmethod
    def _compute_rsi(df, window: int = 14):
        """RSI 계산"""
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=window, min_periods=window).mean()
        avg_loss = loss.rolling(window=window, min_periods=window).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
