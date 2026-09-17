"""The pinned gate toolchain as DATA, and a version comparison that is correct.

PORTED FROM the loading and comparison half of `.ci/scripts/lib/toolchain.sh`.
That file still exists and keeps its function names and its acquisition half; what
moves here is the part every OTHER reader of the pins already reimplements -- `.ci/config/constants.sh`, `.ci/bootstrap.sh`, `.ci/lib/setup.sh` and `.github/workflows/*` each open `.devcontainer/toolchain.env` in their own way, and only one of them refuses when a pin is missing.

--------------------------------------------------------------------------
WHERE THE PINS FILE IS, AND WHY THAT IS NOT `.ci/config/`
--------------------------------------------------------------------------
`<root>/.devcontainer/toolchain.env`, resolved through `rediacc_ci.paths` rather than counted in `..` hops. The pins file's own header states the reason it lives there and not beside the other config: the devcontainer image build context IS `.devcontainer/` (.github/workflows/ci-build-docker.yml:558, .ci/lib/devbox.sh:263), `COPY` cannot reach outside a build context, and widening
the context to the repo root would upload the whole tree plus submodules on every image build. So the path is a decision, and this module reads it rather than guessing at one.

`toolchain_pins_file` in the bash computes the same path with
`cd "$(dirname "${BASH_SOURCE[0]}")/../../.."`. The two are asserted equal by
`test_core_toolchain.py`, so a file move that updates one and not the other is a red rather than two readers of two different files.

--------------------------------------------------------------------------
WHY A MISSING OR EMPTY PIN RAISES, AND NEVER DEFAULTS
--------------------------------------------------------------------------
This is the whole reason the module is more than a two-line parser, so it is argued rather than asserted.

`toolchain_pin_for` used to return "" WITH EXIT CODE 0 when the pins had not been loaded, and that empty string travelled into a download URL. The receipt is in the bash, measured 2026-08-26 on a fresh shell:

    .../releases/download/v/shellcheck-v.linux.aarch64.tar.xz  -> curl 404

The 404 names GitHub, not the missing pin, so the debugging starts in the wrong place. `toolchain_check` and `toolchain_acquire` each grew their own `[[ -n "$pin" ]]` guard afterwards, and the asymmetry between them -- one entry point refusing while the other interpolated -- is recorded in `.ci/scripts/lib/toolchain.sh:452-457` as the defect that let it happen.

`.ci/config/constants.sh` reaches the same conclusion in the other direction and
spells it in bash: `readonly NODE_VERSION_MIN="${NODE_VERSION_MIN:?NODE_VERSION_MIN
not sourced from toolchain.env}"` (constants.sh:58, and the same `:?` form at :44
and :234). `:?` is bash's "fail loudly rather than default", and it is there because the key it guards REPLACED a composed default: constants.sh used to build
the floor as `"${NODE_VERSION}.0.0"`, a defensible-looking line that silently
yielded 22.0.0 while both manifests said >=22.13.0. The looser of two floors was
the one every shell path enforced, and a machine on Node 22.4 passed `./run.sh setup` and then failed inside npm.

So: `pin()` raises `PinError` on an absent key, on an empty value, and on a pins
file that parses to no pairs at all. There is no `default=` parameter, on purpose
-- a default is how the 22.0.0 floor happened, and adding one here would let it happen again in Python.

--------------------------------------------------------------------------
WHY THE COMPARISON IS FIELD-WISE INTEGER AND NOT A STRING COMPARE
--------------------------------------------------------------------------
    "22.13.0" < "22.9.0"     is TRUE as strings, and FALSE as versions

One character decides it: '1' sorts before '9'. Every floor check in this repo is exactly this shape -- `check_node_version` compares the running Node against
NODE_VERSION_MIN=22.13.0 -- so a string compare would wave through the very
release the floor was raised to exclude, and would do it silently, in the direction that reads as a pass.

The bash gets this right today by delegating to `sort -V` (.ci/lib/local-common.sh:429, .ci/lib/setup.sh:57 and :351), which is GNU coreutils and is a subprocess per comparison. `compare()` here is checked against `sort -V` on a corpus in the tests, so the port is proven equivalent rather than merely plausible, and `test_core_toolchain.py` additionally proves the corpus is one a
string compare FAILS -- a differential nobody can pass by accident.

Shorter is not smaller: `22` and `22.0.0` compare equal, because the missing fields are zeros and not "unknown". That matters for NODE_VERSION, which is a BARE MAJOR (`22`) while every other pin in the file is a full version.
`same_major()` exists for exactly that key, mirroring the `${actual%%.*}` branch
at toolchain.sh:147-151 rather than making every caller remember which pins are majors.

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

    -- added with the acquisition half (W7P5-b) --

    python3 -m rediacc_ci.core.toolchain lane
        `ci`, `devbox` or `host`, matching `toolchain_lane`.

    python3 -m rediacc_ci.core.toolchain cache-dir
        where an acquired tool is cached, matching `toolchain_cache_dir`.

    python3 -m rediacc_ci.core.toolchain probe <tool> [binary]
        the version that binary reports. Exit 1 when it would not say, 2 for a
        tool with no probe arm.

    python3 -m rediacc_ci.core.toolchain check <tool>
        the binary on PATH IF it is at the pin. The refusal goes to stderr and
        the path to stdout, so `bin="$(... check shfmt)" || die` behaves the way
        `toolchain_check` already does. Exit 1 not-at-the-pin, 2 no such pin.

    python3 -m rediacc_ci.core.toolchain acquire <tool>
        the same, installing shfmt or shellcheck at the pin when it is absent.

    python3 -m rediacc_ci.core.toolchain report
    python3 -m rediacc_ci.core.toolchain verify
        the per-lane table. `verify` EXITS 1 ON A MISMATCH, which its bash
        counterpart does not; see DEFECT 1 in the acquisition section below.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import pathlib
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from itertools import zip_longest

from rediacc_ci import paths

# <root>/.devcontainer/toolchain.env, as parts rather than a joined string so the separator is the platform's and the path is greppable one component at a time.
PINS_RELPATH = (".devcontainer", "toolchain.env")

# THE ONLY LINES THAT ARE PINS, and the pattern is copied from the bash rather
# than re-derived: `grep -E '^[A-Z][A-Z0-9_]*='` at toolchain.sh:45. Both readers
# must agree about what a pin line is, because one of them feeds $GITHUB_ENV and the other decides a gate's verdict.
PAIR_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")

# The tool -> key mapping, mirroring the `case` in `toolchain_pin_for` (.ci/scripts/lib/toolchain.sh:107-117). Kept as data because the tests compare it against the arms of that case, so a tool added to one and not the other is a red rather than a silent "no pin defined".
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

# The two Node keys, named because they are different KINDS of number and the difference is the one this file's history is made of. NODE_VERSION is the major
# CI installs; NODE_VERSION_MIN is the oldest release the repo agrees to run on,
# and nothing installs it -- every consumer only compares against it.
NODE_MAJOR_KEY = "NODE_VERSION"
NODE_FLOOR_KEY = "NODE_VERSION_MIN"

# Stripped in this order, each at most once: `out="${out#v}"` then
# `out="${out#go}"` at toolchain.sh:89-90. Order is preserved because it is
# observable -- `vgo1.2` loses both prefixes, `gov1.2` loses only the `go`.
VERSION_PREFIXES = ("v", "go")

# The leading dotted-numeric run, matching `grep -oE '^[0-9]+(\.[0-9]+)*'` at toolchain.sh:91. Anchored, so `go version go1.26.6 linux/arm64` does not yield a number from the middle of the line after the prefixes come off.
NUMERIC_RUN_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)*")


class PinError(RuntimeError):
    """A pin is absent, empty, or the pins file could not be read.

    A distinct type rather than a bare RuntimeError for the same reason `paths.RootError` is one: a caller must be able to tell "your pins are broken" from any other failure without matching a message string, and the gate controls assert on the type.
    """


class VersionError(ValueError):
    """A string that has to be a version is not one.

    Raised rather than returning an empty tuple, because an empty tuple compares equal to another empty tuple and two unparseable versions would then be "the same version" -- vacuity inside the comparison this module exists to make trustworthy.
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
    `.ci/scripts/quality/check-toolchain-pins.sh` owns that rule and owns its "at least 5 keys" floor, and duplicating either here would be a second place to update the day it changes.
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
    (rdc.sh:123 and :161, run.sh's toolchain step, `.ci/lib/setup.sh`'s install-or-skip decision, and engines.node in two manifests). It is therefore the single most likely value to be compared as a string by accident, which is what `compare()` below is for.
    """
    return pin(NODE_FLOOR_KEY, pins)


def normalize_version(text: str) -> str:
    """The dotted-numeric run out of a version string. Raises VersionError.

    The same pipeline as toolchain.sh:88-93 -- strip a leading `v`, then a leading `go`, then keep the leading dotted-numeric run -- so `v22.23.2`, `go1.26.6` and a bare `3.13.1` all normalise, and a `--version` line that printed no number at all raises instead of yielding "".

    THE EMPTY CASE IS THE ONE THAT MATTERS. The bash comment above its own probe table says it: "a normaliser that silently yields '' would make a comparison
    of ''=='' pass -- vacuity inside the very check meant to prevent it."
    """
    # NO `.strip()`, AND THAT IS A CORRECTION rather than an omission. This line
    # read `raw = text.strip()` until 2026-09-10, which made the port ACCEPT an
    # input the twin refuses. Measured on both sides, same input:
    #
    # printf ' 3.1' -> bash toolchain.sh:88-93 refuses (grep is anchored at `^`, and a leading space is not a digit) -> normalize_version(" 3.1") returned "3.1"
    #
    # The permissive direction is the wrong one for this function: it feeds `parse_version`, `compare` and `at_least`, so a padded string would have compared as a version where the bash floor check would have refused it. `NUMERIC_RUN_RE` is already anchored, so dropping the strip is the whole
    # fix; a TRAILING space or newline still normalises on both sides, because
    # the anchored run simply stops before it.
    raw = text
    # BOTH prefixes, in order, each at most once -- NOT "the first one that
    # matches". `${out#v}` and `${out#go}` are two consecutive statements in the
    # bash, so `vgo1.2` loses both and normalises to `1.2`. The first draft here broke out of the loop after the first hit and the frozen-bash differential
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

    Integers, not strings, and that single word is the whole defect this module guards: as strings "13" sorts before "9", so 22.13.0 reads as older than 22.9.0 and a floor of 22.13.0 admits the release it was raised to exclude.
    """
    return tuple(int(field) for field in normalize_version(text).split("."))


