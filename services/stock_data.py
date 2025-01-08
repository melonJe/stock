import asyncio
import logging
import os
import re
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from datetime import timedelta
from typing import Optional
from urllib.parse import parse_qs, urlparse

import FinanceDataReader
import pandas as pd
import requests
import tortoise
from bs4 import BeautifulSoup
from ta.volatility import AverageTrueRange

from data import database
from data.models import Stock, PriceHistoryUs
from data.models import Subscription, Blacklist, PriceHistory, StopLoss, Account
from services.financial_statement import get_financial_summary_for_update_stock, get_finance_from_fnguide


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


def get_stock_symbol_type(symbol: str):
    # try:
    #     return Stock.get(symbol=symbol).country
    # except Exception:
    #     pass
    if re.match(r'(\d{6}|\d{5}[a-zA-Z]?)', symbol):
        return "KOR"
    elif re.match(r'([[a-zA-Z]\s?\.?)*', symbol):
        return "USA"
    else:
        return ""


def get_price_history_table(country: str):
    country = country.upper()
    mapping = {
        'KOR': PriceHistory,
        'USA': PriceHistoryUs,
    }
    try:
        return mapping[country]
    except KeyError:
        raise ValueError(f"Unsupported country code: {country}")


def insert_stock(symbol: str, company_name: str = None):
    # 이미 존재하는 주식인지 확인
    existing_stock = Stock.filter(symbol=symbol).first()
    if existing_stock:
        logging.error(f"Error: A stock with symbol '{symbol}' already exists.")
        return existing_stock

    # company_name이 제공되었는지 확인
    if not company_name:
        company_name = get_company_name(symbol)

    # 새 주식 객체 생성 및 저장
    new_stock = Stock(symbol=symbol, company_name=company_name, country=get_stock_symbol_type(symbol))
    new_stock.save()
    return new_stock


def get_stock(symbol: str):
    try:
        return Stock.get(symbol=symbol)
    except Exception as e:
        return insert_stock(symbol=symbol)


async def update_subscription_stock():
    logging.info(f'{datetime.now()} update_subscription_stock 시작')
    await Subscription.filter(email='cabs0814@naver.com').delete()
    data_to_insert = []
    user = Account.get(email='cabs0814@naver.com')

    for stock in await Stock.all():
        try:
            summary_dict = get_financial_summary_for_update_stock(stock.symbol)
            df_highlight = get_finance_from_fnguide(stock.symbol, 'highlight', period='Q', include_estimates=False)
            df_cash = get_finance_from_fnguide(stock.symbol, 'cash', period='Q', include_estimates=False)

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

            await Subscription.create(email=user, symbol=stock)
        except Exception as e:
            logging.error(f"update_subscription_stock 처리 중 에러 발생 {stock.symbol} : {traceback.format_exc()}")
            pass


