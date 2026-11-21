"""refresh_pr_body must call plan_gate.with_plan_line with arguments the function accepts (85e2fccb.1: the commit dropped the `append` parameter while this caller still passed it, so the hook raised TypeError on every push)."""

import ast
import inspect
import pathlib

from rediacc_hooks import plan_gate

HOOK = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "post-bash" / "refresh_pr_body.py"


def _calls(source: str) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "with_plan_line"
    ]


def _binds(call: ast.Call) -> bool:
    sig = inspect.signature(plan_gate.with_plan_line)
    try:
        sig.bind(*[None] * len(call.args), **{k.arg: None for k in call.keywords if k.arg})
    except TypeError:
        return False
    return True


def test_hook_calls_with_plan_line_with_accepted_arguments():
    calls = _calls(HOOK.read_text(encoding="utf-8"))
    assert calls, "the hook no longer calls with_plan_line; update this test"
    assert all(_binds(c) for c in calls)


def test_control_a_stale_append_keyword_does_not_bind():
    stale = "plan_gate.with_plan_line(stripped, head, append=True)"
    calls = _calls(stale)
    assert len(calls) == 1
    assert not _binds(calls[0])
