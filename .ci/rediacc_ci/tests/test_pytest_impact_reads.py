"""pytest_impact_reads: the strace stream, the attribution, the fold and both derivations (PLAN-ciquick-cpu W4.3).

Every rule has a test that makes it fire and a control that keeps it from firing everywhere: an attributor that put every read on one test file, or on none, would pass half of these and fail the other half.
"""

import json
import os
import pathlib
import signal
import subprocess
import sys
from typing import ClassVar

import pytest

from rediacc_ci.quality import pytest_impact_reads as pr

ROOT = "/r"
MARKS = "/m"
T1 = ".ci/rediacc_ci/tests/test_one.py"
T2 = ".ci/rediacc_ci/tests/test_two.py"


def mark(pid: int, rel: str) -> str:
    return '%d openat(AT_FDCWD</r>, "%s/%s", O_RDONLY|O_CREAT, 0600) = 5<%s/%s>' % (
        pid,
        MARKS,
        pr.marker_name(rel),
        MARKS,
        pr.marker_name(rel),
    )


def opened(pid: int, path: str, fd: int = 3) -> str:
    return '%d openat(AT_FDCWD</r>, "%s", O_RDONLY|O_CLOEXEC) = %d<%s>' % (pid, path, fd, path)


def feed(*lines: str) -> pr.Attributor:
    att = pr.Attributor(root=ROOT, marker_dir=MARKS)
    for line in lines:
        att.feed(line)
    return att


# --------------------------------------------------------------------------- the stream


def test_a_marker_attributes_the_reads_after_it_to_its_test_file():
    att = feed(
        opened(100, "/r/pyproject.toml"),
        mark(100, T1),
        opened(100, "/r/.ci/policy/a.json"),
        mark(100, T2),
        opened(100, "/r/.ci/policy/b.json"),
    )
    assert att.reads[T1] == {".ci/policy/a.json"}
    assert att.reads[T2] == {".ci/policy/b.json"}
    assert att.reads[pr.UNATTRIBUTED] == {"pyproject.toml"}, "start-up reads are nobody's"
    assert att.markers == 2


def test_control_without_markers_every_read_is_unattributed():
    att = feed(opened(100, "/r/.ci/policy/a.json"), opened(100, "/r/.ci/policy/b.json"))
    assert set(att.reads) == {pr.UNATTRIBUTED}
    assert att.markers == 0


def test_a_child_keeps_the_attribution_it_was_created_under():
    att = feed(
        '100 execve("/usr/bin/python3", ["python3"], 0x0 /* 3 vars */) = 0',
        mark(100, T1),
        "100 clone(child_stack=NULL, flags=CLONE_CHILD_CLEARTID|SIGCHLD, child_tidptr=0x7) = 101",
        mark(100, T2),
        opened(101, "/r/.claude/rediacc_hooks/guards/policy.json"),
        opened(100, "/r/.ci/policy/b.json"),
    )
    assert att.reads[T1] == {".claude/rediacc_hooks/guards/policy.json"}, (
        "the child's read moved with the parent's later marker"
    )
    assert att.reads[T2] == {".ci/policy/b.json"}


def test_a_thread_shares_its_group_attribution():
    att = feed(
        mark(100, T1),
        "100 clone3({flags=CLONE_VM|CLONE_FS|CLONE_FILES|CLONE_SIGHAND|CLONE_THREAD|CLONE_SYSVSEM, exit_signal=0}, 88) = 102",
        mark(100, T2),
        opened(102, "/r/.ci/policy/t.json"),
    )
    assert att.reads[T2] == {".ci/policy/t.json"}, "a thread kept a stale attribution"


def test_a_child_seen_before_its_clone_returns_is_held_then_attributed():
    att = feed(
        mark(100, T1),
        "100 clone(child_stack=NULL, flags=SIGCHLD <unfinished ...>",
        opened(103, "/r/.ci/policy/early.json"),
        "100 <... clone resumed>, child_tidptr=0x7) = 103",
        opened(103, "/r/.ci/policy/late.json"),
    )
    assert att.reads[T1] == {".ci/policy/early.json", ".ci/policy/late.json"}
    assert not att.unclaimed


def test_an_unfinished_open_is_joined_with_its_resumption():
    att = feed(
        mark(100, T1),
        '100 openat(AT_FDCWD</r>, "/r/.ci/policy/s.json", O_RDONLY <unfinished ...>',
        "100 <... openat resumed>) = 4</r/.ci/policy/s.json>",
    )
    assert att.reads[T1] == {".ci/policy/s.json"}


def test_reads_outside_the_root_and_failed_calls_are_dropped():
    att = feed(
        mark(100, T1),
        opened(100, "/usr/lib/python3/os.py"),
        opened(100, "/rx/not-the-root.json"),
        '100 openat(AT_FDCWD</r>, "/r/missing.json", O_RDONLY) = -1 ENOENT (No such file or directory)',
        "100 --- SIGCHLD {si_signo=SIGCHLD} ---",
    )
    assert pr.UNATTRIBUTED not in att.reads
    assert T1 not in att.reads, att.reads


