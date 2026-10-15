"""The cases that need a FIXTURE: a temp repo, a stubbed `gh`, an exported root.

Everything that could be data is in hookcases.STATIC. What is left is here because the guard's subject is not the command string: it is the state of a git index, the answer a `gh` call gives, or whether a file exists. Each block builds exactly what its guard reads and tears it down again.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

from rediacc_hooks import dispatch, shellscan
from rediacc_hooks.tests import hookblocks, hookcases
from rediacc_hooks.wellknown import ACCOUNT_REPO, CLAUDE_CODE_URL, GH_REPO

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


# --- block_raw_pr_body_edit: the body-file arms need real files --------------- The PR body is generated, so a hand-written whole-body write silently drops the worklist-epics block and CI fails minutes later naming nothing useful. The CREATE arm cannot insist on being a whole-body write -- there is no block yet to destroy -- so a body already carrying the block passes and only a
# blockless one is refused.
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
    # ONE COMMAND CAN DO BOTH, and reading the flags line-wide gets the scope wrong in both directions. hook_gh_pr_segment exists for exactly this; the first draft of the create arm did not use it, so a legal `create --body <with the block> && edit --add-label x` was refused for the edit's sake.
    block.check(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json("gh pr create --draft --fill && gh pr edit 42 --body-file %s" % with_md),
        "raw-pr-body: a create beside it does not let a raw EDIT through",
    )
    # THE SANCTIONED FORM IS A WHOLE-BODY WRITE TOO. Found 2026-09-04 while babysitting #585: this guard's message prescribed `gh pr edit --body-file`, block-adhoc-sanctioned.sh refused that and prescribed the `gh api ... -X PATCH -F
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
        # A FAILING `gh` IS PART OF THIS CASE NOW, not an accident of the environment. Since 2026-09-23 the arm asks GitHub what the live body actually carries before refusing, so without a stub this case would depend on `repos/o/r/pulls/42` staying a 404 -- a passing assertion resting on a repository nobody here owns. An unreadable live body is the fail-closed arm, which is
        # the verdict this case has always pinned.
        env=path_env(stub_gh(tmp_path / "gh-down", "", 1)),
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


# --- block_raw_pr_body_edit: a marker the LIVE body never had cannot be dropped -- Measured on PR #590, 2026-09-23. Its description carried `worklist-epics` and no `pushed-head` section, because that one is written by the post-bash refresh hook after a push and the PR had not been pushed to since it was created. A PATCH that reproduced the live body exactly, minus one bad
# line, was refused for dropping a block that did not exist, and the doors left were the GitHub UI, which an agent does not have, and closing and reopening the PR.
#
# THE SAME BITE IS ALREADY IN THE GUARD'S HEADER, dated 2026-09-03, written down as a cost rather than as a defect: "a PR body had to lose a footer that check-claude-attribution.sh refuses ... and the only routes left were the GitHub UI or closing and reopening the PR." It came back through the same door for the same reason, which is why the rule is now about what the live body
# carries rather than about what this repo can generate.
#
# STUBBED IN BOTH DIRECTIONS. The verdict now depends on an answer from GitHub, so each case names the answer it is about: a live body with one marker, a live body with both, and a `gh` that cannot answer at all.
@pytest.mark.xdist_group("hooks-fixtures")
def test_block_raw_pr_body_edit_asks_what_the_live_body_carries(tmp_path):
    block = hookblocks.Block("raw-pr-body-live")
    head_mark = "<!-- pushed-head:begin -->"
    epics_only = tmp_path / "epics-only.md"
    epics_only.write_text("prose\n\n%s\n- epic\n<!-- worklist-epics:end -->\n" % EPIC_MARK, "utf-8")
    plain = tmp_path / "plain.md"
    plain.write_text("prose with no block at all\n", encoding="utf-8")
    patch = "gh api repos/o/r/pulls/42 -X PATCH -F body=@%s"
    live_one = path_env(stub_gh(tmp_path / "gh-one", "body\n%s\nx\n" % EPIC_MARK, 0))
    live_both = path_env(
        stub_gh(tmp_path / "gh-both", "body\n%s\n%s\n" % (EPIC_MARK, head_mark), 0)
    )
    live_down = path_env(stub_gh(tmp_path / "gh-none", "", 1))
    block.check(
        "check 0 guards/block_raw_pr_body_edit.py",
        bash_json(patch % epics_only),
        "raw-pr-body-live: a PATCH cannot drop a pushed-head block the live body never had",
        env=live_one,
    )
    block.check(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json(patch % epics_only),
        "raw-pr-body-live CONTROL: the same PATCH IS refused when the live body has both",
        env=live_both,
    )
    block.check(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json(patch % epics_only),
        "raw-pr-body-live CONTROL: an unreadable live body fails closed, as before",
        env=live_down,
    )
    # THE LOOKUP IS NOT A WAY PAST THE GUARD. A body carrying no generated marker at all is a hand-written one, which is the whole subject, and it is refused without asking GitHub anything -- so a live body that happens to carry nothing cannot wave one through.
    block.check(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json(patch % plain),
        "raw-pr-body-live CONTROL: a blockless body is refused whatever the live body says",
        env=live_one,
    )
    block.done()


# --- block_commit_meta: the trailer lives in the FILE, and gh does not say -F --- WHAT WAS UNCOVERED. The guard reads `-F <path>` bodies because two commits carrying the co-author trailer reached a real push before anyone noticed the message was never in the command string. That fix shipped with no case of its own, so the first assertion below is a regression test for a
# repair that has been running untested since it landed.
#
# AND THE FLAG NAME WAS GIT'S ONLY. `gh pr create`/`gh pr edit` spell a long body `--body-file <path>`, and the sanctioned `gh api ... -X PATCH` form spells it `-F body=@<path>`; neither is a prefix or a suffix of `-F` or `--file`, so the file was never opened for either. Measured 2026-09-23: `gh pr create --body-file <path>` created PR #590 with the attribution footer live in
# its description, past this guard, and the operator found it on GitHub.
#
# THE LITERAL IS ASSEMBLED FROM PARTS, for the reason `.ci/rediacc_ci/quality/claude_attribution.py` gives at length: this guard refuses any command whose text carries the trailer, so a file spelling it out could not be handed to a shell here at all.
TOKEN = "Co-" + "Authored-By"
TRAILER = TOKEN + ": Claude Opus 5 <noreply@anthropic.com>"
FOOTER = "\U0001f916 " + ("Generated with [Claude Code](" + CLAUDE_CODE_URL + ")")


@pytest.mark.xdist_group("hooks-fixtures")
def test_block_commit_meta_reads_every_body_file_spelling(tmp_path):
    block = hookblocks.Block("commit-meta-files")
    trailer_md = tmp_path / "trailer.md"
    trailer_md.write_text("a real message\n\n%s\n" % TRAILER, encoding="utf-8")
    footer_md = tmp_path / "footer.md"
    footer_md.write_text("a PR body\n\n%s\n%s\n" % (EPIC_MARK, FOOTER), encoding="utf-8")
    clean_md = tmp_path / "clean.md"
    clean_md.write_text("a PR body\n\n%s\n- epic\n" % EPIC_MARK, encoding="utf-8")
    absent = tmp_path / "absent.md"
    for spelling, path, expected, why in (
        ("git commit -F %s", trailer_md, 2, "-F <file> is READ, and the trailer in it is refused"),
        ("git commit --file=%s", trailer_md, 2, "--file=<file> is the same flag, same answer"),
        ("git commit -F %s", clean_md, 0, "CONTROL: a clean -F body passes"),
        (
            "gh pr create --draft --title t --body-file %s",
            footer_md,
            2,
            "gh spells it --body-file, and the footer in it was walking past (PR #590)",
        ),
        (
            "gh pr create --draft --title t --body-file=%s",
            footer_md,
            2,
            "--body-file=<file> is the same flag, same answer",
        ),
        (
            "gh pr create --draft --title t --body-file %s",
            clean_md,
            0,
            "CONTROL: a clean --body-file passes",
        ),
        (
            "gh api repos/o/r/pulls/42 -X PATCH -F body=@%s",
            footer_md,
            2,
            "the sanctioned PATCH door carries the body in -F body=@<file>",
        ),
        (
            "gh api repos/o/r/pulls/42 --method PATCH --input %s",
            trailer_md,
            2,
            "--input <file> is the same door under another name",
        ),
        # `gh api`'s flags are order-independent, which is why the endpoint and the method are two checks rather than one sequential pattern.
        (
            "gh api -X PATCH repos/o/r/pulls/42 -F body=@%s",
            footer_md,
            2,
            "the method may precede the endpoint and it is the same write",
        ),
        (
            "gh api repos/o/r/pulls/42 -X PATCH -F body=@%s",
            clean_md,
            0,
            "CONTROL: a clean PATCH body passes",
        ),
        # The readability rule the `-F` arm has always had: judge what can be read, allow what cannot, rather than refusing blind.
        (
            "gh pr create --draft --body-file %s",
            absent,
            0,
            "CONTROL: a --body-file that does not exist is allowed, not refused blind",
        ),
    ):
        block.check(
            "check %d guards/block_commit_meta.py" % expected,
            bash_json(spelling % path),
            "commit-meta-files: %s" % why,
        )
    # THE VERB GATE IS STILL THE VERB GATE, and the METHOD half of it is what keeps this guard from blocking its own enforcement. Reaching a `pulls/<n>` endpoint with PATCH authors a PR description; the same endpoint without one is a READ, and reading a live body in order to grep it for the trailer is how the rule gets audited. That shape is the false-positive class the
    # 2026-08-27 verb gate was written to end, and an endpoint-only test would have reintroduced it.
    block.check(
        "check 0 guards/block_commit_meta.py",
        bash_json("gh api repos/o/r/pulls/42 --jq .body"),
        "commit-meta-files CONTROL: a GET against the same endpoint is not a write",
    )
    block.check(
        "check 0 guards/block_commit_meta.py",
        bash_json("gh api repos/o/r/pulls/42 --jq .body | grep %s" % TOKEN),
        "commit-meta-files CONTROL: auditing a live body for the trailer is not adding one",
    )
    block.check(
        "check 0 guards/block_commit_meta.py",
        bash_json("gh api repos/o/r/pulls/42/comments -X POST -f body=hi"),
        "commit-meta-files CONTROL: a comment POST is not a PR description",
    )
    block.check(
        "check 0 guards/block_commit_meta.py",
        bash_json("gh api user --jq .login"),
        "commit-meta-files CONTROL: an unrelated gh api read is not this guard's business",
    )
    block.done()


# --- block_unlinked_commit_author: the identity has to come from the fixture --- THE CONFIG WAS NOT THE CAUSE -- the checkout's only user.email source was the correct one -- so every BLOCK case below is an OVERRIDE path. A guard that read `git config` alone would have watched all 30 go past.
#
# The fixture cache must contain the REAL resolved author, or every case blocks -- including the ALLOW ones, which is how the first draft of this block failed.
#
# AND THE IDENTITY ITSELF, because borrowing the machine's is what broke in CI: a GitHub runner has no global user.email and actions/checkout does not set one, so `git var` resolves nothing, the guard correctly refuses a commit it cannot attribute, and the prose CONTROL went red for a reason that has nothing to do with what it asserts. Measured 2026-09-03, job 100727875171.
#
# AS CONFIG, NOT AS GIT_AUTHOR_EMAIL, and that distinction is the whole trick: git resolves GIT_AUTHOR_EMAIL with HIGHER precedence than user.email, so exporting it
# masked the `-c user.email=bad@...` case -- the guard resolved the good address and
# permitted the very override it exists to refuse. A global config file sits BELOW every override the refuse cases use, which is exactly where an ambient identity belongs.
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
    # CLAUDE_PROJECT_DIR IS SET EXPLICITLY, not left to the `git rev-parse --show-toplevel` fallback: this fixture's own `GIT_CONFIG_GLOBAL` override has no `safe.directory` entry for this checkout, so that fallback genuinely fails here ("dubious ownership"), and every case in this
    # function shared that failure silently until block_unlinked_commit_author.py's root-resolution-failure branch was fixed to fail CLOSED instead of ALLOW -- at which point every case here started returning the SAME blocked verdict regardless of its own real logic, which is what surfaced this.
    env = env_with(
        COMMIT_IDENTITY_FILE=str(identity),
        GIT_CONFIG_GLOBAL=str(gitconfig),
        CLAUDE_PROJECT_DIR=str(ROOT),
    )
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
    # The ALLOW half. Without it, over-blocking is invisible -- and this guard's whole claim is that it CANNOT repeat block-commit-meta.sh's false-positive history, because an author email is never in the command text to begin with.
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
    # The plain-config path, which is the ONE shape a `git config`-reading guard would also have caught. It is here for the opposite reason to the three overrides above: those prove the guard sees what config cannot, and this proves it still sees config.
    badconfig = tmp_path / "gitconfig-bad"
    badconfig.write_text("[user]\n\tname = ctl\n\temail = bad@example.com\n", encoding="utf-8")
    block.check(
        "check 2 guards/block_unlinked_commit_author.py",
        bash_json('git commit -m "x"'),
        "unlinked-author: an unlinked address in plain config is refused",
        env=env_with(COMMIT_IDENTITY_FILE=str(identity), GIT_CONFIG_GLOBAL=str(badconfig)),
    )
    # A MISSING CACHE MUST REFUSE, NEVER PERMIT. The allowed set is a tracked file, so inside this tree its absence means a broken checkout rather than a free pass, and a guard that failed open here would be silent exactly when it could check nothing.
    block.check(
        "check 2 guards/block_unlinked_commit_author.py",
        bash_json('git commit -m "x"'),
        "unlinked-author: an unreadable identity cache refuses rather than permitting",
        env=env_with(
            COMMIT_IDENTITY_FILE=str(tmp_path / "not-here.json"), GIT_CONFIG_GLOBAL=str(gitconfig)
        ),
    )
    # THE SUBMODULE ARM, and the reason it needs a fixture of its own: this guard deliberately judges a commit into a repo UNDER the project root, where block-untagged-commit.sh exits on any foreign root. Three submodules carried the 2026-09-03 defect, so a nested checkout's own local identity is in scope.
    sub_root = (tmp_path / "subroot").resolve()
    (sub_root / "mod").mkdir(parents=True)
    git(sub_root, "init", "-q")
    git(sub_root / "mod", "init", "-q")
    git(sub_root / "mod", "config", "user.name", "ctl")
    git(sub_root / "mod", "config", "user.email", "bad@example.com")
    sub_env = env_with(
        COMMIT_IDENTITY_FILE=str(identity),
        GIT_CONFIG_GLOBAL=str(gitconfig),
        CLAUDE_PROJECT_DIR=str(sub_root),
    )
    block.check(
        "check 2 guards/block_unlinked_commit_author.py",
        bash_json('cd mod && git commit -m "x"'),
        "unlinked-author: a nested checkout under the project root IS judged",
        env=sub_env,
    )
    git(sub_root / "mod", "config", "user.email", "good@example.com")
    block.check(
        "check 0 guards/block_unlinked_commit_author.py",
        bash_json('cd mod && git commit -m "x"'),
        "unlinked-author CONTROL: the same nested checkout with a linked address passes",
        env=sub_env,
    )
    # The false positive this guard's own introducing commit produced: the message EXPLAINING `--author=` is prose, and a guard that cannot be described in a commit message is a guard people route around.
    block.check(
        "check 0 guards/block_unlinked_commit_author.py",
        bash_json('git commit -m "explain --author=bad@example.com in prose"'),
        "unlinked-author CONTROL: --author= inside the message is prose, not an override",
        env=env,
    )
    # GitHub's noreply forms attribute correctly, so they are allowed without being listed in the cache at all.
    block.check(
        "check 0 guards/block_unlinked_commit_author.py",
        bash_json('git -c user.email=1+ctl@users.noreply.github.com commit -m "x"'),
        "unlinked-author CONTROL: the id+login noreply form is allowed unlisted",
        env=env,
    )
    block.done()


# --- warn_stale_index: `git commit` takes the INDEX, not the working tree ------ Needs a REAL repo in a known state, because the condition it reports is a property of the index rather than of the command line. Two defects in one session motivated it: `git commit -F` swept in a peer's staged files, and a file staged then edited committed its stale version under a message that
# described the edits.
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
    # CONTROL: the mention-vs-target class. The first draft of this guard warned on this line, which is why it is pinned rather than remembered.
    probe("silent", "CONTROL: unquoted prose is not a command", "echo do not run git commit here")
    probe("silent", "CONTROL: a non-commit is out of scope", "git status")
    block.done()


# --- block_nonstandard_branch_name: the MMDD-N rule is THIS checkout's convention ------ Needs REAL repos, because the exemption resolves the `-C`/`cd` target with `git rev-parse --show-toplevel`. Found 2026-09-24 restoring branches in a different project with `git -C <that repo> branch chore/...`: the rule refused them. A nested repo under the checkout (a submodule) keeps the rule, because /pr-merge matches coordinated names there.
@pytest.mark.xdist_group("hooks-fixtures")
def test_block_nonstandard_branch_name_other_project(tmp_path):
    block = hookblocks.Block("branch-name-other-project")
    project = (tmp_path / "project").resolve()
    nested = project / "private" / "sub"
    foreign = (tmp_path / "elsewhere").resolve()
    for repo in (project, nested, foreign):
        repo.mkdir(parents=True, exist_ok=True)
        git(repo, "init", "-q", ".")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project))

    def probe(want: int, desc: str, command: str) -> None:
        code, _ = hookcases.run_guard(
            "guards/block_nonstandard_branch_name.py",
            bash_json(command),
            want_stderr=False,
            env=env,
            cwd=str(project),
        )
        block.note(
            0, "branch-name: " + desc, ok=code == want, detail="want %d, got %d" % (want, code)
        )

    probe(0, "another project via -C is exempt", "git -C %s branch chore/x" % foreign)
    probe(0, "another project via cd is exempt", "cd %s && git checkout -b feat/y" % foreign)
    # CONTROLS: the exemption must not leak into this checkout or its submodules.
    probe(
        2,
        "CONTROL: a submodule under the checkout keeps the rule",
        "git -C %s branch chore/x" % nested,
    )
    probe(2, "CONTROL: a plain creation here keeps the rule", "git checkout -b chore/x")
    probe(
        2,
        "CONTROL: -C naming the checkout itself keeps the rule",
        "git -C %s branch chore/x" % project,
    )
    block.done()


# --- block_git_empty_commit: the advice must not name a run that does not exist - THE FINDING THIS CLOSES. The hook blocked unconditionally while its ONLY advice was "rerun the run" -- unreachable when no run exists, which is exactly what a GitHub Actions outage produces (observed 2026-08-26: three pushes to PR #577, zero runs, Actions in major_outage). The fix added a VERIFIED
# escape, and the fix itself was hand-tested with a throwaway probe -- i.e. nothing prevented its return.
#
# The escape must not become a bypass, so all four directions are pinned, with `gh` shimmed so none of them touch the network.
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

    # The property the finding names: with genuinely no run, the hook must NOT tell the session to rerun one.
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
    # Anti-vacuity: an unreadable API fails CLOSED. "I could not check" must never be recorded as "there is no run".
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


# --- block_plan_without_tasks / block_compacted_plan_edit --------------------- Fixtures are built HERE rather than pointed at a real plan in agent/, so deleting or rewriting any plan in the tree cannot silently void these cases.

# Prose under an action-shaped heading: 6 bullets that PARSE as tasks and are nothing of the kind.
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
# A COMPACTED RECORD keeps the plan's path and moves its full text to a git blob, so the header IS the only pointer back.
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
    # `plan-tasks: the harness plan directory is in scope too` lives in hookcases.STATIC: its file_path is the harness plan directory, not this fixture.
    block.check_out(
        "check_out 2 guards/block_plan_without_tasks.py",
        tool_json("Edit", str(agent / "PLAN-absent.md"), "new_string", PLAN_PROSE),
        "plan-tasks: an edit CREATING a prose plan is blocked",
        "has NO checkbox task",
    )
    # The message is the product here: a block that does not spell out the fix sends the author back to the same prose. Pin the three things it must say.
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
    # The ALLOW direction. Without these the guard cannot be shown to leave legitimate work alone, which is how an over-blocking guard gets deleted.
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
    # THE ACCIDENT THIS GUARD IS NAMED FOR: the Edit tool's own advice is to pass a minimal unique substring, and for a header line that is the bare 40-hex blob. A line-anchored pattern does not see it.
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
    # THE CONTROL THAT MATTERS: with no open PR the guard must be invisible, or it would block the FIRST PR too and simply stop all work.
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
    # NO AGENT PATH TO A SECOND PR (CLAUDE.md rule 1): neither refusal may invite an ask. Both name the operator's own `!` command instead, which is the only way a second or unverifiable PR is created.
    gh_case(
        2,
        one_open,
        0,
        "gh pr create --draft -t x -b y",
        "one-pr: the second-PR refusal names the operator's own ! command, not an ask",
        "no agent path to a second PR, and nothing to ask for",
    )
    gh_case(
        2,
        "gh: could not connect",
        1,
        "gh pr create --draft -t x -b y",
        "one-pr: the unverifiable refusal names the operator's own ! command, not an ask",
        "is the operator's own `!` command",
    )
    # DIRECT CASES FOR THE SAME TWO DIRECTIONS, and they are not duplication of the five above. `hook_integrity.covmap` credits a helper-wrapped case by reading which single guard the helper's body names -- and since the W5 P7 cutover this guard is a Python module reached through the dispatcher, so no helper body names it that way and every one of those five became invisible to the
    # coverage assertion. The
    # guard then read block=0,allow=0: a fully covered guard reported as newly
    # uncovered, and the cheap way to clear that red is to baseline it.
    #
    # So the two directions are ALSO asserted directly, in the shape both readers see. The helper cases stay: they cover the failure modes (sh -c wrapping, an unreadable list) that these two do not.
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
        ("gh pr ready 42 --repo " + GH_REPO),
        "premature-ready: flipping ready while CI is not SUCCESS is refused",
    )
    ready_case(
        0,
        "SUCCESS",
        ("gh pr ready 42 --repo " + GH_REPO),
        "premature-ready CONTROL: a green CI Complete lets the flip through",
    )
    # AND DIRECTLY, for the reason spelled out at the one-open-PR cases above: after the cutover a helper body no longer names its guard, so the coverage reader credited
    # this guard with block=0 while `ready_case 2 FAILURE` was asserting the block
    # direction on every run. The helper keeps the CI-conclusion matrix; this is the one line the gate can see.
    block.check(
        "check 2 guards/block_premature_ready.py",
        bash_json("gh pr ready 42 --repo " + GH_REPO),
        "premature-ready: a red CI Complete refuses the flip",
        env=path_env(stub_gh(tmp_path / "gh-red", "FAILURE", 0)),
    )
    block.done()


# --- the head's jq check: the guard that only has an opinion on a BROKEN toolchain --- Every other case in the suite runs on a machine that has jq, where the check is silent. These three are the only place it does any work at all.
#
# WHY A PostToolUse CASE EXISTS AS OF 2026-09-06. The jq check was registered first in all three PreToolUse chains and NOWHERE on PostToolUse, while both post-bash hooks read stdin with `jq -r ... 2>/dev/null`. With no jq they got an empty string, matched nothing, and exited 0 -- failing OPEN and silently. The exit is not a block there: the Bash call has already run. It is the
# only thing that makes the broken toolchain VISIBLE instead of letting two hooks quietly do nothing.
#
# THE SANDBOX HOLDS EXACTLY WHAT THE CHECK USES, no more: `cat` for the refusal heredoc and `grep -qE` for the two carve-out matches. `read`, `command -v` and `printf` are bash builtins and need no binary on disk. jq is absent by construction, which is the entire point, and bash itself is invoked by ABSOLUTE path.
#
# DRIVEN THROUGH `chain-head.sh --check jq` SINCE 2026-09-21, when the two toolchain checks were inlined into the head and their scripts deleted. `--check <tool>` runs that one check and stops, so this stays a test of the jq arm alone and the sandbox needs no python3 for the runner the head would otherwise exec.
@pytest.mark.xdist_group("hooks-fixtures")
def test_the_head_jq_check_only_speaks_when_jq_is_missing(tmp_path):
    block = hookblocks.Block("chain-head-jq")
    nojq, withjq = tmp_path / "nojq", tmp_path / "withjq"
    for sandbox in (nojq, withjq):
        sandbox.mkdir()
        for tool in ("cat", "grep"):
            (sandbox / tool).symlink_to(shutil.which(tool))
    (withjq / "jq").symlink_to(shutil.which("jq"))
    bash = shutil.which("bash")
    guard = HOOKS / "chain-head.sh"
    # Payloads are built HERE, with jq on the PATH, and only then handed to a run under a PATH that has none.
    pre = bash_json("git push --force origin main")
    post = hookcases.inject_json("gh pr checks 42", "all checks passed")

    def nojq_case(expected: int, payload: str, label: str, needle: str, sandbox=nojq) -> None:
        done = subprocess.run(
            [bash, str(guard), "--check", "jq"],
            input=payload.encode(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env={"PATH": str(sandbox)},
            timeout=hookcases.GUARD_TIMEOUT_S,
            check=False,
        )
        said = done.stderr.decode("utf-8", "replace")
        # An empty needle asserts SILENCE, not "no assertion": the jq-present arm's whole claim is that the guard says nothing at all.
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
        "chain-head jq: a PreToolUse Bash payload is REFUSED when jq is missing",
        "BLOCKED: jq is not installed",
    )
    nojq_case(
        2,
        post,
        "chain-head jq: a PostToolUse Bash payload is REFUSED when jq is missing",
        "On PostToolUse the tool has ALREADY run",
    )
    # CONTROL, the direction that matters most: a guard that refuses everything would pass both cases above and be useless. With jq present it must be mute.
    nojq_case(
        0, pre, "chain-head jq CONTROL: silent and exit 0 when jq IS present", "", sandbox=withjq
    )
    block.done()


# --- block_merge_with_unpushed: unpushed commits are invisible to the server --- The only place the question is answerable is the machine holding the commits, at the moment the merge is typed.
#
# The fixture builds its remote-tracking ref with `update-ref` rather than pushing: a real `git push` here would be judged by block_unverified_push against the CONSOLE tree, because that guard does not scope by `git -C`.
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
        bash_json("gh pr merge 583 --repo " + GH_REPO + " --rebase --auto"),
        "merge-unpushed: --repo console is still this checkout",
        env=env,
    )
    block.check(
        "check 0 guards/block_merge_with_unpushed.py",
        bash_json("gh pr merge 84 --repo " + ACCOUNT_REPO + " --rebase"),
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


# --- a guard must judge the tree the COMMAND touches, not this one ------------ hook_target_root is what makes that true, and it had NO case until now: it was verified by hand and committed, so deleting the call would have broken three guards silently. That is the exact shape this harness exists to prevent.
#
# THE DEFECT IT CLOSES WAS LIVE. `git -C <scratch> push origin main` was refused by block_unverified_push because the gate-run stamp it compares belongs to CONSOLE and a scratch tree can never match it (reproduced 2026-09-01, exit 2). warn_remote_drift had the same shape latently, and block_untagged_commit had already hand-rolled the fix -- three copies, which is why the walk moved
# to a shared helper.
#
# block_untagged_commit anchors these because its verdict is DETERMINISTIC in both directions: a commit with no PR-TASK trailer is refused here and irrelevant elsewhere. The push guards depend on a gate-run stamp, which a harness cannot pin.
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
    # THE TOOL CALL'S OWN `cwd` FIELD, WITH NO `cd`/`-C` ANYWHERE IN THE COMMAND TEXT.
    # Reproduced live 2026-09-23: a session ran `git commit` with the Bash tool's `cwd` pointed at an independent local clone.
    # This guard judged it against the console tree's own stale index and epic snapshot, because `bash_json` (used by every other case here) never sets a `"cwd"` key at all, so this exact shape had no case until now.
    cwd_only_payload = '{"tool_input":{"command":%s},"cwd":%s}' % (
        json.dumps("git commit -m 'chore: no trailer here'"),
        json.dumps(str(other)),
    )
    block.check(
        "check 0 guards/block_untagged_commit.py",
        cwd_only_payload,
        "target-root: the tool call's own cwd field alone exempts the commit, with no cd/-C in the command text",
    )
    # The two guards the fix was made FOR. Only the exempting direction is asserted here: their blocking direction depends on a gate-run stamp and a remote's position, neither of which a harness can pin, and both are covered elsewhere.
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


# --- block_worktree_add: a script run BY PATH is a program (#78afdc0b) --------- The guard read `-c`, heredocs and here-strings only, so a script on disk that runs `git worktree add` was allowed (rc 0 at c5c3036c3). It now reads the script: an untracked or edited one is read, a tracked and unchanged one is reviewed code and is not.
@pytest.mark.xdist_group("hooks-fixtures")
def test_block_worktree_add_reads_a_script_run_by_path(tmp_path):
    block = hookblocks.Block("worktree-add-by-path")
    runs = tmp_path / "runs.py"
    runs.write_text("import os\nos.system('git worktree add /tmp/x')\n", encoding="utf-8")
    prints = tmp_path / "prints.py"
    prints.write_text("print('never run git worktree add here')\n", encoding="utf-8")
    silent = tmp_path / "silent.py"
    silent.write_text("import subprocess\nsubprocess.run(['git', 'status'])\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "tracked.py").write_text(runs.read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "edited.py").write_text(prints.read_text(encoding="utf-8"), encoding="utf-8")
    git(repo, "add", "tracked.py", "edited.py")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")
    with open(repo / "edited.py", "a", encoding="utf-8") as handle:
        handle.write("print('edited')\n")
    spec_deny = "check 2 guards/block_worktree_add.py"
    spec_allow = "check 0 guards/block_worktree_add.py"
    # Review 6f52f7ff.1: a script run directly by its shebang names no interpreter in the command.
    direct = tmp_path / "direct.py"
    direct.write_text(
        "#!/usr/bin/env python3\nimport os\nos.system('git worktree add /tmp/x')\n",
        encoding="utf-8",
    )
    direct.chmod(0o755)
    quiet = tmp_path / "quiet.py"
    quiet.write_text(
        "#!/usr/bin/env python3\nprint('never run git worktree add here')\n", encoding="utf-8"
    )
    quiet.chmod(0o755)
    calm = tmp_path / "calm.py"
    calm.write_text("#!/usr/bin/env python3\nprint('hello')\n", encoding="utf-8")
    calm.chmod(0o755)
    block.check(spec_deny, bash_json(str(direct)), "worktree-add: a script run directly by shebang")
    block.check(
        spec_deny,
        bash_json("cd %s && ./direct.py" % tmp_path),
        "worktree-add: the same script directly from a cd",
    )
    # THE FAIL-CLOSED COST, intended: a script that only prints the phrase is refused while it is untracked.
    block.check(
        spec_deny,
        bash_json(str(quiet)),
        "worktree-add: a script run directly that only prints the phrase",
    )
    block.check(
        spec_allow,
        bash_json(str(calm)),
        "worktree-add CONTROL: a script run directly that never names the phrase",
    )
    block.check(spec_deny, bash_json("python3 %s" % runs), "worktree-add: a script by path runs it")
    block.check(
        spec_deny,
        bash_json("cd %s && python3 runs.py" % tmp_path),
        "worktree-add: the same script by a path relative to a cd",
    )
    block.check(
        spec_deny,
        bash_json("python3 %s" % prints),
        "worktree-add: a script by path that only prints the phrase (the fail-closed cost)",
    )
    block.check(
        spec_allow,
        bash_json("python3 %s" % silent),
        "worktree-add CONTROL: a script by path that runs commands but never names the phrase",
    )
    block.check(
        spec_allow,
        bash_json("python3 %s" % (repo / "tracked.py")),
        "worktree-add CONTROL: a tracked, unchanged script is reviewed code and is not read",
    )
    block.check(
        spec_deny,
        bash_json("python3 %s" % (repo / "edited.py")),
        "worktree-add: a tracked script edited since HEAD is read again",
    )
    block.done()


# A SHELL SCRIPT RUN BY PATH WAS NEVER READ. `bash x.sh`, `sh -e x.sh`, `source x.sh`, `. x.sh` and `./x.sh` (a shell shebang) whose file runs `git worktree add` were each allowed (rc 0, 2026-10-15), as was a script the same command wrote and then ran.
@pytest.mark.xdist_group("hooks-fixtures")
def test_block_worktree_add_reads_a_shell_script_run_by_path(tmp_path):
    block = hookblocks.Block("worktree-add-shell-script")
    spec_deny = "check 2 guards/block_worktree_add.py"
    spec_allow = "check 0 guards/block_worktree_add.py"
    runs = tmp_path / "w.sh"
    runs.write_text("#!/bin/bash\ngit worktree add /tmp/x\n", encoding="utf-8")
    runs.chmod(0o755)
    bare = tmp_path / "bare"
    bare.write_text("git worktree add /tmp/x\n", encoding="utf-8")
    bare.chmod(0o755)
    split = tmp_path / "split.sh"
    split.write_text('git work"tree" "a"dd /tmp/x\n', encoding="utf-8")
    calm = tmp_path / "calm.sh"
    calm.write_text("#!/bin/bash\ngit worktree list\necho hi\n", encoding="utf-8")
    calm.chmod(0o755)
    for run_ in (
        "bash %s" % runs,
        "sh -e %s" % runs,
        "bash --norc -o pipefail %s" % runs,
        "source %s" % runs,
        ". %s" % runs,
        str(runs),
        "timeout 5 %s" % runs,
        "cd %s && bash w.sh" % tmp_path,
        str(bare),
        "bash %s" % split,
        "printf 'git worktree add /tmp/x\\n' > %s/v.sh; bash %s/v.sh" % (tmp_path, tmp_path),
    ):
        block.check(spec_deny, bash_json(run_), "worktree-add: a shell script by path: " + run_)
    for run_ in ("bash %s" % calm, str(calm), "source %s" % calm, "/usr/bin/env true"):
        block.check(
            spec_allow,
            bash_json(run_),
            "worktree-add CONTROL: a shell script naming no add: " + run_,
        )
    block.done()


# A FILE IS JUDGED BY ITS TEXT, NOT BY WHAT IT CAN RUN. An earlier reading allowed a file naming the phrase when it found no way for the file to run a command, and decided that from a deny list of exec primitives, dynamic reaches and code-running modules. Every round of review found a road the list missed, so the rule is now plain: an untracked or edited script naming `worktree` with `add` or `create` is refused, whatever it does with the words.
FILE_RUNS = {
    "system.py": "import os\nos.system('git worktree add /tmp/x')\n",
    "argv.py": "import subprocess\nsubprocess.run(['git', 'worktree', 'add', '/tmp/x'])\n",
    "named.py": "import os\ncmd = 'git worktree add /tmp/x'\nos.system(cmd)\n",
    "named_argv.py": "import subprocess\nargv = ['git', 'worktree', 'add', 'x']\nsubprocess.check_call(argv)\n",
    "alias.py": "from subprocess import run as go\ngo('git worktree add /tmp/x', shell=True)\n",
    "wrapper.py": "import subprocess\ndef sh(c):\n    subprocess.run(c, shell=True)\nsh('git worktree add /tmp/x')\n",
    "keyword.py": "import subprocess\nsubprocess.run(args=['git', 'worktree', 'add', 'x'])\n",
    "port.py": "from rediacc_ci.dev import worktree\nworktree.main(['create', 'x'])\n",
    "port_cmd.py": "from rediacc_ci.dev import worktree\nworktree.cmd_create(None)\n",
    "run.js": 'require("child_process").execSync("git worktree add /tmp/x");\n',
    "run.pl": 'system("git", "worktree", "add", "/tmp/x");\n',
    "unparsable.py": "import os\nos.system('git worktree add /tmp/x'\n",
}
# A string reaches a call by more roads than a name assignment; none of them needs tracing when the text is what is judged.
FILE_RUNS_UNTRACED = {
    "for_target.py": "import subprocess\nfor c in ['git worktree add /tmp/x']:\n    subprocess.run(c, shell=True)\n",
    "tuple_unpack.py": "import os\ncmd, other = 'git worktree add /tmp/x', 1\nos.system(cmd)\n",
    "comprehension.py": "import os\n[os.system(c) for c in ['git worktree add /tmp/x']]\n",
    "walrus.py": "import os\nif (c := 'git worktree add /tmp/x'):\n    os.system(c)\n",
    "default.py": "import os\ndef go(c='git worktree add /tmp/x'):\n    os.system(c)\ngo()\n",
    "class_attr.py": "import os\nclass K:\n    c = 'git worktree add /tmp/x'\nos.system(K.c)\n",
    "concat.py": "import os\nos.system('git worktree ' + 'add /tmp/x')\n",
    "fstring.py": "import os\nverb = 'add'\nos.system(f'git worktree {verb} /tmp/x')\n",
    "percent.py": "import os\nos.system('git worktree %s /tmp/x' % 'add')\n",
    "argv_loop.py": "import subprocess\nfor v in ['add']:\n    subprocess.run(['git', 'worktree', v, 'x'])\n",
    "getattr.py": "import os\ngetattr(os, 'system')('git worktree add /tmp/x')\n",
    "eval.py": "eval(\"__import__('os').system('git worktree add /tmp/x')\")\n",
    "map.py": "import os\nlist(map(os.system, ['git worktree add /tmp/x']))\n",
    "other_file.py": "from helper import sh\nsh('git worktree add /tmp/x')\n",
    "loop.js": 'for (const c of ["git worktree add /tmp/x"]) require("child_process").execSync(c);\n',
    "concat.js": 'require("child_process").execSync("git worktree " + "add /tmp/x");\n',
    "multiline.js": 'require("child_process").execFileSync(\n  "git", ["worktree", "add", "/tmp/x"]);\n',
    "concat.pl": 'my $c = "git worktree " . "add /tmp/x";\nsystem($c);\n',
    "interpolate.rb": 'v = "add"\nsystem("git worktree #{v} /tmp/x")\n',
}
# Stdlib roads a deny list of exec primitives missed: each runs the phrase with no listed name, module or dynamic reach.
FILE_RUNS_STDLIB = {
    "methodcaller.py": "import os, operator\noperator.methodcaller('system', 'git worktree add /tmp/x')(os)\n",
    "timeit.py": "import timeit\ntimeit.timeit(\"import os; os.system('git worktree add /tmp/x')\", number=1)\n",
    "partial.py": "import os, functools\nfunctools.partial(os.system, 'git worktree add /tmp/x')()\n",
    "doctest_run.py": (
        "import doctest\n"
        "doctest.run_docstring_examples(\">>> import os; os.system('git worktree add /tmp/x')\", {})\n"
    ),
    "attrgetter.py": "import os, operator\noperator.attrgetter('system')(os)('git worktree add /tmp/x')\n",
    "upper.py": "import os\nos.system('GIT WORKTREE ADD /tmp/x'.lower())\n",
    "adjacent.py": "import os\nos.system('git work' 'tree add /tmp/x')\n",
    "built_verb.py": "import os\nv = 'a' + 'dd'\nos.system(f'git worktree {v} /tmp/x')\n",
    "deno.ts": 'new Deno.Command("git", { args: ["worktree", "add", "/tmp/x"] }).outputSync();\n',
}
# THE FAIL-CLOSED COST, intended: a file that only lists the phrase as data is refused while untracked; committed and unchanged, it runs unread.
FILE_MENTIONS = {
    "table.py": 'CASES = [("plain", "git worktree add /tmp/wt main", True)]\nprint(len(CASES))\n',
    "argv_table.py": 'CASES = [["git", "worktree", "add", "x"], ("run", "./run.sh worktree create x")]\n',
    "check.py": 'def check(c):\n    return len(c)\ncheck("git worktree add /tmp/x")\n',
    "port_table.py": (
        "from rediacc_ci.dev import worktree\nCASES = [['create', 'x']]\n"
        "print(worktree.__doc__, CASES)\n"
    ),
    "table.js": 'const cases = ["git worktree add /tmp/x", ["git", "worktree", "add"]];\nconsole.log(cases);\n',
    "table.pl": 'my @cases = ("git worktree add /tmp/x");\nprint scalar(@cases);\n',
    "built_table.py": "CASES = ['git worktree ' + 'add x', f'git worktree {1}', 'git worktree %s' % 'add']\nprint(CASES)\n",
    "os_path.py": "import os\nprint(os.path.join('a', 'b'), 'git worktree add /tmp/x')\n",
    "doc_read.py": "import helper\nprint(helper.__doc__, 'git worktree add /tmp/x')\n",
    "commented.js": '// run the cases below\nconst cases = ["git worktree " + "add /tmp/x"];\nconsole.log(cases);\n',
}
# A file that never names the phrase runs, whatever it runs.
FILE_SILENT = {
    "list_only.py": "import subprocess\nrepo = '.'\nsubprocess.run(['git', '-C', repo, 'worktree', 'list'])\n",
    "status.py": "import os, subprocess\nos.system('git status')\nsubprocess.run(['ls'])\n",
    "address.py": "print('worktree', 'address', 'added', 'creates')\n",
    "run.js": 'require("child_process").execSync("git status");\n',
    "run.pl": 'system("git", "status");\n',
}
INTERPRETER = {".py": "python3", ".js": "node", ".pl": "perl", ".rb": "ruby", ".ts": "deno run"}


@pytest.mark.xdist_group("hooks-fixtures")
def test_block_worktree_add_judges_a_script_by_its_text(tmp_path):
    block = hookblocks.Block("worktree-add-file-text")
    spec_deny = "check 2 guards/block_worktree_add.py"
    spec_allow = "check 0 guards/block_worktree_add.py"
    denied = {**FILE_RUNS, **FILE_RUNS_UNTRACED, **FILE_RUNS_STDLIB, **FILE_MENTIONS}
    (tmp_path / "deny").mkdir()
    (tmp_path / "allow").mkdir()
    for name, text in denied.items():
        (tmp_path / "deny" / name).write_text(text, encoding="utf-8")
    for name, text in FILE_SILENT.items():
        (tmp_path / "allow" / name).write_text(text, encoding="utf-8")
    for name in denied:
        run_ = "%s %s" % (INTERPRETER[os.path.splitext(name)[1]], tmp_path / "deny" / name)
        block.check(spec_deny, bash_json(run_), "worktree-add: a file naming it: " + name)
    for name in FILE_SILENT:
        run_ = "%s %s" % (INTERPRETER[os.path.splitext(name)[1]], tmp_path / "allow" / name)
        block.check(
            spec_allow, bash_json(run_), "worktree-add CONTROL: a file never naming it: " + name
        )
    # The same files from a cd, and directly by a shebang.
    block.check(
        spec_deny,
        bash_json("cd %s && python3 table.py" % (tmp_path / "deny")),
        "worktree-add: a mentioning file from a cd",
    )
    mention = tmp_path / "direct_mention.py"
    mention.write_text("#!/usr/bin/env python3\n" + FILE_MENTIONS["table.py"], encoding="utf-8")
    mention.chmod(0o755)
    block.check(spec_deny, bash_json(str(mention)), "worktree-add: a mentioning file by shebang")
    # A command line is still judged by its text, whatever file it also runs.
    block.check(
        spec_deny,
        bash_json("git worktree add /tmp/x && python3 %s" % (tmp_path / "allow" / "status.py")),
        "worktree-add: the command line itself is git worktree add",
    )
    block.check(
        spec_allow,
        bash_json("python3 -c 'print(\"never run git worktree add here\")'"),
        "worktree-add CONTROL: a -c program printing a sentence is still judged by its calls",
    )
    block.done()


def test_block_worktree_add_script_refusal_names_the_rule(tmp_path):
    """A script refused for naming the phrase says so, and does not claim a verb was found running in program text."""
    table = tmp_path / "table.py"
    table.write_text(FILE_MENTIONS["table.py"], encoding="utf-8")
    rc, _out, err = dispatch.run_one("block_worktree_add", bash_json("python3 %s" % table))
    assert rc == 2
    assert "names `worktree` together with `add`" in err
    assert "found inside the program text" not in err
    # CONTROL: the same text in a tracked, unchanged file is not read. A second file, because shellscan caches the tracked answer per file for the process.
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "table.py").write_text(FILE_MENTIONS["table.py"], encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "table.py")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")
    rc, _out, err = dispatch.run_one(
        "block_worktree_add", bash_json("python3 %s" % (repo / "table.py"))
    )
    assert rc == 0, err


def test_shebang_interpreter_does_not_open_a_named_pipe(tmp_path):
    """Review 05c4df4d.4: a FIFO named as a command word is not a script, and opening it would block the hook until a writer appears."""
    fifo = tmp_path / "pipe.py"
    os.mkfifo(fifo)
    program = (
        "import sys\nfrom rediacc_hooks import shellscan\n"
        "run = next(iter(shellscan.every_run(sys.argv[1])))\n"
        "print(shellscan.shebang_interpreter(run, None))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", program, str(fifo)],
        cwd=str(ROOT / ".claude"),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "None"


def test_a_script_written_then_run_by_its_shebang_is_read_from_the_write(tmp_path):
    """#7ab88f34: a script an earlier run of the same command writes and a later one runs DIRECTLY by path does not exist when the hook runs. Its shebang and its program are what the write puts there, read with or without the command in hand; a write the walk cannot read is unjudgeable."""
    script = tmp_path / "x.py"
    printed = "printf '#!/usr/bin/env python3\\nprint(1)\\n' > %s; chmod +x %s; %s" % (
        script,
        script,
        script,
    )
    direct = shellscan.every_run(printed)[-1]
    assert direct.name == str(script)
    assert not script.exists()
    assert shellscan.shebang_interpreter(direct, str(tmp_path)) == "python3"
    assert shellscan.interpreter_program(direct, printed, str(tmp_path)) == (
        "#!/usr/bin/env python3\nprint(1)\n\n",
        "file",
    )
    copied = "cp /nowhere/tool %s && %s" % (script, script)
    assert shellscan.interpreter_program(
        shellscan.every_run(copied)[-1], copied, str(tmp_path)
    ) == (None, "unjudgeable")
    # CONTROLS: a written shebang naming a shell is not an interpreter run, and a script nothing in the command writes still reads the disk (absent here, so nothing).
    shell = "printf '#!/bin/sh\\necho 1\\n' > %s; %s" % (script, script)
    assert shellscan.interpreter_program(shellscan.every_run(shell)[-1], shell, None) == (
        None,
        None,
    )
    assert shellscan.interpreter_program(
        shellscan.every_run(str(script))[-1], str(script), None
    ) == (None, None)


