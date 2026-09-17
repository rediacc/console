"""Refuse a plan file that carries no task list the Stop hook can parse.

WHY THIS EXISTS, from this session rather than from theory. The plan-fidelity check (.claude/hooks/stop/wl_planfid.py) blocks a stop while "a plan task nothing tracks" exists, and it finds those tasks with a MARKDOWN parser. A plan written in prose is not seen as having zero tasks -- it is seen as having the WRONG ones. Measured on agent/PLAN-secret-namespace-migration.md before
this guard existed: plan_tasks() returned 21 "tasks", of which 8 were the operator's locked DECISIONS and 5 were open QUESTIONS, while every real unit of work (the two rotation defects, the atomic rename, the four cleanup items) was invisible. The session was then told to decompose a list that did not describe its work, twice, and could not tell why.

So the failure is not "the plan is badly written". It is that the author and the enforcement layer are reading two different documents, and nothing says so until a stop is refused for a reason the author cannot act on.

THE RULE, and it is one line: a plan file must contain at least one CHECKBOX task, `- [ ]` or `- [x]`. That is the only construct wl_planfid.plan_tasks
treats as a task WHEREVER it appears; everything else it counts is a plain
bullet that happens to sit under a heading whose first three words name work, which is precisely the accident that turns a Decisions section into a task list.

WHY NOT "zero parsed tasks". That weaker rule is the obvious one and it would have MISSED the incident above completely -- 21 > 0. A rule that cannot fire on the case that motivated it is the vacuous-gate shape TRAPS.md is about.

WHY IT IS NOT OVER-BLOCKING, which is the failure mode check-hook-integrity.sh names as the reason guards get deleted. MEASURED, not assumed: 59 of the 62 plans in agent/ today carry ZERO checkboxes, so a guard that refused every edit to a checkbox-less plan would fire on almost every plan in the tree, for work that has nothing to do with the convention. That guard would be deleted
within a week. The scope is therefore drawn where authorship actually happens:

  * a WRITE is authoring: the whole document is in hand, so it must conform,
    whether the file is new or a wholesale rewrite of an old one
  * an EDIT/MultiEdit is amending. It is judged against the union of the file
    ON DISK and the incoming fragments, and it is enforced ONLY when the plan
    already has a task list (so an edit can never strip one out) or the file
    does not exist yet. A legacy prose plan is GRANDFATHERED against piecemeal
    edits and says so on stderr rather than blocking
  * scope is agent/PLAN-*.md and <anything>/.claude/plans/*.md, nothing else
  * a plan under 400 chars is a stub and is exempt, matching wl_planfid's own
    MIN_PLAN_CHARS floor for "worth judging"
  * the remedy is one character per line, and the message writes it out

THE PARSER IS IMPORTED, NEVER RE-DERIVED. This calls wl_planfid.plan_tasks and wl_planfid.CHECKBOX_RE directly, so the guard and the Stop hook cannot drift into disagreeing about what a task is -- the same discipline test-plan-status-parse.py uses on plan_records.

FAILS OPEN on a missing python3, a missing module, or unreadable input. A guard about DOCUMENT SHAPE has no business walling a session in because an
interpreter is absent; the Stop hook still enforces the real rule.

RESIDUAL, stated rather than pretended away: an Edit that DELETES the last checkbox from a plan that has one is still allowed, because the union sees the on-disk list and cannot know the line is on its way out. Whole-file Writes -- the shape that actually produced the incident -- are checked exactly.

PORT NOTE ON KEEPING THE SUBPROCESS. The obvious port of the embedded `python3 -c` program is an in-process import of wl_planfid, and it is the wrong move twice over. First, `.claude/hooks/stop` is deliberately NOT an importable
package (pyproject.toml's INP001 note says so in as many words), so an import
means a `sys.path` mutation inside a guard that a chained dispatcher runs alongside 37 others. Second, the fail-open contract above is written in terms of a SUBPROCESS: "a missing python3, a missing module, or unreadable input" all arrive as an empty stdout from a program that exited 0, and reproducing that
with try/except around an import is a re-derivation of exactly the thing the
header says must never be re-derived. So the same program text is run the same way, and `PROBE` below is that text, character for character.

PORT NOTE ON THE TWO PARAMETER EXPANSIONS. `${COUNTS%% *}` takes everything
before the FIRST space and `${COUNTS##* }` everything after the LAST, which are
not the same as `split()[0]` and `split()[1]` the moment the output is not
exactly two fields. `[ "${BOXES:-1}" -eq 0 ] 2>/dev/null || exit 0` then adds a
third behaviour: a non-numeric value makes `test` itself fail, and the `||` turns that into an allow. All three are spelled out below rather than collapsed into an `int()` that would raise.
"""

