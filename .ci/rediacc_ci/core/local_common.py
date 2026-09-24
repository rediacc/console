"""`.ci/lib/local-common.sh`, ported function for function: all thirty.

PORTED FROM `.ci/lib/local-common.sh` (978 lines, 30 functions at 2026-09-24).
The twin still exists and is still sourced at `rdc.sh:18`, `.ci/legacy/run-legacy.sh:47`, `.ci/media/media-entry.sh:50`, `.ci/rediacc_ci/native.py:137` (inside a `bash -c`) and `.ci/scripts/test/gates/test-run-sh.sh:116`, and `.ci/rediacc_ci/setup/bridge.py` still runs four of its functions as bash. Nothing is cut over here: this is a pre-cutover port on the sequencing every other lib in W7P5-b used, and the deletion is W7P5-c's.

--------------------------------------------------------------------------
TWO HALVES, TWO DIFFERENTIALS
--------------------------------------------------------------------------
THE PURE HALF (2026-09-23), nine functions whose whole answer is computation over a local file or a local git read: `_sha256sum`, `_sed_i`, `compute_hash_for_package_dirs`, `_git_tree_fingerprint`, `compute_tree_hash`, `read_stamp_hash`, `write_stamp_hash`, `_version_gte` and `has_npm_script`. Proved by `core/local_common_shadow_driver.py`, ledger `w7p5b-local-common`.

THE MACHINE-MUTATING HALF (2026-09-24), the other twenty-one: the installers and builders (`ensure_cpu_features_gypi`, `ensure_deps`, `ensure_packages_built`, `ensure_cli_built`, `run_npm_script`, `ensure_go_installed`, `ensure_bashcov_sup`, `ensure_host_tools`, `ensure_docker_installed`, `_ensure_docker_group`, `ensure_renet_built`), the interactive and session-altering ones (`prompt_continue`, `open_browser`, `reexec_with_docker_group`), the checks (`check_node_version`, `check_go_installed`), renet's two fingerprints (`_renet_source_hash`, `_renet_artifact_fp`) and the three lane functions (`gate_lane_decide`, `gate_lane_should_route`, `gate_lane_run`), which reach devbox through `core.devbox`, the port of `.ci/lib/devbox.sh`.
Proved by `core/local_common_actions_shadow_driver.py`, ledger `w7p5b-local-common-actions`, by the STUB-FARM TRANSCRIPT technique (`core/stubfarm.py`): every external program the function would run is a stub that logs its argv, and the comparison covers rc, both streams, the ordered call list and the sandbox tree afterwards. See the section note above `ensure_cpu_features_gypi` for what that forces on the code.

`check_node_version` exists TWICE in Python: here, and an older copy in `core/account.py` with its own version compare. `account.py` was under another writer's live rewrite when this landed, so removing its copy is handed over; `test_check_node_version_agrees_with_the_account_copy` pins the two together meanwhile.

TWO LIVE TWIN DEFECTS WERE FIXED IN THE TWIN IN THE SAME CHANGE, both found by this port's scenarios: `ensure_bashcov_sup` read an undefined `$REPO_ROOT` and died on `set -u` every time (so `./run.sh setup` never built the supervisor), and `ensure_cli_built` died silently whenever `build-packages.stamp` was missing. Each function's docstring has the detail.

--------------------------------------------------------------------------
THE MEASUREMENT THIS PORT IS TRUE AGAINST, WHICH IS NOT THE ONE ANYBODY EXPECTS
--------------------------------------------------------------------------
THIS MACHINE DOES NOT RUN GNU COREUTILS. Measured 2026-09-23: `sha256sum`, `sort`, `tr`, `head`, `cat`, `uname` and `stat` are **uutils coreutils 0.8.0**, `find` is **bfs 4.1.1**, `grep` is **ugrep 7.8.4**; only `xargs` (GNU findutils 4.10.0), `awk` (GNU awk 5.3.2) and `sed` (GNU sed 4.9) are the GNU originals.
So the differential licence recorded for this port is equivalence against THAT tool set. Every behaviour reproduced below was measured against the tools actually on PATH rather than read out of a GNU manual, and the two places it could matter are named where they are reproduced: `sort -V`'s ordering in `version_gte` and `sha256sum`'s backslash escaping in `sha256_lines`.

--------------------------------------------------------------------------
SIX TWIN BEHAVIOURS REPRODUCED ON PURPOSE, NOT FIXED
--------------------------------------------------------------------------
  1. `compute_hash_for_package_dirs` OVER AN EMPTY FILE SET IS NOT THE HASH OF NOTHING. `xargs -0 $_SHA256SUM_CMD` with empty input still RUNS the command once, with no arguments, so `sha256sum` reads its own (empty) stdin and prints `e3b0c442...  -`. That line, not an empty stream, is what the outer hash sees. Measured: an empty directory fingerprints as
  `abcfa6a9d4df344d1781bc2560b5e4cdcae08b39ed303063535e7e1e926a304a`, which is `sha256("e3b0c442...  -\n")`. A port that hashed an empty stream would answer `e3b0c442...` and look perfectly reasonable.
  2. `_git_tree_fingerprint` DIES OR SURVIVES DEPENDING ON WHO CALLED IT. `existing="$(while ...; do [[ -f "$f" ]] && printf ...; done)"` is a BARE ASSIGNMENT taking the while loop's status, which is the status of the LAST iteration only. A `changed` list whose last entry is a DELETED file therefore leaves status 1. Under armed `errexit` the subshell dies there,
  printing nothing; called from `compute_tree_hash`, which spells it `if fp="$(_git_tree_fingerprint ...)"`, errexit is SUPPRESSED and the function runs to completion. Measured both ways 2026-09-23. `errexit=` on `git_tree_fingerprint()` carries that, and `compute_tree_hash()` passes `errexit=False` because its call site does.
  3. `has_npm_script` GREPS THE WHOLE `package.json`, not the `scripts` object, so a DEPENDENCY called `zod` makes `has_npm_script zod` true. Preserved, and pinned by a differential case.
  4. `has_npm_script` ON A MISSING `package.json` EXITS 2, not 1, because that is grep's status for an unreadable file, and the message reaches stderr un-prefixed.
  5. `write_stamp_hash` APPENDS A NEWLINE the reader never removes: `read_stamp_hash` is `cat`, so a value written and read back has grown one byte. `ensure_renet_built:848` is built around that, splitting the stamp with `sed -n 1p`.
  6. `_sha256sum` WITH NO TOOL CALLS `exit 1`, killing the sourcing shell rather than returning; and `compute_hash_for_package_dirs` does NOT go through it, it interpolates `$_SHA256SUM_CMD` directly, so with no tool it degrades to an EMPTY COMMAND in a pipeline.
  It then prints nothing on either stream and exits 125, because `xargs` with no command runs `echo`, nothing is reading the pipe, and a child killed by SIGPIPE is 125. Two different failure modes for one missing binary, both preserved.

--------------------------------------------------------------------------
THE ONE PLACE THE PORT REFUSES WHERE THE TWIN WOULD GUESS
--------------------------------------------------------------------------
`has_npm_script` tests with `grep -q "\\"$script_name\\":"`, which makes the script name a BASIC REGULAR EXPRESSION. All 388 script names in this repository's `package.json` are `[a-z0-9:-]+`, where a BRE and a literal agree, so a literal search is equivalent for the whole live corpus.
Rather than silently assume that forever, `has_npm_script()` raises on a name carrying a BRE metacharacter: a divergence that is refused is a divergence somebody sees. Same shape as `account.py`'s `env_add_if_missing`.

--------------------------------------------------------------------------
WHAT IS SHELLED OUT AND WHAT IS REIMPLEMENTED, AND WHY EACH WAY
--------------------------------------------------------------------------
`git` and `sed` are SHELLED OUT: they are the subject, not the packaging. `_sed_i`'s entire content is choosing `-i ''` on Darwin and `-i` elsewhere, and `_git_tree_fingerprint` is git plumbing orchestration.
The `find` walk, the sha256 stream, the prune rules, the byte sort and `sort -V`'s ordering are REIMPLEMENTED in Python, because a port that piped the same shell pipeline would be the same program and its differential would prove nothing.

WHY THE LOGGER IS `rediacc_ci.log`: `log_error` / `log_debug` here are `.ci/scripts/lib/common.sh:35-55`, and `rediacc_ci.log` is already the byte-exact port of those, tty gating included. The twin writes them to STDERR; so does this.
"""

from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import os
import pathlib
import platform
import re
import shutil
import stat
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.core import devbox

# `.ci/lib/local-common.sh:65`. `-path` in find is plain fnmatch: `*` crosses `/`, which is what makes a bare `*/dist/*` prune everything under any `dist` below the start point.
PRUNE_PATH_GLOBS = ("*/dist/*", "*/node_modules/*", "*/reports/*", "*/test-results/*")

# `.ci/lib/local-common.sh:66`. Matched against the BASENAME, which is what `-name` does.
PRUNE_NAME_GLOBS = ("*.tsbuildinfo", ".DS_Store")

# The two tools `.ci/lib/local-common.sh:29-35` resolves between, in its order.
SHA256_TOOLS = (("sha256sum",), ("shasum", "-a", "256"))

# `sha256sum` with no arguments and an empty stdin. See reproduced behaviour 1.
EMPTY_STDIN_LINE = "%s  -\n" % hashlib.sha256(b"").hexdigest()

# What `compute_hash_for_package_dirs` exits with when NO sha256 tool is installed, which is not 0 and not 1. See reproduced behaviour 6; the derivation is in `compute_hash_for_package_dirs`.
XARGS_KILLED_BY_SIGNAL = 125

