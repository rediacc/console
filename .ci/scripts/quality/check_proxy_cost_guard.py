#!/usr/bin/env python3
"""check:ci-proxy-cost-guard -- the executor proxy's container may not grow past its budgeted cost.

WHY THIS EXISTS. The proxy Worker (`workers/proxy`) runs its executor in Cloudflare Containers, billed on provisioned memory while an instance is awake. The one real cost risk, measured in agent/plans/PLAN-cloudflare-proxy.md section 4, is instances pinned awake: 20 `basic` instances 24/7 is about $150/month, 2 is about $15. Two settings bound it. They were lowered on purpose (box A1, 5f9a354ea and 3b96d5133); the instance cap was then raised to 25 per target by operator ruling ASKED:2026-10-26T15:26Z, because one container per org makes demand the sizing rule and `sleepAfter` keeps idle orgs from billing:

  * `max_instances` on every `[[containers]]` entry of every `workers/proxy/wrangler*.toml`;
  * `sleepAfter` on every container class the config names, in `workers/proxy/src/**`,
    the idle time before an instance sleeps. `@cloudflare/containers` defaults it to
    `'10m'`, so a class that drops the line silently quintuples the idle bill.

Every config is held to the same budget, the bench Worker (operator order 2026-10-24) included. What a config may NAME (its own region, channel, services, routes) is `rediacc_ci.deploy.proxy_configs.config_refusals`, gated separately by `check:ci-proxy-configs`; this gate counts cost only. `wrangler.template.toml` is the generator's input with `@@...@@` placeholders, not a deployable config, so the scan skips it.

Nothing else noticed a raise: a reviewer reads `max_instances = 20` as a capacity tweak. This is missing test 9 of the plan (box A5).

THE RULE. Every `[[containers]]` entry names `max_instances`, an integer at or under MAX_INSTANCES_BUDGET (absent means the platform default, which is not a budget). Every container class it names is defined under `workers/proxy/src/` and sets `sleepAfter` in its own body, and EVERY `sleepAfter` assignment in that source, the class field or any override, is a literal the library parses (`'<n>s|m|h'`, or a number of seconds) at or under SLEEP_AFTER_BUDGET_S. A value this gate cannot read (a variable, a call) is a finding, never a pass: an unknown idle time is an unchecked one.

RAISING THE BUDGET is a decision, not a fix: change the constant below in the same commit as the section 4 pricing that justifies it.

ANTI-VACUITY. Zero `[[containers]]` entries in either config, zero source files, or a missing config is exit 2 (no verdict), never a green. The instrument controls (`--selftest`) run before every real check, in both directions. The success line prints the counts it judged.

`--root <dir>` points the gate at a copy of the tree; the pytest module (`.ci/rediacc_ci/tests/test_check_proxy_cost_guard.py`) plants violations into fixture copies and never edits the real config.

Exit 0 within budget, 1 on findings, 2 when a control fails or no verdict is possible.

---- gate ----
step: Proxy cost guard
needs: none
lane: quality-static
why: The proxy's only real cost risk is container instances pinned awake. max_instances
     and sleepAfter were lowered on purpose (20 instances 24/7 is about $150/month, 2 is
     about $15); a raise reads like a capacity tweak in review, so the budget is a gate.
---- end gate ----
"""

from __future__ import annotations

import pathlib
import re
import sys
import tomllib

# THE BUDGET (PLAN-cloudflare-proxy.md section 4, recommendations 1 and 2). Raise either only together with the pricing that justifies it.
# MAX_INSTANCES_BUDGET is 25 by operator ruling ASKED:2026-10-26T15:26Z ("Per-org, raise the cap"): one executor container per org (PLAN-console-executor-multi-org), so the cap is sized by demand, up to 25 per config, at most MAX_DEPLOYABLE_CONFIGS deployable configs, at most MAX_TOTAL_INSTANCES (7 x 25) across them. It supersedes the earlier ruling ASKED:2026-10-25T19:08Z ("1 per target, 7 total but 21 max") for max_instances only; sleepAfter stays 2m, so an idle org sleeps. The cost alarm that replaces the low cap is the container spend threshold of `cf_usage_report` (.ci/config/cf-spend-guard.json, `report.containers_*`).
MAX_INSTANCES_BUDGET = 25
MAX_DEPLOYABLE_CONFIGS = 7
MAX_TOTAL_INSTANCES = 175
SLEEP_AFTER_BUDGET_S = 120

