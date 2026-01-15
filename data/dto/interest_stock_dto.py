"""관심종목 그룹/그룹별 종목 조회 API DTO 모음 (국내주식-204/203)."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class InterestGroupListRequestDTO:
    TYPE: str  # 관심종목구분코드 (예: 1)
    FID_ETC_CLS_CODE: str  # FID 기타 구분 코드
    USER_ID: str  # 사용자 ID


@dataclass
class InterestGroupListItemDTO:
    date: str  # 일자
    trnm_hour: str  # 전송 시간
    data_rank: str  # 데이터 순위
    inter_grp_code: str  # 관심 그룹 코드
    inter_grp_name: str  # 관심 그룹 명
    ask_cnt: str  # 요청 개수


@dataclass
class InterestGroupListResponseDTO:
    output2: List[InterestGroupListItemDTO]


@dataclass
class InterestGroupDetailRequestDTO:
    TYPE: str  # 관심종목구분코드 (예: 1)
    USER_ID: str  # 사용자 ID
    DATA_RANK: str  # 데이터 순위
    INTER_GRP_CODE: str  # 관심 그룹 코드
    INTER_GRP_NAME: str = ""  # 관심 그룹 명
    HTS_KOR_ISNM: str = ""  # HTS 한글 종목명
    CNTG_CLS_CODE: str = ""  # 체결 구분 코드
    FID_ETC_CLS_CODE: str = "4"  # 기타 구분 코드


@dataclass
class InterestGroupDetailInfoDTO:
    data_rank: str  # 데이터 순위
    inter_grp_name: str  # 관심 그룹 명


@dataclass
class InterestGroupDetailItemDTO:
    fid_mrkt_cls_code: str  # FID 시장 구분 코드
    data_rank: str  # 데이터 순위
    exch_code: str  # 거래소코드
    jong_code: str  # 종목코드
    color_code: str  # 색상 코드
    memo: str  # 메모
    hts_kor_isnm: str  # HTS 한글 종목명
    fxdt_ntby_qty: str  # 기준일 순매수 수량
    cntg_unpr: str  # 체결단가
    cntg_cls_code: str  # 체결 구분 코드


@dataclass
class InterestGroupDetailResponseDTO:
    output1: Optional[InterestGroupDetailInfoDTO]
    output2: List[InterestGroupDetailItemDTO]