# A name that is not a literal under `grep`'s BRE. See the module docstring.
BRE_METACHARACTERS = set(".[]*^$\\")


class LocalCommonError(RuntimeError):
    """A refusal the twin reports and then exits on."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


class Outcome:
    """A shell function's two observable channels: what it printed, and its status.

    The twin's functions are SHELL functions. Three of them can print a real answer and still exit non-zero (a missing `find` start point is the live case: the pipeline's other stages run, a hash reaches stdout, and `pipefail` carries find's 1 out), so a port returning only a value would drop half of what the differential compares.
    """

    __slots__ = ("code", "out")

    def __init__(self, out: str, code: int = 0) -> None:
        self.out = out
        self.code = code

    def __repr__(self) -> str:  # pragma: no cover -- diagnostics only
        return "Outcome(out=%r, code=%d)" % (self.out, self.code)


# --------------------------------------------------------------------------- paths ---------------------------------------------------------------------------


def local_root_dir(env: dict[str, str] | None = None) -> str:
    """`LOCAL_ROOT_DIR`, `.ci/lib/local-common.sh:16-18`, EXPORTED at `:914`.

    The twin derives it from its own location, three `cd ... && pwd` hops up from `.ci/lib/`, and then exports it, so every subprocess of a sourcer already carries the answer. This reads that export, then `CONSOLE_ROOT_DIR`, then falls back to the repository root.
    The differential compares the two derivations rather than feeding one to the other: the bash side emits the value it computed for itself and this side emits the value it computed for itself, so a disagreement is a mismatch.
    """
    environ = os.environ if env is None else env
    return (
        environ.get("LOCAL_ROOT_DIR", "")
        or environ.get("CONSOLE_ROOT_DIR", "")
        or str(paths.repo_root())
    )


def local_ci_dir(env: dict[str, str] | None = None) -> str:
    """`LOCAL_CI_DIR`, `.ci/lib/local-common.sh:17`."""
    environ = os.environ if env is None else env
    return environ.get("LOCAL_CI_DIR", "") or os.path.join(local_root_dir(env), ".ci")


def local_lib_dir(env: dict[str, str] | None = None) -> str:
    """`LOCAL_LIB_DIR`, `.ci/lib/local-common.sh:16`."""
    environ = os.environ if env is None else env
    return environ.get("LOCAL_LIB_DIR", "") or os.path.join(local_ci_dir(env), "lib")


# --------------------------------------------------------------------------- the portable tool wrappers ---------------------------------------------------------------------------


def sha256_command() -> list[str]:
    """`_SHA256SUM_CMD`, `.ci/lib/local-common.sh:29-35`, resolved the same way and in the same order.

    Empty list where the twin leaves the variable empty, which is the case both reproduced behaviours in 6 hang off.
    """
    for candidate in SHA256_TOOLS:
        if shutil.which(candidate[0]) is not None:
            return list(candidate)
    return []


def sha256_line(digest: str, name: str) -> str:
    r"""One `sha256sum` output line, escaping the way the tool on this machine escapes.

    MEASURED, NOT ASSUMED, because it decides the bytes the outer hash sees: a name containing a backslash or a newline makes the line start with a literal `\` and the offending characters doubled/escaped inside it. Confirmed 2026-09-23 against uutils 0.8.0: `sha256sum 'back\slash.txt'` prints `\<hex>  back\\slash.txt`. GNU coreutils has escaped the same way since 8.25.
    """
    if "\\" in name or "\n" in name or "\r" in name:
        escaped = name.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
        return "\\%s  %s\n" % (digest, escaped)
    return "%s  %s\n" % (digest, name)


def digest_file(path: str) -> str:
    """The hex `sha256sum <file>` prints, streamed rather than slurped."""
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def sha256sum(names: list[str], stdin: bytes | None = None) -> Outcome:
    """`_sha256sum`, `.ci/lib/local-common.sh:37-43`.

    Raises `LocalCommonError(code=1)` where the twin logs and calls `exit 1`, which in a SOURCED function takes the whole shell down rather than returning to the caller. See reproduced behaviour 6.

    AN UNREADABLE FILE IS NOT AN EXCEPTION, because the tool does not raise either: it names the file on stderr, omits its line, hashes everything else, and exits 1. Measured 2026-09-23. The port raised `FileNotFoundError` here until the differential showed the twin reporting and carrying on, which is the same shape the `core.account` port's missing-curl defect took.
    """
    if not sha256_command():
        log.error("No sha256 tool found (need sha256sum or shasum)")
        raise LocalCommonError("no sha256 tool", code=1)
    if not names:
        body = b"" if stdin is None else stdin
        return Outcome(sha256_line(hashlib.sha256(body).hexdigest(), "-"), 0)
    out = []
    code = 0
    for name in names:
        try:
            digest = digest_file(name)
        except OSError as exc:
            sys.stderr.write("sha256sum: %s: %s\n" % (name, exc.strerror))
            code = 1
            continue
        out.append(sha256_line(digest, name))
    return Outcome("".join(out), code)


def cd_error(path: str) -> str | None:
    """bash's `cd` diagnostic for `path`, or None when `cd` would succeed.

    REPRODUCED BECAUSE IT IS THE ONLY THING THE TWIN PRINTS on that path. `compute_hash_for_package_dirs` and `_git_tree_fingerprint` both open with `cd "$root" || exit`, and an unusable root therefore produces one line on stderr and nothing else; `compute_tree_hash` over an unusable root produces TWO, one per function, which is how a reader can see the fallback really
    happened.
    The `<file>: line <N>: ` stamp bash puts in front of it names a line inside the twin, is not reproducible by a port and is not worth reproducing, so the differential harness strips that prefix from both sides and compares the message itself.
    """
    try:
        os.stat(path)
    except OSError as exc:
        return "cd: %s: %s" % (path, exc.strerror)
    if not os.path.isdir(path):
        return "cd: %s: Not a directory" % path
    if not os.access(path, os.X_OK):
        return "cd: %s: Permission denied" % path
    return None


def sed_i(args: list[str], env: dict[str, str] | None = None) -> Outcome:
    """`_sed_i`, `.ci/lib/local-common.sh:46-52`.

    SHELLED OUT, deliberately: the entire content of this function is choosing the in-place flag, and reimplementing `sed` to prove that choice would be measuring the wrong thing. `platform.system()` is `uname -s` on every platform this repository runs on.
    """
    environ = os.environ if env is None else env
    argv = ["sed", "-i", ""] if platform.system() == "Darwin" else ["sed", "-i"]
    proc = subprocess.run(
        argv + args, env=dict(environ), capture_output=True, text=True, check=False
    )
    sys.stderr.write(proc.stderr)
    return Outcome(proc.stdout, proc.returncode)


# --------------------------------------------------------------------------- the full walk ---------------------------------------------------------------------------


def is_pruned(path: str) -> bool:
    """The two `-prune` arms of `.ci/lib/local-common.sh:65-66`, in the twin's order."""
    for glob in PRUNE_PATH_GLOBS:
        if fnmatch.fnmatchcase(path, glob):
            return True
    base = os.path.basename(path.rstrip("/")) or path
    return any(fnmatch.fnmatchcase(base, glob) for glob in PRUNE_NAME_GLOBS)


def join_under(parent: str, name: str) -> str:
    """How find builds a child path: no doubled separator after a trailing slash.

    `find pkg/ -type f` prints `pkg/.DS_Store`, not `pkg//.DS_Store`. Measured.
    """
    return parent + name if parent.endswith("/") else parent + "/" + name


def find_files(root: str, start_points: list[str]) -> tuple[list[str], bool]:
    """`find "$@" \\( -path ... \\) -prune -o \\( -name ... \\) -prune -o -type f -print0`.

    Returns the paths find would print (UNSORTED, as find emits them) and whether find hit an error, which is what its exit status 1 means and what `pipefail` carries out of the whole pipeline.

    `-type f` uses `lstat`, so a SYMLINK to a regular file is not printed. With no start point at all find defaults to `.`, which this reproduces because `compute_hash_for_package_dirs` is callable with none.
    """
    out: list[str] = []
    failed = False
    points = start_points or ["."]
    for start in points:
        stack = [start]
        while stack:
            current = stack.pop()
            if is_pruned(current):
                continue
            absolute = os.path.join(root, current)
            try:
                status = os.lstat(absolute)
            except OSError:
                failed = True
                continue
            if stat.S_ISDIR(status.st_mode):
                try:
                    names = os.listdir(absolute)
                except OSError:
                    failed = True
                    continue
                stack.extend(join_under(current, name) for name in names)
            elif stat.S_ISREG(status.st_mode):
                out.append(current)
    return out, failed


def sha256_lines(root: str, names: list[str]) -> str:
    """`xargs -0 $_SHA256SUM_CMD 2>/dev/null` over the sorted name list.

    THE EMPTY CASE IS NOT AN EMPTY STREAM. See reproduced behaviour 1: xargs still runs the command once, with no arguments, and the tool then hashes its own empty stdin.

    An UNREADABLE file is skipped rather than raised on, which is what `sha256sum` does: it writes to stderr, which `2>/dev/null` discards, and omits the line.
    """
    if not names:
        return EMPTY_STDIN_LINE
    out = []
    for name in names:
        try:
            digest = digest_file(os.path.join(root, name))
        except OSError:
            continue
        out.append(sha256_line(digest, name))
    return "".join(out)


def compute_hash_for_package_dirs(
    root_dir: str, start_points: list[str], env: dict[str, str] | None = None
) -> Outcome:
    """`compute_hash_for_package_dirs`, `.ci/lib/local-common.sh:58-73`.

    `cd "$root_dir" || exit` inside a subshell: an unusable root prints NOTHING and exits 1, which is why the empty-output case has to be distinguishable from the empty-file-set case above.

    A MISSING START POINT IS NOT A MISSING ANSWER. find reports it on stderr (discarded) and exits 1, the rest of the pipeline still runs, a real hash reaches stdout, and `pipefail` makes the whole thing non-zero. Both channels are returned.
    """
    del env  # the twin reads nothing from the environment here beyond `_SHA256SUM_CMD`
    failure = cd_error(root_dir)
    if failure is not None:
        sys.stderr.write(failure + "\n")
        return Outcome("", 1)
    if not sha256_command():
        # `$_SHA256SUM_CMD` EXPANDS TO NOTHING, and the exit status that produces is 125 rather than the 0 this port first assumed. MEASURED 2026-09-23 against a PATH with neither `sha256sum` nor `shasum` on it, in all three shapes (a populated tree, an empty one, a missing start point), and the port was WRONG until that control ran.
        # The derivation: `xargs -0` with no command defaults to `echo`; the next two pipeline stages are empty commands, so nothing reads the pipe; `echo` takes SIGPIPE; GNU xargs reports a child killed by a signal as 125; `pipefail` carries it out. Stdout and stderr are both empty, so a caller sees an empty hash with a status nobody checks.
        # A CONTROL, NOT A SCENARIO. Every differential scenario runs with `sha256sum` installed, so this branch is unreachable from the ledger; `test_core_local_common.py` builds the PATH farm that reaches it and compares the two sides live rather than against this constant.
        return Outcome("", XARGS_KILLED_BY_SIGNAL)
    found, failed = find_files(root_dir, start_points)
    # `LC_ALL=C sort -z`: a BYTE sort of the NUL-terminated names, not a locale one.
    ordered = sorted(found, key=os.fsencode)
    stream = sha256_lines(root_dir, ordered)
    digest = hashlib.sha256(stream.encode("utf-8", "surrogateescape")).hexdigest()
    # `| $_SHA256SUM_CMD | awk '{print $1}'`: the outer hash, field one, one newline.
    return Outcome(digest + "\n", 1 if failed else 0)


# --------------------------------------------------------------------------- the git fast path ---------------------------------------------------------------------------


def git(
    root: str, args: list[str], env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    """One git call in `root`, with stdout captured as BYTES because `-z` output is not text."""
    environ = os.environ if env is None else env
    return subprocess.run(
        ["git", *args], cwd=root, env=dict(environ), capture_output=True, check=False
    )


def git_tree_fingerprint(
    root: str,
    start_points: list[str],
    env: dict[str, str] | None = None,
    errexit: bool = True,
) -> str | None:
    """`_git_tree_fingerprint`, `.ci/lib/local-common.sh:92-134`.

    Returns the fingerprint with its trailing newline, or None everywhere the twin prints nothing and exits 1: git absent, not a work tree, no HEAD, an unusable root, or a failed plumbing call.

    `errexit` IS NOT A STYLE KNOB, it is reproduced behaviour 2. With it True the port dies where the twin's bare `existing=` assignment dies under armed errexit; with it False the port runs on, which is what the twin does when `compute_tree_hash` calls it from an `if` condition.
    """
    failure = cd_error(root)
    if failure is not None:
        sys.stderr.write(failure + "\n")
        return None
    if shutil.which("git") is None:
        return None
    if git(root, ["rev-parse", "--verify", "-q", "HEAD"], env).returncode != 0:
        return None

    pieces: list[bytes] = []
    for args in (
        ["ls-files", "-m", "-d", "-z", "--", *start_points],
        ["ls-files", "-o", "--exclude-standard", "-z", "--", *start_points],
        ["diff", "--cached", "--name-only", "-z", "--", *start_points],
    ):
        proc = git(root, args, env)
        if proc.returncode != 0:
            # `{ ...; ...; ...; } | sort -zu | tr` under `pipefail`, then `|| exit 1`.
            return None
        pieces.append(proc.stdout)

    # `LC_ALL=C sort -zu`: byte sort, unique, over NUL-terminated records.
    raw = b"".join(pieces)
    records = sorted({record for record in raw.split(b"\0") if record != b""})
    changed = "\n".join(os.fsdecode(record) for record in records)

    existing: list[str] = []
    if changed:
        last_ok = True
        for name in changed.split("\n"):
            last_ok = os.path.isfile(os.path.join(root, name))
            if last_ok:
                existing.append(name)
        if errexit and not last_ok:
            # The bare assignment takes the while loop's status, and the loop's status is the LAST iteration's. Reproduced behaviour 2.
            return None

    hashes = ""
    if existing:
        proc = subprocess.run(
            ["git", "hash-object", "--stdin-paths"],
            cwd=root,
            env=dict(os.environ if env is None else env),
            input=("\n".join(existing) + "\n").encode("utf-8", "surrogateescape"),
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            return None
        hashes = os.fsdecode(proc.stdout).rstrip("\n")

    stream: list[str] = []
    for point in start_points:
        if point == ".":
            probe = git(root, ["rev-parse", "-q", "--verify", "HEAD^{tree}"], env)
            fallback = "no-tree:.\n"
        else:
            probe = git(root, ["rev-parse", "-q", "--verify", "HEAD:%s" % point], env)
            fallback = "no-tree:%s\n" % point
        stream.append(os.fsdecode(probe.stdout) if probe.returncode == 0 else fallback)
    # `printf '%s\n' "$changed"` on an EMPTY value still writes one newline, and so does the one below it. Two bytes that are always in the hashed stream.
    stream.append(changed + "\n")
    stream.append(hashes + "\n")
    body = "".join(stream).encode("utf-8", "surrogateescape")
    return hashlib.sha256(body).hexdigest() + "\n"


def compute_tree_hash(
    root: str, start_points: list[str], env: dict[str, str] | None = None
) -> Outcome:
    """`compute_tree_hash`, `.ci/lib/local-common.sh:137-146`.

    `if fp="$(_git_tree_fingerprint ...)" && [[ -n "$fp" ]]` is an `if` CONDITION, so errexit is suppressed inside it; `errexit=False` below is that call site, not a preference.
    """
    fingerprint = git_tree_fingerprint(root, start_points, env, errexit=False)
    if fingerprint is not None and fingerprint.strip("\n") != "":
        return Outcome(fingerprint.strip("\n") + "\n", 0)
    return compute_hash_for_package_dirs(root, start_points, env)


# --------------------------------------------------------------------------- the stamps ---------------------------------------------------------------------------


def read_stamp_hash(stamp_file: str) -> str:
    """`read_stamp_hash`, `.ci/lib/local-common.sh:148-154`.

    `cat` and nothing else, so the trailing newline `write_stamp_hash` added is STILL THERE. A missing file yields the empty string and status 0, which is the whole reason a fresh checkout reads as stale rather than as an error.
    """
    if not os.path.isfile(stamp_file):
        return ""
    return pathlib.Path(stamp_file).read_text(encoding="utf-8", errors="surrogateescape")


def write_stamp_hash(stamp_file: str, stamp_hash: str) -> None:
    """`write_stamp_hash`, `.ci/lib/local-common.sh:156-162`.

    `printf '%s\\n'` APPENDS A NEWLINE. See reproduced behaviour 5.

    `mkdir -p "$(dirname "$stamp_file")"`, and `dirname` answers `.` for a bare name where `os.path.dirname` answers the empty string. Getting that wrong turns a relative stamp path into a `mkdir("")`.
    """
    parent = os.path.dirname(stamp_file) or "."
    os.makedirs(parent, exist_ok=True)
    with open(stamp_file, "w", encoding="utf-8", errors="surrogateescape") as handle:
        handle.write(stamp_hash + "\n")


# --------------------------------------------------------------------------- version ordering ---------------------------------------------------------------------------


def _order(char: int) -> int:
    """gnulib `filevercmp.c`'s `order()`: `~` sorts before the end of string, digits are handled by the caller, letters keep their byte value and everything else sorts after every letter."""
    if 0x30 <= char <= 0x39:
        return 0
    if (0x41 <= char <= 0x5A) or (0x61 <= char <= 0x7A):
        return char
    if char == 0x7E:
        return -1
    return char + 1 + 0xFF


