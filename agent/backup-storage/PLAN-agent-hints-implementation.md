# PLAN: agent hints in the stop hook, implementation

Status: READY TO IMPLEMENT. Design step for the operator's request "add new agents, then
improve the stop hook to hint at them depending on context".
Owner: 97604f47
Updated: 2026-08-15
Supersedes the design half of `PLAN-agent-hints-in-stop-hook.md` (that file's investigation
half stands; its section 6 matcher and section 1 numbers are corrected below by measurement).

Every `file:line` in this document was read this session. Anything not verified is labelled
HYPOTHESIS.

---

## 0. The verdict, in one paragraph

Ship a deterministic matcher over the agent frontmatter `description` field, scored by set
intersection over tokenised terms, delivered through the existing `outq_add` advisory queue
on the allow path plus one block on `PostCompact`. The corpus is **descriptions only**:
bodies were prototyped this session and made the matcher measurably **worse**, and the
reason is structural rather than a tuning accident (section 2). The bench gap that prompted
this whole request is fixed by **sharpening three descriptions**, not by widening the
corpus, and that fix is measured: the bench query goes from silent to a top hit at 7.0
against a runner-up of 1.0. Final measured configuration on a 17-case table:
**12 true positives, 0 misses, 0 false positives, 1.4 ms per stop.**

---

## 1. Corrections to the inputs I was given

Both investigations were substantially right. Four things need correcting before anyone
builds from them.

| claim | status |
|---|---|
| "modelled on `.ci/scripts/quality/lint-rule-liveness.mjs`" | **Half wrong, and it matters for registration.** The `.mjs` is a *driver*. The thing registered in `package.json:97`, `scripts/ci-runner/manifest.ts:152`, `.github/workflows/ci-quality.yml:760-762` and the anti-vacuity registry is `.ci/scripts/quality/check_lint_rule_liveness.py`. Underscores, not hyphens. The new gate must follow the Python entry-point naming or it will not match its siblings. |
| proposed gate filename `check-agent-hint-liveness.py` | **Wrong shape.** Every Python gate in `.ci/scripts/quality/` uses underscores (10 of 10, verified by `ls`). Use `check_agent_hint_liveness.py`. |
| proposed `leaves: ['.ci/scripts/quality/check-agent-hint-liveness.py']` | Correct in principle, and `check_lint_rule_liveness.py:57-64` carries an explicit warning learned the hard way: `leaves` is a DERIVED field validated at `scripts/check-ci-parity.ts:488-495` against what the `package.json` command resolves to. One file in, one file declared. Do not add a driver to it. |
| matcher scored by "a regex per term against the haystack" | **Superseded.** Measured at 17.4 ms. Tokenising the haystack once and intersecting sets gives byte-identical verdicts at **1.4 ms**, and removes the `read`-matches-`README` bug class by construction rather than by remembering a lookaround (section 3). |

Two claims I re-verified and confirm:

- `wl_judge.py:20` sets `JUDGE_MODEL = claude-haiku-4-5-20251001`; `:21-22` records measured
  cost `$0.011-$0.026` at `4.9-20.0s`; `:33-39` records the timeout raised 120 to 240 after a
  live timeout **blocked a stop**. A second per-stop model call is refused on this evidence.
- The word "bench" appears **zero** times across all seven agent `description` fields and
  exactly once in the whole directory: `.claude/agents/account-dev.md:81`, in the body. The
  knowledge existed; the matching surface did not.

---

## 2. The corpus: descriptions only. Bodies were tested and rejected.

This was the open question, so I measured it instead of arguing it. Three corpus variants,
same scorer, same 17-case table (12 cases with an intended agent, 5 neutral controls).

| variant | TP | MISS | FP |
|---|---|---|---|
| A. descriptions only, current descriptions | 4 | 8 | 0 |
| B. descriptions + body terms at 0.5 weight | 4 | 8 | **1** |
| C. descriptions only, **sharpened** descriptions | 10 | 2 | 0 |
| D. C, with margin 1 instead of 2 | 11 | 1 | 0 |
| E. D, with 3-character words admitted | **12** | **0** | **0** |

**Bodies bought nothing and cost a false positive.** Variant B did not rescue a single case
that A missed. It fired `pr-babysitter` at 2.5 on the neutral haystack "update CLAUDE.md
session defaults and the worklist stop hook docs", on the terms `claude`, `claude.md`,
`hook`, `stop`, `update`, which is exactly the wallpaper failure mode.

