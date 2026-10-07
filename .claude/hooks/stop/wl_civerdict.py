"""wl_civerdict: the CI-published `CI Verdict` check-run, surfaced once to every session (agent/plans/PLAN-ci-verdict.md, box D).

WHAT IT READS. `ci-verdict.yml` posts a neutral `CI Verdict` check-run on a Console CI run's head SHA once the run completes: the title names the cause, the summary is `ci_diagnose.render()`, and the text is the `ci-verdict/v1` JSON. One diagnosis made in CI replaces the same diagnosis re-derived by hand in every session that looks at the run, which is the token cost the operator asked to cut (PR #591, 2026-10-02).

WHO SEES IT, AND HOW OFTEN. Every session in the worktree, INCLUDING a session that is not the only live one: `wl_ci.ci_trouble`'s multi-session skip exists so one session is not BLOCKED over a peer's red, and this note blocks nothing. It is a sticky one-shot advisory, shown once per session per (sha, run, attempt) and recorded in `<worklist>.civerdict-seen-<sid8>`, so a second session gets its own one notice and a new attempt re-notifies both.

THE CACHE IS SHARED AND BRANCH-KEYED. `<worklist>.civerdict-<sha1(branch)[:8]>` sits beside the worklist, where every session in the worktree finds it. The network read happens only when the session opted into the CI checks (`WORKLIST_PUBLISH_REF`, or a focus branch), under a TTL, and never more than once per stop; without the opt-in only the cache is read, so a session pays nothing to see a verdict another session (or `ci-trace.py`) already fetched. `write_cache` is the one writer, and the tracer calls it too.

THE SESSIONSTART LINE IS CACHE-ONLY. `session_start_line` makes no network call at all: a new session learns the last known verdict for its branch from disk, and the Stop hook's read refreshes it later.

Never raises into the Stop hook: every read failure is an empty answer, because this is information, not a gate.
"""

import hashlib
import json
import pathlib
import time

import wl_ci
import wl_core as C
import wl_gh

CHECK_NAME = "CI Verdict"
SCHEMA = "ci-verdict/v1"
# Five minutes: a published verdict changes only when a run attempt completes, and the cost of a miss is one stop of delay.
FETCH_TTL_S = 300
SEEN_KEEP = 64
SUMMARY_LINES = 12

# The note and the SessionStart line. Kept here rather than in worklist_messages: the message catalogue test pins every constant there to a positional arity, and these two are keyed.
N_CI_VERDICT = (
    "CI VERDICT for %(branch)s @ %(sha)s (Console CI run %(run)s, attempt %(attempt)s), "
    "published by CI: %(title)s\n%(summary)s\n"
    "    Shown once per session per run attempt. The verdict is neutral and blocks nothing; "
    "deeper reads start at .ci/scripts/ci/ci-trace.py --why"
)

N_CI_VERDICT_SESSION_START = (
    "Last CI verdict for %(branch)s @ %(sha)s (run %(run)s attempt %(attempt)s, "
    "cached %(age)d min ago): %(title)s"
)


def cache_path(worklist, branch):
    """`<worklist>.civerdict-<sha1(branch)[:8]>`, beside the worklist so every session in the worktree shares it."""
    tag = hashlib.sha1(branch_key(branch).encode("utf-8")).hexdigest()[:8]
    return pathlib.Path("%s.civerdict-%s" % (worklist, tag))


def branch_key(branch):
    """The branch as `wl_core.git_branch` slugs it, so a raw ref (`ci-trace --ref feat/x`) and the hook's slugged branch name one cache file."""
    return C.AGENT_BRANCH_RE.sub("-", (branch or "").strip()).strip("-.")


def seen_path(worklist, session_id):
    """`<worklist>.civerdict-seen-<sid8>`: the (sha, run, attempt) keys this session was already shown."""
    return pathlib.Path("%s.civerdict-seen-%s" % (worklist, (session_id or "")[:8]))


def read_cache(worklist, branch):
    return wl_gh.cache_load(cache_path(worklist, branch))


def write_cache(worklist, branch, sha, verdict, title="", summary="", source="check-run", now=None):
    """Record what is known about `sha`'s verdict. `verdict` None means "looked, none published yet", which the TTL keeps from being re-asked every stop."""
    wl_gh.cache_write(
        cache_path(worklist, branch),
        {
            "branch": branch,
            "sha": sha,
            "at": time.time() if now is None else now,
            "source": source,
            "title": title,
            "summary": summary,
            "verdict": verdict,
        },
    )


def parse_check_run(check_run):
    """(verdict dict, title, summary) from one check-run, or None when it does not carry a `ci-verdict/v1` document."""
    out = (check_run or {}).get("output") or {}
    try:
        doc = json.loads(out.get("text") or "")
    except ValueError:
        return None
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        return None
    return doc, out.get("title") or "", out.get("summary") or ""


