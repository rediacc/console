"""ci-trace.py reads the runs of ANY workflow, not only Console CI (worklist #ff7812f9).

After a merge `/pr-merge` step 5 must find the Release to Edge dispatch run for the merged SHA, and the read guard refuses the raw runs list while `--runs` listed Console CI only. A pins-soaked workflow_dispatch run (39902213758, PLAN-pins-command.md T11) was invisible to `--scheduled`, and `--scheduled --workflow pins-soaked --run 39902213758 --wait` dropped `--run` and `--wait` without a word. Every case here drives the real `main()` with the GitHub reads faked: `_fetcher` for the runs listings, `_run_snapshot` for one run, and a recording `wl_schedred` in `sys.modules`.
"""

import importlib.util
import json
import sys
import types

import pytest

from rediacc_ci import paths

TRACE = paths.from_root(".ci", "scripts", "ci", "ci-trace.py")


@pytest.fixture(scope="module")
def ct():
    spec = importlib.util.spec_from_file_location("ci_trace_workflow_runs_under_test", TRACE)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def api_run(run_id, event, created, status="completed", conclusion="success", sha="daab83af"):
    return {
        "id": run_id,
        "run_attempt": 1,
        "status": status,
        "conclusion": conclusion if status == "completed" else None,
        "head_sha": sha + "0" * 32,
        "event": event,
        "created_at": created,
    }


class Fetch:
    """Answers each runs-list path from `by_event` (the `event=` value, "" for the plain read) and records every path asked."""

    def __init__(self, by_event, fail=""):
        self.by_event = by_event
        self.fail = fail
        self.paths = []

    def json(self, path):
        self.paths.append(path)
        if self.fail:
            return None, self.fail
        event = path.split("&event=", 1)[1] if "&event=" in path else ""
        return {"workflow_runs": list(self.by_event.get(event, []))}, ""


@pytest.fixture
def quiet(ct, monkeypatch):
    """No GitHub status note, no transition ledger, no root-cause read, no sleeping."""
    monkeypatch.setattr(ct, "_github_note", lambda *_a, **_k: "")
    monkeypatch.setattr(ct, "_gh_tick", lambda _as_json: None)
    monkeypatch.setattr(ct, "_gh_transitions", lambda *_a, **_k: None)
    monkeypatch.setattr(ct, "_root_cause_lines", lambda _root, _run_id: [])
    monkeypatch.setattr(ct, "POLL_SECONDS", 0)
    monkeypatch.setattr(ct.time, "sleep", lambda _s: None)


def install_fetch(ct, monkeypatch, fetch):
    monkeypatch.setattr(ct, "_fetcher", lambda _root: fetch)
    return fetch


# ---- --runs --workflow ------------------------------------------------------------------

MIXED = {
    "": [api_run(5, "push", "2026-10-23T01:00:00Z")],
    "push": [api_run(5, "push", "2026-10-23T01:00:00Z")],
    "workflow_dispatch": [
        api_run(7, "workflow_dispatch", "2026-10-23T04:45:41Z", status="in_progress"),
        api_run(3, "workflow_dispatch", "2026-10-20T17:19:10Z", sha="1dd72403"),
    ],
    "schedule": [api_run(4, "schedule", "2026-10-22T00:30:00Z", conclusion="failure")],
}


