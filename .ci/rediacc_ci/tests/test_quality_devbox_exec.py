"""`rediacc_ci.quality.devbox_exec` over core/devbox.py: the detectors in both directions and the live subject.

The detectors are small regexes where a widening costs the gate its life: an over-broad B1 fails the file it protects, an over-narrow `SITE_RE` trips the floor or hides a collapsed enumeration, and `code_of` is what keeps a scan from firing on its own documentation.
"""

from rediacc_ci import paths
from rediacc_ci.quality import devbox_exec as dx

BAD = (
    'self.run([d, "exec"])',
    "x = [words]",
    "[ words , 1]",
)
GOOD = (
    'self.run([*d, "exec", "-u", "vscode"])',
    'self.run([*words, *flags, cid, "bash"])',
    'self.run(["echo", d])',
    "d = self.docker_words()",
)


def test_bug_re_flags_every_single_element_shape() -> None:
    for line in BAD:
        assert dx.find(dx.BUG_RE, line + "\n"), line


def test_bug_re_passes_every_splatted_shape() -> None:
    for line in GOOD:
        assert dx.find(dx.BUG_RE, line + "\n") == [], line


def test_bug_re_spans_lines() -> None:
    assert dx.find(dx.BUG_RE, "run(\n    [\n        d,\n        x,\n    ]\n)\n") == ["2:    ["]


def test_numeric_re_both_directions() -> None:
    assert dx.find(dx.NUMERIC_RE, '["exec", "-u", uid]\n')
    assert dx.find(dx.NUMERIC_RE, '["exec", "-u", "vscode"]\n') == []
    assert dx.find(dx.NUMERIC_RE, '"-u",\n    "vscode",\n') == []


def test_site_re_counts_splat_lines() -> None:
    assert dx.count(dx.SITE_RE, "[*d, 1]\n[*words]\nplain\n") == 2


def test_code_of_blanks_comments_and_keeps_numbering() -> None:
    text = '# a\n   # b\nkept # tail\nrun([d, "x"])\n'
    assert dx.code_of(text).split("\n")[:3] == ["", "", "kept # tail"]
    assert dx.find(dx.BUG_RE, dx.code_of(text)) == ['4:run([d, "x"])']


def test_the_real_devbox_file_is_scanned_and_clean() -> None:
    """A green over ZERO sites would be the vacuity the floor exists for, so the count is asserted too."""
    code = dx.code_of(paths.from_root(dx.DEVBOX_REL).read_text(encoding="utf-8"))
    assert dx.find(dx.BUG_RE, code) == []
    assert dx.find(dx.NUMERIC_RE, code) == []
    assert dx.count(dx.SITE_RE, code) >= dx.MIN_SITES


def test_selftest_runs_and_meets_its_floor() -> None:
    assert dx.selftest() == 0
