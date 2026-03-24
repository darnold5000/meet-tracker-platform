"""Gym routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import Gym, Athlete

router = APIRouter()


@router.get("/")
def list_gyms(db: Session = Depends(get_db)):
    """List all gyms."""
    gyms = db.query(Gym).order_by(Gym.canonical_name).all()
    return [_gym_to_dict(g) for g in gyms]


@router.get("/{gym_id}")
def get_gym(gym_id: int, db: Session = Depends(get_db)):
    """Get a single gym with its athletes."""
    gym = db.query(Gym).filter(Gym.id == gym_id).first()
    if not gym:
        raise HTTPException(status_code=404, detail=f"Gym {gym_id} not found")

    athletes = db.query(Athlete).filter(Athlete.gym_id == gym_id).all()
    result = _gym_to_dict(gym)
    result["athletes"] = [{"id": a.id, "name": a.canonical_name, "level": a.level} for a in athletes]
    return result


def _gym_to_dict(g: Gym) -> dict:
    return {
        "id": g.id,
        "name": g.canonical_name,
        "state": g.state,
    }
