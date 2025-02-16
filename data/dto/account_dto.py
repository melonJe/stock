from dataclasses import dataclass
from typing import Union, List


@dataclass
class InquireBalanceRequestDTO:
    cano: str  # 종합계좌번호: 계좌번호 체계(8-2)의 앞 8자리
    acnt_prdt_cd: str  # 계좌상품코드: 계좌번호 체계(8-2)의 뒤 2자리
    inqr_dvsn: str  # 조회구분: 01 - 대출일별, 02 - 종목별
    afhr_flpr_yn: str = "N"  # 시간외단일가여부: N - 기본값, Y - 시간외단일가
    ofl_yn: str = ""  # 오프라인여부: 공란(Default)
    unpr_dvsn: str = "01"  # 단가구분: 01 - 기본값
    fund_sttl_icld_yn: str = "N"  # 펀드결제분포함여부: N - 포함하지 않음, Y - 포함
    fncg_amt_auto_rdpt_yn: str = "N"  # 융자금액자동상환여부: N - 기본값
    prcs_dvsn: str = "00"  # 처리구분: 00 - 전일매매포함, 01 - 전일매매미포함
    ctx_area_fk100: str = ""  # 연속조회검색조건100: 공란 - 최초 조회시, 이전 조회 Output ctx_area_fk100 값 - 다음페이지 조회시(2번째부터)
    ctx_area_nk100: str = ""  # 연속조회키100: 공란 - 최초 조회시, 이전 조회 Output ctx_area_nk100 값 - 다음페이지 조회시(2번째부터)


@dataclass
class StockResponseDTO:
    pdno: str  # 상품번호: 종목번호(뒷 6자리)
    prdt_name: str  # 상품명: 종목명
    trad_dvsn_name: str  # 매매구분명: 매수매도구분
    bfdy_buy_qty: str  # 전일매수수량
    bfdy_sll_qty: str  # 전일매도수량
    thdt_buyqty: str  # 금일매수수량
    thdt_sll_qty: str  # 금일매도수량
    hldg_qty: str  # 보유수량
    ord_psbl_qty: str  # 주문가능수량
    pchs_avg_pric: str  # 매입평균가격: 매입금액 / 보유수량
    pchs_amt: str  # 매입금액
    prpr: str  # 현재가
    evlu_amt: str  # 평가금액
    evlu_pfls_amt: str  # 평가손익금액: 평가금액 - 매입금액
    evlu_pfls_rt: str  # 평가손익율
    evlu_erng_rt: str  # 평가수익율: 미사용항목(0으로 출력)
    loan_dt: str  # 대출일자: 조회구분을 01(대출일별)로 설정해야 값이 나옴
    loan_amt: str  # 대출금액
    stln_slng_chgs: str  # 대주매각대금
    expd_dt: str  # 만기일자
    fltt_rt: str  # 등락율
    bfdy_cprs_icdc: str  # 전일대비증감
    item_mgna_rt_name: str  # 종목증거금율명
    grta_rt_name: str  # 보증금율명
    sbst_pric: str  # 대용가격: 증권매매의 위탁보증금으로서 현금 대신에 사용되는 유가증권 가격
    stck_loan_unpr: str  # 주식대출단가


class OverseesStockResponseDTO:
    ovrs_pdno: str  # 해외상품번호
    ovrs_item_name: str  # 해외종목명
    frcr_evlu_pfls_amt: str  # 외화평가손익금액
    evlu_pfls_rt: str  # 평가손익율
    pchs_avg_pric: str  # 매입평균가격
    ovrs_cblc_qty: str  # 해외잔고수량
    ord_psbl_qty: str  # 주문가능수량
    frcr_pchs_amt1: str  # 외화매입금액1
    ovrs_stck_evlu_amt: str  # 해외주식평가금액
    now_pric2: str  # 현재가격2
    tr_crcy_cd: str  # 거래통화코드
    ovrs_excg_cd: str  # 해외거래소코드
    loan_type_cd: str  # 대출유형코드
    loan_dt: str  # 대출일자
    expd_dt: str  # 만기일자
    evlu_amt: str  # 평가금액
    evlu_pfls_amt: str  # 평가손익금액
    evlu_pfls_rt: str  # 평가손익율
    bfdy_buy_qty: str  # 전일매수수량
    bfdy_sll_qty: str  # 전일매도수량
    thdt_buyqty: str  # 금일매수수량
    thdt_sll_qty: str  # 금일매도수량
    hldg_qty: str  # 보유수량
    prpr: str  # 현재가
    evlu_erng_rt: str  # 평가수익율
    loan_amt: str  # 대출금액
    stln_slng_chgs: str  # 대주매각대금
    fltt_rt: str  # 등락율
    bfdy_cprs_icdc: str  # 전일대비증감
    item_mgna_rt_name: str  # 종목증거금율명
    grta_rt_name: str  # 보증금율명
    sbst_pric: str  # 대용가격
    stck_loan_unpr: str  # 주식대출단가


