"""`rediacc_ci.proxies.go_unit` against its bash twin
`.ci/scripts/test/proxies/proxy-go-unit.sh` (gate `check:ci-proxy-go-unit`,
`package.json:388`).

Sibling of `test_proxies_linux_packages.py`; see that file for why the two
invocations are compared byte for byte rather than as a finding set.

ONE CASE DRIVES THE REAL `private/renet` (57 packages, ~12 s per side with a
warm build cache -- was 60 before the fifth exclusion alternative). The rest
use a SYNTHETIC module with no external dependencies, because the real one is
947 MB and because the interesting branches -- an empty candidate set, an
exclusion that swallows everything, a package excluded on nothing but a
`testutil.` mention -- cannot be produced by asking the real tree nicely.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-go-unit.observations.jsonl`, re-recorded
2026-09-10 after the fifth (`Getuid`) exclusion alternative landed -- a real
gap this time, not only a documentation fix: `pkg/storage` (and the
`os.Getuid()`-gated `pkg/repository`, `pkg/filesystem`) used to sit in the
non-root subset and hard-fail under `CI=true`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.proxies import go_unit

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/test/proxies/proxy-go-unit.sh"
PORT_REL = ".ci/rediacc_ci/proxies/go_unit.py"
PORT_MODULE = "rediacc_ci.proxies.go_unit"
TWIN = ROOT / TWIN_REL
RENET = "private/renet"

FIXTURE_FILES = (
    TWIN_REL,
    ".ci/scripts/test/proxies/proxy-lib.sh",
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/proxyx.py",
    ".ci/rediacc_ci/proxies/__init__.py",
    PORT_REL,
)

GO_MOD = "module scratch/renet\n\ngo 1.22\n"

PLAIN = {
    f"{RENET}/pkg/alpha/alpha.go": "package alpha\n\nfunc A() int { return 1 }\n",
    f"{RENET}/pkg/alpha/alpha_test.go": (
        'package alpha\n\nimport "testing"\n\nfunc TestA(t *testing.T) '
        '{ if A() != 1 { t.Fatal("no") } }\n'
    ),
    f"{RENET}/pkg/beta/beta.go": "package beta\n\nfunc B() int { return 2 }\n",
    f"{RENET}/pkg/beta/beta_test.go": (
        'package beta\n\nimport "testing"\n\nfunc TestB(t *testing.T) '
        '{ if B() != 2 { t.Fatal("no") } }\n'
    ),
    f"{RENET}/pkg/notests/notests.go": "package notests\n\nfunc N() int { return 0 }\n",
}
# Genuinely privileged: the FIRST alternative of the exclusion grep.
PRIV = {
    f"{RENET}/pkg/priv/priv.go": "package priv\n\nfunc P() int { return 3 }\n",
    f"{RENET}/pkg/priv/priv_test.go": (
        'package priv\n\nimport (\n\t"os"\n\t"testing"\n)\n\nfunc TestP(t *testing.T) {\n'
        '\tif os.Geteuid() != 0 {\n\t\tt.Skip("root only")\n\t}\n}\n'
    ),
}
# THE OVER-EXCLUSION: no Geteuid, no RequireRoot, only a `testutil.` mention.
TU = {
    f"{RENET}/pkg/tu/tu.go": "package tu\n\nfunc T() int { return 4 }\n",
    f"{RENET}/pkg/tu/tu_test.go": (
        'package tu\n\nimport "testing"\n\n'
        "// A helper named testutil.TempDir would live here; the NAME alone is what\n"
        "// the exclusion grep sees, privileged or not.\n"
        'func TestT(t *testing.T) { _ = "testutil.TempDir"; if T() != 4 { t.Fatal("no") } }\n'
    ),
}
# THE FIFTH ALTERNATIVE'S OWN CLASS: `os.Getuid()`, the real idiom `pkg/storage`
# uses, matching neither `Geteuid` nor `RequireRoot` nor `testutil.`.
GU = {
    f"{RENET}/pkg/gu/gu.go": "package gu\n\nfunc G() int { return 5 }\n",
    f"{RENET}/pkg/gu/gu_test.go": (
        'package gu\n\nimport (\n\t"os"\n\t"testing"\n)\n\nfunc TestG(t *testing.T) {\n'
        '\tif os.Getuid() != 0 {\n\t\tt.Skip("root only")\n\t}\n}\n'
    ),
}

pytestmark = pytest.mark.skipif(
    shutil.which("go") is None,
    reason="go absent; both sides would report 77, proving nothing",
)


def build_fixture(
    tmp_path: pathlib.Path,
    *,
    files: dict[str, str] | None = None,
    go_mod: str = GO_MOD,
    port_source: str | None = None,
) -> pathlib.Path:
    fixture = tmp_path / "fixture"
    for rel in FIXTURE_FILES:
        dst = fixture / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((ROOT / rel).read_bytes())
    (fixture / TWIN_REL).chmod(0o755)
    if port_source is not None:
        (fixture / PORT_REL).write_text(port_source, encoding="utf-8")
    (fixture / RENET).mkdir(parents=True, exist_ok=True)
    (fixture / RENET / "go.mod").write_text(go_mod, encoding="utf-8")
    for rel, text in (files if files is not None else {**PLAIN, **PRIV, **TU}).items():
        dst = fixture / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")
    (fixture / RENET / "pkg").mkdir(parents=True, exist_ok=True)
    return fixture


def _env(fixture: pathlib.Path, path: str | None = None) -> dict[str, str]:
    home = fixture / ".home"
    home.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": path if path is not None else os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "LC_ALL": "C",
        "LANG": "C",
        "GOCACHE": str(fixture / ".gocache"),
        "GOFLAGS": "-mod=mod",
        "PYTHONPATH": str(fixture / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def run_both(
    fixture: pathlib.Path, *args: str, path: str | None = None
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
    env = _env(fixture, path)
    kwargs = {"env": env, "cwd": str(fixture), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(fixture / TWIN_REL), *args], timeout=600, check=False, **kwargs
    )
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE, *args], timeout=600, check=False, **kwargs
    )
    return old, new


def assert_same(
    old: subprocess.CompletedProcess[str], new: subprocess.CompletedProcess[str]
) -> None:
    assert new.returncode == old.returncode, "exit: twin %s, port %s (%r)" % (
        old.returncode,
        new.returncode,
        old.stderr,
    )
    assert new.stdout == old.stdout
    # `go test` prints a per-package wall time, and the two runs get different
    # ones. Everything else on the stream must match byte for byte.
    assert _mask(new.stderr) == _mask(old.stderr)


def _mask(text: str) -> str:
    return re.sub(r"[0-9]+\.[0-9]+s", "<t>", text)


def _bin_without(tmp_path: pathlib.Path, drop: str) -> str:
    d = tmp_path / f"bin-no-{drop}"
    d.mkdir(exist_ok=True)
    for tool in (
        "bash",
        "sh",
        "env",
        "python3",
        "go",
        "sed",
        "cat",
        "mktemp",
        "rm",
        "mkdir",
        "chmod",
        "dirname",
        "grep",
        "head",
        "tail",
        "printf",
        "cut",
        "tr",
        "sort",
        "wc",
        "awk",
        "xargs",
    ):
        if tool == drop:
            continue
        src = shutil.which(tool)
        if src and not (d / tool).exists():
            (d / tool).symlink_to(src)
    return str(d)


def _real_tree_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


# ---------------------------------------------------------------------------
# The real tree
# ---------------------------------------------------------------------------


def test_selftest_is_byte_identical() -> None:
    kwargs = {"env": _real_tree_env(), "cwd": str(ROOT), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(TWIN), "--selftest"], timeout=180, check=False, **kwargs
    )
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE, "--selftest"], timeout=180, check=False, **kwargs
    )
    assert old.returncode == 0, old.stderr
    assert "proxy-lib selftest: 4 case(s) passed" in old.stdout
    assert (new.returncode, new.stdout, new.stderr) == (old.returncode, old.stdout, old.stderr)


def test_real_tree_agrees_byte_for_byte() -> None:
    """The only case that compiles the real renet packages, and it does it twice."""
    kwargs = {"env": _real_tree_env(), "cwd": str(ROOT), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(TWIN)], timeout=1800, check=False, **kwargs
    )
    if old.returncode == 77:
        pytest.skip(f"the twin reports cannot-run here: {old.stderr.strip()[:200]}")
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE], timeout=1800, check=False, **kwargs
    )
    assert old.returncode == 0, old.stderr
    assert "3 check(s) passed, 3 requirement(s) present" in old.stdout
    assert "excluded as root-only" in old.stdout
    assert (new.returncode, new.stdout, _mask(new.stderr)) == (
        old.returncode,
        old.stdout,
        _mask(old.stderr),
    )


# ---------------------------------------------------------------------------
# Fixture cases over a synthetic module
# ---------------------------------------------------------------------------


def test_the_derived_subset_prints_its_whole_shape(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    old, new = run_both(fixture)
    assert old.returncode == 0, old.stderr
    assert "4 ./pkg/... package(s) have tests; 2 excluded as root-only; 2 in the subset" in (
        old.stdout
    )
    assert "  - pkg/priv\n  - pkg/tu\n" in old.stdout
    assert "one result line per package (2 of 2)" in old.stdout
    assert_same(old, new)


def test_a_testutil_only_package_is_excluded_by_both_sides(tmp_path: pathlib.Path) -> None:
    """The DELIBERATE breadth of `:100`, driven rather than argued.

    `pkg/tu` has no `Geteuid` and no `RequireRoot` -- only the string
    `testutil.` -- and the fourth alternative of the exclusion grep drops it
    anyway. Documented as intended rather than as debt since 2026-09-10: a
    per-symbol rule could only be a hand-typed allowlist, which goes stale in
    the direction that runs LUKS and loop-device tests unprivileged on a
    workstation. Over-exclusion is visible (the names are printed every run),
    under-exclusion is a hazard. On the real tree it removes NOTHING extra,
    which `test_the_fourth_alternative_removes_nothing_extra_on_the_real_tree`
    measures rather than asserts in prose.
    """
    with_tu = build_fixture(tmp_path / "with", files={**PLAIN, **TU})
    old_w, new_w = run_both(with_tu)
    assert "3 ./pkg/... package(s) have tests; 1 excluded as root-only; 2 in the subset" in (
        old_w.stdout
    )
    assert "  - pkg/tu\n" in old_w.stdout
    assert_same(old_w, new_w)

    # Remove only the `testutil.` mention: the very same package comes back.
    clean = dict(TU)
    clean[f"{RENET}/pkg/tu/tu_test.go"] = clean[f"{RENET}/pkg/tu/tu_test.go"].replace(
        "testutil.", "helper_"
    )
    without = build_fixture(tmp_path / "without", files={**PLAIN, **clean})
    old_o, new_o = run_both(without)
    assert "3 ./pkg/... package(s) have tests; 0 excluded as root-only; 3 in the subset" in (
        old_o.stdout
    )
    assert_same(old_o, new_o)


def test_no_test_files_at_all_is_an_empty_subset_refusal(tmp_path: pathlib.Path) -> None:
    files = {k: v for k, v in PLAIN.items() if not k.endswith("_test.go")}
    fixture = build_fixture(tmp_path, files=files)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "the derived subset is EMPTY" in old.stderr
    assert "exits 0 and proves nothing" in old.stderr
    assert_same(old, new)


def test_an_exclusion_that_swallows_everything_is_also_refused(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path, files={**PRIV, **TU})
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "2 ./pkg/... package(s) have tests; 2 excluded as root-only; 0 in the subset" in (
        old.stdout
    )
    assert "the derived subset is EMPTY" in old.stderr
    assert_same(old, new)


def test_a_planted_failing_test_is_reported_by_both_sides(tmp_path: pathlib.Path) -> None:
    files = dict(PLAIN)
    files[f"{RENET}/pkg/beta/beta_test.go"] = (
        'package beta\n\nimport "testing"\n\nfunc TestB(t *testing.T) '
        '{ t.Fatal("planted failure") }\n'
    )
    fixture = build_fixture(tmp_path, files=files)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "go test exited 1" in old.stderr
    assert "--- FAIL: TestB" in old.stderr
    assert_same(old, new)


def test_a_missing_go_is_77_not_a_verdict(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    old, new = run_both(fixture, path=_bin_without(tmp_path, "go"))
    assert old.returncode == 77
    assert "go is not on PATH" in old.stderr
    assert_same(old, new)


def test_a_go_list_that_produces_nothing_is_77_not_a_finding(tmp_path: pathlib.Path) -> None:
    """A cold module cache with no network is cannot-run, never a verdict."""
    fixture = build_fixture(tmp_path, go_mod="this is not a go.mod\n")
    old, new = run_both(fixture)
    assert old.returncode == 77
    assert "'go list ./pkg/...' produced nothing" in old.stderr
    assert "The renet unit tests were NOT exercised" in old.stderr
    assert_same(old, new)


# ---------------------------------------------------------------------------
# The planted defect: this differential must be able to go RED
# ---------------------------------------------------------------------------


def test_a_planted_defect_in_the_port_is_caught(tmp_path: pathlib.Path) -> None:
    """The plant narrows the exclusion regex to the two privileged markers.

    That is the change a well-meaning reader would make after seeing the
    over-exclusion documented above, and it is exactly what must NOT happen in
    a port: `pkg/tu` re-enters the subset on the new side only.
    """
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    planted = source.replace(
        'EXCLUDE_RE = re.compile(r"Geteuid|RequireRoot|requireRoot|testutil\\.|Getuid")',
        'EXCLUDE_RE = re.compile(r"Geteuid|RequireRoot|requireRoot|Getuid")',
        1,
    )
    assert planted != source, "EXCLUDE_RE moved; re-aim the plant"

    good = build_fixture(tmp_path / "good")
    old_g, new_g = run_both(good)
    assert_same(old_g, new_g)

    bad = build_fixture(tmp_path / "bad", port_source=planted)
    old_b, new_b = run_both(bad)
    assert old_b.stdout != new_b.stdout, "THE PLANT DID NOT FIRE"
    assert "2 excluded as root-only; 2 in the subset" in old_b.stdout
    assert "1 excluded as root-only; 3 in the subset" in new_b.stdout


def test_a_getuid_only_package_is_now_excluded(tmp_path: pathlib.Path) -> None:
    """The real gap found 2026-09-10: `os.Getuid()` matched none of the first
    four alternatives, so a package gated only by it (like the real
    `pkg/storage`) stayed in the subset and hard-failed under `CI=true`.
    """
    fixture = build_fixture(tmp_path, files={**PLAIN, **GU})
    old, new = run_both(fixture)
    assert old.returncode == 0, old.stderr
    assert "3 ./pkg/... package(s) have tests; 1 excluded as root-only; 2 in the subset" in (
        old.stdout
    )
    assert_same(old, new)


# ---------------------------------------------------------------------------
# The pure helpers
# ---------------------------------------------------------------------------


def test_candidates_keeps_only_packages_with_test_files() -> None:
    listing = "a 0 0 /x/a\nb 1 0 /x/b\nc 0 2 /x/c\nd 3 4 /x/d"
    assert go_unit.candidates(listing) == ["b 1 0 /x/b", "c 0 2 /x/c", "d 3 4 /x/d"]
    assert go_unit.candidates("") == []


def test_candidates_skips_a_line_awk_could_not_read() -> None:
    assert go_unit.candidates("only two") == []
    assert go_unit.candidates("a x y /x/a") == []


def test_subset_of_strips_the_cwd_prefix_and_honours_the_exclusion() -> None:
    cands = ["m/pkg/a 1 0 /w/pkg/a", "m/pkg/b 1 0 /w/pkg/b"]
    assert go_unit.subset_of(cands, "/w", ["pkg/b"]) == ["m/pkg/a"]
    # An empty exclusion list keeps everything, matching `[[ -n "$EXCLUDED_DIRS" ]]`.
    assert go_unit.subset_of(cands, "/w", []) == ["m/pkg/a", "m/pkg/b"]
    # A directory outside the cwd keeps its absolute path and matches nothing.
    assert go_unit.subset_of(["m/x 1 0 /other/x"], "/w", ["x"]) == ["m/x"]


def test_the_documented_predicate_matches_the_grep_character_for_character() -> None:
    """The anti-drift guard for the fix of 2026-09-10.

    The twin's header described a NARROWER predicate than its own grep for as
    long as anyone had read it, and a comment cannot go red on its own. So the
    pattern is read out of the grep, the header must quote it verbatim, and
    `EXCLUDE_RE` must equal it. Three places, one string.
    """
    text = TWIN.read_text(encoding="utf-8")
    grep_lines = [ln for ln in text.splitlines() if ln.startswith("EXCLUDED_DIRS=")]
    assert len(grep_lines) == 1, f"the exclusion grep moved: {grep_lines}"
    m = re.search(r"grep -rlE '([^']+)'", grep_lines[0])
    assert m, f"could not read the pattern out of {grep_lines[0]!r}"
    pattern = m.group(1)
    assert pattern == go_unit.EXCLUDE_RE.pattern, (
        f"the port and the twin disagree: {go_unit.EXCLUDE_RE.pattern!r} vs {pattern!r}"
    )
    quoted = [ln for ln in text.splitlines() if ln.startswith("#") and pattern in ln]
    assert quoted, (
        f"the twin's header does not quote its own predicate {pattern!r} verbatim; "
        "a paraphrase is exactly how the documentation drifted from the grep"
    )


def test_the_fourth_alternative_removes_nothing_extra_on_the_real_tree() -> None:
    r"""The measurement behind "blast radius: ZERO packages", re-run every time.

    `testutil\.` is the broad alternative. Today every directory it matches is
    already matched by `Geteuid|RequireRoot|requireRoot`, so the breadth costs
    no local coverage at all. If that stops being true, the cost stops being
    hypothetical and the trade-off in the twin's header needs re-arguing, so
    this reds rather than the sentence quietly going stale.
    """
    renet = ROOT / "private" / "renet"
    if not (renet / "pkg").is_dir():
        pytest.skip("private/renet is not checked out")
    narrow = re.compile(r"Geteuid|RequireRoot|requireRoot")
    broad = re.compile(r"testutil\.")
    fifth = re.compile(r"Getuid")
    narrow_dirs: set[str] = set()
    broad_dirs: set[str] = set()
    fifth_dirs: set[str] = set()
    seen = 0
    for path in (renet / "pkg").rglob("*_test.go"):
        text = path.read_text(encoding="utf-8", errors="replace")
        seen += 1
        rel = str(path.parent.relative_to(renet))
        if narrow.search(text):
            narrow_dirs.add(rel)
        if broad.search(text):
            broad_dirs.add(rel)
        if fifth.search(text):
            fifth_dirs.add(rel)
    assert seen > 0, "no _test.go files were scanned, so this measurement is vacuous"
    assert broad_dirs, "the broad alternative matched NOTHING, so the claim is vacuous"
    assert broad_dirs <= narrow_dirs, (
        "the fourth alternative now excludes packages the first three do not: "
        f"{sorted(broad_dirs - narrow_dirs)}. That is real lost local coverage; "
        "re-argue the trade-off in the twin's header rather than deleting this test."
    )
    # Unlike the fourth, the fifth is NOT a strict subset -- it is why it was
    # added. `pkg/storage`, `pkg/repository` and `pkg/filesystem` sit outside
    # the first four alternatives entirely and are real, measured gains.
    assert fifth_dirs - narrow_dirs - broad_dirs, (
        "the fifth alternative now adds NOTHING beyond the first four; if that "
        "is genuinely true the alternative is dead weight and this test should "
        "say so, not silently pass"
    )
    # The union is what the proxy actually excludes.
    assert set(go_unit.excluded_dirs(renet)) == narrow_dirs | broad_dirs | fifth_dirs


def test_the_real_trees_excluded_dirs_carry_no_regex_metacharacters() -> None:
    """`:83` is `grep -qx "$rel"`, not `-qxF`, so a metacharacter would diverge.

    This is the measurement that licenses `_is_excluded` using plain equality.
    Skipped when the submodule is absent rather than asserted vacuously.
    """
    renet = ROOT / "private" / "renet"
    if not (renet / "pkg").is_dir():
        pytest.skip("private/renet is not checked out")
    dirs = go_unit.excluded_dirs(renet)
    assert dirs, "the exclusion found NOTHING, so this check would be vacuous"
    bad = [d for d in dirs if any(ch in d for ch in ".*[]^$\\+?(){}|")]
    assert bad == [], f"a BRE metacharacter in an excluded path: {bad}"
