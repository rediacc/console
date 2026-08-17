# PLAN: runtime caller-identity awareness for the worklist CLI

Status: DESIGN. Written 2026-08-05 by a planning sub-agent of session `d136ac61`.
Scope: `.claude/hooks/stop/` only.

---

## 0. The one-paragraph answer

The framing I was handed was right about the defect and wrong about its cause. A
CLI process **can** know who is running it: `CLAUDE_CODE_SESSION_ID` is set, live,
in every Bash-tool child, and `wl_report.reader_id()` already reads it. So the
answer is **warn at the call**, not "warn at the next stop". And the root cause is
not a pre-compaction identity change: compaction demonstrably does **not** rotate
the session id (proven twice inside one transcript). `4c3e095a` was an
*agent-namespace token* copied out of a Task-spawn tool result and frozen as a
hand-typed `<me>` argument. Every `<me>` in this CLI is accepted on shape alone;
nothing has ever compared one to reality.

---

## 1. Findings, with evidence

### 1.1 What the hook already knows

`session_id` enters the Stop path from the event payload and is never normalised
away:

- `wl_checks.py:1372` — `session_id = event.get("session_id", "")`, the full UUID.
- `wl_checks.py:1373` — `me8 = (session_id or "unknown")[:8]`, used only to key
  sidecar filenames.
- `wl_checks.py:1604` — the hook writes `<worklist>.lastevent-<me8>.json` holding
  the whole event, `session_id` included. **This is the only writer**; `worklist.py:427`
  and `worklist.py:658` merely read it. That exclusivity is load-bearing in §3.3.

Nothing anywhere compares the event's `session_id` to a CLI-supplied `<me>`. The
closest existing comparison is `wl_checks.py:822`, `xsession_ok()`, which checks
`C.same_session(r["from"], session_id)` — but that validates a *citation in the
Remaining section*, not the identity a command was issued under.

**Does `C.same_session` (`wl_core.py:145-149`) help or hurt?** Both, and the split
matters for the design:

- It **helps**: the CLI passes an 8-char prefix and the event carries a full UUID.
  Symmetric prefix matching is what makes them comparable at all.
- It **hurts** in one specific way: symmetry means a *short* `me` matches
  promiscuously. `same_session("d", "d136ac61-…")` is `True`, so `--add d "x"`
  would sail through a naive check and create an item that every session whose id
  starts with `d` claims as its own.
- It did **not** hurt in the incident. `4c3e095a` and `d136ac61` share no prefix, so
  `same_session` correctly said "different". It just was never asked.

Do **not** change `same_session`. Its ten-plus other callers compare *peer* ids,
where symmetry is correct. §3.2 introduces a stricter predicate for the one place
where `me` is always a claim about *self*.

Also relevant: `C.owned_by_me` (`wl_core.py:135-142`) returns `True` for an
**untagged** owner. Untagged items are claimed by everyone. Out of scope here, but
it is the same family of "identity defaults are generous" and worth remembering.

### 1.2 Every verb taking `<me>`, and the write/read asymmetry

Sub-agent-produced table, spot-checked by me at the sites marked ✓.

