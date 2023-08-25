import time
import schedule
from app.database.db_connect import *
from app.helper import schedule_helper

if __name__ == "__main__":
    print(f"main.py 시작 {datetime.now()}")
    schedule.every().sunday.do(schedule_helper.add_stock_price_1week)
    schedule.every().monday.do(schedule_helper.add_stock)
    schedule.every().day.at("18:00").do(schedule_helper.add_stock_price_1day)
    schedule.every().day.at("20:00").do(schedule_helper.alert)
    schedule.every().day.at("08:30").do(schedule_helper.alert)
    while True:
        schedule.run_pending()
        time.sleep(0.9)

# schedule.every().hour.do(job)
# schedule.every().day.at("10:30").do(job)
# schedule.every().monday.do(job)
# schedule.every().wednesday.at("13:15").do(job)
# schedule.every().minute.at(":17").do(job)
