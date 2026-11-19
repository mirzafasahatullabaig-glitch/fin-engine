"""Knowledge Base A pipeline: ingest documents, retrieve, answer with citations.

The generation step is optional and pluggable. By default it builds a grounded
prompt and calls ``granite4.2:8b`` via Ollama, but a caller can pass any
``generate`` callable (tests pass a fake), and retrieval works with no LLM at
all — useful for evaluating retrieval quality on its own.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .chunk import chunk_text
from .embedder import Embedder
from .store import Chunk, Retrieved, VectorStore

# A generator takes a fully-formed prompt and returns the model's text.
Generator = Callable[[str], str]

# Below this cosine score, retrieved context is treated as irrelevant and the
# pipeline abstains rather than answering (report §4.4 / §8.4).
DEFAULT_MIN_SCORE = 0.3


@dataclass(frozen=True)
class Answer:
    """A grounded answer plus the sources it was built from."""

    text: str
    sources: list[Retrieved]
    grounded: bool  # False when the pipeline abstained for lack of relevant context

    def citations(self) -> list[str]:
        seen: list[str] = []
        for r in self.sources:
            if r.chunk.source not in seen:
                seen.append(r.chunk.source)
        return seen


def _build_prompt(question: str, sources: list[Retrieved]) -> str:
    context = "\n\n".join(
        f"[Source {i + 1}: {r.chunk.source}]\n{r.chunk.text}"
        for i, r in enumerate(sources)
    )
    return (
        "You are a business-knowledge assistant. Answer the question using ONLY "
        "the sources below. Cite sources as [Source N]. If the sources do not "
        "contain the answer, say you don't have enough information.\n\n"
        f"=== SOURCES ===\n{context}\n\n"
        f"=== QUESTION ===\n{question}\n\n=== ANSWER ===\n"
    )


def _ollama_generate(
    prompt: str,
    model: str = "granite4.2:8b",
    host: str = "http://localhost:11434",
    timeout: float = 120.0,
) -> str:
    payload = json.dumps(
        {"model": model, "prompt": prompt, "stream": False, "think": False}
    ).encode()
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode()).get("response", "")
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach Ollama at {host} for model '{model}'. "
            f"Is it running? (ollama pull {model})"
        ) from exc


@dataclass
class KnowledgeBaseA:
    """General business-knowledge RAG over a NumPy vector store."""

    embedder: Embedder
    store: VectorStore = field(default_factory=VectorStore)
    generator: Generator | None = None  # None -> default Ollama granite4.2:8b
    min_score: float = DEFAULT_MIN_SCORE

    def ingest_text(
        self, text: str, *, source: str, metadata: dict | None = None,
        max_chars: int = 1000, overlap_chars: int = 150,
    ) -> int:
        """Chunk, embed and store a document. Returns the number of chunks."""
        pieces = chunk_text(text, max_chars=max_chars, overlap_chars=overlap_chars)
        if not pieces:
            return 0
        meta = metadata or {}
        chunks = [
            Chunk(id=f"{source}#{i}", text=p, source=source, metadata=meta)
            for i, p in enumerate(pieces)
        ]
        vectors = self.embedder.embed([c.text for c in chunks])
        self.store.add(chunks, vectors)
        return len(chunks)

    def ingest_file(self, path: str | Path, **kwargs) -> int:
        """Ingest a UTF-8 text/markdown file (source defaults to the file name)."""
        p = Path(path)
        kwargs.setdefault("source", p.name)
        return self.ingest_text(p.read_text(encoding="utf-8"), **kwargs)

    def retrieve(self, question: str, k: int = 4) -> list[Retrieved]:
        qv = self.embedder.embed([question])[0]
        return self.store.search(qv, k=k)

    def answer(self, question: str, k: int = 4) -> Answer:
        """Retrieve context and generate a grounded, cited answer.

        Abstains (``grounded=False``) when the best retrieved chunk scores below
        ``min_score`` — the engine reports the gap instead of inventing a value.
        """
        hits = self.retrieve(question, k=k)
        relevant = [h for h in hits if h.score >= self.min_score]
        if not relevant:
            return Answer(
                text="I don't have enough relevant information in the knowledge "
                     "base to answer that.",
                sources=[],
                grounded=False,
            )
        gen = self.generator or _ollama_generate
        text = gen(_build_prompt(question, relevant))
        return Answer(text=text, sources=relevant, grounded=True)
