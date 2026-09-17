"""`rediacc_ci.quality.ci_job_aggregation` against the five awk programs it replaces.

WHAT IS WORTH TESTING HERE. The shadow ledger `.ci/shadow/w7p2-ci-job-aggregation.observations.jsonl` drives the whole gate over five distinct trees, one per failure class. What a ledger row cannot isolate is that the port re-implements FIVE awk programs plus a `tr`, and every one of them decides which jobs the gate believes exist. A reader that narrows by one rule reports a fully
wired workflow, which is the exact shape this gate exists to make impossible.

Each program is run through the real awk on the same input and compared, and the inputs chosen are the ones where awk is surprising:

  * `match()` finds only the FIRST RESULT_ var on a line
  * the tier reader's `index(line, ")")` closes the array on the same line
  * `tr '[:lower:]-' '[:upper:]_'` is a two-set translation, so an already
    uppercase letter and a dot both pass through untouched
"""

import subprocess

from rediacc_ci import paths
from rediacc_ci.core import allowlist
from rediacc_ci.quality import ci_job_aggregation as ja

TWIN = paths.from_root(".ci", "scripts", "quality", "check-ci-job-aggregation.sh")

TOP_LEVEL_JOBS_AWK = r"""
    /^jobs:[[:space:]]*$/ { in_jobs = 1; next }
    in_jobs && /^[^[:space:]#]/ { in_jobs = 0 }
    in_jobs && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ {
        key = $0
        sub(/^  /, "", key)
        sub(/:[[:space:]]*$/, "", key)
        print key
    }
"""

NEEDS_AWK = r"""
    /^[[:space:]]*needs:/ {
        line = $0
        sub(/^[[:space:]]*needs:[[:space:]]*/, "", line)
        gsub(/[][,]/, " ", line)
        n = split(line, parts, /[[:space:]]+/)
        for (i = 1; i <= n; i++) if (parts[i] != "") print parts[i]
    }
"""

RESULT_VARS_AWK = r"""
    match($0, /RESULT_[A-Z0-9_]+:/) {
        print substr($0, RSTART, RLENGTH - 1)
    }
"""

TIER_AWK = r"""
    /^(HARD_REQUIRED|SOFT_REQUIRED)\+?=\(/ {
        collecting = 1
        sub(/^[^(]*\(/, "")
    }
    collecting {
        line = $0
        if (index(line, ")") > 0) {
            sub(/\).*$/, "", line)
            collecting = 0
        }
        sub(/#.*$/, "", line)
        n = split(line, parts, /[[:space:]]+/)
        for (i = 1; i <= n; i++) if (parts[i] != "") print parts[i]
    }
"""


