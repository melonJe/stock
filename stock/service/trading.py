import logging
import math
import threading
import traceback
from datetime import datetime, timedelta
from datetime import time
from time import sleep

import numpy as np
import pandas as pd
from django.db.models import Q
from ta.momentum import rsi
from ta.trend import adx
# TA 라이브러리 설치 필요: pip install ta
from ta.volatility import AverageTrueRange
from ta.volume import ChaikinMoneyFlowIndicator

from stock.discord import discord
from stock.korea_investment.api import KoreaInvestmentAPI
from stock.models import PriceHistory, StopLoss, Subscription, Blacklist, Stock
from .data_handler import stop_loss_insert, insert_stock_price, get_price_history_table, get_stock_symbol_type
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


def select_buy_stocks(country: str) -> dict:
    buy_levels = dict()
    table = get_price_history_table(country)
    try:
        stocks = set(
            x['symbol']
            for x in Subscription.objects
            .exclude(Q(symbol__in=Blacklist.objects.values_list('symbol', flat=True)))
            .filter(symbol__country="KOR")
            .select_related("symbol")
            .values("symbol")
        )
        # stocks = set(x['symbol'] for x in Stock.objects.exclude(Q(symbol__in=Blacklist.objects.values_list('symbol', flat=True))).select_related("symbol").values('symbol'))
        for symbol in stocks:
            stock = Stock.objects.filter(symbol=symbol).first()
            df = pd.DataFrame(table.objects.filter(date__range=[datetime.now() - timedelta(days=365), datetime.now()], symbol=symbol).order_by('date').values())
            if len(df) < 200:
                continue

            df['ma120'] = df['close'].rolling(window=120).mean()
            df['ma60'] = df['close'].rolling(window=60).mean()
            df['ma20'] = df['close'].rolling(window=20).mean()
            latest_days = df[-10:]
            if not (
                    np.all(latest_days['ma120'] <= latest_days['ma60']) and
                    np.all(latest_days['ma60'] <= latest_days['ma20']) and
                    np.all(latest_days['ma20'] <= latest_days['close'])
            ):
                continue

            df['RSI'] = rsi(df['close'], window=9)
            if df.iloc[-1]['RSI'] > 70:
                continue

            df['ADX'] = adx(df['high'], df['low'], df['close'], window=14)
            if df.iloc[-1]['ADX'] < 25:
                continue

            df['CMF'] = ChaikinMoneyFlowIndicator(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), volume=df['volume'].astype('float64'), window=10).chaikin_money_flow()
            if df.iloc[-1]['CMF'] > 0.1:
                df['ATR5'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=5).average_true_range()
                df['ATR10'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=10).average_true_range()
                df['ATR20'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=20).average_true_range()
                atr = max(df.iloc[-1]['ATR5'], df.iloc[-1]['ATR10'], df.iloc[-1]['ATR20'])
                if atr / df.iloc[-1]['close'] > 0.05:
                    continue
                volume = int(min(10000 // atr, np.average(df['volume'][-20:]) // (atr ** (1 / 2))))
                buy_levels[symbol] = {
                    df.iloc[-1]['ma120']: volume // 10 * 4,
                    df.iloc[-1]['ma60']: volume // 10 * 3,
                    df.iloc[-1]['ma20']: volume // 10 * 2,
                    df.iloc[-1]['close']: volume // 10 * 1
                }
    except Exception as e:
        traceback.print_exc()
        logging.error(f"Error occurred: {e}")
    return buy_levels


def select_sell_stocks(ki_api: KoreaInvestmentAPI) -> dict:
    stocks = ki_api.get_owned_stock_info()
    sell_levels = {}
    for stock in stocks:
        try:
            df = pd.DataFrame(PriceHistory.objects.filter(date__range=[datetime.now() - timedelta(days=365), datetime.now()], symbol=stock.pdno).order_by('date').values())
            # 날짜순 정렬
            if len(df) < 60:
                continue

            df['MA20'] = df['close'].rolling(20).mean()
            df['StdDev'] = df['close'].rolling(20).std()
            df['UpperBB'] = df['MA20'] + 2 * df['StdDev']
            df['LowerBB'] = df['MA20'] - 2 * df['StdDev']
            df['Bandlength'] = df['UpperBB'] - df['LowerBB']

            if not (df.iloc[-10]['Bandlength'] < df.iloc[-5]['Bandlength'] < df.iloc[-1]['Bandlength']):
                continue

            df['ATR'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close']).average_true_range()
            if not (df.iloc[-10]['ATR'] < df.iloc[-5]['ATR'] < df.iloc[-1]['ATR']):
                continue

            df['RSI'] = rsi(df['close'], window=9)
            if df.iloc[-1]['RSI'] > 20:
                continue

            atr = df.iloc[-10]['ATR']
            volume = int(min(10000 // atr, np.average(df['volume'][-20:]) // (atr ** (1 / 2))))
            sell_levels[stock.pdno] = {
                df.iloc[-1]['high']: int(stock.ord_psbl_qty) // 12,
                df.iloc[-1]['close']: int(stock.ord_psbl_qty) // 3,
                df.iloc[-1]['low']: int(stock.ord_psbl_qty) // 12
            }
        except Exception as e:
            traceback.print_exc()
            logging.error(f"Error occurred: {e}")
    return sell_levels


def trading_buy(ki_api: KoreaInvestmentAPI, buy_levels):
    try:
        end_date = ki_api.get_nth_open_day(3)
    except Exception as e:
        traceback.print_exc()
        logging.error(f"Error occurred while getting nth open day: {e}")
        return

    money = 0

    for symbol, levels in buy_levels.items():
        try:
            stock = ki_api.get_owned_stock_info(symbol)
            stop_loss_insert(symbol, min(levels.keys()) * 0.95)
            for price, volume in levels.items():
                if stock and price > float(stock.pchs_avg_pric) * 0.975:
                    continue
                try:
                    if get_stock_symbol_type(symbol) == "KOR":
                        ki_api.buy_reserve(symbol=symbol, price=price_refine(price), volume=volume, end_date=end_date)
                        money += price * volume
                except Exception as e:
                    traceback.print_exc()
                    logging.error(f"Error occurred while executing trades for symbol {symbol}: {e}")
        except Exception as e:
            traceback.print_exc()
            logging.error(f"Error occurred while processing symbol {symbol}: {e}")

    if money:
        try:
            discord.send_message(f'총 액 : {money}')
        except Exception as e:
            traceback.print_exc()
            logging.error(f"Error occurred while sending message to Discord: {e}")


def trading_sell(ki_api: KoreaInvestmentAPI, sell_levels):
    end_date = ki_api.get_nth_open_day(3)
    for symbol, levels in sell_levels.items():
        stock = ki_api.get_owned_stock_info(symbol)
        if not stock:
            discord.send_message(f'Not held a stock {stock.prdt_name}')
            continue
        for price, volume in levels.items():
            if price < float(stock.pchs_avg_pric):
                price = price_refine(int(float(stock.pchs_avg_pric)), 3)
            ki_api.sell_reserve(symbol=symbol, price=price, volume=volume, end_date=end_date)


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

    while datetime.now().time() < time(10, 30, 30):
        sleep(1 * 60)

    insert_stock_price(start_date=datetime.now().strftime('%Y-%m-%d'), end_date=datetime.now().strftime('%Y-%m-%d'), country="USA")
    usa_stock = select_buy_stocks(country="USA")
    logging.info(f"usa_stock: {usa_stock}")
    buy = threading.Thread(target=trading_buy, args=(ki_api, usa_stock,))
    buy.start()

    while datetime.now().time() < time(15, 35, 30):
        sleep(1 * 60)

    insert_stock_price(start_date=datetime.now().strftime('%Y-%m-%d'), end_date=datetime.now().strftime('%Y-%m-%d'), country="KOR")
    for stock in ki_api.get_owned_stock_info():
        stop_loss_insert(stock.pdno, float(stock.pchs_avg_pric))

    while datetime.now().time() < time(16, 00, 30):
        sleep(1 * 60)

    sell_stock = select_sell_stocks(ki_api)
    sell = threading.Thread(target=trading_sell, args=(ki_api, sell_stock,))
    sell.start()
    buy_stock = select_buy_stocks(country="KOR")
    buy = threading.Thread(target=trading_buy, args=(ki_api, buy_stock,))
    buy.start()
