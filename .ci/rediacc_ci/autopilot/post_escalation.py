#!/usr/bin/env python3
"""Port of `.ci/scripts/autopilot/post-escalation.sh`.

Posts ONE escalation comment on the PR and latches the loop with the `autopilot-blocked` label. Every way an autopilot campaign can stop ends here, which is the whole reason the script exists: before it, an escalating round painted the job red and applied a wordless label, so the operator's first signal was "nothing is happening any more" and the model's reason -- the entire
payload of an escalation -- stayed in a run log nobody was told to open.

THE BODY IS THE PRODUCT. Almost nothing this script does is visible in its exit code: the words an operator reads at the moment a campaign stops are the output, and `--dry-run` exists so those words can be exercised offline. The differential therefore compares the BODY BYTES that would have gone to GitHub, not just the verdict, on every case.

-----------------------------------------------------------------------------
TWO WRITES, IN ORDER, AND THE ORDER IS THE LATCH
-----------------------------------------------------------------------------
The comment goes first, the label second. A failed comment write means `set -e` ends the run before the label is applied, so the loop is NOT latched and the next round retries -- which is right, because a latch with no explanation attached is exactly the silent stop this script was built to end. `--no-label` skips only the second write, and the dry-run message says which of the two
behaviours it would have taken.

-----------------------------------------------------------------------------
MODEL TEXT NEVER BECOMES SHELL, AND THE PORT KEEPS THAT PROPERTY STRUCTURALLY
-----------------------------------------------------------------------------
The reason and the patch are extracted with `jq` straight into a file and the
comment is posted with `-F body=@<file>`. Nothing model-authored is ever
interpolated into a command line, here or in the twin. In Python the argv is a list, so the property holds by construction, but the FILE is kept rather than
switched to `-f body=<text>`: a 20 KB patch as an argv value is a length limit
waiting to truncate an escalation.

-----------------------------------------------------------------------------
`jq` IS SPAWNED, THREE TIMES, FOR THE REASON THIS WAVE KEEPS REPEATING
-----------------------------------------------------------------------------
The `--verdict` file is `autopilot-push.sh --verdict-out`, it comes from outside, and a truncated one is a real shape. When it is truncated the observable is JQ's parse error, JQ's exit code (5, measured on 1.8.1) and a PARTIALLY WRITTEN body
file -- because the twin's `{ ... } >"$work/body.md"` group has the file open
while jq runs. None of that is reproducible by hand, so the three jq programs
are handed to jq, with their stdout pointed at the same open handle.

  THE `//` IS LOAD-BEARING AND IS NOT `or`: `.escalation.reason // "The round
  escalated without recording a reason."` treats `null` AND `false` as absent,
  which is jq's rule and not Python's. Reimplementing it would mean re-deriving
  that rule, and the first time it was got wrong an escalation would post an
  empty reason.

-----------------------------------------------------------------------------
THE FENCE IS SIZED TO THE CONTENT, and this is a security property, not a typographic one. A proposed patch touching a markdown file can itself contain a
``` run; a fixed three-backtick fence would CLOSE early and the remainder of the
patch -- untrusted, model-authored text -- would be promoted from a code block into live markdown. CommonMark closes a fence only on a run at least as long as the opening one, so the twin measures the longest backtick run in the patch and opens with one longer. `longest_backtick_run` below is that measurement, exported so the differential can drive it without a PR.

  `{ grep -oE '`+' || true; }` IS NOT DECORATION: a patch with no backticks is
  the common case, grep exits 1 on no match, and `pipefail` would turn the
  ordinary case into a failed escalation. The port has no pipeline, so the
  equivalent statement is that "no matches" yields 0 and never an error.

-----------------------------------------------------------------------------
ONE HAZARD, REPORTED RATHER THAN REPAIRED, and it is the same shape `update_state.py` reports: `--verdict` is checked with `[[ -n && -s ]]`, never
with `require_file`. A MISTYPED VERDICT PATH IS THEREFORE SILENT -- the script
falls through to `--reason`, or to the step class, and posts an escalation whose reason is missing entirely. That is the model's own words going quietly absent at the one moment they matter. Fixing it means changing a live workflow step's contract, which is the cutover box's call rather than this one's. Pinned by `test_a_mistyped_verdict_path_is_silent`.

A SECOND, SMALLER ONE, ALSO PRESERVED: `--steps` pairs are compared with
`${pair#*=} == "failure"`, and `${pair#*=}` returns the WHOLE token when there
is no `=` in it. So the bare word `failure` in the steps list matches, and
`${pair%%=*}` then hands `failure` to the step-class map, which has no entry for
it and echoes it back. The comment then reads "The round failed in failure." Pinned by `test_a_bare_failure_token_names_itself`.

`gh_retry` IS TRANSLITERATED, NOT IMPORTED, sleeps included. See `update_state.py`'s docstring for the reasoning and the prior copies: `core.ghx` classifies failures and raises typed errors instead of looping three times with a `log_warn` between attempts, so a port built on it would produce different output on the paths a differential cannot reach.

Exit: 0 posted or dry-run, 1 refused or a write failed, 2 usage, and jq's own status when the verdict will not parse.

K=5 LEDGER: `.ci/shadow/w7p6-post-escalation.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "post-escalation.py"

USAGE = (
    "usage: post-escalation.sh --pr <n> --repo <owner/name> --title <text> "
    "[--verdict <file>] [--reason <text>] [--steps <k=v,...>] [--run-url <url>] "
    "[--round <r>] [--no-label]"
)

# `AUTOPILOT_ALLOW_STATE` must be exactly this. Absent is off, fail closed.
ALLOW_ENV = "AUTOPILOT_ALLOW_STATE"
ALLOW_VALUE = "true"

# `_gh_probe`: three attempts, sleeping 3 then 6 seconds.
GH_ATTEMPTS = 3

# The step-class map, in the twin's order. A key with no entry here is reported by its RAW key, so a new stage is never silently unnameable -- that fallback is the `*)` arm and it is deliberate, not a gap.
STEP_CLASSES = {
    "restore": (
        "the trusted-config assert (wall 4): the PR branch's agent config "
        "did not match the trusted snapshot"
    ),
    "model": "the model step itself (turn cap, timeout, or a hard error)",
    "boundary": (
        "the harness boundary: the handoff validator or the exfiltration tripwire refused the round"
    ),
    "escalation": "posting the escalation comment",
    "reply": "answering and resolving the review threads",
    "state": "the state-comment write",
    "submodules": "the submodule push path",
}

NO_FAILURE = "an unclassified step (no step reported a failure conclusion)"

# The two jq programs the body is built from, byte for byte from the twin.
REASON_PROGRAM = '.escalation.reason // "The round escalated without recording a reason."'
PATCH_LENGTH_PROGRAM = '(.escalation.patch // "") | length'
PATCH_PROGRAM = ".escalation.patch"

# `${pair//[[:space:]]/}` in the C locale: space, tab, newline, vertical tab,
# form feed, carriage return. Not Python's `str.strip`, which also eats U+00A0 and friends once the string is text.
BASH_SPACE_RE = re.compile(r"[ \t\n\v\f\r]")

# `grep -oE '`+'`: every maximal run of backticks.
BACKTICK_RUN_RE = re.compile(r"`+")

MIN_FENCE = 3


def step_class(key: str) -> str:
    """`step_class` (post-escalation.sh:71-82). Unknown keys echo themselves."""
    return STEP_CLASSES.get(key, key)


def failed_class(steps: str) -> str:
    """The FIRST `key=failure` pair names the failed class; otherwise the
    unclassified sentinel.

    THE TWO QUIRKS ARE THE TWIN'S, and both are reproduced rather than tidied:

      * whitespace is stripped from ANYWHERE in the pair, not merely trimmed, so
        `model = failure` and `mo del=failure` both parse (the second as the key
        `model`). `${pair//[[:space:]]/}` is a global substitution.
      * `${pair#*=}` returns the WHOLE token when it holds no `=`, so the bare
        word `failure` matches the test, and `${pair%%=*}` then hands `failure`
        to the map as a key. See the module docstring.

    An empty pair (a doubled comma, a trailing one) is skipped, which is why a steps string of `,,,` is not an error.
    """
    if not steps:
        return NO_FAILURE
    for raw in steps.split(","):
        pair = BASH_SPACE_RE.sub("", raw)
        if not pair:
            continue
        # `${pair#*=}`: shortest prefix through the first `=`, or the whole
        # string when there is none.
        after = pair.split("=", 1)[1] if "=" in pair else pair
        if after == "failure":
            # `${pair%%=*}`: longest suffix from the first `=`, or the whole
            # string when there is none.
            return step_class(pair.split("=", 1)[0] if "=" in pair else pair)
    return NO_FAILURE


def longest_backtick_run(patch: bytes) -> int:
    """`jq -r .escalation.patch | { grep -oE '`+' || true; } | awk '...'`.

    Returns the length of the longest run of backticks in the patch, or 0 when there is none -- the `|| true` case, which is the COMMON case and must never be an error.

    Measured in BYTES on purpose: a backtick is one byte in UTF-8 and grep -o counts bytes, so there is no locale question here, unlike `state-comment.sh`'s line cap.
    """
    longest = 0
    for match in BACKTICK_RUN_RE.finditer(patch.decode("utf-8", "surrogateescape")):
        longest = max(longest, len(match.group(0)))
    return longest


def fence_for(longest: int) -> bytes:
    """`fence_len=3; ((longest >= fence_len)) && fence_len=$((longest + 1))`.

    Note the comparison is `>=`, not `>`: a patch containing exactly ``` gets a
    FOUR-backtick fence, because a three-backtick fence would be closed by it.
    """
    fence_len = MIN_FENCE
    if longest >= fence_len:
        fence_len = longest + 1
    return b"`" * fence_len


