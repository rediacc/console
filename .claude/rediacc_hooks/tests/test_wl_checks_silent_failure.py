"""Silent read failures in `wl_checks` (SF3 of the silent-failure sweep).

THE CLASS: a broad `except Exception` that returns or assigns an empty default without naming the failure, so a read, git or parse failure reads as "no data". `wl_checks.note_read_failure(site, exc)` is the fix shape: the default stays (the stop is never taken down), the failure is recorded, and `run_stop` names every recorded site in ONE `check-read-failed` advisory. An advisory only: naming a failure must never widen what a check blocks on.

THREE LAYERS, because the sites are not equally reachable:
  * a structural scan of the real `wl_checks.py` (every `except Exception` handler names its failure, or carries the one explicit "Kept silent on purpose" reason), with controls in both directions so the scan itself is seen to fire;
  * end-to-end injection through a real stop: a wrapper replaces one reader with a function that raises, and the stop output must name that site (the reachable sites on a bare fixture world);
  * in-process injection for the helpers the bare world never reaches.
"""

from __future__ import annotations

import ast
import json
import re
import types

import pytest
import wl_checks
import wl_prscope
import wl_rebase
import wl_retro

from rediacc_hooks.tests import wlfix

SOURCE = (wlfix.STOP_DIR / "wl_checks.py").read_text(encoding="utf-8")
SILENT_OK = "Kept silent on purpose"

WRAPPER = """
import importlib
import os
import runpy
import sys

STOP = {stop!r}
sys.path.insert(0, STOP)
mod, attr = os.environ["SF3_PATCH"].split(":")


def boom(*a, **k):
    raise RuntimeError("sf3-injected")


setattr(importlib.import_module(mod), attr, boom)
sys.argv = [STOP + "/worklist.py"]
runpy.run_path(STOP + "/worklist.py", run_name="__main__")
"""


def silent_handlers(source: str) -> list[int]:
    """Line numbers of every `except Exception` handler that neither uses its bound name, nor calls `note_read_failure`, nor raises, nor carries the SILENT_OK reason."""
    lines = source.splitlines()
    found = []
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.ExceptHandler)
            and isinstance(node.type, ast.Name)
            and node.type.id == "Exception"
        ):
            continue
        body = ast.Module(body=node.body, type_ignores=[])
        names = {n.id for n in ast.walk(body) if isinstance(n, ast.Name)}
        named = bool(node.name and node.name in names) or "note_read_failure" in names
        raises = any(isinstance(n, ast.Raise) for n in ast.walk(body))
        end = max(getattr(n, "end_lineno", node.lineno) or node.lineno for n in node.body)
        reason = any(SILENT_OK in ln for ln in lines[node.lineno - 1 : end])
        if not (named or raises or reason):
            found.append(node.lineno)
    return found


def handler_count(source: str) -> int:
    return sum(
        1
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.ExceptHandler)
        and isinstance(n.type, ast.Name)
        and n.type.id == "Exception"
    )


@pytest.fixture(autouse=True)
def _clean_failures():
    wl_checks.READ_FAILURES.clear()
    yield
    wl_checks.READ_FAILURES.clear()


# ---- layer 1: the scan, and its controls -------------------------------------


def test_scan_fires_on_a_silent_default():
    src = "def f():\n    try:\n        return read()\n    except Exception:\n        return []\n"
    assert silent_handlers(src) == [4]


@pytest.mark.parametrize(
    "handler",
    [
        "except Exception as exc:\n        note_read_failure('x', exc)\n        return []",
        "except Exception as exc:\n        return 'unknown: %s' % exc",
        "except Exception:\n        raise",
        "except Exception:\n        # Kept silent on purpose: nobody reads this.\n        pass",
        "except OSError:\n        return []",
    ],
)
def test_scan_passes_a_named_or_justified_handler(handler):
    src = "def f():\n    try:\n        return read()\n    " + handler + "\n"
    assert silent_handlers(src) == []


