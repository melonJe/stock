import FinanceDataReader

from app.database.db_connect import Stock, StockPrice


def add_stock_price(day):
    day = day.strftime('%Y-%m-%d')
    insert_set = list()
    for stock in Stock.select(Stock.symbol):
        df_krx = FinanceDataReader.DataReader(stock.symbol, day, day)
        for idx, item in df_krx.iterrows():
            insert_set.append({'symbol': stock.symbol, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']})
    StockPrice.insert_many(insert_set).on_conflict_ignore().execute()
    print(len(insert_set))
