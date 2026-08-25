# PLAN: ci-trace must be able to read a branch that has no open PR
Status: executing
Owner: 854ac1c6
Updated: 2026-08-25

## The finding, measured

`/pr-merge` step 5 instructs, verbatim:

> Find the **Console CI** run for the merged commit … then trace it with
> `.ci/scripts/ci/ci-trace.py --wait` (run_in_background: true).

Run it after a merge and it returns immediately:

```
$ .ci/scripts/ci/ci-trace.py --ref main --wait --until-final
no-verdict: no open PR for ref 'main'
```

Measured 2026-08-25 against Console CI run `32903007256` (`b4b5797e` on `main`),
while that run was `in_progress`. The trace exited without watching anything.

**Why this matters more than one broken invocation.** `ci-trace.py` is not merely
*a* way to read CI — it is the **only sanctioned** one. `block-adhoc-sanctioned.sh`
refuses hand-rolled `gh` watch loops and `block-ci-polling.sh` refuses the
`sleep`+`gh run view` pattern, both by design, so that there is exactly one reader.
The post-merge step is therefore left with no sanctioned instrument at all: the
recipe names a tool that cannot answer, and the alternatives are blocked. A session
in that position either gives up on verifying the release path or reaches for a
guard-evading command. Both are worse than the gap itself.

This is the same class the `run.sh` vacuous green belonged to: an instrument that
reports something other than the truth about whether it ran.

## Root cause, with anchors verified against the tree

`ci-trace.py:105` calls `wl_ci.ci_rollup(root, ref)` and maps `state == "no-pr"`
to a `None` payload (`.ci/scripts/ci/ci-trace.py:106-109`). `ci_rollup`
(`.claude/hooks/stop/wl_ci.py:246`) issues exactly one query shape, built by
`ci_query` (`wl_ci.py:229-243`), whose root selector is:

```
repository(owner:…,name:…){pullRequests(headRefName:"<ref>",states:OPEN,first:1){…}}
```

`wl_ci.py:267-268` returns `("no-pr", ref)` when `nodes` is empty. A branch with no
open PR — which is precisely what `main` is after a merge — has no path through
this function. Nothing downstream is at fault.

## The fix

GitHub exposes the identical `statusCheckRollup` object under
`repository.ref(qualifiedName:"refs/heads/<ref>").target`. That is the load-bearing
claim of this plan and it is what makes the fix small: the **context node shape is
the same**, so `ci_classify` (`wl_ci.py:300`), `ci_steps`, and `ci-trace.py`'s
`_snapshot` verdict logic (`ci-trace.py:104-172`) all work unchanged. This is a
second *source* for the same payload, not a second implementation of the reader —
which is the invariant `check-ci-watch-recipe.sh` exists to protect.

1. **`wl_ci.py`** — add `ci_branch_query(owner, name, ref, cursor)`, same context
   selection set as `ci_query`, rooted at `ref(qualifiedName:)…target`. Add the
   paging loop as `_rollup_pages(...)` shared by both, so the `CI_MAX_PAGES` /
   `truncated` semantics cannot drift apart between the two sources.
2. **`wl_ci.py`** — `ci_rollup(root, ref, allow_branch=False)`. **Default `False`
   preserves today's behaviour byte for byte**, so the Stop hook's PR-currency
   logic, which treats `no-pr` as meaningful, is untouched. Only when
   `allow_branch=True` and the PR query returns no nodes does it fall through to
   the branch query. A branch that does not exist returns `("no-ref", ref)` — a
   *distinct* state from `no-pr`, because "you are on a branch with no PR" and
   "that branch does not exist" need opposite responses from a caller.
3. **`ci-trace.py`** — pass `allow_branch=True` when `--ref` was given explicitly.
   Not for the implicit current-branch default: on a feature branch, "no open PR
   yet" is a *useful* answer that should not be silently replaced by a branch read.
4. **`ci-trace.py`** — the payload gains `"source": "pr" | "branch"` and the human
   line prints `@ <sha> (branch main, no PR)` so a reader can never mistake which
   of the two it got. An instrument that reports two different things through one
   undifferentiated channel is the exact defect `2e2179aa` fixed in `run.sh`; do
   not reintroduce it one file over.

## Explicitly NOT in scope

- **Run-id tracing (`--run <id>`).** Tempting and wrong: run ids are per-attempt,
  and the whole reason this reader keys on a head is that a watchdog rerun
  *replaces* an attempt (`wl_ci.py:230-234`). Keying on a run id would reintroduce
  the stale-attempt bug that `ci-trace.py` was written to eliminate.
- Watching the Release workflow. Separate concern, separate step of the recipe.

## Tests — each must FIRE on a planted defect and stay silent when clean

Surface: **static gate** for the wiring, plus a **live probe** for the query,
following `.claude/skills/testing`'s routing (a behavioural claim about a GraphQL
response is not something a `check-*.sh` can assert).

1. **`test-ci-trace-branch.sh`** (new, under `.ci/scripts/test/gates/`):
   - *Clean:* `ci_rollup(root, "main", allow_branch=True)` returns `ok` with a
     non-empty `sha`, and `ci_rollup(root, "main")` — default — still returns
     `no-pr`. **Both directions in one test**, because the whole safety of this
     change rests on the default being unchanged.
   - *Planted defect A:* flip the default to `allow_branch=True`; the assertion
     that the default still yields `no-pr` must go red.
   - *Planted defect B:* point `ci_branch_query` at a nonexistent ref; the result
     must be `no-ref`, never `unreadable` and never a silent `ok` with an empty
     context list. A rollup with zero contexts and a rollup that could not be read
     look identical in the payload otherwise — that is the vacuity risk here.
2. **`check-ci-watch-recipe.sh` extension:** assertion that the `/pr-merge` skill's
   step-5 command and the tool's actual capability agree — i.e. every ref-taking
   invocation named in a skill resolves through a code path that exists. The gate
   today proves the skill hands out *the script*; it does not prove the script can
   answer *the question the skill asks it*. That gap is what let this ship.
3. **Live probe, run once by hand and recorded here:** `--ref main --wait` against
   a real in-flight `main` run must block until terminal and print a verdict.

## Blind spot this does not close

Neither test proves the GraphQL field selection stays valid if GitHub changes the
schema; a deprecation would surface as `unreadable`, which is the correct failure
mode (it says so) but is not caught before it happens.

## Second blind spot, found while driving the fix (2026-08-26)

`--until-final` exits as soon as the HEAD ROLLUP is terminal, which can be
several minutes before the RUN OBJECT reports `completed`. Observed on run
`32903007256`: the trace correctly printed RED (`CI Complete` had failed, so no
release could follow), but `gh run rerun --failed` then refused with *"cannot be
rerun; its workflow file may be broken"* and the per-job rerun with HTTP 403
*"The workflow run containing this job is already running"*.

This is **not** a defect in the verdict — the verdict was right and actionable.
It is two different questions sharing one instrument: the reader answers *"is
this head's CI settled"*, while `rerun` needs *"has the run finished"*. A session
that reads RED and immediately reaches for a rerun will hit the 403 and may
misread it as a broken workflow, which is what the gh message literally suggests.

Not fixed here, deliberately: teaching the head-reader about run objects would
reintroduce run-id coupling, which the NOT-IN-SCOPE section above rules out for
good reasons. The correct handling is on the caller's side — wait for the run
object before rerunning.
