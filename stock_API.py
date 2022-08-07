import requests
import secret
import pandas as pd

def get_stock_price(**kwargs):
    s = 'https://api.odcloud.kr/api/GetStockSecuritiesInfoService/v1/getStockPriceInfo?resultType=json'
    for x in kwargs.items():
        s += '&' + str(x[0]) + '=' + str(x[1])
    s += '&serviceKey=' + secret.SERVICEKEY
    req_data = requests.get(s).json()
    req_data = req_data['response']['body']['items']['item']
    return pd.DataFrame(x for x in req_data).sort_values(by='basDt')[['srtnCd', 'basDt', 'hipr', 'clpr', 'lopr', 'trqu']].astype({'clpr': 'int64', 'trqu': 'int64'})
