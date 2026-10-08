"""Refuse a `git commit` whose plan files lose an open box by G-A1's own signature, or whose QUEUE.md comes apart.

THE INCIDENT, 2026-10-08, two defects in one commit and both found only after it landed:

1. 31d2c28c ticked two boxes by REWRITING the box line. `- [ ] T16 Retarget writers:` became `- [x] T16 Retarget writers: (done 2026-10-08: ...evidence...)`. The evidence sits inside the first 120 normalised characters `check_plan_boxes.sig` hashes, so the done box carried a NEW signature and the open one at the base had no home: `check:ci-plan-boxes` (G-A1) reported both boxes as "open at base and GONE at HEAD". The plans had also just moved with `check_plan_folders.py --move`, so the HEAD text sat at `agent/plans/PLAN-x.md` and the new text at `agent/plans/_done/PLAN-x.md`, with a `Moved-To:` stub left at the old path.
2. A scripted edit of `agent/plans/QUEUE.md` sliced between `## Promoted` and the first occurrence of `## Generated`, which also starts a prose span earlier in the file. The end index fell below the start and the `## Settings` / `## In flight` sections were written twice. `check:ci-plan-record` (RQ-SETTINGS: a `stop-hook` fence outside `## Settings`) caught it a commit later.

THE CORRECT TICK flips only the bracket and puts the evidence on an indented line below, which no signature reads:

    - [x] T16 Retarget writers:
        (ticked) 2026-10-08 by d778be9d: c2ca68dfe, account.py:11 ...

WHAT IS COMPARED. For every plan file the commit names (`agent/plans/PLAN-*.md`, its `_done/` and `_removed/` folders, and the legacy `agent/PLAN-*.md`), the HEAD version against the version the commit will write: the working tree under a pathspec or `-a`, the index otherwise. A MOVE is resolved the way `check_plan_folders.py --move` leaves it: a `_done/` or `_removed/` path with no HEAD version is judged against `HEAD:agent/plans/<basename>`, and a `Moved-To:` stub is never itself a plan. A box open at HEAD survives when its signature is open or done anywhere in the result (the committed files, then the tracked plans the commit leaves at their HEAD version), or when `loose_sig` finds it, which is G-A1's own second chance for a re-spelled citation. Deleting a box is G-A1's business too and is refused the same way.

THE SIGNATURE IS IMPORTED, NEVER RESTATED. `sig`, `loose_sig`, `ruled_at_base`, `ARCHIVE_DIR` and the parser (`wl_planfile.plan_boxes`, through the gate's own `PF`) come from `.ci/scripts/quality/check_plan_boxes.py` loaded as a module, so this guard and the gate cannot disagree about what a box is. The QUEUE arm imports `wl_planqueue.settings`, the exact validator RQ-SETTINGS runs, and adds the duplicate-heading and duplicate-marker test the generated section cannot answer without a full render.

DIFFERENTIAL, NOT ABSOLUTE. A QUEUE problem is refused only when HEAD's queue does not already carry it, and a plan box only when it was OPEN at HEAD, so pre-existing debt never blocks an unrelated commit.

IT FAILS OPEN on a git or import error, as the sibling guards do, and says on stderr that the commit went UNEXAMINED. It touches only the committed plan files plus one `git ls-tree` and one `git cat-file --batch` on the refusal path; the whole-tree gate is never run.
"""

import difflib
import importlib.util
import os
import pathlib
import re
import subprocess
import sys

from rediacc_hooks import commit_policy, hookio

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 56

# The verdict line. With it gone every lost box and every broken queue is committed, which is the incident this guard exists for.
DEFECT = ("    if lost or queue_new:", "    if False:")

PLAN_RX = re.compile(r"^agent/(?:plans/(?:_done/|_removed/)?)?PLAN-[^/]+\.md$")
QUEUE_REL = "agent/plans/QUEUE.md"
MOVE_DIRS = ("agent/plans/_done/", "agent/plans/_removed/")
MOVE_SOURCES = ("agent/plans/", "agent/")

