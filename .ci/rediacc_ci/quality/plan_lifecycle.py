"""Where a plan LIVES, and when it goes. The library half of `check:ci-plan-folders`.

WHY A FOLDER AT ALL. `agent/` held 103 `PLAN-*.md` at its root with no rule about where a plan sits or when it leaves, so the only lifecycle any plan had was the 33-day housekeeping clock and the compaction door. That clock answers "is this record stale"; it never answered "is this directory still a place a reader can find anything". The operator's ruling of 2026-09-21 is that the
answer must be structural and enforced for the CLASS rather than tidied for today's instances.

THE SHAPE, and every rule below is a consequence of it:

    agent/plans/                 active and backlog, the live corpus
    agent/plans/_done/           terminal, finished
    agent/plans/_removed/        terminal, withdrawn (`Status: removed` plus `Removed-Why:`)
    agent/PLAN-<slug>.md         the LEGACY location, and after the migration the STUB namespace

A plan moves EXACTLY ONCE, at close, and leaves a one-line stub at its old path. The stub is what keeps 523 citations across 130 files resolving without re-pointing a single one, which is the mechanism plan compaction already relies on.

TWO CLOCKS, AND NEITHER OF THEM IS `git log` ALONE.

  * TERMINAL, `terminal_days` (40). Measured from `moved_at`, the date the move
    was made, carried in the plan-boxes ledger row. It is CROSS-CHECKED against
    `git log -1 --format=%cI` of the new path, and a disagreement beyond one day
    is finding F6 rather than a silent preference for one of the two. Without
    that check `moved_at` is a number the mover types, and a typed number is not
    a clock.
  * BACKLOG, `backlog_days` (90). Measured from the OLDER of `First-Seen:` and
    `%cI`. `git log` does not follow renames, so the migration would otherwise
    reset every clock at once and buy 90 days of freshness for 103 plans that
    have not moved in months. `First-Seen:` is written at move time from the
    PRE-move committer date, and taking the older of the two means neither a
    move nor a re-write of the header can make a plan younger.

EXPIRY DELETES THE FILE AND KEEPS A TOMBSTONE. The row carries the title, both dates and the git blob id of the full text, and lives in `agent/INDEX.md` under its own section, which is the file `check_plan_record.py` already renders and compares for byte equality. A tombstone is revivable from the blob, so expiry loses no text; it loses a
directory entry nobody was reading.

THE PURE CORE IS PURE ON PURPOSE. `parse_plan`, `classify`, `folder_for`, `retention_days` and every `findings_*` function take data and return data: no git, no filesystem, no clock. That is what lets the gate's controls PLANT a defect into fixture TEXT and assert the finding appears, rather than staging a git repository per control. The impure half is three
functions at the bottom, each of which does one thing and is named for it.
"""

import dataclasses
import datetime as dt
import json
import os
import pathlib
import re

from rediacc_ci import gitx, paths

# --------------------------------------------------------------------------- The layout, in one place.

AGENT_DIR = "agent"
PLANS_DIR = "agent/plans"
DONE_DIR = "agent/plans/_done"
REMOVED_DIR = "agent/plans/_removed"
TERMINAL_DIRS = (DONE_DIR, REMOVED_DIR)

#: Every directory a plan may legally sit in, widest first so a `startswith`
#: scan matches the most specific one. Order is load-bearing: `agent/plans/_done`
#: is a prefix-extension of `agent/plans`, and testing the short one first would
#: file every terminal plan as active.
PLAN_DIRS = (DONE_DIR, REMOVED_DIR, PLANS_DIR, AGENT_DIR)

PLAN_PREFIX = "PLAN-"
PLAN_SUFFIX = ".md"

