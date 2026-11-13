import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Session = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)  # no `with`: lifespan (real DB) is not started
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


class Actor:
    def __init__(self, id: int, token: str):
        self.id = id
        self.h = {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def make_user(client):
    def _make(role: str) -> Actor:
        email = f"{role.lower()}-{uuid.uuid4().hex[:8]}@example.com"
        body = {"name": "Test User", "email": email, "password": "password123", "role": role}
        r = client.post("/api/auth/register", json=body)
        assert r.status_code == 201, r.text
        user_id = r.json()["id"]
        r = client.post("/api/auth/login", json={"email": email, "password": "password123"})
        assert r.status_code == 200, r.text
        return Actor(user_id, r.json()["accessToken"])

    return _make


@pytest.fixture()
def organizer(make_user):
    return make_user("ORGANIZER")


@pytest.fixture()
def hackathon(client, organizer):
    r = client.post(
        "/api/hackathons",
        headers=organizer.h,
        json={
            "title": "AI Innovation Hackathon",
            "description": "Build innovative AI solutions",
            "location": "Almaty",
            "startDate": "2026-12-10T09:00:00Z",
            "endDate": "2026-12-12T18:00:00Z",
            "maxTeamSize": 2,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()
