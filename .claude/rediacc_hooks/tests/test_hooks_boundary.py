"""The process boundary the in-process guard suites stand on (agent/plans/PLAN-ciquick-cpu.md W15).

`hookcases.run_guard` and the standalone `guards/test-*.py` suites answer a `python3 dispatch.py <stem>` case through `guards/_harness.run`, in the test process. That is only the same thing as a child if the dispatcher entry point, the interpreter start and the chain runner say the same as the call. This module is the place those are still run for real, and nowhere else needs to:

  * ONE REAL `dispatch.py <stem>` RUN PER GUARD, compared byte for byte (exit code, stdout, stderr) with `_harness.run_inprocess` on the same payload. The payload is one of the guard's own `hookcases.STATIC` cases, a refusal where it has one, so the run also has an expected exit code; a guard with no static case is fed its first `EDGE_CASES` entry. The three process-table readers never run in process (`_harness.PROCESS_STEMS`), so for them the real run is held to its static case's expected code instead.
  * ONE DENY AND ONE ALLOW PER CHAIN through a real `dispatch.py --chain <chain>`, compared byte for byte with `dispatch.run_chain` called in this process inside `_harness.child_world`.

Both are anti-vacuous by count: every stem `guards.stems()` names is compared or held, every chain that has guards finds both verdicts, and a control proves the byte comparison reports a planted divergence.
"""

import importlib
import importlib.util
import os
import shutil
import subprocess
import sys
import types

import pytest

from rediacc_hooks import dispatch, guards
from rediacc_hooks.guards import _harness
from rediacc_hooks.tests import hookcases

TIMEOUT_S = hookcases.GUARD_TIMEOUT_S

# The event shape a bare-string EDGE_CASES entry is built into, per chain (test_guards_differential.py CHAIN_BUILDER).
CHAIN_BUILDER = {
    "pre-bash": hookcases.bash_json,
    "post-bash": hookcases.bash_json,
    "pre-edit": hookcases.edit_json,
    "pre-ask": hookcases.ask_json,
    "pre-agent": lambda prompt: hookcases._j({"tool_input": {"prompt": prompt}}),
}

# Neutral payloads every chain should let through, tried after the static allows when choosing a chain's ALLOW witness.
NEUTRAL = {
    "pre-bash": ["ls", "true"],
    "post-bash": ["ls"],
    "pre-edit": ["x = 1"],
    "pre-ask": ["Which colour?"],
    "pre-agent": ["Read README.md and summarise it."],
}


def static_cases(stem):
    return [k for k in hookcases.STATIC if k.key == "guards/%s.py" % stem]


def edge_payload(module):
    builder = CHAIN_BUILDER[module.CHAIN]
    for entry in getattr(module, "EDGE_CASES", []):
        spec = entry[1] if isinstance(entry, (tuple, list)) else entry
        return hookcases._j(spec) if isinstance(spec, dict) else builder(spec)
    return builder("true")


def witness(stem):
    """`(payload, expected rc or None)`: a static refusal, else any static case, else the first edge case."""
    cases = static_cases(stem)
    deny = [k for k in cases if k.expected != 0]
    for kase in deny + cases:
        return hookcases.today_filled(kase.payload), kase.expected
    return edge_payload(guards.load(stem)), None


def process_run(argv_tail, payload):
    done = subprocess.run(
        [sys.executable, str(_harness.DISPATCH), *argv_tail],
        input=payload.encode(),
        capture_output=True,
        timeout=TIMEOUT_S,
        check=False,
    )
    return (
        done.returncode,
        done.stdout.decode("utf-8", "replace"),
        done.stderr.decode("utf-8", "replace"),
    )


