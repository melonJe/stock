from dataclasses import dataclass


@dataclass
class StockTradeListRequestDTO:
    CANO: str
    ACNT_PRDT_CD: str
    INQR_STRT_DT: str
    INQR_END_DT: str
    SLL_BUY_DVSN_CD: str = "00"
    INQR_DVSN: str = "00"
    PDNO: str = ""
    CCLD_DVSN: str = "00"
    ORD_GNO_BRNO: str = ""
    ODNO: str = ""
    INQR_DVSN_3: str = "00"
    INQR_DVSN_1: str = ""
    CTX_AREA_FK100: str = ""
    CTX_AREA_NK100: str = ""


@dataclass
class StockTradeListResponseDTO:
    ord_dt: str
    ord_gno_brno: str
    odno: str
    orgn_odno: str
    ord_dvsn_name: str
    sll_buy_dvsn_cd: str
    sll_buy_dvsn_cd_name: str
    pdno: str
    prdt_name: str
    ord_qty: str
    ord_unpr: str
    ord_tmd: str
    tot_ccld_qty: str
    avg_prvs: str
    cncl_yn: str
    tot_ccld_amt: str
    loan_dt: str
    ordr_empno: str
    ord_dvsn_cd: str
    cncl_cfrm_qty: str
    rmn_qty: str
    rjct_qty: str
    ccld_cndt_name: str
    infm_tmd: str
    ctac_tlno: str
    prdt_type_cd: str
    excg_dvsn_cd: str
    inqr_ip_addr: str
    cpbc_ordp_ord_rcit_dvsn_cd: str
    cpbc_ordp_infm_mthd_dvsn_cd: str
    cpbc_ordp_mtrl_dvsn_cd: str
    ord_orgno: str
    rsvn_ord_end_dt: str
    excg_id_dvsn_cd: str
    stpm_cndt_pric: str
    stpm_efct_occr_dtmd: str


@dataclass
class OverseasStockTradeListRequestDTO:
    cano: str  # 계좌번호 체계(8-2)의 앞 8자리
    acnt_prdt_cd: str  # 계좌번호 체계(8-2)의 뒤 2자리
    pdno: str  # 전종목 조회 시 "%" 입력
    ord_strt_dt: str  # YYYYMMDD 형식 (현지시각 기준)
    ord_end_dt: str  # YYYYMMDD 형식 (현지시각 기준)
    sll_buy_dvsn: str  # 00: 전체, 01: 매도, 02: 매수
    ccld_nccs_dvsn: str  # 00: 전체, 01: 체결, 02: 미체결
    ovrs_excg_cd: str  # 전종목 조회 시 "%" 입력
    sort_sqn: str  # DS: 정순, AS: 역순
    ord_dt: str = ""  # "" (Null 값 설정)
    ord_gno_brno: str = ""  # "" (Null 값 설정)
    odno: str = ""  # "" (Null 값 설정) — 주문번호로 검색 불가
    ctx_area_nk200: str = ""  # 연속조회키200 (공란: 최초 조회, 이전 조회값: 다음 페이지)
    ctx_area_fk200: str = ""  # 연속조회검색조건200 (공란: 최초 조회, 이전 조회값: 다음 페이지)


@dataclass
class OverseasStockTradeListResponseDTO:
    ord_dt: str  # 주문일자
    ord_gno_brno: str  # 주문채번지점번호
    odno: str  # 주문번호
    orgn_odno: str  # 원주문번호
    sll_buy_dvsn_cd: str  # 매도매수구분코드
    sll_buy_dvsn_cd_name: str  # 매도매수구분코드명
    rvse_cncl_dvsn: str  # 정정취소구분
    rvse_cncl_dvsn_name: str  # 정정취소구분명
    pdno: str  # 상품번호
    prdt_name: str  # 상품명
    ft_ord_qty: str  # FT주문수량
    ft_ord_unpr3: str  # FT주문단가3
    ft_ccld_qty: str  # FT체결수량
    ft_ccld_unpr3: str  # FT체결단가3
    ft_ccld_amt3: str  # FT체결금액3
    nccs_qty: str  # 미체결수량
    prcs_stat_name: str  # 처리상태명
    rjct_rson: str  # 거부사유
    ord_tmd: str  # 주문시각
    tr_mket_name: str  # 거래시장명
    tr_natn: str  # 거래국가
    tr_natn_name: str  # 거래국가명
    ovrs_excg_cd: str  # 해외거래소코드
    tr_crcy_cd: str  # 거래통화코드
    dmst_ord_dt: str  # 국내주문일자
    thco_ord_tmd: str  # 당사주문시각
    loan_type_cd: str  # 대출유형코드


def convert_overseas_to_stock_trade(src):
    if not isinstance(src, list):
        src = [src]

    result = []
    for overseas_trade in src:
        result.append(StockTradeListResponseDTO(
            ord_dt=overseas_trade.ord_dt,
            ord_gno_brno=overseas_trade.ord_gno_brno,
            odno=overseas_trade.odno,
            orgn_odno=overseas_trade.orgn_odno,
            ord_dvsn_name=overseas_trade.rvse_cncl_dvsn_name,  # 정정/취소 구분명을 주문구분명으로 매핑
            sll_buy_dvsn_cd=overseas_trade.sll_buy_dvsn_cd,
            sll_buy_dvsn_cd_name=overseas_trade.sll_buy_dvsn_cd_name,
            pdno=overseas_trade.pdno,
            prdt_name=overseas_trade.prdt_name,
            ord_qty=overseas_trade.ft_ord_qty,  # FT주문수량 → 주문수량
            ord_unpr=overseas_trade.ft_ord_unpr3,  # FT주문단가3 → 주문단가
            ord_tmd=overseas_trade.ord_tmd,
            tot_ccld_qty=overseas_trade.ft_ccld_qty,  # FT체결수량 → 총체결수량
            avg_prvs=overseas_trade.ft_ccld_unpr3,  # FT체결단가3 → 평균가
            tot_ccld_amt=overseas_trade.ft_ccld_amt3,
            loan_dt="",  # 매핑할 필드 없음
            ordr_empno="",  # 매핑할 필드 없음
            ord_dvsn_cd="",  # 매핑할 필드 없음
            rmn_qty=overseas_trade.nccs_qty,  # 미체결수량 → 잔여수량
            rjct_qty="",  # 매핑할 필드 없음
            ccld_cndt_name="",  # 매핑할 필드 없음
            inqr_ip_addr="",  # 매핑할 필드 없음
            cpbc_ordp_ord_rcit_dvsn_cd="",  # 매핑할 필드 없음
            cpbc_ordp_infm_mthd_dvsn_cd="",  # 매핑할 필드 없음
            infm_tmd=overseas_trade.thco_ord_tmd,  # 당사주문시각 → 통보시각
            ctac_tlno="",  # 매핑할 필드 없음
            prdt_type_cd="",  # 매핑할 필드 없음
            excg_dvsn_cd=overseas_trade.ovrs_excg_cd,  # 해외거래소코드 → 거래소구분코드
            cpbc_ordp_mtrl_dvsn_cd="",  # 매핑할 필드 없음
            ord_orgno="",  # 매핑할 필드 없음
            rsvn_ord_end_dt=overseas_trade.dmst_ord_dt,  # 국내주문일자 → 예약주문종료일자
            stpm_cndt_pric="",  # 매핑할 필드 없음
            stpm_efct_occr_dtmd=""  # 매핑할 필드 없음
        ))
    return result
