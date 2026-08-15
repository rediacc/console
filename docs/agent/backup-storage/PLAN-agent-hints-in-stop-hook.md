# PLAN: Agent hints in the stop hook

Status: SUPERSEDED. Written under a brief that was corrected mid-task: investigation and
design were to be separate steps, and the design step is not this session's. Treat the
design sections as unreviewed proposals, not as agreed plan. The verified facts behind
them were re-delivered as investigation findings to the team lead on 2026-08-15.
Owner: 97604f47
Updated: 2026-08-15

Scope: teach the hook battery to notice, unprompted, that the work in hand matches a
specialist under `.claude/agents/`, and to say so once. Every file:line below was read
this session; anything not verified is labelled HYPOTHESIS.

---

## 1. The verdict up front

Ship a **deterministic matcher over the agent frontmatter `description` field**, delivered
as an **advisory queue section** on the stop path plus an **additionalContext block on
PostCompact**, with a **liveness gate** modelled on `lint-rule-liveness.mjs` that proves it
both fires and stays silent.

Do **not** give the hint its own model call. The hook already pays for one Haiku call per
eventful stop, and a second one would double the dominant cost of a stop for a line of
advice. The Haiku path is worth having, but as a **field on the existing judge call**
(phase 2, flag-gated), never as a new subprocess.

Two pieces of the request I argue against, with reasons, in section 10.

### Why a deterministic matcher is not a downgrade

Measured this session on the real corpus (7 agent files, prototype in-session, not
committed): term extraction from the descriptions, keeping only terms that appear in
**exactly one** agent's description, scoring a haystack by weighted hits.

| session text (synthetic, one line each) | intended | result at threshold 2, margin 2 |
|---|---|---|
| "bench server deployment; run ./run.sh account dev, check the gateway portal login" | account-dev | fires account-dev 5, next 1 |
| ".claude/agents may help for ops as well, need a VM, rdc ops up --basic" | ops-vms | fires ops-vms 2, next 0 |
| "German locale file has Arabic values, re-run naturalize for the www translations" | i18n-guardian | fires i18n-guardian 2, next 0 |
| "license activation cap wrong after a fork, re-metering the datastore" | licensing-ops | fires licensing-ops 3, next 0 |
| "regenerate the tutorial narration, the captions drift by two seconds" | media-pipeline | fires media-pipeline 3, next 0 |
| "push the branch and watch CI until every job is green, flip the PR ready" | pr-babysitter | fires pr-babysitter 6, next 0 |
| "rdc config remote enable fails with Decryption failed after the passkey unlock" | config-universe | **silent** (2 vs 1, margin 1) |
| "add a retention quota to the backup chunk store and wire the CLI verb" | none | silent, 0 |
| "refactor the chunk-store index writer, add a unit test for the manifest" | none | silent, 0 |
| "update CLAUDE.md session defaults and the worklist stop hook docs" | none | silent, 0 |
| "fix a typo in the README" | none | silent, 0 |

6 of 7 true positives, 0 of 4 false positives. Cost of the whole thing including Python
startup: **21 ms** (`time python3 proto.py ...`, this machine, today). For comparison the
judge is 4.9 to 20.0 s and $0.011 to $0.026 per call (`wl_judge.py:21-22`).

Two honest caveats on those numbers:

- The haystacks are one-liners. The real haystack (section 4) is 10x longer, which raises
  both true and false scores. **The thresholds in section 6 are a starting point and must
  be recalibrated against real session text before the gate's thresholds are frozen.**
- The one miss is instructive rather than embarrassing: `config-universe` lost because
  `licensing-ops`'s description literally contains the words "config-universe" and
  "datastore", so the discriminative-term filter strips exactly the terms that would have
  won. Overlapping descriptions are the matcher's real weakness, and the gate in section 8
  is what turns that from a silent weakness into a red build.

---

## 2. How the hook is structured (verified)

