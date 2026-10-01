# PLAN: Held majors age out of the blocklist
Status: done
First-Seen: 2026-10-01
Owner: d778be9d
Updated: 2026-10-01
Depends-On: no-dep -- extends check-deps.ts in place; needs nothing from any other plan
Priority: P1 -- operator ruling 2026-10-01; 12 blocklisted majors are excused today with no time limit, the oldest for 477 days
Concurrency: parallel -- the gate and its policy files only; the shared registration lists get one appended name each
Owns: scripts/gates/check-deps.ts, .ci/policy/deps-major-exceptions.json, .ci/policy/.deps-upgrade-blocklist, docs/agent-reference/suppressions.md

## Problem (measured 2026-10-01)
A blocklisted major leaves categorizePackages at the blocked branch (`scripts/gates/check-deps.ts:188-193`). That branch runs before the breaking-bump test at `:195`, so the major goes into `blocked` and never into `heldMajor`. `hasFailure` (`:1181`) counts only must-upgrade and held majors, so a blocklist line excuses a major with no time limit. A read-only `npx tsx scripts/gates/check-deps.ts` exits 0 with "18 blocked, 21 too new" across 4 manifests. Of those 18, 16 are majors (`isBreakingBump`, `:149-154`). The other two are playwright and @playwright/test, which are minor-only and out of scope. They make 12 distinct holds (Seeds table). Eleven are past 90 days today. typescript is at 84 days and crosses 90 on 2026-10-06.

Two facts the design must handle, both measured with `npm view <pkg> time --json`:
- **@eslint/js 10.0.0 was published 2024-07-26 and is deprecated ("This version should not be used").** The real line started with 10.0.1 on 2026-02-06. The clock must skip deprecated versions, or this hold reads as 796 days old.
- **The clock line is the first line past `current`, not the line of `latest`.** If the clock used latest's line it would restart on every new major: eslint-plugin-unicorn is at 11 days on line 76 but 108 on line 66, and @astrojs/react is at 8 days on line 7 but 100 on line 6. That restart is exactly the "free forever" hole. The rule is first-line-past-current, which the operator confirmed on 2026-10-01 (/ask). 0.x lines follow `releaseLine` (`:138-144`), so lucide-react 0.575 clocks from 0.576.0. @types/node 23 was never published, so its clock starts at 24.0.0.

## Design
**Where the clock reads publish times.** `scripts/lib/release-age.ts` only does the window arithmetic (`isWithinFreshnessWindow` `:99-106`, `getMinReleaseAgeMs` `:54`). The registry reader the window actually uses is `fetchVersionPublishTime` (`scripts/gates/check-deps.ts:648-688`): it does a GET on `registry.npmjs.org/<pkg>` and reads `time[version]`, with a cache keyed per version. The change is to refactor that into `fetchPackument(name)`, cached per package, and build three readers on it: `fetchVersionPublishTime` (unchanged behaviour), `firstReleaseOfLine(name, line)`, which picks the lowest stable, non-deprecated version whose `releaseLine` equals `line` and returns its `time`, and the blocker evaluators. release-age.ts is not edited.

**Fixture seam.** When `FIXTURE_ROOT` is set (`:49-53`), `fetchPackument` reads `<root>/.fixture-registry/<encodeURIComponent(name)>.json` and never touches the network. A missing document returns null. Today fixtures avoid the registry only because the release-age window is set to 0 (`:1265`, short-circuited at `:709`). Nothing fakes a publish time yet, so this seam is new. Fixture times are written relative to `Date.now()` (for example, now minus 91 days), so no NOW seam is needed.

**Hook point.** In `checkDependencies`, after `categorizePackages` in the per-manifest loop (`:1073-1088`), take `cat.blocked.filter(p => isBreakingBump(p.current, p.latest))` and call `ageHeldMajors(...)`, scoped by `m.name`. It returns `{warn, fail, excused, cannotDate}`. A clock failure ORs into `hasFailure` (`:1181`) and fails `--upgrade` the same way held majors do (`:1161-1166`).
- Rule: `deadline = firstMs + 90d`.
- Fail when `now >= deadline`, unless an exception excuses it.
- Warn when `age >= 60d`.
- Stay silent below 60 days.
- An unknown first-release time is refused, not treated as young. This matches the fail-closed contract of `runNpmOutdated` (`:398-489`).

