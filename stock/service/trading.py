import logging
import math
import threading
import traceback
from datetime import datetime, time, timedelta
from time import sleep

import numpy as np
import pandas as pd
from django.db.models import Q
from ta.volatility import AverageTrueRange

from stock.discord import discord
from stock.korea_investment.api import KoreaInvestmentAPI
from stock.models import Subscription, PriceHistory, StopLoss, Blacklist
from .data_handler import stop_loss_insert, add_stock_price
from .. import setting_env


def price_refine(price: int, number: int = 0) -> int:
    PRICE_LEVELS = [(2000, 1), (5000, 5), (20000, 10), (50000, 50), (200000, 100), (500000, 500), (float('inf'), 1000)]

    if number == 0:
        for level_price, adjustment in PRICE_LEVELS:
            if price < level_price or level_price == float('inf'):
                return round(price / adjustment) * adjustment

    increase = number > 0
    number_of_adjustments = abs(number)

    for _ in range(number_of_adjustments):
        for level_price, adjustment in PRICE_LEVELS:
            if (increase and price < level_price) or level_price == float('inf'):
                price = (math.trunc(price / adjustment) + 1) * adjustment
                break
            elif (not increase and price <= level_price) or level_price == float('inf'):
                price = (math.ceil(price / adjustment) - 1) * adjustment
                break

    return int(price)


def validate_and_adjust_volume(stock, requested_volume):
    if not stock or int(stock.ord_psbl_qty) == 0:
        logging.info(f"{stock.prdt_name if stock else '주식'} 가지고 있지 않거나 주문 가능한 수량이 없음")
        return 0
    return min(requested_volume, int(stock.ord_psbl_qty))


