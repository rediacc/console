#!/usr/bin/env python3
"""check:ci-plan-bindings -- no closed plan is still held by anything (agent/plans/PLAN-plan-compaction-bindings.md, box CB4).

THE RULING (operator, 2026-10-03): "The planning tools/system should not allow plan compaction if there is any binding to other plans until we complete all the pieces". The verbs refuse at the moment of compaction, move or sweep (CB2, CB3). This gate judges the committed tree, so a hand edit, a stale record or a path that never asked cannot leave a closed plan with live work hanging off it.

THE DECISION IS NOT HERE. `.claude/hooks/stop/wl_planbind.bindings` decides what binds (an own open box, an open worklist item of any session citing the plan or a box signature, an unfinished dependent, an open box elsewhere citing one of its boxes), imported through `paths.hooks_stop_dir` the way check_plan_deps.py imports wl_plandeps. A second reader would be a second grammar.

WHICH PLANS ARE JUDGED: every non-stub plan that lives under `_done/` or `_removed/`, or whose Status is finished (`wl_planfile.FINISHED_STATES`, `compacted` included), `parked`, `moved` or `removed`. A stub is a pointer with no work of its own; the real file it points at is judged instead, so one citation is never counted twice. Live plans are not this gate's business: binding to a live plan is the normal state of work.

NO BASELINE. The migration box (CB5) empties the set before the gate is expected green; until then every finding is real and stays visible.

FINDINGS, EACH WITH A PLANTED CONTROL IN `--selftest`:

    B1  a judged plan with at least one live binding; every binding is listed with
        the commands that release it (`wl_planbind.render`)
    B0  the vacuity floor: zero plans read, or committed store files that fold to
        zero items. Either is CANNOT RUN (exit 77), never green.

THE VERBS.

    --check        (the default) controls first, then the verdict
    --selftest     the planted controls alone, including a real-file plant under a
                   scratch root driven through the same `check` the CLI runs
    --root <dir>   judge another tree (the plant's door)

Exit codes: 0 green, 1 findings, 2 a control failed or bad usage, 77 cannot run.

---- gate ----
step: Plan bindings
needs: none
lane: quality-static
selftest: true
why: a plan compacted, parked or moved to _done/ while an open box, an open
     worklist item, an unfinished dependent or another plan's open box still
     binds to it orphans that work: on 2026-10-03 the items bound to seven such
     plans reached the operator as "no live box: keep or drop?". The verbs refuse
     the transition; this gate is the merge-time backstop over the committed tree.
---- end gate ----
"""

from __future__ import annotations

import io
import json
import pathlib
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

import _cipath
from rediacc_ci import controls, paths

paths.on_sys_path(paths.hooks_stop_dir())

try:
    import wl_planbind as B
    import wl_plandeps as D
    import wl_planrec as R
except ImportError as _exc:  # pragma: no cover -- a tree without .claude/hooks/stop
    print(
        "VACUOUS INPUT: cannot import the binding decision wl_planbind from %s (%s). "
        "The decision lives only there, so without it there is nothing to judge."
        % (paths.hooks_stop_dir(), _exc),
        file=sys.stderr,
    )
    sys.exit(77)

#: Statuses that close a plan beside FINISHED_STATES: a parked record, a moved stub's real file, a removed plan.
CLOSED_EXTRA = frozenset({R.STATUS_PARKED, "moved", D.REMOVED_STATUS})
TERMINAL_DIRS = (D.DONE_DIR, D.REMOVED_DIR)
CONTROL_FLOOR = 14
STORE_GLOB = "agent/worklist/*.jsonl"


class CannotRunError(RuntimeError):
    """No verdict is possible: exit 77, which is not a pass."""


def judged(graph: D.Graph, rel: str) -> bool:
    """True for a non-stub plan that is closed by folder or by Status."""
    info = graph.plans.get(rel)
    if info is None or info.stub:
        return False
    if info.folder in TERMINAL_DIRS:
        return True
    status = info.header.status
    return status in graph.finished() or status in CLOSED_EXTRA


def evaluate(
    texts: dict[str, str], items: list[dict], index_text: str, root: pathlib.Path
) -> tuple[dict[str, list[B.Binding]], dict[str, int]]:
    """({rel: bindings} for every judged plan with at least one binding, stats). Raises CannotRunError on zero plans."""
    if not texts:
        raise CannotRunError("zero plans read under %s" % ", ".join(D.PLAN_DIRS))
    graph = D.Graph(texts, index_text, root)
    found: dict[str, list[B.Binding]] = {}
    n_judged = 0
    for rel in sorted(texts):
        if not judged(graph, rel):
            continue
        n_judged += 1
        got = B.bindings(root, rel, texts=texts, items=items, index_text=index_text)
        if got:
            found[rel] = got
    return found, {"plans": len(texts), "judged": n_judged, "items": len(items)}


