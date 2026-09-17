#!/usr/bin/env python3
"""How many processes the harness starts for one lifecycle event. The counter
W5 P0 said it had built and did not.

    python3 .claude/rediacc_hooks/execcount.py            the table
    python3 .claude/rediacc_hooks/execcount.py --json     the same, machine readable

WHY THIS FILE EXISTS AT ALL. W5's stated target is "2 processes per Bash tool
call" and W5 P6 recorded "456 execs per Bash call to 35". Neither number can be
reproduced from the tree: on 2026-09-09,

    grep -rlnP 'strace|GUARD_PASS|HOOKS_ONLY|FORK_COUNT' .ci .claude scripts

returns ZERO files, and `git ls-files | grep -iE 'strace|exec-baseline'` returns
zero as well. The fork counter W5 P0 lists as a deliverable is not in the
repository. A target measured against a baseline nobody can recompute is not a
target, it is a slogan, and the whole W5 spine hangs off it. This module is the
baseline, and `.ci/policy/hook-exec-baseline.json` is where its answer is pinned
so that a change to the wiring has to say so.

WHY NOT strace, WHICH IS THE OBVIOUS INSTRUMENT. Three reasons and any one is
disqualifying: it does not exist on macOS, it needs ptrace capability that a
container commonly withholds, and it measures a RUN rather than the wiring, so
its answer depends on which guard happened to short-circuit that day. A baseline
CI cannot reproduce on demand is the same class of problem as the baseline that
went missing. So this counts the wiring, statically, out of
`.claude/settings.json`, and says exactly what it is counting.

WHAT IT COUNTS, STATED NARROWLY SO NOBODY QUOTES IT FOR SOMETHING ELSE. One
`hooks[].command` entry in `.claude/settings.json` is one process the HARNESS
starts. That is the number here. It is a floor on the true exec count, never the
whole of it: `bash x.sh` that pipes through `jq` costs three more, and the
in-guard forks are exactly what `dispatch.py --chain` was built to collapse.
Those are a separate measurement and this module does not pretend to make it.
The distinction is the reason the printed column is called `harness processes`
and not `execs`.

THE MATCHER SEMANTICS ARE NOT DOCUMENTED ANYWHERE IN THIS TREE, so both
readings are computed rather than one being assumed. `.claude/settings.json`
carries three PreToolUse matchers and they are not written in one style:
`^(Edit|MultiEdit|Write|NotebookEdit)$` is anchored, `Bash` and
`AskUserQuestion` are bare. Under a `re.search` reading a bare `Bash` also
matches the tool `BashOutput`; under `re.fullmatch` it does not. Nothing in the
repository settles which the harness does, and guessing would bake a number in
that is either three or twelve depending on a fact nobody checked. So:

  * both counts are computed for every probe tool,
  * a tool where they DISAGREE is an ambiguity, reported by name,
  * and the ambiguity set is pinned in the baseline with a reason each, so a
    NEW one is a finding rather than a quiet extra row.

An anchored matcher has no ambiguity, which makes the pinned set also a to-do
list: it shrinks by anchoring the matcher, not by editing this file.

ANTI-VACUITY. `count_entries` on wiring it cannot see returns nothing, and every
caller here treats that as a refusal rather than as a zero. An empty hooks
object, an event with no entries, a probe set that matches no matcher: each is a
distinct exception with its own sentence. The failure this guards against is the
one that already happened once, which is a baseline artifact that stopped being
produced and was noticed a workstream later.
"""

import argparse
import json
import pathlib
import re
import sys

# The events that fire per TOOL CALL. Their cost depends on which tool, so they
# are the only two the probe table applies to; everything else in settings.json
# fires once per lifecycle moment and is counted per event.
TOOL_EVENTS = ("PreToolUse", "PostToolUse")

# A matcher spelling that means "every tool". `None` is the key being absent, which is how every wildcard row in this repository's settings.json is written
# today; the other two are accepted because the harness's own documentation uses
# them and a future edit may.
WILDCARD_MATCHERS = (None, "", "*")


class WiringError(Exception):
    """The wiring cannot be read, so there is no count. Never a zero."""


