"""Refuse an Edit or Write whose NEW prose breaks the house writing style.

THE STYLE, in one line: make the work, the event or the artifact the subject, or use the shared `we`. Never `you`, never `I`. The eighteen rules, their severities, their scopes and their examples live in `.ci/config/prose-style-rules.json` and nowhere else; this guard loads them and holds no rule text of its own, so a rule edited there is enforced here with no edit to this file.

=============================================================================
THIS GUARD HAS NO BASH TWIN, AND IT WAS THE FIRST ONE THAT DID NOT
=============================================================================

`OWN_SUITE = True` below is a sentinel, not an oversight, and it was added for
this guard. Every one of the 46 guards in this package landed on ONE day, 2026-09-06, the P7 cutover, because every one of them was a PORT of a pre-existing bash hook. There was consequently no precedent for a guard that was never bash, and the harness assumed there could not be one: `test_dispatch.py` asserted `isinstance(module.TWIN, str)`, and `test_guards_differential.py` read
`ORACLES / module.TWIN` in four places, one of which (`test_every_port_has_a_present_twin`) asserted the oracle file exists. Both are gone now (PLAN-retire-bash-oracles A3 deleted `.claude/oracles/` and every `TWIN` constant with it, once every twinned guard had a frozen golden instead), but the sentinel this guard needed first is still the one this whole package uses.

A twin could not be written even as a formality. `.ci/scripts/quality/check_language_policy.py` freezes the SET of shell files under `.ci` and `.claude` and refuses a new one -- "the surface may shrink and may never grow" -- so inventing a bash file purely to satisfy an assertion would have been blocked by a different gate, and would have been a lie to this one.

WHAT REPLACES THE ORACLE, because "no twin" must not mean "no evidence". An
OWN_SUITE guard is held to MORE, not less:

  * a dedicated per-guard suite beside it, `test-block_prose_style_edit.py`,
    which `check-hook-integrity.sh` already recognises as covering both
    directions and which `test_every_port_has_goldens` now REQUIRES of any
    guard declaring `OWN_SUITE = True`. Having no golden is not a free pass
    out of having a control.
  * the DEFECT below, planted by `test_the_differential_can_fail`, which
    compares the guard against ITSELF-WITH-A-BUG rather than against a frozen
    record and so works identically without one.
  * the engine's own 65-control selftest, and
    `.ci/rediacc_ci/tests/test_quality_prose_style.py`, which generates one case
    per example in the rules file.

=============================================================================
WHAT IT REFUSES, AND THE THREE THINGS IT DELIBERATELY DOES NOT
=============================================================================

ONLY THE NEW PROSE. The payload's `content` / `new_string` / `new_source` / `edits[].new_string` is what gets linted. Nothing else in the file is read.

PRE-EXISTING DEBT IS A WARNING, NEVER A BLOCK. A whole-file `Write` carries the lines that were already there, and refusing those would block every rewrite of a legacy document -- the exact over-block that gets a guard deleted within a week. So a finding whose stable id is already in `.ci/config/prose-style-baseline.json` is reported and ALLOWED. Only a finding that is genuinely
new is refused, which is the same shrink-only contract the CI gate runs under.

WARNINGS NEVER BLOCK. Nine of the eighteen rules are advisory and several more are `severity: warning` (R7's absolutes, R11's imperatives). Those are printed and allowed. Only `severity: error` refuses.

OUT-OF-SCOPE FILES PASS SILENTLY. `.sh` is not scanned at all (this repository's shell surface is shrinking under a migration and will not outlive the effort of teaching a linter its comment syntax), `packages/www` is excluded (217 translated, hash-pinned files whose English is the source of twelve derived locales), and `private/` is excluded (four git submodules, other
repositories).

IT FAILS OPEN, LOUDLY. If the engine cannot be imported -- a moved `.ci`, a broken rules file, a partial checkout -- the edit is ALLOWED and stderr says the prose went UNEXAMINED. `block_settled_questions.py` argues the same case for a missing jq: blocking a legitimate edit over a missing module is worse than the thing being guarded, and reporting nothing at all is worse than both,
because "the operator never learns what was not asked".
"""

