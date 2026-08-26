# PLAN: a test advisor, not a longer reggate

Status: done
Owner: b7baf3ee
Updated: 2026-08-26

Header only, by session 9d92d9b6 on 2026-08-26: this plan carried its state as an
inline `· status: BUILT`, which no tool reads, so it listed as `[UNKNOWN]` and was
re-flagged every stop. The design below is UNCHANGED and was not re-litigated. The
`done` is verified, not assumed -- each artifact this plan claims to have shipped
was checked to exist and be wired: `.claude/agents/test-advisor.md`,
`.claude/skills/testing/SKILL.md`, `prove_named_artifact` in
`.claude/hooks/stop/wl_reggate.py`, `outq_add` in `wl_checks.py`, and
`check:ci-skill-size` at `package.json:122`.

## The ask

Per-task CI enforcement in the stop hook, bound to the real `ci.yml`. Operator's
framing, verbatim on the third round:

> I don't want to pick one. We need a general solution. Maybe we should keep open
> an advisor agent in the background each time. He should know the testing
> system. It's better to have a new agent under .claude/agents and add some
> skills. He should also improve himself autonomously. Instead of making larger
> texts, dedicated skills and sharper texts would be better.

Two decisions already settled: only **code-touching ticks** are asked, and haiku
**may override** the session's "not worth it" and must justify it. Blocking is
**one at a time, the rest queued**.

## What is actually broken

`wl_reggate.CHECK_SCRIPT_GLOBS` decides what counts as a gate. It matches
`scripts/check-*.ts`, `packages/*/scripts/check-*.ts`,
`.ci/scripts/quality/check-*.sh`, `.ci/scripts/test/gates/test-*.sh` and the hook
suites. `ci.yml` has **six** regression surfaces and those globs see one of them:

| surface | entry | coverage enforced by |
|---|---|---|
| static gates | `ci-quality.yml` | `check:ci-parity`, gate-reachability |
| E2E on real VMs | `ct-tests.yml` → `run-e2e.sh` (workers, ceph, ceph-workers, k8s, k8s-ceph) | `check-e2e-coverage.sh`, forward AND reverse |
| ops / KVM | `ci-ops-test.yml` (`ops-vm-provision`, `ops-qemu-provision`, `ops-platform-check`) | **nothing** |
| install + update | `ct-install-methods.yml`, `.ci/scripts/test/test-install-*.sh`, `test-rdc-*.sh` | six-platform validation, pre-publish |
| unit | `ct-tests.yml` `test-unit` | — |
| hooks | `.claude/hooks/test-hooks.sh` | `check_test_file_orphans.py` |

`ci.yml:479` already calls `ci-quality.yml`, so "bind to ci.yml" is satisfied for
static gates today. The gap is not wiring. It is that a behavioural fix in the
CLI, in renet, or in provisioning has **no acceptable answer**: the judge will
only take a `check-*.ts`, which is the wrong instrument, so the honest response
to "gate this" is a gate that cannot really cover it.

Enumerating the six in the judge is the fix I proposed and the operator refused,
correctly: the list rots the moment a seventh appears.

## The shape

**1. Skill `.claude/skills/testing/`** — the routing knowledge, one sharp file per
surface, following the `rdc` skill's pattern (a `SKILL.md` routing table plus small
files, not one long document).

```
SKILL.md      "my fix touches X -> its regression home is Y", and how to prove each
gates.md      three-point wiring, control-first, the planted-defect proof
e2e.md        run-e2e.sh, --test to cut 40 min to 60 s, the forward/reverse coverage gate
ops.md        ci-ops-test.yml jobs; the surface with NO coverage gate
install.md    ct-install-methods.yml and the test-install-*/test-rdc-* scripts
unit.md       vitest, and when a unit test is genuinely the right gate
hooks.md      test-hooks.sh, the orphan gate
```

Hard cap **60 lines per file**, enforced (below). The cap is the mechanism, not a
style note: it forces sharpening instead of accretion, which is the failure mode
the operator named.

**2. Agent `.claude/agents/test-advisor.md`** — short. Input: a fix (files, tick
evidence). Output: the surface, a doable/worth verdict, and the exact proof to
produce. It loads the `testing` skill rather than restating it.

**3. Self-improvement with a budget.** After each verdict the advisor may append
one learned line to the relevant surface file. At the 60-line cap it must remove
or tighten a line to add one. A new gate `check:ci-skill-size` enforces the cap,
so unbounded growth fails CI rather than quietly producing the long texts the
operator is objecting to.

**4. Reggate change.** Replace the glob match with the advisor's verdict. Ask once
per code-touching ticked item. Block on the oldest unresolved question only; queue
the rest as `- [?] reggate:<item-id>` with their DEFAULT, which the existing
deferral machinery already drains.

## Decided

**On-demand, not persistent.** Reuse `wl_judge._run_structured`: a haiku call with
a $0.25 budget cap and a recursion guard, warm at $0.011-$0.026. Background agents
died silently four times in one night on the 0804-1 wave, and a dead advisor is
invisible by construction.

**Self-improvement runs through `skill-test-iterate`**, which already exists
(`.claude/skills/skill-test-iterate.md`): a sub-agent does a real task with only
the skill docs, then critiques them. That is a better mechanism than the
append-a-line-per-verdict I first drafted, because the feedback comes from a
reader who did not write them. The 60-line cap stays as the forcing function.

## Not doing

Enumerating surfaces in reggate. Adding a seventh glob. Making the agent file
long enough to hold the routing table itself.


## Built, and the two design conclusions reached while building

Shipped: `a1ec17d9` (the judge names a surface and an artifact path;
`prove_named_artifact` accepts a case on any surface with no glob list, fenced
away from static gates), `43b527ca` (one fix per stop, oldest first,
code-touching ticks only), `3771a92f` (flood guard restored, three controls
repaired), `ccb19e99` (the skill, the agent, `check:ci-skill-size`), `62d69e1d`
(install.md and e2e.md corrected by a real doc test).

**Queued fixes are REPORTED, not turned into worklist items.** The option text
the operator chose said "queue the rest as open worklist items", and building
that would have broken the gate: `apply_regression_verdict` settles any `- [?]`
carrying a `reggate:` token as 'deferred', so auto-creating those lines would
settle the whole queue unasked and turn the mechanism into a no-op. The queue
depth goes out through `outq_add` instead, which is the existing channel for
telling the operator something once.

**The routing stays inline in the judge prompt.** Calling the `test-advisor`
agent from the hook would be a SECOND model call per stop for an answer the one
existing call already produces, and both read the same skill. The agent earns
its place interactively, where a session can ask it and argue back. If the
inline routing starts drifting from `.claude/skills/testing/`, that is the
signal to make the hook call the agent instead.
