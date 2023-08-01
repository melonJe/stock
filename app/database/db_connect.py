from datetime import datetime
from sqlalchemy import create_engine, select, insert, String, BLOB, BigInteger, Integer, Date
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import QueuePool
import config
from sqlalchemy.orm import Session

engine = create_engine(f'mysql+pymysql://{config.DB_USER}:{config.DB_PASS}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}?charset=utf8mb4',
                       poolclass=QueuePool, pool_pre_ping=True)  # pool_recycle=3600,
session = sessionmaker(autoflush=False, autocommit=False, bind=engine)()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'user'
    email: Mapped[str] = mapped_column(String(255), nullable=True, primary_key=True)
    pass_hash: Mapped[bytes] = mapped_column(BLOB(), nullable=False)
    pass_salt: Mapped[bytes] = mapped_column(BLOB(), nullable=False)


class Stock(Base):
    __tablename__ = 'stock'
    symbol: Mapped[str] = mapped_column(String(255), nullable=True, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class StockBuy(Base):
    __tablename__ = 'stock_buy'
    id: Mapped[int] = mapped_column(BigInteger(), autoincrement=True, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    symbol: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    volume: Mapped[int] = mapped_column(Integer(), nullable=False)


class StockPrice(Base):
    __tablename__ = 'stock_price'
    symbol: Mapped[str] = mapped_column(String(255), nullable=True, primary_key=True)
    date = mapped_column(Date(), nullable=True, primary_key=True)
    open: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    high: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    close: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    low: Mapped[int] = mapped_column(BigInteger(), nullable=False)


class StockSubscription(Base):
    __tablename__ = 'stock_subscription'
    id: Mapped[int] = mapped_column(BigInteger(), autoincrement=True, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    symbol: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
