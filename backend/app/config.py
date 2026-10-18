import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/prelude")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Fast model for interview turns, stronger model for reports and document extraction.
# Model IDs from ai.google.dev/gemini-api/docs/models (checked Oct 17 2026) — override in .env.
GEMINI_FAST_MODEL = os.getenv("GEMINI_FAST_MODEL", "gemini-3.8-flash")
GEMINI_SMART_MODEL = os.getenv("GEMINI_SMART_MODEL", "gemini-3.8-flash")
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
FHIR_SERVER_URL = os.getenv("FHIR_SERVER_URL", "https://hapi.fhir.org/baseR4")
MAX_QUESTIONS = int(os.getenv("MAX_QUESTIONS", "12"))
