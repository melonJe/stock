import time
import traceback

import schedule
from app.database.db_connect import *
from app.helper import schedule_helper

if __name__ == "__main__":
    print("main.py 시작")
    DBConnect().db.create_tables([User, Stock, StockPrice, StockBuy, StockSubscription])
    schedule.every().sunday.do(schedule_helper.add_stock_price_1week)
    schedule.every().monday.do(schedule_helper.add_stock)
    schedule.every().days.at("22:00").do(schedule_helper.add_stock_price_1day)
    schedule.every().days.at("08:45").do(schedule_helper.bollinger_band)
    # schedule.every().hours.do(schedule_helper.bollinger_band)
    while True:
        schedule.run_pending()
        time.sleep(1)

# schedule.every().hour.do(job)
# schedule.every().day.at("10:30").do(job)
# schedule.every().monday.do(job)
# schedule.every().wednesday.at("13:15").do(job)
# schedule.every().minute.at(":17").do(job)
