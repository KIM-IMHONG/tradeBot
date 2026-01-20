#!/usr/bin/env python3
"""
트레이딩봇 실행 스크립트
"""
import argparse
import os
import sys
from dotenv import load_dotenv

# 상위 디렉토리 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import TradingConfig
from bot.trading_bot import TradingBot


def main():
    parser = argparse.ArgumentParser(description="바이낸스 선물 트레이딩봇")
    parser.add_argument("--testnet", action="store_true", default=True,
                        help="테스트넷 사용 (기본값)")
    parser.add_argument("--live", action="store_true",
                        help="실거래 모드 (주의!)")
    parser.add_argument("--symbols", type=str, default="BTCUSDT,ETHUSDT,SOLUSDT",
                        help="거래 심볼 (쉼표 구분)")
    parser.add_argument("--leverage", type=int, default=5,
                        help="레버리지 (기본값: 5)")
    parser.add_argument("--risk", type=float, default=0.02,
                        help="거래당 리스크 비율 (기본값: 0.02)")
    parser.add_argument("--interval", type=int, default=60,
                        help="체크 간격 (초, 기본값: 60)")
    parser.add_argument("--once", action="store_true",
                        help="한 번만 실행 (테스트용)")

    args = parser.parse_args()

    # 환경변수 로드
    load_dotenv()

    # API 키 확인
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")

    if not api_key or not api_secret:
        print("❌ 오류: BINANCE_API_KEY, BINANCE_API_SECRET 환경변수를 설정하세요.")
        print("\n.env 파일 예시:")
        print("  BINANCE_API_KEY=your_api_key_here")
        print("  BINANCE_API_SECRET=your_api_secret_here")
        sys.exit(1)

    # 설정 생성
    config = TradingConfig(
        api_key=api_key,
        api_secret=api_secret,
        testnet=not args.live,
        symbols=args.symbols.split(","),
        leverage=args.leverage,
        risk_per_trade=args.risk,
        check_interval=args.interval,
    )

    # 실거래 모드 경고
    if args.live:
        print("\n" + "!" * 60)
        print("  ⚠️  경고: 실거래 모드입니다!")
        print("  실제 자금이 사용됩니다. 계속하시겠습니까?")
        print("!" * 60)
        confirm = input("\n계속하려면 'YES'를 입력하세요: ")
        if confirm != "YES":
            print("취소되었습니다.")
            sys.exit(0)

    # 봇 실행
    bot = TradingBot(config)

    if args.once:
        bot.run_once()
    else:
        bot.run()


if __name__ == "__main__":
    main()
