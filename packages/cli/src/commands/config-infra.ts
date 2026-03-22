import { isValidEmail } from '@rediacc/shared/validation';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import type { InfraConfig, OutputFormat } from '../types/index.js';
import {
  InfraConfigSchema,
  normalizeDomain,
  normalizeEmail,
  normalizeIp,
  parseConfig,
} from '../utils/config-schema.js';
import { handleError, ValidationError } from '../utils/errors.js';

interface ParsedInfraOptions {
  infra: Partial<InfraConfig>;
  configLevel: { certEmail?: string; cfDnsApiToken?: string };
}

function parseInfraOptions(options: Record<string, string>): ParsedInfraOptions {
  const infra: Partial<InfraConfig> = {};
  const configLevel: { certEmail?: string; cfDnsApiToken?: string } = {};

  if (options.publicIpv4) infra.publicIPv4 = normalizeIp(options.publicIpv4);
  if (options.publicIpv6) infra.publicIPv6 = normalizeIp(options.publicIpv6);
  if (options.baseDomain) infra.baseDomain = normalizeDomain(options.baseDomain);
  if (options.certEmail) configLevel.certEmail = normalizeEmail(options.certEmail);
  if (options.cfDnsToken) configLevel.cfDnsApiToken = options.cfDnsToken.trim();
  if (options.tcpPorts) {
    infra.tcpPorts = options.tcpPorts
      .split(',')
      .map((p: string) => Number.parseInt(p.trim(), 10))
      .sort((a, b) => a - b);
  }
  if (options.udpPorts) {
    infra.udpPorts = options.udpPorts
      .split(',')
      .map((p: string) => Number.parseInt(p.trim(), 10))
      .sort((a, b) => a - b);
  }

  return { infra, configLevel };
}