UNEXAMINED = (
    "block-plan-box-rewrite: %s; the plan files in this commit went UNEXAMINED "
    "(the guard did not judge them)."
)

REMEDY = """
A box is the durable record of a task, and `check:ci-plan-boxes` (G-A1) keys it on
the first 120 normalised characters of its text. Rewriting that text is a deletion
plus an unrelated addition, and the gate will report this box as open at the base
and GONE at HEAD.

  - Tick by flipping ONLY the bracket, and put the evidence on an indented line
    below, which no signature reads:
        - [x] <the box text, byte for byte>
            (ticked) <YYYY-MM-DD> by <session>: <evidence>
  - Blocked: `- [?]` with the text unchanged.
  - Not this plan's: move the line, unchanged, into a live plan.
"""

QUEUE_REMEDY = """
QUEUE.md is read by the Stop hook and rendered by `check:ci-plan-record`. A level-2
heading, a generated marker or a `stop-hook` fence that appears twice means the
reader silently takes one of them and the gate fails later. Repair the file so each
section appears once (`git diff -- agent/plans/QUEUE.md` shows the duplicate), then
rerun `npm run check:ci-plan-record`.
"""

_GATE = None


def _load_gate():
    """`check_plan_boxes` as a module, plus `wl_planqueue` and `wl_store`, from THIS checkout's `.ci` and Stop hook.

    `sys.path` is restored afterwards: the gate puts `.ci`, `.ci/scripts/quality` and `.claude/hooks/stop` on it, and a dispatcher process that runs every guard of the chain should not inherit three directories of unrelated module names. The modules stay in `sys.modules`, so the gate's own references keep working. Cached for the life of the process.
    """
    global _GATE  # noqa: PLW0603 -- one load per dispatcher process
    if _GATE is not None:
        return _GATE
    root = hookio.repo_root()
    quality = root / ".ci" / "scripts" / "quality"
    saved = list(sys.path)
    try:
        sys.path.insert(0, str(quality))
        spec = importlib.util.spec_from_file_location(
            "check_plan_boxes_for_guard", quality / "check_plan_boxes.py"
        )
        if spec is None or spec.loader is None:
            msg = "cannot load %s" % (quality / "check_plan_boxes.py")
            raise ImportError(msg)
        gate = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(gate)
        except SystemExit as exc:
            # The gate exits 1 with a VACUOUS INPUT message when it cannot import its parser.
            msg = "check_plan_boxes.py exited %s while loading" % exc.code
            raise ImportError(msg) from exc
        import wl_planqueue  # noqa: PLC0415 -- on sys.path only inside this window
        import wl_store  # noqa: PLC0415 -- same
    finally:
        sys.path[:] = saved
    _GATE = (gate, wl_planqueue, wl_store)
    return _GATE


# --------------------------------------------------------------------------- reading the two versions ---------------------------------------------------------------------------


def _show(repo, spec):
    """`git show <spec>` as text, None when the object does not exist."""
    return commit_policy.git(["show", spec], cwd=repo)


def _stub_target(store, text):
    """The `Moved-To:` target when `text` is a stub, by `wl_store`'s own two-halves test, else ""."""
    head = (text or "")[: store.STUB_PROBE_BYTES]
    if not store._STUB_STATUS_RE.search(head):
        return ""
    m = store._STUB_TARGET_RE.search(head)
    return m.group(1) if m else ""


def _status(gate, text):
    """The plan's Status, read by the same two regexes `wl_checks.plan_records` uses for the ledger row."""
    ck = gate.CK
    head = "\n".join((text or "").splitlines()[: ck.PLAN_HEADER_LINES])
    m = ck.PLAN_STATUS_RE.search(head) or ck.PLAN_STATUS_INLINE_RE.search(head)
    return m.group(1).lower() if m else "UNKNOWN"


