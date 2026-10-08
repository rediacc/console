"""`rediacc_ci.core.jsonl_append` and `rediacc_ci.ci.gate_ledger` (PLAN-gate-scheduling-learned T2, T3).

Every assertion that something holds is paired with a CONTROL showing the same harness goes red when the property is removed: an appender without the lock interleaves, an append without the heal merges a torn fragment into the next line, a path-less gate keyed on filesHash collapses three different trees into one key. A control that does not fire is a claim about the harness before it is a claim about the code.

NO NETWORK and NO REAL LEDGER: every ledger lives under `tmp_path`, `fold_ci` is driven through its injectable `fetch_runs`/`fetch_jobs`, and the only real-tree reads are the lock and the workflows, read-only.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import pathlib
import sys
import threading
import time
from typing import Any

import pytest

from rediacc_ci import gitx, paths
from rediacc_ci.ci import gate_ledger as L
from rediacc_ci.core import jsonl_append

CLEAN = hashlib.sha256(b"").hexdigest()[:16]
GLOBALS = ["**/package-lock.json", "scripts/ci-runner/**"]


# ---------------------------------------------------------------------------- T2: the lifted appender


def _locked_writer(path: str, tag: str, n: int, width: int) -> None:
    for i in range(n):
        jsonl_append.append_lines(path, path + ".lock", [{"w": tag, "i": i, "pad": "x" * width}])


def _naive_writer(path: str, tag: str, n: int, width: int) -> None:
    """THE CONTROL: no lock and the line written in small pieces, the shape a hand-rolled appender takes."""
    for i in range(n):
        line = (json.dumps({"w": tag, "i": i, "pad": "x" * width}) + "\n").encode()
        for k in range(0, len(line), 64):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            os.write(fd, line[k : k + 64])
            os.close(fd)
            time.sleep(0)


def _race(target: Any, path: pathlib.Path, n: int = 150, width: int = 2000) -> list[str]:
    ctx = multiprocessing.get_context("fork")
    procs = [ctx.Process(target=target, args=(str(path), tag, n, width)) for tag in ("a", "b", "c")]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    return path.read_text(encoding="utf-8").splitlines()


def _intact(lines: list[str]) -> int:
    good = 0
    for ln in lines:
        try:
            json.loads(ln)
            good += 1
        except ValueError:
            pass
    return good


@pytest.mark.skipif(sys.platform != "linux", reason="fork-based race harness")
def test_concurrent_appenders_keep_every_line_intact(tmp_path: pathlib.Path) -> None:
    lines = _race(_locked_writer, tmp_path / "locked.jsonl")
    assert len(lines) == 450
    assert _intact(lines) == 450


@pytest.mark.skipif(sys.platform != "linux", reason="fork-based race harness")
def test_control_an_unlocked_piecewise_appender_interleaves(tmp_path: pathlib.Path) -> None:
    lines = _race(_naive_writer, tmp_path / "naive.jsonl")
    assert _intact(lines) < 450, "the control did not interleave; the race harness proves nothing"


def test_append_takes_the_exclusive_lock(tmp_path: pathlib.Path) -> None:
    calls: list[int] = []
    jsonl_append.append_lines(
        tmp_path / "x.jsonl", tmp_path / "x.lock", [{"a": 1}], lock=lambda _h, f: calls.append(f)
    )
    assert calls == [jsonl_append.LOCK_EX]


def test_append_lines_loops_over_partial_writes(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`os.write` may take fewer bytes than offered; the rest of the line must still land, and the return is the total. The fake writes at most 7 bytes a call."""
    real = os.write
    calls: list[int] = []

    def chunked(fd: int, data: Any) -> int:
        n = real(fd, bytes(data)[:7])
        calls.append(n)
        return n

    monkeypatch.setattr(os, "write", chunked)
    path = tmp_path / "x.jsonl"
    payloads = [{"k": "v" * 40}, {"k": 2}]
    got = jsonl_append.append_lines(path, str(path) + ".lock", payloads)
    expect = jsonl_append.encode(payloads)
    assert path.read_bytes() == expect
    assert got == len(expect) == sum(calls)
    assert len(calls) > 1


