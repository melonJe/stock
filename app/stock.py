import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import schedule
import time

from database.db_helper import DBHelper


def add_stock():
    df_krx = fdr.StockListing('KRX')
    MySQLHelper.execute_query('insert ignore into from stock ', )
    db = DBHelper.getInstance()
    # Execute a query and retrieve the results
    result = db.execute_query("SELECT * FROM mytable")
    # Print the results
    print(result)


def add_stock_price():
    df_krx = fdr.StockListing('KRX')

# schedule.every().minutes.do(job)
# schedule.every().hour.do(job)
# schedule.every().day.at("10:30").do(job)
# schedule.every().monday.do(job)
# schedule.every().wednesday.at("13:15").do(job)
# schedule.every().minute.at(":17").do(job)
#
# while True:
#     schedule.run_pending()
#     time.sleep(1)
AddStock()