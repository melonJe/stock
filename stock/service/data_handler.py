import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse, parse_qs

import FinanceDataReader
import pandas as pd
import requests
from bs4 import BeautifulSoup
from django.core.exceptions import ObjectDoesNotExist
from ta.volatility import AverageTrueRange

from stock.models import Stock, Subscription, Blacklist, PriceHistory, StopLoss, Account
from .utils import bulk_insert, fetch_page_content, parse_finance_ratios


def parse_income_elements(tr_tag) -> set:
    income = set()
    for item in tr_tag:
        check = item.select('tr > th > div')
        if isinstance(check, list) and check and check[0].text in ['영업이익', '당기순이익', '영업활동으로인한현금흐름']:
            income = income.union(set([float(x.text.replace(',', '')) for x in item.select('td.r')][:-2]))
    return income


def update_defensive_subscription_stock():
    logging.info(f'{datetime.now()} update_defensive_subscription_stock 시작')
    data_to_insert = []
    user = Account.objects.get(email='cabs0814@naver.com')

    for stock in Stock.objects.all():
        try:
            chart_data_url = f"https://navercomp.wisereport.co.kr/company/chart/c1030001.aspx?cmp_cd={stock.symbol}&frq=Y&rpt=ISM&finGubun=MAIN&chartType=svg"
            chart_data = requests.get(chart_data_url, headers={'Accept': 'application/json'}).json()
            if chart_data['chartData1']['series'][0]['data'][-2] < 1500:
                continue

            finance_ratio_page = fetch_page_content(f"https://comp.fnguide.com/SVO2/ASP/SVD_FinanceRatio.asp?pGB=1&gicode=A{stock.symbol}")
            soup = BeautifulSoup(finance_ratio_page, "html.parser")
            current_ratio = float(soup.select('tr#p_grid1_1 > td.cle')[0].text)
            if current_ratio < 150:
                continue

            income = parse_income_elements(BeautifulSoup(fetch_page_content(f"https://comp.fnguide.com/SVO2/ASP/SVD_Finance.asp?pGB=1&gicode=A{stock.symbol}"), "html.parser").select('tr.rwf'))
            if len(income) < 1 or any([x < 0 for x in income]):
                continue

            per, pbr, dividend_rate = parse_finance_ratios(BeautifulSoup(fetch_page_content(f"https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx?cmp_cd={stock.symbol}"), "html.parser"))
            if dividend_rate == -1 or per > 15 or per * pbr > 22.5:
                continue

            data_to_insert.append({'email': user, 'symbol': stock})
        except Exception as e:
            logging.error(f"Error processing stock {stock.symbol}: {e}")
            continue

    Subscription.objects.filter(email='cabs0814@naver.com').delete()
    if data_to_insert:
        bulk_insert(Subscription, data_to_insert, True, ['email', 'symbol'])


def update_aggressive_subscription_stock():
    data_to_insert = []
    user = Account.objects.get(email='jmayermj@gmail.com')
    df_krx = FinanceDataReader.StockListing('KRX-MARCAP')

    for symbol in df_krx[df_krx['Marcap'] > 300000000000]['Code'].tolist():
        try:
            income = parse_income_elements(BeautifulSoup(fetch_page_content(f"https://comp.fnguide.com/SVO2/ASP/SVD_Finance.asp?pGB=1&gicode=A{symbol}"), "html.parser").select('tr.rwf'))
            if len(income) < 1 or any([x < 0 for x in income]):
                continue

            dividend_rate = parse_finance_ratios(BeautifulSoup(fetch_page_content(f"https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx?cmp_cd={symbol}"), "html.parser"))[2]
            if dividend_rate == -1:
                continue

            data_to_insert.append({'email': user, 'symbol': get_stock(symbol=symbol)})
        except ObjectDoesNotExist:
            insert_stock(symbol)
            data_to_insert.append({'email': user, 'symbol': get_stock(symbol=symbol)})
        except Exception as e:
            logging.error(f"Error processing symbol {symbol}: {e}")
            continue

    Subscription.objects.filter(email='jmayermj@gmail.com').delete()
    if data_to_insert:
        bulk_insert(Subscription, data_to_insert, True, ['email', 'symbol'])


def update_blacklist():
    urls = (
        'https://finance.naver.com/sise/management.naver',
        'https://finance.naver.com/sise/trading_halt.naver',
        'https://finance.naver.com/sise/investment_alert.naver?type=caution',
        'https://finance.naver.com/sise/investment_alert.naver?type=warning',
        'https://finance.naver.com/sise/investment_alert.naver?type=risk'
    )
    symbols = set()
    for url in urls:
        page = fetch_page_content(url)
        soup = BeautifulSoup(page, "html.parser")
        elements = soup.select('a.tltle')
        symbols.update(parse_qs(urlparse(x['href']).query)['code'][0] for x in elements)

    data_to_insert = [{'symbol': x, 'date': datetime.now().strftime('%Y-%m-%d')} for x in symbols]
    if data_to_insert:
        bulk_insert(Blacklist, data_to_insert, True, ['symbol'], ['date'])
    Blacklist.objects.filter(date__lt=(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')).delete()


def stop_loss_insert(symbol: str):
    df = pd.DataFrame(PriceHistory.objects.filter(date__range=[datetime.now() - timedelta(days=550), datetime.now()], symbol=symbol).order_by('date').values())
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['ATR5'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=5).average_true_range()
    df['ATR10'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=10).average_true_range()
    df['ATR20'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=20).average_true_range()
    atr = max(df.iloc[-1]['ATR5'], df.iloc[-1]['ATR10'], df.iloc[-1]['ATR20'])  # 주가 변동성 체크
    stop_loss = df.iloc[-1]['ma20'] - 2 * atr  # 20일(보통), 60일(필수) 손절선
    StopLoss.objects.bulk_create([StopLoss(symbol=get_stock(symbol=symbol), price=stop_loss)], update_conflicts=True, unique_fields=['symbol'], update_fields=['price'])


def get_stock(symbol: str):
    try:
        return Stock.objects.get(symbol=symbol)
    except ObjectDoesNotExist:
        return insert_stock(symbol=symbol)


def get_company_name(symbol: str) -> Optional[str]:
    try:
        df_krx = FinanceDataReader.StockListing('KRX')
        stock_info = df_krx[df_krx['Symbol'] == symbol].to_dict('records')
        if not stock_info:
            logging.error("No stock found with that symbol.")
            return None
        return stock_info[0].get('Name')
    except Exception as e:
        logging.error(f"Failed to fetch stock data: {e}")
        return None


def insert_stock(symbol: str, company_name: str = None):
    existing_stock = Stock.objects.filter(symbol=symbol).first()
    if existing_stock:
        logging.error(f"Error: A stock with symbol '{symbol}' already exists.")
        return existing_stock

    if not company_name:
        company_name = get_company_name(symbol)

    new_stock = Stock(symbol=symbol, company_name=company_name)
    new_stock.save()
    add_stock_price(symbol=symbol, start_date=(datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d"), end_date=datetime.now().strftime("%Y-%m-%d"))
    return new_stock


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