import fnmatch
import os
import pathlib
import sys

from rediacc_hooks import hookio

CHAIN = "pre-edit"
OWN_SUITE = True
ORDER = 12

# THE SCOPE TEST. Planting `False` makes the guard lint every file it is handed, including the two exclusions that are decisions rather than oversights (`private/` submodules, `.sh`), and the EDGE_CASES below carry one of each, plus `packages/www`, which is linted like every other tree so the plant changes a real answer.
#
# THE FIRST DEFECT DECLARED HERE WAS `if finding.fid in baseline:` -> `if False:`, and `test_the_differential_can_fail` reported it UNPROVEN on 2026-09-16: no EDGE_CASE carried text that was actually in the baseline, so removing the baseline consultation changed no answer. That is the control working. The declaration was moved rather than the case set padded, because a defect
# nobody can reach is not a defect this file's green depends on.
DEFECT = ("if not _in_scope(engine, globals_, rel):", "if False:")

UNEXAMINED = (
    "block-prose-style-edit: the prose-style engine could not be loaded (%s); this edit "
    "passed UNEXAMINED (the hook did not run its rules)."
)

HEADER = """BLOCKED: the new prose breaks the house writing style -- make the WORK the subject,
or use the shared "we". Never "you", never "I".

"""

FOOTER = """
R18 (too long) and R19 (hard-wrapped narrow) are WIDTH findings, and the tool
fixes them. Do not hand-wrap and re-submit: %(floor)d is a ceiling, not a
target, and guessing at it costs a round trip per attempt.

    .ci/scripts/quality/check_prose_style.py reflow --write <path>

For a file not yet written, draft it anywhere, reflow the draft, then write
the reflowed text. Reflow keeps the words and only moves the line breaks.

The rules, their examples and the reasons for each are in
.ci/config/prose-style-rules.json. To check a file directly:

    .ci/scripts/quality/check_prose_style.py check <path>

A line that genuinely has to carry the violation (an example, a quotation)
takes an explicit marker on that line: <!-- style-ok --> in markdown,
# style-ok or // style-ok in code. Use it for a line that IS the example,
never to get past this hook.
"""

EDGE_CASES = [
    # The two shapes this guard exists for, on a file it is in scope for.
    (
        "a write whose prose addresses the reader",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "docs/new.md", "content": "Did you run the tests?\n"},
        },
    ),
    (
        "an edit whose new_string says I",
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": "docs/new.md", "new_string": "I think this is wrong.\n"},
        },
    ),
    # CONTROLS: the same bytes, rewritten, must pass untouched.
    (
        "the rewritten sentence passes",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "docs/new.md", "content": "Have the tests been run?\n"},
        },
    ),
    (
        "the ownership exception is allowed",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "docs/new.md",
                "content": "My mistake; a fix is on the way.\n",
            },
        },
    ),
    # SCOPE: a shell script is not scanned at all.
    (
        "a .sh file is out of scope entirely",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "scripts/x.sh", "content": "# Did you run the tests?\n"},
        },
    ),
    (
        "packages/www is linted like every other tree",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "packages/www/src/a.md", "content": "Did you run it?\n"},
        },
    ),
    (
        "a submodule path is excluded",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "private/renet/README.md", "content": "Did you run it?\n"},
        },
    ),
    # EXTRACTION: the violation is inside a fence, an inline code span, a blockquote and a `bad:` exemplar. None of those is prose.
    (
        "a fenced block is not prose",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "docs/new.md", "content": "```\nDid you run it?\n```\n"},
        },
    ),
    (
        "an inline code span is not prose",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "docs/new.md", "content": "The flag is `you` here.\n"},
        },
    ),
    (
        "a quotation is somebody else's words",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "docs/new.md", "content": "> Did you run it?\n"},
        },
    ),
    (
        "a bad: exemplar carries its violation on purpose",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "docs/new.md", "content": "bad: Did you run it?\n"},
        },
    ),
    (
        "the explicit marker exempts the line",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "docs/new.md",
                "content": "Did you run it? <!-- style-ok -->\n",
            },
        },
    ),
    # SEVERITY: a warning-only rule prints and allows.
    (
        "an absolute is a warning, not a block",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "docs/new.md", "content": "That will never work.\n"},
        },
    ),
    # A code file contributes only its COMMENTS.
    (
        "a python comment is prose",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "scripts/x.py", "content": "x = 1  # Did you run it?\n"},
        },
    ),
    (
        "a python STRING is not",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "scripts/x.py", "content": "x = 'did you run it'\n"},
        },
    ),
    # A MultiEdit-shaped payload, and the degenerate ones.
    (
        "the edits[] collector is read",
        {
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": "docs/new.md",
                "edits": [{"new_string": "Did you run it?"}],
            },
        },
    ),
    ("no file path at all", {"tool_name": "Write", "tool_input": {"content": "Did you run it?"}}),
    ("no content at all", {"tool_name": "Write", "tool_input": {"file_path": "docs/new.md"}}),
]


