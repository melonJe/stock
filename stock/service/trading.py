import logging
import threading
import traceback
from datetime import datetime, time, timedelta
from time import sleep

import numpy as np
import pandas as pd
from django.db.models import Q, Sum
from ta.volatility import AverageTrueRange
from ta.volume import ChaikinMoneyFlowIndicator

from stock.discord import discord
from stock.korea_investment.api import KoreaInvestmentAPI
from stock.korea_investment.trading_operations import price_refine, reserve_sell_stock, reserve_buy_stock
from stock.models import Account, SellQueue, Stock, Subscription, PriceHistory, StopLoss, Blacklist
from .data_handler import stop_loss_insert, add_stock_price
from .. import setting_env


def select_buy_stocks() -> dict:
    result = dict()
    try:
        stocks = set(x['symbol'] for x in Subscription.objects.exclude(Q(symbol__in=Blacklist.objects.values_list('symbol', flat=True))).select_related("symbol").values('symbol'))
        buy = dict()
        sieve = dict()
        for symbol in stocks:
            df = pd.DataFrame(PriceHistory.objects.filter(date__range=[datetime.now() - timedelta(days=550), datetime.now()], symbol=symbol).order_by('date').values())
            if len(df) < 300:
                continue

            df['ma60'] = df['close'].rolling(window=60).mean()
            if df.iloc[-1]['ma60'] > df.iloc[-1]['low']:
                continue

            df['ma240'] = df['close'].rolling(window=240).mean()
            df['ma120'] = df['close'].rolling(window=120).mean()
            last_3_days = df[-3:]
            condition1 = np.any(last_3_days['ma240'] > last_3_days['close'])
            condition2 = np.any(last_3_days['ma120'] > last_3_days['close'])
            if condition1 or condition2:
                continue

            last_10_days = df[-10:]
            condition1 = np.all(last_10_days['ma240'] < last_10_days['close'])
            condition2 = np.all(last_10_days['ma120'] < last_10_days['close'])
            if condition1 and condition2:
                continue

            df['ma20'] = df['close'].rolling(window=20).mean()
            df['ma10'] = df['close'].rolling(window=10).mean()
            if not (df.iloc[-1]['ma60'] < df.iloc[-1]['ma20'] < df.iloc[-1]['ma10'] < df.iloc[-1]['close']):
                continue

            df['CMF'] = ChaikinMoneyFlowIndicator(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), volume=df['volume'].astype('float64')).chaikin_money_flow()
            if df.iloc[-1]['CMF'] > 0.25:
                df['ATR5'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=5).average_true_range()
                df['ATR10'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=10).average_true_range()
                df['ATR20'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=20).average_true_range()
                atr = max(df.iloc[-1]['ATR5'], df.iloc[-1]['ATR10'], df.iloc[-1]['ATR20'])
                volume = min(int((10000000 / (100 * atr))), int(np.min(df['volume'][-5:]) / 100))
                buy[symbol] = volume
                sieve[symbol] = df.iloc[-1]['CMF']
        for x in list(dict(sorted(sieve.items(), key=lambda item: item[1], reverse=True)).keys()):
            result[x] = buy[x]
    except Exception as e:
        traceback.print_exc()
        logging.error(f"Error occurred: {e}")
    return result


def trading_buy(ki_api: KoreaInvestmentAPI, buy: dict):
    try:
        account = ki_api.get_account_info()
    except Exception as e:
        traceback.print_exc()
        logging.error(f"Error occurred while getting account info: {e}")
        return

    try:
        end_date = ki_api.get_nth_open_day(3)
    except Exception as e:
        traceback.print_exc()
        logging.error(f"Error occurred while getting nth open day: {e}")
        return

    money = 0

    for symbol, volume in buy.items():
        try:
            stock = ki_api.get_owned_stock_info(symbol)
            df = pd.DataFrame(PriceHistory.objects.filter(date__range=[datetime.now() - timedelta(days=100), datetime.now()], symbol=symbol).order_by('date').values())

            if df.empty:
                logging.error(f"No price history found for symbol: {symbol}")
                continue
            elif len(df) < 20:
                logging.error(f"Not enough price history for symbol: {symbol}")
                continue

            stop_loss_insert(symbol)
            df['ma5'] = df['close'].rolling(window=5).mean()
            df['ma10'] = df['close'].rolling(window=10).mean()
            df['ma20'] = df['close'].rolling(window=20).mean()

            if stock:
                continue

            last_row = df.iloc[-1]
            for price in (price_refine(price) for price in [last_row['close'] + last_row['open'], last_row['ma5'], last_row['ma10'], last_row['ma20']]):
                try:
                    reserve_buy_stock(ki_api=ki_api, symbol=symbol, price=price, volume=int(volume * 0.3), end_date=end_date)
                    money += price * int(volume * 0.3)
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


def update_sell_queue(ki_api: KoreaInvestmentAPI, email: Account):
    today_str = datetime.now().strftime("%Y%m%d")
    response_data = ki_api.get_stock_order_list(start_date=today_str, end_date=today_str)

    if not response_data:
        logging.info("Failed to retrieve sell data")
        return

    sell_queue_entries = {}
    for trade in response_data:
        symbol = Stock.objects.get(symbol=trade.pdno)
        volume = int(trade.tot_ccld_qty)
        price = int(trade.avg_prvs)
        trade_type = trade.sll_buy_dvsn_cd

        if trade_type == "02":
            volumes_and_prices = [
                (int(volume * 0.5), price_refine(int(price * 1.1))),
                (int(volume * 0.3), price_refine(int(price * 1.2))),
                (volume - int(volume * 0.5) - int(volume * 0.3), price_refine(int(price * 1.5)))
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

            volumes_and_prices = [
                (int(additional_volume * 0.5), price_refine(int(avg_price * 1.1))),
                (int(additional_volume * 0.3), price_refine(int(avg_price * 1.2))),
                (additional_volume - int(additional_volume * 0.5) - int(additional_volume * 0.3), price_refine(int(avg_price * 1.5)))
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


def trading_sell(ki_api: KoreaInvestmentAPI):
    end_date = ki_api.get_nth_open_day(1)
    queue_entries = SellQueue.objects.filter(email="cabs0814@naver.com")
    for entry in queue_entries:
        stock = ki_api.get_owned_stock_info(entry.symbol.symbol)
        if not stock:
            discord.send_message(f'Not held a stock {entry.symbol.company_name}')
            continue
        sell_price = price_refine(entry.price)
        if sell_price < float(stock.pchs_avg_pric):
            discord.send_message(f'Sell {stock.prdt_name} below average purchase price: {sell_price}')

        reserve_sell_stock(ki_api, symbol=entry.symbol.symbol, price=sell_price, volume=entry.volume, end_date=end_date)


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
                    stop_loss_insert(item.pdno)
                    continue
                if stock.price < int(item.prpr):
                    continue
                discord.send_message(f"{item.prdt_name} 판매 권유")
                logging.info(f"{item.prdt_name} 판매 권유")
                Subscription.objects.filter(symbol=item.pdno).delete()
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
        stop_loss_insert(stock.pdno)

    while datetime.now().time() < time(16, 00, 30):
        sleep(1 * 60)

    update_sell_queue(ki_api, email=Account.objects.get(email='cabs0814@naver.com'))

    sell = threading.Thread(target=trading_sell, args=(ki_api,))
    sell.start()
    buy_stock = select_buy_stocks()
    buy = threading.Thread(target=trading_buy, args=(ki_api, buy_stock,))
    buy.start()
