"""워크플로우 공통 함수"""
from typing import List, Union

from config import setting_env
from config.logging_config import get_logger
from data.database import db_connect
from data.dto.account_dto import StockResponseDTO
from data.models import Subscription
from services.data_handler import get_country_by_symbol
from services.strategies import DividendStrategy, GrowthStrategy, RangeBoundStrategy
from services.trading_helpers import add_prev_close_allocation, fetch_price_dataframe, normalize_dataframe_for_country
from utils import discord
from utils.operations import price_refine
from core.exceptions import OrderError
from core.decorators import log_execution
from core.error_handler import handle_error

logger = get_logger(__name__)


def select_buy_stocks(country: str = "KOR") -> dict[str, dict[float, int]]:
    """매수 종목 선택"""
    buy_levels = {}

    strategies = [
        DividendStrategy(),
        GrowthStrategy(),
        RangeBoundStrategy(),
    ]

    for strategy in strategies:
        try:
            result = strategy.filter_for_buy(country=country)
            for sym, price_dict in result.items():
                for price, qty in price_dict.items():
                    buy_levels.setdefault(sym, {})
                    buy_levels[sym][price] = buy_levels[sym].get(price, 0) + qty
        except Exception as e:
            logger.error(f"select_buy_stocks 전략 실행 오류: {e}")

    return buy_levels


def select_sell_stocks(stocks_held: Union[List[StockResponseDTO], StockResponseDTO, None]) -> dict[str, dict[float, int]]:
    """매도 종목 선택"""
    sell_levels = {}

    strategies = [
        DividendStrategy(),
        GrowthStrategy(),
        RangeBoundStrategy(),
    ]

    for strategy in strategies:
        try:
            result = strategy.filter_for_sell(stocks_held)
            for sym, price_dict in result.items():
                for price, qty in price_dict.items():
                    sell_levels.setdefault(sym, {})
                    sell_levels[sym][price] = sell_levels[sym].get(price, 0) + qty
        except Exception as e:
            logger.error(f"select_sell_stocks 전략 실행 오류: {e}")

    # 구독하지 않은 종목 처리
    non_sub_result = filter_non_subscription_for_sell(stocks_held)
    for sym, price_dict in non_sub_result.items():
        for price, qty in price_dict.items():
            sell_levels.setdefault(sym, {})
            sell_levels[sym][price] = sell_levels[sym].get(price, 0) + qty

    # 보유 수량 제한 적용
    if not stocks_held or not sell_levels:
        return sell_levels

    holdings = stocks_held if isinstance(stocks_held, list) else [stocks_held]
    limits: dict[str, int] = {}
    for stock in holdings:
        try:
            symbol = stock.pdno
        except Exception:
            continue

        try:
            hldg_qty = int(float(getattr(stock, "hldg_qty", 0) or 0))
        except (TypeError, ValueError):
            hldg_qty = 0

        limits[symbol] = hldg_qty

    for symbol in list(sell_levels.keys()):
        max_qty = limits.get(symbol, 0)
        price_qty = sell_levels[symbol]

        total_sell = sum(price_qty.values())
        if total_sell <= max_qty:
            continue

        if total_sell == 0:
            del sell_levels[symbol]
            continue

        ratio = max_qty / total_sell
        new_price_qty: dict[float, int] = {}
        for price, qty in price_qty.items():
            adj = int(qty * ratio)
            if adj > 0:
                new_price_qty[price] = adj

        if new_price_qty:
            sell_levels[symbol] = new_price_qty
        else:
            del sell_levels[symbol]

    return sell_levels


def filter_non_subscription_for_sell(
        stocks_held: Union[List[StockResponseDTO], StockResponseDTO, None]
) -> dict[str, dict[float, int]]:
    """구독하지 않은 보유 종목을 전일 종가로 전량 매도 대상으로 반환"""
    sell_levels: dict[str, dict[float, int]] = {}
    if not stocks_held:
        return sell_levels

    holdings = stocks_held if isinstance(stocks_held, list) else [stocks_held]
    subscribed_symbols = {sub.symbol for sub in Subscription.select(Subscription.symbol)}

    for stock in holdings:
        try:
            symbol = stock.pdno
        except Exception:
            continue

        if symbol in subscribed_symbols:
            continue

        country = get_country_by_symbol(symbol)
        if not country:
            continue

        try:
            hldg_qty = int(float(getattr(stock, "hldg_qty", 0) or 0))
        except (TypeError, ValueError):
            hldg_qty = 0

        if hldg_qty <= 0:
            continue

        try:
            df = fetch_price_dataframe(symbol)
            if df is None or df.empty or len(df) < 2:
                continue
            df = normalize_dataframe_for_country(df, country)

            prev_close = float(df.iloc[-2]["close"])
            if prev_close <= 0:
                continue

            sell_price = prev_close
            sell_levels.setdefault(symbol, {})[sell_price] = hldg_qty
        except Exception as e:
            logger.error(f"filter_non_subscription_for_sell 처리 중 에러: {symbol} -> {e}")
            continue

    return sell_levels


