"""wl_gh: the Stop hook's one gh layer (agent/plans/PLAN-ci-consolidation.md, boxes T10 and T13).

The spawn is faked at `subprocess.run`, so every case sees the exact kwargs the real call would get and nothing touches the network. The retry policy is the REAL `rediacc_ci.core.gh_retry`, imported through the same scoped loader the hook uses; only its pause is zeroed.

Every refusal has a control beside it: a case that must fire and one that must not, and the two pins at the bottom (no gh spawn outside wl_gh, wl_gh sealed) each prove their scanner on a planted string before trusting a clean tree.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib
import subprocess

import pytest
from rediacc_ci.quality import worklist_env_registry as R

from rediacc_hooks.tests import wlfix

G = wlfix.import_wl("wl_gh")
STOP_DIR = pathlib.Path(G.__file__).resolve().parent
WL_GH = STOP_DIR / "wl_gh.py"
REPO = STOP_DIR.parents[2]
REGISTRY = REPO / ".ci" / "policy" / "worklist-env-registry.json"


@pytest.fixture(autouse=True)
def _no_retry_pause(monkeypatch):
    monkeypatch.setattr(G, "GH_READ_PAUSE_S", 0)


class FakeRun:
    """Stands in for `subprocess.run`: answers from a script of (rc, stdout, stderr) or exceptions, and records every call's argv and kwargs."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, BaseException):
            raise answer
        rc, out, err = answer
        return subprocess.CompletedProcess(argv, rc, out, err)


@pytest.fixture
def fake(monkeypatch):
    def install(*answers):
        f = FakeRun(*answers)
        monkeypatch.setattr(G.subprocess, "run", f)
        return f

    return install


# ---- T10: call() returns (None, why) on every failure arm, never raises ----


def test_g1_a_good_read_parses_json_and_spawns_gh_once(fake):
    f = fake((0, '{"a": 1}', ""))
    assert G.call(["api", "repos/o/n"], cwd="/tmp") == ({"a": 1}, "")
    assert len(f.calls) == 1
    assert f.calls[0][0] == ["gh", "api", "repos/o/n"]


def test_g2_a_non_zero_exit_is_none_and_the_reason(fake):
    fake((1, "", "gh: Not Found (HTTP 404)"))
    data, err = G.call(["api", "repos/o/n"])
    assert data is None
    assert "exited 1" in err
    assert "HTTP 404" in err


def test_g3_a_timeout_is_none_and_is_not_retried(fake):
    f = fake(subprocess.TimeoutExpired(["gh"], 25))
    data, err = G.call(["api", "x"], timeout=25)
    assert data is None
    assert "timed out" in err
    assert len(f.calls) == 1, (
        "a timeout is not a transient fault, so it must not double the hook's wait"
    )


def test_g4_a_spawn_failure_is_none_and_the_reason(fake):
    fake(FileNotFoundError(2, "No such file or directory", "gh"))
    data, err = G.call(["api", "x"])
    assert data is None
    assert "could not run" in err


def test_g5_non_json_output_is_none(fake):
    fake((0, "<html>rate limited</html>", ""))
    data, err = G.call(["api", "x"])
    assert data is None
    assert err.startswith("non-JSON")


def test_g6_graphql_errors_with_exit_0_are_none(fake):
    fake((0, json.dumps({"errors": [{"message": "Field 'x' doesn't exist"}]}), ""))
    data, err = G.call(["api", "graphql", "-f", "query={x}"])
    assert data is None
    assert "doesn't exist" in err


def test_g6c_control_graphql_errors_beside_a_repository_are_kept(fake):
    doc = {"errors": [{"message": "partial"}], "data": {"repository": {"id": 1}}}
    fake((0, json.dumps(doc), ""))
    assert G.call(["api", "graphql", "-f", "query={x}"]) == (doc, "")


def test_g7_a_runner_that_raises_is_none_never_a_raise():
    def boom(_argv):
        raise RuntimeError("fake exploded")

    data, err = G.call(["api", "x"], run=boom)
    assert data is None
    assert "RuntimeError" in err


def test_g8_an_unimportable_retry_policy_is_blindness_not_a_one_shot_read(monkeypatch, fake):
    f = fake((0, "{}", ""))

    def missing():
        raise ImportError("no .ci here")

    monkeypatch.setattr(G, "gh_retry_module", missing)
    data, err = G.call(["api", "x"])
    assert data is None
    assert "could not be imported" in err
    assert f.calls == [], "a read without the retry policy must not run at all"


