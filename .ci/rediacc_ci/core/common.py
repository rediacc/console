"""The refuse-early half of `.ci/scripts/lib/common.sh`, the tree's base library.

`.ci/scripts/lib/common.sh` is 772 lines and **208 files source it** (re-derived 2026-09-10 with `grep -rlP '^\\s*(source|\\.)\\s+.*lib/common\\.sh'`, excluding `node_modules` and `.git`, minus the one `.md` mention: 206 `.sh` plus two `.py` test files that emit a source line). The plan's "251" and the later "209" both counted files rather than real sourcers; the number to quote is
208.

It is NOT one library. It is seven, stacked in one file, and five of them were already ported by earlier waves under names that describe what they do:

    common.sh:17-55    colours + log_info/warn/error/step/debug -> `rediacc_ci.log`
    common.sh:205-210  get_repo_root                            -> `rediacc_ci.paths`
    common.sh:218-294  retry_with_backoff / wait_for /
                       run_with_timeout                         -> `rediacc_ci.proc`
    common.sh:434-473  _gh_probe / gh_retry / gh_json           -> `core.ghx`

Re-porting any of those would be a second implementation of a thing that has one, so this module deliberately does not. What is left, and what is here, is the REFUSE-EARLY half: the eleven functions a script calls in its first twenty lines to decide whether it may proceed at all, plus the three `CI_*` variables the file exports at source time.

    common.sh:63-72    detect_os           4 referring files
    common.sh:88-94    sed_in_place        8
    common.sh:98-106   detect_arch         7
    common.sh:110-112  is_ci               3
    common.sh:115-123  get_temp_dir        3
    common.sh:131-137  require_var        24
    common.sh:141-147  require_cmd        83
    common.sh:151-157  require_file       16
    common.sh:161-167  require_dir         7
    common.sh:186-197  require_input       3
    common.sh:301-303  to_upper            1
    common.sh:324-353  parse_args         53
    common.sh:488-502  require_submodule   7
    common.sh:509-514  CI_OS/CI_ARCH/CI_TEMP

(Counts are files naming the symbol under `--include='*.sh'`, excluding
`common.sh` itself, measured 2026-09-10.)

NOT HERE, AND SAID OUT LOUD RATHER THAN LEFT AS AN ABSENCE:

DETECT_OS AND DETECT_ARCH ARE HERE ON PURPOSE, EVEN THOUGH `core.platform` EXISTS. `core.platform` deliberately refused them, and says so at `platform.py:54-59`: "`.ci/scripts/lib/common.sh:64` is a THIRD spelling (`macos`, `windows`) and it is deliberately NOT a row here, because it also carries a fail-open default arm ... Adopting it would import that behaviour. Reported to the
driver rather than reproduced." That refusal is right for a module whose job is building download URLs, and it leaves a hole: `CI_OS` and `CI_ARCH` are EXPORTED by common.sh into every one of the 208 sourcers' child processes carrying exactly that third spelling, and `sed_in_place` branches on it. So the spelling is reproduced here, in the file whose twin owns it, with the
fail-open arm intact and named -- `platform.os_name()` RAISES where this returns the string `unknown`, and a caller comparing against `unknown` is comparing against something that reads like an answer.

  * `r2_count_objects` (common.sh:381-413, 6 referring files). It shells out to
    `aws s3api list-objects-v2`, and there is no `aws` binary on this machine
    (`which aws` finds nothing, 2026-09-10). A port nobody can drive against the
    twin is a second implementation rather than a replacement, so it is a
    deliberate gap and whoever closes it owns finding an `aws` to compare on.
  * The review-budget half (common.sh:516-772, thirteen functions). It is its
    own concern, it is bigger than everything above put together, and it is in
    `core.review_budget` beside this file.

--------------------------------------------------------------------------
THE ERROR MODEL, AND WHY IT IS NOT `sys.exit`
--------------------------------------------------------------------------
Every `require_*` in the twin ends `log_error ...; exit 1`, and because the twin is SOURCED that `exit` kills the caller's whole script. A Python library cannot do that: it is imported into a process that may have other work, and a module that calls `sys.exit` from a helper is untestable without catching SystemExit.

So each `require_*` here raises `RefusalError`, which carries the exact stderr lines the twin would have printed and the exit code it would have used, and `main()` prints them through `rediacc_ci.log.error` and returns that code. The bytes on stderr and the process exit status are therefore identical through the CLI -- which is what the differential compares -- while an importing
caller gets an exception it can catch. `test_core_common.py` drives both halves.

--------------------------------------------------------------------------
FIVE REAL QUIRKS, EACH DRIVEN ON bash 5.3.9 ON 2026-09-10, NONE FIXED IN THE TWIN
--------------------------------------------------------------------------
`.ci/scripts/lib/` is invariant 5 and outside this writer's ownership, so every one of these is reproduced or pinned rather than repaired.

QUIRK 1 -- `require_input` PASSES VACUOUSLY ON AN EMPTY PATH LIST, and it is the one helper in the file whose entire stated purpose is anti-vacuity. Its own header (common.sh:169-185) says "Refuse unless every required input exists, in the GATE'S OWN WORDS", yet:

    $ bash -c 'source common.sh; require_input -f "missing {}" "why"; echo "rc=$?"'
    reached rc=0

`for p in "$@"` over zero arguments runs zero times and the function returns 0. Two of the three call sites pass named scalars and cannot be empty. The third, `.ci/scripts/quality/check-no-app-admin-perm.sh:56-58`, passes
`"${SCAN_DIRS[@]}"` -- an ARRAY -- and that array is two hard-coded literals
today, so the defect is LATENT rather than live. It is exactly the shape that stops being latent the day someone builds that array from a glob or a `find`. `REQUIRE_INPUT_VACUOUS_IS_A_PASS` below records the twin's answer; this module's `require_input` refuses on an empty list, and both directions are pinned.

QUIRK 2 -- `require_input` MISREPORTS A BAD TEST FLAG AS A MISSING FILE. `test -q /nope` writes "unary operator expected" and exits 2, `! test ...` reads that as true, and the caller is told its file is missing:

    $ bash -c 'source common.sh; require_input -q "missing {}" "why" /nope'
    common.sh: line 191: test: -q: unary operator expected
    ✗ missing /nope
    ✗ why

It fails CLOSED, which is the right direction, with a diagnosis that names the wrong thing. This module raises a distinct `RefusalError` naming the flag.

QUIRK 3 -- `parse_args` KILLS THE SCRIPT ON A FLAG WHOSE NAME IS NOT A VALID SHELL IDENTIFIER, with an error that names common.sh rather than the caller:

    $ bash -c 'source common.sh; parse_args --foo.bar=x; echo reached'
    common.sh: line 333: printf: `ARG_FOO.BAR': not a valid identifier
    ; exit 2

`printf -v` returns 2, `set -e` is on from common.sh:11, and `reached` never prints. 53 files call `parse_args`. Reproduced: `parse_args()` here raises
`RefusalError(code=2)` carrying the twin's exact message.

QUIRK 4 -- `parse_args` SWALLOWS THE NEXT TOKEN WHEN IT STARTS WITH ONE DASH.
The lookahead is `[[ ! "$2" =~ ^-- ]]`, which only excludes long options:

    $ bash -c 'source common.sh; parse_args --verbose -x --other; ...'
    ARG_VERBOSE=[-x] ARG_OTHER=[true]

`--verbose` was meant to be a boolean and ate `-x`. Reproduced exactly; a port that treated any leading `-` as the next flag would silently disagree with 53 callers.

QUIRK 5 -- `get_repo_root` LEAKS A `cd` INTO THE CALLER'S SHELL. Its last line is a bare `cd "$script_dir/../../.." && pwd`, not a subshell:

    $ bash -c 'source common.sh; cd /; echo $PWD; get_repo_root >/dev/null; echo $PWD'
    /
    /home/developer/console

LATENT, NOT LIVE, AND THAT WAS MEASURED RATHER THAN ASSUMED. 99 `.sh` files name `get_repo_root`; grepping for the command-substitution spelling finds 97 occurrences of it, and a command substitution runs in a subshell, so the only three occurrences that are NOT are string literals inside two gates and one awk pattern (`test-breakpoint-portability.sh:174,176`,
`check-pool-writer-safety.sh:188`, in a bash twin W7 P5 has since retired). So there is no live caller that could be moved. `repo_root()` below delegates to `rediacc_ci.paths.repo_root()` and CANNOT chdir a process, which is a divergence stated rather than discovered.

--------------------------------------------------------------------------
THREE MORE DIVERGENCES THAT ARE DECISIONS RATHER THAN BUGS
--------------------------------------------------------------------------
  * `is_ci` tests `[[ "${CI:-false}" == "true" ]]`, so `CI=1` -- which several
    tools set -- reads as NOT CI (driven: prints NO). Reproduced verbatim,
    because 3 callers already live with it and a port that accepted `1` would
    take a different branch than the twin on the same environment.
  * `CI_OS`/`CI_ARCH`/`CI_TEMP` are computed ONCE at SOURCE time
    (common.sh:509-511), so `RUNNER_TEMP=/x; source common.sh; RUNNER_TEMP=/y`
    leaves `CI_TEMP=/x` while `get_temp_dir` answers `/y`. Driven. `ci_env()`
    here is a function, so the caller chooses when to snapshot; the snapshot
    semantics are what `main()`'s `ci-env` verb reproduces.
  * `to_upper -n` prints nothing, because it is `echo "$1"` and `echo` eats its
    own flags (driven: `[]`). Unreachable from `parse_args` -- a key reaching
    `to_upper` has had `--` stripped and `-` mapped to `_` -- but `to_upper` is
    a public function of a library 208 files source. Reproduced, and pinned.

--------------------------------------------------------------------------
WHAT IS DIFFERENTIALLY PROVED
--------------------------------------------------------------------------
`.ci/shadow/w7p5b-common.observations.jsonl` drives BOTH sides through a real caller shape: a script that sources `common.sh` (or imports this module) and then runs the same refuse-early sequence a quality gate runs in its opening lines -- `require_cmd`, `require_file`, `require_dir`, `require_var`, `require_input`, `parse_args`, `get_temp_dir`, `is_ci`. That is the sequence 208
files actually execute, which is why the ledger is not a synthetic per-function harness.
"""

