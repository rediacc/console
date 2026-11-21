import { afterEach, describe, expect, it } from 'vitest';
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

// `feedback report` declares no --yes of its own; the agent hint and the send path rely on the root option.
describe('root --yes is accepted by `feedback report`', () => {
  const saved = process.env.REDIACC_YES;
  afterEach(() => {
    if (saved === undefined) delete process.env.REDIACC_YES;
    else process.env.REDIACC_YES = saved;
  });

  const probe = () => {
    const cli = createCli();
    cli.exitOverride();
    cli.configureOutput({ writeErr: () => undefined, writeOut: () => undefined });
    const report = cli.commands
      .find((c) => c.name() === 'feedback')
      ?.commands.find((c) => c.name() === 'report');
    expect(report).toBeDefined();
    report?.exitOverride();
    report?.configureOutput({ writeErr: () => undefined, writeOut: () => undefined });
    let seen: string | undefined;
    report?.action(() => {
      seen = process.env.REDIACC_YES;
    });
    return { cli, seen: () => seen };
  };

  it('parses --yes after the subcommand and sets REDIACC_YES', async () => {
    delete process.env.REDIACC_YES;
    const { cli, seen } = probe();
    await cli.parseAsync(['node', 'rdc', 'feedback', 'report', '--last', '--yes']);
    expect(seen()).toBe('1');
  });

  it('control: an option no command declares is still refused', async () => {
    const { cli } = probe();
    await expect(
      cli.parseAsync(['node', 'rdc', 'feedback', 'report', '--last', '--no-such-flag'])
    ).rejects.toThrow();
  });
});
