from typing import Dict, Optional

from stock.dto.holiday_dto import HolidayResponseDTO


def find_nth_open_day(holidays: Dict[str, HolidayResponseDTO], nth_day: int) -> Optional[str]:
    """nth 개장일을 찾습니다."""
    open_days = [date for date, info in sorted(holidays.items()) if info.opnd_yn == "Y"]
    if len(open_days) >= nth_day:
        return open_days[nth_day - 1]
    return None
