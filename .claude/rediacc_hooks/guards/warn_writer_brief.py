"""warn_writer_brief: tell the lead what a writer about to start on these files should hear from prior reviews and from the doc generator.

THE ASK (agent/plans/PLAN-experience-feedback.md P1 and P4, box A2). About 6,500 per-commit review findings recur by class (doc contradicts code, a missing control test, a swallowed error) and none of them reached the writer about to edit the same files, so the same finding came back on the same file. And a writer whose files feed a generated doc region learned so from the commit hook, after the work, rather than from its brief.

THE DECISION, for an Agent or Task call, in the order the branches are taken:

    not a spawn                                      silent
    a read-only type (Plan, Explore, ...)            silent
    no `Owns:` line, a malformed one, `Owns: none`   silent
    only universal globs (`**`)                      silent
    no class reaches MIN_FIXED and gen-docs is quiet silent
    otherwise                                        the lines, delivered per DELIVERY
    anything raises or the deadline passes           silent, one stderr note

P1: `wl_reviewclass.brief_lines` (`.claude/hooks/stop/wl_reviewclass.py`) over the review index of the PROJECT ROOT (`wl_core`'s resolution, which is how a test pins a fixture): one line per class with at least three fixed high or medium findings on the Owns paths, at most three.

P4: the Owns globs are materialised against `git ls-files` of THIS GUARD'S OWN CHECKOUT, plus each literal path (a file the writer may create), and handed to `node scripts/gen/gen-docs.ts --could-affect` in that same checkout. The generator judges its own tree, so the guard asks the generator that ships beside it; in a session the two are one checkout, because settings.json runs every hook from `$CLAUDE_PROJECT_DIR/.claude`. A hit adds the step to run `npx tsx scripts/gen/gen-docs.ts --write` in the lease.

DELIVERY, AND WHY IT IS ONE CONSTANT. Whether a PreToolUse hook's `updatedInput` reaches an Agent spawn is unproven here; the plan's box E0 settles it live. Until then `DELIVERY` is `ADDITIONAL_CONTEXT`: the prompt goes out unchanged and the lead is handed the lines to paste or to send with SendMessage. `UPDATED_INPUT` appends the same block to the spawn's prompt and still tells the lead, in `additionalContext`, what was appended. Flipping the constant is the whole switch; the suite tests both encodings.

IT NEVER REFUSES. A brief line is advice, the review history is a heuristic, and the commit hook still owns the gen-docs refusal. `run` returns ALLOW on every path, including every failure.

STDOUT IS EXCLUSIVE ON THIS CHAIN, the same arrangement `warn_staged_shape_duplication` documents for pre-bash: no other pre-agent guard writes to stdout (block_agent_cap, block_focus_spawn and block_plan_concurrency speak on stderr only), so the chain's concatenated stdout is this guard's one JSON document or nothing. A second stdout speaker on this chain would make both unparseable; the suite runs the whole chain and parses its stdout to catch that.

LAST IN THE CHAIN (ORDER 6), behind block_plan_concurrency (ORDER 5). A refused spawn never reaches this guard, so no line is computed for a writer that does not start, and block_plan_concurrency stays the last guard that can refuse.

NO ENVIRONMENT READ here; `wl_core` resolves the root from the payload as it does for block_plan_concurrency.

OWN_SUITE = True: a guard authored directly, with no bash original. `test-warn_writer_brief.py` beside it drives it through the dispatcher, alone and as part of the chain.
"""

import importlib
import json
import os
import pathlib
import subprocess
import tempfile
import time

from rediacc_hooks import hookio, syspath

CHAIN = "pre-agent"
OWN_SUITE = True
ORDER = 6

# The planted defect: with the lines dropped the guard is silent on every spawn, and the suite's firing cases must turn red.
DEFECT = ("lines = p1 + p4", "lines = []")

ADDITIONAL_CONTEXT = "additionalContext"
UPDATED_INPUT = "updatedInput"
# THE E0 SWITCH. Flip to UPDATED_INPUT once box E0 proves a PreToolUse hook's updatedInput reaches an Agent spawn.
DELIVERY = ADDITIONAL_CONTEXT

STOP_DIR = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "stop"
# This guard's own checkout: the generator that answers P4 ships here.
REPO = pathlib.Path(__file__).resolve().parents[3]
GEN_DOCS_REL = "scripts/gen/gen-docs.ts"
# The whole budget, from entry. The chain entry's own timeout is larger; this keeps the spawn fast.
DEADLINE_S = 2.5
# gen-docs is not asked once less than this remains.
MIN_GEN_DOCS_S = 0.3

