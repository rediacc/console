"""`--tick` names the commit, or why there is none (agent/plans/PLAN-commit-as-you-go.md section 3.4, box T6).

Verified work is committed before its item is ticked (CLAUDE.md rule 1). The tick evidence therefore carries `commit:<sha>`, a commit reachable from HEAD in the console or a submodule, or `nocommit:<no-tracked-change|research|operator-deferred>`. Anything else is refused under the key `no-commit-ref` and logged. The rule is the tick's alone: `--update` keeps free text.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_tick_evidence_shapes import lead_transcript, plant_ask


def added(fix, text: str = "(deadbeef) the commit-ref item") -> str:
    got = fix.cli("--add", wlfix.ME, text)
    found = re.search(r"#([0-9a-f]+)", got.out)
    assert found, got.out[:200]
    return found.group(1)


def head(repo) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), check=True, capture_output=True, text=True
    ).stdout.strip()


def last_refusal(fix) -> dict:
    log = fix.stem(".tick-refusals-deadbeef.jsonl")
    assert log.is_file(), "the refusal was not logged"
    return json.loads(log.read_text(encoding="utf-8").splitlines()[-1])


def state_of(fix, item: str) -> str:
    got = fix.cli("--list", "--open", wlfix.ME)
    return "open" if ("#%s" % item) in got.out else "closed"


def test_t6_a_commit_on_head_ticks(wl):
    wl.reg_repo()
    item = added(wl)
    sha = head(wl.proj)
    got = wl.cli("--tick", wlfix.ME, item, "commit:%s pytest rc=0" % sha[:10])
    assert got.rc == 0, got.err[:400]
    assert state_of(wl, item) == "closed"


def test_t6_each_nocommit_reason_ticks(wl):
    wl.reg_repo()
    for reason in ("no-tracked-change", "research", "operator-deferred"):
        item = added(wl, "(deadbeef) a %s item" % reason)
        got = wl.cli("--tick", wlfix.ME, item, "nocommit:%s probe rc=0" % reason)
        assert got.rc == 0, (reason, got.err[:400])


def test_t6_a_named_door_stands_in_for_the_reason(wl):
    """A last-resort door already says why nothing was committed (CLAUDE.md rule 2)."""
    wl.reg_repo()
    item = added(wl)
    got = wl.cli(
        "--tick",
        wlfix.ME,
        item,
        "https://github.com/x/y/issues/9 door:no-write-access, that repo is not writable here",
    )
    assert got.rc == 0, got.err[:400]


def test_t6_a_submodule_commit_ticks(wl):
    """A commit in a submodule is reachable from the submodule's HEAD, never the console's."""
    wl.reg_repo()
    sub = wl.proj / "private" / "sub"
    sub.mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@t"), ("config", "user.name", "t")):
        subprocess.run(["git", *args], cwd=str(sub), check=True, capture_output=True)
    (sub / "f.txt").write_text("sub\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(sub), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "c"], cwd=str(sub), check=True, capture_output=True)
    (wl.proj / ".gitmodules").write_text(
        '[submodule "private/sub"]\n\tpath = private/sub\n\turl = x\n', encoding="utf-8"
    )
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "commit:%s" % head(sub))
    assert got.rc == 0, got.err[:400]


def test_t6_inverse_free_text_evidence_is_refused_and_logged(wl):
    """The pre-T6 shape: real evidence, no commit ref."""
    wl.reg_repo()
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "pytest rc=0, 12 passed")
    assert got.rc != 0, got.out[:300]
    assert "names no commit" in got.err, got.err[:400]
    assert "commit:<sha>" in got.err, got.err[:400]
    assert "nocommit:<reason>" in got.err, got.err[:400]
    assert last_refusal(wl)["why"] == "no-commit-ref"
    assert state_of(wl, item) == "open"


def test_t6_inverse_a_fabricated_sha_is_refused(wl):
    wl.reg_repo()
    item = added(wl)
    fake = "0123456789abcdef0123456789abcdef01234567"
    got = wl.cli("--tick", wlfix.ME, item, "commit:%s rc=0" % fake)
    assert got.rc != 0, got.out[:300]
    assert "commit:%s is not a commit reachable from HEAD" % fake in got.err, got.err[:400]
    assert last_refusal(wl)["why"] == "no-commit-ref"


def test_t6_inverse_a_real_commit_off_this_branch_is_refused(wl):
    """A real object that HEAD does not reach: committed on another branch of the fixture repo."""
    wl.reg_repo()
    base = wl.git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    wl.git("checkout", "-q", "-b", "elsewhere")
    (wl.proj / "other.txt").write_text("x\n", encoding="utf-8")
    wl.git("add", "-A")
    wl.git("commit", "-qm", "elsewhere")
    off = head(wl.proj)
    wl.git("checkout", "-q", base)
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "commit:%s rc=0" % off)
    assert got.rc != 0, got.out[:300]
    assert last_refusal(wl)["why"] == "no-commit-ref"


def test_t6_inverse_a_real_sha_beside_a_fabricated_one_is_refused(wl):
    wl.reg_repo()
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "commit:%s commit:%s" % (head(wl.proj), "deadbee1234"))
    assert got.rc != 0, got.out[:300]


def test_t6_inverse_an_unknown_nocommit_reason_is_refused(wl):
    wl.reg_repo()
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "nocommit:later rc=0")
    assert got.rc != 0, got.out[:300]
    assert "nocommit:later is not one of the three reasons" in got.err, got.err[:400]


def test_t6_update_keeps_free_text(wl):
    """The rule binds the tick only: progress notes need no commit."""
    item = added(wl)
    got = wl.cli("--update", wlfix.ME, item, "half done, tests next")
    assert got.rc == 0, got.err[:400]


def test_t6_mutation_accepting_bare_evidence_flips_the_refusal(wl):
    """CONTROL: with the check planted to accept anything, the inverse case ticks. Proves the refusal above is this check's and not an incidental one."""
    wl.reg_repo()
    hooks = wl.base / "hooks"
    shutil.copytree(wlfix.STOP_DIR, hooks / "stop", ignore=shutil.ignore_patterns("__pycache__"))
    path = hooks / "stop" / "wl_cli.py"
    src = path.read_text(encoding="utf-8")
    old = "        bad = commit_ref_problem(root, rest, transcript)\n"
    assert src.count(old) == 1, "MUTATION FIXTURE BROKEN"
    path.write_text(src.replace(old, "        bad = None\n"), encoding="utf-8")
    wl.hook = hooks / "stop" / "worklist.py"
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "pytest rc=0, 12 passed")
    assert got.rc == 0, "the mutated hook still refused: %s" % got.err[:300]


