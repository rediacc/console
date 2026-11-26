"""wl_core: shared primitives for the worklist Stop hook.

Stdlib-only, no sibling imports, no I/O beyond what each helper documents. Everything here is used by at least two sibling modules; single-consumer logic lives with its consumer. WHY comments for each check stay with the check, not here.
"""

import contextlib
import datetime
import glob
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

import wl_common

# `- [ ] (5546d4bb) do the thing` -> state " ", owner "5546d4bb" Owner accepts any word-ish label, not just hex: a named agent tagged items "(perf6-daemon)", the old hex-only charset failed to parse it, the item read as UNTAGGED, and untagged defaults to mine -- so every OTHER session was blocked on that agent's work. Non-prefix labels now parse as owners and are
# reported-never-blocking for everyone (including the labeler: only a tag that is a PREFIX of your session id binds you).
ITEM = re.compile(
    r"^\s*-\s*\[(?P<state>[ x?>])\]\s*(?:\((?P<owner>[A-Za-z0-9][A-Za-z0-9._-]*)\)\s*)?"
)
# Same shape but INCLUDING tombstones, for the md-sync pass which must see a `[~]` flip as a deletion rather than as an unparseable line.
ITEM_ANY = re.compile(
    r"^\s*-\s*\[(?P<state>[ x?>~])\]\s*(?:\((?P<owner>[A-Za-z0-9][A-Za-z0-9._-]*)\)\s*)?"
)
LEASE = re.compile(r"until:(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)Z")
# worker:<background-task-id> on a lease line names the OS-checkable delegate.
WORKER = re.compile(r"worker:([A-Za-z0-9._-]{1,40})")
DEFAULT_TOKEN = re.compile(r"\bDEFAULT:[ \t]*\S")
# v12 justification tokens (operator, 2026-07-30: "Too many '[?]'. This is an escape hatch... there should be a field in json like 'why' and possibly many"). A deferral now carries WHY (why THIS session cannot settle it right now) and HOW (the concrete action or evidence that would resolve it), plus optional TRIED / NEEDS / BLOCKED_ON. They live as inline tokens in the item text
# (so the markdown inbox round-trips them) AND as a real `j` field on the store event (so nothing downstream re-parses prose it wrote itself).
JUST_TOKEN = re.compile(r"\b(WHY|HOW|TRIED|NEEDS|BLOCKED_ON|DEFAULT):")
# WHY values that describe avoidance rather than inability. Deliberately a SHORT list of unambiguous shapes: this regex is the cheap gate at creation time; whether a why that passes it is actually TRUE is the judge's question.
VAGUE_WHY_RE = re.compile(
    r"\b(did ?not get (to|around)|didn'?t get (to|around)|no time|not yet"
    r"|too busy|later|low priority|will (do|get to)|have?n'?t (had|gotten"
    r"|got around))\b",
    re.IGNORECASE,
)
# Same charset the worklist owner tag accepts.
PREFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")

# Leases beyond this horizon are invalid: a `- [>]` marked "until next year" would be a bypass, not a delegation. 120 also aligns the lease horizon with the top rung of the v10 liveness ladder.
MAX_LEASE_MIN = 120


def parse_justification(text):
    """{field: value} for every WHY:/HOW:/TRIED:/NEEDS:/BLOCKED_ON: token in a
    deferral's text, keys lowercased. A value runs to the next known token (DEFAULT: included, so the tokens compose in any order) or to the end of the line. Empty values are absent, so `bool(j.get("why"))` is the whole presence test."""
    out = {}
    matches = list(JUST_TOKEN.finditer(text or ""))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        key = m.group(1)
        if key == "DEFAULT":
            continue
        val = text[m.end() : end].strip()
        if val:
            out[key.lower()] = val
    return out


def utcnow():
    return datetime.datetime.now(datetime.UTC)


