import React from 'react'
import { 
  Card, 
  Space, 
  Typography, 
  Divider, 
  Empty, 
  Button, 
  Timeline,
  Tag,
  Spin,
  Alert
} from 'antd'
import { 
  DatabaseOutlined,
  CloudServerOutlined,
  HddOutlined,
  CopyOutlined,
  HistoryOutlined,
  RightOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { Machine } from '@/types'
import { useGetMachineAssignmentStatus } from '@/api/queries/distributedStorage'
import MachineAssignmentStatusBadge from './MachineAssignmentStatusBadge'

const { Text, Title } = Typography

interface DistributedStorageSectionProps {
  machine: Machine
  onViewDetails?: () => void
  onManageAssignment?: () => void
}

export const DistributedStorageSection: React.FC<DistributedStorageSectionProps> = ({ 
  machine,
  onViewDetails,
  onManageAssignment
}) => {
  const { t } = useTranslation(['distributedStorage', 'machines'])
  
  // If machine already has distributedStorageClusterName, we know it's assigned to a cluster
  const hasClusterAssignment = !!machine.distributedStorageClusterName
  
  // Fetch assignment status only if not already known
  const { data: assignmentData, isLoading } = useGetMachineAssignmentStatus(
    machine.machineName,
    machine.teamName,
    !hasClusterAssignment // Only fetch if we don't already know it's assigned to a cluster
  )
  
  // Determine assignment status
  const assignmentType = hasClusterAssignment ? 'CLUSTER' : (assignmentData?.assignmentType || 'AVAILABLE')
  const assignmentDetails = hasClusterAssignment 
    ? `Assigned to cluster: ${machine.distributedStorageClusterName}`
    : assignmentData?.assignmentDetails
  
  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '20px' }} data-testid="ds-section-loading">
        <Spin />
      </div>
    )
  }
  
  return (
    <>
      <Divider style={{ margin: '24px 0' }} data-testid="ds-section-divider">
        <Space>
          <CloudServerOutlined />
          {t('machineSection.title')}
        </Space>
      </Divider>
      
      <Card size="small" data-testid="ds-section-card">
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          {/* Current Assignment Status */}
          <div>
            <Text type="secondary" style={{ display: 'block', marginBottom: 8 }} data-testid="ds-section-assignment-label">
              {t('assignment.currentAssignment')}
            </Text>
            <MachineAssignmentStatusBadge 
              assignmentType={assignmentType}
              assignmentDetails={assignmentDetails}
              size="default"
              data-testid="ds-section-assignment-badge"
            />
          </div>
          
          {/* Assignment Details */}
          {assignmentType !== 'AVAILABLE' && assignmentDetails && (
            <Alert
              message={assignmentDetails}
              type="info"
              icon={
                assignmentType === 'CLUSTER' ? <DatabaseOutlined /> :
                assignmentType === 'IMAGE' ? <HddOutlined /> :
                assignmentType === 'CLONE' ? <CopyOutlined /> :
                <CloudServerOutlined />
              }
              showIcon
              data-testid="ds-section-assignment-alert"
            />
          )}
          
          {/* Action Buttons */}
          <Space>
            {onViewDetails && (
              <Button 
                size="small" 
                icon={<HistoryOutlined />}
                onClick={onViewDetails}
                data-testid="ds-section-history-button"
              >
                {t('assignment.history')}
              </Button>
            )}
            {onManageAssignment && assignmentType !== 'AVAILABLE' && (
              <Button 
                size="small" 
                type="primary"
                icon={<RightOutlined />}
                onClick={onManageAssignment}
                data-testid="ds-section-manage-button"
              >
                {t('machineSection.manageAssignment')}
              </Button>
            )}
          </Space>
          
          {/* Exclusivity Warning if assigned */}
          {assignmentType !== 'AVAILABLE' && (
            <Alert
              message={t('warnings.exclusivity')}
              type="warning"
              showIcon
              style={{ marginTop: 8 }}
              data-testid="ds-section-exclusivity-warning"
            />
          )}
        </Space>
      </Card>
    </>
  )
}