import os
import subprocess
import tempfile

from rediacc_hooks import hookio

CHAIN = "pre-edit"
TWIN = "pre-edit/block-plan-without-tasks.sh"
ORDER = 10

# The grandfather clause, and the measured 59-of-62 note above is entirely about it: without it every amendment to a legacy prose plan is refused, which is the over-block that gets a guard deleted within a week.
DEFECT = ("if not hookio.grep_q(TASK_LINE, on_disk):", "if False:")

PLAN_GLOBS = ("*/agent/PLAN-*.md", "agent/PLAN-*.md", "*/.claude/plans/*.md")

TASK_LINE = hookio.rx(r"^[{S}]*[-*+] \[[ xX]\] ")

# The embedded program, unchanged. "<checkbox-count> <parsed-task-count>", or empty when anything at all went wrong -- see FAILS OPEN above.
PROBE = """
import os, sys
sys.path.insert(0, os.environ["STOPDIR"])
try:
    import wl_planfid as P
except Exception:
    sys.exit(0)
text = sys.stdin.read()
if len(text) < P.MIN_PLAN_CHARS:
    sys.exit(0)
boxes = sum(1 for line in text.splitlines() if P.CHECKBOX_RE.match(line))
print(boxes, len(P.plan_tasks(text)))
"""

WHY_INFLATED = (
    "it has NO checkbox task, yet %s of its plain bullets parse as tasks anyway -- they "
    "sit under a heading whose first three words name work, so the Stop hook will quote "
    "THOSE back at you as 'plan task(s) nothing tracks', decisions and open questions "
    "included. That is the exact confusion this guard exists to stop."
)

WHY_EMPTY = (
    "it has no task list at all: wl_planfid.plan_tasks() finds 0 tasks in it, so the "
    "plan-fidelity check reads it as a document with nothing to decompose."
)

GRANDFATHER = (
    "note: %s predates the plan-task convention (no '- [ ]' task list). Not blocking an "
    "amendment, but a plan without checkbox tasks is invisible to the Stop hook's "
    "plan-fidelity check -- add a '## Tasks' section next time you rewrite it."
)

MESSAGE = """❌ BLOCKED: %(file)s is a plan with no parseable task list -- %(why)s

ADD a section like this (anywhere in the file; '## Tasks' near the top is the convention):

## Tasks

- [ ] Fix <the concrete thing>, with a file:line or an id where you have one
- [ ] <the next real unit of work, one line each>
- [x] <a task already done>

The parser is .claude/hooks/stop/wl_planfid.py plan_tasks(). What it actually accepts:
  * '- [ ] text' and '- [x] text' count as a task ANYWHERE in the file. This is the only
    construct that is unambiguous, which is why this guard requires at least one.
  * '- [?]' and '- [>]' do NOT parse. They are worklist states, not plan tasks -- park
    them under a '## Remaining (operator)' heading instead.
  * a PLAIN bullet counts only under a heading whose FIRST THREE WORDS name work
    (wave/phase/step/stage/task/plan/implement/work/change/round/part/build/todo/action).
    That is why 'Part 0 - DECIDED by the operator' turns eight locked decisions into
    eight 'tasks': rename such a heading (e.g. 'Decisions locked by the operator
    (Part 0)') so its bullets read as the prose they are.
  * bullets indented 4 or more spaces are detail about their parent, never tasks.
  * fenced code blocks are skipped, and a task must normalise to 8+ characters.

Then track one worklist item per checkbox: worklist.py --add <you> <task text>
"""

