#!/usr/bin/env python3
"""Both sides of the `core.local_common` port differential, in one file.

WHAT THIS IS FOR. `scripts/lib/shadow-gate.ts` compares two commands and rules on whether a port kept the verdict. It needs each side to PRINT what it observed, because the thing being compared is a finding multiset and not a return value. This module is the printer, and it can print either side:

    PYTHONPATH=.ci python3 -m rediacc_ci.core.local_common_shadow_driver --side old --twin .ci/lib/local-common.sh --port .ci/rediacc_ci/core/local_common.py <scenario>
        drives the BASH: sources `.ci/lib/local-common.sh` through the same prelude `.ci/legacy/run-legacy.sh` uses, and calls the twin's own functions.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.local_common_shadow_driver --side new --twin .ci/lib/local-common.sh --port .ci/rediacc_ci/core/local_common.py <scenario>
        drives the PYTHON: `rediacc_ci.core.local_common`.

RUN AS A MODULE AND NEVER BY PATH, which is not a style choice. A by-path invocation puts `.ci/rediacc_ci/core` on `sys.path[0]` and nothing on it can find `rediacc_ci`, so the file would have to open with a hand-written `sys.path.insert`. `test_canonical_sys_path_hop.py` refuses exactly that, and `PYTHONPATH=.ci` plus `-m` removes the need rather than baselining it.

WHY THIS IS A SECOND DRIVER AND NOT A SCENARIO INSIDE `core/shadow_driver.py`. That file is the `core.account` differential and its ledger rows name it; a pair is one twin against one port, and folding a second twin into it would make `dead_python.py`'s shadow route admit both ports off either ledger.
One file per pair, on the `rediacc_ci/dev`, `rediacc_ci/setup` and `rediacc_ci/docker` precedent.

ONE FILE AND NOT TWO, for the reason those files record: `.ci/rediacc_ci/quality/dead_python.py:280` admits a pre-cutover port as alive only when it is named in a `.ci/shadow/*.jsonl` record, so a separate old-side module would be reported dead the day it landed. `--twin` and `--port` carry the two paths for the same reason, and BOTH are checked to exist before anything runs.

-----------------------------------------------------------------------------
THE SANDBOX, AND WHY PYTHON BUILDS THE FIXTURES FOR BOTH SIDES
-----------------------------------------------------------------------------
Every function in this slice reads or writes a real path, and two of the scenarios MUTATE what they read (`sed` edits files in place, `stamp` writes them). A differential pointing both sides at one directory would have the first side leave the tree in the state that makes the second take a different branch.

So each side builds its OWN temporary `CONSOLE_ROOT_DIR`: a real directory holding the fixtures, with `.devcontainer`, `scripts`, `.ci/config`, `.ci/scripts`, `.ci/lib` and `.ci/rediacc_ci` SYMLINKED to the checkout this driver was invoked from.
Symlinks rather than copies because `constants.sh` derives `CI_LIB_DIR` from `CONSOLE_ROOT_DIR`, and because the code under comparison must be the TRACKED code, which is what the recorded tree id claims.
`cd "$(dirname "${BASH_SOURCE[0]}")" && pwd` is LOGICAL in bash, so the twin's own `LOCAL_ROOT_DIR` resolves to the sandbox rather than to the real checkout behind the symlink. That is load-bearing for the `npm-script` scenario, and the derivation is emitted as an observation rather than assumed.

THE FIXTURES ARE BUILT IN PYTHON FOR BOTH SIDES, which is the one place this driver departs from `core/shadow_driver.py`'s shape. That driver writes its fixtures inside the bash scenario body and again in Python, which works when a fixture is three `printf`s.
Here the `git-fp` fixture is a real git repository with a committed history, a modified file, a deleted file, a staged file and an untracked file; two hand-written builders would be two things that can drift, and a fingerprint differing because the two repositories differ is a mismatch that says nothing about the port. `build_fixtures()` runs before either side is dispatched.

The temporary directory differs between the two sides, so every observation is normalised: the sandbox root becomes `<work>` and `$HOME` becomes `<home>` before anything is printed.

-----------------------------------------------------------------------------
THE SIX SCENARIOS, AND WHAT EACH ONE WOULD CATCH
-----------------------------------------------------------------------------
  hash        `_sha256sum` over files, over a name containing a SPACE and one containing a BACKSLASH (which the tool escapes, changing the bytes the outer hash sees), and over stdin; then `compute_hash_for_package_dirs` over a tree carrying every one of the six prune rules, a symlink, an empty directory, uppercase and underscore names that a locale sort would order differently from a byte sort, two start points, a trailing-slash start point, a MISSING start point (a real hash AND exit 1), an EMPTY result set (the `xargs` special case) and an unusable root. The control is the non-empty tree: without it every case would be a refusal, and two identical refusals prove nothing.
  git-fp      `_git_tree_fingerprint` against a real git repository the driver builds: a clean path, a modified file, a deleted file, a staged file, an untracked file, a start point absent from HEAD (`no-tree:`), `.`, a directory that is not a work tree, and a root that does not exist.
              Then the ERREXIT case in both directions: one repository whose sorted `changed` list ENDS in a deleted file, where the twin dies silently inside its own assignment, and one where the deleted file sorts first, where it does not.
  tree-hash   `compute_tree_hash` taking its git branch and its full-walk fallback, which are different functions reached from one name.
  stamp       `read_stamp_hash` and `write_stamp_hash`: absent, empty, no trailing newline, a multi-line value (the shape `ensure_renet_built` writes), a nested directory that does not exist yet, a relative path whose `dirname` is `.`, and a round trip showing the newline the writer adds and the reader keeps.
  version     `_version_gte` over 72 ordered pairs, including `~`, leading zeros, `rc`/`beta` suffixes, `1.9` against `1.10`, bare dots and empty strings. This is the scenario that proves the transcribed `filevercmp` rather than a plausible-looking version split.
  npm-script  `has_npm_script` on a fixture `package.json`: a plain script, one whose name carries a colon, an absent one, a PREFIX of a real one, and the two false positives the twin really has (a dependency name, and `name` itself).
              Then the missing-file case, which exits 2 rather than 1. `LOCAL_ROOT_DIR`, `LOCAL_CI_DIR` and `LOCAL_LIB_DIR` are emitted on both sides, so the two independent derivations are compared rather than one being fed the other's.
  sed         `_sed_i` on one file, on two files at once, with a pattern that matches nothing, on a file with no trailing newline, and on a file that does not exist. Every touched file is dumped afterwards, so a port that wrote the right exit code over the wrong bytes is caught.

WHAT IS NEVER DRIVEN HERE: `ensure_deps`, `ensure_packages_built`, `ensure_cli_built`, `ensure_cpu_features_gypi`, `ensure_go_installed`, `ensure_bashcov_sup`, `ensure_host_tools`, `ensure_docker_installed`, `_ensure_docker_group`, `ensure_renet_built`, `run_npm_script`, `prompt_continue`, `open_browser`, `reexec_with_docker_group`, `check_node_version`, `check_go_installed`, `_renet_source_hash`, `_renet_artifact_fp`, `gate_lane_decide`, `gate_lane_should_route` and `gate_lane_run`.
None of them is ported, and a ledger row is a claim of equivalence.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import log
from rediacc_ci.core import local_common

# The prefix `shadow-gate --finding-re '^obs '` is pointed at. Deliberately not a cross or a FAIL: those already mean "a finding" to the comparator's marker table, and an observation that AGREES is not a failure.
OBS = "obs"

EXIT_CANNOT_RUN = 77

# What the sandbox symlinks. `.devcontainer` carries the toolchain pins `constants.sh` refuses to load without; `scripts` and `.ci/scripts` because the prelude sources `toolchain.sh` and, through `local-common.sh`, `common.sh`.
SANDBOX_LINKS = (
    (".devcontainer",),
    ("scripts",),
    (".ci", "config"),
    (".ci", "scripts"),
    (".ci", "lib"),
    (".ci", "rediacc_ci"),
)

# The prelude `.ci/legacy/run-legacy.sh:41-47` runs before it dispatches anything, minus the per-verb libs. `local-common.sh` sources `common.sh` itself, which is where `log_error` and `log_debug` come from.
PRELUDE = r"""
set -euo pipefail
source "$W/.ci/config/constants.sh"
source "$W/.ci/scripts/lib/toolchain.sh"
source "$W/.ci/lib/local-common.sh"

