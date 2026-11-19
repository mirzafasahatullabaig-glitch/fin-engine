"""Ingest the PERSONAL reading list (data/reading_list.json) into a RAG index.

    python ingest_reading_list.py          # build + save the index, run sample queries

This is private data (report §3.2): the index is written to data/reading_list.index.json,
which is gitignored. It is kept OUT of the shared KB-A reference store on purpose.

Requires Ollama with nomic-embed-text (embeddings) and granite4.2:8b (answers).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fin_engine.rag import KnowledgeBaseA, OllamaEmbedder

ROOT = Path(__file__).resolve().parent
LIST_PATH = ROOT / "data" / "reading_list.json"
INDEX_PATH = ROOT / "data" / "reading_list.index.json"  # *.index.json is gitignored


def book_to_text(b: dict) -> str:
    """One retrievable passage per book."""
    return (
        f"Book #{b['order']}: {b['book']} by {b.get('author', 'unknown author')}. "
        f"Reason to read: {b['why']}."
    )


def build() -> KnowledgeBaseA:
    data = json.loads(LIST_PATH.read_text(encoding="utf-8"))
    kb = KnowledgeBaseA(embedder=OllamaEmbedder())  # nomic-embed-text

    for b in data["books"]:
        # One book == one chunk: don't let the chunker merge/split them.
        kb.ingest_text(
            book_to_text(b),
            source="reading_list",
            metadata={"order": b["order"], "book": b["book"],
                      "author": b.get("author", "")},
            max_chars=2000,  # comfortably larger than any single entry
        )
    kb.store.save(INDEX_PATH)
    print(f"Ingested {len(kb.store)} books -> {INDEX_PATH}")
    return kb


def main() -> None:
    kb = build()

    for q in [
        "Which book is about making decisions under uncertainty?",
        "What should I read to think strategically about a business?",
        "Which book explains the psychology behind mistakes?",
    ]:
        print(f"\nQ: {q}")
        for r in kb.retrieve(q, k=2):
            print(f"   [{r.score:.3f}] {r.chunk.metadata['book']}")
        ans = kb.answer(q, k=3)
        print(f"A: {ans.text.strip()}")


if __name__ == "__main__":
    main()
