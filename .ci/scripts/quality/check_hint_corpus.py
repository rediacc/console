#!/usr/bin/env python3
"""check:ci-hint-corpus -- the behavioral-hint corpus is well-formed and its rotation actually rotates.

WHY THIS EXISTS. `docs/agent-reference/HINTS.md` is hand-curated prose read by `wl_hints.hint_pick` on every allow-path stop; nothing about its shape is enforced except by this gate. Same governing principle as `check_agent_hint_liveness.py`, its named model: "A healthy matcher on a quiet stop emits nothing, exactly like a broken one.
Counting hints cannot separate them." A rotation that always emits the SAME hint, or that silently drops one from the cycle, looks identical from the stop report's own output to a healthy one -- the report shows one line either way. So this gate drives `hint_pick` directly, over the whole cycle, and asserts every active entry is actually reachable and the cycle actually repeats.

CONTROL-FIRST, same shape as the model.
Before the real corpus is judged at all, every assertion below is driven against a synthetic fixture carrying one planted defect apiece -- a corpus under the population floor, a duplicate id, a malformed id, an oversized or first-person heading, a Source pointing at a file that does not exist, and a hint_pick stubbed to return a constant -- plus one healthy fixture that must stay silent under all six.
If any plant is not caught, this gate declares itself broken and exits non-zero WITHOUT judging the real corpus.

Design: agent/plans/PLAN-stop-hook-behavioral-hints.md section 6.3;
agent/plans/PLAN-hint-corpus-ci-assertions.md (this gate's own design).

---- gate ----
step: Behavioral hints can actually fire
needs: none
selftest: true
lane: quality-content
---- end gate ----
"""

from __future__ import annotations

import contextlib
import os
import re
import sys
import tempfile
from typing import Any

import _cipath  # noqa: F401
from rediacc_ci import paths

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
HOOK_DIR = os.path.join(REPO_ROOT, ".claude", "hooks", "stop")
HINTS_FILE = os.path.join(REPO_ROOT, "docs", "agent-reference", "HINTS.md")

MIN_HINTS = 8  # H1, the number section 6.3 names literally
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,48}$")  # H2
HEADING_MAX = 160  # H4, matches HINTS.md's own schema line at HINTS.md:12
PRONOUN_RE = re.compile(
    r"(?<![\w'-])(i|i'm|i've|i'd|i'll|me|my|mine|myself|you|you're|you've|you'll|"
    r"your|yours|yourself|we|we're|we've|us|our|ours)(?![\w'-])",
    re.IGNORECASE,
)
POINTER_KIND = {"file": "fileline", "gate": "gate", "trap": "trap", "plan": "plan"}

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"