def test_program_prefilter_admits_a_script_behind_a_wrapper_word():
    """Review 05c4df4d.3: `timeout 5 ./wt.py` and `nohup ./long.py` name a script by path, so the pre-filter must start the lexer for them."""
    for cmd in ("timeout 5 ./wt.py", "nohup ./long.py", "env X=1 /tmp/s.py", "sudo ../x/y.py"):
        assert shellscan.PROGRAM_PREFILTER.search(cmd), cmd
    # CONTROL: a command with no path word and no interpreter word is still skipped.
    assert not shellscan.PROGRAM_PREFILTER.search("git status --short")


def test_block_worktree_add_unjudgeable_script_is_not_said_to_hold_a_verb():
    """Review 6f52f7ff.4: an unreadable script is refused, and the refusal must not claim a verb was found inside program text."""
    unreadable = bash_json(
        "cp /tmp/a.py /tmp/wt-78afdc0b.py && python3 /tmp/wt-78afdc0b.py worktree add x"
    )
    found = bash_json("python3 -c 'import os; os.system(\"git worktree add /tmp/x\")'")
    rc, _out, err = dispatch.run_one("block_worktree_add", unreadable)
    assert rc == 2
    assert "cannot read" in err
    assert "found inside the program text" not in err
    # CONTROL: a verb found in program text still carries the note.
    rc, _out, err = dispatch.run_one("block_worktree_add", found)
    assert rc == 2
    assert "found inside the program text" in err


