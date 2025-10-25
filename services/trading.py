import datetime
import logging
import threading
from time import sleep

import FinanceDataReader
import numpy as np
import pandas as pd
from peewee import fn
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator

from apis.korea_investment import KoreaInvestmentAPI
from config import setting_env
from data.dto.account_dto import convert_overseas_to_domestic
from data.dto.stock_trade_dto import convert_overseas_to_stock_trade
from data.models import Blacklist, Stock, StopLoss, Subscription, SellQueue
from services.data_handler import stop_loss_insert, get_country_by_symbol, add_stock_price
from services.trading_helpers import fetch_price_dataframe, calc_adjusted_volumes
from utils import discord
from utils.operations import price_refine


def select_buy_stocks(country: str = "KOR") -> dict[str, dict[float, int]]:
    buy_levels: dict[str, dict[float, int]] = {}
    buy_levels.update(filter_stable_pullback_stocks(country=country))
    buy_levels.update(filter_trend_pullback_reversal(country=country))
    return buy_levels


def filter_trend_pullback_reversal(country: str = "KOR") -> dict[str, dict[float, int]]:
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


def filter_stable_pullback_stocks(country: str = "KOR") -> dict[str, dict[float, int]]:
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

    def bb_proximity_ok(df_all: pd.DataFrame, tol: float = 0.1, use_low: bool = True, lookback: int = 3) -> bool:
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
            if not bb_proximity_ok(df, tol=0.1, use_low=True, lookback=3):
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
            # Compute ATR-based stop loss (based on expected weighted entry price)
            stop_atr_mult = getattr(setting_env, "STOP_ATR_MULT", 1.2)
            # expected weighted average entry from planned levels
            try:
                total_vol = sum(int(v) for v in levels.values() if v)
                weighted_sum = sum(float(p) * int(v) for p, v in levels.items() if v)
                expected_entry = (weighted_sum / total_vol) if total_vol > 0 else float(min(levels.keys()))
            except Exception:
                expected_entry = float(min(levels.keys()))
            try:
                df = fetch_price_dataframe(symbol)
                if country == "USA":
                    df['open'] = df['open'].astype(float)
                    df['high'] = df['high'].astype(float)
                    df['close'] = df['close'].astype(float)
                    df['low'] = df['low'].astype(float)
                df['ATR5'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=5).average_true_range()
                df['ATR10'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=10).average_true_range()
                df['ATR20'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=20).average_true_range()
                atr = max(df.iloc[-1]['ATR5'], df.iloc[-1]['ATR10'], df.iloc[-1]['ATR20'])
                if pd.isna(atr) or atr <= 0:
                    stop_loss_price = expected_entry * 0.95  # fallback to 5% below expected entry
                else:
                    stop_loss_price = max(0.0, expected_entry - atr * float(stop_atr_mult))
            except Exception:
                stop_loss_price = expected_entry * 0.95  # fallback
            stop_loss_insert(symbol, stop_loss_price)
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

    for symbol, levels in sell_levels.items():
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


def update_sell_queue(ki_api: KoreaInvestmentAPI, country: str = "KOR"):
    """Synchronize recent trade history with internal sell queue."""
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    response_data = []
    if country == "KOR":
        response_data = ki_api.get_stock_order_list(start_date=today_str, end_date=today_str)
    elif country == "USA":
        response_data = convert_overseas_to_stock_trade(
            ki_api.get_overseas_stock_order_list(start_date=today_str, end_date=today_str))

    sell_queue_entries = {}
    for trade in response_data:
        volume = int(trade.tot_ccld_qty)
        price = int(trade.avg_prvs)
        trade_type = trade.sll_buy_dvsn_cd

        if trade_type == "02":
            # 매수 체결 시: 최근 가격 이력 기반의 저항선 3레벨로 판매 가격을 분산 설정
            try:
                # 폴백: 기존 고정 비율 기반 가격 생성
                base = float(getattr(trade, "pchs_avg_pric", price))
                volumes_and_prices = calc_adjusted_volumes(volume, base, country)
                for vol, prc in volumes_and_prices:
                    if vol > 0:
                        sell_queue_entries[(trade.pdno, prc)] = sell_queue_entries.get((trade.pdno, prc), 0) + vol
            except Exception:
                continue

        elif trade_type == "01":
            sell_queue_entries[(trade.pdno, price)] = sell_queue_entries.get((trade.pdno, price), 0) - volume

    for (symbol, price), volume in sell_queue_entries.items():
        sell_entry = SellQueue.get_or_none((SellQueue.symbol == symbol) & (SellQueue.price == price))
        if sell_entry:
            sell_entry.volume += volume
            if sell_entry.volume <= 0:
                sell_entry.delete_instance()
            else:
                sell_entry.save()
        elif volume > 0:
            SellQueue.create(symbol=symbol, volume=volume, price=price)

    owned_stock_info = []
    if country == "KOR":
        owned_stock_info = ki_api.get_korea_owned_stock_info()
    else:
        owned_stock_info = convert_overseas_to_domestic(ki_api.get_oversea_owned_stock_info(country=country))

    symbols = [s.pdno for s in owned_stock_info]
    stock_map = {s.symbol: s for s in Stock.select().where(Stock.symbol.in_(symbols))}

    for stock in owned_stock_info:
        stock_db = stock_map.get(stock.pdno)
        if not stock_db:
            continue
        owned_volume = int(stock.hldg_qty)
        total_db_volume = SellQueue.select(fn.SUM(SellQueue.volume)).where(SellQueue.symbol == stock_db.symbol).scalar() or 0

        if owned_volume < total_db_volume:
            excess_volume = total_db_volume - owned_volume
            while excess_volume > 0:
                smallest_price_entry = SellQueue.select().where(SellQueue.symbol == stock_db.symbol).order_by(SellQueue.price).first()
                if smallest_price_entry:
                    if smallest_price_entry.volume <= excess_volume:
                        excess_volume -= smallest_price_entry.volume
                        smallest_price_entry.delete_instance()
                    else:
                        smallest_price_entry.volume -= excess_volume
                        smallest_price_entry.save()
                        excess_volume = 0
        elif owned_volume > total_db_volume:
            additional_volume = owned_volume - total_db_volume
            avg_price = float(stock.pchs_avg_pric)

            volumes_and_prices = calc_adjusted_volumes(additional_volume, avg_price, stock_db.country)
            for vol, prc in volumes_and_prices:
                if vol > 0:
                    sell_entry = SellQueue.get_or_none((SellQueue.symbol == stock_db.symbol) & (SellQueue.price == prc))
                    if sell_entry:
                        sell_entry.volume += vol
                        sell_entry.save()
                    else:
                        SellQueue.create(symbol=stock_db.symbol, volume=vol, price=prc)

    SellQueue.delete().where(SellQueue.volume <= 0).execute()


