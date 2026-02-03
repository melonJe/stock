"""대시보드 API 라우터"""
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from config import setting_env
from config.logging_config import get_logger
from clients.kis import KISClient
from data.models import Stock, PriceHistory, PriceHistoryUS
from repositories.stock_repository import StockRepository
from core.security import verify_basic_auth, sanitize_path, mask_sensitive_data

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(verify_basic_auth)]  # 모든 API에 인증 적용
)


# DTO 모델
class AccountInfo(BaseModel):
    """계좌 정보"""
    account_number: str
    total_asset: float
    cash: float
    stock_value: float
    profit_loss: float
    profit_loss_rate: float


class StockHolding(BaseModel):
    """보유 종목"""
    symbol: str
    name: str
    quantity: int
    avg_price: float
    current_price: float
    profit_loss: float
    profit_loss_rate: float
    country: str


class TradingLog(BaseModel):
    """거래 로그"""
    timestamp: datetime
    symbol: str
    action: str
    quantity: int
    price: float
    status: str


class SystemStatus(BaseModel):
    """시스템 상태"""
    scheduler_running: bool
    last_update: datetime
    total_stocks: int
    korea_holdings: int
    usa_holdings: int


@router.get("/account", response_model=AccountInfo)
async def get_account_info(country: str = Query("KOR", regex="^(KOR|USA)$")):
    """
    계좌 정보 조회
    
    :param country: 국가 코드 (KOR, USA)
    """
    try:
        if country == "KOR":
            client = KISClient(
                app_key=setting_env.APP_KEY_KOR,
                app_secret=setting_env.APP_SECRET_KOR,
                account_number=setting_env.ACCOUNT_NUMBER_KOR,
                account_code=setting_env.ACCOUNT_CODE_KOR
            )
        else:
            client = KISClient(
                app_key=setting_env.APP_KEY_USA,
                app_secret=setting_env.APP_SECRET_USA,
                account_number=setting_env.ACCOUNT_NUMBER_USA,
                account_code=setting_env.ACCOUNT_CODE_USA
            )
        
        account_data = client.get_account_info()
        
        if not account_data:
            raise HTTPException(status_code=404, detail="계좌 정보를 가져올 수 없습니다")
        
        # 실제 API 응답 구조에 맞게 파싱
        return AccountInfo(
            account_number=client.account_number,
            total_asset=float(account_data.get("total_asset") or 0),
            cash=float(account_data.get("cash") or 0),
            stock_value=float(account_data.get("stock_value") or 0),
            profit_loss=float(account_data.get("profit_loss") or 0),
            profit_loss_rate=float(account_data.get("profit_loss_rate") or 0)
        )
    except Exception as e:
        logger.error(f"계좌 정보 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/holdings", response_model=List[StockHolding])
async def get_holdings(country: str = Query("KOR", regex="^(KOR|USA)$")):
    """
    보유 종목 조회
    
    :param country: 국가 코드 (KOR, USA)
    """
    try:
        if country == "KOR":
            client = KISClient(
                app_key=setting_env.APP_KEY_KOR,
                app_secret=setting_env.APP_SECRET_KOR,
                account_number=setting_env.ACCOUNT_NUMBER_KOR,
                account_code=setting_env.ACCOUNT_CODE_KOR
            )
            holdings_data = client.get_korea_owned_stock_info()
        else:
            client = KISClient(
                app_key=setting_env.APP_KEY_USA,
                app_secret=setting_env.APP_SECRET_USA,
                account_number=setting_env.ACCOUNT_NUMBER_USA,
                account_code=setting_env.ACCOUNT_CODE_USA
            )
            holdings_data = client.get_oversea_owned_stock_info()
        
        if not holdings_data:
            return []
        
        result = []
        for stock in holdings_data:
            result.append(StockHolding(
                symbol=stock.get("symbol") or "",
                name=stock.get("name") or "",
                quantity=int(stock.get("quantity") or 0),
                avg_price=float(stock.get("avg_price") or 0),
                current_price=float(stock.get("current_price") or 0),
                profit_loss=float(stock.get("profit_loss") or 0),
                profit_loss_rate=float(stock.get("profit_loss_rate") or 0),
                country=country
            ))
        
        return result
    except Exception as e:
        logger.error(f"보유 종목 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs", response_model=List[str])