# A SCRIPT THE HOOK CANNOT READ IN FULL WAS ALLOWED. An untracked shell script or python program past `shellscan._SCRIPT_MAX`, one the hook may not open, a directory or zip python runs, and a program handed over as `<(...)` or /dev/fd/N each ran `git worktree add` with rc 0 unless the command line itself spelled the verb (2026-10-15). Each is now refused unless tracked and unchanged from HEAD.
WT_PHRASE_PY = "import os\nos.system('git worktree add /tmp/x')\n"


def _oversize(path, tail):
    line = "#" + "x" * 1023 + "\n"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(line * ((shellscan._SCRIPT_MAX // len(line)) + 1))
        handle.write(tail)
    assert os.path.getsize(path) > shellscan._SCRIPT_MAX


def _worktree_rc(command, cwd):
    rc, _out, err = dispatch.run_one(
        "block_worktree_add",
        json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}),
    )
    return rc, err


def test_a_script_the_guard_cannot_read_in_full_is_refused(tmp_path, monkeypatch):
    # The command line must not spell the verb itself, or the older command-line pre-filter refuses it and the case proves nothing.
    assert "worktree" not in str(tmp_path).lower(), tmp_path
    big_sh = tmp_path / "big.sh"
    _oversize(big_sh, "git worktree add /tmp/x\n")
    big_sh.chmod(0o755)
    big_py = tmp_path / "big.py"
    _oversize(big_py, WT_PHRASE_PY)
    locked_sh = tmp_path / "locked.sh"
    locked_sh.write_text("git worktree add /tmp/x\n", encoding="utf-8")
    locked_py = tmp_path / "locked.py"
    locked_py.write_text(WT_PHRASE_PY, encoding="utf-8")
    locked_sh.chmod(0)
    locked_py.chmod(0)
    if os.geteuid() == 0:
        # Root opens a mode-0 file, so the refusal is driven by an open that fails the way it fails for any other user.
        real_open = open

        def denied(path, *args, **kwargs):
            if str(path) in (str(locked_sh), str(locked_py)):
                raise PermissionError(13, "Permission denied", str(path))
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(
            dispatch.guards.load("block_worktree_add"), "open", denied, raising=False
        )
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__main__.py").write_text(WT_PHRASE_PY, encoding="utf-8")
    wrong = []
    try:
        for command in (
            "bash %s" % big_sh,
            str(big_sh),
            "source %s" % big_sh,
            "python3 %s" % big_py,
            "bash %s" % locked_sh,
            "python3 %s" % locked_py,
            "python3 %s" % pkg,
            "python3 <(cat %s)" % locked_py,
            "bash <(cat %s)" % locked_sh,
            "python3 /dev/fd/3 3< %s" % big_py,
        ):
            rc, err = _worktree_rc(command, tmp_path)
            if rc != 2 or "could not read in full" not in err or "`!`" not in err:
                wrong.append((command, rc, err[:120]))
            assert "found inside the program text" not in err, command
        # CONTROLS: a tracked, unchanged oversize script is reviewed code and runs unread; a compiled program run directly, /dev/null, and a path that does not exist are not scripts the hook must read.
        repo = tmp_path / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        _oversize(repo / "big.sh", "git worktree add /tmp/x\n")
        _oversize(repo / "big.py", WT_PHRASE_PY)
        git(repo, "add", "big.sh", "big.py")
        git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")
        for command in (
            "bash %s" % (repo / "big.sh"),
            "python3 %s" % (repo / "big.py"),
            "/usr/bin/env true",
            "bash /dev/null",
            "python3 %s" % (tmp_path / "absent.py"),
        ):
            rc, err = _worktree_rc(command, tmp_path)
            assert rc == 0, (command, err)
        assert not wrong, "\n".join(map(repr, wrong))
    finally:
        locked_sh.chmod(0o600)
        locked_py.chmod(0o600)


# A PROGRAM READ ON STDIN IS JUDGED BY ITS TEXT, WHEREVER THE TEXT COMES FROM (review 0d227c80.1, .2 and a sibling). `python3 /dev/stdin <<'EOF'` was refused as an unreadable descriptor although its program is on the command line, `python3 - < p.py` and its spellings ran a file holding `git worktree add` with rc 0 because only heredocs, here-strings and piped words were read, and a script path holding a NUL raised ValueError out of the guard, which the dispatcher counts as no decision (2026-10-15).
WT_ARGV_PY = 'import subprocess\nsubprocess.run(["git", "worktree", "add", "/tmp/x"])\n'


def test_a_program_read_on_stdin_is_judged_by_its_text(tmp_path):
    # The command line must not spell the verb itself, or the older command-line pre-filter refuses it and the case proves nothing.
    assert "worktree" not in str(tmp_path).lower(), tmp_path
    (tmp_path / "p.py").write_text(WT_ARGV_PY, encoding="utf-8")
    (tmp_path / "x.sh").write_text("git worktree add /tmp/x\n", encoding="utf-8")
    wrong = []
    for command, needle in (
        ("python3 - < p.py", "names `worktree`"),
        ("python3 /dev/stdin < p.py", "names `worktree`"),
        ("python3 < %s" % (tmp_path / "p.py"), "names `worktree`"),
        ("python3 - 0< p.py", "names `worktree`"),
        ("cat p.py | python3 -", "names `worktree`"),
        ("{ python3 -; } < p.py", "names `worktree`"),
        ("cat p.py | (python3 -)", "names `worktree`"),
        ("node - < p.py", "names `worktree`"),
        ("bash < x.sh", "names `worktree`"),
        ('sh -c "python3 - < p.py"', "names `worktree`"),
        ("python3 - < <(cat p.py)", "could not read in full"),
        ("python3 - < /dev/fd/3", "could not read in full"),
        ("python3 /dev/stdin <<'EOF'\n%sEOF" % WT_ARGV_PY, "git worktree add is not run"),
        ("python3 $'p.py\\0x'", "could not read in full"),
        ("python3 'p.py\0x'", "could not read in full"),
        ("python3 - < $'p.py\\0x'", "could not read in full"),
    ):
        # A raise here is the 0d227c80.1 defect itself, so it is recorded as a wrong verdict rather than ending the loop.
        try:
            rc, err = _worktree_rc(command, tmp_path)
        except ValueError as exc:
            rc, err = "raised", repr(exc)
        if rc != 2 or needle not in err:
            wrong.append((command, rc, err[:120]))
    # CONTROLS: a stdin program that runs nothing, through each stdin spelling; a file on stdin that is tracked and unchanged, absent, /dev/null, or on another descriptor; the shell's own stdin.
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "p.py").write_text(WT_ARGV_PY, encoding="utf-8")
    git(repo, "add", "p.py")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")
    for command in (
        "python3 /dev/stdin <<'EOF'\nprint(1)\nEOF",
        "python3 /dev/fd/0 <<'EOF'\nprint(1)\nEOF",
        "python3 /proc/self/fd/0 <<< 'print(1)'",
        "python3 - <<'EOF'\nprint(1)\nEOF",
        "node /dev/stdin <<< 'console.log(1)'",
        "perl /dev/fd/0 <<'EOF'\nprint 1\nEOF",
        "ruby -- /dev/stdin <<'EOF'\nputs 1\nEOF",
        "python3 - < %s" % (repo / "p.py"),
        "python3 - < absent.py",
        "bash < absent.sh",
        "python3 - < /dev/null",
        "python3 - 3< p.py",
        "python3 - < /dev/stdin",
    ):
        rc, err = _worktree_rc(command, tmp_path)
        if rc != 0:
            wrong.append((command, rc, err[:120]))
    # A descriptor other than 0 is still not the program's stdin, so the shell supplies a file the hook does not read.
    rc, err = _worktree_rc("python3 /dev/fd/3 3<<'EOF'\nprint(1)\nEOF", tmp_path)
    if rc != 2 or "could not read in full" not in err:
        wrong.append(("/dev/fd/3", rc, err[:120]))
    assert not wrong, "\n".join(map(repr, wrong))


