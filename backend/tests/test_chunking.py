"""
tests/test_chunking.py — Unit tests for rag/chunking.py

Verifies chunk size limits, overlap, metadata preservation, edge cases.
"""

import pytest
from app.rag.parsing import ParsedBlock, ParsedDocument
from app.rag.chunking import chunk_document
from app.core.config import settings


def _doc_from_blocks(blocks: list[tuple]) -> ParsedDocument:
    """Helper: list of (page_number, section_title, text)"""
    d = ParsedDocument()
    for pn, sec, txt in blocks:
        d.blocks.append(ParsedBlock(page_number=pn, section_title=sec, text=txt))
    return d


def _doc(text: str, page: int = 1, section: str = "Section") -> ParsedDocument:
    return _doc_from_blocks([(page, section, text)])


class TestChunkSizeLimits:
    def test_short_text_is_one_chunk(self):
        d = _doc("Hello world.")
        chunks = chunk_document(d)
        assert len(chunks) == 1

    def test_long_text_split_into_multiple(self):
        # Create text definitely larger than CHUNK_SIZE
        long_text = ("word " * 300).strip()
        d = _doc(long_text)
        chunks = chunk_document(d)
        assert len(chunks) > 1
        for c in chunks:
            assert c.char_count <= settings.CHUNK_SIZE + settings.CHUNK_OVERLAP + 50

    def test_no_empty_chunks(self):
        long_text = ("sentence. " * 100).strip()
        d = _doc(long_text)
        chunks = chunk_document(d)
        assert all(c.text.strip() for c in chunks)
        assert all(c.char_count > 0 for c in chunks)

    def test_very_long_word_still_split(self):
        """A single token longer than CHUNK_SIZE must still be chunked (not dropped)."""
        long_word = "X" * (settings.CHUNK_SIZE * 3)
        d = _doc(long_word)
        chunks = chunk_document(d)
        # All characters must be present
        total = "".join(c.text for c in chunks)
        # Allow for overlap duplication; the original content must appear
        assert long_word in total or len(total) >= len(long_word)


