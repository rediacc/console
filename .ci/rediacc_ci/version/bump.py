#!/usr/bin/env python3
"""Port of `.ci/scripts/version/bump.sh`.

Writes a version into every package manifest `.ci/config/constants.sh` lists, and prints the new version on STDOUT as its last line so a caller can capture it.

Usage: bump.py [--auto | --patch | --minor | --major | --version X.Y.Z]
       [--dry-run] [--output <file>]

WHAT IT ACTUALLY TOUCHES, WHICH IS ONE FILE. The twin's own header says "Updates version across all package files", and `VERSION_FILES_JSON` (`.ci/config/constants.sh:193-195`) holds exactly `packages/cli/package.json`. The root `package.json` is READ for the current version and never written. That asymmetry is the script, not a simplification of it, and it is why the differential
uses a real file tree rather than stubs: the deliverable of this script is a mutated file, and a stub cannot show that the wrong file was written or that the right one was written twice.

THE TWIN IS BROKEN ON THIS REPOSITORY TODAY, REPRODUCED AND REPORTED RATHER
THAN FIXED, on the same contract this box's siblings state: agreement with the twin is the deliverable and changing live behaviour is the operator's call.

    $ bash .ci/scripts/version/bump.sh --dry-run --auto
    ✓ Current version: 0.0.0-dev
    .ci/scripts/version/bump.sh: line 126: dev: unbound variable
    $ echo $?
    1

Every `package.json` in this repository carries the `0.0.0-dev` placeholder, because the version source of truth moved to git tags and is injected at build time (CLAUDE.md, "Versioning"). `increment_patch` splits that on `.` into `0`, `0`, `0-dev` and evaluates `$((patch + 1))`; bash arithmetic reads `0-dev` as `0 - dev`, `dev` is not a variable, and `set -u` kills the script.

WHICH FLAGS THAT ACTUALLY BREAKS, measured rather than assumed: `--auto` and `--patch` die, because they are the two that touch the PATCH field. `--minor` and `--major` survive by luck, because the placeholder's major and minor are plain `0` and the suffix rides along in a field neither of them evaluates. So the script silently works for two of its five flags and dies for two
others, on the same input. `bash_arith` reproduces all of it, exit code and wording included; only the script name and line number are the port's own, because they are true of the port.

CONSTANTS ARE LITERALS WITH A DRIFT TEST, not a bash parser. `VERSION_FILES_JSON` and `CONSOLE_ROOT_DIR`'s default are reproduced below with their line references, and `test_constants_have_not_drifted` reads constants.sh and asserts they still match. A live parse would silently FOLLOW a change to the file list, and this gate's whole subject is which files get written, so a red test
is the answer that gets read.

WHAT SOURCING constants.sh COSTS, reproduced because it fires before any argument is read. `.ci/config/constants.sh:20-33` refuses when `<root>/.devcontainer/toolchain.env` is not readable, and `set -e` on the `source` line kills the caller, so even `bump.sh --help` exits 1 on a checkout
without it. The two `${VAR:?}` refusals further down constants.sh are NOT
reproduced: they need a toolchain.env that exists but is incomplete, which nothing in this repository can produce.

K=5 LEDGER: `.ci/shadow/w7p6-version-bump.observations.jsonl`.
"""

from __future__ import annotations

import inspect
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import log
from rediacc_ci.core import bash_dialect

# `.ci/config/constants.sh:193-195`, verbatim. ONE entry, and the docstring above says why that is not a mistake.
VERSION_FILES_JSON = ("packages/cli/package.json",)

# `get_current_version` (:108-110) reads `.version` out of THIS file, which is not in the list above and is therefore never written.
CURRENT_VERSION_FILE = "package.json"

# `validate_semver` (:113-119). Strict X.Y.Z: no `v`, no prerelease, no build metadata. This is what stops `0.0.1-rc.1` reaching a manifest.
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

# `$((...))` integer literals, bash's three bases (:126, :133, :140).
_DECIMAL_RE = re.compile(r"^[0-9]+$")
_HEX_RE = re.compile(r"^0[xX][0-9a-fA-F]+$")
_OCTAL_RE = re.compile(r"^0[0-7]+$")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_TOKEN_RE = re.compile(r"\s*([A-Za-z_][A-Za-z_0-9]*|[0-9][0-9a-zA-Z]*|[-+])\s*")


class BashFatalError(Exception):
    """A bash runtime death, carrying bash's own wording and exit status 1.

    The script name and the line number are the PORT's, because they are true of the program that printed the line. Every other byte agrees, and `test_divergence_the_unbound_variable_line_names_the_port` pins both halves so nobody later "fixes" one of them.
    """

    def __init__(self, detail: str, line: int) -> None:
        super().__init__("%s: line %d: %s" % (sys.argv[0], line, detail))


