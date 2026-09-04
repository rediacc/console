#!/usr/bin/env python3
"""A judged stop-rule that nothing CALLS is a rule that does not run.

THE GAP THIS CLOSES, measured 2026-09-01. `wl_shapedup` shipped with 239 controls in
`test-judge-schema.py` and every one of them exercises the module in ISOLATION --
`read_verdict`, `apply_verdict`, the latch, the driver. Not one asserts that
`wl_checks.py` actually calls it. Delete the single line `wl_shapedup.run(...)` at its
call site and all 239 controls stay green while the rule silently stops running.

That is the i18n lesson exactly: the thing was built, tested, and unenforced. A rule whose
call site can be deleted without a red is indistinguishable, from CI's point of view, from
a rule that was never written.

WHAT check-rubric-calibration.sh DOES AND DOES NOT COVER. It hashes the PROMPT TEXT of
SWEEP_PROMPT, BRAVE_PROMPT and REGGATE_PROMPT against a recorded manifest, so a calibrated
rubric cannot change without being re-calibrated. It says nothing about whether the rule is
invoked -- the text can be perfectly preserved in a module nobody imports.

THE INVARIANT. Every module under `.claude/hooks/stop/` that defines BOTH a `*_MARKER`
constant and an `apply_verdict` function is a judged rule. Each one must be imported by,
and CALLED from, the stop path (`wl_checks.py` or `wl_judge.py`). The set is discovered,
never listed: a hand-maintained list of wired rules is the same unkept promise this gate
exists to distrust, and a new rule added without wiring would simply be absent from it.

---- gate ----
step: Judged rule wiring
needs: none
lane: quality-code
---- end gate ----
"""

import os
import re
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
STOP = os.path.join(ROOT, ".claude", "hooks", "stop")
# The modules that DRIVE a stop. A rule is wired iff one of these calls it.
DRIVERS = ("wl_checks.py", "wl_judge.py")
# Below this, discovery is broken rather than the tree being empty. Raised 3 -> 4 when
# wl_histfirst landed: a floor that sits below the real count lets a rule be deleted
# without the floor noticing, which is the failure this gate exists to prevent.
MIN_RULES = 4


def judged_rules(stop_dir):
    """{module: marker} for every module that looks like a judged rule.

    DISCOVERED, not listed. Both signals are required: a `*_MARKER` (the string that makes
    the judge ask the question) and an `apply_verdict` (the function that acts on the
    answer). Either alone is something else -- wl_reggate has a verdict applier under a
    different name and no marker of its own, and several modules define constants.
    """
    found = {}
    for name in sorted(os.listdir(stop_dir)):
        if not name.startswith("wl_") or not name.endswith(".py"):
            continue
        with open(os.path.join(stop_dir, name), encoding="utf-8") as fh:
            src = fh.read()
        marker = re.search(r"^([A-Z][A-Z0-9_]*_MARKER)\s*=", src, re.MULTILINE)
        if marker and re.search(r"^def apply_verdict\(", src, re.MULTILINE):
            found[name[:-3]] = marker.group(1)
    return found


def call_sites(stop_dir):
    """{driver: source}. A driver that cannot be read is a hard error, not an empty scan."""
    out = {}
    for d in DRIVERS:
        p = os.path.join(stop_dir, d)
        if not os.path.exists(p):
            raise FileNotFoundError(p)
        with open(p, encoding="utf-8") as fh:
            out[d] = fh.read()
    return out


def wiring_of(module, drivers):
    """(imported_in, called_in) -- lists of driver names.

    IMPORT IS NOT ENOUGH, and that distinction is the whole gate. `import wl_shapedup` at
    the top of a file whose call site was deleted still satisfies a grep for the name;
    ruff would even keep it if anything else referenced it. Only an actual call means the
    rule runs, so the two are reported separately and the CALL is what is required.
    """
    imported, called = [], []
    # `import wl_x`, `import wl_x as X`, `from wl_x import ...`
    imp = re.compile(r"^\s*(?:import\s+%s\b|from\s+%s\s+import)" % (module, module), re.MULTILINE)
    for name, raw in drivers.items():
        # COMMENTS ARE NOT CALLS, and the first cut of this got it wrong -- its own SANITY
        # control caught it. `# wl_shapedup.run(...) used to be here` matched the call
        # regex, so the exact defect the gate exists for (call site deleted, import and a
        # comment left behind) read as wired. Same mention-vs-invocation distinction the
        # pre-bash guards keep paying for, in a gate written to catch a deletion.
        src = re.sub(r"(?m)^\s*#.*$", "", raw)
        src = re.sub(r"(?<!:)#.*$", "", src, flags=re.MULTILINE)
        if imp.search(src):
            imported.append(name)
        alias = re.search(
            r"^\s*import\s+%s\s+as\s+([A-Za-z_][A-Za-z0-9_]*)" % module, src, re.MULTILINE
        )
        names = [module] + ([alias.group(1)] if alias else [])
        # A CALL, not a mention: the name followed by a dot, an attribute, and an open
        # paren. `wl_shapedup.run(` counts; the word inside a comment does not.
        if any(re.search(r"\b%s\.[A-Za-z_][A-Za-z0-9_]*\(" % re.escape(n), src) for n in names):
            called.append(name)
    return imported, called