def compare(left: str, right: str) -> int:
    """-1, 0 or 1, comparing field by field. Raises VersionError on either side.

    Missing trailing fields are ZEROS and not "unknown", so `22` == `22.0.0` and
    `22` < `22.13.0`. That is what `sort -V` does, and it is what NODE_VERSION (a bare major) needs from every caller that compares it against a full version.
    """
    for a, b in zip_longest(parse_version(left), parse_version(right), fillvalue=0):
        if a != b:
            return -1 if a < b else 1
    return 0


def at_least(have: str, want: str) -> bool:
    """`have >= want`. The predicate shape of `sort -V -C`, without coreutils.

    `printf '%s\\n%s\\n' "$min" "$cur" | sort -V -C` is how the four bash callers ask this today (.ci/lib/local-common.sh:429, .ci/lib/setup.sh:57 and :351).
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


# --------------------------------------------------------------------------- THE PROBING AND ACQUISITION HALF (W7P5-b, 2026-09-10)
#
# Everything above this line was ported in W6P2 and covers `toolchain_load`, `toolchain_pairs`, `toolchain_keys`, `toolchain_pin_for` and the comparison. Everything below is the REST OF THE TWIN: `toolchain_probe_version`, `toolchain_check`, `toolchain_lane`, `toolchain_report`, `toolchain_cache_dir` and the whole acquisition apparatus (`_toolchain_need_checksums`,
# `_toolchain_sha256sum`, `_toolchain_os`, `_toolchain_download_shfmt`, `_toolchain_acquire_shfmt`, `_toolchain_acquire_shellcheck`, `toolchain_acquire`). Six real sourcers of the twin, re-measured 2026-09-10
# with `grep -rnP '^\s*(source|\.)\s+.*\btoolchain\.sh'`:
# `.ci/bootstrap.sh:75`, `.ci/legacy/run-legacy.sh:46`, `.ci/scripts/quality/check-python-lint.sh:139`, `.ci/scripts/security/shellcheck.sh:24`, `.ci/scripts/security/shfmt.sh:19`, `.ci/scripts/test/gates/test-toolchain.sh:25`. NOT the "466" in the programme plan, which is this file's LINE COUNT.
#
# -------------------------------------------------------------------------- DEFECT 1, REPRODUCED NOT FIXED, AND IT IS THE CONSEQUENTIAL ONE: `toolchain.sh --verify` CANNOT FAIL. -------------------------------------------------------------------------- `.ci/scripts/lib/toolchain.sh:167` states the contract in the file's own words: "toolchain.sh --verify exit 1 if any pinned tool
# is absent or mismatched". It does not, and cannot. The dispatch block at :211-221 is positioned at line 211 with 245 more lines of function definitions after it, and NONE of its `--report`, `--verify` or `--env` arms calls `exit` (only the usage arm does, at :218). So control falls out of the `fi`, defines the acquisition helpers, and the script exits with the status of the last
# function definition, which is always 0.
#
# Driven live on 2026-09-10, bash 5.3.9:
#
#     PATH=/usr/bin:/bin bash .ci/scripts/lib/toolchain.sh --verify
# lane: host tool pinned actual status shfmt 3.13.1 absent MISMATCH shellcheck 0.10.0 absent MISMATCH ruff 0.16.1 absent MISMATCH actionlint 1.7.12 absent MISMATCH go 1.26.6 absent MISMATCH node 22 absent MISMATCH
#       EXIT=0
#
# Six MISMATCH lines and a green exit. `toolchain_report --verify` (the
# FUNCTION) is correct and returns 1; only the script's dispatch throws that
# away.
#
# BLAST RADIUS, MEASURED. `--verify` has ZERO call sites anywhere in the tree (`grep -rn 'toolchain\.sh --'` finds only `--report` and `--env`), so nothing is green today because of it. It is a gate-shaped verb that is advertised in the file's own help text and would be always-green the moment anyone wired it into CI, which is exactly the vacuity class this programme exists to
# remove.
#
# THE SAME DEFECT HAS A LIVE VARIANT ON `--env`, which DOES have two call sites (`.github/workflows/ci-quality.yml:171` and `:1897`, both `.ci/scripts/lib/toolchain.sh --env >> "$GITHUB_ENV"`). Driven live against a fake root with no pins file:
#
# bash /tmp/tcroot/.ci/scripts/lib/toolchain.sh --env
#       EXIT=0, ZERO bytes on stdout
# stderr: grep: /tmp/tcroot/.devcontainer/toolchain.env: No such file
#
# A missing or unreadable pins file therefore appends NOTHING to $GITHUB_ENV and the step stays green, after which every later step in the job sees unset pins. `set -eo pipefail` (the Actions default) does not help, because the script genuinely exits 0. `--report` is the third arm and behaves the same way: `toolchain_report` returns 2 on a missing pins file, and the script still
# exits 0.
#
# THIS PORT DOES NOT REPRODUCE THE ALWAYS-ZERO EXIT, and the asymmetry is deliberate: the defect lives in the SCRIPT'S DISPATCH, not in the library
# function, and this module is the library. `report()` returns the twin's
# function-level rc, `main("verify")` honours it, and `test_core_toolchain.py`
# pins that the twin's dispatch still has the bug, so the pin goes red the day somebody fixes the twin.
#
# -------------------------------------------------------------------------- DEFECT 2, REPRODUCED NOT FIXED: "CHECKSUM MISMATCH" IS PRINTED WHEN THERE IS NO CHECKSUM TOOL TO MISMATCH WITH. -------------------------------------------------------------------------- `_toolchain_sha256sum` (:282-291) exists precisely so that "a verifier that cannot run must not read as a verifier that
# failed" (:264-265), and it does
# return a distinct message when neither `sha256sum` nor `shasum` is present.
# BOTH CALL SITES THEN DISCARD IT: `:344` and `:429` are `... | _toolchain_sha256sum -c - >/dev/null 2>&1`, and the `2>/dev/null` swallows the very message the helper was written to print.
#
# Driven live on 2026-09-10 with a PATH holding only the coreutils the function needs and a stub `curl`, so that neither hashing tool is reachable:
#
# toolchain: shfmt checksum MISMATCH -- refusing to install expected fb096c5d1ac6beabbdbaa2874d025badb03ee07929f0c9ff67563ce8c75398b1 toolchain: no sha256 tool on PATH (need sha256sum or shasum) -- cannot verify a download actual
#
# The distinguishing line survives only because the SECOND, unredirected call inside the `actual` line leaks it, and it lands out of order (before the line it belongs to) with an EMPTY `actual`. The headline still says MISMATCH.
# 2 call sites; both download helpers. It fails CLOSED, so nothing unverified is
# installed and it is not security-relevant; it is a diagnosis defect, and the
# comment above it claims otherwise.
#
# `sha256_of` below uses `hashlib`, so this port has no verifier that can be absent. That is the same argument `.ci/lib/find-port.sh` made when its own `_sha256sum_portable` died in W7 phase 1, and the twin's comment at :274-277 already anticipates it.
#
# -------------------------------------------------------------------------- DEFECT 3, DOCUMENTATION ONLY: TWO COMMENTS ARE STALE IN THE DIRECTION THAT TELLS A READER TO ADD A CONSTANT THAT IS ALREADY THERE. -------------------------------------------------------------------------- `:328-331` says "Only the LINUX_* pair exists in constants.sh today, so a Mac lands in the refusal
# below". `:401-404` says "adding the two DARWIN_* constants is all a Mac needs". Both DARWIN pairs have since been added: `SHFMT_SHA256_DARWIN_AMD64`/`_ARM64` at `.ci/config/constants.sh:280-281` and `SHELLCHECK_SHA256_DARWIN_X86_64`/`_AARCH64` at `:262-263`. No behaviour is
# wrong; the comments describe a tree that no longer exists.
# ---------------------------------------------------------------------------


# `${CI_TEMP:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}}` at toolchain.sh:258, in order.
# `:-` treats an EMPTY value as unset, which `os.environ.get(...) or ...` also
# does; that is why the chain below is `or` and not a `in os.environ` test.
CACHE_ENV_ORDER = ("CI_TEMP", "RUNNER_TEMP", "TMPDIR")
CACHE_DIR_NAME = "rediacc-toolchain"

# The SHA256 pins live in `.ci/config/constants.sh` rather than in `toolchain.env`, because the Dockerfile has no use for them. Only these two
# families are read here; the constants file holds others (nfpm, actionlint)
# that belong to other acquirers.
SHA_KEY_RE = re.compile(r"^(?:SHFMT|SHELLCHECK)_SHA256_[A-Z0-9_]+$")

# `readonly NAME="value"` as constants.sh writes it. Anchored and quote-aware
# rather than a loose split, so a commented-out line or a `readonly` inside a heredoc cannot contribute a checksum.
CONSTANTS_ASSIGN_RE = re.compile(r'^readonly\s+([A-Z][A-Z0-9_]*)="([^"]*)"\s*$', re.MULTILINE)

# The two probe guards `_toolchain_need_checksums` (:249) reads before deciding whether to source constants.sh at all. Reproduced by name because WHICH two they are is observable: exporting either one suppresses the file read entirely, so the other family then resolves from the environment or not at all.
CHECKSUM_PROBE_KEYS = ("SHELLCHECK_SHA256_LINUX_X86_64", "SHFMT_SHA256_LINUX_AMD64")

# The six tools `toolchain_report` walks, IN ITS ORDER (:196). Order is observable: the report prints one row per tool in this sequence.
#
# uv and pytest are pinned and probeable and are deliberately NOT here. The twin's reason at :189-195: `--verify` returns non-zero on any MISMATCH and runs in lanes that have no business owning a Python toolchain, so a host without uv would start failing a check it passed yesterday for a tool it is not being asked to have. `.ci/bootstrap.sh --check` reports those two, and it can
# also FIX the answer.
REPORT_TOOLS = ("shfmt", "shellcheck", "ruff", "actionlint", "go", "node")

# The tools with a dedicated acquisition arm (:458-460). Everything else falls through to a bare re-check.
ACQUIRE_TOOLS = ("shfmt", "shellcheck")

# uname -m to the arch spelling each UPSTREAM uses in its asset names. Two tables, not one, because the two projects disagree: shfmt publishes `amd64`/`arm64`, shellcheck publishes `x86_64`/`aarch64`, and collapsing them would 404 on one of the two.
SHFMT_ARCH = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
SHELLCHECK_ARCH = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "aarch64",
}


class ToolError(RuntimeError):
    """A tool this library has no arm for. The bash's `*) return 2 ;;`.

    Distinct from `PinError`, because "I have never heard of this tool" and "this tool's pin is missing" want different fixes and the twin gives them different exit codes at `toolchain_check:130-137`.
    """


@dataclasses.dataclass(frozen=True)
class CheckResult:
    """What `toolchain_check` answers with: a binary, a reason, and an rc.

    THREE FIELDS AND NOT A bool, because the twin's answer is genuinely three things and the callers use all of them: `.ci/scripts/security/shfmt.sh:48` wants the PATH, `.ci/legacy/run-legacy.sh:406` re-runs it purely to print the REASON, and `toolchain_report:199` wants only the rc. Collapsing any two of them would push the reconstruction into every caller.
    """

    tool: str
    binary: str | None
    rc: int
    messages: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.rc == 0


def lane(env: dict[str, str] | None = None) -> str:
    """`ci`, `devbox` or `host`. `toolchain_lane` (toolchain.sh:174-182).

    The order matters and is the twin's: $GITHUB_ACTIONS first, so a devbox
    running inside Actions still reports `ci`; then $REDIACC_NPM_RUNTIME (which
    DEFAULTS to `host`, so an unset value is not devbox) or the presence of
    `/.dockerenv`; then host.
    """
    table = os.environ if env is None else env
    if table.get("GITHUB_ACTIONS"):
        return "ci"
    if (table.get("REDIACC_NPM_RUNTIME") or "host") == "devbox":
        return "devbox"
    if pathlib.Path("/.dockerenv").exists():
        return "devbox"
    return "host"


def cache_dir(env: dict[str, str] | None = None) -> pathlib.Path:
    """`toolchain_cache_dir` (:257-259). Never created here, only named."""
    table = os.environ if env is None else env
    base = ""
    for key in CACHE_ENV_ORDER:
        base = table.get(key) or ""
        if base:
            break
    return pathlib.Path(base or "/tmp") / CACHE_DIR_NAME


def os_name(system: str | None = None) -> str:
    """`linux` or `darwin`. Raises ToolError on anything else.

    `_toolchain_os` (:303-312). LOWERCASE, because that is the spelling both
    upstreams use in their asset names; the callers uppercase it to build the
    checksum variable name.

    THE OS IS DERIVED AND NOT ASSUMED, and the twin's comment says why in the one sentence worth carrying over: both download URLs used to hard-code `linux` while deriving only the arch from `uname -m`, so on an arm64 Mac the ARM64 checksum matched, a LINUX binary downloaded, verified, got `chmod +x`, and failed much later with "cannot execute binary file" from a gate that had no
    idea it had installed another operating system's tool.
    """
    value = platform.system() if system is None else system
    if value == "Linux":
        return "linux"
    if value == "Darwin":
        return "darwin"
    raise ToolError(
        "toolchain: unsupported OS '%s' -- no pinned build of this tool exists for it" % value
    )


def sha256_of(path: pathlib.Path | str) -> str:
    """The sha256 of a file, as lowercase hex.

    THIS IS THE WHOLE ARGUMENT FOR THE PORT IN ONE FUNCTION. The twin needs `_toolchain_sha256sum` (:282-291) only because bash has no hash function, and
    that shim was the THIRD copy of itself in this repository; the twin's own
    comment at :274-277 records the second one dying when `.ci/lib/find-port.sh` started delegating to `rediacc_ci.core.ports`. `hashlib` has no macOS branch to write and no verifier that can be absent, so DEFECT 2 above cannot exist here.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def constants_file(root: pathlib.Path | None = None) -> pathlib.Path:
    """`<root>/.ci/config/constants.sh`, where the SHA256 pins live.

    The twin computes the same path from `${BASH_SOURCE[0]}/../../..` at :251.
    A test asserts the two agree, so a file move that updates one and not the other is a red rather than two readers of two different files.
    """
    return paths.ci_dir(root) / "config" / "constants.sh"


