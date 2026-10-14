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
IDENTITY = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
# NO BACKGROUND WRITER IN A TREE WHOSE MTIMES ARE THE SUBJECT. `git commit` ends by starting `git maintenance run --auto --quiet --detach`, and the detached half is still alive when `commit` returns: it holds `.git/objects/maintenance.lock`, and whatever task it decides to run writes under `.git/objects` afterwards. A test here commits and then `backdate`s the tree, so a maintenance child that outlived the commit by one scheduling slice stamped a fresh mtime over the backdated ones and the tree read `changed 0 min ago`.
# That is what GitHub's runner (git 2.55.0, four busy cores) did to `test_a_basetemp_name_is_exempt_only_in_the_shape_pytest_makes` on run 38389205702; on an idle host the child loses the race, so it passed everywhere else.
# `maintenance.auto=false` is the switch `git commit` reads before it spawns anything; `gc.auto=0` is the same for a git old enough to spawn `gc --auto` instead. `test_a_fixture_commit_leaves_no_writer_behind` drives both arms with a task that always has work.
GIT = [
    *IDENTITY,
    "-c",
    "init.defaultBranch=main",
    "-c",
    "maintenance.auto=false",
    "-c",
    "gc.auto=0",
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


def packs_of(clone: pathlib.Path) -> list[str]:
    return sorted(p.name for p in (clone / ".git" / "objects" / "pack").glob("*.pack"))


def test_a_fixture_commit_leaves_no_writer_behind(tmp_path, monkeypatch):
    """The fixture's `git commit` starts no maintenance, even when a maintenance task has work to do.

    The environment hands every git a `loose-objects` task that runs at one loose object, which a fresh commit always has. Without `maintenance.auto=false` the detached child repacks under `.git/objects/pack` AFTER `commit` has returned (measured 20 of 20 on git 2.53.0), which is the writer that stamped a backdated tree. The pack is the evidence either way: none appears behind `GIT` within the half second the test waits, and one does behind the same commit without the switch (the control polls up to 30 s for it, so the wait is not what hides it).
    """
    for index, (key, value) in enumerate(
        (("maintenance.loose-objects.enabled", "true"), ("maintenance.loose-objects.auto", "1"))
    ):
        monkeypatch.setenv("GIT_CONFIG_KEY_%d" % index, key)
        monkeypatch.setenv("GIT_CONFIG_VALUE_%d" % index, value)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "2")
    scratch = tmp_path / "scratchpad"
    scratch.mkdir()
    clone = clone_of(tmp_path, scratch, "work")
    before = packs_of(clone)
    (clone / "b.txt").write_text("b\n")
    git(clone, "add", "b.txt")
    git(clone, "commit", "-qm", "local only")
    time.sleep(0.5)
    assert packs_of(clone) == before, "a maintenance child ran behind the fixture's commit"
    # CONTROL: the same commit WITHOUT the switch is repacked behind its back, so the absence above is the switch's doing and not a task that never fires.
    (clone / "c.txt").write_text("c\n")
    subprocess.run([*IDENTITY, "add", "c.txt"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(
        [*IDENTITY, "commit", "-qm", "c"], cwd=str(clone), check=True, capture_output=True
    )
    deadline = time.monotonic() + 30
    while packs_of(clone) == before and time.monotonic() < deadline:
        time.sleep(0.05)
    assert packs_of(clone) != before, "the control commit started no maintenance"


def test_an_old_idle_dir_is_deleted_and_a_young_one_kept(tmp_path):
    scratch = tmp_path / "scratchpad"
    # Directories only: a plain file would be doubt of its own (test_a_plain_file_outside_every_git_tree_keeps_its_dir), and this case is about the clock.
    (scratch / "old" / "sub").mkdir(parents=True)
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
    # A basetemp, so its plain file is pytest's to discard and the read-only removal path is what this exercises.
    old = scratch / "pytest-5"
    case = old / "test_write0"
    case.mkdir(parents=True)
    (case / "link").symlink_to(outside)
    ro = case / "readonly"
    ro.mkdir()
    (ro / "f").write_text("x")
    ro.chmod(0o500)
    (scratch / "leased").mkdir()
    # A symlink CHILD of the scratchpad is never a candidate, even to a deletable-looking tree.
    (scratch / "linkchild").symlink_to(outside)
    backdate(old)
    backdate(scratch / "leased")
    rc, text = SC.prune(
        str(scratch), True, SC.DEFAULT_OLDER_MIN, [("cc33", "scratch leased")], cwds=[]
    )
    assert rc == 0, text
    assert not old.exists(), text
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
    # `pytest-42` in pytest's own shape (test_wl_scratch's basetemp-shape case): its file sits in a per-test directory.
    for name, sub in (("leasedwork", "."), ("pytest-42", "test_cli0")):
        (scratch / name / sub).mkdir(parents=True, exist_ok=True)
        (scratch / name / sub / "f").write_text("x")
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
    assert re.search(r"DELETE\s+pytest-42 .*a pytest basetemp", listed.out), listed.out
    assert (scratch / "pytest-42").is_dir()

    wrote = fix.cli("--prune-scratch", wlfix.ME, "--write")
    assert wrote.rc == 0, wrote.err
    assert not (scratch / "pytest-42").exists()
    assert (scratch / "leasedwork").is_dir()

    bad = fix.cli("--prune-scratch", wlfix.ME, "--older-than", "soon")
    assert bad.rc == 2, bad.err
    assert "usage: worklist.py --prune-scratch" in bad.err, bad.err


def test_a_plain_file_outside_every_git_tree_keeps_its_dir(tmp_path):
    """REVIEW 7850c0c4.1: a candidate with no git work tree used to pass the git loop vacuously, so `--write` deleted notes and patches nobody had delivered. A plain file outside every work tree is now doubt; the one exemption is a `pytest-<digits>` basetemp, which pytest itself wipes at the start of its next run (`_pytest/tmpdir.py`, `rm_rf(basetemp)`)."""
    scratch = tmp_path / "scratchpad"
    (scratch / "notes").mkdir(parents=True)
    (scratch / "notes" / "draft.md").write_text("undelivered\n")
    # Directories and symlinks only: nothing a deletion could lose.
    (scratch / "hollow" / "a" / "b").mkdir(parents=True)
    (scratch / "hollow" / "link").symlink_to(tmp_path)
    # A clean clone with a loose file BESIDE it: the clone's verdict must not cover the file.
    (scratch / "run2").mkdir()
    clone_of(tmp_path, scratch / "run2", "clone")
    (scratch / "run2" / "result.txt").write_text("output\n")
    # A basetemp holding a fixture repo with a local-only commit: pytest owns it, so neither rule keeps it.
    base = scratch / "pytest-791"
    (base / "test_fixture0").mkdir(parents=True)
    fixture = clone_of(tmp_path, base / "test_fixture0", "fixture")
    (fixture / "b.txt").write_text("b\n")
    git(fixture, "add", "b.txt")
    git(fixture, "commit", "-qm", "local only")
    # One planted character away from the basetemp shape: an ordinary directory again.
    (scratch / "pytest-x1").mkdir()
    (scratch / "pytest-x1" / "f").write_text("x")
    for child in scratch.iterdir():
        backdate(child)
    got = verdicts(scratch)
    assert got["notes"] == (
        False,
        "notes holds 1 file(s) outside any git work tree (notes/draft.md)",
    ), got
    assert got["hollow"] == (True, "idle, unleased, no undelivered work"), got
    assert got["run2"] == (
        False,
        "run2 holds 1 file(s) outside any git work tree (run2/result.txt)",
    ), got
    assert got["pytest-791"] == (True, "idle, unleased, a pytest basetemp"), got
    assert got["pytest-x1"][0] is False, got


def test_a_rename_is_one_change_not_two(tmp_path):
    """REVIEW 7850c0c4.3: `git status -z` writes a rename as `R  new NUL old NUL`; the old path used to be parsed as an entry of its own, so the refusal overcounted."""
    scratch = tmp_path / "scratchpad"
    scratch.mkdir()
    moved = clone_of(tmp_path, scratch, "movedclone")
    git(moved, "mv", "a.txt", "b.txt")
    backdate(moved)
    got = verdicts(scratch)
    assert got["movedclone"] == (
        False,
        "movedclone has 1 uncommitted change(s) and no movedclone.patch",
    ), got


def test_ignored_output_does_not_keep_a_clone_and_untracked_source_does(tmp_path):
    """REVIEW 7850c0c4.2, kept by design: delivery is a `git diff` patch, which never carries an ignored path, so ignored output (a `__pycache__`, a build directory) is not undelivered work. The sibling one fact away, the same file NOT ignored, must keep."""
    scratch = tmp_path / "scratchpad"
    scratch.mkdir()
    for name, ignore in (("ignoredclone", "build/\n"), ("plainclone", "other/\n")):
        clone = clone_of(tmp_path, scratch, name)
        # `info/exclude` ignores without a commit, so the clone stays level with its remote.
        (clone / ".git" / "info" / "exclude").write_text(ignore)
        (clone / "build").mkdir()
        (clone / "build" / "out.bin").write_text("generated\n")
        backdate(clone)
    got = verdicts(scratch)
    assert got["ignoredclone"] == (True, "idle, unleased, no undelivered work"), got
    assert got["plainclone"] == (
        False,
        "plainclone has 1 uncommitted change(s) and no plainclone.patch",
    ), got


def test_a_name_that_is_not_utf8_prints_escaped_and_never_crashes(tmp_path):
    """REVIEW 30573c81.1: `os.scandir` hands back a non-UTF-8 name with surrogates, and the listing printed it raw, so under a UTF-8 locale `print` raised UnicodeEncodeError and the verb died with a traceback. Every name now reaches the text as a `\\xNN` escape, as a candidate's own name and inside a reason alike; driven through the real CLI on a strict UTF-8 stdout."""
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
    scratch.mkdir(parents=True)
    raw = os.fsencode(scratch)
    odd_dir = os.path.join(raw, b"odd\xffdir")
    os.mkdir(odd_dir)
    holder = scratch / "notes"
    holder.mkdir()
    with open(os.path.join(os.fsencode(holder), b"draft\xfe.md"), "wb") as fh:
        fh.write(b"undelivered\n")
    for child in (pathlib.Path(os.fsdecode(odd_dir)), holder):
        backdate(child)
    # A STRICT stream, as `PYTHONIOENCODING=utf-8` sets it: on a host whose only locales are C ones Python falls back to surrogateescape and leaks the raw bytes instead of raising, which is no better.
    env = dict(fix.env, LC_ALL="C.UTF-8", PYTHONIOENCODING="utf-8")
    listed = fix.cli("--prune-scratch", wlfix.ME, env=env)
    assert listed.rc == 0, listed.err
    assert "Traceback" not in listed.err, listed.err
    assert re.search(r"DELETE\s+odd\\xffdir ", listed.out), listed.out
    assert "notes holds 1 file(s) outside any git work tree (notes/draft\\xfe.md)" in listed.out, (
        listed.out
    )
    wrote = fix.cli("--prune-scratch", wlfix.ME, "--write", env=env)
    assert wrote.rc == 0, wrote.err
    assert not os.path.exists(odd_dir)
    assert holder.is_dir()


def test_a_basetemp_name_is_exempt_only_in_the_shape_pytest_makes(tmp_path):
    """REVIEW 30573c81.3: the `pytest-<digits>` exemption keyed on the NAME alone, so a clone stored under such a name, with a commit on no remote, read as a basetemp and `--write` deleted it. The exemption now also needs pytest's own top level: per-test directories ending in digits (`<name>0`, `popen-gw3` under xdist), `<name>current` symlinks, and nothing else (measured against the live scratchpad's basetemps)."""
    scratch = tmp_path / "scratchpad"
    scratch.mkdir()
    # A clone that merely carries the name: `.git` and files at its top.
    ahead = clone_of(tmp_path, scratch, "pytest-6")
    (ahead / "b.txt").write_text("b\n")
    git(ahead, "add", "b.txt")
    git(ahead, "commit", "-qm", "local only")
    # The real shape: a per-test directory holding a fixture repo with a local-only commit, its `current` link, and an xdist worker directory.
    real = scratch / "pytest-7"
    (real / "test_case0").mkdir(parents=True)
    fixture = clone_of(tmp_path, real / "test_case0", "repo")
    (fixture / "c.txt").write_text("c\n")
    git(fixture, "add", "c.txt")
    git(fixture, "commit", "-qm", "local only")
    (real / "test_casecurrent").symlink_to(real / "test_case0")
    (real / "popen-gw3").mkdir()
    for child in scratch.iterdir():
        backdate(child)
    got = verdicts(scratch)
    assert got["pytest-6"][0] is False, got
    assert "has commits on no remote" in got["pytest-6"][1], got
    assert got["pytest-7"] == (True, "idle, unleased, a pytest basetemp"), got
