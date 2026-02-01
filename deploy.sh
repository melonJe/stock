#!/bin/bash
# Docker Volume 오류 해결 및 재배포 스크립트

set -e  # 오류 발생 시 중단

echo "==> 1. logs 디렉토리 생성"
mkdir -p logs

echo "==> 2. 기존 컨테이너 중지 및 제거"
docker-compose down || true

echo "==> 3. 기존 volume 제거"
docker volume rm stock_stock_logs 2>/dev/null || echo "Volume 없음 (정상)"

echo "==> 4. Docker Compose 재시작"
docker-compose up -d

echo "==> 5. 컨테이너 상태 확인"
docker-compose ps

echo ""
echo "✅ 배포 완료!"
echo "로그 확인: docker-compose logs -f stock"