def stop_loss_notify(korea_investment: KoreaInvestmentAPI):
    alert = set()
    while datetime.datetime.now().time() < datetime.time(15, 30, 00):
        try:
            owned_stocks = korea_investment.get_owned_stock_info()
            for item in owned_stocks:
                if item.pdno in alert:
                    continue
                stock = StopLoss.get_or_none(StopLoss.symbol == item.pdno)
                if not stock:
                    stop_loss_insert(item.pdno, float(item.pchs_avg_pric))
                    continue
                if stock.price < int(item.prpr):
                    continue
                discord.send_message(f"{item.prdt_name} 판매 권유")
                logging.info(f"{item.prdt_name} 판매 권유")
                alert.add(item.pdno)
        except Exception as e:
            logging.error(f"stop_loss_notify Error processing: {e}")

        sleep(1 * 60)


def korea_trading():
    """Main entry to run daily domestic trading tasks."""
    ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_code=setting_env.ACCOUNT_CODE)
    if ki_api.check_holiday(datetime.datetime.now().strftime("%Y%m%d")):
        logging.info(f'{datetime.datetime.now()} 휴장일')
        return

    while datetime.datetime.now().time() < datetime.time(18, 15, 00):
        sleep(1 * 60)

    update_sell_queue(ki_api=ki_api)
    add_stock_price(country="KOR", start_date=datetime.datetime.now() - datetime.timedelta(days=5), end_date=datetime.datetime.now())
    for stock in ki_api.get_owned_stock_info():
        stop_loss_insert(stock.pdno, float(stock.pchs_avg_pric))

    sell_queue = {}
    for sell in SellQueue.select().join(Stock, on=(SellQueue.symbol == Stock.symbol)).where(Stock.country == 'KOR'):
        if sell.symbol not in sell_queue.keys():
            sell_queue[sell.symbol] = {}
        sell_queue[sell.symbol][sell.price] = sell.volume
    sell = threading.Thread(target=trading_sell, args=(ki_api, sell_queue,))
    sell.start()

    buy_stock = select_buy_stocks(country="KOR")
    logging.info(f'buy_stock data: {buy_stock}')
    buy = threading.Thread(target=trading_buy, args=(ki_api, buy_stock,))
    buy.start()


def usa_trading():
    """Execute U.S. market trading workflow."""
    ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_code=setting_env.ACCOUNT_CODE)
    update_sell_queue(ki_api=ki_api, country="USA")
    usa_stock = select_buy_stocks(country="USA")
    usa_buy = threading.Thread(target=trading_buy, args=(ki_api, usa_stock,))
    usa_buy.start()

    sell_queue = {}
    for sell in SellQueue.select().join(Stock, on=(SellQueue.symbol == Stock.symbol)).where(Stock.country == 'USA'):
        if sell.symbol not in sell_queue.keys():
            sell_queue[sell.symbol] = {}
        sell_queue[sell.symbol][sell.price] = sell.volume
    sell = threading.Thread(target=trading_sell, args=(ki_api, sell_queue,))
    sell.start()


if __name__ == "__main__":
    print(filter_trend_pullback_reversal())
