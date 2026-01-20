#!/bin/bash

# 빠른 실행 스크립트
# 사용법: ./run.sh 또는 ./run.sh --symbols BTCUSDT --days 90

cd "$(dirname "$0")"

# venv 확인
if [ ! -d "venv" ]; then
    echo "⚠️  가상환경이 없습니다. setup.sh를 먼저 실행하세요."
    echo "   ./setup.sh"
    exit 1
fi

# 가상환경 활성화 후 실행
source venv/bin/activate
python backtest/run_backtest.py "$@"
