"""Connexion à la base de données (SQLite en local, PostgreSQL en prod)."""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from celluletrade_cash_saas import config
from celluletrade_cash_saas.models import Base

connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(config.DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db():
    """Crée les tables si elles n'existent pas encore."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope():
    """Fournit une session SQLAlchemy avec commit/rollback automatique."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