def test_the_real_tree_has_no_silent_handler():
    seen = handler_count(SOURCE)
    # Non-vacuity: the scan must be looking at the whole file, not a stub.
    assert seen > 60, "scanned only %d handlers; the scan is not seeing wl_checks.py" % seen
    assert silent_handlers(SOURCE) == [], (
        "an `except Exception` in wl_checks.py swallows its failure without naming it; "
        "call note_read_failure(site, exc) beside the default, or justify it with '%s'" % SILENT_OK
    )


def test_the_scan_is_red_on_the_pre_fix_file():
    """The same scan over the file as it stood before SF3 (reconstructed by undoing the naming) must find the sweep's sites."""
    stripped = re.sub(r"^(\s*)note_read_failure\(.*\)$", r"\1pass", SOURCE, flags=re.MULTILINE)
    stripped = stripped.replace("except Exception as exc:", "except Exception:")
    assert len(silent_handlers(stripped)) >= 30


# ---- the recorder ------------------------------------------------------------


def test_note_read_failure_names_site_type_and_message():
    wl_checks.note_read_failure("some-site", ValueError("boom"))
    assert wl_checks.READ_FAILURES == {"some-site": "ValueError: boom"}


# ---- layer 2: end-to-end injection through a real stop ------------------------

# (site named in the advisory, "module:attr" replaced by a raising function). Each one is the reader the site wraps.
E2E = [
    ("plan-backlog", "wl_backlog:next_plan"),
    ("plan-drift", "wl_checks:plan_drift_rows"),
    ("plan-enforce", "wl_planenforce:evaluate"),
    ("github-status", "wl_checks:github_status_line"),
    ("backup-lag", "wl_checks:backup_lag"),
    ("feedback-triage", "wl_feedback_triage:due"),
    ("ciquick-on-red", "wl_ci:ciquick_on_red"),
    ("ci-hold", "wl_loopspeed:receipt_behind"),
    ("live-teammates", "wl_liveness:live_teammate_transcripts"),
    ("ask-refusals", "wl_admit:ask_refusals"),
    ("broken-schedules", "wl_checks:broken_schedules"),
    ("deferred-findings", "wl_checks:deferred_findings"),
    ("bg-sweep", "wl_bgsweep:findings"),
    ("unread-reports", "wl_report:read_index"),
    ("landing-stack-tasks", "wl_stack:main_checkout_tasks"),
    ("deflected-finding", "wl_deflect:check"),
    ("idle-stall", "wl_checks:idle_stall"),
]


@pytest.fixture
def stop(tmp_path):
    fix = wlfix.Fixture(tmp_path / "world")
    fix.setup()
    wrapper = tmp_path / "wrap.py"
    wrapper.write_text(WRAPPER.format(stop=str(wlfix.STOP_DIR)), encoding="utf-8")

    def run(patch: str | None = None) -> wlfix.Result:
        if patch is None:
            return fix.run()
        fix.hook = wrapper
        try:
            return fix.run(extra_env={"SF3_PATCH": patch})
        finally:
            fix.hook = wlfix.HOOK

    return run


def advisory_of(got: wlfix.Result) -> str:
    return str(json.loads(got.out).get("systemMessage") or "")


def test_a_clean_stop_names_no_read_failure(stop):
    """CONTROL: the normal path is unchanged, the stop allows and says nothing."""
    got = stop()
    assert got.rc == 0
    assert "check-read-failed" not in got.out
    assert "fell back to an empty default" not in got.out
    assert got.battery_ran


@pytest.mark.parametrize(("site", "patch"), E2E, ids=[s for s, _ in E2E])
def test_an_injected_reader_failure_is_named(stop, site, patch):
    got = stop(patch)
    assert got.rc == 0, got.err[-400:]
    assert got.decision != "block", "naming a failure must never block"
    msg = advisory_of(got)
    assert "  %s: RuntimeError: sf3-injected" % site in msg, (got.out, got.err[-400:])


