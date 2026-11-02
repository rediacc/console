#!/usr/bin/env python3
"""check:ci-proxy-cost-guard -- the executor proxy's container may not grow past its budgeted cost.

WHY THIS EXISTS. The proxy Worker (`workers/proxy`) runs its executor in Cloudflare Containers, billed on provisioned memory while an instance is awake. The one real cost risk, measured in agent/plans/PLAN-cloudflare-proxy.md section 4, is instances pinned awake: 20 `basic` instances 24/7 is about $150/month, 2 is about $15. Two settings bound it. They were lowered on purpose (box A1, 5f9a354ea and 3b96d5133); the instance cap was then raised to 25 per target by operator ruling ASKED:2026-10-26T15:26Z, because one container per org makes demand the sizing rule and `sleepAfter` keeps idle orgs from billing:

  * the executor cap: `[vars] EXECUTOR_CAP` and `EXECUTOR_HEAVY_CAP` of every `workers/proxy/wrangler*.toml`, and `HARD_CAP` / `HARD_HEAVY_CAP` in `workers/proxy/src/capacity.ts`;
  * `sleepAfter` on every container class the config names, in `workers/proxy/src/**`,
    the idle time before an instance sleeps, so a class that drops the line has no budgeted idle bill.

Every config is held to the same budget, the bench Worker (operator order 2026-10-24) included. What a config may NAME (its own region, channel, services, routes) is `rediacc_ci.deploy.proxy_configs.config_refusals`, gated separately by `check:ci-proxy-configs`; this gate counts cost only. `wrangler.template.toml` is the generator's input with `@@...@@` placeholders, not a deployable config, so the scan skips it.

Nothing else noticed a raise: a reviewer reads `EXECUTOR_CAP = "30"` as a capacity tweak. This is missing test 9 of the plan (box A5).

THE RULE. Every `workers/proxy/wrangler*.toml` (the template excepted) declares exactly one `[[containers]]` entry, the `OrgExecutor` of `scheduling_policy = "durable_object"` (PLAN-executor-durable-object-policy.md Design item 7, boxes G1 and C1): the `Container` class and its default-policy entry are retired by migration v3, so a default-policy entry is a finding. The entry carries neither `max_instances` (it caps nothing under that policy) nor `instance_type`. Its cap lives in code: every config carries `[vars] EXECUTOR_CAP` and `EXECUTOR_HEAVY_CAP` as decimal strings at or under MAX_INSTANCES_BUDGET and HEAVY_BUDGET, `workers/proxy/src/capacity.ts` defines `HARD_CAP` and `HARD_HEAVY_CAP` as integer literals at or under the same budgets, and every `instance:` value in the source is one of the allowed literals (`'lite'`, `'standard-1'`, or the one custom object in ALLOWED_CUSTOM_INSTANCE). Every container class a config names is defined under `workers/proxy/src/` and sets `sleepAfter` in its own body, and EVERY `sleepAfter` assignment in that source, the class field or any override, is a literal (`'<n>s|m|h'`, or a number of seconds) at or under SLEEP_AFTER_BUDGET_S. A value this gate cannot read (a variable, a call) is a finding, never a pass: an unknown idle time is an unchecked one. A config's instance count is its `EXECUTOR_CAP`, and its worst-case dollar line is `(cap - heavy) * LIGHT_MONTHLY_USD + heavy * HEAVY_MONTHLY_USD`, at most MAX_CONFIG_MONTHLY_USD per config and MAX_TOTAL_MONTHLY_USD for the deployable set.

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
# Heavy (`standard-1`) instances a target may hold at once (PLAN-executor-durable-object-policy.md Decisions 3).
HEAVY_BUDGET = 5
# Worst-case dollars per config and per deployable set, every instance pinned awake for 30 days (Decisions 4). Memory plus disk at https://developers.cloudflare.com/containers/pricing/ ("+$0.0000025 per additional GiB-second", "+$0.00000007 per additional GB-second"): the LIGHT custom size (1/4 vCPU, 1 GiB, 4 GB) is about $7.21 and `standard-1` (1/2 vCPU, 4 GiB, 8 GB) about $27.37. CPU bills on active use only. 20 x 7.21 + 5 x 27.37 is about $281 per target.
LIGHT_MONTHLY_USD = 7.21
HEAVY_MONTHLY_USD = 27.37
MAX_CONFIG_MONTHLY_USD = 300
MAX_TOTAL_MONTHLY_USD = 2100
DURABLE_POLICY = "durable_object"
# The one custom size LIGHT may use (Spike S1, DU3); every other `instance:` is `lite` or `standard-1`.
ALLOWED_INSTANCE_NAMES = ("lite", "standard-1")
ALLOWED_CUSTOM_INSTANCE = {"vcpu": 0.25, "memoryMib": 1024, "diskMb": 4000}
CAPACITY_REL = ("workers", "proxy", "src", "capacity.ts")
CAP_VARS = (("EXECUTOR_CAP", MAX_INSTANCES_BUDGET), ("EXECUTOR_HEAVY_CAP", HEAVY_BUDGET))
HARD_CAP_NAMES = (("HARD_CAP", MAX_INSTANCES_BUDGET), ("HARD_HEAVY_CAP", HEAVY_BUDGET))
DECIMAL_RE = re.compile(r"^\d+$")
INSTANCE_RE = re.compile(r"\binstance\s*:\s*")
INT_LITERAL_RE = re.compile(r"^\d+$")

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
# The grammar the executor's idle timer reads (org-executor-support.ts, the `sleepAfter` literal): `^(\d+)([smh])$` for a string, seconds for a number.
DURATION_RE = re.compile(r"^(\d+)([smh])$")
NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")
UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600}
MAX_INSTANCES_LINE_RE = re.compile(r"^\s*max_instances\s*=", re.MULTILINE)


def parse_duration(raw: str) -> int | float | None:
    """Seconds for a literal the idle timer accepts, else None (unreadable, so unchecked)."""
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
    """The `[[containers]]` entries and the findings for them: one `durable_object` entry, no `max_instances`, no `instance_type`."""
    config = tomllib.loads(wrangler_text)
    containers = config.get("containers") or []
    lines = [
        line_of(wrangler_text, m.start()) for m in MAX_INSTANCES_LINE_RE.finditer(wrangler_text)
    ]
    findings: list[str] = []
    seen = 0
    for entry in containers:
        name = entry.get("class_name", "<no class_name>")
        policy = entry.get("scheduling_policy", "default")
        has_max = "max_instances" in entry
        where = "%s:%s" % (rel, lines[seen] if has_max and seen < len(lines) else "?")
        if has_max:
            seen += 1
        if policy == DURABLE_POLICY:
            if has_max:
                findings.append(
                    "%s: [[containers]] %s is scheduling_policy = %s and sets max_instances, which "
                    "caps nothing under that policy (wrangler refuses it) and reads as a budget. "
                    "Delete it; the cap is EXECUTOR_CAP in [vars] and HARD_CAP in src/capacity.ts."
                    % (where, name, DURABLE_POLICY)
                )
            if "instance_type" in entry:
                findings.append(
                    "%s: [[containers]] %s is scheduling_policy = %s and sets instance_type, which "
                    "applies only to the default policy. Delete it; each start names its own "
                    "`instance:` size." % (rel, name, DURABLE_POLICY)
                )
            continue
        if policy == "default":
            findings.append(
                "%s: [[containers]] %s uses the default scheduling policy. The `Container` class "
                "is retired (migration v3), so the only entry is the OrgExecutor of "
                "scheduling_policy = %r." % (rel, name, DURABLE_POLICY)
            )
            continue
        findings.append(
            "%s: [[containers]] %s has scheduling_policy = %r, which this gate does not know, "
            "so its cost is unchecked. Use %r." % (rel, name, policy, DURABLE_POLICY)
        )
    if len(containers) > 1:
        findings.append(
            "%s: %d [[containers]] entries; the one entry is the OrgExecutor of "
            "scheduling_policy = %r." % (rel, len(containers), DURABLE_POLICY)
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
                    "%s:%d: class %s sets no sleepAfter, so its idle time has no budgeted value "
                    "(at most %ds). Add `sleepAfter = '2m';` to the class."
                    % (rel, line_of(sources[rel], offset), name, SLEEP_AFTER_BUDGET_S)
                )
    return judged, findings


def is_durable(entry: dict) -> bool:
    return entry.get("scheduling_policy") == DURABLE_POLICY


def is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_cap_var(raw: object) -> int | None:
    """A cap var as the Worker reads it: a plain decimal string only (capacity.ts capFrom)."""
    if isinstance(raw, str) and DECIMAL_RE.match(raw):
        return int(raw)
    return None


def vars_findings(config: dict, rel: str) -> tuple[int, int, list[str]]:
    """`(cap, heavy_cap, findings)` of a config's `[vars]` caps. An absent or unreadable var reads as its budget, an over-budget one as written, so the dollar line is a worst case either way."""
    found: dict[str, int] = {}
    findings: list[str] = []
    config_vars = config.get("vars") or {}
    for key, budget in CAP_VARS:
        parsed = parse_cap_var(config_vars.get(key))
        if key not in config_vars:
            findings.append(
                "%s: a durable_object entry needs [vars] %s as a decimal string at or under %d; "
                'it is missing, so the cap is unchecked. Add `%s = "%d"`.'
                % (rel, key, budget, key, budget)
            )
        elif parsed is None:
            findings.append(
                "%s: [vars] %s = %r is not a decimal string, so the Worker falls back to its hard "
                "cap and this gate cannot read it. Write it as a string of digits at or under %d."
                % (rel, key, config_vars[key], budget)
            )
        elif parsed > budget:
            findings.append(
                '%s: [vars] %s = "%d" is over the budget of %d. Lower it, or raise the budget '
                "constant in .ci/scripts/quality/check_proxy_cost_guard.py together with the "
                "pricing that justifies it." % (rel, key, parsed, budget)
            )
        found[key] = parsed if parsed is not None else budget
    cap, heavy = found["EXECUTOR_CAP"], found["EXECUTOR_HEAVY_CAP"]
    if heavy > cap:
        findings.append(
            "%s: [vars] EXECUTOR_HEAVY_CAP = %d is over EXECUTOR_CAP = %d; heavy instances count "
            "inside the cap." % (rel, heavy, cap)
        )
    return cap, heavy, findings


