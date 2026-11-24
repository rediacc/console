# PLAN: Stop-hook retro, 2026-11-22 (band early, lead session ace763dd, tracking #b63f151f)

Status: ready
Depends-On: no-dep -- no box waits on another plan; R20261122.3 re-counts after R20261117.5, which it names in its text
Priority: P2 -- 4 blocked stops in the window, each answered within 19 s; the cost is 13 hand re-leases and one over-reaching mark-read
Concurrency: parallel -- R20261122.1 edits worklist_messages.py and wl_checks.py, R20261122.2 edits wl_report.py
Owns: .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_report.py, .claude/rediacc_hooks/tests/test_wl_roster.py, .claude/rediacc_hooks/tests/test_wl_report_inbox.py, .claude/rediacc_hooks/tests/test_wl_retro.py, agent/plans/PLAN-stop-hook-retro-20261122.md
First-Seen: 2026-11-22
Owner: d778be9d (adopted from ace763dd 2026-11-24)
Updated: 2026-11-24

**Scope.** The brief gives lead transcript bytes 0 to 13815810 of `ace763dd-04fa-45b1-aa44-0da57b775268.jsonl`. This range holds the blocks at 05:39:23, 05:43:52, 06:13:07 and 08:50:07 on 2026-11-22. The fifth blocklog row, `wake-timer` at 10:21:57, sits at offset 14217661, outside the range. That row is counted from the ledger only and its transcript text was not read.

The ledger `/tmp/claude-worklist/home_developer_console.blocklog-ace763dd.jsonl` holds 5 blocked stops:
- wake-timer: 3
- roster-dead: 1
- unread-reports: 1

All 5 rows have `named: []` and `judge: {}`. There are 0 judge flags, 0 hint proposals, 0 admissions and 0 refused `--tick` calls. Line numbers refer to the working tree at the time of the retro.

**Correction to the lead's observation.** The wake-timer blocks did not fall within one hour. The ledger rows are 05:43:52, 08:50:07 and 10:21:57, which span 4h38m.
- Neither in-range block came "right after a 30-minute timer exited" in the way the observation says.
  - The 05:43:52 block (offset 12051509) was the first arm of the session. No timer had run before it, and the lead armed 11 s later at 12063074 (05:44:03).
  - The 08:50:07 block (13758028) came 5m20s after the timer started at 08:14:47 (13382265) exited. The exit notification is at 13405943 (08:44:48). The lead worked on a CI red for those 5 minutes and stopped without re-arming. It armed again 5 s after the block, at 13773691 (08:50:13).
- Six of the seven wl_wake arms were re-arms made right after a timer exit. They are at 12537627 (06:14:10), 12740533 (06:44:19), 12946116 (07:14:33), 13209734 (07:44:40), 13382265 (08:14:47) and 13773691 (08:50:13). Only the last was forced by the hook. Re-arms 1 to 5 were unprompted, and each one let the stop at that moment pass.
- The hook's text is accurate on the first arm and on the 08:50 stop.
- The remaining gap is that the block does not say the previous timer fired, and that is already open as R20261117.5. See friction 3.

Another timeline fact bears on the ranking. The 05:39:23 `roster-dead` block (offset 11795587) and 13 manual re-leases of the same item made up the other lease traffic in this window. That is friction 1.

**Legitimate or already covered, not ranked:**
- **wake-timer 05:43:52 (12051509):** first arm of the session, with one background task live and no timer. Correct. The lead armed within 11 s.
- **wake-timer 08:50:07 (13758028) and 10:21:57 (not read):** the timer had exited and a CI watch was still running. The block was correct. Cost: one block and one tool call each. The only fix wanted is the one already filed as R20261117.5, third bullet, which blocks "with the fire time and the re-arm command". That bullet has not landed. The check at `.claude/hooks/stop/wl_checks.py:4298-4313` still reads `if live_bg and not _wakers`, and `V_WAKE_TIMER` (`.claude/hooks/stop/worklist_messages.py:444`) still carries no fire time.
- **roster-dead 05:39:23:** #876420de was leased to `worker:a1562580d7c3224df`, which had finished. The lead re-leased within 5 s (11807365). Correct block. The cost is in friction 1.
- **wisdom-due at 93% and 96% context:** these were queued advisories (08:15:02, 08:50:08) and never led a block.

## Ranking by cost to the session