def test_several_failures_ride_one_advisory(stop):
    """The advisory is one section however many readers failed: the site is a row, not a message."""
    got = stop("wl_backlog:next_plan")
    assert advisory_of(got).count("fell back to an empty default") == 1


# ---- layer 3: in-process injection -------------------------------------------


def raising(*_a, **_k):
    raise RuntimeError("sf3-injected")


def test_closed_sig_names_an_unreadable_store():
    fold = types.SimpleNamespace(items=[{"id": "a"}])  # no "state": the row read raises
    assert wl_checks.closed_sig(fold, "deadbeef") == ""
    assert "stuck-signature" in wl_checks.READ_FAILURES


def test_closed_sig_reads_a_good_store_without_noting():
    fold = types.SimpleNamespace(items=[{"id": "a", "state": " ", "owner": "deadbeef"}])
    assert wl_checks.closed_sig(fold, "deadbeef") != ""
    assert wl_checks.READ_FAILURES == {}


def test_ctx_late_band_names_a_failed_budget_read(monkeypatch):
    monkeypatch.setattr(wl_retro, "ctx", raising)
    assert wl_checks._ctx_late_band("deadbeef") is False
    assert "retro-late-band" in wl_checks.READ_FAILURES


def test_judge_receipt_run_names_a_failed_lock_read(monkeypatch):
    monkeypatch.setattr(wl_checks, "vm_check_running", raising)
    assert wl_checks._judge_receipt_run() is None
    assert "judge-receipt-run" in wl_checks.READ_FAILURES


def test_judge_receipt_run_unchanged_when_the_read_works(monkeypatch):
    monkeypatch.setattr(wl_checks, "vm_check_running", lambda: True)
    assert wl_checks._judge_receipt_run() == "vm:check"
    monkeypatch.setattr(wl_checks, "vm_check_running", lambda: False)
    assert wl_checks._judge_receipt_run() is None
    assert wl_checks.READ_FAILURES == {}


def test_lease_rebase_text_names_a_failed_verdict_read(monkeypatch, tmp_path):
    monkeypatch.setattr(wl_rebase, "lease_verdicts", raising)
    assert wl_checks._lease_rebase_text(tmp_path, "deadbeef0000", ["x"]) == ""
    assert "landing-behind" in wl_checks.READ_FAILURES


# ---- the cd-done latch --------------------------------------------------------


def landing_world(monkeypatch, notice: str):
    step = types.SimpleNamespace(release=True, sha="abc1234", text="STEP", blocks=False, pr=7)
    monkeypatch.setattr(wl_checks.wl_ci, "pr_link", lambda *_a, **_k: ([], ""))
    monkeypatch.setattr(wl_prscope, "landing_loop", lambda *_a, **_k: step)
    monkeypatch.setattr(wl_checks, "ci_verdict", lambda *_a, **_k: "green")
    monkeypatch.setattr(wl_checks.wl_stack, "notify_line", lambda *_a, **_k: notice)
    state_doc: dict = {}
    got = wl_checks.landing_next_text(
        types.SimpleNamespace(branch="b"), "root", "wl", "deadbeef", state_doc, {}, {}, []
    )
    return got, state_doc


def test_an_empty_cd_done_message_does_not_latch(monkeypatch):
    """The defect: the marker was set even when the message text was empty, so one failed read dropped cd-done for good."""
    got, state_doc = landing_world(monkeypatch, "")
    assert got == ("STEP", False)
    assert "landing" not in state_doc
    assert "cd-done-message" in wl_checks.READ_FAILURES


def test_a_non_empty_cd_done_message_latches_and_blocks(monkeypatch):
    """CONTROL: the normal path is unchanged."""
    got, state_doc = landing_world(monkeypatch, "CD DONE MESSAGE")
    assert got[1] is True
    assert "CD DONE MESSAGE" in got[0]
    assert state_doc["landing"] == {"cd_done": "abc1234"}
    assert wl_checks.READ_FAILURES == {}