GEN_DOCS_LINE = (
    "These Owns can move generated doc regions (%s): run `npx tsx scripts/gen/gen-docs.ts --write` "
    "in the lease and commit what it rewrites with the change."
)
CONTEXT_HEAD = {
    ADDITIONAL_CONTEXT: (
        "writer-brief: %d line(s) from prior reviews and the doc generator apply to this %r "
        "writer's Owns. The spawn went out unchanged; paste them into the brief or send them with "
        "SendMessage:"
    ),
    UPDATED_INPUT: "writer-brief: appended %d line(s) to this %r writer's prompt:",
}
PROMPT_HEAD = "From prior reviews and the doc generator (warn_writer_brief):"
# ---- the differential's world: a tree whose review store holds three fixed doc findings on a/x.py ------
WORLD = os.path.join(tempfile.gettempdir(), "rediacc-guard-writerbrief-world")
_SID = "c0ffee11-1111-2222-3333-444444444444"


def _brief_world(_unused):
    """WORLD/tree: a project root (a `.git` directory) whose agent/reviews holds three fixed medium doc-contradicts-code findings on a/x.py, rendered by `wl_review` itself. `a/**` matches no file of the real checkout, so the gen-docs half is never asked and the cases answer the same wherever they run."""
    tree = pathlib.Path(WORLD) / "tree"
    (tree / ".git").mkdir(parents=True, exist_ok=True)
    syspath.on_sys_path(STOP_DIR)
    review_mod = importlib.import_module("wl_review")
    at = "2026-11-10T00:00:00Z"
    for n in range(3):
        sha = ("%08x" % (n + 1)) + "0" * 32
        finding = review_mod.Finding(
            "%s.1" % sha[:8],
            "medium",
            "a/x.py",
            1,
            "in-diff",
            "The docstring says the guard refuses, but it returns ALLOW on that path.",
            "fixed %s | abcdef01 %s" % ("f" * 40, at),
        )
        review = review_mod.Review(
            sha=sha,
            subject="s",
            branch="1110-1",
            reviewed_at=at,
            model="m",
            verdict="findings",
            findings=[finding],
        )
        target = review_mod.review_path(tree, "1110-1", sha)
        target.parent.mkdir(parents=True, exist_ok=True)
        hookio.write_world_file(target, review_mod.render(review))
    return WORLD


FIXTURES = {"writerbrief-world": _brief_world}

# CLAUDE_PROJECT_DIR is read by wl_core's root resolution, never by this guard.
ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("writerbrief", {"CLAUDE_PROJECT_DIR": "{FIXTURE:writerbrief-world}/tree"}, {})
]


def _spawn(kind, text):
    return {
        "tool_name": "Agent",
        "session_id": _SID,
        "cwd": "/nonexistent-writer-brief-fixture",
        "tool_input": {"subagent_type": kind, "description": "fixture", "prompt": text},
    }


EDGE_CASES = [
    ("writer-on-files-with-three-fixed-findings", _spawn("general-purpose", "work\nOwns: a/**")),
    ("writer-on-an-untouched-file", _spawn("general-purpose", "work\nOwns: b/untouched/**")),
    ("reader-on-the-same-files", _spawn("Explore", "read\nOwns: a/**")),
    (
        "writer-that-edits-nothing",
        _spawn("general-purpose", "work\nOwns: none -- this writer only reports what it reads"),
    ),
    ("writer-with-no-owns-line", _spawn("general-purpose", "fix the docstring in a/x.py")),
    ("not-a-spawn", {"tool_name": "Bash", "tool_input": {"command": "true"}}),
]

NOT_RUN = "writer-brief: did not run (%s), so this %r spawn carries no brief lines.\n"
# Only the P4 half failed: the review lines, when there are any, still go out, so this note must not say none did.
GEN_DOCS_NOT_RUN = (
    "writer-brief: the gen-docs question did not run (%s), so this %r spawn carries no "
    "gen-docs line; any review lines still went out.\n"
)


class _LateError(Exception):
    """The deadline passed before an answer."""


def _tracked(repo, timeout):
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(repo),
        capture_output=True,
        timeout=timeout,
        check=True,
    ).stdout.decode("utf-8", "replace")
    return [p for p in out.split("\0") if p]


