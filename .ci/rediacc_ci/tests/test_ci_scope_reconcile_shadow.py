"""Differential: `rediacc_ci.ci.scope_reconcile_shadow` against its twin `.ci/scripts/ci/scope-reconcile-shadow.sh` (`ci.yml:1781`).

A FIXTURE TREE, not the real repository: both subjects derive the reconciler path and (by default) the cache directory from their own file location, so each case copies both subjects, PLUS a controllable fake `.cjs` reconciler, into a tree shaped like the repository at the right relative depth.

RECORDING FAKES FOR `gh`, on PATH (seam is PATH, same technique as `ci-stop-elite`'s fake docker): `gh run download` and `gh api` are the only two subcommands either subject calls. `node` and `timeout` are the REAL binaries -- the fake `.cjs` reconciler controls exit code, output, and an optional sleep (to drive the `bounded()` timeout path) via environment variables, so there is
no need to fake `node` itself.

EVERY CASE SETS `GITHUB_STEP_SUMMARY` TO A REAL FILE, matching the ONLY environment this script ever actually runs in (`ci.yml:1781`, inside GitHub Actions, which always sets it). `test_summary_unset_falls_back_to_stdout_but_diverges_on_corruption` is the one case that leaves it unset, and it is a NAMED DIVERGENCE, not an equivalence assertion -- see the port module's own docstring
for the measured, deterministic, kernel-file-offset-race cause (two independent open file descriptions racing to extend the same regular file), confirmed unreachable in production because GitHub Actions always sets the variable.

K=5 LEDGER: `.ci/shadow/w7p6-scope-reconcile-shadow.observations.jsonl`.
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
TWIN = ROOT / ".ci" / "scripts" / "ci" / "scope-reconcile-shadow.sh"
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
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "ci" / TWIN.name)
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


# Every external command the twin invokes (directly, or via a builtin that still needs the binary on PATH for a non-builtin shell): dirname, mkdir, tee, timeout, rm, head, gh, node. `bash` and `python3` are the runners themselves. On this host `gh` and `bash` both resolve through `/usr/bin` (and its `/bin` alias), so excluding "the directory gh lives in" would take the runner down
# with it -- a curated symlink farm avoids that entirely.
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
    subject: pathlib.Path,
    root: pathlib.Path,
    *,
    env: dict[str, str],
    with_fake_gh: bool = True,
) -> subprocess.CompletedProcess[str]:
    subject_dir = (
        root / ".ci" / "scripts" / "ci"
        if subject.suffix == ".sh"
        else root / ".ci" / "rediacc_ci" / "ci"
    )
    runner = ["bash"] if subject.suffix == ".sh" else ["python3"]
    full_env = dict(env)
    if with_fake_gh:
        fake_bin = _fake_gh_bin(root.parent / f"fakebin-{subject.name}")
        full_env["PATH"] = f"{fake_bin}:{full_env.get('PATH', os.environ.get('PATH', ''))}"
    return subprocess.run(
        [*runner, str(subject_dir / subject.name)],
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
    """A minimal, deterministic env: real GITHUB_STEP_SUMMARY file, a fresh SCOPE_SHADOW_OUT, short GH_TIMEOUT so the timeout tests stay fast."""
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


def run_both(root: pathlib.Path, tmp_path: pathlib.Path, label: str, **extra: str):
    old_env, old_summary = _base_env(tmp_path, f"old-{label}", **extra)
    new_env, new_summary = _base_env(tmp_path, f"new-{label}", **extra)
    old = _run(TWIN, root, env=old_env)
    new = _run(PORT, root, env=new_env)
    return old, new, old_summary, new_summary


def _assert_agree(old, new, label: str) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    assert new.stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new.stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )


def test_success_soft_gate(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    old, new, old_summary, new_summary = run_both(root, tmp_path, "success-soft")
    assert old.returncode == 0
    _assert_agree(old, new, "success-soft")
    assert old_summary.read_text(encoding="utf-8") == new_summary.read_text(encoding="utf-8")
    assert "reconciled" in old.stdout


def test_success_hard_gate(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    old, new, _, _ = run_both(root, tmp_path, "success-hard", SCOPE_MODE="reduced")
    assert old.returncode == 0
    _assert_agree(old, new, "success-hard")
    assert "hard gate: true" in old.stdout


def test_node_missing_is_a_gap(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    curated = _curated_bin(tmp_path / "bin-no-node", omit="node")
    env, _ = _base_env(tmp_path, "node-missing")
    env["PATH"] = str(curated)
    old = _run(TWIN, root, env=env, with_fake_gh=False)
    env2, _ = _base_env(tmp_path, "node-missing-2")
    env2["PATH"] = str(curated)
    new = _run(PORT, root, env=env2, with_fake_gh=False)
    assert old.returncode == 0
    _assert_agree(old, new, "node-missing-soft")
    assert "`node` is not available" in old.stdout


def test_gh_missing_is_a_hard_failure_when_reduced(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    curated = _curated_bin(tmp_path / "bin-no-gh", omit="gh")
    env, _ = _base_env(tmp_path, "gh-missing", SCOPE_MODE="reduced")
    env["PATH"] = str(curated)
    old = _run(TWIN, root, env=env, with_fake_gh=False)
    env2, _ = _base_env(tmp_path, "gh-missing-2", SCOPE_MODE="reduced")
    env2["PATH"] = str(curated)
    new = _run(PORT, root, env=env2, with_fake_gh=False)
    assert old.returncode == 1
    _assert_agree(old, new, "gh-missing-hard")
    assert "`gh` is not available" in old.stdout


def test_download_failure_is_a_gap_when_soft(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    old, new, _, _ = run_both(root, tmp_path, "dl-fail-soft", FAKE_GH_DOWNLOAD_RC="1")
    assert old.returncode == 0
    _assert_agree(old, new, "download-fail-soft")
    assert "no attested plan for this run" in old.stdout


def test_download_failure_is_hard_when_reduced(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    old, new, _, _ = run_both(
        root, tmp_path, "dl-fail-hard", FAKE_GH_DOWNLOAD_RC="1", SCOPE_MODE="reduced"
    )
    assert old.returncode == 1
    _assert_agree(old, new, "download-fail-hard")
    assert "RECONCILIATION FAILED" in old.stdout


def test_download_retries_once_then_succeeds(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    old_attempt = tmp_path / "attempt-old"
    new_attempt = tmp_path / "attempt-new"
    old, new, _, _ = run_both(
        root,
        tmp_path,
        "dl-retry",
        FAKE_GH_DOWNLOAD_FAIL_FIRST="1",
        FAKE_GH_DOWNLOAD_ATTEMPT_FILE=str(old_attempt),
    )
    # The port's own recording gets a DIFFERENT attempt-marker file so the two subjects' independent "fail once, then succeed" states do not share state; re-run the port explicitly with its own marker.
    new_env, _ = _base_env(
        tmp_path,
        "dl-retry-new-2",
        FAKE_GH_DOWNLOAD_FAIL_FIRST="1",
        FAKE_GH_DOWNLOAD_ATTEMPT_FILE=str(new_attempt),
    )
    new = _run(
        PORT,
        root,
        env={
            **new_env,
            "PATH": f"{_fake_gh_bin(tmp_path / 'fakebin-retry')}:{os.environ.get('PATH', '')}",
        },
    )
    assert old.returncode == 0
    _assert_agree(old, new, "download-retry")
    assert "the plan download failed; retrying once" in old.stdout


def test_jobs_api_failure_is_a_gap(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    old, new, _, _ = run_both(root, tmp_path, "jobs-fail", FAKE_GH_JOBS_RC="2")
    assert old.returncode == 0
    _assert_agree(old, new, "jobs-fail")
    assert "could not read the jobs API" in old.stdout


def test_reconciler_failure_is_reported(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    old, new, _, _ = run_both(
        root,
        tmp_path,
        "reconcile-fail",
        FAKE_RECONCILE_RC="1",
        FAKE_RECONCILE_STDERR="preexisting-claim-mismatch: boom",
    )
    assert old.returncode == 0
    _assert_agree(old, new, "reconcile-fail-soft")
    assert "reconcile FAILED" in old.stdout
    assert "preexisting-claim-mismatch: boom" in old.stdout


def test_reconciler_failure_is_hard_when_reduced(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    old, new, _, _ = run_both(
        root,
        tmp_path,
        "reconcile-fail-hard",
        FAKE_RECONCILE_RC="1",
        SCOPE_MODE="reduced",
    )
    assert old.returncode == 1
    _assert_agree(old, new, "reconcile-fail-hard")


def test_reconciler_timeout_is_a_gap_not_a_verdict(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    old, new, _, _ = run_both(root, tmp_path, "timeout-soft", FAKE_RECONCILE_SLEEP_MS="3000")
    assert old.returncode == 0
    _assert_agree(old, new, "timeout-soft")
    assert "exceeded 2s and was killed" in old.stdout


def test_reconciler_timeout_is_hard_when_reduced(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    old, new, _, _ = run_both(
        root, tmp_path, "timeout-hard", FAKE_RECONCILE_SLEEP_MS="3000", SCOPE_MODE="reduced"
    )
    assert old.returncode == 1
    _assert_agree(old, new, "timeout-hard")


def test_reconcile_output_is_truncated_and_teed(tmp_path: pathlib.Path) -> None:
    """`head -c 3000`/`head -c 1500` truncation of the reconciler's own stderr/stdout, verified with output that exceeds neither bound but is long enough that a naive re-implementation forgetting the cap would still happen to match -- so the bound itself is exercised in the next test."""
    root = _fixture(tmp_path)
    old, new, _, _ = run_both(
        root,
        tmp_path,
        "reconcile-output",
        FAKE_RECONCILE_STDOUT="stdout line one\nstdout line two\n",
        FAKE_RECONCILE_STDERR="stderr diag one\nstderr diag two\n",
    )
    assert old.returncode == 0
    _assert_agree(old, new, "reconcile-output")
    assert "stdout line one" in old.stdout
    assert "stderr diag one" in old.stdout


