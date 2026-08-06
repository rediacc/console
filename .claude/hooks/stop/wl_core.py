"""wl_core: shared primitives for the worklist Stop hook.

Stdlib-only, no sibling imports, no I/O beyond what each helper documents.
Everything here is used by at least two sibling modules; single-consumer
logic lives with its consumer. WHY comments for each check stay with the
check, not here.
"""

import datetime
import glob
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

# `- [ ] (5546d4bb) do the thing`  ->  state " ", owner "5546d4bb"
# Owner accepts any word-ish label, not just hex: a named agent tagged items
# "(perf6-daemon)", the old hex-only charset failed to parse it, the item read
# as UNTAGGED, and untagged defaults to mine -- so every OTHER session was
# blocked on that agent's work. Non-prefix labels now parse as owners and are
# reported-never-blocking for everyone (including the labeler: only a tag that
# is a PREFIX of your session id binds you).
ITEM = re.compile(
    r"^\s*-\s*\[(?P<state>[ x?>])\]\s*(?:\((?P<owner>[A-Za-z0-9][A-Za-z0-9._-]*)\)\s*)?"
)
# Same shape but INCLUDING tombstones, for the md-sync pass which must see a
# `[~]` flip as a deletion rather than as an unparseable line.
ITEM_ANY = re.compile(
    r"^\s*-\s*\[(?P<state>[ x?>~])\]\s*(?:\((?P<owner>[A-Za-z0-9][A-Za-z0-9._-]*)\)\s*)?"
)
LEASE = re.compile(r"until:(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)Z")
# worker:<background-task-id> on a lease line names the OS-checkable delegate.
WORKER = re.compile(r"worker:([A-Za-z0-9._-]{1,40})")
DEFAULT_TOKEN = re.compile(r"\bDEFAULT:[ \t]*\S")
# v12 justification tokens (operator, 2026-07-30: "Too many '[?]'. This is an
# escape hatch... there should be a field in json like 'why' and possibly
# many"). A deferral now carries WHY (why THIS session cannot settle it right
# now) and HOW (the concrete action or evidence that would resolve it), plus
# optional TRIED / NEEDS / BLOCKED_ON. They live as inline tokens in the item
# text (so the markdown inbox round-trips them) AND as a real `j` field on
# the store event (so nothing downstream re-parses prose it wrote itself).
JUST_TOKEN = re.compile(r"\b(WHY|HOW|TRIED|NEEDS|BLOCKED_ON|DEFAULT):")
# WHY values that describe avoidance rather than inability. Deliberately a
# SHORT list of unambiguous shapes: this regex is the cheap gate at creation
# time; whether a why that passes it is actually TRUE is the judge's question.
VAGUE_WHY_RE = re.compile(
    r"\b(did ?not get (to|around)|didn'?t get (to|around)|no time|not yet"
    r"|too busy|later|low priority|will (do|get to)|have?n'?t (had|gotten"
    r"|got around))\b",
    re.IGNORECASE,
)
# Same charset the worklist owner tag accepts, so a request's from/to can be
# written into a `- [?]` line on escalation without re-validation.
PREFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")

# Leases beyond this horizon are invalid: a `- [>]` marked "until next year"
# would be a bypass, not a delegation. 120 also aligns the lease horizon with
# the top rung of the v10 liveness ladder.
MAX_LEASE_MIN = 120