export function registerInfraCommands(config: Command, program: Command): void {
  const infra = config.command('infra').description(t('commands.config.infra.description'));

  // config infra set <machine>
  infra
    .command('set <machine>')
    .summary(t('commands.config.infra.set.descriptionShort'))
    .description(t('commands.config.infra.set.description'))
    .option('--public-ipv4 <ip>', t('commands.config.infra.set.optionPublicIPv4'))
    .option('--public-ipv6 <ip>', t('commands.config.infra.set.optionPublicIPv6'))
    .option('--base-domain <domain>', t('commands.config.infra.set.optionBaseDomain'))
    .option('--cert-email <email>', t('commands.config.infra.set.optionCertEmail'))
    .option('--cf-dns-token <token>', t('commands.config.infra.set.optionCfDnsToken'))
    .option('--tcp-ports <ports>', t('commands.config.infra.set.optionTcpPorts'))
    .option('--udp-ports <ports>', t('commands.config.infra.set.optionUdpPorts'))
    .action(async (machineName, options) => {
      try {
        const { infra: infraOpts, configLevel } = parseInfraOptions(options);

        if (Object.keys(infraOpts).length === 0 && Object.keys(configLevel).length === 0) {
          outputService.warn(t('commands.config.infra.set.noOptions'));
          return;
        }

        if (Object.keys(infraOpts).length > 0) {
          parseConfig(InfraConfigSchema, infraOpts, 'infra config');
        }

        if (configLevel.certEmail && !isValidEmail(configLevel.certEmail)) {
          throw new ValidationError(
            t('errors.config.invalidEmail', { value: configLevel.certEmail })
          );
        }

        if (Object.keys(infraOpts).length > 0) {
          await configService.setMachineInfra(machineName, infraOpts);
        }

        if (Object.keys(configLevel).length > 0) {
          await configService.updateConfigFields(configLevel);
        }

        outputService.success(t('commands.config.infra.set.success', { name: machineName }));
      } catch (error) {
        handleError(error);
      }
    });

  // config infra show <machine>
  infra
    .command('show <machine>')
    .description(t('commands.config.infra.show.description'))
    .action(async (machineName) => {
      try {
        const machine = await configService.getLocalMachine(machineName);
        const localConfig = await configService.getLocalConfig();
        const format = program.opts().output as OutputFormat;

        if (!machine.infra) {
          outputService.info(t('commands.config.infra.show.noInfra', { name: machineName }));
          return;
        }

        const columns = [
          { key: 'machine', header: 'Machine' },
          { key: 'publicIPv4', header: 'Public IPv4' },
          { key: 'publicIPv6', header: 'Public IPv6' },
          { key: 'baseDomain', header: 'Base Domain' },
          { key: 'certEmail', header: 'Cert Email' },
          { key: 'cfDnsApiToken', header: 'CF DNS API Token' },
          { key: 'cfDnsZoneId', header: 'CF Zone ID' },
          { key: 'tcpPorts', header: 'TCP Ports' },
          { key: 'udpPorts', header: 'UDP Ports' },
        ];

        const display: Record<string, unknown> = {
          machine: machineName,
          publicIPv4: machine.infra.publicIPv4 ?? '-',
          publicIPv6: machine.infra.publicIPv6 ?? '-',
          baseDomain: machine.infra.baseDomain ?? '-',
          certEmail: localConfig.certEmail ?? '-',
          cfDnsApiToken: localConfig.cfDnsApiToken ? '***' : '-',
          cfDnsZoneId: localConfig.cfDnsZoneId ?? '-',
          tcpPorts: machine.infra.tcpPorts?.join(', ') ?? '-',
          udpPorts: machine.infra.udpPorts?.join(', ') ?? '-',
        };

        const output = outputService.format(display, format, columns);
        outputService.print(output);
      } catch (error) {
        handleError(error);
      }
    });

  // config infra push <machine>
  infra
    .command('push <machine>')
    .summary(t('commands.config.infra.push.descriptionShort'))
    .description(t('commands.config.infra.push.description'))
    .option('--debug', t('options.debug'))
    .action(async (machineName, options) => {
      try {
        const { pushInfraConfig } = await import('../services/infra-provision.js');
        await pushInfraConfig(machineName, { debug: options.debug });
        outputService.success(t('commands.config.infra.push.success', { name: machineName }));
      } catch (error) {
        handleError(error);
      }
    });

  // ============================================================================
  // cert-cache subcommands (already nested — keep as-is)
  // ============================================================================

  const certCache = config
    .command('cert-cache')
    .description(t('commands.config.certCache.description'));

  certCache
    .command('pull <machine>')
    .description(t('commands.config.certCache.pull.description'))
    .option('--no-prune', t('commands.config.certCache.pull.optionNoPrune'))
    .option('--debug', t('options.debug'))
    .action(async (machineName, options) => {
      try {
        const { downloadCertCache } = await import('../services/cert-cache.js');
        await downloadCertCache(machineName, {
          noPrune: options.prune === false,
          debug: options.debug,
        });
      } catch (error) {
        handleError(error);
      }
    });

  certCache
    .command('push <machine>')
    .description(t('commands.config.certCache.push.description'))
    .option('--debug', t('options.debug'))
    .action(async (machineName, options) => {
      try {
        const { uploadCertCache } = await import('../services/cert-cache.js');
        await uploadCertCache(machineName, {
          debug: options.debug,
        });
      } catch (error) {
        handleError(error);
      }
    });

  certCache
    .command('status')
    .description(t('commands.config.certCache.status.description'))
    .action(async () => {
      try {
        const { getCertStatus } = await import('../services/cert-cache.js');
        const entries = await getCertStatus();
        const format = program.opts().output as OutputFormat;

        if (entries.length === 0) {
          outputService.info(t('commands.config.certCache.status.noCache'));
          return;
        }

        for (const entry of entries) {
          outputService.info(
            t('commands.config.certCache.status.header', { baseDomain: entry.baseDomain })
          );
          outputService.info(
            t('commands.config.certCache.status.updatedAt', {
              date: new Date(entry.updatedAt).toLocaleString(),
              machine: entry.sourceMachine,
            })
          );
          outputService.info(
            t('commands.config.certCache.status.certCount', {
              count: entry.certCount,
              size: entry.compressedSize,
            })
          );
          outputService.info('');

          const certData = Object.entries(entry.certs)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([domain, expiry]) => ({
              domain,
              expires: new Date(expiry).toLocaleDateString(),
            }));

          const columns = [
            { key: 'domain', header: 'Domain' },
            { key: 'expires', header: 'Expires' },
          ];

          const output = outputService.format(certData, format, columns);
          outputService.print(output);
        }
      } catch (error) {
        handleError(error);
      }
    });

  certCache
    .command('clear')
    .description(t('commands.config.certCache.clear.description'))
    .action(async () => {
      try {
        const { clearCertCache } = await import('../services/cert-cache.js');
        const cleared = await clearCertCache();
        if (cleared) {
          outputService.success(t('commands.config.certCache.clear.cleared'));
        } else {
          outputService.info(t('commands.config.certCache.clear.noCache'));
        }
      } catch (error) {
        handleError(error);
      }
    });
}