The mechanism is worth writing down, because it is not a tuning problem and no weight fixes
it. A first, naive body variant (bodies pooled into the same term set before the
discriminative filter) scored *worse still*: `account-dev` fell from 6.0 to 0.4 on its own
strongest query. The high-value description terms `gateway`, `portal`, `run.sh`, `test_mode`
were **deleted** from its term set, because those words also appear somewhere in another
agent's 33 KB body, so the "appears in exactly one agent" filter stripped them. Bodies do
not add signal to a discriminative matcher, they **destroy** it: every word a long body
mentions in passing is a word that stops discriminating. Variant B above is the repaired
form (discriminate over descriptions only, add body terms as a separate low-weight bonus),
and even repaired it is a net negative.

The corpus sizes make the asymmetry concrete: descriptions yield 27 to 59 discriminative
terms per agent; bodies yield 118 to **734**. `pr-babysitter.md` is 33 KB and
`media-pipeline.md` is 23 KB, so the two largest bodies would dominate any body-weighted
scheme regardless of what the session is doing.

**How the bench case is made to fire, then.** By putting the nouns in the description, where
the matcher can see them (section 6). Measured, sharpened, descriptions-only:

```
"there is bench server deployment, deploy the account worker to bench and reset the D1"
  before:  top = 1.0  pr-babysitter        -> silent
  after:   top = 2.0  account-dev          -> fires, next 0.0
"the wrangler deploy to bench.rediacc.com failed, check the worker secrets"
  after:   top = 7.0  account-dev          -> fires, next 1.0
```

**Falsification test for this decision** (belongs in the gate, section 5): the
`bench` regression specimen must fire for `account-dev` above threshold and margin, AND the
five neutral controls must stay silent, in the same run. Variant B fails that pair. If a
future session wants bodies back, that table is the thing to beat, and re-running the
prototypes in this plan's section 9 is how.

---

## 3. The matcher

New module `.claude/hooks/stop/wl_agents.py`. Pure functions, no writes, one directory read.
Separate module because `wl_checks.py` is already 179 KB and because the CI gate imports the
scorer directly (precedent: `.ci/scripts/quality/check_gate_reachability_coverage.py:66`
already does `sys.path.insert(0, HOOK_DIR)` to import a hook module).

### 3.1 Frozen public API

Both writers depend on this, so it is frozen here and neither invents it.

```python
TERM = tuple            # (kind, text); kind is "path" | "word"

def load_corpus(agents_dir):
    """-> ({name: {"desc": str, "path": Path, "terms": {TERM: float}}}, [error_str])
    Errors are RETURNED, never raised and never swallowed: a file with no
    `name:` or no `description:` in its frontmatter is an error entry, not a
    silent skip."""

def discriminative(corpus):
    """-> {name: {TERM: float}} keeping only terms that occur in exactly one
    agent's description. The agent's own name is always retained at weight 3."""

def tokenize(text):
    """-> {TERM}. The SAME function used for descriptions and for haystacks."""

def score(haystack, uniq):
    """-> [(score: float, name: str, hits: [str])] sorted descending."""

def best_hint(haystack, uniq, min_score, min_margin):
    """-> (name, score, hits) or None."""
```

`tokenize` being shared between corpus and haystack is load-bearing, not tidiness: it is
what makes scoring a set intersection, and a set intersection is what makes the substring
bug impossible.

### 3.2 Tokenisation

```python
PATH_RE = re.compile(r"[A-Za-z0-9_-]*(?:[./][A-Za-z0-9_-]+)+")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
```

- **path terms**: matched by `PATH_RE`, lowercased, leading `./` stripped, kept when longer
  than 5 characters. Weight **3**. These are the high-value ones and they sit verbatim in
  the descriptions already: `./run.sh`, `scripts/dev/deploy-bench.sh`, `bench.rediacc.com`,
  `packages/www`.
- **word terms**: matched by `WORD_RE`, lowercased, minus a stopword list. Weight **1**.
- **The `{2,}` is deliberate and measured.** A `{3,}` minimum (4 characters total) is what
  the earlier prototype used, and it silently discards `ops`, `rdc`, `d1`, `r2`, `vm`, `k3s`,
  which are among the most discriminative tokens this repo has. Admitting 3-character words
  is what took the table from 11/1/0 to **12/0/0**; the case it rescued was
  `"rdc ops up --basic"`, which is a phrase the operator actually types. The stopword list
  carries the cost.
- **Stopwords**: the usual closed-class English set plus `run/runs/running`, `work/works`,
  `make/makes`, `use/used/using`, `new/old`, `need/needs`. Kept in `wl_agents.py` as a module
  constant so the gate sees the same list the hook does.
