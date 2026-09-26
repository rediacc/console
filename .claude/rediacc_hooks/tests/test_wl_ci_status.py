"""Submodule pointer drift and the CI-status check: failing jobs, cancels, watchdog retries, armed watches, the ceiling.

Ported from `.claude/hooks/stop/worklist-cases/09-ci-status.sh`, one pytest function per numbered bash case.

EVERY ONE OF THE CI CASES IS A CONTROL FOR A REAL MISREAD, not a hypothetical. The fixtures below encode the exact shapes that fooled a human reading the same API by hand for a night: a cancelled run with zero failed jobs, a cancelled run hiding one real failure, a flake the watchdog was already retrying, and a background watch pointed at a superseded run. The network is never
touched; `gh` is a shim serving JSON from files.
"""

from __future__ import annotations

import json
import subprocess
import sys

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

# The Actions job the shim serves for every per-job lookup: one green step and one red one, so the block can name a failing step.
CI_JOB_PAYLOAD = {
    "run_id": 30514648812,
    "run_attempt": 1,
    "steps": [
        {"name": "Set up job", "conclusion": "success"},
        {"name": "Shell format", "conclusion": "failure"},
    ],
}

# The freshness check shares the `gh api graphql` path, so the shim must answer BOTH queries; a body edited in 2999 keeps that check quiet.
CI_FRESH_PAYLOAD = {
    "data": {
        "repository": {
            "pullRequests": {
                "nodes": [
                    {
                        "number": 543,
                        "lastEditedAt": "2999-01-01T00:00:00Z",
                        "updatedAt": "2999-01-01T00:00:00Z",
                    }
                ]
            }
        }
    }
}

GH_SHIM = """#!/bin/bash
for a in "$@"; do
    case "$a" in
        *lastEditedAt*) cat "%(base)s/ci-fresh.json"; exit 0 ;;
        query=*) cat "%(base)s/ci-rollup.json"; exit 0 ;;
    esac
done
case "$*" in
    *actions/jobs/*) cat "%(base)s/ci-job.json"; exit 0 ;;
esac
echo '{}'
"""


