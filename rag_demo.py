"""Knowledge Base A (general docs RAG) demo.

    python rag_demo.py

Ingests the sample reference glossary, then answers questions. Requires a
running Ollama with the embedding and generation models:

    ollama pull nomic-embed-text
    ollama pull granite4.2:8b
    ollama serve            # if not already running

Retrieval alone (the first block) works without the generation model; only the
final answer step calls granite4.2:8b.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fin_engine.rag import KnowledgeBaseA, OllamaEmbedder

SAMPLE = Path(__file__).resolve().parent / "data" / "kb_a_sample"


def main() -> None:
    kb = KnowledgeBaseA(embedder=OllamaEmbedder())  # nomic-embed-text

    n = 0
    for md in sorted(SAMPLE.glob("*.md")):
        n += kb.ingest_file(md)
    print(f"Ingested {n} chunks from {SAMPLE}\n")

    questions = [
        "What is working capital?",
        "Why is PBT not the same as EBIT?",
        "Where does a bank loan appear in the cash-flow statement?",
    ]

    for q in questions:
        print(f"Q: {q}")
        # Show retrieval first (no LLM needed).
        for r in kb.retrieve(q, k=2):
            print(f"   [{r.score:.3f}] {r.chunk.source}: {r.chunk.text[:70]}...")
        # Then the grounded answer (calls granite4.2:8b).
        ans = kb.answer(q, k=3)
        tag = "" if ans.grounded else "  (abstained)"
        print(f"A:{tag} {ans.text.strip()}")
        if ans.grounded:
            print(f"   sources: {', '.join(ans.citations())}")
        print()


if __name__ == "__main__":
    main()