- The agent's own `name` is injected as a word term at weight 3, so "ask the i18n-guardian"
  matches even when the prose shares nothing else.

### 3.3 Discrimination

Keep a term only when it appears in **exactly one** agent's description. With 7 to 8
documents this is a cheaper and sharper substitute for IDF, and it is what stops `config`,
`session`, `gate` and `repo` from ever triggering anything.

Recomputed from disk on every stop. This is what makes "a hint pointing at a deleted agent"
structurally impossible rather than a thing to remember: if the file is gone, the name is
not in the corpus.

### 3.4 Scoring, ties, near-misses

```python
hits = agent_terms.keys() & tokenize(haystack)
score = sum(agent_terms[t] for t in hits)
```

Fires only when **both** hold:

- `score >= WORKLIST_AGENT_HINT_MIN_SCORE` (default **2**)
- `score - runner_up >= WORKLIST_AGENT_HINT_MIN_MARGIN` (default **1**)

**Ties are silence, by construction**: a tie makes the margin 0, which is below any positive
threshold, so no hint is emitted and no tie-break rule is needed. Never break a tie by name
order, corpus order, or file mtime; a tie means the evidence does not distinguish two
specialists, and inventing a winner is how a matcher starts lying.

**Near-misses are silence too, and are not logged.** A "you almost matched X" line is a hint
with extra words. If a domain repeatedly scores just under threshold, the correct response is
to sharpen that agent's description, and the gate is what surfaces it.

**On margin 1 versus margin 2.** Margin 2 was the earlier proposal. Margin 1 is better here
and the risk it appears to carry does not materialise, which I checked specifically because a
1-point margin on a long noisy haystack is exactly where a matcher gets loose. Against five
realistic composite haystacks (brief + open items + last assistant message + changed paths,
about 500 characters each, the shape the stop path actually assembles), all four threshold
settings I tried gave **identical** verdicts, because a real match pulls far away:

```
account-dev composite:      top 20.0, next 1.0
backup-storage composite:   top 20.0, next 4.0
neutral cleanup composite:  top  1.0, next 1.0   -> silent
adversarial hook-work one:  top  2.0, next 2.0   -> silent (margin 0)
```

The adversarial case is the reassuring one: a session doing *this* work, whose text is full
of `.claude/agents`, corpus, matcher, gate, manifest, stays silent because it looks equally
like two agents. Longer haystacks separate a true match rather than blurring it. The
thresholds are not knife-edge on realistic input; the one-line specimens are the sensitive
case, which is why the gate's specimens are one-liners (section 5).

### 3.5 Cost

Measured on this machine today, 50 iterations, full load-parse-discriminate-score against a
6 KB haystack and the real 7-file corpus:

| implementation | per stop |
|---|---|
| regex per term (earlier proposal) | 17.4 ms |
| **tokenize once, set intersection** | **1.4 ms** |

Identical verdicts, verified by re-running the whole case table through both. Against a judge
call at 4.9 to 20.0 seconds this is free. No caching: caching 1.4 ms would be an optimisation
of nothing, and a cache is what would let a deleted agent keep being recommended.

### 3.6 Environment knobs

Following the `WORKLIST_*` convention at `wl_checks.py:36-63`.

| var | default | meaning |
|---|---|---|
| `WORKLIST_AGENTS_DIR` | `hook_repo_root()/.claude/agents` | corpus location; the seam the suite and gate point at fixtures. Precedent: `WORKLIST_REPORTS_DIR`, exported by the suite at `test-worklist-v5.sh:102` for exactly this reason |
| `WORKLIST_AGENT_HINT` | `on` | `off` kills the feature. Precedent: `WORKLIST_JUDGE` (`wl_judge.py:40`) |
| `WORKLIST_AGENT_HINT_MIN_SCORE` | `2` | |
| `WORKLIST_AGENT_HINT_MIN_MARGIN` | `1` | |
| `WORKLIST_AGENT_HINT_REFRESH_MIN` | `720` | per-agent re-show window |
| `WORKLIST_AGENT_HINT_MAX_PER_SESSION` | `3` | hard cap across all agents |

Corpus root resolves via `C.hook_repo_root()` (`wl_core.py:357-371`), not `project_root`:
`.claude/agents` is a sibling of `.claude/hooks/stop`, and `hook_repo_root` is immune to cwd
by construction (its own docstring says so).

---

## 4. Delivery, and what stops it becoming noise

### 4.1 Not `vadd`

`vadd` (`wl_checks.py:2234`, 46 call sites) blocks the stop. A hint is advice. Blocking a
session for not consulting a specialist is the fastest possible way to get this feature
switched off, and it would compete for the single focused slot with real violations.

