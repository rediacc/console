"""`rediacc_ci.quality.lockfile` against the shell it replaces.

NOTHING IN THIS FILE RUNS npm, AND THAT IS A RULE RATHER THAN A CONVENIENCE. `npx -y npm@<pin> ci --dry-run` needs the network, downloads a whole npm, and sits next to eleven committed lockfiles whose byte form this repository has an entire CLAUDE.md section about (the 27-line `"dev": true` flip, issue #587). The gate's own logic is which lockfiles were found, which commands
were built, and what their exit codes said -- so `npx` is stubbed by a short script, and its exit code (plus, for the rewrite probe, whether it changes the mirrored lockfile) is the only thing npm contributes. Every probe in this file runs
with that stub first on PATH.

WHY A DIFFERENTIAL FOR THE DISCOVERY. `find . -name package-lock.json -not -path '*/node_modules/*' | sed 's|^\\./||' | sort` has three edges a rewrite loses: the exclusion is a PATH glob rather than a directory name, the `sed` strips a prefix that only the root-level entry has, and the sort is byte order. Running the real pipeline and comparing is the only form of this test that
can fail for the right reason.

The whole gate is what the committed shadow ledger
`.ci/shadow/w7p2-lockfile.observations.jsonl` compares over five distinct trees;
this file covers the seams that ledger cannot isolate.
"""

import os
import pathlib

import pytest

from rediacc_ci import log, paths
from rediacc_ci.quality import lockfile as lf
from rediacc_ci.tests import differential as diff

# Every tree shape the discovery has to survive. Each entry is a list of files to create; the comment is the property it is there for.
TREES = [
    [],  # nothing at all
    ["package-lock.json"],  # the root one, whose `./` prefix the sed strips
    ["a/package-lock.json"],  # nested only
    ["package-lock.json", "a/package-lock.json"],  # both, and the sort order
    ["b/package-lock.json", "a/package-lock.json"],  # sorted, not found-order
    ["node_modules/x/package-lock.json"],  # excluded
    ["a/node_modules/x/package-lock.json"],  # excluded at depth
    ["a/node_modules/x/package-lock.json", "a/package-lock.json"],  # one of each
    ["my_node_modules_backup/package-lock.json"],  # a lookalike is NOT excluded
    ["a/package.json", "a/package-lock.json"],  # a sibling manifest is irrelevant here
    ["package-lock.json.bak"],  # a different name
    ["a/b/c/package-lock.json"],  # deep
]


def _make(root: pathlib.Path, files: list[str]) -> None:
    for rel in files:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")


def _bash_discover(root: pathlib.Path) -> list[str]:
    script = "find . -name package-lock.json -not -path '*/node_modules/*' | sed 's|^\\./||' | sort"
    code, out, err = diff.bash_streams(script, cwd=str(root))
    assert code == 0, err
    return [line for line in out.split("\n") if line]


@pytest.mark.parametrize("files", TREES)
def test_discovery_matches_find(files: list[str], tmp_path: pathlib.Path) -> None:
    _make(tmp_path, files)
    assert lf.discover(tmp_path) == _bash_discover(tmp_path)


def test_discovery_finds_a_lockfile_beside_a_pruned_node_modules(tmp_path: pathlib.Path) -> None:
    """PRUNING THE DIRECTORY MUST NOT PRUNE ITS PARENT.

    `os.walk` pruning is a different mechanism from a path glob, and the way it goes wrong is by skipping too much. A package whose own lockfile sits beside an installed `node_modules` is the ordinary case, so this is the shape that would break most loudly and is therefore worth an assertion of its own.
    """
    _make(tmp_path, ["pkg/package-lock.json", "pkg/node_modules/dep/package-lock.json"])
    assert lf.discover(tmp_path) == ["pkg/package-lock.json"]
    assert lf.discover(tmp_path) == _bash_discover(tmp_path)