# A STDIN THE HOOK CANNOT READ IS REFUSED (#faca6bd7). At c5f0fd121 a program read through a duplicated descriptor (`python3 - <&3 3< p.py`) and one piped from a producer whose output the command line does not hold (`git show HEAD:p.py | python3 -`) both ran with rc 0. A `<&N` is now followed to what opens N, and a stdin program fed by any other producer is refused naming it; a pipe into a `-c`/`-e` program or a script file carries data and still passes.
def test_a_stdin_program_from_a_source_the_hook_cannot_read_is_refused(tmp_path):
    # The command line must not spell the verb itself, or the older command-line pre-filter refuses it and the case proves nothing.
    assert "worktree" not in str(tmp_path).lower(), tmp_path
    (tmp_path / "p.py").write_text(WT_ARGV_PY, encoding="utf-8")
    (tmp_path / "x.sh").write_text("git worktree add /tmp/x\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("print(1)\n", encoding="utf-8")
    unread = "reads on stdin from"
    wrong = []
    for command, needle in (
        # A duplicated descriptor is the file the command line opens on it, in either order, through a group, an `exec`, a move or a chain.
        ("python3 - <&3 3< p.py", "names `worktree`"),
        ("python3 - 3< p.py <&3", "names `worktree`"),
        ("python3 - 0<&3 3<>p.py", "names `worktree`"),
        ("{ python3 - <&3; } 3<p.py", "names `worktree`"),
        ("exec 3<p.py; python3 - <&3", "names `worktree`"),
        ("python3 - <&3- 3<p.py", "names `worktree`"),
        ("python3 - <&3 3<&4 4<p.py", "names `worktree`"),
        ("node - <&3 3<p.py", "names `worktree`"),
        ("perl <&3 3<p.py", "names `worktree`"),
        ("ruby <&3 3<p.py", "names `worktree`"),
        ("bash <&3 3<x.sh", "names `worktree`"),
        ("bash -s <&4 4<x.sh", "names `worktree`"),
        ("cat <&3 3<p.py | python3 -", "names `worktree`"),
        # A descriptor the command line does not open is supplied by the shell, so it is unread.
        ("python3 - <&3", "descriptor 3"),
        ("python3 - <&1", "descriptor 1"),
        ("python3 - <&$fd {fd}<p.py", "a descriptor named by"),
        ("cat <&5 | python3 -", "descriptor 5"),
        # A producer whose output the command line does not hold, into every stdin spelling and family, and through a group, a subshell, `sh -c`, `eval`, a passing `cat` and a prefix command.
        ("git show HEAD:p.py | python3 -", "`git show HEAD:p.py`"),
        ("curl -s http://example.invalid/p.py | python3 -", "`curl -s"),
        ("some_tool | bash", "`some_tool`"),
        ("git show HEAD:p.py | python3", unread),
        ("git show HEAD:p.py | python3 -u", unread),
        ("git show HEAD:p.py | python3 /dev/stdin", unread),
        ("git show HEAD:p.py | node -", unread),
        ("git show HEAD:p.py | node /dev/stdin", unread),
        ("git show HEAD:p.py | perl", unread),
        ("git show HEAD:p.py | ruby", unread),
        ("git show HEAD:x.sh | bash -s", unread),
        ("git show HEAD:x.sh | sh", unread),
        ("git show HEAD:x.sh | zsh", unread),
        ("git show HEAD:p.py | { python3 -; }", unread),
        ("git show HEAD:p.py | (python3 -)", unread),
        ('sh -c "git show HEAD:p.py | python3 -"', unread),
        ("git show HEAD:p.py | sh -c 'python3 -'", unread),
        ("git show HEAD:p.py | eval python3 -", unread),
        ("git show HEAD:p.py | cat | python3 -", unread),
        ("git show HEAD:p.py | (cat - | python3 -)", unread),
        ("git show HEAD:p.py | timeout 5 python3 -", unread),
        ("git show HEAD:p.py | uv run python -", unread),
        ("git show HEAD:p.py | python3 - <&0", unread),
        ("git show HEAD:p.py | python3 - <&3 3<&0", unread),
        ("{ git show HEAD:p.py; } | python3 -", "a subshell or brace group"),
        # A readable source still reaches the program through the paths the pipe now follows.
        ("cat p.py | sh -c 'python3 -'", "names `worktree`"),
        ("{ cat | python3 -; } < p.py", "names `worktree`"),
    ):
        rc, err = _worktree_rc(command, tmp_path)
        if rc != 2 or needle not in err or "`!`" not in err:
            wrong.append((command, rc, err[:160]))
    # CONTROLS: a pipe into an interpreter whose program is `-c`/`-e`, a module or a script file is data; a known source whose text runs nothing; `<&-` and `<&0`; a descriptor opened on a benign file or heredoc, or on a file that does not exist; a redirect that replaces the pipe.
    for command in (
        "echo x | python3 -c 'import sys; print(sys.stdin.read())'",
        "jq . f.json | python3 -c 'import sys; print(sys.stdin.read())'",
        "cat data.txt | python3 script.py",
        "git log | python3 ok.py",
        "git log | python3 -m json.tool",
        "git log | node -e 'process.stdin.pipe(process.stdout)'",
        "git log | perl -ne 'print'",
        "git log | ruby -e 'puts STDIN.read'",
        "git log | bash -c 'wc -l'",
        "git log | sh script.sh",
        "git log | wc -l",
        "cat ok.py | python3 -",
        "echo 'print(1)' | python3 -",
        "printf 'print(1)\\n' | python3",
        "echo x | cat | python3 -",
        "echo 'print(1)' | sh -c 'python3 -'",
        "git log | cat ok.py | python3 -",
        "python3 - <<'EOF'\nprint(1)\nEOF",
        "python3 -",
        "python3 - <&-",
        "git log | python3 - <&-",
        "python3 - <&0",
        "python3 - <&3 3<ok.py",
        "python3 - <&3 3<<'EOF'\nprint(1)\nEOF",
        "python3 - <&3 3<absent.py",
        "git log | python3 - < ok.py",
    ):
        rc, err = _worktree_rc(command, tmp_path)
        if rc != 0:
            wrong.append((command, rc, err[:160]))
    assert not wrong, "\n".join(map(repr, wrong))


# DENO, BUN AND TSX PROGRAMS ARE JUDGED BY THEIR TEXT (#80712245). At 4132c3f7e the guard had no reader for deno or bun: `deno eval`, `bun -e`/`--eval`/`-p`/`--print`, `bun exec`, `deno run -`/`bun run -` on a heredoc, a file or a pipe, `deno run -c <config> x.ts` and `deno serve x.ts` all ran `git worktree add` with rc 0; tsx's `-e`, `watch` and `--tsconfig` were missed the same way.
WT_DENO = "new Deno.Command('git',{args:['worktree','add','/tmp/x']}).outputSync()"
WT_BUN = "Bun.spawnSync(['git','worktree','add','/tmp/x'])"


def test_deno_and_bun_programs_are_judged_by_their_text(tmp_path):
    # The command line must not spell the verb itself unless the case says so, or the command-line pre-filter refuses it and the case proves nothing.
    assert "worktree" not in str(tmp_path).lower(), tmp_path
    (tmp_path / "p.py").write_text(WT_ARGV_PY, encoding="utf-8")
    (tmp_path / "x.ts").write_text(WT_DENO + "\n", encoding="utf-8")
    (tmp_path / "ok.ts").write_text("console.log(1)\n", encoding="utf-8")
    found = "git worktree add is not run"
    script = "names `worktree`"
    unread = "reads on stdin from"
    wrong = []
    for command, needle in (
        ('deno eval "%s"' % WT_DENO, found),
        ('deno eval -p "%s"' % WT_DENO, found),
        ('deno repl --eval "%s"' % WT_DENO, found),
        ('bun -e "%s"' % WT_BUN, found),
        ('bun --eval "%s"' % WT_BUN, found),
        ('bun --eval="%s"' % WT_BUN, found),
        ('bun -p "%s"' % WT_BUN, found),
        ('bun --print "%s"' % WT_BUN, found),
        ('bun exec "git worktree add /tmp/x"', found),
        ("tsx -e \"require('child_process').execSync('git worktree add /tmp/x')\"", found),
        ('deno run "data:text/javascript,%s"' % WT_DENO.replace(" ", "%20"), found),
        # A program on stdin: a heredoc, a file, and a pipe from a producer the hook cannot read.
        ("deno run - <<'EOF'\n%s\nEOF" % WT_DENO, found),
        ("deno run - < p.py", script),
        ("deno - < p.py", script),
        ("bun - < p.py", script),
        ("bun run - < p.py", script),
        ("git show HEAD:x.ts | deno run -", unread),
        ("git show HEAD:x.ts | bun run -", unread),
        ("git show HEAD:x.ts | deno", unread),
        ("git show HEAD:x.ts | tsx", unread),
        # A script by path, through every option walk.
        ("deno run x.ts", script),
        ("deno run -A x.ts", script),
        ("deno -A x.ts", script),
        ("deno x.ts", script),
        ("deno run -c deno.json x.ts", script),
        ("deno run --allow-read=/tmp,/etc x.ts", script),
        ("deno serve x.ts", script),
        ("bun x.ts", script),
        ("bun run x.ts", script),
        ("bun --cwd . run x.ts", script),
        ("bun run --smol x.ts", script),
        ("tsx --tsconfig t.json x.ts", script),
        ("tsx watch x.ts", script),
        ("deno run https://example.invalid/x.ts", "could not read in full"),
        # An option the walk does not know hides the operand, so a command line that could spell the verb is refused.
        ("deno run --frobnicate worktree add x.ts", "cannot read"),
    ):
        rc, err = _worktree_rc(command, tmp_path)
        if rc != 2 or needle not in err:
            wrong.append((command, rc, err[:160]))
    # CONTROLS: a program that runs nothing, a benign script, a package.json script NAME that is no file, no program at all, and an unknown option on a command line that cannot spell the verb.
    for command in (
        'deno eval "console.log(1)"',
        'bun -e "console.log(1)"',
        'tsx -e "console.log(1)"',
        "deno run ok.ts",
        "bun ok.ts",
        "bun run build",
        "bun build",
        'bun exec "ls -la"',
        "deno --version",
        "bun --version",
        "deno fmt",
        "deno",
        "deno run npm:cowsay",
        "deno run --frobnicate ok.ts",
    ):
        rc, err = _worktree_rc(command, tmp_path)
        if rc != 0:
            wrong.append((command, rc, err[:160]))
    # A script tracked and unchanged from HEAD is reviewed code and is not read.
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "x.ts").write_text(WT_DENO + "\n", encoding="utf-8")
    git(repo, "add", "x.ts")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")
    for command in ("deno run x.ts", "bun run x.ts"):
        rc, err = _worktree_rc(command, repo)
        if rc != 0:
            wrong.append(("tracked: " + command, rc, err[:160]))
    assert not wrong, "\n".join(map(repr, wrong))