### 4.2 `outq_add`, priority 3

One call, placed with the other advisory producers on the full allow path at
`wl_checks.py:3563-3644`, immediately after the `_quiet_min` block and before
`outq_drain` at `:3646`.

```python
outq_add(worklist, session_id, state_doc,
         "agent-hint:%s" % name, M.N_AGENT_HINT % (name, name, ", ".join(hits[:6])),
         3, refresh_min=AGENT_HINT_REFRESH_MIN)
```

Wrapped in `try/except Exception`, copying the comment style of `_quiet_min` at
`wl_checks.py:3565-3567` ("an advisory note must never wedge a stop"). An advisory that can
wedge a stop is a worse bug than the silence it fixes.

`outq_add` already provides, for free, every rate limit this feature needs (verified by
reading `wl_checks.py:1142-1222` and `outq_drain` at `:1223-1240`):

- a `shown` ledger keyed by section key with a refresh window,
- **one section released per stop** (`OUTQ_PER_STOP = 1`, `wl_checks.py:1105`),
- a `+N more` tail on truncation, mandatory per the comment at `:3641-3645`,
- persistence on every call, so a hint queued before a block survives the block.

Priority **3** puts it behind every existing advisory (backoff and orphans use 2), so a hint
can never displace a real report section. Combined with `OUTQ_PER_STOP = 1`, a hint is only
ever emitted on a stop that has nothing more important to say. That is the single most
important noise control in this design and it costs nothing to obtain.

Per-agent key plus the 720-minute refresh window means the same agent cannot be suggested
twice in 12 hours. `state_doc["agent_hints"] = {name: stamp}`, saved through the existing
`S.save_state` (`wl_store.py:330`), enforces `MAX_PER_SESSION = 3` and gives the suite
something to assert against.

**Allow path only, deliberately.** A blocked session already has something more urgent being
said to it every stop. The trade is that a session that never reaches a clean stop never gets
hinted, which is acceptable for the same reason.

### 4.3 PostCompact

In `handle_post_compact` (`wl_checks.py:1471`), after the checklists block is appended at
`:1541-1543` and before `C.emit` at `:1544-1553`, append the hint when the matcher fires
against the compacted session's STATE.md body and open items. Once per compaction by
construction, no rate limiting needed, three lines of code.

This is the highest-value delivery in the design. Post-compaction is precisely when a session
has forgotten that a specialist exists, and `additionalContext` is read rather than skimmed.

### 4.4 Wording

New constant in `worklist_messages.py`, placed in the notes section beside `N_JUDGE_STAMP`
(around `:889`), respecting that file's contract of named `%`-format constants with no logic:

```python
N_AGENT_HINT = (
    "Specialist agent available: %s (.claude/agents/%s.md).\n"
    "  Matched on: %s\n"
    "  It carries knowledge this session would otherwise rediscover. Spawn it with the\n"
    "  Agent tool, or ignore this line if it is not the domain you are in."
)
N_AGENT_CORPUS_ERR = (
    "Agent corpus problem (specialist hints are degraded until fixed):\n%s"
)
```

Naming the matched terms is what makes a wrong hint self-refuting: a reader who sees
`Matched on: fork, cap` dismisses it in one second instead of opening a 9 KB file. It is also
what makes the feature debuggable in the field without a flag.

---

## 5. The control: `.ci/scripts/quality/check_agent_hint_liveness.py`

Non-negotiable, and modelled on the repo's canonical shape. `check_lint_rule_liveness.py`
exists because five enabled lint rules **could not fire, ever**, while the repo read their
silence as compliance (its docstring, `:4-10`). A matcher that goes quiet is the same defect
wearing the same disguise: a healthy corpus on a quiet stop looks exactly like a dead matcher.

Registration, matching its siblings exactly:

| where | entry |
|---|---|
| `package.json` scripts | `"check:ci-agent-hint-liveness": ".ci/scripts/quality/check_agent_hint_liveness.py"` |
| `scripts/ci-runner/manifest.ts` | new entry beside `:152`, shape below |
| `.github/workflows/ci-quality.yml` | new step in job `quality-content`, beside `:760-762` |
| `.ci/scripts/test/gates/test-gate-anti-vacuity.sh` | registry line beside `:121` |

```ts
{ id: 'check:ci-agent-hint-liveness', run: 'npm run check:ci-agent-hint-liveness',
  gate: true, leaves: ['.ci/scripts/quality/check_agent_hint_liveness.py'],
  ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml',
        job: 'quality-content', step: "Agent hints can actually fire" } },
```

