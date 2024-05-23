from datetime import datetime


def str_to_number(item: str):
    """문자열을 숫자로 변환합니다."""
    try:
        return int(item)
    except ValueError:
        try:
            return float(item)
        except ValueError:
            return item


def find_nth_open_day(holiday_data, nth_day: int) -> str:
    """오늘을 제외한 nth 개장일을 찾습니다."""
    open_days_found = 0
    for key, value in holiday_data.items():  # holiday_data should be a dictionary
        if value.get("opnd_yn") == "Y":  # Ensure the key exists and check its value
            if open_days_found == nth_day:
                return key
            open_days_found += 1
    return ''
