import datetime
import logging
import threading
from time import sleep
from typing import List, Union

import numpy as np
import pandas as pd

from apis.korea_investment import KoreaInvestmentAPI
from config import setting_env
from data.dto.account_dto import StockResponseDTO
from data.models import Subscription
from services.data_handler import get_country_by_symbol, add_stock_price
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
    rsi_in_range,
    rsi_rebound_below,
    add_prev_close_allocation,
)
from utils import discord
from utils.operations import price_refine


def select_buy_stocks(country: str = "KOR") -> dict[str, dict[float, int]]:
    buy_levels = {}
    for d in [
        filter_stable_for_buy(country=country),
        filter_trend_for_buy(country=country),
        filter_box_for_buy(country=country),
    ]:
        for sym, price_dict in d.items():
            for price, qty in price_dict.items():
                buy_levels.setdefault(sym, {})
                buy_levels[sym][price] = buy_levels[sym].get(price, 0) + qty
    return buy_levels


def select_sell_stocks(stocks_held: Union[List[StockResponseDTO], StockResponseDTO, None]) -> dict[str, dict[float, int]]:
    sell_levels = {}
    for d in [
        filter_stable_for_sell(stocks_held),
        filter_trend_for_sell(stocks_held),
        filter_box_for_sell(stocks_held),
        filter_non_subscription_for_sell(stocks_held),
    ]:
        for sym, price_dict in d.items():
            for price, qty in price_dict.items():
                sell_levels.setdefault(sym, {})
                sell_levels[sym][price] = sell_levels[sym].get(price, 0) + qty

    if not stocks_held or not sell_levels:
        return sell_levels
    holdings = stocks_held if isinstance(stocks_held, list) else [stocks_held]
    limits: dict[str, int] = {}
    for stock in holdings:
        try:
            symbol = stock.pdno
        except Exception:
            continue

        try:
            hldg_qty = int(float(getattr(stock, "hldg_qty", 0) or 0))
        except (TypeError, ValueError):
            hldg_qty = 0

        try:
            ord_psbl_qty = int(float(getattr(stock, "ord_psbl_qty", 0) or 0))
        except (TypeError, ValueError):
            ord_psbl_qty = 0

        limit = ord_psbl_qty if ord_psbl_qty > 0 else hldg_qty
        if limit > 0:
            limits[symbol] = limit

    for symbol, levels in list(sell_levels.items()):
        limit = limits.get(symbol)
        if not limit:
            continue

        price_volume_items = [(price, int(volume)) for price, volume in levels.items() if int(volume) > 0]
        if not price_volume_items:
            sell_levels.pop(symbol, None)
            continue

        total_volume = sum(volume for _, volume in price_volume_items)
        if total_volume <= limit:
            continue

        scale_factor = limit / total_volume if total_volume else 0
        scaled_levels: dict[float, int] = {}
        fractional_remainders: list[tuple[float, float]] = []
        for price, volume in price_volume_items:
            scaled_raw = volume * scale_factor
            scaled_base = int(scaled_raw)
            if scaled_base > 0:
                scaled_levels[price] = scaled_base
                fractional_remainders.append((price, scaled_raw - scaled_base))
            else:
                scaled_levels[price] = 0
                fractional_remainders.append((price, scaled_raw))

        current_total = sum(scaled_levels.values())
        remaining = limit - current_total
        if remaining > 0:
            fractional_remainders.sort(key=lambda x: x[1], reverse=True)
            idx = 0
            n = len(fractional_remainders)
            while remaining > 0 and n > 0:
                price, _ = fractional_remainders[idx % n]
                scaled_levels[price] = scaled_levels.get(price, 0) + 1
                remaining -= 1
                idx += 1

        sell_levels[symbol] = {price: volume for price, volume in scaled_levels.items() if volume > 0}
    return sell_levels


