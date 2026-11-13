"""Business-rule tests: auth, hackathons, teams, projects, reviews, leaderboard."""


def hid(h):
    return h["id"]


def new_team(client, user, hackathon, name="Code Warriors"):
    r = client.post(f"/api/hackathons/{hid(hackathon)}/teams", headers=user.h, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def new_project(client, user, team):
    r = client.put(
        f"/api/teams/{team['id']}/project",
        headers=user.h,
        json={"title": "Smart Planner", "description": "Planner that uses AI to schedule tasks"},
    )
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ auth
def test_register_hides_password_and_rejects_duplicates(client):
    body = {"name": "Alex", "email": "alex@example.com", "password": "password123"}
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 201
    assert r.json()["role"] == "PARTICIPANT"
    assert "password" not in r.text.lower()
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 409
    assert r.json() == {"success": False, "message": "Email is already registered", "statusCode": 409}


def test_register_validation_error_is_400(client):
    r = client.post("/api/auth/register", json={"name": "A", "email": "nope", "password": "1"})
    assert r.status_code == 400
    body = r.json()
    assert body["success"] is False and body["statusCode"] == 400
    assert {e["field"] for e in body["errors"]} == {"name", "email", "password"}


def test_login_wrong_password_is_401(client, make_user):
    r = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "password123"})
    assert r.status_code == 401