def test_torn_tail_is_healed(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_bytes(b'{"ok":1}\n{"torn":')
    jsonl_append.append_lines(p, tmp_path / "t.lock", [{"a": 1}, {"b": 2}])
    lines = p.read_text().splitlines()
    assert lines == ['{"ok":1}', '{"torn":', '{"a":1}', '{"b":2}']


def test_control_without_the_heal_the_next_line_is_lost(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_bytes(b'{"ok":1}\n{"torn":')
    with p.open("ab") as fh:
        fh.write(jsonl_append.encode([{"a": 1}, {"b": 2}]))
    lines = p.read_text().splitlines()
    assert _intact(lines) == 2, "a merged fragment must swallow the first appended row"
    assert '{"a":1}' not in lines


def test_wl_store_appends_through_the_lifted_helper(tmp_path: pathlib.Path) -> None:
    paths.on_sys_path(paths.hooks_stop_dir())
    import wl_store  # noqa: PLC0415 -- the hook module, on its own path

    p = tmp_path / "e.jsonl"
    p.write_bytes(b"{")
    wl_store._append_lines(str(p), str(tmp_path / "e.lock"), [{"ev": 1}])
    assert p.read_text() == '{\n{"ev":1}\n'
    mod = wl_store._jsonl_append()
    assert pathlib.Path(mod.__file__).resolve() == pathlib.Path(jsonl_append.__file__).resolve()
    import ast  # noqa: PLC0415

    tree = ast.parse(pathlib.Path(wl_store.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_append_lines")
    os_calls = {
        n.func.attr
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "os"
    }
    assert not os_calls, (
        "wl_store must not keep a second copy of the append: it calls os.%s" % sorted(os_calls)
    )


# ---------------------------------------------------------------------------- location


def test_ledger_dir_rules(tmp_path: pathlib.Path) -> None:
    assert L.ledger_dir({L.LEDGER_ENV: str(tmp_path / "x"), "CI": "true"}) == tmp_path / "x"
    assert L.ledger_dir({"CI": "true"}) is None
    d = L.ledger_dir({"XDG_STATE_HOME": str(tmp_path / "st")})
    assert d is not None
    assert d.parent == tmp_path / "st" / L.LEDGER_SUBDIR
    assert d.name == L.origin_slug()


def test_origin_slug_is_owner_and_repo(tmp_path: pathlib.Path) -> None:
    assert gitx.git(["init", "-q", str(tmp_path)]).returncode == 0
    assert (
        gitx.git(
            ["remote", "add", "origin", "https://github.com/acme/widget.git"], root=tmp_path
        ).returncode
        == 0
    )
    assert L.origin_slug(tmp_path) == "acme-widget"


# ---------------------------------------------------------------------------- receipts


def _entry(
    verdict: str,
    *,
    files: str = "f0",
    own: list[str] | None = None,
    ih: str | None = None,
    carried: str | None = None,
) -> dict[str, Any]:
    return {
        "inputHash": ih,
        "defHash": "d0",
        "filesHash": files,
        "inputs": {"globs": [*(own or []), *GLOBALS], "files": [], "scripts": []},
        "verdict": verdict,
        "carriedFrom": carried,
    }


def _receipt(
    tree: str,
    fin: str,
    gates: dict[str, Any],
    *,
    dirty: str = CLEAN,
    root: str = "/r",
    findings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": 2,
        "saltHash": "salt",
        "gates": gates,
        "headTree": tree,
        "head": "h" + tree,
        "branch": "b1",
        "dirtyDigest": dirty,
        "whole": True,
        "exitCode": 1,
        "findings": findings or {},
        "wallMs": 100_000,
        "finishedAt": fin,
        "judgedRoot": root,
        "timeline": {g: {"start": 1000, "end": 4000, "ready": 0, "cores": 1} for g in gates},
    }


def _keys(rows: list[dict[str, Any]], gate: str) -> list[tuple[str, str]]:
    return [(r["key"], r["key_kind"]) for r in rows if r.get("t") == "g" and r["gate"] == gate]


def test_input_key_kinds() -> None:
    doc = _receipt(
        "t1",
        "2026-10-08T00:10:00.000Z",
        {
            "x:hashed": _entry("ok", ih="IH"),
            "x:paths": _entry("ok", own=["pkg/**"]),
            "x:pathless": _entry("ok"),
        },
    )
    rows = L.receipt_rows(doc, base_tree=None, changed=None, lock_sha=None)
    assert _keys(rows, "x:hashed") == [("IH", "input")]
    assert _keys(rows, "x:paths")[0][1] == "paths"
    assert _keys(rows, "x:pathless") == [("t1", "tree")]
    dirty = L.receipt_rows(
        _receipt("t1", "2026-10-08T00:10:00.000Z", {"x:pathless": _entry("ok")}, dirty="abcd"),
        base_tree=None,
        changed=None,
        lock_sha=None,
    )
    assert _keys(dirty, "x:pathless")[0][1] == "tree+dirty"


def test_pathless_gate_is_keyed_on_the_tree_not_on_files_hash() -> None:
    """The 10-08 shape: green, red, green with ONE filesHash, because the fix sat outside the gate's globs. Keyed on filesHash the three runs share a key and the red reads as flaky; keyed on the tree they do not."""
    docs = [
        _receipt(t, "2026-10-08T0%d:00:00.000Z" % i, {"x:pathless": _entry(v, files="SAME")})
        for i, (t, v) in enumerate([("t1", "ok"), ("t2", "fail"), ("t3", "ok")])
    ]
    keys = [
        _keys(L.receipt_rows(d, base_tree=None, changed=None, lock_sha=None), "x:pathless")[0][0]
        for d in docs
    ]
    assert len(set(keys)) == 3
    control = {d["gates"]["x:pathless"]["filesHash"] for d in docs}
    assert len(control) == 1, "the control: filesHash alone cannot tell the three runs apart"


def test_receipt_rows_shape() -> None:
    doc = _receipt(
        "t1",
        "2026-10-08T00:10:00.000Z",
        {
            "x:a": _entry("fail"),
            "x:carried": _entry("ok", carried="t0"),
            "x:deferred": _entry("deferred"),
            "x:odd": _entry("mystery"),
        },
        findings={"x:a": ["k:1"]},
    )
    rows = L.receipt_rows(doc, base_tree="t0", changed=["a/b.py"], lock_sha="L")
    run, *gs, end = rows
    assert run["t"] == "run"
    assert run["at"] == "2026-10-08T00:08:20.000Z"
    assert run["src"] == "backfill"
    assert run["changed"] == ["a/b.py"]
    assert run["base_tree"] == "t0"
    assert run["whole"] is True
    by = {g["gate"]: g for g in gs}
    assert "x:carried" not in by
    assert "x:odd" not in by
    assert by["x:a"]["outcome"] == "fail"
    assert by["x:a"]["findings"] == ["k:1"]
    assert by["x:a"]["wall_ms"] == 3000
    assert by["x:a"]["t0_ms"] == 1000
    assert by["x:deferred"]["outcome"] == "skip"
    assert end["t"] == "end"
    assert end["wall_ms"] == 100_000
    assert all(L.validate(r) is None for r in rows)


def _plant_root(root: pathlib.Path, docs: list[dict[str, Any]]) -> None:
    rd = root.joinpath(*L.RECEIPTS_REL)
    rd.mkdir(parents=True)
    for d in docs:
        (rd / ("%s.json" % d["headTree"])).write_text(json.dumps(d))


def test_backfill_finds_judged_roots_and_is_idempotent(tmp_path: pathlib.Path) -> None:
    other = tmp_path / "pushclone"
    main = tmp_path / "main"
    _plant_root(
        main, [_receipt("t1", "2026-10-08T00:10:00.000Z", {"x:a": _entry("ok")}, root=str(other))]
    )
    _plant_root(
        other,
        [_receipt("t2", "2026-10-08T01:10:00.000Z", {"x:a": _entry("fail")}, root=str(other))],
    )
    led = tmp_path / "ledger"
    out: list[str] = []
    assert L.backfill(led, main, [], out=out.append) == 0
    rows, bad = L.read_rows(led)
    assert bad == 0
    assert sum(1 for r in rows if r["t"] == "run") == 2, (
        "the push clone named by judgedRoot must be searched"
    )
    assert "2 new run(s)" in out[-1]
    assert L.backfill(led, main, [], out=out.append) == 0
    assert "0 new run(s)" in out[-1]
    assert "2 already folded" in out[-1]
    assert len(L.read_rows(led)[0]) == len(rows)


def test_backfill_rows_drop_a_base_tree_git_cannot_diff(tmp_path: pathlib.Path) -> None:
    """A base_tree whose diff is unknown (`changed` None: an object this clone lacks) must not be recorded as if `changed` were relative to it. `tmp_path` is not a git repository, so no diff can be answered; the second receipt's base is dropped, the first never had one."""
    docs = [
        _receipt("t1", "2026-10-08T00:10:00.000Z", {"x:a": _entry("ok")}),
        _receipt("t2", "2026-10-08T01:10:00.000Z", {"x:a": _entry("fail")}),
    ]
    out, counts = L.backfill_rows(docs, tmp_path)
    runs = [rows[0] for _key, rows in out]
    assert [r["base_tree"] for r in runs] == [None, None]
    assert counts["no_diff"] == 2


def test_backfill_with_no_receipts_is_a_failure(tmp_path: pathlib.Path) -> None:
    (tmp_path / "empty").mkdir()
    assert L.backfill(tmp_path / "ledger", tmp_path / "empty", []) == 1


def test_export_keeps_only_gates_that_were_ever_red(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "main"
    _plant_root(
        root,
        [
            _receipt(
                "t%d" % i,
                "2026-10-08T0%d:00:00.000Z" % i,
                {"x:red": _entry("fail" if i == 1 else "ok"), "x:green": _entry("ok")},
            )
            for i in range(3)
        ],
    )
    (root / "scripts" / "ci-runner").mkdir(parents=True)
    (root / L.LOCK_REL).write_text(
        json.dumps(
            [
                {
                    "id": "x:red",
                    "gate": True,
                    "leaves": [],
                    "ci": {"kind": "local-only", "blocker": "long text"},
                }
            ]
        )
    )
    dest = tmp_path / "fx"
    assert L.backfill(None, root, [], export_to=dest, only_reds=True) == 0
    rows = [json.loads(ln) for ln in (dest / "outcomes.jsonl").read_text().splitlines()]
    assert {r["gate"] for r in rows if r["t"] == "g"} == {"x:red"}
    lock = json.loads((dest / "lock.json").read_text())
    assert lock == [{"id": "x:red", "gate": True, "leaves": [], "ci": {"kind": "local-only"}}]


# ---------------------------------------------------------------------------- append / rotate


def _run_row(rid: str, at: str = "2026-10-08T00:00:00.000Z") -> dict[str, Any]:
    return {"t": "run", "v": 1, "id": rid, "src": "quick", "at": at}


def test_append_stream_writes_and_refuses_loudly(tmp_path: pathlib.Path) -> None:
    good = [
        _run_row("r1"),
        {"t": "g", "run": "r1", "gate": "x:a", "outcome": "pass"},
        {"t": "end", "run": "r1"},
    ]
    lines = [
        json.dumps(good[0]),
        json.dumps(good[1:]),
        "not json",
        json.dumps({"t": "g", "run": "r1", "gate": "x:a", "outcome": "green"}),
        "",
    ]
    assert L.append_stream(tmp_path, lines) == 1
    rows, bad = L.read_rows(tmp_path)
    assert rows == good
    assert bad == 0


def test_append_is_off_under_ci_without_the_variable() -> None:
    out: list[str] = []
    assert (
        L.append_stream(L.ledger_dir({"CI": "true"}), [json.dumps(_run_row("r"))], out=out.append)
        == 0
    )
    assert "OFF" in out[0]
    assert "1 line(s) discarded" in out[0]


def test_rows_land_in_the_segment_of_their_run(tmp_path: pathlib.Path) -> None:
    L.append_rows(
        tmp_path,
        [_run_row("old", "2026-07-03T00:00:00.000Z"), {"t": "end", "run": "old"}],
        now=1.8e9,
    )
    assert [p.name for p in L.segments(tmp_path)] == ["outcomes-2026-07.jsonl"]


def test_rotation_drops_expired_and_oversized_segments(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = L.epoch("2026-10-08T00:00:00Z") or 0.0
    for name in (
        "outcomes-2026-05.jsonl",
        "outcomes-2026-06.jsonl",
        "outcomes-2026-09.jsonl",
        "outcomes-2026-10.jsonl",
    ):
        (tmp_path / name).write_text("x" * 100)
    assert L.rotate(tmp_path, now) == ["outcomes-2026-05.jsonl"]
    monkeypatch.setattr(L, "LEDGER_MAX_BYTES", 150)
    assert L.rotate(tmp_path, now) == ["outcomes-2026-06.jsonl", "outcomes-2026-09.jsonl"]
    assert [p.name for p in L.segments(tmp_path)] == ["outcomes-2026-10.jsonl"], (
        "the current month is never dropped"
    )


# ---------------------------------------------------------------------------- CI fold-in


def _job(
    name: str, steps: list[tuple[str, str]], conclusion: str = "success", jid: int = 1
) -> dict[str, Any]:
    return {
        "id": jid,
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "started_at": "2026-10-08T00:00:00Z",
        "completed_at": "2026-10-08T00:10:00Z",
        "steps": [
            {
                "name": n,
                "conclusion": c,
                "started_at": "2026-10-08T00:01:00Z",
                "completed_at": "2026-10-08T00:02:00Z",
            }
            for n, c in steps
        ],
    }


def test_ci_rows_attribution() -> None:
    import re  # noqa: PLC0415

    steps = {
        "x:solo": ("j", "Solo"),
        "x:s1": ("j", "Shared"),
        "x:s2": ("j", "Shared"),
        "x:py": ("j", "Py"),
    }
    tests = {"x:t1": "pkg/tests/test_one.py", "x:t2": "pkg/tests/test_two.py"}
    job = _job(
        "Q / J (2/3)",
        [("Solo", "success"), ("Shared", "failure"), ("Py", "failure")],
        conclusion="failure",
    )
    lines = ["2026-10-08T00:01:30Z ::finding::pytest-fail:pkg.tests.test_one::test_x"]
    rows = L.ci_rows(
        {"id": 9, "run_attempt": 2, "head_sha": "abc", "event": "pull_request", "head_branch": "b"},
        [job],
        steps=steps,
        tests=tests,
        patterns={"j": re.compile(r"Q / J \(\d/3\)")},
        log_lines=lambda _j: lines,
        category_of=lambda _j, _l: "code-likely",
        tree_of=lambda _s: "T",
        pytest_hosts={"x:py"},
        leg_tests=lambda _n: {"pkg/tests/test_one.py"},
    )
    run = rows[0]
    assert run["src"] == "ci-step"
    assert run["ci"]["attempt"] == 2
    assert run["ci"]["category"] == "code-likely"
    g = {r["gate"]: r for r in rows if r["t"] == "g"}
    assert g["x:solo"]["attr"] == "own"
    assert g["x:solo"]["outcome"] == "pass"
    assert g["x:s1"]["attr"] == "shared-step"
    assert g["x:s1"]["outcome"] == "fail"
    assert g["x:t1"]["attr"] == "test"
    assert g["x:t1"]["outcome"] == "fail"
    assert "x:t2" not in g, "a leg that does not collect a test file must not judge it green"
    assert g["x:py"]["findings"] == ["pytest-fail:pkg.tests.test_one::test_x"]
    assert all(L.validate(r) is None for r in rows)


def test_fold_ci_is_idempotent_and_unknown_is_a_failure(tmp_path: pathlib.Path) -> None:
    import re  # noqa: PLC0415

    from rediacc_ci.ci import budget_report  # noqa: PLC0415

    root = paths.repo_root()
    patterns = budget_report.lane_display_patterns(root)
    picked = None
    for gid, (job_id, step) in sorted(L.lock_ci(root)[0].items()):
        pat = patterns.get(job_id)
        name = re.sub(r"\\(.)", r"\1", pat.pattern[1:-1]) if pat else ""
        if pat and pat.fullmatch(name):
            picked = (gid, step, name)
            break
    assert picked, "no lock gate maps to a plainly named CI job; the fixture cannot be built"
    gid, step, name = picked
    runs = [
        {
            "id": 77,
            "run_attempt": 1,
            "head_sha": "0" * 40,
            "event": "push",
            "created_at": "2026-10-08T00:00:00Z",
            "head_branch": "main",
        }
    ]
    jobs = [_job(name, [(step, "success")])]
    out: list[str] = []
    rc = L.fold_ci(
        tmp_path,
        root,
        repo="o/r",
        logs=False,
        fetch_runs=lambda *_a, **_k: runs,
        fetch_jobs=lambda *_a: jobs,
        out=out.append,
    )
    assert rc == 0, out
    rows = L.read_rows(tmp_path)[0]
    assert any(r["t"] == "g" and r["gate"] == gid and r["outcome"] == "pass" for r in rows)
    assert (
        L.fold_ci(
            tmp_path,
            root,
            repo="o/r",
            logs=False,
            fetch_runs=lambda *_a, **_k: runs,
            fetch_jobs=lambda *_a: jobs,
            out=out.append,
        )
        == 0
    )
    assert "1 already folded" in out[-1]

    def boom(*_a: Any, **_k: Any) -> list[dict[str, Any]]:
        raise RuntimeError("HTTP 403 rate limit")

    assert (
        L.fold_ci(
            tmp_path / "x",
            root,
            repo="o/r",
            logs=False,
            fetch_runs=boom,
            fetch_jobs=lambda *_a: jobs,
            out=out.append,
        )
        == 1
    )
    assert "3 UNCHECKED" in out[-1], out[-1]


def _fold_runs(n: int) -> list[dict[str, Any]]:
    return [
        {
            "id": 100 + i,
            "run_attempt": 1,
            "head_sha": "0" * 40,
            "event": "push",
            "created_at": "2026-10-08T00:%02d:00Z" % i,
            "head_branch": "main",
        }
        for i in range(n)
    ]


def test_fold_ci_skips_seen_before_reading_and_caps_to_newest_with_progress(
    tmp_path: pathlib.Path,
) -> None:
    root = paths.repo_root()
    runs = _fold_runs(6)
    L.ensure_dir(tmp_path)
    L.mark_seen(tmp_path, ["ci:100:1", "ci:101:1"])
    read: list[int] = []

    def fetch(_repo: str, run_id: int) -> list[dict[str, Any]]:
        read.append(run_id)
        return []

    out: list[str] = []
    prog: list[str] = []
    rc = L.fold_ci(
        tmp_path,
        root,
        repo="o/r",
        logs=False,
        fetch_runs=lambda *_a, **_k: runs,
        fetch_jobs=fetch,
        out=out.append,
        max_unseen=2,
        workers=2,
        progress=prog.append,
    )
    assert rc == 0, out
    assert sorted(read) == [104, 105], "seen runs and runs beyond the cap are never read"
    assert "2 already folded" in out[-1], out[-1]
    assert "2 older unseen deferred" in out[-1], out[-1]
    assert len([m for m in prog if "folded (" in m]) == 2, prog


def test_fold_ci_deadline_names_the_unread_runs_as_unchecked(tmp_path: pathlib.Path) -> None:
    root = paths.repo_root()
    ticks = iter(range(0, 10_000, 100))
    out: list[str] = []
    prog: list[str] = []
    rc = L.fold_ci(
        tmp_path,
        root,
        repo="o/r",
        logs=False,
        fetch_runs=lambda *_a, **_k: _fold_runs(3),
        fetch_jobs=lambda *_a: [],
        out=out.append,
        deadline_s=50.0,
        workers=1,
        progress=prog.append,
        clock=lambda: float(next(ticks)),
    )
    assert rc == 1, out
    assert "3 UNCHECKED" in out[-1], out[-1]
    assert any("UNCHECKED (deadline)" in m for m in prog), prog


def test_fold_ci_max_unseen_zero_reads_nothing(tmp_path: pathlib.Path) -> None:
    read: list[int] = []
    out: list[str] = []

    def fetch(_repo: str, run_id: int) -> list[dict[str, Any]]:
        read.append(run_id)
        return []

    L.fold_ci(
        tmp_path,
        paths.repo_root(),
        repo="o/r",
        logs=False,
        fetch_runs=lambda *_a, **_k: _fold_runs(3),
        fetch_jobs=fetch,
        out=out.append,
        max_unseen=0,
        workers=1,
        progress=lambda _m: None,
    )
    assert read == [], "--max-unseen 0 must read no run"


def test_max_unseen_refuses_a_negative_value() -> None:
    with pytest.raises(SystemExit):
        L.main(["fold-ci", "--max-unseen", "-1"])


def test_fold_ci_deadline_hits_the_futures_timeout_branch(tmp_path: pathlib.Path) -> None:
    gate = threading.Event()
    main_calls = [0]
    out: list[str] = []
    prog: list[str] = []

    def fetch(*_a: Any) -> list[dict[str, Any]]:
        gate.wait(10)
        return []

    def clock() -> float:
        # the pool worker always sees t=0 (inside the deadline); the main thread sees the deadline pass after its first read
        if threading.current_thread() is not threading.main_thread():
            return 0.0
        main_calls[0] += 1
        return 0.0 if main_calls[0] == 1 else 1000.0

    try:
        rc = L.fold_ci(
            tmp_path,
            paths.repo_root(),
            repo="o/r",
            logs=False,
            fetch_runs=lambda *_a, **_k: _fold_runs(1),
            fetch_jobs=fetch,
            out=out.append,
            deadline_s=50.0,
            workers=1,
            progress=prog.append,
            clock=clock,
        )
    finally:
        gate.set()
    assert rc == 1, out
    assert "UNCHECKED" in out[-1], out[-1]
    assert any("UNCHECKED (deadline)" in m for m in prog), prog


def test_fold_ci_leaves_no_joinable_worker_behind_a_deadline(tmp_path: pathlib.Path) -> None:
    """A worker stuck in a gh call at the deadline must not keep the interpreter alive: non-daemon pool threads are joined at exit."""
    gate = threading.Event()
    before = set(threading.enumerate())
    entered = threading.Event()
    main_calls = [0]

    def fetch(*_a: Any) -> list[dict[str, Any]]:
        entered.set()
        gate.wait(10)
        return []

    def clock() -> float:
        if threading.current_thread() is not threading.main_thread():
            return 0.0
        main_calls[0] += 1
        entered.wait(5)
        return 0.0 if main_calls[0] == 1 else 1000.0

    try:
        L.fold_ci(
            tmp_path,
            paths.repo_root(),
            repo="o/r",
            logs=False,
            fetch_runs=lambda *_a, **_k: _fold_runs(1),
            fetch_jobs=fetch,
            out=lambda _m: None,
            deadline_s=50.0,
            workers=1,
            progress=lambda _m: None,
            clock=clock,
        )
        stuck = [t for t in threading.enumerate() if t not in before and t.is_alive()]
        assert stuck, "the blocked worker should still be running at this point"
        assert all(t.daemon for t in stuck), [t.name for t in stuck if not t.daemon]
    finally:
        gate.set()


def test_finding_keys_reads_the_runner_alphabet_only() -> None:
    lines = [
        "2026Z ::finding::pytest-fail:a.b::c#d#",
        "::finding::bad key with spaces",
        "noise",
        "::finding::pytest-fail:a.b::c#d#",
    ]
    assert L.finding_keys(lines) == ["pytest-fail:a.b::c#d#"]


def test_the_pytest_host_is_derived_from_the_key_emitter() -> None:
    """The step that runs the suites is the one whose leaves include the module printing `pytest-fail:` keys. CONTROL: matching on path coverage instead finds several gates whose globs merely contain the tests directory, and each would judge every test gate from its own unrelated step."""
    from rediacc_ci.ci import gate_model  # noqa: PLC0415

    root = paths.repo_root()
    steps, tests = L.lock_ci(root)
    assert tests, "the lock has no test gates; nothing to attribute"
    hosts = L.pytest_hosts(root, tests, steps)
    assert len(hosts) == 1
    by_coverage = {
        str(e["id"])
        for e in gate_model.load_lock(root)
        if e["id"] in steps
        and e.get("paths")
        and all(any(gate_model.match_glob(g, p) for g in e["paths"]) for p in tests.values())
    }
    assert hosts < by_coverage
