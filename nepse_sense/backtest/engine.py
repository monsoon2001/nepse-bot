from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from nepse_sense.backtest.costs import DEFAULT_COSTS, NepseCosts
from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import PriceCanonical, Signal


@dataclass
class Trade:
    symbol: str
    entry_date: date
    entry_price: float
    exit_date: date | None = None
    exit_price: float | None = None
    quantity: int = 1
    pnl: float = 0.0
    return_pct: float = 0.0


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    win_rate: float = 0.0
    avg_return: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    total_return: float = 0.0
    buy_hold_return: float = 0.0
    benchmark_label: str = ""  # e.g. "NEPSE index" or "single-stock approx"
    in_sample_stats: dict = field(default_factory=dict)
    out_sample_stats: dict = field(default_factory=dict)


class Backtester:
    def __init__(
        self,
        costs: NepseCosts = DEFAULT_COSTS,
        holding_period: int = 10,
        atr_stop_multiple: float = 2.0,
        target_pct: float = 0.10,
    ):
        self.costs = costs
        self.holding_period = holding_period
        self.atr_stop_multiple = atr_stop_multiple
        self.target_pct = target_pct
        self.db = SessionLocal()

    def __del__(self):
        try:
            self.db.close()
        except Exception:
            from nepse_sense.logging import logger

            logger.debug("Error closing db in Backtester")

    def _get_price(self, symbol: str, dt: date) -> PriceCanonical | None:
        return (
            self.db.query(PriceCanonical)
            .filter(PriceCanonical.symbol == symbol, PriceCanonical.date == dt)
            .first()
        )

    def _get_next_trading_day(self, symbol: str, after: date) -> date | None:
        nxt = (
            self.db.query(PriceCanonical.date)
            .filter(PriceCanonical.symbol == symbol, PriceCanonical.date > after)
            .order_by(PriceCanonical.date.asc())
            .first()
        )
        return nxt[0] if nxt else None

    def _index_return(
        self, start: date, end: date, index_name: str = "NEPSE"
    ) -> float | None:
        """Index buy-&-hold return (%) over [start, end], or None if no data."""
        from nepse_sense.db.models import IndexDaily

        first = (
            self.db.query(IndexDaily)
            .filter(IndexDaily.index_name == index_name, IndexDaily.day >= start)
            .order_by(IndexDaily.day.asc())
            .first()
        )
        last = (
            self.db.query(IndexDaily)
            .filter(IndexDaily.index_name == index_name, IndexDaily.day <= end)
            .order_by(IndexDaily.day.desc())
            .first()
        )
        if first and last and first.value:
            return (last.value - first.value) / first.value * 100
        return None

    def run(
        self,
        start_date: date,
        end_date: date,
        min_score: float = 50.0,
        signal_types: tuple[str, ...] = ("BUY_CANDIDATE", "BUY_WATCH"),
    ) -> BacktestResult:
        signals = (
            self.db.query(Signal)
            .filter(
                Signal.date >= start_date,
                Signal.date <= end_date,
                Signal.score >= min_score,
                Signal.type.in_(signal_types),
            )
            .order_by(Signal.date.asc())
            .all()
        )
        result = BacktestResult()
        open_trades: dict[str, Trade] = {}
        for sig in signals:
            entry_dt = self._get_next_trading_day(sig.symbol, sig.date)
            if entry_dt is None:
                continue
            entry_price_data = self._get_price(sig.symbol, entry_dt)
            if entry_price_data is None or entry_price_data.open is None:
                continue
            if sig.symbol in open_trades:
                continue
            entry_price = entry_price_data.open * (1 + self.costs.slippage_rate)
            trade = Trade(
                symbol=sig.symbol,
                entry_date=entry_dt,
                entry_price=entry_price,
            )
            open_trades[sig.symbol] = trade
            result.trades.append(trade)
        # Exit logic: holding period based, iterate dates
        for trade in result.trades:
            held = 0
            current_date = trade.entry_date
            while held < self.holding_period:
                nxt = self._get_next_trading_day(trade.symbol, current_date)
                if nxt is None:
                    break
                price_data = self._get_price(trade.symbol, nxt)
                if price_data is None:
                    break
                held += 1
                current_date = nxt
                if price_data.low is not None and price_data.high is not None:
                    stop_level = trade.entry_price * (1 - self.atr_stop_multiple * 0.02)
                    target_level = trade.entry_price * (1 + self.target_pct)
                    if price_data.low <= stop_level:
                        self._exit(trade, current_date, stop_level, result)
                        break
                    if price_data.high >= target_level:
                        self._exit(trade, current_date, target_level, result)
                        break
            if trade.exit_date is None:
                last_price_data = self._get_price(trade.symbol, current_date)
                if last_price_data and last_price_data.close:
                    self._exit(trade, current_date, last_price_data.close, result)
        closed = [t for t in result.trades if t.exit_date is not None]
        if closed:
            result.in_sample_stats = self._compute_stats(closed)
            result.win_rate = result.in_sample_stats["win_rate"]
            result.avg_return = result.in_sample_stats["avg_return"]
            result.profit_factor = result.in_sample_stats["profit_factor"]
            result.total_return = result.in_sample_stats["total_return"]
            result.max_drawdown = result.in_sample_stats["max_drawdown"]
            # Benchmark: prefer the NEPSE index over the same window; fall back
            # to a single-stock approximation when no index data is stored.
            first = closed[0]
            last = closed[-1]
            period_start = first.entry_date
            period_end = last.exit_date or last.entry_date
            index_ret = self._index_return(period_start, period_end)
            if index_ret is not None:
                result.buy_hold_return = index_ret
                result.benchmark_label = "NEPSE index"
            else:
                bh_entry = self._get_price(first.symbol, first.entry_date)
                bh_exit = (
                    self._get_price(last.symbol, last.exit_date) if last.exit_date else None
                )
                if bh_entry and bh_entry.close and bh_exit and bh_exit.close:
                    result.buy_hold_return = (
                        (bh_exit.close - bh_entry.close) / bh_entry.close * 100
                    )
                    result.benchmark_label = "single-stock approx"
        return result

    def _compute_stats(self, trades: list[Trade]) -> dict:
        if not trades:
            return {
                "win_rate": 0.0,
                "avg_return": 0.0,
                "profit_factor": 0.0,
                "total_return": 0.0,
                "max_drawdown": 0.0,
                "num_trades": 0,
            }
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        gross_profit = sum(t.pnl for t in wins) if wins else 0
        gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in trades:
            cumulative += t.return_pct
            peak = max(peak, cumulative)
            dd = peak - cumulative
            max_dd = max(max_dd, dd)
        return {
            "win_rate": len(wins) / len(trades) * 100,
            "avg_return": sum(t.return_pct for t in trades) / len(trades),
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
            "total_return": sum(t.return_pct for t in trades),
            "max_drawdown": max_dd,
            "num_trades": len(trades),
        }

    def run_walk_forward(
        self,
        start_date: date,
        end_date: date,
        split_pct: float = 0.7,
        min_score: float = 50.0,
        signal_types: tuple[str, ...] = ("BUY_CANDIDATE", "BUY_WATCH"),
    ) -> BacktestResult:
        """Run in-sample and out-of-sample backtest via a chronological split."""
        all_signals = (
            self.db.query(Signal.date)
            .filter(
                Signal.date >= start_date,
                Signal.date <= end_date,
                Signal.score >= min_score,
                Signal.type.in_(signal_types),
            )
            .distinct()
            .order_by(Signal.date.asc())
            .all()
        )
        if not all_signals:
            return BacktestResult()
        dates = [d[0] for d in all_signals]
        split_idx = int(len(dates) * split_pct)
        if split_idx <= 0 or split_idx >= len(dates):
            return self.run(start_date, end_date, min_score, signal_types)
        split_date = dates[split_idx]
        in_sample = self.run(start_date, split_date, min_score, signal_types)
        out_sample = self.run(split_date, end_date, min_score, signal_types)
        # Merge: primary result is out-of-sample (the honest metric)
        combined = out_sample
        combined.in_sample_stats = in_sample.in_sample_stats
        combined.out_sample_stats = out_sample.in_sample_stats
        return combined

    def store_outcomes(self, result: BacktestResult, signal_ids: dict | None = None) -> int:
        """Persist closed trades to signal_outcomes. Returns count stored."""
        from nepse_sense.db.models import SignalOutcome

        stored = 0
        for t in result.trades:
            if t.exit_date is None:
                continue
            outcome = "win" if t.pnl > 0 else "loss"
            self.db.add(
                SignalOutcome(
                    signal_id=(signal_ids or {}).get((t.symbol, t.entry_date), 0),
                    symbol=t.symbol,
                    entry_date=t.entry_date,
                    exit_date=t.exit_date,
                    outcome=outcome,
                    return_pct=t.return_pct,
                )
            )
            stored += 1
        self.db.commit()
        return stored

    def _exit(self, trade: Trade, exit_date: date, exit_price: float, result: BacktestResult):
        trade.exit_date = exit_date
        trade.exit_price = exit_price * (1 - self.costs.slippage_rate)
        proceeds = self.costs.sell_proceeds(trade.exit_price, trade.quantity, trade.entry_price)
        cost = self.costs.buy_cost(trade.entry_price, trade.quantity)
        trade.pnl = proceeds - cost
        trade.return_pct = (trade.pnl / cost) * 100 if cost > 0 else 0.0
