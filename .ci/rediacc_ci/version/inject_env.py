#!/usr/bin/env python3
"""Port of `.ci/scripts/version/inject-env.sh`.

Decides, in ONE place, what version number an artifact ships with, and hands it out under four names: `APP_VERSION`, `VITE_APP_VERSION`, `CLI_VERSION` and the legacy `TAG`. Resolution order, unchanged from the twin:

  1. `--version X.Y.Z`                 explicit caller intent
  2. `$VERSION`                        already set by an outer script
  3. `resolve-version.sh --current`    the latest git tag
  4. `0.0.0-dev`                       local dev fallback

-----------------------------------------------------------------------------
WHY THIS IS A LIBRARY *AND* A CLI, WHICH THE TWIN ALSO IS
-----------------------------------------------------------------------------
`inject-env.sh` is on the language-policy allowlist with the reason "sourced by build-cli-executables.sh to export variables into the CALLER's shell -- a child process cannot mutate its parent's environment in any language", and that reason is still true and is not what this port disputes. The twin has TWO callers' shapes, and only one of them is unportable:

  * SOURCED (`source inject-env.sh --strict`) by build-cli-executables.sh and
    build-cli-musl.sh, for the exported set. A child process cannot do this in
    any language, so `inject()` returns the mapping and the CALLER applies it --
    the same shape `core.proxyx` and `infra.ci_env` already take for their
    sourced-only twins.
  * EXECUTED (`inject-env.sh --version "$NEXT_VERSION" --strict --print`) as a
    release preflight from ci-build-cli.yml and ci-build-docker.yml. That one is
    a plain stdout-producing CLI and `main()` is byte-identical to it.

So "equivalent" here has FOUR observables, and `test_version_inject_env.py` compares all four: exit code, stdout, stderr, and the exported set the caller is left holding. Comparing only the exit code would compare almost nothing -- the happy path exits 0 in every case this script has.

-----------------------------------------------------------------------------
THE RESOLVER IS SPAWNED, NOT IMPORTED
-----------------------------------------------------------------------------
`resolve-version.sh --current` is run as a subprocess from the path the twin computes (`<dir of the twin>/resolve-version.sh`), derived here from this module's own location. `rediacc_ci.version.resolve_version` is deliberately NOT imported: it is a separately-verified port with its own ledger, and importing it would make THIS differential's agreement depend on THAT port's
correctness rather than on this one's. Two ports agreeing because they share an implementation is not evidence.

`2>/dev/null` in the twin is reproduced: a resolver that is missing, that is not executable, that is not in a git repository, or that prints a diagnostic, all fall through to the fallback in silence. The twin's own comment records why the `&& [[ -n ... ]]` half exists -- a resolver that exits 0 printing NOTHING used to propagate an EMPTY version through `--strict`.

-----------------------------------------------------------------------------
A REAL DEFECT IN THE TWIN, REPRODUCED HERE ON PURPOSE
-----------------------------------------------------------------------------
`--version` consumes the next word unconditionally, so

    inject-env.sh --version --strict --print

sets the version to the literal string "--strict", never enables strict mode, prints `--strict` on stdout and exits 0. The one guard this file exists to provide is silently switched off by a caller whose `$NEXT_VERSION` expanded to nothing, which is the EXACT failure the twin's own `--version was given an empty value` check was added for -- an unquoted empty expansion drops the
argument entirely rather than passing "". Reproduced byte for byte and pinned by `test_a_flag_swallowed_as_a_version_is_a_twin_defect`, reported rather than fixed: a port that rejected it would fail differently from the script it claims to be equivalent to, and the repair is a cutover-box decision.

-----------------------------------------------------------------------------
ENVIRONMENT IS READ AT THE CALL SITE, ONE NAME AT A TIME
-----------------------------------------------------------------------------
`os.environ.get("VERSION", "")` and nothing else. No `env = dict(os.environ)`
alias: the env-manifest reader parses direct `os.environ` reads, and an alias makes the name invisible to it.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

# The four names the twin exports, in the order it exports them. `TAG` is the legacy name renet/build.sh and some Docker builds still read; it is last in the twin and last here, because a caller that dumps the mapping in insertion order should produce the twin's own order.
EXPORTED_NAMES = ("APP_VERSION", "VITE_APP_VERSION", "CLI_VERSION", "TAG")

# The local-dev fallback, and the exact string `--strict` refuses.
DEV_VERSION = "0.0.0-dev"

# The twin's ERE, character for character. A publishable version is dotted numeric, optionally v-prefixed, with an optional pre-release/build suffix. Matched with `fullmatch` rather than `search`: bash's `$` is end-of-string, where Python's `$` also matches before a trailing newline, so `search` would accept "1.2.3\n" that bash rejects.
PUBLISHABLE_RE = re.compile(r"v?[0-9]+(\.[0-9]+)*([-+][0-9A-Za-z.-]+)?")


class UsageError(Exception):
    """One of the twin's three argument-parsing refusals.

    Carries the message verbatim so `main()` can print it and `inject()` can hand it back to a library caller without either re-deriving the text.
    """


def resolver_path() -> pathlib.Path:
    """`$_ie_dir/resolve-version.sh`, where `_ie_dir` is the twin's directory.

    Derived from this module's own path, matching the twin's `BASH_SOURCE[0]` derivation rather than cwd or `$REDIACC_CI_ROOT`: a differential that pointed one subject at a fixture and the other at the real tree would diverge for a reason that has nothing to do with the port.
    """
    # This file: <root>/.ci/rediacc_ci/version/inject_env.py
    root = pathlib.Path(__file__).resolve().parents[3]
    return root / ".ci" / "scripts" / "version" / "resolve-version.sh"


def parse_args(argv: list[str]) -> tuple[str, bool, bool, bool]:
    """`(override, given, strict, want_print)`, or raise `UsageError`.

    `given` is separate from a truthy `override` because the twin distinguishes them: `--version ""` is an ERROR, while no `--version` at all falls through to `$VERSION`. Folding the two would turn a refusal into a silent fallback, which is the very case the twin's comment says let a release-path caller build the version it had already published.
    """
    override = ""
    given = False
    strict = False
    want_print = False

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--version":
            if i + 1 >= len(argv):
                raise UsageError("inject-env.sh: --version requires an argument")
            # THE DEFECT IN THE MODULE DOCSTRING LIVES HERE: the next word is taken whatever it is, including another flag.
            override = argv[i + 1]
            given = True
            i += 2
        elif arg == "--strict":
            strict = True
            i += 1
        elif arg == "--print":
            want_print = True
            i += 1
        else:
            raise UsageError("inject-env.sh: unknown arg: %s" % arg)

    if given and not override:
        raise UsageError("inject-env.sh: --version was given an empty value")

    return override, given, strict, want_print


def resolve(override: str) -> str:
    """The four-step resolution order, returning the chosen version string."""
    if override:
        return override
    from_env = os.environ.get("VERSION", "")
    if from_env:
        return from_env
    resolved = _resolver_output()
    if resolved:
        return resolved
    # Covers BOTH a failing resolver and one that exits 0 printing nothing. The second case is the one the twin's comment records as having propagated an empty version through `--strict`.
    return DEV_VERSION


def _resolver_output() -> str:
    """`"$(resolve-version.sh --current 2>/dev/null)"`, or "" on any failure.

    Command substitution strips trailing newlines, so `.strip("\\n")` and not `.strip()`: a resolver that printed leading whitespace would keep it in bash, and a port that trimmed it would disagree.
    """
    script = resolver_path()
    try:
        completed = subprocess.run(
            [str(script), "--current"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        # A missing or non-executable resolver: bash's own diagnostic goes to the suppressed stderr and the substitution yields "".
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.rstrip("\n")


def strict_refusal(version: str) -> str | None:
    """The three things `--strict` rejects, in the twin's order, or None.

    Three and not one: the twin's own comment says the original check compared only against the literal `0.0.0-dev`, so an EMPTY version sailed through it, and anything non-numeric (a curl error page, "none", "latest") reached a build define.
    """
    if not version:
        return "inject-env.sh: version is empty under --strict"
    if version == DEV_VERSION:
        return (
            "inject-env.sh: version resolved to 0.0.0-dev under --strict "
            "(did the checkout include tags?)"
        )
    if not PUBLISHABLE_RE.fullmatch(version):
        return (
            "inject-env.sh: version '%s' is not a dotted numeric version, "
            "refusing under --strict" % version
        )
    return None


def inject(argv: list[str]) -> tuple[int, dict[str, str], list[str], list[str]]:
    """The whole contract as data: `(exit_code, exports, stdout, stderr)`.

    This is what a SOURCING caller needs and what `main()` is a thin printer over. `exports` is empty on every refusal path, matching the twin: it `return`s before reaching its `export` statements, so a caller that sourced a failing invocation is left with its previous values, not with new ones.
    """
    try:
        override, _given, strict, want_print = parse_args(argv)
    except UsageError as exc:
        return 1, {}, [], [str(exc)]

    version = resolve(override)

    if strict:
        refusal = strict_refusal(version)
        if refusal is not None:
            return 1, {}, [], [refusal]

    exports = dict.fromkeys(EXPORTED_NAMES, version)
    out = [version] if want_print else []
    return 0, exports, out, []


def main(argv: list[str]) -> int:
    code, _exports, out, err = inject(argv)
    for line in err:
        print(line, file=sys.stderr, flush=True)
    for line in out:
        print(line, flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
