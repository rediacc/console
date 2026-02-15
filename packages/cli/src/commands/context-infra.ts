import { isIP } from 'node:net';
import { t } from '../i18n/index.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { handleError } from '../utils/errors.js';
import type { InfraConfig, OutputFormat } from '../types/index.js';
import type { Command } from 'commander';

/** Validate IPv4/IPv6 addresses. Returns an error message string if invalid, or undefined if valid. */
function validateIpAddresses(infra: Partial<InfraConfig>): string | undefined {
  if (infra.publicIPv4 && isIP(infra.publicIPv4) !== 4) {
    return t('commands.context.setInfra.invalidIPv4', { ip: infra.publicIPv4 });
  }
  if (infra.publicIPv6 && isIP(infra.publicIPv6) !== 6) {
    return t('commands.context.setInfra.invalidIPv6', { ip: infra.publicIPv6 });
  }
  return undefined;
}

/** Parse CLI options into a partial InfraConfig object. */
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

export function registerInfraCommands(context: Command, program: Command): void {
  // context set-infra <machine> - Set infrastructure configuration
  context
    .command('set-infra <machine>')
    .description(t('commands.context.setInfra.description'))
    .option('--public-ipv4 <ip>', t('commands.context.setInfra.optionPublicIPv4'))
    .option('--public-ipv6 <ip>', t('commands.context.setInfra.optionPublicIPv6'))
    .option('--base-domain <domain>', t('commands.context.setInfra.optionBaseDomain'))
    .option('--cert-email <email>', t('commands.context.setInfra.optionCertEmail'))
    .option('--cf-dns-token <token>', t('commands.context.setInfra.optionCfDnsToken'))
    .option('--tcp-ports <ports>', t('commands.context.setInfra.optionTcpPorts'))
    .option('--udp-ports <ports>', t('commands.context.setInfra.optionUdpPorts'))
    .action(async (machineName, options) => {
      try {
        const infra = parseInfraOptions(options);

        if (Object.keys(infra).length === 0) {
          outputService.warn(t('commands.context.setInfra.noOptions'));
          return;
        }

        const ipError = validateIpAddresses(infra);
        if (ipError) {
          outputService.error(ipError);
          return;
        }

        await contextService.setMachineInfra(machineName, infra);
        outputService.success(t('commands.context.setInfra.success', { name: machineName }));
      } catch (error) {
        handleError(error);
      }
    });

  // context show-infra <machine> - Show infrastructure configuration
  context
    .command('show-infra <machine>')
    .description(t('commands.context.showInfra.description'))
    .action(async (machineName) => {
      try {
        const machine = await contextService.getLocalMachine(machineName);
        const format = program.opts().output as OutputFormat;

        if (!machine.infra) {
          outputService.info(t('commands.context.showInfra.noInfra', { name: machineName }));
          return;
        }

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

        outputService.print(display, format);
      } catch (error) {
        handleError(error);
      }
    });

  // context push-infra <machine> - Push infrastructure config to remote
  context
    .command('push-infra <machine>')
    .description(t('commands.context.pushInfra.description'))
    .option('--debug', t('options.debug'))
    .action(async (machineName, options) => {
      try {
        const { pushInfraConfig } = await import('../services/infra-provision.js');
        await pushInfraConfig(machineName, { debug: options.debug });
        outputService.success(t('commands.context.pushInfra.success', { name: machineName }));
      } catch (error) {
        handleError(error);
      }
    });
}
