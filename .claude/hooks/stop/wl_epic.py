"""Epics: a label over N worklist items, for PR structure and per-epic review.

WHY A SIDECAR AND NOT AN EVENT KIND. `compact()` in wl_store.py rewrites the event log down to the minimal item-reproducing set (md, add, lease), so a novel event kind there is SILENTLY DESTROYED. `record_intent` already learned this and says so at its own definition; `.intents` is the precedent this follows. An epic that vanished on the next compact would take a
PR's whole structure with it, and the failure would look like an empty section rather than an error.

WHY EPICS ARE NOT WORKLIST ITEMS. `wl_planfid.is_umbrella()` actively refuses an item that stands for several tasks ("Waves B-D", "phases 1 through 3"), because one item covering many tasks is how work goes untracked. An epic is a LABEL OVER items, never an item: the items stay individually tracked, ticked and evidenced, and the epic only groups them for rendering and review.

WHAT AN EPIC IS FOR. Two consumers, and both need the same grouping:
  1. the PR body, which gets one section per epic so a reader can see which
     change belongs to which task;
  2. the review, which runs once per epic against only that epic's commits, so a
     big-bang PR cannot starve one task's review by crowding it out.

IDS ARE NOT FIXED WIDTH. Worklist item ids are 8 hex from the CLI and 12 hex when migrated from the old markdown. Never parse assuming a width.
"""

import datetime
import json
import os
import pathlib
import re
import subprocess

import wl_core as C
import wl_store as S

EPIC_MAX_CHARS = 200
EPIC_MAX_COVERS = 64


def epics_path():
    """The DURABLE epic sidecar, `agent/worklist/epics.jsonl`.

    IT WAS `worklist.with_suffix(".epics")` AND THAT WAS THE WHOLE BUG. W12 P3.1a is recorded as "the TMPDIR sidecar moved into agent/worklist/" and the code read as if it had, because the durable-looking derivation hid where the argument actually points: `worklist` is the LEGACY markdown mirror, which lives at $TMPDIR/claude-worklist/<slug>.md. So the epics rode along in /tmp, and
    a /tmp clear between branches deleted them.

    Measured 2026-09-06, and it was not hypothetical. Eighteen commits on branch 0906-1 carry `PR-TASK: 24c98380`, an epic whose definition was gone: `check:ci-pr-task-trailers` reported them as naming no epic in the snapshot, which means the review would have covered none of them. The title survived only because a PREVIOUS branch's rendered snapshot, agent/pr/0903-1.md, is
    tracked. A generated view outliving its source is not a recovery plan.

    Repo-scoped, not per-session: an epic is a label many sessions attach items to, and it always behaved that way (one file, whoever wrote it). The `worklist` argument is GONE rather than kept and ignored, because a parameter nothing reads is the next reader's false lead about where this resolves from.
    """
    return S.store_dir() / "epics.jsonl"


def _new_epic_id(existing):
    """Short, collision-checked. Same shape as a CLI item id, 8 hex."""
    for _ in range(64):
        cand = os.urandom(4).hex()
        if cand not in existing:
            return cand
    raise RuntimeError("could not mint a distinct epic id")


PLAN_DIR = "agent/plans/"


def plan_rel_problem(rel, root=None):
    """Why `rel` cannot be an epic's plan, or "" when it can.

    The plan is how the Stop hook scopes items to the live PR (agent/plans/PLAN-stop-hook-one-plan-scope.md, Design 3), so a typo here would silently attach an epic to no plan at all and queue every item under it. A rel must be a repo-relative `agent/plans/....md` that exists, and must not climb out of `agent/plans/`.
    """
    rel = str(rel or "")
    if not rel.startswith(PLAN_DIR) or not rel.endswith(".md"):
        return "a plan is a repo-relative %s<name>.md path, not %r" % (PLAN_DIR, rel)
    if root is None:
        root = C.project_root(C.project_start())
    base = (pathlib.Path(root) / PLAN_DIR).resolve()
    target = (pathlib.Path(root) / rel).resolve()
    if base not in target.parents:
        return "%r leaves %s" % (rel, PLAN_DIR)
    if not target.is_file():
        return "no plan file %s under %s" % (rel, root)
    return ""


