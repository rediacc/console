r"""check:ci-env-file-adoption -- `set -a; source <envfile>` must not come back.

WHY THIS EXISTS. `set -a; source "$f"` does two things nobody at the call site
asked for. It EXECUTES the file, so a `$(...)` in a value runs -- and these files
hold ACCOUNT_ED25519_PRIVATE_KEY, ACCOUNT_X25519_PRIVATE_KEY, ACCOUNT_JWT_SECRET
and ACCOUNT_SERVER_API_KEY. And it lets the FILE overwrite the SHELL, so every
override this repo ships through the environment -- a workflow `env:` block, a
GITHUB_ENV append, `RUSTFS_PORT=9101 ./script` -- is discarded in favour of a line
written to disk months ago, silently.

`rediacc_ci.core.env` is the replacement and `scripts/lib/env-file.sh` is the bash
shim over it.

WHY THE SHIM LIVES UNDER `scripts/lib/` AND NOT `.ci/lib/`, WHICH IS WHERE ITS
SIBLINGS ARE. Ruling 7 makes `.ci` and `.claude` single-language:
`check_language_policy.COVERED_ROOTS` is `(".ci", ".claude")` and its
`baseline_additions` refuses a NEW tracked `.sh` under either. The first cut of
this work put the shim at `.ci/lib/env-file.sh` beside `find-port.sh` and
`age-check.sh`, and `check:ci-language-policy` went rc=1 with `2 NEW bash
file(s)`; the registration was unwound rather than allowlisted.

A bash shim for bash callers cannot itself be Python, so the choice was an
allowlist entry or a different address. `scripts/` is not a covered root, and the
shim already serves callers on both sides of the line -- `scripts/dev/deploy-bench.sh`
and `programs/backup-storage/start-local-plane.sh` were never under `.ci` at all --
so a shared location is the better description of what it is, not merely the legal
one. No exemption was added to any allowlist for this gate or for the shim.

THREE CHECKS, because two of them can pass while the thing is broken:

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

  B. PER-SITE ACCEPTANCE, and it RUNS the site's own line. For each adopted site
     this extracts the literal `env_file_load` invocations out of the file, points
     each one at a fixture, plants one of the fixture's own names in the
     environment with a DIFFERENT value, and asserts the shell value survives
     while an unplanted name is still filled from the file. A site that reverts to
     `source` has no invocation to extract and fails here.

  C. DIFFERENTIAL. The same fixture, under a real `set -a; source`, must give the
     OPPOSITE answer. Without this, B would pass just as happily against a helper
     that did nothing at all, because "the variable still holds the value I
     exported" is also what happens when nothing reads the file.

ONE EXEMPTION DISAPPEARED IN THE PORT, and it is worth saying why rather than
letting the list quietly shrink by one. The bash predecessor had to exempt
ITSELF: it wrote `set -a` fixtures to prove its own matcher fired on all three
spellings, and the sweep read those literals in its own source. This module has
the same fixtures and needs no exemption, because the sweep scans `*.sh` and this
is not one. That is a real reduction in exempted surface, not an accounting
change -- the alternative the predecessor named was obfuscating the literal so the
sweep could not see it, which would have disarmed the control that keeps the
matcher honest.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import stat
import subprocess
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls, controls_first

SHIM_REL = "scripts/lib/env-file.sh"

# The sites that adopted the shim. Each must still call it; see CHECK B.
ADOPTED = (
    ".ci/lib/account.sh",
    "scripts/dev/deploy-bench.sh",
    "programs/backup-storage/start-local-plane.sh",
)

# The sites that may still run `set -a`, reason first. These are PRINTED every
# run rather than being quietly skipped: an exemption nobody sees is how a gate
# stops meaning what its name says.
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
    (
        ".ci/legacy/run-legacy.sh",
        (
            "BLOCKER: W6 P5 deletes this file. Retargeting it is work thrown away, and the "
            "plan records the decision here so the site is not re-found and mistaken for a "
            "miss."
        ),
    ),
)

# A `set -a` COMMAND, not the string. It may open a line or follow a `;`, `&&`,
# `|` or `(` -- .ci/legacy/run-legacy.sh:185 is the `$(set -a && source ...)` form
# and an anchored pattern misses it entirely.
#
# THE TRAILING BOUNDARY WAS `(?:\s|$)` AND THAT MISSED THE CANONICAL FORM.
# Inherited verbatim from the bash predecessor, where it had the same hole. A
# one-liner spells it `set -a; source "$f"; set +a` -- the `;` binds directly to
# the `-a` with no space -- so the single most likely spelling of the exact thing
# this gate exists to prevent went unmatched, as did `set -a|`, `set -a&&` and
# `(set -a; . f)`. Found 2026-09-09 by PLANTING a reversion on the real tree and
# noticing that only CHECK B fired: CHECK A, the sweep, said nothing. The
# selftest agreed with the bug, because all three of its fixtures used the
# spellings the pattern already matched.
#
# So the boundary is now a lookahead over the shell separators as well as
# whitespace and end-of-line. It stays a LOOKAHEAD so a `;` cannot be consumed
# and hide a second command on the same line from a future clause.
SET_A_RE = re.compile(r"(?:^|[;&|(]|&&)\s*set -a(?=\s|[;&|)]|$)")
COMMENT_RE = re.compile(r"^\s*#")

# The invocation shape CHECK B extracts and re-runs.
INVOKE_RE = re.compile(r'(?:^|[;&|(]|&&)\s*env_file_load\s+"')

SCAN_GLOBS = (".ci/**/*.sh", "scripts/**/*.sh", "programs/**/*.sh", "*.sh")


class RefusalError(Exception):
    """The instrument cannot see the tree, so it has no verdict to give."""


# THE ONE PLACE A FINDING IS DECIDED. The controls call this, not the regex,
# because a control that re-implements the predicate tests its own copy: in the
# bash predecessor the comment filter lived only in the sweep for one revision,
# and its selftest case 6 promptly disagreed with the sweep about a comment.
#
# COMMENT LINES ARE NOT COMMANDS. Without the second filter the sweep condemns
# the paragraph that EXPLAINS the rule -- the predecessor's own header was its
# first offender -- and the fix a reader reaches for is to stop writing the
# explanation down. Line numbers survive the filter.
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

    `git ls-files` alone would leave a brand new script invisible to this sweep
    until somebody committed it, which is exactly the window in which a `set -a`
    gets written. `--others --exclude-standard` adds the new files without
    dragging in node_modules or anything else .gitignore already refuses.
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
                "use env_file_load from %s" % (rel, lineno, SHIM_REL)
            )
    # Liveness: an exemption for a file that no longer runs `set -a` excuses
    # nothing and would sit forever looking like coverage. The list may only shrink.
    for rel in sorted(reasons):
        if not (root / rel).is_file():
            findings.append("EXEMPT names %s, which does not exist -- drop the entry" % rel)
        elif rel not in seen_exempt:
            findings.append(
                "EXEMPT names %s, which no longer runs `set -a` -- drop the entry, the "
                "debt is paid" % rel
            )
    return findings, len(scan)


def check_sites(root, fixture):
    """CHECK B. Returns (findings, n_invocations)."""
    findings = []
    invocations = 0
    for site in ADOPTED:
        path = root / site
        if not path.is_file():
            findings.append("%s: listed as an adopted site and not present" % site)
            continue
        lines = [
            (i, line)
            for i, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            )
            if INVOKE_RE.search(line) and not COMMENT_RE.match(line)
        ]
        if not lines:
            findings.append(
                '%s: no `env_file_load "..."` invocation -- adoption was reverted, or '
                "the call moved and this gate went blind" % site
            )
            continue
        for lineno, body in lines:
            # Point the site's OWN line at the fixture, and neutralise a trailing
            # `|| return 1` that only makes sense inside a function.
            probe = re.sub(r'env_file_load "[^"]*"', 'env_file_load "%s"' % fixture, body)
            probe = re.sub(r"\|\| *return [0-9]+", "|| exit 1", probe)
            rc, out = _sh(
                'source "$1/%s" || exit 9\nshift 2\neval "$@"\necho "$PLANTED/$FILLED"' % SHIM_REL,
                root,
                "x",
                probe,
                env={"PLANTED": "fromshell"},
            )
            if rc != 0:
                findings.append("%s:%d: the invocation did not run: %s" % (site, lineno, out))
                continue
            invocations += 1
            if out != "fromshell/fromfile":
                findings.append(
                    "%s:%d: expected fromshell/fromfile, got '%s' -- either the file "
                    "overwrote the shell, or nothing read the file" % (site, lineno, out)
                )
    if invocations == 0:
        findings.append(
            "ZERO invocations were exercised: this check asserted nothing about any site"
        )
    return findings, invocations


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


def selftest():
    """Both directions on fixtures, before the real tree is touched."""
    c = Controls("env file adoption", 8)
    root = paths.repo_root()
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        fixture = _write_fixture(tmp)

        # 1. the shim: the shell wins, the file fills the rest
        _rc, out = _sh(
            'source "$1/%s" || exit 9\nenv_file_load "$2" || exit 8\necho "$PLANTED/$FILLED"'
            % SHIM_REL,
            root,
            fixture,
            env={"PLANTED": "fromshell"},
        )
        c.check(
            "the shim lets the SHELL win and fills the rest from the file",
            out,
            "fromshell/fromfile",
        )

        # 2. CONTROL for 1: a real `set -a; source` must give the OPPOSITE answer.
        #    If it does not, the fixture is not discriminating and case 1 proves
        #    nothing about precedence.
        c.check(
            "CONTROL: `set -a; source` on the same fixture gives the file the win",
            check_differential(fixture),
            [],
        )

        # 3. a missing file is normal, not an error
        rc, _out = _sh('source "$1/%s" && env_file_load "$2"' % SHIM_REL, root, tmp / "absent.env")
        c.check("a missing env file is a no-op, not a failure", rc, 0)

        # 4. an unreadable file is a defect, and must NOT be silently empty
        locked = tmp / "locked.env"
        locked.write_text("", encoding="utf-8")
        locked.chmod(0o000)
        rc, _out = _sh('source "$1/%s" && env_file_load "$2"' % SHIM_REL, root, locked)
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
        #    the canonical one-liner, so the sweep was blind to the likeliest
        #    spelling of the thing it exists to catch.
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

        # 6. CONTROL for 5: it must NOT fire on the word in prose or in a pattern.
        #    .ci/scripts/test/test-rdc-sh-env.sh is the real file this protects.
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

        # 8. ANTI-SILENCER: an adopted site that reverted to `source` is caught.
        #    Proven by PLANTING the reversion on a copy of the real tree, not by
        #    asking the matcher about a string.
        planted = tmp / "planted"
        planted.mkdir()
        (planted / "programs" / "backup-storage").mkdir(parents=True)
        src = root / "programs/backup-storage/start-local-plane.sh"
        reverted = re.sub(
            r'(?m)^(\s*)env_file_load "([^"]*)"',
            r'\1set -a; . "\2"; set +a',
            src.read_text(encoding="utf-8"),
        )
        (planted / "programs/backup-storage/start-local-plane.sh").write_text(
            reverted, encoding="utf-8"
        )
        for rel in (".ci/lib/account.sh", "scripts/dev/deploy-bench.sh", SHIM_REL):
            dst = planted / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / rel, dst)
        site_findings, _n = check_sites(planted, fixture)
        c.truthy(
            "ANTI-SILENCER: a site reverted to `set -a; source` is a finding",
            any("start-local-plane.sh" in f for f in site_findings),
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return not c.report()


def run(root=None):
    """Measure the tree at `root` and return (findings, n_scanned, n_invocations)."""
    base = root or paths.repo_root()
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        fixture = _write_fixture(tmp)
        sweep, n_scanned = check_sweep(base)
        sites, n_invocations = check_sites(base, fixture)
        diff = check_differential(fixture)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return sweep + sites + diff, n_scanned, n_invocations


def main(argv=None):
    argv = list(argv or [])
    if "--selftest" in argv:
        # `selftest()` returns TRUE when a control FAILED, which is the contract
        # `controls_first` reads it under.
        return 1 if selftest() else 0
    rc = controls_first("env file adoption", selftest)
    if rc:
        return rc
    log.info("exemptions, printed every run so the debt cannot be forgotten:")
    for rel, reason in EXEMPT:
        print("  %s" % rel)
        print("      %s" % reason)
    try:
        findings, n_scanned, n_invocations = run()
    except RefusalError as exc:
        log.error("env file adoption: %s" % exc)
        return 2
    if findings:
        for finding in findings:
            log.error("  %s" % finding)
        log.error(
            "%d finding(s). Fix: source %s and call env_file_load; the shell must win "
            "over the file. Do not add an exemption -- every entry in that list is a "
            "dated decision with an owner." % (len(findings), SHIM_REL)
        )
        return 1
    log.success(
        "%d shell files scanned, %d exempt, 0 new `set -a`; %d adopted sites, %d "
        "invocations run, the shell won every time; the differential holds"
        % (n_scanned, len(EXEMPT), len(ADOPTED), n_invocations)
    )
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