def _head_corpus(repo, exclude):
    """{rel: text} for the tracked plans this commit leaves at their HEAD version. Two processes, refusal path only."""
    listed = commit_policy.git(["ls-tree", "-r", "--name-only", "HEAD", "--", "agent"], cwd=repo)
    rels = [r for r in (listed or "").split("\n") if PLAN_RX.match(r) and r not in exclude]
    if not rels:
        return {}
    feed = "".join("HEAD:%s\n" % r for r in rels).encode("utf-8")
    try:
        proc = subprocess.run(
            ["git", "cat-file", "--batch"],
            cwd=repo,
            input=feed,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("git cat-file --batch failed: %s" % exc) from exc
    if proc.returncode != 0:
        # An empty corpus would read every box as lost-nowhere; the outer handler warns UNEXAMINED and allows.
        raise RuntimeError("git cat-file --batch exited %d" % proc.returncode)
    out, data, pos = {}, proc.stdout, 0
    for rel in rels:
        nl = data.find(b"\n", pos)
        if nl < 0:
            break
        header = data[pos:nl].split()
        pos = nl + 1
        if len(header) < 3 or header[1] != b"blob":
            continue
        size = int(header[2])
        out[rel] = data[pos : pos + size].decode("utf-8", "replace")
        pos += size + 1
    return out


def _box_line(gate, text, want):
    """The raw line of `text` whose task signs as `want`, or ""."""
    for line in (text or "").splitlines():
        if not (gate.PF.OPEN_BOX_LINE.match(line) or gate.PF.DONE_BOX_LINE.match(line)):
            continue
        tasks = gate.PFID.plan_tasks(line)
        if tasks and gate.sig(tasks[0]) == want:
            return line
    return ""


def _nearest(gate, text, line, before):
    """The box line of `text` that `line` most likely became, for the message. "" when nothing resembles it.

    Only lines whose signature is NEW against `before` are candidates: a box that kept its text is not what this one turned into, and without the filter a short sibling box outscores the long rewritten line it really became.
    """
    known: set[str] = set()
    o, d = gate.PF.plan_boxes(before or "")
    known.update(gate.sig(t) for t in list(o) + list(d))
    body = _BRACKET.sub("", line).strip()
    best, score = "", 0.0
    for cand in (text or "").splitlines():
        if not (gate.PF.OPEN_BOX_LINE.match(cand) or gate.PF.DONE_BOX_LINE.match(cand)):
            continue
        tasks = gate.PFID.plan_tasks(cand)
        if tasks and gate.sig(tasks[0]) in known:
            continue
        other = _BRACKET.sub("", cand).strip()
        ratio = difflib.SequenceMatcher(None, body, other[: len(body) + 16]).ratio()
        if ratio > score:
            best, score = cand, ratio
    return best if score >= 0.5 else ""


_BRACKET = re.compile(r"^\s*[-*+]\s+\[[ xX?>]\]\s+")


# --------------------------------------------------------------------------- the two judgments ---------------------------------------------------------------------------


def lost_boxes(gate, store, repo, plan_paths, new_text):
    """[(before_rel, head_line, new_line, note)] for every box open at HEAD that the commit leaves with no home.

    `new_text(rel)` is what the commit writes at `rel` (None for a deletion). EXPORTED for the suite.
    """
    befores = {}  # HEAD-side rel -> HEAD text
    after_of = {}  # HEAD-side rel -> the text it became, for the message
    notes = {}
    news = {rel: new_text(rel) for rel in plan_paths}
    for rel in plan_paths:
        head = _show(repo, "HEAD:%s" % rel)
        new = news[rel]
        target = _stub_target(store, new) if new is not None else ""
        if head is not None and not _stub_target(store, head):
            befores[rel] = head
            if target:
                if target in news:
                    after_of[rel] = news[target] or ""
                else:
                    after_of[rel] = _show(repo, "HEAD:%s" % target) or ""
                    if not after_of[rel]:
                        notes[rel] = (
                            "its stub points at %s, which is neither in this commit nor at HEAD"
                            % target
                        )
            else:
                after_of.setdefault(rel, new or "")
        elif head is None and rel.startswith(MOVE_DIRS):
            name = rel.rsplit("/", 1)[-1]
            for src in MOVE_SOURCES:
                old = _show(repo, "HEAD:%s%s" % (src, name))
                if old is not None and not _stub_target(store, old):
                    befores["%s%s" % (src, name)] = old
                    after_of["%s%s" % (src, name)] = new or ""
                    break

    # A finished plan closed under a `Ruling:` at HEAD: G-A1 reads that from the base ledger and lets its boxes go.
    befores = {
        rel: text
        for rel, text in befores.items()
        if not gate.ruled_at_base(
            {"status": _status(gate, text), "ruling": gate.PF.ruling_line(text)}
        )
    }
    if not befores:
        return []

    # A byte-identical move into the archive is G-A2's legal home for a deleted plan.
    archived = {}
    for rel, text in news.items():
        if rel.startswith(gate.ARCHIVE_DIR + "/") and text is not None:
            archived[rel.rsplit("/", 1)[-1]] = text

    alive, alive_loose = set(), set()

    def _absorb(text):
        if not text or _stub_target(store, text):
            return
        o, d = gate.PF.plan_boxes(text)
        for t in list(o) + list(d):
            alive.add(gate.sig(t))
            alive_loose.add(gate.loose_sig(t))

    for text in news.values():
        _absorb(text)

    def _missing():
        out = []
        for rel, text in sorted(befores.items()):
            if news.get(rel) is None and archived.get(rel.rsplit("/", 1)[-1]) == text:
                continue
            open_t, _done = gate.PF.plan_boxes(text)
            for task in open_t:
                s = gate.sig(task)
                if s in alive or gate.loose_sig(task) in alive_loose:
                    continue
                out.append((rel, s))
        return out

    missing = _missing()
    if missing:
        # THE SECOND CHANCE over the rest of the corpus, as G-A1's `head_open` is corpus-wide: a box moved, unchanged, into a plan this commit does not touch still survives. Read at HEAD, which is what that plan holds after this commit.
        for text in _head_corpus(repo, set(news) | set(befores)).values():
            _absorb(text)
        missing = _missing()

    out = []
    for rel, s in missing:
        line = _box_line(gate, befores[rel], s)
        out.append(
            (
                rel,
                line,
                _nearest(gate, after_of.get(rel, ""), line, befores[rel]),
                notes.get(rel, ""),
            )
        )
    return out


def queue_problems(pq, fence_re, text):
    """Every structural problem of one QUEUE.md text, as a set of strings. EXPORTED for the suite."""
    if text is None:
        return set()
    problems = set()
    seen: dict[str, int] = {}
    fenced = False
    markers = (pq.GEN_BEGIN, pq.GEN_END, pq.INF_BEGIN, pq.INF_END)
    marks = dict.fromkeys(markers, 0)
    for line in text.splitlines():
        if fence_re.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        if re.match(r"^## \S", line):
            key = line.rstrip()
            seen[key] = seen.get(key, 0) + 1
        if line.strip() in marks:
            marks[line.strip()] += 1
    for heading, count in seen.items():
        if count > 1:
            problems.add("the heading `%s` appears %d times" % (heading, count))
    for marker, count in marks.items():
        if count > 1:
            problems.add("the marker `%s` appears %d times" % (marker, count))
    problems.update("RQ-SETTINGS: %s" % p for p in pq.settings(text)[1])
    return problems


# --------------------------------------------------------------------------- the event ---------------------------------------------------------------------------


EDGE_CASES = [
    # The incident's first shape: the evidence appended to the box text.
    ("a tick that rewrites the box text", "git commit -F m -- agent/plans/PLAN-rewrite.md"),
    ("the correct tick, evidence indented below", "git commit -F m -- agent/plans/PLAN-ticked.md"),
    (
        "a move into _done with bracket flips only",
        "git commit -F m -- agent/plans/PLAN-moved.md agent/plans/_done/PLAN-moved.md",
    ),
    (
        "a move into _done whose copy rewrites a box",
        "git commit -F m -- agent/plans/PLAN-movedbad.md agent/plans/_done/PLAN-movedbad.md",
    ),
    ("a plan deleted with an open box", "git commit -F m -- agent/plans/PLAN-deleted.md"),
    # The incident's second shape: the sliced QUEUE.md.
    ("a QUEUE.md with its sections duplicated", "git commit -F m -- agent/plans/QUEUE.md"),
    ("a commit touching no plan", "git commit -F m -- docs/x.md"),
    ("a directory pathspec reaches the rewritten plan", "git commit -F m -- agent/plans/"),
    ("prose naming a plan commit", "echo 'git commit -- agent/plans/PLAN-rewrite.md'"),
    ("git log is not a commit", "git log -- agent/plans/PLAN-rewrite.md"),
]


def _fixture(path):
    """A checkout whose working tree holds one instance of each shape, uncommitted. Each EDGE_CASE commits a different pathspec of it."""
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )

    def git(*args):
        subprocess.run(["git", *args], cwd=str(path), check=True, capture_output=True, env=env)

    def put(rel, text):
        p = path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    path.mkdir(parents=True)
    git("init", "--initial-branch=1008-1", "-q")
    for slug, body in FIXTURE_HEAD.items():
        put("agent/plans/PLAN-%s.md" % slug, body)
    put(QUEUE_REL, FIXTURE_QUEUE)
    put("docs/x.md", "seed\n")
    git("add", "-A")
    git("commit", "-q", "-m", "seed")
    for rel, text in FIXTURE_WORKTREE.items():
        if text is None:
            (path / rel).unlink()
        else:
            put(rel, text)
    put("m", "docs(plans): fixture\n")
    return path


