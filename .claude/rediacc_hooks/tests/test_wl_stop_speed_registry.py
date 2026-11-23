"""The Stop battery's registry and per-segment timing, and the CLI split (agent/plans/PLAN-tooling-speed.md D4, box SP3).

Four claims, each with a control:

1. INVENTORY. The `R.start`/`R.begin` marks in run_stop and wl_stopregistry.REGISTRY name the same keys in the same order, read from the source by AST so neither side can drift. Control: a planted extra mark, and a planted missing one, are both reported.
2. TIERS. Each segment's declared tier agrees with the `vadd` calls inside it: `always` exactly when one passes True (or a value the AST cannot read), `rotating` when every one passes False, `advisory` and `setup`/`verdict` when there is none.
3. DURATIONS. A blocked fixture stop writes a blocklog row whose `ms` names every segment it reached, each a whole number of milliseconds; a judge-path block reaches `judge` too. The clock refuses an unregistered key.
4. NO BEHAVIOUR CHANGE. The same fixture stop, run once with the marks and once with them stripped from a copy of wl_checks.py, prints byte-identical stop text.

And the CLI half: `worklist.py --list --open <me>` answers through wl_cli.py, and an unknown verb is still refused there.
"""

from __future__ import annotations

import ast
import json
import re
import shutil

import pytest

from rediacc_hooks.tests import wlfix

R = wlfix.import_wl("wl_stopregistry")
WL_CHECKS = wlfix.STOP_DIR / "wl_checks.py"
MARK_LINE = re.compile(r'(?m)^ +R\.(?:start|begin)\("[a-z-]+"\)\n')