def _digit_head(repo) -> str:
    """Re-date HEAD until its 9-character abbreviation is all digits (about 1 in 69 shas are), and return the sha. Deterministic per tree; the cap is a test bug, never a pass."""
    for i in range(5000):
        sha = head(repo)
        if sha[:9].isdigit():
            return sha
        when = "@%d +0000" % (1767225600 + i)
        subprocess.run(
            ["git", "commit", "-q", "--amend", "--allow-empty", "-m", "chore: base"],
            cwd=str(repo),
            check=True,
            capture_output=True,
            env={**wlfix.scrubbed_environ(), "GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when},
        )
    raise AssertionError("no all-digit 9-char prefix in 5000 re-dates")


def test_t6_an_all_digit_commit_ref_is_recorded_lengthened(wl):
    """#0241c97d. `commit:<sha9>` whose nine characters are all digits ticks, and the evidence is RECORDED lengthened until it carries a letter, so a reader that skips digit runs (plan_lifecycle --move) still sees it. Red before the fix: the bare nine digits were stored."""
    wl.reg_repo()
    sha = _digit_head(wl.proj)
    want = next(sha[:n] for n in range(10, 41) if not sha[:n].isdigit())
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "commit:%s pytest rc=0" % sha[:9])
    assert got.rc == 0, got.err[:400]
    events = wl.wl_events()
    assert "commit:%s pytest rc=0" % want in events, events[-600:]
    assert "commit:%s pytest" % sha[:9] not in events, "the bare all-digit sha9 was recorded"


def test_t6_inverse_an_all_digit_ref_nothing_resolves_is_refused_as_typed(wl):
    """CONTROL: lengthening needs a commit to lengthen along; a digit ref that names none is refused, and the refusal names the token as typed."""
    wl.reg_repo()
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "commit:123456789 pytest rc=0")
    assert got.rc != 0, got.out[:300]
    assert "commit:123456789 is not a commit reachable from HEAD" in got.err, got.err[:400]


