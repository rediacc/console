"""`rediacc_ci.quality.devbox_exec` against the grep it replaced.

WHAT IS WORTH TESTING HERE. The shadow ledger `.ci/shadow/w7p2-devbox-exec.observations.jsonl` drives the whole gate over five distinct trees, but this gate emits exactly ONE finding line -- its failure count -- because every per-assertion line is unmarked and reads as progress. So a ledger row proves the counts agree and says nothing about WHICH assertion fired.

The interesting content is therefore entirely in three greps, and all three are patterns where a small widening costs the gate its life:

  * `BUG_RE` must catch a quoted `"$d"` in command position and must NOT catch
    `$d`, `"${dk[@]}"`, or `"$d"` used as an argument. It flagged nothing in the
    real file for as long as the defect shipped, and an over-broad version would
    fail the file it protects.
  * `SITE_RE` is the anti-vacuity denominator; over-narrowing it silently trips
    the floor and over-widening it hides a collapsed enumeration.
  * `code_of` is the reason a scan does not fire on its own documentation.

Each is run through the real `grep -E` on the same input and compared, and the line-numbering defect the twin carried is pinned rather than described. The twin `.ci/scripts/quality/check-devbox-exec.sh` was retired in W7 P5 once that ledger licensed the port at K=5, so `grep` itself is the oracle here rather than the shell file.
"""

import subprocess

from rediacc_ci import paths
from rediacc_ci.quality import devbox_exec as dx

# The three patterns exactly as the retired bash twin spelled them, in ERE.
BUG_ERE = r'(^|[;&|(]|then |else |do )[[:space:]]*"\$\{?d\}?"[[:space:]]'
SITE_ERE = r"\$\{?d\}?[[:space:]]"
NUMERIC_ERE = r"\-u[[:space:]]+\"?\$\(id -u\)"

CASES = (
    '"$d" exec -u vscode "$cid" bash -lc "$*"',
    '"${d}" exec x',
    'if x; then "$d" exec y; fi',
    'a | "$d" exec y',
    '$d exec -u vscode "$cid" bash',
    'local -a dk; read -r -a dk <<<"$d"',
    '"${dk[@]}" exec "$cid" bash',
    'echo "$d" here',
    '$d exec -it -u "$(id -u):$(id -g)" -w "$w" "$cid" bash',
    "$d exec -u $(id -u):$(id -g) x",
    '$d exec -u vscode "$cid" bash',
    "d=$(devbox_docker)",
)


def _grep_n(ere: str, text: str) -> list[str]:
    """`grep -nE <ere>` over `text`, as lines."""
    proc = subprocess.run(
        ["grep", "-nE", ere],
        input=text.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert proc.returncode in (0, 1), proc.stderr.decode("utf-8")
    return [line for line in proc.stdout.decode("utf-8").split("\n") if line != ""]


def _grep_c(ere: str, text: str) -> int:
    proc = subprocess.run(
        ["bash", "-c", 'grep -cE "$1" || true', "driver", ere],
        input=text.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    return int(proc.stdout.decode("utf-8").strip() or "0")


def test_bug_re_agrees_with_grep_on_every_case() -> None:
    """Twelve lines, both directions, against the twin's own ERE."""
    for line in CASES:
        text = line + "\n"
        assert dx.grep_n(dx.BUG_RE, text) == _grep_n(BUG_ERE, text), line


def test_site_re_agrees_with_grep_on_every_case() -> None:
    """The anti-vacuity denominator, which decides whether B1 is measuring anything."""
    for line in CASES:
        text = line + "\n"
        assert dx.grep_c(dx.SITE_RE, text) == _grep_c(SITE_ERE, text), line


def test_numeric_re_agrees_with_grep_on_every_case() -> None:
    """B2, including the unquoted form."""
    for line in CASES:
        text = line + "\n"
        assert dx.grep_n(dx.NUMERIC_RE, text) == _grep_n(NUMERIC_ERE, text), line


def test_code_of_matches_grep_v() -> None:
    """`grep -vE '^[[:space:]]*#'` DROPS the line, which is why numbering shifts."""
    text = '# a\n   # b\nkept # tail\n"$d" exec x\n'
    proc = subprocess.run(
        ["bash", "-c", "grep -vE '^[[:space:]]*#' || true"],
        input=text.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    want = proc.stdout.decode("utf-8")
    assert dx.code_of(text) == want


def test_the_line_number_defect_is_reproduced_not_repaired() -> None:
    """The twin reports a position in the FILTERED stream. Both sides must agree.

    The offending line is line 4 of the file and both implementations call it line 2, because `code_of` drops the comment lines before anything is numbered. A port that reported the file position would be more useful and would disagree with its twin on every finding.
    """
    text = '# a\n   # b\nkept # tail\n"$d" exec x\n'
    got = dx.grep_n(dx.BUG_RE, dx.code_of(text))
    want = _grep_n(BUG_ERE, dx.code_of(text))
    assert got == want == ['2:"$d" exec x']
    real = [i for i, line in enumerate(text.split("\n"), start=1) if dx.BUG_RE.search(line)]
    assert real == [4]


def test_the_real_devbox_file_is_scanned_and_clean() -> None:
    """The mirror on the live subject, plus the count the success line prints.

    A green over ZERO sites would be the vacuity this gate's own floor exists
    for, so the count is asserted as well as the cleanliness.
    """
    code = dx.code_of(paths.from_root(dx.DEVBOX_REL).read_text(encoding="utf-8", errors="replace"))
    assert dx.grep_n(dx.BUG_RE, code) == []
    assert dx.grep_n(dx.NUMERIC_RE, code) == []
    assert dx.grep_c(dx.SITE_RE, code) >= dx.MIN_SITES


def test_selftest_runs_and_meets_its_floor() -> None:
    """The gate's own both-direction controls, over fixtures built by concatenation."""
    assert dx.selftest() == 0
