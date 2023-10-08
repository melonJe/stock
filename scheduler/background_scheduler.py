import random
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
from stock.service.korea_investment import KoreaInvestment
from stock.models.stock import *
from bs4 import BeautifulSoup as bs
from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.background import BackgroundScheduler
from stock.service import discord


def update_subscription_defensive_investor():
    print(f'{datetime.now()} update_subscription_defensive_investor 시작')
    # 방어적 투자
    data_to_insert = list()
    user = User.objects.get(email='cabs0814@naver.com')
    for stock in Stock.objects.all():
        value = 0
        try:
            if requests.get(f"""https://navercomp.wisereport.co.kr/company/chart/c1030001.aspx?cmp_cd={stock.symbol}&frq=Y&rpt=ISM&finGubun=MAIN&chartType=svg""",
                            headers={'Accept': 'application/json'}).json()['chartData1']['series'][0]['data'][-2] < 10000:
                continue
            page = requests.get(f"""https://comp.fnguide.com/SVO2/ASP/SVD_FinanceRatio.asp?pGB=1&gicode=A{stock.symbol}&cID=&MenuYn=Y&ReportGB=&NewMenuID=104&stkGb=701""").text
            soup = bs(page, "html.parser")
            current_ratio = float(soup.select('tr#p_grid1_1 > td.cle')[0].text)
            if current_ratio < 200:
                continue
            page = requests.get(f"""https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx?cmp_cd={stock.symbol}""").text
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
        data_to_insert.append({'email': user, 'symbol': stock})

    StockSubscription.objects.filter(email='cabs0814@naver.com').delete()
    if data_to_insert:
        data_to_insert = [StockSubscription(**vals) for vals in data_to_insert]
        StockSubscription.objects.bulk_create(data_to_insert)


def update_subscription_aggressive_investor():
    print(f'{datetime.now()} update_subscription_aggressive_investor 시작')
    # 공격적 투자
    data_to_insert = list()
    user = User.objects.get(email='jmayermj@gmail.com')
    for stock in Stock.objects.all():
        insert_true = 0  # 6 is true
        try:
            page = requests.get(f"""https://comp.fnguide.com/SVO2/ASP/SVD_FinanceRatio.asp?pGB=1&gicode=A{stock.symbol}&cID=&MenuYn=Y&ReportGB=&NewMenuID=104&stkGb=701""").text
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
        if insert_true >= 6:
            print(stock.name)
            data_to_insert.append({'email': user, 'symbol': stock})

    StockSubscription.objects.filter(email='jmayermj@gmail.com').delete()
    if data_to_insert:
        data_to_insert = [StockSubscription(**vals) for vals in data_to_insert]
        StockSubscription.objects.bulk_create(data_to_insert)