| thing | where |
|---|---|
| entry point, all dispatch | `.claude/hooks/stop/worklist.py`, Stop battery at `wl_checks.py:1663 run_stop` |
| `--session-start` / `--post-compact` dispatch | `worklist.py:988-994` |
| hook registration | `.claude/settings.json:157` (Stop), `:163-168` (PostCompact), `:181-186` (SessionStart). **No `UserPromptSubmit` hook exists**, verified by dumping `hooks` keys: PreToolUse, PostToolUse, SubagentStop, Stop, PostCompact, SessionStart. |
| blocking violations | `vadd(key, always, text)` defined at `wl_checks.py:2234`, 46 call sites, collected into `violations` and emitted as one focused block at `wl_checks.py:3137-3212` |
| rotation of non-`always` violations | LRU over check keys, `wl_checks.py:3185-3199` |
| advisory sections (non-blocking) | `outq_add(...)` `wl_checks.py:1142`, drained one per stop by `outq_drain` `wl_checks.py:1223` with `OUTQ_PER_STOP` `wl_checks.py:1105` |
| the advisory producer block on the allow path | `wl_checks.py:3568-3644` (backoff tip, other sessions, orphans, open requests), drain at `:3646`, final emit at `:3662`, silent exit at `:3655` |
| message catalogue | `worklist_messages.py`; contract in its header `:1-40` (named `%`-format constants only, no logic); note constants around `:889-897` |
| the model call | `wl_judge.py`: `JUDGE_MODEL` `:20` (`claude-haiku-4-5-20251001`), budget `:31`, timeout `:39` (240 s), `JUDGE_DISABLED` `:40`, verdict cache `:47`, `resolve_claude()` `:270`, transport + recursion guard `:194-219` and `:327-353` |
| judge schema | `wl_judge.py:53-107`; top-level `required` is `["verdict","reason","next_action"]` with `additionalProperties: False` `:105-106`. Optional sub-objects are an established pattern (`regression_gate` `:64`, `defer_audit` `:90`) |
| suite | `.claude/hooks/stop/test-worklist-v5.sh`; gated twice, at `package.json:27` (`check:ci-hook-worklist-suite`, registered `scripts/ci-runner/manifest.ts:141`) and via `.ci/scripts/test/gates/test-worklist-hooks.sh:33-36` (`manifest.ts:433`) |

Registering a new check means: a function (or module) that computes it, one call site in
`run_stop`, one constant in `worklist_messages.py`, and cases in the suite. There is no
registry table to add to.

---

## 3. Which emission path a hint belongs on

**Not `vadd`.** A `vadd` entry blocks the stop. A hint is advice; blocking a session
because it did not consult a specialist would be the single fastest way to get this
feature switched off. It also would compete for the one focused slot with real violations.

**`outq_add`, priority 3.** That machinery already gives, for free, exactly the rate limits
this feature needs: a `shown` ledger keyed by section key with a refresh window
(`wl_checks.py:1199-1215`), a queue cap, "+N more" honesty on truncation (`M.N_OUTQ_MORE`,
`worklist_messages.py:893`), and one section released per stop.

**Plus PostCompact.** `handle_post_compact` (`wl_checks.py:1471`) already hands documents
back as `additionalContext` (`:1545-1553`). Post-compaction is the moment a session most
reliably forgets that a specialist exists, and the delivery costs nothing extra: one more
block appended to the `msg` string that is already being built.

---

## 4. What signal to match on

Cheap and reliable, all already in hand on the full-stop path:

| signal | where it already comes from | cost |
|---|---|---|
| last assistant message | `event["last_assistant_message"]`, read at `wl_checks.py:1902`. Confirmed present in a real captured payload (`/tmp/claude-worklist/*.lastevent-97604f47.json` carries `last_assistant_message`, `background_tasks`, `session_crons`) | free |
| this session's open worklist item text | `fold` is already loaded at `wl_checks.py:1683`; items carry `text`, `state`, `owner`, `id` (used that way in `triage_context`, `wl_checks.py:869-876`) | free |
| this session's brief | `S.read_briefs(worklist)` `wl_store.py:1071`, already called at `wl_checks.py:1922` | free |
| this session's STATE.md section | `S.agent_state_state(...)` `wl_store.py:1360`, already called at `wl_checks.py:1944`, third return value is the body text | free |
| changed file paths | `C._git(root, "status", "--porcelain")` `wl_core.py:440`; `triage_context` already does this at `wl_checks.py:862`. Measured today: **22 ms for 279 lines** on this tree | ~22 ms, one subprocess |