# --------------------------------------------------------------------------- The fixture world ---------------------------------------------------------------------------
#
# Two plan files must EXIST on disk for the `[ -f "$FILE" ]` branch and the grandfather clause to be reachable, and the payload names its path literally, so the path has to be known when this module is imported. Same arrangement as block_roundlog_write.py: a deterministic directory under the system temp dir, built through an ENVS token this guard never reads. Using the repo's own
# agent/PLAN-*.md files instead would make the differential's answer depend on whichever plans happen to be checked out today.
WORLD = os.path.join(tempfile.gettempdir(), "rediacc-guard-plans")
LEGACY_PLAN = "%s/agent/PLAN-legacy-prose.md" % WORLD
TASKED_PLAN = "%s/agent/PLAN-with-tasks.md" % WORLD
NEW_PLAN = "%s/agent/PLAN-not-written-yet.md" % WORLD

_PROSE_BODY = (
    "This document records the decision to move the secret namespace, the four\n"
    "consumers that read it today, and the order the operator locked in. It is\n"
    "written as prose on purpose, the way most of this tree's older plans are,\n"
    "so that an amendment to it exercises the grandfather clause rather than the\n"
    "refusal. Every sentence here exists to carry the file past the 400-character\n"
    "floor that wl_planfid uses to decide whether a plan is worth judging at all.\n"
)

# No checkbox anywhere, and no heading whose first three words name work, so `plan_tasks` finds nothing: the WHY_EMPTY arm.
PROSE_PLAN = "# A plan with no list at all\n\n" + _PROSE_BODY + _PROSE_BODY

# No checkbox either, but the heading DOES name work, so the plain bullets under it parse as tasks: the WHY_INFLATED arm, which is the shape that produced the incident in the header.
INFLATED_PLAN = (
    "# A plan whose bullets are not tasks\n\n"
    + _PROSE_BODY
    + "\n## Part 0 - DECIDED by the operator\n\n"
    "- Rotate the namespace before anything else touches it\n"
    "- Keep the old prefix readable for one release\n"
    "- Do not add a migration command for a consumer nobody has\n"
    "- Land the rename and the consumers in one change\n"
)

TASKED_PLAN_TEXT = (
    "# A plan that conforms\n\n" + _PROSE_BODY + "\n## Tasks\n\n"
    "- [ ] Rotate the namespace and update all four consumers\n"
    "- [x] Record the operator's locked decisions as prose\n"
)


def _plan_world(_unused):
    """The two plan files the on-disk branches need. Idempotent by design."""
    os.makedirs(os.path.join(WORLD, "agent"), exist_ok=True)
    for path, text in ((LEGACY_PLAN, PROSE_PLAN), (TASKED_PLAN, TASKED_PLAN_TEXT)):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    return WORLD


FIXTURES = {"plan-world": _plan_world}

ENVS = [("plans", {"REDIACC_PLAN_WORLD": "{FIXTURE:plan-world}"}, {})]

EDGE_CASES = [
    # A WRITE is authoring, so the whole document must conform.
    (
        "a Write of a prose plan with no list at all",
        {"tool_name": "Write", "tool_input": {"file_path": NEW_PLAN, "content": PROSE_PLAN}},
    ),
    (
        "a Write of the shape that produced the incident",
        {"tool_name": "Write", "tool_input": {"file_path": NEW_PLAN, "content": INFLATED_PLAN}},
    ),
    (
        "a Write of a conforming plan",
        {"tool_name": "Write", "tool_input": {"file_path": NEW_PLAN, "content": TASKED_PLAN_TEXT}},
    ),
    # A plan under 400 chars is a stub and is exempt.
    (
        "a stub is under the floor",
        {"tool_name": "Write", "tool_input": {"file_path": NEW_PLAN, "content": "# stub\n"}},
    ),
    # The grandfather clause: an amendment to a plan that never had a task list.
    (
        "an Edit to a legacy prose plan",
        {"tool_name": "Edit", "tool_input": {"file_path": LEGACY_PLAN, "new_string": "one line"}},
    ),
    # ... and an amendment to one that HAS a list, judged against the union.
    (
        "an Edit to a plan that already conforms",
        {"tool_name": "Edit", "tool_input": {"file_path": TASKED_PLAN, "new_string": "one line"}},
    ),
    # A Write over an existing legacy plan is a wholesale rewrite, so the grandfather clause deliberately does NOT apply to it.
    (
        "a Write over the legacy plan is a rewrite",
        {"tool_name": "Write", "tool_input": {"file_path": LEGACY_PLAN, "content": PROSE_PLAN}},
    ),
    # An Edit to a plan that does not exist yet is judged on its fragments.
    (
        "an Edit to a plan that does not exist yet",
        {"tool_name": "Edit", "tool_input": {"file_path": NEW_PLAN, "new_string": PROSE_PLAN}},
    ),
    (
        "the .claude/plans arm of the scope",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "x/.claude/plans/a.md", "content": PROSE_PLAN},
        },
    ),
    (
        "a document that is not a plan",
        {"tool_name": "Write", "tool_input": {"file_path": "docs/notes.md", "content": PROSE_PLAN}},
    ),
    ("no file_path at all", {"tool_name": "Write", "tool_input": {"content": PROSE_PLAN}}),
]


