"""check:ci-retired-terms -- open work must not plan around a feature that has been retired.

WHY THIS EXISTS. On 2026-10-15 rclone was ordered removed completely, and worklist item #fcd7316f ("bake rclone into the E2E VM image") stayed OPEN beside that order: a queued unit of work whose subject no longer exists. Nothing connects a retirement to the work already queued against it, so the stale item survives until a human happens to read it. The operator's ask (#1201d7b9): "If an open worklist item can be matched against retired features (e.g. a retired-terms list containing rclone), flag that too."

THE RULE. `.ci/config/retired-terms.json` lists retired terms, each with a pattern, a date, a reason and `retired_by`: the plans and worklist items doing the retiring. A SUBJECT is an OPEN worklist item (state ' ', '?' or '>'), a LIVE plan (active or backlog, outside `_done/` and `_removed/`, not a stub, not a compaction record), or a FILE tracked by a checked-out submodule. An item or a plan naming a retired term is a finding UNLESS its text cites one of that term's `retired_by` references, or it IS one of them: the work doing the retiring has to name the thing it retires. A file gets no such excuse, because a file is the shipped system itself rather than a plan for changing it.

THE FILE SUBJECT. Every submodule `.gitmodules` declares (`gitx.submodules`, never a hardcoded list) passes through `common.require_submodule` on its `.git` marker: absent under `CI=true` is CANNOT RUN (rc 2), absent locally prints `NOT CHECKED <path>` and the run continues without it. A checked-out submodule's files are `git -C <sm> ls-files -s -z`, keyed `<sm path>/<rel>`; symlinks, gitlinks and binary files (a NUL in the first 4096 bytes) are skipped. Zero declared submodules, or a checked-out submodule listing zero files, is CANNOT RUN. The shape line `N submodule(s) declared, M checked out, F file(s) read; NOT CHECKED: ...` prints every run. The file half never runs under `--owner`, which is the Stop hook's per-session call and judges items only.

A FILE FINDING IS A COUNT, keyed (path, term id) and never a line number, so a paragraph moving above a hit does not re-key it. `file_baseline` entries `{path, term, count, blocker}` are SHRINK-ONLY debt: a count above its ceiling, or a pair with no entry, is NEW; a count below its ceiling is STALE until drained; an entry under a NOT CHECKED submodule is SKIPPED and printed. `file_exclusions` entries `{prefix, blocker}` drop a whole subtree (append-only applied migrations), and a prefix that matches no tracked file of a checked-out submodule is CANNOT RUN, so an exclusion cannot outlive what it excuses.

THE MARKER, `retired-term-ok(<term id>): <reason>`, on the line it excuses, under any comment leader (a trailing `-->` or `*/` is stripped from the reason). It suppresses only the named term on that line, and only in files. It is refused (rc 1) when the reason is missing or empty, when `allowlist.validate_reason` rejects the reason, when the term id names no term, and when it is DEAD: the line before the marker no longer names its term. It carries a reason where `style-ok` and `slop-ok` do not, because it excuses a retired thing rather than a style choice.

WHERE IT REFUSES AND WHERE IT ADVISES, and the split follows ownership:

  * ITEMS ADVISE IN CI. The worklist store is shared by every session, and CLAUDE.md
    rule 2 forbids ticking or editing another session's item. A refusal in CI would
    turn every PR red over an item its author is not allowed to close, which is a
    deadlock rather than a gate. So CI prints each item finding with its owner, loudly,
    and exits on the plans alone. `--owner <prefix>` is the refusing form: it judges
    only that session's items, which is the one place the finding is actionable, and
    is the call the Stop hook makes for the session that is stopping.
  * PLANS REFUSE IN CI. A plan is a committed document any session may edit, and a
    plan naming a retired term is a document defect with a one-line fix: cite the
    retirement, or drop the stale step. The plans that already did so when this gate
    landed are a SHRINK-ONLY baseline keyed on (plan path, term id), never on a line
    number: a NEW pair refuses, and a baselined pair that stopped firing refuses until
    it is drained with `--write-baseline`, which can only remove.
  * FILES REFUSE IN CI, against `file_baseline`. `--write-baseline` lowers a count to
    what fires and removes an entry that reached zero; it never raises one and never
    adds one, and it refuses while any submodule is NOT CHECKED, because a drain
    judged without a submodule would read that submodule's debt as fixed.

THE IDENTITY OF A SUBJECT IS ITS OWN CITATION. An item whose id appears in `retired_by`, and a plan whose stem does, are the retirement itself and are never findings. A path in `retired_by` is matched by its STEM (`PLAN-backup-program`), because a plan moves exactly once at close, from `agent/plans/` into `_done/`, and a citation must survive that move.

ANTI-VACUITY, in the gate rather than in anybody's memory of having checked:

  * the controls run first on every invocation and the verdict is refused if any
    fails. They plant subjects in both directions against the SHIPPED patterns, and
    write a closed item and an open one through the real `wl_store` writer verbs into
    a scratch store, so "a closed item is ignored" is proven through the real fold;
  * every pattern runs its own `must_match` and `must_not_match` texts first, so a
    pattern edited into matching nothing, or into matching the live
    `ACCOUNT_BACKUP_S3_*` family, is refused before it judges anything;
  * a store that folds zero items, a plan corpus with zero live plans, a `.gitmodules`
    declaring zero submodules, or a checked-out submodule listing zero files, is
    CANNOT RUN, never a clean tree;
  * every `retired_by` reference must resolve: a path to a file in the tree, an item
    id to an item in the store. An unresolvable citation would excuse any text that
    happens to repeat it.

READING ANOTHER CHECKOUT. `--root <path>` judges that tree's plans, that tree's store and that tree's submodules (the store directory is pinned through `WORKLIST_STORE_DIR`, the override `wl_store.store_dir` documents for exactly this), so a disposable clone can measure the live checkout without writing to it. The fold is `wl_store.load(..., sync=False)`, which never writes, and `wl_store` itself always comes from THIS checkout, the instrument. `--config <path>` swaps the term list, which is how the pytest module drives fixture terms against fixture trees; `--write-baseline` refuses all three flags, because a drain judged against another tree must not rewrite this one's baseline.

THE STOP HOOK'S CALL, described rather than wired here: `.ci/scripts/quality/check_retired_terms.py --owner <session prefix>` from the stop checks, as a blocking check for the stopping session. It exits 1 only on that session's own open items, which is the one refusal a session can always act on (withdraw the item, or cite the retirement it belongs to).
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import importlib
import json
import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import gitx, log, paths, proc
from rediacc_ci.controls import Checker, controls_first, fixture_git_env, git_isolated, plant
from rediacc_ci.core import allowlist, common
from rediacc_ci.quality import plan_lifecycle as PL
from rediacc_ci.quality import shrink_only

CONFIG_REL = ".ci/config/retired-terms.json"
WORKLIST_REL = "agent/worklist.md"
STORE_REL = "agent/worklist"

#: The open states. '[x]' is done and '~' is removed; neither is queued work.
OPEN_STATES = frozenset({" ", "?", ">"})

#: Plan states that are queued work. A stub is a pointer, a record is compacted history, and done or removed are terminal.
LIVE_PLAN_STATES = frozenset({PL.STATE_ACTIVE, PL.STATE_BACKLOG})

ID_REF_RE = re.compile(r"^#([0-9a-f]{6,16})$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MIN_REASON = 20


class CannotRunError(Exception):
    """The instrument cannot produce a verdict: config, store or corpus is unusable."""


@dataclasses.dataclass(frozen=True)
class Term:
    id: str
    regex: re.Pattern[str]
    retired: str
    reason: str
    retired_by: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Subject:
    """One thing that could be planning work: an item (`#<id>`) or a plan (its path)."""

    kind: str  # "item" | "plan"
    key: str  # "#<id>" for an item, the repository-relative path for a plan
    text: str
    owner: str = ""


@dataclasses.dataclass(frozen=True)
class Finding:
    subject: Subject
    term: Term
    excerpt: str


# --------------------------------------------------------------------------- the pure core


def ref_token(ref: str) -> re.Pattern[str]:
    """The citation a subject must carry for `ref`.

    `#<hex>` is an item id and matches with or without the `#`; a path matches by its stem, so a plan cited before and after its move to `_done/` is the same citation.
    """
    m = ID_REF_RE.match(ref)
    if m:
        return re.compile(r"(?<![0-9A-Za-z])%s(?![0-9A-Za-z])" % re.escape(m.group(1)))
    stem = ref.rsplit("/", 1)[-1]
    stem = stem.removesuffix(".md")
    return re.compile(r"(?<![0-9A-Za-z-])%s(?![0-9A-Za-z-])" % re.escape(stem))


def subject_identity(subject: Subject) -> str:
    """The token a subject's OWN key would cite: the item id, or the plan's stem."""
    if subject.kind == "item":
        return subject.key.lstrip("#")
    return subject.key.rsplit("/", 1)[-1].removesuffix(".md")


def cites_retirement(subject: Subject, term: Term) -> bool:
    ident = subject_identity(subject)
    for ref in term.retired_by:
        token = ref_token(ref)
        if token.search(subject.text) or token.fullmatch(ident):
            return True
    return False


def excerpt(text: str, m: re.Match[str], width: int = 60) -> str:
    lo = max(0, m.start() - width)
    hi = min(len(text), m.end() + width)
    out = text[lo:hi].replace("\n", " ")
    return ("..." if lo else "") + out + ("..." if hi < len(text) else "")


def judge(subjects: list[Subject], terms: list[Term]) -> list[Finding]:
    """Every (subject, term) where the subject names the term and cites none of its retirements."""
    out = []
    for subject in subjects:
        for term in terms:
            m = term.regex.search(subject.text)
            if m and not cites_retirement(subject, term):
                out.append(Finding(subject, term, excerpt(subject.text, m)))
    return out


def parse_terms(doc: dict) -> tuple[list[Term], list[str]]:
    """The terms, and every reason the config cannot be trusted. Pure: no tree, no store."""
    problems: list[str] = []
    terms: list[Term] = []
    raw = doc.get("terms")
    if not isinstance(raw, list) or not raw:
        return [], [
            "%s has no `terms` list; a gate with nothing to look for passes everything" % CONFIG_REL
        ]
    seen: set[str] = set()
    today = dt.datetime.now(dt.UTC).date().isoformat()
    for i, entry in enumerate(raw):
        where = "terms[%d]" % i
        tid = str(entry.get("id") or "")
        if not tid:
            problems.append("%s has no id" % where)
            continue
        where = "term %r" % tid
        if tid in seen:
            problems.append("%s is listed twice" % where)
        seen.add(tid)
        flags = 0 if entry.get("case_sensitive") is True else re.IGNORECASE
        if not isinstance(entry.get("case_sensitive"), bool):
            problems.append("%s must state case_sensitive as true or false" % where)
        try:
            regex = re.compile(str(entry.get("pattern") or ""), flags)
        except re.error as exc:
            problems.append("%s: pattern does not compile (%s)" % (where, exc))
            continue
        if not regex.pattern:
            problems.append("%s has an empty pattern, which matches every subject" % where)
            continue
        retired = str(entry.get("retired") or "")
        if not DATE_RE.match(retired) or retired > today:
            problems.append(
                "%s: retired %r is not an ISO date on or before today" % (where, retired)
            )
        reason = str(entry.get("reason") or "")
        if len(reason) < MIN_REASON:
            problems.append(
                "%s: reason must say why the term is gone (%d+ chars)" % (where, MIN_REASON)
            )
        retired_by = tuple(str(r) for r in entry.get("retired_by") or [])
        if not retired_by:
            problems.append(
                "%s: retired_by is empty, so nothing could ever cite the retirement" % where
            )
        positives = list(entry.get("must_match") or [])
        negatives = list(entry.get("must_not_match") or [])
        if not positives or not negatives:
            problems.append("%s needs both must_match and must_not_match texts" % where)
        problems.extend(
            "%s: pattern does not match its own must_match text %r" % (where, t)
            for t in positives
            if not regex.search(t)
        )
        problems.extend(
            "%s: pattern matches its must_not_match text %r" % (where, t)
            for t in negatives
            if regex.search(t)
        )
        terms.append(Term(tid, regex, retired, reason, retired_by))
    return terms, problems


def unresolved_refs(
    terms: list[Term], tracked: set[str], item_ids: set[str]
) -> tuple[list[str], list[str]]:
    """(paths that name no file, item ids that name no item in the store).

    THE TWO ARE JUDGED DIFFERENTLY ON PURPOSE. A path is committed with the config, so one that resolves nowhere is a config defect and refuses. An item id is written into the store by the session that tracks the retirement, and the store is a record path that can be committed after the config: refusing on it would turn CI red for the ordering of two commits, so an unresolved id is reported and the run continues. A hex id of six to sixteen digits (ID_REF_RE) is unlikely to recur by accident, so the excuse it grants stays narrow either way.
    """
    missing_paths, missing_ids = [], []
    for term in terms:
        for ref in term.retired_by:
            m = ID_REF_RE.match(ref)
            if m:
                if m.group(1) not in item_ids:
                    missing_ids.append(
                        "term %r: retired_by %s is no item in the store" % (term.id, ref)
                    )
            elif ref not in tracked:
                missing_paths.append(
                    "term %r: retired_by %s is no file in the tree" % (term.id, ref)
                )
    return missing_paths, missing_ids


def baseline_pairs(doc: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """The baselined (plan, term) pairs, and every entry whose BLOCKER reason is refused."""
    pairs: list[tuple[str, str]] = []
    problems: list[str] = []
    for i, entry in enumerate(doc.get("plan_baseline") or []):
        plan, term = str(entry.get("plan") or ""), str(entry.get("term") or "")
        if not plan or not term:
            problems.append("plan_baseline[%d] needs both plan and term" % i)
            continue
        blocker = str(entry.get("blocker") or "")
        rejection = None
        if not blocker.startswith("BLOCKER:"):
            problems.append("plan_baseline %s/%s carries no `BLOCKER:` reason" % (plan, term))
        else:
            rejection = allowlist.validate_reason(
                "%s %s" % (plan, term), blocker.removeprefix("BLOCKER:").strip(), CONFIG_REL
            )
        if rejection is not None:
            problems.append(rejection.message)
        pairs.append((plan, term))
    return pairs, problems


def plan_verdict(
    findings: list[Finding], baseline: list[tuple[str, str]]
) -> tuple[list[Finding], list[Finding], list[tuple[str, str]]]:
    """(new, baselined, stale): the plan findings split against the shrink-only baseline."""
    known = set(baseline)
    plan_findings = [f for f in findings if f.subject.kind == "plan"]
    firing = {(f.subject.key, f.term.id) for f in plan_findings}
    new = [f for f in plan_findings if (f.subject.key, f.term.id) not in known]
    held = [f for f in plan_findings if (f.subject.key, f.term.id) in known]
    stale = [pair for pair in baseline if pair not in firing]
    return new, held, stale


def owned(owner: str, prefix: str) -> bool:
    return bool(owner) and bool(prefix) and (owner.startswith(prefix) or prefix.startswith(owner))


# --------------------------------------------------------------------------- the file subject, pure

MARKER_OPENER = "retired-term-ok("
MARKER_RE = re.compile(r"retired-term-ok\((?P<term>[^)]*)\)(?P<rest>.*)$")
#: A comment closer after the reason, stripped so `<!-- retired-term-ok(t): why -->` reads as `why`.
MARKER_TRAILER_RE = re.compile(r"\s*(?:-->|\*/)\s*$")

#: (path, term id) -> the 1-based line number of every counted hit. The count is `len`.
FileHits = dict[tuple[str, str], list[int]]


def parse_marker(line: str) -> tuple[str, str, int] | None:
    """(term id, reason, column where the marker starts), or None when the line carries no marker."""
    m = MARKER_RE.search(line)
    if not m:
        return None
    rest = m.group("rest")
    reason = MARKER_TRAILER_RE.sub("", rest[1:]).strip() if rest.startswith(":") else ""
    return m.group("term").strip(), reason, m.start()


def scan_text(key: str, text: str, terms: list[Term]) -> tuple[FileHits, list[str]]:
    """Every counted hit in one file, and every refused marker. Pure: the caller read the file.

    A marked line is judged twice. The marked term is searched in the text BEFORE the marker, so a reason that merely repeats the term cannot keep a marker alive; zero hits there is a DEAD marker. Every other term is searched over the whole line, so a reason cannot smuggle a second retired term past the gate.
    """
    hits: FileHits = {}
    problems: list[str] = []
    if MARKER_OPENER not in text and not any(t.regex.search(text) for t in terms):
        return hits, problems
    by_id = {t.id: t for t in terms}
    for number, line in enumerate(text.splitlines(), 1):
        marker = parse_marker(line)
        marked = ""
        if marker is not None:
            tid, reason, col = marker
            where = "%s:%d" % (key, number)
            term = by_id.get(tid)
            if term is None:
                problems.append(
                    "%s: retired-term-ok(%s) names no term in %s (known: %s)"
                    % (where, tid, CONFIG_REL, ", ".join(sorted(by_id)))
                )
            else:
                marked = tid
                if not term.regex.search(line[:col]):
                    problems.append(
                        "%s: DEAD marker retired-term-ok(%s): the line before it no longer "
                        "names %r, so delete the marker" % (where, tid, tid)
                    )
            if not reason:
                problems.append(
                    "%s: retired-term-ok(%s) carries no reason; write "
                    "`retired-term-ok(%s): <why this line must keep naming it>`" % (where, tid, tid)
                )
            else:
                rejection = allowlist.validate_reason(where, reason, key)
                if rejection is not None:
                    problems.append(
                        "%s: retired-term-ok(%s) reason refused: %s"
                        % (where, tid, rejection.message)
                    )
        for term in terms:
            if term.id == marked:
                continue
            n = sum(1 for _ in term.regex.finditer(line))
            if n:
                hits.setdefault((key, term.id), []).extend([number] * n)
    return hits, problems


def _blocker_problem(entry: str, blocker: str) -> str | None:
    if not blocker.startswith("BLOCKER:"):
        return "%s carries no `BLOCKER:` reason" % entry
    rejection = allowlist.validate_reason(
        entry, blocker.removeprefix("BLOCKER:").strip(), CONFIG_REL
    )
    return None if rejection is None else rejection.message


def file_baseline_entries(
    doc: dict, term_ids: set[str]
) -> tuple[dict[tuple[str, str], int], list[str]]:
    """{(path, term): ceiling} from `file_baseline`, and every entry that cannot be trusted."""
    out: dict[tuple[str, str], int] = {}
    problems: list[str] = []
    raw = doc.get("file_baseline") or []
    if not isinstance(raw, list):
        return out, ["file_baseline must be a list"]
    for i, entry in enumerate(raw):
        path, term = str(entry.get("path") or ""), str(entry.get("term") or "")
        count = entry.get("count")
        if not path or not term:
            problems.append("file_baseline[%d] needs both path and term" % i)
            continue
        name = "file_baseline %s/%s" % (path, term)
        if term not in term_ids:
            problems.append("%s names no term in %s" % (name, CONFIG_REL))
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            problems.append("%s: count must be a positive integer, got %r" % (name, count))
            continue
        if (path, term) in out:
            problems.append("%s is listed twice" % name)
        problem = _blocker_problem(name, str(entry.get("blocker") or ""))
        if problem:
            problems.append(problem)
        out[(path, term)] = count
    return out, problems


def file_exclusion_prefixes(doc: dict) -> tuple[list[str], list[str]]:
    """The excluded path prefixes from `file_exclusions`, and every entry that cannot be trusted."""
    out: list[str] = []
    problems: list[str] = []
    raw = doc.get("file_exclusions") or []
    if not isinstance(raw, list):
        return out, ["file_exclusions must be a list"]
    for i, entry in enumerate(raw):
        prefix = str(entry.get("prefix") or "")
        if not prefix:
            problems.append("file_exclusions[%d] has no prefix" % i)
            continue
        problem = _blocker_problem("file_exclusions %s" % prefix, str(entry.get("blocker") or ""))
        if problem:
            problems.append(problem)
        out.append(prefix)
    return out, problems


def under(path: str, prefixes: list[str]) -> bool:
    """True when `path` is one of `prefixes` or sits beneath one (a prefix is a submodule path or ends in `/`)."""
    return any(path == p or path.startswith(p if p.endswith("/") else p + "/") for p in prefixes)


@dataclasses.dataclass(frozen=True)
class FileVerdict:
    new: list[tuple[str, str, int, int]]  # (path, term, have, ceiling)
    held: list[tuple[str, str, int]]  # (path, term, have == ceiling)
    stale: list[tuple[str, str, int, int]]  # (path, term, have, ceiling), have < ceiling
    skipped: list[tuple[str, str, int]]  # (path, term, ceiling) under a NOT CHECKED submodule


def file_verdict(
    hits: FileHits, baseline: dict[tuple[str, str], int], not_checked: list[str]
) -> FileVerdict:
    """The file hits split against the count-keyed shrink-only baseline."""
    new, held, stale, skipped = [], [], [], []
    for (path, term), lines in sorted(hits.items()):
        have, ceiling = len(lines), baseline.get((path, term), 0)
        if have > ceiling:
            new.append((path, term, have, ceiling))
        elif have < ceiling:
            stale.append((path, term, have, ceiling))
        else:
            held.append((path, term, have))
    for (path, term), ceiling in sorted(baseline.items()):
        if (path, term) in hits:
            continue
        if under(path, not_checked):
            skipped.append((path, term, ceiling))
        else:
            stale.append((path, term, 0, ceiling))
    return FileVerdict(new, held, stale, skipped)


def drained_file_baseline(entries: list[dict], hits: FileHits) -> list[dict]:
    """The `file_baseline` a drain writes: each count LOWERED to what fires, an entry at zero removed.

    Never raises a count and never adds an entry: a count above its ceiling is NEW and stays at the old ceiling, so the refusal survives the drain.
    """
    out = []
    for entry in entries:
        key = (str(entry.get("path")), str(entry.get("term")))
        have = len(hits.get(key, []))
        if have == 0:
            continue
        kept = dict(entry)
        kept["count"] = min(int(entry.get("count") or 0), have)
        out.append(kept)
    return out


# --------------------------------------------------------------------------- the tree-reading half


def load_config(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CannotRunError("%s is unreadable (%s)" % (path, exc)) from exc


def _wl_store():
    """`wl_store`, DERIVED rather than copied, the `check_agent_session_archival.py` shape.

    From THIS checkout, which is the instrument, whatever `--root` names: the fold is the reader, and the tree under judgement supplies only the store it reads.
    """
    hooks = paths.hooks_stop_dir(pathlib.Path(paths.repo_root()))
    paths.on_sys_path(hooks)
    try:
        wl_store = importlib.import_module("wl_store")
    except ImportError as exc:
        raise CannotRunError(
            "cannot import wl_store from %s (%s), so the worklist cannot be folded and "
            "every item verdict would be invented here instead" % (hooks, exc)
        ) from exc
    return wl_store


@contextlib.contextmanager
def _store_dir(directory: pathlib.Path):
    """Pin `wl_store.store_dir` for the duration, restoring the caller's value after."""
    old = os.environ.get("WORKLIST_STORE_DIR")
    os.environ["WORKLIST_STORE_DIR"] = str(directory)
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("WORKLIST_STORE_DIR", None)
        else:
            os.environ["WORKLIST_STORE_DIR"] = old


