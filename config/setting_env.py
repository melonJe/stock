"""
이 모듈은 환경 변수를 로드하고 다양한 설정을 구성하는 기능을 제공합니다.

사용법:
1. .env 파일에 환경 변수를 정의합니다.
2. 이 모듈을 임포트하여 환경 변수를 로드하고 필요한 설정을 가져옵니다.
3. 로깅을 통해 주요 이벤트와 오류를 기록합니다.
"""

import os

from dotenv import load_dotenv

load_dotenv()  # .env 파일에서 환경 변수를 로드


def get_env(key, default=None):
    """
    주어진 키에 해당하는 환경 변수를 가져옵니다. 환경 변수가 설정되지 않았고 기본값이 제공되지 않은 경우 예외를 발생시킵니다.

    Args:
        key (str): 가져올 환경 변수의 키.
        default (str, optional): 환경 변수가 설정되지 않은 경우 사용할 기본값. 기본값은 None입니다.

    Returns:
        str: 환경 변수의 값.

    Raises:
        ValueError: 환경 변수가 설정되지 않았고 기본값도 제공되지 않은 경우.
    """
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"환경 변수 {key}가 설정되지 않았습니다.")
    return value


def validate_api_credentials(app_key: str, app_secret: str, key_name: str) -> None:
    """
    API 키와 시크릿의 형식을 검증합니다.

    Args:
        app_key: 앱 키
        app_secret: 앱 시크릿
        key_name: 검증 대상 이름 (로깅용)

    Raises:
        ValueError: 형식이 올바르지 않은 경우
    """
    if not app_key or len(app_key) < 10:
        raise ValueError(f"{key_name} APP_KEY가 유효하지 않습니다. (최소 10자)")
    if not app_secret or len(app_secret) < 10:
        raise ValueError(f"{key_name} APP_SECRET이 유효하지 않습니다. (최소 10자)")


# 환경 변수 읽기 및 기본값 설정
DB_HOST = get_env("DB_HOST", "stock_db")
DB_PORT = int(get_env("DB_PORT", "5432"))
DB_NAME = get_env("DB_NAME")
DB_USER = get_env("DB_USER")
DB_PASS = get_env("DB_PASS")

# 디스코드 메시지 설정
DISCORD_MESSAGE_URL = get_env("DISCORD_MESSAGE_URL")
DISCORD_ERROR_URL = get_env("DISCORD_ERROR_URL")

# API 키와 시뮬레이션 모드
SIMULATE = get_env("SIMULATE", "true").lower() not in ['false', 'f']
TR_ID = "V" if SIMULATE else "T"
DOMAIN = "https://openapivts.koreainvestment.com:29443" if SIMULATE else "https://openapi.koreainvestment.com:9443"
APP_KEY_KOR = get_env("APP_KEY_KOR")
APP_SECRET_KOR = get_env("APP_SECRET_KOR")
ACCOUNT_NUMBER_KOR = get_env("ACCOUNT_NUMBER_KOR")
ACCOUNT_CODE_KOR = get_env("ACCOUNT_CODE_KOR")
validate_api_credentials(APP_KEY_KOR, APP_SECRET_KOR, "KOR")

APP_KEY_USA = get_env("APP_KEY_USA")
APP_SECRET_USA = get_env("APP_SECRET_USA")
ACCOUNT_NUMBER_USA = get_env("ACCOUNT_NUMBER_USA")
ACCOUNT_CODE_USA = get_env("ACCOUNT_CODE_USA")
validate_api_credentials(APP_KEY_USA, APP_SECRET_USA, "USA")

APP_KEY_ETF = get_env("APP_KEY_ETF")
APP_SECRET_ETF = get_env("APP_SECRET_ETF")
ACCOUNT_NUMBER_ETF = get_env("ACCOUNT_NUMBER_ETF")
ACCOUNT_CODE_ETF = get_env("ACCOUNT_CODE_ETF")
validate_api_credentials(APP_KEY_ETF, APP_SECRET_ETF, "ETF")

HTS_ID_ETF = get_env("HTS_ID_ETF")

# 매매 전략 관련
EQUITY_USD = get_env("EQUITY_USD")

# 주요 환경 변수 로그
from config.logging_config import get_logger
logger = get_logger(__name__)
logger.info("환경 변수가 성공적으로 로드되었습니다.")
