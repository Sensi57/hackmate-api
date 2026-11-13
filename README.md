# HackMate API

REST API for managing hackathons, teams, projects and project evaluations.
Built with **FastAPI + SQLAlchemy + PostgreSQL**.

## Features

- JWT authentication (bcrypt password hashing) with roles `ORGANIZER`, `PARTICIPANT`, `JUDGE`
- Hackathon management (CRUD, filtering, pagination)
- Teams with size limits; a user can be in only **one team per hackathon**
- Judge assignments; only assigned judges can review, **once per project**
- Project submission (one project per team)
- Leaderboard computed by the database (`AVG` / `COUNT` + `GROUP BY`)
- Pydantic validation, unified error format, automated tests, Postman collection

## Tech Stack

| Tool | Purpose |
| --- | --- |
| FastAPI | HTTP server, routing, OpenAPI docs |
| SQLAlchemy 2.0 | ORM (models, relationships, queries) |
| PostgreSQL | Relational database |
| Pydantic v2 | Request validation |
| PyJWT + bcrypt | Authentication |
| pytest + httpx | Automated tests |

## Installation

```bash
git clone <your-repo-url> hackmate-api
cd hackmate-api
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
docker compose up -d             # starts PostgreSQL on localhost:5432
```

### Environment variables

| Variable | Example |
| --- | --- |
| `DATABASE_URL` | `postgresql+psycopg2://hackmate:hackmate@localhost:5432/hackmate` |
| `JWT_SECRET` | long random string |
| `JWT_EXPIRE_MINUTES` | `1440` |

Without `DATABASE_URL` the app falls back to a local SQLite file (handy for a quick try-out only).
Tables are created automatically on startup.

## Run

```bash
uvicorn app.main:app --reload
```

- API base URL: `http://localhost:8000/api`
- Interactive docs (Swagger UI): `http://localhost:8000/docs`
- Health check: `GET /api/health`

## Tests

```bash
pytest
```

23 tests cover auth, role checks, validation, team rules, reviews, leaderboard and cascade delete (they run on an in-memory SQLite database).

## Postman

Import `postman/HackMate.postman_collection.json` and run the whole collection with the **Collection Runner** (in order).
It contains 52 requests (every endpoint plus error cases) and stores tokens/ids in collection variables automatically.
`baseUrl` defaults to `http://localhost:8000/api`.

## Project structure

```
hackmate-api/
├── app/
│   ├── main.py            # app, CORS, error handlers
│   ├── config.py          # environment settings
│   ├── database.py        # engine, session
│   ├── models.py          # 7 SQLAlchemy models
│   ├── schemas.py         # Pydantic request/response schemas
│   ├── security.py        # bcrypt + JWT
│   ├── deps.py            # auth dependencies (current user, role checks)
│   ├── services.py        # business logic
│   └── routers/           # auth, hackathons, teams, projects
├── tests/
├── postman/HackMate.postman_collection.json
├── docker-compose.yml
└── requirements.txt
```

Layers: **Router** (HTTP) → **Dependencies** (auth/roles) → **Service** (business rules) → **SQLAlchemy** → **PostgreSQL**.

## Database architecture (ER diagram)

```mermaid
erDiagram
    USER ||--o{ HACKATHON : organizes
    USER ||--o{ REVIEW : writes
    USER ||--o{ TEAM_MEMBER : "joins as"
    USER ||--o{ JUDGE_ASSIGNMENT : "is assigned"
    HACKATHON ||--o{ TEAM : has
    HACKATHON ||--o{ JUDGE_ASSIGNMENT : has
    TEAM ||--o{ TEAM_MEMBER : has
    TEAM ||--o| PROJECT : submits
    PROJECT ||--o{ REVIEW : receives

    USER {
        int id PK
        string name
        string email UK
        string password_hash
        enum role
        datetime created_at
    }
    HACKATHON {
        int id PK
        string title
        text description
        string location
        datetime start_date
        datetime end_date
        int max_team_size
        enum status
        int organizer_id FK
    }
    TEAM {
        int id PK
        string name
        int hackathon_id FK
        datetime created_at
    }
    TEAM_MEMBER {
        int id PK
        int user_id FK
        int team_id FK
        int hackathon_id FK
        datetime joined_at
    }
    PROJECT {
        int id PK
        string title
        text description
        string repository_url
        string demo_url
        int team_id FK "unique"
    }
    REVIEW {
        int id PK
        int project_id FK
        int judge_id FK
        int score "1..10"
        text comment
        datetime created_at
    }
    JUDGE_ASSIGNMENT {
        int id PK
        int hackathon_id FK
        int judge_id FK
        datetime assigned_at
    }
```