norm() {
    local s="$1"
    s="${s//$W/<work>}"
    s="${s//$HOME/<home>}"
    printf '%s' "$s"
}

emit() { printf 'obs %s\n' "$(norm "$1")"; }

# `<file>: line <N>: cd: ...` names a line INSIDE the twin. The message is the twin's real behaviour and is compared; the file-and-line stamp in front of it is not reproducible by a port and is dropped on both sides. `[^ ]*` rather than `.*` so a message that itself contained the phrase could not eat the part being compared.
strip_loc() { printf '%s' "$1" | sed -E 's|^[^ ]*: line [0-9]+: ||'; }

# rc first, then stdout, then stderr, so the two sides cannot differ on ORDER for a reason that is the harness rather than the subject. The subshell keeps a twin function's `exit 1` from taking this driver down with it.
step() {
    local name="$1"
    shift
    local o e rc l
    o="$(mktemp)"
    e="$(mktemp)"
    # NOT `if ( set -e; "$@" ); then`, and that spelling cost a wrong measurement in the `core.account` differential before it was fixed. A command in an `if` CONDITION runs with errexit suppressed, and the suppression propagates into a subshell created there, so the inner `set -e` is INERT: the trap `docs/agent-reference/TRAPS.md` calls errexit-rearmed-in-a-tested-command.
    # It matters twice as much here, because `_git_tree_fingerprint` has a bare assignment whose whole behaviour depends on whether errexit is genuinely armed, which is exactly what one of these scenarios measures.
    set +e
    ( set -e; "$@" ) >"$o" 2>"$e"
    rc=$?
    set -e
    emit "rc $name=$rc"
    # `|| [[ -n "$l" ]]` IS NOT DECORATION. A bare `while IFS= read -r l` DROPS a final line
    # that has no trailing newline, because `read` returns non-zero at EOF without a
    # delimiter. `read_stamp_hash` over a stamp written by hand and `_sed_i` over a file with
    # no final newline both produce exactly that, and without this the BASH side under-reported
    # a line the twin really printed while the Python side reported it. Found by running it.
    while IFS= read -r l || [[ -n "$l" ]]; do emit "out $name| $l"; done <"$o"
    while IFS= read -r l || [[ -n "$l" ]]; do emit "err $name| $(strip_loc "$l")"; done <"$e"
    rm -f "$o" "$e"
}

