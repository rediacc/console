import { describe, expect, it } from 'vitest';
import {
  buildRecoveryKit,
  checkRecoveryKitSaved,
  generateRecoveryCode,
  KIT_CHECK_LENGTH,
} from '../index.js';

const CODE = 'RC1-7GV21VCB-YQ8C4CTM-FV1Z5KST-NVQVCMA9';

describe('buildRecoveryKit', () => {
  const kit = buildRecoveryKit({
    storeName: 'Acme',
    userEmail: 'owner@acme.test',
    createdAt: new Date('2026-11-23T15:00:00Z'),
    recoveryCode: '7gv2lvcb yq8c4ctm fvIz5kst nvqvcma9',
  });

  it('carries the store, the user, the date and the canonical code in groups', () => {
    expect(kit.storeName).toBe('Acme');
    expect(kit.userEmail).toBe('owner@acme.test');
    expect(kit.createdOn).toBe('2026-11-23');
    expect(kit.code).toBe(CODE);
    expect(kit.codeGroups).toEqual(['7GV21VCB', 'YQ8C4CTM', 'FV1Z5KST', 'NVQVCMA9']);
  });

  it('encodes the canonical code in the QR payload, so a scan answers the save check', () => {
    expect(kit.qrPayload).toBe(CODE);
    expect(checkRecoveryKitSaved(CODE, kit.qrPayload)).toBe(true);
  });

  it('names the store and user in the instructions and carries the keep notice', () => {
    expect(kit.instructions.length).toBeGreaterThan(0);
    expect(kit.instructions[0]).toContain('Acme');
    expect(kit.instructions[0]).toContain('owner@acme.test');
    expect(kit.keepNotice).toMatch(/responsibility/);
  });

  it('refuses an invalid code', () => {
    expect(() =>
      buildRecoveryKit({
        storeName: 'Acme',
        userEmail: 'owner@acme.test',
        createdAt: new Date(),
        recoveryCode: 'RC1-SHORT',
      })
    ).toThrow(/must have 32 characters/);
  });
});

describe('checkRecoveryKitSaved', () => {
  it('asks for 4 characters', () => {
    expect(KIT_CHECK_LENGTH).toBe(4);
  });

  it('accepts the right last 4 characters, forgiving case, spaces and aliases', () => {
    expect(checkRecoveryKitSaved(CODE, 'CMA9')).toBe(true);
    expect(checkRecoveryKitSaved(CODE, 'cma9')).toBe(true);
    expect(checkRecoveryKitSaved(CODE, ' cm a9 ')).toBe(true);
    // A code ending in the digit 1 accepts the letter alias typed for it.
    expect(checkRecoveryKitSaved('RC1-00000000-00000000-00000000-0000ABC1', 'abcl')).toBe(true);
  });

  it('refuses the wrong last 4 characters', () => {
    expect(checkRecoveryKitSaved(CODE, 'CMA8')).toBe(false);
    expect(checkRecoveryKitSaved(CODE, '7GV2')).toBe(false); // the first 4, not the last
    expect(checkRecoveryKitSaved(CODE, 'VCMA9')).toBe(false); // 5 characters
    expect(checkRecoveryKitSaved(CODE, 'MA9')).toBe(false); // 3 characters
    expect(checkRecoveryKitSaved(CODE, '')).toBe(false);
    expect(checkRecoveryKitSaved(CODE, '    ')).toBe(false);
  });

  it('accepts the whole code typed with or without the prefix, and refuses another code', () => {
    expect(checkRecoveryKitSaved(CODE, CODE.toLowerCase())).toBe(true);
    expect(checkRecoveryKitSaved(CODE, CODE.slice(4))).toBe(true);
    expect(checkRecoveryKitSaved(CODE, generateRecoveryCode())).toBe(false);
  });
});
