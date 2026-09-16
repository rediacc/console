# PLAN: durable sub-agent reports, and a pushed inbox
Status: compacted
Owner: written by branch `0804-1`, 2026-08-05; closed by session e6500e92, 2026-08-18
Full-Text: f7a5351a9 agent/PLAN-durable-reports-and-push-inbox.md
Full-Text-Blob: a91ac53ed56cfecca406211ee76856603b192686
Record-Sig: f5fe26b0

## Why
Two operator asks. (A) A teammate's report arrived by SendMessage into the lead's
conversation and nowhere the lead could look afterwards, so after a compaction a
substantive report and a silent agent were indistinguishable to a fresh session. (B) The
inbox was polled by a `*/5` cron running `worklist.py --poll`, where almost every firing
printed nothing and each one cost a full session turn: "kind of ping when ready not
loop". The decisive finding was that the harness already hands the report over: the
`SubagentStop` event carries `last_assistant_message`, `agent_id`, `agent_type` and
`agent_transcript_path`, so capture needs no transcript scraping and no join on agent
name.

## Outcome
SHIPPED, both halves. Header `done` is TRUE, and the header itself was the fix for an
earlier lie: this file previously carried no `Status:` line at all and was read as
UNKNOWN. Measured 2026-09-06.

- (A) `.claude/hooks/stop/wl_report.py` exists (blob
  4f733e9ff651d2288e640463ab095c5ecaab3039) with the `--show` and `--read` verbs in its
  dispatch table at `:888-889` and the `--list --unread` guidance at `:579`.
- The capture point is wired where the design put it: `.claude/settings.json` registers
  `SubagentStop` as a single hook running `wl_report.py --subagent-stop`, so the report
  is taken from the harness event rather than reconstructed.
- (B) `.claude/hooks/stop/wl_wait.py` exists (blob
  3b1632cea3743dbe4696d1bd89a891e00062649d).
- Landing: console commit 1575c8c3b, "feat(hooks): durable sub-agent report inbox, a
  blocking waiter, and a CLI dispatch that cannot fall through" (2026-08-05), verified
  with `git log --follow --diff-filter=A` on both files.
- THE RESIDUE THIS PLAN NAMED IS STILL THERE, and it has moved: the stale
  `worklist.py --poll` guidance is now at `.claude/hooks/stop/worklist_messages.py:396`
  and `:768`, not the `:237` and `:446` the header records. The `--poll` verb still works
  (`.claude/hooks/stop/worklist.py:1972`), so this remains stale advice rather than a broken path, but it
  still points a reader at the mechanism this plan replaced. NOT FIXED HERE: this
  session's write access is its ten plan files, and `.claude/hooks/stop/*.py` is
  explicitly out of bounds for it.

## Lessons
- Probe the harness before designing around it. The whole capture half of (A) collapsed
  from "scrape the transcript and join on agent name" to "read the field the event
  already carries" because someone read the installed binary's own schema strings.
- A pointer into another file by LINE NUMBER decays silently. The two residue anchors in
  this plan's own header were both wrong within weeks; the strings were still findable,
  the line numbers were not.
- The exit IS the notification. Replacing a poll with a blocking waiter removed a whole
  class of empty turns rather than making them cheaper.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:32:36Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: .claude/agents/pr-babysitter.md
Gates: none
Why-Source: author
Read-History: `git show a91ac53ed56cfecca406211ee76856603b192686` recovers the text; `git log --find-object=a91ac53ed56cfecca406211ee76856603b192686 --all` names the commit

## History
- 2026-09-06T17:32:36Z compacted by 8f55d4f0 from `done` (record-sig f5fe26b0)
