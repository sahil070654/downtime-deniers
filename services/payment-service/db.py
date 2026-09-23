import os
from sqlalchemy import create_engine, Column, Integer, Float, String
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = URL.create(
    drivername="mysql+pymysql",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASS"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    database=os.getenv("DB_NAME"),
)

engine = create_engine(DATABASE_URL, pool_size=10, pool_recycle=280)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="SUCCESS")

def init_db():
    Base.metadata.create_all(bind=engine)