# A PIPE READ THROUGH /dev/stdin, AND A PIPE AN INLINE PROGRAM EVALUATES, IS A PROGRAM (13fdcda2.1, 13fdcda2.2). At 13fdcda23 `git show HEAD:p.py | python3 - < /dev/stdin` and `... | cat /dev/stdin | python3 -` ran with rc 0 because /dev/stdin was taken for a file, and `git show HEAD:p.py | python3 -c 'import sys; exec(sys.stdin.read())'` ran with rc 0 because a pipe into `-c` was read as data whatever the program did with it.
def test_a_pipe_through_dev_stdin_or_into_an_evaluator_is_a_program(tmp_path):
    assert "worktree" not in str(tmp_path).lower(), tmp_path
    (tmp_path / "p.py").write_text(WT_ARGV_PY, encoding="utf-8")
    unread = "reads on stdin from"
    wrong = []
    for command, needle in (
        ("git show HEAD:p.py | python3 - < /dev/stdin", unread),
        ("git show HEAD:p.py | python3 - < /dev/fd/0", unread),
        ("git show HEAD:p.py | cat /dev/stdin | python3 -", unread),
        ("git show HEAD:p.py | cat /proc/self/fd/0 | python3 -", unread),
        ("git show HEAD:p.py | python3 - <&3 3</dev/stdin", unread),
        ("git show HEAD:p.py | python3 -c 'import sys; exec(sys.stdin.read())'", unread),
        ("git show HEAD:p.py | python3 -c 'exec(open(0).read())'", unread),
        ('git show HEAD:p.py | node -e \'eval(require("fs").readFileSync(0,"utf8"))\'', unread),
        ("git show HEAD:p.py | perl -e 'eval join \"\", <STDIN>'", unread),
        ("git show HEAD:p.py | ruby -e 'eval STDIN.read'", unread),
        (
            "git show HEAD:p.py | deno eval 'eval(await new Response(Deno.stdin.readable).text())'",
            unread,
        ),
        ("cat p.py | python3 -c 'import sys; exec(sys.stdin.read())'", "names `worktree`"),
        ("python3 -c 'import sys; exec(sys.stdin.read())' < p.py", "names `worktree`"),
        (
            "echo 'git worktree add /tmp/x' | python3 -c 'import os,sys; os.system(sys.stdin.read())'",
            "git worktree add is not run",
        ),
    ):
        rc, err = _worktree_rc(command, tmp_path)
        if rc != 2 or needle not in err:
            wrong.append((command, rc, err[:160]))
    # CONTROLS: a program that reads stdin and evaluates nothing takes the pipe as data; a benign program evaluated from a known source; /dev/stdin with no pipe in front.
    for command in (
        "echo x | python3 -c 'import sys; print(sys.stdin.read())'",
        "git log | python3 -c 'import json,sys; print(json.loads(sys.stdin.read()))'",
        "git log | node -e 'process.stdin.pipe(process.stdout)'",
        "git log | ruby -e 'puts STDIN.read'",
        "git log | perl -ne 'print'",
        "echo 'print(1)' | python3 -c 'import sys; exec(sys.stdin.read())'",
        "git log | python3 -c 'import subprocess; subprocess.run([\"ls\"])'",
        "python3 - < /dev/stdin",
        "echo 'print(1)' | cat /dev/stdin | python3 -",
    ):
        rc, err = _worktree_rc(command, tmp_path)
        if rc != 0:
            wrong.append((command, rc, err[:160]))
    assert not wrong, "\n".join(map(repr, wrong))


