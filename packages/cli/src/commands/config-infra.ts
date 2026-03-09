import { isIP } from 'node:net';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import type { InfraConfig, OutputFormat } from '../types/index.js';
import { handleError } from '../utils/errors.js';

function validateIpAddresses(infra: Partial<InfraConfig>): string | undefined {
  if (infra.publicIPv4 && isIP(infra.publicIPv4) !== 4) {
    return t('commands.config.setInfra.invalidIPv4', { ip: infra.publicIPv4 });
  }
  if (infra.publicIPv6 && isIP(infra.publicIPv6) !== 6) {
    return t('commands.config.setInfra.invalidIPv6', { ip: infra.publicIPv6 });
  }
  return undefined;
}

interface ParsedInfraOptions {
  infra: Partial<InfraConfig>;
  configLevel: { certEmail?: string; cfDnsApiToken?: string };
}

function parseInfraOptions(options: Record<string, string>): ParsedInfraOptions {
  const infra: Partial<InfraConfig> = {};
  const configLevel: { certEmail?: string; cfDnsApiToken?: string } = {};

  if (options.publicIpv4) infra.publicIPv4 = options.publicIpv4;
  if (options.publicIpv6) infra.publicIPv6 = options.publicIpv6;
  if (options.baseDomain) infra.baseDomain = options.baseDomain;
  if (options.certEmail) configLevel.certEmail = options.certEmail;
  if (options.cfDnsToken) configLevel.cfDnsApiToken = options.cfDnsToken;
  if (options.tcpPorts) {
    infra.tcpPorts = options.tcpPorts.split(',').map((p: string) => Number.parseInt(p.trim(), 10));
  }
  if (options.udpPorts) {
    infra.udpPorts = options.udpPorts.split(',').map((p: string) => Number.parseInt(p.trim(), 10));
  }

  return { infra, configLevel };
}

export function registerInfraCommands(config: Command, program: Command): void {
  // config set-infra <machine>
  config
    .command('set-infra <machine>')
    .description(t('commands.config.setInfra.description'))
    .option('--public-ipv4 <ip>', t('commands.config.setInfra.optionPublicIPv4'))
    .option('--public-ipv6 <ip>', t('commands.config.setInfra.optionPublicIPv6'))
    .option('--base-domain <domain>', t('commands.config.setInfra.optionBaseDomain'))
    .option('--cert-email <email>', t('commands.config.setInfra.optionCertEmail'))
    .option('--cf-dns-token <token>', t('commands.config.setInfra.optionCfDnsToken'))
    .option('--tcp-ports <ports>', t('commands.config.setInfra.optionTcpPorts'))
    .option('--udp-ports <ports>', t('commands.config.setInfra.optionUdpPorts'))
    .action(async (machineName, options) => {
      try {
        const { infra, configLevel } = parseInfraOptions(options);

        if (Object.keys(infra).length === 0 && Object.keys(configLevel).length === 0) {
          outputService.warn(t('commands.config.setInfra.noOptions'));
          return;
        }

        const ipError = validateIpAddresses(infra);
        if (ipError) {
          outputService.error(ipError);
          return;
        }

        // Set machine-level infra (IPs, domain, ports)
        if (Object.keys(infra).length > 0) {
          await configService.setMachineInfra(machineName, infra);
        }

        // Set config-level shared fields (certEmail, cfDnsApiToken)
        if (Object.keys(configLevel).length > 0) {
          await configService.updateConfigFields(configLevel);
        }

        outputService.success(t('commands.config.setInfra.success', { name: machineName }));
      } catch (error) {
        handleError(error);
      }
    });

  // config show-infra <machine>
  config
    .command('show-infra <machine>')
    .description(t('commands.config.showInfra.description'))
    .action(async (machineName) => {
      try {
        const machine = await configService.getLocalMachine(machineName);
        const localConfig = await configService.getLocalConfig();
        const format = program.opts().output as OutputFormat;

        if (!machine.infra) {
          outputService.info(t('commands.config.showInfra.noInfra', { name: machineName }));
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

  // config push-infra <machine>
  config
    .command('push-infra <machine>')
    .description(t('commands.config.pushInfra.description'))
    .option('--debug', t('options.debug'))
    .action(async (machineName, options) => {
      try {
        const { pushInfraConfig } = await import('../services/infra-provision.js');
        await pushInfraConfig(machineName, { debug: options.debug });
        outputService.success(t('commands.config.pushInfra.success', { name: machineName }));
      } catch (error) {
        handleError(error);
      }
    });

  // ============================================================================
  // cert-cache subcommands
  // ============================================================================

  const certCache = config
    .command('cert-cache')
    .description(t('commands.config.certCache.description'));

  // config cert-cache pull <machine>
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

  // config cert-cache push <machine>
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

  // config cert-cache status
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

          // Show cert inventory
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

  // config cert-cache clear
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