Expensive or unreliable, and rejected:

- **The transcript.** `transcript_tail` (`wl_core.py:790`) is bounded to
  `TRANSCRIPT_TAIL_BYTES = 2,000,000` (`wl_core.py:787`) and exists only as a fallback for
  payloads without `last_assistant_message` (comment at `wl_checks.py:1896-1901` says the
  event is authoritative). Measured today: this session's transcript is **25 MB**, the
  largest in the project directory is **106 MB**, the directory totals **2.3 GB**. Reading
  even the 2 MB tail per stop to feed a keyword matcher buys nothing the last assistant
  message does not already give. Do not read it.
- **"Has this session already used the agent?"** Not cheaply answerable. The `Stop` payload's
  `background_tasks` entries carry `{id, type, status, description}` only (verified in the
  captured payload above); there is no `agent_type`. The subagent type appears in the
  transcript's tool-use input, which is the file we just refused to read. HYPOTHESIS: it
  could be recovered from `wl_report.py`'s subagent records (`wl_report.py:517` reads
  `agent_transcript_path`), but that is a phase-3 refinement, not a launch requirement.
  Suppression is therefore by "already hinted", not by "already using it" (section 7).

Weighting: the **brief and the open item text are the highest-signal inputs** (they are the
session stating its own task in its own words). The last assistant message is noisy but
free. Changed paths are the best signal for domain-shaped work (`packages/cli/src/i18n/**`
means i18n whatever the prose says).

---

## 5. The corpus

`.claude/agents/*.md`, 7 files today: `account-dev`, `config-universe`, `i18n-guardian`,
`licensing-ops`, `media-pipeline`, `ops-vms`, `pr-babysitter`. Each opens with YAML
frontmatter carrying `name`, `description`, `tools`, `model` (verified across all 7). The
`description` is written for precisely this purpose, most of them ending in an explicit
"Use when ..." clause.

**Parse it by hand, not with PyYAML.** `import yaml` appears nowhere under `.claude/`
(verified). PyYAML 6.0.1 happens to be installed on this machine, but the hook must not
acquire a dependency that a CI runner might not carry, and the fields we need are
single-line scalars. Regex `^(name|description):[ \t]*(.+)$` inside the leading `---`
block is sufficient, **and a file that yields no `name` or no `description` must be
reported as a corpus error rather than skipped silently** (a silently skipped agent is the
dead-feature failure mode of section 8).

The corpus is re-read from disk on every stop. That is what makes "a hint pointing at a
deleted agent" structurally impossible rather than a thing to remember: if the file is
gone, the name is not in the corpus, so nothing can point at it. 21 ms measured for the
whole parse-and-score, so caching it would be an optimisation of nothing.

---

## 6. The matcher

New module `.claude/hooks/stop/wl_agents.py`. Pure functions, no writes, one filesystem
read of the agents directory. It is a separate module because `wl_checks.py` is already
179 KB, because the CI gate must import the scorer directly, and because it is genuinely
self-contained.

```
load_corpus(agents_dir)   -> {name: {"desc": str, "path": Path, "terms": {(kind, term)}}}
discriminative(corpus)    -> {name: {(kind, term)}}   # terms unique to ONE agent
score(haystack, uniq)     -> [(name, score, [hits])] sorted desc
best_hint(...)            -> (name, score, hits) or None
```

Term extraction, as prototyped:

- **path/command terms**: `[A-Za-z0-9_-]*(?:[./][A-Za-z0-9_-]+)+`, length > 5, lowercased.
  These are the high-value ones (`./run.sh`, `packages/www`, `private/growth/video_pipeline`)
  and they already sit inside the descriptions verbatim. Weight **3**.
