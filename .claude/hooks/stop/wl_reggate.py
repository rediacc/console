"""wl_reggate: the v7 regression-gate machinery and its v8 bookkeeping.

WHY (v7, operator request): "you fixed but we didn't have a mechanism for future regressions." A fix without a gate is a defect scheduled to return, and the i18n cross-locale bug proved it: fixed by hand, then invisible to every existing check by construction. On every stop where a fix landed, the judge is asked whether a gate protects it, and every model claim is VERIFIED against
artifacts: a named existing gate must be a real check:* key; a new gate counts only when WIRED (reachable from `npm run ci` TRANSITIVELY) and its bounded run is green (cached by content hash).

Detection is from ARTIFACTS, never prose: commit subjects matching ^(fix|revert)[(!:] between the marker's last-seen HEAD and current HEAD, plus newly ticked `- [x]` items owned by this session. A fix-set touching only docs/** and **/*.md never asks. A settled fix-set is NEVER re-asked.

FAIL SAFE: a missing marker initialises to current HEAD and asks nothing that stop; a corrupt one does the same plus ONE systemMessage line. Never a block, never silent. No field-wise salvage: any invalid shape discards the file, because half-parsed fixsets silently resurrect a blocked question as settled.
"""

import contextlib
import datetime
import fnmatch
import glob
import hashlib
import json
import os
import pathlib
import re
import subprocess
import tomllib

import wl_common
import wl_core as C
import wl_proc
import wl_store as S
import worklist_messages as M

FIX_SUBJECT = re.compile(r"^(fix|revert)[(!:]")
REGGATE_TIMEOUT_S = int(os.environ.get("WORKLIST_REGGATE_TIMEOUT_S", "120"))
REGGATE_VERDICTS = (
    "not-applicable",
    "covered",
    "one-off",
    "proven",
    "deferred",
    # Written ONLY by the cap, never by the judge. It says "the finding was computed and verified, then deferred as debt" -- which is a different fact
    # from every verdict above, all of which mean the question was answered.
    # Collapsing it into "deferred" would make a capped demand indistinguishable
    # from one the session argued its way out of.
    "capped",
)

# --------------------------------------------------------------------------- THE EFFORT CAP (operator ruling 2026-09-05T01:55Z).
#
# "This is a general problem. Lets employ a planning agent to have a limit for that. Maybe we can limit new gate work after some point to 7 times? But that check should be done on stop hook side instead of ignoring."
#
# The ruling's second sentence is the load-bearing one: the cap belongs HERE, in the machinery, not in a session deciding it has complied enough. A session that stops complying is indistinguishable from a session that is wrong.
#
# WHAT IS COUNTED (plan Q1): a fix-set this BRANCH settled by writing a new gate (`proven`), plus one for each fix-set the cap itself deferred. NOT demands, blocks or stops -- counting those lets a session outwait a legitimate demand by stopping N times, which is the ignoring the ruling forbids. NOT the cheap settles (`covered`/`one-off`/`not-applicable`/`deferred`) -- those cost
# no artifact and no CI round, and counting them would let a session farm the budget
# with five honest one-offs to buy a pass on the sixth, real gate.
#
# SCOPE IS THE BRANCH, not the session. `reggate_path` is keyed on session id, so a per-session budget would evaporate at exactly the moment a long night makes compaction likely. A branch maps one-to-one onto one PR and one CI queue, which is where the cost actually lands; two sessions sharing a branch share the budget, correctly, because they share the queue.
# ---------------------------------------------------------------------------
REGGATE_CAP = max(1, int(os.environ.get("WORKLIST_REGGATE_CAP", "7")))
# A debt is due when its ledger's branch is not the live one (it landed or was abandoned: the one-branch rule leaves no third case) or when the grace clock runs out, whichever comes first (debt_due). The clock is what makes a debt on the live branch, or on `main`, come back at all.
REGGATE_DEBT_GRACE_MIN = max(1, int(os.environ.get("WORKLIST_REGGATE_DEBT_GRACE_MIN", "720")))
# THE CAP ON THE CAP (design Q4.2, agent/plans/PLAN-reggate-debt-collection.md D2). Past this many outstanding debts on the live branch the cap stops deferring and the demand blocks normally: without it the cap was a permanent hatch, and 0914-1 (29) and 1104-1 (28) both walked through it.
REGGATE_MAX_DEBTS = max(1, int(os.environ.get("WORKLIST_REGGATE_MAX_DEBTS", "5")))
# A retire pays a debt only with the operator minute it was ruled at (D5).
RETIRE_ASKED_RE = re.compile(r"^ASKED:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$")


def debt_dir(root=None):
    """Directory holding the per-branch ledgers. See wl_store.AGENT_RESERVED_DIRS.

    HONOURS $WORKLIST_STORE_DIR, exactly as wl_store.store_dir does, and for the same reason it had to learn it: without the override the test harness runs the hook against the REAL repo root, so every suite run appended a ledger to the operator's own tree. Caught the first time this shipped -- an untracked agent/reggate/agenttest.jsonl appeared in `git status` from a suite run,
    which is the same footgun as the harness once writing the operator's real worklist. A sibling of the store, so one export redirects both.
    """
    override = os.environ.get("WORKLIST_STORE_DIR")
    if override:
        return pathlib.Path(override).parent / "reggate"
    if root is None:
        root = C.project_root(C.project_start())
    return pathlib.Path(root) / "agent" / "reggate"


def _branch_slug(branch):
    """A branch name flattened to one safe filename component.

    Branch names carry '/' and worse; one file per branch means the name IS the filename, so it is sanitised rather than trusted.
    """
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (branch or "detached").strip()) or "detached"
    return slug[:100]


def debt_path(branch, root=None):
    """ONE FILE PER BRANCH, following wl_store's per-writer rule verbatim.

    Both sides of a merge append at EOF, so a single shared ledger conflicts on every concurrent append. Per-branch files never do.
    """
    return debt_dir(root) / (_branch_slug(branch) + ".jsonl")


# Where a freshly written gate leaves its artifact. Both shapes exist in this repo; anything else is not a gate the ci chain can run. The hook and gate test suites count as gate artifacts too: a fix inside .claude/hooks/** or a CI script has its canonical regression home in the corresponding SUITE, and the old two-glob probe kept printing "no new or changed check script found"
# across three consecutive stops while the judge itself had already accepted a suite case (163e) as the gate. A probe narrower than the judge's own ruling is a false-fire generator.
CHECK_SCRIPT_GLOBS = (
    "scripts/gates/check-*.ts",
    # Package-local gates. Omitting these made the probe structurally blind to NINE real gates -- check:ci-tutorial-parity, check:ci-locale-tutorial-assets, check:ci-solution-videos, check:ci-command-planes and friends all live here, because a gate about www content belongs beside www. Measured 2026-08-18: a session wrote packages/www/scripts/check-tutorial-card-fonts.ts, wired its
    # check:ci-* key and its ci-quality.yml step, ran its planted-defect proof, and the probe still answered "no new or changed check script found; a claimed gate must leave one". The only way to satisfy the old globs was to move a www gate to the repo root, i.e. to let the probe dictate layout.
    "packages/*/scripts/check-*.ts",
    ".ci/scripts/quality/check-*.sh",
    ".ci/scripts/quality/check_*.py",
    ".ci/scripts/test/gates/test-*.sh",
    # THE PYTHON GATE-TEST SURFACE, and its omission was the THIRD instance of the exact class this header already records twice. Measured 2026-09-07: 149 bash gate tests here were visible to the probe and 99 Python ones were not, on the surface W7 is actively migrating all 149 onto -- so the blind half is the growing half. A session wrote test_gate_fanout_timeout_declarable.py,
    # proved it against a re-planted defect, confirmed `check:ci-pytest` collects it and that the full gate went 9602 -> 9604 passed, and the probe still answered "no NEW or CHANGED check script this stop". Same shape as the nine www gates above: the only way to satisfy the old globs was to write the gate somewhere it does not belong, i.e. to let the probe dictate layout.
    ".ci/rediacc_ci/tests/gates/test_gate_*.py",
    ".claude/hooks/stop/test-*.sh",
    ".claude/hooks/test-*.sh",
    # The pytest roots in pyproject.toml `testpaths` that the globs above do not reach, and the hook suites' python spelling. Without them an edit to a file here was invisible to the probe.
    ".claude/rediacc_hooks/tests/test_*.py",
    ".claude/hooks/stop/test-*.py",
)
PYTEST_GATE_KEY = "check:ci-pytest"
# UPGRADE GUARD (v10). Tick identity is the hash of the RENDERED line, and the v10 store rewrite changed rendering, so the first stop after an upgrade can see every historical [x] as "new" (791 in the live store). A flood of ticks is bookkeeping drift, not 791 simultaneous fixes: absorb silently with one systemMessage line instead of asking the judge about ancient history.
TICK_FLOOD = int(os.environ.get("WORKLIST_REGGATE_TICK_FLOOD", "20"))


def reggate_path(worklist, session_id):
    return worklist.with_suffix(".reggate-%s" % (session_id or "unknown")[:8])


