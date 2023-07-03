import time
import schedule
from app.database.db_connect import *
from app.helper import schedule_helper

if __name__ == "__main__":
    print("main.py 시작")
    print(f"DB_HOST {config.DB_HOST}")
    print(f"DB_PORT {config.DB_PORT}")
    print(f"DB_NAME {config.DB_NAME}")
    print(f"DB_USER {config.DB_USER}")
    print(f"DB_PASS {config.DB_PASS}")
    DBHelper().db.create_tables([User, Stock, StockPrice, StockBuy, StockSubscription])
    schedule.every().sunday.do(schedule_helper.add_stock_price_1week)
    schedule.every().monday.do(schedule_helper.add_stock)
    schedule.every().day.at("22:00").do(schedule_helper.add_stock_price_1day)
    schedule.every().day.at("07:00").do(schedule_helper.bollinger_band)
    while True:
        schedule.run_pending()
        time.sleep(0.9)
        # TODO DB 연결을 끊김을 확인할 다른 방법 찾기
        if DBHelper().db.is_closed():
            DBHelper().db.connect()

# schedule.every().hour.do(job)
# schedule.every().day.at("10:30").do(job)
# schedule.every().monday.do(job)
# schedule.every().wednesday.at("13:15").do(job)
# schedule.every().minute.at(":17").do(job)
