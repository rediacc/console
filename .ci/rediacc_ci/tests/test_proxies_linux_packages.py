"""`rediacc_ci.proxies.linux_packages` against its bash twin `.ci/scripts/test/proxies/proxy-linux-packages.sh` (gate `check:ci-proxy-linux-packages`, `package.json:385`).

Sibling of `test_proxies_ensure_nfpm.py`; see that file for why the two invocations are compared byte for byte rather than as a finding set.

MOST CASES BUILD NO PACKAGES. Only `test_real_tree_agrees_byte_for_byte` runs the genuine `rediacc_ci.testrun.linux_packages --dry-run` (nfpm really builds four formats, build-pkg-repo.sh really generates APT/RPM/APK/Arch metadata, ~1 s on this host). The rest run against a fixture root whose SUBJECT is a stub with the same SHAPE -- `plan()` entries, `TEST: ` banners on stderr,
`[DRY-RUN] Would` stub lines, a `Results:` summary -- which is the only way to drive the marker-rename defect at all: the real subject cannot be asked to rename its own stub text.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-linux-packages.observations.jsonl` (6 rows,
6 distinct trees, 5 distinct finding sets), re-recorded on 2026-09-10 after the marker-corroboration fix; the pre-fix rows were DISCARDED rather than appended to, because they record a verdict the code no longer gives.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.proxies import linux_packages
from rediacc_ci.tests import differential as diff

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/test/proxies/proxy-linux-packages.sh"
PORT_REL = ".ci/rediacc_ci/proxies/linux_packages.py"
PORT_MODULE = "rediacc_ci.proxies.linux_packages"
TWIN = ROOT / TWIN_REL

FIXTURE_FILES = (
    TWIN_REL,
    ".ci/scripts/test/proxies/proxy-lib.sh",
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/proxyx.py",
    ".ci/rediacc_ci/proxies/__init__.py",
    PORT_REL,
)

# The toolchain the twin's preflight declares (`:52-56`). Named here so the skip below reports which one is missing rather than a bare "cannot run".
NEEDED = ("dpkg-deb", "rpmbuild", "createrepo_c", "gpg")

# A stub SUBJECT with the real one's SHAPE and none of its cost: four entries in a `plan()` body (which is what the proxy derives its expectation
# from), `TEST: ` banners and `[DRY-RUN] Would` lines on stderr, and the
# `Results:` summary the proxy parses.
STUB_SUBJECT = """import sys

DRY = sys.argv[1:] == ["--dry-run"]
passed = failed = 0


def run_test(name, mode):
    global passed, failed
    print("TEST: " + name, file=sys.stderr)
    if mode == "stub" and DRY:
        print("MARKER " + name, file=sys.stderr)
    if mode == "boom":
        failed += 1
    else:
        passed += 1


def plan():
    return [
        ("one", "real"),
        ("two", "real"),
        ("three", "stub"),
        ("four", "stub"),
    ]


for entry in plan():
    run_test(*entry)
print("Results: %d passed, %d failed (total %d)" % (passed, failed, passed + failed), file=sys.stderr)
raise SystemExit(0 if failed == 0 else 1)
"""

# A stub ensure_nfpm.py, so the fixture never reaches the network. The proxy calls it whenever nfpm is not already on PATH, which on this host it is not.
STUB_ENSURE_NFPM = """import pathlib

