import traceback

import FinanceDataReader
import requests
import pandas as pd
from datetime import timedelta, datetime
from django.conf import settings
from stock.models.stock import *
from stock.helper import discord
from stock.service import bollingerBands
from bs4 import BeautifulSoup as bs
from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore


def update_subscription_defensive_investor():
    # 방어적 투자
    now = datetime.now()
    # if now.day != 1:
    #     return
    data_to_insert = list()
    for stock in Stock.objects.values():
        value = 0
        try:
            if requests.get(f"""https://navercomp.wisereport.co.kr/company/chart/c1030001.aspx?cmp_cd={stock["symbol"]}&frq=Y&rpt=ISM&finGubun=MAIN&chartType=svg""",
                            headers={'Accept': 'application/json'}).json()['chartData1']['series'][0]['data'][-2] < 10000:
                continue
            page = requests.get(f"""https://comp.fnguide.com/SVO2/ASP/SVD_FinanceRatio.asp?pGB=1&gicode=A{stock["symbol"]}&cID=&MenuYn=Y&ReportGB=&NewMenuID=104&stkGb=701""").text
            soup = bs(page, "html.parser")
            current_ratio = float(soup.select('tr#p_grid1_1 > td.cle')[0].text)
            if current_ratio < 200:
                continue
            page = requests.get(f"""https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx?cmp_cd={stock["symbol"]}""").text
            soup = bs(page, "html.parser")
            elements = soup.select('td.cmp-table-cell > dl > dt.line-left')
            per = -1
            pbr = -1
            dividend_rate = -1
            for x in elements:
                item = x.text.split(' ')
                if item[0] == 'PER':
                    per = float(item[1])
                if item[0] == 'PBR':
                    pbr = float(item[1])
                if item[0] == '현금배당수익률':
                    dividend_rate = float(item[1][:-1])
        except:
            continue
        del item
        if dividend_rate == -1:
            continue
        if per > 15:
            continue
        if per * pbr > 22.5:
            continue
        data_to_insert.append({'email': 'cabs0814@naver.com', 'symbol': stock["symbol"]})
    StockSubscription.objects.filter(email='cabs0814@naver.com').delete()
    if data_to_insert:
        data_to_insert = [StockSubscription(**vals) for vals in data_to_insert]
        StockSubscription.objects.bulk_create(data_to_insert)


def update_subscription_aggressive_investor():
    # 공격적 투자
    now = datetime.now()
    # if now.day != 1:
    #     return
    # stock = ['45014K']
    data_to_insert = list()
    for stock in Stock.objects.values():
        insert_true = 0  # 6 is true
        try:
            page = requests.get(f"""https://comp.fnguide.com/SVO2/ASP/SVD_FinanceRatio.asp?pGB=1&gicode=A{stock["symbol"]}&cID=&MenuYn=Y&ReportGB=&NewMenuID=104&stkGb=701""").text
            soup = bs(page, "html.parser")
            tr_tag = soup.select('tr')
            if not tr_tag:
                continue
            for item in tr_tag:
                check = item.select('th > div > div > dl > dt')
                if isinstance(check, list) and check and check[0].text in ['매출액증가율', '영업이익증가율', 'EPS증가율']:
                    rate = [float(x.text.replace(',', '')) for x in item.select('td.r')[:-1]]
                    if len(rate) < 1 or all([x > 0 for x in rate]):
                        insert_true += 1
                    # rate_rate = [rate[i + 1] - rate[i] for i in range(len(rate) - 1)]
                    # if any([x < 0 for x in rate_rate]):
                    #     insert_true = False
        except:
            continue
        if insert_true == 6:
            data_to_insert.append({'email': 'jmayermj@gmail.com', 'symbol': stock["symbol"]})
    StockSubscription.objects.filter(email='jmayermj@gmail.com').delete()
    if data_to_insert:
        data_to_insert = [StockSubscription(**vals) for vals in data_to_insert]
        StockSubscription.objects.bulk_create(data_to_insert)


