"""`rediacc_ci.quality.content_quality` against the shell it replaces.

WHAT IS WORTH TESTING HERE, and it is not "does it find the phrase". The shadow ledger `.ci/shadow/w7p2-content-quality.observations.jsonl` drives the whole gate end to end over five distinct trees. What a ledger row cannot isolate is the three pieces of shell that decide WHICH LINES ARE EVEN LOOKED AT, each of which can narrow silently and leave the gate green:

  * the awk exemption program, five rules whose ORDER is the semantics
  * `${line// /}`, which deletes spaces and not whitespace, and therefore
    decides which lines of the .conf load as patterns
  * `${#p}` and `${line_text:0:117}`, which count BYTES under LC_ALL=C and
    CHARACTERS under a UTF-8 locale

So every case below runs the REAL awk or the REAL bash and compares. A test that only asserted against the Python would agree with a port that had quietly widened the frontmatter rule to swallow the whole document.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.quality import content_quality as cq
from rediacc_ci.tests import differential as diff


def _joined(*rows: str) -> str:
    """`"\n".join(rows)` behind a call. The rows stay one per line.

    A helper rather than a literal join because ruff's FLY002 rewrites a join over a LITERAL list into an f-string, and a ten-line shell fixture written as one f-string is unreadable. Passing the rows as arguments keeps the fixture legible and gives the linter nothing static to fold.
    """
    return "\n".join(rows)


# The exemption program, verbatim from check-content-quality.sh:111-118. Copied rather than read out of the file so a rewrite of the twin shows up here as a failing comparison instead of as a silently-updated expectation.
AWK_EXEMPT = r"""awk '
        BEGIN { fm=0; cb=0 }
        /^---$/ && cb==0 { fm++; if (fm<=2) { print NR; next } }
        fm==1 { print NR; next }
        /^```/ { cb=1-cb; print NR; next }
        cb==1 { print NR; next }
        /<!-- slop-ok -->/ { print NR; next }
    ' """


def _bash_exempt(tmp_path: pathlib.Path, text: str) -> set[int]:
    """The line numbers the twin's awk marks exempt, for `text`."""
    target = tmp_path / "doc.md"
    target.write_text(text, encoding="utf-8")
    # The filename is appended rather than interpolated into the awk text so the program below reads exactly as it does in the twin, with no trailing quote gymnastics between the closing `'` and the argument.
    code, out, err = diff.bash_streams(AWK_EXEMPT + '"%s"' % target, cwd=str(tmp_path))
    assert err == "", err
    assert code == 0, code
    return {int(line) for line in out.split("\n") if line.strip()}


DOC = _joined(
    "---",
    "title: at its core",
    "---",
    "prose at its core",
    "```bash",
    "at its core",
    "```",
    "at its core <!-- slop-ok -->",
    "at its core",
    "---",
    "at its core",
    "",
)


def test_exempt_lines_match_the_twins_awk(tmp_path: pathlib.Path) -> None:
    assert cq.exempt_lines(DOC) == _bash_exempt(tmp_path, DOC)


def test_a_third_dash_rule_is_not_frontmatter(tmp_path: pathlib.Path) -> None:
    """The rule most likely to be "simplified" into exempting everything after
    the second `---`. Both implementations must leave lines 10 and 11 alone."""
    got = cq.exempt_lines(DOC)
    assert got == _bash_exempt(tmp_path, DOC)
    assert 10 not in got
    assert 11 not in got


def test_an_unterminated_fence_swallows_the_rest(tmp_path: pathlib.Path) -> None:
    """A document whose fence never closes exempts everything after it. That is
    a real blind spot in the gate, and the port must have exactly the same one
    rather than a narrower or a wider version of it."""
    text = "at its core\n```\nat its core\nat its core\n"
    assert cq.exempt_lines(text) == _bash_exempt(tmp_path, text) == {2, 3, 4}


def test_frontmatter_inside_a_fence_is_not_frontmatter(tmp_path: pathlib.Path) -> None:
    """`cb==0` guards the `---` rule, so a `---` inside a code fence does not
    open a frontmatter block. Losing that guard would exempt the whole tail."""
    text = "a\n```\n---\n```\nat its core\n"
    assert cq.exempt_lines(text) == _bash_exempt(tmp_path, text)


