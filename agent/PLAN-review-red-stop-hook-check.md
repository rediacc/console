# PLAN: a stop-hook check for "CI green, Review Complete red" -- the local
# session has the context a remote job does not
Status: done
Owner: review-red-stop-hook-check plan agent, branch 0827-1 (PR #579)
Updated: 2026-08-31

## Headline conclusion (read this before the rest)

The gap is real and currently has ZERO detection anywhere in the hook suite.
`grep -n "Review Complete" .claude/hooks/stop/*.py` finds exactly the six
hits inside `wl_ci.py`'s `CI_NONBLOCKING_CONTEXTS` comment and its own
`_selftest()` fixtures (`wl_ci.py:183-198`, `920-1014`) -- all of them about
KEEPING "Review Complete" OUT of the general CI-red bucket, per the
`c9e4b146`/`387bfba5` fix this plan must not weaken. `grep -n "Review
Complete\|review-status\|review_gate" .claude/hooks/stop/wl_checks.py` and
the same grep against `worklist_messages.py` return **nothing** beyond one
unrelated `M.V_CI_RED` reference. Nothing in the hook suite reads the
"Review Complete" check-run's own conclusion for ANY purpose other than
excluding it from `ci_classify()`'s hard/soft rollup. So the operator's
observation is exactly right: the local session currently has no proactive
signal at all for "review went red and nobody replied" -- it is purely a
`gh pr checks` / trace-log artifact the session has to notice by accident,
four times in one session per the brief.

The fix is a new, structurally-separate stop-hook check -- `review_gate_row`
+ `review_red` in `wl_ci.py`, wired into `wl_checks.py` at the SAME `T_MISSION`
priority tier as `V_CI_RED`, firing a new `V_REVIEW_RED` message -- that:

1. Reuses the SAME rollup payload `ci_trouble()` already fetched for this
   stop (zero extra GraphQL calls to classify red-or-not: "Review Complete"
   is already a raw context in that payload, `wl_ci.py:256-259`, just
   filtered OUT by `ci_classify()` at `wl_ci.py:421-422`).
2. Fires ONLY when `ci_trouble()`'s own verdict for everything else is `"ok"`
   -- i.e. the exact same "green" `pr-finish` already trusts
   (`wl_checks.py:3900`, `_prf_green = cistate == "ok"`) -- AND the raw
   "Review Complete" context's `conclusion` is a `CI_FAIL_CONCLUSIONS` value.
   This is a NEW, separate function, never folded into `ci_classify`'s
   hard/soft buckets, so the `CI_NONBLOCKING_CONTEXTS` fix stays intact and
   unweakened.
3. Fetches the check-run's own `output.title`/`output.summary` ONE time (a
   single REST call, cached, fired only in the already-rare positive case)
   and QUOTES IT VERBATIM, because that text is produced by the real gates
   (`check-review-comments.sh`, `check-review-report-replies.sh`,
   `check-resolved-threads.sh` via `review-status.sh`) -- reusing the actual
   source of truth rather than reimplementing a second, driftable definition
   of "unreplied", per the constraint.
4. Gives the two reply shapes' EXACT, distinct commands (inline `/replies`
   endpoint vs. plain top-level `gh api .../issues/.../comments -X POST`),
   copied verbatim from the two hygiene scripts' own instructions, not
   invented here.
5. Names the CORRECT re-evaluation command -- `gh workflow run
   review-status.yml --repo <owner>/<name> --ref main -f pr_number=<n>` --
   and explicitly tells the session NOT to do what it did four times
   (`gh run rerun <run-id> --failed`), because that cannot ever work here:
   `review-status.sh`'s own header says its job "exits 0 after posting a
   `failure` conclusion... A non-zero exit therefore always means the
   REPORTER broke, never that the PR is unhealthy" (`review-status.sh:33-36`)
   -- so the Review Status workflow run this endpoint lives on never HAS a
   failed job for `--failed` to find. `--repo ... -f pr_number=...` is not
   invented for this plan either: it is the exact `workflow_dispatch` input
   already added to `review-status.yml` by the prior
   `PLAN-github-actions-workflow-run-trigger-fix.md` (F1), confirmed live in
   the tree at `.github/workflows/review-status.yml:36-45`.
6. Applies the SAME bounded-ceiling + acknowledgement discipline `ci_trouble`
   uses (`wl_ci.py:735-823`), on ITS OWN marker file and signature -- not
   ci_trouble's -- because a `Review Complete` red is not always a
   quick-reply case (see "on the ceiling call", below).

---

## Verified against the real tree

All file:line references below were read directly out of
`/home/developer/console` on branch `0827-1` as of this plan's `Updated:`
date; re-verify before editing if more work has landed on these files.