def gh_retry(what: str, args: list[str]) -> tuple[bool, bytes]:
    """`gh_retry <what> -- <gh args...>`. Returns (ok, stdout bytes).

    The exit status is ALWAYS checked and a failure is never turned into an empty answer (`.ci/scripts/lib/common.sh:392-397`). Both call sites here redirect stdout to /dev/null, so the bytes are returned only for symmetry
    with the other ports; what matters is the boolean and the stderr replay.
    """
    rc = 0
    stderr = b""
    stdout = b""
    for attempt in range(1, GH_ATTEMPTS + 1):
        try:
            proc = subprocess.run(["gh", *args], capture_output=True, check=False)
            rc = proc.returncode
            stdout = proc.stdout or b""
            stderr = proc.stderr or b""
        except OSError:
            # No `gh` on PATH: 127 is the shell's own status for it.
            rc, stdout, stderr = 127, b"", b""
        if rc == 0:
            # `$(...)` strips trailing newlines; `printf '%s'` adds none back.
            return True, stdout.rstrip(b"\n")
        if attempt < GH_ATTEMPTS:
            log.warn(
                "%s: gh call failed or returned unusable output (attempt %d/3), retrying..."
                % (what, attempt)
            )
            time.sleep(attempt * 3)
    log.error("%s: gh failed after %d attempts (last exit %d)." % (what, GH_ATTEMPTS, rc))
    if stderr:
        # `[[ -s "$err" ]] && sed 's/^/ /' "$err" >&2`. GNU sed does not invent a final newline the input did not have.
        text = stderr.decode("utf-8", "replace")
        parts = text.split("\n")
        incomplete = parts[-1] != ""
        if not incomplete:
            parts.pop()
        for index, line in enumerate(parts):
            tail = "" if incomplete and index == len(parts) - 1 else "\n"
            print("    %s" % line, end=tail, file=sys.stderr)
        sys.stderr.flush()
    return False, b""


