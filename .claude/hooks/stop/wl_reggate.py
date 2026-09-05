"""wl_reggate: the v7 regression-gate machinery and its v8 bookkeeping.

WHY (v7, operator request): "you fixed but we didn't have a mechanism for
future regressions." A fix without a gate is a defect scheduled to return,
and the i18n cross-locale bug proved it: fixed by hand, then invisible to
every existing check by construction. On every stop where a fix landed, the
judge is asked whether a gate protects it, and every model claim is VERIFIED
against artifacts: a named existing gate must be a real check:* key; a new
gate counts only when WIRED (reachable from `npm run ci` TRANSITIVELY) and
its bounded run is green (cached by content hash).

Detection is from ARTIFACTS, never prose: commit subjects matching
^(fix|revert)[(!:] between the marker's last-seen HEAD and current HEAD,
plus newly ticked `- [x]` items owned by this session. A fix-set touching
only docs/** and **/*.md never asks. A settled fix-set is NEVER re-asked.

FAIL SAFE: a missing marker initialises to current HEAD and asks nothing
that stop; a corrupt one does the same plus ONE systemMessage line. Never a
block, never silent. No field-wise salvage: any invalid shape discards the
file, because half-parsed fixsets silently resurrect a blocked question as
settled.
"""

import contextlib
import fnmatch
import glob
import hashlib
import json
import os
import pathlib
import re
import subprocess

import wl_core as C
import worklist_messages as M

FIX_SUBJECT = re.compile(r"^(fix|revert)[(!:]")
REGGATE_TIMEOUT_S = int(os.environ.get("WORKLIST_REGGATE_TIMEOUT_S", "120"))
REGGATE_VERDICTS = (
    "not-applicable",
    "covered",
    "one-off",
    "proven",
    "deferred",
    # Written ONLY by the cap, never by the judge. It says "the finding was
    # computed and verified, then deferred as debt" -- which is a different fact
    # from every verdict above, all of which mean the question was answered.
    # Collapsing it into "deferred" would make a capped demand indistinguishable
    # from one the session argued its way out of.
    "capped",
)

# ---------------------------------------------------------------------------
# THE EFFORT CAP (operator ruling 2026-09-05T01:55Z).
#
# "This is a general problem. Lets employ a planning agent to have a limit for
# that. Maybe we can limit new gate work after some point to 7 times? But that
# check should be done on stop hook side instead of ignoring."
#
# The ruling's second sentence is the load-bearing one: the cap belongs HERE, in
# the machinery, not in a session deciding it has complied enough. A session that
# stops complying is indistinguishable from a session that is wrong.
#
# WHAT IS COUNTED (plan Q1): a fix-set this BRANCH settled by writing a new gate
# (`proven`), plus one for each fix-set the cap itself deferred. NOT demands,
# blocks or stops -- counting those lets a session outwait a legitimate demand by
# stopping N times, which is the ignoring the ruling forbids. NOT the cheap
# settles (`covered`/`one-off`/`not-applicable`/`deferred`) -- those cost no
# artifact and no CI round, and counting them would let a session farm the budget
# with five honest one-offs to buy a pass on the sixth, real gate.
#
# SCOPE IS THE BRANCH, not the session. `reggate_path` is keyed on session id, so
# a per-session budget would evaporate at exactly the moment a long night makes
# compaction likely. A branch maps one-to-one onto one PR and one CI queue, which
# is where the cost actually lands; two sessions sharing a branch share the
# budget, correctly, because they share the queue.
# ---------------------------------------------------------------------------
REGGATE_CAP = max(1, int(os.environ.get("WORKLIST_REGGATE_CAP", "7")))
# A branch may never merge, so the merge probe alone could hold a debt open
# forever. due = min(merge_detected, at + grace): the grace clock can only make a
# debt due SOONER, never never.
REGGATE_DEBT_GRACE_MIN = max(1, int(os.environ.get("WORKLIST_REGGATE_DEBT_GRACE_MIN", "720")))


