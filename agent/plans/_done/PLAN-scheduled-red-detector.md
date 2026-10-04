# PLAN: scheduled-workflow reds and PR bot comments reach the agent session

Status: done -- every box ticked; PR #594 merged 2026-10-04 (main 01d3583e1)
Owner: d778be9d
First-Seen: 2026-10-04
Depends-On: no-dep -- builds only on shipped modules (wl_ci, wl_civerdict, ci-trace, sanctioned.py, wl_prreview)
Priority: P1 -- operator order 2026-10-04: Console CI nightly red 5 nights and Housekeeping 4 nights went unseen by every agent and held the stable promotion (promote-stable soak waiver)
Concurrency: exclusive -- operator ruling 2026-09-26: every plan runs alone while the token budget is limited
Owns: .claude/hooks/stop/wl_schedred.py, .claude/hooks/stop/wl_prsignals.py, .claude/hooks/stop/{wl_checks,worklist_messages,wl_prreview}.py, .claude/hooks/stop/test-always-tier.py, .ci/scripts/ci/ci-trace.py, .claude/hooks/lib/sanctioned.py, .claude/rediacc_hooks/guards/test-block_raw_ci_read.py, .claude/rediacc_hooks/tests/{test_wl_schedred,test_wl_message_catalogue,test_wl_prreview}.py, .ci/rediacc_ci/tests/{test_ci_trace_scheduled,test_ci_trace_pr_signals,test_prsignals_pins}.py, docs/agent-reference/ci-gates.md, .claude/skills/ci-watch/SKILL.md, scripts/data/doc-registry.md
Worklist: #5f84123a, #768e10e2

**Operator asks, 2026-10-04.**
- "is there any open plan that's about notifiying scheduled .yml github files failures to the system? Can stophook or ci:quick system somehow detect and block AI agent until it solves the issues?"
- "the CI watching system/script should be aware of such comments like in here https://github.com/rediacc/console/pull/594#issuecomment-5976442241"

**What was true when this was written.**
- A scheduled red reaches only a human. `.github/workflows/nightly-status.yml` with `.ci/scripts/ci/report-nightly-status.cjs` opens a rolling `nightly-red` issue, and housekeeping's budget-check comments on #586.
- The CI-read guards refuse every raw read of the runs list (`.claude/hooks/lib/sanctioned.py` rows `gh-run-list` and `gh-api-runs-list`). `ci-trace.py` lists only Console CI runs, so an agent could not see a scheduled run at all.
- PR #594's review-attempt comment (`<!-- claude-review-attempt: <sha> -->`, `class: error_max_turns`, attempt 1 of 3, plus a re-run command) never appeared in `ci-trace --wait` output.

**Rejected: a ci:quick gate.** `ci:quick` is the offline local lane. A GitHub read there adds network flakiness to every push and blocks pushes unrelated to the red, because a nightly red is never caused by the commit being pushed. A gate also cannot express "one session owns it, the others get an advisory". The Stop hook carries ownership, and it fails open.

## Part A: scheduled-red

**A1. Shared reader, `.claude/hooks/stop/wl_schedred.py` (new, modelled on `wl_civerdict`).**
- **Discovery.** `scheduled_workflows(root)` parses `.github/workflows/*.y*ml` for an uncommented `schedule:` with `cron:` entries. Today that is ci, housekeeping, promote-stable, ci-obs-mirror and ci-vm-bake. The list is never hardcoded, and a test pins it.
- **Reads.**
  - One call: `actions/runs?event=schedule&branch=main&status=completed&per_page=100`, through `wl_ci._gh_json`, which never raises.
  - A workflow missing from that page (the monthly vm-bake) gets one call: `actions/workflows/<file>/runs?event=schedule&status=completed&per_page=1`.
  - Each red run gets one `actions/runs/<id>/jobs?per_page=100` call.
- **Verdict.**
  - It comes from the newest completed `event == schedule` run per workflow, at its latest attempt.
  - Only `success` is green; `cancelled` is red.
  - A green `workflow_dispatch` run does not clear a red, because the promote-stable soak counts only scheduled runs. A green re-run attempt does clear it.
