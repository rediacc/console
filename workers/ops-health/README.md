# ops-health Worker runbook

The off-box alerter. Every 10 minutes (`crons` in `wrangler.toml`) it probes the generic targets and mails the transitions through SES. It only reads and alerts. Fixes run locally: the refresher of `rediacc_ci.ops.ops_health` repairs what is auto-safe on the operator's machines and posts the remaining verdict to this Worker.

Design: `agent/plans/PLAN-health-checks-local.md` (D-runner, D-record, D-mail, D-config).

## What runs

- `src/index.ts`: the cron run, `GET /v1/status` and `POST /v1/ingest`.
- `src/probes.ts`: the five generic probe kinds (`tls`, `banner-465`, `https`, `health-endpoint`, `dnsbl-over-DoH`).
- `src/state.ts`: the `OpsState` Durable Object, one SQLite-backed instance named `state`. It holds the probe records, the mail log, the last digest time, the certificate-transparency cache and the last ingest per source. Reads and writes are serialized in the object, so there is no D1 and no bucket.
- `src/mail.ts`: the SES sender, the alert and the Monday digest.
- Build-time targets: the account and proxy `/health` endpoints of every region in `regions.json`.

## Tokens and secrets

Secrets are named here and never written down. They live in the `ops-health` bws profile and reach the Worker through `python3 -m rediacc_ci.ops.deploy_ops_health`.

| Name | Used for |
|---|---|
| `OPS_HEALTH_READ_TOKEN` | Bearer for `GET /v1/status`; the refresher, the CI gate and the deploy read with it. |
| `OPS_HEALTH_INGEST_TOKEN` | Bearer for `POST /v1/ingest`; the local refresher posts its verdicts with it. It also keys the digests of the deploy. |
| `OPS_ALERT_EMAILS` | The recipients, comma separated. An empty list shows as the `mailer` probe in state `unknown`. |
| `OPS_HEALTH_TARGETS` | The target file, read out of the `ops` repo at deploy time. |

The `AWS_SES_*` names (`AWS_SES_ACCESS_KEY_ID_EU`, `AWS_SES_SECRET_ACCESS_KEY_EU`, `AWS_SES_REGION_EU`, `AWS_SES_FROM`) configure the mail send, and `SPAMHAUS_DQS_KEY` is optional. A missing secret is reported as an `unknown` probe or a 401, never a crash.

## Targets

The target file schema is `{version: 1, probes: [{id, kind, host, port?, path?, expect?}], dnsbl: {ip, zones}}`. Probe ids match `^[a-z0-9][a-z0-9._:-]{0,63}$`, are unique, and never reuse `targets`, `mailer` or the `health:` prefix.

The file lives in the operator's `ops` repo, not here. A target change reaches the Worker in two steps: edit the file in the `ops` repo, then re-run `deploy_ops_health` (a dry run by default, `--write` applies it). The deploy validates the file against this schema, compares what the Worker serves (`targets_sha` in `/v1/status`) and puts only what changed. A code edit is never how a target changes. The Worker cannot read the file out of the repo's backups, because those are encrypted chunks and the repo key never leaves the machine (F20), so the deploy reads it from the live repo.

The local refresher compares `targets_sha` with the file's hash when `OPS_HEALTH_TARGETS_REF` is set, and a mismatch is the finding `ops.targets.drift`.

## Dedupe

Every alert goes through one mailer and one dedupe, applied in the Durable Object from `.ci/config/ops-health.json` (`transitions`):

- A probe turns red after `to_red` consecutive red runs and back to green after `to_green` green runs. A single failed run mails nothing.
- A red is mailed once, then again every `remail_hours` while it stays red. A recovery is mailed once.
- A new probe takes a green or unknown answer at once and still needs `to_red` runs to turn red.
- A local verdict arriving at `/v1/ingest` as `{source, state, detail, at}` goes through the same rules. The refresher posts it after its own auto-repair and re-check, so the mail reports only what is left. An ingest source older than its `ingest.max_age_h` entry counts as stale.
- A failed SES send leaves its transitions unmailed, so the next run retries them.

## Silencing a probe

A probe is silenced by a config edit, never a code edit, and the Worker is redeployed afterwards (the config is bundled at build time):

- A noisy probe: raise `transitions.to_red` (more consecutive runs before a red) or `transitions.remail_hours` in `.ci/config/ops-health.json`.
- A certificate probe that warns too early: lower `tls.warn_days` or `tls.red_days` in the same file.
- A source that posts rarely: raise its `ingest.max_age_h` entry.
- A target that no longer exists: remove it from the target file in the `ops` repo and re-run `deploy_ops_health`.

These knobs apply to every probe of their kind. The config has no per-probe mute, so a single probe is silenced by removing its target.

## Checking it

- `PYTHONPATH=.ci python3 -m rediacc_ci.ops.ops_health offbox` reads `/v1/status` and exits 0 when the verdict is green and the last cron run is fresh, 1 when red or stale, 2 when unreadable.
- `PYTHONPATH=.ci python3 -m rediacc_ci.ops.ops_health refresh --force` re-runs the local checks, runs the auto-safe repairs the config allows (`auto_repair` in `.ci/config/ops-health.json`, a daily attempt limit per code and machine) and posts the verdicts.
