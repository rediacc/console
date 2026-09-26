# Removing `gh` from secret rotation

Status: done -- 2026-09-24, session d778be9d. The GitHub consumer is deleted outright, cf-breakpoint included; see "Done 2026-09-24" at the end.
First-Seen: 2026-09-17
Operator ask: *"plan for removing gh cli tool usage there since we don't keep them in github. also remove from github."*

## Why this is urgent rather than tidy

`./run.sh rotation rotate <slug>` pushes to GitHub through the `github-secret:<NAME>` consumer refs in `scripts/rotation/lib/config.ts`. Those refs do not consult whether the secret still exists on GitHub — they push it.

**This already fired.** On 2026-09-05, after all 45 org secrets were deleted, a rotation RESURRECTED four of them. They had to be deleted a second time. Any rotation run today does it again, silently, and the first sign is a `check:ci-secret-scope` finding or a stale credential nobody is watching.

## The exact surface

| where | count | action |
|---|---|---|
| `scripts/rotation/lib/config.ts` — `github-secret:` consumer refs | **10** across 6 slugs (`cf-cd` 1, `cf-breakpoint` 1, `cf-r2` 5, `otlp-eu/us/asia` 1 each) | remove 9, **KEEP `cf-breakpoint`'s** |
| `scripts/rotation/lib/config.ts` — `githubSecretNames` fields | **9** | remove 8, keep `cf-breakpoint`'s |
| `rotation-manifest.json` — `github_secret_names` | **11 slugs** | remove 10, keep `cf-breakpoint` |
| `scripts/rotation/commands/init.ts` | lines 112-113, 172, 248, 257 | stop writing `github_secret_names` for the removed slugs |
| `scripts/rotation/consumers/github-secret.ts` (63 lines) | — | **KEEP.** `cf-breakpoint` still needs it |
| `private/account/scripts/rotation/lib/credentials.ts:130-137` (`gh auth status`) | — | **KEEP**, for the same reason |

## The one that stays, and why

`cf-breakpoint` → `BREAKPOINT_TUNNEL_TOKEN` is a REPO-level secret that survived the org deletion, and `breakpoint.yml` deliberately reads it from GitHub because a later step in that job hands a human a shell (see `agent/plans/PLAN-breakpoint-secret-shape.md`). Removing its push path would leave that token un-rotatable. So this is a NARROWING of `gh` usage from 10 refs to 1, not an
elimination, and the plan should not pretend otherwise.

## Sequence

1. **Manifest first, code second.** Drop `github_secret_names` from the 10 slugs in
`rotation-manifest.json`. `rotation check` compares manifest to live platform state, so run it before and after: the diff must be exactly those keys.
2. Remove the 9 `github-secret:` consumer refs from `config.ts`.
3. Remove the 8 `githubSecretNames` fields.
4. Update `init.ts` so a fresh bootstrap does not reintroduce them. **This is the
step that makes the removal durable** — without it, `rotation init` rebuilds exactly what steps 1-3 deleted.
5. Run the rotation test suite. The known casualty is
`rotation-bitwarden-names.test.ts`: **4 tests encode the old GitHub↔Bitwarden name mapping**. They are testing scaffold that is being deleted, so they go with it — but read each one first, because any assertion that is really about the BITWARDEN half must be kept and re-pointed, not dropped.
6. `./run.sh rotation check` must be clean, and `rotation list` must still show
every slug.

## Verification that this actually removed the hazard

A grep is not enough — the point is behavioural. After the change, a **dry-run rotation of a slug that used to push** (e.g. `cf-cd`) must make no `gh secret set` call. The cheapest proof is a control in the rotation tests that stubs the `github-secret` consumer and asserts it is never dispatched for those slugs, with its pair asserting it IS still dispatched for `cf-breakpoint`.
Without the pair, a consumer accidentally disabled for everything would pass.

## Scope note

All of this is in the `private/account` SUBMODULE, so it is its own commit and its own PR, coordinated with console only if a console gate reads the manifest. `.ci/config/bws-secret-map.json` and console's gates are unaffected: they describe Bitwarden, which is now the only writer.

## Done 2026-09-24

The operator's ruling of 2026-09-24 widened this plan from a narrowing to an elimination: no GitHub secret or variable is written by rotation, and `BWS_ACCESS_TOKEN` is the only GitHub secret left, which rotation does not own. The cf-breakpoint exception above was already obsolete: `breakpoint.yml` has fetched `CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN` from Bitwarden since 2026-09-14, no workflow reads `secrets.BREAKPOINT_TUNNEL_TOKEN`, and `gh secret list -R rediacc/console` shows only `BWS_ACCESS_TOKEN`.

Steps 1-4 had mostly landed before this session, in `private/account` commits `dd23271` (2026-09-06, every slug but cf-breakpoint) and `6ae35cb` (2026-09-15, cf-breakpoint). What remained was the machinery those commits left in place, and it is now gone:

- `rotation-manifest.json`: the 14 empty `github_secret_names` keys.
- `src/types/rotation-manifest.ts`: the `github_secret_names` field on all four platform schemas, and the `github-secret:` kind in the consumer-ref regex, so a manifest carrying one now fails to load.
- `scripts/rotation/consumers/github-secret.ts`: deleted. `verifyGitHubCli()` and its `gh auth status` call: deleted from `lib/credentials.ts`.
- `commands/rotate.ts`: every `setGitHubSecret` push site (aws-iam pair, cloudflare-token, turnstile, otlp), every `needsGh` preflight, and the `pushToConsumer` skip branch.
- `commands/init.ts`: the `githubNamesOf`/`Pair`/`Single` helpers and all seven `github_secret_names:` writes, so `init --force` cannot rebuild the field.
- `commands/check.ts`: the GitHub-vs-Bitwarden name-count drift check.

A defect the plan did not know about: `rotateCloudflareToken` demanded exactly one or two `github-secret:` consumer refs per slug and refused otherwise. Once `dd23271` removed those refs, every cf-cd, cf-r2 and cf-r2-media rotation (and cf-breakpoint's after `6ae35cb`) was refused before minting. The guard now requires a `bitwarden-sm:` consumer instead, and the dev `.env` keys come from `bitwarden_secret_names`, which share the `CLOUDFLARE_R2_*` spelling.

The control is `private/account/tests/integration/rotation-no-github.test.ts`: no `github-secret:` ref or GitHub-name key in the raw manifest or in `ROTATION_CONFIG`, no GitHub module and no `gh secret|variable|auth` call under `scripts/rotation/`, and planted-defect cases proving each scanner and the schema go red. The plan's proposed pair (the consumer still dispatched for cf-breakpoint) no longer applies, since nothing is dispatched for any slug.

`rotation check` was not run: with the `.env` credentials it mints an ephemeral Cloudflare token through the Global API Key and opens an `rdc term connect` session to the production observability machine, so it has no read-only form. `rotation list` (manifest-only) ran and shows all 15 slugs.