def test_t6_a_letter_bearing_ref_is_recorded_as_typed(wl):
    """CONTROL: only all-digit refs are rewritten."""
    wl.reg_repo()
    sha = head(wl.proj)
    short = next(sha[:n] for n in range(9, 41) if not sha[:n].isdigit())
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "commit:%s pytest rc=0" % short)
    assert got.rc == 0, got.err[:400]
    assert "commit:%s pytest rc=0" % short in wl.wl_events()


# ---- R20261101.1: both gates answer in one refusal ----------------------------------------------


def test_r1_a_bare_claim_is_refused_naming_both_gates_and_ends_with_both_forms(wl):
    """The 2026-11-01 shape: no evidence and no commit ref, refused one gate at a time. Now one refusal names both, and the LAST line carries the two forms."""
    wl.reg_repo()
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "nocommit:read-only cause found by journal")
    assert got.rc != 0, got.out[:300]
    assert "needs evidence in the line" in got.err, got.err[:600]
    assert "Also unmet: the evidence names no commit" in got.err, got.err[:600]
    assert "nocommit:read-only is not one of the three reasons" in got.err, got.err[:600]
    last = got.err.strip().splitlines()[-1]
    assert "commit:<sha>" in last, last
    assert "nocommit:no-tracked-change|research|operator-deferred" in last, last
    row = last_refusal(wl)
    assert row["why"] == "no-evidence", row
    assert row["also"] == ["no-commit-ref"], row
    assert state_of(wl, item) == "open"


def test_r1_evidence_only_refusal_ends_with_both_forms_and_has_no_also(wl):
    wl.reg_repo()
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "done, works nocommit:research")
    assert got.rc != 0, got.out[:300]
    assert "Also unmet" not in got.err, got.err[:600]
    last = got.err.strip().splitlines()[-1]
    assert "nocommit:no-tracked-change|research|operator-deferred" in last, last
    # Review f71f0506.2: the retry line names the same path as the commit-reference refusal.
    assert last.lstrip().startswith(".claude/hooks/stop/worklist.py --tick <me>"), last
    assert "also" not in last_refusal(wl)


def test_r1_commit_only_refusal_ends_with_both_forms(wl):
    wl.reg_repo()
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "pytest rc=0, 12 passed")
    assert got.rc != 0, got.out[:300]
    last = got.err.strip().splitlines()[-1]
    assert "commit:<sha>" in last, last
    assert "nocommit:no-tracked-change|research|operator-deferred" in last, last


# ---- R20261101.2: a verified ASKED stands in for the commit reference ---------------------------


def test_r2_a_verified_asked_stands_in_for_the_commit_ref(wl):
    wl.reg_repo()
    minute = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() - 3600))
    plant_ask(wl, time.strftime("%Y-%m-%dT%H:%M:40.000Z", time.gmtime(time.time() - 3600)))
    item = added(wl)
    got = wl.cli(
        "--tick", wlfix.ME, item, "operator decided, work tracked elsewhere ASKED:%s" % minute
    )
    assert got.rc == 0, got.err[:400]
    assert state_of(wl, item) == "closed"


def test_r2_inverse_an_unmatched_asked_still_fails(wl):
    wl.reg_repo()
    lead_transcript(wl).write_text("", encoding="utf-8")
    minute = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() - 3600))
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "operator decided ASKED:%s" % minute)
    assert got.rc != 0, got.out[:300]
    assert state_of(wl, item) == "open"


def test_r2_inverse_a_verified_asked_does_not_excuse_a_bad_nocommit_word(wl):
    wl.reg_repo()
    minute = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() - 3600))
    plant_ask(wl, time.strftime("%Y-%m-%dT%H:%M:40.000Z", time.gmtime(time.time() - 3600)))
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "nocommit:operator decided ASKED:%s" % minute)
    assert got.rc != 0, got.out[:300]
    assert "nocommit:operator is not one of the three reasons" in got.err, got.err[:400]


def test_r1_an_issue_without_a_door_and_without_a_commit_names_both(wl):
    """Review 7860756f.1: the door refusal fired before the commit gate ran, so an issue link with no door and no commit named only the door."""
    wl.reg_repo()
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "filed https://github.com/x/y/issues/9 for the rest")
    assert got.rc != 0, got.out[:300]
    assert "Also unmet: the evidence names no commit" in got.err, got.err[:600]
    last = got.err.strip().splitlines()[-1]
    assert "commit:<sha>" in last, last
    row = last_refusal(wl)
    assert row["why"] == "issue-without-door", row
    assert row["also"] == ["no-commit-ref"], row
    assert state_of(wl, item) == "open"


