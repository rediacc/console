import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { resolveTofu, type TofuSource } from '../services/tofu/executor.js';
import { installTofu, listInstalledTofu, TOOL_NAMES } from '../services/tools/install.js';
import { OPENTOFU_PIN } from '../services/tools/pins.js';
import type { OutputFormat } from '../types/index.js';
import { handleError } from '../utils/errors.js';

const DEFAULT_OUTPUT_FORMAT = 'table';

interface ToolRow {
  tool: string;
  version: string;
  source: string;
  active: boolean;
  path: string;
}

/** The localized label of where an engine was found. */
export function toolSourceLabel(source: TofuSource): string {
  switch (source) {
    case 'env':
      return t('commands.tools.sources.env');
    case 'rdc':
      return t('commands.tools.sources.rdc');
    case 'path':
      return t('commands.tools.sources.path');
  }
}

/** Every tofu/terraform rdc can see: the engine it would run, plus other rdc-managed versions. */
async function collectToolRows(): Promise<ToolRow[]> {
  const rows: ToolRow[] = [];
  const resolved = await resolveTofu();
  // An engine below its floor is still listed (inactive), so the user sees what rdc refused.
  const engine = 'engine' in resolved ? resolved.engine : null;
  if (engine) {
    rows.push({
      tool: engine.engine,
      version: engine.version,
      source: toolSourceLabel(engine.source),
      active: resolved.ok,
      path: engine.path,
    });
  }
  for (const installed of await listInstalledTofu()) {
    if (installed.path === engine?.path) continue;
    rows.push({
      tool: 'tofu',
      version: installed.version,
      source: toolSourceLabel('rdc'),
      active: false,
      path: installed.path,
    });
  }
  return rows;
}

export function registerToolsCommands(program: Command): void {
  const tools = program
    .command('tools')
    .summary(t('commands.tools.descriptionShort'))
    .description(t('commands.tools.description'));

  tools
    .command('install')
    .summary(t('commands.tools.install.descriptionShort'))
    .description(t('commands.tools.install.description'))
    .argument('<tool>', t('commands.tools.install.argTool'))
    .option('--force', t('commands.tools.install.optionForce'))
    .action(async (tool: string, options: { force?: boolean }) => {
      try {
        if (!(TOOL_NAMES as readonly string[]).includes(tool)) {
          throw new Error(
            t('commands.tools.errors.unknownTool', { tool, available: TOOL_NAMES.join(', ') })
          );
        }
        const result = await installTofu(
          { force: options.force },
          {
            onDownloadStart: ({ version, platform }) =>
              outputService.info(t('commands.tools.install.downloading', { version, platform })),
          }
        );
        const params = { version: result.version, path: result.path };
        if (result.alreadyInstalled) {
          outputService.info(t('commands.tools.install.alreadyInstalled', params));
        } else {
          outputService.success(t('commands.tools.install.installed', params));
        }
      } catch (error) {
        handleError(error);
      }
    });

  tools
    .command('list')
    .summary(t('commands.tools.list.descriptionShort'))
    .description(t('commands.tools.list.description'))
    .option('--output <format>', t('options.outputFormat'))
    .action(async (options: { output?: string }) => {
      try {
        const format = (options.output ??
          program.opts().output ??
          DEFAULT_OUTPUT_FORMAT) as OutputFormat;
        const rows = await collectToolRows();
        if (format !== 'table') {
          outputService.print({ pinned: { tofu: OPENTOFU_PIN.version }, tools: rows }, format);
          return;
        }
        if (rows.length === 0) {
          outputService.info(t('commands.tools.list.empty'));
          return;
        }
        outputService.print(rows, 'table');
      } catch (error) {
        handleError(error);
      }
    });
}
