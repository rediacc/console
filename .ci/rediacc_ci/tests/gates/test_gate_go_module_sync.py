r"""Port of `.ci/scripts/test/gates/test-go-module-sync.sh`, retired in W7 P5.

Both-ways test for `.ci/scripts/quality/check_go_module_sync.py`, which replaced the bash `check-go-module-sync.sh` as the registered `check:ci-go-module-sync` step on 2026-09-08 (W7 P4). The bash gate script is retired in the same change as this port, once this file reaches the same verdicts on the same fixtures.

WHY THIS TEST EXISTS DESPITE THE SIBLING PRECEDENT. `check:ci-go-deps` ships without a gate-test, so convention would have allowed this one to as well. The review of PR #570 flagged that CLAUDE.md's standard is the stronger claim: a gate never watched failing is indistinguishable from `true`. The defect this gate exists for surfaced ~25 minutes into CI and read as a slow proxy, so
the one thing that must never rot is its ability to FAIL.

The gate DISCOVERS modules by grepping for a `replace` onto the renet worktree, so the fixture is a throwaway tree containing such a module rather than the live one; that keeps the proofs independent of whatever license-mint happens to pin today. The fixture is retargeted through `REDIACC_CI_ROOT` -- the same seam `check_go_module_sync.py`'s own `selftest()` uses -- rather than by
copying the gate script into a mirrored tree, which is the port's one structural change from the twin: `paths.repo_root()` already has a fixture seam, so driving the REAL entry point against a fixture root is simpler than reproducing the twin's own relative-path resolution in a second place.
"""

import os

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_go_module_sync.py")

GOMOD = """module example.com/tool

go 1.25.0

require github.com/rediacc/renet v0.0.0

replace github.com/rediacc/renet => ../../private/renet
"""


def write_fake_go(bindir, verdict) -> None:
    """A stub `go` whose `mod tidy -diff` verdict the test controls, so the cases below exercise the GATE's logic rather than a real module graph."""
    body = "#!/bin/bash\n"
    body += 'if [[ "$1" == "mod" && "$2" == "tidy" && "$3" == "-diff" ]]; then\n'
    if verdict == "tidy":
        body += "    exit 0\n"
    else:
        body += '    echo "diff current/go.mod tidy/go.mod"\n'
        body += '    echo "-\tgithub.com/sirupsen/logrus v1.10.0 // indirect"\n'
        body += '    echo "+\tgithub.com/sirupsen/logrus v1.10.1 // indirect"\n'
        body += "    exit 1\n"
    body += "fi\n"
    body += "exit 0\n"
    path = bindir / "go"
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def seed_module(root) -> None:
    tool = root / "tool"
    tool.mkdir(parents=True, exist_ok=True)
    (tool / "go.mod").write_text(GOMOD, encoding="utf-8")


def run_gate(root, bindir) -> harness.RunResult:
    return harness.run(
        ["python3", str(GATE)],
        cwd=root,
        env={
            "REDIACC_CI_ROOT": str(root),
            "PATH": "%s%s%s" % (bindir, os.pathsep, os.environ.get("PATH", "")),
        },
    )


def test_a_tidy_module_passes(gate, tmp_path):
    # Baseline. If this failed, every other case would be meaningless.
    bindir = tmp_path / "bin"
    bindir.mkdir()
    seed_module(tmp_path)
    write_fake_go(bindir, "tidy")
    result = run_gate(tmp_path, bindir)
    gate.assert_exit(0, result, "a module already tidy against renet validates")
    gate.log_pass("a tidy module passes")


def test_an_out_of_sync_module_fails(gate, tmp_path):
    # THE CASE THE GATE EXISTS FOR: renet moved, the replacing module did not.
    bindir = tmp_path / "bin"
    bindir.mkdir()
    seed_module(tmp_path)
    write_fake_go(bindir, "stale")
    result = run_gate(tmp_path, bindir)
    gate.assert_eq(result.rc, 1, "an out-of-sync module must fail")
    gate.assert_contains(result.combined, "OUT OF SYNC", "the failure names the condition")
    gate.assert_contains(result.combined, "go mod tidy", "the failure names the fix")
    gate.log_pass("an out-of-sync module fails and names both the condition and the fix")


def test_finding_no_modules_is_a_failure_not_a_pass(gate, tmp_path):
    # A discovery gate that finds nothing has verified nothing. If the replace coupling ever disappears, this must be a loud decision rather than a silent green.
    bindir = tmp_path / "bin"
    bindir.mkdir()
    write_fake_go(bindir, "tidy")
    result = run_gate(tmp_path, bindir)
    gate.assert_eq(result.rc, 1, "zero discovered modules must not read as success")
    gate.assert_contains(result.combined, "verified NOTHING", "the vacuity guard is what fires")
    gate.log_pass("discovering zero modules fails rather than passing vacuously")
