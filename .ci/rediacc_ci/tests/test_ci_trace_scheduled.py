"""ci-trace.py --scheduled [--workflow X]: one row per scheduled workflow, and an exit code that says whether main's scheduled runs are green (agent/plans/PLAN-scheduled-red-detector.md, A3).

Console CI nightly was red five nights and Housekeeping four before any agent saw it, because this tracer listed Console CI runs only. The verb reads through `wl_schedred`, the Stop hook's reader, so the two cannot disagree; here that module is replaced in `sys.modules` by a recording fake, so no case touches the network and each one states the exact contract the verb calls (`scheduled_workflows`, `refresh(root, worklist, force=True)`, `recent_runs(root, stem, limit=5)`).
"""

import importlib.util
import json
import sys
import types

import pytest

from rediacc_ci import paths

TRACE = paths.from_root(".ci", "scripts", "ci", "ci-trace.py")
NOW_ISO = "2026-10-04T03:00:00Z"


@pytest.fixture(scope="module")
def ct():
    spec = importlib.util.spec_from_file_location("ci_trace_scheduled_under_test", TRACE)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


WORKFLOWS = [
    {"stem": "ci", "file": "ci.yml", "name": "Console CI", "crons": ["0 2 * * *"]},
    {
        "stem": "housekeeping",
        "file": "housekeeping.yml",
        "name": "Housekeeping",
        "crons": ["0 4 * * *"],
    },
    {"stem": "ci-vm-bake", "file": "ci-vm-bake.yml", "name": "CI VM Bake", "crons": ["0 5 1 * *"]},
]


def row(stem, conclusion, run_id, red, jobs=()):
    base: dict = next(dict(w) for w in WORKFLOWS if w["stem"] == stem)
    base.update(
        run_id=run_id,
        attempt=2,
        conclusion=conclusion,
        created_at=NOW_ISO,
        url="https://example.invalid/%s" % run_id,
        failed_jobs=list(jobs),
        red=red,
        in_flight=False,
    )
    return base


class FakeSchedred(types.ModuleType):
    def __init__(self, result=None, runs=None, runs_err="", boom=None):
        super().__init__("wl_schedred")
        self.result = result
        self.runs = runs or []
        self.runs_err = runs_err
        self.boom = boom
        self.calls = []

    def scheduled_workflows(self, root):
        self.calls.append(("scheduled_workflows", root))
        return [dict(w) for w in WORKFLOWS]

    def refresh(self, root, worklist, force=False):
        self.calls.append(("refresh", root, worklist, force))
        if self.boom:
            raise self.boom
        return self.result

    def recent_runs(self, root, stem, limit=5):
        self.calls.append(("recent_runs", root, stem, limit))
        return self.runs, self.runs_err


@pytest.fixture
def install(ct, monkeypatch, tmp_path):
    # The same wl_core module object ci-trace imports inside the verb, reached through its own sys.path hop.
    wl_core = ct.wl_ci.C
    worklist = tmp_path / "wl.md"
    monkeypatch.setattr(wl_core, "worklist_for", lambda _root: worklist)

    def _install(fake):
        monkeypatch.setitem(sys.modules, "wl_schedred", fake)
        return worklist

    return _install


def ok(*rows):
    return {"state": "ok", "error": "", "at": 1.0, "workflows": list(rows)}


ALL_GREEN = ok(
    row("ci", "success", 11, False),
    row("housekeeping", "success", 12, False),
    row("ci-vm-bake", "success", 13, False),
)
ONE_RED = ok(
    row(
        "ci",
        "failure",
        36974916837,
        True,
        ["Quality / Code", "E2E / a", "E2E / b", "E2E / c", "E2E / d", "E2E / e", "E2E / f"],
    ),
    row("housekeeping", "success", 12, False),
    row("ci-vm-bake", "success", 13, False),
)