| Verb | `<me>` at | Parsed | W/R | Validation today |
|---|---|---|---|---|
| `--add` | argv 1 | `worklist.py:330` ✓ | W (`by` + `o`) | PREFIX_RE ✓ |
| `--triage` | argv 1 | `worklist.py:330` | W+R | PREFIX_RE |
| `--tick` | argv 1 | `worklist.py:330` | W+R | PREFIX_RE |
| `--defer` | argv 1 | `worklist.py:330` | W+R | PREFIX_RE |
| `--update` | argv 1 | `worklist.py:330` | W+R | PREFIX_RE |
| `--lease` | argv 1 | `worklist.py:330` | W+R | PREFIX_RE |
| `--reap` | argv 1 | `worklist.py:650` | W+R | PREFIX_RE |
| `--list --open` | argv 2, **optional** | `worklist.py:310` ✓ | R | **NONE** ✓ |
| `--state` | argv 2 | `worklist.py:493` ✓ | W (sidecar key) | **NONE** ✓ |
| `--brief` | argv 2 | `worklist.py:623` ✓ | W (the roster!) | **NONE** ✓ |
| `--loop` | argv 2 | `worklist.py:599` ✓ | W | **NONE** ✓ |
| `--ask` | argv 1 | `wl_requests.py:316` ✓ | W (`from`) | PREFIX_RE ✓ |
| `--answer` / `--decline` / `--ack` | argv 1 | `wl_requests.py:316` | W (`by`) + R | PREFIX_RE |
| `--poll` | argv 1 | `wl_requests.py:424` ✓ | W (marker) + R | PREFIX_RE **+ len≥8** ✓ |
| `--wait` | argv 1 | `wl_wait.py:411` | W (heartbeat) + R | PREFIX_RE + len≥8 |
| `--reports --read` | argv 1 | `wl_report.py:878` | W (`by`) | PREFIX_RE |
| `--reports --list --as` | flag, **optional** | `wl_report.py:834` → `reader_id` `wl_report.py:250-264` ✓ | R | **NONE**, defaults to env |
| `--requests` | — none | `wl_requests.py:294` | R (unfiltered) | n/a |

Three things fall out of that table:

1. **`PREFIX_RE` (`wl_core.py:54`) is a shape check, not an identity check.** It
   accepts any `[A-Za-z0-9][A-Za-z0-9._-]{0,31}`. `4c3e095a` passes it perfectly.
2. **Four write verbs have no validation at all**, and one of them — `--brief` —
   *is* the session roster (`worklist.py:626-627` appends `<prefix> <stamp> <text>`
   to `.sessions`, read back by `wl_store.read_briefs`). The registry of who exists
   is populated by an unvalidated command-line string.
3. **The 8-char floor already exists, on exactly two verbs.** `wl_requests.py:424-428`
   refuses a short `--poll` prefix with a comment that is the whole argument for
   generalising it: *"A short prefix would name a DIFFERENT marker than the Stop hook
   derives from the full session id, silently disabling the fast path, so misuse is
   refused rather than half-working."* That reasoning applies verbatim to `.state-`,
   `.reaped-`, `.lastevent-`, `.waiter-` and item ownership. It was simply never
   generalised.

The write/read asymmetry the lead named is real, but the sharper statement is:
**writes and reads key off the same unvalidated string, so a single typo splits a
session into two half-sessions, each internally consistent.** That is why nothing
downstream could detect it — every individual operation succeeded.

### 1.3 The CLI *can* tell. This is the finding that changes the design.

Live `env` from a Bash-tool child in this very session:

```
CLAUDE_CODE_SESSION_ID=d136ac61-8ff7-4004-af50-c318d23b61b0
CLAUDE_CODE_CHILD_SESSION=1
CLAUDE_PID=1781622
```

It matches the Stop event's `session_id` exactly. Corroborating details:

- The harness injects it per-child-spawn from its own JS
  (`CLAUDE_CODE_SESSION_ID:e.sessionId` in the 2.1.221 bundle) and carries it on the
  shell-snapshot passthrough allowlist. That is platform-neutral — no `/proc`, no
  filesystem assumption, so it satisfies the linux/windows/macOS constraint.
- `wl_report.py:250-264` `reader_id()` already depends on it, and its docstring
  records that the name was verified against the live environment rather than
  guessed. **Precedent exists; it was just never generalised past one verb.**
- I ran the check as a **sub-agent** and still saw the *parent's* id. Sub-agents
  share the top-level `CLAUDE_CODE_SESSION_ID`. This is important: it means a
  sub-agent tagging items with the parent prefix is *correct*, and an env-match rule
  will not fire on the sub-agent fleet. A whole class of false positives is
  structurally absent.
- The harness rotates the value on `/clear` (`conversation_reset` reassigns it), so
  it is "current id", not "id at startup". Correct behaviour for our purpose.

Alternatives, for the record — all rejected:

- **Freshest `.lastevent-*.json` mtime**: gives the full id but picks the wrong
  session under concurrency. Right now `lastevent-2fd369e0.json` (22:02) and
  `lastevent-d136ac61.json` (22:00) are both live. `.lastevent-unknown.json` also
  exists, so the candidate set is not even all-real-ids.