def checksums(
    env: dict[str, str] | None = None,
    constants_path: pathlib.Path | str | None = None,
) -> dict[str, str]:
    """The SHFMT_/SHELLCHECK_ SHA256 pins. `_toolchain_need_checksums` (:248-255).

    THE SHORT-CIRCUIT IS REPRODUCED, INCLUDING ITS ODD SHAPE. The bash returns early when EITHER `SHELLCHECK_SHA256_LINUX_X86_64` or `SHFMT_SHA256_LINUX_AMD64` is already set, and in that case never reads constants.sh at all. So exporting one family's linux key suppresses the file read for BOTH families, and the other family then resolves only from the environment. That is
    observable, a caller could depend on it, and it is not this module's to change.

    When the file IS read, the FILE WINS over an inherited environment value,
    because `readonly NAME="..."` in a fresh shell overwrites a plain variable
    of the same name. Reproducing that ordering is the difference between a stale exported hash being used and being ignored.
    """
    table = os.environ if env is None else env
    from_env = {key: value for key, value in table.items() if SHA_KEY_RE.match(key) and value}
    if any(table.get(key) for key in CHECKSUM_PROBE_KEYS):
        return from_env
    path = pathlib.Path(constants_path) if constants_path else constants_file()
    merged = dict(from_env)
    if path.is_file():
        text = path.read_text(encoding="utf-8", errors="replace")
        merged.update(
            {
                name: value
                for name, value in CONSTANTS_ASSIGN_RE.findall(text)
                if SHA_KEY_RE.match(name)
            }
        )
    return merged