Relationships: **One-to-Many** (User→Hackathon, Hackathon→Team, Project→Review, User→Review), **Many-to-Many** through `TeamMember` (User↔Team) and `JudgeAssignment` (Judge↔Hackathon), **One-to-One** (Team→Project).

Database-level guarantees (unique constraints):

- `(user_id, hackathon_id)` on `team_members` — one team per user per hackathon, even under concurrent requests
- `(project_id, judge_id)` on `reviews` — a judge reviews a project once
- `(hackathon_id, judge_id)` on `judge_assignments`, `(hackathon_id, name)` on `teams`, `team_id` on `projects`
- check constraints: `score BETWEEN 1 AND 10`, `end_date > start_date`, `max_team_size BETWEEN 2 AND 10`

Team capacity is protected by a transaction with a row lock on the team (`SELECT ... FOR UPDATE`), so two simultaneous joins cannot take the last free seat.

---

# API documentation

All paths are relative to `/api`. JSON uses **camelCase**. Protected endpoints need the header
`Authorization: Bearer <accessToken>`.

### Error format

```json
{ "success": false, "message": "Team is already full", "statusCode": 409 }
```

Validation errors (400) additionally contain `errors`:

```json
{
  "success": false,
  "message": "Validation failed",
  "statusCode": 400,
  "errors": [{ "field": "endDate", "message": "End date must be after start date" }]
}
```

| Code | Meaning |
| --- | --- |
| 200 | OK (GET / PATCH / PUT update) |
| 201 | Created |
| 204 | Deleted, no body |
| 400 | Validation error / invalid business input |
| 401 | Missing or invalid token |
| 403 | Insufficient rights |
| 404 | Not found |
| 409 | Conflict (duplicate, team full, ...) |
| 500 | Internal server error |

## Authentication

### 1. `POST /auth/register` — register a user

Body:

```json
{ "name": "Alex", "email": "alex@example.com", "password": "password123", "role": "PARTICIPANT" }
```

`name` 2–100 chars, valid `email`, `password` 8–64 chars, `role` optional (`ORGANIZER` | `PARTICIPANT` | `JUDGE`, default `PARTICIPANT`).

`201 Created`:

```json
{ "id": 1, "name": "Alex", "email": "alex@example.com", "role": "PARTICIPANT", "createdAt": "2026-11-14T10:00:00Z" }
```

Errors: `400` validation, `409` email already registered.

### 2. `POST /auth/login` — get a JWT

Body: `{ "email": "alex@example.com", "password": "password123" }`

`200 OK`:

```json
{ "accessToken": "<jwt>", "tokenType": "bearer", "user": { "id": 1, "name": "Alex", "email": "alex@example.com", "role": "PARTICIPANT", "createdAt": "..." } }
```

Errors: `400` validation, `401` wrong email or password.

## Hackathons

### 3. `GET /hackathons` — list hackathons (public)

Query parameters: `status` (`UPCOMING|ACTIVE|COMPLETED`), `search` (title contains), `page` (default 1), `limit` (default 10, max 100).

`200 OK`:

```json
{
  "total": 1, "page": 1, "limit": 10,
  "items": [{
    "id": 1, "title": "AI Innovation Hackathon", "description": "Build innovative AI products",
    "location": "Almaty", "startDate": "2026-12-10T09:00:00Z", "endDate": "2026-12-12T18:00:00Z",
    "maxTeamSize": 4, "status": "UPCOMING", "organizerId": 1
  }]
}
```

### 4. `POST /hackathons` — create a hackathon (ORGANIZER)

Body:

```json
{
  "title": "AI Innovation Hackathon", "description": "Build innovative AI products", "location": "Almaty",
  "startDate": "2026-12-10T09:00:00Z", "endDate": "2026-12-12T18:00:00Z", "maxTeamSize": 4
}
```

Rules: `title` 3–100, `description` ≥ 10, `location` ≥ 2, `endDate` > `startDate`, `maxTeamSize` 2–10.
`organizerId` is taken from the token, never from the body.

`201 Created` — the hackathon object (status `UPCOMING`). Errors: `400`, `401`, `403`.

### 5. `GET /hackathons/{id}` — get one hackathon (public)

`200 OK` — hackathon object. Errors: `404`.

### 6. `PATCH /hackathons/{id}` — update (ORGANIZER, owner only)

Body: any subset of `title`, `description`, `location`, `startDate`, `endDate`, `maxTeamSize`, `status`.

`200 OK` — updated hackathon. Errors: `400` (empty body / invalid dates), `401`, `403`, `404`, `409` (`maxTeamSize` smaller than an existing team).