def judge(rules, drivers):
    """[(module, marker, problem)] for every rule that is not actually wired."""
    out = []
    for module, marker in sorted(rules.items()):
        imported, called = wiring_of(module, drivers)
        if called:
            continue
        if imported:
            out.append((module, marker, "imported by %s but never CALLED" % ", ".join(imported)))
        else:
            out.append((module, marker, "not imported or called by any driver"))
    return out


def selftest():
    """Controls, both directions. A gate that cannot fail is worse than none."""
    ok = True

    def check(label, cond):
        nonlocal ok
        if cond:
            print("  PASS  %s" % label)
        else:
            ok = False
            print("  FAIL  %s" % label, file=sys.stderr)

    wired = {"wl_checks.py": "import wl_rule\nx = wl_rule.run(a, b)\n", "wl_judge.py": ""}
    imported_only = {
        "wl_checks.py": "import wl_rule\n# wl_rule.run(a, b) used to be here\n",
        "wl_judge.py": "",
    }
    absent = {"wl_checks.py": "import os\n", "wl_judge.py": ""}
    aliased = {"wl_checks.py": "import wl_rule as R\nR.apply_verdict(o)\n", "wl_judge.py": ""}

    rules = {"wl_rule": "RULE_MARKER"}
    check("a wired rule is silent", len(judge(rules, wired)) == 0)
    # THE CASE THE GATE EXISTS FOR: the call site deleted, the import left behind.
    check("SANITY: imported but never called is a finding", len(judge(rules, imported_only)) == 1)
    check("a rule no driver mentions is a finding", len(judge(rules, absent)) == 1)
    check("CONTROL: an aliased import that IS called is silent", len(judge(rules, aliased)) == 0)
    check(
        "the finding names which driver imported it",
        "wl_checks.py" in judge(rules, imported_only)[0][2],
    )
    # A comment mentioning the call must not read as the call. This is the same
    # mention-vs-invocation distinction the pre-bash guards keep paying for.
    check(
        "CONTROL: a commented-out call is not a call",
        len(judge(rules, {"wl_checks.py": "import wl_rule\n#wl_rule.run(a)\n", "wl_judge.py": ""}))
        == 1,
    )
    check("CONTROL: no rules discovered yields no findings", len(judge({}, wired)) == 0)

    # Discovery needs BOTH signals; either alone is a different kind of module.
    with tempfile.TemporaryDirectory() as d:

        def write(fn, body):
            with open(os.path.join(d, fn), "w", encoding="utf-8") as fh:
                fh.write(body)

        write("wl_both.py", "X_MARKER = 'q'\ndef apply_verdict(o):\n    pass\n")
        write("wl_marker_only.py", "X_MARKER = 'q'\n")
        write("wl_verdict_only.py", "def apply_verdict(o):\n    pass\n")
        write("notwl.py", "X_MARKER = 'q'\ndef apply_verdict(o):\n    pass\n")
        got = judged_rules(d)
        check("discovery finds a module with BOTH a marker and apply_verdict", "wl_both" in got)
        check("CONTROL: a marker alone is not a judged rule", "wl_marker_only" not in got)
        check("CONTROL: apply_verdict alone is not a judged rule", "wl_verdict_only" not in got)
        check("CONTROL: a non-wl_ module is out of scope", "notwl" not in got)
    return ok


def main():
    if "--selftest" in sys.argv[1:]:
        return 0 if selftest() else 1
    if not selftest():
        print("REFUSING to report on the tree: this gate's own controls failed.", file=sys.stderr)
        return 1

    rules = judged_rules(STOP)
    if len(rules) < MIN_RULES:
        print(
            "found %d judged rule(s), floor %d. Discovery is broken, not the tree."
            % (len(rules), MIN_RULES),
            file=sys.stderr,
        )
        return 1

    drivers = call_sites(STOP)
    findings = judge(rules, drivers)
    if findings:
        print(
            "\n%d judged rule(s) are not wired into the stop path:\n" % len(findings),
            file=sys.stderr,
        )
        for module, marker, problem in findings:
            print("  %s (%s): %s" % (module, marker, problem), file=sys.stderr)
        print(
            "\n  A judged rule nothing calls does not run, and its own controls stay green\n"
            "  because they exercise the module in isolation. Call it from wl_checks.py or\n"
            "  wl_judge.py, or delete the rule -- an unwired rule is a rubric nobody asks.",
            file=sys.stderr,
        )
        return 1

    print(
        "judged-rule wiring: %d rule(s) (%s), each imported and called from the stop path"
        % (len(rules), ", ".join(sorted(rules)))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