- **Cache.** `<worklist>.schedred`, shared by every session in the repo, written atomically.
  - TTL is `WORKLIST_SCHED_RED_TTL_S`, default 900.
  - Errors are cached for 300 s.
  - Jobs are cached per `(run, attempt)`.
  - With no origin slug the state is `unset` and zero calls are made, which keeps the Stop fixtures offline.
- **Tracking.** An open `[ ]`, `[>]` or `[?]` item tracks a red when it carries any of:
  - the whole token `sched:<stem>`;
  - the run id, bare or as `run:<id>`;
  - the workflow display name together with `nightly`, `scheduled` or `schedule`.

  A bare "Console CI" never counts.
- **Claim before any item exists.** The claim file is `<worklist>.schedred-claim-<stem>`, holding `{run, sid8, at}` and created with `O_EXCL`.
  - The claim is stale when its run id differs from the current red, or when the claimant's brief is older than `SESSION_BRIEF_STALE_MIN`.
  - A stale claim is replaced, then re-read.
- **Ownership.**
  1. If an item tracks the red, its owner owns it: the `open-items` blocker already holds that owner, and every other session gets a one-line advisory.
  2. If there is no item and this session holds the claim, the stop is blocked.
  3. If a peer holds the claim, this session gets an advisory, once per run id.
- **Ending a tracked red.**
  - A later green scheduled run triggers `N_SCHEDULED_GREEN`, which carries the exact tick command.
  - A tick's evidence must name a green scheduled run newer than the red. Operator ruling 2026-10-04 ("Require a green run") removed the fix-on-origin/main alternative: only the next scheduled run proves a fix. A tick naming neither while the newest run is still red fires `V_SCHEDULED_RED_TICK`.
  - A newer red run id starts the cycle again.

**A2. Stop wiring (`wl_checks.py`, after the CI block, before the PR-review block).**
- The whole check sits inside `try/except`. A hook bug becomes an outq "THIS IS A HOOK BUG" note.
- It is not gated on publish ref or sole session.
- Calls:
  - `vadd("scheduled-red", True, M.V_SCHEDULED_RED % ...)` for the claimant.
  - `vadd(... V_SCHEDULED_RED_TICK ...)` for an unevidenced tick.
  - `outq_add` for `scheduled-red-peer` (refresh 360 min) and for `scheduled-unreadable` (refresh 60 min).
- `scheduled-red` joins T_OWED (the party owed is the release pipeline) and `ALWAYS_KEYS` under I2.
- **Block text** names:
  - the workflow, its file, the run id and attempt, the conclusion and the age;
  - the failed jobs (at most 6, plus "+N more"), and what the red blocks (ci gives the stable promotion, the others give main hygiene);
  - `worklist.py --add <me8> 'sched:<stem> run:<id> -- <name> red on main since <date>; failed: <jobs>'`;
  - `ci-trace.py --run <id> --why` and `ci-trace.py --scheduled`.

**A3. `ci-trace.py --scheduled [--workflow X]`.** This uses the same `wl_schedred` module through the existing sys.path hop, and forces a refresh that also writes the shared cache.
- Output is one row per workflow: name, file, cron, newest run and attempt, conclusion, age and failed jobs. A red row adds `next: ci-trace.py --run <id> --why`.
- `--workflow` takes a stem, a file or a display name, and shows the newest 5 scheduled runs. An unknown name exits 2 and lists the known ones.
- Exit codes: 0 all green, 1 any red, 2 unreadable. `--json` gives structure.

**A4. Guard refusal text (`sanctioned.py`).**
- A new row, `gh-run-list-schedule` (`^run list\b.*\s--event[= ]schedule\b`), sits before `gh-run-list` and points to `ci-trace.py --scheduled`.
- The `gh-run-list` and `gh-api-runs-list` texts name `--scheduled`.
- `check_sanctioned_registry.py` must pass, so A3 lands first.

**A5. SessionStart line.** A block in `handle_session_start` reads the cache only, with zero network.
- A red prints `Scheduled red on main: <name> run <id> (<conclusion>, <age>) -- tracked by #<id> | untracked; ci-trace.py --scheduled`.
- A cache older than 6 h is marked stale.

