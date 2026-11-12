# PLAN: enterprise tenants -- stand up acme.rediacc.cloud (bench) and acme.rediacc.io (on hostinger), close the routing and on-prem install gaps
Status: approved -- operator order 2026-11-12 "employ a parallel agent to complete the gaps in PLAN-enterprise-isolation.md ASAP"; operator rulings ASKED:2026-11-12T10:33Z folded in (bench first, acme owner and storage, on-prem as an rdc repo on hostinger plus a customer-grade rdc flow, delegation cert from bench); production X1/H1/X2 wait for an explicit operator go after bench is green
Owner: d778be9d
Updated: 2026-11-12
Depends-On: PLAN-enterprise-isolation.md, PLAN-product-domain-rename.md, PLAN-website-routing-and-mail.md#W1, PLAN-website-routing-and-mail.md#W8, PLAN-website-routing-and-mail.md#M3
Priority: P1 -- the Enterprise offer is unproven until a real tenant answers on each delivery form
Concurrency: parallel -- writers in each wave own disjoint files. PLAN-enterprise-isolation.md owns .ci/rediacc_ci/enterprise/** and .ci/rediacc_ci/__main__.py / core/run_verbs.py, but it has no open writer box, so block_plan_concurrency sees no live holder. Its Owns line should be narrowed to its live boxes when this plan is promoted.
Owns: agent/plans/PLAN-enterprise-tenants.md, .ci/rediacc_ci/ops/cf_dns.py, .ci/rediacc_ci/tests/test_ops_cf_dns.py, .ci/rediacc_ci/enterprise/cli.py, .ci/rediacc_ci/enterprise/onboarding.py, .ci/rediacc_ci/enterprise/dns.py, .ci/rediacc_ci/enterprise/lab.py, .ci/rediacc_ci/enterprise/lifecycle_adapters.py, .ci/rediacc_ci/tests/test_enterprise_dns.py, .ci/rediacc_ci/tests/test_enterprise_add.py, .ci/rediacc_ci/tests/test_enterprise_cli_wiring.py, .ci/rediacc_ci/tests/test_enterprise_lab.py, .ci/rediacc_ci/tests/test_enterprise_lifecycle_adapters.py, .ci/rediacc_ci/onprem/**, .ci/rediacc_ci/tests/test_onprem_*.py, .ci/rediacc_ci/__main__.py, .ci/rediacc_ci/core/run_verbs.py, .ci/rediacc_ci/tests/test_core_run_verbs.py, packages/cli/templates/elite/**, packages/cli/src/templates/embedded.generated.ts, packages/cli/src/commands/onprem.ts, packages/cli/src/services/onprem/**, packages/cli/src/config/command-planes.ts, packages/shared/src/cli-contract/data/i18n/*.json, packages/www/src/content/docs/en/on-premise.md, private/account/docs/enterprise.md, private/elite/BACKUP.md, private/renet/pkg/proxy/infra.go, private/renet/pkg/proxy/infra_test.go, private/account (gitlink bump only), private/elite (gitlink bump only), private/renet (gitlink bump only), packages/cli/src/commands/server.ts, packages/cli/src/services/server/**, packages/cli/src/utils/server-prompts.ts, packages/cli/src/commands/__tests__/server*.test.ts, packages/cli/src/services/account/subscription-password-auth.ts, private/account/src/routes/delegation.ts, private/account/src/routes/portal-delegation-certs.ts, private/account/src/types/api-token.ts, private/account/src/services/device-code.service.ts, private/account/src/services/onprem-free-tier.service.ts, private/account/src/routes/on-premise-status.ts, private/account/tests/integration/delegation-issue*.test.ts, private/account/tests/integration/onprem-free-tier*.test.ts, private/account/docs/runtime/on-premise-licensing.md, packages/shared/src/subscription/types.ts, packages/shared/src/subscription/constants.ts, packages/shared/src/subscription/onprem-free-tier.ts, private/renet/pkg/router/routes.go, private/renet/pkg/router/routes_test.go, private/renet/pkg/proxy/usercert.go, private/renet/pkg/proxy/usercert_test.go, private/renet/cmd/renet/proxy_cert.go, private/renet/cmd/renet/proxy_cert_test.go, private/renet/cmd/renet/setup_command.go, private/renet/cmd/renet/pkg_install_retry.go, private/renet/cmd/renet/job_commands.go, private/renet/cmd/renet/setup_offline_test.go, private/renet/pkg/i18n/locales/*.go, .ci/rediacc_ci/onprem/airgap.py, .ci/rediacc_ci/onprem/testca.py, .ci/rediacc_ci/tests/test_onprem_airgap.py, packages/cli/src/commands/machine/register.ts, packages/cli/src/services/machine/add-existing.ts
Live-Proof: bench, hostinger -- bench proves the signers, routing and the acme company. Hostinger proves the Elite repo acme-onprem behind its proxy with a bench-issued delegation cert. Production (X1/H1/X2) runs only on the operator's go.
First-Seen: 2026-11-12

## Context
The enterprise-isolation dependency is on its live boxes V1-V11, X1, H1 and X2, which run in this plan's order; every writer box there is ticked.

What is verified in the code:

- **No DNS step anywhere.** `enterprise add` runs `control-row, d1, configs, migrate, buckets, secrets, deploy, bootstrap, smoke, lookup, invite, audit` (.ci/rediacc_ci/enterprise/onboarding.py:42-55). None of these steps creates a DNS record.
  - Company Worker routes are declared in the generated toml as `{ pattern = "<host>/*", zone_name = "rediacc.cloud" }` (.ci/rediacc_ci/enterprise/configs.py:172; workers/account/enterprise.template.toml:8-12). So `wrangler deploy` creates the routes itself.
  - A Worker Route only fires when a proxied DNS record covers the host. With no `*.rediacc.cloud` record, the `smoke` step (.ci/rediacc_ci/enterprise/onboarding.py:604-613) cannot pass.
  - The shared Workers use `custom_domain = true` (workers/account/wrangler.eu.toml:7-9, workers/proxy/wrangler.eu.toml:10-12). Those records outrank a wildcard, so a wildcard cannot capture region hosts.
- **Universal SSL fits the host shape.** `names.hosts` (.ci/rediacc_ci/enterprise/names.py, the `hosts` function at the end of the file) gives one-label hosts: `<c>.rediacc.cloud` and `<c>-proxy.rediacc.cloud`. The free Universal certificate covers `*.rediacc.cloud` at exactly one level. Nothing checks that coverage before V4.
- **Removal leaves routes behind.**
  - `CloudflareTeardown.undeploy` deletes Worker scripts only (.ci/rediacc_ci/enterprise/lifecycle_adapters.py:290-311).
  - The V11 reader `leftovers` lists Workers, D1, buckets, the token and the control row, but not zone routes (.ci/rediacc_ci/enterprise/lab.py:1931-1960).
  - So a removed company's routes can outlive it, and V11 would not notice.
- **Known proof gaps, before any live run:**
  - V6 has no config-token driver (.ci/rediacc_ci/enterprise/lab.py:1026) and no E2E-envelope driver (.ci/rediacc_ci/enterprise/lab.py:1032).
  - V7 has no `console_command` (.ci/rediacc_ci/enterprise/lab.py:1173).
  - `proof replay` and `proof proxy` cannot reach rc 0 until these exist.
- **A bench company writes the production lookup.** The `lookup` step writes to KV namespace `7bbf3025...` (.ci/rediacc_ci/ops/enterprise_lookup.py:28; .ci/rediacc_ci/enterprise/onboarding.py:618) whether or not `--bench` is set. With owner `muhammed@rediacc.com` and no `--unlisted`, www lookup for `rediacc.com` would point at acme. acme must be `--unlisted`.
- **Stale doc.** private/account/docs/enterprise.md:21 says export and remove are `Unbound`. The code wires `la.CloudflareExporter` (.ci/rediacc_ci/enterprise/cli.py:223) and `la.CloudflareTeardown` (.ci/rediacc_ci/enterprise/cli.py:271).
- **V10 still waits on GitHub.** `git log origin/main -- .github/workflows/cd-enterprise-release.yml` returns nothing, so the workflow is not on main yet. V10 is the only box with no local path.
- **On-prem pieces already exist and can be reused:**
  - Elite compose: web, rustfs and rustfs-init on external networks; `pull_policy: never`; image `ghcr.io/rediacc/server:${TAG}` (private/elite/docker-compose.yml). It has no `UPSTREAM_URL` or `UPSTREAM_API_KEY` pass-through, so connected cert auto-renew is unwired there.
  - "The first account registered on the box takes the cert's subscription" (private/elite/BACKUP.md:40). That is a race if the box is public before the owner registers.
  - The drill already contains the install sequence: `elite_env` (.ci/rediacc_ci/drills/backup_elite_compose.py:133), `cert_base64` (:183), `ship_image` (docker save/load, :267), and register-then-login (:516-524).
  - Keys: `.ci/rediacc_ci/core/account.py:360 generate_crypto_keys`. Local image build: `ops/build_server.py onprem` produces `rediacc-server-onprem:dev`, with the production public key baked in as `UPSTREAM_PUBLIC_KEY_DEFAULT` (.ci/docker/web/entrypoint.sh:221-226).
  - Bench portal login with TOTP: `.ci/rediacc_ci/ops/login_bench.py:558 login`.
  - The delegation-cert route needs an org owner or admin session (private/account/src/routes/portal-delegation-certs.ts:46,66). The service allows one active cert per subscription.
- **renet supports what the on-prem repo needs:**
  - It routes custom domains from `rediacc.domain` or Traefik `Host()` labels (private/renet/pkg/compose/wrapper.go:763-800).
  - Its Traefik issues Let's Encrypt certificates through Cloudflare DNS-01 only, and only when `CF_DNS_API_TOKEN` is set (private/renet/pkg/proxy/infra.go:205-215).
  - renet injects `network_mode: host` and ignores `ports:`. So Elite's compose cannot run as a repo unchanged; it needs a renet variant that addresses rustfs by `${RUSTFS_IP}`.
  - Templates live in packages/cli/templates/<name> and are embedded by packages/cli/scripts/embed-templates.ts. They are applied with `rdc repo admin template apply <ref> --template <name>` (packages/cli/src/commands/repo-extended.ts:448-470).
  - `rdc machine setup <name>` installs renet (packages/cli/src/commands/machine/register.ts:352-370).
- **The rediacc.io zone has a wildcard.** `*.rediacc.io` is a CNAME to `www.rediacc.io` (private/account/docs/infra/cloudflare.md:143), so acme needs explicit records. Hostinger is 72.61.137.225 / 2a02:4780:c:e9b5::1 (private/account/docs/infra/cloudflare.md:120-121; private/account/docs/email/architecture.md:192-193).

Not verified, and owned by box Q0 below:
- That the wildcard record and routes are really absent.
- Universal SSL state on rediacc.cloud.
- Whether gitlab.rediacc.io is DNS-only with a Let's Encrypt certificate.
- Hostinger's proxy token scope, renet version and free disk.
- Whether an enterprise bws project exists.
- The operator's bench subscription plan and its active delegation certs.

## Rulings

Already ruled (ASKED:2026-11-12T10:33Z):
- R1. The cloud tenant is `acme.rediacc.cloud`, bench first. X1, H1 and X2 wait for an explicit go once bench is green.
- R2. acme's owner is muhammed@rediacc.com, with 10 GB storage.
- R3. On-prem `acme.rediacc.io` runs on hostinger as an rdc repo behind the existing proxy. The install becomes a customer-grade `rdc` flow: `rdc machine setup`, then rdc deploys Elite as a repo with domain, TLS, delegation cert and first account.
- R4. The on-prem delegation cert comes from bench.
- R5-R8 (ASKED:2026-11-12T11:15Z, 12:2xZ). R5: the verb is `rdc server install [machine] [--domain ...]` plus `rdc server status|upgrade|backup|licence`, not `rdc onprem`. Every value has a flag, and on a TTY a missing value is asked for, like packages/cli/src/utils/region-prompt.ts:17-24 (inquirer lazy-loaded). The prompts are: machine pick-or-add (`rdc machine setup` when renet is missing), domain and store domain with a DNS wait that never writes a customer zone, TLS method, and owner email (default: the logged-in account), with the owner created in the same run. R6: the licence comes from the logged-in config through a new token-scoped route that mints the cert and the auto-renew token. With no login, or a plan without delegation, the server starts on a built-in free tier and is upgraded later with `rdc server licence`; `--cert <file>` stays for offline installs. R7: Let's Encrypt HTTP-01 is renet's default resolver when no CF token is set, Cloudflare DNS-01 is used with a token, and bring-your-own cert/key is supported. Certificates are per-host only, never a wildcard; C3 becomes unconditional. R8: keys are generated on the box and never leave it, the install prints a one-time recovery bundle, and `rdc server backup` exports it later. Together these answer Q6-Q10 and Q12, and Q5 for customers. Q11 (whether the image is public) stays open.

Still open. Each has a recommended default; the short list for the operator is at the end.
- Q1. acme is `--unlisted`? Default yes, because of the lookup finding in Context.
- Q2. Which bench subscription issues the on-prem cert? Default: the operator's own account at bench.rediacc.cloud. It exists today and does not wait for V1. The alternative is acme's own ENTERPRISE subscription on acme.rediacc.cloud, which ties the two tenants together but waits for V1, the DNS step and V3/V4.
- Q3. V6/V7 drivers: build all three (config-token, E2E envelope, console command)? Default: build. If the config-store driver is too big for one writer, split it out, and record V6's config-token claim as open. That blocks only V6.
- Q4. Expose the Elite store for backups at `acme-store.rediacc.io`? Default yes. It is one more Traefik router, and the Host header passes through unchanged, so presigned SigV4 URLs stay valid.
- Q5. Where do on-prem secrets live? Default: a local state file at `~/.local/state/rediacc/onprem/<domain>/`, mode 0600, plus bws under an opaque name, because `ACCOUNT_CONFIG_SERVER_KEY` must be backed up (private/elite/BACKUP.md:44-46).
- Q6-Q12 are about the customer flow. They are listed at the end.

## Design

### Cloud: DNS, routes, Universal SSL

1. **`.ci/rediacc_ci/ops/cf_dns.py` (new).** One small Cloudflare DNS and TLS client, used by both tenants.
   - `ensure_record(zone, name, type, content, proxied, comment)` is idempotent: create, update in place, or leave unchanged.
   - `records(zone, name)` lists records.
   - `universal_ssl(zone)` returns `(enabled, hosts covered, status)` from `GET /zones/{id}/ssl/universal/settings` and `/ssl/certificate_packs?status=all`.
   - It reuses `cf_auth.curl_json`, as .ci/rediacc_ci/enterprise/lifecycle_adapters.py:490 already does, and the zone ids in .ci/rediacc_ci/ops/apply_cf_redirect_rules.py:34-37.
   - The CLI is `python -m rediacc_ci.ops.cf_dns ensure|show|ssl`. A record comment never carries a company label.
2. **`./run.sh enterprise dns ensure [--check]`** (new `enterprise/dns.py`, dispatched from cli.py):
   - Ensures one proxied `AAAA * -> 100::` in rediacc.cloud. That is the originless pattern for Worker-only hosts.
   - Refuses if it finds a conflicting `*` record of another type.
   - Asserts Universal SSL is enabled and active and covers `*.rediacc.cloud`.
   - `--check` changes nothing. Exit 1 names the failed claim.
3. **New onboarding step `route`, between `deploy` and `smoke`.**
   - It calls `dns.ensure(check_only=False)`. The wildcard is shared, so this is idempotent and cheap.
   - It then reads `/zones/{id}/workers/routes` and requires `<host>/*` mapped to `account-<c>` and `<c>-proxy` mapped to `proxy-<c>`. It reuses the matching rule from lab.py `routed_worker` (.ci/rediacc_ci/enterprise/lab.py:652-669) by importing it, not copying.
   - Companies that were already onboarded have no `route` row in their ledger, so a rerun runs only that step.
4. **Removal.** `CloudflareTeardown.undeploy` also deletes the zone routes whose `script` is one of the company's Workers. `lab.leftovers` reports a remaining route as the kind `zone route`, never by name.
5. **Turnstile.** V4 checks that the `rediacc-console` widget's domains cover `rediacc.cloud`. If not, V4 fails, and box LT1 adds the domain through the widget API (deploy/turnstile_drift.py names the widget).

### On-prem: Elite as a renet repo

1. **Template `packages/cli/templates/elite/`.** This is the unit both drivers deploy. Files: `Rediaccfile`, `docker-compose.yml`, `template.json`, `secrets.env.example`, `README.md`.
   - The compose is the renet form of private/elite/docker-compose.yml:
     - No `networks` and no `ports`.
     - `CONFIG_R2_ENDPOINT` and `ACCOUNT_BACKUP_S3_ENDPOINT` set to `http://${RUSTFS_IP}:9000`, and `rustfs-init` addresses the store the same way.
     - The web service carries `rediacc.service_port=80` and `rediacc.domain=${ELITE_DOMAIN}`, with `ENABLE_HTTPS=false`, since Traefik terminates TLS.
     - If Q4 is accepted, an `ELITE_STORE_DOMAIN` router to rustfs port 9000.
     - `PUBLIC_SITE_URL=https://${ELITE_DOMAIN}`, and `ACCOUNT_BACKUP_S3_PUBLIC_ENDPOINT=https://${ELITE_STORE_DOMAIN}`.
     - `UPSTREAM_URL` and `UPSTREAM_API_KEY` passed through, so connected renewal works when set.
     - The image is `${ELITE_IMAGE:-ghcr.io/rediacc/server:${TAG}}`.
   - The Rediaccfile `up()` does four things in order:
     - Sources `secrets.env`.
     - Refuses, naming the variable, if `ELITE_DOMAIN` or the enrolment keys are missing.
     - Runs `docker load -i images/server.tar` when that file exists and the tag is absent. This is the local-first image path.
     - Runs `renet compose -- up -d`.
   - It also has `down()` and `info()`. `health()` checks that `/health` answers.
   - Drift guard: `.ci/rediacc_ci/tests/test_onprem_template_parity.py` requires the web service's env key set in the template to equal Elite's, minus the networking keys. If Elite adds a variable, this test fails.
2. **`./run.sh onprem install`** (new `.ci/rediacc_ci/onprem/install.py`). This is the fast operator path, and the reference sequence the `rdc` verb will port. It is resumable through a step ledger in the state dir:
   - `preflight`: `./rdc.sh --config <cfg> machine status <m>`; renet present; the repo name is free or already ours.
   - `dns`: `cf_dns.ensure_record` with A and AAAA, DNS-only, for the domain and the store domain, pointing at the machine's public IPs. This step only acts on zones we own; otherwise it prints the records and verifies them by resolution.
   - `image`: run `build_server onprem` if `rediacc-server-onprem:dev` is missing, then `docker save` into the work dir. With `--image-ref`, nothing is built and the repo pulls instead.
   - `keys`: `generate_crypto_keys(strict=True)` plus the RustFS pair and the config server key, written to the state dir with 0600, then bws.
   - `cert`: the upstream is `bench`. Open a portal session (`login_bench.login`) and `POST /account/api/v1/portal/delegation-certs` for the chosen subscription with the delegated public key. An existing active cert for the same key is reused; one for another key is refused, naming the revoke command. Uses `cert_base64` from the drill.
   - `repo`: `repo create <repo> -m <m> --size <n>` if absent.
   - `files`: `repo admin template apply <repo> --template elite`, then `repo sync upload` of `secrets.env` and `images/` with `--verify`.
   - `up`: `repo up <repo>`.
   - `wait`: `https://<domain>/health` answers 200, and the certificate's SAN covers the domain.
   - `owner`: `POST /auth/register` and `/auth/login` as the owner, as the drill does (:516-524). Then assert the subscription equals the cert's (drill `cert_subscription`, :196). This closes the first-account race inside the same run.
   - `record`: write a no-secrets summary.
   - It never touches another repo, and writes go only through `eu-bench`, per the hostinger rules. It refuses `--config eu-remote` for anything but reads.
3. **Customer-grade `rdc onprem` (wave 3, after the hostinger tenant is green).**
   - `rdc onprem install <machine> --domain <d> [--store-domain <d>] [--repo account] [--size 20G] [--owner <mail>] (--cert <file> | --upstream <url>) [--image <ref>]` runs the same steps in TS. If renet is missing, it runs `machine setup` first, after asking.
   - `rdc onprem status|upgrade|cert` round it out. `upgrade` is `repo fork` (rollback point), new image, `repo up`.
   - Keys are generated on the box (Q8).
   - DNS is never written for a customer domain: the verb prints the records it needs and waits for them to resolve.
4. **TLS for customers whose DNS is not on Cloudflare** (Q7). Add an HTTP-01 (`tlschallenge`) resolver to renet's Traefik as the fallback when no `CF_DNS_API_TOKEN` is set (private/renet/pkg/proxy/infra.go:205-215). Live proof on hostinger, after a release.

### Doc fix

In private/account/docs/enterprise.md:
- Replace line 21: export and remove are wired to `CloudflareExporter` and `CloudflareTeardown` (.ci/rediacc_ci/enterprise/cli.py:223, :271), and need Cloudflare and R2 credentials plus `--bws-project`.
- Add rows for the `dns` verb and the `route` step.
- Add a pointer to `./run.sh onprem`.

In private/elite/BACKUP.md, add a pointer to the renet-repo install.

## Tasks

### Wave 0

- [x] Q0 [live] Read-only survey. Changes nothing; each finding is recorded under this box.
  - Cloudflare, rediacc.cloud: `python -m rediacc_ci.ops.apply_cf_redirect_rules --dry-run --zone rediacc.cloud` reaches the zone. Then use the API (under `bws_env exec --profile deploy-bench`) to list `*` records, `/workers/routes`, Universal SSL settings and cert packs.
  - Cloudflare, rediacc.io: records for `acme`, `acme-store` and `gitlab`.
  - TLS: `openssl s_client -connect gitlab.rediacc.io:443` issuer.
  - Hostinger: `./rdc.sh --config eu-bench machine status hostinger` (renet version, free disk) and `./rdc.sh --config eu-bench repo list -m hostinger`, saved as the baseline.
  - bws: the enterprise project id.
  - Bench: `npm run login:bench`, then the operator subscription's plan and active delegation certs.
  - Owns: none.
  - Accept: `./rdc.sh --config eu-bench machine status hostinger` rc 0, and the findings recorded here.
    (ticked) 2026-11-12T11:23:18Z by d778be9d: read-only survey by agent a96b35961c3384251, findings in its investigation row; machine status hostinger rc 0. DEPS-WAIVED: read-only survey that reads state and changes nothing

### Wave 1: writers, disjoint

- [x] E1 [writer] `ops/cf_dns.py`: `ensure_record`, `records`, `universal_ssl`, and its CLI, tested with a recording transport. Tests cover create, no-op, update, conflict refused, proxied flag, and a comment carrying no label.
  - Owns: .ci/rediacc_ci/ops/cf_dns.py (new), .ci/rediacc_ci/tests/test_ops_cf_dns.py (new).
  - Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_ops_cf_dns.py` rc 0.
    (ticked) 2026-11-12T11:21:02Z by d778be9d: commit:8d3cf5eafc cf_dns client; pytest test_ops_cf_dns.py 16 passed rc 0
- [x] E2 [writer] Lab and teardown gaps:
  - Teardown deletes the company's zone routes, and `leftovers` reports `zone route`.
  - V6 `config-token` driver (store setup with elevated session and CEK slots) and `e2e-envelope` driver (a request sealed to the company's X25519 key through `POST /account/api/v1/tunnel`).
  - V7 `console_command`.
  - The three `not built yet` raises (.ci/rediacc_ci/enterprise/lab.py:1026, 1032, 1173) are gone.
  - Owns: .ci/rediacc_ci/enterprise/lab.py, .ci/rediacc_ci/enterprise/lifecycle_adapters.py, .ci/rediacc_ci/tests/test_enterprise_lab.py, .ci/rediacc_ci/tests/test_enterprise_lifecycle_adapters.py.
  - Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_enterprise_lab.py .ci/rediacc_ci/tests/test_enterprise_lifecycle_adapters.py` rc 0, and `grep -c "not built yet: V[67]" .ci/rediacc_ci/enterprise/lab.py` prints 0.
    (ticked) 2026-11-12T11:21:03Z by d778be9d: commit:2f9bee93c0 + 4fa93b832f; enterprise suites 296 passed rc 0; no "not built yet: V[67]" left; bench proof owed in V6/V7
- [x] P1 [writer] The `elite` template as described in Design, the regenerated embedded catalog, and the parity test against private/elite/docker-compose.yml.
  - Owns: packages/cli/templates/elite/** (new), packages/cli/src/templates/embedded.generated.ts, .ci/rediacc_ci/tests/test_onprem_template_parity.py (new).
  - Accept: `(cd packages/cli && npx tsx scripts/embed-templates.ts) && git diff --exit-code packages/cli/src/templates/embedded.generated.ts` rc 0 after the commit, and `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_onprem_template_parity.py` rc 0, and `bash -n packages/cli/templates/elite/Rediaccfile` rc 0.
    (ticked) 2026-11-12T11:21:23Z by d778be9d: commit:4db510a659 elite template; parity test 2 passed rc 0; catalog regenerates with no diff; machine run owed in HO1
- [x] L1 [writer] The doc fix as described in Design: enterprise.md line 21, the `dns` and `route` rows, the onprem pointer, and the BACKUP.md pointer.
  - Owns: private/account/docs/enterprise.md, private/elite/BACKUP.md.
  - Accept: `grep -c "Unbound" private/account/docs/enterprise.md` prints 0, and `npm run -s check:ci-prose-style` rc 0.
    (ticked) 2026-11-12T11:21:05Z by d778be9d: commit:125b737065 (account 2675ee0, elite 0bd5694); grep -c Unbound prints 0; prose-style rc 0

### Wave 2: writers, after E1 and P1 land

- [x] E3 [writer] `enterprise/dns.py` and the `./run.sh enterprise dns ensure [--check]` dispatch in cli.py. The onboarding `route` step goes between `deploy` and `smoke`, using `cf_dns` and lab's route matcher.
  - Owns: .ci/rediacc_ci/enterprise/dns.py (new), .ci/rediacc_ci/enterprise/cli.py, .ci/rediacc_ci/enterprise/onboarding.py, .ci/rediacc_ci/tests/test_enterprise_dns.py (new), .ci/rediacc_ci/tests/test_enterprise_add.py, .ci/rediacc_ci/tests/test_enterprise_cli_wiring.py.
  - Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_enterprise_dns.py .ci/rediacc_ci/tests/test_enterprise_add.py .ci/rediacc_ci/tests/test_enterprise_cli_wiring.py` rc 0.
    (ticked) 2026-11-12T11:59:28Z by d778be9d: commit:51f22f73d1 enterprise dns verb and route step; pytest enterprise suites 440 passed rc 0; live LD1 owed
- [x] P2 [writer] `./run.sh onprem install|status`:
  - The resumable steps as described in Design, importing `elite_env`, `cert_base64`, `ship_image`, `generate_crypto_keys` and `login_bench.login` rather than copying them.
  - The `onprem` row in `__main__.py`, with `dns` added to the `enterprise` summary at `.ci/rediacc_ci/__main__.py:106-110`, and help in run_verbs.py.
  - Refuses mutating calls through `eu-remote`.
  - Owns: .ci/rediacc_ci/onprem/** (new), .ci/rediacc_ci/tests/test_onprem_install.py (new), .ci/rediacc_ci/__main__.py, .ci/rediacc_ci/core/run_verbs.py, .ci/rediacc_ci/tests/test_core_run_verbs.py.
  - Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_onprem_install.py .ci/rediacc_ci/tests/test_core_run_verbs.py .ci/rediacc_ci/tests/gates/test_gate_run_sh.py` rc 0.
    (ticked) 2026-11-12T12:32:08Z by d778be9d: commit:8b7ae80a62 onprem install + bws backup; pytest rc 0; live HO1 owed
  (corrected 2026-11-12T13:15Z) (operator ruling 2026-11-12, single install path) Superseded by C7: `rdc server install` (locally `./rdc.sh server install`) is the only install engine for customers and for us. C7 absorbs the licence certificate through `POST /account/api/v1/delegation/issue`, the optional `--bws-project` key backup (ours only; customers keep keys on the box) and the optional DNS write for zones we own. `.ci/rediacc_ci/onprem/install.py`, its tests and the `./run.sh onprem` verb are deleted; the lab helpers move to `.ci/rediacc_ci/lab/`.

### Bench queue: one sequential runner, starting after Q0

- [ ] V1 [live] (PLAN-enterprise-isolation V1) Signers. This needs no new writer.
  - Accept: `./run.sh enterprise proof signer --bench` rc 0.
- [ ] LD1 [live] After E3: create the wildcard and check Universal SSL.
  - Accept: `./run.sh enterprise dns ensure` rc 0, then `./run.sh enterprise dns ensure --check` rc 0.
- [ ] V3 [live] Run the add proof.
  - Accept: `./run.sh enterprise proof add --bench` rc 0.
- [ ] V4 [live] Run the routing proof. If the Turnstile claim fails, LT1 fixes it.
  - Accept: `./run.sh enterprise proof routing --bench` rc 0.
- [ ] LT1 [live] Only if V4 names Turnstile: add `rediacc.cloud` to the `rediacc-console` widget domains through the API, then rerun V4.
  - Accept: `./run.sh enterprise proof routing --bench` rc 0.
- [ ] T1 [live] The acme cloud tenant:
  - Run: `bws_env exec --profile deploy-bench -- ./run.sh enterprise add acme --region eu --owner muhammed@rediacc.com --storage-gb 10 --unlisted --bench --bws-project <Q0 id>`.
  - The owner invitation is captured on bench. Read the link with `login_bench mail_token`, then the operator signs in.
  - Accept: `./run.sh enterprise list --bench` rc 0 naming acme `active`, and `curl -s -o /dev/null -w '%{http_code}' https://acme.rediacc.cloud/` and `https://acme-proxy.rediacc.cloud/` each below 500 with a valid certificate (curl without `-k`).
- [ ] V2 [live] Region loss. acme in eu is briefly unavailable during this, which ruling 1 accepts.
  - Accept: `./run.sh enterprise proof region-loss --bench` rc 0.
- [ ] V6 [live] After E2.
  - Accept: `./run.sh enterprise proof replay --bench` rc 0.
- [ ] V7 [live] After E2.
  - Accept: `./run.sh enterprise proof proxy --bench` rc 0.
- [ ] V5 [live] Rings.
  - Accept: `./run.sh enterprise proof release --bench` rc 0.
- [ ] V8 [live] Cost.
  - Accept: `./run.sh enterprise proof cost --bench` rc 0.
- [ ] V11 [live] Remove. Now also checks zone routes.
  - Accept: `./run.sh enterprise proof remove --bench` rc 0.
- [ ] V9 [live] Renet order on a local fleet VM (`npm run vm:check` first).
  - Accept: `./run.sh enterprise proof renet --bench` rc 0.
- [ ] V10 [live] GitHub path. This is the only box that waits on GitHub: it runs after cd-enterprise-release.yml reaches origin/main through the normal merge.
  - Accept: `./run.sh enterprise proof github --bench` rc 0.
- [ ] F* [writer] Fix-forward boxes, opened under this plan for each broken claim a V box prints, owning only the file the claim names.
  - Accept: the failing proof verb rc 0.

### Hostinger queue: in parallel with bench, after Q0, P1 and P2

- [ ] HO1 [live] Elite on hostinger:
  - Run: `./run.sh onprem install hostinger --config eu-bench --repo acme-onprem --size 20G --domain acme.rediacc.io --store-domain acme-store.rediacc.io --upstream bench --owner muhammed@rediacc.com`.
  - Accept: `curl -sf https://acme.rediacc.io/health` rc 0 with a valid certificate. `./run.sh onprem status acme.rediacc.io` rc 0, reporting cert-status `bootstrapMode=false` and the subscription equal to the cert's. `./rdc.sh --config eu-bench repo list -m hostinger` shows Q0's baseline plus `acme-onprem` only.
  (corrected 2026-11-12T13:15Z) (operator ruling 2026-11-12, single install path) The command is `./rdc.sh --config eu-bench server install hostinger --repo acme-onprem --size 20G --domain acme.rediacc.io --store-domain acme-store.rediacc.io --tls cloudflare --owner muhammed@rediacc.com --bws-project <id> --yes` (hostinger keeps its Cloudflare DNS-01 proxy). Accept unchanged, with `./rdc.sh --config eu-bench server status acme.rediacc.io` in place of `./run.sh onprem status`.
- [ ] HO2 [live] A machine licensed by the box. On a local ops VM, log in to `https://acme.rediacc.io` and `repo create`. The licence carries the box's delegation cert. If Q4 is accepted, also take one snapshot into `acme-store.rediacc.io`.
  - Accept: `./rdc.sh repo create hoprobe -m <ops-vm> --size 1G` rc 0 under the acme.rediacc.io login, with `drills.backup_elite_compose.licence_problem` empty on the issued licence.

### Wave 3: customer-grade flow, after HO1 is green and Q6-Q12 are answered

- [x] C1 [writer] `rdc onprem install|status|upgrade|cert` in TS, porting P2's steps. Keys are generated on the box. `--cert` and `--upstream` per Q9. Customer DNS is printed and verified, never written. i18n keys in every locale.
  - Owns: packages/cli/src/commands/onprem.ts (new), packages/cli/src/services/onprem/** (new), packages/cli/src/config/command-planes.ts, packages/shared/src/cli-contract/data/i18n/*.json, packages/cli/src/commands/__tests__/onprem*.test.ts (new).
  - Accept: `(cd packages/cli && npx vitest run src/commands/__tests__/onprem)` rc 0, and `npm run check:ci-cli-contract` rc 0.
  (corrected 2026-11-12T11:58Z) Superseded by C7 (R5): the verb is `rdc server`, so onprem.ts and services/onprem/** are never created. Do not run C1; tick it as superseded when C7 ticks. Its shared Owns (command-planes.ts, i18n) pass to C7.
    (ticked) 2026-11-12T14:30:29Z by d778be9d: superseded by C7 (correction 2026-11-12T11:58Z): commit:6c48953db0 rdc server install|status|upgrade|backup|licence, server vitest rc=0, cli-contract rc=0
- [ ] C2 [writer] Public docs: an "Install with rdc" section in on-premise.md.
  - Owns: packages/www/src/content/docs/en/on-premise.md.
  - Accept: `npm run -s check:ci-prose-style` rc 0.
  (corrected 2026-11-12T11:58Z) The section documents `rdc server install|status|upgrade|backup|licence`, the prompts, the three TLS methods, the free tier and its upgrade, and saving the recovery bundle. It runs after C7.
  (corrected 2026-11-12T12:55Z) Also documents:
      - existing machines first;
      - the air-gapped flow: bundle, prerequisites (Q14), the two-trip licence, BYO TLS/CA, LAN DNS, time sync;
      - updates: CLI, renet, template VERSION, image, and air-gapped via a new bundle.
      Runs after C11.
- [x] C3 [writer] Only if Q7 is ruled yes: an HTTP-01 resolver when `CF_DNS_API_TOKEN` is empty.
  - Owns: private/renet/pkg/proxy/infra.go, private/renet/pkg/proxy/infra_test.go.
  - Accept: `(cd private/renet && go test ./pkg/proxy/...)` rc 0.
  (corrected 2026-11-12T11:58Z) Unconditional (R7). With `CF_DNS_API_TOKEN` set, keep DNS-01 (private/renet/pkg/proxy/infra.go:205-215). Otherwise configure the `letsencrypt` resolver with HTTP-01. The IPv6 entrypoints are separate (private/renet/pkg/proxy/infra.go:197-199), so the test must show the challenge answering on IPv6 too; if one httpChallenge entrypoint cannot cover both, use TLS-ALPN-01. The cases at private/renet/pkg/proxy/infra_test.go:307-334 that assert "no resolver without token" flip. Ships in the same renet release as C6, because routes.go still asks for wildcard SANs.
    (ticked) 2026-11-12T12:32:29Z by d778be9d: commit:012193560e renet 9e612a4b 7aace2ca TLS-ALPN-01 + router hint; go test pkg/proxy rc 0
- [ ] CL1 [live] On a fresh local ops VM, run `rdc machine setup <vm>` and then `rdc onprem install <vm> --domain <ops-vm test name> --cert <file>`.
  - Accept: the same health and status checks as HO1.
  (corrected 2026-11-12T11:58Z) After C7 and the C3/C6 renet release, the command is `rdc server install <vm> --domain <name> --cert <file> --tls byo --tls-cert <crt> --tls-key <key> --owner <mail> --yes`, which proves the offline path and bring-your-own TLS. Accept: `rdc server status <domain>` rc 0 with bootstrapMode=false and the subscription equal to the cert's, and `curl --cacert <ca> -sf https://<domain>/health` rc 0.
  (corrected 2026-11-12T12:55Z) Proves the brought machine, online, on ops VM .11, which is absent from the `onprem-lab` config.
      - Run `./rdc.sh --config onprem-lab server install --ip 192.168.111.11 --user $USER --name lab-brought --domain elite-lab.ops.test --store-domain elite-lab-store.ops.test --tls byo --tls-cert <crt> --tls-key <key> --tls-ca <ca> --licence free --owner <mail> --no-dns-wait --yes` (certs from C12 testca).
      - Accept: `./rdc.sh --config onprem-lab machine list -o json` names lab-brought at 192.168.111.11; `grep -ci tofu <install log>` prints 0; `server status elite-lab.ops.test` rc 0 reporting `tier: free`; `curl --cacert <ca> --resolve elite-lab.ops.test:443:192.168.111.11 -sf https://elite-lab.ops.test/health` rc 0.
      - The offline `--cert` claim moves to CL4.
  (corrected 2026-11-12T13:15Z) (operator ruling 2026-11-12, single install path) Unchanged command form: `./rdc.sh --config onprem-lab server install ...` as in the 13:5xZ correction; the test CA comes from `python -m rediacc_ci.lab.testca`.

- [x] C4 [writer] Token-scoped delegation issue (R6). Today every portal route is session-only (private/account/src/routes/portal-delegation-certs.ts:42) and token auth exists only for `/delegation/renew` (private/account/src/routes/delegation.ts:25).
  - Add a new privileged scope `delegation:issue` to types/api-token.ts. Owners and admins only, granted by the device login next to backup:manage (private/account/src/services/device-code.service.ts:358). `delegation:renew` stays unmintable (private/account/src/types/api-token.ts:78).
  - Add `POST /delegation/issue` in delegation.ts behind `apiTokenAuth('delegation:issue')`, taking `{subscriptionId, delegatedPublicKey, validDays?}`. It returns `{cert, id, effectiveDays, autoRenewToken}` in one call, sharing a helper pulled out of the auto-renew-token handler (private/account/src/routes/portal-delegation-certs.ts:258).
  - An active cert for the same key is returned again (idempotent). One for another key gives 409, naming the cert id to revoke.
  - Add a plan gate: `PLAN_ALLOWS_DELEGATION_CERT` in constants.ts, with FREE false by default. Today no plan is refused (private/account/src/services/delegation-cert.service.ts:202; packages/shared/src/subscription/constants.ts:354-371).
  - Owns: private/account/src/routes/delegation.ts, private/account/src/routes/portal-delegation-certs.ts, private/account/src/types/api-token.ts, private/account/src/services/device-code.service.ts, packages/shared/src/subscription/types.ts, packages/shared/src/subscription/constants.ts, private/account/tests/integration/delegation-issue*.test.ts (new).
  - Accept: `(cd private/account && npx vitest run tests/integration/delegation-issue)` rc 0. The cases cover: token without the scope 403, member 403, FREE plan 402/403, same key idempotent, other key 409, and a session cookie alone rejected.
    (ticked) 2026-11-12T12:32:06Z by d778be9d: commit:22695c1cfd delegation:issue route with 2FA; account vitest 4340 rc 0
- [x] C5 [writer] The anonymous on-prem free tier: design, then build (R6).
  - Design first, as a new "Free tier (no certificate)" section in private/account/docs/runtime/on-premise-licensing.md covering quotas, abuse limits and the upgrade path.
  - Reuse PLAN-free-license and its code where possible: packages/cli/src/services/account/free-license.ts (BAKED_IN_REGIONS region pick :201-208), PLAN_LIMITS.FREE (packages/shared/src/subscription/constants.ts:35-39, 3 GB, no hosted backup), and the per-IP window in private/account/src/services/free-license.service.ts:238-292. Note that PLAN-drop-free-license-ip-prefix-hash is moving that window.
  - Default design, logged for veto: a server with no cert (bootstrapMode, private/account/src/routes/on-premise-status.ts:55-56) reports `tier: free` and gets each repo licence from the public `POST /licenses/free` (private/account/src/routes/license.ts:268-278) on the caller's behalf. Abuse limits stay those of the upstream FREE route, and renet is unchanged. The alternative, a box signing its own licences under built-in caps, is rejected unless the doc proves renet can bound it.
  - Upgrade: `rdc server licence` gets a cert through C4 and installs it with the existing `POST /onprem/cert-upload` (private/account/src/routes/on-premise-status.ts:9). The free-issued repos keep running until their 48 h licences lapse, then renew under the cert.
  - Offline with no cert means no free tier: the server refuses and names `--cert`.
  - Owns: private/account/docs/runtime/on-premise-licensing.md, private/account/src/services/onprem-free-tier.service.ts (new), private/account/src/routes/on-premise-status.ts, packages/shared/src/subscription/onprem-free-tier.ts (new), private/account/tests/integration/onprem-free-tier*.test.ts (new).
  - Accept: `(cd private/account && npx vitest run tests/integration/onprem-free-tier)` rc 0, `grep -c "## Free tier (no certificate)" private/account/docs/runtime/on-premise-licensing.md` prints 1, and `npm run -s check:ci-prose-style` rc 0.
    (ticked) 2026-11-12T12:32:07Z by d778be9d: commit:a3c61197b5 on-prem free tier; account vitest rc 0
- [x] C6 [writer] renet: per-host certificates and bring-your-own (R7).
  - A custom FQDN domain today gets `*.<baseDomain>` SANs (private/renet/pkg/router/routes.go:244-246 into wildcardTLSConfig :110-122), and certResolver is auto-added at :433-447. Instead, a router for a custom domain or an explicit Host label gets `domains: [{main: <host>}]` with no wildcard.
  - In HTTP-01 mode, renet's own base-domain auto-routes get no resolver, so no wildcard order is ever placed.
  - Bring-your-own: the label `rediacc.tls=provided` skips the certResolver. A new `renet proxy cert install --domain <h> --cert <f> --key <f>` (usercert.go) writes a 0600 tls.certificates file into the file-provider directory /etc/traefik/static (private/renet/pkg/proxy/infra.go:182), and `... cert remove` deletes it.
  - Owns: private/renet/pkg/router/routes.go, private/renet/pkg/router/routes_test.go, private/renet/pkg/proxy/usercert.go (new), private/renet/pkg/proxy/usercert_test.go (new), private/renet/cmd/renet/proxy_cert.go (new), private/renet/cmd/renet/proxy_cert_test.go (new).
  - Accept: `(cd private/renet && go test ./pkg/router/... ./pkg/proxy/... ./cmd/renet/...)` rc 0, and `grep -c '"\*\." + domainBase' private/renet/pkg/router/routes.go` unchanged only on the base-domain path (a test asserts no wildcard SAN for an FQDN custom domain).
    (ticked) 2026-11-12T12:32:30Z by d778be9d: commit:012193560e renet d2d92844 per-host certs and BYO; go test pkg/router pkg/proxy pkg/i18n rc 0
- [x] C7 [writer] `rdc server install|status|upgrade|backup|licence` in TS, porting P2's steps. Runs after C4 and C5 (wire shapes); supersedes C1.
  - install takes `[machine] --domain --store-domain --repo --size --owner --tls letsencrypt|cloudflare|byo --cf-token --tls-cert --tls-key --cert <file> --licence auto|free --image --yes`.
  - Interactive prompts live in utils/server-prompts.ts. They load inquirer lazily and exit with the region-prompt TTY error when not on a TTY (packages/cli/src/utils/region-prompt.ts:17-24). Machine pick-or-add reuses `machine add --ip --user` (packages/cli/src/commands/machine/register.ts:141-147), and `machine setup` runs when renet is missing.
  - DNS: print the A and AAAA records, then wait until both resolve to the machine. No zone is ever written.
  - TLS: Cloudflare goes through the existing `machine infra set --cf-dns-token --cert-email` (packages/cli/src/commands/machine/infra.ts:56-57); bring-your-own goes through C6's `renet proxy cert install`.
  - Owner defaults to the logged-in email. Request `delegation:issue` in the login mint (packages/cli/src/services/account/subscription-password-auth.ts:22). An older login without that scope is told to run `rdc subscription login` again, or offered the free tier.
  - Keys are generated on the box over SSH and written only to the repo's secrets.env. On a TTY the one-time recovery bundle (delegated keypair, ACCOUNT_CONFIG_SERVER_KEY, RustFS creds; private/elite/BACKUP.md:44-46) is printed once, never logged and never in `--output json`. With no TTY it is not printed, and the closing line names `rdc server backup`.
  - `backup` streams the bundle from the box to stdout, or to `--out` with mode 0600. `licence` runs C5's upgrade. `upgrade` runs `repo fork`, then a new image, then `repo up`.
  - i18n keys go in every locale. Watch the near-name of the existing `rdc serve` (packages/cli/src/commands/serve.ts:51).
  - Owns: packages/cli/src/commands/server.ts (new), packages/cli/src/services/server/** (new), packages/cli/src/utils/server-prompts.ts (new), packages/cli/src/services/account/subscription-password-auth.ts, packages/cli/src/config/command-planes.ts, packages/shared/src/cli-contract/data/i18n/*.json, packages/cli/src/commands/__tests__/server*.test.ts (new).
  - Accept: `(cd packages/cli && npx vitest run src/commands/__tests__/server)` rc 0, and `npm run check:ci-cli-contract` rc 0.
  (corrected 2026-11-12T12:55Z) The machine step is existing-machine first.
      - `[machine]` names a configured machine. Otherwise `--ip --user [--port] [--name]` registers it through a helper pulled out of packages/cli/src/commands/machine/register.ts:148-178 (config write plus keyscan) and shared with `machine add`.
      - The prompt offers "existing server or LAN device (IP/user)" first. It only mentions `rdc machine provision --provider` (packages/cli/src/commands/machine/provision.ts:50-53, tofu) as a hint and never calls it.
      - Before setup, a preflight runs: sudo -n, arch, ports 80/443 free, disk, clock skew.
      - The image step is explicit: pull on the box, or ship a tar. compose `pull_policy: never` means nothing pulls otherwise (C9).
      - `--cert` must match the box-generated key (Q13).
      - `upgrade` = fork, new image, template re-apply per Q19, TAG update, `repo up`.
      - Owns += packages/cli/src/commands/machine/register.ts, packages/cli/src/services/machine/add-existing.ts (new). Runs together with C9 and C10 (disjoint). C11 extends it afterwards.
  (corrected 2026-11-12T13:15Z) (operator rulings 2026-11-12) Single install path: C7 also carries the P2 extras (licence via /delegation/issue, optional --bws-project, owned-zone DNS write); upgrade re-applies a newer template and refuses on local edits unless --force (ASKED:2026-11-12T13:00Z).
    (ticked) 2026-11-12T14:29:26Z by d778be9d: commit:6c48953db0 rdc server install|status|upgrade|backup|licence; server vitest rc=0 (54), tsc rc=0, check:ci-cli-contract, check:ci-i18n-hashes, check:cli-examples, check:ci-command-tree rc=0; ./rdc.sh server install --help lists the steps
- [ ] C8 [writer] Gitlink bumps for private/account (C4, C5) and private/renet (C3, C6) after their submodule PRs merge, plus a renet release for the live boxes.
  - Owns: private/account (gitlink bump only), private/renet (gitlink bump only).
  - Accept: `git submodule status private/account private/renet` shows the merged C3-C6 commits, and `./rdc.sh --config eu-bench machine status hostinger` reports the released renet version.
  (corrected 2026-11-12T11:58Z) Local-route: hostinger -- the C3-C6 submodule commits ride the 1104-1 branch and land as gitlink commits here (no merge needed); the renet build reaches hostinger through `npm run release:local -- --channel edge` and then `./rdc.sh --config eu-bench machine setup hostinger`, so nothing waits on GitHub.
  (corrected 2026-11-12T12:55Z) The renet bump and release also carry C10.
- [ ] CL2 [live] On hostinger after C7 and C8: the free tier, licence upgrade and recovery bundle.
  - Run `rdc server install hostinger --config eu-bench --repo acme-free --domain acme-free.rediacc.io --licence free --yes`, then `rdc server licence acme-free.rediacc.io`.
  - The upgrade needs a bench subscription with no active cert. Each subscription allows one (packages/shared/src/subscription/constants.ts:388), and HO1 holds the operator's. Use a second bench subscription, or revoke after HO2.
  - Then run `rdc server backup acme-free.rediacc.io --out <tmp>`, and delete acme-free afterwards.
  - Accept: `rdc server status acme-free.rediacc.io` rc 0, reporting `tier: free` before the licence step and the cert's subscription after it. The bundle file is mode 0600 and holds the four keys. `./rdc.sh --config eu-bench repo list -m hostinger` ends at HO1's set.
  (corrected 2026-11-12T13:15Z) (operator ruling 2026-11-12, single install path) Runs `./rdc.sh --config eu-bench server install ...` and `./rdc.sh server licence ...` as written; its licence upgrade uses the dedicated bench lab subscription (operator ASKED:2026-11-12T13:00Z), not the operator subscription HO1 holds.
- [ ] CL3 [live] HTTP-01 on a public machine with no CF token, after C8. Hostinger uses DNS-01, so the operator names the host.
  - Run `rdc server install <public-vm> --domain <test host> --tls letsencrypt --yes` from an interactive session that answers every prompt.
  - Accept: `curl -sf https://<test host>/health` rc 0 over IPv4 and over IPv6 (`curl -6`), and the served certificate's SAN is exactly `<test host>`, with no `*.` entry.

### Wave 3 order (2026-11-12T11:58Z)
- 3a writers run together: C3, C4, C5, C6.
- 3b: C7 and C2, after C4 and C5 land, then C8.
- Live: CL1, CL2, CL3 after C8. C1 is not run.
- (corrected 2026-11-12T12:55Z) 3a += C12. 3b = C7, C9, C10 (disjoint), then C2. 3c = C11. Live: CL1, CL2, CL3, then CL4, CL5 after C8.
- [ ] G3 [writer] Wave-3 Owns are disjoint per writer wave.
  - Owns: none.
  - Accept: `grep -c "Owns:" agent/plans/PLAN-enterprise-tenants.md` is unchanged by any 3a/3b box, and the plan-concurrency check rc 0.

- [x] C9 [writer] elite template v2: versioned, local-first images, health check that works offline.
  - Add a `VERSION` file (integer), which lands in the repo, so an install can be read back with repo cat.
  - Rediaccfile up(): `docker load` every images/*.tar whose ref (from images/manifest.txt) is absent.
    When no tar exists and the server image is absent, `docker pull` it (fixes pull_policy:never, packages/cli/templates/elite/docker-compose.yml:4), unless ELITE_OFFLINE=1, which refuses and names the missing ref.
  - health(): `curl --resolve ${ELITE_DOMAIN}:443:127.0.0.1`, plus `--cacert ${ELITE_CA_FILE}` when set (Rediaccfile:63-66 today needs public DNS and a public CA).
  - The parity test also asserts that every non-server image in the compose is digest-pinned.
  - Owns: packages/cli/templates/elite/**, packages/cli/src/templates/embedded.generated.ts, .ci/rediacc_ci/tests/test_onprem_template_parity.py
  - Accept: `(cd packages/cli && npx tsx scripts/embed-templates.ts) && git diff --exit-code packages/cli/src/templates/embedded.generated.ts` rc 0, `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_onprem_template_parity.py` rc 0, `bash -n packages/cli/templates/elite/Rediaccfile` rc 0, `grep -c 'images/\*.tar\|ELITE_OFFLINE' packages/cli/templates/elite/Rediaccfile` >= 2.
    (ticked) 2026-11-12T13:17:05Z by d778be9d: commit:bba72d908d template v2; parity test 4 passed rc 0; embedded catalog regenerates clean

- [x] C10 [writer] renet `setup --offline`.
  - A bool flag sets setupOffline without the baked marker (private/renet/cmd/renet/pkg_install_retry.go:211-219).
  - It skips the apt mirror swap and the update (private/renet/cmd/renet/setup_command.go:1238-1274), forces docker-source=manual, and fails up front listing the missing pkgset.Essentials, docker engine and compose plugin.
  - Add `offline` to setupStringArgs (private/renet/cmd/renet/job_commands.go:945-950).
  - Owns: private/renet/cmd/renet/setup_command.go, private/renet/cmd/renet/pkg_install_retry.go, private/renet/cmd/renet/job_commands.go, private/renet/cmd/renet/setup_offline_test.go (new), private/renet/pkg/i18n/locales/*.go
  - Accept: `(cd private/renet && go test ./cmd/renet/ -run 'Offline|BuildCommandArgv' && go test ./pkg/i18n/...)` rc 0. A test asserts that offline mode with all tools present prints `[setup] pkg-calls 0`, and with cryptsetup missing names it.
  - Rides C8's renet release (add these commits to C8's bump).
    (ticked) 2026-11-12T13:16:42Z by d778be9d: commit:f2957093f2 renet setup --offline; go test cmd/renet Offline rc 0

- [ ] C11 [writer] Offline bundle and install. Extends C7; runs after C7, C9 and C10.
  - `rdc machine setup --offline` passes `offline:true` (packages/cli/src/commands/machine/register.ts:405).
  - `rdc server bundle --out <dir> [--arch amd64|arm64] [--tag <t> | --image <local ref>] [--with-cli <plat,...>]`, run online, writes:
    - images/server.tar, images/rustfs.tar and images/traefik.tar, each saved with `--platform linux/<arch>`;
    - images/manifest.txt;
    - renet/renet-linux-<arch> from the SEA assets;
    - manifest.json: {schema, cliVersion, template:{name, version, sha256}, renet:{version, arch, sha256}, images:[{ref, digest, file, sha256}], createdAt};
    - SHA256SUMS.
    The Traefik ref is a constant in services/server/bundle/images.ts, pinned by a vitest that reads private/renet/proxy/docker-compose.yml:21.
  - `rdc server install --offline --bundle <dir>`:
    - verifies the sums and the CLI/renet match (Q16);
    - runs the preflight: sudo -n, arch, ports 80/443 free, disk, clock skew (Q18), essentials (Q14);
    - runs `machine setup --offline`;
    - streams images/traefik.tar into `docker load` before the proxy converge;
    - calls no upstream (`--licence free` is refused offline);
    - stops at `cert` with delegation-request.json (Q13), and resumes with `--cert`;
    - uploads `images/` via repo sync and writes ELITE_OFFLINE=1 in secrets.env;
    - replaces the DNS wait with printed LAN records plus `--no-dns-wait`; `--tls-ca` is recorded for health checks.
  - `rdc server licence mint --request <f> --out <f>`, run online.
  - `rdc server upgrade <domain> [--bundle <dir>]`: fork, new image (pull, or bundle tar), template re-apply per Q19, update TAG/ELITE_IMAGE, `repo up`.
  - Owns: packages/cli/src/commands/server.ts, packages/cli/src/services/server/**, packages/cli/src/commands/machine/register.ts, packages/cli/src/commands/__tests__/server*.test.ts, packages/shared/src/cli-contract/data/i18n/*.json
  - Accept: `(cd packages/cli && npx vitest run src/commands/__tests__/server src/services/server)` rc 0 (cases: checksum tamper refused, CLI mismatch refused, offline + free refused, cert key mismatch refused, upgrade re-applies only on a newer VERSION, local-edit refusal), and `npm run check:ci-cli-contract` rc 0.
  (corrected 2026-11-12T13:15Z) (operator rulings ASKED:2026-11-12T13:00Z and 14:2xZ) Offline licence = request/response with a long-lived certificate: the box writes a public-key request, any online machine or the portal mints the cert, it is carried back; offline certs last up to 365 days per plan, the box warns 30 days before expiry, and after expiry it soft-degrades (no new repo licences; running services keep working). Every plan may self-host (operator 2026-11-12; plan gates removed in c167e0ddc9). Offline packages are prerequisites only (C10). The lab subscription for CL4/CL5 is a dedicated bench subscription.

- [x] C12 [writer] Lab helpers: air-gap a VM and a throwaway CA.
  - `python -m rediacc_ci.onprem.airgap apply|remove|check --vm <ip>`, ops network only, refusing anything outside 192.168.111.0/24 (.ci/rediacc_ci/drills/vm_check.py:119):
    - iptables and ip6tables OUTPUT policy DROP, allowing only lo and ESTABLISHED,RELATED, so SSH from the host gateway .254 (private/renet/pkg/infra/opsconfig/config.go:233-235) still works;
    - the same DROP in DOCKER-USER; not persistent, so a reboot clears it;
    - `check` runs on the VM and requires that `curl -m5` to ghcr.io, registry-1.docker.io, archive.ubuntu.com and download.docker.com, and a DNS query to 1.1.1.1, all fail while ssh answers. It prints the OUTPUT DROP counter as evidence.
  - `python -m rediacc_ci.onprem.testca <dir> <host>...` writes ca.crt and a host cert/key with openssl.
  - Owns: .ci/rediacc_ci/onprem/airgap.py (new), .ci/rediacc_ci/onprem/testca.py (new), .ci/rediacc_ci/tests/test_onprem_airgap.py (new)
  - Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_onprem_airgap.py` rc 0 (recorded ssh transport; rules text; refuses a non-ops IP).
  - Can run now (wave 3a).
    (ticked) 2026-11-12T13:16:44Z by d778be9d: commit:bf0bded8be airgap and testca helpers; pytest test_onprem_airgap 19 passed rc 0

- [ ] CL4 [live] Air-gapped install on ops VM .12, after C8 (with C10), C11 and C12.
  - Fleet: `VM_WORKERS='11 12' VM_CEPH_NODES='' ./rdc.sh ops up` (private/renet/pkg/infra/opsconfig/config.go:699-713).
  - Then:
    1. `PYTHONPATH=.ci python3 -m rediacc_ci.onprem.airgap apply --vm 192.168.111.12`
    2. Online: `./rdc.sh server bundle --out <B1> --image rediacc-server-onprem:dev`
    3. Clear the setup marker so setup takes the full path.
    4. `./rdc.sh --config onprem-lab server install --ip 192.168.111.12 --user $USER --name lab-airgap --offline --bundle <B1> --domain elite-air.ops.test --store-domain elite-air-store.ops.test --tls byo --tls-cert <crt> --tls-key <key> --tls-ca <ca> --owner <mail> --no-dns-wait --yes` (exits 75 with the request)
    5. `./rdc.sh --config onprem-lab server licence mint --request <req> --out <cert>`
    6. Re-run step 4 with `--cert <cert>`.
  - Accept: `airgap check --vm 192.168.111.12` rc 0 before and after; the setup log contains `[setup] pkg-calls 0`; `./rdc.sh --config onprem-lab server status elite-air.ops.test` rc 0 with bootstrapMode=false and the subscription equal to the cert's; `curl --cacert <ca> --resolve elite-air.ops.test:443:192.168.111.12 -sf https://elite-air.ops.test/health` rc 0.
  (corrected 2026-11-12T13:15Z) (operator ruling 2026-11-12, single install path) `./rdc.sh server bundle` and `./rdc.sh server install --offline` as written; the air-gap helper is `python -m rediacc_ci.lab.airgap`; the licence follows the request/response flow (operator ASKED:2026-11-12T13:07Z): install writes delegation-request.json, `./rdc.sh server licence mint --request <f> --out <cert>` on the online side (dedicated bench lab subscription), re-run with `--cert`.

- [ ] CL5 [live] Air-gapped upgrade, after CL4.
  - Run `./rdc.sh server bundle --out <B2> --image <newer local tag>`, then `./rdc.sh --config onprem-lab server upgrade elite-air.ops.test --bundle <B2> --yes`.
  - Accept: `airgap check --vm 192.168.111.12` rc 0; `server status` rc 0 reporting the new image digest and `template: <built-in VERSION>`; `./rdc.sh --config onprem-lab repo list -m lab-airgap` shows the fork rollback point; the health curl from CL4 rc 0.
  (corrected 2026-11-12T13:15Z) (operator ruling 2026-11-12, single install path) `./rdc.sh server upgrade --bundle` as written; the template re-apply refuses on local edits unless --force (operator ASKED:2026-11-12T13:00Z).

- [ ] LP-bench [live] Fresh bench receipt through worklist.py --live-proof, after this plan's bench-deployable boxes land.
  Accept: live-proof bench account-smoke
- [ ] LP-hostinger [live] Fresh hostinger receipt through worklist.py --live-proof, after HO1 lands the Elite repo.
  Accept: live-proof hostinger renet-live machine=hostinger

### Production: only after an explicit operator go, once bench is green

- [ ] X1 [live] Production signers, as in PLAN-enterprise-isolation.
  - Accept: `./run.sh enterprise proof keys` rc 0 and `.ci/scripts/quality/check_region_consistency.py --live` rc 0.
- [ ] H1 [live] hostinger renews through signer-eu.
  - Accept: `./rdc.sh --config eu-remote machine status hostinger` rc 0, with the renewal after X1 recorded.
- [ ] X2 [live] Internal canary company, unlisted, one release on each path.
  - Accept: `./run.sh enterprise list` rc 0, naming the canary healthy.

### Order

- Wave 0 is Q0.
- Wave 1 writers E1, E2, P1 and L1 run together.
- Wave 2 writers E3 and P2 run together.
- Two live queues run side by side:
  - Bench: V1 starts right after Q0 because it needs no writer. Then LD1, V3, V4, (LT1), T1, V2, V6, V7, V5, V8, V11, V9, and V10 once the workflow is on main.
  - Hostinger: HO1, then HO2.
- Wave 3 starts after HO1.
- Production (X1, then H1, then X2) starts after the operator's go.

## Questions for the operator (recommended default first)

1. **Cloud tenant lookup.** Make acme `--unlisted`? Default yes. Without it, a bench add writes the production www lookup so that `rediacc.com` maps to acme.
2. **Which bench subscription issues the on-prem cert?** Default: the operator's account at bench.rediacc.cloud, which is available now. The alternative is acme's own ENTERPRISE subscription, which links the two tenants but waits for V1, the DNS step and V3/V4.
3. **V6/V7 drivers.** Build config-token, E2E envelope and console command now? Default yes. Fallback: split config-token out and leave that one claim open.
4. **Elite backup store.** Expose `acme-store.rediacc.io` for presigned backup URLs? Default yes.
5. **On-prem secrets custody.** Default: a local 0600 state file plus a bws entry under an opaque name, since the config server key must be backed up.
6. **Verb shape.** Default: the `elite` template is the unit, `rdc onprem install <machine> --domain …` is the guided wrapper, and `./run.sh onprem install` is the internal fast path first.
7. **TLS for customers.** Default: Let's Encrypt via Cloudflare DNS-01 when the customer gives a token, plus a new HTTP-01 fallback in renet (C3). Bring-your-own certificate comes later.
8. **Where keys are generated.** Default: on the box for customers, so the private key never leaves it. For the hostinger test, locally, as the drill does.
9. **How the cert is obtained.** Default: support both `--cert <file>` (made by the customer in the portal) and `--upstream <url>` (minted from the logged-in session). It needs checking whether a CLI login can call the session-only `/portal/delegation-certs`; if it cannot, `--upstream` opens the portal page.
10. **Cert auto-renew.** Pass `UPSTREAM_URL` and `UPSTREAM_API_KEY` through the template, with the token from `/portal/delegation-certs/auto-renew-token`? Default yes. Elite's compose lacks this today.
11. **Image distribution.** Default: customers pull a public ghcr on-prem tag. Our test ships a local build. Please confirm whether that image is public or needs registry credentials.
12. **DNS, first account and upgrades.**
    - DNS: rdc prints and verifies the customer's records and only writes zones we own. Default yes.
    - First account: the install registers the owner in the same run. Should registration then close? Default: close it.
    - Upgrades: `rdc onprem upgrade` forks the repo as a rollback point, then deploys the new image. Default yes.

### Critical files for implementation
- /home/developer/console/.ci/rediacc_ci/enterprise/onboarding.py
- /home/developer/console/.ci/rediacc_ci/enterprise/cli.py
- /home/developer/console/.ci/rediacc_ci/enterprise/lab.py
- /home/developer/console/.ci/rediacc_ci/drills/backup_elite_compose.py
- /home/developer/console/private/elite/docker-compose.yml
