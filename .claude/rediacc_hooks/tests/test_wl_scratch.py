"""`worklist.py --prune-scratch` (wl_scratch.py, worklist #edd646a8): the session scratchpad prune keeps anything in doubt and deletes only the finished.

Every keep rule has a case that must keep and a sibling, one planted fact away, that must delete, so a rule that keeps EVERYTHING fails as surely as one that keeps nothing. The end-to-end case drives the real CLI against the fixture store with a real `--lease`, under a TMPDIR the fixture owns.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import time

from rediacc_hooks.tests import wlfix

SC = wlfix.import_wl("wl_scratch")

OLD_MIN = 300
GIT = [
    "git",
    "-c",
    "user.email=t@example.invalid",
    "-c",
    "user.name=t",
    "-c",
    "init.defaultBranch=main",
]


def backdate(path: pathlib.Path, minutes: float = OLD_MIN) -> None:
    """Move every mtime under `path` (itself included, symlinks not followed) `minutes` into the past."""
    when = time.time() - minutes * 60
    for here, dirs, files in os.walk(path):
        for name in dirs + files:
            os.utime(os.path.join(here, name), (when, when), follow_symlinks=False)
    os.utime(path, (when, when), follow_symlinks=False)


def git(cwd: pathlib.Path, *args: str) -> None:
    subprocess.run([*GIT, *args], cwd=str(cwd), check=True, capture_output=True)


def clone_of(tmp: pathlib.Path, scratch: pathlib.Path, name: str) -> pathlib.Path:
    """A clone under `scratch` of a fresh origin with one commit: clean, and every commit on a remote."""
    origin = tmp / ("origin-" + name)
    origin.mkdir()
    git(origin, "init", "-q")
    (origin / "a.txt").write_text("one\n")
    git(origin, "add", "a.txt")
    git(origin, "commit", "-qm", "one")
    dest = scratch / name
    git(tmp, "clone", "-q", str(origin), str(dest))
    return dest


def verdicts(scratch: pathlib.Path, leases=(), cwds=()) -> dict[str, tuple[bool, str]]:
    return {
        name: (delete, reason)
        for name, _p, _n, _idle, delete, reason in SC.plan(
            str(scratch), SC.DEFAULT_OLDER_MIN, list(leases), list(cwds)
        )
    }


def test_an_old_idle_dir_is_deleted_and_a_young_one_kept(tmp_path):
    scratch = tmp_path / "scratchpad"
    (scratch / "old").mkdir(parents=True)
    (scratch / "old" / "f").write_text("x")
    (scratch / "young").mkdir()
    backdate(scratch / "old")
    (scratch / "young" / "f").write_text("x")
    # A deep fresh write makes the WHOLE tree young: the top directory's own mtime is not the clock.
    (scratch / "deep" / "a" / "b").mkdir(parents=True)
    backdate(scratch / "deep")
    (scratch / "deep" / "a" / "b" / "fresh").write_text("x")
    got = verdicts(scratch)
    assert got["old"] == (True, "idle, unleased, no undelivered work"), got
    assert got["young"][0] is False, got
    assert "younger than" in got["young"][1], got
    assert got["deep"][0] is False, got


def test_a_dir_named_by_a_live_lease_is_kept_and_an_ended_lease_does_not_count(tmp_path):
    scratch = tmp_path / "scratchpad"
    for name in ("leasedwork", "leasedworkx", "freed"):
        (scratch / name).mkdir(parents=True)
        backdate(scratch / name)
    items = [
        {
            "id": "aa11",
            "state": ">",
            "worker": "bg1",
            "lease_note": "writer in $S/leasedwork, patch due",
            "text": "t",
        },
        # The same name on a CLOSED item is history, not a claim.
        {"id": "bb22", "state": "x", "worker": "bg2", "lease_note": "freed", "text": "freed"},
    ]
    got = verdicts(scratch, leases=SC.lease_texts(items))
    assert got["leasedwork"] == (False, "named by live lease #aa11"), got
    # A whole token, so `leasedwork` does not claim `leasedworkx`.
    assert got["leasedworkx"][0] is True, got
    assert got["freed"][0] is True, got


def test_a_process_working_inside_keeps_it(tmp_path):
    scratch = tmp_path / "scratchpad"
    for name in ("busy", "idle"):
        (scratch / name / "sub").mkdir(parents=True)
        backdate(scratch / name)
    got = verdicts(scratch, cwds=[str(scratch / "busy" / "sub")])
    assert got["busy"] == (False, "1 process(es) work inside it"), got
    assert got["idle"][0] is True, got


def test_a_dirty_clone_is_kept_until_its_patch_is_newer_than_its_changes(tmp_path):
    scratch = tmp_path / "scratchpad"
    scratch.mkdir()
    clean = clone_of(tmp_path, scratch, "cleanclone")
    dirty = clone_of(tmp_path, scratch, "dirtyclone")
    (dirty / "a.txt").write_text("edited\n")
    (dirty / "new.txt").write_text("untracked\n")
    backdate(clean)
    backdate(dirty)
    got = verdicts(scratch)
    assert got["cleanclone"][0] is True, got
    assert got["dirtyclone"] == (
        False,
        "dirtyclone has 2 uncommitted change(s) and no dirtyclone.patch",
    ), got

    patch = scratch / "dirtyclone.patch"
    patch.write_text("diff\n")
    backdate(patch, OLD_MIN + 60)
    got = verdicts(scratch)
    assert got["dirtyclone"] == (
        False,
        "dirtyclone has 2 uncommitted change(s) newer than dirtyclone.patch",
    ), got

    backdate(patch, OLD_MIN - 60)
    assert verdicts(scratch)["dirtyclone"][0] is True


def test_a_clone_with_a_commit_on_no_remote_is_kept(tmp_path):
    scratch = tmp_path / "scratchpad"
    scratch.mkdir()
    ahead = clone_of(tmp_path, scratch, "aheadclone")
    (ahead / "b.txt").write_text("b\n")
    git(ahead, "add", "b.txt")
    git(ahead, "commit", "-qm", "local only")
    # Nested one level, the `run1/clone` shape.
    nested = scratch / "run1"
    nested.mkdir()
    inner = clone_of(tmp_path, nested, "clone")
    (inner / "a.txt").write_text("edited\n")
    backdate(ahead)
    backdate(nested)
    got = verdicts(scratch)
    assert got["aheadclone"][0] is False, got
    assert "has commits on no remote" in got["aheadclone"][1], got
    assert got["run1"] == (False, "run1/clone has 1 uncommitted change(s) and no run1.patch"), got


def test_the_probe_does_not_reset_the_idle_clock_it_reads(tmp_path):
    """THE DEFECT THE FIRST LIVE LISTING HAD: a plain `git status` refreshes `.git/index` on stale stat data, so listing once made every clone read "changed 0 min ago" and a frequent prune would never delete anything."""
    scratch = tmp_path / "scratchpad"
    scratch.mkdir()
    clean = clone_of(tmp_path, scratch, "cleanclone")
    backdate(clean)
    # Stale stat data in the index is what provokes the refresh: the worktree file's mtime no longer matches what the index recorded.
    os.utime(clean / "a.txt", (time.time() - 9000, time.time() - 9000))
    before = os.stat(clean / ".git" / "index").st_mtime
    assert verdicts(scratch)["cleanclone"][0] is True
    assert os.stat(clean / ".git" / "index").st_mtime == before, "the probe rewrote .git/index"
    assert verdicts(scratch)["cleanclone"][0] is True, "the second listing read the clone as young"


def test_write_deletes_only_the_deletable_and_never_follows_a_symlink(tmp_path):
    scratch = tmp_path / "scratchpad"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious").write_text("keep me")
    (scratch / "old").mkdir(parents=True)
    (scratch / "old" / "link").symlink_to(outside)
    ro = scratch / "old" / "readonly"
    ro.mkdir()
    (ro / "f").write_text("x")
    ro.chmod(0o500)
    (scratch / "leased").mkdir()
    # A symlink CHILD of the scratchpad is never a candidate, even to a deletable-looking tree.
    (scratch / "linkchild").symlink_to(outside)
    backdate(scratch / "old")
    backdate(scratch / "leased")
    rc, text = SC.prune(
        str(scratch), True, SC.DEFAULT_OLDER_MIN, [("cc33", "scratch leased")], cwds=[]
    )
    assert rc == 0, text
    assert not (scratch / "old").exists(), text
    assert (scratch / "leased").is_dir(), text
    assert (outside / "precious").read_text() == "keep me"
    assert (scratch / "linkchild").is_symlink()
    assert "linkchild" not in text
    assert re.search(
        r"2 directories under the scratchpad: 1 deletable \(\d+ inodes\), 1 kept; deleted 1", text
    ), text


def test_listing_deletes_nothing(tmp_path):
    scratch = tmp_path / "scratchpad"
    (scratch / "old").mkdir(parents=True)
    backdate(scratch / "old")
    rc, text = SC.prune(str(scratch), False, SC.DEFAULT_OLDER_MIN, [], cwds=[])
    assert rc == 0, text
    assert "listing only" in text, text
    assert "DELETE  old" in text, text
    assert (scratch / "old").is_dir()


def test_the_scratchpad_is_derived_and_an_ambiguous_prefix_refused(tmp_path):
    base = tmp_path / "claude-7" / "-p-proj"
    (base / "abcd1234-x").mkdir(parents=True)
    got, why = SC.scratchpad_for("/p/proj", "abcd1234", "abcd1234-full", tmp=str(tmp_path), uid=7)
    assert got == str(base / "abcd1234-full" / "scratchpad")
    assert not why
    got, why = SC.scratchpad_for("/p/proj", "abcd1234", "", tmp=str(tmp_path), uid=7)
    assert got == str(base / "abcd1234-x" / "scratchpad"), why
    (base / "abcd1234-y").mkdir()
    got, why = SC.scratchpad_for("/p/proj", "abcd1234", "", tmp=str(tmp_path), uid=7)
    assert got is None
    assert "2 session directories" in why


def test_the_cli_reads_the_store_s_live_lease(tmp_path):
    """End to end: a real `--add` and `--lease` naming a scratch dir, then `--prune-scratch` listing and writing under the fixture's TMPDIR."""
    fix = wlfix.Fixture(tmp_path / "hookfix")
    fix.setup()
    munged = re.sub(r"[^A-Za-z0-9]", "-", str(fix.proj))
    scratch = (
        pathlib.Path(fix.env["TMPDIR"])
        / ("claude-%d" % os.getuid())
        / munged
        / wlfix.SID
        / "scratchpad"
    )
    for name in ("leasedwork", "finished"):
        (scratch / name).mkdir(parents=True)
        (scratch / name / "f").write_text("x")
        backdate(scratch / name)

    added = fix.cli("--add", wlfix.ME, "(deadbeef)", "scratch prune fixture item")
    item = re.search(r"#([0-9a-f]+)", added.out + added.err)
    assert item, added.out + added.err
    leased = fix.cli(
        "--lease", wlfix.ME, item.group(1), "+30", "worker:l1bg", "writer", "in", "leasedwork"
    )
    assert leased.rc == 0, leased.out + leased.err

    listed = fix.cli("--prune-scratch", wlfix.ME)
    assert listed.rc == 0, listed.err
    assert "scratch: %s" % scratch in listed.out
    assert re.search(r"KEEP\s+leasedwork .*named by live lease #%s" % item.group(1), listed.out), (
        listed.out
    )
    assert re.search(r"DELETE\s+finished ", listed.out), listed.out
    assert (scratch / "finished").is_dir()

    wrote = fix.cli("--prune-scratch", wlfix.ME, "--write")
    assert wrote.rc == 0, wrote.err
    assert not (scratch / "finished").exists()
    assert (scratch / "leasedwork").is_dir()

    bad = fix.cli("--prune-scratch", wlfix.ME, "--older-than", "soon")
    assert bad.rc == 2, bad.err
    assert "usage: worklist.py --prune-scratch" in bad.err, bad.err
