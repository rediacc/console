import React from 'react'
import { Select, Space, Tag, Spin, Typography, Empty } from 'antd'
import { CloudServerOutlined, CheckCircleOutlined, WarningOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import type { Machine } from '@/types'
import { useGetAvailableMachinesForClone } from '@/api/queries/distributedStorage'
import MachineAssignmentStatusBadge from './MachineAssignmentStatusBadge'

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
  
  const handleChange = (selectedValues: string[]) => {
    if (maxSelection && selectedValues.length > maxSelection) {
      return
    }
    onChange?.(selectedValues)
  }
  
  const filterOption = (input: string, option: any) => {
    const machine = machines.find(m => m.machineName === option.value)
    if (!machine) return false
    
    return machine.machineName.toLowerCase().includes(input.toLowerCase()) ||
           machine.teamName.toLowerCase().includes(input.toLowerCase()) ||
           (machine.bridgeName && machine.bridgeName.toLowerCase().includes(input.toLowerCase()))
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
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Space>
            <CloudServerOutlined />
            <Text strong={!isDisabled}>{machine.machineName}</Text>
            <Tag color="#8FBC8F" size="small">{machine.teamName}</Tag>
            {machine.bridgeName && (
              <Tag color="green" size="small">{machine.bridgeName}</Tag>
            )}
          </Space>
          {showAssignmentStatus && (
            <div style={{ marginLeft: 'auto' }}>
              {isAssigned ? (
                machine.distributedStorageClusterName ? (
                  <Tag color="blue" icon={<WarningOutlined />}>
                    {t('machines:assignmentStatus.cluster')}: {machine.distributedStorageClusterName}
                  </Tag>
                ) : machine.assignmentStatus ? (
                  <MachineAssignmentStatusBadge 
                    assignmentType={machine.assignmentStatus.assignmentType}
                    assignmentDetails={machine.assignmentStatus.assignmentDetails}
                    size="small"
                  />
                ) : null
              ) : (
                <Tag color="green" icon={<CheckCircleOutlined />}>
                  {t('machines:assignmentStatus.available')}
                </Tag>
              )}
            </div>
          )}
        </div>
      </Option>
    )
  }
  
  if (loading) {
    return <Spin />
  }
  
  return (
    <Select
      mode="multiple"
      style={style || { width: '100%' }}
      placeholder={placeholder || t('machines:selectMachines')}
      value={value}
      onChange={handleChange}
      disabled={disabled}
      loading={loading}
      filterOption={filterOption}
      showSearch
      optionLabelProp="label"
      notFoundContent={
        machines.length === 0 ? (
          <Empty description={t('machines:noAvailableMachines')} />
        ) : (
          <Empty description={t('common:noMatchingResults')} />
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
  const { t } = useTranslation(['machines'])
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