def test_execve_and_chdir_resolve_relative_paths():
    att = feed(
        mark(100, T1),
        "100 clone(child_stack=NULL, flags=SIGCHLD) = 104",
        '104 chdir(".claude/hooks") = 0',
        '104 execve("./guard.sh", ["./guard.sh"], 0x0 /* 3 vars */) = 0',
    )
    assert att.reads[T1] == {".claude/hooks/guard.sh"}


def test_a_listing_is_kept_apart_from_reads():
    att = feed(mark(100, T1), "100 getdents64(3</r/.ci/policy>, 0x5 /* 4 entries */, 32768) = 112")
    assert att.lists[T1] == {".ci/policy"}
    assert T1 not in att.reads


def test_marker_names_round_trip():
    for rel in (T1, ".claude/rediacc_hooks/tests/test_x.py", pr.UNATTRIBUTED):
        assert pr.label_of_marker(pr.marker_name(rel)) == rel
    assert "/" not in pr.marker_name(T1)


# --------------------------------------------------------------------------- the tree and the fold

TREE = pr.Tree.of(
    [
        ("100644", p)
        for p in (
            "docs/a.md",
            "docs/b.md",
            ".ci/policy/one.json",
            ".ci/policy/two.json",
            ".ci/policy/three.json",
            ".ci/policy/four.json",
            ".ci/rediacc_ci/__init__.py",
            ".ci/rediacc_ci/leaf.py",
            T1,
            T2,
            ".ci/rediacc_ci/tests/conftest.py",
            "pyproject.toml",
        )
    ]
    + [("160000", "private/renet")]
)


def test_tracked_maps_a_submodule_read_to_its_gitlink_and_drops_git_metadata():
    assert TREE.tracked("private/renet/go.mod") == "private/renet"
    assert TREE.tracked(".ci/policy/one.json") == ".ci/policy/one.json"
    assert TREE.tracked(".git/HEAD") is None
    assert TREE.tracked("private/renet/.git/config") is None
    assert TREE.tracked(".ci/cache/x.json") is None, "an untracked cache counted as an input"


def test_fold_takes_a_mostly_read_directory_whole():
    got = pr.fold([".ci/policy/one.json", ".ci/policy/two.json", ".ci/policy/three.json"], TREE)
    assert got == [".ci/policy/**"]


def test_control_fold_keeps_half_a_directory_exact():
    got = pr.fold([".ci/policy/one.json", ".ci/policy/two.json"], TREE)
    assert got == [".ci/policy/one.json", ".ci/policy/two.json"]


def test_control_fold_never_takes_a_small_directory():
    assert pr.fold(["docs/a.md", "docs/b.md"], TREE) == ["docs/a.md", "docs/b.md"]


# --------------------------------------------------------------------------- the derivations

MAP = {
    "tests": {
        T1: {"closure": [T1, ".ci/rediacc_ci/__init__.py", ".ci/rediacc_ci/leaf.py"]},
        T2: {"closure": [T2]},
    }
}


def test_derive_reads_keeps_data_and_drops_the_closure_and_full_triggers():
    tr = {
        "tests": {
            T1: {
                "reads": [
                    ".ci/rediacc_ci/leaf.py",
                    ".ci/rediacc_ci/tests/conftest.py",
                    "pyproject.toml",
                    ".ci/policy/one.json",
                    ".ci/cache/scratch.json",
                ],
                "lists": [".ci/policy"],
            },
            T2: {"reads": [T2], "lists": []},
            ".ci/rediacc_ci/tests/test_gone.py": {"reads": ["docs/a.md"], "lists": []},
        },
        "unattributed": {"reads": [], "lists": []},
    }
    got = pr.derive_reads(tr, MAP, TREE)
    assert got == {T1: [".ci/policy/one.json"]}, got


def test_derive_paths_unions_reads_closures_and_test_roots():
    tr = {
        "tests": {
            T2: {
                "reads": [".ci/policy/one.json", "private/renet/go.mod"],
                "lists": [".ci/policy", "/nowhere"],
            }
        },
        "unattributed": {"reads": ["pyproject.toml"], "lists": [""]},
    }
    got = pr.derive_paths(tr, MAP, TREE, [".ci/rediacc_ci/tests"])

    def inside(rel):
        return any(pr.glob_matches(g, rel) for g in got["paths"])

    assert inside(".ci/policy/one.json"), got
    assert inside("private/renet"), "a submodule read did not reach its gitlink entry"
    assert inside(".ci/rediacc_ci/leaf.py"), "a closure member was left out"
    for rel in (T1, T2, ".ci/rediacc_ci/tests/conftest.py"):
        assert inside(rel), "the test root was left out: %s" % rel
    assert not inside("docs/a.md"), got
    assert got["lists"] == ["", ".ci/policy"]


def test_the_paths_carry_no_entry_another_already_reaches():
    assert pr._minimal([".ci/**", ".ci/rediacc_ci/tests/**", ".ci/x.json", "docs/a.md"]) == [
        ".ci/**",
        "docs/a.md",
    ]
    assert pr._minimal([".ci/a/**", ".ci/ab.json"]) == [".ci/a/**", ".ci/ab.json"], (
        "CONTROL: a sibling sharing a prefix was taken for a child"
    )