def fold_items(root: pathlib.Path) -> list[dict]:
    """Every live record of the store under `root` (open and closed), through the real fold."""
    wl_store = _wl_store()
    with _store_dir(root / STORE_REL):
        fold = wl_store.load(root / WORKLIST_REL, sync=False)
    return list(fold.items)


def item_subjects(records: list[dict]) -> list[Subject]:
    return [
        Subject("item", "#%s" % r.get("id"), str(r.get("text") or ""), str(r.get("owner") or ""))
        for r in records
        if r.get("state") in OPEN_STATES
    ]


def plan_subjects(root: pathlib.Path) -> tuple[list[Subject], int]:
    """Live plans, and how many plan files were enumerated in total (printed, so a collapse is visible)."""
    rels, err = PL.enumerate_plans(root)
    if err:
        raise CannotRunError(err)
    out = []
    for rel in rels:
        if PL.folder_of(rel) in PL.TERMINAL_DIRS:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if PL.classify(PL.parse_plan(rel, text)) in LIVE_PLAN_STATES:
            out.append(Subject("plan", rel, text))
    return out, len(rels)


PLAN_REF_RE = re.compile(r"^agent/plans/(?:(?:_done|_removed)/)?(PLAN-[A-Za-z0-9._-]+\.md)$")


def _resolves(root: pathlib.Path, ref: str) -> bool:
    """A path ref resolves where it names a file inside the tree; a PLAN ref (`agent/plans/[_done/|_removed/]PLAN-<slug>.md`, nothing deeper) also resolves where the same plan now sits in any of those three places, so a retirement plan that closes into `_done/` and loses its stub does not turn every run into a CannotRunError (reviews 44fdd3b7.1, e34c5d6f.1-.3). A ref that leaves the tree (through `..` or a symlink) never resolves; one that stays inside it, `..` included, resolves as written (review dcd58b41.1)."""

    def in_tree_file(path: pathlib.Path) -> bool:
        # Every candidate, the moved-plan copies included, must resolve inside the tree (review bf93555d.2); a symlink loop raises RuntimeError on Python 3.10-3.12 and OSError later (review bf93555d.3).
        try:
            return path.resolve().is_relative_to(root.resolve()) and path.is_file()
        except (OSError, RuntimeError):
            return False

    m = PLAN_REF_RE.match(ref)
    if m:
        plans = root / "agent" / "plans"
        return any(in_tree_file(plans / sub / m.group(1)) for sub in ("", "_done", "_removed"))
    return in_tree_file(root / ref)