def add_stock():
    print(f'{datetime.now()} add_stock 시작')
    df_krx = FinanceDataReader.StockListing('KRX')
    data_to_insert = [{'symbol': item['Code'], 'name': item['Name']} for item in df_krx.to_dict('records')]
    if data_to_insert:
        data_to_insert = [Stock(**vals) for vals in data_to_insert]
        Stock.objects.bulk_create(data_to_insert,
                                  ignore_conflicts=True,
                                  unique_fields=['symbol'])
    # discord.send_message(f'add_stock   {now}')
    start_date = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")
    for stock in Stock.objects.all():
        df_krx = FinanceDataReader.DataReader(stock.symbol, start_date)
        data_to_insert = [{'symbol': stock, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']} for idx, item in df_krx.iterrows()]
        if data_to_insert:
            data_to_insert = [StockPrice(**vals) for vals in data_to_insert]
            StockPrice.objects.bulk_create(data_to_insert,
                                           update_conflicts=True,
                                           unique_fields=['symbol', 'date'],
                                           update_fields=['open', 'high', 'close', 'low'])


def add_stock_price_all():
    print(f'{datetime.now()} add_stock_price_all 시작')
    one_year_ago = datetime.now().year - 1
    for stock in Stock.objects.all():
        df_krx = FinanceDataReader.DataReader(stock.symbol, str(one_year_ago))
        data_to_insert = [{'symbol': stock, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']} for idx, item in df_krx.iterrows()]
        if data_to_insert:
            data_to_insert = [StockPrice(**vals) for vals in data_to_insert]
            StockPrice.objects.bulk_create(data_to_insert,
                                           update_conflicts=True,
                                           unique_fields=['symbol', 'date'],
                                           update_fields=['open', 'high', 'close', 'low'])


def add_stock_price_1week():
    now = datetime.now()
    print(f'{datetime.now()} add_stock_price_1week 시작')
    week_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')
    now = now.strftime('%Y-%m-%d')
    for stock in Stock.objects.all():
        df_krx = FinanceDataReader.DataReader(stock.symbol, week_ago, now)
        data_to_insert = [{'symbol': stock, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']} for idx, item in df_krx.iterrows()]
        if data_to_insert:
            data_to_insert = [StockPrice(**vals) for vals in data_to_insert]
            StockPrice.objects.bulk_create(data_to_insert,
                                           update_conflicts=True,
                                           unique_fields=['symbol', 'date'],
                                           update_fields=['open', 'high', 'close', 'low'])
    # discord.send_message(f'add_stock_price_1week   {now}')


def add_stock_price_1day():
    now = datetime.now()
    print(f'{datetime.now()} add_stock_price_1day 시작')
    now = now.strftime('%Y-%m-%d')
    data_to_insert = list()
    for stock in Stock.objects.all():
        df_krx = FinanceDataReader.DataReader(stock.symbol, now, now)
        for idx, item in df_krx.iterrows():
            data_to_insert.append({'symbol': stock, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']})
    if data_to_insert:
        data_to_insert = [StockPrice(**vals) for vals in data_to_insert]
        StockPrice.objects.bulk_create(data_to_insert,
                                       update_conflicts=True,
                                       unique_fields=['symbol', 'date'],
                                       update_fields=['open', 'high', 'close', 'low'])


def bollinger_band():
    decision = {'buy': set(), 'sell': set()}
    try:
        stocks = StockSubscription.objects.all().distinct('symbol')
        # stocks = StockSubscription.objects.filter(email='cabs0814@naver.com').select_related("symbol").all()
        for stock in stocks:
            data = pd.DataFrame(StockPrice.objects.filter(date__range=[datetime.now() - timedelta(days=365), datetime.now()], symbol=stock.symbol).order_by('date').values())
            if data.empty:
                continue
            data['ma20'] = data['close'].rolling(window=20).mean()
            data['stddev'] = data['close'].rolling(window=20).std()
            data['upper'] = data['ma20'] + (data['stddev'] * 2)
            data['lower'] = data['ma20'] - (data['stddev'] * 2)
            data['PB'] = (data['close'] - data['lower']) / (data['upper'] - data['lower'])
            data['TP'] = (data['high'] + data['low'] + data['close']) / 3
            data['PMF'] = np.where(data['close'].diff(1) > 0, data['TP'] * data['volume'], 0)  # TODO DB에 거래량 데이터 추가 필요
            data['NMF'] = np.where(data['close'].diff(1) < 0, data['TP'] * data['volume'], 0)
            data['MFR'] = data['PMF'].rolling(window=10).mean() / data['NMF'].rolling(window=10).mean()
            data['MFI10'] = 100 - 100 / (1 + data['MFR'])
            data['decision'] = np.where(data['PB'] > 0.8 and data['MFI10'] > 80, '매수', "")
            data['decision'] = np.where(data['PB'] < 0.2 and data['MFI10'] < 20, '매도', "")
    except:
        str(traceback.print_exc())
        # discord.error_message("stock_db\n" + str(traceback.print_exc()))
    return decision


def initial_yield_growth_stock_investment():  # 초수익 성장주 투자
    decision = {'buy': set(), 'sell': set()}
    try:
        # stocks = StockSubscription.objects.select_related("symbol").all()
        stocks = StockSubscription.objects.filter(email='jmayermj@gmail.com').select_related("symbol").all()
        for stock in stocks:
            data = pd.DataFrame(StockPrice.objects.filter(date__range=[datetime.now() - timedelta(days=365), datetime.now()], symbol=stock.symbol).order_by('date').values())
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
            decision['buy'].add(stock)

        # TODO 판매 알고리즘 공부 및 수정 필요
        account = KoreaInvestment(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_cord=setting_env.ACCOUNT_CORD)
        stocks = account.get_owned_stock_info()
        for stock in stocks:
            data = pd.DataFrame(StockPrice.objects.filter(date__range=[datetime.now() - timedelta(days=365), datetime.now()], symbol=stock['pdno']).order_by('date').values())
            if data.empty:
                continue
            data['ma200'] = data['close'].rolling(window=200).mean()
            data['ma150'] = data['close'].rolling(window=150).mean()
            data['ma50'] = data['close'].rolling(window=50).mean()
            # TODO 조건문 다듬기
            if not (data.iloc[-1]['ma200'] < data.iloc[-1]['ma150'] < data.iloc[-1]['ma50'] < data.iloc[-1]['close']):
                decision['sell'].add(StockSubscription.objects.select_related("symbol").filter(symbol=stock['pdno']).first())
                continue
            if data.iloc[-1]['close'] < data['close'].max() * 0.75:
                decision['sell'].add(StockSubscription.objects.select_related("symbol").filter(symbol=stock['pdno']).first())
                continue
            if data.iloc[-1]['close'] < data['close'].min() * 1.25:
                decision['sell'].add(StockSubscription.objects.select_related("symbol").filter(symbol=stock['pdno']).first())
                continue
    except:
        str(traceback.print_exc())
        # discord.error_message("stock_db\n" + str(traceback.print_exc()))
    return decision


def stock_automated_trading_system():  # 파이썬 주식 자동매매 시스템 - 박준성
    decision = {'buy': set(), 'sell': set()}
    # stocks = StockSubscription.objects.select_related("symbol").all()
    stocks = StockSubscription.objects.filter(email='jmayermj@gmail.com').select_related("symbol").all()
    for stock in stocks:
        data = pd.DataFrame(StockPrice.objects.filter(date__range=[datetime.now() - timedelta(days=28), datetime.now()], symbol=stock.symbol).order_by('date').values())
        data['up'] = np.where(data['close'].diff(1) > 0, data['close'].diff(1), 0)
        data['down'] = np.where(data['close'].diff(1) < 0, data['close'].diff(1) * -1, 0)
        data['all_down'] = data['down'].rolling(window=14).mean()
        data['all_up'] = data['up'].rolling(window=14).mean()
        data['ma20'] = data['close'].rolling(window=20).mean()
        data['ma60'] = data['close'].rolling(window=60).mean()
        if data.iloc[-1]['close'] < data.iloc[-3]['close'] * 0.98 and data.iloc[-1]["ma60"] < data.iloc[-1]["ma20"] and data.iloc[-1]["all_up"] / (data.iloc[-1]["all_up"] + data.iloc[-1]["all_down"]) < 0.05:
            decision['buy'].add(stock)

    account = KoreaInvestment(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_cord=setting_env.ACCOUNT_CORD)
    stocks = account.get_owned_stock_info()
    for stock in stocks:
        data = pd.DataFrame(StockPrice.objects.filter(date__range=[datetime.now() - timedelta(days=28), datetime.now()], symbol=stock['pdno']).order_by('date').values())
        data['up'] = np.where(data['close'].diff(1) > 0, data['close'].diff(1), 0)
        data['down'] = np.where(data['close'].diff(1) < 0, data['close'].diff(1) * -1, 0)
        data['all_down'] = data['down'].rolling(window=14).mean()
        data['all_up'] = data['up'].rolling(window=14).mean()
        if data.iloc[-1]["all_up"] / (data.iloc[-1]["all_up"] + data.iloc[-1]["all_down"]) > 0.8:
            decision['sell'].add(StockSubscription.objects.select_related("symbol").filter(symbol=stock['pdno']).first())

    return decision


def korea_investment_trading_initial_yield_growth_stock_investment():
    account = KoreaInvestment(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_cord=setting_env.ACCOUNT_CORD)
    if account.check_holiday():
        return
    decision = initial_yield_growth_stock_investment()  # decision = {'buy': set(), 'sell': set()}
    buy = set(x.symbol.symbol for x in decision['buy'])
    sell = set(x.symbol.symbol for x in decision['sell'])
    inquire_balance = account.get_account_info()
    dnca_tot_amt = inquire_balance["dnca_tot_amt"] - inquire_balance["tot_evlu_amt"] * 0.10  # 사용 가능한 금액 계산 (총 평가 금액의 10% 제외한 예수금)
    while datetime.now().time() < time(15, 0, 0) and (sell or buy):
        for symbol in sell.copy():
            previous_stock = StockPrice.objects.filter(symbol=symbol).order_by('-date').first()
            inquire_stock = account.get_owned_stock_info(symbol)
            if (not inquire_stock) or inquire_stock["evlu_pfls_rt"] <= 2.5 or inquire_stock["ord_psbl_qty"] == 0:  # 가지고 있지 않거나 수익률이 2.5% 이하거나 주문 가능한 수량이 없으면 다음 주식으로 넘어감
                sell.discard(symbol)
                continue
            volume = math.ceil(inquire_balance["tot_evlu_amt"] * 0.02 / inquire_balance['evlu_amt'])  # 총 평가 금액의 2% 씩 판매
            if volume > inquire_balance["ord_psbl_qty"]:  # 주문 가능 수량을 넘길 경우 주문 수량 수정
                volume = inquire_balance["ord_psbl_qty"]
            if volume < 1 or account.buy(stock=symbol, price=previous_stock.close, volume=volume):
                print(f"{symbol} 종목 매도 수량: {volume}")
                sell.discard(symbol)
                sleep(1)
        for symbol in buy.copy():
            previous_stock = StockPrice.objects.filter(symbol=symbol).order_by('-date').first()
            volume = int(inquire_balance["tot_evlu_amt"] * 0.02 / previous_stock.close)  # 총 평가 금액의 2% 씩 구매
            volume = 1 if volume == 0 else volume  # 구매 수량이 0일 경우 1로 수정
            volume = min(volume, int(dnca_tot_amt / previous_stock.close), 100)  # 구매 수량이 사용 가능한 금액을 초과 하는지, 100주를 넘는지 판단
            inquire_stock = account.get_owned_stock_info(symbol)
            if volume > 0 and inquire_stock:  # 구매 수량이 0보다 크고 보유 중인 주식일 경우
                volume = min(volume, int((inquire_balance["tot_evlu_amt"] * 0.2 - inquire_stock["pchs_amt"]) / previous_stock.close), 1000 - inquire_stock["hldg_qty"])  # 주식 보유 비중이 20%를, 보유수량이 1000주를 넘지 않도록 구매 수량 수정
            if volume < 1 or account.buy(stock=symbol, price=previous_stock.close, volume=volume):
                dnca_tot_amt -= previous_stock.close * volume
                print(f"{symbol} 종목 매수 수량: {volume}")
                buy.discard(symbol)
                sleep(1)
        sleep(60)
    if setting_env.SIMULATE:
        return
    while datetime.now().time() < time(10, 30, 0):
        sleep(60)
    correctable_stock = account.get_cancellable_or_correctable_stock()
    for item in correctable_stock:
        if item['sll_buy_dvsn_cd'] == '02':  # 매수 주문만 변경
            account.modify_stock_order(order_no=item['odno'], volume=item['psbl_qty'])


def notify_negative_profit_warning():
    alert = set()
    account = KoreaInvestment(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_cord=setting_env.ACCOUNT_CORD)
    if account.check_holiday():
        return
    while datetime.now().time() < time(15, 30, 0):
        inquire_stock = account.get_owned_stock_info()
        for item in inquire_stock:
            if item["pdno"] not in alert and item["evlu_pfls_rt"] < -4:
                discord.send_message(f"""{item["prdt_name"]} 수익률 {item["evlu_pfls_rt"]}""")
                alert.add(item["pdno"])
        sleep(10 * 60)


def start():
    scheduler = BackgroundScheduler(misfire_grace_time=3600, coalesce=True, timezone=settings.TIME_ZONE)

    scheduler.add_job(
        update_subscription_defensive_investor,
        trigger=CronTrigger(day=1, hour=4),
        id="update_subscription_defensive_investor",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        update_subscription_aggressive_investor,
        trigger=CronTrigger(day=1, hour=2),
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
        korea_investment_trading_initial_yield_growth_stock_investment,
        trigger=CronTrigger(day_of_week="mon-fri", hour=8, minute=45),
        id="korea_investment_trading_initial_yield_growth_stock_investment",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        notify_negative_profit_warning,
        trigger=CronTrigger(day_of_week="mon-fri", hour=9, minute=00),
        id="notify_negative_profit_warning",
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

    try:
        scheduler.start()  # 없으면 동작하지 않습니다.
    except KeyboardInterrupt:
        scheduler.shutdown()


def test():
    pd.set_option('display.max_rows', None)
    count = 0
    conclusion = []
    # stocks = StockSubscription.objects.select_related("symbol").all()
    # stocks = StockSubscription.objects.filter(email='cabs0814@naver.com').select_related("symbol").all()
    stocks = StockSubscription.objects.filter(email='jmayermj@gmail.com').select_related("symbol").all()
    list_stock_dataframe = []
    for stock in stocks:
        data = pd.DataFrame(StockPrice.objects.filter(date__range=[datetime.now() - timedelta(days=500), datetime.now()], symbol=stock.symbol).order_by('date').values())
        if data.empty:
            continue
        data['ma200'] = data['close'].rolling(window=200).mean()
        data['ma150'] = data['close'].rolling(window=150).mean()
        data['ma50'] = data['close'].rolling(window=50).mean()
        list_stock_dataframe.append(data)
    stock_price = {item.iloc[-1]['symbol_id']: 0 for item in list_stock_dataframe}
    number = {item.iloc[-1]['symbol_id']: 0 for item in list_stock_dataframe}
    account = 35000000
    temp_list_stock_dataframe = []
    for stock_dataframe in list_stock_dataframe:
        stock_dataframe['buy_sell'] = -1
        stock_dataframe.loc[(stock_dataframe['ma200'] < stock_dataframe['ma150'])
                            & (stock_dataframe['ma150'] < stock_dataframe['ma50'])
                            & (stock_dataframe['ma50'] < stock_dataframe['close'])
                            & (stock_dataframe['close'] > stock_dataframe['close'].max() * 0.75)
                            & (stock_dataframe['close'] > stock_dataframe['close'].min() * 1.25), 'buy_sell'] = 1
        # stock_dataframe.loc[(stock_dataframe['ma150'] > stock_dataframe['ma50']), 'buy_sell'] = -1
        temp_list_stock_dataframe.append(stock_dataframe[-260:])
    temp_list_stock_dataframe = [x for x in temp_list_stock_dataframe if len(x) == 260]
    for x in range(260):
        for stock_dataframe in temp_list_stock_dataframe:
            # if math.isnan(item['close']):
            #     continue
            # if number > 0 and stock_price / number * 0.92 > item['close']:
            #     account += item['close'] * 0.992 * number
            #     stock_price -= item['close'] * number
            #     number -= number
            if stock_dataframe.iloc[x]['buy_sell'] == 1:
                total_stock_price = sum(stock_price.values())
                quantity = int((account + total_stock_price) * 0.02 / stock_dataframe.iloc[x]['close'])
                quantity = 1 if quantity == 0 else quantity
                quantity = min(quantity, int(account / stock_dataframe.iloc[x]['close']))
                if number[stock_dataframe.iloc[x]['symbol_id']] > 0 and quantity > 0:
                    quantity = min(quantity, int(((account + total_stock_price) * 0.2 - stock_price[stock_dataframe.iloc[x]['symbol_id']]) / stock_dataframe.iloc[x]['close']))
                account -= stock_dataframe.iloc[x]['close'] * 1.005 * quantity
                stock_price[stock_dataframe.iloc[x]['symbol_id']] += stock_dataframe.iloc[x]['close'] * quantity
                number[stock_dataframe.iloc[x]['symbol_id']] += quantity

            # if number[stock_dataframe.iloc[x]['symbol_id']] > 0 and stock_dataframe.iloc[x]['close'] < stock_price[stock_dataframe.iloc[x]['symbol_id']] / number[stock_dataframe.iloc[x]['symbol_id']] * 0.95:
            #     account += stock_dataframe.iloc[x]['close'] * 0.995 * number[stock_dataframe.iloc[x]['symbol_id']]
            #     stock_price[stock_dataframe.iloc[x]['symbol_id']] -= stock_price[stock_dataframe.iloc[x]['symbol_id']] / number[stock_dataframe.iloc[x]['symbol_id']] * number[stock_dataframe.iloc[x]['symbol_id']]
            #     number[stock_dataframe.iloc[x]['symbol_id']] -= number[stock_dataframe.iloc[x]['symbol_id']]

            if stock_dataframe.iloc[x]['buy_sell'] == -1:
                if number[stock_dataframe.iloc[x]['symbol_id']] > 0 and stock_price[stock_dataframe.iloc[x]['symbol_id']] / number[stock_dataframe.iloc[x]['symbol_id']] * 1.025 < stock_dataframe.iloc[x]['close']:
                    # print(stock_dataframe.iloc[x]['symbol_id'], stock_dataframe.iloc[x]['close'] / (stock_price[stock_dataframe.iloc[-1]['symbol_id']] / number[stock_dataframe.iloc[-1]['symbol_id']]) * 100)
                    quantity = int((account + stock_price[stock_dataframe.iloc[x]['symbol_id']]) * 0.02 / stock_dataframe.iloc[x]['close'])
                    if quantity > number[stock_dataframe.iloc[x]['symbol_id']]:
                        quantity = number[stock_dataframe.iloc[x]['symbol_id']]
                    account += stock_dataframe.iloc[x]['close'] * 0.995 * quantity
                    stock_price[stock_dataframe.iloc[x]['symbol_id']] -= stock_price[stock_dataframe.iloc[x]['symbol_id']] / number[stock_dataframe.iloc[x]['symbol_id']] * quantity
                    number[stock_dataframe.iloc[x]['symbol_id']] -= quantity
                else:
                    pass
                    # if number[stock_dataframe.iloc[-1]['symbol_id']] > 0:
                    #     print(stock_dataframe.iloc[x]['symbol_id'], stock_dataframe.iloc[x]['close'] / (stock_price[stock_dataframe.iloc[-1]['symbol_id']] / number[stock_dataframe.iloc[-1]['symbol_id']]) * 100)
    # for stock_dataframe in temp_list_stock_dataframe:
    #     if number[stock_dataframe.iloc[-1]['symbol_id']] != 0:
    #         print(stock_dataframe.iloc[-1]['close'] / (number[stock_dataframe.iloc[-1]['symbol_id']] > 0 and stock_price[stock_dataframe.iloc[-1]['symbol_id']] / number[stock_dataframe.iloc[-1]['symbol_id']]))
    price = 0
    for stock_dataframe in list_stock_dataframe:
        if number[stock_dataframe.iloc[-1]['symbol_id']] == 0:
            continue
        price += stock_dataframe.iloc[-1]['close'] * number[stock_dataframe.iloc[-1]['symbol_id']]
    print(f"{price:>20.2f}, {account + price:>20.2f}")
