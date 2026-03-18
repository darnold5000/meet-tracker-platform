"""SQLAlchemy ORM models for the USAG meet tracker."""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date,
    ForeignKey, Text, Boolean, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from db.database import Base


class Gym(Base):
    __tablename__ = "gyms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    canonical_name = Column(String(255), nullable=False, unique=True)
    state = Column(String(2))
    created_at = Column(DateTime, default=datetime.utcnow)

    athletes = relationship("Athlete", back_populates="gym")


class Athlete(Base):
    __tablename__ = "athletes"

    id = Column(Integer, primary_key=True, index=True)
    canonical_name = Column(String(255), nullable=False)
    gym_id = Column(Integer, ForeignKey("gyms.id"), nullable=True)
    level = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)

    gym = relationship("Gym", back_populates="athletes")
    scores = relationship("Score", back_populates="athlete")
    name_aliases = relationship("AthleteAlias", back_populates="athlete")

    __table_args__ = (
        Index("ix_athletes_canonical_name", "canonical_name"),
    )


class AthleteAlias(Base):
    """Stores alternate name spellings that resolve to one canonical athlete."""

    __tablename__ = "athlete_aliases"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    raw_name = Column(String(255), nullable=False)
    source = Column(String(50))  # scorecat / mso / website

    athlete = relationship("Athlete", back_populates="name_aliases")

    __table_args__ = (
        UniqueConstraint("athlete_id", "raw_name", name="uq_alias_athlete_name"),
    )


class Meet(Base):
    __tablename__ = "meets"

    id = Column(Integer, primary_key=True, index=True)
    meet_id = Column(String(100), unique=True, nullable=False)  # e.g. "2026-IN-STATE"
    name = Column(String(255), nullable=False)
    location = Column(String(255))
    state = Column(String(2))
    start_date = Column(Date)
    end_date = Column(Date)
    host_gym = Column(String(255))
    scorecat_url = Column(String(500))
    mso_url = Column(String(500))
    website_url = Column(String(500))
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sessions = relationship("Session", back_populates="meet")
    scores = relationship("Score", back_populates="meet")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    meet_id = Column(Integer, ForeignKey("meets.id"), nullable=False)
    session_number = Column(Integer)
    level = Column(String(20))
    start_time = Column(DateTime)

    meet = relationship("Meet", back_populates="sessions")
    scores = relationship("Score", back_populates="session")


class Score(Base):
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    meet_id = Column(Integer, ForeignKey("meets.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    event = Column(String(50), nullable=False)   # vault / bars / beam / floor / aa
    score = Column(Float, nullable=False)
    place = Column(Integer)
    level = Column(String(20))
    division = Column(String(50))  # e.g., "Sr 1", "Jr 3", etc.
    source = Column(String(50))   # scorecat / mso / website
    record_hash = Column(String(64), unique=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    athlete = relationship("Athlete", back_populates="scores")
    meet = relationship("Meet", back_populates="scores")
    session = relationship("Session", back_populates="scores")

    __table_args__ = (
        Index("ix_scores_athlete_meet", "athlete_id", "meet_id"),
        Index("ix_scores_meet_event", "meet_id", "event"),
    )


class IngestSourceState(Base):
    """
    Lightweight per-meet state for change detection/backoff.

    This lets scheduled jobs avoid heavy scraping/normalization when the upstream
    page hasn't changed since the last poll.
    """

    __tablename__ = "ingest_source_state"

    id = Column(Integer, primary_key=True, index=True)
    meet_id = Column(Integer, ForeignKey("meets.id"), nullable=False)
    source = Column(String(50), nullable=False)  # e.g. "mso_results"

    last_fingerprint = Column(String(64))  # sha256 hex
    last_changed_at = Column(DateTime)
    last_polled_at = Column(DateTime)

    meet = relationship("Meet")

    __table_args__ = (
        UniqueConstraint("meet_id", "source", name="uq_ingest_source_state_meet_source"),
        Index("ix_ingest_source_state_meet_source", "meet_id", "source"),
    )
