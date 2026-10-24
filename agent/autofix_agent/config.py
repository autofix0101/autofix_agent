"""
Configuration loader for AutoFix Agent.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from agent root or parents
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()


@dataclass(frozen=True)
class Settings:
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/autofix"
    )
    # LLM keys: supports Groq, Gemini, OpenAI
    GROQ_API_KEY: str | None = os.environ.get("GROQ_API_KEY")
    GEMINI_API_KEY: str | None = os.environ.get("GEMINI_API_KEY")
    LLM_API_KEY: str | None = (
        os.environ.get("LLM_API_KEY")
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
    )
    # Embedding config
    EMBED_MODEL: str = os.environ.get("EMBED_MODEL", "gemini-embedding-001")
    EMBED_DIM: int = int(os.environ.get("EMBED_DIM", "1536"))
    EMBED_BATCH_SIZE: int = int(os.environ.get("EMBED_BATCH_SIZE", "100"))

    # LLM Model config
    LLM_MODEL: str = os.environ.get("LLM_MODEL", "qwen/qwen3.8-27b")

    # Repositories storage directory
    REPOS_DIR: str = os.environ.get("REPOS_DIR", "/data/repos")

    # Worker & Pipeline settings
    MAX_VALIDATION_ATTEMPTS: int = int(os.environ.get("MAX_VALIDATION_ATTEMPTS", "3"))
    WORKER_POLL_INTERVAL: float = float(os.environ.get("WORKER_POLL_INTERVAL", "2.0"))


settings = Settings()
