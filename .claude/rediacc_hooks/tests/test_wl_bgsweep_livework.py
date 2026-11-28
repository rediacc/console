"""wl_bgsweep: a shell whose descendants are real work is reported as unowned live work, never as a kill order.

2026-11-26: pid 701267, launched by a runner sub-agent that had finished, had the child `python3 -m rediacc_ci.housekeeping.cf_retire archive rediacc-www-media --to-bucket media`, a sha256 verify of 8,422 objects 27+ minutes in. The `bg-orphan` check judged the shell alone (a finished agent's shell, quiet past the threshold) and ordered `kill -- -701267` on every stop, which would have thrown the run away. The sweep now classifies a reported shell by its descendant processes: a descendant that is not a wait command (sleep, a poll of grep/test/ls/tail, the wake timer) makes the shell live work, reported once as `unowned live work: <command>, adopt or let finish`. The pure wait loop and duplicate waiter kill orders are untouched.

Run: python3 -m pytest .claude/rediacc_hooks/tests/test_wl_bgsweep_livework.py -q
"""

from __future__ import annotations

import time

import pytest

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_bgsweep_stop import Tree, _children
from rediacc_hooks.tests.test_wl_pr_scope_stop import keys_of, loop_world, reason, run_stop

B = wlfix.import_wl("wl_bgsweep")

WRAP = (
    "/bin/bash -B -c source /home/u/.claude/shell-snapshots/snap.sh 2>/dev/null || true && "
    "eval '%s' < /dev/null && pwd -P >| /tmp/claude-1a2b-cwd /bin/bash"
)
RETIRE = "python3 -m rediacc_ci.housekeeping.cf_retire archive rediacc-www-media --to-bucket media"
POLL = "until [ -s /tmp/claude-1000/p/s/tasks/bd6uzch6r.output ]; do sleep 15; done"
LIM = B.BGSWEEP_AGE_MIN * 60


@pytest.fixture(autouse=True)
def _anchor(monkeypatch):
    monkeypatch.setenv("WORKLIST_HARNESS_PID", "1")


def run(rows, stdout=None, live=(), owners=None):
    table = [(1, 0, "claude", 0), *rows]
    return B.findings(
        table,
        [(p, pp, c) for p, pp, c, _a in table],
        live_ids=set(live),
        stdout_task=(stdout or {}).get,
        owners=owners,
        pgid_of=lambda p: p,
        target_note=lambda _t: "target note",
    )


def kinds(found):
    return sorted((f.pid, f.kind) for f in found)


def finished(agent="arunner1"):
    return lambda ages: (dict.fromkeys(ages, agent), {agent}, {agent: 30})


def test_a_finished_agents_shell_running_a_python_module_is_live_work_not_a_kill():
    shell = WRAP % ("cd /repo && PYTHONPATH=.ci %s" % RETIRE)
    got = run(
        [(701267, 1, shell, 28 * 60 + LIM), (701270, 701267, RETIRE, 28 * 60 + LIM)],
        {701267: "brun1", 701270: "brun1"},
        {"brun1"},
        finished(),
    )
    assert kinds(got) == [(701267, B.LIVE_WORK)], got
    f = got[0]
    assert not B.is_kill_order(f), f
    assert f.origin == B.FINISHED_AGENT, f
    assert B.kill_command(f) == "", B.kill_command(f)
    text = B.describe(f)
    assert "unowned live work: %s" % RETIRE in text, text
    assert "adopt or let finish" in text, text
    assert "arunner1" in text, text


def test_an_undeclared_shell_running_a_python_module_is_live_work_not_a_kill():
    got = run(
        [
            (2, 1, WRAP % ("PYTHONPATH=.ci %s" % RETIRE), LIM + 60),
            (3, 2, RETIRE, LIM + 60),
        ]
    )
    assert kinds(got) == [(2, B.LIVE_WORK)], got
    assert not B.is_kill_order(got[0])
    report = B.live_work_report(got)
    assert "pid 2" in report, report
    assert RETIRE in report, report
    assert "adopt or let finish" in report, report
    assert "kill -- -2" not in report, report
    assert "kill 2" not in report, report


def test_control_an_undeclared_pure_until_sleep_loop_is_still_a_kill_order():
    got = run([(2, 1, WRAP % POLL, LIM + 60), (3, 2, "sleep 15", 5)])
    assert kinds(got) == [(2, B.ORPHAN)], got
    assert B.is_kill_order(got[0])
    assert B.kill_command(got[0]) == "kill -- -2"


def test_control_a_finished_agents_poll_shell_with_only_wait_children_is_still_a_kill_order():
    # Not a PURE wait loop (work follows `done`), so it reaches the finished-agent judgement; its live descendants are a grep probe and a sleep, which are waiting, not work.
    shell = WRAP % "while ! grep -q done /tmp/x.log; do sleep 5; done; ./deploy.sh"
    got = run(
        [(2, 1, shell, LIM + 60), (3, 2, "grep -q done /tmp/x.log", 1), (4, 2, "sleep 5", 1)],
        {2: "bw1", 3: "bw1", 4: "bw1"},
        {"bw1"},
        finished(),
    )
    assert kinds(got) == [(2, B.FINISHED_AGENT)], got
    assert B.is_kill_order(got[0])