def tracked_paths(root: pathlib.Path, refs: list[str]) -> set[str]:
    return {ref for ref in refs if not ID_REF_RE.match(ref) and _resolves(root, ref)}


#: Index modes that are not a regular file's text: a symlink and a gitlink (a nested submodule).
SKIPPED_MODES = frozenset({"120000", "160000"})


def submodule_files(root: pathlib.Path, sm_path: str) -> list[str]:
    """Every tracked regular file of one checked-out submodule, keyed `<sm path>/<rel>`.

    The environment drops `GIT_INDEX_FILE` and its siblings (`fixture_git_env`): a commit through a scratch index exports the SUPERPROJECT's index, which describes console and never this submodule, so honouring it here would list console's paths as the submodule's.
    """
    env = fixture_git_env()
    env.update(gitx.NONINTERACTIVE)
    result = proc.run(["git", "-C", str(root / sm_path), "ls-files", "-s", "-z"], env=env)
    if not result.ok:
        raise CannotRunError(
            "`git -C %s ls-files` failed (rc=%s): %s"
            % (sm_path, result.returncode, result.stderr.strip())
        )
    out = []
    for entry in result.stdout.split("\0"):
        meta, _, rel = entry.partition("\t")
        fields = meta.split()
        if not rel or not fields or fields[0] in SKIPPED_MODES:
            continue
        out.append("%s/%s" % (sm_path, rel))
    if not out:
        raise CannotRunError(
            "checked-out submodule %s lists ZERO tracked files; the file half is not seeing "
            "it and its green would mean nothing" % sm_path
        )
    return out