- **Freshest transcript `.jsonl` mtime**: same ambiguity; four live sessions share
  this project dir.
- **`.sessions` briefs**: not an identity source. `sole_live_session`
  (`wl_store.py:1025-1038`) takes `session_id` as an *input*. It answers "am I
  alone", never "who am I".
- **`/proc` parent walk**: works on Linux, but the `claude` process's own environ
  does *not* contain the variable (it is injected into children only), so the walk
  is strictly redundant with reading your own env — and it is Linux-only, which
  would regress a module that goes out of its way to work on Windows
  (`wl_core.py:167-171`).

### 1.4 A pre-compaction identity change is NOT what happened

The hypothesis was worth testing and it is refuted:

- `~/.claude/projects/-home-muhammed-monorepo-console/d136ac61-….jsonl` (21 MB,
  12,675 records, 2026-07-23 → 2026-08-05) contains **exactly one** `sessionId`
  value across all 12,574 records that carry the field.
- It contains **two** `{"type":"system","subtype":"compact_boundary"}` records
  (lines 4227 and 9095, at 2026-08-04T18:26:01Z and 2026-08-05T10:49:00Z). The
  `sessionId` is identical either side of both.
- No `4c3e095a-*.jsonl` exists anywhere under `~/.claude`.

**What a stale identity actually looks like on disk**, since that is the useful
half of the question:

- Line 469 of that transcript, 2026-08-04T08:41:52Z, is a Task-spawn tool result
  containing `agent_id: search-renet2@session-4c3e095a`.
- Line 559, 2026-08-04T09:03:06Z — 21 minutes later — is
  `worklist.py --add 4c3e095a "…"`, and that timestamp is byte-for-byte the first
  `by:"4c3e095a"` event in the store.
- The `@session-` token is a *different id space* that rotates freely. It rotated
  three times inside this one continuous transcript (`d136ac61` → `4c3e095a` →
  `465e991b`). `4c3e095a` was already stale from 18:00 on 2026-08-04, and the
  session kept writing under it for a further 26 hours.
- Both literals were emitted **from the same process** for ~24 hours: 219 CLI calls
  as `4c3e095a` and 20 as `d136ac61`, ending in the same second.

Implication for the design: **no alias table and no compaction migration are
required.** A one-shot repair for the damage already done *is* required (§3.4), but
it is remediation, not an ongoing mechanism. The design does not have to assume every
session will eventually be renamed.

Corroborating oddity, worth one line: `~/.claude/tasks/` contains directories for
*both* namespaces — `session-d136ac61/` (empty) and `session-4c3e095a/` (empty). I
checked whether `C.tasks_dir` is therefore reading a dead namespace, as one
sub-agent claimed. **It is not.** 156 `session-*` dirs exist and 12 hold JSON (e.g.
`session-b9491d9c/` has 36). The namespace is correct; those two dirs are simply
empty. Recording the correction so nobody re-chases it.

### 1.5 The phantom signature — verified by me, not reported to me

This is the backstop detector's whole basis, so I checked it directly rather than
trusting the sub-agent.

`.lastevent-<prefix>.json` is written at exactly one place, `wl_checks.py:1604`,
inside `run_stop`. **An identity with no `.lastevent-` file is an identity for which
a Stop hook has never run.** A real session always stops.

Live store, `/tmp/claude-worklist/`:

```
lastevent-2fd369e0.json  lastevent-47a18f58.json  lastevent-50601903.json
lastevent-84611aab.json  lastevent-b9491d9c.json  lastevent-d136ac61.json
lastevent-d8d4aea1.json  lastevent-dc8186aa.json  lastevent-unknown.json
                       <-- NO lastevent-4c3e095a.json

state-4c3e095a.json       36 bytes   (CLI-written: only {"state_sig":…})
state-d136ac61.json     2842 bytes   (hook-written: full doc)
```

240 events, a `.pollmark-`, a `.waiter-`, a `.state-` — and no `.lastevent-`. The
signature is exact and binary. The byte-size asymmetry on `.state-` corroborates it
(the CLI writes only `state_sig`, the hook writes the full document) but is a worse
test; use the `.lastevent-` absence.