def die(msg: str) -> None:
    print(f"{RED}✗{NC} {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_hints():
    """Import wl_hints and wl_planrec with contract guards."""
    if not os.path.isdir(HOOK_DIR):
        die(f"{HOOK_DIR} not found; cannot judge a matcher that is not there")
    if not os.path.isfile(os.path.join(HOOK_DIR, "wl_hints.py")):
        die(
            f"{HOOK_DIR}/wl_hints.py not found. The hint module is gone or renamed; "
            "fix the wiring deliberately rather than letting this gate pass over its absence."
        )
    paths.on_sys_path(HOOK_DIR)
    try:
        import wl_hints  # noqa: PLC0415
        import wl_planrec as plan_r  # noqa: PLC0415
    except ImportError as exc:
        die(
            f"cannot import wl_hints or wl_planrec ({exc}). Refusing to pass while measuring nothing."
        )
    for fn in ("hints_path", "load_corpus", "hint_pick", "render"):
        if not hasattr(wl_hints, fn):
            die(
                f"wl_hints.{fn}() is missing (renamed? removed?). The hint module's frozen "
                "contract changed; update this gate deliberately rather than letting it pass."
            )
    if not hasattr(plan_r, "resolve"):
        die(
            "wl_planrec.resolve() is missing. Cannot verify source pointers; "
            "update this gate deliberately."
        )
    return wl_hints, plan_r


def source_pointers(value):
    """[(kind, token), ...] for one Source: field, or [(None, ptr)] for an unrecognised prefix."""
    out = []
    for raw in (value or "").split(","):
        ptr = raw.strip()
        if not ptr:
            continue
        prefix, sep, rest = ptr.partition(":")
        kind = POINTER_KIND.get(prefix)
        out.append((kind, rest.strip() if sep and kind else ptr))
    return out


def judge_corpus(hints_mod, entries, parse_errors):
    """H1 through H4 assertions on the corpus."""
    out = list(
        parse_errors
    )  # load_corpus's own errors: empty heading/id/source, duplicate id -- half of H2
    active = [e for e in entries if e.get("status") == "active"]

    # H1 population floor
    if len(active) < MIN_HINTS:
        out.append(
            "POPULATION FLOOR: %d active entries, under MIN_HINTS=%d. An emptied, "
            "truncated or relocated corpus reds instead of passing vacuously."
            % (len(active), MIN_HINTS)
        )

    for e in entries:
        eid = e.get("id") or ""
        heading = e.get("heading") or ""
        # H2 identity: format, over and above load_corpus's own duplicate/empty checks
        if eid and not ID_RE.match(eid):
            out.append("MALFORMED ID: %r does not match ^[a-z0-9][a-z0-9-]{2,48}$" % eid)
        # H3 grounding
        if eid and e.get("source"):
            for kind, token in source_pointers(e["source"]):
                if kind is None:
                    out.append(
                        "%s: Source pointer %r carries no recognised kind prefix" % (eid, token)
                    )
                    continue
                ok, why = hints_mod.resolve(REPO_ROOT, kind, token) if hints_mod else (False, "")
                if not ok:
                    out.append("%s: Source %s:%s does not resolve -- %s" % (eid, kind, token, why))
        # H4 shape
        if heading:
            if len(heading) > HEADING_MAX:
                out.append(
                    "%s: heading is %d chars, over %d" % (eid or "?", len(heading), HEADING_MAX)
                )
            m = PRONOUN_RE.search(heading)
            if m:
                out.append("%s: heading carries the pronoun %r" % (eid or "?", m.group(0)))
    return out


def cycle_findings(pick_fn, entries):
    """Findings from driving pick_fn(entries, ledger) for one full cycle plus one more pick.

    pick_fn defaults to wl_hints.hint_pick; a control passes a stub instead, so this same
    function is both the real gate's H5/H6 judge and the thing CONTROL 5 proves can fail.
    """
    active = [e for e in entries if e.get("status") == "active"]
    if not active:
        return []  # H1 already reports an empty/under-floor corpus; this function does not pile on
    ledger: dict[Any, Any] = {}
    picks: list[Any] = []
    for _ in range(len(active)):
        got = pick_fn(entries, ledger)
        if got is None:
            return [
                "H5: hint_pick returned None before a full cycle of %d active entries "
                "completed (picked %d)" % (len(active), len(picks))
            ]
        entry, _index, _total = got
        picks.append(entry["id"])
    out = []
    if len(set(picks)) != len(picks):
        out.append("H5: hint_pick repeated an id inside one cycle: %r" % picks)
    active_ids = {e["id"] for e in active}
    if set(picks) != active_ids:
        out.append(
            "H5: hint_pick never surfaced %s over one full cycle" % sorted(active_ids - set(picks))
        )
    extra = pick_fn(entries, ledger)
    if extra is None:
        out.append(
            "H6: hint_pick returned None immediately after a full cycle; the rotation must repeat forever"
        )
    elif extra[0]["id"] == picks[-1]:
        out.append(
            "H6: the pick right after a cycle boundary repeated the hint that just closed "
            "the cycle (%s), which a back-to-back repeat must never do" % picks[-1]
        )
    return out


def write_hint(path: str, hint_id: str, heading: str, source: str) -> None:
    """Write one hint entry in HINTS.md format."""
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"## {heading}\n\nHint-Id: {hint_id}\nSource: {source}\nStatus: active\n\n")