def _engine(root):
    """Import the prose-style engine, restoring `sys.path` on the way out.

    THE INSERT IS SCOPED AND REMOVED, which matters because the dispatcher runs this guard in the SAME process as every other one in its chain. A permanent `sys.path` entry pointing at `.ci` would put `rediacc_ci` and `_cipath` on every later guard's import path, and a name collision there would surface as a guard misbehaving with nothing pointing back at this line.
    `block_plan_without_tasks.py` avoids the question entirely by shelling out;
    this guard imports instead, because the engine is pure Python with no bash contract to reproduce and an in-process call is what lets the whole suite run in one process.
    """
    cipath = str(pathlib.Path(root) / ".ci")
    inserted = cipath not in sys.path
    if inserted:
        sys.path.insert(0, cipath)
    try:
        from rediacc_ci.quality import prose_style  # noqa: PLC0415 - deliberately late
    finally:
        if inserted and cipath in sys.path:
            sys.path.remove(cipath)
    return prose_style


def _relative(root, file_path, cwd=None):
    """The repo-relative path, or "" when the edit is outside the tree.

    An edit to `/tmp/scratch.md` is not this repository's prose and is not this guard's business. Returning a `../..` path for it is deliberate too: the caller's `_in_scope` refuses anything starting with `..`, and the baseline is keyed on repo-relative paths, so an invented `../` prefix that got through would silently miss every baseline entry and turn legacy debt into a block.

    `cwd` IS PASSED IN RATHER THAN READ FROM THE PROCESS, and it was MEASURED rather than reasoned about. The first cut called `os.path.abspath`, which resolves a relative `file_path` against the INTERPRETER's working directory. Running the per-guard harness from `/tmp` on 2026-09-16 produced:

        22 case(s), 0 blocked, 22 allowed
        FAILURES: 6

    Every relative path resolved outside the repository, every case fell out of scope, and the guard reported clean on six payloads it had refused a minute earlier from the repo root. A guard whose verdict depends on who invoked it is a guard that reads as working, because the common case is an absolute path where the difference never shows.

    The caller passes the event's OWN `cwd` -- the top-level key Claude Code sends on every hook payload -- and falls back to the repository root rather than to the process. Neither fallback is the interpreter's directory.
    """
    if not file_path:
        return ""
    try:
        path = file_path
        if not os.path.isabs(path):
            path = os.path.join(cwd or str(root), path)
        return os.path.relpath(os.path.normpath(path), str(root))
    except ValueError:
        return ""


def _in_scope(engine, globals_, rel):
    """Whether an edited file is scanned at all.

    SUFFIX ALONE IS NOT ENOUGH, since `.json` widened `include` to two directories (`.ci/config/*.json`, `.ci/policy/*.json`) rather than every tracked `.json` -- the 740-finding flood a whole-tree `.json` scan would produce, most of it translated CLI copy where second person is the correct register. `SCOPE_BY_SUFFIX` answers "what SCANNER", `include` answers "which FILES"; a
    suffix present in the first without being checked against the second would scan every `.json` in the tree the moment `discover()`'s own corpus wants only two directories of it.
    """
    if not rel or rel.startswith(".."):
        return False
    fixed = rel.replace(os.sep, "/")
    suffix = os.path.splitext(fixed)[1]
    if suffix not in engine.SCOPE_BY_SUFFIX:
        return False
    patterns = tuple(globals_.get("include") or ())
    if patterns and not any(fnmatch.fnmatchcase(fixed, pat) for pat in patterns):
        return False
    parts = pathlib.PurePosixPath(fixed).parts
    skip = set(globals_.get("exclude_dirs") or ())
    joined = ""
    for part in parts[:-1]:
        joined = "%s/%s" % (joined, part) if joined else part
        if part in skip or joined in skip:
            return False
    return True


