# PLAN: a docker pin bump moves the image digest along with the tag
Status: executing
Owner: d778be9d
Updated: 2026-10-30
Epic: 9f92c43e (worklist #d4b2a051)
Priority: P1 -- workers/proxy/Dockerfile's FROM line says node 26.13.0, but its digest pulls 26.12.0. Pins bump and every gate stayed green. Any other digest-pinned leaf would drift the same way, without a sound.
Depends-On: no-dep -- the driver, its selftest, the registry entry and the gate all change inside this plan
Owns: agent/plans/PLAN-docker-pin-digest.md, scripts/lib/pins/drivers/docker.ts, scripts/lib/pins/drivers/shared.ts (T8_MUTANTS only), scripts/lib/pins/drivers/selftest.ts (dockerCases only), scripts/lib/docker-hub.ts (new), scripts/gates/check-docker-image-freshness.ts, .ci/config/pins.json (the image:proxy-node entry only), .ci/rediacc_ci/tests/gates/test_gate_pin_family_drivers.py (MUTANTS only), workers/proxy/Dockerfile
Live-Proof: bench -- workers/proxy/Dockerfile builds the proxy worker image, which deploys to bench first; the pins driver itself is local tooling
Concurrency: parallel -- no other plan owns these files. Inside the plan the order is D1 then D2 then G1 then R0 then R1, then X1. S1 can run at any time.

## Context (anchors checked 2026-10-30)
- The rewrite only ever sees the tag. The registry site for image:proxy-node is `"match": "^FROM (?<value>node:[^@\\s]+)@sha256:[0-9a-f]{64}$"` with role `version` (.ci/config/pins.json:3625). Its name even says "tag only; the digest is pinned beside it" (.ci/config/pins.json:3607). The digest sits outside the named group. scripts/lib/pins/drivers/docker.ts:149-153 calls `planLeafSites(entry, { version: image:tag }, ctx)`, and planLeafSites rewrites only the group of each site it gets (scripts/lib/pins/driver.ts:252-288, `rewriteRegexSite` at :277). No `digest` role exists, and docker.ts never reads a digest. So the old `@sha256:` survives every bump. workers/proxy/Dockerfile:16-18 claims "`npm run pins -- bump image:proxy-node` moves the tag and the digest together", which is false, and still names 26.12.0.
- No code in scripts/ or .ci/rediacc_ci resolves a registry digest today: a search for Docker-Content-Digest, /manifests/, registry-1 and auth.docker.io finds none. Only an operator hint exists, at scripts/gates/check-unverified-downloads.ts:302. Two code paths already talk to Docker Hub:
  - the driver, through `Deps.json` (scripts/lib/pins/drivers/shared.ts:61-70, realDeps :77-95; the tag listing is at scripts/lib/pins/drivers/docker.ts:104-109);
  - the gate, through an authed `fetch` with a token-then-anonymous retry (scripts/gates/check-docker-image-freshness.ts:265-336). The gate also normalises the repo name (`dockerHubRepo` :256), which repeats scripts/lib/pins/drivers/docker.ts:103.
- Measured: `GET hub.docker.com/v2/repositories/library/node/tags/<tag>` returns a top-level `digest`, which is the multi-arch index digest. For `26.13.0-slim` it is `sha256:e4db4c91...02c39`, the same value `imagetools inspect` gives. For `26.12.0-slim` it is `sha256:e556a144...` (the stale value in the tree). The per-arch digests sit under `images[]` and must not be read.
- Gates:
  - check:ci-pin-registry is offline: it checks shape and site counts (scripts/gates/check-pin-registry.ts), so it cannot see tag/digest agreement.
  - check:ci-pin-freshness judges versions only.
  - check:ci-docker-image-freshness (package.json:316) already makes network reads to Hub for every FROM, and its anti-vacuity rule already makes an unlisted image a FAILURE (scripts/gates/check-docker-image-freshness.ts:20-24). Its `parsePins` regex (:186-199) stops at the tag and drops `@sha256:`. That makes it the natural home for the agreement check.
- Selftests:
  - scripts/lib/pins/drivers/selftest.ts runs `allCases(mutant)` once clean, then once per T8_MUTANTS entry. Each mutant must turn at least one control red (:956-979).
  - `dockerCases` (:756-) builds a temporary `tree()` with real registry entries (`entry(id)`, :45) and stubs Hub through `deps({ json })`.
  - The existing mutant `docker-no-drain` (scripts/lib/pins/drivers/shared.ts:38,49; scripts/lib/pins/drivers/docker.ts:163) is the template.
  - The mutant list also appears in .ci/rediacc_ci/tests/gates/test_gate_pin_family_drivers.py:14-23.
  - The selftest runs through check:ci-standalone-selftests (scripts/gates/check-standalone-selftests.ts:100).
- Other digest references in the tree:
  - .devcontainer/Dockerfile:769 `COPY --from=tsl0922/ttyd@sha256:9355...` has no tag on the line; the tag is only named in the comment at :768 (`1.7.8-alpine`).
  - private/elite/docker-compose.yml:107 and :157 `rustfs/rustfs@sha256:41fe...` have no tag; the comment at :100 holds only a `<tag>` placeholder.
  - .ci/rediacc_ci/spikes/do_policy_spike.py:88 is a string inside a spike script.
  - There are no `@sha256` refs in .github or any other compose file.
  - So workers/proxy/Dockerfile:20 is the only line that carries both a tag and a digest.

## Decision
- Add a `digest` site role. image:proxy-node gets a second site on the same line: `^FROM node:[^@\s]+@(?<value>sha256:[0-9a-f]{64})$`. planLeafSites already chains several sites in one file (scripts/lib/pins/driver.ts:262 `texts.get(k)`), so the tag and the digest land in one write.
- Create scripts/lib/docker-hub.ts, the single place for this logic:
  - `hubRepo(image)` normalises the repo name;
  - `hubTagUrl(base, repo, tag)` builds the per-tag URL;
  - `parseTagDigest(json)` reads the top-level `digest`, checks it against `^sha256:[0-9a-f]{64}$`, and returns null otherwise.
  - The driver calls it through `deps.json`, so selftests make no network reads. The gate calls it through its existing authed fetch. Neither keeps its own copy.
- The driver refuses to plan when a leaf has a `digest` site and Hub gives no digest for the target tag. It also refuses when a version site's text carries `@sha256:` but the entry has no `digest` site, so a registry gap cannot hide this bug again.
- Fold the agreement check into check:ci-docker-image-freshness. A network read in CI fails closed: 429, 5xx, a missing `digest` or a malformed `digest` all count as RED (unknown is never a pass), the same as the gate's listing rule. A digest-only ref with no tag on its line is listed as "untagged, agreement not checkable", with no verdict either way.

## Boxes
- [x] D1 Add scripts/lib/docker-hub.ts with `hubRepo`, `hubTagUrl` and `parseTagDigest` as described in the Decision. Replace scripts/lib/pins/drivers/docker.ts:103 and scripts/gates/check-docker-image-freshness.ts:256 with `hubRepo`. Accept: `npx tsc --noEmit -p scripts/tsconfig.json && npm run check:ci-docker-image-freshness`
    (ticked) 2026-10-30T21:47:32Z by d778be9d: commit:55328d805 scripts/lib/docker-hub.ts:44; npx tsc --noEmit -p scripts/tsconfig.json rc 0; check:ci-docker-image-freshness rc 0
- [x] D2 Make the docker driver resolve the digest:
  - In `plan`, for each site with role `digest`, call `deps.json(hubTagUrl(...), image)` and pass `{ version, digest }` to planLeafSites. Throw `PlanRefused("<id>: Docker Hub gives no digest for <image>:<tag>; refusing to move the tag without it")` on null or a throw.
  - Also refuse a version site whose text has `@sha256:` when the entry has no digest site.
  - Add the `digest` site to image:proxy-node in .ci/config/pins.json and drop "tag only" from its name.
  - Accept: `npx tsx scripts/lib/pins/drivers/selftest.ts && npm run check:ci-pin-registry && npm run pins -- plan image:proxy-node`. The plan output must show both `version` and `digest` changes.
    (ticked) 2026-10-30T21:47:42Z by d778be9d: commit:55328d805 scripts/lib/pins/drivers/docker.ts:19; selftest rc 0; check:ci-pin-registry rc 0; the plan on a 26.12.0 scratch tree shows version and digest changes
- [x] T1 Add the mutant `docker-keep-digest` to T8_MUTANTS (scripts/lib/pins/drivers/shared.ts:28-50, plus a doc line) and to the MUTANTS tuple in test_gate_pin_family_drivers.py. In docker.ts the mutant supplies the old digest instead of the resolved one. Add three new dockerCases controls using `entry('image:proxy-node')`:
  - (a) A tree holds `FROM node:26.12.0-slim@sha256:<a*64>`, and a Hub stub answers the listing plus `/tags/26.13.0-slim` → `{digest: "sha256:<b*64>"}`. The plan must write exactly `FROM node:26.13.0-slim@sha256:<b*64>`.
  - (b) A stub with no `digest`, or with an `images[]`-only digest, must give a `PlanRefused` that names the tag.
  - (c) An entry whose version site sees `@sha256:` but which has no digest site is refused.
  - Accept: `npx tsx scripts/lib/pins/drivers/selftest.ts`. Its output must include `MUTANT docker-keep-digest turns 1+ control(s) red`. Also run `PINS_T8_MUTANT=docker-keep-digest npx tsx scripts/lib/pins/drivers/selftest.ts; test $? -eq 1 && npm run check:ci-standalone-selftests`
    (ticked) 2026-10-30T21:47:49Z by d778be9d: commit:55328d805 scripts/lib/pins/drivers/shared.ts:39; PINS_T8_MUTANT=docker-keep-digest rc 1; family-drivers pytest 13 passed; check:ci-standalone-selftests rc 0
- [x] G1 Fold the agreement check into scripts/gates/check-docker-image-freshness.ts:
  - Extend `Pin` with `digest?` by parsing `@(sha256:[0-9a-f]{64})` after the tag in `parsePins` (:190). Do the same for compose `image: <img>:<tag>@sha256:` lines in the tracked compose files.
  - For each pin with a digest, fetch `hubTagUrl` with the same token-then-anonymous attempts as `listHubTags`. A mismatch is RED and names `npm run pins -- bump <leaf> --to <tag>`. A failed lookup is RED with its cause.
  - Update the header to state the fail-closed rule.
  - Add selftest controls: a pure `digestFindings(pins, answers)` function that flags a mismatch (the control proving the check can fail), flags a missing answer, and passes a match.
  - Accept: `npm run check:ci-docker-image-freshness` is green after R1. Before R1 it must be red on workers/proxy/Dockerfile:20. Run it at HEAD first and record that red as the control on the real tree.
    (ticked) 2026-10-30T21:47:53Z by d778be9d: commit:55328d805 scripts/gates/check-docker-image-freshness.ts:153; gate selftest 52/52; red on the stale proxy digest before R1, rc 0 after
- [x] R0 Add the same-tag re-digest to scripts/lib/pins/drivers/docker.ts (lead ruling 2026-10-30), because the core never moves to a target equal to the pinned tag and official images re-push a tag with a new index digest while it is the newest of its line:
  - When a leaf has a `digest` site and Docker Hub's index digest for the PINNED tag differs from the file's, inspect offers that tag again, labelled `<image>:<tag>@<first 12 hex of the served digest>`, dated by the tag's last push and eligible only past the release-age window. The label carries no second colon, because status.ts `majorLineOf` reads the text after the last colon and a hex prefix starting with digits would read as a phantom newer major. The core reads the label as a major (soak.ts `majorOf` is null for `<image>:`), so it is taken only with `--major --reason`. A matching digest offers nothing.
  - Plan rewrites the digest alone, names only the digest change, plans no baseline drain, and refuses when Hub has re-pushed the tag again since the label was printed.
  - Mutant `docker-skip-redigest` in T8_MUTANTS and the MUTANTS tuple; dockerCases controls for the stale-digest re-digest, the digest-only rewrite, the clean case (a matching digest is current), a label Hub has moved again, and a re-push inside the window.
  - Accept: `npx tsx scripts/lib/pins/drivers/selftest.ts` prints `MUTANT docker-skip-redigest turns 1+ control(s) red`, then `PINS_T8_MUTANT=docker-skip-redigest npx tsx scripts/lib/pins/drivers/selftest.ts; test $? -eq 1 && npm run check:ci-standalone-selftests`
    (ticked) 2026-10-30T21:48:09Z by d778be9d: commit:55328d805 scripts/lib/pins/drivers/docker.ts:27; PINS_T8_MUTANT=docker-skip-redigest rc 1 (4 controls red); selftest rc 0
- [x] R1 Repair workers/proxy/Dockerfile through the fixed bump, not by hand:
  - Run `npm run pins -- bump image:proxy-node --to node:26.13.0-slim --major --reason "re-resolve the digest left at 26.12.0 by #d4b2a051"`. If the core refuses because the target equals the current tag, take the newest 26.x.y-slim candidate that `npm run pins -- status image:proxy-node` offers instead. Do not hand-edit to get round the refusal.
  - Reword the comment at workers/proxy/Dockerfile:16-18 so it names no version.
  - Accept: `docker buildx imagetools inspect $(sed -n 's/^FROM \(node:[^@]*\)@.*/\1/p' workers/proxy/Dockerfile) --format '{{.Manifest.Digest}}'` must equal the digest in the file. Then `npm run check:ci-docker-image-freshness && npm run pins -- verify`
    (ticked) 2026-10-30T21:47:36Z by d778be9d: commit:55328d805 workers/proxy/Dockerfile:20; file digest equals docker buildx imagetools inspect node:26.13.0-slim; pins verify rc 0; freshness gate rc 0
- [x] S1 Sweep the siblings:
  - Check that the ttyd digest at .devcontainer/Dockerfile:769 still equals `docker buildx imagetools inspect tsl0922/ttyd:1.7.8-alpine` (the tag named in the comment at :768). Check private/elite/docker-compose.yml:107 and :157 against the rustfs tag the elite stack records.
  - Record each result here. A mismatch gets its own worklist item; do not hand-edit here.
  - Confirm that G1 lists both refs as "untagged".
  - Accept: `docker buildx imagetools inspect tsl0922/ttyd:1.7.8-alpine --format '{{.Manifest.Digest}}' | grep -q 9355735b28a407fe7fb09597f6773d5550f2502259d22b350a2e2460125f9072 && npm run check:ci-unverified-downloads && npm run check:ci-docker-image-freshness`
    (ticked) 2026-10-30T21:47:39Z by d778be9d: commit:55328d805 agent/plans/PLAN-docker-pin-digest.md:80; ttyd 1.7.8-alpine and rustfs 1.0.0-beta.12 digests agree with their registries; G1 lists them as untagged

- [x] X1 Make the FROM scan of check:ci-docker-image-freshness read the git-visible Dockerfiles (`git ls-files --recurse-submodules` plus untracked files git does not ignore) instead of a walk that skipped every directory starting with a dot, so .ci/docker/*, .ci/media/tts and .devcontainer are judged. A pin it newly finds stale is listed for the lead's decision (a bump, or `--write-baseline --seed-image` for a pin deliberately held), never baselined by the writer.
  - Accept: `npx tsx scripts/gates/check-docker-image-freshness.ts --selftest && PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/gates/test_gate_pin_remedies.py`, then `npm run check:ci-docker-image-freshness` red on `.ci/docker/render/Dockerfile:20 node:24-bookworm-slim` until the lead decides image:ci-node, and green after.
    (ticked) 2026-10-30T21:47:46Z by d778be9d: commit:55328d805 scripts/gates/check-docker-image-freshness.ts:47; dot-directory Dockerfiles now scanned; image:ci-node held by its blocklist BLOCKER and seeded; gate rc 0

## Results (2026-10-30)
- D1, D2, T1 and G1 are implemented and their controls were run red and green.
- `npx tsc --noEmit -p .` (D1's accept command) type-checks nothing under scripts/: the root tsconfig.json is a solution file with `"files": []`, and a planted type error under scripts/lib drew zero diagnostics. The command that covers these files is `npx tsc --noEmit -p scripts/tsconfig.json`, which reports the same plant and 0 errors on the tree.
- R1 was first BLOCKED by the Risk named below (the record follows), and then done through R0:
  - `npm run pins -- bump image:proxy-node --to <the re-digest label: node:26.13.0-slim, an @, and the first 12 hex of the new index digest> --major --reason "re-digest: ..." --adopt workers/proxy/Dockerfile` exited 0 and wrote only the digest. `--adopt` names the file's uncommitted tag move (the earlier bump of #d4b2a051) and the comment rewording, which the transaction otherwise refuses as another session's work.
  - workers/proxy/Dockerfile:20 now pins `sha256:e4db4c91...02c39`, equal to `docker buildx imagetools inspect node:26.13.0-slim`; `npm run check:ci-docker-image-freshness` exited 0 before X1 widened the scan; `npm run pins -- verify` exits 0; `pins -- status image:proxy-node` reads current.
- The original block: `npm run pins -- bump image:proxy-node --to node:26.13.0-slim --major --reason ...` exits 1 with `REFUSED image:proxy-node: current: current`, and Docker Hub lists no 3-component `-slim` tag newer than 26.13.0 (newest: 26.13.0-slim, 26.12.1-slim, 26.12.0-slim), so no fallback candidate exists. workers/proxy/Dockerfile:20 still pins the 26.12.0 index and check:ci-docker-image-freshness is red on it, as designed. The comment at :17-19 no longer names a version.
- The same-tag gap is not one-off. Official node patch tags are re-pushed with a new index digest while they are the newest of their line (node:22.12.0-slim, released 2024-12-03, last pushed 2024-12-25; node:20.18.0-slim, released 2024-10-03, last pushed 2024-11-13). So G1 will also turn red when upstream rebuilds a pinned tag, and its only remedy is a same-tag re-digest that the core refuses today. R0 is that path: the driver offers the pinned tag as a re-digest, and the core needs no change.
- D2's plan output was shown on a scratch PINS_ROOT tree holding the 26.12.0 line, with the real driver and Docker Hub: `version node:26.12.0-slim -> node:26.13.0-slim` and `digest sha256:e556a144... -> sha256:e4db4c91...02c39`. The same scratch tree with the digest site removed was refused by the gap rule, naming workers/proxy/Dockerfile:20.
- S1, siblings:
  - .devcontainer/Dockerfile:769 ttyd `sha256:9355735b...9072` equals `docker buildx imagetools inspect tsl0922/ttyd:1.7.8-alpine` today. Agrees.
  - private/elite/docker-compose.yml:107 and :157 rustfs `sha256:41fe8938...ab21` equals Docker Hub's `1.0.0-beta.12` tag (the version the comment at :96-97 records) and `imagetools inspect rustfs/rustfs:1.0.0-beta.12`. Agrees.
  - G1 lists all three lines every run as `untagged, agreement not checkable`.
- X1: the FROM scan skipped every directory whose name starts with a dot (the old glob's `dot: false`), so .ci/docker/render, .ci/docker/web, .ci/media/tts and .devcontainer were never checked, although .ci/config/pins.json claims sites in all of them. Both scans now read the git-visible file list.
  - The scan now reads `node:24-bookworm-slim` (.ci/docker/render:20 and .ci/docker/web:20) and `mcr.microsoft.com/devcontainers/base:ubuntu-24.04` (claimed, non-Hub, not listed); the other two dot-directory FROM lines take their image from a variable.
  - Every newly read FROM line is claimed by a leaf. One is newly stale: `.ci/docker/render/Dockerfile:20 node:24-bookworm-slim -> 26.13-bookworm-slim`, leaf image:ci-node, which `.ci/policy/.pins-upgrade-blocklist` holds with a BLOCKER until 2026-11-14 (node 26 LTS, the CLI SEA build and the workers to validate first). The gate is red on it until the lead decides.

## Risks
- `bump --to` may refuse a target equal to the current tag, because the driver's inspect lists only newer tags (scripts/lib/pins/drivers/docker.ts:122). If so, R1 takes the newest patch, which is a real bump. A same-tag "re-digest" verb is out of scope; file it as a worklist item if it turns out to be needed.
- On a busy day, Hub rate limits could turn G1 red. That is the intended fail-closed outcome. The existing DOCKERHUB_TOKEN env (scripts/gates/check-docker-image-freshness.ts:4) is the mitigation.

### Critical Files for Implementation
- /home/developer/console/scripts/lib/pins/drivers/docker.ts
- /home/developer/console/scripts/lib/pins/drivers/selftest.ts
- /home/developer/console/scripts/gates/check-docker-image-freshness.ts
- /home/developer/console/.ci/config/pins.json
- /home/developer/console/scripts/lib/pins/driver.ts

- [ ] LP-bench [live] Fresh bench receipt through worklist.py --live-proof, after this plan's bench-deployable boxes land.
  Accept: live-proof bench proxy-ready
