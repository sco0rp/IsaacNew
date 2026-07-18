"""Env-driven configuration for optional external memory adapters."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from config import DATA_DIR


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ExternalMemoryConfig:
    mem0_enabled: bool = False
    cognee_enabled: bool = False
    letta_enabled: bool = False
    open_interpreter_enabled: bool = False
    write_enabled: bool = False
    min_score: float = 5.0
    search_timeout_s: float = 2.5
    write_timeout_s: float = 3.0
    search_limit: int = 4
    owner_id: str = "Steffen"
    mem0_allow_cloud: bool = False
    cognee_allow_cloud: bool = False
    cognee_base_url: str = ""
    cognee_api_key: str = ""
    mem0_dir: Path = Path()
    cognee_dir: Path = Path()
    letta_bin: str = "letta"
    open_interpreter_bin: str = "interpreter"
    open_interpreter_sandbox: str = "read-only"
    open_interpreter_provider: str = "openrouter"
    open_interpreter_model: str = "openai/gpt-4o-mini"
    open_interpreter_timeout_s: float = 180.0
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_llm: str = "llama3.1:8b"
    ollama_embed: str = "nomic-embed-text:latest"

    @property
    def any_enabled(self) -> bool:
        return (
            self.mem0_enabled
            or self.cognee_enabled
            or self.letta_enabled
            or self.open_interpreter_enabled
        )


def load_external_memory_config() -> ExternalMemoryConfig:
    owner = (
        os.getenv("ISAAC_OWNER")
        or os.getenv("ISAAC_MEM0_USER_ID")
        or "Steffen"
    ).strip() or "Steffen"
    ollama_host = (
        os.getenv("OLLAMA_HOST")
        or os.getenv("ISAAC_OLLAMA_HOST")
        or "http://127.0.0.1:11434"
    ).rstrip("/")
    return ExternalMemoryConfig(
        mem0_enabled=_env_bool("ISAAC_MEM0_ENABLED", False),
        cognee_enabled=_env_bool("ISAAC_COGNEE_ENABLED", False),
        letta_enabled=_env_bool("ISAAC_LETTA_ENABLED", False),
        open_interpreter_enabled=_env_bool("ISAAC_OPEN_INTERPRETER_ENABLED", False),
        write_enabled=_env_bool("ISAAC_EXTERNAL_MEMORY_WRITE", False),
        min_score=_env_float("ISAAC_EXTERNAL_MEMORY_MIN_SCORE", 5.0),
        search_timeout_s=_env_float("ISAAC_EXTERNAL_MEMORY_SEARCH_TIMEOUT", 2.5),
        write_timeout_s=_env_float("ISAAC_EXTERNAL_MEMORY_WRITE_TIMEOUT", 3.0),
        search_limit=max(1, _env_int("ISAAC_EXTERNAL_MEMORY_SEARCH_LIMIT", 4)),
        owner_id=owner,
        mem0_allow_cloud=_env_bool("ISAAC_MEM0_ALLOW_CLOUD", False),
        cognee_allow_cloud=_env_bool("ISAAC_COGNEE_ALLOW_CLOUD", False),
        cognee_base_url=(
            os.getenv("COGNEE_BASE_URL") or os.getenv("ISAAC_COGNEE_BASE_URL") or ""
        ).strip().rstrip("/"),
        cognee_api_key=(
            os.getenv("COGNEE_API_KEY") or os.getenv("ISAAC_COGNEE_API_KEY") or ""
        ).strip(),
        mem0_dir=Path(os.getenv("ISAAC_MEM0_DIR") or (DATA_DIR / "mem0")),
        cognee_dir=Path(os.getenv("ISAAC_COGNEE_DIR") or (DATA_DIR / "cognee")),
        letta_bin=(os.getenv("LETTA_BIN") or "letta").strip() or "letta",
        open_interpreter_bin=(
            os.getenv("OPEN_INTERPRETER_BIN")
            or os.getenv("ISAAC_OPEN_INTERPRETER_BIN")
            or "interpreter"
        ).strip()
        or "interpreter",
        open_interpreter_sandbox=(
            os.getenv("ISAAC_OPEN_INTERPRETER_SANDBOX") or "read-only"
        ).strip()
        or "read-only",
        open_interpreter_provider=(
            os.getenv("ISAAC_OPEN_INTERPRETER_PROVIDER") or "openrouter"
        ).strip()
        or "openrouter",
        open_interpreter_model=(
            os.getenv("ISAAC_OPEN_INTERPRETER_MODEL") or "openai/gpt-4o-mini"
        ).strip()
        or "openai/gpt-4o-mini",
        open_interpreter_timeout_s=_env_float(
            "ISAAC_OPEN_INTERPRETER_TIMEOUT", 180.0
        ),
        ollama_host=ollama_host,
        ollama_llm=(
            os.getenv("ISAAC_MEM0_OLLAMA_MODEL")
            or os.getenv("OLLAMA_MODEL")
            or "llama3.1:8b"
        ).strip(),
        ollama_embed=(
            os.getenv("ISAAC_MEM0_EMBED_MODEL")
            or "nomic-embed-text:latest"
        ).strip(),
    )
