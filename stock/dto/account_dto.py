from dataclasses import dataclass


@dataclass
class InquireBalanceRequestDTO:
    cano: str
    acnt_prdt_cd: str
    inqr_dvsn: str
    afhr_flpr_yn: str = "N"
    ofl_yn: str = ""
    unpr_dvsn: str = "01"
    fund_sttl_icld_yn: str = "N"
    fncg_amt_auto_rdpt_yn: str = "N"
    prcs_dvsn: str = "00"
    ctx_area_fk100: str = ""
    ctx_area_nk100: str = ""


@dataclass
class StockResponseDTO:
    pdno: str
    prdt_name: str
    trad_dvsn_name: str
    bfdy_buy_qty: str
    bfdy_sll_qty: str
    thdt_buyqty: str
    thdt_sll_qty: str
    hldg_qty: str
    ord_psbl_qty: str
    pchs_avg_pric: str
    pchs_amt: str
    prpr: str
    evlu_amt: str
    evlu_pfls_amt: str
    evlu_pfls_rt: str
    evlu_erng_rt: str
    loan_dt: str
    loan_amt: str
    stln_slng_chgs: str
    expd_dt: str
    fltt_rt: str
    bfdy_cprs_icdc: str
    item_mgna_rt_name: str
    grta_rt_name: str
    sbst_pric: str
    stck_loan_unpr: str


@dataclass
class AccountResponseDTO:
    dnca_tot_amt: str
    nxdy_excc_amt: str
    prvs_rcdl_excc_amt: str
    cma_evlu_amt: str
    bfdy_buy_amt: str
    thdt_buy_amt: str
    nxdy_auto_rdpt_amt: str
    bfdy_sll_amt: str
    thdt_sll_amt: str
    d2_auto_rdpt_amt: str
    bfdy_tlex_amt: str
    thdt_tlex_amt: str
    tot_loan_amt: str
    scts_evlu_amt: str
    tot_evlu_amt: str
    nass_amt: str
    fncg_gld_auto_rdpt_yn: str
    pchs_amt_smtl_amt: str
    evlu_amt_smtl_amt: str
    evlu_pfls_smtl_amt: str
    tot_stln_slng_chgs: str
    bfdy_tot_asst_evlu_amt: str
    asst_icdc_amt: str
    asst_icdc_erng_rt: str
