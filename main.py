from fastapi import FastAPI, Depends, Request
# from fastapi.staticfiles import StaticFiles
# from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config.logging_config import setup_logging
from scheduler import lifespan
# from routers import dashboard
# from core.security import verify_basic_auth

# 로깅 초기화
setup_logging(enable_file_logging=True, enable_json_logging=False)

# Rate Limiter 설정
limiter = Limiter(key_func=get_remote_address, default_limits=["200/day", "50/hour"])

app = FastAPI(
    title="주식 트레이딩 시스템",
    description="자동 주식 트레이딩 시스템 API 및 대시보드",
    version="1.0.0",
    lifespan=lifespan
)

# Rate Limit 핸들러 등록
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS 설정 (프로덕션에서는 특정 도메인만 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:18000", "http://localhost:8000"],  # 프로덕션: 실제 도메인으로 변경
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# 정적 파일 및 템플릿 마운트
# app.mount("/static", StaticFiles(directory="static"), name="static")

# 라우터 등록
# app.include_router(dashboard.router)


# @app.get("/")
# @limiter.limit("30/minute")
# async def read_root(request: Request, username: str = Depends(verify_basic_auth)):
#     """대시보드 페이지 (인증 필요)"""
#     return FileResponse("templates/dashboard.html")


@app.get("/health")
@limiter.limit("100/minute")
async def health_check(request: Request):
    """헬스체크 엔드포인트 (인증 불필요)"""
    return {"status": "healthy", "service": "stock-trading"}


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
