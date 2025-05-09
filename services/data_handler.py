import datetime
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs

import FinanceDataReader
import pandas as pd
import requests
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta
from ta.volatility import AverageTrueRange

from custom_exception.exception import NotFoundUrl
from data.models import Stock, PriceHistory, PriceHistoryUS, Subscription, Blacklist, StopLoss
from utils.data_util import upsert_many


def get_company_name(symbol: str):
    try:
        existing_stock = Stock.get_or_none(Stock.symbol == symbol)
        if existing_stock:
            return existing_stock.company_name

        df_krx = FinanceDataReader.StockListing('KRX')
        code = 'Code'
        if get_country_by_symbol(symbol) == "USA":
            df_krx = pd.concat([df_krx,
                                FinanceDataReader.StockListing('S&P500'),
                                FinanceDataReader.StockListing('NASDAQ'),
                                FinanceDataReader.StockListing('NYSE')
                                ])
            code = 'Symbol'
        return df_krx[df_krx[code] == symbol].to_dict('records')[0].get('Name')
    except Exception as e:
        logging.error(f"Failed to fetch stock data: {e}")
        return None


def get_country_by_symbol(symbol: str):
    # try:
    #     return Stock.get(symbol=symbol).country
    # except Exception:
    #     pass
    if re.match(r'(\d{5}[0-9KLMN])', symbol):
        return "KOR"
    elif re.match(r'([a-zA-Z\s\.]*)', symbol):
        return "USA"
    else:
        return ""


def get_history_table(country: str):
    country = country.upper()
    mapping = {
        'KOR': PriceHistory,
        'USA': PriceHistoryUS,
    }
    try:
        return mapping[country]
    except KeyError:
        raise ValueError(f"Unsupported country code: {country}")


def insert_stock(symbol: str, company_name: str = None, country: str = None):
    existing_stock = Stock.get_or_none(Stock.symbol == symbol)
    if existing_stock:
        return existing_stock

    if not company_name:
        company_name = get_company_name(symbol)

    if not country:
        country = get_country_by_symbol(symbol)

    new_stock = Stock.create(symbol=symbol, company_name=company_name, country=country)
    add_price_for_symbol(symbol, start_date=datetime.datetime.now() - relativedelta(years=5), end_date=datetime.datetime.now())
    return new_stock


def update_subscription_stock():
    logging.info(f'{datetime.datetime.now()} update_subscription_stock 시작')
    data_to_insert = []

    # 한국 주식 프로세스
    data_to_insert.extend([{'symbol': symbol} for symbol in set(FinanceDataReader.StockListing('KRX').iloc[0:75]['Code'])])

    # 미국 주식 프로세스
    for stockList in (FinanceDataReader.StockListing('S&P500'), FinanceDataReader.StockListing('NASDAQ'), FinanceDataReader.StockListing('NYSE')):
        data_to_insert.extend([{'symbol': symbol} for symbol in set(stockList.iloc[0:25]['Symbol'])])

    if data_to_insert:
        logging.info(f"{len(data_to_insert)}개 주식")
        Subscription.delete().execute()
        upsert_many(Subscription, data_to_insert, [Subscription.symbol])


def update_blacklist():
    urls = ('https://finance.naver.com/sise/management.naver', 'https://finance.naver.com/sise/trading_halt.naver', 'https://finance.naver.com/sise/investment_alert.naver?type=caution',
            'https://finance.naver.com/sise/investment_alert.naver?type=warning', 'https://finance.naver.com/sise/investment_alert.naver?type=risk')
    symbol = set()
    for url in urls:
        page = requests.get(url, timeout=30).text
        soup = BeautifulSoup(page, "html.parser")
        elements = soup.select('a.tltle')
        symbol = symbol.union(parse_qs(urlparse(x['href']).query)['code'][0] for x in elements)
    data_to_insert = [{'symbol': x, 'record_date': datetime.datetime.now().strftime('%Y-%m-%d')} for x in symbol]
    if data_to_insert:
        upsert_many(Blacklist, data_to_insert, Blacklist.symbol, Blacklist.record_date)
    Blacklist.delete().where(Blacklist.record_date < datetime.datetime.now() - datetime.timedelta(days=30)).execute()

    # TODO 미국 주식 Blacklist insert 프로세스 추가