@pytest.fixture
def fresh_tmp(tmp_path, monkeypatch):
    """One TMPDIR for both legs of a comparison, emptied before each leg: call the returned function before a run.

    WHY. A guard's state under TMPDIR is shared and mutable: block_plan_concurrency folds `$TMPDIR/claude-worklist/<slug>.md` and APPENDS a row to `<slug>.spawnclaims` on every spawn it admits. Under the inherited TMPDIR the in-process leg saw the real leg's claim (and claims other xdist workers had written in the last 180 s), so the two legs printed different lines whenever no lease was visible (ci:quick 2026-11-23), and every run planted fixture claims into the live claims file that real spawns are judged against. The SAME path for both legs keeps a guard that names its temp directory byte-identical; emptying it between legs keeps one leg's writes out of the other's answer.
    """
    root = tmp_path / "tmp"
    monkeypatch.setenv("TMPDIR", str(root))
    # A SEEABLE ROSTER. block_plan_concurrency counts live writers from `<config dir>/projects/<munged root>` and judges nothing ("ALLOWED unchecked") when that directory is absent and no sibling claim is on disk. On a developer machine it exists; in the ci:quick clone under ~/.cache it does not, so the refusal witness chosen in process (which left a claim behind) was allowed by the real run after `reset` emptied the claims (ci:quick 2026-11-26, pre-agent). A project directory of this test's own makes both legs judge the same way everywhere.
    stop_dir = str(_harness.DISPATCH.parents[2] / "hooks" / "stop")
    sys.path.insert(0, stop_dir)
    try:
        wl_core = importlib.import_module("wl_core")
        wl_report = importlib.import_module("wl_report")

        fixture_cwd = "/nonexistent-plan-concurrency-fixture"
        munged = wl_report._munged(
            wl_core.project_root(wl_core.project_start({"cwd": fixture_cwd}))
        )
    finally:
        sys.path.remove(stop_dir)
    config = tmp_path / "claude"
    (config / "projects" / munged).mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))

    def reset():
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        return root

    reset()
    return reset


def chain_inprocess(chain, payload):
    """`dispatch.run_chain` in this process, inside the child's world and on fresh guard modules, as a `dispatch.py --chain` child would run it."""
    stems = [module.__name__.rsplit(".", 1)[-1] for module in guards.by_chain(chain)]
    with _harness.child_world(None, None, payload), _harness.fresh_guards(stems):
        return dispatch.run_chain(chain, payload)


def stub_guard(run):
    """A stand-in module for `guards.load` to hand `dispatch.run_one`: the only way to plant a behaviour in a call that builds its own fresh module."""
    return types.SimpleNamespace(run=run)


def divergence(label, want, got):
    """None when the two `(rc, stdout, stderr)` triples are identical, else a message naming every field that differs."""
    lines = []
    for name, a, b in zip(("rc", "stdout", "stderr")[: len(want)], want, got, strict=True):
        if a != b:
            lines.append("  %s\n    process    %r\n    in-process %r" % (name, a, b))
    return (
        ("%s: the in-process answer differs from the real process\n" % label + "\n".join(lines))
        if lines
        else None
    )


STEMS = guards.stems()

# A guard declaring a wall-clock budget (`DEADLINE_S`) says on stderr whether its slow half fit inside it, so its stderr measures the machine's load, not the boundary: a cold child spends the budget importing what this process already holds (warn_writer_brief, measured 2026-11-23 under 8 workers: the child printed "no time left for gen-docs", the call did not). For these the exit code and stdout are compared and stderr is not. Derived from the modules, so the set is named by the code and shrinks when a budget goes.
TIMED_STEMS = frozenset(stem for stem in STEMS if hasattr(guards.load(stem), "DEADLINE_S"))
LIVE_CHAINS = [chain for chain in guards.CHAINS if guards.by_chain(chain)]


def test_every_guard_and_chain_is_in_the_boundary_set():
    assert len(STEMS) >= 40, (
        "only %d guard stem(s); the registry is not seeing the guards directory" % len(STEMS)
    )
    assert LIVE_CHAINS, (
        "no chain has a guard, so the chain half of this module would compare nothing"
    )
    assert len(TIMED_STEMS) <= 4, "stderr is skipped for %d budgeted guards: %s" % (
        len(TIMED_STEMS),
        sorted(TIMED_STEMS),
    )
    held = _harness.PROCESS_STEMS - set(STEMS)
    assert not held, "PROCESS_STEMS names stems that are not guards: %s" % sorted(held)


