from datetime import date, timedelta

from nepse_sense.calendar.trading_calendar import TradingCalendar
from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import DataQualityIssue, PriceDaily

calendar = TradingCalendar()


class DataValidator:
    def __init__(self, price_tolerance_pct: float = 1.0, volume_tolerance_pct: float = 10.0):
        self.price_tolerance_pct = price_tolerance_pct
        self.volume_tolerance_pct = volume_tolerance_pct
        self.db = SessionLocal()

    def __del__(self):
        try:
            self.db.close()
        except Exception:
            from nepse_sense.logging import logger
            logger.debug("Error closing db")

    def validate_price_row(self, price: PriceDaily) -> list[DataQualityIssue]:
        issues = []
        if price.close is not None and price.close <= 0:
            issues.append(self._create_issue(price, "zero_or_negative_close", "critical"))
        if price.high is not None and price.high < 0:
            issues.append(self._create_issue(price, "negative_high", "critical"))
        if price.low is not None and price.low < 0:
            issues.append(self._create_issue(price, "negative_low", "critical"))
        if price.volume is not None and price.volume < 0:
            issues.append(self._create_issue(price, "negative_volume", "warning"))
        if all(v is not None for v in [price.high, price.low]) and price.high < price.low:
            issues.append(self._create_issue(price, "high_less_than_low", "critical"))
        if all(v is not None for v in [price.close, price.low, price.high]):
            if price.close < price.low or price.close > price.high:
                issues.append(self._create_issue(price, "close_outside_range", "critical"))
        issues.extend(self._check_suspicious_jumps(price))
        return issues

    def _create_issue(self, price: PriceDaily, issue_type: str, severity: str) -> DataQualityIssue:
        return DataQualityIssue(
            symbol=price.symbol,
            date=price.date,
            issue_type=issue_type,
            severity=severity,
            description=f"{issue_type} detected for {price.symbol} on {price.date}",
            source=price.source,
            resolved=False,
        )

    def _check_suspicious_jumps(self, price: PriceDaily) -> list[DataQualityIssue]:
        issues = []
        if price.close is None:
            return issues
        prev = (
            self.db.query(PriceDaily)
            .filter(PriceDaily.symbol == price.symbol)
            .filter(PriceDaily.date < price.date)
            .order_by(PriceDaily.date.desc())
            .first()
        )
        if prev and prev.close and prev.close > 0:
            pct_change = abs((price.close - prev.close) / prev.close * 100)
            if pct_change > 10.0:
                issues.append(
                    self._create_issue(price, "suspicious_jump_gt10pct", "warning")
                )
        return issues

    def validate_cross_source(self, symbol: str, dt: date):
        prices = (
            self.db.query(PriceDaily)
            .filter(PriceDaily.symbol == symbol, PriceDaily.date == dt)
            .all()
        )
        if len(prices) < 2:
            return
        for i, p1 in enumerate(prices):
            for p2 in prices[i + 1 :]:
                self._compare_prices(p1, p2)

    def _compare_prices(self, p1: PriceDaily, p2: PriceDaily):
        if p1.close and p2.close and p1.close > 0 and p2.close > 0:
            diff = abs((p1.close - p2.close) / max(p1.close, p2.close) * 100)
            if diff > self.price_tolerance_pct:
                issue = DataQualityIssue(
                    symbol=p1.symbol,
                    date=p1.date,
                    issue_type="price_mismatch_cross_source",
                    severity="warning",
                    description=f"Price mismatch {diff:.2f}% between sources",
                    source="validation",
                    resolved=False,
                )
                self.db.add(issue)
        if p1.volume and p2.volume:
            max_vol = max(abs(p1.volume), abs(p2.volume))
            if max_vol > 0:
                diff = abs((p1.volume - p2.volume) / max_vol * 100)
                if diff > self.volume_tolerance_pct:
                    issue = DataQualityIssue(
                        symbol=p1.symbol,
                        date=p1.date,
                        issue_type="volume_mismatch_cross_source",
                        severity="info",
                        description="Volume mismatch between sources",
                        source="validation",
                        resolved=False,
                    )
                    self.db.add(issue)
        self.db.commit()

    def find_missing_trading_days(self, start: date, end: date) -> list[date]:
        missing = []
        cur = start
        while cur <= end:
            if calendar.is_trading_day(cur):
                count = (
                    self.db.query(PriceDaily)
                    .filter(PriceDaily.date == cur)
                    .count()
                )
                if count == 0:
                    missing.append(cur)
            cur += timedelta(days=1)
        return missing
