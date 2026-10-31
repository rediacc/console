"""The W7P5-a DRY-RUN ledgers, and what keeps them evidence.

W7P5-a's acceptance gave every deploy/release script a K=5 shadow-gate ledger. The dry-run half -- bash twin against Python port, every external tool stubbed -- was reachable without touching production, and for the Cloudflare/R2 family it was driven and recorded under the `w7p5a-` pair namespace. The real-run BLOCKER register that once sat beside these ledgers is retired with the last bash twins.

`.ci/shadow/w7p5a-status.json` carries that evidence as a `dry_run_ledger` field. This module is what stops the field decaying into a claim. The three sweeps below police the evidence itself; the set is empty today, and `test_the_dry_run_evidence_set_is_retired` is the floor that keeps it so until a pair is recorded again:

  * THE EVIDENCE IS REAL. Each named ledger must hold at least five rows, every one EQUIVALENT, over at least five DISTINCT clean tree ids and at least five DISTINCT finding-set fingerprints -- `assertEquivalent`'s rule, restated where a pytest sweep runs it. Nothing in CI invokes `shadow-gate --assert` for these pairs, so without this the ledgers vouch for themselves.
  * THE EVIDENCE IS ABOUT THE RIGHT PAIR. Each row's `old.cmd` must name the bash path the row is filed under and its `new.cmd` the Python port. A ledger is a text file; a row copied from a neighbouring pair would otherwise satisfy every count above.
  * THE COMPARISON WAS WIDER THAN THE TWO STREAMS. Each row must agree on at least one `[call]` finding, which is the recording stub's log of the exact argv the run sent to `curl` or `aws`. Two implementations can print identical lines while issuing different requests, and a ledger that only compared stdout could not tell them apart.

THE PORTS ARE NOT RE-TESTED HERE. Every script named by a `dry_run_ledger` already has a permanent side-by-side differential of its own -- `test_deploy_cf_purge_urls.py` for the first of them, and one `test_<family>_<stem>.py` for each of the rest -- driving the twin and the port through recording fakes. Repeating them would buy nothing; what was missing is enforcement of the
LEDGERS those runs produced.

THE SET OF LEDGERED PATHS IS PINNED BELOW rather than read from the status file alone. Every test above is parameterised over whatever rows carry the field, so deleting a field would retire that path's enforcement in silence and leave a green module behind; `EXPECTED_DRY_RUN_PATHS` is what turns that deletion into a red.
"""

from __future__ import annotations

import json
import pathlib

from rediacc_ci import paths

ROOT = paths.repo_root()
STATUS = pathlib.Path(ROOT) / ".ci" / "shadow" / "w7p5a-status.json"

# The shadow-gate rule these ledgers were recorded to satisfy.
K = 5

# A path LEAVES this table in the same change that graduates its row to `status: "ledger"` (the real run happened, so the `dry_run_*` fields go with it); `verify-edge-endpoints`, `verify-stable-endpoints` and `assert-edge-tag-exists` graduated on 2026-09-23 without that edit and left this module red.
# Every path whose dry-run half has been driven and recorded, and the external tool whose argv the row's `[call]` findings must therefore carry. The tool is the one the path's real-run branch reaches for, so this table is also the check that a ledger recorded the RIGHT script's traffic: `mark-production` agreeing only on `curl` lines would mean the fixture answered a neighbour's probes.
#
# Retired 2026-10-08: delete-r2-channel.sh (commit cf878bca0) and assert-artifact-version.sh (commit ebaefca60) were the last two rows, and both twins are deleted after their goldens froze. The ledgers stay under .ci/shadow as records; their status rows left w7p5a-status.json with the twins. A row recorded here again would restore the entries and the sweeps below.
EXPECTED_DRY_RUN_PATHS: dict[str, tuple[str, ...]] = {}


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


def test_the_dry_run_evidence_set_is_retired() -> None:
    """RETIREMENT FLOOR. Every twin a dry-run ledger attested to is deleted, so no status row may still carry a `dry_run_ledger`; a row that did would name a script nothing can run. The sweeps below are parameterised over such rows and are empty by design until one is recorded again."""
    rows = _dry_run_rows()
    assert not rows, (
        "%s carries a `dry_run_ledger` on %s, but %s lists no expected dry-run path. "
        "Add the path to EXPECTED_DRY_RUN_PATHS in the same change that records it."
        % (STATUS, [r["path"] for r in rows], "EXPECTED_DRY_RUN_PATHS")
    )
    assert not EXPECTED_DRY_RUN_PATHS


def test_no_ledgered_path_quietly_loses_its_field() -> None:
    """THE PARAMETERISATION CANNOT POLICE ITSELF. Dropping `dry_run_ledger` from a row removes that path from every `_ids()` sweep above, and the module stays green while one script's evidence is no longer checked at all. Recording a pair is an addition here, which is a one-line edit; losing one is a red."""
    missing = sorted(set(EXPECTED_DRY_RUN_PATHS) - set(_ids()))
    assert not missing, (
        "%s no longer carries a `dry_run_ledger` in %s. The field was recorded from a "
        "real shadow-gate run; if the ledger was genuinely retired, retire it here in "
        "the same change rather than leaving this module asserting nothing about it."
        % (missing, STATUS.name)
    )
