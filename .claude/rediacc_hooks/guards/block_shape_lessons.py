"""Refuse or warn on a Bash command a lesson's own `Shape:` line names.

WHY (PLAN-experience-feedback P3, box D3). A lesson about one command shape used to need its own guard, or else stayed prose that reached a session only through the judge prompt. `.claude/hooks/trapguard/shapes.py` reads `Shape: pre:refuse|pre:warn <regex>` with its `Shape-Fires:` / `Shape-Silent:` samples from docs/agent-reference/TRAPS.md and from the user's memory notes; this guard applies every pre shape that LOADED to the command about to run. The grammar, the run text a regex is searched against and the memory directory are documented there, once.

A SHAPE THAT DID NOT LOAD IS NAMED, ONCE PER SESSION, and never applied. A regex that does not compile or a sample that does not behave as declared would otherwise be a refusal nobody tested. The note goes to stderr with exit 0, so a broken shape never blocks a call; `check:ci-trap-registry` reds on a broken TRAPS shape, and a broken memory-note shape is named here only, since CI cannot see the memory directory.

NEVER FAILS A CALL FOR ITS OWN SAKE. A corpus that cannot be read contributes no shapes. The dispatcher catches a crash and names it, as for every guard.
"""

import importlib.util
import sys

from rediacc_hooks import hookio, syspath

_MODULE = "trapguard_shapes"

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 70

# Without the refusal arm, a loaded pre:refuse shape (and the warn arm, which shares the match) admits silently.
DEFECT = ("hit = shapes.side_match(shape.pre, cmd)", 'hit = ""')

EDGE_CASES = [
    ("a millisecond date under uutils (TRAPS seed, warns)", "date +%s%3N"),
    ("a date run inside a substitution warns too", "t=$(date +%s%3N); echo $t"),
    ("a date with no precision digit", "date +%s"),
    ("the shape named inside an echo is not a run", 'echo "date +%s%3N"'),
    ("an unrelated command", "git status"),
]


def _shapes():
    """`.claude/hooks/trapguard/shapes.py`, loaded by file under its own name: putting `trapguard/` on sys.path would also make its `dispatch.py` importable as a top-level `dispatch`."""
    loaded = sys.modules.get(_MODULE)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(
        _MODULE, syspath.CLAUDE_DIR / "hooks" / "trapguard" / "shapes.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE] = module
    spec.loader.exec_module(module)
    return module


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if not cmd or cmd == "null":
        return hookio.ALLOW
    shapes = _shapes()
    # `SHAPE_ROOT` hands the suite a fixture corpus; otherwise the project the event stands in.
    loaded, problems = shapes.load(ev.env("SHAPE_ROOT") or ev.project_dir)
    session = ev.field("session_id")
    for _shape_id, where, problem in shapes.unseen_problems(session, problems):
        ev.warn(
            "lesson shape NOT LOADED (%s): %s. Fix the Shape lines; until then this lesson is "
            "prose only." % (where, problem)
        )
    refusals = []
    for shape in loaded:
        if shape.pre is None:
            continue
        hit = shapes.side_match(shape.pre, cmd)
        if not hit:
            continue
        if shape.pre.action == "refuse":
            refusals.append((shape, hit))
        else:
            ev.warn(
                "WARNING (lesson %s): %s\n  matched: `%s`\n  lesson: %s"
                % (shape.id, shape.lead(), hit[:120], shape.where())
            )
    if not refusals:
        return hookio.ALLOW
    ev.warn_raw(
        "BLOCKED by a lesson's Shape line:\n"
        + "".join(
            "  - %s\n    matched: `%s`\n    lesson:  %s\n" % (s.lead(), hit[:120], s.where())
            for s, hit in refusals
        )
        + "The lesson's Shape-Fires and Shape-Silent samples were checked before this refusal;\n"
        "if the command is the right one, its Shape-Silent samples say which spelling passes.\n"
    )
    return hookio.DENY
