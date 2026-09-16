#!/usr/bin/env python3
"""PreToolUse: push the compacted history at the moment somebody edits the file,
and refuse a NEW plan that is a near-duplicate of one already on disk.

------------------------------------------------------------------------------
WHY THIS EXISTS, and it is the other half of compaction.

W12 lets a finished `agent/PLAN-*.md` shrink into a RECORD: the file keeps its
path, and its full text moves into a git blob. That trade only pays if somebody
reads the record. Nobody goes looking for a record about a file they are about
to change, because they do not know it exists -- which is the same blind spot
`wl_histfirst.py` records for commit history, measured on a real session: 2,494
Bash calls, zero `git log` invocations naming the file that was failing, while
eight lines of history held the answer.

So the record is pushed at the EDIT rather than waiting to be asked for. Every
record already carries a `Touched:` trailer naming the paths its plan cited, and
`agent/INDEX.md` carries the reverse map, so the question "what is recorded about
this file" is one file read.

------------------------------------------------------------------------------
FOUR PROPERTIES, each of which is what keeps a push from becoming a wall.

1. SILENT WHEN THE INDEX HAS NO EDGE. `--plan-why` answers "nothing is recorded"
   out loud, because a person asked and an empty answer is a result. This hook
   is UNASKED, and an unasked hook that speaks when it has nothing to say is a
   hook that gets turned off. The two behaviours are deliberately different and
   `wl_planrec.why_lines` returns which case it is so both can be right.

2. ONCE PER PATH PER EPOCH. The epoch is the harness's own, read from
   `ctx_budget` -- the counter `epoch-reset.py` bumps on PostCompact -- so
   "again after a compaction" means the same thing here as it does for the
   context bands. Repeating on every Edit of the same file would be noise inside
   a minute, and noise is how a real signal gets ignored.

3. CAPPED PER EPOCH. Even distinct paths stop after `WHY_ON_EDIT_CAP` pushes.
   A session that touches thirty recorded files does not need thirty notices; it
   needs the first few and then `--plan-why` when it wants more, which the last
   push says.

4. IT DOES NOT INSTRUCT. The text is facts -- a record path, a status, one line
   of its `## Why`, and the `git show` that recovers the rest. `band-notice.py`
   records the reason: text framed as an out-of-band command trips the model's
   prompt-injection defences and is surfaced to the user instead of acted on,
   and a trigger that gets surfaced instead of acted on does not fire.

------------------------------------------------------------------------------
THE ONE THING IT BLOCKS, and why that one is worth a refusal.

A `Write` that CREATES a new `agent/PLAN-<slug>.md` whose slug is a near
duplicate of a plan already on disk. This tree holds 79 plans and 2.0 MB, and it
got there one reasonable plan at a time; the housekeeping gate now demands 33 of
them be dealt with on a dated deadline. A second plan about the same thing is
not a second plan, it is the first one forgotten, and by the time anyone notices
both are on the clock.

The refusal is narrow on purpose. It fires only on CREATION (an existing file is
being edited, and editing a plan is the normal thing to do), only on a slug
whose significant tokens are a SUBSET of a neighbour's or overlap it past
`WHY_ON_EDIT_SIMILAR`, and only when both slugs carry at least two significant
tokens. `PLAN-w12-records.md` against `PLAN-w12-registers.md` is one shared
token out of three and is NOT refused; `PLAN-secret-migration-2.md` against
`PLAN-secret-migration.md` is a subset and is.

FAILS OPEN IN EVERY OTHER DIRECTION. No event, no path, an unreadable payload,
a missing module, an unparseable index: exit 0, silently. This hook can only
ever turn an allowed edit into a refused one, so every uncertainty resolves to
allowing it, and `check:ci-plan-record` is the backstop for anything it misses.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "context"))
sys.path.insert(0, str(HERE / "stop"))

#: How many pushes one epoch gets, and how much of a slug's tokens must overlap
#: before a new plan is refused as a duplicate. Both are tunable because both are
#: judgement calls that only a live corpus can settle, and a number nobody can
#: move is a number that gets worked around.
CAP = int(os.environ.get("WHY_ON_EDIT_CAP", "4"))
#: 0.7 is MEASURED, not chosen. Run against this tree's 81 real plan slugs on
#: 2026-09-06, a threshold of 0.6 refused 5 of them: `env-to-bitwarden` against
#: `env-to-bitwarden-v2` (a subset, and exactly the case this rule is for) and
#: the three `chunk-store-browse-{DECISION,engine,server}` plans, which share
#: 60 percent of their words and are a DELIBERATE decomposition of one subject
#: into three. Refusing a deliberate split is the false positive that would get
#: this hook disabled, so the bar sits above it: at 0.7 the trio passes and the
#: subset case still fires, leaving 2 of 81 refused and both of them true.
SIMILAR = float(os.environ.get("WHY_ON_EDIT_SIMILAR", "0.7"))

#: Slug words that carry no subject. Without these, every plan in this tree
#: shares "plan" and "fix" with every other and the duplicate test fires on
#: everything, which is the same as firing on nothing.
STOPWORDS = frozenset(
    ("plan", "the", "a", "an", "of", "for", "and", "to", "in", "on", "fix", "v2", "wip", "new")
)

PLAN_RE = re.compile(r"(?:^|/)agent/PLAN-(?P<slug>[A-Za-z0-9._-]+)\.md$")
EDIT_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit")


def read_event():
    """The hook payload, or {}. Never blocks on a terminal, never raises."""
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 -- an unreadable payload is "allow", not a crash
        return {}


def tokens(slug):
    """The significant words of a plan slug, lowercased and de-duplicated."""
    return {
        w for w in re.split(r"[-_.]+", (slug or "").lower()) if len(w) > 1 and w not in STOPWORDS
    }


def similar_plans(root, slug):
    """[(rel, why)] for every existing plan whose slug is a near duplicate.

    FILENAMES ONLY. No plan is opened: this runs on the Write of every new plan
    and the whole point of the index is that the answer costs one directory
    listing. A near duplicate that differs in filename and matches in content is
    out of scope here and belongs to a person reading `--plan-why`.
    """
    mine = tokens(slug)
    if len(mine) < 2:
        # A one-word slug is too coarse to judge. `PLAN-secrets.md` against
        # `PLAN-secrets-rotation.md` would be a subset and refused, and the
        # short one is exactly the shape a genuinely new umbrella plan takes.
        return []
    out = []
    try:
        others = sorted((root / "agent").glob("PLAN-*.md"))
    except OSError:
        return []
    for p in others:
        their_slug = p.stem[len("PLAN-") :]
        if their_slug == slug:
            continue  # the file itself, when a Write lands over an existing plan
        theirs = tokens(their_slug)
        if len(theirs) < 2:
            continue
        if mine <= theirs or theirs <= mine:
            out.append(("agent/" + p.name, "one slug's words are a subset of the other's"))
            continue
        overlap = len(mine & theirs) / float(len(mine | theirs))
        if overlap >= SIMILAR:
            out.append(("agent/" + p.name, "%.0f%% of the words are shared" % (overlap * 100)))
    return out


def epoch_of(session_id):
    """The harness's own epoch counter, or 0 when the context hooks are absent.

    READ, NEVER WRITTEN. `ctx_budget.save_state` replaces the whole document, so
    writing our keys into that file would clobber whatever `band-notice.py` had
    put there and vice versa. Our own state lives beside it.
    """
    try:
        import ctx_budget as B  # noqa: PLC0415 -- optional; absence must not block an edit

        return int(B.load_state(session_id).get("epoch", 0) or 0)
    except Exception:  # noqa: BLE001
        return 0


def state_file(session_id):
    try:
        import ctx_budget as B  # noqa: PLC0415 -- see epoch_of

        return B.state_dir() / ("why-%s.json" % B.session_slug(session_id))
    except Exception:  # noqa: BLE001
        return HERE / "context" / "state" / "why-unknown.json"


def load_seen(session_id, epoch):
    """{"epoch": n, "paths": [...], "n": k} for THIS epoch, reset across one."""
    try:
        doc = json.loads(state_file(session_id).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- absent or corrupt both mean "nothing pushed yet"
        doc = {}
    if int(doc.get("epoch", -1)) != epoch:
        return {"epoch": epoch, "paths": [], "n": 0}
    doc.setdefault("paths", [])
    doc.setdefault("n", 0)
    return doc


#: The remembered-path list is trimmed to this many entries. A long session can
#: touch hundreds of files, and the list exists only to answer "have I already
#: looked at this path in this epoch" -- a bounded FIFO answers that for
#: everything recent, and the worst case of forgetting an old entry is ONE
#: repeated notice, which is cheaper than an unbounded state file.
SEEN_MAX = int(os.environ.get("WHY_ON_EDIT_SEEN_MAX", "400"))


def save_seen(session_id, doc):
    doc["paths"] = doc.get("paths", [])[-SEEN_MAX:]
    f = state_file(session_id)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, f)
    except OSError:
        pass  # a push that cannot be remembered repeats once; it must never block


def emit(text):
    json.dump(
        {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}},
        sys.stdout,
    )
    sys.stdout.write("\n")


def block(rel, hits):
    sys.stderr.write(
        "BLOCKED: %s would be a NEW plan whose name is a near duplicate of one that\n"
        "already exists.\n\n%s\n\n"
        "This tree holds a plan for almost everything, and it got that way one\n"
        "reasonable plan at a time -- the housekeeping gate now demands 33 of them be\n"
        "dealt with on a dated deadline. A second plan about the same subject is not a\n"
        "second plan, it is the first one forgotten, and both then sit on the clock.\n\n"
        "WHAT TO DO INSTEAD.\n\n"
        "  Same work? Add your boxes to the existing plan. Its history, its ledger\n"
        "  attestations and every citation of its path stay intact.\n\n"
        "  The neighbour is a COMPACTED RECORD (Status: compacted or parked)? Its full\n"
        "  text is in a git blob. Read it before you rewrite it:\n"
        "      .claude/hooks/stop/worklist.py --plan-why %s\n"
        "      .claude/hooks/stop/worklist.py --plan-revive <you> <that path> --write\n\n"
        "  Genuinely different work? Say so in the name. The test is on the slug's\n"
        "  significant words, so a slug that names what is actually different about\n"
        "  this plan passes -- and is a better filename anyway.\n"
        % (
            rel,
            "\n".join("  %s  (%s)" % (r, why) for r, why in hits),
            rel,
        )
    )
    sys.exit(2)


def main():
    event = read_event()
    tool = str(event.get("tool_name") or "")
    if tool not in EDIT_TOOLS:
        return 0
    ti = event.get("tool_input") or {}
    raw_path = str(ti.get("file_path") or ti.get("notebook_path") or "")
    if not raw_path:
        return 0

    root = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or HERE.parents[1])
    try:
        rel = str(pathlib.Path(raw_path).resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        rel = raw_path.lstrip("./")

    # ---- the one refusal: a NEW plan that duplicates an existing one --------
    m = PLAN_RE.search("/" + rel)
    if m and tool == "Write" and not (root / rel).exists():
        hits = similar_plans(root, m.group("slug"))
        if hits:
            block(rel, hits)
        return 0

    # ---- the push ----------------------------------------------------------
    session_id = str(event.get("session_id") or "")
    epoch = epoch_of(session_id)
    seen = load_seen(session_id, epoch)
    if rel in seen["paths"] or seen["n"] >= CAP:
        return 0

    try:
        import wl_planrec as R  # noqa: PLC0415 -- optional; absence must not block an edit

        lines, state = R.why_lines(root, rel)
    except Exception:  # noqa: BLE001 -- a broken index must never cost an edit
        return 0
    if state != R.WHY_EDGES or not lines:
        # SILENT. See property 1: this hook was not asked, so nothing to say
        # means nothing said. The state is still recorded, so a path with no
        # edge is not re-looked-up on every keystroke of the same file.
        seen["paths"].append(rel)
        save_seen(session_id, seen)
        return 0

    seen["paths"].append(rel)
    seen["n"] += 1
    save_seen(session_id, seen)
    tail = ""
    if seen["n"] >= CAP:
        tail = (
            "\n\nThat is the last of %d automatic notices this epoch. Ask for the rest:\n"
            "  .claude/hooks/stop/worklist.py --plan-why <path>" % CAP
        )
    emit(
        "%s is named by the compacted plan history:\n\n%s\n\n"
        "Those plans are finished and their full text is in a git blob, not in the\n"
        "file. `git show <blob>` reads one in full.%s" % (rel, "\n".join(lines), tail)
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 -- see the module docstring: fails open, always
        sys.exit(0)