# REVIEW c5f0fd12.1-.3 AND db1e9409.1-.2 ON THE STDIN READERS. .1 and .2 were closed by db1e94091 before this test existed and are pinned here; .3 (a `..` after a directory symlink read lexically) and db1e9409.1 (a descriptor held in a name) ran `git worktree add` with rc 0 at bd4ead963. db1e9409.2: `eval(console)` reads no stdin, so its pipe is data.
def test_stdin_spellings_review_c5f0fd12_and_db1e9409(tmp_path):
    assert "worktree" not in str(tmp_path).lower(), tmp_path
    (tmp_path / "p.py").write_text(WT_ARGV_PY, encoding="utf-8")
    (tmp_path / "ok.py").write_text("print(1)\n", encoding="utf-8")
    deep = tmp_path / "a" / "b" / "c" / "d" / "e" / "f" / "g"
    deep.mkdir(parents=True)
    (tmp_path / "lnk").symlink_to(deep, target_is_directory=True)
    (tmp_path / "a" / "b" / "c" / "d" / "e" / "f" / "q.py").write_text(WT_ARGV_PY, encoding="utf-8")
    # As many `..` as `lnk` is deep reach / by the text and `a/` by the kernel.
    spelled = str(tmp_path / "lnk") + "/.." * len(tmp_path.parts) + "/dev/stdin"
    assert os.path.normpath(spelled) == "/dev/stdin", spelled
    landed = pathlib.Path(os.path.realpath(os.path.dirname(spelled)))
    assert landed.is_relative_to(tmp_path), landed
    landed.mkdir(parents=True, exist_ok=True)
    (landed / "stdin").write_text(WT_ARGV_PY, encoding="utf-8")
    unread = "reads on stdin from"
    script = "names `worktree`"
    wrong = []
    for command, needle in (
        ("git show HEAD:p.py | python3 /dev/stdin", unread),
        ("git show HEAD:p.py | python3 /dev/fd/0", unread),
        ("cat p.py | python3 /dev/stdin", script),
        ("cat p.py | cat | python3 -", script),
        ("{ cat p.py; } | python3 -", "subshell or brace group"),
        ("( cat p.py ) | python3 -", "subshell or brace group"),
        ("echo 'print(1)' | python3 %s" % spelled, script),
        ("python3 %s" % spelled, script),
        ("python3 lnk/../q.py", script),
        (
            'git show HEAD:p.py | node -e \'const fd=0; eval(require("fs").readFileSync(fd,"utf8"))\'',
            unread,
        ),
        ("git show HEAD:p.py | node -e 'let d = 0; eval(require(\"fs\").readFileSync(d))'", unread),
        (
            (
                'git show HEAD:p.py | node -e \'require("fs").createReadStream(null,{fd:0})'
                '.on("data",c=>eval(String(c)))\''
            ),
            unread,
        ),
        ("git show HEAD:p.py | python3 -c 'import os; d=0; exec(os.read(d, 1 << 20))'", unread),
    ):
        rc, err = _worktree_rc(command, tmp_path)
        if rc != 2 or needle not in err:
            wrong.append((command, rc, err[:160]))
    # CONTROLS: the same spellings over a benign program, a plain `..` through a real directory, a descriptor that is not stdin, and a program that names `console` and reads no stdin.
    for command in (
        "echo 'print(1)' | python3 /dev/stdin",
        "echo 'print(1)' | cat | python3 -",
        "python3 a/../ok.py",
        'git log | node -e \'const fd=1; require("fs").writeSync(fd, "x")\'',
        "git show HEAD:p.py | node -e 'eval(console)'",
        "git log | node -e 'console.log(eval(\"1+1\"))'",
        "git log | python3 -c 'import json; print(json.load(open(\"ok.json\")))'",
    ):
        rc, err = _worktree_rc(command, tmp_path)
        if rc != 0:
            wrong.append((command, rc, err[:160]))
    assert not wrong, "\n".join(map(repr, wrong))


