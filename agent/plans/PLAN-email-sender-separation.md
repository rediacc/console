# PLAN: email sender separation -- customer and contact mail from contact@, system mail from alerts@ with urgent alerts instant and the rest in one daily digest, each to a shared list on the hostinger mail server
Status: approved -- operator rulings ASKED:2026-11-19 (worklist #45585ba5), recorded under ## Rulings
Depends-On: no-dep -- builds on landed account code and the live hostinger mail repo; no open box of another plan is a prerequisite
Owner: d778be9d
First-Seen: 2026-11-19
Priority: P1 -- a www contact-form message from a customer arrives From noreply@notify.rediacc.cloud into the same Rediacc-Notify folder as every refund, dispute and checkout-expiry alert, so a customer can go unanswered
Concurrency: parallel -- wave 1 T1, M1, E1 and K1 (4 writers, disjoint files; E1 waits on the S0 secret ids); wave 2 C1, D1 and R1 (C1 takes email.service.ts after M1 lands, D1 and R1 touch none of C1's files); then X1, X2, H0-H4, O1, P1 and LP-bench in the main checkout. PLAN-account-notices.md owns private/account/src/** broadly, but its only open box is a lead deploy box that edits no file (per PLAN-account-sidebar-redesign.md, Depends-On); block_plan_concurrency checks the rest at spawn
Owns: agent/plans/PLAN-email-sender-separation.md, private/account/src/services/email-transports/types.ts, private/account/src/services/email-transports/ses.ts, private/account/src/services/email-transports/smtp.ts, private/account/src/services/email.service.ts, private/account/src/types/env.ts, private/account/src/services/webhook.service.ts, private/account/src/services/cert-auto-renew.service.ts, private/account/src/services/delegation-cert-apply.service.ts, private/account/src/services/contact.service.ts, private/account/src/services/partner-application.service.ts, private/account/src/services/deal-registration.service.ts, private/account/src/services/sales-digest.service.ts, private/account/src/services/alert-digest.service.ts (new), private/account/src/services/email-capture.service.ts, private/account/src/services/reminder.service.ts, private/account/src/entry/cloudflare.ts, private/account/src/entry/node.ts, private/account/src/routes/root.ts, private/account/src/dto/notice.dto.ts, private/account/src/container.ts, private/account/src/app.ts, private/account/src/db/schema.ts, private/account/src/db/scope-registry.ts, private/account/src/db/shard-router.ts, private/account/drizzle/0091_alert_digest.sql (new; the next free number at write time), private/account/drizzle/meta/**, private/account/tests/integration/email-transport.test.ts, private/account/tests/integration/email-routing.test.ts (new), private/account/tests/integration/alert-classification.test.ts (new), private/account/tests/integration/alert-digest.test.ts (new), private/account/tests/integration/email-capture.test.ts, private/account/tests/integration/webhook.test.ts, private/account/tests/integration/contact.test.ts, private/account/tests/integration/sales-digest.test.ts, private/account/tests/integration/cert-auto-renew.test.ts, private/account/tests/integration/delegation-cert-apply.test.ts, private/account/wrangler.toml, private/account/docs/email/architecture.md, private/account/docs/infra/mail-server.md, .ci/rediacc_ci/deploy/set_account_worker_secrets.py, .ci/rediacc_ci/tests/test_deploy_set_account_worker_secrets.py, .ci/rediacc_ci/ops/deploy_bench.py, .ci/rediacc_ci/tests/test_ops_deploy_bench.py, .ci/rediacc_ci/ops/email_routing_drill.py (new), .ci/rediacc_ci/tests/test_ops_email_routing_drill.py (new), .github/workflows/cd-deploy-account.yml, .ci/config/bws-secret-map.json, .ci/config/secret-supply.json, .ci/config/env-manifest.json, .ci/config/python-env-registry.json, private/account (gitlink bump only)
Live-Proof: bench -- the edited sources are the account Worker (EmailService, the transports, the digest table and cron, a root route) under private/account/src and drizzle, the account surface bench admits; X2 drives the real send through bench and SES into the hostinger mail server
Worklist: #45585ba5, PR-TASK 79b7e92e

## Context (verified 2026-11-19 against the tree; a writer re-reads a line before relying on it)

1. **One sender for everything.** `createEmailService` takes `env.SMTP_FROM ?? env.AWS_SES_FROM` as the single `fromAddress` (private/account/src/services/email.service.ts:148-165), and every send passes it unchanged (:292). Production sets `AWS_SES_FROM` from the secret store (.ci/rediacc_ci/deploy/set_account_worker_secrets.py:222), bench defaults it to `noreply@notify.rediacc.cloud` (.ci/rediacc_ci/ops/deploy_bench.py:173, :342).
2. **No Reply-To and no headers.** `EmailTransport.send` takes `to, subject, html, text, from` and nothing else (private/account/src/services/email-transports/types.ts:1-12). The SES payload is `FromEmailAddress`, `Destination.ToAddresses` and `Content.Simple` only (private/account/src/services/email-transports/ses.ts:37-48); the SMTP one passes `from, to, subject, html, text` to nodemailer (private/account/src/services/email-transports/smtp.ts:61-67).
3. **Internal mail all goes to ROOT_EMAIL.** The constructor's `adminEmail` is `env.ROOT_EMAIL` (private/account/src/services/email.service.ts:161). Three human mails use it: the contact notification (:543-554), the partner application notification (:598-608) and the deal review notification (:723-739). `sendAdminAlert` prefixes `[Rediacc Alert]` and mails it too (:381-391). `sendSalesAlert` prefixes `[Rediacc Sales]` and mails `SALES_NOTIFY_EMAIL` (:398-408).
4. **ROOT_EMAIL is the root identity, not a mailbox setting.** Registration auto-promotes the matching user to root (private/account/src/routes/auth.ts:60), root tokens end when it changes (private/account/src/middleware/root-auth.ts:73-75), root grants key on it (private/account/src/routes/root-grants.ts:25-52), and bench seeds the root user from it (.ci/rediacc_ci/ops/deploy_bench.py:687-690). Repointing it at a list would break root; this plan adds keys instead.
5. **The alert call sites.** `sendAdminAlert` is called for a full refund (private/account/src/services/webhook.service.ts:610-615), a partial refund (:617-622), a paused subscription (:634-639), an expired checkout session (:695-700) and the four dispute events (:723-738, dispatched at :219-223); by the delegation cert apply path, on-prem (private/account/src/services/delegation-cert-apply.service.ts:747-753); and by the on-prem auto-renew loop for failure, expiry and countdown (private/account/src/services/cert-auto-renew.service.ts:382-403, called at :176, :192, :379) and recovery (:413-427). The sales digest calls `sendSalesAlert` once a day (private/account/src/services/sales-digest.service.ts:47-68).
6. **The contact path.** www posts to `/account/api/v1/contact/submit` (packages/www/src/utils/contact-submit.ts:5); the route sits behind a rate limit and the captcha (private/account/src/routes/contact.ts:16-40); `ContactService.submit` stores the row, mails the submitter a confirmation and mails the notification (private/account/src/services/contact.service.ts:22-54). The notification body already carries the submitter's address (private/account/src/email/templates/contact.ts:26-60), but a reply goes to noreply@.
7. **Every SES local part of notify.rediacc.cloud already sends.** The identity is the domain `notify.rediacc.cloud` in every region (private/account/rotation-manifest.json:274-286); the bench IAM policy allows `ses:FromAddress` `*@notify.rediacc.cloud` (private/account/tests/integration/rotation/rotate-guards.test.ts:190-195); the ops-health Worker already sends from `ai@notify.rediacc.cloud` and says why it can (workers/ops-health/wrangler.toml:15-18). The new senders need no SES change. The rotation tool's `fromIdentity: 'noreply@notify.rediacc.cloud'` (private/account/scripts/rotation/lib/config.ts:35) is the probe address, not an allowlist.
8. **The receiver files by domain.** Rspamd gives `notify.rediacc.cloud` -15 (private/account/docs/infra/mail-server.md, *Trusted sender allowlist*), and `muhammed@rediacc.com`'s Sieve files `from :contains "notify.rediacc"` into `Rediacc-Notify` (private/account/docs/email/architecture.md:206-208, :227-229; private/account/docs/infra/mail-server.md *Sieve routing*). That one rule is why contact mail and alerts look alike.
9. **The daily cron.** `0 3 * * *` runs `runNightlyReminders`, which runs the reminders and then the sales digest (private/account/src/entry/cloudflare.ts:494-518, :590-592); bench has the same crons (workers/account/wrangler.bench-eu.toml:51). Retention sweeps are one list (private/account/src/entry/cloudflare.ts:356-369). Node and on-prem run maintenance on timers (private/account/src/entry/node.ts:122-135; private/account/src/entry/on-premise.ts:249-290). A root trigger already exists for the sales digest because `/test` is dark on deployed Workers (private/account/src/routes/root.ts:108-114).
10. **One factory for wired services.** `configuredEmailService` adds the bench domain allowlist and the D1 capture sink (private/account/src/services/reminder.service.ts:50-62); the request path (private/account/src/app.ts:305) and the crons (private/account/src/entry/cloudflare.ts:509, :532) use it, while on-prem extras call `createEmailService` directly (private/account/src/services/onprem-extras.ts:62, :103). About 25 integration tests build `new EmailService(...)` positionally, so the constructor gains a trailing argument rather than a new shape.
11. **Bench mail is real and filtered.** Bench sends through SES only to `ALLOWED_EMAIL_DOMAINS = "rediacc.com,rediacc.io"` (workers/account/wrangler.bench-eu.toml:28; private/account/src/services/email.service.ts:263-274), turns the captcha off (:33) and copies each outgoing mail into `captured_emails` (private/account/drizzle/0058_captured_emails.sql), which has no sender or Reply-To column today.
12. **New table rules.** Every table is registered in exactly one scope list (private/account/src/db/scope-registry.ts:115-160, `capturedEmails` at :143) and in `SHARD_CLASS` (private/account/src/db/shard-router.ts:41, `capturedEmails: 'global'` at :135). The last migration is `0090_partner_customer_optional_org` (private/account/drizzle/meta/_journal.json). A sweep is one predicate `DELETE`, never an id list past D1's 100 bound parameters (private/account/CLAUDE.md, *Schema: per-tenant budget*).
13. **The secret plumbing a new key follows.** `SALES_NOTIFY_EMAIL` is the template: env schema (private/account/src/types/env.ts:154-157), the production push (.ci/rediacc_ci/deploy/set_account_worker_secrets.py:240, :386), the bench push (.ci/rediacc_ci/ops/deploy_bench.py:363), the workflow mapping (.github/workflows/cd-deploy-account.yml:313, :622), the store map (.ci/config/bws-secret-map.json:499), and the manifests (.ci/config/secret-supply.json:328-352, .ci/config/env-manifest.json:285, .ci/config/python-env-registry.json).
14. **Other system mail outside the Worker.** ops-health mails `OPS_ALERT_EMAILS` from `ai@notify.rediacc.cloud` (workers/ops-health/src/mail.ts:12-31, :80-92; deployed by .ci/rediacc_ci/ops/deploy_ops_health.py:50). SES delivery events go to `ses-events@rediacc.io`, a catch-all address (private/account/docs/email/architecture.md:230-233).
15. **The live mail repo.** Container `mail-server` with `roundcube` in the hostinger `mail` repo; `Rediaccfile` has `up / down / user_add / user_del`; `data/config/postfix-main.cf` is generated by the Rediaccfile to bind the renet loopback IP; `postfix-virtual.cf` holds the catch-alls (private/account/docs/infra/mail-server.md, *Repository layout*). The compose and Rediaccfile live only on the host, so H0 reads them before any edit. The repo template in this tree (packages/json/templates/messaging/docker-mailserver/docker-compose.yaml) names its container `mailserver` and is not the live file.
16. **renet rules that bind the DMS change.** `renet compose` forces `network_mode: host` and ignores `ports:`; a service reaches the outside only through `rediacc.tcp_ports` labels and the machine's infra TCP ports; the kernel rewrites every bind to the service's loopback IP inside the repo's /26 and blocks other repos; a raw `${SERVICE_IP}` baked into a persistent config is a validation error, and service names resolve through `/etc/hosts`; `sudo docker` and `docker compose` are refused in a Rediaccfile; `{SERVICE}_IP`, `REDIACC_NETWORK_ID` and `REDIACC_WORKING_DIR` are exported to Rediaccfile functions (packages/www/src/content/docs/en/rules-of-rediacc.md:52-91; packages/www/src/content/docs/en/services.md:63-80, :260-280; packages/www/src/content/docs/en/networking.md:17-25).

## Rulings (operator, ASKED:2026-11-19)

1. Separate senders, Reply-To and subject prefixes; more sender addresses than these two are fine. `contact@notify.rediacc.cloud` sends human and customer mail (the www contact form, sales); `alerts@notify.rediacc.cloud` sends system mail. Contact-form mail carries Reply-To set to the customer's address. Prefixes are `[Contact]` and `[System]`.
2. Email only: no Slack or other channel.
3. Urgent alerts go out at once; the rest go into one daily digest.
4. rediacc.io is infrastructure and system, rediacc.com is customers and humans. Contact mail goes to `contact@rediacc.com`, system mail to `alerts@rediacc.io`. Unaddressed mail already reaches muhammed through the catch-alls. Others join later, so each address is a shared list that can be edited later.
5. On the hostinger docker-mailserver, create real mailboxes `contact@rediacc.com` and `alerts@rediacc.io`, each with a Sieve `redirect :copy` recipient list, initially `muhammed@rediacc.com` and `muhammed@rediacc.io`. Enable ManageSieve (`ENABLE_MANAGESIEVE=1`, port 4190, loopback only), and "be careful about rediacc rules! We have special env vars for ip etc. See the existing config files and the code." The Sieve scripts stay on the volume, not versioned. muhammed's own `.dovecot.sieve` gets fileinto rules for the new senders, placed before the existing `from :contains "notify.rediacc"` rule.
6. Research recorded with the ruling: docker-mailserver has no shared-mailbox page; multi-target aliases are "not officially supported"; Sieve offers global before/after scripts and a per-user `.dovecot.sieve`; ManageSieve needs `ENABLE_MANAGESIEVE=1`. The live DMS runs Dovecot 2.4.1 with the file provisioner, has no contact or alerts account, and its catch-alls send `@rediacc.io` and `@rediacc.com` to muhammed@.

## Design 1: transport

`EmailTransport.send` gains `replyTo?: string` and `headers?: Record<string, string>`. SES maps `replyTo` to the top-level `ReplyToAddresses: [replyTo]` and `headers` to `Content.Simple.Headers: [{Name, Value}]`; SMTP passes both to nodemailer's `replyTo` and `headers`. An absent field leaves the payload byte-identical to today, so every transactional send is unchanged.

The one header is `X-Rediacc-Mail-Class: contact|system`, so a Sieve rule can key on the class as well as the From address. SES v2 `Simple` content headers are a claim about the vendor API: T1 quotes the AWS SendEmail reference in its report, and X2's real send through bench is the proof. If SES refuses the header, T1 drops it and the Sieve rules key on From alone; no second code path is kept.

## Design 2: mail classes and routing

`EmailService` gets a routing object, `MailRouting = { contact: { from, to }, alerts: { from, to }, tag }`, as one trailing constructor argument (Context 10), built by `createEmailService` from four new env keys:

| Key | Meaning | Cloud value | When absent |
|---|---|---|---|
| `CONTACT_FROM_EMAIL` | sender of contact-class mail | `contact@notify.rediacc.cloud` | the transactional `fromAddress` |
| `ALERTS_FROM_EMAIL` | sender of system-class mail | `alerts@notify.rediacc.cloud` | the transactional `fromAddress` |
| `CONTACT_NOTIFY_EMAIL` | recipient list for contact-class mail | `contact@rediacc.com` | `ROOT_EMAIL` |
| `ALERTS_NOTIFY_EMAIL` | recipient list for system-class mail | `alerts@rediacc.io` | `ROOT_EMAIL` |

The absent column exists for on-prem, whose installs set `ROOT_EMAIL` and one SMTP sender and nothing else (private/account/src/services/onprem-extras.ts:62, :103; private/account/src/entry/on-premise.ts:22). The cloud deploy refuses an empty value for all four (E1 adds them to `REQUIRED_NONEMPTY`), so the fallback never hides a cloud misconfiguration. `ROOT_EMAIL` keeps its identity role and is not read for cloud mail routing.

`tag` is `''` in production and ` bench` when `ENVIRONMENT` is `bench`, so a bench mail reads `[System bench] ...` in the shared lists.

Two methods replace the three ROOT_EMAIL mails, `sendAdminAlert` and `sendSalesAlert`:

- `sendContactMail({ kind, subject, html, text, replyTo })`: From `contact.from`, To `contact.to`, subject `[Contact<tag>] <subject>`, Reply-To the human the mail is about, header class `contact`.
- `sendSystemAlert({ kind, urgency: 'urgent' | 'digest', subject, body })`: From `alerts.from`, To `alerts.to`, subject `[System<tag>] <subject>`, no Reply-To, header class `system`. `urgent` sends now; `digest` appends to the alert queue when one is set (Design 3) and sends now when none is set. An urgent send that the transport refuses is also queued, so a failed alert reaches the next digest instead of vanishing.

Customer-facing mail keeps `fromAddress` (`noreply@`), no prefix and its customer recipient. Two customer mails gain `replyTo: contact.to`, because a customer who answers them is writing to a human: the contact confirmation and the partner application receipt.

The prefixes are code constants on mail to the team; no locale string changes, so no i18n box. The three human notifications keep their localized bodies (private/account/src/email/templates/contact.ts:26-60), which the email-template gate already covers.

### Every current mail kind

| Kind (EmailService method) | Caller | Class | Recipient | Urgency |
|---|---|---|---|---|
| contact notification (`sendContactNotificationEmail`) | private/account/src/services/contact.service.ts:43 | contact, Reply-To submitter | `CONTACT_NOTIFY_EMAIL` | instant |
| partner application notification | private/account/src/services/partner-application.service.ts:84 | contact, Reply-To applicant | `CONTACT_NOTIFY_EMAIL` | instant |
| deal review notification | private/account/src/services/deal-registration.service.ts:172 | contact, Reply-To the submitting partner user | `CONTACT_NOTIFY_EMAIL` | instant |
| sales digest (`sendSalesAlert`) | private/account/src/services/sales-digest.service.ts:65 | contact | `SALES_NOTIFY_EMAIL` (unchanged key; S0 sets it to `contact@rediacc.com`) | already daily |
| dispute opened, funds withdrawn | private/account/src/services/webhook.service.ts:746 | system | `ALERTS_NOTIFY_EMAIL` | urgent |
| dispute updated, funds reinstated | private/account/src/services/webhook.service.ts:746 | system | `ALERTS_NOTIFY_EMAIL` | digest |
| full refund (subscriptions revoked) | private/account/src/services/webhook.service.ts:611 | system | `ALERTS_NOTIFY_EMAIL` | urgent |
| partial refund | private/account/src/services/webhook.service.ts:620 | system | `ALERTS_NOTIFY_EMAIL` | digest |
| subscription paused | private/account/src/services/webhook.service.ts:639 | system | `ALERTS_NOTIFY_EMAIL` | digest |
| checkout session expired | private/account/src/services/webhook.service.ts:702 | system | `ALERTS_NOTIFY_EMAIL` | digest |
| delegation cert apply refused (on-prem) | private/account/src/services/delegation-cert-apply.service.ts:758 | system | `ALERTS_NOTIFY_EMAIL` | urgent |
| auto-renew failure, cert expired (on-prem) | private/account/src/services/cert-auto-renew.service.ts:403 | system | `ALERTS_NOTIFY_EMAIL` | urgent |
| auto-renew countdown, recovery (on-prem) | private/account/src/services/cert-auto-renew.service.ts:403, :432 | system | `ALERTS_NOTIFY_EMAIL` | digest |
| contact confirmation | private/account/src/services/contact.service.ts:42 | customer, Reply-To `CONTACT_NOTIFY_EMAIL` | submitter | instant |
| partner application received | private/account/src/services/partner-application.service.ts:81 | customer, Reply-To `CONTACT_NOTIFY_EMAIL` | applicant | instant |
| auth (magic link, reset, reauth, email change) | auth.service.ts, notification.service.ts | customer | the user | instant |
| security notices (new device, password, 2FA, sessions, lockout, API token, device code, invite accepted) | notification.service.ts | customer | the user | instant |
| billing (welcome, payment failed, downgraded, trial ending) | webhook.service.ts | customer | the customer | instant |
| digests (renewal, repo licence, backup health, terms) | notification.service.ts, reminder.service.ts | customer | org recipients | per PLAN-account-notices.md |
| org invitation, member removed | org.service.ts | customer | the invitee or member | instant |
| newsletter, lead magnet | newsletter.service.ts, routes/newsletter.ts | customer | the subscriber | instant |
| partner (invitation, approved, rejected, customer welcome, login link, eval licence, eval expiring, licence granted, deal submitted, deal status, exam, certificates, delegation expiring) | partner*.service.ts, eval-license.service.ts, exam.service.ts, notification.service.ts | customer | the partner or customer | instant |

The on-prem rows go urgent or instant regardless, since on-prem has no queue (Design 3); the auto-renew loop already sends at most one mail per state (private/account/src/services/cert-auto-renew.service.ts:159-196).

## Design 3: the daily digest

**Storage.** One table, `alert_digest_items` (`id` text pk, `created_at` text, `kind` text, `subject` text, `body` text, `sent_at` text null), indexed on `(sent_at, created_at)`. It is UNSCOPED (no org, user or store owns a system alert) and `global` in `SHARD_CLASS`. The same migration adds `from_address` and `reply_to` (both nullable) to `captured_emails`, so the bench drill can read what the routing did; `EmailCaptureSink.record` takes both.

**Queue.** `AlertDigestService` implements `AlertQueue.enqueue({ kind, subject, body })` with one insert. `configuredEmailService` sets it on every runtime except `ON_PREMISE_MODE` (private/account/src/types/env.ts:381), which keeps instant sends.

**Flush.** `AlertDigestService.flushIfDue(now)` mails one `[System<tag>] Daily digest: <n> alerts` when unsent rows exist, no row has a `sent_at` on the current UTC day, and `now` is at or after 03:00 UTC. The body groups by `kind` with a count and at most 20 lines per kind, oldest first, then the hidden remainder per kind. On a successful send it marks the rows with one predicate `UPDATE ... SET sent_at = ? WHERE sent_at IS NULL AND created_at <= ?` (no id list); a refused send marks nothing, so the next run retries. Callers: the Cloudflare `0 3 * * *` path in `runNightlyReminders` (private/account/src/entry/cloudflare.ts:494-518) and the node maintenance timer (private/account/src/entry/node.ts:122-135); the day guard makes repeated node ticks harmless. A root route `POST /admin/alert-digest/run` calls `flush(now)` without the day guard, the way `/admin/sales-digest/run` serves the drill (private/account/src/routes/root.ts:108-114).

**Retention.** `purgeSentAlertDigestItems` deletes rows whose `sent_at` is older than 30 days, one predicate `DELETE`, added to `runRetentionSweeps` (private/account/src/entry/cloudflare.ts:356-369). Unsent rows are never purged.

**Budget.** Not per-tenant: one row per system alert and one SES send a day, far inside the account Worker's subrequest budget.

## Design 4: secrets and deploy tooling

The four keys follow `SALES_NOTIFY_EMAIL` through every file in Context 13 and `AWS_SES_FROM` for the two senders. bench defaults them in `deploy_bench.py` beside `DEFAULT_SES_FROM` (`contact@notify.rediacc.cloud`, `alerts@notify.rediacc.cloud`, `contact@rediacc.com`, `alerts@rediacc.io`), and an explicit value wins, as the existing test does for the sender (.ci/rediacc_ci/tests/test_ops_deploy_bench.py:494-497). Production reads them from the store and refuses an empty value. S0 creates the store entries before E1 writes their ids.

## Design 5: the hostinger mail server

All steps run through `./rdc.sh --config eu-bench term connect mail@hostinger -c '...'` (the access the docs give with `eu-remote`, private/account/docs/infra/mail-server.md *Adding a new trusted sender domain*). `term connect` provisions no renet, and this plan changes no renet code.

1. **Survey first (H0).** Read the live `mail/docker-compose.yml`, `mail/Rediaccfile` (the `user_add` helper and the `postfix-main.cf` generation that binds the renet loopback IP), `data/config/postfix-virtual.cf`, `data/config/user-patches.sh`, `setup email list`, `doveconf -n` (protocols, `sieve` and `managesieve` sections) and both muhammed scripts. Every later step quotes the line it builds on.
2. **Mailboxes (H1).** `user_add contact@rediacc.com` and `user_add alerts@rediacc.io` through the Rediaccfile helper, with random passwords written to the store as `MAIL_CONTACT_PASSWORD` and `MAIL_ALERTS_PASSWORD`. The catch-all trap: Postfix reads `virtual_alias_maps` before mailbox delivery, and an `@rediacc.com` catch-all matches any address that has no alias entry of its own, real mailbox or not. If a real-delivery probe shows the catch-all taking the mail, H1 adds self-aliases (`contact@rediacc.com contact@rediacc.com`, `alerts@rediacc.io alerts@rediacc.io`) to `postfix-virtual.cf`, following whatever the survey shows for muhammed's own address.
3. **Recipient lists (H2).** Each mailbox gets one active Sieve script named `recipients`, stored with `doveadm sieve put -u <box> -a recipients` so it lands in the ManageSieve store rather than as a bare `.dovecot.sieve` file that ManageSieve would later move:

       require ["copy"];
       redirect :copy "muhammed@rediacc.com";

   (`muhammed@rediacc.io` for alerts). `:copy` keeps a copy in the shared mailbox as the archive. A later member is one more `redirect :copy` line, edited through ManageSieve or `doveadm sieve put`. The scripts stay on the volume (Ruling 5).
4. **Folders for muhammed (H3).** Before the existing `from :contains "notify.rediacc"` rule in `/var/mail/rediacc.com/muhammed/home/.dovecot.sieve` (and the `rediacc.io` mailbox's script, if H0 finds one), with `require ["fileinto", "mailbox"]` merged into the existing `require`:

       if address :is "from" "contact@notify.rediacc.cloud" { fileinto :create "Rediacc-Contact"; stop; }
       if address :is "from" ["alerts@notify.rediacc.cloud", "ai@notify.rediacc.cloud"] { fileinto :create "Rediacc-Alerts"; stop; }

   The step copies the script to `.dovecot.sieve.bak-<UTC stamp>` first and runs `sievec` on the new one before it takes effect. A redirected copy keeps its original From, so these rules file it on arrival.
5. **ManageSieve (H4), within the renet rules (Context 16).** `ENABLE_MANAGESIEVE=1` goes into the `mail-server` service's `environment` in `mail/docker-compose.yml`, applied with `renet compose -- up -d mail-server` from the repo directory, never `docker compose` and never `sudo`. No `ports:` entry, no `rediacc.tcp_ports` label and no machine infra TCP port is added, so port 4190 listens only on the service's renet loopback IP inside the repo's /26 and is unreachable from the internet and from other repos. If H0 shows Dovecot's `listen` set from the Rediaccfile the way `postfix-main.cf` is, the change follows that generator and uses `${MAIL_SERVER_IP}` at `up` time, never a hard-coded 127.x address in a stored file. Roundcube's `managesieve` plugin, if enabled, points at the service name `mail-server` port 4190, never an IP. The recreate costs a short IMAP reconnect; hostinger has no maintenance window.

## Tasks
- [ ] S0 [live] Secret-store entries: create `CONTACT_FROM_EMAIL`, `ALERTS_FROM_EMAIL`, `CONTACT_NOTIFY_EMAIL` and `ALERTS_NOTIFY_EMAIL` in bws with the Design 2 cloud values, bound to the production account deploy profile and the deploy-bench profiles; set `SALES_NOTIFY_EMAIL` to `contact@rediacc.com`; confirm `STRIPE_SANDBOX_WEBHOOK_SECRET` is bound for bench (R1's webhook legs need it). The new ids go to E1.
  Owns: none (store writes only). Accept: `bws_env exec --profile deploy-bench-eu -- python3 -c` printing the four names as set (values never printed), and the four ids recorded in the tick.
  Needs: none
- [x] T1 [writer] Transport (Design 1): `replyTo` and `headers` in ses.ts and smtp.ts, absent fields leaving the payload unchanged; the AWS SendEmail reference for `ReplyToAddresses` and `Content.Simple.Headers` quoted in the report.
  Owns: private/account/src/services/email-transports/ses.ts, private/account/src/services/email-transports/smtp.ts, private/account/tests/integration/email-transport.test.ts
  Depends on: none
  Needs: none
  Accept: `cd private/account && npx vitest run tests/integration/email-transport.test.ts && npm run typecheck && npm run lint` rc 0. Covered:
    - SES payload with `replyTo` carries `ReplyToAddresses: [addr]` and with `headers` carries `Content.Simple.Headers`;
    - SES payload with neither is byte-identical to today's (control: the existing payload assertion);
    - SMTP passes `replyTo` and `headers` to `sendMail`, and omits both when absent.
    (ticked) 2026-11-19T13:48:54Z by d778be9d: commit:bf300dcbf (private/account 11eadec); email-transport vitest 14 passed, tsc rc 0, lint rc 0; SES headers quoted from the AWS SendEmail and Message references
- [x] M1 [writer] Routing core (Design 2): the four env keys in env.ts; `replyTo`/`headers` in types.ts; `MailRouting`, the trailing constructor argument, `createEmailService` building it with the on-prem fallbacks and the bench tag; `sendEmail` options `{ from, replyTo, headers }` passed to the transport and to `EmailCaptureSink.record` (which gains optional `from` and `replyTo`); new `sendContactMail` and `sendSystemAlert` with the `AlertQueue` interface and `setAlertQueue`; the old methods stay until C1 moves the callers.
  Owns: private/account/src/types/env.ts, private/account/src/services/email-transports/types.ts, private/account/src/services/email.service.ts, private/account/tests/integration/email-routing.test.ts
  Depends on: none
  Needs: none
  Accept: `cd private/account && npx vitest run tests/integration/email-routing.test.ts tests/integration/email-capture.test.ts tests/integration/email-reserved-domain.test.ts && npm run typecheck && npm run lint` rc 0. Covered:
    - contact mail: From `CONTACT_FROM_EMAIL`, To `CONTACT_NOTIFY_EMAIL`, subject starts `[Contact] `, Reply-To the given address, header class `contact`;
    - system urgent: From `ALERTS_FROM_EMAIL`, To `ALERTS_NOTIFY_EMAIL`, `[System] `, sent at once;
    - system digest with a queue: enqueued, transport called 0 times; with no queue: sent at once;
    - urgent refused by the transport: enqueued as well;
    - `ENVIRONMENT=bench` gives `[System bench] ` and `[Contact bench] `;
    - absent keys: senders fall back to `fromAddress`, recipients to `ROOT_EMAIL` (the on-prem case);
    - a transactional send (`sendMagicLinkEmail`) still goes From `AWS_SES_FROM` with no Reply-To and no header (control: today's behaviour);
    - the allowlist and reserved-domain drops still apply to the new recipients.
    (ticked) 2026-11-19T13:48:56Z by d778be9d: commit:bf300dcbf (private/account 37b1676); email-routing/capture/reserved-domain vitest passed (53 with transport), tsc rc 0, lint rc 0
- [ ] E1 [writer] Deploy plumbing (Design 4): the four keys through set_account_worker_secrets.py (KEYS and REQUIRED_NONEMPTY), deploy_bench.py (defaults beside `DEFAULT_SES_FROM`), cd-deploy-account.yml (the bws mapping and the step env), bws-secret-map.json (S0's ids), secret-supply.json, env-manifest.json, python-env-registry.json and the secrets comment in private/account/wrangler.toml.
  Owns: .ci/rediacc_ci/deploy/set_account_worker_secrets.py, .ci/rediacc_ci/tests/test_deploy_set_account_worker_secrets.py, .ci/rediacc_ci/ops/deploy_bench.py, .ci/rediacc_ci/tests/test_ops_deploy_bench.py, .github/workflows/cd-deploy-account.yml, .ci/config/bws-secret-map.json, .ci/config/secret-supply.json, .ci/config/env-manifest.json, .ci/config/python-env-registry.json, private/account/wrangler.toml
  Depends on: S0 (the store ids)
  Needs: none
  Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_deploy_set_account_worker_secrets.py .ci/rediacc_ci/tests/test_ops_deploy_bench.py .ci/rediacc_ci/tests/test_deploy_bench_sales_notify.py -q && npm run ci -- --narrow` rc 0. Covered:
    - the production push refuses an empty `ALERTS_NOTIFY_EMAIL` (and each of the other three) with the guard message;
    - the bench payload carries the four defaults, and an explicit environment value wins;
    - no value reaches a child argv (the existing `test_no_secret_value_reaches_any_child_argv` still passes with the new keys).
- [x] K1 [writer] Docs: private/account/docs/email/architecture.md gains the sender table (Design 2), the digest (Design 3) and the receiver flow for the two lists; private/account/docs/infra/mail-server.md gains the two mailboxes, the ManageSieve setting and its loopback-only reasoning, the recipient-list edit recipe, and the new Sieve table rows. Written from the design; H0-H4 correct any line the live survey contradicts.
  Owns: private/account/docs/email/architecture.md, private/account/docs/infra/mail-server.md
  Depends on: none
  Needs: none
  Accept: `npm run check:ci-prose-style` rc 0 and both files name `contact@notify.rediacc.cloud`, `alerts@notify.rediacc.cloud`, `contact@rediacc.com`, `alerts@rediacc.io` and `ENABLE_MANAGESIEVE`.
    (ticked) 2026-11-19T14:11:18Z by d778be9d: commit:012b26114 (private/account 4e31056); required names present in both docs; check:ci-prose-style rc 0 after 3a secret-supply reword
- [x] C1 [writer] Classification (the Design 2 table): the three human notifications move to `sendContactMail` with their Reply-To; the contact confirmation and partner application receipt gain `replyTo: CONTACT_NOTIFY_EMAIL`; every `sendAdminAlert` caller moves to `sendSystemAlert` with its kind and urgency; the sales digest moves to the contact sender and prefix with `SALES_NOTIFY_EMAIL` as its recipient; `sendAdminAlert`, `sendSalesAlert` and the `[Rediacc Alert]`/`[Rediacc Sales]` prefixes are deleted from email.service.ts.
  Owns: private/account/src/services/email.service.ts, private/account/src/services/webhook.service.ts, private/account/src/services/cert-auto-renew.service.ts, private/account/src/services/delegation-cert-apply.service.ts, private/account/src/services/contact.service.ts, private/account/src/services/partner-application.service.ts, private/account/src/services/deal-registration.service.ts, private/account/src/services/sales-digest.service.ts, private/account/tests/integration/alert-classification.test.ts, private/account/tests/integration/webhook.test.ts, private/account/tests/integration/contact.test.ts, private/account/tests/integration/sales-digest.test.ts, private/account/tests/integration/cert-auto-renew.test.ts, private/account/tests/integration/delegation-cert-apply.test.ts
  Depends on: M1
  Needs: none
  Accept: `cd private/account && npx vitest run tests/integration/alert-classification.test.ts tests/integration/webhook.test.ts tests/integration/contact.test.ts tests/integration/sales-digest.test.ts tests/integration/admin-sales-digest-run.test.ts tests/integration/cert-auto-renew.test.ts tests/integration/delegation-cert-apply.test.ts && npm run typecheck && npm run lint && cd ../.. && npm run check:ci-i18n-account-email-templates` rc 0. Covered:
    - each webhook event in the table produces its class and urgency (dispute created urgent, dispute updated digest, full refund urgent, partial refund digest, paused digest, checkout expired digest);
    - a contact submission yields a contact mail with Reply-To the submitter and a confirmation From noreply@ with Reply-To `CONTACT_NOTIFY_EMAIL`;
    - partner application and deal review notifications carry Reply-To the applicant and the submitting user;
    - `grep -rn "sendAdminAlert\|sendSalesAlert" private/account/src` finds nothing (control: 9 call sites today).
    (ticked) 2026-11-19T14:52:22Z by d778be9d: commit:3b6ac4434 (private/account c6e35f5); 233 email tests passed with D1, tsc and lint rc 0; grep sendAdminAlert/sendSalesAlert empty
- [x] D1 [writer] Digest (Design 3): migration `alert_digest_items` plus the two `captured_emails` columns, schema.ts, scope-registry.ts (UNSCOPED), shard-router.ts (`global`), `AlertDigestService` with `enqueue`, `flushIfDue` and `flush`, the capture store writing `from_address` and `reply_to`, `configuredEmailService` setting the queue off on-prem, the Cloudflare daily cron and node timer callers, `purgeSentAlertDigestItems` in the retention sweeps, the container entry and app.ts wiring, and `POST /admin/alert-digest/run` with its response schema in notice.dto.ts.
  Owns: private/account/drizzle/0091_alert_digest.sql, private/account/drizzle/meta/**, private/account/src/db/schema.ts, private/account/src/db/scope-registry.ts, private/account/src/db/shard-router.ts, private/account/src/services/alert-digest.service.ts, private/account/src/services/email-capture.service.ts, private/account/src/services/reminder.service.ts, private/account/src/entry/cloudflare.ts, private/account/src/entry/node.ts, private/account/src/routes/root.ts, private/account/src/dto/notice.dto.ts, private/account/src/container.ts, private/account/src/app.ts, private/account/tests/integration/alert-digest.test.ts, private/account/tests/integration/email-capture.test.ts
  Depends on: M1 (the `AlertQueue` interface and the capture fields)
  Needs: none
  Accept: `cd private/account && npx vitest run tests/integration/alert-digest.test.ts tests/integration/email-capture.test.ts tests/integration/scope-audit.test.ts && npm run typecheck && npm run lint` rc 0. Covered:
    - three digest alerts and a flush send one mail listing all three, grouped by kind, and mark them sent; a second flush the same day sends 0;
    - `flushIfDue` before 03:00 UTC sends 0; after it, once per UTC day;
    - a refused send marks nothing and the next flush retries;
    - 150 unsent rows flush with one UPDATE and no id list (the >100-row batched test the budget rule asks for);
    - the sweep deletes sent rows older than 30 days and never an unsent row;
    - `ON_PREMISE_MODE` gets no queue, so a digest alert sends at once;
    - the capture row records `from_address` and `reply_to`;
    - `/admin/alert-digest/run` is refused without root and returns `{ items }` with it.
    (ticked) 2026-11-19T14:52:24Z by d778be9d: commit:3b6ac4434 (private/account 94fe803); alert-digest, email-capture, scope-audit, retention-cron passed in the 233; tsc and lint rc 0
- [x] R1 [writer] The bench drill `.ci/rediacc_ci/ops/email_routing_drill.py`, shaped like licence_expiry_drill.py (root login through `npm run login:bench`, the D1 read through `wrangler d1 execute`): (1) a contact submission from `drill+<UTC stamp>@rediacc.io`; (2) a `charge.dispute.created` webhook signed with `STRIPE_SANDBOX_WEBHOOK_SECRET`; (3) a signed `checkout.session.expired`; (4) `POST /admin/alert-digest/run` twice; (5) assertions on the `captured_emails` rows. Prints one JSON summary; rc 0 only when every assertion holds.
  Owns: .ci/rediacc_ci/ops/email_routing_drill.py, .ci/rediacc_ci/tests/test_ops_email_routing_drill.py
  Depends on: M1 (the subjects and senders it asserts)
  Needs: none
  Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ops_email_routing_drill.py -q` rc 0 against a fake HTTP and D1 layer. Covered:
    - the Stripe signature matches Stripe's `t=<ts>,v1=<hmac>` scheme (control: a tampered body fails verification in the test's own checker);
    - a missing sandbox webhook secret is a named error before any request;
    - a digest row present before step 4 fails the run (the checkout alert went out instantly);
    - a second digest run that mails anything fails the run.
    (ticked) 2026-11-19T14:52:26Z by d778be9d: commit:fbb61bc9d; pytest test_ops_email_routing_drill 17 passed, ruff rc 0; live run is X2
- [ ] X1 [lead] Local proof chain: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench` on the landed tree (migration applied, the four keys pushed).
  Local-route: deploy-bench -- the landed tree is deployed to bench eu from this checkout and its D1 migration applied
  Owns: none (runs only). Accept: deploy_bench rc 0 naming the deployed version, and `wrangler d1 execute` showing `alert_digest_items` and the two new `captured_emails` columns on bench eu.
- [ ] X2 [live] Real send through bench: `npm run login:bench -- --region eu`, then the R1 drill under `bws_env exec --profile bench-login-eu`.
  Owns: none. Accept: drill rc 0 with its JSON summary in the tick: the contact row From `contact@notify.rediacc.cloud`, Reply-To the drill address, subject `[Contact bench] ...`, To `contact@rediacc.com`; the confirmation From `noreply@notify.rediacc.cloud` with Reply-To `contact@rediacc.com`; the dispute row From `alerts@notify.rediacc.cloud`, `[System bench] ...`, To `alerts@rediacc.io`, within 60 s of the webhook; no checkout row before the digest run and one digest row after it; the second digest run mails 0.
  Needs: bench-deploy
- [ ] H0 [live] Survey the hostinger mail repo read-only (Design 5 step 1) and record each file's relevant lines in the tick; correct Design 5 here if the live files disagree.
  Owns: none. Accept: the tick quotes the `mail-server` environment block, the Rediaccfile's `user_add` and `postfix-main.cf` generator lines, the catch-all lines of `postfix-virtual.cf`, the `doveconf -n` protocols and sieve lines, and the head of both muhammed scripts.
  Needs: none
- [ ] H1 [live] Create `contact@rediacc.com` and `alerts@rediacc.io` with `user_add` (Design 5 step 2), passwords to the store; add the self-aliases if the probe needs them.
  Owns: none. Accept: `setup email list` shows both; a test mail sent from `muhammed@rediacc.io` to each lands in that mailbox's `cur/` or `new/` and not in muhammed's (a `find /var/mail/<domain>/<box> -newer` listing in the tick).
  Needs: none
- [ ] H2 [live] Recipient lists (Design 5 step 3): the `recipients` script on both mailboxes through `doveadm sieve put -a`.
  Owns: none. Accept: `doveadm sieve list -u contact@rediacc.com` and `-u alerts@rediacc.io` show `recipients ACTIVE`; a test mail to each arrives in the shared mailbox and in the muhammed mailbox it names.
  Needs: none
- [ ] H3 [live] muhammed's folders (Design 5 step 4): backup, the two rules before the `notify.rediacc` rule, `sievec` clean.
  Owns: none. Accept: `sievec` rc 0; the script shows the new rules above `from :contains "notify.rediacc"`; X2's contact mail sits in `Rediacc-Contact` and its dispute alert in `Rediacc-Alerts` of the muhammed mailboxes, and a mail from `noreply@notify.rediacc.cloud` still lands in `Rediacc-Notify`.
  Needs: none
- [ ] H4 [live] ManageSieve (Design 5 step 5): `ENABLE_MANAGESIEVE=1` in the `mail-server` environment, applied with `renet compose -- up -d mail-server`.
  Owns: none. Accept: inside the repo `ss -ltn` shows port 4190 on the service's 127.x renet address only; `timeout 5 bash -c '</dev/tcp/mail.rediacc.io/4190'` from this machine fails; a ManageSieve `LISTSCRIPTS` for `alerts@rediacc.io` over the service name returns `"recipients" ACTIVE`; IMAP on 993 answers after the recreate.
  Needs: none
- [ ] O1 [live] ops-health to the alerts list: set `OPS_ALERT_EMAILS` to `alerts@rediacc.io` in the store and redeploy with `python3 -m rediacc_ci.ops.deploy_ops_health`.
  Owns: none. Accept: deploy rc 0 and the ops-health `mailer` probe green with 1 recipient.
  Needs: none
- [ ] P1 [live] Production: an edge Worker deploy through `npm run release:local -- --channel edge --workers-only` after X2 and H1-H3, with the rollback version recorded; then one real contact submission on eu from a `@rediacc.io` address.
  Owns: none. Accept: release rc 0 with the rollback id in the tick; the contact mail arrives in `contact@rediacc.com` and, through the list, in muhammed's `Rediacc-Contact` folder, Reply-To the submitter, subject `[Contact] ...`.
  Needs: bench-deploy
- [ ] LP-bench [live] A fresh bench receipt after X2, recorded and ticked through `worklist.py --live-proof`.
  Accept: live-proof bench account-smoke

## Concurrency
- **Wave 0:** S0 (store entries) in the main checkout.
- **Wave 1:** T1, M1, K1, and E1 once S0 reports (4 writers). M1 alone owns types.ts and email.service.ts; T1 implements the new optional fields structurally, so the two compile in either landing order.
- **Wave 2:** C1 and D1 after M1, R1 after M1. C1 takes email.service.ts over from M1; D1 owns the capture store and every wiring file; no file is shared.
- **Live:** X1 after wave 2 lands; X2 after X1; H0 at any time, H1-H4 after H0; H3's last check after X2; O1 after H2; P1 after X2 and H1-H3; LP-bench after X2.

## Why there is no LP-hostinger box

The only hostinger live check is `renet-live`, whose surfaces are renet, cli-remote and cli (.ci/config/proof-tiers.json, `tiers.live.checks`). This plan touches none of them, and LP2 refuses a declared target that no touched surface admits (docs/agent-reference/plan-records.md, *Live proof*). The hostinger work is configuration on the live mail server, so H0-H4 carry their own evidence in each Accept line instead of a receipt.

## Risks

- **Catch-all capture.** A missing self-alias would send the new mailboxes' mail straight to muhammed, which looks like success. H1's Accept checks the shared mailbox's own maildir, not muhammed's.
- **Redirect and DMARC.** A redirected copy keeps `From: alerts@notify.rediacc.cloud`; delivery is local to the same server, so no external SPF check sees it, and the DKIM signature survives an unmodified body. H2's Accept is a real redirected delivery.
- **SES headers.** Design 1's header is a vendor claim until X2 sends it.
- **Bench mail in real lists.** Bench reaches the same lists, tagged `[... bench]` so a reader and a Sieve rule can tell it apart.
- **ManageSieve exposure.** The guarantee is the absence of any `rediacc.tcp_ports` label or infra port for 4190; H4 proves it from outside.

## Follow-ups (not boxes)

- Move the SES event SNS subscription from `ses-events@rediacc.io` to `alerts@rediacc.io` (an AWS console change; today the catch-all already delivers it).
- A global Sieve `before` script for list handling if many lists appear; one per-mailbox script is enough for two.
