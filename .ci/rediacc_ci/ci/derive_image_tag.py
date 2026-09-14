#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/derive-image-tag.sh` (137 lines).

Derive the Docker image tag from an explicit `--version`, from the git ref when
the build is a tag build, or from the newest `v*` tag in the repository. The
twin's header owns the three-step ladder; it is not restated here.

LIVE CALLER, not repointed. The bash twin stays the registered gate; this module
is its verified-equivalent alternative, and the cutover is a separate, later,
driver-only step.

Ledger: `.ci/shadow/w7p6-derive-image-tag.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-derive-image-tag --assert
--k 5`).

-----------------------------------------------------------------------------
DEFECT A -- THE HELP TEXT AND THE HEADER BOTH DESCRIBE A BRANCH THAT DOES NOT
EXIST ANY MORE
-----------------------------------------------------------------------------
Twin :16 ("If running from a branch -> use version from package.json (fallback:
'latest')") and twin :57 ("- Branch (e.g., main) -> uses version from
package.json") both say package.json. The code at :77-88 reads GIT TAGS and has
not touched package.json since the comment at :78-80 was added to explain the
change ("Resolve the actual version from package.json instead of literal
'latest'" -- which is itself describing a third, older behaviour). Nothing in
this file reads package.json.

That matters beyond tidiness: every `package.json` in this repo carries the
`0.0.0-dev` placeholder by design (CLAUDE.md, "Versioning"), so a reader who
believes the help text expects `0.0.0-dev` and would file the real answer as a
bug. The strings are reproduced VERBATIM here, wrong description and all,
because the differential compares bytes and because `.ci/scripts/ci/` is not
this writer's to change. Reported to the driver.

-----------------------------------------------------------------------------
DEFECT B -- `--version ''` IS SILENTLY IGNORED RATHER THAN REFUSED
-----------------------------------------------------------------------------
`VERSION="${2?--version requires an argument}"` refuses an ABSENT argument and
accepts an EMPTY one, and the decision below is `if [[ -n "$VERSION" ]]`. So an
empty value falls through to auto-derivation instead of failing:

    $ bash .ci/scripts/ci/derive-image-tag.sh --version ''
    (info) Auto-derived from git tags (local): 1.3.12
    1.3.12

A workflow input that resolved to the empty string -- which is exactly what a
`workflow_dispatch` input left blank produces -- therefore tags an image with
whatever the newest git tag happens to be, and says so only on stderr, which the
consuming step does not read. Reproduced; not repaired.

-----------------------------------------------------------------------------
WHY `git` IS SHELLED OUT TO RATHER THAN REIMPLEMENTED
-----------------------------------------------------------------------------
`git tag -l 'v*' --sort=-v:refname` is a VERSION sort, not a lexicographic one:
it puts `v1.10.0` above `v1.9.0`, which a Python `sorted()` does not without
reimplementing git's `versioncmp`. A second implementation of that ordering is
the one thing in this script that could pick a different tag from the twin on a
real repository, so the port runs the same command with the same arguments. The
`git fetch --tags --force --no-recurse-submodules origin` on the shallow-clone
path is likewise the twin's, including its `2>/dev/null || true`, so a fetch
that fails for any reason leaves the ladder to fall through to `latest`.

-----------------------------------------------------------------------------
LENGTH IS COUNTED IN CHARACTERS HERE AND IN BYTES BY BASH UNDER LC_ALL=C, AND
THAT CANNOT DIVERGE
-----------------------------------------------------------------------------
`${#TAG}` counts characters in a UTF-8 locale and bytes under `LC_ALL=C`.
`len()` always counts characters. The two can only disagree on a non-ASCII tag,
and the regex check at :112 -- `^[a-zA-Z0-9._-]+$` -- runs FIRST and rejects
every non-ASCII tag before the length check is reached. So the order of the two
validations is what makes the two implementations provably identical, and
reordering them would break that.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys

from rediacc_ci import log

# Twin line numbers bash prints inside its own diagnostics. Re-derived from the
# twin by `test_the_pinned_line_numbers_still_point_at_the_twins_lines`.
VERSION_ARG_LINE = 34
REF_NAME_LINE = 81

# `[[ ! "$TAG" =~ ^[a-zA-Z0-9._-]+$ ]]` (twin :112). Docker's tag alphabet, as
# the twin spells it -- note it accepts a leading `.` or `-`, which a real
# Docker tag may not, so this is the twin's rule and not Docker's.
TAG_RE = re.compile(r"^[a-zA-Z0-9._-]+$")

# `[[ ${#TAG} -gt 128 ]]` (twin :119).
MAX_TAG_LENGTH = 128

# The placeholder every package.json in this repo carries; the twin treats it as
# "no usable version" and falls back (twin :85).
PLACEHOLDER_VERSION = "0.0.0-dev"
FALLBACK_TAG = "latest"

# `BRANCH="${GITHUB_REF_NAME:-local}"` (twin :77).
LOCAL_BRANCH = "local"

# The three names `--env-file` writes, in the twin's order (twin :133-135).
ENV_FILE_NAMES = ("TAG", "WEB_TAG", "RENET_TAG")

# The help body, copied from the twin (:45-66) with `$0` left as a placeholder.
# DEFECT A lives in here verbatim: the "uses version from package.json" line is
# wrong and is reproduced anyway, because the differential compares bytes.
HELP_LINES = (
    "Usage: {prog} [OPTIONS]",
    "",
    "Derive Docker image tag from Git ref or explicit input.",
    "",
    "Options:",
    "  --version TAG      Use explicit version tag",
    "  --github-output    Write 'tag=VALUE' to GITHUB_OUTPUT",
    "  --env-file         Write TAG, WEB_TAG, RENET_TAG to GITHUB_ENV",
    "  -h, --help         Show this help message",
    "",
    "Auto-derivation (when --version not provided):",
    "  - Git tag (e.g., v1.2.3)  → uses tag name",
    "  - Branch (e.g., main)     → uses version from package.json",
    "",
    "Examples:",
    "  {prog}                              # Auto-derive, output to stdout",
    "  {prog} --version v1.2.3             # Explicit: v1.2.3",
    "  {prog} --env-file                   # Auto-derive, set GITHUB_ENV vars",
    "  {prog} --version latest --env-file  # Explicit with env export",
)


class RefusalError(Exception):
    """One exit with a status, after whatever has already been printed."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def parse_argv(argv: list[str]) -> tuple[str, bool, bool]:
    """The twin's hand-rolled `while`/`case` loop (:29-71).

    NOT `common.parse_args`. The twin does not use it here, and the differences
    are observable: this loop REFUSES an unknown option (`*)` -> exit 1) where
    `parse_args` silently accepts every `--flag`, and it treats `-h` -- a single
    dash -- as help where `parse_args` would swallow it as the previous flag's
    value.

    Returns `(version, github_output_mode, env_file_mode)`.
    """
    version = ""
    github_output_mode = False
    env_file_mode = False

    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--version":
            if index + 1 >= len(argv):
                # `${2?--version requires an argument}`: bash names the POSITIONAL
                # PARAMETER (`2`), not the option, which is why the message reads
                # `... line 34: 2: --version requires an argument`.
                sys.stderr.write(
                    "%s: line %d: 2: --version requires an argument\n"
                    % (sys.argv[0], VERSION_ARG_LINE)
                )
                sys.stderr.flush()
                raise RefusalError(1)
            version = argv[index + 1]
            index += 2
        elif arg == "--github-output":
            github_output_mode = True
            index += 1
        elif arg == "--env-file":
            env_file_mode = True
            index += 1
        elif arg in ("-h", "--help"):
            for line in HELP_LINES:
                print(line.format(prog=sys.argv[0]))
            sys.stdout.flush()
            raise RefusalError(0)
        else:
            log.error("Unknown option: %s" % arg)
            raise RefusalError(1)

    return version, github_output_mode, env_file_mode


def git_stdout(args: list[str]) -> str:
    """Run `git <args> 2>/dev/null` and return stdout, or "" if git is absent.

    A MISSING `git` IS THE EMPTY STRING, NOT AN EXCEPTION, and that is the twin's
    behaviour rather than a convenience. Every git call in the twin has its
    stderr on `/dev/null` and its status either tested or `|| true`d, so on a
    machine without git the twin prints nothing, derives `latest` and exits 0.
    Driven 2026-09-14 on a PATH without git; the port raised FileNotFoundError
    until this existed, which is a louder answer than the twin's and therefore a
    divergence rather than an improvement.
    """
    try:
        return subprocess.run(
            ["git", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        ).stdout
    except FileNotFoundError:
        return ""


def git_tags_exist() -> bool:
    """`[[ -z "$(git tag -l 'v*' 2>/dev/null)" ]]`, inverted.

    A missing git, or a directory that is not a work tree, produces no stdout
    and therefore reads as "no tags", exactly as the twin does.
    """
    return git_stdout(["tag", "-l", "v*"]).rstrip("\n") != ""


def git_fetch_tags() -> None:
    """`git fetch --tags --force --no-recurse-submodules origin 2>/dev/null || true`.

    STDOUT IS INHERITED, because the twin redirects only stderr. Failure is
    swallowed, which is the twin's `|| true`, and so is a missing binary.
    """
    with contextlib.suppress(FileNotFoundError):
        subprocess.run(
            ["git", "fetch", "--tags", "--force", "--no-recurse-submodules", "origin"],
            stderr=subprocess.DEVNULL,
            check=False,
        )


def newest_v_tag() -> str:
    """`git tag -l 'v*' --sort=-v:refname 2>/dev/null | head -1 | sed 's/^v//'`.

    `head -1` takes at most one line, so `sed` sees at most one and strips at
    most one leading `v` -- `vv1.0` becomes `v1.0`, which `removeprefix` matches.
    Command substitution strips the trailing newline; a failing git leaves the
    whole thing empty because of the twin's `|| true`.
    """
    first = git_stdout(["tag", "-l", "v*", "--sort=-v:refname"]).split("\n", 1)[0]
    return first.removeprefix("v")


def resolve_tag(version: str) -> str:
    """The three-arm ladder at twin :74-90. Logs exactly what the twin logs."""
    if version:
        log.info("Using explicit version: %s" % version)
        return version

    if os.environ.get("GITHUB_REF_TYPE", "") == "tag":
        # `${GITHUB_REF_NAME?...}` refuses an UNSET name and accepts an empty
        # one; an empty one then fails the format check two arms down.
        if "GITHUB_REF_NAME" not in os.environ:
            sys.stderr.write(
                "%s: line %d: GITHUB_REF_NAME: GITHUB_REF_NAME is not set for a tag build\n"
                % (sys.argv[0], REF_NAME_LINE)
            )
            sys.stderr.flush()
            raise RefusalError(1)
        tag = os.environ.get("GITHUB_REF_NAME", "")
        log.info("Auto-derived from tag: %s" % tag)
        return tag

    branch = os.environ.get("GITHUB_REF_NAME", "") or LOCAL_BRANCH
    if not git_tags_exist():
        git_fetch_tags()
    tag = newest_v_tag()
    if not tag or tag == PLACEHOLDER_VERSION:
        tag = FALLBACK_TAG
    log.info("Auto-derived from git tags (%s): %s" % (branch, tag))
    return tag


def validate(tag: str) -> None:
    """Twin :111-123. Format FIRST, then length -- see the module docstring."""
    if not TAG_RE.match(tag):
        log.error("Invalid tag format: %s" % tag)
        log.error("Tags must contain only alphanumeric characters, dots, hyphens, and underscores")
        raise RefusalError(1)
    if len(tag) > MAX_TAG_LENGTH:
        log.error("Tag too long: %d characters (max %d)" % (len(tag), MAX_TAG_LENGTH))
        raise RefusalError(1)


def write_github_output(tag: str) -> None:
    """Twin :126-133. A missing GITHUB_OUTPUT is a WARNING and a pass."""
    path = os.environ.get("GITHUB_OUTPUT", "")
    if not path:
        log.warn("GITHUB_OUTPUT not set, skipping --github-output")
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("tag=%s\n" % tag)
    log.info("Set GITHUB_OUTPUT: tag=%s" % tag)


def write_github_env(tag: str) -> None:
    """Twin :136-148. Three names, one value, one warning if unset."""
    path = os.environ.get("GITHUB_ENV", "")
    if not path:
        log.warn("GITHUB_ENV not set, skipping --env-file")
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.writelines("%s=%s\n" % (name, tag) for name in ENV_FILE_NAMES)
    log.info("Set GITHUB_ENV: %s" % ", ".join("%s=%s" % (name, tag) for name in ENV_FILE_NAMES))


def main(argv: list[str]) -> int:
    try:
        version, github_output_mode, env_file_mode = parse_argv(argv)
        tag = resolve_tag(version)
        validate(tag)
        if github_output_mode:
            write_github_output(tag)
        if env_file_mode:
            write_github_env(tag)
    except RefusalError as refusal:
        return refusal.code

    print(tag, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
