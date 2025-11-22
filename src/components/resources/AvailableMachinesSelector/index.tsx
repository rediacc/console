import React from 'react'
import { Select, Spin, Empty } from 'antd'
import type { DefaultOptionType } from 'antd/es/select'
import { CloudServerOutlined, CheckCircleOutlined, WarningOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import type { Machine } from '@/types'
import { useGetAvailableMachinesForClone } from '@/api/queries/distributedStorage'
import MachineAssignmentStatusBadge from '../MachineAssignmentStatusBadge'
import {
  StyledSelect,
  OptionContent,
  MachineMeta,
  MachineIcon,
  MachineName,
  TeamTag,
  BridgeTag,
  StatusContainer,
  StatusTag,
  StatusIcon,
  StatusText,
  SpinnerWrapper,
  EmptyDescription,
} from './styles'

const { Option } = Select

interface AvailableMachinesSelectorProps {
  machines: Machine[]
  value?: string[]
  onChange?: (value: string[]) => void
  loading?: boolean
  placeholder?: string
  disabled?: boolean
  showAssignmentStatus?: boolean
  allowSelectAssigned?: boolean
  maxSelection?: number
  style?: React.CSSProperties
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
  const { t } = useTranslation(['machines', 'common'])

  const handleChange = (selectedValues: unknown) => {
    const values = selectedValues as string[]
    if (maxSelection && values.length > maxSelection) {
      return
    }
    onChange?.(values)
  }

  const filterOption = (input: string, option?: DefaultOptionType): boolean => {
    if (!option || typeof option.value !== 'string') return false

    const machine = machines.find((m) => m.machineName === option.value)
    if (!machine) return false

    const loweredInput = input.toLowerCase()
    return (
      machine.machineName.toLowerCase().includes(loweredInput) ||
      machine.teamName.toLowerCase().includes(loweredInput) ||
      (!!machine.bridgeName && machine.bridgeName.toLowerCase().includes(loweredInput))
    )
  }

  const renderMachineOption = (machine: Machine) => {
    const isAssigned =
      machine.distributedStorageClusterName ||
      machine.assignmentStatus?.assignmentType !== 'AVAILABLE'
    const isDisabled = !allowSelectAssigned && isAssigned

    return (
      <Option
        key={machine.machineName}
        value={machine.machineName}
        label={machine.machineName}
        disabled={isDisabled}
        data-testid={`available-machines-option-${machine.machineName}`}
      >
        <OptionContent data-testid={`available-machines-option-content-${machine.machineName}`}>
          <MachineMeta>
            <MachineIcon as={CloudServerOutlined} />
            <MachineName $dimmed={!!isDisabled}>{machine.machineName}</MachineName>
            <TeamTag data-testid={`available-machines-team-tag-${machine.machineName}`}>
              {machine.teamName}
            </TeamTag>
            {machine.bridgeName && (
              <BridgeTag data-testid={`available-machines-bridge-tag-${machine.machineName}`}>
                {machine.bridgeName}
              </BridgeTag>
            )}
          </MachineMeta>
          {showAssignmentStatus && (
            <StatusContainer>
              {isAssigned ? (
                machine.distributedStorageClusterName ? (
                  <StatusTag
                    $variant="cluster"
                    data-testid={`available-machines-cluster-tag-${machine.machineName}`}
                  >
                    <StatusIcon as={WarningOutlined} />
                    <StatusText>
                      {t('machines:assignmentStatus.cluster')}: {machine.distributedStorageClusterName}
                    </StatusText>
                  </StatusTag>
                ) : machine.assignmentStatus ? (
                  <MachineAssignmentStatusBadge
                    assignmentType={machine.assignmentStatus.assignmentType}
                    assignmentDetails={machine.assignmentStatus.assignmentDetails}
                    size="small"
                  />
                ) : null
              ) : (
                <StatusTag
                  $variant="available"
                  data-testid={`available-machines-available-tag-${machine.machineName}`}
                >
                  <StatusIcon as={CheckCircleOutlined} />
                  <StatusText>{t('machines:assignmentStatus.available')}</StatusText>
                </StatusTag>
              )}
            </StatusContainer>
          )}
        </OptionContent>
      </Option>
    )
  }

  if (loading) {
    return (
      <SpinnerWrapper>
        <Spin />
      </SpinnerWrapper>
    )
  }

  return (
    <StyledSelect
      mode="multiple"
      style={style}
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
          <Empty description={<EmptyDescription>{t('machines:noAvailableMachines')}</EmptyDescription>} />
        ) : (
          <Empty description={<EmptyDescription>{t('common:noMatchingResults')}</EmptyDescription>} />
        )
      }
    >
      {machines.map(renderMachineOption)}
    </StyledSelect>
  )
}

export const SimpleMachineSelector: React.FC<{
  teamName: string
  value?: string[]
  onChange?: (value: string[]) => void
  placeholder?: string
  disabled?: boolean
  style?: React.CSSProperties
}> = ({ teamName, value, onChange, placeholder, disabled, style }) => {
  const { t: _t } = useTranslation(['machines'])
  const { data: machines = [], isLoading } = useGetAvailableMachinesForClone(teamName, !disabled)

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
  )
}
