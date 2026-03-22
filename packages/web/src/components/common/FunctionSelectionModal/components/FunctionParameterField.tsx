import type {
  GetTeamStorages_ResultSet1,
  QueueFunction,
  QueueFunctionParameter,
} from '@rediacc/shared/types';
import { Checkbox, Flex, Input, InputNumber, Select } from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';
import TemplateSelector from '@/components/common/TemplateSelector';
import type { Machine, Repository } from '@/types';

// Generic translation function type that accepts any namespace configuration
type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

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
  repositories?: Repository[];
  machinesData?: Machine[];
  storageData?: GetTeamStorages_ResultSet1[];
  currentMachineName?: string;
}

// Helper functions extracted to reduce cognitive complexity
const getStringParam = (functionParams: FunctionParams, key: string): string =>
  (functionParams[key] as string | undefined) ?? '';

const getArrayParam = (functionParams: FunctionParams, key: string): string[] =>
  Array.isArray(functionParams[key]) ? functionParams[key] : [];

const getUnitLabel = (unit: string): string => {
  const unitLabelMap: Record<string, string> = {
    percentage: '%',
    G: 'GB',
    T: 'TB',
  };
  return unitLabelMap[unit] ?? unit;
};

const getUnitValue = (unit: string): string => (unit === 'percentage' ? '%' : unit);

const getDefaultUnit = (units: string[]): string => (units[0] === 'percentage' ? '%' : units[0]);

const filterOption = (input: string, option?: { label?: string }): boolean =>
  (option?.label ?? '').toLowerCase().includes(input.toLowerCase());

const getMachineOptions = (
  machinesData: Machine[],
  currentMachineName: string | undefined,
  t: TranslateFn
) =>
  machinesData.map((machine) => {
    const name = machine.machineName ?? '';
    return {
      value: name,
      label: name === currentMachineName ? `${name} (${t('machines:currentMachine')})` : name,
    };
  });

const getStorageOptions = (storageData: GetTeamStorages_ResultSet1[]) =>
  storageData.map((storage) => ({
    value: storage.storageName ?? '',
    label: storage.storageName ?? '',
  }));

// Size parameter field component
const SizeParameterField: React.FC<{
  paramName: string;
  paramInfo: QueueFunctionParameter;
  functionParams: FunctionParams;
  onParamChange: (paramName: string, value: FunctionParamValue) => void;
}> = ({ paramName, paramInfo, functionParams, onParamChange }) => {
  const units = paramInfo.units ?? [];
  const defaultUnit = getDefaultUnit(units);
  const currentUnit = (functionParams[`${paramName}_unit`] as string | undefined) ?? defaultUnit;

  const handleValueChange = (value: number | string | null) => {
    if (value === null) {
      onParamChange(`${paramName}_value`, undefined);
      onParamChange(paramName, '');
      return;
    }
    const numValue = typeof value === 'string' ? Number.parseInt(value, 10) : value;
    if (Number.isNaN(numValue) || numValue <= 0) return;

    onParamChange(`${paramName}_value`, numValue);
    onParamChange(paramName, `${numValue}${currentUnit}`);
  };

  const handleUnitChange = (unitValue: string) => {
    const unit = String(unitValue);
    const currentValue = functionParams[`${paramName}_value`];
    onParamChange(`${paramName}_unit`, unit);
    onParamChange(paramName, typeof currentValue === 'number' ? `${currentValue}${unit}` : '');
  };

  return (
    <Flex align="center" wrap>
      <InputNumber
        value={
          typeof functionParams[`${paramName}_value`] === 'number'
            ? (functionParams[`${paramName}_value`] as number)
            : undefined
        }
        onChange={handleValueChange}
        parser={(value) => {
          const parsed = value?.replaceAll(/[^\d]/g, '');
          return parsed ? Number.parseInt(parsed, 10) : 0;
        }}
        formatter={(v) => (v ? `${v}` : '')}
        placeholder={units.includes('percentage') ? '95' : '100'}
        min={1}
        max={units.includes('percentage') ? 100 : undefined}
        keyboard
        step={1}
        precision={0}
        data-testid={`function-modal-param-${paramName}-value`}
      />
      <Select
        value={currentUnit}
        onChange={handleUnitChange}
        options={units.map((unit: string) => ({
          value: getUnitValue(unit),
          label: getUnitLabel(unit),
        }))}
        data-testid={`function-modal-param-${paramName}-unit`}
      />
    </Flex>
  );
};

