"""Runtime configuration for the agent and the API.

Loads a local .env file when present (real environment variables take
precedence), then validates the LLM settings at import time so that a
misconfigured process fails at startup instead of silently falling back
to another provider.
"""

import os

from dotenv import load_dotenv

load_dotenv()

SUPPORTED_PROVIDERS = ("anthropic", "ollama")
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()
if LLM_PROVIDER not in SUPPORTED_PROVIDERS:
    raise RuntimeError(
        "LLM_PROVIDER must be set to one of: " + ", ".join(SUPPORTED_PROVIDERS)
        + f" (got {LLM_PROVIDER!r})"
    )

if LLM_PROVIDER == "anthropic":
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
    LLM_MODEL = os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL).strip()
    OLLAMA_HOST = ""
else:
    ANTHROPIC_API_KEY = ""
    LLM_MODEL = os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip()
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST).strip()


def llm_info() -> dict:
    """Provider and model currently configured, for logs and the health endpoint."""
    return {"llm_provider": LLM_PROVIDER, "llm_model": LLM_MODEL}