def routed_count(containers: list[dict], config: dict, rel: str) -> tuple[int, int, list[str]]:
    """`(instances, heavy, findings)` of a config: its `[vars]` caps. A config with no durable entry has none to count; `container_findings` has already refused it."""
    if not any(is_durable(c) for c in containers):
        return 0, 0, []
    return vars_findings(config, rel)


def monthly_usd(instances: int, heavy: int, durable: bool) -> float:
    """Worst-case dollars, every instance awake 30 days."""
    if not durable:
        return instances * LIGHT_MONTHLY_USD
    return (instances - heavy) * LIGHT_MONTHLY_USD + heavy * HEAVY_MONTHLY_USD


def dollar_findings(per_config: dict[str, float], deployable: list[str]) -> list[str]:
    """The per-config and deployable-set dollar rules over `{config name: worst-case USD}`."""
    findings = [
        "workers/proxy/%s: worst case $%.2f/month pinned awake, over the per-config limit of "
        "$%d (Decisions 4). Lower EXECUTOR_CAP or EXECUTOR_HEAVY_CAP."
        % (name, usd, MAX_CONFIG_MONTHLY_USD)
        for name, usd in sorted(per_config.items())
        if usd > MAX_CONFIG_MONTHLY_USD
    ]
    total = sum(per_config[n] for n in deployable)
    if total > MAX_TOTAL_MONTHLY_USD:
        findings.append(
            "workers/proxy: the deployable configs cost $%.2f/month worst case, over the limit of "
            "$%d (Decisions 4)." % (total, MAX_TOTAL_MONTHLY_USD)
        )
    return findings


