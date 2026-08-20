#!/usr/bin/env tsx
/**
 * check-naturalization-model-policy — the committed naturalization provenance must
 * name a model the repo's own policy allows.
 *
 * WHY THIS EXISTS. The naturalization model is configured in three places that do not
 * reference each other:
 *
 *   CLAUDE.md                                  "Use --model haiku"  (policy)
 *   private/growth .../ledger.py               default_model: haiku (metadata)
 *   private/growth .../registry.py             model: "kimi"        (what actually runs)
 *
 * The third one drifted during a later refactor and nothing noticed, because the only
 * artifact CI can see is the ledger this gate reads. On 2026-08-20 that drift surfaced
 * the hard way: the configured provider returned HTTP 402 mid-sweep, and the work was
 * being billed to a backend the policy doc does not mention at all.
 *
 * This gate cannot read `registry.py` -- private/growth is a separate repository and is
 * gitignored here (.gitignore:69), so CI genuinely cannot see it. What it CAN see is the
 * provenance every applied run stamps into the ledger. If a run naturalizes with a model
 * outside the policy set, that model lands in `$meta.models` and this fails. The drift
 * then arrives as a decision to make rather than a surprise on a billing page.
 *
 * It deliberately does NOT adjudicate which model is best. Changing the policy is a real
 * engineering call; the gate only insists the change be made ON PURPOSE, in CLAUDE.md and
 * here together, instead of leaking in through a default nobody read.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const LEDGER = path.join(ROOT, 'packages/www/src/i18n/translations/.naturalized-hashes.json');

/**
 * The models CLAUDE.md names for this pipeline: haiku is the default and the cheapest
 * capable one, with sonnet/opus explicitly permitted for a language whose haiku output
 * reads awkward. Matching is on the FAMILY, so a routine version bump
 * (claude-haiku-4-5 -> claude-haiku-5) does not fail the gate while a change of family
 * or vendor does.
 *
 * BLOCKER: keep in sync with CLAUDE.md's "i18n / Translations" section. If the policy
 * genuinely changes, change it in BOTH places in the same commit -- that pairing is the
 * entire point of this gate.
 */
const POLICY_FAMILIES = ['haiku', 'sonnet', 'opus'];

type Finding = { lang: string; model: string };

export function offendingModels(models: Record<string, string>): Finding[] {
  return Object.entries(models)
    .filter(([, model]) => !POLICY_FAMILIES.some((fam) => model.toLowerCase().includes(fam)))
    .map(([lang, model]) => ({ lang, model }))
    .sort((a, b) => a.lang.localeCompare(b.lang));
}

function selftest(): boolean {
  const cases: { name: string; ok: boolean }[] = [
    {
      name: 'CONTROL: a model outside the policy set IS reported',
      ok: offendingModels({ tr: 'kimi' }).length === 1,
    },
    {
      name: 'CONTROL: it names the language and the model, so the fix is obvious',
      ok:
        JSON.stringify(offendingModels({ tr: 'kimi' })[0]) ===
        JSON.stringify({ lang: 'tr', model: 'kimi' }),
    },
    {
      name: 'the documented default is NOT reported (control)',
      ok: offendingModels({ tr: 'claude-haiku-4-5' }).length === 0,
    },
    {
      name: 'a version bump within the family is NOT reported (control)',
      ok: offendingModels({ tr: 'claude-haiku-5' }).length === 0,
    },
    {
      name: 'sonnet and opus are permitted by policy (control)',
      ok: offendingModels({ a: 'claude-sonnet-5', b: 'claude-opus-5' }).length === 0,
    },
    {
      name: 'a mixed ledger reports ONLY the offender',
      ok:
        offendingModels({ tr: 'claude-haiku-4-5', ar: 'kimi' })
          .map((f) => f.lang)
          .join() === 'ar',
    },
    {
      name: 'an empty ledger reports nothing (control: no false positive on a fresh repo)',
      ok: offendingModels({}).length === 0,
    },
  ];
  let bad = 0;
  for (const c of cases) {
    console.log(`  ${c.ok ? 'PASS' : 'FAIL'}  ${c.name}`);
    if (!c.ok) bad++;
  }
  return bad === 0;
}

function main(): number {
  if (!selftest()) {
    console.error('\n✗ self-test failed: the detector cannot be trusted, so no verdict is given.');
    return 2;
  }

  if (!fs.existsSync(LEDGER)) {
    console.error(`✗ ledger not found at ${path.relative(ROOT, LEDGER)}`);
    console.error('  This gate reads the committed naturalization provenance; without it there');
    console.error('  is nothing to verify, which is a wiring failure rather than a pass.');
    return 1;
  }

  const meta = (JSON.parse(fs.readFileSync(LEDGER, 'utf-8')) as Record<string, unknown>).$meta as
    | { models?: Record<string, string> }
    | undefined;
  const models = meta?.models ?? {};
  const offenders = offendingModels(models);

  if (offenders.length > 0) {
    console.error(
      `\n✗ ${offenders.length} language(s) were naturalized with a model outside repo policy:\n`
    );
    for (const f of offenders) console.error(`    ${f.lang}: ${f.model}`);
    console.error(
      '\n  Policy (CLAUDE.md, "i18n / Translations"): haiku by default, sonnet or opus'
    );
    console.error('  only for a language whose haiku output reads awkward.');
    console.error('\n  If the pipeline default changed on purpose, update CLAUDE.md and');
    console.error('  POLICY_FAMILIES in this file in the SAME commit. If it changed by accident,');
    console.error('  the fix is in private/growth/i18n_pipeline/registry.py.');
    return 1;
  }

  const n = Object.keys(models).length;
  console.log(`\n✓ all ${n} recorded naturalization model(s) are within repo policy`);
  console.log('  controls: a non-policy model IS reported, and haiku/sonnet/opus are NOT,');
  console.log('  so this green distinguishes the two rather than passing unconditionally.');
  return 0;
}

process.exit(main());