### V1. `CI_NONBLOCKING_CONTEXTS` exists and does exactly what it says, nothing more

`wl_ci.py:183-198`:
```python
# NEVER A FAILURE, regardless of conclusion. "Review Complete" is a check-run
# posted directly by .ci/scripts/review/review-status.sh from a workflow no CI
# job references -- its own `output.summary` says outright "this check ... can
# never block Console CI". ...
CI_NONBLOCKING_CONTEXTS = {"Review Complete"}
```
and `ci_classify()` (`wl_ci.py:402-461`) skips any context whose
`context`/`name` is in that set, at line 421-422, BEFORE it can contribute to
`live`, `hard`, or `soft`. This is correct and this plan does not touch it.
The exclusion is the reason a red "Review Complete" currently produces
NOTHING from `ci_trouble()` -- no `trouble`, no `soft`, no `ci_report` -- it
reads as plain `"ok"`, identical to a PR with a genuinely clean, fully green
head. That silent identity is the gap.

### V2. `ci_rollup()` already reads "Review Complete" into `info["contexts"]` -- no new network read needed to classify it

`ci_query()` (`wl_ci.py:246-260`) requests, per context: `... on
CheckRun{name status conclusion databaseId detailsUrl
checkSuite{workflowRun{databaseId}}}`. This means every `ci_trouble()` call
that returns `"ok"` already has the raw "Review Complete" `CheckRun` node
(name + conclusion) sitting unused in `cidetail["contexts"]`. Classifying
red-vs-clean therefore costs **zero** extra `gh api graphql` calls -- it is a
second, pure read of a payload already paid for.

### V3. `review-status.sh` is the single source of truth for what "unreplied" means, and it already writes the fix commands into the check-run body

`review-status.sh:317-326` (verdict block) and `:405-421` posts, via
`post_check()`, `output.summary` built from a `failures[]` array where each
hygiene-script failure entry is `tail -n 20 "$out_file"`
(`review-status.sh:394-399` -- read from the tree during this session's
exploration). The two scripts whose tails matter here:

- `.ci/scripts/quality/check-review-comments.sh` -- covers BOTH surfaces in
  one script: SURFACE 1 is inline review-thread comments
  (`repos/{REPO}/pulls/{PR}/comments`, keyed on `in_reply_to_id`), SURFACE 2
  is the top-level review summary (`repos/{REPO}/issues/{PR}/comments`,
  identified structurally by `select(.user.login | contains("github-actions"))`
  plus either `json:review-findings` fence or a `^#{1,3} Review verdict`
  heading -- `check-review-comments.sh`, SURFACE-2 comment block). Its
  failure output gives the EXACT two remediation commands, verbatim:
  ```
  gh api repos/${REPO}/pulls/${PR_NUMBER}/comments \
    --jq '.[] | select(.in_reply_to_id == null) | {id, path, line, body}'
  gh api repos/${REPO}/pulls/${PR_NUMBER}/comments/{COMMENT_ID}/replies \
    -X POST -f body="Your substantive reply here"
  ```
  for inline, and
  ```
  gh api repos/${REPO}/issues/${PR_NUMBER}/comments -X POST \
    -f body="Re: review summary ${SUMMARY_ID}..."
  ```
  for the top-level summary, plus the explicit warning: `repos/.../issues/.../
  comments/{id}/replies` and `repos/.../pulls/.../comments/{id}/replies` (with
  an ISSUE id) both 404, "verified against the live API" -- this is precisely
  the mistake this session already made once.
- `.ci/scripts/quality/check-review-report-replies.sh` -- covers the
  PIPELINE'S OWN wrapper comment, keyed on the producer constant
  `REPORT_PREFIX='**Claude finished'` (`check-review-report-replies.sh:52-56`,
  citing `claude-review-gate.sh:188` as the literal producer). Same reply
  rule (`is_low_effort_reply`, `SUMMARY_MIN_CHARS=30`,
  `SUMMARY_LONGFORM_CHARS=200`, different-author, posted-after, cites-id-or-
  longform), same 404 warning, same "post a NEW top-level comment" fix.

**The reply rule, read once and never reimplemented in Python.** Both scripts
independently document (and `test-review-status.sh` asserts they do not
drift) the SAME four-part rule for "this counts as a reply": (a) a different
author than the bot, (b) posted after the target comment, (c) not a
stock/low-effort string and past a 30-char floor, (d) either cites the
target's numeric id or exceeds 200 chars. This plan's new check never
re-derives this rule -- it quotes the check-run's own verdict, which was
already produced by these exact scripts.

### V4. `check-resolved-threads.sh` is a THIRD, distinct failure shape the new check must not misdiagnose as "reply to a comment"

