# `.ci/policy/` -- where suppression policy lives

**The move landed in W4 phase 2, on 2026-09-06.** W4 phases 0 and 1 built the seam and the measurements that made it safe; phase 2 relocated all fifteen files named below out of the repository root and into this directory, carrying every reader with them in the same change. `scripts/lib/policy-paths.ts` is where the location is held, and flipping its `POLICY_DIR` from `''` to
`'.ci/policy'` was the whole of the move for every reader that already went through `policyPath()`.

The paths in the tables below are given as BARE NAMES, which is how the seam and every reader still refer to them; the file itself now lives at `.ci/policy/<name>`.

Read this before moving any of them again, and before adding another.

---

## 1. The predicate

A file belongs in `.ci/policy/` when **all four** hold:

1. **It is a decision, not data.** Its content is a set of entries someone chose to
exempt, block, allow or hold, and each entry is a claim about the world that could stop being true. That is what makes it policy rather than configuration.
2. **It is BLOCKER-gated, or should be.** Every entry carries -- or is required by
`docs/agent-reference/suppressions.md` to carry -- a substantive `# BLOCKER:` reason. The two path-list exceptions (`.e2e-coverage-allowlist`, `.profiler-coverage-allowlist`) are in because their gates enforce liveness in-gate instead, which is the same obligation discharged differently.
3. **It has a parser.** Some code opens it and reads entries out of it. A file nothing
parses is not policy; see `.ci-trigger` in section 3.
4. **Its location is an implementation detail.** No tool discovers it by name at the
repository root, and no external consumer depends on the path. This is the clause that keeps `package.json`, `tsconfig.json` and `biome.json` at the root, and it is the same predicate `docs/ci-overhaul/08-driver-contract.md` §5d gives for the `.json` inventory.

The predicate is checkable in **both directions**, and the move phase must assert both: nothing outside the discovered set may sit at the root, and every name in `POLICY_FILES` (`scripts/lib/policy-paths.ts`) must be present here. A move that forgets a reader must be red, not quiet.

---

## 2. The files that moved in W4 P2, and the live inventory

Every one of these was at the repository root until W4 P2 and now lives here. The reader column is what had to follow the file; the seam that made that a one-line change is `scripts/lib/policy-paths.ts`. The "how the path is built" column records the shape each reader had BEFORE the move, which is why four of them were dangerous -- it is kept as the record of what the seam was for,
not as a description of the code today.

| File | Reader, by symbol | How the path is built today |
|---|---|---|
| `.actions-upgrade-blocklist` | `scripts/gates/check-actions.ts` `BLOCKLIST_FILE` | root join |
| `.audit-allowlist` | `.ci/rediacc_ci/security/audit.py` `DEV_ALLOWLIST` | `policy_rel`, over what was a **bare relative name** in the deleted `audit.sh` |
| `.audit-prod-allowlist` | `.ci/rediacc_ci/security/audit.py` `PROD_ALLOWLIST` | `policy_rel`, over what was the same bare name |
| `.ci-parity-exempt` | `scripts/gates/check-ci-parity.ts` `EXEMPT_FILE` | env seam (`CI_PARITY_ROOT`) over root join |
| `.cli-i18n-orphan-allowlist` | `scripts/gates/check-cli-i18n-key-usage.ts` `ORPHAN_ALLOWLIST` | root join |
| `.dead-bash-allowlist` | `scripts/gates/check-dead-bash.ts` `ALLOWLIST` | env seam (`DEAD_BASH_ROOT`) over root join |
| `.deps-upgrade-blocklist` | `scripts/gates/check-deps.ts` `BLOCKLIST_FILE`; the audit gate's `deps_blocklist_has()` | root join; **and a bare relative name** in `deps_blocklist_has` |
| `.devcontainer-upgrade-blocklist` | `scripts/gates/check-devcontainer-pin-freshness.ts` `DEVCONTAINER_BLOCKLIST_FILE` | env seam over root join |
| `.e2e-coverage-allowlist` | `scripts/gates/check-e2e-coverage.ts` `E2E_COV_ALLOWLIST` | env seam over root join |
| `.embed-assets-upgrade-blocklist` | `scripts/gates/check-embed-asset-freshness.ts` `EMBED_BLOCKLIST_FILE` | env seam over root join |
| `.go-deps-upgrade-blocklist` | `.ci/rediacc_ci/quality/go_deps.py` `BLOCKLIST_REL` | `policy_rel`, over what was a root join in the deleted `check-go-deps.sh` |
| `.plan-housekeeping-allowlist` | `.ci/scripts/quality/check-plan-housekeeping.sh` `ALLOWLIST` | env seam (`PLAN_HK_ALLOWLIST`) over root join |
| `.profiler-coverage-allowlist` | `.ci/scripts/quality/check-profiler-coverage.sh` `ALLOWLIST` | **bare relative name**, correct only after the `cd "$REPO_ROOT"` above it |
| `.runner-advice-allowlist` | `.ci/scripts/quality/check_runner_advice.py` `allowlist_path` | flag, then env (`RUNNER_ADVICE_ALLOWLIST`), then root join |
| `.unverified-download-allowlist` | `scripts/gates/check-unverified-downloads.ts` `UNVERIFIED_DOWNLOAD_ALLOWLIST` | env seam over root join |

