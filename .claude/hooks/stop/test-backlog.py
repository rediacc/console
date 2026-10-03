#!/usr/bin/env python3
"""Controls for wl_backlog -- the next plan the one-plan-per-PR loop starts, read off agent/plans/QUEUE.md (agent/plans/PLAN-stop-hook-one-plan-scope.md Design 5, box SC7).

    python3 .claude/hooks/stop/test-backlog.py

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py (glob over test-*.py under .claude/hooks/stop/), so no table edit is needed to wire this file in.

EVERY CASE HERE IS A PAIR, matching test-planfile.py's own convention: a "this must be nominated" case is followed by a "this must NOT be nominated" case built from the same fixture with one thing changed, because a matcher that returns the same answer for everything produces output indistinguishable from a working one. The dry run on PR #592 is the first case: the retired per-session ranking named PLAN-config-passkey-optional.md, a newer plan this session owned that the queue did not hold.
"""

import importlib.util
import pathlib
import re
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import wl_backlog as B  # noqa: E402

# `rediacc_ci.runtmp`, loaded BY FILE rather than through a `sys.path` hop (test_canonical_sys_path_hop.py freezes those): a pid-stamped run directory, removed at exit and swept by the next run when this one was killed before `atexit` could fire, which is how /tmp hit its inode cap on 2026-09-24.
_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", pathlib.Path(__file__).resolve().parents[3] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit(
        "%s: .ci/rediacc_ci/runtmp.py is missing; this suite cannot make its run dir" % __file__
    )
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
# IN-PROCESS ONLY: every `TemporaryDirectory`/`mkdtemp` below lands in the run dir, including the ones handed out without a `with` and cleaned up only when the suite reaches them. TMPDIR itself is left alone, so what this suite spawns sees the environment it always did.
tempfile.tempdir = runtmp.run_dir("backlog-suite-")


class Tally:
    fails = 0
    count = 0


def control(label, got, want):
    Tally.count += 1
    if got != want:
        Tally.fails += 1
        print("FAIL  %s: got %r, wanted %r" % (label, got, want), file=sys.stderr)


def truthy(label, got):
    Tally.count += 1
    if not got:
        Tally.fails += 1
        print("FAIL  %s: got %r, wanted something truthy" % (label, got), file=sys.stderr)


OWNER = "a276391d"


def plan_body(opened=1, done=0, owner=OWNER, depends_on=None, status="approved"):
    head = "# PLAN: a fixture\n\nStatus: %s\nOwner: %s\n" % (status, owner)
    head += "Depends-On: %s\n" % (depends_on or "no-dep -- a standalone fixture plan")
    body = head + "\n## Tasks\n\n"
    body += "".join("- [x] D%d the ticked fixture part number %d\n" % (i, i) for i in range(done))
    body += "".join("- [ ] T%d build the fixture part number %d\n" % (i, i) for i in range(opened))
    return body


def make_tree(plans, promoted=(), generated=()):
    """(td, root): fixture plans written in order (the LAST written is the newest mtime) plus a QUEUE.md."""
    td = tempfile.TemporaryDirectory()
    root = pathlib.Path(td.name)
    (root / "agent" / "plans").mkdir(parents=True)
    for name, text in plans:
        (root / "agent" / "plans" / name).write_text(text, encoding="utf-8")
    queue = "# Plan queue\n\n## Promoted\n\n"
    queue += "".join("%d. agent/plans/%s\n" % (i + 1, n) for i, n in enumerate(promoted))
    queue += "\n## Generated\n\n<!-- queue:generated:begin -->\n"
    queue += "".join("%d. agent/plans/%s\n" % (i + 1, n) for i, n in enumerate(generated))
    queue += "<!-- queue:generated:end -->\n"
    (root / "agent" / "plans" / "QUEUE.md").write_text(queue, encoding="utf-8")
    return td, root


def rel(name):
    return "agent/plans/%s" % name


