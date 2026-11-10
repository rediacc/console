#!/usr/bin/env python3
"""Lesson shapes: a lesson that names the command it is about, checked where the command runs.

WHY (PLAN-experience-feedback P3). TRAPS entries and memory notes are prose, and prose reaches a session only when the judge prompt or a reader happens to carry it. Many lessons are about ONE command shape (`gh run rerun <id>` without `--failed`, `date +%s%3N`, a pytest run with `-p no:cacheprovider` that collected nothing), and a command shape is something a hook can see. A `Shape:` line on the lesson itself makes the lesson its own enforcer, so the next lesson of that kind needs no new guard: `block_shape_lessons` (pre-bash) refuses or warns, and trapguard's `rule_shape_lessons` (post-bash) adds a note after the output shows the trap.

THE GRAMMAR, one key per line. In TRAPS.md the lines sit in the entry's trailer AFTER `Residue:` (`wl_store.trap_entries` ends the trailer at the first key it does not know, so a Shape line above Residue would hide the Residue from the judge; `check:ci-trap-registry` refuses that order). In a memory note they sit anywhere in the body, outside fences.

    Shape: pre:refuse <regex>    refuse the Bash call (exit 2, stderr)
    Shape: pre:warn <regex>      admit it with a warning on stderr
    Shape: post <regex>          after the call, when Shape-Output also matches
    Shape-Output: <regex>        required with `post`: searched in stdout+stderr
    Shape-Fires: <sample>        1..n, each must fire
    Shape-Silent: <sample>       1..n, each must stay silent
    Shape-Say: <text>            optional: the sentence the refusal or note leads with

A command regex is searched (`re.search`) against EACH command bash would run, written `name arg arg ...` as `shellscan.every_run` finds it: after `cd x &&`, inside `bash -c '...'` and `$(...)`, with `VAR=1` prefixes dropped and quotes removed. So `^gh\\s+run\\s+rerun` matches the run and not `echo "gh run rerun 1"` or a commit message naming it, whose run text starts with `echo` or `git`. Anchor with `^` for that reason.

A pre sample is a command line. A post sample is `<command> => <output>`, split at the FIRST ` => `. An entry carries at most one pre and one post Shape; each declared side needs at least one Fires and one Silent sample of its own kind.

A SHAPE THAT DOES NOT BEHAVE IS NOT LOADED, and that is the anti-vacuity half. A regex that does not compile, a side with no sample in either direction, a Fires sample that stays silent or a Silent sample that fires: the shape is dropped from `load` and named in its problems list. `block_shape_lessons` names each problem once per session on stderr, and `check:ci-trap-registry` reds on any TRAPS Shape that does not load. A refusal from an untested regex is worse than no refusal: it teaches a session that the guard is noise.

THE SOURCES. TRAPS.md under the repo root the hook is handed, and the user's memory notes under `~/.claude/projects/<munged main checkout>/memory/` (`memory_dir`). The memory directory is READ-ONLY here and absent in CI, where it simply contributes nothing. `SHAPE_MEMORY_DIR` overrides it (tests point it at a temp dir; an empty value turns memory notes off).

COST. Both hooks run on every Bash call. The corpus is read whole only when it contains the text `Shape:`, the post rule tests each shape's OUTPUT regex before it parses the command or validates a sample, so a call whose output shows no trap never imports `shellscan`.
"""

import json
import os
import pathlib
import re
import sys

SHAPE = "Shape:"
SHAPE_OUTPUT = "Shape-Output:"
SHAPE_FIRES = "Shape-Fires:"
SHAPE_SILENT = "Shape-Silent:"
SHAPE_SAY = "Shape-Say:"
KEYS = (SHAPE_OUTPUT, SHAPE_FIRES, SHAPE_SILENT, SHAPE_SAY, SHAPE)

PRE_ACTIONS = ("refuse", "warn")
POST_SEP = " => "

TRAPS_REL = ("docs", "agent-reference", "TRAPS.md")
FENCE_RE = re.compile(r"^[ \t]*(```+|~~~+)")
DESCRIPTION_RE = re.compile(r"^description:\s*(.*?)\s*$")

# <repo>/.claude/hooks/trapguard/shapes.py: parents[2] is `.claude`, where `rediacc_hooks` lives.
_CLAUDE_DIR = pathlib.Path(__file__).resolve().parents[2]


