import datetime
import logging
import threading
from time import sleep
from typing import List, Union

import FinanceDataReader
import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator

from apis.korea_investment import KoreaInvestmentAPI
from config import setting_env
from data.dto.account_dto import StockResponseDTO
from data.models import Blacklist, Stock, Subscription
from services.data_handler import get_country_by_symbol, add_stock_price
from services.trading_helpers import fetch_price_dataframe
from utils import discord
from utils.operations import price_refine


def select_buy_stocks(country: str = "KOR") -> dict[str, dict[float, int]]:
    buy_levels = {}
    for d in [filter_stable_for_buy(country=country), filter_trend_for_buy(country=country)]:
        for sym, price_dict in d.items():
            for price, qty in price_dict.items():
                buy_levels.setdefault(sym, {})
                buy_levels[sym][price] = buy_levels[sym].get(price, 0) + qty
    return buy_levels


def select_sell_stocks(stocks_held: Union[List[StockResponseDTO], StockResponseDTO, None]) -> dict[str, dict[float, int]]:
    sell_levels = {}
    for d in [filter_stable_for_sell(stocks_held), filter_trend_for_sell(stocks_held)]:
        for sym, price_dict in d.items():
            for price, qty in price_dict.items():
                sell_levels.setdefault(sym, {})
                sell_levels[sym][price] = sell_levels[sym].get(price, 0) + qty
    return sell_levels


