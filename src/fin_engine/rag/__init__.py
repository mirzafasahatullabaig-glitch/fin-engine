"""Knowledge Base A — general business-knowledge RAG (report §3.1, Phase 2).

Local-first, stdlib + NumPy only. Embeddings come from a local Ollama model
(``nomic-embed-text`` by default); generation from ``granite4.2:8b``. The vector
store is an in-memory NumPy index persisted to disk — no Qdrant/Postgres, in
keeping with the prototype's local-first design (report §5.2 left the vector-DB
choice pending; this is the zero-infra option, swappable later).

Design rules carried over from the engine:
- The LLM only *explains* retrieved passages; it is never the source of truth.
- Every answer carries source citations; if nothing relevant is retrieved, the
  system says so rather than inventing an answer (report §4.4, §8.4).
"""

from .embedder import Embedder, OllamaEmbedder
from .store import VectorStore, Chunk, Retrieved
from .chunk import chunk_text
from .pipeline import KnowledgeBaseA, Answer

__all__ = [
    "Embedder",
    "OllamaEmbedder",
    "VectorStore",
    "Chunk",
    "Retrieved",
    "chunk_text",
    "KnowledgeBaseA",
    "Answer",
]