# --------------------------------------------------------------------------- Version probing: what a binary says it is ---------------------------------------------------------------------------


def _probe_argv(tool: str, binary: str) -> list[str]:
    """The exact argv the twin runs for one tool. Raises ToolError.

    `$bin` IS UNQUOTED FOR ruff, uv AND pytest in the bash (:76, :84, :85) and quoted for the rest, so those three accept a MULTI-WORD runner such as `uv tool run pytest`, which is how pytest exists at all on a host with no
    pip. `shlex.split` is the faithful spelling of that word splitting; the
    quoted tools take the string whole, so a path with a space still works for them and still breaks for the other three, exactly as it does today.
    """
    if tool in ("ruff", "uv", "pytest"):
        words = shlex.split(binary)
    elif tool in ("shfmt", "shellcheck", "actionlint", "go", "node"):
        words = [binary]
    else:
        raise ToolError("toolchain: no version probe for %r" % tool)
    return words + (["version"] if tool == "go" else ["--version"])


def _probe_extract(tool: str, out: str) -> str:
    """The awk/head half of `toolchain_probe_version` (:73-87).

    Each arm reproduces one shell pipeline, and they are genuinely different because every tool prints its version differently:

        shfmt       `head -1`                v3.13.1
        shellcheck  `awk -F': *' '/^version:/ {print $2}'` over a banner
        ruff        `awk '{print $2}'`       ruff 0.16.1
        actionlint  `head -1`                1.7.12
        go          `awk '{print $3}'`       go version go1.26.4 linux/arm64
        node        the whole thing          v22.23.2
        uv          `awk '{print $2}'`       uv 0.12.10
        pytest      `head -1 | awk '{print $2}'`   pytest 9.1.1

    `awk` prints ONE LINE PER MATCHING INPUT LINE, so these can legitimately
    return several lines; the numeric-run step below is per-line too, which is
    why neither stage collapses to a single value early.
    """
    lines = out.split("\n")
    if tool in ("shfmt", "actionlint"):
        return lines[0] if lines else ""
    if tool == "node":
        # `$(...)` strips every trailing newline; nothing else is touched.
        return out.rstrip("\n")
    if tool == "shellcheck":
        picked = []
        for line in lines:
            if line.startswith("version:"):
                # `-F': *'`: the separator is a colon followed by any run of spaces, so field 2 is what follows `version:` with its padding already eaten.
                fields = re.split(r": *", line)
                picked.append(fields[1] if len(fields) > 1 else "")
        return "\n".join(picked)
    if tool in ("ruff", "uv", "go"):
        # `awk '{print $N}'`: ruff and uv take field 2 (`ruff 0.16.1`), go takes
        # field 3 (`go version go1.26.4 linux/arm64`). One table rather than two arms, because the ONLY thing that differs is the index and a reader comparing this against the bash should see that immediately.
        index = 2 if tool == "go" else 1
        picked = []
        for line in lines:
            fields = line.split()
            picked.append(fields[index] if len(fields) > index else "")
        # `awk` emits a line for EVERY input line, including a blank one for a line with fewer fields than asked for. The trailing-newline strip that `$(...)` performs is what keeps that from becoming a stray record.
        return "\n".join(picked).rstrip("\n")
    if tool == "pytest":
        first = lines[0] if lines else ""
        fields = first.split()
        return fields[1] if len(fields) > 1 else ""
    raise ToolError("toolchain: no version probe for %r" % tool)