def filter_non_subscription_for_sell(
        stocks_held: Union[List[StockResponseDTO], StockResponseDTO, None]
) -> dict[str, dict[float, int]]:
    """구독하지 않은 보유 종목을 전일 종가로 전량 매도 대상으로 반환한다."""
    sell_levels: dict[str, dict[float, int]] = {}
    if not stocks_held:
        return sell_levels

    holdings = stocks_held if isinstance(stocks_held, list) else [stocks_held]
    subscribed_symbols = {row.symbol for row in Subscription.select(Subscription.symbol)}

    for stock in holdings:
        try:
            symbol = stock.pdno
        except Exception:
            continue

        if symbol in subscribed_symbols:
            continue

        try:
            qty = max(0, int(float(getattr(stock, "hldg_qty", 0))))
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue

        try:
            df = fetch_price_dataframe(symbol)
            if df is None or df.empty or len(df) < 2:
                continue
            symbol_country = get_country_by_symbol(symbol)
            df = normalize_dataframe_for_country(df, symbol_country)
            if len(df) < 2:
                continue
            prev_close = float(df["close"].iloc[-2])
        except Exception as e:
            logging.error(f"filter_non_subscription_for_sell 처리 중 에러: {symbol} -> {e}")
            continue

        if prev_close <= 0:
            continue

        if symbol_country == "KOR":
            price_key = price_refine(int(round(prev_close)))
        else:
            price_key = round(prev_close, 2)

        sell_levels.setdefault(symbol, {})
        sell_levels[symbol][price_key] = sell_levels[symbol].get(price_key, 0) + qty

    return sell_levels


def filter_trend_for_buy(country: str = "KOR") -> dict[str, dict[float, int]]:
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

            if not has_min_rows(df, 150):
                continue

            adtv = calculate_adtv(df)
            if not meets_liquidity_threshold(adtv, country, usd_krw):
                continue

            sma60 = df['close'].rolling(window=60).mean()
            sma120 = df['close'].rolling(window=120).mean()
            if pd.isna(sma60.iloc[-1]) or pd.isna(sma60.iloc[-2]) or pd.isna(sma120.iloc[-1]) or pd.isna(sma120.iloc[-2]):
                continue
            if not (sma60.iloc[-1] > sma60.iloc[-2] and sma120.iloc[-1] > sma120.iloc[-2]):
                continue
            if not (float(df.iloc[-1]['close']) > float(sma120.iloc[-1])):
                continue

            recent_window = 120
            recent_peak = df['close'].rolling(window=recent_window).max().iloc[-2]
            if pd.isna(recent_peak) or recent_peak <= 0:
                continue
            drawdown = (recent_peak - float(df.iloc[-1]['close'])) / recent_peak
            if not (0.10 <= drawdown <= 0.20):
                continue

            if not rsi_in_range(df, window=7, lower=30, upper=50):
                continue

            if not macd_rebound_ok(df):
                continue

            vol = df['volume']
            v20 = vol.rolling(window=20).mean()
            v5 = vol.rolling(window=5).mean()
            if pd.isna(v20.iloc[-1]) or pd.isna(v5.iloc[-1]):
                continue

            if not (float(v5.iloc[-1]) < 0.7 * float(v20.iloc[-1])):
                continue

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

            price_levels = generate_dca_entry_levels(df, atr)
            if not price_levels:
                continue

            levels = allocate_volume_to_levels(price_levels, total_volume=volume_shares)
            if not levels:
                continue

            buy_levels[symbol] = add_prev_close_allocation(levels, df, volume_shares)
        except Exception as e:
            logging.error(f"filter_trend_for_buy 처리 중 에러: {symbol} -> {e}")
    return buy_levels