def _jq_into(handle, program: str, path: str) -> int:
    """`jq -r '<program>' "$VERDICT"` with stdout pointed at the open body file.

    STDERR IS INHERITED so jq's own diagnostic lands on fd 2 in real time, and the handle is FLUSHED first so the bytes this process has already written stay ahead of the child's -- the twin has one shared file descriptor and no such ordering problem.
    """
    handle.flush()
    proc = subprocess.run(["jq", "-r", program, path], stdout=handle, check=False)
    return proc.returncode


def _jq_capture(program: str, path: str) -> tuple[int, bytes]:
    """`$(jq -r '<program>' "$VERDICT")`, stderr inherited."""
    proc = subprocess.run(
        ["jq", "-r", program, path],
        stdout=subprocess.PIPE,
        check=False,
    )
    return proc.returncode, (proc.stdout or b"").rstrip(b"\n")


def _usable_verdict(path: str) -> bool:
    """`[[ -n "$VERDICT" && -s "$VERDICT" ]]`. THE HAZARD, preserved.

    `-s` is TRUE for a non-empty file OR a directory, and FALSE for a path that does not exist -- so a mistyped path is silently "no verdict" rather than a refusal. See the module docstring.
    """
    if not path:
        return False
    try:
        return os.path.getsize(path) > 0
    except OSError:
        return False