def _counts(subject, stopdir):
    """`printf '%s' "$SUBJECT" | STOPDIR=... python3 -c '...' 2>/dev/null`."""
    try:
        proc = subprocess.run(
            ["python3", "-c", PROBE],
            input=subject.encode("utf-8", "surrogateescape"),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            env=dict(os.environ, STOPDIR=stopdir),
        )
    except OSError:
        return ""
    return hookio._command_substitution(proc.stdout.decode("utf-8", "surrogateescape"))


def run(ev):
    file_path = ev.field("tool_input", "file_path")
    if file_path == "":
        return hookio.ALLOW
    if not hookio.case_glob(file_path, *PLAN_GLOBS):
        return hookio.ALLOW

    fragments = ev.texts(
        ("tool_input", "content"),
        ("tool_input", "new_string"),
        ("tool_input", "new_source"),
        ("tool_input", "edits", "[]?", "new_string"),
    )
    if fragments == "":
        return hookio.ALLOW

    # A Write replaces the file outright; an Edit only amends it, so the resulting
    # document is at least the union of what is there and what is arriving.
    tool = ev.field("tool_name")
    subject = fragments
    if tool != "Write" and os.path.isfile(file_path):
        try:
            with open(file_path, encoding="utf-8", errors="surrogateescape") as handle:
                on_disk = handle.read()
        except OSError:
            on_disk = ""
        # `SUBJECT="$(cat "$FILE" 2>/dev/null)\n$FRAGMENTS"`: the substitution
        # strips the file's trailing newlines before the literal one is added.
        subject = "%s\n%s" % (hookio._command_substitution(on_disk), fragments)
        # The grandfather clause. An amendment to a plan that never had a task list is not the moment to demand one -- see the measured note above.
        if not hookio.grep_q(TASK_LINE, on_disk):
            ev.warn(GRANDFATHER % file_path)
            return hookio.ALLOW

    stopdir = "%s/.claude/hooks/stop" % hookio.repo_root()
    if not os.path.isfile("%s/wl_planfid.py" % stopdir):
        return hookio.ALLOW
    if not hookio.have("python3"):
        return hookio.ALLOW

    counts = _counts(subject, stopdir)
    if counts == "":
        return hookio.ALLOW

    # `${COUNTS%% *}` and `${COUNTS##* }`: before the first space, after the
    # last. Not `split()`, which would disagree the moment the probe printed anything but two fields.
    boxes = counts.split(" ", 1)[0]
    parsed = counts.rsplit(" ", 1)[-1]
    # `[ "${BOXES:-1}" -eq 0 ] 2>/dev/null || exit 0` -- a non-numeric value
    # makes `test` fail, and the `||` turns that failure into an allow.
    if boxes == "":
        boxes = "1"
    try:
        if int(boxes) != 0:
            return hookio.ALLOW
    except ValueError:
        return hookio.ALLOW

    try:
        parsed_n = int(parsed) if parsed != "" else 0
    except ValueError:
        parsed_n = 0
    why = WHY_INFLATED % parsed if parsed_n > 0 else WHY_EMPTY

    ev.warn_raw(MESSAGE % {"file": file_path, "why": why})
    return hookio.DENY
