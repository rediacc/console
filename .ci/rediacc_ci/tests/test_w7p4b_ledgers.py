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

-----------------------------------------------------------------------------
THE SECOND FAMILY, seven more pairs, and the two things it did differently
-----------------------------------------------------------------------------

`resolve-version`, `inject-env`, `check-existing-release`, `clone-d1`, `wait-for-preview-worker`, `ci-start-account` and `ci-start-elite` were recorded the same way as the five above, and every one of them already carried an OLDER ledger (`w7p6-*` or `w7p5a-*`) that cannot be read as attesting to anything: those rows reach both sides through a `bash fx/run.sh old|new` or
`_w7p5a_record_wrapper.sh` indirection whose fixture no longer exists. Re-recorded rather than cited, for the reason the first family gives above.

  * THE RECORDING STUB IS NOT ALWAYS A BINARY ON PATH. `wait-for-preview-worker`
    shells out to `curl` while its port speaks HTTP through `urllib`, so a PATH stub for the client would have recorded one side and not the other, and the pair would have had to be excused from the call-log rule. The external thing BOTH sides drive is the preview Worker, so the stub is the SERVER: a local `http.server` that appends one `worker GET <path>` line per request. The
    probe sequence -- which endpoint, how many times, in what order, which is the whole subject of a readiness script -- is therefore inside the compared set for both implementations. `PAIRS` names `worker` as that pair's binary for exactly this reason.
  * `git` IS STUBBED AS A PASS-THROUGH. `resolve-version`, `inject-env` and
    `check-existing-release` exist to run real git commands, so their stub logs the argv and then `exec`s the real binary. That keeps `git tag -l`'s answer real while still putting the invocation inside the comparison; a reimplementing stub would have compared two ports against a third implementation.

ONE ACCEPTED DIVERGENCE, CUT OVER DELIBERATELY: `clone-d1 --sanitize` on a host that HAS `sqlite3`. `.ci/scripts/deploy/sanitize-d1.sql` was deleted in `57b61098c` and never replaced, so that path fails on both sides -- but it fails through a `< file` redirection, and bash reports that as `<script path>: line 117: <path>: No such file or directory` while the port reports
`clone-d1.sh: <path>: No such file or directory`. Same stream, same exit status, same path and reason, different leader; `test_deploy_clone_d1.py` normalises exactly that shape and asserts the normaliser is tight. The recording host has no `sqlite3`, so the ledger's `--sanitize` row is the `Required command 'sqlite3' is not available` refusal, which is byte-identical. The missing
`.sql` file is a defect in its own right and is reported separately: `.github/workflows/edge-clone-d1.yml` passes `--sanitize` today, so that job cannot succeed in EITHER language.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from rediacc_ci import paths, workflows

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
    "w7p4b-resolve-version": (
        ".ci/scripts/version/resolve-version.sh",
        "rediacc_ci.version.resolve_version",
        "git",
    ),
    "w7p4b-inject-env": (
        ".ci/scripts/version/inject-env.sh",
        "rediacc_ci.version.inject_env",
        "git",
    ),
    "w7p4b-check-existing-release": (
        ".ci/scripts/release/check-existing-release.sh",
        "rediacc_ci.release.check_existing_release",
        "gh",
    ),
    "w7p4b-clone-d1": (
        ".ci/scripts/deploy/clone-d1.sh",
        "rediacc_ci.deploy.clone_d1",
        "npx",
    ),
    "w7p4b-ci-start-elite": (
        ".ci/scripts/infra/ci-start-elite.sh",
        "rediacc_ci.infra.ci_start_elite",
        "curl",
    ),
    "w7p4b-ci-start-account": (
        ".ci/scripts/infra/ci-start-account.sh",
        "rediacc_ci.infra.ci_start_account",
        "docker",
    ),
    # `worker`, not `curl`: the twin drives curl and the port drives urllib, so the stub that records the traffic is the preview Worker itself. See the module docstring.
    "w7p4b-wait-for-preview-worker": (
        ".ci/scripts/deploy/wait-for-preview-worker.sh",
        "rediacc_ci.deploy.wait_for_preview_worker",
        "worker",
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


def _call_site_text() -> str:
    """Every `run:` and `with:` VALUE in `.github/workflows/*.yml`, concatenated.

    W7P4-W's acceptance counts a script as still called only under one of those two keys, because 31 of the 290 raw occurrences it started from were comment lines and ten distinct paths appeared in comments alone. A raw text search therefore reads a retired path as live: `ci-start-elite.sh` is named in `breakpoint.yml` by a `workflow_dispatch` input DESCRIPTION and by a comment,
    neither of which runs anything.

    Parsed with `rediacc_ci.workflows` rather than PyYAML, which is not installed for the interpreter that runs pytest (see that module's own docstring). Keys are collected at any depth, so a reusable workflow's job-level `with:` counts alongside a step's.
    """
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("run", "with"):
                    found.append(_flatten(value))
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for path in sorted(WORKFLOWS.glob("*.yml")):
        walk(workflows.load(path))
    return "\n".join(found)


def _flatten(value: object) -> str:
    if isinstance(value, dict):
        return "\n".join(_flatten(v) for v in value.values())
    if isinstance(value, list):
        return "\n".join(_flatten(v) for v in value)
    return str(value)


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
    assert twin not in _call_site_text(), (
        "%s is still named under a `run:` or `with:` key in .github/workflows/*.yml. "
        "P4b's acceptance is that the set of `.ci/**/*.sh` paths under one of those two "
        "keys strictly shrinks, and this path was counted as removed." % twin
    )
    text = _workflow_text()
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


def test_the_call_site_reader_can_still_see_a_call_site() -> None:
    """CONTROL on the assertion above, which is the only one that can go quiet.

    `_call_site_text` narrows the search from the whole workflow text to `run:` and `with:` values, and a narrowing that returned nothing would pass every cutover assertion in this module for every pair, forever. So one path known to be LIVE has to be visible through it, and the two `breakpoint.yml` mentions of `ci-start-elite.sh` -- a `workflow_dispatch` input description and a
    comment, neither of which runs anything -- have to stay invisible.
    """
    text = _call_site_text()
    assert ".ci/scripts/ci/scope-shadow.sh" in text, (
        "the call-site reader found no `run:` naming scope-shadow.sh, which ci.yml "
        "still runs. Every cutover assertion in this module passes vacuously when "
        "this reader returns nothing."
    )
    assert "tunnel + desktop only" not in text, (
        "a workflow_dispatch input description reached the call-site reader, so it is "
        "reading prose again and the comment-line false positives W7P4-W measured are "
        "back."
    )
