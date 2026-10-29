# PLAN: every rdc command that touches a machine runs as one machine job: attached by default, a ticket once the run outlasts the attach window, short polls through the proxy, and no job lost, half-finished or run twice because a connection dropped

Status: approved -- operator rulings 2026-10-29 (ASKED, all four Recommended options), quoted in "Operator rulings (2026-10-29)" below; ruling 1 replaced by the operator's amendment of 2026-10-29, quoted in "Operator rulings, third round"; worklist #0bc3dcfd, lead session d778be9d, branch 1023-1.
Owner: d778be9d
Updated: 2026-10-29
First-Seen: 2026-10-29
Depends-On: no-dep -- builds on the renet `job` verbs and the CLI job client already on main; the related proxy plans are named under "Related plans" as boxes this plan must not break, not as prerequisites
Priority: P1 -- a held NDJSON stream bills the proxy Worker, the OrgExecutor Durable Object and its container for the whole run of every long proxied verb, a direct `renet execute` dies with its SSH channel (private/renet/cmd/renet/execute_command.go:195-212), and an rdc client on an unstable link (a train) loses, half-finishes or repeats any machine command whose connection drops
Concurrency: parallel -- J0b (audit, read-only, lead) runs first and gates J1b, J2b, J3b, J15 and every conversion box. Renet boxes run in sequence on shared files: J1, then J1b, then J1c. Contract: J2, then J2b. Executor: J3, then J3b (after J1b and J2b). Ticket store and steps: J5, then J15 (after J1b). J4 and the conversion boxes J16, J17, J18, J19 and J20 follow J0b, J3b and J15, and they run in parallel because their Owns are disjoint. J6, then J6b (after J2b, J3b and J15). J8, then J8b (after J6b). J21 follows J1c and J3b. J22 removes one BACKGROUND_UNSAFE entry per verb as each verb's conversion box lands. J7 follows J6b. J9 follows every code box. J23 runs any time. L0 and L3a run before any bench deploy of this branch, and L1, L2, L3b, L4 and L5 follow every code box. Overlaps with other plans: PLAN-cloudflare-proxy, PLAN-converge-preflight-and-repo-recovery and PLAN-renet-runtime-converge own packages/cli/src/services/executor/** broadly, and PLAN-cloudflare-proxy, PLAN-console-executor-multi-org, PLAN-proxy-cd-six-targets, PLAN-org-executor-connect-timeout-relocate and PLAN-telemetry-export own packages/cli/src/services/serve/server.ts or serve/**. Their open boxes are live or ops boxes, so a writer here runs while no writer of theirs holds the same file. PLAN-renet-bridge-leftovers owns private/renet/cmd/renet/job_commands.go, with only live boxes open. PLAN-backup-local-image owns section-disjoint parts of packages/cli/src/commands/machine/status.ts (renderPoolSummary only), packages/cli/src/commands/backup.ts (one register call), packages/cli/scripts/generate-cli-contract.ts (two PROXY_EXCLUSIONS entries), packages/cli/src/config/command-metadata.ts (two entries) and private/renet/pkg/list/types.go. A writer on one of those files waits until no writer of that plan holds it. Before J16-J20 spawn, J0b names every other plan that owns a converted command file, and the lead amends this line. workers/proxy/src/** is not edited (J10 only verifies it), so PLAN-executor-durable-object-policy's exclusive hold is untouched.
Owns: agent/plans/PLAN-detached-jobs.md, private/renet/cmd/renet/job_commands.go, private/renet/cmd/renet/job_commands_test.go, private/renet/pkg/jobs/jobs.go, private/renet/pkg/jobs/jobs_test.go, private/renet/pkg/jobs/logs.go, private/renet/pkg/jobs/logs_test.go, private/renet/pkg/jobs/overlap.go (new), private/renet/pkg/jobs/overlap_test.go (new), private/renet/pkg/jobs/steps.go (new), private/renet/pkg/jobs/steps_test.go (new), private/renet/pkg/jobs/retention.go (new), private/renet/pkg/jobs/retention_test.go (new), private/renet/pkg/list/jobs.go (new), private/renet/pkg/list/jobs_test.go (new), private/renet/pkg/list/list.go (the jobs section call only), private/renet/pkg/list/types.go (the jobs section only), private/renet (gitlink bump only), packages/cli/scripts/generate-cli-contract.ts, packages/cli/scripts/lib/plane-rules.ts, packages/shared/src/cli-contract/types.ts, packages/shared/src/cli-contract/validation.ts, packages/shared/src/cli-contract/wire.ts, packages/shared/src/cli-contract/data/contract.generated.ts (regenerated only), packages/shared/src/cli-contract/__tests__/**, packages/cli/src/cli.ts (the finished-notice lines only), packages/cli/src/types/index.ts (one exit code), packages/cli/src/services/executor/local-executor.ts, packages/cli/src/services/executor/detached-execution.ts, packages/cli/src/services/executor/job-client.ts, packages/cli/src/services/executor/job-remote.ts, packages/cli/src/services/executor/executor-factory.ts, packages/cli/src/services/executor/renet-command.ts, packages/cli/src/services/executor/types.ts, packages/cli/src/services/executor/proxy-command.ts, packages/cli/src/services/executor/proxy-client.ts, packages/cli/src/services/executor/__tests__/**, packages/cli/src/services/jobs/** (new), packages/cli/src/commands/job.ts, packages/cli/src/commands/__tests__/job-*.test.ts (new), packages/cli/src/commands/repo.ts, packages/cli/src/commands/repo-fork.ts, packages/cli/src/commands/repo-backup.ts, packages/cli/src/commands/repo-migrate.ts, packages/cli/src/commands/repo-create-delete.ts, packages/cli/src/commands/repo-maintenance.ts, packages/cli/src/commands/repo-prune.ts, packages/cli/src/commands/repo-trim.ts, packages/cli/src/commands/repo-branching.ts, packages/cli/src/commands/repo-extended.ts, packages/cli/src/commands/repo-promote.ts, packages/cli/src/commands/repo-container.ts, packages/cli/src/commands/repo-delta.ts, packages/cli/src/commands/repo-batch-utils.ts, packages/cli/src/commands/repo-replicate.ts, packages/cli/src/commands/repo-canary.ts, packages/cli/src/commands/repo-gpu.ts, packages/cli/src/commands/repo-policy.ts, packages/cli/src/commands/repo-admin.ts, packages/cli/src/commands/repo-cat.ts, packages/cli/src/commands/repo-diff.ts, packages/cli/src/commands/repo-backup-list.ts, packages/cli/src/utils/repo-target.ts, packages/cli/src/utils/repo-executor.ts, packages/cli/src/services/repo/repo-mount-check.ts, packages/cli/src/services/config/network-id-discovery.ts, packages/cli/src/commands/backup.ts, packages/cli/src/commands/backup-ops.ts, packages/cli/src/commands/backup-storage.ts, packages/cli/src/commands/backup-restore-path.ts, packages/cli/src/services/backup/backup-schedule-unit-generator.ts, packages/cli/src/commands/machine/register.ts, packages/cli/src/commands/machine/restart-services.ts, packages/cli/src/commands/machine/prune.ts, packages/cli/src/commands/machine/infra.ts, packages/cli/src/commands/machine/provision.ts, packages/cli/src/commands/machine/health.ts, packages/cli/src/commands/machine/gpu.ts, packages/cli/src/commands/machine/status.ts (the running-jobs section only), packages/cli/src/services/machine/machine-status.ts, packages/cli/src/commands/datastore.ts, packages/cli/src/commands/cluster/**, packages/cli/src/services/cluster/**, packages/cli/src/commands/subscription-actions.ts, packages/cli/src/commands/vscode-serve.ts, packages/cli/src/services/serve/server.ts, packages/cli/src/services/serve/command-dispatch.ts, packages/cli/src/services/serve/__tests__/job-poll*.test.ts (new), packages/cli/src/services/serve/__tests__/job-attach*.test.ts (new), packages/cli/src/services/serve/__tests__/command-dispatch.test.ts, packages/cli/src/commands/mcp/tool-factory.ts, packages/cli/src/commands/mcp/executor.ts, packages/cli/src/commands/mcp/__tests__/**, packages/cli/src/config/command-metadata.ts (the mcp fields of the converted verbs and the job tools only), packages/cli/src/i18n/locales/*/cli.json, private/account/web/src/hooks/useCommand.ts, private/account/web/src/hooks/__tests__/useCommand-*.test.ts, private/account/web/src/api/console.ts, private/account/src/routes/console.ts (the job poll relay only), private/account (gitlink bump only), packages/www/src/content/docs/*/proxy-and-executor.md, packages/www/src/content/docs/*/cli-application.md (regenerated only), .ci/rediacc_ci/ops/proxy_job_cost.py (new), .ci/rediacc_ci/tests/test_ops_proxy_job_cost.py (new), .ci/rediacc_ci/ops/job_latency.py (new), .ci/rediacc_ci/tests/test_ops_job_latency.py (new)
Live-Proof: bench, hostinger -- the serve, executor, ticket and step code under packages/cli/src is the cli surface (live on bench and hostinger). The renet job verbs, the overlap check and spool retention are the renet surface (live on hostinger only, .ci/config/proof-tiers.json surface `renet`). The console poll relay under private/account/src and the wire schema under packages/shared/src are the account surface (live on bench only). The added latency per short command is measured before and after on hostinger direct and through the bench proxy (L3a, L3b). The proxy surface (workers/proxy/src) is not edited.

## Context

### The problem

Three clients reach a machine for a long verb today, and each one ties the job's life or its bill to the client's connection:

1. **Direct SSH, foreground.** Every covered verb runs `renet execute` under the SSH channel (packages/cli/src/services/executor/local-executor.ts:203-214 picks the foreground path unless `options.detached` is set). renet catches SIGHUP and cancels the operation when the channel drops (private/renet/cmd/renet/execute_command.go:195-212). A laptop that sleeps, or a network change, cancels the work.
2. **Direct SSH, `-b/--background`.** The global flag (packages/cli/src/cli.ts:198, handled at :232-235) sets a process global that `backgroundDecorator` turns into `{ detached: true, follow: false }` on EVERY machine call the command makes (packages/cli/src/services/executor/executor-factory.ts:80-84), including short probes whose output the command needs. `isBackgroundRequested` (packages/cli/src/services/executor/executor-factory.ts:66) has no reader. Even a following detached run gives up after 5 reconnects (packages/cli/src/services/executor/job-remote.ts:55, :212-240), so a laptop that sleeps longer than about 20 s turns a running job into a failed command. Commit 53e96d940 made `-b` refuse the ten verbs it breaks (`BACKGROUND_UNSAFE`, packages/cli/src/services/executor/proxy-command.ts:66-78).
3. **The proxy (Cloudflare Worker, OrgExecutor Durable Object, executor container).** A served command runs every machine call detached AND followed (packages/cli/src/services/serve/command-dispatch.ts:389-405 hard-codes `follow: true`), and the route streams NDJSON until the job ends (packages/cli/src/services/serve/server.ts:260-263 announces `{kind:'job', jobId}`). The Durable Object counts the open body in flight (workers/proxy/src/org-executor.ts:96, fetch :283-322) and its alarm renews the lease and re-arms while `inFlight > 0` (:327-346), so the container never reaches its `sleepAfter = '2m'` (:89) during a run. agent/plans/PLAN-executor-durable-object-policy.md:151 records the same fact: "long NDJSON streams hold their slot". The web console (private/account/web/src/hooks/useCommand.ts:80) and the CLI proxy client (packages/cli/src/services/executor/proxy-client.ts:157, :387-421, `MAX_REATTACHES = 5`) both hold that stream.

The third-round amendment widens the problem from the long verbs to every machine command. A short `repo create` or `repo delete` interrupted by a train tunnel is as exposed as a long snapshot: the client cannot tell whether it ran, and a manual retry may run it twice.

### Measured evidence

- **The hostinger seed lost a 10-minute snapshot.** agent/plans/PLAN-backup-program.md:526 records `backup snapshot mautic --bwlimit 100Mbps --parallelism 2` rc=1 after 618 s with `signal: terminated` (go-executor duration_ms=600019). The immediate cause was the 10-minute renet default timeout, fixed by commit d6ea91581 (`resolveRenetTimeoutMs`, a 24 h ceiling for the data-moving backup functions in packages/cli/src/services/executor/renet-command.ts:89-109). That ceiling stays. The run also showed the second exposure: the snapshot ran in the foreground under one SSH channel for 10 minutes, so any client sleep in that window would have cancelled it the same way.
- **The Durable Object and container are billed for the held stream.** agent/plans/PLAN-cloudflare-proxy.md:221 states "In-flight streams still keep the instance alive", and :263 that "a long `repo up` stream keeps the container awake correctly". Container memory is billed on provisioned memory while the instance is awake (agent/plans/PLAN-cloudflare-proxy.md:231-242), and the monthly spend report already reads per-application container seconds (.ci/rediacc_ci/ops/cf_usage_report.py:12). No measurement of the per-run Durable Object wall time exists yet: L0 records the baseline before any code lands, and L2 the result.
- **No measurement exists of the job path's added latency per short command.** L3a records the baseline and L3b the result.

### What already exists (verified 2026-10-29)

- renet `job start|run|status|logs|cancel|list|gc` (private/renet/cmd/renet/job_commands.go). `job start` validates the vault synchronously before it spawns anything (:115-131). It then launches `systemd-run --unit=rediacc-job-<id> --remain-after-exit` (:195-210) and has a 10-minute `--timeout` default (:100). `job logs` takes `--since-line` and `--follow` (:577-609). Its follower checks for new lines every 250 ms and re-reads the status every 1 s (private/renet/pkg/jobs/logs.go:14, :19). The status file carries `state`, `exit_code`, `function`, `repo_guid`, `machine`, `unit`, `pid`, `started_at`, `finished_at` (private/renet/pkg/jobs/jobs.go:96-109). It records no user, config or client. GC removes terminal jobs older than a horizon (default 168 h, private/renet/cmd/renet/job_commands.go:42) only when asked (private/renet/pkg/jobs/jobs.go:500), and it resets failed units but never stops a finished `--remain-after-exit` unit (private/renet/cmd/renet/job_commands.go:741-750). Nothing calls GC on a timer.
- The spool layout: a durable `/var/lib/rediacc/jobs/<id>/` holding `status.json`, `events.ndjson`, `stderr.log` and `cancel.requested`, and a tmpfs `/run/rediacc/jobs/<id>/` for the vault, env and params, which are deleted when the job starts (private/renet/pkg/jobs/jobs.go:8-25).
- The CLI detached path: `runDetachedExecution` (packages/cli/src/services/executor/detached-execution.ts:58-129) and `startJob` (:140-195). `startJob` returns null when renet lacks `job` (:180-185). The caller turns that null into a silent foreground run (packages/cli/src/services/executor/local-executor.ts:211-213) after a warning (packages/cli/src/services/executor/job-client.ts:212-218).
- `rdc job list|status|logs|cancel|gc`, each requiring `-m <machine>` (packages/cli/src/commands/job.ts). MCP already exposes `job_list`, `job_status`, `job_logs` (without `--follow`) and `job_cancel` from the contract (packages/cli/src/config/command-metadata.ts:46-67).
- The contract's `detachable` flag is `proxyCapable && domain !== 'job'` minus an empty exclusion table (packages/cli/scripts/generate-cli-contract.ts:117, :503). The contract has 102 machine-plane commands. 84 are detachable. Five are the `job *` verbs (proxyable, not detachable). Thirteen are not proxyable: three interactive commands, `serve`, three `repo sync` transfers, and six local-effect or caller-secret commands (packages/cli/scripts/generate-cli-contract.ts:79-104, packages/cli/src/config/command-planes.ts:109, :135, :138, :151).
- MCP runs each tool as a child `rdc` through `execFile` with a kill timeout (packages/cli/src/commands/mcp/executor.ts:52-70): 300 s for writes and 120 s for reads (packages/cli/src/config/command-metadata.ts:41-42, applied at packages/cli/src/commands/mcp/tool-factory.ts:232).
- The proxy client's request timeout bounds the response headers only, 60 s by default (packages/cli/src/services/executor/proxy-client.ts:121-128).
- Exit code 15 `BUSY` ("another process holds the resource") exists with a `busy()` helper (packages/cli/src/types/index.ts:91, packages/cli/src/utils/cli-exit-error.ts:71-73), and nothing raises it yet.
- Machine-plane work that does not go through `renet execute`: `machine setup` runs `renet setup --auto` over SFTP exec (packages/cli/src/commands/machine/register.ts:324-336); `machine status` runs `renet list all --json` (packages/cli/src/services/machine/machine-status.ts:55-60); `backup run` runs `systemctl start` of a `Type=oneshot` unit (packages/cli/src/commands/backup-ops.ts:30, packages/cli/src/services/backup/backup-schedule-unit-generator.ts:267-269); `machine provision` runs OpenTofu as a local subprocess (packages/cli/src/services/tofu/executor.ts:8).

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

Ruling 1 is replaced by the third round below. Rulings 2, 3 and 4 stand. Ruling 2's "returns right after `job start`" is refined by the hybrid attach: the request returns when the job finishes or the attach window ends, whichever comes first.

## Design

Sections 1 to 13 are the first design. The third-round sections 14 to 26 amend them, and where the two disagree the third round wins. Each first-round section the third round changes carries a one-line note.

### 1. Which calls become jobs: by renet function, decided once

Amended by section 14: every renet call of a machine-plane command runs as a job, and `JOB_FUNCTIONS` is not built.

- `JOB_FUNCTIONS` in packages/cli/src/services/executor/renet-command.ts, beside the existing `DATA_TRANSFER_TIMEOUT_MS` set (:89-97): `repository_up`, `repository_up_all`, `repository_down`, `repository_down_all`, `repository_fork`, `backup_snapshot`, `backup_push`, `backup_pull`, `backup_restore`, `backup_restore_path`, `backup_verify`. J0 confirms the list against the verb audit and may add a function a covered verb reaches; it never adds a short read.
- The executor decides: a call whose `functionName` is in `JOB_FUNCTIONS` runs through `runDetachedExecution`, on every entry point (direct, daemon fallback, serve dispatch). Every other call stays `renet execute`, which is correct for a probe that answers in a second. `ExecuteOptions.detached` is no longer a caller's choice and is removed from the type (clean break).
- The contract's `detachable` keeps its name and narrows to "this command's long work runs as a job": an explicit `JOB_VERBS` table in generate-cli-contract.ts, each entry with its reason, replaces the derived rule and the empty `DETACH_EXCLUSIONS`. `detachable` still implies `proxyCapable` (packages/shared/src/cli-contract/validation.ts:322-325). Covered: `repo up`, `repo down`, `repo fork`, `repo push`, `repo pull`, `repo migrate`, `backup snapshot`, `backup restore`, `backup verify`, plus `backup restore-path` when PLAN-backup-restore-path lands its verb. `backup run` is decided in J0 (Open question 2).
- `-b` is accepted only on a `detachable` command, as today (packages/cli/src/services/executor/proxy-command.ts:72), so the narrowing changes which commands accept it. A refused command's message stays derived from the contract.

### 2. Direct SSH: start, follow by default, never fail because the watcher left

Amended by section 15: the start and the first follow are one SSH exec (`job start --attach`).

- Following stays a live `renet job logs --follow` tail over SSH: SSH is not billed per second, and the render path is already shared with `rdc job logs`.
- When the tail cannot be re-established after its reconnects, the command no longer fails as if the job had failed. It prints the resume hint, keeps the ticket, and exits `EXIT_CODES.DETACHED` (130, packages/cli/src/types/index.ts:92) for Ctrl-C or a new `FOLLOW_LOST` code for a lost transport (J3 picks the number; the table at packages/cli/src/types/index.ts:74-92 reserves 10 for renet and 11-15 for refusals).
- The reconnect ceiling for the direct tail rises from 5 attempts capped at 5 s (packages/cli/src/services/executor/job-remote.ts:55-60) to a time budget of 2 minutes with the same capped backoff, so a short Wi-Fi change does not detach.
- `-b`: the job function's start returns the ticket at once. Probes before it still run in the foreground. The JSON output under `-o json` is an envelope, `{ "jobId", "machine", "verb", "repo", "state": "running", "follow": "rdc job wait <id>" }`, never the plain hint text (today `backgroundStartedHint` goes to stdout in every output format, packages/cli/src/services/executor/detached-execution.ts:78), so MCP and scripts can parse it.

### 3. Verbs with more than one machine call: the terminal job

