---
description: Near compaction, hand the session's important in-flight work to sub-agents with self-contained briefs, record each brief on its worklist item and in STATE.md, commit verified work and arm the wake timer, so the next context continues the work instead of rediscovering it. The Stop hook orders it (`wisdom-due`) once the context passes 92% of auto-compact; running it earlier is safe.
argument-hint: "[focus: the threads to hand over first; omit to judge from the open worklist]"
allowed-tools: Bash(.claude/hooks/stop/worklist.py:*), Bash(python3 .claude/hooks/stop/worklist.py:*), Bash(python3 .claude/hooks/stop/wl_wake.py:*), Bash(git add:*), Bash(git commit:*), Bash(git status:*), Bash(git log:*), Bash(git branch:*), Bash(date:*), Agent, SendMessage
---

## In flight, gathered

- UTC now: !`date -u +%FT%H:%MZ`
- Branch: !`git branch --show-current`
- Open worklist slice (`[>]` lines name their `worker:`): !`.claude/hooks/stop/worklist.py --list --open 2>/dev/null | head -60 || echo '(worklist unavailable)'`
- Uncommitted paths: !`git status --short | head -40`
- Unpushed commits: !`git log --oneline @{u}..HEAD 2>/dev/null | head -20 || echo '(no upstream)'`

## Why

The summary that replaces this context keeps a fraction of what the context knows. A diagnosis half done, a command already run with its exit code, a dead end already ruled out: none of it survives unless it is on disk or in a running agent's prompt. This command moves it there while the knowledge is still present. `$ARGUMENTS`, when given, names the threads to hand over first.

## Steps

`<me>` is this session's id (`CLAUDE_CODE_SESSION_ID`). Start no new work of the lead's own beyond the small inline fixes step 2 turns up (small as step 2 defines it); this is a hand-over.

1. **Inventory.** From the lines above and the session's own task list: running sub-agents and background shells, open `[ ]` items, `[>]` leases, uncommitted paths this session owns, unpushed commits, and threads held only in this context (an unwritten finding, a verified fix not yet committed, a plan not yet filed). A thread is important when the next context would otherwise rediscover it.
2. **Question the session's own conduct.** Step 1 finds the work that is tracked; this finds the work that was walked past. Reread this context and answer each question with the exact command, output or sentence that shows it, or "none":
   - **Workarounds.** Where did the session route around a tool, flag, guard, script or doc instead of fixing it: a raw read after a sanctioned tool came up short, a manual step a verb should own, a retry in place of a diagnosis? Would extending that tool now let the remaining work run through it?
   - **Narrated limits.** Which sentences say a tool "does not cover", "cannot", "is not supported", "falls back to", or "reads it directly"? Each one names a gap; is it fixed, tracked, or only described?
   - **Contradictions.** Did a doc, command or skill prescribe a step that a guard refused, or did two tools disagree about the same fact? The text and the tool cannot both be right.
   - **Repetition.** Which multi-step sequence ran more than once by hand? Is it worth a verb, a flag or a script?
   - **Unproven claims.** Which statements to the operator, in a commit message or in a tick rest on reading rather than on a run? Which gates were skipped, and which result came from a wrapper whose exit code was never read?
   - **Soft deferrals.** What was called "later", "post-merge" or "a follow-up" that has no real blocker? Work with no blocker is done now, not deferred.
   - **Unrecorded findings.** Is every defect met on the way an item with its exact command and output, and was each fixed bug's sibling class swept?
   - **Own mistakes.** Which error was the session's own (a wrong brief, a misread log, a command that hit a known rule)? Is the lesson on disk (a hint, a memory, a guard) so the next context does not repeat it?
   Each answer other than "none" becomes a thread: fixed inline now when small (CLAUDE.md rule 2: local, no new abstraction, no signature change rippling outward, and verified in this turn), otherwise an item (`worklist.py --add`) that counts as important for step 4 and is handed over there with the evidence that raised it. A thread fixed inline is closed, not handed over.
3. **Commit what is verified.** Each verified unit this session owns becomes its own commit in the CLAUDE.md rule 1 form (`git add -- <new paths>`, `git commit -F <msg> -- <paths>`, a `PR-TASK:` trailer). Unverified work is not committed; its thread is handed over in step 4 with the verification still to run named in the brief.
4. **Hand over each important thread without a live worker.** A running agent that already owns related files continues it (SendMessage with the missing context); otherwise a new background sub-agent takes it, its model chosen by CLAUDE.md rule 4. Writers count against `writer_cap` (agent/plans/QUEUE.md `## Settings`); Explore and Plan agents do not. A thread over the cap is queued, not dropped: its brief is recorded (step 5) and it is leased to `worker:queue`. Each brief stands alone, because its reader has none of this context:
   - the goal, the worklist item id, and the plan box or `PR-TASK:` id it serves;
   - what is already known: findings with `file:line`, commands already run with their exit codes, and the approaches already ruled out;
   - the exact files the agent owns, disjoint from every other live writer, and a ban on touching any other;
   - the acceptance check: the command whose rc 0 proves the work done;
   - the rules: writers never commit (the lead commits each spot-checked report by path); no `git checkout`, `restore`, `stash`, `clean`, `reset` or `add`; no regenerate or sync script (the report names one for the lead); the report lists the changed files and every command run with its exit code.
5. **Record each hand-over** once the agent's real id is back, never a placeholder: `worklist.py --lease <me> <id> +120 worker:<agent-id>`, then `worklist.py --update <me> <id> 'BRIEF: <goal>; owns <files>; accept <command>; agent <agent-id>'`. A thread with no item gets one first (`worklist.py --add <me> '(<me8>) <text>'`).
6. **Rewrite STATE.md** through `worklist.py --state <me>` (body on stdin, 250 to 4000 characters) with a `## Delegated` section, one line per agent (agent id, item id, files owned, acceptance check), and a `## Next action` naming what the lead does as each report lands (spot-check against the artifact, commit by path, tick with the sha). This rewrite is what clears the Stop hook's `wisdom-due`, provided the section is written for this context: a section carried over unchanged from the previous context does not count. Commit STATE.md by path.
7. **Arm the wake timer**: `python3 .claude/hooks/stop/wl_wake.py <me>` as a background Bash call with `timeout: 2400000`. A second start prints ALREADY ARMED.
8. **Report** one line per handed-over thread (item, agent, acceptance check), one line per step 2 answer that was not "none" (fixed with its sha, or handed over as which item), and one line for what stays with the lead.
