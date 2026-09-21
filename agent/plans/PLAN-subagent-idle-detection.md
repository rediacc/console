# Subagent idle/liveness detection
Status: compacted
First-Seen: 2026-09-20
Owner: 0ad063bf
Full-Text-Blob: 3eda61343415af897cc0d2c135836fb962e5cdd4
Record-Sig: 7d5c813c

## Why
A lead session spawning writer subagents couldn't tell whether they were still working, had finished, or were dead. Four approaches failed: ListAgents returned silence (which is not a death signal), file mtimes were misread as liveness (when they only show last-write), waiting for completion notifications (one agent never sent one, the others arrived 37–40 minutes late), and stale
report queries. Real cost: four items held as in-flight on stopped workers for 3.5 hours.

## Outcome
Built `teammate_state()` function that classifies subagent status by reading the transcript JSONL tail: idle (turn finished), working (mid-turn and recent), stalled (mid-turn and old), or unverifiable. Verified against real transcripts. Wired into the worklist liveness ladder to report idle workers and block after 15 minutes. Live probes exposed TeammateIdle hook payload structure
and that streaming partials can hide finished agents; sidecar edge timestamps decide verdict when transcript is ambiguous. Hook journal (idle edges, <1s latency) is the source of truth; notification delivery is observed but not trusted.

## Lessons
- The transcript tail's stop_reason field is a self-recorded ground truth that cannot be faked by self-reports; it is strictly stronger than ListAgents silence or mtime checks.
- File mtimes are lagging indicators and must never be treated as liveness signals—they show when an agent last wrote, never whether it is alive.
- TeammateIdle fires for ordinary subagents, but its payload was undocumented; the name comes from teammate_name, not agent_id, and a diagnostic for future payload drift was added.
- Streaming partials (stop_reason: None) are common and look mid-turn but may indicate finished agents; an idle edge timestamp from the hook decides the verdict only while mtime hasn't moved past it.
- Notification delivery latency varies from 4 to 40 minutes with no observable pattern—too variable to wait on. The hook journal is the instrument.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: ready
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:01:46Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: .claude/settings.json
Gates: none
Why-Source: model
Read-History: `git show 3eda61343415af897cc0d2c135836fb962e5cdd4` recovers the text; `git log --find-object=3eda61343415af897cc0d2c135836fb962e5cdd4 --all` names the commit

## History
- 2026-09-20T18:01:46Z compacted by d778be9d from `ready` (record-sig 7d5c813c)
