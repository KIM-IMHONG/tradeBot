#!/usr/bin/env python3
"""
봇 시뮬레이션 - 과거 데이터로 실제 봇 로직 테스트
백테스트와 달리 실제 봇의 코드를 그대로 사용하여 검증
"""
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import TradingConfig
from bot.strategy import OptionAStrategy, Signal, SignalType


@dataclass
class SimulatedPosition:
    """시뮬레이션 포지션"""
    symbol: str
    side: str
    entry_price: float
    quantity: float
    take_profit: float
    stop_loss: float
    entry_time: datetime
    entry_index: int


@dataclass
class TradeResult:
    """거래 결과"""
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    entry_time: datetime
    exit_time: datetime
    exit_reason: str


class BotSimulator:
    """봇 시뮬레이터"""

    def __init__(self, config: TradingConfig, initial_balance: float = 10000):
        self.config = config
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.strategy = OptionAStrategy(config)
        self.positions: Dict[str, SimulatedPosition] = {}
        self.trades: List[TradeResult] = []
        self.equity_curve: List[float] = []

    def download_data(self, symbol: str, days: int = 180) -> pd.DataFrame:
        """과거 데이터 다운로드"""
        print(f"  📥 {symbol} 데이터 다운로드 중...")

        interval = self.config.timeframe
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

        all_data = []
        current_start = start_time

        while current_start < end_time:
            url = "https://fapi.binance.com/fapi/v1/klines"
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": current_start,
                "limit": 1500
            }

            response = requests.get(url, params=params)
            data = response.json()

            if not data:
                break

            all_data.extend(data)
            current_start = data[-1][0] + 1

            if len(data) < 1500:
                break

        df = pd.DataFrame(all_data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_volume",
            "taker_buy_quote_volume", "ignore"
        ])

        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        print(f"    ✅ {len(df)}개 캔들 다운로드 완료")

        return df

    def calculate_position_size(self, entry_price: float, stop_loss: float) -> float:
        """포지션 크기 계산 (실제 봇과 동일한 로직)"""
        risk_amount = self.balance * self.config.risk_per_trade
        stop_distance = abs(entry_price - stop_loss) / entry_price

        if stop_distance <= 0:
            return 0

        position_value = risk_amount / stop_distance
        quantity = position_value / entry_price

        return quantity

    def check_position_exit(self, pos: SimulatedPosition, candle: pd.Series) -> Optional[str]:
        """포지션 청산 조건 체크"""
        high = candle["high"]
        low = candle["low"]

        if pos.side == "LONG":
            # TP 도달
            if high >= pos.take_profit:
                return "TP"
            # SL 도달
            if low <= pos.stop_loss:
                return "SL"
        else:  # SHORT
            # TP 도달
            if low <= pos.take_profit:
                return "TP"
            # SL 도달
            if high >= pos.stop_loss:
                return "SL"

        return None

    def close_position(self, symbol: str, exit_price: float, exit_time: datetime, reason: str):
        """포지션 청산"""
        pos = self.positions[symbol]

        # PnL 계산
        if pos.side == "LONG":
            pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
        else:
            pnl_pct = (pos.entry_price - exit_price) / pos.entry_price

        pnl_pct *= self.config.leverage
        pnl = self.balance * self.config.risk_per_trade * (pnl_pct / (self.config.sl_atr_mult * 0.01))

        # 수수료 (0.04% x 2)
        fee = pos.quantity * pos.entry_price * 0.0008
        pnl -= fee

        self.balance += pnl

        # 거래 기록
        trade = TradeResult(
            symbol=symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            quantity=pos.quantity,
            pnl=pnl,
            pnl_pct=pnl_pct * 100,
            entry_time=pos.entry_time,
            exit_time=exit_time,
            exit_reason=reason
        )
        self.trades.append(trade)

        del self.positions[symbol]

    def run_simulation(self, symbol: str, df: pd.DataFrame, realtime_mode: bool = True):
        """시뮬레이션 실행

        realtime_mode=True: 실시간 체크 (캔들 진행 중에도 시그널 체크)
        realtime_mode=False: 캔들 마감 시에만 시그널 체크
        """
        mode_str = "실시간" if realtime_mode else "캔들마감"
        print(f"\n  🚀 {symbol} 시뮬레이션 시작... ({mode_str} 모드)")

        # 지표 추가
        df = self.strategy.add_indicators(df)
        df = df.dropna().reset_index(drop=True)

        lookback = 300  # 봇이 사용하는 캔들 수
        cooldown_candles = 20  # 진입 후 쿨다운 (15분 * 20 = 5시간)
        last_entry_idx = -cooldown_candles

        for i in range(lookback, len(df)):
            current_candle = df.iloc[i]
            current_time = current_candle["timestamp"]

            # 포지션 청산 체크
            if symbol in self.positions:
                pos = self.positions[symbol]
                exit_reason = self.check_position_exit(pos, current_candle)

                if exit_reason:
                    if exit_reason == "TP":
                        exit_price = pos.take_profit
                    else:  # SL
                        exit_price = pos.stop_loss

                    self.close_position(symbol, exit_price, current_time, exit_reason)

            # 신규 진입 체크 (포지션 없을 때만)
            if symbol not in self.positions and len(self.positions) < self.config.max_positions:
                # 쿨다운 체크
                if i - last_entry_idx < cooldown_candles:
                    self.equity_curve.append(self.balance)
                    continue

                # 실시간 모드: 현재 캔들의 고가/저가로 BB 터치 체크
                if realtime_mode:
                    # 마감된 캔들들로 지표 계산
                    window_df = df.iloc[i-lookback+1:i].copy()

                    # 현재 캔들을 '진행 중인 캔들'로 처리
                    current_candle_dict = {
                        "timestamp": int(current_candle["timestamp"].timestamp() * 1000),
                        "open": current_candle["open"],
                        "high": current_candle["high"],
                        "low": current_candle["low"],
                        "close": current_candle["close"],
                        "volume": current_candle["volume"],
                    }
                    signal = self.strategy.check_signal_realtime(window_df, current_candle_dict, symbol)
                else:
                    # 캔들 마감 모드: 기존 방식
                    window_df = df.iloc[i-lookback+1:i+1].copy()
                    signal = self.strategy.check_signal(window_df, symbol)

                if signal:
                    quantity = self.calculate_position_size(signal.entry_price, signal.stop_loss)

                    if quantity > 0:
                        pos = SimulatedPosition(
                            symbol=symbol,
                            side=signal.type.value,
                            entry_price=signal.entry_price,
                            quantity=quantity,
                            take_profit=signal.take_profit,
                            stop_loss=signal.stop_loss,
                            entry_time=current_time,
                            entry_index=i
                        )
                        self.positions[symbol] = pos
                        last_entry_idx = i

            # 자본금 기록
            self.equity_curve.append(self.balance)

        # 미청산 포지션 강제 청산
        if symbol in self.positions:
            last_candle = df.iloc[-1]
            self.close_position(
                symbol,
                last_candle["close"],
                last_candle["timestamp"],
                "END"
            )

    def print_results(self):
        """결과 출력"""
        print("\n" + "=" * 70)
        print("  📊 봇 시뮬레이션 결과")
        print("=" * 70)

        if not self.trades:
            print("  거래 없음")
            return

        # 통계 계산
        total_trades = len(self.trades)
        winning_trades = [t for t in self.trades if t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl <= 0]

        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
        total_pnl = sum(t.pnl for t in self.trades)
        total_return = (self.balance - self.initial_balance) / self.initial_balance * 100

        avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0

        # 최대 낙폭 계산
        peak = self.initial_balance
        max_dd = 0
        for equity in self.equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100
            if dd > max_dd:
                max_dd = dd

        print(f"\n  💰 자본금")
        print(f"     초기: ${self.initial_balance:,.2f}")
        print(f"     최종: ${self.balance:,.2f}")
        print(f"     수익: ${total_pnl:,.2f} ({total_return:+.2f}%)")

        print(f"\n  📈 거래 통계")
        print(f"     총 거래: {total_trades}회")
        print(f"     승리: {len(winning_trades)}회")
        print(f"     패배: {len(losing_trades)}회")
        print(f"     승률: {win_rate:.1f}%")

        print(f"\n  📊 성과 지표")
        print(f"     평균 수익: ${avg_win:,.2f}")
        print(f"     평균 손실: ${avg_loss:,.2f}")
        print(f"     최대 낙폭: {max_dd:.2f}%")

        if avg_loss != 0:
            profit_factor = abs(sum(t.pnl for t in winning_trades) / sum(t.pnl for t in losing_trades))
            print(f"     Profit Factor: {profit_factor:.2f}")

        # 최근 거래 내역
        print(f"\n  📝 최근 거래 (최대 10개)")
        for trade in self.trades[-10:]:
            emoji = "✅" if trade.pnl > 0 else "❌"
            side_emoji = "🟢" if trade.side == "LONG" else "🔴"
            print(f"     {side_emoji} {trade.side} | "
                  f"${trade.entry_price:,.2f} → ${trade.exit_price:,.2f} | "
                  f"{emoji} {trade.pnl_pct:+.2f}% (${trade.pnl:+,.2f}) | {trade.exit_reason}")

        print("\n" + "=" * 70)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="봇 시뮬레이션")
    parser.add_argument("--symbols", type=str, default="BTCUSDT",
                        help="테스트할 심볼 (쉼표 구분)")
    parser.add_argument("--days", type=int, default=180,
                        help="테스트 기간 (일)")
    parser.add_argument("--balance", type=float, default=10000,
                        help="초기 자본금")
    parser.add_argument("--candle-close", action="store_true",
                        help="캔들 마감 시에만 시그널 체크 (기본: 실시간)")

    args = parser.parse_args()

    realtime_mode = not args.candle_close
    mode_str = "실시간" if realtime_mode else "캔들마감"

    print("\n" + "=" * 70)
    print("  🤖 봇 시뮬레이션 - 과거 데이터로 실제 봇 로직 검증")
    print("=" * 70)
    print(f"  심볼: {args.symbols}")
    print(f"  기간: {args.days}일")
    print(f"  초기 자본: ${args.balance:,.2f}")
    print(f"  모드: {mode_str}")
    print("=" * 70)

    # 설정
    config = TradingConfig()

    symbols = args.symbols.split(",")

    for symbol in symbols:
        # 시뮬레이터 생성 (심볼별로 독립)
        simulator = BotSimulator(config, args.balance)

        # 데이터 다운로드
        df = simulator.download_data(symbol.strip(), args.days)

        # 시뮬레이션 실행
        simulator.run_simulation(symbol.strip(), df, realtime_mode)

        # 결과 출력
        simulator.print_results()


if __name__ == "__main__":
    main()
