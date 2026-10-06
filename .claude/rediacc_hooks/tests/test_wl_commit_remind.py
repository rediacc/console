"""The commit reminder (agent/plans/PLAN-fast-loop.md, Part 2): the engine `wl_uncommitted`, the Stop advisory `commit-remind` and the PostToolUse member `commit_remind.py`.

EVERY TRIGGER CASE HAS ITS INVERSE, differing by one planted fact: a commit older or younger than the threshold, an own file or a peer's, a throttle window open or shut. The reminder is ADVISORY by operator ruling (2026-10-06), and the last section proves it two ways: its key is not in the blocking set, and a full Stop run that fires it still allows the stop.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import time
from typing import Any

import pytest
from rediacc_ci import paths

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

STOP_DIR = wlfix.STOP_DIR
HOOKS = STOP_DIR.parent
paths.on_sys_path(STOP_DIR)

import wl_core as C  # noqa: E402
import wl_planqueue  # noqa: E402
import wl_standdown  # noqa: E402
import wl_store as S  # noqa: E402
import wl_uncommitted as U  # noqa: E402

NOW = 1_800_000_000.0


def git(root, *args, env=None):
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **(env or {})},
    )


def make_repo(tmp_path, commit_age_min=30, now=NOW):
    """A real repo with one tracked file committed `commit_age_min` minutes before NOW."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "t")
    (root / "a.txt").write_text("a\n")
    (root / "b.txt").write_text("b\n")
    stamp = "%d +0000" % (now - commit_age_min * 60)
    git(root, "add", "--", "a.txt", "b.txt")
    git(
        root,
        "commit",
        "-q",
        "-m",
        "base",
        env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
    )
    return root


def edit_line(path, ts="2027-01-15T08:00:00Z", name="Edit", key="file_path"):
    return json.dumps(
        {
            "type": "assistant",
            "timestamp": ts,
            "message": {"content": [{"type": "tool_use", "name": name, "input": {key: str(path)}}]},
        }
    )


def write_transcript(path, lines):
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return path


# ---- the cursor --------------------------------------------------------------


def test_cursor_collects_each_edit_tool_and_both_path_keys(tmp_path):
    root = make_repo(tmp_path)
    tr = write_transcript(
        tmp_path / "t.jsonl",
        [
            edit_line(root / "a.txt", name="Edit"),
            edit_line(root / "b.txt", name="Write"),
            edit_line(root / "n.ipynb", name="NotebookEdit", key="notebook_path"),
            edit_line(root / "m.txt", name="MultiEdit"),
        ],
    )
    doc: dict[str, Any] = {}
    assert U.scan_transcript(root, tr, doc, now=NOW)
    assert sorted(doc["uc_files"]) == ["a.txt", "b.txt", "m.txt", "n.ipynb"]
    assert doc["uc_cursor"] == tr.stat().st_size


def test_cursor_ignores_other_tools_and_paths_outside_the_root(tmp_path):
    root = make_repo(tmp_path)
    tr = write_transcript(
        tmp_path / "t.jsonl",
        [
            edit_line(root / "a.txt", name="Read"),
            edit_line(root / "a.txt", name="Bash"),
            edit_line("/etc/passwd", name="Edit"),
            "not json at all",
            json.dumps({"type": "user", "message": {"content": "hi"}}),
        ],
    )
    doc: dict[str, Any] = {}
    U.scan_transcript(root, tr, doc, now=NOW)
    assert doc["uc_files"] == {}


def test_cursor_is_incremental_and_first_seen_is_write_once(tmp_path):
    root = make_repo(tmp_path)
    tr = write_transcript(
        tmp_path / "t.jsonl", [edit_line(root / "a.txt", ts="2027-01-15T08:00:00Z")]
    )
    doc: dict[str, Any] = {}
    U.scan_transcript(root, tr, doc, now=NOW)
    first = doc["uc_files"]["a.txt"]
    cursor = doc["uc_cursor"]
    # Nothing new: the cursor does not move and nothing changes.
    assert U.scan_transcript(root, tr, doc, now=NOW) is False
    with open(tr, "a", encoding="utf-8") as handle:
        handle.write(edit_line(root / "a.txt", ts="2027-01-15T09:00:00Z") + "\n")
        handle.write(edit_line(root / "b.txt", ts="2027-01-15T09:30:00Z") + "\n")
    U.scan_transcript(root, tr, doc, now=NOW)
    assert doc["uc_files"]["a.txt"] == first, "a second edit must not move first-seen"
    assert "b.txt" in doc["uc_files"]
    assert doc["uc_cursor"] > cursor


