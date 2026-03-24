"""Cheer MVP schema: teams, meets, sessions, performances (timeline + scores)."""

from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from db.database import Base


class CheerMvpTeam(Base):
    __tablename__ = "cheer_mvp_teams"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    gym_name = Column(String(255))
    level = Column(String(64))
    division = Column(String(255))
    normalized_division = Column(String(255))

    performances = relationship("CheerMvpPerformance", back_populates="team")


class CheerMvpMeet(Base):
    __tablename__ = "cheer_mvp_meets"

    id = Column(Integer, primary_key=True)
    meet_key = Column(String(100), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255))
    start_date = Column(Date)
    end_date = Column(Date)
    source = Column(String(64))

    sessions = relationship("CheerMvpSession", back_populates="meet")
    performances = relationship("CheerMvpPerformance", back_populates="meet")


class CheerMvpSession(Base):
    __tablename__ = "cheer_mvp_sessions"

    id = Column(Integer, primary_key=True)
    meet_id = Column(Integer, ForeignKey("cheer_mvp_meets.id"), nullable=False)
    name = Column(String(255), nullable=False)
    display_order = Column(Integer, nullable=False, default=0)
    start_time = Column(DateTime)

    meet = relationship("CheerMvpMeet", back_populates="sessions")
    performances = relationship("CheerMvpPerformance", back_populates="session")


class CheerMvpPerformance(Base):
    """One timeline row: team routine or break."""

    __tablename__ = "cheer_mvp_performances"

    id = Column(Integer, primary_key=True)
    meet_id = Column(Integer, ForeignKey("cheer_mvp_meets.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("cheer_mvp_sessions.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("cheer_mvp_teams.id"), nullable=True)
    is_break = Column(Boolean, nullable=False, default=False)
    break_label = Column(String(255))
    scheduled_time = Column(DateTime)
    actual_time = Column(DateTime)
    round = Column(String(64))
    status = Column(String(32), nullable=False, default="upcoming")
    display_order = Column(Integer, nullable=False, default=0)
    final_score = Column(Float)
    rank = Column(Integer)
    deductions = Column(Float)

    meet = relationship("CheerMvpMeet", back_populates="performances")
    session = relationship("CheerMvpSession", back_populates="performances")
    team = relationship("CheerMvpTeam", back_populates="performances")
