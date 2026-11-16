# PLAN: zot pull-through cache commits manifest-list images and serves them from cache (#96)

Status: proposed -- converted from console#523 (item #96) on 2026-11-16; awaiting operator approval
Owner: e0f36861
First-Seen: 2026-11-16
Depends-On: PLAN-datastore-migrate-correctness.md
Priority: P3 -- pulls still succeed through containerd's upstream fallback, so nothing is down; the cache's fork/migrate purpose (spec/04 section 7b) is defeated until this lands
Concurrency: parallel -- zot config renderer, its goldens and suite 15 only; the conditional bump files are shared with the datastore plan's pin box, hence the Depends-On
Owns: agent/plans/PLAN-zot-manifest-list-commit.md, private/renet/pkg/kube/registry/zot.go, private/renet/pkg/kube/registry/zot_golden_test.go, private/renet/pkg/kube/registry/zot_verify_test.go, private/renet/pkg/kube/registry/testdata/zot-config-*.golden, packages/e2e-tests/tests/kube/15-k8s-repo.test.ts, private/renet/Dockerfile, private/renet/embed-assets.lock.json, private/renet/pkg/embed/credits_data.go, packages/cli/src/data/third-party-credits.json, private/renet/pkg/infra/docker/service.go, private/renet/pkg/infra/opsconfig/config.go
Live-Proof: hostinger -- the zot config renderer under private/renet/pkg/kube/registry (and a possible embedded zot bump) is the renet surface, whose only live target is hostinger; the CLI credits JSON under packages/cli/src is the cli surface, which hostinger admits too.
Source: https://github.com/rediacc/console/issues/523

## Ask

console#523 item #96: renet's embedded zot pull-through cache SERVES manifest-list images but fails to COMMIT them ("invalid manifest content", zot v2, seen for k3s's own images and busybox). Every pull re-fetches upstream, and the serve path was seen to hang for the whole 360 s test budget on a single manifest GET. Suite 15 keeps the serve and catalog checks as loud tripwires to flip into asserts when the cache works. The ask is to make the cache commit and serve from local storage, then flip the tripwires.

No plan covers it: `grep -rlI zot agent/plans` hits only `_done/` plans about the binary's download, pins and a retired-terms sweep. It depends on PLAN-datastore-migrate-correctness.md because that plan's E1 makes the zot container image literal a pins site, and a bump here must move it too.

## Context (checked 2026-11-16 against the tree)

1. `packages/e2e-tests/tests/kube/15-k8s-repo.test.ts:765-806` (R9): the containerd-config assert and the busybox pod smoke are hard asserts; the manifest GET (`:782-784`, bounded `--max-time 60`) and `/v2/_catalog` (`:785-787`) only `console.warn` a tripwire line (`:788-790`). R1 (`:357-372`) brings zot up with `upstreams: docker.io,ghcr.io,quay.io`, no datastore, so the blob store is `DefaultStorageDir` `/var/lib/rediacc/zot` (`private/renet/pkg/kube/registry/zot.go:51`, `private/renet/cmd/renet/kube_registry.go:55-58`).
2. `private/renet/pkg/kube/registry/zot.go:151-208` (`RenderConfig`): one sync registry per upstream with `onDemand: true`, `tlsVerify: true`, `maxRetries: 3`, `retryDelay: "5m"`, no `content` filter; storage `gc: true`, `dedupe: true`; log level `warn`; no `http` compat setting and no streaming or manifest-check settings. The same renderer feeds the ops-loop zot container (`private/renet/pkg/infra/docker/service.go:313`). Goldens: `pkg/kube/registry/testdata/zot-config-default.json.golden`, `zot-config-single.json.golden`.
3. #96 was observed on the embedded zot 2.1.18: renet's Dockerfile at the #520 squash (console fe3d2f8a7f, renet 9cb5cb18) carries `ARG ZOT_VERSION=2.1.18`. The embedded zot has since moved to 2.1.23 (renet de34d3c5 took 2.1.18 to 2.1.20 on 2026-08-06; today `private/renet/Dockerfile:292,312`, `embed-assets.lock.json:110`). Nobody has re-measured #96 on 2.1.23; the tripwire's last output is not on record.
4. Upstream zot release notes (github.com/project-zot/zot/releases, read 2026-11-16; v2.1.23 of 02 Nov is the newest, so no newer release exists to bump to) list sync fixes after 2.1.18 that bear on #96:
   - 2.1.19: "fix(sync): predict post-OCI digest for on-demand skip checks", "fix(sync): enable exponential HTTP retry backoff via maxRetryDelay", "fix(sync): surface the rejected media type in manifest sync failures".
   - 2.1.21: "feat(sync): add manifestCheckInterval to throttle on-demand upstream manifest checks", "fix(sync): dedupe on-demand sync with singleflight", "fix(compat): preserve Docker media types through MetaDB and search", "fix(storage): honor docker2s2 compat media types in delete/prune/scrub".
   - 2.1.22: "feat(sync): add onDemandInBackground for non-blocking on-demand sync", "fix(sync): surface on-demand upstream errors".
   - 2.1.23: "feat(sync): stream image blobs to clients during on-demand sync".
5. zot's v2.1.23 `examples/README.md` (read 2026-11-16) documents `stream` ("serve an on-demand image to the client while it downloads instead of after it is synced"), `maxConcurrentStreams` (must agree across streaming registries), `manifestCheckInterval` ("the default is 0, which keeps checking upstream on every request"), `onDemandInBackground` (warned against when zot is the client's only source), and `preserveDigest` as deprecated and ignored. The exact key and placement of the Docker-media-type compat switch (`docker2s2`) were not found in that README and are unverified.
6. A default `manifestCheckInterval` of 0 alone explains "every pull re-fetches upstream" for the manifest check, independent of the commit failure. `retryDelay: "5m"` with `maxRetries: 3` on a synchronous on-demand path is a plausible cause of the multi-minute hang (hypothesis, Z1 checks it).