def debt_dir(root=None):
    """Directory holding the per-branch ledgers. See wl_store.AGENT_RESERVED_DIRS.

    HONOURS $WORKLIST_STORE_DIR, exactly as wl_store.store_dir does, and for the
    same reason it had to learn it: without the override the test harness runs
    the hook against the REAL repo root, so every suite run appended a ledger to
    the operator's own tree. Caught the first time this shipped -- an untracked
    agent/reggate/agenttest.jsonl appeared in `git status` from a suite run,
    which is the same footgun as the harness once writing the operator's real
    worklist. A sibling of the store, so one export redirects both.
    """
    override = os.environ.get("WORKLIST_STORE_DIR")
    if override:
        return pathlib.Path(override).parent / "reggate"
    return pathlib.Path(root or ".") / "agent" / "reggate"


def _branch_slug(branch):
    """A branch name flattened to one safe filename component.

    Branch names carry '/' and worse; one file per branch means the name IS the
    filename, so it is sanitised rather than trusted.
    """
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (branch or "detached").strip()) or "detached"
    return slug[:100]


def debt_path(branch, root=None):
    """ONE FILE PER BRANCH, following wl_store's per-writer rule verbatim.

    Both sides of a merge append at EOF, so a single shared ledger conflicts on
    every concurrent append. Per-branch files never do.
    """
    return debt_dir(root) / (_branch_slug(branch) + ".jsonl")