def test_reconcile_stderr_truncated_at_3000_bytes(tmp_path: pathlib.Path) -> None:
    root = _fixture(tmp_path)
    long_err = "E" * 4000
    old, new, _, _ = run_both(root, tmp_path, "truncate", FAKE_RECONCILE_STDERR=long_err)
    assert old.returncode == 0
    _assert_agree(old, new, "truncate")
    # Isolate the fenced block's own run of "E"s from the surrounding prose (which legitimately contains the letter E elsewhere) before counting.
    fenced = old.stdout.split("```")[1]
    run_of_e = max((len(list(g)) for k, g in itertools.groupby(fenced) if k == "E"), default=0)
    assert run_of_e == 3000, "fixture assumption broke: expected exactly the 3000-byte cap"


def test_summary_unset_falls_back_to_stdout_but_diverges_on_corruption(
    tmp_path: pathlib.Path,
) -> None:
    """NAMED DIVERGENCE, not an equivalence claim -- see the port module's own docstring. With `GITHUB_STEP_SUMMARY` unset, `$SUMMARY` falls back to `/dev/stdout` and the twin's per-`emit` `tee -a /dev/stdout` corrupts its own duplicate output via a kernel file-offset race. The port's single buffered `sys.stdout` cannot exhibit that race and duplicates cleanly instead. Unreachable
    in production: `ci.yml:1781` always sets `GITHUB_STEP_SUMMARY`.

    THE RACE IS SPECIFIC TO A REGULAR FILE, not a pipe -- measured directly:
    under `subprocess.run(capture_output=True)` (a pipe) the twin's output
    comes back perfectly clean, exactly double the reference length; the corruption reproduces only when stdout is redirected to a real file with `>`, the documented LOCAL RUN shape this script's own header describes. So this one test redirects both subjects' stdout to real files rather than capturing through a pipe, to exercise the actual condition rather than one that happens not
    to trigger it.
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

    old_file = tmp_path / "old-stdout.txt"
    with open(old_file, "wb") as fh:
        old = subprocess.run(
            ["bash", str(root / ".ci" / "scripts" / "ci" / "scope-reconcile-shadow.sh")],
            cwd=root,
            stdout=fh,
            stderr=subprocess.PIPE,
            env=dict(env, SCOPE_SHADOW_OUT=str(tmp_path / "out-summary-unset-old")),
            check=False,
            timeout=30,
        )
    old_stdout = old_file.read_text(encoding="utf-8")

    new_file = tmp_path / "new-stdout.txt"
    with open(new_file, "wb") as fh:
        new = subprocess.run(
            ["python3", str(root / ".ci" / "rediacc_ci" / "ci" / "scope_reconcile_shadow.py")],
            cwd=root,
            stdout=fh,
            stderr=subprocess.PIPE,
            env=dict(env, SCOPE_SHADOW_OUT=str(tmp_path / "out-summary-unset-new")),
            check=False,
            timeout=30,
        )
    new_stdout = new_file.read_text(encoding="utf-8")

    assert old.returncode == 0
    assert new.returncode == 0

    # A clean reference: the SAME fixture, a real GITHUB_STEP_SUMMARY file, so its stdout (still captured through a pipe -- no fallback path involved) is a single un-doubled copy.
    reference = subprocess.run(
        ["bash", str(root / ".ci" / "scripts" / "ci" / "scope-reconcile-shadow.sh")],
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

    # The twin's own header text appears at least once even when corrupted -- this is the "it did something" floor, not an equivalence claim.
    assert "Skip-plan reconciliation" in old_stdout

    # The PORT duplicates cleanly: total byte count is EXACTLY double the clean single-copy reference, regardless of chunk granularity, even when its own stdout is a real file rather than a pipe.
    assert len(new_stdout) == 2 * len(reference.stdout), (
        "the port must duplicate its total output byte-for-byte when SUMMARY is unset"
    )

    # The TWIN does NOT, on a real file: the kernel file-offset race overwrites part of the second copy, so its total length falls short of a clean double (reproduced deterministically on this host).
    assert len(old_stdout) < 2 * len(reference.stdout), (
        "the twin's known kernel-race corruption did not reproduce on a real file "
        "(output is no longer shorter than a clean double); either the environment "
        "changed or the bug was fixed upstream -- re-measure before loosening this "
        "test, and if genuinely fixed, drop this divergence note"
    )


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY. Flip the polarity comparison `scope_mode == "reduced"` to
    `scope_mode != "reduced"` -- a one-character-class of mistake that inverts
    HARD_GATE entirely. Driven red on a plain download failure (soft in the twin, hard in the mutant), then the source is restored byte-identical and re-verified green."""
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
    old = subprocess.run(
        ["bash", str(root / ".ci" / "scripts" / "ci" / "scope-reconcile-shadow.sh")],
        cwd=root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )
    assert old.returncode == 0, (
        "fixture assumption broke: a plain download failure is no longer soft; update this test"
    )

    with tempfile.TemporaryDirectory() as td:
        mutant_root = pathlib.Path(td) / "tree"
        (mutant_root / ".ci" / "rediacc_ci" / "ci").mkdir(parents=True)
        (mutant_root / ".ci" / "cache").mkdir(parents=True)
        (mutant_root / ".ci" / "rediacc_ci" / "ci" / "scope_reconcile_shadow.py").write_text(
            mutated, encoding="utf-8"
        )
        env2 = dict(env)
        env2["GITHUB_STEP_SUMMARY"] = str(pathlib.Path(td) / "summary-plant2.md")
        env2["SCOPE_SHADOW_OUT"] = str(pathlib.Path(td) / "out-plant2")
        new = subprocess.run(
            [
                "python3",
                str(mutant_root / ".ci" / "rediacc_ci" / "ci" / "scope_reconcile_shadow.py"),
            ],
            cwd=mutant_root,
            capture_output=True,
            text=True,
            env=env2,
            check=False,
            timeout=30,
        )
        assert new.returncode == 1, "the mutant did not flip to hard-gate; plant did not fire"
        assert new.returncode != old.returncode, (
            "planted defect was not caught by exit-code comparison"
        )

    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
