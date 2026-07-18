---
description: Drive the commit → coordinated PRs (submodule-first) → CI-all-green loop for the current tree. Default — run the loop IN THIS SESSION per .claude/agents/pr-babysitter.md (delegating bulky fix implementation to worker sub-agents). Pass `bg` as the first argument to instead spawn a background pr-babysitter teammate and supervise it. Stops at green PRs; never merges.
argument-hint: "[bg] [short summary of the change to seed intent/PR titles]"
disable-model-invocation: true
allowed-tools: Bash(git branch:*), Bash(git status:*), Bash(git submodule status:*), Bash(gh pr list:*), Bash(date:*)
---

## Current state

- Today (branch base): !`date +%m%d`  (feature branches are `MMDD-N`)
- Current branch: !`git branch --show-current`
- Console tree (excl. settings.local.json): !`git status --short | grep -v '.claude/settings.local.json' | wc -l | tr -d ' '` changed path(s)
- Submodules with changes: !`git status --short private/renet private/account private/elite private/homebrew-tap 2>/dev/null || echo '(none)'`
- Existing date branches (console remote): !`git branch -r | grep "$(date +%m%d)-" || echo '(none yet)'`
- Open PRs on the current branch: !`cb="$(git branch --show-current)"; for r in console renet account; do p=$(gh pr list --repo rediacc/$r --head "$cb" --state open --json number,title --jq '.[] | "  rediacc/'$r' #\(.number) \(.title)"' 2>/dev/null); [ -n "$p" ] && echo "$p"; done; true`

## Mode

- If the **first whitespace-delimited token of `$ARGUMENTS` is exactly `bg`** → **Delegate mode** (below); the remainder of `$ARGUMENTS` seeds the intent summary. Bare `/pr-babysit bg` is valid (intent comes from the session survey + cold-start questions).
- Anything else — including no arguments — → **Default mode**: you run the loop in this session; `$ARGUMENTS` seeds the intent summary. (`bg` must be the entire first token: a summary that merely starts with those letters, e.g. "bgp fix", is NOT delegate mode.)
- Model note: the agent file's `model: opus` applies only to the delegated teammate; in default mode the loop runs on the session model.

## Preflight (both modes)

- **One babysit at a time.** Check the task board for a live babysit task and, in default mode, that you are not about to push alongside an existing background babysitter — a second pusher triggers the cancel-old-ci race and the shared-tree hazard. If one is live, stop and say so.
- **Resume detection**: if PRs already exist for this branch (state block above), the loop resumes at CI/reviews — record that in the wave header/briefing; nothing is re-created.
- **Stacking decision — made here, not mid-loop**: new `MMDD-N` branch from main, or stack onto an existing branch/PRs? Stack when the work depends on unmerged prerequisites (precedent: a follow-up wave stacked onto its predecessor's open PRs because main lacked the base). Record the decision and rationale in the wave header/briefing.
- **Cold-start rule**: if you lack session context to fill the wave header's first four slots (intent, deliberate renames, sanctioned reds, frozen surfaces — spec in the agent file's round-log section), survey the diff, fill what you can, and **ask the user the unfillable questions before starting** — sanctioned reds? deliberate renames? stack or new branch? Three questions up front beat a wrong round 1.

## Default mode: run the loop here

**Read `/home/muhammed/monorepo/console/.claude/agents/pr-babysitter.md` in full and execute it as written. You are the babysitter; the principal is the user.** No mechanics are restated here — that file is the single source of truth for the loop, the tier system, the round-log format, and the gotchas.

- Compose the **wave header** at the top of the round log (`reports/pr-babysit-<branch>.md`) per the agent file's slot spec — there is no separate briefing file in this mode.
- **The round log is your compaction insurance.** After any context compaction or session restart, re-read the agent file + wave header + STATUS block before touching anything.
- **Every turn that leaves a CI run in flight ends with an armed terminal-state watch** (agent file, wake-up section). Nobody else is watching the run.
- Tier 3 = stop and put the question to the user (AskUserQuestion or structured report); keep draining tier-1/2 meanwhile; no push until ruled.
- **Default to farming bulky fix implementation out to worker sub-agents** (agent file, "Workers" section — Sonnet for i18n/mechanical sweeps, Opus for code fixes). That is what keeps a long in-context loop affordable; you keep diagnosis, commits, and pushes.
- Scoping honesty: for a wave you expect to run **multi-day**, `bg` is usually the right call — the 0707 babysitter itself died of context exhaustion mid-campaign. The default is a default, not a dogma.

## Delegate mode (bg): spawn and supervise