def _plan(slug, boxes):
    return (
        "# PLAN: %s\n\nStatus: in-progress\nOwner: cafe0000\nDepends-On: no-dep -- a fixture\n\n"
        "## Tasks\n\n%s" % (slug, "".join("- [ ] %s\n" % b for b in boxes))
    )


def _stub(slug):
    return (
        "# PLAN: %s (moved)\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-%s.md\n\n"
        "This plan moved.\n" % (slug, slug)
    )


FIXTURE_HEAD = {
    "rewrite": _plan("rewrite", ["T16 Retarget writers:", "T17 Delete the rewrite env files"]),
    "ticked": _plan("ticked", ["T16 Retarget the ticked writers:", "T17 Delete ticked env files"]),
    "moved": _plan("moved", ["T1 Move the moved token file", "T2 Bind the moved devbox"]),
    "movedbad": _plan("movedbad", ["T1 Seed the movedbad store", "T2 Wire the movedbad fetcher"]),
    "deleted": _plan("deleted", ["T1 Keep the deleted plan's box"]),
}

FIXTURE_QUEUE = (
    "# Plan queue\n\nThe list below `## Generated` is rendered; the Promoted list is by hand.\n\n"
    "## Settings\n\n```stop-hook\nturbo: off\n```\n\n"
    "## In flight\n\n<!-- queue:inflight:begin -->\n- Mode: x\n<!-- queue:inflight:end -->\n\n"
    "## Promoted\n\n1. agent/plans/PLAN-rewrite.md\n\n"
    "## Generated\n\n<!-- queue:generated:begin -->\n1. agent/plans/PLAN-ticked.md\n"
    "<!-- queue:generated:end -->\n"
)