from __future__ import annotations

import os
import pathlib
import platform as _stdlib_platform
import shutil
import subprocess
import sys

from rediacc_ci import log, paths

# QUIRK 1. `for p in "$@"` over an empty list is zero iterations, so the twin's require_input returns 0 on nothing. Recorded as a constant rather than a sentence so a test can assert against the twin's behaviour by name.
REQUIRE_INPUT_VACUOUS_IS_A_PASS = True

# `if [[ "${CI:-false}" == "true" ]]` (common.sh:111). The literal, not a set.
CI_TRUE = "true"

# The env names `is_ci` consults, in the twin's order (common.sh:111).
CI_ENV_NAMES = ("CI", "GITHUB_ACTIONS", "GITLAB_CI")

# `get_temp_dir`'s ladder (common.sh:116-122). Order is the contract.
TEMP_DIR_ENV_NAMES = ("RUNNER_TEMP", "TMPDIR")
TEMP_DIR_FALLBACK = "/tmp"

# The prefix `parse_args` puts on every key (common.sh:332).
ARG_PREFIX = "ARG_"

# `case "$(uname -s)"` (common.sh:64-71), IN ORDER. bash `case` takes the first matching arm, so the order is the contract and not a tidy alphabetisation. Note what is NOT here: `Windows*`. `core.platform`'s SYSTEM_PREFIXES carries it and this does not, so a `uname -s` of `Windows_NT` is `windows` there and `unknown` here. That is the twin's table, reproduced.
OS_PREFIXES = (
    ("Linux", "linux"),
    ("Darwin", "macos"),
    ("CYGWIN", "windows"),
    ("MINGW", "windows"),
    ("MSYS", "windows"),
)