def test_blank_is_spaces_only_not_whitespace() -> None:
    """`${line// /}` deletes SPACE. A tab-only line survives as a pattern, which
    is the twin's behaviour and is asserted against the real bash."""
    code, out, err = diff.bash_streams(
        'line="$(printf "\\t")"; if [[ -z "${line// /}" ]]; then echo BLANK; else echo PATTERN; fi'
    )
    assert (code, err) == (0, "")
    assert out.strip() == "PATTERN"
    assert cq.load_patterns("# [ERROR]\n\t\n")[0] == ["\t"]

    code, out, err = diff.bash_streams(
        'line="   "; if [[ -z "${line// /}" ]]; then echo BLANK; else echo PATTERN; fi'
    )
    assert (code, err) == (0, "")
    assert out.strip() == "BLANK"
    assert cq.load_patterns("# [ERROR]\n   \n")[0] == []


def test_the_real_patterns_file_loads_into_two_non_empty_lists() -> None:
    """ZERO PATTERNS IS A GATE THAT CANNOT FIRE. The twin has no floor on this
    and would print "Loaded 0 error patterns" and pass every file, so the count
    is asserted here rather than left to a reader noticing the banner."""
    text = cq.read_text(paths.repo_root() / cq.PATTERNS_FILE)
    errors, warns = cq.load_patterns(text)
    assert len(errors) >= 30, errors
    assert len(warns) >= 1, warns
    assert "\u2014" in errors, "the em dash pattern is the one this repo cares about most"


def test_short_is_measured_in_bytes_under_lc_all_c() -> None:
    """`${#p}` on a three-byte em dash. The differential pins LC_ALL=C, so the
    twin sees 3 there; a UTF-8 locale would say 1. Both take the fast path, and
    the point of the assertion is that the DIVERGENCE is pinned rather than
    discovered later."""
    code, out, err = diff.bash_streams('p="\u2014"; echo "${#p}"')
    assert (code, err) == (0, "")
    assert out.strip() == "3", "LC_ALL=C should count bytes"
    assert len("\u2014".encode()) == 3
    assert cq.identify_pattern("a \u2014 b", ["\u2014"]) == "\u2014"


def test_truncation_cuts_the_same_bytes_bash_cuts() -> None:
    """A 129-byte line whose 118th byte is in the middle of an em dash.

    COMPARED AS HEX, not as text. Bash's output here is not valid UTF-8 by
    construction, and `subprocess` with `text=True` raises UnicodeDecodeError on
    it -- which would make the test fail for a reason that has nothing to do
    with the port. `od` moves the comparison onto bytes, where it belongs.
    """
    text = "x" * 116 + "\u2014" + "y" * 10
    code, out, err = diff.bash_streams(
        'line="%s"; if [[ ${#line} -gt 120 ]]; then line="${line:0:117}..."; fi; '
        'printf "%%s" "$line" | od -An -v -tx1 | tr -d " \\n"' % text
    )
    assert (code, err) == (0, "")
    assert cq.truncate(text).encode("utf-8", "surrogateescape").hex() == out.strip()


def test_identify_pattern_prefers_the_short_pattern_regardless_of_order() -> None:
    """Two full passes, not one. Reversing the list must not change the answer."""
    patterns = ["in the world of", "\u2014"]
    assert cq.identify_pattern("\u2014 in the world of x", patterns) == "\u2014"
    assert cq.identify_pattern("\u2014 in the world of x", list(reversed(patterns))) == "\u2014"


def test_the_fast_path_is_case_sensitive_and_can_report_unknown() -> None:
    """The twin's asymmetry, preserved: grep matched it, the reporter cannot
    name it. A port that "fixed" this would print a different Pattern: line."""
    assert cq.grep_in_file("AB x\n", "ab") == [(1, "AB x")]
    assert cq.identify_pattern("AB x", ["ab"]) == "(unknown)"


def test_selftest_is_green() -> None:
    assert cq.selftest() == 0


def test_the_real_tree_is_clean() -> None:
    """The gate against the actual repository. If this ever reds, the finding is
    real content debt rather than a broken port."""
    assert cq.main([]) == 0
