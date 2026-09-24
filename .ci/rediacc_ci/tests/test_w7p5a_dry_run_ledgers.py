"""The W7P5-a DRY-RUN ledgers, and the one thing they must never be read as saying.

W7P5-a's acceptance gives every deploy/release script two doors: a K=5 shadow-gate ledger, or a BLOCKER entry in `.ci/policy/.w7p5a-real-run-blocklist`. Thirty-two paths took the second door because their real-run leg needs Cloudflare, R2, GitHub or D1 credentials no session has.

That blocker is about the REAL RUN and nothing else. The dry-run half -- bash twin against Python port, every external tool stubbed -- is reachable without touching production, and for the Cloudflare/R2 family it has been driven and recorded under the `w7p5a-` pair namespace.

`.ci/shadow/w7p5a-status.json` carries that evidence as a `dry_run_ledger` field on a still-`blocked` row. This module is what stops the field decaying into a claim, in both directions:

  * THE EVIDENCE IS REAL. Each named ledger must hold at least five rows, every one EQUIVALENT, over at least five DISTINCT clean tree ids and at least five DISTINCT finding-set fingerprints -- `assertEquivalent`'s rule, restated where a pytest sweep runs it. Nothing in CI invokes `shadow-gate --assert` for these pairs, so without this the ledgers vouch for themselves.
  * THE EVIDENCE IS ABOUT THE RIGHT PAIR. Each row's `old.cmd` must name the bash path the row is filed under and its `new.cmd` the Python port. A ledger is a text file; a row copied from a neighbouring pair would otherwise satisfy every count above.
  * THE COMPARISON WAS WIDER THAN THE TWO STREAMS. Each row must agree on at least one `[call]` finding, which is the recording stub's log of the exact argv the run sent to `curl` or `aws`. Two implementations can print identical lines while issuing different requests, and a ledger that only compared stdout could not tell them apart.
  * AND IT IS STILL ONLY A DRY RUN. A path carrying a `dry_run_ledger` must still be `status: "blocked"` and must still be listed in the blocklist. That is the assertion that matters most here: a future reader must not be able to promote stubbed evidence into "the real run happened" by deleting a line, and the blocklist's own liveness clause reads the same `status` field.

THE PORTS ARE NOT RE-TESTED HERE. Every script named by a `dry_run_ledger` already has a permanent side-by-side differential of its own -- `test_deploy_cf_purge_urls.py` for the first of them, and one `test_<family>_<stem>.py` for each of the rest -- driving the twin and the port through recording fakes. Repeating them would buy nothing; what was missing is enforcement of the
LEDGERS those runs produced.

THE SET OF LEDGERED PATHS IS PINNED BELOW rather than read from the status file alone. Every test above is parameterised over whatever rows carry the field, so deleting a field would retire that path's enforcement in silence and leave a green module behind; `EXPECTED_DRY_RUN_PATHS` is what turns that deletion into a red.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from rediacc_ci import paths

ROOT = paths.repo_root()
STATUS = pathlib.Path(ROOT) / ".ci" / "shadow" / "w7p5a-status.json"
BLOCKLIST = pathlib.Path(ROOT) / ".ci" / "policy" / ".w7p5a-real-run-blocklist"

# The shadow-gate rule these ledgers were recorded to satisfy.
K = 5

# A path LEAVES this table in the same change that graduates its row to `status: "ledger"` (the real run happened, so the `dry_run_*` fields go with the BLOCKER); `verify-edge-endpoints`, `verify-stable-endpoints` and `assert-edge-tag-exists` graduated on 2026-09-23 without that edit and left this module red.
# Every path whose dry-run half has been driven and recorded, and the external tool whose argv the row's `[call]` findings must therefore carry. The tool is the one named in that path's BLOCKER line, so this table is also the check that a ledger recorded the RIGHT script's traffic: `mark-production` agreeing only on `curl` lines would mean the fixture answered a neighbour's probes.
EXPECTED_DRY_RUN_PATHS = {
    ".ci/scripts/deploy/delete-r2-channel.sh": ("aws",),
    ".ci/scripts/deploy/promote-docker-to-stable-hotfix.sh": ("docker",),
    ".ci/scripts/deploy/promote-r2-to-stable.sh": ("aws", "curl"),
    ".ci/scripts/deploy/purge-media-cache.sh": ("curl",),
    ".ci/scripts/release/assert-artifact-version.sh": ("gh",),
    ".ci/scripts/release/create-github-release.sh": ("gh",),
    ".ci/scripts/release/mark-production.sh": ("gh",),
}


def _status_rows() -> list[dict]:
    return json.loads(STATUS.read_text())["paths"]


def _dry_run_rows() -> list[dict]:
    return [r for r in _status_rows() if r.get("dry_run_ledger")]


def _ledger_rows(rel: str) -> list[dict]:
    text = (pathlib.Path(ROOT) / rel).read_text()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _ids() -> list[str]:
    return [r["path"] for r in _dry_run_rows()]


def _row_for(path: str) -> dict:
    return next(r for r in _dry_run_rows() if r["path"] == path)


def test_the_dry_run_evidence_set_is_not_empty() -> None:
    """VACUITY FLOOR. Every test below is parameterised over the rows carrying a `dry_run_ledger`, so an empty set would turn this whole module green while checking nothing -- the exact shape of a gate that cannot fail."""
    rows = _dry_run_rows()
    assert rows, (
        "no row in %s carries a `dry_run_ledger`. Either the field was removed or "
        "this module is parameterised over nothing; a green run here would assert "
        "nothing at all." % STATUS
    )


@pytest.mark.parametrize("path", _ids())
def test_named_ledger_exists_and_holds_k_equivalent_rows(path: str) -> None:
    row = _row_for(path)
    rel = row["dry_run_ledger"]
    ledger = pathlib.Path(ROOT) / rel
    assert ledger.is_file(), "%s names %s, which does not exist" % (path, rel)

    rows = _ledger_rows(rel)
    assert len(rows) >= K, "%s holds %d row(s); K=%d is required" % (rel, len(rows), K)

    verdicts = sorted({r["verdict"] for r in rows})
    assert verdicts == ["EQUIVALENT"], (
        "%s carries non-EQUIVALENT verdict(s) %s. A ledger is evidence only while "
        "every row agrees; a disagreeing tree is never cleared by a later one." % (rel, verdicts)
    )

    # `tree.clean` is the whole point of rule 4: a row from a dirty tree is not reproducible and is not evidence.
    dirty = [r["tree"]["id"][:12] for r in rows if not r["tree"].get("clean")]
    assert not dirty, "%s carries row(s) recorded on a DIRTY tree: %s" % (rel, dirty)

    trees = {r["tree"]["id"] for r in rows}
    assert len(trees) >= K, "%s spans %d distinct tree(s); K=%d is required" % (
        rel,
        len(trees),
        K,
    )

    # Distinct finding sets, so five repetitions of one scenario cannot pass for five observations.
    prints = {r["old"]["fingerprint"] for r in rows}
    assert len(prints) >= K, (
        "%s spans only %d distinct finding set(s) over %d rows: the same scenario "
        "recorded on five trees is one observation, not five." % (rel, len(prints), len(rows))
    )


@pytest.mark.parametrize("path", _ids())
def test_every_row_names_the_pair_it_is_filed_under(path: str) -> None:
    row = _row_for(path)
    rel = row["dry_run_ledger"]
    pair = row["dry_run_pair"]
    stem = pathlib.PurePath(path).stem.replace("-", "_")
    # THE FAMILY IS READ OFF THE PATH, NOT ASSUMED. This was `deploy` verbatim while every ledgered pair happened to be a deploy script; the first release/ pair would have been asserted against a port path that does not exist, and the red would have named a missing module rather than the wrong constant.
    family = pathlib.PurePath(path).parent.name
    port = ".ci/rediacc_ci/%s/%s.py" % (family, stem)

    for n, r in enumerate(_ledger_rows(rel), 1):
        assert r["pair"] == pair, "%s row %d is filed under pair %r, not %r" % (
            rel,
            n,
            r["pair"],
            pair,
        )
        assert path in r["old"]["cmd"], (
            "%s row %d does not invoke %s on the old side; the row attests to a "
            "different script than the one it is filed under" % (rel, n, path)
        )
        assert port in r["new"]["cmd"], "%s row %d does not invoke %s on the new side" % (
            rel,
            n,
            port,
        )
        assert "PYTHONDONTWRITEBYTECODE=1" in r["new"]["cmd"], (
            "%s row %d ran the port without PYTHONDONTWRITEBYTECODE=1, which drops "
            "__pycache__ into the recorded tree and makes the NEXT row's clean-tree "
            "check a coin toss" % (rel, n)
        )


@pytest.mark.parametrize("path", _ids())
def test_the_external_call_log_was_part_of_the_comparison(path: str) -> None:
    """A run that agreed on stdout while calling Cloudflare differently is the failure this prefix exists to catch, so at least one row must actually carry a `[call]` finding. Rows with none are scenarios that refused before reaching a tool, which is legitimate -- a ledger with none is not."""
    row = _row_for(path)
    rel = row["dry_run_ledger"]
    rows = _ledger_rows(rel)

    with_calls = [r for r in rows if any("[call] " in a for a in r["agreed"])]
    assert with_calls, (
        "no row in %s agreed on a single `[call]` line. Either every scenario refused "
        "before invoking a tool, or the call log was never folded into the finding "
        "set -- in both cases the external requests are uncompared." % rel
    )

    for n, r in enumerate(rows, 1):
        assert r["agreed"], "%s row %d agreed on nothing; that is VACUOUS_BOTH_EMPTY" % (rel, n)
        assert any(a.startswith("[error] [exit] ") for a in r["agreed"]), (
            "%s row %d carries no `[exit]` line, so the two sides' status codes were "
            "never re-emitted into the compared set" % (rel, n)
        )


@pytest.mark.parametrize("path", _ids())
def test_a_dry_run_ledger_never_closes_the_real_run_leg(path: str) -> None:
    """The load-bearing one. Stubbed evidence must not be readable as a real run: the row stays `blocked`, and the BLOCKER entry stays in the policy file that CI checks."""
    row = _row_for(path)
    assert row["status"] == "blocked", (
        "%s carries a dry_run_ledger AND status %r. A stub run is a dry-run claim "
        "only; flipping the status here would retire the real-run BLOCKER on evidence "
        "that never touched Cloudflare, R2, GitHub or D1." % (path, row["status"])
    )
    assert row.get("blocker", "").startswith("BLOCKER:"), (
        "%s is 'blocked' with no BLOCKER reason" % path
    )
    entries = [
        line.strip()
        for line in BLOCKLIST.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert path in entries, (
        "%s is 'blocked' in %s but carries no entry in %s. The blocklist gate reads "
        "that file, not this one." % (path, STATUS.name, BLOCKLIST.name)
    )


@pytest.mark.parametrize("path", _ids())
def test_the_note_does_not_claim_a_real_run(path: str) -> None:
    """`check_w7p5a_real_run_blockers.py` treats the phrase "real run each done directly" in a `ledger`-status note as CONFIRMATION that the real leg ran. A dry-run note borrowing that wording would be a false confirmation waiting for the row's status to change."""
    row = _row_for(path)
    blob = " ".join(str(row.get(k, "")) for k in ("note", "dry_run_ledger_note"))
    assert "real run each done directly" not in blob, (
        "%s's dry-run note uses the phrase the blocklist gate reads as a confirmed real run" % path
    )