def test_r1_control_an_issue_beside_a_commit_ticks(wl):
    """CONTROL: a commit makes the evidence more than an issue link, so neither gate refuses."""
    wl.reg_repo()
    item = added(wl)
    got = wl.cli(
        "--tick",
        wlfix.ME,
        item,
        "filed https://github.com/x/y/issues/9 commit:%s" % head(wl.proj)[:10],
    )
    assert got.rc == 0, got.err[:400]
    assert state_of(wl, item) == "closed"


# ---- R20261123.6: a commit landed elsewhere, or landed as a copy, is a real commit ---------------


def _commit(fix, rel: str, text: str, message: str = "c") -> str:
    (fix.proj / rel).write_text(text, encoding="utf-8")
    fix.git("add", "--", rel)
    done = fix.git("commit", "-qm", message)
    assert done.returncode == 0, done.stderr[:300]
    return head(fix.proj)


def _side_commit(fix, rel: str, text: str) -> str:
    """A commit on a throwaway branch, then back on the starting branch: real, and no ancestor of HEAD."""
    base = fix.git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    done = fix.git("checkout", "-q", "-b", "side-%s" % rel.replace(".", "-"))
    assert done.returncode == 0, done.stderr[:300]
    sha = _commit(fix, rel, text)
    fix.git("checkout", "-q", base)
    assert head(fix.proj) != sha
    return sha


def _landing_tree(fix, branch: str = "1104-1"):
    """A linked tree on `branch` holding one commit HEAD does not, as `./run.sh worktree landing` leaves it."""
    land = fix.base / "landing"
    done = fix.git("worktree", "add", "-q", "-b", branch, str(land), "HEAD")
    assert done.returncode == 0, done.stderr[:300]
    (land / "landed.txt").write_text("l\n", encoding="utf-8")
    for args in (("add", "--", "landed.txt"), ("commit", "-qm", "landing work")):
        subprocess.run(["git", *args], cwd=str(land), check=True, capture_output=True)
    return land, head(land)


def _tick_commit(fix, sha: str):
    item = added(fix)
    return item, fix.cli("--tick", wlfix.ME, item, "commit:%s pytest rc=0" % sha)


def test_r6_a_landing_only_commit_ticks(wl):
    """#876420de: a commit in the landing tree, on the landing record's branch, not yet on HEAD."""
    wl.reg_repo()
    land, sha = _landing_tree(wl)
    (wl.proj / ".git" / "rediacc-landing.json").write_text(
        json.dumps({"branch": "1104-1", "path": str(land)}), encoding="utf-8"
    )
    item, got = _tick_commit(wl, sha)
    assert got.rc == 0, got.err[:400]
    assert state_of(wl, item) == "closed"


def test_r6_inverse_a_landing_commit_with_no_landing_record_is_refused(wl):
    """CONTROL: the same branch with no landing record binding it accepts nothing."""
    wl.reg_repo()
    _land, sha = _landing_tree(wl)
    _item, got = _tick_commit(wl, sha)
    assert got.rc != 0, got.out[:300]
    assert last_refusal(wl)["why"] == "no-commit-ref"


def test_r6_a_main_only_hotfix_ticks(wl):
    """#9a4823c8: the operator's hotfix on origin/main, which the development branch does not hold."""
    wl.reg_repo()
    sha = _side_commit(wl, "hotfix.txt", "h\n")
    wl.git("update-ref", "refs/remotes/origin/main", sha)
    item, got = _tick_commit(wl, sha)
    assert got.rc == 0, got.err[:400]
    assert state_of(wl, item) == "closed"


def test_r6_a_pre_rebase_commit_ticks_by_its_patch_equivalent(wl):
    """#b07162cf: the sha a rebase rewrote; HEAD holds the same patch under a new sha."""
    wl.reg_repo()
    old = _side_commit(wl, "rebased.txt", "r\n")
    _commit(wl, "unrelated.txt", "u\n")
    done = wl.git("cherry-pick", old)
    assert done.returncode == 0, done.stderr[:300]
    assert head(wl.proj) != old
    item, got = _tick_commit(wl, old)
    assert got.rc == 0, got.err[:400]
    assert state_of(wl, item) == "closed"


