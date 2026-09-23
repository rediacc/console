"""The PURE-COMPUTATION half of `.ci/lib/local-common.sh`, ported function for function.

PORTED FROM `.ci/lib/local-common.sh` (1008 lines, 30 functions).
The twin still exists, is untouched by this file, and is still sourced at `rdc.sh:18`, `.ci/legacy/run-legacy.sh:47`, `.ci/media/media-entry.sh:50`, `.ci/rediacc_ci/native.py:137` (inside a `bash -c`) and `.ci/scripts/test/gates/test-run-sh.sh:116`. Those five are the real `source` sites, found anchored rather than by bare string match; nothing is cut over here.
This is a pre-cutover port on the same sequencing every other lib in this campaign used, and `.ci/rediacc_ci/core/account.py` is the worked precedent from the same session: its twin `.ci/lib/account.sh` is still sourced at `.ci/legacy/run-legacy.sh:405` while the port carries a K=5 ledger.

--------------------------------------------------------------------------
WHAT IS HERE AND WHAT IS DELIBERATELY ABSENT
--------------------------------------------------------------------------
NINE FUNCTIONS ARE PORTED, and they are the ones whose whole answer is computation over a local file or a local git read: `_sha256sum` (`:37`), `_sed_i` (`:46`), `compute_hash_for_package_dirs` (`:58`), `_git_tree_fingerprint` (`:92`), `compute_tree_hash` (`:137`), `read_stamp_hash` (`:148`), `write_stamp_hash` (`:156`), `_version_gte` (`:545`) and `has_npm_script` (`:401`).

TWENTY-ONE ARE NOT, and saying so here rather than leaving an absence is the point. THERE IS NO PYTHON FUNCTION BELOW FOR ANY OF THEM:

  installers and builders, which mutate the machine     `ensure_cpu_features_gypi:178` (compiles), `ensure_deps:203` (`npm install`), `ensure_packages_built:308`, `ensure_cli_built:333`, `ensure_go_installed:458` (downloads a tarball, `sudo tar` into `/usr/local`), `ensure_bashcov_sup:566` (`gcc`), `ensure_host_tools:587` (`sudo apt-get install`), `ensure_docker_installed:669`,
  `_ensure_docker_group:721` (`sudo usermod`), `ensure_renet_built:789` (`go build`), `run_npm_script:408`.
  interactive or session-altering                       `prompt_continue:371` reads stdin, `open_browser:381` launches a browser, `reexec_with_docker_group:630` calls `exec sg docker`.
  DEVBOX-COUPLED, and out of scope by ruling            `gate_lane_decide:934`, `gate_lane_should_route:980` and `gate_lane_run:1005` all source `.ci/lib/devbox.sh` and call `devbox_state_get` / `devbox_container_running` / `devbox_mount_ok` / `devbox_identity_ok` / `devbox_exec`. `.ci/lib/devbox.sh` is not read, not modified and not ported by this slice.

--------------------------------------------------------------------------
FOUR FUNCTIONS THAT ARE DETERMINISTIC AND ARE STILL NOT PORTED HERE
--------------------------------------------------------------------------
The brief this slice was written to named nine functions. A function-by-function read of all thirty found FOUR MORE that are equally pure, and each is left out for a stated reason rather than by oversight:

  `check_node_version:418`   ALREADY PORTED, at `rediacc_ci/core/account.py:143`, because `account.sh` calls it and does not define it and a module cannot borrow a function from its importer. A second copy here would be two Python implementations of one bash function, which is the duplicate-instrument risk this campaign's invariant 5 exists to prevent.
                             When `account.sh` is cut over, that definition should MOVE here and `account.py` should import it.
  `check_go_installed:439`   Pure (`command -v go`), but it calls `exit 1` rather than returning, so its only real behaviour is killing the sourcing shell. It has no caller outside `ensure_renet_built`, which is not portable.
  `_renet_source_hash:749`   Pure, and the same `find | sort -z | xargs sha256sum` shape as `compute_hash_for_package_dirs`, with renet-specific prunes.
  `_renet_artifact_fp:785`   Pure (`stat -c '%s:%Y'` with a BSD fallback).
                             Both exist solely to serve `ensure_renet_built`, which is not portable, so porting them would add differential surface for a caller that cannot move.

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

import fnmatch
import hashlib
import os
import pathlib
import platform
import shutil
import stat
import subprocess
import sys

from rediacc_ci import log, paths

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


# --------------------------------------------------------------------------- argv ---------------------------------------------------------------------------

USAGE = """rediacc_ci.core.local_common -- the pure half of .ci/lib/local-common.sh

  tree-hash <root> <path>...     compute_tree_hash
  full-hash <root> <path>...     compute_hash_for_package_dirs (no git fast path)
  git-fp <root> <path>...        _git_tree_fingerprint
  read-stamp <file>              read_stamp_hash
  write-stamp <file> <value>     write_stamp_hash
  version-gte <a> <b>            _version_gte (exit 0 when a >= b)
  has-npm-script <name>          has_npm_script

The ensure_*, gate_lane_*, prompt_continue, open_browser and reexec verbs are
NOT here: they install software, start containers or read stdin. See the module
docstring for the full list and why each one stayed in bash."""


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
        else:
            log.error("Unknown local-common command: %s" % verb)
            return 2
    except LocalCommonError as exc:
        return exc.code
    sys.stdout.write(outcome.out)
    return outcome.code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
