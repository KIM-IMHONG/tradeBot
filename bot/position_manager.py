"""
포지션 및 리스크 관리
"""
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from .client import BinanceFuturesClient
from .config import TradingConfig
from .strategy import Signal, SignalType

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """포지션 정보"""
    symbol: str
    side: str  # LONG or SHORT
    entry_price: float
    quantity: float
    take_profit: float
    stop_loss: float
    entry_time: datetime = field(default_factory=datetime.now)
    tp_order_id: Optional[str] = None
    sl_order_id: Optional[str] = None


class PositionManager:
    """포지션 관리자"""

    def __init__(self, client: BinanceFuturesClient, config: TradingConfig):
        self.client = client
        self.config = config
        self.positions: Dict[str, Position] = {}

    def get_position_count(self) -> int:
        """현재 포지션 수"""
        return len(self.positions)

    def has_position(self, symbol: str) -> bool:
        """해당 심볼에 포지션이 있는지 확인"""
        return symbol in self.positions

    def calculate_position_size(self, symbol: str, entry_price: float, stop_loss: float) -> float:
        """포지션 크기 계산 (리스크 기반)"""
        # 잔고 조회
        balance = self.client.get_usdt_balance()
        if balance <= 0:
            logger.warning(f"잔고 부족: {balance} USDT")
            return 0

        # 리스크 금액 계산
        risk_amount = balance * self.config.risk_per_trade

        # 손절까지의 거리 (%)
        stop_distance = abs(entry_price - stop_loss) / entry_price

        # 포지션 크기 계산 (레버리지 적용)
        if stop_distance <= 0:
            logger.warning("손절 거리가 0 이하")
            return 0

        # position_value = risk_amount / stop_distance
        # quantity = position_value / entry_price
        # 레버리지 적용: 실제 필요 마진 = position_value / leverage
        position_value = risk_amount / stop_distance
        quantity = position_value / entry_price

        # 수량 반올림
        quantity = self.client.round_quantity(symbol, quantity)

        # 최소 수량 체크
        if quantity <= 0:
            logger.warning(f"계산된 수량이 0 이하: {quantity}")
            return 0

        logger.info(
            f"포지션 크기 계산: 잔고=${balance:.2f}, "
            f"리스크=${risk_amount:.2f}, "
            f"손절거리={stop_distance*100:.2f}%, "
            f"수량={quantity}"
        )

        return quantity

    def open_position(self, symbol: str, signal: Signal) -> Optional[Position]:
        """포지션 진입"""
        # 이미 포지션이 있는지 확인
        if self.has_position(symbol):
            logger.warning(f"{symbol}: 이미 포지션이 있습니다")
            return None

        # 최대 포지션 수 체크
        if self.get_position_count() >= self.config.max_positions:
            logger.warning(f"최대 포지션 수 초과: {self.get_position_count()}/{self.config.max_positions}")
            return None

        # 포지션 크기 계산
        quantity = self.calculate_position_size(symbol, signal.entry_price, signal.stop_loss)
        if quantity <= 0:
            return None

        try:
            # 레버리지 설정
            self.client.set_leverage(symbol, self.config.leverage)
            self.client.set_margin_type(symbol, "ISOLATED")

            # 진입 주문
            order_side = "BUY" if signal.type == SignalType.LONG else "SELL"
            entry_order = self.client.place_market_order(symbol, order_side, quantity)
            logger.info(f"{symbol}: 진입 주문 완료 - {entry_order}")

            # 실제 체결 가격
            # 시장가 주문은 avgPrice가 반환되지 않을 수 있음
            actual_entry = signal.entry_price

            # TP/SL 가격 정밀도 맞춤
            tp_price = self.client.round_price(symbol, signal.take_profit)
            sl_price = self.client.round_price(symbol, signal.stop_loss)

            # TP 주문
            tp_side = "SELL" if signal.type == SignalType.LONG else "BUY"
            tp_order = self.client.place_take_profit(symbol, tp_side, quantity, tp_price)
            logger.info(f"{symbol}: TP 주문 완료 @ {tp_price}")

            # SL 주문
            sl_order = self.client.place_stop_loss(symbol, tp_side, quantity, sl_price)
            logger.info(f"{symbol}: SL 주문 완료 @ {sl_price}")

            # 포지션 기록
            position = Position(
                symbol=symbol,
                side=signal.type.value,
                entry_price=actual_entry,
                quantity=quantity,
                take_profit=tp_price,
                stop_loss=sl_price,
                tp_order_id=str(tp_order.get("orderId", "")),
                sl_order_id=str(sl_order.get("orderId", "")),
            )
            self.positions[symbol] = position

            logger.info(
                f"✅ {symbol} {signal.type.value} 포지션 오픈: "
                f"진입={actual_entry:.2f}, TP={tp_price:.2f}, SL={sl_price:.2f}, "
                f"수량={quantity}, 사유={', '.join(signal.reasons)}"
            )

            return position

        except Exception as e:
            logger.error(f"{symbol}: 포지션 진입 실패 - {e}")
            # 실패 시 모든 주문 취소
            try:
                self.client.cancel_all_orders(symbol)
            except Exception:
                pass
            return None

    def close_position(self, symbol: str, reason: str = "MANUAL") -> bool:
        """포지션 청산"""
        if not self.has_position(symbol):
            logger.warning(f"{symbol}: 청산할 포지션이 없습니다")
            return False

        position = self.positions[symbol]

        try:
            # 모든 미체결 주문 취소
            self.client.cancel_all_orders(symbol)

            # 청산 주문
            close_side = "SELL" if position.side == "LONG" else "BUY"
            self.client.place_market_order(symbol, close_side, position.quantity, reduce_only=True)

            logger.info(f"✅ {symbol} 포지션 청산 완료 - 사유: {reason}")

            # 포지션 기록 삭제
            del self.positions[symbol]
            return True

        except Exception as e:
            logger.error(f"{symbol}: 포지션 청산 실패 - {e}")
            return False

    def sync_positions(self) -> None:
        """거래소 포지션과 동기화"""
        try:
            exchange_positions = self.client.get_positions()

            # 거래소에 없는 포지션 제거
            symbols_to_remove = []
            for symbol in self.positions:
                found = False
                for ep in exchange_positions:
                    if ep["symbol"] == symbol:
                        found = True
                        break
                if not found:
                    symbols_to_remove.append(symbol)

            for symbol in symbols_to_remove:
                logger.info(f"{symbol}: 거래소에 포지션 없음, 기록 삭제")
                del self.positions[symbol]

            # 거래소 포지션 정보로 업데이트
            for ep in exchange_positions:
                symbol = ep["symbol"]
                if symbol in self.positions:
                    # 기존 포지션 업데이트
                    self.positions[symbol].entry_price = ep["entry_price"]
                    self.positions[symbol].quantity = ep["size"]

        except Exception as e:
            logger.error(f"포지션 동기화 실패: {e}")

    def get_status(self) -> Dict:
        """현재 포지션 상태"""
        return {
            "position_count": self.get_position_count(),
            "max_positions": self.config.max_positions,
            "positions": {
                symbol: {
                    "side": pos.side,
                    "entry_price": pos.entry_price,
                    "quantity": pos.quantity,
                    "take_profit": pos.take_profit,
                    "stop_loss": pos.stop_loss,
                    "entry_time": pos.entry_time.isoformat(),
                }
                for symbol, pos in self.positions.items()
            }
        }