def fetch(root, sha):
    """(verdict, title, summary) for `sha`'s newest github-actions `CI Verdict`, or None. One `gh api` call."""
    owner, name = wl_ci.repo_slug(root)
    if not owner or not sha:
        return None
    data, _err = wl_gh.call(
        [
            "api",
            "repos/%s/%s/commits/%s/check-runs?check_name=CI%%20Verdict&per_page=100"
            % (owner, name, sha),
        ],
        cwd=root,
    )
    runs = [
        r
        for r in ((data or {}).get("check_runs") or [])
        if ((r.get("app") or {}).get("slug") == "github-actions")
    ]
    parsed = [p for p in (parse_check_run(r) for r in runs) if p]
    if not parsed:
        return None
    # Newest (run, attempt) wins, whatever order the API listed them in.
    return max(parsed, key=lambda p: (_int(p[0].get("run_id")), _int(p[0].get("attempt"))))


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def refresh(root, worklist, branch, ref, now=None):
    """The cache entry for `branch`, re-read from GitHub when the tip moved or the TTL ran out. `ref` is the remote branch whose tip is read."""
    now = time.time() if now is None else now
    tip = C._git(root, "rev-parse", "origin/%s" % ref) if ref else ""
    entry = read_cache(worklist, branch)
    if not tip:
        return entry
    if (
        entry
        and entry.get("sha") == tip
        and wl_gh.cache_fresh(entry, FETCH_TTL_S, FETCH_TTL_S, now)
    ):
        return entry
    got = fetch(root, tip)
    if got is None:
        # Keep a verdict already known for this SHA (a transient read failure must not erase it); otherwise record the miss so the TTL holds.
        if entry and entry.get("sha") == tip and entry.get("verdict"):
            return entry
        write_cache(worklist, branch, tip, None, now=now)
    else:
        verdict, title, summary = got
        write_cache(worklist, branch, tip, verdict, title, summary, now=now)
    return read_cache(worklist, branch)


def key_of(entry):
    """`sha:run:attempt`, the unit a session is notified about once."""
    v = (entry or {}).get("verdict") or {}
    return "%s:%s:%s" % (
        v.get("head_sha") or (entry or {}).get("sha") or "",
        v.get("run_id") or "",
        v.get("attempt") or "",
    )


def _summary(entry):
    lines = [ln for ln in str(entry.get("summary") or "").splitlines() if ln.strip()]
    return "\n".join("    " + ln for ln in lines[:SUMMARY_LINES])


def format_note(entry):
    v = entry.get("verdict") or {}
    return N_CI_VERDICT % {
        "branch": entry.get("branch") or "?",
        "sha": str(v.get("head_sha") or entry.get("sha") or "?")[:8],
        "run": v.get("run_id") or "?",
        "attempt": v.get("attempt") or "?",
        "title": entry.get("title") or str(v.get("verdict") or "unknown"),
        "summary": _summary(entry) or "    (no summary published)",
    }


def note(root, worklist, session_id, ref=None, branch=None, now=None):
    """The one-time note for this session, or "". Marks it seen. Never raises."""
    try:
        branch = branch or ref or C.git_branch(root)
        if not branch:
            return ""
        entry = (
            refresh(root, worklist, branch, ref, now=now) if ref else read_cache(worklist, branch)
        )
        if not entry or not entry.get("verdict"):
            return ""
        key = key_of(entry)
        sp = seen_path(worklist, session_id)
        seen = wl_gh.load_json(sp)
        seen = seen if isinstance(seen, list) else []
        if key in seen:
            return ""
        wl_gh.cache_write(sp, ([*seen, key])[-SEEN_KEEP:])
        return format_note(entry)
    except Exception:  # noqa: BLE001 -- information, never a reason to wedge a stop
        return ""


def session_start_line(worklist, branch):
    """One line for SessionStart from the cache alone. Zero network calls, by contract."""
    try:
        entry = read_cache(worklist, branch) if branch else None
        if not entry or not entry.get("verdict"):
            return ""
        v = entry["verdict"]
        age_min = max(0, int((time.time() - float(entry.get("at") or 0)) // 60))
        return N_CI_VERDICT_SESSION_START % {
            "branch": branch,
            "sha": str(v.get("head_sha") or entry.get("sha") or "?")[:8],
            "run": v.get("run_id") or "?",
            "attempt": v.get("attempt") or "?",
            "age": age_min,
            "title": entry.get("title") or v.get("verdict") or "unknown",
        }
    except Exception:  # noqa: BLE001
        return ""
