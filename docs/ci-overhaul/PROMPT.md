# Session prompt: ci-overhaul

Your mission is to execute the CI overhaul program. Start by reading
`docs/ci-overhaul/README.md` and follow its **Read order**; `01-verified-context.md` first and
in full, including section 8b, which corrects earlier sections.

**Validation ethos.** Every `file:line` in that suite is a hypothesis by the time you read it,
so re-verify what you depend on and run the real command rather than trusting a written
number. Plant a control before trusting any zero: this program exists because three separate
mechanisms that looked healthy turned out never to have fired.

**Ask the nine operator decision points early, in one round**, using the RECOMMENDED defaults
in `04-decisions.md` section C. Anything unanswered takes its default and gets logged. There
are also two cheap spikes in `05-execution-guide.md` to run before committing to the designs
that depend on them.

**Staffing.** Opus is the default for coding sub-agents. **Fable for the challenging pieces
and for all planning agents.** Sonnet for translation and naturalisation. At most **2
concurrent writers**, with disjoint file ownership stated verbatim in every prompt;
investigation agents may fan out freely. Spot-check every sub-agent report against the
artifact before building on it, because in the source session three of five verification
sweeps corrected the orchestrator on load-bearing claims. The Fable-tier pieces are named in
the README's Staffing section: the baseline-and-net-delta engine, the attested skip-plan
reconciliation, the D5 content hash, and the autopilot harness.

**Program state** lives at
`~/.claude/projects/-home-muhammed-monorepo-console/programs/ci-overhaul/`. Update
`MANIFEST.md` at every wave boundary. Every writing or planning sub-agent names its working
report `reports/<phase>-<agent>.md` (and its brief `reports/<phase>-<agent>-brief.md` when one
is used); read those reports and the artifacts, never bare summaries. Drop periodic
uncommitted-tree patches into `checkpoints/`, because a host reboot once destroyed a `/tmp`
scratchpad and that is why this directory is durable.

**Worklist.** Seed it at session start; get the path with
`.claude/hooks/stop/worklist.py --path`. One `- [ ]` item per wave, each tagged with your
session-id prefix. Park deferred decisions as `- [?]` so they are reported to the operator on
every stop. Hold background delegation as `- [>] (prefix) until:<ISO>Z`, renewing the lease
when you wake. Only tick an item after probing the artifact.

**Everything stays local and uncommitted** unless the operator asks in-task, with one
exception: this program is explicitly authorised to run the full branch, PR, babysit and merge
flow described in `05-execution-guide.md`, across three sequenced merges from a single
approval. Never push `main`, never merge unasked, never force-push, never suppress a gate.

**Testing is a first-class deliverable**, not a follow-up. The testing pillar in
`02-v1-economics.md` section B6 is part of Wave B, and every new gate must be registered in
`test-gate-anti-vacuity.sh` and proven to fire.

**Autonomy boundary.** Run the flow autonomously and keep moving. Reserve questions for
decisions that are genuinely critical: something irreversible outside the PR, a product
behaviour change where intent is unclear, or a gate you believe is itself wrong. Log every
other judgement call under a `DECISIONS` heading for post-hoc veto.

**No em dashes in any authored text, in any language.**

**Definition of done** is in `05-execution-guide.md`. In short: the nightly is genuinely green
and its failures are visible; `pointer_bump_only` has been observed **true** at least once
after never having been true; the skip-plan reconciler has been proven to fail on a planted
mismatch; and you can state, with a run id, how much a normal round now costs against the
measured 73-minute baseline.