def stamp_now():
    return utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp_ahead(minutes):
    """An ISO8601Z stamp `minutes` from now. Used where a message promises a bound (the background check-in's next-earliest time): a claimed latch a reader cannot check from the message alone is not a latch, it is a slogan."""
    return (utcnow() + datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_stamp(stamp):
    """datetime or None from an ISO8601Z stamp (seconds optional)."""
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%MZ"):
        try:
            return datetime.datetime.strptime(stamp, fmt).replace(tzinfo=datetime.UTC)
        except (TypeError, ValueError):
            continue
    return None


# A deferral whose DEFAULT cannot run before a given instant (a release-age window, a scheduled date) says so with `NOT-BEFORE:<ISO8601Z>`; its autonomy window does not close before then.
NOT_BEFORE = re.compile(r"\bNOT-BEFORE:[ \t]*(\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?Z)")


# A hold is time-boxed too: an instant further than this past the item's last update is ignored, so a mistyped year cannot park a DEFAULT for good.
NOT_BEFORE_MAX_DAYS = 7


def not_before_pending(line, upd=""):
    """True while the line's latest NOT-BEFORE: instant is in the future and within NOT_BEFORE_MAX_DAYS of `upd` (the item's last update stamp, or now when absent)."""
    stamps = NOT_BEFORE.findall(line or "")
    when = parse_stamp(stamps[-1]) if stamps else None
    if when is None:
        return False
    base = parse_stamp(upd) or utcnow()
    return utcnow() < when <= base + datetime.timedelta(days=NOT_BEFORE_MAX_DAYS)


def not_before_problem(line, upd=""):
    """Why the line's latest NOT-BEFORE: token holds nothing (an impossible date, or beyond the cap), or "" when it holds or is absent or already passed."""
    stamps = NOT_BEFORE.findall(line or "")
    if not stamps:
        return ""
    when = parse_stamp(stamps[-1])
    if when is None:
        return "NOT-BEFORE:%s is not a valid instant" % stamps[-1]
    if when <= utcnow():
        return ""
    base = parse_stamp(upd) or utcnow()
    if when > base + datetime.timedelta(days=NOT_BEFORE_MAX_DAYS):
        return "NOT-BEFORE:%s is more than %d days out and is ignored" % (
            stamps[-1],
            NOT_BEFORE_MAX_DAYS,
        )
    return ""


def stamp_age_min(stamp):
    when = parse_stamp(stamp)
    if when is None:
        return None
    return (utcnow() - when).total_seconds() / 60.0


def lease_state(line):
    """'fresh' | 'expired' | 'invalid' for a `- [>]` line's until: token."""
    m = LEASE.search(line)
    if not m:
        return "invalid"
    stamp = m.group(1)
    fmt = "%Y-%m-%dT%H:%M:%S" if stamp.count(":") == 2 else "%Y-%m-%dT%H:%M"
    try:
        until = datetime.datetime.strptime(stamp, fmt).replace(tzinfo=datetime.UTC)
    except ValueError:
        return "invalid"
    now = utcnow()
    if until <= now:
        return "expired"
    if until > now + datetime.timedelta(minutes=MAX_LEASE_MIN):
        return "invalid"
    return "fresh"


def lease_remaining_tag(line):
    """`, 59m left` for a fresh lease, `` for anything else.

    A DEADLINE THAT IS ONLY ABSOLUTE IS AMBIGUOUS TO A READER IN A DIFFERENT DAY. UTC and a +0200 local clock disagree about the DATE for two hours out of every twenty-four, and during that window an `until:2026-09-08T23:36Z` reads as yesterday to anyone whose own clock says the 9th. That happened on 2026-09-08 and cost a round trip: the lease had 59 minutes left and was reported
    as expired.

    Relative time has no timezone, so it cannot be misread. Absolute stays too, because it is the form the store round-trips.
    """
    m = LEASE.search(line or "")
    if not m or lease_state(line) != "fresh":
        return ""
    stamp = m.group(1)
    fmt = "%Y-%m-%dT%H:%M:%S" if stamp.count(":") == 2 else "%Y-%m-%dT%H:%M"
    try:
        until = datetime.datetime.strptime(stamp, fmt).replace(tzinfo=datetime.UTC)
    except ValueError:
        return ""
    return ", %dm left" % max(0, round((until - utcnow()).total_seconds() / 60))


# LINEAGE ALIASES: the ids a compaction gave to ONE conversation.
#
# A compaction can hand a continuous session a new id, and the ownership rule -- correctly -- then refuses to let it resolve its own items. On 2026-09-02 that left four settled decisions open all night, reported to the operator as a peer's, while the session reasoned about a peer that did not exist.
#
# _LINEAGE maps a BOUND id to the set of ids proven to be the same conversation. It is keyed on the bound id rather than held as a bare set for one reason: a peer session loading this module must never pick up my aliases. `bind_lineage` is called once, with the identity this process actually resolved to. The bound id is held under a reserved key INSIDE the mapping rather than in a
# separate module global: one object, one write, and no `global` statement for a linter to object to. The key cannot collide with a session id because a session id never contains a space.
_BOUND_KEY = "bound id"
_LINEAGE = {}


def bind_lineage(session_id, aliases):
    """Declare that `session_id` is also known by `aliases` (proven, not guessed).

    Called once per process from the store load, after the `lineage` events have been folded and the chain resolved transitively.
    """
    if not session_id:
        return
    _LINEAGE[_BOUND_KEY] = session_id
    _LINEAGE[session_id] = set(aliases or ())


def lineage_of(session_id):
    """The proven aliases of `session_id`, or an empty set.

    Returns nothing for an id that is not the bound one, which is what keeps a peer from inheriting this process's adoptions.
    """
    bound = _LINEAGE.get(_BOUND_KEY)
    if not session_id or bound is None:
        return set()
    if not same_session(session_id, bound):
        return set()
    return _LINEAGE.get(bound, set())


def owned_by_me(owner, session_id):
    """An UNTAGGED item counts as this session's: that is the safe default, since the cost of wrongly claiming one is doing a little extra work, while the cost of wrongly disowning one is silently dropping it. A tag is a PREFIX of the session id (CLAUDE.md asks for a short prefix, not the whole uuid).

    An ANCESTOR's tag is also mine, but only when a `lineage` event has proven the two ids are one conversation (see wl_lineage.py, which requires a compaction boundary AND shared conversational record uuids). This is the single chokepoint
    for 25 call sites, so the compaction fix cannot roll out half-applied.
    """
    if owner is None:
        return True
    if not session_id:
        return False
    if session_id.startswith(owner):
        return True
    return any(alias.startswith(owner) for alias in lineage_of(session_id))


def same_session(a, b):
    """Two prefixes/ids denote one session when either is a prefix of the other. Symmetric, because CLI callers pass short prefixes while the Stop event carries the full id, and either side of a comparison can be either.

    DELIBERATELY NOT LINEAGE-AWARE, and that is not an oversight. Its callers compare PEERS -- the brief roster, the dead-session sweep, phantom detection -- and a predecessor is genuinely gone for every one of those purposes. Widening this would silently change all of them; the ancestor branch belongs in `owned_by_me`, which is about who may RESOLVE an item.
    """
    return bool(a) and bool(b) and (a.startswith(b) or b.startswith(a))


# A `<me>` must be at least this long, for a reason that applies everywhere: a short prefix names a DIFFERENT sidecar than the Stop hook derives from the full session id, so it half-works instead of failing. It also closes the hole `same_session`'s symmetry would leave open -- `--add d` would
# otherwise be accepted by every session whose id starts with "d".
ME_MIN_LEN = 8


def resolve_session_id():
    """This process's TRUE session id, or "" when the environment cannot say.

    ONE definition, deliberately: two answers to "who am I" is how the drift this function exists to catch starts again.

    WORKLIST_SESSION_ID first, and it is an identity ASSERTION rather than a suppression flag -- the test suite declares its fixture id with it, and an operator acting for a dead session declares that session's id. A boolean bypass was rejected: it would suppress the check without stating a claim, which is the exact shape docs/agent-reference/suppressions.md exists to prevent, and
    it would be reachable by a session trying to get past its own mistake.

    CLAUDE_CODE_SESSION_ID, not CLAUDE_SESSION_ID. The latter DOES NOT EXIST;
    the name was verified against a live Bash-tool child's environment rather than guessed, and a wrong name here resolves to "" forever, which every caller treats as pass -- a check that cannot fire, wearing the costume of one that works. The harness injects it per child spawn and rotates it on /clear, so it is "current id", not "id at startup", and it is platform-neutral (no
    /proc, no filesystem assumption). Sub-agents inherit the PARENT's value, which is why a sub-agent tagging items with the parent prefix is correct and this check does not fire on the sub-agent fleet.

    Returns "" rather than raising. "" means CANNOT VERIFY, and the honest response to that is to say nothing, not to accuse.
    """
    return str(
        os.environ.get("WORKLIST_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    ).strip()


def check_me(me):
    """(ok, message) for a `<me>` argument: is this session really that one?

    THE DEFECT THIS CLOSES, in one paragraph because the fix is only obvious once you have seen it. Every `<me>` in this CLI was accepted on SHAPE alone (PREFIX_RE), and nothing had ever compared one to reality. A session copied a SUB-AGENT's namespace token out of a Task-spawn tool result (`agent_id: search-renet2@session-4c3e095a`) and used it as its own `<me>`
    for 26 hours: 219 calls under the wrong identity and 20 under the right one,
    from the same process. Every individual operation SUCCEEDED, because writes
    and reads key off the same unvalidated string -- so one typo splits a session into two half-sessions, each internally consistent, and nothing downstream can tell. The cost was work sitting unseen in the other half for 34 hours.

    ASYMMETRIC on purpose: `sid.startswith(me)`, not `same_session(me, sid)`. On the CLI `me` is always a claim about SELF, never a peer id, so the symmetry that makes same_session right for peer comparisons is exactly what
    would let a one-character `me` through here. same_session is NOT changed;
    its other callers compare peers, where symmetry is correct.

    REFUSES rather than warns (operator decision). A warning beside a successful command is what the failing session skimmed past for a day: shape-only validation passing silently is what let this through in the first place, and a warning would be read past the same way. A non-zero exit costs one turn and the message carries the copy-paste fix.
    """
    me = me or ""
    sid = resolve_session_id()
    if not sid:
        # UNVERIFIABLE, so silent. A plain operator terminal has no session id and must not be accused of impersonating one.
        return True, ""
    if len(me) < ME_MIN_LEN and os.environ.get("WORKLIST_SESSION_ID") != me:
        # The floor is skipped ONLY on an exact declared match, and that exception is a bug fix, not a loophole. Legacy sub-agents tagged items
        # with their NAME (`w2s-en`, 6 chars), and those items still need
        # reading and reassigning. Without this, `WORKLIST_SESSION_ID=w2s-en
        # --list --open w2s-en` was REFUSED and then advised to "rerun with
        # <me>=w2s-en" -- the value it had just rejected. An instruction that
        # tells you to retry the thing it refused leaves no next move at all, and it made two real items unreadable.
        #
        # Safe because the floor guards against an UNDER-SPECIFIED guess about self, and an exact match to an explicit declaration is not a guess. A bare short `me` with no declaration is still refused, which is the
        # case the floor was built for.
        return False, _identity_msg(
            me,
            sid,
            "it is shorter than %d characters, so it does not identify one session" % ME_MIN_LEN,
        )
    if not sid.startswith(me):
        return False, _identity_msg(me, sid, "this session is %s" % sid)
    return True, ""


def _identity_msg(me, sid, why):
    """The refusal text. Names the variable it read, because the next session to hit this needs the mechanism to be inspectable, not just the verdict."""
    src = (
        "WORKLIST_SESSION_ID" if os.environ.get("WORKLIST_SESSION_ID") else "CLAUDE_CODE_SESSION_ID"
    )
    return (
        "identity mismatch: you passed <me>=%s but %s (%s).\n"
        "Writing as one identity and reading as another splits your items in "
        "two and neither half is complete: every call succeeds, the halves stay "
        "internally consistent, and items wait in the one you are not reading.\n"
        "  rerun with <me>=%s\n"
        "If you really mean to act as another session, declare it rather than "
        "assert it by hand:\n"
        "  WORKLIST_SESSION_ID=<that session's id> worklist.py ..."
        % (me, why, src, sid[:ME_MIN_LEN])
    )


def project_root(start):
    """Nearest ancestor holding .git. This repo uses worktrees, where .git is a FILE, not a directory, so test existence rather than is_dir().

    Resolves from WHEREVER IT IS POINTED, deliberately. It cannot tell a repo
    from a repo nested inside one, and it must not try -- see project_start(),
    which is what every caller should be pointing it at.

    Two redirects: a lease tree answers with the checkout that holds it (lease_main), and the landing tree answers with the main checkout (landing_main), so both trees of agent/plans/PLAN-two-track-merge-dev.md share one worklist store, one STATE.md and one set of TMPDIR sidecars.
    """
    tree = checkout_root(start)
    return landing_main(tree) or tree


def checkout_root(start):
    """project_root WITHOUT the landing redirect: the checkout a session works in (a lease still answers with its holder). A read of the session's own HEAD (its branch) starts here, since project_root of the landing tree is the main checkout, whose HEAD is the development branch."""
    p = pathlib.Path(start).resolve()
    for candidate in [p, *p.parents]:
        if (candidate / ".git").exists():
            return lease_main(candidate) or candidate
    return p


def _git_dirs(tree):
    """(git dir, common dir) of a checkout, read from its files, or None. A hot path, so no subprocess."""
    dotgit = tree / ".git"
    try:
        if dotgit.is_dir():
            git_dir = dotgit.resolve()
        else:
            text = dotgit.read_text(encoding="utf-8").strip()
            if not text.startswith("gitdir:"):
                return None
            git_dir = (tree / text[len("gitdir:") :].strip()).resolve()
        commondir = git_dir / "commondir"
        if not commondir.is_file():
            return git_dir, git_dir
        return git_dir, (git_dir / commondir.read_text(encoding="utf-8").strip()).resolve()
    except (OSError, ValueError, RuntimeError):
        return None


def lease_main(tree):
    """The checkout holding `tree` when `tree` is its lease, `<main>/.claude/worktrees/<id>`, else None (agent/plans/PLAN-worktree-lease.md Design 4).

    A lease has one store, the main checkout's. The rule needs position AND git's word: a linked tree's git dir is `<common>/worktrees/<id>` with a `commondir` file, and `<main>` shares that common dir. A `.git` file into `modules/` has no `commondir`, an operator's `.worktrees/<MMDD-N>` is not under `.claude`, and both keep their own root. The admin directory's name is compared rather than a literal so worklist.py's twin stays identical to this.
    """
    tree = pathlib.Path(tree)
    if tree.parent.parent.name != ".claude" or not (tree / ".git").is_file():
        return None
    mine = _git_dirs(tree)
    if mine is None or mine[0] == mine[1] or mine[0].parent.parent != mine[1]:
        return None
    if mine[0].parent.name != tree.parent.name:
        return None
    main = tree.parents[2]
    theirs = _git_dirs(main) if (main / ".git").exists() else None
    return main if theirs is not None and theirs[1] == mine[1] else None


# The landing record (agent/plans/PLAN-two-track-merge-dev.md, box LT1): one JSON object {"path": <realpath>, "branch": <MMDD-N>} in the COMMON git dir, so every tree of the repository reads the same file. commit_policy.py writes and validates it. This module looks for the file without a subprocess, because project_root is a hot path, and validates an existing one through commit_policy once per record version (read_landing_record).
LANDING_RECORD_NAME = "rediacc-landing.json"
# The git config key naming a common dir's main checkout, `core.<this>`. worklist.py's twin assembles the same string from two halves.
CORE_TREE_KEY = "worktree"


def _common_main(common):
    """The main checkout of common git dir `common`, or None: core.worktree when the dir sets one (a submodule's `.git/modules/<name>`), else the parent of a dir named `.git`. Confirmed against git's own answer by sharing the common dir."""
    main = None
    try:
        text = (common / "config").read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            section = line.strip("[]").strip().lower()
            continue
        key, sep, value = line.partition("=")
        if section == "core" and sep and key.strip().lower() == CORE_TREE_KEY:
            main = (common / value.strip()).resolve()
    if main is None and common.name == ".git":
        main = common.parent
    if main is None or not (main / ".git").exists():
        return None
    theirs = _git_dirs(main)
    return main if theirs is not None and theirs[0] == theirs[1] == common else None


# One validation per record version per process: commit_policy's reader asks git (the common dir, the linked-tree check), and project_root is a hot path, so its answer is kept keyed on the record file's (path, mtime_ns, size). A rewrite of the record changes the key.
_LANDING_READS: dict[tuple[str, str, int, int, int, int, int, int], tuple[dict | None, str]] = {}


def _commit_policy():
    """commit_policy from `.claude/rediacc_hooks`, through the canonical sys.path hop loaded by file (this module lives outside that package)."""
    import importlib.util

    helper = pathlib.Path(__file__).resolve().parents[2] / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("_rediacc_syspath", helper)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % helper)
    syspath = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(syspath)
    syspath.on_sys_path(syspath.CLAUDE_DIR)
    from rediacc_hooks import commit_policy

    return commit_policy


def read_landing_record(tree):
    """`(record, problem)` for `tree`'s repository: the validated `{"path", "branch"}` and "", `(None, "")` when there is no record, or `(None, <defect>)` when one exists and binds nothing.

    The validation is commit_policy.read_landing_record's, the one validator, so a record every guard refuses binds nothing here either. Only an existing record is validated (a missing one costs no subprocess), and its answer is kept per record version.
    """
    dirs = _git_dirs(pathlib.Path(tree))
    if dirs is None:
        return None, ""
    where = dirs[1] / LANDING_RECORD_NAME
    try:
        st = os.lstat(where)
    except FileNotFoundError:
        return None, ""
    except OSError as exc:
        return None, "%s cannot be read: %s: %s" % (where, type(exc).__name__, exc)
    # The tree is part of the key (read_landing_record validates against it) and so are the inode and ctime: a same-size rewrite inside the mtime granularity replaces the inode or moves ctime. The verdict also reads the tree's `.git` entry, whose version joins the key, so a tree re-pointed within one process is read again (review 1cd88702.4).
    try:
        dot = os.lstat(os.path.join(str(tree), ".git"))
        dot_key = (dot.st_mtime_ns, dot.st_size)
    except OSError:
        dot_key = (0, 0)
    key = (str(tree), str(where), st.st_mtime_ns, st.st_ctime_ns, st.st_ino, st.st_size, *dot_key)
    if key not in _LANDING_READS:
        try:
            policy = _commit_policy()
        except Exception as exc:
            return (
                None,
                "commit_policy, the landing record's validator, could not be loaded (%s: %s)"
                % (type(exc).__name__, exc),
            )
        _LANDING_READS[key] = policy.read_landing_record(str(tree))
    return _LANDING_READS[key]


def landing_record(tree):
    """The landing record of `tree`'s repository as {"path", "branch"}, or None when there is none or it binds nothing.

    The callers of this form only route (project_root's landing redirect, projects_dirs, wl_worktrees' lease sweep), so a defect reads as no record here and nothing is said: the stop names it once, in the `landing-stack` advisory, where wl_stack.stack_state reads the same validator's problem. A caller that speaks takes read_landing_record and names the problem itself.
    """
    return read_landing_record(tree)[0]


def landing_main(tree):
    """The main checkout when `tree` is the landing tree its repository's landing record binds, else None (agent/plans/PLAN-two-track-merge-dev.md, box LT14).

    The rule needs git's word as lease_main's does: `tree` is a linked worktree (its git dir is `<common>/worktrees/<id>`), its realpath equals the record's path, and the main checkout shares that common dir. With no record every tree keeps its own root.
    """
    tree = pathlib.Path(tree)
    if not (tree / ".git").is_file():
        return None
    mine = _git_dirs(tree)
    if mine is None or mine[0] == mine[1] or mine[0].parent.parent != mine[1]:
        return None
    rec = landing_record(tree)
    if rec is None or os.path.realpath(str(tree)) != os.path.realpath(rec["path"]):
        return None
    return _common_main(mine[1])


def _munged(path):
    """Claude Code's project-directory naming: every non-alphanumeric character of the absolute path becomes a `-`."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def projects_dirs(root, base=None):
    """Every directory holding this repo's session transcripts: the main checkout's, then the landing tree's when a landing record binds one (a landing session writes under its own tree's name).

    With `base` None this is projects_dir's answer as a list: $WORKLIST_PROJECTS_DIR alone when set, else the directories under ~/.claude/projects that exist. With `base` given (the subagent scans' `<config dir>/projects`), the candidate Paths under it, existing or not, since those callers test is_dir themselves.
    """
    if base is None:
        env = os.environ.get("WORKLIST_PROJECTS_DIR")
        if env:
            return [env]
    try:
        main = pathlib.Path(root).resolve()
    except (OSError, RuntimeError):
        return []
    trees = [main]
    rec = landing_record(main)
    if rec is not None and pathlib.Path(rec["path"]) != main:
        trees.append(pathlib.Path(rec["path"]))
    if base is not None:
        return [pathlib.Path(base) / _munged(t) for t in trees]
    home = pathlib.Path.home() / ".claude" / "projects"
    return [str(home / _munged(t)) for t in trees if (home / _munged(t)).is_dir()]


def projects_dir(root):
    """Where this repo's session TRANSCRIPTS live, or "" when nothing says.

    ONE definition, for the same reason resolve_session_id is one definition. The Stop hook has always derived this from the event's transcript_path (exact, and it keeps preferring that), but the CLI write path has no event to derive it from and still has to answer "is this section's owner alive?". Two answers to that question is how the drift starts.

    The convention, verified on this machine rather than assumed: the harness writes ~/.claude/projects/<abs-repo-path-with-/-as->/<session-uuid>.jsonl, e.g. /home/muhammed/.claude/projects/-home-muhammed-monorepo-console/.

    Returns "" rather than guessing when the directory is absent: "" means CANNOT SAY, and owner_age_hours already treats that as "unknown owner", which is the conservative direction (unknown never reads as dead by transcript, only by its own section stamp).

    The main checkout's directory only: projects_dirs answers the landing tree's beside it. The name is the harness's own munging (_munged, every non-alphanumeric character a `-`); the earlier `/`-only replace named a directory the harness never writes for a path holding `.` or `_`.
    """
    env = os.environ.get("WORKLIST_PROJECTS_DIR")
    if env:
        return env
    try:
        cand = pathlib.Path.home() / ".claude" / "projects" / _munged(pathlib.Path(root).resolve())
    except (OSError, RuntimeError):
        return ""
    return str(cand) if cand.is_dir() else ""


# <repo>/.claude/hooks/stop/wl_core.py -> parents[3] is <repo>.
_HOOK_ROOT_DEPTH = 3


def hook_repo_root():
    """The repo this hook FILE lives in, or None if it does not look like one.

    Immune to cwd by construction, which is the whole point: settings.json invokes every hook as "$CLAUDE_PROJECT_DIR/.claude/hooks/...", so this answers the same thing the env var does at hook time, and keeps answering it when a human runs the CLI from a subdirectory with no env var set.
    """
    try:
        cand = pathlib.Path(__file__).resolve().parents[_HOOK_ROOT_DEPTH]
    except (IndexError, OSError):
        return None
    if (cand / ".git").exists() and (cand / ".claude" / "hooks" / "stop").is_dir():
        return cand
    return None


def project_start(event=None):
    """Where root resolution STARTS. cwd is the LAST resort, never the first.

    WHY THIS EXISTS, measured 2026-08-06. The Stop event's cwd is wherever the session last worked, and this tree has repos INSIDE the repo: submodules (private/renet) and gitignored non-submodule siblings (private/growth). Resolving from cwd walked project_root() straight into one of those and read ITS branch -- a session on 0804-1 was told to bootstrap `agent/main/` because
    private/growth happened to be on main. Confirmed twice, on both kinds of nested repo, so it is not a submodule quirk.

    The ladder, and the reason for each rung:

    1. CLAUDE_PROJECT_DIR. Guaranteed present for hooks -- .claude/settings.json
       spells every hook command "$CLAUDE_PROJECT_DIR/.claude/hooks/...", so an
       unset var would make every hook fail to launch, not merely misresolve.
       It is also how both test suites pin a fixture root, which is why it must
       stay ABOVE the file-derived rung.
    2. This hook file's own repo. Covers the CLI case: a shell has no
       CLAUDE_PROJECT_DIR (verified: unset in this session's Bash), so `cd
       private/growth && ../../.claude/hooks/stop/worklist.py --list` used to
       read a DIFFERENT store than the same command one directory up.
    3. The event's cwd, then getcwd(). Kept only as a floor for a copy of these
       hooks living somewhere that is not a repo.

    THE FIX THAT LOOKS RIGHT AND IS NOT: teaching project_root() to skip a `.git` file pointing into `/modules/`. This repo is ITSELF a submodule (`gitdir: ../.git/modules/console`), so that walks PAST console, changes the store slug from home_muhammed_monorepo_console to home_muhammed_monorepo, and orphans every open item in one step. Tried and reverted. Anchoring the START is the
    fix; the WALK is fine as it is.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return env
    hook_root = hook_repo_root()
    if hook_root is not None:
        return str(hook_root)
    if event:
        cwd = event.get("cwd")
        if cwd:
            return cwd
    return os.getcwd()


def worklist_for(start):
    # TMPDIR first, then tempfile's search. NOT a bare gettempdir(): on POSIX that also honours TEMP and TMP, so a machine with TEMP set and TMPDIR unset would resolve a DIFFERENT worklist path than the old expression did and silently orphan every live session's open items. This spelling is byte-identical to `os.environ.get("TMPDIR", "/tmp")` wherever TMPDIR is set or
    # absent-with-/tmp-present (verified on this machine), and it is what gives Windows -- which sets TEMP/TMP and never TMPDIR -- a real temp dir instead of a literal "/tmp" it cannot create.
    d = pathlib.Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "claude-worklist"
    d.mkdir(parents=True, exist_ok=True)
    root = project_root(start)
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(root)).strip("_")
    return d / (slug + ".md")


def emit(obj):
    print(json.dumps(obj))
    sys.exit(0)


def commit_only_env(args):
    """The environment for a git call, with lazy fetch OFF when the call reads only commits.

    CI's quality-branch job checks out with `filter: blob:none`, which keeps every REACHABLE commit and fetches blobs lazily. A commit-only query (`merge-base`, `rev-parse --verify <x>^{commit}`) on a sha that is not in the clone is therefore asking about an orphaned commit, and the answer is already "not here, not an ancestor". With lazy fetch on, git asks GitHub for the object instead, one
    round trip per sha: 112 such fetches from `merge-base --is-ancestor` took check:ci-plan-implementation from 22 s to 278 s in a blob-less clone (measured 2026-10-03, GIT_TRACE2), and twice pushed Quality / Branch over its 12-minute watchdog budget. `GIT_NO_LAZY_FETCH` (git 2.44+) makes the missing commit an instant no. Blob reads (`show`, `cat-file blob`, `log --follow`) keep fetching.
    """
    if args and (
        args[0] == "merge-base"
        or (args[0] == "rev-parse" and any(str(a).endswith("^{commit}") for a in args))
    ):
        env = dict(os.environ)
        env["GIT_NO_LAZY_FETCH"] = "1"
        return env
    return None


def _git(root, *args):
    got = git_run(root, args, timeout=20)
    if got is None:
        return ""
    rc, out = got
    return git_text(out).strip() if rc == 0 else ""


# ---- GIT ANSWERS KEYED ON HEAD (agent/plans/PLAN-tooling-speed.md D2) ---------
#
# A Stop run started 15-25 git processes for answers that change only when HEAD, a ref, the index or the config moves. git_run answers a READ-ONLY query (git_cacheable) from a cache keyed on that state, read from the git directory's own files without a process: the HEAD text, the sha its branch ref names, the mtime and size of the index, packed-refs,
# FETCH_HEAD and the config files, the mtime of every directory under refs/ (a ref update is a lock-file rename, which moves its directory's mtime) and any rebase, merge or cherry-pick in progress. The answers persist across processes in `<git-dir>/rediacc-gitcache.json`, written once at exit, so a second stop on an unchanged HEAD starts no git process for them. A
# working-tree query (status, diff without --cached, ls-files) is never cached, nor one whose answer moves with the clock (--since, relative dates). A miss runs git once. A GIT_* variable that changes which repository git reads (_GIT_REPO_ENV), or WORKLIST_READ_MEMO=off, turns the cache off; the GIT_CONFIG* variables join the key.
GIT_CACHE_NAME = "rediacc-gitcache.json"
GIT_CACHE_STATS = {"hit": 0, "miss": 0}
GIT_CACHE_MAX_ANSWERS = 512
GIT_CACHE_MAX_ANSWER_BYTES = 1 << 20
_GIT_CACHEABLE = frozenset(
    {
        "rev-parse",
        "symbolic-ref",
        "log",
        "rev-list",
        "merge-base",
        "show",
        "cat-file",
        "for-each-ref",
        "describe",
        "ls-tree",
        "name-rev",
        "config",
    }
)
_GIT_REFLOG_ARGS = frozenset({"-g", "--walk-reflogs", "reflog"})
_GIT_CLOCK_WORDS = (
    "--since",
    "--until",
    "--after",
    "--before",
    "relative",
    "ago",
    "now",
    "%cr",
    "%ar",
    "%gr",
)
# The environment variables that change WHICH repository, index, objects or refs git reads; any of them set turns the cache off. GIT_EDITOR, GIT_PAGER and the like change nothing git answers, and are ignored.
_GIT_REPO_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
    "GIT_REPLACE_REF_BASE",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_GRAFT_FILE",
    "GIT_SHALLOW_FILE",
    "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
)
_GIT_DIRS: dict[str, tuple | None] = {}
_GIT_CACHE: dict[str, dict] = {}
_GIT_ATEXIT = {"on": False}


def git_text(out):
    """Text of git stdout bytes, as `text=True` would give it (newlines universal); undecodable bytes become U+FFFD rather than raising."""
    if isinstance(out, str):
        return out
    return out.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")


def git_cacheable(args):
    """True for a read-only git query whose answer is fixed by the repository state git_state_key reads."""
    if not args:
        return False
    args = [str(a) for a in args]
    sub = args[0]
    # Not `submodule status --cached`: its describe text reads the SUBMODULE's refs, which no key of this repository covers.
    if sub not in _GIT_CACHEABLE:
        return False
    if sub == "config" and not any(a in ("--get", "--get-all", "--get-regexp") for a in args[1:]):
        return False
    for a in args[1:]:
        if a in _GIT_REFLOG_ARGS or "@{" in a:
            return False
        if any(w in a for w in _GIT_CLOCK_WORDS):
            return False
    return True


def _repo_git_dirs(root):
    """(git dir, common dir) of the repository holding `root` (the nearest `.git` at or above it, read by _git_dirs without a process), or None when there is none or it has no HEAD. Memoized per process."""
    key = str(root)
    if key in _GIT_DIRS:
        return _GIT_DIRS[key]
    dirs = None
    with contextlib.suppress(OSError, ValueError, RuntimeError):
        here = pathlib.Path(root).resolve()
        for base in (here, *here.parents):
            if (base / ".git").exists():
                dirs = _git_dirs(base)
                break
    if dirs is not None and not (dirs[0] / "HEAD").is_file():
        dirs = None
    _GIT_DIRS[key] = dirs
    return dirs


def _stat_sig(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return [st.st_mtime_ns, st.st_size]


def git_reads_index(args):
    """True for a cacheable query whose answer comes from the index (a `:path` or `:<stage>:path` object name)."""
    args = [str(a) for a in args]
    return bool(args) and any(a.startswith(":") for a in args[1:])


def git_state_key(root, index=False):
    """The repository state a cacheable answer depends on, as a JSON-able list, or None when there is no readable git directory. The index's mtime and size join the key only for a query that reads the index (`index=True`): `git status` rewrites a racy index on most stops, and a key holding it would expire every ref answer with it."""
    if any(k in os.environ for k in _GIT_REPO_ENV):
        return None
    dirs = _repo_git_dirs(root)
    if dirs is None:
        return None
    gd, cd = dirs
    try:
        head = (gd / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    key = [str(gd), head]
    if head.startswith("ref: "):
        ref = head[5:].strip()
        try:
            key.append((cd / ref).read_text(encoding="utf-8").strip())
        except OSError:
            key.append(None)
    files = (
        cd / "packed-refs",
        cd / "FETCH_HEAD",
        cd / "config",
        gd / "config.worktree",
        gd / "rebase-merge",
        gd / "rebase-apply",
        gd / "MERGE_HEAD",
        gd / "CHERRY_PICK_HEAD",
        pathlib.Path(os.environ.get("GIT_CONFIG_GLOBAL") or os.path.expanduser("~/.gitconfig")),
        pathlib.Path(os.path.expanduser("~/.config/git/config")),
    )
    key.extend(_stat_sig(p) for p in files)
    # GIT_CONFIG_GLOBAL, GIT_CONFIG_NOSYSTEM and GIT_CONFIG_COUNT/KEY_n/VALUE_n change what `config --get` answers, so their values are part of the state.
    key.append(sorted([k, v] for k, v in os.environ.items() if k.startswith("GIT_CONFIG")))
    key.extend([dirpath, _stat_sig(dirpath)] for dirpath, _d, _f in os.walk(cd / "refs"))
    if index:
        key.append(["index", _stat_sig(gd / "index")])
    return key


def _key_hash(key):
    return hashlib.sha1(json.dumps(key).encode("utf-8")).hexdigest()[:16]


def _git_cache_for(gd):
    """The answer table of git dir `gd`, loaded from disk once per process: {answer key: [rc, stdout, state hash]}."""
    entry = _GIT_CACHE.get(str(gd))
    if entry is None:
        entry = {"answers": {}, "dirty": False}
        with contextlib.suppress(OSError, ValueError):
            disk = json.loads((gd / GIT_CACHE_NAME).read_text(encoding="utf-8"))
            if (
                isinstance(disk, dict)
                and disk.get("v") == 2
                and isinstance(disk.get("answers"), dict)
            ):
                entry["answers"] = disk["answers"]
        _GIT_CACHE[str(gd)] = entry
    return entry


def flush_git_cache():
    """Write each git dir's answers once (tmp + rename). The last writer wins, and every answer carries the hash of the state it was read at, so a merged-away answer costs one git call, never a stale one."""
    for gd, entry in list(_GIT_CACHE.items()):
        if not entry.get("dirty"):
            continue
        entry["dirty"] = False
        path = pathlib.Path(gd) / GIT_CACHE_NAME
        with contextlib.suppress(OSError, ValueError):
            fd, tmp = tempfile.mkstemp(dir=gd, prefix=GIT_CACHE_NAME)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"v": 2, "answers": entry["answers"]}, fh)
            os.replace(tmp, path)


def git_run(root, args, timeout=20, opts=()):
    """(returncode, stdout bytes) of `git <opts> -C root <args>`, or None when git could not run or timed out. A cacheable query on a readable repository is answered from the HEAD-keyed cache when the state it was read at still holds."""
    args = [str(a) for a in args]
    cached = read_memo_on() and git_cacheable(args)
    index = git_reads_index(args)
    key = git_state_key(root, index=index) if cached else None
    entry, akey, kh = None, None, None
    if key is not None:
        entry = _git_cache_for(_repo_git_dirs(root)[0])
        akey = json.dumps([os.path.realpath(str(root)), args])
        kh = _key_hash(key)
        hit = entry["answers"].get(akey)
        if isinstance(hit, list) and len(hit) == 3 and hit[2] == kh:
            GIT_CACHE_STATS["hit"] += 1
            return int(hit[0]), str(hit[1]).encode("utf-8", "surrogateescape")
    try:
        proc = subprocess.run(
            ["git", *opts, "-C", str(root), *args],
            capture_output=True,
            timeout=timeout,
            check=False,
            env=commit_only_env(args),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    GIT_CACHE_STATS["miss"] += 1
    if (
        entry is not None
        and len(proc.stdout) <= GIT_CACHE_MAX_ANSWER_BYTES
        and git_state_key(root, index=index) == key
    ):
        answers = entry["answers"]
        if len(answers) >= GIT_CACHE_MAX_ANSWERS:
            # Full: keep only the answers read at the current state.
            for k in [
                k for k, v in answers.items() if not (isinstance(v, list) and v[-1:] == [kh])
            ]:
                del answers[k]
        if len(answers) < GIT_CACHE_MAX_ANSWERS:
            answers[akey] = [proc.returncode, proc.stdout.decode("utf-8", "surrogateescape"), kh]
            entry["dirty"] = True
            if not _GIT_ATEXIT["on"]:
                import atexit

                atexit.register(flush_git_cache)
                _GIT_ATEXIT["on"] = True
    return proc.returncode, proc.stdout


AGENT_BRANCH_RE = re.compile(r"[^A-Za-z0-9._-]+")


def git_branch(root):
    """The slugified current branch, or "" when HEAD is not on one.

    NOTHING UNDER agent/ IS KEYED ON THIS ANY MORE (2026-08-18): the working notes tree is per session, and the only remaining caller is the sub-agent REPORT store in TMPDIR (wl_report), which keys per branch on purpose because a report is most wanted after its branch is gone.

    `symbolic-ref --short -q` and NOT `rev-parse --abbrev-ref HEAD`. The latter returns the LITERAL STRING "HEAD" on a detached HEAD, and that string slugs to a perfectly valid directory name, so it would silently seed a junk `HEAD` universe during every interactive rebase. Measured on this worktree: `private/renet` is detached, where abbrev-ref returns "HEAD" and symbolic-ref
    returns empty. Empty is the honest answer, and callers treat it as "cannot resolve a branch" rather than as a branch name.

    Slugged because a branch may contain a slash, which would otherwise nest a directory one level deeper than any caller expects.

    WORKLIST_AGENT_BRANCH is not decoration. It is how the test suite drives this without a git repo (its fixture leaves `.git` unusable, so `symbolic-ref` exits 128 and every branch-dependent check would be SKIPPED, which is a gate that never fires in its own suite), and it is the escape hatch for a session working mid-rebase.

    timeout=5, not `_git`'s default 20: the Stop hook's own budget is 15s, so a
    20s git call could outlive the hook that is waiting for it. `symbolic-ref` is a local read and returns instantly, so 5 is generous.
    """
    b = os.environ.get("WORKLIST_AGENT_BRANCH")
    if b is None:
        try:
            r = subprocess.run(
                ["git", "-C", str(root), "symbolic-ref", "--short", "-q", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            b = r.stdout if r.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            b = ""
    return AGENT_BRANCH_RE.sub("-", (b or "").strip()).strip("-.")


def _cron_field(spec, lo, hi):
    """The sorted set of matching values for one cron field, or None on any shape this parser does not understand (the caller treats None as unparseable and skips the cron rather than guessing)."""
    vals = set()
    for raw_part in spec.split(","):
        part = raw_part.strip()
        step = 1
        if "/" in part:
            part, _, s = part.partition("/")
            if not s.isdigit() or int(s) < 1:
                return None
            step = int(s)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, _, b = part.partition("-")
            if not (a.isdigit() and b.isdigit()):
                return None
            a, b = int(a), int(b)
        elif part.isdigit():
            a = b = int(part)
        else:
            return None
        if a < lo or b > hi or a > b:
            return None
        vals.update(range(a, b + 1, step))
    return sorted(vals)


def cron_next(schedule, now=None):
    """The next fire time (UTC datetime) of a 5-field cron expression after `now`, or None when the expression is unparseable or never fires within 60 days.

    WHY THIS EXISTS (operator, 2026-07-30): the Stop event's `session_crons` carries the FULL expansion of every scheduled task -- id, schedule, and the exact prompt that will fire -- but the hook was ignoring it and reporting the loop from a hand-declared sidecar that goes stale. The truthful answer to "when does work resume, and what happens then?" is computable from the event;
    this is the computing half.

    Standard cron semantics including the one everyone forgets: when BOTH day-of-month and day-of-week are restricted, the entry fires when EITHER matches. dow accepts 0-7 with both 0 and 7 meaning Sunday. Python's
    weekday() has Monday=0, cron has Sunday=0; the +1 %% 7 below is that
    conversion, worth naming because it reads like an off-by-one.
    """
    fields = (schedule or "").split()
    if len(fields) != 5:
        return None
    mins = _cron_field(fields[0], 0, 59)
    hours = _cron_field(fields[1], 0, 23)
    doms = _cron_field(fields[2], 1, 31)
    months = _cron_field(fields[3], 1, 12)
    dows = _cron_field(fields[4], 0, 7)
    if None in (mins, hours, doms, months, dows):
        return None
    dows = sorted({d % 7 for d in dows})  # 7 == 0 == Sunday
    dom_star = fields[2] == "*"
    dow_star = fields[4] == "*"
    now = now or utcnow()
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for _ in range(60):
        if day.month in months:
            dom_hit = day.day in doms
            dow_hit = ((day.weekday() + 1) % 7) in dows
            # Both restricted -> OR; otherwise the starred one is vacuous.
            day_ok = (
                (dom_hit or dow_hit)
                if (not dom_star and not dow_star)
                else (dom_hit if not dom_star else dow_hit if not dow_star else True)
            )
            if day_ok:
                for h in hours:
                    for m in mins:
                        cand = day.replace(hour=h, minute=m)
                        if cand > now:
                            return cand
        day += datetime.timedelta(days=1)
    return None


def tasks_dir(session_id):
    home = os.environ.get("WORKLIST_TASKS_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude", "tasks"
    )
    return os.path.join(home, "session-" + session_id[:8])


# v19: THE TASK DIR IS NOT ALWAYS NAMED AFTER THE STOP EVENT'S SESSION ID. On 2026-08-08 a session's tasks lived under session-6e7fb45f (the harness
# team id) while every Stop event said session_id=d136ac61, so pending_tasks
# read a directory that did not exist and returned [] for the whole session -- the exact "two queues, one supervisor, watching the empty one" failure the v5 docstring below describes, reintroduced one naming scheme later, and
# INVISIBLE because "missing dir = no evidence" is also the function's
# legitimate no-manufactured-blocks safety.
#
# The join that survives the rename: the session TRANSCRIPT (whose path the Stop event does carry) contains every TaskCreate result verbatim -- "Task #<id> created successfully: <subject>" -- and a directory holding a task with that exact id whose subject matches is this session's directory. Content-based, deterministic, and refuses on ambiguity (0 or 2+ matching dirs resolve to
# None, which downstream treats as "no evidence", never a manufactured block). Cached per process so the fallback's directory scan runs at most once per hook invocation.
_TASKS_DIR_CACHE = {}
_TASK_CREATED_RE = re.compile(r"Task #(\d+) created successfully: ([^\"\\\n]{10,})")


def _taskdir_cache_file(key):
    # Same /tmp family the hook already uses. Persisting the resolution is what lets TRANSCRIPT-LESS processes (the --state CLI verb at worklist.py:884, any other verb) agree with the stop battery: without it, world_sig written by the CLI and world_sig checked by the hook would hash DIFFERENT task sets whenever the primary dir is empty, and STATE.md would look eternally stale.
    # Found by review on #559 (the sweep finding).
    return os.path.join(tempfile.gettempdir(), "claude-worklist", "taskdir." + key)


def _resolve_tasks_dir(session_id, transcript_path=None):
    if not session_id:
        return None
    key = session_id[:8]
    if key in _TASKS_DIR_CACHE:
        return _TASKS_DIR_CACHE[key]
    d = tasks_dir(session_id)
    # An EMPTY primary dir is "no evidence", not an answer: the live failure had a zero-file session-d136ac61 relic (created 2026-07-23, before the harness renamed its task store) shadowing the real session-6e7fb45f. Only a primary dir that actually holds a task settles the question.
    if os.path.isdir(d) and glob.glob(os.path.join(d, "*.json")):
        _TASKS_DIR_CACHE[key] = d
        return d
    # Durable cache next: a previous process (with a transcript) may have resolved this already. Validated before trust -- the dir must still exist and still hold a task; a stale pointer is discarded, never followed.
    try:
        cf = _taskdir_cache_file(key)
        if os.path.isfile(cf):
            with open(cf, encoding="utf-8") as fh:
                cached = fh.read().strip()
            if cached and os.path.isdir(cached) and glob.glob(os.path.join(cached, "*.json")):
                _TASKS_DIR_CACHE[key] = cached
                return cached
    except OSError:
        pass
    resolved = None
    if transcript_path and os.path.isfile(transcript_path):
        try:
            got = tail_bytes(transcript_path, TRANSCRIPT_TAIL_BYTES)
            if got is None:
                raise OSError("transcript unreadable")
            tail = got[2].decode("utf-8", "replace")
            # Newest creations first: the last one is the least likely to have been deleted since. Subjects are read out of JSONL, so cut each at the first escape sequence and prefix-match on what is left.
            matches = _TASK_CREATED_RE.findall(tail)[-5:][::-1]
            cands = set()
            for tid, raw_subj in matches:
                subj = raw_subj.strip()
                for sd in glob.glob(os.path.join(os.path.dirname(d), "session-*")):
                    f = os.path.join(sd, tid + ".json")
                    if not os.path.isfile(f):
                        continue
                    try:
                        with open(f, encoding="utf-8") as fh:
                            t = json.load(fh)
                    except (OSError, ValueError):
                        continue
                    if str(t.get("subject", "")).strip().startswith(subj):
                        cands.add(sd)
                if cands:
                    break  # the newest resolvable creation decides
            if len(cands) == 1:
                resolved = cands.pop()
        except OSError:
            resolved = None
    if resolved:
        # Persist for transcript-less processes (tmp+rename; best-effort).
        try:
            cf = _taskdir_cache_file(key)
            os.makedirs(os.path.dirname(cf), exist_ok=True)
            tmp = cf + ".tmp." + str(os.getpid())
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(resolved)
            os.replace(tmp, cf)
        except OSError:
            pass
    _TASKS_DIR_CACHE[key] = resolved
    return resolved


def pending_tasks(session_id, transcript_path=None):
    """Harness Task-list items that are not done, as [(id, subject, status)].

    THE POINT OF v5. The hook used to see only the markdown worklist, and a session kept that at zero open items while six tasks sat pending in the harness. Two queues, one supervisor, watching the empty one.

    Never raises: a missing or malformed task dir means "no evidence of pending work", which cannot manufacture a block out of nothing.
    """
    if not session_id:
        return []
    d = _resolve_tasks_dir(session_id, transcript_path) or tasks_dir(session_id)
    out = []
    try:
        for f in sorted(glob.glob(os.path.join(d, "*.json"))):
            try:
                with open(f, encoding="utf-8") as fh:
                    t = json.load(fh)
            except (OSError, ValueError):
                continue
            if t.get("status") in ("pending", "in_progress"):
                out.append((str(t.get("id", "?")), str(t.get("subject", ""))[:70], t.get("status")))
    except OSError:
        return []
    out.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 1 << 30)
    return out


def actionable_tasks(session_id, transcript_path=None):
    """Pending harness tasks whose every recorded blocker is finished, as [(id, subject)] -- the tasks a waiting session could be working RIGHT NOW.

    v19, operator directive 2026-08-08: a session sat in "pure background wait" for hours while a fully-planned task was pending and unblocked; the check-in kept saying "this is not a demand for other work" because the pure-wait state never consulted the harness queue. A pending task with an unresolved `blockedBy` is legitimately parked; one without is not. A blocker id whose
    file no longer exists counts as resolved (deleted tasks vanish from the dir). Never raises."""
    if not session_id:
        return []
    d = _resolve_tasks_dir(session_id, transcript_path)
    if not d:
        return []
    all_t = {}
    try:
        for f in glob.glob(os.path.join(d, "*.json")):
            try:
                with open(f, encoding="utf-8") as fh:
                    t = json.load(fh)
            except (OSError, ValueError):
                continue
            if t.get("id") is not None:
                all_t[str(t["id"])] = t
    except OSError:
        return []
    out = []
    for tid, t in all_t.items():
        if t.get("status") != "pending":
            continue
        unresolved = [
            b
            for b in (t.get("blockedBy") or [])
            if str(b) in all_t and all_t[str(b)].get("status") != "completed"
        ]
        if not unresolved:
            out.append((tid, str(t.get("subject", ""))[:70]))
    out.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 1 << 30)
    return out


def task_statuses(session_id, transcript_path=None):
    """{id: (status, subject)} for ALL harness tasks, completed included.
    pending_tasks() serves the queue; this serves the completion-evidence check and the liveness ladder, which need TRANSITIONS, not the queue."""
    if not session_id:
        return {}
    d = _resolve_tasks_dir(session_id, transcript_path) or tasks_dir(session_id)
    out = {}
    try:
        for f in glob.glob(os.path.join(d, "*.json")):
            try:
                with open(f, encoding="utf-8") as fh:
                    t = json.load(fh)
            except (OSError, ValueError):
                continue
            if t.get("id") is not None:
                out[str(t["id"])] = (str(t.get("status", "")), str(t.get("subject", ""))[:70])
    except OSError:
        return {}
    return out


#: Backticked and quoted spans, blanked out.
#:
#: LIVES HERE, not beside its first caller, because two modules now need the
#: same one. wl_checks has used it since V_FOUND_NOT_FIXED for every detector
#: whose trigger phrases appear in prose ABOUT the rule, and wl_admit's
#: pending-ask gate needs exactly the same treatment for exactly the same
#: reason: this file, CLAUDE.md and the hook's own block texts all quote the
#: phrases these gates match. A gate that cannot survive being WRITTEN ABOUT is
#: too broad, and the fix is not a narrower pattern but ignoring the spans where
#: quoting happens. wl_checks._strip_quoted_spans delegates here so its ~6 call
#: sites keep one definition rather than acquiring a second copy that drifts.
def strip_quoted_spans(text):
    """Blank out backticked and quoted spans."""
    return re.sub(r"`[^`]*`|\"[^\"]*\"|\u201c[^\u201d]*\u201d", " ", text or "")


TRANSCRIPT_TAIL_BYTES = int(os.environ.get("WORKLIST_TAIL_BYTES", "2000000"))


# ---- ONE TRANSCRIPT READ PER STOP (agent/plans/PLAN-tooling-speed.md D1) ------
#
# The Stop run read the transcript tail about twelve times: the tasks-dir join, transcript_tail, wl_admit, wl_deflect, wl_uncommitted, each its own open, seek and parse. The memo below keeps the LAST bytes read per path, keyed on (mtime_ns, size), and serves any later request whose start lies inside them; a request reaching further back, or a file whose mtime or size moved, reads
# again. A miss reads at least TRANSCRIPT_TAIL_BYTES, so the standard-size readers that follow are all served by the first. The parsed records of one (path, mtime, size, start) are memoized too, and every caller gets its own list.
#
# A memo can serve a stale read only if a write keeps both mtime_ns and size, which an append cannot. WORKLIST_READ_MEMO=off turns it off (the control in test_wl_stop_speed_reads.py proves the open counter is not blind with it off).
READ_MEMO_STATS = {"hit": 0, "miss": 0}
_TAIL_MEMO: dict[str, tuple] = {}
_RECS_MEMO: dict[tuple, list] = {}
_MEMO_PATHS_MAX = 4


def read_memo_on():
    """False only under WORKLIST_READ_MEMO=off."""
    return os.environ.get("WORKLIST_READ_MEMO", "on").strip().lower() != "off"


def clear_read_memo():
    _TAIL_MEMO.clear()
    _RECS_MEMO.clear()
    READ_MEMO_STATS.update(hit=0, miss=0)


def tail_bytes(path, max_bytes=None, start=None):
    """(size, start, data): the bytes of `path` from `start`, or the last `max_bytes` when no start is given, to the end. None when the file cannot be read.

    Served from the per-process memo when the file's mtime and size are unchanged and the memo's bytes reach back to the requested start.
    """
    try:
        st = os.stat(path)
    except (OSError, TypeError, ValueError):
        return None

    def want_of(size):
        if start is not None:
            return min(max(0, int(start)), size)
        return max(0, size - int(max_bytes or 0))

    key = os.path.abspath(os.fsdecode(path))
    on = read_memo_on()
    m = _TAIL_MEMO.get(key) if on else None
    want = want_of(st.st_size)
    if m is not None and m[0] == st.st_mtime_ns and m[1] == st.st_size and m[2] <= want:
        READ_MEMO_STATS["hit"] += 1
        return st.st_size, want, m[3][want - m[2] :]
    try:
        with open(path, "rb") as fh:
            fst = os.fstat(fh.fileno())
            size, mtime = fst.st_size, fst.st_mtime_ns
            want = want_of(size)
            read_from = min(want, max(0, size - TRANSCRIPT_TAIL_BYTES)) if on else want
            fh.seek(read_from)
            data = fh.read(size - read_from)
    except OSError:
        return None
    READ_MEMO_STATS["miss"] += 1
    if on:
        if len(_TAIL_MEMO) >= _MEMO_PATHS_MAX:
            _TAIL_MEMO.clear()
            _RECS_MEMO.clear()
        _TAIL_MEMO[key] = (mtime, size, read_from, data)
    return size, want, data[want - read_from :]


def tail_records(path, max_bytes):
    """The JSON objects in the last `max_bytes` of the file at `path`, oldest first, or None when there is no such file or it cannot be read; wl_common.tail_records' contract, served from the memo. When the read starts mid-file its first line is dropped, because it is probably partial."""
    if not path or not os.path.exists(path):
        return None
    got = tail_bytes(path, max_bytes)
    if got is None:
        return None
    size, start, chunk = got
    on = read_memo_on()
    rkey = None
    if on:
        m = _TAIL_MEMO.get(os.path.abspath(os.fsdecode(path)))
        rkey = (os.path.abspath(os.fsdecode(path)), m[0] if m else None, size, start)
        if rkey in _RECS_MEMO:
            return list(_RECS_MEMO[rkey])
    lines = chunk.split(b"\n")
    if start > 0:
        lines = lines[1:]
    recs = list(wl_common.records(lines))
    if rkey is not None:
        _RECS_MEMO[rkey] = recs
    return list(recs)


# wl_admit.turn_text and wl_deflect read the tail through wl_common.tail_records; rebinding the shared name here serves them from the same memo without a second copy of the reader. Same contract, same return value. A reader that opens the transcript itself (wl_admit.turn_tools, wl_uncommitted.scan_transcript) is served only once it calls tail_bytes, and test_wl_stop_speed_reads.py names each one that still opens it.
wl_common.tail_records = tail_records


def transcript_tail(path, want=None, tries=6, delay=0.25):
    """(last_assistant_text, tool_names_since_last_user, readable) from the tail.

    THE RACE THIS RIDES OUT, found the hard way: the gate blocked a message that DID carry its `## Remaining` heading. Re-reading the transcript afterwards showed the heading present in a single text block, so the extraction was fine and the file simply had not been flushed when the hook ran. A check that reads the transcript to judge the message that just ended is racing the
    writer, so when `want` is absent it retries briefly before believing it.

    `readable` distinguishes "I read the message and the heading is absent" from "I could not read any assistant text at all". Those need different verdicts: the first is the session's fault, the second is this hook's.

    Tail-read, because the transcript is tens of MB and the hook runs on every stop. Measured: 2 MB tail + parse is 0.08s / 15 MB RSS on a 36 MB file, so this is not the expensive part of anything.
    """
    # The first (probably partial) line is dropped unless the read started at byte 0.
    recs = tail_records(path, TRANSCRIPT_TAIL_BYTES)
    if recs is None:
        return "", [], False
    turn_texts, since_user = [], []
    for rec in recs:
        rtype = rec.get("type")
        if rtype == "user":
            # A new operator turn resets what "this turn" means.
            since_user = []
            turn_texts = []
            continue
        if rtype != "assistant":
            continue
        for block in rec.get("message", {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text", "").strip():
                # EVERY narration line before a tool call is its own text block, so the LAST block mid-turn is a one-liner, not the answer. That is what made this check fire on a message that did carry its heading. Judge the whole turn's output instead.
                turn_texts.append(block["text"])
            elif block.get("type") == "tool_use" and block.get("name"):
                since_user.append(block["name"])
    last_text = "\n\n".join(turn_texts)
    readable = bool(last_text)
    if want is not None and readable and want.search(last_text) is None and tries > 1:
        # Not there yet. Give the writer a moment rather than calling the session a liar about a message it actually wrote.
        time.sleep(delay)
        return transcript_tail(path, want, tries - 1, delay)
    return last_text, since_user, readable


# ARM THE EXIT RECORDER, LAST, and inside a guard that turns any Exception into one stderr line.
#
# wl_core is imported by 16 modules and by every one of the ~880 python3 invocations the case suite makes, so this line is the single seam that turns "profile every hook process" into one edit with no settings change, no wrapper and no per-guard work. It is also, for the same reason, the single line that could break every hook at once -- which is why the import itself is guarded,
# why wl_resprofile.install() never raises, why its exit handler writes nothing to
# stdout or stderr, and why WORKLIST_PROFILE=off exists. A profiler that can
# change the exit code of the thing it measures is not a profiler.
try:
    import wl_resprofile as _resprofile

    _resprofile.install()
except Exception as _profiler_exc:
    # Only Exception: SystemExit and KeyboardInterrupt are the hook's own to raise and must propagate. The failure is named once on stderr and never changes the exit code or stdout of the hook it measures.
    # A closed or broken stderr cannot carry the line; the hook's exit code stays its own.
    # sys.stderr is None when fd 2 was invalid at startup, so the write raises AttributeError; that is suppressed too.
    with contextlib.suppress(OSError, ValueError, AttributeError):
        sys.stderr.write(
            "wl_core: resprofile profiler not armed (%s: %s)\n"
            % (type(_profiler_exc).__name__, _profiler_exc)
        )