# `@cloudflare/containers` lib/container.js: the idle timeout a class gets when it sets none.
LIBRARY_DEFAULT_SLEEP_AFTER = "10m"

PROXY_REL = ("workers", "proxy")
CONFIG_GLOB = "wrangler*.toml"
BENCH_CONFIG = "wrangler.bench.toml"
EU_CONFIG = "wrangler.eu.toml"
REQUIRED_CONFIGS = (EU_CONFIG, BENCH_CONFIG)
# The local-development config is judged against the per-config budget but is not deployed, so it does not count toward the deployable set.
DEV_CONFIG = "wrangler.dev.toml"
# The generator input: placeholders, never deployed.
TEMPLATE_CONFIG = "wrangler.template.toml"
SOURCE_REL = ("workers", "proxy", "src")
SOURCE_SUFFIXES = (".ts", ".mts", ".js", ".mjs")
# Tests assert the value; they do not set it for the deployed Worker.
TEST_PARTS = ("__tests__",)

# `sleepAfter = '2m'` (class field), `this.sleepAfter = 300`, `{ sleepAfter: "5m" }`. The value is everything up to the end of the statement or property, so a non-literal is captured whole and refused rather than skipped.
SLEEP_AFTER_RE = re.compile(r"\bsleepAfter\s*[:=](?!=)\s*([^;,\n}]+)")
# The library's own grammar (lib/helpers.js parseTimeExpression): `^(\d+)([smh])$` for a string, seconds for a number.
DURATION_RE = re.compile(r"^(\d+)([smh])$")
NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")
UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600}
MAX_INSTANCES_LINE_RE = re.compile(r"^\s*max_instances\s*=", re.MULTILINE)


def parse_duration(raw: str) -> int | float | None:
    """Seconds for a literal `@cloudflare/containers` accepts, else None (unreadable, so unchecked)."""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"`":
        match = DURATION_RE.match(value[1:-1])
        if match is None:
            return None
        return int(match.group(1)) * UNIT_SECONDS[match.group(2)]
    if NUMBER_RE.match(value):
        return float(value) if "." in value else int(value)
    return None


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def class_body(text: str, name: str) -> tuple[int, str] | None:
    """`(offset, body)` of `class <name> ... { ... }`, braces matched; None when the class is not in `text`."""
    match = re.search(r"\bclass\s+%s\b[^{]*\{" % re.escape(name), text)
    if match is None:
        return None
    depth = 1
    i = match.end()
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return match.end(), text[match.end() : i - 1]


