r"""check:ci-hook-exec-baseline -- the hook wiring cannot change its cost silently.

THE BASELINE THIS GUARDS DID NOT EXIST UNTIL 2026-09-09, AND THAT IS THE POINT.
W5 P0 lists "a fork counter" among its delivered artifacts and W5 P6 records "456 execs per Bash call to 35". Neither is reproducible from the tree:

    grep -rlnP 'strace|GUARD_PASS|HOOKS_ONLY|FORK_COUNT' .ci .claude scripts
      -> zero files
    git ls-files | grep -iE 'strace|exec-baseline'
      -> zero files

So W5's target of "2 processes per Bash tool call" was, for three days, a number
with nothing on the other side of the comparison. A target with no baseline is
unfalsifiable, and an unfalsifiable target is checked off by whoever gets tired first. `.claude/rediacc_hooks/execcount.py` is the counter and
`.ci/policy/hook-exec-baseline.json` is the pin; this gate is what makes the pin
mean something.

WHY IT IS STATIC AND NOT strace. Three disqualifications, any one of them enough: strace is absent on macOS, it needs a ptrace capability containers routinely withhold, and it measures a RUN rather than the wiring, so its answer moves with whichever guard short-circuited that day. A baseline CI cannot recompute on demand is the same failure class as the baseline that vanished. The
counter therefore reads `.claude/settings.json` and counts the processes the HARNESS starts, one per `hooks[].command`. That is a FLOOR on the true exec
count and the module says so in as many words; in-guard forks are a different
measurement and this gate does not pretend to make it.

BOTH DIRECTIONS, AND THE SECOND ONE IS THE HALF THAT KEEPS IT SHRINKING. A count that GREW is refused, which is the obvious direction. A count that SHRANK is ALSO refused, with the new value printed ready to paste. A baseline that silently absorbs an improvement can no longer prove the next one, and D4's whole acceptance ("30 entries down to 11") is a statement about this file's
numbers moving in a change that says it is moving them.

WHAT ELSE IS PINNED, because a table of tool costs is not by itself complete:

  * the ENTRY count and the distinct (event, matcher) PATTERN count, which are
    what D4 changes and what a stray hook addition changes,
  * the per-event cost of every lifecycle event that is not a tool call, both
    directions, so an event appearing or disappearing is a finding,
  * the AMBIGUITY set. `.claude/settings.json` mixes an anchored matcher
    (`^(Edit|MultiEdit|Write|NotebookEdit)$`) with two bare ones (`Bash`,
    `AskUserQuestion`), and nothing in this repository records whether the
    harness matches by search or by fullmatch. Under search, `Bash` selects the
    tool `BashOutput` and every Bash guard runs on it; under fullmatch it does
    not. The counter computes BOTH readings rather than guessing, a tool where
    they disagree is an ambiguity, and the ambiguity set is pinned with a
    BLOCKER reason each. A NEW ambiguity is a finding. A pinned one that has
    GONE is also a finding, telling the author to drain the entry, because that
    is what anchoring the matcher looks like from here.
  * COMPLETENESS: a matcher in the wiring that no probe tool selects, under
    either reading, is a matcher whose cost no row of the table carries. A table
    that only lists tools cannot notice that on its own.

ANTI-VACUITY, FIVE REFUSALS AND EACH ITS OWN SENTENCE. A missing or unparseable
baseline; a baseline with no probe tools; a baseline with no `measured` block; a
settings file the counter cannot read; and a wiring that parses to zero hook
commands. The last one is the shape of the failure that started this box: an instrument that stopped producing numbers and reported nothing rather than reporting that it had stopped.

Exit 1 on any finding or refusal, 2 on a failed control.

THE GATE HEADER LIVES IN THE ENTRY POINT, not here. `gate-bind` reads the file the
registry INVOKES, and the registry invokes .ci/scripts/quality/check_hook_exec_baseline.py by path;
a header here derives this module's own path and the binding disagrees with
package.json. Measured 2026-09-09: three gates landed with it in the module and
`check:ci-gate-bind` named all three.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

from rediacc_ci import log, paths
from rediacc_ci.controls import Checker, controls_first, plant
from rediacc_ci.policy_paths import policy_path


class RefusalError(Exception):
    """The gate cannot reach a verdict. Exit 1, never a silent pass."""


BASELINE_NAME = "hook-exec-baseline.json"
SETTINGS_REL = (".claude", "settings.json")

# The counter lives in the `.claude` hook package, not here, and importing it costs one sys.path hop.
#
# ANCHORED ON THIS FILE, NOT ON `paths.from_root()`, and the difference is the whole of a bug this gate had for about twenty minutes on 2026-09-09. `from_root()` honours $REDIACC_CI_ROOT, which is the root of the tree being
# JUDGED; the counter is part of the INSTRUMENT and travels with the gate.
# Written the other way, pointing the gate at a fixture made it look for `rediacc_hooks` INSIDE the fixture and die with `ModuleNotFoundError` -- and the selftest did not catch it, because `selftest()` resolves the counter once before any fixture root is set. It was the first run against a scratch copy of the REAL tree that found it, which is the argument for doing that run.
# `check_language_policy.py:120-133` makes the same distinction about its validator, in the same words, for the same reason.
#
# THE COUNTER IS NOT COPIED HERE, deliberately. Two implementations of "how many processes does a Bash call cost" is exactly the drift this gate exists to stop, and it would be a drift the gate could not see.
_HOOK_PKG_PARENT = pathlib.Path(
    os.environ.get("HOOK_EXEC_COUNTER_DIR")
    or pathlib.Path(__file__).resolve().parents[3] / ".claude"
)


def _load_counter():
    """`rediacc_hooks.execcount`, imported through one documented path hop."""
    # `paths.on_sys_path` IS the "insert it once" this used to spell by hand, and it is the package's own resolver rather than a fourth copy of the idiom.
    parent = str(_HOOK_PKG_PARENT)
    paths.on_sys_path(parent)
    try:
        from rediacc_hooks import execcount  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        raise RefusalError(
            "the counter this gate is built on is not importable from %s (%s). "
            "It should be at .claude/rediacc_hooks/execcount.py; this gate has no "
            "second implementation to fall back to, and reporting a pass without it "
            "would be reporting a measurement nobody took." % (parent, exc)
        ) from exc
    return execcount


def load_baseline(path):
    """The pinned baseline, validated far enough to be comparable."""
    p = pathlib.Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise RefusalError(
            "cannot read the pinned baseline at %s (%s). Without it there is nothing "
            "to compare today's wiring against, and a pass would mean nothing." % (p, exc)
        ) from exc
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RefusalError("%s is not valid JSON: %s" % (p, exc)) from exc
    if not isinstance(obj, dict):
        raise RefusalError("%s does not hold a JSON object" % p)
    probes = obj.get("probeTools")
    if not isinstance(probes, dict) or not probes:
        raise RefusalError(
            "%s declares no probeTools, so the gate would measure NOTHING and pass. "
            "A tool table with no tools is the vacuous shape this gate refuses." % p
        )
    measured = obj.get("measured")
    if not isinstance(measured, dict) or not measured.get("tools"):
        raise RefusalError(
            "%s has no `measured.tools` block to compare against; regenerate it with "
            "`python3 .claude/rediacc_hooks/execcount.py --json`" % p
        )
    if not isinstance(obj.get("ambiguousMatchers", {}), dict):
        raise RefusalError("%s: ambiguousMatchers must be an object" % p)
    return obj


def _drift(label, pinned, live):
    """One finding line for a pinned scalar that moved, naming the direction.

    The direction is in the message on purpose. "12 != 11" tells a reader a
    number changed; "SHRANK, paste 11" tells them which of the two completely
    different things happened and what to do about it.
    """
    if pinned == live:
        return None
    direction = "GREW" if live > pinned else "SHRANK"
    tail = (
        "the wiring got more expensive; if that is intended, say so and repin"
        if live > pinned
        else "the improvement is real; repin it with %r so the NEXT one can be proven" % live
    )
    return "%s %s: pinned %r, measured %r. %s" % (label, direction, pinned, live, tail)


def compare(baseline, result, unmatched):
    """Every finding, as a list of strings. Pure: no I/O, no exits.

    Exported so the controls can drive it directly, and so a caller that wants the findings without the printing can have them.
    """
    findings = []
    pinned = baseline["measured"]
    probes = baseline["probeTools"]

    for key in ("entryCount", "patternCount"):
        line = _drift(key, pinned.get(key), result.get(key))
        if line:
            findings.append(line)

    pinned_tools = pinned.get("tools", {})
    live_tools = result.get("tools", {})
    findings.extend(
        "tool %s is pinned but was not measured; it is missing from probeTools" % tool
        for tool in sorted(set(pinned_tools) - set(live_tools))
    )
    findings.extend(
        "tool %s was measured but is not pinned in measured.tools" % tool
        for tool in sorted(set(live_tools) - set(pinned_tools))
    )
    for tool in sorted(set(pinned_tools) & set(live_tools)):
        for reading in ("search", "fullmatch"):
            pin_row = pinned_tools[tool].get(reading, {})
            live_row = live_tools[tool].get(reading, {})
            for field in ("PreToolUse", "PostToolUse", "total"):
                line = _drift(
                    "%s/%s/%s" % (tool, reading, field), pin_row.get(field), live_row.get(field)
                )
                if line:
                    findings.append(line)

    pinned_events = pinned.get("events", {})
    live_events = result.get("events", {})
    findings.extend(
        "lifecycle event %s is pinned at %r but the wiring no longer carries it"
        % (event, pinned_events[event])
        for event in sorted(set(pinned_events) - set(live_events))
    )
    findings.extend(
        "lifecycle event %s carries %d harness process(es) and is not pinned at all"
        % (event, live_events[event])
        for event in sorted(set(live_events) - set(pinned_events))
    )
    for event in sorted(set(pinned_events) & set(live_events)):
        line = _drift("event %s" % event, pinned_events[event], live_events[event])
        if line:
            findings.append(line)

    declared = baseline.get("ambiguousMatchers", {})
    live_ambig = result.get("ambiguous", {})
    findings.extend(
        "NEW ambiguity: %s costs %d process(es) under a search reading and %d under "
        "fullmatch. Anchor the matcher, or declare it in ambiguousMatchers with a "
        "BLOCKER reason. Do not add it to the baseline to make this go away."
        % (tool, live_ambig[tool][0], live_ambig[tool][1])
        for tool in sorted(set(live_ambig) - set(declared))
    )
    findings.extend(
        "ambiguity %s is declared but no longer measurable; the matcher was probably "
        "anchored. Drain the entry from ambiguousMatchers in the same change." % tool
        for tool in sorted(set(declared) - set(live_ambig))
    )
    for tool in sorted(set(declared) & set(live_ambig)):
        row = declared[tool]
        counts = row.get("counts", {}) if isinstance(row, dict) else {}
        for index, reading in enumerate(("search", "fullmatch")):
            line = _drift(
                "ambiguity %s/%s" % (tool, reading), counts.get(reading), live_ambig[tool][index]
            )
            if line:
                findings.append(line)
        why = row.get("why", "") if isinstance(row, dict) else ""
        if "BLOCKER:" not in why:
            findings.append(
                "ambiguity %s carries no `BLOCKER:` reason. Every entry that holds a "
                "known divergence open must say why it is still true." % tool
            )

    findings.extend(
        "matcher %r on %s is selected by no probe tool, so no row of this table "
        "carries its cost. Add a tool to probeTools that it selects." % (matcher, event)
        for event, matcher in unmatched
    )
    findings.extend(
        "probeTools names %s but the counter did not measure it" % tool
        for tool in sorted(set(probes) - set(live_tools))
    )

    return findings


def run(root=None):
    """Measure the tree at `root` and return (findings, result, baseline)."""
    execcount = _load_counter()
    base_root = root or paths.repo_root()
    baseline = load_baseline(policy_path(BASELINE_NAME, base_root))
    settings = base_root.joinpath(*SETTINGS_REL)
    try:
        entries = execcount.parse_entries(execcount.load_settings(settings))
        tools = sorted(baseline["probeTools"])
        result = execcount.measure(entries, tools)
        unmatched = execcount.unmatched_matchers(entries, tools)
    except execcount.WiringError as exc:
        raise RefusalError(str(exc)) from exc
    return compare(baseline, result, unmatched), result, baseline


def main(argv=None):
    argv = list(argv or [])
    if "--selftest" in argv:
        # `selftest()` returns TRUE when a control FAILED, which is the contract `controls_first` reads it under. The first draft of this line had the sense inverted and `--selftest` exited 1 on a fully green run: caught by the gate test driving the flag as a process, never by the controls themselves, which never look at their own exit code.
        return 1 if selftest() else 0
    rc = controls_first("hook exec baseline", selftest)
    if rc:
        return rc
    try:
        findings, result, baseline = run()
    except RefusalError as exc:
        log.error("hook exec baseline: %s" % exc)
        return 1
    if findings:
        for finding in findings:
            log.error("  %s" % finding)
        log.error(
            "%d finding(s). The counter is `python3 .claude/rediacc_hooks/execcount.py`; "
            "repin with its `--json` output in .ci/policy/%s." % (len(findings), BASELINE_NAME)
        )
        return 1
    target = baseline.get("target", {})
    log.success(
        "hook exec baseline: %d harness command entries, %d (event, matcher) patterns, "
        "%d probe tool(s), %d lifecycle event(s), %d pinned ambiguity(ies). "
        "Bash costs %d process(es) against a target of %d."
        % (
            result["entryCount"],
            result["patternCount"],
            len(result["tools"]),
            len(result["events"]),
            len(result.get("ambiguous", {})),
            result["tools"]["Bash"]["fullmatch"]["total"],
            target.get("processes", -1),
        )
    )
    return 0


# --------------------------------------------------------------------------- controls ---------------------------------------------------------------------------


def _fixture(tmp, settings_text, baseline_obj):
    """A minimal tree: `.claude/settings.json` plus `.ci/policy/<baseline>`."""
    root = pathlib.Path(tmp)
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "policy").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "settings.json").write_text(settings_text, encoding="utf-8")
    (root / ".ci" / "policy" / BASELINE_NAME).write_text(
        json.dumps(baseline_obj, indent=2) + "\n", encoding="utf-8"
    )
    return root


# WRITTEN AS A LITERAL, NOT json.dumps. The plants below substitute exact substrings into it, and a serialiser is free to choose its own whitespace: the
# first draft used json.dumps(indent=2) and every needle missed, which
# `plant()` caught by raising rather than by handing the gate clean input. The fixture is small on purpose but NOT trivial -- it carries an unanchored matcher, a wildcard group and a non-tool event, which are the three shapes the comparison has separate code for.
_CLEAN_SETTINGS = """{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash", "hooks": [{"command": "bash a.sh"}, {"command": "bash b.sh"}]}
    ],
    "PostToolUse": [{"hooks": [{"command": "python3 c.py"}]}],
    "Stop": [{"hooks": [{"command": "python3 d.py"}]}]
  }
}
"""


def _clean_baseline(execcount):
    """The baseline that matches `_CLEAN_SETTINGS` exactly, derived not typed."""
    entries = execcount.parse_entries(json.loads(_CLEAN_SETTINGS))
    tools = ["Bash", "BashOutput", "Read"]
    result = execcount.measure(entries, tools)
    return {
        "probeTools": dict.fromkeys(tools, "control fixture"),
        "ambiguousMatchers": {
            tool: {
                "counts": {"search": pair[0], "fullmatch": pair[1]},
                "why": "BLOCKER: control fixture, unanchored Bash matcher",
            }
            for tool, pair in result["ambiguous"].items()
        },
        "measured": {k: v for k, v in result.items() if k != "ambiguous"},
        "target": {"processes": 2},
    }


def _run_at(root):
    """`run()` against a fixture root, restoring $REDIACC_CI_ROOT afterwards."""
    saved = os.environ.get(paths.ROOT_ENV)
    os.environ[paths.ROOT_ENV] = str(root)
    try:
        return run(pathlib.Path(root))
    finally:
        if saved is None:
            os.environ.pop(paths.ROOT_ENV, None)
        else:
            os.environ[paths.ROOT_ENV] = saved


def selftest():
    """True when a control failed, which is what `controls_first` expects."""
    import tempfile  # noqa: PLC0415

    check = Checker()
    execcount = _load_counter()
    clean = _clean_baseline(execcount)

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, _CLEAN_SETTINGS, clean)
        findings, result, _ = _run_at(root)
        check("CONTROL: a fixture whose pin matches its wiring is clean", findings == [])
        check(
            "CONTROL: and the measurement is not trivially empty",
            result["entryCount"] == 4 and result["patternCount"] == 3,
        )

    with tempfile.TemporaryDirectory() as tmp:
        grown = plant(
            _CLEAN_SETTINGS,
            '{"command": "bash b.sh"}',
            '{"command": "bash b.sh"}, {"command": "bash e.sh"}',
        )
        root = _fixture(tmp, grown, clean)
        findings, _, _ = _run_at(root)
        check(
            "PLANT: one more hook command reds, and the message says GREW",
            any("entryCount GREW" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        shrunk = plant(_CLEAN_SETTINGS, ', {"command": "bash b.sh"}', "")
        root = _fixture(tmp, shrunk, clean)
        findings, _, _ = _run_at(root)
        check(
            "PLANT: one fewer hook command ALSO reds, and says SHRANK with the repin value",
            any("entryCount SHRANK" in f and "repin it with 3" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        anchored = plant(_CLEAN_SETTINGS, '"matcher": "Bash"', '"matcher": "^Bash$"')
        root = _fixture(tmp, anchored, clean)
        findings, _, _ = _run_at(root)
        check(
            "PLANT: anchoring the matcher removes the ambiguity, which is a finding to DRAIN",
            any("declared but no longer measurable" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        no_ambig = dict(clean)
        no_ambig["ambiguousMatchers"] = {}
        root = _fixture(tmp, _CLEAN_SETTINGS, no_ambig)
        findings, _, _ = _run_at(root)
        check(
            "PLANT: an undeclared ambiguity reds and refuses the shortcut",
            any("NEW ambiguity" in f and "Do not add it to the baseline" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        weak = json.loads(json.dumps(clean))
        weak["ambiguousMatchers"]["BashOutput"]["why"] = "we will look at it later"
        root = _fixture(tmp, _CLEAN_SETTINGS, weak)
        findings, _, _ = _run_at(root)
        check(
            "PLANT: a declared ambiguity with no BLOCKER reason reds",
            any("no `BLOCKER:` reason" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        extra = plant(
            _CLEAN_SETTINGS,
            '"PostToolUse": [{"hooks"',
            '"PostToolUse": [{"matcher": "Nonesuch", "hooks": [{"command": "bash n.sh"}]}, {"hooks"',
        )
        root = _fixture(tmp, extra, clean)
        findings, _, _ = _run_at(root)
        check(
            "PLANT: a matcher no probe tool selects reds as uncounted",
            any("selected by no probe tool" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        renamed = plant(_CLEAN_SETTINGS, "bash a.sh", "bash renamed.sh")
        root = _fixture(tmp, renamed, clean)
        findings, _, _ = _run_at(root)
        check(
            "ANTI-SILENCER: renaming a hook COMMAND is not a cost change and stays clean",
            findings == [],
        )

    with tempfile.TemporaryDirectory() as tmp:
        reordered = json.dumps(json.loads(_CLEAN_SETTINGS), indent=4, sort_keys=True)
        root = _fixture(tmp, reordered, clean)
        findings, _, _ = _run_at(root)
        check(
            "ANTI-SILENCER: reformatting settings.json is not a finding either",
            findings == [],
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, '{"hooks": {}}', clean)
        check(
            "VACUITY: wiring that parses to zero hook commands is a REFUSAL",
            _refuses(root),
        )

    with tempfile.TemporaryDirectory() as tmp:
        empty = dict(clean)
        empty["probeTools"] = {}
        root = _fixture(tmp, _CLEAN_SETTINGS, empty)
        check("VACUITY: a baseline with no probe tools is a REFUSAL", _refuses(root))

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / ".claude").mkdir()
        (root / ".claude" / "settings.json").write_text(_CLEAN_SETTINGS, encoding="utf-8")
        check("VACUITY: a missing baseline file is a REFUSAL", _refuses(root))

    # THE INSTRUMENT ITSELF. This control exists because the bug it describes was live and every control above still passed: they all resolve the counter once, before any fixture root is set, so none of them could see a counter path that followed the judged tree. A missing counter must be a loud refusal naming the directory, never a traceback that reads as flake.
    #
    # THE sys.modules PURGE IS NOT BOILERPLATE. Without it this control passed
    # while asserting nothing: `rediacc_hooks` is already imported by the time it
    # runs, so `from rediacc_hooks import execcount` succeeds no matter what sys.path says, and the refusal branch is unreachable inside a warm process.
    # The gate itself always runs cold, so the branch IS live where it matters;
    # simulating cold is what makes the control a claim about that branch rather than about the import cache.
    global _HOOK_PKG_PARENT  # noqa: PLW0603
    saved_parent = _HOOK_PKG_PARENT
    saved_modules = {k: v for k, v in sys.modules.items() if k.split(".")[0] == "rediacc_hooks"}
    saved_path = list(sys.path)
    with tempfile.TemporaryDirectory() as tmp:
        _HOOK_PKG_PARENT = pathlib.Path(tmp)
        for name in saved_modules:
            del sys.modules[name]
        sys.path[:] = [p for p in sys.path if p != str(saved_parent)]
        try:
            _load_counter()
            missing_refused = False
        except RefusalError as exc:
            missing_refused = ".claude/rediacc_hooks/execcount.py" in str(exc)
        finally:
            _HOOK_PKG_PARENT = saved_parent
            sys.modules.update(saved_modules)
            sys.path[:] = saved_path
    check(
        "VACUITY: a counter that cannot be imported is a REFUSAL naming the fix",
        missing_refused,
    )
    check(
        "ANTI-SILENCER: and the real counter is still importable afterwards",
        _load_counter().parse_entries is not None,
    )

    return not check.ok


def _refuses(root):
    try:
        _run_at(root)
    except RefusalError:
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