dump() {
    local name="$1" path="$2" l
    if [[ ! -f "$path" ]]; then emit "file $name| <absent>"; return 0; fi
    while IFS= read -r l || [[ -n "$l" ]]; do emit "file $name| $l"; done <"$path"
}
"""

# The prefix `strip_loc` removes above, applied identically on the port side, where it is a
# no-op because nothing in Python emits a bash source location.
BASH_LOCATION_RE = re.compile(r"^[^ ]*: line [0-9]+: ")

# The fixture `package.json` the `npm-script` scenario reads. `zod` and `name` are here because they are the twin's two real false positives: the grep is over the whole file.
PACKAGE_JSON = """{
  "name": "shadow-probe",
  "private": true,
  "scripts": {
    "build": "echo build",
    "check:ci-thing": "echo thing",
    "test-e2e": "echo e2e"
  },
  "dependencies": {
    "zod": "^4.4.3"
  }
}
"""

# `has_npm_script` arguments. Every one is BRE-literal, which is what the port's refusal guarantees for the live corpus; the refusal itself is a pytest case rather than a scenario, because the twin does not refuse and a differential mismatch is the wrong way to record a difference the port makes ON PURPOSE.
NPM_SCRIPT_NAMES = (
    "build",
    "check:ci-thing",
    "test-e2e",
    "nosuch",
    "buil",
    "uild",
    "zod",
    "name",
    "private",
    "scripts",
)

# `_version_gte` pairs. Chosen for the cases a hand-rolled numeric split gets wrong: `~` sorts BEFORE the empty string, `1.9 < 1.10`, leading zeros collapse, an alphabetic suffix sorts before the bare version, and `sort` falls back to a byte compare when two strings tie under `-V`.
VERSION_PAIRS = (
    ("1.25.13", "1.25.13"),
    ("1.25.13", "1.25.0"),
    ("1.25.0", "1.25.13"),
    ("1.26.4", "1.25.13"),
    ("1.25", "1.25.13"),
    ("1.25.13", "1.25"),
    ("22.14.0", "18.0.0"),
    ("18.0.0", "22.14.0"),
    ("9.0.0", "10.0.0"),
    ("10.0.0", "9.0.0"),
    ("1.9", "1.10"),
    ("1.10", "1.9"),
    ("0.9", "0.10"),
    ("0.10", "0.9"),
    ("20.04", "20.4"),
    ("20.4", "20.04"),
    ("1.0", "1.00"),
    ("1.00", "1.0"),
    ("01.0", "1.0"),
    ("1.0", "01.0"),
    ("1.0.0", "1.0"),
    ("1.0", "1.0.0"),
    ("1.0.0-rc1", "1.0.0-rc2"),
    ("1.0.0-rc2", "1.0.0-rc1"),
    ("1.0.0rc1", "1.0.0"),
    ("1.0.0", "1.0.0rc1"),
    ("1.0.0beta", "1.0.0alpha"),
    ("1.0.0alpha", "1.0.0beta"),
    ("2.0~rc1", "2.0"),
    ("2.0", "2.0~rc1"),
    ("~", "1.0"),
    ("1.0", "~"),
    ("~1", "~"),
    ("", "1.0"),
    ("1.0", ""),
    ("", ""),
    ("0", "00"),
    ("00", "0"),
    ("0", ""),
    ("1.2.3.4", "1.2.3"),
    ("1.2.3", "1.2.3.4"),
    ("a", "b"),
    ("b", "a"),
    ("1a", "a1"),
    ("a1", "1a"),
    ("1.0.0.tar.gz", "1.0.0.tgz"),
    ("1.0.0.tgz", "1.0.0.tar.gz"),
    ("v1.0", "1.0"),
    ("1.0", "v1.0"),
    ("go1.25.13", "go1.25.0"),
    ("go1.25.0", "go1.25.13"),
    ("1.25.13-dev", "1.25.13"),
    ("1.25.13", "1.25.13-dev"),
    ("1.0-1", "1.0-2"),
    ("1.0-2", "1.0-1"),
    ("....", "."),
    (".", ".."),
    ("..", "."),
    (".1", "1"),
    ("1", ".1"),
    ("1_0", "1.0"),
    ("1.0", "1_0"),
    ("1+0", "1.0"),
    ("1.0", "1+0"),
    ("1.0.0", "1.0.0 "),
    ("1.0.0 ", "1.0.0"),
    ("A", "a"),
    ("a", "A"),
    ("1.0.0", "1.0.O"),
    ("1.0.O", "1.0.0"),
    ("2026.09.23", "2026.9.23"),
    ("2026.9.23", "2026.09.23"),
)


class RefusalError(RuntimeError):
    """The driver cannot run, so its silence would not be evidence."""


# --------------------------------------------------------------------------- the sandbox ---------------------------------------------------------------------------


def build_sandbox(repo: pathlib.Path) -> pathlib.Path:
    """One `CONSOLE_ROOT_DIR` for one side of one scenario."""
    for parts in SANDBOX_LINKS:
        source = repo.joinpath(*parts)
        if not source.exists():
            raise RefusalError(
                "the sandbox cannot be built: %s is missing from %s, so neither side would "
                "have the code under comparison" % ("/".join(parts), repo)
            )
    work = pathlib.Path(tempfile.mkdtemp(prefix="lc-shadow-"))
    for parts in SANDBOX_LINKS:
        target = work.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(repo.joinpath(*parts))
    return work


def sandbox_env(work: pathlib.Path) -> dict[str, str]:
    """The environment both sides run under, built the same way for each.

    `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` are `/dev/null` because `core.autocrlf`, `core.symlinks` or a `filter` in the operator's own config would change what `git hash-object` answers, and a fingerprint that depends on the machine's gitconfig is not a fingerprint of the tree.
    `GIT_CEILING_DIRECTORIES` stops the not-a-work-tree cases from discovering some repository above the temporary directory and answering a different question.
    """
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "CONSOLE_ROOT_DIR": str(work),
        "REDIACC_CI_ROOT": str(work),
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CEILING_DIRECTORIES": str(work.parent),
        "GIT_AUTHOR_NAME": "shadow",
        "GIT_AUTHOR_EMAIL": "shadow@example.invalid",
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
        "GIT_COMMITTER_NAME": "shadow",
        "GIT_COMMITTER_EMAIL": "shadow@example.invalid",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
    }


# --------------------------------------------------------------------------- the fixtures ---------------------------------------------------------------------------


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_hash_tree(work: pathlib.Path) -> None:
    """A tree exercising all six prune rules, a symlink, and byte-versus-locale ordering."""
    pkg = work / "pkg"
    write(pkg / "src" / "c.ts", "c\n")
    write(pkg / "src" / "A.ts", "A\n")
    write(pkg / "src" / "_under.ts", "_\n")
    write(pkg / "src" / "Z.ts", "Z\n")
    write(pkg / "src" / "a space.ts", "space\n")
    write(pkg / "README.md", "readme\n")
    # Every one of these must be invisible to the walk.
    write(pkg / "dist" / "a.js", "dist\n")
    write(pkg / "dist" / "sub" / "b.js", "dist-sub\n")
    write(pkg / "node_modules" / "x" / "d.js", "nm\n")
    write(pkg / "reports" / "r.json", "rep\n")
    write(pkg / "test-results" / "t.xml", "tr\n")
    write(pkg / "e.tsbuildinfo", "tsb\n")
    write(pkg / ".DS_Store", "ds\n")
    # A symlink to a real file: `-type f` is false for it, so it must NOT be hashed.
    (pkg / "src" / "link.ts").symlink_to("c.ts")
    write(work / "other" / "o.txt", "other\n")
    (work / "empty").mkdir(parents=True, exist_ok=True)
    write(work / "plain.txt", "plain\n")
    write(work / "second.txt", "second\n")
    write(work / "a space.txt", "spaced\n")
    write(work / "back\\slash.txt", "backslash\n")


def git_run(repo: pathlib.Path, args: list[str], env: dict[str, str]) -> None:
    proc = subprocess.run(
        ["git", *args], cwd=str(repo), env=env, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise RefusalError(
            "the git fixture could not be built: `git %s` exited %d: %s"
            % (" ".join(args), proc.returncode, proc.stderr.strip())
        )


def build_git_repo(
    repo: pathlib.Path, env: dict[str, str], deleted_sorts_last: bool = True
) -> None:
    """A real repository with one commit and then every kind of local change.

    `deleted_sorts_last` decides whether the sorted `changed` list ENDS in a path that is no longer on disk, which is the whole subject of reproduced behaviour 2 in the port: the twin's bare `existing=` assignment takes the while loop's last status, so a deleted file LAST kills it under armed errexit and a deleted file FIRST does not.
    """
    repo.mkdir(parents=True, exist_ok=True)
    write(repo / "src" / "kept.ts", "kept\n")
    write(repo / "src" / "modified.ts", "original\n")
    write(repo / "src" / "staged.ts", "staged-original\n")
    write(repo / "doc" / "readme.md", "doc\n")
    gone = "src/zz-gone.ts" if deleted_sorts_last else "src/00-gone.ts"
    write(repo / gone, "gone\n")
    git_run(repo, ["init", "-q", "-b", "main"], env)
    git_run(repo, ["add", "-A"], env)
    git_run(repo, ["commit", "-q", "-m", "fixture"], env)

    (repo / "src" / "modified.ts").write_text("changed\n", encoding="utf-8")
    (repo / gone).unlink()
    (repo / "src" / "staged.ts").write_text("staged-new\n", encoding="utf-8")
    git_run(repo, ["add", "src/staged.ts"], env)
    write(repo / "src" / "untracked.ts", "untracked\n")


def build_fixtures(work: pathlib.Path, scenario: str, env: dict[str, str]) -> None:
    """Every input both sides read, built ONCE in Python. See the header."""
    if scenario == "hash":
        build_hash_tree(work)
        return
    if scenario in ("git-fp", "tree-hash"):
        build_git_repo(work / "repo", env, deleted_sorts_last=True)
        build_git_repo(work / "repo-first", env, deleted_sorts_last=False)
        write(work / "notarepo" / "plain.txt", "plain\n")
        write(work / "notarepo" / "nested" / "deep.txt", "deep\n")
        return
    if scenario == "stamp":
        write(work / "stamps" / "empty.stamp", "")
        write(work / "stamps" / "bare.stamp", "no-trailing-newline")
        write(work / "stamps" / "two.stamp", "abc123\nbin=4096:1700000000\n")
        return
    if scenario == "version":
        write(work / "version-pairs.txt", "".join("%s|%s\n" % pair for pair in VERSION_PAIRS))
        return
    if scenario == "npm-script":
        write(work / "package.json", PACKAGE_JSON)
        write(work / "names.txt", "".join("%s\n" % name for name in NPM_SCRIPT_NAMES))
        return
    if scenario == "sed":
        write(work / "sed" / "one.txt", "alpha\nbeta\ngamma\n")
        write(work / "sed" / "two.txt", "alpha\ndelta\n")
        write(work / "sed" / "nonewline.txt", "alpha\nbeta")
        write(work / "sed" / "nomatch.txt", "zulu\n")
        return
    raise RefusalError("unknown scenario %r" % scenario)


# --------------------------------------------------------------------------- printing ---------------------------------------------------------------------------


def text_lines(text: str) -> list[str]:
    """The lines `while IFS= read -r` would see: none at all for empty text."""
    if text == "":
        return []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


class Printer:
    """The one emitter the new side goes through, matching the bash helpers above."""

    def __init__(self, work: pathlib.Path) -> None:
        self.work = str(work)
        self.home = os.environ.get("HOME", "/tmp")

    def norm(self, text: str) -> str:
        return text.replace(self.work, "<work>").replace(self.home, "<home>")

    def emit(self, text: str) -> None:
        print("%s %s" % (OBS, self.norm(text)))

    def step(self, name: str, rc: int, out: str, err: str) -> None:
        self.emit("rc %s=%d" % (name, rc))
        for line in text_lines(out):
            self.emit("out %s| %s" % (name, line))
        for line in text_lines(err):
            self.emit("err %s| %s" % (name, BASH_LOCATION_RE.sub("", line)))

    def dump(self, name: str, path: pathlib.Path) -> None:
        if not path.is_file():
            self.emit("file %s| <absent>" % name)
            return
        text = path.read_text(encoding="utf-8", errors="surrogateescape")
        for line in text_lines(text):
            self.emit("file %s| %s" % (name, line))


def call(printer: Printer, name: str, fn) -> int:
    """Run one port call with its two streams captured, and print the same shape.

    The return-value mapping is the twin's: an `Outcome` carries both channels, False is exit 1, True and None are exit 0, and a `LocalCommonError` carries the code the twin's `exit` would have used.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        log.reset(colour=False)
        try:
            result = fn()
        except local_common.LocalCommonError as exc:
            result = local_common.Outcome("", exc.code)
        if isinstance(result, local_common.Outcome):
            sys.stdout.write(result.out)
            rc = result.code
        elif result is False:
            rc = 1
        elif result is True or result is None:
            rc = 0
        elif isinstance(result, str):
            sys.stdout.write(result)
            rc = 0
        else:
            rc = int(result)
    log.reset(colour=False)
    printer.step(name, rc, out.getvalue(), err.getvalue())
    return rc


