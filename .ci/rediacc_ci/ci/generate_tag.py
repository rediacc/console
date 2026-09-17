#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/generate-tag.sh` (362 lines, 4 tag modes).

Mints the tag a CI-built Docker image is published under. The twin is mostly COMMENT -- roughly 200 of its 362 lines argue for the membership of each hashed input, record the measured incidents that shaped the closure key (the v1.2.12 "Version mismatch: expected '1.2.13', got '1.2.12'" runs, the weekly bucket, the 12-hex widening after 3-char collisions), and name what the key
still does not cover. All of that stays in the twin and is not restated here; what follows is only what a reader of THIS file needs.

FOUR MODES, in the twin's own precedence order (`--submodule` > `--closure` > `--self` > time-based). The precedence is silent: `--self --closure web` runs the closure and says nothing about the ignored flag.

LIVE CALLERS, not repointed: `.ci/scripts/ci/initialize.sh` calls `--submodule private/renet`, `--closure web` and `--closure rdc`, publishing the last two as `web_tag`/`rdc_tag`, which `cd-stage.yml` retags straight onto a release channel. The bash twin stays the registered gate; this module is its verified-equivalent alternative, and the cutover is a separate, later, driver-only
step.

Ledger: `.ci/shadow/w7p6-generate-tag.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-generate-tag --assert --k 5`).

-----------------------------------------------------------------------------
DEFECT G: `--github-output` WITH $GITHUB_OUTPUT UNSET IS A SILENT NO-OP
-----------------------------------------------------------------------------
    if [[ "$GITHUB_OUTPUT_MODE" == "true" ]] && [[ -n "${GITHUB_OUTPUT:-}" ]]

The caller ASKED for a GitHub Actions output. When the variable is absent the twin writes nothing, says nothing, and exits 0:

    $ bash .ci/scripts/ci/generate-tag.sh --self --github-output
    (info) Generated self tag: b99162b7f
    b99162b7f
    exit=0

Downstream that is `steps.<id>.outputs.ci_tag` resolving to the empty string, and every consumer of it reading an empty image tag. "The write could not happen" is folded into "the write happened". Reproduced, not repaired. `GITHUB_OUTPUT_IS_SILENTLY_OPTIONAL` names it so a test can assert it by name.

-----------------------------------------------------------------------------
DEFECT H: THE FAIL-LOUD BUILD-CONFIG CHECK IS CWD-DEPENDENT
-----------------------------------------------------------------------------
Three of the six `BUILD_CONFIG_FILES` are repo-relative (`.github/workflows/...`, `.ci/scripts/build/build-renet.sh`), so the check the twin added specifically so a renamed input could not "silently narrow what the tag covers" fires on a correct input reached from the wrong directory, and blames the file:

    $ cd /tmp && bash <repo>/.ci/scripts/ci/generate-tag.sh \\
        --submodule <repo>/private/renet
    (error) Build-config input not found: .github/workflows/ci-build-renet.yml
    (error) This file is hashed into the renet image tag. ...
    exit=1

The message sends the reader to `BUILD_CONFIG_FILES` when the fault is the working directory. Reproduced verbatim.

-----------------------------------------------------------------------------
DEFECT I: THE `else CI_TAG="$SUBMODULE_COMMIT"` ARM IS UNREACHABLE
-----------------------------------------------------------------------------
`BUILD_CONFIG_HASH` is built from a NON-EMPTY hard-coded list whose every miss exits 1, so `[[ -n "$BUILD_CONFIG_HASH" ]]` is always true and the bare-commit tag can never be produced. Dead code that reads as a supported fallback. `UNREACHABLE_BARE_COMMIT_TAG` names it; the port keeps the arm so the two files stay line-comparable.

-----------------------------------------------------------------------------
DEFECT J: A MISSING OPTION VALUE DIES AS BASH, NOT AS THE SCRIPT
-----------------------------------------------------------------------------
`--output`, `--submodule`, `--closure` and `--extra` read `"$2"` under `set -u`, so as the last token each dies with `<path>: line 30: $2: unbound variable`, exit 1, instead of the `Unknown option:` message the parser exists to print.

-----------------------------------------------------------------------------
DIVERGENCES, ALL IN TEXT ONLY A HUMAN READS
-----------------------------------------------------------------------------
 1. `$0` in `--help` is the program's own name, so the twin prints a `.sh` path
    and this prints a `.py` one. The differential normalises that one token.
 2. Defect J's `$2: unbound variable` becomes `MISSING_VALUE`, same stream,
    same exit 1. Same ruling as `deploy/cf_purge_urls.py` divergence 1.
 3. `date -u +%Y%m%d-%H%M%S` versus `datetime.now(UTC).strftime(...)`: two
    processes started a second apart mint different tags. Same ruling as
    `deploy/write_release_sentinel.py` -- the differential normalises the one
    field and asserts the FORMAT on both sides separately. `%G%V` in the
    closure key has the same shape but a one-week period, so it agrees except
    across an ISO-week boundary.
 4. common.sh's `echo -e` interprets backslash escapes in the message;
    `rediacc_ci.log` formats the message as data.

