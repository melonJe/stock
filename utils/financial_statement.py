import re
import time
from datetime import datetime, timedelta
from functools import reduce

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta

pd.set_option('display.max_columns', None)


def html_table_to_dataframe_for_fnguide(table) -> pd.DataFrame:
    """
    FnGuide 재무제표 테이블(HTML)을 받아 DataFrame으로 변환해주는 함수
    """
    if not table:
        raise ValueError("table data is None")

    # 헤더에서 연도/분기/전년동기 등의 형태를 추출하여 인덱스로 사용
    index = []
    thead_ths = table.select_one('thead').select("th", {"scope": "col"})
    for th in thead_ths:
        txt = th.get_text(strip=True)
        match = re.search(r'\d{4}\/\d{2}(\(E\))?', txt)
        if match:
            index.append(match.group())

    data = {}
    # 본문(tbody)에서 각 행(계정 과목)에 대한 값들을 추출
    # 마지막 len(index)개 데이터만 활용
    for tbody in table.select("tbody"):
        for tr in tbody.select("tr"):
            column = tr.select_one("div")
            if column:
                # dt 태그가 있으면 해당 값이 계정명인 경우가 많으므로 우선 추출
                dt_tag = column.select_one('dt')
                if dt_tag:
                    column = dt_tag.get_text(strip=True)
                else:
                    column = column.get_text(strip=True)
            else:
                continue

            if column:
                key = column
                values = [td.get_text(strip=True) for td in tr.select("td")]
                # 헤더로 인식된 index 길이에 맞춰잘라 매핑
                data[key] = values[:len(index)]

    df = pd.DataFrame(data, index=index)
    return df


def get_finance_from_fnguide(symbol: str, report='highlight', report_type: str = 'D', period: str = 'Y', include_estimates: bool = False) -> pd.DataFrame:
    """
    FnGuide에서 제공하는 메인 페이지 및 재무제표 페이지를 크롤링하여
    report 파라미터(쉼표로 구분된 문자열)에 따라
    - highlight : 재무 하이라이트
    - income    : 손익계산서
    - state     : 재무상태표
    - cash      : 현금흐름표
    를 조회 후 하나의 DataFrame으로 병합(return).
    """
    # 파라미터 유효성 검사
    report_type, period = report_type.upper(), period.upper()
    if report_type not in ['D', 'B']:
        raise ValueError(
            f"Invalid value for parameter 'report_type': {report_type}. "
            f"Valid options are: 'D', 'B'."
        )
    if period not in ['A', 'Y', 'Q']:
        raise ValueError(
            f"Invalid value for parameter 'period': {period}. "
            f"Valid options are: 'A', 'Y', 'Q'."
        )

    # report를 쉼표로 구분하여 리스트로 변환: highlight, income, state, cash 등
    report_list = [r.strip().lower() for r in report.split(",") if r.strip()]

    # highlight 여부 확인
    need_main_page = 'highlight' in report_list
    # 나머지(=재무제표 페이지에서 조회할) 리스트
    finance_list = [r for r in report_list if r != 'highlight']

    df_list = []

    # (1) 메인 페이지: 하이라이트
    if need_main_page:
        url_main = (
            f'https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp'
            f'?pGB=1&gicode=A{symbol}&cID=&MenuYn=Y&ReportGB=&NewMenuID=101&stkGb=701'
        )
        response = requests.get(url_main)
        response.raise_for_status()
        soup_main = BeautifulSoup(response.text, 'html.parser')

        highlight_div_id = f"highlight_{report_type}_{period}"
        table_highlight = soup_main.select_one(f"div#{highlight_div_id} table")
        if table_highlight:
            df_list.append(html_table_to_dataframe_for_fnguide(table_highlight))
        else:
            raise ValueError(f"Unable to find highlight table with id: {highlight_div_id}")

    # (2) 재무제표 페이지: 손익계산서, 재무상태표, 현금흐름표
    if finance_list:
        url_finance = (
            f'https://comp.fnguide.com/SVO2/ASP/SVD_Finance.asp'
            f'?pGB=1&gicode=A{symbol}&cID=&MenuYn=Y&ReportGB=&NewMenuID=103&stkGb=701'
        )
        response = requests.get(url_finance)
        response.raise_for_status()
        soup_finance = BeautifulSoup(response.text, 'html.parser')

        # report -> div id 매핑
        div_id_dict = {
            'income': 'divSonik',
            'state': 'divDaecha',
            'cash': 'divCash'
        }

        for key in finance_list:
            if key not in div_id_dict:
                # 잘못된 report 키값이 들어온 경우
                raise ValueError(f"Invalid report name: '{key}'. Choose from {list(div_id_dict.keys())}.")
            div_key = div_id_dict[key]
            table_selector = f"div#{div_key}{period} table"
            table = soup_finance.select_one(table_selector)
            if table:
                df_list.append(html_table_to_dataframe_for_fnguide(table))
            else:
                raise ValueError(f"Unable to find {key} table (selector: {table_selector}).")

    # 여러 DataFrame 병합
    if df_list:
        # 필요시 suffixes 옵션 사용 가능: suffixes=('', '_dup') 등
        merged_df = reduce(
            lambda left, right: pd.merge(
                left, right, how='outer', left_index=True, right_index=True
            ),
            df_list
        )
    else:
        merged_df = pd.DataFrame()

    # 추정치(E)가 포함된 항목 제거(옵션)
    if not include_estimates:
        merged_df = merged_df[~merged_df.index.str.contains(r'\(E\)')]
    if period == 'Y':
        merged_df = merged_df[merged_df.index.str.contains(r'\d{4}/12(?:\(E\))?')]

    return merged_df


