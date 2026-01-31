"""전략 기본 인터페이스"""
from abc import ABC, abstractmethod
from typing import List, Union

from data.dto.account_dto import StockResponseDTO


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
