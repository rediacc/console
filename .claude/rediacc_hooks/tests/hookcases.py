"""The guard smoke suite, as data: every case `.claude/hooks/test-hooks.sh` asserts.

WHY THIS IS A PYTHON MODULE AND NOT A SECOND SHELL SCRIPT. The obvious move for a 2,774-line bash suite is to shard it into several smaller ones. That is ILLEGAL in this tree and the refusal is mechanical, not stylistic: `check:ci-language-policy` freezes a SET of 521 bash paths under `.ci/` and `.claude/`
(`.ci/scripts/quality/check_language_policy.py:137` `COVERED_ROOTS = (".ci", ".claude")`),
and a new tracked `.sh` under either root is a 522nd entry that `baseline_additions` refuses. `.claude/hooks/test-hooks.sh` is itself entry 472 of that 521. The precedent a shard would reach for -- `test-worklist-v5.sh` split into 27 files -- predates the freeze and cannot be repeated. So the suite is PORTED, which is what `.ci/rediacc_ci/tests/gates/test_gate_claude_hooks.py:31`
already says in code, and pytest already collects this directory (`pyproject.toml` `testpaths`), so the destination needed no wiring.

THE SPEC STRING IN COLUMN 1 IS LOAD-BEARING TEXT, NOT A LABEL. Read it before editing one. `hook_integrity.covmap` decides whether a guard still has a BLOCK case and an ALLOW case by scanning its declared `case_sources` for the literal shape

    check 2 guards/block_x.py

(`.ci/rediacc_ci/quality/hook_integrity.py:459`, `\\b(?:check|check_out)\\s+([0-9]+)\\s+<guard>`). That reader is what credits a guard with coverage, and a port that spelled its cases `case(2, "guards/block_x.py", ...)` would present ZERO cases for all 46 ported guards -- every one of them reading as newly uncovered, whose cheapest fix is to baseline them, which retires the
assertion for good. Keeping the case's identity as one string in the reader's own shape means the port re-keys DATA (`scripts/data/hook-audit-scope.json` `case_sources`) and the reader is never opened.

WHAT DID NOT CHANGE. Every payload, every expected exit code, every message needle and every label below is the one the bash suite asserted. The proof is the label multiset: `hooklabels.py` reads `ok [rc] label` lines out of whatever a suite printed, and it is the SAME function on both sides, so "the port asserts what the suite asserted" is a comparison of two runs rather than a
claim about a diff.

HOW A CASE NAMES ITS GUARD. By the key `check-hook-integrity.sh` inventories it under: `guards/<module>.py` for the 46 guards ported in W5 -- the file really is at `.claude/rediacc_hooks/guards/<module>.py` and the way to RUN one is the dispatcher -- and the path under `.claude/hooks/` for anything still in bash.
"""

import dataclasses
import datetime
import json
import subprocess

from rediacc_hooks.tests import corpus

ROOT = corpus.repo_root()
HOOKS = ROOT / ".claude" / "hooks"
GUARD_DISPATCH = ROOT / ".claude" / "rediacc_hooks" / "dispatch.py"
GUARD_MODULES = ROOT / ".claude" / "rediacc_hooks" / "guards"

# The suite derived this with `cd "$DIR/../.." && pwd`. Two cases used to hardcode /home/developer/console and therefore asserted "inside the repo" about a path that
# is inside the repo only on the machine they were written on; in CI the tree is at
# /home/runner/work/... and the guard CORRECTLY allowed the command, so the tests
# failed while the code was right. Measured: run 33133377611, PASS=1557 FAIL=2.
TEST_REPO_ROOT = str(ROOT)

# How long any single guard may take. The bash suite had no bound at all, so a guard
# that hangs on stdin took the whole run down with it and reported nothing; this
# turns that into one named failure.
GUARD_TIMEOUT_S = 60


class GuardKeyError(LookupError):
    """A case names a guard key that resolves to no program.

    A NAMED FAILURE, because the alternative is worse than a miss. `python3 dispatch.py <typo>` raises ModuleNotFoundError and exits 1, which a case expecting 2 reports as a plain wrong-exit and a case expecting 0 reports as a failure -- both of them wrong about the reason.
    """


def guard_cmd(key: str) -> list[str]:
    """The argv that runs the guard `key` names."""
    if key.startswith("guards/") and key.endswith(".py"):
        stem = key[len("guards/") : -len(".py")]
        module = GUARD_MODULES / (stem + ".py")
        if not module.is_file():
            raise GuardKeyError("guard key %s names no module (%s absent)" % (key, module))
        return ["python3", str(GUARD_DISPATCH), stem]
    program = HOOKS / key
    if not program.is_file():
        raise GuardKeyError("guard key %s names no file (%s absent)" % (key, program))
    return ["bash", str(program)]


# --- the payload builders, one per event shape the suite feeds ---------------- Transcribed from the suite's seven `printf` one-liners. `guardcorpus.BUILDERS` carries the same table for the differential and compares itself against the suite on every run, which is what stops the two transcriptions drifting apart.


def _j(obj: object) -> str:
    """The suite's payloads, byte for byte.

    `jq -Rn --arg c ... '$c'` emits COMPACT json and does not escape non-ASCII. Python's defaults do the opposite on both counts, and a guard that matches on
    raw text (require-jq.sh greps stdin; several guards scan the command string
    before parsing) would be handed different bytes than the suite handed it.
    """
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def bash_json(command: str) -> str:
    return _j({"tool_input": {"command": command}})


def bash_bg_json(command: str) -> str:
    """Same, but flagged as a harness background task.

    block_long_sleep raises its sleep cap for these: a long sleep only costs anything in the foreground.
    """
    return _j({"tool_input": {"command": command, "run_in_background": True}})


def edit_json(new_string: str) -> str:
    return _j({"tool_input": {"new_string": new_string}})


def multiedit_json(new_string: str) -> str:
    return _j({"tool_input": {"edits": [{"new_string": new_string}]}})


def wf_edit_json(file_path: str, new_string: str) -> str:
    """An Edit payload carrying a target file path."""
    return _j({"tool_input": {"file_path": file_path, "new_string": new_string}})


def tool_json(tool_name: str, file_path: str, field: str, value: str) -> str:
    return _j({"tool_name": tool_name, "tool_input": {"file_path": file_path, field: value}})


def ask_json(question: str) -> str:
    return _j({"tool_input": {"questions": [{"question": question, "header": "x"}]}})


def path_json(file_path: str) -> str:
    return _j({"tool_input": {"file_path": file_path}})


EMPTY_INPUT = _j({"tool_input": {}})


def inject_json(command: str, stdout: str) -> str:
    """A PostToolUse payload: the trapguard rules judge what a command SAID."""
    return _j(
        {
            "tool_name": "Bash",
            "cwd": TEST_REPO_ROOT,
            "tool_input": {"command": command},
            "tool_response": {"stdout": stdout, "stderr": ""},
        }
    )


def inject_killed(command: str, stdout: str, interrupted: bool) -> str:
    return _j(
        {
            "tool_name": "Bash",
            "cwd": TEST_REPO_ROOT,
            "tool_input": {"command": command},
            "tool_response": {"stdout": stdout, "stderr": "", "interrupted": interrupted},
        }
    )


@dataclasses.dataclass(frozen=True)
class Case:
    """One assertion: run `key` on `payload` and expect `expected`.

    `spec` is kept verbatim because it is what `hook_integrity.covmap` reads; `verb`,
    `expected` and `key` are parsed OUT of it rather than passed separately, so the two can never disagree.
    """

    spec: str
    payload: str
    label: str
    needle: str | None = None

    @property
    def verb(self) -> str:
        return self.spec.split()[0]

    @property
    def expected(self) -> int:
        return int(self.spec.split()[1])

    @property
    def key(self) -> str:
        return self.spec.split()[2]


def case(spec: str, payload: str, label: str, needle: str | None = None) -> Case:
    """One row of the corpus. See the module docstring on `spec`'s spelling."""
    parts = spec.split()
    if len(parts) != 3 or parts[0] not in ("check", "check_out"):
        raise ValueError("case spec must read '<check|check_out> <rc> <guard-key>': %r" % spec)
    if not parts[1].isdigit():
        raise ValueError("case spec's second word must be the expected exit code: %r" % spec)
    if (needle is None) != (parts[0] == "check"):
        raise ValueError("check_out takes a needle and check does not: %r" % spec)
    return Case(spec=spec, payload=payload, label=label, needle=needle)