def _probe_numeric(text: str) -> str:
    """`${out#v}`, `${out#go}`, then `grep -oE '^[0-9]+(\\.[0-9]+)*'` (:89-91).

    PER LINE, because `grep -o` is. The prefix strips are NOT per line: they are parameter expansions over the whole string, so only the very first character run can lose a `v` or a `go`. That asymmetry is real and is why this is not just `normalize_version` in a loop.
    """
    raw = text
    for prefix in VERSION_PREFIXES:
        raw = raw.removeprefix(prefix)
    matched = [m.group(0) for m in (NUMERIC_RUN_RE.match(line) for line in raw.split("\n")) if m]
    return "\n".join(matched).rstrip("\n")


def probe_version(tool: str, binary: str | None = None, *, timeout: int = 60) -> str | None:
    """The version a binary reports, or None when it would not say. Raises ToolError.

    `toolchain_probe_version` (:71-94). `2>/dev/null` on every arm, so a tool that prints its version to stderr reads as absent, and a tool that fails outright reads as absent too. None rather than "" for the same reason the twin returns 1: "a normaliser that silently yields '' would make a
    comparison of ''=='' pass -- vacuity inside the very check meant to prevent
    it" (:54-57).

    THE ONE DELIBERATE DIVERGENCE: a 60s timeout the twin does not have. A `--version` that never returns hangs the bash forever, and a gate that hangs is worse than a gate that refuses, because CI reports nothing for the whole job timeout. The timeout lands in the same branch as a crash, so a hung tool reads as "would not say" rather than as a pass. Unreachable with any of the
    eight real tools; it is here for the ninth.
    """
    argv = _probe_argv(tool, tool if binary is None else binary)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        # `$("$bin" --version 2>/dev/null)` with no such binary yields "" and a non-zero status the assignment swallows, so the twin also lands on the empty-output branch rather than aborting.
        return None
    answer = _probe_numeric(_probe_extract(tool, proc.stdout))
    return answer or None


# --------------------------------------------------------------------------- The question every gate asks ---------------------------------------------------------------------------


