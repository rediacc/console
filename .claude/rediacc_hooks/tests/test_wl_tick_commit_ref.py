"""`--tick` names the commit, or why there is none (agent/plans/PLAN-commit-as-you-go.md section 3.4, box T6).

Verified work is committed before its item is ticked (CLAUDE.md rule 1). The tick evidence therefore carries `commit:<sha>`, a commit reachable from HEAD in the console or a submodule, or `nocommit:<no-tracked-change|research|operator-deferred>`. Anything else is refused under the key `no-commit-ref` and logged. The rule is the tick's alone: `--update` keeps free text.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401


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


def test_t6_a_commit_on_head_ticks(wl):  # noqa: F811
    wl.reg_repo()
    item = added(wl)
    sha = head(wl.proj)
    got = wl.cli("--tick", wlfix.ME, item, "commit:%s pytest rc=0" % sha[:10])
    assert got.rc == 0, got.err[:400]
    assert state_of(wl, item) == "closed"


def test_t6_each_nocommit_reason_ticks(wl):  # noqa: F811
    wl.reg_repo()
    for reason in ("no-tracked-change", "research", "operator-deferred"):
        item = added(wl, "(deadbeef) a %s item" % reason)
        got = wl.cli("--tick", wlfix.ME, item, "nocommit:%s probe rc=0" % reason)
        assert got.rc == 0, (reason, got.err[:400])


def test_t6_a_named_door_stands_in_for_the_reason(wl):  # noqa: F811
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


def test_t6_a_submodule_commit_ticks(wl):  # noqa: F811
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


def test_t6_inverse_free_text_evidence_is_refused_and_logged(wl):  # noqa: F811
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


def test_t6_inverse_a_fabricated_sha_is_refused(wl):  # noqa: F811
    wl.reg_repo()
    item = added(wl)
    fake = "0123456789abcdef0123456789abcdef01234567"
    got = wl.cli("--tick", wlfix.ME, item, "commit:%s rc=0" % fake)
    assert got.rc != 0, got.out[:300]
    assert "commit:%s is not a commit reachable from HEAD" % fake in got.err, got.err[:400]
    assert last_refusal(wl)["why"] == "no-commit-ref"


def test_t6_inverse_a_real_commit_off_this_branch_is_refused(wl):  # noqa: F811
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


def test_t6_inverse_a_real_sha_beside_a_fabricated_one_is_refused(wl):  # noqa: F811
    wl.reg_repo()
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "commit:%s commit:%s" % (head(wl.proj), "deadbee1234"))
    assert got.rc != 0, got.out[:300]


def test_t6_inverse_an_unknown_nocommit_reason_is_refused(wl):  # noqa: F811
    wl.reg_repo()
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "nocommit:later rc=0")
    assert got.rc != 0, got.out[:300]
    assert "nocommit:later is not one of the three reasons" in got.err, got.err[:400]


def test_t6_update_keeps_free_text(wl):  # noqa: F811
    """The rule binds the tick only: progress notes need no commit."""
    item = added(wl)
    got = wl.cli("--update", wlfix.ME, item, "half done, tests next")
    assert got.rc == 0, got.err[:400]


def test_t6_mutation_accepting_bare_evidence_flips_the_refusal(wl):  # noqa: F811
    """CONTROL: with the check planted to accept anything, the inverse case ticks. Proves the refusal above is this check's and not an incidental one."""
    wl.reg_repo()
    hooks = wl.base / "hooks"
    shutil.copytree(wlfix.STOP_DIR, hooks / "stop", ignore=shutil.ignore_patterns("__pycache__"))
    path = hooks / "stop" / "worklist.py"
    src = path.read_text(encoding="utf-8")
    old = "        bad = commit_ref_problem(root, rest)\n"
    assert src.count(old) == 1, "MUTATION FIXTURE BROKEN"
    path.write_text(src.replace(old, "        bad = None\n"), encoding="utf-8")
    wl.hook = path
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "pytest rc=0, 12 passed")
    assert got.rc == 0, "the mutated hook still refused: %s" % got.err[:300]