# Where a freshly written gate leaves its artifact. Both shapes exist in this
# repo; anything else is not a gate the ci chain can run.
# The hook and gate test suites count as gate artifacts too: a fix inside
# .claude/hooks/** or a CI script has its canonical regression home in the
# corresponding SUITE, and the old two-glob probe kept printing "no new or
# changed check script found" across three consecutive stops while the
# judge itself had already accepted a suite case (163e) as the gate. A
# probe narrower than the judge's own ruling is a false-fire generator.
CHECK_SCRIPT_GLOBS = (
    "scripts/check-*.ts",
    # Package-local gates. Omitting these made the probe structurally blind to
    # NINE real gates -- check:ci-tutorial-parity, check:ci-locale-tutorial-assets,
    # check:ci-solution-videos, check:ci-command-planes and friends all live here,
    # because a gate about www content belongs beside www. Measured 2026-08-18: a
    # session wrote packages/www/scripts/check-tutorial-card-fonts.ts, wired its
    # check:ci-* key and its ci-quality.yml step, ran its planted-defect proof, and
    # the probe still answered "no new or changed check script found; a claimed
    # gate must leave one". The only way to satisfy the old globs was to move a
    # www gate to the repo root, i.e. to let the probe dictate layout.
    "packages/*/scripts/check-*.ts",
    ".ci/scripts/quality/check-*.sh",
    ".ci/scripts/test/gates/test-*.sh",
    ".claude/hooks/stop/test-*.sh",
    ".claude/hooks/test-*.sh",
)
# UPGRADE GUARD (v10). Tick identity is the hash of the RENDERED line, and the
# v10 store rewrite changed rendering, so the first stop after an upgrade can
# see every historical [x] as "new" (791 in the live store). A flood of ticks
# is bookkeeping drift, not 791 simultaneous fixes: absorb silently with one
# systemMessage line instead of asking the judge about ancient history.
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

    Append-only JSONL, folded on read, NEVER edited. It is deliberately not an
    `ev:` kind in the item store: wl_epic.py's header records why, and it learned
    it the hard way -- `compact()` rewrites that log down to the minimal
    item-reproducing set, so a novel event kind there is SILENTLY DESTROYED.
    `.requests`, `.intents` and `.epics` are the precedents this follows.
    """
    import wl_store as S

    path = debt_path(branch, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(record)
    rec.setdefault("at", C.stamp_now())
    rec.setdefault("br", branch or "")
    # Pass the DICT: _append_lines serialises each payload itself. Handing it a
    # pre-encoded string double-encodes it into a JSON string containing JSON,
    # which read_ledger then rejects as malformed -- silently emptying the
    # ledger and, with it, the budget.
    S._append_lines(path, path.with_suffix(".lock"), [rec])
    return rec


def read_ledger(branch, root=None):
    """(records, forgot), same FAIL SAFE contract as load_reggate.

    `forgot` means the ledger could not be read as written. It is reported rather
    than swallowed, because a budget computed from an unreadable ledger reads as
    a FRESH budget -- the most permissive answer possible, and exactly the shape
    that would let the cap silently stop capping.
    """
    path = debt_path(branch, root)
    if not path.exists():
        return [], False
    records, forgot = [], False
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
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


def branch_merged(branch, root=None):
    """Has this branch landed on origin/main?

    A FAILED PROBE IS NOT A MERGE. It returns False, so the grace clock alone
    governs the debt -- making it due sooner, never never. A probe that answered
    True on failure would discharge every debt on any git hiccup.
    """
    if not branch:
        return False
    # NOT `merge-base --is-ancestor`: it answers through its EXIT CODE and prints
    # nothing, while C._git returns stdout and collapses every failure to "".
    # Through that helper a merged branch and a broken git are the same empty
    # string. `rev-list --count origin/main..HEAD` puts the answer on stdout:
    # "0" means HEAD carries nothing origin/main lacks, i.e. it landed.
    return C._git(root or ".", "rev-list", "--count", "origin/main..HEAD") == "0"


def budget_state(branch, root=None):
    """(charged, remaining, debts, forgot) folded from the ledger.

    THE COUNTER RESETS WHEN THE BRANCH LANDS; DEBTS DO NOT. A merge resets the
    counter and simultaneously makes every outstanding debt DUE. That inversion
    is the point: merging is what makes you pay, and there is no ordering in
    which a merge discharges a debt.
    """
    records, forgot = read_ledger(branch, root)
    discharged = {r.get("sig") for r in records if r.get("kind") == "discharge"}
    charged = sum(1 for r in records if r.get("kind") == "charge")
    debts = [
        r
        for r in records
        if r.get("kind") == "debt" and r.get("sig") not in discharged
    ]
    if branch_merged(branch, root):
        charged = 0
    return charged, max(0, REGGATE_CAP - charged), debts, forgot


def charge(branch, sig, reason, root=None):
    """Spend one unit of budget. Called ONLY on a `proven` settle or at the cap."""
    return append_ledger(branch, {"kind": "charge", "sig": sig, "why": reason}, root=root)


def save_reggate(path, state):
    # Whole-file rewrite is correct here for the same reason as the handover:
    # the marker is per-session, so there is no second writer to race.
    with contextlib.suppress(OSError):
        path.write_text(json.dumps(state, indent=1), encoding="utf-8")


def _tick_id(line):
    return hashlib.sha1(line.strip().encode("utf-8", "replace")).hexdigest()[:12]


def mine_tick_ids(lines, session_id):
    out = []
    for line in lines:
        m = C.ITEM.match(line)
        if m and m.group("state") == "x" and C.owned_by_me(m.group("owner"), session_id):
            out.append(_tick_id(line))
    return out


def _hash_file(path):
    try:
        return hashlib.sha1(pathlib.Path(path).read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def seed_gate_hashes(root):
    """Hashes of every existing check script, recorded at marker init so only
    scripts that are NEW or CHANGED after that point ever count as candidate
    proof (or get run). Without this seed, the first fix-signal stop in a real
    repo would treat ~all 90 existing gates as candidates and try to run them."""
    stamp = C.stamp_now()
    out = {}
    for pat in CHECK_SCRIPT_GLOBS:
        for f in glob.glob(os.path.join(str(root), pat)):
            rel = os.path.relpath(f, str(root)).replace(os.sep, "/")
            digest = _hash_file(f)
            if digest:
                out[rel] = {"hash": digest, "exit": -3, "at": stamp}  # -3 = seeded, never run
    return out


# A path-shaped token with an extension. Used only to decide whether a tick's
# EVIDENCE names code; the tick text itself is prose and is never parsed further.
_EVIDENCE_PATH = re.compile(r"(?<![\w/])((?:[\w.@-]+/)+[\w.@-]+\.[A-Za-z0-9]+)")


def tick_touches_code(line):
    """Does this tick's evidence name a file that is not documentation?

    The operator's rule: only code-touching ticks are asked. This mirrors the
    docs-only filter already applied to commits, and it FAILS TOWARD ASKING --
    a tick whose evidence names no path at all is asked, because "no path" is
    not evidence that nothing shipped, and silently dropping a fix is the
    failure this whole mechanism exists to prevent.
    """
    paths = _EVIDENCE_PATH.findall(line or "")
    if not paths:
        return True
    return not all(p.startswith("docs/") or p.endswith(".md") for p in paths)


# Paths that are CI-gate MAINTENANCE rather than product code. Derived by
# checking real commits, not guessed: the first version of this list omitted
# .github/workflows and scripts/data and therefore answered False for
# 3148399c9, a commit that is nothing BUT gate maintenance.
GATE_ARTIFACT_PREFIXES = (
    "scripts/check-",
    "scripts/data/",  # gate seeds and baselines
    "scripts/lib/",  # gate-support libraries: verified 2026-09-05 that
    # every consumer is a check script or a test, never
    # product runtime (action-refs, blocker-validator,
    # gate-header, shrink-only-baseline, controls...)
    # NOT "packages/" -- that was the first version and it is WRONG in the most
    # expensive direction: it marks EVERY file under packages/ as gate
    # maintenance, so all product code would earn the hint. Caught by case 96 in
    # a fixture repo, where packages/cli/src/real.ts came back True. Sampling 7
    # real commits had missed it because none touched product code under
    # packages/ -- testing against the data you happen to have is how a rule
    # ships inverted. Package-local gates are matched by GLOB below instead.
    ".ci/scripts/quality/",
    ".ci/scripts/security/",
    ".ci/scripts/test/",
    ".claude/hooks/",
    ".github/workflows/ci-",  # the quality workflows a gate is wired into
)
GATE_ARTIFACT_EXACT = ("scripts/ci-runner/manifest.ts", "package.json")
# Package-local gates live beside their package, so they need a GLOB, not a
# prefix. CHECK_SCRIPT_GLOBS' own header records why they must be reachable at
# all: omitting them made the gate probe structurally blind to nine real gates.
GATE_ARTIFACT_GLOBS = (
    "packages/*/scripts/check-*.ts",
    "packages/*/scripts/check-*.sh",
)

# BOOKKEEPING, ignored rather than counted. Every commit in this repo carries
# agent/ session state and often docs; requiring them to be gate artifacts made
# the probe answer False for 89189c0b5, which touches one hook file and two
# agent files. This mirrors the docs-only skip below: prose is not the subject.
GATE_NEUTRAL_PREFIXES = ("agent/", "docs/")


def gate_only_fixset(root, shas):
    """True when every NON-BOOKKEEPING file in the fix-set is a CI-gate artifact.

    ARTIFACTS, NEVER PROSE -- this reads `git diff-tree`, not a commit subject,
    the same rule fix_signals states for its docs-only skip below.

    WHY IT IS A HINT AND NOT A SKIP. A gate-maintenance fix can still deserve a
    gate of its own, so this never suppresses a fix-set; it tells the judge what
    it is looking at, so question (0) has something to bite on. Measured
    2026-09-04/05: two sessions ran a self-generating loop where writing gate A
    produced the finding that gate B was needed, and every one of those findings
    had ALREADY been caught by an existing gate. Nothing told the judge the
    fix-set was gate machinery.

    Fails toward saying nothing extra: any git error, an empty fix-set, or a
    fix-set that is ONLY bookkeeping returns False rather than skipping the
    question. That includes a TICK-BASED fix-set: fix_signals' ids are commit
    shas OR tick ids, and a tick id is not a tree-ish, so `git diff-tree` fails
    and this answers False. Correct by construction -- an uncommitted fix has no
    file list to classify -- and it means the hint is a commit-fix-set feature.
    """
    if not shas:
        return False
    seen = False
    for sha in shas:
        try:
            files = C._git(
                root, "diff-tree", "--no-commit-id", "--name-only", "-r", sha
            ).splitlines()
        except Exception:  # noqa: BLE001 -- a hint must never raise into the stop path
            return False
        if not files:
            # A ROOT commit has no parent, so `diff-tree` prints nothing. Retry
            # with --root, which does list a root commit's files. Caught by case
            # 96, whose fixture repo's first commit IS the root. Still False if
            # that yields nothing: an unreadable ref says nothing extra.
            try:
                files = C._git(
                    root, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", sha
                ).splitlines()
            except Exception:  # noqa: BLE001
                return False
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


def fix_signals(root, lines, session_id, state):
    """(descriptions, ids, new_tick_pairs, current_head, banked_only_ids).

    ARTIFACTS, never prose. Primary: commit subjects matching FIX_SUBJECT in
    marker-head..HEAD. Secondary: newly ticked `- [x]` lines owned by this
    session, covering the uncommitted-tree default. The skip filter is
    deliberately narrow: a fix commit touching only docs/** and **/*.md never
    asks; everything else does, and the judge's four questions sort the
    one-offs out. A rewound or unreachable old head yields an empty log,
    which reads as no signals and lets head self-heal by advancing.

    `banked_only_ids` is a SEPARATE list from `new_tick_pairs`, deliberately: a
    docs-only tick must be marked seen so it stops being rediscovered every
    stop, but it must NOT be asked about and must NOT be subjected to the I7
    completion-evidence check that `new_tick_pairs` feeds elsewhere. Folding it
    into `new_tick_pairs` instead (the first version of this fix) would have
    made that evidence check run over ticks nobody is asking about -- a
    docs-only tick with a bare `- [x]` line and no evidence would then fail I7
    for a reason unrelated to what it actually is. Found in review, not by a
    control: no `- [x]` docs-only fixture exercised that path."""
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
    for line in lines:
        m = C.ITEM.match(line)
        if m and m.group("state") == "x" and C.owned_by_me(m.group("owner"), session_id):
            tid = _tick_id(line)
            if tid not in state["seen_ticks"]:
                new_ticks.append((tid, line.strip()))
    # ONE UNIT PER STOP, oldest first. Until now every commit and every new tick
    # of a stop were hashed into a SINGLE fix-set, so one verdict had to cover
    # unrelated fixes and the judge's answers wandered across the bundle. Asking
    # per item is what the operator asked for; asking about ALL of them at once
    # would wall a busy stop in behind eight simultaneous demands, so the rest
    # stay unbanked and the next stop picks up the next one.
    #
    # Commits are ONE unit, not one each: they already passed the docs-only
    # filter above and they landed together.
    # THE FLOOD GUARD RUNS BEFORE UNIT SELECTION, and it has to. The caller
    # absorbs a burst of "new" ticks as store-format drift rather than as
    # fixes, and it decides that from `len(new_ticks)`. Handing it one unit
    # first hid the burst from it, so the flood was never absorbed and the very
    # first historical tick blocked instead. Caught by the suite's own
    # tick-flood case, not by review.
    if len(new_ticks) > TICK_FLOOD:
        return (
            ["tick: " + t[:120] for _, t in new_ticks],
            sorted([t for t, _ in new_ticks]),
            new_ticks,
            head,
            [],
        )
    units = []
    banked_only = []
    if commits:
        units.append(([s for s, _ in commits], [d for _, d in commits], []))
    for tid, line in new_ticks:
        if not tick_touches_code(line):
            # SEEN, NOT ASKED. Without this the id is never added to seen_ticks
            # (the caller only banks what THIS function returns), so it is
            # rediscovered as "new" and re-filtered on every future stop,
            # forever. It still must not enter `ticks`/`ids`: those feed both
            # the ask and the I7 evidence check, and a docs-only tick is
            # neither being asked about nor required to carry evidence.
            banked_only.append(tid)
            continue
        units.append(([tid], ["tick: " + line[:120]], [(tid, line)]))
    if not units:
        return [], [], [], head, banked_only
    ids, descriptions, ticks = units[0]
    if len(units) > 1:
        descriptions = [
            *descriptions,
            "(%d more fix(es) queued for later stops; this one is asked alone)" % (len(units) - 1),
        ]
    # ticks stays (id, line) pairs: I7 needs the LINE to check evidence, the
    # absorb/settle sites need the id. Returning ids only here once made the I7
    # unpack crash, and a crashed hook reads as ALLOW -- fail-open.
    return descriptions, sorted(ids), ticks, head, banked_only


def package_scripts(root):
    try:
        d = json.loads((pathlib.Path(root) / "package.json").read_text(encoding="utf-8"))
        s = d.get("scripts")
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def _manifest_gate_ids(root):
    """Gate ids registered in the ci-runner manifest, as a set.

    The runner is the dispatcher for every `check:ci-*` in this repo, so a gate
    listed there with `gate: true` IS run by `npm run ci` even though nothing in
    package.json ever says `npm run <that key>`.
    """
    ids = set()
    if root is None:
        return ids
    mf = os.path.join(str(root), "scripts", "ci-runner", "manifest.ts")
    try:
        with open(mf, encoding="utf-8") as fh:
            src = fh.read()
    except OSError:
        return ids
    # `(?:\s|//[^\n]*\n)*`, not `\s*`: a manifest entry whose leading comment sits
    # INSIDE the brace was invisible to this scan, so the reachability gate silently
    # checked a smaller set and still printed a healthy "agrees with all N
    # registrations". Found 2026-08-20 with a planted entry that the gate went green
    # over; it was already hiding check:ci-dockerfile-mirror-resilience and
    # check:ci-tutorial-card-fonts (259 of 261 seen).
    for m in re.finditer(r"\{(?:\s|//[^\n]*\n)*id:\s*'([^']+)'(.*?)\}", src, re.DOTALL):
        if "gate: true" in m.group(2):
            ids.add(m.group(1))
    return ids


def _manifest_gate_run_paths(root):
    """`run:` script paths for every `gate: true` manifest entry, as a set.

    A citation of real, ci-runner-scheduled coverage is far more often a FILE
    PATH ("test-ci-trace-branch.sh" or its full repo-relative path, optionally
    with "::test_name" naming the specific case inside it) than the manifest's
    own `id:` string -- both a human and a judge model reach for the path they
    can see in the tree, not an id that exists only in manifest.ts. Checking
    ids alone (the first fix here) left that whole citation shape unrecognized
    and still reporting real coverage as hallucinated. Same regex/parsing
    approach as _manifest_gate_ids, deliberately: one manifest scan, two views.
    """
    paths = set()
    if root is None:
        return paths
    mf = os.path.join(str(root), "scripts", "ci-runner", "manifest.ts")
    try:
        with open(mf, encoding="utf-8") as fh:
            src = fh.read()
    except OSError:
        return paths
    for m in re.finditer(r"\{(?:\s|//[^\n]*\n)*id:\s*'([^']+)'(.*?)\}", src, re.DOTALL):
        if "gate: true" not in m.group(2):
            continue
        rm = re.search(r"run:\s*'([^']+)'", m.group(2))
        if rm:
            paths.add(rm.group(1))
    return paths


def _citation_matches_gate(eg, root):
    """True when `eg` names real, `npm run ci`-scheduled coverage: either a
    manifest `id:` (checked by the caller against `_manifest_gate_ids`
    directly) or a `run:` file path, exact or with a trailing "::name"/"#name"
    case qualifier and/or a leading "./" stripped."""
    base = re.split(r"::|#", eg, maxsplit=1)[0].strip()
    while base.startswith("./"):
        base = base[2:]
    paths = _manifest_gate_run_paths(root)
    return base in paths or any(p.endswith("/" + base) for p in paths)


def gate_reachable(scripts, target, root=None):
    """Is `target` TRANSITIVELY reachable from the `ci` script via `npm run`
    references? Transitive, because ci reaches most gates through batch keys.
    NOT a substring test: a gate's name inside an `echo` is not reachability,
    and the substring version produced real false positives on this repo."""
    seen, todo = set(), ["ci"]
    runner = False
    while todo:
        k = todo.pop()
        if k in seen or k not in scripts:
            continue
        seen.add(k)
        body = scripts[k]
        # A DISPATCHER, not an npm-run chain. `ci` is `tsx scripts/ci-runner/run.ts`,
        # whose body contains ZERO `npm run` references -- it schedules from
        # manifest.ts instead. Walking npm-run edges alone therefore returned False
        # for EVERY gate in this repo, check:ci-shell-commands and check:ci-dead-bash
        # included, and reported each new gate as "defined but never run". A probe
        # that cannot pass is the same defect as a check that cannot fail: it was
        # rejecting correctly-wired gates and demanding they be re-wired.
        if "ci-runner/run.ts" in body:
            runner = True
        todo.extend(re.findall(r"npm run\s+(?:--silent\s+)?([A-Za-z0-9:._-]+)", body))
    if target in seen:
        return True
    return runner and target in _manifest_gate_ids(root)


def prove_named_artifact(root, artifact):
    """(proven, note) for a case on ANY surface, by the path the judge named.

    THE GLOB PROBE BELOW CAN ONLY SEE ONE SURFACE. It matches check-*.ts,
    check-*.sh and the two test suites, so a fix whose regression home is an
    E2E case, an ops step, an install script or a unit test had no acceptable
    answer at all: the only thing it could prove was a static gate, which for a
    behavioural defect asserts that the source still looks right. Enumerating
    the other five here would rot the moment a sixth appears, so this asks a
    different question -- the judge names the path, and this checks whether that
    path CHANGED in this session's tree.

    Deliberately weaker than the glob probe, and it says so: this proves the
    case was written, not that it runs or that it fails on the defect. The
    surface's own file in `.claude/skills/testing/` names the run that would.
    A path that does not exist, or exists unchanged, proves nothing.
    """
    # `.lstrip("./")` was the first spelling and it is wrong: lstrip takes a
    # CHARACTER SET, so `.claude/hooks/...` came back as `claude/hooks/...` and
    # every hook-surface artifact was reported as nonexistent. Strip the prefix.
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


def prove_new_gate(root, scripts, state):
    """(proven, notes). A claimed gate must leave ARTIFACTS, each verified:
    a NEW or CHANGED check script (content hash vs the marker), a check:* key
    whose command runs it, reachability from `npm run ci` (transitive, see
    gate_reachable), and a bounded green run. Runs are cached by content hash
    so a red gate is not re-run every stop and a green one is not re-paid.
    A green run of a control-first gate IS the planted-defect proof, because
    such a gate self-fails when its own control cannot fire -- the
    check-i18n-cross-locale.ts --selftest that NOTHING invoked is the exact
    failure this rule exists for, and check-gate-reachability.ts exists
    because a gate can be defined yet never run."""
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
                # First sight of a gate the working tree has NOT touched. That is
                # a glob widening or a fresh marker, not evidence about this fix,
                # so record it and move on. Without this, widening the globs to
                # packages/*/scripts turned one stop into eight `npm run` gates at
                # up to REGGATE_TIMEOUT_S each -- a sixteen-minute stop hook that
                # proves nothing, because none of those gates was written here.
                state["gate_runs"][rel] = {"hash": digest, "exit": -3, "at": stamp}
                continue
            if prev and prev.get("hash") == digest:
                # Neither new nor changed, so it proves nothing for THIS fix and
                # `proven` stays False. But a gate this marker already RAN GREEN
                # must still be NAMED, because the alternative message is false.
                # Measured 2026-08-10: a session wrote check:ci-mutate-check,
                # the probe ran it and recorded exit 0, and on the very next
                # finding the probe reported "no new or changed check script
                # found; a claimed gate must leave one" -- while that gate sat
                # in this same marker at exit 0 with a matching hash. The
                # session cannot tell "your gate is missing" from "your gate is
                # old news", so it either writes a duplicate gate or argues with
                # a message that is simply wrong. Naming it makes the REBUT exit
                # usable, which is the exit the judge itself asked for here.
                if prev.get("exit") == 0:
                    already_green.append(rel)
                continue
            # SUITE gates (hook and gate test suites) have no check:* key and
            # take minutes to run, so they are accepted ON CHANGE: they run in
            # CI regardless (Quality/Static executes the hook suite; the gates
            # suites ride check:ci-quality-gates), and the session that added
            # the case has just run it. The note says which run to trust.
            if rel.startswith((".claude/hooks/", ".ci/scripts/test/gates/")):
                state["gate_runs"][rel] = {"hash": digest, "exit": 0, "at": stamp}
                notes.append(
                    "%s: suite gate accepted on change (CI runs it; verify locally with `bash %s`)"
                    % (rel, rel)
                )
                proven = True
                continue
            key = next(
                (k for k in sorted(scripts) if k.startswith("check:") and rel in scripts[k]),
                "",
            )
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
            try:
                pr = subprocess.run(
                    ["npm", "run", "--silent", key],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=REGGATE_TIMEOUT_S,
                    check=False,
                )
                code = pr.returncode
            except subprocess.TimeoutExpired:
                code = 124
            except (OSError, subprocess.SubprocessError):
                code = 127
            state["gate_runs"][rel] = {"hash": digest, "exit": code, "at": stamp}
            notes.append("%s via `npm run %s`: exit %d" % (rel, key, code))
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

    _is_dirty used to be the ENTIRE freshness test, which silently assumed a
    session leaves its work UNCOMMITTED. That holds under this repo's default,
    but the moment a session COMMITS its gate -- which the findings rule pushes
    toward as soon as the fix is headed for a PR -- the path is clean, `prev is
    None`, and prove_new_gate files it at exit -3 as a glob widening.

    Measured 2026-08-26: check-devbox-exec.sh was written, wired three-point,
    proven against pre-fix source AND committed inside one stop. The very next
    stop reported "no NEW or CHANGED check script this stop" while the marker
    held that exact gate at exit -3, never run. The finding then re-fired every
    stop with NO REACHABLE EXIT: writing the gate again could not change the
    outcome, and the judge itself was answering "no further work needed".

    Errs toward True on any git failure, matching _is_dirty: run the gate
    rather than silently skip it.
    """
    if not head:
        return False
    try:
        pr = subprocess.run(
            ["git", "cat-file", "-e", "%s:%s" % (head, rel)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    return pr.returncode != 0


def _is_dirty(rel, root):
    """True when the working tree has touched this path (modified or untracked).

    The probe's question is "did the session that just claimed a fix leave a
    gate", so a gate it did not touch is not evidence either way. Errs toward
    True: if git cannot answer, run the gate rather than silently skip it.
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

    Deterministic mapping from the judge's regression_gate object to an
    action, with every model claim VERIFIED against artifacts:
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
        # A `gate-test:*` (or any other) manifest id with `gate: true` is run
        # DIRECTLY by `npm run ci` -- scripts/ci-runner/run.ts schedules from
        # manifest.ts, not from package.json `check:*` keys. gate_reachable()
        # already trusts this same set for the WRITE path; the REBUT path was
        # checking package.json only, so a correct citation of a real,
        # ci-runner-scheduled suite gate (e.g. gate-test:ci-trace-branch) was
        # unconditionally reported as hallucinated. Verified live 2026-08-27:
        # `npx tsx scripts/ci-runner/run.ts --only gate-test:ci-trace-branch`
        # actually executes and passes it.
        if eg in _manifest_gate_ids(root):
            return "settle", "covered", eg
        # A citation is at least as often a FILE PATH (optionally with
        # "::test_name") as it is a manifest id -- both a human rebuttal and
        # the judge itself reach for the path visible in the tree. Observed
        # live 2026-08-27: three consecutive REBUTs, each naming a real,
        # already-passing case in test-ci-trace-branch.sh by path/function,
        # kept reporting hallucinated because only the bare id was checked.
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
    # The other five surfaces. Only consulted when the judge routed AWAY from
    # `gates`, so a static gate still has to clear the stricter probe above --
    # wired, reachable and green -- rather than being waved through by touching
    # a file.
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