async def update_blacklist():
    urls = ('https://finance.naver.com/sise/management.naver', 'https://finance.naver.com/sise/trading_halt.naver', 'https://finance.naver.com/sise/investment_alert.naver?type=caution',
            'https://finance.naver.com/sise/investment_alert.naver?type=warning', 'https://finance.naver.com/sise/investment_alert.naver?type=risk')
    symbol = set()
    for url in urls:
        page = requests.get(url).text
        soup = BeautifulSoup(page, "html.parser")
        elements = soup.select('a.tltle')
        symbol = symbol.union(parse_qs(urlparse(x['href']).query)['code'][0] for x in elements)
    data_to_insert = [{'symbol': x, 'date': datetime.now().strftime('%Y-%m-%d')} for x in symbol]
    for row in data_to_insert:
        defaults = {
            "open": row["open"],
            "high": row["high"],
            "close": row["close"],
            "low": row["low"],
            "volume": row["volume"],
        }

        await Blacklist.update_or_create(
            defaults=defaults,
            symbol=row["symbol"],
            date=row["date"]
        )
    await Blacklist.filter(date__lt=(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')).delete()


def stop_loss_insert(symbol: str, pchs_avg_pric: float):
    df = pd.DataFrame(get_price_history_table(get_stock_symbol_type(symbol)).filter(date__range=[datetime.now() - timedelta(days=550), datetime.now()], symbol=symbol).order_by('date').values())
    df['ATR5'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=5).average_true_range()
    df['ATR10'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=10).average_true_range()
    df['ATR20'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=20).average_true_range()
    atr = max(df.iloc[-1]['ATR5'], df.iloc[-1]['ATR10'], df.iloc[-1]['ATR20'])  # 주가 변동성 체크
    stop_loss = pchs_avg_pric - 1.2 * atr  # 20일(보통), 60일(필수) 손절선
    StopLoss.update_or_create(defaults={'price': stop_loss}, symbol=symbol)


def add_stock():
    exchanges = [
        {'name': 'KRX', 'symbol_field': 'Code', 'name_field': 'Name'},
        {'name': 'S&P500', 'symbol_field': 'Symbol', 'name_field': 'Name'},
        {'name': 'NASDAQ', 'symbol_field': 'Symbol', 'name_field': 'Name'},
        {'name': 'NYSE', 'symbol_field': 'Symbol', 'name_field': 'Name'},
    ]

    for exchange in exchanges:
        try:
            logging.info(f"Fetching stock listing for {exchange['name']}")
            df_stocks = FinanceDataReader.StockListing(exchange['name'])
            stock_data = [
                (item[exchange['symbol_field']], item[exchange['name_field']])
                for item in df_stocks.to_dict('records')
            ]
            for symbol, company_name in stock_data:
                insert_stock(symbol, company_name)
            logging.info(f"Completed processing for {exchange['name']}")
        except Exception as e:
            logging.error(f"Error occurred while processing {exchange['name']}: {e}")


async def insert_stock_price(symbol: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, country: Optional[str] = None):
    """
    주어진 테이블에 특정 국가의 주식 가격 데이터를 추가합니다.

    :param symbol: 특정 주식 심볼 (없을 경우 모든 주식 처리).
    :param start_date: 시작 날짜 (YYYY-MM-DD 형식).
    :param end_date: 종료 날짜 (YYYY-MM-DD 형식).
    :param country: 주식의 국가 정보.
    """

    if symbol:
        await add_price_for_symbol(get_price_history_table(get_stock_symbol_type(symbol)), symbol, start_date, end_date)
    else:
        # 전체 종목 조회
        stocks = await Stock.all()

        # ThreadPoolExecutor로 스레드 풀 생성
        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            futures = [
                executor.submit(add_price_for_symbol, get_price_history_table(stock.country), stock.symbol, start_date, end_date)
                for stock in stocks
            ]

            # 모든 작업이 완료될 때까지 대기하며 에러 확인
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"에러 발생: {e}")


async def add_price_for_symbol(model_class: tortoise.models.Model, symbol: str, start_date: str, end_date: Optional[str]):
    """
    특정 국가의 주식 심볼에 대한 가격 데이터를 가져와 주어진 테이블에 삽입합니다.

    :param model_class: DB table 정보
    :param symbol: 주식 심볼.
    :param start_date: 시작 날짜 (YYYY-MM-DD 형식).
    :param end_date: 종료 날짜 (YYYY-MM-DD 형식).
    """
    try:
        if not model_class:
            logging.info(f"model_class에 대한 데이터가 없습니다. {symbol}")

        df = FinanceDataReader.DataReader(
            symbol=symbol,
            start=start_date,
            end=end_date
        )

        if df.empty:
            logging.info(f"{symbol}에 대한 데이터가 없습니다.")
            return

        # DB에 넣을 자료 생성
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
            for idx, row in df.iterrows()
        ]

        for row in data_to_insert:
            defaults = {
                "open": row["open"],
                "high": row["high"],
                "close": row["close"],
                "low": row["low"],
                "volume": row["volume"],
            }

            await model_class.update_or_create(
                defaults=defaults,
                symbol=row["symbol"],
                date=row["date"]
            )
    except Exception as e:
        logging.error(f"add_price_for_symbol 처리 중 에러 발생 {symbol} : {traceback.format_exc()}")


if __name__ == "__main__":
    asyncio.run(database.init())
    # ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_code=setting_env.ACCOUNT_CODE)