Amended by sections 14 and 18: the probes fold into the job as start preconditions, successors live on the ticket and in the spool, and local bookkeeping becomes ticket steps that run in the CLI.

A covered verb that keeps working after its job (a second machine call or local bookkeeping) cannot simply return at the start. The rule:

- Each covered verb marks exactly one job call as its terminal job (`ExecuteOptions.terminalJob: true`). Under `-b` and on the proxy, the command returns at that job's start.
- A job function called with `captureOutput` before the terminal job (a probe whose answer the command needs, such as `backup_verify` in `readSourceAnchor`, packages/cli/src/commands/backup.ts:485-500) is followed to completion in the same process, because the command cannot continue without it.
- A machine call AFTER the terminal job is a bug, and a test hook throws on it. J0 classifies every post-job tail, and J4 moves each one:
  - a second machine step joins the terminal job inside renet when renet already has a compound form (`repository_fork` with `up`, packages/cli/src/commands/repo-fork.ts:262-273), and the legacy client-side leg is removed when it exists only for a renet older than the job verbs;
  - a machine step with no compound form becomes the terminal job's successor recorded on the ticket (`then: <function, params>`), started by whichever client observes the first job's success (`rdc job wait`, the finished notice, or a proxy poll on the executor side), exactly once, keyed by the ticket's request id;
  - local bookkeeping (the deferred identity refresh, a config record) runs as the ticket's finalizer when success is observed, on the side that owns the config: the CLI on direct SSH, the executor on the proxy.
- J0 writes the per-verb table into this plan before J3 starts. Its default for `repo migrate` keeps the source deletion inside the job chain, never on a client that may be asleep.

### 4. Proxy wire protocol: return after start, then short polls

Amended by section 15: `/v1/command` waits up to the attach window inside the request, and returns the result directly when the job finishes within it.

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
- Container billing follows from the cap: a client polling every 30 s keeps the container awake (30 s is under the 2-minute `sleepAfter`), while a client that is gone (sleep, `-b`, MCP) costs nothing after the job starts. The Durable Object's billed duration falls from the whole run to the sum of poll durations. The second-round ruling keeps 2-30 s until L2 measures.

### 6. The ticket store

Amended by section 18: a ticket also mirrors the step plan and the claims. Section 16 covers the `starting` record written before every start.

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

Amended by section 18: the notice also triggers pending steps, within limits.

- The root `preAction` hook starts a background check of this config's pending tickets whose last check is older than 60 s: at most 5 tickets, in parallel, with a 2-second budget, one `job status` each (an SSH exec, or one proxy poll with `maxLines=0`).
- The `postAction` hook prints one line per newly finished ticket on stderr, never stdout, so `-o json` output stays parseable: `Job <id> (<verb> <repo>@<machine>) succeeded 12m ago. Details: rdc job logs <id>`. A failed job names its exit code. The ticket then becomes acknowledged.
- Skipped for `rdc job *` itself (which shows tickets anyway), under `-q`, and when the budget expires (the check retries on a later invocation).

### 9. renet changes (J1)

Extended by J1b and J1c (sections 15, 17, 19, 21, 22).

- `job start --request-id <uuid>`: the id is stored in the status file. A second start with the same id returns the existing handle with exit 0 and starts nothing.
- `job logs --max-lines <k>` (default 0, unlimited) bounds a non-follow read, and `--with-status` appends one trailer line `{"type":"job_status", ...}` after the events, so one SSH exec answers a poll.
- The status JSON keeps its fields. `exit_code` is already set by `finalizeJob` (private/renet/cmd/renet/job_commands.go:347-363).
- The 10-minute `job start --timeout` default (private/renet/cmd/renet/job_commands.go:100) is unchanged: the CLI already passes `resolveRenetTimeoutMs`. Section 20 sets the ceiling per function.
- Spool retention: section 22 replaces "unchanged".

### 10. Cancel semantics

- Ctrl-C while following detaches and never cancels (unchanged: packages/cli/src/services/executor/detached-execution.ts:106-117).
- `rdc job cancel <id>` (machine from the ticket) stops the unit through `renet job cancel`. The proxy route `POST /v1/jobs/:id/cancel` does the same under `job cancel` policy. A successor recorded on a cancelled ticket never starts. A failure step (section 18) runs on cancel, because a cancelled job did not succeed.
- The web console gains no cancel button in this plan (Out of scope).

### 11. The old-renet refusal

- `startJob` no longer returns null. renet without `job`, or without `--request-id`, `--max-lines` or `--attach`, raises `JobsUnsupportedError`: `renet on '<machine>' is older than this CLI and cannot run <verb> as a job. Upgrade it: rdc machine setup <machine>` (the wording of `renetOlderThanCliMessage`, packages/cli/src/services/executor/job-client.ts:162-164). It exits 1, and nothing ran, because cobra rejects an unknown command or flag before any work. `versionSkewWarning` and the foreground fallback (packages/cli/src/services/executor/local-executor.ts:211-213) are deleted. `machine setup` is the one command that must still reach an old renet. It uploads the new binary through the bootstrap (section 24) before its job starts, so the refusal never blocks the upgrade it names.

### 12. MCP tool shapes (J8)

Amended by section 15: an MCP tool waits up to the attach window and returns the result when the job finishes within it, otherwise the ticket envelope (ruling 4 holds for every run that outlasts the window).

- Each covered tool appends `--background` and returns the JSON envelope of Design 2 within seconds: `{ jobId, machine, verb, repo, state: "running", next: "job_status" }`. Its description says it starts a job and names `job_status` and `job_logs`.
- `job_status` and `job_logs` accept a job id alone (the ticket supplies the machine); `job_logs` keeps `since-line` for incremental reads. `job_wait` is not exposed: an agent cannot usefully block on it.
- The covered tools keep the 300 s kill timeout, which now bounds only the start. A killed starter leaves the ticket at `starting`, and the job, if it started, is found by its request id.

### 13. Telemetry

- The CLI command span gains `rediacc.job.id`, `rediacc.job.function`, `rediacc.job.follow` (`tail`, `poll`, `background`, `attached-finished`) and, for a followed run, `rediacc.job.polls`, `rediacc.job.outcome` and `rediacc.job.start_latency_ms` (from the exec to the first event, which L3b reads).
- The serve dispatch span gains `rediacc.proxy.route` (`command`, `job-poll`, `job-cancel`) so the request-duration drop is visible per route in the existing traces. No new exporter; the attributes ride the spans PLAN-telemetry-export already ships.

## Design, third round (2026-10-29)

### 14. Scope: one machine job per machine-plane command

- The scope is the contract's machine plane (packages/shared/src/cli-contract/data/contract.generated.ts, `plane: "machine"`): 102 commands. It is not a hand-kept list of long verbs. Section 24 lists the exceptions with their reasons. The `job *` verbs read the spool and are not jobs themselves.
- The rule: one command run makes at most one `renet job start` per machine it touches, plus successor jobs recorded in the spool and on the ticket. A command that spans machines (`cluster *`, the target leg of `repo migrate`) holds one job per machine under one ticket (`group: <requestId>`).
- How today's calls fold into that one job. J0b assigns each command one of four forms:
  1. **Single call.** The command makes one renet call. No command code changes: the executor runs the call as a job (J3b).
  2. **Shared probes become start preconditions.** The `resolveRepoRef` default verifier runs `repository_list` before the work (packages/cli/src/utils/repo-target.ts:35-45, packages/cli/src/services/repo/repo-mount-check.ts:55-60). `job start` already validates the vault synchronously, before any unit exists (private/renet/cmd/renet/job_commands.go:115-131). The verifier therefore becomes a vault precondition (`expect: { repo_present | repo_absent | repo_unmounted }`) that renet evaluates at that point, refusing with the probe's current message and no unit spawned. The `network_used` probe of `ensureRepositoryNetworkId` (packages/cli/src/services/config/network-id-discovery.ts:69) becomes `network_id: "auto"` in the vault. renet allocates the id inside the job and reports it in the result, and the config-registration step (section 18) records it.
  3. **Raw renet subcommands become command-kind jobs.** `renet setup --auto` (packages/cli/src/commands/machine/register.ts:324), `renet list all` (packages/cli/src/services/machine/machine-status.ts:57) and the `systemctl start` of backup units (packages/cli/src/commands/backup-ops.ts:30) are not vault functions. They run as `job start --command <name> --args <json>` against a fixed allow-list in renet (`setup`, `list-all`, `backup-unit`), never free-form argv.
  4. **Multi-call commands.** J0b names a compound renet function or a recorded successor for each one. `repo migrate` becomes one `repository_migrate` job, as the J0 audit recommends (push, down, delta push, down-unmount, up on the target, delete unless `--keep-source`, a `cutover_complete` marker). The job runs on the source machine. If source renet cannot drive the target's `repository_up` over the channel `backup_push` already uses, J0b records the target up as a successor job on the target under the same ticket.
- `ExecuteOptions.detached` is removed (clean break, as Design 1 already intended): every renet call through the executor is a job unless section 24 exempts it.

### 15. Hybrid attach

- One knob, `attachWindowMs` in `ExecuteOptions`, set by the entry point and never by the verb:

  | Entry point | Window | After the window |
  |---|---|---|
  | Direct SSH, a terminal or script | unlimited (attached for the whole run) | a drop reattaches (section 16) |
  | `--proxy` and the web console | 20 s inside `/v1/command` | ticket, then 2-30 s polls (Design 5) |
  | MCP tool (child `rdc`) | 20 s | ticket envelope (ruling 4) |
  | `-b` | 0 | ticket at once |

- Duration alone decides between a direct result and a ticket. No table of long and short verbs exists anywhere.
- renet `job start --attach <duration>` starts the job and streams its events in the same SSH exec until the job is terminal or the duration passes. It then writes one trailer line `{"type":"job_status", state, exit_code, deduped, overlaps}`. A short command therefore costs one SSH exec, as `renet execute` does today. While attached, the follower checks the status every 50 ms for the first 2 s, then at the existing 1 s interval (private/renet/pkg/jobs/logs.go:19), so a 300 ms job is not reported a second late. An unlimited window is `--attach 0s`, meaning "until terminal".
- Through the proxy, the executor calls `job start --attach 20s`. When the job finishes within the window, the route streams the events, the client-side steps run (section 18), the result line follows, and the request ends: one round trip. Otherwise the route writes `{kind:'job', jobId, machine, sinceLine}`, then a result with `state: 'running'`, and ends. The window counts from the job start. Pre-job work (renet acquire, key deploy) comes before it. During a quiet window the route writes a `{kind:'heartbeat'}` line every 10 s.
- **Why 20 s.** Each factor, with its source:
  1. *Workers request duration.* An HTTP request whose client stays connected has no wall-clock cap, and awaiting I/O does not consume CPU time. This is a hypothesis about the platform, to confirm against the Cloudflare documentation before J6b (CLAUDE.md rule 3). The window does not depend on it, because any value up to a minute stays inside the client's own header deadline (packages/cli/src/services/executor/proxy-client.ts:128). The route flushes headers at once, so that deadline never bites.
  2. *Durable Object billing in flight.* The Durable Object counts a request in flight until its body closes (workers/proxy/src/org-executor.ts:290-311), so each second inside the window is billed duration. 20 s caps a long command's in-request cost at 20 s instead of its whole run. A short command pays only its own duration, as today.
  3. *Container.* `sleepAfter = '2m'` (workers/proxy/src/org-executor.ts:89) dominates. Any window under 2 minutes adds no container time beyond the wake the request already causes.
  4. *systemd unit start.* `systemd-run` (private/renet/cmd/renet/job_commands.go:213-224), a second renet process (`job run`) and the spool writes add a few hundred milliseconds. That figure is a hypothesis: L3a and L3b measure it. It is noise against 20 s, so the window does not need to absorb it.
  5. *The proxy client's fetch and stream.* The client reads NDJSON lines as they arrive, so a 20 s window shows live progress, and the heartbeat keeps a mobile NAT mapping alive. A shorter window (5 s) would move every health-gated `repo create` or `repo delete` onto polls, adding at least one 2 s poll and its Durable Object request. A longer one (60 s) holds more bytes in flight across a tunnel and pays Durable Object duration for runs that are long anyway.
  6. *The measured split.* L3b records the duration of every short command it runs. If more than 10 % of the J0b "short" rows exceed 20 s on bench, the constant goes back to the operator. The constant is `JOB_ATTACH_WINDOW_MS = 20_000` in packages/cli/src/services/jobs/attach.ts, with an environment override for tests only.

### 16. Reattach and the ticket

- Before every `job start`, the CLI appends a `starting` ticket record carrying the request id (Design 6). That is one local append per command.
- **Direct SSH.** When the attached exec drops, the client reconnects with `job logs --since-line <last line received> --follow` within the 2-minute budget (Design 2). If the drop came before the handle arrived, the client retries `job start` with the same request id (section 17). If the budget runs out, the ticket keeps `lastSeenLine` and the command exits `FOLLOW_LOST`, with the hint `rdc job wait <id>`.
- **Proxy.** A drop after the job line resumes with polls from the last line received. A drop before the job line retries `POST /v1/command` with the same `requestId`, at most 3 times on the Design 5 ladder. The executor and renet deduplicate, so the retry attaches to the same job. When the retries run out, the ticket stays at `starting` with its request id, and `rdc job wait <id>` resolves it through `job list --request-id`.
- **Failure to reattach** always ends with the ticket kept. `rdc job wait <id>` and the finished-while-away notice pick it up, and the client-side steps run there (section 18).
- The executor does not abort a dispatch when its client disconnects during the window. It keeps the attach to the end of the window and runs the steps if the job finished, so a short command whose client lost the answer still completes its steps.

### 17. No double execution

- The request id is minted once per command invocation (a UUID). Each job of that invocation uses `<requestId>:<machine>:<seq>`.
- renet keeps a request index, `/var/lib/rediacc/jobs/.requests/<requestId>`, created with `O_EXCL` under the start lock (section 19). A second start with the same id returns the existing handle with `deduped: true` and starts nothing, even when two retries race.
- Every entry point carries the id: the direct executor, the serve dispatch (taken from the `POST /v1/command` body, else minted there), MCP (the child `rdc` mints it), and successor starts (derived from the ticket).
- Request-id dedupe is not overlap handling. The same request id means the same invocation retrying, and it attaches silently. A different request id against a live conflicting job is a second invocation (a user retyping the command, another user, the scheduler), and the overlap policy of section 19 applies.

### 18. Client-side steps on the ticket

- **The steps stay in the CLI** (operator ruling 5), with their behaviour unchanged: `postRepoUpTasks` (DNS, cert sync, service URLs; packages/cli/src/commands/repo.ts:111), `reconcileBackupSchedules`, `recordPushBase`, `recordBackupRun`, config registration and rollback, the identity refresh, and the output reports (push and restore stats, the verify verdict, the restore-path record).
- **A registry.** packages/cli/src/services/jobs/steps.ts maps a name to a handler that calls today's function. Each step declares `on: success | failure`, whether it needs the job's output, and its params, which are non-secret: repo name, machine, flags and the job id. A command body calls `runJob(call, steps)`. The code that today follows the call moves into steps. `runJob` returns `finished(result)` or `pending(ticket)`.
- **The step plan lives in the job spool.** `job start --steps <json>` writes `steps.json` (0600) into the job directory, so every observer finds the same plan: the direct CLI, the executor after a container restart, or `rdc job wait` in another process. The local ticket mirrors it.
- **Exactly once.** `renet job claim --id <id> --steps a,b` creates `steps/<name>.claim` with `O_EXCL`, recording the claimant (origin, host, pid), and `steps/<name>.done` afterwards. An observer runs only the steps it claimed. A claim older than 15 minutes, with no `done` and a claimant no longer alive on the same host, can be reclaimed. Every step is either idempotent (DNS upsert, cert sync, unit reconcile) or keyed by job id (`recordBackupRun`, `recordPushBase`), so a reclaimed rerun changes nothing. The local ticket records `step-done`. Only commands that have steps pay the claim exec, and those are the long ones.
- **Success and failure.** A success step runs only when the job's state is `succeeded`. This fixes today's `repo up`, which runs `postRepoUpTasks` after a failed up (packages/cli/src/commands/repo.ts:111). A failure step (the rollback, a failed `recordBackupRun`) runs only on `failed` or `cancelled`. `repo migrate`'s placement rewrite fires on the `cutover_complete` marker, not on success (J0 Surprise 4).
- **Config gate.** Steps run only for an observer whose config matches the origin's config id (section 19). Any other observer shows "N steps pending for config <name>".
- **Triggers.** The steps run when an observer first sees the job finished, wherever that happens:
  - inside the attach, on direct SSH or in the proxy window;
  - after a reattach;
  - in `rdc job wait <id>`;
  - on a proxy poll that observes the terminal state (the executor runs them);
  - from the finished-while-away notice, in an interactive text run only. The notice runs steps for up to 20 s after the command's own output. Under `-o json`, `-q` or MCP it never runs steps; it prints `steps pending: rdc job wait <id>` on stderr instead.
- **While the client is away**, nothing runs the steps. The consequences, per step:

  | Step | Effect of the delay until the client returns |
  |---|---|
  | `postRepoUpTasks` | The service answers on its IP. Its DNS names, cert sync and URL listing wait. |
  | `reconcileBackupSchedules` (after fork, migrate, restore) | The new repo has no backup units, so scheduled backups are missed. After migrate, the source units keep firing at a deleted repo and fail. |
  | `recordPushBase` | The next push is a full one, not a delta. Safe, but slower. |
  | `recordBackupRun` | A gap in the run history. |
  | Registration rollback (failed restore) | A stale config entry for a target that does not exist. |
  | Identity refresh (fork) | The license identity stays stale. Already warn-only today. |

  Default: accept the delay, and make it visible. `rdc job list` and the notice show "steps pending". `reconcileBackupSchedules` is the one step with data risk (missed backups), and the trade-offs list a nudge for it, which needs an operator ruling because it would move work out of the CLI.

### 19. Overlapping jobs: warn, refuse, and show the attach command

- **The check.** `job start` takes an exclusive `flock` on `/var/lib/rediacc/jobs/.lock`, then:
  1. resolves the request id (section 17);
  2. lists the live jobs in the spool (non-terminal, reconciled against systemd as `job status` already does, private/renet/cmd/renet/job_commands.go:437);
  3. lists the active `rediacc-backup-*` units (the scheduler; unit names at packages/cli/src/commands/backup-ops.ts:99 and :241);
  4. applies the policy table;
  5. creates the job, all before releasing the lock.

  The check costs no extra exec, because it is folded into `job start`. The same scan backs `job list --active`.