**Allowed majors are never held.** The blocklist wins over an allow entry (`:188` comes before `:198`), and an allow entry shadowed by a blocklist line already fails as dead (`:1091-1103`, selftest `:1456-1461`). An allowed major reaches `mustUpgrade` and the clock never sees it, so the two files cannot both apply to one package.

**Exceptions file `.ci/policy/deps-major-exceptions.json`**, `{"$comment":[...],"exceptions":{<key>:{owner,reason,blocker|expires}}}`.
- The key uses blocklist grammar, `(<dir>:)?<pkg>`, with the same scoping as `:188-189`: a scoped key applies to its own manifest, and a bare key applies to every manifest the blocklist line covers.
- Parsing is a pure function, `parseMajorExceptions(text, nowMs)`, modelled on `parseMajorAllow` (`:288-316`). Loading is modelled on `loadMajorAllow` (`:321-340`), and an absent file is a loud failure.
- Reason quality goes through `validateBlockerQuality` (`scripts/lib/blocker-validator.ts:175-218`: 30-character floor, banned phrases). The entry carries no `BLOCKER:` prefix, following the precedent of the JSON commit-attributions row (`docs/agent-reference/suppressions.md:46`).

**Exception refusals.** check:deps exits 1 when an entry:
- has no owner (owner must match `^[A-Za-z0-9._@-]{3,}$`);
- has no reason, or a low-quality one;
- has neither or both of `blocker` and `expires` (a free-text-only entry);
- has an `expires` that is not YYYY-MM-DD, is in the past ("expired"), or is more than 30 days from now. This is checked on every run, so no `added` field is needed; extending an expiry takes a new commit;
- has an unknown `blocker.kind`;
- has a key with no matching blocklist line;
- matches no blocklist-held major in this run ("dead", the same idea as `:1091`);
- has a mechanical blocker that has lifted ("stale").

**Blocker kinds: two, because today's seeds need exactly two.**
- `{"kind":"peer-range","package":P,"peer":Q,"excludes":L}`. Live while `P@dist-tags.latest` declares `peerDependencies[Q]` and no stable, non-deprecated published version of Q on line L satisfies that range. If the peer is dropped, or any version on L satisfies it, the entry is stale.
  - The range evaluator is in-file: `||` sets of space-separated comparators (`^ ~ >= > <= < =`, partial versions such as `^9.7` and `>=10.4`). Anything it cannot parse is refused, never passed.
  - `satisfiesRange` (`:800-815`) cannot be reused because it handles single shapes only.
  - `semver` is not a direct dependency, so importing it would add an unlisted dependency.
- `{"kind":"engine-floor","engine":"node"}`. Evaluated against the judged manifest's own `package.json` `engines.node`. Live while the major of its lower bound is below the clock line's major. A missing engines field makes the blocker not live.

**Exact texts.** `<m>` is `root` or the manifest path.
- WARN (stdout, yellow): `Held major aging: <pkg> <cur> -> <latest> (<m>): line <L> first released <date> (<ver>), <N> days ago. Deadline <date> (90 days); after it a blocklist line no longer excuses it.`
- FAIL (stderr): `✗ Held major past 90 days: <pkg> <cur> -> <latest> (<m>): line <L> first released <date> (<ver>), <N> days ago; deadline <date> passed. A .ci/policy/.deps-upgrade-blocklist line alone no longer excuses it: take it (add "<suggestedAllowKey>" to .ci/config/deps-major-allow.json and drop the blocklist line) or add an entry to .ci/policy/deps-major-exceptions.json with a mechanical blocker or an expiry at most 30 days out.`
- EXCUSED (stdout, every run, never silent): `  <pkg> (<m>), <N> days: excused by deps-major-exceptions.json "<key>" (owner <o>): <peer-range: P@v declares peer Q "<range>" | engine-floor: engines.node "<r>" | expires <date>>`
- Refusals, prefixed `✗ .ci/policy/deps-major-exceptions.json "<key>": `:
  - `no owner`
  - `no reason`
  - `free-text-only entries are refused; give exactly one of "blocker" (re-checked every run) or "expires" (YYYY-MM-DD, at most 30 days out)`
  - `expires <date> is <N> days out; the limit is 30`
  - `expired on <date>; the hold is unexcused again`
  - `blocker lifted: <P>@<v> declares peer <Q> "<range>", which admits <Q>@<w>. Delete the entry.` For engine-floor: `blocker lifted: <m>/package.json engines.node "<r>" now admits <L>.x. Delete the entry.`
  - `excuses nothing in this run (no blocklist-held major matches). Delete the entry.`
