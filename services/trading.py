import datetime
import logging
import threading
from time import sleep
from typing import List, Union

import numpy as np
import pandas as pd
from ta.volatility import BollingerBands

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
    compute_resistance_prices,
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
        qty = int(stock.hldg_qty)
        try:
            if qty <= 0:
                continue

            df = fetch_price_dataframe(symbol)
            if df is None or len(df) < 30:
                continue

            bollinger = BollingerBands(close=df['close'], window=20, window_dev=2)
            df['BB_Upper'] = bollinger.bollinger_hband()
            df['BB_Lower'] = bollinger.bollinger_lband()
            bollinger_upper = df['BB_Upper'].iloc[-1] - (df['BB_Upper'].iloc[-1] - df['BB_Lower'].iloc[-1]) * 0.1
            target_price = max(float(stock.prpr) * 1.01, float(stock.pchs_avg_pric) * 1.025, bollinger_upper)
            if pd.isna(target_price) or target_price <= 0:
                continue

            lookback = 120
            window_df = df.tail(lookback).copy()
            if len(window_df) < 5:
                continue

            # pivot high: 현재 high가 이전·다음의 high보다 큰 경우
            window_df['pivot_high'] = (window_df['high'] > window_df['high'].shift(1)) & (window_df['high'] > window_df['high'].shift(-1))

            pivots = window_df[window_df['pivot_high']]

            # 후보 저항선: pivot 고점 중 target_price 이상인 값
            candidate_resistances = []
            if len(pivots) > 0:
                # pivot의 high값을 사용
                for val in pivots['high'].values:
                    try:
                        h = float(val)
                        if h >= target_price:
                            candidate_resistances.append(h)
                    except Exception:
                        continue

            # 보조: pivot이 없거나 후보가 없으면 최근 고점(rolling max) 중 target 이상인 것 사용
            if not candidate_resistances:
                rolling_max_20 = window_df['high'].rolling(window=20, min_periods=5).max()
                # 최근 3 지점에서 rolling max가 target 이상인 경우 후보로 추가
                recent_rolling = rolling_max_20.dropna().iloc[-10:] if len(rolling_max_20.dropna()) > 0 else pd.Series(dtype=float)
                for val in recent_rolling.values:
                    try:
                        v = float(val)
                        if v >= target_price:
                            candidate_resistances.append(v)
                    except Exception:
                        continue

            if not candidate_resistances:
                # 저항선 없음 -> 스킵
                continue

            # 가장 근접한(작은) 저항선 선택
            resistance_price = float(np.min(candidate_resistances))

            sell_qty = max(1, int(qty * 0.1))

            # 가격 소수점 정리: 종목에 따라 틱 사이즈가 다를 수 있으므로 소수 2자리로 둠.
            resistance_price = round(resistance_price, 2)

            if get_country_by_symbol(symbol) == "KOR":
                sell_levels[symbol] = {price_refine(int(resistance_price)): sell_qty}
            elif get_country_by_symbol(symbol) == "USA":
                sell_levels[symbol] = {resistance_price: sell_qty}

        except Exception as e:
            logging.error(f"sell_on_resistance 처리 중 에러: {symbol} -> {e}")
            continue
    return sell_levels

def filter_box_for_buy(country: str = "KOR") -> dict[str, dict[float, int]]:
    anchor_date, risk_amount_value, risk_k, adtv_limit_ratio, stocks, usd_krw = prepare_buy_context(country, "box")
    buy_levels: dict[str, dict[float, int]] = {}
    for symbol in stocks:
        try:
            df = fetch_price_dataframe(symbol)
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
            if df is None or len(df) < 120:
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

            box_break = (
                width_ratio < 0.05
                or width_ratio > 0.22
                or slope_ratio > 0.06
                or close_price > bb_upper * 1.01
                or close_price < bb_lower * 0.99
            )

            if box_break:
                sell_qty = max(1, int(qty * 0.2))
                target_price = prev_close if prev_close > 0 else close_price
                if symbol_country == "KOR":
                    price_key = price_refine(int(round(target_price)))
                else:
                    price_key = round(target_price, 2)
                sell_levels.setdefault(symbol, {})
                sell_levels[symbol][price_key] = sell_levels[symbol].get(price_key, 0) + sell_qty
                continue

            try:
                price_r1, price_r2, price_r3 = compute_resistance_prices(df.copy())
            except Exception:
                price_r1 = price_r2 = price_r3 = 0.0

            resistance_candidates = [r for r in (price_r1, price_r2, price_r3) if r and r > close_price]
            if not resistance_candidates:
                resistance_price = close_price * 1.02
            else:
                resistance_price = float(min(resistance_candidates))

            if resistance_price <= 0:
                continue

            sell_qty = max(1, int(qty * 0.1))
            if symbol_country == "KOR":
                price_key = price_refine(int(round(resistance_price)))
            else:
                price_key = round(resistance_price, 2)

            sell_levels.setdefault(symbol, {})
            sell_levels[symbol][price_key] = sell_levels[symbol].get(price_key, 0) + sell_qty

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
                    price = price_refine(int(float(stock.pchs_avg_pric)), 3)
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
    print(filter_trend_for_buy(country="USA"))
    print(filter_stable_for_buy(country="USA"))
