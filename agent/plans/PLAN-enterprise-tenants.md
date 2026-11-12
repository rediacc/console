# PLAN: enterprise tenants -- stand up acme.rediacc.cloud (bench) and acme.rediacc.io (on hostinger), close the routing and on-prem install gaps
Status: approved -- operator order 2026-11-12 "employ a parallel agent to complete the gaps in PLAN-enterprise-isolation.md ASAP"; operator rulings ASKED:2026-11-12T11:3xZ folded in (bench first, acme owner and storage, on-prem as an rdc repo on hostinger plus a customer-grade rdc flow, delegation cert from bench); production X1/H1/X2 wait for an explicit operator go after bench is green
Owner: d778be9d
Updated: 2026-11-12
Depends-On: PLAN-enterprise-isolation.md, PLAN-product-domain-rename.md, PLAN-website-routing-and-mail.md#W1, PLAN-website-routing-and-mail.md#W8, PLAN-website-routing-and-mail.md#M3
Priority: P1 -- the Enterprise offer is unproven until a real tenant answers on each delivery form
Concurrency: parallel -- writers in each wave own disjoint files. PLAN-enterprise-isolation.md owns .ci/rediacc_ci/enterprise/** and .ci/rediacc_ci/__main__.py / core/run_verbs.py, but it has no open writer box, so block_plan_concurrency sees no live holder. Its Owns line should be narrowed to its live boxes when this plan is promoted.
Owns: agent/plans/PLAN-enterprise-tenants.md, .ci/rediacc_ci/ops/cf_dns.py, .ci/rediacc_ci/tests/test_ops_cf_dns.py, .ci/rediacc_ci/enterprise/cli.py, .ci/rediacc_ci/enterprise/onboarding.py, .ci/rediacc_ci/enterprise/dns.py, .ci/rediacc_ci/enterprise/lab.py, .ci/rediacc_ci/enterprise/lifecycle_adapters.py, .ci/rediacc_ci/tests/test_enterprise_dns.py, .ci/rediacc_ci/tests/test_enterprise_add.py, .ci/rediacc_ci/tests/test_enterprise_cli_wiring.py, .ci/rediacc_ci/tests/test_enterprise_lab.py, .ci/rediacc_ci/tests/test_enterprise_lifecycle_adapters.py, .ci/rediacc_ci/onprem/**, .ci/rediacc_ci/tests/test_onprem_*.py, .ci/rediacc_ci/__main__.py, .ci/rediacc_ci/core/run_verbs.py, .ci/rediacc_ci/tests/test_core_run_verbs.py, packages/cli/templates/elite/**, packages/cli/src/templates/embedded.generated.ts, packages/cli/src/commands/onprem.ts, packages/cli/src/services/onprem/**, packages/cli/src/config/command-planes.ts, packages/shared/src/cli-contract/data/i18n/*.json, packages/www/src/content/docs/en/on-premise.md, private/account/docs/enterprise.md, private/elite/BACKUP.md, private/renet/pkg/proxy/infra.go, private/renet/pkg/proxy/infra_test.go, private/account (gitlink bump only), private/elite (gitlink bump only), private/renet (gitlink bump only)
Live-Proof: bench, hostinger -- bench proves the signers, routing and the acme company. Hostinger proves the Elite repo acme-onprem behind its proxy with a bench-issued delegation cert. Production (X1/H1/X2) runs only on the operator's go.
First-Seen: 2026-11-12

## Context
The enterprise-isolation dependency is on its live boxes V1-V11, X1, H1 and X2, which run in this plan's order; every writer box there is ticked.

What is verified in the code:

- **No DNS step anywhere.** `enterprise add` runs `control-row, d1, configs, migrate, buckets, secrets, deploy, bootstrap, smoke, lookup, invite, audit` (.ci/rediacc_ci/enterprise/onboarding.py:42-55). None of these steps creates a DNS record.
  - Company Worker routes are declared in the generated toml as `{ pattern = "<host>/*", zone_name = "rediacc.cloud" }` (.ci/rediacc_ci/enterprise/configs.py:172; workers/account/enterprise.template.toml:8-12). So `wrangler deploy` creates the routes itself.
  - A Worker Route only fires when a proxied DNS record covers the host. With no `*.rediacc.cloud` record, the `smoke` step (onboarding.py:604-613) cannot pass.
  - The shared Workers use `custom_domain = true` (workers/account/wrangler.eu.toml:7-9, workers/proxy/wrangler.eu.toml:10-12). Those records outrank a wildcard, so a wildcard cannot capture region hosts.
- **Universal SSL fits the host shape.** `names.hosts` (.ci/rediacc_ci/enterprise/names.py, the `hosts` function at the end of the file) gives one-label hosts: `<c>.rediacc.cloud` and `<c>-proxy.rediacc.cloud`. The free Universal certificate covers `*.rediacc.cloud` at exactly one level. Nothing checks that coverage before V4.
- **Removal leaves routes behind.**
  - `CloudflareTeardown.undeploy` deletes Worker scripts only (.ci/rediacc_ci/enterprise/lifecycle_adapters.py:290-311).
  - The V11 reader `leftovers` lists Workers, D1, buckets, the token and the control row, but not zone routes (.ci/rediacc_ci/enterprise/lab.py:1931-1960).
  - So a removed company's routes can outlive it, and V11 would not notice.
- **Known proof gaps, before any live run:**
  - V6 has no config-token driver (lab.py:1026) and no E2E-envelope driver (lab.py:1032).
  - V7 has no `console_command` (lab.py:1173).
  - `proof replay` and `proof proxy` cannot reach rc 0 until these exist.
- **A bench company writes the production lookup.** The `lookup` step writes to KV namespace `7bbf3025...` (.ci/rediacc_ci/ops/enterprise_lookup.py:28; onboarding.py:618) whether or not `--bench` is set. With owner `muhammed@rediacc.com` and no `--unlisted`, www lookup for `rediacc.com` would point at acme. acme must be `--unlisted`.
- **Stale doc.** private/account/docs/enterprise.md:21 says export and remove are `Unbound`. The code wires `la.CloudflareExporter` (cli.py:223) and `la.CloudflareTeardown` (cli.py:271).
- **V10 still waits on GitHub.** `git log origin/main -- .github/workflows/cd-enterprise-release.yml` returns nothing, so the workflow is not on main yet. V10 is the only box with no local path.
- **On-prem pieces already exist and can be reused:**
  - Elite compose: web, rustfs and rustfs-init on external networks; `pull_policy: never`; image `ghcr.io/rediacc/server:${TAG}` (private/elite/docker-compose.yml). It has no `UPSTREAM_URL` or `UPSTREAM_API_KEY` pass-through, so connected cert auto-renew is unwired there.
  - "The first account registered on the box takes the cert's subscription" (private/elite/BACKUP.md:40). That is a race if the box is public before the owner registers.
  - The drill already contains the install sequence: `elite_env` (.ci/rediacc_ci/drills/backup_elite_compose.py:133), `cert_base64` (:183), `ship_image` (docker save/load, :267), and register-then-login (:516-524).
  - Keys: `core/account.py:360 generate_crypto_keys`. Local image build: `ops/build_server.py onprem` produces `rediacc-server-onprem:dev`, with the production public key baked in as `UPSTREAM_PUBLIC_KEY_DEFAULT` (.ci/docker/web/entrypoint.sh:221-226).
  - Bench portal login with TOTP: `ops/login_bench.py:558 login`.
  - The delegation-cert route needs an org owner or admin session (private/account/src/routes/portal-delegation-certs.ts:46,66). The service allows one active cert per subscription.
- **renet supports what the on-prem repo needs:**
  - It routes custom domains from `rediacc.domain` or Traefik `Host()` labels (private/renet/pkg/compose/wrapper.go:763-800).
  - Its Traefik issues Let's Encrypt certificates through Cloudflare DNS-01 only, and only when `CF_DNS_API_TOKEN` is set (private/renet/pkg/proxy/infra.go:205-215).
  - renet injects `network_mode: host` and ignores `ports:`. So Elite's compose cannot run as a repo unchanged; it needs a renet variant that addresses rustfs by `${RUSTFS_IP}`.
  - Templates live in packages/cli/templates/<name> and are embedded by packages/cli/scripts/embed-templates.ts. They are applied with `rdc repo admin template apply <ref> --template <name>` (packages/cli/src/commands/repo-extended.ts:448-470).
  - `rdc machine setup <name>` installs renet (packages/cli/src/commands/machine/register.ts:352-370).
- **The rediacc.io zone has a wildcard.** `*.rediacc.io` is a CNAME to `www.rediacc.io` (private/account/docs/infra/cloudflare.md:143), so acme needs explicit records. Hostinger is 72.61.137.225 / 2a02:4780:c:e9b5::1 (cloudflare.md:120-121; private/account/docs/email/architecture.md:192-193).

Not verified, and owned by box Q0 below:
- That the wildcard record and routes are really absent.
- Universal SSL state on rediacc.cloud.
- Whether gitlab.rediacc.io is DNS-only with a Let's Encrypt certificate.
- Hostinger's proxy token scope, renet version and free disk.
- Whether an enterprise bws project exists.
- The operator's bench subscription plan and its active delegation certs.

## Rulings

Already ruled (ASKED:2026-11-12T11:3xZ):
- R1. The cloud tenant is `acme.rediacc.cloud`, bench first. X1, H1 and X2 wait for an explicit go once bench is green.
- R2. acme's owner is muhammed@rediacc.com, with 10 GB storage.
- R3. On-prem `acme.rediacc.io` runs on hostinger as an rdc repo behind the existing proxy. The install becomes a customer-grade `rdc` flow: `rdc machine setup`, then rdc deploys Elite as a repo with domain, TLS, delegation cert and first account.
- R4. The on-prem delegation cert comes from bench.

Still open. Each has a recommended default; the short list for the operator is at the end.
- Q1. acme is `--unlisted`? Default yes, because of the lookup finding in Context.
- Q2. Which bench subscription issues the on-prem cert? Default: the operator's own account at bench.rediacc.cloud. It exists today and does not wait for V1. The alternative is acme's own ENTERPRISE subscription on acme.rediacc.cloud, which ties the two tenants together but waits for V1, the DNS step and V3/V4.
- Q3. V6/V7 drivers: build all three (config-token, E2E envelope, console command)? Default: build. If the config-store driver is too big for one writer, split it out, and record V6's config-token claim as open. That blocks only V6.
- Q4. Expose the Elite store for backups at `acme-store.rediacc.io`? Default yes. It is one more Traefik router, and the Host header passes through unchanged, so presigned SigV4 URLs stay valid.
- Q5. Where do on-prem secrets live? Default: a local state file at `~/.local/state/rediacc/onprem/<domain>/`, mode 0600, plus bws under an opaque name, because `ACCOUNT_CONFIG_SERVER_KEY` must be backed up (BACKUP.md:44-46).
- Q6-Q12 are about the customer flow. They are listed at the end.

## Design

### Cloud: DNS, routes, Universal SSL

1. **`.ci/rediacc_ci/ops/cf_dns.py` (new).** One small Cloudflare DNS and TLS client, used by both tenants.
   - `ensure_record(zone, name, type, content, proxied, comment)` is idempotent: create, update in place, or leave unchanged.
   - `records(zone, name)` lists records.
   - `universal_ssl(zone)` returns `(enabled, hosts covered, status)` from `GET /zones/{id}/ssl/universal/settings` and `/ssl/certificate_packs?status=all`.
   - It reuses `cf_auth.curl_json`, as lifecycle_adapters.py:490 already does, and the zone ids in ops/apply_cf_redirect_rules.py:34-37.
   - The CLI is `python -m rediacc_ci.ops.cf_dns ensure|show|ssl`. A record comment never carries a company label.
2. **`./run.sh enterprise dns ensure [--check]`** (new `enterprise/dns.py`, dispatched from cli.py):
   - Ensures one proxied `AAAA * -> 100::` in rediacc.cloud. That is the originless pattern for Worker-only hosts.
   - Refuses if it finds a conflicting `*` record of another type.
   - Asserts Universal SSL is enabled and active and covers `*.rediacc.cloud`.
   - `--check` changes nothing. Exit 1 names the failed claim.
3. **New onboarding step `route`, between `deploy` and `smoke`.**
   - It calls `dns.ensure(check_only=False)`. The wildcard is shared, so this is idempotent and cheap.
   - It then reads `/zones/{id}/workers/routes` and requires `<host>/*` mapped to `account-<c>` and `<c>-proxy` mapped to `proxy-<c>`. It reuses the matching rule from lab.py `routed_worker` (lab.py:652-669) by importing it, not copying.
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
- Replace line 21: export and remove are wired to `CloudflareExporter` and `CloudflareTeardown` (cli.py:223, :271), and need Cloudflare and R2 credentials plus `--bws-project`.
- Add rows for the `dns` verb and the `route` step.
- Add a pointer to `./run.sh onprem`.

In private/elite/BACKUP.md, add a pointer to the renet-repo install.

## Tasks

### Wave 0

- [ ] Q0 [live] Read-only survey. Changes nothing; each finding is recorded under this box.
  - Cloudflare, rediacc.cloud: `python -m rediacc_ci.ops.apply_cf_redirect_rules --dry-run --zone rediacc.cloud` reaches the zone. Then use the API (under `bws_env exec --profile deploy-bench`) to list `*` records, `/workers/routes`, Universal SSL settings and cert packs.
  - Cloudflare, rediacc.io: records for `acme`, `acme-store` and `gitlab`.
  - TLS: `openssl s_client -connect gitlab.rediacc.io:443` issuer.
  - Hostinger: `./rdc.sh --config eu-bench machine status hostinger` (renet version, free disk) and `./rdc.sh --config eu-bench repo list -m hostinger`, saved as the baseline.
  - bws: the enterprise project id.
  - Bench: `npm run login:bench`, then the operator subscription's plan and active delegation certs.
  - Owns: none.
  - Accept: `./rdc.sh --config eu-bench machine status hostinger` rc 0, and the findings recorded here.

### Wave 1: writers, disjoint

- [ ] E1 [writer] `ops/cf_dns.py`: `ensure_record`, `records`, `universal_ssl`, and its CLI, tested with a recording transport. Tests cover create, no-op, update, conflict refused, proxied flag, and a comment carrying no label.
  - Owns: .ci/rediacc_ci/ops/cf_dns.py (new), .ci/rediacc_ci/tests/test_ops_cf_dns.py (new).
  - Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_ops_cf_dns.py` rc 0.
- [ ] E2 [writer] Lab and teardown gaps:
  - Teardown deletes the company's zone routes, and `leftovers` reports `zone route`.
  - V6 `config-token` driver (store setup with elevated session and CEK slots) and `e2e-envelope` driver (a request sealed to the company's X25519 key through `POST /account/api/v1/tunnel`).
  - V7 `console_command`.
  - The three `not built yet` raises (lab.py:1026, 1032, 1173) are gone.
  - Owns: .ci/rediacc_ci/enterprise/lab.py, .ci/rediacc_ci/enterprise/lifecycle_adapters.py, .ci/rediacc_ci/tests/test_enterprise_lab.py, .ci/rediacc_ci/tests/test_enterprise_lifecycle_adapters.py.
  - Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_enterprise_lab.py .ci/rediacc_ci/tests/test_enterprise_lifecycle_adapters.py` rc 0, and `grep -c "not built yet: V[67]" .ci/rediacc_ci/enterprise/lab.py` prints 0.
- [ ] P1 [writer] The `elite` template as described in Design, the regenerated embedded catalog, and the parity test against private/elite/docker-compose.yml.
  - Owns: packages/cli/templates/elite/** (new), packages/cli/src/templates/embedded.generated.ts, .ci/rediacc_ci/tests/test_onprem_template_parity.py (new).
  - Accept: `(cd packages/cli && npx tsx scripts/embed-templates.ts) && git diff --exit-code packages/cli/src/templates/embedded.generated.ts` rc 0 after the commit, and `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_onprem_template_parity.py` rc 0, and `bash -n packages/cli/templates/elite/Rediaccfile` rc 0.
- [ ] L1 [writer] The doc fix as described in Design: enterprise.md line 21, the `dns` and `route` rows, the onprem pointer, and the BACKUP.md pointer.
  - Owns: private/account/docs/enterprise.md, private/elite/BACKUP.md.
  - Accept: `grep -c "Unbound" private/account/docs/enterprise.md` prints 0, and `npm run -s check:ci-prose-style` rc 0.

### Wave 2: writers, after E1 and P1 land

- [ ] E3 [writer] `enterprise/dns.py` and the `./run.sh enterprise dns ensure [--check]` dispatch in cli.py. The onboarding `route` step goes between `deploy` and `smoke`, using `cf_dns` and lab's route matcher.
  - Owns: .ci/rediacc_ci/enterprise/dns.py (new), .ci/rediacc_ci/enterprise/cli.py, .ci/rediacc_ci/enterprise/onboarding.py, .ci/rediacc_ci/tests/test_enterprise_dns.py (new), .ci/rediacc_ci/tests/test_enterprise_add.py, .ci/rediacc_ci/tests/test_enterprise_cli_wiring.py.
  - Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_enterprise_dns.py .ci/rediacc_ci/tests/test_enterprise_add.py .ci/rediacc_ci/tests/test_enterprise_cli_wiring.py` rc 0.
- [ ] P2 [writer] `./run.sh onprem install|status`:
  - The resumable steps as described in Design, importing `elite_env`, `cert_base64`, `ship_image`, `generate_crypto_keys` and `login_bench.login` rather than copying them.
  - The `onprem` row in `__main__.py`, with `dns` added to the `enterprise` summary at `__main__.py:106-110`, and help in run_verbs.py.
  - Refuses mutating calls through `eu-remote`.
  - Owns: .ci/rediacc_ci/onprem/** (new), .ci/rediacc_ci/tests/test_onprem_install.py (new), .ci/rediacc_ci/__main__.py, .ci/rediacc_ci/core/run_verbs.py, .ci/rediacc_ci/tests/test_core_run_verbs.py.
  - Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_onprem_install.py .ci/rediacc_ci/tests/test_core_run_verbs.py .ci/rediacc_ci/tests/gates/test_gate_run_sh.py` rc 0.

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
- [ ] HO2 [live] A machine licensed by the box. On a local ops VM, log in to `https://acme.rediacc.io` and `repo create`. The licence carries the box's delegation cert. If Q4 is accepted, also take one snapshot into `acme-store.rediacc.io`.
  - Accept: `./rdc.sh repo create hoprobe -m <ops-vm> --size 1G` rc 0 under the acme.rediacc.io login, with `drills.backup_elite_compose.licence_problem` empty on the issued licence.

### Wave 3: customer-grade flow, after HO1 is green and Q6-Q12 are answered

- [ ] C1 [writer] `rdc onprem install|status|upgrade|cert` in TS, porting P2's steps. Keys are generated on the box. `--cert` and `--upstream` per Q9. Customer DNS is printed and verified, never written. i18n keys in every locale.
  - Owns: packages/cli/src/commands/onprem.ts (new), packages/cli/src/services/onprem/** (new), packages/cli/src/config/command-planes.ts, packages/shared/src/cli-contract/data/i18n/*.json, packages/cli/src/commands/__tests__/onprem*.test.ts (new).
  - Accept: `(cd packages/cli && npx vitest run src/commands/__tests__/onprem)` rc 0, and `npm run check:ci-cli-contract` rc 0.
- [ ] C2 [writer] Public docs: an "Install with rdc" section in on-premise.md.
  - Owns: packages/www/src/content/docs/en/on-premise.md.
  - Accept: `npm run -s check:ci-prose-style` rc 0.
- [ ] C3 [writer] Only if Q7 is ruled yes: an HTTP-01 resolver when `CF_DNS_API_TOKEN` is empty.
  - Owns: private/renet/pkg/proxy/infra.go, private/renet/pkg/proxy/infra_test.go.
  - Accept: `(cd private/renet && go test ./pkg/proxy/...)` rc 0.
- [ ] CL1 [live] On a fresh local ops VM, run `rdc machine setup <vm>` and then `rdc onprem install <vm> --domain <ops-vm test name> --cert <file>`.
  - Accept: the same health and status checks as HO1.

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