def test_protected_endpoint_requires_token(client):
    assert client.post("/api/hackathons", json={}).status_code == 401
    r = client.post("/api/hackathons", json={}, headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


# ------------------------------------------------------------ hackathons
def test_hackathon_crud_flow(client, organizer, hackathon):
    assert hackathon["status"] == "UPCOMING"
    assert hackathon["organizerId"] == organizer.id

    r = client.get(f"/api/hackathons/{hid(hackathon)}")
    assert r.status_code == 200 and r.json()["title"] == hackathon["title"]

    r = client.get("/api/hackathons", params={"search": "innovation", "status": "UPCOMING"})
    assert r.status_code == 200 and r.json()["total"] == 1

    r = client.patch(
        f"/api/hackathons/{hid(hackathon)}", headers=organizer.h, json={"status": "ACTIVE"}
    )
    assert r.status_code == 200 and r.json()["status"] == "ACTIVE"

    r = client.delete(f"/api/hackathons/{hid(hackathon)}", headers=organizer.h)
    assert r.status_code == 204
    assert client.get(f"/api/hackathons/{hid(hackathon)}").status_code == 404


def test_hackathon_invalid_dates_is_400(client, organizer):
    r = client.post(
        "/api/hackathons",
        headers=organizer.h,
        json={
            "title": "Bad dates",
            "description": "End is before start",
            "location": "Almaty",
            "startDate": "2026-12-12T09:00:00Z",
            "endDate": "2026-12-10T09:00:00Z",
            "maxTeamSize": 4,
        },
    )
    assert r.status_code == 400
    assert r.json()["errors"][0]["message"] == "End date must be after start date"


def test_patch_cannot_make_dates_invalid(client, organizer, hackathon):
    r = client.patch(
        f"/api/hackathons/{hid(hackathon)}",
        headers=organizer.h,
        json={"endDate": "2026-12-01T00:00:00Z"},
    )
    assert r.status_code == 400


def test_only_organizer_role_can_create(client, make_user):
    participant = make_user("PARTICIPANT")
    r = client.post("/api/hackathons", headers=participant.h, json={})
    assert r.status_code == 403


def test_other_organizer_cannot_modify(client, make_user, hackathon):
    stranger = make_user("ORGANIZER")
    assert client.patch(
        f"/api/hackathons/{hid(hackathon)}", headers=stranger.h, json={"status": "ACTIVE"}
    ).status_code == 403
    assert client.delete(f"/api/hackathons/{hid(hackathon)}", headers=stranger.h).status_code == 403


def test_organizer_id_in_body_is_ignored(client, organizer, make_user):
    other = make_user("ORGANIZER")
    r = client.post(
        "/api/hackathons",
        headers=organizer.h,
        json={
            "title": "Spoof attempt",
            "description": "organizerId must come from the token",
            "location": "Astana",
            "startDate": "2026-12-10T09:00:00Z",
            "endDate": "2026-12-12T09:00:00Z",
            "maxTeamSize": 3,
            "organizerId": other.id,
        },
    )
    assert r.status_code == 201 and r.json()["organizerId"] == organizer.id


def test_assign_judge_rules(client, organizer, hackathon, make_user):
    judge, participant = make_user("JUDGE"), make_user("PARTICIPANT")
    url = f"/api/hackathons/{hid(hackathon)}/judges"
    assert client.post(url, headers=organizer.h, json={"judgeId": judge.id}).status_code == 201
    assert client.post(url, headers=organizer.h, json={"judgeId": judge.id}).status_code == 409
    assert client.post(url, headers=organizer.h, json={"judgeId": participant.id}).status_code == 400
    assert client.post(url, headers=organizer.h, json={"judgeId": 9999}).status_code == 404
    assert client.post(url, headers=judge.h, json={"judgeId": judge.id}).status_code == 403


# ----------------------------------------------------------------- teams
def test_create_team_for_missing_hackathon_is_404(client, make_user):
    p = make_user("PARTICIPANT")
    r = client.post("/api/hackathons/999/teams", headers=p.h, json={"name": "Ghosts"})
    assert r.status_code == 404


def test_creator_becomes_member_and_cannot_join_second_team(client, make_user, hackathon):
    p1, p2 = make_user("PARTICIPANT"), make_user("PARTICIPANT")
    team = new_team(client, p1, hackathon)
    assert [m["userId"] for m in team["members"]] == [p1.id]

    r = client.post(f"/api/hackathons/{hid(hackathon)}/teams", headers=p1.h, json={"name": "Second"})
    assert r.status_code == 409

    r = client.post(
        f"/api/hackathons/{hid(hackathon)}/teams", headers=p2.h, json={"name": "Code Warriors"}
    )
    assert r.status_code == 409  # duplicate team name within hackathon

    teams = client.get(f"/api/hackathons/{hid(hackathon)}/teams").json()
    assert len(teams) == 1 and teams[0]["name"] == "Code Warriors"


def test_user_cannot_be_in_two_teams_of_same_hackathon(client, make_user, hackathon):
    p1, p2, p3 = (make_user("PARTICIPANT") for _ in range(3))
    new_team(client, p1, hackathon, "Alpha")
    team_b = new_team(client, p2, hackathon, "Beta")
    # p1 is already in Alpha, so Beta must refuse them
    r = client.post(f"/api/teams/{team_b['id']}/members", headers=p2.h, json={"userId": p1.id})
    assert r.status_code == 409
    # but a free participant can join
    r = client.post(f"/api/teams/{team_b['id']}/members", headers=p2.h, json={"userId": p3.id})
    assert r.status_code == 201 and len(r.json()["members"]) == 2


def test_team_size_limit_returns_409(client, make_user, hackathon):  # maxTeamSize == 2
    p1, p2, p3 = (make_user("PARTICIPANT") for _ in range(3))
    team = new_team(client, p1, hackathon)
    url = f"/api/teams/{team['id']}/members"
    assert client.post(url, headers=p1.h, json={"userId": p2.id}).status_code == 201
    r = client.post(url, headers=p1.h, json={"userId": p3.id})
    assert r.status_code == 409 and r.json()["message"] == "Team is already full"


def test_add_member_validations(client, make_user, hackathon):
    p1, judge = make_user("PARTICIPANT"), make_user("JUDGE")
    outsider = make_user("PARTICIPANT")
    team = new_team(client, p1, hackathon)
    url = f"/api/teams/{team['id']}/members"
    assert client.post(url, headers=p1.h, json={"userId": judge.id}).status_code == 400
    assert client.post(url, headers=p1.h, json={"userId": 9999}).status_code == 404
    assert client.post("/api/teams/999/members", headers=p1.h, json={"userId": 1}).status_code == 404
    assert client.post(url, headers=outsider.h, json={"userId": outsider.id}).status_code == 403
    assert client.post(url, json={"userId": 1}).status_code == 401


def test_remove_member(client, make_user, hackathon):
    p1, p2, p3 = (make_user("PARTICIPANT") for _ in range(3))
    team = new_team(client, p1, hackathon)
    client.post(f"/api/teams/{team['id']}/members", headers=p1.h, json={"userId": p2.id})
    base = f"/api/teams/{team['id']}/members"
    assert client.delete(f"{base}/{p2.id}", headers=p3.h).status_code == 403
    assert client.delete(f"{base}/{p2.id}", headers=p2.h).status_code == 204  # leave
    assert client.delete(f"{base}/{p2.id}", headers=p2.h).status_code == 404
    # seat freed: p3 can now be added
    assert client.post(base, headers=p1.h, json={"userId": p3.id}).status_code == 201


# -------------------------------------------------------------- projects
def test_project_put_creates_then_updates(client, make_user, hackathon):
    p1, outsider = make_user("PARTICIPANT"), make_user("PARTICIPANT")
    team = new_team(client, p1, hackathon)
    url = f"/api/teams/{team['id']}/project"
    body = {
        "title": "Smart Planner",
        "description": "Planner that uses AI to schedule tasks",
        "repositoryUrl": "https://github.com/team/smart-planner",
    }
    r = client.put(url, headers=p1.h, json=body)
    assert r.status_code == 201 and r.json()["teamId"] == team["id"]
    r = client.put(url, headers=p1.h, json={**body, "title": "Smart Planner v2"})
    assert r.status_code == 200 and r.json()["title"] == "Smart Planner v2"
    assert client.put(url, headers=outsider.h, json=body).status_code == 403
    assert client.put(url, headers=p1.h, json={**body, "demoUrl": "not-a-url"}).status_code == 400


# --------------------------------------------------------------- reviews
def setup_reviewable(client, organizer, hackathon, make_user):
    judge, p1 = make_user("JUDGE"), make_user("PARTICIPANT")
    client.post(
        f"/api/hackathons/{hid(hackathon)}/judges", headers=organizer.h, json={"judgeId": judge.id}
    )
    team = new_team(client, p1, hackathon)
    project = new_project(client, p1, team)
    return judge, p1, team, project


def test_review_rules(client, organizer, hackathon, make_user):
    judge, p1, _, project = setup_reviewable(client, organizer, hackathon, make_user)
    url = f"/api/projects/{project['id']}/reviews"

    r = client.post(url, headers=judge.h, json={"score": 9, "comment": "Excellent"})
    assert r.status_code == 201 and r.json()["judgeId"] == judge.id

    assert client.post(url, headers=judge.h, json={"score": 5}).status_code == 409  # duplicate
    assert client.post(url, headers=p1.h, json={"score": 5}).status_code == 403  # not a judge
    other_judge = make_user("JUDGE")  # judge role but not assigned
    assert client.post(url, headers=other_judge.h, json={"score": 5}).status_code == 403
    assert client.post(url, headers=judge.h, json={"score": 11}).status_code == 400
    assert client.post(url, headers=judge.h, json={"score": 0}).status_code == 400
    assert client.post("/api/projects/999/reviews", headers=judge.h, json={"score": 5}).status_code == 404

    data = client.get(url).json()
    assert data["count"] == 1 and data["averageScore"] == 9.0


# ----------------------------------------------------------- leaderboard
def test_leaderboard_ranking_and_unreviewed_teams(client, organizer, hackathon, make_user):
    # maxTeamSize fixture is 2 which is fine: one member per team here
    judge1, judge2 = make_user("JUDGE"), make_user("JUDGE")
    for j in (judge1, judge2):
        client.post(
            f"/api/hackathons/{hid(hackathon)}/judges", headers=organizer.h, json={"judgeId": j.id}
        )
    users = [make_user("PARTICIPANT") for _ in range(3)]
    teams = [new_team(client, u, hackathon, n) for u, n in zip(users, ["Alpha", "Beta", "Gamma"])]
    alpha = new_project(client, users[0], teams[0])
    beta = new_project(client, users[1], teams[1])
    # Gamma never submits a project

    for judge, a, b in ((judge1, 10, 7), (judge2, 9, 8)):
        assert client.post(f"/api/projects/{alpha['id']}/reviews", headers=judge.h, json={"score": a}).status_code == 201
        assert client.post(f"/api/projects/{beta['id']}/reviews", headers=judge.h, json={"score": b}).status_code == 201

    r = client.get(f"/api/hackathons/{hid(hackathon)}/leaderboard")
    assert r.status_code == 200
    board = r.json()["leaderboard"]
    assert [(e["rank"], e["team"], e["averageScore"]) for e in board] == [
        (1, "Alpha", 9.5),
        (2, "Beta", 7.5),
        (None, "Gamma", None),
    ]
    assert board[2]["status"] == "NOT_REVIEWED"
    assert client.get("/api/hackathons/999/leaderboard").status_code == 404


def test_delete_hackathon_cascades(client, organizer, hackathon, make_user):
    judge, p1, team, project = setup_reviewable(client, organizer, hackathon, make_user)
    client.post(f"/api/projects/{project['id']}/reviews", headers=judge.h, json={"score": 8})
    assert client.delete(f"/api/hackathons/{hid(hackathon)}", headers=organizer.h).status_code == 204
    assert client.get(f"/api/projects/{project['id']}/reviews").status_code == 404


def test_unknown_route_uses_unified_error_format(client):
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["success"] is False


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}