def stop_loss_insert(symbol: str, pchs_avg_pric: float):
    table = get_history_table(get_country_by_symbol(symbol))
    df = pd.DataFrame((
        list((table.select()
              .where(table.date.between(datetime.datetime.now() - datetime.timedelta(days=550), datetime.datetime.now()) & (table.symbol == symbol))
              .order_by(table.date)).dicts())
    ))
    df['ATR5'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=5).average_true_range()
    df['ATR10'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=10).average_true_range()
    df['ATR20'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=20).average_true_range()
    atr = max(df.iloc[-1]['ATR5'], df.iloc[-1]['ATR10'], df.iloc[-1]['ATR20'])  # 주가 변동성 체크
    stop_loss = pchs_avg_pric - 1.2 * atr  # 20일(보통), 60일(필수) 손절선
    StopLoss.insert(symbol=symbol, price=stop_loss)


#
def process_stock_listing(df, code_col, name_col, region):
    """
    주어진 시장 데이터를 처리하고, insert_stock 함수를 병렬로 실행.
    """
    try:
        with ThreadPoolExecutor(max_workers=min(os.cpu_count(), 10)) as executor:
            futures = [
                executor.submit(insert_stock, item[code_col], item[name_col], region)
                for item in df.to_dict('records')
            ]

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"Error while processing data: {e}")
    except Exception as e:
        logging.error(f"Error loading data for market: {e}")


def update_stock_listings():
    """
    KRX 및 미국 시장 데이터를 병렬로 처리.
    """

    try:
        df_kr = FinanceDataReader.StockListing('KRX')
        process_stock_listing(df_kr, 'Code', 'Name', "KOR")

        df_us = pd.concat([
            FinanceDataReader.StockListing('S&P500'),
            FinanceDataReader.StockListing('NASDAQ'),
            FinanceDataReader.StockListing('NYSE')  # 주석 해제 시 추가 가능
        ])
        process_stock_listing(df_us, "Symbol", "Name", "USA")

    except Exception as e:
        logging.error(f"Error loading US data: {e}")


def add_stock_price(symbol: str = None, country: str = None, start_date: datetime.datetime = None, end_date: datetime.datetime = None):
    if start_date is None:
        start_date = datetime.datetime.now()

    # 특정 종목만 처리할 경우
    if symbol:
        add_price_for_symbol(symbol, start_date, end_date)
    else:
        # 전체 종목 조회
        stocks = Stock.select()
        if country:
            stocks = stocks.where(Stock.country == country)

        # ThreadPoolExecutor로 스레드 풀 생성
        with ThreadPoolExecutor(max_workers=min(os.cpu_count(), 10)) as executor:
            futures = []
            for stock in stocks:
                futures.append(
                    executor.submit(add_price_for_symbol, stock.symbol, start_date, end_date)
                )

            # 모든 작업이 완료될 때까지 대기하며 에러 확인
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"에러 발생: {e}")


def add_price_for_symbol(symbol: str, start_date: datetime.datetime = None, end_date: datetime.datetime = None):
    start_date = (datetime.datetime.now() - relativedelta(days=5)).strftime('%Y-%m-%d') if not start_date else start_date.strftime('%Y-%m-%d')
    try:
        country = get_country_by_symbol(symbol)
        table = get_history_table(country)
        data_to_insert = None
        if country == "KOR":
            df_krx = FinanceDataReader.DataReader(
                symbol=f'NAVER:{symbol}',
                start=start_date,
                end=end_date
            )
            data_to_insert = [
                {'symbol': symbol,
                 'date': idx.date(),
                 'open': row['Open'],
                 'high': row['High'],
                 'close': row['Close'],
                 'low': row['Low'],
                 'volume': row['Volume']}
                for idx, row in df_krx.iterrows()
            ]
        elif country == "USA":
            df_krx = FinanceDataReader.DataReader(symbol=symbol, start=start_date, end=end_date)
            data_to_insert = [
                {'symbol': symbol,
                 'date': idx.date(),
                 'open': float(row['Open']),
                 'high': float(row['High']),
                 'close': float(row['Close']),
                 'low': float(row['Low']),
                 'volume': int(row['Volume']) if not pd.isna(row['Volume']) else None}
                for idx, row in df_krx.iterrows()
            ]

        upsert_many(table, data_to_insert, [table.symbol, table.date], ['open', 'high', 'close', 'low', 'volume'])

    except NotFoundUrl as e:
        Stock.delete().where(Stock.symbol == symbol).execute()
    except KeyError as e:
        # logging.error(f"Error processing symbol {symbol}: {e}")
        pass
    except Exception as e:
        # logging.error(f"Error processing symbol {symbol}: {e}")
        pass


if __name__ == "__main__":
    add_stock_price(country="USA", start_date=(datetime.datetime.now() - relativedelta(years=2)))
