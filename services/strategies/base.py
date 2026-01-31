"""전략 기본 인터페이스"""
from abc import ABC, abstractmethod
from typing import List, Union

from data.dto.account_dto import StockResponseDTO
from config.strategy_config import RISK_CONFIG


class BaseStrategy(ABC):
    """매매 전략 기본 클래스"""

    @abstractmethod
    def filter_for_buy(self, country: str = "KOR") -> dict[str, dict[float, int]]:
        """매수 대상 종목 필터링"""
        pass

    @abstractmethod
    def filter_for_sell(
            self,
            stocks_held: Union[List[StockResponseDTO], StockResponseDTO, None]
    ) -> dict[str, dict[float, int]]:
        """매도 대상 종목 필터링"""
        pass
    
    def _apply_max_position_weight(self, volume: int, close_price: float, risk_amount_value: float) -> int:
        """
        종목당 최대 비중 제한 적용 (공통 로직)
        
        Args:
            volume: 계산된 포지션 수량
            close_price: 현재가
            risk_amount_value: 리스크 금액
        
        Returns:
            int: 최대 비중 제한이 적용된 수량
        """
        estimated_equity = risk_amount_value / 0.0051  # RISK_PCT 기본값
        max_position_value = estimated_equity * RISK_CONFIG.max_position_weight
        max_volume = int(max_position_value / close_price) if close_price > 0 else volume
        return min(volume, max_volume)