def filter_trend_for_sell(
        stocks_held: Union[List[StockResponseDTO], StockResponseDTO, None]
) -> dict[str, dict[float, int]]:
    sell_levels: dict[str, dict[float, int]] = {}
    if not stocks_held:
        return sell_levels

    holdings = stocks_held if isinstance(stocks_held, list) else [stocks_held]
    growth_symbols = {
        row.symbol
        for row in Subscription.select(Subscription.symbol).where(Subscription.category == "growth")
    }

    for stock in holdings:
        try:
            symbol = stock.pdno
        except Exception:
            continue

        if symbol not in growth_symbols:
            continue

        try:
            qty = max(0, int(float(getattr(stock, "hldg_qty", 0))))
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue

        try:
            entry_price = float(stock.pchs_avg_pric)
        except (TypeError, ValueError):
            entry_price = None

        try:
            df = fetch_price_dataframe(symbol)
            if df is None or df.empty:
                continue

            symbol_country = get_country_by_symbol(symbol)
            df = normalize_dataframe_for_country(df, symbol_country)
            if len(df) < 150:
                continue

            closes = df["close"].astype(float)
            highs = df["high"].astype(float)
            if len(closes) < 2:
                continue

            close = float(closes.iloc[-1])
            prev_close = float(closes.iloc[-2])

            sma60 = closes.rolling(60).mean()
            sma120 = closes.rolling(120).mean()
            atr = calculate_atr(df)

            sell_plan: dict[float, int] = {}

            # ATR 기반 손절/익절
            if atr is not None and atr > 0 and entry_price and entry_price > 0:
                risk_per_share = float(atr)
                stop_price = max(entry_price - 1.0 * risk_per_share, 0)
                target_price = entry_price + 2.0 * risk_per_share

                if close <= stop_price * 1.01:
                    sell_plan[stop_price] = sell_plan.get(stop_price, 0) + max(1, int(qty * 0.3))
                if close >= (entry_price + risk_per_share):
                    sell_plan[target_price] = sell_plan.get(target_price, 0) + max(1, int(qty * 0.1))

            # 추세 이탈(SMA 하락 전환 또는 120SMA 하회)
            try:
                trend_break = False
                if len(sma120) >= 1 and not pd.isna(sma120.iloc[-1]):
                    trend_break = bool(close < float(sma120.iloc[-1]))
                if len(sma60) >= 2 and len(sma120) >= 2:
                    if not any(pd.isna([sma60.iloc[-1], sma60.iloc[-2], sma120.iloc[-1], sma120.iloc[-2]])):
                        trend_break = trend_break or (
                            float(sma60.iloc[-1]) < float(sma60.iloc[-2])
                            and float(sma120.iloc[-1]) < float(sma120.iloc[-2])
                        )
                if trend_break:
                    exit_price = min(prev_close, close) * 0.995
                    sell_plan[exit_price] = sell_plan.get(exit_price, 0) + max(1, int(qty * 0.2))
            except Exception:
                pass

            # 트레일링 스탑(전일 기준 최고가 대비 하락)
            try:
                if len(closes) >= 5 and len(highs) >= 5:
                    rolling_window = 60
                    rolling_max_close = closes.iloc[:-1].rolling(rolling_window, min_periods=5).max().iloc[-1]
                    rolling_max_high = highs.iloc[:-1].rolling(rolling_window, min_periods=5).max().iloc[-1]
                    if not pd.isna(rolling_max_close) and not pd.isna(rolling_max_high):
                        base_max = max(float(rolling_max_close), float(rolling_max_high))
                        trailing_stop = base_max * (1.0 - 0.10)
                        if close <= trailing_stop * 1.01:
                            sell_plan[trailing_stop] = sell_plan.get(trailing_stop, 0) + max(1, int(qty * 0.1))
            except Exception:
                pass

            # 수량 스케일링(보유수량 초과 방지)
            total_planned = sum(sell_plan.values())
            if total_planned > qty and total_planned > 0:
                scale = qty / total_planned
                scaled_plan: dict[float, int] = {}
                for price, vol in sell_plan.items():
                    scaled_vol = int(vol * scale)
                    if scaled_vol > 0:
                        scaled_plan[price] = scaled_vol
                sell_plan = scaled_plan

            sell_plan = {p: q for p, q in sell_plan.items() if q > 0}
            if not sell_plan:
                continue

            for raw_price, vol in sell_plan.items():
                if vol <= 0:
                    continue
                if symbol_country == "KOR":
                    price_key = price_refine(int(round(raw_price)))
                else:
                    price_key = round(raw_price, 2)
                sell_levels.setdefault(symbol, {})
                sell_levels[symbol][price_key] = sell_levels[symbol].get(price_key, 0) + vol

        except Exception as e:
            logging.error(f"filter_trend_for_sell 처리 중 에러: {symbol} -> {e}")
            continue

    return sell_levels


def filter_stable_for_buy(country: str = "KOR") -> dict[str, dict[float, int]]:
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
            logging.error(f"filter_stable_for_buy 처리 중 에러: {symbol} -> {e}")
    return buy_levels