class HelpRequestedError(Exception):
    """`-h | --help` (:74-87): a multi-line usage block on STDOUT, exit 0."""


class RefusalError(Exception):
    """One `log_error ...; exit 1` from the twin, as a catchable object."""

    def __init__(self, error: str) -> None:
        super().__init__(error)
        self.error = error


class MissingSourceError(Exception):
    """`source <path>` on a path that is not there (:25-26)."""

    def __init__(self, path: pathlib.Path, line: int) -> None:
        super().__init__("%s: line %d: %s: No such file or directory" % (sys.argv[0], line, path))


class Options:
    """The four variables the twin's `while` loop sets (:28-93)."""

    def __init__(self, *, dry_run: bool) -> None:
        self.dry_run = dry_run
        self.explicit_version = ""
        self.output_file = ""
        self.bump_type = ""


def console_root() -> pathlib.Path:
    """This module sits at `<root>/.ci/rediacc_ci/version/`, so `parents[3]`."""
    return pathlib.Path(__file__).resolve().parents[3]


def constants_root(root: pathlib.Path, env: dict[str, str] | None = None) -> str:
    """`CONSOLE_ROOT_DIR` (`.ci/config/constants.sh:76`).

    `${CONSOLE_ROOT_DIR:-$(cd "$(dirname constants.sh)/../.." && pwd)}`: an
    environment value wins and is used AS WRITTEN, unresolved, while the default is the physical path of the repository root. Both halves matter to a caller that sets it to a relative path or a symlink.
    """
    e = dict(os.environ) if env is None else env
    return e.get("CONSOLE_ROOT_DIR") or str(root)


def usage_one_line(prog: str) -> str:
    """`:98`, the line the no-arguments refusal prints to STDOUT."""
    return "Usage: %s [--auto | --patch | --minor | --major | --version X.Y.Z] [--dry-run]" % prog


def usage_block(prog: str) -> str:
    """`:75-85`, the `--help` text, to STDOUT, exit 0."""
    return "\n".join(
        [
            "Usage: %s [--auto | --patch | --minor | --major | --version X.Y.Z] "
            "[--dry-run] [--output file]" % prog,
            "",
            "Options:",
            "  --auto        Auto-increment patch version",
            "  --patch       Auto-increment patch version",
            "  --minor       Manually increment minor version (X.Y+1.0)",
            "  --major       Manually increment major version (X+1.0.0)",
            "  --version     Set explicit version (X.Y.Z format)",
            "  --dry-run     Preview changes without writing",
            "  --output      Write version to file (for CI)",
            "  -h, --help    Show this help",
        ]
    )


def read_dot_fields(text: str, count: int) -> list[str]:
    """`IFS='.' read -r major minor patch <<<"$version"`.

    `.` IS NOT AN IFS WHITESPACE CHARACTER, which makes this the opposite of a tab split: every single `.` is its own delimiter, so runs of them produce EMPTY fields and a leading `.` produces an empty first field. The last variable absorbs the remainder including its delimiters, which is why `1.2.3.4` yields a patch of `3.4` and not `3`. All four properties driven against bash
    5.3.
    """
    parts: list[str] = []
    rest = text
    while len(parts) < count - 1:
        if "." not in rest:
            parts.append(rest)
            rest = ""
            continue
        head, _, rest = rest.partition(".")
        parts.append(head)
    parts.append(rest)
    return parts


def bash_arith(expr_text: str, value: str, line: int) -> int:
    """`$((<name> + 1))` where the named variable holds `value`, under `set -u`.

    BASH DOES NOT SUBSTITUTE THE VALUE, IT RE-EVALUATES IT. An identifier in an arithmetic context has its VALUE parsed as a fresh arithmetic expression, recursively, which is the whole reason `0.0.0-dev` is fatal here: `patch` holds `0-dev`, that parses as `0 - dev`, `dev` is an unset name, and `set -u` makes an unset name in arithmetic a fatal error rather than a zero.

    Reproduced exactly for the three outcomes that are reachable from a manifest version string:

      * an empty value is 0 (the NAME is set, so `set -u` is satisfied)
      * a decimal, hex or octal literal is its value
      * the FIRST identifier encountered is fatal: "<ident>: unbound variable"

    A leading-zero literal that is not octal ("08") is fatal with bash's own "value too great for base" wording, which is also reproduced. Anything else raises with bash 5.3's syntax-error wording as an APPROXIMATION, and that is said out loud rather than claimed as a match: the exact error token bash reports depends on how far its parser got, no manifest version can produce one,
    and the differential does not drive it.
    """
    total = 0
    sign = 1
    seen_operand = False
    pos = 0
    text = value.strip()
    if text == "":
        return 1
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            raise BashFatalError(
                '%s: %s: invalid arithmetic operator (error token is "%s")'
                % (expr_text, bash_dialect.arith_syntax_error(), text[pos:]),
                line,
            )
        piece = match.group(1)
        pos = match.end()
        if piece in ("+", "-"):
            if not seen_operand:
                sign = -sign if piece == "-" else sign
            else:
                sign = -1 if piece == "-" else 1
                seen_operand = False
            continue
        if _IDENT_RE.fullmatch(piece):
            raise BashFatalError("%s: unbound variable" % piece, line)
        total += sign * _literal(piece, line)
        seen_operand = True
        sign = 1
    if not seen_operand:
        raise BashFatalError(
            '%s: %s: operand expected (error token is "")'
            % (expr_text, bash_dialect.arith_syntax_error()),
            line,
        )
    return total + 1


