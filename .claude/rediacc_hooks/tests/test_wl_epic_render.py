"""The PR epic block renders THIS PR's epics in full, then a mandatory open system backlog (operator request 2026-10-07).

Before: `wl_epic.render` printed every epic the ledger ever minted, finished ones included, so every PR repeated all earlier PRs' work (agent/pr/1006-3.md carried 20 sections), and the open backlog trailed as an unframed "Not in any epic" list a reader could not tell from the PR's own work.

Every case drives the REAL `worklist.py --publish` against a disposable git repository (the fixture's proj/), so the branch's `PR-TASK:` trailers are read by the code path that reads them live. The epic ledger is planted directly with fixed stamps, because the minted-after-fork rule compares those stamps with the merge-base's commit time and a ledger minted "now" could not sit on both sides of it.
"""

from __future__ import annotations

import json
import os
import re

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

FORK = "2026-01-01T00:00:00Z"
BEFORE = "2025-12-01T00:00:00Z"
AFTER = "2026-02-01T00:00:00Z"
BRANCH = "0101-1"

EPIC_OLD = "aaaa0001"  # finished, not cited: must not render at all
EPIC_PR = "bbbb0002"  # cited by a commit: renders in full
EPIC_OTHER = "cccc0003"  # open items, not cited: its items reach the backlog, tagged
EPIC_NEW = (
    "dddd0004"  # minted after the fork, not yet cited: renders (the commit guard needs it declared)
)
EPIC_GHOST = "eeee0005"  # cited, but the ledger has no record: reported, never rendered


def add(fix, text: str) -> str:
    got = fix.cli("--add", wlfix.ME, text)
    assert got.rc == 0, got.err[:300]
    found = re.search(r"added #([0-9a-f]+)", got.out)
    assert found, got.out[:200]
    return found.group(1)


def tick(fix, iid: str) -> None:
    got = fix.cli("--tick", wlfix.ME, iid, "done in the fixture, exit 0 nocommit:research")
    assert got.rc == 0, got.err[:300]


