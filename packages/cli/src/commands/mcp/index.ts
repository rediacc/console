import { DEFAULTS } from '@rediacc/shared/config';
import { Command } from 'commander';
import { t } from '../../i18n/index.js';

const MCP_TIMEOUT_DEFAULT = String(DEFAULTS.TIMEOUT.MCP_COMMAND);

export function registerMcpCommands(program: Command): void {
  const mcp = program
    .command('mcp')
    .summary(t('commands.mcp.descriptionShort'))
    .description(t('commands.mcp.description'));

  mcp
    .command('serve')
    .description(t('commands.mcp.serve.description'))
    .option('--config <name>', t('commands.mcp.serve.configOption'))
    .option('--timeout <ms>', t('commands.mcp.serve.timeoutOption'), MCP_TIMEOUT_DEFAULT)
    .option('--allow-grand', t('commands.mcp.serve.allowGrandOption'))
    .action(async (options: { config?: string; timeout?: string; allowGrand?: boolean }) => {
      const { startMcpServer } = await import('./server.js');
      await startMcpServer({
        configName: options.config,
        defaultTimeoutMs: Number.parseInt(options.timeout ?? MCP_TIMEOUT_DEFAULT, 10),
        allowGrand: options.allowGrand,
        program,
      });
    });
}