- **word terms**: `[A-Za-z][A-Za-z0-9_-]{3,}`, lowercased, minus a stopword list. Weight **1**.
- **discriminative filter**: keep a term only when it appears in exactly one agent's
  description. With 7 documents this is a cheap and effective substitute for IDF, and it is
  what kills "config", "gate", "session" as triggers.
- **word boundaries on both sides.** The first prototype used a left-only boundary and
  scored `read` against `README`, firing a hint on "fix a typo in the README". That bug is
  recorded here because it is the exact shape of noise that would discredit the feature in
  week one.

Firing rule, both conditions required:

- `score >= AGENT_HINT_MIN_SCORE` (default **2**)
- `score - runner_up >= AGENT_HINT_MIN_MARGIN` (default **2**)

The margin is the part that matters. It is what makes the matcher say nothing when the
session's text is generic enough to look a little like three agents at once, which is the
common case and the one that would otherwise produce noise.

Env knobs, following the existing `WORKLIST_*` convention (`wl_checks.py:36-63`):

| var | default | meaning |
|---|---|---|
| `WORKLIST_AGENTS_DIR` | `hook_repo_root()/.claude/agents` | corpus location; the seam the suite and the gate point at fixtures (precedent: `WORKLIST_REPORTS_DIR`, `wl_checks.py` / suite `:102`) |
| `WORKLIST_AGENT_HINT` | `on` | `off` disables the feature entirely (precedent: `WORKLIST_JUDGE`) |
| `WORKLIST_AGENT_HINT_MIN_SCORE` | `2` | |
| `WORKLIST_AGENT_HINT_MIN_MARGIN` | `2` | |
| `WORKLIST_AGENT_HINT_REFRESH_MIN` | `720` | outq refresh window per agent |
| `WORKLIST_AGENT_HINT_MAX_PER_SESSION` | `3` | hard cap across all agents |

Corpus root uses `C.hook_repo_root()` (`wl_core.py:357`), not `project_root`: `.claude/agents`
is a sibling of `.claude/hooks/stop`, and `hook_repo_root` is immune to cwd by construction.

---

## 7. Delivery, and the rate limits that keep it from becoming noise

**Stop path.** One call, placed with the other advisory producers at `wl_checks.py:3568`
(that is, on the full allow path, after the judge, before `outq_drain` at `:3646`), wrapped
in `try/except Exception` exactly like `_quiet_min` at `:3563-3567`, because an advisory
note that can wedge a stop is a worse bug than the silence it fixes.

```
outq_add(worklist, session_id, state_doc,
         "agent-hint:%s" % name, M.N_AGENT_HINT % (...), 3,
         refresh_min=AGENT_HINT_REFRESH_MIN)
```

Priority 3 puts it behind every existing advisory (they use 1 and 2), so a hint never
displaces a real report section. Per-agent key plus the refresh window means the same
agent cannot be suggested twice in 12 hours. A counter in the per-session state doc
(`state_doc["agent_hints"] = {name: stamp}`, saved through the existing
`S.save_state`, `wl_store.py:330`) enforces `MAX_PER_SESSION` and gives the gate something
to assert against.

Placing it on the allow path is deliberate: a session that is blocked has a violation to
fix, and adding "by the way, consider agent X" to a block is the noise this design is
trying to avoid. The trade is that a session that never reaches a clean stop never gets
hinted. That is acceptable, because such a session is by definition being told something
more urgent every stop.

**PostCompact.** In `handle_post_compact` (`wl_checks.py:1471`), after the plans and
checklists blocks are appended to `msg` (`:1530-1544`), append the hint block when the
matcher fires against the compacted session's STATE.md body and open items. Once per
compaction, by construction. This is the highest-value delivery in the design and it is
three lines.

**The wording matters.** The hint must name the agent, the file, the terms that matched,
and it must say "consider", not "you must". Proposed constant in `worklist_messages.py`
(placed in the notes section beside `N_JUDGE_STAMP`, `:889`):

```
N_AGENT_HINT = (
    "Specialist agent available: %s (.claude/agents/%s.md). "
    "Your current work matched it on: %s. "
    "It carries knowledge this session would otherwise rediscover; "
    "spawn it with the Agent tool, or ignore this if it is not the domain you are in."
)
```

