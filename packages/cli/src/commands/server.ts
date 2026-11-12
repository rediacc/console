/**
 * `rdc server install|status|upgrade|backup|licence`: the self-hosted Rediacc account server
 * (Elite) as a repo on one machine. The engine lives in services/server; this file only parses.
 *
 * Not to be confused with `rdc serve` (commands/serve.ts), which runs this process as an executor.
 */

import { Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { isMachineReadable } from '../services/core/output-format.js';
import { setExitCode } from '../services/core/request-context.js';
import { liveServerDeps } from '../services/server/deps.js';
import { type InstallOptions, ServerInstall } from '../services/server/install.js';
import { LICENCE_MODES, TLS_METHODS } from '../services/server/types.js';
import {
  serverBackup,
  serverLicence,
  serverStatus,
  serverUpgrade,
} from '../services/server/verbs.js';
import { handleError } from '../utils/errors.js';
import { inquirerPrompts } from '../utils/server-prompts.js';

interface InstallFlags extends Omit<InstallOptions, 'machine' | 'machineReadable'> {
  dnsWait?: boolean;
}

interface LocatorFlags {
  machine?: string;
  repo?: string;
}

function registerInstall(server: Command): void {
  server
    .command('install')
    .summary(t('commands.server.install.summary'))
    .description(t('commands.server.install.description'))
    .argument('[machine]', t('commands.server.install.machineArgument'))
    .option('--ip <address>', t('commands.server.install.optionIp'))
    .option('--user <name>', t('commands.server.install.optionUser'))
    .option('--port <port>', t('commands.server.install.optionPort'))
    .option('--name <name>', t('commands.server.install.optionName'))
    .option('--domain <host>', t('commands.server.install.optionDomain'))
    .option('--store-domain <host>', t('commands.server.install.optionStoreDomain'))
    .option('--repo <name>', t('commands.server.install.optionRepo'))
    .option('--size <size>', t('commands.server.install.optionSize'))
    .option('--owner <email>', t('commands.server.install.optionOwner'))
    .addOption(
      new Option('--tls <method>', t('commands.server.install.optionTls')).choices([...TLS_METHODS])
    )
    .option('--cf-token <token>', t('commands.server.install.optionCfToken'))
    .option('--cert-email <email>', t('commands.server.install.optionCertEmail'))
    .option('--tls-cert <file>', t('commands.server.install.optionTlsCert'))
    .option('--tls-key <file>', t('commands.server.install.optionTlsKey'))
    .option('--tls-ca <file>', t('commands.server.install.optionTlsCa'))
    .addOption(
      new Option('--licence <mode>', t('commands.server.install.optionLicence')).choices([
        ...LICENCE_MODES,
      ])
    )
    .option('--cert <file>', t('commands.server.install.optionCert'))
    .option('--image <ref>', t('commands.server.install.optionImage'))
    .option('--image-file <tar>', t('commands.server.install.optionImageFile'))
    .option('--local-image', t('commands.server.install.optionLocalImage'))
    .option('--no-dns-wait', t('commands.server.install.optionNoDnsWait'))
    .option('--bws-project <id>', t('commands.server.install.optionBwsProject'))
    .option('--rotate', t('commands.server.install.optionRotate'))
    .option('-y, --yes', t('commands.server.install.optionYes'))
    .addHelpText('after', `\n${t('commands.server.install.help')}\n`)
    .action(async (machine: string | undefined, flags: InstallFlags) => {
      try {
        const machineReadable = isMachineReadable();
        const install = new ServerInstall(
          { ...flags, ...(machine ? { machine } : {}), machineReadable },
          liveServerDeps(),
          inquirerPrompts()
        );
        const result = await install.run();
        if (machineReadable) outputService.print(result, 'json');
      } catch (error) {
        handleError(error);
      }
    });
}

function locatorOptions(command: Command): Command {
  return command
    .option('-m, --machine <name>', t('commands.server.optionMachine'))
    .option('--repo <name>', t('commands.server.optionRepo'));
}

function registerStatus(server: Command): void {
  locatorOptions(
    server
      .command('status')
      .description(t('commands.server.status.description'))
      .argument('<domain>', t('commands.server.domainArgument'))
  ).action(async (domain: string, flags: LocatorFlags) => {
    try {
      const result = await serverStatus(liveServerDeps(), { domain, ...flags });
      if (isMachineReadable()) {
        outputService.print(result, 'json');
      } else {
        for (const [key, value] of Object.entries(result)) {
          outputService.report(`${key.padEnd(24)} ${String(value)}`);
        }
      }
      if (result.health !== 200) setExitCode(1);
    } catch (error) {
      handleError(error);
    }
  });
}

function registerBackup(server: Command): void {
  locatorOptions(
    server
      .command('backup')
      .description(t('commands.server.backup.description'))
      .argument('<domain>', t('commands.server.domainArgument'))
      .option('--out <file>', t('commands.server.backup.optionOut'))
  ).action(async (domain: string, flags: LocatorFlags & { out?: string }) => {
    try {
      await serverBackup(liveServerDeps(), { domain, ...flags }, flags.out);
    } catch (error) {
      handleError(error);
    }
  });
}

function registerUpgrade(server: Command): void {
  locatorOptions(
    server
      .command('upgrade')
      .description(t('commands.server.upgrade.description'))
      .argument('<domain>', t('commands.server.domainArgument'))
      .option('--image <ref>', t('commands.server.install.optionImage'))
      .option('--image-file <tar>', t('commands.server.install.optionImageFile'))
      .option('--local-image', t('commands.server.install.optionLocalImage'))
      .option('-y, --yes', t('commands.server.install.optionYes'))
  ).action(
    async (
      domain: string,
      flags: LocatorFlags & {
        image?: string;
        imageFile?: string;
        localImage?: boolean;
        yes?: boolean;
      }
    ) => {
      try {
        // askConfirm refuses a stdin that is no terminal with an error naming --yes (REDIACC_YES=1 confirms), so a non-interactive run never restarts the server unprompted.
        if (!flags.yes) {
          const { askConfirm } = await import('../utils/prompt.js');
          if (!(await askConfirm(t('commands.server.upgrade.confirm', { domain })))) {
            outputService.info(t('status.cancelled'));
            return;
          }
        }
        const result = await serverUpgrade(liveServerDeps(), { domain, ...flags }, flags);
        if (isMachineReadable()) {
          outputService.print(result, 'json');
        } else {
          outputService.success(
            t('commands.server.upgrade.done', { domain, rollback: result.rollback })
          );
        }
      } catch (error) {
        handleError(error);
      }
    }
  );
}

function registerLicence(server: Command): void {
  locatorOptions(
    server
      .command('licence')
      .description(t('commands.server.licence.description'))
      .argument('<domain>', t('commands.server.domainArgument'))
      .option('--cert <file>', t('commands.server.install.optionCert'))
  ).action(async (domain: string, flags: LocatorFlags & { cert?: string }) => {
    try {
      const result = await serverLicence(liveServerDeps(), { domain, ...flags }, flags.cert);
      if (isMachineReadable()) {
        outputService.print(result, 'json');
      } else {
        outputService.success(
          t('commands.server.licence.done', { domain, subscription: result.subscriptionId })
        );
      }
    } catch (error) {
      handleError(error);
    }
  });
}

export function registerServerCommands(program: Command): void {
  const server = new Command('server')
    .summary(t('commands.server.summary'))
    .description(t('commands.server.description'));
  registerInstall(server);
  registerStatus(server);
  registerUpgrade(server);
  registerBackup(server);
  registerLicence(server);
  program.addCommand(server);
}
