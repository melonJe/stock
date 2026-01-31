"""관심종목 조회 API"""
import logging
from typing import Optional

from clients.kis.base import KISBaseClient
from data.dto.interest_stock_dto import (
    InterestGroupListRequestDTO,
    InterestGroupListItemDTO,
    InterestGroupListResponseDTO,
    InterestGroupDetailRequestDTO,
    InterestGroupDetailInfoDTO,
    InterestGroupDetailItemDTO,
    InterestGroupDetailResponseDTO,
)


class WatchlistClient(KISBaseClient):
    """관심종목 조회 클라이언트"""

    def get_groups(
            self,
            user_id: str,
            group_type: str = "1",
            fid_etc_cls_code: str = "00",
            custtype: str = "P"
    ) -> Optional[InterestGroupListResponseDTO]:
        """
        관심종목 그룹 목록 조회

        :param user_id: 사용자 ID
        :param group_type: 그룹 타입
        :param fid_etc_cls_code: 기타 분류 코드
        :param custtype: 고객 타입
        :return: 관심종목 그룹 목록 응답 DTO
        """
        headers = self._get_headers_with_tr_id("HHKCM113004C7", use_prefix=False)
        headers["custtype"] = custtype
        params = InterestGroupListRequestDTO(
            TYPE=group_type,
            FID_ETC_CLS_CODE=fid_etc_cls_code,
            USER_ID=user_id
        ).__dict__
        response_data = self._get(
            "/uapi/domestic-stock/v1/quotations/intstock-grouplist",
            params,
            headers,
            error_log_prefix="관심종목 그룹조회 API 요청 실패"
        )

        if response_data:
            try:
                output2 = response_data.get("output2", []) or []
                if isinstance(output2, dict):
                    output2 = [output2]
                items = [InterestGroupListItemDTO(**item) for item in output2]
                return InterestGroupListResponseDTO(output2=items)
            except Exception as e:
                logging.critical(f"관심종목 그룹조회 파싱 오류: {e} - response data: {response_data}")
                return None

        logging.critical("관심종목 그룹조회 API 응답 없음")
        return None

    def get_stocks_by_group(
            self,
            user_id: str,
            inter_grp_code: str,
            group_type: str = "1",
            data_rank: str = "",
            inter_grp_name: str = "",
            hts_kor_isnm: str = "",
            cntg_cls_code: str = "",
            fid_etc_cls_code: str = "4",
            custtype: str = "P"
    ) -> Optional[InterestGroupDetailResponseDTO]:
        """
        관심종목 그룹별 종목 조회

        :param user_id: 사용자 ID
        :param inter_grp_code: 관심종목 그룹 코드
        :param group_type: 그룹 타입
        :param data_rank: 데이터 순위
        :param inter_grp_name: 그룹 이름
        :param hts_kor_isnm: HTS 한글 종목명
        :param cntg_cls_code: 체결 분류 코드
        :param fid_etc_cls_code: 기타 분류 코드
        :param custtype: 고객 타입
        :return: 관심종목 상세 응답 DTO
        """
        headers = self._get_headers_with_tr_id("HHKCM113004C6", use_prefix=False)
        headers["custtype"] = custtype
        params = InterestGroupDetailRequestDTO(
            TYPE=group_type,
            USER_ID=user_id,
            DATA_RANK=data_rank,
            INTER_GRP_CODE=inter_grp_code,
            INTER_GRP_NAME=inter_grp_name,
            HTS_KOR_ISNM=hts_kor_isnm,
            CNTG_CLS_CODE=cntg_cls_code,
            FID_ETC_CLS_CODE=fid_etc_cls_code
        ).__dict__
        response_data = self._get(
            "/uapi/domestic-stock/v1/quotations/intstock-stocklist-by-group",
            params,
            headers,
            error_log_prefix="관심종목 그룹별 종목조회 API 요청 실패"
        )

        if response_data:
            try:
                output1 = response_data.get("output1")
                info = InterestGroupDetailInfoDTO(**output1) if output1 else None
                output2 = response_data.get("output2", []) or []
                if isinstance(output2, dict):
                    output2 = [output2]
                items = [InterestGroupDetailItemDTO(**item) for item in output2]
                return InterestGroupDetailResponseDTO(output1=info, output2=items)
            except Exception as e:
                logging.critical(f"관심종목 그룹별 종목조회 파싱 오류: {e} - response data: {response_data}")
                return None

        logging.critical("관심종목 상세조회 API 응답 없음")
        return None
