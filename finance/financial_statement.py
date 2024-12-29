import re

import pandas as pd
import requests
from bs4 import BeautifulSoup


def get_financial_summary(symbol: str, report_type='D', period='Q', include_estimates=False) -> pd.DataFrame:
    url = f'https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?pGB=1&gicode=A{symbol}&cID=&MenuYn=Y&ReportGB=&NewMenuID=101&stkGb=701'
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    if report_type not in ['D', 'B']:
        raise ValueError(f"Invalid value for parameter 'report_type': {report_type}. "
                         f"Valid options are: {', '.join(['D', 'B'])}.")

    if period not in ['A', 'Y', 'Q']:
        raise ValueError(f"Invalid value for parameter 'period': {period}. "
                         f"Valid options are: {', '.join(['A', 'Y', 'Q'])}.")

    try:
        div = soup.select(f"div#highlight_{report_type}_{period}")[0]
    except IndexError:
        raise ValueError("Unable to get the div on the page.")

    index = [
        match.group() for match in
        (re.search(r'\d{4}/\d{2}(\(E\)|)', th.get_text(strip=True)) for th in div.select("th", {"scope": "col"}))
        if match
    ]

    data = {}
    for tbody in div.select("tbody")[0].select("tr"):
        header = tbody.select_one("div")
        if header.select_one('dt'):
            header = header.select_one('dt').get_text(strip=True)
        else:
            header = header.get_text(strip=True)
        if header:
            key = header
            values = [td.get_text(strip=True) for td in tbody.select("td")]
            data[key] = values
    df = pd.DataFrame(data, index=index)

    if not include_estimates:
        df = df[~df.index.str.contains(r'\(E\)')]

    return df


def get_last_financial_summary(symbol: str, report_type='D', period='A', include_estimates=False) -> pd.DataFrame:
    return get_financial_summary(symbol=symbol, report_type=report_type, period=period, include_estimates=include_estimates).tail(1)
