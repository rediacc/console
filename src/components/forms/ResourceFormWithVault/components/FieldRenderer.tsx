import { Input } from 'antd'
import { Controller, Control } from 'react-hook-form'
import type { ControllerProps, FieldValues } from 'react-hook-form'
import type { FormFieldConfig } from '../types'
import {
  SizeInputGroup,
  SizeNumberInput,
  SizeUnitSelect,
  FullWidthSelect,
} from '../styles'

interface FieldRendererProps<T extends FieldValues> {
  field: FormFieldConfig<T>
  control: Control<T>
}

export const FieldRenderer = <T extends FieldValues>({
  field,
  control,
}: FieldRendererProps<T>) => {
  switch (field.type) {
    case 'select':
      return (
        <Controller
          name={field.name as any}
          control={control}
          rules={field.rules as ControllerProps<T>['rules']}
          render={({ field: controllerField }) => (
            <FullWidthSelect
              {...controllerField}
              options={field.options}
              placeholder={field.placeholder}
              disabled={field.disabled}
              showSearch
              allowClear
              optionFilterProp="label"
              data-testid={`resource-modal-field-${field.name}-select`}
            />
          )}
        />
      )
    case 'password':
      return (
        <Controller
          name={field.name as any}
          control={control}
          rules={field.rules as ControllerProps<T>['rules']}
          render={({ field: controllerField }) => (
            <Input.Password
              {...controllerField}
              placeholder={field.placeholder}
              disabled={field.disabled}
              data-testid={`resource-modal-field-${field.name}-password`}
            />
          )}
        />
      )
    case 'size': {
      const units = field.sizeUnits || ['G', 'T']
      const defaultUnit = units[0] === 'percentage' ? '%' : units[0]
      return (
        <Controller
          name={field.name as any}
          control={control}
          rules={field.rules as ControllerProps<T>['rules']}
          render={({ field: controllerField }) => {
            const rawValue = controllerField.value
            const currentValue =
              typeof rawValue === 'string'
                ? rawValue
                : rawValue !== undefined && rawValue !== null
                ? String(rawValue)
                : ''
            let parsedValue: number | undefined
            let parsedUnit = defaultUnit

            if (currentValue) {
              const match = currentValue.match(/^(\d+)([%GT]?)$/)
              if (match) {
                parsedValue = parseInt(match[1], 10)
                parsedUnit = match[2] || defaultUnit
              }
            }

            return (
              <SizeInputGroup>
                <SizeNumberInput
                  data-testid={`resource-modal-field-${field.name}-size-input`}
                  value={parsedValue}
                  onChange={(value) => {
                    if (value === null || value === undefined) {
                      controllerField.onChange('')
                      return
                    }
                    const numericValue =
                      typeof value === 'string' ? parseInt(value, 10) : value
                    if (!isNaN(numericValue) && numericValue > 0) {
                      controllerField.onChange(`${numericValue}${parsedUnit}`)
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
                    ]
                    if (
                      !/[0-9]/.test(event.key) &&
                      !allowedKeys.includes(event.key)
                    ) {
                      event.preventDefault()
                    }
                  }}
                  parser={(value) => {
                    const parsed = value?.replace(/[^\d]/g, '')
                    return parsed ? parseInt(parsed, 10) : 0
                  }}
                  formatter={(value) => (value ? `${value}` : '')}
                  placeholder={units.includes('percentage') ? '95' : '100'}
                  min={1}
                  max={units.includes('percentage') ? 100 : undefined}
                  disabled={field.disabled}
                  keyboard
                  step={1}
                  precision={0}
                />
                <SizeUnitSelect
                  data-testid={`resource-modal-field-${field.name}-size-unit`}
                  value={parsedUnit}
                  onChange={(unit) => {
                    const newValue = parsedValue ? `${parsedValue}${unit}` : ''
                    controllerField.onChange(newValue)
                  }}
                  options={units.map((unit) => ({
                    value: unit === 'percentage' ? '%' : unit,
                    label:
                      unit === 'percentage'
                        ? '%'
                        : unit === 'G'
                        ? 'GB'
                        : 'TB',
                  }))}
                  disabled={field.disabled}
                />
              </SizeInputGroup>
            )
          }}
        />
      )
    }
    default:
      return (
        <Controller
          name={field.name as any}
          control={control}
          rules={field.rules as ControllerProps<T>['rules']}
          render={({ field: controllerField }) => (
            <Input
              {...controllerField}
              data-testid={`resource-modal-field-${field.name}-input`}
              type={field.type || 'text'}
              placeholder={field.placeholder}
              disabled={field.disabled}
              readOnly={field.readOnly}
              autoComplete="off"
            />
          )}
        />
      )
  }
}
