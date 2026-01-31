"""배당주 전략 - 안정적인 배당 수익 추구

특징:
- 배당수익률 3% 이상, 배당성향 40-80% 필터링
- 연간 리밸런싱 (단기 매매 아님)
- VIX 기반 매수 중단
"""
from typing import List, Union

import pandas as pd

from config.logging_config import get_logger
from config.strategy_config import DIVIDEND_CONFIG
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
from services.market_condition import is_buy_allowed, get_position_size_adjusted
from services.data_handler import get_country_by_symbol

logger = get_logger(__name__)


class DividendStrategy(BaseStrategy):
    """배당주 전략 (안정적인 배당 수익 추구)"""

    def filter_for_buy(self, country: str = "KOR") -> dict[str, dict[float, int]]:
        """배당주 매수 대상 필터링"""
        # VIX 체크 - 30 이상이면 매수 중단
        buy_allowed, vix = is_buy_allowed()
        if not buy_allowed:
            logger.info(f"VIX {vix:.2f} >= 30, 배당주 매수 중단")
            return {}
        
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

                if not has_min_rows(df, DIVIDEND_CONFIG.min_data_rows):
                    continue

                adtv = calculate_adtv(df)
                if not meets_liquidity_threshold(adtv, country, usd_krw):
                    continue

                if not higher_timeframe_ok(df):
                    continue

                df = apply_bollinger_bands(df)
                if not bb_proximity_ok(df, tol=DIVIDEND_CONFIG.bb_tolerance, use_low=True, lookback=3):
                    continue

                # OBV 상승 확인 기간 5일로 확대
                if not obv_sma_rising(df, steps=DIVIDEND_CONFIG.obv_rising_steps):
                    continue

                if not (rsi_rebound_below(df, window=7, upper_bound=DIVIDEND_CONFIG.rsi_upper_bound) or macd_rebound_ok(df)):
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

                # 시장 상황 기반 포지션 사이즈 조정
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
                logger.error(f"DividendStrategy.filter_for_buy 처리 중 에러: {symbol} -> {e}")
        return buy_levels
    
    def filter_for_sell(
            self,
            stocks_held: Union[List[StockResponseDTO], StockResponseDTO, None]
    ) -> dict[str, dict[float, int]]:
        """배당주 매도 대상 필터링 - 연간 리밸런싱 방식
        
        배당주는 장기 보유 목적이므로 단기 BB 기반 매도 제거.
        매도 조건:
        1. 배당 삭감/중단 시 (외부 데이터 필요 - 추후 구현)
        2. 펀더멘털 악화 시 (연간 리밸런싱)
        """
        sell_levels: dict[str, dict[float, int]] = {}
        if not stocks_held:
            return sell_levels

        holdings = stocks_held if isinstance(stocks_held, list) else [stocks_held]

        # 다른 전략 종목 제외 (해당 전략에서 처리)
        other_strategy_query = (
            Subscription
            .select(Subscription.symbol)
            .where(Subscription.category.in_(["growth", "box"]))
        )
        other_symbols = {sub.symbol for sub in other_strategy_query}

        for stock in holdings:
            try:
                symbol = stock.pdno
            except Exception:
                continue

            if symbol in other_symbols:
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

                if not has_min_rows(df, DIVIDEND_CONFIG.min_data_rows):
                    continue

                df = apply_bollinger_bands(df)
                if df is None or "BB_Upper" not in df.columns:
                    continue

                close_price = float(df.iloc[-1]["close"])

                # 배당주는 장기 보유 - 극단적 상황에서만 매도
                # 1. 급격한 하락 (20% 이상) - 펀더멘털 문제 가능성
                if len(df) >= 20:
                    price_20d_ago = float(df.iloc[-20]["close"])
                    if price_20d_ago > 0:
                        drop_ratio = (price_20d_ago - close_price) / price_20d_ago
                        if drop_ratio >= 0.20:
                            # 급락 시 일부 정리 (손실 확대 방지)
                            sell_vol = max(1, int(hldg_qty * 0.3))
                            sell_price = round(close_price * 1.002, 2) if country == "USA" else int(close_price * 1.002)
                            sell_levels.setdefault(symbol, {})[sell_price] = sell_vol
                            logger.info(f"배당주 {symbol} 급락({drop_ratio:.1%}) - 일부 정리")

            except Exception as e:
                logger.error(f"DividendStrategy.filter_for_sell 처리 중 에러: {symbol} -> {e}")
                continue

        return sell_levels
