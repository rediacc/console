import { describe, expect, it, vi } from 'vitest';
import { applyImportedData } from '../importUtils';

describe('importUtils', () => {
  describe('applyImportedData', () => {
    it('should extract extra fields from imported data', () => {
      const data = {
        fieldA: 'value1',
        unknownField: 'value2',
        extraFields: { extra1: 'extraValue' },
      };

      const entityDef = {
        fields: {
          fieldA: { type: 'string' },
        },
      };

      const form = {
        setFieldsValue: vi.fn(),
      };

      const callbacks = {
        setExtraFields: vi.fn(),
        setImportedData: vi.fn(),
        handleFormChange: vi.fn(),
      };

      applyImportedData(data, entityDef, form as never, callbacks);

      expect(callbacks.setExtraFields).toHaveBeenCalledWith({
        extra1: 'extraValue',
        unknownField: 'value2',
      });

      expect(form.setFieldsValue).toHaveBeenCalledWith({
        fieldA: 'value1',
      });
    });

    it('should decode base64 fields', () => {
      const data = {
        base64Field: btoa('decoded value'),
      };

      const entityDef = {
        fields: {
          base64Field: { type: 'string', format: 'base64' },
        },
      };

      const form = {
        setFieldsValue: vi.fn(),
      };

      const callbacks = {
        setExtraFields: vi.fn(),
        setImportedData: vi.fn(),
        handleFormChange: vi.fn(),
      };

      applyImportedData(data, entityDef, form as never, callbacks);

      expect(form.setFieldsValue).toHaveBeenCalledWith({
        base64Field: 'decoded value',
      });
    });
  });
});
