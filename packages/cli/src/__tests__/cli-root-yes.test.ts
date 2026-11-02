import { describe, expect, it } from 'vitest';
import { createCli } from '../cli.js';

// Commander hands -y to the root option wherever it appears, so a subcommand that declares its own
// -y/--yes never saw it: `rdc repo prune <ref> --apply --offline -y` was refused as unconfirmed.
describe('root -y reaches the subcommand that declares it', () => {
  it.each([['-y'], ['--yes']])('%s sets the subcommand option', async (flag) => {
    const cli = createCli();
    let seen: unknown;
    cli
      .command('yes-probe')
      .option('-y, --yes', 'confirm')
      .action((opts: { yes?: boolean }) => {
        seen = opts.yes;
      });
    await cli.parseAsync(['node', 'rdc', 'yes-probe', flag]);
    expect(seen).toBe(true);
  });
});
