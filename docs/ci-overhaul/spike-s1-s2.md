# Spikes S-1 and S-2, settled

Both spikes from [05-execution-guide.md](05-execution-guide.md) are settled by direct
measurement. This file records the evidence, what was measured versus inferred, and the
things that stayed open.

Date settled: 2026-07-30. Investigation was read-only against the repo; no file in the
tree was modified except this one, and nothing was dispatched, cancelled or commented on
in CI.

---

## The questions

**S-2.** Does `--max-budget-usd` actually BIND when `anthropics/claude-code-action` runs
under OAuth (`ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`), or is it silently ignored? Wave C's cost-control
section is about to claim a dollar stop exists.

**S-1.** Is `--model claude-sonnet-5` honoured at all? Haiku legitimately appears for the
action's internal sub-steps, so the thing to look for is the ABSENCE of sonnet in
`modelUsage` on a run that requested it.

---

## Evidence tier reached

**Higher than tier 1.** The guide listed source reading as the strongest available tier.
It was possible to go past it and run the experiment itself, locally, on the exact pinned
CLI build and under the same class of OAuth subscription credential, without dispatching
anything in CI:

- The action pin `fa7e2f0a29a126f0b81cdcf360561b36e44cf608` is tag `v1.0.180`, whose
  commit message is `chore: bump Claude Code to 2.1.217 and Agent SDK to 0.3.217`
  (`gh api repos/anthropics/claude-code-action/commits/fa7e2f0a...`).
- That exact CLI build is on this machine at
  `/home/muhammed/.local/share/claude/versions/2.1.217`, left behind by the local
  auto-updater.
- Local auth is `claudeAiOauth` with `subscriptionType: max` in
  `~/.claude/.credentials.json`, and no `ANTHROPIC_API_KEY` is set. That is the same auth
  class as `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` in CI, an `sk-ant-oat01` subscription token, not an
  API key.

So four tiers of evidence are present: action source at the pin, SDK source at the pin,
real CI artifacts, and a live experiment on the pinned binary. They agree.

Total cost of the live experiments: $0.49.

---

## S-2 verdict: the flag BINDS. It is a real dollar stop, but it is POST-HOC, not a ceiling

### Measured, live, under OAuth

Command, run in the scratchpad with the pinned binary, a ~16k-token filler prompt sized to
blow past the cap on the first request, and only `Bash(echo:*)` allowed:

```
/home/muhammed/.local/share/claude/versions/2.1.217 \
  -p --model claude-sonnet-5 --max-budget-usd 0.01 --max-turns 8 \
  --output-format json --setting-sources user --allowedTools 'Bash(echo:*)'
```

Exit code `1`, stderr empty, stdout:

```json
{"type":"result","subtype":"error_max_budget_usd","num_turns":1,
 "total_cost_usd":0.2340351,"terminal_reason":"budget_exhausted",
 "modelUsage":{"claude-sonnet-5":{"outputTokens":115,"costUSD":0.2340351, ...}},
 "errors":["Reached maximum budget ($0.01)"]}
```

**Control** (proves the flag is not a blanket abort): identical command with
`--max-budget-usd 100 --max-turns 2` ran past $0.22 with no budget halt and terminated on
`"subtype":"error_max_turns"`, `"terminal_reason":"max_turns"`,
`"errors":["Reached maximum number of turns (2)"]`, `total_cost_usd: 0.2224398`. So the
halt at `0.01` was budget-specific, not an artifact of passing the flag.

### The caveat that matters more than the verdict

The cap was $0.01. The run spent **$0.2340351**, a **23x overshoot**, and stopped after
turn 1.

This is by construction, not a bug. The check is
`function Irr(e){return e!==void 0&&nS()>=e}` at offset 245323106 in the 2.1.217 bundle:
accumulated cost compared against the cap, evaluated BETWEEN turns as messages are drained.
A single request's cost is not bounded by anything. So the guarantee is:

