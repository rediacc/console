/**
 * Controls for the drafted `Ran:` line (ran-line.ts).
 *
 *   npx tsx scripts/lib/pins/ran-line-selftest.ts
 */
import process from 'node:process';
import { type ControlCase, summarizeControls } from '../controls.js';
import { isEntryPoint } from '../entry-point.js';
import { ranLine } from './ran-line.js';

const ROOT = '/repo';
const payload = Buffer.from(
  JSON.stringify([
    { cwd: '/repo/packages/cli', args: ['update', '-w=packages/cli', 'x'.repeat(300)] },
  ])
).toString('base64');
const node = 'node --require /r/preflight.cjs --import file:///r/loader.mjs';

export function ranLineCases(): ControlCase[] {
  const step = (verb: string) =>
    ranLine(
      {
        cmd: `${node} ${ROOT}/scripts/lib/pins/drivers/npm-steps.ts ${verb} ${payload}`,
        cwd: '.',
        rc: 0,
      },
      ROOT
    );
  const guard = step('guard');
  const sync = step('sync');
  const plain = ranLine({ cmd: 'npx -y npm@11.21.0 ci', cwd: '.', rc: 0 }, ROOT);
  const junk = ranLine(
    { cmd: `${node} /x/npm-steps.ts guard !!notbase64!!notbase64!!`, cwd: '.', rc: 1 },
    ROOT
  );
  return [
    {
      name: 'a guard step is labelled and its base64 argument is absent',
      ok:
        guard === 'Ran: npm-steps guard (packages/cli) (in .) rc=0' &&
        !guard.includes(payload.slice(0, 20)),
      detail: guard,
    },
    {
      name: 'a sync step is labelled and its base64 argument is absent',
      ok:
        sync === 'Ran: npm-steps sync (packages/cli) (in .) rc=0' &&
        !sync.includes(payload.slice(0, 20)),
      detail: sync,
    },
    {
      name: 'a normal command is kept verbatim',
      ok: plain === 'Ran: npx -y npm@11.21.0 ci (in .) rc=0',
      detail: plain,
    },
    { name: 'a step line stays short', ok: guard.length < 100, detail: String(guard.length) },
    {
      name: 'an undecodable payload is left alone rather than mislabelled',
      ok: junk.includes('!!notbase64'),
      detail: junk,
    },
  ];
}

if (isEntryPoint(import.meta.filename)) {
  process.exit(summarizeControls(ranLineCases()));
}