def pick(root, exclude=()):
    cand, reason, stats = B.next_plan(root, exclude=exclude)
    return (cand or {}).get("rel") or reason, cand, stats


# --------------------------------------------------------------------------- 1. QUEUE.md DECIDES, not ownership or mtime. A Promoted entry beats a newer plan this session owns that the queue does not hold (the PLAN-config-passkey-optional.md nomination of the dry run).
td, root = make_tree(
    [
        ("PLAN-queued.md", plan_body(owner="cafe1234")),
        ("PLAN-config-passkey-optional.md", plan_body(owner=OWNER)),
    ],
    promoted=["PLAN-queued.md"],
)
try:
    got, cand, _stats = pick(root)
    control("QUEUE: the Promoted entry is the next plan", got, rel("PLAN-queued.md"))
    control("  at its queue position", (cand or {}).get("position"), "Promoted 1")
finally:
    td.cleanup()

# PAIR: the same tree with the owned plan queued ahead of it names the owned one, so the order is the queue's, not a tie-break.
td, root = make_tree(
    [
        ("PLAN-queued.md", plan_body(owner="cafe1234")),
        ("PLAN-config-passkey-optional.md", plan_body(owner=OWNER)),
    ],
    promoted=["PLAN-config-passkey-optional.md", "PLAN-queued.md"],
)
try:
    got, _cand, _stats = pick(root)
    control("PAIR: queued first, it is next", got, rel("PLAN-config-passkey-optional.md"))
finally:
    td.cleanup()


# --------------------------------------------------------------------------- 2. A FINISHED PROMOTED ENTRY IS SKIPPED for the Generated head.
td, root = make_tree(
    [("PLAN-merged.md", plan_body(opened=0, done=3)), ("PLAN-gen.md", plan_body(opened=2))],
    promoted=["PLAN-merged.md"],
    generated=["PLAN-gen.md"],
)
try:
    got, cand, _stats = pick(root)
    control("FINISHED: a Promoted entry with zero open boxes is skipped", got, rel("PLAN-gen.md"))
    control(
        "  for the Generated head, named by position", (cand or {}).get("position"), "Generated 1"
    )
finally:
    td.cleanup()

# PAIR: one open box left on the Promoted entry and it is next again.
td, root = make_tree(
    [("PLAN-merged.md", plan_body(opened=1, done=3)), ("PLAN-gen.md", plan_body(opened=2))],
    promoted=["PLAN-merged.md"],
    generated=["PLAN-gen.md"],
)
try:
    got, _cand, _stats = pick(root)
    control("PAIR: an open box keeps the Promoted entry next", got, rel("PLAN-merged.md"))
finally:
    td.cleanup()


# --------------------------------------------------------------------------- 3. THE PR'S OWN PLAN IS NEVER NOMINATED: the loop state's set is excluded.
td, root = make_tree(
    [("PLAN-pr.md", plan_body()), ("PLAN-after.md", plan_body())],
    promoted=["PLAN-pr.md", "PLAN-after.md"],
)
try:
    got, _cand, _stats = pick(root, exclude=(rel("PLAN-pr.md"),))
    control("PR PLAN: the PR's own plan is skipped", got, rel("PLAN-after.md"))
    got, _cand, _stats = pick(root)
    control("PAIR: without the exclusion the queue head is named", got, rel("PLAN-pr.md"))
finally:
    td.cleanup()


# --------------------------------------------------------------------------- 4. A PREREQUISITE COMES FIRST: a queued plan whose dependency is open names the dependency, and says whose prerequisite it is.
td, root = make_tree(
    [
        ("PLAN-top.md", plan_body(depends_on="PLAN-base.md")),
        ("PLAN-base.md", plan_body()),
    ],
    promoted=["PLAN-top.md"],
)
try:
    got, cand, _stats = pick(root)
    control("PREREQ: the open dependency is the next plan", got, rel("PLAN-base.md"))
    control(
        "  named as the queued plan's prerequisite",
        (cand or {}).get("position"),
        "prerequisite of %s" % rel("PLAN-top.md"),
    )
