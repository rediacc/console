---
description: Spawn a background pr-babysitter teammate to commit the uncommitted work, open coordinated PRs (submodule-first), and drive CI to all-green — while you (the team lead) continue the remaining task list. You compose a context briefing from the session, hand the primary tree to the babysitter, rule on its escalations, and independently verify the final green. Stops at green PRs; does not merge.
argument-hint: "[short summary of the change to seed the briefing/PR titles]"
disable-model-invocation: true
allowed-tools: Bash(git branch:*), Bash(git status:*), Bash(git submodule status:*), Bash(gh pr list:*), Bash(date:*)
---

## Current state

- Today (branch base): !`date +%m%d`  (feature branches are `MMDD-N`)
- Current branch: !`git branch --show-current`
- Console tree (excl. settings.local.json): !`git status --short | grep -v '.claude/settings.local.json' | wc -l | tr -d ' '` changed path(s)
- Submodules with changes: !`git status --short private/renet private/account private/elite private/homebrew-tap 2>/dev/null || echo '(none)'`
- Open PRs on the current branch: !`cb="$(git branch --show-current)"; for r in console renet account; do p=$(gh pr list --repo rediacc/$r --head "$cb" --state open --json number,title --jq '.[] | "  rediacc/'$r' #\(.number) \(.title)"' 2>/dev/null); [ -n "$p" ] && echo "$p"; done; true`

## Task: orchestrate a background babysit, keep working

You are the **team lead**. Do not run the CI loop yourself — a long babysit (up to ~27 rounds over days) belongs in a disposable context. Your job is the four things only you can do: compose the briefing, hand over the tree, rule on escalations, verify the end. The loop mechanics live in `.claude/agents/pr-babysitter.md`; wave-specific intent lives in the briefing you write now. `$ARGUMENTS`, if given, seeds the intent summary.

### 1. Preconditions
- **One babysitter at a time.** Check the task board for an existing babysit task; if one is live, stop and say so (a second pusher triggers the cancel-old-ci race and the shared-tree hazard).
- **Resume detection**: if PRs already exist for this branch (state block above), the babysitter resumes at CI/reviews — say so in the briefing; nothing is re-created.
- **Stacking decision — yours, not the babysitter's**: new `MMDD-N` branch from main, or stack onto an existing branch/PRs? Stack when the work depends on unmerged prerequisites (precedent: a follow-up wave stacked onto its predecessor's open PRs because main lacked the base). Record the decision and the rationale in the briefing.

### 2. Compose the briefing (the context-awareness artifact)
Write it to `~/.claude/projects/-home-muhammed-monorepo-console/reports/pr-babysit-<branch>-briefing.md`. **It is immutable once the babysitter is running** — supersede with a new file if it must change; never rewrite in place. Slots (fill from the session; the diff cannot tell you intent):

1. **Intent** — what the wave did and why, in a paragraph.
2. **Deliberate renames / removals** — commands, flags, files. A failing test or doc that references an old name must be read against this map, not "fixed" backwards.
3. **Sanctioned reds, each with its reason** — CI checks that are red on purpose (deferrals, environment-only). Without this the babysitter's first act is to "fix" a deferral.
4. **Frozen surfaces** — anything the babysitter must not edit without escalating.
5. **Known-good baseline numbers** — test counts, gate counts, fingerprints — so drift is a question, not a chore.
6. **Decision-boundary additions** — wave-specific tier-2/tier-3 adjustments (e.g. a sanctioned i18n string class).
7. **Escalation routing** — domain → who answers. Default: you. Name live domain teammates only if you explicitly authorize direct asks.
8. **Memory pointers** — at minimum: the previous `pr-babysit-*` memory, `feedback_ci_gate_chain_pr501`, `feedback_ci_review_gates_flow`, `feedback_ci_watch_pattern`.

**Cold-start rule**: if you lack session context to fill slots 1–4 (fresh session, unfamiliar tree), survey the diff, fill what you can, and **ask the user the unfillable questions before spawning** — sanctioned reds? deliberate renames? stack or new branch? Three questions up front beat a wrong round 1.

### 3. Hand over the tree, register, spawn
- **The primary working tree belongs to the babysitter** from now until green (it needs the installed node_modules, builds, `rdc.sh`). Any further implementation teammates you spawn for other tasks use `isolation: "worktree"`. You yourself avoid editing tracked files in the primary tree; if work must be absorbed into the PR later, message the babysitter with explicit paths.
- `TaskCreate` a babysit task so the board and your watchdog cover it.
- Spawn the teammate in the background (`subagent_type: pr-babysitter` if registered, else general-purpose with an instruction to read `.claude/agents/pr-babysitter.md` as its role definition), initial prompt = the briefing path + branch + PR links + anything time-critical.

### 4. Your duties while it runs (interleave with your other tasks)
- **Rule on escalations** — each arrives as a structured question (gate, log, candidate fixes, recommendation). Verify claims in code before ruling when they are load-bearing; a wrong ruling costs a CI round. Record rulings where the babysitter logs rounds.
- **Watchdog**: cover the babysitter's round log (`reports/pr-babysit-<branch>.md`) in your periodic tick — freshness is its liveness; judge from the artifact, not process lists. Dead-driver signature → one ping → replacement brief that HOLDS for your GO (warm-start from the round log).
- Do **not** edit the gates or generated artifacts it depends on while it runs. An instrument under edit cannot be read.

### 5. Verify, then close
- When the babysitter reports green: **verify independently** — check every PR's checks via `gh` yourself, spot-run the local battery. Never accept "all green" on report; require run URLs.
- Distill the round log into a `pr-babysit-<branch>` memory file (the previous one demonstrably saved rounds on the next wave).
- Report PR links + headline results. **Do NOT merge, do NOT push `main`** — `/pr-merge` is the user's call.
