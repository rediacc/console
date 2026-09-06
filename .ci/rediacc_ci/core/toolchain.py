"""The pinned gate toolchain as DATA, and a version comparison that is correct.

PORTED FROM the loading and comparison half of `.ci/scripts/lib/toolchain.sh`.
That file still exists and keeps its function names and its acquisition half; what
moves here is the part every OTHER reader of the pins already reimplements --
`.ci/config/constants.sh`, `.ci/bootstrap.sh`, `.ci/lib/setup.sh` and
`.github/workflows/*` each open `.devcontainer/toolchain.env` in their own way,
and only one of them refuses when a pin is missing.

--------------------------------------------------------------------------
WHERE THE PINS FILE IS, AND WHY THAT IS NOT `.ci/config/`
--------------------------------------------------------------------------
`<root>/.devcontainer/toolchain.env`, resolved through `rediacc_ci.paths` rather
than counted in `..` hops. The pins file's own header states the reason it lives
there and not beside the other config: the devcontainer image build context IS
`.devcontainer/` (.github/workflows/ci-build-docker.yml:558, .ci/lib/devbox.sh:263),
`COPY` cannot reach outside a build context, and widening the context to the repo
root would upload the whole tree plus submodules on every image build. So the
path is a decision, and this module reads it rather than guessing at one.

`toolchain_pins_file` in the bash computes the same path with
`cd "$(dirname "${BASH_SOURCE[0]}")/../../.."`. The two are asserted equal by
`test_core_toolchain.py`, so a file move that updates one and not the other is a
red rather than two readers of two different files.

--------------------------------------------------------------------------
WHY A MISSING OR EMPTY PIN RAISES, AND NEVER DEFAULTS
--------------------------------------------------------------------------
This is the whole reason the module is more than a two-line parser, so it is
argued rather than asserted.

`toolchain_pin_for` used to return "" WITH EXIT CODE 0 when the pins had not been
loaded, and that empty string travelled into a download URL. The receipt is in the
bash, measured 2026-08-26 on a fresh shell:

    .../releases/download/v/shellcheck-v.linux.aarch64.tar.xz  -> curl 404

The 404 names GitHub, not the missing pin, so the debugging starts in the wrong
place. `toolchain_check` and `toolchain_acquire` each grew their own
`[[ -n "$pin" ]]` guard afterwards, and the asymmetry between them -- one entry
point refusing while the other interpolated -- is recorded in
`.ci/scripts/lib/toolchain.sh:452-457` as the defect that let it happen.

`.ci/config/constants.sh` reaches the same conclusion in the other direction and
spells it in bash: `readonly NODE_VERSION_MIN="${NODE_VERSION_MIN:?NODE_VERSION_MIN
not sourced from toolchain.env}"` (constants.sh:58, and the same `:?` form at :44
and :234). `:?` is bash's "fail loudly rather than default", and it is there
because the key it guards REPLACED a composed default: constants.sh used to build
the floor as `"${NODE_VERSION}.0.0"`, a defensible-looking line that silently
yielded 22.0.0 while both manifests said >=22.13.0. The looser of two floors was
the one every shell path enforced, and a machine on Node 22.4 passed
`./run.sh setup` and then failed inside npm.

So: `pin()` raises `PinError` on an absent key, on an empty value, and on a pins
file that parses to no pairs at all. There is no `default=` parameter, on purpose
-- a default is how the 22.0.0 floor happened, and adding one here would let it
happen again in Python.

--------------------------------------------------------------------------
WHY THE COMPARISON IS FIELD-WISE INTEGER AND NOT A STRING COMPARE
--------------------------------------------------------------------------
    "22.13.0" < "22.9.0"     is TRUE as strings, and FALSE as versions

One character decides it: '1' sorts before '9'. Every floor check in this repo is
exactly this shape -- `check_node_version` compares the running Node against
NODE_VERSION_MIN=22.13.0 -- so a string compare would wave through the very
release the floor was raised to exclude, and would do it silently, in the
direction that reads as a pass.

The bash gets this right today by delegating to `sort -V`
(.ci/lib/local-common.sh:429, .ci/lib/setup.sh:57 and :351), which is GNU
coreutils and is a subprocess per comparison. `compare()` here is checked against
`sort -V` on a corpus in the tests, so the port is proven equivalent rather than
merely plausible, and `test_core_toolchain.py` additionally proves the corpus is
one a string compare FAILS -- a differential nobody can pass by accident.

Shorter is not smaller: `22` and `22.0.0` compare equal, because the missing
fields are zeros and not "unknown". That matters for NODE_VERSION, which is a
BARE MAJOR (`22`) while every other pin in the file is a full version.
`same_major()` exists for exactly that key, mirroring the `${actual%%.*}` branch
at toolchain.sh:147-151 rather than making every caller remember which pins are
majors.

--------------------------------------------------------------------------
COMMAND-LINE ENTRY POINT (what a bash caller can reach)
--------------------------------------------------------------------------
    python3 -m rediacc_ci.core.toolchain pairs
        the KEY=value lines only, one per line -- the `--env` form that is safe
        to append to $GITHUB_ENV, which rejects anything that is not KEY=value.

    python3 -m rediacc_ci.core.toolchain keys
        the key names, one per line.

    python3 -m rediacc_ci.core.toolchain value <KEY>
        one pin by key name. Exit 1 and a message on stderr when it is absent or
        empty; NOTHING on stdout, so a caller's `v="$(...)" || die` cannot pick
        up a plausible empty string.

    python3 -m rediacc_ci.core.toolchain pin <tool>
        the same, addressed by TOOL name (the `toolchain_pin_for` mapping).

    python3 -m rediacc_ci.core.toolchain normalize <text>
        the dotted-numeric run out of a `--version` line, matching the strip
        pipeline at toolchain.sh:88-93.

    python3 -m rediacc_ci.core.toolchain compare <a> <b>
        prints -1, 0 or 1. Exit 0 unless a version cannot be parsed.

    python3 -m rediacc_ci.core.toolchain at-least <have> <want>
        exit 0 when have >= want, 1 when it does not. The predicate shape of
        `sort -V -C`, without the subprocess and without the GNU dependency.
"""