You are the **team lead**. Your job is the four things only you can do: compose the briefing, hand over the tree, rule on escalations, verify the end. Your real work while it runs is *the remaining task list* — if you have nothing to do but watch CI, the wave was mis-scoped.

### 1. Compose the briefing
Write it to `~/.claude/projects/-home-muhammed-monorepo-console/reports/pr-babysit-<branch>-briefing.md`. Contents: the **wave-header slots as specced in the agent file's round-log section** (intent, renames/removals, sanctioned reds, frozen surfaces, baselines + their measurement commands, decision-boundary additions, memory pointers) plus two delegate-only slots: **escalation routing** (domain → who answers; default: you) and **anything time-critical**. **Immutable once the babysitter is running** — supersede with a new file, never rewrite in place. (Briefing and round log stay two artifacts on purpose: the briefing is your immutable handoff; the round log is the babysitter's mutable state. Do not "simplify" them into one.)

### 2. Hand over the tree, register, spawn
- **The primary working tree belongs to the babysitter** until green (it needs node_modules, builds, `rdc.sh`). Other implementation teammates you spawn use `isolation: "worktree"`. Do not edit tracked files in the primary tree; if you must (a fix only you can make), tell the babysitter the exact paths and that they are yours — it stages surgically and will otherwise treat them as a leak.
- `TaskCreate` a babysit task so the board and your watchdog cover it.
- Spawn in the background (`subagent_type: pr-babysitter` if registered, else general-purpose with an instruction to read `.claude/agents/pr-babysitter.md` as its role definition), initial prompt = briefing path + branch + PR links + anything time-critical.

### 3. ⛔ You do not read CI
From spawn until it reports green, you do not run `gh run watch/view/list` or fetch a job log — not once, not "just to check" — and you do not diagnose a red. The failure mode is not the lead ignoring CI; it is the lead **shadowing** it: two agents burning full context to produce one answer. (Real case: lead and babysitter independently root-caused the same compile break, the same crashing gate, and fell into the same stale-`tsbuildinfo` trap. Everything correct, everything doubled.) **Two agents agreeing is not verification — it is the same answer, paid for twice.** Verification is the babysitter testing a claim against the live system. Your status channel is the round log's **STATUS block**; if it does not say what you need, ask the babysitter — do not go look.

### 4. Rule on escalations (the interrupt handler)
- Each arrives structured: gate, log, candidate fixes, recommendation. Verify a load-bearing claim **in the code**, not by re-running CI. **Rule on the question asked; do not adopt the red** — "helping" by diagnosing it yourself is the shadowing failure wearing a helpful face.
- **Expect to be overruled, and make it safe.** The babysitter is required to test your rulings before executing (agent file, Rule 1); one wave overturned the lead four times, including an order to delete what was in fact the strictest gate in the suite. A ruling issued from an artifact rather than from running the thing is a hypothesis — say so when it is one.
- Learned coordination rules: **rule on the class, not the site** (one commit per ruling — a sweep ruled site-by-site burns rounds); never diagnose from a truncated instrument read (`grep | head` has hidden the decisive hit); **no parallel editors** against the babysitter's tree (translators racing it caused live losses); agree baseline counts **and the command that measures them** up front — two parties measuring differently manufactures drift; a suspiciously quiet gate may be short-circuiting upstream (one emitted 30 rounds of false comfort) — ask what would make it fire.

### 5. Watchdog
- Liveness = **freshness of the round log's STATUS block**, judged from the artifact, not process lists or notifications.
- **An "idle/available" notification is the NORMAL state of a healthy babysitter** — an armed background watch means its turn ended by design. Idle + fresh STATUS + run in flight = working as intended: do not ping, do not replace, do not peek at CI. (Real case: a lead treated three idle notifications in four minutes as a dying agent while the round log was 90 seconds old.)
- The actual dead-driver signature: **stale STATUS across a period in which the run demonstrably changed state.** Then: one ping → if still stale, a replacement brief that HOLDS for your GO (warm-start from the round log).
- Do **not** edit the gates or generated artifacts the babysitter depends on while it runs. An instrument under edit cannot be read.

### 6. Verify once, then close
- On the green report: **verify independently, ONCE** — check every PR's checks via `gh`, spot-run the local battery. Never accept "all green" on report; require run URLs. **This is the only time you touch the GitHub API during a babysit** — a per-round habit is exactly how the lead drifts back into shadowing.
- Confirm debugging aids are off (e.g. a `no-cancel-failure` label) and files you told it to leave alone are still uncommitted.
- Distill the round log into a `pr-babysit-<branch>` memory file (the previous one demonstrably saved rounds on the next wave).
- Report PR links + headline results. **Do NOT merge, do NOT push `main`** — `/pr-merge` is the user's call.
