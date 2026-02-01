"""입력값 검증 유틸리티"""
import re
from typing import Optional


class ValidationError(Exception):
    """입력값 검증 실패 예외"""
    pass


def validate_symbol(symbol: str, country: str = None) -> str:
    """
    종목코드를 검증하고 정규화한다.

    :param symbol: 종목코드
    :param country: 국가코드 (KOR, USA)
    :return: 정규화된 종목코드
    :raises ValidationError: 유효하지 않은 종목코드
    """
    if not symbol or not isinstance(symbol, str):
        raise ValidationError("종목코드가 비어있습니다.")

    symbol = symbol.strip().upper()

    if len(symbol) < 1 or len(symbol) > 12:
        raise ValidationError(f"종목코드 길이가 유효하지 않습니다: {symbol}")

    # 특수문자 검사 (알파벳, 숫자만 허용)
    if not re.match(r'^[A-Z0-9]+$', symbol):
        raise ValidationError(f"종목코드에 유효하지 않은 문자가 포함되어 있습니다: {symbol}")

    return symbol


def validate_price(price: float, min_value: float = 0, max_value: float = 1e12) -> float:
    """
    가격을 검증한다.

    :param price: 가격
    :param min_value: 최소값
    :param max_value: 최대값
    :return: 검증된 가격
    :raises ValidationError: 유효하지 않은 가격
    """
    try:
        price = float(price)
    except (TypeError, ValueError):
        raise ValidationError(f"가격이 숫자가 아닙니다: {price}")

    if price < min_value:
        raise ValidationError(f"가격이 최소값({min_value})보다 작습니다: {price}")

    if price > max_value:
        raise ValidationError(f"가격이 최대값({max_value})보다 큽니다: {price}")

    return price


def validate_volume(volume: int, min_value: int = 1, max_value: int = 1000000) -> int:
    """
    수량을 검증한다.

    :param volume: 수량
    :param min_value: 최소값
    :param max_value: 최대값
    :return: 검증된 수량
    :raises ValidationError: 유효하지 않은 수량
    """
    try:
        volume = int(volume)
    except (TypeError, ValueError):
        raise ValidationError(f"수량이 정수가 아닙니다: {volume}")

    if volume < min_value:
        raise ValidationError(f"수량이 최소값({min_value})보다 작습니다: {volume}")

    if volume > max_value:
        raise ValidationError(f"수량이 최대값({max_value})보다 큽니다: {volume}")

    return volume


def validate_order_type(order_type: str) -> str:
    """
    주문 유형을 검증한다.

    :param order_type: 주문 유형 코드
    :return: 검증된 주문 유형
    :raises ValidationError: 유효하지 않은 주문 유형
    """
    valid_types = {"00", "01", "03", "04", "05", "06"}

    if order_type not in valid_types:
        raise ValidationError(f"유효하지 않은 주문 유형입니다: {order_type}. 허용: {valid_types}")

    return order_type


def validate_date(date_str: str, format_str: str = "%Y%m%d") -> str:
    """
    날짜 문자열을 검증한다.

    :param date_str: 날짜 문자열
    :param format_str: 날짜 형식
    :return: 검증된 날짜 문자열
    :raises ValidationError: 유효하지 않은 날짜
    """
    from datetime import datetime

    if not date_str or not isinstance(date_str, str):
        raise ValidationError("날짜가 비어있습니다.")

    try:
        datetime.strptime(date_str, format_str)
        return date_str
    except ValueError:
        raise ValidationError(f"유효하지 않은 날짜 형식입니다: {date_str}. 형식: {format_str}")


def validate_country(country: str) -> str:
    """
    국가코드를 검증한다.

    :param country: 국가코드
    :return: 검증된 국가코드 (대문자)
    :raises ValidationError: 유효하지 않은 국가코드
    """
    valid_countries = {"KOR", "USA", "JPN", "CHN", "HKG", "VNM"}

    if not country:
        raise ValidationError("국가코드가 비어있습니다.")

    country = country.upper().strip()

    if country not in valid_countries:
        raise ValidationError(f"지원하지 않는 국가코드입니다: {country}. 허용: {valid_countries}")

    return country


__all__ = [
    "ValidationError",
    "validate_symbol",
    "validate_price",
    "validate_volume",
    "validate_order_type",
    "validate_date",
    "validate_country",
]
