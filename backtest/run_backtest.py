#!/usr/bin/env python3
"""
바이낸스 선물 백테스트 실행 스크립트
옵션 A (보수적) vs 옵션 B (균형) 전략 비교

사용법:
    python run_backtest.py
    python run_backtest.py --symbols BTCUSDT,ETHUSDT --days 180
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
import time

import requests
import pandas as pd
import pandas_ta as ta
import numpy as np
import matplotlib.pyplot as plt
from tabulate import tabulate

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from backtest.strategies import StrategyOptionA, StrategyOptionB
from backtest.engine import BacktestEngine


def download_klines(symbol: str, interval: str, start_date: str, end_date: str) -> pd.DataFrame:
    """바이낸스에서 캔들 데이터 다운로드 (API 키 불필요)"""
    
    print(f"  📥 {symbol} 데이터 다운로드 중...")
    
    base_url = "https://api.binance.com/api/v3/klines"
    
    start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
    end_ts = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000)
    
    all_klines = []
    current_start = start_ts
    
    while current_start < end_ts:
        params = {
            'symbol': symbol,
            'interval': interval,
            'startTime': current_start,
            'endTime': end_ts,
            'limit': 1000
        }
        
        try:
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            klines = response.json()
        except Exception as e:
            print(f"    ⚠️  API 에러: {e}")
            break
        
        if not klines:
            break
        
        all_klines.extend(klines)
        current_start = klines[-1][0] + 1
        
        # 진행 상황 표시
        progress = (current_start - start_ts) / (end_ts - start_ts) * 100
        print(f"    진행: {len(all_klines):,}개 캔들 ({progress:.0f}%)", end='\r')
        
        # 레이트 리밋 방지
        time.sleep(0.1)
    
    print(f"    ✅ 완료: {len(all_klines):,}개 캔들                    ")
    
    if not all_klines:
        return pd.DataFrame()
    
    # DataFrame 변환
    df = pd.DataFrame(all_klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])
    
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    
    return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """기술적 지표 추가"""
    
    print("  📊 지표 계산 중...")
    
    # RSI
    df['rsi'] = ta.rsi(df['close'], length=14)
    
    # Stochastic
    stoch = ta.stoch(df['high'], df['low'], df['close'], k=14, d=3, smooth_k=3)
    df['stoch_k'] = stoch['STOCHk_14_3_3']
    df['stoch_d'] = stoch['STOCHd_14_3_3']
    
    # Bollinger Bands
    bb = ta.bbands(df['close'], length=20, std=2)
    # pandas_ta 버전에 따라 컬럼명이 다를 수 있음
    bb_cols = bb.columns.tolist()
    upper_col = [c for c in bb_cols if 'BBU' in c][0]
    middle_col = [c for c in bb_cols if 'BBM' in c][0]
    lower_col = [c for c in bb_cols if 'BBL' in c][0]
    df['bb_upper'] = bb[upper_col]
    df['bb_middle'] = bb[middle_col]
    df['bb_lower'] = bb[lower_col]
    
    # ATR
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    # Volume MA
    df['volume_ma'] = ta.sma(df['volume'], length=20)
    
    # EMA
    df['ema_50'] = ta.ema(df['close'], length=50)
    df['ema_200'] = ta.ema(df['close'], length=200)
    
    print("    ✅ 지표 계산 완료")
    
    return df


def print_detailed_results(results: list):
    """상세 결과 출력"""
    
    print("\n")
    print("=" * 80)
    print("                         📊 상세 백테스트 결과")
    print("=" * 80)
    
    for result in results:
        print(f"\n{'─' * 80}")
        print(f"📌 전략: {result.strategy_name}")
        print(f"   설명: {result.strategy_description}")
        print(f"{'─' * 80}")
        
        print(f"\n  📈 거래 통계")
        print(f"     • 총 거래 수: {result.total_trades}회")
        print(f"     • 롱 거래: {result.long_trades}회 (승률: {result.long_win_rate:.1%})")
        print(f"     • 숏 거래: {result.short_trades}회 (승률: {result.short_win_rate:.1%})")
        print(f"     • 승리: {result.winning_trades}회 / 패배: {result.losing_trades}회")
        
        print(f"\n  💰 수익 분석")
        print(f"     • 총 수익률: {result.total_return_pct:+.2%}")
        print(f"     • 총 수익금: ${result.total_return:+,.2f}")
        print(f"     • 최대 낙폭: {result.max_drawdown_pct:.2%}")
        
        print(f"\n  📊 성과 지표")
        print(f"     • 전체 승률: {result.win_rate:.1%}")
        print(f"     • Profit Factor: {result.profit_factor:.2f}")
        print(f"     • Sharpe Ratio: {result.sharpe_ratio:.2f}")
        
        print(f"\n  💵 거래별 분석")
        print(f"     • 평균 수익 거래: ${result.avg_win:+.2f} ({result.avg_win_pct:+.2%})")
        print(f"     • 평균 손실 거래: ${result.avg_loss:.2f} ({result.avg_loss_pct:.2%})")
        print(f"     • 평균 거래: ${result.avg_trade:+.2f}")
        print(f"     • 총 수수료: ${result.total_commission:.2f}")
        
        # 최근 거래 내역 (최대 10개)
        if result.trades:
            print(f"\n  📝 최근 거래 내역 (최대 10개)")
            recent_trades = result.trades[-10:]
            for i, trade in enumerate(recent_trades, 1):
                side_emoji = "🟢" if trade.side == 'long' else "🔴"
                result_emoji = "✅" if trade.pnl > 0 else "❌"
                print(f"     {i}. {side_emoji} {trade.side.upper()} | "
                      f"진입: ${trade.entry_price:,.2f} → 청산: ${trade.exit_price:,.2f} | "
                      f"{result_emoji} {trade.pnl_pct:+.2%} (${trade.pnl:+.2f}) | "
                      f"사유: {trade.exit_reason.upper()}")


def plot_comparison(results: list, symbol: str, save_path: str = None):
    """비교 차트 생성"""
    
    print("\n  📈 차트 생성 중...")
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f'Strategy Comparison - {symbol}', fontsize=14, fontweight='bold')
    
    colors = ['#2ecc71', '#3498db']  # 녹색(A), 파랑(B)
    
    # 1. 자산 곡선
    ax1 = axes[0, 0]
    for i, result in enumerate(results):
        if result.equity_curve is not None:
            ax1.plot(result.equity_curve.index, result.equity_curve.values, 
                    label=result.strategy_name, color=colors[i], linewidth=1.5)
    ax1.axhline(y=10000, color='gray', linestyle='--', alpha=0.5, label='Initial')
    ax1.set_title('Equity Curve')
    ax1.set_xlabel('Date')
    ax1.set_ylabel('Equity ($)')
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    
    # 2. 거래 분포
    ax2 = axes[0, 1]
    x = np.arange(len(results))
    width = 0.35
    
    long_trades = [r.long_trades for r in results]
    short_trades = [r.short_trades for r in results]
    
    bars1 = ax2.bar(x - width/2, long_trades, width, label='Long', color='#27ae60', alpha=0.8)
    bars2 = ax2.bar(x + width/2, short_trades, width, label='Short', color='#e74c3c', alpha=0.8)
    
    ax2.set_title('Trade Distribution')
    ax2.set_ylabel('Number of Trades')
    ax2.set_xticks(x)
    ax2.set_xticklabels([r.strategy_name.replace('_', '\n') for r in results])
    ax2.legend()
    
    # 막대 위에 숫자 표시
    for bar, val in zip(bars1, long_trades):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, 
                str(val), ha='center', va='bottom', fontsize=10)
    for bar, val in zip(bars2, short_trades):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, 
                str(val), ha='center', va='bottom', fontsize=10)
    
    # 3. 승률 비교
    ax3 = axes[1, 0]
    win_rates = [r.win_rate * 100 for r in results]
    long_wr = [r.long_win_rate * 100 for r in results]
    short_wr = [r.short_win_rate * 100 for r in results]
    
    x = np.arange(len(results))
    width = 0.25
    
    ax3.bar(x - width, win_rates, width, label='Total', color='#9b59b6', alpha=0.8)
    ax3.bar(x, long_wr, width, label='Long', color='#27ae60', alpha=0.8)
    ax3.bar(x + width, short_wr, width, label='Short', color='#e74c3c', alpha=0.8)
    
    ax3.axhline(y=50, color='gray', linestyle='--', alpha=0.7, label='Break-even')
    ax3.set_title('Win Rate Comparison')
    ax3.set_ylabel('Win Rate (%)')
    ax3.set_xticks(x)
    ax3.set_xticklabels([r.strategy_name.replace('_', '\n') for r in results])
    ax3.set_ylim(0, 100)
    ax3.legend(loc='upper right')
    
    # 4. 수익률 & 낙폭
    ax4 = axes[1, 1]
    returns = [r.total_return_pct * 100 for r in results]
    drawdowns = [-r.max_drawdown_pct * 100 for r in results]
    
    x = np.arange(len(results))
    width = 0.35
    
    colors_return = ['#27ae60' if r >= 0 else '#e74c3c' for r in returns]
    ax4.bar(x - width/2, returns, width, label='Return', color=colors_return, alpha=0.8)
    ax4.bar(x + width/2, drawdowns, width, label='Max Drawdown', color='#e74c3c', alpha=0.4)
    
    ax4.axhline(y=0, color='gray', linestyle='-', alpha=0.5)
    ax4.set_title('Return vs Max Drawdown')
    ax4.set_ylabel('Percentage (%)')
    ax4.set_xticks(x)
    ax4.set_xticklabels([r.strategy_name.replace('_', '\n') for r in results])
    ax4.legend()
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"    ✅ 차트 저장: {save_path}")
    
    plt.show()


def save_trades_to_csv(results: list, output_dir: str):
    """거래 내역 CSV 저장"""
    
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    for result in results:
        if result.trades:
            trades_data = []
            for t in result.trades:
                trades_data.append({
                    'Symbol': t.symbol,
                    'Side': t.side,
                    'Entry_Time': t.entry_time,
                    'Entry_Price': t.entry_price,
                    'Exit_Time': t.exit_time,
                    'Exit_Price': t.exit_price,
                    'Quantity': t.quantity,
                    'TP_Price': t.tp_price,
                    'SL_Price': t.sl_price,
                    'PnL': t.pnl,
                    'PnL_Pct': t.pnl_pct,
                    'Exit_Reason': t.exit_reason,
                    'Commission': t.commission,
                    'Reasons': ', '.join(t.reasons)
                })
            
            df = pd.DataFrame(trades_data)
            filename = output_path / f"trades_{result.strategy_name}_{result.symbol}.csv"
            df.to_csv(filename, index=False)
            print(f"  💾 거래내역 저장: {filename}")


def main():
    parser = argparse.ArgumentParser(
        description='바이낸스 선물 백테스트 - 옵션 A vs B 비교',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python run_backtest.py
  python run_backtest.py --symbols BTCUSDT,ETHUSDT,SOLUSDT
  python run_backtest.py --symbols BTCUSDT --days 365 --leverage 10
        """
    )
    
    parser.add_argument('--symbols', default='BTCUSDT,ETHUSDT,SOLUSDT',
                       help='심볼 목록 (콤마 구분, 기본: BTCUSDT,ETHUSDT,SOLUSDT)')
    parser.add_argument('--interval', default='15m',
                       help='타임프레임 (기본: 15m)')
    parser.add_argument('--days', type=int, default=180,
                       help='백테스트 기간 일수 (기본: 180일)')
    parser.add_argument('--balance', type=float, default=10000,
                       help='초기 자본 (기본: $10,000)')
    parser.add_argument('--leverage', type=int, default=5,
                       help='레버리지 (기본: 5배)')
    parser.add_argument('--risk', type=float, default=0.02,
                       help='거래당 리스크 비율 (기본: 0.02 = 2%%)')
    parser.add_argument('--no-chart', action='store_true',
                       help='차트 생성 안함')
    parser.add_argument('--save-trades', action='store_true',
                       help='거래 내역 CSV 저장')
    
    args = parser.parse_args()
    
    symbols = [s.strip().upper() for s in args.symbols.split(',')]
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    
    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + "  바이낸스 선물 백테스트: 옵션 A vs 옵션 B 비교  ".center(78) + "║")
    print("╠" + "═" * 78 + "╣")
    print(f"║  📌 심볼: {', '.join(symbols):<66} ║")
    print(f"║  📅 기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')} ({args.days}일){' ' * (66 - len(start_date.strftime('%Y-%m-%d')) - len(end_date.strftime('%Y-%m-%d')) - len(str(args.days)) - 10)}║")
    print(f"║  ⏱️  타임프레임: {args.interval:<61} ║")
    print(f"║  💰 초기 자본: ${args.balance:,.0f}{' ' * (62 - len(f'{args.balance:,.0f}'))}║")
    print(f"║  📊 레버리지: {args.leverage}x{' ' * (64 - len(str(args.leverage)))}║")
    print(f"║  ⚠️  거래당 리스크: {args.risk:.0%}{' ' * (59 - len(f'{args.risk:.0%}'))}║")
    print("╚" + "═" * 78 + "╝")
    print()
    
    # 전략 초기화
    strategies = [
        StrategyOptionA(),
        StrategyOptionB()
    ]
    
    print("📋 전략 설명:")
    print(f"   • Option A (보수적): {strategies[0].description}")
    print(f"   • Option B (균형): {strategies[1].description}")
    print()
    
    # 백테스트 엔진 초기화
    engine = BacktestEngine(
        initial_balance=args.balance,
        leverage=args.leverage,
        risk_per_trade=args.risk,
        commission_rate=0.0004  # 0.04%
    )
    
    all_results = []
    
    for symbol in symbols:
        print(f"\n{'━' * 80}")
        print(f"🔍 {symbol} 백테스트 시작")
        print(f"{'━' * 80}")
        
        # 데이터 다운로드
        df = download_klines(
            symbol=symbol,
            interval=args.interval,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d')
        )
        
        if df.empty:
            print(f"  ⚠️  {symbol} 데이터 없음, 스킵")
            continue
        
        # 지표 계산
        df = add_indicators(df)
        
        # NaN 제거
        df = df.dropna()
        print(f"  📊 분석 가능 캔들: {len(df):,}개")
        
        # 백테스트 실행
        print("  🚀 백테스트 실행 중...")
        comparison, results = engine.compare_strategies(strategies, df, symbol)
        
        print(f"\n  📊 {symbol} 결과 요약:")
        print(tabulate(comparison, headers='keys', tablefmt='pretty', showindex=False))
        
        all_results.extend(results)
        
        # 상세 결과 출력
        print_detailed_results(results)
        
        # 차트 생성
        if not args.no_chart:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            results_dir = os.path.join(script_dir, 'results')
            os.makedirs(results_dir, exist_ok=True)
            chart_path = os.path.join(results_dir, f"backtest_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            plot_comparison(results, symbol, chart_path)

        # 거래 내역 저장
        if args.save_trades:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            results_dir = os.path.join(script_dir, 'results')
            save_trades_to_csv(results, results_dir)
    
    # 전체 요약
    if len(symbols) > 1 and all_results:
        print("\n")
        print("╔" + "═" * 78 + "╗")
        print("║" + "  📊 전체 심볼 종합 결과  ".center(78) + "║")
        print("╚" + "═" * 78 + "╝")
        
        # 전략별 집계
        strategy_summary = {}
        for result in all_results:
            name = result.strategy_name
            if name not in strategy_summary:
                strategy_summary[name] = {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'total_return': 0,
                    'symbols': []
                }
            
            strategy_summary[name]['total_trades'] += result.total_trades
            strategy_summary[name]['winning_trades'] += result.winning_trades
            strategy_summary[name]['total_return'] += result.total_return
            strategy_summary[name]['symbols'].append(result.symbol)
        
        print("\n전략별 종합 성과:")
        for name, data in strategy_summary.items():
            win_rate = data['winning_trades'] / data['total_trades'] if data['total_trades'] > 0 else 0
            avg_return = data['total_return'] / len(data['symbols']) if data['symbols'] else 0
            
            print(f"\n  📌 {name}")
            print(f"     • 총 거래: {data['total_trades']}회")
            print(f"     • 종합 승률: {win_rate:.1%}")
            print(f"     • 심볼당 평균 수익: ${avg_return:+,.2f}")
    
    print("\n" + "=" * 80)
    print("✅ 백테스트 완료!")
    print("=" * 80 + "\n")


if __name__ == '__main__':
    main()
