from datetime import datetime
from typing import Optional

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from .models import HackathonStatus, UserRole
from .utils import to_naive_utc


class CamelModel(BaseModel):
    """JSON uses camelCase (maxTeamSize); snake_case is accepted too."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, from_attributes=True
    )


# ---------- auth / users ----------
class RegisterIn(CamelModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=64)
    role: UserRole = UserRole.PARTICIPANT


class LoginIn(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=64)


class UserOut(CamelModel):
    id: int
    name: str
    email: str
    role: UserRole
    created_at: datetime


class UserShort(CamelModel):
    id: int
    name: str
    role: UserRole


class TokenOut(CamelModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- hackathons ----------
class HackathonCreate(CamelModel):
    title: str = Field(min_length=3, max_length=100)
    description: str = Field(min_length=10)
    location: str = Field(min_length=2, max_length=200)
    start_date: datetime
    end_date: datetime
    max_team_size: int = Field(ge=2, le=10)

    @model_validator(mode="after")
    def check_dates(self):
        if to_naive_utc(self.end_date) <= to_naive_utc(self.start_date):
            raise ValueError("End date must be after start date")
        return self


class HackathonUpdate(CamelModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, min_length=10)
    location: Optional[str] = Field(default=None, min_length=2, max_length=200)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    max_team_size: Optional[int] = Field(default=None, ge=2, le=10)
    status: Optional[HackathonStatus] = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date and self.end_date:
            if to_naive_utc(self.end_date) <= to_naive_utc(self.start_date):
                raise ValueError("End date must be after start date")
        return self


class HackathonOut(CamelModel):
    id: int
    title: str
    description: str
    location: str
    start_date: datetime
    end_date: datetime
    max_team_size: int
    status: HackathonStatus
    organizer_id: int


class HackathonList(CamelModel):
    total: int
    page: int
    limit: int
    items: list[HackathonOut]


class JudgeAssignIn(CamelModel):
    judge_id: int


class JudgeAssignmentOut(CamelModel):
    id: int
    hackathon_id: int
    judge_id: int
    assigned_at: datetime


# ---------- teams ----------
class TeamCreate(CamelModel):
    name: str = Field(min_length=2, max_length=80)


class MemberAddIn(CamelModel):
    user_id: int


class TeamMemberOut(CamelModel):
    user_id: int
    joined_at: datetime
    user: UserShort


class TeamOut(CamelModel):
    id: int
    name: str
    hackathon_id: int
    created_at: datetime
    members: list[TeamMemberOut]


# ---------- projects / reviews ----------
class ProjectIn(CamelModel):
    title: str = Field(min_length=3, max_length=100)
    description: str = Field(min_length=10)
    repository_url: Optional[AnyHttpUrl] = None
    demo_url: Optional[AnyHttpUrl] = None

    @field_validator("repository_url", "demo_url")
    @classmethod
    def url_to_str(cls, v):
        return str(v) if v is not None else None


class ProjectOut(CamelModel):
    id: int
    title: str
    description: str
    repository_url: Optional[str]
    demo_url: Optional[str]
    team_id: int


class ReviewIn(CamelModel):
    score: int = Field(ge=1, le=10)
    comment: Optional[str] = Field(default=None, max_length=1000)


class ReviewOut(CamelModel):
    id: int
    project_id: int
    judge_id: int
    score: int
    comment: Optional[str]
    created_at: datetime


class ReviewList(CamelModel):
    project_id: int
    count: int
    average_score: Optional[float]
    reviews: list[ReviewOut]
