# CI overhaul: economics, correctness, and eventual autonomy

This suite is the durable handoff from the 2026-07-27 discovery session that started as
"make CI shorter" and turned into a measurement exercise. It carries everything found,
including nine defects and twelve findings, the scored options, the operator's locked
decisions, and a full design for both halves of the work. Nothing in it has been built.

Memory pointer: `project_ci_overhaul.md` in the auto-memory index.
Program state: `~/.claude/projects/-home-muhammed-monorepo-console/programs/ci-overhaul/`
(`MANIFEST.md`, `reports/`, `checkpoints/`).

**The one-paragraph summary.** The obvious plan (skip CI jobs when their module did not
change) was measured twice and fires on 5 to 7 percent of real PRs, cutting the expensive E2E
fleet on **zero of forty**. Scoping the diff to the last *green* commit instead of the merge
base takes that to **30 percent**, which is where the babysit loop's pain actually lives. On
the way, the pointer-bump fast path was found to have **never fired once**, the nightly to
have been **red for four consecutive nights** with its failures laundered into `cancelled`,
and coverage to be an instrument nothing reads. The plan is therefore: repair the backstop,
fix the engine that was already supposed to do this, take the policy wins that apply to every
run, and only then hand the keys to an agent.

---

## Read order

1. **[01-verified-context.md](01-verified-context.md)** first, always. Every measurement and
   every defect, with `file:line` and run ids. Section 8b corrects earlier sections; trust 8b.
2. **[02-v1-economics.md](02-v1-economics.md)** for PR-A and PR-B.
3. **[03-v2-autonomy.md](03-v2-autonomy.md)** for PR-C. Read walls 1 to 5 before designing
   anything; wall 4 is the dangerous one.
4. **[04-decisions.md](04-decisions.md)** for what is locked, what is open, and the scored
   ledger. Ask the open decision points early, in one round.
5. **[05-execution-guide.md](05-execution-guide.md)** last, when you are ready to move.

---

## Non-negotiable working ethos

**Validate, do not believe.** Every `file:line` reference in this suite is a hypothesis by
the time you read it. Re-verify against the tree before relying on it. Run the real thing;
read stdout and stderr separately. **Plant a control before trusting any zero.** This suite
exists because three separate "working" mechanisms turned out never to have fired.

**Everything stays local and uncommitted** unless the operator asks in-task. Never
`git checkout`, `restore`, `stash` or `clean` to undo your own mistake; repair forward. The
tree routinely holds other sessions' work.

**Testing and concurrency support are first-class deliverables**, not follow-ups.

**No em dashes in any authored text, in any language.**

**A workaround is a bug report.** If you route around something, say so with the exact
command and the exact output.

---

## Staffing

- **Opus** is the default for coding sub-agents.
- **Fable for the challenging pieces and for all planning agents.**
- **Sonnet** for translation and naturalisation work.
- **At most 2 concurrent writers**, with disjoint file ownership stated verbatim in every
  prompt. Investigation agents may fan out freely.
- Every sub-agent report is **spot-checked against the artifact** before anything builds on
  it. In this very session, three of five verification sweeps corrected the orchestrator on
  load-bearing claims.

**Fable-tier pieces, named:**
1. The **baseline-and-net-delta engine** (02 section B1). It is the keystone, it merges two
   mechanisms, and getting the base-moved case wrong silently weakens CI.
2. The **attested skip-plan reconciliation** (02 section B2, finding F11). Caller-level
   assertions are structurally blind here; the reconciler is the only thing that is not.
3. The **D5 content hash** (02 section B3). Under-inclusion causes stale image reuse, and the
   renet-pointer trap is subtle.
4. The **autopilot harness** `autopilot-push.sh` (03). It is a security boundary. Keep it
   tiny and boring.

---

## Scope

**Wave A (PR-A, ~400 lines).** Resurrect the nightly and repair the watchdog that hides its
failures. Merge first; prove green before anything in Wave B ships.

**Wave B (PR-B, ~2.6 to 3.2K lines).** The baseline engine and incremental scoping (fixing
D9 in the same stroke), the attested skip-plan, the policy cuts, the defect sweep D3 to D7
plus D10, the four in-scope issues, the testing pillar, labels, metadata and milestones.

**Wave C (PR-C, ~1.5 to 2.5K lines).** The autopilot, landing with every stage flag off.
Enable stages only after Wave B has been observed on real traffic.

### Explicitly OUT

- **Merge queue.** Feasible on console, deliberately not now. See 04 section D.
- **GitHub Projects v2.** Needs a long-lived org credential; the operator has ruled out PATs.
  Replaced by sub-issues.
- **GitHub Discussions** as a decision database. Replaced by `docs/adr/`.
- **Agent-authored `.github/workflows/**` edits.** Dropped permanently.
- **E2E matrix 5-to-2 reduction.** Wall-neutral; revisit only if concurrency binds.
- **`#533` compose-stack consolidation.** Product-stack design, not CI economics.
- **The intra-quality serial gate chain.** Separate project.
- **Buying GitHub Team.** It does not sell what was wanted.

---

## Operator decision points (ask EARLY, in one round)

Full text and rationale in [04-decisions.md](04-decisions.md) section C. Summarised, with
defaults:

1. **D-1 Detection live or shadow?** RECOMMENDED: live, but only behind the attested
   skip-plan reconciler; fall back to shadow if the reconciler slips.
2. **D-2 `/handoff` report root?** RECOMMENDED: adopt `programs/<slug>/` as specified, with
   babysit round logs in a sibling `babysit/` namespace.
3. **D-3 #533 debug-box target stack?** RECOMMENDED: answer in the issue, defer the work.
4. **D-4 #537 classifier fallback?** RECOMMENDED: allowlist-only retry, plus capture the log
   before re-running.
5. **D-5 #534 detector approach?** RECOMMENDED: fix the rule and BLOCKER-allowlist the
   survivors.
6. **D-6 Submodule draft PRs: how do they flip ready?** RECOMMENDED: gate on the console PR's
   green.
7. **D-7 `strict_required_status_checks_policy`?** RECOMMENDED: on.
8. **D-8 Merge queue: dropped or live option?** RECOMMENDED: live option, documented design.
9. **D-9 The two dead `deploy-preview` inject steps?** RECOMMENDED: delete them.

There are also two **spikes** to run before committing to designs, listed in
[05-execution-guide.md](05-execution-guide.md).
