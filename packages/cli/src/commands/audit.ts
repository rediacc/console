import { Command } from 'commander';
import { parseGetAuditLogs, parseGetEntityAuditTrace } from '@rediacc/shared/api';
import { typedApi } from '../services/api.js';
import { authService } from '../services/auth.js';
import { outputService } from '../services/output.js';
import { handleError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import type { OutputFormat } from '../types/index.js';

export function registerAuditCommands(program: Command): void {
  const audit = program.command('audit').description('Audit log commands');

  // audit log
  audit
    .command('log')
    .description('View audit logs')
    .option('--limit <n>', 'Limit results', '100')
    .action(async (options: { limit: string }) => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          'Fetching audit logs...',
          () =>
            typedApi.GetAuditLogs({
              maxRecords: parseInt(options.limit, 10),
            }),
          'Audit logs fetched'
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
    .description('Trace audit history for an entity')
    .action(async (entityType: string, entityId: string) => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          'Fetching entity audit trace...',
          () => typedApi.GetEntityAuditTrace({ entityType, entityIdentifier: entityId }),
          'Audit trace fetched'
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
    .description('View entity history')
    .action(async (entityType: string, entityId: string) => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          'Fetching entity history...',
          () => typedApi.GetEntityAuditTrace({ entityType, entityIdentifier: entityId }),
          'History fetched'
        );

        const trace = parseGetEntityAuditTrace(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        outputService.print(trace, format);
      } catch (error) {
        handleError(error);
      }
    });
}