def strip_comments(text: str) -> str:
    """`text` with `//` and `/* */` comment bodies blanked (newlines kept), string literals respected."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        two = text[i : i + 2]
        if two == "//":
            while i < n and text[i] != "\n":
                i += 1
        elif two == "/*":
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out.append("".join("\n" if c == "\n" else " " for c in text[i:end]))
            i = end
        elif ch in "'\"`":
            j = i + 1
            while j < n and text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            out.append(text[i : j + 1])
            i = j + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_instance(raw: str) -> bool:
    """True when `raw` (an `instance:` value) is one of the allowed literals."""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"`":
        return value[1:-1] in ALLOWED_INSTANCE_NAMES
    if value.startswith("{") and value.endswith("}"):
        fields: dict[str, float] = {}
        for part in value[1:-1].split(","):
            if not part.strip():
                continue
            key, sep, num = part.partition(":")
            if not sep or not NUMBER_RE.match(num.strip()):
                return False
            fields[key.strip()] = float(num.strip())
        return fields == {k: float(v) for k, v in ALLOWED_CUSTOM_INSTANCE.items()}
    return False


def instance_findings(sources: dict[str, str]) -> tuple[int, list[str]]:
    """`(instance values judged, findings)`: every `instance:` value is an allowed literal, so a size cannot grow unseen."""
    findings: list[str] = []
    judged = 0
    for rel, raw_text in sorted(sources.items()):
        text = strip_comments(raw_text)
        for match in INSTANCE_RE.finditer(text):
            start = match.end()
            if text[start : start + 1] == "{":
                end = text.find("}", start)
                value = text[start : end + 1] if end >= 0 else text[start:]
            else:
                tail = re.match(r"[^;,\n}]+", text[start:])
                value = tail.group(0) if tail else ""
            judged += 1
            if not parse_instance(value):
                findings.append(
                    "%s:%d: instance: %s is not an allowed literal ('lite', 'standard-1', or %s), "
                    "so the instance size, and its price, is unchecked. Use one of those, or raise "
                    "the allowlist in .ci/scripts/quality/check_proxy_cost_guard.py together with "
                    "the pricing that justifies it."
                    % (
                        rel,
                        line_of(text, match.start()),
                        " ".join(value.split()),
                        "{ vcpu: 0.25, memoryMib: 1024, diskMb: 4000 }",
                    )
                )
    return judged, findings


def hard_cap_findings(sources: dict[str, str]) -> list[str]:
    """`HARD_CAP` and `HARD_HEAVY_CAP` in capacity.ts are integer literals at or under their budgets."""
    rel = "/".join(CAPACITY_REL)
    text = strip_comments(sources.get(rel, ""))
    findings: list[str] = []
    if not text:
        return [
            "%s is missing, so HARD_CAP and HARD_HEAVY_CAP cannot be checked for a config with a "
            "durable_object entry." % rel
        ]
    for name, budget in HARD_CAP_NAMES:
        match = re.search(r"\bconst\s+%s\b[^=\n]*=\s*([^;\n]+)" % name, text)
        if match is None:
            findings.append(
                "%s: defines no `const %s`, so the code cap is unchecked." % (rel, name)
            )
            continue
        raw = match.group(1).strip()
        where = "%s:%d" % (rel, line_of(text, match.start()))
        if not INT_LITERAL_RE.match(raw):
            findings.append(
                "%s: %s = %s is not an integer literal this gate can read, so the cap is "
                "unchecked. Write it as a literal at or under %d." % (where, name, raw, budget)
            )
        elif int(raw) > budget:
            findings.append(
                "%s: %s = %s is over the budget of %d. Lower it, or raise the budget constant in "
                ".ci/scripts/quality/check_proxy_cost_guard.py together with the pricing that "
                "justifies it." % (where, name, raw, budget)
            )
    return findings


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
    """The deployable-set rule over `{config name: EXECUTOR_CAP}`; the dev config is not in `counts`."""
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
            "workers/proxy: the deployable configs total an executor cap of %d, over the limit of "
            "%d (operator ruling ASKED:2026-10-26T15:26Z: 7 x 25 at most)."
            % (total, MAX_TOTAL_INSTANCES)
        )
    return findings


def check(root: pathlib.Path) -> int:
    containers: list[dict] = []
    findings: list[str] = []
    counts: dict[str, int] = {}
    dollars: dict[str, float] = {}
    any_durable = False
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
        durable = any(is_durable(c) for c in these)
        any_durable = any_durable or durable
        instances, heavy, routed_findings = routed_count(these, tomllib.loads(text), rel)
        findings += routed_findings
        dollars[wrangler.name] = monthly_usd(instances, heavy, durable)
        if wrangler.name != DEV_CONFIG:
            counts[wrangler.name] = instances
    findings += total_findings(counts)
    findings += dollar_findings(dollars, list(counts))
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
    instances_judged, instance_problems = instance_findings(sources)
    findings += instance_problems
    if any_durable:
        findings += hard_cap_findings(sources)
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
        "proxy cost guard: OK, %d container(s) at an executor cap <= %d in %d config(s) "
        "(%d deployable, %d instance(s) in total, at most %d), "
        "%d sleepAfter assignment(s) <= %ds, %d instance size(s) in the allowlist, "
        "worst case $%.2f/month (limit $%d), across %d source file(s)."
        % (
            len(containers),
            MAX_INSTANCES_BUDGET,
            len(configs),
            len(counts),
            sum(counts.values()),
            MAX_TOTAL_INSTANCES,
            judged,
            SLEEP_AFTER_BUDGET_S,
            instances_judged,
            sum(dollars[n] for n in counts),
            MAX_TOTAL_MONTHLY_USD,
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
    control(
        "a default-policy entry fires (the Container class is retired)",
        len(container_findings(SELFTEST_TOML % "2")[1]) == 1,
    )
    control(
        "a default-policy entry with no max_instances fires",
        len(container_findings('[[containers]]\nclass_name = "C"\n')[1]) == 1,
    )
    ok_src = {"s.ts": "export class C {\n  sleepAfter = '2m';\n}\n"}
    control(
        "sleepAfter '2m' in the class is within budget", not sleep_after_findings(ok_src, ["C"])[1]
    )
    control(
        "sleepAfter '10m' fires",
        len(sleep_after_findings({"s.ts": "class C {\n  sleepAfter = '10m';\n}\n"}, ["C"])[1]) == 1,
    )
    control(
        "a class with no sleepAfter fires",
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
    durable = '[[containers]]\nclass_name = "O"\nscheduling_policy = "durable_object"\n%s'
    control("a durable entry with neither field is clean", not container_findings(durable % "")[1])
    control(
        "a durable entry with max_instances fires",
        len(container_findings(durable % "max_instances = 25\n")[1]) == 1,
    )
    control(
        "a durable entry with instance_type fires",
        len(container_findings(durable % 'instance_type = "basic"\n')[1]) == 1,
    )
    control(
        "an unknown scheduling_policy fires",
        len(container_findings(SELFTEST_TOML % "2" + 'scheduling_policy = "x"\n')[1]) == 1,
    )
    control(
        "a second entry beside the durable one fires",
        len(container_findings(durable % "" + durable % "")[1]) == 1,
    )
    good_vars = {"vars": {"EXECUTOR_CAP": "25", "EXECUTOR_HEAVY_CAP": "5"}}
    control("caps of 25 and 5 are clean", not vars_findings(good_vars, "c")[2])
    control(
        'EXECUTOR_CAP = "26" fires',
        len(vars_findings({"vars": {"EXECUTOR_CAP": "26", "EXECUTOR_HEAVY_CAP": "5"}}, "c")[2])
        == 1,
    )
    control(
        'EXECUTOR_HEAVY_CAP = "6" fires',
        len(vars_findings({"vars": {"EXECUTOR_CAP": "25", "EXECUTOR_HEAVY_CAP": "6"}}, "c")[2])
        == 1,
    )
    control(
        "a non-string cap fires",
        len(vars_findings({"vars": {"EXECUTOR_CAP": 25, "EXECUTOR_HEAVY_CAP": "5"}}, "c")[2]) == 1,
    )
    control("absent cap vars fire", len(vars_findings({}, "c")[2]) == 2)
    one: list[dict] = [{"class_name": "O", "scheduling_policy": DURABLE_POLICY}]
    capped = {"vars": {"EXECUTOR_CAP": "10", "EXECUTOR_HEAVY_CAP": "1"}}
    control("a durable entry counts EXECUTOR_CAP", routed_count(one, capped, "c")[0] == 10)
    control(
        "a config with no durable entry counts nothing", routed_count([], capped, "c") == (0, 0, [])
    )
    control(
        "the worst case per target is about $281 and within the limit",
        280 < monthly_usd(25, 5, True) < 282
        and not dollar_findings({"a": monthly_usd(25, 5, True)}, ["a"]),
    )
    control("a config over $300 fires", len(dollar_findings({"a": 301.0}, ["a"])) == 1)
    control(
        "a deployable set over $2,100 fires",
        len(
            dollar_findings(
                {
                    "a": 299.0,
                    "b": 299.0,
                    "c": 299.0,
                    "d": 299.0,
                    "e": 299.0,
                    "f": 299.0,
                    "g": 299.0,
                    "h": 299.0,
                },
                list("abcdefgh"),
            )
        )
        == 1,
    )
    control(
        "the dev config's dollars are not in the set",
        not dollar_findings({"a": 299.0, "dev": 299.0}, ["a"]),
    )
    cap_ok = {
        "workers/proxy/src/capacity.ts": "export const HARD_CAP = 25;\nexport const HARD_HEAVY_CAP = 5;\n"
    }
    control("HARD_CAP 25 and HARD_HEAVY_CAP 5 are clean", not hard_cap_findings(cap_ok))
    for label, old, new in (
        ("HARD_CAP = 30", "HARD_CAP = 25", "HARD_CAP = 30"),
        ("HARD_HEAVY_CAP = 6", "HARD_HEAVY_CAP = 5", "HARD_HEAVY_CAP = 6"),
        ("a non-literal HARD_CAP", "HARD_CAP = 25", "HARD_CAP = LIMIT"),
    ):
        planted = {
            "workers/proxy/src/capacity.ts": cap_ok["workers/proxy/src/capacity.ts"].replace(
                old, new
            )
        }
        control("%s fires" % label, len(hard_cap_findings(planted)) == 1)
    control("a missing capacity.ts fires", len(hard_cap_findings({"x.ts": "1"})) == 1)
    control(
        "a missing HARD_CAP definition fires",
        len(
            hard_cap_findings(
                {"workers/proxy/src/capacity.ts": "export const HARD_HEAVY_CAP = 5;\n"}
            )
        )
        == 1,
    )
    clean = "const A = { light: { instance: { vcpu: 0.25, memoryMib: 1024, diskMb: 4000 } }, heavy: { instance: 'standard-1' }, x: { instance: 'lite' } };\n"
    control("the three allowed sizes are clean", instance_findings({"s.ts": clean}) == (3, []))
    for label, src in (
        ("standard-2", "x = { instance: 'standard-2' };"),
        ("a variable", "x = { instance: SIZE };"),
        ("a second custom object", "x = { instance: { vcpu: 1, memoryMib: 1024, diskMb: 4000 } };"),
        (
            "an extra custom field",
            "x = { instance: { vcpu: 0.25, memoryMib: 1024, diskMb: 4000, extra: 1 } };",
        ),
    ):
        control("instance: %s fires" % label, len(instance_findings({"s.ts": src})[1]) == 1)
    control(
        "an instance: in a comment is not a size",
        instance_findings({"s.ts": "// instance: SIZE\n/* instance: 'standard-4' */\nx = 1;"})
        == (0, []),
    )
    control(
        "a // inside a string does not hide the next size",
        len(instance_findings({"s.ts": "u = 'http://x'; v = { instance: 'standard-2' };"})[1]) == 1,
    )
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
