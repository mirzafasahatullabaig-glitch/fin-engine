"""RAG tests — fully offline using a deterministic fake embedder.

No Ollama needed: a hashing embedder gives stable, repeatable vectors, and a
fake generator stands in for Granite. This keeps the suite deterministic, the
same way the finance-engine tests avoid external services.
"""

import hashlib

import numpy as np
import pytest

from fin_engine.rag import KnowledgeBaseA, VectorStore, Chunk, chunk_text
from fin_engine.rag.embedder import Embedder


class HashEmbedder:
    """Deterministic bag-of-words embedder for tests.

    Maps each word to a fixed slot in a fixed-dim vector via hashing, so texts
    sharing vocabulary get similar vectors. Not for production — tests only.
    """

    dim = 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = np.zeros(self.dim, dtype=np.float32)
            for word in t.lower().split():
                h = int(hashlib.md5(word.encode()).hexdigest(), 16)
                v[h % self.dim] += 1.0
            out.append(v.tolist())
        return out


def test_hash_embedder_satisfies_protocol():
    assert isinstance(HashEmbedder(), Embedder)


def test_chunking_overlaps_and_covers():
    text = "\n\n".join(f"Paragraph number {i} with some filler words." for i in range(10))
    chunks = chunk_text(text, max_chars=120, overlap_chars=30)
    assert len(chunks) > 1
    assert all(len(c) <= 120 + 30 for c in chunks)  # allow overlap seed


def test_long_paragraph_is_hard_split():
    chunks = chunk_text("x" * 500, max_chars=100, overlap_chars=0)
    assert len(chunks) == 5


def test_ingest_and_retrieve_ranks_relevant_first():
    kb = KnowledgeBaseA(embedder=HashEmbedder())
    kb.ingest_text("Working capital is current assets minus current liabilities.",
                   source="finance_glossary.md")
    kb.ingest_text("Photosynthesis converts sunlight into chemical energy.",
                   source="biology.md")
    hits = kb.retrieve("what is working capital", k=2)
    assert hits[0].chunk.source == "finance_glossary.md"
    assert hits[0].score >= hits[1].score


def test_answer_is_grounded_and_cited():
    kb = KnowledgeBaseA(
        embedder=HashEmbedder(),
        generator=lambda prompt: "Grounded answer [Source 1].",
    )
    kb.ingest_text("Gross profit is revenue minus cost of goods sold.",
                   source="accounting.md")
    ans = kb.answer("define gross profit", k=1)
    assert ans.grounded
    assert "accounting.md" in ans.citations()
    assert ans.text == "Grounded answer [Source 1]."


def test_answer_abstains_when_nothing_relevant():
    """report §4.4/§8.4: report the gap, do not invent an answer."""
    called = []
    kb = KnowledgeBaseA(
        embedder=HashEmbedder(),
        generator=lambda prompt: called.append(prompt) or "should not be called",
        min_score=0.9,  # force everything below threshold
    )
    kb.ingest_text("Unrelated content about gardening.", source="garden.md")
    ans = kb.answer("explain deferred tax liabilities")
    assert not ans.grounded
    assert ans.sources == []
    assert called == []  # generator must NOT run when abstaining


def test_answer_on_empty_store_abstains():
    kb = KnowledgeBaseA(embedder=HashEmbedder(),
                        generator=lambda p: "nope")
    assert not kb.answer("anything").grounded


def test_store_save_load_roundtrip(tmp_path):
    kb = KnowledgeBaseA(embedder=HashEmbedder())
    kb.ingest_text("Revenue is income from sales.", source="a.md")
    p = tmp_path / "index.json"
    kb.store.save(p)

    loaded = VectorStore.load(p)
    assert len(loaded) == len(kb.store)
    qv = HashEmbedder().embed(["revenue"])[0]
    assert loaded.search(qv, k=1)[0].chunk.source == "a.md"


def test_dim_mismatch_rejected():
    store = VectorStore()
    store.add([Chunk("1", "a", "s", {})], [[1.0, 0.0]])
    with pytest.raises(ValueError, match="dim"):
        store.add([Chunk("2", "b", "s", {})], [[1.0, 0.0, 0.0]])
