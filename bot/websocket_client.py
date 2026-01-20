"""
바이낸스 선물 WebSocket 클라이언트
실시간 캔들 및 가격 데이터 수신
"""
import json
import logging
import threading
import time
from typing import Callable, Dict, List, Optional
from collections import deque

import websocket

from .config import TradingConfig, TESTNET_WS_URL, MAINNET_WS_URL

logger = logging.getLogger(__name__)


class BinanceWebSocket:
    """바이낸스 선물 WebSocket 클라이언트"""

    def __init__(self, config: TradingConfig):
        self.config = config
        self.base_url = "wss://stream.binancefuture.com" if config.testnet else "wss://fstream.binance.com"
        self.ws: Optional[websocket.WebSocketApp] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # 콜백 함수들
        self.on_kline_close: Optional[Callable] = None  # 캔들 마감 시
        self.on_price_update: Optional[Callable] = None  # 가격 업데이트 시

        # 캔들 데이터 저장 (심볼별)
        self.klines: Dict[str, deque] = {}  # 마감된 캔들
        self.current_candles: Dict[str, dict] = {}  # 현재 진행 중인 캔들
        self.current_prices: Dict[str, float] = {}

        # 재연결 설정
        self.reconnect_delay = 5
        self.max_reconnect_attempts = 10

    def _get_stream_url(self, symbols: List[str], timeframe: str) -> str:
        """스트림 URL 생성"""
        streams = []
        for symbol in symbols:
            symbol_lower = symbol.lower()
            # 캔들 스트림
            streams.append(f"{symbol_lower}@kline_{timeframe}")
            # 실시간 가격 스트림 (mark price)
            streams.append(f"{symbol_lower}@markPrice@1s")

        stream_path = "/".join(streams)
        return f"{self.base_url}/stream?streams={stream_path}"

    def _on_message(self, ws, message):
        """메시지 수신 처리"""
        try:
            data = json.loads(message)

            if "stream" not in data:
                return

            stream = data["stream"]
            payload = data["data"]

            # 캔들 데이터
            if "@kline_" in stream:
                self._handle_kline(payload)

            # 가격 데이터
            elif "@markPrice" in stream:
                self._handle_price(payload)

        except Exception as e:
            logger.error(f"메시지 처리 오류: {e}")

    def _handle_kline(self, data):
        """캔들 데이터 처리"""
        kline = data["k"]
        symbol = kline["s"]
        is_closed = kline["x"]  # 캔들 마감 여부

        candle = {
            "timestamp": kline["t"],
            "open": float(kline["o"]),
            "high": float(kline["h"]),
            "low": float(kline["l"]),
            "close": float(kline["c"]),
            "volume": float(kline["v"]),
            "is_closed": is_closed
        }

        # 현재 가격 업데이트
        self.current_prices[symbol] = candle["close"]

        # 현재 진행 중인 캔들 저장 (실시간 업데이트)
        self.current_candles[symbol] = candle

        # 캔들 마감 시
        if is_closed:
            if symbol not in self.klines:
                self.klines[symbol] = deque(maxlen=500)

            self.klines[symbol].append(candle)
            logger.info(f"📊 {symbol} 캔들 마감: {candle['close']:.2f}")

            # 콜백 호출
            if self.on_kline_close:
                self.on_kline_close(symbol, candle)

    def _handle_price(self, data):
        """가격 데이터 처리"""
        symbol = data["s"]
        price = float(data["p"])
        self.current_prices[symbol] = price

        # 콜백 호출
        if self.on_price_update:
            self.on_price_update(symbol, price)

    def _on_error(self, ws, error):
        """에러 처리"""
        logger.error(f"WebSocket 에러: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        """연결 종료 처리"""
        logger.warning(f"WebSocket 연결 종료: {close_status_code} - {close_msg}")

        # 재연결 시도
        if self.running:
            logger.info(f"{self.reconnect_delay}초 후 재연결 시도...")
            time.sleep(self.reconnect_delay)
            self._connect()

    def _on_open(self, ws):
        """연결 성공"""
        logger.info("✅ WebSocket 연결 성공")

    def _connect(self):
        """WebSocket 연결"""
        url = self._get_stream_url(self.config.symbols, self.config.timeframe)
        logger.info(f"WebSocket 연결 중: {url[:50]}...")

        self.ws = websocket.WebSocketApp(
            url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open
        )

        self.ws.run_forever()

    def start(self):
        """WebSocket 시작 (백그라운드 스레드)"""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._connect, daemon=True)
        self.thread.start()
        logger.info("WebSocket 스레드 시작")

        # 연결 대기
        time.sleep(2)

    def stop(self):
        """WebSocket 종료"""
        self.running = False
        if self.ws:
            self.ws.close()
        logger.info("WebSocket 종료")

    def get_current_price(self, symbol: str) -> Optional[float]:
        """현재 가격 조회"""
        return self.current_prices.get(symbol)

    def get_klines(self, symbol: str) -> List[dict]:
        """저장된 캔들 데이터 조회 (마감된 캔들만)"""
        if symbol in self.klines:
            return list(self.klines[symbol])
        return []

    def get_current_candle(self, symbol: str) -> Optional[dict]:
        """현재 진행 중인 캔들 조회"""
        return self.current_candles.get(symbol)
