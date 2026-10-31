"""The guard smoke suite, as data: every case `.claude/hooks/test-hooks.sh` asserts.

WHY THIS IS A PYTHON MODULE AND NOT A SECOND SHELL SCRIPT. The obvious move for a 2,774-line bash suite is to shard it into several smaller ones. That is ILLEGAL in this tree and the refusal is mechanical, not stylistic: `check:ci-language-policy` freezes a SET of bash paths under `.ci/` and `.claude/`
(`.ci/scripts/quality/check_language_policy.py:137` `COVERED_ROOTS = (".ci", ".claude")`),
and a new tracked `.sh` under either root is one more entry that `baseline_additions` refuses. `.claude/hooks/test-hooks.sh` was itself a member of that set until this port retired it. The precedent a shard would reach for -- `test-worklist-v5.sh` split into 27 files -- predates the freeze and cannot be repeated. So the suite is PORTED, and pytest already collects this directory
(`pyproject.toml` `testpaths`), so the destination needed no wiring.

THE SPEC STRING IN COLUMN 1 IS LOAD-BEARING TEXT, NOT A LABEL. Read it before editing one. `hook_integrity.covmap` decides whether a guard still has a BLOCK case and an ALLOW case by scanning its declared `case_sources` for the literal shape

    check 2 guards/block_x.py

(`.ci/rediacc_ci/quality/hook_integrity.py:459`, `\\b(?:check|check_out)\\s+([0-9]+)\\s+<guard>`). That reader is what credits a guard with coverage, and a port that spelled its cases `case(2, "guards/block_x.py", ...)` would present ZERO cases for all 46 ported guards -- every one of them reading as newly uncovered, whose cheapest fix is to baseline them, which retires the
assertion for good. Keeping the case's identity as one string in the reader's own shape means the port re-keys DATA (`scripts/data/hook-audit-scope.json` `case_sources`) and the reader is never opened.

WHAT DID NOT CHANGE. Every payload, every expected exit code, every message needle and every label below is the one the bash suite asserted. The proof is the label multiset: `hooklabels.py` reads `ok [rc] label` lines out of whatever a suite printed, and it is the SAME function on both sides, so "the port asserts what the suite asserted" is a comparison of two runs rather than a
claim about a diff.

HOW A CASE NAMES ITS GUARD. By the key `check-hook-integrity.sh` inventories it under: `guards/<module>.py` for the 46 guards ported in W5 -- the file really is at `.claude/rediacc_hooks/guards/<module>.py` and the way to RUN one is the dispatcher -- and the path under `.claude/hooks/` for anything still in bash.
"""

import dataclasses
import json
import subprocess
import time

from rediacc_hooks.tests import corpus
from rediacc_hooks.wellknown import GH_ORIGIN, GH_REPO, RENET_REPO

ROOT = corpus.repo_root()
HOOKS = ROOT / ".claude" / "hooks"
GUARD_DISPATCH = ROOT / ".claude" / "rediacc_hooks" / "dispatch.py"
GUARD_MODULES = ROOT / ".claude" / "rediacc_hooks" / "guards"

# The suite derived this with `cd "$DIR/../.." && pwd`. Two cases used to hardcode /home/developer/console and therefore asserted "inside the repo" about a path that is inside the repo only on the machine they were written on; in CI the tree is at /home/runner/work/... and the guard CORRECTLY allowed the command, so the tests
# failed while the code was right. Measured: run 33133377611, PASS=1557 FAIL=2.
TEST_REPO_ROOT = str(ROOT)

# How long any single guard may take. The bash suite had no bound at all, so a guard that hangs on stdin took the whole run down with it and reported nothing; this turns that into one named failure.
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

    `jq -Rn --arg c ... '$c'` emits COMPACT json and does not escape non-ASCII. Python's defaults do the opposite on both counts, and a guard that matches on raw text (the chain head greps stdin; several guards scan the command string before parsing) would be handed different bytes than the suite handed it.
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


