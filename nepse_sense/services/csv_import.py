import csv
from datetime import datetime
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import Event, Fundamental, PriceDaily
from nepse_sense.logging import logger


class CSVImporter:
    def __init__(self):
        self.db = SessionLocal()

    def __del__(self):
        try:
            self.db.close()
        except Exception as e:
            logger.debug(f"Error closing db in destructor: {e}")

    def import_prices_csv(self, file_path: str | Path) -> int:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        count = 0
        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    price = PriceDaily(
                        symbol=str(row.get("symbol", row.get("SYMBOL", ""))).upper().strip(),
                        date=datetime.strptime(
                            str(row.get("date", row.get("DATE", ""))), "%Y-%m-%d"
                        ).date(),
                        source=str(row.get("source", "csv")),
                        open=float(row.get("open", 0)) if row.get("open") else None,
                        high=float(row.get("high", 0)) if row.get("high") else None,
                        low=float(row.get("low", 0)) if row.get("low") else None,
                        close=float(row.get("close", 0)) if row.get("close") else None,
                        volume=float(row.get("volume", 0)) if row.get("volume") else None,
                        turnover=float(row.get("turnover", 0)) if row.get("turnover") else None,
                    )
                    self.db.add(price)
                    self.db.commit()
                    count += 1
                except IntegrityError:
                    self.db.rollback()
                    logger.debug("Duplicate price record skipped")
                except Exception as e:
                    self.db.rollback()
                    logger.warning(f"Skipped row: {e}")
        logger.info(f"Imported {count} price records")
        return count

    def import_fundamentals_csv(self, file_path: str | Path) -> int:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        count = 0
        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    fund = Fundamental(
                        symbol=str(row.get("symbol", "")).upper().strip(),
                        date=datetime.strptime(str(row.get("date", "")), "%Y-%m-%d").date(),
                        eps=float(row.get("eps")) if row.get("eps") else None,
                        pe=float(row.get("pe")) if row.get("pe") else None,
                        book_value=float(row.get("book_value")) if row.get("book_value") else None,
                        pb=float(row.get("pb")) if row.get("pb") else None,
                        sector_pe=float(row.get("sector_pe")) if row.get("sector_pe") else None,
                        sector_pb=float(row.get("sector_pb")) if row.get("sector_pb") else None,
                    )
                    self.db.add(fund)
                    self.db.commit()
                    count += 1
                except IntegrityError:
                    self.db.rollback()
                    logger.debug("Duplicate fundamental record skipped")
                except Exception as e:
                    self.db.rollback()
                    logger.warning(f"Skipped row: {e}")
        logger.info(f"Imported {count} fundamental records")
        return count

    def import_events_csv(self, file_path: str | Path) -> int:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        count = 0
        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    event = Event(
                        symbol=str(row.get("symbol", "")).upper().strip()
                        if row.get("symbol")
                        else None,
                        date=datetime.strptime(str(row.get("date", "")), "%Y-%m-%d").date(),
                        event_type=str(row.get("event_type", "general")),
                        description=str(row.get("description", "")),
                        adjustment_factor=float(row.get("adjustment_factor", 1.0))
                        if row.get("adjustment_factor")
                        else 1.0,
                        source="csv",
                    )
                    self.db.add(event)
                    self.db.commit()
                    count += 1
                except Exception as e:
                    self.db.rollback()
                    logger.warning(f"Skipped row: {e}")
        logger.info(f"Imported {count} event records")
        return count