WHAT IS SHELLED OUT TO AND WHAT IS NOT. `git` is shelled out to, because the answers are git's (`rev-parse --short` honours core.abbrev, `rev-parse HEAD:p` resolves a gitlink to its recorded commit) and a reimplementation would be a second answer to a question git has already answered. So is `resolve-version.sh`, which is a sibling script rather than a tool. `sha256sum` and `cut
-c1-N` are NOT: hashlib produces the same digest and the slice is a slice, so two processes per hashed file would buy nothing.

Exit: 0 on a tag, 1 on any refusal.
"""

from __future__ import annotations

import datetime
import hashlib
import os
import subprocess
import sys

from rediacc_ci import log, paths

# Defect names, so a test asserts them by name rather than by restating a sentence.
GITHUB_OUTPUT_IS_SILENTLY_OPTIONAL = True
UNREACHABLE_BARE_COMMIT_TAG = True

# Divergence 2's stand-in for bash's `$2: unbound variable`.
MISSING_VALUE = "generate-tag.sh: %s requires a value"

# `sha256sum | cut -c1-8` per file, then `... | cut -c1-12` over the
# concatenation (twin :143, :152). 12 hex chars = 48 bits; the twin records at
# :146-150 why the old 3-char form was not enough.
PER_FILE_HEX = 8
COMBINED_HEX = 12

# `BUILD_CONFIG_FILES` (twin :120-127), with `{sub}` where the twin writes
# `$SUBMODULE_PATH`. The membership rule and the deliberate omission of `.ci/scripts/infra/build-renet.sh` are argued at twin :96-118.
BUILD_CONFIG_FILES = (
    "{sub}/Dockerfile",
    "{sub}/Dockerfile.native",
    "{sub}/build.sh",
    ".github/workflows/ci-build-renet.yml",
    ".github/workflows/ci-build-docker.yml",
    ".ci/scripts/build/build-renet.sh",
)

# `CLOSURE_PATHS` per closure (twin :203-245). Hashed as git object ids AT HEAD, not as file bytes: an entry may be a directory (the tree oid covers files added later) or a gitlink (private/account resolves to its recorded commit), and HEAD-based hashing is immune to the in-job version bump that dirties
# package.json after initialize.sh has run.
CLOSURE_PATHS = {
    "web": (
        "Dockerfile",
        ".ci/docker/web",
        "package.json",
        "package-lock.json",
        "tsconfig.json",
        "packages/shared",
        "packages/www",
        "packages/json",
        "packages/cli",
        "packages/provisioning",
        "private/account",
        ".ci/scripts/build/build-www.sh",
        ".ci/scripts/build/build-cli.sh",
        ".ci/scripts/build/pack-cli-npm.sh",
        ".ci/scripts/build/buildx-push-web.sh",
        ".github/workflows/ci-build-docker.yml",
        ".github/actions/setup-workspace",
    ),
    "rdc": (
        "packages/cli",
        "packages/shared",
        "packages/provisioning",
        "package.json",
        "package-lock.json",
        "tsconfig.json",
        ".ci/scripts/build/build-cli-musl.sh",
        ".ci/scripts/build/build-cli-executables.sh",
        ".ci/scripts/build/prepare-cli-assets.sh",
        "scripts/gen/generate-third-party-licenses.ts",
        ".github/workflows/ci-build-cli.yml",
        ".github/workflows/ci-build-docker.yml",
    ),
}

# The four advice lines under a missing build-config input (twin :138-140) and under a missing closure input (twin :253-256). Kept as templates so the differential can assert each one appears in the twin verbatim.
BUILD_CONFIG_ADVICE = (
    "This file is hashed into the renet image tag. A missing entry silently",
    "narrows what the tag covers, so a changed build can reuse a stale image.",
    "Fix the path in BUILD_CONFIG_FILES, or delete the entry if the file is gone.",
)
CLOSURE_ADVICE = (
    "It is hashed into the {closure} image tag. A missing entry",
    "narrows what the tag covers, so a changed build can reuse a",
    "stale image. Fix the path, or delete the entry if it is gone.",
)

# `$SCRIPT_DIR/../version/resolve-version.sh` (twin :329), resolved from the TWIN's directory. Expressed relative to the repo root, which is the same place, and which `paths.repo_root()` finds from this module rather than from cwd.
RESOLVE_VERSION = ".ci/scripts/version/resolve-version.sh"


class RefusalError(Exception):
    """A refusal that has already been logged. Carries the exit status."""

    def __init__(self, status: int = 1) -> None:
        super().__init__("refused")
        self.status = status


def sha256_hex(data: bytes) -> str:
    """`sha256sum`, as hex. The digest is the digest; see the header."""
    return hashlib.sha256(data).hexdigest()


def git_out(args: list[str], *, quiet: bool = False) -> tuple[int, str]:
    """`git <args>`. Returns (status, stdout with trailing newlines stripped).

    `quiet` sends stderr to /dev/null, which is what the twin's `2>/dev/null` does on the two lookups that have a fallback.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL if quiet else None,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return 127, ""
    return proc.returncode, proc.stdout.rstrip("\n")


def help_text(program: str) -> str:
    """The twin's `-h|--help` block (twin :54-69), `$0` substituted.

    Reproduced as data rather than extracted from the twin: extracting would make this module depend on the twin still existing, and the cutover deletes it. `test_ci_generate_tag.py` re-derives the block from the twin file and fails if the two ever drift.
    """
    return "\n".join(
        [
            "Usage: %s [OPTIONS]" % program,
            "",
            "Modes:",
            "  (default)              Generate time-based tag (YYYYMMDD-HHMMSS)",
            "  --submodule PATH       Get commit hash of specified submodule",
            "  --self                 Get commit hash of current repository",
            "",
            "Options:",
            "  --output FILE          Write tag to specified file",
            "  --github-output        Write to GITHUB_OUTPUT for GitHub Actions",
            "  -h, --help             Show this help message",
            "",
            "Examples:",
            "  %s                                    # -> 20260120-104603" % program,
            "  %s --submodule private/renet          # -> fb33b0f" % program,
            "  %s --self                             # -> c909b05" % program,
            "",
        ]
    )


class Args:
    """The twin's six parser variables, with its own defaults."""

    def __init__(self) -> None:
        self.output_file = ""
        self.github_output_mode = False
        self.submodule_path = ""
        self.self_mode = False
        self.closure_name = ""
        # `EXTRA_KEY+="$2"` APPENDS, so repeated `--extra` concatenate. The
        # other value options assign, so repeated ones overwrite.
        self.extra_key = ""
        self.help = False


def parse_args(argv: list[str]) -> Args:
    """The twin's `while [[ $# -gt 0 ]]` loop, shift semantics included."""
    args = Args()
    i = 0
    while i < len(argv):
        opt = argv[i]
        if opt in ("--output", "--submodule", "--closure", "--extra"):
            if i + 1 >= len(argv):
                # Defect J. `"$2"` under `set -u`.
                print(MISSING_VALUE % opt, file=sys.stderr, flush=True)
                raise RefusalError(1)
            value = argv[i + 1]
            if opt == "--output":
                args.output_file = value
            elif opt == "--submodule":
                args.submodule_path = value
            elif opt == "--closure":
                args.closure_name = value
            else:
                args.extra_key += value
            i += 2
        elif opt == "--github-output":
            args.github_output_mode = True
            i += 1
        elif opt == "--self":
            args.self_mode = True
            i += 1
        elif opt in ("-h", "--help"):
            args.help = True
            return args
        else:
            log.error("Unknown option: %s" % opt)
            raise RefusalError(1)
    return args


def submodule_tag(submodule_path: str) -> str:
    """`--submodule PATH` (twin :80-158). Commit hash plus a build-config hash."""
    if not os.path.isdir(submodule_path):
        log.error("Submodule not found: %s" % submodule_path)
        raise RefusalError(1)
    dot_git = os.path.join(submodule_path, ".git")
    if not os.path.isdir(dot_git) and not os.path.isfile(dot_git):
        log.error("Not a git repository: %s" % submodule_path)
        raise RefusalError(1)

    status, submodule_commit = git_out(["-C", submodule_path, "rev-parse", "--short", "HEAD"])
    if status != 0:
        # A plain assignment in the twin, so `set -e` ends the run with git's own stderr and git's own status.
        raise RefusalError(status)

    build_config_hash = ""
    for template in BUILD_CONFIG_FILES:
        path = template.format(sub=submodule_path)
        if not os.path.isfile(path):
            log.error("Build-config input not found: %s" % path)
            for line in BUILD_CONFIG_ADVICE:
                log.error(line)
            raise RefusalError(1)
        with open(path, "rb") as fh:
            build_config_hash += sha256_hex(fh.read())[:PER_FILE_HEX]

    if build_config_hash:
        config_short = sha256_hex(build_config_hash.encode("utf-8"))[:COMBINED_HEX]
        return "%s-%s" % (submodule_commit, config_short)
    # Defect I: unreachable, kept so the two files stay line-comparable.
    return submodule_commit


def iso_week_bucket(now: datetime.datetime | None = None) -> str:
    """`date -u +%G%V` (twin :281). ISO year and week, NOT `%Y%W`.

    The twin's own note: the last days of December must not collide with the first days of January, which `%Y%W` allows and `%G%V` does not.
    """
    moment = datetime.datetime.now(datetime.UTC) if now is None else now
    return moment.strftime("%G%V")


def closure_version() -> tuple[str, bool]:
    """`resolve-version.sh --current`, with the twin's fallback (twin :329-333).

    Returns `(value, fell_back)`. Failure is NOT fatal -- this runs where no tag is reachable (a shallow clone, a fresh fork, initialize.sh Step 5 before it fetches tags) -- but the fallback is DISTINGUISHING rather than empty: an empty marker would collapse every untagged build to one key, which is the exact failure the version component was added to fix.
    """
    script = str(paths.repo_root() / RESOLVE_VERSION)
    try:
        proc = subprocess.run(
            [script, "--current"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        status, value = proc.returncode, proc.stdout.rstrip("\n")
    except OSError:
        status, value = 127, ""
    if status == 0 and value:
        return value, False
    head_status, head = git_out(["rev-parse", "HEAD"], quiet=True)
    return "untagged-%s" % (head if head_status == 0 and head else "unknown"), True


def closure_tag(closure_name: str, extra_key: str) -> str:
    """`--closure web|rdc` (twin :160-336). The producer-closure key."""
    if closure_name not in CLOSURE_PATHS:
        log.error("Unknown closure: %s (expected: web, rdc)" % closure_name)
        raise RefusalError(1)

    closure_hash = ""
    for closure_path in CLOSURE_PATHS[closure_name]:
        status, path_oid = git_out(["rev-parse", "HEAD:%s" % closure_path], quiet=True)
        if status != 0:
            log.error("Closure input not found at HEAD: %s" % closure_path)
            for line in CLOSURE_ADVICE:
                log.error(line.format(closure=closure_name))
            raise RefusalError(1)
        closure_hash += path_oid

    # `--extra` folds in an opaque upstream key. Used for RENET_TAG: renet binaries reach BOTH images as artifacts, never as source, so no path can cover them.
    closure_hash += extra_key
    closure_hash += "week:%s" % iso_week_bucket()

    version, fell_back = closure_version()
    if fell_back:
        log.warn(
            "No version tag reachable; closure key falls back to '%s'. "
            "Image reuse is disabled for this build." % version
        )
    closure_hash += "version:%s" % version

    return "%s-%s" % (
        closure_name,
        sha256_hex(closure_hash.encode("utf-8"))[:COMBINED_HEX],
    )


def time_tag(now: datetime.datetime | None = None) -> str:
    """`date -u +%Y%m%d-%H%M%S` (twin :345). Divergence 3."""
    moment = datetime.datetime.now(datetime.UTC) if now is None else now
    return moment.strftime("%Y%m%d-%H%M%S")


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
    except RefusalError as exc:
        return exc.status

    if args.help:
        sys.stdout.write(help_text(sys.argv[0]))
        return 0

    try:
        # The twin's precedence, and it is silent: a second mode flag is ignored without a word.
        if args.submodule_path:
            ci_tag = submodule_tag(args.submodule_path)
            log.info("Generated submodule tag (%s): %s" % (args.submodule_path, ci_tag))
        elif args.closure_name:
            ci_tag = closure_tag(args.closure_name, args.extra_key)
            log.info("Generated closure tag (%s): %s" % (args.closure_name, ci_tag))
        elif args.self_mode:
            status, ci_tag = git_out(["rev-parse", "--short", "HEAD"])
            if status != 0:
                raise RefusalError(status)
            log.info("Generated self tag: %s" % ci_tag)
        else:
            ci_tag = time_tag()
            log.info("Generated CI tag: %s" % ci_tag)
    except RefusalError as exc:
        return exc.status

    if args.output_file:
        try:
            with open(args.output_file, "w", encoding="utf-8") as fh:
                fh.write("%s\n" % ci_tag)
        except OSError as exc:
            # bash's own redirection error, turned into exit 1 by `set -e`.
            print("%s: %s" % (args.output_file, exc.strerror), file=sys.stderr, flush=True)
            return 1
        log.info("Wrote CI tag to: %s" % args.output_file)

    # Defect G: the caller asked, and an absent variable is silence.
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if args.github_output_mode and github_output:
        try:
            with open(github_output, "a", encoding="utf-8") as fh:
                fh.write("ci_tag=%s\n" % ci_tag)
        except OSError as exc:
            print("%s: %s" % (github_output, exc.strerror), file=sys.stderr, flush=True)
            return 1
        log.info("Set GITHUB_OUTPUT: ci_tag=%s" % ci_tag)

    print(ci_tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