def _gen_docs_line(globs, planconc, left):
    """The P4 line, or "" when gen-docs names nothing. Raises on any failure; the caller turns that into the one note."""
    script = REPO / GEN_DOCS_REL
    if not script.is_file():
        raise FileNotFoundError("%s is absent" % GEN_DOCS_REL)
    if left() < MIN_GEN_DOCS_S:
        raise _LateError("no time left for gen-docs")
    # Every child is bounded by what is left of the whole budget, so the 2.5 s holds however slow the checkout is.
    paths = set(planconc.materialise(globs, _tracked(REPO, min(2.0, left()))))
    paths.update(g for g in globs if not planconc._has_wild(g))
    if not paths:
        return ""
    if left() < MIN_GEN_DOCS_S:
        raise _LateError("no time left for gen-docs after listing the tracked files")
    proc = subprocess.run(
        ["node", str(script), "--could-affect"],
        cwd=str(REPO),
        input="\n".join(sorted(paths)) + "\n",
        capture_output=True,
        text=True,
        timeout=left(),
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "gen-docs --could-affect exited %d: %s"
            % (proc.returncode, (proc.stderr.strip().splitlines() or [""])[-1][:160])
        )
    doc = json.loads(proc.stdout)
    affected = list(doc.get("affected") or [])
    targets = list(doc.get("targets") or [])
    if not affected and not targets:
        return ""
    named = []
    if affected:
        named.append("providers: " + ", ".join(affected))
    if targets:
        named.append("region documents: " + ", ".join(targets[:3]))
    return GEN_DOCS_LINE % "; ".join(named)


def render(lines, kind, tool_input, delivery=None):
    """The one stdout document for `lines`, in the `delivery` encoding (DELIVERY unless a test names one)."""
    delivery = delivery or DELIVERY
    bullets = "\n".join("- " + ln for ln in lines)
    specific: dict[str, object] = {
        "hookEventName": "PreToolUse",
        "additionalContext": "%s\n%s" % (CONTEXT_HEAD[delivery] % (len(lines), kind), bullets),
    }
    if delivery == UPDATED_INPUT:
        prompt = str(tool_input.get("prompt") or "")
        specific["updatedInput"] = dict(
            tool_input, prompt="%s\n\n%s\n%s\n" % (prompt.rstrip("\n"), PROMPT_HEAD, bullets)
        )
    return json.dumps({"hookSpecificOutput": specific})


def run(event):
    doc = event.doc
    if not isinstance(doc, dict) or doc.get("tool_name") not in ("Agent", "Task"):
        return hookio.ALLOW
    raw_input = doc.get("tool_input")
    tool_input = raw_input if isinstance(raw_input, dict) else {}
    kind = str(tool_input.get("subagent_type") or "general-purpose")
    entered = time.monotonic()

    def left():
        return DEADLINE_S - (time.monotonic() - entered)

    try:
        syspath.on_sys_path(STOP_DIR)
        # Imported by name rather than by statement: the Stop directory is on sys.path only from the line above.
        core = importlib.import_module("wl_core")
        planconc = importlib.import_module("wl_planconc")
        wl_reviewclass = importlib.import_module("wl_reviewclass")
        wl_roster = importlib.import_module("wl_roster")

        cwd = str(doc.get("cwd") or event.cwd)
        root = core.project_root(core.project_start({"cwd": cwd}))
        if kind in wl_roster.read_only_types(root):
            return hookio.ALLOW
        text = "%s\n%s" % (tool_input.get("description") or "", tool_input.get("prompt") or "")
        declared = planconc.declared_owns(text)
        if not declared:
            return hookio.ALLOW
        globs = [
            g for g in planconc.normalize_owns(list(declared))[0] if not planconc.is_universal(g)
        ]
        if not globs:
            return hookio.ALLOW
        notes: list[str] = []
        p1 = wl_reviewclass.brief_lines(wl_reviewclass.index(root, notes=notes), globs)
        for note in notes:
            event.warn("writer-brief: %s" % note)
        try:
            line = _gen_docs_line(globs, planconc, left)
        except Exception as exc:
            event.warn_raw(
                GEN_DOCS_NOT_RUN % ("%s: %s" % (type(exc).__name__, str(exc)[:200]), kind)
            )
            line = ""
        p4 = [line] if line else []
        lines = p1 + p4
        if not lines:
            return hookio.ALLOW
        event.say(render(lines, kind, tool_input))
        event.warn("writer-brief: %d line(s) handed to the lead (%s)" % (len(lines), DELIVERY))
    except Exception as exc:
        event.warn_raw(NOT_RUN % ("%s: %s" % (type(exc).__name__, str(exc)[:160]), kind))
    return hookio.ALLOW
