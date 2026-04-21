import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from parse_candidates import CANDIDATE_HEADER, split_candidates


class TestCandidateHeaderRegex:
    def _match(self, line: str):
        return CANDIDATE_HEADER.match(line.strip())

    # --- formats that already work ---
    def test_bold_bracket(self):
        assert self._match("**Candidate [1]**")

    def test_bold_plain(self):
        assert self._match("**Candidate 1**")

    def test_plain_no_bold(self):
        assert self._match("Candidate 3")

    # --- new formats ---
    def test_markdown_h2(self):
        assert self._match("## Candidate 1"), "## heading not matched"

    def test_markdown_h3(self):
        assert self._match("### Candidate 2"), "### heading not matched"

    def test_colon_suffix(self):
        assert self._match("Candidate 1:"), "colon suffix not matched"

    def test_bold_colon(self):
        assert self._match("**Candidate 1**:"), "bold + colon not matched"

    def test_h2_colon(self):
        assert self._match("## Candidate 3:"), "## + colon not matched"

    def test_captures_number(self):
        m = self._match("## Candidate 42:")
        assert m and m.group(1) == "42"

    def test_does_not_match_random_text(self):
        assert not self._match("This is a sentence about candidates.")

    def test_does_not_match_partial(self):
        assert not self._match("  some text Candidate 1 in middle")


class TestSplitCandidates:
    def test_bold_bracket_format(self):
        raw = "**Candidate [1]**\nContent one.\n\n**Candidate [2]**\nContent two."
        result = split_candidates(raw)
        assert len(result) == 2
        assert result[0][0] == 1
        assert result[1][0] == 2

    def test_markdown_heading_format(self):
        raw = "## Candidate 1\nContent one.\n\n## Candidate 2\nContent two."
        result = split_candidates(raw)
        assert len(result) == 2
        assert result[0][0] == 1

    def test_colon_format(self):
        raw = "Candidate 1:\nBody here.\n\nCandidate 2:\nAnother body."
        result = split_candidates(raw)
        assert len(result) == 2

    def test_empty_raw_returns_empty(self):
        assert split_candidates("") == []

    def test_no_headers_returns_empty(self):
        assert split_candidates("Just some text without any headers.") == []
