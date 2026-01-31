"""휴일 조회 API"""
from datetime import datetime
from typing import Dict, Optional

from clients.kis.base import KISBaseClient
from data.dto.holiday_dto import HolidayResponseDTO, HolidayRequestDTO
from utils.operations import find_nth_open_day


class HolidayClient(KISBaseClient):
    """휴일 조회 클라이언트"""

    def get_holidays(self, date: str) -> Dict[str, HolidayResponseDTO]:
        """
        국내 시장 휴일 조회

        :param date: 조회 기준 날짜 (YYYYMMDD)
        :return: 휴일 정보 딕셔너리 {날짜: HolidayResponseDTO}
        """
        headers = self._get_headers_with_tr_id("CTCA0903R", use_prefix=False)
        params = HolidayRequestDTO(bass_dt=date).__dict__
        response = self._get(
            "/uapi/domestic-stock/v1/quotations/chk-holiday",
            params,
            headers,
            error_log_prefix="Holiday API 요청 실패"
        )
        holidays = response.get("output", []) if response else []
        holiday_dtos = [HolidayResponseDTO(**item) for item in holidays]
        return {dto.bass_dt: dto for dto in holiday_dtos}

    def get_nth_open_day(self, nth_day: int) -> Optional[str]:
        """
        오늘 이후 n번째 개장일 조회

        :param nth_day: n번째 개장일
        :return: 개장일 (YYYYMMDD) 또는 None
        """
        holiday_keys = sorted(self.total_holidays.keys())
        current_date = holiday_keys[-1] if holiday_keys else datetime.now().strftime("%Y%m%d")

        while True:
            nth_open_day = find_nth_open_day(self.total_holidays, nth_day + 1)
            if nth_open_day:
                return nth_open_day

            holidays = self.get_holidays(current_date)
            self.total_holidays.update(holidays)
            current_date = max(holidays.keys(), default=current_date)

    def check_holiday(self, date: str) -> bool:
        """
        특정 날짜 휴장일 여부 확인

        :param date: 확인할 날짜 (YYYYMMDD)
        :return: 휴장일이면 True
        """
        holidays = self.get_holidays(date)
        holiday = holidays.get(date)
        return holiday.opnd_yn == "N" if holiday else False