- CANNOT DATE: `✗ cannot date held major <pkg> (<m>): no stable, non-deprecated release on line <L> in the registry document. Unknown age is unchecked, not young.`

**Mutant seam.** `CHECK_DEPS_MUTANT=ignore-clock` skips the clock. It is honoured only when `CHECK_DEPS_ROOT` is set; on a real tree it is a loud refusal, so it can never weaken a real run.

## Files
- `scripts/gates/check-deps.ts`: packument cache, clock, exceptions loader, blocker evaluators, range evaluator, fixture registry, mutant, selftest group 11, header and help text (`:5-21`, `:982-1010`).
- `.ci/policy/deps-major-exceptions.json`: new, seeded as below.
- `.ci/policy/.deps-upgrade-blocklist`: header note (`:1-16`) saying a major hold expires at 90 days. The entry lines do not change.
- `docs/agent-reference/suppressions.md`: a new row after `:46`, and "Age policy" (`:118-120`) rewritten to say this is enforced for npm majors.
- **Required edits outside Owns (claim them first).** Because the file lives in `.ci/policy/`, `check:ci-policy-inventory` needs three-way equality between both name lists and the directory:
  - `scripts/lib/policy-paths.ts` POLICY_FILES (`:69-102`)
  - `.ci/rediacc_ci/policy_paths.py` POLICY_FILES (`:60-92`)
  - `.ci/policy/README.md` §2 table
  - `.ci/config/env-manifest.json` gate-seam shard (beside `:482`)
  - `scripts/data/doc-registry.md`, which is generated

## Tests (selftest group 11, `selftest()` `:1344`; e2e cases through `runFixture` `:1314` and `CHECK_DEPS_ROOT`)
The fixture is extended with `registry?: Record<string, packument>` and `exceptions?: object`, written by `buildFixture` (`:1253-1312`). Each test below lists its case and its control.
1. A blocklisted major at 89 days exits 0 and prints `Held major aging` with the deadline. Control: the same fixture at 91 days exits 1 and names the package and manifest.
2. Age comes from X.0.0, not the latest patch. X.0.0 at 120 days with X.4.1 at 5 days fails. Control: X.0.0 at 30 days is silent. Variant with the @eslint/js shape: a deprecated X.0.0 at 800 days and X.0.1 at 30 days is silent.
3. A live peer-range exception exits 0 and prints the excused line. Control: the fixture's newest P admits line L, so the entry is stale and the run exits 1. An engine-floor case and its control (engines `>=24`) are included too.
4. An exception that expired yesterday exits 1 with "expired". Controls: +10 days passes, +45 days is refused for being over the 30-day limit.
5. Missing owner, missing reason, and free-text-only each exit 1 with their own message. Control: a complete entry passes.
6. A 30-day hold prints no `aging` text and exits 0. Control: case 1's 89-day run does print it.
7. Mutant: `CHECK_DEPS_MUTANT=ignore-clock` on case 1's 91-day fixture must exit 0. The selftest asserts this, which proves the control actually depends on the clock. The same seam without `CHECK_DEPS_ROOT` must be refused.
8. Scope: a `private/account/web:vite` exception does not excuse a root vite hold. Control: a bare key excuses both.
9. A missing registry document gives CANNOT DATE and exit 1. A dead exception key exits 1. An allowed major never reaches the clock.
10. Pure range evaluator cases: `>=4.8.4 <6.1.0` vs 7, `^3 || ^9` vs 10, `^9.7`, `>=10.4`, and an unparseable range is refused.