def get_financial_summary_for_update_stock(symbol: str, report_type: str = 'D', period: str = 'Q', include_estimates: bool = False) -> dict:
    """
    종목(symbol)에 대한 재무 요약 정보를 딕셔너리 형태로 반환
    """
    result = {}

    # 재무제표 정보 중 첫 행(row)을 dict 형태로 변환 (가장 최근년도/분기)
    finance_df = get_finance_from_fnguide(symbol=symbol, report='highlight', report_type=report_type, period=period, include_estimates=include_estimates)

    if not finance_df.empty:
        financial_summary = finance_df.iloc[0].to_dict()
    else:
        financial_summary = {}

    # 업종 PER 크롤링
    url_main = (
        f'https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp'
        f'?pGB=1&gicode=A{symbol}&cID=&MenuYn=Y&ReportGB=&NewMenuID=101&stkGb=701'
    )
    response = requests.get(url_main)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    result["PER"] = soup.select_one('a[id="h_per"]').parent.parent.select('dd')[-1].get_text(strip=True)
    result["업종 PER"] = soup.select_one('a[id="h_u_per"]').parent.parent.select('dd')[-1].get_text(strip=True)
    result["PBR"] = soup.select_one('a[id="h_pbr"]').parent.parent.select('dd')[-1].get_text(strip=True)
    result["배당수익률"] = soup.select_one('a[id="h_rate"]').parent.parent.select('dd')[-1].get_text(strip=True)

    # 재무제표에서 가져올 항목 (키 이름이 DataFrame 컬럼과 일치해야 함)
    result["영업이익률"] = financial_summary.get("영업이익률(%)", None)
    result["ROE"] = financial_summary.get("ROE(%)", None)
    result["부채비율"] = financial_summary.get("부채비율(%)", None)

    for key, value in result.items():
        if value in ["", "-", None]:
            result[key] = float('-inf')
        else:
            result[key] = float(re.search(r'-?\d*\.?\d*', value.replace(',', '')).group())

    return result


