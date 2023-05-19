import datetime
import FinanceDataReader
from app.database.db_connect import *


def add_stock():
    print("start add_stock")
    if datetime.datetime.now().day != 1:
        return
    df_krx = FinanceDataReader.StockListing('KRX')
    insert_set = list()
    for item in df_krx.to_dict('records'):
        insert_set.append({'symbol': item['Code'], 'name': item['Name']})
    Stock.insert_many(insert_set).on_conflict_ignore().execute()
    print(len(insert_set))


def add_stock_price_1day():
    print("start add_stock_price_1day")
    now = datetime.datetime.now()
    if now.weekday() in (5, 6):
        return
    now = now.strftime('%Y-%m-%d')
    insert_set = list()
    for stock in Stock.select(Stock.symbol):
        df_krx = FinanceDataReader.DataReader(stock.symbol, now, now)
        for idx, item in df_krx.iterrows():
            insert_set.append({'symbol': stock.symbol, 'date': idx, 'open': item['Open'], 'high': item['High'],
                               'close': item['Close'], 'low': item['Low']})
    StockPrice.insert_many(insert_set).on_conflict_ignore().execute()
    print(len(insert_set))


def add_stock_price_1week():
    print("start add_stock_price_1week")
    now = datetime.datetime.now()
    if now.weekday() in (5, 6):
        return
    week_ago = (now - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
    now = now.strftime('%Y-%m-%d')
    for stock in Stock.select(Stock.symbol):
        df_krx = FinanceDataReader.DataReader(stock.symbol, week_ago, now)
        insert_set = list()
        for idx, item in df_krx.iterrows():
            insert_set.append({'symbol': stock.symbol, 'date': idx, 'open': item['Open'], 'high': item['High'],
                               'close': item['Close'], 'low': item['Low']})
        StockPrice.insert_many(insert_set).on_conflict_ignore().execute()
        print(len(insert_set))
