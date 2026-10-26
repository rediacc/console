#!/usr/bin/env python3
"""check:ci-worker-observability-budget -- every Worker's telemetry signals stay inside the sampling budget.

WHY THIS EXISTS. Workers Observability bills ingestion past 50 GB and storage past 10 GB-month. The volume is small today (agent/plans/PLAN-cloudflare-spend-guard.md T4: about 0.9 percent of the allowance), but a Worker config that drops its `head_sampling_rate` runs at the platform default of 1, and a `persist = true` keeps a second copy at Cloudflare. Neither shows in review as a cost change, so the budget is a gate (box T5).

THE RULE, read from the `worker_observability` object of `.ci/config/cf-spend-guard.json`:

  * every enabled `logs` or `traces` signal of every `workers/*/wrangler*.toml` (the proxy template and the local dev config excluded) carries an explicit numeric `head_sampling_rate` in (0, 1];
  * that rate is at or under `sampling_ceiling`, unless the config is named in `sampling_exempt`, where it is judged against the rate listed there instead. An exemption is never inferred;
  * a config matching a `persist_disallowed` glob never sets `persist = true`, and a signal that does not persist must name at least one destination, so its data is exported somewhere;
  * a signal or the whole `[observability]` table that is `enabled = false` is not judged.

ANTI-VACUITY. Zero configs parsed, an unreadable config, or a missing `worker_observability` object is exit 2 (no verdict). `--selftest` runs planted controls in both directions before the real check. The success line prints the counts it judged.

Exit 0 within budget, 1 on findings, 2 when a control fails or no verdict is possible.

---- gate ----
step: Worker observability budget
needs: none
lane: quality-static
why: A Worker config without an explicit head_sampling_rate runs at the platform default of 1, and persist = true
     keeps a second copy at Cloudflare; neither reads as a cost change in review, so the sampling ceiling is a gate.
---- end gate ----
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import pathlib
import sys
import tomllib
from typing import TypeGuard

CONFIG_REL = (".ci", "config", "cf-spend-guard.json")
EXCLUDED = ("wrangler.template.toml", "wrangler.dev.toml")
SIGNALS = ("logs", "traces")


def config_paths(root: pathlib.Path) -> list[pathlib.Path]:
    found = sorted(root.glob("workers/*/wrangler*.toml"))
    return [p for p in found if p.name not in EXCLUDED]


def rel(root: pathlib.Path, path: pathlib.Path) -> str:
    return path.relative_to(root).as_posix()


def is_rate(value: object) -> TypeGuard[float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value <= 1


def signal_findings(
    name: str, signal: str, block: dict, ceiling: float, exempt: dict, disallowed: list[str]
) -> list[str]:
    out: list[str] = []
    rate = block.get("head_sampling_rate")
    if not is_rate(rate):
        out.append(
            "%s [observability.%s] has no explicit head_sampling_rate in (0, 1] (got %r)"
            % (name, signal, rate)
        )
    else:
        limit = ceiling
        if name in exempt:
            limit = exempt[name]["rate"]
        if rate > limit:
            out.append(
                "%s [observability.%s] head_sampling_rate %s is above %s%s"
                % (
                    name,
                    signal,
                    rate,
                    limit,
                    " (its sampling_exempt rate)" if name in exempt else " (sampling_ceiling)",
                )
            )
    persist = block.get("persist", True)
    if persist is True and any(fnmatch.fnmatch(name, pattern) for pattern in disallowed):
        out.append(
            "%s [observability.%s] persists in Cloudflare (persist is true or unset); persist_disallowed covers it"
            % (name, signal)
        )
    if persist is not True and not block.get("destinations"):
        out.append(
            "%s [observability.%s] does not persist and names no destination, so its data goes nowhere"
            % (name, signal)
        )
    return out


def judge(name: str, config: dict, rules: dict) -> tuple[list[str], int]:
    """Findings and the number of enabled signals judged for one parsed config."""
    obs = config.get("observability")
    if not isinstance(obs, dict) or obs.get("enabled") is False:
        return [], 0
    findings: list[str] = []
    judged = 0
    for signal in SIGNALS:
        block = obs.get(signal)
        if block is None and signal == "logs" and obs.get("enabled") is True:
            # `[observability] enabled = true` alone turns logs on at the platform defaults (rate 1, persisted); the
            # table-level rate is the only knob such a config sets, and the missing rate is a finding.
            block = {k: obs[k] for k in ("head_sampling_rate",) if k in obs}
        if not isinstance(block, dict) or block.get("enabled") is False:
            continue
        judged += 1
        findings += signal_findings(
            name,
            signal,
            block,
            rules["sampling_ceiling"],
            rules["sampling_exempt"],
            rules["persist_disallowed"],
        )
    return findings, judged


def load_rules(path: pathlib.Path) -> dict | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))["worker_observability"]
        ceiling = raw["sampling_ceiling"]
        exempt = raw["sampling_exempt"]
        disallowed = raw["persist_disallowed"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not is_rate(ceiling) or not isinstance(exempt, dict) or not isinstance(disallowed, list):
        return None
    for entry in exempt.values():
        if not isinstance(entry, dict) or not is_rate(entry.get("rate")) or not entry.get("why"):
            return None
    return {
        "sampling_ceiling": ceiling,
        "sampling_exempt": exempt,
        "persist_disallowed": disallowed,
    }


def check(root: pathlib.Path, config_file: pathlib.Path | None = None) -> int:
    rules = load_rules(config_file or root.joinpath(*CONFIG_REL))
    if rules is None:
        print(
            "check_worker_observability_budget: no readable worker_observability object in cf-spend-guard.json",
            file=sys.stderr,
        )
        return 2
    paths = config_paths(root)
    findings: list[str] = []
    judged = 0
    parsed = 0
    for path in paths:
        try:
            config = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            print(
                "check_worker_observability_budget: cannot parse %s: %s" % (rel(root, path), exc),
                file=sys.stderr,
            )
            return 2
        parsed += 1
        found, count = judge(rel(root, path), config, rules)
        findings += found
        judged += count
    if parsed == 0:
        print(
            "check_worker_observability_budget: zero workers/*/wrangler*.toml parsed",
            file=sys.stderr,
        )
        return 2
    stale = sorted(name for name in rules["sampling_exempt"] if not root.joinpath(name).is_file())
    findings += ["sampling_exempt names %s, which is not a config" % name for name in stale]
    if findings:
        for line in findings:
            print("FAIL " + line, file=sys.stderr)
        return 1
    print(
        "check_worker_observability_budget: ok, %d configs, %d enabled signals judged, ceiling %s, %d exempt"
        % (parsed, judged, rules["sampling_ceiling"], len(rules["sampling_exempt"]))
    )
    return 0


RULES = {
    "sampling_ceiling": 0.1,
    "sampling_exempt": {"workers/a/wrangler.edge.toml": {"rate": 1, "why": "x"}},
    "persist_disallowed": ["workers/*/wrangler*.toml"],
}


def selftest() -> bool:
    def signals(rate: str = "0.1", persist: str = "false", dest: str = '["d"]') -> dict:
        body = "[observability]\nenabled = true\n[observability.logs]\nenabled = true\n"
        if rate:
            body += "head_sampling_rate = %s\n" % rate
        body += "persist = %s\ndestinations = %s\n" % (persist, dest)
        return tomllib.loads(body)

    cases = [
        ("clean config passes", "workers/a/wrangler.eu.toml", signals(), 0),
        ("rate above the ceiling fails", "workers/a/wrangler.eu.toml", signals(rate="1"), 1),
        ("missing rate fails", "workers/a/wrangler.eu.toml", signals(rate=""), 1),
        (
            "persist true on a disallowed config fails",
            "workers/a/wrangler.eu.toml",
            signals(persist="true"),
            1,
        ),
        (
            "no destination without persist fails",
            "workers/a/wrangler.eu.toml",
            signals(dest="[]"),
            1,
        ),
        (
            "exempt config at its listed rate passes",
            "workers/a/wrangler.edge.toml",
            signals(rate="1"),
            0,
        ),
        (
            "disabled observability is not judged",
            "workers/a/wrangler.eu.toml",
            {"observability": {"enabled": False}},
            0,
        ),
    ]
    ok = True
    for label, name, config, want in cases:
        got = 1 if judge(name, config, RULES)[0] else 0
        if got != want:
            print(
                "selftest control failed: %s (wanted %d, got %d)" % (label, want, got),
                file=sys.stderr,
            )
            ok = False
    return ok


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[3]
    )
    parser.add_argument(
        "--config",
        type=pathlib.Path,
        default=None,
        help="rules file, default .ci/config/cf-spend-guard.json under --root",
    )
    parser.add_argument("--selftest", action="store_true", help="run only the planted controls")
    args = parser.parse_args(argv)
    if not selftest():
        return 2
    if args.selftest:
        print("check_worker_observability_budget: selftest ok")
        return 0
    return check(args.root, args.config)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