def load_reggate(path):
    """(state, forgot). See the module docstring's FAIL SAFE contract."""
    default = {"head": "", "seen_ticks": [], "fixsets": {}, "gate_runs": {}}
    if not path.exists():
        return default, False
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        ok = (
            isinstance(d, dict)
            and isinstance(d.get("head"), str)
            and isinstance(d.get("seen_ticks"), list)
            and all(isinstance(t, str) for t in d.get("seen_ticks", []))
            and isinstance(d.get("fixsets"), dict)
            and all(
                isinstance(v, dict) and v.get("verdict") in REGGATE_VERDICTS
                for v in d.get("fixsets", {}).values()
            )
            and isinstance(d.get("gate_runs"), dict)
        )
    except (OSError, ValueError):
        ok, d = False, None
    if not ok:
        return default, True
    return d, False


def append_ledger(branch, record, root=None):
    """Append ONE ledger record under a blocking flock, via the store's own primitive.

    Append-only JSONL, folded on read, NEVER edited. It is deliberately not an `ev:` kind in the item store: wl_epic.py's header records why, and it learned it the hard way -- `compact()` rewrites that log down to the minimal item-reproducing set, so a novel event kind there is SILENTLY DESTROYED. `.requests`, `.intents` and `.epics` are the precedents this follows.
    """
    path = debt_path(branch, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(record)
    rec.setdefault("at", C.stamp_now())
    rec.setdefault("br", branch or "")
    # Pass the DICT: _append_lines serialises each payload itself. Handing it a pre-encoded string double-encodes it into a JSON string containing JSON, which read_ledger then rejects as malformed -- silently emptying the ledger and, with it, the budget.
    S._append_lines(path, path.with_suffix(".lock"), [rec])
    return rec


def read_ledger(branch, root=None):
    """(records, forgot), same FAIL SAFE contract as load_reggate.

    `forgot` means the ledger could not be read as written. It is reported rather than swallowed, because a budget computed from an unreadable ledger reads as a FRESH budget -- the most permissive answer possible, and exactly the shape that would let the cap silently stop capping.
    """
    return read_ledger_path(debt_path(branch, root))


def read_ledger_path(path):
    """(records, forgot) for one ledger file, under read_ledger's FAIL SAFE contract."""
    path = pathlib.Path(path)
    if not path.exists():
        return [], False
    records, forgot = [], False
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                forgot = True
                continue
            if isinstance(d, dict) and isinstance(d.get("kind"), str):
                records.append(d)
            else:
                forgot = True
    except OSError:
        return [], True
    return records, forgot


def ledger_paths(root=None):
    """Every per-branch debt ledger under debt_dir, sorted.

    SKIPS `*.*.jsonl`. The shape-duplication advisory writes `<branch>.shapedup-wide.jsonl` beside the ledgers, holding only `ask` records; a reader that folded those as ledgers would count a second "branch" per real one. A branch slug never carries a dot in this repo's `MMDD-N` naming, so a dotted stem is never a ledger.
    """
    d = debt_dir(root)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.jsonl") if p.is_file() and "." not in p.stem)


def debt_due(record, live_branch, now=None):
    """Is this debt due? (agent/plans/PLAN-reggate-debt-collection.md D1.)

    True when the debt's branch is not the live one, or when `at + REGGATE_DEBT_GRACE_MIN` has passed. `main` is never "the other branch": a `main.jsonl` debt is due by the clock alone, because main is where every branch lands rather than a branch that landed.

    IT REPLACED `branch_merged`, which ignored its argument and answered `rev-list --count origin/main..HEAD == "0"` for the CURRENT HEAD. Under `gh pr merge --rebase` a landed branch's shas are rewritten, so that probe never saw a merge from the branch itself, and a fresh branch with no commits read as merged. The one-branch rule makes the question unnecessary: a ledger whose branch is not the live one has landed or been abandoned, and either way it is due.

    An unparseable `at` is DUE: a debt whose clock cannot be read must not be held open forever by its own corruption.
    """
    br = str((record or {}).get("br") or "")
    if br != "main" and br != str(live_branch or ""):
        return True
    at = C.parse_stamp(str((record or {}).get("at") or ""))
    if at is None:
        return True
    now = now or C.utcnow()
    return at + datetime.timedelta(minutes=REGGATE_DEBT_GRACE_MIN) <= now


def cap_defers(remaining, forgot, outstanding):
    """The cap's guard, as the wl_checks block site spells it: defer only when the ledger read cleanly, the budget is spent, and fewer than REGGATE_MAX_DEBTS debts are outstanding on the live branch. Any other answer leaves the demand to block normally."""
    return not forgot and remaining <= 0 and outstanding < REGGATE_MAX_DEBTS


def paid_sigs(records):
    """Sigs one ledger has paid: a `discharge`, or a `retire` carrying its operator `ASKED:` stamp. A retire without the stamp pays nothing (D5)."""
    out = {r.get("sig") for r in records if r.get("kind") == "discharge"}
    out |= {
        r.get("sig")
        for r in records
        if r.get("kind") == "retire" and RETIRE_ASKED_RE.match(str(r.get("asked") or ""))
    }
    out.discard(None)
    return out


def budget_state(branch, root=None, live=None):
    """(charged, remaining, debts, forgot) folded from the ledger; `debts` are the outstanding (unpaid) ones.

    THE COUNTER RESETS WHEN THE LEDGER'S BRANCH IS NOT THE LIVE ONE; DEBTS DO NOT. A branch that landed has a counter nobody can charge again, while its outstanding debts become due (debt_due). That inversion is the point: landing is what makes a debt payable, and there is no ordering in which landing discharges one. `live` defaults to the checkout's current branch.
    """
    records, forgot = read_ledger(branch, root)
    paid = paid_sigs(records)
    charged = sum(1 for r in records if r.get("kind") == "charge")
    debts = [r for r in records if r.get("kind") == "debt" and r.get("sig") not in paid]
    if live is None:
        live = C.git_branch(root or C.project_root(C.project_start()))
    if (branch or "") != (live or ""):
        charged = 0
    return charged, max(0, REGGATE_CAP - charged), debts, forgot


def charge(branch, sig, reason, root=None):
    """Spend one unit of budget. Called ONLY on a `proven` settle or at the cap."""
    return append_ledger(branch, {"kind": "charge", "sig": sig, "why": reason}, root=root)


# --------------------------------------------------------------------------- DEBT COLLECTION (agent/plans/PLAN-reggate-debt-collection.md D3-D7).
#
# The cap above turns a demand into a `debt` record. Until this half landed nothing read those records back: no code wrote `materialize` or `discharge`, so a capped demand was a permanent deferral. Here a due debt becomes a worklist item exactly once, a changed named artifact discharges it, an operator minute retires it, and the CI gate (.ci/rediacc_ci/quality/reggate_debt.py) folds the same ledgers through these same readers.
# ---------------------------------------------------------------------------
BACKLOG_PLAN = "agent/plans/PLAN-reggate-debt-collection.md"
BACKLOG_TITLE = "reggate debt backlog"
LEGACY_REL = ".ci/policy/reggate-debt-legacy.json"
# Epics truncate one record's covers at wl_epic.EPIC_MAX_COVERS; a first import of a hundred debts is attached in chunks of this size.
_EPIC_CHUNK = 64


def debt_entries(root=None):
    """One dict per `debt` record across every ledger, in ledger then file order.

    Keys: sig, br (the record's branch, else the ledger's), ledger (the file stem, which append_ledger maps back to the same file), at, blind_spot, surface, artifact, paid (a discharge or a stamped retire), retired, discharged, item (the materialized item id, or "").
    """
    out = []
    for path in ledger_paths(root):
        records, _forgot = read_ledger_path(path)
        discharged = {r.get("sig") for r in records if r.get("kind") == "discharge"}
        paid = paid_sigs(records)
        items = {
            r.get("sig"): str(r.get("item") or "")
            for r in records
            if r.get("kind") == "materialize"
        }
        for r in records:
            if r.get("kind") != "debt":
                continue
            sig = str(r.get("sig") or "")
            out.append(
                {
                    "sig": sig,
                    "br": str(r.get("br") or path.stem),
                    "ledger": path.stem,
                    "at": str(r.get("at") or ""),
                    "blind_spot": str(r.get("blind_spot") or ""),
                    "surface": str(r.get("surface") or ""),
                    "artifact": str(r.get("artifact") or ""),
                    "paid": sig in paid,
                    "discharged": sig in discharged,
                    "retired": sig in paid and sig not in discharged,
                    "item": items.get(sig, ""),
                }
            )
    return out


def due_debts(root, live_branch, now=None):
    """Debts that are due, unpaid and not yet materialized."""
    return [
        e
        for e in debt_entries(root)
        if not e["paid"] and not e["item"] and debt_due(e, live_branch, now)
    ]


def debt_item_text(entry, me8):
    """The item a due debt becomes. The blind spot rides VERBATIM: it is the judge's finding, and a paraphrase is how a debt loses what it was about."""
    return "reggate-debt:%s (%s) %s -- branch %s, surface %s, named artifact %s" % (
        entry["sig"][:8],
        (me8 or "")[:8],
        entry["blind_spot"],
        entry["br"],
        entry["surface"] or "none",
        entry["artifact"] or "(none)",
    )


@contextlib.contextmanager
def _collect_lock(root=None):
    """One collector at a time across sessions sharing this tree: two stops folding the same due set would each add the same items. The lock file has no `.jsonl` suffix, so ledger_paths never reads it."""
    import fcntl

    d = debt_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "collect.lock", "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _live_plan_epic(loop_plans):
    """The first epic carrying one of the live PR's plans, or ""."""
    import wl_epic as E

    plans = set(loop_plans or ())
    if not plans:
        return ""
    return next((eid for eid, rec in E.load_epics().items() if rec.get("plan") in plans), "")


def backlog_epic(me8):
    """The one backlog epic carrying this plan, minted on first use."""
    import wl_epic as E

    for eid, rec in E.load_epics().items():
        if rec.get("plan") == BACKLOG_PLAN and rec.get("title") == BACKLOG_TITLE:
            return eid
    return E.new_epic(me8, BACKLOG_TITLE, plan=BACKLOG_PLAN)


def _attach(me8, epic_id, ids):
    import wl_epic as E

    for k in range(0, len(ids), _EPIC_CHUNK):
        E.add_to_epic(me8, epic_id, ids[k : k + _EPIC_CHUNK])


def materialize(root, worklist, me8, live_branch, loop_plans=(), now=None):
    """Turn every due, unpaid, unmaterialized debt into ONE worklist item, once. -> [(sig, item_id)].

    One `add_items` append for the whole set, then one `materialize` record per debt in its own ledger, which is what makes a second stop add nothing. A debt on the live branch joins the live PR plan's epic, so it blocks like any item there; any other debt (and a live one when no PR plan epic exists) joins the backlog epic, which carries this plan and stays one queued line until this plan is the live PR's.
    """
    with _collect_lock(root):
        due = due_debts(root, live_branch, now)
        if not due:
            return []
        ids = S.add_items(worklist, me8, [debt_item_text(e, me8) for e in due], root=root)
        for e, iid in zip(due, ids, strict=True):
            append_ledger(
                e["ledger"], {"kind": "materialize", "sig": e["sig"], "item": iid}, root=root
            )
        live_epic = _live_plan_epic(loop_plans)
        on_live = [
            iid for e, iid in zip(due, ids, strict=True) if live_epic and e["br"] == live_branch
        ]
        rest = [iid for iid in ids if iid not in set(on_live)]
        if on_live:
            _attach(me8, live_epic, on_live)
        if rest:
            _attach(me8, backlog_epic(me8), rest)
        return [(e["sig"], iid) for e, iid in zip(due, ids, strict=True)]


def legacy_sigs(root=None):
    """The frozen legacy set from LEGACY_REL, or an empty set when the file is absent or unreadable."""
    if root is None:
        root = C.project_root(C.project_start())
    try:
        data = json.loads((pathlib.Path(root) / LEGACY_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    sigs = data.get("sigs") if isinstance(data, dict) else None
    return {s for s in sigs if isinstance(s, str)} if isinstance(sigs, list) else set()


def debt_status(root=None, legacy=None):
    """(open, legacy_open, oldest_date) over every unpaid debt; oldest_date is "" when none is open."""
    legacy = legacy_sigs(root) if legacy is None else legacy
    unpaid = [e for e in debt_entries(root) if not e["paid"]]
    if not unpaid:
        return 0, 0, ""
    oldest = min((e["at"] for e in unpaid if e["at"]), default="")
    return len(unpaid), sum(1 for e in unpaid if e["sig"] in legacy), oldest[:10]


# A path a session names on the debt's item (`worklist.py --update <me> <id> artifact:<path>`), tried beside the debt's own named artifact.
_ARTIFACT_TOKEN = re.compile(r"(?<!\S)artifact:(\S+)")


def _clean_rel(rel):
    """A repo-relative path, or "" for anything that climbs out or is absolute (the prefix strip, never `.lstrip("./")`: see prove_named_artifact)."""
    rel = str(rel or "").strip().strip("`'\"")
    while rel.startswith("./"):
        rel = rel[2:]
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        return ""
    return rel


def _dirty_paths(root):
    """Every path `git status --porcelain` names, or an empty set when git cannot answer. A broken git proves NOTHING here, the opposite of _is_dirty's err-toward-True: that one decides whether to run a gate, this one whether a debt is paid."""
    status = C._git(root, "status", "--porcelain", "--untracked-files=all") or ""
    return {_porcelain_path(ln) for ln in status.splitlines() if ln.strip()}


def _committed_after(root, rel, at):
    """The committer date of the last commit touching `rel` when it is later than `at`, else ""."""
    out = (C._git(root, "log", "-1", "--format=%cI", "--", rel) or "").strip()
    if not out:
        return ""
    try:
        when = datetime.datetime.fromisoformat(out)
    except ValueError:
        return ""
    return out if when > at else ""


def _artifact_reachable(root, scripts, rel):
    """True unless `rel` is a check script (CHECK_SCRIPT_GLOBS) that nothing `npm run ci` runs. A unit test, an E2E case or an ops step is not a gate and needs no key; a gate that is defined but never run proves nothing."""
    if not any(fnmatch.fnmatch(rel, pat) for pat in CHECK_SCRIPT_GLOBS):
        return True
    key = _gate_key(scripts, rel)
    if key and gate_reachable(scripts, key, root):
        return True
    if PYTEST_GATE_KEY in scripts and pytest_collects(rel, root):
        return gate_reachable(scripts, PYTEST_GATE_KEY, root)
    if _citation_matches_gate(rel, root):
        return True
    # The hook suites run in CI without a check:* key (prove_new_gate accepts them on change for the same reason).
    return rel.startswith(".claude/hooks/")


def prove_debt(root, scripts, rel, at, dirty):
    """(proven, proof) for one candidate path against one debt's `at` (D4).

    Proven when the path exists, changed after the debt (dirty in this tree, or last committed after `at`), and, when it is a check script, is reachable from `npm run ci`. The two proofs say which one applied, because they differ in strength: the commit-date proof shows a case was written after the debt, not that it fails on the defect.
    """
    rel = _clean_rel(rel)
    when = C.parse_stamp(at)
    if not rel or when is None or not (pathlib.Path(root) / rel).exists():
        return False, ""
    if rel in dirty or any(d.endswith("/") and rel.startswith(d) for d in dirty):
        proof = "dirty-tree: %s changed in this tree after the debt (%s)" % (rel, at)
    else:
        committed = _committed_after(root, rel, when)
        if not committed:
            return False, ""
        proof = (
            "commit-date: %s last committed %s, after the debt (%s); this shows a case was "
            "written after the debt, not that it fails on the defect" % (rel, committed, at)
        )
    if not _artifact_reachable(root, scripts, rel):
        return False, ""
    return True, proof


def discharge_scan(root, worklist, me8, items=None):
    """Discharge every unpaid debt whose named artifact (or an `artifact:<path>` on its item) proves it. -> [(sig, artifact)].

    HOOK-ONLY. No CLI verb writes `discharge`: a hand tick of a debt's item changes nothing in the ledger, so the gate still counts the debt unpaid (C5). On proof the hook appends `{"kind": "discharge", ...}` and ticks the item with `discharge:<sig8> <artifact>`. `items` is the fold's item list, read for the `artifact:` tokens and to skip re-ticking a closed item.
    """
    by_id = {r.get("id"): r for r in (items or [])}
    out: list[tuple[str, str]] = []
    with _collect_lock(root):
        unpaid = [e for e in debt_entries(root) if not e["paid"]]
        if not unpaid:
            return out
        scripts = package_scripts(root)
        dirty = _dirty_paths(root)
        for e in unpaid:
            rec = by_id.get(e["item"]) or {}
            notes = "%s\n%s" % (rec.get("text", ""), rec.get("line", ""))
            cands = [e["artifact"], *_ARTIFACT_TOKEN.findall(notes)]
            for cand in dict.fromkeys(c for c in cands if _clean_rel(c)):
                ok, proof = prove_debt(root, scripts, cand, e["at"], dirty)
                if not ok:
                    continue
                rel = _clean_rel(cand)
                append_ledger(
                    e["ledger"],
                    {"kind": "discharge", "sig": e["sig"], "artifact": rel, "proof": proof},
                    root=root,
                )
                if e["item"] and rec.get("state", " ") != "x":
                    S.set_state(
                        worklist, me8, e["item"], "x", "discharge:%s %s" % (e["sig"][:8], rel)
                    )
                out.append((e["sig"], rel))
                break
    return out


def retire(root, worklist, me8, sig8, asked, reason, asked_ok, items=None):
    """`worklist.py --reggate-retire <me> <sig8> ASKED:<YYYY-MM-DDTHH:MM>Z <reason>` (D5). -> (rc, text).

    The one escape for a debt whose subject is gone. Refused unless the minute matches an operator answer in the lead transcript (`asked_ok`, the check `--review-mark waived` uses), the sig names exactly one unpaid debt, and a reason is given. Writes `retire` with the stamp, which is the only form the gate counts as paid, and closes the debt's item.
    """
    if not RETIRE_ASKED_RE.match(str(asked or "")):
        return 2, "reggate-retire: %r is not ASKED:<YYYY-MM-DDTHH:MM>Z" % (asked,)
    reason = str(reason or "").strip()
    if not reason:
        return 2, "reggate-retire: a reason is required (why the debt's subject is gone)"
    sig8 = str(sig8 or "").strip().lower()
    if len(sig8) < 6 or not re.fullmatch(r"[0-9a-f]+", sig8):
        return 2, "reggate-retire: %r is not a debt sig (6 or more hex characters)" % (sig8,)
    with _collect_lock(root):
        hits = [e for e in debt_entries(root) if e["sig"].startswith(sig8)]
        if not hits:
            return 2, "reggate-retire: no reggate debt has sig %s" % sig8
        open_hits = [e for e in hits if not e["paid"]]
        if not open_hits:
            return 2, "reggate-retire: debt %s is already paid" % sig8
        if len({e["sig"] for e in open_hits}) > 1:
            return 2, "reggate-retire: sig %s is ambiguous (%s)" % (
                sig8,
                ", ".join(sorted({e["sig"] for e in open_hits})),
            )
        if asked_ok is None or not asked_ok(asked):
            return 2, (
                "reggate-retire: %s matches no AskUserQuestion answer in this session's transcript: "
                "ask the operator first, then retire with that answer's minute" % asked
            )
        e = open_hits[0]
        append_ledger(
            e["ledger"],
            {"kind": "retire", "sig": e["sig"], "asked": asked, "reason": reason[:300], "by": me8},
            root=root,
        )
        state = ({r.get("id"): r for r in (items or [])}.get(e["item"]) or {}).get("state", " ")
        if e["item"] and state != "x":
            S.set_state(worklist, me8, e["item"], "x", "retire:%s %s" % (e["sig"][:8], asked))
    return 0, "reggate-retire: debt %s retired (%s)" % (e["sig"], asked)


def unpaid_listing(root=None):
    """The bare `--reggate-retire <me>` answer: every unpaid debt, one line each."""
    unpaid = [e for e in debt_entries(root) if not e["paid"]]
    lines = ["reggate-retire: %d unpaid reggate debt(s)" % len(unpaid)]
    lines += [
        "  %s  %s  %s  %s" % (e["sig"][:12], e["br"], e["at"][:10], e["blind_spot"][:100])
        for e in unpaid
    ]
    return "\n".join(lines)


def save_reggate(path, state):
    # Whole-file rewrite is correct here for the same reason as the handover: the marker is per-session, so there is no second writer to race.
    with contextlib.suppress(OSError):
        path.write_text(json.dumps(state, indent=1), encoding="utf-8")


def _tick_id(line):
    return hashlib.sha1(line.strip().encode("utf-8", "replace")).hexdigest()[:12]


def mine_tick_ids(items, session_id):
    return [
        _tick_id(rec["line"])
        for rec in items
        if rec["state"] == "x" and C.owned_by_me(rec.get("owner"), session_id)
    ]


def _hash_file(path):
    try:
        return hashlib.sha1(pathlib.Path(path).read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def seed_gate_hashes(root):
    """Hashes of every existing check script, recorded at marker init so only scripts that are NEW or CHANGED after that point ever count as candidate proof (or get run). Without this seed, the first fix-signal stop in a real repo would treat ~all 90 existing gates as candidates and try to run them."""
    stamp = C.stamp_now()
    out = {}
    for pat in CHECK_SCRIPT_GLOBS:
        for f in glob.glob(os.path.join(str(root), pat)):
            rel = os.path.relpath(f, str(root)).replace(os.sep, "/")
            digest = _hash_file(f)
            if digest:
                out[rel] = {"hash": digest, "exit": -3, "at": stamp}  # -3 = seeded, never run
    return out


# A path-shaped token with an extension. Used only to decide whether a tick's EVIDENCE names code; the tick text itself is prose and is never parsed further.
_EVIDENCE_PATH = re.compile(r"(?<![\w/])((?:[\w.@-]+/)+[\w.@-]+\.[A-Za-z0-9]+)")


def tick_touches_code(line):
    """Does this tick's evidence name a file that is not documentation?

    The operator's rule: only code-touching ticks are asked. This mirrors the docs-only filter already applied to commits, and it FAILS TOWARD ASKING -- a tick whose evidence names no path at all is asked, because "no path" is not evidence that nothing shipped, and silently dropping a fix is the failure this whole mechanism exists to prevent.
    """
    paths = _EVIDENCE_PATH.findall(line or "")
    if not paths:
        return True
    return not all(p.startswith("docs/") or p.endswith(".md") for p in paths)


# Paths that are CI-gate MAINTENANCE rather than product code. Derived by checking real commits, not guessed: the first version of this list omitted .github/workflows and scripts/data and therefore answered False for 3148399c9, a commit that is nothing BUT gate maintenance.
GATE_ARTIFACT_PREFIXES = (
    "scripts/gates/check-",
    "scripts/data/",  # gate seeds and baselines
    "scripts/lib/",  # gate-support libraries: verified 2026-09-05 that
    # every consumer is a check script or a test, never product runtime (action-refs, blocker-validator, gate-header, shrink-only-baseline, controls...) NOT "packages/" -- that was the first version and it is WRONG in the most expensive direction: it marks EVERY file under packages/ as gate maintenance, so all product code would earn the hint. Caught by case 96 in a fixture repo,
    # where packages/cli/src/real.ts came back True. Sampling 7 real commits had missed it because none touched product code under packages/ -- testing against the data you happen to have is how a rule ships inverted. Package-local gates are matched by GLOB below instead.
    ".ci/scripts/quality/",
    ".ci/scripts/security/",
    ".ci/scripts/test/",
    # The ported half of the same estate. Without it a fix whose regression home is a Python gate test counts as touching no gate artifact at all, which is the same blindness CHECK_SCRIPT_GLOBS carried, one list further down.
    ".ci/rediacc_ci/tests/",
    ".claude/hooks/",
    ".github/workflows/ci-",  # the quality workflows a gate is wired into
)
GATE_ARTIFACT_EXACT = ("scripts/ci-runner/manifest.ts", "package.json")
# Package-local gates live beside their package, so they need a GLOB, not a prefix. CHECK_SCRIPT_GLOBS' own header records why they must be reachable at all: omitting them made the gate probe structurally blind to nine real gates.
GATE_ARTIFACT_GLOBS = (
    "packages/*/scripts/check-*.ts",
    "packages/*/scripts/check-*.sh",
)

# BOOKKEEPING, ignored rather than counted. Every commit in this repo carries agent/ session state and often docs; requiring them to be gate artifacts made the probe answer False for 89189c0b5, which touches one hook file and two agent files. This mirrors the docs-only skip below: prose is not the subject.
GATE_NEUTRAL_PREFIXES = ("agent/", "docs/")


def _diff_tree_files(root, sha):
    """The real files one commit touched, root-commit safe. `[]` on any git failure or an unresolvable ref.

    FACTORED OUT of `gate_only_fixset` and `fix_signals`, which each carried this exact root-commit-retry shape independently -- the third copy of one pattern, found while grounding the judge's prompt in real data rather than narrated claims (agent/plans/PLAN-judge-prompt-trap-conflation.md). `C._git` itself never raises (it returns `""` on any failure), so the `try/except` here is
    belt-and-suspenders against a future change to that contract, matching the caller this replaces.
    """
    try:
        files = C._git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", sha).splitlines()
    except Exception:
        # Safe to ignore: C._git already turns a git or spawn failure into "", so this only guards a programming error, and [] is the documented answer for an id that is not a tree-ish (a tick id) that every caller handles.
        return []
    if files:
        return [f.strip() for f in files if f.strip()]
    # A ROOT commit has no parent, so `diff-tree` prints nothing. Retry with `--root`, which does list a root commit's files. Caught by case 96, whose fixture repo's first commit IS the root.
    try:
        files = C._git(
            root, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", sha
        ).splitlines()
    except Exception:
        # Safe to ignore, for the reason on the first arm: C._git never raises on a git failure, and [] is the documented answer.
        return []
    return [f.strip() for f in files if f.strip()]


def _porcelain_path(line):
    """The path one `git status --porcelain` line names (the NEW path of a rename).

    `C._git` strips the WHOLE output, so the first line's leading space is gone: ` M a.ts` arrives as `M a.ts`, and the old `ln[3:]` answered `ackages/x/a.ts` for `packages/x/a.ts` (found 2026-09-24 by the R.1 fixture of agent/plans/PLAN-stop-hook-retro-20260924.md). A two-character status is followed by one space; a stripped one-character status is not.
    """
    path = line[2:] if line[1:2] == " " and line[2:3] != " " else line[3:]
    return path.split(" -> ", 1)[-1].strip().strip('"')


_SUBPROJECT_RE = re.compile(r"^([-+])Subproject commit ([0-9a-f]{7,40})", re.MULTILINE)
_NULL_SHA = re.compile(r"^0+$")


def _submodule_files(root, path, old, new):
    """`<path>/<file>` for every file the submodule at `path` changed between `old` and `new`, or [] when either is missing or the range does not resolve there."""
    if not old or not new or _NULL_SHA.match(old) or _NULL_SHA.match(new) or old == new:
        return []
    sub = os.path.join(str(root), path)
    listed = C._git(sub, "diff", "--name-only", old, new) or ""
    return ["%s/%s" % (path, f.strip()) for f in listed.splitlines() if f.strip()]


def _gitlink_moves_status(root, paths):
    """{path: (old, new)} for each of `paths` that is a gitlink whose working-tree commit differs from HEAD's, read from `git diff HEAD -- <path>`."""
    out = {}
    for path in paths:
        # A gitlink is a checked-out repository; a plain dirty file never costs a git call here.
        if not os.path.exists(os.path.join(str(root), path, ".git")):
            continue
        diff = C._git(root, "diff", "--no-color", "--no-ext-diff", "HEAD", "--", path) or ""
        if "Subproject commit" not in diff:
            continue
        sides = dict(_SUBPROJECT_RE.findall(diff))
        if "-" in sides and "+" in sides:
            out[path] = (sides["-"], sides["+"])
    return out


def _gitlink_moves_commit(root, sha):
    """{path: (old, new)} for each gitlink one commit moved, read from `git diff-tree --raw` (mode 160000)."""
    out = {}
    raw = C._git(root, "diff-tree", "--no-commit-id", "-r", "--raw", "--abbrev=40", sha) or ""
    for line in raw.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.lstrip(":").split()
        if len(parts) >= 4 and "160000" in (parts[0], parts[1]) and path:
            out[path.strip()] = (parts[2], parts[3])
    return out


def _expand_gitlinks(root, moves):
    files = []
    for path, (old, new) in moves.items():
        files.extend(_submodule_files(root, path, old, new))
    return files


def fixset_files(root, ids, live_paths=None):
    """(files, provenance). The real files THIS fix-set touched, computed by git, never narrated. `provenance` is `"diff-tree"` when every id resolved to a real commit, or `"status-fallback"` when nothing did and the answer is the whole working tree's `git status --porcelain` instead -- named so a caller can tell the judge WHICH ground truth it is being shown, since the two answer
    different questions (agent/plans/PLAN-sweep-obligation-carry-forward.md task "Label the injected file list with its provenance").

    `ids` are fix_signals' own ids: commit shas for a commit-based fix-set, a single tick id for a tick-based one. A tick id is not a tree-ish, so `_diff_tree_files` answers `[]` for it -- correct, because a tick-based fix-set's evidence is necessarily still UNCOMMITTED. Falls back to `git status --porcelain`, the same ground truth `gate_only_fixset`'s own docstring already calls
    out as the honest answer for that shape, so a hallucinated bulk transform can be checked against what git ACTUALLY shows changed rather than trusted from the judge's own prose (agent/plans/PLAN-judge-prompt-trap-conflation.md).

    `live_paths` (wl_roster.live_writer_paths) is subtracted on the status arm ONLY, under provenance `"status-minus-live-writers"` (agent/plans/PLAN-stop-hook-retro-20260924.md R.1): the dirty tree is shared, and a writer's uncommitted edits are not the lead's fix-set while the writer is live or an item leased to it is un-ticked (R20260925.2). The obligation for them belongs in that writer's own tick: when `ids` is a tick whose item had agent lease workers (`live_paths.by_tick`), the answer is those workers' paths intersected with the dirty tree, under provenance `"item-writers"`. A path covers every file below it. A commit-based fix-set is never trimmed.

    A MOVED GITLINK IS EXPANDED into `<sub>/<file>` for every file the submodule's own range changed, on both arms (R20260924.19). The gitlink path alone stays listed. At 16:23:57Z on 2026-09-24 the judge said "no test files appear in this fix-set" while the tests sat in private/account commit aea435154, because the list carried `private/account` and nothing under it.
    """
    files = set()
    for i in ids or []:
        found = _diff_tree_files(root, i)
        files.update(found)
        if found:
            files.update(_expand_gitlinks(root, _gitlink_moves_commit(root, i)))
    if files:
        return sorted(files), "diff-tree"
    status = C._git(root, "status", "--porcelain") or ""
    dirty = {_porcelain_path(ln) for ln in status.splitlines() if ln.strip()}
    dirty = {rel for rel in dirty if not _hook_refresh_only(root, rel)}
    files.update(dirty)
    files.update(_expand_gitlinks(root, _gitlink_moves_status(root, sorted(dirty))))
    # A TICK ANSWERS FOR ITS OWN WRITERS (agent/plans/PLAN-stop-hook-retro-20260925.md R20260925.2). An item that had agent lease workers is asked about exactly the dirty files those workers changed, not the whole tree: at 19:47:31 on 2026-09-24 the judge picked a "class" out of another writer's uncommitted rewrites. An item that never had a worker lease keeps the status arm below.
    by_tick = getattr(live_paths, "by_tick", None) or {}
    own = [by_tick[i] for i in ids or [] if i in by_tick]
    if own:
        mine = set().union(*own)
        return sorted(f for f in files if _covers(mine, f)), "item-writers"
    if live_paths:
        kept = {f for f in files if not _covers(live_paths, f)}
        if kept != files:
            return sorted(kept), "status-minus-live-writers"
    return sorted(files), "status-fallback"


QUEUE_REL = "agent/plans/QUEUE.md"


def _hook_refresh_only(root, rel):
    """True when the dirty `rel` is agent/plans/QUEUE.md and its only difference from HEAD lies inside the `## In flight` markers, which the Stop hook itself rewrites on every stop (wl_planqueue.refresh_inflight, 9b22294e6). That rewrite is the hook's runtime state, not the session's work, and counting it put the proof and sweep questions on every stop (test_r1_a_live_writers_edit_asks_no_sweep_or_proof). Any other change to the file keeps it in the fix-set."""
    if rel != QUEUE_REL:
        return False
    import wl_planqueue as Q

    try:
        now = (pathlib.Path(root) / rel).read_text(encoding="utf-8")
    except OSError:
        return False
    head = C._git(root, "show", "HEAD:%s" % rel)
    if head is None:
        return False

    # Both sides get the same placeholder body: a HEAD that predates the section gains `## In flight` and its intro from `with_inflight`, exactly as the refresh did.
    # The progress block is re-rendered from the plans on every stop, so it is masked the same way (wl_planqueue.without_progress).
    def masked(text):
        return Q.without_progress(Q.with_inflight(text, "")).rstrip("\n")

    return masked(now) == masked(head)


def _covers(paths, rel):
    """True when the `git status` path `rel` is one of `paths` or lies under one: a writer's Bash-made directory removal (`rm -rf .claude/oracles`) covers every file below it (R20260925.1)."""
    rel = str(rel).rstrip("/")
    for raw in paths or ():
        p = str(raw).rstrip("/")
        if p and (rel == p or rel.startswith(p + "/")):
            return True
    return False


def gate_only_fixset(root, shas):
    """True when every NON-BOOKKEEPING file in the fix-set is a CI-gate artifact.

    ARTIFACTS, NEVER PROSE -- this reads `git diff-tree`, not a commit subject, the same rule fix_signals states for its docs-only skip below.

    WHY IT IS A HINT AND NOT A SKIP. A gate-maintenance fix can still deserve a gate of its own, so this never suppresses a fix-set; it tells the judge what it is looking at, so question (0) has something to bite on. Measured 2026-09-04/05: two sessions ran a self-generating loop where writing gate A produced the finding that gate B was needed, and every one of those findings had
    ALREADY been caught by an existing gate. Nothing told the judge the fix-set was gate machinery.

    Fails toward saying nothing extra: any git error, an empty fix-set, or a fix-set that is ONLY bookkeeping returns False rather than skipping the question. That includes a TICK-BASED fix-set: fix_signals' ids are commit shas OR tick ids, and a tick id is not a tree-ish, so `git diff-tree` fails and this answers False. Correct by construction -- an uncommitted fix has no file
    list to classify -- and it means the hint is a commit-fix-set feature.
    """
    if not shas:
        return False
    seen = False
    for sha in shas:
        files = _diff_tree_files(root, sha)
        if not files:
            return False
        for raw in files:
            path = raw.strip()
            if not path or any(path.startswith(pre) for pre in GATE_NEUTRAL_PREFIXES):
                continue
            if (
                path in GATE_ARTIFACT_EXACT
                or any(path.startswith(pre) for pre in GATE_ARTIFACT_PREFIXES)
                or any(fnmatch.fnmatch(path, pat) for pat in GATE_ARTIFACT_GLOBS)
            ):
                seen = True
                continue
            return False
    return seen


def fix_signals(root, items, session_id, state):
    """(descriptions, ids, new_tick_triples, current_head, banked_only_ids).

    ARTIFACTS, never prose. Primary: commit subjects matching FIX_SUBJECT in marker-head..HEAD. Secondary: newly ticked `- [x]` lines owned by this session, covering the uncommitted-tree default. The skip filter is deliberately narrow: a fix commit touching only docs/** and **/*.md never asks; everything else does, and the judge's four questions sort the one-offs out. A rewound or
    unreachable old head yields an empty log, which reads as no signals and lets head self-heal by advancing.

    `banked_only_ids` is a SEPARATE list from `new_tick_triples`, deliberately: a docs-only tick must be marked seen so it stops being rediscovered every stop, but it must NOT be asked about and must NOT be subjected to the I7 completion-evidence check that `new_tick_triples` feeds elsewhere. Folding it into `new_tick_triples` instead (the first version of this fix) would have made
    that evidence check run over ticks nobody is asking about -- a docs-only tick with a bare `- [x]` line and no evidence would then fail I7 for a reason unrelated to what it actually is. Found in review, not by a control: no `- [x]` docs-only fixture exercised that path.

    `new_tick_triples` is `(tid, line, evidence_text)`, not `(tid, line)`: `evidence_text` is `rec["lastnote"]` when present, the closing note that actually carries the fix's proof, falling back to the full `line` only for markdown-origin items with no structured note. `line` stays the FULL rendered text (accumulated history included) because `tick_touches_code` genuinely needs
    to scan it all for a path; only the I7 evidence check needs the narrower, unpolluted slice. Before this, both consumers shared one accumulated blob, and a tick whose history grew past a few dozen lease/update notes buried its own closing sha under longer worker-id-shaped tokens that a "5 longest hex candidates" heuristic picked first -- the real evidence sat there,
    unchecked."""
    head = C._git(root, "rev-parse", "HEAD")
    commits, new_ticks = [], []
    if state["head"] and head and state["head"] != head:
        for row in C._git(
            root, "log", "--format=%H%x09%s", "%s..%s" % (state["head"], head)
        ).splitlines():
            sha, _, subj = row.partition("\t")
            if not FIX_SUBJECT.match(subj):
                continue
            files = C._git(
                root, "diff-tree", "--no-commit-id", "--name-only", "-r", sha
            ).splitlines()
            if files and all(f.startswith("docs/") or f.endswith(".md") for f in files):
                continue
            commits.append((sha, "%s %s" % (sha[:7], subj)))
    for rec in items:
        if rec["state"] == "x" and C.owned_by_me(rec.get("owner"), session_id):
            line = rec["line"]
            tid = _tick_id(line)
            if tid not in state["seen_ticks"]:
                evidence_text = rec.get("lastnote") or line
                new_ticks.append((tid, line.strip(), evidence_text))
    # ONE UNIT PER STOP, oldest first. Until now every commit and every new tick of a stop were hashed into a SINGLE fix-set, so one verdict had to cover unrelated fixes and the judge's answers wandered across the bundle. Asking per item is what the operator asked for; asking about ALL of them at once would wall a busy stop in behind eight simultaneous demands, so the rest stay
    # unbanked and the next stop picks up the next one.
    #
    # Commits are ONE unit, not one each: they already passed the docs-only filter above and they landed together. THE FLOOD GUARD RUNS BEFORE UNIT SELECTION, and it has to. The caller absorbs a burst of "new" ticks as store-format drift rather than as fixes, and it decides that from `len(new_ticks)`. Handing it one unit first hid the burst from it, so the flood was never absorbed
    # and the very first historical tick blocked instead. Caught by the suite's own tick-flood case, not by review.
    if len(new_ticks) > TICK_FLOOD:
        return (
            ["tick: " + t[:120] for _, t, _ev in new_ticks],
            sorted([t for t, _, _ev in new_ticks]),
            new_ticks,
            head,
            [],
        )
    units = []
    banked_only = []
    if commits:
        units.append(([s for s, _ in commits], [d for _, d in commits], []))
    for tid, line, evidence_text in new_ticks:
        if not tick_touches_code(line):
            # SEEN, NOT ASKED. Without this the id is never added to seen_ticks (the caller only banks what THIS function returns), so it is rediscovered as "new" and re-filtered on every future stop, forever. It still must not enter `ticks`/`ids`: those feed both the ask and the I7 evidence check, and a docs-only tick is neither being asked about nor required to carry evidence.
            banked_only.append(tid)
            continue
        units.append(([tid], ["tick: " + line[:120]], [(tid, line, evidence_text)]))
    if not units:
        return [], [], [], head, banked_only
    ids, descriptions, ticks = units[0]
    if len(units) > 1:
        descriptions = [
            *descriptions,
            "(%d more fix(es) queued for later stops; this one is asked alone)" % (len(units) - 1),
        ]
    # ticks stays (id, line, evidence_text) triples: tick_touches_code needs the FULL line, I7 needs the narrower evidence_text, the absorb/settle sites need the id. Returning ids only here once made the I7 unpack crash, and a crashed hook reads as ALLOW -- fail-open.
    return descriptions, sorted(ids), ticks, head, banked_only


def package_scripts(root):
    try:
        d = json.loads((pathlib.Path(root) / "package.json").read_text(encoding="utf-8"))
        s = d.get("scripts")
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


LOCK_REL = ("scripts", "ci-runner", "gates.lock.json")


def _manifest_entries(root):
    """Every manifest entry, read from `scripts/ci-runner/gates.lock.json`.

    THIS USED TO BE A TYPESCRIPT PARSER WRITTEN IN REGEX, and it shipped wrong. Two functions each ran a finditer over a brace-delimited pattern matching an optional run of whitespace-or-line-comment, then an `id:` string, applied to a 5,700-line TS literal. The whitespace-or-comment alternation in that pattern is a scar: the first version allowed whitespace only, so any entry
    whose leading comment sat INSIDE the brace was invisible, and the reachability gate checked a smaller set while printing a healthy "agrees with all N registrations". Found 2026-08-20 with a planted entry it went green over; it was already hiding check:ci-dockerfile-mirror-resilience and check:ci-tutorial-card-fonts, at 259 of 261 seen. The next TS shape nobody anticipated would
    have done it again, silently and in the same direction.

    The lock is that literal, projected to JSON by `scripts/gen/gen-gates-lock.ts` and kept faithful by `check:ci-gen-gates`, which fails when the two disagree. One parse, no regex archaeology, and a shape error is a JSON error rather than a quietly shorter list.

    RETURNS AN EMPTY LIST WHEN THE LOCK IS ABSENT, deliberately and not by oversight. That matches what the regex version did on an unreadable file, and `check_gate_reachability_coverage.py` DEPENDS on it: its control stubs this lookup to empty and requires the probe's verdict to change, which is how that gate proves it can still detect manifest-blindness. Absence is a broken
    checkout rather than a state to tolerate, and the gate that refuses it is check:ci-gen-gates, not this reader.
    """
    if root is None:
        return []
    try:
        with open(os.path.join(str(root), *LOCK_REL), encoding="utf-8") as fh:
            parsed = json.load(fh)
    except (OSError, ValueError):
        return []
    return [g for g in parsed if isinstance(g, dict) and isinstance(g.get("id"), str)]


def _manifest_gate_ids(root):
    """Gate ids registered in the ci-runner manifest, as a set.

    The runner is the dispatcher for every `check:ci-*` in this repo, so a gate listed there with `gate: true` IS run by `npm run ci` even though nothing in
    package.json ever says `npm run <that key>`.
    """
    return {g["id"] for g in _manifest_entries(root) if g.get("gate") is True}


def _manifest_gate_run_paths(root):
    """`run:` script paths for every `gate: true` manifest entry, as a set.

    A citation of real, ci-runner-scheduled coverage is far more often a FILE PATH ("test_gate_ci_trace_branch.py" or its full repo-relative path, optionally
    with "::test_name" naming the specific case inside it) than the manifest's
    own `id:` string -- both a human and a judge model reach for the path they can see in the tree, not an id that exists only in manifest.ts. Checking ids alone (the first fix here) left that whole citation shape unrecognized and still reporting real coverage as hallucinated. Same regex/parsing approach as _manifest_gate_ids, deliberately: one manifest scan, two views.
    """
    return {
        g["run"]
        for g in _manifest_entries(root)
        if g.get("gate") is True and isinstance(g.get("run"), str)
    }


def _citation_matches_gate(eg, root):
    """True when `eg` names real, `npm run ci`-scheduled coverage: either a manifest `id:` (checked by the caller against `_manifest_gate_ids` directly) or a `run:` file path, exact or with a trailing "::name"/"#name"
    case qualifier and/or a leading "./" stripped."""
    base = re.split(r"::|#", eg, maxsplit=1)[0].strip()
    while base.startswith("./"):
        base = base[2:]
    paths = _manifest_gate_run_paths(root)
    return base in paths or any(p.endswith("/" + base) for p in paths)


def gate_reachable(scripts, target, root=None):
    """Is `target` TRANSITIVELY reachable from the `ci` script via `npm run` references? Transitive, because ci reaches most gates through batch keys. NOT a substring test: a gate's name inside an `echo` is not reachability, and the substring version produced real false positives on this repo."""
    seen, todo = set(), ["ci"]
    runner = False
    while todo:
        k = todo.pop()
        if k in seen or k not in scripts:
            continue
        seen.add(k)
        body = scripts[k]
        # A DISPATCHER, not an npm-run chain. `ci` is `tsx scripts/ci-runner/run.ts`, whose body contains ZERO `npm run` references -- it schedules from manifest.ts instead. Walking npm-run edges alone therefore returned False
        # for EVERY gate in this repo, check:ci-shell-commands and check:ci-dead-bash
        # included, and reported each new gate as "defined but never run". A probe that cannot pass is the same defect as a check that cannot fail: it was rejecting correctly-wired gates and demanding they be re-wired.
        if "ci-runner/run.ts" in body:
            runner = True
        todo.extend(re.findall(r"npm run\s+(?:--silent\s+)?([A-Za-z0-9:._-]+)", body))
    if target in seen:
        return True
    return runner and target in _manifest_gate_ids(root)


def prove_named_artifact(root, artifact):
    """(proven, note) for a case on ANY surface, by the path the judge named.

    THE GLOB PROBE BELOW CAN ONLY SEE ONE SURFACE. It matches check-*.ts, check-*.sh and the two test suites, so a fix whose regression home is an E2E case, an ops step, an install script or a unit test had no acceptable answer at all: the only thing it could prove was a static gate, which for a behavioural defect asserts that the source still looks right. Enumerating the other
    five here would rot the moment a sixth appears, so this asks a different question -- the judge names the path, and this checks whether that path CHANGED in this session's tree.

    Deliberately weaker than the glob probe, and it says so: this proves the
    case was written, not that it runs or that it fails on the defect. The
    surface's own file in `.claude/skills/testing/` names the run that would. A path that does not exist, or exists unchanged, proves nothing.
    """
    # `.lstrip("./")` was the first spelling and it is wrong: lstrip takes a CHARACTER SET, so `.claude/hooks/...` came back as `claude/hooks/...` and every hook-surface artifact was reported as nonexistent. Strip the prefix.
    rel = str(artifact or "").strip()
    while rel.startswith("./"):
        rel = rel[2:]
    if not rel or ".." in rel or rel.startswith("/"):
        return False, ""
    full = pathlib.Path(root) / rel
    if not full.exists():
        return False, "named artifact %s does not exist" % rel
    if not _is_dirty(rel, root):
        return False, "named artifact %s exists but this session did not touch it" % rel
    return True, "named artifact %s was written or changed this session" % rel


def pytest_collects(rel, root):
    """True when pytest, as pyproject.toml configures it, collects the repo-relative `rel`.

    No package.json script TEXT names a file pytest collects through `[tool.pytest.ini_options] testpaths`, so the text search read every such file as "no check:* key runs it". The roots and the `python_files` patterns are read from pyproject.toml (never hardcoded here); a non-test helper under a root does not match the patterns and is not claimed. Any read or parse failure answers False, which leaves the old text search to decide.
    """
    try:
        with open(os.path.join(str(root), "pyproject.toml"), "rb") as fh:
            ini = tomllib.load(fh).get("tool", {}).get("pytest", {}).get("ini_options", {})
    except (OSError, tomllib.TOMLDecodeError):
        return False
    roots = ini.get("testpaths")
    if not isinstance(roots, list):
        return False
    patterns = ini.get("python_files", ["test_*.py", "*_test.py"])
    if isinstance(patterns, str):
        patterns = patterns.split()
    if not any(isinstance(t, str) and rel.startswith(t.rstrip("/") + "/") for t in roots):
        return False
    return any(fnmatch.fnmatch(os.path.basename(rel), pat) for pat in patterns)


VERDICT_FILE = "rediacc-reggate-verdicts.json"
LOG_DIR = "rediacc-reggate-logs"


def _verdict_path(root):
    dirs = C._repo_git_dirs(root)
    return None if dirs is None else dirs[0] / VERDICT_FILE


def _log_dir(root):
    dirs = C._repo_git_dirs(root)
    return None if dirs is None else dirs[0] / LOG_DIR


def _proof_trailer(rel, digest, code):
    return "REGGATE-PROOF gate=%s hash=%s exit=%d\n" % (rel, digest, code)


def recorded_verdict(root, rel, digest):
    """The exit code `--prove` recorded for gate `rel` at content hash `digest`, or None when none was recorded, the record is unreadable, or the evidence behind it does not check out.

    A row alone settles nothing: it must name a log file under <git-dir>/rediacc-reggate-logs/ whose sha256 equals the row's `log_sha256` and whose last line is the proof trailer for THIS gate, hash and exit. A hand-written `{"hash", "exit": 0}` therefore has no log to name. RESIDUAL RISK: a writer with access to the git directory can still forge the row, the log and the trailer together; this binds a verdict to a run's recorded output, it does not authenticate who ran it (no key outside the agent's writable paths exists to sign with).
    """
    path = _verdict_path(root)
    logs = _log_dir(root)
    if path is None or logs is None:
        return None
    try:
        row = json.loads(path.read_text(encoding="utf-8")).get(rel)
    except (OSError, ValueError, AttributeError):
        return None
    if not (isinstance(row, dict) and row.get("hash") == digest):
        return None
    code, name, want = row.get("exit"), row.get("log"), row.get("log_sha256")
    if not isinstance(code, int) or isinstance(code, bool):
        return None
    if not isinstance(name, str) or not name or os.path.basename(name) != name:
        return None
    try:
        raw = (logs / name).read_bytes()
    except OSError:
        return None
    if hashlib.sha256(raw).hexdigest() != want:
        return None
    if not raw.decode("utf-8", "replace").endswith(_proof_trailer(rel, digest, code)):
        return None
    return code


def _record_verdict(root, rel, digest, code, output=""):
    path = _verdict_path(root)
    logs = _log_dir(root)
    if path is None or logs is None:
        raise OSError("no git directory under %s to hold %s" % (root, VERDICT_FILE))
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, dict):
            rows = {}
    except FileNotFoundError:
        rows = {}
    except ValueError:
        rows = {}  # a corrupt record is replaced by this fresh one, which names the run that wrote it
    logs.mkdir(parents=True, exist_ok=True)
    name = "%s-%s.log" % (hashlib.sha256(rel.encode("utf-8")).hexdigest()[:12], digest[:16])
    body = (
        output
        + ("" if output.endswith("\n") or not output else "\n")
        + _proof_trailer(rel, digest, code)
    )
    (logs / name).write_text(body, encoding="utf-8")
    rows[rel] = {
        "hash": digest,
        "exit": code,
        "at": C.stamp_now(),
        "log": name,
        "log_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
    path.write_text(json.dumps(rows, indent=1, sort_keys=True), encoding="utf-8")


def _gate_key(scripts, rel):
    return next((k for k in sorted(scripts) if k.startswith("check:") and rel in scripts[k]), "")


def prove_cli(root):
    """`wl_reggate.py --prove`: run `npm run <key>` for every check script that is new or dirty relative to HEAD and has no recorded verdict at its content hash (a script changed in an earlier commit is skipped), and record each exit. The Stop hook only READS these verdicts (prove_new_gate), so a gate's minutes-long run never sits on the stop path (agent/plans/PLAN-tooling-speed.md D3). Returns the printed lines."""
    scripts = package_scripts(root)
    out = []
    for pat in CHECK_SCRIPT_GLOBS:
        for f in sorted(glob.glob(os.path.join(str(root), pat))):
            rel = os.path.relpath(f, str(root)).replace(os.sep, "/")
            digest = _hash_file(f)
            if not digest or recorded_verdict(root, rel, digest) is not None:
                continue
            if not (_is_dirty(rel, root) or _new_since_head(rel, root, "HEAD")):
                continue
            key = _gate_key(scripts, rel)
            if not key or not gate_reachable(scripts, key, root):
                out.append("%s: skipped (no reachable check:* key runs it)" % rel)
                continue
            res = wl_proc.run(
                ["npm", "run", "--silent", key], cwd=str(root), timeout=REGGATE_TIMEOUT_S
            )
            code = res.returncode
            _record_verdict(root, rel, digest, code, (res.stdout or "") + (res.stderr or ""))
            out.append("%s via `npm run %s`: exit %d (recorded)" % (rel, key, code))
    return out or ["nothing to prove: no new or changed check script lacks a verdict"]


def prove_new_gate(root, scripts, state):
    """(proven, notes). A claimed gate must leave ARTIFACTS, each verified: a NEW or CHANGED check script (content hash vs the marker), a check:* key whose command runs it, reachability from `npm run ci` (transitive, see gate_reachable), and a bounded green run. Runs are cached by content hash so a red gate is not re-run every stop and a green one is not re-paid. A green run of
    a control-first gate IS the planted-defect proof, because such a gate self-fails when its own control cannot fire -- the check-i18n-cross-locale.ts --selftest that NOTHING invoked is the exact failure this rule exists for, and check-gate-reachability.ts exists because a gate can be defined yet never run."""
    stamp = C.stamp_now()
    notes, proven = [], False
    already_green = []
    for pat in CHECK_SCRIPT_GLOBS:
        for f in sorted(glob.glob(os.path.join(str(root), pat))):
            rel = os.path.relpath(f, str(root)).replace(os.sep, "/")
            digest = _hash_file(f)
            if not digest:
                continue
            prev = state["gate_runs"].get(rel)
            if (
                prev is None
                and not _is_dirty(rel, root)
                and not _new_since_head(rel, root, state.get("head", ""))
            ):
                # First sight of a gate the working tree has NOT touched. That is a glob widening or a fresh marker, not evidence about this fix, so record it and move on. Without this, widening the globs to packages/*/scripts turned one stop into eight `npm run` gates at up to REGGATE_TIMEOUT_S each -- a sixteen-minute stop hook that proves nothing, because none of those gates was
                # written here.
                state["gate_runs"][rel] = {"hash": digest, "exit": -3, "at": stamp}
                continue
            if prev and prev.get("hash") == digest:
                # Neither new nor changed, so it proves nothing for THIS fix and `proven` stays False. But a gate this marker already RAN GREEN must still be NAMED, because the alternative message is false. Measured 2026-08-10: a session wrote check:ci-mutate-check, the probe ran it and recorded exit 0, and on the very next finding the probe reported "no new or changed check script
                # found; a claimed gate must leave one" -- while that gate sat in this same marker at exit 0 with a matching hash. The session cannot tell "your gate is missing" from "your gate is old news", so it either writes a duplicate gate or argues with a message that is simply wrong. Naming it makes the REBUT exit usable, which is the exit the judge itself asked for here.
                if prev.get("exit") == 0:
                    already_green.append(rel)
                continue
            # SUITE gates (hook and gate test suites) have no check:* key and take minutes to run, so they are accepted ON CHANGE: they run in CI regardless (Quality/Static executes the hook suite; the gates suites ride check:ci-quality-gates), and the session that added the case has just run it. The note says which run to trust.
            if rel.startswith((".claude/hooks/", ".ci/scripts/test/gates/")):
                state["gate_runs"][rel] = {"hash": digest, "exit": 0, "at": stamp}
                notes.append(
                    "%s: suite gate accepted on change (CI runs it; verify locally with `bash %s`)"
                    % (rel, rel)
                )
                proven = True
                continue
            key = _gate_key(scripts, rel)
            if not key and PYTEST_GATE_KEY in scripts and pytest_collects(rel, root):
                # Collected through pyproject.toml testpaths. The whole suite exceeds REGGATE_TIMEOUT_S, so like the other suites it is accepted on change once the key is shown reachable from `npm run ci`.
                if not gate_reachable(scripts, PYTEST_GATE_KEY, root):
                    state["gate_runs"][rel] = {"hash": digest, "exit": -2, "at": stamp}
                    notes.append(
                        "%s: %s is defined but NOT reachable from `npm run ci`"
                        % (rel, PYTEST_GATE_KEY)
                    )
                    continue
                state["gate_runs"][rel] = {"hash": digest, "exit": 0, "at": stamp}
                notes.append(
                    "%s: collected by `npm run %s` (pyproject.toml testpaths); accepted on change, "
                    "verify locally with pytest -q" % (rel, PYTEST_GATE_KEY)
                )
                proven = True
                continue
            if not key:
                state["gate_runs"][rel] = {"hash": digest, "exit": -1, "at": stamp}
                notes.append("%s: no check:* key runs it" % rel)
                continue
            if not gate_reachable(scripts, key, root):
                state["gate_runs"][rel] = {"hash": digest, "exit": -2, "at": stamp}
                notes.append(
                    "%s: %s is defined but NOT reachable from `npm run ci` "
                    "(defined-but-never-run is the check-gate-reachability failure)" % (rel, key)
                )
                continue
            # The Stop hook never starts npm: it reads the verdict `wl_reggate.py --prove` recorded for this content hash. A gate with no recorded verdict is left unsettled (not written to gate_runs, so the next stop looks again) and the note names the command.
            code = recorded_verdict(root, rel, digest)
            if code is None:
                notes.append(
                    "%s: no recorded verdict for `npm run %s`; run `python3 .claude/hooks/stop/wl_reggate.py --prove`"
                    % (rel, key)
                )
                continue
            state["gate_runs"][rel] = {"hash": digest, "exit": code, "at": stamp}
            notes.append("%s via `npm run %s`: exit %d (recorded verdict)" % (rel, key, code))
            if code == 0:
                proven = True
    if not notes:
        if already_green:
            notes.append(
                "no NEW or CHANGED check script this stop, but this marker already ran "
                "these green: %s. If one of them covers this finding, REBUT and name it; "
                "the judge re-reads your message" % ", ".join(sorted(already_green)[:4])
            )
        else:
            notes.append("no new or changed check script found; a claimed gate must leave one")
    return proven, "; ".join(notes)


def _new_since_head(rel, root, head):
    """True when `rel` did not exist at the marker's last-seen head.

    _is_dirty used to be the ENTIRE freshness test, which silently assumed a session leaves its work UNCOMMITTED. That holds under this repo's default, but the moment a session COMMITS its gate -- which the findings rule pushes toward as soon as the fix is headed for a PR -- the path is clean, `prev is None`, and prove_new_gate files it at exit -3 as a glob widening.

    Measured 2026-08-26: check-devbox-exec.sh was written, wired three-point, proven against pre-fix source AND committed inside one stop. The very next stop reported "no NEW or CHANGED check script this stop" while the marker held that exact gate at exit -3, never run. The finding then re-fired every stop with NO REACHABLE EXIT: writing the gate again could not change the outcome,
    and the judge itself was answering "no further work needed".

    Errs toward True on any git failure, matching _is_dirty: run the gate rather than silently skip it.
    """
    if not head:
        return False
    pr = wl_common.run_quiet(["git", "cat-file", "-e", "%s:%s" % (head, rel)], cwd=str(root))
    return pr is None or pr.returncode != 0


def _is_dirty(rel, root):
    """True when the working tree has touched this path (modified or untracked).

    The probe's question is "did the session that just claimed a fix leave a gate", so a gate it did not touch is not evidence either way. Errs toward True: if git cannot answer, run the gate rather than silently skip it.
    """
    try:
        pr = subprocess.run(
            ["git", "status", "--porcelain", "--", rel],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    if pr.returncode != 0:
        return True
    return bool(pr.stdout.strip())


def apply_regression_verdict(rg, scripts, root, state, sig, lines, me8):
    """('malformed'|'settle'|'block', payload, detail).

    Deterministic mapping from the judge's regression_gate object to an action, with every model claim VERIFIED against artifacts:
      applicable false                      -> settle 'not-applicable'
      existing_gate is a REAL check:* key   -> settle 'covered'
      existing_gate names a key that is not -> hallucinated coverage, counts
                                               as none, falls through
      recurring false                       -> settle 'one-off'
      a `- [?]` line carrying reggate:<sig> -> settle 'deferred' (the deferral
                                               machinery prints it every stop)
      a new/changed gate, wired + green     -> settle 'proven'
      otherwise: recurring AND ungated AND unproven AND undeferred -> block,
      naming the three exits. gate_needed=false with recurring=true and no
      real coverage is incoherent and blocks too; the REBUT exit lets the
      judge re-answer coherently next stop."""
    fields = (
        "applicable",
        "blind_spot",
        "existing_gate",
        "recurring",
        "gate_needed",
        "gate_proven",
        "instruction",
    )
    if not isinstance(rg, dict) or any(k not in rg for k in fields):
        return "malformed", "regression_gate missing or incomplete: %r" % (rg,), ""
    if rg["applicable"] is False:
        return "settle", "not-applicable", str(rg["blind_spot"])[:160]
    keys = [k for k in scripts if k.startswith("check:")]
    hall, eg = "", str(rg["existing_gate"] or "").strip()
    if eg:
        if eg in keys:
            return "settle", "covered", eg
        # A `test:*` (or any other non-`check:*`) manifest id with `gate: true` is run DIRECTLY by `npm run ci` -- scripts/ci-runner/run.ts schedules from manifest.ts, not from package.json `check:*` keys. gate_reachable() already trusts this same set for the WRITE path; the REBUT path was checking package.json only, so a correct citation of a real, ci-runner-scheduled suite gate (e.g.
        # `test:write-once-guard`) was unconditionally reported as hallucinated. Verified live 2026-08-27 that `npx tsx scripts/ci-runner/run.ts --only <id>` executes and passes a manifest gate that has no `check:*` script (the id then checked was the ci-trace-branch gate test, since retired into the pytest module .ci/rediacc_ci/tests/gates/test_gate_ci_trace_branch.py; `test:write-once-guard` is an illustration, not what was run).
        if eg in _manifest_gate_ids(root):
            return "settle", "covered", eg
        # A citation is at least as often a FILE PATH (optionally with "::test_name") as it is a manifest id -- both a human rebuttal and the judge itself reach for the path visible in the tree. Observed live 2026-08-27: three consecutive REBUTs, each naming a real, already-passing case in test_gate_ci_trace_branch.py by path/function, kept reporting hallucinated because only the
        # bare id was checked.
        if _citation_matches_gate(eg, root):
            return "settle", "covered", eg
        hall = eg
    if rg["recurring"] is False and not hall:
        return "settle", "one-off", str(rg["blind_spot"])[:160]
    token = "reggate:%s" % sig[:8]
    for ln in lines:
        m = C.ITEM.match(ln)
        if m and m.group("state") == "?" and token in ln:
            return "settle", "deferred", token
    proven, notes = prove_new_gate(root, scripts, state)
    if proven:
        return "settle", "proven", notes[:300]
    # The other five surfaces. Only consulted when the judge routed AWAY from `gates`, so a static gate still has to clear the stricter probe above -- wired, reachable and green -- rather than being waved through by touching a file.
    surface = str(rg.get("surface") or "").strip()
    if surface and surface not in ("gates", "none"):
        ok, note = prove_named_artifact(root, rg.get("artifact"))
        if ok:
            return "settle", "proven", ("%s (%s)" % (note, surface))[:300]
        if note:
            notes = (notes + "; " if notes else "") + note
    surface_line = ""
    if surface and surface not in ("", "none"):
        surface_line = "  surface: %s -- read .claude/skills/testing/%s.md; artifact: %s\n" % (
            surface,
            surface if surface != "gates" else "gates",
            str(rg.get("artifact") or "(unnamed)")[:120],
        )
    reason = M.R_REGGATE_BLOCK % (
        str(rg["blind_spot"])[:300],
        (surface_line + str(rg["instruction"]))[:600],
        "" if not hall else M.R_REGGATE_HALLUCINATED % hall,
        "" if not notes else "  gate probe: %s\n" % notes[:400],
        me8,
        token,
    )
    return "block", reason, ""


if __name__ == "__main__":
    import sys

    if sys.argv[1:2] == ["--prove"]:
        print("\n".join(prove_cli(sys.argv[2] if len(sys.argv) > 2 else os.getcwd())))
    else:
        sys.stderr.write("usage: wl_reggate.py --prove [<repo root>]\n")
        sys.exit(2)
