import logging
import threading
import traceback
from datetime import timedelta, datetime, time
from time import sleep

import numpy as np
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django.db.models import Q, Sum
from ta.volatility import AverageTrueRange
from ta.volume import ChaikinMoneyFlowIndicator

import stock.utils.stock_management as stock_update
from stock import setting_env
from stock.discord import discord
from stock.korea_investment.api import KoreaInvestmentAPI
from stock.korea_investment.trading import korea_investment_trading_sell_reserve, korea_investment_trading_buy_reserve
from stock.korea_investment.utils import price_refine
from stock.models import Account, SellQueue, Stock, Subscription, Blacklist, PriceHistory, StopLoss


def select_buy_stocks() -> dict:
    """
    특정 기준에 따라 매수할 주식을 선택합니다.

    이 함수는 현재 주식 시장 데이터를 분석하고,
    주식을 평가한 후 매수할 주식을 선택합니다.
    
    반환값:
        dict: 키는 주식 식별자이고 값은 선택된 주식에 대한 세부 정보를 포함하는 사전입니다.
    """
    result = dict()
    try:
        stocks = set(x['symbol'] for x in Subscription.objects.exclude(Q(symbol__in=Blacklist.objects.values_list('symbol', flat=True))).select_related("symbol").values('symbol'))
        buy = dict()
        sieve = dict()
        for symbol in stocks:
            df = pd.DataFrame(PriceHistory.objects.filter(date__range=[datetime.now() - timedelta(days=550), datetime.now()], symbol=symbol).order_by('date').values())
            if len(df) < 300:  # or df.iloc[-1]['low'] < 10000:
                continue

            # 일봉데이터 주봉으로 변환
            # df['date'] = pd.to_datetime(df['date'])
            # w_df = df.resample('W-Sun', on='date').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'})

            df['ma60'] = df['close'].rolling(window=60).mean()
            if df.iloc[-1]['ma60'] > df.iloc[-1]['low']:
                continue

            df['ma240'] = df['close'].rolling(window=240).mean()
            df['ma120'] = df['close'].rolling(window=120).mean()
            last_3_days = df[-3:]  # DataFrame의 마지막 3일을 선택
            condition1 = np.any(last_3_days['ma240'] > last_3_days['close'])
            condition2 = np.any(last_3_days['ma120'] > last_3_days['close'])
            if condition1 or condition2:
                continue

            last_10_days = df[-10:]  # DataFrame의 마지막 10일을 선택
            condition1 = np.all(last_10_days['ma240'] < last_10_days['close'])
            condition2 = np.all(last_10_days['ma120'] < last_10_days['close'])
            if condition1 and condition2:
                continue

            df['ma20'] = df['close'].rolling(window=20).mean()
            df['ma10'] = df['close'].rolling(window=10).mean()
            # 60, 20, 10, 5, close 순서대로 있지 않으면 다음 주식으로 넘어감
            if not (df.iloc[-1]['ma60'] < df.iloc[-1]['ma20'] < df.iloc[-1]['ma10'] < df.iloc[-1]['close']):
                continue

            df['CMF'] = ChaikinMoneyFlowIndicator(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), volume=df['volume'].astype('float64')).chaikin_money_flow()
            if df.iloc[-1]['CMF'] > 0.25:
                df['ATR5'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=5).average_true_range()
                df['ATR10'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=10).average_true_range()
                df['ATR20'] = AverageTrueRange(high=df['high'].astype('float64'), low=df['low'].astype('float64'), close=df['close'].astype('float64'), window=20).average_true_range()
                atr = max(df.iloc[-1]['ATR5'], df.iloc[-1]['ATR10'], df.iloc[-1]['ATR20'])
                volume = min(int((10000000 / (100 * atr))), int(np.min(df['volume'][-5:]) / 100))  # 수량 = 계좌 잔액 / 100 / atr
                buy[symbol] = volume
                sieve[symbol] = df.iloc[-1]['CMF']
        for x in list(dict(sorted(sieve.items(), key=lambda item: item[1], reverse=True)).keys()):
            result[x] = buy[x]
    except Exception as e:
        traceback.print_exc()
        logging.error(f"Error occurred: {e}")
    return result


