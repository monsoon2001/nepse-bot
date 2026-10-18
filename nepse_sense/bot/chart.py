from io import BytesIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import IndicatorDaily, PriceCanonical


def render_chart(symbol: str, days: int = 60) -> BytesIO | None:
    db = SessionLocal()
    prices = (
        db.query(PriceCanonical)
        .filter(PriceCanonical.symbol == symbol)
        .order_by(PriceCanonical.date.desc())
        .limit(days)
        .all()
    )
    prices = list(reversed(prices))
    if not prices:
        db.close()
        return None
    dates = [p.date for p in prices]
    closes = [p.close for p in prices]
    volumes = [p.volume or 0 for p in prices]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [3, 1]})
    ax1.plot(dates, closes, label="Close", linewidth=1.5)
    indicators = (
        db.query(IndicatorDaily)
        .filter(IndicatorDaily.symbol == symbol)
        .order_by(IndicatorDaily.date.desc())
        .limit(days)
        .all()
    )
    indicators = list(reversed(indicators))
    if indicators:
        ind_dates = [i.date for i in indicators]
        ema20 = [i.ema20 for i in indicators]
        ema50 = [i.ema50 for i in indicators]
        if any(ema20):
            ax1.plot(ind_dates, ema20, label="EMA20", linestyle="--", alpha=0.7)
        if any(ema50):
            ax1.plot(ind_dates, ema50, label="EMA50", linestyle="--", alpha=0.7)
    ax1.set_title(f"{symbol} - Price")
    ax1.legend(loc="best")
    ax1.grid(True, alpha=0.3)
    ax2.bar(dates, volumes, alpha=0.5, color="steelblue")
    ax2.set_title("Volume")
    ax2.grid(True, alpha=0.3)
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    db.close()
    return buf
