"""시장 상황 분석 및 VIX 체크 유틸리티"""
import datetime
from typing import Optional, Tuple

import FinanceDataReader
import pandas as pd

from config.logging_config import get_logger
from config.strategy_config import RISK_CONFIG, MARKET_CONDITION_CONFIG

logger = get_logger(__name__)


def get_vix() -> Optional[float]:
    """현재 VIX 지수 조회"""
    try:
        df = FinanceDataReader.DataReader("VIX", 
            start=(datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d"))
        if df is None or df.empty:
            return None
        return float(df.iloc[-1]["Close"])
    except Exception as e:
        logger.warning(f"VIX 조회 실패: {e}")
        return None


def is_buy_allowed() -> Tuple[bool, Optional[float]]:
    """
    매수 가능 여부 확인 (VIX 기반)
    
    Returns:
        Tuple[bool, Optional[float]]: (매수가능여부, 현재VIX)
    """
    vix = get_vix()
    if vix is None:
        logger.warning("VIX 조회 불가, 매수 허용")
        return True, None
    
    if vix >= RISK_CONFIG.vix_buy_halt_threshold:
        logger.warning(f"VIX {vix:.2f} >= {RISK_CONFIG.vix_buy_halt_threshold}, 매수 중단")
        return False, vix
    
    return True, vix


def get_market_trend(country: str = "USA") -> str:
    """
    시장 추세 판단 (상승/횡보/하락)
    
    Args:
        country: 국가 코드 (USA, KOR)
    
    Returns:
        str: "bull", "neutral", "bear"
    """
    try:
        index_symbol = "^GSPC" if country == "USA" else "KS11"
        df = FinanceDataReader.DataReader(index_symbol,
            start=(datetime.datetime.now() - datetime.timedelta(days=200)).strftime("%Y-%m-%d"))
        
        if df is None or len(df) < 50:
            return "neutral"
        
        close = df["Close"]
        sma50 = close.rolling(50).mean()
        sma200 = close.rolling(200).mean()
        
        current_price = float(close.iloc[-1])
        sma50_val = float(sma50.iloc[-1]) if not pd.isna(sma50.iloc[-1]) else current_price
        sma200_val = float(sma200.iloc[-1]) if not pd.isna(sma200.iloc[-1]) else current_price
        
        # 골든크로스/데드크로스 + 가격 위치
        if current_price > sma50_val > sma200_val:
            return "bull"
        elif current_price < sma50_val < sma200_val:
            return "bear"
        else:
            return "neutral"
            
    except Exception as e:
        logger.warning(f"시장 추세 판단 실패: {e}")
        return "neutral"


def get_sell_ratio_adjusted(base_ratio: float, vix: Optional[float] = None) -> float:
    """
    VIX 기반 매도 비율 조정
    
    Args:
        base_ratio: 기본 매도 비율
        vix: 현재 VIX (None이면 조회)
    
    Returns:
        float: 조정된 매도 비율
    """
    if vix is None:
        vix = get_vix()
    
    if vix is None:
        return base_ratio
    
    multiplier = MARKET_CONDITION_CONFIG.get_sell_ratio_multiplier(vix)
    adjusted = min(1.0, base_ratio * multiplier)
    
    logger.debug(f"매도비율 조정: {base_ratio:.2f} * {multiplier:.2f} = {adjusted:.2f} (VIX: {vix:.2f})")
    return adjusted


def get_position_size_adjusted(base_size: int, country: str = "USA") -> int:
    """
    시장 상황 기반 포지션 사이즈 조정
    
    Args:
        base_size: 기본 포지션 사이즈
        country: 국가 코드
    
    Returns:
        int: 조정된 포지션 사이즈
    """
    market_trend = get_market_trend(country)
    multiplier = MARKET_CONDITION_CONFIG.get_position_multiplier(market_trend)
    adjusted = max(1, int(base_size * multiplier))
    
    logger.debug(f"포지션 조정: {base_size} * {multiplier:.2f} = {adjusted} (추세: {market_trend})")
    return adjusted


def check_52week_high_drawdown(df: pd.DataFrame, min_dd: float = 0.15, max_dd: float = 0.35) -> bool:
    """
    52주 신고가 대비 조정폭 확인
    
    Args:
        df: 가격 데이터프레임
        min_dd: 최소 조정폭
        max_dd: 최대 조정폭
    
    Returns:
        bool: 조건 충족 여부
    """
    if df is None or len(df) < 252:
        return False
    
    try:
        high_52w = float(df["high"].tail(252).max())
        current_price = float(df.iloc[-1]["close"])
        
        if high_52w <= 0:
            return False
        
        drawdown = (high_52w - current_price) / high_52w
        return min_dd <= drawdown <= max_dd
    except (KeyError, IndexError, ValueError):
        return False


def check_breakout_with_volume(df: pd.DataFrame, lookback: int = 5, volume_mult: float = 1.5) -> bool:
    """
    브레이크아웃 + 거래량 급증 확인
    
    Args:
        df: 가격 데이터프레임
        lookback: 확인 기간
        volume_mult: 평균 대비 거래량 배수
    
    Returns:
        bool: 브레이크아웃 조건 충족 여부
    """
    if df is None or len(df) < 30:
        return False
    
    try:
        recent = df.tail(lookback)
        avg_volume = float(df["volume"].rolling(20).mean().iloc[-lookback-1])
        resistance = float(df["high"].iloc[-lookback-1:-1].max())
        
        if avg_volume <= 0 or resistance <= 0:
            return False
        
        # 최근 기간 내 저항선 돌파 + 거래량 급증
        for i in range(len(recent)):
            close = float(recent.iloc[i]["close"])
            volume = float(recent.iloc[i]["volume"])
            
            if close > resistance and volume > avg_volume * volume_mult:
                return True
        
        return False
    except (KeyError, IndexError, ValueError):
        return False


def check_range_bound_duration(df: pd.DataFrame, min_days: int = 20, bb_width_range: Tuple[float, float] = (0.07, 0.18)) -> bool:
    """
    박스권 최소 유지 기간 확인
    
    Args:
        df: 가격 데이터프레임 (BB 컬럼 포함)
        min_days: 최소 유지 일수
        bb_width_range: BB 폭 허용 범위
    
    Returns:
        bool: 박스권 유지 조건 충족 여부
    """
    if df is None or len(df) < min_days or "BB_Upper" not in df.columns:
        return False
    
    try:
        recent = df.tail(min_days)
        count_in_range = 0
        
        for i in range(len(recent)):
            bb_upper = float(recent.iloc[i]["BB_Upper"])
            bb_lower = float(recent.iloc[i]["BB_Lower"])
            bb_mavg = float(recent.iloc[i]["BB_Mavg"])
            
            if pd.isna(bb_upper) or pd.isna(bb_lower) or bb_mavg <= 0:
                continue
            
            width = (bb_upper - bb_lower) / bb_mavg
            if bb_width_range[0] <= width <= bb_width_range[1]:
                count_in_range += 1
        
        # 최소 80% 이상의 기간이 박스권 범위 내
        return count_in_range >= min_days * 0.8
    except (KeyError, IndexError, ValueError):
        return False


def check_fakeout_filter(df: pd.DataFrame, confirm_days: int = 3) -> bool:
    """
    가짜 돌파 필터 (BB 하단 돌파 후 복귀 확인)
    
    Args:
        df: 가격 데이터프레임 (BB 컬럼 포함)
        confirm_days: 확인 기간
    
    Returns:
        bool: 진짜 진입 신호인지 여부 (가짜 돌파가 아님)
    """
    if df is None or len(df) < confirm_days + 5 or "BB_Lower" not in df.columns:
        return True  # 데이터 부족 시 통과
    
    try:
        recent = df.tail(confirm_days + 5)
        
        # 최근 confirm_days+5일 내에 BB 하단 터치 후 복귀 패턴 확인
        touched_lower = False
        recovered = False
        
        for i in range(len(recent) - confirm_days):
            low = float(recent.iloc[i]["low"])
            bb_lower = float(recent.iloc[i]["BB_Lower"])
            
            if pd.isna(bb_lower):
                continue
            
            if low <= bb_lower * 1.02:  # 2% 이내 터치
                touched_lower = True
                
                # 이후 confirm_days 내 복귀 확인
                for j in range(1, min(confirm_days + 1, len(recent) - i)):
                    future_close = float(recent.iloc[i + j]["close"])
                    future_bb_lower = float(recent.iloc[i + j]["BB_Lower"])
                    
                    if not pd.isna(future_bb_lower) and future_close > future_bb_lower * 1.05:
                        recovered = True
                        break
                
                if touched_lower and recovered:
                    return True
        
        # 터치하지 않았거나 복귀 패턴이면 진입 허용
        return not touched_lower or recovered
    except (KeyError, IndexError, ValueError):
        return True
