import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class UserRole(str, enum.Enum):
    ORGANIZER = "ORGANIZER"
    PARTICIPANT = "PARTICIPANT"
    JUDGE = "JUDGE"


class HackathonStatus(str, enum.Enum):
    UPCOMING = "UPCOMING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"


def _now():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), default=UserRole.PARTICIPANT
    )
    created_at: Mapped[datetime] = _now()

    organized_hackathons: Mapped[list["Hackathon"]] = relationship(back_populates="organizer")
    team_memberships: Mapped[list["TeamMember"]] = relationship(back_populates="user")
    reviews: Mapped[list["Review"]] = relationship(back_populates="judge")
    judge_assignments: Mapped[list["JudgeAssignment"]] = relationship(back_populates="judge")


class Hackathon(Base):
    __tablename__ = "hackathons"
    __table_args__ = (
        CheckConstraint("end_date > start_date", name="ck_hackathon_dates"),
        CheckConstraint("max_team_size BETWEEN 2 AND 10", name="ck_hackathon_team_size"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    max_team_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[HackathonStatus] = mapped_column(
        Enum(HackathonStatus, name="hackathon_status"), default=HackathonStatus.UPCOMING
    )
    organizer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _now()

    organizer: Mapped[User] = relationship(back_populates="organized_hackathons")
    teams: Mapped[list["Team"]] = relationship(
        back_populates="hackathon", cascade="all, delete-orphan"
    )
    judge_assignments: Mapped[list["JudgeAssignment"]] = relationship(
        back_populates="hackathon", cascade="all, delete-orphan"
    )


class JudgeAssignment(Base):
    __tablename__ = "judge_assignments"
    __table_args__ = (UniqueConstraint("hackathon_id", "judge_id", name="uq_assignment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hackathon_id: Mapped[int] = mapped_column(ForeignKey("hackathons.id", ondelete="CASCADE"))
    judge_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = _now()

    hackathon: Mapped[Hackathon] = relationship(back_populates="judge_assignments")
    judge: Mapped[User] = relationship(back_populates="judge_assignments")


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("hackathon_id", "name", name="uq_team_name_per_hackathon"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    hackathon_id: Mapped[int] = mapped_column(ForeignKey("hackathons.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = _now()

    hackathon: Mapped[Hackathon] = relationship(back_populates="teams")
    members: Mapped[list["TeamMember"]] = relationship(
        back_populates="team", cascade="all, delete-orphan", order_by="TeamMember.id"
    )
    project: Mapped[Optional["Project"]] = relationship(
        back_populates="team", cascade="all, delete-orphan", uselist=False
    )


class TeamMember(Base):
    """Many-to-many link User <-> Team.

    hackathon_id is denormalised on purpose: together with the unique constraint
    (user_id, hackathon_id) the database itself guarantees that a user is in at most
    one team per hackathon, even under concurrent requests.
    """

    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("user_id", "team_id", name="uq_member_team"),
        UniqueConstraint("user_id", "hackathon_id", name="uq_member_hackathon"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    hackathon_id: Mapped[int] = mapped_column(ForeignKey("hackathons.id", ondelete="CASCADE"))
    joined_at: Mapped[datetime] = _now()

    user: Mapped[User] = relationship(back_populates="team_memberships")
    team: Mapped[Team] = relationship(back_populates="members")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    repository_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    demo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), unique=True  # one team -> one project
    )

    team: Mapped[Team] = relationship(back_populates="project")
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Review.id"
    )


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("project_id", "judge_id", name="uq_review_once_per_judge"),
        CheckConstraint("score BETWEEN 1 AND 10", name="ck_review_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    judge_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    score: Mapped[int] = mapped_column(Integer)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _now()

    project: Mapped[Project] = relationship(back_populates="reviews")
    judge: Mapped[User] = relationship(back_populates="reviews")