@pytest.mark.parametrize(
    "name", ["Release to Edge", "cd-v2", "cd-v2.yml", ".github/workflows/cd-v2.yml"]
)
def test_runs_workflow_lists_that_workflows_runs_every_event_merged(ct, monkeypatch, capsys, name):
    fetch = install_fetch(ct, monkeypatch, Fetch(MIXED))
    assert ct.main(["--runs", "--ref", "main", "--workflow", name]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "Release to Edge runs on main (newest first):"
    # Newest first, each run once although two reads listed run 5, every event kept.
    assert [ln.split()[0] for ln in out[1:]] == ["7", "5", "4", "3"]
    for needle in ("in_progress", "workflow_dispatch", "daab83af"):
        assert needle in out[1]
    assert "push" in out[2]
    assert "schedule" in out[3]
    assert "failure" in out[3]
    # The workflow's own file, on the bare branch name, read once per RUNS_EVENTS spelling.
    assert len(fetch.paths) == len(ct.RUNS_EVENTS)
    assert all(p.startswith("actions/workflows/cd-v2.yml/runs?branch=main&") for p in fetch.paths)


def test_runs_without_workflow_still_reads_console_ci(ct, monkeypatch, capsys):
    """CONTROL: the Console CI listing is the same verb with the default file."""
    fetch = install_fetch(ct, monkeypatch, Fetch(MIXED))
    assert ct.main(["--runs", "--ref", "main"]) == 0
    assert capsys.readouterr().out.startswith("Console CI runs on main")
    assert all(p.startswith("actions/workflows/ci.yml/runs?") for p in fetch.paths)


def test_runs_workflow_json_rows(ct, monkeypatch, capsys):
    install_fetch(ct, monkeypatch, Fetch(MIXED))
    assert ct.main(["--runs", "--ref", "main", "--workflow", "cd-v2", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["run_id"] for r in rows] == [7, 5, 4, 3]
    assert set(rows[0]) == {
        "run_id",
        "attempt",
        "status",
        "conclusion",
        "sha",
        "event",
        "created_at",
    }


def test_runs_unknown_workflow_rc2_names_the_known_and_reads_nothing(ct, monkeypatch, capsys):
    fetch = install_fetch(ct, monkeypatch, Fetch(MIXED))
    assert ct.main(["--runs", "--ref", "main", "--workflow", "nope"]) == 2
    err = capsys.readouterr().err
    assert "'nope' names no workflow" in err
    assert "cd-v2 (cd-v2.yml, Release to Edge)" in err
    assert "pins-soaked (pins-soaked.yml, Pins Soaked)" in err
    assert fetch.paths == []


def test_runs_workflow_empty_and_unreadable_rc2(ct, monkeypatch, capsys):
    install_fetch(ct, monkeypatch, Fetch({}))
    assert ct.main(["--runs", "--ref", "0930-1", "--workflow", "cd-v2"]) == 2
    assert "no Release to Edge run on branch '0930-1'" in capsys.readouterr().err
    install_fetch(ct, monkeypatch, Fetch({}, fail="HTTP 502"))
    assert ct.main(["--runs", "--ref", "main", "--workflow", "cd-v2"]) == 2
    assert "HTTP 502" in capsys.readouterr().err


# ---- --scheduled [--workflow X] --run N [--wait] ----------------------------------------

SCHED = [
    {
        "stem": "pins-soaked",
        "file": "pins-soaked.yml",
        "name": "Pins Soaked",
        "crons": ["30 0 * * *"],
    },
]


class FakeSchedred(types.ModuleType):
    def __init__(self, runs=None, doc=None):
        super().__init__("wl_schedred")
        self.runs = runs or []
        self.doc = doc
        self.calls = []

    def scheduled_workflows(self, root):
        self.calls.append(("scheduled_workflows", root))
        return [dict(w) for w in SCHED]

    def refresh(self, root, worklist, force=False):
        self.calls.append(("refresh", root, worklist, force))
        return self.doc

    def recent_runs(self, root, stem, limit=5):
        self.calls.append(("recent_runs", root, stem, limit))
        return self.runs, ""


def snapshots(ct, monkeypatch, seq, workflow="Pins Soaked"):
    """`_run_snapshot` answering each read from `seq` in turn (the last one repeats); returns the list of run ids read."""
    seen = []

    def fake(_root, run_id):
        seen.append(run_id)
        status, conclusion, jobs = seq[min(len(seen), len(seq)) - 1]
        return status, conclusion, jobs, workflow

    monkeypatch.setattr(ct, "_run_snapshot", fake)
    return seen


IN_FLIGHT = (
    "in_progress",
    None,
    [{"name": "Report soaked pins", "status": "in_progress", "conclusion": None}],
)
RED = ("completed", "failure", [{"name": "Report soaked pins", "conclusion": "failure"}])
GREEN = ("completed", "success", [{"name": "Report soaked pins", "conclusion": "success"}])


@pytest.mark.usefixtures("quiet")
@pytest.mark.parametrize(
    ("final", "rc", "word"),
    [(RED, 1, "RED  run 39902213758"), (GREEN, 0, "GREEN  run 39902213758")],
)
def test_scheduled_workflow_run_wait_follows_the_run_to_its_verdict(
    ct, monkeypatch, capsys, final, rc, word
):
    fake = FakeSchedred()
    monkeypatch.setitem(sys.modules, "wl_schedred", fake)
    seen = snapshots(ct, monkeypatch, [IN_FLIGHT, IN_FLIGHT, final])
    argv = ["--scheduled", "--workflow", "pins-soaked", "--run", "39902213758", "--wait"]
    assert ct.main(argv) == rc
    out = capsys.readouterr().out
    assert word in out
    # It waited: three reads of THAT run, and the scheduled listing was never read in its place.
    assert seen == ["39902213758"] * 3
    assert [c[0] for c in fake.calls if c[0] != "scheduled_workflows"] == []


@pytest.mark.usefixtures("quiet")
def test_scheduled_run_without_wait_is_no_verdict_while_in_flight(ct, monkeypatch, capsys):
    """CONTROL for the wait: the same run read once is in flight, exit 2, one read."""
    monkeypatch.setitem(sys.modules, "wl_schedred", FakeSchedred())
    seen = snapshots(ct, monkeypatch, [IN_FLIGHT, RED])
    assert ct.main(["--scheduled", "--workflow", "pins-soaked", "--run", "39902213758"]) == 2
    assert "still in_progress" in capsys.readouterr().err
    assert seen == ["39902213758"]


@pytest.mark.usefixtures("quiet")
def test_scheduled_run_of_another_workflow_is_refused(ct, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "wl_schedred", FakeSchedred())
    snapshots(ct, monkeypatch, [GREEN], workflow="Release to Edge")
    assert ct.main(["--scheduled", "--workflow", "pins-soaked", "--run", "39902042581"]) == 2
    assert "is a 'Release to Edge' run, not 'Pins Soaked'" in capsys.readouterr().err


@pytest.mark.usefixtures("quiet")
def test_scheduled_run_without_workflow_judges_any_run(ct, monkeypatch):
    monkeypatch.setitem(sys.modules, "wl_schedred", FakeSchedred())
    snapshots(ct, monkeypatch, [RED], workflow="Release to Edge")
    assert ct.main(["--scheduled", "--run", "39902042581"]) == 1


def test_scheduled_workflow_shows_dispatch_runs_without_counting_them(ct, monkeypatch, capsys):
    green_sched = {
        "stem": "pins-soaked",
        "file": "pins-soaked.yml",
        "name": "Pins Soaked",
        "run_id": 10,
        "attempt": 1,
        "conclusion": "success",
        "created_at": "2026-10-22T00:30:00Z",
        "red": False,
        "in_flight": False,
        "failed_jobs": [],
    }
    monkeypatch.setitem(sys.modules, "wl_schedred", FakeSchedred(runs=[green_sched]))
    fetch = install_fetch(
        ct,
        monkeypatch,
        Fetch(
            {
                "workflow_dispatch": [
                    api_run(
                        39902213758,
                        "workflow_dispatch",
                        "2026-10-23T04:47:00Z",
                        conclusion="failure",
                    )
                ]
            }
        ),
    )
    # A red dispatch beside a green scheduled run: shown, labelled, and the exit code stays the scheduled verdict.
    assert ct.main(["--scheduled", "--workflow", "pins-soaked"]) == 0
    out = capsys.readouterr().out
    assert "workflow_dispatch runs on main (shown, not counted in the exit code):" in out
    assert "RED    run 39902213758 attempt 1  failure @ daab83af  dispatch" in out
    assert "--scheduled --workflow pins-soaked --run 39902213758" in out
    assert fetch.paths == [
        "actions/workflows/pins-soaked.yml/runs?branch=main&per_page=3&event=workflow_dispatch"
    ]


def test_all_workflows_scheduled_verdict_reads_no_dispatch_run(ct, monkeypatch, capsys):
    """The Stop hook shares the all-workflows read: it stays wl_schedred's document alone."""
    doc = {
        "state": "ok",
        "error": "",
        "at": 1.0,
        "workflows": [
            dict(
                SCHED[0],
                run_id=1,
                attempt=1,
                conclusion="success",
                created_at="2026-10-22T00:30:00Z",
                red=False,
                in_flight=False,
            )
        ],
    }
    monkeypatch.setitem(sys.modules, "wl_schedred", FakeSchedred(doc=doc))
    fetch = install_fetch(
        ct,
        monkeypatch,
        Fetch(
            {
                "workflow_dispatch": [
                    api_run(9, "workflow_dispatch", "2026-10-23T00:00:00Z", conclusion="failure")
                ]
            }
        ),
    )
    monkeypatch.setattr(ct.wl_ci.C, "worklist_for", lambda _root: "/nonexistent/wl.md")
    assert ct.main(["--scheduled"]) == 0
    assert "dispatch" not in capsys.readouterr().out
    assert fetch.paths == []


# ---- refused combinations ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "needle"),
    [
        (["--scheduled", "--wait"], "--scheduled --wait needs --run"),
        (["--scheduled", "--workflow", "pins-soaked", "--wait"], "--scheduled --wait needs --run"),
        (["--runs", "--wait"], "--wait does not combine with --runs"),
        (["--why", "--wait", "--run", "1"], "--wait does not combine with --why"),
        (["--run", "1", "--jobs", "--wait"], "--wait does not combine with --jobs"),
        (["--runs", "--run", "1"], "--runs lists a branch's runs"),
        (["--workflow", "cd-v2"], "--workflow needs --scheduled or --runs"),
        (["--scheduled", "--ref", "0930-1"], "--scheduled reads main only"),
        (["--scheduled", "--why"], "--why and --scheduled are separate verbs"),
        (["--until-final"], "--until-final needs --wait"),
        # Review finding 3: every pair of verbs is refused, not only the --scheduled ones.
        (["--runs", "--jobs", "--run", "1"], "--runs and --jobs are separate verbs"),
        (["--why", "--runs"], "--why and --runs are separate verbs"),
        (["--runs", "--history", "Quality / Code"], "--runs and --history are separate verbs"),
        (["--runs", "--watchdog"], "--runs and --watchdog are separate verbs"),
        (["--job", "5", "--history", "x"], "--job and --history are separate verbs"),
        (["--why", "--watchdog", "1"], "--why and --watchdog are separate verbs"),
        # Review finding 4: a --run wait already lasts until the run completes.
        (
            ["--scheduled", "--run", "1", "--wait", "--until-final"],
            "--until-final applies to a branch wait",
        ),
        (["--run", "1", "--wait", "--until-final"], "--until-final applies to a branch wait"),
    ],
)
def test_a_flag_that_would_be_ignored_is_refused(ct, capsys, argv, needle):
    with pytest.raises(SystemExit) as exc:
        ct.main(argv)
    assert exc.value.code == 2
    assert needle in capsys.readouterr().err


def test_a_crash_in_the_run_path_names_the_run_reader(ct, monkeypatch, capsys):
    def boom(*_args, **_kwargs):
        raise RuntimeError("no such run")

    monkeypatch.setattr(ct, "_verb_scheduled_run", boom)
    rc = ct.verb_scheduled(str(paths.repo_root()), "pins-soaked", False, run_id="1")
    err = capsys.readouterr().err
    assert rc == ct.EXIT_NO_VERDICT
    assert "the run reader failed: RuntimeError: no such run" in err
    assert "scheduled-run reader" not in err


@pytest.mark.usefixtures("quiet")
def test_an_unread_workflow_name_is_no_verdict_not_a_match(ct, monkeypatch, capsys):
    """Review finding 1: a run whose workflow name came back empty is not judged as the named workflow's run."""
    monkeypatch.setitem(sys.modules, "wl_schedred", FakeSchedred())
    snapshots(ct, monkeypatch, [GREEN], workflow="")
    assert ct.main(["--scheduled", "--workflow", "pins-soaked", "--run", "39902213758"]) == 2
    assert "the workflow of run 39902213758 could not be read" in capsys.readouterr().err


@pytest.mark.usefixtures("quiet")
def test_an_unread_workflow_name_still_reads_without_workflow(ct, monkeypatch):
    """CONTROL: with no --workflow named there is nothing to match, so the same run is judged."""
    monkeypatch.setitem(sys.modules, "wl_schedred", FakeSchedred())
    snapshots(ct, monkeypatch, [GREEN], workflow="")
    assert ct.main(["--scheduled", "--run", "39902213758"]) == 0


@pytest.mark.usefixtures("quiet")
@pytest.mark.parametrize("name", ["Release to Edge", "cd-v2", "cd-v2.yml"])
def test_scheduled_run_resolves_a_dispatch_only_workflow(ct, monkeypatch, capsys, name):
    """Review finding 2: `--scheduled --workflow X --run N` takes any workflow, so the Release to Edge dispatch is judged."""
    fake = FakeSchedred()
    monkeypatch.setitem(sys.modules, "wl_schedred", fake)
    seen = snapshots(ct, monkeypatch, [GREEN], workflow="Release to Edge")
    assert ct.main(["--scheduled", "--workflow", name, "--run", "39902042581"]) == 0
    assert "GREEN  run 39902042581" in capsys.readouterr().out
    assert seen == ["39902042581"]


@pytest.mark.usefixtures("quiet")
def test_scheduled_run_unknown_workflow_rc2_names_every_workflow(ct, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "wl_schedred", FakeSchedred())
    seen = snapshots(ct, monkeypatch, [GREEN])
    assert ct.main(["--scheduled", "--workflow", "nope", "--run", "1"]) == 2
    err = capsys.readouterr().err
    assert "'nope' names no workflow" in err
    assert "cd-v2 (cd-v2.yml, Release to Edge)" in err
    assert seen == []


def test_a_nameless_workflow_is_named_as_github_names_its_runs(ct, tmp_path, monkeypatch):
    """GitHub names the runs of a workflow with no top-level `name:` by its repository path, so the --run check compares against that, never against an empty name."""
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "named.yml").write_text("name: Named One\non: push\n")
    (wf / "bare.yml").write_text("on: push\njobs: {}\n")
    known = {k["stem"]: k["name"] for k in ct._workflows(str(tmp_path))}
    assert known == {"bare": ".github/workflows/bare.yml", "named": "Named One"}

    seen = {}

    def fake_trace(*_args, expect_workflow=""):
        seen["expect"] = expect_workflow
        return 0

    monkeypatch.setattr(ct, "_trace_run", fake_trace)
    assert ct._verb_scheduled_run(str(tmp_path), "bare", "1", False, 0, False) == 0
    assert seen["expect"] == ".github/workflows/bare.yml"


def test_an_empty_name_value_does_not_capture_the_next_line(ct, tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "empty.yml").write_text("name:\non: push\njobs: {}\n")
    (wf / "spaced.yml").write_text("name:   Spaced Name  \non: push\n")
    known = {k["stem"]: k["name"] for k in ct._workflows(str(tmp_path))}
    assert known == {"empty": ".github/workflows/empty.yml", "spaced": "Spaced Name"}
