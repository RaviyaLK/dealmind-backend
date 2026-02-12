import logging
from sqlalchemy import create_engine, event, text, inspect
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

logger = logging.getLogger(__name__)

# SQLite needs different engine args than PostgreSQL
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
    )

    # Enable WAL mode and foreign keys for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency that provides a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _auto_migrate(engine_instance):
    """Add missing columns to existing tables (lightweight SQLite migration)."""
    insp = inspect(engine_instance)

    # Define migrations as (table, column, sql_type_default)
    migrations = [
        ("alerts", "email_subject", "VARCHAR(500)"),
        ("alerts", "email_body", "TEXT"),
    ]

    with engine_instance.connect() as conn:
        for table, column, col_type in migrations:
            if table in insp.get_table_names():
                existing_cols = [c["name"] for c in insp.get_columns(table)]
                if column not in existing_cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                    logger.info("Auto-migrate: added column %s.%s (%s)", table, column, col_type)
        conn.commit()


def init_db():
    """Create all tables. Called on startup."""
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    _auto_migrate(engine)
    logger.info("Database tables ready.")
