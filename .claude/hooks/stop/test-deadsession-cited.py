#!/usr/bin/env python3
"""Controls for the dead-session archive sparing items a plan cites (worklist #28742604).

    python3 .claude/hooks/stop/test-deadsession-cited.py

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py.

`wl_store.cleanup_dead_sessions` tombstones a dead owner's items, and a plan's `Ruling:` resolves against the store with tombstones dropped, so an archived ruling item turned every box it released back into a binding. A fixture root holds one plan citing a closed CLI item and a markdown item; the same dead owner holds an uncited closed CLI item and an uncited markdown item. The cited pair must survive, the uncited pair must still be archived (the control that keeps "archive nothing" from passing), and a root whose plan cites nothing must archive everything (the twin that proves the citation, not the fixture, is what spares the item).
"""

import importlib.util
import os
import pathlib
import shutil
import tempfile
import time

import wl_store as S

_REAL = pathlib.Path(__file__).resolve()
_CI = _REAL.parents[3] / ".ci" / "rediacc_ci"


def _by_file(name):
    spec = importlib.util.spec_from_file_location(name, _CI / ("%s.py" % name))
    if spec is None or spec.loader is None:
        raise SystemExit("%s: .ci/rediacc_ci/%s.py is missing" % (__file__, name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


controls = _by_file("controls")
runtmp = _by_file("runtmp")
# Every process-wide seam this file sets is restored before it reports (75590cfb.3), so an in-process import leaves no store, root or TMPDIR behind.
_ENV0 = dict(os.environ)
_TEMPDIR0 = tempfile.tempdir
_TMP = runtmp.run_dir("deadcite-test-")
os.environ["TMPDIR"] = _TMP
tempfile.tempdir = _TMP
for _k in [k for k in os.environ if k.startswith("WORKLIST_")]:
    del os.environ[_k]

T = controls.Controls("deadsession_cited", floor=19)
check = T.check

ME = "cafe0000"
SID = ME + "-0000-4000-8000-000000000000"
DEAD = "dead0000"
MD_CITED = "an md ruling the plan cites"
MD_FREE = "an md item nothing cites"


def make_world(cite):
    """(root, worklist, projects_dir, ids). `cite` decides whether the plan names the two cited items."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="root-"))
    (root / ".git").mkdir()
    plans = root / "agent" / "plans"
    plans.mkdir(parents=True)
    store = root / "agent" / "worklist"
    store.mkdir()
    os.environ["WORKLIST_STORE_DIR"] = str(store)
    os.environ["CLAUDE_PROJECT_DIR"] = str(root)
    worklist = root / "wl.md"
    cited_cli = S.add_item(worklist, DEAD, "operator ruling: retire plan X", state="x", root=root)
    free_cli = S.add_item(worklist, DEAD, "an ordinary finished item", state="x", root=root)
    md_cited_id = S.item_key(DEAD, MD_CITED)
    worklist.write_text(
        "- [x] (%s) %s\n- [x] (%s) %s\n" % (DEAD, MD_CITED, DEAD, MD_FREE), encoding="utf-8"
    )
    refs = "#%s and #%s" % (cited_cli, md_cited_id) if cite else "nothing"
    (plans / "PLAN-fixture.md").write_text(
        "# PLAN: fixture\n\nStatus: superseded\nRuling: %s\n\n## Tasks\n\n- [ ] F1 a box\n" % refs,
        encoding="utf-8",
    )
    projects = root / "projects"
    projects.mkdir()
    transcript = projects / ("%s-0000-4000-8000-000000000000.jsonl" % DEAD)
    transcript.write_text("{}\n", encoding="utf-8")
    old = time.time() - 200 * 3600
    os.utime(transcript, (old, old))
    return root, worklist, projects, {"cited": cited_cli, "free": free_cli}


def states(worklist):
    S.clear_read_memo()
    fold = S.load(worklist, sync=True)
    return {r["id"]: r["state"] for r in fold.items}, fold


def md_state(worklist, text):
    for line in worklist.read_text(encoding="utf-8").splitlines():
        if line.endswith(text):
            return line.split("[", 1)[1][0]
    return None


roots = []
try:
    # The citing plan: root resolved from CLAUDE_PROJECT_DIR, the stop hook's own call shape.
    root, worklist, projects, ids = make_world(cite=True)
    roots.append(root)
    before, fold = states(worklist)
    check("fixture: the cited CLI item starts closed", before.get(ids["cited"]), "x")
    check("fixture: the uncited CLI item starts closed", before.get(ids["free"]), "x")
    archived, orphaned, changed = S.cleanup_dead_sessions(worklist, fold, SID, str(projects))
    after, _ = states(worklist)
    check("cited CLI item is not tombstoned", after.get(ids["cited"]), "x")
    check("uncited CLI item is still archived (control)", ids["free"] in after, False)
    check("cited markdown item is not flipped", md_state(worklist, MD_CITED), "x")
    check("uncited markdown item is still flipped (control)", md_state(worklist, MD_FREE), "~")
    check("the archive reports exactly the two uncited items", len(archived), 2)
    check("a cited item is not reported orphaned either", orphaned, [])
    check("the archive says it changed the store", changed, True)

    # The twin: the same world with a plan that cites nothing, root passed explicitly.
    root2, worklist2, projects2, ids2 = make_world(cite=False)
    roots.append(root2)
    _, fold2 = states(worklist2)
    archived2, _, _ = S.cleanup_dead_sessions(worklist2, fold2, SID, str(projects2), root=root2)
    after2, _ = states(worklist2)
    check("twin: an uncited ruling item is archived", ids2["cited"] in after2, False)
    check("twin: an uncited markdown ruling is flipped", md_state(worklist2, MD_CITED), "~")
    check("twin: all four items archived", len(archived2), 4)

    # A citation scan that raises fails closed (75590cfb.1): nothing is archived or orphaned, where an empty set would tombstone the cited ruling item. The first world above is the control: the same dead owner with a working scan archives the uncited pair.
    root3, worklist3, projects3, ids3 = make_world(cite=True)
    roots.append(root3)
    _, fold3 = states(worklist3)
    real_files = S.agent_plan_files

    def broken_files(*_args, **_kwargs):
        raise OSError("plan listing unreadable")

    S.agent_plan_files = broken_files
    try:
        archived3, orphaned3, changed3 = S.cleanup_dead_sessions(
            worklist3, fold3, SID, str(projects3), root=root3
        )
    finally:
        S.agent_plan_files = real_files
    after3, _ = states(worklist3)
    check("failed scan: the cited CLI item is not tombstoned", after3.get(ids3["cited"]), "x")
    check("failed scan: the uncited CLI item is spared too", after3.get(ids3["free"]), "x")
    check("failed scan: no markdown item is flipped", md_state(worklist3, MD_FREE), "x")
    check(
        "failed scan: nothing archived or orphaned",
        (archived3, orphaned3, changed3),
        ([], [], False),
    )

    check(
        "citation regex: a longer hex run is not an 8-char citation",
        S.PLAN_ITEM_CITE_RE.findall("#d969cb29 #0123456789abcdef x#d969cb30 (#936e6c58)"),
        ["d969cb29", "936e6c58"],
    )
finally:
    for d in roots:
        shutil.rmtree(d, ignore_errors=True)
    os.environ.clear()
    os.environ.update(_ENV0)
    tempfile.tempdir = _TEMPDIR0

check("the environment is restored after the run", dict(os.environ) == _ENV0, True)
check("tempfile.tempdir is restored after the run", tempfile.tempdir, _TEMPDIR0)

raise SystemExit(0 if T.report() else 1)