def run(ev):
    try:
        root = hookio.repo_root()
        engine = _engine(root)
        globals_, rules = engine.load_rules_file(root)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        # FAIL OPEN, AND SAY SO. See the header: a missing module is this hook's problem, not the session's, and an edit that passed unexamined must be reported as unexamined rather than as clean.
        ev.warn(UNEXAMINED % exc)
        return hookio.ALLOW

    off = globals_.get("env_off", "PROSE_STYLE")
    if ev.env(off, "").lower() in ("off", "0", "false"):
        ev.warn(
            "%s=%s: block-prose-style-edit did NOT run. That is an UNEXAMINED edit, not a "
            "clean one." % (off, ev.env(off))
        )
        return hookio.ALLOW

    # THE PAYLOAD'S OWN `cwd` FIRST. Claude Code sends it on every hook event, and it is the only value that describes where the TOOL CALL is happening rather than where this interpreter happens to have been started. `str(root)` is the fallback, never `os.getcwd()`; see `_relative` for the measurement.
    rel = _relative(
        root,
        ev.first(("tool_input", "file_path"), ("tool_input", "notebook_path")),
        cwd=ev.default(("cwd",), str(root)),
    )
    if not _in_scope(engine, globals_, rel):
        return hookio.ALLOW

    new_prose = ev.texts(
        ("tool_input", "content"),
        ("tool_input", "new_string"),
        ("tool_input", "new_source"),
        ("tool_input", "edits", "[]?", "new_string"),
    )
    if not new_prose.strip():
        return hookio.ALLOW

    scope = engine.SCOPE_BY_SUFFIX.get(os.path.splitext(rel)[1], "markdown")
    findings, _note = engine.lint_text(rel, new_prose, rules, globals_, scope=scope)
    if not findings:
        return hookio.ALLOW

    baseline = engine.load_baseline(root) or {}
    errors = []
    warnings = []
    carried = 0
    for finding in findings:
        if finding.fid in baseline:
            carried += 1
            continue
        (errors if finding.severity == "error" else warnings).append(finding)

    if warnings:
        ev.warn(
            "block-prose-style-edit: %d style warning(s) in the new prose (not blocking):"
            % len(warnings)
        )
        for finding in warnings[:10]:
            ev.warn("  ~ %s %s: %s" % (finding.rule, finding.snippet, finding.text[:120]))

    if not errors:
        if carried:
            ev.warn(
                "block-prose-style-edit: %d pre-existing finding(s) carried through this "
                "write are already baselined and were NOT blocked." % carried
            )
        return hookio.ALLOW

    by_id = {rule.id: rule for rule in rules}
    lines = [HEADER]
    lines.append("%s\n" % rel)
    for finding in errors[:12]:
        rule = by_id.get(finding.rule)
        lines.append("  line %d  %s  %r\n" % (finding.lineno, finding.rule, finding.snippet))
        lines.append("    %s\n" % (rule.description if rule else ""))
        for example in rule.examples if rule else ():
            if example.get("kind") == "good":
                lines.append("    instead: %s\n" % example["text"])
                break
        lines.append("    in: %s\n" % finding.text[:200])
    if len(errors) > 12:
        lines.append("  ... and %d more\n" % (len(errors) - 12))
    if carried:
        lines.append(
            "\n%d further finding(s) in this write are already baselined and were NOT the "
            "reason for the refusal.\n" % carried
        )
    lines.append(FOOTER % {"floor": globals_.get("max_line_length", 384)})
    ev.warn_raw("".join(lines))
    return hookio.DENY
