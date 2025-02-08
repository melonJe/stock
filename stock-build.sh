#!/bin/bash

# 현재 위치 저장
current_dir=$(pwd)

# Branch 확인 (기본값: main)
branch=${1:-main} # 첫 번째 인자를 사용하고, 없으면 기본값으로 'main' 사용

# Branch 입력 확인
echo "Selected branch: $branch"

# stock 폴더 확인
if [ -d "stock" ]; then
    # 이미 폴더가 있으면 git fetch와 git status를 사용하여 업데이트 필요 여부 확인
    echo "Checking for updates..."
    cd "stock" || exit
    git fetch origin "$branch"
    # git status를 사용하여 로컬과 원격의 차이를 확인
    if git diff --quiet "origin/$branch"; then
        echo "Repository is already up to date. No further action required."
        cd "$current_dir" || exit
        exit 0
    else
        echo "Updates found. Pulling changes..."
        git checkout "$branch" || { echo "Git checkout failed"; exit 1; }
        git merge "origin/$branch" || { echo "Git merge failed"; exit 1; }
    fi
else
    # 폴더가 없으면 git clone 실행
    echo "Cloning repository..."
    git clone -b "$branch" git@github.com:melonJe/stock.git "stock" || { echo "Git clone failed"; exit 1; }
    cd "stock" || exit
fi

# Docker 빌드
docker build --tag stock:latest . || { echo "Docker build failed"; exit 1; }

# Docker Compose 파일 복사
cp -f ./docker-compose.stock.yml ../docker-compose.stock.yml || { echo "Copy failed"; exit 1; }

# 원래 위치로 돌아가기
cd "$current_dir" || exit

# docker-compose up -d 실행하고 더 이상 사용되지 않는 이미지 제거
docker-compose -f docker-compose.stock.yml down && docker-compose -f docker-compose.stock.yml up -d && docker image prune -f || { echo "Docker Compose failed"; exit 1; }
