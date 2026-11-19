"""Text chunking (report §3.1: "chunk by heading/section").

A deliberately simple, deterministic chunker. For markdown it splits on headings
first so each ``#``/``##``/``###`` section becomes its own chunk (sections
retrieve far more precisely than one blob), then packs paragraphs within a
section up to a character budget with a small overlap. No tokenizer dependency
— character budget is a good-enough proxy locally.
"""

from __future__ import annotations

import re

_HEADING = re.compile(r"^#{1,6}[ \t]+\S", re.MULTILINE)


def _split_markdown_sections(text: str) -> list[str]:
    """Split markdown into sections, each starting at a heading line.

    Text before the first heading (if any) is its own leading section. A
    document with no headings returns a single section (the whole text).
    """
    starts = [m.start() for m in _HEADING.finditer(text)]
    if not starts:
        return [text]
    bounds = ([0] if starts[0] != 0 else []) + starts + [len(text)]
    bounds = sorted(set(bounds))
    sections = [text[bounds[i] : bounds[i + 1]] for i in range(len(bounds) - 1)]
    return [s for s in sections if s.strip()]


def chunk_text(
    text: str, *, max_chars: int = 1000, overlap_chars: int = 150
) -> list[str]:
    """Split ``text`` into chunks, heading-aware for markdown.

    Each markdown section is chunked independently so sections never bleed into
    one another. Within a section, paragraphs are packed up to ``max_chars``
    with overlap; a single paragraph longer than ``max_chars`` is hard-split.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be in [0, max_chars)")

    chunks: list[str] = []
    for section in _split_markdown_sections(text):
        chunks.extend(_chunk_section(section, max_chars, overlap_chars))
    return chunks


def _chunk_section(text: str, max_chars: int, overlap_chars: int) -> list[str]:
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
