import { describe, expect, it } from 'vitest';
import { getMaxMachines, PLAN_MAX_MACHINES } from '../constants.js';
import type { PlanCode } from '../types.js';

describe('PLAN_MAX_MACHINES', () => {
  it('should define limits for all plan codes', () => {
    const planCodes: PlanCode[] = ['COMMUNITY', 'PROFESSIONAL', 'BUSINESS', 'ENTERPRISE'];
    for (const code of planCodes) {
      expect(PLAN_MAX_MACHINES[code]).toBeTypeOf('number');
      expect(PLAN_MAX_MACHINES[code]).toBeGreaterThan(0);
    }
  });

  it('should have correct machine limits', () => {
    expect(PLAN_MAX_MACHINES.COMMUNITY).toBe(2);
    expect(PLAN_MAX_MACHINES.PROFESSIONAL).toBe(5);
    expect(PLAN_MAX_MACHINES.BUSINESS).toBe(20);
    expect(PLAN_MAX_MACHINES.ENTERPRISE).toBe(50);
  });

  it('should increase with higher plans', () => {
    expect(PLAN_MAX_MACHINES.PROFESSIONAL).toBeGreaterThan(PLAN_MAX_MACHINES.COMMUNITY);
    expect(PLAN_MAX_MACHINES.BUSINESS).toBeGreaterThan(PLAN_MAX_MACHINES.PROFESSIONAL);
    expect(PLAN_MAX_MACHINES.ENTERPRISE).toBeGreaterThan(PLAN_MAX_MACHINES.BUSINESS);
  });
});

describe('getMaxMachines', () => {
  it('should return correct limit for valid plan codes', () => {
    expect(getMaxMachines('COMMUNITY')).toBe(2);
    expect(getMaxMachines('PROFESSIONAL')).toBe(5);
    expect(getMaxMachines('BUSINESS')).toBe(20);
    expect(getMaxMachines('ENTERPRISE')).toBe(50);
  });

  it('should return COMMUNITY limit for invalid plan codes', () => {
    expect(getMaxMachines('INVALID')).toBe(2);
    expect(getMaxMachines('')).toBe(2);
    expect(getMaxMachines('unknown')).toBe(2);
  });
});
