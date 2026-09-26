"""`rediacc_ci.ci.scope_reconcile_shadow`, driven directly (`ci.yml`'s skip-plan reconciliation step).

A FIXTURE TREE, not the real repository: the subject derives the reconciler path and (by default) the cache directory from its own file location, so each case copies it, PLUS a controllable fake `.cjs` reconciler, into a tree shaped like the repository at the right relative depth.

RECORDING FAKES FOR `gh`, on PATH (seam is PATH, same technique as `ci-stop-elite`'s fake docker): `gh run download` and `gh api` are the only two subcommands the subject calls. `node` and `timeout` are the REAL binaries -- the fake `.cjs` reconciler controls exit code, output, and an optional sleep (to drive the `bounded()` timeout path) via environment variables, so there is
no need to fake `node` itself.

EVERY CASE SETS `GITHUB_STEP_SUMMARY` TO A REAL FILE, matching the ONLY environment this script ever actually runs in (inside GitHub Actions, which always sets it). `test_summary_unset_duplicates_the_whole_output` is the one case that leaves it unset.

WHILE BOTH COPIES EXISTED each case ran `.ci/scripts/ci/scope-reconcile-shadow.sh` beside the port over the same fixture and compared exit code, stdout, stderr and the summary file. The K=5 ledger `.ci/shadow/w7p6-scope-reconcile-shadow.observations.jsonl` recorded that verdict over five distinct trees and licensed the port; W7 P5 retired the twin and the cases that executed
it went with it. The twin's own kernel-file-offset corruption on the unset-summary path went with it too, since there is no longer a second implementation to diverge from; what remains is the port's side of that behaviour, asserted directly.
"""

from __future__ import annotations

import itertools
import os
import pathlib
import shutil
import subprocess
import tempfile

from rediacc_ci import paths

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "ci" / "scope_reconcile_shadow.py"

FAKE_RECONCILER = """#!/usr/bin/env node
const rc = parseInt(process.env.FAKE_RECONCILE_RC || "0", 10);
const sleepMs = parseInt(process.env.FAKE_RECONCILE_SLEEP_MS || "0", 10);
const out = process.env.FAKE_RECONCILE_STDOUT || "";
const err = process.env.FAKE_RECONCILE_STDERR || "";
function done() {
  if (out) process.stdout.write(out);
  if (err) process.stderr.write(err);
  process.exit(rc);
}
if (sleepMs > 0) { setTimeout(done, sleepMs); } else { done(); }
"""

FAKE_GH = """#!/usr/bin/env python3
import os
import sys

argv = sys.argv[1:]
log = os.environ.get("FAKE_GH_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("\\t".join(argv) + "\\n")

if argv[:2] == ["run", "download"]:
    attempt_file = os.environ.get("FAKE_GH_DOWNLOAD_ATTEMPT_FILE")
    if os.environ.get("FAKE_GH_DOWNLOAD_FAIL_FIRST") == "1" and attempt_file:
        if not os.path.exists(attempt_file):
            open(attempt_file, "w", encoding="utf-8").close()
            sys.stderr.write("gh: fake transient failure\\n")
            sys.exit(1)
    rc = int(os.environ.get("FAKE_GH_DOWNLOAD_RC", "0"))
    if rc != 0:
        sys.stderr.write("gh: fake download failure\\n")
        sys.exit(rc)
    d = argv[argv.index("-D") + 1]
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "plan.json"), "w", encoding="utf-8") as f:
        f.write(os.environ.get("FAKE_GH_PLAN_JSON", '{"scope_mode":"reduced"}'))
    sys.exit(0)

if argv[:1] == ["api"]:
    rc = int(os.environ.get("FAKE_GH_JOBS_RC", "0"))
    if rc != 0:
        sys.stderr.write("gh: fake api failure\\n")
        sys.exit(rc)
    sys.stdout.write(os.environ.get("FAKE_GH_JOBS_JSON", "[]"))
    sys.exit(0)

sys.exit(1)
"""


def _fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "tree"
    (root / ".ci" / "scripts" / "ci").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "ci").mkdir(parents=True)
    (root / ".ci" / "cache").mkdir(parents=True)
    shutil.copy2(PORT, root / ".ci" / "rediacc_ci" / "ci" / PORT.name)
    reconciler = root / ".ci" / "scripts" / "ci" / "skip-plan-reconcile.cjs"
    reconciler.write_text(FAKE_RECONCILER, encoding="utf-8")
    reconciler.chmod(0o755)
    return root


