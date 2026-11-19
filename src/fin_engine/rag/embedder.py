"""Embedding providers.

The pipeline depends on the :class:`Embedder` protocol, not on Ollama directly,
so tests can inject a deterministic fake embedder and run fully offline — the
same pattern the rest of the engine uses to stay testable without external
services.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Anything that turns texts into fixed-length float vectors."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class OllamaEmbedder:
    """Embeds text via a local Ollama embedding model.

    Defaults to ``nomic-embed-text`` on ``http://localhost:11434``. Uses only
    the stdlib (``urllib``) so the project stays dependency-light.

    Pull the model first if needed::

        ollama pull nomic-embed-text
    """

    def __init__(
        self,
        model: str = "nomic-embed-text",
        host: str = "http://localhost:11434",
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            payload = json.dumps({"model": self.model, "prompt": text}).encode()
            req = urllib.request.Request(
                f"{self.host}/api/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode())
            except urllib.error.URLError as exc:
                raise RuntimeError(
                    f"Could not reach Ollama at {self.host}. Is it running, and "
                    f"is '{self.model}' pulled? (ollama pull {self.model})"
                ) from exc
            emb = data.get("embedding")
            if not emb:
                raise RuntimeError(f"Ollama returned no embedding: {data!r}")
            vectors.append([float(x) for x in emb])
        return vectors
