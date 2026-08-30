# PLAN: bump embedded k3s 1.36.3+k3s1 -> 1.36.4+k3s1
Status: draft
Owner: 9d92d9b6
Updated: 2026-08-30

## Why

`npm run check:ci-embed-asset-freshness` is RED on branch 0827-1 / console PR #579:

    ✗ 1 embed-asset pin(s) are behind upstream:
      k3s: pinned 1.36.3+k3s1  ->  upstream 1.36.4+k3s1

This gate runs on EVERY PR push (.github/workflows/ci-quality.yml, `quality-go`
job, step "Check embed-asset upstream freshness"), wrapped in
`.ci/scripts/quality/run-external-gate.sh`. On a `pull_request` event without the
`no-external-quality` label the mode is `hard`, so the failure BLOCKS. It is
unrelated to PR #579's own work -- upstream k3s cut v1.36.4+k3s1 on
2026-08-27T15:53Z, past the freshness soak window, during a gap in the session.

Scope: make that gate green by actually performing the bump, correctly, across
both repos. Not in scope: any other component.

## Decision record

### The upgrade is safe -- no hold is warranted

`.embed-assets-upgrade-blocklist` exists and is empty. It is NOT used here.
Checked, not assumed:

- 1.36.4+k3s1 is a patch release (Kubernetes v1.36.4, containerd v2.3.4-k3s1.36,
  Go 1.26.7). No k3s CLI/flag surface change.
- Its ONLY release-notes warning is the Traefik chart v40 breaking change
  (`kubernetesIngressNginx` -> `kubernetesIngressNGINX`). renet always starts
  k3s with `--disable traefik` (private/renet/pkg/kube/distro/k3s.go:146, with
  `--disable servicelb` alongside; the comment at :129 says the Rediacc proxy
  replaces both). The warning cannot reach us.

There is no compatibility risk, no infra limitation, and therefore no honest
BLOCKER reason. A blocklist entry here would be a suppression of a real, fixable
finding. Same verdict for the `no-external-quality` PR label: it exists for
nightly external drift, and applying it to hide a genuinely stale pin would be
the same evasion by a different door. `.ci/config/carried-reds.json` is not in
play and must not be touched.

### No local Docker rebuild -- verified, not assumed

The gate's own remediation text says to run
`(cd private/renet && docker build -t rediacc/renet:latest . && ./build.sh embed_assets --force)`.
That is generic advice for any component bump. For a k3s-only patch bump in THIS
worktree it is unnecessary, and running it costs more than it proves:

1. Docker IS available and working (Docker Desktop 4.88.1 / engine 29.7.2,
   24 cores, ~42 GB RAM free, 360 GB disk free). So this is a judgement call,
   not an environment failure.
2. `rediacc/renet:latest` does NOT exist locally, so the build would be
   from-scratch: CRIU compiled from source for amd64 + arm64, rsync from source
   for both, the three Go CSI sidecars cross-compiled. CI itself budgets this at
   "~12-minute" (comment at .github/workflows/ci-build-renet.yml:74). This is a
   SHARED, contended worktree.