def load(root: pathlib.Path) -> tuple[dict[str, str], list[dict], str]:
    texts = B.load_texts(root)
    items = B.store_items(root)
    if any(root.glob(STORE_GLOB)) and not items:
        raise CannotRunError(
            "%s holds store files but they fold to zero items, so no item binding could be seen"
            % STORE_GLOB
        )
    try:
        index_text = (root / D.INDEX_REL).read_text(encoding="utf-8", errors="replace")
    except OSError:
        index_text = ""
    return texts, items, index_text


def check(root: pathlib.Path) -> int:
    texts, items, index_text = load(root)
    found, stats = evaluate(texts, items, index_text, root)
    if found:
        total = sum(len(v) for v in found.values())
        for rel in sorted(found):
            print("✗ %s" % rel, file=sys.stderr)
            for line in B.render(rel, found[rel]).splitlines():
                print("    %s" % line, file=sys.stderr)
        kinds: dict[str, int] = {}
        for got in found.values():
            for b in got:
                kinds[b.kind] = kinds.get(b.kind, 0) + 1
        print(
            "✗ plan bindings: B1 %d binding(s) hold %d closed plan(s) (%s); %d judged of %d plan(s), %d item(s) read."
            % (
                total,
                len(found),
                ", ".join("%s=%d" % kv for kv in sorted(kinds.items())),
                stats["judged"],
                stats["plans"],
                stats["items"],
            ),
            file=sys.stderr,
        )
        return 1
    print(
        "✓ plan bindings: %d closed plan(s) judged of %d read, %d item(s) read, nothing binds to any."
        % (stats["judged"], stats["plans"], stats["items"])
    )
    print(
        "  Blind spot: a citation spelled other than `PLAN-x.md` or a box signature is not seen, "
        "and whether a re-homed box's new home really took the work is judged by name only."
    )
    return 0


# --------------------------------------------------------------------------- Controls.

ALONE = "no-dep -- stands alone in this fixture"
DONE_X = "agent/plans/_done/PLAN-x.md"
LIVE_Y = "agent/plans/PLAN-y.md"


def _plan(name: str, status: str = "done", boxes=("[x] T1 finished work",), depends=ALONE) -> str:
    lines = [
        "# %s: fixture" % name,
        "",
        "Status: %s" % status,
        "Owner: abc12345",
        "Depends-On: %s" % depends,
        "",
        "## Tasks",
        "",
    ]
    lines += ["- %s" % b for b in boxes]
    return "\n".join(lines) + "\n"


def _clean() -> dict[str, str]:
    return {
        DONE_X: _plan("PLAN-x"),
        LIVE_Y: _plan("PLAN-y", status="in-progress", boxes=("[ ] T1 live work",)),
    }


def _item(iid: str, state: str, text: str) -> dict:
    return {"id": iid, "state": state, "text": text}


def _verdict(texts: dict[str, str], items=()) -> dict[str, list[str]]:
    found, _ = evaluate(texts, list(items), "", pathlib.Path("/nonexistent-root"))
    return {rel: sorted(b.kind for b in got) for rel, got in found.items()}


def _write_root(tmp: pathlib.Path, texts: dict[str, str], events: list[dict]) -> pathlib.Path:
    for rel, text in texts.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    (tmp / D.PLANS_DIR).mkdir(parents=True, exist_ok=True)
    store = tmp / "agent" / "worklist"
    store.mkdir(parents=True, exist_ok=True)
    (store / "abc12345.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
    )
    return tmp


def _add(iid: str, text: str, state: str = " ", ns: int = 1) -> dict:
    return {
        "ev": "add",
        "id": iid,
        "at": "2026-11-09T00:00:0%dZ" % ns,
        "by": "abc12345",
        "s": state,
        "o": "abc12345",
        "t": text,
        "ns": ns,
    }


def _quiet_check(root: pathlib.Path) -> int:
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        try:
            return check(root)
        except CannotRunError:
            return 77


