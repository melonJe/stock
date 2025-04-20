import datetime
import logging
import os
import re
import time
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
from utils.data_util import upsert_many, get_yahoo_finance_data
from utils.financial_statement import get_financial_summary_for_update_stock, get_finance_from_fnguide, fetch_financial_timeseries, get_financial_summary_for_update_stock_usa


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


def update_subscription_kor(stock: Stock, data_to_insert):
    try:
        # print(stock.symbol)
        summary_dict = get_financial_summary_for_update_stock(stock.symbol)
        df_highlight = get_finance_from_fnguide(stock.symbol, 'highlight', period='Q', include_estimates=False)
        df_cash = get_finance_from_fnguide(stock.symbol, 'cash', period='Q', include_estimates=False)

        if not (pd.to_numeric(df_cash['영업활동으로인한현금흐름'].str.replace(",", ""), errors="coerce")[-2:] > 0).all():
            return

        try:
            if not (pd.to_numeric(df_highlight['매출액'].str.replace(",", ""), errors="coerce")[-2:] > 0).all():
                return
            # if not (pd.to_numeric(df_highlight['매출액'].str.replace(",", ""), errors="coerce").diff()[-1:] >= 0).all():
            #     return
        except Exception as e:
            raise ValueError(f"not find 매출액")

        if not (pd.to_numeric(df_highlight['영업이익'].str.replace(",", ""), errors="coerce")[-2:] >= 0).all():
            return
        if not (pd.to_numeric(df_highlight['당기순이익'].str.replace(",", ""), errors="coerce")[-2:] >= 0).all():
            return
        # if not (pd.to_numeric(df_highlight['영업이익'].str.replace(",", ""), errors="coerce").diff()[-1:] >= 0).all():
        #     return
        # if not (pd.to_numeric(df_highlight['당기순이익'].str.replace(",", ""), errors="coerce").diff()[-1:] >= 0).all():
        #     return

        # if not summary_dict["ROE"] > 10:
        #     return
        # if not summary_dict["ROA"] > 10:
        #     return
        # if not summary_dict["PER"] * summary_dict["PBR"] <= 22.5:
        #     return
        if not summary_dict["부채비율"] < 200:
            return
        if not summary_dict["배당수익률"] > 2:
            return

        data_to_insert.append({'symbol': stock})
    except Exception as e:
        pass


def update_subscription_usa(stock: Stock, data_to_insert, retries=5, delay=5):
    # print(stock.symbol)
    for attempt in range(retries):
        try:
            summary_dict = get_financial_summary_for_update_stock_usa(stock.symbol)
            df_income = fetch_financial_timeseries(stock.symbol)
            df_cash = fetch_financial_timeseries(stock.symbol, report='cash')

            if not (df_cash['quarterlyOperatingCashFlow'][-2:] > 0).all():
                return
            try:
                if not (df_income['quarterlyTotalRevenue'][-2:] > 0).all():
                    return
                # if not (df_income['quarterlyTotalRevenue'].diff()[-1:] >= 0).all():
                #     return
            except Exception as e:
                raise ValueError(f"not find 매출액")

            if not (df_income['quarterlyOperatingIncome'][-2:] >= 0).all():
                return
            if not (df_income['quarterlyNetIncome'][-2:] >= 0).all():
                return
            # if not (df_income['quarterlyOperatingIncome'].diff()[-1:] >= 0).all():
            #     return
            # if not (df_income['quarterlyNetIncome'].diff()[-1:] >= 0).all():
            #     return

            # if not summary_dict["ROE"] > 10:
            #     return
            # if not summary_dict["ROA"] > 10:
            #     return
            # if not summary_dict["PER"] * summary_dict["PBR"] <= 22.5:
            #     return
            if not summary_dict["Debt Ratio"] < 200:
                return
            if not summary_dict["Dividend Rate"] > 2:
                return

            data_to_insert.append({'symbol': stock})
            return

        except requests.exceptions.RequestException as e:
            logging.info(f"`Attempt {attempt + 1} failed: {stock.symbol}")
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                # logging.info(f"{stock.symbol} All retries failed.")
                return
        except KeyError as e:
            # logging.info(f"{stock.symbol} KeyError: {e}")
            return
        except Exception as e:
            # logging.info(f"{stock.symbol} Unexpected error occurred: {e}")
            return


def update_subscription_stock():
    logging.info(f'{datetime.datetime.now()} update_subscription_stock 시작')
    data_to_insert = []

    # 한국 주식 프로세스
    with ThreadPoolExecutor(max_workers=min(os.cpu_count(), 10)) as executor:
        futures = [executor.submit(update_subscription_kor, stock, data_to_insert) for stock in Stock.select().where(Stock.country == 'KOR')]

        for future in as_completed(futures):
            future.result()  # Ensure any raised exceptions are handled
    data_to_insert.extend([{'symbol': symbol} for symbol in set(FinanceDataReader.StockListing('KRX').iloc[0:100]['Code'])])

    # 미국 주식 프로세스
    with ThreadPoolExecutor(max_workers=min(os.cpu_count(), 10)) as executor:
        futures = [executor.submit(update_subscription_usa, stock, data_to_insert, 5, 5) for stock in Stock.select().where(Stock.country == 'USA')]

        for future in as_completed(futures):
            future.result()  # Ensure any raised exceptions are handled

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
    # print(symbol)
    try:
        country = get_country_by_symbol(symbol)
        table = get_history_table(country)
        data_to_insert = None
        if country == "KOR":
            start_date = (datetime.datetime.now() - relativedelta(years=2)).strftime('%Y-%m-%d') if not start_date else start_date.strftime('%Y-%m-%d')
            end_date = (datetime.datetime.now() + relativedelta(days=5)).strftime('%Y-%m-%d') if not end_date else end_date.strftime('%Y-%m-%d')
            df_krx = FinanceDataReader.DataReader(
                symbol=f'NAVER:{symbol}',
                start=start_date,
                end=end_date
            )
            data_to_insert = [
                {'symbol': symbol,
                 'date': idx.strftime('%Y-%m-%d'),
                 'open': row['Open'],
                 'high': row['High'],
                 'close': row['Close'],
                 'low': row['Low'],
                 'volume': row['Volume']}
                for idx, row in df_krx.iterrows()
            ]
        elif country == "USA":
            unix_start_date = int((datetime.datetime.now() - relativedelta(years=2)).timestamp()) if not start_date else int(start_date.timestamp())
            unix_end_date = int(datetime.datetime.now().timestamp()) if not end_date else int(end_date.timestamp())
            df_krx = get_yahoo_finance_data(symbol, unix_start_date, unix_end_date)
            data_to_insert = [
                {'symbol': symbol,
                 'date': idx.strftime('%Y-%m-%d'),
                 'open': row['Open'].item(),
                 'high': row['High'].item(),
                 'close': row['Close'].item(),
                 'low': row['Low'].item(),
                 'volume': row['Volume']}
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
    data_to_insert = []
    data_to_insert.extend([{'symbol': symbol} for symbol in set(FinanceDataReader.StockListing('KRX').iloc[0:100]['Code'])])
    if data_to_insert:
        logging.info(f"{len(data_to_insert)}개 주식")
        upsert_many(Subscription, data_to_insert, [Subscription.symbol])
