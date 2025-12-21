import React from 'react';
import { Empty, Flex, Select, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useAvailableMachinesForClone } from '@/api/queries/ceph';
import type { Machine } from '@/types';
import { CheckCircleOutlined, CloudServerOutlined, WarningOutlined } from '@/utils/optimizedIcons';
import type { DefaultOptionType } from 'antd/es/select';

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
      machine.machineName.toLowerCase().includes(loweredInput) ||
      machine.teamName.toLowerCase().includes(loweredInput) ||
      (!!machine.bridgeName && machine.bridgeName.toLowerCase().includes(loweredInput))
    );
  };

  const renderMachineOption = (machine: Machine) => {
    // assignmentStatus is now a simple string: 'ASSIGNED' | 'UNASSIGNED'
    const isAssigned = machine.cephClusterName || machine.assignmentStatus === 'ASSIGNED';
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
          style={{ alignItems: 'center', width: '100%' }}
        >
          <Flex style={{ display: 'inline-flex', alignItems: 'center', flexWrap: 'wrap' }}>
            <Typography.Text style={{ display: 'inline-flex', alignItems: 'center', fontSize: 16 }}>
              <CloudServerOutlined />
            </Typography.Text>
            <Typography.Text
              style={{
                fontWeight: 600,
              }}
            >
              {machine.machineName}
            </Typography.Text>
            <Tag
              bordered={false}
              color="success"
              data-testid={`available-machines-team-tag-${machine.machineName}`}
            >
              {machine.teamName}
            </Tag>
            {machine.bridgeName && (
              <Tag
                bordered={false}
                color="processing"
                data-testid={`available-machines-bridge-tag-${machine.machineName}`}
              >
                {machine.bridgeName}
              </Tag>
            )}
          </Flex>
          {showAssignmentStatus && (
            <Flex align="center">
              {isAssigned ? (
                machine.cephClusterName ? (
                  <Tag
                    data-testid={`available-machines-cluster-tag-${machine.machineName}`}
                    color="processing"
                  >
                    <Typography.Text style={{ display: 'inline-flex', fontSize: 12 }}>
                      <WarningOutlined />
                    </Typography.Text>
                    <Typography.Text style={{ fontSize: 12 }}>
                      {t('machines:assignmentStatus.cluster')}: {machine.cephClusterName}
                    </Typography.Text>
                  </Tag>
                ) : (
                  <Tag
                    data-testid={`available-machines-assigned-tag-${machine.machineName}`}
                    color="warning"
                  >
                    <Typography.Text style={{ display: 'inline-flex', fontSize: 12 }}>
                      <WarningOutlined />
                    </Typography.Text>
                    <Typography.Text style={{ fontSize: 12 }}>
                      {t('machines:assignmentStatus.assigned', 'Assigned')}
                    </Typography.Text>
                  </Tag>
                )
              ) : (
                <Tag
                  data-testid={`available-machines-available-tag-${machine.machineName}`}
                  color="success"
                >
                  <Typography.Text style={{ display: 'inline-flex', fontSize: 12 }}>
                    <CheckCircleOutlined />
                  </Typography.Text>
                  <Typography.Text style={{ fontSize: 12 }}>
                    {t('machines:assignmentStatus.available')}
                  </Typography.Text>
                </Tag>
              )}
            </Flex>
          )}
        </Flex>
      </Select.Option>
    );
  };

  return (
    <Select
      mode="multiple"
      style={{ width: '100%', ...style }}
      placeholder={placeholder || t('machines:selectMachines')}
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

export const SimpleMachineSelector: React.FC<{
  teamName: string;
  value?: string[];
  onChange?: (value: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
  style?: React.CSSProperties;
}> = ({ teamName, value, onChange, placeholder, disabled, style }) => {
  const { t: _t } = useTranslation(['machines']);
  const { data: machines = [], isLoading } = useAvailableMachinesForClone(teamName, !disabled);

  return (
    <AvailableMachinesSelector
      // AvailableMachine has subset of Machine properties needed for display
      machines={machines as unknown as Machine[]}
      value={value}
      onChange={onChange}
      loading={isLoading}
      placeholder={placeholder}
      disabled={disabled}
      style={style}
    />
  );
};
