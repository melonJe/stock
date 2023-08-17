import traceback
import FinanceDataReader
import requests
import pandas as pd
from datetime import timedelta
from app.database.db_connect import *
from app.helper import discord
from app.service import bollingerBands
from bs4 import BeautifulSoup as bs


def update_subscription():
    # 방어적 투자
    now = datetime.now()
    # if now.day != 1:
    #     return
    stock = set(session.scalars(select(Stock.symbol)))
    insert_set = list()
    for stock_symbol in stock:
        value = 0
        try:
            if requests.get(f'https://navercomp.wisereport.co.kr/company/chart/c1030001.aspx?cmp_cd={stock_symbol}&frq=Y&rpt=ISM&finGubun=MAIN&chartType=svg',
                            headers={'Accept': 'application/json'}).json()['chartData1']['series'][0]['data'][-2] < 10000:
                continue
            page = requests.get(f'https://comp.fnguide.com/SVO2/ASP/SVD_FinanceRatio.asp?pGB=1&gicode=A{stock_symbol}&cID=&MenuYn=Y&ReportGB=&NewMenuID=104&stkGb=701').text
            soup = bs(page, "html.parser")
            current_ratio = float(soup.select('tr#p_grid1_1 > td.cle')[0].text)
            if current_ratio < 200:
                continue
            page = requests.get(f'https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx?cmp_cd={stock_symbol}').text
            soup = bs(page, "html.parser")
            elements = soup.select('td.cmp-table-cell > dl > dt.line-left')
            per = -1
            pbr = -1
            dividend_rate = -1
            for x in elements:
                item = x.text.split(' ')
                if item[0] == 'PER':
                    per = float(item[1])
                if item[0] == 'PBR':
                    pbr = float(item[1])
                if item[0] == '현금배당수익률':
                    dividend_rate = float(item[1][:-1])
        except:
            continue
        del item
        if dividend_rate == -1:
            continue
        if per > 15:
            continue
        if per * pbr > 22.5:
            continue
        insert_set.append({'email': 'cabs0814@naver.com', 'symbol': stock_symbol})
    if insert_set:
        # delete(StockSubscription).where(StockSubscription.email == 'cabs0814@naver.com')
        session.execute(insert(StockSubscription), insert_set)
        session.commit()


def add_stock():
    now = datetime.now()
    if now.day != 1:
        return
    df_krx = FinanceDataReader.StockListing('KRX')
    insert_set = [{'symbol': item['Code'], 'name': item['Name']} for item in df_krx.to_dict('records')]
    insert_stmt = insert(Stock).values(insert_set)
    insert_stmt = insert_stmt.on_duplicate_key_update(
        symbol=insert_stmt.inserted.symbol
    )
    session.execute(insert_stmt)
    session.commit()
    # discord.send_message(f'add_stock   {now}')