from __future__ import annotations

import pathlib
import re
import sys
from itertools import zip_longest

from rediacc_ci import paths

# <root>/.devcontainer/toolchain.env, as parts rather than a joined string so the
# separator is the platform's and the path is greppable one component at a time.
PINS_RELPATH = (".devcontainer", "toolchain.env")

# THE ONLY LINES THAT ARE PINS, and the pattern is copied from the bash rather
# than re-derived: `grep -E '^[A-Z][A-Z0-9_]*='` at toolchain.sh:45. Both readers
# must agree about what a pin line is, because one of them feeds $GITHUB_ENV and
# the other decides a gate's verdict.
PAIR_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")

# The tool -> key mapping, mirroring the `case` in `toolchain_pin_for`
# (.ci/scripts/lib/toolchain.sh:107-117). Kept as data because the tests compare
# it against the arms of that case, so a tool added to one and not the other is a
# red rather than a silent "no pin defined".
TOOL_KEYS = {
    "shfmt": "SHFMT_VERSION",
    "shellcheck": "SHELLCHECK_VERSION",
    "ruff": "RUFF_VERSION",
    "actionlint": "ACTIONLINT_VERSION",
    "go": "GO_VERSION",
    "node": "NODE_VERSION",
    "uv": "UV_VERSION",
    "pytest": "PYTEST_VERSION",
}

# The two Node keys, named because they are different KINDS of number and the
# difference is the one this file's history is made of. NODE_VERSION is the major
# CI installs; NODE_VERSION_MIN is the oldest release the repo agrees to run on,
# and nothing installs it -- every consumer only compares against it.
NODE_MAJOR_KEY = "NODE_VERSION"
NODE_FLOOR_KEY = "NODE_VERSION_MIN"