def verrevcmp(one: bytes, two: bytes) -> int:
    """gnulib `filevercmp.c`'s `verrevcmp()`, the core of `sort -V`.

    Digit runs compare NUMERICALLY with leading zeros skipped, everything else compares under `_order`. Transcribed rather than approximated: a `version_tuple`-style split answers `1.10 < 1.9` correctly and then gets `2.0~rc1 < 2.0` wrong, and the `~` rule is the one a hand-rolled comparison always misses.
    """
    i = j = 0
    len_one, len_two = len(one), len(two)
    while i < len_one or j < len_two:
        first_diff = 0
        while (i < len_one and not 0x30 <= one[i] <= 0x39) or (
            j < len_two and not 0x30 <= two[j] <= 0x39
        ):
            left = 0 if i == len_one else _order(one[i])
            right = 0 if j == len_two else _order(two[j])
            if left != right:
                return left - right
            i += 1
            j += 1
        while i < len_one and one[i] == 0x30:
            i += 1
        while j < len_two and two[j] == 0x30:
            j += 1
        while i < len_one and j < len_two and 0x30 <= one[i] <= 0x39 and 0x30 <= two[j] <= 0x39:
            if not first_diff:
                first_diff = one[i] - two[j]
            i += 1
            j += 1
        if i < len_one and 0x30 <= one[i] <= 0x39:
            return 1
        if j < len_two and 0x30 <= two[j] <= 0x39:
            return -1
        if first_diff:
            return first_diff
    return 0