def trading_buy(ki_api: KoreaInvestmentAPI, buy: dict):
    try:
        account = ki_api.get_account_info()
    except Exception as e:
        traceback.print_exc()
        logging.error(f"Error occurred while getting account info: {e}")
        return

    try:
        end_date = ki_api.get_nth_open_day(3)
    except Exception as e:
        traceback.print_exc()
        logging.error(f"Error occurred while getting nth open day: {e}")
        return

    money = 0

    for symbol, volume in buy.items():
        try:
            stock = ki_api.get_owned_stock_info(symbol)
            df = pd.DataFrame(PriceHistory.objects.filter(date__range=[datetime.now() - timedelta(days=100), datetime.now()], symbol=symbol).order_by('date').values())

            if df.empty:
                logging.error(f"No price history found for symbol: {symbol}")
                continue
            elif len(df) < 20:
                logging.error(f"Not enough price history for symbol: {symbol}")
                continue

            stock_update.stop_loss_insert(symbol)
            df['ma5'] = df['close'].rolling(window=5).mean()
            df['ma10'] = df['close'].rolling(window=10).mean()
            df['ma20'] = df['close'].rolling(window=20).mean()

            if stock:
                continue
                # if int(account.tot_evlu_amt) * 0.15 < (int(stock.evlu_amt) + price * volume):
                #     volume = int((int(account.tot_evlu_amt) * 0.15 - int(stock.evlu_amt)) / price)
                # volume = int(volume / 3)
            # else:
            #     if int(account.tot_evlu_amt) * 0.15 < price * volume:
            #         volume = int(int(account.tot_evlu_amt) * 0.15 / price)

            last_row = df.iloc[-1]
            for price in (price_refine(price) for price in [last_row['close'] + last_row['open'], last_row['ma5'], last_row['ma10'], last_row['ma20']]):
                try:
                    korea_investment_trading_buy_reserve(ki_api=ki_api, symbol=symbol, price=price, volume=int(volume * 0.3), end_date=end_date)
                    money += price * int(volume * 0.3)
                except Exception as e:
                    traceback.print_exc()
                    logging.error(f"Error occurred while executing trades for symbol {symbol}: {e}")

        except Exception as e:
            traceback.print_exc()
            logging.error(f"Error occurred while processing symbol {symbol}: {e}")

    if money:
        try:
            discord.send_message(f'총 액 : {money}')
        except Exception as e:
            traceback.print_exc()
            logging.error(f"Error occurred while sending message to Discord: {e}")