Noise check, done before recommending it: `state-spotchk1`, `state-spotchk2` and
`state-40fa3b7c` also lack `.lastevent-`. They are test residue and a session that
never stopped. This is why §3.3 gates the report on **owning open work** — a phantom
that owns nothing is not worth a word.

### 1.6 Blast radius of a false positive

Legitimate multi-identity situations, enumerated so the check can be tuned to miss
all of them:

| Case | Env state | Verdict under this design |
|---|---|---|
| Sub-agent runs the CLI | inherits **parent's** id (verified) | passes — tagging as parent is correct |
| Cron-driven `--poll` | same session, inherits | passes |
| Operator in a plain terminal | `CLAUDE_CODE_SESSION_ID` **unset** | **silent pass** — cannot verify, so do not accuse |
| The test suite (`test-worklist-v5.sh`) | sets `WORKLIST_SESSION_ID` or leaves unset | passes deliberately |
| Operator cleaning up a dead session's items | unset, or declares `WORKLIST_SESSION_ID=<that id>` | passes |
| `--ask <me> <to>` | `me` is still self; `to` is the peer | passes |
| `--tick` of another session's item | already refused by the *ownership* check | unchanged |

I could not construct a legitimate case where a session with a resolvable env id
should write under a different `<me>`. The one forward risk is a harness change that
gives sub-agents their own ids; §5 carries it as an open question with a kill switch.

The false-positive cost the lead is right to fear lands almost entirely on the
**Stop-hook** side, not the CLI side. §3.3 is therefore report-only and gated on
open work, while §3.2 refuses — and §3.2 refusing is safe precisely because it is
self-correcting in one turn and prints the right prefix.

---

## 2. Recommendation in one line

Resolve the true session id from the environment in the CLI process, **refuse** any
`<me>` that is not a ≥8-char prefix of it, stay silent when the environment cannot
answer, and add one report-only Stop-hook backstop that names identities which write
to the store but have never stopped.

---

## 3. Design

### 3.1 `wl_core.resolve_session_id()` — one definition

```
WORKLIST_SESSION_ID   (test / operator override; an identity ASSERTION)
  -> CLAUDE_CODE_SESSION_ID
  -> ""   (unresolvable)
```

Returns `""` rather than raising. `""` means *cannot verify* and every caller treats
it as pass.

**Decision: the override is `WORKLIST_SESSION_ID=<id>`, not a `…_CHECK=off` flag.**
Declaring who you are is honest and serves the test suite and the operator with one
mechanism; a suppression flag would be an escape hatch needing a `BLOCKER:` reason
under `docs/agent/suppressions.md`, and would be reachable by a session trying to get
past its own mistake. *Rejected alternative:* a boolean bypass — it suppresses the
check without stating a claim, which is the exact shape this repo's suppressions doc
exists to prevent.

**Decision: refactor `wl_report.reader_id()` (`wl_report.py:250-264`) to call this.**
Two definitions of "who am I" is how the next drift starts. Its docstring's hard-won
note about `CLAUDE_CODE_SESSION_ID` vs `CLAUDE_SESSION_ID` moves with it.

### 3.2 Layer 1 — refuse at the call (primary defence)

One helper, `wl_core.check_me(me) -> (ok, message)`, applied at every `<me>` parse
site. The predicate is deliberately **stricter** than `same_session`:

```
sid = resolve_session_id()
if not sid:          return OK          # unverifiable -> silent pass
if len(me) < 8:      return REFUSE      # promiscuous prefix
if not sid.startswith(me): return REFUSE
return OK
```

- **Length floor 8, everywhere.** This generalises the floor `--poll` has carried
  since it was written (`wl_requests.py:424-428`) and its stated reason. It closes
  the `--add d` hole that `same_session`'s symmetry would otherwise leave open.
- **`sid.startswith(me)`, not `same_session(me, sid)`.** Asymmetric on purpose: on
  the CLI, `me` is always a *claim about self*, never a peer id. A full UUID still
  passes.
