# =============================================================================
# Build Stage - 의존성 설치
# =============================================================================
FROM python:3.10-slim AS builder

WORKDIR /build

# 빌드 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 가상환경 생성
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 의존성 설치 (레이어 캐싱 최적화 - requirements.txt만 먼저 복사)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# =============================================================================
# Runtime Stage - 최소한의 런타임 환경
# =============================================================================
FROM python:3.10-slim AS runtime

# 환경 변수 설정
ENV TZ="Asia/Seoul" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    PATH="/opt/venv/bin:$PATH" \
    APP_HOME=/app

# 런타임 의존성 설치 + 비root 사용자 생성
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# 가상환경 복사
COPY --from=builder /opt/venv /opt/venv

# 작업 디렉토리 설정
WORKDIR $APP_HOME

# 애플리케이션 코드 복사 (소유권 설정)
COPY --chown=appuser:appgroup . .

# 필요한 디렉토리 생성
RUN mkdir -p $APP_HOME/logs $APP_HOME/static/css $APP_HOME/static/js $APP_HOME/templates \
    && chown -R appuser:appgroup $APP_HOME

# 비root 사용자로 전환
USER appuser

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 포트 노출
EXPOSE 8000

# 애플리케이션 실행
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0"]