@pytest.mark.parametrize("stem", STEMS)
def test_one_real_dispatch_run_per_guard(stem, fresh_tmp):
    payload, expected = witness(stem)
    fresh_tmp()
    real = process_run([stem], payload)
    if stem in _harness.PROCESS_STEMS:
        assert expected is not None, (
            "%s reads the process table and has no static case to hold its real run to" % stem
        )
        assert real[0] == expected, (
            "%s: real dispatch exited %d, its static case expects %d\n%s"
            % (stem, real[0], expected, real[2])
        )
        return
    if expected is not None:
        assert real[0] == expected, (
            "%s: real dispatch exited %d, its static case expects %d\n%s"
            % (stem, real[0], expected, real[2])
        )
    fresh_tmp()
    got = _harness.run_inprocess(stem, payload, timeout=TIMEOUT_S)
    if stem in TIMED_STEMS:
        real, got = real[:2], got[:2]
    problem = divergence(stem, real, got)
    assert problem is None, problem


def chain_witnesses(chain):
    """`(deny payload, allow payload)` for `chain`, chosen in process; either may be None.

    Deny candidates are the chain members' static refusals, then their `EDGE_CASES` (the pre-agent guards have no static case at all). Allow candidates lead with the neutral payloads, which return before any guard does real work, then the same pool.
    """
    modules = guards.by_chain(chain)
    members = {module.__name__.rsplit(".", 1)[-1] for module in modules}
    builder = CHAIN_BUILDER[chain]
    static = [
        k
        for k in hookcases.STATIC
        if k.verb == "check" and k.key[len("guards/") : -len(".py")] in members
    ]
    edges = []
    for module in modules:
        for entry in getattr(module, "EDGE_CASES", []):
            spec = entry[1] if isinstance(entry, (tuple, list)) else entry
            edges.append(hookcases._j(spec) if isinstance(spec, dict) else builder(spec))
    pool = [hookcases.today_filled(k.payload) for k in static if k.expected == 2] + edges
    neutral = [builder(text) for text in NEUTRAL[chain]]
    deny = next((p for p in pool if chain_inprocess(chain, p)[0] == 2), None)
    allow = next((p for p in neutral + pool if chain_inprocess(chain, p)[0] == 0), None)
    return deny, allow


@pytest.mark.parametrize("chain", LIVE_CHAINS)
def test_a_chain_denies_and_allows_the_same_in_and_out_of_process(chain, fresh_tmp):
    deny, allow = chain_witnesses(chain)
    assert deny is not None, (
        "chain %s: no static case or neutral payload is refused by the chain; nothing to compare"
        % chain
    )
    assert allow is not None, (
        "chain %s: no static case or neutral payload passes the chain; nothing to compare" % chain
    )
    for verdict, payload, want_rc in (("deny", deny, 2), ("allow", allow, 0)):
        fresh_tmp()
        real = process_run(["--chain", chain], payload)
        assert real[0] == want_rc, "chain %s %s witness: real run exited %d\n%s" % (
            chain,
            verdict,
            real[0],
            real[2],
        )
        fresh_tmp()
        problem = divergence(
            "chain %s %s" % (chain, verdict), real, chain_inprocess(chain, payload)
        )
        assert problem is None, problem


def test_control_a_planted_divergence_is_reported(monkeypatch):
    """CONTROL. A byte comparison that cannot fail proves nothing: a guard whose in-process `run` is swapped for one that allows everything must be reported against its real run, on the rc field."""
    stem = "block_git_amend"
    payload, expected = witness(stem)
    assert expected == 2, "control setup: %s's witness is not a refusal" % stem
    real = process_run([stem], payload)
    monkeypatch.setattr(guards, "load", lambda _stem: stub_guard(lambda _event: 0))
    problem = divergence(stem, real, _harness.run_inprocess(stem, payload))
    assert problem is not None, "CONTROL FAILED: an allow-everything plant was not reported"
    assert "  rc\n" in problem, (
        "CONTROL FAILED: the plant was reported on the wrong field:\n%s" % problem
    )


