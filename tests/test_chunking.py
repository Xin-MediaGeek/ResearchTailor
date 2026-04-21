import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from extract_modules import (
    estimate_tokens,
    split_into_paragraphs,
    pack_paragraphs_into_chunks,
    split_text_into_chunks,
)

DEFAULT_CFG = {
    "max_tokens": 100,
    "overlap_tokens": 20,
    "chars_per_token": 2.5,
    "min_paragraph_tokens": 5,
}


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("", 2.5) == 0

    def test_basic(self):
        assert estimate_tokens("a" * 250, 2.5) == 100

    def test_fractional_rounds_down(self):
        assert estimate_tokens("a" * 251, 2.5) == 100


class TestSplitIntoParagraphs:
    def test_double_newline_splits(self):
        text = "para one\n\npara two\n\npara three"
        result = split_into_paragraphs(text, max_tokens=1000, chars_per_token=2.5)
        assert result == ["para one", "para two", "para three"]

    def test_empty_paragraphs_dropped(self):
        text = "a\n\n\n\nb"
        result = split_into_paragraphs(text, max_tokens=1000, chars_per_token=2.5)
        assert result == ["a", "b"]

    def test_oversized_paragraph_force_split(self):
        long_para = "x" * 600  # 600 chars / 2.5 = 240 tokens > max_tokens=100
        result = split_into_paragraphs(long_para, max_tokens=100, chars_per_token=2.5)
        assert len(result) > 1
        for chunk in result:
            assert estimate_tokens(chunk, 2.5) <= 100

    def test_single_paragraph_under_limit(self):
        text = "short paragraph"
        result = split_into_paragraphs(text, max_tokens=1000, chars_per_token=2.5)
        assert result == ["short paragraph"]


class TestPackParagraphsIntoChunks:
    def test_single_chunk_when_fits(self):
        paras = ["hello world"] * 3
        result = pack_paragraphs_into_chunks(paras, max_tokens=1000, overlap_tokens=10,
                                             chars_per_token=2.5, min_paragraph_tokens=1)
        assert len(result) == 1

    def test_splits_when_overflow(self):
        # Each para ~ 40 tokens (100 chars / 2.5), max=100 → 2 paras per chunk
        paras = ["a" * 100] * 6
        result = pack_paragraphs_into_chunks(paras, max_tokens=100, overlap_tokens=10,
                                             chars_per_token=2.5, min_paragraph_tokens=1)
        assert len(result) >= 3

    def test_overlap_carries_forward(self):
        # Each para: "alpha "*10 = 60 chars = 24 tokens. max=50 fits 2 (48 tok).
        # overlap=25 carries the last para (24 tok) of the closed chunk forward.
        paras = ["alpha " * 10, "beta " * 10, "gamma " * 10, "delta " * 10]
        result = pack_paragraphs_into_chunks(paras, max_tokens=50, overlap_tokens=25,
                                             chars_per_token=2.5, min_paragraph_tokens=1)
        assert len(result) >= 2
        # The last paragraph of chunk 1 should appear at the start of chunk 2
        last_of_chunk1 = result[0].split("\n\n")[-1]
        assert last_of_chunk1 in result[1]

    def test_small_paragraphs_merge(self):
        # 4 tiny paras (< min_paragraph_tokens=5) should merge together
        cfg = {**DEFAULT_CFG, "min_paragraph_tokens": 5}
        paras = ["hi"] * 4
        result = pack_paragraphs_into_chunks(
            paras, max_tokens=cfg["max_tokens"], overlap_tokens=cfg["overlap_tokens"],
            chars_per_token=cfg["chars_per_token"], min_paragraph_tokens=cfg["min_paragraph_tokens"]
        )
        assert len(result) == 1

    def test_empty_input(self):
        result = pack_paragraphs_into_chunks([], max_tokens=100, overlap_tokens=10,
                                             chars_per_token=2.5, min_paragraph_tokens=5)
        assert result == []


class TestSplitTextIntoChunks:
    def test_short_text_single_chunk(self):
        text = "This is a short paper."
        result = split_text_into_chunks(text, DEFAULT_CFG)
        assert result == [text]

    def test_long_text_multiple_chunks(self):
        para = "word " * 60 + "\n\n"  # ~120 tokens per para at chars_per_token=2.5
        text = para * 5
        result = split_text_into_chunks(text, DEFAULT_CFG)
        assert len(result) > 1

    def test_chunks_non_empty(self):
        text = "\n\n".join(["paragraph " * 30] * 10)
        result = split_text_into_chunks(text, DEFAULT_CFG)
        assert all(c.strip() for c in result)

    def test_accepts_chunking_cfg_dict(self):
        cfg = {"max_tokens": 50, "overlap_tokens": 10, "chars_per_token": 2.5, "min_paragraph_tokens": 5}
        text = "a" * 500
        result = split_text_into_chunks(text, cfg)
        assert isinstance(result, list)
