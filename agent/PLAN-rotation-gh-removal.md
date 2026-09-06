# Removing `gh` from secret rotation

Status: PLAN — 2026-09-06, session d1589e0b
Operator ask: *"plan for removing gh cli tool usage there since we don't keep them
in github. also remove from github."*

## Why this is urgent rather than tidy

`./run.sh rotation rotate <slug>` pushes to GitHub through the
`github-secret:<NAME>` consumer refs in `scripts/rotation/lib/config.ts`. Those
refs do not consult whether the secret still exists on GitHub — they push it.

**This already fired.** On 2026-09-05, after all 45 org secrets were deleted, a
rotation RESURRECTED four of them. They had to be deleted a second time. Any
rotation run today does it again, silently, and the first sign is a
`check:ci-secret-scope` finding or a stale credential nobody is watching.

## The exact surface

| where | count | action |
|---|---|---|
| `scripts/rotation/lib/config.ts` — `github-secret:` consumer refs | **10** across 6 slugs (`cf-cd` 1, `cf-breakpoint` 1, `cf-r2` 5, `otlp-eu/us/asia` 1 each) | remove 9, **KEEP `cf-breakpoint`'s** |
| `scripts/rotation/lib/config.ts` — `githubSecretNames` fields | **9** | remove 8, keep `cf-breakpoint`'s |
| `rotation-manifest.json` — `github_secret_names` | **11 slugs** | remove 10, keep `cf-breakpoint` |
| `scripts/rotation/commands/init.ts` | lines 112-113, 172, 248, 257 | stop writing `github_secret_names` for the removed slugs |
| `scripts/rotation/consumers/github-secret.ts` (63 lines) | — | **KEEP.** `cf-breakpoint` still needs it |
| `scripts/rotation/lib/credentials.ts:130-137` (`gh auth status`) | — | **KEEP**, for the same reason |

## The one that stays, and why

`cf-breakpoint` → `BREAKPOINT_TUNNEL_TOKEN` is a REPO-level secret that survived
the org deletion, and `breakpoint.yml` deliberately reads it from GitHub because a
later step in that job hands a human a shell (see
`agent/PLAN-breakpoint-secret-shape.md`). Removing its push path would leave that
token un-rotatable. So this is a NARROWING of `gh` usage from 10 refs to 1, not an
elimination, and the plan should not pretend otherwise.

## Sequence

1. **Manifest first, code second.** Drop `github_secret_names` from the 10 slugs in
   `rotation-manifest.json`. `rotation check` compares manifest to live platform
   state, so run it before and after: the diff must be exactly those keys.
2. Remove the 9 `github-secret:` consumer refs from `config.ts`.
3. Remove the 8 `githubSecretNames` fields.
4. Update `init.ts` so a fresh bootstrap does not reintroduce them. **This is the
   step that makes the removal durable** — without it, `rotation init` rebuilds
   exactly what steps 1-3 deleted.
5. Run the rotation test suite. The known casualty is
   `rotation-bitwarden-names.test.ts`: **4 tests encode the old GitHub↔Bitwarden
   name mapping**. They are testing scaffold that is being deleted, so they go
   with it — but read each one first, because any assertion that is really about
   the BITWARDEN half must be kept and re-pointed, not dropped.
6. `./run.sh rotation check` must be clean, and `rotation list` must still show
   every slug.

## Verification that this actually removed the hazard

A grep is not enough — the point is behavioural. After the change, a **dry-run
rotation of a slug that used to push** (e.g. `cf-cd`) must make no `gh secret set`
call. The cheapest proof is a control in the rotation tests that stubs the
`github-secret` consumer and asserts it is never dispatched for those slugs, with
its pair asserting it IS still dispatched for `cf-breakpoint`. Without the pair,
a consumer accidentally disabled for everything would pass.

## Scope note

All of this is in the `private/account` SUBMODULE, so it is its own commit and its
own PR, coordinated with console only if a console gate reads the manifest.
`.ci/config/bws-secret-map.json` and console's gates are unaffected: they describe
Bitwarden, which is now the only writer.
