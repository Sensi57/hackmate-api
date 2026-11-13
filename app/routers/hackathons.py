from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from .. import schemas, services
from ..database import get_db
from ..deps import require_role
from ..models import HackathonStatus, User, UserRole

router = APIRouter(prefix="/hackathons", tags=["Hackathons"])

organizer_only = require_role(UserRole.ORGANIZER)


@router.get("", response_model=schemas.HackathonList)
def list_hackathons(
    status: Optional[HackathonStatus] = None,
    search: Optional[str] = Query(default=None, max_length=100, description="Title contains"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return services.list_hackathons(db, status, search, page, limit)


@router.post("", response_model=schemas.HackathonOut, status_code=201)
def create_hackathon(
    data: schemas.HackathonCreate,
    db: Session = Depends(get_db),
    organizer: User = Depends(organizer_only),
):
    return services.create_hackathon(db, data, organizer)


@router.get("/{hackathon_id}", response_model=schemas.HackathonOut)
def get_hackathon(hackathon_id: int, db: Session = Depends(get_db)):
    return services.get_hackathon(db, hackathon_id)


@router.patch("/{hackathon_id}", response_model=schemas.HackathonOut)
def update_hackathon(
    hackathon_id: int,
    data: schemas.HackathonUpdate,
    db: Session = Depends(get_db),
    organizer: User = Depends(organizer_only),
):
    return services.update_hackathon(db, hackathon_id, data, organizer)


@router.delete("/{hackathon_id}", status_code=204)
def delete_hackathon(
    hackathon_id: int,
    db: Session = Depends(get_db),
    organizer: User = Depends(organizer_only),
):
    services.delete_hackathon(db, hackathon_id, organizer)
    return Response(status_code=204)


@router.post("/{hackathon_id}/judges", response_model=schemas.JudgeAssignmentOut, status_code=201)
def assign_judge(
    hackathon_id: int,
    data: schemas.JudgeAssignIn,
    db: Session = Depends(get_db),
    organizer: User = Depends(organizer_only),
):
    return services.assign_judge(db, hackathon_id, data, organizer)


@router.get("/{hackathon_id}/leaderboard", tags=["Statistics"])
def leaderboard(hackathon_id: int, db: Session = Depends(get_db)):
    return services.leaderboard(db, hackathon_id)
