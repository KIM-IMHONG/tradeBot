#!/bin/bash

# 백테스트 환경 설정 스크립트
# 사용법: chmod +x setup.sh && ./setup.sh

echo "=========================================="
echo "  바이낸스 선물 백테스트 환경 설정"
echo "=========================================="

# Python 버전 확인
python3 --version

# 기존 venv 삭제 (있으면)
if [ -d "venv" ]; then
    echo "기존 venv 삭제 중..."
    rm -rf venv
fi

# 가상환경 생성
echo "가상환경 생성 중..."
python3 -m venv venv

# 가상환경 활성화
echo "가상환경 활성화..."
source venv/bin/activate

# pip 업그레이드
echo "pip 업그레이드 중..."
pip install --upgrade pip

# 패키지 설치
echo "패키지 설치 중..."
pip install -r requirements.txt

echo ""
echo "=========================================="
echo "  설정 완료!"
echo "=========================================="
echo ""
echo "사용 방법:"
echo "  1. source venv/bin/activate"
echo "  2. python run_backtest.py"
echo ""
