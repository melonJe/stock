import requests
import setting_env
import urllib.parse

from stock.helper import discord


def str_to_number(item: str):
    try:
        return int(item)
    except ValueError:
        try:
            return float(item)
        except ValueError:
            return item


# TODO 예외 처리
class KoreaInvestment:
    __app_key: str = ''
    __app_secret: str = ''
    __hash: str = ''
    __access_token: str = ''
    __account_number: str = ''
    __account_cord: str = ''
    __headers: dict = {}  # TODO __headers 사용하기 ???

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
            discord.error_message(f"""stock_db\nHTTP 요청 실패. 상태 코드 : {response.status_code}\n{response.json()}""")

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
            "ORD_QTY": str(volume),
            "ORD_UNPR": str(price)
        }
        if data["ORD_DVSN"] != "00":
            data["ORD_UNPR"] = 0
        response = requests.post(setting_env.DOMAIN + "/uapi/domestic-stock/v1/trading/order-cash", headers=headers, json=data)
        if response.status_code == 200:
            data = response.json()
            if data["rt_cd"] == "0":
                return True
            else:
                discord.error_message(f"""stock_db\n응답 코드 : {data["msg_cd"]}\n응답 메세지 : {data["msg"]}""")
        else:
            discord.error_message(f"""stock_db\nHTTP 요청 실패. 상태 코드 : {response.status_code}\n{response.json()}""")

    def sell(self, stock: str, price: int, volume: int, order_type: str = "00"):
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
            "ORD_DVSN": order_type,
            "ORD_QTY": str(volume),
            "ORD_UNPR": str(price)
        }
        if data["ORD_DVSN"] != "00":
            data["ORD_UNPR"] = 0
        response = requests.post(setting_env.DOMAIN + "/uapi/domestic-stock/v1/trading/order-cash", headers=headers, json=data)
        if response.status_code == 200:
            data = response.json()
            if data["rt_cd"] == "0":
                return True
            else:
                discord.error_message(f"""stock_db\n응답 코드 : {data["msg_cd"]}\n응답 메세지 : {data["msg"]}\n{data["output"]}""")
        else:
            discord.error_message(f"""stock_db\nHTTP 요청 실패. 상태 코드 : {response.status_code}\n{response.json()}""")

    def get_account_info(self):
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
            data = response.json()["output2"][0]
            for key, value in data.items():
                data[key] = str_to_number(data[key])
            return data
        else:
            discord.error_message(f"""stock_db\nHTTP 요청 실패. 상태 코드 : {response.status_code}\n{response.json()}""")

    def get_owned_stock_info(self, stock: str = None):
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
            data = response.json()["output1"]
            if stock:
                for item in data:
                    if item["pdno"] == stock:
                        for key, value in item.items():
                            if key == "pdno":
                                continue
                            item[key] = str_to_number(item[key])
                        return item
                return None
            else:
                for index in range(len(data)):
                    for key, value in data[index].items():
                        if key == "pdno":
                            continue
                        data[index][key] = str_to_number(data[index][key])
                return data
        else:
            discord.error_message(f"""stock_db\nHTTP 요청 실패. 상태 코드 : {response.status_code}\n{response.json()}""")

    def get_cancellable_or_correctable_stock(self):
        if setting_env.SIMULATE:
            return None
        headers = {
            "authorization": self.__access_token,
            "appkey": self.__app_key,
            "appsecret": self.__app_secret,
            "tr_id": "TTTC8036R",
        }
        data = {
            "CANO": self.__account_number,
            "ACNT_PRDT_CD": self.__account_cord,
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
            "INQR_DVSN_1": "2",
            "INQR_DVSN_2": "0"
        }
        response = requests.get(setting_env.DOMAIN + "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl?" + urllib.parse.urlencode(data), headers=headers)
        if response.status_code == 200:
            return response.json()["output1"]
        else:
            discord.error_message(f"""stock_db\nHTTP 요청 실패. 상태 코드 : {response.status_code}\n{response.json()}""")

    def modify_stock_order(self, order_no: str, volume: str, price: str = '0', order_type: str = '03', order_code: str = '01', all_or_none: str = 'Y'):
        headers = {
            "authorization": self.__access_token,
            "appkey": self.__app_key,
            "appsecret": self.__app_secret,
            "tr_id": setting_env.TR_ID + "TTC0803U",
        }
        data = {
            "CANO": self.__account_number,
            "ACNT_PRDT_CD": self.__account_cord,
            "KRX_FWDG_ORD_ORGNO": "",
            "ORGN_ODNO": order_no,
            "ORD_DVSN": order_type,
            "RVSE_CNCL_DVSN_CD": order_code,
            "ORD_QTY": volume,
            "ORD_UNPR": price,
            "QTY_ALL_ORD_YN": all_or_none
        }
        response = requests.post(setting_env.DOMAIN + "/uapi/domestic-stock/v1/trading/order-rvsecncl", headers=headers, json=data)
        if response.status_code == 200:
            return True
        else:
            discord.error_message(f"""stock_db\nHTTP 요청 실패. 상태 코드 : {response.status_code}\n{response.json()}""")

# account = KoreaInvestment(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_cord=setting_env.ACCOUNT_CORD)
# print(account.get_owned_stock_info(stock="003030"))