# `case "$arch"` (common.sh:101-105). Exact matches, not prefixes: the twin uses bare words with no `*`, so `x86_64-pc-linux` is `unknown`.
ARCH_ALIASES = {
    "x86_64": "x64",
    "amd64": "x64",
    "aarch64": "arm64",
    "arm64": "arm64",
}

# The `*)` arm of both cases. A STRING, not a refusal: see the module docstring.
UNKNOWN = "unknown"


class RefusalError(Exception):
    """One `log_error ...; exit N` from the twin, as a catchable object.

    `lines` are the stderr lines in order, without the `✗ ` marker -- the marker belongs to `log_error`, and `rediacc_ci.log.error` adds it. `code` is the twin's exit status: 1 for every `require_*`, 2 for the `printf -v` failure in `parse_args` (QUIRK 3), which is `printf`'s own status rather than a number the script chose.
    """

    def __init__(self, *lines: str, code: int = 1) -> None:
        super().__init__(lines[0] if lines else "")
        self.lines = list(lines)
        self.code = code

    def report(self) -> None:
        for line in self.lines:
            log.error(line)


# --------------------------------------------------------------------------- ENVIRONMENT DETECTION (common.sh:88-123) ---------------------------------------------------------------------------


def _env(env: dict[str, str] | None) -> dict[str, str]:
    return dict(os.environ) if env is None else env


