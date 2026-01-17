import { describe, expect, it } from 'vitest';
import { processFieldMovements, syncFormWithJson } from '../jsonUtils';

describe('jsonUtils', () => {
  describe('processFieldMovements', () => {
    it('should process fields correctly', () => {
      const parsed = {
        fieldA: 'value1',
        fieldB: 'value2',
        unknownField: 'value3',
        extraFields: { extra1: 'extraValue' },
      };

      const entityDef = {
        fields: {
          fieldA: { type: 'string' },
          fieldB: { type: 'string' },
        },
      };

      const extraFields = {};

      const result = processFieldMovements(parsed, entityDef, extraFields);

      expect(result.formData).toEqual({
        fieldA: 'value1',
        fieldB: 'value2',
      });

      expect(result.extras).toEqual({
        extra1: 'extraValue',
        unknownField: 'value3',
      });

      expect(result.movements.movedToExtra).toContain('unknownField');
    });

    it('should decode base64 fields', () => {
      const parsed = {
        base64Field: btoa('decoded value'),
      };

      const entityDef = {
        fields: {
          base64Field: { type: 'string', format: 'base64' },
        },
      };

      const result = processFieldMovements(parsed, entityDef, {});

      expect(result.formData.base64Field).toBe('decoded value');
    });

    it('should track fields moved from extra', () => {
      const parsed = {
        fieldA: 'value1',
      };

      const entityDef = {
        fields: {
          fieldA: { type: 'string' },
        },
      };

      const extraFields = {
        fieldA: 'old value',
      };

      const result = processFieldMovements(parsed, entityDef, extraFields);

      expect(result.movements.movedFromExtra).toContain('fieldA');
    });
  });

  describe('syncFormWithJson', () => {
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

      const result = syncFormWithJson(formData, {}, entityDef);

      expect(result.base64Field).toBe(btoa('raw value'));
      expect(result.normalField).toBe('normal value');
    });

    it('should include extraFields when present', () => {
      const formData = { field1: 'value1' };
      const extras = { extra1: 'extraValue' };
      const entityDef = { fields: { field1: { type: 'string' } } };

      const result = syncFormWithJson(formData, extras, entityDef);

      expect(result.extraFields).toEqual(extras);
    });

    it('should not include extraFields when empty', () => {
      const formData = { field1: 'value1' };
      const entityDef = { fields: { field1: { type: 'string' } } };

      const result = syncFormWithJson(formData, {}, entityDef);

      expect(result.extraFields).toBeUndefined();
    });
  });
});
