# PLAN: warn-* guards are outside the inventory that exists to keep guards alive
Status: executing
Owner: 9d92d9b6
Updated: 2026-08-28

## 0. The finding, measured

`check-hook-integrity.sh:136` builds its guard list from `block-*.sh` only:

    for _f in "$HOOKS/$_c"/block-*.sh; do

So every `warn-*.sh` guard is invisible to the gate whose stated purpose is that
a guard cannot silently disappear. Three are affected today —
`warn-hook-change.sh`, `warn-remote-drift.sh`, `warn-submodule-deletions.sh` —
plus `warn-stale-index.sh`, added this wave.

Check A's own failure text is the proof of what this costs: *"Until listed, each
of these can be deleted with no gate noticing."* That sentence is currently true
of four guards and nothing says so.

## 0.1 Claims verified before filing

- `on_disk` is populated at `:134-139` from the `block-*.sh` glob alone.
- **A uses it in both directions**: baseline→disk existence at `:156-160`, and
  disk→baseline (`unlisted`) at `:169-172`.
- **B uses it too**, at `:186`, for the block/allow direction check.
- `scripts/data/hook-inventory-baseline.json` held 38 entries, exactly the
  `block-*` set. `warn-stale-index.sh` was added to it this session, taking it
  to 39 against 38 globbed — which is why the pass line reads oddly today.
- **The obvious fix was probed and is wrong on its own.** Extending the glob to
  `warn-*` makes A correctly name all three uninventoried guards — and then B
  fails all four with `block=0,allow=0`, because a warn guard NEVER blocks.
  Measured, not predicted: `✗ B. guard(s) newly missing a direction:
  warn-hook-change.sh(block=0,allow=0) …`.

## 1. Why B must not simply be extended

B's model is "a guard needs a block case AND an allow case, because a guard with
only block-cases cannot detect OVER-blocking". A `warn-*` guard exits 0 always;
it has no block direction to have a case for. Demanding one would make the gate
wrong about four correct guards, and a gate that is wrong is a gate that gets
suppressed. The two models are genuinely different:

| | block-* | warn-* |
|---|---|---|
| directions | blocks / allows | warns / silent |
| exit codes | 2 / 0 | 0 / 0 (stderr is the signal) |

## 2. The change

**Split the enumeration, because A and B are asking different questions.**

- `all_guards` = `block-*` + `warn-*` — used by A, whose question is "can this
  file vanish unnoticed", which applies to every guard.
- `on_disk` = `block-*` only — used by B and C, whose question is about a
  block/allow pair that a warn guard does not have.

Then add the three uninventoried `warn-*` guards to the baseline.

**Explicitly NOT done here:** teaching B a warns/silent model. That is a real
improvement — `warn-stale-index.sh` already has five such cases in
`test-hooks.sh` — but it needs a second covmap shape, and it is a separate
change from closing the deletion hole. Recorded in §5 rather than half-built.

## 3. Controls (each must FAIL before and PASS after)

1. Remove a `warn-*` guard from the baseline → A reds naming it as uninventoried.
   **Today this cannot fail**, which is the defect.
2. Delete a baselined `warn-*` guard from disk → A reds naming it as gone.
3. B still passes: no warn guard appears in its `newly missing a direction` list.
4. The `block-*` behaviour is unchanged: baseline count and B's output match
   what they were before the split.

## 4. Verification

`npm run check:ci-hook-integrity` green, its pass line naming 42 baselined
guards, and B unchanged. Controls 1 and 2 planted and restored byte-identical.

## 5. What is left open

B has no warns/silent model, so a `warn-*` guard can still lose the case that
proves it stays SILENT on prose — the exact class
`check:ci-guard-mention-anchoring` was added for in `43d7797d7`. That gate now
covers the prose direction behaviourally for every guard including warns, which
is why this is a gap rather than a hole.
