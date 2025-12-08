import React from 'react';
import { Checkbox, Input, Select } from 'antd';
import { useTranslation } from 'react-i18next';
import type { QueueFunction, QueueFunctionParameter } from '@/api/queries/queue';
import TemplateSelector from '@/components/common/TemplateSelector';
import type { Machine, Repo } from '@/types';
import type { GetTeamStorages_ResultSet1 as Storage } from '@rediacc/shared/types';
import {
  AdditionalOptionsInput,
  CheckboxGroupStack,
  SizeInputGroup,
  SizeUnitSelect,
  SizeValueInput,
} from '../styles';

type FunctionParamValue = string | number | string[] | undefined;
type FunctionParams = Record<string, FunctionParamValue>;

interface FunctionParameterFieldProps {
  paramName: string;
  paramInfo: QueueFunctionParameter;
  functionParams: FunctionParams;
  selectedFunction?: QueueFunction;
  onParamChange: (paramName: string, value: FunctionParamValue) => void;
  onTemplatesChange: (templates: string[]) => void;
  onTemplateView: (templateName: string) => void;
  selectedTemplates: string[];
  repos?: Repo[];
  machinesData?: Machine[];
  storageData?: Storage[];
  currentMachineName?: string;
}

const FunctionParameterField: React.FC<FunctionParameterFieldProps> = ({
  paramName,
  paramInfo,
  functionParams,
  selectedFunction: _selectedFunction,
  onParamChange,
  onTemplatesChange,
  onTemplateView,
  selectedTemplates,
  repos = [],
  machinesData = [],
  storageData = [],
  currentMachineName,
}) => {
  const { t } = useTranslation(['functions', 'common', 'machines', 'resources']);

  const getStringParam = (key: string): string => (functionParams[key] as string | undefined) || '';
  const getArrayParam = (key: string): string[] =>
    Array.isArray(functionParams[key]) ? (functionParams[key] as string[]) : [];
  const getSelectValue = (key: string): string | number | undefined =>
    functionParams[key] as string | number | undefined;

  const isSizeParam = paramInfo.format === 'size' && paramInfo.units;

  // Size parameter renderer
  if (isSizeParam && paramInfo.units) {
    return (
      <SizeInputGroup>
        <SizeValueInput
          value={
            typeof functionParams[`${paramName}_value`] === 'number'
              ? (functionParams[`${paramName}_value`] as number)
              : undefined
          }
          onChange={(value) => {
            if (value === null || value === undefined) {
              onParamChange(`${paramName}_value`, undefined);
              onParamChange(paramName, '');
            } else {
              const numValue = typeof value === 'string' ? parseInt(value, 10) : value;
              if (!Number.isNaN(numValue) && numValue > 0 && paramInfo.units) {
                const unit =
                  (functionParams[`${paramName}_unit`] as string | undefined) ||
                  (paramInfo.units[0] === 'percentage' ? '%' : paramInfo.units[0]);
                onParamChange(`${paramName}_value`, numValue);
                onParamChange(paramName, `${numValue}${unit}`);
              }
            }
          }}
          parser={(value) => {
            const parsed = value?.replace(/[^\d]/g, '');
            return parsed ? parseInt(parsed, 10) : 0;
          }}
          formatter={(v) => (v ? `${v}` : '')}
          placeholder={paramInfo.units?.includes('percentage') ? '95' : '100'}
          min={1}
          max={paramInfo.units?.includes('percentage') ? 100 : undefined}
          keyboard
          step={1}
          precision={0}
          data-testid={`function-modal-param-${paramName}-value`}
        />
        <SizeUnitSelect
          value={
            (functionParams[`${paramName}_unit`] as string | undefined) ||
            (paramInfo.units[0] === 'percentage' ? '%' : paramInfo.units[0] || '')
          }
          onChange={(unitValue) => {
            const unit = String(unitValue ?? '');
            const currentValue = functionParams[`${paramName}_value`];
            onParamChange(`${paramName}_unit`, unit);
            onParamChange(
              paramName,
              typeof currentValue === 'number' ? `${currentValue}${unit}` : ''
            );
          }}
          options={paramInfo.units.map((unit: string) => ({
            value: unit === 'percentage' ? '%' : unit,
            label: unit === 'percentage' ? '%' : unit === 'G' ? 'GB' : 'TB',
          }))}
          data-testid={`function-modal-param-${paramName}-unit`}
        />
      </SizeInputGroup>
    );
  }

  // Select dropdown (with options)
  if (paramInfo.options && paramInfo.options.length > 0) {
    return (
      <Select<string>
        value={(getSelectValue(paramName) as string) ?? paramInfo.default ?? ''}
        onChange={(value: string) => {
          const previousValue = functionParams[paramName];
          onParamChange(paramName, value);
          // Clear dependent field when destinationType changes
          if (paramName === 'destinationType' && value !== previousValue) {
            onParamChange('to', '');
          }
        }}
        placeholder={paramInfo.help || ''}
        options={paramInfo.options.map((option: string) => ({
          value: option,
          label: option,
        }))}
        data-testid={`function-modal-param-${paramName}`}
      />
    );
  }

  // Repo dropdown
  if (paramInfo.ui === 'repo-dropdown') {
    return (
      <Select
        value={getStringParam(paramName)}
        onChange={(value) => onParamChange(paramName, value)}
        placeholder={t('resources:repos.selectRepo')}
        options={
          repos?.map((repo) => ({
            value: repo.repoGuid,
            label: repo.repoName,
          })) || []
        }
        notFoundContent={t('resources:repos.noReposFound')}
        showSearch
        filterOption={(input, option) =>
          (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
        }
        data-testid={`function-modal-param-${paramName}`}
      />
    );
  }

  // Destination dropdown
  if (paramInfo.ui === 'destination-dropdown') {
    const destinationType = getStringParam('destinationType');
    return (
      <Select
        value={getStringParam(paramName)}
        onChange={(value) => onParamChange(paramName, value)}
        placeholder={
          destinationType === 'machine'
            ? t('machines:selectMachine')
            : t('resources:storage.selectStorage')
        }
        options={
          destinationType === 'machine'
            ? machinesData?.map((machine) => ({
                value: machine.machineName,
                label:
                  machine.machineName === currentMachineName
                    ? `${machine.machineName} (${t('machines:currentMachine')})`
                    : machine.machineName,
              })) || []
            : storageData?.map((storage) => ({
                value: storage.storageName,
                label: storage.storageName,
              })) || []
        }
        notFoundContent={
          destinationType === 'machine'
            ? t('machines:noMachinesFound')
            : t('resources:storage.noStorageFound')
        }
        showSearch
        filterOption={(input, option) =>
          (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
        }
        disabled={!destinationType}
        data-testid={`function-modal-param-${paramName}`}
      />
    );
  }

  // Source dropdown
  if (paramInfo.ui === 'source-dropdown') {
    const sourceType = getStringParam('sourceType');
    return (
      <Select
        value={getStringParam(paramName)}
        onChange={(value) => onParamChange(paramName, value)}
        placeholder={
          sourceType === 'machine'
            ? t('machines:selectMachine')
            : t('resources:storage.selectStorage')
        }
        options={
          sourceType === 'machine'
            ? machinesData?.map((machine) => ({
                value: machine.machineName,
                label:
                  machine.machineName === currentMachineName
                    ? `${machine.machineName} (${t('machines:currentMachine')})`
                    : machine.machineName,
              })) || []
            : storageData?.map((storage) => ({
                value: storage.storageName,
                label: storage.storageName,
              })) || []
        }
        notFoundContent={
          sourceType === 'machine'
            ? t('machines:noMachinesFound')
            : t('resources:storage.noStorageFound')
        }
        showSearch
        filterOption={(input, option) =>
          (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
        }
        disabled={!sourceType}
        data-testid={`function-modal-param-${paramName}`}
      />
    );
  }

  // Machine multiselect
  if (paramInfo.ui === 'machine-multiselect') {
    return (
      <Select
        mode="multiple"
        value={getArrayParam(paramName)}
        onChange={(value) => onParamChange(paramName, value)}
        placeholder={t('machines:selectMachines')}
        options={
          machinesData?.map((machine) => ({
            value: machine.machineName,
            label:
              machine.machineName === currentMachineName
                ? `${machine.machineName} (${t('machines:currentMachine')})`
                : machine.machineName,
          })) || []
        }
        notFoundContent={t('machines:noMachinesFound')}
        showSearch
        filterOption={(input, option) =>
          (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
        }
        data-testid={`function-modal-param-${paramName}`}
      />
    );
  }

  // Storage multiselect
  if (paramInfo.ui === 'storage-multiselect') {
    return (
      <Select
        mode="multiple"
        value={getArrayParam(paramName)}
        onChange={(value) => onParamChange(paramName, value)}
        placeholder={t('resources:storage.selectStorageSystems')}
        options={
          storageData?.map((storage) => ({
            value: storage.storageName,
            label: storage.storageName,
          })) || []
        }
        notFoundContent={t('resources:storage.noStorageFound')}
        showSearch
        filterOption={(input, option) =>
          (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
        }
        data-testid={`function-modal-param-${paramName}`}
      />
    );
  }

  // Template selector
  if (paramInfo.ui === 'template-selector') {
    return (
      <TemplateSelector
        value={selectedTemplates}
        onChange={(templateIds) => {
          onTemplatesChange(Array.isArray(templateIds) ? templateIds : []);
        }}
        onViewDetails={(templateName) => onTemplateView(templateName)}
        multiple={true}
      />
    );
  }

  // Checkbox group
  if (paramInfo.ui === 'checkbox' && paramInfo.checkboxOptions) {
    const selectedValues = getStringParam(paramName).split(' ').filter(Boolean);

    return (
      <CheckboxGroupStack>
        {paramInfo.checkboxOptions.map((option: { value: string; label: string }) => {
          const isChecked = selectedValues.includes(option.value);

          return (
            <Checkbox
              key={option.value}
              checked={isChecked}
              onChange={(e) => {
                const updatedValues = e.target.checked
                  ? Array.from(new Set([...selectedValues, option.value]))
                  : selectedValues.filter((value) => value !== option.value);

                onParamChange(paramName, updatedValues.join(' '));
              }}
              data-testid={`function-modal-param-${paramName}-${option.value}`}
            >
              {t(`functions:checkboxOptions.${option.label}`)}
            </Checkbox>
          );
        })}
        <AdditionalOptionsInput
          value={getStringParam(paramName)}
          onChange={(e) => onParamChange(paramName, e.target.value)}
          placeholder={t('functions:additionalOptions')}
          autoComplete="off"
          data-testid={`function-modal-param-${paramName}-additional`}
        />
      </CheckboxGroupStack>
    );
  }

  // Default: text input
  return (
    <Input
      value={getStringParam(paramName)}
      onChange={(e) => onParamChange(paramName, e.target.value)}
      placeholder={paramInfo.help || ''}
      autoComplete="off"
      data-testid={`function-modal-param-${paramName}`}
    />
  );
};

export default FunctionParameterField;
