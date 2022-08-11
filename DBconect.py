from time import strptime
from bs4 import BeautifulSoup as bs
import requests
import pandas as pd
import pymysql
import datetime as dt
import stock_API as API
import secret

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)
pd.set_option('display.max_colwidth', None)


class DBconect:
    def __init__(self):
        self.conn = pymysql.connect(
            user=secret.DBUSER,
            passwd=secret.DBPASS,
            host=secret.HOST,
            port=secret.PORT,
            db=secret.DBNAME,
            charset='utf8'
        )

    def __del__(self):
        self.conn.close()

    def last_update(self):
        with self.conn.cursor() as cursor:
            sql = "SELECT basDt FROM latest_time_data"
            cursor.execute(sql)
            return cursor.fetchone()[0]

    def stock_criteria(self, data, srtnCd):
        with self.conn.cursor() as cursor:
            if srtnCd:
                select_sql = 'SELECT srtnCd,basDt,hipr,clpr,lopr,trqu from stock_price_data where srtnCd=%s and basDt<(select basDt from latest_time_data) ORDER BY basDt DESC LIMIT 245'
                cursor.execute(select_sql, srtnCd)
                data = pd.concat([pd.DataFrame(cursor.fetchall(), columns=('srtnCd', 'basDt', 'hipr', 'clpr', 'lopr', 'trqu')).sort_values(by='basDt'), data])
            data['ema5'] = data['clpr'].ewm(span=5, min_periods=5).mean()
            data['ema20'] = data['clpr'].ewm(span=20, min_periods=20).mean()
            data['ema60'] = data['clpr'].ewm(span=60, min_periods=60).mean()
            data['ema120'] = data['clpr'].ewm(span=120, min_periods=120).mean()
            data['ema240'] = data['clpr'].ewm(span=240, min_periods=240).mean()
            data['PMF'] = 0
            data['NMF'] = 0
            data['perb'] = (data['clpr'] - data['clpr'].rolling(window=20).mean() + 2 * data['clpr'].rolling(window=20).std()) / (4 * data['clpr'].rolling(window=20).std())
            for i in range(1, len(data)):
                if data['clpr'].values[i - 1] < data['clpr'].values[i]:
                    data['PMF'].values[i] = data['clpr'].values[i] * data['trqu'].values[i]
                else:
                    data['NMF'].values[i] = data['clpr'].values[i] * data['trqu'].values[i]
            data['MFI'] = 100 - (100 / (1 + data['PMF'].rolling(window=10).std() / data['NMF'].rolling(window=10).std()))
            data['max_hipr'] = data['hipr'].rolling(window=14).max()
            data['min_lopr'] = data['lopr'].rolling(window=14).min()
            data['fast_k'] = (data['clpr'] - data['min_lopr']) / (data['max_hipr'] - data['min_lopr']) * 100
            data['slow_d'] = data['fast_k'].rolling(window=3).mean()
            return data[['srtnCd', 'basDt', 'hipr', 'clpr', 'lopr', 'trqu', 'ema5', 'ema20', 'ema60', 'ema120', 'ema240', 'PMF', 'NMF', 'perb', 'MFI', 'slow_d']]

    def stock_data_update_daily_naver(self):
        with self.conn.cursor() as cursor:
            select_sql = 'SELECT srtnCd FROM saved_srtnCd'
            cursor.execute(select_sql)
            stocks = [x[0] for x in cursor.fetchall()]
            insert_sql = "REPLACE INTO stock_price_data(srtnCd,basDt,hipr,clpr,lopr,trqu,ema5,ema20,ema60,ema120,ema240,PMF,NMF,perb,MFI,slow_d) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            answer = pd.DataFrame()
            for srtnCd in stocks:
                url = 'https://finance.naver.com/item/sise.naver?code=' + srtnCd
                html = requests.get(url).text
                soup = bs(html, 'html.parser')
                tags = soup.findAll('dd')
                data = pd.DataFrame([[tags[2].text.split(' ')[1], strptime(soup.findAll('em', attrs={'class': 'date'})[0].text.split(' ')[0], '%Y.%m.%d'), tags[6].text.split(' ')[1].replace(',', ''), tags[3].text.split(' ')[1].replace(',', ''),
                                      tags[8].text.split(' ')[1].replace(',', ''), tags[10].text.split(' ')[1].replace(',', '')]], columns=['srtnCd', 'basDt', 'hipr', 'clpr', 'lopr', 'trqu']).astype({'clpr': 'int64', 'trqu': 'int64'})
                data = self.stock_criteria(data, srtnCd)
                answer = pd.concat([answer, data[-1:]])
            if not answer.empty:
                answer = answer.fillna(0)
                cursor.executemany(insert_sql, answer.values.tolist())
                self.conn.commit()

    def get_buy_0_or_1(self):
        with self.conn.cursor() as cursor:
            select_sql = 'SELECT srtnCd FROM saved_srtnCd WHERE buy=0 or buy=1'
            cursor.execute(select_sql)
            return [x[0] for x in cursor.fetchall()]

    def bollinger(self):
        buy = set()
        sell = set()
        with self.conn.cursor() as cursor:
            stocks = self.get_buy_0_or_1()
            select_sql = 'SELECT a.*,saved_srtnCd.itmsNm,saved_srtnCd.buy FROM (select srtnCd,basDt,hipr,clpr,lopr,trqu,perb,MFI from stock_price_data where srtnCd=%s) as a JOIN saved_srtnCd ON a.srtnCd=saved_srtnCd.srtnCd ORDER BY basDt DESC LIMIT 1'
            for x in stocks:
                cursor.execute(select_sql, x)
                data = pd.DataFrame(cursor.fetchall(), columns=['srtnCd', 'basDt', 'hipr', 'clpr', 'lopr', 'trqu', 'perb', 'MFI', 'itmsNm', 'buy'])
                if data['buy'].values[-1] == 0:
                    if 0.8 < data['perb'].values[-1] and data['MFI'].values[-1] > 80:
                        buy.add(data['itmsNm'].values[-1])
                elif data['buy'].values[-1] == 1:
                    if 0.2 > data['perb'].values[-1] and data['MFI'].values[-1] < 20:
                        sell.add(data['srtnCd'].values[-1])
        return 'bollinger 매수 : ' + str(buy) + '\nbollinger 매도 : ' + str(sell)

    def triple_screen(self):
        buy = set()
        sell = set()
        with self.conn.cursor() as cursor:
            stocks = stocks = self.get_buy_0_or_1()
            select_sql = 'SELECT a.*,saved_srtnCd.itmsNm,saved_srtnCd.buy FROM (select srtnCd,basDt,hipr,clpr,lopr,trqu,ema120,slow_d from stock_price_data where srtnCd=%s) as a JOIN saved_srtnCd ON a.srtnCd=saved_srtnCd.srtnCd ORDER BY basDt DESC LIMIT 2'
            for x in stocks:
                cursor.execute(select_sql, x)
                data = pd.DataFrame(cursor.fetchall(), columns=['srtnCd', 'basDt', 'hipr', 'clpr', 'lopr', 'trqu', 'ema120', 'slow_d', 'itmsNm', 'buy']).sort_values(by='basDt')
                if data['buy'].values[-1] == 0:
                    if data['ema120'].values[-2] < data['ema120'].values[-1] and data['slow_d'].values[-1] < 15:
                        buy.add(data['itmsNm'].values[-1])
                elif data['buy'].values[-1] == 1:
                    if data['ema120'].values[-2] > data['ema120'].values[-1] and data['slow_d'].values[-1] > 70:
                        sell.add(data['itmsNm'].values[-1])
        return 'triple_screen 매수 : ' + str(buy) + '\ntriple_screen 매도 : ' + str(sell)

    def granville(self):
        buy = set()
        # sell = set()
        with self.conn.cursor() as cursor:
            stocks = stocks = self.get_buy_0_or_1()
            select_sql = 'SELECT a.*,saved_srtnCd.itmsNm,saved_srtnCd.buy FROM (select srtnCd,basDt,hipr,clpr,lopr,trqu,ema120 from stock_price_data where srtnCd=%s) as a JOIN saved_srtnCd ON a.srtnCd=saved_srtnCd.srtnCd ORDER BY basDt DESC LIMIT 30'
            for x in stocks:
                cursor.execute(select_sql, x)
                data = pd.DataFrame(cursor.fetchall(), columns=['srtnCd', 'basDt', 'hipr', 'clpr', 'lopr', 'trqu', 'ema120', 'itmsNm', 'buy']).sort_values(by='basDt')
                data = data.sort_values(by='basDt', ascending=True)
                if data['buy'].values[-1] == 0:
                    if data['lopr'].values[-1] <= data['ema120'].values[-1] <= data['hipr'].values[-1]:
                        for i in range(-2, -30, -1):
                            if -21 < i:
                                if data['ema120'].values[i] <= data['hipr'].values[i]:
                                    break
                            else:
                                if data['ema120'].values[i] < data['lopr'].values[i]:
                                    if data['lopr'].values[i] < data['hipr'].values[-1] and data['ema120'].values[i] < data['ema120'].values[-1]:
                                        buy.add(data['itmsNm'].values[-1])
                                    break
                # elif data['buy'].values[-1] == 1:
                #     for i in range(1, len(data)):
                #         if False:
                #             data['decision'].values[i] = 0
                #         if False:
                #             data['decision'].values[i] = 1
                #     for i in range(len(data) - 1, -1, -1):
                #         if data['decision'].values[i] == 0:
                #             sell.add(data['itmsNm'].values[-1])
                #             break
                #         elif data['decision'].values[i] == 1:
                #             break
        return 'granville 매수 : ' + str(buy)
        # print('granville 매도', sell)