def load_settings(path):
    """The parsed `.claude/settings.json`, or WiringError naming the file.

    Deliberately not tolerant. A settings file that does not parse is not a
    session with no hooks, it is a session whose hooks the harness also could
    not read, and answering "0 processes" for it would be the best-looking
    number this module can print.
    """
    p = pathlib.Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise WiringError(
            "cannot read the hook wiring at %s (%s), so no exec count exists to "
            "report. This is a refusal, not a count of zero." % (p, exc)
        ) from exc
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WiringError("%s is not valid JSON: %s" % (p, exc)) from exc
    if not isinstance(obj, dict):
        raise WiringError("%s does not hold a JSON object at the top level" % p)
    return obj


def parse_entries(settings):
    """Every harness-started command, as (event, matcher, command) triples.

    One triple per `hooks[].command`, which is one process. The shape is
    flattened here rather than at each call site so that the two counting
    functions below cannot disagree about what an entry is.
    """
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        raise WiringError(
            "the settings object has no `hooks` mapping, so this module is not "
            "seeing the wiring at all; its green would mean nothing"
        )
    out = []
    for event in sorted(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            raise WiringError("hooks[%r] is not a list of matcher groups" % event)
        for group in groups:
            if not isinstance(group, dict):
                raise WiringError("a matcher group under hooks[%r] is not an object" % event)
            matcher = group.get("matcher")
            commands = group.get("hooks")
            if not isinstance(commands, list):
                raise WiringError(
                    "the matcher group %r under hooks[%r] has no `hooks` list" % (matcher, event)
                )
            for entry in commands:
                if not isinstance(entry, dict):
                    raise WiringError("a hook entry under hooks[%r] is not an object" % event)
                command = entry.get("command")
                if not isinstance(command, str) or not command.strip():
                    raise WiringError(
                        "a hook entry under hooks[%r] has no `command` string; the harness "
                        "would start nothing for it and this module would undercount" % event
                    )
                out.append((event, matcher, command))
    if not out:
        raise WiringError(
            "the wiring parsed to ZERO hook commands. Either settings.json holds no "
            "hooks or this parser has stopped seeing them; both are refusals, "
            "because a baseline of zero is the failure shape that started W5 P0 over"
        )
    return out


def matches(matcher, tool, *, anchored):
    """Does `matcher` select `tool`, under one of the two readings.

    `anchored=True` is `re.fullmatch`, `anchored=False` is `re.search`. Both are
    offered because the harness's rule is not written down anywhere in this
    repository; see the module docstring. An invalid regex is a WiringError and
    not a False, because a matcher the harness cannot compile is a matcher whose
    real behaviour this module has no opinion about.
    """
    if matcher in WILDCARD_MATCHERS:
        return True
    try:
        pattern = re.compile(matcher)
    except re.error as exc:
        raise WiringError(
            "matcher %r is not a valid regular expression: %s" % (matcher, exc)
        ) from exc
    if anchored:
        return pattern.fullmatch(tool) is not None
    return pattern.search(tool) is not None


def tool_cost(entries, tool, *, anchored):
    """`{"PreToolUse": n, "PostToolUse": m, "total": n + m}` for one tool call."""
    out = {}
    for event in TOOL_EVENTS:
        out[event] = sum(
            1
            for ev, matcher, _ in entries
            if ev == event and matches(matcher, tool, anchored=anchored)
        )
    out["total"] = sum(out[event] for event in TOOL_EVENTS)
    return out


def event_cost(entries, event):
    """Harness processes for a lifecycle event that is not a tool call.

    No matcher applies: `Stop`, `SessionStart` and the compaction events fire
    every entry they carry. Counting them the same way as a tool call would
    silently apply a `Bash` matcher to an event that has no tool.
    """
    return sum(1 for ev, _, _ in entries if ev == event)


def non_tool_events(entries):
    """The events present in the wiring that are not PreToolUse/PostToolUse."""
    return sorted({ev for ev, _, _ in entries} - set(TOOL_EVENTS))


def ambiguous_tools(entries, tools):
    """Probe tools whose two readings disagree, as {tool: (search, fullmatch)}.

    This is the only place the two readings are compared, and it returns the
    PAIR rather than a boolean so a caller can print what the disagreement is.
    A tool absent from the result is a tool where the semantics question does
    not arise, which is the state every row should eventually be in.
    """
    out = {}
    for tool in tools:
        loose = tool_cost(entries, tool, anchored=False)["total"]
        strict = tool_cost(entries, tool, anchored=True)["total"]
        if loose != strict:
            out[tool] = (loose, strict)
    return out


def unmatched_matchers(entries, tools):
    """(event, matcher) pairs no probe tool selects, under EITHER reading.

    The completeness half of the baseline. A matcher nothing probes is a matcher
    whose cost the baseline does not carry, so adding one is invisible to a table
    that only lists tools. Wildcards are excluded because every tool selects them
    by construction and they can never be unmatched.
    """
    out = []
    for event, matcher, _ in entries:
        if matcher in WILDCARD_MATCHERS:
            continue
        if (event, matcher) in out:
            continue
        hit = any(
            matches(matcher, tool, anchored=False) or matches(matcher, tool, anchored=True)
            for tool in tools
        )
        if not hit:
            out.append((event, matcher))
    return sorted(out)


def measure(entries, tools):
    """The whole measurement, as plain data. The one thing the gate compares.

    Returns a dict with `tools` (per tool, both readings), `events` (per non-tool
    event), `ambiguous`, `entryCount` and `patternCount`. Plain dicts and ints so
    it can be json.dumps'd into the baseline verbatim.
    """
    if not tools:
        raise WiringError(
            "measure() was handed an empty probe-tool set, so it would report "
            "nothing about a fully wired tree; declare the tools in the baseline"
        )
    return {
        "entryCount": len(entries),
        "patternCount": len({(ev, matcher) for ev, matcher, _ in entries}),
        "tools": {
            tool: {
                "search": tool_cost(entries, tool, anchored=False),
                "fullmatch": tool_cost(entries, tool, anchored=True),
            }
            for tool in sorted(tools)
        },
        "events": {event: event_cost(entries, event) for event in non_tool_events(entries)},
        "ambiguous": {
            tool: list(pair) for tool, pair in sorted(ambiguous_tools(entries, tools).items())
        },
    }


def render(result):
    """The human table. Printed by `__main__` and by the gate's shape line."""
    lines = []
    lines.append(
        "%d harness command entries across %d distinct (event, matcher) patterns"
        % (result["entryCount"], result["patternCount"])
    )
    lines.append("")
    lines.append("  %-18s %-16s %-16s" % ("tool call", "search", "fullmatch"))
    for tool, cost in result["tools"].items():
        lines.append(
            "  %-18s pre %-2d post %-2d = %-3d  pre %-2d post %-2d = %-3d%s"
            % (
                tool,
                cost["search"]["PreToolUse"],
                cost["search"]["PostToolUse"],
                cost["search"]["total"],
                cost["fullmatch"]["PreToolUse"],
                cost["fullmatch"]["PostToolUse"],
                cost["fullmatch"]["total"],
                "   AMBIGUOUS" if tool in result["ambiguous"] else "",
            )
        )
    lines.append("")
    for event, count in result["events"].items():
        lines.append("  %-18s %d" % (event, count))
    return "\n".join(lines)


def _default_settings_path():
    return pathlib.Path(__file__).resolve().parents[2] / ".claude" / "settings.json"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--settings", default=None, help="path to settings.json")
    ap.add_argument("--tools", default=None, help="comma separated probe tools")
    ap.add_argument("--json", action="store_true", help="emit the measurement as JSON")
    args = ap.parse_args(argv)
    path = args.settings or _default_settings_path()
    try:
        entries = parse_entries(load_settings(path))
        tools = (
            [t for t in (args.tools or "").split(",") if t]
            if args.tools
            else sorted({t for _, m, _ in entries for t in _literal_tools(m)})
        )
        result = measure(entries, tools)
    except WiringError as exc:
        print("execcount: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else render(result))
    return 0


def _literal_tools(matcher):
    """Tool names spelled literally inside a matcher, for the bare CLI only.

    A convenience for `python3 execcount.py` with no `--tools`, so the file is
    runnable by hand. It is NOT what the gate uses: the gate reads its probe set
    out of the baseline, because a set derived from the matchers can never
    notice a matcher that selects a tool nobody listed. Alternation and anchors
    are the only two shapes in this repository's settings.json today, and a
    matcher this cannot decompose contributes nothing rather than a wrong guess.
    """
    if matcher in WILDCARD_MATCHERS:
        return []
    body = matcher.strip("^$")
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    return [part for part in body.split("|") if part and re.fullmatch(r"[A-Za-z]+", part)]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
