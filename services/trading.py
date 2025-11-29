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
    ]:
        for sym, price_dict in d.items():
            for price, qty in price_dict.items():
                sell_levels.setdefault(sym, {})
                sell_levels[sym][price] = sell_levels[sym].get(price, 0) + qty
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
            logging.error(f"filter_trend_pullback_reversal Error occurred: {e}")
    return buy_levels


def filter_trend_for_sell(stocks_held: list[StockResponseDTO] | StockResponseDTO | None, country: str = "KOR") -> dict[str, dict[float, int]]:
    sell_levels = {}
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
            logging.error(f"select_buy_stocks Error occurred: {e}")
    return buy_levels


def filter_stable_for_sell(stocks_held: Union[List[StockResponseDTO], StockResponseDTO, None], country: str = "KOR") -> dict[str, dict[float, int]]:
    sell_levels = {}
    growth_query = (
        Subscription
        .select(Subscription.symbol)
        .where(Subscription.category == "growth")
    )

    growth_symbols = {
        row.symbol
        for row in (
            Subscription
            .select(Subscription.symbol)
            .where(Subscription.category == "dividend")
            .where(Subscription.symbol.not_in(growth_query))
        )
    }
    for stock in (stocks_held or {}):
        symbol = stock.pdno
        if symbol in growth_symbols:
            continue
        try:
            qty = max(0, int(float(stock.hldg_qty)))
        except (TypeError, ValueError):
            continue
        try:
            if qty <= 0:
                continue

            df = fetch_price_dataframe(symbol)
            if df is None or df.empty:
                continue

            country_code = get_country_by_symbol(symbol)
            df = normalize_dataframe_for_country(df, country_code)
            if len(df) < 30:
                continue

            # 기본: 일봉 기준 트레일링 스탑 (전일까지의 rolling max)
            closes = df["close"].astype(float)
            highs = df["high"].astype(float)
            if len(closes) < 5:
                continue

            # 전일까지의 최고 종가/고가
            rolling_window = 60
            prev_closes = closes.iloc[:-1]
            prev_highs = highs.iloc[:-1]
            rolling_max_close = prev_closes.rolling(window=rolling_window, min_periods=5).max().iloc[-1]
            rolling_max_high = prev_highs.rolling(window=rolling_window, min_periods=5).max().iloc[-1]

            if pd.isna(rolling_max_close) or pd.isna(rolling_max_high):
                continue

            # 트레일링 스탑 비율 (예: 고점 대비 8% 하락 시 매도)
            trailing_drop_pct = 0.08
            base_max = max(float(rolling_max_close), float(rolling_max_high))
            trailing_stop = base_max * (1.0 - trailing_drop_pct)

            # ATR 기반 target/stop 보조: ATR 계산 가능하고 매입가가 있다면 사용
            atr = calculate_atr(df)
            atr_target_price = None
            atr_stop_price = None
            try:
                entry_price = float(stock.pchs_avg_pric)
            except (TypeError, ValueError):
                entry_price = None

            if atr is not None and entry_price and entry_price > 0:
                # 예시: 2R 익절, 1R 손절
                r_multiple_target = 2.0
                r_multiple_stop = 1.0
                risk_per_share = float(atr)
                atr_stop_price = max(entry_price - r_multiple_stop * risk_per_share, 0)
                atr_target_price = entry_price + r_multiple_target * risk_per_share

            # 실제 주문 가격 선택: ATR 타겟이 있으면 우선 사용, 없으면 트레일링 스탑만 사용
            price_candidates: list[float] = []
            if atr_target_price and atr_target_price > 0:
                price_candidates.append(float(atr_target_price))
            price_candidates.append(float(trailing_stop))

            if not price_candidates:
                continue

            # 상향 정렬 후 1~2개 가격대에 분할 매도 (R-multiple 관리용)
            price_candidates = sorted(set(price_candidates))
            sell_plan: dict[float, int] = {}

            if len(price_candidates) == 1:
                # 하나만 있으면 20%만 매도 예약
                sell_qty = max(1, int(qty * 0.2))
                sell_plan[price_candidates[0]] = sell_qty
            else:
                # 두 개 이상이면 절반씩 분할
                first_price, second_price = price_candidates[0], price_candidates[-1]
                first_qty = max(1, int(qty * 0.1))
                second_qty = max(1, int(qty * 0.1))
                total_planned = first_qty + second_qty
                if total_planned > qty:
                    # 보수적으로 전체 수량을 넘지 않도록 조정
                    scale = qty / total_planned
                    first_qty = max(1, int(first_qty * scale))
                    second_qty = max(1, int(second_qty * scale))
                sell_plan[first_price] = first_qty
                sell_plan[second_price] = sell_plan.get(second_price, 0) + second_qty

            if not sell_plan:
                continue

            for raw_price, vol in sell_plan.items():
                if vol <= 0:
                    continue
                if country_code == "KOR":
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
            logging.error(f"filter_box_for_buy Error occurred: {e}")
    return buy_levels


def filter_box_for_sell(stocks_held: list[StockResponseDTO] | StockResponseDTO | None, country: str = "KOR") -> dict[str, dict[float, int]]:
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

            # VWAP/POC 기반 분할 매도 (데이터 인프라가 충분한 경우)
            # 여기서는 단순 일봉 VWAP를 근사치로 사용
            vwap_price = None
            try:
                if "volume" in df.columns and not df["volume"].isna().all():
                    vol = df["volume"].astype(float)
                    typical_price = (df["high"].astype(float) + df["low"].astype(float) + df["close"].astype(float)) / 3.0
                    vwap_series = (typical_price * vol).cumsum() / vol.cumsum()
                    vwap_price = float(vwap_series.iloc[-1])
            except Exception:
                vwap_price = None

            if vwap_price and vwap_price > 0:
                # VWAP 근처 1차 매도, 상단 근처 2차 매도
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
        logging.error(f"Error occurred while getting nth open day: {e}")
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
                    logging.error(f"Error occurred while executing trades for symbol {symbol}: {e}")
        except Exception as e:
            logging.error(f"Error occurred while processing symbol {symbol}: {e}")

    if money:
        try:
            discord.send_message(f'총 액 : {money}')
        except Exception as e:
            logging.error(f"Error occurred while sending message to Discord: {e}")


def trading_sell(korea_investment: KoreaInvestmentAPI, sell_levels):
    """Place sell orders for stocks present in the queue."""
    end_date = korea_investment.get_nth_open_day(1)

    for symbol, levels in (sell_levels or {}).items():
        country = get_country_by_symbol(symbol)
        stock = korea_investment.get_owned_stock_info(symbol=symbol)
        if not stock:
            continue
        for price, volume in levels.items():
            if country == "KOR":
                if price < float(stock.pchs_avg_pric):
                    price = price_refine(int(float(stock.pchs_avg_pric) * 1.002), 1)
                korea_investment.sell_reserve(symbol=symbol, price=int(price), volume=volume, end_date=end_date)
            elif country == "USA":
                if price < float(stock.pchs_avg_pric):
                    price = round(float(stock.pchs_avg_pric) * 1.025, 2)
                korea_investment.submit_overseas_reservation_order(country=country, action="sell", symbol=symbol, price=str(round(float(price), 2)), volume=str(volume))


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
    print(sell_queue)