Readers are cited by SYMBOL rather than by line, deliberately. This checkout is shared with other sessions (`docs/ci-overhaul/08-driver-contract.md` section 4), and the first draft of this table went stale within the hour: half its line numbers had moved by the time the file was written, because unrelated edits landed above them. A symbol survives that; a line number is a claim
about a tree nobody has any more.

Eleven of the fifteen are additionally read by `scripts/gates/check-suppression-liveness.ts`, which since 2026-09-06 routes every one of those reads through `policyPath()` and therefore needs no edit when the move lands.

**The four bare-relative reads are the reason the seam exists.** `audit.sh` and `check-profiler-coverage.sh` opened their allowlists by bare name and were correct only because they `cd` to the repository root first. Two of the four left with `audit.sh` at W7P5-b, and its port reads through `policy_rel` instead. A move that updated the root joins and missed these would leave four
readers opening a file that is no longer there -- and in every one of these mechanisms, a file that is not there parses as zero entries, which is indistinguishable from "nothing is suppressed".

### The live inventory, generated

The table above is the RECORD OF A MOVE and stops being true the moment a file is added, which has now happened three times (section 5). The table below is re-derived from the tree on every `gen-docs` run and is checked byte for byte by `check:ci-doc-region-parity`, so it cannot say fifteen while the directory holds eighteen. That sentence is not hypothetical: this heading read
"fifteen" against sixteen files on disk for a day, and against eighteen by the time it was fixed.

Three things it shows that a hand-typed table cannot. **Entries** is re-counted, so a suppression list that quietly filled up is visible here without anyone re-reading it. **In POLICY_FILES** is the two-direction set equality between the directory and BOTH seams, so `ts only`, `py only` or `NEITHER` in that column is the half-landed move `scripts/lib/policy-paths.ts` exists to
prevent. And a name that is in a seam with **NO FILE ON DISK** gets a row of its own rather than being absent, because absence is exactly how that failure hides: every reader here treats a missing file as zero entries, which is indistinguishable from "nothing is suppressed".

The column that is NOT here is Readers, and its absence is deliberate: `scripts/lib/doc-providers.ts` records that a grep-derived Readers column flipped mid-run on 2026-09-06 when an unrelated peer session staged a file, and forbids re-adding it. The reader mapping above is hand-written and cited by symbol for the same reason.

<!-- >>> gen-docs: policy -->
<!-- Tracked files only, via git ls-files, which is the rule every provider in -->
<!-- doc-providers.ts follows: an untracked file is not yet part of the repository's -->
<!-- contract. check:ci-policy-inventory reads the DIRECTORY instead, so an untracked -->
<!-- policy file is a finding there and invisible here. That is the intended split. -->

Scans: every tracked file in the policy directory, against `POLICY_FILES` in both seams (`scripts/lib/policy-paths.ts`, `.ci/rediacc_ci/policy_paths.py`).

| File | Shape | Entries | BLOCKER lines | In POLICY_FILES |
|---|---|---|---|---|
| `.actions-upgrade-blocklist` | name per line | 0 | 0 | both |
| `.audit-allowlist` | name per line | 0 | 1 | both |
| `.audit-prod-allowlist` | name per line | 10 | 6 | both |
| `.ci-parity-exempt` | name per line | 9 | 10 | both |
| `.cli-i18n-orphan-allowlist` | name per line | 5 | 6 | both |
| `.dead-bash-allowlist` | name per line | 12 | 13 | both |
| `.deps-upgrade-blocklist` | name per line | 18 | 19 | both |
| `.devcontainer-upgrade-blocklist` | name per line | 0 | 1 | both |
| `.e2e-coverage-allowlist` | name per line | 21 | 3 | both |
| `.embed-assets-upgrade-blocklist` | name per line | 1 | 2 | both |
| `.go-deps-upgrade-blocklist` | name per line | 3 | 4 | both |
| `.host-toolchain-exceptions` | name per line | 0 | 1 | both |
| `.language-policy-allowlist` | name per line | 18 | 19 | both |
| `.plan-housekeeping-allowlist` | name per line | 0 | 1 | both |
| `.profiler-coverage-allowlist` | name per line | 65 | 4 | both |
| `.runner-advice-allowlist` | name per line | 0 | 1 | both |
| `.unverified-download-allowlist` | name per line | 4 | 4 | both |
| `.w7p5a-real-run-blocklist` | name per line | 28 | 20 | both |
| `.w7p5a-real-run-leg-blocklist` | name per line | 7 | 7 | both |
| `hook-exec-baseline.json` | JSON table | - | 1 | both |
| `tree-shape.json` | JSON table | - | 0 | both |
| `worklist-env-registry.json` | JSON table | - | 0 | both |

