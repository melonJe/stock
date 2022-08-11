from DBconect import *
from email.mime.text import MIMEText
import smtplib
import arrow
import secret

db = DBconect()

db.stock_data_update_daily_naver()

text = db.bollinger() + "\n" + db.triple_screen() + "\n" + db.granville()

smtp = smtplib.SMTP('smtp.naver.com', 587)
smtp.starttls()  # TLS 사용시 필요
smtp.login(secret.SENDEMAIL, secret.PASSWORD)

msg = MIMEText(text)
msg['Subject'] = arrow.now().format('YYYY년 MM월 DD일 dddd')
msg['From'] = secret.SENDEMAIL
msg['To'] = secret.RECVEMAIL
smtp.sendmail(secret.SENDEMAIL, secret.RECVEMAIL, msg.as_string())
smtp.close()  # smtp 서버 연결을 종료합니다.

del db