- **What the spool records today:** function, machine (the vault's machine name), repo GUID, unit, pid and start time (private/renet/pkg/jobs/jobs.go:96-109). It records no user, config or client. `CaptureEnv` keeps only `REDIACC_SECRET_*`, `REDIACC_OTLP_*` and three exact keys (private/renet/pkg/jobs/jobs.go:552-561). **To add:** `origin` in `status.json`:
  - `client`: `rdc`, `proxy`, `mcp`, `console` or `scheduler`;
  - `version`: the rdc version;
  - `ssh_user`: read by renet from `SUDO_USER`, as a label only;
  - `config`: the config name and a short config id;
  - `actor`: the account principal, on the proxy and console paths only.

  The CLI passes it as `job start --origin <json>`, capped at 1 KiB. renet records `SUDO_USER` itself.
- **Lock classes**, a table in renet keyed by function and command kind. J0b assigns every function to one:
  - `repo-exclusive`: up, down, fork (on the new repo), migrate, delete, resize, expand, restore, pull into a repo, commit, merge, promote, checkout, gc, trim, prune, fsck;
  - `repo-shared`: snapshot, push, verify, fork (on the source), non-interactive exec;
  - `machine-exclusive`: `setup`, machine prune, restart-services, infra push, the datastore lifecycle, the `*_all` functions;
  - `read`: list, status, health, logs, cat, diff.
- **Policy**, per pair with the same scope (the same repo GUID, or the machine for `machine-exclusive`):

  | New \ Live | repo-exclusive | repo-shared | machine-exclusive | read | scheduled backup unit |
  |---|---|---|---|---|---|
  | repo-exclusive | refuse | refuse | refuse | warn | warn |
  | repo-shared | refuse | warn | refuse | warn | warn |
  | machine-exclusive | refuse | refuse | refuse | warn | warn |
  | read | warn | warn | warn | silent | warn |

  - A second `repo up`, `repo migrate` or `backup restore` on the same repo therefore refuses rather than races.
  - Scheduled units only warn, because renet cannot map a strategy unit to its repos.
  - A refusal exits 15 (`BUSY`, packages/cli/src/types/index.ts:91) with `{"refused":"overlap", overlaps:[...]}` on stdout. The CLI keys on the JSON, not on the exit code alone.
  - There is no override flag in this plan. The way out is `rdc job wait`, or `rdc job cancel` on the other job.
- **The warning.** For each overlapping job the CLI prints one line on stderr: job id, verb (mapped from the function), repo (the name from this config, else the GUID), started-at, origin (`started by <ssh_user> via <client> (config <name>)`, or `started by: unknown (older renet)`) and state. Then the exact command: `rdc job logs <id> -m <machine> --follow`, or `rdc job wait <id>` when the ticket is this config's own. A scheduled unit prints `rdc backup status -m <machine>`.
- **Structured, everywhere.** The handle trailer, the `-o json` envelope, the proxy `job` wire line and the refusal `result` all carry `overlaps: [{ jobId, function, verb?, repoGuid?, repo?, state, startedAt, origin?, unit?, attach }]`. The MCP envelope carries the same array, and the web console renders it (J7 note).
- **Status surfaces.** `renet list all` gains a `jobs` section: live jobs, plus jobs that finished in the last hour. `machine status` renders it from the call it already makes (packages/cli/src/services/machine/machine-status.ts:57), at no extra exec. `repo status` (packages/cli/src/commands/repo.ts:293) shows the jobs on that repo's GUID, from the same section or the status function's payload, whichever J0b finds already called.

### 20. The timeout ceiling, per function

- Today `resolveRenetTimeoutMs` gives 24 h only to the six data-moving backup functions (packages/cli/src/services/executor/renet-command.ts:91-109). Everything else gets renet's 10-minute default.
- The rule: a function gets 24 h when its run time grows with the data it moves, or when it waits on a health gate. That covers the six backup functions, `repository_up`, `repository_up_all`, `repository_fork`, `repository_migrate`, `repository_expand`, the resize and create functions, the datastore and cluster lifecycle functions, and the command-kind `setup` and `backup-unit`. Every other function keeps the 10-minute default. There are two classes and no middle one.
- J3b turns the set into an explicit two-way table that names every function in packages/shared/src/renet-contract/data/license-tiers.generated.ts. A test fails on any function in neither set, so a new renet function forces a decision.
- The cost: a hung 24 h job holds its overlap lock for up to 24 h. The refusal message names `rdc job cancel <id>`.

### 21. `backup run`

- Today a deployed unit blocks on `systemctl start` of a `Type=oneshot` unit with `TimeoutStartSec=infinity` (packages/cli/src/commands/backup-ops.ts:30, packages/cli/src/services/backup/backup-schedule-unit-generator.ts:267-269). The ad-hoc path returns at the start (packages/cli/src/services/backup/backup-schedule-unit-generator.ts:217).
- Decision: `backup run` becomes a command-kind job, `job start --command backup-unit --args {"unit": "<name>"}`. Inside the job, renet runs `systemctl start <unit>`, blocking inside the job unit rather than on the client. The spool then records the start, the finish and the exit code, the overlap check sees it, and the ticket, attach and steps work as for every other command. The ad-hoc path folds in the same way, with the job running the strategy commands instead of its own `systemd-run`.
- `--no-block` plus a ticket on the unit is the alternative, listed under the trade-offs.

### 22. Spool retention and unit cleanup

- **Today.** There is no timer GC. `job gc` defaults to 168 h only when called. GC resets failed units but never stops a finished `--remain-after-exit` unit (private/renet/cmd/renet/job_commands.go:42, :741-750). That flag is what lets `job status` read the exit status (:189-194). With every command a job, the spool directories and the loaded transient units both grow without bound. A monitoring loop of `repo status` once a minute leaves 1440 jobs a day.
- **Retention.** `job start` runs an opportunistic GC under the start lock, at most once an hour (a stamp file).
  - A terminal `read`-class job is kept 1 hour.
  - Any other terminal job is kept 7 days, the existing default.
  - A hard cap of 2000 terminal jobs or 256 MiB of spool collects the oldest terminal jobs first.
  - A running job is never collected.
  - A job with unclaimed steps is kept until 7 days have passed, whatever its class.
- **Units.** Once `status.json` is terminal, the unit has done its job. The stop happens on the first `job status` or GC that sees the terminal status (`stopUnit`, private/renet/cmd/renet/job_commands.go:535-540), so a `rediacc-job-*` unit does not outlive its job by more than one observation or one GC pass.
- L4 measures the spool size, the job count and the loaded-unit count after a burst, and after GC.

### 23. Latency cost per short command

- **Before:** one SSH exec of `renet execute`. **After:** one SSH exec of `job start --attach`, which adds the vault validation already present, the lock and overlap scan, the request index, `systemd-run`, a second renet process start, the spool writes, and the follower's detection of the terminal status.
- **Budget:** p50 plus 500 ms and p95 plus 1 s per short command, on hostinger direct and through the bench proxy. L3a measures the baseline and L3b the result, with the J23 script.
- Past the budget, the result goes to the operator with the measured breakdown. The known levers are inotify instead of polling in the follower, skipping the GC stamp check, and caching the origin JSON. A foreground fallback is not a lever, because ruling 1 was a clean break.

### 24. Exceptions: machine-plane commands that do not run as jobs

| Command | Reason |
|---|---|
| `term connect` (default form), `repo tunnel`, `vscode connect` | Interactive: a TTY or a tunnel held until Ctrl-C (packages/cli/src/config/command-planes.ts:109, :135, :138). |
| `repo exec -i` (`tty: true`) | An interactive exec needs a live TTY (packages/cli/src/commands/repo-container.ts:127). Plain `repo exec` is a job, with its output in the spool. |
| `repo logs -f` | A follow that never ends on its own (packages/cli/src/commands/repo-container.ts:68). The plain `repo logs` read is a job. |
| `repo sync upload`, `repo sync download`, `repo sync status` | Client-side transfers that rely on rsync's own resume. The files are on the laptop (packages/cli/scripts/generate-cli-contract.ts:81-87). |
| `backup download`, `backup upload` (planned, agent/plans/PLAN-backup-local-image.md) | Client-side rsync transfers with their own resume and state file. |
| `machine scan-keys`, `machine infra cert pull`, `cluster kubeconfig`, `config reconcile`, `machine access push`, `machine converge` | Not proxyable: their effect, or the secrets they carry, belong to the caller (packages/cli/scripts/generate-cli-contract.ts:89-103). J0b decides per command whether the machine-side part becomes a job while the local write stays in the CLI. Default: they become jobs when they make a renet call, and stay exempt from the proxy. |
| `serve` | The executor daemon itself (packages/cli/src/config/command-planes.ts:151). |
| `job list`, `job status`, `job logs`, `job cancel`, `job gc`, `job wait` | They read or drive the spool. A job per job query is circular. |
| The renet bootstrap inside every command (`acquireRemoteRenet`, packages/cli/src/commands/machine/register.ts:310) | It installs or verifies the binary that runs jobs. It is a version check plus, at worst, a re-upload, which is safe to repeat after a drop. |
| The local OpenTofu legs of `machine provision` and `machine deprovision` (packages/cli/src/services/tofu/executor.ts:8) | They run on the laptop against the cloud API, before or after any SSH. Tofu's state makes a rerun converge. The SSH legs after provisioning (setup) are jobs. |
| Config-plane and other-plane commands (57 config, 31 other in the contract) | They never touch a machine. |

### 25. The `-b` refusal stays until each verb is converted

`BACKGROUND_UNSAFE` (packages/cli/src/services/executor/proxy-command.ts:66-78) keeps refusing its ten verbs. J22 removes an entry only when that verb's conversion box has landed (one job, steps on the ticket). An invariant test then holds every detachable verb in exactly one of two states: still in `BACKGROUND_UNSAFE`, or listed in the converted registry (packages/cli/src/services/jobs/plans.ts). Being in both, or in neither, fails the test.

### 26. `-b -o json` prints the hint on stdout

`backgroundStartedHint` is written to stdout in every output format (packages/cli/src/services/executor/detached-execution.ts:78). J3 already replaces it with the JSON envelope under `-o json`. J3b keeps that fix, sends the text hint to stderr in text mode, and adds `overlaps` to the envelope.

### Related plans: boxes touched or not to break

- PLAN-cloudflare-proxy.md B4 (:40), the nightly e2e of `repo status`, `repo up` and `repo down` through a local serve: its re-attach assertion changes meaning. J6 and J6b add the attach and poll path's in-process tests, and B4's writer asserts the attach window and polls instead of the held stream. The box text is left to that plan.
- PLAN-cloudflare-proxy.md Phase 2 step 4 (:115), "Proves egress, streaming, detach and re-attach through the Worker": after J6b it proves attach-then-poll. No box of that plan is edited here.
- agent/plans/PLAN-executor-durable-object-policy.md:151: the lease renewal while in flight stays correct for the attach window and the remaining streams. Nothing in workers/proxy/src changes (J10), so its exclusive Owns and its L-boxes are untouched.
- PLAN-console-executor-multi-org.md: the per-org container, token and audit trail are unchanged. The new routes authenticate through the same `authenticate` and per-org policy path as `/v1/command`.
- PLAN-cloudflare-spend-guard.md T6 owns cf_usage_report.py. L2's measurement lives in a new module that imports its GraphQL helper rather than editing it.
- PLAN-proxy-cd-six-targets.md: the deploy shape is unchanged; the new routes ship with the executor image like every serve route.
- PLAN-backup-restore-path.md: `backup restore-path` is a route of `backup restore` (J0 audit). Its record print becomes a ticket step.
- PLAN-backup-local-image.md: `backup download` and `backup upload` are exceptions (section 24). Its `machine status` pool section and this plan's running-jobs section are disjoint parts of packages/cli/src/commands/machine/status.ts.

## Tasks

- [x] J0 [lead] Verb audit, read-only. For each covered verb, list its machine calls in order (function, `captureOutput` or not, terminal or not), every post-job tail with its class (compound in renet, successor, finalizer, delete), and whether `-b` today detaches a probe. Settle `backup run` (Open question 2) and the timeout question of Design 9. Write the table into a new "Verb audit" section of this plan with file:line evidence.
  Owns: agent/plans/PLAN-detached-jobs.md. Accept: `python3 .ci/scripts/quality/check_plan_citations.py` rc 0 and `python3 .ci/scripts/quality/check_plan_deps.py` rc 0.
    (ticked) 2026-10-29T10:19:43Z by d778be9d: commit:53e96d940 J0 audit section in the plan; citations and deps gates show no finding

- [x] J0b [lead] Machine-plane job audit, read-only: one table row per machine-plane command in packages/shared/src/cli-contract/data/contract.generated.ts (102 at 2026-10-29). That is the nine covered verbs of J0 (re-checked; the detachable set is 9 covered + 75 others = 84), the 75 others listed under "The 84 `detachable` commands" (including machine setup, machine provision, the datastore verbs, the cluster verbs, repo resize, repo gc and repo prune), the five `job *` verbs and the thirteen non-proxyable commands. Columns:
  1. command, and its CLI entry file:line;
  2. machine calls in order (renet function, raw renet subcommand, SFTP, systemctl or local subprocess);
  3. single-job form (single call, precondition fold, command-kind, compound function, successor) or the section 24 exception and its reason;
  4. client-side steps, each with its trigger (`success` or `failure`);
  5. timeout class (section 20);
  6. lock class (section 19);
  7. retention class (section 22);
  8. `-b` today;
  9. the conversion box (J4, J16-J20).
    (ticked) 2026-10-29T11:34:34Z by d778be9d: commit:dc503e38b

  It also names every other plan whose Owns cover a converted command file, so the lead can amend the Concurrency line, and confirms or corrects the target-up channel of `repository_migrate` (section 14).
  Owns: agent/plans/PLAN-detached-jobs.md. Accept: `python3 .ci/scripts/quality/check_plan_citations.py` rc 0, `python3 .ci/scripts/quality/check_plan_deps.py` rc 0, and the row count in the "Machine-plane job audit" section equals the output of `awk -F'"' '/"pathKey"/{p=$4} /^      "plane"/{if($4=="machine")n++} END{print n}' packages/shared/src/cli-contract/data/contract.generated.ts`.

- [x] J1 [writer] renet: `job start --request-id` (idempotent start), `job logs --max-lines` and `--with-status` (Design 9). Changes:
    (ticked) 2026-10-29 by d778be9d: J1 landed in renet ea953b6 against its own request index, `<jobs>/.requests/<id>` claimed through a staged hard link (an exclusive create, private/renet/pkg/jobs/jobs.go ClaimRequest); its tests (TestLaunchJobDedupesRequestID: a second start spawns nothing; TestLaunchJobRacingSameRequestID: 16 racers, one spawn; TestReplayMaxLinesBoundsRead with a byte-identical default control; TestReplayWithStatusAppendsOneTrailer) run on J1 alone. J1b moves the claim under the spool lock.
  - the request id lands in `jobs.Status` and a lookup by request id returns the existing handle;
  - the logs reader stops after k complete lines and appends the status trailer;
  - help text for both flags.
    (ticked) 2026-10-29T11:26:20Z by d778be9d: commit:2d1a1b193

  Tests: a second start with the same request id starts no second unit (fake systemd-run seam) and prints the first handle; `--max-lines 2` on a 5-line spool returns 2 lines and `--with-status` adds exactly one trailer line whose state matches the status file; control: without the flags the output is byte-identical to today's.

  Owns: private/renet/cmd/renet/job_commands.go, private/renet/cmd/renet/job_commands_test.go, private/renet/pkg/jobs/jobs.go, private/renet/pkg/jobs/jobs_test.go, private/renet (the gitlink bump only). Accept: `cd private/renet && go test ./cmd/renet/ ./pkg/jobs/` rc 0, and `cd private/renet && go vet ./cmd/renet/ ./pkg/jobs/` rc 0.
  Amended (third round): the request lookup goes through J1b's `O_EXCL` index under the start lock, not a spool scan; J1 may land the flag and J1b the index.

- [x] J1b [writer] renet attach, origin, overlap and steps. After J1. Changes:
  - `job start --attach <dur>` streams events and a status trailer in the same exec, with 50 ms status checks for the first 2 s (section 15);
  - the start lock and the request index `.requests/<id>` created with `O_EXCL` (section 17);
  - `--origin <json>` (1 KiB cap) and `SUDO_USER` recorded as `origin` in `status.json`;
  - the lock-class table and the overlap policy, with `overlaps` in the trailer and the `{"refused":"overlap"}` refusal exiting 15; active `rediacc-backup-*` units included (section 19);
  - `job start --steps <json>` writing `steps.json`, and `job claim --id --steps` with `O_EXCL` claim and done markers (section 18);
  - command-kind jobs `job start --command setup|list-all|backup-unit --args <json>` against a fixed allow-list (section 14);
  - `job list --active` and `job list --request-id`.
    (ticked) 2026-10-29T11:57:08Z by d778be9d: commit:65243dc8a

  Tests:
  - two concurrent starts with one request id spawn one unit (fake systemd-run seam, goroutines);
  - a `repo-exclusive` start against a live `repo-exclusive` job on the same GUID exits 15 with one overlap entry carrying the origin, and spawns nothing;
  - `repo-shared` against `repo-shared` starts and lists the other job in `overlaps`;
  - a `read` start never refuses;
  - a fake active `rediacc-backup-x.service` appears as a warning;
  - a second claim of a claimed step answers `already-claimed`;
  - `--command rm` is refused by the allow-list;
  - `--attach 1s` on a job that finishes in 300 ms returns its trailer in under 500 ms;
  - control: a start with none of the new flags behaves as today.

  Owns: private/renet/cmd/renet/job_commands.go, private/renet/cmd/renet/job_commands_test.go, private/renet/pkg/jobs/jobs.go, private/renet/pkg/jobs/jobs_test.go, private/renet/pkg/jobs/logs.go, private/renet/pkg/jobs/logs_test.go, private/renet/pkg/jobs/overlap.go (new), private/renet/pkg/jobs/overlap_test.go (new), private/renet/pkg/jobs/steps.go (new), private/renet/pkg/jobs/steps_test.go (new), private/renet (gitlink bump only). Accept: `cd private/renet && go test ./cmd/renet/ ./pkg/jobs/` rc 0, and `cd private/renet && go vet ./cmd/renet/ ./pkg/jobs/` rc 0.

- [x] J1c [writer] renet retention, unit cleanup and the jobs section. After J1b. Changes:
  - opportunistic GC in `job start` under the lock, at most hourly, with the retention classes, the count and size cap, and the pending-steps hold (section 22);
  - `stopUnit` on a terminal job at the first status read or GC;
  - `renet list all` gains a `jobs` section: live jobs plus those finished in the last hour, with origin (section 19).
    (ticked) 2026-10-29T12:17:23Z by d778be9d: commit:2308cbe89

  Tests:
  - a spool of 2100 terminal jobs is cut to the cap, oldest first;
  - a running job and a job with an unclaimed step survive GC;
  - a terminal `read` job older than 1 h is collected and a 2 h old `repo-exclusive` one is kept;
  - the GC stamp prevents a second pass within the hour;
  - the stop seam is called once per terminal job;
  - `list all --json` carries `jobs` with one live entry;
  - control: an empty spool yields `jobs: []` and no GC error.

  Owns: private/renet/pkg/jobs/retention.go (new), private/renet/pkg/jobs/retention_test.go (new), private/renet/cmd/renet/job_commands.go, private/renet/cmd/renet/job_commands_test.go, private/renet/pkg/list/jobs.go (new), private/renet/pkg/list/jobs_test.go (new), private/renet/pkg/list/list.go (the jobs section call only), private/renet/pkg/list/types.go (the jobs section only), private/renet (gitlink bump only). Accept: `cd private/renet && go test ./cmd/renet/ ./pkg/jobs/ ./pkg/list/` rc 0, and `cd private/renet && go vet ./cmd/renet/ ./pkg/jobs/ ./pkg/list/` rc 0.

- [ ] J2 [writer] Contract: `detachable` narrows to the covered verbs through an explicit `JOB_VERBS` table with reasons (Design 1); the job wire line gains `machine`; the poll response schema and the poll and cancel routes join `PROXY_ROUTES`; `jobEvents` and `jobEventsPattern` are removed. The lead regenerates the contract with `npm run generate:cli-contract -w @rediacc/cli` after the writer's edit.

  Tests: the contract test asserts the exact covered set and that no `domain === 'job'` command is detachable; the poll schema round-trips a sample and refuses a body without `nextLine`; control: a planted `repo list` in `JOB_VERBS` makes the set test red.

  Owns: packages/cli/scripts/generate-cli-contract.ts, packages/cli/scripts/lib/plane-rules.ts, packages/shared/src/cli-contract/types.ts, packages/shared/src/cli-contract/validation.ts, packages/shared/src/cli-contract/wire.ts, packages/shared/src/cli-contract/data/contract.generated.ts (regenerated only), packages/shared/src/cli-contract/__tests__/**. Accept: `cd packages/shared && npx vitest run src/cli-contract` rc 0, and `npx tsc --noEmit --project packages/shared/tsconfig.json` rc 0.
  Superseded in part (third round): the `JOB_VERBS` narrowing is not built. J2b keeps the derived `detachable` rule. J2's wire, poll and route changes stand.

- [ ] J2b [writer] Contract, third round. After J0b and J2. Changes:
  - `detachable` stays `proxyCapable && domain !== 'job'`, with `DETACH_EXCLUSIONS` filled from the section 24 exceptions that are proxyable, each with its reason;
  - `POST /v1/command` accepts `requestId`;
  - the `job` line gains `overlaps`, a `heartbeat` line kind is added, and the result gains `state: 'running'`, `attached: boolean` and `overlaps`;
  - the `-b` envelope schema `{ jobId, machine, verb, repo, state, follow, overlaps }` is shared by the CLI and MCP.

  Tests:
  - the contract test pins the detachable set to the J0b table;
  - `overlaps` round-trips, and an entry without `jobId` is refused;
  - a heartbeat line validates;
  - control: a planted unknown key in `DETACH_EXCLUSIONS` fails the existing key check (packages/cli/scripts/generate-cli-contract.ts:333-365).

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
  Superseded in part (third round): `JOB_FUNCTIONS` is not built, and `repository_list` does not stay on `renet execute`; J3b makes every call a job and folds the probe into a precondition. The refusal, `FOLLOW_LOST`, reconnect budget, envelope and span items stand, and J3b may absorb them if J3 has not landed.

- [ ] J3b [writer] CLI executor, third round. After J0b, J1b, J2b and J3. Changes:
  - every renet call of a machine-plane command runs through `job start --attach`, with `attachWindowMs` by entry point, and the section 24 exemptions (`tty: true`, follow logs) stay on `renet execute` through a named exemption predicate (sections 14, 15);
  - the request id per invocation and per job, with a retry of a start whose handle was lost (section 17);
  - `--origin` built from the client kind, version and config (section 19);
  - the `expect` precondition in the vault replaces the client-side `repository_list` verifier, and `network_id: "auto"` replaces the `network_used` probe (section 14);
  - the two-way timeout table naming every function in packages/shared/src/renet-contract/data/license-tiers.generated.ts (section 20);
  - the overlap warning on stderr, the BUSY refusal (`busy()`, packages/cli/src/utils/cli-exit-error.ts:71) and `overlaps` in the envelope; the text hint goes to stderr (section 26).

  Tests:
  - `repo list` makes exactly one `job start --attach 0s` exec and no `renet execute` (recording SFTP fake);
  - `repo exec -i` stays on `renet execute`;
  - a handle lost mid-exec is retried with the same request id and yields one job;
  - a trailer with `refused: overlap` exits 15, prints the attach command, and makes no further call;
  - a planted function missing from both timeout sets fails the table test;
  - `-b -o json` stdout parses as one envelope with `overlaps` and carries no hint text;
  - control: a job finishing within the attach returns its exit code with no ticket left pending.

  Owns: packages/cli/src/services/executor/local-executor.ts, packages/cli/src/services/executor/detached-execution.ts, packages/cli/src/services/executor/job-client.ts, packages/cli/src/services/executor/job-remote.ts, packages/cli/src/services/executor/executor-factory.ts, packages/cli/src/services/executor/renet-command.ts, packages/cli/src/services/executor/types.ts, packages/cli/src/services/executor/__tests__/** (except proxy-client tests), packages/cli/src/utils/repo-target.ts, packages/cli/src/services/repo/repo-mount-check.ts, packages/cli/src/services/config/network-id-discovery.ts. Accept: `cd packages/cli && npx vitest run src/services/executor` rc 0, and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.

- [ ] J4 [writer] Verb tails, per J0's table. After J0 and J3. Each covered verb marks its terminal job; compound renet forms replace client-side second legs where renet has them; successors and finalizers register on the ticket (Design 3).

  Tests: one per verb class from J0's table (compound, successor, finalizer), each driving the verb against the recording executor under `-b` and asserting it returns at the terminal start with the successor or finalizer recorded on the ticket; control: the same verb followed runs the tail in-process exactly once.

  Owns: packages/cli/src/commands/repo-fork.ts, packages/cli/src/commands/repo-backup.ts, packages/cli/src/commands/repo-migrate.ts, packages/cli/src/commands/backup.ts, packages/cli/src/commands/backup-ops.ts, packages/cli/src/commands/backup-storage.ts (the snapshot action only), packages/cli/src/commands/__tests__/job-tails.test.ts (new). Accept: `cd packages/cli && npx vitest run src/commands/__tests__/job-tails.test.ts` rc 0, and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.
  Amended (third round): follows J0b, J3b and J15 as well. Finalizers are J15 steps (`runJob` with `on: success|failure`). `repo migrate` uses the `repository_migrate` compound job, which J1b's allow-list or a renet function provides, as J0b decides. `repo up`, `repo down`, `repo checkout`, `repo commit` and `backup restore-path` join this box's verbs, with packages/cli/src/commands/repo.ts, packages/cli/src/commands/repo-branching.ts and packages/cli/src/commands/backup-restore-path.ts added to its Owns.

- [x] J5 [writer] Ticket store, `rdc job list` and `rdc job wait`, the optional `-m`, and the finished notice (Design 6, 7, 8). Adds the en locale keys for these strings.
    (ticked) 2026-10-29T11:39:12Z by d778be9d: commit:cd565de8b

  Tests: two processes appending concurrently lose no ticket; the store file is 0600 and its directory 0700; no planted vault or env value appears in the file; `job wait` resumes from `lastSeenLine` and exits with the job's code; the notice prints on stderr only and once per ticket; a `jobs/` file never shows up in `rdc config list`; control: with no tickets the notice makes zero machine calls.

  Owns: packages/cli/src/services/jobs/** (new), packages/cli/src/commands/job.ts, packages/cli/src/commands/__tests__/job-wait.test.ts (new), packages/cli/src/commands/__tests__/job-tickets.test.ts (new), packages/cli/src/cli.ts (the finished-notice lines only), packages/cli/src/i18n/locales/en/cli.json. Accept: `cd packages/cli && npx vitest run src/services/jobs src/commands/__tests__/job-wait.test.ts src/commands/__tests__/job-tickets.test.ts` rc 0, and `npm run check:ci-i18n-cli-key-usage` rc 0.
  Amended (third round): a `starting` record is appended before every start (section 16), and `job wait` resolves a ticket stuck at `starting` through `job list --request-id`.
    (review note 2026-10-29, 9f92c43e) The tick records the vitest result only. Rerun 2026-10-29: `npm run check:ci-i18n-cli-key-usage` rc=0.

- [x] J15 [writer] Ticket steps and `runJob`. After J1b and J5. Changes:
  - packages/cli/src/services/jobs/steps.ts holds the registry, packages/cli/src/services/jobs/run-job.ts holds `runJob(call, steps)`, packages/cli/src/services/jobs/attach.ts holds `JOB_ATTACH_WINDOW_MS`, and packages/cli/src/services/jobs/plans.ts holds the converted-verb registry (sections 15, 18, 25);
  - steps are stored in the spool with `--steps` and claimed with `job claim`, and the ticket mirrors `step-done`;
  - the config gate;
  - triggers from the attach finish, the reattach, `job wait` and the notice (interactive text runs only, 20 s budget; otherwise the "steps pending" line).
    (ticked) 2026-10-29T12:22:37Z by d778be9d: commit:59fdb8e06

  Tests:
  - two observers in parallel (a `job wait` and a notice) run a success step exactly once;
  - a success step never runs on `failed` and a failure step never on `succeeded`; `cancelled` runs the failure step;
  - a stale claim whose claimant pid is dead is reclaimed, and the rerun of a job-id-keyed step is a no-op;
  - an observer from another config runs nothing and prints the pending line;
  - the notice under `-o json` runs no step and keeps stdout parseable;
  - the steps file never contains a planted secret;
  - control: a job finishing inside the attach runs its steps inline once, with no ticket left pending.

  Owns: packages/cli/src/services/jobs/** (new), packages/cli/src/cli.ts (the finished-notice lines only), packages/cli/src/commands/__tests__/job-steps.test.ts (new), packages/cli/src/i18n/locales/en/cli.json. Accept: `cd packages/cli && npx vitest run src/services/jobs src/commands/__tests__/job-steps.test.ts` rc 0, and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.

- [ ] J16 [writer] Conversions, repo verbs outside J4, per J0b's rows. After J0b, J3b and J15. Each command becomes one job (single call, precondition fold or compound) with its steps on the ticket. Every probe after the main call is moved into the job or recorded as a successor. `repository_commit_meta` after an immutable push (packages/cli/src/commands/repo-delta.ts:97) becomes a successor.

  Tests: one `job-plan-repo.test.ts` case per J0b row, each asserting one `job start` per machine (recording executor) and the declared steps; the coverage test in packages/cli/src/services/jobs/__tests__/job-plan-coverage.test.ts fails for any machine-plane command with no J0b plan and no section 24 exception; control: `repo list` keeps its output byte for byte.

  Owns: packages/cli/src/commands/repo-create-delete.ts, packages/cli/src/commands/repo-maintenance.ts, packages/cli/src/commands/repo-prune.ts, packages/cli/src/commands/repo-trim.ts, packages/cli/src/commands/repo-extended.ts, packages/cli/src/commands/repo-promote.ts, packages/cli/src/commands/repo-container.ts, packages/cli/src/commands/repo-delta.ts, packages/cli/src/commands/repo-batch-utils.ts, packages/cli/src/commands/repo-replicate.ts, packages/cli/src/commands/repo-canary.ts, packages/cli/src/commands/repo-gpu.ts, packages/cli/src/commands/repo-policy.ts, packages/cli/src/commands/repo-admin.ts, packages/cli/src/commands/repo-cat.ts, packages/cli/src/commands/repo-diff.ts, packages/cli/src/commands/repo-backup-list.ts, packages/cli/src/utils/repo-executor.ts, packages/cli/src/commands/__tests__/job-plan-repo.test.ts (new). Accept: `cd packages/cli && npx vitest run src/commands/__tests__/job-plan-repo.test.ts src/services/jobs` rc 0, and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.

- [ ] J17 [writer] Conversions, backup verbs outside J4. After J0b, J3b and J15. `backup run` becomes a `backup-unit` command-kind job, and its ad-hoc path folds into the same job (section 21). `backup list`, `browse`, `status`, `cancel` and `schedule` follow their J0b rows.

  Tests: `backup run` on a deployed unit makes one `job start --command backup-unit` exec and returns its ticket past the window, and no `systemctl start` runs on the client; the ad-hoc path makes one job; `backup schedule` keeps its unit content byte for byte; control: `backup status` output is unchanged.

  Owns: packages/cli/src/commands/backup-ops.ts, packages/cli/src/services/backup/backup-schedule-unit-generator.ts, packages/cli/src/commands/__tests__/job-plan-backup.test.ts (new). Accept: `cd packages/cli && npx vitest run src/commands/__tests__/job-plan-backup.test.ts` rc 0, and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.

- [ ] J18 [writer] Conversions, machine verbs. After J0b, J3b and J15. `machine setup` keeps the bootstrap upload outside the job, then runs one `setup` command-kind job, with the converge pass inside the job or as a successor, per J0b. `restart-services`, `prune`, `infra push`, `infra cert push`, `health`, `gpu list` and `status` follow their rows. The SSH legs of `provision` and `deprovision` become jobs, and the tofu legs stay local (section 24).

  Tests: `machine setup` makes one bootstrap upload, then one `job start --command setup`; `machine status` makes one `list-all` job; `provision` makes no job for its tofu leg and one for its setup leg; control: `machine setup` against a renet older than `--attach` still upgrades (bootstrap first) and then starts the job.

  Owns: packages/cli/src/commands/machine/register.ts, packages/cli/src/commands/machine/restart-services.ts, packages/cli/src/commands/machine/prune.ts, packages/cli/src/commands/machine/infra.ts, packages/cli/src/commands/machine/provision.ts, packages/cli/src/commands/machine/health.ts, packages/cli/src/commands/machine/gpu.ts, packages/cli/src/services/machine/machine-status.ts, packages/cli/src/commands/__tests__/job-plan-machine.test.ts (new). Accept: `cd packages/cli && npx vitest run src/commands/__tests__/job-plan-machine.test.ts` rc 0, and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.

- [ ] J19 [writer] Conversions, datastore and cluster verbs. After J0b, J3b and J15. Each datastore verb becomes one job. Each cluster verb becomes one job per member machine under one ticket group (section 14).

  Tests: `datastore resize` makes one job; `cluster create` on three fake machines makes three jobs under one group and runs its success step once after all three succeed; a failure on one member runs the failure step once; control: `datastore list` output unchanged.

  Owns: packages/cli/src/commands/datastore.ts, packages/cli/src/commands/cluster/**, packages/cli/src/services/cluster/**, packages/cli/src/commands/__tests__/job-plan-cluster.test.ts (new). Accept: `cd packages/cli && npx vitest run src/commands/__tests__/job-plan-cluster.test.ts` rc 0, and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.

- [ ] J20 [writer] Conversions, subscription and vscode serve verbs. After J0b, J3b and J15. `subscription status -m`, `subscription refresh`, `vscode serve status` and `vscode serve stop` each become one job.

  Tests: one job per command (recording executor); control: `subscription status` without `-m` (account-only) starts no job.

  Owns: packages/cli/src/commands/subscription-actions.ts, packages/cli/src/commands/vscode-serve.ts, packages/cli/src/commands/__tests__/job-plan-misc.test.ts (new). Accept: `cd packages/cli && npx vitest run src/commands/__tests__/job-plan-misc.test.ts` rc 0, and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.

- [ ] J6 [writer] Proxy serve and client. After J2, J3 and J5. Changes:
  - the dispatch returns at the terminal job's start (packages/cli/src/services/serve/command-dispatch.ts:389-405 loses `follow: true`);
  - the poll and cancel routes, the held re-attach route deleted, start and terminal audit events (Design 4);
  - proxy-client follows by polls with the Design 5 backoff, writes and updates the ticket (`via: proxy`), and loses its re-attach loop.

  Tests: an in-process serve with a fake machine shows `/v1/command` for `repo up` ending right after the job and result lines (the response closes before the fake job finishes); poll returns events after `sinceLine` with the status and honours `maxLines` and `more`; a poll for a machine outside the caller's policy is 403; the cancel route audits as destructive; exactly one terminal audit event across three polls of a finished job; the client's backoff sequence on empty polls is 2, 3, 4.5 ... 30 s within jitter; control: a non-detachable command (`repo list`) still streams to its result.

  Owns: packages/cli/src/services/serve/server.ts, packages/cli/src/services/serve/command-dispatch.ts, packages/cli/src/services/serve/__tests__/job-poll.test.ts (new), packages/cli/src/services/serve/__tests__/command-dispatch.test.ts, packages/cli/src/services/executor/proxy-client.ts, packages/cli/src/services/executor/__tests__/proxy-client-poll.test.ts (new). Accept: `cd packages/cli && npx vitest run src/services/serve src/services/executor/__tests__/proxy-client-poll.test.ts` rc 0, and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.
  Amended (third round): J6b replaces "ends right after the job line" with the 20 s attach window. The control changes too: `repo list` is now a job that finishes inside the window, so it returns directly.

- [ ] J6b [writer] Proxy attach window, start retry, steps and overlaps. After J2b, J3b, J6 and J15. Changes:
  - `/v1/command` attaches for `JOB_ATTACH_WINDOW_MS`, with a heartbeat every 10 s; it returns the result when the job finishes within the window, otherwise the job line and a running result (section 15);
  - the dispatch keeps the attach when its client disconnects, and runs the steps when the job finishes inside the window (section 16);
  - `requestId` is taken from the body and forwarded; the client retries a POST that dropped before the job line with the same id, up to 3 times (section 17);
  - the poll that observes a terminal state runs the steps on the executor through J15;
  - `overlaps` on the job line and the result, and BUSY as a structured refusal.

  Tests:
  - a fake job of 2 s returns its result in one request, with no job line and no poll;
  - a fake job of 40 s returns a running result at about 20 s, and polls finish it;
  - a client disconnect at 1 s of a 2 s job still runs its success step once (claim marker present);
  - a POST dropped before the job line and retried with the same id yields one fake job;
  - an overlap refusal arrives as `result` with code BUSY and a non-empty `overlaps`;
  - a quiet 25 s window carries at least two heartbeats;
  - control: a non-detachable exception (`repo sync status` refused through the proxy) is unchanged.

  Owns: packages/cli/src/services/serve/server.ts, packages/cli/src/services/serve/command-dispatch.ts, packages/cli/src/services/serve/__tests__/job-attach.test.ts (new), packages/cli/src/services/serve/__tests__/command-dispatch.test.ts, packages/cli/src/services/executor/proxy-client.ts, packages/cli/src/services/executor/proxy-command.ts, packages/cli/src/services/executor/__tests__/proxy-client-attach.test.ts (new). Accept: `cd packages/cli && npx vitest run src/services/serve src/services/executor/__tests__/proxy-client-attach.test.ts` rc 0, and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.

- [ ] J7 [writer] Web console: `useCommand` stops at the job line and follows by polls through a new account route that relays `/v1/jobs/:id/poll` to the org's executor with the same session and grant checks as the command relay (private/account/src/routes/console.ts:467). Same backoff as Design 5; leaving the page stops polling and never cancels.

  Tests: the hook renders events from three polls and the final outcome from the terminal status; unmount stops the timer; the relay refuses a request without a console session; control: a non-detachable command renders from the stream as today.

  Owns: private/account/web/src/hooks/useCommand.ts, private/account/web/src/hooks/__tests__/useCommand-poll.test.ts (new), private/account/web/src/api/console.ts, private/account/src/routes/console.ts (the job poll relay only), private/account (the gitlink bump only). Accept: `cd private/account && npx vitest run web/src/hooks src/routes` rc 0, and `cd private/account && npx tsc --noEmit` rc 0.
  Amended (third round): follows J6b. The hook renders a result that arrives inside the window without polling, renders `overlaps` as a warning with the attach command, and sends a `requestId`. The test adds one case per behaviour.

- [ ] J8 [writer] MCP (Design 12). After J2, J3 and J5. Covered tools append `--background` and describe the job; `job_status` and `job_logs` take the machine optionally.

  Tests: each covered tool's argv carries `--background`; the parsed envelope of a fake `repo up` returns within the read timeout with a job id; `job_status` built with only an id omits `-m`; the coverage test lists every covered verb with `--background`; control: `repo list` carries no `--background`.

  Owns: packages/cli/src/commands/mcp/tool-factory.ts, packages/cli/src/commands/mcp/__tests__/**, packages/cli/src/config/command-metadata.ts (the mcp fields of the covered verbs and the job tools only). Accept: `cd packages/cli && npx vitest run src/commands/mcp` rc 0.
  Amended (third round): J8b replaces `--background` with the 20 s attach window for every machine tool.

- [ ] J8b [writer] MCP attach window and overlaps. After J6b and J8. Each machine-plane tool runs the child `rdc` with the 20 s attach window (an internal flag or environment variable that the child reads into `attachWindowMs`), and returns either the command's result or the ticket envelope with `next: "job_status"`. `overlaps` is a structured field of the tool result, and a BUSY refusal is a tool error carrying `overlaps`. Tool descriptions say "returns the result, or a job id when the run outlasts about 20 s".

  Tests: a fake 2 s `repo create` returns its result; a fake 60 s `backup snapshot` returns a job id in under 30 s; the parsed result of an overlap carries `overlaps[0].attach`; the coverage test lists every machine-plane tool with the window; control: an `other`-plane tool (`backup usage`) carries no window.

  Owns: packages/cli/src/commands/mcp/tool-factory.ts, packages/cli/src/commands/mcp/executor.ts, packages/cli/src/commands/mcp/__tests__/**, packages/cli/src/config/command-metadata.ts (the mcp fields of the converted verbs and the job tools only). Accept: `cd packages/cli && npx vitest run src/commands/mcp` rc 0.

- [ ] J21 [writer] Running jobs in `machine status` and `repo status`, and the overlap warning text. After J1c and J3b. `machine status` renders the `jobs` section of `renet list all` (id, verb, repo, started-at, origin, state, and the attach command). `repo status` shows the jobs on its repo GUID. The en keys cover the warning, refusal and status lines.

  Tests: a fake `list all` with one live job renders one row with the attach command; `-o json` carries `jobs`; `repo status` filters by GUID; a job from another config shows its GUID and origin; control: an empty `jobs` section prints nothing extra.

  Owns: packages/cli/src/commands/machine/status.ts (the running-jobs section only), packages/cli/src/commands/repo.ts (the status action only), packages/cli/src/commands/__tests__/job-status-surfaces.test.ts (new), packages/cli/src/i18n/locales/en/cli.json. Accept: `cd packages/cli && npx vitest run src/commands/__tests__/job-status-surfaces.test.ts` rc 0, and `npm run check:ci-i18n-cli-key-usage` rc 0.

- [ ] J22 [writer] Remove each BACKGROUND_UNSAFE entry only when its verb's job and ticket steps land (section 25). One commit per verb, after that verb's conversion box (J4 for all ten). Each commit adds the verb to the converted registry in packages/cli/src/services/jobs/plans.ts.

  Tests: the invariant test holds every detachable verb in exactly one of `BACKGROUND_UNSAFE` or the converted registry; for each removed verb, `-b` returns the envelope with its steps recorded in the spool and on the ticket (recording executor); the existing per-key test (packages/cli/src/services/executor/__tests__/proxy-command.test.ts:131-133) keeps passing for the remaining keys; control: a planted verb in both sets fails the invariant.

  Owns: packages/cli/src/services/executor/proxy-command.ts, packages/cli/src/services/executor/__tests__/proxy-command.test.ts, packages/cli/src/services/jobs/plans.ts. Accept: `cd packages/cli && npx vitest run src/services/executor/__tests__/proxy-command.test.ts src/services/jobs` rc 0.

- [ ] J9 [writer] Docs and i18n in 13 locales. After J3, J5, J6 and J8. The new en keys are naturalized into the 12 derived locales (docs/i18n/CONVENTIONS.md); proxy-and-executor.md gains a section on jobs, tickets and polling in English and is re-translated as a delta; cli-application.md is regenerated with `npm run generate:cli-docs -w @rediacc/www` by the lead.

  Owns: packages/cli/src/i18n/locales/*/cli.json (non-en), packages/www/src/content/docs/*/proxy-and-executor.md, packages/www/src/content/docs/*/cli-application.md (regenerated only). Accept: `npm run check:i18n` rc 0.
  Amended (third round): follows every code box. The docs section also covers the attach window, the overlap warnings and refusals, the ticket steps and when they run while the client is away, the exceptions list, and spool retention.

- [x] J10 [lead] Durable Object: verify that no code change is needed. With every detachable run returning after start, `inFlight` falls to zero between polls and the alarm's idle branch applies unchanged (workers/proxy/src/org-executor.ts:327-346). Record the reading here; if L1 shows a poll that holds the lease past its body, the fix is filed under PLAN-executor-durable-object-policy's exclusive Owns, not here.
  Owns: agent/plans/PLAN-detached-jobs.md. Accept: `npm run check:ci-proxy-cost-guard` rc 0.
  Amended (third round): the reading also covers the 20 s attach window, during which `inFlight` is 1 and the alarm renews as for any request.
    (live record 2026-10-29, d778be9d) J10 reading: workers/proxy/src/org-executor.ts:332 renews only while inFlight > 0, so a request that ends after its 20 s attach window (or with the result) lets inFlight fall to zero between polls and the idle branch applies unchanged; during the window inFlight is 1, as for any request. No change under workers/proxy/src. `npm run check:ci-proxy-cost-guard` rc 0 (16 containers at max_instances <= 25, sleepAfter <= 120 s, worst case 1967.35 USD a month under the 2100 limit).
    (ticked) 2026-10-29T12:08:29Z by d778be9d: commit:ca9cf2625
    (review note 2026-10-29, 9f92c43e) The tick reading cites workers/proxy/src/org-executor.ts:332 only. The condition on L1 (no poll holding the lease past its body) is not evidenced by this tick and stays owed to L1; until L1 runs, the no-change verdict is the code reading alone.

- [ ] J11 [lead] The VM proof for the renet change: `npm run vm:check -- --changed` VERIFIED on the tree carrying J1 and J3, as the push guard requires for the renet trigger paths.
  Owns: agent/plans/PLAN-detached-jobs.md. Accept: `npm run vm:check -- --changed` rc 0 with a VERIFIED receipt.
  Amended (third round): the tree carries J1b, J1c and J3b as well.

- [x] J12 [writer] Cost measurement module: `.ci/rediacc_ci/ops/proxy_job_cost.py --script <name> --from <ISO> --to <ISO>` prints Durable Object requests and wall time (sum, p50, p99) and container active seconds for one script over a window, importing the GraphQL transport from cf_usage_report rather than copying it. The dataset and field names (`durableObjectsInvocationsAdaptiveGroups` with wall time, `containersMetricsAdaptiveGroups`) are hypotheses to confirm against the live API first (CLAUDE.md rule 3).
    (ticked) 2026-10-29T11:26:24Z by d778be9d: commit:e7b2d599e

  Tests: a recorded GraphQL response yields the expected sums; an empty response exits 2, never 0; a GraphQL error exits 2; control: a response with one row prints that row.

  Owns: .ci/rediacc_ci/ops/proxy_job_cost.py (new), .ci/rediacc_ci/tests/test_ops_proxy_job_cost.py (new). Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ops_proxy_job_cost.py` rc 0.

- [x] J23 [writer] Latency measurement script: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.job_latency --rdc <path> --config <name> --runs 20 -- <rdc args>` runs one command N times and prints wall time p50, p95 and max, plus the `rediacc.job.start_latency_ms` attribute when the run prints it under `--debug`. It also compares two result files (`--compare before.json after.json`) and prints the deltas.
    (ticked) 2026-10-29T11:26:59Z by d778be9d: commit:e7b2d599e

  Tests: a fake rdc with recorded durations yields the expected percentiles; a non-zero rc in any run exits 2; `--compare` prints the delta; control: one run prints one sample.

  Owns: .ci/rediacc_ci/ops/job_latency.py (new), .ci/rediacc_ci/tests/test_ops_job_latency.py (new). Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ops_job_latency.py` rc 0.

- [ ] L0 [live] Baseline before any bench deploy of this branch: one `rdc --proxy <bench proxy origin> repo up <fork>` and one `backup verify <fork>` through the bench proxy on the current protocol, then the Durable Object request wall time, request count and container seconds for `rediacc-proxy-bench` over that window, read with the J12 module (or by hand with the same GraphQL query if J12 has not landed, recorded verbatim).
  Owns: agent/plans/PLAN-detached-jobs.md. Accept: the run's timings and the three metrics recorded under "Live records" with the UTC window, and both commands rc 0.

- [ ] L3a [live] Latency baseline before any deploy of this branch, on the main CLI and renet: J23 with 20 runs each of `repo list -m <machine>`, `repo status <fork>`, `machine status <machine>` and `repo create`/`repo delete` of a scratch repo. Each runs on hostinger direct through `--config eu-bench`, and each through the bench proxy.
  Owns: agent/plans/PLAN-detached-jobs.md. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.job_latency --runs 20 ...` rc 0 for each command and path, with p50, p95 and max recorded under "Live records" with the UTC window.

- [ ] L1 [live] Bench through the proxy, after every code box. Deploy the branch to bench (deploy_bench, then `deploy_proxy --target bench`), provision the branch renet to hostinger (ASK first, as LP-hostinger says), then on a fork through `--config eu-bench` and the bench proxy:
  1. `repo up <fork>`: the `/v1/command` response ends within seconds of the job line, polls follow to success, rc 0;
  2. `-b backup snapshot <fork>`: returns a ticket at once; the laptop process exits; `rdc job list` shows it; `rdc job wait <id>` finishes it with rc 0;
  3. start `backup verify <fork>` followed, kill the client mid-run, run any `rdc` command after the job ends: the finished notice prints once;
  4. the MCP `backup_snapshot` tool returns a job id in under 30 s and `job_status` reaches `succeeded`;
  5. a machine whose renet lacks `--request-id` (a pinned older renet on a dev VM) refuses with the upgrade text and rc 1.

  Owns: agent/plans/PLAN-detached-jobs.md. Accept: each step's command, rc and timing recorded under "Live records"; steps 1-4 rc 0 and step 5 rc 1.
  Amended (third round): in step 1 the response ends at the 20 s window (or with the result, if the up finishes within it). L5 adds the hybrid, overlap and drop steps.

- [ ] L5 [live] Unstable-link drill, after every code box, on the same deploy as L1:
  1. `repo create` of a scratch repo through the proxy returns its result in one request, with no poll in the client's debug log;
  2. `repo up <fork>` through the proxy: the client's network is cut (the client process is suspended with SIGSTOP) for 60 s at second 5 and resumed; the run finishes through polls, `postRepoUpTasks` ran once (one claim marker in the spool), and `rdc job list -m` shows one job for the request id;
  3. `repo up <fork>` direct over SSH with the client suspended for 3 minutes: it exits `FOLLOW_LOST` with a ticket; `rdc job wait <id>` finishes it, and the steps run once;
  4. a second `repo up <fork>` from another config while the first runs refuses with rc 15 and names the first job's id, origin and attach command; `machine status` lists the running job;
  5. a `backup snapshot` started while a `repo status` loop runs shows the warning on each `repo status` and finishes;
  6. a forced retry of the same start (the J3b test seam enabled through an environment flag on the dev build) yields one job on the machine.

  Owns: agent/plans/PLAN-detached-jobs.md. Accept: each step's command, rc, timing and the job count recorded under "Live records"; steps 1, 2, 3, 5 and 6 rc 0 with one job per request id; step 4 rc 15.

- [x] J24 [lead] Settle the third-round trade-offs the operator has not ruled on (the attach window if L3b breaches its 10 % rule, the `reconcileBackupSchedules` nudge, the origin fields): record each answer under "Operator rulings, fourth round".
  Owns: agent/plans/PLAN-detached-jobs.md. Accept: `python3 .ci/scripts/quality/check_plan_deps.py` rc 0 and each answer quoted with its date.
    (ticked) 2026-10-29T12:08:32Z by d778be9d: commit:afcb5c297


- [ ] L2 [live] Cost after: the L0 commands again on the deployed branch, and the same three metrics over the new window with `PYTHONPATH=.ci python3 -m rediacc_ci.ops.proxy_job_cost --script rediacc-proxy-bench --from <ISO> --to <ISO>`. The expected result is Durable Object wall time per run falling from the run length to the sum of poll durations; the measured before and after go into "Live records" with the ratio.
  Owns: agent/plans/PLAN-detached-jobs.md. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.proxy_job_cost --script rediacc-proxy-bench --from <ISO> --to <ISO>` rc 0 for both windows, with both readings recorded.

- [ ] L3b [live] Latency after: the L3a commands again on the deployed branch and the branch renet, same paths and run counts, then `job_latency --compare`. The added p50 and p95 per command are checked against the section 23 budget (p50 plus 500 ms, p95 plus 1 s), and the share of short commands over 20 s against the section 15 rule (10 %).
  Owns: agent/plans/PLAN-detached-jobs.md. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.job_latency --compare <before> <after>` rc 0, with the deltas recorded under "Live records". A breach of either budget is recorded and asked under J24, not silently accepted.

- [ ] L4 [live] Spool growth and cleanup on hostinger, after J1c is provisioned: 300 `repo status <fork>` runs, then the spool directory count, `du -sh /var/lib/rediacc/jobs` and `systemctl list-units 'rediacc-job-*' --all --no-legend | wc -l` read over `term connect -c`. The read is repeated after `job gc --older-than 1h` and after one hour of idle followed by one start (the opportunistic GC).
  Owns: agent/plans/PLAN-detached-jobs.md. Accept: the three readings at each point recorded under "Live records"; after the GC pass the loaded-unit count equals the live-job count and no terminal `read` job older than 1 h remains.

- [ ] LP-bench [live] Fresh bench receipt (PLAN-tested-on-bench ruling 3): deploy this branch to bench with deploy_bench, then record and tick through worklist.py --live-proof.
  - Accept: `live-proof bench account-smoke`
- [ ] LP-hostinger [live] Fresh hostinger receipt through --config eu-bench (PLAN-tested-on-bench ruling 3), after a VERIFIED npm run vm:check -- --changed on the same tree; ASK the operator first, because provisioning a branch renet restarts the router and daemons.
  - Accept: `live-proof hostinger renet-live`

## Open questions for the operator

1. **The poll cap and the container's sleep.** Settled in the second round: keep 2-30 s, and let L2 measure.
2. **`backup run`.** Settled by J0 and section 21: it becomes a `backup-unit` command-kind job.
3. **The attach window.** 20 s by default (section 15). It returns to the operator if L3b finds more than 10 % of short commands over it.
4. **A nudge for `reconcileBackupSchedules` while the client is away** (section 18). The default is to accept the delay and make it visible. The alternatives are listed under the trade-offs.
5. **The origin fields** (section 19): which identity other machine admins may see.

## Risks

1. **A start whose answer is lost.** A proxy response dropped after `job start`, or an MCP child killed mid-start, would otherwise leave a running job nobody knows. The request id and the `O_EXCL` index (section 17) make the retry find it. A client that never retries still finds it under `rdc job list -m <machine>`, and the overlap check stops a manual rerun of an exclusive verb.
2. **Post-job tails that silently stop running.** Section 18 turns every tail into a registered step with a trigger, and J0b's table is the inventory. The J16 coverage test fails for any machine-plane command with no plan.
3. **A poll per 2-30 s opens an SSH exec each time.** The connection lease reuses a live connection inside a warm container; a cold container pays one SSH handshake per poll. L1 records the poll latency.
4. **A hung job under a 24 h ceiling holds its overlap lock.** The refusal names `rdc job cancel`. Section 20 keeps 10 minutes for every function outside the two-class rule.
5. **Spool and unit growth.** Every machine command now leaves a spool entry and a loaded unit. Section 22 bounds both, and L4 measures them.
6. **Latency on short commands.** Section 23 budgets it, L3a and L3b measure it, and a breach goes to the operator.
7. **Steps that never run because the client never returns.** Section 18's visibility (`rdc job list`, the notice) and the 7-day spool hold keep them recoverable. A config that is never used again leaves its steps undone. The trade-offs list the nudge.
8. **Overlapping owners.** Several live plans own packages/cli/src/services/serve/** and packages/cli/src/services/executor/** broadly, and PLAN-backup-local-image owns parts of the files J17, J18 and J21 touch (Concurrency line). Their open boxes are live, ops or section-disjoint, so the conflict is in the concurrency guard, not in edits; a refused spawn is queued.
9. **Origin data visible to other machine admins.** `status.json` is root-only (0700 spool, private/renet/pkg/jobs/jobs.go:86-93), but every root user on the machine can read who started what. Section 19 limits the fields, and J24 asks the operator.

## Out of scope

- Any change under workers/proxy/src (J10 verifies, PLAN-executor-durable-object-policy owns it).
- A cancel button and a jobs page in the web console.
- An override flag that forces a start past an overlap refusal.
- Moving the scheduler's timer-fired backup units into the job spool. They appear in the overlap check as active units only.
- The section 24 exceptions.

## Live records

(empty until L0 and L3a)

## Operator rulings, second round (2026-10-29)

- Poll cap (ASKED 2026-10-29, "Keep 2-30 s, measure first (Recommended)"): the 2-30 s backoff ships as ruled; L2 measures Durable Object and container time before any change to the cap.
- `backup run` stays outside the covered verbs (the plan's default for its second question, not an operator answer: no ASKED record exists for it); J0 confirms it never calls `renet execute`. Superseded by the third round: every machine command is a job, and section 21 makes `backup run` one.

## Operator rulings, third round (2026-10-29)

The operator's amendment of 2026-10-29, which replaces ruling 1, quoted:

> Every rdc command that touches a remote machine runs as a machine job, not only the long verbs. The client stays attached by default. The reason: the rdc client can be on an unstable connection, for example on a train. A dropped connection must never kill a command, leave it half-done, or run it twice.
>
> 1. Hybrid attach. Job start, then wait inside the same request for a short window (about 20 s). If the job finishes within the window, return the result directly: one round trip, through the proxy too. Otherwise, return the ticket and follow with short polls, backing off from 2 s to 30 s (already ruled). No hand-kept list of long versus short verbs; duration decides.
> 2. Reattach. On a drop, reattach from the last line received. If that fails, keep the ticket in the per-config ticket store (ruling 3), so `rdc job wait <id>` picks it up.
> 3. No double execution. A start retried after a drop must not run the job twice. The request id on job start (box J1) applies to every command, with a test.
> 4. One machine job per command. Extend the J0 audit to every machine-plane command in the contract. Machine-side work (probes, extra renet calls) becomes part of the single job or a recorded successor job. repo migrate needs a combined renet job (`repository_migrate`, as J0 recommends).
> 5. Client-side steps stay in the CLI: postRepoUpTasks (DNS, cert sync, service URLs), reconcileBackupSchedules, recordPushBase, recordBackupRun, config registration and rollback, and identity refresh. Their behaviour is unchanged. Only their trigger changes: they run once the job is seen finished, wherever that happens (inside the in-request wait, after a reattach, on `rdc job wait <id>`, or on the next rdc run through the finished-while-away notice). Each runs exactly once per job, recorded on the ticket. A success step runs only on success; a failure step (rollback) runs only on failure.
> 6. Exceptions, each listed with its reason: interactive (term connect, repo tunnel, vscode, interactive exec); client-side transfers that rely on rsync's own resume (repo sync, and the planned backup download/upload); config-plane and account-only commands that never touch a machine.
> 7. Costs to measure and bound: the extra latency per short command (systemd unit start and spool write), measured before and after on bench; spool growth on the machine, with its retention and cleanup.
> 8. Rulings unchanged: the proxy returns the ticket and the client polls (ruling 2); the ticket store (ruling 3); MCP returns the ticket (ruling 4); the 2-30 s poll cap, measured first in L2.
> 9. Keep in force the current `-b` refusal of unsafe verbs (BACKGROUND_UNSAFE) until each verb is one job with its client-side steps on the ticket.

The operator's addition of the same day, quoted: "maybe we can also show some warnings if there is already an ongoing background job since the users may not know what's happening in the background. i.e. started by another user. The rdc/renet may suggest/hint 'run xyz to see/attach' etc." Section 19, J1b and J21 carry it.

## J0 verb audit (2026-10-29, lead session d778be9d)

Legend: **FG** is a foreground call whose answer the verb needs. **JOB** is a call in `JOB_FUNCTIONS` (`packages/cli/src/services/executor/renet-command.ts`; not yet added, the plan's J3 adds it). **SSH/HTTP** is a non-renet step: SFTP or HTTP in the CLI process, not a machine call through the executor.

| Verb | 1. CLI entry | 2. Machine calls in order | 3. Final long job | 4. Post-job tail (output needed?) | 5. Tail under the design | 6. `-b` today |
|---|---|---|---|---|---|---|
| **repo up** | `packages/cli/src/commands/repo.ts:152` (`.command('up')`), body `handleSingleRepoUp` at `packages/cli/src/commands/repo.ts:45`. `--all` goes to `handleUpAll` at `packages/cli/src/commands/repo-batch-utils.ts:287`. | (a) `resolveRepoRef` default verifier runs `repository_list` with `captureOutput` (`packages/cli/src/utils/repo-target.ts:35-45`, `packages/cli/src/services/repo/repo-mount-check.ts:55-60`). (b) `deployRepoKeyIfNeeded` over SSH/HTTP (`packages/cli/src/commands/repo.ts:100`). (c) `repository_up` through `executeRepoFunction` (`packages/cli/src/commands/repo.ts:102`, `packages/cli/src/utils/repo-executor.ts:88`). `ensureRepositoryNetworkId` may add a `network_used` probe when it allocates (`packages/cli/src/services/config/network-id-discovery.ts:69`). | `repository_up` (`packages/cli/src/commands/repo.ts:102`) | `postRepoUpTasks` at `packages/cli/src/commands/repo.ts:111`: DNS over HTTP, cert sync over SFTP, and service URLs from `fetchMachineStatus`. All are SSH/HTTP, not renet execute. The service-URL output is printed, not consumed. **It runs even when `repository_up` failed**, because `executeRepoFunction` returns the result and does not throw. | **Local step run when success is seen** (the ticket finalizer). DNS and cert are idempotent. Gate it on success, which fixes the unconditional run. | **Misbehaves.** The probe `repository_list` becomes a detached job (`packages/cli/src/services/executor/executor-factory.ts:83`). Its stdout is empty, so `probeRepoPresent` returns undefined and fails open, so the step-5 check silently disappears. `postRepoUpTasks` then runs at job start, against containers that are not up, and falls back to the URL pattern. |
| **repo fork** | `packages/cli/src/commands/repo-fork.ts:616` (`.command('fork')`), action at `packages/cli/src/commands/repo-fork.ts:640-660`. Also reached from `repo checkout` and `repo commit` through `handleForkAction` (`packages/cli/src/commands/repo-branching.ts:175`). | (a) `resolveRepoRef` default verifier, `repository_list` (`packages/cli/src/commands/repo-fork.ts:645`). (b) `ensureRecordedNetworkId`, which may issue `network_used` (`packages/cli/src/commands/repo-fork.ts:646`). (c) `deployRepoKeyIfNeeded` (`packages/cli/src/commands/repo-fork.ts:496`). (d) `repository_fork`, compound with `up: true` when `--up` and not `--checkpoint` (`packages/cli/src/commands/repo-fork.ts:500`, `packages/cli/src/commands/repo-fork.ts:277-295`). (e) Legacy second leg `repository_up` when `--checkpoint`, or when the remote renet ignored `--up` (`packages/cli/src/commands/repo-fork.ts:331`, called at `packages/cli/src/commands/repo-fork.ts:517`). (f) A network-id retry `repository_up` (`packages/cli/src/commands/repo-fork.ts:462`). | `repository_fork` (compound with up). The legacy `repository_up` is the final job on the checkpoint path. | (1) Identity refresh `localExecutorService.refreshIdentityFor('repository_fork', …)`, an SSH license call, started at `packages/cli/src/commands/repo-fork.ts:512` (`packages/cli/src/commands/repo-fork.ts:321`). The output is not needed and the step is warn-only. (2) `postRepoUpTasks` at `packages/cli/src/commands/repo-fork.ts:520`. (3) `reconcileBackupSchedules(machine)` at `packages/cli/src/commands/repo-fork.ts:537`, an SSH step that pushes units. (4) The legacy `up` leg. (5) Rollback on failure: `removeRepository` plus key removal (`packages/cli/src/commands/repo-fork.ts:446-452`). | Compound up: **folded into renet**. Keep it as the only path and delete the legacy leg (`packages/cli/src/commands/repo-fork.ts:515-518`), but `--checkpoint` still needs a renet compound or successor. Identity refresh, `postRepoUpTasks` and `reconcileBackupSchedules`: **finalizer on success**. The failure rollback needs a **finalizer on failure**, keyed on the `cow_reflink`/`cow_clone` step, which is not in the plan. | **Misbehaves.** `startIdentityRefresh` runs right after the detached start (`packages/cli/src/commands/repo-fork.ts:512`), before the fork exists. The legacy up leg runs concurrently with the fork job and would fail. `forkCreated` is false because no steps arrive. `reconcileBackupSchedules` runs early. |
| **repo push** | `packages/cli/src/commands/repo-backup.ts:393` (`.command('push')`), body `pushRepo` at `packages/cli/src/commands/repo-backup.ts:256`. | (a) `resolveRepoRef` default verifier, `repository_list`. (b) Optional `autoProvisionTarget` (`packages/cli/src/commands/repo-backup.ts:116`). (c) `deployRepoKeyIfNeeded` on the target. (d) `backup_push` through `executeFunction` (`packages/cli/src/commands/repo-backup.ts:283`, helper at `packages/cli/src/commands/repo-backup.ts:46-80`). | `backup_push` | (1) `reportPushStats`, which needs stdout (`packages/cli/src/commands/repo-backup.ts:285`). (2) `finalizePush` (`packages/cli/src/commands/repo-backup.ts:289`, `packages/cli/src/commands/repo-delta.ts:73`): `recordPushBase`, a local config write that is needed for the next delta, and for an immutable repo `repository_commit_meta` on the **target** (`packages/cli/src/commands/repo-delta.ts:97`), a short machine call after the job. Best-effort. (3) `postPushDeploy` is exported (`packages/cli/src/commands/repo-backup.ts:162`) but not called by `push`. | Stats: the finalizer prints from the replayed output. `recordPushBase`: **finalizer**. `repository_commit_meta` is a machine call after the terminal job, so it is a bug under rule 3. Make it a **successor on the ticket**, or fold it into `backup_push` when the object is immutable. | **Misbehaves.** The result is `ok:true` at start. `recordPushBase` then records a `verifiedBase` for a push that has not finished, so the next push deltas against a base that may not exist. `repository_commit_meta` is also detached and races the push. |
| **repo pull** | `packages/cli/src/commands/repo-backup.ts:423` (`.command('pull')`), body `pullRepo` at `packages/cli/src/commands/repo-backup.ts:348`. | (a) `resolveRepoRef` default verifier. (b) `deployRepoKeyIfNeeded`. (c) `backup_pull` (`packages/cli/src/commands/repo-backup.ts:378`). (d) With `--up`, `postPullDeploy`: `deployRepoKeyIfNeeded`, then `repository_up` with `mount: true` (`packages/cli/src/commands/repo-backup.ts:381`, `packages/cli/src/commands/repo-backup.ts:328`). | `backup_pull`, or the `--up` `repository_up` when `--up` | The `--up` leg is a second job whose input is the first job's success. No output is needed. `postPullDeploy` also returns early without running the `up` if the subscription token is not ready (`packages/cli/src/commands/repo-backup.ts:316-322`). | **Successor recorded on the ticket**: `then: repository_up {mount:true}`. | **Misbehaves.** `--up` fires `repository_up` while the pull is still running. |
| **repo down** | `packages/cli/src/commands/repo.ts:204` (`.command('down')`), `executeRepoFunction` at `packages/cli/src/commands/repo.ts:261`. `--all` goes to `handleDownAll` at `packages/cli/src/commands/repo-batch-utils.ts:328`. | (a) `resolveRepoRef` (likely `absentOk`, not read in this audit), so probably the default `repository_list` probe. (b) `repository_down`. | `repository_down` | None. | None. | The probe leak as in `repo up`. It starts a stray job but is otherwise correct, and is the cleanest of the verbs. |
| **repo migrate** | `packages/cli/src/commands/repo-migrate.ts:40` (`.command('migrate')`), `migrateRepo` at `packages/cli/src/commands/repo-migrate.ts:454`. | (1) `resolveRepoRef`, a `repository_list` probe. (2) Optional provision (`packages/cli/src/commands/repo-migrate.ts:493`). (3) `assertNotMountedOnTarget`, `repository_list` with capture (`packages/cli/src/commands/repo-migrate.ts:500`, `:154`). (4) Phase 1: `deployRepoKeyIfNeeded`, then `backup_push` (`packages/cli/src/commands/repo-migrate.ts:106-120`, `:143`). (5) Phase 2: `repository_down`, then `backup_push` delta (or a checkpoint push), then `repository_down {unmount}` (`packages/cli/src/commands/repo-migrate.ts:265-285`). (6) `setRepositoryPlacement(name, {machine:to})` (`packages/cli/src/commands/repo-migrate.ts:432`). (7) Phase 3: `deployRepoKeyIfNeeded`, `repository_up` on the target (`packages/cli/src/commands/repo-migrate.ts:308`). (8) `postRepoUpTasks` for DNS (`packages/cli/src/commands/repo-migrate.ts:316`). (9) `repository_delete` on the source (`packages/cli/src/commands/repo-migrate.ts:451`, `:359`). (10) `reconcileBackupSchedules` on `to` and `from` (`packages/cli/src/commands/repo-migrate.ts:538-539`). | There are five jobs in sequence, and the final one is `repository_up` on the target. | The **source delete** (a `repository_delete` machine call; failure only warns, `packages/cli/src/commands/repo-migrate.ts:366`), `postRepoUpTasks`, `reconcileBackupSchedules` ×2, and the placement rewrite, which comes **before** phase 3 on purpose (`packages/cli/src/commands/repo-migrate.ts:419-433`). Output is needed only for the stats (`extractPushResult`). | There is no compound form in renet. Recommended: **add one renet compound job `repository_migrate`** (push, down, delta push, down-unmount, up on target, delete unless `--keep-source`) that emits a `cutover_complete` marker. The **placement rewrite** is a finalizer on the marker, so it must fire even if the up fails afterwards (R1). `postRepoUpTasks` and `reconcileBackupSchedules` are finalizers on success. Without a compound, the five-job chain cannot be driven by "return at the terminal start", because the client has to follow every earlier job to completion. | **Catastrophic.** Every leg returns at once. `repository_down` stops the source, the delta push and the unmount start while phase 1 is still copying, placement is rewritten, `repository_up` on the target starts mid-transfer, and `repository_delete` of the source runs while the push is still reading it. `assertNotMountedOnTarget` silently passes because stdout is empty (`packages/cli/src/commands/repo-migrate.ts:160`). |
| **backup snapshot** | `packages/cli/src/commands/backup-storage.ts:499` (`.command('snapshot')`), `executeRepoFunction` at `packages/cli/src/commands/backup-storage.ts:529`. | (a) `resolveRepoRef` probe. (b) `backup_snapshot`. | `backup_snapshot` | `recordBackupRun(repoKey, {kind:'snapshot', status})` (`packages/cli/src/commands/backup-storage.ts:558`) uses the exit code; the quota-refused code 16 needs `result.exitCode` (`packages/cli/src/commands/backup-storage.ts:542`, `:565-568`). | **Finalizer**, which must receive the exit code. | **Misbehaves.** It records `status: 'stored'` at job start, an unverified lie in the run history. |
| **backup restore** | `packages/cli/src/commands/backup.ts:143` (`.command('restore')`), action from `packages/cli/src/commands/backup.ts:160`. There are three routes: path (`packages/cli/src/commands/backup.ts:163`), chunk (`backup_restore`, `packages/cli/src/commands/backup.ts:213`), or pull (`backup_pull`, `packages/cli/src/commands/backup.ts:224`). | Account HTTP: `lineageHasSnapshots` (`packages/cli/src/commands/backup.ts:177`) and `resolveSnapshotAt`. A config write registers the target **before** the job. Chunk route with a time in `--at`: `backup_verify` on the **source** with capture (`readSourceAnchor`, `packages/cli/src/commands/backup.ts:493`), then `backup_restore` (`packages/cli/src/commands/backup.ts:553`) with `captureOutput`. Pull route: `backup_pull` (`packages/cli/src/commands/backup.ts:365`). Then `reconcileBackupSchedules(targetMachine)` (`packages/cli/src/commands/backup.ts:237`), then `--up`: `repository_up` (`packages/cli/src/commands/backup.ts:240`, `:634`). | `backup_restore` or `backup_pull` | `recordBackupRun`; on failure `removeRepository` (`packages/cli/src/commands/backup.ts:344`, `:578`). `reportRestoreStats` needs the stdout. `reconcileBackupSchedules`. `--up` runs `repository_up` with health params, which is a second job. | The failure rollback and `recordBackupRun` are a **finalizer (on failure and on success)**. Stats are printed by the finalizer. `reconcileBackupSchedules` is a **finalizer**. The `--up` is a **successor** `repository_up {mount, health_*}`. The `backup_verify` anchor probe stays **followed to completion** in the same process (design 3). | **Misbehaves.** `readSourceAnchor` is detached, so its stdout is empty and the anchor is undefined. A time in `--at` then throws `streamUnknown` (`packages/cli/src/commands/backup.ts:451-455`). With a snapshot id the restore returns `ok` at start, `recordBackupRun` writes `ok`, and `--up` races the restore. |
| **backup restore-path** | There is no separate contract verb. It is `backup restore --at --path`, routed by `packages/cli/src/commands/backup.ts:163` to `restorePathRoute` (`packages/cli/src/commands/backup.ts:265`), then `runRestorePath` (`packages/cli/src/commands/backup-restore-path.ts:140`). | `backup_verify` for the anchor when `--at` is a time (`streamScopeFor`, FG), then `backup_restore_path` with capture (`packages/cli/src/commands/backup-restore-path.ts:160`). | `backup_restore_path` | The output is **needed**: a `parseRecord` record is printed (`packages/cli/src/commands/backup-restore-path.ts:187`), and exit code 18 (`RENET_NO_LISTING_EXIT`) has a custom message. No machine or config step follows. | Print the record from the replayed output when success is seen. Exit 18 is a distinct code that the ticket must keep. | **Misbehaves.** `parseRecord` on empty stdout throws `restore-path returned no record` (`packages/cli/src/commands/backup-restore-path.ts:187-190`). The `-b` run also fails if the time anchor is needed. |
| **backup verify** | `packages/cli/src/commands/backup-storage.ts:365` (`.command('verify')`), `executeRepoFunction` at `packages/cli/src/commands/backup-storage.ts:389`. `--store` is account-side only and never calls a machine. | (a) `resolveRepoRef` probe. (b) `backup_verify` with `captureOutput`. | `backup_verify` | The verdict is **needed** (`parseVerifyVerdict`, printed at `packages/cli/src/commands/backup-storage.ts:410`), plus `recordBackupRun` for `verified` or `mismatch`. | Print the verdict and record the run in the finalizer. | **Misbehaves badly.** With empty stdout the verdict falls back to `{status:'verified', level}` (`packages/cli/src/commands/backup-storage.ts:410`), and `recordBackupRun(... 'verified')` is written without anything having been verified. |

### Confirm or refute: `backup run` and `renet execute`

**Confirmed that it never calls `renet execute`; refuted that it "returns at the unit start".** `packages/cli/src/commands/backup-ops.ts` has no `getExecutor` or `execute(` call. The only machine calls are `sftp.execStreaming` of systemd commands.

- A **deployed unit** runs `sudo systemctl start <unit>` (`packages/cli/src/commands/backup-ops.ts:30`). The unit is `Type=oneshot` with `TimeoutStartSec=infinity` (`packages/cli/src/services/backup/backup-schedule-unit-generator.ts:265-268`), and there is no `--no-block`. So `systemctl start` blocks until the whole backup finishes. The SSH session is held for the whole run, and Ctrl-C or a dropped session leaves the unit running but the client reports nothing useful. So for deployed units the work outlives the client, but the client does **not** return at the start.
- The **ad-hoc path** uses `sudo systemd-run --unit … --remain-after-exit` without `--wait` (`packages/cli/src/services/backup/backup-schedule-unit-generator.ts:217`). It does return at the start, with "Ad-hoc backup started" (`packages/cli/src/commands/backup-ops.ts:131`).
- Before either path, `acquireRemoteRenet('provision')` runs (`packages/cli/src/commands/backup-ops.ts:206`). It is a renet install step, not a job.

The plan's Open question 2 default needs this correction. To make `backup run` return at the start, use `systemctl start --no-block`. `-b` on `backup run` today sets `detached` on nothing: it makes no executor call, so it is a silent no-op.

### The 84 `detachable` commands

The set is in `packages/shared/src/cli-contract/data/contract.generated.ts`, computed by `packages/cli/scripts/generate-cli-contract.ts:503` as `proxyCapable && domain !== 'job' && !DETACH_EXCLUSIONS`. `DETACH_EXCLUSIONS` is empty (`packages/cli/scripts/generate-cli-contract.ts:117`).

Covered long verbs (9): `repo up`, `repo down`, `repo fork`, `repo push`, `repo pull`, `repo migrate`, `backup snapshot`, `backup restore`, `backup verify`. `backup restore-path` is not a command.

The other **75 are not covered**:

- **Read and probe verbs:** `backup browse`, `backup list`, `backup status`, `repo cat`, `repo diff`, `repo list`, `repo log`, `repo logs`, `repo status`, `repo policy get`, `repo admin autostart list`, `machine gpu list`, `machine health`, `machine status`, `datastore list`, `datastore status`, `datastore snapshot list`, `cluster snapshot list`, `subscription status`, `vscode serve status`.
- **Short mutations or config:** `backup cancel`, `backup schedule`, `repo admin autostart enable`, `repo admin autostart disable`, `repo admin ownership`, `repo admin template apply`, `repo admin validate`, `repo canary create`, `repo canary remove`, `repo canary weight`, `repo gpu grant`, `repo gpu revoke`, `repo policy set`, `repo replicate refresh`, `repo replicate remove`, `repo promote`, `repo commit`, `repo merge`, `repo exec`, `repo delete`, `repo create`, `subscription refresh`, `vscode serve stop`.
- **Long but not on the covered list:**
  - `repo checkout` (forks via `handleForkAction`, `packages/cli/src/commands/repo-branching.ts:175`).
  - `repo replicate`.
  - `repo resize`, `repo expand`, `repo gc`, `repo prune`, `repo trim`, `repo admin fsck`.
  - `machine setup`, `machine provision`, `machine deprovision`, `machine prune`, `machine restart-services`, `machine infra push`, `machine infra cert push`.
  - `cluster create`, `cluster destroy`, `cluster evict`, `cluster fork`, `cluster join`, `cluster migrate`, `cluster rehearse`, `cluster scale`, `cluster snapshot create`.
  - `datastore attach`, `datastore create`, `datastore delete`, `datastore detach`, `datastore fork`, `datastore resize`, `datastore snapshot create`.
- **Never calls the executor, so `-b` does nothing:** `backup run`.

Counting `backup run` there, the list is 75. The narrowed `JOB_VERBS` table will refuse `-b` on every one of them, so J2 needs a decision on each long-but-uncovered group.

Third-round note: there is no narrowing (J2b). All 75 become jobs per J0b's rows, and `-b` opens on each one as it converts. Only the ten `BACKGROUND_UNSAFE` verbs stay refused until J22 removes them.

### Settled by the audit

- **JOB_FUNCTIONS list:** confirmed against the verb audit (call sites listed under "Callers" below). It needs no extra function. `repository_mount` (`repo up --no-start`) stays out and would run as a plain `renet execute` even though `repo up` is a `JOB_VERB`. Third-round note: superseded by section 14. `repository_mount` is a job like every other call.
- **Timeout (Design 9, Risk 4):**
  - `resolveRenetTimeoutMs` (`packages/cli/src/services/executor/renet-command.ts:99-109`) gives 24 h only to the six backup functions (`:91-97`).
  - `repository_up`, `repository_up_all` and `repository_fork` get the 10-minute default.
  - **Recommendation: add `repository_up`, `repository_up_all` and `repository_fork` to the 24 h set.** Both `repo up --no-wait` and `fork --no-wait` exist because these runs can wait on a health gate, and migrate's phase 3 and the fork `--up` compound both run them as the final step.
  - `repository_down` can stay at the default.
  - Third-round note: section 20 generalizes this into the two-class rule over every function.
- **Callers of the job functions** (from a grep):
  - `repository_up`: `packages/cli/src/commands/repo.ts:84`, `packages/cli/src/commands/repo-backup.ts:185` and `:328`, `packages/cli/src/commands/repo-fork.ts:333`, `packages/cli/src/commands/repo-migrate.ts:308`, `packages/cli/src/commands/backup.ts:635`.
  - `repository_down` and the `_all` forms: `packages/cli/src/commands/repo.ts:262`, `packages/cli/src/commands/repo-migrate.ts:265` and `:285`, `packages/cli/src/commands/repo-batch-utils.ts:288` and `:329`.
  - All paths are under `packages/cli/src/commands/`.

### Surprises

1. `backup run` does not return at the unit start for a deployed unit. It blocks on `systemctl start` of a `Type=oneshot` unit (`packages/cli/src/commands/backup-ops.ts:30`; `packages/cli/src/services/backup/backup-schedule-unit-generator.ts:265-268`). The plan's Open question 2 default rests on the opposite claim.
2. `backupDecorator` marks **every** call detached, including `repository_list` (`packages/cli/src/services/repo/repo-mount-check.ts:55`) and `network_used`. Each mutating verb under `-b` leaks a stray job per probe, and every probe fails open on empty stdout. The step-5 wrong-host check (`packages/cli/src/utils/repo-target.ts:35-45`) is silently off.
3. `backup verify -b` records and prints "verified" with no verification (`packages/cli/src/commands/backup-storage.ts:410-412`). `backup snapshot -b` records `stored` at job start.
4. `repo migrate -b` is destructive: it deletes the source image while the delta push is still running. It also needs a renet compound `repository_migrate`, because it has five jobs in a row and the plan's "terminal job" rule cannot fit it otherwise. The R1 placement rewrite must survive a phase-3 failure, so the finalizer must fire on a `cutover_complete` marker, not on job success.
5. `repo up` runs `postRepoUpTasks` even when the up failed (`packages/cli/src/commands/repo.ts:111`).
6. The comment at `packages/cli/src/commands/repo-fork.ts:643` says step-5 verification is skipped, but `resolveRepoRef(ref)` is called with no options, so `withDefaultVerifier` does inject the probe. The comment is stale.
7. `repo push`'s `finalizePush` makes a machine call after its terminal job when the repo is immutable (`repository_commit_meta`, `packages/cli/src/commands/repo-delta.ts:97`). That is a design-rule-3 violation the plan's table does not list.
8. `repo checkout` and `repo commit` reach `repository_fork` through `handleForkAction` (`packages/cli/src/commands/repo-branching.ts:175`) but are not in the plan's `JOB_VERBS`, so under the new design they would run a job without accepting `-b`.
9. `readSourceAnchor` is a `backup_verify` job needed by `backup restore --at <time>` and by the restore-path route. Under `-b` it blocks `--at` with `streamUnknown`. Design 3 already says to follow such probes. The J3 test hook must distinguish the probe from the terminal job by `captureOutput`, not by function name.
10. Fork's `repository_fork` is the only create-tier job function (`packages/shared/src/renet-contract/data/license-tiers.generated.ts:162`). Under `-b` its identity refresh runs before the fork exists, so it needs the finalizer (`packages/cli/src/commands/repo-fork.ts:512`).

## Operator rulings, fourth round (2026-10-29)

Asked 2026-10-29 after the third-round amendment, all four Recommended options chosen:

- Attach window: "20 s (Recommended)". `JOB_ATTACH_WINDOW_MS = 20_000`; it returns to the operator only if L3b finds more than 10 % of short commands over it.
- Overlap: "Class matrix (Recommended)". Exclusive meeting exclusive or shared on the same repo refuses with exit 15 and the attach hint; shared with shared warns; reads and scheduled units only warn; no override flag.
- Client-side steps while the client is away: "Accept, make it visible (Recommended)". No nudge; `rdc job list` and the notice show pending steps, and the spool keeps the step plan 7 days.
- Origin: "Full origin (Recommended)". Client kind, rdc version, the sudo user, the config name and short id, and the account actor on the proxy and console paths.

## J0b machine-plane job audit (2026-10-29, lead session d778be9d)

All paths are repo-relative. The table has 93 rows.

**Shorthand**
- **verifier probe**: the `repository_list` probe from `resolveRepoRef`, injected for every non-`readOnly` ref (packages/cli/src/utils/repo-target.ts:35-45, packages/cli/src/services/repo/repo-mount-check.ts:55-60).
- **netid probe**: the `network_used` or list probe `ensureRepositoryNetworkId` may issue when a repo record lacks a network id (packages/cli/src/services/config/network-id-discovery.ts:69).
- **datastore arm**: cluster repos resolve to a datastore, so the verifier returns true without a probe (packages/cli/src/utils/repo-target.ts:35-45).
- **S** is a success step and **F** is a failure step.
- Lock classes: repo-exclusive, repo-shared, machine-exclusive, read. `control` is a proposed class (see finding 4).
- Timeout: `24h` or `10m` per section 20.

### Table

| Command | 1. CLI entry | 2. Machine calls in order | 3. Form | 4. Client steps after the work | 5. Lock | 6. Timeout | 7. Exception | 8. Box |
|---|---|---|---|---|---|---|---|---|
| backup browse | packages/cli/src/commands/backup-storage.ts:208 | verifier probe; with `--at`, `backup_browse_at` (packages/cli/src/commands/backup-storage-browse.ts:55), else `backup_browse` (packages/cli/src/commands/backup-storage.ts:237); netid probe | 2 | S: render listing (needs output). F: exit 18 (`RENET_NO_LISTING_EXIT`) maps to a warning and its own exit code, so the ticket must keep the code | read | 10m | none | J17 |
| backup cancel | packages/cli/src/commands/backup-ops.ts:438 | no renet call. SFTP `systemctl is-active` and `sudo systemctl stop` per unit (packages/cli/src/commands/backup-ops.ts:255, :334) | 3* (new allow-list entry) | none; the per-unit messages are output | control (finding 4) | 10m | none | J17 |
| backup list | packages/cli/src/commands/backup.ts:38 | `backup_list` (packages/cli/src/commands/repo-backup-list.ts:95) | 1 | S: render list (needs output) | read | 10m | none | J17 |
| backup run | packages/cli/src/commands/backup-ops.ts:410 | `acquireRemoteRenet` (exempt bootstrap, :219); per unit `systemctl cat` probe, `systemctl show`/`stop`/`reset-failed` of the ad-hoc unit (:146); deployed path `sudo systemctl start` (:30) or ad-hoc `systemd-run` (:110) | 3 (`backup-unit`) | before the job: `seedStrategyRetention` over HTTP (packages/cli/src/commands/backup-ops.ts:157). After: none | machine-scope shared (finding 4); no listed class fits | 24h (`backup-unit`) | none | J17 |
| backup schedule | packages/cli/src/commands/backup-ops.ts:379 | `acquireRemoteRenet`; raw renet license scan, account HTTP issue, license write (packages/cli/src/services/backup/backup-schedule.ts:116-150, packages/cli/src/services/account/license-batch.ts:170-183); SFTP unit-file reads and writes, `daemon-reload`, enable, verify (packages/cli/src/services/backup/backup-schedule.ts:342-395) | 3* (unit bodies as args) | S: `seedStrategyRetention` (HTTP), `warnIfConfigStorageUnenrolled` (packages/cli/src/commands/backup-ops.ts:390-410) | machine-exclusive | 10m | none | J17 |
| backup status | packages/cli/src/commands/backup-ops.ts:424 | no renet call. SFTP `systemctl show` per unit (packages/cli/src/services/backup/backup-schedule.ts:286-330); with a strategy, `journalctl` (packages/cli/src/commands/backup-ops.ts:360) | 3* (read) | S: render table and set exit code from `scheduleStatusExitCode` (needs output) | read | 10m | none | J17 |
| cluster create | packages/cli/src/commands/cluster/index.ts:35 | local tofu or KVM provision (packages/cli/src/services/cluster/cluster-provision.ts:113); per member `waitForSSH` then raw `renet setup --auto` (packages/cli/src/services/renet/machine-bootstrap.ts:41-79, packages/cli/src/services/cluster/cluster-provision.ts:161); control DNS over HTTP (:387); `ceph_health` (:196), `ceph_install_prerequisites` per member (:234), ceph bootstrap and cluster create (:239-253), `ceph_pool_create` (:279), ceph client config export and install (:306-322); `datastore_create`, `datastore_attach`, `kube_install` on control (packages/cli/src/services/cluster/cluster-kube.ts:316-327), `kube_join_token` (:368), `kube_join` per agent (:382) | 4 | S: `updateCluster` (KVM ids), `materializeClusterMachines`, audit record. F: none today | machine-exclusive per member | 24h | local tofu legs stay local (section 24) | J19 |
| cluster destroy | packages/cli/src/commands/cluster/index.ts:174 | no machine call: DNS removal over HTTP, tofu destroy or KVM teardown (local), config removal (packages/cli/src/services/cluster/cluster-provision.ts:538-565) | exempt | n/a | n/a | n/a | proposed: local tofu and ops only, no SSH leg (section 24 tofu row) | none (J19 records) |
| cluster evict | packages/cli/src/commands/cluster/index.ts:321 | `kube_node_remove` on control, `kube_uninstall` on the member (packages/cli/src/services/cluster/cluster-membership.ts:236-253) | 4 (two machines, group ticket, static successor) | S: `updateMachine` clears the cluster field (:267) | machine-exclusive per machine | 24h | none | J19 |
| cluster fork | packages/cli/src/commands/cluster/index.ts:208 | `assertDestNotRunningOwnK3s` probe, `prepareForkDest` (`kube_fork_dest_prep`, `ceph_client_config_install`), `datastore_list` capture (packages/cli/src/services/cluster/cluster-fork.ts:99-104), `datastore_snapshot_create` (:187), per datastore `datastore_fork` (:198), `datastore_adopt` (:206), `datastore_attach` (:218), client `allocateNetworkId` (:231), `kube_identity_rewrite` (:237), `kube_join_token` (:254), `kube_join` (:266) | 4 | S: config records, audit record (:288). F: discard of partial fork (:463) | machine-exclusive per machine | 24h | none | J19 |
| cluster join | packages/cli/src/commands/cluster/index.ts:309 | `kube_join_token` on control, `kube_join` on the member (packages/cli/src/services/cluster/cluster-membership.ts:132-149) | 4 (the join consumes the token output) | S: `updateMachine` cluster membership (:163) | machine-exclusive per machine | 24h | none | J19 |
| cluster kubeconfig | packages/cli/src/commands/cluster/index.ts:195 | no renet call. SFTP `sudo cat <kubeconfig>` (packages/cli/src/services/cluster/kubeconfig-cache.ts:36) | exempt | the local cache write is the command | n/a | n/a | section 24 not-proxyable row; no renet call, so nothing to convert | none |
| cluster migrate | packages/cli/src/commands/cluster/index.ts:247 | `datastore_list` capture (packages/cli/src/services/cluster/cluster-fork.ts:646), `datastore_adopt` (:539), `kube_prep_fork` (:553), `datastore_detach` (:561), `datastore_attach` on dest (:570), `kube_identity_rewrite` (:590), `datastore_forget` (:617), verify `datastore_list` (:667) | 4 | F: client-driven rollback `rollbackMigrateToSource` (`datastore_attach --force`, `kube_identity_rewrite`; :689-697). S: audit record (:627) | machine-exclusive per machine | 24h | none | J19 |
| cluster rehearse | packages/cli/src/commands/cluster/index.ts:259 | the `cluster fork` chain, then `kube_health` polling gate (packages/cli/src/services/cluster/cluster-fork.ts:318-342), then discard: `kube_uninstall`, `datastore_detach` (:432-455) | 4 | S and F: discard teardown runs on both outcomes | machine-exclusive per machine | 24h | none | J19 |
| cluster scale | packages/cli/src/commands/cluster/index.ts:154 | grow: tofu or KVM (local), `bootstrapMachine` per new member, `kube_join_token`, `kube_join`; shrink: `kube_prep_fork`, `kube_node_remove` (packages/cli/src/services/cluster/cluster-kube.ts:404-449) | 4 | S: `updateCluster` pool count, then `removeMachine` for removed members (packages/cli/src/services/cluster/cluster-provision.ts:630-645) | machine-exclusive per machine | 24h | local tofu legs stay local | J19 |
| cluster snapshot create | packages/cli/src/commands/cluster/index.ts:284 | `datastore_list` capture, then `datastore_snapshot_create` with `group` (packages/cli/src/services/cluster/cluster-snapshot.ts:48, :83) | 2* (the ceph-datastores-exist check becomes a new precondition) | S: out-of-instant warning (needs the list output) | machine-exclusive | 24h | none | J19 |
| cluster snapshot list | packages/cli/src/commands/cluster/index.ts:296 | `datastore_snapshot_list` (packages/cli/src/services/cluster/cluster-snapshot.ts:108) | 1 | S: render (needs output) | read | 10m | none | J19 |
| config reconcile | packages/cli/src/commands/config.ts:610 | per machine, raw `renet list all` through `fetchMachineStatus` (packages/cli/src/commands/config.ts:288-340, packages/cli/src/services/machine/machine-status.ts:57) | 3 (`list-all`, one job per machine under one group) | S: `reconcileState` writes the state bucket (packages/cli/src/services/config/config-reconcile.ts:297) | read | 10m | stays exempt from the proxy (packages/cli/scripts/generate-cli-contract.ts:89-103); the machine call is a job | J18 |
| datastore attach | packages/cli/src/commands/datastore.ts:300 | simple: `datastore_attach`. Relocation: `datastore_list` capture on the source, `datastore_adopt` on the target (packages/cli/src/commands/datastore.ts:73, :113), `datastore_detach` on the source, `datastore_attach` on the target | 4 | S: `setDatastoreState` | machine-exclusive per machine | 24h | none | J19 |
| datastore create | packages/cli/src/commands/datastore.ts:144 | `datastore_create` (:192) | 1 | S: `recordDatastore` | machine-exclusive | 24h | none | J19 |
| datastore delete | packages/cli/src/commands/datastore.ts:624 | if attached: `datastore_detach`, then `datastore_delete` on the same host | 4 (compound on one machine) | S: `setDatastoreState` cleared between the calls, then `forgetDatastore` (:650-672) | machine-exclusive | 24h | none | J19 |
| datastore detach | packages/cli/src/commands/datastore.ts:396 | `datastore_detach` | 1 | S: `setDatastoreState({lastHolder})`; with `--discard`, `forgetDatastore` | machine-exclusive | 24h | none | J19 |
| datastore fork | packages/cli/src/commands/datastore.ts:454 | `datastore_fork` on the host; with `--attach-to`, `datastore_attach` on a second machine | 4 (static successor) | S: `recordDatastore` after the fork, then `setDatastoreState` after the attach | machine-exclusive per machine | 24h | none | J19 |
| datastore list | packages/cli/src/commands/datastore.ts:230 | none; reads config and state only | exempt | n/a | n/a | n/a | proposed: no machine call (plane is inherited from the domain, packages/cli/src/config/command-planes.ts:50) | none |
| datastore resize | packages/cli/src/commands/datastore.ts:599 | `datastore_resize` | 1 | S: `recordDatastore` with the new size (:616) | machine-exclusive | 24h | none | J19 |
| datastore snapshot create | packages/cli/src/commands/datastore.ts:550 | `datastore_snapshot_create` | 1 | none | machine-exclusive | 24h | none | J19 |
| datastore snapshot list | packages/cli/src/commands/datastore.ts:575 | `datastore_snapshot_list` capture | 1 | S: render (needs output) | read | 10m | none | J19 |
| datastore status | packages/cli/src/commands/datastore.ts:263 | when attached, `datastore_status` capture (:282); otherwise no machine call | 1 | S: render (needs output) | read | 10m | none | J19 |
| job cancel | packages/cli/src/commands/job.ts:170 | `renet job cancel` | exempt | n/a | control | n/a | section 24: drives the spool | none |
| job gc | packages/cli/src/commands/job.ts:184 | `renet job gc` | exempt | n/a | n/a | n/a | section 24 | none |
| job list | packages/cli/src/commands/job.ts:117 | `renet job list` | exempt | n/a | n/a | n/a | section 24 | none |
| job logs | packages/cli/src/commands/job.ts:154 | `renet job logs` | exempt | n/a | n/a | n/a | section 24 | none |
| job status | packages/cli/src/commands/job.ts:137 | `renet job status` | exempt | n/a | n/a | n/a | section 24 | none |
| machine access push | packages/cli/src/commands/machine/access.ts:211 | no renet call. SFTP read, write and compare-and-swap of `authorized_keys` (packages/cli/src/services/machine/access-push.ts:250-289) | exempt | none | n/a | n/a | section 24 not-proxyable row; no renet call, so nothing to convert | none |
| machine converge | packages/cli/src/commands/machine/converge.ts:83 | `machine_converge_runtime` with capture (:83-130) | 1 | S and F: `settleConverge` renders the report and sets the exit code from the output | machine-exclusive | 24h (proposed; not named in section 20, finding 5) | stays exempt from the proxy; the call is a job | J18 |
| machine deprovision | packages/cli/src/commands/machine/provision.ts:38 | none: tofu destroy and cleanup, config removal, DNS over HTTP (packages/cli/src/services/tofu/provision.ts:218-233) | exempt | n/a | n/a | n/a | section 24 tofu row; J18's "SSH legs of deprovision" do not exist | none |
| machine gpu list | packages/cli/src/commands/machine/gpu.ts:170 | `machine_gpu_list` capture (:142) | 1 | S: render (needs output) | read | 10m | none | J18 |
| machine health | packages/cli/src/commands/machine/health.ts:185 | raw `renet list all` through `getWithVaultStatus` (packages/cli/src/services/state.ts:104-113), then raw `/proc` probe `probeStaleRenetProcesses` (packages/cli/src/commands/machine/status.ts:678, packages/cli/src/services/renet/renet-daemons.ts:28-64) | 3 (`list-all`; the stale-process probe must fold into its payload) | S: render, set exit code from `getMachineHealth` (needs output) | read | 10m | none | J18 |
| machine infra cert pull | packages/cli/src/commands/machine/infra.ts:163 | no renet call. SFTP `sudo cat` of `acme.json` (packages/cli/src/services/account/cert-cache.ts:434) | exempt | the merge into the local cert cache is the command | n/a | n/a | section 24 not-proxyable row; no renet call | none |
| machine infra cert push | packages/cli/src/commands/machine/infra.ts:181 | no renet call. SFTP `sudo sh -c` writing `acme.json` (packages/cli/src/services/account/cert-cache.ts:447) | exempt (proposed) | none | machine-exclusive if converted | 10m | proposed: one raw write of a local file, no renet call. The alternative is a `cert-write` allow-list entry | none (J18 records) |
| machine infra push | packages/cli/src/commands/machine/infra.ts:142 | `acquireRemoteRenet` (exempt); raw `renet proxy configure` with the infra JSON on stdin; SFTP cert upload; raw `renet proxy install` (packages/cli/src/services/provision/infra-provision.ts:283-343) | 4 (new command-kind and a pre-job upload) | S: Cloudflare DNS ensure over HTTP (:356-396) | machine-exclusive | 10m | none | J18 |
| machine provision | packages/cli/src/commands/machine/provision.ts:9 | tofu apply (local); `waitForSSH`; raw `renet setup --auto` (packages/cli/src/services/tofu/provision.ts:146-154); `pushInfraConfig` (infra push chain above) | 4 (`setup`, then a successor `infra push`) | S: `addMachine`, `knownHosts`, `setMachineInfra` (packages/cli/src/services/tofu/provision.ts:149-166) | machine-exclusive | 24h (`setup`) | tofu legs stay local (section 24) | J18 |
| machine prune | packages/cli/src/commands/machine/prune.ts:382 | `repository_prune` capture (:55), `network_prune` capture (:109); with `--orphaned-repos` or `--prune-unknown`, raw `renet list all` (`fetchMachineStatus`), then N `repository_delete` (:171) | 4 | S: `cleanupSshArtifacts`, `purgeExpiredArchives`, outcome render (packages/cli/src/commands/machine/prune.ts:188-330) | machine-exclusive | 10m | none | J18 |
| machine restart-services | packages/cli/src/commands/machine/restart-services.ts:71 | no renet function. Raw `renet daemons upgrade --json --keep-slots 0` (packages/cli/src/services/renet/renet-daemons.ts:233-249) | 3* (`daemons-restart`) | S: render report, set exit code if any restart failed (needs output) | machine-exclusive | 24h (proposed, finding 5) | none | J18 |
| machine scan-keys | packages/cli/src/commands/machine/register.ts:269 | no machine exec: local `ssh-keyscan` (packages/cli/src/commands/machine/register.ts:80-110) | exempt | `updateMachine` is the command | n/a | n/a | section 24 not-proxyable row; local write | none |
| machine setup | packages/cli/src/commands/machine/register.ts:288 | `acquireRemoteRenet` (exempt, :310); raw `renet setup --auto` (:324); raw `renet runtime status --json` (packages/cli/src/services/renet/runtime-converge.ts:183-216); `machine_converge_runtime` if stale (packages/cli/src/commands/machine/converge.ts:160-190); raw router refresh (packages/cli/src/services/renet/renet-provisioner.ts:563) | 4 (`setup` job, converge as a recorded successor) | S: `deployAllRepoKeys`, `pushAccess`, `pushInfraConfig` (packages/cli/src/commands/machine/register.ts:22-65) and the converge pass. F: converge off, router refresh only (:114) | machine-exclusive | 24h | none | J18 |
| machine status | packages/cli/src/commands/machine/status.ts:748 | raw `renet list all` (packages/cli/src/services/machine/machine-status.ts:57); `fetchRepoLicenseDetail` (raw license reads, :150-180); raw `/proc` probe (packages/cli/src/commands/machine/status.ts:678) | 3 (`list-all`; license and stale reads fold into its payload) | S: render (needs output) | read | 10m | none | J18 |
| repo admin autostart disable | packages/cli/src/commands/repo-extended.ts:343 | with ref: verifier probe, `repository_autostart_disable` (:361); with `-m`: single call | 2 (1 with `-m`) | none | repo-exclusive with ref, machine-exclusive with `-m` | 10m | none | J16 |
| repo admin autostart enable | packages/cli/src/commands/repo-extended.ts:289 | as above with `repository_autostart_enable` (:307) | 2 (1 with `-m`) | none | repo-exclusive with ref, machine-exclusive with `-m` | 10m | none | J16 |
| repo admin autostart list | packages/cli/src/commands/repo-extended.ts:397 | `repository_autostart_list` capture (:91) | 1 | S: render (needs output) | read | 10m | none | J16 |
| repo admin fsck | packages/cli/src/commands/repo-maintenance.ts:233 | one `repository_list` capture per recorded datastore mount (packages/cli/src/commands/repo-maintenance.ts:89) | 4 (compound read) | S and F: dangling and orphan report, exit 1 on drift (needs output and config) | read (machine scope, finding 4) | 10m | none | J16 |
| repo admin ownership | packages/cli/src/commands/repo-extended.ts:412 | verifier probe, `repository_ownership` (:434) | 2 | none | repo-exclusive | 10m | none | J16 |
| repo admin template apply | packages/cli/src/commands/repo-extended.ts:484 | verifier probe, `repository_template_apply` (:547) | 2 | none | repo-exclusive | 10m | none | J16 |
| repo admin validate | packages/cli/src/commands/repo-extended.ts:243 | verifier probe, `repository_validate` (:260) | 2 | none | read | 10m | none | J16 |
| repo canary create | packages/cli/src/commands/repo-canary.ts:53 | no probe (datastore arm); `datastore_snapshot_create` group (packages/cli/src/services/cluster/repo-release.ts:66), `kube_apply` (:283) | 4 (compound on the control machine) | S: `recordCanary` (packages/cli/src/services/cluster/repo-release.ts:192) | repo-exclusive | 24h (datastore lifecycle) | none | J16 |
| repo canary remove | packages/cli/src/commands/repo-canary.ts:134 | `kube_delete` (packages/cli/src/services/cluster/repo-release.ts:239-262) | 1 | S: forget the canary record. Today a delete failure only warns and the record is still forgotten | repo-exclusive | 10m | none | J16 |
| repo canary weight | packages/cli/src/commands/repo-canary.ts:117 | `datastore_snapshot_create` group, `kube_apply` (packages/cli/src/services/cluster/repo-release.ts:206-232) | 4 | S: `recordCanary` | repo-exclusive | 24h | none | J16 |
| repo cat | packages/cli/src/commands/repo-cat.ts:54 | netid probe; `repository_cat` (:109) | 1 | S: print file (needs output) | read | 10m | none | J16 |
| repo checkout | packages/cli/src/commands/repo-branching.ts:343 | verifier probe on the source family, netid probe, `deployRepoKeyIfNeeded`, `repository_fork` (packages/cli/src/commands/repo-fork.ts:541-600, `handleForkAction`) | 2 | S: identity refresh, `reconcileBackupSchedules`, record `headCommit` (packages/cli/src/commands/repo-branching.ts:200-215). F: rollback `removeRepository` and key removal | repo-exclusive on the new repo, repo-shared on the source | 24h (`repository_fork`) | none | J16 |
| repo commit | packages/cli/src/commands/repo-branching.ts:325 | verifier probe, `repository_commit` (:67) | 2 | S: `addRepository` for the commit object, advance `headCommit` (:84-96) | repo-exclusive | 10m | none | J16 |
| repo create | packages/cli/src/commands/repo-create-delete.ts:536 | config registration before the job; netid allocation (`network_used`); `repository_create` (:218, :301); a network-id-conflict retry `repository_create` (packages/cli/src/services/config/network-id-discovery.ts:347) | 2 (`network_id:"auto"` removes the retry leg) | S: `reconcileBackupSchedules` (:83). F: `rollbackCreateRepo` (:62) | repo-exclusive | 24h | none | J16 |
| repo delete | packages/cli/src/commands/repo-create-delete.ts:551 | verifier with `absentOk` (a definite absence skips the machine call); netid probe; `repository_delete` (:503) | 2 (`repo_present` or `repo_absent` precondition) | S: SSH-config cleanup, `settleConfigEntry`, `reconcileBackupSchedules`, `settleCloudBackups`, `settleRepoLicense` (:385-430) | repo-exclusive | 10m | none | J16 |
| repo diff | packages/cli/src/commands/repo-diff.ts:316 | netid probe; `repository_diff` (:275) | 1 | S: render (needs output) | read | 10m | none | J16 |
| repo exec | packages/cli/src/commands/repo-container.ts:121 | verifier probe; `container_exec` (:146); the interactive form (`-i`, `tty: true`) is exempt | 2 | S and F: the remote exit code is the result (`setExitCode`, :150-170), so the ticket must keep the job exit code | repo-shared | 10m | `-i` form: section 24 | J16 |
| repo expand | packages/cli/src/commands/repo-extended.ts:189 | verifier probe, `repository_expand` (:208) | 2 | none | repo-exclusive | 24h | none | J16 |
| repo gc | packages/cli/src/commands/repo-maintenance.ts:220 | one `repository_list` capture per datastore mount (:89); then N `repository_delete` (:145) over a client-computed set | 4 (compound `repository_gc`) | S: per-commit result lines and totals (needs the delete results) | machine-exclusive (finding 4) | 10m | none | J16 |
| repo gpu grant | packages/cli/src/commands/repo-gpu.ts:100 | verifier probe; `repository_gpu_grant` capture (:47) | 2 | S: `setRepositoryGpuDevices` from the output (:62) | repo-exclusive | 10m | none | J16 |
| repo gpu revoke | packages/cli/src/commands/repo-gpu.ts:100 | verifier probe; `repository_gpu_revoke` capture (:47) | 2 | S: `setRepositoryGpuDevices` from the output (:62) | repo-exclusive | 10m | none | J16 |
| repo list | packages/cli/src/commands/repo.ts:359 | `repository_list` capture (packages/cli/src/commands/repo-batch-utils.ts:408) | 1 | S: render with name resolution (needs output) | read | 10m | none | J16 |
| repo log | packages/cli/src/commands/repo-branching.ts:354 | `repository_log` (:211); read-only resolve | 1 | S: render (needs output) | read | 10m | none | J16 |
| repo logs | packages/cli/src/commands/repo-container.ts:63 | `container_logs` (:95); read-only resolve | 1 | none (passthrough output) | read | 10m | `-f` form: section 24 | J16 |
| repo merge | packages/cli/src/commands/repo-branching.ts:362 | verifier probe, `repository_merge` (:289) | 2 | S: advance `headCommit` (:302-312) | repo-exclusive | 10m | none | J16 |
| repo policy get | packages/cli/src/commands/repo-policy.ts:215 | `repository_policy_get` capture (:91); read-only resolve | 1 | S: render (needs output) | read | 10m | none | J16 |
| repo policy set | packages/cli/src/commands/repo-policy.ts:184 | verifier probe, `repository_policy_set` capture (:91) | 2 | S: render result (needs output) | repo-exclusive | 10m | none | J16 |
| repo promote | packages/cli/src/commands/repo-promote.ts:135 | verifier probe; `repository_promote` (:91) | 2 | S: `reconcileBackupSchedules` (:127) | repo-exclusive | 10m | none | J16 |
| repo prune | packages/cli/src/commands/repo-prune.ts:270 | with ref (read-only resolve): `repository_docker_prune` capture (:176). Machine survey: `repository_list` capture (:229), then N `repository_docker_prune` | 4 for the survey, 1 for the ref form | S: render records, exit 1 if any refused (needs output) | repo-exclusive with ref, machine-exclusive for the survey | 24h (finding 5) | none | J16 |
| repo replicate | packages/cli/src/commands/repo-replicate.ts:66 | per replica: `datastore_snapshot_create`, `datastore_fork`, `datastore_adopt`, `datastore_attach`, `datastore_forget`, `datastore_volumes_open`, `kube_node_label` (packages/cli/src/services/cluster/repo-replicate.ts:117-246); then `kube_apply` (packages/cli/src/services/cluster/repo-replicate-ops.ts:139) | 4 (multi-machine) | S: `recordReplicaSet` (:153) | repo-exclusive | 24h | none | J16 |
| repo replicate refresh | packages/cli/src/commands/repo-replicate.ts:145 | `datastore_snapshot_create`, `kube_node_label`, `kube_delete`, `datastore_volumes_close`, detach with retry, `datastore_snapshot_delete`, re-provision (packages/cli/src/services/cluster/repo-replicate-ops.ts:412-490) | 4 | S: `recordReplicaSet` (:480) | repo-exclusive | 24h | none | J16 |
| repo replicate remove | packages/cli/src/commands/repo-replicate.ts:129 | `kube_delete`, `kube_node_label`, `datastore_snapshot_delete`, N detach with discard, `datastore_list` survivors (packages/cli/src/services/cluster/repo-replicate-ops.ts:197-262, :365) | 4 | S: `forgetReplicaSet` (:261) | repo-exclusive | 24h | none | J16 |
| repo resize | packages/cli/src/commands/repo-extended.ts:146 | verifier probe, `repository_resize` (:165) | 2 | none | repo-exclusive | 24h | none | J16 |
| repo status | packages/cli/src/commands/repo.ts:293 | netid probe; `repository_status` capture. No `renet list all` call | 1 | S: render record, replica sets, canaries (needs output) | read | 10m | none | J16 |
| repo sync download | packages/cli/src/commands/repo-sync.ts:553 | client rsync | exempt | n/a | n/a | n/a | section 24 | none |
| repo sync status | packages/cli/src/commands/repo-sync.ts:575 | client rsync dry-run | exempt | n/a | n/a | n/a | section 24 | none |
| repo sync upload | packages/cli/src/commands/repo-sync.ts:531 | client rsync | exempt | n/a | n/a | n/a | section 24 | none |
| repo trim | packages/cli/src/commands/repo-trim.ts:163 | `repository_trim` capture (:104); read-only resolve | 1 | S: render (needs output) | repo-exclusive with ref, machine-exclusive with `-m` (finding 4) | 24h (finding 5) | none | J16 |
| repo tunnel | packages/cli/src/commands/repo-tunnel.ts:267 | interactive tunnel | exempt | n/a | n/a | n/a | section 24 | none |
| serve | packages/cli/src/commands/serve.ts:51 | the executor daemon | exempt | n/a | n/a | n/a | section 24 | none |
| subscription refresh | packages/cli/src/commands/subscription.ts:417 | `-m`: `acquireRemoteRenet` (provision); raw read of machine id and repo licenses, account HTTP issue, then license write over SFTP (packages/cli/src/services/account/license-batch.ts:170-183, packages/cli/src/commands/subscription-actions.ts:455-475). `--repo`: read-only resolve then `refreshRepoLicenseIdentity` over SSH (:476-520) | 4 (cannot fit, finding 3) | S: render summary | machine-exclusive (`-m`), repo-exclusive (`--repo`) | 10m | none | J20 |
| subscription status | packages/cli/src/commands/subscription.ts:397 | with `-m`: read-only renet acquire, raw runtime license reads, machine activation read (packages/cli/src/commands/subscription-actions.ts:395-430) | 3* (read; new `license-status` allow-list entry) | S: render (needs output) | read | 10m | none | J20 |
| term connect | packages/cli/src/commands/term.ts:600 | interactive shell | exempt | n/a | n/a | n/a | section 24 | none |
| vscode connect | packages/cli/src/commands/vscode.ts:562 | interactive | exempt | n/a | n/a | n/a | section 24 | none |
| vscode serve status | packages/cli/src/commands/vscode-serve.ts:58 | no renet call. SSH script as the repo user (packages/cli/src/services/core/vscode-server-remote.ts:316-330) | exempt (finding 9) | S: render (needs output) | n/a | n/a | runs as the repo user, not root (J0b finding 9) | none |
| vscode serve stop | packages/cli/src/commands/vscode-serve.ts:88 | no renet call. SSH script as the repo user (packages/cli/src/services/core/vscode-server-remote.ts:343) | exempt (finding 9) | S: render stopped or not-running (needs output) | n/a | n/a | runs as the repo user, not root (J0b finding 9) | none |

### Other plans that own a file a conversion box would touch

The plans below were found by grepping the `Owns` headers in `agent/plans`. Open boxes come from the plan checkboxes. The Concurrency line already names PLAN-cloudflare-proxy, PLAN-converge-preflight-and-repo-recovery, PLAN-renet-runtime-converge, PLAN-console-executor-multi-org, PLAN-proxy-cd-six-targets, PLAN-org-executor-connect-timeout-relocate, PLAN-telemetry-export, PLAN-renet-bridge-leftovers and PLAN-backup-local-image. The rest are missing from it.

**Not in the Concurrency line (open boxes in parentheses)**
- agent/plans/PLAN-backup-program.md (41): packages/cli/src/commands/backup.ts, packages/cli/src/commands/backup-storage-browse.ts. Boxes J17 touches.
- agent/plans/PLAN-backup-restore-path.md (4): packages/cli/src/commands/backup.ts, packages/cli/src/commands/backup-restore-path.ts, packages/cli/src/commands/backup-storage.ts, packages/cli/src/commands/backup-storage-browse.ts, packages/cli/src/services/executor/renet-function-access.ts.
- agent/plans/PLAN-backup-meter-orphaned-chunks.md (3): packages/cli/src/commands/backup-storage.ts, packages/cli/src/commands/backup-reconcile.ts.
- agent/plans/PLAN-snapshot-read-io-cap.md (1): packages/cli/src/commands/backup-storage.ts, packages/cli/src/commands/backup-strategy.ts, packages/cli/src/services/backup/backup-schedule-unit-generator.ts (J17 and J21).
- agent/plans/PLAN-backup-toc-exact-opt-in.md (10, not started): packages/cli/src/commands/repo-extended.ts, packages/cli/src/services/executor/renet-function-access.ts.
- agent/plans/PLAN-repo-docker-storage-prune.md (4): packages/cli/src/commands/repo-extended.ts, packages/cli/src/commands/repo-prune.ts, packages/cli/src/services/executor/renet-function-access.ts, packages/cli/src/utils/command-policy.ts.
- agent/plans/PLAN-config-networkid-discovery.md (1): packages/cli/src/commands/backup.ts, packages/cli/src/commands/repo-create-delete.ts, packages/cli/src/commands/repo-fork.ts, packages/cli/src/services/cluster/cluster-kube.ts, packages/cli/src/services/config/network-id-discovery.ts, packages/cli/src/services/repo/repo-mount-check.ts, packages/cli/src/utils/repo-executor.ts. This is the plan most likely to conflict with J16 and J19.
- agent/plans/PLAN-gpu-device-grants.md (3): packages/cli/src/commands/machine/gpu.ts, packages/cli/src/commands/repo-gpu.ts, packages/cli/src/commands/repo.ts.
- agent/plans/PLAN-ssh-key-source-ranges.md (2): packages/cli/src/commands/machine/register.ts, packages/cli/src/commands/machine/access.ts, packages/cli/scripts/generate-cli-contract.ts. J2b also edits `generate-cli-contract.ts`.
- agent/plans/PLAN-sync-remote-file-ownership.md (1): packages/cli/src/commands/repo-sync.ts. That file is exempt and not converted, so no conflict.

**Already named, with extra files the Concurrency line does not list**
- PLAN-telemetry-export owns packages/cli/src/services/cluster/cluster-target.ts, which J19 touches through `resolveExecutionTarget`.
- PLAN-renet-runtime-converge and PLAN-converge-preflight-and-repo-recovery own packages/cli/src/commands/machine/register.ts, packages/cli/src/commands/machine/converge.ts and packages/cli/src/services/renet/runtime-converge.ts, all J18 files.
- PLAN-cloudflare-proxy owns packages/cli/src/commands/subscription*.ts, which J20 touches.
- PLAN-renet-bridge-leftovers owns `packages/cli/src/commands/repo-*.ts` and `packages/cli/src/services/**` as globs, so it overlaps every J16 and J19 file.
- PLAN-backup-local-image owns two more files than the Concurrency line lists: packages/cli/src/commands/datastore-prune-parser.ts and packages/cli/src/utils/command-policy.ts.

### Commands whose machine work cannot fit one job or one recorded successor

1. **Chains where a later call consumes an earlier call's output, or a client decision sits between calls.** These cannot be a static successor recorded at start. Each needs a compound renet function, or the client must feed the successor from the first job's output. Section 18 steps are non-secret and run only in the CLI, so they cannot start a machine call.
   - `cluster join`: `kube_join` needs the `kube_join_token` output.
   - `cluster create`, `cluster scale` and `cluster fork`: the same token chain, plus client-side `allocateNetworkId` and SSH waits between machines.
   - `cluster migrate`: the source record is captured, then verified, with a client-driven rollback.
   - `cluster rehearse`: a client polling gate, and a teardown that must run on both outcomes.
   - `datastore attach` relocation: the source `datastore_list` record becomes the target's `datastore_adopt` input. The adopt on the target also comes before the detach on the source, so the calls alternate between machines.
   - `repo gc`, `repo admin fsck`, `repo prune` survey and `machine prune --orphaned-repos` or `--prune-unknown`: the deletion set is computed from the client's config. These fit only if the config's GUID set travels in the vault, so renet can compute the set inside one compound job.
2. **Secrets in a recorded successor.** `machine provision` chains `setup` into `infra push`. The infra JSON carries `cfDnsApiToken`. The ticket's `then` params must be non-secret (section 18), so the vault must be built at start and the successor must carry no secret. `machine infra push` also needs its cert-cache upload done before the job, as a pre-job SFTP step like the bootstrap upload.
3. **HTTP between two machine phases.** `subscription refresh` (both `-m` and `--repo`) and the license refresh inside `backup schedule` scan the machine, ask the account server for licenses, then write them back. A job with a step that issues a machine call is not allowed by section 18. Either split the work into a job, a client step and a successor job, or leave it exempt.
4. **Not renet calls at all.**
   - `backup cancel`, `backup status` and `backup schedule` run SFTP and `systemctl` directly.
   - `vscode serve status` and `vscode serve stop` run a shell script as the repo user, not as root. A job runs as a root systemd unit, so the identity changes.
   - `machine restart-services` runs `renet daemons upgrade`, and `subscription status -m` runs renet license reads.
   - None of these is in the section 14 allow-list (`setup`, `list-all`, `backup-unit`). Each needs a new entry or an exemption.

### Findings that change plan text

1. **`repository_migrate` target-up channel is refuted.** The channel `backup_push` uses is rsync over SSH from the source to the destination (private/renet/cmd/renet/backup_push.go:277-330, `pushToMachine`). It carries bytes only and does not run `renet execute` on the target. A target `repository_up` needs the target machine's vault, which the CLI builds per machine. Section 14's fallback is therefore the correct design, in three jobs under one ticket:
   - a source job: push, down, delta push, down-unmount, then the `cutover_complete` marker;
   - a successor `repository_up` on the target;
   - a successor `repository_delete` on the source, after the target up succeeds.

   Folding the delete into the source job would delete the source before the target is up.
2. **`repo status` has no `renet list all` call.** It makes one call, `repository_status` (packages/cli/src/commands/repo.ts:293). Section 19's jobs-on-this-repo view must come from the status function's payload.
3. **`cluster_create`, `cluster_destroy`, `cluster_scale`, `cluster_fork` and `cluster_migrate` are audit labels, not renet functions.** They are only passed to `auditService.recordOperation` (packages/cli/src/services/cluster/cluster-provision.ts:479, :552, :618; packages/cli/src/services/cluster/cluster-fork.ts:288, :627). None appears in packages/shared/src/renet-contract/data/license-tiers.generated.ts, so J3b's table does not list them and J19 cannot rely on them as job functions.
4. **The lock class list has gaps.**
   - `backup cancel` and `job cancel` must never be refused by the job they cancel, so a `control` class is needed.
   - `backup run` covers many repos, so it needs a machine-scope shared class.
   - `repo gc`, `fsck`, `trim -m` and `prune` survey have no repo GUID, so they need machine scope.
5. **Timeout gaps.**
   - Section 20 names neither `machine_converge_runtime` nor `renet daemons upgrade`. The latter waits on per-unit stability polls and, with `--include-docker`, restarts containers one repo at a time. Both are marked 24h here as a proposal.
   - `repository_trim` and `repository_docker_prune` are marked 10m by the rule. Both run longer on large pools.
6. **`machine deprovision` has no SSH leg** (packages/cli/src/services/tofu/provision.ts:218-233). J18's sentence about "the SSH legs of provision and deprovision" is wrong for deprovision.
7. **`backup run` with several strategies or units** needs `backup-unit` to take a `units` list. The section 21 form `{"unit": name}` covers one unit.
8. **`repo create` retry.** The network-id-conflict retry leg disappears if renet allocates the id inside the job (`network_id: "auto"`, section 14).
9. **Contract `detachable` flag.** The `detachable` flag is true for `machine infra cert push`, `machine infra push`, `backup cancel`, `backup status` and `backup schedule`, which make no renet call or only raw ones.

### J0b findings applied to the design (lead, 2026-10-29)

These corrections bind the later boxes wherever sections 14 to 24 say otherwise:
1. repo migrate (its row is in the J0 table above, not repeated in the J0b table) is three jobs under one ticket, not one: a source job (push, down, delta push, down-unmount, then the cutover_complete marker), a successor repository_up on the target, and a successor repository_delete on the source that starts only after the target up succeeds. The backup_push channel carries bytes only (private/renet/cmd/renet/backup_push.go:277-330).
2. repo status makes one call, repository_status; the jobs-on-this-repo view of section 19 comes from that function's payload (J21).
3. cluster_create, cluster_destroy, cluster_scale, cluster_fork and cluster_migrate are audit labels, not renet functions; J19 converts the underlying datastore and kube functions.
4. Lock classes gain `control` (backup cancel, job cancel: never refused by the job they stop) and a machine-scope shared class (backup run over many repos; repo gc, fsck, trim -m and the prune survey, which carry no repo GUID).
5. Timeouts: machine_converge_runtime and renet daemons upgrade join the 24 h class; repository_trim and repository_docker_prune join it too, since they run long on large pools.
6. machine deprovision has no SSH leg; it stays local (section 24), and J18 drops it.
7. backup-unit takes a `units` list, so one backup run job covers several strategies.
8. repo create's network-id retry leg disappears with network_id "auto" allocated in the job.
9. Chains whose later call consumes an earlier call's output (cluster join and the token chains, datastore attach relocation, client-computed deletion sets, the license refresh between two machine phases) get a compound renet function each, or stay client-driven with one job per phase under one ticket; J16 to J20 name which per row. vscode serve status and stop run as the repo user, so they stay exempt (section 24) rather than becoming root jobs.

