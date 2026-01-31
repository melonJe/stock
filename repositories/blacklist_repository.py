"""블랙리스트 데이터 접근"""
import datetime
import logging
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

from config.logging_config import get_logger
from data.models import Blacklist
from utils.data_util import upsert_many
from config.constants import BLACKLIST_RETENTION_DAYS

logger = get_logger(__name__)


class BlacklistRepository:
    """블랙리스트 Repository"""

    BLACKLIST_URLS = (
        'https://finance.naver.com/sise/management.naver',
        'https://finance.naver.com/sise/trading_halt.naver',
        'https://finance.naver.com/sise/investment_alert.naver?type=caution',
        'https://finance.naver.com/sise/investment_alert.naver?type=warning',
        'https://finance.naver.com/sise/investment_alert.naver?type=risk'
    )

    @staticmethod
    def get_all():
        """전체 블랙리스트 조회"""
        return Blacklist.select()

    @staticmethod
    def is_blacklisted(symbol: str) -> bool:
        """블랙리스트 여부 확인"""
        return Blacklist.get_or_none(Blacklist.symbol == symbol) is not None

    @staticmethod
    def update():
        """블랙리스트 업데이트"""
        blacklisted_symbols = set()

        for url in BlacklistRepository.BLACKLIST_URLS:
            try:
                page = requests.get(url, timeout=30).text
                soup = BeautifulSoup(page, "html.parser")
                elements = soup.select('a.tltle')
                blacklisted_symbols = blacklisted_symbols.union(
                    parse_qs(urlparse(x['href']).query)['code'][0] for x in elements
                )
            except Exception as e:
                logger.error(f"블랙리스트 URL 처리 오류 ({url}): {e}")
                continue

        data_to_insert = [
            {'symbol': x, 'record_date': datetime.datetime.now().strftime('%Y-%m-%d')}
            for x in blacklisted_symbols
        ]

        if data_to_insert:
            upsert_many(Blacklist, data_to_insert, Blacklist.symbol, Blacklist.record_date)

        # 오래된 블랙리스트 제거
        Blacklist.delete().where(
            Blacklist.record_date < datetime.datetime.now() - datetime.timedelta(days=BLACKLIST_RETENTION_DAYS)
        ).execute()

        # TODO: 미국 주식 Blacklist insert 프로세스 추가