| Rank | Point | Count in this window | Turns lost | Already fixed by? |
|---|---|---|---|---|
| 1 | #1: a lease on the lead's own background shell dangles when the shell exits, so the lead re-leases by hand after each one. The roster-dead text does not name `worker:lead`. | 13 manual `--lease ace763dd 876420de` calls (11807365 at 05:39:28 to 13736844 at 08:49:29, ledger row roster-dead 05:39:23). 1 block, 12 pre-emptive. | 1 block turn plus 12 re-lease calls, each folded into an `--update` call. | no |
| 2 | #2: `wl_report.py --list --unread` lists reports the Stop hook did not count, so a bulk mark-read over-reaches. | 1 block (unread-reports 06:13:07). The hook counted 28, the list printed 35, and 35 were marked read (12512751). | 1 block turn, 3 calls (12508330 to 12526130). | no |
| 3 | #3: the wake-timer block does not say the previous timer fired. | 2 in-range blocks (12051509, 13758028), 1 more in the ledger row 10:21:57 (not read). 6 re-arms, 1 forced. | 2 block turns in range, 5 s and 11 s to recover. | R20261117.5 (open, third bullet), not re-proposed |

Total in range: 4 blocked stops, all answered within 11 s except the report mark (19 s, 06:13:07 to 06:13:26).

## 1. A lease on the lead's own shell dangles at each exit, and the block does not name `worker:lead`

**What happened.** Item #876420de ("PR 605 landing ci:quick reds") was leased to `worker:a1562580d7c3224df`, a finished writer. The 05:39:23 stop was blocked with `LEASED TO A FINISHED WORKER` (11795587). From then on, every new background shell the lead started became the item's worker through a hand-typed re-lease. The 13 calls (14 `--lease` calls in total, 1 of them for another item) are at offsets 11807365, 12032495, 12140779, 12328519, 12466502, 12714715, 12918689, 13029630, 13115905, 13181218, 13264853, 13353317 and 13736844. The worker ids are shell ids (`b0ec6gznz`, `b379m9kso`, `b2zwbpfmg`, `b771kv4p0`, `bjica57ks`, `bszopyp4k`, `bhz92iik4`, `bzmls4q7m`, `b079kohxw`, `bm4f3vptz`, `b4mzw0cnk`, `b5n1gtcaw`, `b76zao0yr`) and not agent ids. After 05:39:23 no further roster-dead block fired. The re-leases kept the lease on a live shell, one every 5 to 30 minutes.

**Root cause.**
- The block text offers only `--tick` and `--lease <me> <id> release`, plus the words "re-lease it to a live worker". It gives no command for a live worker (`.claude/hooks/stop/worklist_messages.py:3044-3052`, `V_ROSTER_DEAD`).
- A durable remedy already exists. `worker:lead` is live "exactly while something of this session is running to wake the lead" (`.claude/hooks/stop/wl_store.py:1577-1580`). The Stop hook adds it to `live_worker_ids` whenever a live background task or the wake timer covers the session (`.claude/hooks/stop/wl_checks.py:3509-3515`, `wl_leasehelp.lead_covered`).
- The lead's item waits on that session's own CI shell and the wake timer. A one-time lease to `worker:lead` would have covered every later shell with no further calls.
- The message does not mention it, and the WORKLIST GUIDE line at 08:15:02 (13400562) shows `worker:b5n1gtcaw [confirmed]`, which reads as the form to copy.

**Fix.** Give `V_ROSTER_DEAD` a third remedy line, `.claude/hooks/stop/worklist.py --lease <me> <id> +120 worker:lead`. It is worded as "when the work waits on this session's own background shell or the wake timer". It is rendered only when `lead_covered` holds at that stop, so it is never offered when it would immediately fail closed.

## 2. `wl_report.py --list --unread` disagrees with the Stop hook's count

**What happened.** The 06:13:07 stop was blocked by `UNREAD SUB-AGENT REPORTS (28 on branch 1121-1)`, 10 rows shown and "18 older not shown" (12482224, ledger row unread-reports 06:13:07). The lead ran `--list --unread`, got 35 ids, and marked all 35 read (12510143, result "35" and "marked 35 report(s) read" at 12512751). Its own message records that 35 were marked read, "which may include a few the hook listing hadn't shown" (12526130).

Measured against the index (`/home/developer/.claude/agent-reports/home_developer_console`):
- Branch 1121-1 holds 84 index rows, 77 from session d778be9d and 7 from ace763dd.
- The read ledger holds 70 `task-notification` marks and 7 `superseded` marks by d778be9d, and 42 `task-notification` marks plus the 35 manual marks (`via` unset) by ace763dd.
- The claim that the reports were already read holds. The predecessor read 70 of them. That the restarted session sees them again is the accepted cost recorded at `.claude/hooks/stop/wl_report.py:266`, so no change to marking is proposed.

**Root cause.**
- The hook calls `wl_report.unread(store, branch, reader, peer_live)` (`.claude/hooks/stop/wl_report.py:292-325`). That function skips a foreign-and-stale report, a foreign-and-live report, a relay, and an interim wait that is still pending or superseded.
- The CLI path (`.claude/hooks/stop/wl_report.py:1491-1516`) filters the branch only, then `rejudge` and `relay`. It applies none of `_foreign_and_stale`, `_foreign_and_live` or the `interim` handling.
- The in-code comment says "so the listing and the Stop hook agree on what is a report", and that is not true for those three filters.
- The 7 extra ids were therefore reports the hook had chosen not to count, such as a peer's live report or a held interim wait. Marking them read removed them for good.

