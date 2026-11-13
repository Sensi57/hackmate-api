from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from .. import schemas, services
from ..database import get_db
from ..deps import get_current_user, require_role
from ..models import User, UserRole

router = APIRouter(tags=["Projects & Reviews"])


@router.put(
    "/teams/{team_id}/project",
    response_model=schemas.ProjectOut,
    responses={201: {"model": schemas.ProjectOut, "description": "Project created"}},
)
def upsert_project(
    team_id: int,
    data: schemas.ProjectIn,
    response: Response,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """Creates the team's project (201) or updates the existing one (200)."""
    project, created = services.upsert_project(db, team_id, data, actor)
    response.status_code = 201 if created else 200
    return project


@router.get("/projects/{project_id}/reviews", response_model=schemas.ReviewList)
def list_reviews(project_id: int, db: Session = Depends(get_db)):
    return services.list_reviews(db, project_id)


@router.post(
    "/projects/{project_id}/reviews", response_model=schemas.ReviewOut, status_code=201
)
def create_review(
    project_id: int,
    data: schemas.ReviewIn,
    db: Session = Depends(get_db),
    judge: User = Depends(require_role(UserRole.JUDGE)),
):
    return services.create_review(db, project_id, data, judge)
