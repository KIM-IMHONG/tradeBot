"""
백테스트 엔진: 전략 시뮬레이션 및 성과 분석
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import pandas as pd
import numpy as np

from backtest.strategies import BaseStrategy, Signal


@dataclass
class Trade:
    """개별 거래 기록"""
    symbol: str
    side: str  # 'long', 'short'
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    quantity: float = 0
    tp_price: float = 0
    sl_price: float = 0
    pnl: float = 0
    pnl_pct: float = 0
    exit_reason: str = ''  # 'tp', 'sl'
    commission: float = 0
    reasons: List[str] = field(default_factory=list)


@dataclass
class BacktestResult:
    """백테스트 결과"""
    strategy_name: str
    strategy_description: str
    symbol: str
    trades: List[Trade] = field(default_factory=list)
    equity_curve: pd.Series = None
    
    # 기본 통계
    total_trades: int = 0
    long_trades: int = 0
    short_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # 승률
    win_rate: float = 0
    long_win_rate: float = 0
    short_win_rate: float = 0
    
    # 수익
    total_return: float = 0
    total_return_pct: float = 0
    max_drawdown: float = 0
    max_drawdown_pct: float = 0
    
    # 추가 지표
    profit_factor: float = 0
    avg_win: float = 0
    avg_loss: float = 0
    avg_trade: float = 0
    avg_win_pct: float = 0
    avg_loss_pct: float = 0
    
    sharpe_ratio: float = 0
    total_commission: float = 0
    
    # 기간
    start_date: datetime = None
    end_date: datetime = None
    duration_days: int = 0


class BacktestEngine:
    """백테스트 실행 엔진"""
    
    def __init__(
        self,
        initial_balance: float = 10000,
        leverage: int = 5,
        risk_per_trade: float = 0.02,
        commission_rate: float = 0.0004,  # 0.04% (바이낸스 선물 기본)
    ):
        self.initial_balance = initial_balance
        self.leverage = leverage
        self.risk_per_trade = risk_per_trade
        self.commission_rate = commission_rate
    
    def run(
        self,
        strategy: BaseStrategy,
        df: pd.DataFrame,
        symbol: str = 'BTCUSDT'
    ) -> BacktestResult:
        """단일 전략 백테스트 실행"""
        
        balance = self.initial_balance
        equity_history = []
        trades: List[Trade] = []
        open_position: Optional[Trade] = None
        
        # 지표 계산에 필요한 초기 구간 스킵
        start_idx = 50
        
        for i in range(start_idx, len(df)):
            current = df.iloc[i]
            historical = df.iloc[:i+1]
            
            current_time = current['timestamp']
            
            # 1. 오픈 포지션 있으면 청산 체크
            if open_position:
                exit_result = self._check_exit(open_position, current)
                
                if exit_result:
                    exit_price, exit_reason = exit_result
                    
                    # PnL 계산
                    if open_position.side == 'long':
                        pnl_pct = (exit_price - open_position.entry_price) / open_position.entry_price
                    else:
                        pnl_pct = (open_position.entry_price - exit_price) / open_position.entry_price
                    
                    # 레버리지 적용
                    pnl_pct_leveraged = pnl_pct * self.leverage
                    
                    # 청산 수수료
                    exit_commission = open_position.quantity * exit_price * self.commission_rate
                    
                    # 실제 PnL (수수료 차감)
                    position_value = open_position.quantity * open_position.entry_price
                    pnl = (position_value * pnl_pct_leveraged) - open_position.commission - exit_commission
                    
                    # 거래 기록 업데이트
                    open_position.exit_time = current_time
                    open_position.exit_price = exit_price
                    open_position.pnl = pnl
                    open_position.pnl_pct = pnl_pct_leveraged
                    open_position.exit_reason = exit_reason
                    open_position.commission += exit_commission
                    
                    trades.append(open_position)
                    balance += pnl
                    open_position = None
            
            # 2. 포지션 없으면 진입 시그널 체크
            if not open_position:
                signal = strategy.check_signal(historical)
                
                if signal and signal.side != 'none':
                    # 포지션 사이징 (리스크 기반)
                    risk_amount = balance * self.risk_per_trade
                    price_risk = abs(signal.entry_price - signal.sl_price)
                    
                    if price_risk > 0:
                        # 레버리지 고려한 수량 계산
                        quantity = (risk_amount / price_risk)
                        
                        # 최대 포지션 크기 제한 (잔고의 30%)
                        max_position_value = balance * 0.3 * self.leverage
                        max_quantity = max_position_value / signal.entry_price
                        quantity = min(quantity, max_quantity)
                        
                        # 진입 수수료
                        entry_commission = quantity * signal.entry_price * self.commission_rate
                        
                        open_position = Trade(
                            symbol=symbol,
                            side=signal.side,
                            entry_time=current_time,
                            entry_price=signal.entry_price,
                            quantity=quantity,
                            tp_price=signal.tp_price,
                            sl_price=signal.sl_price,
                            commission=entry_commission,
                            reasons=signal.reasons
                        )
            
            # 3. 자산 기록
            unrealized_pnl = 0
            if open_position:
                if open_position.side == 'long':
                    unrealized_pnl_pct = (current['close'] - open_position.entry_price) / open_position.entry_price
                else:
                    unrealized_pnl_pct = (open_position.entry_price - current['close']) / open_position.entry_price
                
                unrealized_pnl = (open_position.quantity * open_position.entry_price * 
                                  unrealized_pnl_pct * self.leverage)
            
            equity_history.append({
                'timestamp': current_time,
                'balance': balance,
                'equity': balance + unrealized_pnl
            })
        
        # 마지막에 열린 포지션 강제 청산
        if open_position:
            last_price = df.iloc[-1]['close']
            if open_position.side == 'long':
                pnl_pct = (last_price - open_position.entry_price) / open_position.entry_price
            else:
                pnl_pct = (open_position.entry_price - last_price) / open_position.entry_price
            
            pnl_pct_leveraged = pnl_pct * self.leverage
            exit_commission = open_position.quantity * last_price * self.commission_rate
            position_value = open_position.quantity * open_position.entry_price
            pnl = (position_value * pnl_pct_leveraged) - open_position.commission - exit_commission
            
            open_position.exit_time = df.iloc[-1]['timestamp']
            open_position.exit_price = last_price
            open_position.pnl = pnl
            open_position.pnl_pct = pnl_pct_leveraged
            open_position.exit_reason = 'end'
            open_position.commission += exit_commission
            
            trades.append(open_position)
        
        # 결과 계산
        result = self._calculate_metrics(strategy, symbol, trades, equity_history, df)
        return result
    
    def _check_exit(self, position: Trade, candle: pd.Series) -> Optional[Tuple[float, str]]:
        """TP/SL 체크"""
        high = candle['high']
        low = candle['low']
        
        if position.side == 'long':
            # 롱: 고가가 TP에 도달하면 익절, 저가가 SL에 도달하면 손절
            if high >= position.tp_price:
                return (position.tp_price, 'tp')
            if low <= position.sl_price:
                return (position.sl_price, 'sl')
        else:
            # 숏: 저가가 TP에 도달하면 익절, 고가가 SL에 도달하면 손절
            if low <= position.tp_price:
                return (position.tp_price, 'tp')
            if high >= position.sl_price:
                return (position.sl_price, 'sl')
        
        return None
    
    def _calculate_metrics(
        self,
        strategy: BaseStrategy,
        symbol: str,
        trades: List[Trade],
        equity_history: List[dict],
        df: pd.DataFrame
    ) -> BacktestResult:
        """성과 지표 계산"""
        
        result = BacktestResult(
            strategy_name=strategy.name,
            strategy_description=strategy.description,
            symbol=symbol,
            trades=trades
        )
        
        if not trades:
            return result
        
        # 기본 통계
        result.total_trades = len(trades)
        result.long_trades = len([t for t in trades if t.side == 'long'])
        result.short_trades = len([t for t in trades if t.side == 'short'])
        result.winning_trades = len([t for t in trades if t.pnl > 0])
        result.losing_trades = len([t for t in trades if t.pnl <= 0])
        
        # 승률
        result.win_rate = result.winning_trades / result.total_trades if result.total_trades > 0 else 0
        
        long_wins = len([t for t in trades if t.side == 'long' and t.pnl > 0])
        short_wins = len([t for t in trades if t.side == 'short' and t.pnl > 0])
        result.long_win_rate = long_wins / result.long_trades if result.long_trades > 0 else 0
        result.short_win_rate = short_wins / result.short_trades if result.short_trades > 0 else 0
        
        # 수익
        total_pnl = sum(t.pnl for t in trades)
        result.total_return = total_pnl
        result.total_return_pct = total_pnl / self.initial_balance
        
        # 평균
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        
        result.avg_win = np.mean([t.pnl for t in wins]) if wins else 0
        result.avg_loss = np.mean([t.pnl for t in losses]) if losses else 0
        result.avg_trade = np.mean([t.pnl for t in trades])
        
        result.avg_win_pct = np.mean([t.pnl_pct for t in wins]) if wins else 0
        result.avg_loss_pct = np.mean([t.pnl_pct for t in losses]) if losses else 0
        
        # Profit Factor
        gross_profit = sum(t.pnl for t in wins) if wins else 0
        gross_loss = abs(sum(t.pnl for t in losses)) if losses else 1
        result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # 자산 곡선 & 최대 낙폭
        if equity_history:
            equity_df = pd.DataFrame(equity_history)
            result.equity_curve = equity_df.set_index('timestamp')['equity']
            
            peak = equity_df['equity'].expanding().max()
            drawdown = (equity_df['equity'] - peak) / peak
            result.max_drawdown_pct = abs(drawdown.min())
            result.max_drawdown = result.max_drawdown_pct * self.initial_balance
        
        # 샤프 비율 (연환산)
        if equity_history and len(equity_history) > 1:
            equity_df = pd.DataFrame(equity_history)
            returns = equity_df['equity'].pct_change().dropna()
            if len(returns) > 0 and returns.std() > 0:
                # 15분봉 기준: 252일 * 24시간 * 4 (15분당 4개)
                periods_per_year = 252 * 24 * 4
                result.sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(periods_per_year)
        
        # 수수료
        result.total_commission = sum(t.commission for t in trades)
        
        # 기간
        result.start_date = df.iloc[0]['timestamp']
        result.end_date = df.iloc[-1]['timestamp']
        result.duration_days = (result.end_date - result.start_date).days
        
        return result
    
    def compare_strategies(
        self,
        strategies: List[BaseStrategy],
        df: pd.DataFrame,
        symbol: str = 'BTCUSDT'
    ) -> Tuple[pd.DataFrame, List[BacktestResult]]:
        """여러 전략 비교"""
        
        results = []
        for strategy in strategies:
            result = self.run(strategy, df, symbol)
            results.append(result)
        
        # 비교 테이블 생성
        comparison_data = []
        for r in results:
            comparison_data.append({
                '전략': r.strategy_name,
                '총거래': r.total_trades,
                '롱/숏': f"{r.long_trades}/{r.short_trades}",
                '승률': f"{r.win_rate:.1%}",
                '롱승률': f"{r.long_win_rate:.1%}",
                '숏승률': f"{r.short_win_rate:.1%}",
                '총수익률': f"{r.total_return_pct:.1%}",
                '최대낙폭': f"{r.max_drawdown_pct:.1%}",
                'PF': f"{r.profit_factor:.2f}",
                '샤프': f"{r.sharpe_ratio:.2f}",
                '평균거래': f"${r.avg_trade:.2f}",
                '수수료': f"${r.total_commission:.2f}",
            })
        
        comparison = pd.DataFrame(comparison_data)
        return comparison, results
