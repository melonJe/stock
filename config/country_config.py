# country_config.py

# 국가별 설정 추가
COUNTRY_CONFIG = {
    "KOR": {
        "symbol_prefix": "NAVER:",
        "default_trading_platform": "KRX",
        # 추가 설정 가능
    },
    "USA": {
        "symbol_prefix": "",  # 미국 주식은 프리픽스 없이 심볼 사용
        "default_trading_platform": "NYSE",
        # 추가 설정 가능
    },
    # 추후 다른 국가 추가 가능
}

COUNTRY_CONFIG_ORDER = {
    "USA": {
        "tr_id_buy": "TTT3014U",
        "tr_id_sell": "TTT3016U",
        "ovrs_excg_cd": "NASD,NYSE,AMEX",
        "prdt_type_cd": None,
        "sll_buy_dvsn_cd_buy": "02",
        "sll_buy_dvsn_cd_sell": "01",
        "ord_dvsn_buy": "00",
        "ord_dvsn_sell": "00",
        "rvse_cncl_dvsn_cd": "00",
        "ovrs_rsvn_odno": None,
        "tr_crcy_cd": "USD"  # 미국달러
    },
    "CHN": {
        "tr_id_buy": "TTTS3013U",
        "tr_id_sell": "TTTS3013U",
        "ovrs_excg_cd": "SHAA",
        "prdt_type_cd": "551",
        "sll_buy_dvsn_cd_buy": "02",
        "sll_buy_dvsn_cd_sell": "01",
        "ord_dvsn_buy": "00",
        "ord_dvsn_sell": "00",
        "rvse_cncl_dvsn_cd": "00",
        "ovrs_rsvn_odno": None,
        "tr_crcy_cd": "CNY"  # 중국위안화
    },
    "HKG": {
        "tr_id_buy": "TTTS3013U",
        "tr_id_sell": "TTTS3013U",
        "ovrs_excg_cd": "SEHK",
        "prdt_type_cd": "501",
        "sll_buy_dvsn_cd_buy": "02",
        "sll_buy_dvsn_cd_sell": "01",
        "ord_dvsn_buy": "00",
        "ord_dvsn_sell": "00",
        "rvse_cncl_dvsn_cd": "00",
        "ovrs_rsvn_odno": None,
        "tr_crcy_cd": "HKD"  # 홍콩달러
    },
    "JPN": {
        "tr_id_buy": "TTTS3013U",
        "tr_id_sell": "TTTS3013U",
        "ovrs_excg_cd": "TKSE",
        "prdt_type_cd": "515",
        "sll_buy_dvsn_cd_buy": "02",
        "sll_buy_dvsn_cd_sell": "01",
        "ord_dvsn_buy": "00",
        "ord_dvsn_sell": "00",
        "rvse_cncl_dvsn_cd": "00",
        "ovrs_rsvn_odno": None,
        "tr_crcy_cd": "JPY"  # 일본엔화
    },
    "VNM": {
        "tr_id_buy": "TTTS3013U",
        "tr_id_sell": "TTTS3013U",
        "ovrs_excg_cd": "HASE",  # 하노이거래소
        "prdt_type_cd": "507",
        "sll_buy_dvsn_cd_buy": "02",
        "sll_buy_dvsn_cd_sell": "01",
        "ord_dvsn_buy": "00",
        "ord_dvsn_sell": "00",
        "rvse_cncl_dvsn_cd": "00",
        "ovrs_rsvn_odno": None,
        "tr_crcy_cd": "VND"  # 베트남동
    },
    # 필요한 다른 국가 추가...
}
