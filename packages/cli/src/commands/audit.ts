import { Command } from 'commander';
import { authService } from '../services/auth.js';
import { api } from '../services/api.js';
import { outputService } from '../services/output.js';
import { withSpinner } from '../utils/spinner.js';
import { handleError } from '../utils/errors.js';
import type { OutputFormat } from '../types/index.js';
export function registerAuditCommands(program: Command): void {
  const audit = program.command('audit').description('Audit log commands');

  // audit log
  audit
    .command('log')
    .description('View audit logs')
    .option('--limit <n>', 'Limit results', '100')
    .option('--offset <n>', 'Offset results', '0')
    .action(async (options) => {
      try {
        await authService.requireAuth();

        const logs = await withSpinner(
          'Fetching audit logs...',
          () =>
            api.audit.getLogs(undefined, undefined, undefined, parseInt(options.limit, 10), {
              offset: parseInt(options.offset, 10),
            }),
          'Audit logs fetched'
        );

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
    .action(async (entityType, entityId) => {
      try {
        await authService.requireAuth();

        const trace = await withSpinner(
          'Fetching entity audit trace...',
          () => api.audit.getEntityTrace(entityType, entityId),
          'Audit trace fetched'
        );

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
    .action(async (entityType, entityId) => {
      try {
        await authService.requireAuth();

        const history = await withSpinner(
          'Fetching entity history...',
          () => api.audit.getEntityHistory(entityType, entityId),
          'History fetched'
        );

        const format = program.opts().output as OutputFormat;

        outputService.print(history, format);
      } catch (error) {
        handleError(error);
      }
    });
}
