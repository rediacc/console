/**
 * Controls for the URL refusal in isEntryPoint (entry-point.ts).
 *
 * A module URL (`import.meta.url`) is never a path. Returning false would skip a gate's
 * main() and exit 0 having checked nothing, so the helper throws. The symlink and spaced-path
 * behaviour has its own controls in scripts/__tests__/entry-point.control.ts.
 *
 *   npx tsx scripts/lib/entry-point-selftest.ts
 */
import process from 'node:process';
import { type ControlCase, summarizeControls } from './controls.js';
import { isEntryPoint } from './entry-point.js';

function throwsOn(input: string): boolean {
  try {
    isEntryPoint(input);
    return false;
  } catch (error) {
    return error instanceof Error && error.message.includes('got a URL');
  }
}

export function entryPointCases(): ControlCase[] {
  return [
    { name: 'a file:// module URL throws', ok: throwsOn('file:///repo/scripts/gate.ts') },
    { name: 'a file:// URL with an encoded space throws', ok: throwsOn('file:///a%20b/gate.ts') },
    { name: 'an https:// URL throws', ok: throwsOn('https://example.com/gate.ts') },
    {
      name: 'a plain absolute path does not throw',
      ok: !throwsOn('/no/such/dir/gate.ts') && isEntryPoint('/no/such/dir/gate.ts') === false,
    },
    {
      name: 'a Windows-style drive path is not mistaken for a URL',
      ok: !throwsOn('C:\\repo\\gate.ts'),
    },
  ];
}

if (isEntryPoint(import.meta.filename)) process.exit(summarizeControls(entryPointCases()));
