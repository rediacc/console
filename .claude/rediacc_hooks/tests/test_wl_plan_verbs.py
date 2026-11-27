"""The one-call plan verbs (agent/plans/PLAN-plan-verbs.md): `--plan-new` (T14) and `--plan-tick ... --investigate present` (T15).

Each case drives `worklist.py` against a fixture git repository and pairs the effect with a control that changes one planted fact: a refused call leaves every file it would have written byte-identical.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from rediacc_hooks.tests import wlfix

if TYPE_CHECKING:
    import pathlib

PR = wlfix.import_wl("wl_planrec")
PQ = wlfix.import_wl("wl_planqueue")
CK = wlfix.import_wl("wl_checks")
ME = wlfix.ME
NEW = "agent/plans/PLAN-fresh.md"
LEDGER = ".ci/config/plan-boxes.json"
INDEX = "agent/INDEX.md"
QUEUE = "agent/plans/QUEUE.md"

HEADER = {
    "Status": "approved",
    "Owner": "deadbeef",
    "First-Seen": "2026-11-27",
    "Depends-On": "no-dep -- a fixture plan for the plan-verbs suite",
    "Priority": "P2 -- fixture",
    "Concurrency": "parallel",
    "Owns": "docs/x/**",
}


def plan_text(drop: str = "", boxes: str = "- [ ] F1 the first fresh box\n") -> str:
    head = "".join("%s: %s\n" % (k, v) for k, v in HEADER.items() if k != drop)
    return "# PLAN fresh\n\n%s\n## Tasks\n%s" % (head, boxes)


def seed(wl) -> None:
    """A git repo with a committed (empty-plans) ledger and the fixture QUEUE.md; agent/INDEX.md is absent until a verb writes it."""
    wl.reg_repo()
    (wl.proj / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    (wl.proj / LEDGER).write_text(json.dumps({"plans": {}}, indent=2) + "\n", encoding="utf-8")
    wl.git("add", "-A")
    wl.git("commit", "-qm", "chore: seed ledger")


def snapshot(root: pathlib.Path, *rels: str) -> dict[str, bytes | None]:
    return {r: ((root / r).read_bytes() if (root / r).is_file() else None) for r in rels}


def tracked(wl, rel: str) -> bool:
    return bool(wl.git("ls-files", "--", rel).stdout.strip())


def write_plan(wl, text: str, rel: str = NEW) -> None:
    path = wl.proj / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---- T14: --plan-new ------------------------------------------------------------------------


def test_plan_new_stages_the_plan_writes_its_ledger_row_and_lists_it_in_index_and_queue(wl):
    seed(wl)
    write_plan(wl, plan_text())
    listing = wl.cli("--plan-new", ME)
    assert listing.rc == 0, (listing.out, listing.err)
    assert NEW in listing.out, listing.out

    before = snapshot(wl.proj, NEW, LEDGER, INDEX, QUEUE)
    dry = wl.cli("--plan-new", ME, NEW)
    assert dry.rc == 0, (dry.out, dry.err)
    assert "NOTHING was written" in dry.out, dry.out
    assert snapshot(wl.proj, NEW, LEDGER, INDEX, QUEUE) == before
    assert not tracked(wl, NEW)

    got = wl.cli("--plan-new", ME, NEW, "--write")
    assert got.rc == 0, (got.out, got.err)
    assert "git commit -F <msg> -- %s" % NEW in got.out, got.out
    ledger = json.loads((wl.proj / LEDGER).read_text(encoding="utf-8"))
    text = (wl.proj / NEW).read_text(encoding="utf-8")
    assert ledger["plans"][NEW] == PR.ledger_row(str(wl.proj), NEW, text)
    assert ledger["plans"][NEW]["open"] == 1
    assert NEW in (snapshot(wl.proj, INDEX)[INDEX] or b"").decode(), "INDEX does not list the plan"
    queue = (wl.proj / QUEUE).read_text(encoding="utf-8")
    assert NEW in (PQ.generated_text(queue) or ""), queue
    assert tracked(wl, NEW), "the plan was not staged"
    # The plan is registered now, so the listing no longer offers it and a second run is refused toward --plan-tick.
    assert NEW not in wl.cli("--plan-new", ME).out
    again = wl.cli("--plan-new", ME, NEW, "--write")
    assert again.rc == 2, (again.rc, again.err)
    assert "--plan-tick" in again.err, again.err


def test_staging_is_what_puts_the_plan_in_the_index(wl):
    """CONTROL for the `git add` step: the same refresh over the same plan, left untracked, omits it from INDEX and the QUEUE generated section, which is why --plan-new stages before it refreshes."""
    seed(wl)
    write_plan(wl, plan_text())
    PR.refresh_index(str(wl.proj), CK.plan_records, CK.plan_box_census)
    index = wl.proj / INDEX
    assert not index.is_file() or NEW not in index.read_text(encoding="utf-8")
    assert NEW not in (PQ.generated_text((wl.proj / QUEUE).read_text(encoding="utf-8")) or "")


def test_plan_new_refusals_write_nothing(wl):
    seed(wl)
    cases = [
        (NEW, plan_text(drop="Owns"), "Owns: missing"),
        (NEW, plan_text(drop="First-Seen"), "First-Seen: missing"),
        (NEW, plan_text(boxes="Prose only, no task yet.\n"), "has no box"),
        ("agent/PLAN-fresh.md", plan_text(), "not a plan path under agent/plans/"),
    ]
    for rel, text, needle in cases:
        write_plan(wl, text, rel)
        before = snapshot(wl.proj, rel, LEDGER, INDEX, QUEUE)
        got = wl.cli("--plan-new", ME, rel, "--write")
        assert got.rc == 2, (rel, needle, got.rc, got.out, got.err)
        assert needle in got.err, (needle, got.err)
        assert "Nothing was written" in got.err, got.err
        assert snapshot(wl.proj, rel, LEDGER, INDEX, QUEUE) == before, needle
        assert not tracked(wl, rel), "a refused --plan-new staged %s" % rel
        (wl.proj / rel).unlink()
    missing = wl.cli("--plan-new", ME, "agent/plans/PLAN-absent.md", "--write")
    assert missing.rc == 2, (missing.rc, missing.err)
    assert "does not exist" in missing.err, missing.err
