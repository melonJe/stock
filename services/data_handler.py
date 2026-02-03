import datetime
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs

import FinanceDataReader
import pandas as pd
import requests
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta

from config.logging_config import get_logger
from core.exceptions import NotFoundError as NotFoundUrl
from data.models import Stock, Subscription, Blacklist
from repositories.stock_repository import StockRepository
from services.tradingview_scan import (
    build_tradingview_payload,
    request_tradingview_scan,
)
from utils.data_util import upsert_many
from config.constants import (
    KOREAN_STOCK_PATTERN,
    AMERICA_STOCK_PATTERN,
    MAX_WORKER_COUNT,
    BLACKLIST_RETENTION_DAYS,
    DEFAULT_PRICE_HISTORY_YEARS,
    TICKER_INDEX,
    DIVIDEND_YIELD_INDEX,
    DIVIDEND_PAYOUT_RATIO_INDEX,
    CONTINUOUS_DIVIDEND_INDEX,
    CASH_FLOW_INDEX,
    NET_INCOME_INDEX,
)

logger = get_logger(__name__)


# StockRepository로 위임
def get_company_name(symbol: str) -> str:
    return StockRepository.get_company_name(symbol)


def get_country_by_symbol(symbol: str) -> str:
    return StockRepository.get_country_by_symbol(symbol)


def get_history_table(country: str):
    return StockRepository.get_history_table(country)


def insert_stock(symbol: str, company_name: str = None, country: str = None):
    existing_stock = Stock.get_or_none(Stock.symbol == symbol)
    if existing_stock:
        return existing_stock

    if not company_name:
        company_name = get_company_name(symbol)

    if not country:
        country = get_country_by_symbol(symbol)

    new_stock = Stock.create(symbol=symbol, company_name=company_name, country=country)
    add_price_for_symbol(symbol, start_date=datetime.datetime.now() - relativedelta(years=DEFAULT_PRICE_HISTORY_YEARS), end_date=datetime.datetime.now())
    return new_stock


def stock_dividend_filter(country="korea",
                          min_yield=2.0,
                          min_continuous_dividend_payout=10,
                          payout_ratio=True, min_payout_ratio=30.0, max_payout_ratio=50.0,
                          conversion_ratio=True, min_conversion_ratio=1,
                          max_count=20000):
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
        # 데이터를 pandas DataFrame으로 변환
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

        # DataFrame 생성
        df = pd.DataFrame(data_list)

        if df.empty:
            logger.warning("stock_dividend_filter: 데이터가 없습니다.")
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
        logger.error(f"stock_dividend_filter 요청 실패: {e}")
        return set()
    except Exception as e:
        logger.error(f"stock_dividend_filter 오류 발생: {e}")
        return set()


def stock_growth_filter(country="korea",
                        min_rev_cagr: float = 10.0,
                        min_eps_cagr: float = 10.0,
                        min_roe: float = 10.0,
                        max_debt_to_equity: float = 100.0,
                        min_current_ratio: float = 1.0,
                        max_peg: float = 1.5,
                        max_count: int = 20000):
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

    payload = build_tradingview_payload(
        columns=columns,
        max_count=max_count,
        sort={"sortBy": "market_cap_basic", "sortOrder": "desc"},
        markets=[country],
        ignore_unknown_fields=True,
    )

    try:
        result = request_tradingview_scan(country, payload)

        rows = []
        for item in result.get("data", []):
            values = item.get("d", [])
            row = dict(zip(columns, values))
            rows.append(row)

        df = pd.DataFrame(rows)
        if df.empty:
            return set()

        def get_first_available_value(series, keys):
            for k in keys:
                if k in series and pd.notna(series[k]):
                    return series[k]
            return None

        df["rev_cagr"] = df.apply(lambda r: get_first_available_value(r, ["total_revenue_cagr_5y", "total_revenue_yoy_growth_fy"]), axis=1)
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

        return set(df.loc[df['sel'], 'name'].tolist())

    except requests.RequestException as e:
        logger.error(f"stock_growth_filter 요청 실패: {e}")
        return set()
    except Exception as e:
        logger.error(f"stock_growth_filter 오류 발생: {e}")
        return set()