def run_guard(
    key: str, payload: str, *, want_stderr: bool, env: dict | None = None, cwd: str | None = None
) -> tuple[int, str]:
    """`(exit code, stderr text)`. stdout is discarded, exactly as the suite did.

    The suite ran `... 2>&1 >/dev/null` for the message assertions, which redirects stderr to the pipe and stdout to /dev/null -- NOT the other way round. A guard's product is what it says on stderr.
    """
    argv = guard_cmd(key)
    completed = subprocess.run(
        argv,
        input=payload.encode(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE if want_stderr else subprocess.DEVNULL,
        env=env,
        cwd=cwd,
        timeout=GUARD_TIMEOUT_S,
        check=False,
    )
    err = completed.stderr.decode("utf-8", "replace") if want_stderr else ""
    return completed.returncode, err


# The corpus. Every entry below is one case of the bash suite, in file order, with the comment that explained it. Cases whose payload needs a FIXTURE -- a temporary git repo, a PATH stub, a live process -- are not here: they cannot be data, so they live in test_hooks_fixtures.py beside the code that builds what they need.
STATIC: list[Case] = [
    # --- should BLOCK (exit 2) --- The PR body is generated, so a hand-written whole-body write silently drops the worklist-epics block and CI fails minutes later naming nothing useful.
    case(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json("gh pr edit 42 --body-file b.md"),
        "raw-pr-body(blocked)",
    ),
    case(
        "check 0 guards/block_raw_pr_body_edit.py",
        bash_json(".ci/scripts/pr/sync-epic-block.sh 42 0826-1"),
        "raw-pr-body(tool passes)",
    ),
    # The edit arm requires EVERY generated marker, not just the epic one. This case asserted the opposite for a few hours on 2026-09-03 and was WRONG: the edit form writes the WHOLE body, and these PR bodies carry a second machine-written section, pushed-head. A body carrying only the epic block therefore passes a one-marker check and silently destroys the other section -- the
    # exact loss this guard exists to prevent, arriving through the door the narrowing opened.
    #
    # So: carrying ONE marker is refused, carrying BOTH passes. The pair below is the whole rule, and the first half is the one that was briefly inverted.
    case(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json(
            'gh pr edit 42 --body "prose <!-- worklist-epics:begin --> x <!-- worklist-epics:end -->"'
        ),
        "raw-pr-body: an edit carrying ONLY the epic block still drops pushed-head",
    ),
    case(
        "check 0 guards/block_raw_pr_body_edit.py",
        bash_json(
            'gh pr edit 42 --body "prose <!-- worklist-epics:begin --> x <!-- worklist-epics:end --> <!-- pushed-head:begin --> y <!-- pushed-head:end -->"'
        ),
        "raw-pr-body CONTROL: an edit carrying EVERY generated marker passes",
    ),
    case(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json('gh pr edit 42 --body "prose with no block at all"'),
        "raw-pr-body(edit dropping the block blocked)",
    ),
    case(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json("gh pr edit 42 --body-file /nonexistent-body.md"),
        "raw-pr-body(edit with an unreadable body still blocked)",
    ),
    # THE PRE-PUSH RECEIPT GUARD. A CI round costs ~15 minutes; three of the five
    # reds on PR #579 were sub-2-second gates -- check:format 1.72s, check:ci-python-lint 0.59s, check:ci-parity 1.29s -- which cost roughly 45
    # minutes of CI between them. The gates existed; nothing made anyone run them.
    #
    # Only the ALLOW direction is pinned here, deliberately. The refusal arms need a receipt file planted at a specific tree sha, which is fixture work this
    # suite's `check` helper cannot express; they live in the dedicated gate suite
    # instead. What these four pin is the half that decides whether the guard is tolerable: a guard that refuses things it has no business refusing is a guard that gets bypassed, and every one of these ran green before the guard existed.
    case(
        "check 0 guards/block_unverified_push.py",
        bash_json("git status"),
        "unverified-push CONTROL: a non-push is out of scope",
    ),
    case(
        "check 0 guards/block_unverified_push.py",
        bash_json("git push --dry-run origin 0827-1"),
        "unverified-push CONTROL: a dry run publishes nothing, so it buys no CI round",
    ),
    case(
        "check 0 guards/block_unverified_push.py",
        bash_json("echo 'remember to git push once green'"),
        "unverified-push CONTROL: prose about pushing is not a push",
    ),
    case(
        "check 0 guards/block_unverified_push.py",
        bash_json("cd private/account && git push origin 0827-1"),
        "unverified-push CONTROL: a submodule push advances no console branch",
    ),
    case(
        "check 0 guards/block_raw_pr_body_edit.py",
        bash_json("gh pr edit 42 --add-label ci"),
        "raw-pr-body(non-body passes)",
    ),
    # CONTROL: prose ABOUT the rule is not a violation of it. The first version blocked this, which is the false-positive class block-commit-meta.sh warns of.
    case(
        "check 0 guards/block_raw_pr_body_edit.py",
        bash_json('echo "never use gh pr edit --body by hand"'),
        "raw-pr-body(prose passes)",
    ),
    case(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json('gh pr create --draft --body "x"'),
        "raw-pr-body: CREATE --body with no epic block is refused (was allowed)",
    ),
    case(
        "check 0 guards/block_raw_pr_body_edit.py",
        bash_json('gh pr create --draft --body "x <!-- worklist-epics:begin --> y"'),
        "raw-pr-body CONTROL: CREATE --body that ALREADY carries the block passes",
    ),
    case(
        "check 0 guards/block_raw_pr_body_edit.py",
        bash_json("gh pr create --draft --title t --fill"),
        "raw-pr-body CONTROL: CREATE with no body flag is out of scope",
    ),
    case(
        "check 0 guards/block_raw_pr_body_edit.py",
        bash_json(
            'gh pr create --draft --body "x <!-- worklist-epics:begin --> y" && gh pr edit 42 --add-label a'
        ),
        "raw-pr-body CONTROL: the edit's --add-label is not the create's --body",
    ),
    case(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json("gh api repos/o/r/pulls/42 -X PATCH -F body=@$S/body.md"),
        "raw-pr-body: PATCH with a path behind a shell variable is unreadable, refused",
    ),
    case(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json('gh api repos/o/r/pulls/42 -X PATCH -f body="prose only"'),
        "raw-pr-body: PATCH with an inline body and no block is refused",
    ),
    case(
        "check 0 guards/block_raw_pr_body_edit.py",
        bash_json(
            'gh api repos/o/r/pulls/42 --method PATCH -f body="x <!-- worklist-epics:begin --> y <!-- pushed-head:begin --> z"'
        ),
        "raw-pr-body CONTROL: PATCH inline body carrying every marker passes",
    ),
    case(
        "check 0 guards/block_raw_pr_body_edit.py",
        bash_json("gh api repos/o/r/pulls/42 -X PATCH -F title=t"),
        "raw-pr-body CONTROL: PATCH that touches no body is out of scope",
    ),
    case(
        "check 0 guards/block_raw_pr_body_edit.py",
        bash_json("gh api repos/o/r/pulls/42 --jq .body"),
        "raw-pr-body CONTROL: a GET of the body is not a write",
    ),
    case(
        "check_out 2 guards/block_raw_pr_body_edit.py",
        bash_json('gh pr edit 42 --body "prose"'),
        "raw-pr-body: the refusal prescribes the PATCH form the sanctioned guard accepts",
        "-X PATCH -F body=@",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("git checkout .claude/settings.json"),
        "protected-files",
    ),
    case(
        "check 2 guards/block_commit_meta.py",
        bash_json("git commit -m msg Co-Authored-By: bot"),
        "commit-meta",
    ),
    case(
        "check 2 guards/block_binary_deploy.py",
        bash_json("scp renet host:/tmp"),
        "binary-deploy",
    ),
    case(
        "check 2 guards/block_cli_bundle.py",
        bash_json("node packages/cli/dist/x.js"),
        "cli-bundle",
    ),
    # ALLOW CASES FOR THE FOUR GUARDS ABOVE, and they are not a formality. Until 2026-08-27 each of these had exactly one block case and NOTHING asserting it
    # let anything through, so nobody had ever measured the other direction. When
    # somebody finally did, every one of the four was over-blocking:
    #
    # block-cli-bundle refused `node packages/cli/bundle.mjs`, this repo's OWN build entry (package.json build:bundle) block-commit-meta refused `grep -rn 'co-authored-by' docs/` -- searching for the banned trailer, i.e. auditing the rule the guard enforces block-binary-deploy refused pulling a LOG back from a host, which is the opposite of deploying a binary block-protected-files
    # refused `git checkout main && cat .claude/settings.json`, because `.*` in its pattern spanned the `&&`
    #
    # All four now require EXECUTION INTENT rather than a matching substring. That is one bug in four places, and it is the same bug the guards written to catch it kept committing: twelve mention-as-execution false positives in one session, including one where a guard blocked its own repair.
    case(
        "check 0 guards/block_cli_bundle.py",
        bash_json("node packages/cli/bundle.mjs"),
        "cli-bundle CONTROL: the repo's own build entry is not the bundle",
    ),
    case(
        "check 0 guards/block_cli_bundle.py",
        bash_json("node scripts/x.mjs --outdir packages/cli/dist"),
        "cli-bundle CONTROL: the path is an output flag, not the program",
    ),
    case(
        "check 0 guards/block_commit_meta.py",
        bash_json("grep -rn 'co-authored-by' docs/"),
        "commit-meta CONTROL: GREPPING for the banned trailer is how you audit it",
    ),
    case(
        "check 0 guards/block_commit_meta.py",
        bash_json('echo "the rule bans Co-Authored-By lines"'),
        "commit-meta CONTROL: prose naming the rule is not a violation of it",
    ),
    # THE GAP MUST NOT CROSS A CLAUSE, and the first draft of the commit-verb gate
    # let it. `git ...* (commit|tag)` has to tolerate flags between the verb and its
    # subcommand, but a gap of "any non-space token" spans `|` and `&&` too, so a `git log` in one clause and the word `commit` in another read as a commit carrying a trailer. Same defect, same day, same fix as block-protected-files.
    case(
        "check 0 guards/block_commit_meta.py",
        bash_json("git log --oneline | grep commit | grep co-authored-by"),
        "commit-meta CONTROL: a git verb and the word commit in DIFFERENT clauses",
    ),
    case(
        "check 0 guards/block_commit_meta.py",
        bash_json("git diff HEAD~1 && echo commit && echo Co-Authored-By"),
        "commit-meta CONTROL: the gap does not span two && clauses",
    ),
    # And the enforcement shapes the gate has to keep reaching. Narrowing a guard without pinning what it must still catch is how the next narrowing goes too far.
    case(
        "check 2 guards/block_commit_meta.py",
        bash_json("git -C private/account commit -m x --trailer Co-Authored-By=bot"),
        "commit-meta: git -C <path> commit is still reached",
    ),
    case(
        "check 2 guards/block_commit_meta.py",
        bash_json("git commit -a -m x --trailer Co-Authored-By=bot"),
        "commit-meta: flags between the verb and the subcommand are still reached",
    ),
    case(
        "check 2 guards/block_commit_meta.py",
        bash_json("git tag -a v1 -m Co-Authored-By:bot"),
        "commit-meta: a tag message carries the same rule",
    ),
    case(
        "check 2 guards/block_commit_meta.py",
        bash_json("gh pr create --body Co-Authored-By:bot"),
        "commit-meta: a PR body carries it too",
    ),
    case(
        "check 0 guards/block_binary_deploy.py",
        bash_json("scp host:/var/log/renet.log ./logs/"),
        "binary-deploy CONTROL: pulling a log back is diagnosis, not a deploy",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("git checkout main && cat .claude/settings.json"),
        "protected-files CONTROL: checkout then READ is not a restore",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("grep -n hooks .claude/settings.json"),
        "protected-files CONTROL: reading the file is untouched",
    ),
    # ECHOING A BANNED COMMAND IS NOT RUNNING IT. Several guards matched their raw command text, so a string merely NAMING the thing they guard was refused -- `echo '<banned command>'`, a doc quoting a recipe, a commit message. A sweep on 2026-08-27 asked this of all 48 block cases at once and 17 fired, where reading the guards one at a time had found four. The ones below were
    # routed through lib/command-scan.sh in response: it strips heredoc bodies and quoted prose while still EXTRACTING `sh -c` and `eval` payloads. The anti-evasion cases that follow are what make that claim checkable rather than a hope.
    #
    # THREE GUARDS WERE DELIBERATELY LEFT ALONE, and the sweep is where that got decided rather than assumed. block-ci-polling, block-ci-reverse-poll and block-long-sleep keep their prose false positive under the operator's 2026-08-25 ruling (see the pinned cases further down): their failure is LOUD, every narrowing fails SILENTLY, and the shared scanner drops heredoc bodies -- the
    # option that ruling names as the most tempting and the worst. They WERE routed with the others in this sweep, and those pinned cases turned red and reverted it, which is exactly the job they were written for.
    #
    # The distinction is not arbitrary. For the guards below, a narrowing does not fail silently: the real violation is still caught, which the `sh -c` and `eval` cases assert. For the sleep/poll family, a missed match means a real poll runs and nobody is told.
    case(
        "check 0 guards/block_ssh_docker.py",
        bash_json("echo 'ssh host docker ps'"),
        "ssh-docker CONTROL: echoing it is not running it",
    ),
    case(
        "check 0 guards/block_ssh_file_write.py",
        bash_json("echo 'cat a | ssh host tee /etc/x'"),
        "ssh-file-write CONTROL: echoing it is not writing",
    ),
    case(
        "check 0 guards/block_git_amend.py",
        bash_json("echo 'git commit --amend'"),
        "git-amend CONTROL: quoting the rule is not amending",
    ),
    # AND THE EVASION THAT CAME WITH IT. Stripping quoted spans to stop this guard matching prose ALSO removed `sh -c "git commit --amend"`, where the whole command lives inside a quoted span -- the guard returned 0 on a real amend. The comment shipped alongside that draft claimed the dedicated
    # test-block-git-amend.py pinned the `sh -c` case; it did not, and the claim was
    # never checked. One probe found the false comment and the hole together, which is why these live here now rather than in a sentence.
    case(
        "check 2 guards/block_git_amend.py",
        bash_json('sh -c "git commit --amend"'),
        "git-amend: an amend hidden in sh -c is still caught",
    ),
    case(
        "check 2 guards/block_git_amend.py",
        bash_json('eval "git commit --amend"'),
        "git-amend: an amend hidden in eval is still caught",
    ),
    case(
        "check 0 guards/block_git_empty_commit.py",
        bash_json("echo 'git commit --allow-empty -m x'"),
        "git-empty-commit CONTROL: echoing it is not committing",
    ),
    # The quoted case above was pinned; the UNQUOTED one was not, and the guard
    # blocked on it until 2026-08-28. hook_scan_target strips quoted spans, so an ordinary sentence survives it intact and reached a matcher that looked for the phrase ANYWHERE. A doc line or worklist note was refused as a command.
    case(
        "check 0 guards/block_git_empty_commit.py",
        bash_json("echo never use git commit --allow-empty to retrigger CI"),
        "git-empty-commit CONTROL: unquoted prose is not a command",
    ),
    case(
        "check 0 guards/block_cli_bundle.py",
        bash_json("echo 'node packages/cli/cli-bundle.cjs'"),
        "cli-bundle CONTROL: echoing it is not running it",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("echo 'git restore .claude/settings.json'"),
        "protected-files CONTROL: echoing it is not restoring",
    ),
    # AND THE OTHER DIRECTION, which is the half that makes the narrowing safe. The scanner extracts shell-wrapper payloads, so hiding a banned command inside `sh -c` / `eval` must still be caught. Without these, "we stopped matching prose" and "we stopped matching" look identical from the outside.
    case(
        "check 2 guards/block_ci_polling.py",
        bash_json('bash -c "sleep 30 && gh run view 123"'),
        "ci-polling: polling hidden in bash -c is still caught",
    ),
    case(
        "check 2 guards/block_ssh_docker.py",
        bash_json("sh -c 'ssh host docker ps'"),
        "ssh-docker: hidden in sh -c is still caught",
    ),
    case(
        "check 2 guards/block_cli_bundle.py",
        bash_json('eval "node packages/cli/cli-bundle.cjs x"'),
        "cli-bundle: hidden in eval is still caught",
    ),
    case(
        "check 2 guards/block_git_empty_commit.py",
        bash_json('bash -c "git commit --allow-empty -m x"'),
        "git-empty-commit: hidden in bash -c is still caught",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('sh -c "git restore .claude/settings.json"'),
        "protected-files: hidden in sh -c is still caught",
    ),
    case(
        "check 2 guards/block_long_sleep.py",
        bash_json('bash -c "sleep 300"'),
        "long-sleep: hidden in bash -c is still caught",
    ),
    # THE HEREDOC CASE IS NOT NEGOTIABLE for this guard. block-long-sleep documented its prose false positive as ACCEPTED, reasoning that exempting heredoc bodies would hide the shape most likely to carry a real long sleep. That reasoning is right and it is about heredocs, not quotes -- so only the quotes were dropped, and this pins the part that was kept.
    case(
        "check 2 guards/block_long_sleep.py",
        bash_json("bash <<EOF\nsleep 300\nEOF"),
        "long-sleep: a heredoc fed to bash is still scanned",
    ),
    case(
        "check 2 guards/block_ssh_docker.py",
        bash_json("ssh host docker ps"),
        "ssh-docker",
    ),
    case(
        "check 2 guards/block_ssh_file_write.py",
        bash_json("cat a | ssh host tee /etc/x"),
        "ssh-file-write",
    ),
    # --- block-agent-browser-repo-output: two mechanisms, both exit 0 in the wild --- 1. positional flag-eating: `screenshot [selector] [path]`, an unknown --flag is eaten as [path] and the file lands in $PWD. Reproduced 2026-08-27. 2. AGENT_BROWSER_SCREENSHOT_DIR is ignored, so a bare filename resolves against $PWD (browser-probe.md:119-123: it put three untracked PNGs into a
    # repo).
    case(
        "check_out 2 guards/block_agent_browser_repo_output.py",
        bash_json("agent-browser screenshot /tmp/x.png --full-page"),
        "agent-browser: unknown flag is eaten as the output path",
        "consume it as the output PATH",
    ),
    case(
        "check_out 2 guards/block_agent_browser_repo_output.py",
        bash_json("agent-browser screenshot probe.png"),
        "agent-browser: bare filename resolves against $PWD",
        "No absolute output path",
    ),
    case(
        "check_out 2 guards/block_agent_browser_repo_output.py",
        bash_json("agent-browser screenshot %s/packages/www/x.png" % TEST_REPO_ROOT),
        "agent-browser: absolute path inside the repo",
        "is inside the repo at",
    ),
    case(
        "check 2 guards/block_agent_browser_repo_output.py",
        bash_json("agent-browser pdf out.pdf"),
        "agent-browser: pdf with a relative path",
    ),
    case(
        "check 0 guards/block_agent_browser_repo_output.py",
        bash_json("agent-browser screenshot /tmp/x.png --full"),
        "agent-browser: absolute path outside the repo is fine",
    ),
    case(
        "check 0 guards/block_agent_browser_repo_output.py",
        bash_json("agent-browser screenshot .sp-problem /tmp/sec.png"),
        "agent-browser: selector plus absolute path",
    ),
    case(
        "check 0 guards/block_agent_browser_repo_output.py",
        bash_json("agent-browser open http://localhost:4321/en"),
        "agent-browser: open writes no file",
    ),
    case(
        "check 0 guards/block_agent_browser_repo_output.py",
        bash_json("echo 'agent-browser screenshot probe.png'"),
        "agent-browser CONTROL: echoing it is not running it",
    ),
    # A compound command has more than one agent-browser segment. Selecting only the FIRST judged `open` (which has no path) and so BLOCKED a correct absolute screenshot, while a second output subcommand on the same line was never inspected at all. Both directions:
    case(
        "check 0 guards/block_agent_browser_repo_output.py",
        bash_json(
            "agent-browser open http://localhost:4321/en && agent-browser screenshot /tmp/x.png"
        ),
        "agent-browser: open then an absolute screenshot is fine",
    ),
    case(
        "check_out 2 guards/block_agent_browser_repo_output.py",
        bash_json(
            "agent-browser open http://localhost:4321/en && agent-browser screenshot %s/x.png"
            % TEST_REPO_ROOT
        ),
        "agent-browser: open then an in-repo screenshot",
        "is inside the repo at",
    ),
    case(
        "check_out 2 guards/block_agent_browser_repo_output.py",
        bash_json("agent-browser screenshot /tmp/a.png && agent-browser screenshot b.png"),
        "agent-browser: the SECOND output command is bare",
        "No absolute output path",
    ),
    # --- block-host-toolchain-run: a gate that cannot run reports no verdict --- This guard sat on disk UNREGISTERED, so the lesson it encodes had no enforcement at all. It fires only when the HOST lacks the toolchain and the devbox has it, so its allow direction is the interesting half: a host that has the tool must not be pushed anywhere.
    case(
        "check 0 guards/block_host_toolchain_run.py",
        bash_json("./run.sh devbox exec -- npm run check:ci-python-lint"),
        "host-toolchain: already routed through the devbox",
    ),
    case(
        "check 0 guards/block_host_toolchain_run.py",
        bash_json("npm run check:ci-dead-css"),
        "host-toolchain: a gate needing no extra toolchain",
    ),
    case(
        "check 0 guards/block_host_toolchain_run.py",
        bash_json("echo 'npm run check:ci-python-lint'"),
        "host-toolchain CONTROL: echoing a gate name is not running it",
    ),
    case(
        "check 0 guards/block_host_toolchain_run.py",
        bash_json("ls -la"),
        "host-toolchain: an unrelated command",
    ),
    # NPX CANNOT RESOLVE A NON-NPM BINARY. Measured 2026-08-28: `npx --yes ruff format ...` failed with an npm resolution error even though the real ruff
    # binary was on PATH the whole time; the session read that as "no ruff
    # resolves" and hand-patched two files instead. This fires on shape alone.
    case(
        "check 2 guards/block_host_toolchain_run.py",
        bash_json("npx --yes ruff format file.py"),
        "host-toolchain: npx cannot run a pinned non-npm tool",
    ),
    case(
        "check 2 guards/block_host_toolchain_run.py",
        bash_json("npx -y shfmt -l ."),
        "host-toolchain: npx misuse, short flag form",
    ),
    case(
        "check 0 guards/block_host_toolchain_run.py",
        bash_json("npx --yes tsx scripts/foo.ts"),
        "host-toolchain CONTROL: npx running an actual npm package is untouched",
    ),
    # BARE TOOL INVOCATIONS. The NEEDS table above only matches a GATE KEY in the
    # command; running the tool directly was invisible to it.
    case(
        "check 0 guards/block_host_toolchain_run.py",
        bash_json("ruff format file.py"),
        "host-toolchain: bare tool, host has it",
    ),
    case(
        "check 0 guards/block_host_toolchain_run.py",
        bash_json('git commit -m \\"note: install ruff and go before running this\\"'),
        "host-toolchain CONTROL: prose mentioning tool names is not a command",
    ),
    case(
        "check 2 guards/block_ci_polling.py",
        bash_json("sleep 5 && gh run view 1"),
        "ci-polling",
    ),
    case(
        "check 2 guards/block_ci_reverse_poll.py",
        bash_json("gh run view 1 --jq .x && sleep 5"),
        "ci-reverse-poll",
    ),
    case(
        "check 2 guards/block_long_sleep.py",
        bash_json("sleep 30"),
        "long-sleep",
    ),
    case(
        "check 2 guards/block_git_amend.py",
        bash_json("git commit --amend"),
        "git-amend",
    ),
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json("git push --force"),
        "git-force-push",
    ),
    # THE TWO SPELLINGS THE GUARD MISSED until 2026-08-23. Neither carries the word --force, and both rewrite published history: --mirror forces every ref AND deletes remote refs absent locally, and a leading + forces the ref it prefixes. Found while an agent was running an operator-approved history rewrite and the guard refused it -- dropping one word would have slipped the
    # identical push through. Command strings are CONCATENATED on purpose: the guard matches any Bash command containing these literals, including the one that edits this file.
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json("git push --mirror https://github.com/rediacc/console.git"),
        "force-push: --mirror is a force of every ref",
    ),
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json("cd /tmp/mirror.git && git push --mirror origin"),
        "force-push: --mirror behind a cd is still caught",
    ),
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json("git push origin +refs/heads/main"),
        "force-push: a leading + on a refspec forces that ref",
    ),
    # THE SHORTHAND FORMS, which the +refs/ case above did NOT cover. A refspec does not have to be refs-qualified to force, and the first fix for this guard matched only the long form: `+main:main` and `+HEAD:main` both slipped past a guard whose commit message said the hole was closed. Caught in review on PR #571. The case
    # above tested the REGEX; these test the THREAT.
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json("git push origin +main:main"),
        "force-push: a plus-prefixed branch shorthand forces too",
    ),
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json("git push origin +HEAD:main"),
        "force-push: +HEAD:<branch> is the same force in shorthand",
    ),
    # THE WRAPPER BYPASS, review-found on PR #579. Every sibling guard touched in that same PR (block-cli-bundle.sh, block-protected-files.sh, etc.) routes through lib/command-scan.sh's hook_scan_target, which unwraps eval/sh -c
    # payloads; this guard matched $CMD directly, so wrapping the forbidden push
    # left the push text preceded by a quote character instead of a line start or accepted separator, and the command-position anchor never fired. Same class as the worktree-add wrapper case above, on the one guard this file's own comment calls "the whole security story".
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json('eval "git push --force origin main"'),
        "force-push: eval wrapper bypass",
    ),
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json('sh -c "git push --force origin main"'),
        "force-push: sh -c wrapper bypass",
    ),
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json('eval "git push origin +main:main"'),
        "force-push: eval wrapper bypass, refspec form",
    ),
    case(
        "check 2 guards/block_git_empty_commit.py",
        bash_json("git commit --allow-empty -m x"),
        "git-empty-commit",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("git worktree add ../foo -b bar"),
        "worktree-add",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("git -C /some/path worktree add ../x main"),
        "worktree-add: -C before the subcommand",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json('sh -c "git worktree add ../x"'),
        "worktree-add: sh -c wrapper bypass",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("echo start; git worktree add ../x"),
        "worktree-add: after a command separator",
    ),
    # THE WRAPPER FORMS. `./run.sh worktree create` runs `git worktree add -b` inside scripts/dev/worktree.sh, so it is the same decision -- but the text this hook sees never contains "git worktree add", and the literal block matched nothing. It now also starts a devbox, so the bypass costs an image pull and a port block.
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("./run.sh worktree create"),
        "worktree-add: run.sh wrapper",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("run.sh worktree create -t"),
        "worktree-add: wrapper with flags",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("bash scripts/dev/worktree.sh create"),
        "worktree-add: interpreter prefix puts bash in command position, not the script",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("cd /x && ./run.sh worktree create"),
        "worktree-add: wrapper after a separator",
    ),
    # The OTHER subcommands must stay usable, and prose about the command must not trip it -- a detector that flags its own documentation cannot be satisfied
    # except by deleting the explanation.
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("./run.sh worktree list"),
        "worktree-add: list is not create",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("./run.sh worktree remove 0826-1"),
        "worktree-add: remove is not create",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("./run.sh worktree prune"),
        "worktree-add: prune is not create",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json('echo "run.sh worktree create is blocked"'),
        "worktree-add: prose is not an invocation",
    ),
    case(
        "check 2 guards/block_blanket_git_add.py",
        bash_json("git add -A"),
        "blanket-git-add: -A with no pathspec",
    ),
    case(
        "check 2 guards/block_blanket_git_add.py",
        bash_json("git add --all"),
        "blanket-git-add: --all with no pathspec",
    ),
    case(
        "check 2 guards/block_blanket_git_add.py",
        bash_json("git add ."),
        "blanket-git-add: a lone dot",
    ),
    case(
        "check 2 guards/block_blanket_git_add.py",
        bash_json("git add :/"),
        "blanket-git-add: the repo-root magic pathspec",
    ),
    # block-pathspecless-git-commit.sh -- the OTHER half of the blanket-add trap, and the half a correct `git add` does not protect you from. `git commit` writes the INDEX, so a peer session's staged work rides your commit. Added 2026-09-06 after it happened TWICE in one session: fifteen policy renames landed without their readers, then an hour later, after the trap was written
    # down by the same session, 108 files landed where 33 were intended.
    case(
        "check 2 pre-bash/block-pathspecless-git-commit.sh",
        bash_json('git commit -m "x"'),
        "pathspecless-commit: -m with no pathspec",
    ),
    case(
        "check 2 pre-bash/block-pathspecless-git-commit.sh",
        bash_json("git commit"),
        "pathspecless-commit: the bare form",
    ),
    case(
        "check 2 pre-bash/block-pathspecless-git-commit.sh",
        bash_json('git commit -a -m "x"'),
        "pathspecless-commit: -a stages every modified tracked file",
    ),
    case(
        "check 2 pre-bash/block-pathspecless-git-commit.sh",
        bash_json('git commit -m "x" --'),
        "pathspecless-commit: a -- with nothing after it is the bare form in disguise",
    ),
    case(
        "check 0 pre-bash/block-pathspecless-git-commit.sh",
        bash_json("git commit -F msg.txt -- a/b.ts"),
        "pathspecless-commit: ALLOW a named pathspec",
    ),
    case(
        "check 0 pre-bash/block-pathspecless-git-commit.sh",
        bash_json("git commit -q -F - -- .ci/x.sh agent/y.md"),
        "pathspecless-commit: ALLOW several named paths",
    ),
    case(
        "check 0 pre-bash/block-pathspecless-git-commit.sh",
        bash_json("git commit --amend --no-edit"),
        "pathspecless-commit: ALLOW an amend, which chooses no new content",
    ),
    case(
        "check 0 pre-bash/block-pathspecless-git-commit.sh",
        bash_json("git add -- a.ts"),
        "pathspecless-commit: ALLOW a git add, which is a different guard's business",
    ),
    case(
        "check 0 pre-bash/block-pathspecless-git-commit.sh",
        bash_json("git init -q && git add -A && git commit -qm seed"),
        "pathspecless-commit: ALLOW a throwaway fixture repo, which every port agent must seal",
    ),
    case(
        "check 0 pre-bash/block-pathspecless-git-commit.sh",
        bash_json("cd /tmp/claude-1000/fx/r1; git add -A; git commit -qm seed"),
        "pathspecless-commit: ALLOW a commit inside /tmp, which is never this checkout",
    ),
    case(
        "check 0 pre-bash/block-pathspecless-git-commit.sh",
        bash_json("git -C /tmp/claude-1000/fx/r1 commit -qm seed"),
        "pathspecless-commit: ALLOW git -C into a scratch repo",
    ),
    case(
        "check 2 pre-bash/block-pathspecless-git-commit.sh",
        bash_json("git commit -F /tmp/claude-1000/msg.txt"),
        "pathspecless-commit: a /tmp MESSAGE FILE is not a /tmp repo, so this is still blocked",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git checkout -- packages/www/src/i18n/translations/.translation-hashes.json"),
        "destructive-git: the exact 2026-08-14 command",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git checkout ."),
        "destructive-git: checkout a lone dot",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git restore src/file.ts"),
        "destructive-git: restore",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git -C private/renet restore pkg/chunkstore/session.go"),
        "destructive-git: restore in a submodule via -C",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git stash"),
        "destructive-git: bare stash",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git stash pop"),
        "destructive-git: stash pop",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git clean -fd"),
        "destructive-git: clean",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("echo hi; git restore src/"),
        "destructive-git: after a command separator",
    ),
    # THE NEGATIVE HALF, which matters more than usual: this guard sits on `git checkout`, which sessions use to switch branches all day. A guard that blocks that is one sessions demand be removed, leaving no guard at all.
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git checkout main"),
        "destructive-git: branch switch is NOT blocked",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git checkout -b feature/x"),
        "destructive-git: branch create is NOT blocked",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git stash list"),
        "destructive-git: stash list is read-only",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git stash show -p"),
        "destructive-git: stash show is read-only",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git clean -n"),
        "destructive-git: clean --dry-run is read-only",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git status"),
        "destructive-git: unrelated git command",
    ),
    case(
        "check 2 guards/block_blanket_git_add.py",
        bash_json("cd /tmp && git add -A"),
        "blanket-git-add: after a command separator",
    ),
    case(
        "check 2 guards/block_blanket_git_add.py",
        bash_json('sh -c "git add -A"'),
        "blanket-git-add: sh -c wrapper bypass",
    ),
    # BYPASSES found by review of PR #566, each confirmed by running the guard before the fix: all three exited 0 while staging the whole tree. Redirection is not a pathspec, and `--` with nothing after it is not a restriction -- git treats an empty pathspec list as no restriction at all, so it is the bare form wearing the escape's clothes.
    case(
        "check 2 guards/block_blanket_git_add.py",
        bash_json("git add -A > /dev/null"),
        "blanket-git-add: stdout redirection is not a pathspec",
    ),
    case(
        "check 2 guards/block_blanket_git_add.py",
        bash_json("git add -A 2>&1"),
        "blanket-git-add: fd redirection is not a pathspec",
    ),
    case(
        "check 2 guards/block_blanket_git_add.py",
        bash_json("git add -A --"),
        "blanket-git-add: a bare -- with no pathspec is still blanket",
    ),
    case(
        "check 2 guards/block_blanket_git_add.py",
        bash_json("git add . > /dev/null"),
        "blanket-git-add: dot plus redirection",
    ),
    case(
        "check 2 guards/block_nondraft_pr_create.py",
        bash_json("gh pr create --title x --body y"),
        "nondraft-create: console without --draft",
    ),
    # Stale-dated PR branch (PR #575 was filed from 0825-2 on 08-26). Both directions: the stale name blocks, today's name and a non-wave name pass.
    case(
        "check 2 guards/block_stale_pr_branch_date.py",
        bash_json("gh pr create --draft --head 0825-2 -t x -b y"),
        "stale-pr-branch: yesterday's MMDD blocked",
    ),
    case(
        "check 0 guards/block_stale_pr_branch_date.py",
        bash_json(
            # LOCAL today, deliberately, and noqa'd on this line rather than by
            # disabling DTZ: the guard under test reads the clock with a bare `datetime.now()` precisely so it honours TZ the way its `date +%m%d` twin does. A tz-aware `today()` here would disagree with the guard
            # for the hours either side of local midnight and fail this case on
            # any host off Greenwich -- which is the exact defect the guard's port notes record being measured at 00:47 CEST.
            "gh pr create --draft --head %s-9 -t x -b y" % datetime.date.today().strftime("%m%d")  # noqa: DTZ011
        ),
        "stale-pr-branch: today's MMDD allowed",
    ),
    case(
        "check 0 guards/block_stale_pr_branch_date.py",
        bash_json("gh pr create --draft --head feature/not-a-wave -t x"),
        "stale-pr-branch: non-MMDD name is out of scope",
    ),
    case(
        "check 0 guards/block_stale_pr_branch_date.py",
        bash_json("gh pr list --head 0825-2"),
        "stale-pr-branch: not a create, ignored",
    ),
    case(
        "check 2 guards/block_stale_pr_branch_date.py",
        bash_json("sh -c 'gh pr create --draft --head 0825-2 -t x'"),
        "stale-pr-branch: sh -c wrapper bypass blocked",
    ),
    case(
        "check 2 guards/block_nondraft_pr_create.py",
        bash_json("cd private/renet && gh pr create --draft --title x"),
        "nondraft-create: draft on private submodule",
    ),
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("gh pr merge 531 --squash --admin"),
        "admin-merge: --admin banned",
    ),
    # Adversarial bypass cases (review finding F1): the quote-strip used to let
    # shell-wrapper / eval / flag=value / variable-indirection forms slip the ban.
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("sh -c 'gh pr merge 531 --admin'"),
        "admin-merge: sh -c wrapper bypass blocked",
    ),
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json('bash -c "gh pr merge 531 --admin"'),
        "admin-merge: bash -c wrapper bypass blocked",
    ),
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("eval 'gh pr merge 531 --admin'"),
        "admin-merge: eval wrapper bypass blocked",
    ),
    # Round-39 review finding: bundled/separate flags before -c defeated both the wrapper-unwrap AND the prose-strip (which erases the same quoted payload).
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("bash -lc 'gh pr merge 531 --admin'"),
        "admin-merge: bundled-flag wrapper (bash -lc) bypass blocked",
    ),
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("sh -eu -c 'gh pr merge 531 --admin'"),
        "admin-merge: separate-flag wrapper (sh -eu -c) bypass blocked",
    ),
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("bash -eux -c 'gh pr merge 531 --admin'"),
        "admin-merge: multi-flag wrapper (bash -eux -c) bypass blocked",
    ),
    # Round-40 review finding: GNU long options and value-taking short options
    # before -c also defeated the round-40 flag-shape regex; fixed via
    # token-scanning (any intervening token is skippable) instead of a 4th regex.
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("bash --posix -c 'gh pr merge 531 --admin'"),
        "admin-merge: GNU long-option wrapper (bash --posix -c) bypass blocked",
    ),
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("bash --norc -c 'gh pr merge 531 --admin'"),
        "admin-merge: GNU long-option wrapper (bash --norc -c) bypass blocked",
    ),
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("bash -o pipefail -c 'gh pr merge 531 --admin'"),
        "admin-merge: value-taking-flag wrapper (bash -o pipefail -c) bypass blocked",
    ),
    # Round-42 review finding: a path-qualified shell name (exact-match anchor, not basename) defeated the token-scanner the same way flag shapes did.
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("/bin/bash -c 'gh pr merge 531 --admin'"),
        "admin-merge: path-qualified shell (/bin/bash -c) bypass blocked",
    ),
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("./bash -c 'gh pr merge 531 --admin'"),
        "admin-merge: relative-path shell (./bash -c) bypass blocked",
    ),
    # Round-44 review finding: a QUOTED shell path defeated the basename strip (the last `/` lands inside the quotes, leaving a trailing quote character).
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("\"/bin/bash\" -c 'gh pr merge 531 --admin'"),
        'admin-merge: double-quoted path ("/bin/bash" -c) bypass blocked',
    ),
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("'/bin/bash' -c 'gh pr merge 531 --admin'"),
        "admin-merge: single-quoted path ('/bin/bash' -c) bypass blocked",
    ),
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("gh pr merge 531 --squash --admin=true"),
        "admin-merge: --admin=value bypass blocked",
    ),
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("X=--admin; gh pr merge 531 $X"),
        "admin-merge: variable-indirection bypass blocked",
    ),
    case(
        "check 2 guards/block_nondraft_pr_create.py",
        bash_json("sh -c 'gh pr create --title x --body y'"),
        "nondraft-create: sh -c wrapper bypass blocked",
    ),
    # Round-46 (live during a real /pr-merge): fields were parsed from the WHOLE bash line, so sibling gh invocations donated fields to each other and only ONE invocation per line was ever examined. Each of these pairs a compliant
    # invocation with a violating one; both must be judged on their own segment.
    case(
        "check 2 guards/block_nondraft_pr_create.py",
        bash_json(
            "gh pr create --draft --repo rediacc/console -t x; gh pr create --repo rediacc/console -t y"
        ),
        "nondraft-create: second create on the line is judged too (no --draft donation)",
    ),
    case(
        "check 2 guards/block_nondraft_pr_create.py",
        bash_json(
            "gh pr create --draft --repo rediacc/console -t x; gh pr create --draft --repo rediacc/renet -t y"
        ),
        "nondraft-create: draft-on-private caught in the second segment (no --repo donation)",
    ),
    case(
        "check 2 guards/block_settled_questions.py",
        ask_json("Should I commit this change?"),
        "settled(commit)",
    ),
    case(
        "check 2 guards/block_settled_questions.py",
        ask_json("Shall I open a PR for this?"),
        "settled(pr)",
    ),
    case(
        "check 2 guards/block_settled_questions.py",
        ask_json("Do you want me to create a branch first?"),
        "settled(branch)",
    ),
    # CONTROLS: a design question and a factual question that merely MENTION the vocabulary must pass. Anchoring on words rather than on intent is the over-matching mistake wl_agents.py paid for four times in one session.
    case(
        "check 0 guards/block_settled_questions.py",
        ask_json("Which branching strategy should this repo use, trunk or release branches?"),
        "settled(design passes)",
    ),
    case(
        "check 0 guards/block_settled_questions.py",
        ask_json("Did the rebase drop a commit, or is the count right?"),
        "settled(fact passes)",
    ),
    case(
        "check 0 guards/block_settled_questions.py",
        ask_json("Should I install node from a tarball or a package manager?"),
        "settled(unrelated permission passes)",
    ),
    # THE MENTION-VS-TARGET PAIR. Both regexes hit anywhere in the question, so a sentence ABOUT the settled rule was refused as if it were the rule being broken -- measured 2026-08-28, "Should I explain in the report why we never commit unasked?" exited 2. The fix anchors the permission to the clause it GOVERNS (no subordinating conjunction or comma in between) and does not touch
    # the object list, so the three direct forms above still refuse.
    case(
        "check 0 guards/block_settled_questions.py",
        ask_json("Should I explain in the report why we never commit unasked?"),
        "settled(mention of the rule passes)",
    ),
    case(
        "check 0 guards/block_settled_questions.py",
        ask_json("Can we record that the commit rule is settled?"),
        "settled(that-clause passes)",
    ),
    case(
        "check 0 guards/block_settled_questions.py",
        ask_json("Should I describe how the branch guard works?"),
        "settled(how-clause passes)",
    ),
    # 2026-09-16, added live: the worktree/branch ROUTING class -- "shouldn't have asked ... it has big-bang answering usually" -- gets the same two-condition treatment as commit/branch/push/pr/merge.
    case(
        "check 2 guards/block_settled_questions.py",
        ask_json("Where should this work happen: a new worktree, or the current checkout?"),
        "settled(worktree routing)",
    ),
    case(
        "check 2 guards/block_settled_questions.py",
        ask_json("Should a new worktree be created for this task?"),
        "settled(worktree should)",
    ),
    case(
        "check 0 guards/block_settled_questions.py",
        ask_json("How are worktrees organized across the repos?"),
        "settled(worktree design question passes)",
    ),
    case(
        "check 2 guards/block_suppressions.py",
        edit_json("a // @ts-ignore"),
        "suppressions(new_string)",
    ),
    case(
        "check 2 guards/block_suppressions.py",
        multiedit_json("b // eslint-disable"),
        "suppressions(MultiEdit)",
    ),
    case(
        "check 2 guards/block_inline_workflow_run.py",
        wf_edit_json(
            ".github/workflows/x.yml",
            "      - name: Big\n"
            "        run: |\n"
            "          echo 1\n"
            "          echo 2\n"
            "          echo 3\n"
            "          echo 4\n"
            "          echo 5\n"
            "          echo 6\n"
            "          echo 7\n"
            "          echo 8\n"
            "          echo 9",
        ),
        "inline-workflow-run: 9-line block blocked",
    ),
    case(
        "check_out 2 guards/block_plan_without_tasks.py",
        tool_json(
            "Write",
            "/r/home/u/.claude/plans/harness.md",
            "content",
            "Status: ready\n"
            "\n"
            "# A plan\n"
            "\n"
            "## Part 0 - DECIDED by the operator\n"
            "\n"
            "1. A locked decision sentence long enough to be a task 0.\n"
            "2. A locked decision sentence long enough to be a task 1.\n"
            "3. A locked decision sentence long enough to be a task 2.\n"
            "4. A locked decision sentence long enough to be a task 3.\n"
            "5. A locked decision sentence long enough to be a task 4.\n"
            "6. A locked decision sentence long enough to be a task 5.\n"
            "\n"
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        ),
        "plan-tasks: the harness plan directory is in scope too",
        "ADD a section like this",
    ),
    case(
        "check 0 guards/block_plan_without_tasks.py",
        tool_json(
            "Write",
            "/r/packages/cli/src/foo.ts",
            "content",
            "Status: ready\n"
            "\n"
            "# A plan\n"
            "\n"
            "## Part 0 - DECIDED by the operator\n"
            "\n"
            "1. A locked decision sentence long enough to be a task 0.\n"
            "2. A locked decision sentence long enough to be a task 1.\n"
            "3. A locked decision sentence long enough to be a task 2.\n"
            "4. A locked decision sentence long enough to be a task 3.\n"
            "5. A locked decision sentence long enough to be a task 4.\n"
            "6. A locked decision sentence long enough to be a task 5.\n"
            "\n"
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        ),
        "plan-tasks: a non-plan path is out of scope",
    ),
    # STATE.md write guard: the CLI refusal alone is bypassed by a raw Write (the document lives at a plain repo path), so the guard is the closing half.
    #
    # IT DENIES EVERY DIRECT WRITE NOW, shape-valid ones included, and the WELL-SHAPED case below is the one that changed. Only the CLI writes STATE.md,
    # with the heading, the stamp and the lock that make it recoverable; a
    # perfectly shaped whole-file Write lands unstamped, exactly as unrecoverably as a malformed one, so a guard that measured LENGTH was waving through the only defect that matters. Each case asserts the message too, because redirecting to `--state` IS the guard's product.
    #
    # THE PATHS HERE ARE LITERAL STRINGS with no filesystem behind them, which is what makes them dangerous during a move: when the tree went from .agent/<branch>/ to agent/<branch>/<session>/ (2026-08-14), every one of these cases would have kept passing against the OLD path while the guard stopped covering the new one, and the suite would have reported that as green. It moved
    # AGAIN on 2026-08-18, when the branch left the path and agent/<session>/STATE.md became the live shape, so the same hazard applies to these very lines: the live one-level shape is asserted FIRST, and the retired two-level shapes after it, because writing THERE is a session running stale instructions rather than a path nobody would ever try.
    case(
        "check_out 2 guards/block_agent_state_shape.py",
        tool_json("Write", "/r/agent/deadbeef/STATE.md", "content", "tiny"),
        "agent-state: thin Write blocked",
        "worklist.py --state",
    ),
    case(
        "check_out 2 guards/block_agent_state_shape.py",
        tool_json(
            "Write",
            "/r/agent/deadbeef/STATE.md",
            "content",
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        ),
        "agent-state: aimless Write (no Next action) blocked",
        "worklist.py --state",
    ),
    case(
        "check_out 2 guards/block_agent_state_shape.py",
        tool_json("Edit", "/r/agent/deadbeef/STATE.md", "new_string", "patch"),
        "agent-state: Edit blocked (rewrite, never append)",
        "agent/<your-prefix>/STATE.md",
    ),
    case(
        "check_out 2 guards/block_agent_state_shape.py",
        tool_json("MultiEdit", "/r/agent/deadbeef/STATE.md", "new_string", "patch"),
        "agent-state: MultiEdit blocked",
        "worklist.py --state",
    ),
    # The live path must be reached at DEPTH inside an absolute path too: a pattern anchored at the string start leaves every real checkout open.
    case(
        "check_out 2 guards/block_agent_state_shape.py",
        tool_json(
            "Write",
            "/r/monorepo/console/agent/deadbeef/STATE.md",
            "content",
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "\n"
            "## Next action\n"
            "\n"
            "go",
        ),
        "agent-state: the real session path is reached, deep in an absolute path",
        "agent/<your-prefix>/STATE.md",
    ),
    case(
        "check_out 2 guards/block_agent_state_shape.py",
        tool_json(
            "Write",
            "/r/agent/0814-1/deadbeef/STATE.md",
            "content",
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "\n"
            "## Next action\n"
            "\n"
            "go",
        ),
        "agent-state: the retired branch/session path is blocked too",
        "worklist.py --state",
    ),
    case(
        "check_out 2 guards/block_agent_state_shape.py",
        tool_json(
            "Write",
            "/r/.agent/b/STATE.md",
            "content",
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "\n"
            "## Next action\n"
            "\n"
            "go",
        ),
        "agent-state: the legacy dotted path is blocked too",
        "worklist.py --state",
    ),
    # --- should PASS (exit 0) --- NOTE: block-admin-merge.sh verifies live thread state over the network on its
    # enforcement path; only its pattern paths (--auto, --draft flags, non-matching
    # commands) are unit-tested here.
    #
    # block-premature-ready.sh USED to be in that sentence, and the network was the stated reason. It was not a good one: `gh` is stubbed for the second-open-PR cases a few lines below, and stubbing it here reaches the enforcement path in both directions (see ready_case). "Cannot be tested here" is a claim, and the command that would have disproved it took one minute to write.
    case(
        "check 0 guards/block_blanket_git_add.py",
        bash_json("git add -A -- packages/cli/src"),
        "blanket-git-add: -A WITH a pathspec is the escape, allowed",
    ),
    case(
        "check 0 guards/block_blanket_git_add.py",
        bash_json("git add packages/cli/src/foo.ts"),
        "blanket-git-add: a named file is allowed",
    ),
    case(
        "check 0 guards/block_blanket_git_add.py",
        bash_json("git -C private/renet add -A -- pkg/"),
        "blanket-git-add: -C plus a pathspec is allowed",
    ),
    case(
        "check 0 guards/block_blanket_git_add.py",
        bash_json("git add -A -- . > /dev/null"),
        "blanket-git-add CONTROL: a real pathspec WITH redirection is still allowed",
    ),
    # CROSS-TALK CONTROL. Two guards match adjacent `git ... add` shapes, and a regex widened by one word would make this one swallow worktree creation -- which would then be blocked with the WRONG message and the wrong escape.
    case(
        "check 0 guards/block_blanket_git_add.py",
        bash_json("git worktree add /tmp/wt main"),
        "blanket-git-add CONTROL: worktree add is NOT this guard's business",
    ),
    case(
        "check 0 guards/block_nondraft_pr_create.py",
        bash_json("gh pr create --draft --title x --body y"),
        "nondraft-create: console with --draft ok",
    ),
    case(
        "check 0 guards/block_nondraft_pr_create.py",
        bash_json("cd private/renet && gh pr create --title x --body y"),
        "nondraft-create: plain create on private submodule ok",
    ),
    case(
        "check 0 guards/block_nondraft_pr_create.py",
        bash_json("gh pr list --repo rediacc/console"),
        "nondraft-create: non-create command ignored",
    ),
    case(
        "check 0 guards/block_premature_ready.py",
        bash_json("gh pr ready 531 --undo"),
        "premature-ready: --undo always allowed",
    ),
    case(
        "check 0 guards/block_premature_ready.py",
        bash_json("gh pr view 531"),
        "premature-ready: non-ready command ignored",
    ),
    # Regression: the phrase inside heredoc/doc prose is NOT an invocation. The unanchored v1 fired on a round-log heredoc that merely mentioned the flow.
    case(
        "check 0 guards/block_premature_ready.py",
        bash_json("cat >> log.md <<EOF\ngreen-gated `gh pr ready` + hook-banned --admin\nEOF"),
        "premature-ready: prose mention in heredoc ignored",
    ),
    case(
        "check 0 guards/block_admin_merge.py",
        bash_json("cat >> log.md <<EOF\nthe old flow used gh pr merge --admin, now banned\nEOF"),
        "admin-merge: prose mention in heredoc ignored",
    ),
    # SANITY FIRST. Every exemption case below is vacuous if the guard does not fire on an untagged commit in THIS repo -- a guard that exits 0 for everything passes them all.
    case(
        "check 2 guards/block_untagged_commit.py",
        bash_json('git commit -m "chore: no trailer here"'),
        "target-root SANITY: an untagged commit in THIS repo is refused",
    ),
    # THE SUBTLE ONE, and the reason the resolver compares git ROOTS rather than paths: a -C into a SUBDIRECTORY of this repo is still this repo, and must stay covered. A naive "any -C means elsewhere" check passes every case above and fails this one.
    case(
        "check 2 guards/block_untagged_commit.py",
        bash_json('git -C packages/cli commit -m "chore: no trailer here"'),
        "target-root CONTROL: -C into a subdirectory of THIS repo is still this repo",
    ),
    case(
        "check 2 guards/block_untagged_commit.py",
        bash_json('git -C /nonexistent-path-xyz commit -m "chore: no trailer"'),
        "target-root CONTROL: a -C that resolves to no repo is not an exemption",
    ),
    # Even a command-position-looking mention inside a heredoc BODY is data, not a command, and must not fire (heredoc-body stripping, the FP that fired on a worklist write).
    case(
        "check 0 guards/block_admin_merge.py",
        bash_json("cat >> log.md <<EOF\n; gh pr merge 531 --admin\nEOF"),
        "admin-merge: command-position mention in heredoc body ignored",
    ),
    case(
        "check 0 guards/block_premature_ready.py",
        bash_json(
            'git commit -m "feat: x\n'
            "\n"
            '- gh pr ready is hook-gated; gh pr merge --admin is banned" && git push'
        ),
        "premature-ready: quoted commit-msg mention ignored",
    ),
    case(
        "check 0 guards/block_admin_merge.py",
        bash_json(
            'git commit -m "feat: x\n'
            "\n"
            '- gh pr ready is hook-gated; gh pr merge --admin is banned" && git push'
        ),
        "admin-merge: quoted commit-msg --admin mention ignored",
    ),
    # --auto on a rediacc repo now verifies review hygiene LIVE (report reply + threads), which this offline harness cannot assert, and that path is covered by the hook's manual live proofs. Offline we prove the non-rediacc early-exit still holds for --auto.
    case(
        "check 0 guards/block_admin_merge.py",
        bash_json("gh pr merge 7 --squash --auto --repo otherorg/tool"),
        "admin-merge: --auto on non-rediacc repo ignored",
    ),
    case(
        "check 0 guards/block_admin_merge.py",
        bash_json("gh pr checks 531"),
        "admin-merge: non-merge command ignored",
    ),
    # Round-46 cross-attribution, the exact live firing: a sibling `gh pr view` donated its --repo to the merge's PR number, resolving a DIFFERENT repo's PR #66 (long merged, one unresolved thread) and blocking a clean merge. With the segment fix this stays a foreign-repo no-op and never hits the
    # network; with the bug it resolves rediacc/renet and blocks.
    case(
        "check 0 guards/block_admin_merge.py",
        bash_json("gh pr view 94 --repo rediacc/renet; gh pr merge 66 --repo otherorg/tool"),
        "admin-merge: sibling gh --repo does not donate to the merge segment",
    ),
    # NOT asserted here: per-segment --auto and per-segment PR selectors on block-admin-merge. Both only change behavior once a rediacc repo is resolved, which puts them on the network path this offline harness cannot drive (same limitation as the NOTE above). They are covered by the hook's live proofs, not by a case that would pass either way -- a green assertion that cannot fail
    # is worse than no assertion. REST/GraphQL parity (agent/PLAN-rest-graphql-guard-parity.md): the same three guards also police the REST or GraphQL call that reaches the identical GitHub mutation as the `gh pr` verb they already gate. One BLOCK and one ALLOW per guard, mirrored here because hook_integrity.covmap reads coverage off this exact "check <rc> guards/<module>.py"
    # shape.
    case(
        "check 2 guards/block_admin_merge.py",
        bash_json("gh api repos/o/r/pulls/589/merge -X PUT -f merge_method=squash"),
        "admin-merge: REST merge bypass blocked",
    ),
    case(
        "check 0 guards/block_admin_merge.py",
        bash_json("gh api repos/o/r/pulls/589/merge"),
        "admin-merge: a GET on the merge endpoint is not a merge",
    ),
    case(
        "check 2 guards/block_nondraft_pr_create.py",
        bash_json("gh api repos/o/r/pulls -X POST -f title=x -f head=b -f base=main"),
        "nondraft-create: REST create bypass blocked",
    ),
    case(
        "check 0 guards/block_nondraft_pr_create.py",
        bash_json("gh api repos/o/r/pulls/42/comments -X POST -f body=hi"),
        "nondraft-create: a POST to the comments sub-endpoint is not a create",
    ),
    case(
        "check 2 guards/block_premature_ready.py",
        bash_json("gh api graphql -f query=markPullRequestReadyForReview"),
        "premature-ready: GraphQL ready bypass blocked",
    ),
    case(
        "check 0 guards/block_premature_ready.py",
        bash_json("gh api graphql -f query=someOtherQuery"),
        "premature-ready: the same endpoint querying something else is not a flip",
    ),
    case(
        "check 0 guards/block_git_amend.py",
        bash_json("git status"),
        "amend: benign",
    ),
    case(
        "check 0 guards/block_ssh_docker.py",
        bash_json("ssh 192.168.111.1 docker ps"),
        "ssh-docker: bridge allowed",
    ),
    case(
        "check 0 guards/block_ssh_file_write.py",
        bash_json('ssh host "cat /etc/criu/runc.conf 2>&1; ls"'),
        "ssh-file-write: stderr redirect is a read",
    ),
    case(
        "check 0 guards/block_ssh_file_write.py",
        bash_json('ssh host "cat /var/log/x >/dev/null 2>&1"'),
        "ssh-file-write: dev-null read ok",
    ),
    case(
        "check 0 guards/block_long_sleep.py",
        bash_json("sleep 10"),
        "long-sleep: 10s ok",
    ),
    case(
        "check 0 guards/block_ci_polling.py",
        bash_bg_json(
            'R=123; P=""; while :; do S=$(gh api "repos/o/r/actions/runs/$R" --jq ".status") || { sleep 20; continue; }; case "$S" in completed*) [ "$P" = "$S" ] && break; P="$S"; sleep 90 ;; *) P=""; sleep 20 ;; esac; done'
        ),
        "ci-polling: attempt-stable watch ok",
    ),
    case(
        "check 0 guards/block_ci_reverse_poll.py",
        bash_bg_json(
            'R=123; P=""; while :; do S=$(gh api "repos/o/r/actions/runs/$R" --jq ".status") || { sleep 20; continue; }; case "$S" in completed*) [ "$P" = "$S" ] && break; P="$S"; sleep 90 ;; *) P=""; sleep 20 ;; esac; done'
        ),
        "ci-reverse-poll: attempt-stable watch ok",
    ),
    case(
        "check 0 guards/block_long_sleep.py",
        bash_bg_json(
            'R=123; P=""; while :; do S=$(gh api "repos/o/r/actions/runs/$R" --jq ".status") || { sleep 20; continue; }; case "$S" in completed*) [ "$P" = "$S" ] && break; P="$S"; sleep 90 ;; *) P=""; sleep 20 ;; esac; done'
        ),
        "long-sleep: attempt-stable watch ok in background",
    ),
    case(
        "check 0 guards/block_long_sleep.py",
        bash_bg_json(
            'R=123; P=""; while :; do S=$(gh api "repos/o/r/actions/runs/$R" --jq ".status"); case "$S" in completed*) P="$S"; sleep 90 ;; *) sleep 20 ;; esac; done'
        ),
        "long-sleep: arm order does not decide the verdict",
    ),
    # ...and the foreground cap must still bite, or the exemption above is a hole.
    case(
        "check 2 guards/block_long_sleep.py",
        bash_json("sleep 90"),
        "long-sleep: 90s in the FOREGROUND still blocked",
    ),
    case(
        "check 2 guards/block_long_sleep.py",
        bash_json(
            'R=123; P=""; while :; do S=$(gh api "repos/o/r/actions/runs/$R" --jq ".status") || { sleep 20; continue; }; case "$S" in completed*) [ "$P" = "$S" ] && break; P="$S"; sleep 90 ;; *) P=""; sleep 20 ;; esac; done'
        ),
        "long-sleep: the same watch unbackgrounded is blocked",
    ),
    case(
        "check 2 guards/block_long_sleep.py",
        bash_bg_json("sleep 900"),
        "long-sleep: background is not unlimited",
    ),
    case(
        "check 0 guards/block_long_sleep.py",
        bash_bg_json("sleep 20"),
        "long-sleep: short background sleep ok",
    ),
    # --- block-adhoc-sanctioned.sh: the registry-driven guard -------------------- It refuses an ad-hoc command when a sanctioned tool exists, reading the table in .claude/hooks/lib/sanctioned.py. Both directions matter more than usual here: this guard sits in front of every Bash call in the session, so an over-broad row would be felt immediately and then removed.
    case(
        "check 2 guards/block_adhoc_sanctioned.py",
        bash_json("gh run watch 123 --exit-status"),
        "adhoc: the banned watch command is refused",
    ),
    case(
        "check 2 guards/block_adhoc_sanctioned.py",
        bash_json('gh pr edit 574 --body \\"x\\"'),
        "adhoc: gh pr edit --body is refused (it exits 1 and does not write)",
    ),
    case(
        "check 2 guards/block_adhoc_sanctioned.py",
        bash_json(
            'until [ \\"$(gh run view $R --json status --jq .status)\\" = \\"completed\\" ]; do :; done'
        ),
        "adhoc: a hand-rolled status loop is refused",
    ),
    case(
        "check 0 guards/block_adhoc_sanctioned.py",
        bash_json(".ci/scripts/ci/ci-trace.py --wait"),
        "adhoc: the sanctioned tracer passes",
    ),
    case(
        "check 0 guards/block_adhoc_sanctioned.py",
        bash_json("gh run view 123 --json conclusion,jobs"),
        "adhoc: a one-shot read is not a watch",
    ),
    case(
        "check 0 guards/block_adhoc_sanctioned.py",
        bash_json("gh api repos/o/r/pulls/574 -X PATCH -F body=@b.md"),
        "adhoc: the sanctioned body update passes",
    ),
    case(
        "check 0 guards/block_adhoc_sanctioned.py",
        bash_json("git status"),
        "adhoc: an unrelated command passes",
    ),
    case(
        "check 0 guards/block_adhoc_sanctioned.py",
        bash_json("cat > doc.md <<'EOF'\nUse gh run watch 123 --exit-status to follow it\nEOF"),
        "adhoc CONTROL: a DOC quoting the banned recipe is not a use of it",
    ),
    # THE CONTROL THAT MATTERS: it must FAIL OPEN on its own breakage. A guard that bricks every command when its registry is missing gets deleted, and then nothing is guarded at all.
    case(
        "check 0 guards/block_adhoc_sanctioned.py",
        EMPTY_INPUT,
        "adhoc: no command in the payload is not a violation",
    ),
    # --- warn-hook-change.sh: warning only, ALWAYS exit 0 ------------------------ The operator chose warn over block for hook edits (2026-08-25) because a hard block would have fired six times that day on legitimate work. These pin that it can never block: a warn hook that can block is a block hook nobody reviewed.
    case(
        "check 0 guards/warn_hook_change.py",
        bash_json("git commit -m x"),
        "warn-hook-change: a commit never blocks",
    ),
    case(
        "check 0 guards/warn_hook_change.py",
        bash_json("git status"),
        "warn-hook-change: an unrelated command never blocks",
    ),
    # --- block-ci-polling.sh boundaries, both directions ------------------------ These pin the pattern itself. A guard nobody tests either rots into blocking everything (and gets disabled) or stops matching (and guards nothing).
    case(
        "check 2 guards/block_ci_polling.py",
        bash_json("sleep 30 && gh run list --repo rediacc/console"),
        "ci-polling: classic poll with && blocks",
    ),
    case(
        "check 2 guards/block_ci_polling.py",
        bash_json("sleep 20; gh run view 123 --json status"),
        "ci-polling: classic poll with ; blocks",
    ),
    case(
        "check 0 guards/block_ci_polling.py",
        bash_json("gh run view 123 --json status"),
        "ci-polling: a bare gh run view is not a poll",
    ),
    case(
        "check 0 guards/block_ci_polling.py",
        bash_json("sleep 30"),
        "ci-polling: a bare sleep is not a poll",
    ),
    case(
        "check 0 guards/block_ci_polling.py",
        bash_json(
            'while :; do S=$(gh api "repos/o/r/actions/runs/1" --jq .status); sleep 20; done'
        ),
        "ci-polling: the gh api watch loop is not a gh-run-view poll",
    ),
    # THE ACCEPTED FALSE POSITIVE, PINNED ON PURPOSE.
    #
    # Both guards read the command TEXT, so a command that merely DESCRIBES the pattern -- editing this repo's own watch documentation, or a commit message quoting the recipe -- is blocked exactly as if it were polling. That is not a bug to be fixed later: it was put to the operator on 2026-08-25 with four scored options and the ruling was to keep both guards as they are, because
    # this failure is LOUD (a blocked command naming its workaround) while every narrowing that would admit the doc edit fails SILENTLY -- a real long poll runs and nobody is told. Exempting heredoc bodies is the most tempting of those, and the worst: a heredoc is where a genuine long sleep would hide.
    #
    # So these two assert exit 2. If someone later "fixes" the false positive, these turn red and force the decision to be re-made deliberately rather than drifting. The workaround stays: write the file with the Write tool and pass it by path. The shapes below were probed, not assumed. A first draft of these cases asserted exit 2 on payloads that do not actually match either
    # pattern
    # ("sleeps 90s" is not `sleep +[0-9]+`; a `done;` sits between the sleep and the
    # gh in the until-loop form), so they failed on correct code -- a test pinning a false positive that could not occur. These two are the real triggers.
    case(
        "check 2 guards/block_ci_polling.py",
        bash_json("cat > doc.md <<'EOF'\nPoll with sleep 20; gh run view $R --json status\nEOF"),
        "ci-polling: prose showing an INLINE poll is blocked on purpose (operator ruling 2026-08-25)",
    ),
    case(
        "check 2 guards/block_long_sleep.py",
        bash_json("git commit -F - <<'MSG'\nits sleep 20 arm precedes its sleep 90 arm\nMSG"),
        "long-sleep: a commit message quoting a literal long sleep is blocked on purpose (operator ruling 2026-08-25)",
    ),
    # The BOUNDARY, and the reason the false positive is narrower than it sounds:
    # prose showing the SANCTIONED until-loop is NOT blocked, because a `done;` sits
    # between its sleep and its gh. Only an inline `sleep N; gh run view` trips it.
    case(
        "check 0 guards/block_ci_polling.py",
        bash_json(
            "cat > doc.md <<'EOF'\n"
            'R=1; until [ "$(gh run view $R --json status)" = c ]; do sleep 20; done; gh run view $R\n'
            "EOF"
        ),
        "ci-polling: prose showing the sanctioned until-loop is NOT blocked",
    ),
    # ...and the sanctioned escape hatch must keep working, or the ruling above is a trap rather than a trade-off: the same content passed by PATH is fine.
    case(
        "check 0 guards/block_ci_polling.py",
        bash_json("python3 /tmp/patch_the_docs.py"),
        "ci-polling: the documented workaround (file by path) passes",
    ),
    case(
        "check 0 guards/block_long_sleep.py",
        bash_json("git commit -F /tmp/commit-msg.txt"),
        "long-sleep: the documented workaround (message by path) passes",
    ),
    # The self-matching pgrep waiter. The FIRE case is the literal shape that ran
    # 70 minutes past its condition on 2026-08-26; the first control is the
    # documented remedy, and it must pass BY CONSTRUCTION -- a bracket class does not match its own literal text, which is the same property the hook tests
    # with. The last two keep the scope honest: a one-shot diagnostic and an
    # artifact waiter are not this bug and must not be refused.
    case(
        "check 2 guards/block_self_matching_pgrep.py",
        bash_json("until ! pgrep -f 'some-suite.sh' >/dev/null 2>&1; do sleep 5; done"),
        "self-pgrep: a loop whose pattern matches its own command line",
    ),
    case(
        "check 0 guards/block_edit_of_running_script.py",
        EMPTY_INPUT,
        "running-script CONTROL: no file_path names nothing",
    ),
    # A VARIABLE EXPANSION IS NOT A FILENAME. `"$SP/mp-$ver.sh"` yielded the candidate `ver.sh` -- the tail of a variable name plus the suffix, naming a file that exists nowhere. The guard cannot know what $ver expands to, so it
    # must not guess; both defects fired on one command while measuring this guard.
    case(
        "check 0 guards/block_bash_write_to_running_script.py",
        bash_json('python3 - "$SP/mp-$ver.sh" "$SP/out-$ver.sh" && x.write_text(1)'),
        "bash-write CONTROL: a variable expansion yields no phantom candidate",
    ),
    # A HOOK-CHAIN SIBLING IS NOT A RUNNING JOB. Every pre-bash guard executes on every Bash call, so without this exclusion the guard blocked all four of the commands repairing it -- permanently, with no moment of quiet to wait for.
    #
    # THE SUBJECT MOVED, the case did not. This named block-binary-deploy.sh until the W5 P7 cutover ported it to Python and moved the bash original out of the
    # chain; the payload has to name a bash guard that is STILL registered in the
    # pre-bash chain, or it stops being an instance of the exclusion it controls. block-pathspecless-git-commit.sh is the one that is left.
    case(
        "check 0 guards/block_bash_write_to_running_script.py",
        bash_json("sed -i s/a/b/ %s/pre-bash/block-pathspecless-git-commit.sh" % HOOKS),
        "bash-write CONTROL: a chain evaluator is not a job you can corrupt",
    ),
    case(
        "check 2 guards/block_self_matching_pgrep.py",
        bash_json('until ! pgrep -f "some-suite.sh" >/dev/null; do sleep 2; done'),
        "self-pgrep: the double-quoted form too",
    ),
    case(
        "check 0 guards/block_self_matching_pgrep.py",
        bash_json("until ! pgrep -f '[s]ome-suite.sh' >/dev/null 2>&1; do sleep 5; done"),
        "self-pgrep CONTROL: the bracket-class remedy is allowed",
    ),
    case(
        "check 0 guards/block_self_matching_pgrep.py",
        bash_json("pgrep -cf some-suite.sh"),
        "self-pgrep CONTROL: a one-shot count is not a wait loop",
    ),
    case(
        "check 0 guards/block_self_matching_pgrep.py",
        bash_json("until [ -s out.txt ]; do sleep 5; done"),
        "self-pgrep CONTROL: an artifact waiter names no process at all",
    ),
    # THE SIXTH MENTION-AS-EXECUTION FALSE POSITIVE OF THIS SESSION, and it was in the guard written to catch the fifth. The loop keyword and the pgrep were tested INDEPENDENTLY, so a one-shot `pgrep -cf` sharing a line with the ordinary English word "while" -- in a worklist message, not a loop -- read as a wedged waiter. The pgrep must sit in the loop's CONDITION.
    case(
        "check 0 guards/block_self_matching_pgrep.py",
        bash_json(
            'echo "alive: $(pgrep -cf x.sh)"; worklist.py --add me "blocked while the suite runs"'
        ),
        "self-pgrep CONTROL: a one-shot count beside the WORD while is not a loop",
    ),
    case(
        "check 2 guards/block_self_matching_pgrep.py",
        bash_json('while pgrep -f "my-job.sh" >/dev/null; do sleep 2; done'),
        "self-pgrep: the while form fires like the until form",
    ),
    # Branch names are MMDD-N with no suffix. The FIRE cases are the two shapes that actually happened: a `-prerebase` safety copy (2026-08-26, in the console AND a submodule) and a slashed feature name. The slashed one is here because the first draft of the hook let it through -- its escape hatch for start-point refs skipped any candidate containing a slash -- and only the control
    # caught it. The SILENT cases keep reads, deletes and start points out of scope.
    case(
        "check 2 guards/block_nonstandard_branch_name.py",
        bash_json("git branch 0826-1-prerebase 0826-1"),
        "branch-name: a suffixed safety copy is refused",
    ),
    case(
        "check 2 guards/block_nonstandard_branch_name.py",
        bash_json("git checkout -b feature/my-thing"),
        "branch-name: a slashed feature name is refused",
    ),
    case(
        "check 2 guards/block_nonstandard_branch_name.py",
        bash_json("git switch -c wip"),
        "branch-name: a bare word is refused",
    ),
    case(
        "check 2 guards/block_nonstandard_branch_name.py",
        bash_json("git branch -m 0826-3 0826-3-backup"),
        "branch-name: renaming INTO a suffix is refused",
    ),
    case(
        "check 0 guards/block_nonstandard_branch_name.py",
        bash_json("git branch -m 0826-3-prerebase 0826-4"),
        "branch-name CONTROL: renaming OUT of a suffix is how you FIX it",
    ),
    case(
        "check 0 guards/block_nonstandard_branch_name.py",
        bash_json("git checkout -b 0826-5 origin/main"),
        "branch-name CONTROL: a legal name with a remote start point",
    ),
    case(
        "check 0 guards/block_nonstandard_branch_name.py",
        bash_json("git branch --show-current"),
        "branch-name CONTROL: a read is not a creation",
    ),
    case(
        "check 2 guards/block_untagged_commit.py",
        bash_json('git commit -m "feat(x): a thing"'),
        "untagged-commit: a message with no trailer is refused",
    ),
    case(
        "check 2 guards/block_untagged_commit.py",
        bash_json('git commit -m "feat(x): mentions PR-TASK in prose but has no trailer"'),
        "untagged-commit: a MENTION is not a trailer (anchored to line start)",
    ),
    case(
        "check 0 guards/block_untagged_commit.py",
        bash_json("cat m.txt | git commit -F -"),
        "untagged-commit CONTROL: a PIPED message is genuinely unreadable, so it ALLOWS",
    ),
    case(
        "check 2 guards/block_untagged_commit.py",
        bash_json("git commit -q -F - <<'MSG'\nfeat(x): a thing\n\nno trailer\nMSG"),
        "untagged-commit: a heredoc with NO trailer is refused (was silently allowed)",
    ),
    case(
        "check 0 guards/block_untagged_commit.py",
        bash_json("git status"),
        "untagged-commit CONTROL: a non-commit is out of scope",
    ),
    case(
        "check 0 guards/block_nonstandard_branch_name.py",
        bash_json("git branch -d 0826-2"),
        "branch-name CONTROL: a delete is not a creation",
    ),
    case(
        "check 0 guards/block_nonstandard_branch_name.py",
        bash_json("git checkout 0826-3"),
        "branch-name CONTROL: checking out an existing branch is not a creation",
    ),
    case(
        "check 0 guards/block_nonstandard_branch_name.py",
        bash_json("SLASH='git checkout -b some/name'; echo hi"),
        "branch-name CONTROL: a variable assignment holding the words runs nothing",
    ),
    case(
        "check 0 guards/block_nonstandard_branch_name.py",
        bash_json("git commit -F - <<'MSG'\nprose naming git checkout -b some/name here\nMSG"),
        "branch-name CONTROL: the shape named inside a heredoc BODY is prose",
    ),
    case(
        "check 2 guards/block_nonstandard_branch_name.py",
        bash_json("git commit -F - <<'MSG'\nprose about a name\nMSG\ngit switch -c nope"),
        "branch-name: a real creation AFTER a heredoc still fires",
    ),
    case(
        "check 0 guards/block_ci_polling.py",
        bash_json(
            'R=123; until [ "$(gh run view $R --repo rediacc/console --json status --jq .status)" = "completed" ]; do sleep 20; done; gh run view $R --repo rediacc/console --json conclusion,jobs'
        ),
        "ci-polling: terminal-state watch ok",
    ),
    case(
        "check 0 guards/block_ci_reverse_poll.py",
        bash_json(
            'R=123; until [ "$(gh run view $R --repo rediacc/console --json status --jq .status)" = "completed" ]; do sleep 20; done; gh run view $R --repo rediacc/console --json conclusion,jobs'
        ),
        "ci-reverse-poll: terminal-state watch ok",
    ),
    case(
        "check 0 guards/block_long_sleep.py",
        bash_json(
            'R=123; until [ "$(gh run view $R --repo rediacc/console --json status --jq .status)" = "completed" ]; do sleep 20; done; gh run view $R --repo rediacc/console --json conclusion,jobs'
        ),
        "long-sleep: terminal-state watch ok",
    ),
    case(
        "check 0 guards/block_git_force_push.py",
        bash_json("git push"),
        "force-push: plain push ok",
    ),
    # THE CONTROLS THAT MATTER for the widened pattern. A guard that blocks every push is worse than no guard: it gets disabled, and then nothing is guarded. Each of these is an ordinary push that must survive the --mirror/+refspec widening.
    case(
        "check 0 guards/block_git_force_push.py",
        bash_json("git push --set-upstream origin feat"),
        "force-push: --set-upstream ok",
    ),
    # THE CONTROL FOR THE WIDENING ABOVE. The guard now matches any WHITESPACE-preceded plus, so this pins the boundary: a plus INSIDE a token is a legal branch name and must stay allowed. Without this arm, widening the pattern further would silently start refusing legitimate pushes.
    case(
        "check 0 guards/block_git_force_push.py",
        bash_json("git push origin HEAD:refs/heads/feature+x"),
        "force-push: a plus inside a branch name is not a force refspec",
    ),
    case(
        "check 0 guards/block_git_force_push.py",
        bash_json("git push --tags origin"),
        "force-push: --tags ok",
    ),
    # LOAD-BEARING. This is the exact form the /pr-merge GitLab step uses. If the guard ever matches it, that step dies SILENTLY -- a blocked hook is an exit 2 the step never distinguishes from a push that simply did not happen. Note how close it comes: `--follow-tags` begins `--f`, one character from the `-f` arm.
    case(
        "check 0 guards/block_git_force_push.py",
        bash_json("git push gitlab refs/heads/main:refs/heads/main --follow-tags"),
        "force-push: the /pr-merge GitLab refspec push is NOT blocked",
    ),
    # The `[^|;&]*` boundary, asserted rather than assumed: a forcing flag on the far
    # side of a pipe belongs to a different command, so the scan must stop at the pipe instead of pairing it with the push.
    case(
        "check 0 guards/block_git_force_push.py",
        bash_json('echo "git push origin main" | grep -q -- --mirror'),
        "force-push: a flag past a pipe is a different command",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("git worktree list"),
        "worktree-add: list ok",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("git worktree remove ../foo"),
        "worktree-add: remove ok",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("git status"),
        "worktree-add: unrelated git command ok",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json('echo "lets talk about git worktree add sometime"'),
        "worktree-add: quoted prose mention ignored",
    ),
    case(
        "check 0 guards/block_suppressions.py",
        edit_json("const x = 1;"),
        "suppressions: clean",
    ),
    # THE NEAR-MISS that `const x = 1;` never tested. block-suppressions' own header
    # named this over-block class as a known risk and nothing asserted against it, so the guard refused documentation of the rule it enforces -- and then refused the edit repairing it, because the repair's comment named the tokens. A real
    # suppression sits immediately after a comment opener; prose puts words in
    # between, and those words are the whole difference.
    case(
        "check 0 guards/block_suppressions.py",
        wf_edit_json("docs/style.md", "Never write @ts-ignore; fix the type instead."),
        "suppressions CONTROL: prose in Markdown naming the directive",
    ),
    case(
        "check 0 guards/block_suppressions.py",
        wf_edit_json("a.ts", "// Never write @ts-ignore here -- fix the type."),
        "suppressions CONTROL: prose INSIDE a code comment",
    ),
    case(
        "check 0 guards/block_suppressions.py",
        wf_edit_json("docs/x.md", "```ts\n// @ts-ignore\n```"),
        "suppressions CONTROL: a fenced example of the wrong way stays writable",
    ),
    case(
        "check 2 guards/block_suppressions.py",
        wf_edit_json("a.ts", "const x = 1; // @ts-ignore"),
        "suppressions: a real directive in a .ts still blocks",
    ),
    case(
        "check 2 guards/block_inline_python.py",
        wf_edit_json(
            "packages/cli/src/x.ts",
            "const script = `\n"
            "import os\n"
            "import sys\n"
            "\n"
            "def main(argv):\n"
            "    for a in argv:\n"
            "        print(a)\n"
            "    return 0\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    sys.exit(main(sys.argv[1:]))\n"
            "`;",
        ),
        "inline-python: a Python program inside a .ts is refused",
    ),
    # THE SAME BYTES, a different extension. This is what proves the guard selects on file type rather than sniffing for Python-ish text anywhere.
    case(
        "check 0 guards/block_inline_python.py",
        wf_edit_json(
            "scripts/x.py",
            "const script = `\n"
            "import os\n"
            "import sys\n"
            "\n"
            "def main(argv):\n"
            "    for a in argv:\n"
            "        print(a)\n"
            "    return 0\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    sys.exit(main(sys.argv[1:]))\n"
            "`;",
        ),
        "inline-python CONTROL: the identical content in a real .py file",
    ),
    case(
        "check 0 guards/block_inline_python.py",
        wf_edit_json(
            "docs/x.md",
            "const script = `\n"
            "import os\n"
            "import sys\n"
            "\n"
            "def main(argv):\n"
            "    for a in argv:\n"
            "        print(a)\n"
            "    return 0\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    sys.exit(main(sys.argv[1:]))\n"
            "`;",
        ),
        "inline-python CONTROL: the identical content in Markdown",
    ),
    case(
        "check 0 guards/block_inline_python.py",
        wf_edit_json("packages/cli/src/x.ts", "export const n: number = 1;"),
        "inline-python CONTROL: ordinary TypeScript",
    ),
    case(
        "check 0 guards/block_inline_python.py",
        wf_edit_json(
            "packages/cli/src/x.ts", 'const cmd = "python3 --version"; // run python here'
        ),
        "inline-python CONTROL: TypeScript that merely MENTIONS python",
    ),
    # --- the shell-backgrounded mail waiter ------------------------------------- Also zero cases in either direction, and grandfathered into the coverage baseline since it was written. The whole guard is one regex matching a single literal behind a two-stage heredoc stripper: if the stripper ever over-strips, the guard silently becomes a no-op and every existing check stays
    # green. It cannot detect its own neutering, so something else has to.
    case(
        "check 2 guards/block_shell_background_waiter.py",
        bash_json("python3 .claude/hooks/stop/wl_wait.py abc --timeout 60 &"),
        "background-waiter: a shell & makes it untracked",
    ),
    case(
        "check 0 guards/block_shell_background_waiter.py",
        bash_json("python3 .claude/hooks/stop/wl_wait.py abc --timeout 60"),
        "background-waiter CONTROL: the same command in the foreground",
    ),
    case(
        "check 0 guards/block_shell_background_waiter.py",
        bash_json('ps -eo pid,args | grep "[p]ython3.*wl_wait"'),
        "background-waiter CONTROL: checking whether one already runs",
    ),
    case(
        "check 0 guards/block_shell_background_waiter.py",
        bash_json(
            "worklist.py --state abc <<'EOF'\n- wl_wait.py must never run with a shell &.\nEOF"
        ),
        "background-waiter CONTROL: a QUOTED-delimiter heredoc body is data, not commands",
    ),
    case(
        "check 0 guards/block_shell_background_waiter.py",
        bash_json(
            "worklist.py --state abc <<EOF\n- wl_wait.py must never run with a shell &.\nEOF"
        ),
        "background-waiter CONTROL: the unquoted-delimiter form too",
    ),
    case(
        "check 2 guards/block_shell_background_waiter.py",
        bash_json("bash <<'EOF'\npython3 wl_wait.py x &\nEOF"),
        "background-waiter: a heredoc feeding a SHELL is still the command",
    ),
    case(
        "check 0 guards/block_shell_background_waiter.py",
        bash_json("grep -n timeout .claude/hooks/stop/wl_wait.py"),
        "background-waiter CONTROL: merely reading the module",
    ),
    # INVERTED 2026-08-09: a well-shaped whole-file Write used to PASS here, and that is the hole the incident went through. It is now denied like every other direct write, and it lives up in the deny block above only in spirit -- it is asserted here, beside its controls, so the pair reads as one decision.
    case(
        "check_out 2 guards/block_agent_state_shape.py",
        tool_json(
            "Write",
            "/r/agent/deadbeef/STATE.md",
            "content",
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "\n"
            "## Next action\n"
            "\n"
            "go",
        ),
        "agent-state: well-shaped Write is ALSO blocked (shape was never the defect)",
        "worklist.py --state",
    ),
    # The controls that keep the guard from being a blanket denial: it must not reach RULES.md (sharpened by ordinary edits), the root-level plans, the tree's own README, or anything outside the notes tree at all.
    #
    # EVERY ONE OF THESE IS A NEGATIVE: exit 0 is also what a guard that matches NOTHING returns, so they cannot tell a live guard from a dead one and they are not trying to. Their job is the opposite one -- to catch a pattern that grew too broad -- and `agent` without the leading dot is an ordinary word, which is exactly when that stops being hypothetical. The positives above are
    # what proves the guard fires at all: break the pattern in the hook so it matches nothing, and THEY go red while every line below stays green. That one-minute mutation is how this block was checked rather than assumed.
    case(
        "check 0 guards/block_agent_state_shape.py",
        tool_json("Edit", "/r/agent/RULES.md", "new_string", "sharpen"),
        "agent-state: the shared RULES.md edits untouched",
    ),
    case(
        "check 0 guards/block_agent_state_shape.py",
        tool_json("Edit", "/r/agent/deadbeef/RULES.md", "new_string", "sharpen"),
        "agent-state: a session's own RULES.md untouched",
    ),
    case(
        "check 0 guards/block_agent_state_shape.py",
        tool_json("Write", "/r/packages/cli/src/foo.ts", "content", "tiny"),
        "agent-state: non-agent files untouched",
    ),
    case(
        "check 0 guards/block_agent_state_shape.py",
        tool_json(
            "Write",
            "/r/.agent/TRAPS.md",
            "content",
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "\n"
            "## Next action\n"
            "\n"
            "go",
        ),
        "agent-state: TRAPS.md untouched",
    ),
    case(
        "check 0 guards/block_agent_state_shape.py",
        tool_json(
            "Write",
            "/r/agent/README.md",
            "content",
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "\n"
            "## Next action\n"
            "\n"
            "go",
        ),
        "agent-state: the notes tree README untouched",
    ),
    case(
        "check 0 guards/block_agent_state_shape.py",
        tool_json(
            "Write",
            "/r/agent/PLAN-thing.md",
            "content",
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "\n"
            "## Next action\n"
            "\n"
            "go",
        ),
        "agent-state: root-level plan files untouched",
    ),
    # The docs trees are committed prose that this guard must not own, and they are the paths a `*/agent/*/STATE.md` pattern would swallow by accident. Both names are asserted: the standing docs live in docs/agent-reference/ since the 2026-08-14 move, and docs/agent/ is what that tree was called before.
    case(
        "check 0 guards/block_agent_state_shape.py",
        tool_json(
            "Write",
            "/r/docs/agent/b/s/STATE.md",
            "content",
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "\n"
            "## Next action\n"
            "\n"
            "go",
        ),
        "agent-state: docs/agent/ is not this guard's tree",
    ),
    case(
        "check 0 guards/block_agent_state_shape.py",
        tool_json(
            "Write",
            "/r/docs/agent-reference/b/s/STATE.md",
            "content",
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "\n"
            "## Next action\n"
            "\n"
            "go",
        ),
        "agent-state: docs/agent-reference/ is not this guard's tree either",
    ),
    case(
        "check 0 guards/block_inline_workflow_run.py",
        wf_edit_json(
            ".github/workflows/x.yml",
            "      - name: Thin\n"
            "        run: |\n"
            "          echo hi\n"
            "          bash .ci/scripts/quality/x.sh",
        ),
        "inline-workflow-run: thin block ok",
    ),
    case(
        "check 0 guards/block_inline_workflow_run.py",
        wf_edit_json(
            "packages/cli/src/foo.ts",
            "      - name: Big\n"
            "        run: |\n"
            "          echo 1\n"
            "          echo 2\n"
            "          echo 3\n"
            "          echo 4\n"
            "          echo 5\n"
            "          echo 6\n"
            "          echo 7\n"
            "          echo 8\n"
            "          echo 9",
        ),
        "inline-workflow-run: non-workflow file ok",
    ),
]