class Side:
    """One side of a shape: pre (refuse or warn) or post (with an output regex)."""

    __slots__ = ("action", "command", "fires", "output", "silent", "where")

    def __init__(self, where, action, command):
        self.where = where  # "pre" or "post"
        self.action = action  # "refuse" / "warn" for pre, "note" for post
        self.command = command  # the compiled command regex
        self.output = None  # the compiled output regex (post only)
        self.fires = []
        self.silent = []


class Shape:
    """One lesson's shape: where it came from and its sides."""

    __slots__ = ("id", "path", "post", "pre", "say", "source", "title")

    def __init__(self, shape_id, source, path, title):
        self.id = shape_id
        self.source = source  # "traps" or "memory"
        self.path = path
        self.title = title
        self.say = ""
        self.pre = None
        self.post = None

    def where(self):
        """Where a reader finds the lesson, for a refusal or a problem line."""
        if self.source == "traps":
            return "docs/agent-reference/TRAPS.md (Trap-Id: %s)" % self.id
        return "memory note %s" % self.path

    def lead(self):
        return self.say or self.title


# -- reading the sources -------------------------------------------------------


def _key_of(line):
    for key in KEYS:
        if line.startswith(key):
            return key, line[len(key) :].strip()
    return None, ""


def traps_blocks(text):
    """(trap id, title, [(line no, key, value)]) per TRAPS entry carrying a Shape key, fences skipped.

    The trailer is the block between the `## ` heading and the first blank line, as `trap_registry.parse_corpus` and `wl_store.trap_entries` read it.
    """
    out = []
    fence = ""
    current = None
    in_trailer = False
    for number, line in enumerate(text.split("\n"), start=1):
        match = FENCE_RE.match(line)
        if match:
            char = match.group(1)[0]
            fence = char if fence == "" else ("" if fence == char else fence)
            continue
        if fence:
            continue
        if line.startswith("## ") and not line.startswith("### "):
            current = ["", line[3:].strip(), []]
            out.append(current)
            in_trailer = True
            continue
        if not in_trailer or current is None:
            continue
        if line.strip() == "":
            in_trailer = False
            continue
        if line.startswith("Trap-Id:"):
            current[0] = line[len("Trap-Id:") :].strip()
            continue
        key, value = _key_of(line)
        if key:
            current[2].append((number, key, value))
    return [(tid, title, rows) for tid, title, rows in out if rows]


def memory_rows(text):
    """(description, [(line no, key, value)]) for one memory note: Shape keys anywhere in the body, outside fences."""
    description = ""
    rows = []
    fence = ""
    lines = text.split("\n")
    body_from = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                body_from = index + 1
                break
            m = DESCRIPTION_RE.match(lines[index])
            if m:
                description = m.group(1).strip().strip("\"'")
    for index in range(body_from, len(lines)):
        line = lines[index]
        match = FENCE_RE.match(line)
        if match:
            char = match.group(1)[0]
            fence = char if fence == "" else ("" if fence == char else fence)
            continue
        if fence:
            continue
        key, value = _key_of(line)
        if key:
            rows.append((index + 1, key, value))
    return description, rows


def _main_checkout(root):
    """The checkout whose `.git` is a directory, following a worktree's `gitdir:` file. No subprocess: a hot path."""
    root = pathlib.Path(root)
    dotgit = root / ".git"
    try:
        if dotgit.is_dir() or not dotgit.is_file():
            return root
        text = dotgit.read_text(encoding="utf-8").strip()
    except OSError:
        return root
    if not text.startswith("gitdir:"):
        return root
    git_dir = (root / text[len("gitdir:") :].strip()).resolve()
    try:
        common = (git_dir / (git_dir / "commondir").read_text(encoding="utf-8").strip()).resolve()
    except OSError:
        common = git_dir
    return common.parent if common.name == ".git" else root


def memory_dir(root):
    """The user's memory notes for this repository, or None. `SHAPE_MEMORY_DIR` wins; an empty value means none.

    Claude Code names a project directory by its absolute path with every non-alphanumeric run turned into `-` (`/home/developer/console` -> `-home-developer-console`), and a worktree or lease shares the main checkout's memory, so the main checkout is resolved first.
    """
    if "SHAPE_MEMORY_DIR" in os.environ:
        value = os.environ["SHAPE_MEMORY_DIR"]
        return pathlib.Path(value) if value else None
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    projects = (pathlib.Path(base) if base else pathlib.Path.home() / ".claude") / "projects"
    try:
        main = _main_checkout(pathlib.Path(root).resolve())
    except (OSError, RuntimeError):
        return None
    return projects / re.sub(r"[^A-Za-z0-9]", "-", str(main)) / "memory"


