import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./hackmate.db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me-in-production-baby")
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
