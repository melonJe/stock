import traceback
from datetime import datetime

from stock.discord import discord
from stock.korea_investment.api import KoreaInvestmentAPI


# TODO 파일명 정리 및 하위폴더 정리 필요
def korea_investment_trading_buy(ki_api: KoreaInvestmentAPI, symbol: str, price: int, volume: int):
    account = ki_api.get_account_info()
    try:
        stock = ki_api.get_owned_stock_info(symbol)
        if volume > 0 and stock:  # 구매 수량이 0보다 크고 보유 중인 주식일 경우
            volume = min(volume, int((account.tot_evlu_amt * 0.2 - int(stock.pchs_amt)) / price))  # 주식 보유 비중이 15%를 넘지 않도록 구매 수량 수정
        else:
            volume = min(volume, int(account.tot_evlu_amt * 0.2 / price))  # 주식 보유 비중이 15%를 넘지 않도록 구매 수량 수정
        if volume > 0:
            ki_api.buy(symbol=symbol, price=price, volume=volume)
            discord.send_message(f"{symbol} 주식 {price}원으로 {volume}수량 구매 = {price * volume:,}")
    except Exception as e:
        traceback.print_exc()
        print(f"Error occurred: {e}")


def korea_investment_trading_buy_reserve(ki_api: KoreaInvestmentAPI, symbol: str, price: int, volume: int, end_date: str):
    try:
        if volume > 0:
            ki_api.buy_reserve(symbol=symbol, price=price, volume=volume, end_date=end_date)
            # discord.send_message(f"{symbol} 주식 {price}원으로 {volume}수량 예약 구매 = {price * volume:,}")
    except Exception as e:
        traceback.print_exc()
        print(f"Error occurred: {e}")


def korea_investment_trading_sell(ki_api: KoreaInvestmentAPI, symbol: str, price: int, volume: int):
    print(f'{datetime.now()} korea_investment_trading_sell')
    try:
        stock = ki_api.get_owned_stock_info(symbol)
        if (not stock) or int(stock.ord_psbl_qty) == 0:  # 가지고 있지 않거나 주문 가능한 수량이 없으면 다음 주식으로 넘어감
            print(f"{symbol} 가지고 있지 않거나 주문 가능한 수량이 없음")
            return
        if volume > int(stock.ord_psbl_qty):  # 주문 가능 수량을 넘길 경우 주문 수량 수정
            volume = int(stock.ord_psbl_qty)
        if volume < 1 or ki_api.sell(symbol=symbol, price=price, volume=volume):
            print(symbol, price, volume)
            return True
    except Exception as e:
        traceback.print_exc()
        print(f"Error occurred: {e}")


def korea_investment_trading_sell_reserve(ki_api: KoreaInvestmentAPI, symbol: str, price: int, volume: int, end_date: str):
    print(f'{datetime.now()}, {symbol}, {price}, {volume} korea_investment_trading_sell_reserve')
    try:
        stock = ki_api.get_owned_stock_info(symbol)
        if (not stock) or int(stock.ord_psbl_qty) == 0:  # 가지고 있지 않거나 주문 가능한 수량이 없으면 다음 주식으로 넘어감
            print(f"{symbol} 가지고 있지 않거나 주문 가능한 수량이 없음")
            return
        if volume > int(stock.ord_psbl_qty):  # 주문 가능 수량을 넘길 경우 주문 수량 수정
            volume = int(stock.ord_psbl_qty)
        if volume < 1 or ki_api.sell_reserve(symbol=symbol, price=price, volume=volume, end_date=end_date):
            print(symbol, price, volume)
            return True
    except Exception as e:
        traceback.print_exc()
        print(f"Error occurred: {e}")
