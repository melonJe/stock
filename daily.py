from DBconect import *
from email.mime.text import MIMEText
import smtplib
import datetime as dt
import secret as s

db = DBconect()

db.stock_data_update_daily()
db.stock_data_update_daily_naver()

smtpName = "smtp.naver.com" #smtp 서버 주소
smtpPort = 587 #smtp 포트 번호

text =  db.bollinger() +"\n"+ db.triple_screen() +"\n"+ db.granville()

s=smtplib.SMTP( smtpName , smtpPort ) #메일 서버 연결
s.starttls() #TLS 보안 처리
s.login( s.SENDEMAIL , s.PASSWORD ) #로그인
s.sendmail( s.SENDEMAIL, s.RECVEMAIL, msg.as_string() ) #메일 전송, 문자열로 변환하여 보냅니다.
s.close() #smtp 서버 연결을 종료합니다.

del db