def check(tool: str, *, pins: dict[str, str] | None = None, path: str | None = None) -> CheckResult:
    """Is the pinned version of `tool` on PATH? `toolchain_check` (:128-157).

    Returns the binary to use and rc 0 when it is, and an explanation with rc 1 or 2 when it is not. DELIBERATELY DOES NOT INSTALL: acquisition differs per tool and per lane, and a library that shells out to a package manager as a side effect of a version check is a library nobody trusts (:124-127).

    The messages are the twin's, character for character, because `.ci/legacy/run-legacy.sh:406` pipes them to the user through `sed 's/^/ /'` and a reworded refusal would change what an operator reads.

    rc 2 is "you asked something I have no answer for" (unknown tool, or an
    empty pin); rc 1 is "the answer is no".
    """
    try:
        pin_value = pin_for(tool, pins)
    except PinError as exc:
        if tool not in TOOL_KEYS:
            return CheckResult(tool, None, 2, ("toolchain: no pin defined for '%s'" % tool,))
        # An absent or empty KEY. The bash reaches this through `[[ -n "$pin" ]]` at :134 rather than through pin_for's own failure, because `toolchain_pin_for` returns "" with STATUS 0 for a known tool whose key is unset. Two bash branches, one Python exception, same two messages and same rc.
        del exc
        return CheckResult(
            tool,
            None,
            2,
            ("toolchain: pin for '%s' is empty -- did toolchain_load run?" % tool,),
        )

    binary = shutil.which(tool, path=path)
    if binary is None:
        return CheckResult(
            tool,
            None,
            1,
            ("toolchain: %s is not on PATH (pinned at %s)" % (tool, pin_value),),
        )

    actual = probe_version(tool, binary)
    if actual is None:
        return CheckResult(
            tool,
            None,
            1,
            (
                "toolchain: could not read a version from '%s --version' -- refusing to "
                "assume it matches %s" % (tool, pin_value),
            ),
        )

    if tool == "node":
        # NODE_VERSION is a MAJOR, not a full version: compare only that field.
        # `${actual%%.*}` is a TEXT prefix and not a parsed integer, so `22` and
        # `022` would differ here just as they do in the bash; `same_major`
        # would say they match, which is why this branch does not use it.
        major = actual.split(".", 1)[0]
        if major != pin_value:
            return CheckResult(
                tool,
                None,
                1,
                (
                    "toolchain: node major %s != pinned %s (found %s at %s)"
                    % (major, pin_value, actual, binary),
                ),
            )
    elif actual != pin_value:
        return CheckResult(
            tool,
            None,
            1,
            ("toolchain: %s %s != pinned %s (at %s)" % (tool, actual, pin_value, binary),),
        )

    return CheckResult(tool, binary, 0)


def report(
    verify: bool = False,
    *,
    pins: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
) -> tuple[list[str], int]:
    """(the lines to print, the rc). `toolchain_report` (:184-209).

    `verify=False` ALWAYS returns 0, matching the twin's `[[ "$strict" ==
    "--verify" ]] || return 0` at :207: the plain report is information and not
    a verdict. `verify=True` returns 1 if any of the six tools mismatched.

    THE FUNCTION'S rc IS CORRECT IN BOTH IMPLEMENTATIONS. What is broken is the
    twin's SCRIPT DISPATCH, which throws that rc away; see DEFECT 1 at the top
    of this section. The port keeps the function honest and makes its CLI honour it, so `python3 -m rediacc_ci.core.toolchain verify` exits 1 where `toolchain.sh --verify` exits 0.

    `env` IS THREADED THROUGH TO `lane()`, and the omission was a real CI-only
    divergence. `lane()` and `cache_dir()` have always taken an env; this one
    read `os.environ` unconditionally, so the differential handed the TWIN a controlled `diff.env_for()` (no `GITHUB_ACTIONS`, hence `lane: host`) while the port read the ambient environment. On a developer machine both say
    `host` and the test passes; the first time it ran inside real GitHub Actions
    -- 2026-09-15, the first run in this wave that let `quality-security` finish -- the twin said `host`, the port said `ci`, and four cases failed on a
    one-line diff. Reproducible anywhere with `GITHUB_ACTIONS=true pytest`.
    """
    table = load_pins() if pins is None else pins
    out = ["lane: %s" % lane(env), ""]
    out.append("  %-11s %-9s %-15s %s" % ("tool", "pinned", "actual", "status"))
    rc = 0
    for tool in REPORT_TOOLS:
        # `pin="$(toolchain_pin_for "$tool")"` at :197 keeps an EMPTY pin rather
        # than refusing, because this column is a report and not a verdict; the
        # status column is where the refusal shows up.
        try:
            pin_value = pin_for(tool, table)
        except PinError:
            pin_value = ""
        actual = probe_version(tool) or "absent"
        result = check(tool, pins=table)
        if result.ok:
            status = "ok"
        else:
            status = "MISMATCH"
            rc = 1
        out.append("  %-11s %-9s %-15s %s" % (tool, pin_value, actual, status))
    if not verify:
        return out, 0
    return out, rc


# --------------------------------------------------------------------------- Acquisition: getting the tool, not just asking about it ---------------------------------------------------------------------------
#
# A PATH binary AT THE PIN always wins, so a developer's own install is honoured and CI does not re-download on every invocation. Two acquisition models, chosen per tool by what the upstream actually offers:
#
# go install @vX (shfmt) -- Go verifies the module against its checksum database, which is a stronger guarantee than a hash recorded here. shfmt publishes no checksums file at all, so this is also the only verified option available for it. download + recorded sha256 (shellcheck) -- a prebuilt Haskell binary.


def shfmt_url(want: str, os_key: str, arch: str) -> str:
    """The shfmt release asset URL (:339). Named so a test can pin its shape."""
    return "https://github.com/mvdan/sh/releases/download/v%s/shfmt_v%s_%s_%s" % (
        want,
        want,
        os_key,
        arch,
    )


def shellcheck_url(want: str, os_key: str, arch: str) -> str:
    """The shellcheck release asset URL (:422). `.tar.xz` is the only form."""
    return (
        "https://github.com/koalaman/shellcheck/releases/download/v%s/shellcheck-v%s.%s.%s.tar.xz"
        % (want, want, os_key, arch)
    )


CURL_ARGS = ("-fsSL", "--max-time", "180", "--retry", "3", "--retry-delay", "5")


