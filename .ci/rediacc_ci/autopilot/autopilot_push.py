#!/usr/bin/env python3
"""Port of `.ci/scripts/autopilot/autopilot-push.sh`.

THE SECURITY BOUNDARY OF THE AUTOPILOT (03-v2-autonomy.md section 0). The model never holds a write token; this script, run AFTER the model exits, is the only path from a handoff file to a commit and a push. Review any change to this file, or to this port, as a change to the security boundary itself.

Its whole job is REFUSING pushes it should not make, so the interesting surface is not the happy path -- it is the twenty-odd refusal branches below, each of which is a thing that has to stay refused. Every one is enumerated in `test_autopilot_push.py` with a case that drives it, because an incomplete port here is a security regression rather than a missed edge case.

-----------------------------------------------------------------------------
THE FOUR PHASES, AND WHY THE SPLIT IS THE DESIGN
-----------------------------------------------------------------------------
  phase 1  COMMIT every submodule, on the caller's branch name, at the
           submodule's CURRENT HEAD. No remote is written.
  phase 2  Stage and validate the CONSOLE side. Still no remote write.
  phase 3  Push: submodules first, console last.
  phase 4  If an orphan adoption moved a submodule SHA, re-stage the pointers
           and re-run phase 2's validation VERBATIM.

There is no transaction across four git remotes, but there is an order that makes the common failure -- a validation refusal -- leave ZERO remote writes. A console-side refusal used to arrive after the submodules had already been pushed, leaving branches and PRs on renet/account/elite referring to a console commit that was never made. Phase 4 re-runs the REAL check rather than
reasoning that an adopted SHA "cannot matter", which is why `stage_and_validate_console` is a function on both sides.

-----------------------------------------------------------------------------
WHAT MUST NEVER BE STAGED WHOLESALE
-----------------------------------------------------------------------------
Staging is per validated path only: `git add -- <one path>` in a loop, never `-A`, never `--all`, never a bare dot. A harness test sweeps this directory for the banned forms, and the port keeps the same shape so the same sweep reads it the same way. The staged set is then proved EQUAL to the declared set with `diff -u`, in both directions, because a pathspec that expands is the
same bug here as in console.

-----------------------------------------------------------------------------
THE THREE OUTCOMES ARE ALL FIRST-CLASS
-----------------------------------------------------------------------------
`push` stages and commits; `escalate` and `no-change` are ROUND RESULTS, not failures -- the handoff was valid, the model reached a legitimate conclusion, and the script exits 0 having staged nothing. Exiting 1 on them (as the twin did until 2026-08-09) made every escalating round paint the job red, which fired the generic failure latch and LOST the model's reason. `--verdict-out`
is published BEFORE any outcome branching, so the post-boundary steps see the same validated object on every accepted round.

-----------------------------------------------------------------------------
WHAT IS SPAWNED RATHER THAN REIMPLEMENTED, AND THIS LIST IS THE POINT
-----------------------------------------------------------------------------
`git`, `node validate-handoff.cjs`, `node exfil-tripwire.cjs`, `jq` and `diff` are all spawned exactly as the twin spawns them, with the same argv. Two of those are the actual security controls; re-implementing either would create a SECOND validator whose disagreements with the first are the hole. `diff -u` is spawned too, because its output goes to fd 2 and is the operator's
evidence for a staged-set mismatch.

  `git ls-files -s` + `awk '{print $1}'` IS REPRODUCED AS A FIELD SPLIT, and the
  vacuous case is handled the way the twin's comment says: an unstaged submodule
  yields an EMPTY entry, `staged_mode` is empty, the `!= "160000"` test fires and
  the message prints `<absent>`. That floor is the test, not the split.

-----------------------------------------------------------------------------
`set -e` DOES NOT REACH INTO `$( )`, and this port depends on knowing it
-----------------------------------------------------------------------------
`inherit_errexit` is OFF (verified, bash 5.3.9), so a failing command inside a command substitution does NOT end the twin -- only the ASSIGNMENT's own status
does. That is why `sub_top="$(git ... || true)"` yields an empty string on an
uninitialized submodule instead of dying, and why the `--base-head "$(git rev-parse HEAD)"` argument can arrive empty and be refused by the validator rather than crashing the harness. Both are reproduced.

-----------------------------------------------------------------------------
ONE UNREACHABLE ARM, NAMED SO NOBODY DELETES IT AS DEAD CODE
-----------------------------------------------------------------------------
`submodule-missing` (the `[[ ! -d "$subdir" ]]` test) cannot fire today, and the twin says so at length: both routes to an absent submodule are stopped earlier. It stays because the outcome it prevents -- submodule content committed into console as ordinary files -- is severe and the check costs one comparison. The port keeps it, and the differential drives it by handing the
validator a `--root` in which the directory has been removed between validation and staging.

  AND `rev-parse --git-dir` WOULD BE THE WRONG QUESTION. Git walks UP, so inside
  an uninitialized submodule it answers with the PARENT's git dir; every command
  after that would run against console with a working directory one level down,
  and `git add pkg/x.go` would stage `private/renet/pkg/x.go` as ordinary console
  content. Comparing the resolved TOPLEVEL is the question actually being asked,
  and `submodule_toplevel_matches` below is exported so the differential can
  drive it directly.

-----------------------------------------------------------------------------
ONE DIVERGENCE, ON AN ARM THE VALIDATOR MAKES UNREACHABLE
-----------------------------------------------------------------------------
`sub_count` comes from `jq -r '(.submodules // []) | length'` over a verdict this script produced three lines earlier with `validate-handoff.cjs`, whose schema pins `submodules` to an array. So unlike `submodule_prs.py` -- whose `--verdict` arrives from OUTSIDE and which therefore reproduces bash's arithmetic-error walk-on in full -- there is no path here by which the count is not
a non-negative integer. The port refuses a non-integer with `verdict-count-unusable` and exit 1
instead of reproducing `for ((i = 0; i < 3.5; i++))`'s syntax error. Named here
because it is a difference, and it fails CLOSED.

Exit: 0 pushed, dry-run complete, or a validated escalate/no-change round;
      1 rejected handoff or a tripped tripwire (nothing staged, nothing pushed);
      2 usage; and git's, jq's or node's own status where `set -e` takes it.

K=5 LEDGER: `.ci/shadow/w7p6-autopilot-push.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "autopilot-push.py"

USAGE = (
    "usage: autopilot-push.sh --root <checkout> --handoff <file> --branch <name> "
    "[--remote <name>] [--failed-jobs <file>] [--verdict-out <file>] [--dry-run]"
)

# The write gate. Absent is OFF; only the exact string `true` arms it. A dry run needs no flag because it never writes the remote.
ALLOW_PUSH_ENV = "AUTOPILOT_ALLOW_PUSH"
ALLOW_SUBMODULES_ENV = "AUTOPILOT_ALLOW_SUBMODULES"
ALLOW_VALUE = "true"

# Branch names the autopilot never pushes, whatever the caller says. Checked UNCONDITIONALLY: renet/account/elite have no rulesets, so this is their only guard, and even a harness bug upstream must not be able to aim this script at a default branch.
FORBIDDEN_BRANCHES = ("main", "master", "HEAD")

# `grep -qiE` on the push stderr: the shapes git uses for a non-fast-forward.
NON_FAST_FORWARD_RE = re.compile(r"non-fast-forward|fetch first|\[rejected\]", re.IGNORECASE)

# jq programs, byte for byte from the twin.
OUTCOME_PROGRAM = ".outcome"
SUB_COUNT_PROGRAM = "(.submodules // []) | length"
COMMIT_MESSAGE_PROGRAM = ".commit_message"
FILES_PROGRAM = ".files[]"
ADOPT_MESSAGE_PROGRAM = ".submodules[] | select(.path == $p) | .message"

COUNT_RE = re.compile(r"^[0-9]+$")


class _Exit(Exception):  # noqa: N818
    """One `exit N` from anywhere in the twin, including inside a function.

    Bash's `exit` inside a shell function ends the whole script; a Python `return` from a helper does not, and the two staging functions here are called from three places. Modelling it as an exception keeps the control flow the twin's rather than threading a status back through every caller.
    """

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def script_dir() -> pathlib.Path:
    """The twin's `SCRIPT_DIR`: `.ci/scripts/autopilot`, where the two `.cjs` controls live.

    From THIS file's location, matching `dirname "${BASH_SOURCE[0]}"` and
    computed BEFORE the `cd "$ROOT"`, exactly as the twin computes it. `rediacc_ci.paths.repo_root()` is deliberately not used: it honours `$REDIACC_CI_ROOT` and the twin honours nothing, and a boundary script that could be pointed at a different validator by an environment variable would not be a boundary.
    """
    return pathlib.Path(__file__).resolve().parents[3] / ".ci" / "scripts" / "autopilot"


def _flush() -> None:
    """Both streams, before every child. The children inherit fd 1 and fd 2, and Python block-buffers stdout when it is a pipe -- so without this the tripwire's quiet line would overtake a `log_info` written before it."""
    sys.stdout.flush()
    sys.stderr.flush()


