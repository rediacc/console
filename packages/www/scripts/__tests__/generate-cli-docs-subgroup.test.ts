import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { generate } from '../generate-cli-docs.js';

const cliJsonPath = fileURLToPath(
  new URL('../../../cli/src/i18n/locales/en/cli.json', import.meta.url)
);

describe('generate-cli-docs: a sub-group with an action of its own', () => {
  const doc = generate('en', JSON.parse(fs.readFileSync(cliJsonPath, 'utf-8'))) as string;

  it.each([
    ['licence', 'rdc server licence <domain> [options]'],
    ['replicate', 'rdc repo replicate <ref> [options]'],
    ['retention', 'rdc backup retention [repo-ref]'],
  ])('%s keeps its usage line beside its sub-commands', (name, usage) => {
    expect(doc).toContain(`\`\`\`bash\n${usage}\n\`\`\``);
    expect(doc).toMatch(new RegExp(`### \\d+\\.\\d+ ${name}\\n`));
  });

  it('puts the option table of a sub-group with options under its usage line', () => {
    const at = doc.indexOf('rdc repo replicate <ref> [options]');
    expect(at).toBeGreaterThan(-1);
    const after = doc.slice(at, at + 400);
    expect(after).toContain('| {{t:cli.docs.tableHeaders.flag}}');
    expect(after).toMatch(/\| `--[a-z-]+/);
  });

  it('control: a sub-group with no arguments or options of its own gets no usage line', () => {
    expect(doc).not.toContain('```bash\nrdc server\n```');
    expect(doc).not.toContain('```bash\nrdc config\n```');
  });
});