def test_the_pin_is_the_toolchain_pin_and_is_npm_11() -> None:
    """ONE npm, read from `.devcontainer/toolchain.env` rather than written into the gate, and it is an exact 11.x."""
    pin = lf.npm_pin(paths.repo_root())
    assert lf.EXACT_VERSION_RE.match(pin), pin
    assert pin.split(".")[0] == lf.NPM_MAJOR == "11"


def test_the_real_tree_installs_the_pin_everywhere() -> None:
    """PROPERTY D ON THE REAL TREE, with no npm run: every setup-node site is the composite, and every Dockerfile that installs a project tree installs the pin first."""
    root = paths.repo_root()
    assert lf.ci_npm_findings(root, lf.npm_pin(root)) == []


def test_a_bare_setup_node_step_is_a_finding(tmp_path: pathlib.Path) -> None:
    """The planted defect property D exists for: a workflow step that would install with Node's bundled npm 10."""
    lf.scaffold(tmp_path)
    assert lf.ci_npm_findings(tmp_path, lf.FIXTURE_PIN) == []
    wf = tmp_path / ".github" / "workflows" / "ci.yml"
    wf.write_text(
        wf.read_text(encoding="utf-8") + "      - uses: actions/setup-node@abc\n", encoding="utf-8"
    )
    findings = lf.ci_npm_findings(tmp_path, lf.FIXTURE_PIN)
    assert len(findings) == 1, findings
    assert "ci.yml:5" in findings[0], findings


def test_a_venv_lockfile_is_not_discovered(tmp_path: pathlib.Path) -> None:
    """A virtualenv vendors other projects' JavaScript; `private/generative/.venv` carries gradio's lockfile beside a package.json."""
    _make(tmp_path, ["package-lock.json", "tool/.venv/lib/gradio/package-lock.json"])
    assert lf.discover(tmp_path) == ["package-lock.json"]


def test_the_probe_argv_is_the_twins_argv() -> None:
    """The check IS the command, so the command is the thing to pin."""
    assert lf.resolve_argv("npm@11.20.0") == [
        "npx",
        "-y",
        "npm@11.20.0",
        "ci",
        "--dry-run",
        "--ignore-scripts",
    ]
    assert lf.lint_argv("pkg/package-lock.json") == [
        "npx",
        "--no-install",
        "lockfile-lint",
        "--path",
        "pkg/package-lock.json",
        "--type",
        "npm",
        "--validate-https",
        "--allowed-hosts",
        "npm",
        "--validate-package-names",
        "--validate-integrity",
    ]


@pytest.fixture
def stub_npx(tmp_path: pathlib.Path):
    """An `npx` on PATH whose exit codes are decided per probe, and nothing else.

    Yields a setter. The fixture restores PATH afterwards, because a leaked PATH would let a LATER test reach the real npx without anyone noticing -- which is exactly the thing this file exists to prevent.
    """
    binpath = tmp_path / "stub-bin"
    binpath.mkdir()
    stub = binpath / "npx"

    def setter(lint: int = 0, resolve: int = 0, rewrite: int = 0, rewrites: bool = False) -> None:
        stub.write_text(
            "#!/bin/bash\n"
            'case "$*" in\n'
            "  *lockfile-lint*) echo lint-transcript; exit %d ;;\n"
            "  *' ci '*) echo resolve-transcript; exit %d ;;\n"
            "  *--package-lock-only*) %s echo rewrite-transcript; exit %d ;;\n"
            "esac\nexit 0\n"
            % (lint, resolve, "echo drift >> package-lock.json;" if rewrites else "", rewrite),
            encoding="utf-8",
        )
        stub.chmod(0o755)

    setter()
    saved = os.environ.get("PATH", "")
    os.environ["PATH"] = "%s:%s" % (binpath, saved)
    try:
        yield setter
    finally:
        os.environ["PATH"] = saved