d = pathlib.Path(__file__).resolve().parents[3] / ".ci" / "cache" / "bin"
d.mkdir(parents=True, exist_ok=True)
(d / "nfpm").write_text('#!/bin/bash\\necho "nfpm version 2.45.0"\\n', encoding="utf-8")
(d / "nfpm").chmod(0o755)
print(d)
"""


def _missing() -> list[str]:
    return [c for c in NEEDED if shutil.which(c) is None]


pytestmark = pytest.mark.skipif(
    bool(_missing()),
    reason=f"packaging toolchain absent ({', '.join(_missing())}); both sides would "
    "report 77, proving nothing",
)


def build_fixture(
    tmp_path: pathlib.Path,
    *,
    subject: str = STUB_SUBJECT,
    port_source: str | None = None,
) -> pathlib.Path:
    fixture = tmp_path / "fixture"
    for rel in FIXTURE_FILES:
        dst = fixture / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not (ROOT / rel).exists():
            continue  # the retired twin and its library: only a recording run copies them
        dst.write_bytes((ROOT / rel).read_bytes())
    if (fixture / TWIN_REL).exists():
        (fixture / TWIN_REL).chmod(0o755)
    if port_source is not None:
        (fixture / PORT_REL).write_text(port_source, encoding="utf-8")
    subj = fixture / linux_packages.SUBJECT_REL
    subj.parent.mkdir(parents=True, exist_ok=True)
    (subj.parent / "__init__.py").write_text("", encoding="utf-8")
    subj.write_text(subject, encoding="utf-8")
    ensure = fixture / linux_packages.ENSURE_NFPM_REL
    ensure.parent.mkdir(parents=True, exist_ok=True)
    ensure.write_text(STUB_ENSURE_NFPM, encoding="utf-8")
    return fixture


def _env(fixture: pathlib.Path, path: str | None = None) -> dict[str, str]:
    return {
        "PATH": path if path is not None else os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(fixture / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def run_both(
    fixture: pathlib.Path, *args: str, path: str | None = None
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
    env = _env(fixture, path)
    kwargs: diff.RunKwargs = {"env": env, "cwd": str(fixture), "capture_output": True, "text": True}

    def port_side() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", "-m", PORT_MODULE, *args], timeout=300, check=False, **kwargs
        )

    def port_streams() -> tuple[int, str, str]:
        proc = port_side()
        return proc.returncode, proc.stdout, proc.stderr

    def retired_bash() -> tuple[int, str, str]:
        raise RuntimeError("proxy-linux-packages.sh is retired; only its golden answers")

    # The bash proxy is retired, so its answer comes from the golden. A case whose output names the subject was re-recorded from the port after the subject moved to the Python module (Rule T, PLAN-retire-bash-oracles).
    rc, out, err = diff.twin_call(
        TWIN_REL,
        [repr(["bash", str(fixture / TWIN_REL), *args])],
        retired_bash,
        port=port_streams,
        work=(fixture.parent,),
    )
    old = subprocess.CompletedProcess([], rc, out, err)
    return old, port_side()


def assert_same(
    old: subprocess.CompletedProcess[str], new: subprocess.CompletedProcess[str]
) -> None:
    assert new.returncode == old.returncode, "exit: twin %s, port %s (%r)" % (
        old.returncode,
        new.returncode,
        old.stderr,
    )
    assert new.stdout == old.stdout
    assert new.stderr == old.stderr


def _bin_without(tmp_path: pathlib.Path, drop: str) -> str:
    """A PATH directory carrying every tool this fixture needs EXCEPT one."""
    d = tmp_path / f"bin-no-{drop}"
    d.mkdir(exist_ok=True)
    for tool in (
        "bash",
        "sh",
        "env",
        "python3",
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
        *NEEDED,
    ):
        if tool == drop:
            continue
        src = shutil.which(tool)
        if src and not (d / tool).exists():
            (d / tool).symlink_to(src)
    return str(d)


# --------------------------------------------------------------------------- The real tree ---------------------------------------------------------------------------


def _real_tree_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def test_selftest_is_byte_identical() -> None:
    kwargs: diff.RunKwargs = {
        "env": _real_tree_env(),
        "cwd": str(ROOT),
        "capture_output": True,
        "text": True,
    }
    old = diff.twin_result(
        TWIN_REL,
        [repr(["bash", str(TWIN), "--selftest"])],
        lambda: subprocess.run(
            ["bash", str(TWIN), "--selftest"], timeout=180, check=False, **kwargs
        ),
        work=(),
    )
    new = subprocess.run(
        ["python3", "-m", PORT_MODULE, "--selftest"], timeout=180, check=False, **kwargs
    )
    assert old.returncode == 0, old.stderr
    assert "proxy-lib selftest: 4 case(s) passed" in old.stdout
    assert (new.returncode, new.stdout, new.stderr) == (old.returncode, old.stdout, old.stderr)


def test_real_tree_passes_through_the_port() -> None:
    """The only case that really builds packages. The bash twin it was compared with is retired (PLAN-retire-bash-oracles B3)."""
    kwargs: diff.RunKwargs = {
        "env": _real_tree_env(),
        "cwd": str(ROOT),
        "capture_output": True,
        "text": True,
    }
    new = subprocess.run(["python3", "-m", PORT_MODULE], timeout=600, check=False, **kwargs)
    assert new.returncode == 0, new.stderr
    assert "4 check(s) passed, 6 requirement(s) present" in new.stdout
    assert "subtests really executed" in new.stdout


# --------------------------------------------------------------------------- Fixture cases: no packaging, no network ---------------------------------------------------------------------------


def test_a_stub_subject_reports_its_real_versus_stubbed_split(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path, subject=STUB_SUBJECT.replace("MARKER", "[DRY-RUN] Would"))
    old, new = run_both(fixture)
    assert old.returncode == 0, old.stderr
    assert "ran all 4 subtests the subject declares" in old.stdout
    assert "2 of 4 subtests really executed" in old.stdout
    assert "2 are dry-run stubs, 2 stub lines, 4 TEST banners" in old.stdout
    assert_same(old, new)


def test_the_banner_names_the_python_subject_not_the_retired_bash_one(
    tmp_path: pathlib.Path,
) -> None:
    """RULE T: the proxy drives `rediacc_ci.testrun.linux_packages`, the module CI runs. The retired bash proxy announced `test-linux-packages.sh`, a file that no longer exists."""
    fixture = build_fixture(tmp_path, subject=STUB_SUBJECT.replace("MARKER", "[DRY-RUN] Would"))
    _old, new = run_both(fixture)
    assert (
        "proxy linux-packages: local stand-in for "
        ".ci/rediacc_ci/testrun/linux_packages.py --dry-run\n" in new.stdout
    )
    assert "test-linux-packages.sh" not in new.stdout + new.stderr


def test_a_failing_subtest_is_reported_by_both_sides(tmp_path: pathlib.Path) -> None:
    subject = STUB_SUBJECT.replace("MARKER", "[DRY-RUN] Would").replace(
        '("two", "real")', '("two", "boom")'
    )
    fixture = build_fixture(tmp_path, subject=subject)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "1 subtest(s) failed" in old.stderr
    assert_same(old, new)


def test_zero_run_test_call_sites_is_refused_not_passed(tmp_path: pathlib.Path) -> None:
    """The corpus-derived expectation collapsing must be LOUD, never a pass."""
    subject = STUB_SUBJECT.replace("MARKER", "[DRY-RUN] Would").replace(
        '\n        ("', '\n        # ("'
    )
    fixture = build_fixture(tmp_path, subject=subject)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "found ZERO run_test call sites in the subject" in old.stderr
    assert "would be vacuous" in old.stderr
    assert_same(old, new)


def test_no_summary_line_is_a_finding_not_a_pass(tmp_path: pathlib.Path) -> None:
    subject = STUB_SUBJECT.replace("MARKER", "[DRY-RUN] Would").replace("Results: ", "Totals: ")
    fixture = build_fixture(tmp_path, subject=subject)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "printed no 'Results:' summary line" in old.stderr
    assert_same(old, new)


def test_a_missing_toolchain_is_77_not_a_verdict(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path, subject=STUB_SUBJECT.replace("MARKER", "[DRY-RUN] Would"))
    old, new = run_both(fixture, path=_bin_without(tmp_path, "rpmbuild"))
    assert old.returncode == 77
    assert "CANNOT RUN" in old.stderr
    assert "rpmbuild is not on PATH" in old.stderr
    assert_same(old, new)


# --------------------------------------------------------------------------- THE DEFECT THAT WAS: the anti-vacuity check failed OPEN. FIXED 2026-09-10.
#
# BOTH DIRECTIONS, because a refusal with only a positive control would red every legitimate run in which nothing happened to be stubbed. ---------------------------------------------------------------------------


def test_a_renamed_dry_run_marker_is_now_a_loud_refusal(
    tmp_path: pathlib.Path,
) -> None:
    """MUST FIRE. `:132` subtracts a count of a LITERAL that lives in the subject.

    Before 2026-09-10 a rename turned the subtraction into `N - 0`, so the proxy reported the STRONGEST possible coverage claim -- "4 of 4 subtests really executed", "0 stub lines" -- at the exact moment its evidence disappeared, and exited 0. `:126` now corroborates the marker against the subject's SOURCE first, so the rename is a named refusal on both sides.
    """
    fixture = build_fixture(tmp_path, subject=STUB_SUBJECT.replace("MARKER", "[dry-run] skipping"))
    old, new = run_both(fixture)
    assert old.returncode == 1, "the rename must not be able to exit 0 any more"
    assert "VACUOUS: the dry-run stub marker '[DRY-RUN] Would' appears 0 times" in old.stderr
    assert ".ci/rediacc_ci/testrun/linux_packages.py" in old.stderr
    assert "which means it was renamed" in old.stderr
    # And the claim it used to make is GONE, not merely accompanied by a red.
    assert "4 of 4 subtests really executed" not in old.stdout
    assert_same(old, new)


def test_a_present_marker_with_no_stub_lines_is_not_a_refusal(
    tmp_path: pathlib.Path,
) -> None:
    """MUST NOT FIRE. The corroboration reads the SOURCE, never the output.

    A run in which every subtest did real work prints no `[DRY-RUN] Would` line at all, and that is the strongest possible outcome, not a defect. The marker is still in the subject's source, so the refusal above stays silent and the PASS line reports the corroborated site count.
    """
    subject = (
        STUB_SUBJECT.replace("MARKER", "[DRY-RUN] Would")
        .replace('("three", "stub")', '("three", "real")')
        .replace('("four", "stub")', '("four", "real")')
    )
    assert "[DRY-RUN] Would" in subject, "the marker must survive in the SOURCE"
    fixture = build_fixture(tmp_path, subject=subject)
    old, new = run_both(fixture)
    assert old.returncode == 0, old.stderr
    assert "VACUOUS" not in old.stderr
    assert "4 of 4 subtests really executed" in old.stdout
    assert "0 stub lines" in old.stdout
    assert "marker corroborated at 1 site(s) in the subject" in old.stdout
    assert_same(old, new)


def test_the_surviving_pass_line_prints_the_corroborated_shape(
    tmp_path: pathlib.Path,
) -> None:
    """ "OK" hides a collapse; the numbers beside it do not."""
    fixture = build_fixture(tmp_path, subject=STUB_SUBJECT.replace("MARKER", "[DRY-RUN] Would"))
    old, new = run_both(fixture)
    assert old.returncode == 0, old.stderr
    assert (
        "2 of 4 subtests really executed (nfpm build + repo metadata); 2 are dry-run "
        "stubs, 2 stub lines, 4 TEST banners, marker corroborated at 1 site(s) in the "
        "subject"
    ) in old.stdout
    assert_same(old, new)


# --------------------------------------------------------------------------- The planted defect: this differential must be able to go RED ---------------------------------------------------------------------------


def test_a_planted_defect_in_the_port_is_caught(tmp_path: pathlib.Path) -> None:
    """A control that never fires is a claim about the control, not the port.

    The plant drops the `-B1` context line from `banners_above_stubs`, which turns `10 of 21` into `21 of 21` on the port side alone. If this passes without the plant, every green above means nothing.
    """
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    planted = source.replace("            if i > 0:\n                emitted.add(i - 1)\n", "", 1)
    assert planted != source, "the -B1 context line moved; re-aim the plant"

    subject = STUB_SUBJECT.replace("MARKER", "[DRY-RUN] Would")
    good = build_fixture(tmp_path / "good", subject=subject)
    old_g, new_g = run_both(good)
    assert_same(old_g, new_g)

    bad = build_fixture(tmp_path / "bad", subject=subject, port_source=planted)
    # The expected answer is the unplanted one, already read above for the same subject and arguments.
    old_b = old_g
    new_b = subprocess.run(
        ["python3", "-m", PORT_MODULE],
        timeout=300,
        check=False,
        env=_env(bad),
        cwd=str(bad),
        capture_output=True,
        text=True,
    )
    assert old_b.stdout != new_b.stdout, "THE PLANT DID NOT FIRE"
    assert "2 of 4 subtests really executed" in old_b.stdout
    assert "4 of 4 subtests really executed" in new_b.stdout


# --------------------------------------------------------------------------- The pure helpers, driven directly ---------------------------------------------------------------------------


def test_expected_tests_counts_lines_not_matches() -> None:
    head = "def other():\n    return [(1, 2)]\n\n\ndef plan(s):\n    return [\n"
    tail = '    ]\n\n\ndef later():\n    return [\n        ("z", 3),\n    ]\n'
    assert (
        linux_packages.expected_tests(head + '        ("a", 1),\n        ("b", 2),\n' + tail) == 2
    )
    # Anchored: a deeper-indented entry does not count.
    assert linux_packages.expected_tests(head + '            ("a", 1),\n' + tail) == 0
    # One line, two entries, still ONE line.
    assert linux_packages.expected_tests(head + '        ("a", 1), ("b", 2),\n' + tail) == 1
    # Only the plan() body is read: entries of later functions do not count.
    assert linux_packages.expected_tests(head + tail) == 0
    assert linux_packages.expected_tests("") == 0


def test_marker_sites_counts_lines_in_the_subject_source() -> None:
    """The corroboration helper, driven directly in both directions."""
    assert linux_packages.marker_sites('echo "[DRY-RUN] Would do it"\n') == 1
    # grep -c counts LINES, so two sites on one line count once.
    assert linux_packages.marker_sites("a [DRY-RUN] Would b [DRY-RUN] Would c\n") == 1
    assert linux_packages.marker_sites("[DRY-RUN] Would a\n[DRY-RUN] Would b\n") == 2
    # MUST be zero for the rename, which is the whole refusal.
    assert linux_packages.marker_sites('echo "[dry-run] skipping it"\n') == 0
    assert linux_packages.marker_sites("") == 0


def test_results_line_takes_the_last_match() -> None:
    text = "Results: 1 passed, 0 failed (total 1)\nResults: 9 passed, 2 failed (total 11)"
    assert linux_packages.results_line(text) == "Results: 9 passed, 2 failed (total 11)"
    assert linux_packages.results_line("nothing here") == ""


def test_banners_above_stubs_matches_grep_b1() -> None:
    text = (
        "TEST: one\n"
        "did real work\n"
        "TEST: two\n"
        "[DRY-RUN] Would two\n"
        "TEST: three\n"
        "[DRY-RUN] Would three\n"
        "[DRY-RUN] Would three again"
    )
    # `two` and `three` each have a banner directly above a stub line; the SECOND stub line for `three` re-emits nothing new.
    assert linux_packages.banners_above_stubs(text) == 2
    assert linux_packages.banners_above_stubs("no stubs at all") == 0


def test_count_lines_treats_an_empty_body_as_one_empty_line() -> None:
    assert linux_packages.count_lines("", "TEST: ") == 0
    assert linux_packages.count_lines("TEST: a\nTEST: b", "TEST: ") == 2