# --------------------------------------------------------------------------- the old side ---------------------------------------------------------------------------

BASH_SCENARIOS = {
    "hash": r"""
step sha-one _sha256sum "$W/plain.txt"
step sha-two _sha256sum "$W/plain.txt" "$W/second.txt"
step sha-space _sha256sum "$W/a space.txt"
step sha-backslash _sha256sum "$W/back\\slash.txt"
step sha-missing _sha256sum "$W/nosuch.txt"
step sha-partial _sha256sum "$W/plain.txt" "$W/nosuch.txt"

sha_stdin() { printf 'hello\nworld\n' | _sha256sum; }
step sha-stdin sha_stdin

step walk-pkg compute_hash_for_package_dirs "$W" pkg
step walk-two compute_hash_for_package_dirs "$W" pkg other
step walk-slash compute_hash_for_package_dirs "$W" pkg/
step walk-empty compute_hash_for_package_dirs "$W" empty
step walk-missing compute_hash_for_package_dirs "$W" nosuch
step walk-mixed compute_hash_for_package_dirs "$W" pkg nosuch
step walk-default compute_hash_for_package_dirs "$W/pkg"
step walk-bad-root compute_hash_for_package_dirs "$W/not-a-directory" pkg
step walk-file-root compute_hash_for_package_dirs "$W" plain.txt
step walk-file-as-root compute_hash_for_package_dirs "$W/plain.txt" pkg
""",
    "git-fp": r"""
step fp-dot _git_tree_fingerprint "$W/repo" .
step fp-src _git_tree_fingerprint "$W/repo" src
step fp-doc _git_tree_fingerprint "$W/repo" doc
step fp-two _git_tree_fingerprint "$W/repo" src doc
step fp-no-tree _git_tree_fingerprint "$W/repo" src nosuchdir
step fp-only-missing _git_tree_fingerprint "$W/repo" nosuchdir
step fp-deleted-first _git_tree_fingerprint "$W/repo-first" .
step fp-deleted-first-src _git_tree_fingerprint "$W/repo-first" src
step fp-not-a-repo _git_tree_fingerprint "$W/notarepo" .
step fp-bad-root _git_tree_fingerprint "$W/nosuch" .
step fp-no-paths _git_tree_fingerprint "$W/repo"
""",
    "tree-hash": r"""
step th-git compute_tree_hash "$W/repo" .
step th-git-src compute_tree_hash "$W/repo" src
step th-deleted-first compute_tree_hash "$W/repo-first" src
step th-fallback compute_tree_hash "$W/notarepo" .
step th-fallback-nested compute_tree_hash "$W/notarepo" nested
step th-bad-root compute_tree_hash "$W/nosuch" .
""",
    "stamp": r"""
step read-absent read_stamp_hash "$W/stamps/nosuch.stamp"
step read-empty read_stamp_hash "$W/stamps/empty.stamp"
step read-bare read_stamp_hash "$W/stamps/bare.stamp"
step read-two read_stamp_hash "$W/stamps/two.stamp"
step read-dir read_stamp_hash "$W/stamps"

step write-simple write_stamp_hash "$W/stamps/out.stamp" "deadbeef"
dump write-simple "$W/stamps/out.stamp"
step read-back read_stamp_hash "$W/stamps/out.stamp"

step write-two write_stamp_hash "$W/stamps/deep/nested/out.stamp" "abc
bin=4096:1700000000"
dump write-two "$W/stamps/deep/nested/out.stamp"

step write-spaces write_stamp_hash "$W/stamps/spaces.stamp" "a value with spaces"
dump write-spaces "$W/stamps/spaces.stamp"

step write-empty write_stamp_hash "$W/stamps/blank.stamp" ""
dump write-empty "$W/stamps/blank.stamp"

step write-overwrite write_stamp_hash "$W/stamps/out.stamp" "second"
dump write-overwrite "$W/stamps/out.stamp"

relative() { (cd "$W/stamps" && write_stamp_hash "relative.stamp" "rel"); }
step write-relative relative
dump write-relative "$W/stamps/relative.stamp"
""",
    "version": r"""
while IFS='|' read -r a b; do
    set +e
    ( set -e; _version_gte "$a" "$b" )
    rc=$?
    set -e
    emit "vgte [$a] [$b] = $rc"
done <"$W/version-pairs.txt"
""",
    "npm-script": r"""
emit "root| $LOCAL_ROOT_DIR"
emit "ci| $LOCAL_CI_DIR"
emit "lib| $LOCAL_LIB_DIR"
while IFS= read -r name; do
    set +e
    ( set -e; has_npm_script "$name" )
    rc=$?
    set -e
    emit "npm [$name] = $rc"
done <"$W/names.txt"
mv "$W/package.json" "$W/package.json.away"
step npm-missing has_npm_script build
mv "$W/package.json.away" "$W/package.json"
""",
    "sed": r"""
step sed-one _sed_i 's/beta/BETA/' "$W/sed/one.txt"
dump sed-one "$W/sed/one.txt"

step sed-two _sed_i 's/alpha/ALPHA/' "$W/sed/one.txt" "$W/sed/two.txt"
dump sed-two-a "$W/sed/one.txt"
dump sed-two-b "$W/sed/two.txt"

step sed-nomatch _sed_i 's/nothing-here/X/' "$W/sed/nomatch.txt"
dump sed-nomatch "$W/sed/nomatch.txt"

step sed-nonewline _sed_i 's/beta/BETA/' "$W/sed/nonewline.txt"
dump sed-nonewline "$W/sed/nonewline.txt"

step sed-append _sed_i '$a appended' "$W/sed/two.txt"
dump sed-append "$W/sed/two.txt"

step sed-missing _sed_i 's/a/b/' "$W/sed/nosuch.txt"
""",
}


