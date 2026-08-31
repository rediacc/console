# PLAN: re-sync the nine `techDiff.description` values across 12 locales

Status: ready to run, gated on #583 merging
Owner: whichever session picks it up
Origin: worklist `#d84b5b51`, session f88f9be7, 2026-08-31. Its 120-minute autonomy
window closed unanswered, so its DEFAULT is the decision: **this does NOT ride #583; it is
its own pass, after #583 merges.** This file is that pass, written so it needs no
rediscovery.

## The defect

Nine solution pages had their English `techDiff.description` rewritten in `03b6259b6` to
drop a shared btrfs explainer that now lives once, in `solutions.mechanism.cow`. The
twelve locale values were NOT updated, and they were already behind: they translate the
pre-round-6, more technical English draft, so this is a register gap and not a missing
clause.

Measured, on the merged English:

    en  failoverTesting  "Old-school DR tests need production downtime, a room full of
                          engineers, and weeks of planning. Rediacc clones a whole setup
                          in seconds. The test runs on the copy. Production never stops."
    de  failoverTesting  "Traditionelle DR-Tests erfordern Produktionsausfallzeit, ein
                          Team von Ingenieuren und wochenlange Planung. Rediacc nutzt
                          btrfs Copy-on-Write-Snapshots, um in Sekunden einen isolierten
                          Klon Ihrer gesamten Infrastruktur zu erstellen. Der Test läuft
                          gegen den Klon — die Produktion stoppt nie."

The nine slugs, all at `pages.solutionPages.<slug>.techDiff.description`:
instantRecovery, safeOsTesting, retentionCompliance, cloudOutageProtection,
failoverTesting, vulnerabilityManagement, rapidRecovery, environmentCloning,
immutableBackups.

## Why no gate sees it

The nine keys are absent from `.naturalized-hashes.json`, so `check:ci-i18n-naturalization`
has no recorded English CRC to compare and structurally cannot flag them.
`check:ci-i18n-locale-only` asks the MIRROR question (a locale that moved while its English
did not), so it looks the other way by construction. `check:ci-i18n-ledger-growth`
(953b35ab1) stops this hole GROWING but is deliberately non-retroactive, so it is silent
here too, and its header says so.

## Why it is a pipeline run and not an edit

Two read-only sonnet agents were given the exact old->new English diff and correctly
declined to clause-edit: the locale text is a different register, not the same sentence
minus a clause. Re-translation is the only correct fix.

Sizing, measured with `--plan-only` on 2026-08-31, NOT estimated:

| scope | result |
|---|---|
| `de --group pages.solutionPages.failoverTesting` | 102 stale keys, 2 work-items |
| `de --surface solution` | 1949 stale, **REJECTED** over `LARGE_DELTA_REJECT_UNITS=150` |
| `de --surface solution --regressed-only` | 0 (none were ever tracked) |

So the smallest usable unit is a WHOLE PAGE: 9 pages x 12 locales x ~102 keys, roughly
11,000 keys of paid haiku output that replaces page content nobody asked to replace. That
volume is why it is its own pass rather than a rider on a 10,131-line PR.

## The run

```bash
cd private/growth/i18n_pipeline
for lang in de es fr it pt tr ru ja ko zh ar et; do
  for slug in instantRecovery safeOsTesting retentionCompliance cloudOutageProtection \
              failoverTesting vulnerabilityManagement rapidRecovery environmentCloning \
              immutableBackups; do
    ./run.sh --plan-only --lang "$lang" --group "pages.solutionPages.$slug"   # size it first
    ./run.sh            --lang "$lang" --group "pages.solutionPages.$slug"
  done
done
```

`--model haiku` is the default and the policy (CLAUDE.md); do not bump it without a
language whose output reads awkward.

## Before believing it

1. **Spot-check 3 locales x 3 pages against English by hand** before stamping anything.
   The 2026-07-28 incident that motivated `check-locale-only-edits.ts` was a pipeline run
   inventing pricing facts, and every other gate passed it.
2. `npm run i18n:generate-hashes`, then `npm run check:i18n` end to end.
3. `check:ci-i18n-locale-only` will see 108+ locale values move. Each is backed by an
   English change that is already on main by then, so it should pass; if it does not, read
   its finding rather than reaching for `--base`.
4. **Never `--mark-done --all-stale`** to close what the gate names. On this catalogue it
   means ~1,965 keys per locale and it cost session f88f9be7 23,561 bogus stamps.
   See `docs/agent-reference/TRAPS.md`.