@dataclasses.dataclass
class FileScan:
    declared: list[str]
    checked: list[str]
    not_checked: list[str]
    tracked: list[str]
    files_read: int
    excluded: int
    hits: FileHits
    marker_problems: list[str]


def scan_submodules(
    root: pathlib.Path,
    terms: list[Term],
    exclusions: list[str],
    env: dict[str, str] | None = None,
) -> FileScan:
    """The file subject: every checked-out submodule's tracked text files, counted against `terms`.

    `env` reaches `common.require_submodule` only, which reads `CI` from it; the selftest passes one in each direction so the CI fail-closed branch is proven without exporting anything.
    """
    declared = [sm.path for sm in gitx.submodules(root)]
    if not declared:
        raise CannotRunError(
            "%s declares ZERO submodules; the file half has nothing to read and its green "
            "would mean nothing" % (root / ".gitmodules")
        )
    checked, not_checked = [], []
    for sm_path in declared:
        try:
            present = common.require_submodule(
                root / sm_path / ".git", "retired terms: submodule %s" % sm_path, env
            )
        except common.RefusalError as exc:
            raise CannotRunError("\n  ".join(exc.lines)) from exc
        (checked if present else not_checked).append(sm_path)
    tracked: list[str] = []
    for sm_path in checked:
        tracked.extend(submodule_files(root, sm_path))
    dead = [
        p
        for p in exclusions
        if not under(p, not_checked) and not any(under(f, [p]) for f in tracked)
    ]
    if dead:
        raise CannotRunError(
            "file_exclusions prefix(es) match no tracked file of a checked-out submodule: %s. "
            "Delete the dead entry; an exclusion must not outlive what it excuses" % ", ".join(dead)
        )
    hits: FileHits = {}
    problems: list[str] = []
    read = excluded = 0
    for key in tracked:
        if under(key, exclusions):
            excluded += 1
            continue
        try:
            data = (root / key).read_bytes()
        except OSError:
            continue
        if b"\0" in data[:4096]:
            continue
        read += 1
        file_hits, file_problems = scan_text(key, data.decode("utf-8", "replace"), terms)
        hits.update(file_hits)
        problems.extend(file_problems)
    return FileScan(declared, checked, not_checked, tracked, read, excluded, hits, problems)


@dataclasses.dataclass
class Report:
    terms: list[Term]
    items_folded: int
    items: list[Subject]
    plans: list[Subject]
    plans_enumerated: int
    findings: list[Finding]
    baseline: list[tuple[str, str]]
    unresolved_ids: list[str]
    #: None under `--owner`: the Stop hook's call judges that session's items and nothing else.
    files: FileScan | None = None
    file_baseline: dict[tuple[str, str], int] = dataclasses.field(default_factory=dict)


