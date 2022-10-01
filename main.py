import win32com.client

# 연결 여부 체크
objCpCybos = win32com.client.Dispatch("CpUtil.CpCybos")
bConnect = objCpCybos.IsConnect
if (bConnect == 0):
    print("PLUS가 정상적으로 연결되지 않음. ")
    exit()

# 종목코드 리스트 구하기
objCpCodeMgr = win32com.client.Dispatch("CpUtil.CpCodeMgr")
codeList = []
for i in range(1, 6):
    codeList.extend(objCpCodeMgr.GetStockListByMarket(i))

for i, code in enumerate(codeList):
    secondCode = objCpCodeMgr.GetStockSectionKind(code)
    name = objCpCodeMgr.CodeToName(code)
    stdPrice = objCpCodeMgr.GetStockStdPrice(code)
    print(i, code, secondCode, stdPrice, name)

