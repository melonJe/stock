"""가격 데이터 접근"""
import datetime
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import FinanceDataReader
import pandas as pd
from dateutil.relativedelta import relativedelta

from config.logging_config import get_logger
from custom_exception.exception import NotFoundUrl
from data.models import Stock
from repositories.stock_repository import StockRepository
from utils.data_util import upsert_many

logger = get_logger(__name__)


class PriceRepository:
    """가격 데이터 Repository"""

    @staticmethod
    def add(
            symbol: str = None,
            country: str = None,
            start_date: datetime.datetime = None,
            end_date: datetime.datetime = None
    ):
        """가격 데이터 추가 (전체 또는 특정 종목)"""
        if start_date is None:
            start_date = datetime.datetime.now()

        if symbol:
            PriceRepository.add_for_symbol(symbol, start_date, end_date)
        else:
            stocks = Stock.select()
            if country:
                stocks = stocks.where(Stock.country == country)

            with ThreadPoolExecutor(max_workers=min(os.cpu_count(), 10)) as executor:
                futures = []
                for stock in stocks:
                    futures.append(executor.submit(PriceRepository.add_for_symbol, stock.symbol, start_date, end_date))

                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"에러 발생: {e}")

    @staticmethod
    def add_for_symbol(
            symbol: str,
            start_date: datetime.datetime = None,
            end_date: datetime.datetime = None
    ):
        """특정 종목의 가격 데이터 추가"""
        start_date_str = (datetime.datetime.now() - relativedelta(days=5)).strftime('%Y-%m-%d') \
            if not start_date else start_date.strftime('%Y-%m-%d')

        try:
            country = StockRepository.get_country_by_symbol(symbol)
            table = StockRepository.get_history_table(country)
            data_to_insert = None

            if country == "KOR":
                df_krx = FinanceDataReader.DataReader(
                    symbol=f'NAVER:{symbol}',
                    start=start_date_str,
                    end=end_date
                )
                data_to_insert = [
                    {
                        'symbol': symbol,
                        'date': idx.date(),
                        'open': row['Open'],
                        'high': row['High'],
                        'close': row['Close'],
                        'low': row['Low'],
                        'volume': row['Volume']
                    }
                    for idx, row in df_krx.iterrows()
                ]
            elif country == "USA":
                df_krx = FinanceDataReader.DataReader(symbol=symbol, start=start_date_str, end=end_date)
                data_to_insert = [
                    {
                        'symbol': symbol,
                        'date': idx.date(),
                        'open': float(row['Open']),
                        'high': float(row['High']),
                        'close': float(row['Close']),
                        'low': float(row['Low']),
                        'volume': int(row['Volume']) if not pd.isna(row['Volume']) else None
                    }
                    for idx, row in df_krx.iterrows()
                ]

            if data_to_insert:
                upsert_many(table, data_to_insert, [table.symbol, table.date], ['open', 'high', 'close', 'low', 'volume'])

        except NotFoundUrl:
            Stock.delete().where(Stock.symbol == symbol).execute()
        except KeyError:
            pass
        except Exception:
            pass