def _run_stop(source: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_stop")


def marks_of(source: str) -> list[tuple[int, str, str]]:
    """(line, method, key) for every R.start / R.begin call in run_stop, in source order."""
    return sorted(
        (node.lineno, node.func.attr, node.args[0].value)
        for node in ast.walk(_run_stop(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "R"
        and node.func.attr in ("start", "begin")
    )


def inventory_problems(source: str) -> list[str]:
    marks = marks_of(source)
    problems = []
    starts = sum(1 for m in marks if m[1] == "start")
    if not marks or marks[0][1] != "start":
        problems.append("run_stop does not open with R.start")
    if starts != 1:
        problems.append("R.start is called %d times" % starts)
    got = [m[2] for m in marks]
    want = [s.key for s in R.REGISTRY]
    if got != want:
        extra = [k for k in got if k not in want]
        missing = [k for k in want if k not in got]
        problems.append("marks and REGISTRY disagree: extra %s, missing %s" % (extra, missing))
    return problems


def derived_tiers(source: str) -> dict[str, str]:
    """{segment: always|rotating|quiet} from the vadd calls inside each segment's `_stop_<key>` function (the lifted body of that segment)."""
    tree = ast.parse(source)
    calls: dict[str, list[object]] = {m[2]: [] for m in marks_of(source)}
    for fn in tree.body:
        if not (isinstance(fn, ast.FunctionDef) and fn.name.startswith("_stop_")):
            continue
        key = fn.name.removeprefix("_stop_").replace("_", "-")
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "vadd"
            ):
                flag = node.args[1] if len(node.args) > 1 else None
                calls[key].append(flag.value if isinstance(flag, ast.Constant) else "unreadable")
    out = {}
    for key, flags in calls.items():
        if any(f is True or f == "unreadable" for f in flags):
            out[key] = "always"
        elif flags:
            out[key] = "rotating"
        else:
            out[key] = "quiet"
    return out


def test_every_segment_is_its_own_function_called_once_in_order():
    """SP3's lift: run_stop calls one `_stop_<key>(ns)` per mark, in registry order, and holds no vadd of its own."""
    source = WL_CHECKS.read_text(encoding="utf-8")
    body = _run_stop(source)
    called = [
        n.func.id
        for n in ast.walk(body)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id.startswith("_stop_")
    ]
    want = ["_stop_" + s.key.replace("-", "_") for s in R.REGISTRY]
    assert called == want
    defined = {n.name for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
    assert set(want) <= defined
    assert not any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "vadd"
        for n in ast.walk(body)
    )


def test_the_marks_and_the_registry_name_the_same_segments_in_order():
    source = WL_CHECKS.read_text(encoding="utf-8")
    assert inventory_problems(source) == []
    assert len(R.REGISTRY) == len(R.KEYS), "a registry key is listed twice"
    assert {s.tier for s in R.REGISTRY} <= set(R.TIERS)


def test_control_an_extra_or_a_missing_mark_is_reported():
    source = WL_CHECKS.read_text(encoding="utf-8")
    extra = source.replace(
        '    R.begin("judge")\n', '    R.begin("judge")\n    R.begin("ghost")\n', 1
    )
    assert extra != source
    assert any("extra ['ghost']" in p for p in inventory_problems(extra))
    missing = source.replace('    R.begin("roster")\n', "", 1)
    assert missing != source
    assert any("missing ['roster']" in p for p in inventory_problems(missing))


def test_each_tier_agrees_with_the_vadd_calls_in_its_segment():
    derived = derived_tiers(WL_CHECKS.read_text(encoding="utf-8"))
    wrong = []
    for seg in R.REGISTRY:
        got = derived[seg.key]
        want = "quiet" if seg.tier in ("setup", "verdict", "advisory") else seg.tier
        if got != want:
            wrong.append("%s declared %s, its vadd calls read %s" % (seg.key, seg.tier, got))
    assert wrong == []


def test_control_a_tier_that_disagrees_is_seen():
    """The rule above is not vacuous: a planted always-tier vadd in an advisory segment changes what it derives."""
    source = WL_CHECKS.read_text(encoding="utf-8")
    planted = source.replace(
        "def _stop_next_plan(ns):\n",
        'def _stop_next_plan(ns):\n    vadd("planted", True, "x")\n',
        1,
    )
    assert derived_tiers(source)["next-plan"] == "quiet"
    assert derived_tiers(planted)["next-plan"] == "always"


def test_the_clock_refuses_an_unregistered_key_and_counts_the_open_segment():
    clock = iter([10.0, 10.25, 10.5, 11.0]).__next__
    R.start("setup", clock=clock)
    R.begin("roster", clock=clock)
    got = R.durations(clock=clock)
    assert got == {"setup": 250, "roster": 250}, got
    with pytest.raises(KeyError):
        R.begin("not-a-segment", clock=clock)
    with pytest.raises(KeyError):
        R.start("not-a-segment", clock=clock)


def _blocklog(fx) -> list[dict]:
    rows = []
    for path in fx.base.rglob("*.blocklog-*.jsonl"):
        rows += [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln]
    return rows


def _static_block_world(fx) -> None:
    fx.brief_now()
    fx.hand_now()
    fx.add_item("- [ ] (deadbeef) open thing")
    fx.say("answer with no report section")


def test_a_static_block_writes_a_duration_for_every_segment_it_reached(wl):
    _static_block_world(wl)
    got = wl.run()
    assert got.decision == "block", got.out[:300]
    rows = _blocklog(wl)
    assert len(rows) == 1, rows
    ms = rows[0]["ms"]
    want = [s.key for s in R.REGISTRY if s.key != "judge"]
    assert list(ms) == want, ms
    assert all(isinstance(v, int) and v >= 0 for v in ms.values()), ms


def test_a_judge_path_block_reaches_the_judge_segment(wl):
    """The judge runs only after a clean static battery; with no `claude` on PATH it fails closed, and that block's row carries `judge`."""
    wl.say("waiting on CI.\n\n## Remaining\n- #7 merge the chain (pending)")
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "merge the chain")
    wl.judge_mode = "on"
    event = json.dumps(
        {
            "session_id": wl.sid,
            "cwd": str(wl.proj),
            "transcript_path": str(wl.transcript),
            "session_crons": wlfix.DEFAULT_CRONS,
        }
    )
    got = wl.run({"PATH": str(wl.base / "binonly"), "HOME": str(wl.base / "nohome")}, event=event)
    assert got.decision == "block", got.out[:300]
    rows = _blocklog(wl)
    assert rows, "the judge-path block wrote no blocklog row"
    assert "judge" in rows[-1]["ms"], rows[-1]


def test_the_marks_change_no_stop_text(tmp_path):
    """The same world, the same hook path, the same base: once with the marks, once with them stripped. Control: the strip removed exactly one line per registry entry, so the two runs really differ in code."""
    hooks = tmp_path / "hooks" / "stop"
    shutil.copytree(wlfix.STOP_DIR, hooks, ignore=shutil.ignore_patterns("__pycache__"))
    source = (hooks / "wl_checks.py").read_text(encoding="utf-8")
    stripped = MARK_LINE.sub("", source)
    assert len(MARK_LINE.findall(source)) == len(R.REGISTRY)
    assert "R.begin(" not in stripped

    def one_run():
        fx = wlfix.Fixture(tmp_path / "hookfix")
        fx.setup()
        fx.hook = hooks / "worklist.py"
        _static_block_world(fx)
        return fx.run({"PYTHONDONTWRITEBYTECODE": "1"})

    marked = one_run()
    (hooks / "wl_checks.py").write_text(stripped, encoding="utf-8")
    bare = one_run()
    assert marked.decision == "block", marked.out[:300]
    assert (marked.rc, marked.out) == (bare.rc, bare.out)


def test_the_cli_answers_through_wl_cli(wl):
    """`--list --open <me>` is a wl_cli verb now. Control: with wl_cli's dispatch planted to hand nothing back, the same call falls through to the Stop path (a hook verdict on stdout), so the real answer came from wl_cli."""
    got = wl.cli("--list", "--open", wlfix.ME)
    assert got.rc == 0, got.err[:300]
    assert '"decision"' not in got.out, got.out[:300]
    refused = wl.cli("--no-such-verb")
    assert refused.rc == 2, refused.out[:300]
    assert "unknown verb" in refused.err, refused.err[:300]

    hooks = wl.base / "hooks" / "stop"
    shutil.copytree(wlfix.STOP_DIR, hooks, ignore=shutil.ignore_patterns("__pycache__"))
    cli = (hooks / "wl_cli.py").read_text(encoding="utf-8")
    anchor = '    """Run the verb named by sys.argv.'
    end = cli.index('"""', cli.index(anchor) + len(anchor)) + 3
    planted = cli[:end] + "\n    return False" + cli[end:]
    (hooks / "wl_cli.py").write_text(planted, encoding="utf-8")
    wl.hook = hooks / "worklist.py"
    mute = wl.cli("--list", "--open", wlfix.ME)
    assert '"decision"' in mute.out, (mute.rc, mute.out[:300], mute.err[:300])