def detect_os(system: str | None = None) -> str:
    """`detect_os` (common.sh:63-72). linux | macos | windows | unknown.

    FAILS OPEN, and that is the whole reason `core.platform` would not take it. An unrecognised `uname -s` yields the STRING `unknown`, which every caller then compares against as though it were an answer -- `sed_in_place` twelve
    lines down asks `== "macos"` and takes the GNU arm for `unknown`, which is
    correct by luck rather than by decision. Reproduced verbatim; `core.platform` is where a caller goes when it wants a refusal instead.
    """
    raw = _stdlib_platform.system() if system is None else system
    for prefix, name in OS_PREFIXES:
        if raw.startswith(prefix):
            return name
    return UNKNOWN


def detect_arch(machine: str | None = None) -> str:
    """`detect_arch` (common.sh:98-106). x64 | arm64 | unknown.

    Same fail-open arm as `detect_os`, and the same divergence from `core.platform.machine_key()`, which raises `UnsupportedPlatformError`. The spellings differ too: this answers `x64`, `machine_key` answers `x86_64`, and `arch_for("node")` answers `x64` -- three functions, two of which agree.

    The twin matches EXACT words, not prefixes, so anything that is not one of the four literals is `unknown`.
    """
    raw = _stdlib_platform.machine() if machine is None else machine
    return ARCH_ALIASES.get(raw, UNKNOWN)


def sed_in_place_argv(args: list[str], os_name: str | None = None) -> list[str]:
    """`sed_in_place`'s argv (common.sh:88-94), without running it.

    The whole function is one branch: macOS `sed` REQUIRES a backup suffix after `-i` and GNU `sed` refuses one, so the twin inserts an empty `''` argument on macOS only. Exposed as an argv builder because that branch is the entire content, and asserting on a list is how a test on Linux can prove the macOS arm without a Mac.

    `os_name` is `detect_os`'s answer. The twin calls `detect_os` -- and therefore forks `uname` -- on EVERY invocation; this does not, which is a cost difference and not a behaviour one.

    The comparison is `== "macos"`, so every other answer INCLUDING `unknown`
    takes the GNU arm. Reproduced, and named, because it is right by luck.
    """
    resolved = detect_os() if os_name is None else os_name
    if resolved == "macos":
        return ["sed", "-i", "", *args]
    return ["sed", "-i", *args]


def sed_in_place(args: list[str], os_name: str | None = None) -> int:
    """Run `sed_in_place_argv`. Returns sed's exit status, like the twin."""
    return subprocess.run(sed_in_place_argv(args, os_name), check=False).returncode


def is_ci(env: dict[str, str] | None = None) -> bool:
    """`is_ci` (common.sh:110-112), including its `CI=1` blind spot.

    `[[ "${CI:-false}" == "true" ]] || [[ -n "${GITHUB_ACTIONS:-}" ]] ||
     [[ -n "${GITLAB_CI:-}" ]]`

    CI is compared to the literal `true`; the other two only have to be
    non-empty. So `CI=1` alone is NOT ci here (driven 2026-09-10), while
    `GITHUB_ACTIONS=0` IS. Both asymmetries are the twin's and both are
    reproduced.
    """
    e = _env(env)
    if e.get("CI", "false") == CI_TRUE:
        return True
    return bool(e.get("GITHUB_ACTIONS")) or bool(e.get("GITLAB_CI"))