def gather(
    root: pathlib.Path, config: pathlib.Path, owner: str = "", env: dict[str, str] | None = None
) -> Report:
    """The verdict's inputs: the terms from `config`, the subjects (store, plans and, outside `--owner`, submodule files) from `root`."""
    doc = load_config(config)
    terms, problems = parse_terms(doc)
    baseline, base_problems = baseline_pairs(doc)
    problems += base_problems
    file_baseline, fb_problems = file_baseline_entries(doc, {t.id for t in terms})
    exclusions, ex_problems = file_exclusion_prefixes(doc)
    problems += fb_problems + ex_problems
    records = fold_items(root)
    if not records:
        raise CannotRunError(
            "the worklist store under %s folded to ZERO items; the gate is not seeing the "
            "store and its green would mean nothing" % (root / STORE_REL)
        )
    refs = [ref for term in terms for ref in term.retired_by]
    missing_paths, missing_ids = unresolved_refs(
        terms, tracked_paths(root, refs), {str(r.get("id") or "") for r in records}
    )
    problems += missing_paths
    if problems:
        raise CannotRunError("%s cannot be trusted:\n  %s" % (config, "\n  ".join(problems)))
    items = item_subjects(records)
    plans, enumerated = plan_subjects(root)
    if not plans:
        raise CannotRunError(
            "ZERO live plans among %d enumerated plan file(s) under %s; the plan half is "
            "not seeing the corpus" % (enumerated, root)
        )
    findings = judge(items + plans, terms)
    files = None if owner else scan_submodules(root, terms, exclusions, env)
    return Report(
        terms,
        len(records),
        items,
        plans,
        enumerated,
        findings,
        baseline,
        missing_ids,
        files,
        file_baseline,
    )


def write_baseline(config: pathlib.Path, report: Report) -> int:
    """Drain both baselines. NEVER adds and never raises a count; a new finding is fixed, not baselined.

    Refuses (rc 2) while any submodule is NOT CHECKED: that submodule's files were never read, so every one of its entries would look fixed and be drained away.
    """
    files = report.files
    if files is None:
        log.error("retired terms: --write-baseline needs the file half, which did not run")
        return 2
    if files.not_checked:
        log.error(
            "retired terms: refusing --write-baseline while submodule(s) are NOT CHECKED (%s): "
            "their files were never read, so their baseline entries would drain as fixed. "
            "Run `git submodule update --init %s` first."
            % (", ".join(files.not_checked), " ".join(files.not_checked))
        )
        return 2
    new, _held, stale = plan_verdict(report.findings, report.baseline)
    fv = file_verdict(files.hits, report.file_baseline, files.not_checked)
    doc = load_config(config)
    kept = [
        e
        for e in doc.get("plan_baseline") or []
        if (str(e.get("plan")), str(e.get("term"))) not in set(stale)
    ]
    old_files = list(doc.get("file_baseline") or [])
    kept_files = drained_file_baseline(old_files, files.hits)
    old_ids = ["plan %s %s" % p for p in report.baseline] + [
        "file %s %s" % key for key in report.file_baseline
    ]
    new_ids = ["plan %s %s" % (e.get("plan"), e.get("term")) for e in kept] + [
        "file %s %s" % (e.get("path"), e.get("term")) for e in kept_files
    ]
    added = shrink_only.baseline_additions(old_ids, new_ids)
    raised = [
        "file %s %s" % (e.get("path"), e.get("term"))
        for e in kept_files
        if e["count"] > report.file_baseline.get((str(e.get("path")), str(e.get("term"))), 0)
    ]
    verdict = shrink_only.write_verdict(baseline_exists=True, first_seed=False, additions=added)
    if verdict is not None or added or raised:
        log.error(
            "retired terms: refusing --write-baseline (%s): added %s, raised %s"
            % (verdict, added, raised)
        )
        return 1
    for f in new:
        log.warn(
            "  NOT ADDED %s names %r: fix the plan; a new finding is never baselined"
            % (f.subject.key, f.term.id)
        )
    for path, term, have, ceiling in fv.new:
        log.warn(
            "  NOT ADDED %s names %r %d time(s), ceiling %d: fix the file or mark the line; "
            "a new finding is never baselined" % (path, term, have, ceiling)
        )
    doc["plan_baseline"] = kept
    doc["file_baseline"] = kept_files
    # tree-write: mode --write-baseline the drain verb a human runs by name, never reached by the default check
    config.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lowered = sum(
        1
        for e in kept_files
        if e["count"] < report.file_baseline.get((str(e.get("path")), str(e.get("term"))), 0)
    )
    log.success(
        "retired terms: plan baseline %d -> %d pair(s); file baseline %d -> %d entr(ies), "
        "%d lowered, %d removed; 0 added, 0 raised"
        % (
            len(report.baseline),
            len(kept),
            len(old_files),
            len(kept_files),
            lowered,
            len(old_files) - len(kept_files),
        )
    )
    return 0


def render(report: Report, owner: str) -> int:
    new, held, stale = plan_verdict(report.findings, report.baseline)
    item_findings = [f for f in report.findings if f.subject.kind == "item"]
    refused_items = [f for f in item_findings if owner and owned(f.subject.owner, owner)]
    advised_items = [f for f in item_findings if f not in refused_items]
    log.info(
        "  %d term(s); %d item(s) folded, %d open; %d live plan(s) of %d enumerated; "
        "%d item finding(s), %d plan finding(s) (%d baselined, %d new, %d stale baseline pair(s))"
        % (
            len(report.terms),
            report.items_folded,
            len(report.items),
            len(report.plans),
            report.plans_enumerated,
            len(item_findings),
            len(new) + len(held),
            len(held),
            len(new),
            len(stale),
        )
    )

    for note in report.unresolved_ids:
        log.warn("  UNRESOLVED %s (not yet committed, or compacted away)" % note)

    def line(f: Finding) -> str:
        who = " owner %s" % f.subject.owner if f.subject.kind == "item" else ""
        cites = ", ".join(f.term.retired_by)
        return (
            "%s%s names retired term %r (retired %s: %s)\n      text: %s\n      fix: withdraw or "
            "rewrite it, or cite the retirement it belongs to (%s)"
            % (f.subject.key, who, f.term.id, f.term.retired, f.term.reason, f.excerpt, cites)
        )

    for f in advised_items:
        log.warn("  ADVISORY item %s" % line(f))
    for f in refused_items:
        log.error("  ITEM %s" % line(f))
    if not owner:
        for f in held:
            log.warn("  BASELINED plan %s" % line(f))
        for f in new:
            log.error("  NEW plan %s\n      Do not add it to the baseline." % line(f))
        for plan, term in stale:
            log.error(
                "  STALE baseline %s no longer names %r: drain it with "
                "`.ci/scripts/quality/check_retired_terms.py --write-baseline`" % (plan, term)
            )
    refused = len(refused_items) + (0 if owner else len(new) + len(stale))
    files_note = ""
    if report.files is not None:
        refused += render_files(report, report.files)
        fv = file_verdict(report.files.hits, report.file_baseline, report.files.not_checked)
        files_note = ", %d file pair(s) baselined, %d skipped as NOT CHECKED" % (
            len(fv.held),
            len(fv.skipped),
        )
    if refused:
        log.error("retired terms: %d refusal(s)" % refused)
        return 1
    log.success(
        "retired terms: no %s names a retired term without citing its retirement%s"
        % (
            "open item of %s" % owner if owner else "new live plan or submodule file",
            ""
            if owner
            else " (%d item advisory(ies), %d plan pair(s) baselined%s)"
            % (len(advised_items), len(held), files_note),
        )
    )
    return 0