> total spend <= budget + the cost of one more turn

not "total spend <= budget". On PR #543's real review the average was $5.9255 over 61
turns, about **$0.097 per turn**, so on that workload a cap would overshoot by roughly a
dime. But a review whose first turn ingests a large diff and a 5 MB context can overshoot
by dollars before the first check ever runs, which is exactly what the local run
demonstrated.

Wave C's cost section may say a dollar stop exists. It must NOT say a hard cap exists.

### Why it binds under OAuth: no auth branch anywhere on the path

Cost accounting in 2.1.217 is pure token-times-price arithmetic with no auth-mode
condition:

- `function h$i(e,t){return t.input_tokens/1e6*e.inputTokens + t.output_tokens/1e6*e.outputTokens + ...}`
  at offset 242099028, and its price-table lookup `g$i` at 242099253. No subscription check,
  no API-key check.
- `function Iui(e,t,r){It.modelUsage[r]=t,It.totalCostUSD+=e}` at 239697890 accumulates it;
  `function nS(){return It.totalCostUSD}` at 239697939 reads it.
- `Irr` compares `nS()` to the cap. Nothing between the credential and the comparison.

Corroborated in production: the marker comment on PR #540
(`repos/rediacc/console/issues/comments/5093500917`) reports `Cost: $1.0464`, and CI run
30527484990 logged `"total_cost_usd": 5.925512999999999`. Both under
`ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`. Cost is fully populated on the OAuth path.

### The plumbing, measured end to end

