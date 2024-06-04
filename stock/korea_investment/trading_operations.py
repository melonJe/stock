import logging
import math
import traceback
from typing import Dict, Optional

from stock.discord import discord
from stock.dto.holiday_dto import HolidayResponseDTO
from stock.korea_investment.api import KoreaInvestmentAPI


def log_and_handle_exception(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            traceback.print_exc()
            logging.error(f"Error occurred: {e}")

    return wrapper


def find_nth_open_day(holidays: Dict[str, HolidayResponseDTO], nth_day: int) -> Optional[str]:
    """nth 개장일을 찾습니다."""
    open_days = [date for date, info in sorted(holidays.items()) if info.opnd_yn == "Y"]
    if len(open_days) >= nth_day:
        return open_days[nth_day - 1]
    return None


def price_refine(price: int, number: int = 0) -> int:
    PRICE_LEVELS = [(2000, 1), (5000, 5), (20000, 10), (50000, 50), (200000, 100), (500000, 500), (float('inf'), 1000)]

    if number == 0:
        for level_price, adjustment in PRICE_LEVELS:
            if price < level_price or level_price == float('inf'):
                return round(price / adjustment) * adjustment

    increase = number > 0
    number_of_adjustments = abs(number)

    for _ in range(number_of_adjustments):
        for level_price, adjustment in PRICE_LEVELS:
            if (increase and price < level_price) or level_price == float('inf'):
                price = (math.trunc(price / adjustment) + 1) * adjustment
                break
            elif (not increase and price <= level_price) or level_price == float('inf'):
                price = (math.ceil(price / adjustment) - 1) * adjustment
                break

    return int(price)


@log_and_handle_exception
def buy_stock(ki_api: KoreaInvestmentAPI, symbol: str, price: int, volume: int):
    if volume > 0:
        ki_api.buy(symbol=symbol, price=price, volume=volume)
        discord.send_message(f"{symbol} 주식 {price}원으로 {volume}수량 구매 = {price * volume:,}")


@log_and_handle_exception
def reserve_buy_stock(ki_api: KoreaInvestmentAPI, symbol: str, price: int, volume: int, end_date: str):
    if volume > 0:
        ki_api.buy_reserve(symbol=symbol, price=price, volume=volume, end_date=end_date)
        # discord.send_message(f"{symbol} 주식 {price}원으로 {volume}수량 예약 구매 = {price * volume:,}")


def validate_and_adjust_volume(stock, requested_volume):
    if not stock or int(stock.ord_psbl_qty) == 0:
        logging.info(f"{stock.prdt_name if stock else '주식'} 가지고 있지 않거나 주문 가능한 수량이 없음")
        return 0
    return min(requested_volume, int(stock.ord_psbl_qty))


@log_and_handle_exception
def sell_stock(ki_api: KoreaInvestmentAPI, symbol: str, price: int, volume: int):
    stock = ki_api.get_owned_stock_info(symbol)
    volume = validate_and_adjust_volume(stock, volume)
    if volume > 0:
        if ki_api.sell(symbol=symbol, price=price, volume=volume):
            return True


@log_and_handle_exception
def reserve_sell_stock(ki_api: KoreaInvestmentAPI, symbol: str, price: int, volume: int, end_date: str):
    stock = ki_api.get_owned_stock_info(symbol)
    volume = validate_and_adjust_volume(stock, volume)
    if volume > 0:
        if ki_api.sell_reserve(symbol=symbol, price=price, volume=volume, end_date=end_date):
            return True
