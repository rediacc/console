import { isIP } from 'node:net';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import { handleError } from '../utils/errors.js';
import type { InfraConfig, OutputFormat } from '../types/index.js';
import type { Command } from 'commander';

function validateIpAddresses(infra: Partial<InfraConfig>): string | undefined {
  if (infra.publicIPv4 && isIP(infra.publicIPv4) !== 4) {
    return t('commands.config.setInfra.invalidIPv4', { ip: infra.publicIPv4 });
  }
  if (infra.publicIPv6 && isIP(infra.publicIPv6) !== 6) {
    return t('commands.config.setInfra.invalidIPv6', { ip: infra.publicIPv6 });
  }
  return undefined;
}

function parseInfraOptions(options: Record<string, string>): Partial<InfraConfig> {
  const infra: Partial<InfraConfig> = {};

  if (options.publicIpv4) infra.publicIPv4 = options.publicIpv4;
  if (options.publicIpv6) infra.publicIPv6 = options.publicIpv6;
  if (options.baseDomain) infra.baseDomain = options.baseDomain;
  if (options.certEmail) infra.certEmail = options.certEmail;
  if (options.cfDnsToken) infra.cfDnsApiToken = options.cfDnsToken;
  if (options.tcpPorts) {
    infra.tcpPorts = options.tcpPorts.split(',').map((p: string) => Number.parseInt(p.trim(), 10));
  }
  if (options.udpPorts) {
    infra.udpPorts = options.udpPorts.split(',').map((p: string) => Number.parseInt(p.trim(), 10));
  }

  return infra;
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
        const infra = parseInfraOptions(options);

        if (Object.keys(infra).length === 0) {
          outputService.warn(t('commands.config.setInfra.noOptions'));
          return;
        }

        const ipError = validateIpAddresses(infra);
        if (ipError) {
          outputService.error(ipError);
          return;
        }

        await configService.setMachineInfra(machineName, infra);
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
          { key: 'tcpPorts', header: 'TCP Ports' },
          { key: 'udpPorts', header: 'UDP Ports' },
        ];

        const display: Record<string, unknown> = {
          machine: machineName,
          publicIPv4: machine.infra.publicIPv4 ?? '-',
          publicIPv6: machine.infra.publicIPv6 ?? '-',
          baseDomain: machine.infra.baseDomain ?? '-',
          certEmail: machine.infra.certEmail ?? '-',
          cfDnsApiToken: machine.infra.cfDnsApiToken ? '***' : '-',
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
}
