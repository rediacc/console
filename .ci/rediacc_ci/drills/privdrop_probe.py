"""H2 of agent/plans/PLAN-rediaccfile-unprivileged.md: the per-repo fork test of the Rediaccfile privilege drop, through `./rdc.sh --config eu-bench` on hostinger.

`privdrop-probe/Rediaccfile` is the L1 probe (`lifecycle_privilege.probe_rediaccfile()`, a test keeps the two equal). For one repo `<r>` the runner forks `<r>:privdrop@hostinger` without `--up`, uploads the probe, runs `repo up`, `repo down`, `repo up` again, reads the probe's output files back and judges them with L1's pure verdicts: uid other than 0 with an empty CapEff, every denied read denied, `sudo` stopped by no_new_privs, created files owned by the function's uid. It then prints one verdict table and exits nonzero on any failed verdict. The fork is deleted in the end (`repo delete <r>:privdrop@hostinger`, only the fork), also after a failure. The app-level reads of H2 step 5 (container set, restart counts, `find . -user root`, docker logs grep) are printed by `--collect`.

    PYTHONPATH=.ci python3 -m rediacc_ci.drills.privdrop_probe demo-stackoverflow [--collect] [--dry-run]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from rediacc_ci.drills import lifecycle_privilege as lp

CONFIG = "eu-bench"
MACHINE = "hostinger"
TAG = "privdrop"
PROBE_DIR = Path(__file__).resolve().parent / "privdrop-probe"
# Read-only commands run inside the fork's own shell after the second `repo up` (H2 step 5).
COLLECT = (
    "docker ps -a --format '{{.Names}} {{.State}} {{.Status}}'",
    "docker ps -q | xargs -r docker inspect --format '{{.Name}} restarts={{.RestartCount}}'",
    "find . -user root 2>/dev/null | head -n 20",
    "docker ps -q | xargs -r -n1 docker logs --tail 200 2>&1 | grep -ci 'permission denied\\|operation not permitted'",
)


def fork_ref(repo: str) -> str:
    return "%s:%s@%s" % (repo, TAG, MACHINE)


def rdc_argv(*args: str) -> list[str]:
    return ["./rdc.sh", "--config", CONFIG, *args]


def recipe(repo: str, local_dir: str = str(PROBE_DIR)) -> list[list[str]]:
    """The rdc invocations of H2 steps 2 to 4, in order.

    The fork verb does not start the fork, and `repo sync upload` refuses a repository that is not deployed (measured on hostinger 2026-11-05: VALIDATION_ERROR "not deployed ... Deploy it first"), so the fork is brought up once before the probe lands. That first up runs the app's own up() unprivileged, which is itself an H2 data point.
    """
    ref = fork_ref(repo)
    return [
        rdc_argv("repo", "fork", "%s@%s" % (repo, MACHINE), "--tag", TAG),
        rdc_argv("repo", "up", ref),
        rdc_argv("repo", "sync", "upload", ref, "--local", local_dir.rstrip("/") + "/"),
        rdc_argv("repo", "up", ref),
        rdc_argv("repo", "down", ref),
        rdc_argv("repo", "up", ref),
    ]


def root_retry(repo: str) -> list[list[str]]:
    """H2 step 6, run only when an up failed: the root tier on the fork alone, then up again."""
    ref = fork_ref(repo)
    return [
        rdc_argv("repo", "permission", "grant", ref, "--root"),
        rdc_argv("repo", "up", ref),
    ]


def read_argv(repo: str, name: str) -> list[str]:
    return rdc_argv("term", "connect", fork_ref(repo), "-c", lp.read_command(name))


def delete_argv(repo: str, dry_run: bool) -> list[str]:
    return rdc_argv("repo", "delete", fork_ref(repo), *(["--dry-run"] if dry_run else ["-y"]))


def verdicts(up: dict[str, str], down: dict[str, str]) -> list[tuple[str, bool, str]]:
    """One row per verdict: (name, ok, evidence). An empty probe (the file never arrived) fails every row."""
    rows: list[tuple[str, bool, str]] = []
    for label, probe in (("up", up), ("down", down)):
        for name, fn in (
            ("dropped", lp.dropped_verdict),
            ("denied", lp.denied_verdict),
            ("sudo", lp.sudo_verdict),
            ("owner", lp.owner_verdict),
        ):
            ok, why = fn(probe)
            rows.append(("%s.%s" % (label, name), ok, why))
    return rows


def table(repo: str, rows: list[tuple[str, bool, str]]) -> str:
    lines = ["%s: %s" % (fork_ref(repo), "PASS" if all(r[1] for r in rows) else "FAIL")]
    lines += ["  %-14s %s  %s" % (n, "ok  " if ok else "FAIL", why) for n, ok, why in rows]
    return "\n".join(lines)


def _run(argv: list[str], timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


def run(repo: str, collect: bool = False) -> int:
    """Run the recipe for one repo; 0 only when every verdict holds and every rdc step exited 0."""
    failed = False
    up_failed = False
    try:
        for argv in recipe(repo):
            res = _run(argv)
            print("$ %s -> rc=%d" % (" ".join(argv), res.returncode))
            if res.returncode != 0:
                # rdc prints its JSON error envelope on stdout and progress on stderr: both are needed to see why.
                print(res.stdout[-2000:], file=sys.stderr)
                print(res.stderr[-2000:], file=sys.stderr)
                failed = True
                # A failing up is itself the H2 data point (a fork's container cannot bind a host port its running original holds, hostinger 2026-11-05); the fork stays mounted, so the probe can still land. A failing fork or upload leaves nothing to probe.
                if argv[3:5] == ["repo", "up"]:
                    up_failed = True
                    continue
                break
        if up_failed:
            # H2 step 6: the root tier on the FORK alone, then up again, to tell a privilege failure from one the root tier does not fix either.
            for argv in root_retry(repo):
                res = _run(argv)
                print("$ %s -> rc=%d (step 6)" % (" ".join(argv), res.returncode))
                if res.returncode != 0:
                    print(res.stdout[-2000:], file=sys.stderr)
                    print(res.stderr[-2000:], file=sys.stderr)
        probes: dict[str, dict[str, str]] = {}
        for name in (lp.UP_FILE, lp.DOWN_FILE):
            probes[name] = lp.parse_probe(_run(read_argv(repo, name)).stdout)
        rows = verdicts(probes[lp.UP_FILE], probes[lp.DOWN_FILE])
        print(table(repo, rows))
        failed = failed or not all(r[1] for r in rows)
        if collect:
            for cmd in COLLECT:
                res = _run(rdc_argv("term", "connect", fork_ref(repo), "-c", cmd))
                print("$ %s -> rc=%d\n%s" % (cmd, res.returncode, res.stdout.strip()))
    finally:
        for dry in (True, False):
            argv = delete_argv(repo, dry)
            res = _run(argv)
            print("$ %s -> rc=%d" % (" ".join(argv), res.returncode))
            if dry:
                print(res.stdout.strip())
            if res.returncode != 0:
                failed = True
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("repo")
    ap.add_argument(
        "--collect", action="store_true", help="also print the H2 step 5 app-level reads"
    )
    ap.add_argument("--dry-run", action="store_true", help="print the recipe, run nothing")
    args = ap.parse_args(argv)
    if args.dry_run:
        for a in recipe(args.repo):
            print(" ".join(a))
        print(" ".join(delete_argv(args.repo, True)))
        return 0
    return run(args.repo, args.collect)


if __name__ == "__main__":
    sys.exit(main())