Naming the matched terms is what makes a wrong hint self-refuting: the reader sees
"matched on: fork, cap" and dismisses it in one second instead of opening the file.

---

## 8. Failure modes, and the control that proves it works

Three failure modes, in the order they are likely:

1. **Fires on every stop, becomes wallpaper.** Defended by: margin rule, per-agent refresh
   window, per-session cap, priority 3 behind everything else.
2. **Never fires, nobody notices.** This is the one this repo has been burned by. Defended
   by the gate below.
3. **Points at an agent that no longer exists.** Structurally impossible: the corpus is the
   directory listing, re-read each stop (section 5).

### The gate: `.ci/scripts/quality/check-agent-hint-liveness.py`

Modelled on `lint-rule-liveness.mjs`, which is this repo's canonical shape for proving a
matcher can fire (`.ci/scripts/quality/lint-rule-liveness.mjs:590-604` universe equality,
`:644-720` inline negative controls, `:732-767` core loop, `:799-837` four distinct verdict
shapes).

It imports `wl_agents.py` and asserts:

- **Universe equality in both directions.** The specimen table's key set must equal the set
  of `.claude/agents/*.md` names. A new agent with no specimen fails as `UNPROVEN`; a
  specimen for a deleted agent fails as `STALE SPECIMEN`. This is the single most valuable
  assertion: it makes "write a proof that your new agent is reachable" a build requirement
  rather than a good intention.
- **Each specimen fires for its own agent, as the top match, above threshold and margin.**
  A specimen that scores but loses to another agent is reported as `CROSS-MATCHED to <other>`,
  not as dead, because the two diagnoses have different fixes (sharpen the description
  versus fix the matcher).
- **Negative controls run inline on every invocation, never behind a flag.** At minimum:
  three neutral haystacks (a README typo, a chunk-store refactor, a docs edit) that must
  produce **no** hint. If any control fires, the gate refuses a verdict entirely and exits
  non-zero, the way `lint-rule-liveness.mjs:715-720` does. "The controls passed because
  everything is silent" is separately excluded by the specimen assertions above.
- **Anti-tautology.** A specimen must not be a verbatim slice of the agent's own
  description, and must be at most ~200 characters. Without this, a lazy specimen is
  "paste the description in", which proves that a string matches itself.
- **Vacuity refusal.** With an empty or absent agents directory the gate must print
  `VACUOUS INPUT: no agent files under <dir>` and exit non-zero, then be registered in
  `.ci/scripts/test/gates/test-gate-anti-vacuity.sh` beside its siblings (registry entries
  at `:110-121`, e.g. `.ci/scripts/quality/check_lint_rule_liveness.py|VACUOUS INPUT`), so a
  renamed agents directory cannot silently retire the whole feature.

Registration: `package.json` script `check:ci-agent-hint-liveness`, plus a manifest entry
following the shape at `scripts/ci-runner/manifest.ts:152`:

```
{ id: 'check:ci-agent-hint-liveness', run: 'npm run check:ci-agent-hint-liveness',
  gate: true, leaves: ['.ci/scripts/quality/check-agent-hint-liveness.py'],
  ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml',
        job: 'quality-content', step: "Agent hints can actually fire" } }
```

`leaves` is validated against what `package.json` resolves to (`scripts/check-ci-parity.ts:488-495`),
so the script path in `leaves` must be the one the npm script runs.

---

## 9. The Haiku question

**A model call is already in the hook.** `wl_judge.run_judge` / `run_triage` shell out to
`claude -p` with `--output-format json --json-schema`, model `claude-haiku-4-5-20251001`
(`wl_judge.py:20`), budget $0.25 (`:31`), timeout 240 s (`:39`), recursion-guarded with
`STOPHOOK_CHILD=1` (`:194-196`, `:327-330`) and run from an isolated workdir. So the answer
to "can the hook call a model at all" is yes, and the answer to "should the hint invent a
second path" is no: a second transport that drifts from the first is a second bug
(`wl_judge.py:177-181` says exactly this about `run_triage`).

