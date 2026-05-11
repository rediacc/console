# PDF rewrite pipeline — agent team

A four-subagent team that processes Rediacc growth PDF source markdowns:

1. Strips sales/internal-strategy content (last-page CTA only policy).
2. Produces two variants per deck: `-cto` (current technical depth) and `-exec` (grade 5–7 plain language, jargon translated).
3. Gates publication at slop-rubric score ≥ 8.

Source of truth for the team design: this directory plus `private/growth/research/anthropic/marketing-playbooks/ai-slop-avoidance{,-exec-edition}.md`.

## Subagents

| Name | Stage | Tools | Model | Job |
|---|---|---|---|---|
| `pdf-cut-auditor` | 1 (triage) | Read, Grep, Glob, Bash | sonnet | Classify each section value / pitch / hybrid; output structured cut list. No write access. |
| `pdf-rewriter` | 2 (rewrite) | Read, Edit, Write, Glob, Bash | opus | Produce `-cto` and/or `-exec` variant from approved cut list. Writes to new sibling dirs. |
| `pdf-reader` | 3a (persona review, parallel) | Read, Grep | sonnet | Persona-reads the rewrite. CTO = "Marc, Austin SaaS CISO". Exec = "Sarah, Ohio logistics IT director". |
| `pdf-verifier` | 3b (mechanical review, parallel) | Read, Bash, Grep, Glob | sonnet | Banned-phrase scan, citations, Marp lint, Flesch math, rubric score. Gates publication. |

Lead is the user's main Claude Code session. No subagent file for the Lead.

## Output layout

For source `private/growth/dist/<deck>-a4/<deck>.md`:

- `private/growth/dist/<deck>-cto/<deck>.md` + `assets/` copied
- `private/growth/dist/<deck>-exec/<deck>.md` + `assets/` copied

Source `dist/<deck>-a4/` is never overwritten. `build-pdfs.sh` needs to learn the new directory names (separate task).

## Creating the team (one-time)

The team itself is a Claude Code feature, separate from the subagent definitions. To spin it up, paste this into the Lead session:

```
Create an agent team named pdf-pipeline using these subagents:
pdf-cut-auditor, pdf-rewriter, pdf-reader, pdf-verifier.

I am the lead. Require plan approval before the rewriter writes any file.
Use Sonnet for the auditor, reader, and verifier; Opus for the rewriter.
```

The team config will be auto-generated at `~/.claude/teams/pdf-pipeline/config.json`. Don't hand-edit it.

## Per-PDF invocation

Once the team exists, kick off a deck with a single prompt to the Lead:

```
Run pdf-pipeline on private/growth/dist/ransomware-survival-a4/ransomware-survival.md.
Produce both -cto and -exec variants.

Audit first. Wait for my approval on the cut list before rewriting.
```

The Lead will:

1. Spawn `pdf-cut-auditor` with the source path. It reads the playbooks and emits a cut list.
2. Show you the cut list. You approve, redirect, or ask for changes.
3. Spawn `pdf-rewriter` twice — once for `cto`, once for `exec` — passing the audience flag in each invocation prompt.
4. After each variant is written, spawn `pdf-reader` and `pdf-verifier` in parallel against that variant.
5. Direct-message the Rewriter with consolidated revision asks if either reviewer fails.
6. Loop until both gates pass and the rubric score is ≥ 8.
7. Report final file paths and scores.

## Audience flag (how it flows)

Subagents don't take structured arguments. The Lead passes the audience in the natural-language prompt to the Rewriter, Reader, and Verifier:

```
@pdf-rewriter audience=exec — rewrite the approved cut list of
private/growth/dist/ransomware-survival-a4/ransomware-survival.md into
private/growth/dist/ransomware-survival-exec/ransomware-survival.md.
Follow the exec-edition playbook.
```

The Reader and Verifier infer audience from the output path (`*-cto/*.md` vs `*-exec/*.md`) per their system prompts, but the Lead should still state the audience explicitly to remove ambiguity.

## Plan-approval gate

The Rewriter is configured to post a one-paragraph plan before writing any file. The Lead must approve. This is the built-in feedback mechanism that prevents the Rewriter from going off-script on a long deck.

If you want to skip plan approval for a known-good deck (e.g., re-running after a small revision), tell the Lead explicitly: "no plan gate this run".

## When a deck fails

- **Cut Auditor produces a bad cut list.** Edit the list manually, tell the Rewriter to use the edited version, or re-run the auditor with a clarification prompt.
- **Rewriter drifts from voice.** Direct-message it with the specific deviation (e.g., "slide 7 reads salesy — that's what we're trying to remove"). It will revise.
- **Verifier fails gate 4 (reading level) on exec.** Rewriter rewrites the failing slides with shorter sentences and the analogy bank. Repeat until grade ≤ 7.5.
- **Verifier fails gate 7 (rubric) below 8.** Rewriter applies the specific revision asks. Don't ship under 8 — the per-deck checklists set that as the minimum for solution-page-grade content.
- **Reader fails too many slides.** May indicate the cut list was wrong, not the rewrite. Escalate to the Lead for a re-audit.

## Reusability across the 26+ decks

The same four subagents handle every English deck and every NIS2 language variant. The Lead changes one path per run. No per-deck configuration. New decks added to `private/growth/dist/` are automatically eligible the moment they're committed.

The exec-edition playbook is the lever for tuning the `-exec` voice across all decks at once. If a deck-2-onwards review shows the analogy bank is missing a concept, add it to the playbook and the rewriter picks it up on the next run.

## Files referenced by the team

- `private/growth/research/anthropic/marketing-playbooks/ai-slop-avoidance.md`
- `private/growth/research/anthropic/marketing-playbooks/ai-slop-avoidance-exec-edition.md`
- `private/growth/research/anthropic/strategy/brand-voice-messaging.md`
- `private/growth/research/anthropic/strategy/authentic-voice-candor-strategy.md`
- `private/growth/dist/<deck>-a4/slop-review-checklist.md` (when present)
- `private/growth/dist/<deck>-pdf/slop-review-checklist.md` (when present)
- `private/growth/dist/<deck>-a4/<deck>.md` (source)
- `private/growth/dist/<deck>-a4/assets/*` (images)
