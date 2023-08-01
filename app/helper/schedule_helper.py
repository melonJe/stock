import traceback

import FinanceDataReader
import pandas as pd
from datetime import datetime, timedelta
from app.database.db_connect import *
from app.helper import discord
from app.service import bollingerBands


def add_stock():
    now = datetime.now()
    if now.day != 1:
        return
    df_krx = FinanceDataReader.StockListing('KRX')
    insert_set = list()
    for item in df_krx.to_dict('records'):
        insert_set.append({'symbol': item['Code'], 'name': item['Name']})
    session.execute(insert(Stock).prefix_with('REPLACE'), insert_set)
    session.commit()
    print(f'add_stock   {now}')


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
    session.execute(insert(StockPrice).prefix_with('IGNORE'), insert_set)
    session.commit()
    print(f'add_stock_price_1day   {now}')
    discord.send_message(f'add_stock_price_1day   {now}')


def add_stock_price_1week():
    now = datetime.now()
    if now.weekday() in (5, 6):
        return
    week_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')
    now = now.strftime('%Y-%m-%d')
    stock = session.scalars(select(Stock.symbol))
    for stock_symbol in stock:
        insert_set = list()
        df_krx = FinanceDataReader.DataReader(stock_symbol, week_ago, now)
        for idx, item in df_krx.iterrows():
            insert_set.append({'symbol': stock_symbol, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']})
        session.execute(insert(StockPrice).prefix_with('IGNORE'), insert_set)
    session.commit()
    print(f'add_stock_price_1week   {now}')
    discord.send_message(f'add_stock_price_1week   {now}')


def add_stock_price_all():
    for stock_symbol in session.scalars(select(Stock.symbol)):
        df_krx = FinanceDataReader.DataReader(stock_symbol)
        insert_set = list()
        for idx, item in df_krx.iterrows():
            insert_set.append({'symbol': stock_symbol, 'date': idx, 'open': item['Open'], 'high': item['High'], 'close': item['Close'], 'low': item['Low']})
        session.execute(insert(StockPrice).prefix_with('IGNORE'), insert_set)
    session.commit()
    print(f'add_stock_price_all')


def alert(num_std=2):
    message = f"{datetime.now().date()}\n"
    window = buy_sell(window=5, num_std=num_std)
    message += f"bollinger_band 5\nbuy : {window['buy']}\nsell : {window['sell']}\n\n"
    window = buy_sell(window=20, num_std=num_std)
    message += f"bollinger_band 20\nbuy : {window['buy']}\nsell : {window['sell']}\n\n"
    window = buy_sell(window=60, num_std=num_std)
    message += f"bollinger_band 60\nbuy : {window['buy']}\nsell : {window['sell']}"
    discord.send_message(message)


def buy_sell(window=20, num_std=2):
    # if datetime.now().weekday() in (5, 6):
    #     return
    decision = {'buy': set(), 'sell': set()}
    try:
        # stock = session.scalars(select(Stock.symbol))
        stock = session.scalars(select(StockSubscription.symbol).where(StockSubscription.email == 'cabs0814@naver.com'))
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
        discord.error_message("stock_db\n" + str(traceback.print_exc()))
    return decision
