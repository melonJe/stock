import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import FinanceDataReader
import pandas as pd
import requests
from bs4 import BeautifulSoup
from django.core.exceptions import ObjectDoesNotExist
from ta.volatility import AverageTrueRange

from finance.financial_statement import get_financial_summary_for_update_stock, get_finance_from_fnguide
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


def update_subscription_process(stock, user, data_to_insert):
    try:
        summary_dict = get_financial_summary_for_update_stock(stock.symbol)
        df_highlight = get_finance_from_fnguide(stock.symbol, 'highlight', period='Y', include_estimates=False)
        df_cash = get_finance_from_fnguide(stock.symbol, 'cash', period='Y', include_estimates=False)

        if not (pd.to_numeric(df_cash['영업활동으로인한현금흐름'].str.replace(",", ""), errors="coerce")[-3:] > 0).all():
            return

        try:
            if not (pd.to_numeric(df_highlight['매출액'].str.replace(",", ""), errors="coerce")[-3:] > 0).all():
                return
            if not (pd.to_numeric(df_highlight['매출액'].str.replace(",", ""), errors="coerce").diff()[-2:] >= 0).all():
                return
        except Exception as e:
            raise ValueError(f"not find 매출액")

        if not (pd.to_numeric(df_highlight['영업이익'].str.replace(",", ""), errors="coerce").diff()[-1:] >= 0).all():
            return
        if not (pd.to_numeric(df_highlight['당기순이익'].str.replace(",", ""), errors="coerce").diff()[-1:] >= 0).all():
            return

        # if not summary_dict["ROE"] > 10:
        #     return
        # if not summary_dict["ROA"] > 10:
        #     return
        if not summary_dict["PER"] * summary_dict["PBR"] <= 22.5:
            return
        if not summary_dict["부채비율"] < 200:
            return
        if not summary_dict["배당수익률"] >= 2:
            return

        data_to_insert.append({'email': user, 'symbol': stock})
    except Exception as e:
        pass


def update_subscription_stock():
    logging.info(f'{datetime.now()} update_subscription_stock 시작')
    Subscription.objects.filter(email='cabs0814@naver.com').delete()
    data_to_insert = []
    user = Account.objects.get(email='cabs0814@naver.com')

    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = [executor.submit(update_subscription_process, stock, user, data_to_insert) for stock in Stock.objects.all()]

        for future in futures:
            future.result()  # Ensure any raised exceptions are handled

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
