import datetime
import logging
import threading
import traceback
from datetime import time
from time import sleep

import numpy as np
import pandas as pd
from ta.momentum import rsi
from ta.trend import adx
from ta.volatility import AverageTrueRange
from ta.volume import ChaikinMoneyFlowIndicator

from apis.korea_investment import KoreaInvestmentAPI
from config import setting_env
from data.models import Blacklist, Stock, StopLoss, Subscription
from services.data_handler import stop_loss_insert, get_history_table, get_country_by_symbol, add_stock_price
from utils import discord
from utils.operations import price_refine


def select_buy_stocks(country: str) -> dict:
    buy_levels = dict()
    table = get_history_table(country)

    blacklist_symbols = Blacklist.select(Blacklist.symbol)
    sub_symbols = Subscription.select(Subscription.symbol)
    stocks_query = Stock.select(Stock.symbol).where(
        (Stock.country == country)
        & (Stock.symbol.in_(sub_symbols))
        # &~(Stock.symbol.in_(blacklist_symbols))
    )
    stocks = {row.symbol for row in stocks_query}
    for symbol in stocks:
        try:
            df = pd.DataFrame(table
                              .where(table.date.between(datetime.datetime.now() - datetime.timedelta(days=365), datetime.datetime.now()) & (table.symbol == symbol))
                              .order_by(table.date))
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

            df[['high', 'low', 'close']] = df[['high', 'low', 'close']].apply(pd.to_numeric, errors='coerce')
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
                if country == "USA":
                    volume //= 100
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


def select_sell_stocks(korea_investment: KoreaInvestmentAPI) -> dict:
    owned_stocks = korea_investment.get_owned_stock_info()
    sell_levels = {}
    for stock in owned_stocks:
        table = get_history_table(get_country_by_symbol(stock.pdno))
        try:
            df = pd.DataFrame(table
                              .where(table.date.between(datetime.datetime.now() - datetime.timedelta(days=365), datetime.datetime.now()) & (table.symbol == stock.pdno))
                              .order_by(table.date))
            if len(df) < 200:
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

            sell_levels[stock.pdno] = {
                df.iloc[-1]['high']: int(stock.ord_psbl_qty) // 12,
                df.iloc[-1]['close']: int(stock.ord_psbl_qty) // 3,
                df.iloc[-1]['low']: int(stock.ord_psbl_qty) // 12
            }
        except Exception as e:
            traceback.print_exc()
            logging.error(f"Error occurred: {e}")
    return sell_levels


def trading_buy(korea_investment: KoreaInvestmentAPI, buy_levels):
    try:
        end_date = korea_investment.get_nth_open_day(3)
    except Exception as e:
        traceback.print_exc()
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
                try:
                    if country == "KOR":
                        price = price_refine(price)
                        korea_investment.buy_reserve(symbol=symbol, price=price, volume=volume, end_date=end_date)
                        money += price * volume
                    elif country == "USA":
                        price = round(price, 2)
                        logging.info(f'{stock.prdt_name} price: {price}, volume: {volume}')
                        # money += price * volume

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


def trading_sell(korea_investment: KoreaInvestmentAPI, sell_levels):
    end_date = korea_investment.get_nth_open_day(3)
    for symbol, levels in sell_levels.items():
        stock = korea_investment.get_owned_stock_info(symbol=symbol)
        if not stock:
            discord.send_message(f'Not held a stock {stock.prdt_name}')
            continue
        for price, volume in levels.items():
            if price < float(stock.pchs_avg_pric):
                price = price_refine(int(float(stock.pchs_avg_pric)), 3)
            korea_investment.sell_reserve(symbol=symbol, price=price, volume=volume, end_date=end_date)


def stop_loss_notify(korea_investment: KoreaInvestmentAPI):
    alert = set()
    while datetime.datetime.now().time() < time(15, 30, 00):
        owned_stocks = korea_investment.get_owned_stock_info()
        for item in owned_stocks:
            try:
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
                logging.error(f"Error processing item {item.pdno}: {e}")
                traceback.print_exc()

        sleep(1 * 60)


def investment_trading():
    ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_code=setting_env.ACCOUNT_CODE)
    if ki_api.check_holiday(datetime.datetime.now().strftime("%Y%m%d")):
        logging.info(f'{datetime.datetime.now()} 휴장일')
        return

    # usa_stock = select_buy_stocks(country="USA")
    # discord.send_message(f"usa_stock: {usa_stock}")
    # usa_buy = threading.Thread(target=trading_buy, args=(ki_api, usa_stock,))
    # usa_buy.start()

    stop_loss = threading.Thread(target=stop_loss_notify, args=(ki_api,))
    stop_loss.start()

    while datetime.datetime.now().time() < time(18, 15, 00):
        sleep(1 * 60)

    add_stock_price(start_date=datetime.datetime.now().strftime('%Y-%m-%d'), end_date=datetime.datetime.now().strftime('%Y-%m-%d'))
    for stock in ki_api.get_owned_stock_info():
        stop_loss_insert(stock.pdno, float(stock.pchs_avg_pric))

    sell_stock = select_sell_stocks(ki_api)
    sell = threading.Thread(target=trading_sell, args=(ki_api, sell_stock,))
    sell.start()
    buy_stock = select_buy_stocks(country="KOR")
    buy = threading.Thread(target=trading_buy, args=(ki_api, buy_stock,))
    buy.start()


if __name__ == "__main__":
    pass
    # ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_code=setting_env.ACCOUNT_CODE)
    # print(select_buy_stocks(country="KOR"))
    # print(select_sell_stocks(ki_api))
    # trading_buy(korea_investment=ki_api, buy_levels=select_buy_stocks(country="KOR"))
    # trading_sell(korea_investment=ki_api, sell_levels=select_sell_stocks(korea_investment=ki_api))