def selftest() -> int:
    """Controls before plants: a gate that flags everything fails the controls, one that flags nothing fails the plants."""
    tally = controls.Controls("plan bindings", floor=CONTROL_FLOOR)
    cite = "finish PLAN-x.md first"

    # Controls.
    tally.check("control: a clean closed plan with no citation is green", _verdict(_clean()), {})
    tally.check(
        "control: an open item citing a LIVE plan is not this gate's business",
        _verdict(_clean(), [_item("aa11bb22", " ", "keep going on PLAN-y.md")]),
        {},
    )
    tally.check(
        "control: a ticked item citing the closed plan does not bind",
        _verdict(_clean(), [_item("aa11bb22", "x", cite)]),
        {},
    )
    stubbed = dict(
        _clean(),
        **{"agent/plans/PLAN-x.md": "# PLAN-x\n\nStatus: moved\nMoved-To: %s\n" % DONE_X},
    )
    tally.check(
        "control: a moved stub is not judged, so one citation is one finding on the real file",
        _verdict(stubbed, [_item("aa11bb22", " ", cite)]),
        {DONE_X: ["item"]},
    )

    # Plants.
    tally.check(
        "B1 planted: an open item citing a _done plan",
        _verdict(_clean(), [_item("aa11bb22", " ", cite)]),
        {DONE_X: ["item"]},
    )
    tally.check(
        "B1 planted: a deferred item citing a _done plan",
        _verdict(_clean(), [_item("aa11bb22", "?", cite)]),
        {DONE_X: ["item"]},
    )
    tally.check(
        "B1 planted: a _done plan with an open box of its own",
        _verdict(dict(_clean(), **{DONE_X: _plan("PLAN-x", boxes=("[ ] T1 orphaned work",))})),
        {DONE_X: ["box"]},
    )
    rec = "agent/plans/PLAN-r.md"
    tally.check(
        "B1 planted: a compacted record in agent/plans with an open citing item",
        _verdict(
            dict(_clean(), **{rec: _plan("PLAN-r", status="compacted")}),
            [_item("cc33dd44", " ", "PLAN-r.md follow-up")],
        ),
        {rec: ["item"]},
    )
    tally.check(
        "B1 planted: a parked record with an open box",
        _verdict(
            dict(_clean(), **{rec: _plan("PLAN-r", status="parked", boxes=("[ ] T1 parked",))})
        ),
        {rec: ["box"]},
    )
    tally.check(
        "B1 planted: an unfinished plan depending on a _done plan",
        _verdict(
            dict(
                _clean(),
                **{LIVE_Y: _plan("PLAN-y", status="in-progress", depends="PLAN-x.md")},
            )
        ),
        {DONE_X: ["dependent"]},
    )
    tally.raises(
        "B0 planted: zero plans read is CANNOT RUN, never green",
        CannotRunError,
        evaluate,
        {},
        [],
        "",
        pathlib.Path("/nonexistent-root"),
    )

    # The real-file path: the same `check` the CLI runs, over a scratch root.
    with tempfile.TemporaryDirectory(prefix="plan-bindings-") as tmp:
        root = _write_root(pathlib.Path(tmp), _clean(), [_add("aa11bb22", cite, state="x")])
        tally.check("real files, control: the clean scratch tree exits 0", _quiet_check(root), 0)
        (root / "agent" / "worklist" / "abc12345.jsonl").write_text(
            json.dumps(_add("aa11bb22", cite)) + "\n", encoding="utf-8"
        )
        tally.check("real files, plant: an open citing item on disk exits 1", _quiet_check(root), 1)
    with tempfile.TemporaryDirectory(prefix="plan-bindings-") as tmp:
        root = _write_root(pathlib.Path(tmp), {}, [_add("aa11bb22", cite)])
        tally.check("real files, B0: an empty plans tree exits 77", _quiet_check(root), 77)
    return 0 if tally.report() else 1


def main(argv: list[str]) -> int:
    try:
        if "--selftest" in argv:
            return selftest()
        root = paths.repo_root()
        if "--root" in argv:
            i = argv.index("--root")
            if i + 1 >= len(argv):
                print("✗ --root needs a directory", file=sys.stderr)
                return 2
            root = pathlib.Path(argv[i + 1])
        unknown = [a for a in argv if a.startswith("--") and a not in ("--root", "--check")]
        if unknown:
            print("✗ unknown flag(s): %s" % " ".join(unknown), file=sys.stderr)
            return 2
        print("plan bindings: controls first, then the verdict")
        if selftest() != 0:
            print(
                "✗ instrument control failed; every verdict below would be meaningless",
                file=sys.stderr,
            )
            return 2
        return check(root)
    except CannotRunError as exc:
        print("⚠ CANNOT RUN (exit 77, which is not a verdict): %s" % exc, file=sys.stderr)
        return 77


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
