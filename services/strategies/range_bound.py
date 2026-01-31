"""박스권 전략 - 횡보 구간 매매

특징:
- 박스권 최소 20거래일 유지 확인
- 가짜 돌파 필터 (3일 확인)
- VIX 기반 매수 중단
"""
from typing import List, Union

import pandas as pd

from config.logging_config import get_logger
from config.strategy_config import RANGEBOX_CONFIG
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
from services.market_condition import (
    is_buy_allowed,
    get_position_size_adjusted,
    get_sell_ratio_adjusted,
    check_range_bound_duration,
    check_fakeout_filter,
)
from services.data_handler import get_country_by_symbol

logger = get_logger(__name__)


class RangeBoundStrategy(BaseStrategy):
    """박스권 전략 (횡보 구간 매매)"""

    def filter_for_buy(self, country: str = "KOR") -> dict[str, dict[float, int]]:
        """박스권 매수 대상 필터링"""
        # VIX 체크
        buy_allowed, vix = is_buy_allowed()
        if not buy_allowed:
            logger.info(f"VIX {vix:.2f} >= 30, 박스권 매수 중단")
            return {}
        
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
                if not has_min_rows(df, RANGEBOX_CONFIG.min_data_rows):
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
                if not (RANGEBOX_CONFIG.bb_width_min <= width_ratio <= RANGEBOX_CONFIG.bb_width_max):
                    continue

                sma20 = df["close"].rolling(window=20).mean()
                if len(sma20) < 11 or pd.isna(sma20.iloc[-1]) or pd.isna(sma20.iloc[-11]):
                    continue
                slope_ratio = abs(float(sma20.iloc[-1]) / float(sma20.iloc[-11]) - 1.0)
                if slope_ratio > RANGEBOX_CONFIG.sma_slope_max:
                    continue

                # 박스권 최소 20거래일 유지 확인
                if not check_range_bound_duration(df, 
                        min_days=RANGEBOX_CONFIG.min_range_days,
                        bb_width_range=(RANGEBOX_CONFIG.bb_width_min, RANGEBOX_CONFIG.bb_width_max)):
                    continue

                # 가짜 돌파 필터 (3일 확인)
                if not check_fakeout_filter(df, confirm_days=RANGEBOX_CONFIG.fakeout_confirm_days):
                    continue

                if not higher_timeframe_ok(df):
                    continue
                if not obv_sma_rising(df, steps=3):
                    continue

                if not bb_proximity_ok(df, tol=RANGEBOX_CONFIG.bb_tolerance, use_low=True, lookback=3):
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

                # 시장 상황 기반 포지션 조정
                volume = get_position_size_adjusted(volume, country)
                
                # 종목당 최대 비중 체크
                volume = self._apply_max_position_weight(volume, close_price, risk_amount_value)

                price_levels = generate_dca_entry_levels(df, atr)
                if not price_levels:
                    continue

                levels = allocate_volume_to_levels(price_levels, total_volume=volume)
                if not levels:
                    continue

                buy_levels[symbol] = add_prev_close_allocation(levels, df, volume)
            except Exception as e:
                logger.error(f"RangeBoundStrategy.filter_for_buy 처리 중 에러: {symbol} -> {e}")
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

                if not has_min_rows(df, RANGEBOX_CONFIG.min_data_rows):
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

                # 볼린저 밴드 상단 근접 시 매도 (VIX 기반 비율 조정)
                dist_to_upper = (bb_upper - close_price) / atr if atr > 0 else 999
                if dist_to_upper <= 0.3:
                    base_ratio = RANGEBOX_CONFIG.sell_ratio_upper
                    adjusted_ratio = get_sell_ratio_adjusted(base_ratio)
                    sell_vol = max(1, int(hldg_qty * adjusted_ratio))
                    sell_price = round(bb_upper * 0.99, 2) if country == "USA" else int(bb_upper * 0.99)
                    sell_levels.setdefault(symbol, {})[sell_price] = sell_vol
                    logger.info(f"박스권 {symbol} BB상단 도달 - 매도비율 {adjusted_ratio:.1%}")
                    continue

                # 박스권 이탈 시 (하단 돌파) - 3일 확인 후 매도
                if close_price < bb_lower:
                    # 3일 연속 하단 이탈 확인
                    if len(df) >= 3:
                        recent_3 = df.tail(3)
                        all_below = all(
                            float(recent_3.iloc[i]["close"]) < float(recent_3.iloc[i]["BB_Lower"])
                            for i in range(len(recent_3))
                            if not pd.isna(recent_3.iloc[i]["BB_Lower"])
                        )
                        if all_below:
                            base_ratio = RANGEBOX_CONFIG.sell_ratio_breakdown
                            adjusted_ratio = get_sell_ratio_adjusted(base_ratio)
                            sell_vol = max(1, int(hldg_qty * adjusted_ratio))
                            sell_price = round(close_price * 0.995, 2) if country == "USA" else int(close_price * 0.995)
                            sell_levels.setdefault(symbol, {})[sell_price] = sell_vol
                            logger.info(f"박스권 {symbol} 3일 연속 하단이탈 - 매도비율 {adjusted_ratio:.1%}")

            except Exception as e:
                logger.error(f"RangeBoundStrategy.filter_for_sell 처리 중 에러: {symbol} -> {e}")
                continue

        return sell_levels
