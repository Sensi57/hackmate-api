"""Business logic. Routers stay thin; every rule of the platform lives here."""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import schemas
from .models import (
    Hackathon,
    HackathonStatus,
    JudgeAssignment,
    Project,
    Review,
    Team,
    TeamMember,
    User,
    UserRole,
)
from .security import create_access_token, hash_password, verify_password
from .utils import to_naive_utc


def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail=message)


def _commit(db: Session, conflict_message: str):
    """Commit; a violated DB unique constraint (e.g. a race) becomes 409."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _err(409, conflict_message)


# ------------------------------------------------------------------ auth
def register_user(db: Session, data: schemas.RegisterIn) -> User:
    email = data.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise _err(409, "Email is already registered")
    user = User(
        name=data.name.strip(),
        email=email,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    _commit(db, "Email is already registered")
    return user


def login_user(db: Session, data: schemas.LoginIn) -> dict:
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise _err(401, "Invalid email or password")
    return {
        "access_token": create_access_token(user.id, user.role.value),
        "token_type": "bearer",
        "user": user,
    }


# ------------------------------------------------------------ hackathons
def get_hackathon(db: Session, hackathon_id: int) -> Hackathon:
    hackathon = db.get(Hackathon, hackathon_id)
    if hackathon is None:
        raise _err(404, "Hackathon not found")
    return hackathon


def get_owned_hackathon(db: Session, hackathon_id: int, organizer: User) -> Hackathon:
    hackathon = get_hackathon(db, hackathon_id)
    if hackathon.organizer_id != organizer.id:
        raise _err(403, "Only the organizer of this hackathon can do this")
    return hackathon


def list_hackathons(
    db: Session, status: HackathonStatus | None, search: str | None, page: int, limit: int
) -> dict:
    query = select(Hackathon)
    if status:
        query = query.where(Hackathon.status == status)
    if search:
        query = query.where(Hackathon.title.ilike(f"%{search}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.order_by(Hackathon.id).offset((page - 1) * limit).limit(limit)
    ).all()
    return {"total": total, "page": page, "limit": limit, "items": items}


def create_hackathon(db: Session, data: schemas.HackathonCreate, organizer: User) -> Hackathon:
    # organizer_id always comes from the token, never from the request body
    hackathon = Hackathon(**data.model_dump(), organizer_id=organizer.id)
    db.add(hackathon)
    db.commit()
    return hackathon


def update_hackathon(
    db: Session, hackathon_id: int, data: schemas.HackathonUpdate, organizer: User
) -> Hackathon:
    hackathon = get_owned_hackathon(db, hackathon_id, organizer)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise _err(400, "No fields to update")

    start = changes.get("start_date", hackathon.start_date)
    end = changes.get("end_date", hackathon.end_date)
    if to_naive_utc(end) <= to_naive_utc(start):
        raise _err(400, "End date must be after start date")

    new_size = changes.get("max_team_size")
    if new_size is not None:
        biggest = max((len(t.members) for t in hackathon.teams), default=0)
        if new_size < biggest:
            raise _err(409, f"A team already has {biggest} members; cannot set a smaller limit")

    for field, value in changes.items():
        setattr(hackathon, field, value)
    db.commit()
    return hackathon


def delete_hackathon(db: Session, hackathon_id: int, organizer: User) -> None:
    hackathon = get_owned_hackathon(db, hackathon_id, organizer)
    db.delete(hackathon)  # cascades: teams, members, projects, reviews, assignments
    db.commit()


def assign_judge(
    db: Session, hackathon_id: int, data: schemas.JudgeAssignIn, organizer: User
) -> JudgeAssignment:
    hackathon = get_owned_hackathon(db, hackathon_id, organizer)
    judge = db.get(User, data.judge_id)
    if judge is None:
        raise _err(404, "User not found")
    if judge.role != UserRole.JUDGE:
        raise _err(400, "User does not have the JUDGE role")
    if db.scalar(
        select(JudgeAssignment.id).where(
            JudgeAssignment.hackathon_id == hackathon.id,
            JudgeAssignment.judge_id == judge.id,
        )
    ):
        raise _err(409, "Judge is already assigned to this hackathon")
    assignment = JudgeAssignment(hackathon_id=hackathon.id, judge_id=judge.id)
    db.add(assignment)
    _commit(db, "Judge is already assigned to this hackathon")
    return assignment


def leaderboard(db: Session, hackathon_id: int) -> dict:
    get_hackathon(db, hackathon_id)
    # Aggregation is done by the database (AVG / COUNT + GROUP BY), not in Python.
    rows = db.execute(
        select(
            Team.id,
            Team.name,
            func.avg(Review.score),
            func.count(Review.id),
        )
        .select_from(Team)
        .outerjoin(Project, Project.team_id == Team.id)
        .outerjoin(Review, Review.project_id == Project.id)
        .where(Team.hackathon_id == hackathon_id)
        .group_by(Team.id, Team.name)
    ).all()

    reviewed = sorted(
        [(tid, name, round(float(avg), 2), cnt) for tid, name, avg, cnt in rows if cnt > 0],
        key=lambda r: (-r[2], -r[3], r[1]),
    )
    entries = []
    prev_score, prev_rank = None, 0
    for position, (tid, name, avg, cnt) in enumerate(reviewed, start=1):
        rank = prev_rank if avg == prev_score else position  # ties share a rank
        prev_score, prev_rank = avg, rank
        entries.append(
            {
                "rank": rank,
                "teamId": tid,
                "team": name,
                "averageScore": avg,
                "reviewsCount": cnt,
                "status": "REVIEWED",
            }
        )
    # Teams without any review are listed at the end instead of being hidden.
    for tid, name, _, _ in sorted((r for r in rows if r[3] == 0), key=lambda r: r[1]):
        entries.append(
            {
                "rank": None,
                "teamId": tid,
                "team": name,
                "averageScore": None,
                "reviewsCount": 0,
                "status": "NOT_REVIEWED",
            }
        )
    return {"hackathonId": hackathon_id, "leaderboard": entries}


# ----------------------------------------------------------------- teams
def get_team(db: Session, team_id: int, lock: bool = False) -> Team:
    query = select(Team).where(Team.id == team_id)
    if lock:
        query = query.with_for_update()  # row lock on PostgreSQL; no-op on SQLite
    team = db.scalar(query)
    if team is None:
        raise _err(404, "Team not found")
    return team


def _can_manage_team(team: Team, user: User) -> bool:
    is_member = any(m.user_id == user.id for m in team.members)
    is_organizer = user.role == UserRole.ORGANIZER and team.hackathon.organizer_id == user.id
    return is_member or is_organizer


def list_teams(db: Session, hackathon_id: int) -> list[Team]:
    get_hackathon(db, hackathon_id)
    return list(
        db.scalars(select(Team).where(Team.hackathon_id == hackathon_id).order_by(Team.id))
    )


def _user_team_in_hackathon(db: Session, user_id: int, hackathon_id: int):
    return db.scalar(
        select(TeamMember.id).where(
            TeamMember.user_id == user_id, TeamMember.hackathon_id == hackathon_id
        )
    )


def create_team(db: Session, hackathon_id: int, data: schemas.TeamCreate, user: User) -> Team:
    hackathon = get_hackathon(db, hackathon_id)
    if hackathon.status == HackathonStatus.COMPLETED:
        raise _err(409, "Hackathon is completed")
    if _user_team_in_hackathon(db, user.id, hackathon.id):
        raise _err(409, "You are already in a team of this hackathon")
    name = data.name.strip()
    if db.scalar(select(Team.id).where(Team.hackathon_id == hackathon.id, Team.name == name)):
        raise _err(409, "Team name is already taken in this hackathon")

    team = Team(name=name, hackathon_id=hackathon.id)
    team.members.append(TeamMember(user_id=user.id, hackathon_id=hackathon.id))  # creator joins
    db.add(team)
    _commit(db, "Team name taken or you are already in a team of this hackathon")
    return team


def add_member(db: Session, team_id: int, user_id: int, actor: User) -> Team:
    # Lock the team row so two concurrent joins cannot both take the last free seat.
    team = get_team(db, team_id, lock=True)
    hackathon = team.hackathon
    if not _can_manage_team(team, actor):
        raise _err(403, "Only team members or the hackathon organizer can add members")
    if hackathon.status == HackathonStatus.COMPLETED:
        raise _err(409, "Hackathon is completed")

    user = db.get(User, user_id)
    if user is None:
        raise _err(404, "User not found")
    if user.role != UserRole.PARTICIPANT:
        raise _err(400, "Only users with the PARTICIPANT role can join teams")
    if _user_team_in_hackathon(db, user.id, hackathon.id):
        raise _err(409, "User is already in a team of this hackathon")

    count = db.scalar(select(func.count(TeamMember.id)).where(TeamMember.team_id == team.id))
    if count >= hackathon.max_team_size:
        raise _err(409, "Team is already full")

    db.add(TeamMember(user_id=user.id, team_id=team.id, hackathon_id=hackathon.id))
    _commit(db, "User is already in a team of this hackathon")
    db.refresh(team)
    return team


def remove_member(db: Session, team_id: int, user_id: int, actor: User) -> None:
    team = get_team(db, team_id, lock=True)
    is_self = actor.id == user_id
    is_organizer = actor.role == UserRole.ORGANIZER and team.hackathon.organizer_id == actor.id
    if not (is_self or is_organizer):
        raise _err(403, "You can only remove yourself, unless you are the organizer")
    member = db.scalar(
        select(TeamMember).where(TeamMember.team_id == team.id, TeamMember.user_id == user_id)
    )
    if member is None:
        raise _err(404, "User is not a member of this team")
    db.delete(member)
    db.commit()


# -------------------------------------------------------------- projects
def upsert_project(
    db: Session, team_id: int, data: schemas.ProjectIn, actor: User
) -> tuple[Project, bool]:
    team = get_team(db, team_id)
    if not any(m.user_id == actor.id for m in team.members):
        raise _err(403, "Only team members can edit the project")
    if team.hackathon.status == HackathonStatus.COMPLETED:
        raise _err(409, "Hackathon is completed")

    project = team.project
    created = project is None
    if created:
        project = Project(team_id=team.id)
        db.add(project)
    project.title = data.title.strip()
    project.description = data.description
    project.repository_url = data.repository_url
    project.demo_url = data.demo_url
    _commit(db, "Project already exists for this team")
    return project, created


# --------------------------------------------------------------- reviews
def get_project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise _err(404, "Project not found")
    return project


def list_reviews(db: Session, project_id: int) -> dict:
    project = get_project(db, project_id)
    count, avg = db.execute(
        select(func.count(Review.id), func.avg(Review.score)).where(
            Review.project_id == project.id
        )
    ).one()
    return {
        "project_id": project.id,
        "count": count,
        "average_score": round(float(avg), 2) if avg is not None else None,
        "reviews": project.reviews,
    }


def create_review(db: Session, project_id: int, data: schemas.ReviewIn, judge: User) -> Review:
    project = get_project(db, project_id)
    hackathon_id = project.team.hackathon_id
    if not db.scalar(
        select(JudgeAssignment.id).where(
            JudgeAssignment.hackathon_id == hackathon_id,
            JudgeAssignment.judge_id == judge.id,
        )
    ):
        raise _err(403, "Judge is not assigned to this hackathon")
    if db.scalar(
        select(Review.id).where(Review.project_id == project.id, Review.judge_id == judge.id)
    ):
        raise _err(409, "You have already reviewed this project")
    review = Review(
        project_id=project.id, judge_id=judge.id, score=data.score, comment=data.comment
    )
    db.add(review)
    _commit(db, "You have already reviewed this project")
    return review