def test_all_green_rc0_one_row_per_workflow_and_a_forced_refresh(ct, install, capsys):
    fake = FakeSchedred(ALL_GREEN)
    worklist = install(fake)
    assert ct.main(["--scheduled"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "Scheduled workflows on main: 3, 0 red"
    for name, cron in (
        ("Console CI (ci.yml)", "0 2 * * *"),
        ("Housekeeping", "0 4"),
        ("CI VM Bake", "0 5 1"),
    ):
        assert any(
            name in ln and cron in ln and ln.lstrip().startswith("GREEN") for ln in out.splitlines()
        )
    # THE CACHE WRITE: refresh is forced, against the hooks' own worklist path, so the Stop hook reads what this verb fetched.
    assert ("refresh", ct.REPO_ROOT, worklist, True) in fake.calls


def test_one_red_rc1_names_run_jobs_and_next(ct, install, capsys):
    install(FakeSchedred(ONE_RED))
    assert ct.main(["--scheduled"]) == 1
    out = capsys.readouterr().out
    assert "1 red" in out.splitlines()[0]
    red = [ln for ln in out.splitlines() if ln.lstrip().startswith("RED")]
    assert len(red) == 1
    assert "run 36974916837 attempt 2" in red[0]
    assert "failure" in red[0]
    assert "failed: Quality / Code, E2E / a, E2E / b, E2E / c, E2E / d, E2E / e (+1 more)" in out
    assert "next: .ci/scripts/ci/ci-trace.py --run 36974916837 --why" in out


def test_red_is_read_from_the_row_not_guessed(ct, install):
    """MUTATION CONTROL: the same rows with every red flag cleared exit 0, so rc 1 above comes from the red flag."""
    rows = [dict(w, red=False) for w in ONE_RED["workflows"]]
    install(FakeSchedred(ok(*rows)))
    assert ct.main(["--scheduled"]) == 0


@pytest.mark.parametrize(
    ("result", "needle"),
    [
        ({"state": "unreadable", "error": "HTTP 502", "at": 1.0, "workflows": []}, "HTTP 502"),
        ({"state": "unset", "error": "", "at": 1.0, "workflows": []}, "no GitHub origin"),
        (ok(), "no scheduled workflow"),
        (None, "state None"),
    ],
)
def test_unreadable_unset_and_empty_rc2(ct, install, capsys, result, needle):
    install(FakeSchedred(result))
    assert ct.main(["--scheduled"]) == 2
    assert needle in capsys.readouterr().err


def test_a_reader_that_raises_is_rc2_never_green(ct, install, capsys):
    install(FakeSchedred(boom=RuntimeError("cache corrupt")))
    assert ct.main(["--scheduled"]) == 2
    assert "cache corrupt" in capsys.readouterr().err


def test_json_shape(ct, install, capsys):
    install(FakeSchedred(ONE_RED))
    assert ct.main(["--scheduled", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["state"] == "ok"
    assert [w["stem"] for w in data["workflows"]] == ["ci", "housekeeping", "ci-vm-bake"]
    assert data["workflows"][0]["red"] is True
    assert data["workflows"][0]["failed_jobs"][0] == "Quality / Code"


@pytest.mark.parametrize(
    "name",
    ["housekeeping", "housekeeping.yml", "Housekeeping", ".github/workflows/housekeeping.yml"],
)
def test_workflow_resolves_stem_file_and_name(ct, install, capsys, name):
    runs = [
        row("housekeeping", "failure", 21, True, ["budget-check"]),
        row("housekeeping", "success", 20, False),
    ]
    fake = FakeSchedred(runs=runs)
    install(fake)
    assert ct.main(["--scheduled", "--workflow", name]) == 1
    out = capsys.readouterr().out
    assert ("recent_runs", ct.REPO_ROOT, "housekeeping", 5) in fake.calls
    assert "run 21" in out
    assert "run 20" in out
    assert "failed: budget-check" in out
    assert "next: .ci/scripts/ci/ci-trace.py --run 21 --why" in out


def test_workflow_newest_green_rc0(ct, install):
    install(FakeSchedred(runs=[row("ci", "success", 31, False), row("ci", "failure", 30, True)]))
    assert ct.main(["--scheduled", "--workflow", "ci"]) == 0


def test_workflow_an_in_flight_newest_run_is_not_the_verdict(ct, install, capsys):
    """An in-flight run (conclusion blanked by wl_schedred) neither greens nor reds; the newest completed one decides."""
    flying = dict(row("ci", None, 52, False), in_flight=True)
    install(FakeSchedred(runs=[flying, row("ci", "failure", 51, True)]))
    assert ct.main(["--scheduled", "--workflow", "ci"]) == 1
    out = capsys.readouterr().out
    assert "RUN    run 52" in out
    assert "next: .ci/scripts/ci/ci-trace.py --run 51 --why" in out


def test_workflow_only_in_flight_runs_rc2(ct, install, capsys):
    install(FakeSchedred(runs=[dict(row("ci", None, 52, False), in_flight=True)]))
    assert ct.main(["--scheduled", "--workflow", "ci"]) == 2
    assert "no completed scheduled run" in capsys.readouterr().err


def test_unknown_workflow_rc2_lists_the_known(ct, install, capsys):
    fake = FakeSchedred()
    install(fake)
    assert ct.main(["--scheduled", "--workflow", "nightly-thing"]) == 2
    err = capsys.readouterr().err
    assert "'nightly-thing' is not a scheduled workflow" in err
    for stem in ("ci (ci.yml, Console CI)", "housekeeping", "ci-vm-bake"):
        assert stem in err
    assert not any(c[0] == "recent_runs" for c in fake.calls)


def test_workflow_with_no_runs_or_an_error_rc2(ct, install, capsys):
    install(FakeSchedred(runs=[], runs_err="HTTP 403 rate limited"))
    assert ct.main(["--scheduled", "--workflow", "ci"]) == 2
    assert "rate limited" in capsys.readouterr().err


def test_workflow_json(ct, install, capsys):
    install(FakeSchedred(runs=[row("ci", "failure", 41, True)]))
    assert ct.main(["--scheduled", "--workflow", "ci", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["workflow"]["stem"] == "ci"
    assert data["runs"][0]["run_id"] == 41


def test_workflow_without_scheduled_is_a_usage_error(ct):
    with pytest.raises(SystemExit) as exc:
        ct.main(["--workflow", "ci"])
    assert exc.value.code == 2
