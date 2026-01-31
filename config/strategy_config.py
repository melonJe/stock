"""전략별 설정 및 리스크 관리 파라미터"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# =============================================================================
# 전략 우선순위 (subscription 중복 방지용)
# =============================================================================
STRATEGY_PRIORITY: Dict[str, int] = {
    "dividend": 1,  # 최우선 - 배당주
    "growth": 2,    # 2순위 - 성장주
    "box": 3,       # 3순위 - 박스권
}


# =============================================================================
# 리스크 관리 설정
# =============================================================================
@dataclass
class RiskConfig:
    """리스크 관리 글로벌 설정"""
    max_position_weight: float = 0.15       # 종목당 최대 비중 15%
    vix_buy_halt_threshold: float = 30.0    # VIX 30 이상 매수 중단
    stop_loss_ratio: float = 0.07           # 손절선 -7%
    

RISK_CONFIG = RiskConfig()


# =============================================================================
# 배당주 전략 설정
# =============================================================================
@dataclass
class DividendStrategyConfig:
    """배당주 전략 파라미터"""
    # 필터링 조건
    min_yield_kor: float = 3.0              # 한국 최소 배당수익률 3%
    min_yield_usa: float = 3.0              # 미국 최소 배당수익률 3%
    min_payout_ratio: float = 40.0          # 최소 배당성향 40%
    max_payout_ratio: float = 80.0          # 최대 배당성향 80%
    min_continuous_dividend_kor: int = 3    # 한국 최소 연속배당 년수
    min_continuous_dividend_usa: int = 5    # 미국 최소 연속배당 년수
    
    # 기술적 조건
    bb_tolerance: float = 0.10              # BB 하단 근접 허용치
    obv_rising_steps: int = 5               # OBV 상승 확인 기간 (3→5)
    rsi_upper_bound: float = 30.0           # RSI 과매도 상한
    min_data_rows: int = 100                # 최소 데이터 행 수
    
    # 매도 조건 (연간 리밸런싱)
    rebalance_frequency: str = "annual"     # 리밸런싱 주기
    sell_on_dividend_cut: bool = True       # 배당 삭감 시 매도
    

DIVIDEND_CONFIG = DividendStrategyConfig()


# =============================================================================
# 성장주 전략 설정
# =============================================================================
@dataclass
class GrowthStrategyConfig:
    """성장주 전략 파라미터"""
    # 필터링 조건 (한국)
    min_rev_cagr_kor: float = 15.0
    min_eps_cagr_kor: float = 10.0
    min_roe_kor: float = 10.0
    max_debt_to_equity_kor: float = 150.0
    min_current_ratio_kor: float = 1.2
    max_peg_kor: float = 1.15
    
    # 필터링 조건 (미국)
    min_rev_cagr_usa: float = 20.0
    min_eps_cagr_usa: float = 15.0
    min_roe_usa: float = 15.0
    max_debt_to_equity_usa: float = 100.0
    min_current_ratio_usa: float = 1.5
    max_peg_usa: float = 1.4
    
    # 기술적 조건 (개선)
    drawdown_min: float = 0.15              # 최소 조정폭 15% (기존 10%)
    drawdown_max: float = 0.35              # 최대 조정폭 35% (기존 20%)
    use_52week_high: bool = True            # 52주 신고가 대비 활용
    rsi_lower: float = 30.0
    rsi_upper: float = 60.0                 # RSI 상한 확대 (50→60)
    min_data_rows: int = 150
    
    # 브레이크아웃 조건
    breakout_volume_mult: float = 1.5       # 거래량 급증 배수
    breakout_lookback: int = 5              # 브레이크아웃 확인 기간
    
    # 섹터 RS (상대강도)
    use_sector_rs: bool = True              # 섹터 RS 필터 사용
    min_sector_rs_rank: float = 0.3         # 상위 30% 섹터
    
    # 매도 조건
    sell_ratio_trend_break: float = 0.5     # 추세 이탈 시 매도 비율


GROWTH_CONFIG = GrowthStrategyConfig()


# =============================================================================
# 박스권 전략 설정
# =============================================================================
@dataclass
class RangeBoundStrategyConfig:
    """박스권 전략 파라미터"""
    # 필터링 조건 (한국)
    min_ebitda_kor: float = 0.0
    min_cash_flow_kor: float = 0.0
    max_debt_to_equity_kor: float = 120.0
    min_revenue_growth_kor: float = 12.0
    min_roe_kor: float = 12.0
    min_oper_margin_kor: float = 10.0
    min_current_ratio_kor: float = 1.3
    max_per_kor: float = 18.0
    min_market_cap_quantile_kor: float = 0.92
    
    # 필터링 조건 (미국)
    min_ebitda_usa: float = 0.0
    min_cash_flow_usa: float = 0.0
    max_debt_to_equity_usa: float = 100.0
    min_revenue_growth_usa: float = 15.0
    min_roe_usa: float = 15.0
    min_oper_margin_usa: float = 12.0
    min_current_ratio_usa: float = 1.4
    max_per_usa: float = 22.0
    min_market_cap_quantile_usa: float = 0.92
    
    # 기술적 조건
    bb_width_min: float = 0.07              # BB 폭 최소 7%
    bb_width_max: float = 0.18              # BB 폭 최대 18%
    sma_slope_max: float = 0.05             # SMA 기울기 최대 5%
    bb_tolerance: float = 0.15              # BB 하단 근접 허용치
    min_data_rows: int = 120
    
    # 박스권 검증 조건 (신규)
    min_range_days: int = 20                # 최소 20거래일 박스권 유지
    fakeout_confirm_days: int = 3           # 가짜 돌파 확인 3일
    
    # 매도 조건
    sell_ratio_upper: float = 0.5           # BB 상단 도달 시 매도 비율
    sell_ratio_breakdown: float = 0.7       # 하단 이탈 시 매도 비율


RANGEBOX_CONFIG = RangeBoundStrategyConfig()


# =============================================================================
# 시장 상황별 매도 비율 조정
# =============================================================================
@dataclass
class MarketConditionConfig:
    """시장 상황에 따른 동적 파라미터"""
    
    # VIX 기반 매도 비율 조정
    vix_thresholds: List[float] = field(default_factory=lambda: [15.0, 20.0, 25.0, 30.0])
    sell_ratio_multipliers: List[float] = field(default_factory=lambda: [0.8, 1.0, 1.2, 1.5])
    
    # 시장 추세 기반 포지션 사이징
    # bull: 상승장, neutral: 횡보장, bear: 하락장
    position_size_multipliers: Dict[str, float] = field(default_factory=lambda: {
        "bull": 1.2,
        "neutral": 1.0,
        "bear": 0.6,
    })
    
    def get_sell_ratio_multiplier(self, vix: float) -> float:
        """VIX에 따른 매도 비율 배수 반환"""
        for i, threshold in enumerate(self.vix_thresholds):
            if vix < threshold:
                return self.sell_ratio_multipliers[i] if i < len(self.sell_ratio_multipliers) else 1.0
        return self.sell_ratio_multipliers[-1] if self.sell_ratio_multipliers else 1.5
    
    def get_position_multiplier(self, market_trend: str) -> float:
        """시장 추세에 따른 포지션 사이즈 배수 반환"""
        return self.position_size_multipliers.get(market_trend, 1.0)


MARKET_CONDITION_CONFIG = MarketConditionConfig()


# =============================================================================
# 포지션 사이징 설정
# =============================================================================
@dataclass
class PositionSizingConfig:
    """동적 포지션 사이징 설정"""
    base_risk_pct: float = 0.0051           # 기본 리스크 비율
    risk_atr_mult: float = 12.0             # ATR 배수
    adtv_limit_ratio: float = 0.015         # ADTV 제한 비율
    
    # 변동성 기반 조정
    volatility_thresholds: List[float] = field(default_factory=lambda: [0.02, 0.03, 0.05])
    volatility_multipliers: List[float] = field(default_factory=lambda: [1.2, 1.0, 0.7, 0.5])
    
    def get_volatility_multiplier(self, atr_ratio: float) -> float:
        """ATR/가격 비율에 따른 포지션 배수"""
        for i, threshold in enumerate(self.volatility_thresholds):
            if atr_ratio < threshold:
                return self.volatility_multipliers[i]
        return self.volatility_multipliers[-1]


POSITION_SIZING_CONFIG = PositionSizingConfig()
