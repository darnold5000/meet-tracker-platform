"""Meet routes."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import Meet, Score

router = APIRouter()


@router.get("/")
def list_meets(
    state: Optional[str] = Query(None, description="Filter by state abbreviation"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db),
):
    """List all discovered meets."""
    query = db.query(Meet)
    if state:
        query = query.filter(Meet.state == state.upper())
    if is_active is not None:
        query = query.filter(Meet.is_active == is_active)
    meets = query.order_by(Meet.start_date.desc()).limit(200).all()
    return [_meet_to_dict(m) for m in meets]


@router.get("/{meet_id}")
def get_meet(meet_id: str, db: Session = Depends(get_db)):
    """Get a single meet by meet_id string."""
    meet = db.query(Meet).filter(Meet.meet_id == meet_id).first()
    if not meet:
        raise HTTPException(status_code=404, detail=f"Meet '{meet_id}' not found")
    return _meet_to_dict(meet)


@router.get("/{meet_id}/scores")
def get_meet_scores(
    meet_id: str,
    event: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """All scores for a meet, optionally filtered by event or level."""
    meet = db.query(Meet).filter(Meet.meet_id == meet_id).first()
    if not meet:
        raise HTTPException(status_code=404, detail=f"Meet '{meet_id}' not found")

    query = db.query(Score).filter(Score.meet_id == meet.id)
    if event:
        query = query.filter(Score.event == event)
    if level:
        query = query.filter(Score.level == level)

    scores = query.order_by(Score.event, Score.score.desc()).all()
    return [_score_to_dict(s) for s in scores]


def _meet_to_dict(m: Meet) -> dict:
    return {
        "meet_id": m.meet_id,
        "name": m.name,
        "location": m.location,
        "state": m.state,
        "start_date": m.start_date.isoformat() if m.start_date else None,
        "end_date": m.end_date.isoformat() if m.end_date else None,
        "host_gym": m.host_gym,
        "is_active": m.is_active,
        "scorecat_url": m.scorecat_url,
        "mso_url": m.mso_url,
    }


def _score_to_dict(s: Score) -> dict:
    return {
        "id": s.id,
        "athlete_id": s.athlete_id,
        "event": s.event,
        "score": s.score,
        "place": s.place,
        "level": s.level,
        "source": s.source,
        "timestamp": s.timestamp.isoformat() if s.timestamp else None,
    }
