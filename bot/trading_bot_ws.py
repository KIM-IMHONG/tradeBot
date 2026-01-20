"""
WebSocket 기반 트레이딩봇
실시간 데이터로 더 빠른 대응
"""
import logging
import signal
import sys
import time
from datetime import datetime
from typing import Optional

import pandas as pd

from .client import BinanceFuturesClient
from .config import TradingConfig
from .strategy import OptionAStrategy, SignalType
from .position_manager import PositionManager
from .websocket_client import BinanceWebSocket

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("trading_bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


class WebSocketTradingBot:
    """WebSocket 기반 트레이딩봇"""

    def __init__(self, config: TradingConfig):
        self.config = config
        self.running = False

        # 클라이언트 초기화
        self.client = BinanceFuturesClient(config)
        self.ws_client = BinanceWebSocket(config)

        # 전략 초기화
        self.strategy = OptionAStrategy(config)

        # 포지션 관리자 초기화
        self.position_manager = PositionManager(self.client, config)

        # WebSocket 콜백 설정
        self.ws_client.on_kline_close = self._on_kline_close
        self.ws_client.on_price_update = self._on_price_update

        # 초기 데이터 로드 여부
        self.initial_data_loaded = False

        # 실시간 시그널 체크 설정
        self.realtime_check_interval = 10  # 10초마다 시그널 체크
        self.last_signal_check: dict = {}  # {symbol: timestamp}
        self.signal_cooldown = 300  # 같은 심볼 진입 후 5분 쿨다운
        self.last_entry_time: dict = {}  # {symbol: timestamp}

        # 시그널 핸들러
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """종료 시그널 핸들러"""
        logger.info("종료 시그널 수신...")
        self.stop()

    def print_banner(self):
        """시작 배너"""
        print("\n" + "=" * 60)
        print("  🚀 바이낸스 선물 트레이딩봇 (WebSocket)")
        print("=" * 60)
        print(f"  모드: {'테스트넷' if self.config.testnet else '🔴 실거래'}")
        print(f"  심볼: {', '.join(self.config.symbols)}")
        print(f"  타임프레임: {self.config.timeframe}")
        print(f"  레버리지: {self.config.leverage}x")
        print(f"  익절: {self.config.tp_pct * 100}%")
        print(f"  손절: ATR × {self.config.sl_atr_mult}")
        print("=" * 60)
        print("  ⚡ 실시간 WebSocket 연결")
        print(f"  ⏱️  시그널 체크: {self.realtime_check_interval}초 간격")
        print(f"  🔄 진입 쿨다운: {self.signal_cooldown}초")
        print("=" * 60 + "\n")

    def _load_initial_data(self):
        """초기 캔들 데이터 로드 (지표 계산용)"""
        logger.info("📥 초기 데이터 로드 중...")

        for symbol in self.config.symbols:
            try:
                df = self.client.get_klines(symbol, self.config.timeframe, limit=300)
                # deque에 저장
                for _, row in df.iterrows():
                    candle = {
                        "timestamp": int(row["timestamp"].timestamp() * 1000),
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                        "is_closed": True
                    }
                    if symbol not in self.ws_client.klines:
                        from collections import deque
                        self.ws_client.klines[symbol] = deque(maxlen=500)
                    self.ws_client.klines[symbol].append(candle)

                logger.info(f"  ✅ {symbol}: {len(self.ws_client.klines[symbol])}개 캔들 로드")
            except Exception as e:
                logger.error(f"  ❌ {symbol} 데이터 로드 실패: {e}")

        self.initial_data_loaded = True

    def _klines_to_dataframe(self, symbol: str) -> Optional[pd.DataFrame]:
        """캔들 데이터를 DataFrame으로 변환"""
        klines = self.ws_client.get_klines(symbol)
        if len(klines) < 200:
            return None

        df = pd.DataFrame(klines)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df

    def _on_kline_close(self, symbol: str, candle: dict):
        """캔들 마감 시 호출 (시그널 체크)"""
        if not self.initial_data_loaded:
            return

        logger.info(f"🕯️ {symbol} 캔들 마감 - 시그널 체크...")

        # 이미 포지션이 있으면 스킵
        if self.position_manager.has_position(symbol):
            logger.info(f"  ↳ {symbol}: 이미 포지션 보유 중")
            return

        # 최대 포지션 수 체크
        if self.position_manager.get_position_count() >= self.config.max_positions:
            logger.info(f"  ↳ 최대 포지션 수 도달")
            return

        # DataFrame 변환
        df = self._klines_to_dataframe(symbol)
        if df is None:
            logger.warning(f"  ↳ {symbol}: 데이터 부족")
            return

        # 시그널 체크
        signal_result = self.strategy.check_signal(df)

        if signal_result:
            logger.info(
                f"🎯 {symbol}: {signal_result.type.value} 시그널! "
                f"사유: {', '.join(signal_result.reasons)}"
            )

            # 포지션 진입
            position = self.position_manager.open_position(symbol, signal_result)
            if position:
                logger.info(f"✅ {symbol} {signal_result.type.value} 포지션 오픈 완료")
        else:
            logger.info(f"  ↳ {symbol}: 시그널 없음")

    def _on_price_update(self, symbol: str, price: float):
        """가격 업데이트 시 호출 - 실시간 시그널 체크"""
        if not self.initial_data_loaded:
            return

        # 이미 포지션이 있으면 스킵
        if self.position_manager.has_position(symbol):
            return

        # 최대 포지션 수 체크
        if self.position_manager.get_position_count() >= self.config.max_positions:
            return

        # 쿨다운 체크 (최근 진입 후 일정 시간 대기)
        current_time = time.time()
        if symbol in self.last_entry_time:
            if current_time - self.last_entry_time[symbol] < self.signal_cooldown:
                return

        # 시그널 체크 간격 확인 (과도한 계산 방지)
        if symbol in self.last_signal_check:
            if current_time - self.last_signal_check[symbol] < self.realtime_check_interval:
                return

        self.last_signal_check[symbol] = current_time

        # 실시간 시그널 체크
        self._check_realtime_signal(symbol)

    def _check_realtime_signal(self, symbol: str):
        """실시간 시그널 체크 (현재 캔들 포함)"""
        # 마감된 캔들 데이터
        klines = self.ws_client.get_klines(symbol)
        if len(klines) < 200:
            return

        # 현재 진행 중인 캔들
        current_candle = self.ws_client.get_current_candle(symbol)
        if not current_candle:
            return

        # DataFrame 변환 (마감된 캔들만)
        df = pd.DataFrame(klines)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        # 실시간 시그널 체크
        signal_result = self.strategy.check_signal_realtime(df, current_candle)

        if signal_result:
            logger.info(
                f"⚡ {symbol}: 실시간 {signal_result.type.value} 시그널! "
                f"사유: {', '.join(signal_result.reasons)}"
            )

            # 포지션 진입
            position = self.position_manager.open_position(symbol, signal_result)
            if position:
                logger.info(f"✅ {symbol} {signal_result.type.value} 포지션 오픈 완료 (실시간)")
                self.last_entry_time[symbol] = time.time()  # 쿨다운 시작

    def check_connection(self) -> bool:
        """API 연결 확인"""
        try:
            balance = self.client.get_usdt_balance()
            logger.info(f"✅ API 연결 성공 - USDT 잔고: ${balance:.2f}")
            return True
        except Exception as e:
            logger.error(f"❌ API 연결 실패: {e}")
            return False

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
                current_price = self.ws_client.get_current_price(symbol) or 0
                print(f"    - {symbol}: {pos['side']} @ {pos['entry_price']:.2f}")
                print(f"      현재가: {current_price:.2f} | TP: {pos['take_profit']:.2f} | SL: {pos['stop_loss']:.2f}")

            # 실시간 가격
            print(f"  실시간 가격:")
            for symbol in self.config.symbols:
                price = self.ws_client.get_current_price(symbol)
                if price:
                    print(f"    - {symbol}: ${price:,.2f}")

            print("-" * 50)

        except Exception as e:
            logger.error(f"상태 출력 오류: {e}")

    def run(self):
        """봇 실행"""
        self.print_banner()

        # API 연결 확인
        if not self.check_connection():
            logger.error("API 연결 실패, 종료합니다.")
            sys.exit(1)

        # 초기 데이터 로드
        self._load_initial_data()

        # 포지션 동기화
        self.position_manager.sync_positions()

        # WebSocket 시작
        logger.info("🔌 WebSocket 연결 시작...")
        self.ws_client.start()

        self.running = True
        logger.info("✅ 봇 시작! 실시간 모니터링 중...")

        status_interval = 60  # 상태 출력 간격 (초)
        last_status_time = time.time()

        try:
            while self.running:
                # 주기적 상태 출력
                if time.time() - last_status_time >= status_interval:
                    self.print_status()
                    self.position_manager.sync_positions()
                    last_status_time = time.time()

                time.sleep(1)

        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        """봇 종료"""
        logger.info("봇 종료 중...")
        self.running = False
        self.ws_client.stop()
        logger.info("✅ 봇 종료 완료")


def main():
    """메인 함수"""
    import argparse
    import os
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description="WebSocket 트레이딩봇")
    parser.add_argument("--live", action="store_true", help="실거래 모드")
    parser.add_argument("--symbols", type=str, default=None, help="거래 심볼")

    args = parser.parse_args()

    load_dotenv()

    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")

    if not api_key or not api_secret:
        print("❌ API 키를 설정하세요 (.env 파일)")
        sys.exit(1)

    # 심볼 설정: 명령줄 인자 > .env > 기본값
    if args.symbols:
        symbols = args.symbols.split(",")
    else:
        symbols_env = os.getenv("TRADING_SYMBOLS", "")
        symbols = symbols_env.split(",") if symbols_env else None

    config = TradingConfig(
        api_key=api_key,
        api_secret=api_secret,
        testnet=not args.live,
        symbols=symbols,
    )

    if args.live:
        print("\n" + "!" * 60)
        print("  ⚠️  경고: 실거래 모드입니다!")
        print("!" * 60)
        confirm = input("계속하려면 'YES' 입력: ")
        if confirm != "YES":
            print("취소됨")
            sys.exit(0)

    bot = WebSocketTradingBot(config)
    bot.run()


if __name__ == "__main__":
    main()