// Options select field component
const OptionsSelectField: React.FC<{
  paramName: string;
  paramInfo: QueueFunctionParameter;
  functionParams: FunctionParams;
  onParamChange: (paramName: string, value: FunctionParamValue) => void;
}> = ({ paramName, paramInfo, functionParams, onParamChange }) => {
  const handleChange = (value: string) => {
    const previousValue = functionParams[paramName];
    onParamChange(paramName, value);
    if (paramName === 'destinationType' && value !== previousValue) {
      onParamChange('to', '');
    }
  };

  return (
    <Select
      value={
        getStringParam(functionParams, paramName) ||
        (typeof paramInfo.default === 'string' ? paramInfo.default : '')
      }
      onChange={handleChange}
      placeholder={typeof paramInfo.help === 'string' ? paramInfo.help : ''}
      options={(paramInfo.options ?? []).map((option: string) => ({
        value: option,
        label: option,
      }))}
      data-testid={`function-modal-param-${paramName}`}
    />
  );
};

// Repository dropdown field component
const RepoDropdownField: React.FC<{
  paramName: string;
  functionParams: FunctionParams;
  repositories: Repository[];
  onParamChange: (paramName: string, value: FunctionParamValue) => void;
  t: TranslateFn;
}> = ({ paramName, functionParams, repositories, onParamChange, t }) => (
  <Select
    value={getStringParam(functionParams, paramName)}
    onChange={(value) => onParamChange(paramName, value)}
    placeholder={t('resources:repositories.selectRepository')}
    options={repositories.map((repository) => ({
      value: repository.repositoryGuid ?? '',
      label: repository.repositoryName ?? '',
    }))}
    notFoundContent={t('resources:repositories.noRepositoriesFound')}
    showSearch
    filterOption={filterOption}
    data-testid={`function-modal-param-${paramName}`}
  />
);

// Type-based dropdown field component (destination/source)
const TypeBasedDropdownField: React.FC<{
  paramName: string;
  typeParamName: string;
  functionParams: FunctionParams;
  machinesData: Machine[];
  storageData: GetTeamStorages_ResultSet1[];
  currentMachineName?: string;
  onParamChange: (paramName: string, value: FunctionParamValue) => void;
  t: TranslateFn;
}> = ({
  paramName,
  typeParamName,
  functionParams,
  machinesData,
  storageData,
  currentMachineName,
  onParamChange,
  t,
}) => {
  const selectedType = getStringParam(functionParams, typeParamName);
  const isMachineType = selectedType === 'machine';

  return (
    <Select
      value={getStringParam(functionParams, paramName)}
      onChange={(value) => onParamChange(paramName, value)}
      placeholder={
        isMachineType ? t('machines:selectMachine') : t('resources:storage.selectStorage')
      }
      options={
        isMachineType
          ? getMachineOptions(machinesData, currentMachineName, t)
          : getStorageOptions(storageData)
      }
      notFoundContent={
        isMachineType ? t('machines:noMachinesFound') : t('resources:storage.noStorageFound')
      }
      showSearch
      filterOption={filterOption}
      disabled={!selectedType}
      data-testid={`function-modal-param-${paramName}`}
    />
  );
};

// Machine multiselect field component
const MachineMultiselectField: React.FC<{
  paramName: string;
  functionParams: FunctionParams;
  machinesData: Machine[];
  currentMachineName?: string;
  onParamChange: (paramName: string, value: FunctionParamValue) => void;
  t: TranslateFn;
}> = ({ paramName, functionParams, machinesData, currentMachineName, onParamChange, t }) => (
  <Select
    mode="multiple"
    value={getArrayParam(functionParams, paramName)}
    onChange={(value) => onParamChange(paramName, value)}
    placeholder={t('machines:selectMachines')}
    options={getMachineOptions(machinesData, currentMachineName, t)}
    notFoundContent={t('machines:noMachinesFound')}
    showSearch
    filterOption={filterOption}
    data-testid={`function-modal-param-${paramName}`}
  />
);

// Storage multiselect field component
const StorageMultiselectField: React.FC<{
  paramName: string;
  functionParams: FunctionParams;
  storageData: GetTeamStorages_ResultSet1[];
  onParamChange: (paramName: string, value: FunctionParamValue) => void;
  t: TranslateFn;
}> = ({ paramName, functionParams, storageData, onParamChange, t }) => (
  <Select
    mode="multiple"
    value={getArrayParam(functionParams, paramName)}
    onChange={(value) => onParamChange(paramName, value)}
    placeholder={t('resources:storage.selectStorageSystems')}
    options={getStorageOptions(storageData)}
    notFoundContent={t('resources:storage.noStorageFound')}
    showSearch
    filterOption={filterOption}
    data-testid={`function-modal-param-${paramName}`}
  />
);

