#!/usr/bin/env python3
"""check:ci-proxy-deploy-dry-run -- every proxy deploy target compiles, with fake credentials and no image build.

WHY THIS EXISTS. The proxy has six CD targets (edge and stable, in each region of regions.json) and bench, and each deploys through `deploy_proxy --target T --region R`. Nothing in CI ran that path: a renamed config, a refusal that fired on a real config, or a wrangler key the pinned wrangler rejects surfaced on the first real deploy. `--dry-run` runs the config refusals and `wrangler deploy --dry-run --containers-rollout none`, which compiles the Worker without building or updating a container and needs no credentials, no fetch and no staged artifacts. The image itself is built and booted by check:ci-proxy-image-smoke.

THE TARGETS ARE DERIVED, NOT LISTED. `regions.json` gives the regions; each region contributes `stable` and `edge`, and bench is the seventh. A region added there is dry-run here with no edit. The expected config per target (`wrangler.<region>.toml`, `wrangler.edge-<region>.toml`, `wrangler.bench.toml`) is checked against the `(config: ...)` the run printed, so a target that compiled the wrong file is a finding, not a pass.

FAKE CREDENTIALS. Every `CLOUDFLARE_*` and `ACCOUNT_*` variable of the caller is dropped and `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` are set to obvious fakes, so the run proves a dry run needs none, and a dry run that starts asking for a secret fails here instead of in a lane that holds one.

ANTI-VACUITY. Zero targets, a regions.json that cannot be read, or a missing wrangler install (the fix is in the message) is exit 2, never a green. Each target needs rc 0 AND the run's own `Dry run passed` line AND the expected config name in its output; a command that exits 0 and prints nothing is a finding. The success line prints the target count and each config.

`--entry <script.py>` replaces `python3 -m rediacc_ci.deploy.deploy_proxy` with a script taking the same arguments (the pytest module drives a fake one); `--root <dir>` points the gate at a tree copy.

Exit 0 every target compiled, 1 on findings, 2 when a control fails or no verdict is possible.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

REGIONS_REL = "regions.json"
WRANGLER_REL = ("workers", "proxy", "node_modules", ".bin", "wrangler")
MODULE = "rediacc_ci.deploy.deploy_proxy"
PASSED_LINE = "Dry run passed"
FAKE_API_VALUE = "fake-dry-run-token"
FAKE_ACCOUNT = "0" * 32
DROPPED_PREFIXES = ("CLOUDFLARE_", "ACCOUNT_", "REDIACC_TOKEN")
TIMEOUT_S = 180
WRANGLER_FIX = "npm ci --prefix workers/proxy"


def targets_from_regions(regions: list[dict]) -> list[tuple[str, str | None]]:
    """`(target, region)` pairs: stable and edge per region, then bench (no region flag)."""
    out: list[tuple[str, str | None]] = []
    for region in regions:
        rid = str(region["id"])
        out.append(("stable", rid))
        out.append(("edge", rid))
    out.append(("bench", None))
    return out


def expected_config(target: str, region: str | None) -> str:
    if target == "bench":
        return "wrangler.bench.toml"
    if target == "edge":
        return "wrangler.edge-%s.toml" % region
    return "wrangler.%s.toml" % region


def label(target: str, region: str | None) -> str:
    return target if region is None else "%s/%s" % (target, region)


def argv_for(entry: str | None, target: str, region: str | None) -> list[str]:
    head = [sys.executable, entry] if entry else [sys.executable, "-m", MODULE]
    tail = ["--target", target]
    if region is not None:
        tail += ["--region", region]
    return [*head, *tail, "--dry-run"]


def fake_env(base: dict[str, str]) -> dict[str, str]:
    """The caller's env without any credential, plus the two fakes."""
    env = {k: v for k, v in base.items() if not k.startswith(DROPPED_PREFIXES)}
    env["CLOUDFLARE_API_TOKEN"] = FAKE_API_VALUE
    env["CLOUDFLARE_ACCOUNT_ID"] = FAKE_ACCOUNT
    return env


def judge(target: str, region: str | None, rc: int, output: str) -> list[str]:
    """Findings for one run; empty when it compiled the expected config."""
    name = label(target, region)
    config = expected_config(target, region)
    findings: list[str] = []
    if rc != 0:
        findings.append(
            "%s: deploy_proxy --dry-run exited %d. Its last output:\n%s"
            % (name, rc, "\n".join("    " + line for line in output.strip().splitlines()[-12:]))
        )
        return findings
    if PASSED_LINE not in output:
        findings.append(
            "%s: exited 0 without printing %r, so the run did not reach the compile."
            % (name, PASSED_LINE)
        )
    if "(config: %s)" % config not in output:
        findings.append(
            "%s: the run did not name `(config: %s)`; it compiled a different file or none."
            % (name, config)
        )
    return findings


def load_regions(root: pathlib.Path) -> list[dict]:
    data = json.loads((root / REGIONS_REL).read_text(encoding="utf-8"))
    regions = data.get("regions") if isinstance(data, dict) else None
    if not isinstance(regions, list):
        raise TypeError("%s carries no regions list" % REGIONS_REL)
    return regions


