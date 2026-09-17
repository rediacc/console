#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/initialize.sh` (324 lines, 7 steps).

The first job of every CI run: validate the app token, decide whether the push
came from a bot, initialise the private submodules, mint the three image tags,
resolve the next version from the tag list, and ask the registry which of the
three images already exist. Everything downstream reads its outputs, so a wrong
answer here is a wrong answer everywhere.

LIVE CALLER, not repointed. The bash twin stays the registered gate; this module
is its verified-equivalent alternative, and the cutover is a separate, later,
driver-only step. The twin is also the subject of
`.ci/scripts/test/gates/test-releaseversion-tag-fetch.sh`, which EXTRACTS its
tag-fetch block by literal anchors; nothing here changes those anchors because
nothing here touches the twin.

Ledger: `.ci/shadow/w7p6-initialize.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-initialize --assert --k 5`).

-----------------------------------------------------------------------------
WHY THE FIVE SIBLING SCRIPTS ARE STILL THE BASH ONES
-----------------------------------------------------------------------------
The twin shells out to `detect-pointer-bump.sh`, `generate-tag.sh` (three
times), `detect-bump-type.sh`, `dispatch-release.sh` and `resolve-version.sh`.
This port runs the SAME five bash scripts, by the same relative paths, with the
same argv. Three reasons, in order of weight:

  1. `detect-pointer-bump.sh` has no Python port at all, so a port that reached
     for `rediacc_ci` siblings would have to reach for bash anyway, and the
     mixture would be harder to reason about than either pure form.
  2. A differential that ran bash siblings on one side and Python siblings on
     the other would be comparing SIX pairs at once. When it disagreed, nothing
     in the output would say which pair moved.
  3. Repointing a live caller at a port is exactly the cutover step this wave is
     forbidden to take.

`set_image_tags.py`, the other file in this wave, does the opposite and calls
`derive_image_tag` in process. The difference is deliberate: that sibling is
ALREADY ported and already carries a K=5 ledger, and its twin's job there is one
call with two arms rather than six calls threaded through five steps.

-----------------------------------------------------------------------------
DEFECT A -- `GITHUB_REPOSITORY` IS REQUIRED AND NEVER CHECKED, AND IT DIES 200
LINES AFTER THE CHECK THAT WOULD HAVE CAUGHT IT
-----------------------------------------------------------------------------
Step 1 validates `GITHUB_PAT` with four lines of prose naming the secret, the
settings page and the scopes it needs. `GITHUB_REPOSITORY` is just as required
-- it is half of the fetch URL -- and is read bare, under `set -u`, at :219:

    $ GITHUB_PAT=s3cr3t GITHUB_EVENT_NAME=pull_request \\
        bash .ci/scripts/ci/initialize.sh
    ...
    → Calculating next version from git tags...
    <path>/initialize.sh: line 219: GITHUB_REPOSITORY: unbound variable
    exit=1

By then the submodules are initialised, the token rewrite is written into the
GLOBAL git config, three tags are minted and EIGHT outputs are already on stdout
and in `$GITHUB_OUTPUT`. The diagnostic is bash's, names no fix, and arrives
after the expensive half of the work. Reproduced verbatim; not repaired, because
`.ci/scripts/ci/` is not this writer's to change. `UNCHECKED_REQUIRED_ENV` names
it so a test can assert it by name.

Note the asymmetry the port has to preserve: `${GITHUB_REPOSITORY}` refuses an
UNSET variable and accepts an EMPTY one, which yields
`https://x-access-token:<pat>@github.com/.git` and a fetch failure three
attempts and fifteen seconds later.

-----------------------------------------------------------------------------
DEFECT B -- `IFS=', '` JOINS WITH A COMMA AND NO SPACE
-----------------------------------------------------------------------------
    log_info "Push event: versioned tags - $(
        IFS=', '
        echo "${log_parts[*]}"
    )"

`${array[*]}` joins with the FIRST CHARACTER of IFS, never with the whole
string, so the two-character separator the author wrote produces:

    ✓ Push event: versioned tags - RENET: renet-aaaa-1.2.4,WEB: web-bbbb-1.2.4,RDC: rdc-cccc-1.2.4

