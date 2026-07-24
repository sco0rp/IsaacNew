"""
Load secrets from environment + local cli_auth_backup into SecretsStore.

Never commits secrets. Safe for CI (no-op if nothing present).

Sources (priority: existing os.environ wins, then files):
  1. process environment
  2. data/cli_auth_backup/all_cli_api_keys.env
  3. .env (if python-dotenv available or simple parse)

Also mirrors well-known keys into SecretsStore refs for tool auth.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("Isaac.SecretsBootstrap")

ROOT = Path(__file__).resolve().parent
BACKUP_ENV = ROOT / "data" / "cli_auth_backup" / "all_cli_api_keys.env"
DOTENV = ROOT / ".env"

# env key → secrets_store ref
SECRET_REFS: dict[str, str] = {
    "GROQ_API_KEY": "provider.groq.api_key",
    "OPENROUTER_API_KEY": "provider.openrouter.api_key",
    "OPENAI_API_KEY": "provider.openai.api_key",
    "GOOGLE_API_KEY": "provider.gemini.api_key",
    "GEMINI_API_KEY": "provider.gemini.api_key",
    "ANTHROPIC_API_KEY": "provider.anthropic.api_key",
    "XAI_API_KEY": "provider.xai.api_key",
    "GITHUB_TOKEN": "github.token",
    "GH_TOKEN": "github.token",
    "GITHUB_TOKEN_GLINKASTEFFEN075_BIT": "github.token",
    "SENTRY_DSN": "sentry.dsn",
    "COGNEE_API_KEY": "memory.cognee.api_key",
    "OPENROUTER_API_KEY_ALT": "provider.openrouter.api_key_alt",
}

# Keys that may be applied INTO os.environ from backup if missing
IMPORT_ENV_KEYS = frozenset(SECRET_REFS.keys()) | {
    "ACTIVE_PROVIDER",
    "GROQ_MODEL",
    "OPENROUTER_MODEL",
    "OLLAMA_HOST",
    "OLLAMA_MODEL",
    "SENTRY_TRACES_SAMPLE_RATE",
    "SENTRY_ENVIRONMENT",
    "SENTRY_RELEASE",
    "SENTRY_INCLUDE_PROMPTS",
    "ISAAC_GROK_AGENT_ENABLED",
    "ISAAC_AGENT_AUTO_SELECT",
    "ISAAC_OWNER",
}


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and v:
                out[k] = v
    except Exception as exc:
        log.debug("parse env file %s: %s", path, exc)
    return out


def load_secret_files_into_environ(*, overwrite: bool = False) -> dict[str, int]:
    """Load backup/.env keys into os.environ if missing (or overwrite=True)."""
    stats = {"files": 0, "applied": 0, "skipped_existing": 0}
    for path in (BACKUP_ENV, DOTENV):
        data = _parse_env_file(path)
        if not data:
            continue
        stats["files"] += 1
        for k, v in data.items():
            if k not in IMPORT_ENV_KEYS and not k.endswith("_API_KEY") and not k.endswith("_TOKEN"):
                continue
            if not v:
                continue
            if k in os.environ and os.environ.get(k) and not overwrite:
                stats["skipped_existing"] += 1
                continue
            os.environ[k] = v
            stats["applied"] += 1
    return stats


def sync_environ_to_secrets_store() -> dict[str, Any]:
    """Mirror known env secrets into SecretsStore (values never logged)."""
    from secrets_store import get_secrets_store

    store = get_secrets_store()
    written: list[str] = []
    for env_key, ref in SECRET_REFS.items():
        val = (os.getenv(env_key) or "").strip()
        if not val:
            continue
        # Prefer first non-empty; don't overwrite existing store with empty
        existing = store.get_secret(ref)
        if existing and existing == val:
            continue
        if existing and env_key in {"GH_TOKEN", "GITHUB_TOKEN_GLINKASTEFFEN075_BIT"}:
            # keep primary GITHUB_TOKEN if set
            if (os.getenv("GITHUB_TOKEN") or "").strip():
                continue
        store.set_secret(ref, val, kind="api_key")
        written.append(ref)
    return {"written_refs": written, "count": len(written)}


def resolve_secret(ref_or_env: str, default: str = "") -> str:
    """Resolve secret by store ref or env var name."""
    if not ref_or_env:
        return default
    # env first
    if ref_or_env.isupper() or ref_or_env.replace("_", "").isalnum():
        env_val = (os.getenv(ref_or_env) or "").strip()
        if env_val:
            return env_val
    try:
        from secrets_store import get_secrets_store

        val = get_secrets_store().get_secret(ref_or_env)
        if val:
            return str(val)
    except Exception:
        pass
    # map env name via SECRET_REFS
    ref = SECRET_REFS.get(ref_or_env)
    if ref:
        try:
            from secrets_store import get_secrets_store

            val = get_secrets_store().get_secret(ref)
            if val:
                return str(val)
        except Exception:
            pass
    return default


def bootstrap_secrets(*, overwrite_env: bool = False) -> dict[str, Any]:
    """Full bootstrap: files → environ → secrets store."""
    file_stats = load_secret_files_into_environ(overwrite=overwrite_env)
    store_stats = sync_environ_to_secrets_store()
    result = {
        "ok": True,
        "from_files": file_stats,
        "store": store_stats,
        "github_token_present": bool(resolve_secret("GITHUB_TOKEN") or resolve_secret("GH_TOKEN")),
        "groq_present": bool(resolve_secret("GROQ_API_KEY")),
        "sentry_dsn_present": bool(resolve_secret("SENTRY_DSN")),
        "xai_present": bool(resolve_secret("XAI_API_KEY")),
    }
    log.info(
        "Secrets bootstrap: files=%s applied=%s store_refs=%s",
        file_stats.get("files"),
        file_stats.get("applied"),
        store_stats.get("count"),
    )
    return result