def _awk(program: str, text: str, *args: str) -> list[str]:
    """Run the real awk over `text` and return its non-empty output lines."""
    proc = subprocess.run(
        ["awk", *args, program],
        input=text.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8")
    return [line for line in proc.stdout.decode("utf-8").split("\n") if line != ""]


def test_top_level_jobs_matches_awk_on_the_fixture() -> None:
    """The four keys, and the three 2-space keys outside the jobs block."""
    text = ja.FIXTURE_WORKFLOW
    assert ja.top_level_jobs(text) == _awk(TOP_LEVEL_JOBS_AWK, text)


def test_top_level_jobs_matches_awk_when_a_later_key_closes_the_block() -> None:
    """The mirror: a top-level key after `jobs:` must END the block, not be a job."""
    text = "jobs:\n  a:\n    runs-on: x\nfooter:\n  b:\n"
    assert ja.top_level_jobs(text) == _awk(TOP_LEVEL_JOBS_AWK, text) == ["a"]


def test_top_level_jobs_matches_awk_on_a_file_with_no_jobs_block() -> None:
    """Zero jobs is what the MIN_JOBS floor exists to refuse, so it must be zero."""
    text = "name: x\non:\n  push:\n"
    assert ja.top_level_jobs(text) == _awk(TOP_LEVEL_JOBS_AWK, text) == []


def test_job_block_matches_awk() -> None:
    """The aggregator's body, compared line for line against the awk extractor."""
    program = r"""
        $0 ~ ("^  " want ":[[:space:]]*$") { in_job = 1; next }
        in_job && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ { in_job = 0 }
        in_job { print }
    """
    text = ja.FIXTURE_WORKFLOW
    got = ja.job_block(text, "ci-complete")
    want = _awk(program, text, "-v", "want=ci-complete")
    assert [line for line in got.split("\n") if line != ""] == want


def test_job_block_of_an_absent_job_is_empty_on_both_sides() -> None:
    """An empty block is what makes the gate say the aggregator is gone."""
    assert ja.job_block(ja.FIXTURE_WORKFLOW, "no-such-job") == ""


def test_needs_names_matches_awk_on_both_forms() -> None:
    """`needs: [a, b]` and the bare `needs: a`, which the twin's comment names."""
    for text in ("    needs: [a, b, c]\n", "    needs: solo\n", "    runs-on: x\n"):
        assert ja.needs_names(text) == _awk(NEEDS_AWK, text), text


def test_result_vars_matches_awk_including_the_first_match_only_shape() -> None:
    """awk's `match()` returns the FIRST occurrence, so two vars on a line read as one.

    That is a limitation of the twin, not of the port, and it is pinned here so the two agree about a shape neither of them handles.
    """
    for text in (
        "      RESULT_A: ${{ needs.a.result }}\n      RESULT_B: x\n",
        "  RESULT_A: x RESULT_B: y\n",
        "      FOO: ${{ needs.x.result }}\n",
    ):
        assert ja.result_vars(text) == _awk(RESULT_VARS_AWK, text), text


def test_tier_entries_matches_awk_on_every_array_form() -> None:
    """Multi-line, single-line, `+=`, an inline comment, and an unrelated array."""
    for text in (
        ja.FIXTURE_ASSERT,
        "HARD_REQUIRED+=(EXTRA)\n",
        "HARD_REQUIRED=(\n  A  # why\n  B\n)\n",
        "OTHER=(A B)\n",
        "SOFT_REQUIRED=(A B C)\n",
    ):
        assert ja.tier_entries(text) == _awk(TIER_AWK, text), text


def test_result_var_for_matches_tr() -> None:
    """`tr '[:lower:]-' '[:upper:]_'`, run for real, on the cases that differ.

    `a.b` is the interesting one: `.upper().replace()` gives the same answer here and would diverge from tr on any character outside both sets, so the test asserts against tr rather than against the tidier spelling.
    """
    for job in ("build-cli", "quality", "a.b", "MiXeD-Case", "job_1"):
        proc = subprocess.run(
            ["tr", "[:lower:]-", "[:upper:]_"],
            input=job.encode("utf-8"),
            stdout=subprocess.PIPE,
            check=True,
        )
        want = "RESULT_" + proc.stdout.decode("utf-8")
        assert ja.result_var_for(job) == want, job


def test_the_exempt_set_matches_the_twins_block_entry_for_entry() -> None:
    """The five exempt job names, and their reasons, taken from the twin's own text.

    A port that dropped one would silently widen the gate by one job. A port that ADDED one would silently narrow it, which is worse, so the comparison is a set equality against the twin rather than a floor.
    """
    body = TWIN.read_text(encoding="utf-8")
    start = body.index("read -r -d '' EXEMPT_BLOCK <<'EXEMPT'")
    end = body.index("\nEXEMPT\n", start)
    twin_block = body[body.index("\n", start) + 1 : end + 1]
    twin_pairs = allowlist.pairs(allowlist.parse_text(twin_block))
    assert ja.exempt_entries() == twin_pairs
    assert len(twin_pairs) == 5


def test_selftest_runs_and_meets_its_floor() -> None:
    """The gate's own both-direction controls, over fixtures built by construction."""
    assert ja.selftest() == 0