def test_a_docs_only_change_meets_no_derived_path():
    """The derived union is exact: a doc no test reads stays outside it. On the real trace the union reached every tracked file, which is why check:ci-pytest hashes the whole tree (W4.3, 2026-11-18); a union that swallowed unread files would make that verdict unfalsifiable."""
    tr = {
        "tests": {T1: {"reads": [".ci/policy/one.json"], "lists": []}},
        "unattributed": {"reads": [], "lists": []},
    }
    got = pr.derive_paths(tr, MAP, TREE, [".ci/rediacc_ci/tests"])
    assert not any(pr.glob_matches(g, "docs/a.md") for g in got["paths"]), got


def test_control_a_doc_a_test_reads_is_inside_the_paths():
    tr = {
        "tests": {T1: {"reads": ["docs/a.md"], "lists": []}},
        "unattributed": {"reads": [], "lists": []},
    }
    got = pr.derive_paths(tr, MAP, TREE, [".ci/rediacc_ci/tests"])
    assert any(pr.glob_matches(g, "docs/a.md") for g in got["paths"]), got
    assert not any(pr.glob_matches(g, "docs/b.md") for g in got["paths"]), got


# --------------------------------------------------------------------------- refusing a trace that did not see the suite


def record(markers=10, tests=None):
    return {"markers": markers, "tests": {T1: {}, T2: {}} if tests is None else tests}


def test_a_trace_with_no_marker_is_refused():
    assert "no marker" in (pr.trace_problem(record(markers=0), 2) or "")


def test_a_trace_with_no_attributed_file_is_refused():
    assert "no test file" in (pr.trace_problem(record(tests={}), 2) or "")


def test_a_trace_that_saw_too_few_files_is_refused():
    assert "2 of 10" in (pr.trace_problem(record(), 10) or "")


def test_control_a_full_trace_is_accepted():
    assert pr.trace_problem(record(), 2) is None


def test_strace_reads_only_successful_calls_through_a_pid_prefixed_stream():
    argv = pr.strace_argv("/tmp/log", ["pytest"])
    assert "status=successful" in argv
    assert argv[argv.index("-o") + 1] == "/dev/stderr", "bare stderr drops the `<pid> ` prefix"
    assert "-f" in argv
    assert argv[-1] == "pytest"


# --------------------------------------------------------------------------- the plugin, in a real pytest run


def _plugin_run(
    tmp_path, workers: list[str], with_option: bool = True, positional: bool = True
) -> list[str]:
    """`positional=False` names no test path, so pytest falls back to the ini `testpaths`: the whole-suite shape the traced run uses."""
    proj = tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    (proj / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")
    for name in ("test_a.py", "test_b.py"):
        (proj / "tests" / name).write_text("def test_x():\n    assert True\n", encoding="utf-8")
    markers = tmp_path / "m"
    markers.mkdir()
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(pathlib.Path(pr.__file__).resolve().parents[2]), env.get("PYTHONPATH", "")]
    )
    option = ["%s=%s" % (pr.MARKER_OPTION, markers)] if with_option else []
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "rediacc_ci.quality.pytest_impact_reads",
            *workers,
            *option,
            *(["tests"] if positional else []),
        ],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return sorted(pr.label_of_marker(n) for n in os.listdir(markers))


@pytest.mark.parametrize("workers", [["-p", "no:xdist"], ["-n", "2"]], ids=["serial", "xdist"])
def test_the_plugin_marks_each_collected_and_run_test_file(tmp_path, workers):
    """The xdist case is the traced run's own shape: the option has to reach the workers, which are the processes that collect and run."""
    got = _plugin_run(tmp_path, workers)
    assert got == [pr.UNATTRIBUTED, "tests/test_a.py", "tests/test_b.py"], got


def test_run_trace_hands_the_option_to_pytest_and_reads_markers_in_that_directory(
    tmp_path, monkeypatch
):
    """The traced command and the Attributor must agree on ONE marker directory: an option pointing elsewhere, or none, leaves every read unattributed and the coverage floor refusing the trace."""
    seen: dict = {}

    class FakeChild:
        pid = 0
        returncode = 0

        def __init__(self, argv, **_k):
            seen["argv"] = argv
            log = argv[argv.index("-c") + 2]
            pathlib.Path(log).write_text("1 passed\n", encoding="utf-8")
            pathlib.Path(log + ".rc").write_text("0\n", encoding="utf-8")
            token = next(a for a in argv if a.startswith(pr.MARKER_OPTION + "="))
            markers = token.split("=", 1)[1]
            self.stderr = [
                '100 openat(AT_FDCWD</r>, "x", O_RDONLY) = 5<%s/%s>'
                % (markers, pr.marker_name(T1)),
                opened(100, "%s/.ci/policy/one.json" % tmp_path),
            ]

        def wait(self):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(pr.shutil, "which", lambda _n: "/usr/bin/strace")
    monkeypatch.setattr(pr.subprocess, "Popen", FakeChild)
    rc, att, out = pr.run_trace(tmp_path, ["pytest", "-q"])
    assert rc == 0
    assert out == "1 passed\n"
    assert pr.MARKER_OPTION not in seen["argv"], "a separate value token reads as a test path"
    assert att.reads == {T1: {".ci/policy/one.json"}}, att.reads


