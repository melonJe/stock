import datetime
import time
import schedule

from app.database.db_connect import *
import FinanceDataReader


def add_stock():
    if datetime.datetime.now().day != 1:
        return
    df_krx = FinanceDataReader.StockListing('KRX')
    insert_list = []
    for item in df_krx.to_dict('records'):
        insert_list.append({'symbol': item['Code'], 'name': item['Name']})
    Stock.insert_many(insert_list).on_conflict('REPLACE').execute()

    # .execute_query('insert ignore into from stock ', )
    # db = DBHelper.getInstance()
    # Execute a query and retrieve the results
    # result = db.execute_query("SELECT * FROM mytable")
    # Print the results
    # print(result)


def add_stock_price():
    df_krx = FinanceDataReader.DataReader('068270', '2023-05-12')
    print(df_krx)


if __name__ == "__main__":
    DBConnect().db.create_tables([User, Stock, StockPrice, StockBuy, StockSubscription])
    add_stock()
    schedule.every().days.do(add_stock)
    # schedule.every().hour.do(job)
    # schedule.every().day.at("10:30").do(job)
    # schedule.every().monday.do(job)
    # schedule.every().wednesday.at("13:15").do(job)
    # schedule.every().minute.at(":17").do(job)
    while True:
        schedule.run_pending()
        time.sleep(1)
        break