# ONE PROGRAM PARSE FOR EVERY GUARD (#a2599946). At bd4ead963 `shellscan._program_parse` read deno, bun and tsx with node's table after a leading `run`, so the words in the `was` column are what every shell-write guard and block_long_sleep took for the program; and it returned the FIRST inline program, where node runs the last and perl and ruby join them all (measured on node v24.21.0 and perl 5.40.1).
PROGRAM_PARSE_ROWS = [
    # (base, argv, now, was)
    ("deno", ["eval", "x"], ("inline", "x"), ("file", "eval")),
    ("deno", ["run", "-c", "cfg.json", "x.ts"], ("file", "x.ts"), ("file", "cfg.json")),
    ("deno", ["serve", "x.ts"], ("file", "x.ts"), ("file", "serve")),
    ("deno", ["run", "https://e.invalid/x.ts"], ("remote", "https://e.invalid/x.ts"), None),
    ("deno", ["fmt"], ("none", None), None),
    ("deno", ["--version"], ("none", None), None),
    ("deno", ["run", "npm:cowsay"], ("none", None), None),
    ("deno", ["test"], ("unjudgeable", "`deno test`"), None),
    ("deno", ["run", "-"], ("stdin", None), None),
    ("bun", ["exec", "echo hi"], ("shell", "echo hi"), ("file", "exec")),
    ("bun", ["build"], ("none", None), None),
    ("bun", ["x", "cowsay"], ("none", None), None),
    ("bun", ["test"], ("unjudgeable", "`bun test`"), None),
    ("bun", ["-e", "A", "-e", "B"], ("inline", "A\nB"), ("inline", "A")),
    ("bunx", ["cowsay"], ("none", None), ("file", "cowsay")),
    ("tsx", ["watch", "x.ts"], ("file", "x.ts"), ("file", "watch")),
    ("tsx", ["--tsconfig", "t.json", "x.ts"], ("file", "x.ts"), ("file", "t.json")),
    ("tsx", ["-e", "A", "-e", "B"], ("inline", "B"), ("inline", "A")),
    ("tsx", ["scripts/foo.ts"], ("file", "scripts/foo.ts"), None),
    ("node", ["-e", "A", "-r", "fs", "-e", "B"], ("inline", "B"), ("inline", "A")),
    ("node", ["-e", "A", "foo", "-e", "B"], ("inline", "A"), None),
    ("node", ["-pe", "P"], ("inline", "P"), ("inline", "e")),
    ("perl", ["-e", "A", "-e", "B"], ("inline", "A\nB"), ("inline", "A")),
    ("perl", ["-le", "A", "-e", "B"], ("inline", "A\nB"), ("inline", "A")),
    ("ruby", ["-e", "A", "-e", "B"], ("inline", "A\nB"), ("inline", "A")),
    # Unchanged: python's `-c` ends its options, and the rest of the table.
    ("python3", ["-c", "A", "-c", "B"], ("inline", "A"), None),
    ("python3", ["-W", "ignore", "-"], ("stdin", None), None),
    ("python3", ["-m", "json.tool"], ("module", None), None),
    ("python3", ["-E", "s.py"], ("file", "s.py"), None),
    ("node", ["x.js"], ("file", "x.js"), None),
    ("node", [], ("stdin", None), None),
    ("perl", ["-I", "lib", "-e", "A"], ("inline", "A"), None),
]


def test_program_parse_reads_each_interpreter_as_it_does():
    wrong = [
        (base, argv, shellscan.program_parse(base, argv), now)
        for base, argv, now, _was in PROGRAM_PARSE_ROWS
        if shellscan.program_parse(base, argv) != now
    ]
    assert not wrong, "\n".join(map(repr, wrong))
    # The rows that moved must have read differently before, or they pin nothing.
    assert sum(1 for row in PROGRAM_PARSE_ROWS if row[3] is not None) >= 10


def test_interpreter_program_maps_runtime_kinds(tmp_path):
    """`interpreter_program` hands a guard no reason text: a remote module and an option the walk does not know are `(None, "unjudgeable")`; a `bun exec` line and a line with no program are `(None, None)`."""
    (tmp_path / "x.ts").write_text("console.log(1)\n", encoding="utf-8")
    for command, want in (
        ("deno run https://e.invalid/x.ts", (None, "unjudgeable")),
        ("deno run --frobnicate x.ts", (None, "unjudgeable")),
        ("deno test", (None, "unjudgeable")),
        ("deno fmt", (None, None)),
        ("bunx cowsay", (None, None)),
        ("deno eval 'console.log(2)'", ("console.log(2)", "inline")),
        ("deno run -c cfg.json x.ts", ("console.log(1)\n", "file")),
    ):
        run = shellscan.every_run(command)[0]
        assert shellscan.interpreter_program(run, command, str(tmp_path)) == want, command
    # A `bun exec` line is walked as runs of its own, so the command inside it is a run every guard sees.
    command = "bun exec 'echo y > out.md'"
    assert shellscan.interpreter_program(shellscan.every_run(command)[0], command) == (None, None)
    assert [r.name for r in shellscan.every_run(command)] == ["bun", "echo"]
    assert shellscan.every_run(command)[1].writes == ["out.md"]


