import FinanceDataReader
import math

import numpy as np
import pandas as pd
import requests
import setting_env
import traceback
from time import sleep
from datetime import timedelta, datetime, time
from django.conf import settings
from stock.helper.korea_investment import KoreaInvestment
from stock.models.stock import *
from stock.helper import discord
from stock.service import bollingerBands
from bs4 import BeautifulSoup as bs
from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.background import BackgroundScheduler


def update_subscription_defensive_investor():
    print(f'{datetime.now()} update_subscription_defensive_investor 시작')
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
    print(f'{datetime.now()} update_subscription_aggressive_investor 시작')
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
                if isinstance(check, list) and check and check[0].text in [
                    '매출액증가율', '영업이익증가율', 'EPS증가율']:
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
    print(f'{datetime.now()} add_stock 시작')
    df_krx = FinanceDataReader.StockListing('KRX')
    data_to_insert = [{'symbol': Stock.objects.get(symbol=item['Code']), 'name': item['Name']} for item in df_krx.to_dict('records')]
    if data_to_insert:
        data_to_insert = [StockSubscription(**vals) for vals in data_to_insert]
        Stock.objects.bulk_create(data_to_insert,
                                  ignore_conflicts=True,
                                  unique_fields=['symbol', 'date'])
    # discord.send_message(f'add_stock   {now}')