def filter_stable_for_sell(
        stocks_held: Union[List[StockResponseDTO], StockResponseDTO, None]
        ) -> dict[str, dict[float, int]]:
    sell_levels: dict[str, dict[float, int]] = {}
    if not stocks_held:
        return sell_levels

    holdings = stocks_held if isinstance(stocks_held, list) else [stocks_held]
    growth_query = (
        Subscription
        .select(Subscription.symbol)
        .where(Subscription.category == "growth")
    )

    dividend_symbols = {
        row.symbol
        for row in (
            Subscription
            .select(Subscription.symbol)
            .where(Subscription.category == "dividend")
            .where(Subscription.symbol.not_in(growth_query))
        )
    }
    for stock in holdings:
        try:
            symbol = stock.pdno
        except Exception:
            continue
        if symbol not in dividend_symbols:
            continue

        try:
            qty = max(0, int(float(getattr(stock, "hldg_qty", 0))))
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue

        try:
            df = fetch_price_dataframe(symbol)
            if df is None or df.empty:
                continue

            symbol_country = get_country_by_symbol(symbol)
            df = normalize_dataframe_for_country(df, symbol_country)
            if len(df) < 30:
                continue

            # 기본: 일봉 기준 트레일링 스탑 (전일까지의 rolling max)
            closes = df["close"].astype(float)
            highs = df["high"].astype(float)
            if len(closes) < 5:
                continue

            rolling_window = 60
            prev_closes = closes.iloc[:-1]
            prev_highs = highs.iloc[:-1]
            rolling_max_close = prev_closes.rolling(window=rolling_window, min_periods=5).max().iloc[-1]
            rolling_max_high = prev_highs.rolling(window=rolling_window, min_periods=5).max().iloc[-1]

            if pd.isna(rolling_max_close) or pd.isna(rolling_max_high):
                continue

            trailing_drop_pct = 0.08
            base_max = max(float(rolling_max_close), float(rolling_max_high))
            trailing_stop = base_max * (1.0 - trailing_drop_pct)

            atr = calculate_atr(df)
            atr_target_price = None
            try:
                entry_price = float(stock.pchs_avg_pric)
            except (TypeError, ValueError):
                entry_price = None

            if atr is not None and entry_price and entry_price > 0:
                r_multiple_target = 2.0
                risk_per_share = float(atr)
                atr_target_price = entry_price + r_multiple_target * risk_per_share

            sell_plan: dict[float, int] = {}

            # 트레일링 스탑: 조건 만족 시에만 예약
            if close := float(closes.iloc[-1]) <= trailing_stop * 1.01:
                sell_plan[trailing_stop] = sell_plan.get(trailing_stop, 0) + max(1, int(qty * 0.2))

            # ATR 타겟: 현재가가 1R 이상 상승했을 때만 예약
            if atr_target_price and atr_target_price > 0 and float(closes.iloc[-1]) >= (entry_price + risk_per_share):
                sell_plan[atr_target_price] = sell_plan.get(atr_target_price, 0) + max(1, int(qty * 0.1))

            if not sell_plan:
                continue

            # 총 계획 수량이 보유 수량을 넘지 않도록 조정
            total_planned = sum(sell_plan.values())
            if total_planned > qty and total_planned > 0:
                scale = qty / total_planned
                scaled_plan: dict[float, int] = {}
                for price, vol in sell_plan.items():
                    scaled_vol = int(vol * scale)
                    if scaled_vol > 0:
                        scaled_plan[price] = scaled_vol
                sell_plan = scaled_plan

            for raw_price, vol in sell_plan.items():
                if vol <= 0:
                    continue
                if symbol_country == "KOR":
                    price_key = price_refine(int(round(raw_price)))
                else:
                    price_key = round(raw_price, 2)
                sell_levels.setdefault(symbol, {})
                sell_levels[symbol][price_key] = sell_levels[symbol].get(price_key, 0) + vol

        except Exception as e:
            logging.error(f"filter_stable_for_sell 처리 중 에러: {symbol} -> {e}")
            continue
    return sell_levels


def filter_box_for_buy(country: str = "KOR") -> dict[str, dict[float, int]]:
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
            logging.error(f"filter_box_for_buy 처리 중 에러: {symbol} -> {e}")
    return buy_levels


