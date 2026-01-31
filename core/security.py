"""보안 유틸리티"""
import os
import secrets
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials, APIKeyHeader

from config import setting_env

# HTTP Basic 인증
security_basic = HTTPBasic()

# API Key 헤더 인증
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_basic_auth(credentials: HTTPBasicCredentials = Security(security_basic)) -> str:
    """
    HTTP Basic 인증 검증
    
    :param credentials: 인증 정보
    :return: 사용자명
    :raises HTTPException: 인증 실패 시
    """
    # 환경 변수에서 인증 정보 읽기
    correct_username = os.getenv("DASHBOARD_USERNAME", "admin")
    correct_password = os.getenv("DASHBOARD_PASSWORD", "")
    
    # 비밀번호가 설정되지 않은 경우 경고
    if not correct_password:
        import logging
        logging.warning("대시보드 비밀번호가 설정되지 않았습니다. DASHBOARD_PASSWORD 환경 변수를 설정하세요.")
        # 개발 환경에서는 허용
        if os.getenv("ENVIRONMENT", "production") == "development":
            return correct_username
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="인증 설정이 완료되지 않았습니다."
        )
    
    # Timing attack 방지를 위한 secrets.compare_digest 사용
    is_correct_username = secrets.compare_digest(
        credentials.username.encode("utf8"),
        correct_username.encode("utf8")
    )
    is_correct_password = secrets.compare_digest(
        credentials.password.encode("utf8"),
        correct_password.encode("utf8")
    )
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 정보가 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    return credentials.username


def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """
    API Key 인증 검증
    
    :param api_key: API 키
    :return: API 키
    :raises HTTPException: 인증 실패 시
    """
    correct_api_key = os.getenv("API_KEY", "")
    
    if not correct_api_key:
        import logging
        logging.warning("API 키가 설정되지 않았습니다. API_KEY 환경 변수를 설정하세요.")
        # 개발 환경에서는 허용
        if os.getenv("ENVIRONMENT", "production") == "development":
            return "dev-key"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API 키 설정이 완료되지 않았습니다."
        )
    
    if not api_key or not secrets.compare_digest(api_key, correct_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 API 키입니다.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    return api_key


def sanitize_path(base_dir: Path, requested_path: str) -> Path:
    """
    경로 탐색 공격(Path Traversal) 방지
    
    :param base_dir: 기본 디렉토리
    :param requested_path: 요청된 경로
    :return: 검증된 절대 경로
    :raises HTTPException: 유효하지 않은 경로
    """
    # 절대 경로로 변환
    base_dir = base_dir.resolve()
    full_path = (base_dir / requested_path).resolve()
    
    # base_dir 외부 접근 시도 차단
    try:
        full_path.relative_to(base_dir)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="접근 권한이 없습니다."
        )
    
    # 파일 존재 확인
    if not full_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="파일을 찾을 수 없습니다."
        )
    
    # 디렉토리 접근 차단
    if full_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="디렉토리에는 접근할 수 없습니다."
        )
    
    return full_path


def mask_sensitive_data(data: str, patterns: list = None) -> str:
    """
    민감한 데이터 마스킹
    
    :param data: 원본 데이터
    :param patterns: 마스킹할 패턴 목록
    :return: 마스킹된 데이터
    """
    import re
    
    if patterns is None:
        patterns = [
            r'(appkey["\s:=]+)([A-Za-z0-9]{20,})',
            r'(appsecret["\s:=]+)([A-Za-z0-9]{20,})',
            r'(password["\s:=]+)([^\s,}]+)',
            r'(token["\s:=]+)([A-Za-z0-9\-_\.]{20,})',
            r'([0-9]{8,10})',  # 계좌번호
        ]
    
    masked_data = data
    for pattern in patterns:
        masked_data = re.sub(pattern, r'\1***MASKED***', masked_data, flags=re.IGNORECASE)
    
    return masked_data


def generate_api_key() -> str:
    """
    안전한 API 키 생성
    
    :return: 랜덤 API 키 (32바이트 hex)
    """
    return secrets.token_hex(32)


def validate_input_length(value: str, max_length: int, field_name: str) -> None:
    """
    입력 길이 검증
    
    :param value: 검증할 값
    :param max_length: 최대 길이
    :param field_name: 필드 이름
    :raises HTTPException: 길이 초과 시
    """
    if len(value) > max_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name}의 길이가 최대 {max_length}자를 초과했습니다."
        )
