#!/usr/bin/env node
// T-SCHED B2 D4. The receipt one matrix leg of a sharded quality lane writes about ITSELF, read back by `check:ci-quality-complete --receipts <dir>`.
//
// WHY A RECEIPT AT ALL. A matrix job reports ONE roll-up result for every leg, so a leg that was never created is indistinguishable from a leg that passed. Worse, with no `strategy.matrix` on the job at all GitHub evaluates `matrix.shard` as null, every `matrix.shard == N` conjunct is false, and the whole lane goes green having run nothing. A leg that counts what actually ran,
// and says so in the aggregator's own currency, is what makes that visible.
//
// COUNTS WHAT RAN, NOT WHAT WAS PLANNED. A literal emitted by the binder would report a full leg even when every step skipped, which is the exact vacuity above. The count is therefore derived from `steps.<id>.outcome`, and a step counts as run when its outcome is anything other than `skipped`.
//
// THE CURRENCY IS LOCK IDS, because `scripts/gates/check-quality-complete.ts` compares `gates` against `declaredShard.ids.length`, and one emitted step can carry several lock ids (five `check:lint*` ids ride one `Lint` step). `GATE_STEP_LOCK_MAP` is that translation, built at bind time by `jobLockIdMap` in `scripts/gate-bind.ts`, where every conjuncted gate's id is already known.
//
// A FILE RATHER THAN A HEREDOC IN THE STEP, and that is not cosmetic. The binder emitted this as an inline run block until 2026-09-20, when populating SHARD_COUNTS for the first time made `check:ci-workflows` red: 18 logic lines against a cap of 8. The cap exists so a workflow step stays env wiring plus one call, and the first real lane to shard was what proved the emitter had
// never been held to it.
//
// Required env, all written by `emitReceiptStep`:
//   GATE_STEP_LOCK_MAP  JSON, step id -> lock ids
//   STEPS_JSON          the steps context, as JSON
//   SHARD_INDEX         the leg number
//   SHARD_OF            how many legs the lane has
//   JOB_STATUS          the leg's own conclusion
//   RECEIPT_LANE        the lane name
//   RECEIPT_PATH        where to write the JSON
//
// Locally:
//   GATE_STEP_LOCK_MAP='{"gate_check_ci_seo":["check:ci-seo"]}' \
//   STEPS_JSON='{"gate_check_ci_seo":{"outcome":"success"}}' \
//   SHARD_INDEX=1 SHARD_OF=4 JOB_STATUS=success RECEIPT_LANE=quality-code \
//   RECEIPT_PATH=/tmp/receipt.json node scripts/ci/write-shard-receipt.cjs

'use strict';

const fs = require('fs');

const stepsCtx = JSON.parse(process.env.STEPS_JSON);
const map = JSON.parse(process.env.GATE_STEP_LOCK_MAP);
let gates = 0;
for (const stepId of Object.keys(map)) {
  const s = stepsCtx[stepId];
  if (s && s.outcome !== 'skipped') gates += map[stepId].length;
}
const receipt = {
  lane: process.env.RECEIPT_LANE,
  index: Number(process.env.SHARD_INDEX),
  of: Number(process.env.SHARD_OF),
  result: process.env.JOB_STATUS,
  gates,
};
fs.writeFileSync(process.env.RECEIPT_PATH, JSON.stringify(receipt));
