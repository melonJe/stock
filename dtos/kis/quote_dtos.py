"""국내주식 시세 조회 DTO"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class CurrentPriceRequestDTO:
    """현재가 조회 요청 DTO"""
    fid_cond_mrkt_div_code: str  # 시장 구분 코드 (J: 주식)
    fid_input_iscd: str  # 종목코드


@dataclass
class CurrentPriceResponseDTO:
    """현재가 조회 응답 DTO"""
    stck_prpr: int  # 주식 현재가
    stck_oprc: int  # 시가
    stck_hgpr: int  # 고가
    stck_lwpr: int  # 저가
    prdy_vrss: int  # 전일 대비
    prdy_vrss_sign: str  # 전일 대비 부호 (1:상한, 2:상승, 3:보합, 4:하한, 5:하락)
    prdy_ctrt: float  # 전일 대비율
    acml_vol: int  # 누적 거래량
    acml_tr_pbmn: int  # 누적 거래대금
    
    @classmethod
    def from_api_response(cls, output: dict) -> Optional["CurrentPriceResponseDTO"]:
        """API 응답에서 DTO 생성"""
        try:
            return cls(
                stck_prpr=int(output.get("stck_prpr", 0)),
                stck_oprc=int(output.get("stck_oprc", 0)),
                stck_hgpr=int(output.get("stck_hgpr", 0)),
                stck_lwpr=int(output.get("stck_lwpr", 0)),
                prdy_vrss=int(output.get("prdy_vrss", 0)),
                prdy_vrss_sign=output.get("prdy_vrss_sign", "3"),
                prdy_ctrt=float(output.get("prdy_ctrt", 0)),
                acml_vol=int(output.get("acml_vol", 0)),
                acml_tr_pbmn=int(output.get("acml_tr_pbmn", 0)),
            )
        except (KeyError, ValueError, TypeError):
            return None
