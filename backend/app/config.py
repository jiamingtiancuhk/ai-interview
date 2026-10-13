import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3:8b")
LLM_NUM_CTX = int(os.getenv("LLM_NUM_CTX", "8192"))

DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "interview.db"))

# Built frontend (frontend/dist). Served by FastAPI when present.
STATIC_DIR = Path(os.getenv("STATIC_DIR", BASE_DIR.parent / "frontend" / "dist"))

# Interview policy knobs
MAX_FOLLOW_UPS = int(os.getenv("MAX_FOLLOW_UPS", "3"))