#: Git pathspecs that enumerate the whole corpus, legacy location included. A
#: bare `*` crosses `/` in git's wildmatch, so `agent/*PLAN-*.md` alone would
#: also match `agent/archive/plans/PLAN-x.md` and `agent/<session>/PLAN-x.md`.
#: The four are spelled out so the set is exactly the four legal folders.
PLAN_PATHSPECS = (
    "agent/PLAN-*.md",
    "agent/plans/PLAN-*.md",
    "agent/plans/_done/PLAN-*.md",
    "agent/plans/_removed/PLAN-*.md",
)

DEFAULT_CONFIG_REL = ".ci/config/plan-lifecycle.json"
LEDGER_REL = ".ci/config/plan-boxes.json"
INDEX_REL = "agent/INDEX.md"

#: How far into a file the header keys are looked for. `wl_checks` reads
#: `Status:` within 10 lines; two more are allowed here because a moved plan
#: gains `First-Seen:` and a removed one gains `Removed-Why:` above it.
HEADER_LINES = 12

#: How many bytes of a plan are read to decide whether it is a stub. A stub is
#: five lines; a real plan's header is inside this too, so the probe answers
#: both questions from one read and the stat-only census path never has to open
#: a whole plan to tell a pointer from a document.
STUB_PROBE_BYTES = 1024

#: The corpus floor, shared with `check_plan_boxes` and `check_plan_record`
#: rather than re-typed: below this the enumeration has lost the tree and no
#: verdict about folders would mean anything.
MIN_PLAN_FILES = int(os.environ.get("PLAN_FOLDERS_MIN_PLANS", "20"))

ROOT_ENV = "PLAN_FOLDERS_ROOT"

# --------------------------------------------------------------------------- Line grammars. Anchored, every one of them.

STATUS_RE = re.compile(r"^\*{0,2}Status\*{0,2}:[ \t]*([A-Za-z-]+)", re.MULTILINE)
FIRST_SEEN_RE = re.compile(r"^First-Seen:[ \t]*(\d{4}-\d{2}-\d{2})", re.MULTILINE)
MOVED_TO_RE = re.compile(r"^Moved-To:[ \t]*(\S+)[ \t]*$", re.MULTILINE)
REMOVED_WHY_RE = re.compile(r"^Removed-Why:[ \t]*(\S.*)$", re.MULTILINE)
BLOB_RE = re.compile(r"^Full-Text-Blob:[ \t]*([0-9a-f]{40})[ \t]*$", re.MULTILINE)

#: A plan path in prose, the four folders included. `wl_planrec.PLAN_REF_RE` is
#: the canonical one and learns the same alternation; this copy exists because a
#: gate under `.ci` must answer on a checkout where `.claude/` is absent, and
#: `test_quality_plan_lifecycle.py` compares the two in both directions. A mirror
#: nobody compares is just a second regex.
PLAN_REF_RE = re.compile(r"\bagent/(?:plans/(?:_done/|_removed/)?)?PLAN-[A-Za-z0-9._-]+\.md\b")

#: The word a stub carries in its `Status:` line. Deliberately NOT a member of
#: `wl_planfile.FINISHED_STATES`: a stub is not a finished plan, it is a pointer,
#: and every reader drops it at the enumeration rather than filtering it later.
STUB_STATUS = "moved"

#: The word that puts a plan in `_removed/`. It is the only state declared
#: explicitly rather than inferred, because withdrawing a plan is a decision and
#: an inferred one would be a guess about intent.
REMOVED_STATUS = "removed"

#: States a plan may carry that mean "finished". Restated rather than imported
#: for the same reason `plan_housekeeping.record_states` restates its vocabulary:
#: this module runs in a checkout where `.claude/` may be absent. The mirror is
#: compared against `wl_planfile.FINISHED_STATES` in both directions by
#: `test_quality_plan_lifecycle.py`.
FINISHED_STATES = frozenset(
    {
        "done",
        "superseded",
        "landed",
        "shipped",
        "merged",
        "implemented",
        "complete",
        "completed",
        "closed",
        "obsolete",
        "abandoned",
        "dropped",
        "cancelled",
        "canceled",
        "withdrawn",
        "archived",
        "historical",
        "compacted",
    }
)

