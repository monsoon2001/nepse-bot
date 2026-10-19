"""Local matplotlib chart rendering (Agg backend, no display, no temp files).

Candles + EMA20/EMA50 + support/resistance zones + volume + RSI + MACD panels.
Rendering runs off the event loop via `asyncio.to_thread` in the handlers.
"""

from __future__ import annotations

import json
from datetime import date
from io import BytesIO

import matplotlib

matplotlib.use("Agg")  # must precede pyplot import; no display, safe for threads
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from nepse_sense.db.engine import SessionLocal  # noqa: E402
from nepse_sense.db.models import IndicatorDaily, PriceCanonical  # noqa: E402

TIMEFRAMES = {"3M": 90, "6M": 180, "1Y": 365}


def _parse_zones(raw) -> dict:
    if not raw:
        return {"support": [], "resistance": []}
    if isinstance(raw, (bytes, str)):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return {"support": [], "resistance": []}
    if not isinstance(raw, dict):
        return {"support": [], "resistance": []}
    return {
        "support": raw.get("support") or [],
        "resistance": raw.get("resistance") or [],
    }


def render_chart(symbol: str, days: int = 90) -> tuple[BytesIO | None, date | None]:
    """Render the full chart. Returns (buffer, as_of_date) or (None, None)."""
    days = max(2, int(days))
    db = SessionLocal()
    fig = None
    buf = None
    try:
        rows = (
            db.query(PriceCanonical)
            .filter(PriceCanonical.symbol == symbol)
            .order_by(PriceCanonical.date.desc())
            .limit(days)
            .all()
        )
        if not rows:
            return None, None
        rows = list(reversed(rows))

        dates = [p.date for p in rows]
        opens = [p.open if p.open is not None else p.close for p in rows]
        highs = [p.high if p.high is not None else p.close for p in rows]
        lows = [p.low if p.low is not None else p.close for p in rows]
        closes = [p.close for p in rows]
        volumes = [p.volume or 0 for p in rows]
        as_of = rows[-1].date

        inds = (
            db.query(IndicatorDaily)
            .filter(IndicatorDaily.symbol == symbol)
            .order_by(IndicatorDaily.date.desc())
            .limit(days)
            .all()
        )
        ind_by_date = {i.date: i for i in inds}
        ind_dates = [d for d in dates if d in ind_by_date]
        ema20 = [ind_by_date[d].ema20 for d in ind_dates]
        ema50 = [ind_by_date[d].ema50 for d in ind_dates]
        rsi = [ind_by_date[d].rsi14 for d in ind_dates]
        macd_l = [ind_by_date[d].macd_line for d in ind_dates]
        macd_s = [ind_by_date[d].macd_signal for d in ind_dates]
        macd_h = [ind_by_date[d].macd_hist for d in ind_dates]
        zones = _parse_zones(ind_by_date[ind_dates[-1]].zones) if ind_dates else {
            "support": [],
            "resistance": [],
        }

        x = mdates.date2num(dates)
        fig, (ax_p, ax_v, ax_r, ax_m) = plt.subplots(
            4,
            1,
            figsize=(12, 11),
            gridspec_kw={"height_ratios": [5, 1.2, 1.6, 1.6], "hspace": 0.32},
        )

        # --- price panel: S/R zones under candles ---
        for z in zones.get("resistance", [])[:5]:
            price = float(z.get("price", 0) or 0)
            ax_p.axhspan(price * 0.995, price * 1.005, color="red", alpha=0.10, zorder=0)
        for z in zones.get("support", [])[:5]:
            price = float(z.get("price", 0) or 0)
            ax_p.axhspan(price * 0.995, price * 1.005, color="green", alpha=0.10, zorder=0)

        # candles: wick line + body rectangle (width ~0.7 day)
        for xi, o, h, lo, c in zip(x, opens, highs, lows, closes, strict=False):
            up = c >= o
            color = "#26a69a" if up else "#ef5350"
            ax_p.plot([xi, xi], [lo, h], color=color, linewidth=0.8, zorder=2)
            body_low, body_high = min(o, c), max(o, c)
            ax_p.add_patch(
                Rectangle(
                    (xi - 0.35, body_low),
                    0.7,
                    max(body_high - body_low, 1e-9),
                    facecolor=color,
                    edgecolor=color,
                    alpha=0.9,
                    zorder=3,
                )
            )

        if any(v is not None for v in ema20):
            ax_p.plot(ind_dates, ema20, label="EMA20", color="#ff9800", linewidth=1.2)
        if any(v is not None for v in ema50):
            ax_p.plot(ind_dates, ema50, label="EMA50", color="#2196f3", linewidth=1.2)
        if zones.get("support") or zones.get("resistance"):
            ax_p.plot([], [], color="green", alpha=0.4, linewidth=6, label="Support zone")
            ax_p.plot([], [], color="red", alpha=0.4, linewidth=6, label="Resistance zone")

        ax_p.set_title(f"{symbol} — as of {as_of}")
        ax_p.legend(loc="best", fontsize=8)
        ax_p.grid(True, alpha=0.3)
        ax_p.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))

        # --- volume ---
        ax_v.bar(x, volumes, width=0.7, alpha=0.6, color="steelblue")
        ax_v.set_ylabel("Vol")
        ax_v.grid(True, alpha=0.3)

        # --- RSI ---
        if any(v is not None for v in rsi):
            ax_r.plot(ind_dates, rsi, color="#9c27b0", linewidth=1.2)
            ax_r.axhline(70, color="red", linestyle="--", linewidth=0.8, alpha=0.7)
            ax_r.axhline(30, color="green", linestyle="--", linewidth=0.8, alpha=0.7)
            ax_r.set_ylim(0, 100)
        ax_r.set_ylabel("RSI14")
        ax_r.grid(True, alpha=0.3)

        # --- MACD ---
        if any(v is not None for v in macd_l):
            ax_m.plot(ind_dates, macd_l, label="MACD", color="#26a69a", linewidth=1.1)
            ax_m.plot(ind_dates, macd_s, label="Signal", color="#ef5350", linewidth=1.1)
            if any(v is not None for v in macd_h):
                colors = ["#26a69a" if (h or 0) >= 0 else "#ef5350" for h in macd_h]
                ax_m.bar(ind_dates, macd_h, width=0.8, alpha=0.5, color=colors)
            ax_m.axhline(0, color="grey", linewidth=0.7)
            ax_m.legend(loc="best", fontsize=8)
        ax_m.set_ylabel("MACD")
        ax_m.grid(True, alpha=0.3)

        fig.suptitle(f"{symbol} · NEPSE Sense · {days}d", fontsize=11, y=0.995)
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
        buf.seek(0)
        return buf, as_of
    finally:
        if fig is not None:
            plt.close(fig)
        db.close()
        # buf is handed to the caller (Telegram send); caller closes it after send
