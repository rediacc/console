Status: ready
First-Seen: 2026-11-23
Owner: ace763dd
Updated: 2026-11-23
Owns: .claude/hooks/stop/wl_stack.py, .ci/rediacc_ci/dev/landing_promote.py, .ci/rediacc_ci/tests/test_dev_landing_promote.py, .claude/hooks/stop/test-landing-stack.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/wl_checks.py, .claude/rediacc_hooks/guards/block_rebase_over_foreign_dirt.py, .claude/rediacc_hooks/guards/test-block_rebase_over_foreign_dirt.py, .claude/rediacc_hooks/tests/test_rebase_standdown.py, .ci/policy/record-paths.json, .ci/rediacc_ci/tests/gates/test_gate_record_paths.py, .claude/commands/wisdom.md, .claude/commands/branch-rebase.md, .claude/rediacc_hooks/guards/block_unverified_push.py, .claude/rediacc_hooks/guards/test-block_unverified_push.py, .claude/hooks/stop/worklist.py, .claude/rediacc_hooks/tests/test_wl_tick_commit_ref.py, .claude/hooks/stop/wl_worktrees.py, .claude/hooks/stop/test-wl_worktrees.py, agent/plans/PLAN-stop-hook-retro-20261123.md
Concurrency: parallel -- R1/R2, R3/R4, R5 and R6/R7 touch disjoint files
Priority: P1 -- operator 2026-11-23: full speed, ci:quick is slow
Depends-On: no-dep -- no box waits on another plan

# PLAN: Stop-hook retro, 2026-11-23 (band late, lead session ace763dd, tracking #3b9c59de)

**Scope.** This retro covers lead transcript bytes 13815810 to 46126102 of `ace763dd-04fa-45b1-aa44-0da57b775268.jsonl`, from 2026-11-22T10:21Z to 2026-11-23T02:56Z. The blocklog `/tmp/claude-worklist/home_developer_console.blocklog-ace763dd.jsonl` holds 109 blocked stops in this window (its last 109 rows):
- landing-stack: 70
- judge: 14 (14 continue, 0 sweep demands, 0 proof demands)
- worktree-unlanded: 7
- wake-timer: 4
- bg-report: 4
- roster-dead: 3
- commit-review: 2
- ladder-gone: 2
- giveup-claim:does-not-reproduce: 1
- loop-next: 1
- unread-reports: 1

Other ledgers in the window:
- 7 hint proposals
- 4 admissions
- 10 refused `--tick` calls: 6 `no-commit-ref`, 4 `no-evidence`

Line numbers refer to the working tree at 1121-1, after the rebase. Rebasing moved two commits:
- The landing-stack fix was rewritten by the rebase and is now b430509a52 (its pre-rebase sha is no longer an ancestor of HEAD or origin/main, so it is not cited).
- The rebase stand-down fix was two commits before the rebase and is now d9c3ad783c and 6af8c18eb3 (the pre-rebase shas are not ancestors of HEAD and are not cited).

`git merge-base --is-ancestor d9c3ad783c origin/main` fails, so the stand-down is **not on origin/main**.

**Fixed this window and not re-ranked, except for what the fix left open:**
- **landing-stack at effort quiet.** b430509a52 moves the key off the FLOOR. It is now `{"block": "low", "advise": "quiet"}` at `.claude/config/effort.json:54-57`. Quiet now advises. low, smart and high still block. Friction 1 covers what that leaves.
- **Hooks writing tracked records mid-rebase.** d9c3ad783c and 6af8c18eb3 add `_operation_standdown` at `.claude/hooks/stop/worklist.py:313-358`, plus the reviewer, band-notice and post-compact guards. Friction 2 covers what that leaves.
- **Promote refusing on hook ledgers.** `_record_globs` and the tracked-only `_dirty` at `.ci/rediacc_ci/dev/landing_promote.py:109-145` (operator ruling ASKED:2026-11-22T18:55Z) fixed this. Not re-ranked.