def filter_box_for_sell(
        stocks_held: Union[List[StockResponseDTO], StockResponseDTO, None]
) -> dict[str, dict[float, int]]:
    sell_levels: dict[str, dict[float, int]] = {}
    if not stocks_held:
        return sell_levels

    holdings = stocks_held if isinstance(stocks_held, list) else [stocks_held]
    growth_query = (
        Subscription
        .select(Subscription.symbol)
        .where(Subscription.category == "growth")
    )

    box_symbols = {
        row.symbol
        for row in (
            Subscription
            .select(Subscription.symbol)
            .where(Subscription.category == "box")
            .where(Subscription.symbol.not_in(growth_query))
        )
    }

    for stock in holdings:
        try:
            symbol = stock.pdno
            if symbol not in box_symbols:
                continue

            try:
                qty = max(0, int(float(stock.hldg_qty)))
            except (TypeError, ValueError):
                continue
            if qty <= 0:
                continue

            symbol_country = get_country_by_symbol(symbol)

            df = fetch_price_dataframe(symbol)
            if df is None or df.empty:
                continue
            if len(df) < 120:
                continue

            df = normalize_dataframe_for_country(df, symbol_country)
            df = apply_bollinger_bands(df)

            if len(df) < 2:
                continue

            try:
                bb_upper = float(df["BB_Upper"].iloc[-1])
                bb_lower = float(df["BB_Lower"].iloc[-1])
                bb_mavg = float(df["BB_Mavg"].iloc[-1])
                close_price = float(df.iloc[-1]["close"])
                prev_close = float(df.iloc[-2]["close"])
            except (TypeError, ValueError):
                continue

            if any(np.isnan(x) or x <= 0 for x in (bb_upper, bb_lower, bb_mavg, close_price, prev_close)):
                continue

            width_ratio = float((bb_upper - bb_lower) / bb_mavg) if bb_mavg else np.inf
            sma20 = df["close"].rolling(window=20).mean()
            slope_ratio = np.inf
            if len(sma20) >= 11 and not pd.isna(sma20.iloc[-1]) and not pd.isna(sma20.iloc[-11]):
                try:
                    slope_ratio = abs(float(sma20.iloc[-1]) / float(sma20.iloc[-11]) - 1.0)
                except (TypeError, ValueError):
                    slope_ratio = np.inf

            # 박스 범위 계산: Bollinger 상단/하단을 박스 상·하단으로 사용
            low_box = bb_lower
            high_box = bb_upper
            box_range = high_box - low_box
            if box_range <= 0:
                continue

            # 박스 이탈 여부 (기존 조건 유지)
            box_break = (
                    width_ratio < 0.05
                    or width_ratio > 0.22
                    or slope_ratio > 0.06
                    or close_price > high_box * 1.01
                    or close_price < low_box * 0.99
            )

            # 기본 출구 2-1: 박스 높이 비율 익절/손절
            # 예시: 박스 70% 지점에서 익절, 로우 박스 하회 시 손절
            take_profit_ratio = 0.7
            tp_price = low_box + box_range * take_profit_ratio
            stop_price = low_box * 0.99

            sell_plan: dict[float, int] = {}

            if box_break:
                # 박스가 깨지면 보수적으로 일부 수량 정리 (예: 20%)
                break_qty = max(1, int(qty * 0.2))
                # 이탈 방향과 무관하게 직전 종가 기준으로 예약
                base_price = prev_close if prev_close > 0 else close_price
                sell_plan[base_price] = break_qty
            else:
                # 박스 내부: 박스 비율 기반 익절/손절
                tp_qty = max(1, int(qty * 0.1))
                stop_qty = max(1, int(qty * 0.1))
                sell_plan[tp_price] = tp_qty
                sell_plan[stop_price] = sell_plan.get(stop_price, 0) + stop_qty

            # VWAP/POC 기반 분할 매도 (최근 구간으로 제한, 박스 내부에서만 적용)
            vwap_price = None
            if not box_break:
                try:
                    df_tail = df.tail(60)
                    if "volume" in df_tail.columns and not df_tail["volume"].isna().all() and len(df_tail) >= 5:
                        vol = df_tail["volume"].astype(float)
                        typical_price = (df_tail["high"].astype(float) + df_tail["low"].astype(float) + df_tail["close"].astype(float)) / 3.0
                        vwap_series = (typical_price * vol).cumsum() / vol.cumsum()
                        vwap_price = float(vwap_series.iloc[-1])
                except Exception:
                    vwap_price = None

                if vwap_price and vwap_price > 0:
                    vwap_qty = max(1, int(qty * 0.1))
                    upper_qty = max(1, int(qty * 0.1))
                    sell_plan[vwap_price] = sell_plan.get(vwap_price, 0) + vwap_qty
                    sell_plan[high_box * 0.98] = sell_plan.get(high_box * 0.98, 0) + upper_qty

            # 총 계획 수량이 보유 수량을 넘지 않도록 스케일 조정
            total_planned = sum(sell_plan.values())
            if total_planned > qty and total_planned > 0:
                scale = qty / total_planned
                for k in list(sell_plan.keys()):
                    scaled = int(sell_plan[k] * scale)
                    sell_plan[k] = max(0, scaled)

            # 0 이상인 주문만 반영
            sell_plan = {p: q for p, q in sell_plan.items() if q > 0}
            if not sell_plan:
                continue

            for raw_price, vol in sell_plan.items():
                if vol <= 0:
                    continue
                if symbol_country == "KOR":
                    price_key = price_refine(int(round(raw_price)))
                else:
                    price_key = round(raw_price, 2)
                sell_levels.setdefault(symbol, {})
                sell_levels[symbol][price_key] = sell_levels[symbol].get(price_key, 0) + vol

        except Exception as exc:
            logging.error(f"filter_box_for_sell error: %s -> %s", getattr(stock, "pdno", "unknown"), exc)
            continue

    return sell_levels


