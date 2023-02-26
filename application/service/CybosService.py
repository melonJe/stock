from ponySetting import *
import win32com.client


class CybosService:
    objCpCodeMgr = win32com.client.Dispatch("CpUtil.CpCodeMgr")

    def __init__(self):
        objCpCybos = win32com.client.Dispatch("CpUtil.CpCybos")
        bConnect = objCpCybos.IsConnect
        if (bConnect == 0):
            print("PLUS가 정상적으로 연결되지 않음. ")
            exit()
        self.objCpCodeMgr = win32com.client.Dispatch("CpUtil.CpCodeMgr")

    def insert_stock(self):
        with pony.db_session:
            saved_stock = {x.symbol for x in Stock.select()}
            for i in (1, 2, 3, 4, 5):
                for j, code in enumerate(self.objCpCodeMgr.GetStockListByMarket(i)):
                    if code[0] == 'A' and not code[1:] in saved_stock:
                        Stock(symbol=code[1:], name=self.objCpCodeMgr.CodeToName(code), unit='KRW')
            pony.commit()

    def insert_stock_price(self):
        pass


stock_service = CybosService()
