import { Command } from 'commander';
import { parseGetAuditLogs, parseGetEntityAuditTrace } from '@rediacc/shared/api';
import { t } from '../i18n/index.js';
import { typedApi } from '../services/api.js';
import { authService } from '../services/auth.js';
import { outputService } from '../services/output.js';
import { handleError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import type { OutputFormat } from '../types/index.js';

export function registerAuditCommands(program: Command): void {
  const audit = program.command('audit').description(t('commands.audit.description'));

  // audit log
  audit
    .command('log')
    .description(t('commands.audit.log.description'))
    .option('--limit <n>', t('options.limit'), '100')
    .action(async (options: { limit: string }) => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          t('commands.audit.log.fetching'),
          () =>
            typedApi.GetAuditLogs({
              maxRecords: parseInt(options.limit, 10),
            }),
          t('commands.audit.log.success')
        );

        const logs = parseGetAuditLogs(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        outputService.print(logs, format);
      } catch (error) {
        handleError(error);
      }
    });

  // audit trace
  audit
    .command('trace <entityType> <entityId>')
    .description(t('commands.audit.trace.description'))
    .action(async (entityType: string, entityId: string) => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          t('commands.audit.trace.fetching'),
          () => typedApi.GetEntityAuditTrace({ entityType, entityIdentifier: entityId }),
          t('commands.audit.trace.success')
        );

        const trace = parseGetEntityAuditTrace(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        outputService.print(trace.records, format);
      } catch (error) {
        handleError(error);
      }
    });

  // audit history
  audit
    .command('history <entityType> <entityId>')
    .description(t('commands.audit.history.description'))
    .action(async (entityType: string, entityId: string) => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          t('commands.audit.history.fetching'),
          () => typedApi.GetEntityAuditTrace({ entityType, entityIdentifier: entityId }),
          t('commands.audit.history.success')
        );

        const trace = parseGetEntityAuditTrace(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        outputService.print(trace.records, format);
      } catch (error) {
        handleError(error);
      }
    });
}
