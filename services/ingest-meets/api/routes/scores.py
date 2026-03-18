"""Score routes."""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import Score

router = APIRouter()


@router.get("/")
def list_scores(
    event: Optional[str] = Query(None, description="e.g. vault, AA, balance_beam"),
    level: Optional[str] = Query(None),
    source: Optional[str] = Query(None, description="scorecat / mso / website"),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    """List recent scores with optional filters."""
    query = db.query(Score)
    if event:
        query = query.filter(Score.event == event)
    if level:
        query = query.filter(Score.level == level)
    if source:
        query = query.filter(Score.source == source)

    scores = query.order_by(Score.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": s.id,
            "athlete_id": s.athlete_id,
            "meet_id": s.meet_id,
            "event": s.event,
            "score": s.score,
            "place": s.place,
            "level": s.level,
            "source": s.source,
            "timestamp": s.timestamp.isoformat() if s.timestamp else None,
        }
        for s in scores
    ]