def suffix_length(text: bytes) -> int:
    r"""gnulib `filevercmp.c`'s `match_suffix()`: the trailing `(\.[A-Za-z~][A-Za-z0-9~]*)*`.

    A version string rarely has one, but `1.0.0.tar.gz` does, and `sort -V` compares the STEM first. Left in rather than dropped as unreachable, because `_version_gte` is a general-purpose helper and its only current caller passes a Go version read out of `go.mod`.
    """
    length = len(text)
    read = 0
    match = -1
    while read < length:
        if text[read] == 0x2E:
            start = read
            read += 1
            if read < length and (
                (0x41 <= text[read] <= 0x5A) or (0x61 <= text[read] <= 0x7A) or text[read] == 0x7E
            ):
                read += 1
                while read < length and (
                    (0x30 <= text[read] <= 0x39)
                    or (0x41 <= text[read] <= 0x5A)
                    or (0x61 <= text[read] <= 0x7A)
                    or text[read] == 0x7E
                ):
                    read += 1
                if match < 0:
                    match = start
                continue
            match = -1
            continue
        read += 1
        match = -1
    return length - match if match >= 0 else 0


def filevercmp(one: bytes, two: bytes) -> int:
    """gnulib `filevercmp()`, which is the comparison `sort -V` uses per line."""
    if one == two:
        return 0
    if one == b"":
        return -1
    if two == b"":
        return 1
    one_dot = one[:1] == b"."
    two_dot = two[:1] == b"."
    if one_dot and not two_dot:
        return -1
    if two_dot and not one_dot:
        return 1
    if one_dot and two_dot:
        one_special = one[1:] in (b"", b".")
        two_special = two[1:] in (b"", b".")
        if one_special and two_special:
            return verrevcmp(one, two)
        if one_special:
            return -1
        if two_special:
            return 1
    one_body = one[1:] if one_dot else one
    two_body = two[1:] if two_dot else two
    one_stem = one_body[: len(one_body) - suffix_length(one_body)]
    two_stem = two_body[: len(two_body) - suffix_length(two_body)]
    result = verrevcmp(one_stem, two_stem)
    if result != 0:
        return result
    return verrevcmp(one_body, two_body)


def version_gte(one: str, two: str) -> bool:
    """`_version_gte`, `.ci/lib/local-common.sh:545-550`. Is `$1 >= $2`?

    The twin sorts the two strings and asks whether `$2` came first, so the port answers the same question the same way, including `sort`'s LAST-RESORT byte comparison for two strings that compare equal under `-V` without being equal: `sort` falls back to a whole-line compare unless `-s` is given, and `_version_gte` does not give it.

    VALIDATED AGAINST THE LIVE `sort -V`, not against a reading of one: 2,401 ordered pairs drawn from a 49-string corpus (versions, leading zeros, `~`, `rc`/`beta` suffixes, bare dots, empty strings, `.tar.gz`) agreed on every one. The tool measured was uutils 0.8.0, which is what is on PATH here; see the tool-set note in the module docstring.
    """
    if one == two:
        return True
    left, right = one.encode("utf-8", "surrogateescape"), two.encode("utf-8", "surrogateescape")
    compared = filevercmp(left, right)
    if compared == 0:
        compared = (left > right) - (left < right)
    lower = one if compared <= 0 else two
    return lower == two


# --------------------------------------------------------------------------- package.json ---------------------------------------------------------------------------


def has_npm_script(script_name: str, env: dict[str, str] | None = None) -> bool:
    """`has_npm_script`, `.ci/lib/local-common.sh:401-404`.

    `grep -q "\\"$script_name\\":" "$LOCAL_ROOT_DIR/package.json"`, which is a SEARCH OF THE WHOLE FILE and not of the `scripts` object: reproduced behaviour 3. A missing file raises with code 2, which is grep's: reproduced behaviour 4.

    Raises `ValueError` on a name carrying a BRE metacharacter. See the module docstring.
    """
    metachars = BRE_METACHARACTERS & set(script_name)
    if metachars:
        raise ValueError(
            "script name %r carries the BRE metacharacter(s) %s; the twin tests for it "
            'with `grep -q "\\"$script_name\\":"`, where that is a pattern and not a '
            "literal, so this port would silently answer a different question. Add a case "
            "to test_core_local_common.py pinning what the twin actually does before "
            "allowing it." % (script_name, "".join(sorted(metachars)))
        )
    target = os.path.join(local_root_dir(env), "package.json")
    try:
        text = pathlib.Path(target).read_text(encoding="utf-8", errors="surrogateescape")
    except OSError as exc:
        # grep's own diagnostic, un-prefixed, on stderr, and its own exit status.
        sys.stderr.write("grep: %s: %s\n" % (target, exc.strerror))
        raise LocalCommonError("grep could not read %s" % target, code=2) from exc
    return ('"%s":' % script_name) in text


# --------------------------------------------------------------------------- the machine-mutating half ---------------------------------------------------------------------------
#
# EVERYTHING BELOW CHANGES THE MACHINE OR TALKS TO A PERSON, and is proved by the STUB-FARM TRANSCRIPT differential (`core/stubfarm.py`, driven by `core/local_common_shadow_driver.py`): both sides run with `npm`, `node`, `go`, `sudo`, `curl`, `tar`, `gcc`, `docker`, `sg` and the rest replaced by stubs that log their argv, and the comparison is rc, both streams, the files written AND the ordered call list.
# That is why the port calls PROGRAMS where a Python programmer would reach for a library: `uname`, `mktemp` and `go version` are the twin's questions, and a scenario answers them through the stubs. A port that asked `platform.system()` instead could not be put on the other branch at all.
#
# ERREXIT. Every sourcer arms `set -euo pipefail`, so a bare command that fails ENDS THE PROCESS rather than returning. `_must()` is that: it raises `LocalCommonError` with the command's own status, and `main()` exits with it.


def _flush() -> None:
    """Flush both streams before a child writes to the same descriptors, so the twin's line order survives."""
    sys.stdout.flush()
    sys.stderr.flush()


def _run(
    argv: list[str],
    *,
    cwd: str | None = None,
    quiet_out: bool = False,
    quiet_err: bool = False,
    stdout=None,
    env: dict[str, str] | None = None,
) -> int:
    """A bare command line of the twin's: streams inherited unless it redirects them."""
    _flush()
    out = subprocess.DEVNULL if quiet_out else stdout
    return subprocess.run(
        argv,
        cwd=cwd,
        stdout=out,
        stderr=subprocess.DEVNULL if quiet_err else None,
        env=env,
        check=False,
    ).returncode


def _must(argv: list[str], **kwargs) -> None:
    """A bare command under errexit: a non-zero status ends the process with that status."""
    status = _run(argv, **kwargs)
    if status != 0:
        raise LocalCommonError("%s exited %d under errexit" % (argv[0], status), code=status)


def _capture(
    argv: list[str], *, quiet_err: bool = False, cwd: str | None = None
) -> subprocess.CompletedProcess:
    """`$(argv)`: stdout captured, stderr inherited unless the twin discards it."""
    _flush()
    return subprocess.run(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL if quiet_err else None,
        text=True,
        check=False,
    )


def _subst(text: str) -> str:
    """What `$(...)` keeps: everything but the trailing newlines."""
    return text.rstrip("\n")


def _uname(flag: str) -> str:
    """`$(uname <flag>)`, asked of the PROGRAM. See the section note above."""
    return _subst(_capture(["uname", flag]).stdout)


def ci_os() -> str:
    """`CI_OS`, which `common.sh:510` sets once at load time from `detect_os`, i.e. from `uname -s`."""
    raw = _uname("-s")
    for prefix, name in (
        ("Linux", "linux"),
        ("Darwin", "macos"),
        ("CYGWIN", "windows"),
        ("MINGW", "windows"),
        ("MSYS", "windows"),
    ):
        if raw.startswith(prefix):
            return name
    return "unknown"


def _hex_of(stream: bytes) -> str:
    """`| _sha256sum | awk '{print $1}'` over a stream: the digest alone."""
    return hashlib.sha256(stream).hexdigest()


def ensure_cpu_features_gypi(node_modules_dir: str) -> bool:
    """`ensure_cpu_features_gypi`, `.ci/lib/local-common.sh:178`. False where the twin returns 1.

    The `>` into `buildcheck.gypi.tmp` belongs to the SUBSHELL, so the file exists before `node` runs and whether or not it succeeds; the failure arm removes it. Publishing only after success is the twin's whole point and is kept.
    """
    features = os.path.join(node_modules_dir, "cpu-features")
    gypi = os.path.join(features, "buildcheck.gypi")
    if os.path.isfile(gypi) and os.path.getsize(gypi) == 0:
        log.debug("Removing empty buildcheck.gypi left by a failed run")
        os.remove(gypi)
    if os.path.isfile(os.path.join(features, "buildcheck.js")) and not os.path.isfile(gypi):
        temporary = os.path.join(features, "buildcheck.gypi.tmp")
        with open(temporary, "wb") as handle:
            status = _run(["node", "buildcheck.js"], cwd=features, stdout=handle)
        if status != 0:
            with contextlib.suppress(OSError):
                os.remove(temporary)
            log.error("cpu-features buildcheck failed (is a C compiler installed?)")
            return False
        os.replace(temporary, gypi)
    return True


