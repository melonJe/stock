import datetime
import schedule
import FinanceDataReader
from app.database.db_connect import *


def add_stock():
    if datetime.datetime.now().day != 1:
        return
    df_krx = FinanceDataReader.StockListing('KRX')
    insert_list = []
    for item in df_krx.to_dict('records'):
        insert_list.append({'symbol': item['Code'], 'name': item['Name']})
    Stock.insert_many(insert_list).on_conflict_ignore().execute()


def add_stock_price_1day():
    now = datetime.datetime.now()
    if now.weekday() in (5, 6):
        return
    insert_list = []
    for stock in Stock.select(Stock.symbol):
        df_krx = FinanceDataReader.DataReader(stock.symbol, now.strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d'))
        for idx, item in df_krx.iterrows():
            insert_list.append(
                {'symbol': stock.symbol, 'date': idx, 'open': item['Open'], 'high': item['High'],
                 'close': item['Close'], 'low': item['Low']})
    StockPrice.insert_many(insert_list).on_conflict_ignore().execute()


def add_stock_price_1week():
    now = datetime.datetime.now()
    if now.weekday() in (5, 6):
        return
    for stock in Stock.select(Stock.symbol):
        df_krx = FinanceDataReader.DataReader(stock.symbol, (now - datetime.timedelta(days=7)).strftime('%Y-%m-%d'),
                                              now.strftime('%Y-%m-%d'))
        insert_list = []
        for idx, item in df_krx.iterrows():
            insert_list.append(
                {'symbol': stock.symbol, 'date': idx, 'open': item['Open'], 'high': item['High'],
                 'close': item['Close'], 'low': item['Low']})
        StockPrice.insert_many(insert_list).on_conflict_ignore().execute()


if __name__ == "__main__":
    DBConnect().db.create_tables([User, Stock, StockPrice, StockBuy, StockSubscription])
    schedule.every().monday.do(add_stock)
    schedule.every().monday.do(add_stock_price_1day)
    schedule.every().sunday.do(add_stock_price_1week)
    while True:
        schedule.run_pending()
        time.sleep(1)
        break

# schedule.every().hour.do(job)
# schedule.every().day.at("10:30").do(job)
# schedule.every().monday.do(job)
# schedule.every().wednesday.at("13:15").do(job)
# schedule.every().minute.at(":17").do(job)