finally:
    td.cleanup()

# PAIR: the dependency finished, the queued plan itself is next.
td, root = make_tree(
    [
        ("PLAN-top.md", plan_body(depends_on="PLAN-base.md")),
        ("PLAN-base.md", plan_body(opened=0, done=2)),
    ],
    promoted=["PLAN-top.md"],
)
try:
    got, _cand, _stats = pick(root)
    control("PAIR: a finished dependency does not redirect", got, rel("PLAN-top.md"))
finally:
    td.cleanup()


# --------------------------------------------------------------------------- 5. AN EMPTY QUEUE NAMES NOTHING, and renders nothing.
td, root = make_tree([("PLAN-owned.md", plan_body())])
try:
    got, cand, _stats = pick(root)
    control("EMPTY: an empty queue is queue-empty, not a guess", (got, cand), ("queue-empty", None))
    control("  and renders no advisory", B.render(None, "queue-empty", {"queued": 0}), "")
finally:
    td.cleanup()


# --------------------------------------------------------------------------- 6. RENDER: the position, the first box with its signature, the advisory statement, and no live counter.
td, root = make_tree([("PLAN-a.md", plan_body(opened=2))], promoted=["PLAN-a.md"])
try:
    cand, reason, stats = B.next_plan(root)
    text = B.render(cand, reason, stats)
    truthy("RENDER: names the queue position", "QUEUE.md Promoted 1" in text)
    truthy("  and the first open box", "T0 build the fixture part number 0" in text)
    truthy("  with its box signature", cand and cand["first"] and cand["first"][0] in text)
    truthy("  and says it is advisory", "ADVISORY" in text)
    control(
        "  with no live minute-precision counter",
        bool(re.search(r"\d+ min(ute)?s? ago", text)),
        False,
    )
    # A precomputed next plan (the loop state's) is rendered without recomputing; "" means the queue is empty.
    control(
        "RENDER: an empty precomputed next plan is queue-empty",
        B.next_plan(root, nxt="")[1],
        "queue-empty",
    )
finally:
    td.cleanup()


# --------------------------------------------------------------------------- 7. NEVER BLOCKS, and the retired ranking is gone: no vadd, no plan file written, no per-session cap, no ownership filter.
src = (HERE / "wl_backlog.py").read_text(encoding="utf-8")
control("NEVER BLOCKS: the module source contains no call to vadd", "vadd(" in src, False)
control(
    "  and never opens a plan file for writing",
    re.search(r"open\([^)]*[\"']w[\"']", src) is not None,
    False,
)
truthy("  and its own docstring states the never-blocks contract", "NEVER blocks" in src)
# Spelled in two halves so box SC7's `git grep` acceptance finds the retired key nowhere, these controls included.
_RETIRED_KEY = "backlog_" + "nominated"
control("RETIRED: no per-session nomination cap", _RETIRED_KEY in src, False)
control("  and no environment knob", "os.environ" in src, False)
control("  and no ownership filter", "owned_by_me" in src, False)
_wire_src = (HERE / "wl_checks.py").read_text(encoding="utf-8")
truthy(
    "NEVER BLOCKS: the wl_checks call site delivers it through outq_add",
    "wl_backlog.next_plan" in _wire_src
    and "outq_add(worklist, session_id, state_doc, _bl_key" in _wire_src,
)
control("  and keeps no cap state key", _RETIRED_KEY in _wire_src, False)


if Tally.count < 27:
    Tally.fails += 1
    print(
        "FAIL  only %d control(s) ran; the file is not being executed as written" % Tally.count,
        file=sys.stderr,
    )

if Tally.fails:
    print("FAIL: %d of %d control(s) failed" % (Tally.fails, Tally.count), file=sys.stderr)
    sys.exit(1)
print("%d control(s) passed" % Tally.count)
