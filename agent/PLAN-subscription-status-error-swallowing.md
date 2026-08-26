# PLAN: `subscription status` swallows account-server errors and exits 0 silently

Status: done
Owner: 9d92d9b6
Updated: 2026-08-26

## Finding

`rdc subscription status` (no `-m`, the account view) exits **0** and writes
**zero bytes to both stdout and stderr** when the account server rejects the
call. Reproduced on a freshly set-up machine whose restored token was minted
elsewhere; the server answers:

```
HTTP 403  Token is bound to a different IP address
```

Observed (before):

```
$ rdc subscription status
exit=0 bytes=0
```

The account view's entire output is `outputRemoteStatus(status)`, so when the
report is unavailable the command is a silent no-op. The comment calling remote
status "optional" is wrong: it is the only thing the verb does.

## Root cause — three stacked swallows

1. `packages/cli/src/services/account/license.ts` —
   `fetchSubscriptionLicenseReport()` catches every error, sends it to
   telemetry, and returns `null`. The reason never reaches the caller.
2. `packages/cli/src/commands/subscription-actions.ts:111` —
   `if (!status) return;` turns that `null` into a silent success.
3. `packages/cli/src/commands/subscription-actions.ts` — the enclosing
   `catch { /* Remote status is optional */ }` swallows anything left.

## Sibling in the same class

`executeAccountRefresh()` (`subscription-actions.ts:345`) shares swallow #1. It
handles the `null` correctly (throws `ValidationError`, exit 2) but reports a
generic "Could not read account state from the account server." — the actionable
403 reason is still lost. Fixing only `status` would leave the class half-swept.

`doctor.ts:422` is the one caller that **legitimately wants** the tolerant
null: it races the fetch against a timeout and degrades to a `warn` row. Its
behavior must not change.

## Design

Split the fetch into a throwing core and a tolerant wrapper, so each caller
opts into the contract it actually wants:

- Add `fetchSubscriptionLicenseReportOrThrow()` to `license.ts`: performs the
  fetch, sets telemetry user context on success, tracks the error on failure,
  and **rethrows**.
- Keep `fetchSubscriptionLicenseReport()` as a thin wrapper that calls the
  throwing core and returns `null` on error — byte-identical contract for
  `doctor.ts`, which keeps its null-tolerant path untouched.
- `executeSubscriptionStatus()` calls the throwing variant, drops the
  `if (!status) return` and the empty `catch`, and lets `handleError` render the
  real server message and set a non-zero exit.
- `executeAccountRefresh()` calls the throwing variant too, so its failure names
  the real reason instead of the generic string.

No migration path, no dual behavior for one caller, no deprecation window.

## Files

| File | Change |
|---|---|
| `packages/cli/src/services/account/license.ts` | add throwing core; wrapper delegates |
| `packages/cli/src/commands/subscription-actions.ts` | `status` + `refresh` use throwing variant; delete empty catch |
| `packages/cli/src/commands/__tests__/subscription.test.ts` | regression tests |

`doctor.ts` is deliberately NOT edited.

## Tests (must FIRE on a planted defect, stay silent when clean)

1. `subscription status` when the report call rejects → non-zero exit **and**
   the server's message appears in output. Plant the defect by restoring
   `if (!status) return;` → test must fail.
2. `subscription status` on success → unchanged rendering (guards over-correction).
3. `subscription refresh` when the report call rejects → surfaces the server
   message, not the generic string.
4. `doctor` when the report call rejects → still a `warn` row, still exit 0
   (guards the tolerant wrapper's contract).

## Status

- [x] Finding reproduced against a live server (403, exact message captured)
- [x] Root cause confirmed by probing each layer in isolation
- [x] Implemented (`license.ts` split; `status` + `refresh` use the throwing variant)
- [x] Tests green: 2 new regression tests, each proven to FIRE on its planted
      defect and silent when clean; full CLI suite 182 files / 2403 tests pass;
      `tsc --noEmit` clean; biome clean
- [x] Verified live against the account server: `subscription status` went from
      `exit=0, 0 bytes` to `exit=1` naming "Token is bound to a different IP
      address"; `doctor` still degrades to a `warn` row (tolerant contract intact)

### Deliberately not changed

`renderActivationSection`'s `catch` (subscription-actions.ts:320) also drops the
reason, but it EMITS a warning and is one optional section of a multi-section
command, so it is not the silent-no-op class this plan addresses.
