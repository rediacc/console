"""pytest_impact_reads: the strace stream, the attribution, the fold and both derivations (PLAN-ciquick-cpu W4.3).

Every rule has a test that makes it fire and a control that keeps it from firing everywhere: an attributor that put every read on one test file, or on none, would pass half of these and fail the other half.
"""

import json
import os
import pathlib
import subprocess
import sys

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
    """W4.3 Accept, on the derivation: a doc no test reads is outside check:ci-pytest's paths, so a docs-only diff leaves its input hash alone and the gate carries."""
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


def _plugin_run(tmp_path, workers: list[str], with_option: bool = True) -> list[str]:
    proj = tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    (proj / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    for name in ("test_a.py", "test_b.py"):
        (proj / "tests" / name).write_text("def test_x():\n    assert True\n", encoding="utf-8")
    markers = tmp_path / "m"
    markers.mkdir()
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(pathlib.Path(pr.__file__).resolve().parents[2]), env.get("PYTHONPATH", "")]
    )
    option = [pr.MARKER_OPTION, str(markers)] if with_option else []
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
            "tests",
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

        def __init__(self, argv, **_k):
            seen["argv"] = argv
            log = argv[argv.index("-c") + 2]
            pathlib.Path(log).write_text("1 passed\n", encoding="utf-8")
            markers = argv[argv.index(pr.MARKER_OPTION) + 1]
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
    assert pr.MARKER_OPTION in seen["argv"], seen["argv"]
    assert att.reads == {T1: {".ci/policy/one.json"}}, att.reads


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
    ],
)
def test_glob_matches(glob, rel, want):
    assert pr.glob_matches(glob, rel) is want
