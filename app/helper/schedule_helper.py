import traceback

import FinanceDataReader
import pandas as pd
from datetime import datetime, timedelta
from app.database.db_connect import *
from app.helper import discord
from app.service import stock, bollingerBands


def add_stock():
    if datetime.now().day != 1:
        return
    df_krx = FinanceDataReader.StockListing('KRX')
    insert_set = list()
    for item in df_krx.to_dict('records'):
        insert_set.append({'symbol': item['Code'], 'name': item['Name']})
        print(item['Name'])
    Stock.insert_many(insert_set).on_conflict_ignore().execute()
    print('add_stock')


def add_stock_price_1day():
    now = datetime.now()
    if now.weekday() in (5, 6):
        return
    now = now.strftime('%Y-%m-%d')
    insert_set = list()
    for stock_item in Stock.select(Stock.symbol):
        df_krx = FinanceDataReader.DataReader(stock_item.symbol, now, now)
        for idx, item in df_krx.iterrows():
            insert_set.append({'symbol': stock_item.symbol, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']})
    StockPrice.insert_many(insert_set).on_conflict_ignore().execute()
    print(f'add_stock_price_1day   {now}')


def add_stock_price_1week():
    now = datetime.now()
    if now.weekday() in (5, 6):
        return
    week_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')
    now = now.strftime('%Y-%m-%d')
    for stock_item in Stock.select(Stock.symbol):
        insert_set = list()
        df_krx = FinanceDataReader.DataReader(stock_item.symbol, week_ago, now)
        for idx, item in df_krx.iterrows():
            insert_set.append({'symbol': stock_item.symbol, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']})
        StockPrice.insert_many(insert_set).on_conflict_ignore().execute()
    print(f'add_stock_price_1week   {now}')


def add_stock_price_all():
    for stock_item in Stock.select(Stock.symbol):
        df_krx = FinanceDataReader.DataReader(stock_item.symbol)
        insert_set = list()
        for idx, item in df_krx.iterrows():
            insert_set.append({'symbol': stock_item.symbol, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']})
        StockPrice.insert_many(insert_set).on_conflict_ignore().execute()
    print(f'add_stock_price_all')


def bollinger_band():
    if datetime.now().weekday() in (5, 6):
        return
    decision = {'buy': set(), 'sell': set()}
    # for stock_item in Stock.select(Stock.symbol):
    for stock_item in StockSubscription.select(StockSubscription.symbol).where(StockSubscription.email == 'cabs0814@naver.com'):
        try:
            name = Stock.get(Stock.symbol == stock_item.symbol).name
            data = list(StockPrice.select().limit(25).where((StockPrice.date >= (datetime.now() - timedelta(days=50))) & (StockPrice.symbol == stock_item.symbol))
                        .order_by(StockPrice.date.desc()).dicts())
            if not data:
                continue
            data = pd.DataFrame(data).sort_values(by='date', ascending=True)
            bollingerBands.bollinger_band(data)
            if data.iloc[-1]['decision'] == 'buy':
                decision['buy'].add(name)
            if data.iloc[-1]['decision'] == 'sell':
                decision['sell'].add(name)
            del data, name
            # TODO: custum exception
        except:
            discord.error_message("stock_db\n" + str(traceback.print_exc()))
    sell_set = decision['sell'] & set(StockBuy.select().where(StockBuy.email == 'cabs0814@naver.com'))
    # print(f"{datetime.now().date()}\nbuy : {decision['buy']}\nsell : {decision['sell']}\nsell from buy : {sell_set}")
    discord.send_message(f"{datetime.now().date()}\nbuy : {decision['buy']}\nsell : {decision['sell']}\nsell from buy : {sell_set}")
    return decision


# add_stock_price_1day()
print(bollinger_band())