def _sliced_queue(text):
    """The incident's splice: a new `## Promoted` body written between that heading and the FIRST `## Generated`, which sits in prose above it, so the tail `text[end:]` starts before the head ends and `## Settings` / `## In flight` are written twice."""
    start = text.index("\n## Promoted") + 1
    end = text.index("## Generated")
    return text[:start] + "## Promoted\n\n1. agent/plans/PLAN-ticked.md\n\n" + text[end:]


FIXTURE_WORKTREE = {
    "agent/plans/PLAN-rewrite.md": FIXTURE_HEAD["rewrite"].replace(
        "- [ ] T16 Retarget writers:",
        "- [x] T16 Retarget writers: (done 2026-10-08: c2ca68dfe with private/account 65b2332)",
    ),
    "agent/plans/PLAN-ticked.md": FIXTURE_HEAD["ticked"].replace(
        "- [ ] T16 Retarget the ticked writers:\n",
        "- [x] T16 Retarget the ticked writers:\n"
        "    (ticked) 2026-10-08 by d778be9d: c2ca68dfe with private/account 65b2332\n",
    ),
    "agent/plans/PLAN-moved.md": _stub("moved"),
    "agent/plans/_done/PLAN-moved.md": FIXTURE_HEAD["moved"].replace("[ ]", "[x]"),
    "agent/plans/PLAN-movedbad.md": _stub("movedbad"),
    "agent/plans/_done/PLAN-movedbad.md": FIXTURE_HEAD["movedbad"]
    .replace("[ ]", "[x]")
    .replace("store", "store (done 2026-10-08: c2ca68dfe)"),
    "agent/plans/PLAN-deleted.md": None,
    QUEUE_REL: _sliced_queue(FIXTURE_QUEUE),
}