NOT_STARTED_STATES = frozenset(
    {
        "draft",
        "design",
        "designed",
        "proposal",
        "proposed",
        "idea",
        "sketch",
        "rfc",
        "exploratory",
        "deferred",
        "rejected",
        "parked",
    }
)

#: A plan whose text has been compacted into a blob. Governed by
#: `check:ci-plan-housekeeping` and `check:ci-plan-record`, never by the 90-day
#: sweeper: deleting the pointer would orphan the blob that holds the only copy
#: of the text, which is the one outcome this whole file exists to prevent.
RECORD_STATES = frozenset({"compacted", "parked"})

STATE_ACTIVE = "active"
STATE_BACKLOG = "backlog"
STATE_RECORD = "record"
STATE_DONE = "done"
STATE_REMOVED = "removed"
STATE_STUB = "stub"

TERMINAL_STATES = frozenset({STATE_DONE, STATE_REMOVED})


# --------------------------------------------------------------------------- The data, and the pure functions over it.


@dataclasses.dataclass(frozen=True)
class Plan:
    """One plan file, as the gate sees it. Parsed text plus injected clocks.

    `moved_at`, `last_commit` and `move_commit` arrive from the ledger and from git rather than from the text, so a control can set them directly and assert a clock finding without staging a repository.
    """

    rel: str
    status: str
    first_seen: str = ""
    moved_to: str = ""
    removed_why: str = ""
    blob: str = ""
    title: str = ""
    moved_at: str = ""
    last_commit: str = ""
    move_commit: str = ""


@dataclasses.dataclass(frozen=True)
class Tombstone:
    """An expired plan: no file, a row, and a blob that still resolves."""

    rel: str
    title: str
    first_seen: str
    expired_at: str
    blob: str


@dataclasses.dataclass(frozen=True)
class Finding:
    """One defect, with the code the controls assert on.

    The CODE is the assertable half and the MESSAGE is the readable one. A control that matched on message text would break every time the wording improved, which is how a suite stops being edited.
    """

    code: str
    rel: str
    message: str


def _head(text: str) -> str:
    return "\n".join(text.splitlines()[:HEADER_LINES])


def _title(text: str) -> str:
    """The first `# ` heading, or "". 62 of the plans in this tree name themselves that way and nothing else in a plan is a title."""
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _first(rx: re.Pattern[str], head: str) -> str:
    m = rx.search(head)
    return m.group(1).strip() if m else ""


def parse_plan(rel: str, text: str, **clocks: str) -> Plan:
    """A `Plan` from its path and its bytes. NO filesystem, NO git, NO clock."""
    head = _head(text)
    return Plan(
        rel=rel,
        status=(_first(STATUS_RE, head) or "UNKNOWN").lower(),
        first_seen=_first(FIRST_SEEN_RE, head),
        moved_to=_first(MOVED_TO_RE, head),
        removed_why=_first(REMOVED_WHY_RE, head),
        blob=_first(BLOB_RE, text),
        title=_title(text),
        moved_at=clocks.get("moved_at", ""),
        last_commit=clocks.get("last_commit", ""),
        move_commit=clocks.get("move_commit", ""),
    )


def is_stub(plan: Plan) -> bool:
    """A pointer rather than a document. Both halves are required.

    `Status: moved` alone would let a plan whose author typed the word out of the corpus, and `Moved-To:` alone would let an ordinary plan that merely cites a successor out. Together they are a shape nothing writes by accident.
    """
    return plan.status == STUB_STATUS and bool(plan.moved_to)


def looks_like_stub(probe: str) -> bool:
    """`is_stub` from the first `STUB_PROBE_BYTES` of a file.

    The cheap half, for the census path that reads sizes rather than documents. It parses the same two header lines out of a prefix, so it can differ from `is_stub` only for a file whose `Moved-To:` sits past the probe -- which the stub grammar puts on line three and the gate's F5 refuses anywhere else.
    """
    head = _head(probe)
    return (
        bool(STATUS_RE.search(head))
        and _first(STATUS_RE, head).lower() == STUB_STATUS
        and bool(MOVED_TO_RE.search(head))
    )


