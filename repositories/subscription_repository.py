"""구독 종목 데이터 접근"""
import datetime
import logging

import pandas as pd
import requests

from data.models import Subscription
from services.tradingview_scan import build_tradingview_payload, request_tradingview_scan
from utils.data_util import upsert_many
from config.constants import (
    TICKER_INDEX,
    DIVIDEND_YIELD_INDEX,
    DIVIDEND_PAYOUT_RATIO_INDEX,
    CONTINUOUS_DIVIDEND_INDEX,
    CASH_FLOW_INDEX,
    NET_INCOME_INDEX,
)


class SubscriptionRepository:
    """구독 종목 Repository"""

    @staticmethod
    def get_all():
        """전체 구독 종목 조회"""
        return Subscription.select()

    @staticmethod
    def get_by_category(category: str):
        """카테고리별 구독 종목 조회"""
        return Subscription.select().where(Subscription.category == category)

    @staticmethod
    def delete_all():
        """전체 구독 종목 삭제"""
        Subscription.delete().execute()

    @staticmethod
    def upsert_many(data_list: list):
        """구독 종목 일괄 저장"""
        if data_list:
            upsert_many(Subscription, data_list, [Subscription.symbol])

    @staticmethod
    def filter_dividend_stocks(
            country: str = "korea",
            min_yield: float = 2.0,
            min_continuous_dividend_payout: int = 10,
            payout_ratio: bool = True,
            min_payout_ratio: float = 30.0,
            max_payout_ratio: float = 50.0,
            conversion_ratio: bool = True,
            min_conversion_ratio: float = 1,
            max_count: int = 20000
    ) -> set:
        """배당주 필터링"""
        columns = [
            "name", "description", "logoid", "update_mode", "type", "typespecs",
            "dividends_yield",
            "dividend_payout_ratio_ttm",
            "continuous_dividend_payout",
            "cash_f_operating_activities_ttm",
            "net_income_fy",
            "exchange",
        ]
        payload = build_tradingview_payload(
            columns=columns,
            max_count=max_count,
            sort={"sortBy": "dividends_yield", "sortOrder": "desc"},
            markets=["america"],
        )

        try:
            result = request_tradingview_scan(country, payload)
            data_list = []
            for item in result.get("data", []):
                values = item.get("d", [])
                try:
                    data_dict = {
                        'ticker': values[TICKER_INDEX] if len(values) > TICKER_INDEX else None,
                        'dividend_yield': float(values[DIVIDEND_YIELD_INDEX]) if values[DIVIDEND_YIELD_INDEX] is not None else None,
                        'dividend_payout_ratio_ttm': float(values[DIVIDEND_PAYOUT_RATIO_INDEX]) if values[DIVIDEND_PAYOUT_RATIO_INDEX] is not None else None,
                        'continuous_dividend_payout': int(values[CONTINUOUS_DIVIDEND_INDEX]) if values[CONTINUOUS_DIVIDEND_INDEX] is not None else None,
                        'cash_conversion_ratio': float(values[CASH_FLOW_INDEX]) / float(values[NET_INCOME_INDEX]) if values[NET_INCOME_INDEX] else None
                    }
                    data_list.append(data_dict)
                except (ValueError, TypeError, IndexError):
                    continue

            df = pd.DataFrame(data_list)

            if df.empty:
                logging.warning("filter_dividend_stocks: 데이터가 없습니다.")
                return set()

            df = df[
                (df['dividend_yield'] > min_yield) &
                (df['continuous_dividend_payout'] >= min_continuous_dividend_payout)
            ]

            if payout_ratio:
                df = df[(df['dividend_payout_ratio_ttm'] >= min_payout_ratio) &
                        (df['dividend_payout_ratio_ttm'] <= max_payout_ratio)]

            if conversion_ratio:
                df = df[(df['cash_conversion_ratio'] >= min_conversion_ratio)]

            return set(df['ticker'].tolist())

        except requests.RequestException as e:
            logging.error(f"filter_dividend_stocks 요청 실패: {e}")
            return set()
        except Exception as e:
            logging.error(f"filter_dividend_stocks 오류 발생: {e}")
            return set()

    @staticmethod
    def filter_growth_stocks(
            country: str = "korea",
            min_rev_cagr: float = 10.0,
            min_eps_cagr: float = 10.0,
            min_roe: float = 10.0,
            max_debt_to_equity: float = 100.0,
            min_current_ratio: float = 1.0,
            max_peg: float = 1.5,
            max_count: int = 20000
    ) -> set:
        """성장주 필터링"""
        columns = [
            "name",
            "total_revenue_cagr_5y", "total_revenue_yoy_growth_fy",
            "earnings_per_share_basic_ttm",
            "return_on_equity_fq",
            "debt_to_equity_fy",
            "current_ratio_fy",
            "price_earnings_ttm",
            "price_earnings_growth_ttm",
            "net_income_fq", "net_income_fh", "net_income_fy", "net_income_ttm"
        ]

        payload = build_tradingview_payload(
            columns=columns,
            max_count=max_count,
            sort={"sortBy": "market_cap_basic", "sortOrder": "desc"},
            markets=[country],
            ignore_unknown_fields=True,
        )

        try:
            result = request_tradingview_scan(country, payload)

            data_list = []
            for item in result.get("data", []):
                values = item.get("d", [])
                try:
                    data_dict = {
                        'ticker': values[0] if len(values) > 0 else None,
                        'revenue_cagr_5y': float(values[1]) if values[1] is not None else None,
                        'revenue_yoy_growth': float(values[2]) if values[2] is not None else None,
                        'eps_basic_ttm': float(values[3]) if values[3] is not None else None,
                        'roe_fq': float(values[4]) if values[4] is not None else None,
                        'debt_to_equity_fy': float(values[5]) if values[5] is not None else None,
                        'current_ratio_fy': float(values[6]) if values[6] is not None else None,
                        'pe_ttm': float(values[7]) if values[7] is not None else None,
                        'peg_ttm': float(values[8]) if values[8] is not None else None,
                    }
                    data_list.append(data_dict)
                except (ValueError, TypeError, IndexError):
                    continue

            df = pd.DataFrame(data_list)

            if df.empty:
                logging.warning("filter_growth_stocks: 데이터가 없습니다.")
                return set()

            df = df[
                (df['revenue_cagr_5y'] >= min_rev_cagr) &
                (df['roe_fq'] >= min_roe) &
                (df['debt_to_equity_fy'] <= max_debt_to_equity) &
                (df['current_ratio_fy'] >= min_current_ratio) &
                (df['peg_ttm'] <= max_peg) &
                (df['peg_ttm'] > 0)
            ]

            return set(df['ticker'].tolist())

        except requests.RequestException as e:
            logging.error(f"filter_growth_stocks 요청 실패: {e}")
            return set()
        except Exception as e:
            logging.error(f"filter_growth_stocks 오류 발생: {e}")
            return set()

    @staticmethod
    def filter_box_pattern_stocks(
            country: str = "korea",
            min_ebitda_ttm: float = 0.0,
            min_cash_f_operating_activities_ttm: float = 0.0,
            max_debt_to_equity: float = 100.0,
            min_revenue_growth: float = 10.0,
            min_roe: float = 10.0,
            min_oper_margin: float = 8.0,
            min_current_ratio: float = 1.2,
            max_per: float = 20.0,
            min_market_cap_quantile: float = 0.9,
            max_count: int = 20000
    ) -> set:
        """박스권 패턴 종목 필터링"""
        columns = [
            "name",
            "ebitda_ttm",
            "cash_f_operating_activities_ttm",
            "debt_to_equity_fy",
            "revenue_one_year_growth_ttm",
            "return_on_equity_fq",
            "oper_income_margin_fy",
            "current_ratio_fy",
            "price_earnings_ttm",
            "market_cap_basic"
        ]

        payload = build_tradingview_payload(
            columns=columns,
            max_count=max_count,
            sort={"sortBy": "market_cap_basic", "sortOrder": "desc"},
            markets=[country],
            ignore_unknown_fields=True,
        )

        try:
            result = request_tradingview_scan(country, payload)

            data_list = []
            for item in result.get("data", []):
                values = item.get("d", [])
                try:
                    data_dict = {
                        'ticker': values[0] if len(values) > 0 else None,
                        'ebitda_ttm': float(values[1]) if values[1] is not None else None,
                        'cash_f_operating_activities_ttm': float(values[2]) if values[2] is not None else None,
                        'debt_to_equity_fy': float(values[3]) if values[3] is not None else None,
                        'revenue_one_year_growth_ttm': float(values[4]) if values[4] is not None else None,
                        'roe_fq': float(values[5]) if values[5] is not None else None,
                        'oper_income_margin_fy': float(values[6]) if values[6] is not None else None,
                        'current_ratio_fy': float(values[7]) if values[7] is not None else None,
                        'pe_ttm': float(values[8]) if values[8] is not None else None,
                        'market_cap': float(values[9]) if values[9] is not None else None,
                    }
                    data_list.append(data_dict)
                except (ValueError, TypeError, IndexError):
                    continue

            df = pd.DataFrame(data_list)

            if df.empty:
                logging.warning("filter_box_pattern_stocks: 데이터가 없습니다.")
                return set()

            market_cap_threshold = df['market_cap'].quantile(min_market_cap_quantile)

            df = df[
                (df['ebitda_ttm'] >= min_ebitda_ttm) &
                (df['cash_f_operating_activities_ttm'] >= min_cash_f_operating_activities_ttm) &
                (df['debt_to_equity_fy'] <= max_debt_to_equity) &
                (df['revenue_one_year_growth_ttm'] >= min_revenue_growth) &
                (df['roe_fq'] >= min_roe) &
                (df['oper_income_margin_fy'] >= min_oper_margin) &
                (df['current_ratio_fy'] >= min_current_ratio) &
                (df['pe_ttm'] <= max_per) &
                (df['pe_ttm'] > 0) &
                (df['market_cap'] >= market_cap_threshold)
            ]

            return set(df['ticker'].tolist())

        except requests.RequestException as e:
            logging.error(f"filter_box_pattern_stocks 요청 실패: {e}")
            return set()
        except Exception as e:
            logging.error(f"filter_box_pattern_stocks 오류 발생: {e}")
            return set()

    @staticmethod
    def update_all():
        """전체 구독 종목 업데이트"""
        logging.info(f'{datetime.datetime.now()} update_subscription_stock 시작')
        data_to_insert = []

        # 한국 배당주
        data_to_insert.extend([
            {'symbol': symbol, 'category': 'dividend'}
            for symbol in SubscriptionRepository.filter_dividend_stocks(
                country="korea", min_yield=2.0, min_continuous_dividend_payout=3,
                min_payout_ratio=0, max_payout_ratio=50
            )
        ])
        # 미국 배당주
        data_to_insert.extend([
            {'symbol': symbol, 'category': 'dividend'}
            for symbol in SubscriptionRepository.filter_dividend_stocks(
                country="america", min_yield=2.0, min_continuous_dividend_payout=5,
                min_payout_ratio=20, max_payout_ratio=60
            )
        ])

        # 한국 성장주
        data_to_insert.extend([
            {'symbol': symbol, 'category': 'growth'}
            for symbol in SubscriptionRepository.filter_growth_stocks(
                country="korea", min_rev_cagr=15.0, min_eps_cagr=10.0, min_roe=10.0,
                max_debt_to_equity=150.0, min_current_ratio=1.2, max_peg=1.15
            )
        ])
        # 미국 성장주
        data_to_insert.extend([
            {'symbol': symbol, 'category': 'growth'}
            for symbol in SubscriptionRepository.filter_growth_stocks(
                country="america", min_rev_cagr=20.0, min_eps_cagr=15, min_roe=15.0,
                max_debt_to_equity=100.0, min_current_ratio=1.5, max_peg=1.4
            )
        ])

        # 한국 박스권
        data_to_insert.extend([
            {'symbol': symbol, 'category': 'box'}
            for symbol in SubscriptionRepository.filter_box_pattern_stocks(
                country="korea", min_ebitda_ttm=0.0, min_cash_f_operating_activities_ttm=0.0,
                max_debt_to_equity=120.0, min_revenue_growth=12.0, min_roe=12.0,
                min_oper_margin=10.0, min_current_ratio=1.3, max_per=18.0,
                min_market_cap_quantile=0.92
            )
        ])
        # 미국 박스권
        data_to_insert.extend([
            {'symbol': symbol, 'category': 'box'}
            for symbol in SubscriptionRepository.filter_box_pattern_stocks(
                country="america", min_ebitda_ttm=0.0, min_cash_f_operating_activities_ttm=0.0,
                max_debt_to_equity=100.0, min_revenue_growth=15.0, min_roe=15.0,
                min_oper_margin=12.0, min_current_ratio=1.4, max_per=22.0,
                min_market_cap_quantile=0.92
            )
        ])

        if data_to_insert:
            logging.info(f"{len(data_to_insert)}개 주식")
            SubscriptionRepository.delete_all()
            SubscriptionRepository.upsert_many(data_to_insert)