def get_temp_dir(env: dict[str, str] | None = None) -> str:
    """`get_temp_dir` (common.sh:115-123).

    `[[ -n "${RUNNER_TEMP:-}" ]]` then `[[ -n "${TMPDIR:-}" ]]` then `/tmp`. The
    test is NON-EMPTY, not "set", so `RUNNER_TEMP=` falls through to TMPDIR
    (driven). Nothing checks that the answer exists or is writable, which is the twin's contract and not an oversight to correct in a port.
    """
    e = _env(env)
    for name in TEMP_DIR_ENV_NAMES:
        value = e.get(name, "")
        if value:
            return value
    return TEMP_DIR_FALLBACK


# --------------------------------------------------------------------------- VALIDATION HELPERS (common.sh:131-197) ---------------------------------------------------------------------------


def require_var(name: str, env: dict[str, str] | None = None) -> str:
    """`require_var` (common.sh:131-137). Returns the value, raises on absent.

    `[[ -z "${!var_name:-}" ]]` is an EMPTINESS test reached through indirect
    expansion, so a variable that is exported as the empty string is reported as
    "not set" (driven: `export FOO=""; require_var FOO` refuses). Reproduced.

    The twin has a third outcome this cannot have: `require_var 'a-b'` dies with `common.sh: line 133: a-b: invalid variable name`, exit 1, before any `log_error` runs -- bash refuses the indirection itself. A Python dict lookup has no such rule, so the port refuses through the normal path with the normal message. Named here because the exit code is the same and the stderr is not.
    """
    value = _env(env).get(name, "")
    if not value:
        raise RefusalError("Required environment variable '%s' is not set" % name)
    return value


def require_cmd(cmd: str, env: dict[str, str] | None = None) -> str:
    """`require_cmd` (common.sh:141-147). Returns the resolved path.

    `command -v "$cmd" &>/dev/null`. `shutil.which` is the closest available equivalent and differs on one point worth naming: `command -v` also answers
    for shell BUILTINS and functions, which `which` cannot see. Every one of the
    83 referring files passes an external binary (`gh`, `jq`, `docker`, `go`, `node`), so the difference is not reachable from any live call site -- but it is a difference, and a caller that ever passes `cd` would get opposite answers from the two.
    """
    e = _env(env)
    found = shutil.which(cmd, path=e.get("PATH"))
    if found is None:
        raise RefusalError("Required command '%s' is not available" % cmd)
    return found


def require_file(path: str | os.PathLike[str]) -> pathlib.Path:
    """`require_file` (common.sh:151-157). `[[ ! -f "$file" ]]`.

    `-f` follows symlinks and is TRUE only for a regular file, so a directory and a dangling link both refuse. `pathlib.Path.is_file()` has the same two properties.
    """
    p = pathlib.Path(path)
    if not p.is_file():
        raise RefusalError("Required file '%s' does not exist" % path)
    return p


def require_dir(path: str | os.PathLike[str]) -> pathlib.Path:
    """`require_dir` (common.sh:161-167). `[[ ! -d "$dir" ]]`."""
    p = pathlib.Path(path)
    if not p.is_dir():
        raise RefusalError("Required directory '%s' does not exist" % path)
    return p


