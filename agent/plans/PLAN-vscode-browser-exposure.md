# PLAN: open a repo's VS Code from the web console, gated by a portal token, with no SSH key

Status: proposed -- converted from console#522 on 2026-11-16 after its Phase A spike ran on hostinger; awaiting operator approval
Owner: e0f36861
First-Seen: 2026-11-16
Depends-On: no-dep -- the spike's evidence is recorded below; no open plan owns the router gate, the vscode verbs or the console RepoDetail page
Priority: P3 -- convenience feature; the SSH-tunnel flow (`rdc vscode connect --browser`) keeps working meanwhile
Concurrency: parallel -- new files plus narrow edits; Owns decides overlaps
Owns: agent/plans/PLAN-vscode-browser-exposure.md, private/renet/pkg/router/gate*.go, private/renet/pkg/router/server.go (gate handler mount only), private/renet/cmd/renet/repository_vscode*.go, private/renet/pkg/functions/commands/repository.go, private/renet/pkg/i18n/locales/*.go, packages/cli/src/commands/vscode-expose.ts, packages/cli/src/services/core/vscode-server-remote.ts, packages/cli/src/i18n/locales/**, packages/shared/src/cli-contract/data/**, packages/shared/src/renet-contract/data/**, private/account/src/routes/console-vscode.ts, private/account/web/src/pages/console/RepoDetail.tsx, private/account/web/src/i18n/locales/**, packages/e2e-tests/tests/34-vscode-expose.test.ts, packages/www/src/content/docs/en/vscode.md, workers/signer/src/index.ts, private/account/src/services/signer-client.ts, private/account/src/services/license-signer.service.ts, private/account/src/container.ts, private/account/src/app.ts, private/account/tests/integration/vscode-token-signer.test.ts, private/account/tests/integration/license-signer-scope.test.ts, private/account/tests/integration/helpers/test-db.ts
Live-Proof: bench, hostinger -- the router gate and repository verb under private/renet are the renet surface (hostinger), the token route and RepoDetail button under private/account plus the regenerated contracts are the account surface (bench)
Source: https://github.com/rediacc/console/issues/522

## Ask

Today `rdc vscode connect --browser` serves code-server from inside the repo sandbox and reaches it over an SSH tunnel held open from the operator's laptop, so it needs an SSH key. The web console should offer "Open in VS Code" on a repo: the editor is exposed at a public per-repo hostname through the machine's Traefik, behind a short-lived token the portal mints, with no SSH key on the user's side. Interactive traffic goes direct through Traefik on grey-cloud DNS, never through the Cloudflare container tier, and no Cloudflare Tunnel is used (constraints locked in console#522).

## Context (checked 2026-11-16 against the tree and on hostinger)

1. Phase A spike, run 2026-11-16 07:35-07:55Z on hostinger through `./rdc.sh --config eu-bench`, disposable repo `vscode-spike` (4G, GUID e9304ffc-0c96-47f2-a2fb-6076c1df6f52): a `codercom/code-server:4.96.4` service with Tier-2 Traefik labels and a forwardAuth middleware pointing at a 40-line Python gate service in the same repo.
   - Reachability and TLS: `https://vscode-spike.hostinger.rediacc.io/` served with the Let's Encrypt wildcard `CN=*.hostinger.rediacc.io` (openssl s_client); DNS resolves straight to 72.61.137.225, so Cloudflare is not in the WebSocket path.
   - Token gate: no token 401, wrong token 401, right token 302 with an HttpOnly Secure cookie, cookie 302 to `./?folder=/data/work` then 200 with `workbench.js` (curl).
   - Idle: PASS. A real browser (agent-browser) opened the editor at 07:42:19Z and the workbench connected (the workspace-trust prompt only appears once the remote server answers). The session was then left alone for 10 min 38 s; the gate logged zero requests for `/` in that window (only the minute-by-minute cookie-less probes to `/healthz-nocookie`, all 401), so the editor made no reconnect, and no disconnect or reconnect notice was showing at 07:52:57Z. At 07:54:57Z the Explorer's New File action created `/data/work/after-idle.txt` on the server over the same connection (`ls` in the repo showed the file, owner root, timestamp 07:54:57).
   - Go/no-go: GO. All three pass criteria of console#522 Phase A hold.
   - Observed along the way: three cookie-less `GET /` requests were denied at 07:53:24-07:53:50Z, most likely VS Code's webview service-worker fetches, which send no credentials; the session kept working, but the product gate must not break webviews (Risks). Restricted Mode (an unanswered workspace-trust prompt) blocks the integrated terminal, so the product flow should open a trusted folder.
2. The route server passes Tier-2 middleware labels through: `ParseTraefikLabels` collects `traefik.http.middlewares.*` (private/renet/pkg/router/labels.go:144) and `GenerateTier2Routes` emits them (private/renet/pkg/router/routes.go:539). A Tier-2 router with `tls=true` gets the host's wildcard certResolver filled in (private/renet/pkg/router/routes.go:448-475). So the gate needs no new Traefik capability, only an address Traefik can reach.
3. Traefik's forwardAuth does not forward the `Upgrade` header to the auth service (the spike's gate logged `upgrade=-` on every request, WebSocket included), so the gate must decide on the cookie alone, never on whether a request is a WebSocket.
4. Service IPs are assigned by renet at compose time; the spike had to start once, read the gate's `rediacc.service_ip` (127.0.157.195) and start again with it in `.env`. A product gate cannot depend on that dance, which is why Design 1 puts the gate in the route server, whose address is fixed per machine.
5. Existing machinery to reuse: `packages/cli/src/commands/vscode-browser.ts` (218 lines, SSH-tunnel flow), `packages/cli/src/services/core/vscode-server-remote.ts` (389 lines: `ensureServerInstalled`, `launchServer`, `waitForHttpReady`), `packages/cli/src/remote/vscode-server/code-server.ts:10` pins code-server `4.123.0`. The console's who-may-act rule is `useConsoleAccess` (private/account/web/src/pages/console/ConsoleGate.tsx), plan gate `PLAN_METADATA[plan].webConsole` plus role default `MISSING_POLICY_DEFAULT`, the same constant the executor enforces.
6. Per-repo wildcard DNS is created by `repo up` (`Created A record *.vscode-spike.hostinger.rediacc.io` in the spike's output), and per-repo wildcard certificates come from the router's auto-TLS, so a name `vscode.<repo>.<machine>.<baseDomain>` needs no new DNS or certificate step.
7. No plan covers this: `grep -ril 'code-server\|vscode' agent/plans` names only finished vscode CLI work.

## Design

1. **The gate lives in the route server, not in the repo.** `rediacc-router` gains a forwardAuth endpoint on its fixed local address. It verifies a portal-minted token offline with the account Ed25519 public key renet already carries for licences: claims `repo` (GUID), `machine`, `exp` (at most 15 minutes after mint), `nonce`. A valid `?rdc_vscode=<token>` answers 302 with a host-scoped HttpOnly Secure SameSite=Lax cookie holding a router-signed session (sliding, 30 minutes), a valid cookie answers 200, anything else 401. Every decision is made on the cookie, never on `Upgrade` (Context 3).
2. **The editor runs as a container on the repo's own daemon**, so it inherits the repo's isolation, loopback IP and data mount, and the route server discovers it through labels like any service. Image pinned by digest through `npm run pins`; the CLI's `code-server.ts` pin and the container pin move together.
3. **Name**: `vscode.<repo>.<machine>.<baseDomain>` (forks: `vscode-fork-<tag>.<repo>...`, the existing auto-route rule), covered by the per-repo wildcard (Context 6).
4. **Lifetime**: the portal tab heartbeats every 60 s; the router records the last heartbeat per session; a reaper stops the container after 15 minutes without one. `rdc vscode unexpose <ref>` stops it at once.
5. **Who may open it**: the token route reuses the console's plan and role gate (Context 5), so the button, the token and the executor agree.
6. Out of scope (console#522): CF-container-hosted VS Code, NAT'd machines (they keep `rdc serve`), removing local env-var guardrails.

## Boxes

- [x] V1 [writer] renet router: forwardAuth gate endpoint per Design 1 with unit tests for valid, expired, wrong-repo, wrong-signature, replayed-nonce and cookie-only WebSocket cases. Accept: `cd private/renet && go test ./pkg/router/... -run Gate` rc 0
    (ticked) 2026-11-27T07:23:36Z by d778be9d: renet 4e896393 via b67f598470; go test ./pkg/router/... -run Gate rc 0 (22 tests); sub/kind/nonce plants fail rc 1
- [x] V2 [writer] renet: `repository vscode expose|unexpose` function that starts and stops the pinned code-server container on the repo daemon with the Design 2-3 labels pointing at the gate, plus the heartbeat reaper; registry, tier map and generated contract updated. Accept: `cd private/renet && go test ./cmd/renet/... -run Vscode` rc 0 and `npm run ci -- --narrow` rc 0
    (ticked) 2026-11-27T07:23:36Z by d778be9d: renet 4db3c9e9 2cb70045 via b67f598470, contract 50a1f356cb, CLI+pins ba7d42f328; go test router/cmd/functions/license rc 0, tsc rc 0, vitest executor 331 passed, renet tiers/types rc 0 on the landed tree
- [ ] V3 [writer] CLI: `rdc vscode expose <ref>` and `rdc vscode unexpose <ref>` paired with V2, sharing the install code in vscode-server-remote.ts; i18n across locales, cli docs regenerated. Accept: `npm run ci -- --narrow` rc 0
- [x] V4a [writer] Signer method for editor tokens (operator /ask ASKED:2026-11-27T09:21Z, "Add signer method"): a typed `signVscodeToken` in workers/signer/src/index.ts, private/account/src/services/signer-client.ts and license-signer.service.ts, with its own scope check (the token `sub` is a subscription of the calling company and region), payload `{v:1,kind:"vscode",sub,repo,machine,iat,exp<=iat+15m,nonce}` matching the V1 gate, and `signing` exposed in src/container.ts and src/app.ts so the V4 route can reach it. Tests: a foreign subscription refused, a non-vscode kind refused, a licence payload refused by the vscode method and vice versa.
  Accept: the signer Worker and account test files for the new method rc 0, and `npx tsc --noEmit -p private/account/tsconfig.json` rc 0
  After: V1
    (ticked) 2026-11-27T10:53:29Z by d778be9d: commit:51e6d3472b (account 69e56e3e7a gitlink, renet 5a4a9c0723); landed-tree: vitest vscode-token-signer+license-signer-scope 154 passed rc 0, go test ./pkg/router -run Gate rc 0, tsc workers/signer rc 0
- [x] V4 [writer] account: `POST /console/repos/:guid/vscode-token` minting the Design 1 token behind the console plan and role gate, the "Open in VS Code" action on RepoDetail and the 60 s heartbeat; integration test for allowed, plan-refused and role-refused callers. Accept: `cd private/account && npm test -- console-vscode` rc 0
    (ticked) 2026-11-27T13:42:24Z by d778be9d: commit:2a3cf03258; V4 route+portal button (account 9fc81ad9); account console-vscode + web repo-detail-vscode rc 0 landed
- [ ] V5 [writer] e2e on the VM fleet: expose, admit with a fresh token, refuse a stale one, idle reaper stops the container. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.testrun.e2e --test tests/vscode-expose.test.ts --fail-on-skip` rc 0
- [ ] V6 [live] Repeat the spike's idle test against the product path on hostinger: an editor session left idle 15 minutes is still usable and the reaper stops the container after the portal tab closes. Accept: the browser check and `docker ps` on the repo daemon recorded here
- [ ] V7 [live] Tear down the spike repo `vscode-spike` on hostinger once a delete cannot re-render the production backup units through the bench config (agent/plans/PLAN-backup-schedule-origin-guard.md). Accept: `./rdc.sh --config eu-bench repo list -m hostinger` no longer lists vscode-spike and every unit still carries `--expect-account-server https://eu.rediacc.cloud`
- [x] LP-hostinger [live] Fresh hostinger receipt after V1-V3 land.
  Accept: live-proof hostinger renet-live
    (ticked) 2026-11-24T00:03:03Z by ace763dd: live-proof lp-79199c7af404 VERIFIED rc=0 on hostinger at head commit d5c8422010, vm:check vmc-11232310-742652 VERIFIED (278 assertions, renet phase); PLAN-vscode-browser-exposure.md box de4e368a proven live on hostinger
- [ ] LP-bench [live] Fresh bench receipt after V4 lands.
  Accept: live-proof bench account-smoke

## Risks

- VS Code webviews fetch through a service worker without credentials; in the spike those requests were refused by the cookie gate (Context 1). V1's tests cover a webview resource request, and V6 opens a webview (the Welcome page, Markdown preview) and checks it renders.

- A cookie scoped to the repo's hostname is readable by nothing else, but any service in the same repo under the same wildcard could set cookies for its parent domain; the session cookie is host-only (no Domain attribute) for that reason.
- Exposing an editor that can run a terminal is exposing a shell in the repo sandbox: the token's 15-minute mint window, the sliding session and the reaper bound it, and the plan and role gate decide who can mint.
- The route server restarts on every renet update (networking docs), which drops in-memory sessions; sessions are router-signed cookies rather than server state so a restart does not log users out.
