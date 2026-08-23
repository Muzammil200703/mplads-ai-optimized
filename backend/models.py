from sqlalchemy import Column, Integer, String, Float, Boolean, Index
from database import Base

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String, index=True)
    state = Column(String, index=True)
    district = Column(String, index=True)
    constituency = Column(String, index=True)
    project_type = Column(String, index=True)
    sanctioned_amount = Column(Float, index=True)
    expenditure = Column(Float, index=True)
    completion_percentage = Column(Float, index=True)
    status = Column(String, index=True)

    __table_args__ = (
        Index("idx_project_state_dist", "state", "district"),
        Index("idx_project_state_status", "state", "status"),
    )


class MPSummary(Base):
    __tablename__ = "mp_summaries"

    id = Column(Integer, primary_key=True, index=True)
    mp_name = Column(String, index=True)
    constituency = Column(String, index=True)
    state = Column(String, index=True)
    house = Column(String)
    allocated_amount = Column(Float)
    total_expenditure = Column(Float)
    utilization_percentage = Column(Float)
    completed_works = Column(Integer)
    recommended_works = Column(Integer)
    completion_rate_percentage = Column(Float)
    unspent_amount = Column(Float)
    transaction_count = Column(Integer)
    successful_payments = Column(Integer)
    pending_payments = Column(Integer)
    average_rating = Column(Float)


class RecommendedWork(Base):
    __tablename__ = "recommended_works"

    id = Column(Integer, primary_key=True, index=True)
    work_id = Column(Integer, index=True)
    work_description = Column(String)
    category = Column(String, index=True)
    mp_name = Column(String, index=True)
    constituency = Column(String, index=True)
    state = Column(String, index=True)
    house = Column(String)
    recommended_amount = Column(Float)
    recommendation_date = Column(String)
    has_images = Column(Boolean)
    ida = Column(String)


class Expenditure(Base):
    __tablename__ = "expenditures"

    id = Column(Integer, primary_key=True, index=True)
    mp_name = Column(String, index=True)
    constituency = Column(String, index=True)
    state = Column(String, index=True)
    house = Column(String)
    work_description = Column(String)
    vendor = Column(String)
    ida = Column(String)
    expenditure_amount = Column(Float)
    expenditure_date = Column(String)
    payment_status = Column(String, index=True)


class CompletedWork(Base):
    __tablename__ = "completed_works"

    id = Column(Integer, primary_key=True, index=True)
    work_id = Column(Integer, index=True)
    work_description = Column(String)
    category = Column(String, index=True)
    mp_name = Column(String, index=True)
    constituency = Column(String, index=True)
    state = Column(String, index=True)
    house = Column(String)
    final_amount = Column(Float)
    completed_date = Column(String)
    has_images = Column(Boolean)
    average_rating = Column(Float)
    ida = Column(String)


class RiskScore(Base):
    __tablename__ = "risk_scores"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, index=True, unique=True)
    ml_anomaly = Column(Boolean, index=True)
    ml_score = Column(Float)
    risk_score = Column(Integer, index=True)
    risk_level = Column(String, index=True)
    reasons = Column(String)

    __table_args__ = (
        Index("idx_risk_level_score", "risk_level", "risk_score"),
    )