## Design

**Measure before changing.** Z1 re-runs suite 15 on the current 2.1.23 binary with the current config and records the tripwire line, `journalctl -u rediacc-zot` at the run, and whether `/var/lib/rediacc/zot/library/busybox/index.json` holds tag 1.36 after the pod pull. That separates what 2.1.19-2.1.23 already fixed from what the config must fix.

**Config, not a bump.** 2.1.23 is the newest release, so the fix is in `RenderConfig`. The candidate set, each adopted only if Z1/Z3 shows it is needed and Z2 confirms the key against zot 2.1.23's config schema:
- `manifestCheckInterval` per registry (proposed `"1h"`) so a committed tag is served without an upstream round trip.
- `stream: true` with one shared `maxConcurrentStreams`, so a first pull is served while it downloads instead of after.
- `maxRetries`/`retryDelay` replaced by a short bounded retry (`maxRetryDelay`), so a failing sync cannot hold a client for minutes.
- The Docker media type compat switch, if Z1 still shows "invalid manifest content" for Docker manifest lists.
- `onDemandInBackground` is rejected: zot is the mirror k3s pulls from first, and the zot docs warn against it for a client's only source.
- Per-upstream `content` routing is out of scope unless Z1 shows ghcr/quay pulls stalling behind docker.io 404s.

**Proof that the config is accepted.** A Go test runs the embedded zot binary's `verify` subcommand on each rendered golden, so a misspelled key fails in CI instead of on a machine.

**Tripwires become asserts.** In R9 the manifest GET must return 200 within the bound, the catalog must list `library/busybox`, the blob store must hold the committed index, and a second GET must be served without an upstream check (a fast repeat, plus no new sync line in the journal). The `console.warn` and the "#96 tripwire" comments are deleted.

**Conditional bump.** If a zot release newer than 2.1.23 appears before Z3 and Z1 shows a residue that only an upstream fix can close, it moves through `npm run pins -- bump embed:zot` (which, after the datastore plan's E1, also moves the container image literal). Otherwise the bump files stay untouched.

## Boxes

- [ ] Z1 [live] Re-measure #96 on the current tree: run suite 15 on the local KVM fleet (ops VMs are shared with another agent: no `ops down`, only the suite's own machine), then record the R9 tripwire line, the zot journal for the run, and `ls /var/lib/rediacc/zot/library/busybox` on the node, in the plan's Context with the date. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.testrun.e2e --workers 1 --test tests/kube/15-k8s-repo.test.ts` rc 0 and the three observations recorded
- [ ] Z2 [writer] Confirm each candidate key (Design) against zot 2.1.23's sync and http config structs and `examples/config-sync*.json` at tag v2.1.23, and record the source line of each in the commit body; drop any key that does not exist. Accept: the commit body cites a v2.1.23 file and line per adopted key
- [ ] Z3 [writer] `RenderConfig` emits the adopted keys; both zot config goldens are regenerated by the golden test's update flag and reviewed by diff. Accept: `cd private/renet && go test ./pkg/kube/registry -count=1` rc 0
- [ ] Z4 [writer] `zot_verify_test.go`: run the embedded zot binary's `verify` on each rendered config (skip with a named reason only when the binary is not extracted, and the skip reason names the extraction command). Accept: `cd private/renet && go test ./pkg/kube/registry -run TestZotVerify -count=1 -v` rc 0 with the test reported PASS, not SKIP
- [ ] Z5 [writer] Suite 15 R9: serve and catalog become hard asserts, plus the committed-index check and the second-GET-from-cache check per Design; the tripwire `console.warn` and its comments go. Accept: `npx tsc --noEmit -p packages/e2e-tests` rc 0
- [ ] Z6 [live] Suite 15 green on the local KVM fleet with Z3-Z5 landed (same shared-fleet rule as Z1). Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.testrun.e2e --workers 1 --test tests/kube/15-k8s-repo.test.ts` rc 0
- [ ] Z7 [writer] Conditional: only when Z1/Z6 leave a residue that a zot release newer than 2.1.23 fixes, `npm run pins -- bump embed:zot` and re-run Z4 and Z6; otherwise tick with the measured reason no bump was taken. Accept: `npm run pins -- verify` rc 0 and either the bump commit or the recorded no-bump reason
- [ ] V1 [live] VM tier for the renet surface before the live receipt. Accept: `npm run vm:check -- --changed` rc 0 with a VERIFIED receipt
- [ ] LP-hostinger [live] Fresh hostinger receipt after V1 on the same tree; provisioning a branch renet restarts the router and daemons on hostinger.
  Accept: live-proof hostinger renet-live

## Risks

- Z1 may show that 2.1.23 already commits and serves; then the plan shrinks to the manifest-check interval, the verify test and the flipped asserts, and Z2-Z3 record that.
- `stream` and `maxConcurrentStreams` are new upstream features (2.1.23); a regression in them would land on every machine's pulls. The suite-15 pod smoke and Z6 guard it, and containerd still falls back to upstream on a mirror error.
- A non-zero `manifestCheckInterval` serves a moved tag (for example `latest`) stale for up to the interval. Pinned tags and digests are unaffected; the interval is a renderer constant and can be shortened.
- The ops-loop zot container shares `RenderConfig` and still runs the 2.1.18 image until the datastore plan's E1 lands; a key that 2.1.18 rejects would break that container. The Depends-On orders E1 first.
