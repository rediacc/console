import { Input, InputNumber, Select, Space } from 'antd';
import type { FormFieldConfig } from '../types';

interface FieldRendererProps {
  field: FormFieldConfig;
  value?: unknown;
  onChange?: (value: unknown) => void;
}

/**
 * Renders form field input based on field type.
 * Used with Ant Design Form.Item which handles value binding via name prop.
 */
export const FieldRenderer: React.FC<FieldRendererProps> = ({ field, value, onChange }) => {
  switch (field.type) {
    case 'select':
      return (
        <Select
          value={value as string | undefined}
          onChange={onChange}
          className="w-full"
          options={field.options}
          placeholder={field.placeholder}
          disabled={field.disabled}
          showSearch
          allowClear
          optionFilterProp="label"
          data-testid={`resource-modal-field-${field.name}-select`}
        />
      );

    case 'password':
      return (
        <Input.Password
          value={value as string | undefined}
          onChange={(e) => onChange?.(e.target.value)}
          placeholder={field.placeholder}
          disabled={field.disabled}
          data-testid={`resource-modal-field-${field.name}-password`}
        />
      );

    case 'size': {
      const units = field.sizeUnits ?? ['G', 'T'];
      const defaultUnit = units[0] === 'percentage' ? '%' : units[0];

      const currentValue =
        typeof value === 'string'
          ? value
          : value !== undefined && value !== null
            ? String(value)
            : '';

      let parsedValue: number | undefined;
      let parsedUnit = defaultUnit;

      if (currentValue) {
        const match = currentValue.match(/^(\d+)([%GT]?)$/);
        if (match) {
          parsedValue = parseInt(match[1], 10);
          parsedUnit = match[2] || defaultUnit;
        }
      }

      return (
        <Space.Compact className="w-full">
          <InputNumber
            data-testid={`resource-modal-field-${field.name}-size-input`}
            value={parsedValue}
            onChange={(numValue) => {
              if (numValue === null) {
                onChange?.('');
                return;
              }
              const numericValue = typeof numValue === 'string' ? parseInt(numValue, 10) : numValue;
              if (!isNaN(numericValue) && numericValue > 0) {
                onChange?.(`${numericValue}${parsedUnit}`);
              }
            }}
            onKeyDown={(event) => {
              const allowedKeys = [
                'Backspace',
                'Delete',
                'Tab',
                'Enter',
                'ArrowLeft',
                'ArrowRight',
              ];
              if (!/[0-9]/.test(event.key) && !allowedKeys.includes(event.key)) {
                event.preventDefault();
              }
            }}
            parser={(val) => {
              const parsed = val?.replace(/[^\d]/g, '');
              return parsed ? parseInt(parsed, 10) : 0;
            }}
            formatter={(val) => (val ? `${val}` : '')}
            placeholder={units.includes('percentage') ? '95' : '100'}
            min={1}
            max={units.includes('percentage') ? 100 : undefined}
            disabled={field.disabled}
            keyboard
            step={1}
            precision={0}
            className="flex-1"
          />
          <Select
            data-testid={`resource-modal-field-${field.name}-size-unit`}
            value={parsedUnit}
            onChange={(unit) => {
              const newValue = parsedValue ? `${parsedValue}${unit}` : '';
              onChange?.(newValue);
            }}
            options={units.map((unit) => {
              const unitValue = unit === 'percentage' ? '%' : unit;
              let label: string;
              if (unit === 'percentage') {
                label = '%';
              } else if (unit === 'G') {
                label = 'GB';
              } else {
                label = 'TB';
              }
              return { value: unitValue, label };
            })}
            disabled={field.disabled}
            style={{ width: 80 }} // eslint-disable-line no-restricted-syntax
          />
        </Space.Compact>
      );
    }

    default: {
      // Remaining types: 'text' | 'email' | 'number' | undefined
      // Note: 'password' is handled in its own case above
      const inputType = field.type === 'email' ? 'email' : 'text';

      return (
        <Input
          value={value as string | undefined}
          onChange={(e) => onChange?.(e.target.value)}
          data-testid={`resource-modal-field-${field.name}-input`}
          type={inputType}
          placeholder={field.placeholder}
          disabled={field.disabled}
          readOnly={field.readOnly}
          autoComplete="off"
        />
      );
    }
  }
};