**A6. Failure modes.**

| Failure | Behaviour |
|---|---|
| `gh` missing, rate limited or 5xx | `unreadable`, cached 5 min, advisory, no block |
| No origin | Silent, zero calls |
| Corrupt cache | Refetch |
| Claim race | `O_EXCL` then re-read |
| Claimant dead | Its brief goes stale after 90 min and the next session claims |

## Part B: PR SIGNALS

**B1. `.claude/hooks/stop/wl_prsignals.py` (new).** Hooks cannot import `rediacc_ci`, so these marker constants are copied by value, and a pin test proves they match:
- `ATTEMPT_PREFIX` and `MARKER_PREFIX` from `claude_review_gate.py`
- `review_table.MARKER_PREFIX`
- `pr_labels.LEDGER_PREFIX`
- the label-guide marker
- `wl_prreview.REPORT_HEAD`
- `INFRA_CLASSES`, `REVIEW_FREE_REATTEMPTS_PER_HEAD` and `REVIEW_MAX_ATTEMPTS_PER_HEAD` from `review_budget`
- `review_status.OUTAGE_CLASSES`

`classify(comments, head, pr, branch)` keeps bot comments that are for this head: the marker sha equals the head, the REPORT_HEAD sha7 matches, or the comment was created after the head's committer date. Each kind of signal gets an action:

| Signal | Action |
|---|---|
| Attempt, infra class, within the free re-attempts | Re-run: `gh workflow run claude-review.yml --ref <branch> -f pr_number=<n>`, with the branch filled in |
| Attempt, outage class | Excused |
| Attempt, budget spent | Push a change |
| Reviewed marker | `wl_prreview.py --status` |
| Summary with findings | `wl_prreview.py --draft` |
| Table or ledger | Informational |
| Unknown bot comment | First line, clipped |

`render()` prints a `PR SIGNALS (#<pr> @ <sha8>)` block.

**B2. ci-trace integration.**
- **The read.** `_pr_signals` makes one paginated `issues/<pr>/comments` read through `_fetcher`. It runs on every verdict print (red, green, no-ci) and on the one-shot path.
- **While waiting.** It reads every `CI_TRACE_SIGNALS_POLL_S` (120 s by default) and prints new signals at once, de-duplicated by comment id and `updated_at`.
- **Failure.** It never changes the exit code. An unreadable read prints `PR SIGNALS: unreadable`.
- **Green on a non-draft PR.** The NEXT block points to `wl_prreview.py --wait`.
- **JSON.** `--json` adds `pr_signals`.

**B3. `wl_prreview.py --wait`.** On `failed-run`, `exhausted`, `outage`, `stale` or a timeout, it classifies the PR's comments and prints the attempt class and its action. The generic text stays as the fallback.

## Tests (each with a mutation control)
**`test_wl_schedred.py`** runs against a recording `gh` shim:
- discovery, including a commented-out schedule;
- newest scheduled run and attempt;
- the red conclusions, with `cancelled` red;
- TTL and the error TTL, plus a corrupt cache;
- fail open;
- no origin, zero calls;
- matching, with "fix Console CI lint" as the negative;
- ownership across two sessions and a stale claimant;
- green clears;
- tick evidence;
- the Stop block, then a quiet second stop after `--add`;
- the SessionStart line, cache only.

**Updates to existing tests:**
- `test-always-tier.py`: the new invariant key.
- `test_wl_message_catalogue.py`: ARITY rows for every new message.
- `test-block_raw_ci_read.py`: a schedule list is refused and names `--scheduled`, while a `--workflow housekeeping.yml` list stays allowed.

**New tests:**
- `test_ci_trace_scheduled.py`: rows, exit codes, `--workflow` resolution, the `--json` shape and the cache write.
- `test_prsignals_pins.py`: the copied constants equal their sources. Attempt round trips: 1 `error_max_turns` gives a re-run with the branch filled in; 3 gives "push a change"; an outage class is excused; another sha is ignored.
- `test_ci_trace_pr_signals.py`: the block on each verdict; an unreadable read keeps the exit code; the wait loop prints once.
- `test_wl_prreview.py`: the attempt class is shown on `failed-run`, and the fallback when there is no comment.

