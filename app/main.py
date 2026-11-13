from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .database import Base, engine
from .routers import auth, hackathons, projects, teams


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)  
    yield


app = FastAPI(
    title="HackMate API",
    description="REST API for managing hackathons, teams, projects and project evaluations.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

for router in (auth.router, hackathons.router, teams.router, projects.router):
    app.include_router(router, prefix="/api")


@app.get("/api/health", tags=["Health"])
def health():
    return {"status": "ok"}


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": str(exc.detail), "statusCode": exc.status_code},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = [
        {
            "field": ".".join(str(p) for p in e["loc"][1:]) or None,
            "message": e["msg"].removeprefix("Value error, "),
        }
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "message": "Validation failed",
            "statusCode": 400,
            "errors": errors,
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error", "statusCode": 500},
    )