def add_stock():
    now = datetime.now()
    if now.day != 1:
        return
    df_krx = FinanceDataReader.StockListing('KRX')
    data_to_insert = [{'symbol': item['Code'], 'name': item['Name']} for item in df_krx.to_dict('records')]
    if data_to_insert:
        data_to_insert = [StockSubscription(**vals) for vals in data_to_insert]
        Stock.objects.bulk_create(data_to_insert, ignore_conflicts=True)
    # discord.send_message(f'add_stock   {now}')


def add_stock_price_all():
    one_year_ago = datetime.now().year - 1
    for stock in Stock.objects.values():
        df_krx = FinanceDataReader.DataReader(stock["symbol"], str(one_year_ago))
        data_to_insert = [{'symbol': stock["symbol"], 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']} for idx, item in
                          df_krx.iterrows()]
        if data_to_insert:
            data_to_insert = [StockPrice(**vals) for vals in data_to_insert]
            StockPrice.objects.bulk_create(data_to_insert, update_conflicts=True)


def add_stock_price_1week():
    now = datetime.now()
    if now.weekday() not in (5, 6):
        return
    week_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')
    now = now.strftime('%Y-%m-%d')
    for stock in Stock.objects.values():
        df_krx = FinanceDataReader.DataReader(stock["symbol"], week_ago, now)
        data_to_insert = [{'symbol': stock["symbol"], 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']} for idx, item in
                          df_krx.iterrows()]
        if data_to_insert:
            data_to_insert = [StockPrice(**vals) for vals in data_to_insert]
            StockPrice.objects.bulk_create(data_to_insert, update_conflicts=True)
    # discord.send_message(f'add_stock_price_1week   {now}')


def add_stock_price_1day():
    now = datetime.now()
    if now.weekday() in (5, 6):
        return
    now = now.strftime('%Y-%m-%d')
    data_to_insert = list()
    for stock in Stock.objects.values():
        df_krx = FinanceDataReader.DataReader(stock["symbol"], now, now)
        for idx, item in df_krx.iterrows():
            data_to_insert.append({'symbol': stock["symbol"], 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']})
    if data_to_insert:
        data_to_insert = [StockPrice(**vals) for vals in data_to_insert]
        StockPrice.objects.bulk_create(data_to_insert, update_conflicts=True)


def alert(num_std=2):
    if datetime.now().weekday() in (5, 6):
        return
    message = f"{datetime.now().date()}\n"
    # window = buy_sell_bollinger_band(window=5, num_std=num_std)
    # message += f"bollinger_band 5\nbuy : {window['buy']}\nsell : {window['sell']}\n\n"
    # window = buy_sell_bollinger_band(window=20, num_std=num_std)
    # message += f"bollinger_band 20\nbuy : {window['buy']}\nsell : {window['sell']}\n\n"
    # window = buy_sell_bollinger_band(window=60, num_std=num_std)
    # message += f"bollinger_band 60\nbuy : {window['buy']}\nsell : {window['sell']}\n\n"
    window = buy_sell_trend_judgment()
    message += f"trend_judgment\nbuy : {window['buy']}\nsell : {window['sell']}"
    # print(message)
    discord.send_message(message)


def buy_sell_bollinger_band(window=20, num_std=2):
    decision = {'buy': set(), 'sell': set()}
    try:
        stock = StockSubscription.objects.all().distinct('symbol')
        stock = StockSubscription.objects.all().union(StockBuy.objects.filter(email='cabs0814@naver.com'))
        for s in stock:
            data = pd.DataFrame(
                list(StockPrice.objects.filter(date__range=[datetime.now(), datetime.now() - timedelta(days=200)], symbol=s['symbol']).order_by('date').desc())).sort_values(
                by='date', ascending=True)
            if data.empty:
                continue
            bollingerBands.bollinger_band(data, window=window, num_std=num_std)
            # if data.iloc[-2]['open'] < data.iloc[-2]['close'] and data.iloc[-2]['open'] < data.iloc[-1]['open'] < data.iloc[-2]['close']:
            #     continue
            # if data.iloc[-2]['open'] > data.iloc[-2]['close'] and data.iloc[-2]['open'] > data.iloc[-1]['open'] > data.iloc[-2]['close']:
            #     continue
            if data.iloc[-1]['decision'] == 'buy':
                decision['buy'].add(s['name'])
            if data.iloc[-1]['decision'] == 'sell':
                decision['sell'].add(s['name'])
            # TODO: custom exception
    except:
        str(traceback.print_exc())
        # discord.error_message("stock_db\n" + str(traceback.print_exc()))
    return decision


def buy_sell_trend_judgment():
    decision = {'buy': set(), 'sell': set()}
    try:
        # stock = StockSubscription.objects.all()
        stock = StockSubscription.objects.filter(email='jmayermj@gmail.com')
        for s in stock:
            data = pd.DataFrame(
                list(StockPrice.objects.order_by('date').desc().filter(date__range=[datetime.now(), datetime.now() - timedelta(days=365)], symbol=s['symbol']))).sort_values(
                by='date', ascending=True)
            if data.empty:
                continue
            data['ma200'] = data['close'].rolling(window=200).mean()
            data['ma150'] = data['close'].rolling(window=150).mean()
            data['ma50'] = data['close'].rolling(window=50).mean()
            if not (data.iloc[-1]['ma200'] < data.iloc[-1]['ma150'] < data.iloc[-1]['ma50'] < data.iloc[-1]['close']):
                continue
            if data.iloc[-1]['close'] < data['close'].max() * 0.75:
                continue
            if data.iloc[-1]['close'] < data['close'].min() * 1.25:
                continue
            decision['buy'].add(f"{s['name']}  {data.iloc[-1]['close'] / data['close'].max()}")

        stock = StockBuy.objects.filter(email='cabs0814@naver.com')
        for s in stock:
            data = pd.DataFrame(
                list(StockPrice.objects.order_by('date').desc().filter(date__range=[datetime.now(), datetime.now() - timedelta(days=365)], symbol=s['symbol']))).sort_values(
                by='date', ascending=True)
            data['ma200'] = data['close'].rolling(window=200).mean()
            data['ma150'] = data['close'].rolling(window=150).mean()
            data['ma50'] = data['close'].rolling(window=50).mean()
            if not (data.iloc[-1]['ma200'] < data.iloc[-1]['ma150'] < data.iloc[-1]['ma50'] < data.iloc[-1]['close']):
                decision['sell'].add(s['name'])
                continue
            if data.iloc[-1]['close'] < data['close'].max() * 0.75:
                decision['sell'].add(s['name'])
                continue
            if data.iloc[-1]['close'] < data['close'].min() * 1.25:
                decision['sell'].add(s['name'])
                continue
            # TODO: custom exception
    except:
        str(traceback.print_exc())
        # discord.error_message("stock_db\n" + str(traceback.print_exc()))
    return decision


def start():
    scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)  # BlockingScheduler를 사용할 수도 있습니다.
    scheduler.add_jobstore(DjangoJobStore(), "default")

    scheduler.add_job(
        update_subscription_defensive_investor,
        trigger=CronTrigger(day=1, hour=1),
        id="update_subscription_defensive_investor",  # id는 고유해야합니다.
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        update_subscription_aggressive_investor,
        trigger=CronTrigger(day=1, hour=1),
        id="update_subscription_aggressive_investor",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        add_stock,
        trigger=CronTrigger(day=1, hour=0),
        id="add_stock",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        add_stock_price_1week,
        trigger=CronTrigger(day_of_week="sat"),
        id="add_stock_price_1week",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        add_stock_price_1day,
        trigger=CronTrigger(day_of_week="mon-fri", hour=18),
        id="add_stock_price_1day",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        alert,
        trigger=CronTrigger(day_of_week="mon-fri", hour=20),
        id="alert",
        max_instances=1,
        replace_existing=True,
    )

    try:
        scheduler.start()  # 없으면 동작하지 않습니다.
    except KeyboardInterrupt:
        scheduler.shutdown()