def _read(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def corpus_sources(corpus):
    """[(id, "traps", path, title, rows)] for the TRAPS entries of one corpus file carrying a Shape key."""
    text = _read(pathlib.Path(corpus))
    if SHAPE not in text:
        return []
    return [(tid, "traps", str(corpus), title, rows) for tid, title, rows in traps_blocks(text)]


def memory_sources(folder):
    """[(note stem, "memory", path, description, rows)] for the memory notes in `folder` carrying a Shape key. MEMORY.md is the index, not a note."""
    out = []
    if folder is None or not pathlib.Path(folder).is_dir():
        return out
    for note in sorted(pathlib.Path(folder).glob("*.md")):
        if note.name == "MEMORY.md":
            continue
        body = _read(note)
        if SHAPE not in body:
            continue
        description, rows = memory_rows(body)
        if rows:
            out.append((note.stem, "memory", str(note), description, rows))
    return out


def raw_sources(root, memory=None):
    """Every lesson carrying a Shape key: TRAPS under `root`, then the memory notes. `memory` overrides `memory_dir(root)`."""
    folder = memory if memory is not None else memory_dir(root)
    return corpus_sources(pathlib.Path(root).joinpath(*TRAPS_REL)) + memory_sources(folder)


# -- building and validating ---------------------------------------------------


def _compile(pattern, what, problems):
    if pattern == "":
        problems.append("%s regex is empty" % what)
        return None
    try:
        return re.compile(pattern)
    except re.error as exc:
        problems.append("%s regex %r does not compile (%s)" % (what, pattern, exc))
        return None


def build(shape_id, source, path, title, rows):
    """(Shape or None, [problem]). Parses the rows; does NOT run the samples (see `validate`)."""
    problems = []
    shape = Shape(shape_id, source, path, title)
    if not shape_id:
        problems.append("the entry carrying Shape lines has no id")
    samples = []
    for number, key, value in rows:
        if key == SHAPE:
            head, _, pattern = value.partition(" ")
            pattern = pattern.strip()
            if head.startswith("pre:"):
                action = head[len("pre:") :]
                if action not in PRE_ACTIONS:
                    problems.append(
                        "line %d: `Shape: %s` is not pre:refuse or pre:warn" % (number, head)
                    )
                    continue
                if shape.pre is not None:
                    problems.append("line %d: a second pre Shape (one per lesson)" % number)
                    continue
                rx = _compile(pattern, "line %d: the pre" % number, problems)
                if rx is not None:
                    shape.pre = Side("pre", action, rx)
            elif head == "post":
                if shape.post is not None:
                    problems.append("line %d: a second post Shape (one per lesson)" % number)
                    continue
                rx = _compile(pattern, "line %d: the post" % number, problems)
                if rx is not None:
                    shape.post = Side("post", "note", rx)
            else:
                problems.append(
                    "line %d: `Shape: %s` names no side; write pre:refuse, pre:warn or post"
                    % (number, head)
                )
        elif key == SHAPE_OUTPUT:
            samples.append((number, "output", value))
        elif key == SHAPE_SAY:
            shape.say = value
        else:
            samples.append((number, "fires" if key == SHAPE_FIRES else "silent", value))
    for number, kind, value in samples:
        if kind == "output":
            if shape.post is None:
                problems.append("line %d: Shape-Output with no post Shape" % number)
            else:
                shape.post.output = _compile(value, "line %d: the output" % number, problems)
            continue
        if POST_SEP in value:
            side = shape.post
            if side is None:
                problems.append(
                    "line %d: a post sample (`cmd => output`) with no post Shape" % number
                )
                continue
            cmd, _, out = value.partition(POST_SEP)
            (side.fires if kind == "fires" else side.silent).append((cmd.strip(), out.strip()))
        else:
            side = shape.pre
            if side is None:
                problems.append(
                    "line %d: a pre sample (a command line) with no pre Shape; a post sample "
                    "is `<command> => <output>`" % number
                )
                continue
            (side.fires if kind == "fires" else side.silent).append((value, ""))
    if shape.pre is None and shape.post is None and not problems:
        problems.append("Shape lines name no usable side")
    if shape.post is not None and shape.post.output is None and not problems:
        problems.append("the post Shape has no Shape-Output regex")
    for side in (shape.pre, shape.post):
        if side is None:
            continue
        if not side.fires:
            problems.append("the %s Shape has no Shape-Fires sample" % side.where)
        if not side.silent:
            problems.append("the %s Shape has no Shape-Silent sample" % side.where)
    return (None if problems else shape), problems


def _every_run():
    """`shellscan.every_run`, importing `rediacc_hooks` from this checkout's `.claude/` when it is not already importable."""
    try:
        from rediacc_hooks import shellscan
    except ImportError:
        sys.path.insert(0, str(_CLAUDE_DIR))
        from rediacc_hooks import shellscan
    return shellscan.every_run


def run_texts(cmd):
    """`name arg arg ...` for every command bash would run in `cmd`."""
    every_run = _every_run()
    return [" ".join([run.name, *run.argv]) for run in every_run(cmd or "")]


def side_match(side, cmd, out=""):
    """The run text this side fires on, or "". A post side needs its output regex to match first."""
    if side.where == "post" and (side.output is None or not side.output.search(out or "")):
        return ""
    for text in run_texts(cmd):
        if side.command.search(text):
            return text
    return ""


def validate(shape):
    """[problem] when a Fires sample stays silent or a Silent sample fires, through the same `side_match` the hooks use."""
    problems = []
    for side in (shape.pre, shape.post):
        if side is None:
            continue
        for cmd, out in side.fires:
            if not side_match(side, cmd, out):
                problems.append(
                    "the %s Shape-Fires sample %r does not fire"
                    % (side.where, cmd if not out else "%s => %s" % (cmd, out))
                )
        for cmd, out in side.silent:
            if side_match(side, cmd, out):
                problems.append(
                    "the %s Shape-Silent sample %r fires"
                    % (side.where, cmd if not out else "%s => %s" % (cmd, out))
                )
    return problems


def load(root, memory=None, validate_samples=True):
    """(loaded shapes, [(id, where, problem)]). A shape with any problem is not loaded."""
    return load_sources(raw_sources(root, memory), validate_samples)


def load_sources(sources, validate_samples=True):
    """`load` over sources already read (`corpus_sources`, `memory_sources`): what `check:ci-trap-registry` calls with its own corpus seam."""
    shapes = []
    problems = []
    for shape_id, source, path, title, rows in sources:
        shape, found = build(shape_id, source, path, title, rows)
        if shape is not None and validate_samples:
            found = validate(shape)
        where = (
            "docs/agent-reference/TRAPS.md (Trap-Id: %s)" % shape_id
            if source == "traps"
            else "memory note %s" % path
        )
        if found:
            problems.extend((shape_id, where, p) for p in found)
            continue
        shapes.append(shape)
    return shapes, problems


# -- the post-bash side, for trapguard --------------------------------------------


def post_notes(cmd, out, root, memory=None):
    """The notes post shapes add for this call, as (shape id, text).

    The output regex runs FIRST on the unvalidated parse, so a call whose output shows no trap costs one corpus read and never imports shellscan. Only a shape whose output matched is validated, and a shape that fails validation says nothing here (the pre-bash guard names it).
    """
    notes = []
    for shape_id, source, path, title, rows in raw_sources(root, memory):
        shape, found = build(shape_id, source, path, title, rows)
        if found or shape is None or shape.post is None:
            continue
        if not shape.post.output.search(out or ""):
            continue
        if validate(shape):
            continue
        hit = side_match(shape.post, cmd, out)
        if hit:
            notes.append(
                (shape.id, "%s (matched `%s`; %s)" % (shape.lead(), hit[:80], shape.where()))
            )
    return notes


# -- naming a problem once per session ---------------------------------------------


def state_dir():
    """trapguard's own ledger directory (`TRAPGUARD_DIR`, else `~/.claude/trapguard`)."""
    return pathlib.Path(
        os.environ.get("TRAPGUARD_DIR") or (pathlib.Path.home() / ".claude" / "trapguard")
    )


def unseen_problems(session, problems):
    """The problems not yet named to this session, recording them as named. No session: all of them, nothing recorded."""
    if not session:
        return list(problems)
    path = state_dir() / ("shape-problems-%s.json" % re.sub(r"[^A-Za-z0-9_.-]", "_", session)[:80])
    try:
        seen = set(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        seen = set()
    fresh = [p for p in problems if "|".join(p) not in seen]
    if fresh:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(sorted(seen | {"|".join(p) for p in fresh})), encoding="utf-8"
            )
        except OSError:
            pass
    return fresh