def _literal(piece: str, line: int) -> int:
    if _HEX_RE.fullmatch(piece):
        return int(piece, 16)
    if _OCTAL_RE.fullmatch(piece):
        return int(piece, 8)
    if _DECIMAL_RE.fullmatch(piece):
        if len(piece) > 1 and piece.startswith("0"):
            raise BashFatalError(
                '%s: value too great for base (error token is "%s")' % (piece, piece), line
            )
        return int(piece, 10)
    raise BashFatalError(
        '%s: %s: invalid arithmetic operator (error token is "%s")'
        % (piece, bash_dialect.arith_syntax_error(), piece),
        line,
    )


def increment_patch(version: str) -> str:
    """`:122-127`. `0.4.29` -> `0.4.30`, `0.0.0-dev` -> a fatal error."""
    major, minor, patch = read_dot_fields(version, 3)
    frame = inspect.currentframe()
    line = frame.f_lineno if frame else 0
    return "%s.%s.%d" % (major, minor, bash_arith("%s + 1" % patch, patch, line))


def increment_minor(version: str) -> str:
    """`:129-134`."""
    major, minor, _patch = read_dot_fields(version, 3)
    frame = inspect.currentframe()
    line = frame.f_lineno if frame else 0
    return "%s.%d.0" % (major, bash_arith("%s + 1" % minor, minor, line))


def increment_major(version: str) -> str:
    """`:136-141`."""
    major, _minor, _patch = read_dot_fields(version, 3)
    frame = inspect.currentframe()
    line = frame.f_lineno if frame else 0
    return "%d.0.0" % bash_arith("%s + 1" % major, major, line)


def is_semver(version: str) -> bool:
    """`validate_semver` (:113-119)."""
    return SEMVER_RE.match(version) is not None


def parse_argv(argv: list[str], *, dry_run_default: bool) -> Options:
    """The twin's hand-rolled loop (:44-93), including how it refuses.

    `set_bump_type` (:34-41) is the reason `--patch --minor` is an error rather than a last-flag-wins: two bump flags mean the caller does not know what it is asking for, and this script writes a number into a manifest.
    """
    opts = Options(dry_run=dry_run_default)
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag == "--dry-run":
            opts.dry_run = True
            i += 1
        elif flag in ("--auto", "--patch", "--minor", "--major"):
            wanted = "patch" if flag in ("--auto", "--patch") else flag[2:]
            if opts.bump_type:
                raise RefusalError(
                    "Only one bump flag may be used (--auto/--patch/--minor/--major)"
                )
            opts.bump_type = wanted
            i += 1
        elif flag == "--version":
            if i + 1 >= len(argv):
                frame = inspect.currentframe()
                raise BashFatalError("$2: unbound variable", frame.f_lineno if frame else 0)
            opts.explicit_version = argv[i + 1]
            i += 2
        elif flag == "--output":
            if i + 1 >= len(argv):
                frame = inspect.currentframe()
                raise BashFatalError("$2: unbound variable", frame.f_lineno if frame else 0)
            opts.output_file = argv[i + 1]
            i += 2
        elif flag in ("-h", "--help"):
            raise HelpRequestedError(usage_block(sys.argv[0]))
        else:
            raise RefusalError("Unknown option: %s" % flag)
    return opts


