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
        if isinstance(n, ast.Call) and _callee(n) == "with_plan_line"
    ]


def _callee(call: ast.Call) -> str:
    """The called name, whether written `x.with_plan_line(...)` or a bare `with_plan_line(...)`."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def _binds(call: ast.Call) -> bool:
    sig = inspect.signature(plan_gate.with_plan_line)
    if any(k.arg is None for k in call.keywords) or any(
        isinstance(a, ast.Starred) for a in call.args
    ):
        # A `**mapping` or `*args` splat hides the names it passes, so the call cannot be proven to bind.
        return False
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


def test_control_a_bare_call_with_a_stale_keyword_is_seen_and_does_not_bind():
    calls = _calls("with_plan_line(stripped, head, append=True)")
    assert len(calls) == 1
    assert not _binds(calls[0])


def test_control_a_splatted_call_cannot_be_proven_to_bind():
    calls = _calls("plan_gate.with_plan_line(stripped, head, **extra)")
    assert len(calls) == 1
    assert not _binds(calls[0])
