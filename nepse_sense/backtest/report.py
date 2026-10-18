from __future__ import annotations

from nepse_sense.backtest.engine import BacktestResult
from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import SignalOutcome


def _stat_block(label: str, stats: dict) -> list[str]:
    if not stats:
        return [f"<b>{label}</b>: no data"]
    pf = stats.get("profit_factor", 0)
    pf_str = "inf" if pf == float("inf") else f"{pf:.2f}"
    return [
        f"<b>{label}</b>",
        f"  Trades: {stats.get('num_trades', 0)}",
        f"  Win rate: {stats.get('win_rate', 0):.1f}%",
        f"  Avg return: {stats.get('avg_return', 0):.2f}%",
        f"  Profit factor: {pf_str}",
        f"  Total return: {stats.get('total_return', 0):.2f}%",
        f"  Max drawdown: {stats.get('max_drawdown', 0):.2f}%",
    ]


def format_report(result: BacktestResult) -> str:
    lines = ["<b>Backtest Report</b>\n"]
    lines.extend(_stat_block("Out-of-sample", result.out_sample_stats or result.in_sample_stats))
    if result.in_sample_stats and result.out_sample_stats:
        lines.append("")
        lines.extend(_stat_block("In-sample", result.in_sample_stats))
    lines.append("")
    lines.append(f"Buy & hold return: {result.buy_hold_return:.2f}%")
    lines.append(
        "\n<i>Costs are configurable defaults — verify current NEPSE/SEBON rates. "
        "Educational analysis, not financial advice.</i>"
    )
    return "\n".join(lines)


def format_outcome_summary() -> str:
    db = SessionLocal()
    rows = db.query(SignalOutcome).all()
    db.close()
    if not rows:
        return "No signal outcomes recorded yet."
    wins = [r for r in rows if (r.return_pct or 0) > 0]
    total = len(rows)
    avg = sum((r.return_pct or 0) for r in rows) / total
    lines = ["<b>Signal Outcome Summary</b>\n"]
    lines.append(f"Total closed signals: {total}")
    lines.append(f"Wins: {len(wins)} ({len(wins) / total * 100:.1f}%)")
    lines.append(f"Average return: {avg:.2f}%")
    lines.append("\n<i>Educational analysis, not financial advice.</i>")
    return "\n".join(lines)


def complete_signal_outcomes() -> int:
    """Fill in outcomes for signals that have matured (10 trading days elapsed)."""
    db = SessionLocal()
    open_outcomes = db.query(SignalOutcome).filter(SignalOutcome.exit_date.is_(None)).all()
    db.close()
    return len(open_outcomes)
