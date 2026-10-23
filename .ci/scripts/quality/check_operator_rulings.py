#!/usr/bin/env python3
"""check:ci-operator-rulings -- the `## Rulings (machine-checked)` section of agent/RULES.md is byte-equal to the ruling ledger.

WHY (agent/plans/PLAN-stop-hook-rulings-campaign.md section 2). An operator ruling lives twice: as rows in `agent/rulings/<session>.jsonl`, which the Stop hook's checks consult before firing, and as a rendered list in `agent/RULES.md`, which every session reads. `worklist.py --rule` writes both under one lock. A hand edit of the rendered list, a ledger row added without the render, or a merge that took one side's
RULES.md and both sides' ledgers would leave the document a reader trusts disagreeing with what the hook actually obeys: a cache that can lie, the shape wl_planindex refuses for the plan census. This gate is that refusal.

THE RENDER IS NOT HERE. It lives in `.claude/hooks/stop/wl_ruling.py` (`render_section`, `read_ledger`, `extract_section`), imported through `paths.hooks_stop_dir` the way check_plan_deps.py imports its grammar, so the writer and the checker are one function and cannot disagree about a byte.

FINDINGS:

    O1  agent/RULES.md is missing, or carries no complete generated block (both markers, in order)
    O2  a ledger row is not JSON or is malformed (wl_ruling.row_problem)
    O3  the block differs from the render of the ledger; the diff is printed

An EMPTY ledger is a real state with a real render (`(no ruling recorded)`), so it is still a byte comparison and never a vacuous pass: a block listing a ruling the ledger lacks fails O3.

Every run executes the planted controls first and refuses a verdict when one fails.

Exit codes: 0 green, 1 findings, 2 a control failed or bad usage, 77 cannot run.

---- gate ----
step: Operator rulings
needs: none
selftest: true
lane: quality-branch
why: an operator ruling binds a Stop check through the ledger and a reader through
     agent/RULES.md; the two must never disagree, or the document a session trusts
     says one thing while the hook obeys another.
---- end gate ----
"""

from __future__ import annotations

import difflib
import json
import pathlib
import sys
import tempfile

import _cipath
from rediacc_ci import paths

paths.on_sys_path(paths.hooks_stop_dir())

try:
    import wl_ruling as R
except ImportError as _exc:  # pragma: no cover -- a tree without .claude/hooks/stop
    print(
        "CANNOT RUN: cannot import the ruling render wl_ruling from %s (%s)."
        % (paths.hooks_stop_dir(), _exc),
        file=sys.stderr,
    )
    sys.exit(77)

ROOT = _cipath.CI_DIR.parent


def verdict(root: pathlib.Path) -> list[str]:
    """The findings for one tree, empty when the block equals the render."""
    rules = root / "agent" / R.RULES_MD_NAME
    directory = root / "agent" / R.RULINGS_DIR_NAME
    findings: list[str] = []
    rows, problems = R.read_ledger(directory)
    findings.extend("O2 %s/%s" % (directory.relative_to(root), p) for p in problems)
    if not rules.is_file():
        findings.append("O1 %s does not exist" % rules.relative_to(root))
        return findings
    have = R.extract_section(rules.read_text(encoding="utf-8"))
    if have is None:
        findings.append(
            "O1 %s carries no complete generated block (%r ... %r)"
            % (rules.relative_to(root), R.BEGIN[:24], R.END)
        )
        return findings
    want = R.render_section(rows)
    if have != want:
        diff = "".join(
            difflib.unified_diff(
                have.splitlines(keepends=True),
                want.splitlines(keepends=True),
                "%s (as committed)" % rules.relative_to(root),
                "render of %s/*.jsonl" % directory.relative_to(root),
            )
        )
        findings.append(
            "O3 the generated block differs from the ledger's render. Re-render it by "
            "recording through `worklist.py --rule`, never by hand:\n" + diff
        )
    return findings


def _plant(base: pathlib.Path, rows: list[dict], block: str | None) -> pathlib.Path:
    agent = base / "agent"
    (agent / R.RULINGS_DIR_NAME).mkdir(parents=True, exist_ok=True)
    if rows:
        (agent / R.RULINGS_DIR_NAME / "c0ffee00.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
    if block is not None:
        (agent / R.RULES_MD_NAME).write_text(
            "# RULES\n\nprose\n\n" + R.SECTION_HEADING + "\n\n" + block, encoding="utf-8"
        )
    return base


def controls() -> list[str]:
    """Planted fixtures, each with the finding it must (or must not) produce. Returns the failures."""
    rule = R.rule_row("c0ffee00", "submodule", "private/account@aea435154", "KEEP, rides 1023-1")
    revoke = R.revoke_row("c0ffee00", rule["id"], "the pointer moved on")
    cases: list[tuple[str, list[dict], str | None, str]] = [
        ("an empty ledger and its render agree", [], R.render_section([]), ""),
        ("one ruling and its render agree", [rule], R.render_section([rule]), ""),
        (
            "a revoked ruling and its render agree",
            [rule, revoke],
            R.render_section([rule, revoke]),
            "",
        ),
        ("a ledger row the block lacks", [rule], R.render_section([]), "O3"),
        ("a block listing a ruling the ledger lacks", [], R.render_section([rule]), "O3"),
        (
            "a revoke the block does not show",
            [rule, revoke],
            R.render_section([rule]),
            "O3",
        ),
        (
            "a hand edit inside the block",
            [rule],
            R.render_section([rule]).replace("KEEP", "DROP"),
            "O3",
        ),
        ("no generated block at all", [], "", "O1"),
        ("no RULES.md", [], None, "O1"),
        ("a malformed row", [dict(rule, sig="0" * 16)], R.render_section([]), "O2"),
    ]
    failures = []
    for label, rows, block, want in cases:
        with tempfile.TemporaryDirectory() as tmp:
            got = verdict(_plant(pathlib.Path(tmp), rows, block))
        codes = {g[:2] for g in got}
        if (want and want not in codes) or (not want and got):
            failures.append("CONTROL %r: wanted %r, got %r" % (label, want or "green", got))
    return failures


def main(argv: list[str]) -> int:
    root = ROOT
    selftest = False
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--selftest":
            selftest = True
        elif arg == "--root" and args:
            root = pathlib.Path(args.pop(0)).resolve()
        else:
            print("usage: check_operator_rulings.py [--selftest] [--root <dir>]", file=sys.stderr)
            return 2
    failed = controls()
    if failed:
        print("\n".join(failed), file=sys.stderr)
        print("%d control(s) failed; no verdict rendered" % len(failed), file=sys.stderr)
        return 2
    if selftest:
        print("operator rulings: 10 planted control(s) passed")
        return 0
    findings = verdict(root)
    rows, _problems = R.read_ledger(root / "agent" / R.RULINGS_DIR_NAME)
    if findings:
        print("\n".join(findings), file=sys.stderr)
        print("operator rulings: %d finding(s)" % len(findings), file=sys.stderr)
        return 1
    print(
        "operator rulings: agent/RULES.md block equals the render of %d ledger row(s) "
        "(%d live ruling(s)); 10 planted control(s) passed" % (len(rows), len(R.live_rulings(rows)))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
