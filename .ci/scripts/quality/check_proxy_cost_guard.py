#!/usr/bin/env python3
"""check:ci-proxy-cost-guard -- the executor proxy's container may not grow past its budgeted cost.

WHY THIS EXISTS. The proxy Worker (`workers/proxy`) runs its executor in Cloudflare Containers, billed on provisioned memory while an instance is awake. The one real cost risk, measured in agent/plans/PLAN-cloudflare-proxy.md section 4, is instances pinned awake: 20 `basic` instances 24/7 is about $150/month, 2 is about $15. Two settings bound it, and both were lowered on purpose (box A1, 5f9a354ea and 3b96d5133):

  * `max_instances` on every `[[containers]]` entry of `workers/proxy/wrangler.toml`;
  * `sleepAfter` on every container class the config names, in `workers/proxy/src/**`,
    the idle time before an instance sleeps. `@cloudflare/containers` defaults it to
    `'10m'`, so a class that drops the line silently quintuples the idle bill.

Nothing else noticed a raise: a reviewer reads `max_instances = 20` as a capacity tweak. This is missing test 9 of the plan (box A5).

THE RULE. Every `[[containers]]` entry names `max_instances`, an integer at or under MAX_INSTANCES_BUDGET (absent means the platform default, which is not a budget). Every container class it names is defined under `workers/proxy/src/` and sets `sleepAfter` in its own body, and EVERY `sleepAfter` assignment in that source, the class field or any override, is a literal the library parses (`'<n>s|m|h'`, or a number of seconds) at or under SLEEP_AFTER_BUDGET_S. A value this gate cannot read (a variable, a call) is a finding, never a pass: an unknown idle time is an unchecked one.

RAISING THE BUDGET is a decision, not a fix: change the constant below in the same commit as the section 4 pricing that justifies it.

ANTI-VACUITY. Zero `[[containers]]` entries, zero source files, or a missing config is exit 2 (no verdict), never a green. The instrument controls (`--selftest`) run before every real check, in both directions. The success line prints the counts it judged.

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
MAX_INSTANCES_BUDGET = 2
SLEEP_AFTER_BUDGET_S = 120

# `@cloudflare/containers` lib/container.js: the idle timeout a class gets when it sets none.
LIBRARY_DEFAULT_SLEEP_AFTER = "10m"

WRANGLER_REL = ("workers", "proxy", "wrangler.toml")
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
        hits = [(rel, class_body(text, name)) for rel, text in sorted(sources.items())]
        hits = [(rel, body) for rel, body in hits if body is not None]
        if not hits:
            findings.append(
                "workers/proxy/wrangler.toml names container class %s, and no file under "
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


def check(root: pathlib.Path) -> int:
    wrangler = root.joinpath(*WRANGLER_REL)
    if not wrangler.is_file():
        print(
            "NO VERDICT: %s is missing; the gate is not seeing the proxy config." % wrangler,
            file=sys.stderr,
        )
        return 2
    try:
        containers, findings = container_findings(wrangler.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        print("NO VERDICT: %s does not parse as TOML: %s" % (wrangler, exc), file=sys.stderr)
        return 2
    if not containers:
        print(
            "NO VERDICT: %s declares zero [[containers]] entries; the gate is not seeing the container "
            "config, and its green would mean nothing." % wrangler,
            file=sys.stderr,
        )
        return 2
    sources = read_sources(root)
    if not sources:
        print(
            "NO VERDICT: zero source files under %s; the gate cannot see any sleepAfter."
            % root.joinpath(*SOURCE_REL),
            file=sys.stderr,
        )
        return 2
    names = [str(c.get("class_name", "")) for c in containers if c.get("class_name")]
    judged, sleep_findings = sleep_after_findings(sources, names)
    findings += sleep_findings
    if findings:
        for finding in findings:
            print("FAIL  %s" % finding, file=sys.stderr)
        print(
            "proxy cost guard: %d finding(s) over %d container(s), %d sleepAfter assignment(s), "
            "%d source file(s)." % (len(findings), len(containers), judged, len(sources)),
            file=sys.stderr,
        )
        return 1
    print(
        "proxy cost guard: OK, %d container(s) at max_instances <= %d, %d sleepAfter assignment(s) "
        "<= %ds across %d source file(s)."
        % (len(containers), MAX_INSTANCES_BUDGET, judged, SLEEP_AFTER_BUDGET_S, len(sources))
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
    control("max_instances = 20 fires", len(container_findings(SELFTEST_TOML % "20")[1]) == 1)
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
