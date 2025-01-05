import logging

import requests


def bulk_upsert(model_class, data: list, update_conflicts: bool, unique_fields: list, update_fields: list = None):
    try:
        model_class.objects.bulk_create(
            [model_class(**vals) for vals in data],
            update_conflicts=update_conflicts,
            unique_fields=unique_fields,
            update_fields=update_fields
        )
    except Exception as e:
        logging.error(f"Error during data insertion: {e}")


def fetch_page_content(url: str) -> str:
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logging.error(f"Failed to fetch page content from {url}: {e}")
        return ""


def parse_finance_ratios(soup) -> tuple:
    elements = soup.select('td.cmp-table-cell > dl > dt.line-left')
    per = pbr = dividend_rate = -1
    for x in elements:
        item = x.text.split(' ')
        if item[0] == 'PER':
            per = float(item[1])
        elif item[0] == 'PBR':
            pbr = float(item[1])
        elif item[0] == '현금배당수익률':
            dividend_rate = float(item[1][:-1])
    return per, pbr, dividend_rate