`check-resolved-threads.sh:1-7`: "This is separate from 'unreplied comments'
-- a thread can have replies but still be unresolved... Also checks if any
reviewer has requested changes." A `Review Complete` red can therefore ALSO
mean "an approved-looking thread was never marked resolved on GitHub" or "a
reviewer requested changes", neither of which a `/replies` POST fixes. The
currency assertion (`review-status.sh:264-316`, "head has not been reviewed
at all") is a FOURTH shape. **The new check's message must not assume every
red is the two-reply-shape case** -- it must show the real `output.summary`
(which already distinguishes these, since each hygiene script contributes
its own `## Failures` bullet) and only give the two reply-command blocks as
"if the summary above says X, do Y", never as an unconditional instruction.

### V5. The correct re-evaluation command already exists in this repo, and `gh run rerun --failed` cannot work on this check-run

`review-status.sh:33-36`: "The script exits 0 after posting a `failure`
conclusion: the verdict lives in the check-run, and a red JOB would be a
second, confusing signal on the same head SHA. A non-zero exit therefore
always means the REPORTER broke, never that the PR is unhealthy." The
`Review Status` workflow's own job therefore always reports `success` to
Actions regardless of what `Review Complete` says -- there is never a
"failed job" on that run for `gh run rerun <run-id> --failed` to select.
`.github/workflows/review-status.yml:36-45` (verified in the live tree)
already carries:
```yaml
  workflow_dispatch:
    inputs:
      pr_number:
        description: 'PR number to re-evaluate (used when the workflow_run
          entry point could not resolve the PR, e.g. after a Claude Review
          workflow_dispatch)'
        required: true
        type: string
```
built by the prior `agent/PLAN-github-actions-workflow-run-trigger-fix.md`
(its own Status section: "`review-status.yml` gained the `workflow_dispatch`
trigger with `pr_number`... F3 not built"). `claude-review-reusable.yml`
already calls this exact form
(`gh workflow run review-status.yml --repo rediacc/console --ref main -f
pr_number=...`) from its own "Nudge review-status.yml with the resolved PR"
step. This plan's message reuses that identical command -- it does not
invent a new re-trigger mechanism.

### V6. `V_CI_RED`'s tier, ceiling, and wiring pattern, exactly as they exist today

- Tier: `wl_checks.py:2354-2374`, `T_MISSION` frozenset includes `"ci-red"`
  alongside `"pr-finish"`, `"open-items"`, etc. -- the tier this new check
  should join, per the operator's own words ("this should be a priority").
- Ceiling: `ci_trouble()`'s docstring, `wl_ci.py:735-761`: "A check that
  demands what a session cannot produce deadlocks it... So there are TWO
  exits" -- naming the failing item in the stop message (ack), or a hard
  ceiling of `CI_MAX_BLOCKS` (env `WORKLIST_CI_MAX_BLOCKS`, default `2`)
  consecutive blocks per failure SIGNATURE (`sha1(sha|sorted names)`,
  `wl_ci.py:809-811`), after which it "downgrades to a loud report on the
  allowed stop", never silently.
- Wiring: `wl_checks.py:3793-3851` -- `ci_trouble()` called once,
  `cistate`/`cidetail` branch into `vadd("ci-unreadable"...)`,
  `vadd("ci-red", True, M.V_CI_RED % (...))`, or a non-blocking `ci_report`
  string appended later (`wl_checks.py:3936-` onward, verified but not fully
  quoted here). `cistate == "ok"` currently falls through with NO explicit
  branch until the unrelated `pr-finish` block at `wl_checks.py:3885-3935`
  reads `cidetail` again for its own "green" box. **This exact fallthrough
  point (`elif cistate in ("trouble", "downgraded", "soft"): ...` ending
  around `wl_checks.py:3851`, before the `# ---- v21: THE pr-babysit FINISH
  LINE` comment) is where the new check's call belongs**, because it is the
  only place in the file that already holds a freshly-classified `"ok"`
  `cidetail` for THIS session's PR.

---

## The fix

### F1. New pure classifier: `wl_ci.review_gate_row(info)`

Structurally next to `ci_classify()`, in `wl_ci.py`:

```python
def review_gate_row(info):
    """(state, row) -- what does "Review Complete" say for THIS rollup.

    state: absent | clean | red. `row` is the raw context dict, or None.

    DELIBERATELY SEPARATE from ci_classify(). Folding this into hard/soft
    would be exactly the bug CI_NONBLOCKING_CONTEXTS exists to prevent --
    this function's whole job is to look at the ONE context ci_classify()
    is told to ignore, using the SAME shape-matching ci_classify already
    proved handles both CheckRun.name and StatusContext.context
    (wl_ci.py's own selftest, "the filter matches on EITHER shape").

    `truncated` fails CLOSED to absent: a partial context page proves
    nothing about a context it never reached, so this function never
    asserts "clean" or "red" off a page that might not contain the row at
    all. It can only ever MISS a real red (silence), never invent one.
    """
    if info.get("truncated"):
        return "absent", None
    for c in info.get("contexts") or []:
        name = c.get("context") or c.get("name") or ""
        if name not in CI_NONBLOCKING_CONTEXTS:
            continue
        concl = (c.get("conclusion") or c.get("state") or "").upper()
        if concl in CI_FAIL_CONCLUSIONS:
            return "red", c
        return "clean", c
    return "absent", None
```

Reuses `CI_NONBLOCKING_CONTEXTS` (so a future second non-blocking context
name is covered by both functions automatically) and `CI_FAIL_CONCLUSIONS`
(the same `{"FAILURE", "TIMED_OUT", "STARTUP_FAILURE", "ACTION_REQUIRED"}`
set `ci_classify` already uses) -- no new constant invented for "what counts
as red".

### F2. New detail fetch: `wl_ci.review_gate_detail(root, info, row)`

One bounded REST call, fired only from the caller below (i.e. only once the
rare precondition already holds), mirroring `ci_steps()`'s "ONE bounded REST
call... only on the path that is about to speak" discipline:

```python
def review_gate_detail(root, info, row):
    """(title, summary, html_url) for the "Review Complete" check-run,
    read directly, not guessed. This IS review-status.sh's own posted
    verdict -- the same text a human reads in `gh pr checks` -- so there is
    no second definition of "what's wrong" to drift from the real gate.
    """
    data, err = _gh_json(
        root,
        [
            "api",
            "repos/%s/%s/commits/%s/check-runs" % (info["owner"], info["name"], info["sha"]),
            "-f", "check_name=Review Complete",
        ],
        timeout=20,
    )
    if data is None:
        return "", "(could not re-fetch Review Complete's own summary: %s)" % err, row.get("detailsUrl") or ""
    runs = (data or {}).get("check_runs") or []
    run = runs[-1] if runs else {}
    out = run.get("output") or {}
    return out.get("title") or "", out.get("summary") or "", run.get("html_url") or row.get("detailsUrl") or ""
```

Cached exactly like `_ci_cache_write`/`cistate_path` (new
`reviewcache_path(worklist, session_id)`, same `CI_CACHE_LIVE_S` /
`CI_CACHE_FINAL_S` TTL split, keyed on `info["sha"]`) so a session sitting on
an unresolved red for several stops does not re-fetch the summary every
time.

### F3. New orchestrator: `wl_ci.review_red(root, worklist, session_id, cidetail, ack_text)`

Called ONLY when the caller already has `cistate == "ok"` for this exact PR
(so it inherits `ci_trouble`'s own `WORKLIST_PUBLISH_REF` opt-in and
`S.sole_live_session` multi-session guard for free -- no new repo-wide scan,
satisfying the "current session's PR only" scoping requirement):

```python
REVIEW_MAX_BLOCKS = int(os.environ.get("WORKLIST_REVIEW_MAX_BLOCKS", "2"))

def reviewmark_path(worklist, session_id):
    return worklist.with_suffix(".reviewmark-%s" % (session_id or "unknown")[:8])

def review_red(root, worklist, session_id, cidetail, ack_text):
    """(state, detail) -- is "Review Complete" red while the rest of this
    PR's CI is clean, and has this already been reported enough times.

    state: clean | absent | trouble | downgraded
    """
    rstate, row = review_gate_row(cidetail)
    if rstate != "red":
        return rstate, None
    title, summary, url = review_gate_detail(root, cidetail, row)
    marker_p = reviewmark_path(worklist, session_id)
    sig = hashlib.sha1(
        ("%s|%s" % (cidetail.get("sha") or "", title)).encode("utf-8", "replace")
    ).hexdigest()[:12]
    try:
        mark = json.loads(marker_p.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        mark = {}
    blocks = int(mark.get("blocks") or 0) if mark.get("sig") == sig else 0
    low = (ack_text or "").lower()
    acked = "review complete" in low
    detail = {
        "row": row, "title": title, "summary": summary, "url": url,
        "pr": cidetail.get("pr"), "owner": cidetail["owner"], "name": cidetail["name"],
        "sha": cidetail.get("sha"), "n": blocks,
    }
    if acked or blocks >= REVIEW_MAX_BLOCKS:
        return "downgraded", detail
    with contextlib.suppress(OSError):
        marker_p.write_text(json.dumps({"sig": sig, "blocks": blocks + 1}), encoding="utf-8")
    detail["n"] = blocks + 1
    return "trouble", detail
```

The signature is keyed on `(sha, title)` rather than `(sha, verdict-hash)` --
`review-status.sh`'s `title` already distinguishes "Reviewed, but needs
attention (see failures)" from "Review is not complete for this head", so a
NEW distinct failure shape on the same head (e.g. hygiene clears but currency
then goes stale again) re-arms the budget, matching `ci_trouble`'s own "a new
red is worth interrupting for exactly once more" rule.

### F4. Wiring into `wl_checks.py`, right after the existing `ci_trouble` branch

Insert immediately after the `elif cistate in ("trouble", "downgraded",
"soft"): ...` block ends (currently `wl_checks.py:3806-3851`), before the `#
---- v21: THE pr-babysit FINISH LINE` comment:

```python
elif cistate == "ok":
    try:
        rstate, rdetail = wl_ci.review_red(
            root, worklist, session_id, cidetail,
            (last_msg or "") + "\n" + "\n".join(deferred),
        )
    except Exception as exc:  # noqa: BLE001 -- a broken check must SAY SO
        rstate, rdetail = "unreadable", "%s: %s" % (type(exc).__name__, str(exc)[:120])
    if rstate == "unreadable":
        vadd("review-unreadable", True, M.V_REVIEW_UNREADABLE % rdetail)
    elif rstate == "trouble":
        vadd(
            "review-red",
            True,
            M.V_REVIEW_RED
            % (
                rdetail["pr"], rdetail["sha"], rdetail["title"], rdetail["summary"],
                rdetail["owner"], rdetail["name"], rdetail["pr"],
                rdetail["owner"], rdetail["name"], rdetail["pr"],
                rdetail["owner"], rdetail["name"], rdetail["pr"],
                rdetail["owner"], rdetail["name"], rdetail["pr"],
                wl_ci.REVIEW_MAX_BLOCKS, rdetail["n"], me8, rdetail["pr"],
            ),
        )
    elif rstate == "downgraded":
        ci_report = (ci_report + "\n\n" if ci_report else "") + M.REVIEW_NOTE_DOWNGRADED % (
            rdetail["pr"], rdetail["title"], rdetail["n"],
        )
```

(Placeholder count above is illustrative -- exact `%`-tuple arity to be
finalized against the final `V_REVIEW_RED` template text at implementation
time; the important structural facts are: it reuses `cidetail` from the SAME
`ci_trouble()` call, it reuses the existing `ci_report` accumulator so a
downgraded review-red rides the same non-blocking note path `CI_NOTE_
DOWNGRADED` already uses, and it never re-resolves the PR independently.)

Tier registration, `wl_checks.py:2354-2374` (`T_MISSION` frozenset): add
`"review-red"` beside `"ci-red"`. `wl_checks.py:2400-2431` (`T_INTEGRITY`
frozenset): add `"review-unreadable"` beside `"ci-unreadable"`.

### F5. New message templates in `worklist_messages.py`

Placed beside `V_CI_RED` (`worklist_messages.py:255-269`), same voice and
same structural beats (name the exact facts, name the exact commands, state
the ceiling, give the escape hatch):

```python
V_REVIEW_RED = """CI IS GREEN ON PR #%s BUT "Review Complete" IS RED (head %s), AND NOTHING
IS WATCHING IT. This is NOT a genuine CI failure -- CI_NONBLOCKING_CONTEXTS
already keeps "Review Complete" out of the CI red/soft bucket for exactly
that reason -- but it is a separate signal THIS session has the context to
resolve (what it just pushed, what the review is about) and a remote job
does not.

Review Complete's own verdict, read from the check-run itself, not guessed:
    Title: %s
%s

WHAT TO DO, BY SHAPE. The summary above already says which surface(s) are
unanswered -- reply on THAT surface. An inline reply on a top-level comment
(or vice versa) 404s; this session has made that mistake once already.

  INLINE review-thread comments (have a path/line):
      gh api repos/%s/%s/pulls/%s/comments --jq '.[] | select(.in_reply_to_id == null)'
      gh api repos/%s/%s/pulls/%s/comments/<id>/replies -X POST -f body="<substantive reply>"

  TOP-LEVEL review summary or report (posted by github-actions[bot], body
  starting "## Review verdict" or "**Claude finished"; there is NO /replies
  endpoint for an issue comment -- 404, verified):
      gh api repos/%s/%s/issues/%s/comments -X POST -f body="<substantive reply>"

  If the summary instead names an UNRESOLVED THREAD or an UNREVIEWED HEAD,
  neither reply command above fixes it -- resolve the thread on GitHub, or
  push a change, per check-resolved-threads.sh / the currency check in
  review-status.sh.

A reply must be SUBSTANTIVE: past 30 characters, not a stock "done"/"ack"/
"thanks", posted by someone OTHER than the bot, and either cite the target
comment's id or run past 200 characters -- the exact rule
check-review-comments.sh and check-review-report-replies.sh already apply
(cited here, not re-implemented).

THEN RE-EVALUATE. Do NOT `gh run rerun <run-id> --failed` -- Review Status's
own job always exits 0 (the verdict lives in the check-run body, not the job
conclusion), so there is never a failed job for --failed to find. Nudge the
same workflow_dispatch path review-status.yml already has for this:
    gh workflow run review-status.yml --repo %s/%s --ref main -f pr_number=%s

THIS CANNOT TRAP YOU: it blocks at most %d consecutive stop(s) per verdict
(this is %d), then downgrades to a report for that verdict forever. To clear
it now, post the reply(ies) and re-dispatch, or name "Review Complete" in
your stop message, or -- if it is not yours to fix -- file
    - [?] (%s) Review Complete red on PR #%s: <one-line reason>  DEFAULT: <the ACTION you take alone -- 'hold' is not one>  WHY: <why it is not yours>  HOW: <who or what resolves it>"""

REVIEW_NOTE_DOWNGRADED = """CI on PR #%s: "Review Complete" is still red ("%s"), but this has
already been reported %d time(s) and downgraded per the no-deadlock rule --
this is a non-blocking reminder, not a new block. Same fix as before: reply
on the right surface, then `gh workflow run review-status.yml --repo <owner>/<name>
--ref main -f pr_number=%s`."""

V_REVIEW_UNREADABLE = (
    "THIS IS A HOOK BUG: the Review Complete check-run lookup failed (%s), so "
    "that check is blind. It blocks rather than passing quietly, per "
    "no-escape-hatch."
)
```

---

## On the ceiling call (constraint 2)

**Apply a bounded ceiling, structurally identical to `V_CI_RED`'s, but on its
own marker/signature -- do not share `ci_trouble`'s ceiling state.**

The naive argument against a ceiling is that this condition is always
self-clearing by the SAME session's own action (post a reply, re-dispatch),
unlike a genuine CI red that "may not be this session's to fix" (`wl_ci.py`'s
own reasoning for `ci_trouble`'s ceiling, `wl_ci.py:751-757`). That argument
holds for the two-reply-shape case, which is the common one the brief
reports (~4 times in one session). It does NOT hold for the other two shapes
V4 above identifies:

- The triggering `Claude Review` run itself concluded `failure`/`timed_out`
  (`review-status.sh:279-291`) -- a genuine pipeline problem that may need
  real debugging, structurally identical to a CI red.
- `check-resolved-threads.sh` failing because a reviewer "requested changes"
  -- resolving that may require a substantive code change, not a quick
  reply, and could legitimately take several turns.

Since the new check cannot always tell these apart cheaply before firing (it
would need to parse the FIRST LINE of `summary` to distinguish "reply-shape"
from "not", which is exactly the kind of guessing constraint 4 warns
against), the safe default is: apply the SAME bounded-N ceiling and ack
escape uniformly, `REVIEW_MAX_BLOCKS` defaulting to `2` (same default as
`CI_MAX_BLOCKS`, independently overridable via `WORKLIST_REVIEW_MAX_BLOCKS`
so operators can tune the two independently later if the common case proves
to need more patience than the rare one). This is `adhoc_watch`'s
"unconditional, no ceiling" shape REJECTED, in favor of `ci_trouble`'s
bounded shape, because unlike `adhoc_watch` ("the remedy is entirely yours --
stop the task, run the script", `worklist_messages.py`'s `V_ADHOC_WATCH`)
this check's remedy is NOT always entirely and immediately within the
session's reach.

---

## Test / control plan (fixture-based, no live API calls)

Extend `wl_ci.py`'s `_selftest()` (`wl_ci.py:917-1038`) in place, same
`check(label, cond, detail)` harness, same synthetic-fixture-shaped-like-
real-GraphQL-contexts discipline the existing controls already use. Bump the
floor in `.claude/hooks/test-hooks.sh:1905-1924` from `n -lt 6` to reflect
the added control count (illustratively `n -lt 12`, i.e. 6 new controls
alongside the 6 already there).

### T1. FIRE -- the real defect shape: CheckRun red, everything else clean

```python
review_complete_red_only = {
    "rollup": "SUCCESS",
    "truncated": False,
    "contexts": [
        {
            "status": "COMPLETED", "conclusion": "FAILURE", "name": "Review Complete",
            "databaseId": 1, "checkSuite": {"workflowRun": {"databaseId": 1}},
            "detailsUrl": "https://example/1",
        }
    ],
}
state, row = review_gate_row(review_complete_red_only)
check(
    "FIRE: Review Complete conclusion=FAILURE reads as 'red'",
    state == "red" and (row or {}).get("name") == "Review Complete",
    "state=%r row=%r" % (state, row),
)
```

### T2. CONTROL -- clean conclusion never fires

```python
review_complete_clean = {
    "rollup": "SUCCESS", "truncated": False,
    "contexts": [{"status": "COMPLETED", "conclusion": "SUCCESS", "name": "Review Complete"}],
}
check(
    "CONTROL: Review Complete conclusion=SUCCESS reads as 'clean', never fires",
    review_gate_row(review_complete_clean)[0] == "clean",
)
```

### T3. CONTROL -- absent (never posted, e.g. draft PR) is silence, not a false red

```python
no_review_context = {"rollup": "SUCCESS", "truncated": False, "contexts": []}
check(
    "CONTROL: no Review Complete context at all reads as 'absent', not 'red'",
    review_gate_row(no_review_context)[0] == "absent",
)
```

### T4. CONTROL -- truncated page fails closed to 'absent', never asserts red or clean off a partial read

```python
truncated_page = {"rollup": "SUCCESS", "truncated": True, "contexts": []}
check(
    "CONTROL: a truncated context page never asserts a verdict for a row it might not have reached",
    review_gate_row(truncated_page)[0] == "absent",
)
```

### T5. CONTROL -- StatusContext shape matches too (mirrors `ci_classify`'s own dual-shape control)

```python
status_shape_red = {
    "rollup": "SUCCESS", "truncated": False,
    "contexts": [{"__typename": "StatusContext", "state": "FAILURE", "context": "Review Complete"}],
}
check(
    "CONTROL: the row detector matches EITHER shape, same as ci_classify's own filter",
    review_gate_row(status_shape_red)[0] == "red",
)
```

### T6. CONTROL -- exact-name match only, a differently-named "Review ..." job is not swallowed

```python
review_gate_unrelated = {
    "rollup": "SUCCESS", "truncated": False,
    "contexts": [{"status": "COMPLETED", "conclusion": "FAILURE", "name": "Review Gate"}],
}
check(
    "CONTROL: an unrelated job merely containing 'Review' is not read as the review-gate row",
    review_gate_row(review_gate_unrelated)[0] == "absent",
)
```

### T7. FIRE + CONTROL pair for `review_red`'s ceiling/ack (integration-level, needs a temp worklist path like the existing marker-file tests use elsewhere in this suite)

- FIRE: first two calls with the same `(sha, title)` signature return
  `"trouble"` with `n` incrementing 1, 2; the THIRD call with the same
  signature returns `"downgraded"` (proves the ceiling fires, mirroring
  `ci_trouble`'s own `CI_MAX_BLOCKS` behavior).
- CONTROL: a call whose `ack_text` contains `"review complete"` (any case)
  returns `"downgraded"` immediately, on the FIRST call, without spending a
  block -- proving the ack escape is honored exactly like `ci_trouble`'s.
- CONTROL: a DIFFERENT `title` on the same `sha` (i.e. the failure mode
  changed, e.g. from "needs attention" to "not complete for this head") gets
  a FRESH signature and re-arms at `n=1` -- proving a genuinely new problem
  is worth interrupting for again, matching `ci_trouble`'s "new failure set"
  re-arm rule.

### T8. Integration control -- `wl_checks.py` never reaches `review_red` when `cistate != "ok"`

Not a `wl_ci.py --selftest` control (it is about the CALLER's branching, in
`wl_checks.py`), but must be verified by hand or a `wl_checks`-level test
before landing: construct a fixture where a genuine hard CI failure AND a
red "Review Complete" coexist on the same head. `ci_trouble()` must still
return `"trouble"` (the genuine failure), the `elif cistate == "ok":` branch
must not execute at all, and `review_red` must never be called -- proving
the two checks cannot double-fire or race on the same stop. This is the
direct regression control for "do not lump this into ci_classify's hard/soft
bucketing" (constraint 1): the genuine CI red must still win the turn's
attention, with the review-red signal silent until CI is actually clean.

### T9. No live API calls anywhere in the above

Every fixture is a literal Python dict shaped like the real GraphQL/REST
payloads already documented in `wl_ci.py`'s comments (`ci_query`'s selection
set, `post_check`'s `output: {title, summary}` shape) -- exactly the
`--selftest` discipline `docs/agent-reference/ci-gates.md`'s control-first
testing conventions and this file's own existing six controls already
follow. `review_gate_detail()`'s REST call is NOT unit-tested against a live
endpoint; it is exercised only via `_gh_json`'s existing error-string
contract (already covered generically elsewhere in this file), and its
CALLER (`review_red`) is the unit tested against a fixture that supplies
`title`/`summary` directly, never through a real `gh` invocation.

---

## Implementer notes

- Every file:line reference above was checked against the tree on branch
  `0827-1` as of this plan's `Updated:` date. Re-verify line numbers before
  editing -- `wl_checks.py` is 5659 lines and under active edit from other
  worklist work in the same session.
- `review_gate_detail`'s REST call needs `owner`/`name`/`sha` off the SAME
  `cidetail` dict `ci_trouble` already returned for `"ok"` -- do not
  re-resolve the PR or re-derive the repo slug; `wl_ci.repo_slug` is already
  called once per stop inside `ci_rollup`, and calling it again here would
  be the exact kind of duplicated read this file's own comments repeatedly
  warn against (see `_rollup_pages`'s docstring on why both rollup sources
  share one loop).
- Do NOT add a `needs:`/`wait-for` on `Review Complete` anywhere as part of
  implementing this -- that would violate the acyclicity `review-status.sh`'s
  own header documents and `test_no_ci_job_references_review_complete`
  (referenced in the prior plan's T6) already guards. This stop-hook check
  reads the check-run; it must never make anything WAIT on it.
- `REVIEW_MAX_BLOCKS`'s default of `2` is a starting guess, not evidence --
  unlike `CI_MAX_BLOCKS` (justified by "one night of real runs" per
  `wl_ci.py:145-171`), there is no equivalent overnight sample for review-red
  yet. Flag to the operator that this number may want tuning after a few
  real occurrences, the same way `CI_MAX_BLOCKS` itself was tuned from
  observed behavior rather than picked in the abstract.
- This plan deliberately does NOT touch the `pr-finish` box's definition of
  "green" (`wl_checks.py:3900`, `_prf_green = cistate == "ok"`) -- a red
  `Review Complete` does not, and per this repo's own design should not,
  block the `pr-finish` green checkbox, since `Review Complete` is
  documented everywhere as "can never block Console CI". Making `review-red`
  ALSO gate `pr-finish`'s green box would be a second, larger design
  decision outside this plan's scope; note it as a possible future
  extension, not something to build here.
- Do not implement this by having the stop hook shell out to
  `.ci/scripts/quality/check-review-comments.sh` /
  `check-review-report-replies.sh` directly as subprocesses. It was
  considered (it would be the most driftproof possible option) and rejected
  for this plan: those scripts require `GH_TOKEN`/`GITHUB_TOKEN` explicitly
  (`check-review-comments.sh:104-107`) which a local interactive session
  does not export by default (only `gh auth login`'s stored credential
  does), `source ../lib/common.sh` pulls in retry/logging machinery not
  needed for a read-only stop-hook glance, and it is a new subprocess-shape
  `wl_ci.py` does not otherwise use anywhere (every existing call in this
  file is a direct `gh api`/`gh graphql`, never another repo script).
  Quoting the check-run's own already-computed `output.summary` gets the
  same zero-drift guarantee at a fraction of the operational complexity.

## Critical files for implementation

- `.claude/hooks/stop/wl_ci.py` (new `review_gate_row`, `review_gate_detail`,
  `review_red`, `REVIEW_MAX_BLOCKS`, `reviewmark_path`, extended `_selftest`)
- `.claude/hooks/stop/wl_checks.py` (new `elif cistate == "ok":` branch after
  the existing `ci_trouble` wiring at `~3806-3851`; `T_MISSION`/`T_INTEGRITY`
  tier registration at `~2354-2431`)
- `.claude/hooks/stop/worklist_messages.py` (new `V_REVIEW_RED`,
  `REVIEW_NOTE_DOWNGRADED`, `V_REVIEW_UNREADABLE`, placed beside `V_CI_RED`)
- `.claude/hooks/test-hooks.sh` (bump the `wl_ci.py --selftest` control-count
  floor at `~1905-1924`)
- `.ci/scripts/quality/check-review-comments.sh` and
  `.ci/scripts/quality/check-review-report-replies.sh` (read-only reference
  -- the source of truth the new check quotes rather than reimplements)
- `.ci/scripts/review/review-status.sh` and
  `.github/workflows/review-status.yml` (read-only reference -- verdict-
  posting shape and the existing `workflow_dispatch` re-evaluation path)

## Status

Implemented, wired, and tested as specified in commit `4a00daed`: F1-F5
landed in `wl_ci.py`/`wl_checks.py`/`worklist_messages.py`, the priority-
ladder registration in `test-always-tier.py`'s `ALWAYS_KEYS`, and the
message-catalogue arity map in `worklist-cases/08-poll-and-waiting.sh`
(both real gaps the suite itself caught while landing this, per that
commit's message). 15 fixture controls in `wl_ci.py --selftest` (was 6).
Full hook suite: 1773/1773. `ci:quick` clean. Reviewed by two automated
passes with zero new findings; the `pr-finish` green-box interaction this
plan's "Implementer notes" section flagged as a deliberate non-goal was
independently re-confirmed by the second review as intentional, not
missed.
