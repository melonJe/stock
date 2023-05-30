import FinanceDataReader
import pandas as pd
from datetime import datetime, timedelta
from app.database.db_connect import *
from app.service import stock


def add_stock():
    print("start add_stock")
    if datetime.now().day != 1:
        return
    df_krx = FinanceDataReader.StockListing('KRX')
    insert_set = list()
    for item in df_krx.to_dict('records'):
        insert_set.append({'symbol': item['Code'], 'name': item['Name']})
    Stock.insert_many(insert_set).on_conflict_replace().execute()
    print(len(insert_set))


def add_stock_price_1day():
    print("start add_stock_price_1day")
    now = datetime.now()
    if now.weekday() in (5, 6):
        return
    now = now.strftime('%Y-%m-%d')
    insert_set = list()
    for stock_item in Stock.select(Stock.symbol):
        df_krx = FinanceDataReader.DataReader(stock_item.symbol, now, now)
        for idx, item in df_krx.iterrows():
            insert_set.append({'symbol': stock_item.symbol, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']})
    StockPrice.insert_many(insert_set).on_conflict_replace().execute()
    print(len(insert_set))


def add_stock_price_1week():
    print("start add_stock_price_1week")
    now = datetime.now()
    if now.weekday() in (5, 6):
        return
    week_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')
    now = now.strftime('%Y-%m-%d')
    insert_set = list()
    for stock_item in Stock.select(Stock.symbol):
        df_krx = FinanceDataReader.DataReader(stock_item.symbol, week_ago, now)
        for idx, item in df_krx.iterrows():
            insert_set.append({'symbol': stock_item.symbol, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']})
    StockPrice.insert_many(insert_set).on_conflict_replace().execute()
    print(len(insert_set))


def add_stock_price_all():
    print("start add_stock_price_all")
    for stock_item in Stock.select(Stock.symbol):
        df_krx = FinanceDataReader.DataReader(stock_item.symbol)
        insert_set = list()
        for idx, item in df_krx.iterrows():
            insert_set.append({'symbol': stock_item.symbol, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']})
        StockPrice.insert_many(insert_set).on_conflict_replace().execute()
        print(len(insert_set))


def bollinger_band():
    decision = {'buy': [], 'sell': []}
    stock.add_stock_price(datetime.now() - timedelta(days=1))
    for stock_item in Stock.select(Stock.symbol):
        query = StockPrice.select().limit(25).where(StockPrice.symbol == stock_item.symbol).order_by(StockPrice.date.desc())
        data = pd.DataFrame(list(query.dicts())).sort_values(by='date', ascending=True)
        if data.iloc[-1]['decision'] == 'buy':
            decision['buy'].append(stock_item.name)
        if data.iloc[-1]['decision'] == 'sell':
            decision['sell'].append(stock_item.name)
    print(decision)
    return decision
