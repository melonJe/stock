import datetime
import logging
import time
import traceback
from typing import Type

import pandas as pd
import requests
from dateutil.relativedelta import relativedelta
from peewee import Model

from data import models


def upsert(model: Type[Model], data: dict, conflict_target: list, preserve_fields: list):
    """
    범용 UPSERT 함수 (다중 필드 고유 인덱스 처리 포함)
    :param model: Peewee 모델 클래스
    :param data: 삽입할 데이터 딕셔너리 (e.g., {'field1': value1, 'field2': value2, ...})
    :param conflict_target: 중복 확인 키 리스트 (e.g., [Model.field1, Model.field2])
    :param preserve_fields: 충돌 시 업데이트할 필드 리스트 (e.g., ['field3', 'field4'])
    """
    if not data:
        return

    try:
        with models.db.atomic():
            model.insert(**data).on_conflict(
                conflict_target=conflict_target,
                preserve=preserve_fields
            ).execute()
    except Exception as e:
        logging.error(f"Upsert failed for model {model.__name__}: {e}")


def upsert_many(model: Type[Model], data: list, conflict_target: list = None, preserve_fields: list = None):
    """
    Peewee insert_many와 UPSERT를 결합하여 다중 데이터 처리
    :param model: Peewee 모델 클래스
    :param data: 삽입할 데이터의 리스트 (e.g., [{'field1': value1, ...}, ...])
    :param conflict_target: 중복 확인 키 리스트 (e.g., [Model.field1, Model.field2])
    :param preserve_fields: 충돌 시 업데이트할 필드 리스트 (e.g., ['field3', 'field4'])
    """
    if not data:
        return

    try:
        with models.db.atomic():
            if not conflict_target:
                model.insert_many(data).on_conflict().execute()
            elif not preserve_fields:
                model.insert_many(data).on_conflict(
                    conflict_target=conflict_target,
                    action='IGNORE'
                ).execute()
            else:
                model.insert_many(data).on_conflict(
                    conflict_target=conflict_target,
                    preserve=preserve_fields
                ).execute()
    except Exception as e:
        traceback.print_exc()
        logging.error(f"Upsert many failed for model {model.__name__}: {e}")


def get_yahoo_finance_data(symbol, unix_start_date, unix_end_date, interval='1d', retries=5, delay=5):
    base_url = "https://query1.finance.yahoo.com/v8/finance/chart/"
    params = {
        "events": "capitalGain|div|split",
        "formatted": "true",
        "includeAdjustedClose": "true",
        "interval": interval,
        "period1": unix_start_date,
        "period2": unix_end_date,
        "symbol": symbol,
        "userYfid": "true",
        "lang": "en-US",
        "region": "US"
    }

    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "DNT": "1",
        "Origin": "https://finance.yahoo.com",
        "Pragma": "no-cache",
        "Referer": "https://finance.yahoo.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }
    for attempt in range(retries):
        try:
            response = requests.get(base_url + symbol, params=params, headers=headers)
            response.raise_for_status()

            data = response.json()

            timestamps = data['chart']['result'][0]['timestamp']
            indicators = data['chart']['result'][0]['indicators']['quote'][0]
            close = indicators.get('close', [])
            open_prices = indicators.get('open', [])
            high = indicators.get('high', [])
            low = indicators.get('low', [])
            volume = indicators.get('volume', [])

            change = [(close[i] - close[i - 1]) / close[i - 1] if i > 0 else 0 for i in range(len(close))]

            df = pd.DataFrame({
                "Date": pd.to_datetime(timestamps, unit='s'),
                "Close": close,
                "Open": open_prices,
                "High": high,
                "Low": low,
                "Volume": volume,
                "Change": change
            })
            df.set_index("Date", inplace=True)

            return df

        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {symbol}")
            print(e)
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                print("All retries failed.")
                return None


if __name__ == "__main__":
    # symbol = "AAPL"
    # unix_start_date = "1704958797"
    # unix_end_date = "1736581197"
    # interval = "1d"
    #
    # df = get_yahoo_finance_data(symbol, unix_start_date, unix_end_date, interval)
    # if df is not None:
    #     print(df)
    print(int((datetime.datetime.now() - relativedelta(months=1)).timestamp()))
    get_yahoo_finance_data('AAPL', int((datetime.datetime.now() - relativedelta(days=4)).timestamp()), int(datetime.datetime.now().timestamp()))