def build_body(handle, args: dict[str, str], klass: str) -> int:
    """The `{ ... } >"$work/body.md"` group, in order. Returns an exit code.

    A NON-ZERO RETURN LEAVES A PARTIALLY WRITTEN BODY, exactly as the twin's `set -e` does: the redirection is already open, so whatever printf and jq emitted before the failure is on disk. Nothing downstream reads it in that
    case, but a port that buffered and discarded would leave a different file
    behind, and this file is the one artifact an operator is handed.
    """
    title = args.get("ARG_TITLE", "")
    verdict = args.get("ARG_VERDICT", "")
    reason = args.get("ARG_REASON", "")
    steps = args.get("ARG_STEPS", "")
    run_url = args.get("ARG_RUN_URL", "")
    round_ = args.get("ARG_ROUND", "")

    def out(text: str) -> None:
        handle.write(text.encode("utf-8", "surrogateescape"))

    out("### Autopilot escalation: %s\n\n" % title)
    if round_:
        out("Round %s. " % round_)
    out("The loop is latched; clear the `autopilot-blocked` label to resume.\n\n")

    have_verdict = _usable_verdict(verdict)
    if have_verdict:
        code = _jq_into(handle, REASON_PROGRAM, verdict)
        if code != 0:
            return code
        if steps:
            out("\nFailed step class: %s\n" % klass)
    elif reason:
        out("%s\n" % reason)
        if steps:
            out("\nFailed step class: %s\n" % klass)
    else:
        # With no verdict and no reason the step class IS the whole message, so printing it twice would be noise at the one moment the operator is scanning for what actually broke.
        out("The round failed in %s.\n" % klass)

    if have_verdict:
        # `[[ "$(jq ...)" != "0" ]]` sits inside `[[ ]]`, where `set -e` does
        # NOT apply: a jq failure here yields the empty string, which is `!= "0"`
        # and therefore ENTERS the patch block. Reproduced -- the next jq then fails the same way and takes the run with it, which is the twin's behaviour and not a smoothing opportunity.
        _, length = _jq_capture(PATCH_LENGTH_PROGRAM, verdict)
        if length != b"0":
            code, patch = _jq_capture(PATCH_PROGRAM, verdict)
            if code != 0:
                return code
            fence = fence_for(longest_backtick_run(patch))
            handle.write(
                b"\n<details><summary>Proposed patch (data, not applied)</summary>\n\n"
                + fence
                + b"diff\n"
            )
            # The twin runs jq a THIRD time here rather than reusing the
            # captured value; the bytes are the same because `$( )` stripped
            # only the trailing newlines jq's own `-r` added, and printing them back is what `jq -r ... >file` does.
            code = _jq_into(handle, PATCH_PROGRAM, verdict)
            if code != 0:
                return code
            handle.write(b"\n" + fence + b"\n\n</details>\n")

    if run_url:
        out("\nRun log: %s\n" % run_url)
    handle.flush()
    return 0


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    pr = args.get("ARG_PR", "")
    repo = args.get("ARG_REPO", "")
    title = args.get("ARG_TITLE", "")
    no_label = args.get("ARG_NO_LABEL", "false")
    dry_run = args.get("ARG_DRY_RUN", "false")

    # ORDER, KEPT: usage first, then the stage flag, so a broken invocation still gets the usage message rather than a confusing refusal.
    if not (pr and repo and title):
        log.error(USAGE)
        return 2
    if os.environ.get(ALLOW_ENV, "") != ALLOW_VALUE:
        log.error(
            "stage-flag-disabled: %s is not '%s'; refusing to comment or label (fail closed)"
            % (ALLOW_ENV, ALLOW_VALUE)
        )
        return 1

    klass = failed_class(args.get("ARG_STEPS", ""))

    work = tempfile.mkdtemp()
    try:
        return _post(args, pr, repo, no_label, dry_run, klass, work)
    finally:
        # `trap 'rm -rf "$work"' EXIT`.
        shutil.rmtree(work, ignore_errors=True)


def _post(
    args: dict[str, str],
    pr: str,
    repo: str,
    no_label: str,
    dry_run: str,
    klass: str,
    work: str,
) -> int:
    body_md = os.path.join(work, "body.md")
    with open(body_md, "wb") as handle:
        code = build_body(handle, args, klass)
    if code != 0:
        return code

    if dry_run == "true":
        # `cat "$work/body.md"` -- BYTES, because the body carries model-authored text that need not be valid UTF-8.
        sys.stdout.flush()
        with open(body_md, "rb") as handle:
            sys.stdout.buffer.write(handle.read())
        sys.stdout.buffer.flush()
        log.info(
            "dry-run: would comment on PR #%s and %s"
            % (pr, "leave the labels alone" if no_label == "true" else "apply autopilot-blocked")
        )
        return 0

    ok, _ = gh_retry(
        "escalation comment",
        [
            "api",
            "--method",
            "POST",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "-F",
            "body=@%s" % body_md,
        ],
    )
    if not ok:
        # `set -e` on gh_retry's status: THE LABEL IS NEVER APPLIED, so a campaign is not latched without the words that say why. See the module docstring.
        return 1
    log.info("escalation comment posted on PR #%s" % pr)

    if no_label != "true":
        ok, _ = gh_retry(
            "escalation label",
            [
                "api",
                "--method",
                "POST",
                "repos/%s/issues/%s/labels" % (repo, pr),
                "-f",
                "labels[]=autopilot-blocked",
            ],
        )
        if not ok:
            return 1
        log.info(
            "autopilot-blocked applied to PR #%s; the loop is latched until a human clears it" % pr
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