**Fix.** The CLI `--list --unread` path calls the same `unread()`, with `peer_live` from the same source the hook uses. When the CLI cannot read liveness, it prints the dropped count ("7 held back: live peer or pending wait") and does not mark them. `--read` on an id the hook would not count prints a one-line warning and still marks it.

## 3. The wake-timer block says nothing about the timer that just fired

**What happened.** Blocks 12051509 (05:43:52) and 13758028 (08:50:07); ledger row wake-timer 10:21:57 (transcript text not read). The 08:50 block names 2 live background tasks and says "arm the session's timer", without saying that the timer started at 08:14:47 exited at 08:44:48.

**Root cause.** `.claude/hooks/stop/wl_checks.py:4298-4313` and `.claude/hooks/stop/worklist_messages.py:444`, the same site named in R20261117.5.

**Fix.** Covered by R20261117.5, third bullet ("blocks with the fire time and the re-arm command"). No new box is added. That box also cites the old line `.claude/hooks/stop/wl_checks.py:4469`, which is now `:4298-4313`, so it should be edited when it lands. The re-count in R20261122.3 reuses this window's number (2 in-range blocks) as the baseline.

## Decisions

- **Name `worker:lead` in the roster-dead block (friction 1).**
  - DEFAULT: add the remedy line only when `lead_covered` holds. Do not auto-release or auto-re-lease from the hook.
  - WHY: `worker:lead` is the documented lease for work the lead waits on (`.claude/hooks/stop/wl_store.py:1577`). The 13 hand re-leases added no information the hook lacked.
  - HOW: pass the covered flag into the message renderer the same way `lead_covered` is already used at `.claude/hooks/stop/wl_checks.py:3512`, then add one `%s` line to `V_ROSTER_DEAD`.
- **Keep per-reader marks (friction 2).**
  - DEFAULT: do not carry marks across a restart, and do not widen `--read`.
  - WHY: `.claude/hooks/stop/wl_report.py:261-269` records that the re-surfacing is accepted on purpose and warns against a suppression mechanism. Only the CLI/hook disagreement is a defect.
  - HOW: reuse `unread()`.
- **Wake timer.**
  - DEFAULT: leave to R20261117.5. Do not make `wl_wake` re-arm itself.
  - WHY: the exit is the wake-up (`.claude/hooks/stop/wl_wake.py:6`), so a self-respawning timer would never exit and would never wake the session.
  - HOW: see R20261117.5.

## Sequencing

1. R20261122.1 and R20261122.2 are independent and can go in parallel.
   - .1 edits `worklist_messages.py` and `wl_checks.py`.
   - .2 edits `wl_report.py`.
2. R20261122.3 runs after them, and after R20261117.5 and R20261117.9, so the two re-counts share one window.

## Tasks

- [ ] **R20261122.1** Name `worker:lead` as a re-lease target in `V_ROSTER_DEAD` (`.claude/hooks/stop/worklist_messages.py:3044-3052`), shown only when `wl_leasehelp.lead_covered` holds at that stop (`.claude/hooks/stop/wl_checks.py:3509-3515`, render site `:4251-4253`). Fixture: #876420de leased to a finished agent, with a live background shell of the session, so the block text holds `--lease <me> <id> +120 worker:lead`. Inverse: no live task and no timer, so the line is absent. Inverse: a lease already on `worker:lead` with a live shell raises no roster-dead. Test: .claude/rediacc_hooks/tests/test_wl_roster.py.
- [ ] **R20261122.2** Make `wl_report.py --list --unread` (`.claude/hooks/stop/wl_report.py:1491-1516`) use `unread()` (`:292-325`), so the CLI and the hook count the same reports. It prints how many it held back and why. Fixture: 35 branch rows of which 7 are a live peer's reports or pending interim waits, giving a CLI list of 28 that equals the hook count. Inverse: reader unknown, so all 35 are listed. Test: .claude/rediacc_hooks/tests/test_wl_report_inbox.py.
- [ ] **R20261122.3** After .1, .2 and R20261117.5 land, re-count on the next window's blocklog. Record before and after for three numbers: the manual lease calls against this plan's 13, the CLI-minus-hook unread gap against 7, and the wake-timer blocks that name a fire time against this plan's 0 of 3. Test: .claude/rediacc_hooks/tests/test_wl_retro.py.

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/worklist_messages.py
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/hooks/stop/wl_report.py
- /home/developer/console/.claude/hooks/stop/wl_store.py
- /home/developer/console/.claude/rediacc_hooks/tests/test_wl_roster.py
