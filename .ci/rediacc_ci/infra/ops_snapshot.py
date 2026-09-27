#!/usr/bin/env python3
"""Prepared-VM snapshot for the E2E VM jobs (T2.17, PLAN-ci-time-budget).

Replaces `.ci/scripts/test/ops-snapshot.sh` (deleted; ruling 7, 2026-09-06, refuses new bash under `.ci`). Called from five jobs in `.github/workflows/ct-tests.yml`, one subcommand per workflow step:

    ops_snapshot.py key <name>                 outputs t0, and key + enabled=true when a snapshot can be used
    ops_snapshot.py restore <name> <t0>        outputs ready=true when the VMs came back from the snapshot
    ops_snapshot.py prepare <name> [<config>]  outputs ready=true when the VMs were prepared and captured

The snapshot lives in `$RUNNER_TEMP/ops-snapshot/<name>`, and the workflow's cache steps carry it between runs. Every outcome appends its seconds to `$GITHUB_STEP_SUMMARY`, because the plan's 3-minute restore is a hypothesis until measured.

NOTHING HERE FAILS THE JOB ON AN OPERATIONAL MISS. A missing key, a failed restore or a failed capture leaves the test step on its normal path, which prepares the VMs itself and reports any real failure there -- every subcommand returns 0 on those paths. A missing tool (`git`, `npx`) or a missing CI contract (`RUNNER_TEMP`, `GITHUB_OUTPUT`, `GITHUB_STEP_SUMMARY`) is not an operational miss and does fail the job, the same way the twin's `require_cmd` and its unguarded `$RUNNER_TEMP`/`$GITHUB_OUTPUT`/`$GITHUB_STEP_SUMMARY` references did under `set -u`.

Env:
    OPS_SNAPSHOT  'on' enables the snapshot; any other value, unset included, is the kill switch and forces the normal path.
    GITHUB_OUTPUT, GITHUB_STEP_SUMMARY, RUNNER_TEMP  set by GitHub Actions.

Outside Actions, after an E2E `.env` exists:

    OPS_SNAPSHOT=on GITHUB_OUTPUT=/dev/stdout GITHUB_STEP_SUMMARY=/dev/null RUNNER_TEMP=/tmp \\
        PYTHONPATH=.ci python3 -m rediacc_ci.infra.ops_snapshot key workers
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time

from rediacc_ci import paths
from rediacc_ci.core import common

USAGE = "usage: ops_snapshot.py key|restore|prepare <name> [<t0>|<playwright-config>]"

# The binary the E2E harness drives (create_e2e_env --renet-path), so the key and the capture see the renet that provisioned the VMs.
RENET = "/usr/bin/renet"
ENV_FILE = "packages/e2e-tests/.env"


class Outputs:
    """The step outputs, step summary and snapshot directory a workflow step hands this program.

    Bundled so every subcommand reaches them the same way a test's fixture does: three tmp paths standing in for the real Actions runner.
    """

    def __init__(self, name: str, output_path: str, summary_path: str, runner_temp: str) -> None:
        self.name = name
        self.output_path = output_path
        self.summary_path = summary_path
        self.snap_dir = pathlib.Path(runner_temp) / "ops-snapshot"

    def out(self, line: str) -> None:
        """`echo "$1" >>"$GITHUB_OUTPUT"`."""
        with open(self.output_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def note(self, message: str) -> None:
        """`echo "ops-snapshot $NAME: $1" | tee -a "$GITHUB_STEP_SUMMARY"`: printed once, appended once."""
        text = "ops-snapshot %s: %s" % (self.name, message)
        print(text)
        with open(self.summary_path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def _du_sh(path: pathlib.Path) -> str:
    """`du -sh "$path" 2>/dev/null | cut -f1`, empty on any failure or empty output."""
    proc = subprocess.run(
        ["du", "-sh", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        return ""
    return proc.stdout.split("\n", 1)[0].split("\t", 1)[0]


def key_cmd(io: Outputs) -> int:
    """`key` (twin :34-46). Always exits 0: the kill switch, a missing key and a missing tool are the only branches, and only the last one is a real failure."""
    io.out("t0=%d" % int(time.time()))

    ops_snapshot = os.environ.get("OPS_SNAPSHOT", "")
    if ops_snapshot != "on":
        io.note("off (OPS_SNAPSHOT=%s); normal preparation" % (ops_snapshot or "unset"))
        return 0

    try:
        common.require_cmd("git")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    proc = subprocess.run(
        [RENET, "ops", "snapshot", "key", "--name", io.name, "--env-file", ENV_FILE],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        io.note(
            "no key (renet's reason is above; usually the base image is not cached yet); "
            "normal preparation"
        )
        return 0
    key = proc.stdout.rstrip("\n")

    rev = subprocess.run(
        ["git", "-C", "private/renet", "rev-parse", "--short=12", "HEAD"],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    if rev.returncode != 0:
        # Command-substitution failure under the twin's `set -e`: the script dies here, with git's own stderr (already on the console, uncaptured) and git's own exit status.
        return rev.returncode
    short_sha = rev.stdout.rstrip("\n")
    month = time.strftime("%Y-%m", time.gmtime())

    io.out("key=ops-snapshot-%s-%s-%s" % (key, short_sha, month))
    io.out("enabled=true")
    return 0


def restore_cmd(io: Outputs, t0: str) -> int:
    """`restore` (twin :48-58). Always exits 0: a failed restore is reported and left to the test step's own normal preparation."""
    start = time.time()
    outcome = "restore-failed"
    proc = subprocess.run(
        [
            RENET,
            "ops",
            "snapshot",
            "restore",
            "--name",
            io.name,
            "--from",
            str(io.snap_dir),
            "--env-file",
            ENV_FILE,
        ],
        check=False,
    )
    if proc.returncode == 0:
        io.out("ready=true")
        outcome = "restored"
    else:
        print(
            "::warning title=ops snapshot::restore failed; "
            "the test step prepares the VMs the normal way"
        )
    now = time.time()
    io.note(
        "cache hit, %s; restore %ds, cache download plus restore %ds "
        "(harness steps 2-8 still run inside the test step)"
        % (outcome, int(now - start), int(now - float(t0)))
    )
    return 0


