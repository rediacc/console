"""The W7P4-b cutover ledgers, and what each one is allowed to be read as saying.

P4b is the tail of W7P4-W: the `.ci/**/*.sh` paths still named under a `run:` or `with:` key in `.github/workflows/**`. Five of them were cut over to their Python ports here, and a cutover is the one change a ledger genuinely licenses -- after it, CI runs the port and nothing runs the twin, so a divergence nobody recorded is a divergence nobody will ever see.

Each pair was recorded from a SCRATCH git repo outside this tree, one clean committed tree per scenario, with recording stubs for `gh`, `aws`, `npm`, `curl`, `tar`, `sha256sum`, `uname` and `sleep` first on PATH. Both sides re-emit stdout, stderr, the stub call log, `GITHUB_OUTPUT` and `GITHUB_ENV` under one `--finding-re`, so the comparison covers the external requests and the
exported variables rather than text alone.

WHAT THIS MODULE REFUSES TO LET DECAY, in four directions:

  * THE EVIDENCE IS REAL. Five rows minimum, every one EQUIVALENT, over five distinct CLEAN tree ids and five distinct finding fingerprints. That is `assertEquivalent`'s rule, restated where a pytest sweep runs it, because nothing in CI invokes `shadow-gate --assert` for these pairs.
  * THE EVIDENCE IS ABOUT THE RIGHT PAIR. Each row's `old.cmd` must name the bash path the row is filed under and its `new.cmd` the `python3 -m` module spec that replaced it at the call site. A ledger is a text file, and rows copied from a neighbouring pair would satisfy every count above.

    Not a hypothetical worry here: the earlier `w7p6-` ledgers for four of these same five scripts reach both sides through a `bash fx/run.sh old|new` indirection whose fixture is gone, so no reader can now tell which script those rows attest to.
  * THE COMPARISON WAS WIDER THAN THE EXIT CODE. A row whose only agreeing finding is its own `[exit] N` line has compared two status codes and nothing else, and five of those are not five observations of a port. `K` is counted over SUBSTANTIVE rows only, which is also what quarantines the two harness-bug rounds described below.
  * THE CALL LOG WAS PART OF IT. Each pair names the external binary its script exists to drive, and at least one row must agree on that binary's recorded argv. Two implementations can print identical lines while issuing different requests.

TWO HARNESS BUGS LEFT ROWS IN THESE FILES, and neither is deleted, because a ledger is a record and rewriting it to look tidier is how a mismatch stops being evidence.

  1. `w7p4b-assert-r2-sentinel` carries nine early rows whose only agreeing finding is `[exit] N`. The wrapper read its normalization script through `sed -f`, and that file's first two bytes were `#n`, POSIX sed's suppress-auto-print directive.

     Every captured stream therefore came back empty and the comparison silently narrowed to the status code. The rows are true and nearly vacuous, and the SUBSTANTIVE-row rule below is what stops them counting toward K.
  2. The same pair then recorded two MISMATCH_FINDINGS rows, also a wrapper artifact: prefixing each captured line with `[err] ` displaced the severity glyph out of column 1, where shadow-gate's own MARKERS rule strips it, so `release_state_validator`'s deliberately glyph-free stderr read as a divergence from the twin's.

     The wrapper now folds that glyph back on BOTH sides before prefixing. Those two tree ids stay disqualified for good, which is the rule working as designed; the pair re-earned its licence on later clean trees.

`w7p4b-ensure-nfpm` likewise carries eight rows from a scratch repo that had no `.devcontainer/toolchain.env`, where both sides refused identically at `constants.sh`. Those rows are substantive and honest -- the two implementations agree on a refusal -- and they are simply not the interesting half of the ledger.

THE PORTS ARE NOT RE-TESTED HERE. Each has a permanent side-by-side differential of its own under `.ci/rediacc_ci/tests/`; what was missing is enforcement of the LEDGERS the cutover rests on.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from rediacc_ci import paths

ROOT = pathlib.Path(paths.repo_root())
SHADOW = ROOT / ".ci" / "shadow"
WORKFLOWS = ROOT / ".github" / "workflows"

# The shadow-gate rule these ledgers were recorded to satisfy.
K = 5

# pair -> (bash twin, module spec now at the call site, external binary the row's `[call]` findings must carry).
#
# The binary is the one the script exists to drive, so this table doubles as the check that a ledger recorded the RIGHT script's traffic: `ensure-nfpm` agreeing only on `gh` lines would mean the fixture answered a neighbour's probes.
PAIRS = {
    "w7p4b-assert-r2-sentinel": (
        ".ci/scripts/test/assert-r2-sentinel.sh",
        "rediacc_ci.release.assert_r2_sentinel",
        "aws",
    ),
    "w7p4b-cancel-older-runs": (
        ".ci/scripts/ci/cancel-older-runs.sh",
        "rediacc_ci.ci.cancel_older_runs",
        "gh",
    ),
    "w7p4b-check-rerun-attempt": (
        ".ci/scripts/ci/check-rerun-attempt.sh",
        "rediacc_ci.ci.check_rerun_attempt",
        "gh",
    ),
    "w7p4b-ensure-nfpm": (
        ".ci/scripts/build/ensure-nfpm.sh",
        "rediacc_ci.build.ensure_nfpm",
        "uname",
    ),
    "w7p4b-install-cli-global": (
        ".ci/scripts/setup/install-cli-global.sh",
        "rediacc_ci.setup.install_cli_global",
        "npm",
    ),
}

# A finding that is only the re-emitted status code. Five of these agree about two integers.
EXIT_ONLY = re.compile(r"^\[error\] \[exit\] -?\d+$")


def _ledger(pair: str) -> pathlib.Path:
    return SHADOW / ("%s.observations.jsonl" % pair)


def _rows(pair: str) -> list[dict]:
    text = _ledger(pair).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _substantive(rows: list[dict]) -> list[dict]:
    """Rows that agreed on something other than the exit code, and agreed fully."""
    return [
        r
        for r in rows
        if r["verdict"] == "EQUIVALENT"
        and r["tree"].get("clean")
        and any(not EXIT_ONLY.match(a) for a in r["agreed"])
    ]


def _workflow_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(WORKFLOWS.glob("*.yml")))


def test_the_pair_set_is_not_empty() -> None:
    """VACUITY FLOOR. Every test below is parameterised over `PAIRS`, so an empty table would turn this module green while checking nothing."""
    assert PAIRS, "PAIRS is empty; a green run here would assert nothing at all"


@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_the_ledger_exists_and_holds_k_substantive_rows(pair: str) -> None:
    ledger = _ledger(pair)
    assert ledger.is_file(), "%s names %s, which does not exist" % (pair, ledger)

    rows = _rows(pair)
    good = _substantive(rows)
    assert len(good) >= K, (
        "%s holds %d substantive row(s) out of %d; K=%d is required. A row counts "
        "only when it is EQUIVALENT, was recorded on a CLEAN tree, and agreed on "
        "something other than its own `[exit]` line." % (ledger.name, len(good), len(rows), K)
    )

    trees = {r["tree"]["id"] for r in good}
    assert len(trees) >= K, "%s spans %d distinct tree(s); K=%d is required" % (
        ledger.name,
        len(trees),
        K,
    )

    prints = {r["old"]["fingerprint"] for r in good}
    assert len(prints) >= K, (
        "%s spans only %d distinct finding set(s) over %d substantive rows: the same "
        "scenario recorded on five trees is one observation, not five."
        % (ledger.name, len(prints), len(good))
    )


@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_every_row_names_the_pair_it_is_filed_under(pair: str) -> None:
    """A count means something only once the rows are known to be about this script. The `w7p6-` ledgers for four of these five scripts cannot pass this test at all, which is why they were re-recorded rather than cited."""
    twin, module, _ = PAIRS[pair]
    for n, row in enumerate(_rows(pair), 1):
        assert row["pair"] == pair, "%s row %d is filed under pair %r" % (pair, n, row["pair"])
        assert twin in row["old"]["cmd"], (
            "%s row %d does not invoke %s on the old side; the row attests to a "
            "different script than the one it is filed under" % (pair, n, twin)
        )
        assert ("python3 -m %s" % module) in row["new"]["cmd"], (
            "%s row %d does not invoke `python3 -m %s` on the new side, which is the "
            "exact spelling the workflow call site now carries" % (pair, n, module)
        )
        assert "PYTHONDONTWRITEBYTECODE=1" in row["new"]["cmd"], (
            "%s row %d ran the port without PYTHONDONTWRITEBYTECODE=1, which drops "
            "__pycache__ into the recorded tree and makes the NEXT row's clean-tree "
            "check a coin toss" % (pair, n)
        )


@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_the_external_call_log_was_part_of_the_comparison(pair: str) -> None:
    """A run that agreed on stdout while sending a different request is what this prefix exists to catch, so the recorded argv has to be inside the compared set."""
    _, _, tool = PAIRS[pair]
    rows = _rows(pair)
    logged = {
        agreed.split("[call] ", 1)[1].split()[0]
        for row in rows
        for agreed in row["agreed"]
        if "[call] " in agreed and agreed.split("[call] ", 1)[1].split()
    }
    assert tool in logged, (
        "no row in %s agreed on a `[call] %s ...` line, yet that is the binary the "
        "script exists to drive. The recorded calls were %s."
        % (_ledger(pair).name, tool, sorted(logged) or "none")
    )


@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_the_call_site_was_actually_cut_over(pair: str) -> None:
    """THE LOAD-BEARING ONE, and the direction a ledger alone cannot police. A licence that nothing consumed is a licence nobody notices going stale; a call site that reverted to bash while the ledger stayed reads as a finished cutover."""
    twin, module, _ = PAIRS[pair]
    text = _workflow_text()
    assert twin not in text, (
        "%s is still named in .github/workflows/*.yml. P4b's acceptance is that the "
        "set of `.ci/**/*.sh` paths under a `run:` or `with:` key strictly shrinks, "
        "and this path was counted as removed." % twin
    )
    assert ("python3 -m %s" % module) in text, (
        "no workflow runs `python3 -m %s`, so %s's ledger licenses a cutover that is "
        "not in the tree." % (module, pair)
    )


@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_the_bash_twin_is_still_on_disk(pair: str) -> None:
    """W7P5 retires the `.sh` files as its own step. Until then the twin is what a future re-record compares against, and deleting it would strand every ledger here."""
    twin, _, _ = PAIRS[pair]
    assert (ROOT / twin).is_file(), (
        "%s has been deleted. The ledgers in this module compare against it, so its "
        "removal retires the evidence for the cutover rather than completing it." % twin
    )
