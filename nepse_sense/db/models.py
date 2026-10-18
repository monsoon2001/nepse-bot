from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from nepse_sense.db.engine import Base


class Symbol(Base):
    __tablename__ = "symbols"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    company_name = Column(String(200))
    sector = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PriceDaily(Base):
    __tablename__ = "prices_daily"
    __table_args__ = (UniqueConstraint("symbol", "date", "source", name="uq_prices_daily"),)

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    source = Column(String(50), nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    turnover = Column(Float)
    raw_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class PriceCanonical(Base):
    __tablename__ = "prices_canonical"
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_prices_canonical"),)

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    turnover = Column(Float)
    sources = Column(JSON)
    provenance = Column(JSON)
    is_validated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class IndicatorDaily(Base):
    __tablename__ = "indicators_daily"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    ema20 = Column(Float)
    ema50 = Column(Float)
    rsi14 = Column(Float)
    macd_line = Column(Float)
    macd_signal = Column(Float)
    macd_hist = Column(Float)
    atr14 = Column(Float)
    rel_volume = Column(Float)
    high_52w = Column(Float)
    low_52w = Column(Float)
    indicators = Column(JSON)
    zones = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_indicators_daily"),)


class Fundamental(Base):
    __tablename__ = "fundamentals"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False)
    eps = Column(Float)
    pe = Column(Float)
    book_value = Column(Float)
    pb = Column(Float)
    sector_pe = Column(Float)
    sector_pb = Column(Float)
    score = Column(Float)
    score_breakdown = Column(JSON)
    raw_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_fundamentals"),)


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), index=True)
    date = Column(Date, nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    description = Column(Text)
    adjustment_factor = Column(Float, default=1.0)
    source = Column(String(50), default="manual")
    created_at = Column(DateTime, default=datetime.utcnow)


class News(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), index=True)
    date = Column(Date, nullable=False, index=True)
    title = Column(String(500))
    content = Column(Text)
    source = Column(String(100))
    impact_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    type = Column(String(50))
    score = Column(Float)
    reasons = Column(JSON)
    risk_flags = Column(JSON)
    data_asof = Column(DateTime)
    sources = Column(JSON)
    confidence_tier = Column(String(20))
    key_levels = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class SignalOutcome(Base):
    __tablename__ = "signal_outcomes"

    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, nullable=False)
    symbol = Column(String(20), index=True)
    entry_date = Column(Date)
    exit_date = Column(Date)
    outcome = Column(String(20))
    return_pct = Column(Float)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    settings = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, nullable=False)
    symbol = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("telegram_id", "symbol", name="uq_watchlist"),)


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    quantity = Column(Float, nullable=False)
    buy_price = Column(Float, nullable=False)
    buy_date = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AlertSent(Base):
    __tablename__ = "alerts_sent"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, nullable=False, index=True)
    symbol = Column(String(20))
    signal_type = Column(String(50))
    date = Column(Date, nullable=False)
    score = Column(Float)
    message_hash = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint(
            "telegram_id", "symbol", "date", "message_hash", name="uq_alert_sent"
        ),
    )


class SourceHealth(Base):
    __tablename__ = "source_health"

    id = Column(Integer, primary_key=True)
    source_name = Column(String(50), nullable=False, index=True)
    status = Column(String(20))
    last_success = Column(DateTime)
    last_check = Column(DateTime, default=datetime.utcnow)
    error_count = Column(Integer, default=0)
    response_time_ms = Column(Integer)
    details = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id = Column(Integer, primary_key=True)
    run_type = Column(String(50))
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    status = Column(String(20))
    symbols_processed = Column(Integer, default=0)
    symbols_excluded = Column(Integer, default=0)
    signals_generated = Column(Integer, default=0)
    details = Column(JSON)
    error_message = Column(Text)


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    issue_type = Column(String(50), nullable=False)
    severity = Column(String(20))
    description = Column(Text)
    details = Column(JSON)
    source = Column(String(50))
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
