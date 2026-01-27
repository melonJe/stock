import math
from typing import Dict, Optional

from data.dto.holiday_dto import HolidayResponseDTO
from utils.price_constants import PRICE_TICK_LEVELS


def find_nth_open_day(holidays: Dict[str, HolidayResponseDTO], nth_day: int) -> Optional[str]:
    """nth 개장일을 찾습니다."""
    open_days = [date for date, info in sorted(holidays.items()) if info.opnd_yn == "Y"]
    if len(open_days) >= nth_day:
        return open_days[nth_day - 1]
    return None


def price_refine(price: int, tick_adjustment: int = 0) -> int:
    """한국 주식 호가 단위로 가격을 조정한다.
    
    Args:
        price: 조정할 가격
        tick_adjustment: 호가 단위 조정 횟수 (양수: 상향, 음수: 하향, 0: 반올림)
    
    Returns:
        호가 단위로 조정된 가격
    """
    if tick_adjustment == 0:
        for level_price, tick_size in PRICE_TICK_LEVELS:
            if price < level_price or level_price == float('inf'):
                return round(price / tick_size) * tick_size

    is_upward = tick_adjustment > 0
    adjustment_count = abs(tick_adjustment)

    for _ in range(adjustment_count):
        for level_price, tick_size in PRICE_TICK_LEVELS:
            if (is_upward and price < level_price) or level_price == float('inf'):
                price = (math.trunc(price / tick_size) + 1) * tick_size
                break
            elif (not is_upward and price <= level_price) or level_price == float('inf'):
                price = (math.ceil(price / tick_size) - 1) * tick_size
                break

    return int(price)