def folder_of(rel: str) -> str:
    """The plan directory `rel` sits in, or "" when it is not in one at all."""
    for candidate in PLAN_DIRS:
        prefix = candidate + "/"
        if rel.startswith(prefix) and "/" not in rel[len(prefix) :]:
            return candidate
    return ""


def is_plan_path(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return bool(folder_of(rel)) and name.startswith(PLAN_PREFIX) and name.endswith(PLAN_SUFFIX)


def classify(plan: Plan) -> str:
    """The lifecycle state of a plan, from its `Status:` header alone.

    Folder does not enter into it, deliberately: the state is what the plan SAYS it is, and F2 is then the disagreement between that and where the file sits. A classifier that read the folder has no disagreement left to report, because it defines it away.
    """
    if is_stub(plan):
        return STATE_STUB
    if plan.status == REMOVED_STATUS:
        return STATE_REMOVED
    if plan.status in RECORD_STATES:
        return STATE_RECORD
    if plan.status in FINISHED_STATES:
        return STATE_DONE
    if plan.status in NOT_STARTED_STATES:
        return STATE_BACKLOG
    return STATE_ACTIVE


def folder_for(state: str) -> str:
    """Where a plan in `state` belongs. A stub belongs where it already is."""
    if state == STATE_DONE:
        return DONE_DIR
    if state == STATE_REMOVED:
        return REMOVED_DIR
    if state == STATE_STUB:
        return AGENT_DIR
    return PLANS_DIR


def retention_days(state: str, config: dict) -> int | None:
    """How long a plan in `state` is kept, or None when nothing expires it.

    Active and record plans have no expiry here at all. An active plan is work in hand, and a record is governed by the compaction machinery, which owns the only copy of its text.
    """
    if state in TERMINAL_STATES:
        return int(config["terminal_days"])
    if state == STATE_BACKLOG:
        return int(config["backlog_days"])
    return None


def as_date(value: str) -> dt.date | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.date()


def last_touch(plan: Plan) -> dt.date | None:
    """The OLDER of `First-Seen:` and the last commit touching the path.

    Risk 1 of the plan in one function. `git log` does not follow renames, so a move resets `%cI`; taking the older of the two means the move cannot buy freshness, and neither can re-writing the header, because the commit date is still in the minimum.
    """
    dates = [d for d in (as_date(plan.first_seen), as_date(plan.last_commit)) if d is not None]
    return min(dates) if dates else None


def age_days(when: dt.date | None, today: dt.date) -> int | None:
    return None if when is None else (today - when).days


# --------------------------------------------------------------------------- The findings. One function per code, all pure.


def finding_f1(plans: list[Plan]) -> list[Finding]:
    """F1 -- a plan outside `agent/plans/**`.

    FATAL SINCE THE 103 MOVED. It carried a `fatal` flag for exactly one stage, so the gate could land green over a tree where every plan was still at the legacy path; the flag went with the migration rather than staying behind switched off. A stub is exempt by construction: the legacy path is exactly where a stub must be.
    """
    out = []
    for plan in plans:
        if is_stub(plan) or folder_of(plan.rel) != AGENT_DIR:
            continue
        out.append(
            Finding(
                "F1",
                plan.rel,
                "%s sits at the legacy path. A plan lives under %s/ and moves once, at "
                "close, into _done/ or _removed/, leaving a stub behind. Move it with "
                "`check_plan_folders.py --move %s`." % (plan.rel, PLANS_DIR, plan.rel),
            )
        )
    return out


def finding_f2(plans: list[Plan]) -> list[Finding]:
    """F2 -- the folder disagrees with `Status:`."""
    out = []
    for plan in plans:
        state = classify(plan)
        if state == STATE_STUB:
            continue
        here = folder_of(plan.rel)
        if here == AGENT_DIR:
            continue
        want = folder_for(state)
        if here == want:
            continue
        out.append(
            Finding(
                "F2",
                plan.rel,
                "%s carries `Status: %s`, which is %s, but sits in %s/ rather than %s/. "
                "The folder is the claim a reader trusts without opening the file, so a "
                "disagreement makes both of them worthless."
                % (plan.rel, plan.status, state, here, want),
            )
        )
    return out


def finding_f3(plans: list[Plan], config: dict, today: dt.date) -> list[Finding]:
    """F3 -- a terminal plan past `terminal_days`."""
    limit = int(config["terminal_days"])
    out = []
    for plan in plans:
        if classify(plan) not in TERMINAL_STATES or folder_of(plan.rel) not in TERMINAL_DIRS:
            continue
        age = age_days(as_date(plan.moved_at), today)
        if age is None or age <= limit:
            continue
        out.append(
            Finding(
                "F3",
                plan.rel,
                "%s moved to a terminal folder %d day(s) ago, past the %d-day retention. "
                "`check_plan_folders.py --sweep --write` deletes it and mints a tombstone "
                "row in %s carrying its title, its dates and the blob id of its full text."
                % (plan.rel, age, limit, INDEX_REL),
            )
        )
    return out


def finding_f4(plans: list[Plan], config: dict, today: dt.date) -> list[Finding]:
    """F4 -- a not-started plan untouched past `backlog_days`."""
    limit = int(config["backlog_days"])
    out = []
    for plan in plans:
        if classify(plan) != STATE_BACKLOG:
            continue
        age = age_days(last_touch(plan), today)
        if age is None or age <= limit:
            continue
        out.append(
            Finding(
                "F4",
                plan.rel,
                "%s has not been started or touched for %d day(s), past the %d-day backlog "
                "retention. Start it, close it with `Status: removed` and a `Removed-Why:`, "
                "or let the sweeper expire it into a tombstone." % (plan.rel, age, limit),
            )
        )
    return out


def finding_f5(plans: list[Plan], existing: set[str]) -> list[Finding]:
    """F5 -- a stub pointing at a stub, at itself, or at nothing.

    A chain of stubs is the failure the one-move rule exists to prevent: every hop is a file a reader opens to be told to open another, and the last hop is the only one that carries text. A stub whose target is missing is worse, because the citation it exists to keep alive resolves to a dead end.
    """
    stubs = {p.rel for p in plans if is_stub(p)}
    out = []
    for plan in plans:
        if not is_stub(plan):
            continue
        target = plan.moved_to
        if target == plan.rel:
            reason = "points at itself"
        elif target in stubs:
            reason = "points at %s, which is itself a stub" % target
        elif target not in existing:
            reason = "points at %s, which is not a file" % target
        else:
            continue
        out.append(
            Finding(
                "F5",
                plan.rel,
                "%s %s. A plan moves exactly ONCE, so a stub names the plan itself and "
                "never another pointer; a chain is a citation that resolves to a dead end."
                % (plan.rel, reason),
            )
        )
    return out


def finding_f6(plans: list[Plan], *, slack_days: int = 1) -> list[Finding]:
    """F6 -- `moved_at` disagrees with git.

    Without this the 40-day clock reads a number the mover typed, and a typed number can be back-dated to expire a plan early or forward-dated to keep one forever. The commit date of the NEW path is the unforgeable half; `moved_at` is kept anyway because `git log` stops following the path the moment a later rename touches it.
    """
    out = []
    for plan in plans:
        if folder_of(plan.rel) not in TERMINAL_DIRS:
            continue
        claimed = as_date(plan.moved_at)
        actual = as_date(plan.move_commit)
        if claimed is None or actual is None:
            continue
        drift = abs((claimed - actual).days)
        if drift <= slack_days:
            continue
        out.append(
            Finding(
                "F6",
                plan.rel,
                "%s records moved_at %s but its first commit at this path is %s, %d day(s) "
                "apart. The retention clock reads moved_at, so a drift this size is a clock "
                "nobody set by moving the file."
                % (plan.rel, plan.moved_at, plan.move_commit, drift),
            )
        )
    return out


def finding_f7(
    refs: list[tuple[str, str]], existing: set[str], tombstoned: set[str]
) -> list[Finding]:
    """F7 -- a citation resolving to neither a file nor a tombstone.

    `refs` is [(where, cited_path)]. The stub is what makes this rule cheap to satisfy: a moved plan's old path keeps resolving, so the only way to reach this finding is a path that was never written or a file deleted without a tombstone.
    """
    out = []
    for where, cited in sorted(set(refs)):
        if cited in existing or cited in tombstoned:
            continue
        out.append(
            Finding(
                "F7",
                where,
                "%s cites %s, which is neither a file nor a tombstone row in %s. A move "
                "leaves a stub and an expiry leaves a row, so a citation that resolves to "
                "neither names something that was deleted without either."
                % (where, cited, INDEX_REL),
            )
        )
    return out


def finding_f8(tombstones: list[Tombstone], resolves: set[str]) -> list[Finding]:
    """F8 -- a tombstone whose blob does not resolve.

    A tombstone is the ONLY surviving copy of an expired plan's text. A row whose blob is unreachable is a receipt for something nobody can read, which is worse than no row at all because it reads as preserved.
    """
    return [
        Finding(
            "F8",
            t.rel,
            "the tombstone for %s names blob %s, which this repository cannot resolve. The "
            "blob is the only copy of the text left; a row pointing at nothing reads as "
            "preserved and is not." % (t.rel, t.blob or "(none)"),
        )
        for t in tombstones
        if t.blob not in resolves
    ]


def finding_f9(plans: list[Plan], floor: int = MIN_PLAN_FILES) -> list[Finding]:
    """F9 -- the vacuity floor.

    Every other finding above is a statement about a corpus. An enumeration that lost the corpus produces none of them and exits green, which is indistinguishable from a tree with nothing wrong. The floor is the only thing that tells those two apart.
    """
    real = [p for p in plans if not is_stub(p)]
    if len(real) >= floor:
        return []
    return [
        Finding(
            "F9",
            "",
            "VACUOUS INPUT: %d plan file(s) enumerated across %s, floor is %d. The glob "
            "lost the corpus; refusing a verdict rather than reporting a clean layout for "
            "files nobody read." % (len(real), ", ".join(PLAN_DIRS), floor),
        )
    ]


def findings(
    plans: list[Plan],
    *,
    config: dict,
    today: dt.date,
    existing: set[str],
    refs: list[tuple[str, str]],
    tombstones: list[Tombstone],
    blob_resolves: set[str],
) -> list[Finding]:
    """Every finding, in code order. The whole verdict, and still pure."""
    vacuous = finding_f9(plans)
    if vacuous:
        return vacuous
    tombstoned = {t.rel for t in tombstones}
    return [
        *finding_f1(plans),
        *finding_f2(plans),
        *finding_f3(plans, config, today),
        *finding_f4(plans, config, today),
        *finding_f5(plans, existing),
        *finding_f6(plans),
        *finding_f7(refs, existing, tombstoned),
        *finding_f8(tombstones, blob_resolves),
    ]


# --------------------------------------------------------------------------- The stub, and the tombstone table.

STUB_BODY = (
    "This plan moved to `%s`. The stub keeps every citation of the old path resolving; a "
    "plan moves exactly once, at close. See agent/README.md for the layout."
)


#: A `PLAN:` label the plan's own heading already carries. 86 of the 103 plans in
#: this tree begin `# PLAN: ...`, and pasting that into the stub's own `# PLAN: `
#: heading produced `# PLAN: PLAN: ...` on every one of them.
TITLE_PREFIX_RE = re.compile(r"^PLAN:[ \t]*")


def stub_text(old_rel: str, new_rel: str, title: str) -> str:
    """The whole of the file left behind at `old_rel`. Five lines, one claim."""
    return "# PLAN: %s (moved)\nStatus: %s\nMoved-To: %s\n\n%s\n" % (
        TITLE_PREFIX_RE.sub("", title).strip() or old_rel.rsplit("/", 1)[-1],
        STUB_STATUS,
        new_rel,
        STUB_BODY % new_rel,
    )


TOMBSTONE_SECTION = "## Expired plans"

TOMBSTONE_HEADER = (
    """
%s

A plan whose retention ran out. The FILE is gone and the full text is the blob below, which is content-addressed and survives the rebase this repository merges with. Revive one with `check_plan_folders.py --plan-revive <path>`.

| Plan | Title | First seen | Expired | Full-Text-Blob |
|---|---|---|---|---|
"""
    % TOMBSTONE_SECTION
)

TOMBSTONE_ROW_RE = re.compile(
    r"^\|[ \t]*`(?P<rel>[^`]+)`[ \t]*\|(?P<title>[^|]*)\|(?P<seen>[^|]*)\|"
    r"(?P<expired>[^|]*)\|[ \t]*`(?P<blob>[0-9a-f]{40})`[ \t]*\|[ \t]*$",
    re.MULTILINE,
)


def render_tombstones(rows: list[Tombstone]) -> str:
    """The `## Expired plans` section of `agent/INDEX.md`, or "".

    "" IS A REAL ANSWER and an absent section equals it, exactly as `wl_planrec.render_index` treats an empty record set. A generated table with no rows is a committed document that says nothing.
    """
    if not rows:
        return ""
    body = "".join(
        "| `%s` | %s | %s | %s | `%s` |\n" % (r.rel, r.title, r.first_seen, r.expired_at, r.blob)
        for r in sorted(rows, key=lambda r: r.rel)
    )
    return (
        TOMBSTONE_HEADER
        + body
        + ("\n%d expired plan(s). The row is the receipt; the blob is the text.\n" % len(rows))
    )


def parse_tombstones(text: str) -> list[Tombstone]:
    """Rows read back out of `agent/INDEX.md`. The section is APPEND-ONLY.

    Reading the file back is what makes the section durable across a regeneration: the plans it names have no disk state left, so a render computed only from the tree would drop every row it had ever written.
    """
    return [
        Tombstone(
            rel=m.group("rel").strip(),
            title=m.group("title").strip(),
            first_seen=m.group("seen").strip(),
            expired_at=m.group("expired").strip(),
            blob=m.group("blob"),
        )
        for m in TOMBSTONE_ROW_RE.finditer(text)
    ]


# --------------------------------------------------------------------------- The impure half. Three functions, each named for its one effect.


def load_config(root: pathlib.Path) -> dict:
    """`plan-lifecycle.json`, with both retention numbers required.

    A missing key is a SETUP error at the call site rather than a default here: a default would make the number live in two places, which is precisely the deadlock the file's own comment records for `delete_days`.
    """
    return json.loads((root / DEFAULT_CONFIG_REL).read_text(encoding="utf-8"))


def repo_root() -> pathlib.Path:
    override = os.environ.get(ROOT_ENV)
    return pathlib.Path(override) if override else paths.repo_root()


def enumerate_plans(root: pathlib.Path) -> tuple[list[str], str]:
    """Every tracked-or-untracked plan path, and "" when git answered cleanly.

    THE EXIT STATUS IS KEPT. `gitx.ls_files` returns `[]` on a non-zero git, which a caller reads as "no plans" and a gate then reports as a clean layout. The failure is returned as a second value so the caller can refuse instead.
    """
    args = ["ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *PLAN_PATHSPECS]
    result = gitx.git(args, root=root)
    if not result.ok:
        return [], "git ls-files failed under %s: %s" % (root, result.stderr.strip() or "no stderr")
    found = sorted({p for p in result.stdout.split("\0") if p and is_plan_path(p)})
    return found, ""


def git_dates(root: pathlib.Path, rel: str) -> tuple[str, str]:
    """(last commit touching `rel`, first commit at `rel`) as ISO dates.

    The SECOND one is what F6 cross-checks `moved_at` against, and it is the LAST line of `git log --format=%cI -- <path>` rather than a second invocation: git prints newest first, so the oldest entry is the move that created the path.
    """
    out = gitx.git(["log", "--format=%cI", "--", rel], root=root).stdout.strip().splitlines()
    if not out:
        return "", ""
    return out[0].strip(), out[-1].strip()


def blob_resolves(root: pathlib.Path, blobs: set[str]) -> set[str]:
    """The subset of `blobs` this repository can actually produce."""
    return {
        blob
        for blob in blobs
        if blob and gitx.git(["cat-file", "-e", "%s^{blob}" % blob], root=root).ok
    }


def read_probe(path: pathlib.Path) -> str:
    """At most `STUB_PROBE_BYTES` of a file, never raising."""
    try:
        with path.open("rb") as handle:
            return handle.read(STUB_PROBE_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return ""


def ledger_rows(root: pathlib.Path) -> dict:
    try:
        return (json.loads((root / LEDGER_REL).read_text(encoding="utf-8")) or {}).get(
            "plans"
        ) or {}
    except (OSError, ValueError):
        return {}


def needs_git_dates(plan: Plan) -> bool:
    """Whether a plan's verdict depends on git at all.

    ONE `git log` PER PLAN IS THE COST, and it is the whole runtime of this gate: 103 subprocesses is five seconds where the verdict needs twelve of them. A backlog plan needs the last-commit half of its 90-day clock, a plan in a terminal folder needs the first-commit half of F6, and nothing else in the file reads either date. Asking here rather than fetching unconditionally is
    not a micro-optimisation: a gate slow enough to be moved into a nightly lane is a gate that stops being read on the change that breaks it.
    """
    return classify(plan) == STATE_BACKLOG or folder_of(plan.rel) in TERMINAL_DIRS


def load_plans(root: pathlib.Path, rels: list[str], ledger: dict) -> list[Plan]:
    """`Plan` objects for `rels`, with the clocks filled in from git and the ledger."""
    out = []
    for rel in rels:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        row = ledger.get(rel) or {}
        plan = parse_plan(rel, text, moved_at=str(row.get("moved_at") or ""))
        if needs_git_dates(plan):
            last, first = git_dates(root, rel)
            plan = dataclasses.replace(plan, last_commit=last, move_commit=first)
        out.append(plan)
    return out


def citation_refs(root: pathlib.Path) -> list[tuple[str, str]]:
    """[(where, cited)] from the ledger keys and from `agent/INDEX.md`.

    Those two are the places the plan names for F7 because both are GENERATED: a generated file citing a path that does not exist is a generator reading a tree nobody else can see, which is a louder defect than the same citation in prose.
    """
    refs: list[tuple[str, str]] = [(LEDGER_REL, key) for key in ledger_rows(root)]
    try:
        text = (root / INDEX_REL).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return refs
    refs.extend((INDEX_REL, m.group(0)) for m in PLAN_REF_RE.finditer(text))
    return refs


__all__ = [
    "AGENT_DIR",
    "DONE_DIR",
    "PLANS_DIR",
    "PLAN_PATHSPECS",
    "PLAN_REF_RE",
    "REMOVED_DIR",
    "STUB_STATUS",
    "Finding",
    "Plan",
    "Tombstone",
    "as_date",
    "classify",
    "enumerate_plans",
    "findings",
    "folder_for",
    "folder_of",
    "is_plan_path",
    "is_stub",
    "last_touch",
    "looks_like_stub",
    "parse_plan",
    "parse_tombstones",
    "render_tombstones",
    "retention_days",
    "stub_text",
]
