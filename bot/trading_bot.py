"""
트레이딩봇 메인 로직
"""
import logging
import time
import signal
import sys
from datetime import datetime
from typing import Optional

from .client import BinanceFuturesClient
from .config import TradingConfig
from .strategy import OptionAStrategy, SignalType
from .position_manager import PositionManager

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("trading_bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


class TradingBot:
    """바이낸스 선물 트레이딩봇"""

    def __init__(self, config: TradingConfig):
        self.config = config
        self.running = False

        # 클라이언트 초기화
        self.client = BinanceFuturesClient(config)

        # 전략 초기화
        self.strategy = OptionAStrategy(config)

        # 포지션 관리자 초기화
        self.position_manager = PositionManager(self.client, config)

        # 시그널 핸들러 등록
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """종료 시그널 핸들러"""
        logger.info("종료 시그널 수신, 봇을 종료합니다...")
        self.running = False

    def print_banner(self):
        """시작 배너 출력"""
        print("\n" + "=" * 60)
        print("  바이낸스 선물 트레이딩봇 - Option A (보수적 전략)")
        print("=" * 60)
        print(f"  모드: {'테스트넷' if self.config.testnet else '🔴 실거래'}")
        print(f"  심볼: {', '.join(self.config.symbols)}")
        print(f"  타임프레임: {self.config.timeframe}")
        print(f"  레버리지: {self.config.leverage}x")
        print(f"  거래당 리스크: {self.config.risk_per_trade * 100}%")
        print(f"  최대 포지션: {self.config.max_positions}개")
        print(f"  익절: {self.config.tp_pct * 100}%")
        print(f"  손절: ATR x {self.config.sl_atr_mult}")
        print("=" * 60 + "\n")

    def check_connection(self) -> bool:
        """API 연결 확인"""
        try:
            balance = self.client.get_usdt_balance()
            logger.info(f"API 연결 성공 - USDT 잔고: ${balance:.2f}")
            return True
        except Exception as e:
            logger.error(f"API 연결 실패: {e}")
            return False

    def process_symbol(self, symbol: str) -> Optional[str]:
        """심볼 처리"""
        try:
            # 이미 포지션이 있으면 스킵
            if self.position_manager.has_position(symbol):
                return None

            # 캔들 데이터 가져오기
            df = self.client.get_klines(symbol, self.config.timeframe, limit=300)
            if len(df) < 200:
                logger.warning(f"{symbol}: 데이터 부족 ({len(df)}개)")
                return None

            # 시그널 체크
            signal_result = self.strategy.check_signal(df)

            if signal_result:
                logger.info(
                    f"📊 {symbol}: {signal_result.type.value} 시그널 감지! "
                    f"사유: {', '.join(signal_result.reasons)}"
                )

                # 포지션 진입
                position = self.position_manager.open_position(symbol, signal_result)
                if position:
                    return f"{symbol}: {signal_result.type.value} 포지션 오픈"

            return None

        except Exception as e:
            logger.error(f"{symbol}: 처리 중 오류 - {e}")
            return None

    def print_status(self):
        """현재 상태 출력"""
        try:
            balance = self.client.get_usdt_balance()
            status = self.position_manager.get_status()

            print("\n" + "-" * 50)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 상태")
            print(f"  잔고: ${balance:.2f}")
            print(f"  포지션: {status['position_count']}/{status['max_positions']}")

            for symbol, pos in status["positions"].items():
                print(f"    - {symbol}: {pos['side']} @ {pos['entry_price']:.2f}")
                print(f"      TP: {pos['take_profit']:.2f}, SL: {pos['stop_loss']:.2f}")

            print("-" * 50)

        except Exception as e:
            logger.error(f"상태 출력 오류: {e}")

    def run(self):
        """봇 실행"""
        self.print_banner()

        # 연결 확인
        if not self.check_connection():
            logger.error("API 연결 실패, 봇을 종료합니다.")
            sys.exit(1)

        self.running = True
        logger.info("봇 시작!")

        iteration = 0
        while self.running:
            try:
                iteration += 1
                logger.info(f"\n=== 반복 #{iteration} ===")

                # 포지션 동기화
                self.position_manager.sync_positions()

                # 각 심볼 처리
                for symbol in self.config.symbols:
                    result = self.process_symbol(symbol)
                    if result:
                        logger.info(f"📈 {result}")

                # 상태 출력 (5회마다)
                if iteration % 5 == 0:
                    self.print_status()

                # 대기
                logger.info(f"다음 체크까지 {self.config.check_interval}초 대기...")
                time.sleep(self.config.check_interval)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"메인 루프 오류: {e}")
                time.sleep(10)

        logger.info("봇 종료됨")

    def run_once(self):
        """한 번만 실행 (테스트용)"""
        self.print_banner()

        if not self.check_connection():
            logger.error("API 연결 실패")
            return

        logger.info("단일 실행 모드")

        # 포지션 동기화
        self.position_manager.sync_positions()

        # 각 심볼 처리
        for symbol in self.config.symbols:
            # 시장 상황 출력
            df = self.client.get_klines(symbol, self.config.timeframe, limit=300)
            context = self.strategy.get_market_context(df)

            print(f"\n{symbol} 시장 상황:")
            print(f"  가격: ${context.get('price', 0):.2f}")
            print(f"  RSI: {context.get('rsi', 0):.1f}")
            print(f"  Stoch K/D: {context.get('stoch_k', 0):.1f}/{context.get('stoch_d', 0):.1f}")
            print(f"  BB: {context.get('bb_lower', 0):.2f} - {context.get('bb_upper', 0):.2f}")
            print(f"  ATR: {context.get('atr', 0):.2f}")
            print(f"  거래량 배율: {context.get('volume_ratio', 0):.2f}x")
            print(f"  추세: {context.get('trend', 'N/A')}")

            # 시그널 체크
            result = self.process_symbol(symbol)
            if result:
                logger.info(f"📈 {result}")

        self.print_status()