def run_one(
    root: pathlib.Path, entry: str | None, target: str, region: str | None
) -> tuple[int, str]:
    env = fake_env(dict(os.environ))
    # The entry imports rediacc_ci from `.ci`; the repo's own tooling sets this the same way.
    env["PYTHONPATH"] = str(root / ".ci") + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.run(
            argv_for(entry, target, region),
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, "timed out after %ds" % TIMEOUT_S
    return proc.returncode, proc.stdout + proc.stderr


def check(root: pathlib.Path, entry: str | None) -> int:
    try:
        regions = load_regions(root)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("NO VERDICT: %s cannot be read: %s" % (root / REGIONS_REL, exc), file=sys.stderr)
        return 2
    pairs = targets_from_regions(regions)
    if len(pairs) < 2:
        print(
            "NO VERDICT: %d target(s) derived from %s; the gate is not seeing the regions."
            % (len(pairs), REGIONS_REL),
            file=sys.stderr,
        )
        return 2
    if entry is None and not root.joinpath(*WRANGLER_REL).exists():
        print(
            "NO VERDICT: %s is missing, so wrangler cannot compile anything. Fix: run `%s`."
            % (root.joinpath(*WRANGLER_REL), WRANGLER_FIX),
            file=sys.stderr,
        )
        return 2
    findings: list[str] = []
    for target, region in pairs:
        rc, output = run_one(root, entry, target, region)
        problems = judge(target, region, rc, output)
        findings += problems
        print(
            "  %s  %s -> %s"
            % (
                "FAIL" if problems else "PASS",
                label(target, region),
                expected_config(target, region),
            ),
            file=sys.stderr,
        )
    if findings:
        for finding in findings:
            print("FAIL  %s" % finding, file=sys.stderr)
        print(
            "proxy deploy dry run: %d finding(s) over %d target(s). Fix the config or the deploy path the run names; do not skip the target."
            % (len(findings), len(pairs)),
            file=sys.stderr,
        )
        return 1
    print(
        "proxy deploy dry run: OK, %d target(s) compiled with fake credentials (%s)."
        % (len(pairs), ", ".join(expected_config(t, r) for t, r in pairs))
    )
    return 0


def selftest() -> bool:
    ok = True

    def control(text: str, passed: bool) -> None:
        nonlocal ok
        print("  %s  %s" % ("PASS" if passed else "FAIL", text), file=sys.stderr)
        ok = ok and passed

    regions = [{"id": "eu"}, {"id": "us"}, {"id": "asia"}]
    pairs = targets_from_regions(regions)
    control(
        "three regions give six CD targets and bench",
        len(pairs) == 7 and pairs[-1] == ("bench", None),
    )
    control(
        "stable maps to wrangler.<region>.toml",
        expected_config("stable", "us") == "wrangler.us.toml",
    )
    control(
        "edge maps to wrangler.edge-<region>.toml",
        expected_config("edge", "asia") == "wrangler.edge-asia.toml",
    )
    control(
        "bench maps to wrangler.bench.toml", expected_config("bench", None) == "wrangler.bench.toml"
    )
    control("bench takes no --region", "--region" not in argv_for(None, "bench", None))
    control(
        "a region target passes --region <id> before --dry-run",
        argv_for(None, "edge", "eu")[-3:] == ["--region", "eu", "--dry-run"],
    )
    env = fake_env(
        {
            "CLOUDFLARE_API_TOKEN": "real",
            "ACCOUNT_ED25519_PUBLIC_KEY": "k",
            "REDIACC_TOKEN": "t",
            "PATH": "/bin",
        }
    )
    control(
        "a real credential is dropped and replaced by the fake",
        env["CLOUDFLARE_API_TOKEN"] == FAKE_API_VALUE
        and "ACCOUNT_ED25519_PUBLIC_KEY" not in env
        and "REDIACC_TOKEN" not in env,
    )
    control("PATH survives", env["PATH"] == "/bin")
    good = (
        "-> Dry run: compiling (config: wrangler.us.toml)...\n%s. Nothing was deployed.\n"
        % PASSED_LINE
    )
    control("a run naming its config and passing is clean", not judge("stable", "us", 0, good))
    control("a non-zero exit fires", len(judge("stable", "us", 1, "boom")) == 1)
    control("rc 0 with no output fires twice (silent pass)", len(judge("stable", "us", 0, "")) == 2)
    control("rc 0 naming the wrong config fires", len(judge("edge", "us", 0, good)) == 1)
    return ok


def main(argv: list[str]) -> int:
    root = pathlib.Path(__file__).resolve().parents[3]
    entry: str | None = None
    args = list(argv)
    for flag in ("--root", "--entry"):
        if flag in args:
            i = args.index(flag)
            if i + 1 >= len(args):
                print("%s needs a value" % flag, file=sys.stderr)
                return 2
            if flag == "--root":
                root = pathlib.Path(args[i + 1]).resolve()
            else:
                entry = args[i + 1]
            del args[i : i + 2]
    if not selftest():
        print("proxy deploy dry run: the instrument controls failed; no verdict.", file=sys.stderr)
        return 2
    if "--selftest" in args:
        print("proxy deploy dry run: selftest OK.")
        return 0
    return check(root, entry)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