def fetch_financial_timeseries(symbol: str, report='income', period: str = 'Q', include_estimates: bool = False, years=5) -> pd.DataFrame:
    """
    Yahoo Finance에서 재무 시계열 데이터를 가져와 DataFrame으로 반환합니다.

    매개변수:
    - symbol (str): 주식 티커 심볼 (예: 'AAPL').
    - report (str): 재무 보고서 유형 (예: 'income', 'balance', 'cash').
    - report_type (str): 보고서 세부 유형 ('D'는 상세, 'S'는 요약).
    - period (str): 데이터 주기 ('Y'는 연간, 'Q'는 분기별).
    - include_estimates (bool): 추정치를 포함할지 여부.

    반환값:
    - pd.DataFrame: 요청된 재무 데이터를 포함하는 DataFrame.
    """

    # 기본 URL 설정
    base_url = f"https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}"

    # 사용자가 제공한 type 목록

    # report, report_type, period에 따라 type 선택
    # 예시로, report='income', period='Q'인 경우 분기별 타입 선택
    # 이 매핑은 사용자의 필요에 따라 조정할 수 있습니다.
    types = {
        'income': {
            'Q': 'quarterlyTaxEffectOfUnusualItems,quarterlyTaxRateForCalcs,quarterlyNormalizedEBITDA,quarterlyNormalizedDilutedEPS,quarterlyNormalizedBasicEPS,quarterlyTotalUnusualItems,quarterlyTotalUnusualItemsExcludingGoodwill,quarterlyNetIncomeFromContinuingOperationNetMinorityInterest,quarterlyReconciledDepreciation,quarterlyReconciledCostOfRevenue,quarterlyEBITDA,quarterlyEBIT,quarterlyNetInterestIncome,quarterlyInterestExpense,quarterlyInterestIncome,quarterlyContinuingAndDiscontinuedDilutedEPS,quarterlyContinuingAndDiscontinuedBasicEPS,quarterlyNormalizedIncome,quarterlyNetIncomeFromContinuingAndDiscontinuedOperation,quarterlyTotalExpenses,quarterlyRentExpenseSupplemental,quarterlyReportedNormalizedDilutedEPS,quarterlyReportedNormalizedBasicEPS,quarterlyTotalOperatingIncomeAsReported,quarterlyDividendPerShare,quarterlyDilutedAverageShares,quarterlyBasicAverageShares,quarterlyDilutedEPS,quarterlyDilutedEPSOtherGainsLosses,quarterlyTaxLossCarryforwardDilutedEPS,quarterlyDilutedAccountingChange,quarterlyDilutedExtraordinary,quarterlyDilutedDiscontinuousOperations,quarterlyDilutedContinuousOperations,quarterlyBasicEPS,quarterlyBasicEPSOtherGainsLosses,quarterlyTaxLossCarryforwardBasicEPS,quarterlyBasicAccountingChange,quarterlyBasicExtraordinary,quarterlyBasicDiscontinuousOperations,quarterlyBasicContinuousOperations,quarterlyDilutedNIAvailtoComStockholders,quarterlyAverageDilutionEarnings,quarterlyNetIncomeCommonStockholders,quarterlyOtherunderPreferredStockDividend,quarterlyPreferredStockDividends,quarterlyNetIncome,quarterlyMinorityInterests,quarterlyNetIncomeIncludingNoncontrollingInterests,quarterlyNetIncomeFromTaxLossCarryforward,quarterlyNetIncomeExtraordinary,quarterlyNetIncomeDiscontinuousOperations,quarterlyNetIncomeContinuousOperations,quarterlyEarningsFromEquityInterestNetOfTax,quarterlyTaxProvision,quarterlyPretaxIncome,quarterlyOtherIncomeExpense,quarterlyOtherNonOperatingIncomeExpenses,quarterlySpecialIncomeCharges,quarterlyGainOnSaleOfPPE,quarterlyGainOnSaleOfBusiness,quarterlyOtherSpecialCharges,quarterlyWriteOff,quarterlyImpairmentOfCapitalAssets,quarterlyRestructuringAndMergernAcquisition,quarterlySecuritiesAmortization,quarterlyEarningsFromEquityInterest,quarterlyGainOnSaleOfSecurity,quarterlyNetNonOperatingInterestIncomeExpense,quarterlyTotalOtherFinanceCost,quarterlyInterestExpenseNonOperating,quarterlyInterestIncomeNonOperating,quarterlyOperatingIncome,quarterlyOperatingExpense,quarterlyOtherOperatingExpenses,quarterlyOtherTaxes,quarterlyProvisionForDoubtfulAccounts,quarterlyDepreciationAmortizationDepletionIncomeStatement,quarterlyDepletionIncomeStatement,quarterlyDepreciationAndAmortizationInIncomeStatement,quarterlyAmortization,quarterlyAmortizationOfIntangiblesIncomeStatement,quarterlyDepreciationIncomeStatement,quarterlyResearchAndDevelopment,quarterlySellingGeneralAndAdministration,quarterlySellingAndMarketingExpense,quarterlyGeneralAndAdministrativeExpense,quarterlyOtherGandA,quarterlyInsuranceAndClaims,quarterlyRentAndLandingFees,quarterlySalariesAndWages,quarterlyGrossProfit,quarterlyCostOfRevenue,quarterlyTotalRevenue,quarterlyExciseTaxes,quarterlyOperatingRevenue,',
            'Y': 'annualTreasurySharesNumber,annualPreferredSharesNumber,annualOrdinarySharesNumber,annualShareIssued,annualNetDebt,annualTotalDebt,annualTangibleBookValue,annualInvestedCapital,annualWorkingCapital,annualNetTangibleAssets,annualCapitalLeaseObligations,annualCommonStockEquity,annualPreferredStockEquity,annualTotalCapitalization,annualTotalEquityGrossMinorityInterest,annualMinorityInterest,annualStockholdersEquity,annualOtherEquityInterest,annualGainsLossesNotAffectingRetainedEarnings,annualOtherEquityAdjustments,annualFixedAssetsRevaluationReserve,annualForeignCurrencyTranslationAdjustments,annualMinimumPensionLiabilities,annualUnrealizedGainLoss,annualTreasuryStock,annualRetainedEarnings,annualAdditionalPaidInCapital,annualCapitalStock,annualOtherCapitalStock,annualCommonStock,annualPreferredStock,annualTotalPartnershipCapital,annualGeneralPartnershipCapital,annualLimitedPartnershipCapital,annualTotalLiabilitiesNetMinorityInterest,annualTotalNonCurrentLiabilitiesNetMinorityInterest,annualOtherNonCurrentLiabilities,annualLiabilitiesHeldforSaleNonCurrent,annualRestrictedCommonStock,annualPreferredSecuritiesOutsideStockEquity,annualDerivativeProductLiabilities,annualEmployeeBenefits,annualNonCurrentPensionAndOtherPostretirementBenefitPlans,annualNonCurrentAccruedExpenses,annualDuetoRelatedPartiesNonCurrent,annualTradeandOtherPayablesNonCurrent,annualNonCurrentDeferredLiabilities,annualNonCurrentDeferredRevenue,annualNonCurrentDeferredTaxesLiabilities,annualLongTermDebtAndCapitalLeaseObligation,annualLongTermCapitalLeaseObligation,annualLongTermDebt,annualLongTermProvisions,annualCurrentLiabilities,annualOtherCurrentLiabilities,annualCurrentDeferredLiabilities,annualCurrentDeferredRevenue,annualCurrentDeferredTaxesLiabilities,annualCurrentDebtAndCapitalLeaseObligation,annualCurrentCapitalLeaseObligation,annualCurrentDebt,annualOtherCurrentBorrowings,annualLineOfCredit,annualCommercialPaper,annualCurrentNotesPayable,annualPensionandOtherPostRetirementBenefitPlansCurrent,annualCurrentProvisions,annualPayablesAndAccruedExpenses,annualCurrentAccruedExpenses,annualInterestPayable,annualPayables,annualOtherPayable,annualDuetoRelatedPartiesCurrent,annualDividendsPayable,annualTotalTaxPayable,annualIncomeTaxPayable,annualAccountsPayable,annualTotalAssets,annualTotalNonCurrentAssets,annualOtherNonCurrentAssets,annualDefinedPensionBenefit,annualNonCurrentPrepaidAssets,annualNonCurrentDeferredAssets,annualNonCurrentDeferredTaxesAssets,annualDuefromRelatedPartiesNonCurrent,annualNonCurrentNoteReceivables,annualNonCurrentAccountsReceivable,annualFinancialAssets,annualInvestmentsAndAdvances,annualOtherInvestments,annualInvestmentinFinancialAssets,annualHeldToMaturitySecurities,annualAvailableForSaleSecurities,annualFinancialAssetsDesignatedasFairValueThroughProfitorLossTotal,annualTradingSecurities,annualLongTermEquityInvestment,annualInvestmentsinJointVenturesatCost,annualInvestmentsInOtherVenturesUnderEquityMethod,annualInvestmentsinAssociatesatCost,annualInvestmentsinSubsidiariesatCost,annualInvestmentProperties,annualGoodwillAndOtherIntangibleAssets,annualOtherIntangibleAssets,annualGoodwill,annualNetPPE,annualAccumulatedDepreciation,annualGrossPPE,annualLeases,annualConstructionInProgress,annualOtherProperties,annualMachineryFurnitureEquipment,annualBuildingsAndImprovements,annualLandAndImprovements,annualProperties,annualCurrentAssets,annualOtherCurrentAssets,annualHedgingAssetsCurrent,annualAssetsHeldForSaleCurrent,annualCurrentDeferredAssets,annualCurrentDeferredTaxesAssets,annualRestrictedCash,annualPrepaidAssets,annualInventory,annualInventoriesAdjustmentsAllowances,annualOtherInventories,annualFinishedGoods,annualWorkInProcess,annualRawMaterials,annualReceivables,annualReceivablesAdjustmentsAllowances,annualOtherReceivables,annualDuefromRelatedPartiesCurrent,annualTaxesReceivable,annualAccruedInterestReceivable,annualNotesReceivable,annualLoansReceivable,annualAccountsReceivable,annualAllowanceForDoubtfulAccountsReceivable,annualGrossAccountsReceivable,annualCashCashEquivalentsAndShortTermInvestments,annualOtherShortTermInvestments,annualCashAndCashEquivalents,annualCashEquivalents,annualCashFinancial',
            'T': ''
        },
        'balance': {
            'Q': 'quarterlyTreasurySharesNumber,quarterlyPreferredSharesNumber,quarterlyOrdinarySharesNumber,quarterlyShareIssued,quarterlyNetDebt,quarterlyTotalDebt,quarterlyTangibleBookValue,quarterlyInvestedCapital,quarterlyWorkingCapital,quarterlyNetTangibleAssets,quarterlyCapitalLeaseObligations,quarterlyCommonStockEquity,quarterlyPreferredStockEquity,quarterlyTotalCapitalization,quarterlyTotalEquityGrossMinorityInterest,quarterlyMinorityInterest,quarterlyStockholdersEquity,quarterlyOtherEquityInterest,quarterlyGainsLossesNotAffectingRetainedEarnings,quarterlyOtherEquityAdjustments,quarterlyFixedAssetsRevaluationReserve,quarterlyForeignCurrencyTranslationAdjustments,quarterlyMinimumPensionLiabilities,quarterlyUnrealizedGainLoss,quarterlyTreasuryStock,quarterlyRetainedEarnings,quarterlyAdditionalPaidInCapital,quarterlyCapitalStock,quarterlyOtherCapitalStock,quarterlyCommonStock,quarterlyPreferredStock,quarterlyTotalPartnershipCapital,quarterlyGeneralPartnershipCapital,quarterlyLimitedPartnershipCapital,quarterlyTotalLiabilitiesNetMinorityInterest,quarterlyTotalNonCurrentLiabilitiesNetMinorityInterest,quarterlyOtherNonCurrentLiabilities,quarterlyLiabilitiesHeldforSaleNonCurrent,quarterlyRestrictedCommonStock,quarterlyPreferredSecuritiesOutsideStockEquity,quarterlyDerivativeProductLiabilities,quarterlyEmployeeBenefits,quarterlyNonCurrentPensionAndOtherPostretirementBenefitPlans,quarterlyNonCurrentAccruedExpenses,quarterlyDuetoRelatedPartiesNonCurrent,quarterlyTradeandOtherPayablesNonCurrent,quarterlyNonCurrentDeferredLiabilities,quarterlyNonCurrentDeferredRevenue,quarterlyNonCurrentDeferredTaxesLiabilities,quarterlyLongTermDebtAndCapitalLeaseObligation,quarterlyLongTermCapitalLeaseObligation,quarterlyLongTermDebt,quarterlyLongTermProvisions,quarterlyCurrentLiabilities,quarterlyOtherCurrentLiabilities,quarterlyCurrentDeferredLiabilities,quarterlyCurrentDeferredRevenue,quarterlyCurrentDeferredTaxesLiabilities,quarterlyCurrentDebtAndCapitalLeaseObligation,quarterlyCurrentCapitalLeaseObligation,quarterlyCurrentDebt,quarterlyOtherCurrentBorrowings,quarterlyLineOfCredit,quarterlyCommercialPaper,quarterlyCurrentNotesPayable,quarterlyPensionandOtherPostRetirementBenefitPlansCurrent,quarterlyCurrentProvisions,quarterlyPayablesAndAccruedExpenses,quarterlyCurrentAccruedExpenses,quarterlyInterestPayable,quarterlyPayables,quarterlyOtherPayable,quarterlyDuetoRelatedPartiesCurrent,quarterlyDividendsPayable,quarterlyTotalTaxPayable,quarterlyIncomeTaxPayable,quarterlyAccountsPayable,quarterlyTotalAssets,quarterlyTotalNonCurrentAssets,quarterlyOtherNonCurrentAssets,quarterlyDefinedPensionBenefit,quarterlyNonCurrentPrepaidAssets,quarterlyNonCurrentDeferredAssets,quarterlyNonCurrentDeferredTaxesAssets,quarterlyDuefromRelatedPartiesNonCurrent,quarterlyNonCurrentNoteReceivables,quarterlyNonCurrentAccountsReceivable,quarterlyFinancialAssets,quarterlyInvestmentsAndAdvances,quarterlyOtherInvestments,quarterlyInvestmentinFinancialAssets,quarterlyHeldToMaturitySecurities,quarterlyAvailableForSaleSecurities,quarterlyFinancialAssetsDesignatedasFairValueThroughProfitorLossTotal,quarterlyTradingSecurities,quarterlyLongTermEquityInvestment,quarterlyInvestmentsinJointVenturesatCost,quarterlyInvestmentsInOtherVenturesUnderEquityMethod,quarterlyInvestmentsinAssociatesatCost,quarterlyInvestmentsinSubsidiariesatCost,quarterlyInvestmentProperties,quarterlyGoodwillAndOtherIntangibleAssets,quarterlyOtherIntangibleAssets,quarterlyGoodwill,quarterlyNetPPE,quarterlyAccumulatedDepreciation,quarterlyGrossPPE,quarterlyLeases,quarterlyConstructionInProgress,quarterlyOtherProperties,quarterlyMachineryFurnitureEquipment,quarterlyBuildingsAndImprovements,quarterlyLandAndImprovements,quarterlyProperties,quarterlyCurrentAssets,quarterlyOtherCurrentAssets,quarterlyHedgingAssetsCurrent,quarterlyAssetsHeldForSaleCurrent,quarterlyCurrentDeferredAssets,quarterlyCurrentDeferredTaxesAssets,quarterlyRestrictedCash,quarterlyPrepaidAssets,quarterlyInventory,quarterlyInventoriesAdjustmentsAllowances,quarterlyOtherInventories,quarterlyFinishedGoods,quarterlyWorkInProcess,quarterlyRawMaterials,quarterlyReceivables,quarterlyReceivablesAdjustmentsAllowances,quarterlyOtherReceivables,quarterlyDuefromRelatedPartiesCurrent,quarterlyTaxesReceivable,quarterlyAccruedInterestReceivable,quarterlyNotesReceivable,quarterlyLoansReceivable,quarterlyAccountsReceivable,quarterlyAllowanceForDoubtfulAccountsReceivable,quarterlyGrossAccountsReceivable,quarterlyCashCashEquivalentsAndShortTermInvestments,quarterlyOtherShortTermInvestments,quarterlyCashAndCashEquivalents,quarterlyCashEquivalents,quarterlyCashFinancial',
            'Y': 'annualTreasurySharesNumber,annualPreferredSharesNumber,annualOrdinarySharesNumber,annualShareIssued,annualNetDebt,annualTotalDebt,annualTangibleBookValue,annualInvestedCapital,annualWorkingCapital,annualNetTangibleAssets,annualCapitalLeaseObligations,annualCommonStockEquity,annualPreferredStockEquity,annualTotalCapitalization,annualTotalEquityGrossMinorityInterest,annualMinorityInterest,annualStockholdersEquity,annualOtherEquityInterest,annualGainsLossesNotAffectingRetainedEarnings,annualOtherEquityAdjustments,annualFixedAssetsRevaluationReserve,annualForeignCurrencyTranslationAdjustments,annualMinimumPensionLiabilities,annualUnrealizedGainLoss,annualTreasuryStock,annualRetainedEarnings,annualAdditionalPaidInCapital,annualCapitalStock,annualOtherCapitalStock,annualCommonStock,annualPreferredStock,annualTotalPartnershipCapital,annualGeneralPartnershipCapital,annualLimitedPartnershipCapital,annualTotalLiabilitiesNetMinorityInterest,annualTotalNonCurrentLiabilitiesNetMinorityInterest,annualOtherNonCurrentLiabilities,annualLiabilitiesHeldforSaleNonCurrent,annualRestrictedCommonStock,annualPreferredSecuritiesOutsideStockEquity,annualDerivativeProductLiabilities,annualEmployeeBenefits,annualNonCurrentPensionAndOtherPostretirementBenefitPlans,annualNonCurrentAccruedExpenses,annualDuetoRelatedPartiesNonCurrent,annualTradeandOtherPayablesNonCurrent,annualNonCurrentDeferredLiabilities,annualNonCurrentDeferredRevenue,annualNonCurrentDeferredTaxesLiabilities,annualLongTermDebtAndCapitalLeaseObligation,annualLongTermCapitalLeaseObligation,annualLongTermDebt,annualLongTermProvisions,annualCurrentLiabilities,annualOtherCurrentLiabilities,annualCurrentDeferredLiabilities,annualCurrentDeferredRevenue,annualCurrentDeferredTaxesLiabilities,annualCurrentDebtAndCapitalLeaseObligation,annualCurrentCapitalLeaseObligation,annualCurrentDebt,annualOtherCurrentBorrowings,annualLineOfCredit,annualCommercialPaper,annualCurrentNotesPayable,annualPensionandOtherPostRetirementBenefitPlansCurrent,annualCurrentProvisions,annualPayablesAndAccruedExpenses,annualCurrentAccruedExpenses,annualInterestPayable,annualPayables,annualOtherPayable,annualDuetoRelatedPartiesCurrent,annualDividendsPayable,annualTotalTaxPayable,annualIncomeTaxPayable,annualAccountsPayable,annualTotalAssets,annualTotalNonCurrentAssets,annualOtherNonCurrentAssets,annualDefinedPensionBenefit,annualNonCurrentPrepaidAssets,annualNonCurrentDeferredAssets,annualNonCurrentDeferredTaxesAssets,annualDuefromRelatedPartiesNonCurrent,annualNonCurrentNoteReceivables,annualNonCurrentAccountsReceivable,annualFinancialAssets,annualInvestmentsAndAdvances,annualOtherInvestments,annualInvestmentinFinancialAssets,annualHeldToMaturitySecurities,annualAvailableForSaleSecurities,annualFinancialAssetsDesignatedasFairValueThroughProfitorLossTotal,annualTradingSecurities,annualLongTermEquityInvestment,annualInvestmentsinJointVenturesatCost,annualInvestmentsInOtherVenturesUnderEquityMethod,annualInvestmentsinAssociatesatCost,annualInvestmentsinSubsidiariesatCost,annualInvestmentProperties,annualGoodwillAndOtherIntangibleAssets,annualOtherIntangibleAssets,annualGoodwill,annualNetPPE,annualAccumulatedDepreciation,annualGrossPPE,annualLeases,annualConstructionInProgress,annualOtherProperties,annualMachineryFurnitureEquipment,annualBuildingsAndImprovements,annualLandAndImprovements,annualProperties,annualCurrentAssets,annualOtherCurrentAssets,annualHedgingAssetsCurrent,annualAssetsHeldForSaleCurrent,annualCurrentDeferredAssets,annualCurrentDeferredTaxesAssets,annualRestrictedCash,annualPrepaidAssets,annualInventory,annualInventoriesAdjustmentsAllowances,annualOtherInventories,annualFinishedGoods,annualWorkInProcess,annualRawMaterials,annualReceivables,annualReceivablesAdjustmentsAllowances,annualOtherReceivables,annualDuefromRelatedPartiesCurrent,annualTaxesReceivable,annualAccruedInterestReceivable,annualNotesReceivable,annualLoansReceivable,annualAccountsReceivable,annualAllowanceForDoubtfulAccountsReceivable,annualGrossAccountsReceivable,annualCashCashEquivalentsAndShortTermInvestments,annualOtherShortTermInvestments,annualCashAndCashEquivalents,annualCashEquivalents,annualCashFinancial',
            'T': ''
        },
        'cash': {
            'Q': 'quarterlyForeignSales,quarterlyDomesticSales,quarterlyAdjustedGeographySegmentData,quarterlyFreeCashFlow,quarterlyRepurchaseOfCapitalStock,quarterlyRepaymentOfDebt,quarterlyIssuanceOfDebt,quarterlyIssuanceOfCapitalStock,quarterlyCapitalExpenditure,quarterlyInterestPaidSupplementalData,quarterlyIncomeTaxPaidSupplementalData,quarterlyEndCashPosition,quarterlyOtherCashAdjustmentOutsideChangeinCash,quarterlyBeginningCashPosition,quarterlyEffectOfExchangeRateChanges,quarterlyChangesInCash,quarterlyOtherCashAdjustmentInsideChangeinCash,quarterlyCashFlowFromDiscontinuedOperation,quarterlyFinancingCashFlow,quarterlyCashFromDiscontinuedFinancingActivities,quarterlyCashFlowFromContinuingFinancingActivities,quarterlyNetOtherFinancingCharges,quarterlyInterestPaidCFF,quarterlyProceedsFromStockOptionExercised,quarterlyCashDividendsPaid,quarterlyPreferredStockDividendPaid,quarterlyCommonStockDividendPaid,quarterlyNetPreferredStockIssuance,quarterlyPreferredStockPayments,quarterlyPreferredStockIssuance,quarterlyNetCommonStockIssuance,quarterlyCommonStockPayments,quarterlyCommonStockIssuance,quarterlyNetIssuancePaymentsOfDebt,quarterlyNetShortTermDebtIssuance,quarterlyShortTermDebtPayments,quarterlyShortTermDebtIssuance,quarterlyNetLongTermDebtIssuance,quarterlyLongTermDebtPayments,quarterlyLongTermDebtIssuance,quarterlyInvestingCashFlow,quarterlyCashFromDiscontinuedInvestingActivities,quarterlyCashFlowFromContinuingInvestingActivities,quarterlyNetOtherInvestingChanges,quarterlyInterestReceivedCFI,quarterlyDividendsReceivedCFI,quarterlyNetInvestmentPurchaseAndSale,quarterlySaleOfInvestment,quarterlyPurchaseOfInvestment,quarterlyNetInvestmentPropertiesPurchaseAndSale,quarterlySaleOfInvestmentProperties,quarterlyPurchaseOfInvestmentProperties,quarterlyNetBusinessPurchaseAndSale,quarterlySaleOfBusiness,quarterlyPurchaseOfBusiness,quarterlyNetIntangiblesPurchaseAndSale,quarterlySaleOfIntangibles,quarterlyPurchaseOfIntangibles,quarterlyNetPPEPurchaseAndSale,quarterlySaleOfPPE,quarterlyPurchaseOfPPE,quarterlyCapitalExpenditureReported,quarterlyOperatingCashFlow,quarterlyCashFromDiscontinuedOperatingActivities,quarterlyCashFlowFromContinuingOperatingActivities,quarterlyTaxesRefundPaid,quarterlyInterestReceivedCFO,quarterlyInterestPaidCFO,quarterlyDividendReceivedCFO,quarterlyDividendPaidCFO,quarterlyChangeInWorkingCapital,quarterlyChangeInOtherWorkingCapital,quarterlyChangeInOtherCurrentLiabilities,quarterlyChangeInOtherCurrentAssets,quarterlyChangeInPayablesAndAccruedExpense,quarterlyChangeInAccruedExpense,quarterlyChangeInInterestPayable,quarterlyChangeInPayable,quarterlyChangeInDividendPayable,quarterlyChangeInAccountPayable,quarterlyChangeInTaxPayable,quarterlyChangeInIncomeTaxPayable,quarterlyChangeInPrepaidAssets,quarterlyChangeInInventory,quarterlyChangeInReceivables,quarterlyChangesInAccountReceivables,quarterlyOtherNonCashItems,quarterlyExcessTaxBenefitFromStockBasedCompensation,quarterlyStockBasedCompensation,quarterlyUnrealizedGainLossOnInvestmentSecurities,quarterlyProvisionandWriteOffofAssets,quarterlyAssetImpairmentCharge,quarterlyAmortizationOfSecurities,quarterlyDeferredTax,quarterlyDeferredIncomeTax,quarterlyDepreciationAmortizationDepletion,quarterlyDepletion,quarterlyDepreciationAndAmortization,quarterlyAmortizationCashFlow,quarterlyAmortizationOfIntangibles,quarterlyDepreciation,quarterlyOperatingGainsLosses,quarterlyPensionAndEmployeeBenefitExpense,quarterlyEarningsLossesFromEquityInvestments,quarterlyGainLossOnInvestmentSecurities,quarterlyNetForeignCurrencyExchangeGainLoss,quarterlyGainLossOnSaleOfPPE,quarterlyGainLossOnSaleOfBusiness,quarterlyNetIncomeFromContinuingOperations,quarterlyCashFlowsfromusedinOperatingActivitiesDirect,quarterlyTaxesRefundPaidDirect,quarterlyInterestReceivedDirect,quarterlyInterestPaidDirect,quarterlyDividendsReceivedDirect,quarterlyDividendsPaidDirect,quarterlyClassesofCashPayments,quarterlyOtherCashPaymentsfromOperatingActivities,quarterlyPaymentsonBehalfofEmployees,quarterlyPaymentstoSuppliersforGoodsandServices,quarterlyClassesofCashReceiptsfromOperatingActivities,quarterlyOtherCashReceiptsfromOperatingActivities,quarterlyReceiptsfromGovernmentGrants,quarterlyReceiptsfromCustomers',
            'Y': 'annualForeignSales,annualDomesticSales,annualAdjustedGeographySegmentData,annualFreeCashFlow,annualRepurchaseOfCapitalStock,annualRepaymentOfDebt,annualIssuanceOfDebt,annualIssuanceOfCapitalStock,annualCapitalExpenditure,annualInterestPaidSupplementalData,annualIncomeTaxPaidSupplementalData,annualEndCashPosition,annualOtherCashAdjustmentOutsideChangeinCash,annualBeginningCashPosition,annualEffectOfExchangeRateChanges,annualChangesInCash,annualOtherCashAdjustmentInsideChangeinCash,annualCashFlowFromDiscontinuedOperation,annualFinancingCashFlow,annualCashFromDiscontinuedFinancingActivities,annualCashFlowFromContinuingFinancingActivities,annualNetOtherFinancingCharges,annualInterestPaidCFF,annualProceedsFromStockOptionExercised,annualCashDividendsPaid,annualPreferredStockDividendPaid,annualCommonStockDividendPaid,annualNetPreferredStockIssuance,annualPreferredStockPayments,annualPreferredStockIssuance,annualNetCommonStockIssuance,annualCommonStockPayments,annualCommonStockIssuance,annualNetIssuancePaymentsOfDebt,annualNetShortTermDebtIssuance,annualShortTermDebtPayments,annualShortTermDebtIssuance,annualNetLongTermDebtIssuance,annualLongTermDebtPayments,annualLongTermDebtIssuance,annualInvestingCashFlow,annualCashFromDiscontinuedInvestingActivities,annualCashFlowFromContinuingInvestingActivities,annualNetOtherInvestingChanges,annualInterestReceivedCFI,annualDividendsReceivedCFI,annualNetInvestmentPurchaseAndSale,annualSaleOfInvestment,annualPurchaseOfInvestment,annualNetInvestmentPropertiesPurchaseAndSale,annualSaleOfInvestmentProperties,annualPurchaseOfInvestmentProperties,annualNetBusinessPurchaseAndSale,annualSaleOfBusiness,annualPurchaseOfBusiness,annualNetIntangiblesPurchaseAndSale,annualSaleOfIntangibles,annualPurchaseOfIntangibles,annualNetPPEPurchaseAndSale,annualSaleOfPPE,annualPurchaseOfPPE,annualCapitalExpenditureReported,annualOperatingCashFlow,annualCashFromDiscontinuedOperatingActivities,annualCashFlowFromContinuingOperatingActivities,annualTaxesRefundPaid,annualInterestReceivedCFO,annualInterestPaidCFO,annualDividendReceivedCFO,annualDividendPaidCFO,annualChangeInWorkingCapital,annualChangeInOtherWorkingCapital,annualChangeInOtherCurrentLiabilities,annualChangeInOtherCurrentAssets,annualChangeInPayablesAndAccruedExpense,annualChangeInAccruedExpense,annualChangeInInterestPayable,annualChangeInPayable,annualChangeInDividendPayable,annualChangeInAccountPayable,annualChangeInTaxPayable,annualChangeInIncomeTaxPayable,annualChangeInPrepaidAssets,annualChangeInInventory,annualChangeInReceivables,annualChangesInAccountReceivables,annualOtherNonCashItems,annualExcessTaxBenefitFromStockBasedCompensation,annualStockBasedCompensation,annualUnrealizedGainLossOnInvestmentSecurities,annualProvisionandWriteOffofAssets,annualAssetImpairmentCharge,annualAmortizationOfSecurities,annualDeferredTax,annualDeferredIncomeTax,annualDepreciationAmortizationDepletion,annualDepletion,annualDepreciationAndAmortization,annualAmortizationCashFlow,annualAmortizationOfIntangibles,annualDepreciation,annualOperatingGainsLosses,annualPensionAndEmployeeBenefitExpense,annualEarningsLossesFromEquityInvestments,annualGainLossOnInvestmentSecurities,annualNetForeignCurrencyExchangeGainLoss,annualGainLossOnSaleOfPPE,annualGainLossOnSaleOfBusiness,annualNetIncomeFromContinuingOperations,annualCashFlowsfromusedinOperatingActivitiesDirect,annualTaxesRefundPaidDirect,annualInterestReceivedDirect,annualInterestPaidDirect,annualDividendsReceivedDirect,annualDividendsPaidDirect,annualClassesofCashPayments,annualOtherCashPaymentsfromOperatingActivities,annualPaymentsonBehalfofEmployees,annualPaymentstoSuppliersforGoodsandServices,annualClassesofCashReceiptsfromOperatingActivities,annualOtherCashReceiptsfromOperatingActivities,annualReceiptsfromGovernmentGrants,annualReceiptsfromCustomers',
            'T': ''
        },
        'statistics': {
            'Q': 'quarterlyMarketCap,quarterlyEnterpriseValue,quarterlyPeRatio,quarterlyForwardPeRatio,quarterlyPegRatio,quarterlyPsRatio,quarterlyPbRatio,quarterlyEnterprisesValueRevenueRatio,quarterlyEnterprisesValueEBITDARatio'
        }
    }
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "DNT": "1",
        "Origin": "https://finance.yahoo.com",
        "Pragma": "no-cache",
        "Referer": "https://finance.yahoo.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }
    # 쿼리 파라미터 구성
    params = {
        'merge': 'false',
        'padTimeSeries': 'true',
        'period1': int(time.mktime((datetime.now() - timedelta(days=365 * years)).timetuple())),  # 10년 전
        'period2': int(time.mktime(datetime.now().timetuple())),  # 현재
        'lang': 'ko-KR',  # 한국어 설정
        'region': 'KR',  # 대한민국 설정
        'type': types[report][period]
    }

    # GET 요청 전송
    response = requests.get(base_url, params=params, headers=headers)
    if response.status_code != 200:
        raise ConnectionError(f"데이터 가져오기 실패: {response.status_code} - {response.text}")

    data = response.json()

    # print(json.dumps(data, ensure_ascii=False, indent=3))
    if 'timeseries' not in data or 'result' not in data['timeseries']:
        raise ValueError("잘못된 응답 구조입니다.")

    results = data['timeseries']['result']

    df_list = []

    for item in results:
        meta = item.get('meta', {})
        data_type = meta.get('type', [None])[0]
        timestamps = item.get('timestamp', [])
        data_points = item.get(data_type, [])

        if not data_type or not data_points:
            continue  # 데이터가 없는 경우 건너뜀

        # 데이터 추출
        records = []
        missing_data_count = 0
        for ts, dp in zip(timestamps, data_points):
            date = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
            if dp is None:
                reported_value = None
                missing_data_count += 1
            else:
                reported_value = dp.get('reportedValue', {}).get('raw', None)
            records.append({'Date': date, data_type: reported_value})

        # if missing_data_count > 0:
        #     print(f"Warning: {missing_data_count} missing data points for {data_type}")

        df = pd.DataFrame(records)
        df.set_index('Date', inplace=True)
        df_list.append(df)

    if not df_list:
        return pd.DataFrame()  # 데이터가 없는 경우 빈 DataFrame 반환

    # 모든 DataFrame을 Date 기준으로 병합
    final_df = pd.concat(df_list, axis=1)

    # 날짜 순으로 정렬
    final_df.sort_index(inplace=True)

    return final_df