def _lines(numbers: list[int], limit: int = 8) -> str:
    shown = ", ".join(str(n) for n in numbers[:limit])
    return shown + (" (+%d more)" % (len(numbers) - limit) if len(numbers) > limit else "")


def render_files(report: Report, files: FileScan) -> int:
    """The file half's shape line and findings. Returns its refusal count."""
    fv = file_verdict(files.hits, report.file_baseline, files.not_checked)
    by_id = {t.id: t for t in report.terms}
    log.info(
        "  %d submodule(s) declared, %d checked out, %d file(s) read (%d tracked, %d excluded); "
        "NOT CHECKED: %s; %d file pair(s) firing (%d baselined, %d new, %d stale, %d skipped), "
        "%d refused marker(s)"
        % (
            len(files.declared),
            len(files.checked),
            files.files_read,
            len(files.tracked),
            files.excluded,
            ", ".join(files.not_checked) or "none",
            len(files.hits),
            len(fv.held),
            len(fv.new),
            len(fv.stale),
            len(fv.skipped),
            len(files.marker_problems),
        )
    )
    for sm_path in files.not_checked:
        log.warn(
            "  NOT CHECKED %s: not checked out, so none of its files were read "
            "(`git submodule update --init %s`)" % (sm_path, sm_path)
        )
    for path, term, ceiling in fv.skipped:
        log.warn(
            "  SKIPPED baseline %s %r (ceiling %d): its submodule is NOT CHECKED"
            % (path, term, ceiling)
        )
    for path, term, have in fv.held:
        log.warn("  BASELINED file %s names %r %d time(s)" % (path, term, have))
    for path, term, have, ceiling in fv.new:
        t = by_id[term]
        log.error(
            "  NEW file %s names retired term %r %d time(s), baseline allows %d (retired %s: %s)\n"
            "      lines: %s\n"
            "      fix: remove the stale text, or mark a line that must keep it with "
            "`retired-term-ok(%s): <reason>`. Do not add it to the baseline."
            % (
                path,
                term,
                have,
                ceiling,
                t.retired,
                t.reason,
                _lines(files.hits[(path, term)]),
                term,
            )
        )
    for path, term, have, ceiling in fv.stale:
        log.error(
            "  STALE file baseline %s %r allows %d, now %d: drain it with "
            "`.ci/scripts/quality/check_retired_terms.py --write-baseline`"
            % (path, term, ceiling, have)
        )
    for problem in files.marker_problems:
        log.error("  MARKER %s" % problem)
    return len(fv.new) + len(fv.stale) + len(files.marker_problems)


def _arg(argv: list[str], flag: str) -> str:
    if flag in argv:
        i = argv.index(flag)
        if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
            raise CannotRunError("%s needs a value" % flag)
        return argv[i + 1]
    return ""


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return 1 if selftest() else 0
    rc = controls_first("retired terms", selftest)
    if rc:
        return rc
    try:
        root_arg = _arg(argv, "--root")
        owner = _arg(argv, "--owner")
        config_arg = _arg(argv, "--config")
        here = pathlib.Path(paths.repo_root())
        root = pathlib.Path(root_arg).resolve() if root_arg else here
        config = pathlib.Path(config_arg).resolve() if config_arg else here / CONFIG_REL
        report = gather(root, config, owner)
    except CannotRunError as exc:
        log.error("retired terms: CANNOT RUN: %s" % exc)
        return 2
    if "--write-baseline" in argv:
        if root_arg or owner or config_arg:
            log.error(
                "retired terms: --write-baseline drains THIS checkout's baseline against THIS "
                "checkout's plans; it does not combine with --root, --owner or --config"
            )
            return 2
        return write_baseline(config, report)
    return render(report, owner)


# --------------------------------------------------------------------------- controls


def _shipped_terms() -> list[Term]:
    terms, problems = parse_terms(load_config(pathlib.Path(paths.repo_root()) / CONFIG_REL))
    if problems:
        raise CannotRunError("; ".join(problems))
    return terms


def _mutant(subject: Subject, old: str, new: str) -> Subject:
    """`subject` with its text planted; `plant` refuses a mutation that changes nothing."""
    return Subject(subject.kind, subject.key, plant(subject.text, old, new), subject.owner)


def _flagged(subjects: list[Subject], terms: list[Term]) -> set[tuple[str, str]]:
    return {(f.subject.key, f.term.id) for f in judge(subjects, terms)}