def test_no_ledgered_path_quietly_loses_its_field() -> None:
    """THE PARAMETERISATION CANNOT POLICE ITSELF. Dropping `dry_run_ledger` from a row removes that path from every `_ids()` sweep above, and the module stays green while one script's evidence is no longer checked at all. Recording a pair is an addition here, which is a one-line edit; losing one is a red."""
    missing = sorted(set(EXPECTED_DRY_RUN_PATHS) - set(_ids()))
    assert not missing, (
        "%s no longer carries a `dry_run_ledger` in %s. The field was recorded from a "
        "real shadow-gate run; if the ledger was genuinely retired, retire it here in "
        "the same change rather than leaving this module asserting nothing about it."
        % (missing, STATUS.name)
    )


@pytest.mark.parametrize("path", sorted(EXPECTED_DRY_RUN_PATHS))
def test_the_ledger_carries_the_tool_the_blocker_names(path: str) -> None:
    """A ledger proves something about the RIGHT script only if the traffic it agreed on is that script's. Each path's BLOCKER names the external system its real-run leg reaches for, so the recorded call log must carry that tool's argv; a fixture wired to the wrong probes, or a row copied in from a neighbouring pair, agrees on somebody else's."""
    rel = _row_for(path)["dry_run_ledger"]
    logged = {
        agreed.split("[call] ", 1)[1].split()[0]
        for row in _ledger_rows(rel)
        for agreed in row["agreed"]
        if "[call] " in agreed and agreed.split("[call] ", 1)[1].split()
    }
    for tool in EXPECTED_DRY_RUN_PATHS[path]:
        assert tool in logged, (
            "%s agreed on no `[call] %s ...` line, yet %s's real-run branch is blocked "
            "on exactly that tool. The recorded calls were %s."
            % (rel, tool, path, sorted(logged) or "none")
        )