def get_financial_summary_for_update_stock_usa(symbol: str, year: int = 5):
    result = dict()
    balance_df = fetch_financial_timeseries(symbol=symbol, report='balance', period='Q', years=1)
    result['Debt Ratio'] = float(balance_df.iloc[-1]['quarterlyTotalDebt'] / balance_df.iloc[-1]['quarterlyTotalAssets'] * 100)

    statistics_df = fetch_financial_timeseries(symbol=symbol, report='statistics', period='Q', years=1)
    # result['ROE']
    # result['ROA']
    result['PER'] = float(statistics_df.iloc[-1]['quarterlyPeRatio'])
    result['PBR'] = float(statistics_df.iloc[-1]['quarterlyPbRatio'])

    base_url = "https://query1.finance.yahoo.com/v8/finance/chart/"
    params = {
        "events": "capitalGain|div|split",
        "formatted": "true",
        "includeAdjustedClose": "true",
        "interval": '1d',
        "period1": int((datetime.now() - relativedelta(years=year)).timestamp()),
        "period2": int(datetime.now().timestamp()),
        "symbol": symbol,
        "userYfid": "true",
        "lang": "en-US",
        "region": "US"
    }

    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "DNT": "1",
        "Origin": "https://finance.yahoo.com",
        "Pragma": "no-cache",
        "Referer": "https://finance.yahoo.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }
    response = requests.get(base_url + symbol, params=params, headers=headers)
    response.raise_for_status()
    data = response.json()
    result['Dividend Rate'] = 0
    for values in data['chart']['result'][0]['events']['dividends'].values():
        result['Dividend Rate'] += float(values['amount'])
    result['Dividend Rate'] = result['Dividend Rate'] / float(data['chart']['result'][0]['indicators']['quote'][0]['close'][-1]) * 100 / year
    return result


if __name__ == "__main__":
    # 사용 예시
    symbol = "MO"
    print(get_financial_summary_for_update_stock_usa('AAPL'))