async def get_logs(
    log_type: str = Query("app", regex="^(app|error|trading)$"),
    lines: int = Query(100, ge=1, le=1000)
):
    """
    로그 파일 조회 (Path Traversal 방지)
    
    :param log_type: 로그 타입 (app, error, trading)
    :param lines: 조회할 라인 수
    """
    try:
        # Path Traversal 공격 방지
        logs_dir = Path("logs")
        safe_path = sanitize_path(logs_dir, f"{log_type}.log")
        
        with open(safe_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            
            # 민감한 정보 마스킹
            masked_lines = [mask_sensitive_data(line) for line in all_lines[-lines:]]
            return masked_lines
            
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"{log_type} 로그 파일을 찾을 수 없습니다")
    except Exception as e:
        logger.error(f"로그 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="로그 조회 중 오류가 발생했습니다")


@router.get("/status", response_model=SystemStatus)
async def get_system_status():
    """시스템 상태 조회"""
    try:
        # 보유 종목 수 계산
        korea_client = KISClient(
            app_key=setting_env.APP_KEY_KOR,
            app_secret=setting_env.APP_SECRET_KOR,
            account_number=setting_env.ACCOUNT_NUMBER_KOR,
            account_code=setting_env.ACCOUNT_CODE_KOR
        )
        
        korea_holdings = korea_client.get_korea_owned_stock_info() or []
        
        # DB에서 전체 종목 수 조회
        total_stocks = Stock.select().count()
        
        return SystemStatus(
            scheduler_running=True,  # TODO: 실제 스케줄러 상태 확인
            last_update=datetime.now(),
            total_stocks=total_stocks,
            korea_holdings=len(korea_holdings),
            usa_holdings=0  # TODO: 미국 보유 종목 수
        )
    except Exception as e:
        logger.error(f"시스템 상태 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stocks/search")
async def search_stocks(query: str = Query(..., min_length=1)):
    """
    종목 검색
    
    :param query: 검색어 (종목코드 또는 종목명)
    """
    try:
        stocks = Stock.select().where(
            (Stock.symbol.contains(query)) | (Stock.name.contains(query))
        ).limit(20)
        
        return [
            {
                "symbol": stock.symbol,
                "name": stock.name,
                "country": stock.country
            }
            for stock in stocks
        ]
    except Exception as e:
        logger.error(f"종목 검색 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stocks/{symbol}/price-history")
async def get_price_history(
    symbol: str,
    days: int = Query(30, ge=1, le=365)
):
    """
    종목 가격 히스토리 조회
    
    :param symbol: 종목 코드
    :param days: 조회 일수
    """
    try:
        # 종목 정보 조회
        stock = Stock.get_or_none(Stock.symbol == symbol)
        if not stock:
            raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
        
        # 가격 히스토리 조회
        start_date = datetime.now() - timedelta(days=days)
        
        if stock.country == "KOR":
            prices = PriceHistory.select().where(
                (PriceHistory.stock == stock) &
                (PriceHistory.date >= start_date)
            ).order_by(PriceHistory.date)
        else:
            prices = PriceHistoryUS.select().where(
                (PriceHistoryUS.stock == stock) &
                (PriceHistoryUS.date >= start_date)
            ).order_by(PriceHistoryUS.date)
        
        return [
            {
                "date": price.date.isoformat(),
                "open": float(price.open),
                "high": float(price.high),
                "low": float(price.low),
                "close": float(price.close),
                "volume": int(price.volume)
            }
            for price in prices
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"가격 히스토리 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))