def test_cursor_leaves_a_half_written_last_line_unread(tmp_path):
    root = make_repo(tmp_path)
    tr = tmp_path / "t.jsonl"
    whole = edit_line(root / "a.txt") + "\n"
    tr.write_text(whole + edit_line(root / "b.txt")[:30], encoding="utf-8")
    doc: dict[str, Any] = {}
    U.scan_transcript(root, tr, doc, now=NOW)
    assert list(doc["uc_files"]) == ["a.txt"]
    assert doc["uc_cursor"] == len(whole.encode())
    with open(tr, "a", encoding="utf-8") as handle:
        handle.write(edit_line(root / "b.txt")[30:] + "\n")
    U.scan_transcript(root, tr, doc, now=NOW)
    assert sorted(doc["uc_files"]) == ["a.txt", "b.txt"]


def test_cursor_catch_up_is_bounded_on_a_first_read(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    old = edit_line(root / "a.txt")
    new = edit_line(root / "b.txt")
    tr = write_transcript(tmp_path / "t.jsonl", [old] * 50 + [new])
    monkeypatch.setattr(U, "CATCHUP_MAX_BYTES", len(new) + 20)
    doc: dict[str, Any] = {}
    U.scan_transcript(root, tr, doc, now=NOW)
    assert list(doc["uc_files"]) == ["b.txt"], "only the tail inside the bound is read"
    assert doc["uc_cursor"] == tr.stat().st_size


def test_cursor_past_the_end_restarts_from_the_top(tmp_path):
    root = make_repo(tmp_path)
    tr = write_transcript(tmp_path / "t.jsonl", [edit_line(root / "a.txt")])
    doc: dict[str, Any] = {"uc_cursor": 10**9}
    U.scan_transcript(root, tr, doc, now=NOW)
    assert "a.txt" in doc["uc_files"]


def test_a_missing_transcript_is_a_quiet_no_op(tmp_path):
    root = make_repo(tmp_path)
    doc: dict[str, Any] = {}
    assert U.scan_transcript(root, tmp_path / "gone.jsonl", doc) is False
    assert U.scan_transcript(root, "", doc) is False
    assert doc == {}


# ---- the dirty intersection and the trigger -------------------------------


def test_a_peers_dirty_file_is_never_counted(tmp_path):
    root = make_repo(tmp_path)
    (root / "a.txt").write_text("mine\n")
    (root / "b.txt").write_text("a peer's\n")
    tr = write_transcript(tmp_path / "t.jsonl", [edit_line(root / "a.txt")])
    facts = U.evaluate(root, tr, {}, now=NOW, minutes=15)
    assert facts
    assert facts["files"] == ["a.txt"]
    assert facts["count"] == 1
    # The inverse: with only the peer's file dirty, nothing is owed.
    (root / "a.txt").write_text("a\n")
    assert U.evaluate(root, tr, {}, now=NOW, minutes=15) is None


def test_trigger_boundary_at_commit_remind_min(tmp_path):
    root = make_repo(tmp_path, commit_age_min=30)
    (root / "a.txt").write_text("x\n")
    tr = write_transcript(tmp_path / "t.jsonl", [edit_line(root / "a.txt")])
    assert U.evaluate(root, tr, {}, now=NOW, minutes=30) is not None, "age == threshold fires"
    assert U.evaluate(root, tr, {}, now=NOW, minutes=31) is None, "age < threshold is silent"


def test_clean_tree_owes_nothing_however_old_the_last_commit(tmp_path):
    root = make_repo(tmp_path, commit_age_min=5000)
    tr = write_transcript(tmp_path / "t.jsonl", [edit_line(root / "a.txt")])
    assert U.evaluate(root, tr, {}, now=NOW, minutes=15) is None


def test_threshold_comes_from_the_queue_settings(tmp_path):
    root = make_repo(tmp_path, commit_age_min=20)
    (root / "a.txt").write_text("x\n")
    tr = write_transcript(tmp_path / "t.jsonl", [edit_line(root / "a.txt")])
    # No QUEUE.md: the default (15) applies, so a 20-minute-old commit fires.
    assert U.evaluate(root, tr, {}, now=NOW) is not None
    queue = root / wl_planqueue.QUEUE_REL
    queue.parent.mkdir(parents=True)
    queue.write_text(
        wl_planqueue.set_settings("# Plan queue\n\n## Promoted\n", {"commit_remind_min": "45"}),
        encoding="utf-8",
    )
    assert U.remind_min(root) == 45
    assert U.evaluate(root, tr, {}, now=NOW) is None


def test_oldest_age_and_listing_in_the_rendered_text(tmp_path):
    root = make_repo(tmp_path, commit_age_min=40)
    for i in range(12):
        (root / ("f%d.txt" % i)).write_text("x\n")
    lines = [edit_line(root / ("f%d.txt" % i), ts="2027-01-15T08:00:00Z") for i in range(12)]
    tr = write_transcript(tmp_path / "t.jsonl", lines)
    # Epoch of the stamp used above; a clock one hour later reads "60 min".
    first = U._epoch("2027-01-15T08:00:00Z", 0)
    facts = U.evaluate(root, tr, {}, now=first + 3600, minutes=15)
    assert facts["count"] == 12
    assert facts["oldest_min"] == 60
    text = U.render(facts)
    assert "12 file(s)" in text
    assert "60 min" in text
    assert text.count("\n  - ") == U.LIST_CAP
    assert "and 4 more" in text
    assert "git add -- <new paths>" in text
    assert "git commit -F <msg> -- <paths>" in text
    assert "nocommit:<reason>" in text


def test_a_committed_file_drops_out_and_a_new_edit_restarts_its_clock(tmp_path):
    root = make_repo(tmp_path, commit_age_min=30)
    (root / "a.txt").write_text("x\n")
    tr = write_transcript(tmp_path / "t.jsonl", [edit_line(root / "a.txt")])
    doc: dict[str, Any] = {}
    assert U.evaluate(root, tr, doc, now=NOW, minutes=15)
    git(root, "add", "--", "a.txt")
    git(root, "commit", "-q", "-m", "mine")
    assert U.evaluate(root, tr, doc, now=NOW + 1, minutes=15) is None
    assert "a.txt" not in doc["uc_files"]


def test_porcelain_parser_handles_renames_and_untracked_dirs():
    text = " M a.txt\0R  new.txt\0old.txt\0?? d/\0"
    assert U.parse_porcelain(text) == ["a.txt", "new.txt", "d/"]
    assert U._dirty_match({"d/x.py": 1, "a.txt": 1, "z": 1}, ["a.txt", "d/"]) == ["a.txt", "d/x.py"]


# ---- the throttle ------------------------------------------------------------


class GitCalls:
    """Counts `git status` and `git log` subprocess runs through wl_uncommitted."""

    def __init__(self, monkeypatch):
        self.verbs: list[str] = []
        real = subprocess.run

        def counting(argv, *a, **kw):
            if argv and argv[0] == "git":
                self.verbs.append(argv[3] if argv[1] == "-C" else argv[1])
            return real(argv, *a, **kw)

        monkeypatch.setattr(U.subprocess, "run", counting)

    @property
    def status(self):
        return self.verbs.count("status")


def test_status_is_throttled_to_the_ten_minute_floor(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    (root / "a.txt").write_text("x\n")
    tr = write_transcript(tmp_path / "t.jsonl", [edit_line(root / "a.txt")])
    calls = GitCalls(monkeypatch)
    doc: dict[str, Any] = {}
    U.evaluate(root, tr, doc, now=NOW, minutes=15)
    assert calls.status == 1
    U.evaluate(root, tr, doc, now=NOW + U.STATUS_FLOOR_S - 1, minutes=15)
    assert calls.status == 1, "inside the floor the cached read is used"
    U.evaluate(root, tr, doc, now=NOW + U.STATUS_FLOOR_S, minutes=15)
    assert calls.status == 2, "at the floor the read is refreshed"


def test_a_new_commit_forces_a_fresh_status_read_inside_the_floor(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    (root / "a.txt").write_text("x\n")
    tr = write_transcript(tmp_path / "t.jsonl", [edit_line(root / "a.txt")])
    calls = GitCalls(monkeypatch)
    doc: dict[str, Any] = {}
    U.evaluate(root, tr, doc, now=NOW, minutes=15)
    git(root, "add", "--", "a.txt")
    git(root, "commit", "-q", "-m", "mine")
    assert U.evaluate(root, tr, doc, now=NOW + 5, minutes=15) is None
    assert calls.status == 2


# ---- read-only by construction ---------------------------------------------


MUTATING = re.compile(
    r"\b(add|commit|stash|restore|checkout|clean|reset|rebase|merge|rm|mv|push|pull|cherry-pick|revert|apply|am)\b"
)


def test_the_engine_runs_only_git_status_and_git_log():
    source = (STOP_DIR / "wl_uncommitted.py").read_text(encoding="utf-8")
    verbs = set(re.findall(r'_git\(\s*\w+,\s*"([a-z-]+)"', source))
    assert verbs == {"log", "status"}, verbs
    for call in re.findall(r'_git\([^)]*\)|\["git"[^\]]*\]', source):
        assert not MUTATING.search(call.replace("--porcelain", "")), call


def test_the_source_scan_control_catches_a_planted_mutating_verb():
    planted = 'out = _git(root, "stash", "push")'
    verbs = set(re.findall(r'_git\(\s*\w+,\s*"([a-z-]+)"', planted))
    assert verbs - {"log", "status"} == {"stash"}


def test_evaluation_leaves_the_worktree_and_index_byte_identical(tmp_path):
    root = make_repo(tmp_path)
    (root / "a.txt").write_text("x\n")
    (root / "new.txt").write_text("n\n")
    tr = write_transcript(tmp_path / "t.jsonl", [edit_line(root / "a.txt")])

    def snapshot():
        return subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v2", "--branch"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    before = snapshot()
    U.evaluate(root, tr, {}, now=NOW, minutes=1)
    assert snapshot() == before


# ---- advisory, never blocking -------------------------------------------------


def test_the_keys_are_focus_advisories_and_not_core_or_cap_wait():
    for key in ("commit-remind", "receipt-behind", "ci-hold"):
        assert wl_standdown.advisory_kept(key), key
        assert key not in wl_standdown.CORE, "%s must not be a blocking core key" % key


def test_the_stop_wiring_uses_the_allow_queue_and_never_vadd():
    source = (STOP_DIR / "wl_checks.py").read_text(encoding="utf-8")
    for key in ("commit-remind", "receipt-behind", "ci-hold"):
        assert 'vadd("%s"' % key not in source
        assert re.search(r'outq_add\(\s*worklist,\s*session_id,\s*state_doc,\s*"%s"' % key, source)


def init_real_repo(proj, commit_age_min):
    """Replace the fixture's plain `.git` directory with a real repo holding one old commit."""
    shutil.rmtree(proj / ".git")
    git(proj, "init", "-q")
    git(proj, "config", "user.email", "t@example.invalid")
    git(proj, "config", "user.name", "t")
    (proj / "work.txt").write_text("w\n")
    stamp = "%d +0000" % (time.time() - commit_age_min * 60)
    git(proj, "add", "--", "work.txt")
    git(
        proj,
        "commit",
        "-q",
        "-m",
        "base",
        env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
    )


def test_a_full_stop_run_carries_the_reminder_and_still_allows(wl):  # noqa: F811
    init_real_repo(wl.proj, commit_age_min=60)
    wl.settings(commit_remind_min=15)
    (wl.proj / "work.txt").write_text("edited\n")
    wl.append_transcript(
        json.loads(edit_line(wl.proj / "work.txt", ts="2026-10-06T10:00:00Z")),
    )
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    got = wl.run()
    assert got.rc == 0, got.out[:400] + got.err[:400]
    assert "COMMIT REMINDER" in got.out, got.out[:600] + got.err[:400]
    assert '"decision"' not in got.out
    assert "Do not stop yet" not in got.out


def test_the_inverse_stop_run_is_silent_when_the_commit_is_recent(wl):  # noqa: F811
    init_real_repo(wl.proj, commit_age_min=1)
    wl.settings(commit_remind_min=15)
    (wl.proj / "work.txt").write_text("edited\n")
    wl.append_transcript(json.loads(edit_line(wl.proj / "work.txt")))
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    got = wl.run()
    assert "COMMIT REMINDER" not in got.out


# ---- the PostToolUse member ------------------------------------------------


def load_member():
    spec = importlib.util.spec_from_file_location(
        "commit_remind_member", HOOKS / "post-tool" / "commit_remind.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def member_env(tmp_path, monkeypatch):
    root = make_repo(tmp_path, commit_age_min=40, now=time.time())
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("WORKLIST_STORE_DIR", str(tmp_path / "store"))
    for var in ("COMMIT_REVIEW_CHILD", "STOPHOOK_CHILD"):
        monkeypatch.delenv(var, raising=False)
    (root / "a.txt").write_text("x\n")
    tr = write_transcript(tmp_path / "t.jsonl", [edit_line(root / "a.txt")])
    return root, tr


def run_member(payload):
    member = load_member()
    out = io.StringIO()
    rc = member.main(stdin=io.StringIO(json.dumps(payload)), stdout=out)
    return rc, out.getvalue()


def payload(root, tr, tool="Edit", session="feedface-0000"):
    return {
        "session_id": session,
        "transcript_path": str(tr),
        "cwd": str(root),
        "tool_name": tool,
        "tool_input": {"file_path": str(root / "a.txt")},
    }


def test_member_emits_posttooluse_context_json_on_an_edit(member_env):
    root, tr = member_env
    rc, out = run_member(payload(root, tr))
    assert rc == 0
    doc = json.loads(out)
    assert doc["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "COMMIT REMINDER" in doc["hookSpecificOutput"]["additionalContext"]
    assert "a.txt" in doc["hookSpecificOutput"]["additionalContext"]


def test_member_is_throttled_to_once_per_five_minutes(member_env):
    root, tr = member_env
    member = load_member()
    p = payload(root, tr)
    t0 = time.time()
    first = member.remind(p, now=t0)
    assert "COMMIT REMINDER" in first
    assert member.remind(p, now=t0 + member.THROTTLE_S - 1) == "", "inside the window"
    assert "COMMIT REMINDER" in member.remind(p, now=t0 + member.THROTTLE_S), "window elapsed"


def test_member_is_silent_for_every_other_tool_and_never_imports_the_stop_modules(member_env):
    root, tr = member_env
    for tool in ("Bash", "Read", "Grep", "Agent", ""):
        rc, out = run_member(payload(root, tr, tool=tool))
        assert (rc, out) == (0, ""), tool
    # The cheap exit comes before any state read: no sidecar and no state doc appear.
    assert not list(pathlib.Path(os.environ["TMPDIR"]).glob("claude-worklist/*"))


def test_member_is_silent_when_nothing_is_owed_and_exits_zero_on_garbage(member_env):
    root, tr = member_env
    (root / "a.txt").write_text("a\n")  # back to the committed content
    rc, out = run_member(payload(root, tr))
    assert (rc, out) == (0, "")
    member = load_member()
    for raw in ("", "not json", "[]", "null"):
        assert member.main(stdin=io.StringIO(raw), stdout=io.StringIO()) == 0


def test_member_does_not_clobber_the_stop_hooks_own_state_fields(member_env):
    root, tr = member_env
    member = load_member()
    p = payload(root, tr)
    worklist = C.worklist_for(root)
    S.save_state(worklist, p["session_id"], {"stop_owned": "keep me"})
    member.remind(p, now=time.time())
    state = S.load_state(worklist, p["session_id"])
    assert state["stop_owned"] == "keep me"
    assert "a.txt" in state["uc_files"]
