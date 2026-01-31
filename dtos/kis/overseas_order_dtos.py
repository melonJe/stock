"""해외주식 주문 DTO"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class OverseasReservationOrderRequestDTO:
    """해외주식 예약 주문 요청 DTO"""
    cano: str  # 종합계좌번호 (8자리)
    acnt_prdt_cd: str  # 계좌상품코드 (2자리)
    pdno: str  # 종목코드
    ovrs_excg_cd: str  # 해외거래소코드 (NASD, NYSE, AMEX 등)
    ft_ord_qty: int  # 주문수량
    ft_ord_unpr3: float  # 주문단가
    sll_buy_dvsn_cd: str  # 매도매수구분코드 (01: 매도, 02: 매수)
    ord_dvsn: str = "00"  # 주문구분 (00: 지정가)
    prdt_type_cd: str = ""  # 상품유형코드
    rvse_cncl_dvsn_cd: str = "00"  # 정정취소구분코드 (00: 신규)
    ord_svr_dvsn_cd: str = "0"  # 주문서버구분코드
    ovrs_rsvn_odno: str = ""  # 해외예약주문번호 (신규일 경우 공백)
    
    def to_payload(self) -> dict:
        """API 요청 페이로드로 변환"""
        return {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": self.pdno,
            "OVRS_EXCG_CD": self.ovrs_excg_cd,
            "FT_ORD_QTY": self.ft_ord_qty,
            "FT_ORD_UNPR3": self.ft_ord_unpr3,
            "SLL_BUY_DVSN_CD": self.sll_buy_dvsn_cd,
            "ORD_DVSN": self.ord_dvsn,
            "PRDT_TYPE_CD": self.prdt_type_cd,
            "RVSE_CNCL_DVSN_CD": self.rvse_cncl_dvsn_cd,
            "ORD_SVR_DVSN_CD": self.ord_svr_dvsn_cd,
            "OVRS_RSVN_ODNO": self.ovrs_rsvn_odno,
        }


@dataclass
class OverseasReservationOrderResponseDTO:
    """해외주식 예약 주문 응답 DTO"""
    rt_cd: str  # 응답코드 (0: 성공)
    msg_cd: str  # 메시지코드
    msg1: str  # 응답메시지
    ovrs_rsvn_odno: Optional[str] = None  # 해외예약주문번호
    
    @classmethod
    def from_api_response(cls, response: dict) -> "OverseasReservationOrderResponseDTO":
        """API 응답에서 DTO 생성"""
        output = response.get("output", {})
        return cls(
            rt_cd=response.get("rt_cd", ""),
            msg_cd=response.get("msg_cd", ""),
            msg1=response.get("msg1", ""),
            ovrs_rsvn_odno=output.get("OVRS_RSVN_ODNO"),
        )
    
    @property
    def is_success(self) -> bool:
        """주문 성공 여부"""
        return self.rt_cd == "0"