def parse_justification(text):
    """{field: value} for every WHY:/HOW:/TRIED:/NEEDS:/BLOCKED_ON: token in a
    deferral's text, keys lowercased. A value runs to the next known token
    (DEFAULT: included, so the tokens compose in any order) or to the end of
    the line. Empty values are absent, so `bool(j.get("why"))` is the whole
    presence test."""
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
    """An ISO8601Z stamp `minutes` from now. Used where a message promises a
    bound (the background check-in's next-earliest time): a claimed latch a
    reader cannot check from the message alone is not a latch, it is a
    slogan."""
    return (utcnow() + datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_stamp(stamp):
    """datetime or None from an ISO8601Z stamp (seconds optional)."""
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%MZ"):
        try:
            return datetime.datetime.strptime(stamp, fmt).replace(tzinfo=datetime.UTC)
        except (TypeError, ValueError):
            continue
    return None


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


def owned_by_me(owner, session_id):
    """An UNTAGGED item is mine: that is the safe default, since the cost of
    wrongly claiming one is doing a little extra work, while the cost of wrongly
    disowning one is silently dropping it. A tag is a PREFIX of the session id
    (CLAUDE.md asks for a short prefix, not the whole uuid)."""
    if owner is None:
        return True
    return bool(session_id) and session_id.startswith(owner)


def same_session(a, b):
    """Two prefixes/ids denote one session when either is a prefix of the
    other. Symmetric, because CLI callers pass short prefixes while the Stop
    event carries the full id, and either side of a comparison can be either."""
    return bool(a) and bool(b) and (a.startswith(b) or b.startswith(a))


# The identity a `<me>` argument may name without being checked against the
# environment. "operator" is the HUMAN's reply handle: wl_email mails
# `worklist.py --answer operator <id> '<words>'` to a person who runs it in
# whatever shell they have open, and if that shell happens to be a Claude
# session's Bash the env check would refuse the one command the mail exists to
# get run. It is a name, not a session prefix, and it was never verifiable.
#
# THE HOLE THIS LEAVES, ACCEPTED AND UNDECIDABLE. Because "operator" is exempt,
# a session can run `--answer operator <its-own-request-id>` and answer its own
# question, slipping past the self-answer refusal in wl_requests (which compares
# `me` to the asker). This is PRE-EXISTING -- it was true before any identity
# checking existed and is not a regression from it -- and it is recorded here
# rather than fixed because both obvious fixes are worse than the hole:
#
#   * "refuse when a session id IS resolvable" breaks the exact case the
#     exemption exists for. The documented path is a human pasting the mailed
#     command into a Claude session's Bash, and that process has a perfectly
#     resolvable CLAUDE_CODE_SESSION_ID. The fix would refuse the operator.
#   * "refuse when the answering session is the asker" fails too: the operator
#     may legitimately paste the answer into the very session that asked, which
#     is the commonest way it happens.
#
# There is no narrower rule, and the reason is structural rather than a gap in
# imagination: from inside this process, a session forging an operator answer
# and the operator answering through that session's shell are the SAME syscall,
# from the same pid, with the same environment. Nothing observable separates
# them. Any check would be inferring intent from evidence that does not carry
# it -- which is the shape of validation that produced the incident this module
# exists to prevent.
#
# If this is ever worth closing, the honest mechanism is a SHARED SECRET carried
# in the mail (a per-request token wl_email generates and --answer requires),
# not an inference. That makes the operator's answer provable instead of
# assumed. Until someone wants that, an operator answer is trusted by
# construction, and this comment is why.
UNCHECKED_ME = ("operator",)
# A `<me>` must be at least this long. GENERALISED from --poll/--wait, which
# have carried the floor since they were written for a reason that applies
# everywhere: a short prefix names a DIFFERENT sidecar than the Stop hook
# derives from the full session id, so it half-works instead of failing. It
# also closes the hole `same_session`'s symmetry would leave open -- `--add d`
# would otherwise be accepted by every session whose id starts with "d".
ME_MIN_LEN = 8


def resolve_session_id():
    """This process's TRUE session id, or "" when the environment cannot say.

    ONE definition, deliberately: two answers to "who am I" is how the drift
    this function exists to catch starts again.

    WORKLIST_SESSION_ID first, and it is an identity ASSERTION rather than a
    suppression flag -- the test suite declares its fixture id with it, and an
    operator acting for a dead session declares that session's id. A boolean
    bypass was rejected: it would suppress the check without stating a claim,
    which is the exact shape docs/agent/suppressions.md exists to prevent, and
    it would be reachable by a session trying to get past its own mistake.

    CLAUDE_CODE_SESSION_ID, not CLAUDE_SESSION_ID. The latter DOES NOT EXIST;
    the name was verified against a live Bash-tool child's environment rather
    than guessed, and a wrong name here resolves to "" forever, which every
    caller treats as pass -- a check that cannot fire, wearing the costume of
    one that works. The harness injects it per child spawn and rotates it on
    /clear, so it is "current id", not "id at startup", and it is
    platform-neutral (no /proc, no filesystem assumption). Sub-agents inherit
    the PARENT's value, which is why a sub-agent tagging items with the parent
    prefix is correct and this check does not fire on the sub-agent fleet.

    Returns "" rather than raising. "" means CANNOT VERIFY, and the honest
    response to that is to say nothing, not to accuse.
    """
    return str(
        os.environ.get("WORKLIST_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    ).strip()


def check_me(me):
    """(ok, message) for a `<me>` argument: is this session really that one?

    THE DEFECT THIS CLOSES, in one paragraph because the fix is only obvious
    once you have seen it. Every `<me>` in this CLI was accepted on SHAPE alone
    (PREFIX_RE), and nothing had ever compared one to reality. A session copied
    a SUB-AGENT's namespace token out of a Task-spawn tool result
    (`agent_id: search-renet2@session-4c3e095a`) and used it as its own `<me>`
    for 26 hours: 219 calls under the wrong identity and 20 under the right one,
    from the same process. Every individual operation SUCCEEDED, because writes
    and reads key off the same unvalidated string -- so one typo splits a session
    into two half-sessions, each internally consistent, and nothing downstream
    can tell. The cost was a peer's message sitting unread in the other half's
    inbox for 34 hours while it auto-escalated.

    ASYMMETRIC on purpose: `sid.startswith(me)`, not `same_session(me, sid)`.
    On the CLI `me` is always a claim about SELF, never a peer id, so the
    symmetry that makes same_session right for peer comparisons is exactly what
    would let a one-character `me` through here. same_session is NOT changed;
    its other callers compare peers, where symmetry is correct.

    REFUSES rather than warns (operator decision). A warning beside a
    successful command is what the failing session skimmed past for a day:
    shape-only validation passing silently is what let this through in the
    first place, and a warning would be read past the same way. A non-zero exit
    costs one turn and the message carries the copy-paste fix.
    """
    me = me or ""
    if me in UNCHECKED_ME:
        return True, ""
    sid = resolve_session_id()
    if not sid:
        # UNVERIFIABLE, so silent. A plain operator terminal has no session id
        # and must not be accused of impersonating one.
        return True, ""
    if len(me) < ME_MIN_LEN and os.environ.get("WORKLIST_SESSION_ID") != me:
        # The floor is skipped ONLY on an exact declared match, and that
        # exception is a bug fix, not a loophole. Legacy sub-agents tagged items
        # with their NAME (`w2s-en`, 6 chars), and those items still need
        # reading and reassigning. Without this, `WORKLIST_SESSION_ID=w2s-en
        # --list --open w2s-en` was REFUSED and then advised to "rerun with
        # <me>=w2s-en" -- the value it had just rejected. An instruction that
        # tells you to retry the thing it refused leaves no next move at all,
        # and it made two real items unreadable.
        #
        # Safe because the floor guards against an UNDER-SPECIFIED guess about
        # self, and an exact match to an explicit declaration is not a guess.
        # A bare short `me` with no declaration is still refused, which is the
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
    """The refusal text. Names the variable it read, because the next session to
    hit this needs the mechanism to be inspectable, not just the verdict."""
    src = (
        "WORKLIST_SESSION_ID" if os.environ.get("WORKLIST_SESSION_ID") else "CLAUDE_CODE_SESSION_ID"
    )
    return (
        "identity mismatch: you passed <me>=%s but %s (%s).\n"
        "Writing as one identity and reading as another gives you two inboxes "
        "and neither of them is complete: every call succeeds, the halves stay "
        "internally consistent, and a peer's message waits in the one you are "
        "not reading.\n"
        "  rerun with <me>=%s\n"
        "If you really mean to act as another session, declare it rather than "
        "assert it by hand:\n"
        "  WORKLIST_SESSION_ID=<that session's id> worklist.py ..."
        % (me, why, src, sid[:ME_MIN_LEN])
    )


def project_root(start):
    """Nearest ancestor holding .git. This repo uses worktrees, where .git is a
    FILE, not a directory, so test existence rather than is_dir().

    Resolves from WHEREVER IT IS POINTED, deliberately. It cannot tell a repo
    from a repo nested inside one, and it must not try -- see project_start(),
    which is what every caller should be pointing it at.
    """
    p = pathlib.Path(start).resolve()
    for candidate in [p, *p.parents]:
        if (candidate / ".git").exists():
            return candidate
    return p


# <repo>/.claude/hooks/stop/wl_core.py -> parents[3] is <repo>.
_HOOK_ROOT_DEPTH = 3


def hook_repo_root():
    """The repo this hook FILE lives in, or None if it does not look like one.

    Immune to cwd by construction, which is the whole point: settings.json
    invokes every hook as "$CLAUDE_PROJECT_DIR/.claude/hooks/...", so this
    answers the same thing the env var does at hook time, and keeps answering
    it when a human runs the CLI from a subdirectory with no env var set.
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

    WHY THIS EXISTS, measured 2026-08-06. The Stop event's cwd is wherever the
    session last worked, and this tree has repos INSIDE the repo: submodules
    (private/renet) and gitignored non-submodule siblings (private/growth).
    Resolving from cwd walked project_root() straight into one of those and
    read ITS branch -- a session on 0804-1 was told to bootstrap `.agent/main/`
    because private/growth happened to be on main. Confirmed twice, on both
    kinds of nested repo, so it is not a submodule quirk.

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

    THE FIX THAT LOOKS RIGHT AND IS NOT: teaching project_root() to skip a
    `.git` file pointing into `/modules/`. This repo is ITSELF a submodule
    (`gitdir: ../.git/modules/console`), so that walks PAST console, changes
    the store slug from home_muhammed_monorepo_console to
    home_muhammed_monorepo, and orphans every open item in one step. Tried and
    reverted. Anchoring the START is the fix; the WALK is fine as it is.
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
    # TMPDIR first, then tempfile's search. NOT a bare gettempdir(): on POSIX
    # that also honours TEMP and TMP, so a machine with TEMP set and TMPDIR
    # unset would resolve a DIFFERENT worklist path than the old expression did
    # and silently orphan every live session's open items. This spelling is
    # byte-identical to `os.environ.get("TMPDIR", "/tmp")` wherever TMPDIR is
    # set or absent-with-/tmp-present (verified on this machine), and it is what
    # gives Windows -- which sets TEMP/TMP and never TMPDIR -- a real temp dir
    # instead of a literal "/tmp" it cannot create.
    d = pathlib.Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "claude-worklist"
    d.mkdir(parents=True, exist_ok=True)
    root = project_root(start)
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(root)).strip("_")
    return d / (slug + ".md")


def emit(obj):
    print(json.dumps(obj))
    sys.exit(0)


def _git(root, *args):
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


AGENT_BRANCH_RE = re.compile(r"[^A-Za-z0-9._-]+")


def git_branch(root):
    """The slugified current branch, or "" when HEAD is not on one.

    `symbolic-ref --short -q` and NOT `rev-parse --abbrev-ref HEAD`. The latter
    returns the LITERAL STRING "HEAD" on a detached HEAD, and that string slugs
    to a perfectly valid directory name, so it would silently seed a junk
    `.agent/HEAD/` universe during every interactive rebase. Measured on this
    worktree: `private/renet` is detached, where abbrev-ref returns "HEAD" and
    symbolic-ref returns empty. Empty is the honest answer, and callers treat it
    as "cannot resolve a branch" rather than as a branch name.

    Slugged because a branch may contain a slash: `feature/foo` would otherwise
    create a NESTED `.agent/feature/foo/`, which no caller expects and which the
    bootstrap message could not name in one `mkdir`.

    WORKLIST_AGENT_BRANCH is not decoration. It is how the test suite drives
    this without a git repo (its fixture leaves `.git` unusable, so
    `symbolic-ref` exits 128 and every branch-dependent check would be SKIPPED,
    which is a gate that never fires in its own suite), and it is the escape
    hatch for a session working mid-rebase.

    timeout=5, not `_git`'s default 20: the Stop hook's own budget is 15s, so a
    20s git call could outlive the hook that is waiting for it. `symbolic-ref`
    is a local read and returns instantly, so 5 is generous.
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
    """The sorted set of matching values for one cron field, or None on any
    shape this parser does not understand (the caller treats None as
    unparseable and skips the cron rather than guessing)."""
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
    """The next fire time (UTC datetime) of a 5-field cron expression after
    `now`, or None when the expression is unparseable or never fires within
    60 days.

    WHY THIS EXISTS (operator, 2026-07-30): the Stop event's `session_crons`
    carries the FULL expansion of every scheduled task -- id, schedule, and
    the exact prompt that will fire -- but the hook was ignoring it and
    reporting the loop from a hand-declared sidecar that goes stale. The
    truthful answer to "when does work resume, and what happens then?" is
    computable from the event; this is the computing half.

    Standard cron semantics including the one everyone forgets: when BOTH
    day-of-month and day-of-week are restricted, the entry fires when EITHER
    matches. dow accepts 0-7 with both 0 and 7 meaning Sunday. Python's
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


def pending_tasks(session_id):
    """Harness Task-list items that are not done, as [(id, subject, status)].

    THE POINT OF v5. The hook used to see only the markdown worklist, and a
    session kept that at zero open items while six tasks sat pending in the
    harness. Two queues, one supervisor, watching the empty one.

    Never raises: a missing or malformed task dir means "no evidence of pending
    work", which cannot manufacture a block out of nothing.
    """
    if not session_id:
        return []
    d = tasks_dir(session_id)
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


def task_statuses(session_id):
    """{id: (status, subject)} for ALL harness tasks, completed included.
    pending_tasks() serves the queue; this serves the completion-evidence
    check and the liveness ladder, which need TRANSITIONS, not the queue."""
    if not session_id:
        return {}
    d = tasks_dir(session_id)
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


TRANSCRIPT_TAIL_BYTES = int(os.environ.get("WORKLIST_TAIL_BYTES", "2000000"))


def transcript_tail(path, want=None, tries=6, delay=0.25):
    """(last_assistant_text, tool_names_since_last_user, readable) from the tail.

    THE RACE THIS RIDES OUT, found the hard way: the gate blocked a message that
    DID carry its `## Remaining` heading. Re-reading the transcript afterwards
    showed the heading present in a single text block, so the extraction was
    fine and the file simply had not been flushed when the hook ran. A check that
    reads the transcript to judge the message that just ended is racing the
    writer, so when `want` is absent it retries briefly before believing it.

    `readable` distinguishes "I read the message and the heading is absent" from
    "I could not read any assistant text at all". Those need different verdicts:
    the first is the session's fault, the second is this hook's.

    Tail-read, because the transcript is tens of MB and the hook runs on every
    stop. Measured: 2 MB tail + parse is 0.08s / 15 MB RSS on a 36 MB file, so
    this is not the expensive part of anything.
    """
    if not path or not os.path.exists(path):
        return "", [], False
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - TRANSCRIPT_TAIL_BYTES))
            chunk = f.read()
    except OSError:
        return "", [], False
    # Drop the first (probably partial) line unless we read from byte 0.
    lines = chunk.split(b"\n")
    if size > TRANSCRIPT_TAIL_BYTES:
        lines = lines[1:]
    turn_texts, since_user = [], []
    for raw in lines:
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
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
                # EVERY narration line before a tool call is its own text block,
                # so the LAST block mid-turn is a one-liner, not the answer. That
                # is what made this check fire on a message that did carry its
                # heading. Judge the whole turn's output instead.
                turn_texts.append(block["text"])
            elif block.get("type") == "tool_use" and block.get("name"):
                since_user.append(block["name"])
    last_text = "\n\n".join(turn_texts)
    readable = bool(last_text)
    if want is not None and readable and want.search(last_text) is None and tries > 1:
        # Not there yet. Give the writer a moment rather than calling the session
        # a liar about a message it actually wrote.
        time.sleep(delay)
        return transcript_tail(path, want, tries - 1, delay)
    return last_text, since_user, readable