# Stripped in this order, each at most once: `out="${out#v}"` then
# `out="${out#go}"` at toolchain.sh:89-90. Order is preserved because it is
# observable -- `vgo1.2` loses both prefixes, `gov1.2` loses only the `go`.
VERSION_PREFIXES = ("v", "go")

# The leading dotted-numeric run, matching `grep -oE '^[0-9]+(\.[0-9]+)*'` at
# toolchain.sh:91. Anchored, so `go version go1.26.6 linux/arm64` does not yield
# a number from the middle of the line after the prefixes come off.
NUMERIC_RUN_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)*")


class PinError(RuntimeError):
    """A pin is absent, empty, or the pins file could not be read.

    A distinct type rather than a bare RuntimeError for the same reason
    `paths.RootError` is one: a caller must be able to tell "your pins are
    broken" from any other failure without matching a message string, and the
    gate controls assert on the type.
    """


class VersionError(ValueError):
    """A string that has to be a version is not one.

    Raised rather than returning an empty tuple, because an empty tuple compares
    equal to another empty tuple and two unparseable versions would then be
    "the same version" -- vacuity inside the comparison this module exists to
    make trustworthy.
    """


def pins_file(root: pathlib.Path | None = None) -> pathlib.Path:
    """`<root>/.devcontainer/toolchain.env`. See the module docstring on WHERE."""
    return paths.from_root(*PINS_RELPATH, root=root)


def load_pins(path: pathlib.Path | str | None = None) -> dict[str, str]:
    """Every KEY=value pin in the file, as a dict. Raises PinError.

    THREE REFUSALS, and the third is the anti-vacuity one:

      * the file cannot be read at all,
      * a key is defined twice with two different values (bash's `.` would take
        the last silently, and a pins file that contradicts itself is a defect
        whichever value wins),
      * the file parses to ZERO pairs. A dict that is empty answers every
        subsequent `key in pins` with False, so a caller reading a moved,
        emptied or comment-only file would get "no pin defined for shellcheck"
        -- a message that sends the reader to the tool rather than to the file.

    Comment and blank lines are skipped, exactly as `grep -E '^[A-Z]...'` skips
    them. Nothing here validates that a VALUE is well formed; assertion A3 of
    `.ci/scripts/quality/check-toolchain-pins.sh` owns that rule and owns its
    "at least 5 keys" floor, and duplicating either here would be a second place
    to update the day it changes.
    """
    target = pins_file() if path is None else pathlib.Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise PinError(
            "toolchain: pins file missing or unreadable: %s (%s)" % (target, exc)
        ) from exc

    pins: dict[str, str] = {}
    for line in text.splitlines():
        matched = PAIR_RE.match(line)
        if matched is None:
            continue
        key, value = matched.group(1), matched.group(2)
        if key in pins and pins[key] != value:
            raise PinError(
                "toolchain: %s is defined twice in %s with different values "
                "(%r then %r) -- one of them is dead and nobody can tell which"
                % (key, target, pins[key], value)
            )
        pins[key] = value

    if not pins:
        raise PinError(
            "toolchain: %s defines no KEY=value pin at all. An empty pin table "
            "answers every lookup with 'no pin defined for <tool>', which names "
            "the tool instead of the file." % target
        )
    return pins


def pin(key: str, pins: dict[str, str] | None = None) -> str:
    """One pin by KEY NAME. Raises PinError when it is absent or empty.

    NO `default=` PARAMETER, and that omission is the point of the function. See
    the module docstring: the empty pin that reached a download URL, and the
    composed `"${NODE_VERSION}.0.0"` floor that silently read 22.0.0, are both
    what a default looks like on the day it is wrong.
    """
    table = load_pins() if pins is None else pins
    if key not in table:
        raise PinError(
            "toolchain: no pin named %s. Defined keys: %s"
            % (key, ", ".join(sorted(table)) or "(none)")
        )
    value = table[key].strip()
    if not value:
        raise PinError(
            "toolchain: pin %s is EMPTY. An empty version interpolates into a "
            "download URL and returns a 404 that names the server rather than "
            "the missing pin." % key
        )
    return value