def inject_json(command: str, stdout: str, cwd: str | None = None) -> str:
    """A PostToolUse payload: the trapguard rules judge what a command SAID. `cwd` defaults to this checkout; a case that needs a planted file passes a scratch repository instead of writing this one."""
    return _j(
        {
            "tool_name": "Bash",
            "cwd": cwd or TEST_REPO_ROOT,
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

    `spec` is kept verbatim because it is what `hook_integrity.covmap` reads; `verb`, `expected` and `key` are parsed OUT of it rather than passed separately, so the two can never disagree.
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


# Stands for the machine's LOCAL month and day in a payload, and is filled by `today_filled` at the moment the case runs. Local and not UTC, as block_stale_pr_branch_date reads its clock.
TODAY_MARK = "@TODAY-MMDD@"


def today_filled(text: str) -> str:
    """`text` with `TODAY_MARK` replaced by the local MMDD read NOW, so a case built before midnight and run after it still names the day the guard sees."""
    if TODAY_MARK not in text:
        return text
    return text.replace(TODAY_MARK, time.strftime("%m%d"))


def run_guard(
    key: str, payload: str, *, want_stderr: bool, env: dict | None = None, cwd: str | None = None
) -> tuple[int, str]:
    """`(exit code, stderr text)`. stdout is discarded, exactly as the suite did.

    The suite ran `... 2>&1 >/dev/null` for the message assertions, which redirects stderr to the pipe and stdout to /dev/null -- NOT the other way round. A guard's product is what it says on stderr.
    """
    argv = guard_cmd(key)
    completed = subprocess.run(
        argv,
        input=today_filled(payload).encode(),
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
def _handed_down(cmd: str, times: int) -> str:
    """`cmd` wrapped `times` times in `python3 -c "import os; os.system(...)"`: each layer is one program handing a command down, which is what block_review_file_shell_write's depth counts."""
    for _ in range(times):
        cmd = "python3 -c " + json.dumps("import os; os.system(%s)" % json.dumps(cmd))
    return cmd


STATIC: list[Case] = [
    # --- should BLOCK (exit 2) --- The PR body is generated, so a hand-written whole-body write silently drops the worklist-epics block and CI fails minutes later naming nothing useful.
    case(
        "check 2 guards/block_raw_pr_body_edit.py",
        bash_json("gh pr edit 42 --body-file b.md"),
        "raw-pr-body(blocked)",
    ),
    case(
        "check 0 guards/block_raw_pr_body_edit.py",
        bash_json("PYTHONPATH=.ci python3 -m rediacc_ci.pr.sync_epic_block 42 0826-1"),
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
    # THE PRE-PUSH RECEIPT GUARD. A CI round costs ~15 minutes; three of the five reds on PR #579 were sub-2-second gates -- check:format 1.72s, check:ci-python-lint 0.59s, check:ci-parity 1.29s -- which cost roughly 45 minutes of CI between them. The gates existed; nothing made anyone run them.
    #
    # Only the ALLOW direction is pinned here, deliberately. The refusal arms need a receipt file planted at a specific tree sha, which is fixture work this suite's `check` helper cannot express; they live in the dedicated gate suite instead. What these four pin is the half that decides whether the guard is tolerable: a guard that refuses things it has no business refusing is a
    # guard that gets bypassed, and every one of these ran green before the guard existed.
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
    # scp AT COMMAND POSITION, 2026-10-09 (#ecb59527). `(^|[{B}])scp[{B}]` matched after any blank, so a sentence ending in a host spec read as an upload. The launcher the guard names (sshpass) is pinned beside the two prose controls, so the narrowing cannot drift into letting a real upload through.
    case(
        "check 0 guards/block_binary_deploy.py",
        bash_json("echo never run scp bin/renet host:/usr/local/bin/renet"),
        "binary-deploy CONTROL: an unquoted sentence naming scp is not an upload",
    ),
    case(
        "check 0 guards/block_binary_deploy.py",
        bash_json("git commit -m 'docs: scp x h:/p'"),
        "binary-deploy CONTROL: a commit message naming scp is not an upload",
    ),
    case(
        "check 2 guards/block_binary_deploy.py",
        bash_json("sshpass -p x scp x h:/p"),
        "binary-deploy: a launcher before scp is still at command position",
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
    # AND THE EVASION THAT CAME WITH IT. Stripping quoted spans to stop this guard matching prose ALSO removed `sh -c "git commit --amend"`, where the whole command lives inside a quoted span -- the guard returned 0 on a real amend. The comment shipped alongside that draft claimed the dedicated test-block-git-amend.py pinned the `sh -c` case; it did not, and the claim was never
    # checked. One probe found the false comment and the hole together, which is why these live here now rather than in a sentence.
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
    # The quoted case above was pinned; the UNQUOTED one was not, and the guard blocked on it until 2026-08-28. hook_scan_target strips quoted spans, so an ordinary sentence survives it intact and reached a matcher that looked for the phrase ANYWHERE. A doc line or worklist note was refused as a command.
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
    # THE UNQUOTED SENTENCE, for the three guards check:ci-guard-mention-anchoring found refusing it on 2026-10-09. Each matched its command word after any whitespace (or anywhere, for `\bssh\b`), so a doc line or worklist note naming the command was refused; each now anchors at command position. The deny cases after them are what anchoring must not have cost.
    case(
        "check 0 guards/block_cli_bundle.py",
        bash_json("echo the docs say never to run node cli-bundle.js in this repo"),
        "cli-bundle CONTROL: an unquoted sentence naming it is not running it",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("echo the docs say never to run git restore .claude/settings.json in this repo"),
        "protected-files CONTROL: an unquoted sentence naming the restore is not restoring",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("echo never rm .claude/settings.json here"),
        "protected-files CONTROL: an unquoted sentence naming rm is not deleting",
    ),
    case(
        "check 0 guards/block_ssh_docker.py",
        bash_json("echo the docs say never to run ssh docker in this repo"),
        "ssh-docker CONTROL: an unquoted sentence naming it is not running it",
    ),
    case(
        "check 2 guards/block_cli_bundle.py",
        bash_json("cd packages/cli && sudo node cli-bundle.js"),
        "cli-bundle: a prefix command after && is still at command position",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("git -C . restore .claude/settings.json"),
        "protected-files: git global flags before the verb are still reached",
    ),
    case(
        "check 2 guards/block_ssh_docker.py",
        bash_json("timeout 9 ssh prod-1 docker ps"),
        "ssh-docker: a prefix command is still at command position",
    ),
    # #ec63ff8c, 2026-10-09: a quoted ssh remote command, a protected path arriving on stdin through xargs, sshpass stripped as a prefix, and the launchers shellscan now walks (npx, find -exec). Every deny row here was allowed before; every CONTROL row was allowed before and after.
    case(
        "check 2 guards/block_ssh_docker.py",
        bash_json('ssh prod-1 "docker ps"'),
        "ssh-docker: a quoted remote command is a payload the far side runs",
    ),
    case(
        "check 2 guards/block_ssh_docker.py",
        bash_json("ssh -p 2222 -i key prod-1 'sudo docker ps'"),
        "ssh-docker: the remote command behind ssh flags and sudo",
    ),
    case(
        "check 2 guards/block_ssh_docker.py",
        bash_json('sshpass -p x ssh prod-1 "docker ps"'),
        "ssh-docker: a quoted remote command behind sshpass",
    ),
    case(
        "check 2 guards/block_ssh_docker.py",
        bash_json("ssh -t prod-1 'cd /srv && docker compose up -d'"),
        "ssh-docker: docker after a separator inside the remote command",
    ),
    case(
        "check 2 guards/block_ssh_docker.py",
        bash_json("ssh 192.168.111.10 uptime; ssh prod-1 docker ps"),
        "ssh-docker: the bridge carve-out is per ssh, not per line",
    ),
    case(
        "check 0 guards/block_ssh_docker.py",
        bash_json('ssh 192.168.111.10 "docker ps"'),
        "ssh-docker CONTROL: a quoted remote command on the bridge VM",
    ),
    case(
        "check 0 guards/block_ssh_docker.py",
        bash_json("ssh prod-1 'echo docker'"),
        "ssh-docker CONTROL: a remote command that only names docker",
    ),
    case(
        "check 0 guards/block_ssh_docker.py",
        bash_json("ssh -o 'ProxyCommand=ssh -W %h:%p jump' prod-1 uptime"),
        "ssh-docker CONTROL: an option value is not the remote command",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | xargs rm"),
        "protected-files: xargs rm fed the path on stdin",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("printf '%s' scripts/pre-commit-check.sh | xargs git restore"),
        "protected-files: xargs git restore fed the path on stdin",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | sort | xargs git checkout --"),
        "protected-files: an earlier stage of the pipe feeds xargs too",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json(r"find . -name x -exec true {} \; -exec rm .claude/settings.json \;"),
        "protected-files: every find -exec is walked, not only the first",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | cat"),
        "protected-files CONTROL: piping the path to cat reads it",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | xargs cat"),
        "protected-files CONTROL: xargs cat reads it",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json; ls | xargs rm"),
        "protected-files CONTROL: a separator ends the pipe before xargs",
    ),
    case(
        "check 2 guards/block_cli_bundle.py",
        bash_json("npx -y node packages/cli/dist/cli.js"),
        "cli-bundle: npx with its own flag before node",
    ),
    case(
        "check 2 guards/block_cli_bundle.py",
        bash_json(r"find packages -maxdepth 0 -exec node cli-bundle.js \;"),
        "cli-bundle: find -exec running node",
    ),
    case(
        "check 0 guards/block_cli_bundle.py",
        bash_json("npx -y prettier --check packages/cli/dist/cli.js"),
        "cli-bundle CONTROL: npx running another program over the bundle path",
    ),
    case(
        "check 2 guards/block_ssh_docker.py",
        bash_json('ssh prod-1 -t "docker ps"'),
        "ssh-docker: an ssh option after the destination",
    ),
    case(
        "check 2 guards/block_ssh_docker.py",
        bash_json('ssh bastion ssh prod-1 "docker ps"'),
        "ssh-docker: an ssh hop inside the remote command",
    ),
    case(
        "check 2 guards/block_ssh_docker.py",
        bash_json('sshpass -e ssh prod-1 "docker ps"'),
        "ssh-docker: sshpass -e takes no value",
    ),
    case(
        "check 0 guards/block_ssh_docker.py",
        bash_json("ssh -O check prod-1"),
        "ssh-docker CONTROL: a control command names no remote command",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | git restore --pathspec-from-file=-"),
        "protected-files: git reads its pathspec from stdin",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json(r"find .claude/settings.json -exec rm {} \;"),
        "protected-files: find -exec rm of the path find names",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("git ls-files .claude/settings.json | xargs git rm"),
        "protected-files: xargs git rm",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | xargs ls -l"),
        "protected-files CONTROL: xargs ls lists it",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json(r"find .claude/settings.json -exec cat {} \;"),
        "protected-files CONTROL: find -exec cat reads it",
    ),
    # #32e75fa4 (review 4aad4597.1, 2026-10-09): xargs hands the fed words to a `sh -c` payload as its positional parameters, so the rm inside it deletes the path. Each refusal was allowed (rc 0) before.
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("""echo .claude/settings.json | xargs sh -c 'rm "$0"'"""),
        "protected-files: an xargs-fed sh -c payload removes $0",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("""echo .claude/settings.json | xargs bash -c 'rm "$@"' _"""),
        "protected-files: an xargs-fed bash -c payload removes $@",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | xargs -I{} sh -c 'rm {}'"),
        "protected-files: xargs -I substitutes the path into a sh -c payload",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("""echo .claude/settings.json | xargs sh -c 'cat "$0"'"""),
        "protected-files CONTROL: an xargs-fed sh -c payload that only reads",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("""echo packages/x.ts | xargs sh -c 'rm "$0"'"""),
        "protected-files CONTROL: an xargs-fed sh -c rm of an unprotected path",
    ),
    # The other way a payload inherits the feed: its own commands read the shell's stdin, so the xargs inside it is fed. Allowed (rc 0) before.
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | sh -c 'xargs rm'"),
        "protected-files: a piped sh -c payload's xargs rm reads the shell's stdin",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | bash -c 'cat | xargs rm'"),
        "protected-files: a piped bash -c payload passes its stdin through cat to xargs rm",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | bash -c 'xargs cat'"),
        "protected-files CONTROL: a piped bash -c payload that only reads",
    ),
    case(
        "check 2 guards/block_cli_bundle.py",
        bash_json("npx -c 'node cli-bundle.js'"),
        "cli-bundle: npx -c runs a shell string",
    ),
    # #31ed6c5f, 2026-10-09: a wrapper is a command the walk found, not a quoted word that spells one. Both refusals below were rc 2 before, the second on the lead's own worklist note.
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("""echo "sh -c 'rm x'" "x .claude/settings.json | y\""""),
        "protected-files CONTROL: a quoted sh -c is an echo argument, not a wrapper",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json(
            """python3 .claude/hooks/stop/worklist.py --add d778be9d "sh -c 'rm x' then .claude/settings.json | y\""""
        ),
        "protected-files CONTROL: a worklist note quoting sh -c rm and the settings path",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("""echo "sh -c 'rm x'"; sh -c 'rm .claude/settings.json'"""),
        "protected-files: a real sh -c after a quoted mention is still read",
    ),
    # #31ed6c5f: a group's stdin is every member's, and a read loop turns the feed into a variable. All three were allowed (rc 0) before.
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | (xargs rm)"),
        "protected-files: a subshell consumer is fed",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | { xargs rm; }"),
        "protected-files: a brace-group consumer is fed",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('echo .claude/settings.json | while read f; do rm "$f"; done'),
        "protected-files: a read loop removes the read variable",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('echo .claude/settings.json | while read -r f; do cat "$f"; done'),
        "protected-files CONTROL: a read loop that only reads",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("echo packages/x.ts | (xargs rm)"),
        "protected-files CONTROL: a subshell consumer fed an unprotected path",
    ),
    # Review e085085d.1: a loop's stdin is what `done` redirects, and what feeds the loop feeds its body. Each refusal was allowed (rc 0) before; the first was pinned as a KNOWN GAP.
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('while read f; do rm "$f"; done <<< .claude/settings.json'),
        "protected-files: a read loop fed through done <<<",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('while read f; do rm "$f"; done < <(echo .claude/settings.json)'),
        "protected-files: a read loop fed through done < <(...)",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("while read f; do rm \"$f\"; done <<'EOF'\n.claude/settings.json\nEOF"),
        "protected-files: a read loop fed a heredoc through done",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | while true; do xargs rm; break; done"),
        "protected-files: a piped loop's body reads the loop's stdin",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('while read f; do cat "$f"; done <<< .claude/settings.json'),
        "protected-files CONTROL: a loop fed through done that only reads",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('while read f; do rm "$f"; done <<< packages/x.ts'),
        "protected-files CONTROL: a loop fed an unprotected path through done",
    ),
    # The path reaching the destructive command through syntax the prose view drops (e085085d.1 sweep): quoting, a variable, a for list, a substitution, a cd. Each was allowed (rc 0) before.
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('rm ".claude/settings.json"'),
        "protected-files: a quoted path",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('git restore -- ".claude/settings.json"'),
        "protected-files: a quoted path after git restore --",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('f=.claude/settings.json; rm "$f"'),
        "protected-files: a variable holding the path",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('for f in .claude/settings.json; do rm "$f"; done'),
        "protected-files: a for list holding the path",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('rm "$(echo .claude/settings.json)"'),
        "protected-files: a quoted substitution printing the path",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("cd .claude && rm settings.json"),
        "protected-files: a path relative to a cd",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm .claude//settings.json"),
        "protected-files: a path with a doubled slash",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm -rf .claude"),
        "protected-files: a recursive rm of a directory holding the path",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('for f in .claude/settings.json; do cat "$f"; done'),
        "protected-files CONTROL: a for list read, not removed",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('f=.claude/settings.json; cat "$f"'),
        "protected-files CONTROL: a variable read, not removed",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("rm -rf .claude/tmp-scratch"),
        "protected-files CONTROL: a recursive rm beside the path, not above it",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("rm .claude/settings.local.json"),
        "protected-files CONTROL: a neighbouring file",
    ),
    # Review c093f0f3.2: a word the guard cannot evaluate (`$(...)`, a backtick, an unresolved `$NAME`) is a wildcard; it is refused when a literal segment is a protected path's and the pattern can reach a protected file. Each refusal was allowed (rc 0) before.
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm .claude/$(echo settings.json)"),
        "protected-files: a substitution after the protected directory",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm $(echo .claude)/settings.json"),
        "protected-files: a substitution before the protected basename",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm `echo .claude`/settings.json"),
        "protected-files: a backtick substitution before the protected basename",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('rm .claude/"$NAME"'),
        "protected-files: an unresolved variable after the protected directory",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm -rf $(pwd)/.claude"),
        "protected-files: a recursive rm of the protected directory under a substitution",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('rm "$(mktemp)"'),
        "protected-files CONTROL: a substitution with no protected segment",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('rm -rf "$(mktemp -d)/x"'),
        "protected-files CONTROL: a substitution beside an unrelated segment",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('rm "$X".json'),
        "protected-files CONTROL: a variable beside a partial basename",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("rm .claude/$(echo tmp)/x.log"),
        "protected-files CONTROL: a protected segment whose pattern cannot reach a protected file",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('rm -rf "$S/w2clone"'),
        "protected-files CONTROL: a recursive rm of an unrelated directory under a variable",
    ),
    # Review cd8ccb11.1-.2: a wildcarded operand is normalised segment by segment (`.` dropped, `//` collapsed, `..` popping a literal segment, a `..` popping a substitution reaching anything under the literal prefix). Measured on cd8ccb112, 7 rows were wrong: 6 refusals were allowed (rc 0), namely the `./`, `//` and literal-`..` rows before a substitution, the `./` row after one, `"$D"/.claude/..` and the unnormalised substitution text; and the `"$(mktemp -d)"/..` control was refused. The other 4 refusals and 3 controls were already right, and stay as pins.
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm .claude/./$(echo settings.json)"),
        "protected-files: a ./ segment before a substitution",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm .claude//$(echo settings.json)"),
        "protected-files: a doubled slash before a substitution",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm .claude/x/../$(echo settings.json)"),
        "protected-files: a .. popping a literal segment before a substitution",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm $(echo .claude)/./settings.json"),
        "protected-files: a ./ segment after a substitution",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('rm -rf "$D"/.claude/..'),
        "protected-files: a recursive rm whose .. pops the protected directory under a variable",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm -rf .claude/$(echo x)/.."),
        "protected-files: a recursive rm whose .. pops a substitution under the protected directory",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm .claude/$(echo x)/../settings.json"),
        "protected-files: a .. popping a substitution back onto the protected file",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('rm "$(echo .claude/./settings.json)"'),
        "protected-files: a substitution printing an unnormalised protected path",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm -rf .claude/x/.."),
        "protected-files: a recursive rm of a literal path that normalises to the protected directory",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('rm "$(mktemp -d)"/../x.log'),
        "protected-files CONTROL: a .. popping a substitution beside an unrelated file",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm -rf ./$(echo build)/.."),
        "protected-files: a recursive rm whose .. pops a substitution back onto the project root",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("rm ./$(echo build)/out.txt"),
        "protected-files CONTROL: a ./ substitution path with no protected segment",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('rm -rf "$(mktemp -d)"/..'),
        "protected-files CONTROL: a recursive rm whose .. pops an unknown absolute substitution",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("rm .claude/./$(echo tmp)/x.log"),
        "protected-files CONTROL: a ./ protected-directory path that cannot reach a protected file",
    ),
    # Review f12404e0.1-.2: a glob (`*`, `?`, `[`) is a pattern matched segment by segment against the protected set, in a plain word and inside a substitution's text; and a word whose `..` pops a substitution is skipped only where rm itself refuses it. Rows run from `.claude/` carry that `cwd`.
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm $(echo .claude/settings.json*)"),
        "protected-files: a glob inside a substitution names the protected file",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm .claude/settings.js*"),
        "protected-files: a glob names the protected file",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm .claude/*"),
        "protected-files: a glob over the protected directory",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('rm "$(ls .claude/settings.j?on)"'),
        "protected-files: a ? glob inside a quoted substitution",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm -rf .cl*"),
        "protected-files: a recursive rm of a glob naming the protected directory",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("rm *.log"),
        "protected-files CONTROL: a glob that cannot cross into a directory",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("rm .claude/*.log"),
        "protected-files CONTROL: a glob in the protected directory that cannot name a protected file",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("rm -rf /tmp/zz-*"),
        "protected-files CONTROL: a recursive glob elsewhere",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("rm -rf .claude/*/"),
        "protected-files CONTROL: a trailing slash makes a glob expand to directories, never the protected file",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("rm -f */settings.json"),
        "protected-files CONTROL: a glob never matches a leading dot, so */ cannot reach .claude/",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm -rf scr*/"),
        "protected-files: a directory-only glob over the directory holding a protected file",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        _j({"tool_input": {"command": 'rm -rf "$(echo x)/.."'}, "cwd": str(ROOT / ".claude")}),
        "protected-files CONTROL: from .claude/, rm refuses a last component of .. (GNU rm 9.7, measured)",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        _j({"tool_input": {"command": 'git rm -r "$(echo x)/.."'}, "cwd": str(ROOT / ".claude")}),
        "protected-files: from .claude/, git rm -r normalises x/.. to the directory holding the protected file",
    ),
    # Review 63ee61e3.2: a bracket class is matched the way bash expands it, never compiled from raw text, so no pattern can crash the guard. Measured on bash 5.3: an invalid range and an unknown POSIX class match nothing, `]` first is a member, an unterminated `[` is literal; an unknown class is still read as any character, toward refusing.
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("rm .claude/[z-a]"),
        "protected-files CONTROL: an invalid range matches nothing, as bash expands it (it crashed the guard, rc 1)",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("rm .claude/settings.jso[!]"),
        "protected-files CONTROL: an unterminated class is literal text (it crashed the guard, rc 1)",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("rm .claude/s[e-a]ttings.json"),
        "protected-files CONTROL: an invalid range inside the protected name matches nothing",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm .claude/s[[:alpha:]]ttings.json"),
        "protected-files: a POSIX class names the protected file",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm .claude/s[]e]ttings.json"),
        "protected-files: a class whose first member is ] names the protected file",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm .claude/s[!a-d]ttings.json"),
        "protected-files: a negated range names the protected file",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm .claude/s[[:bogus:]]ttings.json"),
        "protected-files: an unknown POSIX class fails safe toward the protected file",
    ),
    # Found on 2e8dfd963 by this writer's own cleanup command: a `?` inside `${T:?}` was read as a glob, and a word whose root is unevaluated was resolved under the run's directory, so the documented safe idiom was refused from the project root. Both controls were refused (rc 2); the refusals stay refused.
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('rm -rf "${T:?}"'),
        "protected-files CONTROL: the ${VAR:?} idiom is a parameter, not a glob",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('rm -rf "$(mktemp -d)"/*'),
        "protected-files CONTROL: a glob under an unknown root",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('rm -rf "${T:?}"/.claude'),
        "protected-files: a protected segment after a ${VAR:?} root",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("rm -rf ./*"),
        "protected-files: a glob over the project root's own directories",
    ),
    # Review fc3f376a.3: a glob under an unknown root still names the protected file by its trailing segments. Review fc3f376a.4: a protected path written after a substitution is `_unjudgeable`'s, pinned here. The two glob refusals were allowed (rc 0) before; the controls stay allowed.
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('rm "$D"/.claude/settings*'),
        "protected-files: a glob naming the protected file under an unknown root",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('rm -rf "$D"/.cl*'),
        "protected-files: a recursive glob naming the protected directory under an unknown root",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('rm "$(pwd)"/.claude/settings.json'),
        "protected-files: a protected path written after a substitution",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('rm -rf "$D"/*'),
        "protected-files CONTROL: a bare glob under an unknown root names no protected segment",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('rm "$D"/.claude/notes*'),
        "protected-files CONTROL: a glob under an unknown root that no protected name matches",
    ),
    # Review 094dea3b.4-.5: a glob glued to an unknown root with no slash was allowed (rc 0); a protected basename directly under an unknown root is refused on purpose, since the root may be `.claude`.
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('rm "$D"settings*'),
        "protected-files: a glob glued to an unknown root with no slash",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('rm "$D"/settings*'),
        "protected-files: a protected basename glob directly under an unknown root",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('rm "$D"notes*'),
        "protected-files CONTROL: a glued glob no protected name matches",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json('rm -f "$D"*'),
        "protected-files CONTROL: a bare glob glued to an unknown root",
    ),
    # A prefix command's option VALUE is not the command (cac47d16.1 sweep, shellscan._prefix_option): each refusal was allowed (rc 0) before, the value read as the command.
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | xargs --max-procs 2 rm"),
        "protected-files: xargs --max-procs takes a separate value",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | xargs -rP 2 rm"),
        "protected-files: xargs bundle ending in a value letter",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | xargs --max-p 2 rm"),
        "protected-files: xargs abbreviated long option",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("sudo --user root rm .claude/settings.json"),
        "protected-files: sudo --user takes a separate value",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("stdbuf --output L rm .claude/settings.json"),
        "protected-files: stdbuf --output takes a separate value",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json('env -S "rm .claude/settings.json"'),
        "protected-files: env -S splits its string into the command",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("env --chdir .claude rm settings.json"),
        "protected-files: env --chdir moves where rm runs",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("echo .claude/settings.json | xargs --max-procs 2 cat"),
        "protected-files CONTROL: xargs --max-procs feeding a reader",
    ),
    case(
        "check 0 guards/block_protected_files.py",
        bash_json("env --chdir /tmp rm settings.json"),
        "protected-files CONTROL: env --chdir elsewhere",
    ),
    # Review 5aa562c3.1: a fed shell payload with any destructive command is refused whether or not it names $0, because both of these delete the path without the rm naming a positional.
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("""echo .claude/settings.json | xargs sh -c 'f=$0; rm "$f"'"""),
        "protected-files: a fed payload copying $0 before the rm",
    ),
    case(
        "check 2 guards/block_protected_files.py",
        bash_json("""echo .claude/settings.json | xargs sh -c 'for f; do rm "$f"; done' _"""),
        "protected-files: a fed payload looping over its positionals",
    ),
    # #31ed6c5f: npm's own parse finds the program, abbreviations included, and `npm exec`/`npm x` launch like npx. Each was allowed (rc 0) before.
    case(
        "check 2 guards/block_cli_bundle.py",
        bash_json("npx --logl silent node packages/cli/dist/cli.js"),
        "cli-bundle: an abbreviated npx value option",
    ),
    case(
        "check 2 guards/block_cli_bundle.py",
        bash_json("npm exec -- node packages/cli/dist/cli.js"),
        "cli-bundle: npm exec launches node",
    ),
    case(
        "check 2 guards/block_cli_bundle.py",
        bash_json("npm x node packages/cli/dist/cli.js"),
        "cli-bundle: npm x launches node",
    ),
    case(
        "check 2 guards/block_cli_bundle.py",
        bash_json("npm --logl silent exe -- node packages/cli/dist/cli.js"),
        "cli-bundle: an npm option before an abbreviated exec",
    ),
    case(
        "check 0 guards/block_cli_bundle.py",
        bash_json("npm exec -- prettier --check packages/cli/dist/cli.js"),
        "cli-bundle CONTROL: npm exec running another program over the bundle path",
    ),
    case(
        "check 0 guards/block_cli_bundle.py",
        bash_json("npm run build -- packages/cli/dist/cli.js"),
        "cli-bundle CONTROL: npm run is not a launcher",
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
    # #503f0ba8, 2026-10-09: the commands `npx` and `find -exec` LAUNCH, judged through `shellscan.every_run`. Every deny row below was allowed on the base (rc 0, measured); every CONTROL row was allowed before and after. A launched run that executes ELSEWHERE (`find -execdir`, `npx -w/--prefix`, `shellscan.Launch.elsewhere`) is left unjudged by the guards that resolve a cwd or a package.
    case(
        "check 2 guards/block_long_sleep.py",
        bash_json(r"find . -maxdepth 0 -exec sleep 900 \;"),
        "long-sleep: a sleep that find -exec launches",
    ),
    case(
        "check 2 guards/block_long_sleep.py",
        bash_json("npx sleep 900"),
        "long-sleep: a sleep that npx launches",
    ),
    case(
        "check 0 guards/block_long_sleep.py",
        bash_json("echo find . -maxdepth 0 -exec sleep 900"),
        "long-sleep CONTROL: prose naming a launched sleep",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(r"find . -maxdepth 0 -exec python3 -m rediacc_ci.dev.worktree create x \;"),
        "worktree-add: the port's create launched by find -exec",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "find . -maxdepth 0 -exec python3 -c \"import os; os.system('git worktree add /tmp/x')\" \\;"
        ),
        "worktree-add: a python program launched by find -exec",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json(
            r"find . -maxdepth 0 -exec python3 -c 'print(\"never run git worktree add here\")' \;"
        ),
        "worktree-add CONTROL: a launched python printing a sentence",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("echo find . -exec python3 -m rediacc_ci.dev.worktree create x"),
        "worktree-add CONTROL: prose naming a launched create",
    ),
    case(
        "check 2 guards/block_host_toolchain_run.py",
        bash_json("find . -name '*.py' -exec npx ruff format {} +"),
        "host-toolchain: npx ruff launched by find -exec",
    ),
    case(
        "check 0 guards/block_host_toolchain_run.py",
        bash_json("echo find . -name x -exec npx ruff format {} +"),
        "host-toolchain CONTROL: prose naming a launched npx ruff",
    ),
    # #0c331972: npm's own option grammar (shellscan._launches) instead of a hand-rolled `-y` skip, so both shapes below were allowed at 306285231 (rc 0, measured).
    case(
        "check 2 guards/block_host_toolchain_run.py",
        bash_json("npx --logl silent --yes ruff check"),
        "host-toolchain: npx ruff behind a value option",
    ),
    case(
        "check 2 guards/block_host_toolchain_run.py",
        bash_json("npm x -y ruff check"),
        "host-toolchain: npx ruff through the npm x alias",
    ),
    case(
        "check 0 guards/block_host_toolchain_run.py",
        bash_json("echo 'npm x -y ruff check'"),
        "host-toolchain CONTROL: prose naming npm x ruff",
    ),
    case(
        "check 2 guards/block_self_matching_pgrep.py",
        bash_json(r"find . -maxdepth 0 -exec pkill -f sleep \;"),
        "self-matching-pgrep: a pkill -f that find -exec launches",
    ),
    case(
        "check 0 guards/block_self_matching_pgrep.py",
        bash_json("echo find . -maxdepth 0 -exec pkill -f sleep"),
        "self-matching-pgrep CONTROL: prose naming a launched pkill",
    ),
    case(
        "check 2 guards/block_missing_npm_script.py",
        bash_json("npx -c 'npm run does-not-exist-example'"),
        "missing-npm-script: an npm run that npx -c launches",
    ),
    case(
        "check 2 guards/block_missing_npm_script.py",
        bash_json(r"find packages -maxdepth 1 -name cli -exec npm run does-not-exist-example \;"),
        "missing-npm-script: find -exec runs npm in find's own cwd",
    ),
    case(
        "check 0 guards/block_missing_npm_script.py",
        bash_json(
            r"find packages -maxdepth 1 -name cli -execdir npm run does-not-exist-example \;"
        ),
        "missing-npm-script CONTROL: find -execdir runs npm in each match's directory",
    ),
    case(
        "check 0 guards/block_missing_npm_script.py",
        bash_json("npx -w packages/cli -c 'npm run does-not-exist-example'"),
        "missing-npm-script CONTROL: npx -w runs npm in another package",
    ),
    case(
        "check 0 guards/block_missing_npm_script.py",
        bash_json("npx -c 'npm run check:ci-python-lint'"),
        "missing-npm-script CONTROL: a launched npm run of a real script",
    ),
    case(
        "check 2 guards/block_raw_ci_read.py",
        bash_json("npx -c 'gh pr checks 591'"),
        "raw-ci-read: a gh read that npx -c launches",
    ),
    case(
        "check 2 guards/block_raw_ci_read.py",
        bash_json(r"find . -maxdepth 0 -exec gh run list --limit 1 \;"),
        "raw-ci-read: a gh read that find -exec launches",
    ),
    case(
        "check 0 guards/block_raw_ci_read.py",
        bash_json("echo npx -c gh pr checks 591"),
        "raw-ci-read CONTROL: prose naming a launched read",
    ),
    case(
        "check 2 guards/block_unscoped_formatter_run.py",
        bash_json(r"find . -maxdepth 0 -exec ruff format \;"),
        "unscoped-formatter: find -exec runs ruff format with no path",
    ),
    case(
        "check 2 guards/block_unscoped_formatter_run.py",
        bash_json("npx -c 'eslint --fix .'"),
        "unscoped-formatter: npx -c runs eslint --fix on the root",
    ),
    case(
        "check 0 guards/block_unscoped_formatter_run.py",
        bash_json("find . -name '*.py' -exec ruff format {} +"),
        "unscoped-formatter CONTROL: find -exec naming {} is scoped",
    ),
    case(
        "check 0 guards/block_unscoped_formatter_run.py",
        bash_json(r"find packages -name cli -execdir ruff format . \;"),
        "unscoped-formatter CONTROL: find -execdir's . is each match's directory",
    ),
    # #0c331972: the launched command comes from shellscan's npm parser. The two deny rows were allowed at 306285231 (rc 0, measured); npm consumes a flag written before `--`, so the third hands prettier no --write.
    case(
        "check 2 guards/block_unscoped_formatter_run.py",
        bash_json("npm x -- prettier --write"),
        "unscoped-formatter: npm x runs prettier --write with no path",
    ),
    case(
        "check 2 guards/block_unscoped_formatter_run.py",
        bash_json("npx --logl silent --yes prettier --write"),
        "unscoped-formatter: a value option npx takes does not hide the tool",
    ),
    case(
        "check 0 guards/block_unscoped_formatter_run.py",
        bash_json("npm x prettier --write"),
        "unscoped-formatter CONTROL: npm x eats a flag written before --",
    ),
    case(
        "check 2 guards/block_unscoped_formatter_run.py",
        bash_json("npx prettier --write $files"),
        "unscoped-formatter: an unquoted variable npx hands on may vanish",
    ),
    # Review 0bbd6471.2: a versioned spec under the npm spellings, which shellscan launches as npx does.
    case(
        "check 2 guards/block_unscoped_formatter_run.py",
        bash_json("npm exec -- prettier@3 --write"),
        "unscoped-formatter: npm exec with a versioned spec",
    ),
    case(
        "check 2 guards/block_unscoped_formatter_run.py",
        bash_json("npm x -- prettier@3 --write"),
        "unscoped-formatter: npm x with a versioned spec",
    ),
    case(
        "check 2 guards/block_suppressions_shell_write.py",
        bash_json("find . -name '*.py' -exec sed -i 's/$/  # " + "no" + "qa: E501/' {} +"),
        "suppressions-shell-write: sed -i launched by find -exec on the *.py it names",
    ),
    case(
        "check 0 guards/block_suppressions_shell_write.py",
        bash_json("find . -name '*.py' -exec grep -n " + "no" + "qa {} +"),
        "suppressions-shell-write CONTROL: a launched grep reads, never writes",
    ),
    # #f3f36655: a script run BY PATH is read like a heredoc; the refusals need a scratch script on disk and live in test-block_suppressions.py. These pin the two allow paths: a TRACKED script whose own source carries markers (worklist.py: reading it would refuse every run), and a script that cannot be read, which fails open.
    case(
        "check 0 guards/block_suppressions_shell_write.py",
        bash_json("python3 .claude/hooks/stop/worklist.py --list --open x"),
        "suppressions-shell-write CONTROL: a tracked script whose source carries markers",
    ),
    case(
        "check 0 guards/block_suppressions_shell_write.py",
        bash_json("python3 /nonexistent/zz-never-written.py"),
        "suppressions-shell-write CONTROL: a script that cannot be read fails open",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("find agent/reviews -name '*.md' -exec sed -i s/high/low/ {} +"),
        "review-file-shell-write: sed -i launched by find under agent/reviews",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(r"find agent/reviews -name '*.md' -exec cp /tmp/x.md {} \;"),
        "review-file-shell-write: a launched cp onto the files find names",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json(r"find agent/reviews -name '*.md' -exec cp {} /tmp/ \;"),
        "review-file-shell-write CONTROL: a launched copy OUT of the directory",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("echo find agent/reviews -exec sed -i s/high/low/ {} +"),
        "review-file-shell-write CONTROL: prose naming a launched sed -i",
    ),
    # The cac47d16.1 sweep: a copy's destination is getopt's answer. Both refusals were allowed (rc 0) before, and the control was refused.
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("cp -t agent/reviews/1231-9 /tmp/x.md"),
        "review-file-shell-write: cp -t into the review directory",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("echo agent/reviews/1231-9/ | xargs cp /tmp/x.md"),
        "review-file-shell-write: xargs appends the review directory as the destination",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("cp -t /tmp agent/reviews/1231-9/a.md"),
        "review-file-shell-write CONTROL: cp -t copies a review file OUT",
    ),
    # Review 6dcf79c7.1-.2: a Python template filled by keyword, by a star width's extra argument, or from a mapping. Each was allowed (rc 0) before.
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 - <<'EOF'\nimport os\nos.system('echo x > {p}'.format(p='agent/reviews/a.md'))\nEOF"
        ),
        "review-file-shell-write: a str.format keyword field fills the redirect target",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 - <<'EOF'\nimport os\nos.system('echo x > %*sfoo' % (0, 'agent/reviews/a.md'))\nEOF"
        ),
        "review-file-shell-write: a star width takes its own argument",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 - <<'EOF'\nimport os\nos.system('echo x > %(p)s' % {'p': 'agent/reviews/a.md'})\nEOF"
        ),
        "review-file-shell-write: a percent mapping key fills the redirect target",
    ),
    # The twin of the coordinator finding: a program that only READS a review file is allowed, one that writes it is refused.
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('agent/reviews/1231-9/a.md')\nprint(p.read_text())\nEOF"
        ),
        "review-file-shell-write CONTROL: a heredoc that only reads a review file",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('agent/reviews/1231-9/a.md')\np.write_text('x')\nEOF"
        ),
        "review-file-shell-write: a heredoc writing a review file through Path",
    ),
    # #c4542b69: a script run BY PATH is read like a heredoc; the refusals need scratch scripts and live in test-block_review_file_edit.py. These pin the allow paths: a TRACKED script whose own text names a review path and writes files, and a script that cannot be read, which fails open.
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("python3 .claude/rediacc_hooks/tests/test_wl_loopspeed.py"),
        "review-file-shell-write CONTROL: a tracked script the guard would refuse if it read it",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("python3 /nonexistent/zz-agent-reviews-writer.py"),
        "review-file-shell-write CONTROL: a script that cannot be read fails open",
    ),
    # Review c093f0f3.1: more auto-numbered fields than positionals (`*row`) rendered by raising StopIteration inside the guard. An unknown field renders as a placeholder.
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 - <<'EOF'\nimport os\nrow = ['a', 'b', 'c']\nos.system('{} {} {} > agent/reviews/a.md'.format(*row))\nEOF"
        ),
        "review-file-shell-write: more auto fields than positionals before a review redirect",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 - <<'EOF'\nimport os\nrow = ['a', 'b', 'c']\nos.system('echo {} {} {} > /tmp/x'.format(*row))\nprint('agent/reviews/a.md')\nEOF"
        ),
        "review-file-shell-write CONTROL: more auto fields than positionals, written elsewhere",
    ),
    case(
        "check 2 guards/block_ssh_file_write.py",
        bash_json(r"find . -maxdepth 0 -exec ssh prod-1 'cat > /etc/x' \;"),
        "ssh-file-write: an ssh remote write that find -exec launches",
    ),
    case(
        "check 2 guards/block_ssh_file_write.py",
        bash_json("npx -c \"ssh prod-1 'tee /etc/x'\""),
        "ssh-file-write: an ssh remote tee that npx -c launches",
    ),
    case(
        "check 0 guards/block_ssh_file_write.py",
        bash_json("echo \"find . -exec ssh prod-1 'cat > /etc/x' ;\""),
        "ssh-file-write CONTROL: prose naming a launched remote write",
    ),
    # The shared ssh parser (`shellscan.ssh_remote_commands`) replaced this guard's own copy, and four answers moved ON PURPOSE: the old option table had no `P` (a typo), it stopped at the destination although OpenSSH reads options after it, and it never walked a hop.
    case(
        "check 2 guards/block_ssh_file_write.py",
        bash_json("ssh -P tag prod-1 tee /etc/x < f"),
        "ssh-file-write: -P takes a value, so the remote command is the tee",
    ),
    case(
        "check 2 guards/block_ssh_file_write.py",
        bash_json("ssh prod-1 -t tee /etc/x < f"),
        "ssh-file-write: an option after the destination is ssh's, not the remote command",
    ),
    case(
        "check 2 guards/block_ssh_file_write.py",
        bash_json('ssh jump "ssh prod-1 tee /etc/x"'),
        "ssh-file-write: a remote write one hop further in",
    ),
    case(
        "check 0 guards/block_ssh_file_write.py",
        bash_json('ssh prod-1 -o "ProxyCommand=nc %h %p 2>/tmp/err" uptime'),
        "ssh-file-write CONTROL: a ProxyCommand's redirect is local, and the remote command is uptime",
    ),
    # Review findings fa5d11be.1-.4 on block_worktree_add: an option's value is not the script, `-e` takes attached code, a program too deep for `ast` is read by regex instead of crashing the guard, and bracket-delimited quote-like literals are read. Each deny row was allowed on the base (rc 0, or rc 1 from a traceback for the deep one).
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json('perl -I lib -e \'system("git","worktree","add","x")\''),
        "worktree-add: perl -I's value is not the script, so the -e after it runs (fa5d11be.1)",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("perl -I lib script.pl git worktree add x"),
        "worktree-add CONTROL: words after perl's script are its arguments (fa5d11be.1)",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("perl '-esystem(\"git worktree add x\")'"),
        "worktree-add: perl -e with its code attached (fa5d11be.2)",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("perl -Iexample -e 'system(\"git worktree add x\")'"),
        "worktree-add: an attached -I value holding an e is not an eval (fa5d11be.2)",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("perl -x /tmp -e 'print 1'"),
        "worktree-add CONTROL: a perl one-liner with no worktree in it (fa5d11be.2)",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "python3 -c \"import os; os.system('git worktree add /tmp/x'); x = %s1\""
            % ("-" * 10000)
        ),
        "worktree-add: a program too deep for ast is read by regex, not crashed on (fa5d11be.3)",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json('python3 -c "x = %s1"' % ("-" * 10000)),
        "worktree-add CONTROL: a deep program that runs nothing (fa5d11be.3)",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("perl -e 'system qw(git worktree add x)'"),
        "worktree-add: a perl qw() word list spells the command (fa5d11be.4)",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("perl -e 'print qw(never run git worktree add here)'"),
        "worktree-add CONTROL: a qw() sentence is not a command (fa5d11be.4)",
    ),
    # #78afdc0b: the program text is `shellscan.interpreter_program`'s reading, so a script run BY PATH is read and python's option parse is the shared one. Each deny row was allowed (rc 0) at c72518af1; the scripts on disk are in test_hooks_fixtures.py.
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "python3 --check-hash-based-pycs always -c \"import os; os.system('git worktree add x')\""
        ),
        "worktree-add: an option's value is not the script, so the -c after it runs (#78afdc0b)",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' 'import os' 'os.system(\"git worktree add x\")' > /tmp/wt-78afdc0b.py; "
            "python3 /tmp/wt-78afdc0b.py"
        ),
        "worktree-add: a script the same command writes, then runs by path (#78afdc0b)",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' 'print(\"never run git worktree list here\")' > /tmp/wt-78afdc0b.py; "
            "python3 /tmp/wt-78afdc0b.py"
        ),
        "worktree-add CONTROL: a written script printing a sentence (#78afdc0b)",
    ),
    # 33f26fa7c refuses an untracked script naming the phrase whatever it does with the words, so the sentence that names `worktree add` is no longer a control.
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' 'print(\"never run git worktree add here\")' > /tmp/wt-78afdc0b.py; "
            "python3 /tmp/wt-78afdc0b.py"
        ),
        "worktree-add: a written script naming the phrase is refused for its text (33f26fa7c)",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("cp /tmp/a.py /tmp/wt-78afdc0b.py && python3 /tmp/wt-78afdc0b.py worktree add x"),
        "worktree-add: an unreadable script on a line naming the verb is unjudgeable (#78afdc0b)",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("cp /tmp/a.py /tmp/wt-78afdc0b.py && python3 /tmp/wt-78afdc0b.py"),
        "worktree-add CONTROL: an unreadable script on a line naming no worktree verb (#78afdc0b)",
    ),
    # A noexec shell (`bash -n`, a cluster holding `n`, `-o noexec`) parses its script and runs none of it, so a syntax check of an edited script that names the phrase is not a run (#bfe569ca: `bash -n .ci/bootstrap.sh` was refused for its `per-worktree` comment). Each 0 row was rc 2 before; the 2 rows pin that only noexec is exempt.
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' '# per-worktree cache' 'git worktree add x' > /tmp/wt-bfe569ca.sh; bash -n /tmp/wt-bfe569ca.sh"
        ),
        "worktree-add CONTROL: `bash -n` on a written script naming the phrase (#bfe569ca)",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' '# per-worktree cache' 'git worktree add x' > /tmp/wt-bfe569ca.sh; bash -xn /tmp/wt-bfe569ca.sh"
        ),
        "worktree-add CONTROL: `bash -xn` on a written script naming the phrase (#bfe569ca)",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' '# per-worktree cache' 'git worktree add x' > /tmp/wt-bfe569ca.sh; bash -o noexec /tmp/wt-bfe569ca.sh"
        ),
        "worktree-add CONTROL: `bash -o noexec` on a written script naming the phrase (#bfe569ca)",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' '# per-worktree cache' 'git worktree add x' > /tmp/wt-bfe569ca.sh; bash --norc -n /tmp/wt-bfe569ca.sh"
        ),
        "worktree-add CONTROL: `bash --norc -n` on a written script naming the phrase (#bfe569ca)",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' '# per-worktree cache' 'git worktree add x' > /tmp/wt-bfe569ca.sh; sh -n /tmp/wt-bfe569ca.sh"
        ),
        "worktree-add CONTROL: `sh -n` on a written script naming the phrase (#bfe569ca)",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' '# per-worktree cache' 'git worktree add x' > /tmp/wt-bfe569ca.sh; bash /tmp/wt-bfe569ca.sh"
        ),
        "worktree-add: `bash` on a written script naming the phrase (#bfe569ca)",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' '# per-worktree cache' 'git worktree add x' > /tmp/wt-bfe569ca.sh; bash -x /tmp/wt-bfe569ca.sh"
        ),
        "worktree-add: `bash -x` on a written script naming the phrase (#bfe569ca)",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' '# per-worktree cache' 'git worktree add x' > /tmp/wt-bfe569ca.sh; bash +n /tmp/wt-bfe569ca.sh"
        ),
        "worktree-add: `bash +n` on a written script naming the phrase (#bfe569ca)",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' '# per-worktree cache' 'git worktree add x' > /tmp/wt-bfe569ca.sh; bash -o errexit /tmp/wt-bfe569ca.sh"
        ),
        "worktree-add: `bash -o errexit` on a written script naming the phrase (#bfe569ca)",
    ),
    # The last setting wins (`+n`, `+o noexec` turn it off again) and `-i` does not undo it for a script operand, each measured on bash 5.3.9 (review 02425af7.1).
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' '# per-worktree cache' 'git worktree add x' > /tmp/wt-bfe569ca.sh; bash -in /tmp/wt-bfe569ca.sh"
        ),
        "worktree-add CONTROL: `bash -in` on a written script naming the phrase (#bfe569ca)",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' '# per-worktree cache' 'git worktree add x' > /tmp/wt-bfe569ca.sh; bash -i -o noexec /tmp/wt-bfe569ca.sh"
        ),
        "worktree-add CONTROL: `bash -i -o noexec` on a written script naming the phrase (#bfe569ca)",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' '# per-worktree cache' 'git worktree add x' > /tmp/wt-bfe569ca.sh; bash -n +n /tmp/wt-bfe569ca.sh"
        ),
        "worktree-add: `bash -n +n` on a written script naming the phrase (#bfe569ca)",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "printf '%s\\n' '# per-worktree cache' 'git worktree add x' > /tmp/wt-bfe569ca.sh; bash -o noexec +o noexec /tmp/wt-bfe569ca.sh"
        ),
        "worktree-add: `bash -o noexec +o noexec` on a written script naming the phrase (#bfe569ca)",
    ),
    # block_user_only_command and its shell twin (operator ruling 2026-10-09, #18c7e53c): no slash command or skill is user-only, except a file on the operator's exception list.
    case(
        "check 2 guards/block_user_only_command.py",
        tool_json(
            "Write",
            ".claude/commands/zz-probe.md",
            "content",
            "---\ndescription: x\ndisable-model-invocation: true\n---\n",
        ),
        "user-only-command: a Write that adds the key",
    ),
    case(
        "check 2 guards/block_user_only_command.py",
        tool_json("Write", ".ci/config/model-invocation-exceptions.json", "content", "{}"),
        "user-only-command: a Write of the exception list",
    ),
    case(
        "check 0 guards/block_user_only_command.py",
        tool_json(
            "Write",
            ".claude/commands/zz-probe.md",
            "content",
            "---\ndescription: x\n---\n\nNever set `disable-model-invocation: true`.\n",
        ),
        "user-only-command CONTROL: a body that only mentions the key",
    ),
    case(
        "check 0 guards/block_user_only_command.py",
        tool_json(
            "Write", "docs/zz-probe.md", "content", "---\ndisable-model-invocation: true\n---\n"
        ),
        "user-only-command CONTROL: a file outside the command directories",
    ),
    case(
        "check 2 guards/block_user_only_command_shell_write.py",
        bash_json("echo 'disable-model-invocation: true' >> .claude/commands/zz-probe.md"),
        "user-only-command-shell-write: an append of the key",
    ),
    case(
        "check 2 guards/block_user_only_command_shell_write.py",
        bash_json("echo '{}' > .ci/config/model-invocation-exceptions.json"),
        "user-only-command-shell-write: a redirect into the exception list",
    ),
    case(
        "check 0 guards/block_user_only_command_shell_write.py",
        bash_json("sed -i '/^disable-model-invocation:/d' .claude/commands/zz-probe.md"),
        "user-only-command-shell-write CONTROL: sed -i deleting the key line",
    ),
    case(
        "check 0 guards/block_user_only_command_shell_write.py",
        bash_json("echo 'disable-model-invocation: true is banned'"),
        "user-only-command-shell-write CONTROL: echo to the terminal",
    ),
    # Review cac47d16.1: the target-directory option names where a copy lands. The listed command carries the key, so a copy of it anywhere else is refused; each was allowed (rc 0) before.
    case(
        "check 2 guards/block_user_only_command_shell_write.py",
        bash_json("cp -t .claude/skills .claude/commands/handoff.md"),
        "user-only-command-shell-write: cp -t copies a flagged command into the skills directory",
    ),
    case(
        "check 2 guards/block_user_only_command_shell_write.py",
        bash_json("cp .claude/commands/handoff.md .claude/skills/ -S .bak"),
        "user-only-command-shell-write: a value option written after the destination",
    ),
    case(
        "check 0 guards/block_user_only_command_shell_write.py",
        bash_json("cp -t /tmp .claude/commands/handoff.md"),
        "user-only-command-shell-write CONTROL: cp -t copies a command OUT",
    ),
    # #c4542b69: a script run BY PATH is read like a heredoc; the refusals need scratch scripts and live in test-block_user_only_command.py, and so does the TRACKED-and-unchanged control, in a fixture git repo (review b922f15c.3: the only tracked script in this tree that the guard would refuse if read is its own harness, which is edited whenever the guard is, and an edited tracked script is read). This pins the other allow path: a script that cannot be read, which fails open.
    case(
        "check 0 guards/block_user_only_command_shell_write.py",
        bash_json("python3 /nonexistent/zz-commands-writer.py"),
        "user-only-command-shell-write CONTROL: a script that cannot be read fails open",
    ),
    # A python program is judged by where it WRITES, not by the paths it names (coordinator finding 2026-10-11): the first two controls were refused as "a python3 program writing the exception list".
    case(
        "check 0 guards/block_user_only_command_shell_write.py",
        bash_json(
            "python3 - <<'EOF'\nimport json\np = '.ci/config/model-invocation-exceptions.json'\nprint(len(json.load(open(p))['exceptions']))\nEOF"
        ),
        "user-only-command-shell-write CONTROL: a heredoc that only reads the exception list",
    ),
    case(
        "check 0 guards/block_user_only_command_shell_write.py",
        bash_json(
            "python3 - <<'EOF'\nimport pathlib\nprint('.ci/config/model-invocation-exceptions.json')\npathlib.Path('/tmp/out.txt').write_text('x')\nEOF"
        ),
        "user-only-command-shell-write CONTROL: a heredoc naming the list and writing elsewhere",
    ),
    case(
        "check 2 guards/block_user_only_command_shell_write.py",
        bash_json(
            "python3 - <<'EOF'\np = '.ci/config/model-invocation-exceptions.json'\nopen(p, 'w').write('{}')\nEOF"
        ),
        "user-only-command-shell-write: a heredoc opening the exception list for write",
    ),
    case(
        "check 2 guards/block_user_only_command_shell_write.py",
        bash_json(
            "python3 - <<'EOF'\nimport pathlib\npathlib.Path('.ci/config').joinpath('model-invocation-exceptions.json').write_text('{}')\nEOF"
        ),
        "user-only-command-shell-write: a heredoc writing the list through Path",
    ),
    # #5077391c: the fed words under `-t` are SOURCES. The deny row was allowed (the commands directory read as the source) and both controls refused (a fed word read as the destination).
    case(
        "check 2 guards/block_user_only_command_shell_write.py",
        bash_json("echo .claude/commands/handoff.md | xargs cp -t .claude/skills/demo"),
        "user-only-command-shell-write: xargs feeds a flagged command to cp -t a skill",
    ),
    case(
        "check 0 guards/block_user_only_command_shell_write.py",
        bash_json("echo .claude/commands/handoff.md | xargs cp -t /tmp"),
        "user-only-command-shell-write CONTROL: xargs feeds a flagged command to cp -t another directory",
    ),
    case(
        "check 0 guards/block_user_only_command_shell_write.py",
        bash_json("echo .ci/config/model-invocation-exceptions.json | xargs cp -t /tmp"),
        "user-only-command-shell-write CONTROL: xargs feeds the exception list to cp -t another directory",
    ),
    case(
        "check 2 guards/block_user_only_command_shell_write.py",
        bash_json("echo /tmp/x.json .ci/config/model-invocation-exceptions.json | xargs cp"),
        "user-only-command-shell-write: xargs feeds cp the exception list as its destination",
    ),
    # #e5b0540a: a relative fed glob is matched in the run's own directory (allowed before: only a name of its shape was read).
    case(
        "check 2 guards/block_user_only_command_shell_write.py",
        bash_json("cd .claude && echo command?/handoff.md | xargs cp -t skills/demo"),
        "user-only-command-shell-write: a relative fed glob names the flagged command copied into a skill",
    ),
    case(
        "check 2 guards/block_user_only_command_shell_write.py",
        bash_json("cd .ci && echo /tmp/x.json conf?g/model-invocation-exceptions.json | xargs cp"),
        "user-only-command-shell-write: a relative fed glob names the exception list as the destination",
    ),
    case(
        "check 0 guards/block_user_only_command_shell_write.py",
        bash_json("cd .claude && echo command?/handoff.md | xargs cp -t /tmp"),
        "user-only-command-shell-write CONTROL: the same glob copied out of the tree",
    ),
    # block_review_file_shell_write judges a Python program by its write TARGETS (2026-10-09): a review path that only flows into written content was refused live, and a target built from a review path through a name was allowed.
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('/tmp/scratchpad/fix833t.py')\n"
            "s = p.read_text()\ns = s.replace('X', 'agent/reviews/feat/%02d.md')\np.write_text(s)\nEOF"
        ),
        "review-file-shell-write CONTROL: a review path that is only written CONTENT",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 - <<'EOF'\nimport pathlib\nT = 'agent/reviews/feat/%02d.md'\n"
            "p = pathlib.Path(T % 1)\np.write_text('x')\nEOF"
        ),
        "review-file-shell-write: a write whose target is built from a review path",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 - <<'EOF'\nimport pathlib\nroot = pathlib.Path('agent/reviews')\n"
            "(root / 'b' / 'x.md').write_text('x')\nEOF"
        ),
        "review-file-shell-write: a write under a name bound to the directory itself",
    ),
    # Review findings e30f1ad1.1-.2 on block_review_file_shell_write: pathlib's `.open` takes its mode FIRST and `os.open` takes flags, and a command a program hands to a shell is a command. Each deny row was allowed on the base (rc 0).
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 -c \"import pathlib; pathlib.Path('agent/reviews/x.md').open('w').write('x')\""
        ),
        "review-file-shell-write: Path.open with its mode as the first argument (e30f1ad1.1)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 -c \"import os; os.open('agent/reviews/x.md', os.O_WRONLY | os.O_CREAT)\""
        ),
        "review-file-shell-write: os.open with write flags (e30f1ad1.1)",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 -c \"import pathlib; print(pathlib.Path('agent/reviews/x.md').open().read())\""
        ),
        "review-file-shell-write CONTROL: Path.open with no mode reads (e30f1ad1.1)",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("python3 -c \"import os; os.open('agent/reviews/x.md', os.O_RDONLY)\""),
        "review-file-shell-write CONTROL: os.open read-only (e30f1ad1.1)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("python3 -c \"import os; os.system('echo x > agent/reviews/a.md')\""),
        "review-file-shell-write: a redirect inside os.system (e30f1ad1.2)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 -c \"import subprocess as sp; sp.call(['sh', '-c', 'echo x > agent/reviews/a.md'])\""
        ),
        "review-file-shell-write: an sh -c argv through an aliased subprocess (e30f1ad1.2)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("python3 -c \"import os; p = 'agent/reviews/a.md'; os.system(f'echo x > {p}')\""),
        "review-file-shell-write: an f-string shell command through a bound review path (e30f1ad1.2)",
    ),
    # Review 071b7987.1 and its siblings: a review path glued after a value the ast cannot spell, in every way Python builds a string.
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 -c \"import os; root = os.environ['R']; os.system(f'echo x > {root}agent/reviews/a.md')\""
        ),
        "review-file-shell-write: an f-string review path after an unbound prefix (071b7987.1)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 -c \"import os; os.system('echo x > %sagent/reviews/a.md' % os.environ['R'])\""
        ),
        "review-file-shell-write: a %-template review path after an unbound prefix (071b7987.1)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 -c \"import os; os.system('echo x > {}agent/reviews/a.md'.format(os.environ['R']))\""
        ),
        "review-file-shell-write: a str.format review path after an unbound prefix (071b7987.1)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 -c \"import os; os.system('echo x > ' + os.path.join(os.environ['R'], 'agent/reviews/a.md'))\""
        ),
        "review-file-shell-write: an os.path.join review path (071b7987.1)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 -c \"import os; from pathlib import Path; os.system('echo x > ' + str(Path(os.environ['R']) / 'agent/reviews/a.md'))\""
        ),
        "review-file-shell-write: a Path / review path through str() (071b7987.1)",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 -c \"import os; os.system('echo %s > /tmp/out' % 'agent/reviews/a.md')\""
        ),
        "review-file-shell-write CONTROL: a %-template that only echoes a review path into another file (071b7987.1)",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 -c \"import os; os.system('cat {}agent/reviews/a.md > /tmp/out'.format(os.environ['R']))\""
        ),
        "review-file-shell-write CONTROL: a str.format review path that is only read (071b7987.1)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("perl -e 'system(\"echo x > agent/reviews/a.md\")'"),
        "review-file-shell-write: a redirect inside perl system, read by the line fallback (e30f1ad1.2)",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 -c \"import os; os.system('grep -rn high agent/reviews/ > /tmp/hits')\""
        ),
        "review-file-shell-write CONTROL: a shell command that reads the directory and writes elsewhere (e30f1ad1.2)",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 -c \"open('/tmp/x', 'w').write('os.system(\\\"echo > agent/reviews/a\\\")')\""
        ),
        "review-file-shell-write CONTROL: a shell command that is only written CONTENT (e30f1ad1.2)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(_handed_down("echo x > agent/reviews/a.md", 6)),
        "review-file-shell-write: a write handed down six programs deep is refused, not dropped at the depth cap",
    ),
    # #5077391c: xargs appends its feed to cp's own words, so under `-t` a fed word is a SOURCE. The control was refused while every fed word read as a destination.
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("echo agent/reviews/1008-1/x.md | xargs cp -t /tmp"),
        "review-file-shell-write CONTROL: xargs feeds a review file to cp -t another directory",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("echo /tmp/a.md | xargs cp -t agent/reviews/1008-1"),
        "review-file-shell-write: xargs feeds a source to cp -t the review directory",
    ),
    # The fed word as the file an in-place editor, tee or truncate writes: appended, or put where the marker stands. Each refusal was allowed before, since the editor's own words named no review file.
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("echo agent/reviews/1008-1/x.md | xargs sed -i s/a/b/"),
        "review-file-shell-write: xargs feeds a review file to sed -i",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("echo agent/reviews/1008-1/x.md | xargs -rI{} sed -i s/a/b/ {}"),
        "review-file-shell-write: xargs puts a review file at its marker for sed -i",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("echo agent/reviews/1008-1/x.md | xargs tee"),
        "review-file-shell-write: xargs feeds a review file to tee",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("echo agent/reviews/1008-1 | xargs -I{} truncate -s 0 {}/x.md"),
        "review-file-shell-write: xargs puts a review directory at its marker for truncate",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("echo agent/reviews/1008-1 | xargs -I X truncate -s 0 X/x.md"),
        "review-file-shell-write: xargs puts a review directory at a marker of its own for truncate",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("echo agent/reviews/1008-1/x.md | xargs cat"),
        "review-file-shell-write CONTROL: xargs feeds a review file to a reader",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("echo /tmp/x.md | xargs sed -i s/a/b/"),
        "review-file-shell-write CONTROL: xargs feeds another file to sed -i",
    ),
    # #e5b0540a: a relative fed glob is matched in the run's own directory, so `revi*s/...` from agent/ is the review directory (allowed before: only a name of its shape was read).
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("cd agent && echo revi*s/1008-1/026b*.md | xargs cp /tmp/x.md; ls reviews"),
        "review-file-shell-write: a relative fed glob from agent/ lands in the review directory",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("cd agent && echo plan*/QUEUE.md | xargs cp /tmp/x.md; ls reviews"),
        "review-file-shell-write CONTROL: a relative fed glob elsewhere in agent/",
    ),
    # Worklist item ff3ab826: a tool's own output option is a write, and a command `shellscan.output_landings` does not list as a reader is read as writing any word it names. Every deny row was allowed (rc 0) on the base; the controls name the same paths through a reader, or the same option elsewhere.
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("sort -o agent/reviews/1231-9/a.md /tmp/a"),
        "review-file-shell-write: sort -o names a review file",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("sort --output=agent/reviews/1231-9/a.md /tmp/a"),
        "review-file-shell-write: sort --output= names a review file",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("sort -uoagent/reviews/1231-9/a.md /tmp/a"),
        "review-file-shell-write: sort carries the review file in a short bundle",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("sort --out agent/reviews/1231-9/a.md /tmp/a"),
        "review-file-shell-write: sort --out is a unique prefix of --output",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("sort /tmp/a -o agent/reviews/1231-9/a.md"),
        "review-file-shell-write: sort -o after the operands",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("curl -o agent/reviews/1231-9/a.md https://e.x/a"),
        "review-file-shell-write: curl -o names a review file",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("wget -O agent/reviews/1231-9/a.md https://e.x/a"),
        "review-file-shell-write: wget -O names a review file",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("tar -cf agent/reviews/1231-9/a.md /tmp/a"),
        "review-file-shell-write: tar -cf names a review file",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("tar -xf /tmp/a.tar -C agent/reviews/1231-9"),
        "review-file-shell-write: tar -C unpacks into the review directory",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("openssl enc -in /tmp/a -out agent/reviews/1231-9/a.md"),
        "review-file-shell-write: openssl -out names a review file",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("git diff --output=agent/reviews/1231-9/a.md HEAD~1"),
        "review-file-shell-write: git diff --output= names a review file",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("git format-patch -o agent/reviews/1231-9 -1"),
        "review-file-shell-write: git format-patch -o names the review directory",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("pandoc /tmp/a.md -o agent/reviews/1231-9/a.md"),
        "review-file-shell-write: pandoc -o names a review file",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("echo agent/reviews/1231-9/a.md | xargs sort /tmp/a -o"),
        "review-file-shell-write: xargs appends the review file as the value of sort -o",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("echo agent/reviews/1231-9/a.md | xargs -I{} sort --output={} /tmp/a"),
        "review-file-shell-write: xargs -I puts the review file in sort --output=",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json(r"find agent/reviews -name '*.md' -exec sort -o {} /tmp/a \;"),
        "review-file-shell-write: a launched sort -o onto the files find names",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("find /tmp -name a -fprint agent/reviews/1231-9/a.md"),
        "review-file-shell-write: find -fprint names a review file",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("sed -n 'w agent/reviews/1231-9/a.md' /tmp/a"),
        "review-file-shell-write: a sed w command names a review file",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("awk '{print > \"agent/reviews/1231-9/a.md\"}' /tmp/a"),
        "review-file-shell-write: an awk program redirects into a review file",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("uniq /tmp/a agent/reviews/1231-9/a.md"),
        "review-file-shell-write: uniq's second operand is its output",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("touch agent/reviews/1231-9/a.md"),
        "review-file-shell-write: touch names a review file",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("prettier --write agent/reviews/1231-9/a.md"),
        "review-file-shell-write: prettier --write names a review file",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("sort agent/reviews/1231-9/a.md"),
        "review-file-shell-write CONTROL: sort reads a review file",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("sort -o /tmp/out agent/reviews/1231-9/a.md"),
        "review-file-shell-write CONTROL: sort -o elsewhere reads a review file",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("wc -l agent/reviews/1231-9/a.md"),
        "review-file-shell-write CONTROL: wc reads a review file",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("head -5 agent/reviews/1231-9/a.md"),
        "review-file-shell-write CONTROL: head reads a review file",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("git log --oneline -- agent/reviews/"),
        "review-file-shell-write CONTROL: git log over the review directory",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("git diff --stat agent/reviews/"),
        "review-file-shell-write CONTROL: git diff --stat over the review directory",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("git diff --output=/tmp/d -- agent/reviews/"),
        "review-file-shell-write CONTROL: git diff --output= elsewhere",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("diff agent/reviews/1231-9/a.md /tmp/b"),
        "review-file-shell-write CONTROL: diff reads a review file",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("jq . agent/reviews/1231-9/clean.jsonl"),
        "review-file-shell-write CONTROL: jq reads the clean ledger",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("curl -o /tmp/out https://e.x/agent/reviews/a"),
        "review-file-shell-write CONTROL: curl -o elsewhere, a URL naming the directory",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("echo agent/reviews/1231-9/a.md | xargs sort"),
        "review-file-shell-write CONTROL: xargs feeds a review file to sort as its input",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("echo sort -o agent/reviews/1231-9/a.md /tmp/a"),
        "review-file-shell-write CONTROL: prose naming a sort -o",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("sed 's|agent/reviews/||' /tmp/list"),
        "review-file-shell-write CONTROL: a sed script that names the directory and writes nothing",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("rm agent/reviews/1231-9/a.md"),
        "review-file-shell-write CONTROL: rm keeps the verdict it had",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("git checkout -- agent/reviews/1231-9/a.md"),
        "review-file-shell-write CONTROL: git checkout keeps the verdict it had",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("grep -n Resolution agent/reviews/1008-1/*.md"),
        "review-file-shell-write CONTROL: grep -n over the records",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("sed -n 1,20p agent/reviews/1231-9/a.md"),
        "review-file-shell-write CONTROL: sed -n prints a range of a review file",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("git add -- agent/reviews/1008-1/"),
        "review-file-shell-write CONTROL: git add of the review directory",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("git commit -F /tmp/m -- agent/reviews/1008-1/"),
        "review-file-shell-write CONTROL: git commit of the review directory",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("ls agent/reviews/1008-1/"),
        "review-file-shell-write CONTROL: ls of the review directory",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("tail -1 agent/reviews/1231-9/clean.jsonl"),
        "review-file-shell-write CONTROL: tail of the clean ledger",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json(
            "python3 .claude/hooks/stop/worklist.py --review-mark d778be9d ab12cd34.1 not-a-bug 'x agent/reviews/1008-1/x.md:3'"
        ),
        "review-file-shell-write CONTROL: the mark verb with evidence naming a record",
    ),
    # Review 906a4d56.1 and .2: gawk's -o, -p and -d take a value only attached, and -W takes a separate word, so the option parse put the program in the wrong word and its redirect was never read. Every deny row was allowed (rc 0) on the base.
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("gawk -p '{print > \"agent/reviews/1231-9/a.md\"}' /tmp/a"),
        "review-file-shell-write: gawk -p takes no separate value, the next word is the program (906a4d56.1)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("gawk -d '{print > \"agent/reviews/1231-9/a.md\"}' /tmp/a"),
        "review-file-shell-write: gawk -d takes no separate value, the next word is the program (906a4d56.1)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("gawk -o '{print > \"agent/reviews/1231-9/a.md\"}' /tmp/a"),
        "review-file-shell-write: gawk -o with a program that redirects into a review file (906a4d56.1)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("gawk --profile '{print > \"agent/reviews/1231-9/a.md\"}' /tmp/a"),
        "review-file-shell-write: gawk --profile takes its file only after = (906a4d56.1 sweep)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("gawk -W lint '{print > \"agent/reviews/1231-9/a.md\"}' /tmp/a"),
        "review-file-shell-write: gawk -W takes a separate word, the word after it is the program (906a4d56.2)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("mawk -W interactive '{print > \"agent/reviews/1231-9/a.md\"}' /tmp/a"),
        "review-file-shell-write: mawk -W takes a separate word (906a4d56.2)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("gawk -W dump-variables=agent/reviews/1231-9/a.md '{print}' /tmp/a"),
        "review-file-shell-write: gawk -W hands over a long write option (906a4d56.2 sweep)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("xxd -ps /tmp/in agent/reviews/1231-9/a.md"),
        "review-file-shell-write: xxd -ps is one flag, the second operand is its output (906a4d56 sweep)",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("awk '{print > (FILENAME \".bak\")}' agent/reviews/1231-9/a.md"),
        "review-file-shell-write: an awk program writes beside its input through FILENAME (906a4d56 sweep)",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("gawk '{print $1}' agent/reviews/1231-9/a.md"),
        "review-file-shell-write CONTROL: gawk reads a review file",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("gawk -W lint '{print $1}' agent/reviews/1231-9/a.md"),
        "review-file-shell-write CONTROL: gawk -W lint reads a review file",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("gawk -d '{print $1}' agent/reviews/1231-9/a.md"),
        "review-file-shell-write CONTROL: gawk -d reads a review file",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("awk -F'|' '{print $2}' agent/reviews/1231-9/a.md"),
        "review-file-shell-write CONTROL: awk splitting on a pipe reads a review file",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("xxd -ps agent/reviews/1231-9/a.md"),
        "review-file-shell-write CONTROL: xxd -ps reads a review file",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json(
            "cd agent/reviews/1008-1 && awk '/^### /{p=0} /^### (0b8baf43.1|599bfb94.1)/{p=1} p' x.md"
        ),
        "review-file-shell-write CONTROL: awk with an alternation and its own assignments, run inside the directory",
    ),
    # Review 660ec7a0.1: an awk program that redirects a print names its target without a literal, so every operand is a landing. The three refusals were allowed at cc5c597a8.
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("awk 'BEGIN{print \"x\" > ARGV[1]}' agent/reviews/1008-1/x.md"),
        "review-file-shell-write: awk prints into the operand it was handed",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("awk '{f=ARGV[1]; print \"x\" > f}' agent/reviews/1008-1/x.md"),
        "review-file-shell-write: awk prints into a variable built from its operand",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("awk '{print > FILENAME}' agent/reviews/1008-1/x.md"),
        "review-file-shell-write: awk prints into the file it reads",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("awk 'BEGIN{print \"a;b\" > ARGV[1]}' agent/reviews/1008-1/x.md"),
        "review-file-shell-write: awk redirects after a literal that holds a semicolon",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json('awk \'BEGIN{print "x" > "" ARGV[1]}\' agent/reviews/1008-1/x.md'),
        "review-file-shell-write: awk redirects into a target that starts with a literal",
    ),
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("awk '$3 > 5 {print}' agent/reviews/1008-1/x.md"),
        "review-file-shell-write: a printing awk program that holds a > is refused, comparison or not",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("awk '$3 > 5' agent/reviews/1008-1/x.md"),
        "review-file-shell-write CONTROL: an awk program that prints nothing redirects nothing",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("awk '/^### (a|b)/{p=1} p' agent/reviews/1008-1/x.md"),
        "review-file-shell-write CONTROL: a pattern's alternation is not a pipe",
    ),
    # Review fd4eda1a.1: the rule does not follow where a print goes, so a program that redirects into a literal ELSEWHERE is refused while it reads a review file. The control is the same program over another file.
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("awk '{print > \"x\"}' agent/reviews/1008-1/x.md"),
        "review-file-shell-write: an awk that redirects into a literal elsewhere while reading a review file (fd4eda1a.1)",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("awk '{print > \"x\"}' /tmp/agent-reviews-list.txt"),
        "review-file-shell-write CONTROL: the same redirecting awk program over a file that is not a review file",
    ),
    # Review fd4eda1a.3: the rule is lexical. This program prints nothing; the letters `print` beside a `|` inside its regex read as a program that may redirect, and the refusal is a stated over-read in the direction that fails closed.
    case(
        "check 2 guards/block_review_file_shell_write.py",
        bash_json("awk '/print|x/' agent/reviews/1008-1/x.md"),
        "review-file-shell-write: over-read, an awk regex that spells print beside a pipe is refused (fd4eda1a.3)",
    ),
    case(
        "check 0 guards/block_review_file_shell_write.py",
        bash_json("awk '/prin|x/' agent/reviews/1008-1/x.md"),
        "review-file-shell-write CONTROL: an awk regex with an alternation and no print reads a review file",
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
    # NPX CANNOT RESOLVE A NON-NPM BINARY. Measured 2026-08-28: `npx --yes ruff format ...` failed with an npm resolution error even though the real ruff binary was on PATH the whole time; the session read that as "no ruff resolves" and hand-patched two files instead. This fires on shape alone.
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
    # BARE TOOL INVOCATIONS. The NEEDS table above only matches a GATE KEY in the command; running the tool directly was invisible to it.
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
        bash_json(("git push --mirror " + GH_ORIGIN + "/") + GH_REPO + ".git"),
        "force-push: --mirror is a force of every ref",
    ),
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json("cd private/account && git push --mirror origin"),
        "force-push: --mirror behind a cd is still caught",
    ),
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json("git push origin +refs/heads/main"),
        "force-push: a leading + on a refspec forces that ref",
    ),
    # THE SHORTHAND FORMS, which the +refs/ case above did NOT cover. A refspec does not have to be refs-qualified to force, and the first fix for this guard matched only the long form: `+main:main` and `+HEAD:main` both slipped past a guard whose commit message said the hole was closed. Caught in review on PR #571. The case above tested the REGEX; these test the THREAT.
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
    # THE WRAPPER BYPASS, review-found on PR #579. Every sibling guard touched in that same PR (block-cli-bundle.sh, block-protected-files.sh, etc.) routes through lib/command-scan.sh's hook_scan_target, which unwraps eval/sh -c payloads; this guard matched $CMD directly, so wrapping the forbidden push left the push text preceded by a quote character instead of a line start or
    # accepted separator, and the command-position anchor never fired. Same class as the worktree-add wrapper case above, on the one guard this file's own comment calls "the whole security story".
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
    # #18c7e53c A-1 and C-3 (operator ruling 2026-10-09). The checked-out-branch and dirty-tree directions depend on the checkout, so they live in each guard's EDGE_CASES against fixture worlds; the rows here answer the same in any checkout.
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json("git push --prune origin"),
        "force-push #18c7e53c: --prune deletes remote branches no line names",
    ),
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json('git push origin --delete "$B"'),
        "force-push #18c7e53c: a deleted branch name the walk cannot read",
    ),
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json("git -C private/renet push --force-with-lease --delete origin 0101-9"),
        "force-push #18c7e53c: --delete is never part of the lease form",
    ),
    case(
        "check 0 guards/block_git_force_push.py",
        bash_json("git push origin --delete 0101-9"),
        "force-push #18c7e53c: deleting a branch no checkout names (pr-merge step 7)",
    ),
    case(
        "check 0 guards/block_git_force_push.py",
        bash_json("git push origin :"),
        "force-push #18c7e53c: the matching refspec deletes nothing",
    ),
    case(
        "check 2 guards/block_rebase_over_foreign_dirt.py",
        bash_json("git --work-tree=. rebase origin/main"),
        "rebase-dirt #18c7e53c: --work-tree hides the tree the rebase touches",
    ),
    case(
        "check 2 guards/block_rebase_over_foreign_dirt.py",
        bash_json("GIT_DIR=.git git rebase origin/main"),
        "rebase-dirt #18c7e53c: GIT_DIR on the command line is refused, not guessed",
    ),
    case(
        "check 2 guards/block_rebase_over_foreign_dirt.py",
        bash_json("git --git-dir=.git merge origin/main"),
        "rebase-dirt #18c7e53c: --git-dir on a merge",
    ),
    case(
        "check 0 guards/block_rebase_over_foreign_dirt.py",
        bash_json("git rebase --continue"),
        "rebase-dirt #18c7e53c: --continue starts nothing",
    ),
    case(
        "check 0 guards/block_rebase_over_foreign_dirt.py",
        bash_json("git rebase --abort"),
        "rebase-dirt #18c7e53c: --abort starts nothing",
    ),
    # Worklist #dbbed0b6: `--skip` drops the commit being replayed, so it is refused on any tree; outside this checkout it is not this guard's business.
    case(
        "check 2 guards/block_rebase_over_foreign_dirt.py",
        bash_json("git rebase --skip"),
        "rebase-dirt #dbbed0b6: --skip drops the replayed commit",
    ),
    case(
        "check 0 guards/block_rebase_over_foreign_dirt.py",
        bash_json("git -C /tmp rebase --skip"),
        "rebase-dirt #dbbed0b6 CONTROL: --skip outside this checkout",
    ),
    case(
        "check 0 guards/block_rebase_over_foreign_dirt.py",
        bash_json("git pull --ff-only"),
        "rebase-dirt #18c7e53c: a fast-forward pull (pr-merge step 7)",
    ),
    case(
        "check 0 guards/block_rebase_over_foreign_dirt.py",
        bash_json("git merge --ff-only origin/main"),
        "rebase-dirt #18c7e53c: a fast-forward merge",
    ),
    case(
        "check 0 guards/block_rebase_over_foreign_dirt.py",
        bash_json("echo 'git rebase origin/main later'"),
        "rebase-dirt #18c7e53c: prose naming a rebase",
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
    # THE WRAPPER FORMS. `./run.sh worktree create` runs `git worktree add -b` inside `rediacc_ci.dev.worktree.cmd_create`, so it is the same decision -- but the text this hook sees never contains "git worktree add", and the literal block matched nothing. It now also starts a devbox, so the bypass costs an image pull and a port block.
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
        bash_json("bash run.sh worktree create"),
        "worktree-add: interpreter prefix puts bash in command position, not the script",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("/home/x/console/run.sh worktree create"),
        "worktree-add: run.sh by absolute path",
    ),
    # THE PYTHON PORT, reached without run.sh. scripts/dev/worktree.sh became `.ci/rediacc_ci/dev/worktree.py` and was deleted, and chain-head.sh allowed each spelling below with rc 0 on 2026-10-09 because neither arm named it.
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("PYTHONPATH=.ci python3 -m rediacc_ci worktree create x"),
        "worktree-add: the package entry run.sh execs",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("PYTHONPATH=.ci python3 -m rediacc_ci.dev.worktree create x"),
        "worktree-add: the port's module",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("python3 .ci/rediacc_ci/dev/worktree.py create x"),
        "worktree-add: the port by path",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("PYTHONPATH=.ci python3 .ci/rediacc_ci worktree create x"),
        "worktree-add: the package directory by path",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("PYTHONPATH=.ci python3 -m rediacc_ci.dev.worktree list"),
        "worktree-add: the port's list is not create",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("PYTHONPATH=.ci python3 -m rediacc_ci worktree list"),
        "worktree-add: the package's worktree list is not create",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("grep -n create .ci/rediacc_ci/dev/worktree.py"),
        "worktree-add: reading the port is not running it",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("echo the docs say never to run rediacc_ci.dev.worktree create here"),
        "worktree-add: an unquoted sentence naming the port is not running it",
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
    # THE INTERPRETER FORMS. Every one ran with rc 0 through chain-head.sh on 2026-10-09: a program text handed to python (-c, a heredoc, a here-string, a pipe), node, perl or ruby is one opaque argument to the shell walk, so the three arms above never saw the command inside it.
    case(
        "check_out 2 guards/block_worktree_add.py",
        bash_json(
            "python3 -c \"import subprocess; subprocess.run(['git','worktree','add','/tmp/x'])\""
        ),
        "worktree-add: python -c with a git argv list",
        "program text",
    ),
    case(
        "check_out 2 guards/block_worktree_add.py",
        bash_json("python3 -c 'from rediacc_ci.dev import worktree; worktree.main([\"create\"])'"),
        "worktree-add: python -c calling the port's main with create",
        "worktree port",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "PYTHONPATH=.ci python3 -c 'from rediacc_ci.dev.worktree import cmd_create; cmd_create([\"x\"])'"
        ),
        "worktree-add: python -c calling cmd_create",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            'python3 -c \'from rediacc_ci.__main__ import main; main(["worktree", "create", "x"])\''
        ),
        "worktree-add: python -c through the package entry",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("python3 -c 'import os; os.system(\"git worktree add /tmp/x\")'"),
        "worktree-add: python -c with a shell string",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "python3 -c \"import subprocess; subprocess.run('cd /r && git worktree add /tmp/x', shell=True)\""
        ),
        "worktree-add: python -c with a compound shell string",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "python3 -c \"import subprocess; subprocess.run(['python3','-m','rediacc_ci.dev.worktree','create','x'])\""
        ),
        "worktree-add: python -c spawning the port",
    ),
    case(
        "check_out 2 guards/block_worktree_add.py",
        bash_json(
            "python3 - <<'EOF'\nimport subprocess\nsubprocess.run(['git', 'worktree', 'add', '/tmp/x'])\nEOF"
        ),
        "worktree-add: python reading a heredoc",
        "program text",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("python3 <<'EOF'\nimport os\nos.system('git worktree add /tmp/x')\nEOF"),
        "worktree-add: python with no target reads the heredoc",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("python3 - <<< 'import os; os.system(\"git worktree add /tmp/x\")'"),
        "worktree-add: python reading a here-string",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("echo 'import os; os.system(\"git worktree add /tmp/x\")' | python3"),
        "worktree-add: python fed by echo through a pipe",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("timeout 30 python3 -c \"import os; os.system('git worktree add /tmp/x')\""),
        "worktree-add: python -c behind timeout",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "sh -c \"python3 - <<'EOF'\nimport os; os.system('git worktree add /tmp/x')\nEOF\""
        ),
        "worktree-add: a python heredoc inside sh -c",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            "x=$(python3 - <<'EOF'\nimport subprocess; subprocess.run(['git','worktree','add','/tmp/x'])\nEOF\n)"
        ),
        "worktree-add: a python heredoc inside a substitution",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json(
            'PYTHONPATH=.ci python3 -c \'from rediacc_ci.core import git; git.run("worktree", "add", "/tmp/x")\''
        ),
        "worktree-add: python -c handing a helper worktree add",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json('node -e \'require("child_process").execSync("git worktree add /tmp/x")\''),
        "worktree-add: node -e",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("perl -le 'print `git worktree add /tmp/x`'"),
        "worktree-add: perl backticks in a bundled -le",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("ruby -e 'system \"git worktree add /tmp/x\"'"),
        "worktree-add: ruby -e",
    ),
    case(
        "check 2 guards/block_worktree_add.py",
        bash_json("bash -c 'git worktree add /tmp/x'"),
        "worktree-add: bash -c (caught before the interpreter arm)",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json(
            "python3 -c \"import subprocess; print(subprocess.run(['git','worktree','list'],capture_output=True).stdout)\""
        ),
        "worktree-add: python -c listing worktrees is allowed",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("python3 -c 'from rediacc_ci.dev import worktree; worktree.main([\"list\"])'"),
        "worktree-add: python -c calling the port's list is allowed",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("python3 -c 'print(\"never run git worktree add here\")'"),
        "worktree-add: python printing a sentence naming it is allowed",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json(
            "python3 - <<'EOF'\nprint(open('.ci/rediacc_ci/dev/worktree.py').read().count('create'))\nEOF"
        ),
        "worktree-add: python reading the port's source is allowed",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json(
            "python3 -c 'from rediacc_ci.dev import worktree; print(worktree.cmd_create.__doc__)'"
        ),
        "worktree-add: python reading cmd_create's docstring is allowed",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json("perl -ne 'print if /git worktree add/' docs/x.md"),
        "worktree-add: perl grepping for the command is allowed",
    ),
    case(
        "check 0 guards/block_worktree_add.py",
        bash_json(
            "cat > n.md <<'EOF'\npython3 -c \"import os; os.system('git worktree add x')\"\nEOF"
        ),
        "worktree-add: a heredoc into a file naming a python -c is data",
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
    # block_pathspecless_git_commit.py -- the OTHER half of the blanket-add trap, and the half a correct `git add` does not protect against. `git commit` writes the INDEX, so a peer session's staged work rides the commit. Added 2026-09-06 after it happened TWICE in one session: fifteen policy renames landed without their readers, then an hour later, after the trap was written down
    # by the same session, 108 files landed where 33 were intended.
    case(
        "check 2 guards/block_pathspecless_git_commit.py",
        bash_json('git commit -m "x"'),
        "pathspecless-commit: -m with no pathspec",
    ),
    case(
        "check 2 guards/block_pathspecless_git_commit.py",
        bash_json("git commit"),
        "pathspecless-commit: the bare form",
    ),
    case(
        "check 2 guards/block_pathspecless_git_commit.py",
        bash_json('git commit -a -m "x"'),
        "pathspecless-commit: -a stages every modified tracked file",
    ),
    case(
        "check 2 guards/block_pathspecless_git_commit.py",
        bash_json('git commit -m "x" --'),
        "pathspecless-commit: a -- with nothing after it is the bare form in disguise",
    ),
    case(
        "check 0 guards/block_pathspecless_git_commit.py",
        bash_json("git commit -F msg.txt -- a/b.ts"),
        "pathspecless-commit: ALLOW a named pathspec",
    ),
    case(
        "check 0 guards/block_pathspecless_git_commit.py",
        bash_json("git commit -q -F - -- .ci/x.sh agent/y.md"),
        "pathspecless-commit: ALLOW several named paths",
    ),
    case(
        "check 0 guards/block_pathspecless_git_commit.py",
        bash_json("git commit --amend --no-edit"),
        "pathspecless-commit: ALLOW an amend, which chooses no new content",
    ),
    case(
        "check 0 guards/block_pathspecless_git_commit.py",
        bash_json("git add -- a.ts"),
        "pathspecless-commit: ALLOW a git add, which is a different guard's business",
    ),
    case(
        "check 0 guards/block_pathspecless_git_commit.py",
        bash_json("git init -q && git add -A && git commit -qm seed"),
        "pathspecless-commit: ALLOW a throwaway fixture repo, which every port agent must seal",
    ),
    case(
        "check 0 guards/block_pathspecless_git_commit.py",
        bash_json("cd /tmp/claude-1000/fx/r1; git add -A; git commit -qm seed"),
        "pathspecless-commit: ALLOW a commit inside /tmp, which is never this checkout",
    ),
    case(
        "check 0 guards/block_pathspecless_git_commit.py",
        bash_json("git -C /tmp/claude-1000/fx/r1 commit -qm seed"),
        "pathspecless-commit: ALLOW git -C into a scratch repo",
    ),
    case(
        "check 0 guards/block_nonstandard_branch_name.py",
        bash_json(
            "git init -q /tmp/claude-1000/fx/r1 && git -C /tmp/claude-1000/fx/r1 branch feat"
        ),
        "branch-name scope: ALLOW a repository outside this checkout (#5810a9f3)",
    ),
    case(
        "check 2 guards/block_nonstandard_branch_name.py",
        bash_json("git branch feat"),
        "branch-name scope CONTROL: the same command in the console is still refused",
    ),
    case(
        "check 0 guards/block_nonstandard_branch_name.py",
        bash_json(
            "git init -q /tmp/claude-1000/fx/nb && cd /tmp/claude-1000/fx/nb && git branch feat"
        ),
        "branch-name scope: ALLOW a repository outside this checkout (#5810a9f3), created by the same command",
    ),
    case(
        "check 0 guards/block_second_branch.py",
        bash_json(
            "git init -q /tmp/claude-1000/fx/nb && cd /tmp/claude-1000/fx/nb && git checkout -b feat"
        ),
        "second-branch scope: ALLOW a repository outside this checkout (#5810a9f3), created by the same command",
    ),
    case(
        "check 2 guards/block_second_branch.py",
        bash_json("git checkout -b feat"),
        "second-branch scope CONTROL: the same command in the console is still refused",
    ),
    case(
        "check 0 guards/block_untagged_commit.py",
        bash_json(
            "git init -q /tmp/claude-1000/fx/nb && cd /tmp/claude-1000/fx/nb && git commit -m x"
        ),
        "untagged-commit scope: ALLOW a repository outside this checkout (#5810a9f3), created by the same command",
    ),
    case(
        "check 2 guards/block_untagged_commit.py",
        bash_json("git commit -m x"),
        "untagged-commit scope CONTROL: the same command in the console is still refused",
    ),
    case(
        "check 0 guards/block_unlinked_commit_author.py",
        bash_json(
            'git init -q /tmp/claude-1000/fx/nb && cd /tmp/claude-1000/fx/nb && git commit --author="x <x@y.z>" -m x -- a'
        ),
        "commit-author scope: ALLOW a repository outside this checkout (#5810a9f3), created by the same command",
    ),
    case(
        "check 2 guards/block_unlinked_commit_author.py",
        bash_json('git commit --author="x <x@y.z>" -m x -- a'),
        "commit-author scope CONTROL: the same command in the console is still refused",
    ),
    case(
        "check 0 guards/block_git_amend.py",
        bash_json(
            "git init -q /tmp/claude-1000/fx/nb && cd /tmp/claude-1000/fx/nb && git commit --amend"
        ),
        "git-amend scope: ALLOW a repository outside this checkout (#5810a9f3), created by the same command",
    ),
    case(
        "check 2 guards/block_git_amend.py",
        bash_json("git commit --amend"),
        "git-amend scope CONTROL: the same command in the console is still refused",
    ),
    case(
        "check 0 guards/block_git_empty_commit.py",
        bash_json(
            "git init -q /tmp/claude-1000/fx/nb && cd /tmp/claude-1000/fx/nb && git commit --allow-empty -m x"
        ),
        "git-empty-commit scope: ALLOW a repository outside this checkout (#5810a9f3), created by the same command",
    ),
    case(
        "check 2 guards/block_git_empty_commit.py",
        bash_json("git commit --allow-empty -m x"),
        "git-empty-commit scope CONTROL: the same command in the console is still refused",
    ),
    case(
        "check 0 guards/block_git_hook_bypass.py",
        bash_json(
            "git init -q /tmp/claude-1000/fx/nb && cd /tmp/claude-1000/fx/nb && git commit --no-verify -m x"
        ),
        "git-hook-bypass scope: ALLOW a repository outside this checkout (#5810a9f3), created by the same command",
    ),
    case(
        "check 2 guards/block_git_hook_bypass.py",
        bash_json("git commit --no-verify -m x"),
        "git-hook-bypass scope CONTROL: the same command in the console is still refused",
    ),
    case(
        "check 0 guards/block_git_force_push.py",
        bash_json(
            "git init -q /tmp/claude-1000/fx/nb && cd /tmp/claude-1000/fx/nb && git push --force origin main"
        ),
        "git-force-push scope: ALLOW a repository outside this checkout (#5810a9f3), created by the same command",
    ),
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json("git push --force origin main"),
        "git-force-push scope CONTROL: the same command in the console is still refused",
    ),
    # A FAILED cd IS NOT FOREIGN (#5810a9f3 follow-up). After `cd <missing>;` git runs in THIS checkout, so a directory that neither exists nor is created by the same command must keep the guard judging the console. `;` and `||` are the shapes where the git command still runs.
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json("cd /nonexistent-zz9; git push --force origin main"),
        "git-force-push scope: a cd that cannot happen leaves git in the console, still refused",
    ),
    case(
        "check 2 guards/block_git_force_push.py",
        bash_json("cd /nonexistent-zz9 || true; git push --force origin main"),
        "git-force-push scope: a failed cd behind || is still refused",
    ),
    case(
        "check 2 guards/block_git_amend.py",
        bash_json("cd /nonexistent-zz9; git commit --amend --no-edit"),
        "git-amend scope: a cd that cannot happen leaves git in the console, still refused",
    ),
    case(
        "check 0 guards/block_push_to_protected_branch.py",
        bash_json(
            "git init -q /tmp/claude-1000/fx/nb && cd /tmp/claude-1000/fx/nb && git push origin main"
        ),
        "protected-branch scope: ALLOW a repository outside this checkout (#5810a9f3), created by the same command",
    ),
    case(
        "check 2 guards/block_push_to_protected_branch.py",
        bash_json("git push origin main"),
        "protected-branch scope CONTROL: the same command in the console is still refused",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json(
            "git init -q /tmp/claude-1000/fx/nb && cd /tmp/claude-1000/fx/nb && git checkout -- ."
        ),
        "destructive-git scope: ALLOW a repository outside this checkout (#5810a9f3), created by the same command",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git checkout -- ."),
        "destructive-git scope CONTROL: the same command in the console is still refused",
    ),
    case(
        "check 0 guards/block_commit_meta.py",
        bash_json(
            'git init -q /tmp/claude-1000/fx/nb && cd /tmp/claude-1000/fx/nb && git commit -m "fix: x\\n\\nCo-Authored-By: A <a@b.c>"'
        ),
        "commit-meta scope: ALLOW a repository outside this checkout (#5810a9f3), created by the same command",
    ),
    case(
        "check 2 guards/block_commit_meta.py",
        bash_json('git commit -m "fix: x\\n\\nCo-Authored-By: A <a@b.c>"'),
        "commit-meta scope CONTROL: the same command in the console is still refused",
    ),
    case(
        "check 0 guards/block_prose_style_commit.py",
        bash_json(
            'git init -q /tmp/claude-1000/fx/nb && cd /tmp/claude-1000/fx/nb && git commit -m "feat: you should see — this"'
        ),
        "prose-style-commit scope: ALLOW a repository outside this checkout (#5810a9f3), created by the same command",
    ),
    case(
        "check 2 guards/block_prose_style_commit.py",
        bash_json('git commit -m "feat: you should see — this"'),
        "prose-style-commit scope CONTROL: the same command in the console is still refused",
    ),
    case(
        "check 2 guards/block_pathspecless_git_commit.py",
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
    # #18c7e53c, operator ruling 2026-10-09: /branch-rebase is AI-invocable, and what its prose forbids a guard refuses. Every BLOCK row below answered rc 0 through the live pre-bash chain in the audit that opened the item. Each payload answers the same in any checkout: no row depends on which branch is checked out or what is dirty.
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git checkout -f"),
        "destructive-git #18c7e53c: a forced checkout overwrites every modified file",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git checkout -f main"),
        "destructive-git #18c7e53c: a forced checkout of a branch",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git checkout HEAD packages/cli/x.ts"),
        "destructive-git #18c7e53c: a tree-ish and a path without --",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git checkout origin/main packages/cli/x.ts"),
        "destructive-git #18c7e53c: a remote ref and a path without --",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git checkout zz-no-such-ref-q9"),
        "destructive-git #18c7e53c: a lone operand that resolves as no ref is a pathspec",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git checkout --ours private/renet"),
        "destructive-git #18c7e53c: --ours on a gitlink drops the branch's submodule work",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git checkout --theirs private/renet"),
        "destructive-git #18c7e53c: --theirs on a gitlink pins an orphaned commit",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git -C private/renet switch -f main"),
        "destructive-git #18c7e53c: a forced switch in a submodule",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git switch --discard-changes main"),
        "destructive-git #18c7e53c: a discarding switch",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git reset --hard origin/main"),
        "destructive-git #18c7e53c: a hard reset",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git -C private/renet reset --hard origin/main"),
        "destructive-git #18c7e53c: a hard reset in a submodule",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git reset --keep HEAD"),
        "destructive-git #18c7e53c: a keep reset rewrites the tree too",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git rebase --autostash origin/main"),
        "destructive-git #18c7e53c: --autostash stashes peers' work",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git -c rebase.autoStash=true rebase origin/main"),
        "destructive-git #18c7e53c: -c rebase.autoStash is the same stash",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git -C private/renet pull --rebase --autostash"),
        "destructive-git #18c7e53c: pull --autostash in a submodule",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git merge --autostash origin/main"),
        "destructive-git #18c7e53c: merge --autostash",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git config --global rebase.autoStash true"),
        "destructive-git #18c7e53c: a global autoStash write",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git checkout HEAD"),
        "destructive-git #18c7e53c: a lone operand that resolves is a switch",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git -C private/renet checkout --detach HEAD"),
        "destructive-git #18c7e53c: setting a gitlink by commit stays open",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git reset --soft HEAD~1"),
        "destructive-git #18c7e53c: a soft reset keeps the tree",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git reset -- packages/cli/x.ts"),
        "destructive-git #18c7e53c: a path reset only unstages",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git rebase --no-autostash origin/main"),
        "destructive-git #18c7e53c: --no-autostash is allowed",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git config rebase.autoStash false"),
        "destructive-git #18c7e53c: turning autoStash off is allowed",
    ),
    # #a234b06e, the second widening: the audit's B38-B49 forms. With no submodule present a foreach payload is judged in the repository itself, so these rows too answer the same in any checkout.
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git rm -f packages/cli/x.ts"),
        "destructive-git #a234b06e: a forced rm deletes a modified file",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git rm --cached -r ."),
        "destructive-git #a234b06e: a recursive cached rm empties the shared index",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git read-tree --reset -u HEAD"),
        "destructive-git #a234b06e: read-tree -u rewrites the work tree",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git checkout-index -f -a"),
        "destructive-git #a234b06e: a forced checkout-index overwrites modified files",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git submodule update --init --force"),
        "destructive-git #a234b06e: a forced submodule update discards submodule work",
    ),
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git submodule foreach git clean -fd"),
        "destructive-git #a234b06e: a foreach payload is judged as a command in each submodule",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git rm packages/cli/x.ts"),
        "destructive-git #a234b06e: a plain rm stays open, git refuses it over a modified file",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git rm --cached packages/cli/x.ts"),
        "destructive-git #a234b06e: one cached path stays open",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git submodule update --init --recursive"),
        "destructive-git #a234b06e: /pr-merge's submodule update stays open",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git submodule foreach git status"),
        "destructive-git #a234b06e: a read-only foreach payload stays open",
    ),
    # Review 9849764b.1: a payload's `-C` is relative to the submodule it runs in, so `../..` from private/renet is this checkout.
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("git -C private/renet submodule foreach 'git -C ../.. checkout -- .'"),
        "destructive-git 9849764b.1: a foreach payload's relative -C resolves from the submodule",
    ),
    # Review 72e7ac97.2/.3: GIT_CONFIG_PARAMETERS is read per key, and an empty value is git's false.
    case(
        "check 2 guards/block_destructive_git_restore.py",
        bash_json("""GIT_CONFIG_PARAMETERS="'rebase.autostash'='true'" git rebase origin/main"""),
        "destructive-git 72e7ac97.2: GIT_CONFIG_PARAMETERS with autostash true",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("""GIT_CONFIG_PARAMETERS="'rebase.autostash'='false'" git rebase origin/main"""),
        "destructive-git 72e7ac97.2 CONTROL: GIT_CONFIG_PARAMETERS with autostash false",
    ),
    case(
        "check 0 guards/block_destructive_git_restore.py",
        bash_json("git -c rebase.autostash= rebase origin/main"),
        "destructive-git 72e7ac97.3 CONTROL: an empty -c value is false",
    ),
    case(
        "check 2 guards/block_blanket_git_add.py",
        bash_json("cd private/account && git add -A"),
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
            # LOCAL today, deliberately: the guard under test reads the clock with a bare `datetime.now()` precisely so it honours TZ the way its `date +%m%d` twin does. A tz-aware `today()` here would disagree with the guard
            # for the hours either side of local midnight and fail this case on
            # any host off Greenwich -- which is the exact defect the guard's port notes record being measured at 00:47 CEST.
            # The date is `TODAY_MARK`, filled when the case RUNS (#0f87655f): a date frozen when this table is imported is yesterday's for every case run after a midnight the suite crosses.
            "gh pr create --draft --head %s-9 -t x -b y" % TODAY_MARK
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
    # THE HATCH AS A COMMAND PREFIX, the only form an agent's Bash call can pass: the hook reads its own environment, so a prefix was invisible and the guard's own advice was unrunnable (2026-09-24).
    case(
        "check 0 guards/block_stale_pr_branch_date.py",
        bash_json("PR_BRANCH_DATE_OK=1 gh pr create --head 0825-2 -t x"),
        "stale-pr-branch: the documented hatch works as a command prefix",
    ),
    case(
        "check 2 guards/block_stale_pr_branch_date.py",
        bash_json('echo "PR_BRANCH_DATE_OK=1 gh pr create" && gh pr create --head 0825-2 -t x'),
        "stale-pr-branch CONTROL: the hatch quoted as prose opens nothing",
    ),
    # A QUOTED NEIGHBOUR ASSIGNMENT: the turbo push guard demands `TURBO_PUSH_REASON='<kind>: <why>'` on the same `gh pr create`, and a value with spaces made the hatch unmatchable, so the two guards could not both be satisfied (2026-10-21).
    case(
        "check 0 guards/block_stale_pr_branch_date.py",
        bash_json(
            "PR_BRANCH_DATE_OK=1 TURBO_PUSH_REASON='ci-cd: a reason with spaces' gh pr create --head 0825-2 -t x"
        ),
        "stale-pr-branch: the hatch holds beside a quoted assignment after it",
    ),
    case(
        "check 0 guards/block_stale_pr_branch_date.py",
        bash_json(
            "TURBO_PUSH_REASON='ci-cd: a reason with spaces' PR_BRANCH_DATE_OK=1 gh pr create --head 0825-2 -t x"
        ),
        "stale-pr-branch: the hatch holds beside a quoted assignment before it",
    ),
    case(
        "check 2 guards/block_stale_pr_branch_date.py",
        bash_json(
            "TURBO_PUSH_REASON='ci-cd: a reason with spaces' gh pr create --head 0825-2 -t x"
        ),
        "stale-pr-branch CONTROL: a quoted assignment without the hatch opens nothing",
    ),
    case(
        "check 0 guards/block_stale_pr_branch_date.py",
        bash_json(
            'TURBO_PUSH_REASON="ci-cd: a reason with spaces" PR_BRANCH_DATE_OK=1 gh pr create --head 0825-2 -t x'
        ),
        "stale-pr-branch: the hatch holds beside a double-quoted assignment",
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
    # Round-40 review finding: GNU long options and value-taking short options before -c also defeated the round-40 flag-shape regex; fixed via token-scanning (any intervening token is skippable) instead of a 4th regex.
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
    # Round-46 (live during a real /pr-merge): fields were parsed from the WHOLE bash line, so sibling gh invocations donated fields to each other and only ONE invocation per line was ever examined. Each of these pairs a compliant invocation with a violating one; both must be judged on their own segment.
    case(
        "check 2 guards/block_nondraft_pr_create.py",
        bash_json(
            "gh pr create --draft --repo "
            + GH_REPO
            + " -t x; gh pr create --repo "
            + GH_REPO
            + " -t y"
        ),
        "nondraft-create: second create on the line is judged too (no --draft donation)",
    ),
    case(
        "check 2 guards/block_nondraft_pr_create.py",
        bash_json(
            "gh pr create --draft --repo "
            + GH_REPO
            + " -t x; gh pr create --draft --repo "
            + RENET_REPO
            + " -t y"
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
    case(
        "check 0 guards/block_settled_questions.py",
        ask_json("How do I push to a fork?"),
        "settled(push how-do mechanics passes)",
    ),
    case(
        # The permission rule, not the timing rule, owns "can i push": a leading `how` does not make it a mechanics question.
        "check 2 guards/block_settled_questions.py",
        ask_json("How can I push a submodule commit?"),
        "settled(push how-can is still a permission ask)",
    ),
    case(
        "check 0 guards/block_settled_questions.py",
        ask_json("We already pushed the first fix to origin."),
        "settled(push statement with a time word passes)",
    ),
    case(
        "check 2 guards/block_settled_questions.py",
        ask_json("How should a finished turbo batch push?"),
        "settled(push how-should timing refused)",
    ),
    case(
        "check 2 guards/block_settled_questions.py",
        ask_json("Should I push now?"),
        "settled(push now question refused)",
    ),
    case(
        # An unpunctuated timing ask is still the permission rule's: the time word is not what refuses it.
        "check 2 guards/block_settled_questions.py",
        ask_json("Should we push now."),
        "settled(push now unpunctuated refused)",
    ),
    case(
        # A mechanics lead (how do/does/can ...) keeps a trailing time clause part of the mechanics.
        "check 0 guards/block_settled_questions.py",
        ask_json("How do we push the batch once the review is in?"),
        "settled(push how-do with a once clause is mechanics)",
    ),
    case(
        "check 0 guards/block_settled_questions.py",
        ask_json("How do I push to a fork once my branch is rebased?"),
        "settled(push how-do to a fork with a once clause is mechanics)",
    ),
    case(
        "check 0 guards/block_settled_questions.py",
        ask_json("How do we push the batch until the review is in?"),
        "settled(push how-do with an until clause is mechanics)",
    ),
    case(
        "check 2 guards/block_settled_questions.py",
        ask_json("Should I push once CI is green?"),
        "settled(push should with a once clause is timing)",
    ),
    case(
        # Review ef6e61d0.1: a mechanics lead silences only a once/until condition, never a time choice.
        "check 2 guards/block_settled_questions.py",
        ask_json("How do we push the batch now or later?"),
        "settled(push how-do with a now-or-later choice is timing)",
    ),
    case(
        # Review 53e2515a.1: a time word inside the object noun phrase of a mechanics question is not a timing ask.
        "check 0 guards/block_settled_questions.py",
        ask_json("How do I push the first commit to my fork?"),
        "settled(push how-do with 'the first commit' is mechanics)",
    ),
    case(
        "check 0 guards/block_settled_questions.py",
        ask_json("How do I push the fix I already committed?"),
        "settled(push how-do with 'I already committed' is mechanics)",
    ),
    case(
        # Review cae71925.1: the determiner or pronoun must modify a following word; at the end of the clause it is the timing ask.
        "check 2 guards/block_settled_questions.py",
        ask_json("How do we push this first?"),
        "settled(push how-do ending in 'this first' is timing)",
    ),
    case(
        "check 2 guards/block_settled_questions.py",
        ask_json("How do I push it already?"),
        "settled(push how-do ending in 'it already' is timing)",
    ),
    case(
        "check 2 guards/block_settled_questions.py",
        ask_json("How do I push that already, or wait for the review?"),
        "settled(push how-do with 'that already, or wait' is timing)",
    ),
    case(
        "check 2 guards/block_settled_questions.py",
        ask_json("How do we push the branch first, or wait for the review?"),
        "settled(push how-do with an or-wait alternative is timing)",
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
    # #bc7d998c: the path is judged where the write LANDS. Both refusals were allowed (rc 0) before, the second because its typed `docs/agent/` prefix took the docs exclusion; the control was allowed before and stays allowed.
    case(
        "check 2 guards/block_agent_state_shape.py",
        tool_json("Write", "agent/x/../deadbeef/STATE.md", "content", "tiny"),
        "agent-state: a .. detour into a session's STATE.md",
    ),
    case(
        "check 2 guards/block_agent_state_shape.py",
        tool_json("Write", "docs/agent/../../agent/deadbeef/STATE.md", "content", "tiny"),
        "agent-state: a docs/agent prefix that lands in agent/",
    ),
    case(
        "check 0 guards/block_agent_state_shape.py",
        tool_json("Write", "agent/deadbeef/../../docs/agent/x/STATE.md", "content", "tiny"),
        "agent-state CONTROL: a .. detour that lands in docs/agent",
    ),
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
    # --- should PASS (exit 0) --- NOTE: block-admin-merge.sh verifies live thread state over the network on its enforcement path; only its pattern paths (--auto, --draft flags, non-matching commands) are unit-tested here.
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
        bash_json("gh pr list --repo " + GH_REPO),
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
    # Regression: the phrase inside heredoc/doc prose is NOT an invocation. The unanchored v1 fired on a round-log heredoc that merely mentioned the flow. The delimiter is QUOTED since 2026-09-24 (PLAN-retire-bash-oracles A4, A0 L3): under a bare `<<EOF` bash expands the backticks and really runs `gh pr ready`, so the unquoted spelling this case used to carry was a flip, not prose; block_premature_ready's EDGE_CASES pin both spellings.
    case(
        "check 0 guards/block_premature_ready.py",
        bash_json("cat >> log.md <<'EOF'\ngreen-gated `gh pr ready` + hook-banned --admin\nEOF"),
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
        bash_json('git -C nonexistent-subdir-xyz commit -m "chore: no trailer"'),
        "target-root CONTROL: a -C under this checkout that resolves to no repo is not an exemption",
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
    # Round-46 cross-attribution, the exact live firing: a sibling `gh pr view` donated its --repo to the merge's PR number, resolving a DIFFERENT repo's PR #66 (long merged, one unresolved thread) and blocking a clean merge. With the segment fix this stays a foreign-repo no-op and never hits the network; with the bug it resolves rediacc/renet and blocks.
    case(
        "check 0 guards/block_admin_merge.py",
        bash_json("gh pr view 94 --repo " + RENET_REPO + "; gh pr merge 66 --repo otherorg/tool"),
        "admin-merge: sibling gh --repo does not donate to the merge segment",
    ),
    # NOT asserted here: per-segment --auto and per-segment PR selectors on block-admin-merge. Both only change behavior once a rediacc repo is resolved, which puts them on the network path this offline harness cannot drive (same limitation as the NOTE above). They are covered by the hook's live proofs, not by a case that would pass either way -- a green assertion that cannot fail
    # is worse than no assertion. REST/GraphQL parity (agent/plans/PLAN-rest-graphql-guard-parity.md): the same three guards also police the REST or GraphQL call that reaches the identical GitHub mutation as the `gh pr` verb they already gate. One BLOCK and one ALLOW per guard, mirrored here because hook_integrity.covmap reads coverage off this exact "check <rc> guards/<module>.py"
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
    # #0c331972, 2026-10-11: three guards matched raw text, so a plain echo of the command they guard was refused (rc 2 at 306285231, each measured). They judge the runs bash would start now: every CONTROL row below was refused before, and every deny row is a real run of the same command. block_adhoc_sanctioned keeps its text match by operator ruling 2026-08-25 (#6a2c9652), so it has deny rows here and no mention control.
    case(
        "check 2 guards/block_adhoc_sanctioned.py",
        bash_json("bash -c 'gh run watch 123'"),
        "adhoc: a watch inside sh -c still runs",
    ),
    case(
        "check 0 guards/block_bash_write_to_running_script.py",
        bash_json("echo 'echo x > /tmp/rediacc-guard-bashwrite/bash-side-suite.sh'"),
        "bash-write CONTROL: an echo quoting a redirect writes nothing",
    ),
    case(
        "check 0 guards/block_binary_deploy.py",
        bash_json("echo 'true; sudo cp renet /usr/local/bin/renet'"),
        "binary-deploy CONTROL: a quoted separator is not a command position",
    ),
    case(
        "check 2 guards/block_binary_deploy.py",
        bash_json("sudo -u root cp renet /usr/local/bin/renet"),
        "binary-deploy: sudo with an option still copies onto the binary",
    ),
    case(
        "check 0 guards/block_binary_deploy.py",
        bash_json("sudo cp /usr/local/bin/renet /tmp/renet.bak"),
        "binary-deploy CONTROL: backing up the installed binary is a read",
    ),
    # Review 0bbd6471.1: a renet-named sibling in the install directory is the two-step deploy, and every copier counts.
    case(
        "check 2 guards/block_binary_deploy.py",
        bash_json("sudo cp bin/renet /usr/local/bin/renet.new"),
        "binary-deploy: a staged renet sibling is refused",
    ),
    case(
        "check 2 guards/block_binary_deploy.py",
        bash_json("sudo install -m 755 bin/renet /usr/local/bin/renet"),
        "binary-deploy: sudo install onto the binary is refused",
    ),
    case(
        "check 0 guards/block_binary_deploy.py",
        bash_json("sudo cp bin/rdc /usr/local/bin/rdc"),
        "binary-deploy CONTROL: another binary in the install directory",
    ),
    # Review 126f2a9f.1 and 88362611.1: a fed word bash brace-expands is not a literal (allowed at 126f2a9fc), and a destination a variable holds is read expanded.
    case(
        "check 2 guards/block_binary_deploy.py",
        bash_json("echo {/tmp/x,/usr/local/bin/renet} | sudo xargs cp bin/renet"),
        "binary-deploy: a brace-expanded fed destination is the binary",
    ),
    case(
        "check 2 guards/block_binary_deploy.py",
        bash_json("D=/usr/local/bin/renet; sudo cp bin/renet $D"),
        "binary-deploy: a destination set by an earlier statement",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("echo 'echo x | tee --output-error=warn agent/pr-babysit-0831-1.md'"),
        "roundlog-truncate CONTROL: an echo quoting a truncating tee",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("echo x | tee --output-error=warn agent/pr-babysit-0831-1.md"),
        "roundlog-truncate: the same tee, run",
    ),
    # Review 3f53e99e.2 sweep: in place is sed's own option parse. The first refusal pins a bundle; the control was refused before, its `i` read inside an attached `-e` script.
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("sed -Ei 's/a/b/' agent/pr-babysit-0831-1.md"),
        "roundlog-truncate: sed -Ei is in place",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("sed -es/i/x/ agent/pr-babysit-0831-1.md"),
        "roundlog-truncate CONTROL: an i inside an attached -e script is not in place",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            ".claude/hooks/stop/worklist.py --roundlog 0831-1; mv agent/pr-babysit-0831-1.md /tmp/bak.md"
        ),
        "roundlog-truncate: the verb's name no longer exempts a mv on the same line",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("echo x >> agent/pr-babysit-0831-1.md"),
        "roundlog-truncate CONTROL: an append cannot truncate",
    ),
    # Review 0bbd6471.3: xargs appends the log as cp's destination.
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("echo agent/pr-babysit-0831-1.md | xargs cp /tmp/bak.md"),
        "roundlog-truncate: xargs feeds the log to cp as its destination",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("cp agent/pr-babysit-0831-1.md /backup/"),
        "roundlog-truncate CONTROL: a copy into a backup directory is a read",
    ),
    # Review 126f2a9f.1: a fed word bash brace-expands is not a literal (allowed at 126f2a9fc).
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("echo {/tmp/x,agent/pr-babysit-0831-1.md} | xargs cp /tmp/y.md"),
        "roundlog-truncate: a brace-expanded fed destination is the log",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("echo {/tmp/x,/tmp/z} | xargs cp /tmp/y.md"),
        "roundlog-truncate CONTROL: a brace-expanded fed destination elsewhere",
    ),
    # Review 8ae5b370.1: a ten-billion range is capped, not built; the guard answers inside the case timeout.
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("echo {1..9999999999} pr-babysit-0831-1.md | xargs cp /tmp/x.md"),
        "roundlog-truncate: a huge fed brace range is capped and the log still read",
    ),
    # Review 8ae5b370.2 and .4: bash expands a brace after an unmatched `{`, and a stepped range (both allowed at 8ae5b3706).
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("echo x{y{/tmp/a,agent/pr-babysit-0831-1.md} | xargs cp /tmp/x.md"),
        "roundlog-truncate: a brace after an unmatched one still expands to the log",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "cat agent/pr-babysit-0831-1.md; echo agent/pr-babysit-0831-{1..3..2}.md | xargs cp /tmp/x.md"
        ),
        "roundlog-truncate: a stepped fed range expands to the log",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "cat agent/pr-babysit-0831-1.md; echo /tmp/pr-babysit-0831-{2..4..2}.txt | xargs cp /tmp/x.md"
        ),
        "roundlog-truncate CONTROL: a stepped fed range that names no log",
    ),
    # #e5b0540a: a glob or brace that could spell a round-log name passes the prefilter (it allowed all of these before the walk ran), and every arm reads it expanded.
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json('cd "$D" && echo pr-babysit-*.md | xargs cp /tmp/x.md'),
        "roundlog-truncate: a fed log glob in an unknown directory",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("mv agent/pr-babysit-{0831-1,x}.md /tmp/"),
        "roundlog-truncate: mv a brace that spells the log",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("echo x > agent/pr-babysit-*.md"),
        "roundlog-truncate: a redirect onto a log glob",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json('cd "$D" && echo notes-*.md | xargs cp /tmp/x.md'),
        "roundlog-truncate CONTROL: a fed glob that cannot spell a log",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("ls agent/pr-babysit-*.md"),
        "roundlog-truncate CONTROL: listing a log glob is a read",
    ),
    # #6378e10e: perl edits in place too (allowed at 553038bdb while only sed was asked).
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("perl -pi -e 's/a/b/' agent/pr-babysit-0831-1.md"),
        "roundlog-truncate: perl -pi rewrites the log",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("perl -pe 's/a/b/' agent/pr-babysit-0831-1.md"),
        "roundlog-truncate CONTROL: perl -pe only prints the log",
    ),
    # Review 9ed30a8a.3: the prefilter meets the round-log pattern itself, not three sample names, and a relative glob in an unknown directory that could name a log counts as one (both allowed at 553038bdb).
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json('cd "$D" && echo pr-babysit-a*.md | xargs cp /tmp/x.md'),
        "roundlog-truncate: a log glob no sample name fits still reaches the walk",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json('cd "$D" && truncate -s 0 *.md'),
        "roundlog-truncate: an md glob in an unknown directory could be a log",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json('cd "$D" && truncate -s 0 *.txt'),
        "roundlog-truncate CONTROL: a txt glob cannot be a log",
    ),
    # #e5b0540a, live false positive reported by w2: a `*` in Python code passed the whole-command prefilter and the program's write through a variable failed closed (all three refused at 677f3ca25).
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('notes.txt')\nn = 3 * 4\np.write_text(str(n))\nEOF"
        ),
        "roundlog-truncate CONTROL: a heredoc that multiplies and writes through a variable",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import pathlib,sys; t=pathlib.Path(sys.argv[1]); t.write_text('x' * 3)\" out.txt"
        ),
        "roundlog-truncate CONTROL: python -c repeating a string into a file",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("python3 - <<'EOF'\nfrom os import *\nf = open(name, 'w')\nf.write('x')\nEOF"),
        "roundlog-truncate CONTROL: a star import that writes",
    ),
    # ...and a program whose own text could spell a log still fails closed on an unresolvable target.
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 - <<'PY'\nimport glob\nfor p in glob.glob('agent/*.md'):\n    open(p, 'w').write('')\nPY"
        ),
        "roundlog-truncate: a program globbing md files writes through a variable",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 - <<'PY'\nb = '0831-1'\nopen(f'agent/pr-babysit-{b}.md', 'w').write('')\nPY"
        ),
        "roundlog-truncate: a program building the log name in an f-string",
    ),
    # Review 1d4e1754.1: a program HANDED the log (an argument, the environment, stdin) names no path in its text, and all three were allowed at 50fcf7c7f.
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys; open(sys.argv[1],'w').write('')\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: a program opening argv for write, handed the log",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "F=agent/pr-babysit-0831-1.md python3 -c \"import os; open(os.environ['F'],'w').write('')\""
        ),
        "roundlog-truncate: the log handed through the environment",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "echo agent/pr-babysit-0831-1.md | python3 -c \"import sys; open(sys.stdin.read().strip(),'w').write('')\""
        ),
        "roundlog-truncate: the log handed on stdin",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            'python3 -c "import sys; print(open(sys.argv[1]).read())" agent/pr-babysit-0831-1.md'
        ),
        "roundlog-truncate CONTROL: a program that only reads the log it is handed",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "cat agent/pr-babysit-0831-1.md; python3 -c \"import sys; open(sys.argv[1],'w').write('')\" notes.txt"
        ),
        "roundlog-truncate CONTROL: a writer handed another file after the log was only read",
    ),
    # Review 4b3f59b5.1: the program arm is judged per write. Each deny row was allowed at d15fe3f5b with the log handed.
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys; print(open('README.md').read()); open(sys.argv[1],'w').write('')\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: a named md file read beside a write to argv",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys,pathlib; pathlib.Path(sys.argv[1]).open('w').write('')\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: a path object's own open('w') on argv",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            'python3 -c "import sys,os; os.truncate(sys.argv[1], 0)" agent/pr-babysit-0831-1.md'
        ),
        "roundlog-truncate: os.truncate on argv",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json('python3 -c "import sys,os; os.remove(sys.argv[1])" agent/pr-babysit-0831-1.md'),
        "roundlog-truncate: os.remove on argv",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys,os; os.system('cp /dev/null ' + sys.argv[1])\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: a shell command built from argv",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "node -e \"require('fs').truncateSync(process.argv[1])\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: node truncateSync on argv",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys; open(sys.argv[1].split('=')[1],'w').write('')\" --out=pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: the log as an option's value",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            'cd "$D" && ls *.md | python3 -c "import sys; [open(l.strip(),\'w\') for l in sys.stdin]"'
        ),
        "roundlog-truncate: an md glob on the program's stdin",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys; m='w'; open(sys.argv[1], m).write('')\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: a write mode held in a variable",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\np = 'x.txt'\nfor p in sys.argv[1:]:\n    open(p, 'w').write('')\nPY"
        ),
        "roundlog-truncate: a literal-bound name a loop rebinds",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys; open('out.txt','w').write(open(sys.argv[1]).read())\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate CONTROL: a named output written from the handed log",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys; print(open(sys.argv[1]).read()); open('copy.md','w').write('x')\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate CONTROL: a named md copy written while the handed log is printed",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys; m='r'; print(open(sys.argv[1], m).read())\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate CONTROL: a read mode held in a variable",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys; open(sys.argv[1], 'a').write('more')\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate CONTROL: an append to the handed log",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("python3 -c \"p=2*3; open('n.txt','w').write(str(p))\""),
        "roundlog-truncate CONTROL: a star in inline code beside a named write",
    ),
    # Review 8b651626.1: a perl open's path is its third argument, not its handle. The controls were refused at f087a1b96; the python deny rows were allowed.
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json('perl -e \'open(my $f, ">", "out.txt"); print $f 1\' agent/pr-babysit-0831-1.md'),
        "roundlog-truncate CONTROL: perl writing a named file beside the handed log",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("perl -e 'open(F, \">out.txt\"); print F 1' agent/pr-babysit-0831-1.md"),
        "roundlog-truncate CONTROL: perl two-argument open onto a named file",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json('perl -e \'open my $f, ">", "out.txt"; print $f 1\' agent/pr-babysit-0831-1.md'),
        "roundlog-truncate CONTROL: perl open without parentheses onto a named file",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys,pathlib; s=pathlib.Path(sys.argv[1]).read_text(); print(s.replace('a','b'))\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate CONTROL: str.replace on text read through a Path of the handed log",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json('perl -e \'open(my $f, ">", "agent/pr-babysit-0831-1.md")\''),
        "roundlog-truncate: perl three-argument open onto the log by name",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("perl -e 'open my $f, \">\", $ARGV[0]; close $f' agent/pr-babysit-0831-1.md"),
        "roundlog-truncate: perl open without parentheses onto argv",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys,pathlib; p=pathlib.Path(sys.argv[1]); p.replace('/tmp/x')\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: Path.replace on a name bound to a Path of argv",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys,pathlib; pathlib.Path('x.txt').rename(sys.argv[1])\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: Path.rename of a named file onto argv",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys; __import__('os').remove(sys.argv[1])\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: __import__('os').remove on argv",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys,os; getattr(os,'rem'+'ove')(sys.argv[1])\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: getattr on os with a concatenated literal name",
    ),
    # Reviews 97a72d29.1/.2: with a log in play the program must be one the guard can follow. The deny rows were allowed at ca2f75c43; the BOUNDARY rows are the same programs with no log in play.
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\nfrom pathlib import Path\np = 'x'\np = Path(sys.argv[1])\np.replace('/tmp/x')\nPY"
        ),
        "roundlog-truncate: a name bound to a string and then to a Path of argv",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys; __import__('o' + 's').remove(sys.argv[1])\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: __import__ with a concatenated module name",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys, pathlib\nxs = []\nxs.append(pathlib.Path(sys.argv[1]))\nxs[0].unlink()\nPY"
        ),
        "roundlog-truncate: a Path of argv appended to a list and indexed back",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys,os; vars(os)['remove'](sys.argv[1])\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: vars() subscripted for a writer",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys; ().__class__.__base__.__subclasses__()[0](sys.argv[1], 'w')\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: a subclass walk from a tuple",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\nclass W:\n    def go(self, p):\n        open(p, 'w')\nW().go(sys.argv[1])\nPY"
        ),
        "roundlog-truncate: a class",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "node -e \"const fs=require('fs'); fs['rm'+'Sync'](process.argv[1])\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: node: a computed member call",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json('ruby -e "ARGV.each(&File.method(:delete))" agent/pr-babysit-0831-1.md'),
        "roundlog-truncate: ruby: a method object",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("ruby -i -pe '$_.upcase!' agent/pr-babysit-0831-1.md"),
        "roundlog-truncate: ruby: -i edits the handed file in place",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json("perl -e 'my $f = \"unlink\"; &$f($ARGV[0])' agent/pr-babysit-0831-1.md"),
        "roundlog-truncate: perl: a call through a name",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("python3 -c \"import sys; __import__('o' + 's').remove(sys.argv[1])\" notes.txt"),
        "roundlog-truncate CONTROL: BOUNDARY: a concatenated __import__ handed another file",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 - notes.txt <<'PY'\nimport sys\nfrom pathlib import Path\np = 'x'\np = Path(sys.argv[1])\np.replace('/tmp/x')\nPY"
        ),
        "roundlog-truncate CONTROL: BOUNDARY: a mixed-binding Path handed another file",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 -c \"import sys,subprocess; subprocess.run(['rm', sys.argv[1]])\" notes.txt"
        ),
        "roundlog-truncate CONTROL: BOUNDARY: a subprocess handed another file",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "cat agent/pr-babysit-0831-1.md; python3 -c \"import subprocess; subprocess.run(['ls'])\""
        ),
        "roundlog-truncate CONTROL: BOUNDARY: a subprocess beside a cat of the log",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys, datetime\nlines = open(sys.argv[1]).read().splitlines()\nrows = sorted(lines, key=lambda l: l.lower())\nout = open('sorted.txt', 'w')\nout.write('\\n'.join(rows))\nout.close()\nprint(datetime.datetime.now().isoformat(), len(rows))\nPY"
        ),
        "roundlog-truncate CONTROL: a sort by a lambda written to a named file",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport argparse\np = argparse.ArgumentParser()\np.add_argument('log')\na = p.parse_args()\nprint(open(a.log).read().count('\\n'))\nPY"
        ),
        "roundlog-truncate CONTROL: argparse reading the handed log",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "node -e \"const fs=require('fs'); const t=fs.readFileSync(process.argv[1],'utf8').split('\\n').filter(l => l.startsWith('#')); console.log(t.length)\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate CONTROL: node: an arrow filter over the handed log",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "ruby -e \"File.open('out.txt', 'w') { |f| f.write(File.read(ARGV[0])) }\" agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate CONTROL: ruby: a block writing a named file from the handed log",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("perl -ne 'print if /round/' agent/pr-babysit-0831-1.md"),
        "roundlog-truncate CONTROL: perl: -ne with a pattern",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            'perl -e \'open(my $f, ">|", "out.txt"); print $f 1\' agent/pr-babysit-0831-1.md'
        ),
        "roundlog-truncate CONTROL: perl: the >| mode onto a named file is not a pipe",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json("perl -e 'open(FH, \"w\"); print <FH>' agent/pr-babysit-0831-1.md"),
        "roundlog-truncate CONTROL: perl: a two-argument open of a file named w is a read",
    ),
    # Reviews 801bbb46.1/.2: a construct whose extent the word reader does not know is refused, not blanked.
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            'perl -e \'local $" = ","; my $c = \\&CORE::unlink; $c->($ARGV[0])\' agent/pr-babysit-0831-1.md'
        ),
        "roundlog-truncate: perl: the list separator variable is not a string opener",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "perl -e 'my @x = qw#a#; my $c = \\&CORE::unlink; $c->($ARGV[0])' agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: perl: a quote-like operator on a # delimiter is not a comment",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            'ruby -e \'x = ?"; File.send(:delete, ARGV[0]); y = ""\' agent/pr-babysit-0831-1.md'
        ),
        "roundlog-truncate: ruby: a character literal is not a string opener",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "perl -e 'open(my $f, \"<\", $ARGV[0]) or die; print <$f>' agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate CONTROL: perl: a plain read of the handed log",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json('ruby -e "puts File.read(ARGV[0])" agent/pr-babysit-0831-1.md'),
        "roundlog-truncate CONTROL: ruby: a plain read of the handed log",
    ),
    # Reviews 012e1b7b.1/.2/.3: the quote-like extent rule, not a delimiter list. The deny rows were allowed at cc5dbd0a3.
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            'ruby -e \'x = %-"-; y = File.send(:delete, ARGV[0]); z = ""\' agent/pr-babysit-0831-1.md'
        ),
        "roundlog-truncate: ruby: percent on a dash delimiter",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            'perl -e \'my @q = qw,",; my $c = \\&CORE::unlink; $c->($ARGV[0]); print ""\' agent/pr-babysit-0831-1.md'
        ),
        "roundlog-truncate: perl: qw on a comma delimiter",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            'perl -e \'print << "EOT";\nA"\nEOT\nmy $c = \\&CORE::unlink; $c->($ARGV[0]); print ""\' agent/pr-babysit-0831-1.md'
        ),
        "roundlog-truncate: perl: heredoc with a space before the quoted tag",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            'ruby -e \'x = %Q-"-; y = File.send(:delete, ARGV[0]); z = ""\' agent/pr-babysit-0831-1.md'
        ),
        "roundlog-truncate: ruby: a typed percent on a dash delimiter",
    ),
    # Review a52292e4.4: the four rows of the round above that had only a golden record. Reviews a52292e4.1/.2: a quote-like word after an operator, and one with a space before its slash; allowed at d0452ef0b.
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            'ruby -e \'x = %="=; y = File.send(:delete, ARGV[0]); z = ""\' agent/pr-babysit-0831-1.md'
        ),
        "roundlog-truncate: ruby: percent on an equals delimiter",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            'perl -e \'print 1 if m,",; my $c = \\&CORE::unlink; $c->($ARGV[0]); print ""\' agent/pr-babysit-0831-1.md'
        ),
        "roundlog-truncate: perl: m on a comma delimiter holding a quote",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            'perl -e \'my $x="z"; $x =~ s=z="=; my $c = \\&CORE::unlink; $c->($ARGV[0]); print ""\' agent/pr-babysit-0831-1.md'
        ),
        "roundlog-truncate: perl: s on an equals delimiter holding a quote",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            'ruby -e \'x = <<~EOS\n  a"\nEOS\nFile.send(:delete, ARGV[0]); y = ""\' agent/pr-babysit-0831-1.md'
        ),
        "roundlog-truncate: ruby: a tilde heredoc body holding a quote",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "perl -e 'my $x = 1>q#a#; my $c = \\&CORE::unlink; $c->($ARGV[0]); print \"\"' agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: perl: a quote-like word after a comparison is not a name",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "perl -e 'my $x = 1&&q#a#; my $c = \\&CORE::unlink; $c->($ARGV[0]); print \"\"' agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: perl: a quote-like word after a logical and is not a name",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            "perl -e 'my $x = 7 %q#2#; my $c = \\&CORE::unlink; $c->($ARGV[0]); print \"\"' agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate: perl: a quote-like word after a modulo is not a name",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            'perl -e \'$_ = "z"; s /z/"/; my $c = \\&CORE::unlink; $c->($ARGV[0]); print ""\' agent/pr-babysit-0831-1.md'
        ),
        "roundlog-truncate: perl: a substitution with a space before its slash",
    ),
    case(
        "check 2 guards/block_roundlog_truncate.py",
        bash_json(
            'perl -e \'print 1 if m /"/; my $c = \\&CORE::unlink; $c->($ARGV[0]); print ""\' agent/pr-babysit-0831-1.md'
        ),
        "roundlog-truncate: perl: a match with a space before its slash",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json(
            "perl -e 'open(my $f, \"<\", $ARGV[0]) or die; print <$f>' agent/pr-babysit-0831-1.md"
        ),
        "roundlog-truncate CONTROL: perl: a plain read of the handed log",
    ),
    case(
        "check 0 guards/block_roundlog_truncate.py",
        bash_json('ruby -e "puts File.read(ARGV[0])" agent/pr-babysit-0831-1.md'),
        "roundlog-truncate CONTROL: ruby: a plain read of the handed log",
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
        bash_json("sleep 30 && gh run list --repo " + GH_REPO),
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
    # pattern ("sleeps 90s" is not `sleep +[0-9]+`; a `done;` sits between the sleep and the gh in the until-loop form), so they failed on correct code -- a test pinning a false positive that could not occur. These two are the real triggers.
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
    # The BOUNDARY, and the reason the false positive is narrower than it sounds: prose showing the SANCTIONED until-loop is NOT blocked, because a `done;` sits between its sleep and its gh. Only an inline `sleep N; gh run view` trips it.
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
    # The self-matching pgrep waiter. The FIRE case is the literal shape that ran 70 minutes past its condition on 2026-08-26; the first control is the documented remedy, and it must pass BY CONSTRUCTION -- a bracket class does not match its own literal text, which is the same property the hook tests
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
    # A VARIABLE EXPANSION IS NOT A FILENAME. `"$SP/mp-$ver.sh"` yielded the candidate `ver.sh` -- the tail of a variable name plus the suffix, naming a file that exists nowhere. The guard cannot know what $ver expands to, so it must not guess; both defects fired on one command while measuring this guard.
    case(
        "check 0 guards/block_bash_write_to_running_script.py",
        bash_json('python3 - "$SP/mp-$ver.sh" "$SP/out-$ver.sh" && x.write_text(1)'),
        "bash-write CONTROL: a variable expansion yields no phantom candidate",
    ),
    # A HOOK-CHAIN SIBLING IS NOT A RUNNING JOB. Every pre-bash guard executes on every Bash call, so without this exclusion the guard blocked all four of the commands repairing it -- permanently, with no moment of quiet to wait for.
    #
    # THE SUBJECT MOVED TWICE, the case did not. It named block-binary-deploy.sh until the W5 P7 cutover ported that guard to Python, then block-pathspecless-git-commit.sh until W7 P6 ported the last bash guard out of the chain. The payload has to name a bash file the chain STILL executes, or it stops being an instance of the exclusion it controls, and `chain-head.sh` is the one
    # that is left: it leads every chain, it is bash, and `HOOK_CHAIN` in the guard names it beside the four chain directories for that reason.
    case(
        "check 0 guards/block_bash_write_to_running_script.py",
        bash_json("sed -i s/a/b/ %s/chain-head.sh" % HOOKS),
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
            'R=123; until [ "$(gh run view $R --repo '
            + GH_REPO
            + ' --json status --jq .status)" = "completed" ]; do sleep 20; done; gh run view $R --repo '
            + GH_REPO
            + " --json conclusion,jobs"
        ),
        "ci-polling: terminal-state watch ok",
    ),
    case(
        "check 0 guards/block_ci_reverse_poll.py",
        bash_json(
            'R=123; until [ "$(gh run view $R --repo '
            + GH_REPO
            + ' --json status --jq .status)" = "completed" ]; do sleep 20; done; gh run view $R --repo '
            + GH_REPO
            + " --json conclusion,jobs"
        ),
        "ci-reverse-poll: terminal-state watch ok",
    ),
    case(
        "check 0 guards/block_long_sleep.py",
        bash_json(
            'R=123; until [ "$(gh run view $R --repo '
            + GH_REPO
            + ' --json status --jq .status)" = "completed" ]; do sleep 20; done; gh run view $R --repo '
            + GH_REPO
            + " --json conclusion,jobs"
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
    # The `[^|;&]*` boundary, asserted rather than assumed: a forcing flag on the far side of a pipe belongs to a different command, so the scan must stop at the pipe instead of pairing it with the push.
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
    # named this over-block class as a known risk and nothing asserted against it, so the guard refused documentation of the rule it enforces -- and then refused the edit repairing it, because the repair's comment named the tokens. A real suppression sits immediately after a comment opener; prose puts words in between, and those words are the whole difference.
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
    # 2026-10-30 (PR-TASK 9f92c43e): console is public, and a Claude session link or session trailer is refused on every publishing channel, while the audit shapes stay legal. Assembled, so no line here is itself one.
    case(
        "check_out 2 guards/block_commit_meta.py",
        bash_json(
            "git commit -m fix -m 'Claude-" + "Session: https://claude" + ".ai/code/session_01Ab'"
        ),
        "commit-meta session: a session trailer in a commit is refused, naming the public repository",
        "PUBLIC repository",
    ),
    case(
        "check 2 guards/block_commit_meta.py",
        bash_json("gh pr comment 5 -b 'see https://claude" + ".ai/chat/1a2b-3c4d'"),
        "commit-meta session: a chat link in a PR comment is refused",
    ),
    case(
        "check 2 guards/block_commit_meta.py",
        bash_json("gh api repos/o/r/issues/5/comments -f body='claude" + ".ai/code/session_01Ab'"),
        "commit-meta session: a session link in a gh api comment field is refused",
    ),
    case(
        "check 0 guards/block_commit_meta.py",
        bash_json("git log --oneline --grep claude" + ".ai"),
        "commit-meta session CONTROL: searching the log for claude.ai is an audit",
    ),
    case(
        "check 0 guards/block_commit_meta.py",
        bash_json("grep -rn 'Claude-" + "Session:' docs/"),
        "commit-meta session CONTROL: grepping for the session trailer is an audit",
    ),
]
