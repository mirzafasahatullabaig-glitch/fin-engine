"""Config + health-check + logging tests (offline, no Ollama needed)."""

import logging

from fin_engine.config import Config, Health, health_check
from fin_engine.logging_setup import configure_logging, get_logger


def test_config_defaults():
    c = Config()
    assert c.ollama_host == "http://localhost:11434"
    assert c.gen_model == "granite4.2:8b"
    assert c.embed_model == "nomic-embed-text"


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("FIN_ENGINE_OLLAMA_HOST", "http://example:1234")
    monkeypatch.setenv("FIN_ENGINE_GEN_MODEL", "qwen2.5:14b")
    c = Config.from_env()
    assert c.ollama_host == "http://example:1234"
    assert c.gen_model == "qwen2.5:14b"
    assert c.embed_model == "nomic-embed-text"  # unset -> default


def test_health_check_unreachable_never_raises():
    # Point at a port nothing listens on; must return a Health, not raise.
    cfg = Config(ollama_host="http://127.0.0.1:1")
    h = health_check(cfg, timeout=1.0)
    assert isinstance(h, Health)
    assert h.ollama_up is False
    assert h.ok is False
    assert "not reachable" in h.detail


def test_health_ok_property():
    assert Health(True, True, True).ok is True
    assert Health(True, False, True).ok is False
    assert Health(False, False, False).ok is False


def test_get_logger_namespaced():
    assert get_logger("fin_engine.foo").name == "fin_engine.foo"
    assert get_logger("bar").name == "fin_engine.bar"  # auto-namespaced


def test_configure_logging_is_idempotent():
    configure_logging("INFO")
    configure_logging("INFO")  # second call must not add a second handler
    root = logging.getLogger("fin_engine")
    stream_handlers = [h for h in root.handlers
                       if isinstance(h, logging.StreamHandler)
                       and not isinstance(h, logging.NullHandler)]
    assert len(stream_handlers) == 1