def controls_fired(hints_mod, plan_r):
    """Drive the matcher and this gate's evaluator against planted defects.

    Returns the list of planted defects that were NOT caught. Anything in it means the instrument cannot fail, so no verdict may be issued.
    """
    missed: list[str] = []

    # Healthy fixture: 9 entries (one above MIN_HINTS)
    healthy_entries = [
        (
            "investigate-with-fan-out",
            "Investigate questions with them by default, launching multiple agents in parallel",
            "file:CLAUDE.md:1, trap:check-cannot-fail",
        ),
        ("plan-with-them", "Plan with them on anything non-trivial", "file:CLAUDE.md:1"),
        (
            "writing-agents",
            "Writing agents: at most 2 at a time, with disjoint file ownership",
            "file:CLAUDE.md:1",
        ),
        (
            "spot-check-output",
            "Spot-check every agent's output against the artifact",
            "file:CLAUDE.md:1",
        ),
        (
            "model-by-task-shape",
            "Model choice is by task SHAPE, never by language or domain",
            "file:CLAUDE.md:1",
        ),
        (
            "verify-load-bearing",
            "Verify the load-bearing ones before relying on them",
            "file:CLAUDE.md:1",
        ),
        (
            "run-real-thing",
            "Run the real thing. Output, exit-code, and error-path defects",
            "file:CLAUDE.md:1",
        ),
        (
            "cannot-be-done-probe",
            "Cannot be done here is a claim, so probe it before making it",
            "file:CLAUDE.md:1",
        ),
        (
            "gate-that-ran",
            "Name the gates that ran, and the ones that were skipped",
            "file:CLAUDE.md:1",
        ),
    ]

    def make_fixture(entries_list):
        """Create a temp HINTS.md file and load it."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as fh:
            path = fh.name
            fh.write("# Hints\n\n")
            for hint_id, heading, source in entries_list:
                fh.write(f"## {heading}\nHint-Id: {hint_id}\nSource: {source}\nStatus: active\n\n")
        try:
            entries, errors = hints_mod.load_corpus(path)
            return path, entries, errors
        finally:
            pass

    def judge(entries_list):
        """Load fixture and judge it with both evaluators."""
        path, entries, errors = make_fixture(entries_list)
        try:
            return judge_corpus(plan_r, entries, errors) + cycle_findings(
                hints_mod.hint_pick, entries
            )
        finally:
            with contextlib.suppress(Exception):
                os.unlink(path)

    # CONTROL 0: on a HEALTHY fixture the evaluator must be silent
    findings = judge(healthy_entries)
    if findings:
        die(
            "CONTROL 0 FAILED: the evaluator reported findings on a healthy synthetic "
            f"corpus, so every planted-defect result below is meaningless: {findings}"
        )

    # CONTROL 1 (H1): population floor
    trimmed = healthy_entries[:3]
    findings = judge(trimmed)
    if not any(f.startswith("POPULATION FLOOR") for f in findings):
        missed.append("a corpus under MIN_HINTS was not reported POPULATION FLOOR")

    # CONTROL 2 (H2a): duplicate id
    dup_entries = list(healthy_entries)
    dup_entries[1] = (dup_entries[0][0], dup_entries[1][1], dup_entries[1][2])  # reuse entry 0's id
    findings = judge(dup_entries)
    if not any("duplicate" in f.lower() for f in findings):
        missed.append("a duplicate Hint-Id was not reported in findings")

    # CONTROL 3 (H2b): malformed id
    bad_id_entries = list(healthy_entries)
    bad_id_entries[0] = ("Record_The_Order", bad_id_entries[0][1], bad_id_entries[0][2])
    findings = judge(bad_id_entries)
    if not any(f.startswith("MALFORMED ID") for f in findings):
        missed.append("a malformed Hint-Id was not reported MALFORMED ID")

    # CONTROL 4 (H3): unresolvable source
    bad_source_entries = list(healthy_entries)
    bad_source_entries[0] = (
        bad_source_entries[0][0],
        bad_source_entries[0][1],
        "file:docs/agent-reference/DOES-NOT-EXIST-PLANTED.md:1",
    )
    findings = judge(bad_source_entries)
    if not any("does not resolve" in f for f in findings):
        missed.append("an unresolvable Source was not reported 'does not resolve'")

    # CONTROL 5 (H4): oversized heading and pronoun
    h4_entries = list(healthy_entries)
    h4_entries[0] = (
        h4_entries[0][0],
        "Check your work before calling the artifact finished",
        h4_entries[0][2],
    )  # pronoun
    h4_entries[1] = (h4_entries[1][0], "x" * 161, h4_entries[1][2])  # 161 chars
    findings = judge(h4_entries)
    has_pronoun = any("pronoun" in f for f in findings)
    has_length = any("over" in f and "160" in f for f in findings)
    if not (has_pronoun and has_length):
        missed.append("either a pronoun heading or an oversized heading was not caught")

    # CONTROL 6a (H5/H6): hint_pick stubbed to always return first entry
    active = [e for e in healthy_entries if True]  # all are active in healthy fixture

    def constant_pick(_entries, _ledger):
        return ({"id": active[0][0]}, 1, len(active))

    findings = cycle_findings(
        constant_pick,
        [
            {"id": eid, "heading": h, "source": s, "status": "active"}
            for eid, h, s in healthy_entries
        ],
    )
    if not any("never surfaced" in f for f in findings):
        missed.append("a hint_pick that only returns one entry was not reported H5")

    # CONTROL 6b (H5/H6): hint_pick that repeats the last entry after cycle
    def repeating_pick(entries, ledger):
        active = [e for e in entries if e.get("status") == "active"]
        if not active:
            return None
        shown = ledger.get("shown", set())
        last = ledger.get("last")
        # First 9 picks: return each once in order
        for e in active:
            if e["id"] not in shown:
                ledger["shown"] = shown | {e["id"]}
                ledger["last"] = e["id"]
                return (e, 1, len(active))
        # 10th pick: repeat the last
        if last and last == active[-1]["id"]:
            return (active[-1], 1, len(active))
        return None

    findings = cycle_findings(
        repeating_pick,
        [
            {"id": eid, "heading": h, "source": s, "status": "active"}
            for eid, h, s in healthy_entries
        ],
    )
    if not any("repeated the hint that just closed" in f for f in findings):
        missed.append("a hint_pick that repeats the last entry was not reported H6")

    return missed


def main() -> int:
    # --- vacuity, before anything is imported --------------------------------
    if not os.path.isfile(HINTS_FILE):
        print(
            f"{RED}✗ VACUOUS INPUT{NC}: {HINTS_FILE} does not exist, so no hints "
            "can be judged. A missing corpus makes every assertion true over nothing, "
            "which reads exactly like a healthy corpus. Refusing to report a pass.",
            file=sys.stderr,
        )
        return 1

    hints_mod, plan_r = load_hints()

    # --- control-first: prove this instrument can fail -------------------------
    missed = controls_fired(hints_mod, plan_r)
    if missed:
        print(
            f"{RED}✗{NC} CONTROLS DID NOT FIRE, so this gate cannot detect what it exists for:",
            file=sys.stderr,
        )
        for m in missed:
            print(f"  {m}", file=sys.stderr)
        return 1

    # --- real corpus judgment --------------------------------------------------
    entries, parse_errors = hints_mod.load_corpus(HINTS_FILE)
    findings = judge_corpus(plan_r, entries, parse_errors) + cycle_findings(
        hints_mod.hint_pick, entries
    )

    if findings:
        print(f"{RED}✗{NC} hints corpus defects:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1

    active = [e for e in entries if e.get("status") == "active"]
    print(f"{GREEN}✓{NC} hints corpus is well-formed")
    print(
        f"  {len(entries)} total entries, {len(active)} active, every entry reachable "
        f"in one cycle of {len(active)}"
    )
    print("  7 planted defects were caught first, so this green means the check can fail")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