def select_buy_stocks() -> dict:
    result = dict()
    try:
        stocks = set(x['symbol'] for x in Subscription.objects.exclude(Q(symbol__in=Blacklist.objects.values_list('symbol', flat=True))).select_related("symbol").values('symbol'))
        # stocks = set(x['symbol'] for x in Stock.objects.select_related("symbol").values('symbol'))
        for symbol in stocks:
            df = pd.DataFrame(PriceHistory.objects.filter(date__range=[datetime.now() - timedelta(days=365), datetime.now()], symbol=symbol).order_by('date').values())
            if len(df) < 120:
                continue

            short_window = 12
            long_window = 26
            signal_window = 9

            df['MA20'] = df['close'].rolling(window=20).mean()
            df['STD20'] = df['close'].rolling(window=20).std()
            df['Upper_BB'] = df['MA20'] + (df['STD20'] * 2)
            df['Lower_BB'] = df['MA20'] - (df['STD20'] * 2)
            upper_bb = df.iloc[-1]['Upper_BB']
            lower_bb = df.iloc[-1]['Lower_BB']
            current_close = df.iloc[-1]['close']
            if not (current_close < lower_bb + (abs(upper_bb - lower_bb) * 0.05)):
                continue

            # lowest_20 = df.iloc[-20:-1]['MA20'].min()
            # # if not (0 <= (current_close - lowest_20) / lowest_20 * 100 <= 5):
            # if not (current_close > lowest_20):
            #     continue

            df['EMA_short'] = df['close'].ewm(span=short_window, adjust=False).mean()
            df['EMA_long'] = df['close'].ewm(span=long_window, adjust=False).mean()
            df['MACD'] = df['EMA_short'] - df['EMA_long']
            df['Signal'] = df['MACD'].ewm(span=signal_window, adjust=False).mean()
            if not (df.iloc[-2]['MACD'] < df.iloc[-2]['Signal']) and (df.iloc[-1]['MACD'] > df.iloc[-1]['Signal']):
                continue

            price_diff = df['close'].diff()  # 종가 차이 계산
            obv_change = np.select(
                [price_diff > 0, price_diff < 0, price_diff == 0],
                [df['volume'], -df['volume'], 0]  # 상승, 하락, 동일
            )
            df['OBV'] = obv_change.cumsum()
            df['OBV'] = df['OBV'].astype('float64')
            if not (df.iloc[-1]['OBV'] > df.iloc[-2]['OBV']):
                continue

            df['ATR5'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=5).average_true_range()
            df['ATR10'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=10).average_true_range()
            df['ATR20'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=20).average_true_range()
            atr = max(df.iloc[-1]['ATR5'], df.iloc[-1]['ATR10'], df.iloc[-1]['ATR20'])
            result[symbol] = min(100000000 // (100 * atr), np.min(df['volume'][-5:]) // 100)
    except Exception as e:
        traceback.print_exc()
        logging.error(f"Error occurred: {e}")
    return result


def select_sell_stocks(ki_api: KoreaInvestmentAPI) -> list:
    result = list()
    try:
        stocks = ki_api.get_owned_stock_info()
        for stock in stocks:
            df = pd.DataFrame(PriceHistory.objects.filter(date__range=[datetime.now() - timedelta(days=365), datetime.now()], symbol=stock.pdno).order_by('date').values())
            condition = []
            if len(df) < 200:
                continue

            df['MA20'] = df['close'].rolling(window=20).mean()
            df['STD20'] = df['close'].rolling(window=20).std()
            df['Upper_BB'] = df['MA20'] + (df['STD20'] * 2)
            df['Lower_BB'] = df['MA20'] - (df['STD20'] * 2)
            upper_bb = df.iloc[-1]['Upper_BB']
            lower_bb = df.iloc[-1]['Lower_BB']
            current_close = df.iloc[-1]['close']
            condition.append(current_close > upper_bb - (abs(upper_bb - lower_bb) * 0.05))

            highest_20 = df.iloc[-20:-1]['MA20'].max()
            condition.append(0 <= (highest_20 - current_close) / highest_20 * 100 <= 5)

            if any(condition):
                result.append(stock.pdno)
    except Exception as e:
        traceback.print_exc()
        logging.error(f"Error occurred: {e}")
    return result


def trading_buy(ki_api: KoreaInvestmentAPI):
    buy = select_buy_stocks()
    try:
        end_date = ki_api.get_nth_open_day(3)
    except Exception as e:
        traceback.print_exc()
        logging.error(f"Error occurred while getting nth open day: {e}")
        return

    money = 0
    volume_index = 0.002

    for symbol, volume in buy.items():
        try:
            price_last = PriceHistory.objects.filter(date__range=[datetime.now() - timedelta(days=5), datetime.now()], symbol=symbol).order_by('date').last()
            order_queue = {
                price_last.low: int(volume * volume_index * 0.6),
                price_refine((price_last.high + price_last.low) // 2): int(volume * volume_index * 0.4),
                price_last.high: int(volume * volume_index * 0.2)
            }
            for price, vol in order_queue:
                ki_api.buy_reserve(symbol=symbol, price=price, volume=vol, end_date=end_date)
                money += price * vol

        except Exception as e:
            traceback.print_exc()
            logging.error(f"Error occurred while executing trades for symbol {symbol}: {e}")

    if money:
        try:
            discord.send_message(f'총 액 : {money}')
        except Exception as e:
            traceback.print_exc()
            logging.error(f"Error occurred while sending message to Discord: {e}")


def trading_sell(ki_api: KoreaInvestmentAPI):
    end_date = ki_api.get_nth_open_day(14)
    sell = select_sell_stocks(ki_api)
    for symbol in sell:
        stock = ki_api.get_owned_stock_info(symbol)
        if not stock:
            discord.send_message(f'Not held a stock {stock.prdt_name}')
            continue
        sell_price = price_refine(int(stock.prpr))
        volume = validate_and_adjust_volume(stock, stock.ord_psbl_qty)
        if volume <= 0:
            continue

        if sell_price < price_refine(int(float(stock.pchs_avg_pric)), 3):
            sell_price = price_refine(int(float(stock.pchs_avg_pric)), 3)
        ki_api.sell_reserve(symbol=symbol, price=sell_price, volume=volume, end_date=end_date)


def stop_loss_notify(ki_api: KoreaInvestmentAPI):
    alert = set()
    while datetime.now().time() < time(15, 30, 00):
        owned_stock = ki_api.get_owned_stock_info()
        for item in owned_stock:
            try:
                if item.pdno in alert:
                    continue
                stock = StopLoss.objects.filter(symbol=item.pdno).first()
                if not stock:
                    stop_loss_insert(item.pdno, float(item.pchs_avg_pric))
                    continue
                if stock.price < int(item.prpr):
                    continue
                discord.send_message(f"{item.prdt_name} 판매 권유")
                logging.info(f"{item.prdt_name} 판매 권유")
                alert.add(item.pdno)
            except Exception as e:
                logging.error(f"Error processing item {item.pdno}: {e}")
                traceback.print_exc()

        sleep(1 * 60)


def korea_investment_trading():
    ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_code=setting_env.ACCOUNT_CODE)
    if ki_api.check_holiday(datetime.now().strftime("%Y%m%d")):
        logging.info(f'{datetime.now()} 휴장일')
        return
    stop_loss = threading.Thread(target=stop_loss_notify, args=(ki_api,))
    stop_loss.start()

    while datetime.now().time() < time(15, 35, 30):
        sleep(1 * 60)

    add_stock_price(start_date=datetime.now().strftime('%Y-%m-%d'), end_date=datetime.now().strftime('%Y-%m-%d'))
    for stock in ki_api.get_owned_stock_info():
        stop_loss_insert(stock.pdno, float(stock.pchs_avg_pric))

    while datetime.now().time() < time(16, 00, 30):
        sleep(1 * 60)

    sell = threading.Thread(target=trading_sell, args=(ki_api,))
    sell.start()
    buy = threading.Thread(target=trading_buy, args=(ki_api,))
    buy.start()