def trading_buy(korea_investment: KoreaInvestmentAPI, buy_levels):
    """Submit buy orders for calculated levels with ATR-based stop-loss preset."""
    try:
        end_date = korea_investment.get_nth_open_day(3)
    except Exception as e:
        logging.critical(f"trading_buy 오픈일 조회 실패: {e}")
        return

    money = 0

    for symbol, levels in buy_levels.items():
        try:
            country = get_country_by_symbol(symbol)
            stock = korea_investment.get_owned_stock_info(symbol=symbol)
            for price, volume in levels.items():
                if stock and price > float(stock.pchs_avg_pric) * 0.975:
                    continue
                if not volume:
                    continue
                try:
                    if country == "KOR":
                        price = price_refine(price)
                        korea_investment.buy_reserve(symbol=symbol, price=price, volume=volume, end_date=end_date)
                        money += price * volume
                    elif country == "USA":
                        korea_investment.submit_overseas_reservation_order(country=country, action="buy", symbol=symbol, price=str(round(price, 2)), volume=str(volume))
                        money += price * volume

                except Exception as e:
                    logging.critical(f"trading_buy 주문 실패: {symbol} -> {e}")
        except Exception as e:
            logging.error(f"trading_buy 처리 중 에러: {symbol} -> {e}")

    if money:
        try:
            discord.send_message(f'총 액 : {money}')
        except Exception as e:
            logging.error(f"trading_buy 디스코드 전송 실패: {e}")


def trading_sell(korea_investment: KoreaInvestmentAPI, sell_levels):
    """Place sell orders for stocks present in the queue."""
    try:
        end_date = korea_investment.get_nth_open_day(1)
    except Exception as e:
        logging.critical(f"trading_sell 오픈일 조회 실패: {e}")
        return

    for symbol, levels in (sell_levels or {}).items():
        try:
            country = get_country_by_symbol(symbol)
            stock = korea_investment.get_owned_stock_info(symbol=symbol)
            if not stock:
                continue

            try:
                available = int(float(getattr(stock, "ord_psbl_qty", 0) or 0))
            except (TypeError, ValueError):
                available = 0

            if available <= 0:
                logging.debug(f"trading_sell 스킵: {symbol} - 주문가능수량 없음")
                continue

            for price, volume in levels.items():
                try:
                    volume = int(volume)
                except (TypeError, ValueError):
                    continue
                if volume <= 0 or available <= 0:
                    continue
                if volume > available:
                    volume = available
                available -= volume

                try:
                    if country == "KOR":
                        if price < float(stock.pchs_avg_pric):
                            price = price_refine(int(float(stock.pchs_avg_pric) * 1.002), 1)
                        korea_investment.sell_reserve(symbol=symbol, price=int(price), volume=volume, end_date=end_date)
                    elif country == "USA":
                        if price < float(stock.pchs_avg_pric):
                            price = round(float(stock.pchs_avg_pric) * 1.005, 2)
                        korea_investment.submit_overseas_reservation_order(country=country, action="sell", symbol=symbol, price=str(round(float(price), 2)), volume=str(volume))
                except Exception as e:
                    logging.critical(f"trading_sell 주문 실패: {symbol} -> {e}")
        except Exception as e:
            logging.error(f"trading_sell 처리 중 에러: {symbol} -> {e}")


