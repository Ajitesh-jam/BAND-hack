"""Database connection and models."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import Column, Float, Integer, String, create_engine
from sqlalchemy.exc import TimeoutError
from sqlalchemy.orm import Session, declarative_base, sessionmaker



class PoolExhaustedError(Exception):
    """Raised when the database connection pool is exhausted."""

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://checkout:checkout@localhost:5432/checkout",
)

engine = create_engine(
    DATABASE_URL,
    pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
    pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "5")),
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=100)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    customer_email = Column(String(200), nullable=False)
    product_id = Column(Integer, nullable=False)
    quantity = Column(Integer, default=1)
    status = Column(String(50), default="pending")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with session_scope() as db:
        if db.query(Product).count() == 0:
            db.add_all(
                [
                    Product(name="BandAid Kit", price=29.99, stock=500),
                    Product(name="Incident Runbook", price=9.99, stock=1000),
                    Product(name="War Room Mug", price=14.99, stock=200),
                ]
            )


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except TimeoutError:
        session.rollback()
        raise PoolExhaustedError("database connection pool timed out")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
