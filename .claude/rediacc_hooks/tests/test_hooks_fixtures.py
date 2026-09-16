"""The cases that need a FIXTURE: a temp repo, a stubbed `gh`, an exported root.

Everything that could be data is in hookcases.STATIC. What is left is here because
the guard's subject is not the command string: it is the state of a git index, the
answer a `gh` call gives, or whether a file exists. Each block builds exactly what
its guard reads and tears it down again.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_hooks.tests import hookblocks, hookcases

bash_json = hookcases.bash_json
tool_json = hookcases.tool_json
env_with = hookblocks.env_with
HOOKS = hookcases.HOOKS
ROOT = hookcases.ROOT
GUARD_DISPATCH = hookcases.GUARD_DISPATCH


def git(directory, *args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(directory), *args],
        capture_output=True,
        check=False,
        stdin=subprocess.DEVNULL,
        timeout=300,
        **kwargs,
    )


def stub_gh(directory, body: str, code: int) -> pathlib.Path:
    """A directory holding a fake `gh`, to prepend to PATH."""
    directory.mkdir(parents=True, exist_ok=True)
    fake = directory / "gh"
    fake.write_text(
        "#!/usr/bin/env bash\ncat <<'GHEOF'\n%s\nGHEOF\nexit %d\n" % (body, code), encoding="utf-8"
    )
    fake.chmod(0o755)
    return directory


def path_env(*prefixes) -> dict:
    return env_with(PATH=os.pathsep.join([str(p) for p in prefixes] + [os.environ["PATH"]]))


# --- block_raw_pr_body_edit: the body-file arms need real files ---------------
# The PR body is generated, so a hand-written whole-body write silently drops the
# worklist-epics block and CI fails minutes later naming nothing useful. The CREATE
# arm cannot insist on being a whole-body write -- there is no block yet to destroy --
# so a body already carrying the block passes and only a blockless one is refused.
EPIC_MARK = "<!-- worklist-epics:begin -->"


@pytest.mark.xdist_group("hooks-fixtures")
def test_block_raw_pr_body_edit_body_files(tmp_path):
    block = hookblocks.Block("raw-pr-body")
    with_md = tmp_path / "with.md"
    with_md.write_text(
        "prose\n\n%s\n- epic\n<!-- worklist-epics:end -->\n" % EPIC_MARK, encoding="utf-8"
    )
    without_md = tmp_path / "without.md"
    without_md.write_text("prose only\n", encoding="utf-8")
    absent = tmp_path / "absent.md"
    block.check(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json("gh pr create --draft --body-file %s" % without_md),
        "raw-pr-body: CREATE --body-file with no epic block is refused (was allowed)",
    )
    block.check(
        "check 0 guards/block_raw_pr_body_edit.py",
        bash_json("gh pr create --draft --body-file %s" % with_md),
        "raw-pr-body CONTROL: CREATE --body-file that ALREADY carries the block passes",
    )
    block.check(
        "check 0 guards/block_raw_pr_body_edit.py",
        bash_json("gh pr create --draft --body-file %s" % absent),
        "raw-pr-body CONTROL: an unreadable --body-file is ALLOWED, not refused blind",
    )
    block.check(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json("gh pr edit 42 --body-file %s" % with_md),
        "raw-pr-body: EDIT is refused even WITH the block -- it rewrites the whole body",
    )
    # ONE COMMAND CAN DO BOTH, and reading the flags line-wide gets the scope wrong in
    # both directions. hook_gh_pr_segment exists for exactly this; the first draft of
    # the create arm did not use it, so a legal `create --body <with the block> && edit
    # --add-label x` was refused for the edit's sake.
    block.check(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json("gh pr create --draft --fill && gh pr edit 42 --body-file %s" % with_md),
        "raw-pr-body: a create beside it does not let a raw EDIT through",
    )
    # THE SANCTIONED FORM IS A WHOLE-BODY WRITE TOO. Found 2026-09-04 while babysitting
    # #585: this guard's message prescribed `gh pr edit --body-file`,
    # block-adhoc-sanctioned.sh refused that and prescribed the `gh api ... -X PATCH -F
    # body=@file` form, and that form had no marker check at all.
    both = tmp_path / "both.md"
    both.write_text(
        "prose\n\n%s\n- epic\n<!-- worklist-epics:end -->\n"
        "<!-- pushed-head:begin -->\nhead\n<!-- pushed-head:end -->\n" % EPIC_MARK,
        encoding="utf-8",
    )
    patch = "gh api repos/o/r/pulls/42 -X PATCH -F body=@%s"
    block.check(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json(patch % without_md),
        "raw-pr-body: PATCH -F body=@file with no block is refused (was allowed)",
    )
    block.check(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json(patch % with_md),
        "raw-pr-body: PATCH carrying ONLY the epic block still drops pushed-head",
    )
    block.check(
        "check 0 guards/block_raw_pr_body_edit.py",
        bash_json(patch % both),
        "raw-pr-body CONTROL: PATCH whose file carries EVERY generated marker passes",
    )
    block.check(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json(patch % absent),
        "raw-pr-body: PATCH with an unreadable body file is refused, not trusted",
    )
    block.done()


# --- block_unlinked_commit_author: the identity has to come from the fixture ---
# THE CONFIG WAS NOT THE CAUSE -- the checkout's only user.email source was the
# correct one -- so every BLOCK case below is an OVERRIDE path. A guard that read
# `git config` alone would have watched all 30 go past.
#
# The fixture cache must contain the REAL resolved author, or every case blocks --
# including the ALLOW ones, which is how the first draft of this block failed.
#
# AND THE IDENTITY ITSELF, because borrowing the machine's is what broke in CI: a
# GitHub runner has no global user.email and actions/checkout does not set one, so
# `git var` resolves nothing, the guard correctly refuses a commit it cannot
# attribute, and the prose CONTROL went red for a reason that has nothing to do with
# what it asserts. Measured 2026-09-03, job 100727875171.
#
# AS CONFIG, NOT AS GIT_AUTHOR_EMAIL, and that distinction is the whole trick: git
# resolves GIT_AUTHOR_EMAIL with HIGHER precedence than user.email, so exporting it
# masked the `-c user.email=bad@...` case -- the guard resolved the good address and
# permitted the very override it exists to refuse. A global config file sits BELOW
# every override the refuse cases use, which is exactly where an ambient identity
# belongs.
@pytest.mark.xdist_group("hooks-fixtures")
def test_block_unlinked_commit_author(tmp_path):
    block = hookblocks.Block("unlinked-author")
    identity = tmp_path / "identity.json"
    identity.write_text(
        '{"format":1,"identities":[{"login":"ctl","id":1,"emails":["good@example.com"]}]}\n',
        encoding="utf-8",
    )
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = ctl\n\temail = good@example.com\n", encoding="utf-8")
    env = env_with(COMMIT_IDENTITY_FILE=str(identity), GIT_CONFIG_GLOBAL=str(gitconfig))
    block.check(
        "check 2 guards/block_unlinked_commit_author.py",
        bash_json("git -c user.email=bad@example.com commit -m x"),
        "unlinked-author: -c user.email override is refused",
        env=env,
    )
    block.check(
        "check 2 guards/block_unlinked_commit_author.py",
        bash_json("GIT_AUTHOR_EMAIL=bad@example.com git commit -m x"),
        "unlinked-author: GIT_AUTHOR_EMAIL override is refused",
        env=env,
    )
    # --author= must be read from the RAW command: git's own form is
    # `--author="Name <a@b>"`, and the scan strips quoted spans, so reading it from
    # there found an empty `--author=` and permitted the very override this exists for.
    block.check(
        "check 2 guards/block_unlinked_commit_author.py",
        bash_json('git commit --author="N <bad@example.com>" -m x'),
        "unlinked-author: --author= override is refused (quoted value survives the scan)",
        env=env,
    )
    # The ALLOW half. Without it, over-blocking is invisible -- and this guard's whole
    # claim is that it CANNOT repeat block-commit-meta.sh's false-positive history,
    # because an author email is never in the command text to begin with.
    block.check(
        "check 0 guards/block_unlinked_commit_author.py",
        bash_json('git commit -m "fix: drop bad@example.com from the docs"'),
        "unlinked-author CONTROL: prose naming a bad address is not a bad author",
        env=env,
    )
    block.check(
        "check 0 guards/block_unlinked_commit_author.py",
        bash_json("grep -rn bad@example.com docs/"),
        "unlinked-author CONTROL: grepping for an address is not a commit at all",
        env=env,
    )
    block.check(
        "check 0 guards/block_unlinked_commit_author.py",
        bash_json('git tag -m "bad@example.com" v1'),
        "unlinked-author CONTROL: a tag writes a tagger, not a commit author",
        env=env,
    )
    block.done()


# --- warn_stale_index: `git commit` takes the INDEX, not the working tree ------
# Needs a REAL repo in a known state, because the condition it reports is a property
# of the index rather than of the command line. Two defects in one session motivated
# it: `git commit -F` swept in a peer's staged files, and a file staged then edited
# committed its stale version under a message that described the edits.
@pytest.mark.xdist_group("hooks-fixtures")
def test_warn_stale_index(tmp_path):
    block = hookblocks.Block("stale-index")
    repo = tmp_path / "stale"
    repo.mkdir()
    git(repo, "init", "-q", ".")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("v1\n", encoding="utf-8")
    git(repo, "add", "--", "a.txt")
    (repo / ".msg").write_text("fixture\n\nPR-TASK: f2757830\n", encoding="utf-8")
    git(repo, "commit", "-q", "-F", ".msg")
    (repo / "a.txt").write_text("v2\n", encoding="utf-8")
    git(repo, "add", "--", "a.txt")
    (repo / "a.txt").write_text("v3\n", encoding="utf-8")

    def probe(want: str, desc: str, command: str) -> None:
        _, said = hookcases.run_guard(
            "guards/warn_stale_index.py",
            bash_json(command),
            want_stderr=True,
            cwd=str(repo),
        )
        got = "warn" if said else "silent"
        block.note(
            0, "stale-index: " + desc, ok=got == want, detail="want %s, got %s" % (want, got)
        )

    probe("warn", "a staged-then-edited path is named", "git commit -F msg.txt")
    probe("warn", "after a separator, still named", "cd . && git commit -F msg.txt")
    # CONTROL: -a takes the WORKING TREE for tracked paths, so there is no staleness.
    probe("silent", "CONTROL: commit -a is not index-only", "git commit -a -m x")
    # CONTROL: the mention-vs-target class. The first draft of this guard warned on
    # this line, which is why it is pinned rather than remembered.
    probe("silent", "CONTROL: unquoted prose is not a command", "echo do not run git commit here")
    probe("silent", "CONTROL: a non-commit is out of scope", "git status")
    block.done()


# --- block_git_empty_commit: the advice must not name a run that does not exist -
# THE FINDING THIS CLOSES. The hook blocked unconditionally while its ONLY advice was
# "rerun the run" -- unreachable when no run exists, which is exactly what a GitHub
# Actions outage produces (observed 2026-08-26: three pushes to PR #577, zero runs,
# Actions in major_outage). The fix added a VERIFIED escape, and the fix itself was
# hand-tested with a throwaway probe -- i.e. nothing prevented its return.
#
# The escape must not become a bypass, so all four directions are pinned, with `gh`
# shimmed so none of them touch the network.
@pytest.mark.xdist_group("hooks-fixtures")
def test_block_git_empty_commit(tmp_path):
    block = hookblocks.Block("empty-commit")
    head = git(ROOT, "rev-parse", "HEAD").stdout.decode().strip() or "unknown"

    def run(
        expected: int, mode: str, claim: str, label: str, needle: str = "", notneedle: str = ""
    ) -> None:
        shim = tmp_path / ("shim-" + mode)
        shim.mkdir(parents=True, exist_ok=True)
        fake = shim / "gh"
        fake.write_text(
            "#!/bin/bash\nexit 1\n" if mode == "FAIL" else "#!/bin/bash\necho %s\n" % mode,
            encoding="utf-8",
        )
        fake.chmod(0o755)
        code, said = hookcases.run_guard(
            "guards/block_git_empty_commit.py",
            '{"tool_input":{"command":"git commit --allow-empty -m x"}}',
            want_stderr=True,
            env=path_env(shim) | {"CI_RETRIGGER_NO_RUN_FOR": claim},
        )
        bad = ""
        if code != expected:
            bad = "exit %d, wanted %d" % (code, expected)
        elif needle and needle not in said:
            bad = "message lacked: " + needle
        elif notneedle and notneedle in said:
            bad = "message WRONGLY advised: " + notneedle
        block.note(expected, label, ok=not bad, detail=bad)

    # The property the finding names: with genuinely no run, the hook must NOT tell the
    # session to rerun one.
    run(
        0,
        "0",
        head,
        "empty-commit: 0 check-runs -> allowed, advises no rerun",
        notneedle="gh run rerun",
    )
    # ...and where there IS something to rerun, that advice is correct and must appear.
    run(
        2,
        "3",
        head,
        "empty-commit: 3 check-runs -> blocked, DOES advise the rerun",
        needle="gh run rerun",
    )
    # Anti-vacuity: an unreadable API fails CLOSED. "I could not check" must never be
    # recorded as "there is no run".
    run(
        2,
        "FAIL",
        head,
        "empty-commit: unreadable check-runs API fails closed",
        needle="could not be read",
    )
    # The claim is a CHECK, not a flag: a sha that is not HEAD proves nothing.
    run(2, "0", "deadbeefcafe", "empty-commit: a claim that is not HEAD is refused")
    block.done()


# --- block_plan_without_tasks / block_compacted_plan_edit ---------------------
# Fixtures are built HERE rather than pointed at a real plan in agent/, so deleting
# or rewriting any plan in the tree cannot silently void these cases.

# Prose under an action-shaped heading: 6 bullets that PARSE as tasks and are nothing
# of the kind.
PLAN_PROSE = "\n".join(
    ["Status: ready", "", "# A plan", "", "## Part 0 - DECIDED by the operator", ""]
    + ["%d. A locked decision sentence long enough to be a task %d." % (i + 1, i) for i in range(6)]
    + ["", "x" * 500]
)
# No list at all: the weaker failure, still a plan nothing can decompose.
PLAN_NOTASK = "\n".join(
    ["Status: ready", "", "# A plan", "", "## Context", "", "Just prose. " * 80]
)
# The shape the guard asks for.
PLAN_TASKS = "\n".join(
    ["Status: ready", "", "# A plan", "", "## Tasks", ""]
    + ["- [ ] Do the concrete thing number %d at file.ts:%d" % (i, i + 10) for i in range(3)]
    + ["", "x" * 500]
)
# A COMPACTED RECORD keeps the plan's path and moves its full text to a git blob, so
# the header IS the only pointer back.
REC_BLOB = "0123456789abcdef0123456789abcdef01234567"
REC_BODY = (
    "\n".join(
        [
            "# A compacted plan",
            "Status: compacted",
            "Full-Text: abc123def agent/PLAN-compacted.md",
            "Full-Text-Blob: " + REC_BLOB,
            "Record-Sig: 1a2b3c4d",
            "",
            "## Why",
            "Because the wave needed it.",
            "",
            "## Boxes",
            "- [x] Do the concrete thing at file.ts:10",
            "    (record) sig=1a2b3c4d done=abc123def",
        ]
    )
    + "\n"
)


@pytest.mark.xdist_group("hooks-fixtures")
def test_block_plan_without_tasks_and_compacted_records(tmp_path):
    block = hookblocks.Block("plan-tasks")
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "PLAN-legacy.md").write_text(PLAN_PROSE + "\n", encoding="utf-8")
    (agent / "PLAN-conforming.md").write_text(PLAN_TASKS + "\n", encoding="utf-8")
    new = str(agent / "PLAN-new.md")
    block.check_out(
        "check_out 2 guards/block_plan_without_tasks.py",
        tool_json("Write", new, "content", PLAN_PROSE),
        "plan-tasks: a prose plan whose DECISIONS parse as tasks is blocked",
        "has NO checkbox task",
    )
    block.check_out(
        "check_out 2 guards/block_plan_without_tasks.py",
        tool_json("Write", new, "content", PLAN_NOTASK),
        "plan-tasks: a plan with no list at all is blocked",
        "finds 0 tasks in it",
    )
    # `plan-tasks: the harness plan directory is in scope too` lives in
    # hookcases.STATIC: its file_path is the harness plan directory, not this fixture.
    block.check_out(
        "check_out 2 guards/block_plan_without_tasks.py",
        tool_json("Edit", str(agent / "PLAN-absent.md"), "new_string", PLAN_PROSE),
        "plan-tasks: an edit CREATING a prose plan is blocked",
        "has NO checkbox task",
    )
    # The message is the product here: a block that does not spell out the fix sends
    # the author back to the same prose. Pin the three things it must say.
    block.check_out(
        "check_out 2 guards/block_plan_without_tasks.py",
        tool_json("Write", new, "content", PLAN_PROSE),
        "plan-tasks: the block names the exact syntax to add",
        "- [ ] Fix <the concrete thing>",
    )
    block.check_out(
        "check_out 2 guards/block_plan_without_tasks.py",
        tool_json("Write", new, "content", PLAN_PROSE),
        "plan-tasks: the block says which states do NOT parse",
        "'- [?]' and '- [>]' do NOT parse",
    )
    # The ALLOW direction. Without these the guard cannot be shown to leave legitimate
    # work alone, which is how an over-blocking guard gets deleted.
    block.check(
        "check 0 guards/block_plan_without_tasks.py",
        tool_json("Write", new, "content", PLAN_TASKS),
        "plan-tasks: a plan with a checkbox list passes",
    )
    block.check(
        "check 0 guards/block_plan_without_tasks.py",
        tool_json("Write", new, "content", "Status: ready"),
        "plan-tasks: a stub under 400 chars is exempt",
    )
    block.check_out(
        "check_out 0 guards/block_plan_without_tasks.py",
        tool_json("Edit", str(agent / "PLAN-legacy.md"), "new_string", "one more paragraph"),
        "plan-tasks: amending a legacy prose plan is grandfathered, with a note",
        "predates the plan-task convention",
    )

    rec = str(agent / "PLAN-compacted.md")
    (agent / "PLAN-compacted.md").write_text(REC_BODY, encoding="utf-8")
    block.check_out(
        "check_out 2 guards/block_compacted_plan_edit.py",
        tool_json("Write", rec, "content", "# x"),
        "compacted-record: a Write over a record is refused",
        "COMPACTED PLAN RECORD",
    )
    # THE ACCIDENT THIS GUARD IS NAMED FOR: the Edit tool's own advice is to pass a
    # minimal unique substring, and for a header line that is the bare 40-hex blob. A
    # line-anchored pattern does not see it.
    block.check_out(
        "check_out 2 guards/block_compacted_plan_edit.py",
        tool_json("Edit", rec, "old_string", REC_BLOB),
        "compacted-record: a bare-blob old_string is refused",
        "Full-Text-Blob VALUE",
    )
    block.check(
        "check 0 guards/block_compacted_plan_edit.py",
        tool_json("Edit", rec, "new_string", "a nicer sentence"),
        "compacted-record: a prose-only Edit is allowed",
    )
    block.check(
        "check 0 guards/block_compacted_plan_edit.py",
        tool_json("Write", str(agent / "PLAN-conforming.md"), "content", "# x"),
        "compacted-record: a plain plan is out of scope",
    )
    block.check(
        "check 0 guards/block_plan_without_tasks.py",
        tool_json("Edit", str(agent / "PLAN-conforming.md"), "new_string", "one more paragraph"),
        "plan-tasks: amending a plan that already has a task list passes",
    )
    block.done()


# --- one open PR at a time ----------------------------------------------------
@pytest.mark.xdist_group("hooks-fixtures")
def test_block_second_open_pr(tmp_path):
    block = hookblocks.Block("one-pr")
    one_open = '[{"number":563,"title":"t","headRefName":"b","isDraft":false}]'

    def gh_case(
        expected: int, body: str, code: int, command: str, label: str, needle: str = ""
    ) -> None:
        shim = stub_gh(tmp_path / ("gh-%d" % block.count), body, code)
        result = subprocess.run(
            ["python3", str(GUARD_DISPATCH), "block_second_open_pr"],
            input=bash_json(command).encode(),
            capture_output=True,
            env=path_env(shim),
            timeout=hookcases.GUARD_TIMEOUT_S,
            check=False,
        )
        said = (result.stdout + result.stderr).decode("utf-8", "replace")
        ok = result.returncode == expected and (not needle or needle in said)
        block.note(expected, label, ok=ok, detail="got %d: %s" % (result.returncode, said[:90]))

    gh_case(
        2,
        one_open,
        0,
        "gh pr create --draft -t x -b y",
        "one-pr: a second create is blocked when one is open",
        "One at a time",
    )
    gh_case(
        2,
        one_open,
        0,
        "sh -c 'gh pr create --draft -t x -b y'",
        "one-pr: sh -c wrapping does not bypass it",
    )
    # THE CONTROL THAT MATTERS: with no open PR the guard must be invisible, or it
    # would block the FIRST PR too and simply stop all work.
    gh_case(0, "[]", 0, "gh pr create --draft -t x -b y", "one-pr CONTROL: the first PR is allowed")
    gh_case(0, "[]", 0, "gh pr view 567", "one-pr CONTROL: a non-create gh command is ignored")
    # FAILS CLOSED: an unreadable list is not evidence that the list is empty.
    gh_case(
        2,
        "gh: could not connect",
        1,
        "gh pr create --draft -t x -b y",
        "one-pr: an unreadable PR list blocks rather than assuming none",
        "cannot verify",
    )
    # DIRECT CASES FOR THE SAME TWO DIRECTIONS, and they are not duplication of the
    # five above. `hook_integrity.covmap` credits a helper-wrapped case by reading which
    # single guard the helper's body names -- and since the W5 P7 cutover this guard is
    # a Python module reached through the dispatcher, so no helper body names it that
    # way and every one of those five became invisible to the coverage assertion. The
    # guard then read block=0,allow=0: a fully covered guard reported as newly
    # uncovered, and the cheap way to clear that red is to baseline it.
    #
    # So the two directions are ALSO asserted directly, in the shape both readers see.
    # The helper cases stay: they cover the failure modes (sh -c wrapping, an unreadable
    # list) that these two do not.
    blocking = path_env(stub_gh(tmp_path / "gh-block", one_open, 0))
    allowing = path_env(stub_gh(tmp_path / "gh-allow", "[]", 0))
    block.check(
        "check 2 guards/block_second_open_pr.py",
        bash_json("gh pr create --draft -t x -b y"),
        "one-pr: a second create is blocked while one is open",
        env=blocking,
    )
    block.check(
        "check 0 guards/block_second_open_pr.py",
        bash_json("gh pr create --draft -t x -b y"),
        "one-pr CONTROL: with no open PR the first one is allowed",
        env=allowing,
    )
    block.done()


# --- premature `gh pr ready` --------------------------------------------------
@pytest.mark.xdist_group("hooks-fixtures")
def test_block_premature_ready(tmp_path):
    block = hookblocks.Block("premature-ready")

    def ready_case(expected: int, conclusion: str, command: str, label: str) -> None:
        shim = stub_gh(tmp_path / ("gh-" + conclusion), conclusion, 0)
        payload = '{"tool_input":{"command":%s},"cwd":%s}' % (
            json.dumps(command),
            json.dumps(os.getcwd()),
        )
        code, _ = hookcases.run_guard(
            "guards/block_premature_ready.py", payload, want_stderr=False, env=path_env(shim)
        )
        block.note(expected, label, ok=code == expected, detail="got %d" % code)

    ready_case(
        2,
        "FAILURE",
        "gh pr ready 42 --repo rediacc/console",
        "premature-ready: flipping ready while CI is not SUCCESS is refused",
    )
    ready_case(
        0,
        "SUCCESS",
        "gh pr ready 42 --repo rediacc/console",
        "premature-ready CONTROL: a green CI Complete lets the flip through",
    )
    # AND DIRECTLY, for the reason spelled out at the one-open-PR cases above: after the
    # cutover a helper body no longer names its guard, so the coverage reader credited
    # this guard with block=0 while `ready_case 2 FAILURE` was asserting the block
    # direction on every run. The helper keeps the CI-conclusion matrix; this is the one
    # line the gate can see.
    block.check(
        "check 2 guards/block_premature_ready.py",
        bash_json("gh pr ready 42 --repo rediacc/console"),
        "premature-ready: a red CI Complete refuses the flip",
        env=path_env(stub_gh(tmp_path / "gh-red", "FAILURE", 0)),
    )
    block.done()


# --- require-jq.sh: the guard that only has an opinion on a BROKEN toolchain ---
# Every other case in the suite runs on a machine that has jq, where require-jq.sh
# exits 0 at its first line. These three are the only place it does any work at all.
#
# WHY A PostToolUse CASE EXISTS AS OF 2026-09-06. require-jq.sh was registered first
# in all three PreToolUse chains and NOWHERE on PostToolUse, while both post-bash
# hooks read stdin with `jq -r ... 2>/dev/null`. With no jq they got an empty string,
# matched nothing, and exited 0 -- failing OPEN and silently. The exit is not a block
# there: the Bash call has already run. It is the only thing that makes the broken
# toolchain VISIBLE instead of letting two hooks quietly do nothing.
#
# THE SANDBOX HOLDS EXACTLY WHAT require-jq.sh USES, no more: `cat` to slurp stdin and
# `grep -qE` for the two carve-out matches. `command -v` and `printf` are bash
# builtins and need no binary on disk. jq is absent by construction, which is the
# entire point -- and bash itself is invoked by ABSOLUTE path.
@pytest.mark.xdist_group("hooks-fixtures")
def test_require_jq_only_speaks_when_jq_is_missing(tmp_path):
    block = hookblocks.Block("require-jq")
    nojq, withjq = tmp_path / "nojq", tmp_path / "withjq"
    for sandbox in (nojq, withjq):
        sandbox.mkdir()
        for tool in ("cat", "grep"):
            (sandbox / tool).symlink_to(shutil.which(tool))
    (withjq / "jq").symlink_to(shutil.which("jq"))
    bash = shutil.which("bash")
    guard = HOOKS / "require-jq.sh"
    # Payloads are built HERE, with jq on the PATH, and only then handed to a run under
    # a PATH that has none.
    pre = bash_json("git push --force origin main")
    post = hookcases.inject_json("gh pr checks 42", "all checks passed")

    def nojq_case(expected: int, payload: str, label: str, needle: str, sandbox=nojq) -> None:
        done = subprocess.run(
            [bash, str(guard)],
            input=payload.encode(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env={"PATH": str(sandbox)},
            timeout=hookcases.GUARD_TIMEOUT_S,
            check=False,
        )
        said = done.stderr.decode("utf-8", "replace")
        # An empty needle asserts SILENCE, not "no assertion": the jq-present arm's
        # whole claim is that the guard says nothing at all.
        ok = done.returncode == expected and (needle in said if needle else said == "")
        block.note(
            expected,
            label,
            ok=ok,
            detail="got exit %d, said: %s" % (done.returncode, said or "<nothing>"),
        )

    nojq_case(
        2,
        pre,
        "require-jq: a PreToolUse Bash payload is REFUSED when jq is missing",
        "BLOCKED: jq is not installed",
    )
    nojq_case(
        2,
        post,
        "require-jq: a PostToolUse Bash payload is REFUSED when jq is missing",
        "On PostToolUse the tool has ALREADY run",
    )
    # CONTROL, the direction that matters most: a guard that refuses everything would
    # pass both cases above and be useless. With jq present it must be mute.
    nojq_case(
        0, pre, "require-jq CONTROL: silent and exit 0 when jq IS present", "", sandbox=withjq
    )
    block.done()


# --- block_merge_with_unpushed: unpushed commits are invisible to the server ---
# The only place the question is answerable is the machine holding the commits, at
# the moment the merge is typed.
#
# The fixture builds its remote-tracking ref with `update-ref` rather than pushing: a
# real `git push` here would be judged by block_unverified_push against the CONSOLE
# tree, because that guard does not scope by `git -C`.
@pytest.mark.xdist_group("hooks-fixtures")
def test_block_merge_with_unpushed(tmp_path):
    block = hookblocks.Block("merge-unpushed")
    repo = tmp_path / "mu"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "0901-1")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "a").write_text("", encoding="utf-8")
    git(repo, "add", "a")
    git(repo, "commit", "-qm", "base")
    head = git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    git(repo, "update-ref", "refs/remotes/origin/0901-1", head)
    env = env_with(CLAUDE_PROJECT_DIR=str(repo))
    block.check(
        "check 0 guards/block_merge_with_unpushed.py",
        bash_json("gh pr merge 1 --rebase"),
        "merge-unpushed CONTROL: a branch in sync merges freely",
        env=env,
    )
    block.check(
        "check 0 guards/block_merge_with_unpushed.py",
        bash_json("gh pr view 1 --json state"),
        "merge-unpushed CONTROL: gh pr view is not a merge",
        env=env,
    )

    (repo / "b").write_text("", encoding="utf-8")
    git(repo, "add", "b")
    git(repo, "commit", "-qm", "the commit that would be stranded")
    # SANITY: every control above is vacuous if this one does not fire.
    block.check(
        "check 2 guards/block_merge_with_unpushed.py",
        bash_json("gh pr merge 1 --rebase"),
        "merge-unpushed SANITY: an unpushed commit refuses the merge",
        env=env,
    )
    block.check(
        "check 2 guards/block_merge_with_unpushed.py",
        bash_json("gh pr merge 583 --repo rediacc/console --rebase --auto"),
        "merge-unpushed: --repo console is still this checkout",
        env=env,
    )
    block.check(
        "check 0 guards/block_merge_with_unpushed.py",
        bash_json("gh pr merge 84 --repo rediacc/account --rebase"),
        "merge-unpushed CONTROL: a merge for a DIFFERENT repo is out of scope",
        env=env,
    )
    block.check(
        "check 0 guards/block_merge_with_unpushed.py",
        bash_json("git push origin 0901-1"),
        "merge-unpushed CONTROL: a push is not a merge",
        env=env,
    )
    block.done()


# --- a guard must judge the tree the COMMAND touches, not this one ------------
# hook_target_root is what makes that true, and it had NO case until now: it was
# verified by hand and committed, so deleting the call would have broken three guards
# silently. That is the exact shape this harness exists to prevent.
#
# THE DEFECT IT CLOSES WAS LIVE. `git -C <scratch> push origin main` was refused by
# block_unverified_push because the gate-run stamp it compares belongs to CONSOLE and
# a scratch tree can never match it (reproduced 2026-09-01, exit 2). warn_remote_drift
# had the same shape latently, and block_untagged_commit had already hand-rolled the
# fix -- three copies, which is why the walk moved to a shared helper.
#
# block_untagged_commit anchors these because its verdict is DETERMINISTIC in both
# directions: a commit with no PR-TASK trailer is refused here and irrelevant
# elsewhere. The push guards depend on a gate-run stamp, which a harness cannot pin.
@pytest.mark.xdist_group("hooks-fixtures")
def test_a_guard_judges_the_tree_the_command_touches(tmp_path):
    block = hookblocks.Block("target-root")
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-q", "-b", "main")
    git(other, "config", "user.email", "t@t")
    git(other, "config", "user.name", "t")
    (other / "f").write_text("", encoding="utf-8")
    git(other, "add", "f")
    git(other, "commit", "-qm", "seed")
    block.check(
        "check 0 guards/block_untagged_commit.py",
        bash_json("git -C %s commit -m 'chore: no trailer here'" % other),
        "target-root: -C into another repo is that repo's business, not ours",
    )
    block.check(
        "check 0 guards/block_untagged_commit.py",
        bash_json("cd %s && git commit -m 'chore: no trailer here'" % other),
        "target-root: a cd into another repo exempts the whole line",
    )
    # The two guards the fix was made FOR. Only the exempting direction is asserted
    # here: their blocking direction depends on a gate-run stamp and a remote's
    # position, neither of which a harness can pin, and both are covered elsewhere.
    block.check(
        "check 0 guards/block_unverified_push.py",
        bash_json("git -C %s push origin main" % other),
        "target-root: block-unverified-push ignores another repo's push",
    )
    block.check(
        "check 0 guards/warn_remote_drift.py",
        bash_json("git -C %s push origin main" % other),
        "target-root: warn-remote-drift ignores another repo's push",
    )
    block.done()


# --- block_untagged_commit: the id cases need a REAL epic to judge against -----
# THE EPIC ID IS RESOLVED, NEVER FROZEN. An earlier read of this block hardcoded the
# id that happened to be in the tree the day it was written, which is the same class
# of defect as the branch resolution below: it passes on one machine and asserts
# something else everywhere else.
#
# AND RESOLVE THE BRANCH THE WAY CI ACTUALLY PRESENTS IT. `git rev-parse --abbrev-ref
# HEAD` prints the literal string "HEAD" in a detached checkout, which is EVERY
# pull_request run -- actions/checkout lands on refs/pull/N/merge. Measured
# 2026-08-27: this block looked for `agent/pr/HEAD.md`, did not find it, and failed
# the suite in CI while passing on every developer machine. The precondition was right
# to refuse a vacuous pass; it was wrong to treat CI's normal state as a broken one.
EPIC_RE = re.compile(r"^`?PR-TASK:[ \t]*([0-9a-f]{6,32})`?$", re.MULTILINE)


def resolve_epic() -> tuple[str | None, str]:
    """`(epic id or None, the snapshot path relative to the root)`."""
    root = os.environ.get("CLAUDE_PROJECT_DIR") or str(ROOT)
    branch = os.environ.get("PR_HEAD_REF") or os.environ.get("GITHUB_HEAD_REF") or ""
    if not branch:
        branch = git(root, "branch", "--show-current").stdout.decode().strip()
    relative = "agent/pr/%s.md" % branch.replace("/", "-")
    snapshot = pathlib.Path(root) / relative
    try:
        found = EPIC_RE.search(snapshot.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        found = None
    return (found.group(1) if found else None), relative


@pytest.mark.xdist_group("hooks-fixtures")
def test_block_untagged_commit_reads_the_message_it_is_given(tmp_path):
    block = hookblocks.Block("untagged-commit")
    epic, relative = resolve_epic()
    # With no snapshot the guard has no set to judge against and ALLOWS any well-formed
    # trailer -- its documented behaviour, not a bug. So the shape cases run either way;
    # only the id-validation case needs a real epic, and it says so out loud rather than
    # silently not running.
    identifier = epic or "f2757830"
    block.check(
        "check 0 guards/block_untagged_commit.py",
        bash_json('git commit -m "feat(x): a thing\n\nPR-TASK: %s"' % identifier),
        "untagged-commit CONTROL: a real trailer passes",
    )
    # `-F` USED TO BE EXEMPTED OUTRIGHT, and that is the form every message longer than
    # one line uses -- 36 consecutive commits in one session passed this guard without
    # it ever looking at them. Two of the three "unreadable" shapes were never
    # unreadable: a heredoc BODY is in the command string, and a -F file is on disk.
    block.check(
        "check 0 guards/block_untagged_commit.py",
        bash_json("git commit -q -F - <<'MSG'\nfeat(x): a thing\n\nPR-TASK: %s\nMSG" % identifier),
        "untagged-commit: a heredoc body IS read, and a real trailer in it passes",
    )
    ok_txt, no_txt = tmp_path / "ok.txt", tmp_path / "no.txt"
    ok_txt.write_text("feat(x): a thing\n\nPR-TASK: %s\n" % identifier, encoding="utf-8")
    no_txt.write_text("feat(x): a thing\n\nno trailer\n", encoding="utf-8")
    block.check(
        "check 0 guards/block_untagged_commit.py",
        bash_json("git commit -F %s" % ok_txt),
        "untagged-commit: -F <file> is READ from disk, and a real trailer passes",
    )
    block.check(
        "check 2 guards/block_untagged_commit.py",
        bash_json("git commit -F %s" % no_txt),
        "untagged-commit: -F <file> with no trailer is refused (was silently allowed)",
    )
    # A TYPO IS WORSE THAN A MISSING TRAILER: it LOOKS tagged, so `git log --grep` finds
    # no epic, the per-epic review never selects the commit, and nothing reports the
    # gap. Shape alone cannot see this; the id is checked against the committed
    # snapshot, so this case needs one.
    if epic:
        typo = epic[:-1] + "0123456789abcdef0"["0123456789abcdef".index(epic[-1]) + 1]
        block.check(
            "check 2 guards/block_untagged_commit.py",
            bash_json('git commit -m "feat(x): a thing\n\nPR-TASK: %s"' % typo),
            "untagged-commit: an id naming NO epic is refused, not just a missing one",
        )
    else:
        block.note(
            "--",
            "untagged-commit: NOT VERIFIED here -- no epic in %s, so there is no set to "
            "judge an id against" % relative,
            ok=True,
        )
    block.done()


# --- warn_remote_drift, then the pr-babysit ROUND LOG guards ------------------
# warn_remote_drift needs a real repo pair (a bare origin, a stale local), because its
# subject is git state, not the command string. The origin is a filesystem path so the
# hook's fetch works offline.
#
# ONE TEST FOR THE WHOLE SEQUENCE, deliberately. The round-log cases below ran inside
# the same exported CLAUDE_PROJECT_DIR as the drift cases in the suite this ports, and
# splitting them would silently change what the guards resolve against.
RLOG = "/home/x/.claude/projects/-home-muhammed-monorepo-console/reports/pr-babysit-0818-1.md"


@pytest.mark.xdist_group("hooks-fixtures")
def test_remote_drift_and_the_round_log_guards(tmp_path):
    block = hookblocks.Block("remote-drift+roundlog")
    origin = tmp_path / "origin.git"
    writer, stale = tmp_path / "writer", tmp_path / "stale"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, timeout=120
    )
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(writer)],
        check=True,
        capture_output=True,
        timeout=300,
    )
    git(
        writer,
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "c1",
    )
    git(writer, "push", "-q", "origin", "main")
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(stale)],
        check=True,
        capture_output=True,
        timeout=300,
    )
    git(
        writer,
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "c2",
    )
    git(writer, "push", "-q", "origin", "main")

    block.check(
        "check 2 guards/warn_remote_drift.py",
        bash_json("git push"),
        "remote-drift: push from a stale local is blocked",
        env=env_with(CLAUDE_PROJECT_DIR=str(stale)),
    )
    env = env_with(CLAUDE_PROJECT_DIR=str(writer))
    block.check(
        "check 0 guards/warn_remote_drift.py",
        bash_json("git push"),
        "remote-drift: aligned local pushes freely",
        env=env,
    )
    block.check(
        "check 0 guards/warn_remote_drift.py",
        bash_json("git status"),
        "remote-drift: non-push commands untouched",
        env=env,
    )

    # On 2026-08-19 a heartbeat tick refreshed the STATUS block with
    # `p.write_text(s[:i] + new)`, which replaces from the STATUS heading to END OF
    # FILE and silently deleted the entire round-history appendix, on a file with no
    # backup. Two guards close it: a pre-edit one for whole-file tool writes, and a
    # pre-bash one for the Bash heredoc that actually did it. Both must also NOT block
    # the legitimate shapes, which is why every deny below has an allow beside it.
    heredoc = (
        "python3 - <<'PY'\nfrom pathlib import Path\n"
        "p=Path('%s'); s=p.read_text(); i=s.index('## STATUS')\n"
        "p.write_text(s[:i] + new)\nPY" % RLOG
    )
    # EXISTENCE IS WHAT DECIDES NOW, so the fixture has to have it. This case used a
    # path under /home/x/ that has never existed, and passed for the wrong reason: the
    # guard was refusing on the NAME alone. That also refused CREATING a round log --
    # and `worklist.py --roundlog` refuses to create one too, so the two halves of the
    # contract deadlocked with no third door.
    real = tmp_path / "reports" / "pr-babysit-0818-1.md"
    real.parent.mkdir(parents=True, exist_ok=True)
    real.write_text(
        "## Wave header\nx\n## STATUS (round 1, t)\ny\n## Rounds\nhistory\n", encoding="utf-8"
    )
    block.check(
        "check 2 guards/block_roundlog_write.py",
        tool_json("Write", str(real), "content", "x"),
        "roundlog: a whole-file Write over an EXISTING log is blocked",
        env=env,
    )
    # The exemption, and the reason it is safe: nothing to swallow.
    block.check(
        "check 0 guards/block_roundlog_write.py",
        tool_json("Write", RLOG, "content", "x"),
        "roundlog CONTROL: CREATING one passes -- a file that does not exist has no appendix",
        env=env,
    )
    block.check(
        "check 0 guards/block_roundlog_write.py",
        tool_json("Edit", str(real), "new_string", "x"),
        "roundlog: a targeted Edit of an existing log passes",
        env=env,
    )
    block.check(
        "check 0 guards/block_roundlog_write.py",
        tool_json("Edit", RLOG, "new_string", "x"),
        "roundlog: a targeted Edit passes (it cannot swallow an unnamed appendix)",
        env=env,
    )
    block.check(
        "check 0 guards/block_roundlog_write.py",
        tool_json("Write", "/r/reports/pr-babysit-0818-1-briefing.md", "content", "x"),
        "roundlog: a briefing has its own contract, not this guard's",
        env=env,
    )
    block.check(
        "check 0 guards/block_roundlog_write.py",
        tool_json("Write", "packages/www/src/x.astro", "content", "x"),
        "roundlog: an unrelated file is untouched",
        env=env,
    )
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(heredoc),
        "roundlog: the exact 2026-08-19 heredoc is blocked",
        env=env,
    )
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("echo hi > %s" % RLOG),
        "roundlog: truncating redirection is blocked",
        env=env,
    )
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("sed -i s/a/b/ %s" % RLOG),
        "roundlog: sed -i is blocked",
        env=env,
    )
    # A NAME IS NOT A TARGET. The python arm used to fire on any write idiom as soon as
    # a round-log name appeared ANYWHERE in the command. Measured 2026-08-27: it refused
    # a heredoc editing a scratchpad state-body file whose CONTENT quoted a round-log
    # path -- a write that could not have touched a round log.
    block.check(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 - <<PY\nq = '/tmp/scratch/state-body.md'\n"
            "open(q, 'w').write('see %s for the round history')\nPY" % RLOG
        ),
        "roundlog CONTROL: a python write to a DIFFERENT .md that merely QUOTES a round log",
        env=env,
    )
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("python3 - <<PY\nopen('%s', 'w').write('x')\nPY" % RLOG),
        "roundlog: a python write whose open() TARGET is the log is blocked",
        env=env,
    )
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("python3 - <<PY\nq = '%s'\nopen(q, 'w').write('x')\nPY" % RLOG),
        "roundlog: a python write whose ASSIGNED target is the log is blocked",
        env=env,
    )
    # FAIL CLOSED, and this is the case that makes the narrowing safe rather than merely
    # quieter: no resolvable literal target, a slicing write_text, a round-log name in
    # the command. That is the 2026-08-19 shape verbatim and it must still fire.
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 - <<PY\nimport pathlib\n"
            "q = pathlib.Path(*['%s'.split('/')[-1]])\n"
            "q.write_text(s[:i] + new)\nPY" % RLOG
        ),
        "roundlog: an UNRESOLVABLE target still fires (fail closed)",
        env=env,
    )
    # PYTHON COPY AND MOVE ARE WRITES TOO. The shell half has refused `cp` and `mv` onto
    # a round log since it was written; their python spelling was never covered, so
    # shutil.copy and os.replace onto the log both returned 0 -- a one-line rename
    # walked through a guard that read as thorough. Measured 2026-08-27.
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("python3 - <<PY\nimport shutil\nshutil.copy('/tmp/x', '%s')\nPY" % RLOG),
        "roundlog: shutil.copy ONTO the log is a write, and is blocked",
        env=env,
    )
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("python3 - <<PY\nimport os\nos.replace('/tmp/x', '%s')\nPY" % RLOG),
        "roundlog: os.replace ONTO the log is a write, and is blocked",
        env=env,
    )
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("python3 - <<PY\nimport shutil\nshutil.move('/tmp/x', '%s')\nPY" % RLOG),
        "roundlog: shutil.move ONTO the log is a write, and is blocked",
        env=env,
    )
    # And the control that keeps the new arm from becoming a blanket refusal: a copy
    # between two innocent paths, with the log named only in a comment.
    block.check(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 - <<PY\nimport shutil\n# see %s for the round history\n"
            "shutil.copy('/tmp/a.md', '/tmp/scratch/n.md')\nPY" % RLOG
        ),
        "roundlog CONTROL: a copy between two innocent .md paths still passes",
        env=env,
    )
    shutil.rmtree(real.parent, ignore_errors=True)

    _deadlock_probe(block, tmp_path)

    block.check(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("echo hi >> %s" % RLOG),
        "roundlog: appending passes (it cannot truncate)",
        env=env,
    )
    block.check(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("grep -n STATUS %s" % RLOG),
        "roundlog: reading passes",
        env=env,
    )
    # THE UNDER-BLOCK REGRESSIONS, found in review 2026-08-19 and each reproduced
    # against the live hook before it was fixed. All three are ways a command that
    # genuinely TRUNCATES the log was waved through, which is worse than an over-block:
    # the guard reported safety it was not providing.
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("tee --output-error=warn %s" % RLOG),
        "roundlog: tee --output-error=warn truncates, and is not an -a",
        env=env,
    )
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("tee -a /tmp/other.txt | tee %s" % RLOG),
        "roundlog: a decoy -a on another file does not license a bare tee",
        env=env,
    )
    block.check(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("tee --append %s" % RLOG),
        "roundlog: long --append is a real append",
        env=env,
    )
    block.check(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("tee -ai %s" % RLOG),
        "roundlog: a short bundle containing a is a real append",
        env=env,
    )
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("tee %s" % RLOG),
        "roundlog: a bare tee still truncates",
        env=env,
    )
    # cp names the log as a SOURCE here, which is a read, and backing the log up is the
    # most useful thing a session can do with it. mv in the same position is NOT a read:
    # it removes the log from its path, so the two verbs are deliberately different.
    block.check(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("cp %s /tmp/backup.md" % RLOG),
        "roundlog: cp with the log as SOURCE is a read",
        env=env,
    )
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("cp /tmp/new.md %s" % RLOG),
        "roundlog: cp ONTO the log still blocked",
        env=env,
    )
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("mv %s /tmp/backup.md" % RLOG),
        "roundlog: mv away removes the log, still blocked",
        env=env,
    )
    # THE OVER-BLOCK REGRESSIONS. Found in review, then reproduced twice against the
    # live hook within minutes: the truncating verbs were matched ANYWHERE in the
    # command rather than anchored to the log, so `truncate` hit the harness's own
    # filename and a bare `cp`/`mv` hit a copy of unrelated files that merely shared a
    # command line with a round-log READ. The guard blocked `cat <log>`.
    block.check(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("cp /tmp/a /tmp/b && grep STATUS %s" % RLOG),
        "roundlog: an unrelated cp beside a read passes",
        env=env,
    )
    block.check(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("grep STATUS %s && mv /tmp/x /tmp/y" % RLOG),
        "roundlog: an unrelated mv beside a read passes",
        env=env,
    )
    block.check(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("ls .claude/hooks/guards/block_roundlog_truncate.py; cat %s" % RLOG),
        "roundlog: the hook's OWN filename beside a read passes",
        env=env,
    )
    block.check(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("tee -a %s < /tmp/x" % RLOG),
        "roundlog: tee -a passes (it cannot truncate)",
        env=env,
    )
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("cp /tmp/x %s" % RLOG),
        "roundlog: cp ONTO the log is blocked",
        env=env,
    )
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("mv /tmp/x %s" % RLOG),
        "roundlog: mv ONTO the log is blocked",
        env=env,
    )
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("tee %s < /tmp/x" % RLOG),
        "roundlog: tee WITHOUT -a is blocked",
        env=env,
    )
    block.check(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("truncate -s 0 %s" % RLOG),
        "roundlog: truncate on the log is blocked",
        env=env,
    )
    block.check(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("worklist.py --roundlog 0818-1"),
        "roundlog: the sanctioned verb passes",
        env=env,
    )
    block.check(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("npm run ci"),
        "roundlog: an unrelated command is untouched",
        env=env,
    )
    block.done()


# THE DEADLOCK CHECK, and it is an INTERACTION -- which is why neither side's own
# cases could see it. Tested in isolation both parties were correct:
# `worklist.py --roundlog` refuses to create a log ("Write the wave header first"), and
# the guard refuses whole-file writes to a round log. Put them in sequence and there
# was NO DOOR AT ALL: the verb sends you to Write, and Write was refused. A session
# following the documented path could not create a round log, which is exactly what
# happened on 2026-08-27 when one tried.
#
# So the assertion is about the PAIR: for a log that does not exist yet, the two must
# not BOTH refuse. Whichever way a future change moves the responsibility -- guard
# exempts creation, or the verb learns to create -- this stays true; it only goes red
# if a door closes with no other one open.
DEADLOCK_BODY = (
    "run:      probe\n"
    "result:   probe body long enough to clear the verb's minimum-length floor\n"
    "red:      none\n"
    "doing:    proving the verb refuses to CREATE a log\n"
    "blocked:  nothing\n"
)


def _deadlock_probe(block, tmp_path) -> None:
    log = tmp_path / "dl" / "reports" / "pr-babysit-zz-deadlock-probe.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.unlink(missing_ok=True)  # must NOT exist: creation is the case under test
    guard_rc, _ = hookcases.run_guard(
        "guards/block_roundlog_write.py",
        tool_json("Write", str(log), "content", "x"),
        want_stderr=False,
    )
    verb = subprocess.run(
        ["python3", str(HOOKS / "stop" / "worklist.py"), "--roundlog", "zz-deadlock-probe"],
        input=DEADLOCK_BODY.encode(),
        capture_output=True,
        timeout=300,
        check=False,
    )
    verb_rc = verb.returncode
    block.note(
        0,
        "roundlog: the guard and the verb must not BOTH refuse creation "
        "(verb=%d guard=%d -- at least one door is open)" % (verb_rc, guard_rc),
        ok=not (verb_rc != 0 and guard_rc != 0),
    )
    # CONTROL: the probe must be measuring a real refusal from the verb, or the
    # assertion above passes because the verb happily creates logs -- a different
    # world, and one this case would be silent about.
    block.note(
        0,
        "roundlog CONTROL: the verb does refuse to create, so the pair check is not vacuous",
        ok=verb_rc != 0,
        detail="the verb no longer refuses to create -- re-read the pair check above, "
        "it now proves nothing",
    )
    shutil.rmtree(log.parent.parent, ignore_errors=True)
