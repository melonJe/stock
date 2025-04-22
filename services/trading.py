import datetime
import logging
import math
import threading
from time import sleep
from typing import Union

import numpy as np
import pandas
import pandas as pd
from peewee import fn
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands

from apis.korea_investment import KoreaInvestmentAPI
from config import setting_env
from data.models import Blacklist, Stock, StopLoss, Subscription, PriceHistory, PriceHistoryUS, SellQueue
from services.data_handler import stop_loss_insert, get_history_table, get_country_by_symbol, add_stock_price
from utils import discord
from utils.operations import price_refine


def select_buy_stocks(country: str = "KOR") -> dict:
    buy_levels = dict()
    anchor_date = datetime.datetime.now()
    if country == 'USA':
        anchor_date = anchor_date - datetime.timedelta(days=1)
    anchor_date = anchor_date.strftime('%Y-%m-%d')

    blacklist_symbols = Blacklist.select(Blacklist.symbol)
    sub_symbols = Subscription.select(Subscription.symbol)
    stocks_query = Stock.select(Stock.symbol).where(
        (Stock.country == country)
        & (Stock.symbol.in_(sub_symbols))
        & ~(Stock.symbol.in_(blacklist_symbols))
    )
    stocks = {row.symbol for row in stocks_query}
    for symbol in stocks:
        try:
            table = get_history_table(get_country_by_symbol(symbol))
            df = pd.DataFrame((
                list((table.select()
                      .where(table.date.between(datetime.datetime.now() - datetime.timedelta(days=365), datetime.datetime.now()) & (table.symbol == symbol))
                      .order_by(table.date)).dicts())
            ))
            if not str(df.iloc[-1]['date']) == anchor_date:  # 마지막 데이터가 오늘이 아니면 pass
                continue

            if len(df) < 200:
                continue

            # df['Vol_Avg'] = df['volume'].rolling(window=5).mean()
            # if not df.iloc[-1]['volume'] > (df.iloc[-1]['Vol_Avg'] * 1.5):
            #     continue

            bollinger = BollingerBands(close=df['close'], window=10, window_dev=2)
            df['BB_Mavg'] = bollinger.bollinger_mavg()
            df['BB_Upper'] = bollinger.bollinger_hband()
            df['BB_Lower'] = bollinger.bollinger_lband()
            if df.iloc[-1]['close'] > df.iloc[-1]['BB_Lower'] * 1.05 and df.iloc[-1]['low'] > df.iloc[-1]['BB_Lower'] * 1.05:
                continue

            # obv_indicator = OnBalanceVolumeIndicator(close=df['close'], volume=df['volume']).on_balance_volume()
            # if not obv_indicator.iloc[-1] > obv_indicator.iloc[-4]:
            #     continue

            df['RSI'] = RSIIndicator(close=df['close'], window=7).rsi()
            latest_rsi = df.iloc[-1]['RSI']
            rsi_condition = latest_rsi < 30
            macd_indicator = MACD(close=df['close'], window_fast=12, window_slow=26, window_sign=9)
            df['MACD'], df['MACD_Signal'] = macd_indicator.macd(), macd_indicator.macd_signal()
            prev, curr = df.iloc[-2], df.iloc[-1]
            macd_condition = prev['MACD'] <= prev['MACD_Signal'] and curr['MACD'] >= curr['MACD_Signal']
            if not (rsi_condition or macd_condition):
                continue

            atr = max(df.iloc[-1]['ATR5'], df.iloc[-1]['ATR10'], df.iloc[-1]['ATR20'])
            volume = int(min(100000 // atr, np.average(df['volume'][-20:]) // (atr ** (1 / 2))))
            if country == "USA":
                volume //= 1000
            buy_levels[symbol] = {
                df.iloc[-1]['low']: volume // 9 * 5,
                (df.iloc[-1]['open'] + df.iloc[-1]['close']) / 2: volume // 3,
                df.iloc[-1]['high']: volume // 9
            }
        except Exception as e:
            logging.error(f"Error occurred: {e}")
    return buy_levels


def filter_sell_stocks(df: pandas.DataFrame, volume) -> Union[dict, None]:
    if len(df) < 200:
        return None

    bollinger = BollingerBands(close=df['close'], window=10, window_dev=2)
    df['BB_Mavg'] = bollinger.bollinger_mavg()
    df['BB_Upper'] = bollinger.bollinger_hband()
    df['BB_Lower'] = bollinger.bollinger_lband()
    if df.iloc[-1]['close'] < df.iloc[-1]['BB_Upper'] * 0.95 and df.iloc[-1]['low'] < df.iloc[-1]['BB_Upper'] * 0.95:
        return None

    df['RSI'] = RSIIndicator(close=df['close'], window=7).rsi()
    latest_rsi = df.iloc[-1]['RSI']
    rsi_condition = latest_rsi > 70
    macd_indicator = MACD(close=df['close'], window_fast=12, window_slow=26, window_sign=9)
    df['MACD'] = macd_indicator.macd()
    df['MACD_Signal'] = macd_indicator.macd_signal()
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    prev_macd_condition = prev['MACD'] >= prev['MACD_Signal']
    curr_macd_condition = curr['MACD'] <= curr['MACD_Signal']
    if not (rsi_condition or (prev_macd_condition and curr_macd_condition)):
        return None

    return {
        df.iloc[-1]['high']: int(volume) // 12,
        df.iloc[-1]['close']: int(volume) // 3,
        df.iloc[-1]['low']: int(volume) // 12
    }


def select_sell_korea_stocks(korea_investment: KoreaInvestmentAPI) -> dict:
    owned_stocks = korea_investment.get_korea_owned_stock_info()
    sell_levels = {}
    for stock in owned_stocks:
        try:
            df = pd.DataFrame((
                list((PriceHistory.select()
                      .where(PriceHistory.date.between(datetime.datetime.now() - datetime.timedelta(days=365), datetime.datetime.now()) & (PriceHistory.symbol == stock.pdno))
                      .order_by(PriceHistory.date)).dicts())
            ))
            data = filter_sell_stocks(df, stock.ord_psbl_qty)
            if data:
                sell_levels[stock.pdno] = data
        except Exception as e:
            logging.error(f"Error occurred: {e}")
    return sell_levels


def select_sell_overseas_stocks(korea_investment: KoreaInvestmentAPI, country: str = "USA") -> dict:
    owned_stocks = korea_investment.get_oversea_owned_stock_info(country=country)
    sell_levels = {}
    for stock in owned_stocks:
        try:
            df = pd.DataFrame((
                list((PriceHistoryUS.select()
                      .where(PriceHistoryUS.date.between(datetime.datetime.now() - datetime.timedelta(days=365), datetime.datetime.now()) & (PriceHistoryUS.symbol == stock.ovrs_pdno))
                      .order_by(PriceHistoryUS.date)).dicts())
            ))
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['close'] = df['close'].astype(float)
            df['low'] = df['low'].astype(float)

            data = filter_sell_stocks(df, stock.ord_psbl_qty)
            if data:
                sell_levels[stock.pdno] = data
        except Exception as e:
            logging.error(f"Error occurred: {e}")
    return sell_levels


def trading_buy(korea_investment: KoreaInvestmentAPI, buy_levels):
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
            stop_loss_insert(symbol, min(levels.keys()) * 0.95)
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


def update_sell_queue(ki_api: KoreaInvestmentAPI):
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    response_data = ki_api.get_stock_order_list(start_date=today_str, end_date=today_str)

    sell_queue_entries = {}
    for trade in response_data:
        stock = Stock.get(Stock.symbol == trade.pdno)
        table = get_history_table(get_country_by_symbol(stock.symbol))
        volume = int(trade.tot_ccld_qty)
        price = int(trade.avg_prvs)
        trade_type = trade.sll_buy_dvsn_cd

        if trade_type == "02":
            df = pd.DataFrame(
                list(table.select().where(
                    (table.date.between(datetime.datetime.now() - datetime.timedelta(days=600), datetime.datetime.now())) &
                    (table.symbol == stock.symbol)
                ).order_by(table.date).dicts())
            )
            df['ma60'] = df['close'].rolling(window=60).mean()
            volumes_and_prices = []
            if stock.country == 'KOR':
                volumes_and_prices = [
                    (volume - int(volume * 0.5), price_refine(math.ceil(price * 1.105))),
                    (int(volume * 0.5), price_refine(math.ceil(price * 1.255)))
                ]
            elif stock.country == 'USA':
                volumes_and_prices = [
                    (volume - int(volume * 0.5), round(float(stock.pchs_avg_pric) * 1.105, 2)),
                    (int(volume * 0.5), round(float(stock.pchs_avg_pric) * 1.255, 2))
                ]

            for vol, prc in volumes_and_prices:
                if vol > 0:
                    sell_queue_entries[(stock.symbol, prc)] = sell_queue_entries.get((stock.symbol, prc), 0) + vol

        elif trade_type == "01":
            sell_queue_entries[(stock.symbol, price)] = sell_queue_entries.get((stock.symbol, price), 0) - volume

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

    owned_stock_info = ki_api.get_owned_stock_info()
    for stock in owned_stock_info:
        stock_db = Stock.get(Stock.symbol == stock.pdno)
        table = get_history_table(get_country_by_symbol(stock_db.symbol))
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

            df = pd.DataFrame(
                list(table.select().where(
                    (table.date.between(datetime.datetime.now() - datetime.timedelta(days=600), datetime.datetime.now())) &
                    (table.symbol == stock_db.symbol)
                ).order_by(table.date).dicts())
            )
            df['ma60'] = df['close'].rolling(window=60).mean()

            volumes_and_prices = []
            if stock_db.country == 'KOR':
                volumes_and_prices = [
                    (additional_volume - int(additional_volume * 0.5), price_refine(math.ceil(avg_price * 1.105))),
                    (int(additional_volume * 0.5), price_refine(math.ceil(avg_price * 1.255)))
                ]
            elif stock_db.country == 'USA':
                volumes_and_prices = [
                    (additional_volume - int(additional_volume * 0.5), round(float(avg_price * 1.105))),
                    (int(additional_volume * 0.5), round(float(avg_price * 1.255)))
                ]
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
    ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_code=setting_env.ACCOUNT_CODE)
    if ki_api.check_holiday(datetime.datetime.now().strftime("%Y%m%d")):
        logging.info(f'{datetime.datetime.now()} 휴장일')
        return

    stop_loss = threading.Thread(target=stop_loss_notify, args=(ki_api,))
    stop_loss.start()

    while datetime.datetime.now().time() < datetime.time(18, 15, 00):
        sleep(1 * 60)

    update_sell_queue(ki_api=ki_api)
    add_stock_price(country="KOR", start_date=datetime.datetime.now() - datetime.timedelta(days=5), end_date=datetime.datetime.now())
    for stock in ki_api.get_owned_stock_info():
        stop_loss_insert(stock.pdno, float(stock.pchs_avg_pric))

    sell_stock = select_sell_korea_stocks(ki_api)
    sell_queue = {}
    for sell in SellQueue.select().join(Stock, on=(SellQueue.symbol == Stock.symbol)).where(Stock.country == 'KOR'):
        if sell.symbol not in sell_queue.keys():
            sell_queue[sell.symbol] = {}
        sell_queue[sell.symbol][sell.price] = sell.volume
    sell_queue.update(sell_stock)
    sell = threading.Thread(target=trading_sell, args=(ki_api, sell_queue,))
    sell.start()

    buy_stock = select_buy_stocks(country="KOR")
    logging.info(f'buy_stock data: {buy_stock}')
    buy = threading.Thread(target=trading_buy, args=(ki_api, buy_stock,))
    buy.start()


def usa_trading():
    ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_code=setting_env.ACCOUNT_CODE)

    usa_stock = select_buy_stocks(country="USA")
    usa_buy = threading.Thread(target=trading_buy, args=(ki_api, usa_stock,))
    usa_buy.start()

    sell_stock = select_sell_overseas_stocks(ki_api)
    sell_queue = {}
    for sell in SellQueue.select().join(Stock, on=(SellQueue.symbol == Stock.symbol)).where(Stock.country == 'USA'):
        if sell.symbol not in sell_queue.keys():
            sell_queue[sell.symbol] = {}
        sell_queue[sell.symbol][sell.price] = sell.volume
    sell_queue.update(sell_stock)
    sell = threading.Thread(target=trading_sell, args=(ki_api, sell_queue,))
    sell.start()


if __name__ == "__main__":
    ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_code=setting_env.ACCOUNT_CODE)
    update_sell_queue(ki_api=ki_api)
    add_stock_price(country="KOR", start_date=datetime.datetime.now() - datetime.timedelta(days=5), end_date=datetime.datetime.now())
    for stock in ki_api.get_owned_stock_info():
        stop_loss_insert(stock.pdno, float(stock.pchs_avg_pric))

    sell_stock = select_sell_korea_stocks(ki_api)
    sell_queue = {}
    for sell in SellQueue.select().join(Stock, on=(SellQueue.symbol == Stock.symbol)).where(Stock.country == 'KOR'):
        if sell.symbol not in sell_queue.keys():
            sell_queue[sell.symbol] = {}
        sell_queue[sell.symbol][sell.price] = sell.volume
    sell_queue.update(sell_stock)
    sell = threading.Thread(target=trading_sell, args=(ki_api, sell_queue,))
    sell.start()
    buy_stock = select_buy_stocks(country="KOR")
    logging.info(f'buy_stock data: {buy_stock}')
    buy = threading.Thread(target=trading_buy, args=(ki_api, buy_stock,))
    buy.start()