## Seeds (age as of 2026-10-01 00:00Z; "line" is the clock line, the first line past current)
| Key (exceptions.json) | Manifest(s) | Held | Line | First release | Age | Blocker / expiry |
|---|---|---|---|---|---|---|
| typescript | root, account, account/web | 6.0.3->7.0.2 | 7 | 7.0.2 2026-07-08 | 84 (<90, warns; 90 on 10-06) SEED | peer-range typescript-eslint/typescript excludes 7 (8.71.0: ">=4.8.4 <6.1.0") |
| eslint | root | 9.39.4->10.11.0 | 10 | 10.0.0 2026-02-06 | 236 | peer-range eslint-plugin-import/eslint excludes 10 (2.32.0: "...^9") |
| @eslint/js | root | 9.39.4->10.0.1 | 10 | 10.0.1 2026-02-06 (10.0.0 deprecated) | 236 | same as eslint (10.0.1 peers eslint ^10) |
| eslint-plugin-unicorn | root | 65.0.1->76.0.0 | 66 | 66.0.0 2026-06-14 | 108 | same as eslint (66 through 76 all peer eslint >=10.4) |
| @types/node | root, account | 22.20.x->26.6.3 | 24 | 24.0.0 2025-06-10 | 477 | engine-floor node (>=22.13.0 / >=22.0.0) |
| glob | root | 11.1.0->13.0.6 | 12 | 12.0.0 2025-11-17 | 317 | expires 2026-10-15 (self-imposed override, `package.json:457`) |
| private/account/web:vite | account/web | 6.4.2->8.3.1 | 7 | 7.0.0 2025-06-24 | 463 | expires 2026-10-22 |
| private/account/web:@vitejs/plugin-react | account/web | 4.7.0->6.1.1 | 5 | 5.0.0 2025-08-07 | 419 | expires 2026-10-22 (6.x peers vite ^8) |
| private/account/web:lucide-react | account/web | 0.575.0->1.49.0 | 0.576 | 0.576.0 2026-03-02 | 212 | expires 2026-10-22 |
| astro | root | 5.18.1->7.3.5 | 6 | 6.0.0 2026-03-10 | 204 | expires 2026-10-29 |
| @astrojs/mdx | root | 4.3.14->8.0.2 | 5 | 5.0.0 2026-03-10 | 204 | expires 2026-10-29 (8.x peers astro ^7.2.10) |
| @astrojs/react | root | 5.0.5->7.0.0 | 6 | 6.0.0 2026-06-22 | 100 | expires 2026-10-29 |

Owner for every seed: `d778be9d`. Not seeded:
- playwright and @playwright/test: minor holds, outside the clock.
- stripe 22->23 in private/account and private/account/e2e: published 2026-10-01, too new, not blocklisted. It becomes an ordinary held major tomorrow and fails under the existing rules, which is unrelated to this plan but is a red to expect.

Operator veto point: @types/node's engine-floor blocker stays live for as long as Node 22 remains the engine floor. Choosing an expiry instead would force a Node 24 decision.

## Registration notes
- Env: `CHECK_DEPS_MUTANT` goes into the env-manifest gate-seam shard, sorted between `CHECK_DEPS_FORCE_PROBE_FAILURE` and `CHECK_DEPS_ROOT`. No other env name is needed; the fixture registry is derived from `CHECK_DEPS_ROOT`.
- After the edits, run `npx tsx scripts/gen/gen-docs.ts --write` to regenerate the doc-registry env table and inventory rows. `gate-test:docs-gen` must stay green.
- Suppressions row: `| Held-major exceptions | .ci/policy/deps-major-exceptions.json | scripts/gates/check-deps.ts. A blocklisted major whose first release on the next line is 90+ days old fails unless excused here; owner + reason + exactly one of a re-checked blocker (peer-range, engine-floor) or an expiry <=30 days out. Liveness in-gate (stale/dead/expired), because the oracle is the registry and check-suppression-liveness is offline by rule (:110-111) |`
- `check:deps` already runs `--selftest` first (`package.json:28`), so the new controls run in CI with no wiring change.

## Tasks
- [x] Refactor `fetchVersionPublishTime` onto a per-package `fetchPackument` with the fixture-registry branch.
    (ticked) 2026-10-01T05:51:16Z by d778be9d: verified by commit 4a386aa0e: landed in 4a386aa0e (check-deps.ts age clock, exceptions file, registrations); selftest 118 checks with group 11, real check:deps rc=0, ignore-clock mutant caught -- box: Refactor fetchVersionPublishTime onto a per-package fetchPac