@pytest.mark.parametrize("workers", [["-p", "no:xdist"], ["-n", "2"]], ids=["serial", "xdist"])
def test_the_plugin_marks_the_ini_testpaths_when_no_test_path_is_named(tmp_path, workers):
    got = _plugin_run(tmp_path, workers, positional=False)
    assert got == [pr.UNATTRIBUTED, "tests/test_a.py", "tests/test_b.py"], got


def test_control_the_plugin_is_inert_without_its_option(tmp_path):
    assert _plugin_run(tmp_path, ["-p", "no:xdist"], with_option=False) == []


def test_the_trace_file_is_json_the_derivation_reads():
    att = feed(
        mark(100, T1),
        opened(100, "/r/.ci/policy/one.json"),
        "100 getdents64(3</r/.ci>, 0x5, 32768) = 48",
    )
    rec = pr.trace_record(att, collected=3)
    again = json.loads(json.dumps(rec))
    assert again["tests"][T1] == {"reads": [".ci/policy/one.json"], "lists": [".ci"]}
    assert again["markers"] == 1
    assert pr.derive_reads(again, MAP, TREE) == {T1: [".ci/policy/one.json"]}


@pytest.mark.parametrize(
    ("glob", "rel", "want"),
    [
        (".ci/policy/**", ".ci/policy/one.json", True),
        (".ci/policy/**", ".ci/policyx/one.json", False),
        ("docs/a.md", "docs/a.md", True),
        ("docs/a.md", "docs/a.mdx", False),
        ("**", "anything/at/all.txt", True),
    ],
)
def test_glob_matches(glob, rel, want):
    assert pr.glob_matches(glob, rel) is want


LANG = "packages/www/src/pages/[lang]"


def test_a_tracked_name_holding_a_glob_character_folds_to_its_clean_ancestor():
    """input-hash.ts hashes an entry with `[` in `lists` or `paths` to null, which never carries (the first full derivation, 2026-11-18, listed Astro's `[lang]` directories and nulled the whole check:ci-pytest entry)."""
    assert pr._clean_dir(LANG + "/docs") == "packages/www/src/pages"
    assert pr._clean_glob(LANG + "/index.astro") == "packages/www/src/pages/**"
    assert pr._clean_glob(LANG + "/**") == "packages/www/src/pages/**"
    assert pr._clean_glob("[x]/a.md") == "**", "a fold to the root is the whole tree"
    assert pr._clean_dir("[x]") == ""


def test_control_clean_names_pass_through_unchanged():
    assert pr._clean_dir("packages/www/src/pages") == "packages/www/src/pages"
    assert pr._clean_glob("docs/a.md") == "docs/a.md"
    assert pr._clean_glob(".ci/policy/**") == ".ci/policy/**"


def test_derive_paths_writes_no_glob_character_the_hasher_refuses():
    tree = pr.Tree.of(
        [("100644", p) for p in (T1, LANG + "/index.astro", LANG + "/about.astro", "docs/a.md")]
    )
    tr = {
        "tests": {T1: {"reads": [LANG + "/index.astro"], "lists": [LANG, "docs"]}},
        "unattributed": {"reads": [], "lists": []},
    }
    got = pr.derive_paths(tr, {"tests": {T1: {"closure": [T1]}}}, tree, [".ci/rediacc_ci/tests"])
    for item in [*got["paths"], *got["lists"]]:
        body = item.removesuffix("/**")
        assert not any(c in body for c in pr._GLOB_CHARS), (
            "the hasher would null this entry: %r" % item
        )
    assert any(pr.glob_matches(g, LANG + "/index.astro") for g in got["paths"]), got
    assert got["lists"] == ["docs", "packages/www/src/pages"], got


# --------------------------------------------------------------------------- a red traced run


def test_failed_nodeids_come_from_the_short_summary():
    out = (
        "....F.\n=== short test summary info ===\n"
        "FAILED .ci/rediacc_ci/tests/test_x.py::test_a[1] - AssertionError: slow\n"
        "FAILED .claude/rediacc_hooks/tests/test_y.py::test_b\n"
        "ERROR .ci/rediacc_ci/tests/test_z.py - collection\n"
    )
    assert pr.failed_nodeids(out) == [
        ".ci/rediacc_ci/tests/test_x.py::test_a[1]",
        ".claude/rediacc_hooks/tests/test_y.py::test_b",
    ]


def test_control_a_green_run_is_accepted():
    assert pr.red_run_problem(0, 100, []) is None


def test_a_few_named_failures_are_accepted():
    """Timing under ptrace: 5 of 9,571 failed in the 2026-11-18 traced run, 0.05%."""
    assert pr.red_run_problem(1, 9571, ["a::b"] * 5) is None


