"""NumPy-backed vector store with cosine similarity and JSON persistence.

In-memory, zero-infrastructure (report §5.2: the local-first option, swappable
for Qdrant/pgvector later). Vectors are L2-normalised on add, so cosine
similarity is a single matrix-vector dot product.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Chunk:
    """A stored text chunk and its provenance (report §3.1 source metadata)."""

    id: str
    text: str
    source: str          # file name / document title
    metadata: dict       # title, author, page, section, etc.


@dataclass(frozen=True)
class Retrieved:
    """A chunk returned from a search, with its similarity score."""

    chunk: Chunk
    score: float


class VectorStore:
    """Dense vector index over text chunks."""

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._matrix: np.ndarray | None = None  # shape (n, dim), unit rows

    def __len__(self) -> int:
        return len(self._chunks)

    @staticmethod
    def _normalise(vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0  # avoid division by zero for empty vectors
        return vectors / norms

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Add chunks with their embedding vectors (same order)."""
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must be the same length")
        if not chunks:
            return
        arr = self._normalise(np.asarray(vectors, dtype=np.float32))
        if self._matrix is not None and arr.shape[1] != self._matrix.shape[1]:
            raise ValueError(
                f"embedding dim {arr.shape[1]} does not match existing "
                f"{self._matrix.shape[1]} — did the embedding model change?"
            )
        self._chunks.extend(chunks)
        self._matrix = arr if self._matrix is None else np.vstack([self._matrix, arr])

    def search(self, query_vector: list[float], k: int = 4) -> list[Retrieved]:
        """Return the top-k chunks by cosine similarity."""
        if self._matrix is None or not self._chunks:
            return []
        q = self._normalise(np.asarray([query_vector], dtype=np.float32))[0]
        scores = self._matrix @ q  # cosine, since all rows are unit length
        k = min(k, len(self._chunks))
        top = np.argsort(-scores)[:k]
        return [Retrieved(self._chunks[i], float(scores[i])) for i in top]

    # --- persistence -----------------------------------------------------
    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "chunks": [asdict(c) for c in self._chunks],
            "matrix": [] if self._matrix is None else self._matrix.tolist(),
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "VectorStore":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        store = cls()
        store._chunks = [Chunk(**c) for c in data["chunks"]]
        matrix = data["matrix"]
        store._matrix = (
            np.asarray(matrix, dtype=np.float32) if matrix else None
        )
        return store
