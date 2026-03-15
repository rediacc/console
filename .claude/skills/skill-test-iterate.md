---
name: skill-test-iterate
description: Test skill docs by running a real task with a sub-agent, then extracting feedback to improve the docs. Use when you want to validate and improve any skill docs through real-world usage.
user-invocable: false
---

# Skill Doc Test & Iterate

A two-phase pattern for improving skill docs through real sub-agent usage.

## When to use

After writing or updating skill docs, run this pattern to validate them against reality. The sub-agent uses ONLY the skill docs to complete a real task, then reports what was wrong, missing, or misleading.

## Phase 1: Execute a real task

Launch a sub-agent with a concrete task that exercises the skill docs. The prompt must:

1. **Point the agent to the skill docs** — tell it to read and follow them
2. **Give a specific, testable task** — not "explore", but "deploy X, verify Y, migrate Z"
3. **Include success criteria** — what does "working" look like? (e.g., "counter should continue from N, not reset to 0")
4. **Include cleanup instructions** — leave the environment clean for the next round
5. **Ask for a detailed report** — timing, errors, exact log messages, anything unexpected

```
You are testing the [DOMAIN] workflow end-to-end. Use the skill docs at `.claude/skills/[SKILL]/` for guidance.

**CRITICAL**: This repo uses git worktrees. Your working directory is [WORKTREE_PATH] — use this for ALL paths. Use `./rdc.sh` (not `npx tsx`) for CLI commands.

**Infrastructure state**: [describe current state — what's running, what's clean, SSH keys, etc.]

**Your task**: [specific steps with expected outcomes]

**Report**: Provide a clear summary of:
- What succeeded and what failed
- Exact timing for each step
- Exact error messages and log output
- Anything that surprised you or that the docs didn't cover
- Any command that didn't work as the docs described
```

## Phase 2: Extract feedback

Resume the SAME agent (by ID) and ask it to critique the docs based on its experience:

```
Based on your full test experience, what specific improvements should be made to the skill docs in `.claude/skills/[SKILL]/`? Think about:

1. **Anything you got wrong or had to figure out** that the docs didn't explain well
2. **Timing/performance numbers** — your measurements vs what the docs say
3. **Behaviors you observed** that should be documented (exact log messages, error sequences, side effects)
4. **Missing warnings or gotchas** — things that surprised you or could trip up a future agent
5. **Any commands that didn't work as expected** or had surprising behavior
6. **Contradictions** between different doc files

Be specific: give me the exact file, what's wrong/missing, and what should be added or changed. Don't be generic — cite your actual test observations.
```

## Phase 3: Apply improvements

Review the agent's feedback and apply changes to the skill docs. For each suggestion:
- **Verify it's real** — the agent observed it, not speculated
- **Keep it concise** — bullet points, not paragraphs
- **No internal implementation details** — no source file references (e.g., `wrapper.go:106`), only user-facing behavior
- **Update all affected files** — a finding may apply to multiple docs

## Key principles

- **Resume, don't re-launch** — Phase 2 must resume the Phase 1 agent so it has full context of what it actually experienced
- **Real tasks only** — the value comes from real execution, not hypothetical review
- **Specific over generic** — "ECONNREFUSED after restore because postgres needs 5s to start" beats "handle connection errors"
- **One round minimum, two rounds ideal** — if Phase 2 reveals significant gaps, run another Phase 1 with the updated docs to verify the fixes
