"""Text chunking (report §3.1: "chunk by heading/section").

A deliberately simple, deterministic chunker: split on blank lines into
paragraphs, then pack paragraphs into chunks up to a target character budget
with a small overlap so a sentence spanning a boundary is still retrievable.
No tokenizer dependency — character budget is a good-enough proxy locally.
"""

from __future__ import annotations


def chunk_text(
    text: str, *, max_chars: int = 1000, overlap_chars: int = 150
) -> list[str]:
    """Split ``text`` into overlapping chunks of roughly ``max_chars``.

    Paragraphs (blank-line separated) are kept whole where possible. A single
    paragraph longer than ``max_chars`` is hard-split. Overlap is applied
    between consecutive chunks to preserve context across boundaries.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be in [0, max_chars)")

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for para in paragraphs:
        # Hard-split a paragraph that alone exceeds the budget.
        if len(para) > max_chars:
            flush()
            start = 0
            while start < len(para):
                chunks.append(para[start : start + max_chars].strip())
                start += max_chars - overlap_chars
            continue

        if not current:
            current = para
        elif len(current) + 2 + len(para) <= max_chars:
            current = f"{current}\n\n{para}"
        else:
            flush()
            # Seed the next chunk with the tail of the previous one for overlap.
            if overlap_chars and chunks:
                tail = chunks[-1][-overlap_chars:]
                current = f"{tail}\n\n{para}"
            else:
                current = para

    flush()
    return chunks