def test_a_latched_sha_is_not_sent_again(monkeypatch):
    step = types.SimpleNamespace(release=True, sha="abc1234", text="STEP", blocks=False, pr=7)
    monkeypatch.setattr(wl_checks.wl_ci, "pr_link", lambda *_a, **_k: ([], ""))
    monkeypatch.setattr(wl_prscope, "landing_loop", lambda *_a, **_k: step)
    monkeypatch.setattr(wl_checks, "ci_verdict", lambda *_a, **_k: "green")
    monkeypatch.setattr(wl_checks.wl_stack, "notify_line", raising)
    state_doc = {"landing": {"cd_done": "abc1234"}}
    got = wl_checks.landing_next_text(
        types.SimpleNamespace(branch="b"), "root", "wl", "deadbeef", state_doc, {}, {}, []
    )
    assert got == ("STEP", False)
    assert wl_checks.READ_FAILURES == {}


def test_main_checkout_tasks_failure_is_named_in_the_landing_text():
    """The inline `landing-stack-tasks` site keeps the note beside whichever landing-stack text speaks."""
    assert "_ls_tasks_note" in SOURCE
    assert 'note_read_failure("landing-stack-tasks", exc)' in SOURCE
    assert "_ls_block = _ls_block" in SOURCE
    assert "_ls_held = _ls_held" in SOURCE
    assert _note_reaches_render(SOURCE) == {"_ls_block": "vadd", "_ls_held": "outq_add"}


def _note_reaches_render(source: str) -> dict[str, str]:
    """For each of `_ls_block` / `_ls_held`: the call that renders it (`vadd` or `outq_add`, with the variable as an argument) in a statement AFTER the one appending `_ls_tasks_note` to it, in the same block. A variable whose note is appended but never rendered afterwards is absent (cc68eafa.2)."""
    found: dict[str, str] = {}
    for node in ast.walk(ast.parse(source)):
        stmts = getattr(node, "body", None)
        if not isinstance(stmts, list):
            continue
        for i, stmt in enumerate(stmts):
            if not isinstance(stmt, ast.If) or "_ls_tasks_note" not in ast.unparse(stmt.test):
                continue
            targets = {
                t.id
                for s in stmt.body
                if isinstance(s, ast.Assign)
                for t in s.targets
                if isinstance(t, ast.Name)
            }
            for var in targets & {"_ls_block", "_ls_held"}:
                for later in stmts[i + 1 :]:
                    for call in ast.walk(later):
                        if not isinstance(call, ast.Call):
                            continue
                        name = ast.unparse(call.func)
                        if name in ("vadd", "outq_add") and any(
                            isinstance(a, ast.Name) and a.id == var for a in call.args
                        ):
                            found.setdefault(var, name)
    return found


def test_control_a_note_appended_after_the_render_is_not_rendered():
    """cc68eafa.2 control: the note appended after the render calls reaches neither; the check above would fail on it."""
    planted = (
        "def f():\n"
        "    if _ls_block:\n"
        "        vadd('landing-stack', False, _ls_block)\n"
        "    if _ls_held:\n"
        "        outq_add(w, s, d, 'landing-stack', _ls_held, 1)\n"
        "    if _ls_block and _ls_tasks_note:\n"
        "        _ls_block = _ls_block + _ls_tasks_note\n"
        "    if _ls_held and _ls_tasks_note:\n"
        "        _ls_held = _ls_held + _ls_tasks_note\n"
    )
    assert _note_reaches_render(planted) == {}


def test_the_advisory_is_not_a_violation():
    """No new stop block: the section rides the allow queue and is never a vadd key."""
    assert 'vadd("check-read-failed"' not in SOURCE
    assert '"check-read-failed",' in SOURCE