def test_r6_a_commit_named_by_a_cherry_picked_line_on_head_ticks(wl):
    """A pick resolved by hand differs in patch, so only its `-x` line names the original."""
    wl.reg_repo()
    _commit(wl, "a.txt", "base\n")
    old = _side_commit(wl, "a.txt", "lease\n")
    _commit(wl, "a.txt", "other\n")
    _commit(wl, "a.txt", "resolved\n", "pick\n\n(cherry picked from commit %s)" % old)
    item, got = _tick_commit(wl, old)
    assert got.rc == 0, got.err[:400]
    assert state_of(wl, item) == "closed"


def test_r6_inverse_a_line_naming_another_sha_lands_nothing(wl):
    """CONTROL: the `-x` line must name THIS commit; a resolved pick of a different patch is still refused."""
    wl.reg_repo()
    _commit(wl, "a.txt", "base\n")
    old = _side_commit(wl, "a.txt", "lease\n")
    _commit(wl, "a.txt", "other\n", "pick\n\n(cherry picked from commit %s)" % ("f" * 40))
    _item, got = _tick_commit(wl, old)
    assert got.rc != 0, got.out[:300]
    assert "commit:%s is not a commit reachable from HEAD" % old in got.err, got.err[:400]


def test_r6_inverse_a_random_sha_still_fails_with_every_route_present(wl):
    """CONTROL: origin/main, a landing branch and a `-x` line all exist, and a random 40-hex sha still fails."""
    wl.reg_repo()
    wl.git("update-ref", "refs/remotes/origin/main", _side_commit(wl, "hotfix.txt", "h\n"))
    land, _sha = _landing_tree(wl)
    (wl.proj / ".git" / "rediacc-landing.json").write_text(
        json.dumps({"branch": "1104-1", "path": str(land)}), encoding="utf-8"
    )
    _commit(wl, "x.txt", "x\n", "pick\n\n(cherry picked from commit %s)" % ("e" * 40))
    fake = "3c1f9a0e7b2d4c6a8e0f1b3d5c7a9e1f2b4d6c8a"
    _item, got = _tick_commit(wl, fake)
    assert got.rc != 0, got.out[:300]
    assert "commit:%s is not a commit reachable from HEAD" % fake in got.err, got.err[:400]
    assert last_refusal(wl)["why"] == "no-commit-ref"


def test_r6_a_probe_that_cannot_run_is_named_never_read_as_absent(wl):
    """A ref git lists but cannot walk (origin/main naming a missing object): the check refuses and names the failed probe, rather than reading the failure as `not landed` or folding it into a pass."""
    wl.reg_repo()
    off = _side_commit(wl, "off.txt", "o\n")
    ref = wl.proj / ".git" / "refs" / "remotes" / "origin" / "main"
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text("%s\n" % ("1" * 40), encoding="utf-8")
    item, got = _tick_commit(wl, off)
    assert got.rc != 0, got.out[:300]
    assert "could not be checked" in got.err, got.err[:600]
    assert "refs/remotes/origin/main" in got.err, got.err[:600]
    assert last_refusal(wl)["why"] == "no-commit-ref"
    assert state_of(wl, item) == "open"


class _FakeGit:
    """A run_git that answers rev-parse with a sha, show-ref with 1 (no extra ref) and merge-base with `ancestor_rc`."""

    def __init__(self, ancestor_rc: int, ancestor_err: str = ""):
        self.ancestor_rc, self.ancestor_err = ancestor_rc, ancestor_err

    def run_git(self, argv, **_kw):
        if argv[0] == "rev-parse":
            return 0, "a" * 40, ""
        if argv[0] == "show-ref":
            return 1, "", ""
        if argv[0] == "merge-base":
            return self.ancestor_rc, "", self.ancestor_err
        return 0, "", ""


def test_r6_a_failed_ancestry_probe_names_its_exit_code_and_stderr():
    """26dc7587.1: the refusal names the git call, the repo, the exit code and stderr, like every other probe; exit 0 is a landed answer."""
    cli = wlfix.import_wl("wl_cli")
    landed, why = cli._commit_ref_landed(_FakeGit(128, "fatal: bad object"), "/r", "aaaa", "")
    assert landed is False
    assert "exited 128: fatal: bad object" in why
    assert "merge-base --is-ancestor" in why
    assert cli._commit_ref_landed(_FakeGit(0), "/r", "aaaa", "") == (True, "")
