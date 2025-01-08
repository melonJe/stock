import math
from typing import Dict, Optional

from data.dto.holiday_dto import HolidayResponseDTO


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
