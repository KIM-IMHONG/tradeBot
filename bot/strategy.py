"""
Option A 전략 - 보수적 전략
모든 조건 AND (RSI<35, Stoch크로스, BB터치, 거래량증가)
"""
import pandas as pd
import pandas_ta as ta
from dataclasses import dataclass
from typing import Optional, Tuple
from enum import Enum

from .config import TradingConfig


class SignalType(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


@dataclass
class Signal:
    type: SignalType
    entry_price: float
    take_profit: float
    stop_loss: float
    reasons: list
    atr: float


class OptionAStrategy:
    """Option A 보수적 전략"""

    def __init__(self, config: TradingConfig):
        self.config = config

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """기술적 지표 추가"""
        df = df.copy()

        # RSI
        df["rsi"] = ta.rsi(df["close"], length=self.config.rsi_period)

        # Stochastic
        stoch = ta.stoch(
            df["high"], df["low"], df["close"],
            k=self.config.stoch_k,
            d=self.config.stoch_d,
            smooth_k=self.config.stoch_smooth
        )
        stoch_cols = stoch.columns.tolist()
        k_col = [c for c in stoch_cols if "STOCHk" in c][0]
        d_col = [c for c in stoch_cols if "STOCHd" in c][0]
        df["stoch_k"] = stoch[k_col]
        df["stoch_d"] = stoch[d_col]

        # Bollinger Bands
        bb = ta.bbands(df["close"], length=self.config.bb_period, std=self.config.bb_std)
        bb_cols = bb.columns.tolist()
        upper_col = [c for c in bb_cols if "BBU" in c][0]
        middle_col = [c for c in bb_cols if "BBM" in c][0]
        lower_col = [c for c in bb_cols if "BBL" in c][0]
        df["bb_upper"] = bb[upper_col]
        df["bb_middle"] = bb[middle_col]
        df["bb_lower"] = bb[lower_col]

        # ATR
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=self.config.atr_period)

        # Volume MA
        df["volume_ma"] = ta.sma(df["volume"], length=self.config.volume_ma_period)

        # EMA
        df["ema_fast"] = ta.ema(df["close"], length=self.config.ema_fast)
        df["ema_slow"] = ta.ema(df["close"], length=self.config.ema_slow)

        return df

    def check_long_entry(self, df: pd.DataFrame) -> Optional[Signal]:
        """롱 진입 조건 체크"""
        if len(df) < 2:
            return None

        last = df.iloc[-1]
        prev = df.iloc[-2]
        reasons = []

        # 조건 1: RSI 과매도 + 반등
        cond_rsi = last["rsi"] < self.config.long_rsi_oversold and last["rsi"] > prev["rsi"]
        if cond_rsi:
            reasons.append(f"RSI과매도반등({last['rsi']:.1f})")

        # 조건 2: 스토캐스틱 골든크로스
        cond_stoch = (last["stoch_k"] > last["stoch_d"]) and (prev["stoch_k"] <= prev["stoch_d"])
        if cond_stoch:
            reasons.append(f"Stoch골든크로스(K:{last['stoch_k']:.1f})")

        # 조건 3: BB 하단 터치 + 반등
        cond_bb_touch = last["low"] <= last["bb_lower"] * self.config.long_bb_touch_mult
        cond_bb_bounce = last["close"] > last["bb_lower"]
        if cond_bb_touch and cond_bb_bounce:
            reasons.append("BB하단반등")

        # 조건 4: 거래량 증가
        cond_volume = last["volume"] > last["volume_ma"] * self.config.long_volume_mult
        if cond_volume:
            reasons.append(f"거래량증가({last['volume']/last['volume_ma']:.1f}x)")

        # 모든 조건 충족 시 진입
        if cond_rsi and cond_stoch and (cond_bb_touch and cond_bb_bounce) and cond_volume:
            entry_price = last["close"]
            atr = last["atr"]

            # TP/SL 계산
            take_profit = entry_price * (1 + self.config.tp_pct)
            stop_loss = entry_price - (atr * self.config.sl_atr_mult)

            return Signal(
                type=SignalType.LONG,
                entry_price=entry_price,
                take_profit=take_profit,
                stop_loss=stop_loss,
                reasons=reasons,
                atr=atr
            )

        return None

    def check_short_entry(self, df: pd.DataFrame) -> Optional[Signal]:
        """숏 진입 조건 체크"""
        if len(df) < 2:
            return None

        last = df.iloc[-1]
        prev = df.iloc[-2]
        reasons = []

        # 조건 1: RSI 과매수 + 하락
        cond_rsi = last["rsi"] > self.config.short_rsi_overbought and last["rsi"] < prev["rsi"]
        if cond_rsi:
            reasons.append(f"RSI과매수하락({last['rsi']:.1f})")

        # 조건 2: 스토캐스틱 데드크로스
        cond_stoch = (last["stoch_k"] < last["stoch_d"]) and (prev["stoch_k"] >= prev["stoch_d"])
        if cond_stoch:
            reasons.append(f"Stoch데드크로스(K:{last['stoch_k']:.1f})")

        # 조건 3: BB 상단 터치 + 하락
        cond_bb_touch = last["high"] >= last["bb_upper"] * self.config.short_bb_touch_mult
        cond_bb_bounce = last["close"] < last["bb_upper"]
        if cond_bb_touch and cond_bb_bounce:
            reasons.append("BB상단반락")

        # 조건 4: 거래량 증가
        cond_volume = last["volume"] > last["volume_ma"] * self.config.long_volume_mult
        if cond_volume:
            reasons.append(f"거래량증가({last['volume']/last['volume_ma']:.1f}x)")

        # 모든 조건 충족 시 진입
        if cond_rsi and cond_stoch and (cond_bb_touch and cond_bb_bounce) and cond_volume:
            entry_price = last["close"]
            atr = last["atr"]

            # TP/SL 계산
            take_profit = entry_price * (1 - self.config.tp_pct)
            stop_loss = entry_price + (atr * self.config.sl_atr_mult)

            return Signal(
                type=SignalType.SHORT,
                entry_price=entry_price,
                take_profit=take_profit,
                stop_loss=stop_loss,
                reasons=reasons,
                atr=atr
            )

        return None

    def check_signal(self, df: pd.DataFrame) -> Optional[Signal]:
        """시그널 체크 (롱/숏)"""
        df = self.add_indicators(df)

        # NaN 제거
        df = df.dropna()
        if len(df) < 2:
            return None

        # 롱 체크
        long_signal = self.check_long_entry(df)
        if long_signal:
            return long_signal

        # 숏 체크
        short_signal = self.check_short_entry(df)
        if short_signal:
            return short_signal

        return None

    def check_signal_realtime(self, df: pd.DataFrame, current_candle: dict) -> Optional[Signal]:
        """
        실시간 시그널 체크 (현재 진행 중인 캔들 포함)
        - df: 마감된 캔들 데이터
        - current_candle: 현재 진행 중인 캔들 {open, high, low, close, volume, timestamp}
        """
        if len(df) < 200:
            return None

        # 현재 캔들을 DataFrame에 추가
        df = df.copy()
        current_row = pd.DataFrame([{
            "timestamp": pd.to_datetime(current_candle["timestamp"], unit="ms"),
            "open": current_candle["open"],
            "high": current_candle["high"],
            "low": current_candle["low"],
            "close": current_candle["close"],
            "volume": current_candle["volume"],
        }])
        df = pd.concat([df, current_row], ignore_index=True)

        return self.check_signal(df)

    def get_market_context(self, df: pd.DataFrame) -> dict:
        """시장 상황 분석"""
        df = self.add_indicators(df)
        df = df.dropna()

        if len(df) < 1:
            return {}

        last = df.iloc[-1]

        return {
            "price": last["close"],
            "rsi": last["rsi"],
            "stoch_k": last["stoch_k"],
            "stoch_d": last["stoch_d"],
            "bb_upper": last["bb_upper"],
            "bb_middle": last["bb_middle"],
            "bb_lower": last["bb_lower"],
            "atr": last["atr"],
            "volume_ratio": last["volume"] / last["volume_ma"] if last["volume_ma"] > 0 else 0,
            "trend": "UP" if last["ema_fast"] > last["ema_slow"] else "DOWN",
        }
