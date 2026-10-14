import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3:8b")
LLM_NUM_CTX = int(os.getenv("LLM_NUM_CTX", "8192"))

# A Hugging Face repo id, or a local folder (relative to backend/). The local
# copy from scripts/download_asr_model.py is preferred when present.
_LOCAL_ASR = BASE_DIR / "models" / "whisper-large-v3-turbo"
ASR_MODEL = os.getenv("ASR_MODEL") or (str(_LOCAL_ASR) if (_LOCAL_ASR / "config.json").exists() else "mlx-community/whisper-large-v3-turbo")
if not ASR_MODEL.startswith("mlx-community/") and not Path(ASR_MODEL).is_absolute():
    ASR_MODEL = str(BASE_DIR / ASR_MODEL)

DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "interview.db"))

# Built frontend (frontend/dist). Served by FastAPI when present.
STATIC_DIR = Path(os.getenv("STATIC_DIR", BASE_DIR.parent / "frontend" / "dist"))

# Interview policy knobs
MAX_FOLLOW_UPS = int(os.getenv("MAX_FOLLOW_UPS", "3"))
