from DBconect import *

import smtplib
from email.mime.text import MIMEText

db = DBconect()

# db.stock_data_update_daily()
# db.stock_data_update_daily_naver()
db.bollinger()
db.triple_screen()
db.granville()

del db