def test_the_stub_is_really_what_runs(tmp_path: pathlib.Path, stub_npx) -> None:
    """A CONTROL ON THE CONTROL. Without it every case below could be green because `npx` was never invoked at all, which is the vacuity this whole exercise refuses."""
    stub_npx(resolve=3)
    assert lf.run_resolve(tmp_path, "npm@%s" % lf.FIXTURE_PIN) == 3
    stub_npx(resolve=0)
    assert lf.run_resolve(tmp_path, "npm@%s" % lf.FIXTURE_PIN) == 0


def test_the_failure_transcript_is_indented_and_truncated(tmp_path: pathlib.Path, stub_npx) -> None:
    """`2>&1 | head -25 | sed 's/^/ /'`, including the merge of the streams.

    Merging is correct HERE and only here: this is a transcript shown to a human, not a comparison, and the twin's `|| true` says its exit code is not part of the verdict.
    """
    stub_npx(resolve=1)
    spec = "npm@%s" % lf.FIXTURE_PIN
    assert lf.resolve_failure_detail(tmp_path, spec) == ["    resolve-transcript"]
    assert lf.resolve_failure_detail(tmp_path, spec, limit=0) == []


def _run_gate(root: pathlib.Path) -> int:
    """Drive `main` at a fixture root, with the logger REBOUND to the current stream.

    `rediacc_ci.log` builds its default Logger once and holds the `sys.stderr` object it saw. pytest replaces that object per test, so a cached Logger keeps writing to a stream `capsys` is no longer reading -- the messages appear in pytest's own "Captured stderr" section while `readouterr().err` comes back empty, which reads as "the gate printed nothing". `log.reset()` exists for
    exactly this caller; see its docstring.
    """
    saved = os.environ.get(paths.ROOT_ENV)
    os.environ[paths.ROOT_ENV] = str(root)
    log.reset(colour=False)
    try:
        return lf.main([])
    finally:
        log.reset()
        if saved is None:
            os.environ.pop(paths.ROOT_ENV, None)
        else:
            os.environ[paths.ROOT_ENV] = saved


@pytest.mark.usefixtures("stub_npx")
def test_no_lockfile_anywhere_is_a_refusal(tmp_path: pathlib.Path) -> None:
    """THE VACUITY CASE. An empty list is the one a gate most easily turns into a pass by reading it as "nothing to complain about"."""
    root = tmp_path / "tree"
    root.mkdir()
    assert _run_gate(root) == 1


@pytest.mark.usefixtures("stub_npx")
def test_a_lockfile_with_no_sibling_manifest_is_skipped_loudly(
    tmp_path: pathlib.Path, capsys
) -> None:
    """SKIPPED, NOT SILENT, AND STILL EXIT 0.

    The quality-security job checks out without submodules, so this state is legitimate. The twin warns twice -- once per lockfile and once in a summary -- and `scripts/lib/shadow-gate.ts` classifies a `⚠` line as a FINDING, so a port that downgraded either warning to chatter would show up as a mismatch.
    """
    root = tmp_path / "tree"
    _make(root, ["package-lock.json"])
    lf.scaffold(root)
    assert _run_gate(root) == 0
    err = capsys.readouterr().err
    assert "SKIP package-lock.json" in err
    assert "Skipped 1 lockfile(s)" in err


@pytest.mark.parametrize(
    ("lint", "resolve", "rewrite", "rewrites", "want"),
    [
        (0, 0, 0, False, 0),  # everything holds
        (1, 0, 0, False, 1),  # property A fails
        (0, 1, 0, False, 1),  # the pinned npm cannot resolve
        (0, 0, 0, True, 1),  # the pinned npm would rewrite it
        (0, 0, 2, False, 1),  # the rewrite itself fails
        (1, 1, 1, True, 1),  # all of them
    ],
)
def test_each_probes_outcome_decides_the_verdict(
    tmp_path: pathlib.Path,
    stub_npx,
    lint: int,
    resolve: int,
    rewrite: int,
    rewrites: bool,
    want: int,
) -> None:
    """BOTH DIRECTIONS. The first row is the mirror that stops a port which simply reds on everything from passing this table."""
    root = tmp_path / "tree"
    _make(root, ["package-lock.json", "package.json"])
    lf.scaffold(root)
    stub_npx(lint=lint, resolve=resolve, rewrite=rewrite, rewrites=rewrites)
    assert _run_gate(root) == want


