"""`wl_roster.load_metas` parses each subagent meta once per process (agent/plans/PLAN-tooling-speed.md SP8).

A stop called it seven times over 4,334 metas on 2026-11-24, about 1 s of reads and JSON. The memo is keyed on each file's mtime and size, so a rewritten meta (a resume, a finish) is read again.
"""

from __future__ import annotations

import json
import os
import pathlib

from rediacc_hooks.tests import wlfix

RO = wlfix.import_wl("wl_roster")


def _meta(sub, aid, **info):
    p = sub / ("agent-%s.meta.json" % aid)
    p.write_text(
        json.dumps({"agentType": "general-purpose", "description": aid, **info}), encoding="utf-8"
    )
    return p


def _reads(monkeypatch):
    seen = []
    real = pathlib.Path.read_text

    def read_text(self, *a, **k):
        if self.name.endswith(".meta.json"):
            seen.append(self.name)
        return real(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_text", read_text)
    return seen


def test_a_second_call_reads_no_meta_and_answers_the_same(tmp_path, monkeypatch):
    for n in range(5):
        _meta(tmp_path, "a%d" % n)
    first = RO.load_metas(tmp_path)
    seen = _reads(monkeypatch)
    assert RO.load_metas(tmp_path) == first
    assert seen == []


def test_control_a_rewritten_meta_is_read_again(tmp_path, monkeypatch):
    p = _meta(tmp_path, "b0")
    assert RO.load_metas(tmp_path)["b0"]["finished"] is False
    _meta(tmp_path, "b0", finished=True)
    st = p.stat()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    seen = _reads(monkeypatch)
    assert RO.load_metas(tmp_path)["b0"]["finished"] is True
    assert seen == ["agent-b0.meta.json"]


def test_control_a_caller_edit_does_not_leak_into_the_next_answer(tmp_path):
    _meta(tmp_path, "c0")
    RO.load_metas(tmp_path)["c0"]["desc"] = "edited"
    assert RO.load_metas(tmp_path)["c0"]["desc"] == "c0"