@log_execution(level=logging.INFO)
def trading_buy(client, buy_levels):
    """
    매수 주문 실행

    :param client: KISClient 인스턴스
    :param buy_levels: 매수 대상 {symbol: {price: volume}}
    """
    try:
        end_date = client.get_nth_open_day(3)
    except Exception as e:
        logger.critical(f"trading_buy 오픈일 조회 실패: {e}")
        return

    money = 0

    for symbol, levels in buy_levels.items():
        try:
            country = get_country_by_symbol(symbol)
            stock = client.get_owned_stock_info(symbol=symbol)
            for price, volume in levels.items():
                if stock and price > float(stock.pchs_avg_pric) * 0.975:
                    continue

                try:
                    if country == "KOR":
                        price = price_refine(price)
                        client.buy_reserve(symbol=symbol, price=price, volume=volume, end_date=end_date)
                        money += price * volume
                    elif country == "USA":
                        try:
                            result = client.buy(symbol, price, volume)
                            if result:
                                logger.info(f"매수 성공: {symbol} {volume}주 @{price}")
                            else:
                                error = OrderError(f"매수 실패: {symbol}")
                                handle_error(
                                    error,
                                    context="trading_buy",
                                    metadata={"symbol": symbol, "price": price, "volume": volume},
                                    should_raise=False
                                )
                        except Exception as e:
                            error = OrderError(f"매수 중 예외 발생: {symbol}", original_error=e)
                            handle_error(
                                error,
                                context="trading_buy",
                                critical=True,
                                metadata={"symbol": symbol, "price": price, "volume": volume},
                                should_raise=False
                            )
                        money += price * volume
                except Exception as e:
                    logger.critical(f"trading_buy 주문 실패: {symbol} -> {e}")
        except Exception as e:
            logger.error(f"trading_buy 처리 중 에러: {symbol} -> {e}")

    if money:
        try:
            discord.send_message(f'총 액 : {money}')
        except Exception as e:
            logger.error(f"trading_buy 디스코드 전송 실패: {e}")


@log_execution(level=logging.INFO)
def trading_sell(client, sell_levels):
    """
    매도 주문 실행

    :param client: KISClient 인스턴스
    :param sell_levels: 매도 대상 {symbol: {price: volume}}
    """
    try:
        end_date = client.get_nth_open_day(1)
    except Exception as e:
        logger.critical(f"trading_sell 오픈일 조회 실패: {e}")
        return

    for symbol, levels in (sell_levels or {}).items():
        try:
            country = get_country_by_symbol(symbol)
            stock = client.get_owned_stock_info(symbol=symbol)
            if not stock:
                continue

            try:
                hldg_qty = int(float(getattr(stock, "hldg_qty", 0) or 0))
            except (TypeError, ValueError):
                hldg_qty = 0

            for price, volume in levels.items():
                volume = min(volume, hldg_qty)
                if volume <= 0:
                    continue
                hldg_qty -= volume

                try:
                    if country == "KOR":
                        if price < float(stock.pchs_avg_pric):
                            price = price_refine(int(float(stock.pchs_avg_pric) * 1.002), 1)
                        client.sell_reserve(symbol=symbol, price=int(price), volume=volume, end_date=end_date)
                    elif country == "USA":
                        if price < float(stock.pchs_avg_pric):
                            price = round(float(stock.pchs_avg_pric) * 1.005, 2)
                        client.submit_overseas_reservation_order(
                            country=country,
                            action="sell",
                            symbol=symbol,
                            price=str(round(float(price), 2)),
                            volume=str(volume)
                        )
                except Exception as e:
                    logger.critical(f"trading_sell 주문 실패: {symbol} -> {e}")
        except Exception as e:
            logger.error(f"trading_sell 처리 중 에러: {symbol} -> {e}")