def test_the_rewrite_never_touches_the_committed_lockfile(tmp_path: pathlib.Path, stub_npx) -> None:
    """The rewrite runs on a scratch mirror; the committed bytes are what the verdict is about, not something the gate may change."""
    root = tmp_path / "tree"
    _make(root, ["package-lock.json", "package.json"])
    lf.scaffold(root)
    stub_npx(rewrites=True)
    assert _run_gate(root) == 1
    assert (root / "package-lock.json").read_text(encoding="utf-8") == "{}\n"


def test_a_resolve_failure_ends_that_lockfiles_checks(
    tmp_path: pathlib.Path, stub_npx, capsys
) -> None:
    """ONE LOCKFILE, ONE FIRST FAILURE: a lockfile npm cannot resolve has no meaningful rewrite, so the rewrite is not reported under it."""
    root = tmp_path / "tree"
    _make(root, ["package-lock.json", "package.json"])
    lf.scaffold(root)
    stub_npx(resolve=1, rewrites=True)
    assert _run_gate(root) == 1
    captured = capsys.readouterr()
    assert "CANNOT RESOLVE" in captured.err
    assert "would rewrite" not in captured.err


def test_a_skipped_lockfile_does_not_stop_the_others(tmp_path: pathlib.Path, stub_npx) -> None:
    """A skip that suppressed the rest of the run would look identical to a clean tree, which is how a gate goes green while checking nothing."""
    root = tmp_path / "tree"
    _make(root, ["package-lock.json", "package.json", "sub/package-lock.json"])
    lf.scaffold(root)
    stub_npx()
    assert _run_gate(root) == 0
    stub_npx(lint=1)
    assert _run_gate(root) == 1


def test_the_real_tree_has_lockfiles_to_check() -> None:
    """A CONTROL ON THE INPUT, and it runs no npm.

    Discovery only. Without it, every case above could be passing while the walker returned nothing on the repository it is actually pointed at, which is the shape of a gate that has stopped seeing its subject.
    """
    root = paths.repo_root()
    found = lf.discover(root)
    assert len(found) >= 2, "the lockfile discovery collapsed on the real tree"
    assert all("node_modules" not in pathlib.Path(p).parts for p in found)
    assert found == sorted(found)


def test_selftest_is_green() -> None:
    """The gate's own controls, driven in-process. Exit 0 or the port is broken."""
    assert lf.selftest() == 0


def test_no_test_in_this_file_can_reach_the_real_npx() -> None:
    """THE PROHIBITION, ASSERTED RATHER THAN REMEMBERED.

    Outside the `stub_npx` fixture this module must never invoke `npx`. If a future edit adds a probe without the fixture it would silently start downloading npm beside this repository's committed lockfiles. There is no way to assert "was not called", so the next best thing is asserted: the module never spawns anything except through the four helpers named here, and all
    four take an explicit argv built by `lint_argv` / `resolve_argv` / `rewrite_argv`.
    """
    source = pathlib.Path(lf.__file__).read_text(encoding="utf-8")
    spawn_sites = [line for line in source.split("\n") if "subprocess.run(" in line]
    # Four, and only four: run_lint, run_resolve, resolve_failure_detail, run_rewrite. A fifth would be a spawn nobody reviewed.
    assert len(spawn_sites) == 4, spawn_sites
    # And the literal `npx` is built in exactly three places, all of them argv helpers this file pins. A fourth would be an argv nobody compared.
    builders = [line for line in source.split("\n") if line.strip().startswith('return ["npx"')]
    assert len(builders) == 3, builders