## Docs
- `docs/agent-reference/ci-gates.md` gains a "Scheduled workflows" paragraph and a PR SIGNALS sentence.
- `.claude/skills/ci-watch/SKILL.md` gains a `--scheduled` line and a PR SIGNALS paragraph.
- `scripts/data/doc-registry.md` is regenerated by `npx tsx scripts/gen/gen-docs.ts --write`.

## Tasks
- [x] T1 `wl_prsignals.py`: copied constants, `classify`, `render`, plus `test_prsignals_pins.py`.
    (ticked) 2026-10-04T05:36:17Z by d778be9d: commit:680ddc708 wl_prsignals and its pin test built in 680ddc708
- [x] T2 `wl_schedred.py`: discovery, the reads with fallback, jobs, the shared cache with TTL and error TTL, the no-origin gate.
    (ticked) 2026-10-04T05:35:44Z by d778be9d: commit:f6e8ea29d
- [x] T3 `wl_schedred`: `tracks()`, the claim file, ownership, the tick-evidence rule.
    (ticked) 2026-10-04T05:35:46Z by d778be9d: commit:f6e8ea29d
- [x] T4 Message constants in `worklist_messages.py`, plus ARITY rows.
    (ticked) 2026-10-04T05:35:48Z by d778be9d: commit:f6e8ea29d
- [x] T5 `ci-trace.py --scheduled [--workflow]`, plus `test_ci_trace_scheduled.py`.
    (ticked) 2026-10-04T05:35:50Z by d778be9d: commit:680ddc708
- [x] T6 `sanctioned.py` rows and texts, plus guard cases; `check_sanctioned_registry.py` passes.
    (ticked) 2026-10-04T05:35:51Z by d778be9d: commit:3ffbf2c9d
- [x] T7 Stop wiring in `wl_checks.py`, T_OWED and `ALWAYS_KEYS`.
    (ticked) 2026-10-04T05:35:53Z by d778be9d: commit:f6e8ea29d
- [x] T8 `test_wl_schedred.py` cases, each with its control.
    (ticked) 2026-10-04T05:35:55Z by d778be9d: commit:f6e8ea29d
- [x] T9 SessionStart block, plus its case.
    (ticked) 2026-10-04T05:35:56Z by d778be9d: commit:f6e8ea29d
- [x] T10 ci-trace `_pr_signals` on every verdict, the throttled in-wait read, the green NEXT, plus `test_ci_trace_pr_signals.py`.
    (ticked) 2026-10-04T05:36:18Z by d778be9d: commit:680ddc708 PR SIGNALS in ci-trace built in 680ddc708
- [x] T11 `wl_prreview --wait` attempt-class surfacing, plus tests.
    (ticked) 2026-10-04T05:36:19Z by d778be9d: commit:c9952740b attempt class in wl_prreview --wait (680ddc708), single Next line c9952740b
- [x] T12 Docs; regenerate doc-registry.md.
    (ticked) 2026-10-04T05:36:20Z by d778be9d: commit:761443a4a docs and regenerated doc-registry in 761443a4a, doc-region-parity rc=0
- [x] T13 Full hook and CI pytest suites and `ci:quick`.
    (ticked) 2026-10-04T06:47:05Z by d778be9d: full pytest 20988 passed + docs_gen 6 passed after commit:860478325; ci:quick 304/306, the 2 remaining fixed by 860478325 and by this tick
- [x] T14 Live check, read-only: `ci-trace.py --scheduled` against main names the current reds, and one Stop blocks with the `--add` text.
    (ticked) 2026-10-04T05:36:22Z by d778be9d: commit:680ddc708 live ci-trace.py --scheduled: 5 workflows, RED Console CI 37101760904 and Housekeeping 37111522524
- [x] T15 Track the current reds with `sched:ci` and `sched:housekeeping` items.
    (ticked) 2026-10-04T05:36:23Z by d778be9d: commit:f6e8ea29d reds tracked as #069cb1d2 (sched:ci run:37101760904) and #5f43e8c8 (sched:housekeeping run:37111522524)