def _curl(url: str, target: pathlib.Path) -> bool:
    """`curl -fsSL --max-time 180 --retry 3 --retry-delay 5 -o <target> <url>`."""
    target.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["curl", *CURL_ARGS, "-o", str(target), url],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def download_shfmt(
    want: str,
    cache: pathlib.Path,
    binary: pathlib.Path,
    *,
    env: dict[str, str] | None = None,
    machine: str | None = None,
    system: str | None = None,
) -> tuple[str | None, list[str]]:
    """(the installed path or None, the messages). `_toolchain_download_shfmt` (:314-353).

    THE CHECKSUM VARIABLE IS KEYED BY OS AS WELL AS ARCH, because the URL is. The refusal names the CONSTANT to add rather than the arch, which is the difference between a message a reader can act on and one they have to decode.
    """
    messages: list[str] = []
    try:
        os_key = os_name(system)
    except ToolError as exc:
        return None, [str(exc)]
    uname_m = platform.machine() if machine is None else machine
    arch = SHFMT_ARCH.get(uname_m)
    if arch is None:
        return None, [
            "toolchain: no pinned shfmt checksum for %s; add one rather than downloading "
            "unverified" % uname_m
        ]
    sha_var = "SHFMT_SHA256_%s_%s" % (os_key.upper(), arch.upper())
    sha = checksums(env).get(sha_var, "")
    if not sha:
        return None, [
            "toolchain: no shfmt checksum for %s/%s -- define %s in .ci/config/constants.sh "
            "(and source it) rather than downloading unverified" % (os_key, arch, sha_var)
        ]
    cache.mkdir(parents=True, exist_ok=True)
    url = shfmt_url(want, os_key, arch)
    # A PRIVATE TEMP PER PROCESS, mirroring `mktemp "$cache/shfmt.XXXXXXXX"` in the twin. The shared `$bin.tmp` both sides used to write was a data-
    # corruption race under any concurrent acquisition; the twin carries the
    # measurement (8 racers, 7 failures, a false "checksum MISMATCH") and the reasoning. `.replace()` is the atomic rename the fix turns on.
    fd, tmp_name = tempfile.mkstemp(prefix="shfmt.", dir=str(cache))
    os.close(fd)
    tmp = pathlib.Path(tmp_name)
    if not _curl(url, tmp):
        tmp.unlink(missing_ok=True)
        return None, ["toolchain: could not download shfmt from %s" % url]
    actual = sha256_of(tmp)
    if actual != sha:
        # DEFECT 2 CANNOT HAPPEN HERE: `actual` is always a real digest, so this headline is only ever printed when there genuinely was a mismatch.
        messages.append("toolchain: shfmt checksum MISMATCH -- refusing to install")
        messages.append("  expected %s" % sha)
        messages.append("  actual   %s" % actual)
        tmp.unlink(missing_ok=True)
        return None, messages
    tmp.chmod(0o755)
    tmp.replace(binary)
    return str(binary), messages


def acquire_shfmt(want: str, *, env: dict[str, str] | None = None) -> tuple[str | None, list[str]]:
    """`_toolchain_acquire_shfmt` (:355-380). A cached binary short-circuits.

    NO GO? DOWNLOAD THE RELEASE BINARY. The CI Static lane is a bare checkout
    with no Go toolchain, so a Go-only acquisition simply cannot run there, and
    the unpinned `curl webi.sh/shfmt | sh` this replaced is what used to cover that lane.

    `GOTOOLCHAIN=local` on the install: without it a tool's own `go` directive
    can drag in a different toolchain and 404 on a runner with no network to fetch it.
    """
    cache = cache_dir(env) / ("shfmt-%s" % want)
    binary = cache / "shfmt"
    if os.access(str(binary), os.X_OK):
        return str(binary), []
    if shutil.which("go") is None:
        return download_shfmt(want, cache, binary, env=env)
    cache.mkdir(parents=True, exist_ok=True)
    child = dict(os.environ if env is None else env)
    child["GOTOOLCHAIN"] = "local"
    child["GOBIN"] = str(cache)
    proc = subprocess.run(
        ["go", "install", "mvdan.cc/sh/v3/cmd/shfmt@v%s" % want],
        capture_output=True,
        text=True,
        check=False,
        env=child,
    )
    if proc.returncode != 0:
        # FALLS BACK TO THE DOWNLOAD, matching the twin. `command -v go` asks
        # whether go is PRESENT; the pin check asks whether it is the RIGHT
        # version. CI's quality-security lane answered yes and no respectively, so this branch ran, failed, and made shfmt unacquirable while the static lane -- with no go at all -- downloaded it in 0.6s. The message is emitted BEFORE the fallback's own, because the twin echoes then calls, and the differential compares the stream in order.
        found, messages = download_shfmt(want, cache, binary, env=env)
        return found, ["toolchain: go install shfmt@v%s failed" % want, *messages]
    if not os.access(str(binary), os.X_OK):
        # The twin's `[[ -x "$bin" ]] || return 1` at :378 is SILENT, and that is reproduced: a message here would be a line the differential sees on one side only.
        return None, []
    return str(binary), []


