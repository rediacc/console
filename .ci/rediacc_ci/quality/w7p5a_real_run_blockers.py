"""check:ci-w7p5a-real-run-blockers -- FRAGMENT, drafted and driven by a writer
agent outside the real tree (scripts/ and .ci/rediacc_ci/** are outside its
write grant). Intended final home: .ci/rediacc_ci/quality/w7p5a_real_run_blockers.py,
with a thin entry point at .ci/scripts/quality/check_w7p5a_real_run_blockers.py
(see check_go_deps.py / check_worklist_env_registry.py for the split).

WHAT THIS CLOSES. W7P5-a's acceptance ("agent/PLAN-tooling-transformation.md")
requires every one of the 48 deploy/release bash scripts under port to carry
either a K=5 shadow-gate ledger or an allowlist entry with a BLOCKER -- no
third state. The 39 real-run-blocked paths had BLOCKER-shaped reasons that
validated, but only inside .ci/shadow/w7p5a-status.json, a status file nothing
in CI reads. This gate reads .ci/policy/.w7p5a-real-run-blocklist instead
(BLOCKER-gated through the canonical rediacc_ci.core.allowlist validator, same
as every other .ci/policy/ mechanism) and checks it in BOTH directions against
the box's own tracker, so the "no third state" acceptance is an assertion a
machine makes, not a claim a status file's prose makes on its own behalf.

LIVENESS IS IN-GATE (the `.runner-advice-allowlist` / `.profiler-coverage-allowlist`
precedent in docs/agent-reference/suppressions.md, not a
check-suppression-liveness.ts probe): the oracle is whether
.ci/shadow/w7p5a-status.json still records the path as "blocked" rather than
"ledger". An entry whose path graduated to a K=5 ledger is stale here and must
be removed by whoever did that work -- not folded into the baseline.

Two vacuity refusals distinct from the four regular findings: zero entries in
the allowlist, and a missing or unparseable status.json. Both are exit 1 with
the fix named, never a silent pass.

Exit 0: every entry validates, every path still exists, no entry has
graduated to a ledger, and the allowlist and the status file's "blocked" set
are the same set. Exit 1 otherwise, naming every finding. Exit 2 when the
gate's own --selftest fails (controls_first convention).
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Checker, controls_first
from rediacc_ci.core import allowlist
from rediacc_ci.policy_paths import policy_path

ALLOWLIST_NAME = ".w7p5a-real-run-blocklist"


class RefusalError(Exception):
    """The gate cannot reach a verdict. Exit 1, never a silent pass."""


def _status_path(root: pathlib.Path) -> pathlib.Path:
    return root / ".ci" / "shadow" / "w7p5a-status.json"


def _load_status_paths(root: pathlib.Path) -> dict[str, str]:
    """path -> status ("ledger" or "blocked"), from w7p5a-status.json."""
    sp = _status_path(root)
    if not sp.is_file():
        raise RefusalError(
            "%s does not exist. The w7p5a-real-run-blocklist gate cross-checks "
            "against the box's own progress tracker and cannot reach a verdict "
            "without it." % sp
        )
    try:
        data = json.loads(sp.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusalError("%s does not parse as JSON: %s" % (sp, exc)) from exc
    rows = data.get("paths")
    if not isinstance(rows, list) or not rows:
        raise RefusalError(
            "%s has no 'paths' array (or it is empty); nothing to cross-check "
            "against, which is not the same as everything agreeing." % sp
        )
    out: dict[str, str] = {}
    for row in rows:
        p = row.get("path")
        s = row.get("status")
        if isinstance(p, str) and isinstance(s, str):
            out[p] = s
    return out


def run(root: pathlib.Path) -> tuple[list[str], dict[str, int]]:
    """Findings plus a stats dict for the success line. Raises RefusalError."""
    allow_file = policy_path(ALLOWLIST_NAME, root)
    if not allow_file.is_file():
        raise RefusalError(
            "%s does not exist. If W7P5-a's real-run BLOCKER register was "
            "renamed or removed, this gate's registration must move with it." % allow_file
        )
    text = allow_file.read_text()
    entries = allowlist.parse_text(text)
    if not entries:
        raise RefusalError(
            "%s has zero entries. A BLOCKER-gated register with nothing in it "
            "is indistinguishable from a register nobody wired up; if every "
            "W7P5-a real-run path now has a K=5 ledger, delete the file and "
            "its POLICY_FILES registration instead of leaving it empty." % allow_file
        )

    findings: list[str] = []

    # Duplicate detection: parse_text does not itself refuse a repeated entry,
    # and a duplicate would let a later BLOCKER silently shadow an earlier one.
    by_path: dict[str, allowlist.Entry] = {}
    for e in entries:
        if e.entry in by_path:
            findings.append(
                "%s:%d duplicates the entry for %s already declared at line %d"
                % (ALLOWLIST_NAME, e.line, e.entry, by_path[e.entry].line)
            )
            continue
        by_path[e.entry] = e

    # BLOCKER quality, through the one canonical validator.
    findings.extend(allowlist.verify(entries, ALLOWLIST_NAME))

    # Every named path must still exist in the tree.
    for p, e in sorted(by_path.items()):
        if not (root / p).is_file():
            findings.append(
                "%s:%d names %s, which no longer exists in the tree -- delete "
                "the entry, do not leave a BLOCKER for a file that is gone"
                % (ALLOWLIST_NAME, e.line, p)
            )

    status = _load_status_paths(root)
    blocked_in_status = {p for p, s in status.items() if s == "blocked"}
    ledgered_in_status = {p for p, s in status.items() if s == "ledger"}
    allow_paths = set(by_path)

    # STALE: graduated to a ledger but the real-run BLOCKER is still parked here.
    findings.extend(
        "%s still carries a real-run BLOCKER for %s, but "
        ".ci/shadow/w7p5a-status.json now records a K=5 ledger for it. "
        "Remove the stale entry -- do not add it to the baseline." % (ALLOWLIST_NAME, p)
        for p in sorted(allow_paths & ledgered_in_status)
    )

    # THE THIRD STATE, direction one: the box's tracker says "blocked" and
    # this file says nothing at all.
    findings.extend(
        ".ci/shadow/w7p5a-status.json marks %s 'blocked' but %s carries no "
        "entry for it. That is the third state W7P5-a's acceptance forbids "
        "-- a claimed BLOCKER nothing checks." % (p, ALLOWLIST_NAME)
        for p in sorted(blocked_in_status - allow_paths)
    )

    # Direction two: an entry here that the tracker does not know about at all
    # (neither blocked nor ledgered) is a claim with no corresponding box state.
    findings.extend(
        "%s names %s, which .ci/shadow/w7p5a-status.json does not track "
        "at all (neither 'blocked' nor 'ledger')" % (ALLOWLIST_NAME, p)
        for p in sorted(allow_paths - blocked_in_status - ledgered_in_status)
    )

    stats = {
        "entries": len(allow_paths),
        "blocked_in_status": len(blocked_in_status),
        "ledgered_in_status": len(ledgered_in_status),
    }
    return findings, stats


def _write_fixture(
    root: pathlib.Path,
    *,
    allow_text: str
    | None = "# BLOCKER: real reason naming curl against a real endpoint, thirty chars easily\n.ci/scripts/deploy/x.sh\n",
    status_rows: list[dict] | None = None,
    touch_paths: tuple[str, ...] = (".ci/scripts/deploy/x.sh",),
) -> None:
    (root / ".ci" / "policy").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "shadow").mkdir(parents=True, exist_ok=True)
    for rel in touch_paths:
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("#!/usr/bin/env bash\ncurl https://example.invalid\n")
    if allow_text is not None:
        (root / ".ci" / "policy" / ALLOWLIST_NAME).write_text(allow_text)
    if status_rows is None:
        status_rows = [{"path": ".ci/scripts/deploy/x.sh", "status": "blocked"}]
    (root / ".ci" / "shadow" / "w7p5a-status.json").write_text(
        json.dumps({"schema": "w7p5a-status/v1", "paths": status_rows})
    )


def selftest() -> bool:
    check = Checker()

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _write_fixture(root)
        findings, stats = run(root)
        check("CLEAN: a matching entry and a matching 'blocked' row is quiet", findings == [])
        check("CLEAN: stats count the one entry", stats["entries"] == 1)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _write_fixture(root, allow_text=".ci/scripts/deploy/x.sh\n")
        findings, _ = run(root)
        check(
            "PLANT: an entry with no BLOCKER at all reds",
            any("BLOCKER" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _write_fixture(root, allow_text="# BLOCKER: tbd\n.ci/scripts/deploy/x.sh\n")
        findings, _ = run(root)
        check(
            "PLANT: a low-effort BLOCKER ('tbd') reds through the canonical validator",
            any("low-effort" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _write_fixture(root, touch_paths=())
        findings, _ = run(root)
        check(
            "PLANT: an entry naming a path absent from the tree reds",
            any("no longer exists" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _write_fixture(
            root,
            status_rows=[{"path": ".ci/scripts/deploy/x.sh", "status": "ledger"}],
        )
        findings, _ = run(root)
        check(
            "PLANT: an entry whose path graduated to a K=5 ledger is STALE and reds",
            any("K=5 ledger" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _write_fixture(
            root,
            status_rows=[
                {"path": ".ci/scripts/deploy/x.sh", "status": "blocked"},
                {"path": ".ci/scripts/deploy/y.sh", "status": "blocked"},
            ],
        )
        (root / ".ci" / "scripts" / "deploy" / "y.sh").write_text("echo hi\n")
        findings, _ = run(root)
        check(
            "PLANT: THE THIRD STATE -- status.json says 'blocked' with no allowlist entry",
            any("third state" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _write_fixture(root, status_rows=[])
        check("VACUITY: an empty status.json 'paths' array is a REFUSAL", _refuses(root))

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _write_fixture(root)
        (root / ".ci" / "shadow" / "w7p5a-status.json").unlink()
        check("VACUITY: a missing status.json is a REFUSAL", _refuses(root))

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _write_fixture(root, allow_text="")
        check("VACUITY: an allowlist with zero entries is a REFUSAL", _refuses(root))

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _write_fixture(root, allow_text=None)
        check("VACUITY: a missing allowlist file is a REFUSAL", _refuses(root))

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _write_fixture(
            root,
            allow_text=(
                "# BLOCKER: real reason naming curl against a real endpoint, thirty chars\n"
                ".ci/scripts/deploy/x.sh\n"
                ".ci/scripts/deploy/x.sh\n"
            ),
        )
        findings, _ = run(root)
        check("PLANT: a duplicate entry reds", any("duplicates" in f for f in findings))

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _write_fixture(
            root,
            status_rows=[{"path": ".ci/scripts/deploy/OTHER.sh", "status": "blocked"}],
        )
        (root / ".ci" / "scripts" / "deploy" / "OTHER.sh").write_text("echo hi\n")
        findings, _ = run(root)
        check(
            "PLANT: an entry status.json does not track at all (neither blocked nor ledger) reds",
            any("does not track at all" in f for f in findings),
        )

    return not check.ok


def _refuses(root: pathlib.Path) -> bool:
    try:
        run(root)
    except RefusalError:
        return True
    return False


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return controls_first("w7p5a real-run blocklist", selftest)
    root = paths.repo_root()
    try:
        findings, stats = run(root)
    except RefusalError as exc:
        print("✗ %s" % exc, file=sys.stderr)
        return 1
    if findings:
        print("✗ %d w7p5a-real-run-blocklist finding(s):" % len(findings), file=sys.stderr)
        for f in findings:
            print("    %s" % f, file=sys.stderr)
        return 1
    print(
        "✓ %d BLOCKER-gated real-run exemption(s) in %s, agreeing with "
        ".ci/shadow/w7p5a-status.json (%d 'blocked', %d ledgered) -- no third state"
        % (
            stats["entries"],
            ALLOWLIST_NAME,
            stats["blocked_in_status"],
            stats["ledgered_in_status"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