def require_input(test_flag: str, lead: str, why: str, paths_: list[str | os.PathLike[str]]) -> int:
    """`require_input` (common.sh:186-197). Returns how many paths were checked.

    THE RETURN VALUE IS THE DIVERGENCE, and it is the point. The twin returns 0 on an empty list (QUIRK 1) -- the anti-vacuity helper passing vacuously. This returns the count so a caller can see that it was non-trivial, and RAISES on an empty list rather than reporting a green that proves nothing.

    Everything else is the twin, exactly:

      * `{}` in `lead` is replaced by the offending path with `${lead//\\{\\}/$p}`,
        a string substitution and not a printf format, so a path containing `%`
        is harmless (driven against `/no%sdir`).
      * The lead line stays the CALLER's words. common.sh:179-183 records why:
        `.ci/scripts/test/test-ci-job-aggregation.sh:333` asserts the literal
        "input not found" against `check-ci-job-aggregation.sh`, so a helper that
        imposed one house wording would turn a real gate test red.
      * It stops at the FIRST missing path, so a caller with three broken inputs
        hears about one.
      * `test_flag` is `-f` or `-d`. Anything else is QUIRK 2 in the twin; here
        it raises immediately, naming the flag, before any path is examined.
    """
    if test_flag not in ("-f", "-d"):
        raise RefusalError(
            "require_input: unknown test flag '%s' (expected -f or -d)" % test_flag,
            "The twin reports this as a MISSING PATH instead: `test %s <p>` exits 2, "
            "`! test` reads that as true, and the caller is told the wrong thing." % test_flag,
            code=1,
        )
    if not paths_:
        raise RefusalError(
            "require_input: nothing to check, so a pass here would mean nothing.",
            'The twin returns 0 on an empty path list (common.sh:190, `for p in "$@"` '
            "over zero arguments). Name the inputs, or do not call this.",
            code=1,
        )
    want_file = test_flag == "-f"
    checked = 0
    for raw in paths_:
        p = pathlib.Path(raw)
        ok = p.is_file() if want_file else p.is_dir()
        if not ok:
            raise RefusalError(lead.replace("{}", str(raw)), why)
        checked += 1
    return checked


# --------------------------------------------------------------------------- PATH HELPERS (common.sh:205-210) ---------------------------------------------------------------------------


def repo_root() -> pathlib.Path:
    """`get_repo_root` (common.sh:205-210), delegated to `rediacc_ci.paths`.

    NOT a re-port. `paths.repo_root()` is already the module the whole package
    resolves the root through, and re-deriving `${BASH_SOURCE[0]}/../../..` here
    would be a second answer to a question that has one. Two differences, both deliberate:

      * QUIRK 5: the twin's final `cd` is not in a subshell and therefore moves
        the caller's shell. This cannot, and a port that could would be a defect.
      * `paths.repo_root()` honours `$REDIACC_CI_ROOT` and the twin honours
        nothing. On a tree with that variable unset -- which is every real run --
        the two land on the same directory, which is what the ledger records.
    """
    return paths.repo_root()


# --------------------------------------------------------------------------- ARGUMENT PARSING (common.sh:301-353) ---------------------------------------------------------------------------


def to_upper(text: str) -> str:
    """`to_upper` (common.sh:301-303). `echo "$1" | tr '[:lower:]' '[:upper:]'`.

    `tr '[:lower:]' '[:upper:]'` is BYTE-WISE and locale-dependent in a way `str.upper()` is not: `str.upper()` maps `ß` to `SS` and `ı` to `I`, and `tr` maps neither. Every key that reaches this from `parse_args` is ASCII by the time it arrives, so `str.upper()` is used, and the divergence is named rather than hidden.

    The twin also has QUIRK: `to_upper -n` prints nothing, because `echo` eats its own flag (driven). Not reproduced -- reproducing it would mean writing an `echo` emulator into a case-folding helper -- and pinned in the tests so the absence is a recorded decision.
    """
    return text.upper()


def _arg_key(flag: str) -> str:
    """`--some-flag` -> `ARG_SOME_FLAG` (common.sh:328-332 and :337-339)."""
    key = flag.removeprefix("--")
    return ARG_PREFIX + to_upper(key.replace("-", "_"))


def _valid_identifier(name: str) -> bool:
    """What `printf -v NAME` accepts: `[A-Za-z_][A-Za-z0-9_]*`.

    Deliberately NOT `str.isidentifier()`, which accepts Unicode letters that bash rejects. This is bash's rule, so it is spelled as bash's rule.
    """
    if not name:
        return False
    head, tail = name[0], name[1:]
    if not (head.isascii() and (head.isalpha() or head == "_")):
        return False
    return all(c.isascii() and (c.isalnum() or c == "_") for c in tail)