def buy_etf_group_stocks():
    """ETF 관심종목 그룹에 포함된 종목을 1주씩 매수한다."""
    ki_api = KoreaInvestmentAPI(
        app_key=setting_env.APP_KEY_ETF,
        app_secret=setting_env.APP_SECRET_ETF,
        account_number=setting_env.ACCOUNT_NUMBER_ETF,
        account_code=setting_env.ACCOUNT_CODE_ETF,
    )
    today = datetime.datetime.now().strftime("%Y%m%d")
    holidays = ki_api.get_domestic_market_holidays(today)
    holiday = holidays.get(today)
    if holiday and holiday.opnd_yn == "N":
        logging.info("ETF 그룹 매수 스킵: 휴장일")
        return

    group_list = ki_api.get_interest_group_list(user_id=setting_env.HTS_ID_ETF)
    if not group_list or not group_list.output2:
        logging.warning("ETF 그룹 매수 스킵: 관심종목 그룹 없음")
        return

    etf_groups = [
        item for item in group_list.output2
        if "ETF" in (item.inter_grp_name or "").upper()
    ]
    if not etf_groups:
        logging.warning("ETF 그룹 매수 스킵: ETF 그룹 미존재")
        return

    symbols = set()
    for group in etf_groups:
        detail = ki_api.get_interest_group_stocks(
            user_id=setting_env.HTS_ID_ETF,
            inter_grp_code=group.inter_grp_code,
        )
        if not detail or not detail.output2:
            continue
        for item in detail.output2:
            if item.jong_code:
                symbols.add(item.jong_code)

    if not symbols:
        logging.warning("ETF 그룹 매수 스킵: 매수 대상 없음")
        return

    for symbol in sorted(symbols):
        try:
            ki_api.buy(symbol=symbol, price=0, volume=1, order_type="03")
        except Exception as e:
            logging.critical(f"ETF 그룹 매수 실패: {symbol} - {e}")


def korea_trading():
    """Main entry to run daily domestic trading tasks."""
    ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY_KOR, app_secret=setting_env.APP_SECRET_KOR, account_number=setting_env.ACCOUNT_NUMBER_KOR, account_code=setting_env.ACCOUNT_CODE_KOR)
    if ki_api.check_holiday(datetime.datetime.now().strftime("%Y%m%d")):
        logging.info(f'{datetime.datetime.now()} 휴장일')
        return

    while datetime.datetime.now().time() < datetime.time(18, 15, 00):
        sleep(1 * 60)

    add_stock_price(country="KOR", start_date=datetime.datetime.now() - datetime.timedelta(days=5), end_date=datetime.datetime.now())

    stocks_held = ki_api.get_owned_stock_info()
    sell_queue = select_sell_stocks(stocks_held)
    sell = threading.Thread(target=trading_sell, args=(ki_api, sell_queue,))
    sell.start()

    buy_stock = select_buy_stocks(country="KOR")
    buy = threading.Thread(target=trading_buy, args=(ki_api, buy_stock,))
    buy.start()


def usa_trading():
    """Execute U.S. market trading workflow."""
    ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY_USA, app_secret=setting_env.APP_SECRET_USA, account_number=setting_env.ACCOUNT_NUMBER_USA, account_code=setting_env.ACCOUNT_CODE_USA)
    usa_stock = select_buy_stocks(country="USA")
    usa_buy = threading.Thread(target=trading_buy, args=(ki_api, usa_stock,))
    usa_buy.start()

    stocks_held = ki_api.get_owned_stock_info()
    sell_queue = select_sell_stocks(stocks_held)
    sell = threading.Thread(target=trading_sell, args=(ki_api, sell_queue,))
    sell.start()


if __name__ == "__main__":
    ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY_USA, app_secret=setting_env.APP_SECRET_USA, account_number=setting_env.ACCOUNT_NUMBER_USA, account_code=setting_env.ACCOUNT_CODE_USA)
    stocks_held = ki_api.get_owned_stock_info()
    sell_queue = select_sell_stocks(stocks_held)
    sell = threading.Thread(target=trading_sell, args=(ki_api, sell_queue,))
    sell.start()