# THE RUNTIME LINES EVERY GUARD READS (#a2599946). Each `deny` row was allowed (rc 0) at bd4ead963: the shell-write guards and block_long_sleep read `cfg.json`, `serve`, `watch` or `t.json` as the script, block_review_file_shell_write named no deno, bun or tsx at all, block_suppressions_shell_write missed a `-` after an option's value, and nothing walked the line inside `bun exec`.
_NQ = "no" + "qa"
_RUNTIME_W = 'require("fs").writeFileSync("a.py","x = 1  # %s\\n")' % _NQ
_RUNTIME_R = 'require("fs").writeFileSync("agent/reviews/x.md","x\\n")'
_RUNTIME_U = 'require("fs").writeFileSync(".ci/config/model-invocation-exceptions.json","x\\n")'
_RUNTIME_S = 'Deno.Command("sh",{args:["-c","sleep 900"]}).outputSync()'
_LOG = "agent/pr-babysit-1008-1.md"
RUNTIME_GUARD_ROWS = [
    ("block_long_sleep", 2, "deno eval 'x(\"sleep 900\")'"),
    ("block_long_sleep", 2, "deno run -c cfg.json s.ts"),
    ("block_long_sleep", 2, "deno serve s.ts"),
    ("block_long_sleep", 2, "tsx watch s.ts"),
    ("block_long_sleep", 2, "tsx --tsconfig t.json s.ts"),
    ("block_long_sleep", 2, 'bun exec "sleep 900"'),
    ("block_long_sleep", 2, "bun -e 'x(\"sleep 900\")'"),
    ("block_long_sleep", 2, "node -e 'console.log(1)' -e 'x(\"sleep 900\")'"),
    ("block_long_sleep", 2, "node -pe 'x(\"sleep 900\")'"),
    ("block_long_sleep", 2, "perl -e 'print 1;' -e 'system(\"sleep 900\")'"),
    ("block_long_sleep", 2, "tsx -e 'console.log(1)' -e 'x(\"sleep 900\")'"),
    ("block_long_sleep", 0, "deno run -c cfg.json ok.ts"),
    ("block_long_sleep", 0, 'bun exec "sleep 5"'),
    ("block_long_sleep", 0, "node -e 'x(\"sleep 5\")' -e 'console.log(1)'"),
    # An option the walk does not know is unjudgeable, which this guard leaves alone by design (`_program_texts`).
    ("block_long_sleep", 0, "deno run --frobnicate s.ts"),
    ("block_suppressions_shell_write", 2, "deno run -c cfg.json w.ts"),
    ("block_suppressions_shell_write", 2, "deno serve w.ts"),
    ("block_suppressions_shell_write", 2, "tsx watch w.ts"),
    ("block_suppressions_shell_write", 2, "tsx --tsconfig t.json w.ts"),
    ("block_suppressions_shell_write", 2, "deno run - <<'EOF'\n%s\nEOF" % _RUNTIME_W),
    (
        "block_suppressions_shell_write",
        2,
        "python3 -W ignore - <<'EOF'\nopen('a.py','w').write('x = 1  # %s')\nEOF" % _NQ,
    ),
    ("block_suppressions_shell_write", 2, "bun exec 'echo \"x = 1  # %s\" > a.py'" % _NQ),
    ("block_suppressions_shell_write", 2, "deno run --frobnicate w.ts --tag=%s" % _NQ),
    ("block_suppressions_shell_write", 2, "deno eval '%s'" % _RUNTIME_W),
    ("block_suppressions_shell_write", 0, "deno run -c cfg.json ok.ts"),
    ("block_suppressions_shell_write", 0, "bun exec ls"),
    ("block_review_file_shell_write", 2, "deno eval '%s'" % _RUNTIME_R),
    ("block_review_file_shell_write", 2, "bun -e '%s'" % _RUNTIME_R),
    ("block_review_file_shell_write", 2, "tsx -e '%s'" % _RUNTIME_R),
    ("block_review_file_shell_write", 2, "deno run - <<'EOF'\n%s\nEOF" % _RUNTIME_R),
    ("block_review_file_shell_write", 2, "bun exec 'echo y > agent/reviews/x.md'"),
    ("block_review_file_shell_write", 2, "deno run -c cfg.json r.ts"),
    ("block_review_file_shell_write", 2, "deno serve r.ts"),
    ("block_review_file_shell_write", 2, "tsx watch r.ts"),
    ("block_review_file_shell_write", 2, "tsx --tsconfig t.json r.ts"),
    (
        "block_review_file_shell_write",
        0,
        "deno eval 'console.log(Deno.readTextFileSync(\"agent/reviews/x.md\"))'",
    ),
    ("block_review_file_shell_write", 0, "deno run -c cfg.json ok.ts"),
    (
        "block_user_only_command_shell_write",
        2,
        "bun exec 'echo x > .ci/config/model-invocation-exceptions.json'",
    ),
    ("block_user_only_command_shell_write", 2, "deno run -c cfg.json u.ts"),
    ("block_user_only_command_shell_write", 2, "deno serve u.ts"),
    ("block_user_only_command_shell_write", 2, "tsx watch u.ts"),
    ("block_user_only_command_shell_write", 2, "tsx --tsconfig t.json u.ts"),
    ("block_user_only_command_shell_write", 2, "deno eval '%s'" % _RUNTIME_U),
    (
        "block_user_only_command_shell_write",
        0,
        "bun exec 'cat .ci/config/model-invocation-exceptions.json'",
    ),
    ("block_roundlog_truncate", 2, "tsx --tsconfig t.json l.js %s" % _LOG),
    ("block_roundlog_truncate", 2, "deno run -c cfg.json l.js %s" % _LOG),
    ("block_roundlog_truncate", 2, "bun exec 'echo > %s'" % _LOG),
    ("block_roundlog_truncate", 0, "tsx --tsconfig t.json ok.ts %s" % _LOG),
]


def test_runtime_lines_are_read_by_every_guard(tmp_path):
    files = {
        "cfg.json": "{}\n",
        "t.json": "{}\n",
        "ok.ts": "console.log(1)\n",
        "s.ts": _RUNTIME_S + "\n",
        "w.ts": _RUNTIME_W + "\n",
        "r.ts": _RUNTIME_R + "\n",
        "u.ts": _RUNTIME_U + "\n",
        "l.js": 'require("fs").writeFileSync(process.argv[2],"")\n',
    }
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    wrong = []
    for stem, want, command in RUNTIME_GUARD_ROWS:
        rc, _out, err = dispatch.run_one(
            stem,
            json.dumps(
                {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(tmp_path)}
            ),
        )
        if rc != want:
            wrong.append((stem, want, rc, command, err[:160]))
    assert len(RUNTIME_GUARD_ROWS) >= 40
    assert not wrong, "\n".join(map(repr, wrong))


# --- block_untagged_commit: the id cases need a REAL epic to judge against ----- THE EPIC ID IS RESOLVED, NEVER FROZEN. An earlier read of this block hardcoded the id that happened to be in the tree the day it was written, which is the same class of defect as the branch resolution below: it passes on one machine and asserts something else everywhere else.
#
# AND RESOLVE THE BRANCH THE WAY CI ACTUALLY PRESENTS IT. `git rev-parse --abbrev-ref HEAD` prints the literal string "HEAD" in a detached checkout, which is EVERY pull_request run -- actions/checkout lands on refs/pull/N/merge. Measured 2026-08-27: this block looked for `agent/pr/HEAD.md`, did not find it, and failed the suite in CI while passing on every developer machine. The
# precondition was right to refuse a vacuous pass; it was wrong to treat CI's normal state as a broken one.
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
    if found:
        return found.group(1), relative
    # NO SNAPSHOT: the guard falls back to agent/worklist/epics.jsonl (block_untagged_commit._ledger_epic_ids), so a real id comes from the same ledger. A placeholder id here failed three cases on any branch that had not published its snapshot yet (measured 2026-10-04 on 1004-1, before agent/pr/1004-1.md existed).
    try:
        for line in (
            (pathlib.Path(root) / "agent" / "worklist" / "epics.jsonl")
            .read_text(encoding="utf-8", errors="replace")
            .splitlines()
        ):
            row = json.loads(line) if line.strip() else {}
            if isinstance(row, dict) and row.get("id"):
                return str(row["id"]), relative
    except (OSError, ValueError):
        pass
    return None, relative


@pytest.mark.xdist_group("hooks-fixtures")
def test_block_untagged_commit_reads_the_message_it_is_given(tmp_path):
    block = hookblocks.Block("untagged-commit")
    epic, relative = resolve_epic()
    # With no snapshot the guard judges against the epic ledger instead, so resolve_epic draws a real id from it; only a tree with neither falls back to the placeholder, where the guard has no set and allows any well-formed trailer.
    identifier = epic or "f2757830"
    block.check(
        "check 0 guards/block_untagged_commit.py",
        bash_json('git commit -m "feat(x): a thing\n\nPR-TASK: %s"' % identifier),
        "untagged-commit CONTROL: a real trailer passes",
    )
    # `-F` USED TO BE EXEMPTED OUTRIGHT, and that is the form every message longer than one line uses -- 36 consecutive commits in one session passed this guard without it ever looking at them. Two of the three "unreadable" shapes were never unreadable: a heredoc BODY is in the command string, and a -F file is on disk.
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
    # A TYPO IS WORSE THAN A MISSING TRAILER: it LOOKS tagged, so `git log --grep` finds no epic, the per-epic review never selects the commit, and nothing reports the gap. Shape alone cannot see this; the id is checked against the committed snapshot, so this case needs one.
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


# --- warn_remote_drift, then the pr-babysit ROUND LOG guards ------------------ warn_remote_drift needs a real repo pair (a bare origin, a stale local), because its subject is git state, not the command string. The origin is a filesystem path so the hook's fetch works offline.
#
# ONE TEST FOR THE WHOLE SEQUENCE, deliberately. The round-log cases below ran inside the same exported CLAUDE_PROJECT_DIR as the drift cases in the suite this ports, and splitting them would silently change what the guards resolve against.
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

    # On 2026-08-19 a heartbeat tick refreshed the STATUS block with `p.write_text(s[:i] + new)`, which replaces from the STATUS heading to END OF FILE and silently deleted the entire round-history appendix, on a file with no backup. Two guards close it: a pre-edit one for whole-file tool writes, and a pre-bash one for the Bash heredoc that actually did it. Both must also NOT block
    # the legitimate shapes, which is why every deny below has an allow beside it.
    heredoc = (
        "python3 - <<'PY'\nfrom pathlib import Path\n"
        "p=Path('%s'); s=p.read_text(); i=s.index('## STATUS')\n"
        "p.write_text(s[:i] + new)\nPY" % RLOG
    )
    # EXISTENCE IS WHAT DECIDES NOW, so the fixture has to have it. This case used a path under /home/x/ that has never existed, and passed for the wrong reason: the guard was refusing on the NAME alone. That also refused CREATING a round log -- and `worklist.py --roundlog` refuses to create one too, so the two halves of the contract deadlocked with no third door.
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
    # A NAME IS NOT A TARGET. The python arm used to fire on any write idiom as soon as a round-log name appeared ANYWHERE in the command. Measured 2026-08-27: it refused a heredoc editing a scratchpad state-body file whose CONTENT quoted a round-log path -- a write that could not have touched a round log.
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
    # FAIL CLOSED, and this is the case that makes the narrowing safe rather than merely quieter: no resolvable literal target, a slicing write_text, a round-log name in the command. That is the 2026-08-19 shape verbatim and it must still fire.
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
    # PYTHON COPY AND MOVE ARE WRITES TOO. The shell half has refused `cp` and `mv` onto a round log since it was written; their python spelling was never covered, so shutil.copy and os.replace onto the log both returned 0 -- a one-line rename walked through a guard that read as thorough. Measured 2026-08-27.
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
    # And the control that keeps the new arm from becoming a blanket refusal: a copy between two innocent paths, with the log named only in a comment.
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
    # THE UNDER-BLOCK REGRESSIONS, found in review 2026-08-19 and each reproduced against the live hook before it was fixed. All three are ways a command that genuinely TRUNCATES the log was waved through, which is worse than an over-block: the guard reported safety it was not providing.
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
    # cp names the log as a SOURCE here, which is a read, and backing the log up is the most useful thing a session can do with it. mv in the same position is NOT a read: it removes the log from its path, so the two verbs are deliberately different.
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
    # THE OVER-BLOCK REGRESSIONS. Found in review, then reproduced twice against the live hook within minutes: the truncating verbs were matched ANYWHERE in the command rather than anchored to the log, so `truncate` hit the harness's own filename and a bare `cp`/`mv` hit a copy of unrelated files that merely shared a command line with a round-log READ. The guard blocked `cat
    # <log>`.
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


# THE DEADLOCK CHECK, and it is an INTERACTION -- which is why neither side's own cases could see it. Tested in isolation both parties were correct: `worklist.py --roundlog` refuses to create a log ("Write the wave header first"), and the guard refuses whole-file writes to a round log. Put them in sequence and there was NO DOOR AT ALL: the verb sends you to Write, and Write was
# refused. A session following the documented path could not create a round log, which is exactly what happened on 2026-08-27 when one tried.
#
# So the assertion is about the PAIR: for a log that does not exist yet, the two must not BOTH refuse. Whichever way a future change moves the responsibility -- guard exempts creation, or the verb learns to create -- this stays true; it only goes red
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
    # CONTROL: the probe must be measuring a real refusal from the verb, or the assertion above passes because the verb happily creates logs -- a different world, and one this case would be silent about.
    block.note(
        0,
        "roundlog CONTROL: the verb does refuse to create, so the pair check is not vacuous",
        ok=verb_rc != 0,
        detail="the verb no longer refuses to create -- re-read the pair check above, "
        "it now proves nothing",
    )
    shutil.rmtree(log.parent.parent, ignore_errors=True)