def container_findings(
    wrangler_text: str, rel: str = "workers/proxy/wrangler.toml"
) -> tuple[list[dict], list[str]]:
    """The `[[containers]]` entries and the max_instances findings for them."""
    config = tomllib.loads(wrangler_text)
    containers = config.get("containers") or []
    lines = [
        line_of(wrangler_text, m.start()) for m in MAX_INSTANCES_LINE_RE.finditer(wrangler_text)
    ]
    findings: list[str] = []
    seen = 0
    for entry in containers:
        name = entry.get("class_name", "<no class_name>")
        if "max_instances" not in entry:
            findings.append(
                "%s: [[containers]] %s sets no max_instances, so the platform default applies "
                "instead of the budget of %d. Add `max_instances = %d`."
                % (rel, name, MAX_INSTANCES_BUDGET, MAX_INSTANCES_BUDGET)
            )
            continue
        where = "%s:%s" % (rel, lines[seen] if seen < len(lines) else "?")
        seen += 1
        value = entry["max_instances"]
        if not isinstance(value, int) or isinstance(value, bool):
            findings.append(
                "%s: [[containers]] %s max_instances = %r is not an integer; the budget is %d."
                % (where, name, value, MAX_INSTANCES_BUDGET)
            )
        elif value > MAX_INSTANCES_BUDGET:
            findings.append(
                "%s: [[containers]] %s max_instances = %d is over the budget of %d "
                "(PLAN-cloudflare-proxy.md section 4: each awake basic instance is about $7.50/month). "
                "Lower it, or raise MAX_INSTANCES_BUDGET in .ci/scripts/quality/check_proxy_cost_guard.py "
                "together with the pricing that justifies it."
                % (where, name, value, MAX_INSTANCES_BUDGET)
            )
    return containers, findings


def sleep_after_findings(sources: dict[str, str], class_names: list[str]) -> tuple[int, list[str]]:
    """`(assignments judged, findings)` over the source files, keyed by repo-relative path."""
    findings: list[str] = []
    judged = 0
    for rel, text in sorted(sources.items()):
        for match in SLEEP_AFTER_RE.finditer(text):
            judged += 1
            raw = match.group(1).strip()
            where = "%s:%d" % (rel, line_of(text, match.start()))
            seconds = parse_duration(raw)
            if seconds is None:
                findings.append(
                    "%s: sleepAfter = %s is not a literal this gate can read, so the idle time is "
                    "unchecked. Write it as a literal ('2m', '90s', or a number of seconds) at or "
                    "under %ds." % (where, raw, SLEEP_AFTER_BUDGET_S)
                )
            elif seconds > SLEEP_AFTER_BUDGET_S:
                findings.append(
                    "%s: sleepAfter = %s is %ss idle, over the budget of %ds; an idle instance "
                    "bills memory the whole time. Lower it, or raise SLEEP_AFTER_BUDGET_S in "
                    ".ci/scripts/quality/check_proxy_cost_guard.py together with the pricing that "
                    "justifies it." % (where, raw, seconds, SLEEP_AFTER_BUDGET_S)
                )
    for name in class_names:
        hits: list[tuple[str, tuple[int, str]]] = []
        for rel, text in sorted(sources.items()):
            found_body = class_body(text, name)
            if found_body is not None:
                hits.append((rel, found_body))
        if not hits:
            findings.append(
                "workers/proxy/wrangler*.toml names container class %s, and no file under "
                "workers/proxy/src defines it, so its sleepAfter cannot be checked." % name
            )
            continue
        for rel, (offset, body) in hits:
            if SLEEP_AFTER_RE.search(body) is None:
                findings.append(
                    "%s:%d: class %s sets no sleepAfter, so @cloudflare/containers applies its "
                    "default of '%s', over the budget of %ds. Add `sleepAfter = '2m';` to the class."
                    % (
                        rel,
                        line_of(sources[rel], offset),
                        name,
                        LIBRARY_DEFAULT_SLEEP_AFTER,
                        SLEEP_AFTER_BUDGET_S,
                    )
                )
    return judged, findings