def prepare_cmd(io: Outputs, config: str | None) -> int:
    """`prepare` (twin :60-77). Always exits 0 past the tool check: a failed prepare or a failed save is reported and left to the test step's own normal preparation."""
    try:
        common.require_cmd("npx")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    args = ["--pass-with-no-tests", "--grep", "ops-snapshot prepare-only run matches no test"]
    if config:
        args = ["--config", config, *args]

    start = time.time()
    env = dict(os.environ)
    env["E2E_JSON_REPORT_FILE"] = "reports/bridge-logs/ops-snapshot-prepare.json"
    # The suite's globalSetup (steps 1-8) runs; the grep matches no test.
    proc = subprocess.run(
        ["npx", "playwright", "test", *args],
        cwd=str(paths.repo_root() / "packages" / "e2e-tests"),
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        print(
            "::warning title=ops snapshot::preparation failed; "
            "the test step prepares again and reports the cause"
        )
        io.note("cache miss, prepare failed after %ds" % int(time.time() - start))
        return 0

    prepared = time.time()
    outcome = "save-failed"
    save = subprocess.run(
        [
            RENET,
            "ops",
            "snapshot",
            "save",
            "--name",
            io.name,
            "--out",
            str(io.snap_dir),
            "--env-file",
            ENV_FILE,
        ],
        check=False,
    )
    if save.returncode == 0:
        io.out("ready=true")
        outcome = "saved"
    else:
        print(
            "::warning title=ops snapshot::save failed; the test step prepares the VMs the normal way"
        )
    now = time.time()
    size = _du_sh(io.snap_dir) or "0"
    io.note(
        "cache miss; prepare %ds, %s in %ds, size %s"
        % (int(prepared - start), outcome, int(now - prepared), size)
    )
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(USAGE, file=sys.stderr)
        return 1
    cmd, name = argv[0], argv[1]

    os.chdir(paths.repo_root())

    try:
        runner_temp = common.require_var("RUNNER_TEMP")
        github_output = common.require_var("GITHUB_OUTPUT")
        github_summary = common.require_var("GITHUB_STEP_SUMMARY")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    io = Outputs(name, github_output, github_summary, runner_temp)

    if cmd == "key":
        return key_cmd(io)
    if cmd == "restore":
        if len(argv) < 3:
            print(USAGE, file=sys.stderr)
            return 1
        return restore_cmd(io, argv[2])
    if cmd == "prepare":
        config = argv[2] if len(argv) > 2 else None
        return prepare_cmd(io, config)

    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