**Legitimate or already covered, not ranked:**
- **judge continue at 13:11:17Z and 15:19:12Z.** The message left out tracked ids (#95ffeb93, #8da3a559), so this is covered by R20261117.1, which is still open. The other 12 continue verdicts named real local work, for example 14:01:58Z (17 dev reds) and 16:16:06Z (one doc sentence, `docs/agent-reference/ci-gates.md:567`). They were correct.
- **roster-dead (17:51:36Z, 19:43:16Z, 20:24:59Z).** Covered by R20261122.1 (open).
- **wake-timer (16:57:02Z, 21:53:27Z, 02:00:30Z, and one more row).** Covered by R20261117.5 (open).
- **unread-reports at 02:31:56Z (45861516).** One real report, marked read 23 s later (45888144). Correct.
- **worktree-unlanded, 6 of 7 rows (15:55:35Z to 16:07:37Z).** Two finished trees held real dirty paths while the plan-close agent ran (lead text 28872272). The block was correct.
- **Ledger-only rows: bg-report ×4, commit-review ×2, ladder-gone ×2, loop-next ×1, giveup-claim ×1.** Counted from the ledger. Their transcript text was not read, so nothing is claimed about them.
- **Hint proposals 11:27:43Z (review finding waiting on a main-CI artifact), 14:09:01Z (plan-renders) and 15:18:40Z (pr-merge.md workflow_dispatch).** These are not stop blocks in this window. They are not measured here.

## Ranking by cost to the session

| Rank | Point | Count in this window | Turns lost | Already fixed by? |
|---|---|---|---|---|
| 1 | landing-stack blocks every stop at low and above while `--promote` itself refuses (code-complete, a peer's dirty tracked paths, a live run in the main checkout) | 70 blocks in 3 bursts: 15 (18:01:35Z to 18:10:56Z), 21 (18:38:33Z to 18:47:16Z), 34 (19:04:57Z to 19:15:23Z) | 70 stop turns. 28m30s of wall time across the bursts. One failed self-fix (36179620 to 36209256). Operator intervention at 19:27:07Z (39234631). | Partly: b430509a52 frees **quiet only**. Burst 3 would still block at low today. |
| 2 | Hooks run from the tree being rebased, so a hook fix cannot protect a halted rebase onto a base that lacks it | 1 rebase. Halted at step 26 of 273 in the main checkout (43613119), abandoned at 00:04:12Z (43926603). | 43m49s from the console rebase start (43416154, 23:59:03Z) to the branch move (44773460, 00:42:52Z). Side damage: the main checkout's `private/account` gitdir broke (44548208, 00:41:22Z). | Partly: d9c3ad783c and 6af8c18eb3. They are on 1121-1 but not on origin/main. |
| 3 | A STATE.md commit voids the push receipt during a ci:quick run, and the push refusal does not name the path that voided it | 2 refusals with "judged a different tree": 43185757 (23:30:36Z) and 45966754 (02:56:04Z). A third at 22655769 (13:45:11Z, landing tree) was a record-only advance that cost 71 s. | One 54m50s ci:quick run wasted (45667671 01:59:42Z to 45903417 02:54:32Z), and its re-run (45979988). One 27m02s whole-lane advance (43203047 to 43270162). One peer commit held back (45802940). | no |
| 4 | `--tick commit:<sha>` accepts only shas reachable from HEAD | 6 `no-commit-ref` rows: #876420de 11:41:07Z and 11:41:34Z, #9a4823c8 16:59:10Z and 16:59:16Z, #b07162cf 00:46:01Z and 00:46:12Z | 6 calls and 3 re-cites (for example 45046206) | no (hint 2026-11-22T11:41:50Z) |
| 5 | worktree-unlanded judges a landing-cut lease against the development HEAD | 1 block (13:06:43Z, 21490879). It listed 36 landing commits as unlanded. | 1 turn and 3 calls (21515785 to 21553188) | no (hint 2026-11-22T13:07:02Z) |

## 1. landing-stack blocks while promotion is refused for reasons the session cannot act on

**What happened.** After #605's edge release went green (35843749, 18:01:20Z), every stop got `LANDING MERGED (blocks at every effort level) ... ./run.sh worktree landing --promote` (first block 36065447, 18:03:46Z). There were three bursts. The lead's text names the cause of each:
- **Burst A: 15 blocks, 18:01:35Z to 18:10:56Z.** Promote refused on a dirty main checkout. Peer console-1a was editing `PLAN-ciquick-cpu.md`, `INDEX.md`, `plan-boxes.json`, `QUEUE.md` and `epics.jsonl` (36061944, 36159976). The lead filed hint c6e3c13e (2026-11-22T18:03:55Z). At 36179620 it started to fix `wl_stack.py`, as the block text invites (its "Fix THIS" line names the session as the one that fixes it). It gave up at 36209256 because "deciding which dirty paths belong to which session ... is more than a small fix". The burst ended when the peer committed bad4ebe5cb (36507958, 18:11:06Z).
- **Burst B: 21 blocks, 18:38:33Z to 18:47:16Z.** The bench/VM runner's vm:check was running in the main checkout. The lead held back because "rebasing the checkout under a running vm:check is what broke an earlier run" (37129557). 19 of the 21 replies are one line of "still waiting" (37151204 to 37541696). The burst ended with vm:check rc 0 (37571963).
- **Burst C: 34 blocks, 19:04:57Z to 19:15:23Z.** Promote refused at step 5: `PLAN-two-track-merge-dev` had open `[writer]` boxes R3 and R4 (38384007 at 19:02:22Z, 38477880). That refusal is deterministic: no amount of stopping changes it before the writer reports. All 34 replies are "still waiting on the R3 and R4 writer" (38503352 to 39191929).
- **The operator stepped in at 19:27:07Z:** "effort: quiet but the stop hook doesn't exit with code 0" (39234631). The lead fixed it in b430509a52 (rewritten by the rebase) at 19:41Z.

**Root cause.**
- `wl_stack.stack_block` (`.claude/hooks/stop/wl_stack.py:225-233`) returns the block text whenever `st.state == MERGED` and `released`. It never asks whether promote would actually proceed.
- `landing_promote.promote` refuses at step 1 on any tracked non-record dirt in either checkout (`_dirty`, `.ci/rediacc_ci/dev/landing_promote.py:135-145`). It also refuses at step 5 on any open `[writer]` box (`_code_complete`, `:286-317`, called at `:447`).
- The repo's own notify text says promote waits for code-complete: "once every [writer] box of the plans on its branch is ticked, promote" (`.claude/hooks/stop/wl_stack.py:286-294`, `cd-done`). The block ignores that rule, which contradicts it.
- The block is raised by the `vadd("landing-stack", ...)` call in the `landing-stack` segment of `.claude/hooks/stop/wl_checks.py` (written as `:5455-5457` when this plan was drafted; `:6655` in the current tree).
- b430509a52 changed only the level table, so at low, smart and high all three bursts would recur. Burst C would recur byte for byte.

**Fix.**
- **(a) Code-complete.** When the development commits name a plan with an open `[writer]` box, `stack_block` returns "" and the merged state rides the advisory queue. The advisory reads "LANDING MERGED, PROMOTION WAITS ON CODE-COMPLETE: `<plan>` has N open [writer] box(es), first: ...". One helper computes the answer for both sides: it moves out of `landing_promote._code_complete` into a hook module (`wl_stack.open_writer_boxes(root, shas)`), and `_code_complete` raises on its non-empty answer. That way the hook and the verb cannot disagree.
- **(b) Dirty tree or live run.** When promote's dirty preflight would refuse and every dirty path is outside this session's edited-file union (the `uc_*` keys `commit_remind.py` keeps in the state doc), the block downgrades to an advisory naming those paths. The same happens while a live background task of this session runs with cwd in the main checkout. This mirrors the loop-next rule "a background task of this session downgrades it" at `.claude/hooks/stop/wl_checks.py:5459-5461`. When a dirty path is this session's own, it still blocks, and the text now lists those paths.

## 2. A rebase that halts runs the hooks of its onto base, so the stand-down cannot protect the rebase that carries it

**What happened.**
- The console rebase of 1121-1 onto main started in the main checkout at 23:59:03Z (43416154).
- The tree went dirty before and during it from hook writes: the per-commit reviewer ledger (43471657) and "the hook ledgers were rewritten mid-rebase too, and the per-commit reviewer is firing on every replayed commit" (43613119, 00:01:08Z).
- `git rebase --continue` refused with git's merge-conflict message while `ls-files -u` was empty (43663486). The repo's continue helper failed the same way (43692401).
- The lead abandoned it at 00:04:12Z (43926603) and briefed writer ab527440ea775f121, which reported at 00:31:54Z (44050751).
- The lead then ran the whole rebase in the landing tree, "since the hooks read the main checkout" (tick refusal #b07162cf, 00:46:12Z): from 44332964 (00:35:13Z) to the branch move at 44773460 (00:42:52Z).
- That route broke the main checkout's `private/account` gitdir pointer (44548208). The lead recorded hint 2026-11-23T00:41:52Z: never `git submodule update --init` in the landing tree.

**Root cause.**
- Every hook is read from `$CLAUDE_PROJECT_DIR/.claude/hooks/...` in `.claude/settings.json`, which is the main checkout's working tree.
- Mid-rebase that tree is `<onto>` plus the steps replayed so far. A hook fix carried by the branch is therefore absent until its own step replays.
- d9c3ad783c makes the Stop hook, reviewer, band notice and post-compact stand down (`.claude/hooks/stop/worklist.py:313-358`), but the commit is not on origin/main. Until 1121-1 lands, any halted rebase of 1121-1 onto origin/main in the main checkout runs the old hooks again.
- `.claude/commands/branch-rebase.md:142-151` and `block_rebase_over_foreign_dirt.py` say nothing about this.
- `landing --promote` step 6 is not exposed: it autostashes and aborts on conflict (`.ci/rediacc_ci/dev/landing_promote.py:6`), so it never halts between tool calls.
- The same trap applies to every future hook fix in general. Whenever `<onto>` lacks a stand-down the branch carries, the rebase is unprotected.

**Fix.** Extend `block_rebase_over_foreign_dirt.py` with one self-expiring refusal for a `git rebase` that would start in the main checkout. The check reads `git show <onto>:.claude/hooks/stop/wl_git.py` and looks for `def operation_in_progress`. If the onto base lacks it, the guard refuses and names the route that worked:
- the landing tree when it is idle on main, or a lease tree;
- then `git branch -f <dev> <rebased tip>` from the main checkout;
- and the warning not to run `git submodule update --init` there.

The refusal goes away by itself once origin/main carries the stand-down. Add one line to branch-rebase.md step 3 that names the same rule.

## 3. A STATE.md commit voids the receipt mid-run, and the refusal does not say which path did it

**What happened.**
- **Incident 1.** At 01:59:42Z (45667671) the lead started ci:quick on the tip for the backup push. At 02:00:31Z the stop was blocked on wake-timer with `wisdom-due: CONTEXT AT 96%` queued (45707808). `/wisdom` step 6 says "Commit STATE.md by path" (`.claude/commands/wisdom.md:43`), so the lead committed ea95248e0f at 02:00:54Z, 72 s into the run. The run finished at 02:54:32Z (45903417). The push was refused at 02:56:04Z with "the gate run judged a different tree (02cb102e…), not this one (069fb2c2…)" (45966754). The lead worked out that "the STATE.md commit voided the receipt: STATE.md isn't a record path" (45978110) and started the run again (45979988). Separately, peer console-1a held a commit to avoid voiding the same receipt (45802940, 02:14:13Z).
- **Incident 2.** At 23:30:36Z (43185757) the same generic refusal followed carried-reds 685ba31ced and a review-record commit. The lead expected a short advance pass ("the record commits since that run need ci:quick's quick advance pass", 43201205). Instead it ran the whole lane for 27m02s (43270162: "ran the whole lane, because the receipt was red"). An added carried-reds entry voids by design (record-paths.json `$comment`), but nothing in the refusal said so.

**Root cause.**
- `.ci/policy/record-paths.json` has no glob for `agent/<sid>/STATE.md`. Its `$comment` says "agent/STATE.md is not a record", with no reason given.
- The hook's own design assumes commits during a ci:quick run are harmless: "A ci:quick run never holds: it judges a pinned clone and its receipt advances to the tree after a record-only commit" (`.claude/hooks/stop/wl_checks.py:3115`). The one commit the Stop hook itself orders near the end of a context (wisdom-due) is not record-only.
- When the receipt carries no `advances`, `advance_chain` returns `(None, None)` (`.claude/rediacc_hooks/guards/block_unverified_push.py:947-954`). `_receipt_front` then prints only the two tree hashes (`:2207-2213`), with no voiding path and no hint whether ci:quick will advance or run whole.

**Fix.**
- **(a)** Add a record glob `agent/*/STATE.md`, with its readers derived by `check:ci-record-paths` (`npm run check:ci-record-paths -- --update`). The wisdom commit then advances the receipt. `agent/STATE.md` stays out as the comment says.
- **(b)** When the refusal has no advance chain, it names the paths in `git diff --name-only <receipt tree> <tree>` that fall outside the record set, or the carried-reds widening. It ends with "ci:quick will run the whole lane" or "ci:quick will advance (record-only)". The same predicate `planAdvance` uses decides which.

## 4. `--tick commit:` accepts only shas reachable from HEAD

**What happened.** There are 6 `no-commit-ref` refusals:
- **#876420de (11:41:07Z, 11:41:34Z):** landing-tree commits 7886ef9b8, f4093e83a and 1b5c7d83a, not yet on 1121-1.
- **#9a4823c8 (16:59:10Z, 16:59:16Z):** the operator's hotfix aa829a19d on main.
- **#b07162cf (00:46:01Z, 00:46:12Z):** d9c3ad783c (the pre-rebase sha is no longer an ancestor), rewritten by the rebase. The lead had to look up the new sha (45046206).

**Root cause.** `commit_ref_problem` requires `merge-base --is-ancestor <sha> HEAD` (`.claude/hooks/stop/wl_cli.py:1455-1458`). It ignores origin/main, the landing branch, and the patch-equivalent copy that `wl_worktrees` already treats as landed via `git cherry` (`.claude/hooks/stop/wl_worktrees.py:9`).

**Fix.** A sha passes when one of these holds:
- it is an ancestor of HEAD, `refs/remotes/origin/main`, or the landing record's branch;
- it has a patch-equivalent on HEAD (`git cherry`);
- a `(cherry picked from commit <sha>)` line on HEAD names it.

A fabricated sha still fails the `rev-parse --verify` step.

## 5. worktree-unlanded judges a landing-cut lease against the development HEAD

**What happened.** Lease ace763dd-1 was cut with `--tree landing`. At 13:06:43Z (21490879) the block listed 36 commits as unlanded. Its one new commit was already in the landing tree as ba24ec5e7, and `gc` agreed the tree was safe to delete (21535068).

**Root cause.**
- The survey's live tip is the HEAD of the tree it stands in (`.claude/hooks/stop/wl_worktrees.py:117`, `_tip_row`).
- The lease record's `cut_from` (`.ci/rediacc_ci/dev/worktree_lease.py:123`) is read only by `wl_rebase.base_branch` (`.claude/hooks/stop/wl_rebase.py:53-56`), and only after a merge.

**Fix.** When a lease record carries `cut_from` equal to the landing record's branch, `wl_worktrees` judges that lease's commits against `refs/heads/<landing branch>`. Every other lease keeps today's tip.

## Decisions

- **D1 (friction 1a).**
  - DEFAULT: an open `[writer]` box on a plan the development commits name turns the landing-stack block into an advisory naming the plan and its first open box.
  - WHY: promote refuses in that state by design (`.ci/rediacc_ci/dev/landing_promote.py:286-317`), and the cd-done text already says to wait. 34 of the 70 blocks were this case.
  - HOW: a shared `wl_stack.open_writer_boxes`, called by both `stack_block` and `_code_complete`.
- **D2 (friction 1b).**
  - DEFAULT: the block downgrades only when every dirty tracked non-record path is outside this session's edited-file union, or when a live background task of this session has its cwd in the main checkout. Otherwise it keeps blocking and lists the paths.
  - WHY: the lead's own reason for not fixing this at 36209256 was ownership. The `uc_*` union is the existing ownership signal, and a dirty path this session owns is a real action.
  - HOW: `stack_block` takes `own_paths` and `live_main_bg` from `.claude/hooks/stop/wl_checks.py:5455`, and runs `landing_promote._dirty` through a non-raising wrapper.
- **D3 (friction 2).**
  - DEFAULT: a pre-bash refusal that expires on its own, based on whether `<onto>` holds `def operation_in_progress`. There is no hook-pinning mechanism.
  - WHY: pinning hook code outside the working tree is a larger design. The trap closes for good once main carries the stand-down, and it reopens only when a future stand-down is added, which the probe can name.
  - HOW: a probe in `block_rebase_over_foreign_dirt.py`, plus one sentence in branch-rebase.md step 3.
- **D4 (friction 3a).**
  - DEFAULT: `agent/*/STATE.md` becomes a record.
  - WHY: `.claude/hooks/stop/wl_checks.py:3115` already assumes commits during a ci:quick run are record-only, and the hook itself orders a STATE.md commit near the end of a context. The other option, telling /wisdom not to commit, leaves a hand-over that a crash would lose.
  - HOW: a record-paths.json row, with readers derived by `check:ci-record-paths`. If the derivation finds a reader the record set cannot carry (a commit-range verdict, as with epics.jsonl), fall back to wisdom.md step 6: write through `--state`, and commit after the push while a ci:quick run of this session is live.
- **D5 (friction 3b).**
  - DEFAULT: name the paths that voided the receipt and say which kind of run ci:quick will do.
  - WHY: the lead guessed wrong once (43201205), and that guess cost 27 min.
  - HOW: `_receipt_front` on the `(None, None)` branch.
- **D6 (friction 4).**
  - DEFAULT: accept origin/main, the landing branch, and patch-equivalents.
  - WHY: all 6 refusals named real commits.
  - HOW: `commit_ref_problem`.
- **D7 (friction 5).**
  - DEFAULT: judge a lease by its `cut_from` when that is the landing branch.
  - WHY: one wrong block, which the lead disproved with `gc` in 13 s.
  - HOW: `wl_worktrees` tip selection per lease.

## Sequencing

1. R20261123.1 and .2 go first. They touch `wl_stack.py`, `landing_promote.py` and `.claude/hooks/stop/wl_checks.py:5455`, and remove the most turns.
2. R20261123.3 is independent and should land before the next rebase of 1121-1 onto origin/main.
3. R20261123.4 and .5 go together: the guard text in .5 names the record set that .4 changes.
4. R20261123.6 and .7 are independent of everything else.
5. R20261123.8 runs after .1 to .5 land.

## Tasks

- [x] **R20261123.1** Move the open-`[writer]`-box reading out of `landing_promote._code_complete` (`.ci/rediacc_ci/dev/landing_promote.py:286-317`) into `wl_stack.open_writer_boxes(root, shas)`, and have `_code_complete` raise on its answer. `stack_block` (`.claude/hooks/stop/wl_stack.py:225-233`) returns "" when the answer is non-empty. `.claude/hooks/stop/wl_checks.py:5455-5461` then queues a `landing-stack` advisory: "PROMOTION WAITS ON CODE-COMPLETE: `<plan>` has N open [writer] box(es), first: ...". Fixture: merged landing branch, green release, one development commit with `Plan-Box:` naming a plan with an open `[writer]` box, so there is no block and the advisory names the box. Inverse: all writer boxes ticked, so the effort-low block stands. Mutant: drop the call, and the fixture goes red. Test: .claude/hooks/stop/test-landing-stack.py.
    (ticked) 2026-11-23T04:51:33Z by ace763dd: commit:e943d92e8a fileline:.claude/hooks/stop/wl_stack.py:1 -- open-writer-box reader shared by stack_block and _code_complete; test-landing-stack.py rc 0 with 12 mutants red; review fix f2893b51ee
- [x] **R20261123.2** `stack_block` takes `own_paths` (the session's `uc_*` edited-file union) and `live_main_bg` (a live background task of this session with cwd in the main checkout). It downgrades to an advisory naming the dirty paths when promote's tracked non-record dirt (`landing_promote._dirty` through a non-raising wrapper) is disjoint from `own_paths`, or when `live_main_bg` holds. Otherwise the block text lists the dirty paths that are this session's. Fixtures: a peer-dirty `agent/plans/PLAN-stop-hook-retro-20261123.md` with an empty union gives an advisory; the same path in the union gives a block naming it; a live main-checkout background task with a clean tree gives an advisory. Test: .claude/hooks/stop/test-landing-stack.py.
    (ticked) 2026-11-23T04:51:43Z by ace763dd: commit:e943d92e8a fileline:.claude/hooks/stop/test-landing-stack.py:1 -- peer dirt and live main-checkout task downgrade to an advisory, own dirt keeps the block; test-landing-stack.py rc 0
- [x] **R20261123.3** In `.claude/rediacc_hooks/guards/block_rebase_over_foreign_dirt.py`, refuse a `git rebase <onto>` that would start in the main checkout when `git show <onto>:.claude/hooks/stop/wl_git.py` lacks `def operation_in_progress`. The refusal names the landing-tree or lease-tree route, `git branch -f`, and the ban on `git submodule update --init` there (hint 2026-11-23T00:41:52Z). Add one sentence to `.claude/commands/branch-rebase.md` step 3. Fixtures: an onto commit without the function gives a refusal; an onto commit with it allows; `--continue` and `--abort` are never refused. Test: .claude/rediacc_hooks/tests/test_rebase_standdown.py.
    (ticked) 2026-11-23T04:51:49Z by ace763dd: commit:055f887a18 fileline:.claude/rediacc_hooks/guards/block_rebase_over_foreign_dirt.py:1 -- main-checkout rebase onto a base without operation_in_progress refused; guard suite rc 0, test_rebase_standdown 59 passed (pre-fix 7 red); branch-rebase step 3 sentence f468b0a0a7
- [x] **R20261123.4** Add the record glob `agent/*/STATE.md` to `.ci/policy/record-paths.json`, with its readers derived by `npm run check:ci-record-paths -- --update`. Keep `agent/STATE.md` excluded, and record why in the `$comment`. If the derivation flags a commit-range reader, take the D4 fallback instead: in wisdom.md step 6, commit after the push while a ci:quick run of this session is live. Fixture: a receipt at T0, then a commit touching only `agent/ace763dd/STATE.md`. ci:quick appends an advance step and `block_unverified_push` admits T1. Test: .ci/rediacc_ci/tests/gates/test_gate_record_paths.py.
    (ticked) 2026-11-23T04:51:56Z by ace763dd: commit:66d9771ff3 fileline:.ci/policy/record-paths.json:1 -- agent/*/STATE.md is a record with 73 readers; check:ci-record-paths rc 0, test_gate_record_paths 14 passed (pre-fix red)
- [x] **R20261123.5** On the no-advances branch of `_receipt_front` (`.claude/rediacc_hooks/guards/block_unverified_push.py:2207-2213`, with `advance_chain` returning `(None, None)` at `:1424-1425`), append the paths of `git diff --name-only <receipt tree> <tree>` outside the record set, or "carried-reds.json widened". End with "ci:quick will run the whole lane" or "ci:quick will advance (record-only)". Fixtures: a STATE.md-only diff before .4 lands names the path and says whole lane; a review-record-only diff says advance; an added carried entry names the widening. The golden for a receipt with advances stays byte for byte the same. Test: .claude/rediacc_hooks/guards/test-block_unverified_push.py.
  (corrected 2026-11-23, CR5 3f695f2703 moved the guard test tables out) .claude/rediacc_hooks/guards/block_unverified_push.py:2207-2213 now at .claude/rediacc_hooks/guards/block_unverified_push.py:1780-1808
    (ticked) 2026-11-23T04:52:00Z by ace763dd: commit:6b78fcc55e fileline:.claude/rediacc_hooks/guards/block_unverified_push.py:1 -- no-advance refusal names voiding paths and whole-lane vs advance; 7 new cases, suite 357 rc 0, 19 goldens re-recorded (1d367af7f1 24d540ed98)
- [x] **R20261123.6** `commit_ref_problem` (`.claude/hooks/stop/worklist.py:1683`) accepts a `commit:<sha>` in any of these cases: it is an ancestor of HEAD, `refs/remotes/origin/main` or the landing record's branch; it has a patch-equivalent on HEAD (`git cherry`); or a `(cherry picked from commit <sha>)` trailer on HEAD names it. Fixtures, one per refused row: a landing-only sha (item #876420de), a main-only hotfix (item #9a4823c8) and a pre-rebase sha (item #b07162cf) each pass. A random 40-hex sha still fails. Test: .claude/rediacc_hooks/tests/test_wl_tick_commit_ref.py.
    (corrected 2026-11-24, ace763dd) `.claude/hooks/stop/worklist.py:1683` now at `.claude/hooks/stop/wl_cli.py:1386`
    (ticked) 2026-11-23T04:52:05Z by ace763dd: commit:26dc7587c1 fileline:.claude/rediacc_hooks/tests/test_wl_tick_commit_ref.py:1 -- commit: accepted when on origin/main, the landing branch, a patch-equivalent or a cherry-picked line; random sha refused; pytest 30 passed
- [x] **R20261123.7** In `wl_worktrees`, judge a lease whose record `cut_from` equals the landing record's branch against `refs/heads/<landing branch>`, not the survey tree's HEAD (`.claude/hooks/stop/wl_worktrees.py:117-142`). Fixture: a lease cut from landing with one commit picked into landing gives no `worktree-unlanded`. Inverse: an unpicked commit is still listed. Test: .claude/hooks/stop/test-wl_worktrees.py.
    (ticked) 2026-11-23T04:52:08Z by ace763dd: commit:0fbab17947 fileline:.claude/hooks/stop/wl_worktrees.py:1 -- a landing-cut lease is judged against the landing branch; test-wl_worktrees 180 controls rc 0 (pre-fix 6 failures)
- [x] **R20261123.8** After .1 to .5 land, re-count on the next window's blocklog and transcript. Record before and after for four numbers:
  - landing-stack blocks while promote would refuse, against this plan's 70;
  - halted rebases in the main checkout on a base without the stand-down, against 1;
  - "judged a different tree" refusals caused by a STATE.md-only diff, against 1;
  - refusals that name no voiding path, against 2.
    (ticked) 2026-11-23T10:42:10Z by ace763dd: commit:6b78fcc55e window 2026-11-23T04:52Z-10:35Z after R.1-R.7 landed, blocklog /tmp/claude-worklist/home_developer_console.blocklog-ace763dd.jsonl, 39 blocked stops: landing-stack while promote would refuse 70->0, halted main-checkout rebases 1->0, judged-different-tree on a STATE.md-only diff 1->0, refusals naming no voiding path 2->0
    (corrected 2026-11-27T07:36Z, review c3ca980d.1) 6b78fcc55e (`a receipt with no advance names what voided it and the run ci:quick will do`) is cited for both R.5 and R.8: the R.8 numbers come from the blocklog window 2026-11-23T04:52Z-10:35Z, which that commit ended, so it marks the window's close, not the commit that produced each after-state; R.1 to R.7 each carry their own commit.

  Test: .claude/rediacc_hooks/tests/test_wl_retro.py.

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/wl_stack.py
- /home/developer/console/.ci/rediacc_ci/dev/landing_promote.py
- /home/developer/console/.claude/rediacc_hooks/guards/block_rebase_over_foreign_dirt.py
- /home/developer/console/.claude/rediacc_hooks/guards/block_unverified_push.py
- /home/developer/console/.ci/policy/record-paths.json
