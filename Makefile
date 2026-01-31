# Makefile for stock trading system

.PHONY: help build up down logs restart clean dev prod

help: ## 사용 가능한 명령어 표시
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Docker 이미지 빌드
	docker build -t stock:latest .

up: ## 서비스 시작
	docker-compose up -d

down: ## 서비스 중지
	docker-compose down

logs: ## 로그 확인
	docker-compose logs -f stock

restart: down up ## 서비스 재시작

clean: ## 사용하지 않는 이미지 정리
	docker image prune -af --filter "until=24h"

dev: ## 개발 환경 시작
	ENVIRONMENT=development docker-compose up -d

prod: build up ## 운영 배포 (빌드 + 시작)

health: ## 헬스체크
	@echo "=== Service Status ==="
	@docker-compose ps
	@echo ""
	@echo "=== API Health ==="
	@curl -s http://localhost:18000/ || echo "API not responding"

deploy: ## 전체 배포 프로세스
	./stock-build.sh

status: ## 컨테이너 상태 및 리소스 확인
	@docker-compose ps
	@echo ""
	@docker stats --no-stream stock stock-postgres

tail-app: ## app.log 실시간 확인
	tail -f logs/app.log

tail-error: ## error.log 실시간 확인
	tail -f logs/error.log

tail-trading: ## trading.log 실시간 확인
	tail -f logs/trading.log

shell: ## 컨테이너 쉘 접속
	docker exec -it stock /bin/bash

db-shell: ## PostgreSQL 쉘 접속
	docker exec -it stock-postgres psql -U postgres -d stock_db

backup-logs: ## 로그 백업
	@mkdir -p backups
	tar -czf backups/logs-$$(date +%Y%m%d-%H%M%S).tar.gz logs/

setup: ## 초기 설정 (네트워크, 디렉토리)
	@echo "Setting up environment..."
	@docker network create melon-net 2>/dev/null || echo "Network already exists"
	@mkdir -p logs
	@chmod 755 logs
	@echo "Done!"