### 7. `DELETE /hackathons/{id}` — delete (ORGANIZER, owner only)

Deletes the hackathon with all its teams, memberships, projects, reviews and judge assignments.
`204 No Content`. Errors: `401`, `403`, `404`.

### 8. `POST /hackathons/{id}/judges` — assign a judge (ORGANIZER, owner only)

Body: `{ "judgeId": 3 }`

`201 Created`:

```json
{ "id": 1, "hackathonId": 1, "judgeId": 3, "assignedAt": "2026-11-14T10:00:00Z" }
```

Errors: `400` user is not a JUDGE, `401`, `403`, `404` hackathon/user not found, `409` already assigned.

### 9. `GET /hackathons/{id}/leaderboard` — team ranking (public)

Average review score per team, computed in SQL. Teams without reviews are listed at the end with `status: "NOT_REVIEWED"`. Teams with equal averages share a rank.

`200 OK`:

```json
{
  "hackathonId": 1,
  "leaderboard": [
    { "rank": 1, "teamId": 1, "team": "Code Warriors", "averageScore": 9.4, "reviewsCount": 5, "status": "REVIEWED" },
    { "rank": 2, "teamId": 2, "team": "Byte Masters", "averageScore": 8.7, "reviewsCount": 5, "status": "REVIEWED" },
    { "rank": null, "teamId": 3, "team": "Newbies", "averageScore": null, "reviewsCount": 0, "status": "NOT_REVIEWED" }
  ]
}
```

Errors: `404`.

## Teams

Team object:

```json
{
  "id": 1, "name": "Code Warriors", "hackathonId": 1, "createdAt": "2026-11-14T10:00:00Z",
  "members": [{ "userId": 1, "joinedAt": "...", "user": { "id": 1, "name": "Alex", "role": "PARTICIPANT" } }]
}
```

### 10. `GET /hackathons/{id}/teams` — teams of a hackathon (public)

`200 OK` — array of team objects. Errors: `404`.

### 11. `POST /hackathons/{id}/teams` — create a team (PARTICIPANT)

Body: `{ "name": "Code Warriors" }` (2–80 chars). The creator automatically becomes the first member.

`201 Created` — team object. Errors: `400`, `401`, `403`, `404` hackathon not found, `409` (hackathon completed, creator already in a team of this hackathon, team name taken).

### 12. `POST /teams/{id}/members` — add a member (team member or the hackathon's organizer)

Body: `{ "userId": 5 }`

Checks: team exists → caller may manage the team → user exists → user has role `PARTICIPANT` → user is not in another team of this hackathon → team is not full. Runs in a transaction with a row lock.

`201 Created` — updated team object. Errors: `400` user is not a PARTICIPANT, `401`, `403`, `404`, `409` (`Team is already full`, user already in a team of this hackathon).

### 13. `DELETE /teams/{id}/members/{userId}` — remove a member

Allowed for the user themselves (leave the team) or the hackathon's organizer.
`204 No Content`. Errors: `401`, `403`, `404` team or membership not found.

## Projects & Reviews

### 14. `PUT /teams/{id}/project` — create or update the team's project (team members)

Body:

```json
{
  "title": "Smart Planner", "description": "Planner that uses AI to schedule tasks",
  "repositoryUrl": "https://github.com/team/smart-planner", "demoUrl": "https://smart-planner.example.com"
}
```

`repositoryUrl` and `demoUrl` are optional, must be http(s) URLs.

`201 Created` on first call, `200 OK` when updating:

```json
{ "id": 1, "title": "Smart Planner", "description": "...", "repositoryUrl": "...", "demoUrl": "...", "teamId": 1 }
```

Errors: `400`, `401`, `403` not a member of the team, `404`, `409` hackathon completed.

### 15. `GET /projects/{id}/reviews` — reviews of a project (public)

`200 OK`:

```json
{
  "projectId": 1, "count": 1, "averageScore": 9.0,
  "reviews": [{ "id": 1, "projectId": 1, "judgeId": 3, "score": 9, "comment": "Excellent technical implementation", "createdAt": "..." }]
}
```

Errors: `404`.

### 16. `POST /projects/{id}/reviews` — review a project (JUDGE)

Body: `{ "score": 9, "comment": "Excellent technical implementation" }` — `score` integer 1–10, `comment` optional (≤ 1000 chars).

The judge must be assigned to the project's hackathon and may review a project only once.

`201 Created` — review object. Errors: `400` (score out of range), `401`, `403` (not a judge / not assigned), `404`, `409` (already reviewed).

---

## Author

Your name