def _hash_line(path: str) -> bytes:
    """`_sha256sum <file>`'s line inside `ensure_deps`' `{ ...; }` group.

    AN UNREADABLE FILE DOES NOT STOP THE HASH. The group's status is its LAST command's (the `printf 'runtime=...'`), so `sha256sum` naming a missing lockfile on stderr and exiting 1 is invisible to `pipefail`; the line is simply absent from what gets hashed. No tool at all is different: `_sha256sum` calls `exit 1`, which ends the group and, through `pipefail`, the assignment.
    """
    return sha256sum([path]).out.encode("utf-8", "surrogateescape")


def deps_hash(env: dict[str, str] | None = None) -> str:
    """`ensure_deps`' `current_hash`: the manifests, the lockfile, `.npmrc` when present, and the runtime tag.

    `_sha256sum` prints the path AS GIVEN, which is absolute, so the hash depends on where the checkout lives. Reproduced, not normalised: the stamp is per checkout anyway.
    """
    environ = os.environ if env is None else env
    root = local_root_dir(env)
    stream = _hash_line(os.path.join(root, "package.json"))
    stream += _hash_line(os.path.join(root, "package-lock.json"))
    if os.path.isfile(os.path.join(root, ".npmrc")):
        stream += _hash_line(os.path.join(root, ".npmrc"))
    stream += ("runtime=%s\n" % (environ.get("REDIACC_NPM_RUNTIME") or "host")).encode()
    return _hex_of(stream)


def ensure_deps(env: dict[str, str] | None = None) -> bool:
    """`ensure_deps`, `.ci/lib/local-common.sh:203`. False where the twin returns 1; errexit deaths raise."""
    root = local_root_dir(env)
    node_modules = os.path.join(root, "node_modules")
    stamp = os.path.join(root, ".ci", "cache", "npm-install.stamp")
    current = deps_hash(env)
    saved = _subst(read_stamp_hash(stamp))
    if (
        os.path.isdir(node_modules)
        and os.access(os.path.join(node_modules, ".bin", "tsx"), os.X_OK)
        and os.path.islink(os.path.join(node_modules, "@rediacc", "cli"))
        and saved == current
    ):
        log.debug("Dependencies are up-to-date (stamp matched)")
        return True
    log.step("Installing dependencies...")
    _must(["npm", "install"], cwd=root)
    if not ensure_cpu_features_gypi(node_modules):
        return False
    log.step("Compiling native modules (blocked at install by ignore-scripts)...")
    _must(["npm", "run", "install:natives"], cwd=root)
    write_stamp_hash(stamp, current)
    return True


def _tree_hash_or_die(root: str, points: list[str]) -> str:
    """`current_hash="$(compute_tree_hash ...)"`: a bare assignment, so a failing hash is the twin's death."""
    outcome = compute_tree_hash(root, points)
    if outcome.code != 0:
        raise LocalCommonError("compute_tree_hash failed", code=outcome.code)
    return outcome.out


def ensure_packages_built(env: dict[str, str] | None = None) -> bool:
    """`ensure_packages_built`, `.ci/lib/local-common.sh:278`."""
    root = local_root_dir(env)
    stamp = os.path.join(root, ".ci", "cache", "build-packages.stamp")
    current = _subst(_tree_hash_or_die(root, ["packages/shared", "packages/provisioning"]))
    saved = _subst(read_stamp_hash(stamp))
    if (
        os.path.isdir(os.path.join(root, "packages", "shared", "dist"))
        and os.path.isdir(os.path.join(root, "packages", "provisioning", "dist"))
        and saved == current
    ):
        log.debug("Shared packages are up-to-date (stamp matched)")
        return True
    log.step("Building shared packages...")
    _must([os.path.join(local_ci_dir(env), "scripts", "setup", "build-packages.sh")])
    write_stamp_hash(stamp, current)
    return True


def ensure_cli_built(env: dict[str, str] | None = None) -> bool:
    """`ensure_cli_built`, `.ci/lib/local-common.sh:303`.

    A MISSING `build-packages.stamp` hashes as empty. It used to KILL THE TWIN SILENTLY: the stamp `cat` was the last command of the `{ ...; }` group feeding `| _sha256sum | awk` in a bare assignment, so its exit 1 became the pipeline's status under `pipefail` and errexit ended the process with no message. Found by this port's `cli-no-packages-stamp` case on 2026-09-24 and fixed in the twin in the same change (`|| true`); both sides now build.
    """
    root = local_root_dir(env)
    entry = os.path.join(root, "packages", "cli", "dist", "cli-bundle.cjs")
    stamp = os.path.join(root, ".ci", "cache", "build-cli.stamp")
    packages_stamp = os.path.join(root, ".ci", "cache", "build-packages.stamp")
    tree = compute_tree_hash(root, ["packages/cli"])
    try:
        with open(packages_stamp, "rb") as handle:
            stamp_bytes = handle.read()
    except OSError:
        stamp_bytes = b""
    current = _hex_of(tree.out.encode("utf-8", "surrogateescape") + stamp_bytes)
    saved = _subst(read_stamp_hash(stamp))
    if os.path.isfile(entry) and saved == current:
        log.debug("CLI build is up-to-date (stamp matched)")
        return True
    log.step("Building CLI...")
    _must(["npm", "run", "build", "-w", "@rediacc/cli"], cwd=root)
    _must(["npm", "run", "build:bundle", "-w", "@rediacc/cli"], cwd=root)
    if not os.path.isfile(entry):
        log.error("CLI build failed: entrypoint not found at %s" % entry)
        raise LocalCommonError("no CLI entrypoint", code=1)
    write_stamp_hash(stamp, current)
    return True


def prompt_continue(message: str = "Continue?") -> bool:
    """`prompt_continue`, `.ci/lib/local-common.sh:341`.

    `read -p` PRINTS ITS PROMPT ONLY WHEN STDIN IS A TERMINAL, to stderr, and that is bash's rule rather than the twin's; piped input answers silently. End of input is a `read` failure, which the documented call shape `prompt_continue ... || exit 1` turns into "no". A backslash in the answer is an escape to `read` without `-r`, so `\\y` reads as `y`.
    """
    if sys.stdin.isatty():
        sys.stderr.write("%s (y/N): " % message)
        sys.stderr.flush()
    line = sys.stdin.readline()
    if not line:
        return False
    # A trailing UNESCAPED backslash (an odd run) is a line CONTINUATION to `read` without `-r`.
    while line.endswith("\n"):
        body = line[:-1]
        run = len(body) - len(body.rstrip("\\"))
        if run % 2 == 0:
            break
        more = sys.stdin.readline()
        line = body[:-1] + more
        if not more:
            break
    answer = line.rstrip("\n")
    unescaped, index = [], 0
    while index < len(answer):
        if answer[index] == "\\" and index + 1 < len(answer):
            index += 1
        unescaped.append(answer[index])
        index += 1
    answer = "".join(unescaped).strip(" \t")
    return answer in ("y", "Y")


def open_browser(url: str) -> None:
    """`open_browser`, `.ci/lib/local-common.sh:351`. Every arm swallows its failure."""
    system = ci_os()
    if system == "macos":
        _run(["open", url], quiet_err=True)
    elif system == "linux":
        if shutil.which("xdg-open") is not None:
            _run(["xdg-open", url], quiet_err=True)
    elif system == "windows":
        _run(["cmd", "/c", "start", "", url], quiet_err=True)


def run_npm_script(script_name: str, description: str | None = None, env=None) -> None:
    """`run_npm_script`, `.ci/lib/local-common.sh:378`. A failing script is the twin's errexit death."""
    log.step(description or "Running npm script: %s" % script_name)
    _must(["npm", "run", script_name], cwd=local_root_dir(env))


def check_node_version(min_version: str = "18.0.0") -> bool:
    """`check_node_version`, `.ci/lib/local-common.sh:388`.

    The ONLY Python copy: `core/account.py` and `core/account_lifecycle.py` import it (their older duplicate with a `version_tuple` compare was deleted 2026-09-24).

    `node -v | cut -d'v' -f2` keeps the SECOND `v`-separated field (the whole line when there is no `v`), and `sort -V -C` asks whether min-then-current is already in version order, which is `version_gte(current, min)` under the same comparator, `filevercmp` included.
    """
    if shutil.which("node") is None:
        log.error("Node.js is not installed")
        return False
    proc = _capture(["node", "-v"])
    if proc.returncode != 0:
        raise LocalCommonError("node -v failed under pipefail", code=proc.returncode)
    lines = []
    for line in proc.stdout.split("\n"):
        fields = line.split("v")
        lines.append(fields[1] if len(fields) > 1 else line)
    current = _subst("\n".join(lines))
    if not version_gte(current, min_version):
        log.error("Node.js version %s is too old (minimum: %s)" % (current, min_version))
        return False
    log.debug("Node.js version: %s" % current)
    return True


def check_go_installed() -> None:
    """`check_go_installed`, `.ci/lib/local-common.sh:409`: `exit 1` where Go is missing."""
    found = shutil.which("go")
    if found is None:
        log.error("Go is not installed (required for building renet)")
        log.info("Install Go from: https://go.dev/dl/")
        raise LocalCommonError("go is not installed", code=1)
    log.debug("Go present: %s" % found)


def _gomod_version(gomod: str) -> str:
    """The `toolchain goX` line's version, else the `go X` line's, as the twin's two `sed -n ... | head -1` read them."""
    text = pathlib.Path(gomod).read_text(encoding="utf-8", errors="surrogateescape")
    for pattern in (r"^toolchain go([0-9.]*)", r"^go ([0-9.]*)"):
        for line in text.split("\n"):
            match = re.match(pattern, line)
            if match:
                if match.group(1):
                    return match.group(1)
                break
    return ""


