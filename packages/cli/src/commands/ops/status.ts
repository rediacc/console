import { Command, Option } from 'commander';
import { t } from '../../i18n/index.js';
import { outputService } from '../../services/core/output.js';
import type { OpsBackend } from '../../services/executor/ops-executor.js';
import { opsExecutorService } from '../../services/executor/ops-executor.js';
import type { OutputFormat } from '../../types/index.js';
import { handleError } from '../../utils/errors.js';

interface VMInfo {
  id: number;
  name: string;
  ip: string;
  status: string;
}

interface OpsStatusResponse {
  vms: VMInfo[];
}

export function registerOpsStatusCommand(ops: Command, program: Command): void {
  ops
    .command('status')
    .description(t('commands.ops.status.description'))
    .addOption(new Option('--backend <backend>', t('options.opsBackend')).choices(['kvm', 'qemu']))
    .action(async (options: { backend?: string }) => {
      try {
        const backend = options.backend ? (options.backend as OpsBackend) : undefined;
        const response = await opsExecutorService.runOpsJSON<OpsStatusResponse>('status', [], {
          backend,
        });

        const format = program.opts().output as OutputFormat;

        if (response.vms.length === 0) {
          outputService.info(t('commands.ops.status.noVMs'));
          if (format === 'json') {
            outputService.print({ vms: [] }, format);
          }
          return;
        }

        if (format === 'json') {
          outputService.print(response, format);
        } else {
          outputService.print(response.vms, format);
        }
      } catch (error) {
        handleError(error);
      }
    });
}