def acquire_shellcheck(
    want: str,
    *,
    env: dict[str, str] | None = None,
    machine: str | None = None,
    system: str | None = None,
) -> tuple[str | None, list[str]]:
    """`_toolchain_acquire_shellcheck` (:382-440). Checksummed `.tar.xz` download.

    xz IS A PRECONDITION, and this repo depends on it nowhere else. shellcheck publishes its Linux builds only as `.tar.xz` and the CI Static lane runs on a deliberately slim image, so "tar: unrecognized option J" is a plausible failure whose text names neither xz nor shellcheck. The twin probes for the
    binary and says so instead; this port keeps that probe rather than reaching
    for Python's `lzma`, because a port that succeeds where the twin refuses is
    a port whose differential can never be clean.

    VERIFY BEFORE EXTRACTING: an unverified archive is arbitrary content, and extraction is the point at which that starts to matter.
    """
    cache = cache_dir(env) / ("shellcheck-%s" % want)
    binary = cache / "shellcheck"
    if os.access(str(binary), os.X_OK):
        return str(binary), []
    try:
        os_key = os_name(system)
    except ToolError as exc:
        return None, [str(exc)]
    uname_m = platform.machine() if machine is None else machine
    arch = SHELLCHECK_ARCH.get(uname_m)
    if arch is None:
        return None, [
            "toolchain: no pinned shellcheck checksum for %s; add one rather than "
            "downloading unverified" % uname_m
        ]
    sha_var = "SHELLCHECK_SHA256_%s_%s" % (os_key.upper(), arch.upper())
    sha = checksums(env).get(sha_var, "")
    if not sha:
        return None, [
            "toolchain: no checksum for shellcheck %s/%s -- define %s in "
            ".ci/config/constants.sh (and source it) rather than downloading unverified"
            % (os_key, arch, sha_var)
        ]
    if shutil.which("xz") is None:
        return None, [
            (
                "toolchain: xz is required to extract shellcheck (every release it "
                "publishes is .tar.xz only)"
            ),
            (
                "  install xz-utils, or run this gate in the devbox where shellcheck "
                "is already at the pin"
            ),
        ]
    cache.mkdir(parents=True, exist_ok=True)
    # PRIVATE STAGING DIR, mirroring `mktemp -d "$cache/sc.XXXXXXXX"` in the twin. Both the archive and the extraction used to target the shared `$cache`, so two concurrent acquisitions could leave a half-written `shellcheck` at the final path, executable, for a third process to run.
    stage = pathlib.Path(tempfile.mkdtemp(prefix="sc.", dir=str(cache)))
    tmp = stage / "sc.tar.xz"
    url = shellcheck_url(want, os_key, arch)
    if not _curl(url, tmp):
        shutil.rmtree(stage, ignore_errors=True)
        return None, ["toolchain: could not download shellcheck from %s" % url]
    actual = sha256_of(tmp)
    if actual != sha:
        messages = [
            "toolchain: shellcheck checksum MISMATCH -- refusing to extract",
            "  expected %s" % sha,
            "  actual   %s" % actual,
        ]
        shutil.rmtree(stage, ignore_errors=True)
        return None, messages
    member = "shellcheck-v%s/shellcheck" % want
    proc = subprocess.run(
        ["tar", "-xJf", str(tmp), "-C", str(stage), "--strip-components=1", member],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        # THE TWIN NO LONGER LEAKS THE ARCHIVE HERE, and neither does this. It used to: `tar ... || return 1` with the `rm -f "$tmp"` on the NEXT line left a multi-megabyte `sc.tar.xz` in the cache forever, and this port reproduced that rather than tidying, because the cache directory's contents are observable to a caller that lists it. Private staging changed the arithmetic -- one
        # file overwritten in place became an unbounded pile of randomly named directories -- so both sides now tear the staging dir down on every exit path.
        shutil.rmtree(stage, ignore_errors=True)
        return None, []
    staged = stage / "shellcheck"
    if not os.access(str(staged), os.X_OK):
        shutil.rmtree(stage, ignore_errors=True)
        return None, []
    staged.replace(binary)
    shutil.rmtree(stage, ignore_errors=True)
    if not os.access(str(binary), os.X_OK):
        return None, []
    return str(binary), []


def acquire(
    tool: str, *, pins: dict[str, str] | None = None, env: dict[str, str] | None = None
) -> tuple[str | None, list[str]]:
    """(a binary that IS the pin, the messages). `toolchain_acquire` (:444-466).

    A PATH BINARY AT THE PIN WINS FIRST, and its failure messages are SWALLOWED (`toolchain_check "$tool" 2>/dev/null` at :446) because "not installed yet" is the normal case here, not a finding.

    THE EMPTY-PIN GUARD IS DUPLICATED FROM `check`, and the twin says why at
    :451-457: its absence here was the asymmetry that let an empty pin reach a
    download URL and 404 against GitHub rather than naming the missing pin.

    THE DEFAULT ARM re-runs `check` and hands back its rc without its binary (`toolchain_check "$tool" >/dev/null` at :462). That looks like a dropped
    return value and is harmless: the arm is reachable only when the FIRST
    `check` already failed, so the rc is always non-zero and there is no path on which a caller receives success with an empty string. Verified live on 2026-09-10 for `go` and `ruff`, both of which returned their real path through the first branch instead. The port returns the messages from that second call, which is what the twin's un-redirected `>/dev/null` leaves on stderr for
    the user.
    """
    first = check(tool, pins=pins)
    if first.ok:
        return first.binary, []

    try:
        pin_value = pin_for(tool, pins)
    except PinError:
        if tool not in TOOL_KEYS:
            return None, []
        return None, ["toolchain: pin for '%s' is empty -- the pins file did not load" % tool]

    if tool == "shfmt":
        return acquire_shfmt(pin_value, env=env)
    if tool == "shellcheck":
        return acquire_shellcheck(pin_value, env=env)
    again = check(tool, pins=pins)
    return (again.binary if again.ok else None), list(again.messages)


# --------------------------------------------------------------------------- argv dispatch -- the surface a bash caller reaches ---------------------------------------------------------------------------


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

    if verb == "lane":
        print(lane())
        return 0

    if verb == "cache-dir":
        print(cache_dir())
        return 0

    if verb in ("report", "verify"):
        # `verify` EXITS NON-ZERO ON A MISMATCH, which `toolchain.sh --verify`
        # does not; see DEFECT 1 in the acquisition section. The lines are
        # identical, only the exit code differs, so a differential over the OUTPUT still compares clean while the verdict here is usable.
        try:
            lines, rc = report(verb == "verify")
        except PinError as exc:
            # `toolchain_report` opens with `toolchain_load || return 2`, so a missing or unreadable pins file is rc 2 and NOT a table full of blanks. Reproduced here rather than left to raise, because an unhandled traceback is a third outcome the twin does not have.
            print(str(exc), file=sys.stderr)
            return 2
        for line in lines:
            print(line)
        return rc

    if verb == "probe":
        if not rest:
            return _fail("toolchain: probe needs a tool name")
        try:
            answer = probe_version(rest[0], rest[1] if len(rest) > 1 else None)
        except ToolError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if answer is None:
            return 1
        print(answer)
        return 0

    if verb == "check":
        if not rest:
            return _fail("toolchain: check needs a tool name")
        result = check(rest[0])
        for message in result.messages:
            print(message, file=sys.stderr)
        if result.binary:
            print(result.binary)
        return result.rc

    if verb == "acquire":
        if not rest:
            return _fail("toolchain: acquire needs a tool name")
        try:
            binary, messages = acquire(rest[0])
        except PinError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        for message in messages:
            print(message, file=sys.stderr)
        if binary is None:
            # 2 is "you asked something I have no answer for" and covers BOTH of the twin's rc-2 exits at :450 (no such tool) and :454 (the pin is
            # empty); 1 is "I tried and could not get it". `acquire` signals the
            # empty-pin case with its one message, which is why the test for it is on the message and not on the tool name alone.
            empty_pin = any("is empty" in message for message in messages)
            return 2 if (rest[0] not in TOOL_KEYS or empty_pin) else 1
        print(binary)
        return 0

    return _fail("unknown verb: %s" % verb)


__all__ = [
    "ACQUIRE_TOOLS",
    "CACHE_DIR_NAME",
    "CACHE_ENV_ORDER",
    "CHECKSUM_PROBE_KEYS",
    "CONSTANTS_ASSIGN_RE",
    "CURL_ARGS",
    "NODE_FLOOR_KEY",
    "NODE_MAJOR_KEY",
    "NUMERIC_RUN_RE",
    "PAIR_RE",
    "PINS_RELPATH",
    "REPORT_TOOLS",
    "SHA_KEY_RE",
    "SHELLCHECK_ARCH",
    "SHFMT_ARCH",
    "TOOL_KEYS",
    "VERSION_PREFIXES",
    "CheckResult",
    "PinError",
    "ToolError",
    "VersionError",
    "acquire",
    "acquire_shellcheck",
    "acquire_shfmt",
    "at_least",
    "cache_dir",
    "check",
    "checksums",
    "compare",
    "constants_file",
    "download_shfmt",
    "lane",
    "load_pins",
    "node_floor",
    "node_major",
    "normalize_version",
    "os_name",
    "parse_version",
    "pin",
    "pin_for",
    "pins_file",
    "probe_version",
    "report",
    "same_major",
    "sha256_of",
    "shellcheck_url",
    "shfmt_url",
]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