3. NOTHING this change commits is produced by that build. The staged tree lives
   at private/renet/pkg/embed/assets/**, is fully gitignored (`*.zst`,
   `*-linux-{amd64,arm64}`, `.staged.json`), and is currently EMPTY here.
   Running the build would newly populate shared, uncommittable state.
4. The build's only k3s-specific assertion is `sha256sum -c -` in the two
   downloader stages. That assertion is already satisfied, more directly: the
   checksums below were taken from upstream's published manifests AND
   independently reproduced by downloading and hashing the exact release
   binaries (see "Checksum provenance").
5. CI performs the real rebuild automatically. `ci-build-renet.yml`'s
   `Renet (Full)` job restores `private/renet/pkg/embed/assets` under cache key
   `renet-embed-assets-${{ hashFiles('private/renet/embed-assets.lock.json') }}`.
   This change MUTATES that lockfile, so the key necessarily changes, the cache
   necessarily misses, and `_build_docker_for_assets` necessarily runs the full
   Docker build -- executing the k3s `sha256sum -c -` against the new pins on a
   clean runner. `build-renet` runs on every CI (ci.yml:698). A green
   `build-renet` IS the checksum-correctness proof, in the environment that
   matters.
6. Precedent: renet `de34d3c` (the 1.36.2 -> 1.36.3 bump) states "No full
   embed_assets rebuild was needed: the lockfile carries versions and licence
   metadata, not checksums." Same shape of change, same conclusion.

OPTIONAL cheap local proof (step 6 below) exercises the exact checksum lines
without any of the source compiles, in ~1-2 min.

### Pre-existing defect this bump must not perpetuate

private/renet/embed-assets.lock.json's k3s block has `version: 1.36.3+k3s1`
(line 142) but its per-arch download records still name **v1.36.2+k3s1**:

    line 160: "url": ".../releases/download/v1.36.2+k3s1/k3s"
    line 161: "sha256": "65a55ec5…"   (the 1.36.2 amd64 hash)
    line 165: "url": ".../releases/download/v1.36.2+k3s1/k3s-arm64"
    line 166: "sha256": "1dc5fc17…"   (the 1.36.2 arm64 hash)

The previous bump moved `version` and left these behind. Nothing catches it:
`check-embed-arch-parity.ts` only asserts each `arches[*]` entry HAS an https
url and a well-formed sha256 (lines 115-121), never that they match the
component's version; `build.sh` reads only `arches | keys[]` (line 296) for the
staging loop. The lockfile's own `_doc` claims "every fetch is verified.
'sha256' values were checked against upstream's own published checksums" -- so
these fields are a documented integrity record that is currently false for k3s.
This is the identical class of miss that became review finding `f63fa47` on the
last bump's PR (attribution URLs left at the previous release). Fix it here, in
the same commit, with the commit body saying so plainly.

Deliberately OUT of scope, recorded for a follow-up task: **zot has the same
drift** -- lockfile lines 128/131 name `v2.1.18` with the 2.1.18 hashes while
`version` is `2.1.20`. Different component, not what this PR is about.
Recommended durable fix (its own task, not this one): extend
`scripts/check-embed-arch-parity.ts` to assert each `arches[*].url` contains
the component's `version` string, which makes this whole class impossible.

## Checksum provenance

Two independent derivations, agreeing exactly:

    # 1. upstream's own published manifests
    curl -fsSL "https://github.com/k3s-io/k3s/releases/download/v1.36.4%2Bk3s1/sha256sum-amd64.txt"
    curl -fsSL "https://github.com/k3s-io/k3s/releases/download/v1.36.4%2Bk3s1/sha256sum-arm64.txt"

    # 2. the actual binaries the Dockerfile fetches, hashed
    curl -fsSL "https://github.com/k3s-io/k3s/releases/download/v1.36.4+k3s1/k3s"       | sha256sum
    curl -fsSL "https://github.com/k3s-io/k3s/releases/download/v1.36.4+k3s1/k3s-arm64" | sha256sum

Result:

    amd64  k3s        835873f37245fc615f547a2fe2af9402a347875f13fa64a1f136de644955ea3f
    arm64  k3s-arm64  c920706346d5ad4e5cd3c7bf1bb09ce71ebe07fec829e513e40f1caf98aed8bb

Format control: the SAME manifest fetch for v1.36.3+k3s1 returns exactly the two
values currently pinned in the Dockerfile (`2f98a9f8…`, `c9a20910…`). The URL
shape and the "bare release binary, not the airgap tarball" convention are
therefore confirmed against the existing, working pins rather than guessed.

WARNING: READ CAREFULLY when editing. The OLD arm64 pin is `c9a20910…` and the
NEW one is `c920706…`. They share a 2-character prefix. Copy, do not retype.

## Repository topology

`private/renet` is a SEPARATE git repository (`.gitmodules` -> rediacc/renet),
currently checked out on branch `0827-1` at `3f49e09`, with an already-open,
already-linked coordinated PR **rediacc/renet#109** on that same branch. Console
PR #579 is on branch `0827-1` too.

That matters: `.ci/scripts/quality/check-submodule-branches.sh` requires a
submodule with pointer changes to be on a branch matching the console branch,
with an open PR linked from the console PR body. All three conditions already
hold -- this change adds a commit to the EXISTING renet branch and PR. Do NOT
create a new branch or a new renet PR.

Console-side submodule pointer bumps follow `bdb5098f8`
("chore(submodule): bump private/renet to 3f49e09, …").

## The change set

### A. renet repo -- private/renet, branch 0827-1, PR rediacc/renet#109

A1. `Dockerfile` line 320 (stage `k3s-downloader-amd64`)
      ARG K3S_VERSION=1.36.3+k3s1
    ->
      ARG K3S_VERSION=1.36.4+k3s1

A2. `Dockerfile` line 321
      ARG K3S_SHA256_AMD64=2f98a9f8fe5782479ee2d54e70a1b10a7f6fd4cae8d38ed3098452dc6eed76b5
    ->
      ARG K3S_SHA256_AMD64=835873f37245fc615f547a2fe2af9402a347875f13fa64a1f136de644955ea3f

A3. `Dockerfile` line 340 (stage `k3s-downloader-arm64`)
      ARG K3S_VERSION=1.36.3+k3s1
    ->
      ARG K3S_VERSION=1.36.4+k3s1

A4. `Dockerfile` line 341
      ARG K3S_SHA256_ARM64=c9a209103f480f163b7c6a56f00862b4481927b284dc29a3716bb70d886691a8
    ->
      ARG K3S_SHA256_ARM64=c920706346d5ad4e5cd3c7bf1bb09ce71ebe07fec829e513e40f1caf98aed8bb

    Both K3S_VERSION ARGs must move together -- the Dockerfile declares the pin
    once per stage and `scripts/lib/dockerfile-versions.ts` reports a CONFLICT
    (surfaced by check-embed-credits) if they disagree.

A5. `embed-assets.lock.json` line 142
      "version": "1.36.3+k3s1"   ->   "version": "1.36.4+k3s1"

A6. `embed-assets.lock.json` line 148
      "upstreamSourceUrl": "https://github.com/k3s-io/k3s/archive/v1.36.4+k3s1/k3s-1.36.4+k3s1.tar.gz"

A7. `embed-assets.lock.json` line 149
      "plannedMirrorUrl": "https://releases.rediacc.com/third-party-src/k3s-1.36.4+k3s1.tar.gz"

A8. `embed-assets.lock.json` lines 160-161 (k3s arches.amd64) -- also repairs the
    pre-existing v1.36.2 drift
      "url":    "https://github.com/k3s-io/k3s/releases/download/v1.36.4+k3s1/k3s"
      "sha256": "835873f37245fc615f547a2fe2af9402a347875f13fa64a1f136de644955ea3f"

A9. `embed-assets.lock.json` lines 165-166 (k3s arches.arm64) -- same
      "url":    "https://github.com/k3s-io/k3s/releases/download/v1.36.4+k3s1/k3s-arm64"
      "sha256": "c920706346d5ad4e5cd3c7bf1bb09ce71ebe07fec829e513e40f1caf98aed8bb"

    Leave `notes` and `buildNote` byte-identical. The lockfile _doc is explicit:
    `notes` is ATTRIBUTION text reproduced verbatim into generated credits --
    never reflow it.

A10. `pkg/embed/embed.go` line 61
      const AssetK3sVersion = "1.36.3+k3s1"
     ->
      const AssetK3sVersion = "1.36.4+k3s1"

     This const is the runtime truth: pkg/kube/distro/k3s.go:265 stamps it into
     distro.json at install, :229 logs it at extraction, and :407 is the upgrade
     guard that rejects a request for any other version. If it does not match
     the embedded binary the version report lies.

A11. `pkg/embed/credits_data.go` lines 41/44/45 -- **GENERATED, never hand-edited.**
     Produced by step 3 below. File header says "Code generated by
     scripts/generate-embed-credits.ts. DO NOT EDIT."

### B. console repo -- /home/developer/console, branch 0827-1, PR #579

B1. `packages/cli/src/data/third-party-credits.json` lines 40/43/44 -- also
    GENERATED by the same command; the generator preserves the non-embedded
    entries (Node runtime, bundled npm deps) untouched.

B2. `private/renet` gitlink -> the new renet commit from A.

Explicitly NOT changed:
- `packages/cli/dist/data/third-party-credits.json` -- gitignored build output
  (`.gitignore:7` `packages/*/dist`).
- `scripts/check-embed-asset-versions.ts:263-264` -- a `1.36.3` string inside a
  self-test fixture for the "k3s version v… (sha)" output shape. Not a pin.
- `docs/design/spec/05-*.md`, `docs/design/spec/08-*.md` -- historical spike
  records naming k3s v1.36.2. Point-in-time measurements; the 1.36.3 bump left
  them alone and so does this one.
- `.embed-assets-upgrade-blocklist` -- stays empty.

## Ordered execution

Run everything from `/home/developer/console` unless stated. There is a hard
ordering constraint: the freshness gate's `--upgrade` rewrites the Dockerfile
ARG ONLY. Between that and the lockfile edit, `check:ci-embed-credits` will fail
by design (Dockerfile 1.36.4 vs lockfile 1.36.3). Do not stop there.

1. Apply A1-A4 and A5-A9 and A10 by hand.

   Do NOT use `npm run check:ci-embed-asset-freshness -- --upgrade`. It rewrites
   only the two ARG lines and would leave the two SHA256 ARGs pointing at the
   1.36.3 binaries -- a state in which `docker build` fails at `sha256sum -c -`.
   Hand-editing all ten locations at once is both safer and fewer steps. (If it
   is used anyway, treat it as having done A1 and A3 only, and finish the rest.)

2. Sanity-check the Dockerfile edit read back the intended bytes:

       grep -n "K3S_VERSION\|K3S_SHA256" private/renet/Dockerfile

   Expect four lines: two `1.36.4+k3s1`, one `835873f3…`, one `c9207063…`.

3. Regenerate BOTH attribution artifacts from the lockfile (writes into BOTH
   repos -- credits_data.go into renet, third-party-credits.json into console):

       npx tsx scripts/generate-embed-credits.ts

   Then confirm the diff it produced contains ONLY k3s version/URL lines.

4. Compile-verify the renet side:

       cd /home/developer/console/private/renet
       go build ./...
       go vet ./pkg/embed/ ./pkg/kube/distro/

   (Matches what de34d3c verified, plus pkg/kube/distro since AssetK3sVersion is
   consumed there.)

5. Run the four embed gates from the console root -- see "Proof" below for the
   exact expected output of each.

6. OPTIONAL local checksum proof (~1-2 min, no source compiles, no staging).
   This builds ONLY the two k3s downloader stages, which is precisely the
   `sha256sum -c -` verification and nothing else:

       cd /home/developer/console/private/renet
       docker build --target k3s-downloader-amd64 -t renet-k3s-check-amd64 .
       docker build --target k3s-downloader-arm64 -t renet-k3s-check-arm64 .
       docker image rm renet-k3s-check-amd64 renet-k3s-check-arm64

   Both stages are plain `FROM ubuntu:24.04` with no `--platform`, so neither
   needs QEMU binfmt (none is registered on this host -- only WSLInterop and
   python3.14 -- which is another reason not to attempt the full build here).
   A checksum mismatch fails the build loudly at `sha256sum -c -`. Skip this
   only if the Docker daemon is contended; CI covers it either way.

   Do NOT run the full `docker build -t rediacc/renet:latest .` or
   `./build.sh embed_assets --force`. See the decision record.

7. Commit in the renet repo (four files, one commit, on the existing branch):

       cd /home/developer/console/private/renet
       git status --short     # expect exactly: Dockerfile, embed-assets.lock.json,
                              # pkg/embed/embed.go, pkg/embed/credits_data.go
       git add Dockerfile embed-assets.lock.json pkg/embed/embed.go pkg/embed/credits_data.go
       git commit             # message per "Commit messages" below
       git push origin 0827-1

   This updates the already-open, already-linked rediacc/renet#109. No new
   branch, no new PR -- check-submodule-branches.sh is already satisfied.

8. Capture the new renet SHA:

       cd /home/developer/console/private/renet && git rev-parse --short HEAD

9. Commit in the console repo (generated CLI mirror + gitlink, one commit):

       cd /home/developer/console
       git add packages/cli/src/data/third-party-credits.json private/renet
       git commit             # MUST carry a `PR-TASK: <id>` trailer -- see the
                              # pr-epics skill for obtaining the id for PR #579
       git push origin 0827-1

   Note this worktree is shared and carries unrelated modified files. Stage by
   explicit path; never `git add -A` / `git add .`.

10. Watch CI via the ci-watch skill (never a hand-rolled `gh` polling loop -- the
    pre-bash guard and the Stop hook block those). The two jobs that matter:
    `Quality / Go` (the freshness gate goes green) and `build-renet` (the full
    Docker rebuild with the real `sha256sum -c -`).

## Proof -- how the implementer knows it is done

Local, before pushing. Each of these is a specific claim, not a smoke test.

    npm run check:ci-embed-asset-freshness
      BEFORE: "✗ 1 embed-asset pin(s) are behind upstream: k3s: pinned
              1.36.3+k3s1 -> upstream 1.36.4+k3s1", exit 1
      AFTER:  "✓ Every embed-asset pin is current (or deferred / held /
              uncheckable)", exit 0
      This is the gate that is red. Zero findings is the headline result.
      Caveat: this gate FAILS SOFT on network trouble. A "? k3s: could not
      check (…)" line also exits 0 but proves nothing -- re-run until it
      actually reports the comparison.

    npm run check:ci-embed-credits
      Asserts (1) the Dockerfile ARG pins equal the lockfile versions and
      (2) credits_data.go + third-party-credits.json are byte-identical to what
      the generator produces from the lockfile.
      EXPECT: "✓ 7 embedded components: Dockerfile pins and generated
              attribution match the lockfile"
      A failure here after step 3 means an artifact was hand-edited, or the
      lockfile and Dockerfile disagree.

    npm run check:ci-embed-arch-parity
      EXPECT: "✓ 7 components x [amd64, arm64] = 14 arch entries, all pinned"
      Both baseline and post-change. Note it validates SHAPE only (https url
      present, sha256 well-formed) -- it will not catch a wrong-but-well-formed
      hash. It is not the checksum proof.

    npm run check:ci-embed-asset-versions
      The ONLY gate that opens the artifact: it decompresses each staged .zst
      and asks the binary its own version. In THIS worktree
      private/renet/pkg/embed/assets/{amd64,arm64} contain no .zst, so it will
      SKIP LOUDLY while still running its comparison controls. That skip is
      expected and correct here -- but it means this gate is NOT the proof
      either. It becomes the proof on CI's build-renet job, after the rebuild
      stages the real binaries.

    .ci/scripts/test/gates/test-embed-asset-freshness.sh
    .ci/scripts/test/gates/test-embed-credits.sh
    .ci/scripts/test/gates/test-embed-arch-parity.sh
      The gates' own oracles (they read renet's Dockerfile; they exit 0 with a
      "submodule not present" skip when it is absent, which is why CI checks
      out submodules for this job). Run them to confirm the edits did not break
      the parsers themselves.

    cd private/renet && go build ./... && go vet ./pkg/embed/ ./pkg/kube/distro/
      AssetK3sVersion compiles and its three consumers still typecheck.

Checksum correctness specifically. Three layers, weakest to strongest:

  1. The two independent upstream derivations above (manifest + hash-the-binary).
     Already done; strongest evidence available without a build.
  2. Step 6's `--target` builds, which run the Dockerfile's own
     `sha256sum -c -` against the newly downloaded binaries. Cheap. Optional.
  3. CI `build-renet`. The lockfile change guarantees an embed-assets cache
     miss, guaranteeing the full `_build_docker_for_assets`, so the real
     `sha256sum -c -` executes on a clean runner and, downstream, the staged
     assets exist for check:ci-embed-asset-versions to open and interrogate.
     **A green build-renet is the definitive proof.** If the hash were wrong,
     that job fails at the k3s download stage with a checksum mismatch -- loud,
     not silent.

Definition of done: check:ci-embed-asset-freshness reports zero findings; the
other three embed gates green; renet `go build`/`go vet` clean; rediacc/renet#109
updated and console #579 carrying the matching gitlink; CI `Quality / Go` and
`build-renet` both green.

## Commit messages

renet (rediacc/renet#109, branch 0827-1) -- no PR-TASK trailer in this repo:

    chore(embed): k3s 1.36.3+k3s1 -> 1.36.4+k3s1

    console's check:ci-embed-asset-freshness went red on Quality / Go: the pin
    was behind upstream past the soak window (v1.36.4+k3s1 published
    2026-08-27) and carries no documented hold. Unrelated to the rest of this
    branch's work -- the world moved, not this tree.

    Not held back. The release's only warning is the Traefik chart v40
    ingress-nginx provider rename, and pkg/kube/distro/k3s.go:146 starts k3s
    with --disable traefik unconditionally, so it cannot reach us. Otherwise a
    patch release: Kubernetes v1.36.4, containerd v2.3.4-k3s1.36, Go 1.26.7.

    Checksums are the REAL ones, taken two ways that agree: upstream's
    sha256sum-amd64/arm64 manifests for v1.36.4+k3s1, and an independent
    download-and-hash of the exact binaries the Dockerfile fetches. The same
    manifest fetch for v1.36.3+k3s1 reproduces the pins being replaced, which
    is what makes the URL shape and file format confirmed rather than assumed.

    AssetK3sVersion moved with it -- pkg/kube/distro stamps that const into
    distro.json and guards `kube upgrade` against it, so a const that lags the
    embedded binary makes the runtime version report lie.

    Also repairs pre-existing drift in the SAME block: the lockfile's k3s
    arches.{amd64,arm64}.url/sha256 still named v1.36.2+k3s1 with the 1.36.2
    hashes, because the previous bump moved `version` and left them. Nothing
    catches that -- check-embed-arch-parity only asserts an https url and a
    well-formed sha256 exist, never that they match the version -- and the
    lockfile's own _doc claims those hashes were checked against upstream's
    published checksums, so a stale one is a false integrity record. Same class
    as f63fa47. zot has the identical drift (arches at v2.1.18, version 2.1.20);
    left alone deliberately, recorded for its own task.

    credits_data.go REGENERATED from the lockfile via
    scripts/generate-embed-credits.ts, not hand-edited.

    No embed_assets rebuild: nothing committed here comes out of that build,
    the staged tree is gitignored, and console CI's build-renet keys its
    embed-assets cache on this lockfile's hash -- so this change forces the
    full Docker build, where the Dockerfile's own `sha256sum -c -` verifies
    both new pins on a clean runner.

    Verified: check:ci-embed-asset-freshness 1 finding -> 0,
    check:ci-embed-credits rc=0, check:ci-embed-arch-parity rc=0,
    go build ./... and go vet ./pkg/embed/ ./pkg/kube/distro/ clean.

console (PR #579, branch 0827-1) -- MUST carry a PR-TASK trailer:

    chore(embed): bump private/renet for the k3s 1.36.4+k3s1 pin

    check:ci-embed-asset-freshness runs on every PR push and was blocking this
    branch on a pin that upstream moved out from under it. The bump itself
    lives in rediacc/renet#109 on branch 0827-1 (already open, already linked);
    this carries the pointer plus the CLI-side attribution mirror.

    packages/cli/src/data/third-party-credits.json is generated from
    private/renet/embed-assets.lock.json by scripts/generate-embed-credits.ts,
    which writes both this mirror and renet's credits_data.go from the one
    source -- so it moves in lockstep with the submodule commit rather than
    after it. check:ci-embed-credits compares derivation, not agreement, and
    would fail on either half alone.

    check:ci-embed-asset-freshness rc=0 (was 1 finding),
    check:ci-embed-credits rc=0, check:ci-embed-arch-parity rc=0.

    PR-TASK: <id>

## Risks and how each is caught

- Wrong SHA256 transcribed (the c9a20910 / c9207063 prefix collision).
  Caught by: step 6's --target build, and unavoidably by CI build-renet's
  `sha256sum -c -`. Loud failure, never silent.
- Only one of the two K3S_VERSION ARGs edited.
  Caught by: parseDockerfileVersions emits a CONFLICT, surfaced as an error by
  check:ci-embed-credits.
- credits artifacts hand-edited instead of regenerated.
  Caught by: check:ci-embed-credits compares against generator output byte for
  byte.
- Console gitlink pushed without the renet commit being pushed first.
  Caught by: check-submodule-branches.sh (unreachable gitlink). Mitigated by the
  step ordering -- renet push at step 7, console push at step 9.
- The freshness gate passing for the wrong reason (network soft-fail).
  Mitigated by: reading the actual output, not just the exit code. A "?
  could not check" line is not a pass.
- Shared worktree: unrelated modified files swept into a commit.
  Mitigated by: explicit `git add <path>`; never `-A` or `.`.

## Follow-ups (separate tasks, not this one)

1. zot's lockfile `arches.{amd64,arm64}.url`/`sha256` still name v2.1.18 while
   its `version` is 2.1.20. Same defect, different component.
2. Durable fix for the whole class: extend
   `scripts/check-embed-arch-parity.ts` to assert each `arches[*].url` contains
   the component's `version`. That single assertion would have caught both the
   k3s and the zot drift at the moment they were introduced, and would make the
   lockfile's "checked against upstream's own published checksums" claim
   enforceable rather than aspirational. Belongs in the existing gate, with a
   case added to `.ci/scripts/test/gates/test-embed-arch-parity.sh`.
