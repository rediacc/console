/**
 * The semantic fields of a contract command (D1 of
 * agent/plans/PLAN-console-contract-semantics.md): summary, severity, preview,
 * the proxy-refusal key, and the contract's error-code origins.
 *
 * Each invariant gets a planted defect that names it and a clean control that
 * stays silent. The fixtures are synthetic so the tests hold whatever the
 * committed contract currently carries.
 */
import { describe, expect, it } from 'vitest';
import type { CliContract, ContractCommand, ContractOption } from '../types.js';
import {
  CliContractSchema,
  ContractCommandSchema,
  checkContractInvariants,
  SUMMARY_MAX_LENGTH,
} from '../validation.js';
import { omitKey } from '../../utils/omit-key.js';

function option(long: string, valueTaking: boolean): ContractOption {
  return {
    flags: valueTaking ? `--${long} <value>` : `--${long}`,
    long,
    valueTaking,
    variadic: false,
    mandatory: false,
    defaultValue: null,
    tier: 'common',
    descriptionKey: null,
    label: long,
  };
}

/** A clean, proxyable, non-job command with a dry-run switch. */
function command(extra: Partial<ContractCommand> = {}): ContractCommand {
  return {
    path: ['thing', 'prune'],
    pathKey: 'thing prune',
    domain: 'thing',
    group: null,
    plane: 'machine',
    descriptionKey: null,
    label: 'Prune things',
    summaryKey: 'commands.thing.prune.descriptionShort',
    summary: 'Prune things',
    severity: 'destructive',
    preview: { flag: 'dry-run', polarity: 'opt-in' },
    options: [option('dry-run', false), option('machine', true)],
    positionals: [],
    hasSubcommands: false,
    interactive: false,
    proxyCapable: true,
    detachable: true,
    machineOption: 'machine',
    repoOption: null,
    machinePositional: null,
    repoPositional: null,
    ...extra,
  };
}

function contract(commands: ContractCommand[], extra: Partial<CliContract> = {}): CliContract {
  return {
    version: 'test',
    languages: ['en'],
    commands,
    errorCodes: [
      { code: 'INVALID_ARGUMENT', origin: 'user' },
      { code: 'SSH_ERROR', origin: 'environment' },
      { code: 'SERVER_ERROR', origin: 'rediacc' },
    ],
    ...extra,
  };
}

describe('contract semantics: schema', () => {
  it('accepts a command carrying every semantic field', () => {
    expect(CliContractSchema.safeParse(contract([command()])).success).toBe(true);
  });

  it('requires summaryKey, summary and severity', () => {
    for (const field of ['summaryKey', 'summary', 'severity'] as const) {
      const entry: Record<string, unknown> = { ...command() };
      delete entry[field];
      expect(ContractCommandSchema.safeParse(entry).success, field).toBe(false);
    }
  });

  it('allows a null summaryKey but not an empty summary', () => {
    expect(ContractCommandSchema.safeParse(command({ summaryKey: null })).success).toBe(true);
    expect(ContractCommandSchema.safeParse(command({ summary: '' })).success).toBe(false);
  });

  it('refuses a severity or polarity outside its set', () => {
    expect(ContractCommandSchema.safeParse({ ...command(), severity: 'high' }).success).toBe(false);
    expect(
      ContractCommandSchema.safeParse({
        ...command(),
        preview: { flag: 'dry-run', polarity: 'always' },
      }).success
    ).toBe(false);
  });

  it('requires errorCodes, each with an origin from the set', () => {
    const withoutCodes = omitKey(contract([command()]), 'errorCodes');
    expect(CliContractSchema.safeParse(withoutCodes).success).toBe(false);
    const badOrigin = { ...contract([command()]), errorCodes: [{ code: 'X', origin: 'cosmic' }] };
    expect(CliContractSchema.safeParse(badOrigin).success).toBe(false);
    const noOrigin = { ...contract([command()]), errorCodes: [{ code: 'X' }] };
    expect(CliContractSchema.safeParse(noOrigin).success).toBe(false);
  });
});

describe('contract semantics: invariants', () => {
  it('a clean contract has no problems', () => {
    expect(checkContractInvariants(contract([command()]))).toEqual([]);
  });

  it(`refuses a summary over ${SUMMARY_MAX_LENGTH} characters, and accepts one at the limit`, () => {
    const atLimit = command({ summary: 'x'.repeat(SUMMARY_MAX_LENGTH) });
    expect(checkContractInvariants(contract([atLimit]))).toEqual([]);
    const over = command({ summary: 'x'.repeat(SUMMARY_MAX_LENGTH + 1) });
    expect(checkContractInvariants(contract([over]))).toEqual([
      `thing prune: summary is ${SUMMARY_MAX_LENGTH + 1} characters, over ${SUMMARY_MAX_LENGTH}`,
    ]);
  });

  it('refuses a preview.flag that names no option of its command', () => {
    const planted = command({ preview: { flag: 'apply', polarity: 'default' } });
    expect(checkContractInvariants(contract([planted]))).toEqual([
      'thing prune: preview.flag "apply" names no option of this command',
    ]);
  });

  it('accepts a default-polarity preview whose flag is a real switch', () => {
    const clean = command({
      options: [option('apply', false)],
      machineOption: null,
      preview: { flag: 'apply', polarity: 'default' },
    });
    expect(checkContractInvariants(contract([clean]))).toEqual([]);
  });

  it('refuses a preview.flag that takes a value', () => {
    const planted = command({
      options: [option('apply', true)],
      machineOption: null,
      preview: { flag: 'apply', polarity: 'default' },
    });
    expect(checkContractInvariants(contract([planted]))).toEqual([
      'thing prune: preview.flag "apply" takes a value, not a switch',
    ]);
  });

  it('accepts a command with no preview', () => {
    expect(checkContractInvariants(contract([command({ preview: undefined })]))).toEqual([]);
  });

  it('refuses severity none on an MCP-destructive command, and allows caution', () => {
    const planted = command({ destructive: true, severity: 'none' });
    expect(checkContractInvariants(contract([planted]))).toEqual([
      'thing prune: MCP-annotated destructive but severity is "none"',
    ]);
    const clean = command({ destructive: true, severity: 'caution' });
    expect(checkContractInvariants(contract([clean]))).toEqual([]);
    const unannotated = command({ severity: 'none' });
    expect(checkContractInvariants(contract([unannotated]))).toEqual([]);
  });

  it('refuses a proxyBlockedReasonKey without a proxyBlockedReason', () => {
    const planted = command({ proxyBlockedReasonKey: 'commands.proxyBlocked.local' });
    expect(checkContractInvariants(contract([planted]))).toEqual([
      'thing prune: proxyBlockedReasonKey set without a proxyBlockedReason',
    ]);
    const clean = command({
      proxyCapable: false,
      detachable: false,
      proxyBlockedReason: 'Runs locally.',
      proxyBlockedReasonKey: 'commands.proxyBlocked.local',
    });
    expect(checkContractInvariants(contract([clean]))).toEqual([]);
  });

  it('refuses a duplicate error code', () => {
    const planted = contract([command()], {
      errorCodes: [
        { code: 'SSH_ERROR', origin: 'environment' },
        { code: 'SSH_ERROR', origin: 'user' },
      ],
    });
    expect(checkContractInvariants(planted)).toEqual(['error code SSH_ERROR: duplicate entry']);
  });
});
