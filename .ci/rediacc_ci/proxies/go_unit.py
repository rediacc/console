"""Port of `.ci/scripts/test/proxies/proxy-go-unit.sh`.

Local proxy for the renet Go unit tests, the heaviest single leg of CI's
test-renet job, wired as the registered gate `check:ci-proxy-go-unit`
(`package.json:388`). CI runs `sudo -E gotestsum -- -v -race -coverprofile=...
./pkg/... ./cmd/...` under root; none of that is in the parity surface, so a
developer's local run has never compiled a single renet test.

The subset is DERIVED on every run, never typed, and the excluded set is
PRINTED BY NAME: it is real debt (those tests run only in CI) and a quiet
exemption is how a gate stops meaning what its name says. What this proxy
therefore does NOT prove is stated in the twin's header and unchanged here: no
race detector, no root paths, no subscription e2e.

-----------------------------------------------------------------------------
THE EXCLUSION REGEX WAS WIDER THAN ITS OWN DOCUMENTATION. FIXED 2026-09-10,
BY CORRECTING THE DOCUMENTATION -- THE REGEX WAS RIGHT
-----------------------------------------------------------------------------
The twin's header used to say the excluded set was the packages "whose
_test.go files reference Geteuid, RequireRoot or the pkg/testutil PRIVILEGED
HELPERS (btrfs.go, luksext4.go)", while `:100` greps

    Geteuid|RequireRoot|requireRoot|testutil\\.

which excludes a directory on ANY reference to the testutil package, and on
`requireRoot` in lower case, which the header did not mention at all. Two
discrepancies, and both were in the DOCUMENT rather than in the code.

WHY THE WIDER MATCH IS THE CORRECT ONE, which is the judgement this fix rests
on. Narrowing to "privileged helpers" means classifying pkg/testutil's symbols
one by one -- `CreateLuksExt4Repo` and `RequireBtrfs` yes, `SHA256File`,
`NewSeededRng`, `MakePatch` and `FilesIdentical` no -- and that classification
can only live as a HAND-TYPED allowlist, the one thing this subset refuses to
be ("DERIVED on every run, never typed"). A typed list goes stale in the
HAZARDOUS direction: add a privileged helper to pkg/testutil, forget the list,
and an unprivileged developer box starts creating loop devices and LUKS
containers, which the twin's own header calls "not a test, it is a hazard".
Over-exclusion costs local coverage and is PRINTED BY NAME on every run;
under-exclusion costs a damaged workstation and prints nothing. So the
conservative direction wins and the comment was brought in line with it.

BLAST RADIUS, MEASURED BEFORE AND AFTER AND UNCHANGED BY THIS FIX: ZERO
packages. Nothing about the excluded set moved, because only a comment moved.
On this tree the fourth alternative matches five files
(pkg/chunkstore, pkg/delta x2, pkg/kubecsi, pkg/repodiff) that are a STRICT
SUBSET of the nine matched by `Geteuid|RequireRoot|requireRoot`, so all eight
excluded directories

    pkg/chunkstore  pkg/daemon  pkg/datastore  pkg/delta
    pkg/ebpf        pkg/kubecsi pkg/luks       pkg/repodiff

would be excluded without it. That measurement is now a TEST rather than a
sentence:
`test_proxies_go_unit.py::test_the_fourth_alternative_removes_nothing_extra_on_
the_real_tree`. The drift itself cannot recur silently either:
`::test_the_documented_predicate_matches_the_grep_character_for_character`
reads the pattern out of the twin's grep, requires the twin's header to quote
it verbatim, and requires `EXCLUDE_RE` below to equal it.

-----------------------------------------------------------------------------
THE FIFTH ALTERNATIVE, ADDED 2026-09-10: A REAL GAP, FOUND UNDER CI=true
-----------------------------------------------------------------------------
`pkg/storage` gates its root-only tests with plain `os.Getuid() != 0`
(`directory_test.go`, `luks_test.go`), an idiom none of the first four
alternatives catch -- it is neither `Geteuid` (a distinct, real Go function
this pattern must also ignore) nor `RequireRoot` nor `testutil.`. Locally,
with no `CI` env var, those tests just call `t.Skip` and this proxy silently
reported a clean pass over 11 tests it never really ran. Under `CI=true`
(what real CI sets, and what this port's own real-tree differential drives it
under), the same tests instead call `t.Fatalf("CI must run as root for LUKS
storage tests")`, and the whole package -- including its non-LUKS
`TestDirectoryStorage_*` cases, gated by the same idiom -- hard-failed this
gate. `pkg/repository` and `pkg/filesystem` use the identical guard and move
into the excluded set too; `pkg/daemon` was already excluded. Net: 68 -> 11
excluded, 57 in the subset (was 8 excluded, 60 in the subset). Pinned by
`test_a_getuid_only_package_is_now_excluded`.

-----------------------------------------------------------------------------
TWO SMALLER FIDELITIES WORTH NAMING
-----------------------------------------------------------------------------
`:108` is `grep -qx "$rel"`, not `grep -qxF`, so the relative directory is used
as a BASIC REGULAR EXPRESSION against the excluded list. Every path in that
list today is metacharacter-free (checked: none of the eleven contains any of
`.` `*` `[` `]` `^` `$` `\\`), so exact string equality is the same predicate
and is what `_is_excluded` uses. A directory named `pkg/v1.2` would diverge,
and that is recorded here rather than silently normalised.

`:117` is `printf '  - %s\\n' $EXCLUDED_DIRS`, UNQUOTED -- deliberate word
splitting so one line prints per directory. It also globs, which is why
`_print_excluded` splits on whitespace rather than on newlines: the bytes are
the same for these names and the shape is the twin's.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-go-unit.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

from rediacc_ci.core import proxyx

# `grep -rlE 'Geteuid|RequireRoot|requireRoot|testutil\.|Getuid'` (:116). Kept
# character-for-character equal to the twin's grep AND to the pattern its
# header quotes; see this module's docstring for why the fourth alternative
# is deliberately broader than "privileged" and why the fifth was added.
EXCLUDE_RE = re.compile(r"Geteuid|RequireRoot|requireRoot|testutil\.|Getuid")

GO_LIST_FORMAT = "{{.ImportPath}} {{len .TestGoFiles}} {{len .XTestGoFiles}} {{.Dir}}"


def _proxy_root() -> pathlib.Path:
    """`ROOT_DIR="$PROXY_DIR/../../../.."` (:63-64)."""
    return pathlib.Path(__file__).resolve().parents[3]


def candidates(listing: str) -> list[str]:
    """`printf '%s\\n' "$LIST" | awk '$2+$3>0'` (:97).

    awk splits on runs of whitespace and compares numerically, so a package
    with no test files of either kind drops out. A `.Dir` containing a space
    would shift the fields on BOTH sides identically, since `read -r ip _nt
    _nx dir` below takes the rest of the line into `dir`.
    """
    out = []
    for line in listing.split("\n"):
        fields = line.split()
        if len(fields) < 3:
            continue
        try:
            if int(fields[1]) + int(fields[2]) > 0:
                out.append(line)
        except ValueError:
            continue
    return out


def excluded_dirs(renet: pathlib.Path) -> list[str]:
    """`grep -rlE '<markers>' pkg/ --include='*_test.go' | xargs -r -n1 dirname | sort -u`.

    Relative to `renet`, exactly as the twin's `cd` makes them.
    """
    found: set[str] = set()
    pkg = renet / "pkg"
    if not pkg.is_dir():
        return []
    for path in pkg.rglob("*_test.go"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if EXCLUDE_RE.search(text):
            found.add(str(path.parent.relative_to(renet)))
    return sorted(found)


def _is_excluded(rel: str, excluded: list[str]) -> bool:
    """`printf '%s\\n' "$EXCLUDED_DIRS" | grep -qx "$rel"` (:108). See docstring."""
    return rel in excluded


def subset_of(cands: list[str], cwd: str, excluded: list[str]) -> list[str]:
    """`:104-112`. `read -r ip _nt _nx dir` then `rel="${dir#"$PWD"/}"`."""
    out: list[str] = []
    for line in cands:
        parts = line.split(None, 3)
        if not parts or not parts[0]:
            continue
        directory = parts[3] if len(parts) > 3 else ""
        rel = directory.removeprefix(f"{cwd}/")
        if excluded and _is_excluded(rel, excluded):
            continue
        out.append(parts[0])
    return out


def _count_lines(text: str, pattern: re.Pattern[str] | str) -> int:
    """`grep -c` over a FILE: lines, not matches."""
    lines = text.split("\n")
    if isinstance(pattern, str):
        return sum(1 for line in lines if pattern in line)
    return sum(1 for line in lines if pattern.search(line))


# `grep -cE '^(ok|---)'` (:148) and `grep -cE '^(ok|FAIL|\?)'` (:150).
OK_RE = re.compile(r"^(ok|---)")
REPORTED_RE = re.compile(r"^(ok|FAIL|\?)")


def run() -> int:
    root = _proxy_root()
    renet = root / "private" / "renet"

    p = proxyx.Proxy(
        "go-unit", "the ./pkg/... unit phase of private/renet/.ci/scripts/test/run-tests.sh"
    )
    p.need_cmd(
        "go", "./run.sh setup, or install the toolchain pinned in .devcontainer/toolchain.env"
    )
    p.need_file(str(renet / "go.mod"), "git submodule update --init private/renet")
    p.need_file(str(renet / "pkg"), "git submodule update --init private/renet")
    p.preflight()

    # `cd "$RENET_DIR" || exit 2` (:82). Every subprocess below gets cwd=renet
    # rather than this process chdir'ing, so a caller importing the module is
    # left where it was.
    if not renet.is_dir():
        return 2
    cwd = str(renet)
    env = dict(os.environ)
    env["GOTOOLCHAIN"] = env.get("GOTOOLCHAIN") or "auto"

    # :88. stderr discarded; `$( )` strips the trailing newlines.
    listing = subprocess.run(
        ["go", "list", "-f", GO_LIST_FORMAT, "./pkg/..."],
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    ).stdout.rstrip("\n")

    if not listing:
        yel, off = p._c(proxyx.YEL), p._c(proxyx.OFF)
        print(f"{yel}proxy go-unit: CANNOT RUN{off}", file=sys.stderr)
        print(f"  'go list ./pkg/...' produced nothing in {renet}.", file=sys.stderr)
        print("  fix: run 'go mod download' there once with network available.", file=sys.stderr)
        print(
            "  Exiting 77 (cannot-run). The renet unit tests were NOT exercised.", file=sys.stderr
        )
        return proxyx.PROXY_CANNOT_RUN

    cands = candidates(listing)
    cand_n = len(cands)
    excluded = excluded_dirs(renet)
    excl_n = len(excluded)
    subset = subset_of(cands, cwd, excluded)

    print(
        f"proxy go-unit: {cand_n} ./pkg/... package(s) have tests; "
        f"{excl_n} excluded as root-only; {len(subset)} in the subset"
    )
    if excl_n > 0:
        yel, off = p._c(proxyx.YEL), p._c(proxyx.OFF)
        print(f"{yel}proxy go-unit: NOT EXERCISED HERE (root-only, CI runs them under sudo):{off}")
        for word in " ".join(excluded).split():
            print(f"  - {word}")

    if not subset:
        red, off = p._c(proxyx.RED), p._c(proxyx.OFF)
        print(f"{red}proxy go-unit: the derived subset is EMPTY{off}", file=sys.stderr)
        print(
            "  Either go list saw no test files or the exclusion swallowed everything.",
            file=sys.stderr,
        )
        print(
            "  A run over zero packages exits 0 and proves nothing, so this is a failure.",
            file=sys.stderr,
        )
        return 1
    p.ok(f"derived a non-empty subset: {len(subset)} of {cand_n} packages with tests")

    sys.stdout.flush()
    proc = subprocess.run(
        ["go", "test", "-count=1", "-timeout", "300s", *subset],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    rc = proc.returncode

    if rc == 0:
        p.ok(f"go test exited 0 over {len(subset)} package(s)")
    else:
        p.bad(f"go test exited {rc}")
        print("  --- go test stdout (failures) ---", file=sys.stderr)
        # `grep -E '^(FAIL|---|\s+---)' "$OUT" >&2 || tail -40 "$OUT" >&2`: the
        # tail is the FALLBACK taken only when grep matched nothing at all.
        fail_re = re.compile(r"^(FAIL|---|\s+---)")
        hits = [line for line in proc.stdout.split("\n") if fail_re.search(line)]
        if hits:
            for line in hits:
                print(line, file=sys.stderr)
        else:
            for line in proc.stdout.splitlines()[-40:]:
                print(line, file=sys.stderr)
        print("  --- go test stderr (last 40) ---", file=sys.stderr)
        for line in proc.stderr.splitlines()[-40:]:
            print(line, file=sys.stderr)

    ok_n = _count_lines(proc.stdout, OK_RE)
    notests = _count_lines(proc.stdout, "no test files")
    reported = _count_lines(proc.stdout, REPORTED_RE)
    if reported == len(subset):
        p.ok(
            f"go test reported one result line per package ({reported} of {len(subset)}); "
            f"{ok_n} ok, {notests} with no test files"
        )
    else:
        p.bad(
            f"go test reported {reported} result line(s) for {len(subset)} package(s); "
            "packages went missing from the run"
        )

    return p.finish()


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        return proxyx.run_selftest()
    return run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
