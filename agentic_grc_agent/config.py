"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    ollama_host: str = os.getenv("AGRC_OLLAMA_HOST", "http://localhost:11434")
    llm_model: str = os.getenv("AGRC_LLM_MODEL", "qwen2.5:7b")
    llm_timeout_s: float = float(os.getenv("AGRC_LLM_TIMEOUT_S", "8"))  # keeps the turn under the 10 s NFR
    llm_retries: int = int(os.getenv("AGRC_LLM_RETRIES", "1"))
    max_follow_ups: int = int(os.getenv("AGRC_MAX_FOLLOW_UPS", "3"))  # HU-06
    kb_path: Path = Path(os.getenv("AGRC_KB_PATH", Path(__file__).parent / "data" / "kb_demo.yaml"))
    trace_dir: Path = Path(os.getenv("AGRC_TRACE_DIR", "traces"))