# ---- T10: stdin is closed, with its control ----


def _stdin_is_devnull(module) -> tuple[bool, object]:
    seen: dict = {}

    def capture(argv, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, "{}", "")

    real = module.subprocess.run
    module.subprocess.run = capture
    try:
        module.spawn(["api", "x"])
    finally:
        module.subprocess.run = real
    return seen.get("stdin") is subprocess.DEVNULL, seen.get("stdin", "<absent>")


def test_g9_stdin_is_devnull():
    ok, got = _stdin_is_devnull(G)
    assert ok, "spawn passed stdin=%r; a gh that prompts would hang the Stop hook" % (got,)


def test_g9c_control_dropping_stdin_fails_the_same_check(tmp_path):
    src = WL_GH.read_text(encoding="utf-8")
    line = "            stdin=subprocess.DEVNULL,\n"
    assert src.count(line) == 1, "the plant needs exactly one stdin= line to remove"
    mutant = tmp_path / "wl_gh_mutant.py"
    mutant.write_text(src.replace(line, ""), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("wl_gh_mutant", mutant)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ok, got = _stdin_is_devnull(module)
    assert not ok, "the control did not fire: the mutant still closed stdin (%r)" % (got,)


def test_g10_the_spawn_is_bounded_by_the_timeout_it_was_given(fake):
    f = fake((0, "{}", ""))
    G.call(["api", "x"], timeout=7, cwd="/somewhere")
    kwargs = f.calls[0][1]
    assert kwargs["timeout"] == 7
    assert kwargs["cwd"] == "/somewhere"
    assert kwargs["check"] is False


# ---- the bounded transient retry (PLAN-gh-retry G13), folded into call ----


def test_g11_one_502_is_retried_once_after_the_hook_pause(monkeypatch, fake):
    monkeypatch.setattr(G, "GH_READ_PAUSE_S", 2)
    naps: list[float] = []
    f = fake((1, "", "gh: Server Error (HTTP 502)"), (0, '{"ok": true}', ""))
    assert G.call(["api", "x"], sleep=naps.append) == ({"ok": True}, "")
    assert len(f.calls) == 2
    assert naps == [2], "the hook's own bound, not gh_retry's 5 s"


def test_g11c_control_a_404_is_not_retried(fake):
    f = fake((1, "", "gh: Not Found (HTTP 404)"), (0, "{}", ""))
    data, _err = G.call(["api", "x"])
    assert data is None
    assert len(f.calls) == 1


def test_g12_a_persistent_502_is_bounded_to_the_attempts(fake):
    f = fake((1, "", "gh: Server Error (HTTP 502)"))
    data, err = G.call(["api", "x"])
    assert data is None
    assert "HTTP 502" in err
    assert len(f.calls) == G.GH_READ_ATTEMPTS == 2


# ---- call_list ----


def test_g13_call_list_flattens_slurped_pages_and_asks_for_them():
    calls: list[list[str]] = []

    def run(argv):
        calls.append(argv)
        return 0, json.dumps([[{"id": 1}, {"id": 2}], [{"id": 3}], {"id": 4}]), ""

    rows, err = G.call_list(["api", "repos/o/n/issues/1/comments"], run=run)
    assert err == ""
    assert [r["id"] for r in rows] == [1, 2, 3, 4]
    assert calls == [["api", "repos/o/n/issues/1/comments", "--paginate", "--slurp"]]


def test_g13c_control_a_non_list_answer_is_none():
    rows, err = G.call_list(["api", "x"], run=lambda _a: (0, '{"id": 1}', ""))
    assert rows is None
    assert "list of pages" in err


# ---- write: one attempt, and only for a write ----


def test_g14_a_write_is_never_retried():
    calls: list[list[str]] = []

    def run(argv):
        calls.append(argv)
        return 1, "", "gh: Server Error (HTTP 502)"

    rc, _out, err = G.write(
        ["api", "-X", "POST", "repos/o/n/issues/1/comments", "-f", "body=x"], run=run
    )
    assert rc == 1
    assert "502" in err
    assert len(calls) == 1, "a retried POST after a lost response is a second comment"


def test_g15_write_refuses_a_read_and_spawns_nothing():
    calls: list[list[str]] = []

    def run(argv):
        calls.append(argv)
        return 0, "", ""

    rc, _out, err = G.write(["pr", "list"], run=run)
    assert rc == G.RC_REFUSED
    assert "not a write" in err
    assert calls == []


def test_g15c_control_a_graphql_mutation_is_a_write():
    calls: list[list[str]] = []
    argv = ["api", "graphql", "-f", "query=mutation($id:ID!){x(id:$id)}", "-f", "id=T"]

    def run(a):
        calls.append(a)
        return 0, "{}", ""

    rc, _out, _err = G.write(argv, run=run)
    assert rc == 0
    assert calls == [argv]


# ---- the runner budget (wl_checks' review read) ----


def test_g16_a_spent_budget_answers_124_without_spawning(fake):
    f = fake((0, "{}", ""))
    now = [100.0]
    run = G.runner("/r", timeout=20, budget_s=45, clock=lambda: now[0])
    assert run(["api", "x"])[0] == 0
    assert f.calls[-1][1]["timeout"] == 20
    now[0] += 40
    run(["api", "x"])
    assert f.calls[-1][1]["timeout"] == pytest.approx(5), "the last call gets only what is left"
    now[0] += 5
    rc, _out, err = run(["api", "x"])
    assert rc == G.RC_TIMEOUT
    assert "budget" in err
    assert len(f.calls) == 2


# ---- the cache helpers ----


def test_g17_cache_ttl_and_error_ttl(tmp_path):
    ok, bad = tmp_path / "ok.json", tmp_path / "bad.json"
    assert G.cache_write(ok, {"at": 1000.0, "state": "ok", "error": ""})
    assert G.cache_write(bad, {"at": 1000.0, "state": "unreadable", "error": "HTTP 502"})
    assert G.cache_read(ok, ttl=900, error_ttl=300, now=1800.0) is not None
    assert G.cache_read(ok, ttl=900, error_ttl=300, now=1901.0) is None
    assert G.cache_read(bad, ttl=900, error_ttl=300, now=1300.0) is not None
    assert G.cache_read(bad, ttl=900, error_ttl=300, now=1301.0) is None, (
        "an error entry expires on error_ttl"
    )


def test_g17c_a_corrupt_or_absent_cache_is_none(tmp_path):
    p = tmp_path / "c.json"
    assert G.cache_read(p, 900, 300, now=0) is None
    p.write_text("{half", encoding="utf-8")
    assert G.cache_read(p, 900, 300, now=0) is None
    p.write_text("[1, 2]", encoding="utf-8")
    assert G.cache_load(p) is None, "a cache is a JSON object"


def test_g18_an_atomic_write_leaves_no_tmp_file(tmp_path):
    p = tmp_path / "sub" / "c.json"
    assert G.cache_write(p, {"at": 1, "n": [1, 2]})
    assert json.loads(p.read_text(encoding="utf-8")) == {"at": 1, "n": [1, 2]}
    assert sorted(x.name for x in p.parent.iterdir()) == ["c.json"]


def test_g18c_a_failed_write_keeps_the_old_file_and_leaves_no_tmp(tmp_path):
    p = tmp_path / "c.json"
    assert G.cache_write(p, {"at": 1})
    assert G.cache_write(p, {"at": 2, "bad": object()}) is False
    assert json.loads(p.read_text(encoding="utf-8")) == {"at": 1}
    assert sorted(x.name for x in tmp_path.iterdir()) == ["c.json"]


# ---- T13: no gh spawn under .claude/hooks/stop outside wl_gh.py ----

# The calls that take an argv as DATA rather than running it.
_NOT_A_SPAWN = frozenset({"join", "list2cmdline", "quote", "print", "format", "classify"})
_ARGV_KEYWORDS = ("args", "argv", "cmd", "command")

# A spawn that predates wl_gh and is migrated by an edit outside this plan's writer, named here so the pin can land before it. LIVENESS: an entry that no longer matches a spawn fails test_t13b, so the exemption cannot outlive the code it excuses.
PENDING: dict[str, str] = {}


def _is_gh_argv(node: ast.AST) -> bool:
    """A list or tuple literal whose first element is "gh", seen through a leading `timeout [opts] <duration>`."""
    if not isinstance(node, (ast.List, ast.Tuple)):
        return False
    words = [
        e.value if isinstance(e, ast.Constant) and isinstance(e.value, str) else ""
        for e in node.elts
    ]
    if words[:1] == ["timeout"]:
        i = 1
        while i < len(words) and words[i].startswith("-"):
            i += 2 if words[i] in ("-k", "--kill-after", "-s", "--signal") else 1
        words = words[i + 1 :]
    return words[:1] == ["gh"]


def gh_spawns(source: str, rel: str = "<src>") -> list[tuple[int, str]]:
    """[(line, call)] for every call handed a `["gh", ...]` argv, as its first argument or an argv keyword. The callee is deliberately NOT limited to `subprocess.*`: wl_proc.run and wl_common.run spawn too, so only the calls known to take an argv as data are excused."""
    out = []
    for node in ast.walk(ast.parse(source, filename=rel)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in _NOT_A_SPAWN:
            continue
        cands = list(node.args[:1]) + [k.value for k in node.keywords if k.arg in _ARGV_KEYWORDS]
        if any(_is_gh_argv(c) for c in cands):
            out.append((node.lineno, ast.unparse(func)))
    return out


def _hook_modules() -> list[pathlib.Path]:
    # test-*.py scripts are tests, not hook code (the check:ci-gh-retry-reads rule).
    return sorted(p for p in STOP_DIR.glob("*.py") if not p.name.startswith("test-"))


@pytest.mark.parametrize(
    ("source", "fires"),
    [
        ('subprocess.run(["gh", "pr", "list"], check=False)\n', True),
        ('wl_proc.run(["timeout", "-k", "5", "20", "gh", "api", "x"])\n', True),
        ('C.run(args=["gh", "api", "x"])\n', True),
        ('subprocess.Popen(("gh", "run", "watch"))\n', True),
        ('subprocess.run(["git", "status"])\n', False),
        ('subprocess.run(["timeout", "20", "ls"])\n', False),
        ('" ".join(["gh", "api"])\n', False),
    ],
)
def test_t13a_the_scanner_flags_a_planted_spawn_and_only_a_spawn(source, fires):
    assert bool(gh_spawns(source)) is fires, source


def test_t13b_no_hook_module_spawns_gh_outside_wl_gh():
    modules = _hook_modules()
    assert len(modules) >= 40, "the scan sees %d modules under %s; it is not seeing the tree" % (
        len(modules),
        STOP_DIR,
    )
    own = gh_spawns(WL_GH.read_text(encoding="utf-8"), "wl_gh.py")
    assert len(own) == 1, "wl_gh.py should hold exactly one gh spawn (spawn), found %r" % own
    found = {}
    for path in modules:
        if path.name == "wl_gh.py":
            continue
        hits = gh_spawns(path.read_text(encoding="utf-8"), path.name)
        if hits:
            found[path.name] = hits
    stale = sorted(set(PENDING) - set(found))
    assert not stale, (
        "PENDING names %s, which no longer spawns gh: delete its entry here, and its "
        "check:ci-gh-retry-reads ALLOWED entry if one remains" % stale
    )
    new = {name: hits for name, hits in found.items() if name not in PENDING}
    assert not new, (
        "gh is spawned outside .claude/hooks/stop/wl_gh.py: %s. Route the read through "
        "wl_gh.call / wl_gh.call_list (retried, never raises) or the write through wl_gh.write; "
        "do not add it to PENDING" % new
    )
    for name, why in sorted(PENDING.items()):
        print("PENDING %s %s: %s" % (name, found[name], why))


# ---- T13: wl_gh is sealed ----


def test_t13c_wl_gh_is_sealed_and_its_bounds_are_literals():
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entry = reg["sealed_modules"].get(".claude/hooks/stop/wl_gh.py")
    assert entry, "wl_gh.py is not in %s sealed_modules" % REGISTRY
    pins = entry.get("literals") or {}
    assert pins == {"GH_READ_ATTEMPTS": 2, "GH_READ_PAUSE_S": 2, "DEFAULT_TIMEOUT_S": 25}
    assert R.scan_env_any('import os\nx = os.environ.get("A")\n'), (
        "control: the scanner must see a planted read"
    )
    assert R.scan_env_any(WL_GH.read_text(encoding="utf-8"), "wl_gh.py") == []