def stock_box_pattern_filter(
        country: str = "korea",
        min_ebitda_ttm: float = 0.0,
        min_cash_f_operating_activities_ttm: float = 0.0,
        max_debt_to_equity: float = 1.5,
        min_revenue_growth: float = 15.0,
        min_roe: float = 12.0,
        min_oper_margin: float = 10.0,
        min_current_ratio: float = 1.3,
        max_per: float = 18.0,
        min_market_cap_quantile: float = 0.85,
        max_count: int = 20000,
):
    columns = [
        "name",
        "total_revenue_cagr_5y", "total_revenue_yoy_growth_fy",
        "ebitda_ttm",
        "debt_to_equity_fq",
        "cash_f_operating_activities_ttm",
        "return_on_equity_fq",
        "operating_margin_fy",
        "current_ratio_fy",
        "price_earnings_ttm",
        "market_cap_basic",
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

        rows = []
        for item in result.get("data", []):
            values = item.get("d", [])
            rows.append(dict(zip(columns, values)))

        df = pd.DataFrame(rows)
        if df.empty:
            return set()

        numeric_cols = [
            "total_revenue_cagr_5y",
            "total_revenue_yoy_growth_fy",
            "ebitda_ttm",
            "debt_to_equity_fq",
            "cash_f_operating_activities_ttm",
            "return_on_equity_fq",
            "operating_margin_fy",
            "current_ratio_fy",
            "price_earnings_ttm",
            "market_cap_basic",
        ]
        available_numeric_cols = [c for c in numeric_cols if c in df.columns]
        if available_numeric_cols:
            df[available_numeric_cols] = df[available_numeric_cols].apply(pd.to_numeric, errors="coerce")

        df["ebitda"] = df.get("ebitda_ttm")
        df["dte"] = df.get("debt_to_equity_fq")
        df["cash"] = df.get("cash_f_operating_activities_ttm")
        df["roe"] = df.get("return_on_equity_fq")
        df["op_margin"] = df.get("operating_margin_fy")
        df["cr"] = df.get("current_ratio_fy")
        df["per"] = df.get("price_earnings_ttm")
        df["mcap"] = df.get("market_cap_basic") if "market_cap_basic" in df.columns else None

        revenue_cols = ["total_revenue_cagr_5y", "total_revenue_yoy_growth_fy"]
        available_revenue_cols = [c for c in revenue_cols if c in df.columns]
        if available_revenue_cols:
            df["rev_growth"] = (
                df[available_revenue_cols]
                .bfill(axis=1)
                .iloc[:, 0]
            )
        else:
            df["rev_growth"] = None

        if "mcap" in df.columns and df["mcap"].notna().any():
            mcap_threshold = df["mcap"].quantile(min_market_cap_quantile)
            mcap_ok = df["mcap"].apply(lambda x: pd.notna(x) and float(x) >= float(mcap_threshold))
        else:
            mcap_ok = pd.Series([True] * len(df))

        df["sel"] = (
                df["ebitda"].apply(lambda x: pd.notna(x) and float(x) >= float(min_ebitda_ttm))
                & df["cash"].apply(lambda x: pd.notna(x) and float(x) >= float(min_cash_f_operating_activities_ttm))
                & df["dte"].apply(lambda x: pd.notna(x) and float(x) <= float(max_debt_to_equity))
                & df["rev_growth"].apply(lambda x: pd.notna(x) and float(x) >= float(min_revenue_growth))
                & df["roe"].apply(lambda x: pd.notna(x) and float(x) >= float(min_roe))
                & df["op_margin"].apply(lambda x: pd.notna(x) and float(x) >= float(min_oper_margin))
                & df["cr"].apply(lambda x: pd.notna(x) and float(x) >= float(min_current_ratio))
                & df["per"].apply(lambda x: pd.notna(x) and float(x) <= float(max_per))
                & mcap_ok
        )

        return set(df.loc[df["sel"], "name"].dropna().tolist())

    except requests.RequestException as e:
        logger.error(f"stock_box_pattern_filter 요청 실패: {e}")
        return set()
    except Exception as e:
        logger.error(f"stock_box_pattern_filter 오류 발생: {e}")
        return set()


def update_subscription_stock():
    """
    전략별 종목 업데이트 - 우선순위 적용
    
    우선순위: dividend(1) > growth(2) > box(3)
    동일 종목이 여러 전략에 해당할 경우 최우선 전략만 등록
    """
    from config.strategy_config import (
        STRATEGY_PRIORITY,
        DIVIDEND_CONFIG,
        GROWTH_CONFIG,
        RANGEBOX_CONFIG,
    )
    
    logger.info(f'{datetime.datetime.now()} update_subscription_stock 시작')
    
    # 전략별 종목 수집 (symbol -> category 매핑)
    strategy_candidates: dict[str, list[str]] = {}  # symbol -> [categories]
    
    # 1. 배당주 (최우선) - 배당수익률 3%+, 배당성향 40-80%
    dividend_kor = stock_dividend_filter(
        country="korea",
        min_yield=DIVIDEND_CONFIG.min_yield_kor,
        min_continuous_dividend_payout=DIVIDEND_CONFIG.min_continuous_dividend_kor,
        min_payout_ratio=DIVIDEND_CONFIG.min_payout_ratio,
        max_payout_ratio=DIVIDEND_CONFIG.max_payout_ratio
    )
    dividend_usa = stock_dividend_filter(
        country="america",
        min_yield=DIVIDEND_CONFIG.min_yield_usa,
        min_continuous_dividend_payout=DIVIDEND_CONFIG.min_continuous_dividend_usa,
        min_payout_ratio=DIVIDEND_CONFIG.min_payout_ratio,
        max_payout_ratio=DIVIDEND_CONFIG.max_payout_ratio
    )
    for symbol in dividend_kor | dividend_usa:
        strategy_candidates.setdefault(symbol, []).append("dividend")
    
    # 2. 성장주
    growth_kor = stock_growth_filter(
        country="korea",
        min_rev_cagr=GROWTH_CONFIG.min_rev_cagr_kor,
        min_eps_cagr=GROWTH_CONFIG.min_eps_cagr_kor,
        min_roe=GROWTH_CONFIG.min_roe_kor,
        max_debt_to_equity=GROWTH_CONFIG.max_debt_to_equity_kor,
        min_current_ratio=GROWTH_CONFIG.min_current_ratio_kor,
        max_peg=GROWTH_CONFIG.max_peg_kor
    )
    growth_usa = stock_growth_filter(
        country="america",
        min_rev_cagr=GROWTH_CONFIG.min_rev_cagr_usa,
        min_eps_cagr=GROWTH_CONFIG.min_eps_cagr_usa,
        min_roe=GROWTH_CONFIG.min_roe_usa,
        max_debt_to_equity=GROWTH_CONFIG.max_debt_to_equity_usa,
        min_current_ratio=GROWTH_CONFIG.min_current_ratio_usa,
        max_peg=GROWTH_CONFIG.max_peg_usa
    )
    for symbol in growth_kor | growth_usa:
        strategy_candidates.setdefault(symbol, []).append("growth")
    
    # 3. 박스권
    box_kor = stock_box_pattern_filter(
        country="korea",
        min_ebitda_ttm=RANGEBOX_CONFIG.min_ebitda_kor,
        min_cash_f_operating_activities_ttm=RANGEBOX_CONFIG.min_cash_flow_kor,
        max_debt_to_equity=RANGEBOX_CONFIG.max_debt_to_equity_kor,
        min_revenue_growth=RANGEBOX_CONFIG.min_revenue_growth_kor,
        min_roe=RANGEBOX_CONFIG.min_roe_kor,
        min_oper_margin=RANGEBOX_CONFIG.min_oper_margin_kor,
        min_current_ratio=RANGEBOX_CONFIG.min_current_ratio_kor,
        max_per=RANGEBOX_CONFIG.max_per_kor,
        min_market_cap_quantile=RANGEBOX_CONFIG.min_market_cap_quantile_kor
    )
    box_usa = stock_box_pattern_filter(
        country="america",
        min_ebitda_ttm=RANGEBOX_CONFIG.min_ebitda_usa,
        min_cash_f_operating_activities_ttm=RANGEBOX_CONFIG.min_cash_flow_usa,
        max_debt_to_equity=RANGEBOX_CONFIG.max_debt_to_equity_usa,
        min_revenue_growth=RANGEBOX_CONFIG.min_revenue_growth_usa,
        min_roe=RANGEBOX_CONFIG.min_roe_usa,
        min_oper_margin=RANGEBOX_CONFIG.min_oper_margin_usa,
        min_current_ratio=RANGEBOX_CONFIG.min_current_ratio_usa,
        max_per=RANGEBOX_CONFIG.max_per_usa,
        min_market_cap_quantile=RANGEBOX_CONFIG.min_market_cap_quantile_usa
    )
    for symbol in box_kor | box_usa:
        strategy_candidates.setdefault(symbol, []).append("box")
    
    # 우선순위 적용: 각 종목에 대해 최우선 전략만 선택
    data_to_insert = []
    for symbol, categories in strategy_candidates.items():
        # 우선순위가 높은 전략 선택 (숫자가 작을수록 높음)
        best_category = min(categories, key=lambda c: STRATEGY_PRIORITY.get(c, 999))
        data_to_insert.append({'symbol': symbol, 'category': best_category})
    
    if data_to_insert:
        # 전략별 통계
        category_counts = {}
        for item in data_to_insert:
            cat = item['category']
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        logger.info(f"{len(data_to_insert)}개 종목 (dividend: {category_counts.get('dividend', 0)}, "
                    f"growth: {category_counts.get('growth', 0)}, box: {category_counts.get('box', 0)})")
        
        Subscription.delete().execute()
        upsert_many(Subscription, data_to_insert, [Subscription.symbol])


def update_blacklist():
    urls = ('https://finance.naver.com/sise/management.naver', 'https://finance.naver.com/sise/trading_halt.naver',
            'https://finance.naver.com/sise/investment_alert.naver?type=caution',
            'https://finance.naver.com/sise/investment_alert.naver?type=warning',
            'https://finance.naver.com/sise/investment_alert.naver?type=risk')
    blacklisted_symbols = set()
    for url in urls:
        page = requests.get(url, timeout=30).text
        soup = BeautifulSoup(page, "html.parser")
        elements = soup.select('a.tltle')
        for x in elements:
            parsed = parse_qs(urlparse(x['href']).query)
            if 'code' in parsed and parsed['code']:
                blacklisted_symbols.add(parsed['code'][0])
    data_to_insert = [{'symbol': x, 'record_date': datetime.datetime.now().strftime('%Y-%m-%d')} for x in blacklisted_symbols]
    if data_to_insert:
        upsert_many(Blacklist, data_to_insert, Blacklist.symbol, Blacklist.record_date)
    Blacklist.delete().where(Blacklist.record_date < datetime.datetime.now() - datetime.timedelta(days=BLACKLIST_RETENTION_DAYS)).execute()

    # TODO 미국 주식 Blacklist insert 프로세스 추가


def process_stock_listing(df, code_col, name_col, region):
    """
    주어진 시장 데이터를 처리하고, insert_stock 함수를 병렬로 실행.
    """
    try:
        with ThreadPoolExecutor(max_workers=min(os.cpu_count(), MAX_WORKER_COUNT)) as executor:
            futures = [
                executor.submit(insert_stock, item[code_col], item[name_col], region)
                for item in df.to_dict('records')
            ]

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Error while processing data: {e}")
    except Exception as e:
        logger.error(f"Error loading data for market: {e}")


def update_stock_listings():
    """
    KRX 및 미국 시장 데이터를 병렬로 처리.
    """

    try:
        df_kr = FinanceDataReader.StockListing('KRX')
        try:
            process_stock_listing(df_kr, 'Code', 'Name', "KOR")
        except Exception as e:
            logger.error(f"Error insert KOR data: {e}")
    except Exception as e:
        logger.error(f"Error loading KOR data: {e}")

    try:
        df_us = pd.concat([
            FinanceDataReader.StockListing('S&P500'),
            FinanceDataReader.StockListing('NASDAQ'),
            FinanceDataReader.StockListing('NYSE')  # 주석 해제 시 추가 가능
        ])
        try:
            process_stock_listing(df_us, "Symbol", "Name", "USA")
        except Exception as e:
            logger.error(f"Error insert USA data: {e}")
    except Exception as e:
        logger.error(f"Error loading USA data: {e}")


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
                    logger.error(f"에러 발생: {e}")


def add_price_for_symbol(symbol: str, start_date: datetime.datetime = None, end_date: datetime.datetime = None):
    start_date_str = (datetime.datetime.now() - relativedelta(days=5)).strftime('%Y-%m-%d') if not start_date else start_date.strftime('%Y-%m-%d')
    try:
        country = get_country_by_symbol(symbol)
        table = get_history_table(country)
        data_to_insert = None

        if country == "KOR":
            df = FinanceDataReader.DataReader(
                symbol=f'NAVER:{symbol}',
                start=start_date_str,
                end=end_date
            )
            if not df.empty:
                df = df.reset_index()
                df['symbol'] = symbol
                df['date'] = df['Date'].dt.date
                data_to_insert = df[['symbol', 'date', 'Open', 'High', 'Close', 'Low', 'Volume']].rename(
                    columns={'Open': 'open', 'High': 'high', 'Close': 'close', 'Low': 'low', 'Volume': 'volume'}
                ).to_dict('records')
        elif country == "USA":
            df = FinanceDataReader.DataReader(symbol=symbol, start=start_date_str, end=end_date)
            if not df.empty:
                df = df.reset_index()
                df['symbol'] = symbol
                df['date'] = df['Date'].dt.date
                df['open'] = df['Open'].astype(float)
                df['high'] = df['High'].astype(float)
                df['close'] = df['Close'].astype(float)
                df['low'] = df['Low'].astype(float)
                df['volume'] = df['Volume'].apply(lambda x: int(x) if pd.notna(x) else None)
                data_to_insert = df[['symbol', 'date', 'open', 'high', 'close', 'low', 'volume']].to_dict('records')

        if data_to_insert:
            upsert_many(table, data_to_insert, [table.symbol, table.date], ['open', 'high', 'close', 'low', 'volume'])

    except NotFoundUrl:
        Stock.delete().where(Stock.symbol == symbol).execute()
    except KeyError:
        pass
    except Exception:
        pass


if __name__ == "__main__":
    print(stock_box_pattern_filter(country="korea"))
    print(stock_box_pattern_filter(country="america"))