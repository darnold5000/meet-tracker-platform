"""Athlete routes."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import Athlete, Score, Meet

router = APIRouter()


@router.get("/")
def list_athletes(
    gym_id: Optional[int] = Query(None),
    level: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List athletes, optionally filtered by gym or level."""
    query = db.query(Athlete)
    if gym_id:
        query = query.filter(Athlete.gym_id == gym_id)
    if level:
        query = query.filter(Athlete.level == level)
    athletes = query.order_by(Athlete.canonical_name).limit(500).all()
    return [_athlete_to_dict(a) for a in athletes]


@router.get("/{athlete_id}")
def get_athlete(athlete_id: int, db: Session = Depends(get_db)):
    """Get a single athlete profile."""
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail=f"Athlete {athlete_id} not found")
    return _athlete_to_dict(athlete)


@router.get("/{athlete_id}/history")
def get_athlete_history(athlete_id: int, db: Session = Depends(get_db)):
    """Full meet history for an athlete — all scores across all meets."""
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail=f"Athlete {athlete_id} not found")

    scores = (
        db.query(Score, Meet)
        .join(Meet, Score.meet_id == Meet.id)
        .filter(Score.athlete_id == athlete_id)
        .order_by(Meet.start_date.desc(), Score.event)
        .all()
    )

    return {
        "athlete": _athlete_to_dict(athlete),
        "history": [
            {
                "meet_id": meet.meet_id,
                "meet_name": meet.name,
                "meet_date": meet.start_date.isoformat() if meet.start_date else None,
                "event": score.event,
                "score": score.score,
                "place": score.place,
                "level": score.level,
            }
            for score, meet in scores
        ],
    }


def _athlete_to_dict(a: Athlete) -> dict:
    return {
        "id": a.id,
        "name": a.canonical_name,
        "gym_id": a.gym_id,
        "level": a.level,
    }
