#!/bin/bash

# 바이낸스 선물 트레이딩봇 실행 스크립트
# 사용법: ./run_trading_bot.sh [옵션]
#
# 옵션:
#   --live      실거래 모드 (주의!)
#   --once      한 번만 실행 (테스트용)
#   --symbols   거래 심볼 (예: BTCUSDT,ETHUSDT)
#   --leverage  레버리지 (기본값: 5)
#   --risk      거래당 리스크 (기본값: 0.02)
#   --interval  체크 간격 초 (기본값: 60)

cd "$(dirname "$0")"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║     바이낸스 선물 트레이딩봇 - Option A (보수적 전략)         ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# venv 확인
if [ ! -d "venv" ]; then
    echo -e "${RED}⚠️  가상환경이 없습니다. setup.sh를 먼저 실행하세요.${NC}"
    echo "   ./setup.sh"
    exit 1
fi

# .env 파일 확인
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env 파일이 없습니다.${NC}"
    echo ""
    if [ -f ".env.example" ]; then
        echo "1. .env.example 파일을 .env로 복사하세요:"
        echo "   cp .env.example .env"
        echo ""
        echo "2. .env 파일을 열어 API 키를 설정하세요:"
        echo "   BINANCE_API_KEY=your_api_key"
        echo "   BINANCE_API_SECRET=your_api_secret"
    fi
    exit 1
fi

# 가상환경 활성화 후 실행
source venv/bin/activate
python bot/run_bot.py "$@"