class TestOverlap:
    def test_overlap_tail_in_next_chunk(self):
        # Build text with clearly distinct paragraphs
        overlap = settings.CHUNK_OVERLAP
        para_a = "AAAA " * (settings.CHUNK_SIZE // 5)
        para_b = "BBBB " * (settings.CHUNK_SIZE // 5)
        para_c = "CCCC " * (settings.CHUNK_SIZE // 5)
        d = _doc(f"{para_a}\n\n{para_b}\n\n{para_c}")
        chunks = chunk_document(d)
        if len(chunks) >= 2:
            # The tail of chunk[0] should appear somewhere in chunk[1]
            tail = chunks[0].text[-overlap:].strip()
            if tail:
                assert tail in chunks[1].text


class TestMetadataPreservation:
    def test_page_number_preserved(self):
        d = _doc("Some text here.", page=7, section="Chapter 7")
        chunks = chunk_document(d)
        assert all(c.page_number == 7 for c in chunks)

    def test_section_title_preserved(self):
        d = _doc("Some text here.", section="Introduction")
        chunks = chunk_document(d)
        assert all(c.section_title == "Introduction" for c in chunks)

    def test_chunk_index_sequential(self):
        long_text = ("paragraph. " * 200).strip()
        d = _doc(long_text)
        chunks = chunk_document(d)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))


class TestSectionBoundaries:
    def test_different_sections_not_merged(self):
        d = _doc_from_blocks([
            (1, "Section A", "text A"),
            (2, "Section B", "text B"),
        ])
        chunks = chunk_document(d)
        # Chunks should preserve section boundaries
        section_a_chunks = [c for c in chunks if c.section_title == "Section A"]
        section_b_chunks = [c for c in chunks if c.section_title == "Section B"]
        assert len(section_a_chunks) >= 1
        assert len(section_b_chunks) >= 1
        # text A must not appear in a Section B chunk
        for c in section_b_chunks:
            assert "text A" not in c.text

    def test_same_section_merged_up_to_chunk_size(self):
        """Small adjacent blocks in the same section should be merged."""
        d = _doc_from_blocks([
            (1, "Intro", "short text one."),
            (1, "Intro", "short text two."),
        ])
        chunks = chunk_document(d)
        # Both should end up in a single chunk since they're small
        assert len(chunks) == 1
        assert "short text one" in chunks[0].text
        assert "short text two" in chunks[0].text

    def test_docx_no_page_number(self):
        d = _doc_from_blocks([
            (None, "Intro", "DOCX text with no page number."),
        ])
        chunks = chunk_document(d)
        assert all(c.page_number is None for c in chunks)


class TestDeterminism:
    def test_same_input_same_output(self):
        text = ("The quick brown fox. " * 50).strip()
        d1 = _doc(text)
        d2 = _doc(text)
        chunks1 = chunk_document(d1)
        chunks2 = chunk_document(d2)
        assert [c.text for c in chunks1] == [c.text for c in chunks2]


class TestSectionBugFix:
    """
    Regression tests for the section-title assignment bug.

    When a page (or block) contains a heading that appears AFTER some body text,
    the body text that precedes the heading must NOT be tagged with that heading.
    Only text that starts AFTER a heading is active should carry that heading.
    """

    def test_text_before_heading_does_not_get_later_heading(self):
        """
        Simulate what the fixed PDF parser produces: two sub-blocks on the same page.
          sub-block 1: section=None,          text='PRIVACY POLICY ...'
          sub-block 2: section='Information We Collect', text='Information We Collect\n...'
        Chunk 0 must NOT have section_title='Information We Collect'.
        """
        # Build the already-split blocks that the fixed parser would emit.
        d = _doc_from_blocks([
            (1, None,                   "PRIVACY POLICY This document explains our practices."),
            (1, "Information We Collect", "Information We Collect\nWe collect your name and email."),
        ])
        chunks = chunk_document(d)
        # The first chunk must come from the first block (no section yet).
        first_chunk = chunks[0]
        assert first_chunk.section_title is None, (
            f"Expected section_title=None for text before the first heading, "
            f"got {first_chunk.section_title!r}"
        )
        # Chunks from the second block must carry the heading.
        second_section_chunks = [c for c in chunks if c.section_title == "Information We Collect"]
        assert second_section_chunks, "Expected at least one chunk with 'Information We Collect'"
        for c in second_section_chunks:
            assert "PRIVACY POLICY" not in c.text, (
                "Text before the heading leaked into a chunk tagged with the later heading"
            )

    def test_body_text_gets_preceding_heading_not_following(self):
        """
        Page layout: Heading A → body → Heading B → body
        Body text between A and B must have section='Heading A'.
        Body text after Heading B must have section='Heading B'.
        """
        d = _doc_from_blocks([
            (1, "Heading A", "Heading A\nThis is the body under A."),
            (1, "Heading B", "Heading B\nThis is the body under B."),
        ])
        chunks = chunk_document(d)
        for c in chunks:
            if "body under A" in c.text:
                assert c.section_title == "Heading A", (
                    f"Body under A got wrong section: {c.section_title!r}"
                )
            if "body under B" in c.text:
                assert c.section_title == "Heading B", (
                    f"Body under B got wrong section: {c.section_title!r}"
                )


class TestOverlapWordBoundary:
    """
    Regression tests for the overlap word-boundary bug.
    Overlap must never start mid-word (e.g. 'tivate' instead of 'activate').
    """

    def test_overlap_starts_at_word_boundary(self):
        """
        Force two chunks, then verify that the overlap prefix in chunk[1]
        does not start in the middle of a word from chunk[0].
        """
        # Build a text long enough to produce at least 2 chunks.
        # Use clearly distinct words so we can detect mid-word cuts.
        chunk_size = settings.CHUNK_SIZE
        overlap = settings.CHUNK_OVERLAP

        # Each word is 10 chars; fill > CHUNK_SIZE to guarantee a split.
        words = [f"wordnum{i:03d}" for i in range(chunk_size // 10 + 20)]
        long_text = " ".join(words)
        d = _doc(long_text)
        chunks = chunk_document(d)

        assert len(chunks) >= 2, "Need at least 2 chunks to test overlap"

        for i in range(1, len(chunks)):
            text = chunks[i].text
            # The overlap portion is the first few characters of this chunk
            # (before the original chunk[i] content).  Whatever it starts with
            # must be a complete word that also exists in chunks[i-1].
            first_token = text.split()[0]
            # It must be a full word (matches one of our word tokens exactly).
            assert first_token in long_text.split(), (
                f"Chunk {i} starts with {first_token!r} which is not a complete "
                f"word from the original text — mid-word overlap detected."
            )

    def test_overlap_no_mid_word_cut_on_exact_boundary(self):
        """
        Directly test _add_overlap: if the overlap slice cuts into a word, the
        returned prefix must start at a word boundary.

        Setup:
          chunk_a ends with "...activate softcomputing"
          overlap=10  →  raw_tail = "tcomputing"  (no whitespace → all mid-word)

        Expected behaviour: since the entire tail is inside one word, no overlap
        prefix is prepended (omit rather than emit a partial word).
        chunk[1] in the result must therefore start with the first token of chunk_b.
        """
        from app.rag.chunking import _add_overlap

        chunk_a = "some prefix text activate softcomputing"
        chunk_b = "next section of text goes here now"
        result = _add_overlap([chunk_a, chunk_b], overlap=10)
        # chunk_b is result[1]; it must not start with a mid-word fragment.
        first_word = result[1].split()[0]
        assert first_word in chunk_a.split() or first_word in chunk_b.split(), (
            f"result[1] starts with {first_word!r}, which is not a complete word "
            f"from either chunk."
        )
        # More specifically: "tcomputing" must NOT appear at the start.
        assert not result[1].startswith("tcomputing"), (
            "Mid-word fragment 'tcomputing' leaked into the overlap prefix."
        )
