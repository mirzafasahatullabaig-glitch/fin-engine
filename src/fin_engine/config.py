"""Runtime configuration and health checks (v1.5.3, reliability).

Local-first, env-driven. Nothing here is required — defaults match the existing
hardcoded values, so behaviour is unchanged unless the environment overrides it.

Env vars:
  FIN_ENGINE_OLLAMA_HOST   default http://localhost:11434
  FIN_ENGINE_GEN_MODEL     default granite4.2:8b
  FIN_ENGINE_EMBED_MODEL   default nomic-embed-text
  FIN_ENGINE_LOG_LEVEL     default WARNING (see logging_setup)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from .logging_setup import get_logger

_log = get_logger(__name__)


@dataclass(frozen=True)
class Config:
    ollama_host: str = "http://localhost:11434"
    gen_model: str = "granite4.2:8b"
    embed_model: str = "nomic-embed-text"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            ollama_host=os.getenv("FIN_ENGINE_OLLAMA_HOST", cls.ollama_host),
            gen_model=os.getenv("FIN_ENGINE_GEN_MODEL", cls.gen_model),
            embed_model=os.getenv("FIN_ENGINE_EMBED_MODEL", cls.embed_model),
        )


@dataclass(frozen=True)
class Health:
    """Result of a health check. ``ok`` iff Ollama is up and both models present."""

    ollama_up: bool
    gen_model_present: bool
    embed_model_present: bool
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.ollama_up and self.gen_model_present and self.embed_model_present


def health_check(config: Config | None = None, timeout: float = 5.0) -> Health:
    """Check Ollama reachability and that the configured models are pulled.

    Fails fast and informatively so the app can tell the user *before* a long
    model call hangs (report: model availability monitoring). Never raises —
    returns a structured result.
    """
    cfg = config or Config.from_env()
    host = cfg.ollama_host.rstrip("/")
    try:
        req = urllib.request.Request(f"{host}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            tags = json.loads(resp.read().decode())
        names = {m.get("name", "") for m in tags.get("models", [])}
        # Match on the family prefix so "granite4.2:8b" matches a pulled
        # "granite4.2:8b" exactly, and a bare family name is tolerated.
        def present(model: str) -> bool:
            return any(n == model or n.split(":")[0] == model.split(":")[0]
                       for n in names)
        gen_ok = present(cfg.gen_model)
        emb_ok = present(cfg.embed_model)
        _log.info("health check: ollama up, gen=%s embed=%s", gen_ok, emb_ok)
        missing = [m for m, ok in
                   ((cfg.gen_model, gen_ok), (cfg.embed_model, emb_ok)) if not ok]
        detail = "" if not missing else f"missing models: {', '.join(missing)}"
        return Health(True, gen_ok, emb_ok, detail)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log.warning("health check: ollama unreachable at %s (%s)", host, exc)
        return Health(False, False, False,
                      f"Ollama not reachable at {host}: {exc}")