- **Refuse, do not warn.** A warning on stderr next to a successful command is what
  the failing session would have skimmed past; the command succeeded, so nothing
  demanded attention. A non-zero exit costs one turn and the message carries the
  copy-paste fix. Replayed against the real trace: the very first bad call
  (`--add 4c3e095a`, 2026-08-04T09:03:06Z) fails immediately and names `d136ac61` —
  26 hours and one missed authorisation earlier than the hand-dump that actually
  found it.
- **Refuse, do not auto-correct.** Silently substituting the env id would make the
  class impossible, but it would also retarget a deliberate operator command without
  saying so, and it would teach nothing. *Rejected.*
- **Symmetric across read and write.** In the incident the *read* (`--poll d136ac61`)
  was the correct one and the writes were wrong; the next occurrence could be the
  other way round. Refusing both sides is simpler to reason about and to test.

Message shape (goes in `worklist_messages.py`, per the existing `M.CLI_*` convention):

```
identity mismatch: you passed <me>=4c3e095a but this session is
d136ac61-8ff7-4004-af50-c318d23b61b0 (CLAUDE_CODE_SESSION_ID).
Writing as one identity and reading as another gives you two inboxes and
neither of them is complete.
  use:  worklist.py --add d136ac61 ...
If you really mean to act as another session, declare it:
  WORKLIST_SESSION_ID=<that id> worklist.py ...
```

Naming the variable matters: it makes the mechanism inspectable by the next session
that hits it.

**Sites to change** (13, and the count is the point — a partial rollout reproduces
the bug in the verbs that were missed):

- `worklist.py:331` — the shared `--add/--triage/--tick/--defer/--update/--lease` gate
- `worklist.py:310` — `--list --open` (currently unvalidated)
- `worklist.py:493` — `--state` (currently unvalidated)
- `worklist.py:599` — `--loop` (currently unvalidated)
- `worklist.py:623` — `--brief` (currently unvalidated; **this one is the roster**)
- `worklist.py:652` — `--reap`
- `wl_requests.py:317` — `--ask/--answer/--decline/--ack`
- `wl_requests.py:424` — `--poll` (replaces its bespoke floor)
- `wl_wait.py:411` — `--wait` (replaces its bespoke floor)
- `wl_report.py:878` — `--reports --read`
- `wl_report.py:834` — `--reports --list --as` (validate an *explicit* `--as`; the
  env default is already correct by construction)

### 3.2b Sweep the class: `--ask <to>` is unvalidated too

`wl_requests.py:320-321` validates the **recipient** with `PREFIX_RE` only. Asking a
prefix that no session has ever briefed posts into an inbox nobody reads. That is the
same defect from the sender's side, and the incident shows its cost: a peer's ask to
`4c3e095a` eventually auto-escalated with *"recipient 4c3e095a silent for 2062min"* —
34 hours late.

**Decision: refuse `--ask <me> <to>` when `to` has no entry in `.sessions`** (via
`wl_store.read_briefs`), listing the prefixes that do. Not a staleness check — a
*never-existed* check, so a briefly-idle peer is unaffected. `to == "*"` and
`to == "operator"` bypass it.

### 3.3 Layer 2 — the phantom-identity backstop (Stop hook, report-only)

Layer 1 cannot heal history, and its unverifiable-env path is a deliberate hole. The
hook closes both.

**The check.** For each distinct `by` in the event log:

1. Skip if `same_session(by, session_id)`.
2. Skip unless `.lastevent-<by[:8]>.json` is **absent** (§1.5).
3. Skip unless its earliest event is older than `WORKLIST_PHANTOM_MIN` (default 30).
   A brand-new session writes before its first stop; that window is not a phantom.
4. Skip unless it **owns open work**: an open item in the fold, or an open request
   with `from == by` or `to == by`. This is the noise gate — `spotchk1`/`spotchk2`
   exist in the live store and must stay silent.

**The instrument control, inside the check itself.** If **zero** `.lastevent-*` files
exist in the store dir, the test is blind (a wiped `TMPDIR`) and would otherwise
indict every identity at once. In that case report the *blindness*, in words, and
flag nothing. A check that cannot fail must say so out loud; this repo found six
today that did not.