def read_sources(root: pathlib.Path) -> dict[str, str]:
    src = root.joinpath(*SOURCE_REL)
    out: dict[str, str] = {}
    if not src.is_dir():
        return out
    for path in sorted(src.rglob("*")):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        rel_parts = path.relative_to(src).parts
        if (
            any(part in TEST_PARTS for part in rel_parts)
            or ".test." in path.name
            or ".spec." in path.name
        ):
            continue
        out[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    return out


def total_findings(counts: dict[str, int]) -> list[str]:
    """The deployable-set rule over `{config name: summed max_instances}`; the dev config is not in `counts`."""
    findings: list[str] = []
    if len(counts) > MAX_DEPLOYABLE_CONFIGS:
        findings.append(
            "workers/proxy: %d deployable configs (%s), over the limit of %d (operator ruling "
            "ASKED:2026-10-25T19:08Z: seven deployable targets in all)."
            % (len(counts), ", ".join(sorted(counts)), MAX_DEPLOYABLE_CONFIGS)
        )
    total = sum(counts.values())
    if total > MAX_TOTAL_INSTANCES:
        findings.append(
            "workers/proxy: the deployable configs total max_instances = %d, over the limit of %d "
            "(operator ruling ASKED:2026-10-26T15:26Z: 7 x 25 at most)."
            % (total, MAX_TOTAL_INSTANCES)
        )
    return findings


def check(root: pathlib.Path) -> int:
    containers: list[dict] = []
    findings: list[str] = []
    counts: dict[str, int] = {}
    proxy_dir = root.joinpath(*PROXY_REL)
    configs = (
        [c for c in sorted(proxy_dir.glob(CONFIG_GLOB)) if c.name != TEMPLATE_CONFIG]
        if proxy_dir.is_dir()
        else []
    )
    for required in REQUIRED_CONFIGS:
        if not any(c.name == required for c in configs):
            print(
                "NO VERDICT: %s is missing; the gate is not seeing the proxy config."
                % proxy_dir.joinpath(required),
                file=sys.stderr,
            )
            return 2
    for wrangler in configs:
        rel = "/".join((*PROXY_REL, wrangler.name))
        text = wrangler.read_text(encoding="utf-8")
        try:
            these, these_findings = container_findings(text, rel)
        except tomllib.TOMLDecodeError as exc:
            print("NO VERDICT: %s does not parse as TOML: %s" % (wrangler, exc), file=sys.stderr)
            return 2
        if not these:
            print(
                "NO VERDICT: %s declares zero [[containers]] entries; the gate is not seeing the "
                "container config, and its green would mean nothing." % wrangler,
                file=sys.stderr,
            )
            return 2
        containers += these
        findings += these_findings
        if wrangler.name != DEV_CONFIG:
            counts[wrangler.name] = sum(
                c["max_instances"]
                for c in these
                if isinstance(c.get("max_instances"), int)
                and not isinstance(c["max_instances"], bool)
            )
    for name, config_total in sorted(counts.items()):
        if config_total > MAX_INSTANCES_BUDGET:
            findings.append(
                "workers/proxy/%s: its [[containers]] entries total max_instances = %d, over the "
                "per-config budget of %d." % (name, config_total, MAX_INSTANCES_BUDGET)
            )
    findings += total_findings(counts)
    sources = read_sources(root)
    if not sources:
        print(
            "NO VERDICT: VACUOUS, zero source files under %s; the gate cannot see any sleepAfter."
            % root.joinpath(*SOURCE_REL),
            file=sys.stderr,
        )
        return 2
    names = sorted({str(c.get("class_name", "")) for c in containers if c.get("class_name")})
    judged, sleep_findings = sleep_after_findings(sources, names)
    findings += sleep_findings
    if findings:
        for finding in findings:
            print("FAIL  %s" % finding, file=sys.stderr)
        print(
            "proxy cost guard: %d finding(s) over %d container(s) in %d config(s), %d sleepAfter "
            "assignment(s), %d source file(s)."
            % (len(findings), len(containers), len(configs), judged, len(sources)),
            file=sys.stderr,
        )
        return 1
    print(
        "proxy cost guard: OK, %d container(s) at max_instances <= %d in %d config(s) "
        "(%d deployable, %d instance(s) in total, at most %d), "
        "%d sleepAfter assignment(s) <= %ds across %d source file(s)."
        % (
            len(containers),
            MAX_INSTANCES_BUDGET,
            len(configs),
            len(counts),
            sum(counts.values()),
            MAX_TOTAL_INSTANCES,
            judged,
            SLEEP_AFTER_BUDGET_S,
            len(sources),
        )
    )
    return 0


SELFTEST_TOML = """
[[containers]]
class_name = "C"
image = "./Dockerfile"
max_instances = %s
"""


def selftest() -> bool:
    ok = True

    def control(label: str, passed: bool) -> None:
        nonlocal ok
        print("  %s  %s" % ("PASS" if passed else "FAIL", label), file=sys.stderr)
        ok = ok and passed

    control("'2m' is 120s", parse_duration("'2m'") == 120)
    control('"90s" is 90s', parse_duration('"90s"') == 90)
    control("a bare number is seconds", parse_duration("300") == 300)
    control("'1h' is 3600s", parse_duration("'1h'") == 3600)
    control("a variable is unreadable", parse_duration("IDLE") is None)
    control("'2 m' is not the library grammar", parse_duration("'2 m'") is None)
    control("max_instances = 2 is within budget", not container_findings(SELFTEST_TOML % "2")[1])
    control("max_instances = 26 fires", len(container_findings(SELFTEST_TOML % "26")[1]) == 1)
    control('max_instances = "2" fires', len(container_findings(SELFTEST_TOML % '"2"')[1]) == 1)
    control(
        "an absent max_instances fires",
        len(container_findings('[[containers]]\nclass_name = "C"\n')[1]) == 1,
    )
    ok_src = {"s.ts": "export class C extends Container {\n  sleepAfter = '2m';\n}\n"}
    control(
        "sleepAfter '2m' in the class is within budget", not sleep_after_findings(ok_src, ["C"])[1]
    )
    control(
        "sleepAfter '10m' fires",
        len(sleep_after_findings({"s.ts": "class C {\n  sleepAfter = '10m';\n}\n"}, ["C"])[1]) == 1,
    )
    control(
        "a class with no sleepAfter fires (library default)",
        len(sleep_after_findings({"s.ts": "class C {\n  x = 1;\n}\n"}, ["C"])[1]) == 1,
    )
    control(
        "an over-budget override outside the class fires",
        len(
            sleep_after_findings(
                {"s.ts": "class C {\n  sleepAfter = '2m';\n}\nopts = { sleepAfter: '1h' };\n"},
                ["C"],
            )[1]
        )
        == 1,
    )
    control(
        "a non-literal sleepAfter fires",
        len(sleep_after_findings({"s.ts": "class C {\n  sleepAfter = IDLE;\n}\n"}, ["C"])[1]) == 1,
    )
    control(
        "a comparison is not an assignment",
        sleep_after_findings(
            {"s.ts": "class C {\n  sleepAfter = '1m';\n}\nif (a.sleepAfter == b) {}\n"}, ["C"]
        )[0]
        == 1,
    )
    control(
        "a class the config names and no file defines fires",
        len(sleep_after_findings({"s.ts": "class D {\n  sleepAfter = '1m';\n}\n"}, ["C"])[1]) == 1,
    )
    control(
        "seven deployable configs of 25 are within the set",
        not total_findings(dict.fromkeys("abcdefg", 25)),
    )
    control(
        "an eighth deployable config fires", len(total_findings(dict.fromkeys("abcdefgh", 1))) == 1
    )
    control("a total of 176 fires", len(total_findings({"a": 88, "b": 88})) == 1)
    return ok


def main(argv: list[str]) -> int:
    root = pathlib.Path(__file__).resolve().parents[3]
    args = list(argv)
    if "--root" in args:
        i = args.index("--root")
        if i + 1 >= len(args):
            print("--root needs a directory", file=sys.stderr)
            return 2
        root = pathlib.Path(args[i + 1]).resolve()
        del args[i : i + 2]
    selftest_only = "--selftest" in args
    if not selftest():
        print("proxy cost guard: the instrument controls failed; no verdict.", file=sys.stderr)
        return 2
    if selftest_only:
        print("proxy cost guard: selftest OK.")
        return 0
    return check(root)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