def parse_args(argv: list[str]) -> dict[str, str]:
    """`parse_args` (common.sh:324-353), as a dict instead of shell globals.

    THE SECURITY PROPERTY IS THE REASON THIS FUNCTION IS WORTH PORTING AT ALL.
    common.sh:309-314 records it: the assignment used to be
    `eval "$key=\\"$value\\""`, and `eval` re-parses its argument as a command
    line, so a value carrying backticks, `$(...)` or `;` was EXECUTED. Driven again here on 2026-09-10 against the current twin, which uses `printf -v`:

        parse_args '--foo=a"; PROOF=INJECTED; :"'
        ARG_FOO=[a"; PROOF=INJECTED; :"]   PROOF=[none]

    The bytes are stored, nothing runs. A dict cannot execute anything, so the port has the property structurally, and `test_core_common.py` asserts the same string round-trips.

    THE THREE PARSING RULES, all reproduced:

      1. `--key=value` splits on the FIRST `=` (`${1%%=*}` / `${1#*=}`), so
         `--url=http://x?a=b` keeps everything after the first one.
      2. `--key value` consumes the next token as the value UNLESS that token
         starts with `--`. QUIRK 4: a token starting with ONE dash is consumed.
      3. A bare `--` becomes the key `ARG_` and the value `true`, because
         `${1#--}` leaves the empty string and `ARG_` is a valid identifier
         (driven).
      4. Anything not starting with `--` is skipped silently. Positional
         arguments are invisible to this parser.

    QUIRK 3 is reproduced as a `RefusalError(code=2)`: a key that is not a valid shell
    identifier is `printf -v`'s error, exit 2, and under the twin's `set -e` it takes the caller's whole script down.
    """
    out: dict[str, str] = {}
    i = 0
    n = len(argv)
    while i < n:
        token = argv[i]
        if token.startswith("--") and "=" in token:
            flag, _, value = token.partition("=")
            key = _arg_key(flag)
            _store(out, key, value)
            i += 1
        elif token.startswith("--"):
            key = _arg_key(token)
            if i + 1 < n and not argv[i + 1].startswith("--"):
                _store(out, key, argv[i + 1])
                i += 2
            else:
                _store(out, key, "true")
                i += 1
        else:
            i += 1
    return out


def _store(out: dict[str, str], key: str, value: str) -> None:
    if not _valid_identifier(key):
        # `printf -v` writes exactly this and returns 2 (common.sh:333/:341/:344).
        raise RefusalError("printf: `%s': not a valid identifier" % key, code=2)
    out[key] = value


# --------------------------------------------------------------------------- SUBMODULE GUARDS (common.sh:488-502) ---------------------------------------------------------------------------

# common.sh:500, verbatim. Quoted whole because it is what a caller greps for.
SUBMODULE_SKIP_SUFFIX = "not available, skipping (this is a hard failure in CI)"


def require_submodule(
    marker: str | os.PathLike[str], label: str, env: dict[str, str] | None = None
) -> bool:
    """`require_submodule` (common.sh:488-502). True present, False absent-locally.

    THREE outcomes, not two, and the third is why the function exists:

      present            -> True
      absent, CI         -> RefusalError(code=1), because `check:ci-renet` rides on
                            this and it carries govulncheck, deadcode and
                            golangci-lint. All three would report success while
                            checking nothing.
      absent, local      -> a warning and False, so a fresh clone without
                            `--recursive` is still workable. Callers spell it
                            `require_submodule ... || exit 0`.

    `[[ -e "$marker" ]]` is EXISTENCE, not file-ness, so an uninitialised submodule's empty directory counts as PRESENT -- git leaves the mount point behind. Reproduced with `os.path.exists`, which is the same test.

    The CI branch is `[[ "${CI:-false}" == "true" ]]` -- the literal again, NOT
    `is_ci()`. So `GITHUB_ACTIONS=true` with `CI` unset takes the LOCAL branch
    here while `is_ci()` twelve lines up says CI. That inconsistency is the twin's, it is inside one file, and it is reproduced rather than harmonised.

    `.ci/rediacc_ci/quality/subscription_schema.py:129` already re-implements this privately. That is a duplicate, named here rather than repointed: the gate is not this writer's file, and a cutover is a driver decision.
    """
    if os.path.exists(marker):
        return True
    if _env(env).get("CI", "false") == CI_TRUE:
        raise RefusalError(
            "%s is required in CI but missing: %s" % (label, marker),
            "  A gate skipped here would report success while checking nothing.",
            "  Fix the workflow checkout (submodules: true, or git submodule update --init).",
        )
    log.warn("%s %s" % (label, SUBMODULE_SKIP_SUFFIX))
    return False