def pin_for(tool: str, pins: dict[str, str] | None = None) -> str:
    """One pin by TOOL name, the `toolchain_pin_for` mapping. Raises PinError.

    An unknown tool is a refusal and not an empty string, matching the bash's
    `*) return 2 ;;` -- exit 2 there is "you asked something I have no answer
    for", which is a different thing from "the answer is nothing".
    """
    if tool not in TOOL_KEYS:
        raise PinError(
            "toolchain: no pin defined for %r. Known tools: %s"
            % (tool, ", ".join(sorted(TOOL_KEYS)))
        )
    return pin(TOOL_KEYS[tool], pins)


def node_major(pins: dict[str, str] | None = None) -> str:
    """NODE_VERSION -- the bare major CI installs. Raises PinError."""
    return pin(NODE_MAJOR_KEY, pins)


def node_floor(pins: dict[str, str] | None = None) -> str:
    """NODE_VERSION_MIN -- the oldest release this repo runs on. Raises PinError.

    Nothing installs this number; every consumer compares against it
    (rdc.sh:123 and :161, run.sh's toolchain step, `.ci/lib/setup.sh`'s
    install-or-skip decision, and engines.node in two manifests). It is
    therefore the single most likely value to be compared as a string by
    accident, which is what `compare()` below is for.
    """
    return pin(NODE_FLOOR_KEY, pins)


def normalize_version(text: str) -> str:
    """The dotted-numeric run out of a version string. Raises VersionError.

    The same pipeline as toolchain.sh:88-93 -- strip a leading `v`, then a
    leading `go`, then keep the leading dotted-numeric run -- so `v22.23.2`,
    `go1.26.6` and a bare `3.13.1` all normalise, and a `--version` line that
    printed no number at all raises instead of yielding "".

    THE EMPTY CASE IS THE ONE THAT MATTERS. The bash comment above its own probe
    table says it: "a normaliser that silently yields '' would make a comparison
    of ''=='' pass -- vacuity inside the very check meant to prevent it."
    """
    raw = text.strip()
    # BOTH prefixes, in order, each at most once -- NOT "the first one that
    # matches". `${out#v}` and `${out#go}` are two consecutive statements in the
    # bash, so `vgo1.2` loses both and normalises to `1.2`. The first draft here
    # broke out of the loop after the first hit and the frozen-bash differential
    # caught it on exactly that input; the loop is written open for that reason.
    for prefix in VERSION_PREFIXES:
        raw = raw.removeprefix(prefix)
    matched = NUMERIC_RUN_RE.match(raw)
    if matched is None:
        raise VersionError(
            "toolchain: %r carries no version number. Refusing to treat it as "
            "one: an empty version compares equal to another empty version." % text
        )
    return matched.group(0)


def parse_version(text: str) -> tuple[int, ...]:
    """A version as a tuple of INTEGERS. Raises VersionError.

    Integers, not strings, and that single word is the whole defect this module
    guards: as strings "13" sorts before "9", so 22.13.0 reads as older than
    22.9.0 and a floor of 22.13.0 admits the release it was raised to exclude.
    """
    return tuple(int(field) for field in normalize_version(text).split("."))


def compare(left: str, right: str) -> int:
    """-1, 0 or 1, comparing field by field. Raises VersionError on either side.

    Missing trailing fields are ZEROS and not "unknown", so `22` == `22.0.0` and
    `22` < `22.13.0`. That is what `sort -V` does, and it is what NODE_VERSION
    (a bare major) needs from every caller that compares it against a full
    version.
    """
    for a, b in zip_longest(parse_version(left), parse_version(right), fillvalue=0):
        if a != b:
            return -1 if a < b else 1
    return 0