def plant_ledger(fix, rows: list[tuple[str, str, str, list[str]]]) -> None:
    lines = [
        json.dumps(
            {"at": at, "by": wlfix.ME, "id": eid, "title": title, "covers": covers, "order": None}
        )
        for eid, at, title, covers in rows
    ]
    (fix.store_dir / "epics.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def repo_on_branch(fix, trailers: list[str]) -> None:
    """main with one base commit dated FORK, then BRANCH with one commit per trailer."""
    fix.reg_repo()
    fix.git("branch", "-M", "main")
    # Re-date the base so the merge-base time is FORK, deterministic against the planted stamps.
    env = dict(os.environ, GIT_COMMITTER_DATE=FORK, GIT_AUTHOR_DATE=FORK)
    import subprocess  # noqa: PLC0415 -- only this re-date needs an env git

    subprocess.run(
        ["git", "commit", "-q", "--amend", "--no-edit", "--reset-author"],
        cwd=str(fix.proj),
        env=dict(env, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t"),
        check=True,
    )
    fix.git("checkout", "-q", "-b", BRANCH)
    for n, eid in enumerate(trailers):
        (fix.proj / ("f%d.txt" % n)).write_text("x\n", encoding="utf-8")
        fix.git("add", "-A")
        fix.git("commit", "-qm", "feat: unit %d\n\nPR-TASK: %s" % (n, eid))


def publish(fix, branch: str = BRANCH):
    env = fix.stop_env({"WORKLIST_PUBLISH_ROOT": str(fix.proj)})
    got = fix.cli("--publish", wlfix.ME, branch, env=env)
    snap = fix.proj / "agent" / "pr" / ("%s.md" % branch)
    return got, (snap.read_text(encoding="utf-8") if snap.is_file() else "")


def section(text: str, heading: str) -> str:
    """The lines under the `### <heading...>` line, up to the next heading."""
    lines = text.split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith("### " + heading))
    rest = lines[start + 1 :]
    stop = next((i for i, line in enumerate(rest) if line.startswith("### ")), len(rest))
    return "\n".join(rest[:stop])


def world(fix):
    ids = {
        "old": add(fix, "old finished work in a long-merged epic"),
        "pr_done": add(fix, "this PR's finished unit"),
        "pr_open": add(fix, "this PR's open unit"),
        "other_open": add(fix, "open work parked under another epic"),
        "other_done": add(fix, "finished work under another epic"),
        "new_open": add(fix, "work for the epic minted after the fork"),
        "stray": add(fix, "open work in no epic at all"),
    }
    for key in ("old", "pr_done", "other_done"):
        tick(fix, ids[key])
    plant_ledger(
        fix,
        [
            (EPIC_OLD, BEFORE, "Old merged epic", [ids["old"]]),
            (EPIC_PR, BEFORE, "This PR's epic", [ids["pr_done"], ids["pr_open"]]),
            (EPIC_OTHER, BEFORE, "Another open epic", [ids["other_open"], ids["other_done"]]),
            (EPIC_NEW, AFTER, "Minted on this branch", [ids["new_open"]]),
        ],
    )
    return ids


def test_renders_only_this_prs_epics_then_the_backlog(wl):  # noqa: F811
    ids = world(wl)
    repo_on_branch(wl, [EPIC_PR, EPIC_PR])
    got, snap = publish(wl)
    assert got.rc == 0, got.err[:600]

    declared = re.findall(r"^`PR-TASK: ([0-9a-f]+)`$", snap, re.MULTILINE)
    assert declared == [EPIC_PR, EPIC_NEW], snap
    # A finished epic this PR does not cite is not rendered at all, title included.
    assert "Old merged epic" not in snap
    assert ids["old"] not in snap
    assert "### Another open epic" not in snap

    # The PR's epic shows EVERY covered item, ticked and open.
    own = section(snap, "This PR's epic")
    assert "- [x] `#%s`" % ids["pr_done"] in own
    assert "- [ ] `#%s`" % ids["pr_open"] in own
    assert "- [ ] `#%s`" % ids["new_open"] in section(snap, "Minted on this branch")

    # The backlog: fixed heading with its count, every open item outside the PR's epics, the epic named inline.
    assert "### Open system backlog (2)" in snap
    back = section(snap, "Open system backlog")
    assert "- [ ] `#%s` (epic `%s`) " % (ids["other_open"], EPIC_OTHER) in back
    assert "- [ ] `#%s` open work in no epic" % ids["stray"] in back
    for key in ("old", "pr_done", "pr_open", "other_done", "new_open"):
        assert ids[key] not in back, key
    # The backlog is the LAST section, so nothing can trail after it unframed.
    # Which backlog item renders last follows the fold's order, not insertion (the ids are random hex); pinning `stray` failed about 3 runs in 5.
    last = snap.rstrip().split("\n")[-1]
    assert any(last.startswith("- [ ] `#%s`" % ids[k]) for k in ("stray", "other_open")), last

    # The shape line says what was read, so a collapse is visible.
    assert "2 PR epic(s) (1 cited by %s's commits) of 4 in the ledger" % BRANCH in got.out
    assert "Open system backlog: 2 open item(s)" in got.out


def test_backlog_renders_none_when_empty(wl):  # noqa: F811
    iid = add(wl, "the only item, in this PR's epic")
    plant_ledger(wl, [(EPIC_PR, BEFORE, "This PR's epic", [iid])])
    repo_on_branch(wl, [EPIC_PR])
    got, snap = publish(wl)
    assert got.rc == 0, got.err[:600]
    assert "### Open system backlog (0)" in snap
    assert section(snap, "Open system backlog").strip().endswith("_none_")


def test_a_cited_id_the_ledger_lacks_is_reported_not_rendered(wl):  # noqa: F811
    world(wl)
    repo_on_branch(wl, [EPIC_PR, EPIC_GHOST])
    got, snap = publish(wl)
    assert got.rc == 0, got.err[:600]
    assert EPIC_GHOST not in snap
    assert "cites PR-TASK %s" % EPIC_GHOST in got.err


def test_control_an_unread_range_is_said_not_folded_into_cites_nothing(wl):  # noqa: F811
    """CONTROL. A branch that does not resolve must not publish as "this PR cites nothing" in silence."""
    world(wl)
    repo_on_branch(wl, [EPIC_PR])
    got, snap = publish(wl, "no-such-branch")
    assert got.rc == 0, got.err[:600]
    assert "were NOT read" in got.err
    assert "does not resolve" in got.err
    assert "range UNREAD" in got.out
    # The backlog still publishes: it is the part a reviewer must always see.
    assert "### Open system backlog (" in snap
    assert "`PR-TASK: %s`" % EPIC_PR not in snap
