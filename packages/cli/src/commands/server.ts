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
import { serverBundle } from '../services/server/bundle/build.js';
import { licenceMint } from '../services/server/bundle/offline.js';
import { liveServerDeps } from '../services/server/deps.js';
import { ServerInstall } from '../services/server/install.js';
import type { InstallOptions } from '../services/server/install-options.js';
import {
  BUNDLE_ARCHES,
  type BundleArch,
  DEFAULT_BUNDLE_ARCH,
  LICENCE_MODES,
  TLS_METHODS,
} from '../services/server/types.js';
import {
  type StatusResult,
  serverBackup,
  serverLicence,
  serverStatus,
  serverUpgrade,
} from '../services/server/verbs.js';
import { handleError } from '../utils/errors.js';
import { inquirerPrompts } from '../utils/server-prompts.js';

const CERT_WARN_DAYS = 30;

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
    .option('--offline', t('commands.server.install.optionOffline'))
    .option('--bundle <dir>', t('commands.server.install.optionBundle'))
    .option('--bws-project <id>', t('commands.server.install.optionBwsProject'))
    .option('--rotate', t('commands.server.install.optionRotate'))
    .option('-y, --yes', t('commands.server.install.optionYes'))
    .addHelpText('after', `\n${t('commands.server.install.help')}\n`)
    .addHelpText('after', `\n${t('commands.server.install.helpOffline')}\n`)
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

/** The marker's `at` as `YYYY-MM-DD HH:MMZ` in UTC, whatever offset it carries; `?` when it is absent, and the raw text when it is not a date. */
function refusedAt(raw: string): string {
  const date = new Date(raw);
  if (!raw || Number.isNaN(date.getTime())) return raw || '?';
  return `${date.toISOString().slice(0, 16).replace('T', ' ')}Z`;
}

/** Within 30 days of the cert's end the box is told to renew; past it the server only serves what it already runs. */
function warnCertExpiry(days: number | undefined): void {
  if (days === undefined || Number.isNaN(days) || days > CERT_WARN_DAYS) return;
  outputService.warn(
    days < 0
      ? t('commands.server.status.certExpired')
      : t('commands.server.status.certExpiring', { days })
  );
}

/** The status lines; a refused cert prints as one `cert` line plus the command that fixes it. */
function reportStatus(result: StatusResult, domain: string): void {
  for (const [key, value] of Object.entries(result)) {
    if (key !== 'certRefused') outputService.report(`${key.padEnd(24)} ${String(value)}`);
  }
  warnCertExpiry(result.certExpiresInDays);
  if (!result.certRefused) return;
  const { reason } = result.certRefused;
  const at = refusedAt(result.certRefused.at);
  outputService.report(
    `${'cert'.padEnd(24)} ${t('commands.server.status.certRefused', { reason, at })}`
  );
  outputService.report(
    `${''.padEnd(24)} ${t('commands.server.status.certRefusedRun', { domain })}`
  );
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
        reportStatus(result, domain);
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
      .summary(t('commands.server.upgrade.descriptionShort'))
      .description(t('commands.server.upgrade.description'))
      .argument('<domain>', t('commands.server.domainArgument'))
      .option('--image <ref>', t('commands.server.install.optionImage'))
      .option('--image-file <tar>', t('commands.server.install.optionImageFile'))
      .option('--local-image', t('commands.server.install.optionLocalImage'))
      .option('--bundle <dir>', t('commands.server.upgrade.optionBundle'))
      .option('--force', t('commands.server.upgrade.optionForce'))
      .option('-y, --yes', t('commands.server.install.optionYes'))
  ).action(
    async (
      domain: string,
      flags: LocatorFlags & {
        image?: string;
        imageFile?: string;
        localImage?: boolean;
        bundle?: string;
        force?: boolean;
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
  // `rdc server licence <domain>` applies a cert; `mint` is the one word that is a subcommand instead.
  const licence = locatorOptions(
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
      } else if (result.via === 'inbox') {
        outputService.success(
          t('commands.server.licence.done', { domain, subscription: result.subscriptionId })
        );
      }
    } catch (error) {
      handleError(error);
    }
  });
  licence
    .command('mint')
    .description(t('commands.server.licence.mint.description'))
    .requiredOption('--request <file>', t('commands.server.licence.mint.optionRequest'))
    .requiredOption('--out <file>', t('commands.server.licence.mint.optionOut'))
    .action(async (flags: { request: string; out: string }) => {
      try {
        const result = await licenceMint(liveServerDeps(), flags.request, flags.out);
        if (isMachineReadable()) {
          outputService.print({ out: flags.out, ...result }, 'json');
        } else {
          outputService.success(
            t('commands.server.licence.mint.done', { file: flags.out, until: result.validUntil })
          );
        }
      } catch (error) {
        handleError(error);
      }
    });
}

function registerBundle(server: Command): void {
  server
    .command('bundle')
    .summary(t('commands.server.bundle.summary'))
    .description(t('commands.server.bundle.description'))
    .requiredOption('--out <dir>', t('commands.server.bundle.optionOut'))
    .addOption(
      new Option('--arch <arch>', t('commands.server.bundle.optionArch'))
        .choices([...BUNDLE_ARCHES])
        .default(DEFAULT_BUNDLE_ARCH)
    )
    .option('--tag <tag>', t('commands.server.bundle.optionTag'))
    .option('--image <ref>', t('commands.server.bundle.optionImage'))
    .option('--with-cli <platforms>', t('commands.server.bundle.optionWithCli'))
    .action(
      async (flags: {
        out: string;
        arch: BundleArch;
        tag?: string;
        image?: string;
        withCli?: string;
      }) => {
        try {
          const manifest = await serverBundle(liveServerDeps(), flags);
          if (isMachineReadable()) outputService.print(manifest, 'json');
        } catch (error) {
          handleError(error);
        }
      }
    );
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
  registerBundle(server);
  program.addCommand(server);
}
