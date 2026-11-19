"""Knowledge Base A pipeline: ingest documents, retrieve, answer with citations.

The generation step is optional and pluggable. By default it builds a grounded
prompt and calls ``granite4.2:8b`` via Ollama, but a caller can pass any
``generate`` callable (tests pass a fake), and retrieval works with no LLM at
all — useful for evaluating retrieval quality on its own.
"""

from __future__ import annotations

import json
import re
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

# Small models sometimes echo the literal citation template from the prompt
# ("[Source N]") or leave an empty "[Source ]" marker. Strip those artifacts
# deterministically rather than hoping prompt-tuning suppresses them.
_CITATION_ARTIFACT = re.compile(r"\[\s*Source\s*(?:N|n|\d*)\s*\]")


# Reasoning models (Granite 4.2 included) sometimes emit a <think>...</think>
# block, or a stray closing </think>, even with think=False. Strip it.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_STRAY_THINK = re.compile(r"</?think>", re.IGNORECASE)


def _clean_answer(text: str) -> str:
    """Remove think-tags and placeholder citation markers; keep real citations.

    Drops ``<think>…</think>`` reasoning blocks, ``[Source N]`` (literal
    template) and ``[Source ]`` (empty); leaves numbered citations intact.
    """
    def keep_numbered(m: re.Match) -> str:
        inner = m.group(0)
        return inner if re.search(r"\d", inner) else ""

    cleaned = _THINK_BLOCK.sub("", text)
    cleaned = _STRAY_THINK.sub("", cleaned)
    cleaned = _CITATION_ARTIFACT.sub(keep_numbered, cleaned)
    # Tidy artifacts left behind by the removal.
    cleaned = re.sub(r"\(\s*\)", "", cleaned)               # empty parens "()"
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)            # runs of spaces
    cleaned = re.sub(r" +([.,;:])", r"\1", cleaned)         # space before punct
    # Collapse orphaned sentence punctuation, e.g. "[1]. ." -> "[1]."
    cleaned = re.sub(r"([.,;:])(\s*[.,;:])+", r"\1", cleaned)
    return cleaned.strip()

# Below this cosine score, retrieved context is treated as irrelevant and the
# pipeline abstains rather than answering (report §4.4 / §8.4).
#
# Tuned against nomic-embed-text: off-topic queries floor around 0.40-0.43
# (every text has some similarity), while genuine hits land at 0.70+. 0.5 sits
# in the gap — above the noise floor, below real matches. Retune if the
# embedding model changes.
DEFAULT_MIN_SCORE = 0.5


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


# Ingested documents are UNTRUSTED (report §9.2). Neutralise common
# prompt-injection phrasing so a poisoned source cannot hijack the model. This
# is defence-in-depth alongside the grounding prompt, not a complete guarantee.
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\b.*", re.I),
    re.compile(r"\byou\s+are\s+now\b.*", re.I),
    re.compile(r"\bsystem\s+prompt\b", re.I),
    re.compile(r"do\s+not\s+cite\s+(any\s+)?sources?", re.I),
    re.compile(r"reply\s+(only\s+)?(with|exactly)\b.*", re.I),
    re.compile(r"\bsend\s+(all\s+)?.*\bto\b\s+\S+@\S+", re.I),
]


def sanitize_ingest(text: str) -> str:
    """Strip imperative prompt-injection phrases from untrusted document text.

    Replaces matched spans with a visible ``[removed: possible injection]``
    marker so the content is not silently altered and the redaction is auditable.
    """
    for pat in _INJECTION_PATTERNS:
        text = pat.sub("[removed: possible injection]", text)
    return text


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
        """Chunk, embed and store a document. Returns the number of chunks.

        Ingested text is sanitised for prompt-injection phrasing first (§9.2).
        """
        text = sanitize_ingest(text)
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
        text = _clean_answer(gen(_build_prompt(question, relevant)))
        return Answer(text=text, sources=relevant, grounded=True)