@git_isolated
def selftest() -> bool:
    """True when a control failed, which is what `controls_first` expects."""
    check = Checker()
    try:
        terms = _shipped_terms()
    except CannotRunError as exc:
        check(
            "CONTROL: the shipped config parses and every pattern passes its own texts (%s)" % exc,
            False,
        )
        return True
    by_id = {t.id: t for t in terms}
    for need in ("rclone", "BACKUP_S3_pre-rename", "edge-rediacc-configs"):
        check("CONTROL: the shipped config still carries term %r" % need, need in by_id)
    if not check.ok:
        return True

    rclone = Subject("item", "#aaaa1111", "(x) bake rclone into the E2E VM image", "aaaaaaaa")
    check(
        "PLANT: an open item naming rclone is a finding",
        _flagged([rclone], terms) == {("#aaaa1111", "rclone")},
    )
    cited = _mutant(rclone, "VM image", "VM image, superseded by PLAN-backup-program")
    check(
        "CONTROL: the same item citing PLAN-backup-program is allowed",
        _flagged([cited], terms) == set(),
    )
    moved = _mutant(
        rclone, "VM image", "VM image, see agent/plans/_done/PLAN-rclone-decommission.md"
    )
    check(
        "CONTROL: a citation of the plan at its _done/ path is the same citation",
        _flagged([moved], terms) == set(),
    )
    lookalike = _mutant(rclone, "VM image", "VM image, see PLAN-backup-program-v2")
    check(
        "PLANT: a plan whose name merely EXTENDS a retirement plan's stem cites nothing",
        _flagged([lookalike], terms) != set(),
    )
    itself = Subject("item", "#1201d7b9", "(x) withdraw the rclone bake item", "aaaaaaaa")
    check(
        "CONTROL: the retiring item itself is never a finding", _flagged([itself], terms) == set()
    )
    live_family = Subject(
        "item", "#aaaa2222", "(x) set ACCOUNT_BACKUP_S3_BUCKET and ACCOUNT_BACKUP_S3_*", "aaaaaaaa"
    )
    check(
        "CONTROL: ACCOUNT_BACKUP_S3_BUCKET is the live family and is allowed",
        _flagged([live_family], terms) == set(),
    )
    old_family = _mutant(
        live_family, "ACCOUNT_BACKUP_S3_BUCKET and ACCOUNT_BACKUP_S3_*", "BACKUP_S3_BUCKET"
    )
    check(
        "PLANT: a bare BACKUP_S3_BUCKET is a finding",
        _flagged([old_family], terms) == {("#aaaa2222", "BACKUP_S3_pre-rename")},
    )
    regional = Subject(
        "item", "#aaaa3333", "(x) copy the configs into edge-rediacc-configs-eu", "aaaaaaaa"
    )
    check(
        "CONTROL: edge-rediacc-configs-eu is a live regional bucket and is allowed",
        _flagged([regional], terms) == set(),
    )
    bare = _mutant(regional, "edge-rediacc-configs-eu", "edge-rediacc-configs and verify")
    check(
        "PLANT: the bare edge-rediacc-configs bucket is a finding",
        _flagged([bare], terms) == {("#aaaa3333", "edge-rediacc-configs")},
    )
    plan = Subject("plan", "agent/plans/PLAN-x.md", "- [ ] retry the apt in ensureRclone")
    check(
        "PLANT: a live plan naming rclone in an identifier is a finding",
        _flagged([plan], terms) == {("agent/plans/PLAN-x.md", "rclone")},
    )
    own_plan = Subject(
        "plan", "agent/plans/PLAN-backup-program.md", "rclone goes; BACKUP_S3_* goes"
    )
    check(
        "CONTROL: a retirement plan is never a finding against itself",
        _flagged([own_plan], terms) == set(),
    )

    # The config validator, in both directions, on fixture docs.
    good = {
        "terms": [
            {
                "id": "t",
                "pattern": "foo",
                "case_sensitive": True,
                "retired": "2026-01-01",
                "reason": "a reason long enough to say something",
                "retired_by": ["#abcdef12"],
                "must_match": ["a foo"],
                "must_not_match": ["a bar"],
            }
        ]
    }
    check("CONTROL: a well-formed fixture config parses clean", parse_terms(good)[1] == [])
    vacuous = json.loads(json.dumps(good))
    vacuous["terms"][0]["pattern"] = "fooo"
    check(
        "PLANT: a pattern that misses its own must_match text is refused",
        any("does not match" in p for p in parse_terms(vacuous)[1]),
    )
    greedy = json.loads(json.dumps(good))
    greedy["terms"][0]["pattern"] = "a"
    check(
        "PLANT: a pattern that hits its must_not_match text is refused",
        any("matches its must_not_match" in p for p in parse_terms(greedy)[1]),
    )
    future = json.loads(json.dumps(good))
    future["terms"][0]["retired"] = "2999-01-01"
    check(
        "PLANT: a retirement dated in the future is refused",
        any("ISO date" in p for p in parse_terms(future)[1]),
    )
    check("PLANT: an empty terms list is refused", parse_terms({"terms": []})[1] != [])
    check(
        "PLANT: a retired_by item id naming no item is reported",
        unresolved_refs(parse_terms(good)[0], set(), set())[1] != [],
    )
    on_path = json.loads(json.dumps(good))
    on_path["terms"][0]["retired_by"] = ["agent/plans/PLAN-nowhere.md"]
    check(
        "PLANT: a retired_by path naming no file is refused",
        unresolved_refs(parse_terms(on_path)[0], set(), set())[0] != [],
    )
    check(
        "CONTROL: a resolvable retired_by passes",
        unresolved_refs(parse_terms(good)[0], set(), {"abcdef12"}) == ([], []),
    )

    # The shrink-only plan baseline, both halves.
    f_plan = Finding(plan, by_id["rclone"], "")
    new, held, stale = plan_verdict([f_plan], [])
    check("PLANT: an unbaselined plan finding is NEW", len(new) == 1 and not held and not stale)
    new, held, stale = plan_verdict([f_plan], [("agent/plans/PLAN-x.md", "rclone")])
    check(
        "CONTROL: a baselined plan finding is held, not new",
        not new and len(held) == 1 and not stale,
    )
    new, held, stale = plan_verdict([], [("agent/plans/PLAN-x.md", "rclone")])
    check(
        "PLANT: a baselined pair that stopped firing is STALE, so the baseline drains",
        stale == [("agent/plans/PLAN-x.md", "rclone")],
    )
    blank = baseline_pairs({"plan_baseline": [{"plan": "p", "term": "t", "blocker": "later"}]})[1]
    check("PLANT: a baseline entry without a BLOCKER reason is refused", blank != [])

    _file_controls(check, terms, by_id)

    # The real fold: a closed item is ignored and an open one is seen, written through the real writer verbs.
    try:
        check(
            "CONTROL: through the real wl_store fold, the open rclone item is seen and the closed one is not",
            _fold_control(terms),
        )
    except CannotRunError as exc:
        check("CONTROL: the real wl_store fold is reachable (%s)" % exc, False)
    print("  %d control(s) ran" % check.count)
    return not check.ok


REASON = "this comment records the removal so nobody re-adds it"


def _counts(key: str, text: str, terms: list[Term]) -> tuple[dict[str, int], list[str]]:
    hits, problems = scan_text(key, text, terms)
    return {term: len(lines) for (_k, term), lines in hits.items()}, problems


def _fixture_tree(base: pathlib.Path, *, declared: list[str], present: dict[str, dict]) -> None:
    """A superproject with `.gitmodules` naming `declared`, and each of `present` a git repo whose index holds its files.

    A value of None in a file map plants a symlink to `doc.md` (a READABLE target naming the term, so a gate that stopped skipping symlinks would count it); bytes plant a binary file. The files are only `git add`ed, never committed: `ls-files` reads the index, and a commit would need an identity the CI runner may not carry.
    """
    base.mkdir(parents=True, exist_ok=True)
    (base / ".gitmodules").write_text(
        "".join(
            '[submodule "%s"]\n\tpath = %s\n\turl = https://example.invalid/x.git\n' % (p, p)
            for p in declared
        ),
        encoding="utf-8",
    )
    env = fixture_git_env()
    for sm_path, files in present.items():
        repo = base / sm_path
        repo.mkdir(parents=True, exist_ok=True)
        proc.run(["git", "init", "-q", str(repo)], env=env)
        for rel, body in files.items():
            target = repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if body is None:
                target.symlink_to("doc.md")
            elif isinstance(body, bytes):
                target.write_bytes(body)
            else:
                target.write_text(body, encoding="utf-8")
        if files:
            proc.run(["git", "-C", str(repo), "add", "-A"], env=env)


