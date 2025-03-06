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