def _run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    _flush()
    return subprocess.run(argv, check=False, **kwargs)


def _capture(argv: list[str], *, quiet: bool = False) -> tuple[int, str]:
    """`$(cmd)`: stdout captured with trailing newlines stripped, stderr INHERITED (or discarded when the twin wrote `2>/dev/null`)."""
    proc = _run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL if quiet else None,
    )
    return proc.returncode, (proc.stdout or b"").decode("utf-8", "surrogateescape").rstrip("\n")


def _capture_or_exit(argv: list[str]) -> str:
    """`x="$(cmd)"` under `set -e`: the ASSIGNMENT's status ends the run."""
    rc, out = _capture(argv)
    if rc != 0:
        raise _Exit(rc)
    return out


def _jq_capture_or_exit(program: str, path: str) -> str:
    rc, out = _capture(["jq", "-r", program, path])
    if rc != 0:
        raise _Exit(rc)
    return out


def _jq_to_file(args: list[str], target: str) -> None:
    """`jq -r ... >"$target"` under `set -e`.

    The target holds whatever jq produced BEFORE it failed, because that is what a shell redirection does: the file is open and being written as jq runs.
    """
    with open(target, "wb") as handle:
        proc = _run(["jq", *args], stdout=handle)
    if proc.returncode != 0:
        raise _Exit(proc.returncode)


