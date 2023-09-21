import requests
import setting_env
import urllib.parse


class KoreaInvestment:
    __app_key: str = ''
    __app_secret: str = ''
    __hash: str = ''
    __access_token: str = ''
    __account_number: str = ''
    __account_cord: str = ''

    def __init__(self, app_key: str, app_secret: str, account_number: str, account_cord: str):
        self.__app_key = app_key
        self.__app_secret = app_secret
        self.__account_number = account_number
        self.__account_cord = account_cord
        data = {"grant_type": "client_credentials",
                "appkey": self.__app_key,
                "appsecret": self.__app_secret
                }
        response = requests.post(setting_env.DOMAIN + "/oauth2/tokenP", json=data)
        if response.status_code == 200:
            data = response.json()
            self.__access_token = data["token_type"] + " " + data["access_token"]
        else:
            raise ValueError(f"""HTTP 요청 실패. 상태 코드: {response.status_code}\n{response.content}""")

    def buy(self, stock: str, price: int, volume: int, ord_dvsn: str = "00"):
        headers = {
            "authorization": self.__access_token,
            "appkey": self.__app_key,
            "appsecret": self.__app_secret,
            "tr_id": setting_env.TR_ID + "TTC0802U",
        }
        data = {
            "CANO": self.__account_number,
            "ACNT_PRDT_CD": self.__account_cord,
            "PDNO": stock,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": volume,
            "ORD_UNPR": price
        }
        if data["ORD_DVSN"] != "00":
            data["ORD_UNPR"] = 0
        response = requests.post(setting_env.DOMAIN + "/uapi/domestic-stock/v1/trading/order-cash", headers=headers, json=data)
        if response.status_code == 200:
            data = response.json()
            return True if data["rt_cd"] == "0" else False
        else:
            return False

    def sell(self, stock: str, price: int, volume: int, ord_dvsn: str = "00"):
        headers = {
            "authorization": self.__access_token,
            "appkey": self.__app_key,
            "appsecret": self.__app_secret,
            "tr_id": setting_env.TR_ID + "TTC0801U",
        }
        data = {
            "CANO": self.__account_number,
            "ACNT_PRDT_CD": self.__account_cord,
            "PDNO": stock,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": volume,
            "ORD_UNPR": price
        }
        if data["ORD_DVSN"] != "00":
            data["ORD_UNPR"] = 0
        response = requests.post(setting_env.DOMAIN + "/uapi/domestic-stock/v1/trading/order-cash", headers=headers, json=data)
        if response.status_code == 200:
            data = response.json()
            return True if data["rt_cd"] == "0" else False
        else:
            return False

    def inquire_balance(self):
        headers = {
            "authorization": self.__access_token,
            "appkey": self.__app_key,
            "appsecret": self.__app_secret,
            "tr_id": setting_env.TR_ID + "TTC8434R",
        }
        data = {
            "CANO": self.__account_number,
            "ACNT_PRDT_CD": self.__account_cord,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "N",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        response = requests.get(setting_env.DOMAIN + "/uapi/domestic-stock/v1/trading/inquire-balance?" + urllib.parse.urlencode(data), headers=headers)
        if response.status_code == 200:
            return response.json()["output2"]
        else:
            raise requests.exceptions.HTTPError(f"""HTTP 요청 실패. 상태 코드: {response.status_code}\n{response.content}""")

    def inquire_stock(self, stock: str):
        headers = {
            "authorization": self.__access_token,
            "appkey": self.__app_key,
            "appsecret": self.__app_secret,
            "tr_id": setting_env.TR_ID + "TTC8434R",
        }
        data = {
            "CANO": self.__account_number,
            "ACNT_PRDT_CD": self.__account_cord,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "N",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        response = requests.get(setting_env.DOMAIN + "/uapi/domestic-stock/v1/trading/inquire-balance?" + urllib.parse.urlencode(data), headers=headers)
        if response.status_code == 200:
            for item in response.json()["output1"]:
                if item["pdno"] == stock:
                    return item
            return None
        else:
            raise requests.exceptions.HTTPError(f"""HTTP 요청 실패. 상태 코드: {response.status_code}\n{response.content}""")

# account = KoreaInvestment(app_key := setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_cord=setting_env.ACCOUNT_CORD)
# print(account.inquire_stock(stock="003030"))