FIXTURES = {"plan-box-commits": _fixture}

ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("plan-box-commits", {"CLAUDE_PROJECT_DIR": "{FIXTURE:plan-box-commits}"}, {})
]


def _reader(repo, from_index):
    def read(rel):
        if from_index:
            return _show(repo, ":%s" % rel)
        try:
            return (pathlib.Path(repo) / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    return read


def _message(lost, queue_new):
    out = [
        "BLOCKED: this commit would leave `check:ci-plan-boxes` or `check:ci-plan-record` red.\n"
    ]
    if lost:
        out.append(
            "\n%d box(es) open at HEAD have no home in what this commit writes:\n" % len(lost)
        )
        for rel, head_line, new_line, note in lost[:12]:
            out.append("\n  %s\n" % rel)
            out.append("    at HEAD: %s\n" % (head_line.strip() or "(line not found)"))
            out.append(
                "    now:     %s\n"
                % (new_line.strip() if new_line else "(no box line resembles it: deleted?)")
            )
            if note:
                out.append("    note:    %s\n" % note)
        if len(lost) > 12:
            out.append("\n  ... and %d more\n" % (len(lost) - 12))
        out.append(REMEDY)
    if queue_new:
        out.append("\n%s gains %d structural problem(s):\n" % (QUEUE_REL, len(queue_new)))
        out.extend("  - %s\n" % p for p in sorted(queue_new))
        out.append(QUEUE_REMEDY)
    return "".join(out)


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null"):
        return hookio.ALLOW
    commits = commit_policy.git_runs(cmd, "commit")
    if not commits:
        return hookio.ALLOW
    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    base = ev.field("cwd") or root
    lost, queue_new = [], set()
    try:
        created = commit_policy.created_dirs(cmd, base)
        for commit in commits:
            repo = commit_policy.run_repo(commit, base, created)
            if not repo or not commit_policy.is_inside(repo, root):
                continue
            paths = commit_policy.judged_paths(commit, cmd, repo, base)
            plan_paths = [p for p in paths if PLAN_RX.match(p)]
            if not plan_paths and QUEUE_REL not in paths:
                continue
            gate, pq, store = _load_gate()
            flags = commit_policy.commit_flags(commit)
            named = bool(commit_policy.commit_paths(cmd, run=commit))
            read = _reader(repo, not (named or "-a" in flags or "--all" in flags))
            if plan_paths:
                lost.extend(lost_boxes(gate, store, repo, plan_paths, read))
            if QUEUE_REL in paths:
                fence = gate.PFID.FENCE_RE
                queue_new |= queue_problems(pq, fence, read(QUEUE_REL)) - queue_problems(
                    pq, fence, _show(repo, "HEAD:%s" % QUEUE_REL)
                )
    except (ImportError, OSError, RuntimeError, ValueError, AttributeError) as exc:
        ev.warn(UNEXAMINED % exc)
        return hookio.ALLOW
    if lost or queue_new:
        ev.warn_raw(_message(lost, queue_new))
        return hookio.DENY
    return hookio.ALLOW