def read_lines(path: str) -> list[str]:
    """`while IFS= read -r f; do ... done <"$file"`.

    A FINAL UNTERMINATED LINE IS DROPPED, which is `read`'s rule: it returns non-zero at EOF and the loop body does not run for it. Every file read this way here is written by `jq -r`, which always terminates its last line, so the quirk is unreachable -- reproduced anyway, because the day something else writes one of these files is the day it matters.
    """
    with open(path, "rb") as handle:
        data = handle.read()
    return [line.decode("utf-8", "surrogateescape") for line in data.split(b"\n")[:-1]]


def submodule_toplevel_matches(root: str, sub: str) -> tuple[bool, str]:
    """Is `<root>/<sub>` ITS OWN git checkout? (ok, the toplevel git reported).

    `git -C <dir> rev-parse --show-toplevel` and a PHYSICAL path comparison (`cd ... && pwd -P`, i.e. symlinks resolved on both sides). `--git-dir` would be the wrong question: git walks UP, so inside an uninitialized submodule it answers with the PARENT's git dir and every command after that runs against console one directory down. See the module docstring.

    Exported so the differential can drive it against a real uninitialized directory without having to reach the staging code behind it.
    """
    subdir = os.path.join(root, sub)
    _, top = _capture(["git", "-C", subdir, "rev-parse", "--show-toplevel"], quiet=True)
    if not top:
        return False, ""
    try:
        same = os.path.realpath(top) == os.path.realpath(subdir)
    except OSError:
        same = False
    return same, top


def tripwire_argv(script_directory: pathlib.Path, diff_path: str, failed_jobs: str) -> list[str]:
    """`node exfil-tripwire.cjs --diff <f> ${FAILED_JOBS:+--failed-jobs "$F"}`.

    The `${x:+word}` expansion is unquoted BUT the inner `"$FAILED_JOBS"` keeps
    its quotes, so a path with a space is ONE argument, not two (driven against bash 5.3.9). An empty value contributes nothing at all -- not an empty argument -- which is why the flag cannot arrive with a blank value.
    """
    argv = ["node", str(script_directory / "exfil-tripwire.cjs"), "--diff", diff_path]
    if failed_jobs:
        argv += ["--failed-jobs", failed_jobs]
    return argv


def _diff_u(declared: str, staged: str) -> bool:
    """`diff -u "$declared" "$staged" >&2`. True when they are equal.

    STDOUT GOES TO FD 2 on purpose: the unified diff is the operator's evidence
    for a staged-set mismatch, and it belongs on the same stream as the refusal
    that follows it.
    """
    proc = _run(["diff", "-u", declared, staged], stdout=2)
    return proc.returncode == 0


def _sorted_file(source: str, target: str) -> None:
    """`LC_ALL=C sort "$source" >"$target"`."""
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    with open(target, "wb") as handle:
        proc = _run(["sort", source], stdout=handle, env=env)
    if proc.returncode != 0:
        raise _Exit(proc.returncode)


def _staged_names_sorted(target: str, cwd: str | None = None) -> None:
    """`git diff --cached --name-only | LC_ALL=C sort >"$target"`, a `pipefail`
    pipeline: the RIGHTMOST non-zero status wins, which is why `sort` is checked before `git` below and not after."""
    argv = ["git"] + (["-C", cwd] if cwd is not None else []) + ["diff", "--cached", "--name-only"]
    proc = _run(argv, stdout=subprocess.PIPE)
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    with open(target, "wb") as handle:
        srt = _run(["sort"], input=proc.stdout or b"", stdout=handle, env=env)
    if srt.returncode != 0:
        raise _Exit(srt.returncode)
    if proc.returncode != 0:
        raise _Exit(proc.returncode)


