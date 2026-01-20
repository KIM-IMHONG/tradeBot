#!/usr/bin/env python3
"""
TP/SL 조합 테스트
"""
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List
from dataclasses import dataclass

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import TradingConfig
from bot.strategy import OptionAStrategy, SignalType


def download_data(symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    """데이터 다운로드"""
    end_time = int(datetime.now().timestamp() * 1000)
    start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

    all_data = []
    current_start = start_time

    while current_start < end_time:
        url = "https://fapi.binance.com/fapi/v1/klines"
        params = {
            "symbol": symbol,
            "interval": timeframe,
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

    return df[["timestamp", "open", "high", "low", "close", "volume"]]


def simulate(df: pd.DataFrame, config: TradingConfig, initial_balance: float = 10000) -> Dict:
    """시뮬레이션 실행"""
    strategy = OptionAStrategy(config)
    df = strategy.add_indicators(df)
    df = df.dropna().reset_index(drop=True)

    balance = initial_balance
    position = None
    trades = []
    equity_curve = [initial_balance]
    lookback = 300

    for i in range(lookback, len(df)):
        candle = df.iloc[i]

        # 포지션 청산 체크
        if position:
            exit_reason = None
            exit_price = None

            if position["side"] == "LONG":
                if candle["high"] >= position["tp"]:
                    exit_reason = "TP"
                    exit_price = position["tp"]
                elif candle["low"] <= position["sl"]:
                    exit_reason = "SL"
                    exit_price = position["sl"]
            else:
                if candle["low"] <= position["tp"]:
                    exit_reason = "TP"
                    exit_price = position["tp"]
                elif candle["high"] >= position["sl"]:
                    exit_reason = "SL"
                    exit_price = position["sl"]

            if exit_reason:
                if position["side"] == "LONG":
                    pnl_pct = (exit_price - position["entry"]) / position["entry"]
                else:
                    pnl_pct = (position["entry"] - exit_price) / position["entry"]

                pnl_pct *= config.leverage
                pnl = balance * config.risk_per_trade * (pnl_pct / 0.02)
                pnl -= position["entry"] * 0.0008  # 수수료

                balance += pnl
                trades.append({
                    "pnl": pnl,
                    "pnl_pct": pnl_pct * 100,
                    "reason": exit_reason
                })
                position = None

        # 신규 진입
        if not position:
            window_df = df.iloc[i-lookback+1:i+1].copy()
            signal = strategy.check_signal(window_df)

            if signal:
                position = {
                    "side": signal.type.value,
                    "entry": signal.entry_price,
                    "tp": signal.take_profit,
                    "sl": signal.stop_loss
                }

        equity_curve.append(balance)

    # 미청산 포지션 정리
    if position:
        trades.append({"pnl": 0, "pnl_pct": 0, "reason": "END"})

    # 최대 낙폭 계산
    peak = initial_balance
    max_dd = 0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # 결과 계산
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]

    return {
        "total_return": (balance - initial_balance) / initial_balance * 100,
        "total_trades": len(trades),
        "win_rate": len(wins) / len(trades) * 100 if trades else 0,
        "avg_win": sum(t["pnl"] for t in wins) / len(wins) if wins else 0,
        "avg_loss": sum(t["pnl"] for t in losses) / len(losses) if losses else 0,
        "max_drawdown": max_dd,
        "profit_factor": abs(sum(t["pnl"] for t in wins) / sum(t["pnl"] for t in losses)) if losses and sum(t["pnl"] for t in losses) != 0 else 0,
        "final_balance": balance
    }


def main():
    print("\n" + "=" * 80)
    print("  📊 TP/SL 조합 테스트")
    print("=" * 80)

    # 데이터 다운로드
    print("\n📥 BTCUSDT 데이터 다운로드 중...")
    df = download_data("BTCUSDT", "15m", 180)
    print(f"   ✅ {len(df)}개 캔들")

    # 테스트할 조합
    combinations = [
        # (익절%, 손절 ATR배수)
        (0.01, 2.5),  # 원본
        (0.02, 2.0),  # 익절 2%, 손절 2.0
        (0.02, 2.5),  # 익절 2%, 손절 2.5
        (0.03, 2.0),  # 익절 3%, 손절 2.0
        (0.03, 2.5),  # 익절 3%, 손절 2.5
        (0.03, 3.0),  # 익절 3%, 손절 3.0
        (0.04, 2.5),  # 익절 4%, 손절 2.5
        (0.04, 3.0),  # 익절 4%, 손절 3.0
        (0.05, 2.5),  # 익절 5%, 손절 2.5
        (0.05, 3.0),  # 익절 5%, 손절 3.0
    ]

    results = []

    print("\n🔄 테스트 중...\n")

    for tp_pct, sl_mult in combinations:
        config = TradingConfig()
        config.tp_pct = tp_pct
        config.sl_atr_mult = sl_mult

        result = simulate(df, config)
        result["tp_pct"] = tp_pct * 100
        result["sl_mult"] = sl_mult
        results.append(result)

        print(f"   TP {tp_pct*100:.0f}% / SL ATR×{sl_mult} → "
              f"수익률: {result['total_return']:+.1f}%, "
              f"승률: {result['win_rate']:.1f}%, "
              f"MDD: {result['max_drawdown']:.1f}%, "
              f"PF: {result['profit_factor']:.2f}")

    # 결과 정렬 (수익률 기준)
    results.sort(key=lambda x: x["total_return"], reverse=True)

    print("\n" + "=" * 80)
    print("  🏆 결과 순위 (수익률 기준)")
    print("=" * 80)
    print(f"\n{'순위':<4} {'TP%':<6} {'SL배수':<8} {'수익률':<10} {'승률':<8} {'MDD':<8} {'PF':<6} {'거래수':<6}")
    print("-" * 70)

    for i, r in enumerate(results, 1):
        print(f"{i:<4} {r['tp_pct']:.0f}%{'':<4} ATR×{r['sl_mult']:<4} "
              f"{r['total_return']:+.1f}%{'':<4} {r['win_rate']:.1f}%{'':<3} "
              f"{r['max_drawdown']:.1f}%{'':<3} {r['profit_factor']:.2f}{'':<3} {r['total_trades']}")

    # 최고 수익률 vs 최저 MDD
    print("\n" + "-" * 70)
    best_return = results[0]
    best_mdd = min(results, key=lambda x: x["max_drawdown"])

    print(f"\n📈 최고 수익률: TP {best_return['tp_pct']:.0f}% / SL ATR×{best_return['sl_mult']} "
          f"→ {best_return['total_return']:+.1f}%")
    print(f"📉 최저 낙폭:   TP {best_mdd['tp_pct']:.0f}% / SL ATR×{best_mdd['sl_mult']} "
          f"→ MDD {best_mdd['max_drawdown']:.1f}% (수익률 {best_mdd['total_return']:+.1f}%)")

    # 균형 잡힌 설정 (수익률/MDD 비율)
    for r in results:
        r["risk_reward"] = r["total_return"] / r["max_drawdown"] if r["max_drawdown"] > 0 else 0

    best_balanced = max(results, key=lambda x: x["risk_reward"])
    print(f"⚖️  최적 균형:   TP {best_balanced['tp_pct']:.0f}% / SL ATR×{best_balanced['sl_mult']} "
          f"→ 수익률 {best_balanced['total_return']:+.1f}%, MDD {best_balanced['max_drawdown']:.1f}%")


if __name__ == "__main__":
    main()