**Emission: report-only, priority 1, sticky.** Never blocking. Note the constraint —
`OUTQ_PER_STOP` defaults to 1 (`wl_checks.py:999`), so a priority-2 note can queue
behind others for many stops. An identity split is not something to ration; priority
1 puts it at the head (`outq_drain` is highest-priority-first). *Rejected:* blocking.
This runs on every session's Stop path and the fix (§3.4) is not always the session's
to make.

Text names the identity, its event count and age, what it owns, and the exact repair
verb from §3.4.

### 3.4 Layer 3 — `--reassign`, the one-shot repair

Layer 2 without a fix verb is a nag. Add:

```
worklist.py --reassign <me> <phantom-prefix>
```

- `<me>` must pass §3.2 (so you cannot reassign *to* a fiction).
- `<phantom-prefix>` must satisfy the §3.3 phantom test (no `.lastevent-`), or the
  session must already be dead by the existing liveness rules. This is what stops
  `--reassign` becoming a way to steal a live peer's items — the rule CLAUDE.md
  states as "never tick or remove an item that is not yours".
- **Appends `reassign` events; never rewrites lines.** Both logs are append-only and
  fold-derived (`wl_requests.read_requests` docstring, `wl_requests.py:56-58`), which
  is what makes the lock-free design sound. `read_requests` gains a `reassign` arm
  that rebinds `from`/`to`; the item fold gains the same for `o`.
- **Open items and open requests only.** History stays truthful: `4c3e095a` really
  did write those 240 events, and a log that lies about that is worse than one that
  is untidy.

Scope decision: this exists to repair the live store *once* and to give §3.3 a verb
to point at. It is not a compaction-migration mechanism — §1.4 establishes none is
needed.

---

## 4. Proving it fires

### 4.0 The hazard that decides whether any of this is real

**`test-worklist-v5.sh` inherits `CLAUDE_CODE_SESSION_ID` from whoever runs it, and
its ambient scrub does not strip it.** Lines 16-21 unset every `WORKLIST_*` variable —
deliberately, with a good comment about developers retuning the suite by accident —
but the scrub matches `WORKLIST_*` only. The fixture id is
`SID="deadbeef-1111-2222-3333-444444444444"` (line 25).

That produces **two opposite failures from one omission**:

- **Run from inside a Claude session**: `CLAUDE_CODE_SESSION_ID=d136ac61-…` is live, so
  every fixture prefix mismatches and L1 refuses. Mass breakage that looks like a
  broken feature.
- **Run in CI**: the variable is unset, L1 takes its silent-pass path, and **every L1
  case passes vacuously**. A green suite proving nothing — the exact trap
  `docs/agent/TRAPS.md` is about, arriving in the very change meant to close a
  can't-fail gap.

The second is the dangerous one, because it is green.

**Required, and it is step 2's first commit, not a cleanup:**

1. Extend the ambient scrub to unset `CLAUDE_CODE_SESSION_ID` and `CLAUDE_SESSION_ID`
   alongside `WORKLIST_*`. The suite then behaves identically in CI and locally.
   (`WORKLIST_SESSION_ID` is already covered by the existing `WORKLIST_*` pattern, and
   cases re-export it after the scrub exactly as they already do for `WORKLIST_FOCUS`.)
2. Arm every case that drives the CLI with an explicit
   `WORKLIST_SESSION_ID="$SID"`. Measured scale: **99** call sites pass `deadbeef`
   (which matches `SID`, so they pass once armed) and roughly **12** pass a different
   prefix on purpose — `cafe1234` ×10, `other123`, plus `$pfx`/`$i` variants — modelling
   a *peer* session. Those must declare the peer's id for that call:
   `WORKLIST_SESSION_ID=cafe1234-… python3 "$HOOK" --ask cafe1234 …`. Mechanical, bounded,
   ~110 sites.
3. **A meta-control for the scrub itself**, because step 1 is a check on a check: one
   case runs a FIRE command with *no* explicit `WORKLIST_SESSION_ID` and asserts it
   **passes**. It can only pass if the scrub really removed the ambient id. Run it once
   from inside a Claude session and once with the variable forced, and it must give the
   same verdict both times.

Without all three, the L1 table is decoration.