def run_old(work: pathlib.Path, scenario: str, env: dict[str, str]) -> int:
    """Source the twin through `run-legacy.sh`'s own prelude and call its functions."""
    script = work / "driver.sh"
    script.write_text(
        'W="%s"\n%s\n%s' % (work, PRELUDE, BASH_SCENARIOS[scenario]), encoding="utf-8"
    )
    proc = subprocess.run(
        ["bash", str(script)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


# --------------------------------------------------------------------------- the new side ---------------------------------------------------------------------------


def write_relative(stamps: pathlib.Path) -> None:
    """`(cd "$W/stamps" && write_stamp_hash "relative.stamp" "rel")`.

    A relative stamp path is the case where `dirname` answers `.` and `os.path.dirname` answers the empty string, which is the difference the port's `or "."` exists for.
    """
    previous = os.getcwd()
    os.chdir(str(stamps))
    try:
        local_common.write_stamp_hash("relative.stamp", "rel")
    finally:
        os.chdir(previous)


def fingerprint_or_one(root: str, points: list[str], env: dict[str, str]) -> local_common.Outcome:
    """`_git_tree_fingerprint` as the shell sees it: a line on stdout, or nothing and 1."""
    fingerprint = local_common.git_tree_fingerprint(root, points, env, errexit=True)
    if fingerprint is None:
        return local_common.Outcome("", 1)
    return local_common.Outcome(fingerprint, 0)


def run_hash(printer: Printer, root: str) -> int:
    """The `hash` scenario on the port side."""
    call(printer, "sha-one", lambda: local_common.sha256sum([root + "/plain.txt"]))
    call(
        printer,
        "sha-two",
        lambda: local_common.sha256sum([root + "/plain.txt", root + "/second.txt"]),
    )
    call(printer, "sha-space", lambda: local_common.sha256sum([root + "/a space.txt"]))
    call(printer, "sha-backslash", lambda: local_common.sha256sum([root + "/back\\slash.txt"]))
    call(printer, "sha-missing", lambda: local_common.sha256sum([root + "/nosuch.txt"]))
    call(
        printer,
        "sha-partial",
        lambda: local_common.sha256sum([root + "/plain.txt", root + "/nosuch.txt"]),
    )
    call(printer, "sha-stdin", lambda: local_common.sha256sum([], stdin=b"hello\nworld\n"))

    for name, points in (
        ("walk-pkg", ["pkg"]),
        ("walk-two", ["pkg", "other"]),
        ("walk-slash", ["pkg/"]),
        ("walk-empty", ["empty"]),
        ("walk-missing", ["nosuch"]),
        ("walk-mixed", ["pkg", "nosuch"]),
    ):
        call(
            printer,
            name,
            lambda points=points: local_common.compute_hash_for_package_dirs(root, points),
        )
    call(
        printer,
        "walk-default",
        lambda: local_common.compute_hash_for_package_dirs(root + "/pkg", []),
    )
    call(
        printer,
        "walk-bad-root",
        lambda: local_common.compute_hash_for_package_dirs(root + "/not-a-directory", ["pkg"]),
    )
    call(
        printer,
        "walk-file-root",
        lambda: local_common.compute_hash_for_package_dirs(root, ["plain.txt"]),
    )
    call(
        printer,
        "walk-file-as-root",
        lambda: local_common.compute_hash_for_package_dirs(root + "/plain.txt", ["pkg"]),
    )
    return 0


def run_git_fp(printer: Printer, root: str, env: dict[str, str]) -> int:
    """The `git-fp` scenario on the port side."""
    for name, target, points in (
        ("fp-dot", "repo", ["."]),
        ("fp-src", "repo", ["src"]),
        ("fp-doc", "repo", ["doc"]),
        ("fp-two", "repo", ["src", "doc"]),
        ("fp-no-tree", "repo", ["src", "nosuchdir"]),
        ("fp-only-missing", "repo", ["nosuchdir"]),
        ("fp-deleted-first", "repo-first", ["."]),
        ("fp-deleted-first-src", "repo-first", ["src"]),
        ("fp-not-a-repo", "notarepo", ["."]),
        ("fp-bad-root", "nosuch", ["."]),
        ("fp-no-paths", "repo", []),
    ):
        call(
            printer,
            name,
            lambda target=target, points=points: fingerprint_or_one(
                os.path.join(root, target), points, env
            ),
        )
    return 0


def run_tree_hash(printer: Printer, root: str, env: dict[str, str]) -> int:
    """The `tree-hash` scenario on the port side."""
    for name, target, points in (
        ("th-git", "repo", ["."]),
        ("th-git-src", "repo", ["src"]),
        ("th-deleted-first", "repo-first", ["src"]),
        ("th-fallback", "notarepo", ["."]),
        ("th-fallback-nested", "notarepo", ["nested"]),
        ("th-bad-root", "nosuch", ["."]),
    ):
        call(
            printer,
            name,
            lambda target=target, points=points: local_common.compute_tree_hash(
                os.path.join(root, target), points, env
            ),
        )
    return 0


def run_stamp(printer: Printer, work: pathlib.Path) -> int:
    """The `stamp` scenario on the port side."""
    stamps = work / "stamps"

    def read(target: str) -> local_common.Outcome:
        return local_common.Outcome(local_common.read_stamp_hash(str(stamps / target)), 0)

    for name, target in (
        ("read-absent", "nosuch.stamp"),
        ("read-empty", "empty.stamp"),
        ("read-bare", "bare.stamp"),
        ("read-two", "two.stamp"),
    ):
        call(printer, name, lambda target=target: read(target))
    call(
        printer,
        "read-dir",
        lambda: local_common.Outcome(local_common.read_stamp_hash(str(stamps)), 0),
    )

    call(
        printer,
        "write-simple",
        lambda: local_common.write_stamp_hash(str(stamps / "out.stamp"), "deadbeef"),
    )
    printer.dump("write-simple", stamps / "out.stamp")
    call(printer, "read-back", lambda: read("out.stamp"))

    call(
        printer,
        "write-two",
        lambda: local_common.write_stamp_hash(
            str(stamps / "deep" / "nested" / "out.stamp"), "abc\nbin=4096:1700000000"
        ),
    )
    printer.dump("write-two", stamps / "deep" / "nested" / "out.stamp")

    call(
        printer,
        "write-spaces",
        lambda: local_common.write_stamp_hash(str(stamps / "spaces.stamp"), "a value with spaces"),
    )
    printer.dump("write-spaces", stamps / "spaces.stamp")

    call(
        printer,
        "write-empty",
        lambda: local_common.write_stamp_hash(str(stamps / "blank.stamp"), ""),
    )
    printer.dump("write-empty", stamps / "blank.stamp")

    call(
        printer,
        "write-overwrite",
        lambda: local_common.write_stamp_hash(str(stamps / "out.stamp"), "second"),
    )
    printer.dump("write-overwrite", stamps / "out.stamp")

    call(printer, "write-relative", lambda: write_relative(stamps))
    printer.dump("write-relative", stamps / "relative.stamp")
    return 0


def run_sed(printer: Printer, work: pathlib.Path, env: dict[str, str]) -> int:
    """The `sed` scenario on the port side."""
    directory = work / "sed"
    call(
        printer,
        "sed-one",
        lambda: local_common.sed_i(["s/beta/BETA/", str(directory / "one.txt")], env),
    )
    printer.dump("sed-one", directory / "one.txt")

    call(
        printer,
        "sed-two",
        lambda: local_common.sed_i(
            ["s/alpha/ALPHA/", str(directory / "one.txt"), str(directory / "two.txt")], env
        ),
    )
    printer.dump("sed-two-a", directory / "one.txt")
    printer.dump("sed-two-b", directory / "two.txt")

    call(
        printer,
        "sed-nomatch",
        lambda: local_common.sed_i(["s/nothing-here/X/", str(directory / "nomatch.txt")], env),
    )
    printer.dump("sed-nomatch", directory / "nomatch.txt")

    call(
        printer,
        "sed-nonewline",
        lambda: local_common.sed_i(["s/beta/BETA/", str(directory / "nonewline.txt")], env),
    )
    printer.dump("sed-nonewline", directory / "nonewline.txt")

    call(
        printer,
        "sed-append",
        lambda: local_common.sed_i(["$a appended", str(directory / "two.txt")], env),
    )
    printer.dump("sed-append", directory / "two.txt")

    call(
        printer,
        "sed-missing",
        lambda: local_common.sed_i(["s/a/b/", str(directory / "nosuch.txt")], env),
    )
    return 0


def run_npm_script(printer: Printer, work: pathlib.Path, env: dict[str, str]) -> int:
    """The `npm-script` scenario on the port side."""
    printer.emit("root| %s" % local_common.local_root_dir(env))
    printer.emit("ci| %s" % local_common.local_ci_dir(env))
    printer.emit("lib| %s" % local_common.local_lib_dir(env))
    for name in NPM_SCRIPT_NAMES:
        rc = 0 if local_common.has_npm_script(name, env) else 1
        printer.emit("npm [%s] = %d" % (name, rc))
    (work / "package.json").rename(work / "package.json.away")
    call(printer, "npm-missing", lambda: local_common.has_npm_script("build", env))
    (work / "package.json.away").rename(work / "package.json")
    return 0


def run_new(scenario: str, printer: Printer, work: pathlib.Path, env: dict[str, str]) -> int:
    """Drive `rediacc_ci.core.local_common` through the same scenario."""
    root = str(work)
    if scenario == "hash":
        return run_hash(printer, root)
    if scenario == "git-fp":
        return run_git_fp(printer, root, env)
    if scenario == "tree-hash":
        return run_tree_hash(printer, root, env)
    if scenario == "stamp":
        return run_stamp(printer, work)
    if scenario == "sed":
        return run_sed(printer, work, env)
    if scenario == "npm-script":
        return run_npm_script(printer, work, env)
    if scenario == "version":
        for one, two in VERSION_PAIRS:
            rc = 0 if local_common.version_gte(one, two) else 1
            printer.emit("vgte [%s] [%s] = %d" % (one, two, rc))
        return 0
    raise RefusalError("unknown scenario %r" % scenario)


# --------------------------------------------------------------------------- argv ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="one side of the core.local_common differential")
    parser.add_argument("--side", choices=("old", "new"), required=True)
    parser.add_argument("--twin", required=True, help="the bash file under comparison")
    parser.add_argument("--port", required=True, help="the Python module under comparison")
    parser.add_argument("scenario", choices=sorted(BASH_SCENARIOS))
    args = parser.parse_args(argv)

    repo = pathlib.Path.cwd().resolve()
    for label, rel in (("twin", args.twin), ("port", args.port)):
        if not (repo / rel).is_file():
            sys.stderr.write(
                "local_common_shadow_driver: the %s %s does not exist under %s. A ledger row "
                "naming a file that is not there attests to nothing.\n" % (label, rel, repo)
            )
            return EXIT_CANNOT_RUN

    if shutil.which("git") is None:
        sys.stderr.write(
            "local_common_shadow_driver: git is not installed, so both sides would take the "
            "same refusal branch and the comparison would prove nothing.\n"
        )
        return EXIT_CANNOT_RUN

    work = None
    try:
        work = build_sandbox(repo)
        env = sandbox_env(work)
        build_fixtures(work, args.scenario, env)
        printer = Printer(work)
        if args.side == "old":
            return run_old(work, args.scenario, env)
        return run_new(args.scenario, printer, work, env)
    except RefusalError as exc:
        sys.stderr.write("local_common_shadow_driver: %s\n" % exc)
        return EXIT_CANNOT_RUN
    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