def ensure_go_installed(env: dict[str, str] | None = None) -> bool:
    """`ensure_go_installed`, `.ci/lib/local-common.sh:428`."""
    root = local_root_dir(env)
    gomod = os.path.join(root, "private", "renet", "go.mod")
    want = _gomod_version(gomod) if os.path.isfile(gomod) else ""
    if not want:
        log.error("Cannot determine the required Go version (no readable %s)" % gomod)
        return False

    if shutil.which("go") is not None:
        proc = _capture(["go", "version"])
        if proc.returncode != 0:
            raise LocalCommonError("go version failed under pipefail", code=proc.returncode)
        have = ""
        for line in proc.stdout.split("\n"):
            match = re.match(r".*go([0-9][0-9.]*).*", line)
            if match:
                have = match.group(1)
                break
        if version_gte(have, want):
            log.debug("Go %s present (>= %s)" % (have, want))
            return True
        log.info("Go %s is older than the required %s" % (have, want))

    if _uname("-s") != "Linux":
        log.error("Go %s is required and this helper only installs it on Linux" % want)
        log.info("Install it from https://go.dev/dl/ and re-run")
        return False

    machine = _uname("-m")
    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    else:
        log.error("Unsupported architecture for the Go tarball: %s" % _uname("-m"))
        return False

    tarball = "go%s.linux-%s.tar.gz" % (want, arch)
    url = "https://go.dev/dl/%s" % tarball
    tmp = _subst(_capture(["mktemp", "-d"]).stdout)
    download = os.path.join(tmp, tarball)

    log.step("Installing Go %s (%s) into /usr/local/go" % (want, arch))
    log.info(url)
    if _run(["curl", "-fL", "--progress-bar", "-o", download, url]) != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        log.error("Download failed: %s" % url)
        return False
    if _run(["tar", "-tzf", download], quiet_out=True, quiet_err=True) != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        log.error("Downloaded file is not a valid tarball: %s" % tarball)
        return False

    _must(["sudo", "rm", "-rf", "/usr/local/go"])
    if _run(["sudo", "tar", "-C", "/usr/local", "-xzf", download]) != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        log.error("Failed to unpack %s into /usr/local" % tarball)
        return False
    shutil.rmtree(tmp, ignore_errors=True)

    os.environ["PATH"] = "/usr/local/go/bin:%s" % os.environ.get("PATH", "")
    if shutil.which("go") is None:
        log.error("Go was unpacked but /usr/local/go/bin/go is not on PATH")
        return False
    log.info("Go installed: %s" % _subst(_capture(["go", "version"]).stdout))

    if not os.path.isfile("/etc/profile.d/golang.sh"):
        _flush()
        # `echo ... | sudo tee ... >/dev/null`, a bare pipeline under pipefail: tee's status decides.
        tee = subprocess.run(
            ["sudo", "tee", "/etc/profile.d/golang.sh"],
            input=b'export PATH="/usr/local/go/bin:$PATH"\n',
            stdout=subprocess.DEVNULL,
            check=False,
        )
        if tee.returncode != 0:
            raise LocalCommonError("sudo tee failed", code=tee.returncode)
        _must(["sudo", "chmod", "0644", "/etc/profile.d/golang.sh"])
        log.info("Added /etc/profile.d/golang.sh (new shells get go on PATH)")
    return True


def ensure_bashcov_sup(env: dict[str, str] | None = None) -> bool:
    """`ensure_bashcov_sup`, `.ci/lib/local-common.sh:536`. Always True, as the twin always returns 0.

    TWIN DEFECT FIXED IN THE SAME CHANGE, 2026-09-24: the twin read `$REPO_ROOT`, which nothing on its load path defines, so under `set -u` it died with "REPO_ROOT: unbound variable" on EVERY call and `./run.sh setup` (which calls it through `setup/bridge.py`) never built the supervisor. The twin now reads `LOCAL_ROOT_DIR`; so does this.
    """
    src = os.path.join(local_root_dir(env), ".devcontainer", "bashcov-sup.c")
    binary = os.path.join(
        os.environ.get("HOME", ""), ".local", "share", "rediacc", "bin", "bashcov-sup"
    )
    if not os.path.isfile(src):
        return True
    if os.access(binary, os.X_OK) and not _newer(src, binary):
        return True
    if shutil.which("gcc") is None:
        log.warn(
            "gcc missing: bashcov-sup not built; Bash profiling stays off until setup runs with a compiler"
        )
        return True
    os.makedirs(os.path.dirname(binary), exist_ok=True)
    if _run(["gcc", "-O2", "-Wall", "-o", binary, src]) == 0 and _run([binary, "--", "true"]) == 0:
        log.info("built bashcov-sup -> %s" % binary)
    else:
        log.warn("bashcov-sup build failed; Bash profiling stays off")
        with contextlib.suppress(OSError):
            os.remove(binary)
    return True


def _newer(one: str, two: str) -> bool:
    """`[[ one -nt two ]]`: true when `one` is newer, or exists while `two` does not."""
    try:
        first = os.stat(one).st_mtime_ns
    except OSError:
        return False
    try:
        second = os.stat(two).st_mtime_ns
    except OSError:
        return True
    return first > second


def ensure_host_tools() -> bool:
    """`ensure_host_tools`, `.ci/lib/local-common.sh:557`."""
    missing = [tool for tool in ("jq", "zstd", "curl", "git") if shutil.which(tool) is None]
    if shutil.which("cc") is None and shutil.which("gcc") is None:
        missing.append("build-essential")
    if not missing:
        return True
    joined = " ".join(missing)
    if _uname("-s") != "Linux" or shutil.which("apt-get") is None:
        log.error("Missing required tools: %s" % joined)
        log.info("Install them with your package manager and re-run")
        return False
    log.step("Installing host tools: %s" % joined)
    if (
        _run(["sudo", "apt-get", "update", "-qq"]) != 0
        or _run(["sudo", "apt-get", "install", "-y", "-qq", *missing]) != 0
    ):
        log.error("Failed to install: %s" % joined)
        return False
    return True


# `printf %q`'s backslash set, measured against bash 5.3 over every printable ASCII byte; `#` and `~` are quoted only as the FIRST character.
_Q_ALWAYS = set(" !\"$&'()*,;<>?[\\]^`{|}")
_Q_LEADING = set("#~")
_Q_NAMED = {7: "\\a", 8: "\\b", 9: "\\t", 10: "\\n", 11: "\\v", 12: "\\f", 13: "\\r", 27: "\\E"}


def _utf8_locale() -> bool:
    """Whether bash's `%q` would treat a byte above 0x7f as printable: the first of LC_ALL, LC_CTYPE, LANG that is set decides."""
    for value in (
        os.environ.get("LC_ALL", ""),
        os.environ.get("LC_CTYPE", ""),
        os.environ.get("LANG", ""),
    ):
        if value:
            return "utf-8" in value.lower() or "utf8" in value.lower()
    return False


def bash_q(text: str) -> str:
    """bash's `printf %q`, for the argument shapes a command line carries. Measured, not read from a manual.

    Empty is `''`. A string with a control byte (or, outside a UTF-8 locale, a byte above 0x7f) takes the `$'...'` form, with bash's named escapes, `\\'` and `\\\\`, and three-digit octal for the rest. Anything else is backslash-quoted character by character.
    """
    if text == "":
        return "''"
    utf8 = _utf8_locale()
    raw = text.encode("utf-8", "surrogateescape")
    needs_ansi = any(b < 0x20 or b == 0x7F for b in raw) or (
        not utf8 and any(b >= 0x80 for b in raw)
    )
    if needs_ansi:
        out = []
        if utf8:
            for char in text:
                code = ord(char)
                if code in _Q_NAMED:
                    out.append(_Q_NAMED[code])
                elif char in ("'", "\\"):
                    out.append("\\" + char)
                elif code < 0x20 or code == 0x7F:
                    out.append("\\%03o" % code)
                else:
                    out.append(char)
        else:
            for byte in raw:
                if byte in _Q_NAMED:
                    out.append(_Q_NAMED[byte])
                elif byte in (0x27, 0x5C):
                    out.append("\\" + chr(byte))
                elif byte < 0x20 or byte >= 0x7F:
                    out.append("\\%03o" % byte)
                else:
                    out.append(chr(byte))
        return "$'" + "".join(out) + "'"
    out = []
    for index, char in enumerate(text):
        if char in _Q_ALWAYS or (index == 0 and char in _Q_LEADING):
            out.append("\\" + char)
        else:
            out.append(char)
    return "".join(out)


def _required(name: str, value: str | None) -> str:
    """`$NAME` under `set -u`: the value, or bash's unbound-variable death (its location prefix is not reproducible and the drivers strip it). The caller reads the variable itself, by its literal name, so every environment read in this module stays declarable."""
    if value is None:
        sys.stderr.write("%s: unbound variable\n" % name)
        raise LocalCommonError("%s is unset under set -u" % name, code=1)
    return value


def _docker_group_members() -> str | None:
    """`getent group docker | cut -d: -f4`, or None where `getent group docker` fails."""
    proc = _capture(["getent", "group", "docker"], quiet_err=True)
    if proc.returncode != 0:
        return None
    first = _subst(proc.stdout).split("\n")
    return "\n".join(
        [*line.split(":"), "", "", "", ""][3] if ":" in line else line for line in first
    )


