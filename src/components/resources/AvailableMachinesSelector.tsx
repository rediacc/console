import React from 'react'
import { Select, Space, Tag, Spin, Typography, Empty } from 'antd'
import { CloudServerOutlined, CheckCircleOutlined, WarningOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import type { Machine } from '@/types'
import { useGetAvailableMachinesForClone } from '@/api/queries/distributedStorage'
import MachineAssignmentStatusBadge from './MachineAssignmentStatusBadge'
import { useComponentStyles, useFormStyles } from '@/hooks/useComponentStyles'

const { Text } = Typography
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
  style
}) => {
  const { t } = useTranslation(['machines', 'common'])
  const styles = useComponentStyles()
  const formStyles = useFormStyles()
  
  const handleChange = (selectedValues: string[]) => {
    if (maxSelection && selectedValues.length > maxSelection) {
      return
    }
    onChange?.(selectedValues)
  }
  
  const filterOption = (input: string, option: any): boolean => {
    const machine = machines.find(m => m.machineName === option.value)
    if (!machine) return false

    return !!(machine.machineName.toLowerCase().includes(input.toLowerCase()) ||
           machine.teamName.toLowerCase().includes(input.toLowerCase()) ||
           (machine.bridgeName && machine.bridgeName.toLowerCase().includes(input.toLowerCase())))
  }
  
  const renderMachineOption = (machine: Machine) => {
    const isAssigned = machine.distributedStorageClusterName || 
                      machine.assignmentStatus?.assignmentType !== 'AVAILABLE'
    const isDisabled = !allowSelectAssigned && isAssigned
    
    return (
      <Option 
        key={machine.machineName} 
        value={machine.machineName}
        disabled={isDisabled}
        data-testid={`available-machines-option-${machine.machineName}`}
      >
        <div 
          style={{
            ...styles.flexBetween,
            width: '100%'
          }} 
          data-testid={`available-machines-option-content-${machine.machineName}`}
        >
          <Space>
            <CloudServerOutlined style={styles.icon.small} />
            <Text 
              strong={!isDisabled}
              style={{
                ...styles.body,
                opacity: isDisabled ? 0.6 : 1
              }}
            >
              {machine.machineName}
            </Text>
            <Tag
              color="#8FBC8F"
              style={{
                borderRadius: 'var(--border-radius-sm)',
                ...styles.caption
              }}
              data-testid={`available-machines-team-tag-${machine.machineName}`}
            >
              {machine.teamName}
            </Tag>
            {machine.bridgeName && (
              <Tag
                color="green"
                style={{
                  borderRadius: 'var(--border-radius-sm)',
                  ...styles.caption
                }}
                data-testid={`available-machines-bridge-tag-${machine.machineName}`}
              >
                {machine.bridgeName}
              </Tag>
            )}
          </Space>
          {showAssignmentStatus && (
            <div style={{ marginLeft: 'auto' }}>
              {isAssigned ? (
                machine.distributedStorageClusterName ? (
                  <Tag 
                    color="blue" 
                    icon={<WarningOutlined style={styles.icon.small} />} 
                    style={{
                      borderRadius: 'var(--border-radius-sm)',
                      ...styles.caption
                    }}
                    data-testid={`available-machines-cluster-tag-${machine.machineName}`}
                  >
                    <span style={styles.caption}>
                      {t('machines:assignmentStatus.cluster')}: {machine.distributedStorageClusterName}
                    </span>
                  </Tag>
                ) : machine.assignmentStatus ? (
                  <MachineAssignmentStatusBadge 
                    assignmentType={machine.assignmentStatus.assignmentType}
                    assignmentDetails={machine.assignmentStatus.assignmentDetails}
                    size="small"
                  />
                ) : null
              ) : (
                <Tag 
                  color="green" 
                  icon={<CheckCircleOutlined style={styles.icon.small} />} 
                  style={{
                    borderRadius: 'var(--border-radius-sm)',
                    ...styles.caption
                  }}
                  data-testid={`available-machines-available-tag-${machine.machineName}`}
                >
                  <span style={styles.caption}>{t('machines:assignmentStatus.available')}</span>
                </Tag>
              )}
            </div>
          )}
        </div>
      </Option>
    )
  }
  
  if (loading) {
    return (
      <div style={styles.flexCenter}>
        <Spin />
      </div>
    )
  }
  
  return (
    <Select
      mode="multiple"
      style={{
        width: '100%',
        ...formStyles.formInput,
        ...style
      }}
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
            description={
              <span style={styles.body}>{t('machines:noAvailableMachines')}</span>
            } 
          />
        ) : (
          <Empty 
            description={
              <span style={styles.body}>{t('common:noMatchingResults')}</span>
            } 
          />
        )
      }
    >
      {machines.map(renderMachineOption)}
    </Select>
  )
}

// Export a simpler version for basic use cases
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
      machines={machines}
      value={value}
      onChange={onChange}
      loading={isLoading}
      placeholder={placeholder}
      disabled={disabled}
      style={style}
    />
  )
}