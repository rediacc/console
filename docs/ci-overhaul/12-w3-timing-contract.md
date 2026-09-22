# 12. The W3 timing contract

Status: done
Owner: T-SCHED B5
Updated: 2026-09-09

This file settles how a timing becomes admissible in this programme, and it exists because one gate carries four different figures across four files and every reader so far has treated them as a disagreement. They are not. They are four statistics of one gate, taken with different instruments for different questions, and only one of them is computed the way the tool that JUDGES
cost computes it.

The rule, in one line: **one statistic, one source.** The statistic is the FLOOR of five raw measurements. The source is a quiesced worktree whose tree id is recorded beside the number.

---

## 1. The statistic: the floor, and nothing else

`.ci/cache/gate-durations.json` is written by the runner and read by the tier oracle. Three properties of it decide what a number here may mean:

* **Only a PASSING run is recorded** (`scripts/ci-runner/run.ts:489`). A gate that fails
fast is cheap in wall clock and has measured nothing; folding that into the cost would demand a 21s gate into the pre-push lane forever, which is exactly what happened to three gates on 2026-09-02.
* **The window is the last five raw measurements**, `RECENT_KEEP = 5`
(`scripts/ci-runner/run.ts:439`), oldest first, alongside a scheduling `ewma` that is NOT the judged number.
* **The oracle judges `Math.min(recent)`** (`scripts/gates/check-gate-manifest.ts:527`, under
the comment at `:518` that gives the reason: "load only ever adds time, so the cheapest recent run is the honest cost"), and it declines to tier a gate at all until the window holds `MIN_SAMPLES_TO_TIER = 5` samples (`scripts/gates/check-gate-manifest.ts:104`, applied at `:148` and reported as unjudged at `:545`).

So an admissible cost figure for a gate is `min` of five passing runs. A single run is a SAMPLE. A mean or an ewma is a scheduling estimate. Neither is the statistic the oracle will judge you against, and quoting one as though it were is how a timing turns into an argument.

### Line numbers in this section will drift, and two citations already have

`scripts/ci-runner/manifest.ts:5818` cites `check-gate-manifest.ts:503` for the floor ruling and `agent/plans/PLAN-tooling-transformation.md:792` cites `:511-520`. The ruling is at `:518` to `:527` as of 2026-09-09. Both citations were correct when written. Cite the SYMBOL as well as the line when it matters: the ruling is the `const floor = ... ? Math.min(...recent) : ewma`
assignment, and `MIN_SAMPLES_TO_TIER` is the gate on whether it is applied at all.

---

## 2. The four `check:ci-pytest` figures, reconciled

Read live from `.ci/cache/gate-durations.json` on 2026-09-09:

    "check:ci-pytest": { "ewma": 405204,
                         "recent": [367884, 394649, 401145, 391815, 406786] }

    floor   367.884s   <- min(recent), the admissible statistic
    median  394.649s
    ewma    405.204s
    max     406.786s

Against that window, every figure in the tree resolves:

| Figure | Where it is written | What it actually is |
|---|---|---|
| **367.9s** | `scripts/ci-runner/manifest.ts:5817` | `min(recent)` rounded. The one admissible number, and the reason `slow: true` is on the entry. |
| 396s | `scripts/ci-runner/manifest.ts:5822`, `agent/plans/PLAN-pytest-parallelism.md:226` | One wall-clock run of the `-n 8 --dist loadgroup` cutover (823.93s serial to 396s, 2.08x). It sits between the 394.649s and 401.145s samples in the same window. A SAMPLE. |
| 381.41s | `.ci/rediacc_ci/check_pytest.py:154` | One instrumented run answering a DIFFERENT question: how many workers to buy. Serial 823.93s, `-n 8` 381.41s (2.16x), `-n 16` 377.18s. Its own sub-measurement, the 294.65s guards fixture pinned to one worker, is the floor that makes 16 workers pointless. |
| 318.2s | `docs/ci-overhaul/11-timing-baseline.md` | The same gate inside the 2026-09-06 full-run baseline, before later port batches grew the corpus. Older corpus, so not comparable to the four above at all. |

None of these contradicts another. Three are samples of one gate under three configurations and one is a fifth statistic of an older corpus. Only `367.9s` is computed the admissible way, and it is the only one any box may cite as a cost.

---

## 3. The source: a quiesced worktree, with its tree id recorded

A number from a contended tree is not admissible. Invariant 13 exists because a 4.5s gate measured 21s while two other sessions were writing, and the oracle then demanded it be marked slow.

To take an admissible measurement:

    git status --porcelain          # MUST be empty. Not "only my files". Empty.
    git rev-parse HEAD              # the commit
    git rev-parse 'HEAD^{tree}'     # the TREE ID, which is what was measured
    npm run ci                      # five times, all passing, or the window is short

Record all three alongside the figure. The tree id is the load-bearing one: a commit can be re-pointed and a branch name means nothing later, while a tree id names the exact bytes the number describes. On a dirty worktree `HEAD^{tree}` describes the COMMIT and not what ran, which is why the porcelain check comes first rather than beside it.

**No measurement was taken on this tree for this file, and that is the contract working rather than a gap.** Measured 2026-09-09, `git status --porcelain` returns 352 lines here: several sessions hold uncommitted work in this checkout, so nothing timed in it is admissible. The figures in section 2 are read out of the recorded cache and out of the files that already carry them; not
one of them is a new measurement.

---

## 4. What a timing may and may not be used for

**No target in this slice is checked off by a timing.** The W3 targets are structural: the shard plan exists and refuses correctly, the matrix emits, the aggregator counts shards. A timing is a recorded OBSERVATION attached to one of those boxes, never its acceptance criterion. A box whose acceptance is a number gets closed by a lucky run.

**The quality-tier wall has never been measured, and it cannot be measured here.** It is the wall clock of the slowest `quality-*` job on a GitHub runner, which has a different core count, a cold cache and a network the local box does not have. It must come from a GitHub run. Any local figure standing in for it is a different quantity wearing its name.

---

## 5. Where this leaves the reader

* Quoting a cost: use the floor of five, or say plainly which single run you mean.
* Adding a cost claim to a manifest entry: the oracle will judge it against
`min(recent)`, in both directions. A gate marked slow that is in fact cheap reds as loudly as the converse.
* Finding a figure that seems to contradict this file: check whether it is a floor, a
sample, an ewma, or a measurement of an older corpus, before calling it a disagreement. Four of the five figures above were already in the tree and none of them was wrong.