def _fake_gh_bin(where: pathlib.Path) -> pathlib.Path:
    where.mkdir(parents=True, exist_ok=True)
    fake = where / "gh"
    fake.write_text(FAKE_GH, encoding="utf-8")
    fake.chmod(0o755)
    return where


# Every external command the subject invokes, plus the tools its own runner needs: dirname, mkdir, tee, timeout, rm, head, gh, node. `bash` and `python3` are the runners themselves. On this host `gh` and `bash` both resolve through `/usr/bin` (and its `/bin` alias), so excluding "the directory gh lives in" would take the runner down with it -- a curated symlink farm avoids that
# entirely.
_ALWAYS_NEEDED = ("bash", "python3", "dirname", "mkdir", "tee", "timeout", "rm", "head")


def _curated_bin(where: pathlib.Path, *, omit: str) -> pathlib.Path:
    """A fresh PATH directory with symlinks to every tool this script (and its own runner) needs, EXCEPT `omit` -- which is genuinely absent, not merely shadowed, so `shutil.which`/`command -v` correctly report it missing without also losing `bash` or `python3` in the process."""
    where.mkdir(parents=True, exist_ok=True)
    for tool in (*_ALWAYS_NEEDED, "gh", "node"):
        if tool == omit:
            continue
        found = shutil.which(tool)
        if found:
            (where / tool).symlink_to(found)
    return where


def _run(
    root: pathlib.Path,
    *,
    env: dict[str, str],
    with_fake_gh: bool = True,
) -> subprocess.CompletedProcess[str]:
    subject = root / ".ci" / "rediacc_ci" / "ci" / PORT.name
    full_env = dict(env)
    if with_fake_gh:
        fake_bin = _fake_gh_bin(root.parent / "fakebin")
        full_env["PATH"] = f"{fake_bin}:{full_env.get('PATH', os.environ.get('PATH', ''))}"
    return subprocess.run(
        ["python3", str(subject)],
        cwd=root,
        capture_output=True,
        text=True,
        env=full_env,
        check=False,
        timeout=30,
    )


def _base_env(
    tmp_path: pathlib.Path, label: str, **extra: str
) -> tuple[dict[str, str], pathlib.Path]:
    """A minimal, deterministic env: real GITHUB_STEP_SUMMARY file, a fresh SCOPE_SHADOW_OUT, short timeout so the timeout cases stay fast."""
    out_dir = tmp_path / f"out-{label}"
    summary = tmp_path / f"summary-{label}.md"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "GITHUB_REPOSITORY": "rediacc/console",
        "GITHUB_RUN_ID": "12345",
        "GITHUB_STEP_SUMMARY": str(summary),
        "SCOPE_SHADOW_OUT": str(out_dir),
        "SCOPE_SHADOW_TIMEOUT": "2",
        **extra,
    }
    return env, summary


def run_port(root: pathlib.Path, tmp_path: pathlib.Path, label: str, **extra: str):
    env, summary = _base_env(tmp_path, label, **extra)
    return _run(root, env=env), summary


