from sqlalchemy import text

from nepse_sense.db import models  # noqa: F401  # Ensure models are registered
from nepse_sense.db.engine import Base, engine
from nepse_sense.logging import logger


def init_db():
    logger.info("Initializing database...")
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()
    logger.info("Database initialized successfully")


def reset_db():
    logger.warning("Resetting database...")
    Base.metadata.drop_all(bind=engine)
    init_db()
    logger.info("Database reset successfully")