def test_control_the_dispatcher_argv_is_the_only_one_answered_in_process():
    """CONTROL. `_harness.run` must hand anything that is not `<python> dispatch.py <stem>` to a real process, and must refuse the process-table readers."""
    dispatch_path = str(_harness.DISPATCH)
    assert (
        _harness.dispatch_stem([sys.executable, dispatch_path, "block_git_amend"])
        == "block_git_amend"
    )
    assert (
        _harness.dispatch_stem(["python3", dispatch_path, "block_git_amend"]) == "block_git_amend"
    )
    for argv in (
        [sys.executable, dispatch_path, "--chain", "pre-bash"],
        [sys.executable, dispatch_path, "--list"],
        [sys.executable, dispatch_path, "block_no_such_guard"],
        ["bash", dispatch_path, "block_git_amend"],
        [sys.executable, dispatch_path + ".bak", "block_git_amend"],
        [sys.executable, dispatch_path, "block_self_matching_pgrep"],
    ):
        assert _harness.dispatch_stem(argv) is None, "answered in process: %r" % (argv,)


def test_control_a_seam_patched_on_the_callers_module_does_not_reach_the_call():
    """CONTROL, the regression test-block_second_open_pr.py found: a suite patches a seam onto the live guard module for its own in-process pass, and a dispatcher child never sees it. The in-process call must not see it either, and the caller's module must still carry it afterwards."""
    stem = "block_git_amend"
    payload, expected = witness(stem)
    module = guards.load(stem)
    saved = module.run
    module.run = lambda _event: 0
    try:
        got = _harness.run_inprocess(stem, payload)
        assert got[0] == expected, "the caller's patched module answered the call (rc %d)" % got[0]
        assert guards.load(stem) is module, "the caller's module object was not put back"
        assert module.run(None) == 0, "the caller's patch was lost"
    finally:
        module.run = saved


def test_control_each_call_imports_the_guard_afresh(monkeypatch):
    """CONTROL. Module-body state is the call's own: an environment variable read at import (as block_review_file_shell_write and others do) is read under the call's environment, not the one the module was first imported under."""
    stem = "block_git_amend"
    seen = []
    real_find = importlib.util.find_spec

    def counting(name, *args, **kwargs):
        if name.endswith("." + stem):
            seen.append(os.environ.get("W15_PROBE"))
        return real_find(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", counting)
    _harness.run_inprocess(stem, hookcases.bash_json("ls"), env=dict(os.environ, W15_PROBE="one"))
    _harness.run_inprocess(stem, hookcases.bash_json("ls"), env=dict(os.environ, W15_PROBE="two"))
    assert seen == ["one", "two"], (
        "the guard was not imported afresh inside each call's world: %r" % seen
    )


def test_control_in_process_exit_and_crash_are_loud(monkeypatch):
    """CONTROL. A guard that calls sys.exit(3) is exit 3, as a child would be, and a guard that raises reaches the caller rather than reading as any exit code (a child exits 1; neither is a pass). The runner's world is restored after the raise."""

    def boom(_event):
        raise RuntimeError("planted crash")

    monkeypatch.setattr(guards, "load", lambda _stem: stub_guard(boom))
    before = (os.getcwd(), sys.stdout, sys.stderr, sys.stdin)
    with pytest.raises(RuntimeError, match="planted crash"):
        _harness.run_inprocess("block_git_amend", hookcases.bash_json("ls"), cwd="/")
    assert (os.getcwd(), sys.stdout, sys.stderr, sys.stdin) == before, (
        "the raise left the guard's world in place"
    )

    def leave(_event):
        sys.exit(3)

    monkeypatch.setattr(guards, "load", lambda _stem: stub_guard(leave))
    assert _harness.run_inprocess("block_git_amend", hookcases.bash_json("ls"))[0] == 3


def test_control_the_child_world_is_restored(tmp_path):
    """CONTROL. The environment, cwd and streams a call swapped in are the runner's own again afterwards."""
    before = (dict(os.environ), os.getcwd(), sys.stdout, sys.stderr)
    _harness.run_inprocess(
        "block_git_amend",
        hookcases.bash_json("ls"),
        env={"PATH": "/usr/bin:/bin", "TZ": "Asia/Tokyo"},
        cwd=str(tmp_path),
    )
    assert (dict(os.environ), os.getcwd(), sys.stdout, sys.stderr) == before