def reexec_with_docker_group(args: list[str]) -> bool:
    """`reexec_with_docker_group`, `.ci/lib/local-common.sh:600`. Returns True where the twin returns 0; on success it never returns at all, because the twin `exec`s."""
    if os.environ.get("REDIACC_DOCKER_GROUP_REEXEC"):
        return True
    if _run(["docker", "version"], quiet_out=True, quiet_err=True) == 0:
        return True
    if shutil.which("docker") is None or shutil.which("sg") is None:
        return True
    if _run(["getent", "group", "docker"], quiet_out=True, quiet_err=True) != 0:
        return True
    members = _docker_group_members() or ""
    if ",%s," % _required("USER", os.environ.get("USER")) not in ",%s," % members:
        return True
    if _run(["sg", "docker", "-c", "docker version"], quiet_out=True, quiet_err=True) != 0:
        return True
    log.info("Applying your docker group membership to this run (no logout needed)")
    os.environ["REDIACC_DOCKER_GROUP_REEXEC"] = "1"
    command = "".join(
        bash_q(word) + " "
        for word in [_required("SCRIPT_ENTRYPOINT", os.environ.get("SCRIPT_ENTRYPOINT")), *args]
    )
    _flush()
    os.execvp("sg", ["sg", "docker", "-c", command])  # noqa: S606 -- forwarding exec, same shape as the twin's
    return True  # pragma: no cover -- execvp does not return


def ensure_docker_installed(env: dict[str, str] | None = None) -> bool:
    """`ensure_docker_installed`, `.ci/lib/local-common.sh:639`."""
    root = local_root_dir(env)
    if _run(["docker", "version"], quiet_out=True, quiet_err=True) == 0:
        version = _subst(_capture(["docker", "--version"], quiet_err=True).stdout)
        log.debug("Docker present and usable: %s" % version)
        return True
    if (
        shutil.which("docker") is not None
        and _run(["sudo", "docker", "version"], quiet_out=True, quiet_err=True) == 0
    ):
        log.warn(
            "Docker is installed but not usable as %s (group membership not active in this shell)"
            % _required("USER", os.environ.get("USER"))
        )
        ensure_docker_group()
        return True
    if _uname("-s") != "Linux":
        log.error("Automatic Docker installation is Linux-only")
        log.info("Install Docker Desktop, then re-run")
        return False
    log.step("Installing Docker via renet's installer (official docker.com repository)")
    if not ensure_host_tools():
        return False
    if not ensure_go_installed(env):
        return False
    if not ensure_renet_built(env):
        return False
    renet = os.path.join(root, "private", "renet", "bin", "renet")
    if not (os.path.isfile(renet) and os.access(renet, os.X_OK)):
        log.error("renet was built but %s is not executable" % renet)
        return False
    if _run(["sudo", renet, "install-docker", "--source=docker-repo"]) != 0:
        log.error("renet install-docker failed")
        return False
    ensure_docker_group()
    with contextlib.suppress(OSError):
        os.remove(os.path.join(root, ".ci", "cache", "build-renet.stamp"))
    log.info("Cleared the renet build stamp so assets get embedded on the next build")
    return True


def ensure_docker_group() -> bool:
    """`_ensure_docker_group`, `.ci/lib/local-common.sh:691`. Always True, as the twin always returns 0."""
    if _run(["getent", "group", "docker"], quiet_out=True, quiet_err=True) != 0:
        log.warn("No docker group exists; skipping group membership")
        return True
    user = _required("USER", os.environ.get("USER"))
    members = _docker_group_members() or ""
    if ",%s," % user in ",%s," % members:
        if _run(["docker", "version"], quiet_out=True, quiet_err=True) != 0:
            log.info(
                "Group membership is not active in this shell; ./run.sh re-execs itself under it automatically."
            )
            log.info("New login shells get it without help.")
        return True
    log.step("Adding %s to the docker group" % user)
    if _run(["sudo", "usermod", "-aG", "docker", user]) != 0:
        log.warn("usermod failed; you will need sudo for docker commands")
        return True
    log.info(
        "Added. ./run.sh applies it to this run automatically (via sg); new shells get it on login."
    )
    return True


# `_renet_source_hash`'s prunes and names, `.ci/lib/local-common.sh:719-735`.
RENET_PRUNE = ("./bin", "./build", "./pkg/embed/assets")
RENET_NAMES = ("*.go", "*.c", "*.h", "go.mod", "go.sum", "build.sh", "docker-compose.yml")


def renet_source_hash(renet_dir: str) -> str | None:
    """`_renet_source_hash`, `.ci/lib/local-common.sh:719`. The digest line, or None where `cd` fails.

    `find .` from inside the directory, so every name starts `./`; `-path` prunes are exact paths here, not globs. `LC_ALL=C sort -z` is a byte sort. `xargs -0 sha256sum` over no names at all still runs the tool once on its own empty stdin (reproduced behaviour 1).
    """
    failure = cd_error(renet_dir)
    if failure is not None:
        sys.stderr.write(failure + "\n")
        return None
    names: list[str] = []
    stack = ["."]
    while stack:
        current = stack.pop()
        if current in RENET_PRUNE:
            continue
        absolute = os.path.join(renet_dir, current)
        try:
            status = os.lstat(absolute)
        except OSError:
            continue
        if stat.S_ISDIR(status.st_mode):
            try:
                children = os.listdir(absolute)
            except OSError:
                continue
            stack.extend(join_under(current, child) for child in children)
        elif stat.S_ISREG(status.st_mode):
            base = os.path.basename(current)
            if any(fnmatch.fnmatchcase(base, glob) for glob in RENET_NAMES):
                names.append(current)
    ordered = sorted(names, key=os.fsencode)
    stream = sha256_lines(renet_dir, ordered)
    return hashlib.sha256(stream.encode("utf-8", "surrogateescape")).hexdigest() + "\n"


def renet_artifact_fp(path: str) -> str:
    """`_renet_artifact_fp`, `.ci/lib/local-common.sh:755`: `size:mtime` in whole seconds, empty when absent."""
    try:
        status = os.stat(path)
    except OSError:
        return ""
    return "%d:%d" % (status.st_size, int(status.st_mtime))


def ensure_renet_built(env: dict[str, str] | None = None) -> bool:
    """`ensure_renet_built`, `.ci/lib/local-common.sh:759`."""
    environ = os.environ if env is None else env
    root = local_root_dir(env)
    renet_dir = os.path.join(root, "private", "renet")
    renet_bin = os.path.join(renet_dir, "bin", "renet")
    system = _uname("-s")
    if system.startswith(("MINGW", "MSYS", "CYGWIN")):
        renet_bin = os.path.join(renet_dir, "bin", "renet.exe")

    check_go_installed()

    stamp = os.path.join(root, ".ci", "cache", "build-renet.stamp")
    license_mode = "enforce" if environ.get("RDC_RENET_LICENSE", "0") == "1" else "nolicense"
    account_key = environ.get("ACCOUNT_ED25519_PUBLIC_KEY", "")
    # The public-key cache `./run.sh setup` writes from Bitwarden, never private/account/.env (PLAN-account-env-to-bws T15).
    key_cache = os.path.join(renet_dir, "..", "account", ".cache", "public-keys.env")
    if not account_key and os.path.isfile(key_cache):
        text = pathlib.Path(key_cache).read_text(encoding="utf-8", errors="surrogateescape")
        hits = [
            line[len("ACCOUNT_ED25519_PUBLIC_KEY=") :]
            for line in text.split("\n")
            if line.startswith("ACCOUNT_ED25519_PUBLIC_KEY=")
        ]
        account_key = _subst("\n".join(hits).replace("\r", ""))

    # `if ! { _src_hash="$(_git_tree_fingerprint ...)" && [[ -n ... ]]; }` is an `if` CONDITION, so errexit is suppressed inside it.
    fingerprint = git_tree_fingerprint(renet_dir, ["."], env, errexit=False)
    source = _subst(fingerprint) if fingerprint is not None else ""
    if fingerprint is None or not source:
        computed = renet_source_hash(renet_dir)
        if computed is None:
            raise LocalCommonError("cd %s failed" % renet_dir, code=1)
        source = _subst(computed)

    current = _hex_of(
        ("src=%s\nlicense=%s\nkey=%s\n" % (source, license_mode, account_key)).encode(
            "utf-8", "surrogateescape"
        )
    )
    saved_stamp = _subst(read_stamp_hash(stamp))
    saved_lines = saved_stamp.split("\n")
    saved = saved_lines[0]
    saved_bin = "\n".join(line[len("bin=") :] for line in saved_lines if line.startswith("bin="))

    if (
        os.path.isfile(renet_bin)
        and current
        and saved == current
        and saved_bin
        and saved_bin == renet_artifact_fp(renet_bin)
    ):
        log.debug("Renet binary is up-to-date (stamp matched)")
        return True

    if os.path.isfile(renet_bin):
        log.step("Renet sources changed, rebuilding...")
    else:
        log.step("Building renet (first time, requires Docker for asset extraction)...")

    if _run(["./build.sh", "dev"], cwd=renet_dir) != 0:
        log.error("renet build failed (see the output above)")
        return False
    if not os.path.isfile(renet_bin):
        log.error("Renet build failed: binary not found at %s" % renet_bin)
        raise LocalCommonError("no renet binary", code=1)

    if _uname("-s") != "Linux":
        key_flags = ""
        if account_key:
            key_flags = (
                "-X github.com/rediacc/renet/pkg/license/keys.ProductionPublicKey=%s" % account_key
            )
        described = (
            _capture(["git", "describe", "--tags", "--always"], quiet_err=True, cwd=root)
            if os.path.isdir(root)
            else None
        )
        tag = (
            _subst(described.stdout)
            if described is not None and described.returncode == 0
            else "dev"
        )
        version = "%s-dev" % tag
        for arch in ("amd64", "arm64"):
            log.step("Cross-compiling renet for linux/%s (remote provisioning)..." % arch)
            _must(
                [
                    "go",
                    "build",
                    "-ldflags=-s -w -X main.Version=%s %s" % (version, key_flags),
                    "-o",
                    "bin/renet-linux-%s" % arch,
                    "./cmd/renet",
                ],
                cwd=renet_dir,
                env={**os.environ, "CGO_ENABLED": "0", "GOOS": "linux", "GOARCH": arch},
            )

    write_stamp_hash(stamp, "%s\nbin=%s" % (current, renet_artifact_fp(renet_bin)))
    log.info("Renet built successfully")
    return True