@pytest.mark.parametrize(
    ("rc", "passed", "failed", "why"),
    [
        (2, 100, [], "exited 2"),
        (4, 0, [], "exited 4"),
        (5, 0, [], "exited 5"),
        (1, 100, [], "named no FAILED"),
        (1, 1000, ["t::%d" % i for i in range(11)], "above 1%"),
    ],
)
def test_a_red_run_beyond_a_few_named_failures_is_refused(rc, passed, failed, why):
    problem = pr.red_run_problem(rc, passed, failed)
    assert problem is not None
    assert why in problem, problem


def test_run_trace_removes_its_scratch_when_strace_cannot_start(tmp_path, monkeypatch):
    made = tmp_path / "scratch"
    monkeypatch.setattr(pr.shutil, "which", lambda _n: "/usr/bin/strace")
    monkeypatch.setattr(pr.tempfile, "mkdtemp", lambda **_k: (made.mkdir(), str(made))[1])

    def refuses(*_a, **_k):
        raise OSError("no strace here")

    monkeypatch.setattr(pr.subprocess, "Popen", refuses)
    with pytest.raises(OSError, match="no strace here"):
        pr.run_trace(tmp_path, ["pytest"])
    assert not made.exists(), "a Popen that raised leaked the scratch directory"


def test_a_term_signal_unwinds_as_an_exit():
    with pytest.raises(SystemExit) as got:
        pr._exit_on_term(15, None)
    assert got.value.code == 143


# --------------------------------------------------------------------------- shards


def test_shards_partition_the_files_round_robin_with_nothing_lost():
    files = ["t/test_%02d.py" % i for i in range(7)]
    groups = pr.shard_files(list(reversed(files)), 3)
    assert groups == [files[0::3], files[1::3], files[2::3]]
    assert sorted(f for g in groups for f in g) == files, "a file was dropped or doubled"


def test_control_more_shards_than_files_gives_no_empty_shard():
    assert pr.shard_files(["t/test_a.py"], 4) == [["t/test_a.py"]]


def test_merge_unions_reads_per_label_and_sums_the_counts():
    a = feed(opened(100, "/r/pyproject.toml"), mark(100, T1), opened(100, "/r/.ci/policy/a.json"))
    b = feed(opened(100, "/r/pyproject.toml"), mark(100, T2), opened(100, "/r/.ci/policy/b.json"))
    b.unclaimed[7] = [("read", "/r/x")]
    got = pr.merge_attributors([a, b])
    assert got.reads[T1] == {".ci/policy/a.json"}
    assert got.reads[T2] == {".ci/policy/b.json"}
    assert got.reads[pr.UNATTRIBUTED] == {"pyproject.toml"}
    assert got.markers == 2
    assert got.lines == a.lines + b.lines
    assert len(got.unclaimed) == 1


@pytest.mark.parametrize(
    ("codes", "want"),
    [([0, 0], 0), ([0, 1], 1), ([1, 2, 0], 2), ([0, 5], 5)],
)
def test_the_worst_shard_exit_wins(codes, want):
    assert pr.merged_rc(codes) == want


# --------------------------------------------------------------------------- orphans a test leaked


def _fake_proc(root: pathlib.Path, rows: list[tuple[int, int, str]]) -> str:
    for pid, sid, cmd in rows:
        d = root / str(pid)
        d.mkdir(parents=True)
        # Field 6 of /proc/<pid>/stat is the session id; a command name holding ") " must not shift it.
        (d / "stat").write_text("%d (odd) name) S 1 %d %d 0 -1" % (pid, pid, sid), encoding="utf-8")
        (d / "cmdline").write_bytes(cmd.replace(" ", "\0").encode() + b"\0")
    (root / "self").mkdir()
    return str(root)


def test_session_members_reads_the_session_field_past_a_tricky_command_name(tmp_path):
    proc = _fake_proc(
        tmp_path,
        [(10, 10, "strace -f"), (11, 10, "tail -f /dev/null"), (12, 99, "other session")],
    )
    assert pr.session_members(10, proc) == [(10, "strace -f"), (11, "tail -f /dev/null")]


def test_leaked_lines_pick_out_only_the_orphan_reports():
    out = "1 passed\n%stail -f /dev/null x\nnoise outlived pytest\n%ssleep 300" % (
        pr.LEAKED_PREFIX,
        pr.LEAKED_PREFIX,
    )
    assert pr.leaked_lines(out) == [
        pr.LEAKED_PREFIX + "tail -f /dev/null x",
        pr.LEAKED_PREFIX + "sleep 300",
    ]
    assert pr.leaked_lines("37520 passed\n") == [], "CONTROL: a clean run reports no orphan"


def test_control_session_members_of_an_empty_session_is_empty(tmp_path):
    assert pr.session_members(42, _fake_proc(tmp_path, [(10, 10, "strace -f")])) == []


