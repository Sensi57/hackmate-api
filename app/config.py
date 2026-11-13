import os

from dotenv import load_dotenv

load_dotenv()

# PostgreSQL in production/dev (see .env.example). SQLite is only a zero-setup fallback.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./hackmate.db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me-in-production-0123456789")
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