def convert_to_stock_response(data: Union[OverseesStockResponseDTO, List[OverseesStockResponseDTO]]) -> Union[StockResponseDTO, List[StockResponseDTO]]:
    def convert(item: OverseesStockResponseDTO) -> StockResponseDTO:
        return StockResponseDTO(
            pdno=item.ovrs_pdno,
            prdt_name=item.ovrs_item_name,
            bfdy_buy_qty=item.bfdy_buy_qty,
            bfdy_sll_qty=item.bfdy_sll_qty,
            thdt_buyqty=item.thdt_buyqty,
            thdt_sll_qty=item.thdt_sll_qty,
            hldg_qty=item.hldg_qty,
            ord_psbl_qty=item.ord_psbl_qty,
            pchs_avg_pric=item.pchs_avg_pric,
            pchs_amt=item.frcr_pchs_amt1,
            prpr=item.prpr,
            evlu_amt=item.evlu_amt,
            evlu_pfls_amt=item.evlu_pfls_amt,
            evlu_pfls_rt=item.evlu_pfls_rt,
            evlu_erng_rt=item.evlu_erng_rt,
            loan_dt=item.loan_dt,
            loan_amt=item.loan_amt,
            stln_slng_chgs=item.stln_slng_chgs,
            expd_dt=item.expd_dt,
            fltt_rt=item.fltt_rt,
            bfdy_cprs_icdc=item.bfdy_cprs_icdc,
            item_mgna_rt_name=item.item_mgna_rt_name,
            grta_rt_name=item.grta_rt_name,
            sbst_pric=item.sbst_pric,
            stck_loan_unpr=item.stck_loan_unpr
        )

    if isinstance(data, list):
        return [convert(item) for item in data]
    return convert(data)


@dataclass
class AccountResponseDTO:
    dnca_tot_amt: str  # 예수금총금액: 예수금
    nxdy_excc_amt: str  # 익일정산금액: D+1 예수금
    prvs_rcdl_excc_amt: str  # 가수도정산금액: D+2 예수금
    cma_evlu_amt: str  # CMA평가금액
    bfdy_buy_amt: str  # 전일매수금액
    thdt_buy_amt: str  # 금일매수금액
    nxdy_auto_rdpt_amt: str  # 익일자동상환금액
    bfdy_sll_amt: str  # 전일매도금액
    thdt_sll_amt: str  # 금일매도금액
    d2_auto_rdpt_amt: str  # D+2자동상환금액
    bfdy_tlex_amt: str  # 전일제비용금액
    thdt_tlex_amt: str  # 금일제비용금액
    tot_loan_amt: str  # 총대출금액
    scts_evlu_amt: str  # 유가평가금액
    tot_evlu_amt: str  # 총평가금액: 유가증권 평가금액 합계금액 + D+2 예수금
    nass_amt: str  # 순자산금액
    fncg_gld_auto_rdpt_yn: str  # 융자금자동상환여부: 보유현금에 대한 융자금만 차감여부
    pchs_amt_smtl_amt: str  # 매입금액합계금액
    evlu_amt_smtl_amt: str  # 평가금액합계금액: 유가증권 평가금액 합계금액
    evlu_pfls_smtl_amt: str  # 평가손익합계금액
    tot_stln_slng_chgs: str  # 총대주매각대금
    bfdy_tot_asst_evlu_amt: str  # 전일총자산평가금액
    asst_icdc_amt: str  # 자산증감액
    asst_icdc_erng_rt: str  # 자산증감수익율: 데이터 미제공