def test_pytest_exit_comes_from_its_own_file_not_from_strace(tmp_path, monkeypatch):
    """strace exits with the status of `sh`, whose last command writes the file; the verdict is pytest's code in the file."""

    class FakeChild:
        pid = 0
        returncode = 0

        def __init__(self, argv, **_k):
            log = argv[argv.index("-c") + 2]
            pathlib.Path(log).write_text("1 failed\n", encoding="utf-8")
            pathlib.Path(log + ".rc").write_text("1\n", encoding="utf-8")
            self.stderr = []

        def wait(self):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(pr.shutil, "which", lambda _n: "/usr/bin/strace")
    monkeypatch.setattr(pr.subprocess, "Popen", FakeChild)
    rc, _att, _out = pr.run_trace(tmp_path, ["pytest"])
    assert rc == 1, "strace's own 0 hid pytest's failure"


# --------------------------------------------------------------------------- review findings: the trace run, the markers, the derive guard


def test_a_marker_that_cannot_be_written_falls_back_to_no_test_file(tmp_path, monkeypatch):
    """Finding f4eb37c7.5: the previous file's attribution must not stand when a marker fails."""
    real_open = os.open

    def flaky(path, *a, **k):
        if os.path.basename(path) == pr.marker_name(T1):
            raise OSError("disk full")
        return real_open(path, *a, **k)

    monkeypatch.setattr(pr.os, "open", flaky)
    monkeypatch.setattr(pr, "_MARKERS", [str(tmp_path)])
    pr._mark(T1)
    assert os.listdir(tmp_path) == [pr._UNATTRIBUTED_MARK]
    pr._mark(T2)
    assert sorted(os.listdir(tmp_path)) == sorted([pr._UNATTRIBUTED_MARK, pr.marker_name(T2)])


def test_unconfigure_stops_the_plugin_marking(tmp_path, monkeypatch):
    """Finding 53d58328.2."""
    monkeypatch.setattr(pr, "_MARKERS", [str(tmp_path)])
    pr.pytest_unconfigure()
    pr._mark(T1)
    assert os.listdir(tmp_path) == []


def test_a_new_process_on_a_reused_tid_is_not_a_member_of_the_old_thread_group():
    """Finding f4eb37c7.2: tid 30 was a thread of 100, then a process 100 forked: its reads keep the attribution it was created under."""
    att = feed(
        mark(100, T1),
        "100 clone3({flags=CLONE_VM|CLONE_THREAD, exit_signal=0}, 88) = 30",
        "100 clone(child_stack=NULL, flags=SIGCHLD, child_tidptr=0x7) = 30",
        mark(100, T2),
        opened(30, "/r/.ci/policy/c.json"),
    )
    assert att.reads[T1] == {".ci/policy/c.json"}
    assert T2 not in att.reads


def test_a_zombie_in_the_session_is_named_by_its_comm(tmp_path):
    """Finding c29ab62a.5: an empty command line must not leave the leak report nameless."""
    proc = _fake_proc(tmp_path, [(10, 10, "strace -f"), (11, 10, "")])
    assert pr.session_members(10, proc) == [(10, "strace -f"), (11, "[odd) name]")]


def test_glob_characters_include_the_backslash():
    """Finding bc22fff0.2: a backslash in a tracked name folds to its clean ancestor like any glob character."""
    assert pr._clean_dir("docs/we\\ird/x") == "docs"
    assert pr._clean_glob("docs/we\\ird/x.md") == "docs/**"


class _Stream(list):
    """A stderr stream: a list of strace lines."""


class _OneShot:
    """A stderr stream that is a single pass over its lines, counting those taken: a second `for` over it continues where the first stopped."""

    def __init__(self, lines):
        self._lines = iter(lines)
        self.taken = 0

    def __iter__(self):
        return self

    def __next__(self):
        line = next(self._lines)
        self.taken += 1
        return line


class _Held:
    """A traced child whose rc file exists but which does not end by itself: `strace -f` waits for every tracee."""

    last: ClassVar["_Held"]

    def __init__(self, argv, **_k):
        log = argv[argv.index("-c") + 2]
        pathlib.Path(log).write_text("1 passed\n", encoding="utf-8")
        pathlib.Path(log + ".rc").write_text("0\n", encoding="utf-8")
        self.pid = 4242
        self.returncode = None
        self.alive = True
        self.killed = False
        self.stubborn = False
        self.stderr = _Stream()
        _Held.last = self

    def poll(self):
        return None if self.alive else 0

    def wait(self, timeout=None):
        if self.alive and timeout is not None:
            raise subprocess.TimeoutExpired("strace", timeout)
        self.alive = False
        return 0

    def kill(self):
        self.killed = True
        self.alive = False


@pytest.fixture
def held_trace(monkeypatch):
    monkeypatch.setattr(pr.shutil, "which", lambda _n: "/usr/bin/strace")
    monkeypatch.setattr(pr.subprocess, "Popen", _Held)
    monkeypatch.setattr(pr.time, "sleep", lambda _s: None)
    monkeypatch.setattr(pr, "ORPHAN_GRACE_S", -1.0)


