import logging
import math
import threading
import traceback
from datetime import datetime, time, timedelta
from time import sleep

import numpy as np
import pandas as pd
from django.db.models import Q, Sum
from ta.momentum import rsi
from ta.trend import adx
from ta.volatility import AverageTrueRange
from ta.volume import ChaikinMoneyFlowIndicator

from stock.discord import discord
from stock.korea_investment.api import KoreaInvestmentAPI
from stock.models import PriceHistory, StopLoss, Subscription, Blacklist, SellQueue, Stock, Account
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
        buy = dict()
        sieve = dict()
        for symbol in stocks:
            df = pd.DataFrame(PriceHistory.objects.filter(date__range=[datetime.now() - timedelta(days=365), datetime.now()], symbol=symbol).order_by('date').values())
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
                volume = min(100000000 // (100 * atr), np.min(df['volume'][-5:]) // 100)
                buy[symbol] = volume
                sieve[symbol] = df.iloc[-1]['CMF']
        for x in list(dict(sorted(sieve.items(), key=lambda item: item[1], reverse=True)).keys()):
            result[x] = buy[x]
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


def trading_buy(ki_api: KoreaInvestmentAPI, buy):
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
            stock = ki_api.get_owned_stock_info(symbol)
            price_last = PriceHistory.objects.filter(date__range=[datetime.now() - timedelta(days=20), datetime.now()], symbol=symbol).order_by('date').last()

            stop_loss_insert(symbol, price_last.close * 0.9)

            order_queue = {
                price_last.low: int(volume * volume_index * (1 / 2)),
                price_refine((price_last.high + price_last.low) // 2): int(volume * volume_index * (1 / 3)),
                price_last.high: int(volume * volume_index * (1 / 6))
            }
            for price, vol in order_queue.items():
                if stock and price > float(stock.pchs_avg_pric) * 0.975:
                    continue
                try:
                    ki_api.buy_reserve(symbol=symbol, price=price, volume=vol, end_date=end_date)
                    money += price * vol
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


def trading_sell(ki_api: KoreaInvestmentAPI):
    end_date = ki_api.get_nth_open_day(1)
    queue_entries = SellQueue.objects.filter(email="cabs0814@naver.com")
    for entry in queue_entries:
        stock = ki_api.get_owned_stock_info(entry.symbol.symbol)
        if not stock:
            discord.send_message(f'Not held a stock {entry.symbol.company_name}')
            continue
        sell_price = price_refine(entry.price)
        volume = validate_and_adjust_volume(stock, entry.volume)
        if volume <= 0:
            continue

        if sell_price < float(stock.pchs_avg_pric):
            sell_price = price_refine(int(float(stock.pchs_avg_pric)), 3)
        ki_api.sell_reserve(symbol=entry.symbol.symbol, price=sell_price, volume=volume, end_date=end_date)


def update_sell_queue(ki_api: KoreaInvestmentAPI, email: Account):
    today_str = datetime.now().strftime("%Y%m%d")
    response_data = ki_api.get_stock_order_list(start_date=today_str, end_date=today_str)

    sell_queue_entries = {}
    for trade in response_data:
        symbol = Stock.objects.get(symbol=trade.pdno)
        volume = int(trade.tot_ccld_qty)
        price = int(trade.avg_prvs)
        trade_type = trade.sll_buy_dvsn_cd

        if trade_type == "02":
            df = pd.DataFrame(PriceHistory.objects.filter(date__range=[datetime.now() - timedelta(days=600), datetime.now()], symbol=symbol).order_by('date').values())
            df['ma60'] = df['close'].rolling(window=60).mean()
            volumes_and_prices = [
                (volume - int(volume * 0.5), price_refine(math.ceil(max(price * 1.005, df.iloc[-1]['ma60'] * 1.125)))),
                (int(volume * 0.5), price_refine(math.ceil(max(price * 1.005, df.iloc[-1]['ma60'] * 1.175))))
            ]

            for vol, prc in volumes_and_prices:
                if vol > 0:
                    sell_queue_entries[(email, symbol, prc)] = sell_queue_entries.get((email, symbol, prc), 0) + vol

        elif trade_type == "01":
            sell_queue_entries[(email, symbol, price)] = sell_queue_entries.get((email, symbol, price), 0) - volume

    for (email, symbol, price), volume in sell_queue_entries.items():
        try:
            sell_entry = SellQueue.objects.get(email=email, symbol=symbol, price=price)
            sell_entry.volume += volume
            if sell_entry.volume <= 0:
                sell_entry.delete()
            else:
                sell_entry.save()
        except SellQueue.DoesNotExist:
            if volume > 0:
                SellQueue.objects.create(email=email, symbol=symbol, volume=volume, price=price)

    owned_stock_info = ki_api.get_owned_stock_info()
    for stock in owned_stock_info:
        symbol = Stock.objects.get(symbol=stock.pdno)
        owned_volume = int(stock.hldg_qty)
        total_db_volume = SellQueue.objects.filter(email=email, symbol=stock.pdno).aggregate(total_volume=Sum('volume'))['total_volume'] or 0

        if owned_volume < total_db_volume:
            excess_volume = total_db_volume - owned_volume
            while excess_volume > 0:
                smallest_price_entry = SellQueue.objects.filter(email=email, symbol=symbol).order_by('price').first()
                if smallest_price_entry:
                    if smallest_price_entry.volume <= excess_volume:
                        excess_volume -= smallest_price_entry.volume
                        smallest_price_entry.delete()
                    else:
                        smallest_price_entry.volume -= excess_volume
                        smallest_price_entry.save()
                        excess_volume = 0

        elif owned_volume > total_db_volume:
            additional_volume = owned_volume - total_db_volume
            avg_price = float(stock.pchs_avg_pric)

            df = pd.DataFrame(PriceHistory.objects.filter(date__range=[datetime.now() - timedelta(days=600), datetime.now()], symbol=symbol).order_by('date').values())
            df['ma60'] = df['close'].rolling(window=60).mean()

            volumes_and_prices = [
                (additional_volume, price_refine(math.ceil(avg_price * 1.005), 1))
            ]

            for vol, prc in volumes_and_prices:
                if vol > 0:
                    try:
                        sell_entry = SellQueue.objects.get(email=email, symbol=symbol, price=prc)
                        sell_entry.volume += vol
                        sell_entry.save()
                    except SellQueue.DoesNotExist:
                        SellQueue.objects.create(email=email, symbol=symbol, volume=vol, price=prc)

    SellQueue.objects.filter(volume__lte=0).delete()


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

    update_sell_queue(ki_api, email=Account.objects.get(email='cabs0814@naver.com'))

    sell = threading.Thread(target=trading_sell, args=(ki_api,))
    sell.start()
    buy_stock = select_buy_stocks()
    buy = threading.Thread(target=trading_buy, args=(ki_api, buy_stock,))
    buy.start()
