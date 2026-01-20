"""
트레이딩봇 설정
"""
import os
from dataclasses import dataclass
from typing import List


@dataclass
class TradingConfig:
    """트레이딩 설정"""
    # API 설정
    api_key: str = ""
    api_secret: str = ""
    testnet: bool = True  # True: 테스트넷, False: 실거래

    # 거래 설정
    symbols: List[str] = None
    timeframe: str = "15m"
    leverage: int = 20  # 레버리지 20배

    # 자금 관리
    risk_per_trade: float = 0.02  # 거래당 리스크 2%
    max_positions: int = 3  # 최대 동시 포지션 수

    # Option A 전략 파라미터
    # 롱 진입 조건
    long_rsi_oversold: float = 35
    long_bb_touch_mult: float = 1.01  # BB 하단의 1% 이내
    long_volume_mult: float = 1.3

    # 숏 진입 조건
    short_rsi_overbought: float = 65
    short_bb_touch_mult: float = 0.99  # BB 상단의 1% 이내

    # TP/SL 설정 (기본값)
    tp_pct: float = 0.01  # 1.0% 익절 (레버리지 20x = 20%)
    sl_atr_mult: float = 1.5  # ATR의 1.5배 손절

    # 심볼별 설정 (롱 전용 + 커스텀 TP)
    # BTC: 롱만, TP 0.3% (단기 반등만 먹기)
    # ETH: 롱+숏, TP 1.0%
    symbol_settings: dict = None

    # 지표 설정
    rsi_period: int = 14
    stoch_k: int = 14
    stoch_d: int = 3
    stoch_smooth: int = 3
    bb_period: int = 20
    bb_std: float = 2.0
    atr_period: int = 14
    volume_ma_period: int = 20
    ema_fast: int = 50
    ema_slow: int = 200

    # 실행 설정
    check_interval: int = 60  # 시그널 체크 간격 (초)

    def __post_init__(self):
        if self.symbols is None:
            self.symbols = ["BTCUSDT"]

        # 심볼별 설정 초기화
        if self.symbol_settings is None:
            self.symbol_settings = {
                "BTCUSDT": {
                    "long_only": True,    # 롱만 진입
                    "tp_pct": 0.003,      # TP 0.3% (레버리지 20x = 6%)
                },
                # 다른 심볼은 기본 설정 사용 (롱+숏, TP 1.0%)
            }

    def get_symbol_setting(self, symbol: str, key: str, default=None):
        """심볼별 설정 조회"""
        if symbol in self.symbol_settings:
            return self.symbol_settings[symbol].get(key, default)
        return default

    @classmethod
    def from_env(cls) -> "TradingConfig":
        """환경변수에서 설정 로드"""
        return cls(
            api_key=os.getenv("BINANCE_API_KEY", ""),
            api_secret=os.getenv("BINANCE_API_SECRET", ""),
            testnet=os.getenv("BINANCE_TESTNET", "true").lower() == "true",
            symbols=os.getenv("TRADING_SYMBOLS", "BTCUSDT").split(","),
            leverage=int(os.getenv("LEVERAGE", "5")),
            risk_per_trade=float(os.getenv("RISK_PER_TRADE", "0.02")),
        )


# 테스트넷 URL
TESTNET_BASE_URL = "https://testnet.binancefuture.com"
TESTNET_WS_URL = "wss://stream.binancefuture.com"

# 실거래 URL
MAINNET_BASE_URL = "https://fapi.binance.com"
MAINNET_WS_URL = "wss://fstream.binance.com"
