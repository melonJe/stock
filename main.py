from DBconect import DBconect

db = DBconect()

# db.stock_data_update_daily()
# db.stock_data_update_daily_naver()
print(db.bollinger() + "\n" + db.triple_screen() + "\n" + db.granville())

del db