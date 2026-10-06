"""One pre-push per push and no push into a running run (agent/plans/PLAN-fast-loop.md, Parts 3 and 4): `wl_loopspeed`, the post-bash member `loop_speed_note.py`, and the Stop wiring.

EVERY FIRE CASE HAS ITS INVERSE, differing by one planted fact: a code commit or a record-only one, a running run or a red or a green one, local commits or none. Every advisory is shown NOT blocking: the keys ride `outq_add` and sit outside the blocking core, and the member exits 0 whatever it reads.
"""

from __future__ import annotations

import importlib
import importlib.util
import io
import json
import re
import shutil
import subprocess

import pytest
from rediacc_ci import paths

from rediacc_hooks.tests import wlfix

STOP_DIR = wlfix.STOP_DIR
HOOKS = STOP_DIR.parent
REPO = HOOKS.parent.parent
paths.on_sys_path(STOP_DIR)

import wl_ci  # noqa: E402
import wl_core as C  # noqa: E402
import wl_loopspeed as L  # noqa: E402
import wl_standdown  # noqa: E402
import worklist_messages as M  # noqa: E402

POLICY = {
    "version": 1,
    "records": [
        {"glob": "agent/reviews/**", "except": [], "readers": [{"id": "g"}]},
        {"glob": "agent/*/STATE.md", "except": ["agent/x/STATE.md"], "readers": [{"id": "g"}]},
    ],
}


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def commit(root, rel, text="x\n"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    git(root, "add", "--", rel)
    git(root, "commit", "-q", "-m", "c %s" % rel)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    """A repo on branch `topic` with its record policy committed, pushed to a bare origin, and a receipt for that pushed head."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "topic")
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "t")
    commit(root, L.RECORD_POLICY_REL, json.dumps(POLICY))
    base = commit(root, "src/a.py")
    git(root, "remote", "add", "origin", str(origin))
    git(root, "push", "-q", "origin", "topic")
    receipt = root / L.RECEIPT_REL
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({"head": base, "headTree": "t"}), encoding="utf-8")
    return root, base


# ---- Part 3: receipt_behind -------------------------------------------------


def test_a_code_commit_ahead_of_the_receipt_is_counted(repo):
    root, base = repo
    commit(root, "src/b.py")
    assert L.receipt_behind(root) == (1, base[:8])


def test_record_only_commits_do_not_count(repo):
    root, _ = repo
    commit(root, "agent/reviews/topic/clean.jsonl")
    commit(root, "agent/me/STATE.md")
    assert L.receipt_behind(root) is None


def test_a_record_except_glob_makes_the_path_a_code_path(repo):
    root, base = repo
    commit(root, "agent/x/STATE.md")  # named in the record's `except`
    assert L.receipt_behind(root) == (1, base[:8])


def test_count_is_per_commit_and_a_mixed_commit_is_code(repo):
    root, base = repo
    commit(root, "src/b.py")
    commit(root, "agent/reviews/topic/clean.jsonl")
    (root / "agent/reviews/topic/n.md").write_text("n\n")
    (root / "src/c.py").write_text("c\n")
    git(root, "add", "--", "agent/reviews/topic/n.md", "src/c.py")
    git(root, "commit", "-q", "-m", "mixed")
    assert L.receipt_behind(root) == (2, base[:8])


def test_nothing_unpushed_is_silent_even_when_the_receipt_is_behind(repo):
    root, _ = repo
    commit(root, "src/b.py")
    git(root, "push", "-q", "origin", "topic")
    assert L.unpushed(root) == 0
    assert L.receipt_behind(root) is None


def test_receipt_at_head_is_silent(repo):
    root, _ = repo
    head = commit(root, "src/b.py")
    (root / L.RECEIPT_REL).write_text(json.dumps({"head": head}), encoding="utf-8")
    assert L.receipt_behind(root) is None


def test_missing_garbled_or_unknown_receipts_are_silent(repo):
    root, _ = repo
    commit(root, "src/b.py")
    receipt = root / L.RECEIPT_REL
    for body in ("not json", "[]", json.dumps({"head": "nope"}), json.dumps({"head": "0" * 40})):
        receipt.write_text(body, encoding="utf-8")
        assert L.receipt_behind(root) is None, body
    receipt.unlink()
    assert L.receipt_behind(root) is None


def test_an_unreadable_record_policy_judges_nothing(repo):
    root, _ = repo
    commit(root, L.RECORD_POLICY_REL, "{ not json")
    commit(root, "src/b.py")
    assert L.receipt_behind(root) is None


def test_the_mirrored_record_rules_equal_the_guards_on_the_real_policy():
    # Read-only: the guard is imported only to pin the mirrored record rules equal to its own.
    guard = importlib.import_module("rediacc_hooks.guards.block_unverified_push")

    doc = json.loads((REPO / guard.RECORD_POLICY_REL).read_text(encoding="utf-8"))
    assert guard.RECORD_POLICY_REL == L.RECORD_POLICY_REL
    theirs, err = guard.parse_record_policy(doc)
    mine, merr = L.parse_record_policy(doc)
    assert err is None
    assert merr is None
    assert [(r["glob"], r["except"]) for r in theirs] == [(r["glob"], r["except"]) for r in mine]
    corpus = [
        "agent/reviews/x/clean.jsonl",
        "agent/d778be9d/STATE.md",
        "agent/ledgers/census-claim-check.jsonl",
        "agent/worklist/d778be9d.jsonl",
        "src/a.py",
        "package.json",
        ".claude/hooks/stop/wl_checks.py",
        "scripts/ci-runner/run.ts",
        "docs/agent-reference/ci-gates.md",
    ]
    for path in corpus:
        assert (guard.record_of(path, theirs) is None) == (L.record_of(path, mine) is None), path
    assert guard.record_glob_re("a/**/b?.*").pattern == L.record_glob_re("a/**/b?.*").pattern


# ---- Part 4: ci_hold ----------------------------------------------------------


def check_run(name, status, conclusion=None, ident=1):
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "databaseId": ident,
        "detailsUrl": "https://github.com/o/r/actions/runs/5/job/%d" % ident,
    }


RUNNING = [check_run("quality", "IN_PROGRESS"), check_run("CI Complete", "QUEUED", None, 2)]
RED = [check_run("quality", "COMPLETED", "FAILURE"), check_run("build", "IN_PROGRESS", None, 3)]
GREEN = [
    check_run("quality", "COMPLETED", "SUCCESS"),
    check_run("CI Complete", "COMPLETED", "SUCCESS", 2),
]


def plant_cistate(worklist, session, contexts, sha="a" * 40):
    wl_ci.cistate_path(worklist, session).write_text(
        json.dumps(
            {
                "sha": sha,
                "at": 1.0,
                "state": "ok",
                "info": {"contexts": contexts, "sha": sha, "pr": 5},
                "steps": {},
                "final": False,
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def held(repo, tmp_path, monkeypatch):
    """The repo with one local commit and a worklist path for the cache."""
    root, _ = repo
    commit(root, "src/b.py")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    return root, C.worklist_for(root), "cafef00d-1"


def test_ci_hold_fires_on_running_with_local_commits(held):
    root, worklist, session = held
    plant_cistate(worklist, session, RUNNING)
    assert L.ci_hold(root, worklist, session) == ("aaaaaaaa", 1)


def test_ci_hold_is_silent_on_red_green_and_no_local_commits(held):
    root, worklist, session = held
    plant_cistate(worklist, session, RED)
    assert L.ci_hold(root, worklist, session) is None, "a red pushes at once"
    plant_cistate(worklist, session, GREEN)
    assert L.ci_hold(root, worklist, session) is None, "a settled run holds nothing"
    plant_cistate(worklist, session, RUNNING)
    git(root, "push", "-q", "origin", "topic")
    assert L.ci_hold(root, worklist, session) is None, "no local commit, nothing to hold"


def test_ci_hold_is_silent_without_a_cache_or_on_a_damaged_one(held):
    root, worklist, session = held
    assert L.ci_hold(root, worklist, session) is None
    wl_ci.cistate_path(worklist, session).write_text("garbage", encoding="utf-8")
    assert L.ci_hold(root, worklist, session) is None
    wl_ci.cistate_path(worklist, session).write_text("[]", encoding="utf-8")
    assert L.ci_hold(root, worklist, session) is None


# ---- the post-bash member -----------------------------------------------------


def load_member():
    spec = importlib.util.spec_from_file_location(
        "loop_speed_member", HOOKS / "post-bash" / "loop_speed_note.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_member(command, root, session="cafef00d-1"):
    out = io.StringIO()
    payload = {
        "session_id": session,
        "cwd": str(root),
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    rc = load_member().main(stdin=io.StringIO(json.dumps(payload)), stdout=out)
    return rc, out.getvalue()


@pytest.mark.parametrize(
    "command",
    [
        "npm run ci:quick",
        "npm run -s ci:quick",
        "cd x && npm run ci:quick",
        "npx tsx scripts/ci-runner/run.ts --quick",
        "npm run ci:prepush",
    ],
)
def test_receipt_commands_earn_the_early_receipt_note(command, held, monkeypatch):
    root, *_ = held
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    rc, out = run_member(command, root)
    assert rc == 0
    doc = json.loads(out)
    assert doc["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert doc["hookSpecificOutput"]["additionalContext"] == M.N_RECEIPT_EARLY


@pytest.mark.parametrize(
    "command",
    [
        "ls scripts/ci-runner/",
        "grep ci:quick package.json",
        "echo npm run ci:quick",
        "git status",
        "npm run ci",
        "cat .ci/cache/prepush-receipt.json",
    ],
)
def test_commands_that_only_mention_a_receipt_are_silent(command, held, monkeypatch):
    root, *_ = held
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    assert run_member(command, root) == (0, "")


def test_push_with_a_running_run_and_local_commits_holds(held, monkeypatch):
    root, worklist, session = held
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    plant_cistate(worklist, session, RUNNING)
    rc, out = run_member("git push origin topic", root, session)
    assert rc == 0
    text = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert text == M.N_CI_HOLD % ("aaaaaaaa", 1)


def test_push_that_landed_while_a_run_was_in_progress_says_so(held, monkeypatch):
    root, worklist, session = held
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    plant_cistate(worklist, session, RUNNING)
    git(root, "push", "-q", "origin", "topic")
    _, out = run_member("git push", root, session)
    assert (
        json.loads(out)["hookSpecificOutput"]["additionalContext"]
        == M.N_CI_HOLD_PUSHED % "aaaaaaaa"
    )


def test_push_is_silent_for_red_green_and_an_empty_cache(held, monkeypatch):
    root, worklist, session = held
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    assert run_member("git push", root, session) == (0, "")
    for contexts in (RED, GREEN):
        plant_cistate(worklist, session, contexts)
        assert run_member("git push", root, session) == (0, ""), contexts


def test_a_push_mention_is_silent_and_the_member_never_fails(held, monkeypatch):
    root, worklist, session = held
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    plant_cistate(worklist, session, RUNNING)
    assert run_member("echo git push", root, session) == (0, "")
    assert run_member("git log --oneline | grep push", root, session) == (0, "")
    member = load_member()
    for raw in ("", "not json", "[]", "null", json.dumps({"tool_input": "x"})):
        assert member.main(stdin=io.StringIO(raw), stdout=io.StringIO()) == 0


def test_the_member_stays_silent_inside_a_reviewer_child(held, monkeypatch):
    root, *_ = held
    monkeypatch.setenv("COMMIT_REVIEW_CHILD", "1")
    assert run_member("npm run ci:quick", root) == (0, "")


# ---- advisory, never blocking: the Stop wiring ----------------------------------


def test_receipt_behind_and_ci_hold_ride_the_allow_queue_only():
    source = (STOP_DIR / "wl_checks.py").read_text(encoding="utf-8")
    for key, text in (("receipt-behind", "N_RECEIPT_BEHIND"), ("ci-hold", "N_CI_HOLD")):
        assert 'vadd("%s"' % key not in source
        assert re.search(r'"%s",\s*M\.%s %%' % (key, text), source), key
    for key in ("receipt-behind", "ci-hold"):
        assert wl_standdown.advisory_kept(key)
        assert key not in wl_standdown.CORE


def test_the_member_and_engine_run_no_mutating_git_verb():
    for rel in ("stop/wl_loopspeed.py", "post-bash/loop_speed_note.py"):
        source = (HOOKS / rel).read_text(encoding="utf-8")
        verbs = set(re.findall(r'_git\(\s*\w+,\s*"([a-z-]+)"', source))
        assert verbs <= {"show", "rev-parse", "rev-list", "log"}, (rel, verbs)


def test_a_full_stop_run_carries_receipt_behind_and_still_allows(tmp_path):
    wl = wlfix.Fixture(tmp_path / "fx")
    wl.setup()
    proj = wl.proj
    shutil.rmtree(proj / ".git")
    origin = tmp_path / "o.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    git(proj, "init", "-q", "-b", "topic")
    git(proj, "config", "user.email", "t@example.invalid")
    git(proj, "config", "user.name", "t")
    commit(proj, L.RECORD_POLICY_REL, json.dumps(POLICY))
    base = commit(proj, "src/a.py")
    git(proj, "remote", "add", "origin", str(origin))
    git(proj, "push", "-q", "origin", "topic")
    (proj / L.RECEIPT_REL).parent.mkdir(parents=True, exist_ok=True)
    (proj / L.RECEIPT_REL).write_text(json.dumps({"head": base}), encoding="utf-8")
    commit(proj, "src/b.py")
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    got = wl.run()
    assert got.rc == 0, got.out[:400] + got.err[:400]
    assert "behind HEAD" in got.out, got.out[:600] + got.err[:300]
    assert '"decision"' not in got.out
    assert "Do not stop yet" not in got.out