// Checkbox group field component
const CheckboxGroupField: React.FC<{
  paramName: string;
  paramInfo: QueueFunctionParameter;
  functionParams: FunctionParams;
  onParamChange: (paramName: string, value: FunctionParamValue) => void;
  t: TranslateFn;
}> = ({ paramName, paramInfo, functionParams, onParamChange, t }) => {
  const selectedValues = getStringParam(functionParams, paramName).split(' ').filter(Boolean);
  const checkboxOptions = paramInfo.checkboxOptions ?? [];

  const handleCheckboxChange = (optionValue: string, checked: boolean) => {
    const updatedValues = checked
      ? Array.from(new Set([...selectedValues, optionValue]))
      : selectedValues.filter((value) => value !== optionValue);
    onParamChange(paramName, updatedValues.join(' '));
  };

  return (
    <Flex vertical className="gap-sm">
      {checkboxOptions.map((option: { value: string; label: string }) => (
        <Checkbox
          key={option.value}
          checked={selectedValues.includes(option.value)}
          onChange={(e) => handleCheckboxChange(option.value, e.target.checked)}
          data-testid={`function-modal-param-${paramName}-${option.value}`}
        >
          {t(`functions:checkboxOptions.${option.label}`)}
        </Checkbox>
      ))}
      <Input
        value={getStringParam(functionParams, paramName)}
        onChange={(e) => onParamChange(paramName, e.target.value)}
        placeholder={t('functions:additionalOptions')}
        autoComplete="off"
        data-testid={`function-modal-param-${paramName}-additional`}
      />
    </Flex>
  );
};

// Helper: Render field based on UI type using switch
const renderUITypeField = (
  paramInfo: QueueFunctionParameter,
  props: FunctionParameterFieldProps,
  t: TranslateFn
): React.ReactElement | null => {
  const {
    paramName,
    functionParams,
    onParamChange,
    onTemplatesChange,
    onTemplateView,
    selectedTemplates,
    repositories = [],
    machinesData = [],
    storageData = [],
    currentMachineName,
  } = props;

  switch (paramInfo.ui) {
    case 'repo-dropdown':
      return (
        <RepoDropdownField
          paramName={paramName}
          functionParams={functionParams}
          repositories={repositories}
          onParamChange={onParamChange}
          t={t}
        />
      );
    case 'destination-dropdown':
      return (
        <TypeBasedDropdownField
          paramName={paramName}
          typeParamName="destinationType"
          functionParams={functionParams}
          machinesData={machinesData}
          storageData={storageData}
          currentMachineName={currentMachineName}
          onParamChange={onParamChange}
          t={t}
        />
      );
    case 'source-dropdown':
      return (
        <TypeBasedDropdownField
          paramName={paramName}
          typeParamName="sourceType"
          functionParams={functionParams}
          machinesData={machinesData}
          storageData={storageData}
          currentMachineName={currentMachineName}
          onParamChange={onParamChange}
          t={t}
        />
      );
    case 'machine-multiselect':
      return (
        <MachineMultiselectField
          paramName={paramName}
          functionParams={functionParams}
          machinesData={machinesData}
          currentMachineName={currentMachineName}
          onParamChange={onParamChange}
          t={t}
        />
      );
    case 'storage-multiselect':
      return (
        <StorageMultiselectField
          paramName={paramName}
          functionParams={functionParams}
          storageData={storageData}
          onParamChange={onParamChange}
          t={t}
        />
      );
    case 'template-selector':
      return (
        <TemplateSelector
          value={selectedTemplates}
          onChange={(templateIds) =>
            onTemplatesChange(Array.isArray(templateIds) ? templateIds : [])
          }
          onViewDetails={(templateName) => onTemplateView(templateName)}
          multiple
        />
      );
    case 'checkbox':
      if (!paramInfo.checkboxOptions) return null;
      return (
        <CheckboxGroupField
          paramName={paramName}
          paramInfo={paramInfo}
          functionParams={functionParams}
          onParamChange={onParamChange}
          t={t}
        />
      );
    default:
      return null;
  }
};

// Main component with reduced complexity using switch
const FunctionParameterField: React.FC<FunctionParameterFieldProps> = (props) => {
  const { paramName, paramInfo, functionParams, onParamChange } = props;
  const { t } = useTranslation(['functions', 'common', 'machines', 'resources']);

  // Size parameter (format-based, checked first)
  if (paramInfo.format === 'size' && paramInfo.units) {
    return (
      <SizeParameterField
        paramName={paramName}
        paramInfo={paramInfo}
        functionParams={functionParams}
        onParamChange={onParamChange}
      />
    );
  }

  // Options select (options-based)
  if (paramInfo.options && paramInfo.options.length > 0) {
    return (
      <OptionsSelectField
        paramName={paramName}
        paramInfo={paramInfo}
        functionParams={functionParams}
        onParamChange={onParamChange}
      />
    );
  }

  // UI type-based fields
  const uiTypeField = renderUITypeField(paramInfo, props, t);
  if (uiTypeField) return uiTypeField;

  // Default: text input
  return (
    <Input
      value={getStringParam(functionParams, paramName)}
      onChange={(e) => onParamChange(paramName, e.target.value)}
      placeholder={typeof paramInfo.help === 'string' ? paramInfo.help : ''}
      autoComplete="off"
      data-testid={`function-modal-param-${paramName}`}
    />
  );
};

export default FunctionParameterField;
