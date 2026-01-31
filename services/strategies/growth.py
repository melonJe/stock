"""성장주 전략 - 추세 추종 매매

특징:
- Drawdown 15-35% 범위에서 진입
- 52주 신고가 대비 조정폭 활용
- 브레이크아웃 + 거래량 급증 조건
- VIX 기반 매수 중단
"""
from typing import List, Union

import pandas as pd

from config.logging_config import get_logger
from config.strategy_config import GROWTH_CONFIG
from data.dto.account_dto import StockResponseDTO
from data.models import Subscription
from services.strategies.base import BaseStrategy
from services.trading_helpers import (
    allocate_volume_to_levels,
    apply_bollinger_bands,
    calculate_atr,
    calculate_adtv,
    calculate_position_volume,
    fetch_price_dataframe,
    generate_dca_entry_levels,
    has_min_rows,
    is_same_anchor_date,
    macd_rebound_ok,
    meets_liquidity_threshold,
    normalize_dataframe_for_country,
    prepare_buy_context,
    rsi_in_range,
    add_prev_close_allocation,
)
from services.market_condition import (
    is_buy_allowed,
    get_position_size_adjusted,
    get_sell_ratio_adjusted,
    check_52week_high_drawdown,
    check_breakout_with_volume,
)
from services.data_handler import get_country_by_symbol

logger = get_logger(__name__)