Cosmetic, and reproduced exactly (`LOG_PARTS_SEPARATOR = ","`), because the
differential compares bytes. Driven 2026-09-14.

-----------------------------------------------------------------------------
DEFECT C -- `--output` WITH NO VALUE WRITES A FILE CALLED `true` IN THE REPO ROOT
-----------------------------------------------------------------------------
`parse_args` turns a flag with no value into the STRING `true`, so
`OUTPUT_FILE="${ARG_OUTPUT:-}"` becomes `true`, and `write_output` appends to a
relative path -- resolved against the repo root, because step 0 has already
`cd`'d there:

    $ GITHUB_PAT=x bash .ci/scripts/ci/initialize.sh --check-only --output
    ... exit=0, and a new file `./true` holding is_bot=false, pointer_bump_only=false

Exit 0, no warning, and the outputs the caller asked for are in a file nobody
will look in. Reproduced; not repaired. `EMPTY_OUTPUT_FLAG_WRITES_TRUE` names it.

-----------------------------------------------------------------------------
DEFECT D -- THE REGISTRY PROBE FOLDS "COULD NOT ASK" INTO "DOES NOT EXIST"
-----------------------------------------------------------------------------
`check_image_path` returns `false` when docker is missing, when the daemon is
down, when the registry refuses the credentials and when the manifest genuinely
is not there. Only the last one is what `renet_exists=false` claims. The
consequence is a rebuild rather than a wrong artifact, which is why this is
recorded and not repaired, but the log line
`✓ renet:<tag> exists=false` is stated with the same confidence in all four
cases and the twin's own comment ("Docker not available, assume images don't
exist") only covers one of them.

