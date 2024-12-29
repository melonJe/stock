import re
from functools import reduce

import pandas as pd
import requests
from bs4 import BeautifulSoup

pd.set_option('display.max_columns', None)


def html_table_to_dataframe_for_fnguide(table, include_estimates=False) -> pd.DataFrame:
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
        match = re.search(r'(\d{4}/\d{2}(\(E\)|)|전년동기(\(%\)|))', txt)
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
                # 헤더로 인식된 index 길이에 맞춰 리스트 뒤에서부터 잘라 매핑
                data[key] = values[-len(index):]

    df = pd.DataFrame(data, index=index)

    # 추정치(E)가 포함된 항목 제거(옵션)
    if not include_estimates:
        df = df[~df.index.str.contains(r'\(E\)')]

    return df


def get_finance_from_fnguide(symbol: str, report='highlight', report_type: str = 'D', period: str = 'Q', include_estimates: bool = False) -> pd.DataFrame:
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
            df_list.append(html_table_to_dataframe_for_fnguide(table_highlight, include_estimates))
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
                df_list.append(html_table_to_dataframe_for_fnguide(table, include_estimates))
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

    return result


if __name__ == "__main__":
    # 사용 예시
    symbol_code = "005930"  # 삼성전자

    summary_dict = get_financial_summary_for_update_stock(symbol_code)
    summary_dict = {key: float(re.search(r'([1-9]{1}\d{0,1}|0{1})(\.{1}\d{0,2})?', value).group()) for key, value in summary_dict.items()}
    print("[종합 요약 정보]\n", summary_dict)