def filter_trend_for_buy(country: str = "KOR") -> dict[str, dict[float, int]]:
    buy_levels: dict[str, dict[float, int]] = {}

    usd_krw = FinanceDataReader.DataReader("USD/KRW").iloc[-1]["Adj Close"]

    risk_pct = getattr(setting_env, "RISK_PCT", 0.0051)
    risk_k = getattr(setting_env, "RISK_ATR_MULT", 12.0)
    adtv_limit_ratio = getattr(setting_env, "ADTV_LIMIT_RATIO", 0.015)
    default_equity_krw = getattr(setting_env, "EQUITY_KRW", 100_000_000.0)
    default_equity_usd = getattr(setting_env, "EQUITY_USD", 100_000.0)

    anchor_date = datetime.datetime.now()
    if country == "USA":
        anchor_date -= datetime.timedelta(days=1)
    anchor_date = anchor_date.strftime("%Y-%m-%d")

    equity_base = default_equity_usd if country == "USA" else default_equity_krw
    risk_amount_value = equity_base * risk_pct

    blacklist_symbols = Blacklist.select(Blacklist.symbol)
    sub_symbols = Subscription.select(Subscription.symbol).where(Subscription.category == "growth")
    stocks_query = (
        Stock.select(Stock.symbol)
        .where(
            (Stock.country == country)
            & (Stock.symbol.in_(sub_symbols))
            & ~(Stock.symbol.in_(blacklist_symbols))
        )
    )
    stocks = {row.symbol for row in stocks_query}

    for symbol in stocks:
        try:
            df = fetch_price_dataframe(symbol)

            if country == 'USA':
                df['open'] = df['open'].astype(float)
                df['high'] = df['high'].astype(float)
                df['close'] = df['close'].astype(float)
                df['low'] = df['low'].astype(float)

            if not str(df.iloc[-1]['date']) == anchor_date:
                continue

            if len(df) < 150:
                continue

            if country == 'KOR' and df.iloc[-1]['close'] * df['volume'].rolling(window=50).mean().iloc[-1] < 10000000 * usd_krw:
                continue

            if country == 'USA' and df.iloc[-1]['close'] * df['volume'].rolling(window=50).mean().iloc[-1] < 20000000:
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

            rsi = RSIIndicator(close=df['close'], window=7).rsi()
            if pd.isna(rsi.iloc[-1]):
                continue
            if not (30 <= float(rsi.iloc[-1]) <= 50):
                continue

            macd_indicator = MACD(close=df['close'], window_fast=12, window_slow=26, window_sign=9)
            df['MACD'] = macd_indicator.macd()
            df['MACD_Signal'] = macd_indicator.macd_signal()
            if pd.isna(df['MACD'].iloc[-1]) or pd.isna(df['MACD_Signal'].iloc[-1]):
                continue
            macd_curr = float(df['MACD'].iloc[-1])
            macd_prev = float(df['MACD'].iloc[-2])
            sig_curr = float(df['MACD_Signal'].iloc[-1])
            sig_prev = float(df['MACD_Signal'].iloc[-2])
            recent_below_signal = bool((df['MACD'] <= df['MACD_Signal']).tail(6).head(5).any())
            macd_rebound = (macd_curr >= sig_curr) and ((macd_curr - sig_curr) > (macd_prev - sig_prev)) and recent_below_signal
            if not macd_rebound:
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

            bollinger = BollingerBands(close=df['close'], window=20, window_dev=2)
            df['BB_Mavg'] = bollinger.bollinger_mavg()
            df['BB_Upper'] = bollinger.bollinger_hband()
            df['BB_Lower'] = bollinger.bollinger_lband()

            df['ATR5'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=5).average_true_range()
            df['ATR10'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=10).average_true_range()
            df['ATR20'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=20).average_true_range()
            atr = max(df.iloc[-1]['ATR5'], df.iloc[-1]['ATR10'], df.iloc[-1]['ATR20'])
            if pd.isna(atr) or atr <= 0:
                continue

            base_shares = int(risk_amount_value / (atr * risk_k))
            if base_shares <= 0:
                continue

            adtv = float(df.iloc[-1]['close']) * float(df['volume'].rolling(window=50).mean().iloc[-1])
            if pd.isna(adtv) or adtv <= 0:
                continue
            shares_adtv_cap = int((adtv * adtv_limit_ratio) / float(df.iloc[-1]['close']))
            volume_shares = max(0, min(base_shares, shares_adtv_cap))
            if volume_shares <= 0:
                continue

            df['pivot_low_flag'] = (df['low'] < df['low'].shift(1)) & (df['low'] < df['low'].shift(-1))
            pivots_window = df.tail(30)
            pivots = pivots_window[pivots_window['pivot_low_flag']]
            if len(pivots) > 0:
                pivot_low_val = float(pivots.iloc[-1]['low'])
            else:
                pivot_low_val = float(df['low'].rolling(window=5).min().iloc[-2])

            bb_lower_today = float(df.iloc[-1]['BB_Lower']) if not pd.isna(df.iloc[-1]['BB_Lower']) else np.nan
            if pd.isna(pivot_low_val) or pivot_low_val <= 0:
                pivot_low_val = float(df['low'].rolling(window=10).min().iloc[-2])
            if pd.isna(bb_lower_today) or bb_lower_today <= 0:
                bb_lower_today = float(df['low'].rolling(window=20).quantile(0.1).iloc[-2])

            price_s1 = max(0.0, float(pivot_low_val))
            deeper_candidate = float(pivot_low_val) - 0.5 * float(atr)
            price_s2 = max(0.0, float(min(bb_lower_today, deeper_candidate)))

            vol_s1 = int(volume_shares // 3)
            vol_s2 = int(volume_shares - vol_s1)
            if abs(price_s1 - price_s2) < 1e-8:
                buy_levels[symbol] = {price_s1: int(volume_shares)}
            else:
                buy_levels[symbol] = {price_s1: vol_s1, price_s2: vol_s2}
        except Exception as e:
            logging.error(f"filter_trend_pullback_reversal Error occurred: {e}")
    return buy_levels


def filter_trend_for_sell(stocks_held: list[StockResponseDTO] | StockResponseDTO | None, country: str = "KOR") -> dict[str, dict[float, int]]:
    sell_levels = {}
    return sell_levels


def filter_stable_for_buy(country: str = "KOR") -> dict[str, dict[float, int]]:
    buy_levels: dict[str, dict[float, int]] = {}

    usd_krw = FinanceDataReader.DataReader("USD/KRW").iloc[-1]["Adj Close"]

    # Risk & liquidity config (override via config.setting_env)
    risk_pct = getattr(setting_env, "RISK_PCT", 0.0051)  # 0.51% per trade
    risk_k = getattr(setting_env, "RISK_ATR_MULT", 12.0)  # ATR multiple for risk distance
    adtv_limit_ratio = getattr(setting_env, "ADTV_LIMIT_RATIO", 0.015)  # 1.5% of ADTV cap
    default_equity_krw = getattr(setting_env, "EQUITY_KRW", 100_000_000.0)
    default_equity_usd = getattr(setting_env, "EQUITY_USD", 100_000.0)

    anchor_date = datetime.datetime.now()
    if country == "USA":
        anchor_date -= datetime.timedelta(days=1)
    anchor_date = anchor_date.strftime("%Y-%m-%d")

    equity_base = default_equity_usd if country == "USA" else default_equity_krw
    risk_amount_value = equity_base * risk_pct

    def higher_timeframe_ok(df_all: pd.DataFrame) -> bool:
        df_res = df_all[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
        df_res['date_dt'] = pd.to_datetime(df_res['date'], errors='coerce')
        df_res = df_res.dropna(subset=['date_dt']).sort_values('date_dt')
        weekly_ok = False
        monthly_ok = False
        if len(df_res) >= 2:
            weekly = df_res.resample('W-FRI', on='date_dt').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
            monthly = df_res.resample('ME', on='date_dt').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
            if len(weekly) >= 3:
                wk_close_prev = float(weekly['close'].iloc[-2])
                wk_sma20_series = weekly['close'].rolling(20).mean()
                wk_sma20_prev = wk_sma20_series.iloc[-2] if len(wk_sma20_series) >= 2 else np.nan
                if not pd.isna(wk_sma20_prev):
                    weekly_ok = bool(wk_close_prev > float(wk_sma20_prev))
                else:
                    wk_down1 = bool(weekly['close'].iloc[-2] < weekly['close'].iloc[-3])
                    wk_down2 = bool(weekly['close'].iloc[-3] < weekly['close'].iloc[-4]) if len(weekly) >= 4 else False
                    weekly_ok = not (wk_down1 and wk_down2)
            if len(monthly) >= 2:
                mo_sma10_series = monthly['close'].rolling(10).mean()
                mo_sma10_prev = mo_sma10_series.iloc[-2] if len(mo_sma10_series) >= 2 else np.nan
                if not pd.isna(mo_sma10_prev):
                    mo_close_prev = float(monthly['close'].iloc[-2])
                    monthly_ok = bool(mo_close_prev >= float(mo_sma10_prev))
        return bool(weekly_ok or monthly_ok)

    def bb_proximity_ok(df_all: pd.DataFrame, tol: float = 0.05, use_low: bool = True, lookback: int = 3) -> bool:
        df_tail = df_all.tail(int(max(1, lookback)))
        lower = df_tail['BB_Lower']
        upper = df_tail['BB_Upper']
        denom = upper - lower
        price_series = np.minimum(df_tail['close'], df_tail['low']) if use_low else df_tail['close']
        valid = (~pd.isna(lower)) & (~pd.isna(upper)) & (~pd.isna(price_series)) & (denom > 0)
        if not valid.any():
            return False
        pct_b = (price_series - lower) / denom
        return bool((pct_b[valid] <= tol).any())

    def obv_sma_rising(df_all: pd.DataFrame, steps: int = 3) -> bool:
        obv_series = OnBalanceVolumeIndicator(close=df_all['close'], volume=df_all['volume']).on_balance_volume()
        obv_sma = obv_series.rolling(window=10).mean()
        if len(obv_sma) < steps + 1:
            return False
        if pd.isna(obv_sma.iloc[-1]) or pd.isna(obv_sma.iloc[-steps]):
            return False
        return bool(obv_sma.iloc[-1] > obv_sma.iloc[-steps])

    blacklist_symbols = Blacklist.select(Blacklist.symbol)
    sub_symbols = Subscription.select(Subscription.symbol).where(Subscription.category == "dividend")
    stocks_query = (
        Stock.select(Stock.symbol)
        .where(
            (Stock.country == country)
            & (Stock.symbol.in_(sub_symbols))
            & ~(Stock.symbol.in_(blacklist_symbols))
        )
    )
    stocks = {row.symbol for row in stocks_query}

    for symbol in stocks:
        try:
            df = fetch_price_dataframe(symbol)

            if country == 'USA':
                df['open'] = df['open'].astype(float)
                df['high'] = df['high'].astype(float)
                df['close'] = df['close'].astype(float)
                df['low'] = df['low'].astype(float)

            if not str(df.iloc[-1]['date']) == anchor_date:  # 마지막 데이터가 오늘이 아니면 pass
                continue

            if len(df) < 100:
                continue

            if country == 'KOR' and df.iloc[-1]['close'] * df['volume'].rolling(window=50).mean().iloc[-1] < 10000000 * usd_krw:
                continue

            if country == 'USA' and df.iloc[-1]['close'] * df['volume'].rolling(window=50).mean().iloc[-1] < 20000000:
                continue

            if not higher_timeframe_ok(df):
                continue

            bollinger = BollingerBands(close=df['close'], window=20, window_dev=2)
            df['BB_Mavg'] = bollinger.bollinger_mavg()
            df['BB_Upper'] = bollinger.bollinger_hband()
            df['BB_Lower'] = bollinger.bollinger_lband()
            if not bb_proximity_ok(df, tol=0.10, use_low=True, lookback=3):
                continue

            if not obv_sma_rising(df, steps=3):
                continue

            df['RSI'] = RSIIndicator(close=df['close'], window=7).rsi()
            rsi_curr, rsi_prev = df.iloc[-1]['RSI'], df.iloc[-2]['RSI']
            rsi_condition = rsi_prev < rsi_curr < 30
            macd_indicator = MACD(close=df['close'], window_fast=12, window_slow=26, window_sign=9)
            df['MACD'], df['MACD_Signal'] = macd_indicator.macd(), macd_indicator.macd_signal()
            macd_curr, macd_prev = df.iloc[-1], df.iloc[-2]
            macd_condition = macd_prev['MACD'] <= macd_prev['MACD_Signal'] and macd_curr['MACD'] >= macd_curr['MACD_Signal']
            if not (rsi_condition or macd_condition):
                continue

            if not (float(df.iloc[-1]['close']) > float(df.iloc[-2]['low'])):
                continue

            df['ATR5'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=5).average_true_range()
            df['ATR10'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=10).average_true_range()
            df['ATR20'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=20).average_true_range()
            atr = max(df.iloc[-1]['ATR5'], df.iloc[-1]['ATR10'], df.iloc[-1]['ATR20'])
            if pd.isna(atr) or atr <= 0:
                continue

            # Risk-based position sizing
            base_shares = int(risk_amount_value / (atr * risk_k))
            if base_shares <= 0:
                continue

            # Liquidity cap by ADTV
            adtv = float(df.iloc[-1]['close']) * float(df['volume'].rolling(window=50).mean().iloc[-1])
            if pd.isna(adtv) or adtv <= 0:
                continue
            shares_adtv_cap = int((adtv * adtv_limit_ratio) / float(df.iloc[-1]['close']))
            volume = max(0, min(base_shares, shares_adtv_cap))
            if volume <= 0:
                continue

            # Support-based buy levels: recent pivot low and deeper support (BB lower or ATR-projected)
            # 1) 최근 피벗 저점 탐지 (local minimum)
            df['pivot_low_flag'] = (df['low'] < df['low'].shift(1)) & (df['low'] < df['low'].shift(-1))
            pivots_window = df.tail(30)
            pivots = pivots_window[pivots_window['pivot_low_flag']]
            if len(pivots) > 0:
                pivot_low_val = float(pivots.iloc[-1]['low'])
            else:
                # 피벗이 없으면 최근 5거래일(당일 제외) 최저가 사용
                pivot_low_val = float(df['low'].rolling(window=5).min().iloc[-2])

            bb_lower_today = float(df.iloc[-1]['BB_Lower']) if not pd.isna(df.iloc[-1]['BB_Lower']) else np.nan
            # 안전한 폴백 처리
            if pd.isna(pivot_low_val) or pivot_low_val <= 0:
                pivot_low_val = float(df['low'].rolling(window=10).min().iloc[-2])
            if pd.isna(bb_lower_today) or bb_lower_today <= 0:
                # 볼린저 하단이 없으면 최근 20일 10% 분위값을 근사 하단으로 사용
                bb_lower_today = float(df['low'].rolling(window=20).quantile(0.1).iloc[-2])

            # 두 개의 지지선 가격 산정
            price_s1 = max(0.0, float(pivot_low_val))
            deeper_candidate = float(pivot_low_val) - 0.5 * float(atr)
            price_s2 = max(0.0, float(min(bb_lower_today, deeper_candidate)))

            # 물량 배분 (1/3, 2/3). 동일 가격이면 합산 처리
            vol_s1 = int(volume // 3)
            vol_s2 = int(volume - vol_s1)
            if abs(price_s1 - price_s2) < 1e-8:
                buy_levels[symbol] = {price_s1: int(volume)}
            else:
                buy_levels[symbol] = {
                    price_s1: vol_s1,
                    price_s2: vol_s2,
                }
        except Exception as e:
            logging.error(f"select_buy_stocks Error occurred: {e}")
    return buy_levels


def filter_stable_for_sell(stocks_held: Union[List[StockResponseDTO], StockResponseDTO, None], country: str = "KOR") -> dict[str, dict[float, int]]:
    sell_levels = {}
    for stock in (stocks_held or {}):
        symbol = stock.pdno
        if Subscription.select().where(
                (Subscription.category == "growth") & (Subscription.symbol == symbol)
        ).exists():
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
    ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY_USA, app_secret=setting_env.APP_SECRET_USA, account_number=setting_env.ACCOUNT_NUMBER_USA, account_code=setting_env.ACCOUNT_CODE_USA)
