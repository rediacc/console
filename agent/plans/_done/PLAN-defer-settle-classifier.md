# PLAN: an automated accept/reject classifier for [?] deferrals

Status: done -- all boxes ticked 2026-09-24; .claude/hooks/stop/wl_defersettle.py with test-defer-settle.py (76 controls, 15 planted defects each red), --defer refusal in worklist.py, stop-time batch in wl_checks.py; see Implementation notes
First-Seen: 2026-09-23
Owner: d778be9d
Updated: 2026-09-23

## Finding

Operator request 2026-09-23: design + implement a Haiku-based auto-triage classifier for open [?] deferrals -- auto-reject/settle a deferral whose premise is already false (e.g. a credential question when the credential is already in private/account/.env) or already answered by a standing repo rule (e.g. CLAUDE.md's big-bang packaging rule), building on the existing wl_judge.py Haiku-call pattern. Design produced by a dispatched Plan agent (2026-09-23); recovered from its transcript after its worker process was reaped before the design was written to disk -- the analysis below is unedited from that report.

## 0. What already exists that this must not duplicate

This repo already has a Haiku classifier riding the stop judge that asks almost the right question. `.claude/hooks/stop/wl_checks.py:4337-4463` builds a `DEFER_AUDIT_PROMPT` (`.claude/hooks/stop/worklist_messages.py:1269-1307`) over aged (`S.DEFER_AUDIT_MIN`, 45min), *justified* (`deferral_is_justified`, `.claude/hooks/stop/wl_checks.py:543-546`) `[?]` items, bounded to `S.DEFER_AUDIT_BATCH` (4) per stop, riding the **same** `run_judge` call via the optional `defer_audit` field in `JUDGE_SCHEMA` (`.claude/hooks/stop/wl_judge.py:117-130`).
Its prompt already says almost verbatim what the operator is asking for: *"some of them asking for work that was ALREADY done"* and *"Is the WHY still TRUE? A reason that has expired (the run finished, the file landed, **the answer is in the tree**) is no reason."* A `do_now` verdict reopens the item as `[ ]` (`.claude/hooks/stop/wl_checks.py line 4763-4772 (blob 5a8904da5ad6)`, `S.set_state(worklist, "judge", rid, " ", ...)`).

So a real design choice exists here, not just a green field: **extend `defer_audit` vs. add a sibling module**. This design recommends a **sibling module** (`wl_defersettle.py`, matching the `wl_bravedefault.py`/`wl_classsweep.py`/`wl_proofcheck.py`/`wl_claimcheck.py` family, all of which contribute one optional field to `JUDGE_SCHEMA` and ride the one `run_judge` call), for three reasons argued below in §1, not folded into `defer_audit` itself -- this is a real fork, not a foregone conclusion, so the alternative is given too.

Why not just extend `defer_audit`:
1. **Different question, different evidence, different action.** `defer_audit` interrogates *prose* ("is this WHY real") with no facts handed to it — it is a reasoning-only judge.
   The operator is asking for a *fact-grounded* check ("is X actually present at path Y right now") in the same no-tools style `.claude/hooks/stop/wl_judge.py:771-776` already uses for its OTHER grounding (`fixset_files`, `ground_extra` at `.claude/hooks/stop/wl_judge.py:737-748`): Python computes the fact, hands it to Haiku as a given, Haiku never investigates. Bolting a `KNOWN FACTS:` block onto `defer_audit`'s existing prompt (whose whole rhetorical stance is "assume avoidance, be a hard reviewer of prose") risks the facts contaminating that unrelated judgment, and makes the schema's `verdict` field try to carry two different kinds of "yes."
2. **Different age gate.** `defer_audit` only ever looks at items already aged past 45 minutes and already justified. The operator explicitly wants the credential case caught **at creation time**, before any of that — a fresh, unjustified `[?]` should never even become a stored deferral if the fact that would resolve it is already checkable. `defer_audit`'s trigger can't reach there without breaking its own contract (it fires only on justified, aged items).
3. **Different failure/action semantics.** `defer_audit`'s two verdicts (`valid`/`do_now`) both leave a human/session with something to still do (bank, or convert to ordinary open work). This mechanism's `settled` verdict is stronger — it closes the loop itself (a tick) — which is exactly the higher-stakes action the operator's §7 corroboration requirement is worried about, and deserves its own schema object so its fail-open/fail-closed contract isn't smeared across a field that means something else half the time.

Alternative (if a reviewer prefers less surface area): fold this in as a **third verdict** on the existing `defer_audit` per-item enum (`valid` / `do_now` / `settled`), reusing its batch and its age gate, and skip the creation-time hook entirely. This is simpler (one schema object, one prompt, one call site already wired) but concedes the cheapest catch point (creation time) and forces the credential case to wait 45 minutes before it's even considered — for the operator's own worked example ("does the operator want to provide X" when X is already in `private/account/.env`), that is 45 minutes of a live `[?]` sitting in every stop's report for a question the tree already answers.
The sibling-module design is recommended; this fallback exists if a reviewer wants to keep the touch surface smaller.

## 1. Where this plugs into the lifecycle

Two entry points, both wired, with the reasoning for each:

### 1a. Creation time — `worklist.py --defer`, `.claude/hooks/stop/worklist.py:920-940`

This is the cheap, primary defense. Right now `--defer` (`.claude/hooks/stop/worklist.py:920-940`) does a **shape-only** check: `DEFAULT_TOKEN` present, then `C.parse_justification` extracts WHY/HOW and `VAGUE_WHY_RE` rejects avoidance-shaped prose (`CLI_DEFER_VAGUE_WHY`). Nothing here ever looks at whether the WHY is *true*. One more gate is added, **after** the existing shape checks pass and **before** `S.set_state(..., "?", ...)` is called:

```
# after `S.set_state(worklist, me, item_id, "?", rest, extra={"j": just})` would run:
verdict, err = wl_defersettle.classify_one(root, item_id, rest, just)
if verdict and verdict["verdict"] == "settled" and wl_defersettle.corroborated_once(...):
    ... (see §5: does NOT fire on first sight; see hard limit in §7)
```

In practice creation-time can only ever produce the **first** of the two corroborating signals (§7), never act alone — see §5. Its job at creation time is: run the classifier once, and if it says `settled`, refuse to create the `[?]` in the first place and tell the session what already answers it (mirroring how `CLI_DEFER_NO_JUSTIFICATION`/`CLI_DEFER_VAGUE_WHY` already refuse a bad `--defer` call). That is a **refusal at the CLI**, not an auto-tick — it never touches the store, so it carries none of the corroboration risk: the session that just tried to defer sees the fact immediately, in the same turn, and decides for itself. This is strictly safer than an unattended auto-tick, and it is the cheapest possible catch (a wasted `[?]` never gets born).

Concretely:
```
worklist.py:929-934, after the vague-why check, before S.set_state:
    fact_verdict, fact_err = wl_defersettle.classify_one(root, rest, just)
    if fact_verdict and fact_verdict.get("verdict") == "settled":
        die(M.CLI_DEFER_ALREADY_SETTLED % (fact_verdict["fact_cite"], fact_verdict["reason"]))
```
A classifier error here (`fact_err` set) is **not** a die — see fail-safe direction, §3: it silently falls through to the existing `S.set_state` call, i.e., creation proceeds exactly as it does today. A creation-time classifier failure must never block the one write path CLAUDE.md explicitly protects ("a [?] costs nothing to create").

### 1b. Stop time — re-check aged, still-open `[?]` items

Creation-time only ever sees the world as of the moment the `[?]` is written. The operator explicitly asked for the case where a fact becomes true **after** creation (a credential gets added later, or a standing rule gets written after the question was parked). So a second, bounded pass rides the stop-time judge call, symmetric with `defer_audit`, in `wl_checks.py` right next to the `audit_batch` construction (`.claude/hooks/stop/wl_checks.py:4342-4362`):

```
settle_batch = []
if not wl_judge.JUDGE_DISABLED:
    for r in sorted(deferred_recs, key=...):
        age = C.stamp_age_min(r.get("upd", "")) or 0
        if age < S.DEFER_SETTLE_MIN:   # new constant, see §4 for why this differs from DEFER_AUDIT_MIN
            continue
        facts = wl_defersettle.gather_facts(root, r)
        if not facts:
            continue   # nothing checkable about this item; do not spend a call on it
        banked = settle_cache.get(r["id"])
        if isinstance(banked, dict) and banked.get("stamp") == r.get("upd") and banked.get("corroborated"):
            continue   # already acted on
        settle_batch.append((r, facts))
        if len(settle_batch) >= S.DEFER_SETTLE_BATCH:
            break
```

This rides the same `run_judge` call as `class_sweep`/`brave_default`/`proof_obligation`/`claim_check`/`defer_audit` already do, via one more optional `JUDGE_SCHEMA` field (`defer_settle`), required-iff-asked through `judge_schema_for` (`.claude/hooks/stop/wl_judge.py:679-702`) keyed on a new marker string, exactly the established pattern.

**Why gather facts BEFORE deciding to batch, not inside the model call:** unlike `defer_audit` (which only needs the WHY/HOW prose, always present), this check is worthless for the majority of `[?]` items that don't mention anything checkable (a genuine design decision, a preference question). Computing `facts` first and skipping items where `gather_facts` returns nothing means the classifier is **never invoked on a `[?]` with no checkable claim in it** — this is the cost control the operator asked for in a stronger form than a raw batch cap: most of the ~8-10 item backlog will simply never enter `settle_batch` at all, because most `[?]`s aren't about a fact Python can look up.

## 2. `gather_facts`: the bounded, closed set of checks

This is the module's central discipline, and it is what keeps this from being "an open-ended free-form investigation" the operator explicitly ruled out. `gather_facts(root, rec)` runs **three, and only three**, deterministic Python checks against the `[?]`'s own text + its WHY/HOW (`S.deferral_justification(rec)`), each emitting a fact record `{kind, claim, present, cite}` — never a value, never free text from an arbitrary file:

1. **`env_key_present`** — scan the `[?]` text and WHY/HOW for ALL-CAPS-snake-case tokens (`\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b`, 2+ segments) that look like credential/env names. For each candidate, check ONLY a fixed allowlist of locations — `private/account/.env`, `.env`, `.env.example` — for a line matching `^KEY=` (or, for `.env.example`, `^KEY=` with any value, since that file has no secrets). **The check reads only whether the key NAME appears at the start of a line; it must never read or forward the value.** The fact record's citation is `path:line` of the key line (a real, resolvable citation per `citation_state`'s own contract — `.claude/hooks/stop/wl_checks.py:403-425` — since it's a real path+line on disk, gitignored or not, `citation_state` only checks `is_file()`), and the fact text is literally `"KEY present at private/account/.env line 41"` — no value, ever, in the prompt sent to Haiku or in any ledger record.
2. **`standing_rule_match`** — a small, hand-maintained, versioned catalog in the module (not a live grep of CLAUDE.md, deliberately — see below), each entry `{id, trigger: regex, quote, cite: "CLAUDE.md:47-48", action}`. Two entries ship on day one:
   - `big-bang-packaging`: trigger matches `[?]` text containing packaging-shaped language (`\b(separate|one|which|split|combine|bundle)\b.{0,40}\bPR\b`, `\bbig[- ]bang\b`, `\bcluster\b.{0,40}\bfindings?\b`) → quotes CLAUDE.md's rule 2 verbatim (`CLAUDE.md:46-48`, "The ask decides PACKAGING, never WHETHER... park the ask as a [?] whose DEFAULT is 'fix the cluster this session'") → `action: execute_default`.
   - `model-routing-haiku`: trigger matches `[?]` text asking which model tier for a WRITE task → quotes `CLAUDE.md:135-138`/`D-M1` (`agent/DECISIONS.md:58`) → `action: genuinely_operator_no` (i.e. this fact tells Haiku the *answer* is already settled: never Haiku for writes) `→ execute_default` if the DEFAULT already says "route to Sonnet/Opus", else surfaced as `genuinely_operator` with the rule quoted so the session, not Haiku, decides packaging around it.

   **Why a hand-maintained catalog and not a live grep of CLAUDE.md for keyword overlap:** a dynamic search is exactly the "open-ended investigation" the design brief forbids — it would let the classifier match a paragraph nobody vetted for this purpose, quote it out of context, and act on that quote. A catalog entry is written and reviewed once, by a human/session with agentic write access, the same way `wl_bravedefault.py`'s `HOLD_REASONS` enumeration or `wl_reggate`'s `surface` enum are hand-maintained closed sets. Growing the catalog is a normal code change (add an entry, cite the rule, name the trigger), not something the classifier does unsupervised.
   This is a real tradeoff: a live grep would generalize to rules nobody thought to catalog yet (closer to the operator's "different angles" ask); the catalog only ever recognizes shapes someone wrote down. The catalog is recommended because the fail mode of a live grep (wrong paragraph, right keywords) is exactly the kind of quiet-plausible error class this whole program exists to catch elsewhere in the codebase (see `wl_admit.py`'s own argument for why a regex prefilter is a cost filter and never a verdict) — a match here is stronger evidence than an admission-family regex, since its consequence is auto-executing a DEFAULT, not merely spending a model call.
3. **`artifact_exists`** — for a `[?]` that asks "should this be built" or "does X already exist," a bounded glob check against a repo-relative pattern extracted from a backtick-quoted or `path/like/this` token in the text (checked only against the actual filesystem inside `root`, never a remote/network location). Third class, demonstrating the "different angles" the operator asked for: e.g. a `[?]` reading *"DEFAULT: file an issue asking whether we need a `check:<name>` regression gate for this surface"* when `wl_reggate.package_scripts(root)` (already used at `.claude/hooks/stop/wl_checks.py:4404`) already lists a `check:<name>` key — the fact `check:<name> already registered in package.json scripts` settles the question without a model needing to invent anything, Python already has the authoritative list.

No fourth kind ships day one; the module's docstring states explicitly that a fourth fact kind is a deliberate, reviewed code change, never a runtime decision by the model.

## 3. The schema and prompt

```python
DEFER_SETTLE_MARKER = "THIS DEFERRAL'S PREMISE MAY ALREADY BE FALSE"

DEFER_SETTLE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "maxLength": 16},
            "verdict": {"type": "string",
                        "enum": ["settled", "execute_default", "genuinely_operator", "uncertain"]},
            "reason": {"type": "string", "maxLength": 300},
            "fact_used": {"type": "string", "maxLength": 16},   # which gathered fact's index/id it relied on; "" if none
        },
        "required": ["id", "verdict", "reason", "fact_used"],
        "additionalProperties": False,
    },
}
```

Prompt (`DEFER_SETTLE_PROMPT`, modeled directly on `DEFER_AUDIT_PROMPT`'s rhetorical shape and directly on the operator's own two worked cases):

```
THIS DEFERRAL'S PREMISE MAY ALREADY BE FALSE. ALSO fill the `defer_settle`
array: exactly one entry per item below, using the same id.

You are given, for each item, a CLOSED set of FACTS this session's own code
already checked -- you are not being asked to investigate anything yourself,
only to reason about what is handed to you. Never assume a fact that is not
listed; never treat a KEY NAME being present as proof of its VALUE.

Verdict per item:
  "settled": one of the given facts makes the [?]'s own QUESTION moot -- the
    thing it asks the operator to decide or provide is already true, present,
    or already answered by a quoted standing rule that requires no operator
    judgment call. Cite exactly which fact in `fact_used`.
  "execute_default": a given fact is a STANDING RULE that already settles
    HOW to package this, and the DEFAULT already names the packaging that
    rule requires -- so there is nothing left to wait out the window for.
    Cite the rule fact in `fact_used`.
  "genuinely_operator": the facts given do not settle this; it is a real
    decision for the operator, or the standing rule quoted requires a
    judgment call the rule itself does not make (state which).
  "uncertain": you are not confident either way. USE THIS WHENEVER IN DOUBT --
    an uncertain [?] is left exactly as it is; only a confident "settled" or
    "execute_default" ever changes anything.

Items and their FACTS (%(n)d):
%(items)s
```
Per-item block, e.g.:
```
  id=a1b2c3  [?] does the operator want to provide the Cloudflare R2 access
  key, or should we skip R2-backed backup tests
    WHY: R2 credentials are an operator-only external account
    HOW: operator says yes/no or provides the key
    FACT #1 (env_key_present): key CLOUDFLARE_R2_ACCESS_KEY_ID is present at
      private/account/.env:12 (value not shown; presence only)
```

This mirrors `wl_judge.py`'s established grounding style (`FIXSET_GROUND_TRUTH`, `ground_extra`) — facts are always Python-computed and quoted, never left for the model to assert.

## 4. Fail-safe direction — the opposite of the stop judge's, stated explicitly

`wl_judge.py`'s docstring states the stop judge's contract bluntly: *"Fail CLOSED by contract... a judge failure blocks."* That is correct there because the consequence of a failure is "the turn cannot end" — annoying, never destructive, and reversible by simply calling the judge again next stop.

This classifier's fail-safe direction must be the **opposite**, for its own action: **any failure — timeout, malformed array, budget exceeded, transport error, `is_error`, or a missing `settled`-eligible entry — must leave the `[?]` exactly as it is: still `[?]`, still genuinely-operator, still waiting on its normal `DEFER_WINDOW_MIN` clock.** Never auto-accept, never auto-reject, on a failure. Concretely:
- `run_judge`'s own top-level `err` path already exists and already fails the WHOLE stop closed (`.claude/hooks/stop/wl_checks.py line 4532-4544 (blob 5a8904da5ad6)`) — this is unrelated and must not change; `defer_settle` is a **secondary** object riding the same call, so if the whole judge call fails, the classifier simply never ran this stop (same as `defer_audit`, `class_sweep` etc. today) and the item is untouched.
- If the judge call **succeeds** (verdict returned, stop/continue decided) but `defer_settle` is missing, malformed, or a specific item's entry is absent from the array: **this must NOT fail closed the way `defer_audit`'s malformed case does** (`R_AUDIT_MALFORMED`, `.claude/hooks/stop/wl_checks.py line 4735-4747 (blob 5a8904da5ad6)`, which blocks the stop). The reason `defer_audit`'s malformed path blocks is that a *requested* audit that produced no answer is a promise broken by the judge, and the caller demanded certainty about `valid`/`do_now` before it can safely bank anything. Here the asymmetry is sharper: a malformed `defer_settle` costs the session **nothing** if it is simply dropped — the `[?]` just stays a `[?]`, exactly the outcome a session with no classifier at all already lives with today. Blocking the stop over a missing advisory here would be manufacturing new friction for a feature whose entire point is REDUCING friction. So: same never-fails-closed contract as `class_sweep`/`brave_default`/`proof_obligation` (`.claude/hooks/stop/wl_judge.py:73-82`), not `defer_audit`'s or `regression_gate`'s stronger contract. A degraded/malformed answer appends a one-line note to `reason` (`"[defer-settle not judged: %s]"`), same convention as the sibling modules (`.claude/hooks/stop/wl_judge.py:850-872`).
- Uncertain is a first-class outcome (`"uncertain"` verdict), not an error: this is what "USE THIS WHENEVER IN DOUBT" in the prompt is for, mirroring `defer_audit`'s own "do_now: use this whenever in doubt" instruction — but pointed the safe direction here, since `defer_audit`'s safe default (`do_now`) still leaves a human/session owning the item, while this module's unsafe default would be silently closing it.

## 5. Cost, batching, and the corroboration requirement

- Follows `JUDGE_BUDGET_USD`/`JUDGE_TIMEOUT_S` exactly — this rides `run_judge`'s existing subprocess call, so it has no separate budget or timeout knob; its cost is "however many more tokens the prompt grew by," same accounting `class_sweep`/`brave_default`/`defer_audit` already accept.
- **Batched, not per-item.** New constants `DEFER_SETTLE_MIN` (age gate, default 30min — deliberately *shorter* than `DEFER_AUDIT_MIN`'s 45, because "is the premise already false" is cheaper to be wrong about safely than "is this WHY genuinely an inability," given the never-fails-closed/no-silent-tick design in §3 — see hard limits below for why a short gate is still safe) and `DEFER_SETTLE_BATCH` (default 4, matching `DEFER_AUDIT_BATCH`). Given the session's own ~8-10 item `[?]` backlog, gathering facts BEFORE batching (§1b) means most stops send **zero** extra items (no checkable claim found), keeping the marginal cost near zero on the common stop and bounded on the stop where several items do carry a checkable claim.
- **The corroboration requirement (operator's explicit ask, §7 of the prompt).** A `settled` verdict is never acted on the first time it is seen. It is **banked** exactly like `defer_audit` banks a `valid` verdict (`audit_cache`, `.claude/hooks/stop/wl_checks.py:4339,4748-4754`), keyed to the item's `upd` stamp, but with a NEW field `corroborated: bool`. The FIRST stop that returns `settled` for an item banks it un-corroborated and does **nothing else** — no tick, no message beyond a quiet advisory. Only a **second, later stop** (a different `run_judge` invocation, i.e., a genuinely independent sample, not a retry of the same call) that *also* returns `settled` for the same item **and** cites the same fact (`fact_used` referring to the same fact kind+citation) flips `corroborated: True` and triggers the tick (§6). This is the "bank-then-confirm across two stops" design.

  **Tradeoff worth flagging rather than picking silently:** the alternative is two independent classifier calls **within the same stop**, framed differently (e.g., one prompt asking to justify `settled`, a second independently re-deriving the fact without seeing the first's reasoning), which corroborates immediately rather than waiting for a second stop.
  That is more expensive (two model calls instead of riding the one `run_judge` call — breaks the "ride the existing call" discipline every sibling module observes) and more complex (needs a second, separate subprocess invocation only for this path), but it resolves in one stop instead of possibly waiting an arbitrary number of stops for the item to come up for audit again (if the session goes quiet, corroboration could take a long time). The cross-stop bank-then-confirm design is recommended, since it costs nothing extra per stop and matches the codebase's existing latch idiom exactly; the two-calls-same-stop alternative is reasonable if faster resolution matters more than the extra call.

## 6. What "resolved" means and how it's recorded

On corroboration (§5), the module does **not** call `S.set_state` with `"x"` blindly. It builds an evidence string, referencing the fact's real citation (`path:line`, no secret values), e.g.:

```
"MACHINE-CLASSIFIED (haiku-defer-settle): premise settled -- CLOUDFLARE_R2_ACCESS_KEY_ID present at private/account/.env:12 (key checked, value not read); corroborated over 2 stops (2026-09-23T14:02Z, 2026-09-23T15:10Z), verdict cited fact env:CLOUDFLARE_R2_ACCESS_KEY_ID both times"
```

Then it runs the **same evidence gate** every human/session tick already goes through, even though this is an internal call bypassing the `worklist.py --tick` CLI:
```python
if not CK.completion_evidence(root, evidence) or CK.issue_only_evidence(root, evidence):
    # refuse to tick; leave the [?] exactly as it was, log why, done.
    return "refused-evidence-gate"
S.set_state(worklist, "haiku-defer-settle", item_id, "x", evidence)
```
This is deliberate and important: `citation_state`'s `path:line` requirement (`.claude/hooks/stop/wl_checks.py:403-425`) is what forces the evidence string to actually name a real, resolvable location — the exact "real, resolvable citation" discipline the operator's §5 asks for, reusing `--plan-tick`'s own refusal machinery rather than inventing a parallel one.

**The greppable, permanent marker:** `by="haiku-defer-settle"` on the `state` event (the store already has precedent for a non-human actor in `by` — the audit's reopen uses `by="judge"`, `.claude/hooks/stop/wl_checks.py line 4766-4772 (blob 5a8904da5ad6)`). This is visible two ways forever:
1. In the append-only `.events.jsonl` (never rewritten — `wl_store.py`'s own design guarantee), any future audit greps `"by": "haiku-defer-settle"` and gets every machine-settled item, ever, with its full evidence string attached.
2. In the rendered line itself (`brief_line`, `.claude/hooks/stop/wl_store.py:849`), the note text (which starts `MACHINE-CLASSIFIED (haiku-defer-settle):`) is what a human reads when the item shows up ticked in history — never confusable with an operator's own words, by construction (an operator never types that string).

For `execute_default` (the packaging-rule case, operator's example 2): this does **not** tick the item — it converts it exactly the way an expired-window default already does (`.claude/hooks/stop/wl_checks.py:2915-2937`, `V_DEFER_EXPIRED`), i.e. it emits a report line telling the session to execute the DEFAULT **now**, rather than waiting for `DEFER_WINDOW_MIN`. It never performs the DEFAULT's action itself (see §7 — Haiku is a classifier, never a writer, per D-M1).
Concretely: it reuses `V_DEFER_EXPIRED`'s own wording, fired early, with the item added to the same `expired` list the age-based path already builds — a two-line change at `.claude/hooks/stop/wl_checks.py:2915-2920` (an item can enter `expired` either because its age crossed `DEFER_WINDOW_MIN`, OR because a corroborated `execute_default` fired for it). This means `execute_default` never needs its own new report string, exit path, or `by`-tag machinery — it fully reuses the existing, already-audited "DEFAULT executes" mechanism, and the *session itself* (not Haiku) still does the actual packaging work and ticks it with real evidence through the ordinary `--tick` gate. Only `settled` performs a tick, and only via the module's own gated `S.set_state` call above.

## 7. Hard limits keeping this bounded

1. **Never on the classifier's first attempt** — the cross-stop corroboration bank in §5 is the mechanism; restated here as the hard invariant: `settle_cache[id]["corroborated"]` must be `True`, set only by a *second* independent `run_judge` call agreeing on the *same* cited fact, before any store mutation happens.
2. **Never irreversible/`main`/release/second-PR DEFAULTs auto-execute.** `execute_default` reuses the existing expired-DEFAULT path, which reuses `sanitize_next_action`'s `FORBIDDEN_ORDERS` regex family (`.claude/hooks/stop/wl_judge.py:881-903`) indirectly — but more importantly, `wl_bravedefault.py`'s own boundary (merging, pushing main, releasing, and *committing* are never a "brave" default and this machinery is already forbidden from ordering them) is the model this hard limit borrows: `execute_default` only ever fires the *reporting* of "do it now," never a direct action, and the same `FORBIDDEN_ORDERS` scan should be applied to the catalog `action` text at classifier-module-authoring time (a catalog entry whose `action` would resolve to one of those verbs is refused at import time by an assertion in `wl_defersettle.py`, the same way a bad `HOLD_REASONS` entry would be a code review catch in `wl_bravedefault.py`).
3. **Never on `settled` alone converts an item without the evidence gate** (§6) — `completion_evidence`/`issue_only_evidence` must both pass, or the tick is refused and the item is left untouched, logged as a refusal (not a failure — same never-block contract as §4).
4. **Secret values never leave Python.** `env_key_present` reads key names only; the fact text handed to the Haiku prompt and the evidence string written to the permanent ledger both contain only `KEY present at path:line`, never a value. This is enforced by the fact-gatherer's own return type (a fact record has no `value` field at all — it structurally cannot carry one), not by a redaction step that could be forgotten.
5. **The greppable marker is permanent and un-fakeable by a session.** `by="haiku-defer-settle"` is a reserved actor name the same way `"judge"` already is; a session calling `S.set_state` directly with that `by` value would be indistinguishable from the real thing only if it deliberately typed the reserved string, which is the same trust model the codebase already accepts for `by="judge"`.
6. **A hard per-branch/session cap on corroborated settles**, mirroring `wl_reggate`'s effort-cap ledger (`REGGATE_CAP`, `.claude/hooks/stop/wl_checks.py line 4673-4719 (blob 5a8904da5ad6)`): if this classifier settles more than N items (suggest 5) in one session without an operator ever reviewing one, the Nth+1 attempt is reported instead of acted on ("N deferrals were auto-settled this session; review before more auto-settle") — this is the safeguard against a single bad catalog entry or a systematically wrong fact-check quietly closing an entire backlog unattended.

## 8. Test coverage design

Following `test-judge-schema.py`'s convention exactly: no pytest, a `Tally` counter, `control(label, got, want)`, and the subprocess seam stubbed at `wl_judge.wl_proc.run` (never real `subprocess`, never real judge budget) via a `FakeProc`/`scripted` helper identical to lines 435-505 of that file. New file `test-defer-settle.py` in `.claude/hooks/stop/`.

**Class 1 — credential availability (operator's example 1):**
- **Should auto-resolve (paired with corroboration):** a `[?]` reading `"...does the operator want to provide the R2 access key... DEFAULT: skip R2-backed tests WHY: ... HOW: ..."`, with a fixture `private/account/.env`-equivalent temp file containing `CLOUDFLARE_R2_ACCESS_KEY_ID=xxxx`. `gather_facts` must return one `env_key_present` fact with `present=True` and a citation, and never include the literal value `xxxx` anywhere in the returned fact or in the constructed prompt string. Two scripted `run_judge` calls both returning `settled` citing that fact → assert `corroborated=True` and the constructed evidence string passes `CK.completion_evidence` and does not contain `xxxx`.
- **Control (should NOT auto-resolve):** identical item text, but the fixture `.env`-equivalent has no such key. `gather_facts` must return `present=False` (or no fact at all, if the design chooses to only emit present=True facts — pin whichever the implementation does) and the classifier must never be told to settle; assert the item is untouched after a stop.

**Class 2 — standing-rule packaging (operator's example 2):**
- **Should auto-resolve:** a `[?]` reading `"...should this be one PR or split into three... DEFAULT: fix the cluster this session..."`. `gather_facts` must match the `big-bang-packaging` catalog entry and return the CLAUDE.md quote + citation. A scripted judge response returning `execute_default` citing that fact (corroborated over two calls) → assert the item is added to the `expired`-equivalent report path (i.e., `V_DEFER_EXPIRED`-shaped output) on the SAME stop it would otherwise have had to wait `DEFER_WINDOW_MIN` for, and assert no store `by="haiku-defer-settle"` tick was written (this class never ticks, only accelerates the report).
- **Control:** identical DEFAULT/packaging language but the item's own text doesn't match any catalog trigger regex (e.g., a genuinely novel packaging question with no "PR"/"bundle"/"cluster" language) → `gather_facts` returns no `standing_rule_match` fact, classifier is never invoked for this item, item ages normally to `DEFER_WINDOW_MIN` exactly as today.

**Class 3 -- artifact-already-exists (a third added class, operator's "different angles" ask):**
- **Should auto-resolve:** a `[?]` reading `` "...file an issue asking whether we need a `check:<name>` regression gate for this... DEFAULT: file the issue" `` where a fixture `package.json`-equivalent scripts dict already has `check:<name>`. `gather_facts` returns `artifact_exists` fact citing the scripts entry; two corroborating `settled` verdicts → tick, evidence cites the scripts key (not a value, no secret concern here but the same evidence-gate path is exercised).
- **Control:** identical item text, fixture scripts dict has no `check:<name>` key → no fact, no classification, item left alone.

**Cross-cutting controls (mirroring `test-judge-schema.py`'s "the pair" discipline):**
- **Fail-safe direction pair:** (a) a malformed `defer_settle` array (missing entry for a requested id) must NOT block the stop (unlike `defer_audit`'s malformed path) — assert `decision` is not forced to `"block"` by this alone; (b) a judge timeout/`is_error` on the whole call must leave the item exactly as it was (no bank, no tick) — reuse the existing `_FakeProc`/`_EXHAUSTED`/timeout fixtures already in `.claude/hooks/stop/test-judge-schema.py:1338-1396` verbatim rather than re-deriving them.
- **No-corroboration pair:** a single `settled` verdict (first sight) must bank but never tick; a second `settled` verdict citing a **different** fact than the first must NOT corroborate (asserts the "same fact both times" requirement, not just "settled twice").
- **Secret-never-leaves-Python pair:** assert the constructed Haiku prompt string for a present credential never contains the fixture's value string; assert the constructed evidence/tick string never contains it either.
- **Reserved-actor pair:** assert a real `--tick` invoked by an ordinary session id can never accidentally collide with `by="haiku-defer-settle"` (the CLI's own `me` argument is validated by `C.PREFIX_RE`/`_identity_or_die`, `.claude/hooks/stop/worklist.py:882-885`, which — confirm — rejects a value shaped like `"haiku-defer-settle"` if it doesn't match a real resolvable session identity, or explicitly reserve it the way `AGENT_RESERVED_DIRS` reserves directory names, `.claude/hooks/stop/wl_store.py:173-175`).
- **Cap pair (hard limit 6):** script 6 corroborated `settled` verdicts in one session-state doc; assert the 6th is reported, not acted on.

---

### Critical Files for Implementation

- /home/developer/console/.claude/hooks/stop/wl_judge.py
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/hooks/stop/wl_store.py
- /home/developer/console/.claude/hooks/stop/worklist.py
- /home/developer/console/.claude/hooks/stop/worklist_messages.py
- /home/developer/console/.claude/hooks/stop/wl_bravedefault.py (pattern to clone for the new `wl_defersettle.py` module)
- /home/developer/console/.claude/hooks/stop/test-judge-schema.py (mocking pattern to clone for `test-defer-settle.py`)
- /home/developer/console/CLAUDE.md (rule 2 / rule 4 citations the catalog quotes verbatim)
- /home/developer/console/agent/DECISIONS.md (D-M1 row)

## Implementation notes (2026-09-24)

Where the build departs from the design above, and why:

- **`execute_default` reaches the expired demand one stop later, not the same stop.** The expired list (`wl_checks.py`, `V_DEFER_EXPIRED`) is built in the static battery, which runs before the judge section, so a verdict corroborated during the judge cannot join that stop's list. The corroborated verdict is banked with `accelerate: true`, and `wl_defersettle.accelerated()` adds the item to the next stop's expired list, still ahead of `DEFER_WINDOW_MIN`.
- **Only present facts are emitted.** Section 8 left this open; the controls pin it (`test-defer-settle.py`, class 1 control).
- **Standing-rule citations are derived, not hard-coded.** Each catalog quote must appear verbatim on one line of `CLAUDE.md`; the line it is found on is the citation, and a reworded rule emits no fact.
- **`wl_judge.py` changed too** (not in the file list above): `JUDGE_SCHEMA` gains `defer_settle`, `judge_schema_for` requires it on `DEFER_SETTLE_MARKER`, and `DS.check_catalog(FORBIDDEN_ORDERS)` runs at the bottom of the module, because `wl_judge` imports `wl_defersettle` before it defines `FORBIDDEN_ORDERS`.
- **`CITE_RE` gained nested dotfiles.** `private/account/.env` line 12 did not match any branch, so an env-fact settle's evidence could never pass `completion_evidence`. The dotfile branch now takes an optional directory prefix; `.ci/policy/.dead-bash-allowlist:19` was uncitable for the same reason.
- **The reserved actor is refused in `worklist.py`'s item verbs**, because `check_me` accepts any shape-valid `<me>` on a terminal with no session id.
- **The cached stop verdict is bypassed while a settle batch is pending**, or a second sample could never be taken. A non-acting verdict banks `done` against the item's stamp and fact signature, so an item is asked at most twice per generation.

## Boxes

- [x] Add `wl_defersettle.py` (sibling module, per section 0's recommendation): `gather_facts` with the three closed fact kinds (`env_key_present`, `standing_rule_match`, `artifact_exists`), the hand-maintained standing-rule catalog (two entries day one: `big-bang-packaging`, `model-routing-haiku`), `DEFER_SETTLE_SCHEMA`/`DEFER_SETTLE_PROMPT`, and the corroboration bank (section 5).
    (ticked) 2026-09-24T07:22:23Z by d778be9d: .claude/hooks/stop/wl_defersettle.py:291 gather_facts (three closed fact kinds), .claude/hooks/stop/wl_defersettle.py:88 CATALOG (big-bang-packaging, model-routing-haiku), .claude/hooks/stop/wl_defersettle.py:307 DEFER_SETTLE_SCHEMA, .claude/hooks/stop/wl_defersettle.py:482 apply_stop corroboration bank; python3 .claude/hooks/stop/test-defer-settle.py exit 0, 74 controls
- [x] Wire the creation-time refusal into `worklist.py --defer` (section 1a): a fail-open classifier call before `S.set_state`, refusing creation only on a confident `settled` verdict, never blocking on a classifier error.
    (ticked) 2026-09-24T07:22:23Z by d778be9d: worklist.py --defer calls wl_defersettle.classify_one (.claude/hooks/stop/wl_defersettle.py:569) before S.set_state, refuses only on settled, falls through on error or raise; controls at .claude/hooks/stop/test-defer-settle.py:544 (refusal, error, uncertain, raise) pass, python3 .claude/hooks/stop/test-defer-settle.py exit 0
- [x] Wire the stop-time batch into `wl_checks.py` beside `defer_audit`'s construction (section 1b): age gate `DEFER_SETTLE_MIN` (30min), fact-gathering before batching, `DEFER_SETTLE_BATCH` cap (4).
    (ticked) 2026-09-24T07:22:33Z by d778be9d: wl_checks.py: settle_batch = wl_defersettle.build_batch(...) beside audit_batch (age gate DEFER_SETTLE_MIN 30, facts before batching, DEFER_SETTLE_BATCH 4), prompt_section in the judge extra, cache bypassed while pending, apply_stop before the admission verdict; structural controls .claude/hooks/stop/test-defer-settle.py:636 pass, python3 .claude/hooks/stop/test-defer-settle.py exit 0
- [x] Implement the evidence-gated tick path (section 6): `by=haiku-defer-settle` reserved actor, `completion_evidence`/`issue_only_evidence` gate reused from `--plan-tick`, and the `execute_default` path reusing `V_DEFER_EXPIRED`'s existing expired-list mechanism rather than a new one.
    (ticked) 2026-09-24T07:22:24Z by d778be9d: .claude/hooks/stop/wl_defersettle.py:482 apply_stop ticks by reserved actor .claude/hooks/stop/wl_defersettle.py:46 only through .claude/hooks/stop/wl_defersettle.py:474 _default_gate (completion_evidence + issue_only_evidence); execute_default banks accelerate and .claude/hooks/stop/wl_defersettle.py:555 accelerated() feeds the V_DEFER_EXPIRED list; controls .claude/hooks/stop/test-defer-settle.py:118 .claude/hooks/stop/test-defer-settle.py:175 .claude/hooks/stop/test-defer-settle.py:469, exit 0
- [x] Implement the six hard limits in section 7, including the per-session auto-settle cap (suggest 5, mirroring `REGGATE_CAP`) and the `FORBIDDEN_ORDERS` scan on catalog `action` text at module-authoring time.
    (ticked) 2026-09-24T07:22:24Z by d778be9d: six limits: corroboration .claude/hooks/stop/wl_defersettle.py:482, catalog scan .claude/hooks/stop/wl_defersettle.py:125 (+ wl_judge FORBIDDEN_ORDERS call), evidence gate .claude/hooks/stop/wl_defersettle.py:474, Fact has no value field, reserved actor refused in worklist.py item verbs, SETTLE_CAP .claude/hooks/stop/wl_defersettle.py:51; pairs at .claude/hooks/stop/test-defer-settle.py:379 .claude/hooks/stop/test-defer-settle.py:469 .claude/hooks/stop/test-defer-settle.py:494 .claude/hooks/stop/test-defer-settle.py:518 .claude/hooks/stop/test-defer-settle.py:544, python3 .claude/hooks/stop/test-defer-settle.py exit 0
- [x] Add `test-defer-settle.py` per section 8's three fact classes plus the four cross-cutting control pairs (fail-safe direction, no-corroboration, secret-never-leaves-Python, reserved-actor, cap).
    (ticked) 2026-09-24T07:22:24Z by d778be9d: .claude/hooks/stop/test-defer-settle.py:118 .claude/hooks/stop/test-defer-settle.py:175 .claude/hooks/stop/test-defer-settle.py:239 three fact classes + control pairs fail-safe .claude/hooks/stop/test-defer-settle.py:306, no-corroboration .claude/hooks/stop/test-defer-settle.py:379, secret, reserved .claude/hooks/stop/test-defer-settle.py:544, cap .claude/hooks/stop/test-defer-settle.py:494; python3 .claude/hooks/stop/test-defer-settle.py exit 0, 74 controls; 15 planted defects each turn it red (exit 1)
- [x] Run the new test file and the full `wl_judge`/`wl_checks` suite; confirm no regression.
    (ticked) 2026-09-24T08:24:04Z by d778be9d: python3 .claude/hooks/stop/test-defer-settle.py exit 0 (76 controls, 15 planted defects each exit 1); all 16 stop-hook test-*.py exit 0 (test-judge-schema 547 controls); pytest .claude/rediacc_hooks/tests 7606 passed 12 failed: 2 own fixed (test_hooks_delegates TMPDIR leak, test_117 arity map), 5 waiter/report-queue env failures pass on foreground rerun, 4 guard-differential pid divergences and plan-fidelity 215/216 are outside this change (WORKLIST_JUDGE=off makes the defer-settle paths inert there)