def write_exec(path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def ci_setup(fix) -> None:
    """A repo with an origin/pub ref, one fresh brief, and a gh shim."""
    fix.setup()
    fix.brief_now()
    fix.git("init", "-q", "-b", "main")
    fix.git("config", "user.email", "t@t")
    fix.git("config", "user.name", "t")
    fix.git("remote", "add", "origin", "https://github.com/fake/repo.git")
    (fix.proj / "a.txt").write_text("a\n", encoding="utf-8")
    fix.git("add", "-A")
    fix.git("commit", "-qm", "base")
    head = fix.git("rev-parse", "HEAD").stdout.strip()
    fix.git("update-ref", "refs/remotes/origin/pub", head)
    (fix.base / "ci-fresh.json").write_text(json.dumps(CI_FRESH_PAYLOAD) + "\n", encoding="utf-8")
    (fix.base / "ci-job.json").write_text(json.dumps(CI_JOB_PAYLOAD) + "\n", encoding="utf-8")
    write_exec(fix.base / "binonly" / "gh", GH_SHIM % {"base": fix.base})


def ci_rollup(fix, state: str, contexts: str) -> None:
    """The statusCheckRollup the shim serves, plus the cache drop the swap needs.

    The read is cached on the published tip SHA, so a fixture swap inside one case must drop the cache or it reads the previous shape.
    """
    payload = (
        '{"data":{"repository":{"pullRequests":{"nodes":[{"number":543,"url":"u",'
        '"commits":{"nodes":[{"commit":{"oid":"deadsha0000","statusCheckRollup":'
        '{"state":"%s","contexts":{"totalCount":9,"pageInfo":{"hasNextPage":false,'
        '"endCursor":null},"nodes":%s}}}}]}}]}}}}\n' % (state, contexts)
    )
    (fix.base / "ci-rollup.json").write_text(payload, encoding="utf-8")
    fix.stem(".cistate-deadbeef").unlink(missing_ok=True)


def ci_job(name: str, conclusion: str, ident: int = 90784763855) -> str:
    """A completed Actions check run."""
    return (
        '{"__typename":"CheckRun","name":"%s","status":"COMPLETED","conclusion":"%s",'
        '"databaseId":%s,"detailsUrl":"https://x/job/%s",'
        '"checkSuite":{"workflowRun":{"databaseId":30514648812}}}'
        % (name, conclusion, ident, ident)
    )


def ci_running(name: str) -> str:
    """A check run still in flight."""
    return (
        '{"__typename":"CheckRun","name":"%s","status":"IN_PROGRESS","conclusion":null,'
        '"databaseId":1,"detailsUrl":"",'
        '"checkSuite":{"workflowRun":{"databaseId":30514648812}}}' % name
    )


def ci_run(fix, message: str = "work done", bg: str = "[]", ref: str = "pub") -> wlfix.Result:
    """A Stop event with the CI check armed.

    JSON-ENCODED, not interpolated into a printf template. A message carrying a newline (one with its own `## Remaining` section, which any case whose fixture opens a real item needs) produced INVALID JSON, and the hook's answer to that is to report that the Stop event on stdin was not parseable and block, so the case measured the parse error rather than the behaviour under test.
    """
    payload = json.dumps(
        {
            "session_id": fix.sid,
            "cwd": str(fix.proj),
            "last_assistant_message": message,
            "session_crons": [],
            "background_tasks": json.loads(bg),
        }
    )
    env = dict(fix.env)
    env["PATH"] = "%s:%s" % (fix.base / "binonly", fix.env.get("PATH", ""))
    env["TMPDIR"] = str(fix.base / "tmp")
    env["CLAUDE_PROJECT_DIR"] = str(fix.proj)
    env["WORKLIST_TASKS_DIR"] = str(fix.base / "tasks")
    env["WORKLIST_PUBLISH_REF"] = ref
    env["WORKLIST_JUDGE"] = "off"
    env["GITHUB_ACTIONS"] = fix.gha
    return fix.python([], stdin=payload, env=env)


def cichk(fix, label: str, want: str, needle: str, **kwargs) -> wlfix.Result:
    """`cichk <label> <yes|no> <needle>`: the needle present or absent."""
    got = ci_run(fix, **kwargs)
    present = "yes" if needle in got.out else "no"
    assert present == want, "%s (wanted needle %s, got %s) needle=%r\n  out: %s\n  err: %s" % (
        label,
        want,
        present,
        needle,
        got.out[:400],
        got.err[:200],
    )
    return got


def probe_moves(fix, super_dir) -> str:
    """`worklist.submodule_pointer_moves`, rendered as `<path>|<where>` rows.

    Driven in a subprocess, as the bash did, so importing the whole hook cannot leave module state behind in the pytest process.
    """
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import worklist as W\n"
        "for p, a, b, where in W.submodule_pointer_moves(%r):\n"
        "    print('%%s|%%s' %% (p, where))"
    ) % (str(wlfix.STOP_DIR), str(super_dir))
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=dict(fix.env),
        check=False,
    )
    return proc.stdout.strip()


