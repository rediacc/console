"""The W7P4-b cutover ledgers, and what each one is allowed to be read as saying.

P4b is the tail of W7P4-W: the `.ci/**/*.sh` paths still named under a `run:` or `with:` key in `.github/workflows/**`. The families below cut eighteen of them over to their Python ports, and a cutover is the one change a ledger genuinely licenses -- after it, CI runs the port and nothing runs the twin, so a divergence nobody recorded is a divergence nobody will ever see. The first
family is the five named in the two harness-bug notes below.

Each pair was recorded from a SCRATCH git repo outside this tree, one clean committed tree per scenario, with recording stubs for `gh`, `aws`, `npm`, `curl`, `tar`, `sha256sum`, `uname`, `rdc`, `ssh`, `date` and `sleep` first on PATH. Both sides re-emit stdout, stderr, the stub call log, `GITHUB_OUTPUT` and `GITHUB_ENV` under one `--finding-re`, so the comparison covers the
external requests and the exported variables rather than text alone.

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
`.sql` file is a defect in its own right and was reported separately: `.github/workflows/edge-clone-d1.yml` passed `--sanitize`, so that job could not succeed in EITHER language. It was removed for that reason in `9ac3f6a42`, which is why this pair now sits in `RETIRED_WITH_THEIR_WORKFLOW` below.

-----------------------------------------------------------------------------
THE THIRD FAMILY, two pairs, and the divergence the call log caught
-----------------------------------------------------------------------------

`typecheck-workers` (9 rows, 9 trees, 9 finding sets) and `scope-shadow` (12 rows, 12 trees, 12 finding sets) were recorded the same way, and neither had a usable older ledger: the `w7p6-` pairs for both reach their sides through a fixture that is gone.

  * `typecheck-workers` is a DISCOVERY gate, so the scenarios vary the thing it
    discovers rather than its flags alone: three workers and `--list`, no `workers/` directory at all (the zero-discovery refusal), two workers that already have their deps, one that needs `npm ci`, one with no lockfile that needs `npm install`, a clean typecheck, a `tsc` that reds on the second project, an install that fails, and `--isntall` -- the unknown argument the port's own
    DEFECT A section says falls through to a full run. `npm` and `npx` are recording stubs; nothing reaches a registry.
  * `scope-shadow` has FOUR `.cjs` children it shells out to, and the real ones
    reach `gh api` and throw on a closure path absent from HEAD. The config-driven fakes `test_ci_scope_shadow.py` already ships stand in for all four, so the twelve scenarios can reach arms the real engine would never produce on demand: both kill switches, no shas at all, a resolved baseline with and without a greenlight grant, a baseline engine that crashes, a greenlight
    engine that crashes, a plan writer that throws, a plan whose key set has drifted from scope-map's, an unusable plan mode, a real merge commit so `--classify` runs, and the three tri-state pre-existing conditions. The ledger re-emits `$OUT_DIR/plan.json` under a `[plan]` prefix as well, because the plan is the object this script exists to produce and the one the reconciler
    audits.

THE `node` STUB IS A PASS-THROUGH, and it earned its keep immediately. It logs the argv and execs the real binary, so the five inline `node -e` programs and the two `node <child>` invocations enter the comparison; ten of the twelve scenarios came back MISMATCH_FINDINGS on the first run. The cause was not a fixture artifact: a shell word closed by `'` includes the newline before
that quote, so the twin hands node a program that both opens AND closes with `\\n`, while `test_ci_scope_shadow.py`'s extraction helper split on `"\\n'"` and consumed the closing one. All five carried constants in the port were one byte short. Inert to node, invisible to every stream comparison, and a real divergence in the recorded argv -- repaired in the port and in the helper,
rather than normalised out of the ledger. A planted `--budget 91` was then watched red on the call log alone and restored green, which is the control for this pair.

BOTH CUTOVERS REACH FURTHER THAN A WORKFLOW LINE, and the reach is what the tests below cannot see. `scope-shadow` had one `run:` in `ci.yml` and nothing else. `typecheck-workers` had that plus three `package.json` scripts (`check:types`, `typecheck`, `lint:unused`), its own `---- gate ----` header's `run:`, two `scripts/ci-runner/manifest.ts` leaves, and
`scripts/gates/check-typecheck-scope-coverage.ts`, which resolved the clause by looking for a token ending in `.sh` and would have read every `workers/*/tsconfig.json` as uncovered the moment the clause stopped containing one.

-----------------------------------------------------------------------------
THE FOURTH FAMILY, four pairs, and a gate that had to learn a second spelling
-----------------------------------------------------------------------------
`build-renet` (12 rows), `compose-healthcheck-smoke-test` (11), `run-account` (10) and `run-renet` (9). None of the four had a usable older ledger for the same reason as the families above: the `w7p6-` pairs reach their sides through a fixture that no longer exists.

  * THE SUBJECT'S OWN DELEGATE IS THE STUB, not a binary on PATH.
    `build-renet` never runs `go` itself -- it asks `command -v` whether a toolchain is there and then delegates the whole build to `private/renet/build.sh`, which a PATH stub cannot shadow because the twin invokes it by relative path from inside the submodule. So the recording stand-in IS that file, written into a gitignored `private/` tree by the scenario and removed by
    `shadow/cleanup.sh`, and `PAIRS` names `build.sh` as the binary for exactly that reason. The same trick carries `run-renet`, whose one delegate is `private/renet/.ci/ci.sh`; that stub logs the stage, the inherited cwd and the exported `GOTOOLCHAIN`, because a port that printed the same banner while never invoking the stage would satisfy a stdout-only comparison and run no Go
    tests at all.
  * `uname` IS DELIBERATELY NOT STUBBED for `build-renet`, and the reason is a
    real asymmetry rather than a convenience. `common.sh` makes two platform probes (`uname -s`, `uname -m`) at SOURCE time, before the twin's own code runs; the port sources no such library and makes only the one probe the subject itself asks for. A recording stub would put those two library calls into the comparison on one side only and turn every row into a mismatch over
    traffic neither implementation chose. They have no observable effect, so the pair's call log carries the one delegation that does.
  * THE POLL LOOP NEEDED A DETERMINISTIC CLOCK.
    `compose-healthcheck-smoke-test` polls a container healthcheck against a wall-clock deadline, so with a real `date` the NUMBER of probes depends on how fast each side happens to run and the two sides disagree about a call log neither of them chose. The stub answers `+%s` from a counter that advances by a fixed step per reading and passes every other format through, which fixes
    the probe count for both sides; `sleep` is a no-op recorder beside it. That is what makes "db converges on the third probe" a scenario rather than a race.
  * THE `ssh` STUB LOGS THE WHOLE ARGV, remote program included. The three
    remote programs this script sends are multi-line shell, so they enter the comparison a line at a time -- which is the point, because WHICH probe runs in WHICH order is the entire subject of a healthcheck smoke test, and both implementations build those strings independently.

THE CUTOVER REACHED A GATE THAT COULD NOT SEE THE NEW SPELLING, and it would have failed loudly rather than quietly, which is the lucky direction. `check:ci-workflow-env-provision` follows ONE HOP out of a `run:` block into the script it names, because nine jobs use `$RENET_BINARY` and only the renet build step writes it to `$GITHUB_ENV`. Its resolver matched a PATH ending in
`.sh`/`.py`/`.ts`/`.cjs`, and a cut-over step names no path at all. Driven with the repair removed: nine false findings, one per job, exit 1. The gate now resolves `python3 -m rediacc_ci.<mod>` to its file as well, recognises the Python writer's `"NAME=` string shape, and carries two new controls -- one pinning `RENET_BINARY` through the module spelling, one proving an
unresolvable spec provisions nothing -- because the path half kept passing on a `.sh` file that nothing runs any more.

TWO OF THE FOUR ARE REGISTERED GATES, so their cutover is wider than a workflow line: `check:ci-renet` and `check:ci-account-server` each moved their `package.json` script, their own `---- gate ----` header's `run:` (the header STAYS on the bash file, because `gate-bind` resolves a gate by where its header lives and a second owner would be a parity failure), their
`scripts/ci-runner/manifest.ts` `leaves`, and for `check:ci-renet` its `paths:` as well -- which had named `run-renet.sh` and `lib/common.sh`, so leaving it would have stopped `--changed` selecting the gate when its own port changed. `check_renet_tier_map.py`'s `blocker:` quotes that leaf by name and had to move with it, in the gate header, in the manifest and in the lock, or the
three copies of one sentence would have disagreed.
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
    "w7p4b-typecheck-workers": (
        ".ci/scripts/quality/typecheck-workers.sh",
        "rediacc_ci.quality.typecheck_workers",
        "npx",
    ),
    # `node`, and the stub is a PASS-THROUGH. This script is a shell around five inline `node -e` programs and two `node <child>` invocations; what it exists to drive is node, and the argv is where the one divergence the third family found actually lived.
    "w7p4b-scope-shadow": (
        ".ci/scripts/ci/scope-shadow.sh",
        "rediacc_ci.ci.scope_shadow",
        "node",
    ),
    # `build.sh`, not `go`: the twin only asks `command -v go` and then hands the whole build to `private/renet/build.sh`. See the fourth family's section above for why the stub is a file in the fixture rather than a binary on PATH.
    "w7p4b-build-renet": (
        ".ci/scripts/infra/build-renet.sh",
        "rediacc_ci.infra.build_renet",
        "build.sh",
    ),
    "w7p4b-compose-healthcheck-smoke-test": (
        ".ci/scripts/private/compose-healthcheck-smoke-test.sh",
        "rediacc_ci.private.compose_healthcheck_smoke_test",
        "rdc",
    ),
    "w7p4b-run-account": (
        ".ci/scripts/private/run-account.sh",
        "rediacc_ci.private.run_account",
        "npm",
    ),
    # `ci.sh`, the submodule's own entry point, for the same reason `build-renet` names `build.sh`: it is invoked by path out of `private/renet`, not from PATH.
    "w7p4b-run-renet": (
        ".ci/scripts/private/run-renet.sh",
        "rediacc_ci.private.run_renet",
        "ci.sh",
    ),
}

# A finding that is only the re-emitted status code. Five of these agree about two integers.
EXIT_ONLY = re.compile(r"^\[error\] \[exit\] -?\d+$")

# Pairs whose CALL SITE was deleted outright rather than cut over, with the commit that did it. A cutover assertion cannot be made about a job that no longer exists, and the two directions it polices split here: the twin must still be absent from the call sites (unchanged), but so must the port, because nothing runs either any more.
#
# `w7p4b-clone-d1` entered this set in `9ac3f6a42`, which removed `.github/workflows/edge-clone-d1.yml` -- a manual-dispatch job that passed `--sanitize`, whose PII-scrub SQL had been deleted in `57b61098c`, so it could not complete in either language. That commit kept the script and the port (the D1 migration test still drives them without the flag) and left this module asserting
# that a workflow ran the port, so `pytest` over this file has been red since. Found on 2026-09-20 while adding the third family; repaired here rather than reported, because the repair is one entry and a branch.
RETIRED_WITH_THEIR_WORKFLOW = {
    "w7p4b-clone-d1": "9ac3f6a42 removed .github/workflows/edge-clone-d1.yml",
}


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


def test_the_retired_set_names_real_pairs() -> None:
    """VACUITY FLOOR on the branch above. An entry for a pair that is not in `PAIRS` excuses nothing and reads as if it did."""
    unknown = sorted(set(RETIRED_WITH_THEIR_WORKFLOW) - set(PAIRS))
    assert not unknown, (
        "RETIRED_WITH_THEIR_WORKFLOW names %s, which no pair is filed under" % unknown
    )


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
    if pair in RETIRED_WITH_THEIR_WORKFLOW:
        assert ("python3 -m %s" % module) not in text, (
            "%s is listed as retired with its workflow (%s), yet a workflow runs "
            "`python3 -m %s`. Either the job came back, in which case this is an "
            "ordinary cutover and the entry goes, or the entry names the wrong pair."
            % (pair, RETIRED_WITH_THEIR_WORKFLOW[pair], module)
        )
        return
    assert ("python3 -m %s" % module) in text, (
        "no workflow runs `python3 -m %s`, so %s's ledger licenses a cutover that is "
        "not in the tree." % (module, pair)
    )


# Pairs whose bash twin W7P5 has RETIRED, with the batch that did it. The ledger is then the whole of the evidence, which is what the K=5 assertion above exists to keep true; a re-record is no longer possible and is not supposed to be.
RETIRED_TWINS = {
    "w7p4b-check-rerun-attempt": "W7P5 batch B5",
    # Deleted by the 30-twin batch in 62599afc0 without an entry here, so this assertion was red in the tree until W7P5 batch M1 read it. The batch is named by its commit rather than by a label, because the label it carried is not written down anywhere the entry can cite.
    "w7p4b-cancel-older-runs": "the 30-twin batch in commit 62599afc0",
    "w7p4b-install-cli-global": "W7P5 batch M1",
    "w7p4b-run-renet": "W7P5 batch M5",
    "w7p4b-run-account": "W7P5 batch M5",
    "w7p4b-compose-healthcheck-smoke-test": "W7P5 batch M5",
    "w7p4b-scope-shadow": "W7P5 batch M6",
}


@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_the_bash_twin_is_still_on_disk(pair: str) -> None:
    """W7P5 retires the `.sh` files one batch at a time. Until a pair's batch lands the twin is what a future re-record compares against, and deleting it would strand this pair's ledger without saying so."""
    twin, _, _ = PAIRS[pair]
    if pair in RETIRED_TWINS:
        assert not (ROOT / twin).is_file(), (
            "%s is listed as retired by %s but is still on disk. An entry here excuses "
            "the assertion below, so a stale one hides a twin nobody is checking."
            % (twin, RETIRED_TWINS[pair])
        )
        return
    assert (ROOT / twin).is_file(), (
        "%s has been deleted without an entry in RETIRED_TWINS. The ledgers in this "
        "module compare against it, so an unrecorded removal retires the evidence for "
        "the cutover rather than completing it." % twin
    )


def test_the_retired_twin_set_names_real_pairs() -> None:
    """VACUITY FLOOR on the branch above, the same one `RETIRED_WITH_THEIR_WORKFLOW` carries: an entry for a pair nothing is filed under excuses nothing and reads as if it did."""
    unknown = sorted(set(RETIRED_TWINS) - set(PAIRS))
    assert not unknown, "RETIRED_TWINS names %s, which no pair is filed under" % unknown


# Pairs whose script is a REGISTERED GATE, mapped to that gate's id. A gate's call site is not one line: it is the `package.json` script, the `---- gate ----` header's own `run:`, and the `scripts/ci-runner/manifest.ts` leaf that has to agree with both. The third family recorded that reach in prose and left it untested, which is how a half-finished cutover reads as a finished one
# -- the workflow assertion above passes on the workflow line alone while `npm run <id>` still shells out to bash.
REGISTERED_GATES = {
    "w7p4b-run-renet": "check:ci-renet",
    "w7p4b-run-account": "check:ci-account-server",
    "w7p4b-typecheck-workers": "lint:unused",
}

# The three files a registered gate's cutover has to reach, beyond the workflow.
GATE_SURFACES = (
    "package.json",
    "scripts/ci-runner/manifest.ts",
    "scripts/ci-runner/gates.lock.json",
)


@pytest.mark.parametrize("pair", sorted(REGISTERED_GATES))
def test_a_registered_gate_is_cut_over_everywhere_it_is_named(pair: str) -> None:
    """The half of a gate cutover a workflow grep cannot see."""
    twin, module, _ = PAIRS[pair]
    for rel in GATE_SURFACES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert twin not in text, (
            "%s still names %s. The workflow line is only one of a registered gate's "
            "call sites; `npm run %s` and the manifest leaf are the others, and a "
            "cutover that moved one of the three leaves the gate running bash."
            % (rel, twin, REGISTERED_GATES[pair])
        )
    # THE HEADER FOLLOWS THE OWNER. While the twin existed the `---- gate ----` block stayed on it, because `scripts/gate-bind.ts` resolves a gate by where its header lives and two files claiming one id would give one gate two owners. A retired twin cannot carry it, so the block MOVED to the port, the way `rediacc_ci.quality.staging_tag_guard` carries its own; the assertion follows
    # it rather than being dropped, which is the direction that keeps `gate:bind --write` from putting an old spelling back into the workflow.
    owner = ROOT / twin
    if pair in RETIRED_TWINS:
        owner = ROOT / ".ci" / (module.replace(".", "/") + ".py")
    header = owner.read_text(encoding="utf-8")
    prefix = "" if pair in RETIRED_TWINS else "# "
    assert ("%srun: " % prefix) in header, (
        "%s no longer carries a `---- gate ----` header `run:` line, which is what "
        "`scripts/gate-bind.ts` emits into the workflow." % owner
    )
    assert ("python3 -m %s" % module) in header, (
        "%s's gate header still runs something other than `python3 -m %s`, so "
        "`gate:bind --write` would put the old spelling back into the workflow the "
        "next time anyone runs it." % (owner, module)
    )


def test_the_registered_gate_table_names_real_pairs() -> None:
    """VACUITY FLOOR on the parametrisation above."""
    unknown = sorted(set(REGISTERED_GATES) - set(PAIRS))
    assert not unknown, "REGISTERED_GATES names %s, which no pair is filed under" % unknown


def test_the_call_site_reader_can_still_see_a_call_site() -> None:
    """CONTROL on the assertion above, which is the only one that can go quiet.

    `_call_site_text` narrows the search from the whole workflow text to `run:` and `with:` values, and a narrowing that returned nothing would pass every cutover assertion in this module for every pair, forever. So one path known to be LIVE has to be visible through it, and the two `breakpoint.yml` mentions of `ci-start-elite.sh` -- a `workflow_dispatch` input description and a
    comment, neither of which runs anything -- have to stay invisible.

    THE WITNESS MOVED ONCE, on 2026-09-20, and that is the hazard this control carries: it used to be `scope-shadow.sh`, which the third family then cut over, at which point the control was asserting that an already-retired path was live. A witness has to be a path NO pair in `PAIRS` names, or the control expires the moment its subject is done. `lint.sh` is that: 41 `.ci/**/*.sh`
    paths remain under a `run:` or `with:` key, and this one is the shortest-lived candidate only if someone ports it, which is when this line is expected to move again.
    """
    text = _call_site_text()
    assert ".ci/scripts/quality/lint.sh" in text, (
        "the call-site reader found no `run:` naming lint.sh, which ci-quality.yml "
        "still runs. Every cutover assertion in this module passes vacuously when "
        "this reader returns nothing."
    )
    assert ".ci/scripts/quality/lint.sh" not in {twin for twin, _, _ in PAIRS.values()}, (
        "the witness path is itself a cut-over pair, so this control will start "
        "asserting that a retired path is live the moment that pair lands."
    )
    assert "tunnel + desktop only" not in text, (
        "a workflow_dispatch input description reached the call-site reader, so it is "
        "reading prose again and the comment-line false positives W7P4-W measured are "
        "back."
    )