def get_current_version(root_dir: str) -> tuple[int, str]:
    """`jq -r '.version' "$CONSOLE_ROOT_DIR/package.json"` (:108-110).

    SHELLED OUT, like every other jq call in this package. Returns jq's exit status alongside the text, because the twin's bare command substitution under `set -e` dies with jq's OWN status: 2 for a file it cannot open, 5
    for a file that is not JSON, and a caller reading the exit code can tell
    those apart.
    """
    proc = subprocess.run(
        ["jq", "-r", ".version", os.path.join(root_dir, CURRENT_VERSION_FILE)],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout.rstrip("\n")


def update_package_json(path: str, version: str, *, dry_run: bool) -> tuple[bool, int]:
    """`update_package_json` (:144-163). Returns (counted-as-updated, exit-code).

    A MISSING FILE IS A WARNING THAT BECOMES A FAILURE LATER, not an immediate stop: the twin returns 1, main counts it in `failed`, keeps going through the rest of the list, and only then exits 1. So a two-file list with one file missing still writes the other.

    THE PERMISSION SIDE EFFECT IS THE TWIN'S AND IS REPRODUCED. `mktemp` creates 0600 and `mv` carries that onto the manifest, so a package.json that was 0644 comes out 0600. Named here because it is invisible in the diff and surprises whoever finds it.
    """
    if not os.path.isfile(path):
        log.warn("File not found: %s" % path)
        return False, 0
    if dry_run:
        log.info("[DRY-RUN] Would update %s to %s" % (path, version))
        return True, 0

    fd, tmpname = tempfile.mkstemp()
    with os.fdopen(fd, "wb") as handle:
        rc = subprocess.run(
            ["jq", "--arg", "v", version, ".version = $v", path], stdout=handle, check=False
        ).returncode
    if rc != 0:
        # `set -e` on the bare jq: the twin dies here, before the `mv`.
        pathlib.Path(tmpname).unlink(missing_ok=True)
        return False, rc
    shutil.move(tmpname, path)
    log.info("Updated %s" % path)
    return True, 0


def require_sources(root: pathlib.Path) -> None:
    """`source common.sh` (:25) and `source constants.sh` (:26), in that order, plus the one thing the second refuses on."""
    frame = inspect.currentframe()
    line = frame.f_lineno if frame else 0
    for rel in (".ci/scripts/lib/common.sh", ".ci/config/constants.sh"):
        path = root / rel
        if not path.is_file():
            raise MissingSourceError(path, line)
    pins = root / ".devcontainer" / "toolchain.env"
    if not os.access(pins, os.R_OK):
        # `.ci/config/constants.sh:31-32`, verbatim, then `return 1` which `set -e` turns into the caller's exit 1.
        print("constants.sh: gate toolchain pins missing: %s" % pins, file=sys.stderr)
        raise SystemExit(1)


def main(argv: list[str]) -> int:
    root = console_root()

    try:
        require_sources(root)
        # `DRY_RUN="${DRY_RUN:-false}"` (:28): the environment can turn it on,
        # and ANY value other than the literal `true` reads as off at :153.
        opts = parse_argv(argv, dry_run_default=os.environ.get("DRY_RUN", "false") == "true")
    except MissingSourceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except HelpRequestedError as exc:
        print(str(exc))
        return 0
    except BashFatalError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except RefusalError as exc:
        log.error(exc.error)
        return 1

    if not opts.bump_type and not opts.explicit_version:
        log.error("Must specify --auto/--patch/--minor/--major or --version")
        print(usage_one_line(sys.argv[0]))
        return 1
    if opts.bump_type and opts.explicit_version:
        log.error("Cannot combine bump flags with --version")
        return 1

    if shutil.which("jq") is None:
        log.error("Required command 'jq' is not available")
        return 1

    root_dir = constants_root(root)
    rc, current_version = get_current_version(root_dir)
    if rc != 0:
        return rc
    log.info("Current version: %s" % current_version)

    try:
        new_version = _next_version(opts, current_version)
    except BashFatalError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not is_semver(new_version):
        log.error("Invalid version format: %s (expected X.Y.Z)" % new_version)
        return 1

    log.step("Updating to version: %s" % new_version)

    updated = 0
    failed = 0
    for rel in VERSION_FILES_JSON:
        ok, rc = update_package_json(os.path.join(root_dir, rel), new_version, dry_run=opts.dry_run)
        if rc != 0:
            return rc
        if ok:
            updated += 1
        else:
            failed += 1

    if opts.dry_run:
        log.info("[DRY-RUN] Would update %d files" % updated)
    else:
        log.info("Updated %d files" % updated)

    if failed > 0:
        log.error("Failed to update %d files" % failed)
        return 1

    if opts.output_file:
        pathlib.Path(opts.output_file).write_text(new_version + "\n", encoding="utf-8")
        log.info("Wrote version to %s" % opts.output_file)

    # THE LAST LINE ON STDOUT IS THE INTERFACE (:235). Every other message this script writes goes to stderr precisely so this one can be captured.
    print(new_version)
    return 0


def _next_version(opts: Options, current_version: str) -> str:
    """`:175-193`. An explicit version wins and is NOT incremented."""
    if opts.explicit_version:
        return opts.explicit_version
    if opts.bump_type == "patch":
        return increment_patch(current_version)
    if opts.bump_type == "minor":
        return increment_minor(current_version)
    return increment_major(current_version)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