@pytest.mark.usefixtures("held_trace")
def test_an_orphan_outliving_pytest_is_killed_and_named(tmp_path, monkeypatch):
    """Finding c29ab62a.3: the grace expiry kills the session, names its command, and strace then ends."""

    def kill_session(sid, spare=None):
        assert sid == 4242
        assert spare == 4242
        _Held.last.alive = False
        return ["tail -f\n/dev/null"]

    monkeypatch.setattr(pr, "_kill_session", kill_session)
    rc, _att, out = pr.run_trace(tmp_path, ["pytest"])
    assert rc == 0
    assert pr.leaked_lines(out) == [pr.LEAKED_PREFIX + "tail -f /dev/null"], (
        "a newline split the name"
    )
    assert not _Held.last.killed


@pytest.mark.usefixtures("held_trace")
def test_an_orphan_that_left_the_session_does_not_hang_the_trace(tmp_path, monkeypatch):
    """Finding c29ab62a.1: a setsid leak is outside `_kill_session`; strace itself is ended and the run says so."""
    monkeypatch.setattr(pr, "_kill_session", lambda _sid, **_k: [])
    rc, _att, out = pr.run_trace(tmp_path, ["pytest"])
    assert rc == 0
    assert _Held.last.killed
    assert "outside the strace session" in "".join(pr.leaked_lines(out))


@pytest.mark.usefixtures("held_trace")
def test_a_failure_folding_the_stream_is_raised_not_swallowed_in_the_thread(tmp_path, monkeypatch):
    """Finding c29ab62a.2: the reader keeps draining, and the run fails loudly with the cause."""

    def broken(_self, _line):
        raise ValueError("bad line")

    monkeypatch.setattr(pr.Attributor, "feed", broken)

    def kill_session(_sid, **_k):
        _Held.last.kill()
        return []

    monkeypatch.setattr(pr, "_kill_session", kill_session)
    original = _Held.__init__

    def with_lines(self, argv, **k):
        original(self, argv, **k)
        self.stderr = _OneShot(["1 a", "1 b", "1 c"])

    monkeypatch.setattr(_Held, "__init__", with_lines)
    with pytest.raises(RuntimeError, match="folding the strace stream failed") as got:
        pr.run_trace(tmp_path, ["pytest"])
    assert isinstance(got.value.__cause__, ValueError)
    # The failure is raised on the first line; a drain that stopped there would leave the other two unread, which is a pipe strace blocks on.
    assert _Held.last.stderr.taken == 3


@pytest.fixture
def trace_world(tmp_path, monkeypatch):
    """cmd_trace over a one-test-file universe with `run_trace` replaced; the SIGTERM handler it installs is put back."""
    previous = signal.getsignal(signal.SIGTERM)
    monkeypatch.setattr(pr.impact, "present_files", lambda _r: [T1])
    monkeypatch.setattr(pr.impact, "testpath_roots", lambda _r: [".ci/rediacc_ci/tests"])
    calls: list[list[str]] = []
    result = {"value": None}

    def fake_run(_root, argv):
        calls.append(list(argv))
        value = result["value"]
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(pr, "run_trace", fake_run)
    yield tmp_path, calls, result
    signal.signal(signal.SIGTERM, previous)


def _green(output="3 passed\n"):
    return 0, feed(mark(100, T1), opened(100, "/r/.ci/policy/a.json")), output


def _trace_file(root):
    return root / pr.TRACE_RELPATH


def test_cmd_trace_installs_the_term_handler(trace_world):
    """Finding 45f702cd.2: removing the `signal.signal` line reds this."""
    root, _calls, result = trace_world
    result["value"] = _green()
    assert pr.cmd_trace(root, ["--trace"]) == 0
    assert signal.getsignal(signal.SIGTERM) is pr._exit_on_term


def test_a_leaked_process_is_printed_and_recorded_on_a_green_run(trace_world, capsys):
    """Finding bc22fff0.1: the green path is where a leak would otherwise go unseen."""
    root, _calls, result = trace_world
    line = pr.LEAKED_PREFIX + "tail -f /dev/null"
    result["value"] = _green("3 passed\n" + line)
    assert pr.cmd_trace(root, ["--trace"]) == 0
    assert line in capsys.readouterr().out
    assert json.loads(_trace_file(root).read_text(encoding="utf-8"))["leaked"] == [line]


def test_control_a_clean_green_run_records_no_leak(trace_world):
    root, _calls, result = trace_world
    result["value"] = _green()
    assert pr.cmd_trace(root, ["--trace"]) == 0
    assert json.loads(_trace_file(root).read_text(encoding="utf-8"))["leaked"] == []


def test_a_red_traced_run_writes_nothing(trace_world, capsys):
    """Finding f4eb37c7.4: the refusal itself, not only `red_run_problem`."""
    root, _calls, result = trace_world
    result["value"] = (2, feed(mark(100, T1)), "interrupted")
    assert pr.cmd_trace(root, ["--trace"]) == 1
    assert "nothing written" in capsys.readouterr().err
    assert not _trace_file(root).exists()


@pytest.mark.parametrize("value", ["0", "-2", "many"])
def test_a_shards_value_below_one_is_refused(trace_world, capsys, value):
    """Finding d616eb96.4."""
    root, calls, _result = trace_world
    assert pr.cmd_trace(root, ["--trace", "--shards", value]) == 2
    assert "--shards needs a whole number" in capsys.readouterr().err
    assert calls == []


