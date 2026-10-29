# PLAN: long rdc verbs run as machine jobs everywhere: start, hand back a ticket, follow by short polls through the proxy, and never lose a job to a sleeping client or a tool timeout

Status: approved -- operator rulings 2026-10-29 (ASKED, all four Recommended options), quoted in "Operator rulings (2026-10-29)" below; worklist #0bc3dcfd, lead session d778be9d, branch 1023-1. In ## Generated until the operator promotes it.
Owner: d778be9d
Updated: 2026-10-29
First-Seen: 2026-10-29
Depends-On: no-dep -- builds on the renet `job` verbs and the CLI job client already on main; the related proxy plans are named under "Related plans" as boxes this plan must not break, not as prerequisites
Priority: P1 -- a held NDJSON stream bills the proxy Worker, the OrgExecutor Durable Object and its container for the whole run of every long proxied verb, and a direct `renet execute` dies with its SSH channel (private/renet/cmd/renet/execute_command.go:195-212), so a laptop that sleeps cancels a half-finished snapshot or migration
Concurrency: parallel -- J1 (renet), J2 (contract), J5 (ticket store) and J7 (web console) have disjoint Owns and run at the same time. J0 (audit, read-only) runs first and gates J3 and J4. J3 follows J2 and J5 (it writes tickets through J5's store API). J4 follows J0 and J3. J6 follows J2, J3 and J5. J8 follows J2, J3 and J5. J9 follows J3, J5, J6 and J8 (the en keys and the docs describe the landed behaviour). L0 runs before any bench deploy of this branch. L1 and L2 follow every code box. PLAN-cloudflare-proxy, PLAN-converge-preflight-and-repo-recovery and PLAN-renet-runtime-converge own packages/cli/src/services/executor/** broadly, and PLAN-cloudflare-proxy, PLAN-console-executor-multi-org, PLAN-proxy-cd-six-targets, PLAN-org-executor-connect-timeout-relocate and PLAN-telemetry-export own packages/cli/src/services/serve/server.ts or serve/**; their open boxes are live or ops boxes, so a writer here runs while no writer of theirs holds the same file. PLAN-renet-bridge-leftovers owns private/renet/cmd/renet/job_commands.go with only live boxes open. workers/proxy/src/** is not edited (J10 verifies only), so PLAN-executor-durable-object-policy's exclusive hold is untouched.
Owns: agent/plans/PLAN-detached-jobs.md, private/renet/cmd/renet/job_commands.go, private/renet/cmd/renet/job_commands_test.go, private/renet/pkg/jobs/jobs.go, private/renet/pkg/jobs/jobs_test.go, private/renet (the gitlink bump only), packages/cli/scripts/generate-cli-contract.ts, packages/cli/scripts/lib/plane-rules.ts, packages/shared/src/cli-contract/types.ts, packages/shared/src/cli-contract/validation.ts, packages/shared/src/cli-contract/wire.ts, packages/shared/src/cli-contract/data/contract.generated.ts (regenerated only), packages/shared/src/cli-contract/__tests__/**, packages/cli/src/cli.ts (the finished-notice lines only), packages/cli/src/types/index.ts (one exit code), packages/cli/src/services/executor/local-executor.ts, packages/cli/src/services/executor/detached-execution.ts, packages/cli/src/services/executor/job-client.ts, packages/cli/src/services/executor/job-remote.ts, packages/cli/src/services/executor/executor-factory.ts, packages/cli/src/services/executor/renet-command.ts, packages/cli/src/services/executor/types.ts, packages/cli/src/services/executor/proxy-command.ts, packages/cli/src/services/executor/proxy-client.ts, packages/cli/src/services/executor/__tests__/**, packages/cli/src/services/jobs/** (new), packages/cli/src/commands/job.ts, packages/cli/src/commands/__tests__/job-*.test.ts (new), packages/cli/src/commands/repo-fork.ts, packages/cli/src/commands/repo-backup.ts, packages/cli/src/commands/repo-migrate.ts, packages/cli/src/commands/backup.ts, packages/cli/src/commands/backup-ops.ts, packages/cli/src/commands/backup-storage.ts (the snapshot action only), packages/cli/src/services/serve/server.ts, packages/cli/src/services/serve/command-dispatch.ts, packages/cli/src/services/serve/__tests__/job-poll*.test.ts (new), packages/cli/src/services/serve/__tests__/command-dispatch.test.ts, packages/cli/src/commands/mcp/tool-factory.ts, packages/cli/src/commands/mcp/__tests__/**, packages/cli/src/config/command-metadata.ts (the mcp fields of the covered verbs and the job tools only), packages/cli/src/i18n/locales/*/cli.json, private/account/web/src/hooks/useCommand.ts, private/account/web/src/hooks/__tests__/useCommand-*.test.ts, private/account/web/src/api/console.ts, private/account/src/routes/console.ts (the job poll relay only), private/account (the gitlink bump only), packages/www/src/content/docs/*/proxy-and-executor.md, packages/www/src/content/docs/*/cli-application.md (regenerated only), .ci/rediacc_ci/ops/proxy_job_cost.py (new), .ci/rediacc_ci/tests/test_ops_proxy_job_cost.py (new)
Live-Proof: bench, hostinger -- the serve, executor and ticket code under packages/cli/src is the cli surface (live on bench and hostinger), the renet job verbs are the renet surface (live on hostinger only, .ci/config/proof-tiers.json surface `renet`), and the console poll relay under private/account/src and the wire schema under packages/shared/src are the account surface (live on bench only). The proxy surface (workers/proxy/src) is not edited.

## Context

### The problem

Three clients reach a machine for a long verb today, and each one ties the job's life or its bill to the client's connection:

1. **Direct SSH, foreground.** Every covered verb runs `renet execute` under the SSH channel (packages/cli/src/services/executor/local-executor.ts:203-214 picks the foreground path unless `options.detached` is set). renet catches SIGHUP and cancels the operation when the channel drops (private/renet/cmd/renet/execute_command.go:195-212). A laptop that sleeps, or a network change, cancels the work.
2. **Direct SSH, `-b/--background`.** The global flag (packages/cli/src/cli.ts:198, handled at :232-235) sets a process global that `backgroundDecorator` turns into `{ detached: true, follow: false }` on EVERY machine call the command makes (packages/cli/src/services/executor/executor-factory.ts:80-84), including short probes whose output the command needs. `isBackgroundRequested` (packages/cli/src/services/executor/executor-factory.ts:66) has no reader. Even a following detached run gives up after 5 reconnects (packages/cli/src/services/executor/job-remote.ts:55, :212-240), so a laptop that sleeps longer than about 20 s turns a running job into a failed command.
3. **The proxy (Cloudflare Worker, OrgExecutor Durable Object, executor container).** A served command runs every machine call detached AND followed (packages/cli/src/services/serve/command-dispatch.ts:389-405 hard-codes `follow: true`), and the route streams NDJSON until the job ends (packages/cli/src/services/serve/server.ts:260-263 announces `{kind:'job', jobId}`). The Durable Object counts the open body in flight (workers/proxy/src/org-executor.ts:96, fetch :283-322) and its alarm renews the lease and re-arms while `inFlight > 0` (:327-346), so the container never reaches its `sleepAfter = '2m'` (:89) during a run. agent/plans/PLAN-executor-durable-object-policy.md:151 records the same fact: "long NDJSON streams hold their slot". The web console (private/account/web/src/hooks/useCommand.ts:80) and the CLI proxy client (packages/cli/src/services/executor/proxy-client.ts:157, :387-421, `MAX_REATTACHES = 5`) both hold that stream.

### Measured evidence

- **The hostinger seed lost a 10-minute snapshot.** agent/plans/PLAN-backup-program.md:526 records `backup snapshot mautic --bwlimit 100Mbps --parallelism 2` rc=1 after 618 s with `signal: terminated` (go-executor duration_ms=600019). The immediate cause was the 10-minute renet default timeout, fixed by commit d6ea91581 (`resolveRenetTimeoutMs`, a 24 h ceiling for the data-moving backup functions in packages/cli/src/services/executor/renet-command.ts:89-97). That ceiling stays. The run also showed the second exposure: the snapshot ran in the foreground under one SSH channel for 10 minutes, so any client sleep in that window would have cancelled it the same way.
- **The Durable Object and container are billed for the held stream.** agent/plans/PLAN-cloudflare-proxy.md:221 states "In-flight streams still keep the instance alive", and :263 that "a long `repo up` stream keeps the container awake correctly". Container memory is billed on provisioned memory while the instance is awake (agent/plans/PLAN-cloudflare-proxy.md:231-242), and the monthly spend report already reads per-application container seconds (.ci/rediacc_ci/ops/cf_usage_report.py:12). No measurement of the per-run Durable Object wall time exists yet: L0 records the baseline before any code lands, and L2 the result.

### What already exists (verified 2026-10-29)

- renet `job start|run|status|logs|cancel|list|gc` (private/renet/cmd/renet/job_commands.go). `job start` launches `systemd-run --unit=rediacc-job-<id> --remain-after-exit` (:195-210) and has a 10-minute `--timeout` default (:100). `job logs` takes `--since-line` and `--follow` (:577-609). The status file carries `state`, `exit_code`, `function`, `repo_guid`, `started_at`, `finished_at` (private/renet/pkg/jobs/jobs.go:96-109). GC removes terminal jobs older than a horizon only when asked (private/renet/pkg/jobs/jobs.go:500); nothing calls it on a timer.
- The CLI detached path: `runDetachedExecution` (packages/cli/src/services/executor/detached-execution.ts:58-133) and `startJob` (:143-195). `startJob` returns null when renet lacks `job` (:180-183), which the caller turns into a silent foreground run (packages/cli/src/services/executor/local-executor.ts:212-213) after a warning (packages/cli/src/services/executor/job-client.ts:212-218).
- `rdc job list|status|logs|cancel|gc`, each requiring `-m <machine>` (packages/cli/src/commands/job.ts). MCP already exposes `job_list`, `job_status`, `job_logs` (without `--follow`) and `job_cancel` from the contract (packages/cli/src/config/command-metadata.ts:46-67), so ruling 4 needs no new job tool, only machine-optional lookups and covered tools that return at once.
- The contract's `detachable` flag is `proxyCapable && domain !== 'job'` minus an empty exclusion table (packages/cli/scripts/generate-cli-contract.ts:117, :503). It is true for 84 commands today, including reads such as `repo list` and `backup browse`, so it does not name the long verbs.
- MCP runs each tool as a child `rdc` through `execFile` with a kill timeout (packages/cli/src/commands/mcp/executor.ts:52-70): 300 s for writes and 120 s for reads (packages/cli/src/config/command-metadata.ts:41-42, applied at packages/cli/src/commands/mcp/tool-factory.ts:232). A `backup snapshot` past 300 s is killed mid-follow today; with a foreground renet it also cancels the work.
- Covered verbs make more than one machine call: `repo fork` runs `repository_fork` then a legacy `repository_up` leg (packages/cli/src/commands/repo-fork.ts:281-282, :332-333); `repo migrate` runs `backup_push`, a `repository_list` probe and `repository_delete` (packages/cli/src/commands/repo-migrate.ts:111-112, :154-155, :358-359); `backup restore` runs `backup_restore` then `repository_up` (packages/cli/src/commands/backup.ts:553-554, :634-635); `repo push` and `repo pull` run `repository_up` around `backup_push` and `backup_pull` (packages/cli/src/commands/repo-backup.ts:184-185, :283, :327-328, :378). `backup run` triggers strategy units over SSH without `renet execute` (packages/cli/src/commands/backup-ops.ts:181-225). This is the load-bearing shape for Design 3.

## Operator rulings (2026-10-29)

Asked 2026-10-29, all four Recommended options chosen:

1. Every detachable long verb ALWAYS runs as a machine job (renet `job start`, a systemd unit), on direct SSH too. Covered verbs: repo up, fork, push, pull, down, migrate, and backup snapshot, run, restore (and restore_path, verify, push, pull if they are long).
   - The CLI follows the output by default.
   - `-b` returns the ticket at once.
   - The foreground `renet execute` path is dropped for those verbs. This is a clean break: no fallback and no dual path.
   - The silent sync fallback for an old renet without `job` becomes a refusal that names the upgrade.
2. Proxy: the request returns the job id right after `job start` and ends.
   - The client follows with SHORT poll requests (`job logs --since N`, `job status`), backing off from about 2 s to 30 s.
   - There is no held NDJSON stream for a run. The DO and container are billed per poll, and the container may stop at its 2m sleepAfter between polls.
3. Local ticket store per config: config, machine, job id, verb, repo, started-at, last-seen line.
   - `rdc job list` shows pending tickets.
   - `rdc job wait <id>` resumes following.
   - The next rdc invocation reports jobs that finished while the client was away.
4. MCP: long tools start the job and return its id immediately. `job_status` and `job_logs` tools let the model poll. No tool timeout ever kills a job.

## Design

### 1. Which calls become jobs: by renet function, decided once

- `JOB_FUNCTIONS` in packages/cli/src/services/executor/renet-command.ts, beside the existing `DATA_TRANSFER_TIMEOUT_MS` set (:89-97): `repository_up`, `repository_up_all`, `repository_down`, `repository_down_all`, `repository_fork`, `backup_snapshot`, `backup_push`, `backup_pull`, `backup_restore`, `backup_restore_path`, `backup_verify`. J0 confirms the list against the verb audit and may add a function a covered verb reaches; it never adds a short read.
- The executor decides: a call whose `functionName` is in `JOB_FUNCTIONS` runs through `runDetachedExecution`, on every entry point (direct, daemon fallback, serve dispatch). Every other call stays `renet execute`, which is correct for a probe that answers in a second. `ExecuteOptions.detached` is no longer a caller's choice and is removed from the type (clean break).
- The contract's `detachable` keeps its name and narrows to "this command's long work runs as a job": an explicit `JOB_VERBS` table in generate-cli-contract.ts, each entry with its reason, replaces the derived rule and the empty `DETACH_EXCLUSIONS`. `detachable` still implies `proxyCapable` (packages/shared/src/cli-contract/validation.ts:322-325). Covered: `repo up`, `repo down`, `repo fork`, `repo push`, `repo pull`, `repo migrate`, `backup snapshot`, `backup restore`, `backup verify`, plus `backup restore-path` when PLAN-backup-restore-path lands its verb. `backup run` is decided in J0 (Open question 2).
- `-b` is accepted only on a `detachable` command, as today (packages/cli/src/services/executor/proxy-command.ts:72), so the narrowing changes which commands accept it. A refused command's message stays derived from the contract.

### 2. Direct SSH: start, follow by default, never fail because the watcher left

- Following stays a live `renet job logs --follow` tail over SSH: SSH is not billed per second, and the render path is already shared with `rdc job logs`.
- When the tail cannot be re-established after its reconnects, the command no longer fails as if the job had failed. It prints the resume hint, keeps the ticket, and exits `EXIT_CODES.DETACHED` (130, packages/cli/src/types/index.ts:92) for Ctrl-C or a new `FOLLOW_LOST` code for a lost transport (J3 picks the number; the table at packages/cli/src/types/index.ts:74-92 reserves 10 for renet and 11-15 for refusals).
- The reconnect ceiling for the direct tail rises from 5 attempts capped at 5 s (packages/cli/src/services/executor/job-remote.ts:55-60) to a time budget of 2 minutes with the same capped backoff, so a short Wi-Fi change does not detach.
- `-b`: the job function's start returns the ticket at once. Probes before it still run in the foreground. The JSON output under `-o json` is an envelope, `{ "jobId", "machine", "verb", "repo", "state": "running", "follow": "rdc job wait <id>" }`, never the plain hint text (today `backgroundStartedHint` goes to stdout in every output format, packages/cli/src/services/executor/detached-execution.ts:78-80), so MCP and scripts can parse it.

### 3. Verbs with more than one machine call: the terminal job

A covered verb that keeps working after its job (a second machine call or local bookkeeping) cannot simply return at the start. The rule:

- Each covered verb marks exactly one job call as its terminal job (`ExecuteOptions.terminalJob: true`). Under `-b` and on the proxy, the command returns at that job's start.
- A job function called with `captureOutput` before the terminal job (a probe whose answer the command needs, such as `backup_verify` in `readSourceAnchor`, packages/cli/src/commands/backup.ts:485-500) is followed to completion in the same process, because the command cannot continue without it.
- A machine call AFTER the terminal job is a bug, and a test hook throws on it. J0 classifies every post-job tail, and J4 moves each one:
  - a second machine step joins the terminal job inside renet when renet already has a compound form (`repository_fork` with `up`, packages/cli/src/commands/repo-fork.ts:262-273), and the legacy client-side leg is removed when it exists only for a renet older than the job verbs;
  - a machine step with no compound form becomes the terminal job's successor recorded on the ticket (`then: <function, params>`), started by whichever client observes the first job's success (`rdc job wait`, the finished notice, or a proxy poll on the executor side), exactly once, keyed by the ticket's request id;
  - local bookkeeping (the deferred identity refresh, a config record) runs as the ticket's finalizer when success is observed, on the side that owns the config: the CLI on direct SSH, the executor on the proxy.
- J0 writes the per-verb table into this plan before J3 starts. Its default for `repo migrate` keeps the source deletion inside the job chain, never on a client that may be asleep.

### 4. Proxy wire protocol: return after start, then short polls

- `POST /v1/command` for a `detachable` command streams the pre-job events (probes, validation), then `{kind:'job', jobId, machine, sinceLine: 0}`, then a `result` line with `state: 'running'` and the job id, and ENDS. No request field opts out: the executor always returns after the terminal job's start (ruling 2), so there is one path. A non-detachable command is unchanged.
- The job line gains `machine` (packages/shared/src/cli-contract/wire.ts:170-175), so a client never has to re-derive it.
- One poll route replaces the held re-attach stream: `GET /v1/jobs/:id/poll?machine=<m>&sinceLine=<n>&maxLines=<k>` returns JSON `{ events: [{ line, event }], nextLine, more, status: { state, exitCode?, finishedAt?, function } }`. One request carries both the new log lines and the status, which halves the request count against separate `job logs` and `job status` calls. `maxLines` defaults to 500 and the body is capped at 256 KiB; `more: true` tells the client to poll again at once.
- `GET /v1/jobs/:id/events` (packages/cli/src/services/serve/server.ts:371, `PROXY_ROUTES.jobEventsPattern` at packages/shared/src/cli-contract/wire.ts:217) and the client's re-attach loop (packages/cli/src/services/executor/proxy-client.ts:387-421) are deleted (clean break).
- `POST /v1/jobs/:id/cancel?machine=<m>` cancels.
- Auth and policy: `assertJobId` runs first, as on the old route. Poll authorizes as the contract command `job logs` scoped to the machine; cancel as `job cancel` (destructive, audited). Enabling proxy execution still implies allowing `job logs`, as packages/cli/src/services/serve/server.ts:357-369 documents.
- Audit: one event at job start (the command, `outcome: started`, the job id), and one at the first poll that observes a terminal state (`outcome: succeeded|failed|cancelled`, exit code, duration from the status file), deduplicated on job id inside the executor's session store, so a client that never polls again still leaves the start record.
- Each poll opens its own SSH exec (`renet job logs --since-line N --max-lines K --with-status`) through the existing connection lease, so a container that stopped between polls answers the next one after a cold start.

### 5. Client backoff

- Start at 2 s. Each poll that returns no new line multiplies the delay by 1.5, capped at 30 s. A poll with new lines resets it to 2 s. A `more: true` answer polls at once. Each delay carries plus or minus 20 % jitter.
- Transport errors back off on the same ladder and never fail the command for 10 minutes; past that the client detaches with the ticket kept and exits `FOLLOW_LOST`.
- Container billing follows from the cap: a client polling every 30 s keeps the container awake (30 s is under the 2-minute `sleepAfter`), while a client that is gone (sleep, `-b`, MCP) costs nothing after the job starts. The Durable Object's billed duration falls from the whole run to the sum of poll durations. Open question 1 asks whether a long run's cap should rise past `sleepAfter`.

### 6. The ticket store

- Location: `~/.config/rediacc/jobs/<config>.jsonl` (the config directory from `getConfigDir()`), directory 0700, file 0600. A subdirectory, not a `jobs-<config>.json` sibling, because the config loader treats every other `*.json` in that directory as a config (packages/cli/src/adapters/config-file-storage.ts:28-43).
- Append-only JSONL under `O_APPEND`, one event per line, so concurrent `rdc` processes (an MCP server running tools in parallel) never lose a ticket. Compaction rewrites the file under a lock file when more than 200 lines are acknowledged.
- Schema (version 1): `{ v, ts, kind: started|seen|finished|acknowledged|then-started, requestId, jobId, config, machine, via: { kind: ssh|proxy, url? }, verb, function, repo?, startedAt, lastSeenLine?, state?, exitCode?, finishedAt?, then? }`. The folded view per `requestId` is the ticket.
- `requestId` is a UUID the client mints BEFORE the start and writes as `starting`. It rides to renet as `job start --request-id` (Design 9), so a start whose answer was lost (a dropped proxy response, a killed MCP child) is retried into the same job instead of a second one.
- No secret enters the store: no vault, no env, no event payloads, only the line offset.

### 7. `rdc job list`, `rdc job wait`, and the machine flag

- `rdc job list` without `-m` prints this config's tickets that are pending or finished-and-unacknowledged (id, verb, repo, machine, state, age), newest first. With `-m <machine>` it lists the machine's jobs as today.
- `rdc job wait <id>` resumes following from the ticket's `lastSeenLine` (SSH tail or proxy polls, by `via`), runs any successor and finalizer, marks the ticket acknowledged, and exits with the job's exit code. `--timeout <duration>` stops waiting (not the job) with `FOLLOW_LOST`.
- `job status`, `job logs`, `job cancel` and `job wait` take `-m` optionally: a ticket with that id supplies the machine and the path. With neither, the command fails and names `-m`.
- `job gc` stays machine-side. A ticket whose spool was collected reports `state: unknown (spool removed)` once and is acknowledged.

### 8. The finished-while-away notice

- The root `preAction` hook starts a background check of this config's pending tickets whose last check is older than 60 s: at most 5 tickets, in parallel, with a 2-second budget, one `job status` each (an SSH exec, or one proxy poll with `maxLines=0`).
- The `postAction` hook prints one line per newly finished ticket on stderr, never stdout, so `-o json` output stays parseable: `Job <id> (<verb> <repo>@<machine>) succeeded 12m ago. Details: rdc job logs <id>`. A failed job names its exit code. The ticket then becomes acknowledged.
- Skipped for `rdc job *` itself (which shows tickets anyway), under `-q`, and when the budget expires (the check retries on a later invocation).

### 9. renet changes (J1)

- `job start --request-id <uuid>`: the id is stored in the status file. A second start with the same id returns the existing handle with exit 0 and starts nothing.
- `job logs --max-lines <k>` (default 0, unlimited) bounds a non-follow read, and `--with-status` appends one trailer line `{"type":"job_status", ...}` after the events, so one SSH exec answers a poll.
- The status JSON keeps its fields. `exit_code` is already set by `finalizeJob` (private/renet/cmd/renet/job_commands.go:347-363).
- The 10-minute `job start --timeout` default (private/renet/cmd/renet/job_commands.go:100) is unchanged: the CLI already passes `resolveRenetTimeoutMs`, which gives the data-moving backup functions 24 h. J0 checks whether `repository_up` or `repository_fork` of a large repository needs the same ceiling now that a job, not a client, owns the run (Risk 4).
- Spool retention is unchanged (no timer GC). Design 7 covers a collected spool.

### 10. Cancel semantics

- Ctrl-C while following detaches and never cancels (unchanged: packages/cli/src/services/executor/detached-execution.ts:104-115).
- `rdc job cancel <id>` (machine from the ticket) stops the unit through `renet job cancel`. The proxy route `POST /v1/jobs/:id/cancel` does the same under `job cancel` policy. A successor recorded on a cancelled ticket never starts.
- The web console gains no cancel button in this plan (Out of scope).

### 11. The old-renet refusal

- `startJob` no longer returns null. renet without `job`, or without `--request-id` or `--max-lines`, raises `JobsUnsupportedError`: `renet on '<machine>' is older than this CLI and cannot run <verb> as a job. Upgrade it: rdc machine setup <machine>` (the wording of `renetOlderThanCliMessage`, packages/cli/src/services/executor/job-client.ts:162-164), exit 1, and nothing ran (cobra rejects an unknown command or flag before any work). `versionSkewWarning` and the foreground fallback (packages/cli/src/services/executor/local-executor.ts:212-213) are deleted.

### 12. MCP tool shapes (J8)

- Each covered tool appends `--background` and returns the JSON envelope of Design 2 within seconds: `{ jobId, machine, verb, repo, state: "running", next: "job_status" }`. Its description says it starts a job and names `job_status` and `job_logs`.
- `job_status` and `job_logs` accept a job id alone (the ticket supplies the machine); `job_logs` keeps `since-line` for incremental reads. `job_wait` is not exposed: an agent cannot usefully block on it.
- The covered tools keep the 300 s kill timeout, which now bounds only the start. A killed starter leaves the ticket at `starting`, and the job, if it started, is found by its request id.

### 13. Telemetry

- The CLI command span gains `rediacc.job.id`, `rediacc.job.function`, `rediacc.job.follow` (`tail`, `poll`, `background`) and, for a followed run, `rediacc.job.polls` and `rediacc.job.outcome`.
- The serve dispatch span gains `rediacc.proxy.route` (`command`, `job-poll`, `job-cancel`) so the request-duration drop is visible per route in the existing traces. No new exporter; the attributes ride the spans PLAN-telemetry-export already ships.

### Related plans: boxes touched or not to break

- PLAN-cloudflare-proxy.md B4 (:40), the nightly e2e of `repo status`, `repo up` and `repo down` through a local serve: its re-attach assertion changes meaning. J6 adds the poll path's in-process test, and B4's writer asserts polls instead of the held stream; the box text is left to that plan.
- PLAN-cloudflare-proxy.md Phase 2 step 4 (:115), "Proves egress, streaming, detach and re-attach through the Worker": after J6 it proves start-and-poll. No box of that plan is edited here.
- agent/plans/PLAN-executor-durable-object-policy.md:151: the lease renewal while in flight stays correct for the remaining streams (non-detachable commands, sessions). Nothing in workers/proxy/src changes (J10), so its exclusive Owns and its L-boxes are untouched.
- PLAN-console-executor-multi-org.md: the per-org container, token and audit trail are unchanged. The two new routes authenticate through the same `authenticate` and per-org policy path as `/v1/command`.
- PLAN-cloudflare-spend-guard.md T6 owns cf_usage_report.py. L2's measurement lives in a new module that imports its GraphQL helper rather than editing it.
- PLAN-proxy-cd-six-targets.md: the deploy shape is unchanged; the new routes ship with the executor image like every serve route.
- PLAN-backup-restore-path.md: `backup restore-path` joins `JOB_VERBS` once its verb lands; `backup_restore_path` is already in `JOB_FUNCTIONS`.

## Tasks

- [ ] J0 [lead] Verb audit, read-only. For each covered verb, list its machine calls in order (function, `captureOutput` or not, terminal or not), every post-job tail with its class (compound in renet, successor, finalizer, delete), and whether `-b` today detaches a probe. Settle `backup run` (Open question 2) and the timeout question of Design 9. Write the table into a new "Verb audit" section of this plan with file:line evidence.
  Owns: agent/plans/PLAN-detached-jobs.md. Accept: `python3 .ci/scripts/quality/check_plan_citations.py` rc 0 and `python3 .ci/scripts/quality/check_plan_deps.py` rc 0.

- [ ] J1 [writer] renet: `job start --request-id` (idempotent start), `job logs --max-lines` and `--with-status` (Design 9). Changes:
  - the request id lands in `jobs.Status` and a lookup by request id returns the existing handle;
  - the logs reader stops after k complete lines and appends the status trailer;
  - help text for both flags.

  Tests: a second start with the same request id starts no second unit (fake systemd-run seam) and prints the first handle; `--max-lines 2` on a 5-line spool returns 2 lines and `--with-status` adds exactly one trailer line whose state matches the status file; control: without the flags the output is byte-identical to today's.

  Owns: private/renet/cmd/renet/job_commands.go, private/renet/cmd/renet/job_commands_test.go, private/renet/pkg/jobs/jobs.go, private/renet/pkg/jobs/jobs_test.go, private/renet (the gitlink bump only). Accept: `cd private/renet && go test ./cmd/renet/ ./pkg/jobs/` rc 0, and `cd private/renet && go vet ./cmd/renet/ ./pkg/jobs/` rc 0.

- [ ] J2 [writer] Contract: `detachable` narrows to the covered verbs through an explicit `JOB_VERBS` table with reasons (Design 1); the job wire line gains `machine`; the poll response schema and the poll and cancel routes join `PROXY_ROUTES`; `jobEvents` and `jobEventsPattern` are removed. The lead regenerates the contract with `npm run generate:cli-contract -w @rediacc/cli` after the writer's edit.

  Tests: the contract test asserts the exact covered set and that no `domain === 'job'` command is detachable; the poll schema round-trips a sample and refuses a body without `nextLine`; control: a planted `repo list` in `JOB_VERBS` makes the set test red.

  Owns: packages/cli/scripts/generate-cli-contract.ts, packages/cli/scripts/lib/plane-rules.ts, packages/shared/src/cli-contract/types.ts, packages/shared/src/cli-contract/validation.ts, packages/shared/src/cli-contract/wire.ts, packages/shared/src/cli-contract/data/contract.generated.ts (regenerated only), packages/shared/src/cli-contract/__tests__/**. Accept: `cd packages/shared && npx vitest run src/cli-contract` rc 0, and `npx tsc --noEmit --project packages/shared/tsconfig.json` rc 0.

- [ ] J3 [writer] CLI executor, direct path. After J0, J2 and J5. Changes:
  - `JOB_FUNCTIONS` and the function-based detach decision; `ExecuteOptions.detached` removed; `terminalJob` and the post-terminal-call guard added (Design 1, 3);
  - `startJob` never returns null, `JobsUnsupportedError` replaces the warning and the foreground fallback (Design 11), and `startJob` passes `--request-id`;
  - the 2-minute reconnect budget and the detach-with-ticket exit on a lost tail, with the new `FOLLOW_LOST` exit code (Design 2);
  - `backgroundDecorator` sets `follow: false` on the terminal job only; `isBackgroundRequested` gains its reader in the terminal-job guard;
  - the `-b` JSON envelope under `-o json` (Design 2);
  - the span attributes of Design 13.

  Tests: `repository_up` goes through `job start` and `repository_list` through `renet execute` (recording SFTP fake); renet answering `unknown command "job"` gives rc 1 with the upgrade text and no `execute` call; a tail dropping for longer than the budget exits `FOLLOW_LOST` with the ticket written; `-b -o json` prints one parseable envelope; a machine call after a terminal job throws in the test hook; control: an ordinary followed run returns the job's exit code.

  Owns: packages/cli/src/services/executor/local-executor.ts, packages/cli/src/services/executor/detached-execution.ts, packages/cli/src/services/executor/job-client.ts, packages/cli/src/services/executor/job-remote.ts, packages/cli/src/services/executor/executor-factory.ts, packages/cli/src/services/executor/renet-command.ts, packages/cli/src/services/executor/types.ts, packages/cli/src/services/executor/proxy-command.ts, packages/cli/src/services/executor/__tests__/** (except proxy-client tests), packages/cli/src/types/index.ts (one exit code). Accept: `cd packages/cli && npx vitest run src/services/executor` rc 0, and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.

- [ ] J4 [writer] Verb tails, per J0's table. After J0 and J3. Each covered verb marks its terminal job; compound renet forms replace client-side second legs where renet has them; successors and finalizers register on the ticket (Design 3).

  Tests: one per verb class from J0's table (compound, successor, finalizer), each driving the verb against the recording executor under `-b` and asserting it returns at the terminal start with the successor or finalizer recorded on the ticket; control: the same verb followed runs the tail in-process exactly once.

  Owns: packages/cli/src/commands/repo-fork.ts, packages/cli/src/commands/repo-backup.ts, packages/cli/src/commands/repo-migrate.ts, packages/cli/src/commands/backup.ts, packages/cli/src/commands/backup-ops.ts, packages/cli/src/commands/backup-storage.ts (the snapshot action only), packages/cli/src/commands/__tests__/job-tails.test.ts (new). Accept: `cd packages/cli && npx vitest run src/commands/__tests__/job-tails.test.ts` rc 0, and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.

- [ ] J5 [writer] Ticket store, `rdc job list` and `rdc job wait`, the optional `-m`, and the finished notice (Design 6, 7, 8). Adds the en locale keys for these strings.

  Tests: two processes appending concurrently lose no ticket; the store file is 0600 and its directory 0700; no planted vault or env value appears in the file; `job wait` resumes from `lastSeenLine` and exits with the job's code; the notice prints on stderr only and once per ticket; a `jobs/` file never shows up in `rdc config list`; control: with no tickets the notice makes zero machine calls.

  Owns: packages/cli/src/services/jobs/** (new), packages/cli/src/commands/job.ts, packages/cli/src/commands/__tests__/job-wait.test.ts (new), packages/cli/src/commands/__tests__/job-tickets.test.ts (new), packages/cli/src/cli.ts (the finished-notice lines only), packages/cli/src/i18n/locales/en/cli.json. Accept: `cd packages/cli && npx vitest run src/services/jobs src/commands/__tests__/job-wait.test.ts src/commands/__tests__/job-tickets.test.ts` rc 0, and `npm run check:ci-i18n-cli-key-usage` rc 0.

- [ ] J6 [writer] Proxy serve and client. After J2, J3 and J5. Changes:
  - the dispatch returns at the terminal job's start (packages/cli/src/services/serve/command-dispatch.ts:389-405 loses `follow: true`);
  - the poll and cancel routes, the held re-attach route deleted, start and terminal audit events (Design 4);
  - proxy-client follows by polls with the Design 5 backoff, writes and updates the ticket (`via: proxy`), and loses its re-attach loop.

  Tests: an in-process serve with a fake machine shows `/v1/command` for `repo up` ending right after the job and result lines (the response closes before the fake job finishes); poll returns events after `sinceLine` with the status and honours `maxLines` and `more`; a poll for a machine outside the caller's policy is 403; the cancel route audits as destructive; exactly one terminal audit event across three polls of a finished job; the client's backoff sequence on empty polls is 2, 3, 4.5 ... 30 s within jitter; control: a non-detachable command (`repo list`) still streams to its result.

  Owns: packages/cli/src/services/serve/server.ts, packages/cli/src/services/serve/command-dispatch.ts, packages/cli/src/services/serve/__tests__/job-poll.test.ts (new), packages/cli/src/services/serve/__tests__/command-dispatch.test.ts, packages/cli/src/services/executor/proxy-client.ts, packages/cli/src/services/executor/__tests__/proxy-client-poll.test.ts (new). Accept: `cd packages/cli && npx vitest run src/services/serve src/services/executor/__tests__/proxy-client-poll.test.ts` rc 0, and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.

- [ ] J7 [writer] Web console: `useCommand` stops at the job line and follows by polls through a new account route that relays `/v1/jobs/:id/poll` to the org's executor with the same session and grant checks as the command relay (private/account/src/routes/console.ts:467). Same backoff as Design 5; leaving the page stops polling and never cancels.

  Tests: the hook renders events from three polls and the final outcome from the terminal status; unmount stops the timer; the relay refuses a request without a console session; control: a non-detachable command renders from the stream as today.

  Owns: private/account/web/src/hooks/useCommand.ts, private/account/web/src/hooks/__tests__/useCommand-poll.test.ts (new), private/account/web/src/api/console.ts, private/account/src/routes/console.ts (the job poll relay only), private/account (the gitlink bump only). Accept: `cd private/account && npx vitest run web/src/hooks src/routes` rc 0, and `cd private/account && npx tsc --noEmit` rc 0.

- [ ] J8 [writer] MCP (Design 12). After J2, J3 and J5. Covered tools append `--background` and describe the job; `job_status` and `job_logs` take the machine optionally.

  Tests: each covered tool's argv carries `--background`; the parsed envelope of a fake `repo up` returns within the read timeout with a job id; `job_status` built with only an id omits `-m`; the coverage test lists every covered verb with `--background`; control: `repo list` carries no `--background`.

  Owns: packages/cli/src/commands/mcp/tool-factory.ts, packages/cli/src/commands/mcp/__tests__/**, packages/cli/src/config/command-metadata.ts (the mcp fields of the covered verbs and the job tools only). Accept: `cd packages/cli && npx vitest run src/commands/mcp` rc 0.

- [ ] J9 [writer] Docs and i18n in 13 locales. After J3, J5, J6 and J8. The new en keys are naturalized into the 12 derived locales (docs/i18n/CONVENTIONS.md); proxy-and-executor.md gains a section on jobs, tickets and polling in English and is re-translated as a delta; cli-application.md is regenerated with `npm run generate:cli-docs -w @rediacc/www` by the lead.

  Owns: packages/cli/src/i18n/locales/*/cli.json (non-en), packages/www/src/content/docs/*/proxy-and-executor.md, packages/www/src/content/docs/*/cli-application.md (regenerated only). Accept: `npm run check:i18n` rc 0.

- [ ] J10 [lead] Durable Object: verify that no code change is needed. With every detachable run returning after start, `inFlight` falls to zero between polls and the alarm's idle branch applies unchanged (workers/proxy/src/org-executor.ts:327-346). Record the reading here; if L1 shows a poll that holds the lease past its body, the fix is filed under PLAN-executor-durable-object-policy's exclusive Owns, not here.
  Owns: agent/plans/PLAN-detached-jobs.md. Accept: `npm run check:ci-proxy-cost-guard` rc 0.

- [ ] J11 [lead] The VM proof for the renet change: `npm run vm:check -- --changed` VERIFIED on the tree carrying J1 and J3, as the push guard requires for the renet trigger paths.
  Owns: agent/plans/PLAN-detached-jobs.md. Accept: `npm run vm:check -- --changed` rc 0 with a VERIFIED receipt.

- [ ] L0 [live] Baseline before any bench deploy of this branch: one `rdc --proxy <bench proxy origin> repo up <fork>` and one `backup verify <fork>` through the bench proxy on the current protocol, then the Durable Object request wall time, request count and container seconds for `rediacc-proxy-bench` over that window, read with the J12 module (or by hand with the same GraphQL query if J12 has not landed, recorded verbatim).
  Owns: agent/plans/PLAN-detached-jobs.md. Accept: the run's timings and the three metrics recorded under "Live records" with the UTC window, and both commands rc 0.

- [ ] J12 [writer] Cost measurement module: `.ci/rediacc_ci/ops/proxy_job_cost.py --script <name> --from <ISO> --to <ISO>` prints Durable Object requests and wall time (sum, p50, p99) and container active seconds for one script over a window, importing the GraphQL transport from cf_usage_report rather than copying it. The dataset and field names (`durableObjectsInvocationsAdaptiveGroups` with wall time, `containersMetricsAdaptiveGroups`) are hypotheses to confirm against the live API first (CLAUDE.md rule 3).

  Tests: a recorded GraphQL response yields the expected sums; an empty response exits 2, never 0; a GraphQL error exits 2; control: a response with one row prints that row.

  Owns: .ci/rediacc_ci/ops/proxy_job_cost.py (new), .ci/rediacc_ci/tests/test_ops_proxy_job_cost.py (new). Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ops_proxy_job_cost.py` rc 0.

- [ ] L1 [live] Bench through the proxy, after every code box. Deploy the branch to bench (deploy_bench, then `deploy_proxy --target bench`), provision the branch renet to hostinger (ASK first, as LP-hostinger says), then on a fork through `--config eu-bench` and the bench proxy:
  1. `repo up <fork>`: the `/v1/command` response ends within seconds of the job line, polls follow to success, rc 0;
  2. `-b backup snapshot <fork>`: returns a ticket at once; the laptop process exits; `rdc job list` shows it; `rdc job wait <id>` finishes it with rc 0;
  3. start `backup verify <fork>` followed, kill the client mid-run, run any `rdc` command after the job ends: the finished notice prints once;
  4. the MCP `backup_snapshot` tool returns a job id in under 30 s and `job_status` reaches `succeeded`;
  5. a machine whose renet lacks `--request-id` (a pinned older renet on a dev VM) refuses with the upgrade text and rc 1.

  Owns: agent/plans/PLAN-detached-jobs.md. Accept: each step's command, rc and timing recorded under "Live records"; steps 1-4 rc 0 and step 5 rc 1.

- [ ] L2 [live] Cost after: the L0 commands again on the deployed branch, and the same three metrics over the new window with `PYTHONPATH=.ci python3 -m rediacc_ci.ops.proxy_job_cost --script rediacc-proxy-bench --from <ISO> --to <ISO>`. The expected result is Durable Object wall time per run falling from the run length to the sum of poll durations; the measured before and after go into "Live records" with the ratio.
  Owns: agent/plans/PLAN-detached-jobs.md. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.proxy_job_cost --script rediacc-proxy-bench --from <ISO> --to <ISO>` rc 0 for both windows, with both readings recorded.

- [ ] LP-bench [live] Fresh bench receipt (PLAN-tested-on-bench ruling 3): deploy this branch to bench with deploy_bench, then record and tick through worklist.py --live-proof.
  - Accept: `live-proof bench account-smoke`
- [ ] LP-hostinger [live] Fresh hostinger receipt through --config eu-bench (PLAN-tested-on-bench ruling 3), after a VERIFIED npm run vm:check -- --changed on the same tree; ASK the operator first, because provisioning a branch renet restarts the router and daemons.
  - Accept: `live-proof hostinger renet-live`

## Open questions for the operator

1. **The poll cap and the container's sleep.** At the ruled 30 s cap a client that keeps following keeps the container awake for the whole run, because 30 s is under `sleepAfter = '2m'`; only the Durable Object's held duration and the absent-client case get cheaper. DEFAULT: keep 2-30 s as ruled, and let L2 measure. The alternative is a cap that rises to 150 s after 10 minutes of following, so a long snapshot lets the container sleep between polls at the cost of up to 150 s of output lag and a cold start per poll.
2. **`backup run`.** It triggers the strategy's systemd units over SSH and never calls `renet execute` (packages/cli/src/commands/backup-ops.ts:181-225), so its work already outlives the client. DEFAULT: J0 confirms that it returns at the unit start; if so it stays outside `JOB_VERBS`, its outcome stays on `backup status`, and the docs say so. Otherwise J4 makes the per-strategy run a renet job.

## Risks

1. **A start whose answer is lost.** A proxy response dropped after `job start`, or an MCP child killed mid-start, would otherwise leave a running job nobody knows. The request id (Design 6, 9) makes the retry find it; a client that never retries still finds it under `rdc job list -m <machine>`.
2. **Post-job tails that silently stop running under `-b`.** That is today's state for `-b`, and Design 3 turns it into a test failure. J0's table is the inventory; a verb missing from it keeps the in-process follow.
3. **A poll per 2-30 s opens an SSH exec each time.** The connection lease reuses a live connection inside a warm container; a cold container pays one SSH handshake per poll. L1 records the poll latency.
4. **The 10-minute default of `job start --timeout` now applies to every covered verb.** It applied to `renet execute` the same way, so nothing regresses, but a job no client watches fails quietly. J0 decides whether `repository_up` and `repository_fork` join the 24 h set.
5. **Spool growth.** Every covered verb now leaves a spool under the machine's state directory. `job gc` exists and is not scheduled. Out of scope here; the ticket store tolerates a collected spool.
6. **Overlapping owners.** Several live plans own packages/cli/src/services/serve/** and packages/cli/src/services/executor/** broadly (Concurrency line). Their open boxes are live or ops boxes, so the conflict is in the concurrency guard, not in edits; a refused spawn is queued.

## Out of scope

- Any change under workers/proxy/src (J10 verifies, PLAN-executor-durable-object-policy owns it).
- A cancel button and a jobs page in the web console.
- Scheduled `job gc` and spool retention.
- Non-detachable long commands outside the covered list (`cluster *`, `datastore *`, `machine setup`): they keep the foreground path until a later ruling names them.
- Changing `resolveRenetTimeoutMs` beyond what J0 decides for `repository_up` and `repository_fork`.

## Live records

(empty until L0)

## Operator rulings, second round (2026-10-29)

- Poll cap (ASKED 2026-10-29, "Keep 2-30 s, measure first (Recommended)"): the 2-30 s backoff ships as ruled; L2 measures Durable Object and container time before any change to the cap.
- `backup run` stays outside the covered verbs (the plan's default for its second question); J0 confirms it never calls `renet execute`.
