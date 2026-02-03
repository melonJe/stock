"""종목 정보 데이터 접근"""
import datetime
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import FinanceDataReader
import pandas as pd
from dateutil.relativedelta import relativedelta

from config.logging_config import get_logger
from data.models import Stock, PriceHistory, PriceHistoryUS
from config.constants import (
    KOREAN_STOCK_PATTERN,
    AMERICA_STOCK_PATTERN,
    MAX_WORKER_COUNT,
    DEFAULT_PRICE_HISTORY_YEARS,
)

logger = get_logger(__name__)


class StockRepository:
    """종목 정보 Repository"""

    @staticmethod
    def get_country_by_symbol(symbol: str) -> str:
        """종목코드로 국가 판별"""
        if re.match(KOREAN_STOCK_PATTERN, symbol):
            return "KOR"
        elif re.match(AMERICA_STOCK_PATTERN, symbol):
            return "USA"
        else:
            return ""

    @staticmethod
    def get_history_table(country: str):
        """국가별 가격 히스토리 테이블 반환"""
        country = country.upper()
        mapping = {
            'KOR': PriceHistory,
            'USA': PriceHistoryUS,
        }
        try:
            return mapping[country]
        except KeyError:
            raise ValueError(f"Unsupported country code: {country}")

    @staticmethod
    def get_company_name(symbol: str) -> str:
        """종목코드로 회사명 조회"""
        try:
            existing_stock = Stock.get_or_none(Stock.symbol == symbol)
            if existing_stock:
                return existing_stock.company_name

            df_krx = FinanceDataReader.StockListing('KRX')
            code = 'Code'
            if StockRepository.get_country_by_symbol(symbol) == "USA":
                df_krx = pd.concat([
                    df_krx,
                    FinanceDataReader.StockListing('S&P500'),
                    FinanceDataReader.StockListing('NASDAQ'),
                    FinanceDataReader.StockListing('NYSE')
                ])
                code = 'Symbol'
            records = df_krx[df_krx[code] == symbol].to_dict('records')
            return records[0].get('Name') if records else None
        except Exception as e:
            logger.error(f"종목명 조회 실패: {e}")
            return None

    @staticmethod
    def insert(symbol: str, company_name: str = None, country: str = None, add_price_history: bool = True) -> Stock:
        """
        종목 정보 저장

        :param symbol: 종목코드
        :param company_name: 회사명 (None이면 자동 조회)
        :param country: 국가코드 (None이면 자동 판별)
        :param add_price_history: 가격 히스토리 추가 여부
        :return: Stock 인스턴스
        """
        existing_stock = Stock.get_or_none(Stock.symbol == symbol)
        if existing_stock:
            return existing_stock

        if not company_name:
            company_name = StockRepository.get_company_name(symbol)

        if not country:
            country = StockRepository.get_country_by_symbol(symbol)

        new_stock = Stock.create(symbol=symbol, company_name=company_name, country=country)

        if add_price_history:
            from repositories.price_repository import PriceRepository
            PriceRepository.add_for_symbol(
                symbol,
                start_date=datetime.datetime.now() - relativedelta(years=DEFAULT_PRICE_HISTORY_YEARS),
                end_date=datetime.datetime.now()
            )
        return new_stock

    @staticmethod
    def get_by_symbol(symbol: str) -> Stock:
        """종목코드로 종목 조회"""
        return Stock.get_or_none(Stock.symbol == symbol)

    @staticmethod
    def get_all(country: str = None):
        """전체 종목 조회"""
        stocks = Stock.select()
        if country:
            stocks = stocks.where(Stock.country == country)
        return stocks

    @staticmethod
    def delete_by_symbol(symbol: str):
        """종목 삭제"""
        Stock.delete().where(Stock.symbol == symbol).execute()

    @staticmethod
    def _process_listing(df, code_col, name_col, region):
        """시장 데이터를 처리하고 insert 함수를 병렬로 실행"""
        try:
            with ThreadPoolExecutor(max_workers=min(os.cpu_count(), MAX_WORKER_COUNT)) as executor:
                futures = [
                    executor.submit(StockRepository.insert, item[code_col], item[name_col], region)
                    for item in df.to_dict('records')
                ]

                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"Error while processing data: {e}")
        except Exception as e:
            logger.error(f"Error loading data for market: {e}")

    @staticmethod
    def update_listings():
        """KRX 및 미국 시장 데이터를 병렬로 처리"""
        try:
            df_kr = FinanceDataReader.StockListing('KRX')
            try:
                StockRepository._process_listing(df_kr, 'Code', 'Name', "KOR")
            except Exception as e:
                logger.error(f"Error insert KOR data: {e}")
        except Exception as e:
            logger.error(f"Error loading KOR data: {e}")

        try:
            df_us = pd.concat([
                FinanceDataReader.StockListing('S&P500'),
                FinanceDataReader.StockListing('NASDAQ'),
                FinanceDataReader.StockListing('NYSE')
            ])
            try:
                StockRepository._process_listing(df_us, "Symbol", "Name", "USA")
            except Exception as e:
                logger.error(f"Error insert USA data: {e}")
        except Exception as e:
            logger.error(f"Error loading USA data: {e}")