22 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

### Three things the move carried with it, all three done in W4 P2

- **`.ci/scripts/ci/scope-map.cjs` `ROOT_MANIFESTS`** named ten of the fifteen by exact
repo-relative path, and after the move those names matched nothing. Classification is preserved anyway -- `.ci/policy/<name>` is caught by the `ci-harness` rule (`matchPrefix('.ci/')` ⇒ `full: 'harness'`) -- so no delta stopped forcing full CI. What changed is the REASON string, from `root-manifest:<name>` to `harness:.ci/policy/<name>`. All fifteen names were DELETED from
`ROOT_MANIFESTS` (five of them were never in it and fell through to `unclassified` ⇒ full, which is the same scope by a different route), and the pinned row in `.ci/rediacc_ci/tests/gates/test_gate_scope_engine.py` was re-pinned to two rows: `.ci-trigger` keeps `root-manifest:` covered, and `.ci/policy/.audit-allowlist` pins the new `harness:` reason.
- **`scripts/ci-runner/manifest.ts`** lists `.plan-housekeeping-allowlist` in the `paths:`
array of `check:ci-plan-housekeeping`, and `scripts/ci-runner/gates.lock.json` mirrors it. Change detection for that gate breaks silently if the path is not updated. Both files are driver-owned (driver-contract 5e), so W4 P2 shipped the two lines as a patch fragment for the driver to apply rather than editing them itself.
- **`scripts/lib/doc-providers.ts`** builds the generated suppressions table in
`scripts/data/doc-registry.md` by scanning every tracked non-source file that contains `BLOCKER:`. It names nothing, so it needed no edit -- but the table's paths changed, so the artifact was regenerated (`npx tsx scripts/gen/gen-docs.ts --write`) in the same change, and the fourteen matching keys in the frozen pre-port SET record (`scripts/data/doc-registry-preport.json`) were
RE-KEYED in place. A rename reads to `--diff-snapshot` as fourteen MISSING keys, which is fatal there; re-keying only those fourteen strings is what keeps the record diffable without a `--snapshot --force` that would have destroyed every other provider's pre-port state.

---

## 3. The file that does NOT move: `.ci-trigger`

**Decision: `.ci-trigger` stays at the repository root.** It is deliberately absent from
`POLICY_FILES` in `scripts/lib/policy-paths.ts`, and `.ci/rediacc_ci/tests/gates/test_gate_policy_path.py` asserts that absence so nobody adds it back by tidiness.

The evidence, measured 2026-09-06:

- **Nothing parses it.** A tree-wide search for `ci-trigger` (excluding `node_modules`,
`.git` and this session's own worklist) returns exactly ONE hit: `.ci/scripts/ci/scope-map.cjs:76`, a membership test in the `ROOT_MANIFESTS` set. No reader opens it, no workflow `paths:` filter names it, no gate test references it. Its whole content is one line, a UTC timestamp, last changed in `23c524b9a` (#512).
- **It therefore fails predicate clause 3, and clause 1.** It holds no entries, carries
no `BLOCKER:` reason and expresses no exemption. It is not a suppression at all.
- **Its one semantic is a ROOT GESTURE.** `touch .ci-trigger && git commit` is how a
human forces a full CI round on a delta that would otherwise be scoped down. That gesture only works if the person can find the file, and the place they look is the root of the repository.
- **Moving it would work and still be wrong.** `.ci/policy/.ci-trigger` would keep
forcing full CI, through the generic `ci-harness` rule (`scope-map.cjs:144`) rather than the dedicated `root-manifest` rule. So the behaviour survives while the reason string silently changes and the file becomes undiscoverable for its only purpose: strictly worse on both counts, for no gain.

Recorded either way, as asked: had the answer gone the other direction, the move would have needed the `ROOT_MANIFESTS` entry deleted and `test_gate_scope_engine.py` re-pinned, the same two edits section 2 already lists for the fifteen.

---

## 4. Age baseline, measured 2026-09-06

This is the artifact the move phase re-derives to prove the move changed nothing. If a row's entry, date or age differs after the files are relocated, something other than the location changed.

**How to re-derive it** (`git blame` per entry line, over the same fifteen files):

```bash
git blame --line-porcelain -- <file> \
  | awk '/^author-time /{t=$2} /^\t/{s=substr($0,2); sub(/^[ \t]+/,"",s);
         if (s!="" && substr(s,1,1)!="#") printf "%s %s\n", strftime("%Y-%m-%d",t), s}'
```

**What the number means, and what it does not.** `git blame` reports the last commit that TOUCHED the line, so an age here is a lower bound: an entry reformatted or re-indented since it was written reads as younger than it is. It is the right measure for this artifact anyway, because the artifact's job is to be re-derived identically, not to date the original decision. The
2026-08-23 history rewrite ([#532](https://github.com/rediacc/console/issues/532)) changed every commit SHA but preserved author dates, so these dates span it unaffected.

**Rows that could not be aged: none.** All fifteen files are tracked, all 146 entry lines blamed cleanly, and the run reproduced identically on a second pass. Six of the fifteen hold zero entries and are recorded as such rather than with a sentinel -- and each of the six says in its own header that empty is its correct state, which is why
`scripts/gates/check-suppression-liveness.ts` gives three of them a `minEntries` of 0 rather than demanding they be populated.

### Summary

| File | Entries | Oldest | Newest | Median |
|---|---|---|---|---|
| `.actions-upgrade-blocklist` | 0 | -- | -- | -- |
| `.audit-allowlist` | 0 | -- | -- | -- |
| `.audit-prod-allowlist` | 10 | 130 d | 21 d | 21 d |
| `.ci-parity-exempt` | 9 | 36 d | 3 d | 36 d |
| `.cli-i18n-orphan-allowlist` | 5 | 49 d | 49 d | 49 d |
| `.dead-bash-allowlist` | 14 | 46 d | 9 d | 46 d |
| `.deps-upgrade-blocklist` | 10 | 135 d | 41 d | 65 d |
| `.devcontainer-upgrade-blocklist` | 0 | -- | -- | -- |
| `.e2e-coverage-allowlist` | 21 | 49 d | 21 d | 49 d |
| `.embed-assets-upgrade-blocklist` | 0 | -- | -- | -- |
| `.go-deps-upgrade-blocklist` | 2 | 82 d | 49 d | 82 d |
| `.plan-housekeeping-allowlist` | 0 | -- | -- | -- |
| `.profiler-coverage-allowlist` | 71 | 31 d | 31 d | 31 d |
| `.runner-advice-allowlist` | 0 | -- | -- | -- |
| `.unverified-download-allowlist` | 4 | 4 d | 4 d | 4 d |
| **total** | **146** | | | |

### Per entry

#### `.audit-prod-allowlist`

| Line | Entry | Last touched | Age (days) |
|---|---|---|---|
| 16 | `1117141` | 2026-04-28 | 130 |
| 24 | `1118920` | 2026-05-19 | 109 |
| 32 | `1120680` | 2026-06-16 | 82 |
| 54 | `1123700` | 2026-08-15 | 21 |
| 55 | `1139373` | 2026-08-15 | 21 |
| 56 | `1139375` | 2026-08-15 | 21 |
| 57 | `1139376` | 2026-08-15 | 21 |
| 58 | `1139377` | 2026-08-15 | 21 |
| 59 | `1139378` | 2026-08-15 | 21 |
| 70 | `1124066` | 2026-08-15 | 21 |

#### `.ci-parity-exempt`

| Line | Entry | Last touched | Age (days) |
|---|---|---|---|
| 28 | `ci-only` | 2026-07-31 | 36 |
| 31 | `ci-only` | 2026-07-31 | 36 |
| 34 | `ci-only` | 2026-09-03 | 3 |
| 37 | `ci-only` | 2026-07-31 | 36 |
| 40 | `ci-only` | 2026-07-31 | 36 |
| 43 | `ci-only` | 2026-07-31 | 36 |
| 46 | `ci-only` | 2026-07-31 | 36 |
| 49 | `ci-only` | 2026-07-31 | 36 |
| 52 | `ci-only` | 2026-07-31 | 36 |

#### `.cli-i18n-orphan-allowlist`

| Line | Entry | Last touched | Age (days) |
|---|---|---|---|
| 17 | `commands.sync.` | 2026-07-18 | 49 |
| 18 | `errors.term.` | 2026-07-18 | 49 |
| 19 | `commands.machine.health.` | 2026-07-18 | 49 |
| 20 | `commands.config.infra.push.dns` | 2026-07-18 | 49 |
| 22 | `docs.` | 2026-07-18 | 49 |

#### `.dead-bash-allowlist`

| Line | Entry | Last touched | Age (days) |
|---|---|---|---|
| 20 | `glob:.ci/scripts/test/gates/` | 2026-07-21 | 46 |
| 23 | `glob:.ci/tutorials/` | 2026-07-21 | 46 |
| 26 | `dispatch:phase_` | 2026-07-21 | 46 |
| 36 | `manual:.ci/scripts/deploy/deploy-proxy.sh` | 2026-07-21 | 46 |
| 39 | `manual:.ci/scripts/security/dependency-inventory.sh` | 2026-07-21 | 46 |
| 42 | `manual:.devcontainer/start-vscode.sh` | 2026-07-21 | 46 |
| 45 | `manual:scripts/ops/apply-cf-redirect-rules.sh` | 2026-07-21 | 46 |
| 48 | `manual:scripts/ops/linode-cluster-validation.sh` | 2026-07-21 | 46 |
| 51 | `manual:scripts/ops/r2-oneshot-scrub.sh` | 2026-07-21 | 46 |
| 54 | `manual:scripts/pre-commit-check.sh` | 2026-07-21 | 46 |
| 57 | `manual:.ci/breakpoint/scripts/sync-breakpoint.sh` | 2026-07-27 | 41 |
| 60 | `manual:.ci/docker/run-in-web.sh` | 2026-08-28 | 9 |
| 63 | `manual:.ci/scripts/test/manual/probe-receipt-stability.sh` | 2026-08-28 | 9 |

#### `.deps-upgrade-blocklist`

| Line | Entry | Last touched | Age (days) |
|---|---|---|---|
| 19 | `@eslint/js` | 2026-04-24 | 135 |
| 22 | `@astrojs/react` | 2026-07-21 | 46 |
| 23 | `@astrojs/mdx` | 2026-04-29 | 129 |
| 24 | `astro` | 2026-07-04 | 63 |
| 27 | `glob` | 2026-07-04 | 63 |
| 30 | `@types/node` | 2026-04-24 | 135 |
| 33 | `eslint-plugin-unicorn` | 2026-06-16 | 82 |
| 36 | `playwright` | 2026-07-04 | 63 |
| 37 | `@playwright/test` | 2026-07-26 | 41 |
| 39 | `eslint` | 2026-07-02 | 65 |

#### `.e2e-coverage-allowlist`

| Line | Entry | Last touched | Age (days) |
|---|---|---|---|
| 19 | `backup_delete` | 2026-07-18 | 49 |
| 20 | `backup_list` | 2026-07-18 | 49 |
| 21 | `ceph_client_mount` | 2026-07-18 | 49 |
| 22 | `ceph_client_unmount` | 2026-07-18 | 49 |
| 23 | `ceph_clone_image` | 2026-07-18 | 49 |
| 24 | `container_remove` | 2026-07-18 | 49 |
| 25 | `repository_autostart_disable` | 2026-07-18 | 49 |
| 26 | `repository_autostart_disable_all` | 2026-07-18 | 49 |
| 27 | `repository_autostart_enable` | 2026-07-18 | 49 |
| 28 | `repository_autostart_enable_all` | 2026-07-18 | 49 |
| 29 | `repository_autostart_list` | 2026-07-18 | 49 |
| 30 | `repository_cat` | 2026-07-18 | 49 |
| 31 | `repository_commit_meta` | 2026-07-18 | 49 |
| 32 | `repository_diff` | 2026-07-18 | 49 |
| 33 | `repository_down_all` | 2026-07-18 | 49 |
| 34 | `repository_ownership` | 2026-07-18 | 49 |
| 35 | `repository_prune` | 2026-07-18 | 49 |
| 36 | `repository_template_apply` | 2026-07-18 | 49 |
| 37 | `repository_up_all` | 2026-07-18 | 49 |
| 55 | `backup_restore` | 2026-08-15 | 21 |
| 70 | `machine_uninstall` | 2026-08-16 | 21 |

#### `.go-deps-upgrade-blocklist`

| Line | Entry | Last touched | Age (days) |
|---|---|---|---|
| 13 | `github.com/landlock-lsm/go-landlock` | 2026-06-16 | 82 |
| 25 | `k8s.io/kubelet` | 2026-07-18 | 49 |

#### `.profiler-coverage-allowlist`

| Line | Entry | Last touched | Age (days) |
|---|---|---|---|
| 20 | `breakpoint.yml:preflight` | 2026-08-05 | 31 |
| 21 | `breakpoint.yml:session` | 2026-08-05 | 31 |
| 24 | `profiler-probe.yml:facts-latest` | 2026-08-05 | 31 |
| 25 | `profiler-probe.yml:facts-slim` | 2026-08-05 | 31 |
| 26 | `profiler-probe.yml:post-nested-latest` | 2026-08-05 | 31 |
| 27 | `profiler-probe.yml:post-nested-slim` | 2026-08-05 | 31 |
| 32 | `autopilot.yml:finish` | 2026-08-05 | 31 |
| 33 | `autopilot.yml:gate` | 2026-08-05 | 31 |
| 34 | `autopilot.yml:model` | 2026-08-05 | 31 |
| 35 | `autopilot.yml:sweeper` | 2026-08-05 | 31 |
| 38 | `backfill-release-sentinel.yml:backfill` | 2026-08-05 | 31 |
| 41 | `cd-deploy-account.yml:build` | 2026-08-05 | 31 |
| 42 | `cd-deploy-account.yml:deploy` | 2026-08-05 | 31 |
| 43 | `cd-deploy-account.yml:read-regions` | 2026-08-05 | 31 |
| 46 | `cd-deploy-worker.yml:deploy` | 2026-08-05 | 31 |
| 49 | `cd-v2.yml:init` | 2026-08-05 | 31 |
| 50 | `cd-v2.yml:publish` | 2026-08-05 | 31 |
| 51 | `cd-v2.yml:smoke-test` | 2026-08-05 | 31 |
| 52 | `cd-v2.yml:tag-and-release` | 2026-08-05 | 31 |
| 55 | `ci-build-docker.yml:build-cli-docker` | 2026-08-05 | 31 |
| 56 | `ci-build-docker.yml:build-cli-docker-skip` | 2026-08-05 | 31 |
| 57 | `ci-build-docker.yml:build-devcontainer-amd64` | 2026-08-05 | 31 |
| 58 | `ci-build-docker.yml:build-devcontainer-arm64` | 2026-08-05 | 31 |
| 59 | `ci-build-docker.yml:build-devcontainer-manifest` | 2026-08-05 | 31 |
| 60 | `ci-build-docker.yml:build-renet-docker` | 2026-08-05 | 31 |
| 61 | `ci-build-docker.yml:build-renet-skip` | 2026-08-05 | 31 |
| 62 | `ci-build-docker.yml:build-server-docker-amd64` | 2026-08-05 | 31 |
| 63 | `ci-build-docker.yml:build-server-docker-arm64` | 2026-08-05 | 31 |
| 64 | `ci-build-docker.yml:build-server-docker-manifest` | 2026-08-05 | 31 |
| 65 | `ci-build-docker.yml:build-server-docker-skip` | 2026-08-05 | 31 |
| 68 | `ci-build-renet.yml:build-renet` | 2026-08-05 | 31 |
| 69 | `ci-build-renet.yml:cross-compile-smoke` | 2026-08-05 | 31 |
| 70 | `ci-build-renet.yml:extract-renet` | 2026-08-05 | 31 |
| 73 | `ci-quality.yml:quality-branch` | 2026-08-05 | 31 |
| 74 | `ci-quality.yml:quality-static` | 2026-08-05 | 31 |
| 75 | `ci-quality.yml:quality-submodule-branches` | 2026-08-05 | 31 |
| 78 | `ci.yml:breakpoint-lifecycle` | 2026-08-05 | 31 |
| 79 | `ci.yml:cancel-watchdog` | 2026-08-05 | 31 |
| 80 | `ci.yml:check-release-state` | 2026-08-05 | 31 |
| 81 | `ci.yml:ci-complete` | 2026-08-05 | 31 |
| 82 | `ci.yml:deploy-preview` | 2026-08-05 | 31 |
| 83 | `ci.yml:elite-run-test` | 2026-08-05 | 31 |
| 84 | `ci.yml:finalize-release-sentinel` | 2026-08-05 | 31 |
| 85 | `ci.yml:initialize` | 2026-08-05 | 31 |
| 86 | `ci.yml:label-guide` | 2026-08-05 | 31 |
| 87 | `ci.yml:package-tests` | 2026-08-05 | 31 |
| 88 | `ci.yml:pipeline-sentinel` | 2026-08-05 | 31 |
| 89 | `ci.yml:review-gate` | 2026-08-05 | 31 |
| 90 | `ci.yml:smoke-test-preview` | 2026-08-05 | 31 |
| 91 | `ci.yml:stripe-sandbox` | 2026-08-05 | 31 |
| 92 | `ci.yml:validate-promote` | 2026-08-05 | 31 |
| 95 | `claude-mention.yml:claude` | 2026-08-05 | 31 |
| 98 | `claude-review-reusable.yml:review` | 2026-08-05 | 31 |
| 101 | `cleanup-preview.yml:cleanup` | 2026-08-05 | 31 |
| 104 | `cleanup-r2-staging.yml:cleanup` | 2026-08-05 | 31 |
| 107 | `ct-install-methods.yml:install-methods-complete` | 2026-08-05 | 31 |
| 108 | `ct-install-methods.yml:test-linux-arm64` | 2026-08-05 | 31 |
| 109 | `ct-install-methods.yml:test-linux-x64` | 2026-08-05 | 31 |
| 112 | `ct-tests.yml:migration-test` | 2026-08-05 | 31 |
| 113 | `ct-tests.yml:test-license-enforcement` | 2026-08-05 | 31 |
| 114 | `ct-tests.yml:test-renet` | 2026-08-05 | 31 |
| 117 | `ct-update-flow.yml:test-linux-x64` | 2026-08-05 | 31 |
| 120 | `edge-clone-d1.yml:clone` | 2026-08-05 | 31 |
| 121 | `edge-clone-d1.yml:read-regions` | 2026-08-05 | 31 |
| 124 | `housekeeping.yml:cleanup` | 2026-08-05 | 31 |
| 125 | `housekeeping.yml:stripe-cleanup` | 2026-08-05 | 31 |
| 128 | `nightly-status.yml:report` | 2026-08-05 | 31 |
| 131 | `promote-stable.yml:promote` | 2026-08-05 | 31 |
| 132 | `promote-stable.yml:verify-stable` | 2026-08-05 | 31 |
| 135 | `review-status.yml:review-status` | 2026-08-05 | 31 |
| 138 | `watchdog-monitor.yml:monitor` | 2026-08-05 | 31 |

#### `.unverified-download-allowlist`

| Line | Entry | Last touched | Age (days) |
|---|---|---|---|
| 16 | `awscli.amazonaws.com` | 2026-09-01 | 4 |
| 19 | `raw.githubusercontent.com/nvm-sh/nvm` | 2026-09-01 | 4 |
| 22 | `claude.ai/install.sh` | 2026-09-01 | 4 |
| 25 | `download.docker.com/linux/ubuntu/gpg` | 2026-09-01 | 4 |


---

## 5. Files BORN here, which section 2 cannot describe

Section 2 is the record of a move. Two names now in `POLICY_FILES` never moved, because they were written into this directory in the first place, and a reader looking for them in that table will not find them.

| File | Added | Reader, by symbol | Why it is policy |
|---|---|---|---|
| `.language-policy-allowlist` | `.ci/scripts/quality/check_language_policy.py` | a per-path exemption from ruling 7, each with a `BLOCKER:` reason |
| `hook-exec-baseline.json` | 2026-09-09 (D0) | `.ci/rediacc_ci/quality/hook_exec_baseline.py`, through `policy_path()` | see below |
| `worklist-env-registry.json` | 2026-09-09 (D2) | `.ci/rediacc_ci/quality/worklist_env_registry.py`, through `policy_path()` | see below |
| `.w7p5a-real-run-blocklist` | 2026-09-09 | `.ci/rediacc_ci/quality/w7p5a_real_run_blockers.py`, through `policy_path()` | 39 BLOCKER-gated real-run exemptions for W7P5-a, checked in both directions against `.ci/shadow/w7p5a-status.json` |
| `tree-shape.json` | 2026-09-21 | `.ci/rediacc_ci/quality/tree_shape.py`, through `policy_path()` | the permitted-class table for the repository root and `agent/`; every row is a claim about what the tree may look like, and a change to the tree can stop it being true |
| `.host-toolchain-exceptions` | 2026-09-23 | `.claude/rediacc_hooks/guards/block_host_toolchain_run.py`, through `policy_path()` | the one category that may excuse running on a host the guard would otherwise route into the devbox, a host-only interactive auth ceremony; the category it refuses (a devbox gap, which is fixed in `.devcontainer/Dockerfile`) is checked mechanically rather than left to the reader |

### `hook-exec-baseline.json` is the only non-dotfile and the only `.json` here

Both are deliberate, and it still satisfies the section 1 predicate on all four clauses.

It is a PINNED MEASUREMENT rather than a list of exempted entries: how many processes the harness starts for one tool call, derived from `.claude/settings.json` by `.claude/rediacc_hooks/execcount.py`. A name-per-line dotfile cannot hold a table of per-tool, per-reading counts, which is why the shape differs from its neighbours.

* **A decision, not data.** Every number in it is a claim about the world that an edit to
`.claude/settings.json` can stop being true, and the gate refuses in BOTH directions: growth is a regression, and a SHRINK is also refused, with the new value printed to paste. A baseline that silently absorbs an improvement cannot prove the next one.
* **BLOCKER-gated.** Its `ambiguousMatchers` block is the suppression surface, and every
entry there carries a `BLOCKER:` reason the gate checks for by name. There is one entry today: the `Bash` matcher is written bare rather than anchored, and nothing in this repository records whether the harness matches by `search` or by `fullmatch`, so under one reading `Bash` also selects the tool `BashOutput` and under the other it does not. The two readings differ by nine
processes. It is pinned rather than guessed at, and it shrinks by anchoring the matcher to `^Bash$`, never by editing the list.
* **It has a parser.** `hook_exec_baseline.load_baseline()`, which refuses an empty
`probeTools` and a missing `measured` block rather than reporting zero findings.
* **Its location is an implementation detail.** One reader, reaching it through
`policy_path("hook-exec-baseline.json")`.

W5's target is "2 processes per Bash tool call". It is 12 today, and until 2026-09-09 there was no artifact in the tree stating the 12, which is why this file exists.

### `worklist-env-registry.json`, the second non-dotfile, and the same argument

Every `WORKLIST_*` environment name the program reads: 133 of them, across 28 files that READ one (60 mention one at all, the difference being 30 shell fixtures that only ASSIGN them), at 181 read sites. Measured 2026-09-09; there was no registry and no schema before that date.

* **A decision, not data.** The `kind` of each name is a human's claim that the derivation
is right, and the derivation is wrong for two names in this tree today: the default `"1"` cannot distinguish a boolean from a count, and `WORKLIST_AGENT_HINT_MIN_MARGIN` and `WORKLIST_AGENT_PUSHBACK_MIN_SCORE` are both counts.
* **BLOCKER-gated in substance if not in spelling.** Its suppression surface is the
`exclusions` block, and each prefix carries the reason it is excluded rather than the gate hardcoding it. An exclusion that matches zero tracked paths is a finding, which is the liveness half. Three of the five kinds (`flag`, `handle`, `corpus`) additionally require a substantive `why`, because those are the three where a typo turns something OFF or narrows what is looked at.
* **It has a parser.** `worklist_env_registry.load_registry()`, which refuses an empty
name set and an empty exclusion set rather than reporting zero findings.
* **Its location is an implementation detail.** One reader, through
`policy_path("worklist-env-registry.json")`.

The defect it exists for: a typo'd name reads as UNSET. Four names default to `on` (`WORKLIST_AGENT_HINT`, `WORKLIST_AGENT_PUSHBACK`, `WORKLIST_CADENCE`, `WORKLIST_FOCUS`), so a misspelling leaves them running while the author believes they are off.

---

## 6. The file REFUSED entry: `.ci/config/bws-secret-map.json`

W4 P5 asked whether the Bitwarden secret map belongs here. **The answer is no**, and the answer is recorded rather than merely acted on, because the next reader will have the same idea: it is a `.json` under `.ci/`, it is read by CI, and section 5 has just established that a `.json` can live here. It still fails **three of the four section 1 clauses**, which is a worse case than
`.ci-trigger` in section 3, and that one already got a section of its own.

Measured 2026-09-09 against `.ci/config/bws-secret-map.json`, 191 lines, 58 secrets:

- **Clause 1, decision not data: FAILS.** It carries `refreshed_at` (line 12) and is
regenerated WHOLESALE from Bitwarden by `scripts/ops/bws-map-refresh.py`, with a second writer at `private/account/scripts/rotation/lib/bws-map.ts:75` that refreshes it after a rotation. Every row is a NAME to UUID pair that Bitwarden decides and this repository copies. Nobody chose any of it, so no row can stop being true in the way a suppression can: it goes stale, which is a
different failure with a different fix (re-run the refresher).
- **Clause 2, BLOCKER-gated: FAILS.** Zero `BLOCKER:` lines, and there is no honest one to
write. A per-UUID reason would have to be invented, and an invented reason is the exact thing `docs/agent-reference/suppressions.md` exists to keep out of these files.
- **Clause 3, has a parser: PASSES.** `.ci/scripts/quality/check_bws_map.py:115` opens it as
`MAP`. This is the one clause it satisfies, and on its own it proves nothing: section 3 refused `.ci-trigger` for failing exactly this clause, so passing it is necessary and not sufficient.
- **Clause 4, location is an implementation detail: FAILS, and this is the decisive one.**
`.github/actions/bws-secrets/action.yml:71` builds the path as `${{ github.action_path }}/../../../.ci/config/bws-secret-map.json`, so the location is reached by walking UP from the composite action's own directory at run time, and the next line fails the job with `bws-secret-map.json not found at $MAP` if the walk misses. Two more readers live OUTSIDE this repository's checkout,
in the `private/account` submodule: `private/account/scripts/rotation/lib/bws-map.ts:39` holds the path as `join('.ci', 'config', 'bws-secret-map.json')` and searches upward for the console checkout that has it, and `private/account/tests/integration/rotation-bitwarden-names.test.ts:46` joins the same path to assert the map exists. That is an EXTERNAL CONTRACT, which is the clause
that keeps `package.json` and `biome.json` at the repository root.

It is a worse case than `.language-policy-baseline.json`, which was kept out for clause 1 alone. Three clauses fail here, and one of the three is the cross-repository one.

### The mechanical assertion, so the decision reopens loudly

A refusal written only in prose is a refusal nobody re-derives. `check:ci-policy-inventory` therefore asserts all three failing clauses every run (`.ci/scripts/quality/check_policy_inventory.py`, direction 7):

1. the file EXISTS at `.ci/config/bws-secret-map.json` (a refusal about a file that is gone
is not a refusal, it is a stale paragraph),
2. it is NOT under `.ci/policy/`, and its name is in neither seam's `POLICY_FILES`,
3. it contains ZERO `BLOCKER:` occurrences.

The third is the live one. If somebody ever writes reasons into it, clause 2 stops failing, the argument above is no longer complete, and the gate reds pointing at this section instead of letting the decision drift. The correct response to that red is to re-run the section 1 predicate here, not to widen the gate.