### 4.1 Case design

Convention already in `test-worklist-v5.sh`: every FIRE case is paired with a SILENT
control off the same fixture differing in **one planted fact** (see its own comments
at lines 2873-2875, 3577, 5939 — one of which records that a control satisfied by an
unbuilt fixture is worse than no control, because that shipped once).

### L1 — per verb, table-driven

For **each** of the 13 sites in §3.2:

- **FIRE**: `WORKLIST_SESSION_ID=d136ac61-… worklist.py <verb> 4c3e095a …` → exit ≠ 0,
  stderr contains `d136ac61`. This replays the actual defect verbatim.
- **CONTROL A** (one planted fact — the prefix): same command with `d136ac61` → exit 0
  and the effect actually happens (item added / brief appended / poll marker written).
- **CONTROL B** (instrument blind): `env -u CLAUDE_CODE_SESSION_ID -u WORKLIST_SESSION_ID`
  + the FIRE command → exit 0. This proves both that the unset-env pass exists **and**
  that FIRE was caused by the check rather than by an unrelated failure.
- **CONTROL C** (length floor): `--add d13` refused, `--add d136ac61` accepted.

**Anti-vacuity, and it is the most important test in the plan.** The bug's shape is
"a rule applied to some call sites and not others". So the suite must derive the verb
list from the **source** — grep the dispatch sites in `worklist.py`, `wl_requests.py`,
`wl_wait.py`, `wl_report.py` for `<me>` parses — and **fail if any verb it finds has no
FIRE case in the table**. Without that, adding verb 14 next month silently reopens the
hole and the suite stays green.

### L2 — phantom identity

Fixture store, hook run as `d136ac61`:

- **FIRE**: events `by=phantom01` older than the threshold, no
  `.lastevent-phantom01.json`, and one open item owned by `phantom01` → report names
  `phantom01` and prints the `--reassign` verb.
- **CONTROL A**: identical + `.lastevent-phantom01.json` present → silent.
- **CONTROL B**: identical but events younger than `WORKLIST_PHANTOM_MIN` → silent.
- **CONTROL C**: identical but `phantom01` owns nothing → silent. (This is the one
  that keeps `spotchk1`/`spotchk2` quiet in the real store.)
- **CONTROL D** (instrument blind): zero `.lastevent-*` files → assert the *blindness
  wording appears*, and that no identity is flagged. Asserting silence here would be
  indistinguishable from the check not running.

### L3 — reassign

One test asserting **before and after** in the same run: `--list --open <me>` and
`--poll <me>` must *not* show the item/request before, and *must* show them after.
The before-assert is the control — without it the test passes on a store that already
contained them.

### Live proof, after the suite

Run against the real store, in order: (1) `worklist.py --add 4c3e095a x` now refuses
and names `d136ac61`; (2) the next full stop reports `4c3e095a` as a phantom owning
open work; (3) `--reassign d136ac61 4c3e095a`; (4) `--poll d136ac61` now surfaces
`#3b28601e` and `#cf377b44`, the two messages that were lost. Step 4 is the one that
proves the whole thing, because those are the real messages this defect ate.

---

## 5. Sequencing

1. `wl_core.resolve_session_id()` + `check_me()`, with unit coverage. Pure functions,
   no behaviour change, no file contention.
2. Wire L1 into all 13 sites + the `--ask <to>` roster check (§3.2b). Table-driven
   suite including the anti-vacuity derivation. **This is the piece that matters; if
   the session runs out of room, stop after it.**
3. Refactor `reader_id` onto the shared resolver; delete the duplicate.
4. L2 phantom check + its four controls.
5. L3 `--reassign` + test; operator runs it once against `4c3e095a`.
6. Live proof, step 4 above.

Steps 1-3 are independently valuable and independently shippable. 4-5 are the
backstop and can ride a second change.

## 6. File ownership and staging

Working tree for `.claude/hooks/stop/` is **clean** as of 2026-08-05T22:02Z
(`git status --porcelain` empty for that dir), but several files were written within
the last hour and this session's roster shows live peers:

