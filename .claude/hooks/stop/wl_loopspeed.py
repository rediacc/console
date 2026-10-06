"""wl_loopspeed: the two loop-speed advisories of agent/plans/PLAN-fast-loop.md, Parts 3 and 4. Pure functions plus small read-only git reads; nothing here blocks anything.

PART 3, ONE PRE-PUSH PER PUSH. `receipt_behind(root)` counts the code commits between the pre-push receipt's head and HEAD. A commit whose every changed path is a record path (`.ci/policy/record-paths.json`: reviews, ledgers, STATE.md and the like) does not void a receipt, so it does not count. The Stop hook says "the receipt is N code commits behind" only when a push is actually owed (unpushed commits exist), because a receipt built before a push is due is a receipt built too early.

The record policy is READ FROM HEAD, never the worktree, as the push guard reads it, and its three glob rules are mirrored from `block_unverified_push.py` (`record_glob_re`, `record_of`, `parse_record_policy`), which a hook module cannot import without loading the whole guard. `test_wl_loopspeed.py` pins the mirror equal to the guard on one corpus.

PART 4, DON'T PUSH INTO A RUNNING RUN. `ci_hold` reads the cached PR CI state the Stop hook already keeps (`wl_ci.cistate_path`, written by `wl_ci.ci_trouble`): no GitHub call is made here. The head's run is in progress and not red, and the branch holds commits origin lacks, so the advice is to hold them until the run settles; a red with a fix in hand pushes at once.

Both are advice. Nothing refuses a push and nothing here exits non-zero.
"""

import json
import pathlib
import re
import subprocess

RECEIPT_REL = ".ci/cache/prepush-receipt.json"


def _record_policy_rel():
    """`.ci/policy/record-paths.json` through rediacc_ci.policy_paths (check:ci-policy-inventory): wl_proc puts `.ci` on sys.path when it imports, the seam every Stop module already uses to reach rediacc_ci."""
    import wl_proc  # noqa: F401, PLC0415 -- its import puts .ci on sys.path
    from rediacc_ci.policy_paths import policy_rel  # noqa: PLC0415

    return policy_rel("record-paths.json")


RECORD_POLICY_REL = _record_policy_rel()
RECORD_POLICY_VERSION = 1
GIT_TIMEOUT_S = 20


def _git(root, *args):
    """stdout of one read-only git command in `root`, or None on any failure."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def record_glob_re(glob):
    """`glob` as an anchored regex over a repo-relative path: `**` spans directories, `*` and `?` do not (the guard's own rules)."""
    out = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("^%s$" % "".join(out))


def record_of(path, records):
    """The record entry whose glob covers `path` and none of whose `except` globs does, else None."""
    for rec in records:
        if not record_glob_re(rec["glob"]).match(path):
            continue
        if any(record_glob_re(x).match(path) for x in rec["except"]):
            continue
        return rec
    return None


def parse_record_policy(doc):
    """record-paths.json -> ([{glob, except}], error or None). A malformed policy judges nothing, so it is an error, never an empty set."""
    if not isinstance(doc, dict) or doc.get("version") != RECORD_POLICY_VERSION:
        return [], "not version %d" % RECORD_POLICY_VERSION
    raw = doc.get("records")
    if not isinstance(raw, list) or not raw:
        return [], "no records list"
    records = []
    for rec in raw:
        glob = rec.get("glob") if isinstance(rec, dict) else None
        excepted = rec.get("except", []) if isinstance(rec, dict) else None
        if (
            not isinstance(glob, str)
            or not glob
            or not isinstance(excepted, list)
            or not all(isinstance(x, str) and x for x in excepted)
        ):
            return [], "a record needs a glob and an except list"
        records.append({"glob": glob, "except": excepted})
    return records, None


def _records_at_head(root):
    text = _git(root, "show", "HEAD:%s" % RECORD_POLICY_REL)
    if text is None:
        return None
    try:
        records, error = parse_record_policy(json.loads(text))
    except ValueError:
        return None
    return None if error else records


def current_branch(root):
    out = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    name = (out or "").strip()
    return "" if name in ("", "HEAD") else name


def unpushed(root, branch=None):
    """Commits on HEAD that origin/<branch> lacks, or None when that cannot be read (no branch, no remote ref)."""
    branch = branch or current_branch(root)
    if not branch:
        return None
    out = _git(root, "rev-list", "--count", "origin/%s..HEAD" % branch)
    return int(out) if out and out.strip().isdigit() else None


def receipt_behind(root):
    """(n, receipt head short) when the pre-push receipt is `n` >= 1 code commits behind HEAD AND commits are unpushed, else None.

    A missing or unreadable receipt, an unknown head, an unreadable record policy and a branch with nothing to push are all None: a number is stated only when every part of it was read.
    """
    try:
        receipt = json.loads((pathlib.Path(root) / RECEIPT_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    head = receipt.get("head") if isinstance(receipt, dict) else None
    if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40,64}", head):
        return None
    records = _records_at_head(root)
    if records is None:
        return None
    ahead = unpushed(root)
    if not ahead:
        return None
    log = _git(root, "log", "--name-only", "--format=%x00%H", "%s..HEAD" % head)
    if log is None:
        return None
    behind = 0
    for chunk in log.split("\0")[1:]:
        names = [n for n in chunk.split("\n")[1:] if n]
        if any(record_of(n, records) is None for n in names):
            behind += 1
    return (behind, head[:8]) if behind else None


def ci_hold(root, worklist, session_id):
    """(head short, n) when the cached PR run is in progress and not red AND `n` >= 1 commits are unpushed, else None.

    The cache is `wl_ci.cistate_path`'s file: its `sha` is the pushed head, its `info` the rollup `ci_trouble` classified. Only a `running` verdict with no failing job counts: green, red, cancelled and an unreadable cache all say nothing.
    """
    state = pending_run(worklist, session_id)
    if state is None:
        return None
    ahead = unpushed(root)
    if not ahead:
        return None
    return state, ahead


def pending_run(worklist, session_id):
    """The cached head's short sha when its run is in progress and not red, else None. No git and no network."""
    import wl_ci  # noqa: PLC0415 -- the Stop modules are importable only from the hook's own directory

    try:
        cache = json.loads(wl_ci.cistate_path(worklist, session_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(cache, dict) or cache.get("state") != "ok":
        return None
    info, sha = cache.get("info"), cache.get("sha")
    if not isinstance(info, dict) or not isinstance(sha, str):
        return None
    _live, hard, soft = wl_ci.ci_classify(info)
    if hard or soft or wl_ci.ci_gate(info).get("verdict") != "running":
        return None
    return sha[:8]