class GrowthStrategy(BaseStrategy):
    """성장주 전략 (추세 추종)"""

    def filter_for_buy(self, country: str = "KOR") -> dict[str, dict[float, int]]:
        """성장주 매수 대상 필터링"""
        # VIX 체크
        buy_allowed, vix = is_buy_allowed()
        if not buy_allowed:
            logger.info(f"VIX {vix:.2f} >= 30, 성장주 매수 중단")
            return {}
        
        anchor_date, risk_amount_value, risk_k, adtv_limit_ratio, stocks, usd_krw = prepare_buy_context(country, "growth")
        buy_levels: dict[str, dict[float, int]] = {}

        for symbol in stocks:
            try:
                df = fetch_price_dataframe(symbol)
                if df is None or df.empty:
                    continue
                df = normalize_dataframe_for_country(df, country)

                if not is_same_anchor_date(df, anchor_date):
                    continue

                if not has_min_rows(df, GROWTH_CONFIG.min_data_rows):
                    continue

                adtv = calculate_adtv(df)
                if not meets_liquidity_threshold(adtv, country, usd_krw):
                    continue

                # SMA 추세 확인 (완화: 둘 중 하나만 상승해도 OK)
                sma60 = df['close'].rolling(window=60).mean()
                sma120 = df['close'].rolling(window=120).mean()
                if pd.isna(sma60.iloc[-1]) or pd.isna(sma120.iloc[-1]):
                    continue
                
                sma60_rising = sma60.iloc[-1] > sma60.iloc[-5] if len(sma60) >= 5 else False
                sma120_rising = sma120.iloc[-1] > sma120.iloc[-5] if len(sma120) >= 5 else False
                if not (sma60_rising or sma120_rising):
                    continue

                # 52주 신고가 대비 조정폭 (15-35%)
                if GROWTH_CONFIG.use_52week_high:
                    if not check_52week_high_drawdown(df, GROWTH_CONFIG.drawdown_min, GROWTH_CONFIG.drawdown_max):
                        # fallback: 120일 기준
                        recent_peak = df['close'].rolling(window=120).max().iloc[-2]
                        if pd.isna(recent_peak) or recent_peak <= 0:
                            continue
                        drawdown = (recent_peak - float(df.iloc[-1]['close'])) / recent_peak
                        if not (GROWTH_CONFIG.drawdown_min <= drawdown <= GROWTH_CONFIG.drawdown_max):
                            continue

                # RSI 범위 확대 (30-60)
                if not rsi_in_range(df, window=7, lower=GROWTH_CONFIG.rsi_lower, upper=GROWTH_CONFIG.rsi_upper):
                    continue

                if not macd_rebound_ok(df):
                    continue

                # 브레이크아웃 + 거래량 급증 조건
                if not check_breakout_with_volume(df, 
                        lookback=GROWTH_CONFIG.breakout_lookback, 
                        volume_mult=GROWTH_CONFIG.breakout_volume_mult):
                    # 기존 거래량 조건으로 fallback
                    vol = df['volume']
                    v20 = vol.rolling(window=20).mean()
                    recent_vol = vol.iloc[-3:]
                    recent_v20 = v20.iloc[-3:]
                    if recent_vol.isna().any() or recent_v20.isna().any():
                        continue
                    if not ((recent_vol > 1.2 * recent_v20).any()):
                        continue

                df = apply_bollinger_bands(df)

                atr = calculate_atr(df)
                if atr is None:
                    continue

                close_price = float(df.iloc[-1]['close'])
                volume_shares = calculate_position_volume(
                    atr=atr,
                    adtv=adtv,
                    close_price=close_price,
                    risk_amount_value=risk_amount_value,
                    risk_k=risk_k,
                    adtv_limit_ratio=adtv_limit_ratio,
                )
                if volume_shares <= 0:
                    continue

                # 시장 상황 기반 포지션 조정
                volume_shares = get_position_size_adjusted(volume_shares, country)
                
                # 종목당 최대 비중 체크
                volume_shares = self._apply_max_position_weight(volume_shares, close_price, risk_amount_value)

                price_levels = generate_dca_entry_levels(df, atr)
                if not price_levels:
                    continue

                levels = allocate_volume_to_levels(price_levels, total_volume=volume_shares)
                if not levels:
                    continue

                buy_levels[symbol] = add_prev_close_allocation(levels, df, volume_shares)
            except Exception as e:
                logger.error(f"GrowthStrategy.filter_for_buy 처리 중 에러: {symbol} -> {e}")
        return buy_levels
    
    def filter_for_sell(
            self,
            stocks_held: Union[List[StockResponseDTO], StockResponseDTO, None]
    ) -> dict[str, dict[float, int]]:
        """성장주 매도 대상 필터링"""
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

            if symbol not in growth_symbols:
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

                if not has_min_rows(df, GROWTH_CONFIG.min_data_rows):
                    continue

                df = apply_bollinger_bands(df)
                close_price = float(df.iloc[-1]["close"])

                sma60 = df['close'].rolling(window=60).mean()
                sma120 = df['close'].rolling(window=120).mean()

                if pd.isna(sma60.iloc[-1]) or pd.isna(sma120.iloc[-1]):
                    continue

                # 추세 이탈 시 매도 (VIX 기반 비율 조정)
                if close_price < float(sma120.iloc[-1]):
                    base_ratio = GROWTH_CONFIG.sell_ratio_trend_break
                    adjusted_ratio = get_sell_ratio_adjusted(base_ratio)
                    sell_vol = max(1, int(hldg_qty * adjusted_ratio))
                    sell_price = round(close_price * 0.995, 2) if country == "USA" else int(close_price * 0.995)
                    sell_levels.setdefault(symbol, {})[sell_price] = sell_vol
                    logger.info(f"성장주 {symbol} 추세이탈 - 매도비율 {adjusted_ratio:.1%}")
                    continue

                # 볼린저 밴드 상단 돌파 후 반락 시
                bb_upper = float(df["BB_Upper"].iloc[-1])
                if close_price >= bb_upper * 0.98:
                    atr = calculate_atr(df)
                    if atr and atr > 0:
                        base_ratio = 0.3
                        adjusted_ratio = get_sell_ratio_adjusted(base_ratio)
                        sell_vol = max(1, int(hldg_qty * adjusted_ratio))
                        sell_price = round(bb_upper * 1.01, 2) if country == "USA" else int(bb_upper * 1.01)
                        sell_levels.setdefault(symbol, {})[sell_price] = sell_vol

            except Exception as e:
                logger.error(f"GrowthStrategy.filter_for_sell 처리 중 에러: {symbol} -> {e}")
                continue

        return sell_levels
