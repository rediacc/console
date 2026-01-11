import { describe, it, expect, vi } from 'vitest';
import {
  moveToExtraFields,
  moveFromExtraFields,
  processExtraFields,
  buildValidationRules,
} from '../../utils';
import type { Rule } from 'antd/es/form';

// Helper predicates for rule validation (extracted to avoid nested callbacks)
const hasPattern = (r: Rule): boolean => 'pattern' in r;
const hasMinValue =
  (value: number) =>
  (r: Rule): boolean =>
    'min' in r && (r as { min: number }).min === value;
const hasMaxValue =
  (value: number) =>
  (r: Rule): boolean =>
    'max' in r && (r as { max: number }).max === value;

describe('VaultEditor utils', () => {
  describe('moveToExtraFields', () => {
    it('should move non-schema fields to extras', () => {
      const data = {
        fieldA: 'value1',
        unknownField: 'value2',
      };

      const result = moveToExtraFields(data, ['fieldA'], {});

      expect(result.extras).toEqual({ unknownField: 'value2' });
      expect(result.movedToExtra).toEqual(['unknownField']);
    });

    it('should preserve extraFields structure', () => {
      const data = {
        extraFields: { extra1: 'value1' },
        unknownField: 'value2',
      };

      const result = moveToExtraFields(data, [], {});

      expect(result.extras).toEqual({
        extra1: 'value1',
        unknownField: 'value2',
      });
    });
  });

  describe('moveFromExtraFields', () => {
    it('should identify fields moved from extras', () => {
      const data = { fieldA: 'value1' };
      const currentExtras = { fieldA: 'old value', fieldB: 'value2' };
      const extras = { fieldB: 'value2' };

      const result = moveFromExtraFields(data, ['fieldA'], currentExtras, extras);

      expect(result).toEqual(['fieldA']);
    });
  });

  describe('processExtraFields', () => {
    it('should process all field movements', () => {
      const data = {
        fieldA: 'value1',
        unknownField: 'value2',
      };

      const result = processExtraFields(data, ['fieldA'], {});

      expect(result.extras).toEqual({ unknownField: 'value2' });
      expect(result.movedToExtra).toEqual(['unknownField']);
      expect(result.movedFromExtra).toEqual([]);
    });
  });

  describe('buildValidationRules', () => {
    const mockT = vi.fn((key: string, opts?: Record<string, unknown>) => {
      if (key === 'vaultEditor.isRequired') return `${opts?.field} is required`;
      if (key === 'vaultEditor.minLength') return `Min length ${opts?.length}`;
      if (key === 'vaultEditor.maxLength') return `Max length ${opts?.length}`;
      return key;
    });

    it('should add required rule', () => {
      const field = { type: 'string' };
      const rules = buildValidationRules(field, true, 'Test Field', mockT);

      expect(rules).toHaveLength(1);
      expect(rules[0]).toEqual({
        required: true,
        message: 'Test Field is required',
      });
    });

    it('should add pattern rule', () => {
      const field = { type: 'string', pattern: '^[a-z]+$' };
      const rules = buildValidationRules(field, false, 'Test', mockT);

      expect(rules.some(hasPattern)).toBe(true);
    });

    it('should add length rules', () => {
      const field = { type: 'string', minLength: 3, maxLength: 10 };
      const rules = buildValidationRules(field, false, 'Test', mockT);

      expect(rules.some(hasMinValue(3))).toBe(true);
      expect(rules.some(hasMaxValue(10))).toBe(true);
    });

    it('should add numeric range rules', () => {
      const field = { type: 'number', minimum: 0, maximum: 100 };
      const rules = buildValidationRules(field, false, 'Test', mockT);

      expect(rules.some(hasMinValue(0))).toBe(true);
      expect(rules.some(hasMaxValue(100))).toBe(true);
    });
  });
});