```yaml
      - name: Agent hints can actually fire
        if: ${{ !cancelled() && steps.setup.outcome == 'success' }}
        run: .ci/scripts/quality/check_agent_hint_liveness.py
```

`leaves` holds exactly the one path `package.json` resolves to. `check_lint_rule_liveness.py:57-64`
records what happens otherwise: `scripts/check-ci-parity.ts:488-495` compares the declared
list against the resolved one and reports a hygiene finding on any difference.

### 5.1 What it asserts

**a. Universe equality, both directions.** The specimen table's key set must equal
`{p.stem for p in agents_dir.glob("*.md")}`.

- an agent with no specimen: `UNPROVEN: <name> has no specimen`, exit 1
- a specimen for a missing agent: `STALE SPECIMEN: <name> has no agent file`, exit 1

This is the assertion that carries the feature. It makes "prove your new agent is reachable"
a build requirement rather than a good intention, and it is the one that will actually fire
in six months when someone adds an eighth agent.

**b. Every specimen fires for its own agent**, as the top match, above `MIN_SCORE` and
`MIN_MARGIN`, using the same defaults the hook uses (imported from `wl_agents`, never
re-declared, or the gate proves a configuration nothing runs).

Three distinct verdicts, because they have three different fixes:

| verdict | meaning | fix |
|---|---|---|
| `DEAD` | scored below `MIN_SCORE` | the description lacks the nouns people type |
| `CROSS-MATCHED to <other>` | scored, but another agent won | two descriptions overlap; sharpen one |
| `AMBIGUOUS (margin N < M)` | won, but not by enough | same, and it is the near-miss the matcher deliberately will not report at runtime |

