import logging
from datetime import timedelta, datetime
from urllib.parse import parse_qs, urlparse

import FinanceDataReader
import pandas as pd
import requests
from bs4 import BeautifulSoup
from django.core.exceptions import ObjectDoesNotExist
from ta.volatility import AverageTrueRange

from stock.models import Stock
from stock.models import Subscription, Blacklist, PriceHistory, StopLoss, Account
from stock.service.utils import bulk_insert


def get_company_name(symbol: str):
    try:
        df_krx = FinanceDataReader.StockListing('KRX')
        stock_info = df_krx[df_krx['Symbol'] == symbol].to_dict('records').first()
        if not stock_info:
            logging.error("No stock found with that symbol.")
            return None
        company_name = stock_info.get('Name')
        if not company_name:
            return None
        return company_name
    except Exception as e:
        logging.error(f"Failed to fetch stock data: {e}")
        return None


def insert_stock(symbol: str, company_name: str = None):
    # 이미 존재하는 주식인지 확인
    existing_stock = Stock.objects.filter(symbol=symbol).first()
    if existing_stock:
        logging.error(f"Error: A stock with symbol '{symbol}' already exists.")
        return existing_stock

    # company_name이 제공되었는지 확인
    if not company_name:
        company_name = get_company_name(symbol)

    # 새 주식 객체 생성 및 저장
    new_stock = Stock(symbol=symbol, company_name=company_name)
    new_stock.save()
    add_stock_price(symbol=symbol, start_date=(datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d"), end_date=datetime.now().strftime("%Y-%m-%d"))
    return new_stock


def get_stock(symbol: str):
    try:
        return Stock.objects.get(symbol=symbol)
    except ObjectDoesNotExist:
        return insert_stock(symbol=symbol)


def update_defensive_subscription_stock():  # 방어적 투자
    logging.info(f'{datetime.now()} update_defensive_subscription_stock 시작')
    data_to_insert = list()
    user = Account.objects.get(email='cabs0814@naver.com')
    for stock in Stock.objects.all():
        try:
            if requests.get(f"https://navercomp.wisereport.co.kr/company/chart/c1030001.aspx?cmp_cd={stock.symbol}&frq=Y&rpt=ISM&finGubun=MAIN&chartType=svg",
                            headers={'Accept': 'application/json'}).json()['chartData1']['series'][0]['data'][-2] < 1500:
                continue
            page = requests.get(f"https://comp.fnguide.com/SVO2/ASP/SVD_FinanceRatio.asp?pGB=1&gicode=A{stock.symbol}&cID=&MenuYn=Y&ReportGB=&NewMenuID=104&stkGb=701").text
            soup = BeautifulSoup(page, "html.parser")
            current_ratio = float(soup.select('tr#p_grid1_1 > td.cle')[0].text)
            if current_ratio < 150:
                continue

            income = set([])
            tr_tag = BeautifulSoup(page, "html.parser").select('div.um_table')[-1].select('tr')
            for item in tr_tag:
                check = item.select('th > div > div > dl > dt')
                if isinstance(check, list) and check and check[0].text in ['매출액증가율', '영업이익증가율']:  # 'EPS증가율'
                    income = income.union(set([float(x.text.replace(',', '')) for x in item.select('td.r')][1:]))

            page = requests.get(f"https://comp.fnguide.com/SVO2/ASP/SVD_Finance.asp?pGB=1&gicode=A{stock.symbol}&cID=&MenuYn=Y&ReportGB=&NewMenuID=103&stkGb=701").text
            tr_tag = BeautifulSoup(page, "html.parser").select('tr.rwf')
            for item in tr_tag:
                check = item.select('tr > th > div')
                if isinstance(check, list) and check and check[0].text in ['영업이익', '당기순이익', '영업활동으로인한현금흐름']:
                    income = income.union(set([float(x.text.replace(',', '')) for x in item.select('td.r')][:-2]))
            if len(income) < 1 or any([x < 0 for x in income]):
                continue

            page = requests.get(f"https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx?cmp_cd={stock.symbol}").text
            soup = BeautifulSoup(page, "html.parser")
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

    Subscription.objects.filter(email='cabs0814@naver.com').delete()
    if data_to_insert:
        data_to_insert = [Subscription(**vals) for vals in data_to_insert]
        logging.info(f"{len(data_to_insert)}개 주식")
        Subscription.objects.bulk_create(data_to_insert)


def update_aggressive_subscription_stock():  # 공격적 투자
    data_to_insert = list()
    user = Account.objects.get(email='jmayermj@gmail.com')
    df_krx = FinanceDataReader.StockListing('KRX-MARCAP')
    for symbol in df_krx[df_krx['Marcap'] > 300000000000]['Code'].tolist():
        income = set([])
        try:
            page = requests.get(f"https://comp.fnguide.com/SVO2/ASP/SVD_Finance.asp?pGB=1&gicode=A{symbol}&cID=&MenuYn=Y&ReportGB=&NewMenuID=103&stkGb=701").text
            tr_tag = BeautifulSoup(page, "html.parser").select('tr.rwf')
            for item in tr_tag:
                check = item.select('tr > th > div')
                if isinstance(check, list) and check and check[0].text in ['영업이익', '당기순이익', '영업활동으로인한현금흐름']:  # , '영업활동으로인한현금흐름'
                    income = income.union(set([float(x.text.replace(',', '')) for x in item.select('td.r')][:-2]))
            if len(income) < 1 or any([x < 0 for x in income]):
                continue

            page = requests.get(f"https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx?cmp_cd={symbol}").text
            soup = BeautifulSoup(page, "html.parser")
            elements = soup.select('td.cmp-table-cell > dl > dt.line-left')
            if [float(x.text.split(' ')[1][:-1]) for x in elements if x.text.split(' ')[0] == '현금배당수익률'][0] == -1:
                continue
        except:
            continue
        try:
            data_to_insert.append({'email': user, 'symbol': get_stock(symbol=symbol)})
        except:
            insert_stock(symbol)
            data_to_insert.append({'email': user, 'symbol': get_stock(symbol=symbol)})
    Subscription.objects.filter(email='jmayermj@gmail.com').delete()
    if data_to_insert:
        data_to_insert = [Subscription(**vals) for vals in data_to_insert]
        logging.info(f"{len(data_to_insert)}개 주식")
        Subscription.objects.bulk_create(data_to_insert)


def update_blacklist():
    urls = ('https://finance.naver.com/sise/management.naver', 'https://finance.naver.com/sise/trading_halt.naver', 'https://finance.naver.com/sise/investment_alert.naver?type=caution',
            'https://finance.naver.com/sise/investment_alert.naver?type=warning', 'https://finance.naver.com/sise/investment_alert.naver?type=risk')
    symbol = set()
    for url in urls:
        page = requests.get(url).text
        soup = BeautifulSoup(page, "html.parser")
        elements = soup.select('a.tltle')
        symbol = symbol.union(parse_qs(urlparse(x['href']).query)['code'][0] for x in elements)
    data_to_insert = [{'symbol': x, 'date': datetime.now().strftime('%Y-%m-%d')} for x in symbol]
    if data_to_insert:
        bulk_insert(Blacklist, data_to_insert, True, ['symbol'], ['date'])
    Blacklist.objects.filter(date__lt=(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')).delete()


def stop_loss_insert(symbol: str, pchs_avg_pric: float):
    df = pd.DataFrame(PriceHistory.objects.filter(date__range=[datetime.now() - timedelta(days=550), datetime.now()], symbol=symbol).order_by('date').values())
    df['ATR5'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=5).average_true_range()
    df['ATR10'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=10).average_true_range()
    df['ATR20'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=20).average_true_range()
    atr = max(df.iloc[-1]['ATR5'], df.iloc[-1]['ATR10'], df.iloc[-1]['ATR20'])  # 주가 변동성 체크
    stop_loss = pchs_avg_pric - 1.2 * atr  # 20일(보통), 60일(필수) 손절선
    StopLoss.objects.bulk_create([StopLoss(symbol=get_stock(symbol=symbol), price=stop_loss)], update_conflicts=True, unique_fields=['symbol'], update_fields=['price'])


def add_stock():
    df_krx = FinanceDataReader.StockListing('KRX')
    try:
        for symbol, company_name in [[item['Code'], item['Name']] for item in df_krx.to_dict('records')]:
            insert_stock(symbol, company_name)
    except Exception as e:
        logging.error(f"데이터 로딩 중 오류 발생: {e}")


def add_stock_price(symbol: str = None, start_date: str = None, end_date: str = None):
    if start_date is None:
        start_date = datetime.now().strftime('%Y-%m-%d')

    if symbol:
        add_price_for_symbol(symbol, start_date, end_date)
    else:
        for stock in Stock.objects.all():
            add_price_for_symbol(stock.symbol, start_date, end_date)


def add_price_for_symbol(symbol: str, start_date: str, end_date: str = None):
    try:
        df_krx = FinanceDataReader.DataReader(symbol=f'NAVER:{symbol}', start=start_date, end=end_date)
        if df_krx.empty:
            return
        data_to_insert = [
            {
                'symbol': get_stock(symbol=symbol),
                'date': idx,
                'open': row['Open'],
                'high': row['High'],
                'close': row['Close'],
                'low': row['Low'],
                'volume': row['Volume']
            }
            for idx, row in df_krx.iterrows()
        ]
        bulk_insert(PriceHistory, data_to_insert, True, ['symbol', 'date'], ['open', 'high', 'close', 'low', 'volume'])
    except Exception as e:
        logging.error(f"Error processing symbol {symbol}: {e}")