**Do not add a per-stop model call for hints.** Numbers, from the code's own measured
comments and from the timing above: judge call 4.9 to 20.0 s and $0.011 to $0.026, already
the dominant cost of an eventful stop (`wl_judge.py:21-22`, `:47-52`); deterministic
matcher 21 ms and $0. A second call doubles the stop's cost and, worse, doubles its
worst-case latency, on a path where a 120 s budget already proved too small once and had to
be raised to 240 s after a live timeout blocked a stop (`wl_judge.py:33-39`). A hook that
hangs on the network to deliver advice is worse than no advice.

**Phase 2, if wanted: one optional field on the existing judge call.** The schema already
carries two optional sub-objects for exactly this kind of piggybacking (`regression_gate`
`wl_judge.py:64`, `defer_audit` `:90`), and the judge already sees the session's world.
Add:

```
"agent_hint": {"type": "object",
  "properties": {"use": {"type":"boolean"},
                 "name": {"type":"string","maxLength":40},
                 "why":  {"type":"string","maxLength":200}},
  "required": ["use","name","why"], "additionalProperties": False}
```

with a prompt section listing the roster (name plus first sentence of description, about 7
lines) and the deterministic candidate, asking only: is this candidate the right specialist
for what this session is doing, and if the candidate is empty, is any of them?

Two rules for that field, both non-negotiable:

- **It never blocks.** Every other judge output fails closed by contract
  (`wl_judge.py:1-5`); this one must fail toward silence-or-print, never toward a block. An
  absent, malformed or nonsense `name` (not in the corpus) means "no judge opinion", and
  the deterministic hint stands on its own.
- **It is flag-gated off at first** (`WORKLIST_AGENT_HINT_JUDGE`, default `off`) and turned
  on only after the suite shows the schema addition has not disturbed the judge's core
  verdict. The judge is a load-bearing gate; a hint is not worth destabilising it blind.

Note that the judge only runs when `something_remains or reg_signals` and is skipped on a
cache hit (`wl_checks.py:3221-3243`), and can be disabled entirely
(`WORKLIST_JUDGE=off`). That is another reason the deterministic matcher is the primary and
the judge field is a refinement: the feature must work on a stop the judge never sees.

---

## 10. Two pieces of the request I would change

**"The hint should come from the stop hook" is the second-best delivery point.** The stop
hook speaks *after* the work. The moment a specialist hint is worth most is when the task
arrives, which is `UserPromptSubmit`, and this repo has **no `UserPromptSubmit` hook
registered** (verified, section 2). A `worklist.py --user-prompt` mode that scores the
submitted prompt and returns `additionalContext` when the match is unambiguous would cost
the 21 ms measured above and would have caught this session's actual failure ("there is
bench server deployment") at the only moment where it saves the whole detour. I recommend
it as phase 3, after the matcher has a firing record on the stop path, and I flag it as
requiring an operator decision because it touches `.claude/settings.json` and adds latency
to every prompt.

**"Depending on contexts" should not become a hand-maintained context-to-agent table.**
A `{path glob -> agent}` mapping would match better on day one and would be stale within a
month, which is the specimen-staleness class this repo already pays a gate to catch. Every
signal in this design is derived: the corpus from the directory, the terms from the
descriptions, the discrimination from the corpus itself. The cost is that an agent with a
vague description is hard to match, and the correct fix for that is to sharpen the
description, which is a change that improves the agent for its readers too.

One thing worth noticing but explicitly **out of scope**: a domain that repeatedly scores
just below threshold against every agent is evidence that a specialist is *missing*. The
backup-storage rows in the section 1 table score 0 across the whole corpus, which is
accurate: there is no backup-storage agent. Turning that observation into a "you may want
to write an agent for X" note is a separate feature and should not ride this one.

---

## 11. Test cases for `test-worklist-v5.sh`