- [x] Add `firstReleaseOfLine` (stable, non-deprecated, `releaseLine` match).
    (ticked) 2026-10-01T05:51:16Z by d778be9d: verified by commit 4a386aa0e: landed in 4a386aa0e (check-deps.ts age clock, exceptions file, registrations); selftest 118 checks with group 11, real check:deps rc=0, ignore-clock mutant caught -- box: Add firstReleaseOfLine (stable, non-deprecated, releaseLine
- [x] Add `parseMajorExceptions` and `loadMajorExceptions` (reason quality through blocker-validator, 30-day expiry check, both kinds).
    (ticked) 2026-10-01T05:51:17Z by d778be9d: verified by commit 4a386aa0e: landed in 4a386aa0e (check-deps.ts age clock, exceptions file, registrations); selftest 118 checks with group 11, real check:deps rc=0, ignore-clock mutant caught -- box: Add parseMajorExceptions and loadMajorExceptions (reason qua
- [x] Add the peer-range range evaluator and the engine-floor evaluator, both refusing what they cannot parse.
    (ticked) 2026-10-01T05:51:18Z by d778be9d: verified by commit 4a386aa0e: landed in 4a386aa0e (check-deps.ts age clock, exceptions file, registrations); selftest 118 checks with group 11, real check:deps rc=0, ignore-clock mutant caught -- box: Add the peer-range range evaluator and the engine-floor eval
- [x] Add `ageHeldMajors` in the `:1073` loop and wire it into the check-mode and upgrade-mode exits, using the exact texts above.
    (ticked) 2026-10-01T05:51:19Z by d778be9d: verified by commit 4a386aa0e: landed in 4a386aa0e (check-deps.ts age clock, exceptions file, registrations); selftest 118 checks with group 11, real check:deps rc=0, ignore-clock mutant caught -- box: Add ageHeldMajors in the :1073 loop and wire it into the che
- [x] Add the `CHECK_DEPS_MUTANT=ignore-clock` seam, refused outside `CHECK_DEPS_ROOT`.
    (ticked) 2026-10-01T05:51:20Z by d778be9d: verified by commit 4a386aa0e: landed in 4a386aa0e (check-deps.ts age clock, exceptions file, registrations); selftest 118 checks with group 11, real check:deps rc=0, ignore-clock mutant caught -- box: Add the CHECKDEPSMUTANT=ignore-clock seam, refused outside C
- [x] Add selftest group 11 (tests 1-10) and extend the summary line (`:1924-1934`).
    (ticked) 2026-10-01T05:51:21Z by d778be9d: verified by commit 4a386aa0e: landed in 4a386aa0e (check-deps.ts age clock, exceptions file, registrations); selftest 118 checks with group 11, real check:deps rc=0, ignore-clock mutant caught -- box: Add selftest group 11 (tests 1-10) and extend the summary li
- [x] Create `.ci/policy/deps-major-exceptions.json` with the 12 seeds; re-measure ages on the day it lands.
    (ticked) 2026-10-01T05:51:21Z by d778be9d: verified by commit 4a386aa0e: landed in 4a386aa0e (check-deps.ts age clock, exceptions file, registrations); selftest 118 checks with group 11, real check:deps rc=0, ignore-clock mutant caught -- box: Create .ci/policy/deps-major-exceptions.json with the 12 see
- [x] Register the policy file in policy-paths.ts, policy_paths.py and the README; register the env name; run gen-docs.
    (ticked) 2026-10-01T05:51:22Z by d778be9d: verified by commit 4a386aa0e: landed in 4a386aa0e (check-deps.ts age clock, exceptions file, registrations); selftest 118 checks with group 11, real check:deps rc=0, ignore-clock mutant caught -- box: Register the policy file in policy-paths.ts, policypaths.py
- [x] Update the blocklist header, the suppressions.md row, and the "Age policy" section.
    (ticked) 2026-10-01T05:51:23Z by d778be9d: verified by commit 4a386aa0e: landed in 4a386aa0e (check-deps.ts age clock, exceptions file, registrations); selftest 118 checks with group 11, real check:deps rc=0, ignore-clock mutant caught -- box: Update the blocklist header, the suppressions.md row, and th
- [x] Verify: `npm run check:deps` exits 0 on the real tree, printing 12 excused lines and the typescript warning. `check:ci-policy-inventory`, `check:ci-env-manifest` and `gate-test:docs-gen` are green.
    (ticked) 2026-10-01T05:51:24Z by d778be9d: verified by commit 4a386aa0e: landed in 4a386aa0e (check-deps.ts age clock, exceptions file, registrations); selftest 118 checks with group 11, real check:deps rc=0, ignore-clock mutant caught -- box: Verify: npm run check:deps exits 0 on the real tree, printin