**c. Negative controls, inline on every invocation, never behind a flag.** Copying
`check_lint_rule_liveness.py:83-85` ("the controls are not a separate mode, they run inline;
a control you have to remember to run is how a control stops controlling anything"). Minimum
five, and the exact five measured in section 2:

```
"fix a typo in the README"
"update CLAUDE.md session defaults and the worklist stop hook docs"
"rename a variable in packages/shared and rebuild the dist output"
"the test suite has one failing assertion, find it and fix it"
"bump the eslint version and re-run the linter"
```

If **any** control fires, the gate refuses to issue a verdict at all and exits non-zero, the
way `lint-rule-liveness.mjs` does for its own controls. "The controls passed because
everything is silent" is separately excluded by (b), which is the pairing that makes this a
real control rather than two half-tests.

**d. The bench regression case, named as such.** A specimen carrying a `regression:` marker
and a comment pointing at this plan:

```python
# REGRESSION 2026-08-15. "bench" appeared ZERO times in any agent description and
# once in account-dev's BODY (account-dev.md:81). The knowledge existed and the
# matching surface did not, so the operator had to hint by hand. If this specimen
# stops firing, someone has removed the bench nouns from the description again.
"account-dev": "there is bench server deployment, deploy the account worker to bench and reset the D1",
```

**e. Anti-tautology.** A specimen must not be a verbatim substring of its agent's
description, and must be at most 200 characters. Without this the lazy specimen is "paste the
description in", which proves that a string matches itself. Enforce it and fail with
`TAUTOLOGICAL SPECIMEN: <name>`.

**f. Vacuity refusal.** With an empty or absent agents directory, print
`VACUOUS INPUT: no agent files under <dir>, so no hint can be proven` and exit non-zero,
before any scoring. Then register it in `.ci/scripts/test/gates/test-gate-anti-vacuity.sh`
beside its siblings (registry entries at `:100-121`, the same shape as
`".ci/scripts/quality/check_lint_rule_liveness.py|VACUOUS INPUT"`), so a renamed agents
directory cannot silently retire the whole feature.

A second precondition in the same block: `wl_agents.py` must be importable. Against the
anti-vacuity harness's empty-tree fixture the hook directory does not exist, and an unguarded
import would die with `ModuleNotFoundError`, a non-zero exit for an environment reason
wearing a vacuity failure's exit code. `check_lint_rule_liveness.py:50-56` documents that
exact trap for its own `import('eslint')`. Check the path before touching `sys.path`.

### 5.2 Specimen table, all eight agents

Each is one line, none is a description substring, each is phrased the way a session would
actually state its task.

```python
SPECIMENS = {
  "account-dev":     "there is bench server deployment, deploy the account worker to bench and reset the D1",  # regression
  "ops-vms":         "spin up the fleet of VMs for the bridge test and check hypervisor status",
  "backup-storage":  "the restore drill fails on round-trip verification of a snapshot",
  "i18n-guardian":   "German locale file has Arabic values, re-run naturalize for the www translations",
  "licensing-ops":   "license activation cap wrong after a fork, re-metering the datastore",
  "media-pipeline":  "regenerate the tutorial narration, the captions drift by two seconds",
  "pr-babysitter":   "push the branch and watch CI until every job is green, flip the PR ready",
  "config-universe": "rdc config remote enable fails with Decryption failed after the passkey unlock",
}
```

All eight verified to fire correctly this session against the sharpened corpus at
`MIN_SCORE=2, MIN_MARGIN=1`, with all five controls silent.

---

## 6. The agent changes

Descriptions are the matching surface, so they are written as one: concrete nouns a future
session would type, not a summary of the file. Every added noun below is a token the matcher
can key on.

### 6.1 New agent `.claude/agents/backup-storage.md`

Frontmatter, `description` exactly as measured:

```yaml
---
name: backup-storage
description: The backup and restore stack: the content-addressed chunk store and its index and manifest format, dedup and compaction, snapshot creation and pruning, retention and quota policy, the rdc backup and rdc datastore CLI verbs, scheduled backups and their systemd units, cold-backup runs, restore and disaster-recovery drills including round-trip verification, and remote backup targets (R2, S3, OneDrive) with their upload budgets. Use for work on backup, restore, snapshot, chunk store, retention, prune, or datastore storage accounting, or when a backup verification or restore drill fails.
tools: Bash, Read, Edit, Write, Grep, Glob
model: opus
---
```

Measured behaviour of this description against three phrasings, all firing cleanly with a
runner-up of 0.0:

```
"add a retention quota to the backup chunk store and wire the CLI verb"      -> 5.0
"the restore drill fails on round-trip verification of a snapshot"           -> 5.0
"refactor the chunk-store index writer, add a unit test for the manifest"    -> 4.0
```

Note the third: before this agent existed, that sentence was one of the *negative controls*,
scoring 0 across the entire corpus. That is what a genuine coverage gap looks like from
inside the matcher, and it is the observation the earlier investigation made and correctly
declined to build a feature on.

**The body is a separate, non-urgent job.** It is not the matching surface, so it does not
gate this change. Seed it from `docs/backup-storage/01-verified-context.md`, `02-design.md`
and `03-implementation-map.md`, which already exist. HYPOTHESIS: those three carry enough
verified material for a useful body; I did not read them this session.

### 6.2 `.claude/agents/account-dev.md`

Keep the existing description and insert this sentence before the final "Use when" clause,
then extend that clause:

> Also the bench environment (bench.rediacc.com): deploying the account worker with
> `scripts/dev/deploy-bench.sh`, wrangler deploys, Cloudflare D1 databases and R2 buckets,
> worker secrets, and `reset-bench.sh` wipes.

and the closing clause becomes:

> Use when a task needs a live account server **or a bench deploy**: license/subscription
> flows, config-storage work, portal testing, drills, **D1 or wrangler trouble,** or
> diagnosing gateway weirdness.

New matchable tokens: `bench`, `bench.rediacc.com`, `scripts/dev/deploy-bench.sh`,
`wrangler`, `cloudflare`, `reset-bench.sh`, `buckets`, `secrets`, `deploy`.
Measured effect: the bench query goes from **silent** to **2.0 with runner-up 0.0**, and the
wrangler query to **7.0 with runner-up 1.0**.

### 6.3 `.claude/agents/ops-vms.md`

Keep the existing description and extend only the closing clause:

> Use when a task needs live machines **or a fleet of them**: bridge tests, licensing drills,
> cluster/ceph work, **hypervisor or libvirt trouble,** or diagnosing why `ops up` failed.

New matchable tokens: `fleet`, `hypervisor`, `libvirt`.
Measured effect: `"spin up the fleet of VMs for the bridge test and check hypervisor status"`
goes from silent to **4.0 with runner-up 1.0**.

### 6.4 What I deliberately did not change

The other five descriptions all fire correctly on their specimens as they stand
(`i18n-guardian` 2.0, `licensing-ops` 3.0, `media-pipeline` 3.0, `pr-babysitter` 5.0,
`config-universe` 2.0 at margin 1). Editing a description that already works risks the
overlap problem in section 2 for no gain. `config-universe` is the thinnest at margin 1 and
is the first candidate if a future session wants more headroom.

---

## 7. Suite cases for `test-worklist-v5.sh`

House style verified this session: `setup` at `:48-109` resets every knob and exports
`WORKLIST_REPORTS_DIR="$BASE/reports"` at `:102` for exactly the hermeticity reason this
feature needs; `check <label> <expect-decision> <must-contain>` at `:441-457`; judge off by
default (`JUDGE_MODE=off` in `setup`) and `$BASE/binonly` holds no `claude`, so no case can
reach the network. The CI wrapper asserts only `failed == 0 && passed >= 1`
(`.ci/scripts/test/gates/test-worklist-hooks.sh:68-84`), so there is no assertion count to
update.

Add to `setup`, beside the `WORKLIST_REPORTS_DIR` export:

```bash
    mkdir -p "$BASE/agents"
    export WORKLIST_AGENTS_DIR="$BASE/agents"
```

and a fixture helper beside `say`:

```bash
mk_agent() { # mk_agent <name> <description>
    printf -- '---\nname: %s\ndescription: %s\ntools: Bash\nmodel: opus\n---\nbody text\n' \
        "$1" "$2" >"$BASE/agents/$1.md"
}
```

Pointing the corpus at a fixture is mandatory, not tidiness: without it every case scores
against the operator's real `.claude/agents`, and the suite's verdicts change whenever an
agent description is edited.

| # | claim | assertion |
|---|---|---|
| A | a matching open item produces the hint on an allow stop | `check` expects `allow` and needle `Specialist agent available: fixtureagent` |
| A-CONTROL | neutral text on the same fixture produces no hint | **positive presence check first** (assert the stop emitted its normal content), then `! grep -qF "Specialist agent available"`. A bare negative passes vacuously if the feature is deleted; the suite documents that exact trap at `:9650-9658`, where a mutation suppressing a whole block made an absence-only assertion PASS |
| B | the hint never blocks | fixture that would otherwise stop cleanly; decision must be `allow` with a hint queued |
| C | a tie is silence | two fixture agents with identical descriptions; both score equally; no hint, no error |
| D | rate limit: twice is once | two consecutive stops, identical evidence; count occurrences across both runs and assert exactly 1 (case 142 counts judge calls the same way, `:3865-3877`) |
| E | a deleted agent cannot be recommended | fire for agent `X`, `rm "$BASE/agents/X.md"`, stop again: no hint, no traceback. Proves the corpus is read from disk each stop |
| F | independent of the judge | with `JUDGE_MODE=off` (the default) the hint still appears, pinning that the feature does not ride the model call |
| G | malformed frontmatter is LOUD | an agent file with no `description:` produces the corpus-error note; assert the note is present AND that a valid sibling agent still matches, so the error path degrades rather than disables |
| H | PostCompact carries the hint | drive `worklist.py --post-compact` (dispatch verified at `worklist.py:992-994`; the suite drives `--session-start` the same way at `:7839`) and assert `additionalContext` contains the hint |
| I | the kill switch works | `WORKLIST_AGENT_HINT=off` produces no hint, with a positive presence check first |
| J | per-session cap | `WORKLIST_AGENT_HINT_MAX_PER_SESSION=1`, two different agents match across two stops, exactly one hint total |
| K | priority 3 never displaces a real section | queue a real advisory (orphans) and a hint on the same stop with `OUTQ_PER_STOP=1`; assert the orphan section is emitted and the hint is not, and that `+1 more` is present |

Case K is the one that proves the noise control rather than asserting it, and it is the one I
would write first.

Multi-assertion cases use `pass`/`fail` (`:398-405`) with the case id as the first token of
the label, because `.ci/scripts/test/mutate-check.sh:47-49` matches on it.

---

## 8. Implementation split: two writers, disjoint ownership

Two concurrent writers, per the repo's cap. The file sets do not intersect.

### Writer A, "hook" (Opus)

Owns, and may touch nothing else:

```
.claude/hooks/stop/wl_agents.py            (new)
.claude/hooks/stop/worklist_messages.py    (add N_AGENT_HINT, N_AGENT_CORPUS_ERR)
.claude/hooks/stop/wl_checks.py            (import; one producer near :3563; one block near :1543)
.claude/hooks/stop/test-worklist-v5.sh     (mk_agent helper, setup lines, cases A-K)
```

Finish line: `.claude/hooks/stop/test-worklist-v5.sh` runs green locally with the new cases,
and case K passes.

### Writer B, "gate and agents" (Opus)

Owns, and may touch nothing else:

```
.claude/agents/backup-storage.md                       (new)
.claude/agents/account-dev.md                          (description only)
.claude/agents/ops-vms.md                              (description only)
.ci/scripts/quality/check_agent_hint_liveness.py       (new)
package.json                                           (one script line)
scripts/ci-runner/manifest.ts                          (one entry)
.github/workflows/ci-quality.yml                       (one step)
.ci/scripts/test/gates/test-gate-anti-vacuity.sh       (one registry line)
```

Finish line: `npm run check:ci-agent-hint-liveness` green, `npm run check:ci-parity` green,
and the gate proven to FAIL when a specimen is temporarily blanked (run it, paste the output).

### The one coupling, and how it is handled

B's gate imports A's `wl_agents.py`. That is a dependency on the **API**, not on the files, so
ownership stays disjoint. The API is frozen in section 3.1 and neither writer may change it
unilaterally; if it must change, that is a message to the lead, not an edit. B writes against
the frozen signature and runs its gate for real only after A's module lands. Sequence B's
final verification after A's finish line; everything else in B is independent and can proceed
in parallel from the start.

Both writers are forbidden `git checkout/restore/stash/clean`, any commit or push, and any
sync or regenerate script, per standing rules.

---

## 9. Reproducing the measurements

The prototypes behind every number in this document are at
`/tmp/claude-1000/-home-muhammed-monorepo-console/97604f47-7219-42f3-bed0-211ff4c7d824/scratchpad/`
(`proto.py`, `proto2.py`, `proto3.py`). They are scratch, not deliverables, and will not
survive. Anyone revisiting the corpus decision should rebuild the three variants rather than
trust the table in section 2: the claim to beat is **12/0/0 with descriptions alone**.

---

## 10. Out of scope, with reasons

**Phase 2, a Haiku signal on the judge.** Not in this change. When wanted, it is one optional
field on the existing `JUDGE_SCHEMA` (`wl_judge.py:53-107`), following the established
optional sub-object pattern of `regression_gate` (`:64`) and `defer_audit` (`:90`), gated
`WORKLIST_AGENT_HINT_JUDGE` default `off`, and it must fail toward silence rather than toward
a block. Never a second `claude -p` subprocess: `wl_judge.py:33-39` records a live timeout
that blocked a stop, and doubling the worst-case latency of the stop path to deliver one line
of advice is not a trade worth making. Note also that the judge is skipped entirely on a
cache hit and when nothing remains (`wl_checks.py:3221-3243`), so the deterministic matcher
must be the primary in any case.

**Phase 3, `UserPromptSubmit`.** This is where a hint is worth the most, because it speaks
when the task arrives rather than after the work. There is no `UserPromptSubmit` hook
registered today (the investigation verified the registered set: PreToolUse, PostToolUse,
SubagentStop, Stop, PostCompact, SessionStart), so it means a `.claude/settings.json` entry
and 1.4 ms plus Python startup on **every** prompt. That is an operator decision on latency
and on settings, so it stays out. Recorded here, not built.

**A hand-maintained context-to-agent table.** Rejected. A `{path glob -> agent}` mapping would
match better on day one and be stale within a month, which is the specimen-staleness class
this repo already pays a gate to catch. Everything in this design is derived: the corpus from
the directory, the terms from the descriptions, the discrimination from the corpus itself. The
cost is that a vague description matches poorly, and the correct fix for that is to sharpen
the description, which improves the agent for its human readers too.

**"You may want to write an agent for X."** A domain that scores 0 against every agent is
evidence of a missing specialist, and section 6.1 shows the signal is real. It is still a
different feature and must not ride this one.

---

## 11. Where this design could still be wrong

Stated plainly, because each is checkable rather than a hedge.

- **The 17-case table is mine.** I wrote both the specimens and the controls, which is the
  same hand marking its own homework. The gate's specimen table inherits that. The honest
  mitigation is section 7 case K plus the universe-equality assertion, which force future
  agents to earn their own specimen; the dishonest one would be to call 12/0/0 an accuracy
  figure. It is a smoke test that passed, not a measured hit rate.
- **Thresholds were calibrated on five synthetic composite haystacks**, not on real captured
  stop payloads. The composites are modelled on the real inputs (section 3.4) but they are
  still written by the same hand. If the first week produces a false positive, the first knob
  to turn is `MIN_MARGIN` back to 2, and the second is the stopword list, in that order.
- **HYPOTHESIS: the per-session cap and refresh window are guesses.** 3 hints per session and
  12 hours per agent are plausible, not derived. They are env-tunable for that reason.
- **The bench fix is verified for bench and nothing else.** Sharpening three descriptions
  fixes the gap the operator hit. It does not fix the *next* gap, whose noun nobody has typed
  yet. The universe-equality assertion in section 5.1(a) is the only structural defence, and
  it defends against missing agents, not against thin descriptions of existing ones.
