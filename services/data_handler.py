import datetime
import json
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

from custom_exception.exception import NotFoundUrl
from data.models import Stock, PriceHistory, PriceHistoryUS, Subscription, Blacklist
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


def stock_dividend_filter(country="korea",
                          min_yield=2.0,
                          min_continuous_dividend_payout=10,
                          payout_ratio=True, min_payout_ratio=30.0, max_payout_ratio=50.0,
                          conversion_ratio=True, min_conversion_ratio=1,
                          max_count=20000):
    url = f"https://scanner.tradingview.com/{country}/scan?label-product=screener-stock"
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",
        "Accept": "application/json",
        "Origin": "https://kr.tradingview.com",
        "Referer": "https://kr.tradingview.com/",
        "User-Agent": "Mozilla/5.0"
    }

    payload = {
        "symbols": {},
        "columns": ["name", "description", "logoid", "update_mode", "type", "typespecs",
                    "dividends_yield",
                    "dividend_payout_ratio_ttm",
                    "continuous_dividend_payout",
                    "cash_f_operating_activities_ttm",
                    "net_income_fy",
                    "exchange"
                    ],
        "filter": [
            {"left": "is_primary", "operation": "equal", "right": True}
        ],
        "filter2": {
            "operator": "and",
            "operands": [
                {
                    "operation": {
                        "operator": "or",
                        "operands": [
                            {
                                "operation": {
                                    "operator": "and",
                                    "operands": [
                                        {"expression": {"left": "type", "operation": "equal", "right": "stock"}},
                                        {"expression": {"left": "typespecs", "operation": "has", "right": ["common"]}}
                                    ]
                                }
                            },
                            {
                                "operation": {
                                    "operator": "and",
                                    "operands": [
                                        {"expression": {"left": "type", "operation": "equal", "right": "stock"}},
                                        {"expression": {"left": "typespecs", "operation": "has",
                                                        "right": ["preferred"]}}
                                    ]
                                }
                            },
                            {
                                "operation": {
                                    "operator": "and",
                                    "operands": [
                                        {"expression": {"left": "type", "operation": "equal", "right": "dr"}}
                                    ]
                                }
                            },
                            {
                                "operation": {
                                    "operator": "and",
                                    "operands": [
                                        {"expression": {"left": "type", "operation": "equal", "right": "fund"}},
                                        {"expression": {"left": "typespecs", "operation": "has_none_of",
                                                        "right": ["etf"]}}
                                    ]
                                }
                            }
                        ]
                    }
                }
            ]
        },
        "ignore_unknown_fields": False,
        "markets": ["america"],
        "options": {"lang": "ko"},
        "range": [0, max_count],
        "sort": {
            "sortBy": "dividends_yield",
            "sortOrder": "desc"
        }
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        result = response.json()
        # 데이터를 pandas DataFrame으로 변환
        data_list = []
        for item in result.get("data", []):
            values = item.get("d", [])
            try:
                data_dict = {
                    'ticker': values[0] if len(values) > 0 else None,  # 주식 티커
                    'dividend_yield': float(values[6]) if values[6] is not None else None,  # 배당 수익률
                    'dividend_payout_ratio_ttm': float(values[7]) if values[7] is not None else None,  # 배당금 / 주당 순이익
                    'continuous_dividend_payout': int(values[8]) if values[8] is not None else None,  # 연속 배당 지불 (1년)
                    'cash_conversion_ratio': float(values[9]) / float(values[10]) if values[10] else None
                }
                data_list.append(data_dict)
            except (ValueError, TypeError, IndexError):
                continue

        # DataFrame 생성
        df = pd.DataFrame(data_list)

        if df.empty:
            print("데이터가 없습니다.")
            return set()

        # 조건 필터링
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
        print(f"요청 실패: {e}")
        return set()
    except Exception as e:
        print(f"오류 발생: {e}")
        return set()


def stock_growth_filter(country="korea",
                        min_rev_cagr: float = 10.0,
                        min_eps_cagr: float = 10.0,
                        min_roe: float = 10.0,
                        max_debt_to_equity: float = 100.0,
                        min_current_ratio: float = 1.0,
                        max_peg: float = 1.5,
                        max_count: int = 20000):
    url = f"https://scanner.tradingview.com/{country}/scan?label-product=screener-stock"
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",
        "Accept": "application/json",
        "Origin": "https://kr.tradingview.com",
        "Referer": "https://kr.tradingview.com/",
        "User-Agent": "Mozilla/5.0"
    }

    columns = [
        "name",
        "total_revenue_cagr_5y", "total_revenue_yoy_growth_fy",
        "earnings_per_share_basic_ttm",  # 후행 주당순이익
        "return_on_equity_fq",  # 후행 자기자본수익율
        "debt_to_equity_fy",  # 부채 비율
        "current_ratio_fy",  # 유동 비율
        "price_earnings_ttm",  # PER
        "price_earnings_growth_ttm",  # PEG
        "net_income_fq", "net_income_fh", "net_income_fy", "net_income_ttm"  # 순이익
    ]

    payload = {
        "symbols": {},
        "columns": columns,
        "filter": [
            {"left": "is_primary", "operation": "equal", "right": True}
        ],
        "filter2": {
            "operator": "and",
            "operands": [
                {
                    "operation": {
                        "operator": "or",
                        "operands": [
                            {
                                "operation": {
                                    "operator": "and",
                                    "operands": [
                                        {"expression": {"left": "type", "operation": "equal", "right": "stock"}},
                                        {"expression": {"left": "typespecs", "operation": "has", "right": ["common"]}}
                                    ]
                                }
                            },
                            {
                                "operation": {
                                    "operator": "and",
                                    "operands": [
                                        {"expression": {"left": "type", "operation": "equal", "right": "stock"}},
                                        {"expression": {"left": "typespecs", "operation": "has", "right": ["preferred"]}}
                                    ]
                                }
                            },
                            {
                                "operation": {
                                    "operator": "and",
                                    "operands": [
                                        {"expression": {"left": "type", "operation": "equal", "right": "dr"}}
                                    ]
                                }
                            },
                            {
                                "operation": {
                                    "operator": "and",
                                    "operands": [
                                        {"expression": {"left": "type", "operation": "equal", "right": "fund"}},
                                        {"expression": {"left": "typespecs", "operation": "has_none_of", "right": ["etf"]}}
                                    ]
                                }
                            }
                        ]
                    }
                }
            ]
        },
        "ignore_unknown_fields": True,
        "markets": [country],
        "options": {"lang": "ko"},
        "range": [0, max_count],
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"}
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        result = response.json()

        rows = []
        for item in result.get("data", []):
            values = item.get("d", [])
            row = dict(zip(columns, values))
            rows.append(row)

        df = pd.DataFrame(rows)
        if df.empty:
            return set()

        def pick(series, keys):
            for k in keys:
                if k in series and pd.notna(series[k]):
                    return series[k]
            return None

        df["rev_cagr"] = df.apply(lambda r: pick(r, ["total_revenue_cagr_5y", "total_revenue_yoy_growth_fy"]), axis=1)
        df["eps_cagr"] = df["earnings_per_share_basic_ttm"]
        df["roe"] = df.get("return_on_equity_fq")
        df["dte"] = df.get("debt_to_equity_fy")
        df["cr"] = df.get("current_ratio_fy")
        df["per"] = df.get("price_earnings_ttm")
        df["peg"] = df.get("price_earnings_growth_ttm")

        quarter_cols = [c for c in ["net_income_fq", "net_income_fh", "net_income_fy", "net_income_ttm"] if c in df.columns]

        def profits_ok(row):
            if quarter_cols and all(pd.notna(row.get(c)) for c in quarter_cols):
                try:
                    return all(float(row.get(c)) > 0 for c in quarter_cols)
                except Exception:
                    return False
            ttm = row.get("net_income_ttm")
            try:
                return pd.notna(ttm) and float(ttm) > 0
            except Exception:
                return False

        df["profits_ok"] = df.apply(profits_ok, axis=1)

        df["sel"] = (
                df["rev_cagr"].apply(lambda x: pd.notna(x) and float(x) >= float(min_rev_cagr)) &
                df["eps_cagr"].apply(lambda x: pd.notna(x) and float(x) >= float(min_eps_cagr)) &
                df["roe"].apply(lambda x: pd.notna(x) and float(x) >= float(min_roe)) &
                df["dte"].apply(lambda x: pd.notna(x) and float(x) <= float(max_debt_to_equity)) &
                df["cr"].apply(lambda x: pd.notna(x) and float(x) >= float(min_current_ratio)) &
                df["peg"].apply(lambda x: pd.notna(x) and float(x) <= float(max_peg)) &
                df["profits_ok"]
        )

        return set(df.loc[df['sel'] == True, 'name'].tolist())

    except requests.RequestException as e:
        print(f"요청 실패: {e}")
        return set()
    except Exception as e:
        print(f"오류 발생: {e}")
        return set()


def update_subscription_stock():
    logging.info(f'{datetime.datetime.now()} update_subscription_stock 시작')
    data_to_insert = []

    # 한국 배당주 프로세스
    data_to_insert.extend([{'symbol': symbol, 'category': 'dividend'} for symbol in stock_dividend_filter(country="korea", min_yield=2.0, min_continuous_dividend_payout=3, min_payout_ratio=0, max_payout_ratio=50)])
    # 미국 배당주 프로세스
    data_to_insert.extend([{'symbol': symbol, 'category': 'dividend'} for symbol in stock_dividend_filter(country="america", min_yield=2.0, min_continuous_dividend_payout=5, min_payout_ratio=20, max_payout_ratio=60)])

    # 한국 성장주 프로세스
    data_to_insert.extend([{'symbol': symbol, 'category': 'growth'} for symbol in stock_growth_filter(country="korea", min_rev_cagr=15.0, min_eps_cagr=10.0, min_roe=10.0, max_debt_to_equity=150.0, min_current_ratio=1.2, max_peg=1.15)])
    # 미국 성장주 프로세스
    data_to_insert.extend([{'symbol': symbol, 'category': 'growth'} for symbol in stock_growth_filter(country="america", min_rev_cagr=20.0, min_eps_cagr=15, min_roe=15.0, max_debt_to_equity=100.0, min_current_ratio=1.5, max_peg=1.4)])

    if data_to_insert:
        logging.info(f"{len(data_to_insert)}개 주식")
        Subscription.delete().execute()
        upsert_many(Subscription, data_to_insert, [Subscription.symbol])


def update_blacklist():
    urls = ('https://finance.naver.com/sise/management.naver', 'https://finance.naver.com/sise/trading_halt.naver',
            'https://finance.naver.com/sise/investment_alert.naver?type=caution',
            'https://finance.naver.com/sise/investment_alert.naver?type=warning',
            'https://finance.naver.com/sise/investment_alert.naver?type=risk')
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
                futures.append(executor.submit(add_price_for_symbol, stock.symbol, start_date, end_date))

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
    update_subscription_stock()
    # print(stock_dividend_filter(country="america", min_yield=2.0, min_continuous_dividend_payout=5, min_payout_ratio=20, max_payout_ratio=60))
    # print(len(stock_growth_filter(country="korea", min_rev_cagr=15.0, min_eps_cagr=10.0, min_roe=10.0, max_debt_to_equity=150.0, min_current_ratio=1.2, max_peg=1.15)))
    # print(len(stock_growth_filter(country="america", min_rev_cagr=20.0, min_eps_cagr=15, min_roe=15.0, max_debt_to_equity=100.0, min_current_ratio=1.5, max_peg=1.4)))