def record_epic(me, epic_id, title, covers, order=None, plan=None):
    """Append one epic record. Append-only, like every sidecar here.

    `plan` is written only when given: `load_epics` merges non-None fields later-wins, so a record that omits it (a later `add`) keeps the plan an earlier record set.
    """
    rec = {
        "at": C.stamp_now(),
        "by": (me or "")[:8],
        "id": epic_id,
        "title": (title or "")[:EPIC_MAX_CHARS],
        "covers": sorted({c for c in (covers or []) if c})[:EPIC_MAX_COVERS],
        "order": order,
    }
    if plan:
        rec["plan"] = str(plan)
    S._append_lines(epics_path(), str(epics_path()) + ".lock", [rec])


def load_epics():
    """{epic_id: record}, later lines winning, ordered by `order` then first-seen.

    A torn or malformed line is SKIPPED, never fatal: the same rule the event reader follows, because a crash mid-append must not make the whole file unreadable.
    """
    p = epics_path()
    if not p.exists():
        return {}
    out, seen = {}, []
    try:
        rows = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    for line in rows:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        eid = str(rec.get("id") or "")
        if not eid:
            continue
        if eid not in out:
            seen.append(eid)
        prev = out.get(eid) or {}
        merged = dict(prev)
        merged.update({k: v for k, v in rec.items() if v is not None})
        # `minted` is the FIRST record's stamp; `at` is later-wins like every other field, so it moves on every `add` and cannot say when the epic was born. `pr_epic_ids` reads this to keep a minted-but-not-yet-cited epic on the branch that minted it.
        merged["minted"] = prev.get("minted") or rec.get("at") or ""
        # covers ACCUMULATE across records: `--epic add` is additive, so a later line naming one more item must not drop the ones named before it.
        merged["covers"] = sorted(set(prev.get("covers") or []) | set(rec.get("covers") or []))
        out[eid] = merged
    ordered = sorted(
        out.values(),
        key=lambda r: (
            r.get("order") if r.get("order") is not None else 10**6,
            seen.index(r["id"]),
        ),
    )
    return {r["id"]: r for r in ordered}


def new_epic(me, title, order=None, plan=None):
    existing = set(load_epics())
    eid = _new_epic_id(existing)
    record_epic(me, eid, title, [], order, plan=plan)
    return eid


def set_plan(me, epic_id, rel):
    """Give an existing epic its plan (later-wins). Refuses an unknown epic by returning None; the caller validates `rel` first."""
    epics = load_epics()
    if epic_id not in epics:
        return None
    rec = epics[epic_id]
    record_epic(me, epic_id, rec.get("title"), [], rec.get("order"), plan=rel)
    return epic_id


def plan_epics(rel):
    """Every item id covered by an epic whose `plan` is `rel`.

    Titles are NEVER parsed (clean break, Design 3): an epic whose title names a plan but which carries no `plan` field belongs to no plan until `--epic <me> plan` gives it one.
    """
    out: set[str] = set()
    for rec in load_epics().values():
        if rec.get("plan") == rel:
            out.update(rec.get("covers") or [])
    return out


def add_to_epic(me, epic_id, item_ids):
    """Attach items to an existing epic. Refuses an unknown epic."""
    epics = load_epics()
    if epic_id not in epics:
        return None
    record_epic(me, epic_id, epics[epic_id].get("title"), item_ids, epics[epic_id].get("order"))
    return epic_id


def neutralize(text):
    """Defang HTML comment delimiters in text destined for a PR body.

    THIS IS NOT COSMETIC. The PR body carries managed blocks delimited by HTML comments, and an item whose own text contains `-->` would TERMINATE the block early, silently truncating every section after it. Found immediately: the worklist item tracking this very feature had `<!-- worklist-epics:begin/end -->` in its title, because that is what the task is called.

    Zero-width-space between the characters keeps the text readable to a human
    while making it inert to an HTML parser.
    """
    return (text or "").replace("<!--", "<\u200b!--").replace("-->", "--\u200b>")


