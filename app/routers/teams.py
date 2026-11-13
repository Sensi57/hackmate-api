from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from .. import schemas, services
from ..database import get_db
from ..deps import get_current_user, require_role
from ..models import User, UserRole

router = APIRouter(tags=["Teams"])


@router.get("/hackathons/{hackathon_id}/teams", response_model=list[schemas.TeamOut])
def list_teams(hackathon_id: int, db: Session = Depends(get_db)):
    return services.list_teams(db, hackathon_id)


@router.post(
    "/hackathons/{hackathon_id}/teams", response_model=schemas.TeamOut, status_code=201
)
def create_team(
    hackathon_id: int,
    data: schemas.TeamCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.PARTICIPANT)),
):
    return services.create_team(db, hackathon_id, data, user)


@router.post("/teams/{team_id}/members", response_model=schemas.TeamOut, status_code=201)
def add_member(
    team_id: int,
    data: schemas.MemberAddIn,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return services.add_member(db, team_id, data.user_id, actor)


@router.delete("/teams/{team_id}/members/{user_id}", status_code=204)
def remove_member(
    team_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    services.remove_member(db, team_id, user_id, actor)
    return Response(status_code=204)
