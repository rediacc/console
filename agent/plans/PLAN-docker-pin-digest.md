# PLAN: a docker pin bump moves the image digest along with the tag
Status: executing
Owner: d778be9d
Updated: 2026-10-30
Epic: 9f92c43e (worklist #d4b2a051)
Priority: P1 -- workers/proxy/Dockerfile's FROM line says node 26.13.0, but its digest pulls 26.12.0. Pins bump and every gate stayed green. Any other digest-pinned leaf would drift the same way, without a sound.
Depends-On: no-dep -- the driver, its selftest, the registry entry and the gate all change inside this plan
Owns: agent/plans/PLAN-docker-pin-digest.md, scripts/lib/pins/drivers/docker.ts, scripts/lib/pins/drivers/shared.ts (T8_MUTANTS only), scripts/lib/pins/drivers/selftest.ts (dockerCases only), scripts/lib/docker-hub.ts (new), scripts/gates/check-docker-image-freshness.ts, .ci/config/pins.json (the image:proxy-node entry only), .ci/rediacc_ci/tests/gates/test_gate_pin_family_drivers.py (MUTANTS only), workers/proxy/Dockerfile
Concurrency: parallel -- no other plan owns these files. Inside the plan the order is D1 then D2 then G1 then R1. S1 can run at any time.

## Context (anchors checked 2026-10-30)
- The rewrite only ever sees the tag. The registry site for image:proxy-node is `"match": "^FROM (?<value>node:[^@\\s]+)@sha256:[0-9a-f]{64}$"` with role `version` (.ci/config/pins.json:3625). Its name even says "tag only; the digest is pinned beside it" (.ci/config/pins.json:3607). The digest sits outside the named group. scripts/lib/pins/drivers/docker.ts:149-153 calls `planLeafSites(entry, { version: image:tag }, ctx)`, and planLeafSites rewrites only the group of each site it gets (scripts/lib/pins/driver.ts:252-288, `rewriteRegexSite` at :277). No `digest` role exists, and docker.ts never reads a digest. So the old `@sha256:` survives every bump. workers/proxy/Dockerfile:16-18 claims "`npm run pins -- bump image:proxy-node` moves the tag and the digest together", which is false, and still names 26.12.0.
- No code in scripts/ or .ci/rediacc_ci resolves a registry digest today. I searched for Docker-Content-Digest, /manifests/, registry-1 and auth.docker.io. Only an operator hint exists, at scripts/gates/check-unverified-downloads.ts:302. Two code paths already talk to Docker Hub:
  - the driver, through `Deps.json` (scripts/lib/pins/drivers/shared.ts:61-70, realDeps :77-95; the tag listing is at docker.ts:104-109);
  - the gate, through an authed `fetch` with a token-then-anonymous retry (scripts/gates/check-docker-image-freshness.ts:265-336). The gate also normalises the repo name (`dockerHubRepo` :256), which repeats docker.ts:103.
- Measured: `GET hub.docker.com/v2/repositories/library/node/tags/<tag>` returns a top-level `digest`, which is the multi-arch index digest. For `26.13.0-slim` it is `sha256:e4db4c91...02c39`, the same value `imagetools inspect` gives. For `26.12.0-slim` it is `sha256:e556a144...` (the stale value in the tree). The per-arch digests sit under `images[]` and must not be read.
- Gates:
  - check:ci-pin-registry is offline: it checks shape and site counts (scripts/gates/check-pin-registry.ts), so it cannot see tag/digest agreement.
  - check:ci-pin-freshness judges versions only.
  - check:ci-docker-image-freshness (package.json:316) already makes network reads to Hub for every FROM, and its anti-vacuity rule already makes an unlisted image a FAILURE (scripts/gates/check-docker-image-freshness.ts:20-24). Its `parsePins` regex (:186-199) stops at the tag and drops `@sha256:`. That makes it the natural home for the agreement check.
- Selftests:
  - scripts/lib/pins/drivers/selftest.ts runs `allCases(mutant)` once clean, then once per T8_MUTANTS entry. Each mutant must turn at least one control red (:956-979).
  - `dockerCases` (:756-) builds a temporary `tree()` with real registry entries (`entry(id)`, :45) and stubs Hub through `deps({ json })`.
  - The existing mutant `docker-no-drain` (scripts/lib/pins/drivers/shared.ts:38,49; docker.ts:163) is the template.
  - The mutant list also appears in .ci/rediacc_ci/tests/gates/test_gate_pin_family_drivers.py:14-23.
  - The selftest runs through check:ci-standalone-selftests (scripts/gates/check-standalone-selftests.ts:100).
- Other digest references in the tree:
  - .devcontainer/Dockerfile:769 `COPY --from=tsl0922/ttyd@sha256:9355...` has no tag on the line; the tag is only named in the comment at :768 (`1.7.8-alpine`).
  - private/elite/docker-compose.yml:107 and :157 `rustfs/rustfs@sha256:41fe...` have no tag; the comment at :100 holds only a `<tag>` placeholder.
  - .ci/rediacc_ci/spikes/do_policy_spike.py:88 is a string inside a spike script.
  - There are no `@sha256` refs in .github or any other compose file.
  - So workers/proxy/Dockerfile:20 is the only line that carries both a tag and a digest.

## Decision
- Add a `digest` site role. image:proxy-node gets a second site on the same line: `^FROM node:[^@\s]+@(?<value>sha256:[0-9a-f]{64})$`. planLeafSites already chains several sites in one file (driver.ts:262 `texts.get(k)`), so the tag and the digest land in one write.
- Create scripts/lib/docker-hub.ts, the single place for this logic:
  - `hubRepo(image)` normalises the repo name;
  - `hubTagUrl(base, repo, tag)` builds the per-tag URL;
  - `parseTagDigest(json)` reads the top-level `digest`, checks it against `^sha256:[0-9a-f]{64}$`, and returns null otherwise.
  - The driver calls it through `deps.json`, so selftests make no network reads. The gate calls it through its existing authed fetch. Neither keeps its own copy.
- The driver refuses to plan when a leaf has a `digest` site and Hub gives no digest for the target tag. It also refuses when a version site's text carries `@sha256:` but the entry has no `digest` site, so a registry gap cannot hide this bug again.
- Fold the agreement check into check:ci-docker-image-freshness. A network read in CI fails closed: 429, 5xx, a missing `digest` or a malformed `digest` all count as RED (unknown is never a pass), the same as the gate's listing rule. A digest-only ref with no tag on its line is listed as "untagged, agreement not checkable", with no verdict either way.

## Boxes
- [ ] D1 Add scripts/lib/docker-hub.ts with `hubRepo`, `hubTagUrl` and `parseTagDigest` as described in the Decision. Replace docker.ts:103 and check-docker-image-freshness.ts:256 with `hubRepo`. Accept: `npx tsc --noEmit -p . && npm run check:ci-docker-image-freshness`
- [ ] D2 Make the docker driver resolve the digest:
  - In `plan`, for each site with role `digest`, call `deps.json(hubTagUrl(...), image)` and pass `{ version, digest }` to planLeafSites. Throw `PlanRefused("<id>: Docker Hub gives no digest for <image>:<tag>; refusing to move the tag without it")` on null or a throw.
  - Also refuse a version site whose text has `@sha256:` when the entry has no digest site.
  - Add the `digest` site to image:proxy-node in .ci/config/pins.json and drop "tag only" from its name.
  - Accept: `npx tsx scripts/lib/pins/drivers/selftest.ts && npm run check:ci-pin-registry && npm run pins -- plan image:proxy-node`. The plan output must show both `version` and `digest` changes.
- [ ] T1 Add the mutant `docker-keep-digest` to T8_MUTANTS (scripts/lib/pins/drivers/shared.ts:28-50, plus a doc line) and to the MUTANTS tuple in test_gate_pin_family_drivers.py. In docker.ts the mutant supplies the old digest instead of the resolved one. Add three new dockerCases controls using `entry('image:proxy-node')`:
  - (a) A tree holds `FROM node:26.12.0-slim@sha256:<a*64>`, and a Hub stub answers the listing plus `/tags/26.13.0-slim` → `{digest: "sha256:<b*64>"}`. The plan must write exactly `FROM node:26.13.0-slim@sha256:<b*64>`.
  - (b) A stub with no `digest`, or with an `images[]`-only digest, must give a `PlanRefused` that names the tag.
  - (c) An entry whose version site sees `@sha256:` but which has no digest site is refused.
  - Accept: `npx tsx scripts/lib/pins/drivers/selftest.ts`. Its output must include `MUTANT docker-keep-digest turns 1+ control(s) red`. Also run `PINS_T8_MUTANT=docker-keep-digest npx tsx scripts/lib/pins/drivers/selftest.ts; test $? -eq 1 && npm run check:ci-standalone-selftests`
- [ ] G1 Fold the agreement check into scripts/gates/check-docker-image-freshness.ts:
  - Extend `Pin` with `digest?` by parsing `@(sha256:[0-9a-f]{64})` after the tag in `parsePins` (:190). Do the same for compose `image: <img>:<tag>@sha256:` lines in the tracked compose files.
  - For each pin with a digest, fetch `hubTagUrl` with the same token-then-anonymous attempts as `listHubTags`. A mismatch is RED and names `npm run pins -- bump <leaf> --to <tag>`. A failed lookup is RED with its cause.
  - Update the header to state the fail-closed rule.
  - Add selftest controls: a pure `digestFindings(pins, answers)` function that flags a mismatch (the control proving the check can fail), flags a missing answer, and passes a match.
  - Accept: `npm run check:ci-docker-image-freshness` is green after R1. Before R1 it must be red on workers/proxy/Dockerfile:20. Run it at HEAD first and record that red as the control on the real tree.
- [ ] R1 Repair workers/proxy/Dockerfile through the fixed bump, not by hand:
  - Run `npm run pins -- bump image:proxy-node --to node:26.13.0-slim --major --reason "re-resolve the digest left at 26.12.0 by #d4b2a051"`. If the core refuses because the target equals the current tag, take the newest 26.x.y-slim candidate that `npm run pins -- status image:proxy-node` offers instead. Do not hand-edit to get round the refusal.
  - Reword the comment at workers/proxy/Dockerfile:16-18 so it names no version.
  - Accept: `grep -q 'e4db4c914bf8ad241bd24804fc25d272d89bad97e68cdc8a1414862790a02c39' workers/proxy/Dockerfile || <newest tag's digest>`, then `docker buildx imagetools inspect $(sed -n 's/^FROM \(node:[^@]*\)@.*/\1/p' workers/proxy/Dockerfile) --format '{{.Manifest.Digest}}'` must equal the digest in the file. Then `npm run check:ci-docker-image-freshness && npm run pins -- verify`
- [ ] S1 Sweep the siblings:
  - Check that the ttyd digest at .devcontainer/Dockerfile:769 still equals `docker buildx imagetools inspect tsl0922/ttyd:1.7.8-alpine` (the tag named in the comment at :768). Check private/elite/docker-compose.yml:107 and :157 against the rustfs tag the elite stack records.
  - Record each result here. A mismatch gets its own worklist item; do not hand-edit here.
  - Confirm that G1 lists both refs as "untagged".
  - Accept: `docker buildx imagetools inspect tsl0922/ttyd:1.7.8-alpine --format '{{.Manifest.Digest}}' | grep -q 9355735b28a407fe7fb09597f6773d5550f2502259d22b350a2e2460125f9072 && npm run check:ci-unverified-downloads && npm run check:ci-docker-image-freshness`

## Risks
- `bump --to` may refuse a target equal to the current tag, because the driver's inspect lists only newer tags (docker.ts:122). If so, R1 takes the newest patch, which is a real bump. A same-tag "re-digest" verb is out of scope; file it as a worklist item if it turns out to be needed.
- On a busy day, Hub rate limits could turn G1 red. That is the intended fail-closed outcome. The existing DOCKERHUB_TOKEN env (check-docker-image-freshness.ts:4) is the mitigation.

### Critical Files for Implementation
- /home/developer/console/scripts/lib/pins/drivers/docker.ts
- /home/developer/console/scripts/lib/pins/drivers/selftest.ts
- /home/developer/console/scripts/gates/check-docker-image-freshness.ts
- /home/developer/console/.ci/config/pins.json
- /home/developer/console/scripts/lib/pins/driver.ts