def _file_controls(check: Checker, terms: list[Term], by_id: dict[str, Term]) -> None:
    """The file subject in both directions: patterns, the marker, the count baseline, the drain and the enumeration."""
    # X1: the narrowed patterns.
    check(
        "CONTROL: discoverCloneState is not rclone",
        _counts("f", "x := discoverCloneState(y)", terms)[0] == {},
    )
    check(
        "PLANT: an Rclone in prose is rclone",
        _counts("f", "the Rclone remote", terms)[0] == {"rclone": 1},
    )
    for live in ("edge-rediacc-configs-<region>", "edge-rediacc-configs-${region}"):
        check(
            "CONTROL: %s is a live regional bucket" % live,
            _counts("f", "copy into %s now" % live, terms)[0] == {},
        )

    # X3: the marker.
    clean = "a plain backup to the chunk store\n"
    check("CONTROL: a clean file has no hit and no problem", _counts("f", clean, terms) == ({}, []))
    planted = plant(clean, "chunk store", "chunk store through rclone")
    check(
        "PLANT: a file naming rclone counts one hit on its line",
        scan_text("f", planted, terms) == ({("f", "rclone"): [1]}, []),
    )
    marked = planted.rstrip("\n") + "  // retired-term-ok(rclone): %s\n" % REASON
    check("CONTROL: a marked line with a reason is silent", _counts("f", marked, terms) == ({}, []))
    html = planted.rstrip("\n") + " <!-- retired-term-ok(rclone): %s -->\n" % REASON
    check(
        "CONTROL: a trailing `-->` is no part of the reason",
        _counts("f", html, terms) == ({}, []),
    )
    html_empty = plant(html, REASON, "")
    check(
        "PLANT: `<!-- retired-term-ok(t): -->` is a marker with no reason, not a reason of `-->`",
        any("carries no reason" in p for p in _counts("f", html_empty, terms)[1]),
    )
    no_reason = plant(marked, ": %s" % REASON, "")
    check(
        "PLANT: a marker with no reason is refused",
        any("carries no reason" in p for p in _counts("f", no_reason, terms)[1]),
    )
    low = plant(marked, REASON, "no fix")
    check(
        "PLANT: a marker with a low-effort reason is refused",
        _counts("f", low, terms)[1] != [],
    )
    unknown = plant(marked, "retired-term-ok(rclone)", "retired-term-ok(zzz)")
    unknown_counts, unknown_problems = _counts("f", unknown, terms)
    check(
        "PLANT: a marker naming no term is refused and suppresses nothing",
        any("names no term" in p for p in unknown_problems) and unknown_counts == {"rclone": 1},
    )
    dead = plant(marked, "through rclone", "through the chunk client")
    check(
        "PLANT: a marker whose line no longer names its term is DEAD",
        any("DEAD marker" in p for p in _counts("f", dead, terms)[1]),
    )
    echo = plant(dead, REASON, REASON + " after rclone")
    check(
        "PLANT: a reason that only repeats the term keeps no marker alive",
        any("DEAD marker" in p for p in _counts("f", echo, terms)[1]),
    )
    two = plant(marked, "through rclone", "through rclone and BACKUP_S3_BUCKET")
    check(
        "PLANT: a marker suppresses only its own term",
        _counts("f", two, terms) == ({"BACKUP_S3_pre-rename": 1}, []),
    )

    # X4: the count baseline and its drain.
    hits: FileHits = {("s/a", "rclone"): [3, 9]}
    check(
        "PLANT: an unlisted file pair is NEW",
        file_verdict(hits, {}, []).new == [("s/a", "rclone", 2, 0)],
    )
    v = file_verdict(hits, {("s/a", "rclone"): 2}, [])
    check("CONTROL: a count at its ceiling is held", v.held and not v.new and not v.stale)
    check(
        "PLANT: a count above its ceiling is NEW",
        file_verdict(hits, {("s/a", "rclone"): 1}, []).new == [("s/a", "rclone", 2, 1)],
    )
    check(
        "PLANT: a count below its ceiling is STALE",
        file_verdict(hits, {("s/a", "rclone"): 3}, []).stale == [("s/a", "rclone", 2, 3)],
    )
    gone = file_verdict({}, {("s/a", "rclone"): 3, ("t/b", "rclone"): 1}, ["t"])
    check(
        "CONTROL: an entry under a NOT CHECKED submodule is skipped, a fixed one is STALE",
        gone.skipped == [("t/b", "rclone", 1)] and gone.stale == [("s/a", "rclone", 0, 3)],
    )
    entries = [
        {"path": "s/a", "term": "rclone", "count": 5, "blocker": "x"},
        {"path": "s/b", "term": "rclone", "count": 1, "blocker": "x"},
        {"path": "s/c", "term": "rclone", "count": 1, "blocker": "x"},
    ]
    drained = drained_file_baseline(entries, {("s/a", "rclone"): [1, 2], ("s/c", "rclone"): [1, 2]})
    check(
        "CONTROL: the drain lowers, removes at zero, and never raises a count",
        [(e["path"], e["count"]) for e in drained] == [("s/a", 2), ("s/c", 1)],
    )
    good_blocker = "BLOCKER: removed by PLAN-backup-program H7 with the rest of the rclone code"
    ok_entry = {"path": "s/a", "term": "rclone", "count": 1, "blocker": good_blocker}
    check(
        "CONTROL: a well-formed file_baseline entry parses clean",
        file_baseline_entries({"file_baseline": [ok_entry]}, set(by_id))[1] == [],
    )
    check(
        "PLANT: a file_baseline entry without a BLOCKER reason is refused",
        file_baseline_entries({"file_baseline": [dict(ok_entry, blocker="later")]}, set(by_id))[1]
        != [],
    )
    check(
        "PLANT: a file_baseline entry naming no term is refused",
        file_baseline_entries({"file_baseline": [dict(ok_entry, term="zzz")]}, set(by_id))[1] != [],
    )
    check(
        "PLANT: a file_exclusions entry without a BLOCKER reason is refused",
        file_exclusion_prefixes({"file_exclusions": [{"prefix": "s/x/", "blocker": ""}]})[1] != [],
    )

    # X2: the enumeration, through the real git against fixture repos.
    try:
        _enumeration_controls(check, terms, clean)
    except CannotRunError as exc:
        check("CONTROL: the fixture enumeration reaches a verdict (%s)" % exc, False)


def _enumeration_controls(check: Checker, terms: list[Term], clean: str) -> None:
    with tempfile.TemporaryDirectory(prefix="retired-terms-files-") as tmp:
        base = pathlib.Path(tmp)
        tree = base / "tree"
        _fixture_tree(
            tree,
            declared=["sub/a", "sub/gone"],
            present={
                "sub/a": {
                    "doc.md": "uses rclone\n",
                    "clean.md": clean,
                    "blob.bin": b"\0rclone",
                    "link": None,
                    "mig/0001.sql": "-- rclone\n",
                }
            },
        )
        scan = scan_submodules(tree, terms, [], env={})
        check(
            "CONTROL: a checked-out submodule is read, an absent one is NOT CHECKED locally",
            scan.checked == ["sub/a"] and scan.not_checked == ["sub/gone"],
        )
        check(
            "PLANT: a tracked text file naming rclone is a hit; binary and symlink are skipped",
            set(scan.hits) == {("sub/a/doc.md", "rclone"), ("sub/a/mig/0001.sql", "rclone")}
            and scan.files_read == 3,
        )
        excl = scan_submodules(tree, terms, ["sub/a/mig/"], env={})
        check(
            "CONTROL: an excluded prefix is not read",
            set(excl.hits) == {("sub/a/doc.md", "rclone")} and excl.excluded == 1,
        )
        try:
            scan_submodules(tree, terms, ["sub/a/nothing/"], env={})
            dead_ok = False
        except CannotRunError:
            dead_ok = True
        check("PLANT: an exclusion matching no tracked file is CANNOT RUN", dead_ok)
        try:
            scan_submodules(tree, terms, [], env={"CI": "true"})
            ci_ok = False
        except CannotRunError:
            ci_ok = True
        check("PLANT: an absent submodule under CI=true is CANNOT RUN", ci_ok)
        empty = base / "empty"
        _fixture_tree(empty, declared=[], present={})
        try:
            scan_submodules(empty, terms, [], env={})
            zero_ok = False
        except CannotRunError:
            zero_ok = True
        check("PLANT: zero declared submodules is CANNOT RUN", zero_ok)
        bare = base / "bare"
        _fixture_tree(bare, declared=["sub/e"], present={"sub/e": {}})
        try:
            scan_submodules(bare, terms, [], env={})
            nofile_ok = False
        except CannotRunError:
            nofile_ok = True
        check("PLANT: a checked-out submodule listing zero files is CANNOT RUN", nofile_ok)


def _fold_control(terms: list[Term]) -> bool:
    wl_store = _wl_store()
    with tempfile.TemporaryDirectory(prefix="retired-terms-") as tmp:
        base = pathlib.Path(tmp)
        store = base / "store"
        store.mkdir()
        worklist = base / "worklist.md"
        with _store_dir(store):
            opened = wl_store.add_item(
                worklist, "aaaaaaaa", "(aaaaaaaa) bake rclone into the image", " ", "aaaaaaaa"
            )
            closed = wl_store.add_item(
                worklist, "aaaaaaaa", "(aaaaaaaa) bake rclone, closed", " ", "aaaaaaaa"
            )
            wl_store.set_state(worklist, "aaaaaaaa", closed, "x", "withdrawn")
            records = list(wl_store.load(worklist, sync=False).items)
    seen = {r["id"] for r in records}
    flagged = _flagged(item_subjects(records), terms)
    return {opened, closed} <= seen and flagged == {("#%s" % opened, "rclone")}


__all__ = [
    "Finding",
    "Subject",
    "Term",
    "cites_retirement",
    "judge",
    "main",
    "parse_terms",
    "plan_verdict",
    "selftest",
    "unresolved_refs",
]