The flag is not an action input. `action.yml` at the pin has no budget input at all; the
only channel is `claude_args`, forwarded as `CLAUDE_ARGS` at
[action.yml:305](https://github.com/anthropics/claude-code-action/blob/fa7e2f0a29a126f0b81cdcf360561b36e44cf608/action.yml#L305).
So `01-verified-context.md:413`'s claim that the flag "is not in the action" is correct;
its warning that the flag may not bind is now superseded.

Three hops, each verified:

1. **claude_args to extraArgs.** `parseClaudeArgsToExtraArgs` at
   [base-action/src/parse-sdk-options.ts:133-187](https://github.com/anthropics/claude-code-action/blob/fa7e2f0a29a126f0b81cdcf360561b36e44cf608/base-action/src/parse-sdk-options.ts#L133-L187)
   turns any `--flag value` pair into `extraArgs[flag] = value`. Only `model`,
   `add-dir`, `allowedTools`, `disallowed-tools` and `setting-sources` are lifted out and
   deleted (`:204`, `:213`, `:239`, `:262`, `:337`). `max-budget-usd` is not in that set, so
   it survives into `sdkOptions.extraArgs` at `:324`. READ, not measured.
2. **extraArgs to spawned argv.** Measured. The SDK's argv builder ends with
   `for(let[V,ve]of Object.entries(Vt))if(ve===null)H.push(\`--${V}\`);else Nw(H,V,ve)`.
   Driving the real `@anthropic-ai/claude-agent-sdk@0.3.217` with
   `extraArgs: {'max-budget-usd':'0.01'}` and a stub executable that dumps its argv
   produced, verbatim:

   ```
   --output-format stream-json --verbose --input-format stream-json
   --max-turns 140 --model claude-sonnet-5 --disallowedTools Task,Agent
   --setting-sources=user --permission-mode default --max-budget-usd 0.01
   ```

   Zero API cost; the stub never calls anything.
3. **CLI honours it.** Measured above.

One subtlety worth recording. The action never runs `claude --print`;
[base-action/src/run-claude.ts:19-25](https://github.com/anthropics/claude-code-action/blob/fa7e2f0a29a126f0b81cdcf360561b36e44cf608/base-action/src/run-claude.ts#L19-L25)
always routes through the Agent SDK, and the SDK's argv carries no `--print`. The CLI's
help text says `--max-budget-usd` "only works with --print", and the CLI does reject
`--input-format=stream-json` without print mode (`Error: --input-format=stream-json
requires --print.`, offset 259223593). Those reconcile because print mode is
`function un(){return!It.isInteractive}` (offset 239706098): a spawned process with a piped
stdin is non-interactive, therefore in print mode. So the SDK path IS print mode, and the
"only works with --print" caveat does not exclude the action. This last step is INFERRED
from the predicate plus the fact that the action's SDK spawns work at all in production; it
was not separately measured.

### Consequence Wave C has to design around: a budget halt turns the review job RED

`error_max_budget_usd` carries `is_error: true`. In
[run-claude-sdk.ts:213-215](https://github.com/anthropics/claude-code-action/blob/fa7e2f0a29a126f0b81cdcf360561b36e44cf608/base-action/src/run-claude-sdk.ts#L213-L215)
that makes `conclusion: "failure"`, and `:239-257` throws; `index.ts:72-76` then calls
`core.setFailed` and `process.exit(1)`. The step fails.

In `.github/workflows/claude-review-reusable.yml` the three steps after the review
(`Post review report` at :264, `Post inline findings` at :281, `Record reviewed SHA` at
:288) are all guarded by `if: steps.gate.outputs.go == 'true'` with no status function, so
GitHub's implicit `success()` applies and all three would be SKIPPED. Net effect of a
budget halt today: red job, no report comment, no inline findings, and no marker SHA
recorded, which means the next run re-reviews the same SHA from scratch and pays again.
This is INFERRED from documented `if:` semantics plus the file's conditions; no budget halt
has actually occurred in CI, so it has not been observed.

If Wave C wires the flag in, it should also decide whether the post-steps get `always()`
so a truncated review still records what it found.

---

## S-1 verdict: `--model claude-sonnet-5` IS honoured. The haiku labels were the `keys | first` artifact

Measured on CI run 30527484990, job 90821701588, the Claude Review job for PR #543 at
commit 89eb77d on 2026-07-30. From `gh api repos/rediacc/console/actions/jobs/90821701588/logs`:

- line 614, the action input as received: `claude_args: --model claude-sonnet-5`
- lines 987-999, the action's own log of the parsed options:
  `SDK options: { "model": "claude-sonnet-5", ... }`
- lines 1000-1005, the CLI's own init message: `"type":"system","subtype":"init","model":"claude-sonnet-5"`
- lines 1006-1014, the result: `"total_cost_usd": 5.925512999999999`, 61 turns

And the marker comment that run wrote (`issues/comments/5102584893`, updated
2026-07-30T08:46:17Z):

```
Cost: $5.9255 (claude-sonnet-5) | 61 turns | 7m2s
```

That line came from the FIXED formatter, which lists EVERY key in `modelUsage` joined by
`, ` (`.ci/scripts/review/claude-review-gate.sh:280-300`, present on `origin/main` since
commit f95533298, 2026-07-28 11:54:47 +0200). A single name with no comma means
`modelUsage` had exactly one key, `claude-sonnet-5`. **Haiku is absent from that run
entirely.**

The two comments that showed haiku were both written before that fix landed, so both used
the old `keys | first`:

| PR | marker comment last updated | body | formatter in effect |
|----|------------------------------|------|---------------------|
| #540 | 2026-07-27T15:46:10Z | `Cost: $1.0464 (claude-haiku-4-5-20251001)` | old, `keys \| first` |
| #541 | 2026-07-28T02:43:46Z | `Cost: $1.5343 (claude-haiku-4-5-20251001)` | old, `keys \| first` |
| #543 | 2026-07-30T08:46:17Z | `Cost: $5.9255 (claude-sonnet-5)` | fixed, every model |

Corroborated independently by the source: there is no override channel that could beat the
flag. `index.ts:56` passes `model: process.env.ANTHROPIC_MODEL`, and `action.yml` at the
pin sets no `ANTHROPIC_MODEL` and exposes no `model` input, so it is empty;
`parse-sdk-options.ts:310` is `model: options.model || modelFromClaudeArgs`, so the value
from `claude_args` wins. And both local runs, which requested `claude-sonnet-5`, came back
with `modelUsage` containing exactly one key, `claude-sonnet-5`.

**So issue #539 is a cosmetic label bug, not a review-quality bug.** Every finding received
so far came from the model that was asked for. The fix already shipped.

---

## Found, not fixed

1. **The cost line's per-model token count silently did not render on the one CI run that
   used the fixed formatter.** The comment reads `(claude-sonnet-5)` where the jq at
   `claude-review-gate.sh:296-298` should have produced `(claude-sonnet-5 30313out)`,
   since the same result block's `usage.output_tokens` was 30313 (rendered correctly on
   the `Tokens:` line right below). That implies `modelUsage["claude-sonnet-5"].outputTokens`
   was 0 or absent in the execution file. It is NOT a general property of the field: both
   local runs carried it (`outputTokens: 115` on the error result, `outputTokens: 4` on a
   success result), and `execution-file.ts:15-32` does no sanitizing, it is a plain
   `JSON.stringify(messages)`. Unexplained. The model-name half of the line is still
   trustworthy, which is what S-1 turned on, but the token-share half is not currently
   proving anything.
2. **The execution file is never persisted, so nobody can audit `modelUsage` after the
   fact.** `claude-execution-output.json` is written to `RUNNER_TEMP` and read inline by
   the two gate steps; no workflow uploads it as an artifact. Every question about a past
   review's model usage or cost therefore has to be answered from a one-line comment
   summary. Uploading it (even for 7 days, even only on failure) would have made both
   spikes a five-minute lookup, and would settle finding 1 directly.
3. **`extraArgs` is deliberately excluded from the action's own SDK-options log.**
   `run-claude-sdk.ts:153` destructures `env` and `extraArgs` out before printing, so any
   flag that rides through `extraArgs` (which is every flag except model, add-dir, the two
   tool lists and setting-sources) is invisible in CI logs. If Wave C wires
   `--max-budget-usd` in, the logs will not show it was applied; only a halt would.

---

## What I could not settle, and why

- **The action path was not exercised end to end in CI with the flag set.** Doing that
  needs a live dispatch, which was out of scope. What is measured instead is each hop
  separately: the SDK genuinely emits `--max-budget-usd` into the child argv (measured with
  the real SDK build), and the pinned CLI genuinely halts on it under OAuth (measured on
  the pinned binary). The only unmeasured link is `parseClaudeArgsToExtraArgs`, which was
  read at the pin and has no branch that could drop the flag. I rate the end-to-end claim
  as very high confidence but formally a composition of measurements, not one measurement.
- **Whether the overshoot is bounded by anything other than one turn's cost.** `Irr` is
  evaluated between turns; I did not find any mid-request or streaming-level budget check,
  but I did not exhaustively sweep the bundle for one. Treat "budget plus one turn" as the
  working bound, not a proven one.
- **Why `modelUsage.outputTokens` was 0 on CI run 30527484990** (finding 1). Not
  reproducible locally, and the execution file is gone with the runner.
- **Whether the post-review steps really skip on a budget halt** (the red-job consequence).
  Derived from the `if:` conditions and documented `success()` defaults; never observed,
  because no budget halt has ever happened in this repo.

---

## Recommendation for Wave C's cost section

Say this, and not more than this:

> `--max-budget-usd`, passed through `claude_args`, does bind under OAuth. It stops the run
> at the first turn boundary after accumulated cost crosses the cap, so it bounds total
> spend to roughly the cap plus one turn, not to the cap. On the current review workload one
> turn is about $0.10, but a first turn that ingests a large diff can cost considerably
> more. It is a stop, not a ceiling. Hitting it currently fails the review step and skips
> the report, findings and marker steps.

`03-v2-autonomy.md:359-360` should be updated: the flag is no longer unverified, but the
"hard stop" language needs the overshoot caveat.
