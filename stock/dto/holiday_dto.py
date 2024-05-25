from dataclasses import dataclass


@dataclass
class HolidayRequestDTO:
    bass_dt: str
    ctx_area_nk: str = ""
    ctx_area_fk: str = ""


@dataclass
class HolidayResponseDTO:
    bass_dt: str
    wday_dvsn_cd: str
    bzdy_yn: str
    tr_day_yn: str
    opnd_yn: str
    sttl_day_yn: str
