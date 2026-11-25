"""wl_roster.RosterCache: the cached readers answer exactly what the uncached ones do (PR-TASK 79b7e92e).

The cache exists because two hot guards re-read gigabytes of transcript per call (block_commit_of_live_writer_file on every commit, block_plan_concurrency on every spawn). Its one risk is a STALE answer, so each case grows, shrinks or replaces a transcript after the cache has seen it and compares the cached reader with the uncached one on the same bytes. Controls first: a transcript that never finished is never cached as finished, and a transcript with no edit reads empty through both readers.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import TYPE_CHECKING

import pytest
import wl_liveness
import wl_report
import wl_roster

if TYPE_CHECKING:
    import pathlib

ROOT = "/repo"


def _write(path: pathlib.Path, records, mode="a", newline=True):
    with path.open(mode, encoding="utf-8") as fh:
        for i, rec in enumerate(records):
            fh.write(json.dumps(rec))
            if newline or i < len(records) - 1:
                fh.write("\n")


def _age(path: pathlib.Path, seconds: float) -> None:
    then = time.time() - seconds
    os.utime(path, (then, then))


def idle() -> dict:
    return {
        "type": "assistant",
        "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": "done"}]},
    }


def edit(path: str) -> dict:
    return {
        "type": "assistant",
        "cwd": ROOT,
        "message": {
            "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": path}}],
        },
    }


def bash(cmd: str) -> dict:
    return {
        "type": "assistant",
        "cwd": ROOT,
        "message": {
            "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "name": "Bash", "input": {"command": cmd}}],
        },
    }


# ---- finished verdicts ----------------------------------------------------------------------


def test_control_a_working_transcript_is_never_cached_as_finished(tmp_path):
    jsonl = tmp_path / "agent-w.jsonl"
    _write(jsonl, [edit(ROOT + "/a.py")])
    cache = wl_roster.RosterCache()
    assert wl_roster.finished_cached(cache, jsonl, time.time()) is False
    assert cache.doc["finished"] == {}
    assert cache.dirty is False


def test_a_finished_transcript_that_grows_is_judged_again_not_served_stale(tmp_path):
    jsonl = tmp_path / "agent-f.jsonl"
    _write(jsonl, [edit(ROOT + "/a.py"), idle()])
    _age(jsonl, 60)
    cache = wl_roster.RosterCache()
    assert wl_roster.finished_cached(cache, jsonl, time.time()) is True
    assert cache.finished_hint(jsonl, jsonl.stat()) is not None
    # A resume appends a tool call in flight: the uncached test says working, and so must the cache.
    _write(jsonl, [edit(ROOT + "/b.py")])
    now = time.time()
    assert wl_roster.proven_finished(jsonl, now) is False
    assert wl_roster.finished_cached(cache, jsonl, now) is False


def test_a_finished_verdict_survives_a_reload_and_is_served_without_reading(tmp_path, monkeypatch):
    jsonl = tmp_path / "agent-f.jsonl"
    _write(jsonl, [idle()])
    _age(jsonl, 60)
    store = tmp_path / "cache" / "s.json"
    first = wl_roster.RosterCache(store)
    assert wl_roster.finished_cached(first, jsonl, time.time()) is True
    first.save()
    assert store.is_file()
    again = wl_roster.RosterCache(store)

    def no_read(*_a, **_k):
        raise AssertionError("a cached finished verdict must not re-run the full proof")

    checked = []
    real = wl_roster._verified_finished

    def spy(*a):
        checked.append(a)
        return real(*a)

    monkeypatch.setattr(wl_roster, "last_record", no_read)
    monkeypatch.setattr(wl_roster, "_final_line_offset", no_read)
    monkeypatch.setattr(wl_roster, "_verified_finished", spy)
    assert wl_roster.finished_cached(again, jsonl, time.time()) is True
    assert len(checked) == 1, "the cached verdict is served only after its bounded re-check"


# ---- a forged entry changes no verdict (review 05db4e68.1) ------------------------------------


def _forge(cache, jsonl, off):
    st = jsonl.stat()
    sig = [st.st_ino, st.st_size, st.st_mtime_ns]
    cache.doc["finished"][str(jsonl)] = sig if off is None else [*sig, off]


def _line_starts(jsonl):
    blob = jsonl.read_bytes()
    return [0] + [i + 1 for i, b in enumerate(blob) if b == 0x0A and i + 1 < len(blob)]


@pytest.mark.parametrize("which", ["bare", "every-line", "mid-line", "past-end", "junk"])
def test_a_forged_finished_entry_for_a_live_agent_is_refused_and_dropped(tmp_path, which):
    jsonl = tmp_path / "agent-live.jsonl"
    # A live writer: an idle turn earlier, then a tool call in flight as its last record.
    _write(jsonl, [idle(), edit(ROOT + "/a.py"), edit(ROOT + "/b.py")])
    _age(jsonl, 600)
    now = time.time()
    assert wl_roster.proven_finished(jsonl, now) is False
    offs = {
        "bare": [None],
        "every-line": _line_starts(jsonl),
        "mid-line": [1, 7, jsonl.stat().st_size - 2],
        "past-end": [jsonl.stat().st_size, jsonl.stat().st_size + 10, -1],
        "junk": ["0", 0.0, True],
    }[which]
    for off in offs:
        cache = wl_roster.RosterCache()
        _forge(cache, jsonl, off)
        assert wl_roster.finished_cached(cache, jsonl, now) is False, off
        assert str(jsonl) not in cache.doc["finished"], off


def test_a_forged_entry_survives_no_reload_either(tmp_path):
    jsonl = tmp_path / "agent-live.jsonl"
    _write(jsonl, [idle(), edit(ROOT + "/a.py")])
    store = tmp_path / "cache" / "s.json"
    store.parent.mkdir()
    st = jsonl.stat()
    store.write_text(
        json.dumps(
            {
                "v": wl_roster.ROSTER_CACHE_SCHEMA,
                "finished": {str(jsonl): [st.st_ino, st.st_size, st.st_mtime_ns, 0]},
                "edits": {},
                "delivered": {},
            }
        ),
        encoding="utf-8",
    )
    cache = wl_roster.RosterCache(store)
    assert wl_roster.finished_cached(cache, jsonl, time.time()) is False
    cache.save()
    assert str(jsonl) not in json.loads(store.read_text(encoding="utf-8"))["finished"]


def test_control_a_genuinely_finished_agent_is_recorded_at_its_final_line(tmp_path):
    jsonl = tmp_path / "agent-done.jsonl"
    _write(jsonl, [edit(ROOT + "/a.py"), edit(ROOT + "/b.py"), idle()])
    _age(jsonl, 60)
    cache = wl_roster.RosterCache()
    assert wl_roster.finished_cached(cache, jsonl, time.time()) is True
    st = jsonl.stat()
    ent = cache.doc["finished"][str(jsonl)]
    assert ent == [st.st_ino, st.st_size, st.st_mtime_ns, _line_starts(jsonl)[-1]]
    # Served again from the entry, and a killed-mid-turn agent (durable on the clock) is recorded too.
    assert wl_roster.finished_cached(cache, jsonl, time.time()) is True
    dead = tmp_path / "agent-dead.jsonl"
    _write(dead, [edit(ROOT + "/a.py"), {"type": "user", "message": {"content": "result"}}])
    _age(dead, wl_roster.WAIT_HORIZON_MIN * 60 + 60)
    assert wl_roster.finished_cached(cache, dead, time.time()) is True
    assert str(dead) in cache.doc["finished"]


def test_a_finished_entry_whose_final_line_was_rewritten_in_place_is_judged_again(tmp_path):
    jsonl = tmp_path / "agent-f.jsonl"
    _write(jsonl, [edit(ROOT + "/a.py"), idle()])
    _age(jsonl, 60)
    cache = wl_roster.RosterCache()
    assert wl_roster.finished_cached(cache, jsonl, time.time()) is True
    st = jsonl.stat()
    # Same length, same inode, same mtime: only the bytes say the turn did not end.
    blob = jsonl.read_bytes().replace(b'"end_turn"', b'"tool_use"')
    assert len(blob) == st.st_size
    with jsonl.open("r+b") as fh:
        fh.write(blob)
    os.utime(jsonl, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert wl_roster.finished_cached(cache, jsonl, time.time()) is False
    assert str(jsonl) not in cache.doc["finished"]


def test_a_verdict_resting_on_an_idle_edge_is_answered_but_not_cached(tmp_path, monkeypatch):
    jsonl = tmp_path / "agent-t.jsonl"
    _write(jsonl, [edit(ROOT + "/a.py")])
    mtime = jsonl.stat().st_mtime
    monkeypatch.setattr(wl_liveness, "idle_edge", lambda *_a: mtime)
    cache = wl_roster.RosterCache()
    now = time.time()
    assert wl_roster.proven_finished(jsonl, now, "mate", "/c", "s") is True
    assert wl_roster.finished_cached(cache, jsonl, now, "mate", "/c", "s") is True
    assert cache.doc["finished"] == {}


def test_a_corrupt_or_foreign_cache_file_reads_as_empty(tmp_path):
    store = tmp_path / "s.json"
    store.write_text("{not json", encoding="utf-8")
    assert wl_roster.RosterCache(store).doc["finished"] == {}
    store.write_text(json.dumps({"v": 999, "finished": {"x": [1, 2, 3]}}), encoding="utf-8")
    assert wl_roster.RosterCache(store).doc["finished"] == {}


def test_roster_cache_lives_under_the_git_common_dir(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    sub = tmp_path / "proj" / "sess-1234" / "subagents"
    cache = wl_roster.roster_cache(repo, sub)
    assert cache.path == repo.resolve() / ".git" / wl_roster.ROSTER_CACHE_DIR / "sess-1234.json"
    # No git dir: kept in memory only, and save writes nothing.
    loose = wl_roster.roster_cache(tmp_path / "nowhere", sub)
    assert loose.path is None
    loose.dirty = True
    loose.save()


# ---- incremental edit paths -------------------------------------------------------------------


@pytest.mark.parametrize("strict", [False, True])
def test_cached_edit_paths_equal_the_whole_read_through_growth(tmp_path, strict):
    jsonl = tmp_path / "agent-e.jsonl"
    cache = wl_roster.RosterCache()
    _write(jsonl, [{"type": "user", "message": {"content": "brief"}}])
    assert wl_roster.edit_paths_cached(jsonl, ROOT, cache, strict) == set()
    assert wl_roster.edit_paths(jsonl, ROOT, strict) == set()
    _write(jsonl, [edit(ROOT + "/a.py"), bash("echo hi > %s/out.txt" % ROOT)])
    first = wl_roster.edit_paths_cached(jsonl, ROOT, cache, strict)
    assert first == wl_roster.edit_paths(jsonl, ROOT, strict)
    assert "a.py" in first
    assert "out.txt" in first
    _write(jsonl, [edit(ROOT + "/b.py"), edit(ROOT + "/.claude/worktrees/x/lease.py")])
    grown = wl_roster.edit_paths_cached(jsonl, ROOT, cache, strict)
    assert grown == wl_roster.edit_paths(jsonl, ROOT, strict)
    assert "b.py" in grown
    assert not any(p.startswith(".claude/worktrees/") for p in grown)


def test_a_trailing_line_without_newline_is_read_but_not_consumed(tmp_path):
    jsonl = tmp_path / "agent-p.jsonl"
    cache = wl_roster.RosterCache()
    _write(jsonl, [edit(ROOT + "/a.py"), edit(ROOT + "/c.py")], newline=False)
    assert wl_roster.edit_paths_cached(jsonl, ROOT, cache) == {"a.py", "c.py"}
    assert wl_roster.edit_paths(jsonl, ROOT) == {"a.py", "c.py"}
    ent = cache.get("edits", str(jsonl))
    assert ent["off"] < jsonl.stat().st_size
    assert ent["paths"] == ["a.py"]
    # The newline arrives with the next record; the half line is consumed once, then.
    with jsonl.open("a", encoding="utf-8") as fh:
        fh.write("\n")
    _write(jsonl, [edit(ROOT + "/d.py")])
    assert wl_roster.edit_paths_cached(jsonl, ROOT, cache) == {"a.py", "c.py", "d.py"}


def test_a_replaced_or_shrunk_transcript_is_read_again_from_zero(tmp_path):
    jsonl = tmp_path / "agent-r.jsonl"
    cache = wl_roster.RosterCache()
    _write(jsonl, [edit(ROOT + "/old1.py"), edit(ROOT + "/old2.py")])
    assert wl_roster.edit_paths_cached(jsonl, ROOT, cache) == {"old1.py", "old2.py"}
    # Shrunk in place: the saved offset lies past the end.
    _write(jsonl, [edit(ROOT + "/n.py")], mode="w")
    assert jsonl.stat().st_size < cache.get("edits", str(jsonl))["off"]
    assert wl_roster.edit_paths_cached(jsonl, ROOT, cache) == {"n.py"}
    # Replaced by a new file (new inode) LONGER than the old offset: still read from 0.
    fresh = tmp_path / "agent-r.new"
    _write(fresh, [edit(ROOT + "/x%d.py" % i) for i in range(6)])
    os.replace(fresh, jsonl)
    assert wl_roster.edit_paths_cached(jsonl, ROOT, cache) == wl_roster.edit_paths(jsonl, ROOT)
    assert "n.py" not in wl_roster.edit_paths_cached(jsonl, ROOT, cache)


def test_another_reading_is_not_served_from_the_cache(tmp_path):
    jsonl = tmp_path / "agent-s.jsonl"
    cache = wl_roster.RosterCache()
    _write(jsonl, [edit("/other/a.py")])
    assert wl_roster.edit_paths_cached(jsonl, "/other", cache) == {"a.py"}
    assert wl_roster.edit_paths_cached(jsonl, ROOT, cache) == {"/other/a.py"}


# ---- the lead transcript checkpoint -----------------------------------------------------------


def note(aid: str, stamp: str) -> dict:
    return {
        "type": "user",
        "timestamp": stamp,
        "message": {
            "content": "<task-notification><task-id>%s</task-id><status>completed</status><result>ok</result></task-notification>"
            % aid
        },
    }


def _lead(tmp_path):
    sess = tmp_path / "proj" / "sess"
    (sess / "subagents").mkdir(parents=True)
    return sess / "subagents", sess.with_suffix(".jsonl")


def test_completed_since_reads_only_what_was_appended_and_matches_the_whole_read(
    tmp_path, monkeypatch
):
    sub, lead = _lead(tmp_path)
    _write(lead, [note("aaaa1111", "2026-11-24T10:00:00+00:00")])
    cache = wl_roster.RosterCache()
    first = wl_roster._completed_since(sub, 0, cache=cache)
    assert first == wl_roster._completed_since(sub, 0)
    assert len(first) == 1
    _write(lead, [note("bbbb2222", "2026-11-24T11:00:00+00:00")])
    seen = []
    real = wl_report.delivered_ids

    def spy(path, cursor=None, require_result=True):
        seen.append(int((cursor or {}).get("off") or 0))
        return real(path, cursor=cursor, require_result=require_result)

    monkeypatch.setattr(wl_report, "delivered_ids", spy)
    grown = wl_roster._completed_since(sub, 0, cache=cache)
    assert seen
    assert seen[0] > 0, "the second read must resume from the saved offset"
    monkeypatch.setattr(wl_report, "delivered_ids", real)
    assert grown == wl_roster._completed_since(sub, 0)
    assert len(grown) == 2


def test_completed_since_restarts_on_a_new_inode_or_a_shrink(tmp_path):
    sub, lead = _lead(tmp_path)
    _write(
        lead,
        [
            note("aaaa1111", "2026-11-24T10:00:00+00:00"),
            note("cccc3333", "2026-11-24T10:05:00+00:00"),
        ],
    )
    cache = wl_roster.RosterCache()
    assert len(wl_roster._completed_since(sub, 0, cache=cache)) == 2
    # Shrunk: the old ids are gone with the bytes that carried them.
    _write(lead, [note("dddd4444", "2026-11-24T12:00:00+00:00")], mode="w")
    assert wl_roster._completed_since(sub, 0, cache=cache) == wl_roster._completed_since(sub, 0)
    # Replaced with a longer file: a new inode restarts at 0 even though the offset still fits.
    fresh = lead.with_suffix(".new")
    _write(fresh, [note("eeee%04d" % i, "2026-11-24T13:00:00+00:00") for i in range(5)])
    os.replace(fresh, lead)
    got = wl_roster._completed_since(sub, 0, cache=cache)
    assert got == wl_roster._completed_since(sub, 0)
    assert all(k.startswith("eeee") for k in got)


# ---- one estimate per guard run ---------------------------------------------------------------


def test_pinned_estimate_computes_once_and_unpins_on_exit(monkeypatch):
    calls = []

    def located(cwd, session_id):
        calls.append((cwd, session_id))

    monkeypatch.setattr(wl_roster, "session_subagents_dir", located)
    with wl_roster.pinned_estimate("/c", "s") as est:
        assert est == (None, {})
        assert wl_roster.live_estimate("/c", "s") is est
        assert len(calls) == 1
        # A caller with its own clock asks a different question, and a different session is not pinned.
        wl_roster.live_estimate("/c", "s", now=1.0)
        wl_roster.live_estimate("/c", "other")
        assert len(calls) == 3
    wl_roster.live_estimate("/c", "s")
    assert len(calls) == 4
    assert wl_roster._PINNED == {}
