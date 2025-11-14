import json
from typing import Sequence

import requests


TRADINGVIEW_HEADERS = {
    "Content-Type": "text/plain;charset=UTF-8",
    "Accept": "application/json",
    "Origin": "https://kr.tradingview.com",
    "Referer": "https://kr.tradingview.com/",
    "User-Agent": "Mozilla/5.0",
}


TRADINGVIEW_FILTER_PRIMARY = [
    {"left": "is_primary", "operation": "equal", "right": True}
]


TRADINGVIEW_FILTER_STOCK_TYPES = {
    "operator": "and",
    "operands": [
        {
            "operation": {
                "operator": "or",
                "operands": [
                    {
                        "operation": {
                            "operator": "and",
                            "operands": [
                                {"expression": {"left": "type", "operation": "equal", "right": "stock"}},
                                {"expression": {"left": "typespecs", "operation": "has", "right": ["common"]}},
                            ],
                        }
                    },
                    {
                        "operation": {
                            "operator": "and",
                            "operands": [
                                {"expression": {"left": "type", "operation": "equal", "right": "stock"}},
                                {"expression": {"left": "typespecs", "operation": "has", "right": ["preferred"]}},
                            ],
                        }
                    },
                    {
                        "operation": {
                            "operator": "and",
                            "operands": [
                                {"expression": {"left": "type", "operation": "equal", "right": "dr"}},
                            ],
                        }
                    },
                    {
                        "operation": {
                            "operator": "and",
                            "operands": [
                                {"expression": {"left": "type", "operation": "equal", "right": "fund"}},
                                {"expression": {"left": "typespecs", "operation": "has_none_of", "right": ["etf"]}},
                            ],
                        }
                    },
                ],
            }
        }
    ],
}


def build_tradingview_payload(
    *,
    columns: Sequence[str],
    max_count: int,
    sort: dict,
    markets: Sequence[str],
    ignore_unknown_fields: bool = False,
) -> dict:
    """Return a TradingView scanner payload with standard filters applied."""
    return {
        "symbols": {},
        "columns": list(columns),
        "filter": TRADINGVIEW_FILTER_PRIMARY,
        "filter2": TRADINGVIEW_FILTER_STOCK_TYPES,
        "ignore_unknown_fields": ignore_unknown_fields,
        "markets": list(markets),
        "options": {"lang": "ko"},
        "range": [0, max_count],
        "sort": sort,
    }


def request_tradingview_scan(country: str, payload: dict) -> dict:
    """Execute TradingView scanner request for ``country``."""
    url = f"https://scanner.tradingview.com/{country}/scan?label-product=screener-stock"
    response = requests.post(url, headers=TRADINGVIEW_HEADERS, data=json.dumps(payload))
    response.raise_for_status()
    return response.json()
