import { Empty, Flex, Select, Tag, Typography } from 'antd';
import type { DefaultOptionType } from 'antd/es/select';
import React from 'react';
import { useTranslation } from 'react-i18next';
import type { Machine } from '@/types';
import { CheckCircleOutlined, CloudServerOutlined, WarningOutlined } from '@/utils/optimizedIcons';

interface AvailableMachinesSelectorProps {
  machines: Machine[];
  value?: string[];
  onChange?: (value: string[]) => void;
  loading?: boolean;
  placeholder?: string;
  disabled?: boolean;
  showAssignmentStatus?: boolean;
  allowSelectAssigned?: boolean;
  maxSelection?: number;
  style?: React.CSSProperties;
}

export const AvailableMachinesSelector: React.FC<AvailableMachinesSelectorProps> = ({
  machines,
  value = [],
  onChange,
  loading = false,
  placeholder,
  disabled = false,
  showAssignmentStatus = true,
  allowSelectAssigned = false,
  maxSelection,
  style,
}) => {
  const { t } = useTranslation(['machines', 'common']);

  const handleChange = (selectedValues: unknown) => {
    const values = selectedValues as string[];
    if (maxSelection && values.length > maxSelection) {
      return;
    }
    onChange?.(values);
  };

  const filterOption = (input: string, option?: DefaultOptionType): boolean => {
    if (!option || typeof option.value !== 'string') return false;

    const machine = machines.find((m) => m.machineName === option.value);
    if (!machine) return false;

    const loweredInput = input.toLowerCase();
    return (
      (machine.machineName ?? '').toLowerCase().includes(loweredInput) ||
      (machine.teamName ?? '').toLowerCase().includes(loweredInput) ||
      (!!machine.bridgeName && machine.bridgeName.toLowerCase().includes(loweredInput))
    );
  };

  const renderMachineOption = (machine: Machine) => {
    // assignmentStatus is now a simple string: 'ASSIGNED' | 'UNASSIGNED'
    const isAssigned = machine.cephClusterName ?? machine.assignmentStatus === 'ASSIGNED';
    const isDisabled = !allowSelectAssigned && isAssigned;

    return (
      <Select.Option
        key={machine.machineName}
        value={machine.machineName}
        label={machine.machineName}
        disabled={isDisabled}
        data-testid={`available-machines-option-${machine.machineName}`}
      >
        <Flex
          data-testid={`available-machines-option-content-${machine.machineName}`}
          align="center"
          className="w-full"
        >
          <Flex align="center" wrap className="inline-flex">
            <Typography.Text className="inline-flex items-center text-base">
              <CloudServerOutlined />
            </Typography.Text>
            <Typography.Text className="font-semibold">{machine.machineName}</Typography.Text>
            <Tag
              bordered={false}
              data-testid={`available-machines-team-tag-${machine.machineName}`}
            >
              {machine.teamName}
            </Tag>
            {machine.bridgeName && (
              <Tag
                bordered={false}
                data-testid={`available-machines-bridge-tag-${machine.machineName}`}
              >
                {machine.bridgeName}
              </Tag>
            )}
          </Flex>
          {showAssignmentStatus && (
            <Flex align="center">
              {(() => {
                if (isAssigned && machine.cephClusterName) {
                  return (
                    <Tag data-testid={`available-machines-cluster-tag-${machine.machineName}`}>
                      <Typography.Text className="inline-flex text-xs">
                        <WarningOutlined />
                      </Typography.Text>
                      <Typography.Text className="text-xs">
                        {t('machines:assignmentStatus.cluster')}: {machine.cephClusterName}
                      </Typography.Text>
                    </Tag>
                  );
                } else if (isAssigned) {
                  return (
                    <Tag data-testid={`available-machines-assigned-tag-${machine.machineName}`}>
                      <Typography.Text className="inline-flex text-xs">
                        <WarningOutlined />
                      </Typography.Text>
                      <Typography.Text className="text-xs">
                        {t('machines:assignmentStatus.assigned', 'Assigned')}
                      </Typography.Text>
                    </Tag>
                  );
                }
                return (
                  <Tag data-testid={`available-machines-available-tag-${machine.machineName}`}>
                    <Typography.Text className="inline-flex text-xs">
                      <CheckCircleOutlined />
                    </Typography.Text>
                    <Typography.Text className="text-xs">
                      {t('machines:assignmentStatus.available')}
                    </Typography.Text>
                  </Tag>
                );
              })()}
            </Flex>
          )}
        </Flex>
      </Select.Option>
    );
  };

  return (
    <Select
      mode="multiple"
      // eslint-disable-next-line no-restricted-syntax
      style={{ width: '100%', ...style }}
      placeholder={placeholder ?? t('machines:selectMachines')}
      value={value}
      onChange={handleChange}
      disabled={disabled}
      loading={loading}
      filterOption={filterOption}
      showSearch
      optionLabelProp="label"
      data-testid="available-machines-selector"
      notFoundContent={
        machines.length === 0 ? (
          <Empty
            description={<Typography.Text>{t('machines:noAvailableMachines')}</Typography.Text>}
          />
        ) : (
          <Empty description={<Typography.Text>{t('common:noMatchingResults')}</Typography.Text>} />
        )
      }
    >
      {machines.map(renderMachineOption)}
    </Select>
  );
};