-----------------------------------------------------------------------------
WHAT `set -e`, `set -u` AND `set -o pipefail` MEAN FOR THIS PORT
-----------------------------------------------------------------------------
Every point where the twin would die is reproduced as an early `return` with the
twin's exit status, and the places where it would NOT die are reproduced too.
Three that are easy to get backwards:

  * `NEXT_VERSION=$(...)` dies on a failing sibling (a failing command
    substitution IS the assignment's status), so the port returns that status.
  * `log_info "... (from tag: $(resolve-version.sh --current))"` does NOT die on
    a failing substitution: the outer `log_info` succeeds, so the message simply
    carries an empty tag. The port ignores that one's status on purpose.
  * `LATEST_TAG="$(git tag -l 'v*' --sort=-v:refname | head -1)"` is under
    `pipefail`, so a failing `git` takes the script down with git's status and no
    message of the script's own.

-----------------------------------------------------------------------------
ONE DELIBERATE DIVERGENCE, AND IT IS THE SAME ONE `common.repo_root` CARRIES
-----------------------------------------------------------------------------
`get_repo_root` resolves three directories up from `common.sh` and honours
nothing; `common.repo_root()` delegates to `paths.repo_root()`, which honours
`$REDIACC_CI_ROOT`. On every real run that variable is unset and the two land on
the same directory, which is what the ledger records. The differential exploits
the override deliberately: it points the port at a fixture tree whose
`.ci/scripts/lib/common.sh` sends the twin to the same place, which is the only
way to drive the five sibling calls without running the real ones.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time

from rediacc_ci import log
from rediacc_ci.core import common

# --------------------------------------------------------------------------- Twin line numbers. Bash prints these inside its own diagnostics, so they are part of the observable output rather than documentation. `test_the_pinned_line_numbers_still_point_at_the_twins_lines` re-derives every one of them from the twin.
# ---------------------------------------------------------------------------

#: `echo "${key}=${value}" >>"$OUTPUT_FILE"` -- the redirect that names the file
#: when the file cannot be opened.
WRITE_OUTPUT_LINE = 43

#: `git config --global url."..."` -- reached only when `git` itself is missing.
GIT_CONFIG_LINE = 104

#: `if ! git submodule update --init --recursive private/ 2>/dev/null; then`
GIT_SUBMODULE_LINE = 111

#: `if ! .ci/scripts/ci/detect-pointer-bump.sh ...; then`
DETECT_POINTER_BUMP_LINE = 131

#: The three `generate-tag.sh` command substitutions.
GENERATE_TAG_RENET_LINE = 141
GENERATE_TAG_WEB_LINE = 159
GENERATE_TAG_RDC_LINE = 160

#: `BUMP_TYPE=$(.ci/scripts/version/detect-bump-type.sh --verbose)`
DETECT_BUMP_TYPE_LINE = 175

#: `FETCH_URL="https://x-access-token:${GITHUB_PAT}@github.com/${GITHUB_REPOSITORY}.git"`
FETCH_URL_LINE = 219

#: `if git fetch --tags --force --no-recurse-submodules "$FETCH_URL" ...`
GIT_FETCH_LINE = 234

#: `LATEST_TAG_LIST="$(git tag -l 'v*' --sort=-v:refname)"`. The twin used to
#: pipe that into `head -1`; the pipe was removed because `head` closing the read
#: end SIGPIPEs git and, under `pipefail`, kills the script -- a race masked by
#: the 64 KB pipe buffer until the tag list outgrows it. The twin now takes the
#: first line in-shell, which is what this port has always done.
GIT_TAG_LINE = 280

#: The two `resolve-version.sh` substitutions.
RESOLVE_VERSION_NEXT_LINE = 288
RESOLVE_VERSION_CURRENT_LINE = 290

# --------------------------------------------------------------------------- The five sibling scripts, spelled exactly as the twin spells them: RELATIVE to the repo root, which both implementations have already chdir'd to. Absolute paths would be tidier and would also stop the fixture in the differential from working, because the fixture's whole mechanism is that a relative path
# lands in the fixture tree. ---------------------------------------------------------------------------
DETECT_POINTER_BUMP = ".ci/scripts/ci/detect-pointer-bump.sh"
GENERATE_TAG = ".ci/scripts/ci/generate-tag.sh"
DISPATCH_RELEASE = ".ci/scripts/ci/dispatch-release.sh"
DETECT_BUMP_TYPE = ".ci/scripts/version/detect-bump-type.sh"
RESOLVE_VERSION = ".ci/scripts/version/resolve-version.sh"

#: The file whose presence means "the submodules are already there" (twin :107).
SUBMODULE_SENTINEL = "private/renet/.ci/ci.sh"

#: The two authors the twin treats as bots (twin :72).
BOT_AUTHORS = ("github-actions[bot]", "dependabot[bot]")

#: All three images publish flat under this prefix (twin :304).
REGISTRY_PREFIX = "ghcr.io/rediacc"

#: The registry name each tag belongs to, in the twin's order (twin :307-309).
IMAGE_NAMES = (("renet", "renet"), ("web", "server"), ("rdc", "rdc"))

#: DEFECT B. `${log_parts[*]}` under `IFS=', '` joins with the FIRST character.
LOG_PARTS_SEPARATOR = ","

#: DEFECT A, named so a test can assert it by name rather than by message text.
UNCHECKED_REQUIRED_ENV = "GITHUB_REPOSITORY"

#: DEFECT C, likewise. `parse_args` turns a valueless flag into this string.
EMPTY_OUTPUT_FLAG_WRITES_TRUE = "true"

#: The redaction placeholder and the stand-in the twin uses when GITHUB_PAT is
#: empty (twin :249). Unreachable in practice: step 1 has already refused.
REDACTION = "***"
NO_PAT_SENTINEL = "__no_github_pat_set__"

#: `sleep $((attempt * 5))` (twin :240), and the attempt count above it.
FETCH_ATTEMPTS = 3
FETCH_BACKOFF_SECONDS = 5


class Exit(Exception):  # noqa: N818 -- this is a control flow signal, not an error report
    """`set -e` firing inside a helper: stop, with this status, printing nothing."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def bash_exec_failure(line: int, command: str, err: OSError, *, searched: bool) -> int:
    """Bash's own message for a command it could not run, and bash's status.

    Not defensive padding: without it a missing sibling is a Python traceback
    where the twin prints one line and carries on (step 4) or dies with 127
    (everywhere else), and a traceback is a bigger divergence than any wording.

    `searched` distinguishes the two messages bash uses. A name resolved through
    PATH that is not there is `command not found`; a path containing a slash is
    the operating system's own `No such file or directory`.
    """
    if isinstance(err, PermissionError):
        text, code = "Permission denied", 126
    elif searched:
        text, code = "command not found", 127
    else:
        text, code = "No such file or directory", 127
    sys.stderr.write("%s: line %d: %s: %s\n" % (sys.argv[0], line, command, text))
    sys.stderr.flush()
    return code


def run_inherit(
    argv: list[str], line: int, *, searched: bool = False, quiet_err: bool = False
) -> int:
    """A plain command: both streams inherited, status returned.

    STDOUT IS FLUSHED FIRST, every time. The child writes to the same descriptor
    this process buffers, and Python block-buffers a redirected stdout where bash
    does not. Without the flush the port's `key=value` lines would sort AFTER a
    child's output in a captured stream, which is a byte difference in the one
    thing every downstream consumer parses.
    """
    sys.stdout.flush()
    try:
        return subprocess.run(
            argv,
            stderr=subprocess.DEVNULL if quiet_err else None,
            check=False,
        ).returncode
    except OSError as err:
        return bash_exec_failure(line, argv[0], err, searched=searched)


def run_capture(argv: list[str], line: int) -> tuple[int, str]:
    """`VAR=$(cmd)`: stdout captured, stderr inherited, trailing newlines stripped.

    UTF-8 STRICTLY, where bash passes bytes through. The only values captured
    here are a tag, a bump type and a version, all minted by siblings that
    produce `[0-9a-z.-]`, so the two cannot differ on any real input; and if one
    ever did, a decode error is a loud stop rather than a tag that silently
    differs by one byte from the one the twin would have used.
    """
    sys.stdout.flush()
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            encoding="utf-8",
            check=False,
        )
    except OSError as err:
        return bash_exec_failure(line, argv[0], err, searched=False), ""
    return proc.returncode, proc.stdout.rstrip("\n")


def write_output(key: str, value: str, output_file: str) -> None:
    """`write_output` (twin :39-47). The FILE first, then stdout.

    The order matters and is observable: when the file cannot be opened the twin
    dies before the `echo`, so the key never reaches stdout either (driven).
    """
    if output_file:
        try:
            with open(output_file, "a", encoding="utf-8") as handle:
                handle.write("%s=%s\n" % (key, value))
        except OSError as err:
            sys.stderr.write(
                "%s: line %d: %s: %s\n"
                % (sys.argv[0], WRITE_OUTPUT_LINE, output_file, err.strerror)
            )
            sys.stderr.flush()
            raise Exit(1) from err
    print("%s=%s" % (key, value), flush=True)


def is_bot_commit(event_name: str, commit_author: str) -> tuple[str, str]:
    """Step 2's decision (twin :70-80), as a pure function.

    Returns `(is_bot, message)`. Exported so the differential can exercise all
    three arms directly: the whole of step 2 is one three-armed condition, and
    two of the arms are one character apart in the output they produce.
    """
    if event_name == "push" and commit_author:
        if commit_author in BOT_AUTHORS:
            return "true", "Commit from bot: %s - downstream jobs will be skipped" % commit_author
        return "false", "Commit author: %s" % commit_author
    return "false", "Non-push event or no author info, running CI normally"


def fetch_url(pat: str, repository: str) -> str:
    """Twin :219. The credentialed remote, token and all."""
    return "https://x-access-token:%s@github.com/%s.git" % (pat, repository)


def redact(data: bytes, pat: str) -> bytes:
    """`sed "s|${GITHUB_PAT:-__no_github_pat_set__}|***|g"` (twin :249).

    BYTES, not text: this is git's stderr, and a decode step could raise on
    output the twin passes through untouched.

    THE ONE PLACE THIS IS NOT SED. sed's pattern is a BASIC REGULAR EXPRESSION,
    so a token containing `.`, `*`, `[`, `\\`, `^` or `$` would match more (or
    less) than itself; `bytes.replace` is literal. Every token this repository
    issues is `[A-Za-z0-9_]`, for which the two are identical, and a literal
    replacement can only redact MORE conservatively than a regex that failed to
    match. Stated rather than hidden.
    """
    needle = (pat or NO_PAT_SENTINEL).encode("utf-8", "surrogateescape")
    return data.replace(needle, REDACTION.encode("ascii"))


def check_image_path(path: str, tag: str) -> str:
    """`check_image_path` (twin :293-305). DEFECT D lives here.

    `command -v docker` is `shutil.which`: bash's builtin would also find a
    function or an alias, and neither exists in a `#!/bin/bash` script that
    defines neither.
    """
    if shutil.which("docker") is None:
        return "false"
    proc = subprocess.run(
        ["docker", "manifest", "inspect", "%s:%s" % (path, tag)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return "true" if proc.returncode == 0 else "false"


def release_decision(root_relative: str = DISPATCH_RELEASE) -> str:
    """Twin :209, including the two things that make it fail OPEN.

        RELEASE_DECISION="$(GITHUB_OUTPUT='' <script> --decide-only 2>&1 \\
            | grep '^decision:' || true)"

    `2>&1` merges the child's stderr INTO the pipe, so its diagnostics are
    filtered out with everything else and never reach the log; `|| true`
    swallows every non-zero status, the child's and grep's alike. A crashed,
    cancelled or missing decider therefore yields the empty string, and the
    caller's `!= 'decision: skip'` then releases. That polarity is the twin's
    stated design, not an accident, so it is reproduced exactly.
    """
    sys.stdout.flush()
    # The CHILD's environment, built once and handed to the child. Deliberately not an alias this module then reads its own variables through.
    child_env = {**os.environ, "GITHUB_OUTPUT": ""}
    try:
        proc = subprocess.run(
            [root_relative, "--decide-only"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            env=child_env,
            check=False,
        )
        merged = proc.stdout
    except OSError:
        # bash writes its `No such file or directory` to the command's stderr, which the `2>&1` has already pointed into the pipe, so grep eats it and the substitution is empty. Same shape here.
        merged = ""
    lines = [line for line in merged.split("\n") if line.startswith("decision:")]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as refusal:
        # `printf -v` on a key that is not a valid identifier. bash prints this
        # from common.sh:333 and returns 2, and `set -e` takes the script with it.
        print(str(refusal), file=sys.stderr)
        return refusal.code

    check_only = args.get("ARG_CHECK_ONLY", "") or "false"
    output_file = args.get("ARG_OUTPUT", "")

    os.chdir(common.repo_root())

    try:
        return run(check_only, output_file)
    except Exit as stop:
        return stop.code


def run(check_only: str, output_file: str) -> int:
    # ----------------------------------------------------------------------- Step 1: validate the GH_PAT secret -----------------------------------------------------------------------
    log.step("Validating required secrets...")
    if not os.environ.get("GITHUB_PAT", ""):
        log.error("ERROR: GITHUB_PAT is required but not set")
        log.error("This repository requires private submodule access.")
        log.error("Configure the GH_PAT secret in: Settings > Secrets and variables > Actions")
        log.error("Required scopes: repo, write:packages")
        return 1
    log.info("GH_PAT secret is configured")

    # ----------------------------------------------------------------------- Step 2: bot detection -----------------------------------------------------------------------
    log.step("Checking commit author...")
    is_bot, message = is_bot_commit(
        os.environ.get("GITHUB_EVENT_NAME", ""), os.environ.get("COMMIT_AUTHOR", "")
    )
    log.info(message)

    write_output("is_bot", is_bot, output_file)
    # Default for every early-exit path; detect-pointer-bump.sh may overwrite it
    # with true below (in GITHUB_OUTPUT the last write of a key wins).
    write_output("pointer_bump_only", "false", output_file)

    if is_bot == "true":
        log.info("Bot commit detected, skipping remaining initialization")
        return 0

    if check_only == "true":
        log.info("Check-only mode, skipping submodule and tag generation")
        return 0

    # ----------------------------------------------------------------------- Step 3: submodules -----------------------------------------------------------------------
    log.step("Initializing private submodules...")

    pat = os.environ.get("GITHUB_PAT", "")
    status = run_inherit(
        [
            "git",
            "config",
            "--global",
            "url.https://x-access-token:%s@github.com/.insteadOf" % pat,
            "https://github.com/",
        ],
        GIT_CONFIG_LINE,
        searched=True,
    )
    if status != 0:
        return status

    if os.path.isfile(SUBMODULE_SENTINEL):
        log.info("Submodules already initialized")
    else:
        status = run_inherit(
            ["git", "submodule", "update", "--init", "--recursive", "private/"],
            GIT_SUBMODULE_LINE,
            searched=True,
            quiet_err=True,
        )
        if status != 0:
            log.error("Failed to initialize submodules")
            return 1
        if not os.path.isfile(SUBMODULE_SENTINEL):
            log.error("Submodule initialization incomplete")
            return 1
        log.info("Submodules initialized successfully")

    # ----------------------------------------------------------------------- Step 4: pointer-bump fast-path detection -----------------------------------------------------------------------
    log.step("Detecting pointer-bump-only push...")
    # `${OUTPUT_FILE:+--output "$OUTPUT_FILE"}` unquoted: the inner quotes survive
    # the expansion, so a path with spaces stays ONE word (driven), and an unset OUTPUT_FILE contributes zero words rather than one empty one.
    forwarded = ["--output", output_file] if output_file else []
    if run_inherit([DETECT_POINTER_BUMP, *forwarded], DETECT_POINTER_BUMP_LINE) != 0:
        log.warn("detect-pointer-bump.sh errored; running full CI")
        write_output("pointer_bump_only", "false", output_file)

    # ----------------------------------------------------------------------- Step 5: the three image tags -----------------------------------------------------------------------
    log.step("Generating CI tags...")

    status, renet_tag = run_capture(
        [GENERATE_TAG, "--submodule", "private/renet"], GENERATE_TAG_RENET_LINE
    )
    if status != 0:
        return status
    status, web_tag = run_capture(
        [GENERATE_TAG, "--closure", "web", "--extra", renet_tag], GENERATE_TAG_WEB_LINE
    )
    if status != 0:
        return status
    status, rdc_tag = run_capture(
        [GENERATE_TAG, "--closure", "rdc", "--extra", renet_tag], GENERATE_TAG_RDC_LINE
    )
    if status != 0:
        return status

    write_output("renet_tag", renet_tag, output_file)
    write_output("web_tag", web_tag, output_file)
    write_output("rdc_tag", rdc_tag, output_file)
    write_output("image_tag", renet_tag, output_file)

    log.info("Renet tag: %s (renet commit)" % renet_tag)
    log.info("Web tag: %s (console commit)" % web_tag)
    log.info("RDC tag: %s (console commit)" % rdc_tag)

    # ----------------------------------------------------------------------- Step 6: bump type -----------------------------------------------------------------------
    log.step("Detecting bump type from PR labels...")
    status, bump_type = run_capture([DETECT_BUMP_TYPE, "--verbose"], DETECT_BUMP_TYPE_LINE)
    if status != 0:
        return status
    log.info("Bump type: %s" % bump_type)
    write_output("bump_type", bump_type, output_file)

    # ----------------------------------------------------------------------- Step 6b: does this commit earn a release -----------------------------------------------------------------------
    if (
        os.environ.get("GITHUB_EVENT_NAME", "") == "push"
        and os.environ.get("GITHUB_REF", "") == "refs/heads/main"
    ):
        log.step("Deciding whether this commit earns a release...")
        decision = release_decision()
        log.info("Release decision: %s" % (decision or "<undecided, will release>"))
        if decision == "decision: skip":
            write_output("skip_release", "true", output_file)

    # ----------------------------------------------------------------------- Step 6c: next version, from a tag list this refuses to guess at -----------------------------------------------------------------------
    log.step("Calculating next version from git tags...")

    # DEFECT A. `${GITHUB_REPOSITORY}` under `set -u`: UNSET is fatal here and
    # empty is not, and the port has to keep that distinction to stay identical.
    if UNCHECKED_REQUIRED_ENV not in os.environ:
        sys.stderr.write(
            "%s: line %d: %s: unbound variable\n"
            % (sys.argv[0], FETCH_URL_LINE, UNCHECKED_REQUIRED_ENV)
        )
        sys.stderr.flush()
        return 1
    url = fetch_url(os.environ.get("GITHUB_PAT", ""), os.environ.get("GITHUB_REPOSITORY", ""))

    handle, tag_fetch_err = tempfile.mkstemp()
    os.close(handle)
    fetch_ok = False
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        sys.stdout.flush()
        # `2>` truncates on every attempt, so only the LAST attempt's stderr is ever reported.
        with open(tag_fetch_err, "wb") as errfile:
            try:
                status = subprocess.run(
                    ["git", "fetch", "--tags", "--force", "--no-recurse-submodules", url],
                    stderr=errfile,
                    check=False,
                ).returncode
            except OSError as err:
                status = bash_exec_failure(GIT_FETCH_LINE, "git", err, searched=True)
        if status == 0:
            fetch_ok = True
            break
        log.warn("Tag fetch attempt %d/%d failed" % (attempt, FETCH_ATTEMPTS))
        if attempt < FETCH_ATTEMPTS:
            time.sleep(attempt * FETCH_BACKOFF_SECONDS)

    if not fetch_ok:
        log.error(
            "Could not fetch tags after %d attempts; refusing to compute a version from a tag "
            "list that may be stale." % FETCH_ATTEMPTS
        )
        # FETCH_URL embeds the app token, and git echoes the remote in its errors, so git's stderr is redacted rather than printed raw.
        with open(tag_fetch_err, "rb") as errfile:
            sys.stderr.flush()
            sys.stderr.buffer.write(redact(errfile.read(), os.environ.get("GITHUB_PAT", "")))
            sys.stderr.buffer.flush()
        os.unlink(tag_fetch_err)
        return 1
    os.unlink(tag_fetch_err)

    status, tag_list = run_capture(["git", "tag", "-l", "v*", "--sort=-v:refname"], GIT_TAG_LINE)
    if status != 0:
        # A FAILED READ IS NOT AN EMPTY ONE. git's own status leaves the assignment and `set -e` carries it out, with no message of the script's own -- `test_a_failing_tag_read_dies_silently_under_pipefail` pins exactly that. It is also why the twin's pipe could not simply become `mapfile -t < <(git tag ...)`: a process substitution's status is not checked, so a failing git would
        # arrive here as an empty tag list and be reported as "no v* tag exists".
        return status
    latest_tag = tag_list.split("\n", 1)[0]
    if not latest_tag:
        log.error(
            "Tag fetch succeeded but no v* tag exists; tag-based versioning cannot derive a "
            "version here."
        )
        log.error(
            "Create the initial tag (git tag -a v0.0.0 -m v0.0.0 && git push origin v0.0.0) "
            "before running CI."
        )
        return 1
    log.info("Latest tag: %s" % latest_tag)

    status, next_version = run_capture(
        [RESOLVE_VERSION, "--bump-type", bump_type], RESOLVE_VERSION_NEXT_LINE
    )
    if status != 0:
        return status
    write_output("next_version", next_version, output_file)
    # The nested substitution's status is DISCARDED by bash: the outer log_info succeeds either way, so a failing `--current` only empties the parenthesis.
    _, current_version = run_capture([RESOLVE_VERSION, "--current"], RESOLVE_VERSION_CURRENT_LINE)
    log.info("Next version: %s (from tag: %s)" % (next_version, current_version))

    # ----------------------------------------------------------------------- Step 6d: on push-to-main every tag carries the version, to bust the cache -----------------------------------------------------------------------
    tags = {"RENET": renet_tag, "WEB": web_tag, "RDC": rdc_tag}
    if os.environ.get("GITHUB_EVENT_NAME", "") == "push":
        log_parts = []
        for prefix in ("RENET", "WEB", "RDC"):
            new_value = "%s-%s" % (tags[prefix], next_version)
            tags[prefix] = new_value
            write_output("%s_tag" % prefix.lower(), new_value, output_file)
            log_parts.append("%s: %s" % (prefix, new_value))
        write_output("image_tag", tags["RENET"], output_file)
        # DEFECT B: one comma, no space.
        log.info("Push event: versioned tags - %s" % LOG_PARTS_SEPARATOR.join(log_parts))

    # ----------------------------------------------------------------------- Step 7: which images the registry already has -----------------------------------------------------------------------
    log.step("Checking image cache in registry...")

    exists = {
        key: check_image_path("%s/%s" % (REGISTRY_PREFIX, image), tags[key.upper()])
        for key, image in IMAGE_NAMES
    }
    for key, _ in IMAGE_NAMES:
        write_output("%s_exists" % key, exists[key], output_file)
    for key, _ in IMAGE_NAMES:
        log.info("%s:%s exists=%s" % (key, tags[key.upper()], exists[key]))

    log.info("Initialization complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