def update_sell_queue(ki_api: KoreaInvestmentAPI, email: Account):
    today_str = datetime.now().strftime("%Y%m%d")
    response_data = ki_api.get_stock_order_list(start_date=today_str, end_date=today_str)

    if not response_data:
        logging.info("Failed to retrieve sell data")
        return

    sell_queue_entries = {}
    for trade in response_data:
        symbol = Stock.objects.get(symbol=trade.pdno)  # 주식 심볼
        volume = int(trade.tot_ccld_qty)  # 체결된 주식 수량
        price = int(trade.avg_prvs)  # 체결된 가격
        trade_type = trade.sll_buy_dvsn_cd  # 매도/매수 구분 코드 (01: 매도, 02: 매수)

        if trade_type == "02":  # 매수
            volumes_and_prices = [
                (int(volume * 0.5), price_refine(int(price * 1.1))),
                (int(volume * 0.3), price_refine(int(price * 1.2))),
                (volume - int(volume * 0.5) - int(volume * 0.3), price_refine(int(price * 1.5)))
            ]

            for vol, prc in volumes_and_prices:
                if vol > 0:
                    sell_queue_entries[(email, symbol, prc)] = sell_queue_entries.get((email, symbol, prc), 0) + vol

        elif trade_type == "01":  # 매도
            sell_queue_entries[(email, symbol, price)] = sell_queue_entries.get((email, symbol, price), 0) - volume

    for (email, symbol, price), volume in sell_queue_entries.items():
        try:
            sell_entry = SellQueue.objects.get(email=email, symbol=symbol, price=price)
            sell_entry.volume += volume
            if sell_entry.volume <= 0:
                sell_entry.delete()
            else:
                sell_entry.save()
        except SellQueue.DoesNotExist:
            if volume > 0:
                SellQueue.objects.create(email=email, symbol=symbol, volume=volume, price=price)

    owned_stock_info = ki_api.get_owned_stock_info()
    for stock in owned_stock_info:
        symbol = Stock.objects.get(symbol=stock.pdno)  # 주식 심볼
        owned_volume = int(stock.hldg_qty)
        total_db_volume = SellQueue.objects.filter(email=email, symbol=stock.pdno).aggregate(total_volume=Sum('volume'))['total_volume'] or 0

        if owned_volume < total_db_volume:
            excess_volume = total_db_volume - owned_volume
            while excess_volume > 0:
                smallest_price_entry = SellQueue.objects.filter(email=email, symbol=symbol).order_by('price').first()
                if smallest_price_entry:
                    if smallest_price_entry.volume <= excess_volume:
                        excess_volume -= smallest_price_entry.volume
                        smallest_price_entry.delete()
                    else:
                        smallest_price_entry.volume -= excess_volume
                        smallest_price_entry.save()
                        excess_volume = 0
        elif owned_volume > total_db_volume:
            additional_volume = owned_volume - total_db_volume
            avg_price = float(stock.pchs_avg_pric)

            volumes_and_prices = [
                (int(additional_volume * 0.5), price_refine(int(avg_price * 1.1))),
                (int(additional_volume * 0.3), price_refine(int(avg_price * 1.2))),
                (additional_volume - int(additional_volume * 0.5) - int(additional_volume * 0.3), price_refine(int(avg_price * 1.5)))
            ]

            for vol, prc in volumes_and_prices:
                if vol > 0:
                    try:
                        sell_entry = SellQueue.objects.get(email=email, symbol=symbol, price=prc)
                        sell_entry.volume += vol
                        sell_entry.save()
                    except SellQueue.DoesNotExist:
                        SellQueue.objects.create(email=email, symbol=symbol, volume=vol, price=prc)

    SellQueue.objects.filter(volume__lte=0).delete()


def trading_sell(ki_api: KoreaInvestmentAPI):
    end_date = ki_api.get_nth_open_day(1)
    queue_entries = SellQueue.objects.filter(email="cabs0814@naver.com")
    for entry in queue_entries:
        stock = ki_api.get_owned_stock_info(entry.symbol.symbol)
        if not stock:
            discord.send_message(f'Not held a stock {entry.symbol.company_name}')
            continue
        sell_price = price_refine(entry.price)
        if sell_price < float(stock.pchs_avg_pric):
            discord.send_message(f'Sell {stock.prdt_name} below average purchase price: {sell_price}')

        korea_investment_trading_sell_reserve(ki_api, symbol=entry.symbol.symbol, price=sell_price, volume=entry.volume, end_date=end_date)


def stop_loss_notify(ki_api: KoreaInvestmentAPI):
    alert = set()
    while datetime.now().time() < time(15, 30, 00):
        owned_stock = ki_api.get_owned_stock_info()
        for item in owned_stock:
            try:
                if item.pdno in alert:
                    continue
                stock = StopLoss.objects.filter(symbol=item.pdno).first()
                if not stock:
                    stock_update.stop_loss_insert(item.pdno)
                    continue
                if stock.price < int(item.prpr):
                    continue
                discord.send_message(f"{item.prdt_name} 판매 권유")
                logging.info(f"{item.prdt_name} 판매 권유")
                Subscription.objects.filter(symbol=item.pdno).delete()
                alert.add(item.pdno)
            except Exception as e:
                logging.error(f"Error processing item {item.pdno}: {e}")
                traceback.print_exc()

        sleep(1 * 60)


