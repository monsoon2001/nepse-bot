from datetime import date, timedelta

from nepse_sense.config import settings
from nepse_sense.logging import logger


class TradingCalendar:
    def __init__(self):
        self.timezone = settings.timezone

    def is_trading_day(self, dt: date) -> bool:
        wd = dt.isoweekday()
        if wd in (1, 2, 3, 4, 7):
            return not self.is_holiday(dt)
        return False

    def is_holiday(self, dt: date) -> bool:
        try:
            import csv

            holidays_path = settings.project_root / "config" / "holidays.csv"
            if not holidays_path.exists():
                return False
            with open(holidays_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        hdate = date.fromisoformat(row["date"])
                        if hdate == dt:
                            return True
                    except Exception as e:
                        logger.debug(f"Error parsing holiday row: {e}")
                        continue
        except Exception as e:
            logger.debug(f"Error checking holidays: {e}")
            return False
        return False

    def next_trading_day(self, dt: date) -> date:
        nd = dt + timedelta(days=1)
        while not self.is_trading_day(nd):
            nd += timedelta(days=1)
        return nd

    def previous_trading_day(self, dt: date) -> date:
        pd = dt - timedelta(days=1)
        while not self.is_trading_day(pd):
            pd -= timedelta(days=1)
        return pd

    def get_last_trading_day(self) -> date:
        return self.previous_trading_day(date.today())
