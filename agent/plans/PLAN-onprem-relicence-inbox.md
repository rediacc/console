# PLAN: on-prem relicence through the SSH cert inbox -- one validator for every cert source, strict freshness, a boot quarantine instead of a crash, and the live proof on hostinger
Status: approved -- operator rulings ASKED:2026-11-12T16:30Z, ASKED:2026-11-12T16:56Z and ASKED:2026-11-12T19:34Z (see Rulings); R1-R11 and D1 are landed, L1 and the hostinger proof are open
Depends-On: no-dep -- builds on landed code
Owner: d778be9d
Updated: 2026-11-12
Priority: P1 -- an on-prem box that cannot be relicensed without a redeploy, or that crashes on a bad cert, is an outage the customer cannot repair
Concurrency: parallel -- the landed boxes are done; the open boxes run only against hostinger
Owns: agent/plans/PLAN-onprem-relicence-inbox.md, packages/shared/src/subscription/delegation-cert-id.ts, packages/shared/src/subscription/index.ts, packages/shared/src/subscription/__tests__/delegation-cert-id.test.ts, packages/cli/src/commands/server.ts, packages/cli/src/services/server/**, packages/cli/src/services/account/account-client.ts, packages/cli/src/services/account/__tests__/cert-refused-client.test.ts, packages/cli/templates/elite/**, packages/cli/src/templates/embedded.generated.ts, packages/shared/src/cli-contract/data/i18n/*.json, private/account/src/services/delegation-cert-apply.service.ts, private/account/src/services/cert-inbox.service.ts, private/account/src/services/delegation-cert-loader.service.ts, private/account/src/services/cert-auto-renew.service.ts, private/account/src/entry/on-premise.ts, private/account/src/routes/on-premise-status.ts, private/account/src/errors.ts, private/account/web/src/components/Layout.tsx, private/account/web/src/pages/admin/OnPremiseUpload.tsx, private/account/docs/runtime/on-premise-licensing.md, private/elite/docker-compose.yml, private/elite/BACKUP.md, .ci/rediacc_ci/drills/backup_elite_compose.py, .ci/config/env-manifest.json, packages/www/src/content/docs/*/on-premise.md, packages/www/src/content/docs/*/license-chain.md, packages/www/public/search-index-*.json
Live-Proof: hostinger -- L1 drives the released CLI against the acme.rediacc.io box through `./rdc.sh --config eu-bench`
First-Seen: 2026-11-12

## Context
An on-prem account server took its delegation cert from the `DELEGATION_CERT_BASE64` environment value, so a new cert meant editing the compose env and restarting. Three separate paths then applied a cert with their own checks: the boot loader, `POST /onprem/cert-upload` and auto-renew. A cert that failed at boot stopped the server, leaving no running service to repair it through.

This plan moves every cert source onto one validator and one apply service, adds an SSH-reachable inbox beside the live cert file, and turns a bad cert at boot into a quarantine on the free tier instead of an exit.

## Rulings
- ASKED:2026-11-12T16:30Z: the installer writes `ON_PREMISE_MODE=true`; the exposure of the signing key on the box is accepted and documented.
- ASKED:2026-11-12T16:56Z: relicence goes through an SSH inbox, then validate, then a result file. Freshness is strict: a cert is applied only with a newer `issuedAt`, for the same subscription, and bound to this box's ED25519 key. Every applied or rejected cert is audited and mailed to the owner. There is one validator for the inbox, `POST /onprem/cert-upload` and auto-renew, and no override.
- ASKED:2026-11-12T19:34Z: a bad cert at boot means the server starts on the free tier and quarantines the cert. Licence signing answers 503 `DELEGATION_CERT_REFUSED` until a good cert arrives. The CLI shows the refusal in `server status` and repairs it through `server licence`. The root user sees a banner with the reason, and every box member sees a banner with no detail.
- Standing: one operator, clean break, no compatibility shims (CLAUDE.md rule 2), which is why `DELEGATION_CERT_BASE64` was removed from the server and the template rather than kept as a fallback.

## Design
- **One validator, one apply service.** `CertApplyService` (private/account/src/services/delegation-cert-apply.service.ts) is the only place a cert is decided. It checks the signature, the subscription, binding to this box's ED25519 key and a strictly newer `issuedAt`, writes the live file, audits and mails the owner on every applied or rejected cert, and returns a reason code. The inbox, the upload route and auto-renew call it; none has its own check. The shared `delegationCertId` names a cert the same way in the CLI and the server (packages/shared/src/subscription/delegation-cert-id.ts).
- **The cert inbox.** `cert-inbox.service.ts` watches an inbox directory beside the live cert and writes a result file per drop. The boot order decides the inbox before the server serves. The server no longer reads `DELEGATION_CERT_BASE64`.
- **The CLI.** `rdc server licence`, `install`, `upgrade` and `status` deliver the cert through the inbox and confirm its id from `GET /onprem/cert-status` (`certId`). `upgrade` migrates a leftover `DELEGATION_CERT_BASE64`. The elite template drops that variable and creates the inbox.
- **Boot quarantine.** A cert refused at boot is moved to `delegation-cert.rejected.json`, a boot-rejected marker is written, the refusal is logged and mailed, and the server starts on the free tier. Licence signing (repo issue, batch, renew, machine activation) answers 503 `DELEGATION_CERT_REFUSED` until a cert dropped in the inbox repairs it against the adopted subscription.
- **Visibility.** `GET /onprem/cert-status` gains `bootRejected` for root; the root cert page shows the reason and the repair step; `GET /onprem/licensing-state` returns `{degraded}` to every signed-in member and the layout shows a detail-free banner. `rdc server status` reads the marker and prints REFUSED.

## Tasks
- [x] R1 [writer] The shared validator, `CertApplyService` and `delegationCertId` (Design: one validator).
  Owns: packages/shared/src/subscription/delegation-cert-id.ts, packages/shared/src/subscription/index.ts, packages/shared/src/subscription/__tests__/delegation-cert-id.test.ts, private/account/src/services/delegation-cert-apply.service.ts, private/account/src/services/delegation-cert-loader.service.ts, private/account/src/services/onprem-extras.ts, private/account/tests/integration/delegation-cert-apply.test.ts
  Accept: `cd private/account && npx vitest run tests/integration/delegation-cert-apply.test.ts && npm run typecheck` rc 0. Covered: an older `issuedAt`, another subscription and a cert bound to another key are each rejected with their reason code (control: no apply service before the change).
    (landed) commit:4be8ec4e5f (shared delegationCertId); account 048e81e via gitlink commit:d8f8e97d42
- [x] R2 [writer] The upload route and auto-renew apply every cert through `CertApplyService`; `GET /onprem/cert-status` returns `certId`.
  Owns: private/account/src/routes/on-premise-status.ts, private/account/src/services/cert-auto-renew.service.ts, private/account/tests/integration/on-premise-status.test.ts, private/account/tests/integration/cert-auto-renew.test.ts, private/account/tests/integration/bootstrap-mode.test.ts
  Accept: `cd private/account && npx vitest run tests/integration/on-premise-status.test.ts tests/integration/cert-auto-renew.test.ts tests/integration/bootstrap-mode.test.ts && npm run typecheck` rc 0.
    (landed) account e44f3e2 via gitlink commit:d8f8e97d42
- [x] R3 [writer] The cert inbox service and the boot order that decides the inbox before the server serves; `DELEGATION_CERT_BASE64` removed from the server.
  Owns: private/account/src/services/cert-inbox.service.ts, private/account/src/entry/on-premise.ts, private/account/src/routes/on-premise-index.ts, private/account/src/types/env.ts, private/account/tests/integration/cert-inbox.test.ts
  Accept: `cd private/account && npx vitest run tests/integration/cert-inbox.test.ts tests/integration/bootstrap-mode.test.ts && npm run typecheck` rc 0.
    (landed) account 8bdc6f1 via gitlink commit:d8f8e97d42
- [x] R4 [writer] `rdc server licence`, `install`, `upgrade` and `status` deliver the cert through the inbox and confirm its id.
  Owns: packages/cli/src/commands/server.ts, packages/cli/src/services/server/**, packages/shared/src/cli-contract/data/i18n/*.json
  Accept: `cd packages/cli && npx vitest run src/services/server` and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.
    (landed) commit:c8be2b24dc
- [x] R5 [writer] The elite template drops `DELEGATION_CERT_BASE64` and creates the cert inbox.
  Owns: packages/cli/templates/elite/**, packages/cli/src/templates/embedded.generated.ts, packages/cli/src/services/server/__tests__/helpers.test.ts
  Accept: `cd packages/cli && npx vitest run src/services/server/__tests__/helpers.test.ts` rc 0.
    (landed) commit:0bf0e1e1ca
- [x] R6 [writer] The drills and the private/elite seed take the cert through the inbox; the variable leaves the env manifest.
  Owns: .ci/rediacc_ci/drills/backup_elite_compose.py, .ci/rediacc_ci/drills/backup_onprem.py, .ci/rediacc_ci/tests/test_drills_backup_elite_compose.py, .ci/config/env-manifest.json, private/elite/docker-compose.yml, private/elite/BACKUP.md, private/elite/scripts/test-credentials.sh
  Accept: `python3 -m pytest .ci/rediacc_ci/tests/test_drills_backup_elite_compose.py` rc 0.
    (landed) commit:6ef2ef7717 (drills); elite e64733b via gitlink commit:d8f8e97d42
- [x] R9 [writer] The boot quarantine and the 503 `DELEGATION_CERT_REFUSED` on licence signing, with the shared marker reader (Ruling 19:34Z).
  Owns: private/account/src/entry/on-premise.ts, private/account/src/errors.ts, private/account/src/services/cert-inbox.service.ts, private/account/src/services/delegation-cert-apply.service.ts, private/account/src/services/delegation-cert-loader.service.ts, private/account/src/services/subscription.service.ts, private/account/tests/integration/boot-quarantine.test.ts
  Accept: `cd private/account && npx vitest run tests/integration/boot-quarantine.test.ts tests/integration/cert-inbox.test.ts && npm run typecheck` rc 0. Covered: a bad cert at boot starts the server on the free tier and signing answers 503.
    (landed) account 4328e3d via gitlink commit:7bf848bbc0
- [x] R10 [writer] `rdc server status` and `licence` read the boot-refusal marker, the account client names `rdc server licence` on `DELEGATION_CERT_REFUSED`, and the strings reach the 13 CLI locales.
  Owns: packages/cli/src/commands/server.ts, packages/cli/src/services/server/**, packages/cli/src/services/account/account-client.ts, packages/cli/src/services/account/__tests__/cert-refused-client.test.ts, packages/shared/src/cli-contract/data/i18n/*.json
  Accept: `cd packages/cli && npx vitest run src/services/server src/services/account/__tests__/cert-refused-client.test.ts` rc 0.
    (landed) commit:0818a99077 (CLI status and licence) and commit:781a29e2f2 (13-locale strings)
- [x] R11 [writer] `bootRejected` on `GET /onprem/cert-status`, the root banner with reason and repair, and the detail-free degraded banner for every member.
  Owns: private/account/src/routes/on-premise-status.ts, private/account/web/src/api/endpoints.ts, private/account/web/src/api/types.ts, private/account/web/src/components/Layout.tsx, private/account/web/src/pages/admin/OnPremiseUpload.tsx, private/account/web/src/pages/__tests__/onprem-cert-refused-banner.test.tsx, private/account/tests/integration/on-premise-status.test.ts
  Accept: `cd private/account && npx vitest run tests/integration/on-premise-status.test.ts && cd web && npx vitest run src/pages/__tests__/onprem-cert-refused-banner.test.tsx` rc 0.
    (landed) account 7a9e23a via gitlink commit:370c26926c
- [x] D1 [writer] The docs: the cert-upload reason codes and the inbox relicence path, then the inbox and boot quarantine in `on-premise.md`, naturalized into the 12 locales, with the search index regenerated.
  Owns: packages/www/src/content/docs/*/on-premise.md, packages/www/src/content/docs/*/license-chain.md, packages/www/public/search-index-*.json
  Accept: `npm run check:i18n` rc 0 and the www build rc 0.
    (landed) commit:c09aaca393 (English reason codes) and commit:6f08c85a97 (12 locales); commit:d4b708d161 (English inbox and quarantine) and commit:416242399d (12 locales); commit:da20938bbf (search index)
- [ ] L1 [live] hostinger acme.rediacc.io, through `./rdc.sh --config eu-bench`: `server upgrade` migrates any leftover `DELEGATION_CERT_BASE64`; `server licence` with the current cert answers already-current; a control with an older cert is rejected `not-newer` and the live cert is unchanged; after a revoke and reissue, `server licence` is applied and the `certId` is confirmed. Then a forced bad live file: the server stays up on the free tier, `server status` shows REFUSED, and `server licence` repairs it.
  Owns: none (runs only)
  Accept: each step's CLI output and `GET /onprem/cert-status` read back on the box (`certId`, `bootRejected`), the audit row and the owner mail for each applied and rejected cert, and the final state back on the original licence with no leftover quarantine file.
- [ ] LP-hostinger [live] The live-proof record for the Live-Proof header.
  Owns: none (runs only)
  Accept: live-proof hostinger