# --------------------------------------------------------------------------- INITIALIZATION (common.sh:509-514) ---------------------------------------------------------------------------


def ci_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """`CI_OS` / `CI_ARCH` / `CI_TEMP` (common.sh:509-514), as a snapshot.

    The twin computes these once at SOURCE time and `export`s them, so a caller that changes `RUNNER_TEMP` afterwards keeps the old `CI_TEMP` while
    `get_temp_dir` answers the new one (driven: `CI_TEMP=/rt` and
    `get_temp_dir` -> `/other`, same shell). A function cannot have source-time semantics, so the caller decides when to take the snapshot -- and gets to take a second one, which the twin cannot.

    `CI_ARCH` has ZERO referring files (measured 2026-09-10) and `CI_OS` has 3. It is here because the twin exports it and a subprocess can read it, which is a fan-in this grep cannot see.
    """
    return {
        "CI_OS": detect_os(),
        "CI_ARCH": detect_arch(),
        "CI_TEMP": get_temp_dir(env),
    }


# --------------------------------------------------------------------------- CLI -- the surface the shadow differential drives ---------------------------------------------------------------------------

USAGE = """common -- the refuse-early half of .ci/scripts/lib/common.sh.

  require-cmd <name>              refuse unless the command resolves
  require-file <path>             refuse unless it is a regular file
  require-dir <path>              refuse unless it is a directory
  require-var <NAME>              refuse unless the variable is non-empty
  require-input <-f|-d> <lead-with-{}> <why> <path>...
  require-submodule <marker> <label>
  parse-args <argv...>            print KEY=VALUE per parsed flag, sorted
  to-upper <text>
  temp-dir
  is-ci                           exit 0 when CI, 1 when not
  repo-root
  ci-env                          print CI_OS/CI_ARCH/CI_TEMP, one per line
  detect-os
  detect-arch
  sed-argv <sed-args...>          print the argv sed_in_place would run
"""


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE, file=sys.stderr)
        return 2
    verb, rest = argv[0], argv[1:]
    try:
        return _dispatch(verb, rest)
    except RefusalError as refusal:
        refusal.report()
        return refusal.code


def _dispatch(verb: str, rest: list[str]) -> int:
    if verb == "require-cmd":
        require_cmd(rest[0])
        return 0
    if verb == "require-file":
        require_file(rest[0])
        return 0
    if verb == "require-dir":
        require_dir(rest[0])
        return 0
    if verb == "require-var":
        require_var(rest[0])
        return 0
    if verb == "require-input":
        require_input(rest[0], rest[1], rest[2], list(rest[3:]))
        return 0
    if verb == "require-submodule":
        return 0 if require_submodule(rest[0], rest[1]) else 1
    if verb == "parse-args":
        for key, value in sorted(parse_args(rest).items()):
            print("%s=%s" % (key, value))
        return 0
    if verb == "to-upper":
        print(to_upper(rest[0] if rest else ""))
        return 0
    if verb == "temp-dir":
        print(get_temp_dir())
        return 0
    if verb == "is-ci":
        return 0 if is_ci() else 1
    if verb == "repo-root":
        print(repo_root())
        return 0
    if verb == "ci-env":
        for key, value in ci_env().items():
            print("%s=%s" % (key, value))
        return 0
    if verb == "detect-os":
        print(detect_os())
        return 0
    if verb == "detect-arch":
        print(detect_arch())
        return 0
    if verb == "sed-argv":
        print(" ".join(sed_in_place_argv(list(rest))))
        return 0
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
