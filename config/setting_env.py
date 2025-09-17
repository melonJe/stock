"""
이 모듈은 환경 변수를 로드하고 다양한 설정을 구성하는 기능을 제공합니다.

사용법:
1. .env 파일에 환경 변수를 정의합니다.
2. 이 모듈을 임포트하여 환경 변수를 로드하고 필요한 설정을 가져옵니다.
3. 로깅을 통해 주요 이벤트와 오류를 기록합니다.
"""

import logging
import os

from dotenv import load_dotenv

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
APP_KEY = get_env("APP_KEY")
APP_SECRET = get_env("APP_SECRET")
SIMULATE = get_env("SIMULATE", "true").lower() not in ['false', 'f']
TR_ID = "V" if SIMULATE else "T"
DOMAIN = "https://openapivts.koreainvestment.com:29443" if SIMULATE else "https://openapi.koreainvestment.com:9443"
ACCOUNT_NUMBER = get_env("ACCOUNT_NUMBER")
ACCOUNT_CODE = get_env("ACCOUNT_CODE")

# 주요 환경 변수 로그
logger.info("환경 변수가 성공적으로 로드되었습니다.")