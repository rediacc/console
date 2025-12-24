import { describe, it, expect } from 'vitest';
import { buildExportData } from '../exportUtils';

describe('exportUtils', () => {
  describe('buildExportData', () => {
    it('should encode base64 fields', () => {
      const formData = {
        base64Field: 'raw value',
        normalField: 'normal value',
      };

      const entityDef = {
        fields: {
          base64Field: { type: 'string', format: 'base64' },
          normalField: { type: 'string' },
        },
      };

      const result = buildExportData(formData, entityDef, {});

      expect(result.base64Field).toBe(btoa('raw value'));
      expect(result.normalField).toBe('normal value');
    });

    it('should include extraFields when present', () => {
      const formData = { field1: 'value1' };
      const entityDef = { fields: { field1: { type: 'string' } } };
      const extraFields = { extra1: 'extraValue' };

      const result = buildExportData(formData, entityDef, extraFields);

      expect(result.extraFields).toEqual(extraFields);
    });

    it('should remove undefined values', () => {
      const formData = {
        field1: 'value1',
        field2: undefined,
      };

      const entityDef = {
        fields: {
          field1: { type: 'string' },
          field2: { type: 'string' },
        },
      };

      const result = buildExportData(formData, entityDef, {});

      expect(result.field1).toBe('value1');
      expect('field2' in result).toBe(false);
    });
  });
});