class Push:
    """One invocation. The instance attributes are the twin's globals."""

    def __init__(self, args: dict[str, str], workdir: str) -> None:
        self.root = args.get("ARG_ROOT", "")
        self.handoff = args.get("ARG_HANDOFF", "")
        self.branch = args.get("ARG_BRANCH", "")
        self.remote = args.get("ARG_REMOTE", "") or "origin"
        self.failed_jobs = args.get("ARG_FAILED_JOBS", "")
        self.verdict_out = args.get("ARG_VERDICT_OUT", "")
        self.dry_run = args.get("ARG_DRY_RUN", "false") == "true"
        self.workdir = workdir
        self.script_dir = script_dir()
        self.sub_allowed = os.environ.get(ALLOW_SUBMODULES_ENV, "") == ALLOW_VALUE
        self.git_name = ""
        self.git_email = ""
        self.adopted_sha = ""

    # -- paths inside the work directory -----------------------------------
    def w(self, name: str) -> str:
        return os.path.join(self.workdir, name)

    # -- phase 0: validate --------------------------------------------------
    def validate(self) -> str:
        """Capture the tree's real status, hand it to the validator, publish the verdict, and return the outcome.

        THE STATUS CAPTURE IS TAKEN HERE, BY THE HARNESS, so the validator judges REALITY rather than anything the model asserted about it. Passing it as a file is what keeps the validator pure and offline-testable.
        """
        with open(self.w("status.z"), "wb") as handle:
            proc = _run(["git", "status", "--porcelain=v1", "-z"], stdout=handle)
        if proc.returncode != 0:
            raise _Exit(proc.returncode)

        # `$(git rev-parse HEAD)` inside an argument: `set -e` does not reach into it, so an empty answer is passed on and the validator refuses it.
        _, base_head = _capture(["git", "rev-parse", "HEAD"])

        with open(self.w("verdict.json"), "wb") as handle:
            proc = _run(
                [
                    "node",
                    str(self.script_dir / "validate-handoff.cjs"),
                    "--handoff",
                    self.handoff,
                    "--root",
                    self.root,
                    "--base-head",
                    base_head,
                    "--allow-submodules",
                    "true" if self.sub_allowed else "false",
                    "--status",
                    self.w("status.z"),
                ],
                stdout=handle,
            )
        if proc.returncode != 0:
            log.error("handoff rejected; escalating (nothing staged, nothing pushed)")
            raise _Exit(1)

        # Published BEFORE any outcome branching, so the workflow's post-boundary steps see the same validated object on every accepted round -- push, escalate and no-change alike.
        if self.verdict_out:
            # `cat "$workdir/verdict.json" >"$VERDICT_OUT"`, and it is a PLAIN OPEN-AND-WRITE rather than `shutil.copyfile` on purpose: `copyfile` raises `SpecialFileError` on a fifo, so `--verdict-out /dev/stdout` -- which is what a workflow step does when it wants the verdict in the log -- would have died where the twin happily writes. Found by driving exactly that argument.
            #
            # A target that cannot be opened is bash's own redirection error and exit 1; the code is reproduced, the message is Python's, because bash's names the twin's own line number. Named, not hidden.
            try:
                with open(self.w("verdict.json"), "rb") as source:
                    payload = source.read()
                with open(self.verdict_out, "wb") as target:
                    target.write(payload)
            except OSError as exc:
                log.error("verdict-out-unwritable: %s: %s" % (self.verdict_out, exc.strerror))
                raise _Exit(1) from exc

        return _jq_capture_or_exit(OUTCOME_PROGRAM, self.w("verdict.json"))

    # -- phase 1: submodule commits ----------------------------------------
    def submodule_phase(self) -> None:
        with open(self.w("sub-shas.txt"), "wb"):
            pass
        raw_count = _jq_capture_or_exit(SUB_COUNT_PROGRAM, self.w("verdict.json"))
        if not COUNT_RE.match(raw_count):
            # See the module docstring: unreachable through the validator, and a refusal rather than the twin's arithmetic-error walk-on.
            log.error(
                "verdict-count-unusable: the validated verdict's submodules[] length is "
                "'%s', not a non-negative integer; refusing to stage anything" % raw_count
            )
            raise _Exit(1)
        sub_count = int(raw_count)

        if sub_count > 0 and not self.sub_allowed:
            # BELT AND BRACES: the validator already refused submodules[] when the flag is off. This is the same refusal at the WRITE SITE, because the two are separated by a process boundary and the one that stages bytes should not depend on the other having run.
            log.error(
                "stage-flag-disabled: %s is not 'true'; refusing %d submodule change(s) "
                "(fail closed)" % (ALLOW_SUBMODULES_ENV, sub_count)
            )
            raise _Exit(1)

        for index in range(sub_count):
            self._one_submodule(index)

    def _one_submodule(self, index: int) -> None:
        sub = _jq_capture_or_exit(".submodules[%d].path" % index, self.w("verdict.json"))
        subdir = os.path.join(self.root, sub)

        # BELT AND BRACES, AND CURRENTLY UNREACHABLE -- said plainly so nobody mistakes it for a live control or deletes it as dead code. Both routes to an absent submodule are stopped earlier: an uninitialized one makes the parent report NOTHING dirty at that path (path-not-dirty), and a broken `gitdir:` pointer makes the parent's own `git status` fatal, so the run dies at the
        # status capture. Measured on git 2.43, both directions. It stays because the outcome it prevents (submodule content committed into console as ordinary files) is severe.
        if not os.path.isdir(subdir):
            log.error("submodule-missing: '%s' is not a directory in this checkout" % sub)
            raise _Exit(1)
        ok, sub_top = submodule_toplevel_matches(self.root, sub)
        if not ok:
            log.error(
                "submodule-not-initialized: '%s' is not its own git checkout here (toplevel "
                "resolves to '%s'); refusing rather than committing submodule content into "
                "the parent" % (sub, sub_top or "<none>")
            )
            raise _Exit(1)

        # THE BASE IS CURRENT HEAD, NOT origin/main. Section 5's anti-rollback rule is ancestry: only a descendant of the pointer the parent recorded may ever be committed. Branching at the recorded pointer makes that true by construction; branching at origin/main would silently rebase the round's work onto a different base, which is precisely the "stale checkout" case the design
        # says must commit nothing.
        sub_branch = _capture_or_exit(["git", "-C", subdir, "rev-parse", "--abbrev-ref", "HEAD"])
        if self.branch in FORBIDDEN_BRANCHES:
            log.error(
                "submodule-branch-forbidden: the autopilot never pushes '%s' in '%s'"
                % (self.branch, sub)
            )
            raise _Exit(1)
        if sub_branch != self.branch:
            proc = _run(
                [
                    "git",
                    "-C",
                    subdir,
                    "show-ref",
                    "--verify",
                    "--quiet",
                    "refs/heads/%s" % self.branch,
                ]
            )
            if proc.returncode == 0:
                # Checking it out would move HEAD across a tree the model has already edited. Refuse rather than guess which side wins.
                log.error(
                    "submodule-branch-exists: '%s' already has a local '%s' but HEAD is on "
                    "'%s'; refusing to move HEAD across the round's edits"
                    % (sub, self.branch, sub_branch)
                )
                raise _Exit(1)
            proc = _run(["git", "-C", subdir, "checkout", "-q", "-b", self.branch])
            if proc.returncode != 0:
                raise _Exit(proc.returncode)
        sub_base = _capture_or_exit(["git", "-C", subdir, "rev-parse", "HEAD"])

        # Stage exactly the declared files, one path at a time, then prove the staged set equals the declared set -- the identical check the console boundary applies, because a pathspec that expands is the same bug here.
        _jq_to_file(
            ["-r", ".submodules[%d].files[]" % index, self.w("verdict.json")],
            self.w("sub-files.txt"),
        )
        for entry in read_lines(self.w("sub-files.txt")):
            if not entry:
                continue
            # A path git has never heard of AND that is not on disk is one `git add` would die on with a bare `fatal: pathspec`. Naming the
            # class here keeps a mistyped path diagnosable. A DELETED file is
            # still known to git, so this does not reject a legitimate removal.
            known = (
                _run(
                    ["git", "-C", subdir, "ls-files", "--error-unmatch", "--", entry],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ).returncode
                == 0
            )
            if not known and not os.path.exists(os.path.join(subdir, entry)):
                log.error(
                    "submodule-path-missing: '%s/%s' is declared but is neither tracked in "
                    "the submodule nor present on disk" % (sub, entry)
                )
                raise _Exit(1)
            proc = _run(["git", "-C", subdir, "add", "--", entry])
            if proc.returncode != 0:
                raise _Exit(proc.returncode)

        _staged_names_sorted(self.w("sub-staged.txt"), cwd=subdir)
        _sorted_file(self.w("sub-files.txt"), self.w("sub-declared.txt"))
        if not _diff_u(self.w("sub-declared.txt"), self.w("sub-staged.txt")):
            log.error(
                "submodule-staged-set-mismatch: '%s' staged set does not equal the validated "
                "files[]; refusing to commit" % sub
            )
            raise _Exit(1)

        # THE PATHS ARE REWRITTEN PARENT-RELATIVE. Without the prefixes the tripwire would see `pkg/x.go`, match no module prefix, and treat every byte as out of scope; with them it sees `private/renet/pkg/x.go` and the same scope map that governs a console fix governs this one.
        with open(self.w("sub-staged.diff"), "wb") as handle:
            proc = _run(
                [
                    "git",
                    "-C",
                    subdir,
                    "diff",
                    "--cached",
                    "--src-prefix=a/%s/" % sub,
                    "--dst-prefix=b/%s/" % sub,
                ],
                stdout=handle,
            )
        if proc.returncode != 0:
            raise _Exit(proc.returncode)
        trip = _run(tripwire_argv(self.script_dir, self.w("sub-staged.diff"), self.failed_jobs))
        if trip.returncode != 0:
            log.error(
                "tripwire tripped in submodule '%s'; escalating (nothing committed there, "
                "nothing pushed)" % sub
            )
            raise _Exit(1)

        # `-F` from a file: no shell interpolation of model text, here or on the console commit below.
        _jq_to_file(
            ["-r", ".submodules[%d].message" % index, self.w("verdict.json")], self.w("sub-msg.txt")
        )
        proc = _run(self.commit_argv(subdir, self.w("sub-msg.txt")))
        if proc.returncode != 0:
            raise _Exit(proc.returncode)
        sub_sha = _capture_or_exit(["git", "-C", subdir, "rev-parse", "HEAD"])

        # Ancestry, ASSERTED rather than assumed. It holds by construction today; it is checked so that a future change to the base above cannot quietly publish a pointer that rolls the submodule backwards.
        anc = _run(["git", "-C", subdir, "merge-base", "--is-ancestor", sub_base, sub_sha])
        if anc.returncode != 0:
            log.error(
                "submodule-pointer-rollback: '%s' new commit %s is not a descendant of the "
                "recorded pointer %s; refusing" % (sub, sub_sha, sub_base)
            )
            raise _Exit(1)

        with open(self.w("sub-shas.txt"), "a", encoding="utf-8") as handle:
            handle.write("%s %s %s\n" % (sub, sub_sha, sub_base))

    def commit_argv(self, cwd: str | None, message_file: str) -> list[str]:
        argv = ["git"]
        if cwd is not None:
            argv += ["-C", cwd]
        argv += [
            "-c",
            "user.name=%s" % self.git_name,
            "-c",
            "user.email=%s" % self.git_email,
            "commit",
            "-F",
            message_file,
            "--quiet",
        ]
        return argv

    def sub_shas(self) -> list[tuple[str, str, str]]:
        """`while read -r sub sub_sha sub_base` over sub-shas.txt.

        Three whitespace-separated fields; the last one absorbs the remainder, which is `read`'s rule and matters not at all for shas but is preserved.
        """
        rows = []
        for line in read_lines(self.w("sub-shas.txt")):
            parts = line.split(None, 2)
            if not parts or not parts[0]:
                continue
            while len(parts) < 3:
                parts.append("")
            rows.append((parts[0], parts[1], parts[2]))
        return rows

    # -- phase 2: the console side -----------------------------------------
    def stage_and_validate_console(self) -> None:
        for entry in read_lines(self.w("files.txt")):
            if not entry:
                continue
            proc = _run(["git", "add", "--", entry])
            if proc.returncode != 0:
                raise _Exit(proc.returncode)

        # Staged-set equality: what git staged must be byte-for-byte the declared list. Any divergence (a pathspec that expanded, an index surprise) aborts.
        _staged_names_sorted(self.w("staged.txt"))
        if not _diff_u(self.w("declared.txt"), self.w("staged.txt")):
            log.error(
                "staged-set-mismatch: the staged set does not equal the validated files[]; "
                "refusing to commit"
            )
            raise _Exit(1)

        # THE POINTER ADVANCE, VERIFIED IN THE INDEX rather than trusted. `git add` on a submodule path stages whatever the submodule's HEAD happens to be, so this proves the console commit about to be minted names exactly the SHA this round produced, at mode 160000 -- a gitlink, not a directory of files someone flattened into the parent.
        for sub, sub_sha, _base in self.sub_shas():
            _, entry = _capture(["git", "ls-files", "-s", "--", sub])
            # A VACUOUS `git ls-files` -- the submodule not staged at all -- is already fatal two lines down: staged_mode is empty, the 160000 test fails, and the error prints "<absent>". The floor is that test; naming it here so a reader (and check:ci-enumeration-vacuity) can see the empty case is handled.
            fields = entry.split()
            staged_mode = fields[0] if fields else ""
            staged_sha = fields[1] if len(fields) > 1 else ""
            if staged_mode != "160000":
                log.error(
                    "gitlink-not-staged: '%s' is staged as mode '%s', not a 160000 gitlink; "
                    "refusing to commit" % (sub, staged_mode or "<absent>")
                )
                raise _Exit(1)
            if staged_sha != sub_sha:
                log.error(
                    "gitlink-sha-mismatch: '%s' is staged at %s but this round produced %s; "
                    "refusing to commit a pointer to a different commit"
                    % (sub, staged_sha, sub_sha)
                )
                raise _Exit(1)
            log.info("gitlink verified: %s -> %s" % (sub, sub_sha))

        # Tripwire on the exact bytes about to be committed, BEFORE any commit.
        with open(self.w("staged.diff"), "wb") as handle:
            proc = _run(["git", "diff", "--cached"], stdout=handle)
        if proc.returncode != 0:
            raise _Exit(proc.returncode)
        trip = _run(tripwire_argv(self.script_dir, self.w("staged.diff"), self.failed_jobs))
        if trip.returncode != 0:
            log.error("tripwire tripped; escalating (nothing committed, nothing pushed)")
            raise _Exit(1)

    # -- phase 3: the pushes ------------------------------------------------
    def adopt_or_refuse(self, sub: str, subdir: str, sha: str, base: str) -> None:
        """Handle a non-fast-forward on a submodule branch.

        THE ORPHAN CASE IS OURS TO CLEAN UP. A previous round can leave a submodule branch pushed while its console half never landed (the old ordering did exactly this, and a cancelled run can still do it). The next round then builds on the recorded pointer and its push is rejected as non-fast-forward BY A COMMIT THIS SYSTEM WROTE. Refusing there strands the campaign on a branch
        only a human can unpick, so the harness rebuilds its work on top of the orphan instead -- but only when the orphan is
        PROVABLY OURS.

        "Ours" is two independent facts, BOTH REQUIRED: the tip's committer email is the autopilot identity, and the tip shares its merge-base with origin/main with the base we branched from. The first says the autopilot wrote it; the second says it is a continuation of this line of work rather than an unrelated branch that happens to sit at the same name. A tip failing either is
        somebody else's work and the round stops rather than rewriting it.
        """
        log.warn(
            "submodule '%s': push rejected as non-fast-forward; inspecting the remote tip "
            "before deciding" % sub
        )
        proc = _run(["git", "-C", subdir, "fetch", "-q", self.remote, self.branch])
        if proc.returncode != 0:
            raise _Exit(proc.returncode)
        tip = _capture_or_exit(["git", "-C", subdir, "rev-parse", "FETCH_HEAD"])
        tip_email = _capture_or_exit(["git", "-C", subdir, "log", "-1", "--format=%ce", tip])
        if tip_email != self.git_email:
            log.error(
                "submodule-foreign-branch: '%s' branch '%s' already exists at %s, committed "
                "by '%s' rather than the autopilot identity '%s'; refusing to rewrite someone "
                "else's branch" % (sub, self.branch, tip, tip_email, self.git_email)
            )
            raise _Exit(1)
        main_ref = "%s/main" % self.remote
        # BOTH CHECKS ARE REQUIRED, so an unresolvable main is a REFUSAL, not a skip. The identity check alone is the weaker guard (a committer email is forgeable by anyone who can push), and the checkout mechanics that leave main unfetched here are exactly the ones nobody exercises -- failing closed is the only reading under which "both required" is true.
        if not self._ref_exists(subdir, main_ref):
            _run(
                [
                    "git",
                    "-C",
                    subdir,
                    "fetch",
                    "-q",
                    self.remote,
                    "main:refs/remotes/%s/main" % self.remote,
                ],
                stderr=subprocess.DEVNULL,
            )
        if not self._ref_exists(subdir, main_ref):
            log.error(
                "submodule-main-unresolvable: '%s' has no resolvable %s even after a fetch, "
                "so the ancestry half of the adoption check cannot run; refusing to adopt on "
                "the identity check alone" % (sub, main_ref)
            )
            raise _Exit(1)
        _, base_mb = _capture(["git", "-C", subdir, "merge-base", base, main_ref], quiet=True)
        _, tip_mb = _capture(["git", "-C", subdir, "merge-base", tip, main_ref], quiet=True)
        if not tip_mb or tip_mb != base_mb:
            log.error(
                "submodule-unrelated-branch: '%s' remote tip %s does not share this round's "
                "merge-base with %s (tip: %s, ours: %s); refusing to build on an unrelated "
                "history" % (sub, tip, main_ref, tip_mb or "<none>", base_mb or "<none>")
            )
            raise _Exit(1)
        log.warn(
            "submodule '%s': the remote tip %s is an autopilot orphan; rebuilding this "
            "round's commit on top of it" % (sub, tip)
        )
        # The message is looked up BY PATH rather than by a positional index two separate loops would have to keep in agreement.
        _jq_to_file(
            ["-r", "--arg", "p", sub, ADOPT_MESSAGE_PROGRAM, self.w("verdict.json")],
            self.w("adopt-msg.txt"),
        )
        proc = _run(["git", "-C", subdir, "checkout", "-q", "-B", self.branch, tip])
        if proc.returncode != 0:
            raise _Exit(proc.returncode)
        pick = _run(
            ["git", "-C", subdir, "cherry-pick", "--no-commit", sha],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if pick.returncode != 0:
            _run(
                ["git", "-C", subdir, "cherry-pick", "--abort"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log.error(
                "submodule-adopt-conflict: '%s' this round's commit does not apply cleanly on "
                "top of %s; a human must reconcile the branch" % (sub, tip)
            )
            raise _Exit(1)
        proc = _run(self.commit_argv(subdir, self.w("adopt-msg.txt")))
        if proc.returncode != 0:
            raise _Exit(proc.returncode)
        self.adopted_sha = _capture_or_exit(["git", "-C", subdir, "rev-parse", "HEAD"])
        proc = _run(
            [
                "git",
                "-C",
                subdir,
                "push",
                self.remote,
                "%s:refs/heads/%s" % (self.adopted_sha, self.branch),
            ]
        )
        if proc.returncode != 0:
            raise _Exit(proc.returncode)
        log.info(
            "adopted the orphan in '%s': pushed %s to %s refs/heads/%s"
            % (sub, self.adopted_sha, self.remote, self.branch)
        )

    def _ref_exists(self, subdir: str, ref: str) -> bool:
        return (
            _run(
                ["git", "-C", subdir, "rev-parse", "--verify", "--quiet", ref],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )

    def push_submodules(self) -> bool:
        """Returns whether an adoption happened."""
        if self.dry_run:
            for sub, sub_sha, _base in self.sub_shas():
                log.info(
                    "dry-run: would push %s to %s refs/heads/%s in '%s'"
                    % (sub_sha, self.remote, self.branch, sub)
                )
            return False

        adoption_happened = False
        pushed: list[str] = []
        for sub, sub_sha, sub_base_recorded in self.sub_shas():
            subdir = os.path.join(self.root, sub)
            self.adopted_sha = ""
            pushed_sha = sub_sha
            with open(self.w("push-err.txt"), "wb") as handle:
                proc = _run(
                    [
                        "git",
                        "-C",
                        subdir,
                        "push",
                        self.remote,
                        "%s:refs/heads/%s" % (sub_sha, self.branch),
                    ],
                    stderr=handle,
                )
            if proc.returncode == 0:
                log.info(
                    "pushed %s to %s refs/heads/%s in '%s'"
                    % (sub_sha, self.remote, self.branch, sub)
                )
            else:
                with open(self.w("push-err.txt"), "rb") as handle:
                    err = handle.read()
                _flush()
                sys.stderr.buffer.write(err)
                sys.stderr.buffer.flush()
                if not NON_FAST_FORWARD_RE.search(err.decode("utf-8", "replace")):
                    log.error(
                        "submodule-push-failed: '%s' push failed for a reason that is not a "
                        "non-fast-forward; refusing to guess" % sub
                    )
                    raise _Exit(1)
                self.adopt_or_refuse(sub, subdir, sub_sha, sub_base_recorded)
                # THE ADOPTED SHA REPLACES THE ONE PHASE 1 MINTED, and phase 4 re-stages the gitlink to match. A separate name rather than rebinding the loop variable, which reads the same and does not invite a reader to wonder which value the next line sees.
                pushed_sha = self.adopted_sha
                adoption_happened = True
            pushed.append("%s %s %s\n" % (sub, pushed_sha, sub_base_recorded))
        # `mv "$workdir/sub-shas.pushed" "$workdir/sub-shas.txt"`.
        with open(self.w("sub-shas.txt"), "w", encoding="utf-8") as handle:
            handle.write("".join(pushed))
        return adoption_happened


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    root = args.get("ARG_ROOT", "")
    handoff = args.get("ARG_HANDOFF", "")
    branch = args.get("ARG_BRANCH", "")
    dry_run = args.get("ARG_DRY_RUN", "false") == "true"

    if not (root and handoff and branch):
        log.error(USAGE)
        return 2
    try:
        common.require_dir(root)
    except common.RefusalError as exc:
        exc.report()
        return exc.code
    os.chdir(root)

    # STAGE FLAG, FAIL CLOSED: absent means off, and only the exact string `true` arms the push. A dry run needs no flag because it never writes the remote.
    if not dry_run and os.environ.get(ALLOW_PUSH_ENV, "") != ALLOW_VALUE:
        log.error(
            "stage-flag-disabled: %s is not 'true'; refusing to push (fail closed)" % ALLOW_PUSH_ENV
        )
        return 1

    workdir = tempfile.mkdtemp()
    push = Push(args, workdir)
    try:
        try:
            push.git_name = common.require_var("AUTOPILOT_GIT_NAME")
            push.git_email = common.require_var("AUTOPILOT_GIT_EMAIL")
        except common.RefusalError as exc:
            exc.report()
            return exc.code
        return _drive(push)
    except _Exit as exc:
        return exc.code
    finally:
        # `trap 'rm -rf "$workdir"' EXIT`.
        shutil.rmtree(workdir, ignore_errors=True)


def _drive(push: Push) -> int:
    # HARDCODED BRANCH CHECKS. The current branch must be exactly the one the caller named, and main/master are refused UNCONDITIONALLY: even a harness bug upstream must not be able to aim this script at a default branch (renet/account/elite have no rulesets, so this is their only guard).
    actual_branch = _capture_or_exit(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if actual_branch != push.branch:
        log.error(
            "branch-mismatch: checkout is on '%s', caller named '%s'; refusing"
            % (actual_branch, push.branch)
        )
        return 1
    if push.branch in FORBIDDEN_BRANCHES:
        log.error("branch-forbidden: the autopilot never pushes '%s'" % push.branch)
        return 1

    outcome = push.validate()
    if outcome in ("escalate", "no-change"):
        # Nothing staged, nothing committed, nothing pushed -- and NOT an error. A no-change round with a dirty tree never reaches here: the validator already refused it as undeclared-dirty.
        log.info(
            "outcome-%s: validated round, nothing staged and nothing pushed; the "
            "post-boundary steps own the follow-up" % outcome
        )
        return 0
    if outcome != "push":
        # Unreachable while the schema pins the enum; kept so a schema widening cannot silently reach the staging code below.
        log.error("outcome-unknown: handoff outcome is '%s'; refusing to stage anything" % outcome)
        return 1

    push.submodule_phase()

    _jq_to_file(["-r", FILES_PROGRAM, push.w("verdict.json")], push.w("files.txt"))
    _sorted_file(push.w("files.txt"), push.w("declared.txt"))
    push.stage_and_validate_console()
    log.info("all repos validated; nothing has been pushed yet")

    adoption_happened = push.push_submodules()

    # PHASE 4: an adoption moved a submodule SHA, so the gitlink console staged in phase 2 now names a commit that is no longer the branch tip. Re-stage and re-run the SAME validation rather than patching the index and trusting it.
    if adoption_happened:
        log.warn(
            "an orphan was adopted; re-staging the pointers and re-running the console validation"
        )
        for sub, _sha, _base in push.sub_shas():
            proc = _run(["git", "add", "--", sub])
            if proc.returncode != 0:
                raise _Exit(proc.returncode)
        push.stage_and_validate_console()

    # Commit message via -F from a file: no shell interpolation of model text.
    _jq_to_file(["-r", COMMIT_MESSAGE_PROGRAM, push.w("verdict.json")], push.w("msg.txt"))
    proc = _run(push.commit_argv(None, push.w("msg.txt")))
    if proc.returncode != 0:
        raise _Exit(proc.returncode)

    sha = _capture_or_exit(["git", "rev-parse", "HEAD"])
    if push.dry_run:
        log.info("dry-run: would push %s to %s refs/heads/%s" % (sha, push.remote, push.branch))
        _flush()
        print(sha, flush=True)
        return 0

    # PUSH BY EXPLICIT SHA, never a bare branch name: the ref that leaves this machine is exactly the commit minted above.
    proc = _run(["git", "push", push.remote, "%s:refs/heads/%s" % (sha, push.branch)])
    if proc.returncode != 0:
        raise _Exit(proc.returncode)
    log.info("pushed %s to %s refs/heads/%s" % (sha, push.remote, push.branch))
    _flush()
    print(sha, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