House style, verified: section banner `echo "== <N>. <claim> =="` at column 0; helpers
`setup` (`:48-109`), `say` (`:116-122`), `check <label> <expect> <needle>` (`:441-457`);
event payload built at `:384-385`; judge is off by default (`:388`) and the `$BASE/binonly`
PATH holds no `claude` (`:107-108`), so none of these can reach the network. Multi-assertion
cases use `pass`/`fail` (`:398-405`) with the case id as the first token of the label,
because `mutate-check.sh --expect-red` matches on it (`.ci/scripts/test/mutate-check.sh:47-49`).
There is no declared assertion count to update; the CI wrapper asserts only
`failed == 0` and `passed >= 1` (`.ci/scripts/test/gates/test-worklist-hooks.sh:68-84`).

Add a fixture helper beside `setup` that writes agent files into `$BASE/agents` and exports
`WORKLIST_AGENTS_DIR`, so no case depends on the real `.claude/agents` contents (the same
reason `WORKLIST_REPORTS_DIR` exists, suite `:102`):

```bash
mk_agent() {  # mk_agent <name> <description>
  printf -- '---\nname: %s\ndescription: %s\ntools: Bash\nmodel: opus\n---\nbody\n' "$1" "$2" \
    >"$BASE/agents/$1.md"
}
```

Cases, each with its control:

| # | claim | assertion |
|---|---|---|
| A | a matching open item produces the hint on an allow stop | `check` expects `allow` and the needle `Specialist agent available: <name>` |
| A-CONTROL | neutral text on the same fixture produces no hint | positive presence check first (the stop emitted *something*), then `! grep -qF "Specialist agent available"`. A bare negative passes vacuously if the feature is deleted; the suite documents this at `:9649-9658` |
| B | the hint never blocks | fixture that would otherwise stop cleanly; decision must be `allow` even with a hint queued |
| C | the ambiguity margin holds | two fixture agents whose descriptions share the matching terms so both score equally; no hint |
| D | rate limit | two consecutive stops with identical evidence emit the hint exactly once (count occurrences across both runs, as case 142 counts judge calls at `:3865-3877`) |
| E | deleted agent means silence | fixture matches agent `X`, then `rm $BASE/agents/X.md`, stop again, no hint and no error text. Proves the corpus is read from disk |
| F | works with the judge off | default `JUDGE_MODE=off` path already; assert the hint still appears, pinning that the feature does not depend on the model |
| G | malformed frontmatter is loud, not silent | an agent file with no `description:` produces a corpus-error note, never a silently skipped agent |
| H | PostCompact carries the hint | drive `worklist.py --post-compact` (the suite drives `--session-start` similarly at `:7839`) and assert `additionalContext` contains the hint |
| I | `WORKLIST_AGENT_HINT=off` is silent | the kill switch works |

---

## 12. File set and order

1. `.claude/hooks/stop/wl_agents.py` (new). Corpus, terms, scoring, `best_hint`, rendering
   inputs. No writes.
2. `.claude/hooks/stop/worklist_messages.py`: `N_AGENT_HINT`, and a corpus-error constant.
3. `.claude/hooks/stop/wl_checks.py`: import; one producer near `:3568`; one block appended
   in `handle_post_compact` near `:1544`. Nothing else.
4. `.claude/hooks/stop/test-worklist-v5.sh`: `mk_agent` helper plus cases A to I.
5. `.ci/scripts/quality/check-agent-hint-liveness.py` (new) with its specimen table.
6. `package.json` script + `scripts/ci-runner/manifest.ts` entry +
   `.ci/scripts/test/gates/test-gate-anti-vacuity.sh` registry line.
7. Calibrate `MIN_SCORE` / `MIN_MARGIN` against real session text (this worktree's
   `.sessions` briefs and open worklist items are the honest sample) before freezing the
   gate's thresholds.

Phase 2 (`agent_hint` on `JUDGE_SCHEMA`, default off) and phase 3 (`UserPromptSubmit`) are
separate changes and should not ride this one.

---

## 13. Open questions for the operator

- **Phase 3, `UserPromptSubmit`?** It is where the hint is worth the most, it costs 21 ms
  per prompt, and it needs a `.claude/settings.json` entry. DEFAULT if unanswered: build
  phases 1 only, leave 3 unbuilt and recorded here.
- **Should a hint ever escalate to a block?** My recommendation is never. DEFAULT: never.
