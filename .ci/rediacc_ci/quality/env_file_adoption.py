r"""check:ci-env-file-adoption -- `set -a; source <envfile>` must not come back.

WHY THIS EXISTS. `set -a; source "$f"` does two things nobody at the call site asked for. It EXECUTES the file, so a `$(...)` in a value runs -- and these files hold ACCOUNT_ED25519_PRIVATE_KEY, ACCOUNT_X25519_PRIVATE_KEY, ACCOUNT_JWT_SECRET and ACCOUNT_SERVER_API_KEY. And it lets the FILE overwrite the SHELL, so every override this repo ships through the environment -- a workflow
`env:` block, a
GITHUB_ENV append, `RUSTFS_PORT=9101 ./script` -- is discarded in favour of a line
written to disk months ago, silently.

`rediacc_ci.core.env` is the replacement. A Python caller reads the file with `env_file_load`; a bash caller that cannot be ported yet evals the module's `export` verb, which prints one shell-quoted `export KEY=value` line for every key the environment does not already carry:

    out="$(PYTHONPATH=.ci python3 -m rediacc_ci.core.env export "$f")" || exit 1
    eval "$out"

THE BASH SHIM IS GONE (W7P5-c). `scripts/lib/env-file.sh` wrapped exactly that call as a function; its last bash caller was `scripts/lib/well-known.sh`, which went with it when its three consumers moved to `.ci/config/well-known.generated.sh` (equivalence: `.ci/shadow/w7p5c-well-known-projection.observations.jsonl`). The ADOPTED-SITES check that used to re-run each adopted bash site's own `env_file_load` line went too: it needed the shim's function to exist, and its list was already empty: every adopted site (the bench deploy, `start-local-plane.sh`, `.ci/lib/account.sh`) had been ported to Python and reads the file through `rediacc_ci.core.env` directly. A bash site that comes back needs no list to be held to the rule, because CHECK A refuses its `set -a` wherever it is.

TWO CHECKS, because one of them can pass while the thing is broken:

  A. SWEEP. No shell file may run `set -a`, except the exemptions below, each of
     which is PRINTED with its reason on every run and is liveness-checked: an
     exemption whose file no longer runs `set -a` is a dangling entry and fails,
     so the list can only shrink.

     THE SCAN IS REPO-WIDE, not the four roots the pathspecs read as. A git
     pathspec without `:(glob)` magic matches with FNM_PATHNAME off, so the `*`
     in `*.sh` crosses `/` and that one entry already selects every tracked `.sh`
     in the repository: measured 2026-09-09, `git ls-files '*.sh'` returns 621
     against 514 for the three directory globs combined. The predecessor carried
     the same globs and the same wrong description. It is left repo-wide on
     purpose -- the wider set is the one worth sweeping, and the first thing the
     widened matcher found lived in `.claude/`, outside all three named roots.

  C. DIFFERENTIAL. The same fixture, under a real `set -a; source`, must give the
     OPPOSITE answer to the one the `export` verb gives. Without this, the
     selftest's "the shell wins" would pass just as happily against a loader that
     did nothing at all, because "the variable still holds the value I exported"
     is also what happens when nothing reads the file.

ONE EXEMPTION DISAPPEARED IN THE PORT, and it is worth saying why rather than letting the list quietly shrink by one. The bash predecessor had to exempt ITSELF: it wrote `set -a` fixtures to prove its own matcher fired on all three spellings, and the sweep read those literals in its own source. This module has the same fixtures and needs no exemption, because the sweep scans `*.sh`
and this is not one. That is a real reduction in exempted surface, not an accounting change -- the alternative the predecessor named was obfuscating the literal so the sweep could not see it, which would have disarmed the control that keeps the matcher honest.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import stat
import subprocess
import tempfile

from rediacc_ci import log, paths, runtmp
from rediacc_ci.controls import Controls, controls_first, git_isolated

# The remedy every finding names: the module that parses an env file without executing it, and the bash spelling of a call to it.
LOADER_MODULE = "rediacc_ci.core.env"
# Two steps, never `eval "$(...)"`: the substitution's exit status is lost inside an eval, so an unreadable file would load nothing and say nothing.
BASH_LOADER = (
    'out="$(PYTHONPATH=.ci python3 -m %s export "$f")" || exit 1; eval "$out"' % LOADER_MODULE
)

# The sites that may still run `set -a`, reason first. These are PRINTED every run rather than being quietly skipped: an exemption nobody sees is how a gate stops meaning what its name says.
EXEMPT = (
    (
        ".ci/config/constants.sh",
        (
            "BLOCKER: sourced before python3 is guaranteed. It loads "
            ".devcontainer/toolchain.env for consumers that run during image bootstrap, "
            "so a python3 dependency here is a circularity. W6 P3 owns the retarget."
        ),
    ),
    (
        ".ci/scripts/lib/toolchain.sh",
        (
            "BLOCKER: .ci/bootstrap.sh:76 calls toolchain_load as its FIRST action, and "
            "that script exists because the host has no pip, no uv and no pytest. Putting "
            "python3 in front of the python bootstrap is the same circularity as "
            "constants.sh."
        ),
    ),
)

# A `set -a` COMMAND, not the string. It may open a line or follow a `;`, `&&`, `|` or `(` -- .ci/legacy/run-legacy.sh:185 is the `$(set -a && source ...)` form and an anchored pattern misses it entirely.
#
# THE TRAILING BOUNDARY WAS `(?:\s|$)` AND THAT MISSED THE CANONICAL FORM. Inherited verbatim from the bash predecessor, where it had the same hole. A one-liner spells it `set -a; source "$f"; set +a` -- the `;` binds directly to the `-a` with no space -- so the single most likely spelling of the exact thing this gate exists to prevent went unmatched, as did `set -a|`, `set -a&&`
# and `(set -a; . f)`. Found 2026-09-09 by PLANTING a reversion on the real tree and noticing that only CHECK B fired: CHECK A, the sweep, said nothing. The selftest agreed with the bug, because all three of its fixtures used the spellings the pattern already matched.
#
# So the boundary is now a lookahead over the shell separators as well as whitespace and end-of-line. It stays a LOOKAHEAD so a `;` cannot be consumed and hide a second command on the same line from a future clause.
SET_A_RE = re.compile(r"(?:^|[;&|(]|&&)\s*set -a(?=\s|[;&|)]|$)")
COMMENT_RE = re.compile(r"^\s*#")

SCAN_GLOBS = (".ci/**/*.sh", "scripts/**/*.sh", "programs/**/*.sh", "*.sh")


class RefusalError(Exception):
    """The instrument cannot see the tree, so it has no verdict to give."""


# THE ONE PLACE A FINDING IS DECIDED. The controls call this, not the regex, because a control that re-implements the predicate tests its own copy: in the bash predecessor the comment filter lived only in the sweep for one revision, and its selftest case 6 promptly disagreed with the sweep about a comment.
#
# COMMENT LINES ARE NOT COMMANDS. Without the second filter the sweep condemns the paragraph that EXPLAINS the rule -- the predecessor's own header was its first offender -- and the fix a reader reaches for is to stop writing the explanation down. Line numbers survive the filter.
def sweep_hits(path):
    """Return [(lineno, text)] for every real `set -a` command in `path`."""
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if COMMENT_RE.match(line):
            continue
        if SET_A_RE.search(line):
            out.append((i, line))
    return out


def _sh(script, *args, env=None, cwd=None):
    """Run `bash -c script _ *args`, returning (rc, stdout+stderr stripped)."""
    full = dict(os.environ)
    if env:
        full.update(env)
    proc = subprocess.run(
        ["bash", "-c", script, "_", *[str(a) for a in args]],
        capture_output=True,
        text=True,
        env=full,
        cwd=str(cwd) if cwd else None,
        check=False,  # the return code IS the measurement here
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _scan_set(root):
    """Tracked AND untracked-not-ignored shell files.

    `git ls-files` alone would leave a brand new script invisible to this sweep until somebody committed it, which is exactly the window in which a `set -a` gets written. `--others --exclude-standard` adds the new files without dragging in node_modules or anything else .gitignore already refuses.
    """
    seen = set()
    for extra in ([], ["--others", "--exclude-standard"]):
        proc = subprocess.run(
            ["git", "ls-files", *extra, *SCAN_GLOBS],
            capture_output=True,
            text=True,
            cwd=str(root),
            check=False,  # a non-zero rc is turned into a RefusalError below
        )
        if proc.returncode != 0:
            raise RefusalError("git ls-files failed: %s" % proc.stderr.strip())
        seen.update(p for p in proc.stdout.splitlines() if p.strip())
    return sorted(seen)


def check_sweep(root):
    """CHECK A. Returns (findings, n_scanned)."""
    scan = _scan_set(root)
    if not scan:
        raise RefusalError(
            "the sweep matched ZERO shell files -- it is not seeing the tree, so its "
            "green would mean nothing. Check the pathspecs."
        )
    reasons = dict(EXEMPT)
    seen_exempt = set()
    findings = []
    for rel in scan:
        hits = sweep_hits(root / rel)
        if not hits:
            continue
        if rel in reasons:
            seen_exempt.add(rel)
            continue
        for lineno, _text in hits:
            findings.append(
                "%s:%d -- `set -a` executes the file and lets it overwrite the shell; "
                "read it with %s (in bash: %s)" % (rel, lineno, LOADER_MODULE, BASH_LOADER)
            )
    # Liveness: an exemption for a file that no longer runs `set -a` excuses nothing and would sit forever looking like coverage. The list may only shrink.
    for rel in sorted(reasons):
        if not (root / rel).is_file():
            findings.append("EXEMPT names %s, which does not exist -- drop the entry" % rel)
        elif rel not in seen_exempt:
            findings.append(
                "EXEMPT names %s, which no longer runs `set -a` -- drop the entry, the "
                "debt is paid" % rel
            )
    return findings, len(scan)


def _load_with_verb(root, env_file, env=None):
    """Load `env_file` the sanctioned bash way (the `export` verb, its status checked, then eval) and echo the two fixture names. Returns (rc, output)."""
    full_env = {"PYTHONPATH": str(root / ".ci")}
    full_env.update(env or {})
    return _sh(
        'out="$(python3 -m %s export "$1")" || exit 8\neval "$out"\necho "$PLANTED/$FILLED"'
        % LOADER_MODULE,
        env_file,
        env=full_env,
    )


def check_differential(fixture):
    """CHECK C. Returns findings."""
    _rc, out = _sh(
        'set -a; . "$1"; set +a; echo "$PLANTED/$FILLED"',
        fixture,
        env={"PLANTED": "fromshell"},
    )
    if out != "fromfile/fromfile":
        return [
            "`set -a; source` on the same fixture gave '%s', not fromfile/fromfile. The "
            "fixture does not discriminate, so CHECK B would pass against a helper that "
            "read nothing at all. Fix the fixture before believing CHECK B." % out
        ]
    return []


def _write_fixture(d):
    p = pathlib.Path(d) / "fixture.env"
    p.write_text("PLANTED=fromfile\nFILLED=fromfile\n", encoding="utf-8")
    return p


@git_isolated
def selftest():
    """Both directions on fixtures, before the real tree is touched."""
    c = Controls("env file adoption", 7)
    root = paths.repo_root()
    tmp = pathlib.Path(tempfile.mkdtemp(dir=runtmp.shared("env-file-adoption-")))
    try:
        fixture = _write_fixture(tmp)

        # 1. the remedy the findings name: the shell wins, the file fills the rest
        _rc, out = _load_with_verb(root, fixture, env={"PLANTED": "fromshell"})
        c.check(
            "the export verb lets the SHELL win and fills the rest from the file",
            out,
            "fromshell/fromfile",
        )

        # 2. CONTROL for 1: a real `set -a; source` must give the OPPOSITE answer.
        # If it does not, the fixture is not discriminating and case 1 proves nothing about precedence.
        c.check(
            "CONTROL: `set -a; source` on the same fixture gives the file the win",
            check_differential(fixture),
            [],
        )

        # 3. a missing file is normal, not an error
        rc, _out = _load_with_verb(root, tmp / "absent.env")
        c.check("a missing env file is a no-op, not a failure", rc, 0)

        # 4. an unreadable file is a defect, and must NOT be silently empty
        locked = tmp / "locked.env"
        locked.write_text("", encoding="utf-8")
        locked.chmod(0o000)
        rc, _out = _load_with_verb(root, locked)
        if os.geteuid() == 0:
            # Running as root defeats mode 000; say so rather than reporting a pass.
            log.warn("selftest 4 skipped: running as uid 0, mode 000 does not deny")
            c.truthy("an unreadable env file case is attributable (skipped as uid 0)", True)
        else:
            c.truthy("an unreadable env file FAILS rather than reading as empty", rc != 0)
        locked.chmod(stat.S_IRUSR | stat.S_IWUSR)

        # 5. the sweep matcher fires on every spelling that matters.
        #    The last four are the ones the inherited pattern MISSED: a `;`, `|`,
        #    `&&` or `)` binding straight onto the `-a`. `set -a; source "$f"` is
        # the canonical one-liner, so the sweep was blind to the likeliest spelling of the thing it exists to catch.
        spellings = {
            "a": "set -a\n",
            "b": "    set -a\n",
            "c": "x=$(set -a && . f && env)\n",
            "d": 'set -a; . "$f"; set +a\n',
            "e": "set -a|cat\n",
            "f": "set -a&& . f\n",
            "g": "(set -a; . f)\n",
        }
        for name, body in spellings.items():
            (tmp / ("%s.sh" % name)).write_text(body, encoding="utf-8")
        missed = [n for n in spellings if not sweep_hits(tmp / ("%s.sh" % n))]
        c.check(
            "the sweep fires on all seven spellings, separator-bound ones included",
            missed,
            [],
        )

        # 6. CONTROL for 5: it must NOT fire on the word in prose or in a pattern. .ci/scripts/test/test-rdc-sh-env.sh is the real file this protects.
        (tmp / "prose.sh").write_text(
            "# 1a. No `set -a` command (comments do not count)\n"
            "# the $(set -a && source ...) form, named in a comment\n"
            "if grep -nE '^[[:space:]]*set[[:space:]]+-a' \"$F\"; then :; fi\n"
            'echo "reset -also"\n',
            encoding="utf-8",
        )
        c.check(
            "CONTROL: the matcher does not fire on prose or on a pattern",
            sweep_hits(tmp / "prose.sh"),
            [],
        )

        # 7. VACUITY: a sweep that sees no files REFUSES rather than passing.
        empty = tmp / "empty-repo"
        empty.mkdir()
        subprocess.run(["git", "init", "-q", str(empty)], capture_output=True, check=False)
        refused = False
        try:
            check_sweep(empty)
        except RefusalError:
            refused = True
        c.truthy("VACUITY: a tree with zero shell files is a REFUSAL, not a pass", refused)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return not c.report()


def run(root=None):
    """Measure the tree at `root` and return (findings, n_scanned)."""
    base = root or paths.repo_root()
    tmp = pathlib.Path(tempfile.mkdtemp(dir=runtmp.shared("env-file-adoption-")))
    try:
        fixture = _write_fixture(tmp)
        sweep, n_scanned = check_sweep(base)
        diff = check_differential(fixture)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return sweep + diff, n_scanned


def main(argv=None):
    argv = list(argv or [])
    if "--selftest" in argv:
        # `selftest()` returns TRUE when a control FAILED, which is the contract `controls_first` reads it under.
        return 1 if selftest() else 0
    rc = controls_first("env file adoption", selftest)
    if rc:
        return rc
    log.info("exemptions, printed every run so the debt cannot be forgotten:")
    for rel, reason in EXEMPT:
        print("  %s" % rel)
        print("      %s" % reason)
    try:
        findings, n_scanned = run()
    except RefusalError as exc:
        log.error("env file adoption: %s" % exc)
        return 2
    if findings:
        for finding in findings:
            log.error("  %s" % finding)
        log.error(
            "%d finding(s). Fix: read the file with %s (in bash: %s); the shell must win "
            "over the file. Do not add an exemption -- every entry in that list is a "
            "dated decision with an owner." % (len(findings), LOADER_MODULE, BASH_LOADER)
        )
        return 1
    log.success(
        "%d shell files scanned, %d exempt, 0 new `set -a`; the export verb lets the "
        "shell win and the `set -a` differential gives the file the win" % (n_scanned, len(EXEMPT))
    )
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