def test_control_a_declared_pure_wait_loop_is_still_a_kill_order():
    got = run([(2, 1, WRAP % POLL, LIM + 60), (3, 2, "sleep 15", 5)], {2: "bp1", 3: "bp1"}, {"bp1"})
    assert kinds(got) == [(2, B.WAIT_LOOP)], got
    assert B.is_kill_order(got[0])


def test_control_a_duplicate_waiter_is_still_a_kill_order():
    got = run(
        [(2, 1, WRAP % POLL, 300), (3, 1, WRAP % POLL, 60)],
        {2: "bd1", 3: "bd2"},
        {"bd1", "bd2"},
    )
    assert kinds(got) == [(2, B.DUPLICATE_WAIT)], got
    assert B.is_kill_order(got[0])


def test_live_work_looks_through_a_subshell_layer():
    shell = WRAP % ("bash -c '%s'" % RETIRE)
    got = run(
        [
            (2, 1, shell, LIM + 60),
            (3, 2, "bash -c %s" % RETIRE, LIM + 60),
            (4, 3, RETIRE, LIM + 60),
        ]
    )
    assert kinds(got) == [(2, B.LIVE_WORK)], got
    assert got[0].target == RETIRE, got[0]


def test_a_wake_timer_descendant_is_not_live_work():
    wake = "python3 .claude/hooks/stop/wl_wake.py d778be9d --minutes 30"
    assert B.live_command([(3, 2, wake, 5)], 2) == ""
    assert B.live_command([(3, 2, "sleep 15", 5), (4, 2, "tail -n 5 /tmp/x", 5)], 2) == ""
    assert B.live_command([(3, 2, "env FOO=1 /usr/bin/python3 -m x", 5)], 2) == (
        "env FOO=1 /usr/bin/python3 -m x"
    )


def test_the_live_work_report_is_free_of_ages_so_an_unchanged_set_is_reported_once():
    rows = [(2, 1, WRAP % RETIRE, LIM + 60), (3, 2, RETIRE, LIM + 60)]
    first = B.live_work_report(run(rows))
    later = B.live_work_report(run([(p, pp, c, a + 600) for p, pp, c, a in rows]))
    assert first
    assert first == later


# ---- Through the real Stop hook: a real process tree under a stand-in harness pid (test_wl_bgsweep_stop.Tree), its task undeclared. The trailing `; true` keeps bash from exec-ing the last command, so the shell stays the parent, as the harness wrapper does.
WORK = 'python3 -c "import time; time.sleep(120)"; true'
WAIT = "tail -f /dev/null; true"


def _undeclared_tree(fix, cmd, task):
    tree = Tree(fix, cmd, task)
    fix.bg = "[]"
    deadline = time.time() + 5
    while time.time() < deadline and not _children(tree.pid):
        time.sleep(0.05)
    assert _children(tree.pid), "SETUP: the shell never forked its child"
    return tree


def test_hook_an_undeclared_shell_running_python_is_not_a_bg_orphan_block(wl):
    loop_world(wl)
    tree = _undeclared_tree(wl, WORK, "bwork001")
    try:
        got = run_stop(wl, tree.env)
        assert "bg-orphan" not in keys_of(wl, got), reason(got)[:2500]
        # f493c5be.1: the shell is not dropped, it is reported: the live-work advisory names it, so a stop that silently lost the finding fails here.
        assert "UNOWNED LIVE WORK SHELL" in got.out, got.out[:2500]
    finally:
        tree.close()


def test_hook_control_an_undeclared_tail_shell_is_still_a_bg_orphan_block(wl):
    loop_world(wl)
    tree = _undeclared_tree(wl, WAIT, "bwait001")
    try:
        got = run_stop(wl, tree.env)
        assert "bg-orphan" in keys_of(wl, got), reason(got)[:2500]
        assert "UNOWNED LIVE WORK SHELL" not in got.out, got.out[:2500]
    finally:
        tree.close()


def test_a_finished_agents_live_work_report_ignores_the_agents_quiet_time():
    rows = [(2, 1, WRAP % RETIRE, LIM + 60), (3, 2, RETIRE, LIM + 60)]
    stdout, live = {2: "bq1", 3: "bq1"}, {"bq1"}

    def quiet(minutes):
        return lambda ages: (dict.fromkeys(ages, "aq"), {"aq"}, {"aq": minutes})

    first = B.live_work_report(run(rows, stdout, live, quiet(30)))
    later = B.live_work_report(run(rows, stdout, live, quiet(45)))
    assert "aq" in first
    assert first == later