def korea_investment_trading():
    # TODO 일정 % 수익 때 마다 판매 기능 구축을 위한 DB table 생성 profit_sell (symbol, price, volume(단위 %, int * 100), expire_date...?)
    ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_code=setting_env.ACCOUNT_CODE)
    if ki_api.check_holiday(datetime.now().strftime("%Y%m%d")):
        logging.info(f'{datetime.now()} 휴장일')
        return
    stop_loss = threading.Thread(target=stop_loss_notify, args=(ki_api,))
    stop_loss.start()

    while datetime.now().time() < time(15, 35, 30):
        sleep(1 * 60)

    stock_update.add_stock_price(start_date=datetime.now().strftime('%Y-%m-%d'), end_date=datetime.now().strftime('%Y-%m-%d'))
    for stock in ki_api.get_owned_stock_info():
        stock_update.stop_loss_insert(stock.pdno)

    while datetime.now().time() < time(16, 00, 30):
        sleep(1 * 60)

    update_sell_queue(ki_api, email=Account.objects.get(email='cabs0814@naver.com'))

    sell = threading.Thread(target=trading_sell, args=(ki_api,))
    sell.start()
    buy_stock = select_buy_stocks()
    buy = threading.Thread(target=trading_buy, args=(ki_api, buy_stock,))
    buy.start()
    # TODO profit_sell 테이블 정리 기능 추가


def start():
    scheduler = BackgroundScheduler(misfire_grace_time=3600, coalesce=True, timezone=settings.TIME_ZONE)
    # ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_code=setting_env.ACCOUNT_CODE)
    # update_sell_queue(ki_api, email=Account.objects.get(email='cabs0814@naver.com'))
    # stock_update.add_stock_price(start_date=datetime.now().strftime('%Y-%m-%d'), end_date=datetime.now().strftime('%Y-%m-%d'))
    # trading_buy(ki_api=ki_api, buy=select_buy_stocks())
    # trading_sell(ki_api=ki_api)

    scheduler.add_job(
        stock_update.update_defensive_subscription_stock,
        trigger=CronTrigger(day=1, hour=2),
        id="update_defensive_subscription_stock",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        stock_update.update_aggressive_subscription_stock,
        trigger=CronTrigger(day=1, hour=4),
        id="update_aggressive_subscription_stock",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        stock_update.add_stock,
        trigger=CronTrigger(day=1, hour=0),
        id="add_stock",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        stock_update.add_stock_price,
        trigger=CronTrigger(day_of_week="sat"),
        kwargs={'start_date': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'), 'end_date': datetime.now().strftime('%Y-%m-%d')},
        id="add_stock_price_1week",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        stock_update.add_stock_price,
        trigger=CronTrigger(day_of_week="mon-fri", hour=18, minute=00, second=00),
        kwargs={'start_date': datetime.now().strftime('%Y-%m-%d'), 'end_date': datetime.now().strftime('%Y-%m-%d')},
        id="add_stock_price_1day",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        stock_update.update_blacklist,
        trigger=CronTrigger(hour=15, minute=30, second=00),
        id="update_blacklist",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        korea_investment_trading,
        trigger=CronTrigger(day_of_week="mon-fri", hour=8, minute=50, second=00),
        id="korea_investment_trading",
        max_instances=1,
        replace_existing=True,
    )

    try:
        scheduler.start()  # 없으면 동작하지 않습니다.
    except KeyboardInterrupt:
        scheduler.shutdown()


def test():
    Blacklist.objects.filter(date__lt=(datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')).delete()