# ---- the PR's own epics, read from the branch's commits ---------------------------------------
# WHY THE BLOCK IS SCOPED (operator request 2026-10-07). `render` used to print EVERY epic the ledger ever minted, with every covered item, so each PR repeated all earlier PRs' finished work and agent/pr/1006-3.md carried 20 epic sections. A PR body that grows with the repo's age stops telling a reviewer which change belongs to which task, which is the one thing it exists to say.

# The trailer shape check:ci-pr-task-trailers reads (`trailerIds` in scripts/gates/check-pr-task-trailers.ts): a line of its own, optional indent. Reading the WHOLE message rather than git's `%(trailers)` keeps the two readers agreeing on a trailer git's parser would not count (a non-final paragraph).
TRAILER_RE = re.compile(
    r"^[ \t]*PR-TASK:[ \t]*([0-9a-f]{6,32})[ \t]*$", re.MULTILINE | re.IGNORECASE
)

# Tried in order. origin/main first because a local `main` is routinely stale in a worktree; `main` second so a fixture repo with no remote still has a base.
BASE_REFS = ("origin/main", "main")


def _git(root, *args):
    """(rc, stdout). A git that is missing or hangs answers rc 127, never an exception: the caller turns a failure into a NAMED problem, it never crashes the publish."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return proc.returncode, proc.stdout


def _resolves(root, ref):
    return _git(root, "rev-parse", "--verify", "--quiet", "%s^{commit}" % ref)[0] == 0


def branch_epics(root, branch):
    """(cited, fork_at, problem) for `branch` against the first base in BASE_REFS that resolves.

    `cited` is every `PR-TASK:` id the branch's own commits (`<base>..<branch>`) carry, first-seen order. `fork_at` is the merge-base's committer time as an ISO8601Z stamp, "" when unknown. `problem` is "" when the range was read, otherwise WHY it was not: an unread range is UNKNOWN, and the caller must say so rather than present an empty epic list as "this PR cites nothing".
    """
    if not _resolves(root, branch):
        return [], "", "branch %r does not resolve in %s" % (branch, root)
    base = next((b for b in BASE_REFS if _resolves(root, b)), "")
    if not base:
        return [], "", "no base ref resolves (tried %s)" % ", ".join(BASE_REFS)
    rc, out = _git(root, "log", "--format=%B%x00", "%s..%s" % (base, branch))
    if rc != 0:
        return [], "", "git log %s..%s exited %d" % (base, branch, rc)
    cited: list[str] = []
    for raw in TRAILER_RE.findall(out):
        eid = raw.lower()
        if eid not in cited:
            cited.append(eid)
    fork_at = ""
    rc, mb = _git(root, "merge-base", base, branch)
    if rc == 0 and mb.strip():
        rc, ct = _git(root, "show", "-s", "--format=%ct", mb.strip())
        if rc == 0 and ct.strip().isdigit():
            fork_at = datetime.datetime.fromtimestamp(int(ct.strip()), datetime.UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
    return cited, fork_at, ""


def pr_epic_ids(epics, cited, fork_at=""):
    """The PR's own epics, in ledger order: every epic the branch's commits cite, plus every epic MINTED after the branch forked.

    WHY THE SECOND HALF. block_untagged_commit validates a new commit's `PR-TASK:` against the ids this snapshot declares, so an epic minted for this branch but not yet cited by any commit must already be declared, or the commit that would first cite it is refused for naming "no epic on this branch". Minted-after-fork is that set, read off the ledger's own stamps (no PR body, no network), and on this repo's one-live-branch model nothing else mints epics in the meantime.

    A cited id the ledger does not know is NOT rendered here: a section with no ledger record behind it is what check:ci-pr-task-trailers refuses as hand-edited. `unknown_cited` names those for the caller to report.
    """
    cited = set(cited or ())
    return [
        eid
        for eid, rec in epics.items()
        if eid in cited or (fork_at and str(rec.get("minted") or "") >= fork_at)
    ]


def unknown_cited(epics, cited):
    return [e for e in (cited or ()) if e not in epics]


# THE BACKLOG HEADING IS A CONTRACT, not a label. scripts/gates/check-pr-epic-block.ts refuses a snapshot or PR body without a line matching `### Open system backlog (<N>)` whose N equals the entries listed under it; change it in both places or the gate goes red.
BACKLOG_TITLE = "Open system backlog"
BACKLOG_NONE = "_none_"
BACKLOG_FRAME = (
    "_Every open worklist item outside this PR's epics: the repository's improvement queue,"
    " shown on every PR so it stays visible. Not this PR's work._"
)


def _item_line(r, iid, tag=""):
    """One item, one line. `tag` sits BEFORE the text: brief_text truncates, and a tag after a cut-off parenthetical reads as part of it."""
    return "- [%s] `#%s` %s%s" % (
        r.get("state", " "),
        iid,
        tag,
        neutralize(S.brief_text(r, cap=200)),
    )


def backlog_items(fold, pr_epics, epics=None):
    """Every item with state != x that no epic in `pr_epics` covers, fold order. One definition, so the publish line's count and the rendered heading's N cannot disagree."""
    epics = load_epics() if epics is None else epics
    owned: set[str] = set()
    for eid in pr_epics:
        owned.update((epics.get(eid) or {}).get("covers") or [])
    return [r for r in fold.items if r["id"] not in owned and r.get("state") != "x"]


def render(fold, pr_epics, heading="###"):
    """Markdown in two parts: this PR's epics in full, then the open system backlog.

    `pr_epics` is the ordered list of epic ids this PR owns (`pr_epic_ids`). Each gets its section with EVERY covered item, ticked and open, because a reviewer reads the finished work too. An epic this PR does not own is not rendered at all, finished or not; its OPEN items reach the backlog with the epic named inline.

    The backlog is MANDATORY: it renders on every PR, with `_none_` when empty, because a section that appears only when non-empty is indistinguishable from one a render regression dropped. It lists every item with state != x that no PR epic covers.

    Uses wl_store.brief_text, the v14 display identity (what the item FIRST said plus its LATEST note), never rec["text"] which accumulates every update note forever and would put twenty concatenated lines into a PR body.
    """
    epics = load_epics()
    items = {r["id"]: r for r in fold.items}
    lines, claimed = [], set()
    for eid in pr_epics:
        rec = epics.get(eid)
        if rec is None:
            continue
        lines.append("%s %s" % (heading, neutralize(rec.get("title")) or "(untitled)"))
        lines.append("")
        lines.append("`PR-TASK: %s`" % eid)
        lines.append("")
        covered = [i for i in (rec.get("covers") or []) if i in items]
        if not covered:
            lines.append("_no tracked items yet_")
        for iid in covered:
            claimed.add(iid)
            lines.append(_item_line(items[iid], iid))
        lines.append("")
    # Which OTHER epics an open item sits in, named inline so a reader can tell a stray item from one parked under another task.
    home: dict[str, list[str]] = {}
    for eid, rec in epics.items():
        if eid in pr_epics:
            continue
        for iid in rec.get("covers") or []:
            home.setdefault(iid, []).append(eid)
    backlog = backlog_items(fold, pr_epics, epics)
    lines.append("%s %s (%d)" % (heading, BACKLOG_TITLE, len(backlog)))
    lines.append("")
    lines.append(BACKLOG_FRAME)
    lines.append("")
    if not backlog:
        lines.append(BACKLOG_NONE)
    for r in backlog:
        where = home.get(r["id"]) or []
        tag = "(epic %s) " % ", ".join("`%s`" % e for e in where) if where else ""
        lines.append(_item_line(r, r["id"], tag))
    return "\n".join(lines).rstrip() + "\n"
