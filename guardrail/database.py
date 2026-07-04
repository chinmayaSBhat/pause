import os
import uuid
from datetime import datetime, date
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Date, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = "sqlite:///./guardrail.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True, default=generate_uuid)
    username = Column(String, unique=True, nullable=True)
    password_hash = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    monthly_income = Column(Float, default=0.0)
    work_hours_per_week = Column(Float, default=40.0)
    expense_rent = Column(Float, default=0.0)
    expense_emi = Column(Float, default=0.0)
    expense_subscriptions = Column(Float, default=0.0)
    expense_savings_sip = Column(Float, default=0.0)
    expense_other = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    wishlist_items = relationship("WishlistItem", back_populates="owner")
    daily_logs = relationship("DailyLog", back_populates="owner")
    allocations = relationship("BehavioralAllocation", back_populates="owner", cascade="all, delete-orphan")

class WishlistItem(Base):
    __tablename__ = "wishlist_items"

    item_id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.user_id"))
    item_name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    hours_to_earn = Column(Float, nullable=False)
    status = Column(String, default="COOLING") # 'COOLING', 'SAVED', 'BOUGHT'
    timer_expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="wishlist_items")

class DailyLog(Base):
    __tablename__ = "daily_logs"

    log_id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.user_id"))
    log_date = Column(Date, unique=True, nullable=False, default=date.today)
    is_no_spend_day = Column(Integer, default=1)
    money_saved_today = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="daily_logs")

class SavingGoal(Base):
    __tablename__ = "saving_goals"

    goal_id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.user_id"))
    goal_amount = Column(Float, nullable=False) # In Rupees
    start_date = Column(Date, nullable=False, default=date.today)
    end_date = Column(Date, nullable=False)
    status = Column(String, default="ACTIVE") # 'ACTIVE', 'COMPLETED', 'FAILED'
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User")

class BehavioralAllocation(Base):
    __tablename__ = "behavioral_allocations"

    allocation_id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.user_id"))
    category = Column(String, nullable=False)
    percentage = Column(Float, nullable=False)

    owner = relationship("User", back_populates="allocations")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