def add_stock_price_1day():
    now = datetime.now()
    if now.weekday() in (5, 6):
        return
    now = now.strftime('%Y-%m-%d')
    insert_set = list()
    stock = session.scalars(select(Stock.symbol))
    for stock_symbol in stock:
        df_krx = FinanceDataReader.DataReader(stock_symbol, now, now)
        for idx, item in df_krx.iterrows():
            insert_set.append({'symbol': stock_symbol, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']})
    insert_stmt = insert(StockPrice).values(insert_set)
    insert_stmt = insert_stmt.on_duplicate_key_update(
        symbol=insert_stmt.inserted.symbol,
        date=insert_stmt.inserted.date
    )
    session.execute(insert_stmt)
    session.commit()
    # discord.send_message(f'add_stock_price_1day   {now}')


def add_stock_price_1week():
    now = datetime.now()
    if now.weekday() in (5, 6):
        return
    week_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')
    now = now.strftime('%Y-%m-%d')
    for stock_symbol in session.scalars(select(Stock.symbol)):
        df_krx = FinanceDataReader.DataReader(stock_symbol, week_ago, now)
        insert_set = [{'symbol': stock_symbol, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']} for idx, item in
                      df_krx.iterrows()]
        if df_krx.empty:
            continue
        insert_stmt = insert(StockPrice).values(insert_set)
        insert_stmt = insert_stmt.on_duplicate_key_update(
            symbol=insert_stmt.inserted.symbol,
            date=insert_stmt.inserted.date
        )
        session.execute(insert_stmt)
    session.commit()
    # discord.send_message(f'add_stock_price_1week   {now}')


def add_stock_price_all():
    for stock_symbol in session.scalars(select(Stock.symbol)):
        df_krx = FinanceDataReader.DataReader(stock_symbol)
        insert_set = [{'symbol': stock_symbol, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']} for idx, item in
                      df_krx.iterrows()]
        if df_krx.empty:
            continue
        insert_stmt = insert(StockPrice).values(insert_set)
        insert_stmt = insert_stmt.on_duplicate_key_update(
            symbol=insert_stmt.inserted.symbol,
            date=insert_stmt.inserted.date
        )
        session.execute(insert_stmt)
    session.commit()


def alert(num_std=2):
    if datetime.now().weekday() in (5, 6):
        return
    message = f"{datetime.now().date()}\n"
    window = buy_sell_bollinger_band(window=5, num_std=num_std)
    message += f"bollinger_band 5\nbuy : {window['buy']}\nsell : {window['sell']}\n\n"
    window = buy_sell_bollinger_band(window=20, num_std=num_std)
    message += f"bollinger_band 20\nbuy : {window['buy']}\nsell : {window['sell']}\n\n"
    window = buy_sell_bollinger_band(window=60, num_std=num_std)
    message += f"bollinger_band 60\nbuy : {window['buy']}\nsell : {window['sell']}\n\n"
    window = buy_sell_trend_judgment()
    message += f"trend_judgment\nbuy : {window['buy']}\nsell : {window['sell']}"
    print(message)
    # discord.send_message(message)


def buy_sell_bollinger_band(window=20, num_std=2):
    decision = {'buy': set(), 'sell': set()}
    try:
        # stock = Database().get_session(.)scalars(select(Stock.symbol))
        stock = session.scalars(union(select(StockSubscription.symbol).where(StockSubscription.email == 'cabs0814@naver.com'),
                                      select(StockBuy.symbol).where(StockBuy.email == 'cabs0814@naver.com')))
        for stock_symbol in stock:
            name = session.scalars(select(Stock.name).where(Stock.symbol == stock_symbol).order_by(Stock.name.desc())).first()
            data = pd.read_sql(select(StockPrice).order_by(StockPrice.date.desc()).limit(100).where(
                (StockPrice.date >= (datetime.now() - timedelta(days=200))) & (StockPrice.symbol == stock_symbol)), session.bind).sort_values(by='date', ascending=True)
            if data.empty:
                continue
            bollingerBands.bollinger_band(data, window=window, num_std=num_std)
            # if data.iloc[-2]['open'] < data.iloc[-2]['close'] and data.iloc[-2]['open'] < data.iloc[-1]['open'] < data.iloc[-2]['close']:
            #     continue
            # if data.iloc[-2]['open'] > data.iloc[-2]['close'] and data.iloc[-2]['open'] > data.iloc[-1]['open'] > data.iloc[-2]['close']:
            #     continue
            if data.iloc[-1]['decision'] == 'buy':
                decision['buy'].add(name)
            if data.iloc[-1]['decision'] == 'sell':
                decision['sell'].add(name)
            del data, name
            # TODO: custom exception
    except:
        pass
        # discord.error_message("stock_db\n" + str(traceback.print_exc()))
    return decision


def buy_sell_trend_judgment():
    decision = {'buy': set(), 'sell': set()}
    try:
        # stock = session.scalars(select(Stock.symbol))
        stock = session.scalars(select(StockSubscription.symbol).where(StockSubscription.email == 'cabs0814@naver.com'))
        for stock_symbol in stock:
            name = session.scalars(select(Stock.name).where(Stock.symbol == stock_symbol).order_by(Stock.name.desc())).first()
            data = pd.read_sql(select(StockPrice).order_by(StockPrice.date.desc()).limit(260).where(
                (StockPrice.date >= (datetime.now() - timedelta(days=365))) & (StockPrice.symbol == stock_symbol)), session.bind).sort_values(by='date', ascending=True)
            if data.empty:
                continue
            # TODO 추세 판단 알고리즘 적용
            data['ma200'] = data['close'].rolling(window=200).mean()
            data['ma150'] = data['close'].rolling(window=150).mean()
            data['ma50'] = data['close'].rolling(window=50).mean()
            if data.iloc[-1]['close'] < data.iloc[-1]['ma200']:
                continue
            if data.iloc[-1]['close'] < data.iloc[-1]['ma150']:
                continue
            if data.iloc[-1]['close'] < data.iloc[-1]['ma50']:
                continue
            if data.iloc[-1]['ma50'] < data.iloc[-1]['ma200']:
                continue
            if data.iloc[-1]['ma50'] < data.iloc[-1]['ma150']:
                continue
            if data.iloc[-1]['ma150'] < data.iloc[-1]['ma200']:
                continue
            if data.iloc[-1]['close'] < data['close'].max() * 0.75 and data.iloc[-1]['close'] / data['close'].max() > 0.95:
                continue
            if data.iloc[-1]['close'] < data['close'].min() * 1.25:
                continue
            decision['buy'].add(f"{name}  {data.iloc[-1]['close'] / data['close'].max()}")

        stock = session.scalars(select(StockBuy.symbol).where(StockBuy.email == 'cabs0814@naver.com'))
        for stock_symbol in stock:
            name = session.scalars(select(Stock.name).where(Stock.symbol == stock_symbol).order_by(Stock.name.desc())).first()
            data = pd.read_sql(select(StockPrice).order_by(StockPrice.date.desc()).limit(260).where(
                (StockPrice.date >= (datetime.now() - timedelta(days=365))) & (StockPrice.symbol == stock_symbol)), session.bind).sort_values(by='date', ascending=True)
            if data.empty:
                continue
            # TODO 추세 판단 알고리즘 적용
            data['ma200'] = data['close'].rolling(window=200).mean()
            if data.iloc[-1]['close'] < data.iloc[-1]['ma200']:
                decision['sell'].add(name)
            # TODO: custom exception
    except:
        pass
        # discord.error_message("stock_db\n" + str(traceback.print_exc()))
    return decision


alert()
