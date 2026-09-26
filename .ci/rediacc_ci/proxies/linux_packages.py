"""Port of `.ci/scripts/test/proxies/proxy-linux-packages.sh`.

Local proxy for the CI job "Tests + Infra / Linux Packages", wired as the registered gate `check:ci-proxy-linux-packages` (`package.json:385`, `scripts/ci-runner/manifest.ts`). See the twin's header for why `--dry-run` is the right reduction: phases 1 and 4 still do the REAL work (nfpm really builds all four package formats, build-pkg-repo.sh really generates APT/RPM/APK/Arch
metadata) and only the container-install and full-APT-flow phases become stubs.

The SUBJECT stays bash and is run as bash, exactly as the twin runs it. Only the proxy is ported, same division as `rediacc_ci.proxies.docker_prepull`.

-----------------------------------------------------------------------------
THE ANTI-VACUITY CHECK USED TO FAIL *OPEN*. FIXED 2026-09-10, IN BOTH TWINS
-----------------------------------------------------------------------------
`:132` is

    REAL=$((EXPECTED_TESTS - $(printf '%s\\n' "$BOTH" |
            grep -B1 -F -- "$DRY_MARKER" | grep -cE 'TEST: ' || true)))

so the count of "really executed" subtests is EXPECTED minus the number of `TEST: ` banners that sit immediately above a `[DRY-RUN] Would` line. Both the banner text and the stub text are LITERALS matched out of the subject's
RUNTIME OUTPUT.

THE DEFECT THAT WAS: an absent marker has two causes -- nothing was stubbed, or the string was renamed out from under this check -- and the output cannot tell them apart. Read from the output alone, a rename (`[DRY-RUN] Would` to `[dry-run] skipping`, say) turned the subtraction into `21 - 0`, and this REGISTERED gate printed

    PASS: 21 of 21 subtests really executed ...; 0 are dry-run stubs, 0 stub
    lines, 21 TEST banners

which is the strongest possible claim, made at the exact moment the evidence
for it disappeared, and it exited 0.

THE FIX, and it is the same corroboration `EXPECTED_TESTS` already had: the marker is looked up in the SUBJECT'S SOURCE before the subtraction is trusted (`:125-130`, `marker_sites` here). Zero sites in the source is a LOUD refusal naming the marker, the file, what was expected and what was found -- never a pass -- and the surviving PASS line now prints the corroborated site count
beside the runtime numbers, so a reader sees the shape rather than a verdict. An absent marker WITH sites still present in the source stays a legitimate "everything ran for real", which is the direction that must not become a red.

BLAST RADIUS BEFORE THE FIX: one gate, one line, and only on a rename of a string that lives in one file, so ZERO real packages were affected -- measured before and after, `grep -cF '[DRY-RUN] Would' .ci/scripts/test/test-linux-packages.sh` is 7 both times and the live run still reports `10 of 21`. This was robustness against a future rename, not a live false green. Pinned in BOTH
directions by `test_proxies_linux_packages.py::test_a_renamed_dry_run_marker_is_now_a_loud_ refusal` (must fire) and `::test_a_present_marker_with_no_stub_lines_is_not_a_ refusal` (must NOT fire).

-----------------------------------------------------------------------------
nfpm IS RESOLVED BEFORE THE PREFLIGHT, AND THAT ORDER IS LOAD-BEARING
-----------------------------------------------------------------------------
`:46-49` runs `ensure-nfpm.sh` when nfpm is not already on PATH and prepends what it printed, so a host with a warm `.ci/cache/bin/nfpm` (this one) reports one clear cannot-run instead of dying inside phase 1 with a bare "command not found". Both streams of that call are discarded and a failure is swallowed by `|| true`, so a broken ensure-nfpm.sh says nothing here and surfaces
only as the `nfpm is not on PATH` requirement. Reproduced as written.

The prepend mutates `os.environ["PATH"]` rather than a local copy, because the
bash `export PATH=` is seen by BOTH `command -v nfpm` in the preflight and the
subject subprocess below it.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-linux-packages.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys

from rediacc_ci.core import proxyx

SUBJECT_REL = ".ci/scripts/test/test-linux-packages.sh"

# `grep -cE '^run_test "'` (:60). Anchored, so a `run_test` nested in an `if` does not count -- which is the twin's behaviour and therefore this one's.
RUN_TEST_RE = re.compile(r'^run_test "')

# `grep -oE 'Results: [0-9]+ passed, [0-9]+ failed \(total [0-9]+\)'` (:89).
RESULTS_RE = re.compile(r"Results: ([0-9]+) passed, ([0-9]+) failed \(total ([0-9]+)\)")

# `grep -cE 'TEST: '` (:127) and `grep -cF -- "$DRY_MARKER"` (:128). Both are literal; `DRY_MARKER` is the twin's own variable and this is the same string.
TEST_BANNER = "TEST: "
DRY_STUB = "[DRY-RUN] Would"


def _proxy_root() -> pathlib.Path:
    """`ROOT_DIR="$PROXY_DIR/../../../.."` (:29-30).

    Resolved from this file's own location, not `paths.repo_root()`, for the reason `rediacc_ci.proxies.ensure_nfpm._proxy_root` states: `repo_root()` honours $REDIACC_CI_ROOT and the twin has no such override.
    """
    return pathlib.Path(__file__).resolve().parents[3]


def expected_tests(subject_text: str) -> int:
    """`EXPECTED_TESTS=$(grep -cE '^run_test "' "$SUBJECT")` (:60).

    grep -c counts LINES with at least one match, never matches, so a line carrying two call sites counts once. Exported for the selftest.
    """
    return sum(1 for line in subject_text.splitlines() if RUN_TEST_RE.search(line))


def marker_sites(subject_text: str) -> int:
    """`MARKER_SITES=$(grep -cF -- "$DRY_MARKER" "$SUBJECT" || true)` (:126).

    The corroboration that makes the subtraction below mean anything: the stub marker must still EXIST in the subject for its absence from the output to read as "nothing was stubbed" rather than "it was renamed". `grep -c` counts LINES, so two call sites on one line count once, which is the twin's answer and therefore this one's. Exported for the selftest.
    """
    return sum(1 for line in subject_text.split("\n") if DRY_STUB in line)


def results_line(both: str) -> str:
    """`grep -oE '<results>' | tail -1` (:89). "" when the subject printed none."""
    found = RESULTS_RE.findall(both)
    if not found:
        return ""
    passed, failed, total = found[-1]
    return f"Results: {passed} passed, {failed} failed (total {total})"


def count_lines(both: str, needle: str) -> int:
    """`printf '%s\\n' "$BOTH" | grep -c <needle>`.

    `printf '%s\\n'` appends exactly one newline to a value whose own trailing newlines the `$( )` already stripped, so the line set is `both.split("\\n")` -- an EMPTY `both` is therefore ONE empty line, not zero lines. It matches nothing here either way, but the shape is the twin's.
    """
    return sum(1 for line in both.split("\n") if needle in line)


def banners_above_stubs(both: str) -> int:
    """The inner half of `:132`: `grep -B1 -F -- "$DRY_MARKER" | grep -cE 'TEST: '`.

    `-B1` emits each matching line plus at most one preceding line that has not already been emitted, and `--` group separators between non-adjacent runs. The separators carry no `TEST: ` so they cannot change the count, and a line already emitted as a match is never re-emitted as context, so the emitted SET is what matters and is what this computes.
    """
    lines = both.split("\n")
    emitted: set[int] = set()
    for i, line in enumerate(lines):
        if DRY_STUB in line:
            emitted.add(i)
            if i > 0:
                emitted.add(i - 1)
    return sum(1 for i in sorted(emitted) if TEST_BANNER in lines[i])


def run() -> int:
    root = _proxy_root()
    subject = str(root / SUBJECT_REL)

    p = proxyx.Proxy("linux-packages", f"{SUBJECT_REL} --dry-run")

    # :46-49. Both streams discarded, `|| true` swallows a failure, and the trailing newline of the printed directory is stripped by `$( )`.
    if shutil.which("nfpm") is None:
        proc = subprocess.run(
            [str(root / ".ci" / "scripts" / "build" / "ensure-nfpm.sh")],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        # `$( ... || true )` captures whatever was printed REGARDLESS of the exit status: `|| true` only rewrites the substitution's own status, which nothing here reads. So a subject that printed a directory and then failed still has its directory used, exactly as in bash.
        nfpm_dir = proc.stdout.rstrip("\n")
        if nfpm_dir:
            os.environ["PATH"] = f"{nfpm_dir}:{os.environ.get('PATH', '')}"

    p.need_exec(subject, "the subject script is missing from this checkout")
    p.need_cmd("nfpm", ".ci/scripts/build/ensure-nfpm.sh (needs network on first run)")
    p.need_cmd("dpkg-deb", "sudo apt-get install -y dpkg-dev")
    p.need_cmd("rpmbuild", "sudo apt-get install -y rpm")
    p.need_cmd("createrepo_c", "sudo apt-get install -y createrepo-c")
    p.need_cmd("gpg", "sudo apt-get install -y gnupg")
    p.preflight()

    # :60-67. The corpus-derived expectation, and the refusal when it collapses.
    n_expected = expected_tests(pathlib.Path(subject).read_text(encoding="utf-8"))
    if n_expected == 0:
        red, off = p._c(proxyx.RED), p._c(proxyx.OFF)
        print(
            f"{red}proxy linux-packages: found ZERO run_test call sites in the subject{off}",
            file=sys.stderr,
        )
        print(
            "  The expectation is derived from the subject and the derivation collapsed,",
            file=sys.stderr,
        )
        print(
            "  so any comparison against it would be vacuous. Check the grep in this file",
            file=sys.stderr,
        )
        print(f"  against {subject}.", file=sys.stderr)
        return 1

    # :73-77. Streams read SEPARATELY: the subject writes its log_* lines to stderr and nfpm's own chatter to stdout, so a merged capture hides which
    # side spoke. `BOTH="$(cat "$OUT" "$ERR")"` concatenates them in that order
    # and the `$( )` strips the trailing newlines of the pair.
    sub = subprocess.run([subject, "--dry-run"], capture_output=True, text=True, check=False)
    rc = sub.returncode
    both = (sub.stdout + sub.stderr).rstrip("\n")

    if rc == 0:
        p.ok("test-linux-packages.sh --dry-run exited 0")
    else:
        p.bad(f"test-linux-packages.sh --dry-run exited {rc}")
        print("  --- subject stdout (last 30) ---", file=sys.stderr)
        _tail(sub.stdout, 30)
        print("  --- subject stderr (last 30) ---", file=sys.stderr)
        _tail(sub.stderr, 30)

    line = results_line(both)
    if not line:
        p.bad(
            "the subject printed no 'Results:' summary line, so nothing can be read from this run"
        )
    else:
        passed, failed, total = (int(x) for x in RESULTS_RE.search(line).groups())
        if total == n_expected:
            p.ok(
                f"ran all {n_expected} subtests the subject declares "
                "(corpus-derived, not hand-typed)"
            )
        else:
            p.bad(
                f"subject declares {n_expected} run_test call sites but reported total "
                f"{total}; a phase was skipped or added without this proxy noticing"
            )

        if failed == 0:
            p.ok(f"0 subtest failures ({passed} passed)")
        else:
            p.bad(f"{failed} subtest(s) failed")

    # :110-138. The anti-vacuity check, corroborated against the subject's SOURCE before the subtraction is trusted; see this module's docstring.
    sites = marker_sites(pathlib.Path(subject).read_text(encoding="utf-8"))
    stubbed = count_lines(both, TEST_BANNER)
    drystub = count_lines(both, DRY_STUB)
    if sites == 0:
        p.bad(
            f"VACUOUS: the dry-run stub marker '{DRY_STUB}' appears 0 times in "
            f"{SUBJECT_REL}, so the stub count below is derived from nothing. "
            "Expected: at least one call site in the subject printing that marker. "
            "Found: none, which means it was renamed, and the subtraction would then "
            f"read all {n_expected} subtests as really executed. Re-derive the marker "
            "from the subject's dry-run branch; do not delete this check and do not "
            "allowlist the subject."
        )
    else:
        real = n_expected - banners_above_stubs(both)
        if real > 0:
            p.ok(
                f"{real} of {n_expected} subtests really executed (nfpm build + repo "
                f"metadata); {n_expected - real} are dry-run stubs, {drystub} stub lines, "
                f"{stubbed} TEST banners, marker corroborated at {sites} site(s) in the "
                "subject"
            )
        else:
            p.bad("every subtest was a dry-run stub; this run asserted nothing about packaging")

    return p.finish()


def _tail(text: str, n: int) -> None:
    for line in text.splitlines()[-n:]:
        print(line, file=sys.stderr)


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        return proxyx.run_selftest()
    return run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
