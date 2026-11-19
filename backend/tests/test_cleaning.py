"""
tests/test_cleaning.py — Unit tests for rag/cleaning.py

Each test verifies a specific cleaning rule with before/after examples.
"""

import pytest
from app.rag.parsing import ParsedBlock, ParsedDocument
from app.rag.cleaning import clean_document, HEADER_FOOTER_THRESHOLD


def _doc(*texts, page_numbers=None) -> ParsedDocument:
    d = ParsedDocument()
    for i, text in enumerate(texts):
        pn = page_numbers[i] if page_numbers else (i + 1)
        d.blocks.append(ParsedBlock(page_number=pn, section_title=None, text=text))
    return d


class TestHyphenFix:
    def test_hyphenated_linebreak_joined(self):
        d = _doc("manage-\nment is key")
        result = clean_document(d)
        assert "management" in result.blocks[0].text

    def test_non_hyphen_linebreak_preserved(self):
        d = _doc("line one\nline two")
        result = clean_document(d)
        assert "line one" in result.blocks[0].text
        assert "line two" in result.blocks[0].text


class TestWhitespaceNormalisation:
    def test_multiple_spaces_collapsed(self):
        d = _doc("hello    world")
        result = clean_document(d)
        assert "hello world" in result.blocks[0].text

    def test_tabs_replaced(self):
        d = _doc("col1\t\tcol2")
        result = clean_document(d)
        assert "\t" not in result.blocks[0].text

    def test_excessive_newlines_collapsed(self):
        d = _doc("para one\n\n\n\n\npara two")
        result = clean_document(d)
        assert "\n\n\n" not in result.blocks[0].text


class TestEmptyBlockDropped:
    def test_whitespace_only_block_removed(self):
        d = _doc("   \n\t  ", "real content")
        result = clean_document(d)
        assert len(result.blocks) == 1
        assert result.blocks[0].text == "real content"


class TestHeaderFooterRemoval:
    def test_repeated_short_line_removed(self):
        # Same footer on pages 1–5 (5/5 = 100% ≥ threshold)
        texts = [f"body text page {i}\nPage {i} of 5" for i in range(1, 6)]
        page_nums = list(range(1, 6))
        d = _doc(*texts, page_numbers=page_nums)
        result = clean_document(d)
        # "Page X of 5" varies per page so won't be removed (each is unique)
        # Test with truly identical footer
        d2 = ParsedDocument()
        for i in range(1, 6):
            d2.blocks.append(ParsedBlock(
                page_number=i,
                section_title=None,
                text=f"Real content for section {i}\nCOMPANY CONFIDENTIAL",
            ))
        result2 = clean_document(d2)
        for block in result2.blocks:
            assert "COMPANY CONFIDENTIAL" not in block.text

    def test_long_line_not_removed_as_footer(self):
        # Lines > HEADER_FOOTER_MAX_LEN are never treated as headers/footers
        long_line = "A" * 100
        texts = [f"body\n{long_line}" for _ in range(1, 6)]
        page_nums = list(range(1, 5))
        d = ParsedDocument()
        for i in range(1, 5):
            d.blocks.append(ParsedBlock(page_number=i, section_title=None, text=f"body\n{long_line}"))
        result = clean_document(d)
        # Long line should still be present
        assert any(long_line in b.text for b in result.blocks)


class TestDocxNoPageNumbers:
    def test_docx_blocks_no_page_number_cleaned(self):
        d = ParsedDocument()
        d.blocks.append(ParsedBlock(page_number=None, section_title="Intro", text="  hello   world  "))
        result = clean_document(d)
        assert result.blocks[0].text == "hello world"
