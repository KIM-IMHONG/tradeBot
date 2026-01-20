#!/bin/bash

# WebSocket 기반 트레이딩봇 실행
# 사용법: ./run_bot_ws.sh [옵션]

cd "$(dirname "$0")"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║     🚀 바이낸스 선물 트레이딩봇 (WebSocket)                  ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# venv 확인
if [ ! -d "venv" ]; then
    echo -e "${RED}⚠️  가상환경이 없습니다. setup.sh를 먼저 실행하세요.${NC}"
    exit 1
fi

# .env 확인
if [ ! -f ".env" ]; then
    echo -e "${RED}⚠️  .env 파일이 없습니다.${NC}"
    exit 1
fi

# websocket-client 설치 확인
source venv/bin/activate
pip show websocket-client > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "📦 websocket-client 설치 중..."
    pip install websocket-client==1.7.0 -q
fi

# 실행 (모듈로 실행)
python -m bot.trading_bot_ws "$@"