def at_least(have: str, want: str) -> bool:
    """`have >= want`. The predicate shape of `sort -V -C`, without coreutils.

    `printf '%s\\n%s\\n' "$min" "$cur" | sort -V -C` is how the four bash callers
    ask this today (.ci/lib/local-common.sh:429, .ci/lib/setup.sh:57 and :351).
    It is correct and it is a subprocess and a GNU dependency per question; this
    is neither, and the tests run both over a corpus to prove they agree.
    """
    return compare(have, want) >= 0


def same_major(have: str, want: str) -> bool:
    """Do two versions share a leading field? Raises VersionError.

    Exists for NODE_VERSION specifically. toolchain.sh:147-151 special-cases it
    with `${actual%%.*}` because the pin is a bare major, and putting that branch
    here means a caller comparing against NODE_VERSION cannot forget it -- which
    is the mistake that produces "node 22.23.2 != pinned 22".
    """
    return parse_version(have)[0] == parse_version(want)[0]


# ---------------------------------------------------------------------------
# argv dispatch -- the surface a bash caller reaches
# ---------------------------------------------------------------------------


def _fail(message: str) -> int:
    """Message on STDERR, nothing on stdout, exit 1.

    The empty stdout is the contract, not a side effect: every bash caller reads
    these verbs with `v="$(...)"`, and a diagnostic printed on stdout would be
    captured INTO the variable and then interpolated into whatever the value was
    for. That is the same stream discipline `differential.py` exists to keep
    testable.
    """
    print(message, file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    if not argv:
        print(
            "usage: python3 -m rediacc_ci.core.toolchain <verb> [args]",
            file=sys.stderr,
        )
        return 2
    verb, rest = argv[0], argv[1:]

    if verb in ("pairs", "keys"):
        try:
            table = load_pins()
        except PinError as exc:
            return _fail(str(exc))
        for key in table:
            print(key if verb == "keys" else "%s=%s" % (key, table[key]))
        return 0

    if verb in ("value", "pin"):
        if not rest:
            return _fail("toolchain: %s needs one argument" % verb)
        try:
            print(pin(rest[0]) if verb == "value" else pin_for(rest[0]))
        except PinError as exc:
            return _fail(str(exc))
        return 0

    if verb == "normalize":
        if not rest:
            return _fail("toolchain: normalize needs one argument")
        try:
            print(normalize_version(rest[0]))
        except VersionError as exc:
            return _fail(str(exc))
        return 0

    if verb == "compare":
        if len(rest) < 2:
            return _fail("toolchain: compare needs two arguments")
        try:
            print(compare(rest[0], rest[1]))
        except VersionError as exc:
            return _fail(str(exc))
        return 0

    if verb == "at-least":
        # The ANSWER IS THE EXIT CODE, as `sort -V -C` answers it, so a caller
        # writes `if ... at-least "$cur" "$min"; then`. An unparseable version
        # is exit 2: "I could not tell", which must not read as "too old".
        if len(rest) < 2:
            return _fail("toolchain: at-least needs two arguments")
        try:
            return 0 if at_least(rest[0], rest[1]) else 1
        except VersionError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    return _fail("unknown verb: %s" % verb)


__all__ = [
    "NODE_FLOOR_KEY",
    "NODE_MAJOR_KEY",
    "NUMERIC_RUN_RE",
    "PAIR_RE",
    "PINS_RELPATH",
    "TOOL_KEYS",
    "VERSION_PREFIXES",
    "PinError",
    "VersionError",
    "at_least",
    "compare",
    "load_pins",
    "node_floor",
    "node_major",
    "normalize_version",
    "parse_version",
    "pin",
    "pin_for",
    "pins_file",
    "same_major",
]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