def test_success_soft_gate(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    result, summary = run_port(root, tmp_path, "success-soft")
    assert result.returncode == 0
    assert "reconciled" in result.stdout
    assert "reconciled" in summary.read_text(encoding="utf-8")


def test_success_hard_gate(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    result, _ = run_port(root, tmp_path, "success-hard", SCOPE_MODE="reduced")
    assert result.returncode == 0
    assert "hard gate: true" in result.stdout


def test_node_missing_is_a_gap(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    curated = _curated_bin(tmp_path / "bin-no-node", omit="node")
    env, _ = _base_env(tmp_path, "node-missing")
    env["PATH"] = str(curated)
    result = _run(root, env=env, with_fake_gh=False)
    assert result.returncode == 0
    assert "`node` is not available" in result.stdout


def test_gh_missing_is_a_hard_failure_when_reduced(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    curated = _curated_bin(tmp_path / "bin-no-gh", omit="gh")
    env, _ = _base_env(tmp_path, "gh-missing", SCOPE_MODE="reduced")
    env["PATH"] = str(curated)
    result = _run(root, env=env, with_fake_gh=False)
    assert result.returncode == 1
    assert "`gh` is not available" in result.stdout


def test_download_failure_is_a_gap_when_soft(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    result, _ = run_port(root, tmp_path, "dl-fail-soft", FAKE_GH_DOWNLOAD_RC="1")
    assert result.returncode == 0
    assert "no attested plan for this run" in result.stdout


def test_download_failure_is_hard_when_reduced(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    result, _ = run_port(
        root, tmp_path, "dl-fail-hard", FAKE_GH_DOWNLOAD_RC="1", SCOPE_MODE="reduced"
    )
    assert result.returncode == 1
    assert "RECONCILIATION FAILED" in result.stdout


def test_download_retries_once_then_succeeds(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    result, _ = run_port(
        root,
        tmp_path,
        "dl-retry",
        FAKE_GH_DOWNLOAD_FAIL_FIRST="1",
        FAKE_GH_DOWNLOAD_ATTEMPT_FILE=str(tmp_path / "attempt"),
    )
    assert result.returncode == 0
    assert "the plan download failed; retrying once" in result.stdout


def test_jobs_api_failure_is_a_gap(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    result, _ = run_port(root, tmp_path, "jobs-fail", FAKE_GH_JOBS_RC="2")
    assert result.returncode == 0
    assert "could not read the jobs API" in result.stdout


def test_reconciler_failure_is_reported(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    result, _ = run_port(
        root,
        tmp_path,
        "reconcile-fail",
        FAKE_RECONCILE_RC="1",
        FAKE_RECONCILE_STDERR="preexisting-claim-mismatch: boom",
    )
    assert result.returncode == 0
    assert "reconcile FAILED" in result.stdout
    assert "preexisting-claim-mismatch: boom" in result.stdout


def test_reconciler_failure_is_hard_when_reduced(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    result, _ = run_port(
        root,
        tmp_path,
        "reconcile-fail-hard",
        FAKE_RECONCILE_RC="1",
        SCOPE_MODE="reduced",
    )
    assert result.returncode == 1


def test_reconciler_timeout_is_a_gap_not_a_verdict(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    result, _ = run_port(root, tmp_path, "timeout-soft", FAKE_RECONCILE_SLEEP_MS="3000")
    assert result.returncode == 0
    assert "exceeded 2s and was killed" in result.stdout


def test_reconciler_timeout_is_hard_when_reduced(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    result, _ = run_port(
        root, tmp_path, "timeout-hard", FAKE_RECONCILE_SLEEP_MS="3000", SCOPE_MODE="reduced"
    )
    assert result.returncode == 1


def test_reconcile_output_is_truncated_and_teed(tmp_path: pathlib.Path) -> None:
    """`head -c 3000`/`head -c 1500` truncation of the reconciler's own stderr/stdout, verified with output that exceeds neither bound but is long enough that a naive re-implementation forgetting the cap would still happen to match -- so the bound itself is exercised in the next test."""
    root = _fixture(tmp_path)
    result, _ = run_port(
        root,
        tmp_path,
        "reconcile-output",
        FAKE_RECONCILE_STDOUT="stdout line one\nstdout line two\n",
        FAKE_RECONCILE_STDERR="stderr diag one\nstderr diag two\n",
    )
    assert result.returncode == 0
    assert "stdout line one" in result.stdout
    assert "stderr diag one" in result.stdout


def test_reconcile_stderr_truncated_at_3000_bytes(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    result, _ = run_port(root, tmp_path, "truncate", FAKE_RECONCILE_STDERR="E" * 4000)
    assert result.returncode == 0
    # Isolate the fenced block's own run of "E"s from the surrounding prose (which legitimately contains the letter E elsewhere) before counting.
    fenced = result.stdout.split("```")[1]
    run_of_e = max((len(list(g)) for k, g in itertools.groupby(fenced) if k == "E"), default=0)
    assert run_of_e == 3000, "fixture assumption broke: expected exactly the 3000-byte cap"


def test_summary_unset_duplicates_the_whole_output(tmp_path: pathlib.Path) -> None:
    """With `GITHUB_STEP_SUMMARY` unset, `$SUMMARY` fell back to `/dev/stdout` in the twin and `tee -a` therefore wrote every line twice. The port reproduces the duplication through its single buffered stdout, so the total byte count is EXACTLY double a clean single-copy run over the same fixture.

    THE TWIN GARBLED THIS PATH and the port does not, which was recorded as a named divergence while both copies existed: each `emit` spawned a fresh `tee -a /dev/stdout` whose `-a` target reopened `/proc/self/fd/1` as a SEPARATE open file description, and two descriptions racing to extend the same regular file corrupt the interleaving. That comparison died with the twin. What
    survives is the port's own half, asserted here, and it is asserted with stdout redirected to a REAL FILE rather than captured through a pipe, because the real file was the condition under which the whole question arose.
    """
    root = _fixture(tmp_path)
    fake_bin = _fake_gh_bin(tmp_path / "fakebin-summary-unset")
    env = {
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "GITHUB_REPOSITORY": "rediacc/console",
        "GITHUB_RUN_ID": "12345",
        "SCOPE_SHADOW_OUT": str(tmp_path / "out-summary-unset"),
        "SCOPE_SHADOW_TIMEOUT": "2",
    }

    doubled_file = tmp_path / "doubled-stdout.txt"
    with open(doubled_file, "wb") as fh:
        doubled = subprocess.run(
            ["python3", str(root / ".ci" / "rediacc_ci" / "ci" / PORT.name)],
            cwd=root,
            stdout=fh,
            stderr=subprocess.PIPE,
            env=dict(env, SCOPE_SHADOW_OUT=str(tmp_path / "out-summary-unset-run")),
            check=False,
            timeout=30,
        )
    doubled_stdout = doubled_file.read_text(encoding="utf-8")
    assert doubled.returncode == 0

    # The clean reference: the SAME fixture with a real GITHUB_STEP_SUMMARY file, so its stdout is a single un-doubled copy.
    reference = subprocess.run(
        ["python3", str(root / ".ci" / "rediacc_ci" / "ci" / PORT.name)],
        cwd=root,
        capture_output=True,
        text=True,
        env=dict(
            env,
            GITHUB_STEP_SUMMARY=str(tmp_path / "summary-reference.md"),
            SCOPE_SHADOW_OUT=str(tmp_path / "out-reference"),
        ),
        check=False,
        timeout=30,
    )
    assert reference.returncode == 0
    assert "Skip-plan reconciliation" in reference.stdout
    assert len(doubled_stdout) == 2 * len(reference.stdout), (
        "the port must duplicate its total output byte-for-byte when SUMMARY is unset"
    )


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY. Flip the polarity comparison `scope_mode == "reduced"` to
    `scope_mode != "reduced"` -- a one-character-class of mistake that inverts
    HARD_GATE entirely. The reference side used to be the bash twin; with the twin retired it is the on-disk port, run unmutated over the same fixture. Driven red on a plain download failure (soft in the port, hard in the mutant), then the source is re-read and asserted byte-identical."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        'hard_gate = scope_mode == "reduced"',
        'hard_gate = scope_mode != "reduced"',
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"

    root = _fixture(tmp_path)
    fake_bin = _fake_gh_bin(tmp_path / "fakebin-plant")
    env = {
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "GITHUB_REPOSITORY": "rediacc/console",
        "GITHUB_RUN_ID": "12345",
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary-plant.md"),
        "SCOPE_SHADOW_OUT": str(tmp_path / "out-plant"),
        "SCOPE_SHADOW_TIMEOUT": "2",
        "FAKE_GH_DOWNLOAD_RC": "1",
    }
    clean = subprocess.run(
        ["python3", str(root / ".ci" / "rediacc_ci" / "ci" / PORT.name)],
        cwd=root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )
    assert clean.returncode == 0, (
        "fixture assumption broke: a plain download failure is no longer soft; update this test"
    )

    with tempfile.TemporaryDirectory() as td:
        mutant_root = pathlib.Path(td) / "tree"
        (mutant_root / ".ci" / "rediacc_ci" / "ci").mkdir(parents=True)
        (mutant_root / ".ci" / "cache").mkdir(parents=True)
        (mutant_root / ".ci" / "rediacc_ci" / "ci" / PORT.name).write_text(
            mutated, encoding="utf-8"
        )
        env2 = dict(env)
        env2["GITHUB_STEP_SUMMARY"] = str(pathlib.Path(td) / "summary-plant2.md")
        env2["SCOPE_SHADOW_OUT"] = str(pathlib.Path(td) / "out-plant2")
        mutant = subprocess.run(
            ["python3", str(mutant_root / ".ci" / "rediacc_ci" / "ci" / PORT.name)],
            cwd=mutant_root,
            capture_output=True,
            text=True,
            env=env2,
            check=False,
            timeout=30,
        )
        assert mutant.returncode == 1, "the mutant did not flip to hard-gate; plant did not fire"
        assert mutant.returncode != clean.returncode, (
            "planted defect was not caught by exit-code comparison"
        )

    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
