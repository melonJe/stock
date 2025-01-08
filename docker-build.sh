#!/bin/bash

# 현재 위치 저장
current_dir=$(pwd)

# stock 폴더 확인
if [ -d "stock" ]; then
    # 이미 폴더가 있으면 git fetch와 git status를 사용하여 업데이트 필요 여부 확인
    echo "Checking for updates..."
    cd "stock" || exit
    git fetch origin main
    # git status를 사용하여 로컬과 원격의 차이를 확인
    if git diff --quiet origin/main; then
        echo "Repository is already up to date. No further action required."
        cd "$current_dir" || exit
        exit 0
    else
        echo "Updates found. Pulling changes..."
        git merge origin/main || { echo "Git merge failed"; exit 1; }
    fi
else
    # 폴더가 없으면 git clone 실행
    echo "Cloning repository..."
    git clone -b main git@github.com:melonJe/stockasdfasdf.git "stock" || { echo "Git clone failed"; exit 1; }
    cd "stock" || exit
fi

docker buildx build --tag stockasdfasdf:latest . || { echo "Docker build failed"; exit 1; }
cp -f ./docker-compose.stockasdfasdf.yml ../docker-compose.stockasdfasdf.yml || { echo "Copy failed"; exit 1; }

# 원래 위치로 돌아가기
cd "$current_dir" || exit

# docker-compose up -d 실행하고 더 이상 사용되지 않는 이미지 제거
docker-compose -f docker-compose.stockasdfasdf.yml down && docker-compose -f docker-compose.stockasdfasdf.yml up -d && docker image prune -f || { echo "Docker Compose up failed"; exit 1; }
