"""
전략 클래스 정의: 옵션 A (보수적) vs 옵션 B (균형)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List
import pandas as pd


@dataclass
class Signal:
    """매매 시그널"""
    side: str  # 'long', 'short', 'none'
    strength: float  # 0.0 ~ 1.0
    entry_price: float
    tp_price: float
    sl_price: float
    reasons: List[str]


class BaseStrategy(ABC):
    """전략 베이스 클래스"""
    
    name: str = "base"
    description: str = ""
    
    @abstractmethod
    def check_long_entry(self, df: pd.DataFrame) -> Optional[Signal]:
        pass
    
    @abstractmethod
    def check_short_entry(self, df: pd.DataFrame) -> Optional[Signal]:
        pass
    
    def check_signal(self, df: pd.DataFrame) -> Optional[Signal]:
        """롱/숏 시그널 체크 후 더 강한 시그널 반환"""
        if len(df) < 50:
            return None
            
        long_signal = self.check_long_entry(df)
        short_signal = self.check_short_entry(df)
        
        if long_signal and short_signal:
            return long_signal if long_signal.strength > short_signal.strength else short_signal
        return long_signal or short_signal


class StrategyOptionA(BaseStrategy):
    """
    옵션 A: 보수적 전략
    모든 조건이 AND로 충족되어야 진입
    - 높은 승률, 낮은 거래 빈도
    """
    
    name = "Option_A_Conservative"
    description = "모든 조건 AND (RSI<35, Stoch크로스, BB터치, 거래량증가)"
    
    # 롱 파라미터
    LONG_RSI_OVERSOLD = 35
    LONG_BB_TOUCH_MULT = 1.01  # BB 하단의 1% 이내
    LONG_VOLUME_MULT = 1.3
    
    # 숏 파라미터
    SHORT_RSI_OVERBOUGHT = 65
    SHORT_BB_TOUCH_MULT = 0.99  # BB 상단의 1% 이내
    
    # TP/SL
    TP_PCT = 0.01  # 1% 익절
    SL_ATR_MULT = 2.5  # ATR의 2.5배 손절 (완화)
    
    def check_long_entry(self, df: pd.DataFrame) -> Optional[Signal]:
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        reasons = []
        
        # 조건 1: RSI 과매도 + 반등
        cond_rsi = last['rsi'] < self.LONG_RSI_OVERSOLD and last['rsi'] > prev['rsi']
        if cond_rsi:
            reasons.append(f"RSI과매도반등({last['rsi']:.1f})")
        
        # 조건 2: 스토캐스틱 골든크로스
        cond_stoch = (last['stoch_k'] > last['stoch_d']) and (prev['stoch_k'] <= prev['stoch_d'])
        if cond_stoch:
            reasons.append(f"Stoch골든크로스(K:{last['stoch_k']:.1f})")
        
        # 조건 3: BB 하단 터치 + 반등
        cond_bb_touch = last['low'] <= last['bb_lower'] * self.LONG_BB_TOUCH_MULT
        cond_bb_bounce = last['close'] > last['bb_lower']
        if cond_bb_touch and cond_bb_bounce:
            reasons.append("BB하단반등")
        
        # 조건 4: 거래량 증가
        cond_volume = last['volume'] > last['volume_ma'] * self.LONG_VOLUME_MULT
        if cond_volume:
            reasons.append(f"거래량증가({last['volume']/last['volume_ma']:.1f}x)")
        
        # 모든 조건 충족 시 진입
        if cond_rsi and cond_stoch and cond_bb_touch and cond_bb_bounce and cond_volume:
            entry_price = last['close']
            tp_price = entry_price * (1 + self.TP_PCT)
            sl_price = entry_price - (last['atr'] * self.SL_ATR_MULT)
            
            return Signal(
                side='long',
                strength=1.0,
                entry_price=entry_price,
                tp_price=tp_price,
                sl_price=sl_price,
                reasons=reasons
            )
        
        return None
    
    def check_short_entry(self, df: pd.DataFrame) -> Optional[Signal]:
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        reasons = []
        
        # 조건 1: RSI 과매수 + 하락
        cond_rsi = last['rsi'] > self.SHORT_RSI_OVERBOUGHT and last['rsi'] < prev['rsi']
        if cond_rsi:
            reasons.append(f"RSI과매수하락({last['rsi']:.1f})")
        
        # 조건 2: 스토캐스틱 데드크로스
        cond_stoch = (last['stoch_k'] < last['stoch_d']) and (prev['stoch_k'] >= prev['stoch_d'])
        if cond_stoch:
            reasons.append(f"Stoch데드크로스(K:{last['stoch_k']:.1f})")
        
        # 조건 3: BB 상단 터치 + 저항
        cond_bb_touch = last['high'] >= last['bb_upper'] * self.SHORT_BB_TOUCH_MULT
        cond_bb_reject = last['close'] < last['bb_upper']
        if cond_bb_touch and cond_bb_reject:
            reasons.append("BB상단저항")
        
        # 조건 4: 거래량 증가
        cond_volume = last['volume'] > last['volume_ma'] * self.LONG_VOLUME_MULT
        if cond_volume:
            reasons.append(f"거래량증가({last['volume']/last['volume_ma']:.1f}x)")
        
        # 모든 조건 충족 시 진입
        if cond_rsi and cond_stoch and cond_bb_touch and cond_bb_reject and cond_volume:
            entry_price = last['close']
            tp_price = entry_price * (1 - self.TP_PCT)
            sl_price = entry_price + (last['atr'] * self.SL_ATR_MULT)
            
            return Signal(
                side='short',
                strength=1.0,
                entry_price=entry_price,
                tp_price=tp_price,
                sl_price=sl_price,
                reasons=reasons
            )
        
        return None


class StrategyOptionB(BaseStrategy):
    """
    옵션 B: 균형 전략
    필수 조건(2개) + 확인 조건(5개 중 2개 이상)
    - 적절한 승률, 적절한 거래 빈도
    """
    
    name = "Option_B_Balanced"
    description = "필수조건2개 + 확인조건2개이상 (RSI<40, BB중간아래 + 추가확인)"
    
    # 롱 파라미터
    LONG_RSI_MAX = 40  # 완화: 35 → 40
    LONG_STOCH_OVERSOLD = 35
    LONG_BB_TOUCH_MULT = 1.02  # 완화: 1.01 → 1.02
    LONG_VOLUME_MULT = 1.2  # 완화: 1.3 → 1.2
    CONFIRM_MIN = 2  # 최소 확인 조건 수
    
    # 숏 파라미터
    SHORT_RSI_MIN = 60  # 완화: 65 → 60
    SHORT_STOCH_OVERBOUGHT = 65
    SHORT_BB_TOUCH_MULT = 0.98  # 완화
    
    # TP/SL
    TP_PCT = 0.01
    SL_ATR_MULT = 1.5
    
    def check_long_entry(self, df: pd.DataFrame) -> Optional[Signal]:
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # ===== 필수 조건 (모두 충족) =====
        required_reasons = []
        
        # 필수 1: RSI가 낮은 영역
        req_rsi = last['rsi'] < self.LONG_RSI_MAX
        if req_rsi:
            required_reasons.append(f"RSI<{self.LONG_RSI_MAX}({last['rsi']:.1f})")
        
        # 필수 2: 가격이 BB 중간선 아래
        req_bb = last['close'] < last['bb_middle']
        if req_bb:
            required_reasons.append("BB중간선아래")
        
        if not (req_rsi and req_bb):
            return None
        
        # ===== 확인 조건 (2개 이상 충족) =====
        confirm_reasons = []
        confirm_count = 0
        
        # 확인 1: RSI 상승 전환
        if last['rsi'] > prev['rsi']:
            confirm_count += 1
            confirm_reasons.append("RSI상승전환")
        
        # 확인 2: 스토캐스틱 골든크로스
        if (last['stoch_k'] > last['stoch_d']) and (prev['stoch_k'] <= prev['stoch_d']):
            confirm_count += 1
            confirm_reasons.append("Stoch골든크로스")
        
        # 확인 3: 스토캐스틱 과매도
        if last['stoch_k'] < self.LONG_STOCH_OVERSOLD:
            confirm_count += 1
            confirm_reasons.append(f"Stoch과매도({last['stoch_k']:.1f})")
        
        # 확인 4: BB 하단 근접
        if last['low'] <= last['bb_lower'] * self.LONG_BB_TOUCH_MULT:
            confirm_count += 1
            confirm_reasons.append("BB하단근접")
        
        # 확인 5: 거래량 증가
        if last['volume'] > last['volume_ma'] * self.LONG_VOLUME_MULT:
            confirm_count += 1
            confirm_reasons.append("거래량증가")
        
        # 확인 조건 2개 이상 충족 시 진입
        if confirm_count >= self.CONFIRM_MIN:
            entry_price = last['close']
            tp_price = entry_price * (1 + self.TP_PCT)
            sl_price = entry_price - (last['atr'] * self.SL_ATR_MULT)
            
            # 강도 계산: 기본 0.5 + 확인조건당 0.1
            strength = min(0.5 + (confirm_count * 0.1), 1.0)
            
            return Signal(
                side='long',
                strength=strength,
                entry_price=entry_price,
                tp_price=tp_price,
                sl_price=sl_price,
                reasons=required_reasons + confirm_reasons
            )
        
        return None
    
    def check_short_entry(self, df: pd.DataFrame) -> Optional[Signal]:
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # ===== 필수 조건 (모두 충족) =====
        required_reasons = []
        
        # 필수 1: RSI가 높은 영역
        req_rsi = last['rsi'] > self.SHORT_RSI_MIN
        if req_rsi:
            required_reasons.append(f"RSI>{self.SHORT_RSI_MIN}({last['rsi']:.1f})")
        
        # 필수 2: 가격이 BB 중간선 위
        req_bb = last['close'] > last['bb_middle']
        if req_bb:
            required_reasons.append("BB중간선위")
        
        if not (req_rsi and req_bb):
            return None
        
        # ===== 확인 조건 (2개 이상 충족) =====
        confirm_reasons = []
        confirm_count = 0
        
        # 확인 1: RSI 하락 전환
        if last['rsi'] < prev['rsi']:
            confirm_count += 1
            confirm_reasons.append("RSI하락전환")
        
        # 확인 2: 스토캐스틱 데드크로스
        if (last['stoch_k'] < last['stoch_d']) and (prev['stoch_k'] >= prev['stoch_d']):
            confirm_count += 1
            confirm_reasons.append("Stoch데드크로스")
        
        # 확인 3: 스토캐스틱 과매수
        if last['stoch_k'] > self.SHORT_STOCH_OVERBOUGHT:
            confirm_count += 1
            confirm_reasons.append(f"Stoch과매수({last['stoch_k']:.1f})")
        
        # 확인 4: BB 상단 근접
        if last['high'] >= last['bb_upper'] * self.SHORT_BB_TOUCH_MULT:
            confirm_count += 1
            confirm_reasons.append("BB상단근접")
        
        # 확인 5: 거래량 증가
        if last['volume'] > last['volume_ma'] * self.LONG_VOLUME_MULT:
            confirm_count += 1
            confirm_reasons.append("거래량증가")
        
        # 확인 조건 2개 이상 충족 시 진입
        if confirm_count >= self.CONFIRM_MIN:
            entry_price = last['close']
            tp_price = entry_price * (1 - self.TP_PCT)
            sl_price = entry_price + (last['atr'] * self.SL_ATR_MULT)
            
            strength = min(0.5 + (confirm_count * 0.1), 1.0)
            
            return Signal(
                side='short',
                strength=strength,
                entry_price=entry_price,
                tp_price=tp_price,
                sl_price=sl_price,
                reasons=required_reasons + confirm_reasons
            )
        
        return None
