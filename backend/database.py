import os
import re

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "mplads.db")
)

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        # 16MB page cache per connection. The previous 64MB setting multiplied
        # across the pool's ~5 connections gave SQLite alone a theoretical
        # 320MB footprint on a 512MB instance.
        cursor.execute("PRAGMA cache_size=-16000")
        # SQLite groups aggregate intermediate rows in temp storage; MEMORY
        # would grow them in RAM on the big vendor GROUP BY passes.
        cursor.execute("PRAGMA temp_store=FILE")
    except Exception:
        pass
    finally:
        cursor.close()


@event.listens_for(engine, "connect")
def register_sqlite_udfs(dbapi_connection, connection_record):
    """SQL-side normalization UDFs — shared with the vendor-intelligence
    aggregation (main.py) so GROUP BY / JOIN keys are computed inside
    SQLite instead of streaming every row through Python."""

    def _normkey(value):
        # Same rule as main._vendor_key: lower-case, collapse every run of
        # non-alphanumerics to a single space, trim.
        return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

    try:
        dbapi_connection.create_function("normkey", 1, _normkey, deterministic=True)
    except Exception:
        # Older sqlite3 builds without the deterministic flag.
        try:
            dbapi_connection.create_function("normkey", 1, _normkey)
        except Exception:
            pass

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()