# --------------------------------------------------------------------------- the gate lane ---------------------------------------------------------------------------
#
# The twin's three `gate_lane_*` functions source `.ci/lib/devbox.sh` on demand and call its functions; here they call `core.devbox.Devbox`, the port of that file, so the devbox half of the answer is the same differentially proved code either way. All three log through the Devbox's own `log`, because that is `common.sh`'s colour rule (decided once from the stderr tty and `NO_COLOR`), which is the rule the twin's `log_*` use.


def _devbox():
    """One `Devbox` per top-level call, over this process's environment and binary streams."""
    _flush()
    return devbox, devbox.Devbox()


def gate_lane_decide() -> str:
    """`gate_lane_decide`, `.ci/lib/local-common.sh:904`: `host` or `devbox`, printed WITHOUT a newline by the twin.

    Four rules in order: inside the container is always `host`; `REDIACC_LANE` wins when it is `host` or `devbox`; the sticky `gate_lane=` in `.devbox-state`; otherwise `devbox` exactly when its container is running. The state read and the running probe both discard stderr and run as CONDITIONS, so neither can end the process.
    """
    if os.environ.get("REDIACC_IN_DEVBOX"):
        return "host"
    lane = os.environ.get("REDIACC_LANE", "")
    if lane in ("host", "devbox"):
        return lane
    module, box = _devbox()
    status, sticky = box.sub(box.state_get, "gate_lane", err=module.NULL)
    if status == 0 and sticky:
        return sticky
    with box.redirected(err=module.NULL):
        running = box.cond(box.container_running)
    return "devbox" if running == 0 else "host"


def gate_lane_should_route() -> int:
    """`gate_lane_should_route`, `.ci/lib/local-common.sh:950`. 0 route, 1 stay on the host, 2 refuse: the devbox is unusable."""
    if gate_lane_decide() != "devbox":
        return 1
    module, box = _devbox()
    with box.redirected(err=module.NULL):
        running = box.cond(box.container_running)
    if running != 0:
        box.log("warn", "gate lane is 'devbox' but no container is running; staying on the host")
        box.log("info", "Start it with ./run.sh devbox up, or pin the lane with REDIACC_LANE=host")
        return 1
    # `devbox_mount_ok && devbox_identity_ok || { ...; return 2; }`: both run as conditions, and the second only when the first passed.
    if box.cond(box.mount_ok) != 0 or box.cond(box.identity_ok) != 0:
        box.log(
            "error", "refusing to route gates into an unusable devbox (see ./run.sh devbox doctor)"
        )
        return 2
    return 0


def gate_lane_run(args: list[str]) -> int:
    """`gate_lane_run`, `.ci/lib/local-common.sh:975`: the routed command's own status, nothing layered on it.

    `devbox_exec "./run.sh $*"` passes ONE argument, the words joined by single spaces, so the devbox side sees shell syntax rather than re-quoted argv: an argument carrying a space splits inside the container. Reproduced.
    """
    _, box = _devbox()
    box.log("info", "lane: devbox (matches CI; REDIACC_LANE=host to opt out)")
    return box.invoke("devbox_exec", ["./run.sh %s" % " ".join(args)])


# --------------------------------------------------------------------------- argv ---------------------------------------------------------------------------

USAGE = """rediacc_ci.core.local_common -- .ci/lib/local-common.sh, every function

  tree-hash <root> <path>...         compute_tree_hash
  full-hash <root> <path>...         compute_hash_for_package_dirs (no git fast path)
  git-fp <root> <path>...            _git_tree_fingerprint
  read-stamp <file>                  read_stamp_hash
  write-stamp <file> <value>         write_stamp_hash
  version-gte <a> <b>                _version_gte (exit 0 when a >= b)
  has-npm-script <name>              has_npm_script
  cpu-features-gypi <node_modules>   ensure_cpu_features_gypi
  ensure-deps                        ensure_deps
  ensure-packages-built              ensure_packages_built
  ensure-cli-built                   ensure_cli_built
  prompt-continue [message]          prompt_continue (exit 0 on y/Y)
  open-browser <url>                 open_browser
  run-npm-script <name> [desc]       run_npm_script
  check-node-version [min]           check_node_version
  check-go-installed                 check_go_installed
  ensure-go-installed                ensure_go_installed
  ensure-bashcov-sup                 ensure_bashcov_sup
  ensure-host-tools                  ensure_host_tools
  reexec-docker-group [args...]      reexec_with_docker_group (reads SCRIPT_ENTRYPOINT)
  ensure-docker-installed            ensure_docker_installed
  ensure-docker-group                _ensure_docker_group
  renet-source-hash <dir>            _renet_source_hash
  renet-artifact-fp <path>           _renet_artifact_fp
  ensure-renet-built                 ensure_renet_built
  lane-decide                        gate_lane_decide
  lane-should-route                  gate_lane_should_route (0 route, 1 host, 2 refuse)
  lane-run <args...>                 gate_lane_run

Each verb is the twin's function of the same name: its streams, its files and
its exit status, an errexit death included."""

# verb -> (callable taking the argument list, returning the exit status)
_BOOL_VERBS = {
    "cpu-features-gypi": lambda rest: ensure_cpu_features_gypi(rest[0]),
    "ensure-deps": lambda _rest: ensure_deps(),
    "ensure-packages-built": lambda _rest: ensure_packages_built(),
    "ensure-cli-built": lambda _rest: ensure_cli_built(),
    "prompt-continue": lambda rest: prompt_continue(rest[0] if rest else "Continue?"),
    "check-node-version": lambda rest: check_node_version(
        rest[0] if rest and rest[0] else "18.0.0"
    ),
    "ensure-go-installed": lambda _rest: ensure_go_installed(),
    "ensure-bashcov-sup": lambda _rest: ensure_bashcov_sup(),
    "ensure-host-tools": lambda _rest: ensure_host_tools(),
    "reexec-docker-group": reexec_with_docker_group,
    "ensure-docker-installed": lambda _rest: ensure_docker_installed(),
    "ensure-docker-group": lambda _rest: ensure_docker_group(),
    "ensure-renet-built": lambda _rest: ensure_renet_built(),
}


def _dispatch_actions(verb: str, rest: list[str]) -> int | None:
    """The machine-mutating verbs. None when `verb` is not one of them."""
    if verb in _BOOL_VERBS:
        return 0 if _BOOL_VERBS[verb](rest) else 1
    if verb == "open-browser" and rest:
        open_browser(rest[0])
        return 0
    if verb == "run-npm-script" and rest:
        run_npm_script(rest[0], rest[1] if len(rest) > 1 and rest[1] else None)
        return 0
    if verb == "check-go-installed":
        check_go_installed()
        return 0
    if verb == "lane-decide":
        sys.stdout.write(gate_lane_decide())
        return 0
    if verb == "lane-should-route":
        return gate_lane_should_route()
    if verb == "lane-run":
        return gate_lane_run(rest)
    if verb == "renet-source-hash" and rest:
        digest = renet_source_hash(rest[0])
        if digest is None:
            return 1
        sys.stdout.write(digest)
        return 0
    if verb == "renet-artifact-fp" and rest:
        fingerprint = renet_artifact_fp(rest[0])
        if fingerprint:
            sys.stdout.write(fingerprint + "\n")
        return 0
    return None


def main(argv: list[str]) -> int:
    """The verbs whose whole answer is stdout plus an exit code."""
    if not argv:
        print(USAGE)
        return 2
    if argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    verb, rest = argv[0], argv[1:]
    try:
        if verb == "tree-hash" and rest:
            outcome = compute_tree_hash(rest[0], rest[1:])
        elif verb == "full-hash" and rest:
            outcome = compute_hash_for_package_dirs(rest[0], rest[1:])
        elif verb == "git-fp" and rest:
            fingerprint = git_tree_fingerprint(rest[0], rest[1:])
            if fingerprint is None:
                return 1
            outcome = Outcome(fingerprint, 0)
        elif verb == "read-stamp" and len(rest) == 1:
            outcome = Outcome(read_stamp_hash(rest[0]), 0)
        elif verb == "write-stamp" and len(rest) == 2:
            write_stamp_hash(rest[0], rest[1])
            outcome = Outcome("", 0)
        elif verb == "version-gte" and len(rest) == 2:
            return 0 if version_gte(rest[0], rest[1]) else 1
        elif verb == "has-npm-script" and len(rest) == 1:
            return 0 if has_npm_script(rest[0]) else 1
        elif (status := _dispatch_actions(verb, rest)) is not None:
            return status
        else:
            log.error("Unknown local-common command: %s" % verb)
            return 2
    except LocalCommonError as exc:
        return exc.code
    sys.stdout.write(outcome.out)
    return outcome.code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