| File | Last write | Needed by | Note |
|---|---|---|---|
| `wl_core.py` | 14:55 | steps 1, 2 | cold; additive only |
| `worklist.py` | 20:00 | step 2 | 6 sites |
| `wl_requests.py` | 14:56 | steps 2, 3.2b | cold |
| `wl_wait.py` | 18:47 | step 2 | 1 site |
| `wl_report.py` | **21:58 — HOT** | steps 2, 3 | `impl-reportinbox` is live here; stage last or hand it over |
| `wl_checks.py` | 20:07 | step 4 | large; single insertion point near `run_stop`'s allow tail |
| `worklist_messages.py` | 20:00 | steps 2, 4, 5 | new `M.CLI_*` / `M.N_*` constants |
| `test-worklist-v5.sh` | 20:20 | all | append-only; likely contended |

Per CLAUDE.md rule 4: at most two writing agents, disjoint file sets. A clean split is
**A** = `wl_core.py` + `worklist.py` + `wl_requests.py` + `wl_wait.py`, **B** =
`wl_checks.py` + `worklist_messages.py` + `wl_report.py`. `test-worklist-v5.sh` is
append-only but shared; give it to exactly one of them or serialise the appends.

---

## 7. OPEN QUESTIONS

1. **Refuse or warn on L1?** Recommended default: **refuse** (non-zero exit). A
   warning beside a successful command is what the failing session skimmed past for 26
   hours. Refusal is self-correcting in one turn and the message carries the fix.
   Downside: if the harness ever gives sub-agents their own ids, every sub-agent CLI
   call breaks at once. Mitigation: the message names `WORKLIST_SESSION_ID`, so the
   unblock is one env var — and §5 step 2 lands before the backstop, so a bad
   interaction is visible early.

2. **Should there be a kill switch for L1?** Recommended default: **no separate
   switch**; `WORKLIST_SESSION_ID` is the escape and it is an assertion rather than a
   suppression. If the operator wants belt-and-braces against a harness change,
   `WORKLIST_IDENTITY_CHECK=off` is a two-line addition — but it then belongs in
   `docs/agent/suppressions.md` with a `BLOCKER:` reason and a liveness gate.

3. **Minimum prefix length 8?** Recommended default: **8**, matching the existing
   `--poll`/`--wait` floor, CLAUDE.md's tagging convention, and every `[:8]` sidecar
   key. Cost: an existing item tagged with a shorter prefix can no longer be ticked by
   that short tag. Grep the live store before landing; if any exist, `--reassign` them.

4. **Does `--reassign` move requests as well as items?** Recommended default: **yes,
   open ones**. The incident's real damage was in `.requests` — a repair that leaves
   the lost messages unreachable fixes the symptom the operator did not complain about
   and skips the one they did.

5. **`WORKLIST_PHANTOM_MIN` default?** Recommended default: **30 minutes**. Long enough
   that no real session is mid-first-turn, short enough that a full working session
   surfaces the problem the same day. Weak opinion; any value in 15-60 is defensible.

6. **Does the operator want the one-shot repair run now, or after the checks land?**
   Recommended default: **after**, so L2's FIRE case can be demonstrated against the
   real `4c3e095a` before it is cleaned up. Running the repair first destroys the best
   available live fixture.

## 8. What I did not verify

- The exact `outq_add` priority-1 drain ordering under contention with other sticky
  priority-1 entries. I read the drain comment (`wl_checks.py` allow tail: "highest
  priority first and FIFO inside a priority class") but did not run it. If L2's note
  turns out to queue behind another sticky priority-1 section for several stops, it
  should bypass the queue the way the judge line does.
Closed since drafting, both by running the check rather than reasoning about it:

- **Hard-coded prefixes in command templates: none.** Grepping `.claude/` for
  `worklist.py --<verb> <literal>` across `*.md`, `*.json` and `*.sh` (excluding the
  test files) returns nothing. Step 2 has no template-breakage risk.
- **The test suite has no shared "run the CLI" helper.** `run()` at
  `test-worklist-v5.sh:217` feeds the *hook* a Stop event; CLI cases invoke
  `python3 "$HOOK" …` inline with per-case env. The L1 table needs its own small
  helper — and see §4.0, which is what that investigation actually turned up.