def add_stock_price_all():
    print(f'{datetime.now()} add_stock_price_all 시작')
    one_year_ago = datetime.now().year - 1
    for stock in Stock.objects.values():
        df_krx = FinanceDataReader.DataReader(stock["symbol"], str(one_year_ago))
        stock_instance = Stock.objects.get(symbol=stock['symbol'])
        data_to_insert = [{'symbol': stock_instance, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']} for idx, item in df_krx.iterrows()]
        if data_to_insert:
            data_to_insert = [StockPrice(**vals) for vals in data_to_insert]
            StockPrice.objects.bulk_create(data_to_insert,
                                           update_conflicts=True,
                                           unique_fields=['symbol', 'date'],
                                           update_fields=['open', 'high', 'close', 'low'])


def add_stock_price_1week():
    now = datetime.now()
    # if now.weekday() not in (5, 6):
    #     return
    print(f'{datetime.now()} add_stock_price_1week 시작')
    week_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')
    now = now.strftime('%Y-%m-%d')
    for stock in Stock.objects.values():
        df_krx = FinanceDataReader.DataReader(stock["symbol"], week_ago, now)
        stock_instance = Stock.objects.get(symbol=stock['symbol'])
        data_to_insert = [{'symbol': stock_instance, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']} for idx, item in df_krx.iterrows()]
        if data_to_insert:
            data_to_insert = [StockPrice(**vals) for vals in data_to_insert]
            StockPrice.objects.bulk_create(data_to_insert,
                                           update_conflicts=True,
                                           unique_fields=['symbol', 'date'],
                                           update_fields=['open', 'high', 'close', 'low'])
    # discord.send_message(f'add_stock_price_1week   {now}')


def add_stock_price_1day():
    now = datetime.now()
    if now.weekday() in (5, 6):
        return
    print(f'{datetime.now()} add_stock_price_1day 시작')
    now = now.strftime('%Y-%m-%d')
    data_to_insert = list()
    for stock in Stock.objects.values():
        df_krx = FinanceDataReader.DataReader(stock["symbol"], now, now)
        stock_instance = Stock.objects.get(symbol=stock['symbol'])
        for idx, item in df_krx.iterrows():
            data_to_insert.append({'symbol': stock_instance, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']})
    if data_to_insert:
        data_to_insert = [StockPrice(**vals) for vals in data_to_insert]
        StockPrice.objects.bulk_create(data_to_insert,
                                       update_conflicts=True,
                                       unique_fields=['symbol', 'date'],
                                       update_fields=['open', 'high', 'close', 'low'])


def alert(num_std=2):
    if datetime.now().weekday() in (5, 6):
        return
    print(f'{datetime.now()} alert 시작')
    message = f"{datetime.now().date()}\n"
    window = buy_sell_bollinger_band(window=5, num_std=num_std)
    message += f"bollinger_band 5\nbuy : {[x.symbol.name for x in window['buy']]}\nsell : {[x.symbol.name for x in window['sell']]}\n\n"
    window = buy_sell_bollinger_band(window=20, num_std=num_std)
    message += f"bollinger_band 20\nbuy : {[x.symbol.name for x in window['buy']]}\nsell : {[x.symbol.name for x in window['sell']]}\n\n"
    window = buy_sell_bollinger_band(window=60, num_std=num_std)
    message += f"bollinger_band 60\nbuy : {[x.symbol.name for x in window['buy']]}\nsell : {[x.symbol.name for x in window['sell']]}\n\n"
    window = buy_sell_trend_judgment()
    message += f"trend_judgment\nbuy : {[x.symbol.name for x in window['buy']]}\nsell : {[x.symbol.name for x in window['sell']]}"
    print(message)
    # discord.send_message(message)


def buy_sell_bollinger_band(window=20, num_std=2):
    decision = {'buy': set(), 'sell': set()}
    try:
        # stock = StockSubscription.objects.all().distinct('symbol')
        stocks = StockSubscription.objects.filter(email='cabs0814@naver.com').select_related("symbol").all()
        for stock in stocks:
            data = pd.DataFrame(StockPrice.objects.filter(date__range=[datetime.now() - timedelta(days=365), datetime.now()], symbol=stock.symbol).order_by('date').values())
            if data.empty:
                continue
            bollingerBands.bollinger_band(data, window=window, num_std=num_std)
            # if data.iloc[-2]['open'] < data.iloc[-2]['close'] and data.iloc[-2]['open'] < data.iloc[-1]['open'] < data.iloc[-2]['close']:
            #     continue
            # if data.iloc[-2]['open'] > data.iloc[-2]['close'] and data.iloc[-2]['open'] > data.iloc[-1]['open'] > data.iloc[-2]['close']:
            #     continue
            if data.iloc[-1]['decision'] == 'buy':
                decision['buy'].add(stock)
            if data.iloc[-1]['decision'] == 'sell':
                decision['sell'].add(stock)
            # TODO: custom exception
    except:
        str(traceback.print_exc())
        # discord.error_message("stock_db\n" + str(traceback.print_exc()))
    return decision


def buy_sell_trend_judgment():
    decision = {'buy': set(), 'sell': set()}
    try:
        stocks = StockSubscription.objects.select_related("symbol").all()
        for stock in stocks:
            data = pd.DataFrame(StockPrice.objects.filter(date__range=[datetime.now() - timedelta(days=28), datetime.now()], symbol=stock.symbol).order_by('date').values())
            data['up'] = np.where(data['close'].diff(1) > 0, data['close'].diff(1), 0)
            data['down'] = np.where(data['close'].diff(1) < 0, data['close'].diff(1) * -1, 0)
            data['all_down'] = data['down'].rolling(window=10).mean()
            data['all_up'] = data['up'].rolling(window=10).mean()
            data['ma20'] = data['close'].rolling(window=20).mean()
            data['ma60'] = data['close'].rolling(window=60).mean()
            if data.iloc[-1]["close"] < data.iloc[-3]["close"] * 0.98 and data.iloc[-1]["ma60"] < data.iloc[-1]["ma20"] and data.iloc[-1]["all_up"] / (data.iloc[-1]["all_up"] + data.iloc[-1]["all_down"]) < 0.05:
                decision['sell'].add(stock)

        # TODO 판매 알고리즘 수정
        account = KoreaInvestment(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_cord=setting_env.ACCOUNT_CORD)
        stocks = account.get_owned_stock_info()
        for stock in stocks:
            data = pd.DataFrame(StockPrice.objects.filter(date__range=[datetime.now() - timedelta(days=28), datetime.now()], symbol=stock['pdno']).order_by('date').values())
            data['up'] = np.where(data['close'].diff(1) > 0, data['close'].diff(1), 0)
            data['down'] = np.where(data['close'].diff(1) < 0, data['close'].diff(1) * -1, 0)
            data['all_down'] = data['down'].rolling(window=10).mean()
            data['all_up'] = data['up'].rolling(window=10).mean()
            if data.iloc[-1]["all_up"] / (data.iloc[-1]["all_up"] + data.iloc[-1]["all_down"]) > 0.8:
                decision['sell'].add(StockSubscription.objects.select_related("symbol").filter(symbol=stock['pdno']).first())
    except:
        str(traceback.print_exc())
        # discord.error_message("stock_db\n" + str(traceback.print_exc()))
    return decision


def korea_investment_trading():
    account = KoreaInvestment(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_cord=setting_env.ACCOUNT_CORD)
    decision = buy_sell_trend_judgment()  # decision = {'buy': set(), 'sell': set()}
    buy = set(x.symbol.symbol for x in decision['buy'])
    sell = set(x.symbol.symbol for x in decision['sell'])
    inquire_balance = account.get_account_info()
    dnca_tot_amt = inquire_balance["dnca_tot_amt"] - inquire_balance["tot_evlu_amt"] * 0.10
    while sell or buy:
        for symbol in sell.copy():
            previous_stock = StockPrice.objects.filter(symbol=symbol).order_by('-date').first()
            inquire_stock = account.get_owned_stock_info(symbol)
            if not inquire_stock or inquire_stock["evlu_pfls_rt"] <= 2.5 or inquire_stock["ord_psbl_qty"] == 0:
                sell.discard(symbol)
                continue
            volume = math.ceil(inquire_balance["tot_evlu_amt"] * 0.05)
            if volume > inquire_balance["ord_psbl_qty"]:
                volume = inquire_balance["ord_psbl_qty"]
            if volume < 1 or account.buy(stock=symbol, price=previous_stock.close, volume=volume):
                sell.discard(symbol)
        for symbol in buy.copy():
            previous_stock = StockPrice.objects.filter(symbol=symbol).order_by('-date').first()
            volume = int(inquire_balance["tot_evlu_amt"] * 0.018 / previous_stock.close)
            volume = min(1 if volume == 0 else volume, int(dnca_tot_amt / previous_stock.close))
            inquire_stock = account.get_owned_stock_info(symbol)
            if volume > 0 and inquire_stock:
                volume = min(volume, int((inquire_balance["tot_evlu_amt"] * 0.2 - inquire_stock["pchs_amt"]) / previous_stock.close))
            if volume < 1 or account.buy(stock=symbol, price=previous_stock.close, volume=volume):
                dnca_tot_amt -= previous_stock.close * volume
                buy.discard(symbol)
    if setting_env.SIMULATE:
        return
    while datetime.now().time() < time(10, 30, 0):
        sleep(60)
    correctable_stock = account.get_cancellable_or_correctable_stock()
    for item in correctable_stock:
        account.modify_stock_order(order_no=item['odno'], volume=item['psbl_qty'])


def start():
    scheduler = BackgroundScheduler(misfire_grace_time=3600, coalesce=True, timezone=settings.TIME_ZONE)

    # scheduler.add_job(
    #     update_subscription_defensive_investor,
    #     trigger=CronTrigger(day=1, hour=1),
    #     id="update_subscription_defensive_investor",
    #     max_instances=1,
    #     replace_existing=True,
    # )
    #
    # scheduler.add_job(
    #     update_subscription_aggressive_investor,
    #     trigger=CronTrigger(day=1, hour=1),
    #     id="update_subscription_aggressive_investor",
    #     max_instances=1,
    #     replace_existing=True,
    # )

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
        korea_investment_trading,
        trigger=CronTrigger(day_of_week="mon-fri", hour=8, minute=45),
        id="korea_investment_trading",
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

    # scheduler.add_job(
    #     alert,
    #     trigger=CronTrigger(day_of_week="mon-fri", hour=20),
    #     id="alert",
    #     max_instances=1,
    #     replace_existing=True,
    # )

    try:
        scheduler.start()  # 없으면 동작하지 않습니다.
    except KeyboardInterrupt:
        scheduler.shutdown()