def test_119_a_submodule_pointer_moved_onto_a_feature_branch_is_caught(wl):  # noqa: F811
    """REGRESSION, from a real near-miss. A subagent committed inside a submodule on its own branch, which necessarily moves the superproject's gitlink, and the standing sweep-everything-with-git-add-A rule would have COMMITTED that move, silently adding the submodule's PR to this PR's merge chain. Quality / Submodule Branches only says so minutes later, in CI.

    A REAL git fixture with a REAL remote, because the decisive fact is which REMOTE branches contain the commit: a local-only branch proves nothing about what CI can fetch.

    TWO FIXTURE BUGS, both found by CI and neither by this suite (see the CONTROL note below). First: `git init --bare` inherits init.defaultBranch, which the author's ~/.gitconfig pins to `main` and a CI runner leaves at `master`. The bare remote's HEAD then named a branch that was never pushed, the submodule clone landed on an unborn branch, and `submodule add` aborted on a
    branch yet to be born. Every `-b main` below is therefore load-bearing: pin the branch, never inherit it. Second: the fixture swallowed stdout AND stderr, so that fatal was invisible and CI could only report an empty `got:`. It is captured now and printed on failure.

    VERIFIED, so this is not a guess: the same fixture was run under git 2.55.0 in a container. Without `-b main` it reproduces CI exactly (submodule add exits 128, ls-files -s finds no gitlink). With it, `git submodule status --cached` prints the leading `+` on 2.55.0 just as it does on the author's 2.43.0, so the DETECTOR was never version-sensitive and is left alone.
    """
    subw = wl.base / "subptr"
    subw.mkdir(parents=True, exist_ok=True)
    log: list[str] = []

    def sh(*args: str, cwd=None) -> None:
        proc = subprocess.run(
            list(args), cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=False
        )
        log.append("%s -> %s %s" % (" ".join(args), proc.stdout.strip(), proc.stderr.strip()))

    sh("git", "init", "-q", "--bare", str(subw / "remote.git"), "-b", "main")
    sh("git", "init", "-q", str(subw / "sub"), "-b", "main")
    (subw / "sub" / "f").write_text("one\n", encoding="utf-8")
    sh("git", "add", "f", cwd=subw / "sub")
    sh(
        "git",
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-qm",
        "one",
        cwd=subw / "sub",
    )
    sh("git", "remote", "add", "origin", str(subw / "remote.git"), cwd=subw / "sub")
    sh("git", "push", "-q", "origin", "main", cwd=subw / "sub")
    sh("git", "init", "-q", str(subw / "super"), "-b", "main")
    sh(
        "git",
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(subw / "remote.git"),
        "sub",
        cwd=subw / "super",
    )
    sh("git", "add", "-A", cwd=subw / "super")
    sh(
        "git",
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-qm",
        "super",
        cwd=subw / "super",
    )

    # CONTROL FIRST, and it must NOT be satisfiable by a broken fixture. The old version asserted only that probe_moves prints nothing, which a superproject with no submodule at all satisfies, so it passed green in CI on a fixture whose `submodule add` had died, while the detection half beside it failed with an empty string. A silent control has to prove the instrument exists
    # before it proves the instrument is quiet.
    gitlink = subprocess.run(
        ["git", "-C", str(subw / "super"), "ls-files", "-s", "sub"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    assert gitlink.startswith("160000"), (
        "fixture never built a gitlink (ls-files -s sub: %r)\n  git log: %s"
        % (gitlink or "empty", " ".join(log)[:300])
    )
    assert not probe_moves(wl, subw / "super"), "control fired on a clean pointer"

    sh("git", "checkout", "-q", "-b", "feat", cwd=subw / "super" / "sub")
    (subw / "super" / "sub" / "f2").write_text("two\n", encoding="utf-8")
    sh("git", "add", "f2", cwd=subw / "super" / "sub")
    sh(
        "git",
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-qm",
        "two",
        cwd=subw / "super" / "sub",
    )
    sh("git", "push", "-q", "origin", "feat", cwd=subw / "super" / "sub")
    sh("git", "fetch", "-q", "origin", cwd=subw / "super" / "sub")

    out = probe_moves(wl, subw / "super")
    for needle in ("sub|", "origin/feat", "NOT on origin/main"):
        assert needle in out, "expected %r in the reported move, got %r\n  git log: %s" % (
            needle,
            out,
            " ".join(log)[:300],
        )


def test_120_control_it_fires_a_real_per_job_failure_blocks_with_job_step_and_log(wl):  # noqa: F811
    """A real failure blocks and hands over the job, the failing step and a working log command."""
    ci_setup(wl)
    ci_rollup(
        wl,
        "FAILURE",
        "[%s, %s]"
        % (ci_job("Quality / Static", "FAILURE"), ci_job("Quality / Security", "SUCCESS")),
    )
    got = ci_run(wl)
    for needle in (
        "CI IS RED ON PR #543",
        "Quality / Static",
        "failing step: Shell format",
        "gh api repos/fake/repo/actions/jobs/90784763855/logs",
        "log-failed",
    ):
        assert needle in got.out, "red CI did not produce an actionable block, MISSING %r: %s" % (
            needle,
            got.out[:400],
        )
    assert '"decision": "block"' in got.out, got.out[:400]


def test_121_control_it_stays_silent_an_all_green_run_says_nothing(wl):  # noqa: F811
    """CONTROL: a green run produces no CI complaint at all."""
    ci_setup(wl)
    ci_rollup(
        wl,
        "SUCCESS",
        "[%s, %s]" % (ci_job("Quality / Static", "SUCCESS"), ci_job("E2E / ubuntu", "SUCCESS")),
    )
    cichk(wl, "a green run produces no CI complaint", "no", "CI IS RED")


def test_122_control_a_cancelled_run_with_zero_failed_jobs_is_not_red(wl):  # noqa: F811
    """CONTROL. Four runs in one night ended `cancelled` with no failed job, each superseded by the session's own next push. Reading the run-level rollup would have nagged four times about nothing."""
    ci_setup(wl)
    ci_rollup(
        wl,
        "FAILURE",
        "[%s, %s, %s]"
        % (
            ci_job("Quality / Static", "CANCELLED"),
            ci_job("E2E / ubuntu", "CANCELLED"),
            ci_job("Init", "SKIPPED"),
        ),
    )
    cichk(
        wl,
        "cancelled-with-no-failures is silent even when the rollup says FAILURE",
        "no",
        "CI IS RED",
    )


def test_123_a_cancelled_run_hiding_one_real_failure_still_fires(wl):  # noqa: F811
    """The other half: the watchdog force-cancels a run when a gate fails, so `cancelled` also means something genuinely failed. Only per-JOB conclusions separate run 30514648812 (cancelled, Quality / Static = failure) from 30513152662."""
    ci_setup(wl)
    ci_rollup(
        wl,
        "CANCELLED",
        "[%s, %s]" % (ci_job("Quality / Static", "FAILURE"), ci_job("E2E / ubuntu", "CANCELLED")),
    )
    cichk(wl, "one real failure inside a cancelled run is found", "yes", "Quality / Static")


def test_124_control_a_failing_e2e_leg_with_a_watchdog_retry_pending_does_not_block(wl):  # noqa: F811
    """WATCHDOG_RETRY_ALLOWLIST_PATTERNS in .github/workflows/watchdog-monitor.yml. That night an opensuse E2E leg died on a Docker Hub CDN reset, was retried onto the same run, and the run finished green at 95 jobs."""
    ci_setup(wl)
    ci_rollup(
        wl,
        "PENDING",
        "[%s, %s]" % (ci_job("E2E / opensuse", "FAILURE"), ci_running("E2E / ubuntu")),
    )
    got = ci_run(wl)
    assert "CI IS RED" not in got.out, "a retryable leg on a live run blocked: %s" % got.out[:400]
    assert "retry allowlist" in got.out, (
        "a retryable leg on a live run must still be REPORTED: %s" % got.out[:400]
    )


def test_125_once_the_run_is_final_the_same_leg_is_hard(wl):  # noqa: F811
    """The pair for 124: the same allowlisted leg, still red on a finished run, becomes actionable."""
    ci_setup(wl)
    ci_rollup(wl, "FAILURE", "[%s]" % ci_job("E2E / opensuse", "FAILURE"))
    cichk(wl, "a retryable leg still red on a finished run becomes actionable", "yes", "CI IS RED")


def test_126_a_running_background_watch_naming_this_run_silences_the_check(wl):  # noqa: F811
    """An armed watch on the current run IS the wake-up, so the hook stays quiet."""
    ci_setup(wl)
    ci_rollup(wl, "FAILURE", "[%s]" % ci_job("Quality / Static", "FAILURE"))
    bg = json.dumps(
        [
            {
                "id": "w1",
                "status": "running",
                "description": "watch CI",
                "command": ".ci/scripts/ci/ci-trace.py --wait",
            }
        ]
    )
    cichk(wl, "an armed watch on the current run keeps the hook quiet", "no", "CI IS RED", bg=bg)


def test_127_a_completed_or_superseded_watch_does_not_count_as_armed(wl):  # noqa: F811
    """Both happened: a completed watch reported completed/cancelled for a run that had since been superseded, and another reported a FALSE failure because a watchdog rerun flipped a terminal run back to in_progress."""
    ci_setup(wl)
    ci_rollup(wl, "FAILURE", "[%s]" % ci_job("Quality / Static", "FAILURE"))
    bg = json.dumps(
        [
            {
                "id": "w1",
                "status": "completed",
                "description": "watch",
                "command": ".ci/scripts/ci/ci-trace.py --wait",
            },
            {
                "id": "w2",
                "status": "running",
                "description": "watch",
                "command": ".ci/scripts/ci/ci-trace.py --wait --ref other",
            },
        ]
    )
    cichk(
        wl,
        "a dead watch and a watch on another run leave the check armed",
        "yes",
        "CI IS RED",
        bg=bg,
    )


def test_128_the_block_has_a_hard_ceiling(wl):  # noqa: F811
    """The deadlock guard. A different check trapped this session for an entire night by demanding something it could not produce; this one cannot, by construction. And the downgrade is not silence: the failure is still reported."""
    ci_setup(wl)
    ci_rollup(wl, "FAILURE", "[%s]" % ci_job("Quality / Static", "FAILURE"))
    fired = sum(1 for _ in range(4) if "CI IS RED" in ci_run(wl).out)
    assert fired == 2, "expected 2 blocking stops for one failure set, got %d" % fired
    got = ci_run(wl)
    assert "still red" in got.out, (
        "a downgraded CI failure vanished instead of being reported: %s" % got.out[:300]
    )
    assert "CI IS RED" not in got.out, "the ceiling did not downgrade the block: %s" % got.out[:300]


def test_129_naming_the_failing_job_in_the_stop_message_clears_the_block(wl):  # noqa: F811
    """An acknowledgement that names the job is the fast exit, not a bypass."""
    ci_setup(wl)
    ci_rollup(wl, "FAILURE", "[%s]" % ci_job("Quality / Static", "FAILURE"))
    cichk(
        wl,
        "an acknowledgement that names the job is the fast exit",
        "no",
        "CI IS RED",
        message="Quality / Static is red on the shfmt step; a sub-agent is on it",
    )


def test_130_an_unreadable_lookup_blocks_rather_than_passing_quietly(wl):  # noqa: F811
    """Blindness is its own verdict, per no-escape-hatch."""
    ci_setup(wl)
    write_exec(
        wl.base / "binonly" / "gh",
        '#!/bin/bash\necho "gh: could not resolve to a Repository" >&2\nexit 1\n',
    )
    wl.stem(".cistate-deadbeef").unlink(missing_ok=True)
    cichk(wl, "blindness is its own verdict", "yes", "PR CI-status lookup failed")


def test_131_two_live_sessions_mean_silence(wl):  # noqa: F811
    """A second live session silences the check, because the red may be theirs."""
    ci_setup(wl)
    ci_rollup(wl, "FAILURE", "[%s]" % ci_job("Quality / Static", "FAILURE"))
    wl.brief_other("cafe1234")
    cichk(wl, "a second live session silences the check", "no", "CI IS RED")


def test_131b_an_unset_publish_ref_costs_no_network_call(wl):  # noqa: F811
    """The opt-out must cost NOTHING: a gh that dies if invoked proves the check never reaches the network when WORKLIST_PUBLISH_REF is unset.

    THE BASH ASSERTION HERE COULD NOT FAIL, for two independent reasons, and what is asserted below is what it meant to assert. First, its fixture was a bare `setup` with no git repo and no origin/pub ref, so the CI check had nothing to resolve and would have skipped the lookup whatever the ref said. Second, and fatal on its own, it grepped the HOOK's stderr for the shim's message:
    the hook captures the child's stderr and folds it into the block reason on STDOUT, so `GH-WAS-CALLED` does not appear where the bash looked for it. Both halves are repaired here: the fixture is the one that DOES reach `gh`, and the needle is looked for where the hook really puts it.
    """
    ci_setup(wl)
    write_exec(wl.base / "binonly" / "gh", '#!/bin/bash\necho "GH-WAS-CALLED" >&2\nexit 3\n')
    got = ci_run(wl, ref="")
    assert "GH-WAS-CALLED" not in got.out + got.err, (
        "the opt-out path still shelled out to gh: %s" % got.out[:400]
    )
    # CONTROL: the SAME fixture with the ref set DOES reach the shim, so the silence above is an opt-out working rather than a probe with no way to fire.
    wl.stem(".cistate-deadbeef").unlink(missing_ok=True)
    armed = ci_run(wl, ref="pub")
    assert "GH-WAS-CALLED" in armed.out, (
        "CONTROL: with the ref set the dying gh must be reached and reported: %s" % armed.out[:400]
    )