def test_shards_over_a_selection_that_matches_no_file_is_refused_not_a_crash(trace_world, capsys):
    """Finding d616eb96.2: an empty shard set used to reach `ThreadPoolExecutor(max_workers=0)`."""
    root, calls, _result = trace_world
    assert pr.cmd_trace(root, ["--trace", "--shards", "2", "--tests", "nowhere/"]) == 1
    assert "no test file to shard" in capsys.readouterr().err
    assert calls == []


def test_a_shard_run_dispatches_one_trace_per_group(trace_world, monkeypatch):
    """Finding d616eb96.3: the shard dispatch, with a second file so two groups exist."""
    root, calls, result = trace_world
    result["value"] = _green()
    monkeypatch.setattr(pr.impact, "present_files", lambda _r: [T1, T2])
    pr.cmd_trace(root, ["--trace", "--shards", "2"])
    assert sorted(c[-1] for c in calls) == [T1, T2]


def test_an_interrupted_shard_run_kills_the_live_sessions_and_still_shuts_the_pool(
    trace_world, monkeypatch
):
    """Findings c29ab62a.4 and d616eb96.3: the BaseException path of cmd_trace."""
    root, _calls, result = trace_world
    result["value"] = KeyboardInterrupt()
    killed: list[bool] = []
    monkeypatch.setattr(pr, "_kill_live", lambda: killed.append(True))
    with pytest.raises(KeyboardInterrupt):
        pr.cmd_trace(root, ["--trace"])
    assert killed == [True]


def test_kill_live_kills_only_sessions_still_running(monkeypatch):
    """Finding d616eb96.3: `_kill_live` over one running and one finished child."""
    killed: list[int] = []

    class Child:
        def __init__(self, pid, running):
            self.pid, self.running = pid, running

        def poll(self):
            return None if self.running else 0

    def kill_session(sid, **_k):
        killed.append(sid)
        return []

    monkeypatch.setattr(pr, "_kill_session", kill_session)
    monkeypatch.setattr(pr, "_LIVE", [Child(1, True), Child(2, False)])
    pr._kill_live()
    assert killed == [1]


def test_a_trace_names_the_subset_it_covers(trace_world):
    """Finding f4eb37c7.3: the record carries `subset` so `--derive --write` can refuse it."""
    root, _calls, result = trace_world
    result["value"] = _green()
    assert pr.cmd_trace(root, ["--trace", "--tests", ".ci/rediacc_ci/tests"]) == 0
    assert json.loads(_trace_file(root).read_text(encoding="utf-8"))["subset"] == [
        ".ci/rediacc_ci/tests"
    ]


@pytest.fixture
def derive_world(tmp_path, monkeypatch):
    policy = tmp_path / pr.impact.POLICY_RELPATH
    policy.parent.mkdir(parents=True)
    policy.write_text(json.dumps({"smoke": {"files": [T1]}, "reads": {}}), encoding="utf-8")
    monkeypatch.setattr(pr, "read_tree", lambda _r: pr.Tree.of([("100644", T1)]))
    monkeypatch.setattr(pr.impact, "present_files", lambda _r: [T1])
    monkeypatch.setattr(pr.impact, "testpath_roots", lambda _r: [".ci/rediacc_ci/tests"])
    monkeypatch.setattr(
        pr.impact, "load_or_build_map", lambda _r, _p: ({"tests": {T1: {"closure": [T1]}}}, "")
    )

    def write(extra):
        record = pr.trace_record(feed(mark(100, T1), opened(100, "/r/.ci/policy/a.json")), 1)
        record.update(extra)
        out = _trace_file(tmp_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record), encoding="utf-8")

    return tmp_path, policy, write


def test_derive_write_refuses_a_trace_of_a_subset(derive_world, capsys):
    """Finding f4eb37c7.3: a subset trace would replace every other test file's reads."""
    root, policy, write = derive_world
    write({"subset": [".ci/rediacc_ci/tests/test_one.py"]})
    before = policy.read_text(encoding="utf-8")
    assert pr.cmd_derive(root, ["--derive", "--write"]) == 1
    assert "re-run --trace over the whole suite" in capsys.readouterr().err
    assert policy.read_text(encoding="utf-8") == before


def test_derive_write_records_the_tests_that_failed_under_the_trace(derive_world):
    """Finding 45f702cd.1: their entries are lower bounds, and the policy says so."""
    root, policy, write = derive_world
    write({"subset": [], "failed": ["t/test_x.py::test_slow"]})
    assert pr.cmd_derive(root, ["--derive", "--write"]) == 0
    origin = json.loads(policy.read_text(encoding="utf-8"))["readsOrigin"]
    assert "1 test(s) failed under the trace" in origin
    assert "t/test_x.py::test_slow" in origin


def test_control_derive_write_of_a_clean_whole_suite_trace_adds_no_partial_note(derive_world):
    root, policy, write = derive_world
    write({"subset": [], "failed": []})
    assert pr.cmd_derive(root, ["--derive", "--write"]) == 0
    assert "partial" not in json.loads(policy.read_text(encoding="utf-8"))["readsOrigin"]
